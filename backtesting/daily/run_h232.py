#!/usr/bin/env python3
"""
H232 — EDGAR Narrative Drift Gate (Moving Targets on 8-K Sequences)

Source: arXiv:2510.03195 v5 (Choi, Kim et al., Mar 2026)
  "From Text to Alpha: Can LLMs Track Evolving Signals in Corporate Disclosures?"

Hypothesis: A firm that significantly shifts its emphasized financial metrics
between consecutive 8-K filings has stronger post-earnings drift.

Practical simplification (per H174 OOS EPS surprise coverage issues):
  - Evaluate: does narrative drift score ALONE improve on H163's FinBERT>=0.18?
  - Baseline: H163 FinBERT >= 0.18 (OOS WR=80.8%, n=26, MeanRet=6.22%)
  - Test: FinBERT >= 0.18 AND drift_score > threshold

IS: 2020-2022 (calibrate drift threshold)
OOS: 2023-2025 (holdout)

Signal: cosine distance between sentence-transformer embeddings of consecutive
        8-K press releases for the same ticker (quarter-over-quarter change).

Model: all-MiniLM-L6-v2 (fast, free, 80MB)
"""

import os
import sys
import json
import time
import warnings
import re
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

DRIFT_CACHE = CACHE_DIR / "h232_drift_scores.parquet"
RESULT_PATH = RESULT_DIR / "h232_results.json"

# Same universe as H163
UNIVERSE = [
    "AAPL","MSFT","GOOGL","META","AMZN","NVDA","TSLA",
    "JPM","BAC","WFC",
    "JNJ","PFE","MRK",
    "XOM","CVX",
    "WMT","COST","HD","LOW",
    "SBUX","V","MA",
    "UNH","ABBV","LLY",
    "AVGO","AMD","QCOM","INTC","IBM",
]

IS_START  = pd.Timestamp("2020-01-01")
IS_END    = pd.Timestamp("2022-12-31")
OOS_START = pd.Timestamp("2023-01-01")
OOS_END   = pd.Timestamp("2025-12-31")

FINBERT_THRESH = 0.18  # H163 confirmed threshold


# ── Sentence Transformer ──────────────────────────────────────────────────────

def load_model():
    from sentence_transformers import SentenceTransformer
    print("  Loading all-MiniLM-L6-v2...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    return model


def embed_text(text: str, model) -> np.ndarray:
    """Embed text as a single vector (mean of sentence embeddings)."""
    # Split into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)
                 if len(s.strip()) > 20]
    if not sentences:
        return None
    # Limit to 100 sentences for speed
    sentences = sentences[:100]
    embeddings = model.encode(sentences, batch_size=32, show_progress_bar=False)
    return embeddings.mean(axis=0)


def cosine_distance(v1: np.ndarray, v2: np.ndarray) -> float:
    """Returns cosine distance (1 - cosine_similarity). Range [0, 2]."""
    n1 = np.linalg.norm(v1)
    n2 = np.linalg.norm(v2)
    if n1 == 0 or n2 == 0:
        return np.nan
    return float(1.0 - np.dot(v1, v2) / (n1 * n2))


# ── Load cached data ──────────────────────────────────────────────────────────

def load_finbert_scores() -> pd.DataFrame:
    """Load H163 FinBERT scores cache."""
    path = CACHE_DIR / "h163_finbert_scores.parquet"
    if not path.exists():
        raise FileNotFoundError(f"H163 FinBERT scores not found at {path}")
    df = pd.read_parquet(path)
    df['date'] = pd.to_datetime(df['date'])
    return df


