"""
H168 — PEAD-NLP: Speaker-Weighted FinBERT on Earnings Call Transcripts

Hypothesis: FinBERT sentiment weighted by speaker type (analyst questions > CFO
remarks > executive commentary) outperforms flat-average FinBERT (H163).

Based on arXiv:2604.13260 (April 2026): 16,428 S&P 500 calls 2015-2025.
OOS Spearman IC = 0.142, monthly alpha = 2.03% (t=6.49).
Weights: Analyst 49%, CFO 30%, Executive 16%, Other 5%.

Data: AlphaVantage EARNINGS_CALL_TRANSCRIPT API (25 req/day free tier).
Universe: same as H163 — 30 large-cap gap-up earnings events.
Filter: enter gap-up only if weighted_finbert_score > threshold (0.1).
Hold: 20 trading days. IS: 2020-2023. OOS: 2024+.

Run: python run_h168.py [--download-only] [--score-only]
"""

import os, json, time, warnings
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Config ─────────────────────────────────────────────────────────────────────
CACHE_DIR      = Path("backtesting/cache")
RESULTS_DIR    = Path("backtesting/results")
TRANSCRIPT_DIR = CACHE_DIR / "h168_transcripts"
SCORES_CACHE   = CACHE_DIR / "h168_finbert_scores.parquet"
LOG_PATH       = Path("/tmp/h168_run.log")

AV_KEY         = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
AV_RATE_DELAY  = 15          # seconds between AV requests (free tier: ~4/min)
AV_DAILY_LIMIT = 25

TICKERS = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

# Speaker type weights (arXiv:2604.13260 Table 4)
SPEAKER_WEIGHTS = {
    "analyst":   0.49,
    "cfo":       0.30,
    "executive": 0.16,
    "other":     0.05,
}

GAP_THRESH      = 0.03       # ≥3% gap to qualify as earnings gap-up (match H163)
HOLD_DAYS       = 20
IS_START        = "2020-01-01"
IS_END          = "2023-12-31"
OOS_START       = "2024-01-01"
OOS_END         = "2026-04-30"
FINBERT_THRESH  = 0.10       # min weighted score to enter trade
MAX_POSITIONS   = 10
TRADE_SIZE      = 10_000

CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


# ── Speaker classification ─────────────────────────────────────────────────────

def classify_speaker(title: str) -> str:
    """Map AV speaker title to weight category."""
    t = title.lower()
    if "analyst" in t:
        return "analyst"
    elif "cfo" in t or "chief financial" in t or "finance" in t:
        return "cfo"
    elif any(x in t for x in ["ceo", "chief executive", "president", "director",
                                "investor relations", "vice president", "vp "]):
        return "executive"
    else:
        return "other"


# ── Fiscal quarter estimation ──────────────────────────────────────────────────

# Known non-calendar FY month-end (month when FY ends, 1=Jan...12=Dec)
FISCAL_YEAR_END = {
    "AAPL":  9,   # Sep 30
    "MSFT":  6,   # Jun 30
    "NVDA":  1,   # Jan 31 (roughly)
    "WMT":   1,   # Jan 31
    "COST":  8,   # Aug 31
    "AVGO":  10,  # Oct 31
}

