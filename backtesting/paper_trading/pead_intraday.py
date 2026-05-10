#!/usr/bin/env python3
"""
pead_intraday.py — H174 PEAD-NLP intraday scoring and order submission.

Called by the scheduled intraday scanner task when new 8-K Item 2.02
filings appear for universe tickers during market hours. Receives a list
of tickers via the PEAD_INTRADAY_TICKERS env var (JSON array).

Key difference from overnight pass:
- No gap check (price has already moved intraday)
- Requires stock up > 0% on the day (momentum confirmation)
- Writes positions to shared pead_positions.json so exits pass handles them
"""

import json
import os
import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

WORKSPACE        = Path(__file__).resolve().parent.parent.parent
PAPER_DIR        = WORKSPACE / "backtesting" / "paper_trading"
CACHE_DIR        = WORKSPACE / "backtesting" / "cache"
SCORE_CACHE      = CACHE_DIR / "h163_finbert_scores.parquet"
POSITIONS_PATH   = PAPER_DIR / "pead_positions.json"
INTRADAY_LOG     = PAPER_DIR / "pead_intraday.log"

SCORE_THRESH     = 0.18
SURPRISE_THRESH  = 0.02
POSITION_SIZE_PCT = 0.05
HOLD_DAYS        = 20
EDGAR_HEADERS    = {"User-Agent": "george-nanoclaw george@nanoclaw.com"}


def log(msg: str):
    ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(INTRADAY_LOG, "a") as f:
        f.write(line + "\n")


# ── Reuse overnight pass functions ────────────────────────────────────────────

def fetch_8k_text(ticker: str) -> str | None:
    try:
        import requests
        import edgar
        edgar.set_identity("george-nanoclaw george@nanoclaw.com")
        from edgar import Company
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=2)).isoformat()
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
    return float(probs[0] - probs[1])


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


def get_intraday_return(ticker: str) -> float | None:
    """Return today's price change vs prior close (0.03 = +3%)."""
    try:
        tk = yf.Ticker(ticker)
        current = float(tk.fast_info.last_price)
        # Try yfinance for prior close; fall back to Polygon
        prior_close = None
        try:
            df = yf.download(ticker, period="5d", interval="1d",
                             progress=False, auto_adjust=True)
            if len(df) >= 2:
                prior_close = float(df["Close"].iloc[-2])
        except Exception:
            pass
        if prior_close is None:
            log(f"  {ticker}: yfinance prior_close failed, trying Polygon backup")
            prior_close = _polygon_prev_close(ticker)
        if prior_close is None:
            return None
        return (current - prior_close) / prior_close
    except Exception:
        return None


def get_current_price(ticker: str) -> float | None:
    try:
        return float(yf.Ticker(ticker).fast_info.last_price)
    except Exception:
        return None


def load_positions() -> list:
    if not POSITIONS_PATH.exists():
        return []
    return json.loads(POSITIONS_PATH.read_text())


def save_positions(positions: list):
    POSITIONS_PATH.write_text(json.dumps(positions, indent=2))


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


def get_equity() -> float:
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.environ["ALPACA_API_KEY"],
                               os.environ["ALPACA_SECRET"], paper=True)
        return float(client.get_account().equity)
    except Exception:
        return 100_000.0


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


# ── Main ──────────────────────────────────────────────────────────────────────

def run(tickers: list[str]):
    log("=" * 55)
    log(f"PEAD intraday pass starting — tickers: {tickers}")
    today = date.today().isoformat()

    existing_tickers = {p["ticker"] for p in load_positions()}
    equity = get_equity()
    log(f"Account equity: ${equity:,.0f}")

    new_positions = []

    for ticker in tickers:
        if ticker in existing_tickers:
            log(f"  {ticker}: already in positions, skipping")
            continue

        # Fetch 8-K
        log(f"  Fetching 8-K for {ticker}…")
        text = fetch_8k_text(ticker)
        if not text:
            log(f"  {ticker}: no 8-K Item 2.02 — skip")
            continue

        # Score
        score = score_text(text)
        surprise = compute_surprise(ticker, score)
        log(f"  {ticker}: score={score:.3f}  surprise={'nan' if np.isnan(surprise) else f'{surprise:.3f}'}")

        if score < SCORE_THRESH:
            log(f"  {ticker}: score {score:.3f} < {SCORE_THRESH} — skip")
            continue
        if not np.isnan(surprise) and surprise < SURPRISE_THRESH:
            log(f"  {ticker}: surprise {surprise:.3f} < {SURPRISE_THRESH} — skip")
            continue

        # Intraday momentum confirmation (stock must be up on the day)
        intraday_ret = get_intraday_return(ticker)
        if intraday_ret is None:
            log(f"  {ticker}: could not get intraday return — skip")
            continue
        if intraday_ret <= 0:
            log(f"  {ticker}: down {intraday_ret*100:.1f}% today — skip (no momentum)")
            continue

        current_price = get_current_price(ticker)
        if current_price is None:
            log(f"  {ticker}: could not get price — skip")
            continue

        log(f"  ✓ {ticker} PASSES (score={score:.3f}, surprise={surprise if not np.isnan(surprise) else 'n/a'}, intraday={intraday_ret*100:.1f}%)")

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
            "intraday_ret": round(intraday_ret, 4),
            "stop_price": round(current_price * 0.90, 2),
            "hold_days": HOLD_DAYS,
            "score": round(score, 4),
            "surprise": round(float(surprise), 4) if not np.isnan(surprise) else None,
            "source": "intraday",
        }
        new_positions.append(position)
        log(f"  {ticker}: position logged, exit={exit_date}")

    if new_positions:
        all_positions = load_positions() + new_positions
        save_positions(all_positions)
        log(f"Logged {len(new_positions)} new intraday position(s). Total open: {len(all_positions)}")
    else:
        log("No new positions entered this pass.")

    log("Intraday pass complete.")


if __name__ == "__main__":
    raw = os.environ.get("PEAD_INTRADAY_TICKERS", "[]")
    try:
        tickers = json.loads(raw)
    except Exception:
        tickers = [raw] if raw else []

    if not tickers:
        print("No tickers passed. Set PEAD_INTRADAY_TICKERS env var.")
        sys.exit(0)

    run(tickers)
