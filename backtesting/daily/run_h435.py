#!/usr/bin/env python3
"""
H435 — 52-Week High Proximity Momentum on H026 25-Asset ETF Universe
=====================================================================
George & Hwang (2004) showed stocks near their 52-week high outperform —
the intuition is that investors use the 52WH as a reference point and
resist buying near the high, creating underreaction to positive news.

On ETFs the mechanism shifts: proximity to 52WH serves as a trend-quality
filter — assets closer to their annual peak are in persistent uptrends,
while assets far from their high are in drawdown or choppy regimes.

Signal variants:
  A: Pure 52WH proximity: rank(P / max52w) → top-1 (no momentum)
  B: 12m momentum top-1 with 52WH drawdown filter: if winner price < 75%
     of its own 52WH → skip to BIL (filtering near-bottom assets)
  C: Combo 50/50: rank(12m_mom) + rank(P/max52w) → top-1
  D: Trend consistency (% positive months in past 12) → top-1
  E: Combo: rank(12m_mom) + rank(trend_consistency) → top-1
  F: H026 baseline (12m top-1, no filter) — replication

Gate: OOS Sharpe > 1.200 (H026 standalone, canonical IS 2008-17/OOS 2018-26)
IS:   2008-01-01 – 2017-12-31
OOS:  2018-01-01 – 2026-07-01
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

UNIVERSE = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
    "IBB","XME",
]
CASH     = "BIL"
ALL_TICKERS = UNIVERSE + [CASH]

DATA_START = "2006-01-01"
DATA_END   = "2026-07-01"
IS_START   = pd.Timestamp("2008-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-07-01")
TC         = 0.001   # 10 bp per leg
GATE       = 1.200   # H026 standalone OOS Sharpe


# ── Data ─────────────────────────────────────────────────────────────────────

def load_daily(ticker: str) -> pd.Series:
    # reuse cached data from h346 or earlier runs
    for prefix in ["h346","h345","h344","h343","h435"]:
        for fname in [
            f"{prefix}_{ticker}_close.parquet",
            f"{prefix}_{ticker}_daily.parquet",
        ]:
            p = CACHE_DIR / fname
            if p.exists():
                df = pd.read_parquet(p)
                s = df.squeeze() if hasattr(df, 'squeeze') else df.iloc[:,0]
                s.name = ticker
                return s.sort_index()

    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1) if ticker in raw.columns.get_level_values(1) else raw
    close = raw["Close"].dropna()
    close.name = ticker
    pd.DataFrame(close).to_parquet(CACHE_DIR / f"h435_{ticker}_close.parquet")
    return close.sort_index()


def build_monthly(closes_daily: dict) -> pd.DataFrame:
    frames = {}
    for t, s in closes_daily.items():
        frames[t] = s.resample("ME").last()
    df = pd.DataFrame(frames).sort_index()
    return df


# ── Signal builders ───────────────────────────────────────────────────────────

def mom_12(monthly_px: pd.DataFrame) -> pd.DataFrame:
    """12-month momentum (skip 0), lagged 1 month."""
    r = monthly_px.shift(1).pct_change(12)
    return r


def proximity_52wh(daily_closes: dict, monthly_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Ratio of month-end close to trailing 252-day high, resampled to monthly."""
    frames = {}
    for t, s in daily_closes.items():
        if t == CASH:
            continue
        max52 = s.rolling(252, min_periods=126).max()
        ratio = (s / max52).replace([np.inf, -np.inf], np.nan)
        frames[t] = ratio.resample("ME").last()
    df = pd.DataFrame(frames).sort_index()
    return df.reindex(monthly_index, method="ffill")


def trend_consistency(monthly_px: pd.DataFrame) -> pd.DataFrame:
    """Fraction of positive monthly returns in trailing 12 months, shifted 1m."""
    mret = monthly_px.pct_change()
    pos  = (mret > 0).astype(float).rolling(12, min_periods=6).mean()
    return pos.shift(1)


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_variant(label: str, monthly_px: pd.DataFrame, score_df: pd.DataFrame,
                override_fn=None) -> pd.Series:
    """
    Top-1 selection based on score_df each month.
    override_fn(month_end, winner, monthly_px) -> ticker or None
      Used for Var B filter: if it returns 'BIL', force cash.
    """
    mret = monthly_px.pct_change()
    port_rets, prev_pos = [], None

    for i, dt in enumerate(mret.index):
        if dt < IS_START:
            continue
        scores = score_df.loc[dt].dropna() if dt in score_df.index else pd.Series(dtype=float)
        scores = scores[scores.index.isin(UNIVERSE)]
        scores = scores.dropna()

        if len(scores) == 0:
            winner = CASH
        else:
            winner = scores.idxmax()

        # Var B override: drawdown filter
        if override_fn is not None and winner != CASH:
            override = override_fn(dt, winner, monthly_px)
            if override is not None:
                winner = override

        tc_cost = TC if (prev_pos is not None and prev_pos != winner) else 0.0
        ret_this = float(mret.iloc[i].get(winner, 0.0)) - tc_cost
        port_rets.append((dt, ret_this))
        prev_pos = winner

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Metrics ───────────────────────────────────────────────────────────────────

