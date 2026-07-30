#!/usr/bin/env python3
"""
H478 — Golden Criterion Adaptive Equal-Weight vs Top-1 for H026 ETF Rotation
Source: arXiv:2607.11054 (Feng, Huang, Wang, Zhang, Jul 2026)

1/N (equal weight) is minimum-variance optimal when forecast-error covariance
has uniform eigenstructure — the 'Golden Criterion'. D = std(λ)/mean(λ) where
λ are eigenvalues of trailing monthly return covariance of top-k ETFs.
When D < threshold → EW top-3 (momentum signal is noisy, diversify).
When D >= threshold → top-1 (momentum signal is reliable, concentrate).

Directly addresses H026 OOS degradation (0.785 vs 1.2 IS Sharpe).

Variants:
  Var A: Golden Criterion gate (D threshold at IS 75th percentile)
  Var B: Golden Criterion gate (D threshold at IS 50th percentile — more switching)
  Var C: Always EW top-3 (no criterion, pure diversification benchmark)
  Var D: Always EW top-5
  Var E: H026 canonical top-1 (baseline)

Gate: OOS Sharpe > 2.610 (H346 OB-gated baseline) AND MaxDD improvement vs -5%
IS: 2008-2017  OOS: 2018-2026
Universe: H026 25-asset ETF universe
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

H026_UNIVERSE = [
    "SPY", "QQQ", "IWM", "EFA", "EEM", "VNQ", "GLD", "SLV", "USO", "TLT",
    "IEF", "LQD", "HYG", "XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI",
    "XLU", "XLB", "XLC", "XLRE", "BIL",
]
IS_START, IS_END = "2008-01-01", "2017-12-31"
OOS_START, OOS_END = "2018-01-01", "2026-06-30"
MOMENTUM_WINDOW = 12     # 12-month trailing momentum
EIGENVALUE_WINDOW = 12   # months of covariance history for Golden Criterion
TOP_K_CRIT = 5           # top-k ETFs used to compute eigenstructure
GATE_SHARPE = 2.610
REGULARIZATION = 0.1     # shrinkage toward identity for covariance


def compute_golden_criterion_D(returns_subset: pd.DataFrame) -> float:
    """Compute D = std(λ)/mean(λ) — distance from uniform eigenstructure."""
    cov = returns_subset.cov()
    n = len(cov)
    cov_reg = (1 - REGULARIZATION) * cov + REGULARIZATION * (np.trace(cov) / n) * np.eye(n)
    lambdas = np.linalg.eigvalsh(cov_reg)
    lambdas = lambdas[lambdas > 1e-10]
    if len(lambdas) < 2:
        return np.nan
    return float(np.std(lambdas) / np.mean(lambdas))


def run_variant(monthly_ret: pd.DataFrame, signal: pd.DataFrame, variant: str,
                d_threshold: float = None) -> pd.Series:
    portfolio_returns = []
    dates = signal.index[EIGENVALUE_WINDOW:]

    for date in dates:
        row = signal.loc[date].dropna()
        row = row[row.index != "BIL"]  # BIL is cash proxy, exclude from ranking
        if len(row) < 5:
            portfolio_returns.append(np.nan)
            continue

        top5 = row.nlargest(TOP_K_CRIT).index.tolist()

        if variant == "E":
            selected = [top5[0]]
            weights = {selected[0]: 1.0}

        elif variant in ("A", "B"):
            # Compute Golden Criterion D from trailing EIGENVALUE_WINDOW months
            hist_end_idx = monthly_ret.index.get_loc(date)
            if hist_end_idx < EIGENVALUE_WINDOW:
                selected = [top5[0]]
                weights = {selected[0]: 1.0}
            else:
                hist = monthly_ret.iloc[hist_end_idx - EIGENVALUE_WINDOW:hist_end_idx][top5]
                D = compute_golden_criterion_D(hist)
                if pd.isna(D) or (d_threshold is not None and D >= d_threshold):
                    # Signal concentrated → top-1
                    selected = [top5[0]]
                    weights = {selected[0]: 1.0}
                else:
                    # Signal uniform → EW top-3
                    selected = top5[:3]
                    weights = {t: 1 / 3 for t in selected}

        elif variant == "C":
            selected = top5[:3]
            weights = {t: 1 / 3 for t in selected}

        elif variant == "D":
            selected = top5[:5]
            weights = {t: 1 / 5 for t in selected}

        else:
            selected = [top5[0]]
            weights = {selected[0]: 1.0}

        if date not in monthly_ret.index:
            portfolio_returns.append(np.nan)
            continue

        ret_row = monthly_ret.loc[date]
        port_ret = sum(weights.get(t, 0) * ret_row.get(t, 0) for t in weights)
        portfolio_returns.append(port_ret)

    return pd.Series(portfolio_returns, index=dates).dropna()


def evaluate(returns: pd.Series, label: str):
    ann = returns.mean() * 12
    vol = returns.std() * np.sqrt(12)
    sharpe = ann / vol if vol > 0 else 0.0
    cum = (1 + returns).cumprod()
    mdd = (cum / cum.cummax() - 1).min()
    neg_years = (returns.resample("YE").sum() < 0).sum()
    print(f"  {label}: Sharpe={sharpe:.3f}  CAGR={ann:.1%}  MaxDD={mdd:.1%}  NegYears={neg_years}")
    return sharpe, mdd


if __name__ == "__main__":
    print("H478 — Golden Criterion Adaptive EW vs Top-1 for H026")
    print("Downloading data...")
    raw = yf.download(H026_UNIVERSE, start="2007-01-01", end=OOS_END, auto_adjust=True, progress=False)
    prices = raw["Close"].dropna(axis=1, how="all")

    monthly_ret = prices.resample("MS").last().pct_change()
    signal = prices.resample("MS").last().pct_change(MOMENTUM_WINDOW).shift(1)

    # Calibrate D thresholds on IS period
    is_dates = signal.loc[IS_START:IS_END].index
    d_values = []
    for date in is_dates[EIGENVALUE_WINDOW:]:
        row = signal.loc[date].dropna()
        row = row[row.index != "BIL"]
        top5 = row.nlargest(TOP_K_CRIT).index.tolist() if len(row) >= TOP_K_CRIT else list(row.index)
        idx = monthly_ret.index.get_loc(date)
        if idx >= EIGENVALUE_WINDOW:
            hist = monthly_ret.iloc[idx - EIGENVALUE_WINDOW:idx][top5]
            D = compute_golden_criterion_D(hist)
            if not np.isnan(D):
                d_values.append(D)

    d75 = np.percentile(d_values, 75) if d_values else 1.0
    d50 = np.percentile(d_values, 50) if d_values else 1.0
    print(f"IS D-values: median={d50:.3f}  75th-pct={d75:.3f}")

    thresholds = {"A": d75, "B": d50, "C": None, "D": None, "E": None}
    results = {}
    for var in ["A", "B", "C", "D", "E"]:
        print(f"\nVar {var}:")
        strat = run_variant(monthly_ret, signal, var, d_threshold=thresholds[var])
        is_r = strat.loc[IS_START:IS_END]
        oos_r = strat.loc[OOS_START:OOS_END]
        is_sh, _ = evaluate(is_r, "IS")
        oos_sh, oos_mdd = evaluate(oos_r, "OOS")
        results[f"Var{var}"] = {"is_sharpe": round(is_sh, 3), "oos_sharpe": round(oos_sh, 3), "oos_mdd": round(float(oos_mdd), 4)}

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement vs -5%")
    for k, v in results.items():
        passed = v["oos_sharpe"] > GATE_SHARPE
        print(f"  {k}: OOS={v['oos_sharpe']:.3f}  MDD={v['oos_mdd']:.1%}  {'PASS' if passed else 'FAIL'}")