def load_ohlcv() -> dict:
    """Load OHLCV from H163 cache."""
    result = {}
    for t in UNIVERSE:
        # Try H163 cache
        p = CACHE_DIR / f"h163_{t}_ohlcv_2019-01-01_2026-04-30.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "open" in df.columns and "close" in df.columns:
                result[t] = df[["open", "close"]]
    missing = [t for t in UNIVERSE if t not in result]
    if missing:
        print(f"  Downloading OHLCV for {missing}...")
        import yfinance as yf
        batch = yf.download(missing, start="2019-01-01", end="2026-05-31",
                           auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in missing:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    result[t] = df.dropna()
                except Exception:
                    pass
    return result


def compute_return(ticker, entry_date, ohlcv, hold=20) -> float:
    """20-day hold return from entry_date open."""
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = future.iloc[0]["open"]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


# ── Drift score computation ───────────────────────────────────────────────────

def get_cached_8k_text(ticker: str, date: pd.Timestamp) -> str:
    """Load cached 8-K text if available."""
    date_str = date.strftime('%Y-%m-%d')
    path = CACHE_DIR / f"h163_8k_{ticker}_{date_str}.txt"
    if path.exists():
        return path.read_text(encoding='utf-8', errors='ignore')
    return None


def clean_text_for_embedding(text: str) -> str:
    """Strip box-drawing characters and normalize whitespace."""
    # Remove unicode box chars (│ ╭ ╰ ─ etc.)
    text = re.sub(r'[╭╮╯╰│─┼┤├┬┴┼╎]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def compute_drift_scores(events_df: pd.DataFrame, model) -> pd.DataFrame:
    """
    For each event, find the prior quarter's 8-K for the same ticker,
    embed both, compute cosine distance.

    Returns DataFrame with columns: ticker, date, drift_score
    """
    # Check drift cache first
    if DRIFT_CACHE.exists():
        cached = pd.read_parquet(DRIFT_CACHE)
        cached['date'] = pd.to_datetime(cached['date'])
        print(f"  Loaded {len(cached)} cached drift scores")
    else:
        cached = pd.DataFrame(columns=['ticker', 'date', 'drift_score'])

    cached_keys = set(zip(cached['ticker'], cached['date'].astype(str)))

    # Group events by ticker to find prior quarters
    # Sort all events by ticker and date
    events_sorted = events_df.sort_values(['ticker', 'date']).reset_index(drop=True)

    new_rows = []
    n_computed = 0
    n_skipped_no_cache = 0

    for ticker in events_sorted['ticker'].unique():
        ticker_events = events_sorted[events_sorted['ticker'] == ticker].sort_values('date')

        # Build a map of date -> text for this ticker
        date_text_map = {}
        for _, row in ticker_events.iterrows():
            text = get_cached_8k_text(ticker, row['date'])
            if text:
                date_text_map[row['date']] = text

        # For each event (from 2nd onward), compute drift vs prior
        event_dates = ticker_events['date'].tolist()
        for i, evt_date in enumerate(event_dates):
            key = (ticker, str(evt_date.date()) if hasattr(evt_date, 'date') else str(evt_date)[:10])
            if key in cached_keys:
                continue  # Already computed

            if i == 0:
                # No prior event — can't compute drift
                new_rows.append({'ticker': ticker, 'date': evt_date, 'drift_score': np.nan})
                continue

            # Find the most recent prior event with a cached 8-K
            prior_date = None
            for j in range(i - 1, -1, -1):
                candidate = event_dates[j]
                if candidate in date_text_map:
                    prior_date = candidate
                    break

            if prior_date is None or evt_date not in date_text_map:
                new_rows.append({'ticker': ticker, 'date': evt_date, 'drift_score': np.nan})
                n_skipped_no_cache += 1
                continue

            # Embed both texts and compute drift
            curr_text = clean_text_for_embedding(date_text_map[evt_date])
            prior_text = clean_text_for_embedding(date_text_map[prior_date])

            curr_emb = embed_text(curr_text, model)
            prior_emb = embed_text(prior_text, model)

            if curr_emb is None or prior_emb is None:
                new_rows.append({'ticker': ticker, 'date': evt_date, 'drift_score': np.nan})
                continue

            dist = cosine_distance(curr_emb, prior_emb)
            new_rows.append({'ticker': ticker, 'date': evt_date, 'drift_score': dist})
            n_computed += 1

    # Combine with cache
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        new_df['date'] = pd.to_datetime(new_df['date'])
        combined = pd.concat([cached, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
        combined.to_parquet(DRIFT_CACHE)
        print(f"  Computed {n_computed} new drift scores, {n_skipped_no_cache} skipped (no 8-K cache)")
        return combined
    else:
        return cached


# ── Backtest ──────────────────────────────────────────────────────────────────

def run_backtest(events_df: pd.DataFrame) -> dict:
    """
    Run H232 backtest.

    Args:
        events_df: DataFrame with columns: ticker, date, finbert_score,
                   drift_score, ret20, win

    Returns metrics dict.
    """
    results = {}

    # Split IS / OOS
    is_df  = events_df[(events_df['date'] >= IS_START) & (events_df['date'] <= IS_END)].copy()
    oos_df = events_df[(events_df['date'] >= OOS_START) & (events_df['date'] <= OOS_END)].copy()

    print(f"\n  IS events: {len(is_df)} | OOS events: {len(oos_df)}")

    # H163 baseline: FinBERT >= 0.18 (no drift filter)
    def metrics(df, label):
        if len(df) == 0:
            return {'n': 0, 'wr': np.nan, 'mean_ret': np.nan}
        return {
            'n': len(df),
            'wr': round(float(df['win'].mean()), 4),
            'mean_ret': round(float(df['ret20'].mean()), 4),
        }

    # IS calibration: find best drift threshold
    is_finbert = is_df[is_df['finbert_score'] >= FINBERT_THRESH].dropna(subset=['drift_score'])
    print(f"\n  IS events with finbert>=0.18 and drift score: {len(is_finbert)}")

    # H163 baseline (no drift filter) — OOS
    oos_baseline = oos_df[oos_df['finbert_score'] >= FINBERT_THRESH]
    results['H163_baseline_OOS'] = metrics(oos_baseline, 'H163 baseline OOS')
    print(f"  H163 baseline OOS (finbert>=0.18): n={results['H163_baseline_OOS']['n']}, "
          f"WR={results['H163_baseline_OOS']['wr']:.1%}, "
          f"MeanRet={results['H163_baseline_OOS']['mean_ret']:.2%}")

    # Drift score distribution
    drift_valid = events_df['drift_score'].dropna()
    print(f"\n  Drift score distribution (all events with drift):")
    print(f"    n={len(drift_valid)}, mean={drift_valid.mean():.4f}, "
          f"std={drift_valid.std():.4f}, "
          f"p25={drift_valid.quantile(0.25):.4f}, "
          f"p50={drift_valid.quantile(0.50):.4f}, "
          f"p75={drift_valid.quantile(0.75):.4f}")

    results['drift_distribution'] = {
        'n': len(drift_valid),
        'mean': round(float(drift_valid.mean()), 4),
        'std': round(float(drift_valid.std()), 4),
        'p25': round(float(drift_valid.quantile(0.25)), 4),
        'p50': round(float(drift_valid.quantile(0.50)), 4),
        'p75': round(float(drift_valid.quantile(0.75)), 4),
    }

    # IS calibration: sweep drift thresholds
    print(f"\n  IS calibration — sweep drift threshold:")
    if len(is_finbert) >= 5:
        best_is_wr = 0
        best_threshold = None
        is_sweep = []
        for pct in [0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75]:
            threshold = float(drift_valid.quantile(pct))
            # High drift: select stocks with drift > threshold (more change = stronger signal)
            subset_high = is_finbert[is_finbert['drift_score'] > threshold]
            # Low drift: select stocks with drift < threshold (consistent messaging)
            subset_low = is_finbert[is_finbert['drift_score'] <= threshold]
            m_high = metrics(subset_high, f'IS drift>{threshold:.4f}')
            m_low  = metrics(subset_low,  f'IS drift<={threshold:.4f}')
            is_sweep.append({
                'pctile': pct,
                'threshold': round(threshold, 4),
                'high_drift': m_high,
                'low_drift': m_low,
            })
            print(f"    p{int(pct*100)} drift={threshold:.4f}: "
                  f"HIGH(n={m_high['n']},WR={m_high['wr']:.1%}) | "
                  f"LOW(n={m_low['n']},WR={m_low['wr']:.1%})")
            if m_high['n'] >= 3 and m_high['wr'] > best_is_wr:
                best_is_wr = m_high['wr']
                best_threshold = threshold

        results['IS_sweep'] = is_sweep
        results['IS_best_threshold'] = round(float(best_threshold), 4) if best_threshold else None
    else:
        print(f"    Insufficient IS events ({len(is_finbert)}) for sweep — reporting without IS calibration")
        results['IS_sweep'] = []
        results['IS_best_threshold'] = None

    # OOS evaluation at multiple thresholds
    print(f"\n  OOS results — drift threshold sweep:")
    oos_finbert = oos_df[oos_df['finbert_score'] >= FINBERT_THRESH].dropna(subset=['drift_score'])
    print(f"  OOS events with finbert>=0.18 and drift score: {len(oos_finbert)}")

    oos_results = []
    for pct in [0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75]:
        threshold = float(drift_valid.quantile(pct))
        subset_high = oos_finbert[oos_finbert['drift_score'] > threshold]
        subset_low  = oos_finbert[oos_finbert['drift_score'] <= threshold]
        m_high = metrics(subset_high, '')
        m_low  = metrics(subset_low, '')
        oos_results.append({
            'pctile': pct,
            'threshold': round(threshold, 4),
            'high_drift': m_high,
            'low_drift': m_low,
        })
        print(f"    p{int(pct*100)} drift={threshold:.4f}: "
              f"HIGH(n={m_high['n']},WR={m_high['wr']:.1%},Ret={m_high['mean_ret']:.2%}) | "
              f"LOW(n={m_low['n']},WR={m_low['wr']:.1%},Ret={m_low['mean_ret']:.2%})")

    results['OOS_sweep'] = oos_results

    # Primary OOS: evaluate at IS-calibrated best threshold
    if results['IS_best_threshold']:
        best_t = results['IS_best_threshold']
        best_oos_high = oos_finbert[oos_finbert['drift_score'] > best_t]
        best_oos_low  = oos_finbert[oos_finbert['drift_score'] <= best_t]
        results['OOS_best_high'] = metrics(best_oos_high, '')
        results['OOS_best_low']  = metrics(best_oos_low, '')
        print(f"\n  OOS at IS-best threshold ({best_t:.4f}):")
        print(f"    HIGH drift: n={results['OOS_best_high']['n']}, "
              f"WR={results['OOS_best_high']['wr']:.1%}, "
              f"Ret={results['OOS_best_high']['mean_ret']:.2%}")
        print(f"    LOW drift:  n={results['OOS_best_low']['n']}, "
              f"WR={results['OOS_best_low']['wr']:.1%}, "
              f"Ret={results['OOS_best_low']['mean_ret']:.2%}")

    # Drift-only filter (no FinBERT gate) — explore drift as standalone
    print(f"\n  Drift-only filter (no FinBERT gate, for comparison):")
    oos_all_drift = oos_df.dropna(subset=['drift_score'])
    for pct in [0.50, 0.67, 0.75]:
        threshold = float(drift_valid.quantile(pct))
        subset = oos_all_drift[oos_all_drift['drift_score'] > threshold]
        m = metrics(subset, '')
        print(f"    p{int(pct*100)} drift>{threshold:.4f}: n={m['n']}, WR={m['wr']:.1%}, Ret={m['mean_ret']:.2%}")

    # Final verdict
    baseline_wr = results['H163_baseline_OOS']['wr'] or 0
    baseline_ret = results['H163_baseline_OOS']['mean_ret'] or 0

    # Check if any OOS variant improves over baseline
    confirmed = False
    best_variant = None
    for r in oos_results:
        m = r['high_drift']
        if m['n'] >= 5 and m['wr'] > baseline_wr and m['mean_ret'] > baseline_ret:
            confirmed = True
            best_variant = r
            break

    results['confirmed'] = confirmed
    results['run_date'] = datetime.now().strftime('%Y-%m-%d %H:%M')

    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"
    print(f"\n  === H232 VERDICT: {verdict} ===")
    if confirmed and best_variant:
        bm = best_variant['high_drift']
        print(f"  Best: drift > {best_variant['threshold']:.4f} (p{int(best_variant['pctile']*100)})")
        print(f"  OOS: n={bm['n']}, WR={bm['wr']:.1%}, MeanRet={bm['mean_ret']:.2%}")
        print(f"  vs H163 baseline: WR={baseline_wr:.1%}, MeanRet={baseline_ret:.2%}")
    else:
        print(f"  H163 baseline OOS WR={baseline_wr:.1%}, MeanRet={baseline_ret:.2%}")
        print(f"  No drift threshold improved BOTH WR and MeanRet over baseline.")

    return results


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  H232 — EDGAR Narrative Drift Gate")
    print("=" * 65)

    # 1. Load FinBERT scores
    print("\n[1/5] Loading H163 FinBERT scores...")
    finbert_df = load_finbert_scores()
    print(f"  {len(finbert_df)} events loaded")

    # 2. Load OHLCV for forward returns
    print("\n[2/5] Loading OHLCV data...")
    ohlcv = load_ohlcv()
    print(f"  {len(ohlcv)} tickers loaded")

    # 3. Build full events table with forward returns
    print("\n[3/5] Computing 20-day forward returns...")
    events = []
    for _, row in finbert_df.iterrows():
        ret = compute_return(row['ticker'], row['date'], ohlcv, hold=20)
        if ret is None:
            continue
        events.append({
            'ticker': row['ticker'],
            'date': row['date'],
            'finbert_score': row['finbert_score'],
            'ret20': ret,
            'win': ret > 0,
        })
    events_df = pd.DataFrame(events)
    events_df['date'] = pd.to_datetime(events_df['date'])
    print(f"  {len(events_df)} events with valid forward returns")

    # 4. Compute drift scores
    print("\n[4/5] Computing narrative drift scores...")
    model = load_model()
    drift_df = compute_drift_scores(events_df, model)

    # Merge drift scores into events
    drift_df = drift_df[['ticker', 'date', 'drift_score']].copy()
    drift_df['date'] = pd.to_datetime(drift_df['date'])
    events_df = events_df.merge(drift_df, on=['ticker', 'date'], how='left')

    n_with_drift = events_df['drift_score'].notna().sum()
    print(f"  Events with drift score: {n_with_drift} / {len(events_df)}")

    # 5. Run backtest
    print("\n[5/5] Running H232 backtest...")
    results = run_backtest(events_df)

    # Save results
    with open(RESULT_PATH, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {RESULT_PATH}")

    return results


if __name__ == '__main__':
    main()
