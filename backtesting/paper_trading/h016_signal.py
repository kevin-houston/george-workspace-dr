#!/usr/bin/env python3
"""
H016 paper trading signal — Momentum+Carry Blend (SPY/TLT/GLD).

Computes current holdings, logs to trades.json, and prints status.
Run monthly (or on demand) to get the current allocation.

Strategy: Each month hold the top 2 of (SPY, TLT, GLD) by
  score = 12-month momentum rank + inverse 6-month vol rank
  Remainder goes to SHY (cash equivalent).
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ASSETS   = ["SPY", "TLT", "GLD"]
CASH_ETF = "SHY"
TRADES_FILE = Path(__file__).parent / "h016_positions.json"


def fetch(tickers: list[str], period: str = "15mo") -> pd.DataFrame:
    raw = yf.download(tickers, period=period, auto_adjust=True, progress=False)
    return raw["Close"] if "Close" in raw.columns else raw


def compute_signal(prices: pd.DataFrame) -> tuple[list[str], dict]:
    """Return (top2_holdings, scores_dict) based on latest month-end data."""
    monthly = prices[ASSETS].resample("ME").last()
    monthly_ret = monthly.pct_change()

    mom_12 = (monthly / monthly.shift(12) - 1).iloc[-1].dropna()
    vol_6  = monthly_ret.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)

    if len(mom_12) < 3 or len(vol_6) < 3:
        raise ValueError("Not enough data to compute signal")

    mom_rank    = mom_12.rank()
    inv_vol_rank = vol_6.rank(ascending=False)
    combined    = (mom_rank + inv_vol_rank).sort_values(ascending=False)

    top2 = list(combined.nlargest(2).index)
    scores = {
        ticker: {
            "score":    round(float(combined[ticker]), 2),
            "mom_12m":  round(float(mom_12[ticker]) * 100, 1),
            "vol_6m":   round(float(vol_6[ticker]) * 100, 1),
        }
        for ticker in ASSETS
    }
    return top2, scores


def current_prices(tickers: list[str]) -> dict[str, float]:
    raw = yf.download(tickers, period="5d", auto_adjust=True, progress=False)
    closes = raw["Close"] if "Close" in raw.columns else raw
    return {t: round(float(closes[t].dropna().iloc[-1]), 2) for t in tickers}


def load_positions() -> list:
    if TRADES_FILE.exists():
        return json.loads(TRADES_FILE.read_text())
    return []


def save_positions(positions: list):
    TRADES_FILE.write_text(json.dumps(positions, indent=2, default=str))


def main():
    print("Fetching data...")
    all_tickers = ASSETS + [CASH_ETF]
    prices = fetch(all_tickers)

    top2, scores = compute_signal(prices)
    cash_holds = [s for s in ASSETS if s not in top2]
    holdings = {t: 0.5 for t in top2}  # equal weight among top 2

    px = current_prices(all_tickers)

    print(f"\nH016 Signal — {date.today()}")
    print(f"{'Ticker':<8} {'Score':>7} {'12m Mom':>9} {'6m Vol':>8} {'Action'}")
    print("─" * 52)
    for ticker in sorted(ASSETS, key=lambda t: -scores[t]["score"]):
        action = "HOLD 50%" if ticker in top2 else f"→ {CASH_ETF}"
        print(f"{ticker:<8} {scores[ticker]['score']:>7.1f} "
              f"{scores[ticker]['mom_12m']:>8.1f}% "
              f"{scores[ticker]['vol_6m']:>7.1f}%  {action}")
    print(f"\nHold: {' + '.join(top2)} (50% each)  |  {CASH_ETF}: {', '.join(cash_holds) if cash_holds else 'none'}")

    # Log position
    positions = load_positions()
    today_str = date.today().isoformat()

    # Check if we already have an entry for this month
    this_month = today_str[:7]
    existing = [p for p in positions if p.get("month") == this_month]

    if existing:
        print(f"\nPosition for {this_month} already logged: {existing[0]['holdings']}")
        if existing[0]["holdings"] == top2:
            print("No change in allocation.")
            return
        print("Allocation changed — updating.")
        positions = [p for p in positions if p.get("month") != this_month]

    entry = {
        "month": this_month,
        "date": today_str,
        "holdings": top2,
        "cash_allocation": cash_holds,
        "scores": scores,
        "entry_prices": {t: px.get(t) for t in all_tickers},
        "status": "open",
        "pnl_pct": None,
    }
    positions.append(entry)
    save_positions(positions)
    print(f"\n✓ Position logged for {this_month}: {top2[0]} + {top2[1]} (50/50)")


if __name__ == "__main__":
    main()
