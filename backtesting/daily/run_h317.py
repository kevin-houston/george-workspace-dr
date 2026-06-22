"""
H317 — Multi-Modal PEAD: FinBERT + EPS Analyst Surprise + Pre-Announcement Momentum
====================================================================================
Source: Noseda, Soldati, Paina arXiv:2605.25894 (May 2026)

H174 CONFIRMED: FinBERT score >= 0.18 AND 8K-tone-surprise >= 0.02
→ OOS WR=81.8%, MeanRet=6.89%, n=22

H317 extends H174 by adding two additional signals:
  1. EPS analyst surprise% (actual EPS vs consensus estimate from yfinance)
  2. Pre-announcement 21d price momentum (expect mean reversion if >+10%)

Composite hypothesis: when all three signals align (positive tone, analyst beat,
low pre-announcement drift), win rate should exceed 81.8%.

IS: 2021-2023 (H174 OOS period reused as IS for this test)
OOS: 2024-2026
Gate: Win rate > 70% AND mean return > 4% per trade AND n >= 20 OOS events

Variants:
  A: H174 baseline (score >= 0.18 AND tone-surprise >= 0.02)
  B: H174 + EPS analyst beat (surprise% > 0)
  C: H174 + EPS strong beat (surprise% > 3%)
  D: H174 + pre-momentum filter (exclude if 21d return before announcement > +10%)
  E: H174 + EPS beat + pre-momentum (B AND D combined)
  F: H174 + strong beat + pre-momentum (C AND D combined)
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

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

IS_START  = pd.Timestamp("2021-01-01")
IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")
OOS_END   = pd.Timestamp("2026-06-20")

SCORE_MIN  = 0.18
TONE_SURP  = 0.02
HOLD_DAYS  = 20
PRE_WINDOW = 21
GAP_THRESH = 0.03   # require ≥3% gap-up to enter (same as H174)


def load_daily_prices() -> dict:
    """Load daily OHLCV for each ticker, using cached files if available."""
    result = {}
    start, end = "2019-01-01", "2026-06-20"
    to_dl = []
    for t in UNIVERSE:
        # Try any cached OHLCV file
        found = False
        for pfx in [f"h{i:03d}" for i in range(155, 180)] + ["h320"]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_2026-04-30.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        result[t] = df
                        found = True
                        break
            if found:
                break
        if not found:
            to_dl.append(t)
    if to_dl:
        print(f"  Downloading daily OHLCV for {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        cp = CACHE_DIR / f"h317_{t}_ohlcv_{start}_{end}.parquet"
                        df.to_parquet(cp)
                        result[t] = df
                except Exception:
                    pass
    return result


def fetch_earnings_surprises(ticker: str) -> pd.DataFrame:
    """Fetch EPS surprise data from yfinance earnings_dates."""
    cp = CACHE_DIR / f"h317_{ticker}_earnings.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    try:
        t = yf.Ticker(ticker)
        ed = t.earnings_dates
        if ed is None or len(ed) == 0:
            return pd.DataFrame()
        ed = ed.copy()
        ed.index = pd.DatetimeIndex(ed.index).tz_localize(None)
        ed.columns = [c.lower().replace("(", "").replace(")", "").replace(" ", "_") for c in ed.columns]
        ed.to_parquet(cp)
        return ed
    except Exception as e:
        return pd.DataFrame()


def compute_tone_surprise(df_scores: pd.DataFrame) -> pd.DataFrame:
    """
    For each event, compute 8-K tone surprise = score_t - mean(prior 4 quarters' scores).
    """
    records = []
    for ticker in df_scores['ticker'].unique():
        ts_df = df_scores[df_scores['ticker'] == ticker].sort_values('date')
        ts_df = ts_df.dropna(subset=['finbert_score'])
        for i, row in enumerate(ts_df.itertuples()):
            prior = ts_df.iloc[max(0, i-4):i]
            if len(prior) >= 1:
                tone_surp = row.finbert_score - prior['finbert_score'].mean()
            else:
                tone_surp = np.nan
            records.append({
                'ticker': row.ticker,
                'date': row.date,
                'finbert_score': row.finbert_score,
                'tone_surprise': tone_surp,
            })
    return pd.DataFrame(records)


def compute_outcomes(events: pd.DataFrame, prices: dict) -> pd.DataFrame:
    """
    For each event, compute:
    - gap_pct: open/prior_close - 1 on announcement day
    - pre_21d: 21d return ending day before announcement
    - post_20d: 20d return starting day after announcement (strategy outcome)
    - eps_surprise_pct: from yfinance earnings_dates
    """
    rows = []
    for _, ev in events.iterrows():
        ticker = ev['ticker']
        date   = pd.Timestamp(ev['date'])
        if ticker not in prices:
            continue
        px = prices[ticker]
        if 'open' not in px.columns or 'close' not in px.columns:
            continue

        # Find announcement date in price series
        px_dates = px.index
        future_dates = px_dates[px_dates >= date]
        if len(future_dates) == 0:
            continue
        ann_date = future_dates[0]

        loc = px.index.get_loc(ann_date)
        if loc < PRE_WINDOW + 1 or loc + HOLD_DAYS >= len(px):
            continue

        # Gap: open/prior_close - 1
        prior_close = px['close'].iloc[loc - 1]
        ann_open    = px['open'].iloc[loc]
        gap_pct     = float(ann_open / prior_close - 1)

        # Pre-announcement momentum (21d return ending day before announcement)
        pre_close_end   = px['close'].iloc[loc - 1]
        pre_close_start = px['close'].iloc[loc - PRE_WINDOW - 1]
        pre_21d = float(pre_close_end / pre_close_start - 1)

        # Post-announcement 20d return (from next-day open to 20 days later close)
        entry_price  = px['open'].iloc[loc + 1] if loc + 1 < len(px) else px['close'].iloc[loc]
        exit_price   = px['close'].iloc[loc + HOLD_DAYS]
        post_20d     = float(exit_price / entry_price - 1)

        rows.append({
            'ticker':   ticker,
            'date':     date,
            'ann_date': ann_date,
            'gap_pct':  gap_pct,
            'pre_21d':  pre_21d,
            'post_20d': post_20d,
            'finbert_score':  ev['finbert_score'],
            'tone_surprise':  ev.get('tone_surprise', np.nan),
        })

    result = pd.DataFrame(rows)

    # Join EPS surprise data
    eps_records = []
    for ticker in result['ticker'].unique():
        surp_df = fetch_earnings_surprises(ticker)
        if surp_df.empty:
            continue
        # match by nearest date within ±5 trading days
        for _, row in result[result['ticker'] == ticker].iterrows():
            date = pd.Timestamp(row['ann_date'])
            diffs = abs((surp_df.index - date).days)
            if diffs.min() <= 5:
                best = surp_df.iloc[diffs.argmin()]
                surp_pct = best.get('surprise_', np.nan)
                if pd.isna(surp_pct):
                    # Try alternate column name
                    for col in surp_df.columns:
                        if 'surprise' in col.lower():
                            surp_pct = best[col]
                            break
                eps_records.append({'ticker': ticker, 'ann_date': date,
                                    'eps_surprise_pct': float(surp_pct) if not pd.isna(surp_pct) else np.nan})

    if eps_records:
        eps_df = pd.DataFrame(eps_records)
        result = result.merge(eps_df, on=['ticker', 'ann_date'], how='left')
    else:
        result['eps_surprise_pct'] = np.nan

    return result


def evaluate_filter(events: pd.DataFrame, mask: pd.Series, label: str) -> dict:
    """Compute win rate and mean return for a filtered subset."""
    sub = events[mask]
    n = len(sub)
    if n == 0:
        return {"label": label, "n": 0, "wr": 0.0, "mean_ret": 0.0, "median_ret": 0.0}
    wr = float((sub['post_20d'] > 0).mean())
    mean_ret = float(sub['post_20d'].mean())
    median_ret = float(sub['post_20d'].median())
    return {
        "label": label,
        "n": n,
        "wr": round(wr, 4),
        "mean_ret": round(mean_ret, 4),
        "median_ret": round(median_ret, 4),
    }


def print_period(events: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp,
                 period_label: str):
    ev = events[(events['date'] >= start) & (events['date'] <= end)].copy()
    print(f"\n{'='*65}")
    print(f"Period: {period_label} (n_raw={len(ev)})")
    print(f"{'='*65}")
    print(f"{'Filter':<45} {'n':>4} {'WR':>7} {'MeanRet':>9} {'MedianRet':>10}")
    print("-" * 65)

    results = {}

    # Variant A: H174 baseline
    mask_a = (ev['finbert_score'] >= SCORE_MIN) & (ev['tone_surprise'] >= TONE_SURP)
    r = evaluate_filter(ev, mask_a, "A: H174 baseline (score+tone)")
    results['A'] = r
    print(f"A: H174 baseline{'':29} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Variant B: H174 + EPS beat
    mask_b = mask_a & (ev['eps_surprise_pct'] > 0)
    r = evaluate_filter(ev, mask_b, "B: H174 + EPS beat (>0%)")
    results['B'] = r
    print(f"B: H174 + EPS beat (>0%){'':21} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Variant C: H174 + EPS strong beat
    mask_c = mask_a & (ev['eps_surprise_pct'] > 3)
    r = evaluate_filter(ev, mask_c, "C: H174 + EPS strong beat (>3%)")
    results['C'] = r
    print(f"C: H174 + EPS strong beat (>3%){'':14} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Variant D: H174 + pre-momentum filter
    mask_d = mask_a & (ev['pre_21d'] < 0.10)
    r = evaluate_filter(ev, mask_d, "D: H174 + pre-mom <+10%")
    results['D'] = r
    print(f"D: H174 + pre-mom <+10%{'':22} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Variant E: H174 + EPS beat + pre-momentum
    mask_e = mask_a & (ev['eps_surprise_pct'] > 0) & (ev['pre_21d'] < 0.10)
    r = evaluate_filter(ev, mask_e, "E: H174 + EPS beat + pre-mom<10%")
    results['E'] = r
    print(f"E: H174 + EPS beat + pre-mom<10%{'':12} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Variant F: H174 + strong beat + pre-momentum
    mask_f = mask_a & (ev['eps_surprise_pct'] > 3) & (ev['pre_21d'] < 0.10)
    r = evaluate_filter(ev, mask_f, "F: H174 + strong beat + pre-mom<10%")
    results['F'] = r
    print(f"F: strong beat + pre-mom<10%{'':16} {r['n']:>4} {r['wr']:>6.1%} {r['mean_ret']:>9.1%} {r['median_ret']:>9.1%}")

    # Also show baseline for all events in period
    mask_all = pd.Series([True] * len(ev), index=ev.index)
    r_all = evaluate_filter(ev, mask_all, "Baseline (all events)")
    print(f"\n{'All raw events (no filter)':<45} {r_all['n']:>4} {r_all['wr']:>6.1%} {r_all['mean_ret']:>9.1%} {r_all['median_ret']:>9.1%}")

    return results


def main():
    print("H317 — Multi-Modal PEAD: FinBERT + EPS Surprise + Pre-Momentum")
    print("=" * 65)

    # Load FinBERT scores
    print("\nLoading H163 FinBERT scores…")
    scores = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    scores = scores.dropna(subset=['finbert_score'])
    scores['date'] = pd.to_datetime(scores['date'])
    print(f"  {len(scores)} events loaded")

    # Compute tone surprise
    print("Computing 8-K tone surprise…")
    scores_surp = compute_tone_surprise(scores)
    print(f"  {scores_surp['tone_surprise'].notna().sum()} events with computable tone surprise")

    # Load daily prices
    print("\nLoading daily OHLCV prices…")
    prices = load_daily_prices()
    print(f"  {len(prices)} tickers loaded")

    # Fetch EPS surprises
    print("\nFetching EPS surprise data…")
    for t in UNIVERSE:
        _ = fetch_earnings_surprises(t)
    print("  Done")

    # Build outcome table
    print("\nBuilding event outcome table…")
    events = compute_outcomes(scores_surp, prices)
    print(f"  {len(events)} events with outcomes")
    n_with_eps = events['eps_surprise_pct'].notna().sum()
    print(f"  {n_with_eps} events with EPS surprise data ({n_with_eps/len(events):.0%})")

    # Filter: require gap >= 3% (same as H174 entry condition)
    events_gap = events[events['gap_pct'] >= GAP_THRESH].copy()
    print(f"  {len(events_gap)} events with gap >= {GAP_THRESH:.0%}")

    # IS results
    is_results = print_period(events_gap, IS_START, IS_END, "IS 2021-2023")

    # OOS results
    oos_results = print_period(events_gap, OOS_START, OOS_END, "OOS 2024-2026")

    # Gate check
    print("\n" + "=" * 65)
    print("GATE CHECK: WR > 70% AND MeanRet > 4% AND n >= 20 (OOS)")
    print("=" * 65)
    for v, r in oos_results.items():
        gate = r['n'] >= 20 and r['wr'] > 0.70 and r['mean_ret'] > 0.04
        print(f"  {r['label'][:45]:<45}: n={r['n']:>3}, WR={r['wr']:.1%}, MeanRet={r['mean_ret']:.1%} → {'✓ PASS' if gate else '✗ FAIL'}")

    # Save results
    out = {
        "hypothesis": "H317",
        "title": "Multi-Modal PEAD: FinBERT + EPS Analyst Surprise + Pre-Announcement Momentum",
        "gate": "OOS WR > 70% AND MeanRet > 4% AND n >= 20",
        "is_period": "2021-2023",
        "oos_period": "2024-2026",
        "is_results": is_results,
        "oos_results": oos_results,
    }
    with open(RESULT_DIR / "h317_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to backtesting/results/h317_results.json")

    # Print pre-momentum distribution for context
    print("\n--- Pre-Announcement 21d Momentum Distribution (OOS, H174 filtered) ---")
    ev_oos = events_gap[(events_gap['date'] >= OOS_START) & (events_gap['date'] <= OOS_END)]
    mask_a_oos = (ev_oos['finbert_score'] >= SCORE_MIN) & (ev_oos['tone_surprise'] >= TONE_SURP)
    h174_oos = ev_oos[mask_a_oos]
    if len(h174_oos) > 0:
        print(f"  Mean pre-21d: {h174_oos['pre_21d'].mean():.1%}")
        print(f"  Pct with pre_21d > 10%: {(h174_oos['pre_21d'] > 0.10).mean():.0%}")
        print(f"  Pct with EPS beat (>0%): {(h174_oos['eps_surprise_pct'] > 0).mean():.0%}")
        print(f"  Pct with EPS beat data available: {h174_oos['eps_surprise_pct'].notna().mean():.0%}")


if __name__ == "__main__":
    main()
