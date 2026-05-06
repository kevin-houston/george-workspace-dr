---
updated: 2026-05-06
status: design — H163/H174 confirmed, implementation ready
strategy: H174 PEAD-NLP dual filter (score ≥ 0.18 + surprise ≥ 0.02)
---

# PEAD-NLP Strategy: Live Alpaca Deployment Guide

Deployment guide for the confirmed H163/H174 PEAD-NLP event-driven strategy on Alpaca paper trading. Covers gap detection, overnight 8-K scoring, order submission, and position management.

---

## Strategy Summary

**Confirmed signal (H174):** Buy stocks that gap up ≥ 3% at earnings open, filtered by:
- FinBERT absolute score ≥ 0.18 (primary gate)
- Sentiment surprise ≥ 0.02 (score_t − mean(prior 4q)) — optional secondary gate for higher precision

| Filter | n | WR% | MeanRet% | Notes |
|--------|---|-----|----------|-------|
| Score ≥ 0.18 only | 26 | 80.8% | 6.22% | Widest confirmed combination |
| Score ≥ 0.18 + surprise ≥ 0.02 | 22 | 81.8% | 6.89% | Best balance of n and return |
| Score ≥ 0.20 + surprise ≥ 0.02 | 19 | 78.9% | 6.97% | Highest precision |

Hold period: **20 trading days** from entry open. Entry at open (first bar). Exit at close on day 20.

Backtest OOS baseline: n=85 events over 2024+, WR=57.6%, MeanRet=1.95%.

---

## Architecture

```
[Evening T-1]
  earnings_calendar.py → tickers reporting today
  edgar_poller.py → fetch new 8-K Item 2.02 filings
  finbert_scorer.py → score texts, compute surprise
  
[Pre-market T: before 9:28 AM ET]
  pead_watchlist.py → filter: score ≥ 0.18 AND surprise ≥ 0.02
  (optional) place OPG buy orders for pre-approved tickers

[9:30 AM ET open]
  stream_gaps.py → subscribe Alpaca WebSocket minute bars
  gap_filter.py → detect open / prior_close ≥ 1.03
  order_router.py → cross-check against watchlist, submit market order

[20 trading days later]
  exit_manager.py → submit market sell at close
  log_performance.py → record actual vs expected
```

Two execution paths depending on 8-K filing latency:
1. **Pre-market path** (ideal): 8-K filed overnight → scored before 9:28 AM → OPG order placed before gap detection needed
2. **Open-time path** (fallback): 8-K filed same morning → score at open → submit market order on first bar

---

## Component 1 — Earnings Calendar

```python
import yfinance as yf
from datetime import date, timedelta

def get_earnings_today(universe: list[str]) -> list[str]:
    """Return tickers with earnings confirmed today or yesterday (±1 day window)."""
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
            recent = df[df.index >= pd.Timestamp(today - timedelta(days=1))]
            if not recent.empty:
                reporting.append(ticker)
        except Exception:
            pass
    return reporting
```

Alternative (no yfinance): use Polygon.io `/v3/reference/tickers/{ticker}/events` or Finnhub `/calendar/earnings?from=YYYY-MM-DD&to=YYYY-MM-DD`.

---

## Component 2 — EDGAR 8-K Overnight Poller

```python
import requests
from datetime import date
from edgar import Company  # edgartools v5

EDGAR_HEADERS = {"User-Agent": "george-agent george@nanoclaw.com"}

def search_8k_filings_today(tickers: list[str]) -> dict[str, str]:
    """
    For each ticker, check if an 8-K Item 2.02 was filed today.
    Returns {ticker: text} for scored events.
    """
    today = date.today().isoformat()
    results = {}

    # EFTS full-text search: 8-Ks filed today containing earnings language
    url = (
        "https://efts.sec.gov/LATEST/search-index"
        f"?q=%22results+of+operations%22&forms=8-K"
        f"&dateRange=custom&startdt={today}&enddt={today}&size=100"
    )
    resp = requests.get(url, headers=EDGAR_HEADERS, timeout=10)
    if resp.status_code != 200:
        return results

    data = resp.json()
    filed_ciks = {f["cik"]: f for f in data.get("filings", [])}

    for ticker in tickers:
        try:
            company = Company(ticker)
            # Lookup CIK from company
            cik = str(company.cik).zfill(10)
            if cik not in filed_ciks:
                continue

            # Fetch the actual filing text
            filing = company.get_filings(form="8-K").latest()
            if str(filing.filing_date) != today:
                continue

            eightk = filing.obj()
            if not eightk.items or 2.02 not in eightk.items:
                continue

            text = filing.markdown()
            if text and len(text) > 200:
                results[ticker] = text
        except Exception:
            continue

    return results


def poll_8k_until_available(
    ticker: str, max_attempts: int = 12, interval_secs: int = 300
) -> str | None:
    """Poll for an 8-K filing with 5-minute intervals (max 1 hour)."""
    import time
    today = date.today().isoformat()
    for _ in range(max_attempts):
        try:
            company = Company(ticker)
            filing = company.get_filings(form="8-K").latest()
            if str(filing.filing_date) == today:
                eightk = filing.obj()
                if eightk.items and 2.02 in eightk.items:
                    return filing.markdown()
        except Exception:
            pass
        time.sleep(interval_secs)
    return None
```

