"""
H350 — Text Uncertainty Anti-Filter for H174 PEAD Entries
==========================================================
Source:
  Hong, Kottimukkalur & Noh (2026), "Uncertain Text and Price Reactions to
  Earnings Releases", Journal of Banking & Finance vol. 182.

Finding:
  Firms with HIGH linguistic uncertainty in 8-K earnings filings show:
    + Stronger IMMEDIATE price reaction (market reacts faster)
    - WEAKER post-earnings announcement drift (PEAD signal attenuated)
  Mechanism: uncertainty language attracts institutional attention →
  faster price discovery → the drift H174 exploits is reduced.

Hypothesis:
  Adding a third filter to H174 (score≥0.18 + surprise≥0.02):
    lm_uncertainty_ratio < threshold
  should improve OOS WR above H174's 81.8% (n=22) by excluding events
  where drift is weak due to high uncertainty text.

Design:
  Universe / pipeline: same as H174 (30-stock PEAD universe)
  Uncertainty measure: Loughran-McDonald (2011) uncertainty wordlist ratio
    = count(LM_uncertainty_words in 8-K text) / total_word_count
  Threshold: set on IS all-PEAD-events (not just H174-confirmed)
    to avoid target leakage; then applied to OOS H174-confirmed events.
  Threshold variants tested:
    V1: IS 50th pct (median split)  — keep bottom half by uncertainty
    V2: IS 67th pct                 — keep bottom 2/3
    V3: IS 75th pct                 — keep bottom 3/4
    V4: IS 90th pct                 — keep bottom 90% (soft exclusion)
    V5: H174 baseline (no filter)   — reference

  IS: 2020-2023  |  OOS: 2024+  (same split as H174)

Gates (primary: V2 or V3 must pass to CONFIRM H350):
  OOS WR > 81.8%  (H174 baseline)
  n_oos >= 20
  (V4 "soft" gate: OOS WR > 81.8% AND n_oos >= 15)

LM Uncertainty wordlist: Loughran & McDonald (2011) JF, Section 3.2.
  Official list has ~297 entries. Used subset of ~180 core words below —
  high-frequency uncertainty indicators that appear in 8-K earnings texts.
"""

import re
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

IS_END    = pd.Timestamp("2023-12-31")
OOS_START = pd.Timestamp("2024-01-01")

# Same universe as H174
UNIVERSE = [
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA",
    "WMT","MA","V","JNJ","UNH","ABBV","LLY",
    "AVGO","AMD","QCOM","INTC","IBM",
    "HD","LOW","SBUX","MCD","WFC","BAC",
    "PG","KO","XOM","CVX","PFE",
]

H174_SCORE_THRESH    = 0.18
H174_SURPRISE_THRESH = 0.02

# ── Loughran-McDonald Uncertainty Wordlist (2011 JF) ─────────────────────
# ~297 official words. This implementation uses ~180 high-coverage entries.
LM_UNCERTAINTY = {
    "approximate", "approximately", "appear", "appears", "assume", "assumed",
    "assumes", "assumption", "assumptions", "believe", "believed", "believes",
    "believing", "certain", "challenge", "challenges", "complex", "complexity",
    "concern", "concerned", "concerns", "conceivable", "conditional",
    "contingent", "could", "could be", "depend", "dependent", "depends",
    "difficult", "difficulty", "doubt", "doubtful", "doubts",
    "estimate", "estimated", "estimates", "estimating", "estimation",
    "evaluating", "expect", "expected", "expects", "expectation", "expectations",
    "expose", "exposed", "exposure", "exposures",
    "feel", "flexibility", "fluct", "fluctuate", "fluctuating", "fluctuation",
    "forecasting", "forthcoming",
    "guess", "guesses",
    "hazy", "hesitant", "hesitate",
    "imprecise", "inaccurate", "uncertain", "uncertainties", "uncertainty",
    "unclear", "undetermined", "undetermined", "unforeseen", "unlikely",
    "unresolved", "unsettled", "uncertain", "uncertain",
    "indefinite", "indefinitely", "indicate", "indication", "indeterminate",
    "insufficient", "intend", "intended", "intends",
    "judgment", "judgments",
    "likely", "limited",
    "may", "maybe", "might", "miscalculate", "might",
    "occasional", "often",
    "perhaps", "possibility", "possible", "possibly", "potential", "potentially",
    "predict", "predicted", "predicts", "presumably", "probable", "probably",
    "project", "projected", "projects",
    "question", "questionable",
    "reassess", "rely", "roughly", "risk", "risks", "risky",
    "seek", "seemingly", "should", "somewhat", "speculate", "speculative",
    "subject", "subjective", "suggest", "suggested", "suggests", "suppose",
    "theoretically", "typically",
    "vague", "various", "vary", "varies", "view",
    "when available", "whenever",
}


