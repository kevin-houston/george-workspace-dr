#!/usr/bin/env python3
"""
pead_gap_exits.py — PEAD-GAP position exit manager.

Run at 2:46 PM CT (before MOC cutoff). Closes positions that have reached
their 20-trading-day hold period. Mirror of pead_exits.py for PEAD_GAP strategy.
"""

import json
import os
import sys
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent))
import strategy_equity as se

warnings.filterwarnings("ignore")

PAPER_DIR      = Path(__file__).resolve().parent
POSITIONS_PATH = PAPER_DIR / "pead_gap_positions.json"
CLOSED_PATH    = PAPER_DIR / "pead_gap_closed.json"
LOG_PATH       = PAPER_DIR / "pead_gap_exits.log"

STRATEGY_ID = "PEAD_GAP"


def log(msg: str):
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def load_positions() -> list:
    if not POSITIONS_PATH.exists():
        return []
    return json.loads(POSITIONS_PATH.read_text())


def save_positions(positions: list):
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2))


def load_closed() -> list:
    if not CLOSED_PATH.exists():
        return []
    return json.loads(CLOSED_PATH.read_text())


def save_closed(closed: list):
    CLOSED_PATH.write_text(json.dumps(closed, indent=2))


def get_current_price(ticker: str) -> float | None:
    try:
        return float(yf.Ticker(ticker).fast_info.last_price)
    except Exception:
        return None


def get_alpaca_position(ticker: str):
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.environ["ALPACA_API_KEY"],
                               os.environ["ALPACA_SECRET"], paper=True)
        return client.get_open_position(ticker)
    except Exception:
        return None


def submit_moc_exit(ticker: str, qty: float) -> str | None:
    try:
        from alpaca.trading.client import TradingClient
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        client = TradingClient(os.environ["ALPACA_API_KEY"],
                               os.environ["ALPACA_SECRET"], paper=True)
        order = client.submit_order(MarketOrderRequest(
            symbol=ticker,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.CLS,  # Market-on-Close
        ))
        log(f"  MOC EXIT SUBMITTED: {ticker} qty={qty:.4f} id={order.id}")
        return str(order.id)
    except Exception as e:
        log(f"  MOC EXIT FAILED: {ticker} — {e}")
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.trading.requests import MarketOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            client = TradingClient(os.environ["ALPACA_API_KEY"],
                                   os.environ["ALPACA_SECRET"], paper=True)
            order = client.submit_order(MarketOrderRequest(
                symbol=ticker, qty=qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            log(f"  FALLBACK MARKET EXIT: {ticker} qty={qty:.4f} id={order.id}")
            return str(order.id)
        except Exception as e2:
            log(f"  FALLBACK FAILED: {ticker} — {e2}")
            return None


def record_pnl(position: dict, exit_price: float | None, exit_order_id: str | None):
    records = load_closed()
    entry_price = position.get("ref_price", 0)
    pnl_pct = (exit_price - entry_price) / entry_price if exit_price and entry_price else None
    records.append({
        **position,
        "exit_date_actual": date.today().isoformat(),
        "exit_price": exit_price,
        "exit_order_id": exit_order_id,
        "pnl_pct": round(pnl_pct, 4) if pnl_pct is not None else None,
    })
    save_closed(records)
    if pnl_pct is not None:
        log(f"  P&L record: {position['ticker']} entry={entry_price:.2f} "
            f"exit={exit_price:.2f} pnl={pnl_pct*100:.1f}%")
    else:
        log(f"  P&L record: {position['ticker']} exit price unknown")


def run():
    log("=" * 55)
    log("PEAD-GAP exits pass starting")
    today = date.today().isoformat()

    positions = load_positions()
    if not positions:
        log("No open PEAD-GAP positions.")
        return

    log(f"Open positions: {[p['ticker'] for p in positions]}")

    remaining = []
    for pos in positions:
        exit_date = pos.get("exit_date")
        ticker = pos["ticker"]

        if not exit_date or exit_date > today:
            remaining.append(pos)
            log(f"  {ticker}: exit_date={exit_date}, holding")
            continue

        log(f"  {ticker}: exit_date={exit_date} reached — submitting MOC exit")

        alpaca_pos = get_alpaca_position(ticker)
        if alpaca_pos:
            qty = float(alpaca_pos.qty)
            current_price = float(alpaca_pos.current_price)
        else:
            log(f"  {ticker}: not found in Alpaca — may have been closed already")
            current_price = get_current_price(ticker)
            record_pnl(pos, current_price, None)
            continue

        exit_order_id = submit_moc_exit(ticker, qty)
        record_pnl(pos, current_price, exit_order_id)
        se.close_sell(STRATEGY_ID, ticker, current_price, order_id=exit_order_id or "")

    save_positions(remaining)
    exited = len(positions) - len(remaining)
    log(f"Exits submitted: {exited}. Remaining open: {len(remaining)}")

    remaining_tickers = {p["ticker"] for p in remaining}
    cur_prices = {t: (get_current_price(t) or 0) for t in remaining_tickers}
    se.snapshot_equity(STRATEGY_ID, {k: v for k, v in cur_prices.items() if v})
    log("Exits pass complete.")


if __name__ == "__main__":
    run()