**Filing latency:** After-hours earnings (4+ PM ET) → 8-K typically filed within 2 hours (before 6:30 PM ET) for large-caps. Some file next morning pre-market. EDGAR EFTS indexes within 300ms of acceptance. Check from 5 AM ET onward.

---

## Component 3 — FinBERT Scorer + Surprise Filter

```python
import torch
import numpy as np
import pandas as pd
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from pathlib import Path

CACHE_DIR = Path("backtesting/cache")
SCORE_CACHE = CACHE_DIR / "h163_finbert_scores.parquet"

_tokenizer = None
_model = None

def _load_finbert():
    global _tokenizer, _model
    if _tokenizer is None:
        _tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        _model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        _model.eval()
    return _tokenizer, _model

def score_text(text: str) -> float:
    """FinBERT score = P(positive) - P(negative), range [-1, 1]."""
    tok, model = _load_finbert()
    inputs = tok(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0].numpy()
    # ProsusAI/finbert label order: positive=0, negative=1, neutral=2
    return float(probs[0] - probs[1])

def compute_surprise(ticker: str, event_date: str, current_score: float) -> float:
    """Compare current score vs mean of prior 4 quarters in the score cache."""
    if not SCORE_CACHE.exists():
        return float("nan")
    df = pd.read_parquet(SCORE_CACHE)
    df["date"] = pd.to_datetime(df["date"])
    prior = df[
        (df["ticker"] == ticker) &
        (df["date"] < pd.Timestamp(event_date)) &
        df["finbert_score"].notna()
    ].sort_values("date").tail(4)
    if len(prior) < 2:
        return float("nan")
    return current_score - prior["finbert_score"].mean()

def filter_pead_candidates(
    scored_events: dict[str, tuple[float, float]],
    score_thresh: float = 0.18,
    surprise_thresh: float = 0.02,
) -> list[str]:
    """
    scored_events: {ticker: (finbert_score, surprise)}
    Returns tickers passing both filters.
    """
    return [
        t for t, (sc, surp) in scored_events.items()
        if sc >= score_thresh and (np.isnan(surp) or surp >= surprise_thresh)
    ]
```

**Runtime:** ~15s per text on CPU (MacBook M2 equivalent); ~2s on GPU. For 30-ticker universe, overnight scoring of all expected earnings: 10–15 min on CPU.

---

## Component 4 — Gap-Up Detection (Alpaca WebSocket)

```python
import asyncio
from datetime import date
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
import alpaca_trade_api as tradeapi  # for prior close

API_KEY = os.environ["ALPACA_API_KEY"]
SECRET   = os.environ["ALPACA_SECRET"]

class GapDetector:
    def __init__(self, watch_list: list[str], prior_closes: dict[str, float]):
        self.watch_list = watch_list
        self.prior_closes = prior_closes  # {ticker: close_price_yesterday}
        self.gap_events = {}  # {ticker: gap_pct}
        self.stream = StockDataStream(API_KEY, SECRET, feed=DataFeed.IEX)

    async def handle_bar(self, bar):
        ticker = bar.symbol
        if ticker not in self.prior_closes:
            return
        gap = (bar.open - self.prior_closes[ticker]) / self.prior_closes[ticker]
        if gap >= 0.03 and ticker not in self.gap_events:
            self.gap_events[ticker] = gap
            print(f"GAP-UP: {ticker} +{gap*100:.1f}% (open={bar.open:.2f}, "
                  f"prior_close={self.prior_closes[ticker]:.2f})")

    def run(self, timeout_secs: int = 600):
        """Run stream for timeout_secs (default 10 min covering the open)."""
        self.stream.subscribe_bars(self.handle_bar, *self.watch_list)
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(asyncio.wait_for(
                asyncio.to_thread(self.stream.run), timeout=timeout_secs
            ))
        except asyncio.TimeoutError:
            self.stream.close()
        return self.gap_events
```