def compute_lm_ratio(text: str) -> float:
    """Compute LM uncertainty ratio = LM uncertainty words / total words."""
    words = re.findall(r"[a-z]+", text.lower())
    if len(words) < 50:
        return float("nan")
    count = sum(1 for w in words if w in LM_UNCERTAINTY)
    return count / len(words)


def load_8k_text(ticker: str, date: pd.Timestamp) -> str | None:
    """Load cached 8-K text for a ticker/date combination."""
    date_str = date.strftime("%Y-%m-%d")
    p = CACHE_DIR / f"h163_8k_{ticker}_{date_str}.txt"
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    return None


# ── 1. Load H174 event set ────────────────────────────────────────────────
print("[1/5] Loading FinBERT scores and H174 event pipeline...")
score_df = pd.read_parquet(CACHE_DIR / "h163_finbert_scores.parquet")
score_df["date"] = pd.to_datetime(score_df["date"])

# Build the H174 surprise measure (same logic as run_h174.py)
def compute_surprise(ticker, event_date):
    prior = score_df[
        (score_df["ticker"] == ticker) & (score_df["date"] < event_date)
    ].sort_values("date").tail(4)
    current = score_df[
        (score_df["ticker"] == ticker) & (score_df["date"] == event_date)
    ]
    if current.empty or len(prior) < 2:
        return float("nan")
    return float(current.iloc[0]["finbert_score"]) - float(prior["finbert_score"].mean())


print("[2/5] Computing LM uncertainty ratios for all cached 8-K texts...")
rows = []
for path in sorted(CACHE_DIR.glob("h163_8k_*.txt")):
    parts = path.stem.split("_")
    if len(parts) < 4:
        continue
    ticker   = parts[2]
    date_str = parts[3]
    try:
        date = pd.Timestamp(date_str)
    except Exception:
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    lm   = compute_lm_ratio(text)
    rows.append({"ticker": ticker, "date": date, "lm_ratio": lm})

lm_df = pd.DataFrame(rows)
lm_df["date"] = pd.to_datetime(lm_df["date"])
print(f"  Computed LM uncertainty ratios for {len(lm_df)} cached 8-K texts")
print(f"  Mean ratio: {lm_df['lm_ratio'].mean():.4f}  Std: {lm_df['lm_ratio'].std():.4f}")

# IS threshold: set from all 2020-2023 8-K texts (not just H174-confirmed)
is_lm = lm_df[lm_df["date"] <= IS_END]["lm_ratio"].dropna()
thresholds = {
    "V1_median": is_lm.quantile(0.50),
    "V2_p67":    is_lm.quantile(0.67),
    "V3_p75":    is_lm.quantile(0.75),
    "V4_p90":    is_lm.quantile(0.90),
}
print(f"\n  IS uncertainty distribution (n={len(is_lm)}):")
for k, v in thresholds.items():
    print(f"    {k}: {v:.5f}")

# ── 3. Build H174-confirmed OOS event list ────────────────────────────────
print("\n[3/5] Building H174-qualified OOS events...")

# Load OHLCV (use cached or download)
GAP_THRESH = 0.03
LOOKBACK_Q = 4
MIN_PRIOR  = 2


def load_ohlcv():
    result = {}
    to_dl = []
    for t in UNIVERSE:
        for pfx in [f"h{i:03d}" for i in range(155, 176)]:
            for suf in ["ohlcv", "ohlc"]:
                p = CACHE_DIR / f"{pfx}_{t}_{suf}_2019-01-01_2026-04-30.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "open" in df.columns and "close" in df.columns:
                        result[t] = df
                        break
            if t in result:
                break
        if t not in result:
            to_dl.append(t)
    if to_dl:
        batch = yf.download(to_dl, start="2019-01-01", end="2026-06-30",
                            auto_adjust=True, progress=False)
        if isinstance(batch.columns, pd.MultiIndex):
            for t in to_dl:
                try:
                    df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                    df.columns = ["open", "close"]
                    result[t] = df.dropna()
                except Exception:
                    pass
    return result


