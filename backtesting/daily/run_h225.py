"""
H225 — PEAD-NLP: GPT-4o-mini Scoring vs FinBERT (H174 upgrade)
=================================================================
Hypothesis: GPT-4o-mini scores earnings 8-K press releases more accurately
than FinBERT, improving OOS directional accuracy for the PEAD-NLP strategy.

Source: "Enhancing Post Earnings Announcement Drift Measurement with Large
Language Models" (ACL FinNLP 2025 workshop, aclanthology.org/2025.finnlp-2.13)
Finding: FinBERT achieves 57.6-58.3% directional accuracy; GPT-4 class models
significantly outperform on soft information extraction.

Baseline (H174): OOS WR=81.8%, MeanRet=6.89%, n=22 (score≥0.18 + surprise≥0.02)
Confirm: OOS WR > 83% OR MeanRet > 7.5% (meaningful improvement over H174)
Fallback confirm: same WR but larger n (better recall)

Method:
1. Load all cached h163_8k_TICKER_DATE.txt files (195 events with text)
2. Score each with GPT-4o-mini using structured prompt → score ∈ [-1, +1]
3. Cache GPT scores to h225_gpt_scores.parquet
4. Apply same surprise calculation as H174 (score_t - mean prior 4q)
5. Apply dual filter: gpt_score >= thresh AND surprise >= thresh
6. Compare OOS performance vs H174 baseline

IS: 2019–2023, OOS: 2024–present
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import re
import time
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

WORKSPACE   = Path(__file__).resolve().parent.parent.parent
CACHE_DIR   = WORKSPACE / "backtesting" / "cache"
RESULT_DIR  = WORKSPACE / "backtesting" / "results"
GPT_CACHE   = CACHE_DIR / "h225_gpt_scores.parquet"

IS_END      = pd.Timestamp("2023-12-31")
OOS_START   = pd.Timestamp("2024-01-01")
GAP_THRESH  = 0.03
LOOKBACK_Q  = 4
MIN_PRIOR   = 2

SCORE_PROMPT = """You are a financial analyst evaluating an earnings press release.
Read the text and score the overall earnings quality and management tone.

Return a JSON object with exactly one key: "score" — a float between -1.0 and +1.0 where:
  +1.0 = exceptional results: strong beats on revenue and EPS, confident raised guidance, optimistic language
  +0.5 = solid beat: above expectations, positive outlook
   0.0 = in-line: met expectations, neutral tone
  -0.5 = miss: below expectations, cautious guidance
  -1.0 = serious miss: significant revenue/EPS shortfall, negative guidance or withdrawn outlook

Respond with ONLY the JSON, no explanation. Example: {"score": 0.72}

