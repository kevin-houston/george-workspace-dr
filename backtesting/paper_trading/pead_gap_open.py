#!/usr/bin/env python3
"""
pead_gap_open.py — PEAD-GAP gap-first open pass.

Run at 9:32 AM CT (market open + 2min). Reads earnings candidates from
pead_gap_watchlist.json and enters any that gap up >= 3% at the open.
No NLP pre-filter. Strategy: PEAD_GAP in strategy_accounts.json.
"""

import json
import os
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent))
import strategy_equity as se

PAPER_DIR      = Path(__file__).resolve().parent
WATCHLIST_PATH = PAPER_DIR / "pead_gap_watchlist.json"
POSITIONS_PATH = PAPER_DIR / "pead_gap_positions.json"
LOG_PATH       = PAPER_DIR / "pead_gap_open.log"

STRATEGY_ID       = "PEAD_GAP"
GAP_THRESH        = 0.03   # >= 3% gap-up required
POSITION_SIZE_PCT = 0.05   # 5% of strategy equity per position
STOP_LOSS_PCT     = 0.10   # 10% stop below entry (informational)
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
        return float(yf.Ticker(ticker).fast_info.last_price)
    except Exception:
        return None


def get_exit_date(entry_date: str, hold_days: int = HOLD_DAYS) -> str:
    try:
        import pandas_market_calendars as mcal
        nyse = mcal.get_calendar("NYSE")
        entry = pd.Timestamp(entry_date)
        schedule = nyse.schedule(start_date=entry, end_date=entry + pd.Timedelta(days=60))
        trading_days = schedule.index
        entry_idx = next((i for i, d in enumerate(trading_days) if d.date() >= entry.date()), 0)
        exit_idx = min(entry_idx + hold_days, len(trading_days) - 1)
        return trading_days[exit_idx].strftime("%Y-%m-%d")
    except Exception:
        return (pd.Timestamp(entry_date) + pd.Timedelta(days=28)).strftime("%Y-%m-%d")


def submit_order(ticker: str, notional: float, ref_price: float) -> dict | None:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = TradingClient(os.environ["ALPACA_API_KEY"],
                               os.environ["ALPACA_SECRET"], paper=True)
        order = client.submit_order(MarketOrderRequest(
            symbol=ticker,
            notional=round(notional, 2),
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        ))
        log(f"  ORDER SUBMITTED: {ticker} notional=${notional:.0f} id={order.id}")
        return {"order_id": str(order.id), "ticker": ticker,
                "notional": notional, "ref_price": ref_price}
    except Exception as e:
        log(f"  ORDER FAILED: {ticker} — {e}")
        return None


def run():
    log("=" * 55)
    log("PEAD-GAP open pass starting")
    today = date.today().isoformat()

    watchlist = load_watchlist()
    if not watchlist or watchlist.get("date") != today:
        log("No watchlist for today or stale. Nothing to do.")
        return

    candidates = watchlist.get("candidates", [])
    if not candidates:
        log("Watchlist empty — no earnings candidates today.")
        return

    log(f"Earnings candidates: {candidates}")

    existing = {p["ticker"] for p in load_positions()}
    strat_equity = se.current_equity(STRATEGY_ID)
    log(f"{STRATEGY_ID} strategy equity: ${strat_equity:,.0f}")

    new_positions = []
    for ticker in candidates:
        if ticker in existing:
            log(f"  {ticker}: already in positions, skipping")
            continue

        prior_close = get_prior_close(ticker)
        if prior_close is None:
            log(f"  {ticker}: could not get prior close")
            continue

        current_price = get_current_price(ticker)
        if current_price is None:
            log(f"  {ticker}: could not get current price")
            continue

        gap_pct = (current_price - prior_close) / prior_close
        log(f"  {ticker}: prior_close={prior_close:.2f} current={current_price:.2f} gap={gap_pct*100:.1f}%")

        if gap_pct < GAP_THRESH:
            log(f"  {ticker}: gap {gap_pct*100:.1f}% < {GAP_THRESH*100:.0f}% — skip")
            continue

        log(f"  ✓ {ticker}: gap {gap_pct*100:.1f}% >= {GAP_THRESH*100:.0f}% — entering")

        notional = strat_equity * POSITION_SIZE_PCT
        result = submit_order(ticker, notional, current_price)
        if result is None:
            continue

        qty_est = round(notional / current_price, 4) if current_price else 0
        se.open_buy(STRATEGY_ID, ticker, qty_est, current_price, order_id=result["order_id"])

        exit_date = get_exit_date(today)
        position = {
            "ticker": ticker,
            "strategy": STRATEGY_ID,
            "order_id": result["order_id"],
            "entry_date": today,
            "exit_date": exit_date,
            "notional": notional,
            "ref_price": current_price,
            "prior_close": prior_close,
            "gap_pct": round(gap_pct, 4),
            "stop_price": round(current_price * (1 - STOP_LOSS_PCT), 2),
            "hold_days": HOLD_DAYS,
        }
        new_positions.append(position)
        log(f"  {ticker}: position logged, exit={exit_date}")

    if new_positions:
        all_positions = load_positions() + new_positions
        save_positions(all_positions)
        log(f"Logged {len(new_positions)} new position(s). Total open: {len(all_positions)}")
    else:
        log("No new positions entered today.")

    open_pos = se.get_open_positions(STRATEGY_ID)
    cur_prices = {t: (get_current_price(t) or 0) for t in open_pos}
    se.snapshot_equity(STRATEGY_ID, {k: v for k, v in cur_prices.items() if v})
    log("Open pass complete.")


if __name__ == "__main__":
    run()
