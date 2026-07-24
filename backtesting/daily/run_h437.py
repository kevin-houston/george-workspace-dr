#!/usr/bin/env python3
"""
H437 — Beta-Adjusted Alpha Rotation on H026 25-Asset ETF Universe
=================================================================
Tests whether ranking ETFs by Jensen's alpha (12m return minus beta×SPY
12m return) outperforms raw momentum rotation.

Motivation: Raw 12m momentum rewards beta exposure to SPY in bull markets.
By removing the market factor (beta), we focus selection on genuine
idiosyncratic alpha — which should be more persistent and less correlated
with market direction.

H341 tested this on H198 stocks and got NOT CONFIRMED (OOS 0.984 < gate
1.174). However, H026 is a multi-asset universe (bonds, commodities, sectors)
where beta vs SPY varies dramatically. The beta-adjustment should have more
discriminatory power when assets have very different market sensitivities.

Variants:
  A: Pure alpha (12m return - beta12m × SPY_12m) → top-1
  B: Alpha magnitude filter: only buy if alpha > 0 (else BIL)
  C: 50/50 combo: rank(alpha) + rank(abs_12m) → top-1
  D: Trailing 12m Sharpe ratio ranking → top-1 [H438 preview]
  E: rank(alpha) + rank(inv_vol) → top-1
  F: H026 canonical: rank(12m)+rank(inv_vol) → top-1 (baseline)

Gate: OOS Sharpe > 1.200
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
CASH      = "BIL"
BENCHMARK = "SPY"
ALL_TICKS = UNIVERSE + [CASH, BENCHMARK]

DATA_START = "2006-01-01"
DATA_END   = "2026-07-01"
IS_START   = pd.Timestamp("2008-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-07-01")
TC         = 0.001
GATE       = 1.200
BETA_WINDOW = 12  # months for beta estimation


def load_daily(ticker):
    for prefix in ["h435","h436","h346","h437"]:
        for fname in [f"{prefix}_{ticker}_close.parquet",
                      f"{prefix}_{ticker}_daily.parquet"]:
            p = CACHE_DIR / fname
            if p.exists():
                return pd.read_parquet(p).squeeze().sort_index().rename(ticker)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].dropna().rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h437_{ticker}_close.parquet")
    return s.sort_index()


def build_monthly(daily):
    return pd.DataFrame({t: s.resample("ME").last() for t, s in daily.items()}).sort_index()


def compute_rolling_beta(mret, spy_ret, window=12):
    """
    Rolling beta of each ETF vs SPY over `window` months.
    At each month t, use returns from t-window to t-1 (lagged).
    Returns DataFrame aligned to mret index.
    """
    result = pd.DataFrame(index=mret.index, columns=UNIVERSE, dtype=float)
    spy = spy_ret.reindex(mret.index)

    for i in range(window, len(mret)):
        spy_w = spy.iloc[i - window: i].values
        var_spy = np.var(spy_w, ddof=1)
        if var_spy < 1e-10:
            continue
        for t in UNIVERSE:
            if t not in mret.columns:
                continue
            etf_w = mret[t].iloc[i - window: i].values
            cov = np.cov(etf_w, spy_w, ddof=1)[0, 1]
            result.loc[mret.index[i], t] = cov / var_spy

    return result.astype(float)


def sharpe(r): return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())
def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())
def wf_ratio(a, b): return round(b / a, 3) if a > 0 else 0.0

def eval_p(r, s, e):
    sub = r[(r.index >= s) & (r.index <= e)]
    if len(sub) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(sub), "sharpe": round(sharpe(sub), 3),
            "maxdd": round(maxdd(sub), 3),
            "cagr": round(float(sub.mean() * 12), 3),
            "neg_yrs": neg_years(sub)}


def run_variant(monthly_px, score_df, filter_pos_alpha=False, alpha_df=None):
    mret = monthly_px.pct_change()
    rets, prev = [], None
    for i, dt in enumerate(mret.index):
        if dt < IS_START:
            continue
        if dt not in score_df.index:
            rets.append((dt, 0.0))
            continue
        scores = score_df.loc[dt].reindex(UNIVERSE).dropna()
        if filter_pos_alpha and alpha_df is not None and dt in alpha_df.index:
            alpha_row = alpha_df.loc[dt].reindex(UNIVERSE)
            scores = scores[alpha_row.fillna(-999) > 0]
        if len(scores) == 0:
            winner = CASH
        else:
            winner = scores.idxmax()
        tc_cost = TC if (prev is not None and prev != winner) else 0.0
        ret_this = float(mret.iloc[i].get(winner, 0.0)) - tc_cost
        rets.append((dt, ret_this))
        prev = winner
    s = pd.Series({d: r for d, r in rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H437 — Beta-Adjusted Alpha Rotation on H026 25-Asset ETF Universe")
    print("=" * 68)

    print("Loading prices…")
    daily = {}
    for t in ALL_TICKS:
        try:
            daily[t] = load_daily(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    print(f"  Loaded {len(daily)} tickers")

    monthly_px = build_monthly(daily).loc[DATA_START:DATA_END]
    mret = monthly_px.pct_change()

    spy_ret = mret[BENCHMARK] if BENCHMARK in mret.columns else pd.Series(0.0, index=mret.index)

    # Lagged 12m momentum (shift(1) → uses prior month-end)
    mom12    = monthly_px.shift(1).pct_change(12)
    mret6_sd = mret.rolling(6, min_periods=3).std().shift(1)
    inv_vol6 = (1.0 / mret6_sd[UNIVERSE]).replace([np.inf, -np.inf], np.nan)

    # Trailing 12m Sharpe: mean/std of trailing 12 monthly returns (lagged 1m)
    trailing_mean = mret[UNIVERSE].rolling(12, min_periods=6).mean().shift(1)
    trailing_std  = mret[UNIVERSE].rolling(12, min_periods=6).std().shift(1)
    trailing_sharpe = (trailing_mean / trailing_std).replace([np.inf, -np.inf], np.nan)

    print("Computing rolling beta (12m window)…")
    beta_df = compute_rolling_beta(mret, spy_ret, BETA_WINDOW)
    spy_12m  = mom12[BENCHMARK] if BENCHMARK in mom12.columns else pd.Series(0.0, index=mom12.index)
    # Alpha = 12m ETF return - beta × SPY 12m return
    alpha_df = mom12[UNIVERSE].sub(beta_df.mul(spy_12m, axis=0), fill_value=np.nan)

    # Ranks
    rank_alpha  = alpha_df.rank(axis=1, pct=True)
    rank_mom    = mom12[UNIVERSE].rank(axis=1, pct=True)
    rank_invvol = inv_vol6.rank(axis=1, pct=True)
    rank_sharpe = trailing_sharpe.rank(axis=1, pct=True)

    # Score matrices
    score_A = rank_alpha
    score_C = 0.5 * rank_alpha + 0.5 * rank_mom
    score_D = rank_sharpe                          # trailing Sharpe ranking
    score_E = rank_alpha + rank_invvol
    score_F = rank_mom + rank_invvol               # H026 canonical

    results = {}
    configs = [
        ("A", "Pure alpha (12m ETF - beta×SPY_12m) top-1",   score_A, False, None),
        ("B", "Alpha top-1 + positive alpha filter",          score_A, True,  alpha_df),
        ("C", "50/50 combo: rank(alpha)+rank(12m)",           score_C, False, None),
        ("D", "Trailing 12m Sharpe ranking top-1",            score_D, False, None),
        ("E", "Alpha+inv_vol dual rank",                      score_E, False, None),
        ("F", "H026 canonical: 12m+inv_vol top-1 (baseline)", score_F, False, None),
    ]

    for var, desc, score, do_filter, afilt in configs:
        print(f"\n  Var {var}: {desc}")
        rets = run_variant(monthly_px, score, do_filter, afilt)
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
        "hypothesis": "H437",
        "title": "Beta-Adjusted Alpha + Trailing Sharpe Rotation on H026 ETF Universe",
        "gate_oos_sharpe": GATE,
        "universe": UNIVERSE,
        "is_period":  f"{IS_START.date()} – {IS_END.date()}",
        "oos_period": f"{OOS_START.date()} – {OOS_END.date()}",
        "variants": results,
    }
    out_path = RESULT_DIR / "h437_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved → {out_path}")
    n_pass = sum(1 for v in results.values() if v["passed_gate"])
    print(f"\nSummary: {n_pass}/{len(results)} variants pass OOS Sharpe > {GATE}")


if __name__ == "__main__":
    main()
