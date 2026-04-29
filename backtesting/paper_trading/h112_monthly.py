#!/usr/bin/env python3
"""
H116 Monthly Portfolio Rebalancer
Manages H041a (22%), H026 (27%), H045 (21%) sub-strategies.

H116 upgrade (vs H112): H026 uses TSMOM filter — only assets with positive
12-month return are eligible for the composite ranking. When nothing qualifies,
H026 allocates to cash. Confirmed +14.6% OOS improvement in backtests.

Run on the first trading day of each month at ~9:45 AM CT.
Usage:
    python3 h112_monthly.py            # live run
    python3 h112_monthly.py --dry-run  # print orders, no submission
    python3 h112_monthly.py --status   # show positions only
    python3 h112_monthly.py --force    # skip "first-of-month" guard
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

# ── Universe definitions (H112 confirmed) ──────────────────────────────────
H041A_ASSETS = [
    "SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
    "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN",
]
H026_ASSETS = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO",
]
H045_ASSETS = [
    "SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY",
]

SUB_STRATS = {
    "h041a": {"assets": H041A_ASSETS, "n_hold": 1, "weight": 0.22, "tsmom_filter": False},
    "h026":  {"assets": H026_ASSETS,  "n_hold": 1, "weight": 0.27, "tsmom_filter": True},  # H116 upgrade
    "h045":  {"assets": H045_ASSETS,  "n_hold": 2, "weight": 0.21, "tsmom_filter": False},
}

LOG_FILE = Path(__file__).parent / "h112_monthly_trades.json"
MIN_ORDER_USD = 5.0  # ignore rebalance deltas smaller than $5


# ── Signal computation ──────────────────────────────────────────────────────

def compute_signal(assets: list[str], n_hold: int,
                   tsmom_filter: bool = False) -> tuple[list[str], dict]:
    """
    12-month momentum rank + inv 6-month vol rank → top-N.
    tsmom_filter: if True (H116 upgrade), only assets with positive 12m return
    are eligible. Returns ([], {}) when nothing qualifies → sub-strategy goes
    to cash for the month.
    Returns (top_n_tickers, scores_dict).
    """
    tickers = list(set(assets))
    raw = yf.download(tickers, period="15mo", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices = prices[assets].dropna(how="all", axis=1)

    monthly_px  = prices.resample("ME").last()
    monthly_ret = prices.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    mom_12 = (monthly_px / monthly_px.shift(12) - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)
    valid  = mom_12.index.intersection(vol_6.index)

    if tsmom_filter:
        valid = valid[mom_12[valid] > 0]
        if len(valid) == 0:
            return [], {}  # nothing qualifies → cash

    if len(valid) < n_hold:
        if len(valid) == 0:
            raise ValueError(f"No valid tickers after filtering")
        n_hold = len(valid)  # hold fewer if universe is thin

    score = mom_12[valid].rank() + vol_6[valid].rank(ascending=False)
    top_n = list(score.nlargest(n_hold).index)

    scores = {
        t: {
            "score":   round(float(score[t]), 2),
            "mom_12m": round(float(mom_12[t]) * 100, 1),
            "vol_6m":  round(float(vol_6.get(t, float("nan"))) * 100, 1),
        }
        for t in valid
    }
    return top_n, scores


# ── Alpaca helpers ──────────────────────────────────────────────────────────

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


# ── Trade planning ──────────────────────────────────────────────────────────

def build_target(equity: float) -> dict[str, float]:
    """
    Compute {symbol: target_usd} across all sub-strategies.
    Symbols held by multiple sub-strategies have their allocations summed.
    """
    target: dict[str, float] = {}
    signals: dict[str, tuple[list[str], dict]] = {}

    for name, cfg in SUB_STRATS.items():
        alloc_per_slot = equity * cfg["weight"] / cfg["n_hold"]
        top_n, scores = compute_signal(
            cfg["assets"], cfg["n_hold"],
            tsmom_filter=cfg.get("tsmom_filter", False),
        )
        signals[name] = (top_n, scores)
        for sym in top_n:
            target[sym] = target.get(sym, 0.0) + alloc_per_slot
        if not top_n:
            print(f"  {name.upper()}: TSMOM filter — no qualifying assets, holding cash this month")

    return target, signals


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
            # Never sell more than we have
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


# ── First-trading-day guard ─────────────────────────────────────────────────

def is_first_trading_day() -> bool:
    today = date.today()
    if today.weekday() >= 5:
        return False
    # It's the first trading day if today is the 1st, or if today ≤ 3rd and
    # every earlier day this month was a weekend/holiday (simple heuristic).
    if today.day > 4:
        return False
    for d in range(1, today.day):
        candidate = date(today.year, today.month, d)
        if candidate.weekday() < 5:  # found an earlier weekday this month
            return False
    return True


# ── Logging ─────────────────────────────────────────────────────────────────

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

    print(f"\nH116 Monthly Rebalancer — {date.today()}")
    print(f"Account equity: ${equity:,.2f}")

    if positions:
        print("\nCurrent positions:")
        for sym, pos in sorted(positions.items()):
            print(f"  {sym:<6} {pos['qty']:>10.4f} sh  ${pos['market_value']:>10,.2f}")
    else:
        print("\nNo current positions.")

    if args.status:
        return

    # Compute signals
    print("\nFetching signals (downloading ~15mo of price data)…")
    target, signals = build_target(equity)

    print("\nSub-strategy targets:")
    for name, (top_n, scores) in signals.items():
        cfg = SUB_STRATS[name]
        alloc_per = equity * cfg["weight"] / cfg["n_hold"]
        print(f"\n  {name.upper()} ({cfg['weight']*100:.0f}%):  top-{cfg['n_hold']} → {', '.join(top_n)}")
        for sym in sorted(scores, key=lambda s: -scores[s]["score"])[:5]:
            mark = "★" if sym in top_n else " "
            sc = scores[sym]
            print(f"    {mark} {sym:<6} score={sc['score']:>5.1f}  "
                  f"mom={sc['mom_12m']:>+6.1f}%  vol={sc['vol_6m']:>5.1f}%")

    print("\nCombined target allocations:")
    for sym, usd in sorted(target.items(), key=lambda x: -x[1]):
        print(f"  {sym:<6} ${usd:>10,.0f}  ({usd/equity*100:.1f}%)")

    # Build trade plan
    trades = build_trade_plan(target, positions)

    if not trades:
        print("\nNo rebalance needed — portfolio matches target.")
        return

    print(f"\nTrade plan ({len(trades)} orders):")
    executed = execute_trades(client, trades, dry_run=args.dry_run)

    if not args.dry_run and executed:
        log_run({
            "date":      date.today().isoformat(),
            "equity":    equity,
            "target":    target,
            "signals":   {k: {"top_n": v[0]} for k, v in signals.items()},
            "trades":    executed,
        })
        print(f"\n✓ Logged {len(executed)} trades to {LOG_FILE.name}")
    elif args.dry_run:
        print(f"\n[DRY RUN] {len(trades)} orders would be submitted.")


if __name__ == "__main__":
    main()