To get prior closes, use Alpaca's historical bars endpoint or yfinance. Fetch the night before so they're available at open.

---

## Component 5 — Order Submission

```python
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

client = TradingClient(API_KEY, SECRET, paper=True)

POSITION_SIZE_PCT = 0.05   # 5% of portfolio per event
STOP_LOSS_PCT     = 0.10   # 10% stop-loss (generous, 20-day hold)
HOLD_DAYS         = 20


def get_equity() -> float:
    account = client.get_account()
    return float(account.equity)


def submit_pead_entry(ticker: str, ref_price: float) -> dict:
    """
    Submit market buy order using OPG (fills at next market open).
    ref_price: approximate price for stop-loss calculation.
    Returns order metadata for the exit scheduler.
    """
    equity = get_equity()
    notional = round(equity * POSITION_SIZE_PCT, 2)

    # Note: fractional shares (notional-based) cannot have bracket orders.
    # Submit market entry; stop-loss submitted as separate GTC order after fill.
    entry_order = MarketOrderRequest(
        symbol=ticker,
        notional=notional,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.OPG,
    )
    order = client.submit_order(entry_order)
    print(f"PEAD ENTRY: {ticker} notional=${notional:.0f} OPG "
          f"order_id={order.id}")
    return {
        "order_id": str(order.id),
        "ticker": ticker,
        "notional": notional,
        "entry_date": date.today().isoformat(),
        "ref_price": ref_price,
        "stop_price": ref_price * (1 - STOP_LOSS_PCT),
        "hold_days": HOLD_DAYS,
    }


def submit_stop_loss(ticker: str, qty: float, stop_price: float):
    """Submit GTC stop-loss after entry fills."""
    stop = StopOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        stop_price=round(stop_price, 2),
        time_in_force=TimeInForce.GTC,
    )
    client.submit_order(stop)
    print(f"STOP-LOSS: {ticker} qty={qty} stop=${stop_price:.2f} GTC")


def submit_pead_exit(ticker: str, qty: float):
    """Submit market sell at close (MOC) on day 20."""
    exit_order = MarketOrderRequest(
        symbol=ticker,
        qty=qty,
        side=OrderSide.SELL,
        time_in_force=TimeInForce.CLS,  # MOC — market on close
    )
    order = client.submit_order(exit_order)
    print(f"PEAD EXIT: {ticker} qty={qty} MOC order_id={order.id}")
    return order
```

**Key constraint:** `notional` and `qty` are mutually exclusive. Using `notional` enables fractional sizing but prevents bracket orders — submit stop as a separate GTC order after fill confirmation.

---

## Component 6 — Event Log & Exit Scheduler

```python
import json
from pathlib import Path
from datetime import date, timedelta
import pandas_market_calendars as mcal

LOG_PATH = Path("backtesting/paper_trading/pead_positions.json")

def load_positions() -> list[dict]:
    if LOG_PATH.exists():
        return json.loads(LOG_PATH.read_text())
    return []

def save_positions(positions: list[dict]):
    LOG_PATH.write_text(json.dumps(positions, indent=2))

def add_position(order_meta: dict):
    positions = load_positions()
    positions.append(order_meta)
    save_positions(positions)

def get_exit_date(entry_date: str, hold_days: int = 20) -> str:
    """Calculate exit date as Nth trading day from entry."""
    nyse = mcal.get_calendar("NYSE")
    entry = pd.Timestamp(entry_date)
    schedule = nyse.schedule(start_date=entry, end_date=entry + timedelta(days=40))
    trading_days = schedule.index
    idx = trading_days.get_loc(entry) if entry in trading_days else 0
    exit_day = trading_days[idx + hold_days - 1]
    return exit_day.strftime("%Y-%m-%d")

def check_exits_today():
    """Submit MOC exit for positions whose hold period ends today."""
    today = date.today().isoformat()
    positions = load_positions()
    remaining = []
    for pos in positions:
        exit_date = pos.get("exit_date") or get_exit_date(
            pos["entry_date"], pos.get("hold_days", 20)
        )
        if exit_date <= today:
            # Look up current qty from Alpaca
            try:
                alpaca_pos = client.get_open_position(pos["ticker"])
                qty = float(alpaca_pos.qty)
                submit_pead_exit(pos["ticker"], qty)
            except Exception as e:
                print(f"Exit check failed for {pos['ticker']}: {e}")
        else:
            remaining.append(pos)
    save_positions(remaining)
```