def date_to_av_quarters(ticker: str, event_date: pd.Timestamp) -> list[str]:
    """
    Return a list of (year, quarter) strings to try in AlphaVantage,
    most likely first. e.g. ["2024Q1", "2023Q4", "2024Q2"].
    """
    fy_end_month = FISCAL_YEAR_END.get(ticker, 12)   # default: Dec FY end

    # Determine which fiscal quarter the event_date falls in
    m = event_date.month
    y = event_date.year

    if fy_end_month == 12:
        # Calendar year FY: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
        # Earnings calls happen ~4 weeks after quarter end
        # e.g., Q1 ends Mar 31, earnings in late Apr/early May
        if m in (1, 2, 3):      q, fy = 4, y - 1   # reporting prior Q4
        elif m in (4, 5, 6):    q, fy = 1, y        # reporting Q1
        elif m in (7, 8, 9):    q, fy = 2, y        # reporting Q2
        else:                   q, fy = 3, y        # reporting Q3
    elif fy_end_month == 9:     # AAPL
        # AAPL FY: Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep
        if m in (1, 2, 3):      q, fy = 1, y        # Q1 report Jan-Feb
        elif m in (4, 5, 6):    q, fy = 2, y        # Q2 report Apr-May
        elif m in (7, 8, 9):    q, fy = 3, y        # Q3 report Jul-Aug
        else:                   q, fy = 4, y        # Q4 report Oct-Nov
    elif fy_end_month == 6:     # MSFT
        # MSFT FY: Q1=Jul-Sep, Q2=Oct-Dec, Q3=Jan-Mar, Q4=Apr-Jun
        if m in (7, 8, 9):      q, fy = 1, y + 1
        elif m in (10, 11, 12): q, fy = 2, y + 1
        elif m in (1, 2, 3):    q, fy = 3, y
        else:                   q, fy = 4, y
    else:
        # Generic: estimate based on calendar quarter (report is ~4-6 wks after qtr end)
        qmap = {1: (4, y-1), 2: (4, y-1), 3: (4, y-1),
                4: (1, y),   5: (1, y),
                6: (2, y),   7: (2, y),   8: (2, y),
                9: (3, y),   10: (3, y),  11: (3, y),
                12: (4, y)}
        q, fy = qmap[m]

    primary = f"{fy}Q{q}"
    # Also try adjacent quarters in case of off-by-one
    alternates = []
    if q > 1:   alternates.append(f"{fy}Q{q-1}")
    else:       alternates.append(f"{fy-1}Q4")
    if q < 4:   alternates.append(f"{fy}Q{q+1}")
    else:       alternates.append(f"{fy+1}Q1")

    return [primary] + alternates


# ── AlphaVantage transcript download ──────────────────────────────────────────

def get_transcript_path(ticker: str, quarter: str) -> Path:
    return TRANSCRIPT_DIR / f"{ticker}_{quarter}.json"


_AV_RATE_LIMITED = False  # global flag — set True when rate limit hit, stops all further fetches


def fetch_transcript(ticker: str, quarter: str) -> tuple[list | None, bool]:
    """
    Fetch from AV API.
    Returns (segments, is_rate_limited).
    segments=None + is_rate_limited=True → quota exhausted, stop all fetching.
    segments=[] + is_rate_limited=False → confirmed no transcript for this quarter.
    """
    global _AV_RATE_LIMITED
    if not AV_KEY:
        return None, False
    url = "https://www.alphavantage.co/query"
    params = {"function": "EARNINGS_CALL_TRANSCRIPT", "symbol": ticker,
              "quarter": quarter, "apikey": AV_KEY}
    try:
        import requests
        r = requests.get(url, params=params, timeout=30)
        data = r.json()
        if "transcript" in data:
            return data["transcript"], False
        elif "Information" in data:
            print(f"    AV rate limit: {data['Information'][:60]}")
            _AV_RATE_LIMITED = True
            return None, True
        return [], False   # no transcript key → confirmed missing
    except Exception as e:
        print(f"    fetch_transcript error: {e}")
        return None, False


def load_or_fetch_transcript(ticker: str, event_date: pd.Timestamp,
                              rate_delay: float = AV_RATE_DELAY) -> list | None:
    """Try quarters in priority order; use cache if available."""
    global _AV_RATE_LIMITED
    if _AV_RATE_LIMITED:
        return None

    quarters = date_to_av_quarters(ticker, event_date)
    for q in quarters:
        path = get_transcript_path(ticker, q)
        if path.exists():
            data = json.loads(path.read_text())
            return data  # may be empty list (confirmed miss)

    # Not in cache — try fetching
    for q in quarters:
        path = get_transcript_path(ticker, q)
        segments, rate_limited = fetch_transcript(ticker, q)
        if rate_limited:
            return None   # stop — do NOT save sentinel
        if segments is not None:
            path.write_text(json.dumps(segments))
            time.sleep(rate_delay)
            if len(segments) > 0:
                return segments
            # Empty list = confirmed no transcript for this quarter
            continue
        # fetch_transcript error (non-rate-limit) — skip this quarter

    # All quarters tried, none found
    return None


