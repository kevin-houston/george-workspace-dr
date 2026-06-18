#!/usr/bin/env python3
"""
H041a Monthly Rotation — Global Equity Top-1
19-asset global equity ETF universe. TSMOM 3m > +0.5% filter.
Vol-target 20% annualized. $5k virtual account tracked in strategy_equity.

Run first trading day of each month at 9:45 AM CT.
Usage:
    python3 h041a_monthly.py            # live run
    python3 h041a_monthly.py --dry-run  # print orders, no submission
    python3 h041a_monthly.py --status   # show positions only
    python3 h041a_monthly.py --force    # skip first-of-month guard
"""

import argparse
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import strategy_equity as se

STRATEGY_ID = "H041a"

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig_send = _ra.HTTPAdapter.send
def _no_verify_send(self, request, **kwargs):
    kwargs['verify'] = False
    return _orig_send(self, request, **kwargs)
_ra.HTTPAdapter.send = _no_verify_send

import numpy as np
import pandas as pd
import yfinance as yf
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

ASSETS = [
    "SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL",
    "EWJ", "EWH", "EWT", "EWY", "EWS", "EPHE", "EWG", "EWQ", "EWU", "EWD", "EWN",
]
TSMOM_LB        = 3      # 3-month lookback for TSMOM filter
TSMOM_THRESHOLD = 0.005  # > +0.5%
VOL_TARGET      = 0.20   # 20% annualized
VOL_WINDOW      = 6      # months of history for realized vol
VOL_CLAMP       = (0.5, 2.0)
MIN_ORDER_USD   = 5.0

LOG_FILE = Path(__file__).parent / "h041a_monthly_trades.json"


# ── Signal ──────────────────────────────────────────────────────────────────

def compute_top1() -> tuple[str | None, dict]:
    """Return (top_ticker, scores_dict). Returns (None, {}) if TSMOM filter blocks all."""
    raw = yf.download(ASSETS, period="15mo", auto_adjust=True, progress=False)
    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    prices = prices[ASSETS].dropna(how="all", axis=1)

    monthly_px  = prices.resample("ME").last()
    monthly_ret = prices.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    mom_12 = (monthly_px / monthly_px.shift(12) - 1).iloc[-1].dropna()
    mom_6  = (monthly_px / monthly_px.shift(6)  - 1).iloc[-1].dropna()
    mom_3  = (monthly_px / monthly_px.shift(3)  - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)

    valid = mom_12.index.intersection(vol_6.index).intersection(
            mom_6.index).intersection(mom_3.index)
    valid = valid[mom_3[valid] > TSMOM_THRESHOLD]

    if len(valid) == 0:
        print("  H041a: TSMOM 3m filter — no qualifying assets, holding cash (BIL)")
        return None, {}

    score = (mom_12[valid].rank() + mom_6[valid].rank() +
             mom_3[valid].rank() + vol_6[valid].rank(ascending=False))
    top1  = score.nlargest(1).index[0]

    scores = {
        t: {
            "score":   round(float(score[t]), 2),
            "mom_12m": round(float(mom_12[t]) * 100, 1),
            "mom_6m":  round(float(mom_6[t])  * 100, 1),
            "mom_3m":  round(float(mom_3[t])  * 100, 1),
            "vol_6m":  round(float(vol_6.get(t, float("nan"))) * 100, 1),
        }
        for t in valid
    }
    return top1, scores


def compute_vol_scale() -> float:
    """Scale allocation by (VOL_TARGET / realized_6m_vol). Returns 1.0 if < 3 months history."""
    log = load_log()
    if len(log) < 3:
        return 1.0

    entries = [{"date": e["date"], "sym": e.get("top1")} for e in log]
    n = min(len(entries) - 1, VOL_WINDOW)
    recent = entries[-(n + 1):]

    monthly_rets = []
    for i in range(len(recent) - 1):
        sym = recent[i]["sym"]
        if not sym:
            monthly_rets.append(0.0)
            continue
        try:
            raw = yf.download(sym, start=recent[i]["date"], end=recent[i + 1]["date"],
                              auto_adjust=True, progress=False)
            closes = raw["Close"].dropna()
            if isinstance(closes, pd.DataFrame):
                closes = closes[sym]
            monthly_rets.append(float(closes.iloc[-1] / closes.iloc[0] - 1) if len(closes) >= 2 else 0.0)
        except Exception:
            monthly_rets.append(0.0)

    if len(monthly_rets) < 3:
        return 1.0
    rv = float(pd.Series(monthly_rets).std(ddof=1)) * np.sqrt(12)
    return float(np.clip(VOL_TARGET / rv, *VOL_CLAMP)) if rv > 0 else 1.0


# ── Alpaca ───────────────────────────────────────────────────────────────────

def get_client() -> TradingClient:
    return TradingClient(api_key=os.environ["ALPACA_API_KEY"],
                         secret_key=os.environ["ALPACA_SECRET"], paper=True)