def get_earnings_dates(ticker) -> list:
    cache_path = CACHE_DIR / f"h163_earndates_{ticker}.parquet"
    if not cache_path.exists():
        return []
    df = pd.read_parquet(cache_path)
    return pd.to_datetime(df["date"]).dt.normalize().tolist()


def find_gap_events(ohlcv):
    """Find all days with ≥3% open gap across the full universe."""
    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, _ in df[gap_pct >= GAP_THRESH].iterrows():
            events.append({"ticker": t, "date": idx.normalize(),
                           "gap_pct": float(gap_pct[idx])})
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def is_earnings_gap(ticker, gap_date, earn_dates_map, window=3):
    edates = earn_dates_map.get(ticker, [])
    for ed in edates:
        ed = pd.Timestamp(ed).normalize()
        if abs((gap_date - ed).days) <= window:
            return True
    return False


def compute_return_h174(ticker, entry_date, ohlcv, hold=20):
    """Entry at open on gap day, exit at close after 20 trading days."""
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = float(future.iloc[0]["open"])
    exit_ = float(future.iloc[hold - 1]["close"])
    return (exit_ - entry) / entry if entry > 0 else None


print("  Loading OHLCV data...")
ohlcv = load_ohlcv()

print("  Building earnings-date map...")
earn_map = {t: get_earnings_dates(t) for t in UNIVERSE}

print("  Finding gap events across full universe...")
all_gaps = find_gap_events(ohlcv)
all_gaps["date"] = pd.to_datetime(all_gaps["date"]).dt.normalize()

# Filter to earnings gaps and OOS period
all_gaps["is_earn"] = all_gaps.apply(
    lambda r: is_earnings_gap(r["ticker"], r["date"], earn_map), axis=1)
oos_gaps = all_gaps[(all_gaps["is_earn"]) & (all_gaps["date"] >= OOS_START)].copy()
print(f"  OOS earnings-gap events (any score): {len(oos_gaps)}")

# Enrich with FinBERT score, surprise, return, LM ratio
oos_events = []
for _, gap in oos_gaps.iterrows():
    ticker = gap["ticker"]
    edate  = gap["date"]

    # FinBERT score from cache
    sr = score_df[(score_df["ticker"] == ticker) & (score_df["date"] == edate)]
    if sr.empty:
        continue
    score = float(sr.iloc[0]["finbert_score"])
    if score < H174_SCORE_THRESH:
        continue

    # Surprise vs prior 4 quarters
    prior_scores = score_df[
        (score_df["ticker"] == ticker) & (score_df["date"] < edate)
    ].sort_values("date").tail(LOOKBACK_Q)
    if len(prior_scores) < MIN_PRIOR:
        continue
    surprise = score - float(prior_scores["finbert_score"].mean())
    if surprise < H174_SURPRISE_THRESH:
        continue

    # 20-day return (entry at open, exit at close 20 days later)
    ret = compute_return_h174(ticker, edate, ohlcv, hold=20)
    if ret is None:
        continue

    # LM uncertainty ratio
    lm_row = lm_df[(lm_df["ticker"] == ticker) & (lm_df["date"] == edate)]
    lm_ratio = float(lm_row.iloc[0]["lm_ratio"]) if not lm_row.empty else float("nan")

    oos_events.append({
        "ticker": ticker, "date": edate,
        "score": score, "surprise": surprise,
        "ret": ret, "lm_ratio": lm_ratio,
    })

oos_df = pd.DataFrame(oos_events)
print(f"  H174-qualified OOS events: {len(oos_df)}")
if len(oos_df) == 0:
    print("  ERROR: No OOS events found. Exiting.")
    exit(1)

oos_with_lm = oos_df.dropna(subset=["lm_ratio"])
print(f"  Events with LM ratio available: {len(oos_with_lm)}")
print(f"  OOS LM ratio distribution:")
print(f"    mean={oos_with_lm['lm_ratio'].mean():.5f}  "
      f"median={oos_with_lm['lm_ratio'].median():.5f}  "
      f"max={oos_with_lm['lm_ratio'].max():.5f}")

