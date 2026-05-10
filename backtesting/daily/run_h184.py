"""
H184 — PEAD-NLP: Composite Press-Release + Call-Transcript FinBERT Signal
=========================================================================
Hypothesis (arXiv:2509.24254 — Wu et al. 2025):
  Blending FinBERT scores from two independent text sources —
  the 8-K earnings press release (H163) and the earnings call transcript
  (H168) — improves predictive power over either source alone.

Method:
  1. Load H163 press-release FinBERT scores  (h163_finbert_scores.parquet)
  2. Load H168 call-transcript FinBERT scores (h168_finbert_scores.parquet)
  3. For each earnings gap-up event, compute:
       composite_score = α * pr_score + (1-α) * call_score
     Test α ∈ {0.3, 0.5, 0.7}; also test pr-only and call-only.
     Fallback: if only one source available, use that source's score.
  4. Enter long on gap-up day; hold 20 trading days.
  5. Compare IS/OOS metrics for all variants vs H163 baseline.

Success criterion:
  Any composite variant improves OOS Sharpe by ≥0.2 vs H163 baseline,
  OR reduces OOS MaxDD by ≥2pp.

Data: fully cached — no new API calls or model inference needed.
IS: 2020-2023  |  OOS: 2024-2026
Universe: 30 large-cap S&P 500 stocks (H163 universe)
"""

import math
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

WORKSPACE   = Path(__file__).resolve().parent.parent.parent
CACHE_DIR   = WORKSPACE / "backtesting" / "cache"
RESULT_DIR  = WORKSPACE / "backtesting" / "results"

PR_SCORES_PATH   = CACHE_DIR / "h163_finbert_scores.parquet"
CALL_SCORES_PATH = CACHE_DIR / "h168_finbert_scores.parquet"
RESULT_DIR.mkdir(exist_ok=True)

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
HOLD_DAYS  = 20
ALPHA_VALS = [0.30, 0.50, 0.70]   # pr weight in composite


# ── Data loading ─────────────────────────────────────────────────────────────

def load_scores() -> tuple[dict, dict]:
    """Load both score dicts keyed by (ticker, date_str)."""
    pr   = pd.read_parquet(PR_SCORES_PATH)
    call = pd.read_parquet(CALL_SCORES_PATH)

    pr_dict = {}
    for _, row in pr.iterrows():
        if pd.notna(row["finbert_score"]):
            pr_dict[(row["ticker"], str(pd.Timestamp(row["date"]).date()))] = float(row["finbert_score"])

    call_col = "weighted_score" if "weighted_score" in call.columns else call.columns[-1]
    call_dict = {}
    for _, row in call.iterrows():
        if pd.notna(row[call_col]):
            call_dict[(row["ticker"], str(pd.Timestamp(row["date"]).date()))] = float(row[call_col])

    return pr_dict, call_dict


def load_ohlcv() -> dict:
    result = {}
    start, end = "2019-01-01", "2026-04-30"
    to_dl = []
    for t in UNIVERSE:
        p = CACHE_DIR / f"h163_{t}_ohlcv_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "open" in df.columns and "close" in df.columns:
                result[t] = df[["open", "close"]]
            continue
        to_dl.append(t)

    if to_dl:
        print(f"  Downloading {len(to_dl)} tickers…")
        batch = yf.download(to_dl, start=start, end=end,
                            auto_adjust=True, progress=False)
        for t in to_dl:
            try:
                df = batch.xs(t, axis=1, level=1)[["Open", "Close"]].copy()
                df.columns = ["open", "close"]
                df = df.dropna()
                if len(df) > 100:
                    df.to_parquet(CACHE_DIR / f"h163_{t}_ohlcv_{start}_{end}.parquet")
                    result[t] = df
            except Exception:
                pass
    return result


def get_earnings_dates(ticker: str) -> list:
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


# ── Event detection + enrichment ─────────────────────────────────────────────

def find_earnings_gaps(ohlcv: dict) -> pd.DataFrame:
    earnings_by_ticker = {t: get_earnings_dates(t) for t in UNIVERSE}

    def near_earnings(ticker, gap_date, window=3):
        for ed in earnings_by_ticker.get(ticker, []):
            if abs((gap_date - ed).days) <= window:
                return True
        return False

    events = []
    for t, df in ohlcv.items():
        df = df.sort_index()
        prev_close = df["close"].shift(1)
        gap_pct = (df["open"] - prev_close) / prev_close
        for idx, row in df[gap_pct > GAP_THRESH].iterrows():
            if near_earnings(t, idx):
                events.append({
                    "ticker": t, "date": idx,
                    "gap_pct": gap_pct[idx], "entry_px": row["open"],
                })
    return pd.DataFrame(events).sort_values("date").reset_index(drop=True)