# ── FinBERT scoring ─────────────────────────────────────────────────────────────

def load_finbert():
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    print("  Loading ProsusAI/finbert…")
    tok = AutoTokenizer.from_pretrained("ProsusAI/finbert")
    model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
    model.eval()
    return tok, model


def score_text(text: str, tokenizer, model) -> float:
    """finbert_score = mean(pos_prob - neg_prob) across sentences."""
    import torch
    import nltk
    try:
        sentences = nltk.sent_tokenize(text)
    except Exception:
        sentences = [text[i:i+200] for i in range(0, len(text), 200)]
    if not sentences:
        return float("nan")

    sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:80]
    if not sentences:
        return float("nan")

    pos_idx = list(model.config.label2id.keys()).index("positive") \
              if "positive" in model.config.label2id else 2
    neg_idx = list(model.config.label2id.keys()).index("negative") \
              if "negative" in model.config.label2id else 0

    scores = []
    batch_size = 8
    for i in range(0, len(sentences), batch_size):
        batch = sentences[i:i + batch_size]
        try:
            enc = tokenizer(batch, padding=True, truncation=True,
                            max_length=512, return_tensors="pt")
            with torch.no_grad():
                logits = model(**enc).logits
            probs = torch.softmax(logits, dim=-1).numpy()
            for p in probs:
                scores.append(float(p[pos_idx]) - float(p[neg_idx]))
        except Exception:
            pass

    return float(np.mean(scores)) if scores else float("nan")


def compute_weighted_score(segments: list, tokenizer, model) -> float:
    """
    Compute speaker-weighted FinBERT score.
    weights: Analyst 49%, CFO 30%, Executive 16%, Other 5%.
    """
    by_type = defaultdict(list)
    for seg in segments:
        stype = classify_speaker(seg.get("title", ""))
        content = seg.get("content", "").strip()
        if len(content) > 30:
            by_type[stype].append(content)

    type_scores = {}
    for stype, texts in by_type.items():
        combined = " ".join(texts)
        sc = score_text(combined, tokenizer, model)
        type_scores[stype] = sc

    if not type_scores:
        return float("nan")

    # Weighted average, only using types with actual scores
    total_w, total_ws = 0.0, 0.0
    for stype, w in SPEAKER_WEIGHTS.items():
        sc = type_scores.get(stype, float("nan"))
        if not np.isnan(sc):
            total_ws += w * sc
            total_w  += w

    return total_ws / total_w if total_w > 0 else float("nan")


# ── Price data & event detection ───────────────────────────────────────────────

