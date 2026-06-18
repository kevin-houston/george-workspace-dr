#!/usr/bin/env python3
"""
H112 Daily IBS Mean-Reversion Executor
XLK/SMH/IGV — sized from IBS strategy $5k virtual account.
Weights within IBS strategy (matching original 20/8/2 ratios):
  XLK 66.7%, SMH 26.7%, IGV 6.7% of IBS strategy equity.

Entry: yesterday IBS < buy_thresh AND today gap >= gap_min
Exit:  yesterday IBS > sell_thresh OR days_held >= max_hold

Run every trading day at 9:45 AM CT (10:45 AM ET), after the open is established.

Usage:
    python3 h112_daily_ibs.py            # live run
    python3 h112_daily_ibs.py --dry-run  # print signals, no orders
    python3 h112_daily_ibs.py --status   # show positions only
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import strategy_equity as se

STRATEGY_ID = "IBS"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig_send = _ra.HTTPAdapter.send
def _no_verify_send(self, request, **kwargs):
    kwargs['verify'] = False
    return _orig_send(self, request, **kwargs)
_ra.HTTPAdapter.send = _no_verify_send

import pandas as pd
import yfinance as yf

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# ── IBS parameters (confirmed H112) ────────────────────────────────────────
# Weights within the IBS strategy bucket (proportional to original 20/8/2).
_IBS_TOTAL_WEIGHT = 20 + 8 + 2
IBS_CONFIGS = {
    "XLK": {"weight": 20 / _IBS_TOTAL_WEIGHT, "buy": 0.15, "sell": 0.90, "max_hold": 7,  "gap_min": -0.010},
    "SMH": {"weight":  8 / _IBS_TOTAL_WEIGHT, "buy": 0.20, "sell": 0.75, "max_hold": 6,  "gap_min": -0.005},
    "IGV": {"weight":  2 / _IBS_TOTAL_WEIGHT, "buy": 0.30, "sell": 0.75, "max_hold": 5,  "gap_min":  0.0025},
}

MIN_ORDER_USD = 1.0


# ── Data helpers ────────────────────────────────────────────────────────────

def fetch_ohlc(symbol: str, days: int = 10) -> pd.DataFrame:
    raw = yf.download(symbol, period=f"{days}d", auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(symbol, axis=1, level=1)
    else:
        df = raw
    df.columns = [c.lower() for c in df.columns]
    return df[["open", "high", "low", "close"]]


def compute_ibs(df: pd.DataFrame) -> pd.Series:
    hl = (df["high"] - df["low"]).replace(0, float("nan"))
    return ((df["close"] - df["low"]) / hl).clip(0.0, 1.0).fillna(0.5)


# ── Alpaca helpers ──────────────────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_position(client: TradingClient, symbol: str) -> dict | None:
    try:
        p = client.get_open_position(symbol)
        return {
            "qty":           float(p.qty),
            "market_value":  float(p.market_value),
            "avg_cost":      float(p.avg_entry_price),
            "unrealized_pl": float(p.unrealized_pl),
        }
    except Exception:
        return None


def get_equity(client: TradingClient) -> float:
    return float(client.get_account().equity)


# ── State tracking ──────────────────────────────────────────────────────────

def load_log() -> list:
    return json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []


def save_log(log: list):
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


def days_held_for(symbol: str) -> int:
    pos = se.get_open_positions(STRATEGY_ID).get(symbol)
    if not pos:
        return 0
    return (date.today() - date.fromisoformat(pos["entry_date"])).days


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    args = parser.parse_args()

    client = get_client()
    today  = date.today()

    # Strategy equity from virtual account (not Alpaca account total)
    strat_equity = se.current_equity(STRATEGY_ID)

    print(f"\nH112 Daily IBS — {today}")
    print(f"IBS strategy equity: ${strat_equity:,.2f}  (cash: ${se.get_cash(STRATEGY_ID):,.2f})")

    orders_placed = 0

    for symbol, cfg in IBS_CONFIGS.items():
        position = get_position(client, symbol)
        held     = days_held_for(symbol)

        # Fetch OHLC (need yesterday complete + today's open)
        try:
            df = fetch_ohlc(symbol, days=10)
        except Exception as e:
            print(f"\n  {symbol}: data fetch failed — {e}")
            continue

        if len(df) < 2:
            print(f"\n  {symbol}: insufficient data rows")
            continue

        ibs_series = compute_ibs(df)
        prev_ibs   = float(ibs_series.iloc[-2])   # yesterday's confirmed IBS

        # Gap = today's open vs yesterday's close
        today_open  = float(df["open"].iloc[-1])
        prev_close  = float(df["close"].iloc[-2])
        gap         = (today_open - prev_close) / prev_close if prev_close > 0 else 0.0

        alloc_usd = strat_equity * cfg["weight"]

        print(f"\n  {symbol}  IBS_prev={prev_ibs:.3f}  gap={gap:+.3%}  "
              f"alloc=${alloc_usd:,.0f}", end="")
        if position:
            print(f"  |  LONG {position['qty']:.4f}sh @ ${position['avg_cost']:.2f}  "
                  f"held={held}d  P&L={position['unrealized_pl']:+,.0f}")
        else:
            print("  |  FLAT")

        if args.status:
            continue

        action = None
        reason = ""

        if position:
            if prev_ibs > cfg["sell"]:
                action = "SELL"
                reason = f"IBS exit: prev_ibs {prev_ibs:.3f} > {cfg['sell']}"
            elif held >= cfg["max_hold"]:
                action = "SELL"
                reason = f"time exit: held {held}d ≥ {cfg['max_hold']}"
        else:
            if prev_ibs < cfg["buy"] and gap >= cfg["gap_min"]:
                action = "BUY"
                reason = f"IBS entry: prev_ibs {prev_ibs:.3f} < {cfg['buy']}, gap {gap:+.3%} ≥ {cfg['gap_min']:.3%}"

        if action is None:
            print(f"    → no signal")
            if position:
                print(f"       (sell triggers: IBS>{cfg['sell']} or {cfg['max_hold']}d hold)")
            else:
                print(f"       (buy triggers: IBS<{cfg['buy']} AND gap≥{cfg['gap_min']:.3%})")
            continue

        price = today_open
        if action == "BUY":
            qty = round(alloc_usd / price, 4)
            est_val = qty * price
        else:
            qty     = position["qty"]
            est_val = position["market_value"]

        if est_val < MIN_ORDER_USD:
            print(f"    → {action} too small (${est_val:.2f}), skipping")
            continue

        print(f"    → {action} {qty:.4f} {symbol} @ ~${price:.2f}  (${est_val:,.0f})  — {reason}")

        if args.dry_run:
            print(f"    [DRY RUN] order not submitted")
            continue

        try:
            order = client.submit_order(MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.BUY if action == "BUY" else OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            ))
            oid = str(order.id)
            print(f"    ✓ order_id={oid}")
            if action == "BUY":
                se.open_buy(STRATEGY_ID, symbol, qty, price, order_id=oid, note=reason)
            else:
                trade = se.close_sell(STRATEGY_ID, symbol, price, order_id=oid, reason=reason)
                if trade:
                    print(f"    P&L: ${trade['pnl']:+.2f} ({trade['return']*100:+.2f}%)")
            orders_placed += 1
        except Exception as e:
            print(f"    ✗ order failed: {e}")

    if not args.dry_run and not args.status:
        # Snapshot equity with current prices
        current_prices = {s: float(fetch_ohlc(s, days=2)["close"].iloc[-1]) for s in IBS_CONFIGS}
        eq = se.snapshot_equity(STRATEGY_ID, current_prices)
        print(f"\nIBS equity snapshot: ${eq:,.2f}")
        if orders_placed == 0:
            print("No IBS signals today.")


if __name__ == "__main__":
    main()
