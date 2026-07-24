#!/usr/bin/env python3
"""
H436 — Relative Strength vs SPY on H026 25-Asset ETF Universe
==============================================================
Tests whether selecting ETFs by their EXCESS 12-month return vs SPY
(alpha momentum) outperforms raw 12-month momentum rotation.

Motivation: Cross-sectional ETF rotation already captures beta to equity
markets via SPY-correlated assets. Removing the common SPY factor focuses
selection on genuinely outperforming assets (relative alpha), which may
improve diversification and robustness across regimes.

Variants:
  A: Pure relative strength: rank(12m_excess_vs_SPY) → top-1
  B: Relative strength filtered: require own 12m > 0 (absolute mom positive)
  C: Combo 50/50: rank(abs_12m) + rank(rel_12m) → top-1
  D: H026 canonical: rank(12m) + rank(inv_6m_vol) → top-1 (proper replication)
  E: Relative + vol: rank(rel_12m) + rank(inv_6m_vol) → top-1
  F: Relative 6-month excess vs SPY → top-1 (shorter window)

Gate: OOS Sharpe > 1.200 (H026 canonical baseline)
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
CASH        = "BIL"
BENCHMARK   = "SPY"
ALL_TICKERS = UNIVERSE + [CASH, BENCHMARK]

DATA_START = "2006-01-01"
DATA_END   = "2026-07-01"
IS_START   = pd.Timestamp("2008-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-07-01")
TC         = 0.001
GATE       = 1.200


# ── Data ─────────────────────────────────────────────────────────────────────

def load_daily(ticker: str) -> pd.Series:
    for prefix in ["h435","h346","h345","h344","h343","h436"]:
        for fname in [f"{prefix}_{ticker}_close.parquet",
                      f"{prefix}_{ticker}_daily.parquet"]:
            p = CACHE_DIR / fname
            if p.exists():
                df = pd.read_parquet(p)
                s = df.squeeze()
                s.name = ticker
                return s.sort_index()
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    close = raw["Close"].dropna()
    close.name = ticker
    pd.DataFrame(close).to_parquet(CACHE_DIR / f"h436_{ticker}_close.parquet")
    return close.sort_index()


def build_monthly(daily: dict) -> pd.DataFrame:
    return pd.DataFrame({t: s.resample("ME").last() for t, s in daily.items()}).sort_index()


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_variant(label: str, monthly_px: pd.DataFrame, score_df: pd.DataFrame,
                abs_filter: bool = False, abs_mom: pd.DataFrame = None) -> pd.Series:
    mret = monthly_px.pct_change()
    port_rets, prev = [], None

    for i, dt in enumerate(mret.index):
        if dt < IS_START:
            continue
        if dt not in score_df.index:
            port_rets.append((dt, 0.0))
            continue

        scores = score_df.loc[dt].reindex(UNIVERSE).dropna()

        if abs_filter and abs_mom is not None and dt in abs_mom.index:
            abs_s = abs_mom.loc[dt].reindex(UNIVERSE)
            scores = scores[abs_s.fillna(-1) > 0]

        if len(scores) == 0:
            winner = CASH
        else:
            winner = scores.idxmax()

        tc_cost = TC if (prev is not None and prev != winner) else 0.0
        ret_row = mret.iloc[i]
        ret_this = float(ret_row.get(winner, 0.0)) - tc_cost
        port_rets.append((dt, ret_this))
        prev = winner

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Metrics ───────────────────────────────────────────────────────────────────

def sharpe(r): return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())
def cagr(r): return float(r.mean() * 12)
def neg_years(r):
    ann = r.resample("YE").apply(lambda x: (1+x).prod()-1)
    return int((ann < 0).sum())
def wf_ratio(is_sh, oos_sh): return round(oos_sh / is_sh, 3) if is_sh > 0 else 0.0

def eval_p(r, start, end):
    sub = r[(r.index >= start) & (r.index <= end)]
    if len(sub) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(sub), "sharpe": round(sharpe(sub), 3),
            "maxdd": round(maxdd(sub), 3), "cagr": round(cagr(sub), 3),
            "neg_yrs": neg_years(sub)}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("H436 — Relative Strength vs SPY on H026 25-Asset ETF Universe")
    print("=" * 68)

    print("Loading prices…")
    daily = {}
    for t in ALL_TICKERS:
        try:
            daily[t] = load_daily(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    print(f"  Loaded {len(daily)} tickers")

    monthly_px = build_monthly(daily).loc[DATA_START:DATA_END]
    midx = monthly_px.index

    # ── Signals (all lagged 1 month via shift(1) in pct_change) ──────────────
    # 12m momentum lagged: shift(1) ensures we use prior-month-end price
    mom12  = monthly_px.shift(1).pct_change(12)
    mom6   = monthly_px.shift(1).pct_change(6)

    spy12  = mom12[BENCHMARK] if BENCHMARK in mom12.columns else pd.Series(0.0, index=midx)
    spy6   = mom6[BENCHMARK] if BENCHMARK in mom6.columns else pd.Series(0.0, index=midx)

    # Relative strength: excess 12m return vs SPY (subtract SPY's 12m return)
    rel12 = mom12[UNIVERSE].subtract(spy12, axis=0)
    rel6  = mom6[UNIVERSE].subtract(spy6, axis=0)

    # Inverse 6m volatility (using monthly returns over 6 months)
    mret6 = monthly_px.pct_change().rolling(6, min_periods=3).std().shift(1)
    inv_vol6 = (1.0 / mret6[UNIVERSE]).replace([np.inf, -np.inf], np.nan)

    # Ranked signals
    rank_abs12   = mom12[UNIVERSE].rank(axis=1, pct=True)
    rank_rel12   = rel12.rank(axis=1, pct=True)
    rank_rel6    = rel6.rank(axis=1, pct=True)
    rank_invvol  = inv_vol6.rank(axis=1, pct=True)

    # Variant score matrices
    score_A = rank_rel12
    score_C = 0.5 * rank_abs12 + 0.5 * rank_rel12
    score_D = rank_abs12 + rank_invvol        # canonical H026 dual rank
    score_E = rank_rel12 + rank_invvol        # relative + vol
    score_F = rank_rel6                       # 6-month relative

    results = {}
    variants = [
        ("A", "Pure relative strength (12m excess vs SPY) top-1", score_A, False),
        ("B", "Relative strength + abs_mom>0 filter",             score_A, True),
        ("C", "50/50 abs_mom+relative combo",                     score_C, False),
        ("D", "H026 canonical: rank(12m)+rank(inv_vol6) top-1",  score_D, False),
        ("E", "Relative+vol: rank(rel12)+rank(inv_vol6)",        score_E, False),
        ("F", "6-month relative strength top-1",                  score_F, False),
    ]

    abs_mom_raw = mom12[UNIVERSE]

    for var, desc, score, do_filter in variants:
        print(f"\n  Var {var}: {desc}")
        rets = run_variant(var, monthly_px, score,
                           abs_filter=do_filter,
                           abs_mom=abs_mom_raw if do_filter else None)
        is_m  = eval_p(rets, IS_START, IS_END)
        oos_m = eval_p(rets, OOS_START, OOS_END)
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
        "hypothesis": "H436",
        "title": "Relative Strength vs SPY on H026 25-Asset ETF Universe",
        "gate_oos_sharpe": GATE,
        "universe": UNIVERSE,
        "is_period":  f"{IS_START.date()} – {IS_END.date()}",
        "oos_period": f"{OOS_START.date()} – {OOS_END.date()}",
        "variants": results,
    }
    out_path = RESULT_DIR / "h436_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved → {out_path}")

    n_pass = sum(1 for v in results.values() if v["passed_gate"])
    print(f"\nSummary: {n_pass}/{len(results)} variants pass OOS Sharpe > {GATE}")


if __name__ == "__main__":
    main()