---

## Full Orchestrator Script

```python
#!/usr/bin/env python3
"""
pead_overnight.py — Run nightly, after market close.
1. Identify tickers with earnings today
2. Fetch + score 8-K filings
3. Save watchlist for tomorrow's gap detection

Run at 9:30 AM: pead_open.py (gap detection + order submission)
"""
import os
from datetime import date
from pead_components import (
    get_earnings_today, search_8k_filings_today, score_text,
    compute_surprise, filter_pead_candidates
)
import json
from pathlib import Path

UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC","JNJ","PFE","MRK","XOM","CVX",
    "WMT","COST","HD","LOW","SBUX","V","MA",
    "UNH","ABBV","LLY","AVGO","AMD","QCOM","INTC","IBM",
]

def run_overnight():
    print(f"[{date.today()}] PEAD overnight scoring")

    # 1. Earnings today
    reporting = get_earnings_today(UNIVERSE)
    print(f"  Tickers with earnings today/yesterday: {reporting}")
    if not reporting:
        print("  No earnings detected. Exiting.")
        return

    # 2. Fetch 8-K filings
    texts = search_8k_filings_today(reporting)
    print(f"  8-K texts fetched: {list(texts.keys())}")

    # 3. Score
    scored = {}
    for ticker, text in texts.items():
        sc = score_text(text)
        surp = compute_surprise(ticker, date.today().isoformat(), sc)
        scored[ticker] = (sc, surp)
        print(f"  {ticker}: score={sc:.3f}, surprise={surp:.3f}")

    # 4. Filter
    candidates = filter_pead_candidates(scored, score_thresh=0.18, surprise_thresh=0.02)
    print(f"  PEAD candidates: {candidates}")

    # 5. Save watchlist
    watchlist = {
        "date": date.today().isoformat(),
        "candidates": candidates,
        "scores": {t: {"score": v[0], "surprise": v[1]} for t, v in scored.items()},
    }
    Path("backtesting/paper_trading/pead_watchlist.json").write_text(
        json.dumps(watchlist, indent=2)
    )
    print("  Watchlist saved.")

if __name__ == "__main__":
    run_overnight()
```

---

## Scheduling

| Task | Schedule | Script |
|------|----------|--------|
| Overnight scoring | 11 PM CT (after all 8-Ks likely filed) | `pead_overnight.py` |
| Gap detection | 9:30–9:45 AM CT | `pead_open.py` |
| Exit check | 3:45 PM CT (before MOC) | `pead_exits.py` |
| Score cache update | Monthly (after each 8-K download pass) | `run_h163.py` |

---

## OPG vs Market Order Timing

| Approach | Cutoff | Pros | Cons |
|----------|--------|------|------|
| **OPG order pre-market** | Before 9:28 AM ET | Cleanest; fills at exact open price | Requires 8-K scored before 9:28 AM |
| **Market order at open** | Any time 9:30+ | Works even if 8-K filed at 7 AM | Slight slippage vs opening print |

For after-hours-reporting companies: 8-K typically filed 5–8 PM ET → available by 11 PM → score by 5 AM → OPG order by 9:28 AM. This path is clean.

For pre-market reporters: 8-K may not be filed until after open — use open-time path and submit a market order on first minute bar.

---

## Position Sizing Rationale

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Position size | 5% of equity | Max 20 concurrent PEAD positions (full universe firing simultaneously unlikely) |
| Stop-loss | 10% below entry | H174 20-day MeanRet=6.89%; 10% stop rarely hit but limits catastrophic loss |
| Hold period | 20 trading days | Confirmed via H163/H174 backtests; drift resolves within 4 weeks |
| Max concurrent | 10 positions | At 5% each = 50% portfolio; other 50% in H149 momentum rotation |

A PEAD position co-existing with H149 rotation is intentional. PEAD is event-driven (15–30 events/year in 30-stock universe at 18% threshold) while H149 is monthly rotation — minimal scheduling conflict.

---

## Current Status

- [ ] Scripts written and tested
- [ ] Overnight scoring scheduler created (`mcp__nanoclaw__schedule_task`)
- [ ] Gap detection tested in paper mode
- [ ] First paper trade placed and logged in `pead_positions.json`
- [ ] H174 confirmation criteria validated live vs backtest

**Prerequisites:** H163 score cache (`h163_finbert_scores.parquet`) must have ≥2 prior quarters of scores for each universe ticker before surprise filter is meaningful. Cache currently covers 2020–2026 for 30 tickers.