def compute_return(ticker, entry_date, ohlcv, hold=HOLD_DAYS) -> float | None:
    if ticker not in ohlcv:
        return None
    df = ohlcv[ticker].sort_index()
    future = df[df.index >= entry_date]
    if len(future) < hold:
        return None
    entry = future.iloc[0]["open"]
    exit_ = future.iloc[hold - 1]["close"]
    return (exit_ - entry) / entry if entry > 0 else None


def enrich_events(events: pd.DataFrame, pr_dict: dict, call_dict: dict,
                  ohlcv: dict) -> pd.DataFrame:
    rows = []
    for _, ev in events.iterrows():
        key = (ev["ticker"], str(ev["date"].date()))
        pr_sc   = pr_dict.get(key)
        call_sc = call_dict.get(key)
        ret     = compute_return(ev["ticker"], ev["date"], ohlcv)
        if ret is None:
            continue
        rows.append({
            "ticker":   ev["ticker"],
            "date":     ev["date"],
            "gap_pct":  ev["gap_pct"],
            "pr_score": pr_sc,
            "call_score": call_sc,
            "ret20":    ret,
            "win":      ret > 0,
        })
    return pd.DataFrame(rows)


# ── Metrics ──────────────────────────────────────────────────────────────────

def sharpe(rets: pd.Series, ann=252, hold=HOLD_DAYS) -> float:
    if len(rets) < 5:
        return float("nan")
    periods_per_year = ann / hold
    return float(rets.mean() / rets.std() * math.sqrt(periods_per_year)) if rets.std() > 0 else float("nan")


def max_drawdown(rets: pd.Series) -> float:
    if len(rets) == 0:
        return float("nan")
    cum = (1 + rets).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    return float(dd.min())