def sharpe(r: pd.Series) -> float:
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def cagr(r: pd.Series) -> float:
    return float(r.mean() * 12)

def neg_years(r: pd.Series) -> int:
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def wf_ratio(is_sharpe: float, oos_sharpe: float) -> float:
    return round(oos_sharpe / is_sharpe, 3) if is_sharpe > 0 else 0.0

def eval_period(r: pd.Series, start, end) -> dict:
    sub = r[(r.index >= start) & (r.index <= end)]
    if len(sub) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {
        "n":       len(sub),
        "sharpe":  round(sharpe(sub), 3),
        "maxdd":   round(maxdd(sub), 3),
        "cagr":    round(cagr(sub), 3),
        "neg_yrs": neg_years(sub),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("H435 — 52-Week High Proximity Momentum on H026 25-Asset ETF Universe")
    print("=" * 70)

    print("Loading daily prices…")
    daily = {}
    for t in ALL_TICKERS:
        try:
            daily[t] = load_daily(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    print(f"  Loaded {len(daily)} tickers")

    monthly_px = build_monthly(daily)
    monthly_px = monthly_px.loc[DATA_START:DATA_END]
    midx = monthly_px.index

    print("Computing signals…")
    mom12    = mom_12(monthly_px)
    prox52   = proximity_52wh({t: daily[t] for t in daily if t != CASH}, midx)
    consist  = trend_consistency(monthly_px)

    # Ranked signals (percentile across universe each month)
    # IMPORTANT: prox52 is computed from month-end prices; must shift(1) so
    # selection uses PRIOR month-end proximity, not current — avoids look-ahead.
    rank_mom   = mom12[UNIVERSE].rank(axis=1, pct=True)
    rank_prox  = prox52[UNIVERSE].shift(1).rank(axis=1, pct=True)
    rank_cons  = consist[UNIVERSE].rank(axis=1, pct=True)  # already shift(1) inside

    # Score matrices
    score_A = rank_prox                            # pure 52WH proximity
    score_C = 0.5 * rank_mom + 0.5 * rank_prox    # combo mom+52WH
    score_D = rank_cons                            # trend consistency
    score_E = 0.5 * rank_mom + 0.5 * rank_cons    # combo mom+consistency
    score_F = rank_mom                             # baseline H026

    prox52_lag = prox52.shift(1)  # lagged proximity for causal selection

    def filter_B(dt, winner, mpx):
        """If winner is more than 25% below its prior-month 52WH, use BIL."""
        if dt not in prox52_lag.index:
            return None
        ratio = prox52_lag.loc[dt].get(winner, np.nan)
        if pd.isna(ratio) or ratio < 0.75:
            return CASH
        return None

    variants = {
        "A": ("Pure 52WH Proximity top-1",       score_A, None),
        "B": ("12m mom top-1 + 52WH<0.75→BIL",  score_F, filter_B),
        "C": ("50/50 mom+52WH combo",             score_C, None),
        "D": ("Trend Consistency top-1",          score_D, None),
        "E": ("50/50 mom+Consistency combo",      score_E, None),
        "F": ("H026 baseline (12m top-1)",        score_F, None),
    }

    results = {}
    for var, (desc, score, ovr) in variants.items():
        print(f"\n  Var {var}: {desc}")
        rets = run_variant(var, monthly_px, score, override_fn=ovr)
        is_m  = eval_period(rets, IS_START,  IS_END)
        oos_m = eval_period(rets, OOS_START, OOS_END)
        wf    = wf_ratio(is_m["sharpe"], oos_m["sharpe"])
        passed = oos_m["sharpe"] >= GATE
        print(f"    IS  Sharpe={is_m['sharpe']:.3f}  MaxDD={is_m['maxdd']:.3f}")
        print(f"    OOS Sharpe={oos_m['sharpe']:.3f}  MaxDD={oos_m['maxdd']:.3f}  "
              f"WF={wf:.2f}  neg_yrs={oos_m['neg_yrs']}  {'✅ PASS' if passed else '❌'}")
        results[f"Var_{var}"] = {
            "description": desc, "is": is_m, "oos": oos_m,
            "wf_ratio": wf, "passed_gate": passed,
        }

    out = {
        "hypothesis": "H435",
        "title": "52-Week High Proximity Momentum on H026 25-Asset ETF Universe",
        "gate_oos_sharpe": GATE,
        "universe": UNIVERSE,
        "is_period":  f"{IS_START.date()} – {IS_END.date()}",
        "oos_period": f"{OOS_START.date()} – {OOS_END.date()}",
        "variants": results,
    }
    out_path = RESULT_DIR / "h435_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved → {out_path}")

    n_pass = sum(1 for v in results.values() if v["passed_gate"])
    print(f"\nSummary: {n_pass}/{len(results)} variants pass OOS Sharpe > {GATE}")


if __name__ == "__main__":
    main()
