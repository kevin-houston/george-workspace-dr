#!/usr/bin/env python3
"""
Paper Trading Monitor
Displays current Alpaca paper portfolio status, P&L, drift from target signal,
and upcoming rebalance preview.

Usage:
    python3 monitor.py           # full status + target vs current
    python3 monitor.py --brief   # just P&L summary
    python3 monitor.py --signal  # recompute current signal (slow, downloads data)
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

LOG_FILE = Path(__file__).parent / "h112_monthly_trades.json"

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
    "h026":  {"assets": H026_ASSETS,  "n_hold": 1, "weight": 0.27, "tsmom_filter": True},
    "h045":  {"assets": H045_ASSETS,  "n_hold": 2, "weight": 0.21, "tsmom_filter": False},
}
IBS_WEIGHTS = {"XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def get_client():
    return TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
        paper=True,
    )


def get_positions(client):
    return {
        p.symbol: {
            "qty":          float(p.qty),
            "market_value": float(p.market_value),
            "avg_cost":     float(p.avg_entry_price),
            "unrealized_pl":float(p.unrealized_pl),
            "unrealized_plpc": float(p.unrealized_plpc),
        }
        for p in client.get_all_positions()
    }


def get_account(client):
    acc = client.get_account()
    return {
        "equity":          float(acc.equity),
        "cash":            float(acc.cash),
        "buying_power":    float(acc.buying_power),
        "portfolio_value": float(acc.portfolio_value),
    }


def load_trade_log():
    if not LOG_FILE.exists():
        return []
    return json.loads(LOG_FILE.read_text())


def compute_signal(assets, n_hold, tsmom_filter=False):
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
    mom_6  = (monthly_px / monthly_px.shift(6)  - 1).iloc[-1].dropna()
    mom_3  = (monthly_px / monthly_px.shift(3)  - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)

    valid = mom_12.index.intersection(vol_6.index).intersection(
            mom_6.index).intersection(mom_3.index)

    if tsmom_filter:
        valid = valid[mom_12[valid] > 0]
        if len(valid) == 0:
            return [], {}

    if len(valid) < n_hold:
        if len(valid) == 0:
            return [], {}
        n_hold = len(valid)

    score = (mom_12[valid].rank() + mom_6[valid].rank() +
             mom_3[valid].rank() + vol_6[valid].rank(ascending=False))
    top_n = list(score.nlargest(n_hold).index)

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
    return top_n, scores


def pct_bar(pct, width=20):
    filled = int(abs(pct) / 100 * width)
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    sign = "+" if pct >= 0 else "-"
    return f"{sign}{bar}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--brief",  action="store_true", help="P&L summary only")
    parser.add_argument("--signal", action="store_true", help="Recompute current signal")
    args = parser.parse_args()

    client   = get_client()
    acc      = get_account(client)
    positions = get_positions(client)

    print(f"\n{'='*60}")
    print(f"  H120 Paper Portfolio Monitor — {date.today()}")
    print(f"{'='*60}")
    print(f"  Equity:        ${acc['equity']:>12,.2f}")
    print(f"  Cash:          ${acc['cash']:>12,.2f}")
    print(f"  Buying Power:  ${acc['buying_power']:>12,.2f}")

    # P&L summary from positions
    total_unreal = sum(p["unrealized_pl"] for p in positions.values())
    print(f"  Unrealized P&L:${total_unreal:>12,.2f}")

    # Inception P&L from trade log
    log = load_trade_log()
    if log:
        first_equity = log[0].get("equity", acc["equity"])
        inception_pl = acc["equity"] - first_equity
        inception_pct = (acc["equity"] / first_equity - 1) * 100
        first_date = log[0].get("date", "?")
        print(f"  Since {first_date}: ${inception_pl:>+,.2f} ({inception_pct:>+.2f}%)")

    if args.brief:
        return

    # Positions detail
    if positions:
        print(f"\n  {'Symbol':<8} {'Qty':>10} {'Mkt Val':>12} {'Unreal P&L':>12} {'%':>7}")
        print(f"  {'─'*8} {'─'*10} {'─'*12} {'─'*12} {'─'*7}")
        for sym, pos in sorted(positions.items(), key=lambda x: -x[1]["market_value"]):
            pl_pct = pos["unrealized_plpc"] * 100
            print(f"  {sym:<8} {pos['qty']:>10.4f} ${pos['market_value']:>11,.2f} "
                  f"${pos['unrealized_pl']:>+11,.2f} {pl_pct:>+6.1f}%")
    else:
        print("\n  No open positions.")

    # Target weights vs current
    target_weights = {}
    for strat, cfg in SUB_STRATS.items():
        w_per_slot = cfg["weight"] / cfg["n_hold"]
        # We don't know the last signal without recomputing, use log
        if log:
            last = log[-1]
            sigs = last.get("signals", {})
            if strat in sigs:
                for sym in sigs[strat].get("top_n", []):
                    target_weights[sym] = target_weights.get(sym, 0) + w_per_slot

    if target_weights:
        print(f"\n  Current target weights (from last rebalance {log[-1].get('date','?')}):")
        for sym, tw in sorted(target_weights.items(), key=lambda x: -x[1]):
            cur_w = positions.get(sym, {}).get("market_value", 0) / acc["equity"]
            drift = (cur_w - tw) * 100
            print(f"    {sym:<6} target={tw*100:.1f}%  actual={cur_w*100:.1f}%  "
                  f"drift={drift:>+.1f}pp")

    # Trade history
    if log:
        print(f"\n  Rebalance history ({len(log)} runs):")
        for entry in log[-5:]:  # last 5
            n_trades = len(entry.get("trades", []))
            eq = entry.get("equity", 0)
            print(f"    {entry['date']}  equity=${eq:,.0f}  {n_trades} trades")

    # Recompute signal if requested
    if args.signal:
        print(f"\n{'─'*60}")
        print("  Recomputing current signal (downloading data)…")
        for name, cfg in SUB_STRATS.items():
            top_n, scores = compute_signal(
                cfg["assets"], cfg["n_hold"],
                tsmom_filter=cfg.get("tsmom_filter", False)
            )
            alloc_per = acc["equity"] * cfg["weight"] / cfg["n_hold"]
            print(f"\n  {name.upper()} ({cfg['weight']*100:.0f}%): top-{cfg['n_hold']} → "
                  f"{', '.join(top_n) if top_n else 'CASH (TSMOM filter)'}")
            for sym in sorted(scores, key=lambda s: -scores[s]["score"])[:5]:
                mark = "★" if sym in top_n else " "
                sc = scores[sym]
                print(f"    {mark} {sym:<6} score={sc['score']:>5.1f}  "
                      f"m12={sc['mom_12m']:>+6.1f}%  m6={sc.get('mom_6m',0):>+6.1f}%  "
                      f"m3={sc.get('mom_3m',0):>+6.1f}%  vol={sc['vol_6m']:>5.1f}%")

    print()


if __name__ == "__main__":
    main()