def get_latest_price(symbol: str) -> float:
    raw = yf.download(symbol, period="3d", auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    if isinstance(closes, pd.DataFrame):
        closes = closes[symbol]
    return float(closes.dropna().iloc[-1])


def get_alpaca_position(client: TradingClient, symbol: str) -> dict | None:
    try:
        p = client.get_open_position(symbol)
        return {"qty": float(p.qty), "market_value": float(p.market_value)}
    except Exception:
        return None


# ── Log ──────────────────────────────────────────────────────────────────────

def load_log() -> list:
    return json.loads(LOG_FILE.read_text()) if LOG_FILE.exists() else []


def append_log(entry: dict):
    log = load_log()
    log.append(entry)
    LOG_FILE.write_text(json.dumps(log, indent=2, default=str))


# ── First trading day guard ───────────────────────────────────────────────────

def is_first_trading_day() -> bool:
    today = date.today()
    if today.weekday() >= 5:
        return False
    if today.day > 4:
        return False
    for d in range(1, today.day):
        if date(today.year, today.month, d).weekday() < 5:
            return False
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--status",  action="store_true")
    parser.add_argument("--force",   action="store_true")
    args = parser.parse_args()

    if not args.force and not args.status and not is_first_trading_day():
        print(f"Not the first trading day ({date.today()}). Use --force to override.")
        sys.exit(0)

    client       = get_client()
    strat_equity = se.current_equity(STRATEGY_ID)
    open_pos     = se.get_open_positions(STRATEGY_ID)

    print(f"\nH041a Monthly Rotation — {date.today()}")
    print(f"H041a strategy equity: ${strat_equity:,.2f}  cash: ${se.get_cash(STRATEGY_ID):,.2f}")

    current_sym = next(iter(open_pos), None)
    if current_sym:
        price_now = get_latest_price(current_sym)
        mkt_val   = open_pos[current_sym]["qty"] * price_now
        entry     = open_pos[current_sym]["entry_price"]
        print(f"Current holding: {current_sym}  entry=${entry:.2f}  now=${price_now:.2f}  "
              f"mkt=${mkt_val:,.0f}  P&L={((price_now/entry)-1)*100:+.1f}%")
    else:
        print("Current holding: CASH")

    if args.status:
        return

    vol_scale = compute_vol_scale()
    log = load_log()
    if len(log) < 3:
        print(f"Vol-scale: 1.000 (only {len(log)} month(s) of history)")
    else:
        print(f"Vol-scale: {vol_scale:.3f}")

    print("\nFetching signals…")
    top1, scores = compute_top1()
    target_sym = top1  # None → cash / BIL

    print(f"\nTop-1 signal: {target_sym or 'CASH (BIL)'}")
    for sym in sorted(scores, key=lambda s: -scores[s]["score"])[:5]:
        sc = scores[sym]
        mark = "★" if sym == target_sym else " "
        print(f"  {mark} {sym:<6} score={sc['score']:>5.1f}  "
              f"m3={sc['mom_3m']:>+6.1f}%  m6={sc['mom_6m']:>+6.1f}%  "
              f"m12={sc['mom_12m']:>+6.1f}%  vol={sc['vol_6m']:>5.1f}%")

    # Determine allocation
    alloc = strat_equity * vol_scale
    if vol_scale != 1.0:
        print(f"Effective allocation: ${alloc:,.0f}  ({vol_scale:.2f}x vol-scaled from ${strat_equity:,.0f})")

    trades_executed = []

    # Exit current position if it's not the target
    if current_sym and current_sym != target_sym:
        alpaca_pos = get_alpaca_position(client, current_sym)
        if alpaca_pos:
            qty  = alpaca_pos["qty"]
            price = get_latest_price(current_sym)
            print(f"\n  SELL {qty:.4f} {current_sym} @ ~${price:.2f}")
            if not args.dry_run:
                try:
                    order = client.submit_order(MarketOrderRequest(
                        symbol=current_sym, qty=qty,
                        side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                    ))
                    oid = str(order.id)
                    print(f"    ✓ order_id={oid}")
                    trade = se.close_sell(STRATEGY_ID, current_sym, price, order_id=oid)
                    if trade:
                        print(f"    P&L: ${trade['pnl']:+.2f} ({trade['return']*100:+.2f}%)")
                    trades_executed.append({"action": "SELL", "symbol": current_sym, "qty": qty, "price": price, "order_id": oid})
                except Exception as e:
                    print(f"    ✗ {e}")
            else:
                print(f"    [DRY RUN]")
        else:
            print(f"\n  {current_sym} not in Alpaca — clearing SE position")
            if not args.dry_run:
                se.close_sell(STRATEGY_ID, current_sym, get_latest_price(current_sym))

    # Enter new position if target changed (or cash-out)
    if target_sym and target_sym != current_sym:
        price = get_latest_price(target_sym)
        qty   = round(alloc / price, 4)
        print(f"\n  BUY {qty:.4f} {target_sym} @ ~${price:.2f}  (${alloc:,.0f})")
        if not args.dry_run:
            try:
                order = client.submit_order(MarketOrderRequest(
                    symbol=target_sym, qty=qty,
                    side=OrderSide.BUY, time_in_force=TimeInForce.DAY,
                ))
                oid = str(order.id)
                print(f"    ✓ order_id={oid}")
                se.open_buy(STRATEGY_ID, target_sym, qty, price, order_id=oid)
                trades_executed.append({"action": "BUY", "symbol": target_sym, "qty": qty, "price": price, "order_id": oid})
            except Exception as e:
                print(f"    ✗ {e}")
        else:
            print(f"    [DRY RUN]")
    elif target_sym == current_sym:
        print(f"\nNo rotation needed — {current_sym} remains top-1.")

    if not args.dry_run:
        held = target_sym or "CASH"
        open_now = se.get_open_positions(STRATEGY_ID)
        cur_prices = {s: get_latest_price(s) for s in open_now}
        eq = se.snapshot_equity(STRATEGY_ID, cur_prices)
        print(f"\nH041a equity snapshot: ${eq:,.2f}")
        if trades_executed:
            append_log({
                "date": date.today().isoformat(), "top1": held,
                "equity": strat_equity, "vol_scale": round(vol_scale, 4),
                "trades": trades_executed,
            })


if __name__ == "__main__":
    main()