def load_price_data():
    print("[1/6] Loading OHLCV…")
    cache_key = CACHE_DIR / "h168_prices.parquet"
    if cache_key.exists():
        df = pd.read_parquet(cache_key)
        print(f"  Loaded from cache: {len(df.columns)} tickers")
        return df

    raw = yf.download(TICKERS, start="2019-01-01", end=OOS_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs("Close", axis=1, level=0).copy()
        opn   = raw.xs("Open",  axis=1, level=0).copy()
    else:
        close = raw[["Close"]].copy()
        opn   = raw[["Open"]].copy()

    close.to_parquet(cache_key)
    print(f"  {len(close.columns)} tickers loaded")
    return close, opn


def load_earnings_dates():
    """Load yfinance earnings dates for all tickers (with caching)."""
    path = CACHE_DIR / "h168_earnings_dates.parquet"
    if path.exists():
        return pd.read_parquet(path)
    records = []
    for t in TICKERS:
        try:
            ed = yf.Ticker(t).earnings_dates
            if ed is not None and len(ed) > 0:
                for dt in ed.index:
                    records.append({"ticker": t, "earnings_date": pd.Timestamp(dt).tz_localize(None)
                                    if hasattr(pd.Timestamp(dt), 'tzinfo') and pd.Timestamp(dt).tzinfo
                                    else pd.Timestamp(dt)})
        except Exception:
            pass
    df = pd.DataFrame(records)
    if len(df) > 0:
        df["earnings_date"] = pd.to_datetime(df["earnings_date"]).dt.tz_localize(None)
        df.to_parquet(path)
    return df


def find_gap_events(close_df, open_df, earnings_dates_df=None,
                    earnings_window: int = 5):
    """Find gap-up events. If earnings_dates_df provided, filter to earnings-confirmed gaps."""
    print("[2/6] Finding earnings-confirmed gap-up events…")

    # Build earnings set for fast lookup: {(ticker, date_str)} -> True
    earnings_set = set()
    if earnings_dates_df is not None and len(earnings_dates_df) > 0:
        for _, r in earnings_dates_df.iterrows():
            ed = pd.Timestamp(r["earnings_date"])
            for delta in range(-earnings_window, earnings_window + 1):
                d = ed + pd.Timedelta(days=delta)
                earnings_set.add((r["ticker"], str(d.date())))

    events = []
    for t in close_df.columns:
        c = close_df[t].dropna()
        o = open_df[t].dropna() if t in open_df.columns else None
        if o is None or len(c) < 30:
            continue
        for dt in c.index[1:]:
            prev = c.index[c.index.get_loc(dt) - 1]
            if dt not in o.index:
                continue
            gap = (o[dt] - c[prev]) / c[prev]
            if gap >= GAP_THRESH:
                # Filter by earnings window if earnings data available
                if earnings_set and (t, str(dt.date())) not in earnings_set:
                    continue
                period = "IS" if IS_START <= str(dt.date()) <= IS_END else \
                         "OOS" if OOS_START <= str(dt.date()) <= OOS_END else None
                if period:
                    events.append({"ticker": t, "date": dt, "gap": gap,
                                   "period": period})
    df = pd.DataFrame(events).sort_values("date").reset_index(drop=True)
    is_n  = (df["period"] == "IS").sum()
    oos_n = (df["period"] == "OOS").sum()
    print(f"  IS={is_n}  OOS={oos_n}  Total={len(df)}")
    return df


# ── Main ───────────────────────────────────────────────────────────────────────

def run_download_pass(events_df: pd.DataFrame, max_fetches: int = 20):
    """Download and cache transcripts up to max_fetches API calls."""
    fetched, hits, misses = 0, 0, 0
    for _, row in events_df.iterrows():
        ticker = row["ticker"]
        event_date = pd.Timestamp(row["date"])

        # Check if already cached (any quarter)
        quarters = date_to_av_quarters(ticker, event_date)
        cached = any(get_transcript_path(ticker, q).exists() for q in quarters)
        if cached:
            hits += 1
            continue

        if fetched >= max_fetches or _AV_RATE_LIMITED:
            break

        print(f"  Fetching {ticker} {event_date.date()}…", end=" ", flush=True)
        result = load_or_fetch_transcript(ticker, event_date)
        if _AV_RATE_LIMITED:
            print("rate limit hit — stopping pass")
            break
        fetched += 1
        if result and len(result) > 0:
            hits += 1
            print(f"got {len(result)} segments")
        else:
            misses += 1
            print("no transcript")

    print(f"  Download pass: fetched={fetched}, cached_hits={hits}, misses={misses}")
    return fetched


def main():
    import sys
    download_only = "--download-only" in sys.argv
    score_only    = "--score-only" in sys.argv

    print("=" * 62)
    print("  H168 — PEAD-NLP: Speaker-Weighted FinBERT")
    print("=" * 62)

    # Load price data
    result = load_price_data()
    if isinstance(result, tuple):
        close_df, open_df = result
    else:
        close_df = result
        # Re-download for open prices
        raw = yf.download(TICKERS, start="2019-01-01", end=OOS_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            open_df = raw.xs("Open", axis=1, level=0).copy()
        else:
            open_df = close_df.copy()

    earnings_df = load_earnings_dates()
    events_df = find_gap_events(close_df, open_df, earnings_df)

    # Phase 1: Download transcripts
    if not score_only:
        print(f"\n[3/6] Downloading transcripts ({AV_DAILY_LIMIT}/day limit)…")
        n_cached = sum(
            1 for _, r in events_df.iterrows()
            if any(get_transcript_path(r["ticker"], q).exists()
                   for q in date_to_av_quarters(r["ticker"], pd.Timestamp(r["date"])))
        )
        print(f"  Already cached: {n_cached}/{len(events_df)}")
        remaining = len(events_df) - n_cached
        if remaining > 0 and AV_KEY:
            to_fetch = min(AV_DAILY_LIMIT - 3, remaining)  # leave buffer
            print(f"  Fetching up to {to_fetch} new transcripts…")
            run_download_pass(events_df, max_fetches=to_fetch)
        else:
            print("  All cached or no AV key.")

    if download_only:
        print("\nDownload pass complete.")
        return

    # Phase 2: Load FinBERT and score
    print(f"\n[4/6] Loading FinBERT model…")
    tokenizer, finbert = load_finbert()

    print(f"\n[5/6] Computing speaker-weighted FinBERT scores…")

    # Load existing score cache
    if SCORES_CACHE.exists():
        cached_scores = pd.read_parquet(SCORES_CACHE)
        score_dict = {(r.ticker, str(pd.Timestamp(r.date).date())): r.weighted_score
                      for _, r in cached_scores.iterrows()}
        print(f"  Loaded {len(score_dict)} cached scores")
    else:
        score_dict = {}

    new_scores = []
    n_scored, n_missing = 0, 0

    for i, (_, row) in enumerate(events_df.iterrows()):
        key = (row["ticker"], str(pd.Timestamp(row["date"]).date()))
        if key in score_dict:
            continue

        quarters = date_to_av_quarters(row["ticker"], pd.Timestamp(row["date"]))
        segments = None
        for q in quarters:
            path = get_transcript_path(row["ticker"], q)
            if path.exists():
                data = json.loads(path.read_text())
                if data:
                    segments = data
                    break

        if segments and len(segments) > 0:
            sc = compute_weighted_score(segments, tokenizer, finbert)
            n_scored += 1
        else:
            sc = float("nan")
            n_missing += 1

        score_dict[key] = sc
        new_scores.append({"ticker": row["ticker"], "date": row["date"],
                            "weighted_score": sc})

        if (i + 1) % 10 == 0:
            print(f"  Scored {i+1}/{len(events_df)}… (scored={n_scored}, missing={n_missing})")

    print(f"  Final: scored={n_scored}, missing (no transcript)={n_missing}")

    # Save updated score cache
    if new_scores:
        new_df = pd.DataFrame(new_scores)
        if SCORES_CACHE.exists():
            old_df = pd.read_parquet(SCORES_CACHE)
            combined = pd.concat([old_df, new_df]).drop_duplicates(subset=["ticker","date"])
        else:
            combined = new_df
        combined.to_parquet(SCORES_CACHE)

    # Phase 3: Backtest
    print(f"\n[6/6] Running backtest…")
    _run_backtest(events_df, score_dict, close_df)


def _run_backtest(events_df, score_dict, close_df):
    """Run portfolio simulation with weighted FinBERT filter."""
    import scipy.stats as stats

    spy = yf.download("SPY", start="2018-01-01", end=OOS_END,
                      auto_adjust=True, progress=False)["Close"].squeeze()
    spy_cal = spy.index.tolist()
    spy_idx = {d: i for i, d in enumerate(spy_cal)}

    def fwd_ret(ticker, entry_date, n_days):
        c = close_df[ticker].dropna()
        if entry_date not in c.index:
            return float("nan")
        i0 = c.index.get_loc(entry_date)
        i1 = min(i0 + n_days, len(c) - 1)
        return float(c.iloc[i1] / c.iloc[i0] - 1)

    # Attach scores to events
    events_df = events_df.copy()
    events_df["key"] = list(zip(events_df["ticker"],
                                 events_df["date"].apply(
                                     lambda d: str(pd.Timestamp(d).date()))))
    events_df["weighted_score"] = events_df["key"].map(score_dict)

    def run_cohort(sub, label):
        if len(sub) == 0:
            return
        sub = sub.copy()
        sub["ret20"] = sub.apply(
            lambda r: fwd_ret(r["ticker"], r["date"], HOLD_DAYS), axis=1)
        sub = sub.dropna(subset=["ret20"])

        # Baseline: all events regardless of score
        base = sub
        print(f"\n  {label} baseline: n={len(base)}", end="")
        if len(base) > 5:
            t = stats.ttest_1samp(base["ret20"], 0).statistic
            print(f"  WR={base['ret20'].gt(0).mean()*100:.1f}%"
                  f"  Mean={base['ret20'].mean()*100:.2f}%  t={t:.2f}")

        # Scored subset
        scored = sub.dropna(subset=["weighted_score"])
        filtered = scored[scored["weighted_score"] > FINBERT_THRESH]
        print(f"  {label} scored={len(scored)}, filtered(>{FINBERT_THRESH})={len(filtered)}", end="")
        if len(filtered) > 5:
            t = stats.ttest_1samp(filtered["ret20"], 0).statistic
            print(f"  WR={filtered['ret20'].gt(0).mean()*100:.1f}%"
                  f"  Mean={filtered['ret20'].mean()*100:.2f}%  t={t:.2f}")
        else:
            print()

    is_ev  = events_df[events_df["period"] == "IS"]
    oos_ev = events_df[events_df["period"] == "OOS"]
    run_cohort(is_ev, "IS")
    run_cohort(oos_ev, "OOS")

    # Check coverage
    scored_oos = oos_ev.dropna(subset=["weighted_score"])
    coverage = len(scored_oos) / len(oos_ev) * 100 if len(oos_ev) > 0 else 0
    print(f"\n  OOS transcript coverage: {len(scored_oos)}/{len(oos_ev)} = {coverage:.1f}%")

    if coverage < 20:
        verdict = "BLOCKED — insufficient transcript coverage (<20% OOS)"
    elif len(scored_oos) < 20:
        verdict = "INSUFFICIENT DATA — need more OOS transcripts"
    else:
        oos_filtered = oos_ev[oos_ev["weighted_score"].fillna(-99) > FINBERT_THRESH]
        if len(oos_filtered) > 0:
            oos_filtered = oos_filtered.copy()
            oos_filtered["ret20"] = oos_filtered.apply(
                lambda r: fwd_ret(r["ticker"], r["date"], HOLD_DAYS), axis=1)
            oos_filtered = oos_filtered.dropna(subset=["ret20"])
            wr   = oos_filtered["ret20"].gt(0).mean()
            mean = oos_filtered["ret20"].mean()
            n    = len(oos_filtered)
            if n > 5:
                t = stats.ttest_1samp(oos_filtered["ret20"], 0).statistic
            else:
                t = 0
            if wr >= 0.60 and mean >= 0.03 and t >= 2.0:
                verdict = "CONFIRMED"
            elif wr >= 0.55 and mean >= 0.02:
                verdict = "PARTIAL CONFIRMED"
            else:
                verdict = "NOT CONFIRMED"
        else:
            verdict = "NOT CONFIRMED — no OOS events pass filter"

    print(f"\n  VERDICT: {verdict}")

    out_lines = [
        "H168 — PEAD Speaker-Weighted FinBERT",
        f"Run: {pd.Timestamp.now().date()}",
        f"Universe: {len(TICKERS)} stocks  |  Gap>={GAP_THRESH*100:.0f}%  |  Hold={HOLD_DAYS}d",
        f"Weights: Analyst={SPEAKER_WEIGHTS['analyst']:.0%}  "
        f"CFO={SPEAKER_WEIGHTS['cfo']:.0%}  "
        f"Executive={SPEAKER_WEIGHTS['executive']:.0%}  "
        f"Other={SPEAKER_WEIGHTS['other']:.0%}",
        "",
        f"IS events: {len(is_ev)}  |  OOS events: {len(oos_ev)}",
        f"OOS transcript coverage: {coverage:.1f}%",
        "",
        f"VERDICT: {verdict}",
    ]
    out_path = RESULTS_DIR / "h168_pead_speaker_finbert.txt"
    out_path.write_text("\n".join(out_lines))
    print(f"\n  Results saved → {out_path}")


if __name__ == "__main__":
    main()
