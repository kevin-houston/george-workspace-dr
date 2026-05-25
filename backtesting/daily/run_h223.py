"""
H223 — Cross-Sectional Factor Momentum: Multi-Window Blend
==========================================================
Applied Economics Letters (2025): factor momentum across multiple formation
periods (1–1, 2–6, 7–12, 13–60 months) consistently outperforms single-window.

This extends H198 (6-1m momentum, OOS Sharpe 1.174) by blending signals:
  S_i = rank(R_1m) + rank(R_6m) + rank(R_12m)  (equal-weighted rank sum)

Universe: same 30 large-cap stocks as H198
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 1.4 (must beat H198's 1.174 meaningfully)

Variants tested:
  A) rank(R_1m) + rank(R_6m) + rank(R_12m)  — all windows include last month
  B) rank(R_6m_skip) + rank(R_12m_skip)     — skip last month (like H198)
  C) rank(R_1_1) + rank(R_2_6) + rank(R_7_12) — non-overlapping paper windows
  D) All four paper windows incl. 13-60m     — full paper replication

Long top-5 (quintile of 30), equal-weight, monthly rebalance.
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
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ── Universe (same as H198) ───────────────────────────────────────────────────
UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",  "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",  "COST",
    "CVX",  "XOM",  "BA",   "CAT",  "IBM",
]

DATA_START = "2010-01-01"   # need 60+ months of warmup before IS start
DATA_END   = "2026-05-01"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-05-01")

TOP_N  = 5
TC_BPS = 5   # one-way transaction cost


# ── Data ──────────────────────────────────────────────────────────────────────

def fetch_monthly_prices() -> pd.DataFrame:
    """Returns monthly close prices for all universe tickers."""
    cp = CACHE_DIR / f"h223_universe_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)

    print("  Downloading universe prices…")
    raw = yf.download(
        UNIVERSE, start=DATA_START, end=DATA_END,
        auto_adjust=True, progress=False,
    )
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    # Reindex to ensure all tickers present
    closes = closes.reindex(columns=UNIVERSE).dropna(how="all")
    monthly = closes.resample("ME").last()
    monthly.to_parquet(cp)
    return monthly


# ── Statistics ────────────────────────────────────────────────────────────────

def sharpe(r: pd.Series) -> float:
    if r.std() == 0 or len(r) < 6:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def neg_year_count(r: pd.Series) -> int:
    if r.empty:
        return 0
    annual = (1 + r).resample("YE").prod() - 1
    return int((annual < 0).sum())


def summary_stats(r: pd.Series, label: str) -> dict:
    if r.empty or len(r) < 3:
        return {"label": label, "error": "insufficient data"}
    ann_ret = float(r.mean() * 12)
    ann_vol = float(r.std() * np.sqrt(12))
    return {
        "label":    label,
        "sharpe":   round(sharpe(r), 4),
        "ann_ret":  round(ann_ret, 4),
        "ann_vol":  round(ann_vol, 4),
        "cumul":    round(cumul(r), 4),
        "maxdd":    round(maxdd(r), 4),
        "neg_years": neg_year_count(r),
        "n_months": len(r),
    }


# ── Signal builders ───────────────────────────────────────────────────────────

def rank_cs(s: pd.Series) -> pd.Series:
    """Cross-sectional rank, normalized to [0,1]."""
    return s.rank(method="average") / len(s.dropna())


def build_composite_score(monthly: pd.DataFrame, variant: str, t: int) -> pd.Series | None:
    """
    Compute composite momentum score at time-index t.
    Returns Series of scores (higher = stronger momentum), or None if insufficient data.

    variant:
      A = rank(R_1m) + rank(R_6m) + rank(R_12m)  [all windows touch last month]
      B = rank(R_6m_skip) + rank(R_12m_skip)      [both skip last month]
      C = rank(R_1_1) + rank(R_2_6) + rank(R_7_12) [non-overlapping]
      D = rank(R_1_1) + rank(R_2_6) + rank(R_7_12) + rank(R_13_60) [full paper]
    """
    px = monthly.iloc[:t + 1]

    def ret(lo: int, hi: int) -> pd.Series:
        """Return from t-hi to t-lo (months back). lo=1 means t-1."""
        if len(px) <= hi:
            return pd.Series(dtype=float)
        return (px.iloc[-lo] / px.iloc[-hi - 1] - 1).dropna()

    if variant == "A":
        r1  = ret(0, 1)   # R_1m: last month
        r6  = ret(0, 6)   # R_6m: 6 months
        r12 = ret(0, 12)  # R_12m: 12 months
        if any(s.empty for s in [r1, r6, r12]):
            return None
        common = r1.index.intersection(r6.index).intersection(r12.index)
        if len(common) < TOP_N:
            return None
        return rank_cs(r1[common]) + rank_cs(r6[common]) + rank_cs(r12[common])

    elif variant == "B":
        r6s  = ret(1, 6)   # 6m skip-1: t-6 to t-1
        r12s = ret(1, 12)  # 12m skip-1: t-12 to t-1  (= H198 signal)
        if any(s.empty for s in [r6s, r12s]):
            return None
        common = r6s.index.intersection(r12s.index)
        if len(common) < TOP_N:
            return None
        return rank_cs(r6s[common]) + rank_cs(r12s[common])

    elif variant == "C":
        r1_1  = ret(0, 1)    # month t: pure 1-month return
        r2_6  = ret(1, 6)    # months 2-6: t-6 to t-1 (5-month window)
        r7_12 = ret(6, 12)   # months 7-12: t-12 to t-6 (6-month window)
        if any(s.empty for s in [r1_1, r2_6, r7_12]):
            return None
        common = r1_1.index.intersection(r2_6.index).intersection(r7_12.index)
        if len(common) < TOP_N:
            return None
        return rank_cs(r1_1[common]) + rank_cs(r2_6[common]) + rank_cs(r7_12[common])

    elif variant == "D":
        r1_1   = ret(0, 1)     # month t
        r2_6   = ret(1, 6)     # months 2-6
        r7_12  = ret(6, 12)    # months 7-12
        r13_60 = ret(12, 60)   # months 13-60 (long-term)
        if any(s.empty for s in [r1_1, r2_6, r7_12, r13_60]):
            return None
        common = r1_1.index.intersection(r2_6.index).intersection(r7_12.index).intersection(r13_60.index)
        if len(common) < TOP_N:
            return None
        return rank_cs(r1_1[common]) + rank_cs(r2_6[common]) + rank_cs(r7_12[common]) + rank_cs(r13_60[common])

    return None


# ── Backtest engine ───────────────────────────────────────────────────────────

def backtest_variant(monthly: pd.DataFrame, variant: str) -> pd.Series:
    """
    Run monthly-rebalance top-N momentum strategy for the given variant.
    Returns monthly return series.
    """
    rets_df  = monthly.pct_change()
    tc       = TC_BPS / 10_000

    monthly_ret_series = []
    prev_holdings: list[str] = []

    for t in range(1, len(monthly)):
        dt = monthly.index[t]

        score = build_composite_score(monthly, variant, t - 1)
        if score is None:
            continue

        holdings = list(score.nlargest(TOP_N).index)

        # Transaction cost on turnover
        turnover = len(set(holdings) - set(prev_holdings)) / TOP_N
        cost     = turnover * tc

        # Portfolio return this month
        row     = rets_df.iloc[t]
        valid   = [s for s in holdings if s in row and not np.isnan(row[s])]
        if not valid:
            continue
        port_ret = float(row[valid].mean()) - cost

        monthly_ret_series.append((dt, port_ret))
        prev_holdings = holdings

    if not monthly_ret_series:
        return pd.Series(dtype=float)

    dates = [d for d, _ in monthly_ret_series]
    rets  = [r for _, r in monthly_ret_series]
    return pd.Series(rets, index=pd.DatetimeIndex(dates))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 72)
    print("H223 — Multi-Window Momentum Blend")
    print("═" * 72)
    print(f"  Universe: {len(UNIVERSE)} stocks | IS: {IS_START.date()}–{IS_END.date()} "
          f"| OOS: {OOS_START.date()}–{OOS_END.date()}")
    print(f"  Top-{TOP_N}, equal-weight, monthly rebalance, TC={TC_BPS}bps")

    monthly = fetch_monthly_prices()
    print(f"  Price matrix: {monthly.shape[0]} months × {monthly.shape[1]} tickers "
          f"({monthly.index[0].date()} → {monthly.index[-1].date()})")

    # H198 baseline for comparison (6-1m = variant B without 6m)
    def h198_signal(monthly, t):
        if len(monthly) <= t + 1:
            return None
        r12s = (monthly.iloc[t] / monthly.iloc[max(0, t - 12)] - 1).dropna()
        if len(r12s) < TOP_N:
            return None
        return rank_cs(r12s)

    def backtest_h198(monthly):
        rets_df = monthly.pct_change()
        tc      = TC_BPS / 10_000
        results = []
        prev    = []
        for t in range(13, len(monthly)):
            dt    = monthly.index[t]
            score = h198_signal(monthly, t - 1)
            if score is None:
                continue
            holdings  = list(score.nlargest(TOP_N).index)
            turnover  = len(set(holdings) - set(prev)) / TOP_N
            row       = rets_df.iloc[t]
            valid     = [s for s in holdings if s in row and not np.isnan(row[s])]
            if not valid:
                continue
            results.append((dt, float(row[valid].mean()) - turnover * tc))
            prev = holdings
        if not results:
            return pd.Series(dtype=float)
        return pd.Series([r for _, r in results], index=pd.DatetimeIndex([d for d, _ in results]))

    results = {}
    all_variants = [
        ("A", "rank(R_1m)+rank(R_6m)+rank(R_12m) — all windows"),
        ("B", "rank(R_6m_skip)+rank(R_12m_skip) — skip-1 blend"),
        ("C", "rank(R_1_1)+rank(R_2_6)+rank(R_7_12) — non-overlapping"),
        ("D", "rank(R_1_1)+rank(R_2_6)+rank(R_7_12)+rank(R_13_60) — full paper"),
    ]

    # Also run H198 as baseline
    print(f"\n  Running H198 baseline (6-1m single window)…")
    h198_full = backtest_h198(monthly)
    h198_is   = h198_full.loc[IS_START:IS_END]
    h198_oos  = h198_full.loc[OOS_START:OOS_END]
    h198_stats = {
        "full": summary_stats(h198_full, "H198-baseline"),
        "is":   summary_stats(h198_is, "H198-IS"),
        "oos":  summary_stats(h198_oos, "H198-OOS"),
    }
    print(f"  H198 OOS: Sharpe={h198_stats['oos']['sharpe']:.3f}  "
          f"CAGR={h198_stats['oos']['ann_ret']:.1%}  MaxDD={h198_stats['oos']['maxdd']:.1%}")

    # Run all H223 variants
    best_variant = None
    best_oos_sharpe = 0.0

    print(f"\n  {'Variant':<6}  {'IS Sharpe':>10}  {'OOS Sharpe':>11}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'Confirmed':>9}")
    print(f"  {'-'*66}")

    for variant, desc in all_variants:
        full_r = backtest_variant(monthly, variant)
        is_r   = full_r.loc[IS_START:IS_END]   if not full_r.empty else pd.Series(dtype=float)
        oos_r  = full_r.loc[OOS_START:OOS_END] if not full_r.empty else pd.Series(dtype=float)

        is_s  = summary_stats(is_r, f"H223-{variant}-IS")
        oos_s = summary_stats(oos_r, f"H223-{variant}-OOS")
        full_s = summary_stats(full_r, f"H223-{variant}-full")

        confirmed = oos_s.get("sharpe", 0) > 1.4

        print(f"  {variant:<6}  {is_s.get('sharpe', 0):>10.3f}  {oos_s.get('sharpe', 0):>11.3f}"
              f"  {oos_s.get('ann_ret', 0):>8.1%}  {oos_s.get('maxdd', 0):>9.1%}"
              f"  {'YES ✓' if confirmed else 'no':>9}")
        print(f"         {desc}")

        results[f"variant_{variant}"] = {
            "description": desc,
            "is":   is_s,
            "oos":  oos_s,
            "full": full_s,
            "confirmed": confirmed,
        }

        if oos_s.get("sharpe", 0) > best_oos_sharpe:
            best_oos_sharpe  = oos_s.get("sharpe", 0)
            best_variant     = variant

    # ── Summary ───────────────────────────────────────────────────────────────
    overall_confirmed = any(
        v["confirmed"] for v in results.values()
    )
    best_oos = max(
        (v["oos"].get("sharpe", 0) for v in results.values()), default=0
    )

    print(f"\n  {'═'*66}")
    print(f"  H198 baseline OOS Sharpe : {h198_stats['oos']['sharpe']:.3f}")
    print(f"  H223 best OOS Sharpe     : {best_oos:.3f}  (Variant {best_variant})")
    print(f"  Confirm threshold        : 1.400")
    print(f"  Overall confirmed        : {'YES — H223 CONFIRMED' if overall_confirmed else 'NOT CONFIRMED'}")
    print(f"  Beat H198 OOS?           : {'YES' if best_oos > h198_stats['oos']['sharpe'] else 'NO'}")

    output = {
        "hypothesis":         "H223",
        "strategy":           "Multi-Window Momentum Blend",
        "universe_n":         len(UNIVERSE),
        "top_n":              TOP_N,
        "tc_bps":             TC_BPS,
        "is_period":          f"{IS_START.date()}–{IS_END.date()}",
        "oos_period":         f"{OOS_START.date()}–{OOS_END.date()}",
        "confirm_threshold":  1.4,
        "overall_confirmed":  overall_confirmed,
        "best_variant":       best_variant,
        "best_oos_sharpe":    round(best_oos, 4),
        "h198_baseline":      h198_stats,
        "variants":           results,
    }

    out_path = RESULT_DIR / "h223_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results → {out_path}")
    return output


if __name__ == "__main__":
    main()