Earnings press release text:
"""


def score_with_gpt(text: str, client: "OpenAI") -> float:
    """Call GPT-4o-mini and return a score in [-1, +1]. Returns NaN on failure."""
    try:
        # Truncate to ~3000 tokens to keep costs low
        truncated = text[:12000]
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": SCORE_PROMPT + truncated}
            ],
            max_tokens=20,
            temperature=0,
        )
        raw = resp.choices[0].message.content.strip()
        # Parse JSON
        data = json.loads(raw)
        score = float(data["score"])
        return max(-1.0, min(1.0, score))
    except Exception as e:
        # Try regex fallback
        try:
            m = re.search(r"-?\d+\.?\d*", raw)
            if m:
                return max(-1.0, min(1.0, float(m.group())))
        except Exception:
            pass
        print(f"    GPT parse error: {e} | raw: {repr(raw[:100])}")
        return float("nan")


def load_or_build_gpt_scores() -> pd.DataFrame:
    """
    Load GPT scores from cache, or build by calling GPT-4o-mini for
    each cached 8-K text file. Returns DataFrame with ticker/date/gpt_score.
    """
    if GPT_CACHE.exists():
        df = pd.read_parquet(GPT_CACHE)
        print(f"  Loaded {len(df)} cached GPT scores from {GPT_CACHE.name}")
        return df

    if not HAS_OPENAI:
        print("  ERROR: openai package not installed. Run: pip install openai")
        return pd.DataFrame(columns=["ticker", "date", "gpt_score"])

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("  ERROR: OPENAI_API_KEY not set")
        return pd.DataFrame(columns=["ticker", "date", "gpt_score"])

    client = OpenAI(api_key=api_key)

    # Find all cached 8-K text files
    txt_files = sorted(CACHE_DIR.glob("h163_8k_*.txt"))
    print(f"  Found {len(txt_files)} cached 8-K texts to score")

    records = []
    for i, fp in enumerate(txt_files):
        # Parse ticker and date from filename: h163_8k_TICKER_YYYY-MM-DD.txt
        name = fp.stem  # h163_8k_AAPL_2024-05-03
        parts = name.split("_")
        # parts: ['h163', '8k', 'TICKER', 'YYYY-MM-DD']
        # ticker is always at index 2; date is always the last element
        ticker = parts[2]
        date_str = parts[-1]

        try:
            date = pd.Timestamp(date_str)
        except Exception:
            print(f"  Skipping {fp.name}: can't parse date '{date_str}'")
            continue

        text = fp.read_text(encoding="utf-8", errors="ignore")
        if len(text) < 100:
            print(f"  Skipping {fp.name}: text too short ({len(text)} chars)")
            continue

        score = score_with_gpt(text, client)
        records.append({"ticker": ticker, "date": date, "gpt_score": score})

        if (i + 1) % 10 == 0:
            print(f"  Scored {i + 1}/{len(txt_files)}…")
            # Save incremental progress
            pd.DataFrame(records).to_parquet(GPT_CACHE)

        # Rate limit: 60 req/min for GPT-4o-mini tier
        time.sleep(0.5)

    df = pd.DataFrame(records)
    df.to_parquet(GPT_CACHE)
    print(f"  GPT scoring complete: {len(df)} events. Saved to {GPT_CACHE.name}")
    return df


def load_ohlcv():
    """Reuse H163 cached OHLCV data."""
    result = {}
    for fp in CACHE_DIR.glob("h163_*_ohlcv_*.parquet"):
        ticker = fp.stem.split("_")[1]
        df = pd.read_parquet(fp)
        df.columns = [c.lower() for c in df.columns]
        if "open" in df.columns and "close" in df.columns:
            result[ticker] = df[["open", "close"]]
    return result


def get_earnings_dates(ticker):
    cache_path = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)["date"].tolist()
    return []


def find_gap_events(ohlcv):
    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, row in df[gap_pct > GAP_THRESH].iterrows():
            events.append({"ticker": t, "date": idx, "gap_pct": gap_pct[idx]})
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def compute_return(ticker, entry_date, ohlcv, hold=20):
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = future.iloc[0]["open"]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


def compute_surprise(ticker, event_date, score_df, score_col):
    ticker_scores = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] < event_date) &
        score_df[score_col].notna()
    ].sort_values("date")

    if len(ticker_scores) < MIN_PRIOR:
        return float("nan")

    baseline = ticker_scores.tail(LOOKBACK_Q)[score_col].mean()
    current_row = score_df[
        (score_df["ticker"] == ticker) &
        (score_df["date"] == event_date) &
        score_df[score_col].notna()
    ]
    if current_row.empty:
        return float("nan")
    return current_row.iloc[0][score_col] - baseline


def print_sweep(label, data, thresholds, score_col="score", surp_col="surprise",
                score_thresh=None, surp_thresh=None):
    """Print threshold sweep. If score_thresh and surp_thresh are fixed, show dual filter."""
    print(f"\n  {label}")
    if score_thresh is not None:
        # Dual filter
        filtered = data[(data[score_col] >= score_thresh) & (data[surp_col] >= surp_thresh)]
        n = len(filtered)
        if n == 0:
            print(f"  No events at score≥{score_thresh} + surprise≥{surp_thresh}")
            return []
        wr = (filtered["ret"] > 0).mean()
        mr = filtered["ret"].mean()
        confirmed = "CONFIRM" if (wr >= 0.83 or mr >= 0.075) else ""
        print(f"  score≥{score_thresh} + surprise≥{surp_thresh}: n={n}, WR={wr*100:.1f}%, MeanRet={mr*100:.2f}% {confirmed}")
        return [{"score_thresh": score_thresh, "surp_thresh": surp_thresh, "n": n, "wr": wr, "mr": mr}]
    else:
        # Single score sweep
        print(f"  {'Thresh':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
        print("  " + "-" * 50)
        results = []
        if len(data) == 0 or score_col not in data.columns:
            print(f"  (no data)")
            return results
        for thresh in thresholds:
            filtered = data[data[score_col] >= thresh]
            if len(filtered) == 0:
                continue
            wr = (filtered["ret"] > 0).mean()
            mr = filtered["ret"].mean()
            n = len(filtered)
            confirmed = "CONFIRM" if (wr >= 0.83 or mr >= 0.075) else ""
            results.append({"thresh": thresh, "n": n, "wr": wr, "mr": mr})
            print(f"  {thresh:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")
        return results


def main():
    print("=" * 62)
    print("  H225 — PEAD-NLP: GPT-4o-mini vs FinBERT")
    print("  Baseline: H174 OOS WR=81.8%, MeanRet=6.89%, n=22")
    print("  Confirm: OOS WR > 83% OR MeanRet > 7.5%")
    print("=" * 62)

    # ── [1] GPT scores ────────────────────────────────────────────────
    print("\n[1/5] Loading/building GPT-4o-mini scores…")
    gpt_df = load_or_build_gpt_scores()
    gpt_df["date"] = pd.to_datetime(gpt_df["date"])
    valid_gpt = gpt_df["gpt_score"].notna().sum()
    print(f"  Total: {len(gpt_df)} events, {valid_gpt} with valid GPT scores")

    # Also load FinBERT for comparison
    finbert_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    finbert_df["date"] = pd.to_datetime(finbert_df["date"])

    # ── [2] OHLCV ─────────────────────────────────────────────────────
    print("\n[2/5] Loading OHLCV data…")
    ohlcv = load_ohlcv()
    print(f"  Loaded {len(ohlcv)} tickers from cache")

    # ── [3] Gap events + earnings filter ─────────────────────────────
    print("\n[3/5] Finding earnings-confirmed gap-up events…")
    all_events = find_gap_events(ohlcv)
    earnings_by_ticker = {}
    for t in gpt_df["ticker"].unique():
        earnings_by_ticker[t] = get_earnings_dates(t)

    def is_earnings_gap(ticker, gap_date, window=3):
        for ed in earnings_by_ticker.get(ticker, []):
            if abs((gap_date - ed).days) <= window:
                return True
        return False

    conf_events = all_events[
        all_events.apply(lambda r: is_earnings_gap(r["ticker"], r["date"]), axis=1)
    ].copy()
    is_ev  = conf_events[conf_events["date"] <= IS_END]
    oos_ev = conf_events[conf_events["date"] >= OOS_START]
    print(f"  Earnings gap events — IS: {len(is_ev)}, OOS: {len(oos_ev)}")

    # ── [4] Attach scores and compute returns ─────────────────────────
    print("\n[4/5] Attaching GPT scores, computing surprise and returns…")

    def build_event_df(events, score_df, score_col):
        rows = []
        for _, ev in events.iterrows():
            t, dt = ev["ticker"], ev["date"]
            # Match GPT score to event date (within 1 day tolerance)
            nearby = score_df[
                (score_df["ticker"] == t) &
                (abs((score_df["date"] - dt).dt.days) <= 1) &
                score_df[score_col].notna()
            ]
            if nearby.empty:
                continue
            sc = nearby.iloc[0][score_col]
            surp = compute_surprise(t, nearby.iloc[0]["date"], score_df, score_col)
            ret = compute_return(t, dt, ohlcv, hold=20)
            if ret is None:
                continue
            rows.append({
                "ticker": t, "date": dt,
                "score": sc, "surprise": surp, "ret": ret,
                "gap_pct": ev["gap_pct"],
            })
        return pd.DataFrame(rows)

    is_gpt  = build_event_df(is_ev,  gpt_df,     "gpt_score")
    oos_gpt = build_event_df(oos_ev, gpt_df,     "gpt_score")
    is_fb   = build_event_df(is_ev,  finbert_df, "finbert_score")
    oos_fb  = build_event_df(oos_ev, finbert_df, "finbert_score")

    print(f"  GPT events matched — IS: {len(is_gpt)}, OOS: {len(oos_gpt)}")
    print(f"  FinBERT events matched — IS: {len(is_fb)}, OOS: {len(oos_fb)}")

    # ── [5] Threshold sweep + comparison ──────────────────────────────
    print("\n[5/5] Results")

    print("\n  ── GPT-4o-mini score distribution (OOS) ──")
    if len(oos_gpt) > 0:
        print(f"  mean={oos_gpt['score'].mean():.3f}  "
              f"std={oos_gpt['score'].std():.3f}  "
              f"median={oos_gpt['score'].median():.3f}  "
              f"min={oos_gpt['score'].min():.3f}  "
              f"max={oos_gpt['score'].max():.3f}")

    print("\n  ── IS Results: GPT score sweep ──")
    is_sweep_gpt = print_sweep("IS GPT", is_gpt,
                                [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30])

    print("\n  ── OOS Results: GPT score sweep ──")
    oos_sweep_gpt = print_sweep("OOS GPT", oos_gpt,
                                 [0.05, 0.10, 0.15, 0.18, 0.20, 0.25, 0.30])

    print("\n  ── IS Results: GPT dual filter (score≥0.18 + surprise≥0.02) ──")
    is_dual_gpt = print_sweep("IS GPT dual", is_gpt,
                               thresholds=None, score_thresh=0.18, surp_thresh=0.02)

    print("\n  ── OOS Results: GPT dual filter (score≥0.18 + surprise≥0.02) ──")
    oos_dual_gpt = print_sweep("OOS GPT dual", oos_gpt,
                                thresholds=None, score_thresh=0.18, surp_thresh=0.02)

    print("\n  ── OOS: H174 FinBERT baseline (score≥0.18 + surprise≥0.02) ──")
    oos_dual_fb = print_sweep("OOS FinBERT dual (H174)", oos_fb,
                               thresholds=None, score_thresh=0.18, surp_thresh=0.02)

    # ── Find best GPT dual threshold ─────────────────────────────────
    print("\n  ── OOS: GPT dual filter threshold grid ──")
    print(f"  {'ScoreT':>8} {'SurpT':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 58)
    best_result = None
    for st in [0.10, 0.15, 0.18, 0.20, 0.25]:
        for su in [0.00, 0.01, 0.02, 0.03]:
            if len(oos_gpt) == 0:
                continue
            filtered = oos_gpt[(oos_gpt["score"] >= st) & (oos_gpt["surprise"] >= su)]
            n = len(filtered)
            if n < 5:
                continue
            wr = (filtered["ret"] > 0).mean()
            mr = filtered["ret"].mean()
            confirmed = "CONFIRM" if (wr >= 0.83 or mr >= 0.075) else ""
            print(f"  {st:>8.2f} {su:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")
            if confirmed and (best_result is None or wr > best_result["wr"]):
                best_result = {"score_thresh": st, "surp_thresh": su,
                               "n": n, "wr": wr, "mr": mr}

    # ── Final verdict ─────────────────────────────────────────────────
    print("\n" + "=" * 62)
    h174_oos = oos_dual_fb[0] if oos_dual_fb else {"wr": 0.818, "mr": 0.0689, "n": 22}
    h225_oos = oos_dual_gpt[0] if oos_dual_gpt else None

    if h225_oos:
        wr_delta = h225_oos["wr"] - h174_oos["wr"]
        mr_delta = h225_oos["mr"] - h174_oos["mr"]
        print(f"\n  H174 baseline (FinBERT): WR={h174_oos['wr']*100:.1f}%  "
              f"MeanRet={h174_oos['mr']*100:.2f}%  n={h174_oos['n']}")
        print(f"  H225 result  (GPT-mini): WR={h225_oos['wr']*100:.1f}%  "
              f"MeanRet={h225_oos['mr']*100:.2f}%  n={h225_oos['n']}")
        print(f"  Delta: WR {wr_delta*100:+.1f}pp  MeanRet {mr_delta*100:+.2f}pp  "
              f"n {h225_oos['n'] - h174_oos['n']:+d}")
        confirmed = (h225_oos["wr"] >= 0.83 or h225_oos["mr"] >= 0.075)
        print(f"\n  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    else:
        print("\n  VERDICT: NOT CONFIRMED (insufficient OOS events)")

    # ── Save results ─────────────────────────────────────────────────
    results = {
        "hypothesis": "H225",
        "date_run": datetime.now().isoformat(),
        "model": "gpt-4o-mini",
        "baseline": "H174",
        "h174_oos": h174_oos,
        "h225_oos_dual_0.18_0.02": h225_oos,
        "best_threshold": best_result,
        "n_gpt_scores": int(valid_gpt),
        "n_8k_texts": 195,
    }
    import json
    (RESULT_DIR / "h225_results.json").write_text(
        json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved → backtesting/results/h225_results.json")


if __name__ == "__main__":
    main()
