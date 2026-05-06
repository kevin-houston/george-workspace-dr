"""
H176 — PEAD-NLP: GPT-4o-mini Relative Sentiment (H173 Revival via FinDPO Proxy)
=================================================================================
H173 NOT CONFIRMED: FinBERT scalar surprise (score_t - mean_prior) OOS WR≈66.7%, MeanRet=4.08%
H174 CONFIRMED: H163 score ≥ 0.18 + surprise ≥ 0.02 → WR=81.8%, MeanRet=6.89%

Source: arXiv 2507.18417 (FinDPO, Jul 2025) — DPO-fine-tuned LLM achieves Sharpe 2.0,
67% annual return on sentiment-based trading (11% accuracy improvement vs supervised FinBERT).

Full DPO fine-tuning requires a labeled preference dataset. This script tests a simpler proxy:
use GPT-4o-mini with a calibrated comparison prompt to mimic DPO's relative-strength signal.
Instead of scalar subtraction (H173), the LLM reads both transcripts holistically and decides
whether management tone IMPROVED vs the prior quarter — the 'surprise' as an analyst would read it.

Filter: GPT4oMini = MORE_POSITIVE AND H163 FinBERT score >= score_thresh
Compare: H173 (scalar surprise, NOT CONFIRMED), H174 (dual filter, CONFIRMED)

PREREQUISITE: H168 transcripts must be ≥ 50% cached.
Cost: ~203 events × 2 transcripts × 8k tokens ≈ 3.2M tokens ≈ $0.48 at $0.15/1M tokens.

Confirm criteria: OOS WR ≥ 68%, MeanRet ≥ 5.5%, n ≥ 15
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import re
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
TRANSCRIPT_DIR = CACHE_DIR / "h168_transcripts"
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

IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")
GAP_THRESH = 0.03
LOOKBACK_Q = 4
MIN_PRIOR  = 2
COVERAGE_THRESHOLD = 0.50   # exit if H168 < 50% cached

GPT_MODEL     = "gpt-4o-mini"
MAX_TOKENS    = 512          # plenty for a 3-label classification
TRANSCRIPT_MAX_CHARS = 12_000  # ~3k tokens per transcript chunk


# ── coverage check ─────────────────────────────────────────────────────────────

def check_coverage() -> float:
    """Return fraction of expected ticker×quarter slots that are cached."""
    if not TRANSCRIPT_DIR.exists():
        return 0.0
    files = list(TRANSCRIPT_DIR.glob("*.json"))
    n_cached = len(files)
    # 31 tickers × 28 quarters (2019Q1–2026Q4) = 868 expected
    n_expected = len(UNIVERSE) * 28
    return n_cached / n_expected


# ── transcript helpers ─────────────────────────────────────────────────────────

def date_to_qkey(dt: pd.Timestamp) -> str:
    """Convert a date to 'YYYYQn' key matching h168_transcripts filename format."""
    m = dt.month
    q = (m - 1) // 3 + 1
    return f"{dt.year}Q{q}"


def prior_qkey(qkey: str) -> str:
    """Return the quarter key one quarter before the given key."""
    year = int(qkey[:4])
    q = int(qkey[5])
    if q == 1:
        return f"{year - 1}Q4"
    return f"{year}Q{q - 1}"


def load_transcript(ticker: str, qkey: str) -> list | None:
    """Load transcript segments list from cache, or None if not found."""
    path = TRANSCRIPT_DIR / f"{ticker}_{qkey}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def segments_to_text(segments: list, max_chars: int = TRANSCRIPT_MAX_CHARS) -> str:
    """Flatten speaker segments to a single string, truncated to max_chars."""
    parts = []
    for seg in segments:
        speaker = seg.get("speaker", "")
        content = seg.get("content", "").strip()
        if content:
            parts.append(f"{speaker}: {content}" if speaker else content)
    full = " ".join(parts)
    return full[:max_chars]


# ── GPT-4o-mini comparison ─────────────────────────────────────────────────────

_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _openai_client


def gpt_compare_transcripts(current_text: str, prior_text: str) -> str:
    """
    Ask GPT-4o-mini whether current quarter sentiment is MORE_POSITIVE, SIMILAR,
    or MORE_NEGATIVE vs prior quarter.
    Returns one of: 'MORE_POSITIVE', 'SIMILAR', 'MORE_NEGATIVE', or 'ERROR'.
    """
    prompt = (
        "You are a financial analyst evaluating earnings call sentiment.\n\n"
        "Below are two earnings call transcripts for the SAME company on consecutive quarters.\n\n"
        "PRIOR QUARTER TRANSCRIPT:\n"
        f"{prior_text}\n\n"
        "CURRENT QUARTER TRANSCRIPT:\n"
        f"{current_text}\n\n"
        "Compare the overall management tone and sentiment of the CURRENT QUARTER vs the PRIOR QUARTER.\n"
        "Consider: confidence about future outlook, language around revenue/earnings growth, "
        "acknowledgment of challenges, and forward guidance language.\n\n"
        "Answer with EXACTLY ONE of these three labels and nothing else:\n"
        "MORE_POSITIVE\n"
        "SIMILAR\n"
        "MORE_NEGATIVE"
    )
    try:
        client = get_openai_client()
        resp = client.chat.completions.create(
            model=GPT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=0.0,
        )
        raw = resp.choices[0].message.content.strip().upper()
        # Accept partial matches for robustness
        if "MORE_POSITIVE" in raw or raw.startswith("MORE POS"):
            return "MORE_POSITIVE"
        if "MORE_NEGATIVE" in raw or raw.startswith("MORE NEG"):
            return "MORE_NEGATIVE"
        if "SIMILAR" in raw:
            return "SIMILAR"
        return "ERROR"
    except Exception as e:
        print(f"    GPT error: {e}")
        return "ERROR"


# ── OHLCV + earnings helpers ───────────────────────────────────────────────────

def load_ohlcv():
    result = {}
    start, end = "2019-01-01", "2026-04-30"
    to_dl = []
    for t in UNIVERSE:
        for pfx in [f"h{i:03d}" for i in range(155, 177)]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_{start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        result[t] = df[["open", "close"]]
                        break
            if t in result:
                break
        if t not in result:
            to_dl.append(t)
    if to_dl:
        print(f"  Downloading {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    df = df.dropna()
                    if len(df) > 100:
                        df.to_parquet(
                            CACHE_DIR / f"h176_{t}_ohlcv_{start}_{end}.parquet")
                        result[t] = df
                except Exception:
                    pass
    return result


def get_earnings_dates(ticker):
    cache_path = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)["date"].tolist()
    try:
        tk = yf.Ticker(ticker)
        df = tk.earnings_dates
        if df is None or df.empty:
            return []
        df = df.copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
        df = df.dropna(subset=["Reported EPS"])
        dates = sorted(df.index.tolist())
        pd.DataFrame({"date": dates}).to_parquet(cache_path)
        return dates
    except Exception:
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


# ── GPT label scoring with cache ───────────────────────────────────────────────

def load_gpt_cache() -> pd.DataFrame:
    path = CACHE_DIR / "h176_gpt_comparisons.parquet"
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame(columns=["ticker", "date", "gpt_label"])


def save_gpt_cache(df: pd.DataFrame):
    path = CACHE_DIR / "h176_gpt_comparisons.parquet"
    df.to_parquet(path, index=False)


def get_gpt_label(ticker: str, event_date: pd.Timestamp,
                  gpt_cache: pd.DataFrame) -> str:
    """Get cached GPT label or compute it. Requires current + prior quarter transcript."""
    # Check cache
    cached = gpt_cache[
        (gpt_cache["ticker"] == ticker) &
        (gpt_cache["date"] == event_date)
    ]
    if not cached.empty:
        return cached.iloc[0]["gpt_label"]

    # Need transcripts for current and prior quarter
    cur_qkey = date_to_qkey(event_date)
    prv_qkey = prior_qkey(cur_qkey)

    cur_segs = load_transcript(ticker, cur_qkey)
    prv_segs = load_transcript(ticker, prv_qkey)

    if cur_segs is None or prv_segs is None:
        return "MISSING"

    cur_text = segments_to_text(cur_segs)
    prv_text = segments_to_text(prv_segs)

    label = gpt_compare_transcripts(cur_text, prv_text)

    # Append to cache
    new_row = pd.DataFrame([{
        "ticker": ticker, "date": event_date, "gpt_label": label
    }])
    updated = pd.concat([gpt_cache, new_row], ignore_index=True)
    save_gpt_cache(updated)
    # Update in-place reference for caller
    gpt_cache.loc[len(gpt_cache)] = {"ticker": ticker, "date": event_date,
                                      "gpt_label": label}
    return label


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 66)
    print("  H176 — PEAD-NLP: GPT-4o-mini Relative Sentiment (FinDPO Proxy)")
    print("=" * 66)

    # Prerequisites check
    coverage = check_coverage()
    n_cached = len(list(TRANSCRIPT_DIR.glob("*.json"))) if TRANSCRIPT_DIR.exists() else 0
    n_expected = len(UNIVERSE) * 28
    print(f"\n[0/6] H168 transcript coverage: {n_cached}/{n_expected} = {coverage*100:.1f}%")

    if coverage < COVERAGE_THRESHOLD:
        print(f"\n  PREREQUISITE NOT MET: H168 coverage {coverage*100:.1f}% < {COVERAGE_THRESHOLD*100:.0f}%")
        print("  H176 requires ≥50% of earnings call transcripts to be cached.")
        print("  H168 download pass-5 is scheduled; re-run after transcripts are populated.")
        print(f"\n  Current cache: {n_cached} files in {TRANSCRIPT_DIR}")
        print("  Exiting early — no API charges incurred.\n")

        # Write placeholder result
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        out = [
            "H176 — PEAD-NLP: GPT-4o-mini Relative Sentiment (FinDPO Proxy)",
            f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "",
            "STATUS: PREREQUISITE NOT MET",
            f"H168 transcript coverage: {n_cached}/{n_expected} = {coverage*100:.1f}%",
            "Required: ≥50% coverage before running GPT comparisons.",
            "Re-run after H168 download passes complete.",
        ]
        (RESULT_DIR / "h176_gpt_relative_sentiment.txt").write_text("\n".join(out))
        return

    print(f"  Coverage OK ({coverage*100:.1f}%) — proceeding with backtest")

    print("\n[1/6] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  Loaded: {len(ohlcv)} tickers")

    print("\n[2/6] Finding earnings-confirmed gap-up events…")
    all_events = find_gap_events(ohlcv)
    earnings_by_ticker = {t: get_earnings_dates(t) for t in UNIVERSE}

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
    print(f"  IS={len(is_ev)}  OOS={len(oos_ev)}")

    print("\n[3/6] Loading H163 FinBERT scores…")
    score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
    score_df["date"] = pd.to_datetime(score_df["date"])
    print(f"  Loaded {len(score_df)} score records")

    print("\n[4/6] Running GPT-4o-mini comparisons (current vs prior quarter)…")
    gpt_cache = load_gpt_cache()
    n_cache_hits = 0
    n_api_calls  = 0
    n_missing    = 0

    def enrich(events):
        nonlocal n_cache_hits, n_api_calls, n_missing
        rows = []
        for _, ev in events.iterrows():
            ret = compute_return(ev["ticker"], ev["date"], ohlcv, hold=20)
            if ret is None:
                continue

            # FinBERT score
            score_row = score_df[
                (score_df["ticker"] == ev["ticker"]) &
                (score_df["date"] == ev["date"])
            ]
            score = score_row.iloc[0]["finbert_score"] \
                if not score_row.empty else float("nan")

            # GPT label
            cached = gpt_cache[
                (gpt_cache["ticker"] == ev["ticker"]) &
                (gpt_cache["date"] == ev["date"])
            ]
            if not cached.empty:
                gpt_label = cached.iloc[0]["gpt_label"]
                n_cache_hits += 1
            else:
                gpt_label = get_gpt_label(ev["ticker"], ev["date"], gpt_cache)
                if gpt_label not in ("MISSING", "ERROR"):
                    n_api_calls += 1
                    if n_api_calls % 10 == 0:
                        print(f"    GPT calls: {n_api_calls}")
                else:
                    n_missing += 1

            rows.append({
                "ticker": ev["ticker"], "date": ev["date"],
                "ret": ret, "score": score, "gpt_label": gpt_label,
            })
        return pd.DataFrame(rows)

    is_df  = enrich(is_ev)
    oos_df = enrich(oos_ev)

    print(f"  Cache hits: {n_cache_hits}  |  New API calls: {n_api_calls}  "
          f"|  Missing transcripts: {n_missing}")

    # Only events where GPT gave a usable label AND finbert score is available
    is_valid  = is_df[
        (is_df["gpt_label"] == "MORE_POSITIVE") |
        (is_df["gpt_label"].isin(["SIMILAR", "MORE_NEGATIVE"]))
    ].dropna(subset=["score"])
    oos_valid = oos_df[
        (oos_df["gpt_label"] == "MORE_POSITIVE") |
        (oos_df["gpt_label"].isin(["SIMILAR", "MORE_NEGATIVE"]))
    ].dropna(subset=["score"])

    print(f"  IS with valid GPT label + score: {len(is_valid)} / {len(is_df)}")
    print(f"  OOS with valid GPT label + score: {len(oos_valid)} / {len(oos_df)}")

    print("\n[5/6] Sweep: GPT=MORE_POSITIVE AND score ≥ thresh…")
    print(f"\n  Baseline OOS (all {len(oos_df)}): "
          f"WR={(oos_df['ret']>0).mean()*100:.1f}%, "
          f"MeanRet={oos_df['ret'].mean()*100:.2f}%")

    gpt_pos_oos = oos_valid[oos_valid["gpt_label"] == "MORE_POSITIVE"]
    gpt_pos_is  = is_valid[is_valid["gpt_label"] == "MORE_POSITIVE"]

    print(f"\n  GPT=MORE_POSITIVE events: OOS={len(gpt_pos_oos)}  IS={len(gpt_pos_is)}")
    if len(gpt_pos_oos) > 0:
        print(f"  GPT=MORE_POSITIVE alone: "
              f"OOS WR={(gpt_pos_oos['ret']>0).mean()*100:.1f}%, "
              f"MeanRet={gpt_pos_oos['ret'].mean()*100:.2f}%")

    score_thresholds = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20]
    print(f"\n  {'ScoreT':>8} {'n':>5} {'WR%':>7} {'MeanRet%':>10} {'Confirm':>10}")
    print("  " + "-" * 50)

    all_confirmed = []
    for st in score_thresholds:
        filtered = gpt_pos_oos[gpt_pos_oos["score"] >= st]
        if len(filtered) == 0:
            continue
        wr = (filtered["ret"] > 0).mean()
        mr = filtered["ret"].mean()
        n  = len(filtered)
        confirmed = "CONFIRM" if (wr >= 0.68 and mr >= 0.055 and n >= 15) else ""
        if confirmed or n >= 5:
            print(f"  {st:>8.2f} {n:>5} {wr*100:>7.1f} {mr*100:>10.2f} {confirmed:>10}")
        if confirmed:
            all_confirmed.append({
                "score_thresh": st, "n": n, "wr": wr, "mr": mr
            })

    # H173 comparison: GPT vs scalar surprise
    print("\n  Comparison vs H173 (scalar surprise ≥ 0.02, NOT CONFIRMED):")
    print("  H173 OOS: WR≈66.7%, MeanRet≈4.08% (NOT CONFIRMED)")
    print("  H174 reference: score≥0.18 + surprise≥0.02: WR=81.8%, MeanRet=6.89%")

    print("\n[6/6] IS check for best confirmed threshold…")
    if all_confirmed:
        best_st = all_confirmed[0]["score_thresh"]
        is_fil = gpt_pos_is[gpt_pos_is["score"] >= best_st]
        if len(is_fil) > 0:
            print(f"  IS GPT=MORE_POSITIVE + score≥{best_st:.2f}: "
                  f"n={len(is_fil)}, "
                  f"WR={(is_fil['ret']>0).mean()*100:.1f}%, "
                  f"MeanRet={is_fil['ret'].mean()*100:.2f}%")

    verdict = "CONFIRMED" if all_confirmed else "NOT CONFIRMED"
    best = max(all_confirmed, key=lambda r: r["wr"] * r["n"]) if all_confirmed else None

    out_lines = [
        "H176 — PEAD-NLP: GPT-4o-mini Relative Sentiment (FinDPO Proxy)",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥3%  |  Hold=20d  |  IS: 2020–2023  |  OOS: 2024+",
        f"Filter: GPT-4o-mini = MORE_POSITIVE AND H163 FinBERT score ≥ thresh",
        f"Compare: H173 (scalar surprise, NOT CONFIRMED), H174 (dual filter, CONFIRMED)",
        "",
        f"H168 transcript coverage: {n_cached}/{n_expected} = {coverage*100:.1f}%",
        f"GPT cache hits: {n_cache_hits}  |  New API calls: {n_api_calls}",
        f"OOS events with valid GPT + score: {len(oos_valid)} / {len(oos_df)}",
        f"GPT=MORE_POSITIVE OOS events: {len(gpt_pos_oos)}",
        "",
    ]

    if best:
        out_lines += [
            f"Best: GPT=MORE_POSITIVE + score≥{best['score_thresh']:.2f}: "
            f"n={best['n']}, WR={best['wr']*100:.1f}%, MeanRet={best['mr']*100:.2f}%",
        ]
    out_lines += [
        "",
        f"VERDICT: {verdict}",
    ]
    if not all_confirmed:
        out_lines += ["Possible reasons: insufficient transcript coverage, or GPT proxy weaker than scalar surprise."]

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    result_path = RESULT_DIR / "h176_gpt_relative_sentiment.txt"
    result_path.write_text("\n".join(out_lines))

    print("\n" + "=" * 66)
    print(f"  VERDICT: {verdict}")
    if best:
        print(f"  Best: GPT=MORE_POSITIVE + score≥{best['score_thresh']:.2f}: "
              f"n={best['n']}, WR={best['wr']*100:.1f}%, MeanRet={best['mr']*100:.2f}%")
    print(f"  Results saved → {result_path}")
    print("=" * 66)


if __name__ == "__main__":
    main()