def eval_strategy(df: pd.DataFrame, score_col: str, thresh: float, label: str):
    mask = df[score_col].notna() & (df[score_col] > thresh)
    sub = df[mask]
    if len(sub) < 3:
        return None
    rets = sub["ret20"]
    return {
        "label":    label,
        "n":        len(sub),
        "wr":       float(sub["win"].mean()),
        "mean_ret": float(rets.mean()),
        "sharpe":   sharpe(rets),
        "max_dd":   max_drawdown(rets),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  H184 — Composite PR + Call FinBERT Signal")
    print("=" * 64)

    # 1. Load scores
    print("\n[1/5] Loading cached FinBERT scores…")
    pr_dict, call_dict = load_scores()
    print(f"  Press-release scores: {len(pr_dict)}")
    print(f"  Call-transcript scores: {len(call_dict)}")

    # 2. Load OHLCV
    print("\n[2/5] Loading OHLCV…")
    ohlcv = load_ohlcv()
    print(f"  {len(ohlcv)} tickers loaded")

    # 3. Build events
    print("\n[3/5] Building earnings gap-up events…")
    events = find_earnings_gaps(ohlcv)
    is_ev  = events[events["date"] <= IS_END]
    oos_ev = events[events["date"] >= OOS_START]
    print(f"  IS events: {len(is_ev)}  |  OOS events: {len(oos_ev)}")

    # 4. Enrich with scores and returns
    print("\n[4/5] Enriching events with scores and returns…")
    is_df  = enrich_events(is_ev, pr_dict, call_dict, ohlcv)
    oos_df = enrich_events(oos_ev, pr_dict, call_dict, ohlcv)

    # Add composite columns for each alpha
    for alpha in ALPHA_VALS:
        col = f"composite_{int(alpha*10):02d}"
        for df in [is_df, oos_df]:
            df[col] = np.where(
                df["pr_score"].notna() & df["call_score"].notna(),
                alpha * df["pr_score"] + (1 - alpha) * df["call_score"],
                np.where(df["pr_score"].notna(), df["pr_score"],
                         np.where(df["call_score"].notna(), df["call_score"], np.nan)),
            )

    both_avail_oos = oos_df["pr_score"].notna() & oos_df["call_score"].notna()
    print(f"  OOS events with PR score:   {oos_df['pr_score'].notna().sum()}")
    print(f"  OOS events with call score: {oos_df['call_score'].notna().sum()}")
    print(f"  OOS events with both:       {both_avail_oos.sum()}")

    # 5. Compare strategies
    print("\n[5/5] Strategy comparison (threshold = 0.10):")
    THRESH = 0.10

    results_is  = []
    results_oos = []

    strategies = [
        ("pr_score",   "H163 PR-only"),
        ("call_score", "H168 Call-only"),
    ] + [(f"composite_{int(a*10):02d}", f"H184 composite (α={a:.1f})") for a in ALPHA_VALS]

    for col, label in strategies:
        r_is  = eval_strategy(is_df, col, THRESH, label)
        r_oos = eval_strategy(oos_df, col, THRESH, label)
        if r_is:
            results_is.append(r_is)
        if r_oos:
            results_oos.append(r_oos)

    # Baseline: all OOS events regardless of score
    base_n   = len(oos_df)
    base_wr  = float(oos_df["win"].mean())
    base_ret = float(oos_df["ret20"].mean())
    base_shr = sharpe(oos_df["ret20"])
    base_dd  = max_drawdown(oos_df["ret20"])

    print(f"\n  Baseline (all OOS earnings gaps):  n={base_n}  "
          f"WR={base_wr:.1%}  MeanRet={base_ret:.2%}  "
          f"Sharpe={base_shr:.2f}  MaxDD={base_dd:.1%}")

    print(f"\n  {'Strategy':<30}  {'n':>4}  {'WR':>7}  {'MeanRet':>8}  {'Sharpe':>7}  {'MaxDD':>7}")
    print(f"  {'-'*30}  {'-'*4}  {'-'*7}  {'-'*8}  {'-'*7}  {'-'*7}")

    h163_sharpe_oos = float("nan")
    best_composite_sharpe = float("nan")

    for r in results_oos:
        label = r["label"]
        print(f"  {label:<30}  {r['n']:>4}  {r['wr']:>6.1%}  {r['mean_ret']:>7.2%}  "
              f"  {r['sharpe']:>6.2f}  {r['max_dd']:>6.1%}")
        if "H163 PR-only" in label:
            h163_sharpe_oos = r["sharpe"]
        if "H184 composite" in label and not math.isnan(r["sharpe"]):
            if math.isnan(best_composite_sharpe) or r["sharpe"] > best_composite_sharpe:
                best_composite_sharpe = r["sharpe"]

    # Verdict
    sharpe_lift = best_composite_sharpe - h163_sharpe_oos if not math.isnan(best_composite_sharpe) and not math.isnan(h163_sharpe_oos) else float("nan")
    confirmed = not math.isnan(sharpe_lift) and sharpe_lift >= 0.20
    partial   = not math.isnan(sharpe_lift) and sharpe_lift >= 0.05

    if confirmed:
        verdict = "CONFIRMED"
    elif partial:
        verdict = "PARTIAL"
    else:
        verdict = "NOT CONFIRMED"

    print(f"\n  H163 OOS Sharpe:           {h163_sharpe_oos:.2f}" if not math.isnan(h163_sharpe_oos) else "\n  H163 OOS Sharpe:  n/a")
    print(f"  Best composite OOS Sharpe: {best_composite_sharpe:.2f}" if not math.isnan(best_composite_sharpe) else "  Best composite OOS Sharpe: n/a")
    if not math.isnan(sharpe_lift):
        print(f"  Sharpe lift:               {sharpe_lift:+.2f}  (need ≥+0.20 for CONFIRMED)")

    print(f"\n{'='*64}")
    print(f"  VERDICT: {verdict}")
    print(f"{'='*64}")

    # ── Save results ─────────────────────────────────────────────────────────
    lines = [
        "H184 — Composite PR + Call FinBERT Signal",
        f"Run: {datetime.now():%Y-%m-%d %H:%M}",
        f"Universe: {len(UNIVERSE)} stocks  |  GAP≥{GAP_THRESH:.0%}  |  Hold={HOLD_DAYS}d",
        f"IS: 2020-2023  |  OOS: 2024-2026",
        f"PR scores available:   {len(pr_dict)}",
        f"Call scores available: {len(call_dict)}",
        "",
        f"Baseline OOS:  n={base_n}  WR={base_wr:.1%}  MeanRet={base_ret:.2%}  Sharpe={base_shr:.2f}  MaxDD={base_dd:.1%}",
        "",
        "OOS Strategy Comparison (threshold=0.10):",
    ]
    for r in results_oos:
        lines.append(
            f"  {r['label']:<30}  n={r['n']:>4}  WR={r['wr']:.1%}  "
            f"MeanRet={r['mean_ret']:.2%}  Sharpe={r['sharpe']:.2f}  MaxDD={r['max_dd']:.1%}"
        )
    if not math.isnan(sharpe_lift):
        lines.append(f"\nSharpe lift (best composite vs H163): {sharpe_lift:+.2f}")
    lines.append(f"\nVERDICT: {verdict}")

    out_path = RESULT_DIR / "h184_composite_finbert.txt"
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"\n  Results → {out_path}")

    return verdict, results_oos, base_wr, base_shr


if __name__ == "__main__":
    main()
