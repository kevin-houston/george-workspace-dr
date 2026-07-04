#!/usr/bin/env python3
"""
pead_gap_overnight.py — PEAD-GAP earnings universe scan (no NLP).

Run nightly at 11 PM CT. Finds tickers in universe with earnings today/yesterday
and saves them as candidates for the gap-first open pass tomorrow.
No FinBERT scoring — the only gate is: earnings today + gap-up ≥ 3% at open.
"""

import json
import warnings
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

PAPER_DIR      = Path(__file__).resolve().parent
WATCHLIST_PATH = PAPER_DIR / "pead_gap_watchlist.json"
LOG_PATH       = PAPER_DIR / "pead_gap_overnight.log"

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC","JNJ","PFE","MRK","XOM","CVX",
    "WMT","COST","HD","LOW","SBUX","V","MA",
    "UNH","ABBV","LLY","AVGO","AMD","QCOM","INTC","IBM",
    "MRVL","CRM","DELL",
]


def log(msg: str):
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def get_earnings_today(universe: list[str]) -> list[str]:
    today = date.today()
    reporting = []
    for ticker in universe:
        try:
            tk = yf.Ticker(ticker)
            df = tk.earnings_dates
            if df is None or df.empty:
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None)
            df = df.dropna(subset=["Reported EPS"])
            window = df[df.index >= pd.Timestamp(today - timedelta(days=2))]
            if not window.empty:
                reporting.append(ticker)
        except Exception:
            pass
    return reporting


def run():
    log("=" * 55)
    log("PEAD-GAP overnight pass starting")
    today = date.today().isoformat()

    log("Scanning earnings calendar…")
    candidates = get_earnings_today(UNIVERSE)
    log(f"  Tickers with recent earnings: {candidates or 'none'}")

    watchlist = {
        "date": today,
        "candidates": candidates,
        "source": "earnings_only",
        "strategy": "PEAD_GAP",
    }
    WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))

    if not candidates:
        log("No earnings tonight. Watchlist cleared.")
    else:
        log(f"Watchlist saved — {len(candidates)} candidate(s) for tomorrow's open.")
    log("Overnight pass complete.")


if __name__ == "__main__":
    run()
