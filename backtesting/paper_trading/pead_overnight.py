#!/usr/bin/env python3
"""
pead_overnight.py — H174 PEAD-NLP overnight scoring pass.

Run nightly at 11 PM CT (after all 8-K filings typically submitted).
1. Find tickers with earnings today/yesterday in our universe
2. Fetch 8-K Item 2.02 filings from SEC EDGAR
3. Score with ProsusAI/finbert
4. Compute sentiment surprise vs prior 4 quarters
5. Save watchlist for pead_open.py tomorrow

Scheduled by NanoClaw — see paper-trading/pead-nlp-alpaca.md for architecture.
"""

import json
import os
import sys
import time
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

WORKSPACE      = Path(__file__).resolve().parent.parent.parent
CACHE_DIR      = WORKSPACE / "backtesting" / "cache"
PAPER_DIR      = WORKSPACE / "backtesting" / "paper_trading"
SCORE_CACHE    = CACHE_DIR / "h163_finbert_scores.parquet"
WATCHLIST_PATH = PAPER_DIR / "pead_watchlist.json"
LOG_PATH       = PAPER_DIR / "pead_overnight.log"

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC","JNJ","PFE","MRK","XOM","CVX",
    "WMT","COST","HD","LOW","SBUX","V","MA",
    "UNH","ABBV","LLY","AVGO","AMD","QCOM","INTC","IBM",
    "MRVL","CRM","DELL",
]

SCORE_THRESH   = 0.18
SURPRISE_THRESH = 0.02
EDGAR_HEADERS  = {"User-Agent": "george-nanoclaw george@nanoclaw.com"}


def log(msg: str):
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


# ── Earnings detection ────────────────────────────────────────────────────────

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


# ── EDGAR 8-K fetch ───────────────────────────────────────────────────────────

def fetch_8k_text(ticker: str) -> str | None:
    """Fetch the most recent 8-K Item 2.02 text from EDGAR for ticker."""
    try:
        import requests
        import edgar
        edgar.set_identity("george-nanoclaw george@nanoclaw.com")
        from edgar import Company
        # Look back 5 calendar days to catch Mon earnings reported by Wed night
        cutoff = (date.today() - timedelta(days=5)).isoformat()
        company = Company(ticker)
        filings = company.get_filings(form="8-K")
        latest = filings.latest()
        if str(latest.filing_date) < cutoff:
            return None
        eightk = latest.obj()
        if not eightk.items or "Item 2.02" not in eightk.items:
            return None
        text = latest.markdown()
        if text and len(text) > 200:
            return text
    except Exception as e:
        log(f"  {ticker}: EDGAR fetch error — {e}")
    return None


# ── FinBERT scoring ───────────────────────────────────────────────────────────

_tokenizer = None
_model = None

def _load_finbert():
    global _tokenizer, _model
    if _tokenizer is None:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        log("  Loading ProsusAI/finbert…")
        _tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        _model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        _model.eval()
    return _tokenizer, _model


def score_text(text: str) -> float:
    import torch
    tok, model = _load_finbert()
    inputs = tok(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0].numpy()
    return float(probs[0] - probs[1])  # positive - negative


def compute_surprise(ticker: str, current_score: float) -> float:
    if not SCORE_CACHE.exists():
        return float("nan")
    df = pd.read_parquet(SCORE_CACHE)
    df["date"] = pd.to_datetime(df["date"])
    prior = df[
        (df["ticker"] == ticker) &
        df["finbert_score"].notna()
    ].sort_values("date").tail(4)
    if len(prior) < 2:
        return float("nan")
    return current_score - prior["finbert_score"].mean()


# ── Main ──────────────────────────────────────────────────────────────────────

def run():
    log("=" * 55)
    log("PEAD overnight pass starting")
    # Save tomorrow's date — the open pass runs next morning and checks date == today
    tomorrow = (date.today() + timedelta(days=1)).isoformat()

    # 1. Earnings today
    log("Scanning earnings calendar…")
    reporting = get_earnings_today(UNIVERSE)
    log(f"  Tickers with recent earnings: {reporting or 'none'}")
    if not reporting:
        watchlist = {"date": tomorrow, "candidates": [], "scores": {}, "reason": "no earnings"}
        WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
        log("No earnings tonight. Watchlist cleared.")
        return

    # 2. Fetch 8-K texts
    texts = {}
    for ticker in reporting:
        log(f"  Fetching 8-K for {ticker}…")
        text = fetch_8k_text(ticker)
        if text:
            texts[ticker] = text
            log(f"    {ticker}: {len(text)} chars")
        else:
            log(f"    {ticker}: no 8-K Item 2.02 found")

    if not texts:
        log("No 8-K texts retrieved. Watchlist cleared.")
        watchlist = {"date": today, "candidates": [], "scores": {}, "reason": "no 8-K filings"}
        WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
        return

    # 3. Score with FinBERT
    scored = {}
    for ticker, text in texts.items():
        sc = score_text(text)
        surp = compute_surprise(ticker, sc)
        scored[ticker] = {"score": round(sc, 4), "surprise": round(surp, 4) if not np.isnan(surp) else None}
        log(f"  {ticker}: score={sc:.3f}  surprise={'nan' if np.isnan(surp) else f'{surp:.3f}'}")

    # 4. Filter candidates
    candidates = []
    for ticker, vals in scored.items():
        sc = vals["score"]
        surp = vals["surprise"]
        passes_score = sc >= SCORE_THRESH
        passes_surprise = surp is None or surp >= SURPRISE_THRESH
        if passes_score and passes_surprise:
            candidates.append(ticker)
            log(f"  ✓ {ticker} PASSES filters (score={sc:.3f}, surprise={surp})")
        else:
            log(f"  ✗ {ticker} filtered out (score={sc:.3f}, surprise={surp})")

    log(f"Candidates for tomorrow: {candidates or 'none'}")

    # 5. Save watchlist
    watchlist = {"date": tomorrow, "candidates": candidates, "scores": scored}
    WATCHLIST_PATH.write_text(json.dumps(watchlist, indent=2))
    log(f"Watchlist saved → {WATCHLIST_PATH}")
    log("Overnight pass complete.")


if __name__ == "__main__":
    run()
