#!/usr/bin/env python3
"""
H181 Monthly Industry-Adjusted Reversal Rebalancer
CONFIRMED: OOS Sharpe 1.138, CAGR 24.6%, MaxDD -18.4% (2021-2026)

Signal: REV^IN_i = R_i(t) - R̄_industry(t)
  where R̄_industry = equal-weight avg return of same-GICS-sector stocks this month
  Long bottom-6 (most negative adj-reversal = strongest reversal candidates)

Strategy:
  - Universe: 30 large-cap S&P 500 stocks across 8 GICS sectors
  - Equal-weight: each of 6 positions = equity / 6
  - Monthly rebalance on first trading day of each month
  - Corr(H026) = 0.293 — genuine diversification from ETF rotation strategy

Usage:
    python3 h181_monthly.py            # live run
    python3 h181_monthly.py --dry-run  # print orders, no submission
    python3 h181_monthly.py --status   # show positions only
    python3 h181_monthly.py --force    # skip first-of-month guard
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ── Universe (30-stock GICS sector map) ─────────────────────────────────────
UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}

UNIVERSE  = list(UNIVERSE_SECTORS.keys())
N_HOLD    = 6       # bottom quintile (~6/30 = 20%)
LOG_FILE  = Path(__file__).parent / "h181_monthly_trades.json"
MIN_ORDER_USD = 5.0


# ── Signal computation ───────────────────────────────────────────────────────

def get_prior_month_returns() -> pd.Series:
    """Download last ~45 days of daily prices, return prior-calendar-month return per stock."""
    raw = yf.download(UNIVERSE, period="65d", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw[UNIVERSE] if set(UNIVERSE).issubset(raw.columns) else raw

    prices = prices.dropna(how="all", axis=1)
    monthly = prices.resample("ME").last()

    if len(monthly) < 2:
        raise ValueError("Not enough monthly data to compute prior-month returns")

    prior_close  = monthly.iloc[-2]
    signal_close = monthly.iloc[-1]

    rets = {}
    for t in UNIVERSE:
        if t in prior_close.index and t in signal_close.index:
            p0, p1 = prior_close[t], signal_close[t]
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                rets[t] = (p1 - p0) / p0

    return pd.Series(rets)


def industry_adjusted_reversal(monthly_returns: pd.Series) -> pd.Series:
    """
    Subtract equal-weight sector mean from each stock's return.
    Stocks that underperformed their sector most are best reversal candidates.
    Sort ascending → long bottom N.
    """
    sectors = pd.Series(UNIVERSE_SECTORS)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


def compute_signal() -> tuple[list[str], pd.Series]:
    """Return (long_tickers, full_adj_reversal_series)."""
    prior_rets = get_prior_month_returns()
    adj_rev = industry_adjusted_reversal(prior_rets)
    adj_rev_sorted = adj_rev.sort_values()
    long_tickers = adj_rev_sorted.head(N_HOLD).index.tolist()
    return long_tickers, adj_rev


# ── Alpaca helpers ───────────────────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_positions(client: TradingClient) -> dict[str, dict]:
    return {
        p.symbol: {
            "qty":          float(p.qty),
            "market_value": float(p.market_value),
            "avg_cost":     float(p.avg_entry_price),
        }
        for p in client.get_all_positions()
    }


def get_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


def get_latest_price(symbol: str) -> float:
    raw = yf.download(symbol, period="3d", auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(closes, pd.DataFrame):
        closes = closes[symbol]
    return float(closes.dropna().iloc[-1])


# ── Trade planning ───────────────────────────────────────────────────────────

def build_target(equity: float, long_tickers: list[str]) -> dict[str, float]:
    """Equal-weight: each position = equity / N_HOLD."""
    alloc = equity / N_HOLD
    return {sym: alloc for sym in long_tickers}


def build_trade_plan(
    target: dict[str, float],
    positions: dict[str, dict],
) -> list[dict]:
    """Diff current holdings against target → list of trade dicts."""
    all_syms = set(target) | set(positions)
    trades = []

    for sym in all_syms:
        tgt = target.get(sym, 0.0)
        cur = positions.get(sym, {}).get("market_value", 0.0)
        diff = tgt - cur

        if abs(diff) < MIN_ORDER_USD:
            continue

        price = get_latest_price(sym)
        if price <= 0:
            continue
        qty = abs(diff) / price

        action = "BUY" if diff > 0 else "SELL"
        if action == "SELL" and sym in positions:
            qty = min(qty, positions[sym]["qty"])

        trades.append({
            "symbol":    sym,
            "action":    action,
            "qty":       round(qty, 6),
            "est_value": round(abs(diff), 2),
            "reason":    f"target ${tgt:,.0f}, current ${cur:,.0f}",
        })

    # Sells first to free cash, then buys
    return [t for t in trades if t["action"] == "SELL"] + \
           [t for t in trades if t["action"] == "BUY"]


def execute_trades(client: TradingClient, trades: list[dict], dry_run: bool) -> list[dict]:
    executed = []
    for t in trades:
        tag = "[DRY RUN] " if dry_run else ""
        print(f"  {tag}{t['action']:4} {t['qty']:>10.4f} {t['symbol']:<6}  "
              f"~${t['est_value']:>9,.0f}  ({t['reason']})")
        if dry_run:
            continue
        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=t["symbol"],
                qty=t["qty"],
                side=OrderSide.BUY if t["action"] == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            print(f"         ✓ order_id={order.id}")
            executed.append({**t, "order_id": str(order.id), "submitted_at": datetime.now().isoformat()})
        except Exception as e:
            print(f"         ✗ ERROR: {e}")
    return executed


# ── First-trading-day guard ──────────────────────────────────────────────────

def is_first_trading_day() -> bool:
    today = date.today()
    if today.weekday() >= 5:
        return False
    if today.day > 4:
        return False
    for d in range(1, today.day):
        candidate = date(today.year, today.month, d)
        if candidate.weekday() < 5:
            return False
    return True


# ── Logging ──────────────────────────────────────────────────────────────────

def load_trade_log() -> list:
    if not LOG_FILE.exists():
        return []
    return json.loads(LOG_FILE.read_text())


def log_run(entry: dict):
    log = json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--force",   action="store_true", help="Skip first-of-month guard")
    args = parser.parse_args()

    if not args.force and not args.status and not is_first_trading_day():
        print(f"Not the first trading day of the month ({date.today()}). Skipping. Use --force to override.")
        sys.exit(0)

    client    = get_client()
    positions = get_positions(client)
    equity    = get_equity(client)

    print(f"\nH181 Monthly Industry-Adjusted Reversal — {date.today()}")
    print(f"Account equity: ${equity:,.2f}")

    if positions:
        print("\nCurrent positions:")
        for sym, pos in sorted(positions.items()):
            print(f"  {sym:<6} {pos['qty']:>10.4f} sh  ${pos['market_value']:>10,.2f}")
    else:
        print("\nNo current positions.")

    if args.status:
        return

    print("\nFetching signal (prior-month industry-adjusted returns)…")
    long_tickers, adj_rev = compute_signal()

    print(f"\nSignal rankings (adj reversal — bottom {N_HOLD} are LONG):")
    for sym, val in adj_rev.sort_values().items():
        mark = "★ LONG" if sym in long_tickers else "      "
        sector = UNIVERSE_SECTORS.get(sym, "?")
        print(f"  {mark} {sym:<6} adj_rev={val:>+7.3f}  ({sector})")

    print(f"\nTarget: long {long_tickers} — equal weight {100/N_HOLD:.1f}% each")

    target = build_target(equity, long_tickers)

    print("\nTarget allocations:")
    for sym, usd in sorted(target.items(), key=lambda x: -x[1]):
        print(f"  {sym:<6} ${usd:>10,.0f}  ({usd/equity*100:.1f}%)")

    trades = build_trade_plan(target, positions)

    if not trades:
        print("\nNo rebalance needed — portfolio matches target.")
        return

    print(f"\nTrade plan ({len(trades)} orders):")
    executed = execute_trades(client, trades, dry_run=args.dry_run)

    if not args.dry_run and executed:
        log_run({
            "date":         date.today().isoformat(),
            "equity":       equity,
            "long_tickers": long_tickers,
            "target":       target,
            "adj_reversal": {k: round(float(v), 5) for k, v in adj_rev.items()},
            "trades":       executed,
        })
        print(f"\n✓ Logged {len(executed)} trades to {LOG_FILE.name}")
    elif args.dry_run:
        print(f"\n[DRY RUN] {len(trades)} orders would be submitted.")


if __name__ == "__main__":
    main()