# ── 4. Apply thresholds and measure impact ────────────────────────────────
print("\n[4/5] Applying LM uncertainty filter thresholds...")
print(f"\n  H174 baseline (n={len(oos_df)}):")
wr_base = (oos_df["ret"] > 0).mean()
mr_base = oos_df["ret"].mean()
print(f"  WR={wr_base*100:.1f}%  MeanRet={mr_base*100:.2f}%")

print(f"\n  {'Threshold':>20} {'CutAt':>8} {'n':>5} {'WR%':>7} "
      f"{'MeanRet%':>10} {'LM_cutoff':>11} {'Verdict':>12}")
print("  " + "-" * 82)

results_by_variant = {}
for var, thresh in thresholds.items():
    subset = oos_with_lm[oos_with_lm["lm_ratio"] < thresh]
    if len(subset) == 0:
        print(f"  {var:>20}: no events remain")
        continue
    wr = (subset["ret"] > 0).mean()
    mr = subset["ret"].mean()
    n  = len(subset)
    wr_better = wr > wr_base
    n_ok      = n >= 20
    verdict   = "CONFIRM" if (wr_better and n_ok) else ("soft" if (wr_better and n >= 15) else "FAIL")
    print(f"  {var:>20}: thresh={thresh:.5f}  n={n:>3}  "
          f"WR={wr*100:>5.1f}%  MeanRet={mr*100:>6.2f}%  "
          f"LM<{thresh:.4f}  → {verdict}")
    results_by_variant[var] = {
        "threshold": thresh, "n": n, "wr": wr, "mr": mr,
        "wr_improved": bool(wr_better), "n_ok": n_ok, "verdict": verdict,
    }

# Also show: what are the high-uncertainty OOS events being excluded?
print("\n  Events excluded at V2 (IS p67) — high-uncertainty firms:")
thresh_v2 = thresholds["V2_p67"]
excluded = oos_with_lm[oos_with_lm["lm_ratio"] >= thresh_v2]
for _, ev in excluded.iterrows():
    print(f"    {ev['ticker']} {ev['date'].date()}  "
          f"lm={ev['lm_ratio']:.5f}  ret={ev['ret']*100:+.1f}%  "
          f"score={ev['score']:.3f}")

# Primary verdict: Variant V2 (IS p67) — keep bottom 2/3
primary = results_by_variant.get("V2_p67", {})
confirmed = primary.get("verdict") == "CONFIRM"
soft_confirm = primary.get("verdict") == "soft"

print("\n[5/5] Verdict...")
print("=" * 60)
print(f"  H174 baseline: WR={wr_base*100:.1f}%, n={len(oos_df)}")
if primary:
    print(f"  H350 V2 (p67): WR={primary['wr']*100:.1f}%, n={primary['n']}")
    print(f"  WR improved:   {primary['wr_improved']}")
    print(f"  n >= 20:       {primary['n_ok']}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'SOFT CONFIRM (n<20)' if soft_confirm else 'NOT CONFIRMED'}")
print("=" * 60)

# ── Save results ──────────────────────────────────────────────────────────
import json
out = {
    "hypothesis": "H350",
    "title": "Text Uncertainty Anti-Filter for H174 PEAD (LM uncertainty ratio)",
    "status": "CONFIRMED" if confirmed else ("SOFT" if soft_confirm else "NOT CONFIRMED"),
    "h174_baseline": {"n": len(oos_df), "wr": round(wr_base, 4), "mr": round(mr_base, 4)},
    "is_thresholds": {k: round(v, 6) for k, v in thresholds.items()},
    "is_lm_n": len(is_lm),
    "oos_lm_coverage": len(oos_with_lm),
    "variants": results_by_variant,
    "primary_variant": "V2_p67",
    "sources": [
        "Hong, Kottimukkalur & Noh (2026) JBF vol.182",
        "Loughran & McDonald (2011) JF — LM uncertainty wordlist",
    ],
}
out_path = RESULT_DIR / "h350_results.json"
out_path.write_text(json.dumps(out, indent=2, default=str))
print(f"\nResults saved → {out_path}")
