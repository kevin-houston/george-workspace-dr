#!/usr/bin/env python3
"""
H020 Monthly ETF Rotation Rebalancer

Computes the H020 signal (top 2 of SPY/QQQ/TLT/GLD/IEF by momentum+carry),
diffs against current Alpaca paper holdings, and submits rebalance orders.

Usage:
    python3 h020_rebalancer.py            # live run (submits orders)
    python3 h020_rebalancer.py --dry-run  # print orders, no submission
    python3 h020_rebalancer.py --status   # show current positions only

Run on the first trading day of each month, ideally around 9:45 ET.
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

ASSETS   = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF = "SHY"
TOP_N    = 2

LOG_FILE = Path(__file__).parent / "h020_trades.json"


# ─────────────────────────────────────────────
# Signal
# ─────────────────────────────────────────────

def compute_signal() -> tuple[list[str], list[str], dict]:
    """
    Returns (top2_to_hold, rest_to_cash, scores_dict).
    Identical logic to h016_signal.py but for 5-asset universe.
    """
    tickers = ASSETS + [CASH_ETF]
    raw = yf.download(tickers, period="15mo", auto_adjust=True, progress=False)
    prices = raw["Close"] if "Close" in raw.columns else raw

    monthly    = prices[ASSETS].resample("ME").last()
    monthly_ret = prices[ASSETS].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1)

    mom_12 = (monthly / monthly.shift(12) - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)
    valid  = mom_12.index.intersection(vol_6.index)

    if len(valid) < TOP_N + 1:
        raise ValueError(f"Only {len(valid)} valid assets — need ≥{TOP_N + 1}")

    mom_rank = mom_12[valid].rank()
    inv_vol  = vol_6[valid].rank(ascending=False)
    combined = (mom_rank + inv_vol).sort_values(ascending=False)

    top2 = list(combined.nlargest(TOP_N).index)
    rest = [s for s in valid if s not in top2]

    scores = {
        t: {
            "score":   round(float(combined[t]), 2),
            "mom_12m": round(float(mom_12[t]) * 100, 1),
            "vol_6m":  round(float(vol_6[t]) * 100, 1),
        }
        for t in valid
    }
    return top2, rest, scores


# ─────────────────────────────────────────────
# Alpaca helpers
# ─────────────────────────────────────────────

def get_client() -> TradingClient:
    key    = os.environ["ALPACA_API_KEY"]
    secret = os.environ["ALPACA_SECRET"]
    return TradingClient(api_key=key, secret_key=secret, paper=True)


def get_current_holdings(client: TradingClient) -> dict[str, dict]:
    """Returns {symbol: {qty, market_value, avg_cost}} for all open positions."""
    positions = client.get_all_positions()
    return {
        p.symbol: {
            "qty":          float(p.qty),
            "market_value": float(p.market_value),
            "avg_cost":     float(p.avg_entry_price),
        }
        for p in positions
    }


def get_latest_price(symbol: str) -> float:
    raw = yf.download(symbol, period="3d", auto_adjust=True, progress=False)
    closes = raw["Close"] if "Close" in raw.columns else raw
    if isinstance(closes, pd.DataFrame):
        closes = closes[symbol]
    return float(closes.dropna().iloc[-1])


def get_account_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


# ─────────────────────────────────────────────
# Trade logic
# ─────────────────────────────────────────────

def build_trade_plan(
    top2: list[str],
    rest: list[str],
    holdings: dict[str, dict],
    equity: float,
) -> list[dict]:
    """
    Returns list of {symbol, action, qty, reason}.
    Allocation: top2 at 50% each (100% invested), no SHY.
    Matches the backtest paper-trade intent: "hold top 2 at 50/50".
    """
    # 50% each in the two winners; losing assets simply not held
    target = {s: equity * 0.5 for s in top2}

    trades = []

    # Sell anything not in target universe
    for sym, pos in holdings.items():
        if sym not in target:
            trades.append({
                "symbol": sym,
                "action": "SELL",
                "qty":    pos["qty"],
                "reason": f"not in target ({', '.join(top2)} + {CASH_ETF})",
                "est_value": pos["market_value"],
            })

    # Buy/adjust each target
    for sym, tgt_val in target.items():
        curr_val = holdings.get(sym, {}).get("market_value", 0.0)
        diff     = tgt_val - curr_val

        price = get_latest_price(sym)
        qty   = abs(diff) / price

        if diff > price * 0.5:      # need to buy ≥ 0.5 shares worth
            trades.append({
                "symbol":    sym,
                "action":    "BUY",
                "qty":       round(qty, 4),
                "reason":    f"target ${tgt_val:,.0f}, current ${curr_val:,.0f}",
                "est_value": diff,
            })
        elif diff < -price * 0.5:   # need to sell ≥ 0.5 shares worth
            trades.append({
                "symbol":    sym,
                "action":    "SELL",
                "qty":       round(qty, 4),
                "reason":    f"target ${tgt_val:,.0f}, current ${curr_val:,.0f}",
                "est_value": abs(diff),
            })
        # else: within rounding threshold, skip

    # Sort: SELLs first (frees cash), then BUYs
    sells = [t for t in trades if t["action"] == "SELL"]
    buys  = [t for t in trades if t["action"] == "BUY"]
    return sells + buys


def execute_trades(client: TradingClient, trades: list[dict], dry_run: bool):
    executed = []
    for t in trades:
        if dry_run:
            print(f"  [DRY RUN] {t['action']:4} {t['qty']:>8.4f} {t['symbol']:<6}  "
                  f"~${t['est_value']:>8,.0f}  ({t['reason']})")
            continue

        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=t["symbol"],
                qty=t["qty"],
                side=OrderSide.BUY if t["action"] == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            print(f"  ✓ {t['action']:4} {t['qty']:>8.4f} {t['symbol']:<6}  "
                  f"order_id={order.id}")
            executed.append({**t, "order_id": str(order.id), "submitted_at": datetime.now().isoformat()})
        except Exception as e:
            print(f"  ✗ {t['action']:4} {t['symbol']:<6}  ERROR: {e}")

    return executed


# ─────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────

def log_rebalance(entry: dict):
    log = []
    if LOG_FILE.exists():
        log = json.loads(LOG_FILE.read_text())
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="H020 monthly ETF rotation rebalancer")
    parser.add_argument("--dry-run", action="store_true", help="Print orders, don't submit")
    parser.add_argument("--status",  action="store_true", help="Show current positions only")
    args = parser.parse_args()

    client   = get_client()
    holdings = get_current_holdings(client)
    equity   = get_account_equity(client)

    print(f"\nH020 Rebalancer — {date.today()}")
    print(f"Account equity: ${equity:,.2f}")

    if args.status or holdings:
        print(f"\nCurrent positions:")
        if holdings:
            for sym, pos in holdings.items():
                print(f"  {sym:<6} {pos['qty']:>10.4f} shares  "
                      f"${pos['market_value']:>10,.2f}  (avg ${pos['avg_cost']:.2f})")
        else:
            print("  (none)")

    if args.status:
        return

    # Compute signal
    print("\nFetching signal data…")
    top2, rest, scores = compute_signal()

    print(f"\nH020 Signal:")
    print(f"  {'Ticker':<6} {'Score':>6} {'12m Mom':>8} {'6m Vol':>7} {'Action'}")
    print(f"  {'─'*45}")
    for t in sorted(ASSETS, key=lambda x: -scores.get(x, {}).get("score", 0)):
        if t not in scores:
            continue
        action = f"HOLD {100//TOP_N}%" if t in top2 else f"→ {CASH_ETF}"
        print(f"  {t:<6} {scores[t]['score']:>6.1f} {scores[t]['mom_12m']:>7.1f}% "
              f"{scores[t]['vol_6m']:>6.1f}%  {action}")

    target_str = " + ".join(top2)
    print(f"\n  → Hold: {target_str} ({100//TOP_N}% each)  |  {CASH_ETF}: {', '.join(rest)}")

    # Build trades
    trades = build_trade_plan(top2, rest, holdings, equity)

    if not trades:
        print("\nNo rebalance needed — portfolio already matches target.")
        return

    print(f"\nTrade plan ({len(trades)} orders):")
    for t in trades:
        if not args.dry_run:
            print(f"  {'→':2} {t['action']:4} {t['qty']:>8.4f} {t['symbol']:<6}  "
                  f"~${t['est_value']:>8,.0f}  ({t['reason']})")

    # Execute
    if args.dry_run:
        print(f"\nDry run — {len(trades)} orders would be submitted:")
        execute_trades(client, trades, dry_run=True)
    else:
        print(f"\nSubmitting {len(trades)} orders…")
        executed = execute_trades(client, trades, dry_run=False)
        log_rebalance({
            "date":      date.today().isoformat(),
            "month":     date.today().strftime("%Y-%m"),
            "signal":    {"top2": top2, "rest": rest, "scores": scores},
            "equity":    equity,
            "trades":    executed,
        })
        print(f"\n✓ Logged to {LOG_FILE.name}")


if __name__ == "__main__":
    main()
