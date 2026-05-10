#!/usr/bin/env python3
"""
pead_open.py — H174 PEAD-NLP gap detection and order submission.

Run at 9:30 AM CT (market open). Reads watchlist from pead_overnight.py,
detects gap-ups ≥ 3% in candidates, submits market buy orders, logs positions.
"""

import json
import os
import sys
import time
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

WORKSPACE      = Path(__file__).resolve().parent.parent.parent
PAPER_DIR      = WORKSPACE / "backtesting" / "paper_trading"
WATCHLIST_PATH = PAPER_DIR / "pead_watchlist.json"
POSITIONS_PATH = PAPER_DIR / "pead_positions.json"
LOG_PATH       = PAPER_DIR / "pead_open.log"

GAP_THRESH        = 0.03   # ≥ 3% gap qualifies
POSITION_SIZE_PCT = 0.05   # 5% of equity per position
STOP_LOSS_PCT     = 0.10   # 10% stop below entry
HOLD_DAYS         = 20


def log(msg: str):
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_watchlist() -> dict:
    if not WATCHLIST_PATH.exists():
        return {}
    return json.loads(WATCHLIST_PATH.read_text())


def load_positions() -> list:
    if not POSITIONS_PATH.exists():
        return []
    return json.loads(POSITIONS_PATH.read_text())


def save_positions(positions: list):
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2))


def _polygon_prev_close(ticker: str) -> float | None:
    """Backup: fetch prior close from Polygon API (via OneCLI proxy)."""
    try:
        import requests
        r = requests.get(
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev",
            timeout=10,
        )
        results = r.json().get("results", [])
        if results:
            return float(results[0]["c"])
    except Exception:
        pass
    return None


def get_prior_close(ticker: str) -> float | None:
    try:
        df = yf.download(ticker, period="5d", interval="1d", progress=False, auto_adjust=True)
        if len(df) >= 2:
            return float(df["Close"].iloc[-2])
    except Exception:
        pass
    log(f"  {ticker}: yfinance prior_close failed, trying Polygon backup")
    return _polygon_prev_close(ticker)


def get_current_price(ticker: str) -> float | None:
    try:
        tk = yf.Ticker(ticker)
        data = tk.fast_info
        return float(data.last_price)
    except Exception:
        return None


def get_exit_date(entry_date: str, hold_days: int = HOLD_DAYS) -> str:
    try:
        import pandas_market_calendars as mcal
        from datetime import timedelta
        nyse = mcal.get_calendar("NYSE")
        entry = pd.Timestamp(entry_date)
        schedule = nyse.schedule(start_date=entry, end_date=entry + pd.Timedelta(days=60))
        trading_days = schedule.index
        # Find entry day index
        entry_idx = None
        for i, d in enumerate(trading_days):
            if d.date() >= entry.date():
                entry_idx = i
                break
        if entry_idx is None:
            entry_idx = 0
        exit_idx = min(entry_idx + hold_days, len(trading_days) - 1)
        return trading_days[exit_idx].strftime("%Y-%m-%d")
    except Exception:
        # Fallback: ~28 calendar days ≈ 20 trading days
        return (pd.Timestamp(entry_date) + pd.Timedelta(days=28)).strftime("%Y-%m-%d")


def submit_order(ticker: str, notional: float, ref_price: float) -> dict | None:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        api_key = os.environ["ALPACA_API_KEY"]
        secret  = os.environ["ALPACA_SECRET"]
        client  = TradingClient(api_key, secret, paper=True)

        order_req = MarketOrderRequest(
            symbol=ticker,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )
        order = client.submit_order(order_req)
        log(f"  ORDER SUBMITTED: {ticker} notional=${notional:.0f} id={order.id}")
        return {"order_id": str(order.id), "ticker": ticker, "notional": notional, "ref_price": ref_price}
    except Exception as e:
        log(f"  ORDER FAILED: {ticker} — {e}")
        return None


def get_equity() -> float:
    try:
        from alpaca.trading.client import TradingClient
        api_key = os.environ["ALPACA_API_KEY"]
        secret  = os.environ["ALPACA_SECRET"]
        client  = TradingClient(api_key, secret, paper=True)
        return float(client.get_account().equity)
    except Exception:
        return 100_000.0  # fallback


def run():
    log("=" * 55)
    log("PEAD open pass starting")
    today = date.today().isoformat()

    watchlist = load_watchlist()
    if not watchlist or watchlist.get("date") != today:
        log("No watchlist for today or stale. Nothing to do.")
        return

    candidates = watchlist.get("candidates", [])
    if not candidates:
        log("Watchlist empty — no candidates passed overnight filters.")
        return

    log(f"Candidates from overnight: {candidates}")

    # Check existing positions to avoid doubling up
    existing = {p["ticker"] for p in load_positions()}

    equity = get_equity()
    log(f"Account equity: ${equity:,.0f}")

    new_positions = []
    for ticker in candidates:
        if ticker in existing:
            log(f"  {ticker}: already in positions, skipping")
            continue

        # Get prior close and check gap
        prior_close = get_prior_close(ticker)
        if prior_close is None:
            log(f"  {ticker}: could not get prior close")
            continue

        # Use current price as proxy for open (we're running at/just after open)
        current_price = get_current_price(ticker)
        if current_price is None:
            log(f"  {ticker}: could not get current price")
            continue

        gap_pct = (current_price - prior_close) / prior_close
        log(f"  {ticker}: prior_close={prior_close:.2f} current={current_price:.2f} gap={gap_pct*100:.1f}%")

        if gap_pct < GAP_THRESH:
            log(f"  {ticker}: gap {gap_pct*100:.1f}% < {GAP_THRESH*100:.0f}% threshold — skip")
            continue

        # Submit order
        notional = equity * POSITION_SIZE_PCT
        result = submit_order(ticker, notional, current_price)
        if result is None:
            continue

        exit_date = get_exit_date(today)
        position = {
            "ticker": ticker,
            "order_id": result["order_id"],
            "entry_date": today,
            "exit_date": exit_date,
            "notional": notional,
            "ref_price": current_price,
            "prior_close": prior_close,
            "gap_pct": round(gap_pct, 4),
            "stop_price": round(current_price * (1 - STOP_LOSS_PCT), 2),
            "hold_days": HOLD_DAYS,
            "score": watchlist["scores"].get(ticker, {}).get("score"),
            "surprise": watchlist["scores"].get(ticker, {}).get("surprise"),
        }
        new_positions.append(position)
        log(f"  {ticker}: position logged, exit={exit_date}")

    if new_positions:
        all_positions = load_positions() + new_positions
        save_positions(all_positions)
        log(f"Logged {len(new_positions)} new position(s). Total open: {len(all_positions)}")
    else:
        log("No new positions entered today.")

    log("Open pass complete.")


if __name__ == "__main__":
    run()
