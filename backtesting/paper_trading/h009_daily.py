#!/usr/bin/env python3
"""
H009 Daily IBS Mean-Reversion (SPY)

Each morning before the open:
  - If in position: check if yesterday's IBS > 0.8 OR held ≥ 5 days → SELL
  - If flat: check if yesterday's IBS < 0.2 → BUY

IBS (Internal Bar Strength) = (Close - Low) / (High - Low)
Low IBS = price closed near day's low = oversold → buy signal

Usage:
    python3 h009_daily.py              # live run (submits orders)
    python3 h009_daily.py --dry-run    # print signal, no submission
    python3 h009_daily.py --status     # show current position only

Schedule: run daily at 9:31 ET (1 minute after open).
"""

import argparse
import json
import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

SYMBOL      = "SPY"
BUY_THRESH  = 0.20   # IBS < 0.2 yesterday → buy today
SELL_THRESH = 0.80   # IBS > 0.8 today → sell today
MAX_HOLD    = 5      # max days held regardless of IBS

LOG_FILE = Path(__file__).parent / "h009_trades.json"


# ─────────────────────────────────────────────
# Signal
# ─────────────────────────────────────────────

def compute_ibs(df: pd.DataFrame) -> pd.Series:
    """IBS = (Close - Low) / (High - Low). 0 = closed at low, 1 = at high."""
    hl = df["High"] - df["Low"]
    ibs = (df["Close"] - df["Low"]) / hl
    return ibs.replace([float("inf"), float("-inf")], 0.5).fillna(0.5)


def get_spy_ohlc(days: int = 10) -> pd.DataFrame:
    raw = yf.download(SYMBOL, period=f"{days}d", auto_adjust=True, progress=False)
    raw.columns = raw.columns.get_level_values(0)   # flatten MultiIndex if present
    return raw[["Open", "High", "Low", "Close", "Volume"]]


# ─────────────────────────────────────────────
# Alpaca helpers
# ─────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_spy_position(client: TradingClient) -> dict | None:
    """Returns position dict or None if flat."""
    try:
        pos = client.get_open_position(SYMBOL)
        return {
            "qty":          float(pos.qty),
            "market_value": float(pos.market_value),
            "avg_cost":     float(pos.avg_entry_price),
            "unrealized_pl":float(pos.unrealized_pl),
        }
    except Exception:
        return None


def get_account_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


# ─────────────────────────────────────────────
# Position tracking (days held)
# ─────────────────────────────────────────────

def load_log() -> list:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return []


def save_log(log: list):
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


def get_days_held(log: list) -> int:
    """Count consecutive open days from the most recent BUY."""
    for entry in reversed(log):
        if entry.get("action") == "BUY":
            buy_date = date.fromisoformat(entry["date"])
            return (date.today() - buy_date).days
        if entry.get("action") == "SELL":
            return 0
    return 0


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="H009 daily IBS mean-reversion")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    args = parser.parse_args()

    client   = get_client()
    position = get_spy_position(client)
    equity   = get_account_equity(client)
    log      = load_log()
    today    = date.today()

    print(f"\nH009 Daily IBS — {today}")
    print(f"Account equity: ${equity:,.2f}")

    # Get OHLC
    ohlc = get_spy_ohlc(days=10)
    ibs  = compute_ibs(ohlc)

    yesterday_ibs = float(ibs.iloc[-2])   # yesterday's IBS (signal bar)
    today_ibs     = float(ibs.iloc[-1])   # today's IBS (exit check if in position)
    spy_close     = float(ohlc["Close"].iloc[-1])

    print(f"SPY: ${spy_close:.2f}  |  Yesterday IBS: {yesterday_ibs:.3f}  |  Today IBS: {today_ibs:.3f}")

    # Current position
    if position:
        days_held = get_days_held(log)
        print(f"\nPosition: LONG {position['qty']:.4f} SPY @ ${position['avg_cost']:.2f}  "
              f"(held ~{days_held}d, P&L ${position['unrealized_pl']:+,.2f})")
    else:
        print(f"\nPosition: FLAT")

    if args.status:
        return

    # ── Decision logic ──

    action = None
    reason = ""

    if position:
        # Check exit conditions (using today's IBS or days held)
        if today_ibs > SELL_THRESH:
            action = "SELL"
            reason = f"IBS exit: today IBS {today_ibs:.3f} > {SELL_THRESH}"
        elif get_days_held(log) >= MAX_HOLD:
            action = "SELL"
            reason = f"time exit: held {get_days_held(log)} days ≥ {MAX_HOLD}"
    else:
        # Check entry condition (using yesterday's IBS)
        if yesterday_ibs < BUY_THRESH:
            action = "BUY"
            reason = f"IBS entry: yesterday IBS {yesterday_ibs:.3f} < {BUY_THRESH}"

    if action is None:
        print(f"\nNo signal — holding current state.")
        print(f"  (buy trigger: yesterday IBS < {BUY_THRESH}, was {yesterday_ibs:.3f})")
        if position:
            print(f"  (sell trigger: today IBS > {SELL_THRESH} or {MAX_HOLD}d hold)")
        return

    # ── Size the order ──
    if action == "BUY":
        # Use 50% of account equity (H018: H009 gets half the capital)
        h009_capital = equity * 0.50
        qty = round(h009_capital / spy_close, 4)
        est_value = qty * spy_close
    else:
        qty       = position["qty"]
        est_value = position["market_value"]

    print(f"\nSignal: {action} {qty:.4f} SPY @ ~${spy_close:.2f}  (${est_value:,.0f})  — {reason}")

    if args.dry_run:
        print("[DRY RUN] Order not submitted.")
        return

    # ── Submit ──
    try:
        order = client.submit_order(MarketOrderRequest(
            symbol=SYMBOL,
            qty=qty,
            side=OrderSide.BUY if action == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        ))
        print(f"✓ Order submitted: {order.id}")
    except Exception as e:
        print(f"✗ Order failed: {e}")
        return

    # ── Log ──
    log.append({
        "date":          today.isoformat(),
        "action":        action,
        "symbol":        SYMBOL,
        "qty":           qty,
        "spy_price":     spy_close,
        "yesterday_ibs": round(yesterday_ibs, 4),
        "today_ibs":     round(today_ibs, 4),
        "reason":        reason,
        "order_id":      str(order.id),
        "submitted_at":  datetime.now().isoformat(),
        "equity":        equity,
    })
    save_log(log)
    print(f"✓ Logged to {LOG_FILE.name}")


if __name__ == "__main__":
    main()
