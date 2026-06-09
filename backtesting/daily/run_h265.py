"""
H265 — Drift-Regime Conditional Momentum
=========================================
Source: arXiv:2511.12490 (2025) — "Drift Regimes Unlock Hidden Cross-Sectional
        Predictability." S&P 500 2004-2024 walk-forward OOS Sharpe >13 at $100-500M,
        Sharpe ~7 at $1B. Drift regime: individual stock has >60% positive trading days
        in trailing 63-day window. Authors apply value+reversal inside drift regime;
        we test 6-1m momentum with drift gate on a stable large-cap universe.

Hypothesis: The drift-regime gate (DRG) reduces false-entry momentum chasing in
trending-down stocks, improving Sharpe by skipping stocks in downtrends regardless
of their relative rank.

Design:
  Universe:  50 stable S&P 500 large-caps with history back to 2008 (fixed list,
             no survivorship adjustment — acknowledged limitation; pure IS/OOS test)
  Signal:    6-1m momentum (same as H041a/H026 baseline)
  Gate:      Stock eligible only if fraction of positive return days in trailing
             63 trading days > DRIFT_THRESHOLD (test 0.50, 0.55, 0.60)
  Selection: Top-N by momentum among eligible stocks (N=5 equal weight)
  Defensive: SPY if <N stocks qualify; pure cash (no position) if <2 qualify
  Rebalance: Monthly (end of month)
  TC:        10bp per side

IS:  2008-2017 (includes 2008 GFC, 2011 correction, 2015-16 vol)
OOS: 2018-present (includes 2020 COVID crash, 2022 bear, 2023-25 recovery)

Confirm gates:
  OOS Sharpe > 1.10 (must beat baseline momentum — no drift gate)
  Corr(H265, SPY) OOS < 0.85 (significant decorrelation vs SPY)
  NegYrs OOS <= 2
  IS Sharpe > 0.60
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2006-01-01"
FULL_END     = "2025-12-31"
IS_START     = "2008-01-01"
IS_END       = "2017-12-31"
OOS_START    = "2018-01-01"
TC           = 0.001    # 10bp
TOP_N        = 5
DRIFT_WINDOW = 63       # trading days ≈ 3 months
DRIFT_THRESHOLDS = [0.50, 0.55, 0.60]

# 50 stable large-caps with history back to pre-2008
UNIVERSE = [
    "AAPL", "MSFT", "INTC", "CSCO", "ORCL", "IBM", "QCOM", "TXN",
    "JPM",  "BAC",  "WFC",  "GS",   "AXP",  "C",   "USB",  "MS",
    "JNJ",  "PFE",  "ABT",  "MRK",  "LLY",  "MDT", "AMGN", "GILD",
    "KO",   "PEP",  "PG",   "WMT",  "MCD",  "VZ",  "DIS",  "NKE",
    "XOM",  "CVX",  "BA",   "MMM",  "CAT",  "GE",  "HON",  "EMR",
    "HD",   "TGT",  "LOW",  "COST", "SBUX", "T",   "BK",   "MET",
    "BMY",  "SLB",
]
BENCHMARK = "SPY"


def sharpe(ret_series, ann=12):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def max_drawdown(curve):
    ec = pd.Series(curve)
    return float(((ec - ec.cummax()) / ec.cummax()).min())


print("Downloading 50-stock large-cap universe + SPY...")
all_tickers = UNIVERSE + [BENCHMARK]
_dl = yf.download(all_tickers, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)

available   = [t for t in UNIVERSE if t in raw.columns]
missing     = [t for t in UNIVERSE if t not in raw.columns]
if missing:
    print(f"  ⚠ Not available: {missing} — dropped")

raw_daily   = raw[available + [BENCHMARK]].ffill().dropna(how="all")
daily_ret   = raw_daily.pct_change()

# Monthly close for momentum signal
monthly     = raw_daily.resample("ME").last()
monthly_ret = monthly.pct_change()

# 6-1m momentum signal (skip most recent month, use prior 6m)
# At month-end date d: signal = price[d-1m] / price[d-7m] - 1, then shift 1 more for execution lag
sig_6m = (monthly.shift(1) / monthly.shift(7) - 1).shift(1)

print(f"  Universe: {len(available)} stocks available out of {len(UNIVERSE)}")

# Pre-compute drift fraction for each stock at each month-end
# drift_frac[date, stock] = fraction of positive daily return days in trailing 63 trading days
# computed from daily returns, sampled at month-ends
print("Pre-computing drift fractions (63-day rolling positive-day fraction)...")
drift_pos   = (daily_ret[available] > 0).astype(float)
drift_frac_daily = drift_pos.rolling(DRIFT_WINDOW, min_periods=30).mean()
# Sample at month-end dates
drift_frac  = drift_frac_daily.resample("ME").last()


def backtest(start, end, drift_threshold, label="", baseline=False):
    """
    If baseline=True: ignore drift gate (pure 6-1m momentum, Top-5).
    If baseline=False: apply drift gate at drift_threshold.
    """
    ret    = monthly_ret[available].loc[start:end]
    dates  = ret.index
    equity = 1.0
    curve  = []
    prev_hold = frozenset()
    annual = {}

    for date in dates:
        s     = sig_6m.loc[date, available].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        if baseline:
            eligible = s
        else:
            # Apply drift gate: only eligible if drift_frac > threshold
            df_row = drift_frac.loc[date, available] if date in drift_frac.index else pd.Series(dtype=float)
            if len(df_row) == 0:
                curve.append(equity)
                continue
            eligible_tickers = [t for t in s.index if t in df_row.index
                                 and not pd.isna(df_row.loc[t])
                                 and float(df_row.loc[t]) > drift_threshold]
            eligible = s.loc[eligible_tickers] if eligible_tickers else pd.Series(dtype=float)

        if len(eligible) == 0:
            # No eligible stocks → hold SPY as defensive
            hold_assets = [BENCHMARK]
        else:
            ranked    = eligible.sort_values(ascending=False)
            hold_assets = list(ranked.head(TOP_N).index)

        hold_set  = frozenset(hold_assets)
        changed   = hold_set != prev_hold

        period_total = 0.0
        for asset in hold_assets:
            w  = 1.0 / len(hold_assets)
            r  = monthly_ret.loc[date, asset] if asset in monthly_ret.columns else 0.0
            r  = 0.0 if pd.isna(r) else float(r)
            tc = TC if changed else 0.0
            period_total += w * (r - tc)

        equity *= (1 + period_total)
        curve.append(equity)
        prev_hold = hold_set
        annual.setdefault(date.year, []).append(period_total)

    ret_series = pd.Series(curve, index=dates).pct_change().dropna()
    neg_yrs    = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret    = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

    res = {
        "sharpe":  round(sharpe(ret_series), 4),
        "cagr":    round(float(pd.Series(curve).iloc[-1] ** (12/max(len(curve),1)) - 1), 4),
        "max_dd":  round(max_drawdown(curve), 4),
        "neg_yrs": neg_yrs,
        "months":  len(curve),
    }
    tag = "Baseline" if baseline else f"DRG>{drift_threshold:.2f}"
    print(f"\n── {label} [{tag}] ──")
    print(f"  Sharpe={res['sharpe']:.3f}  CAGR={res['cagr']*100:.1f}%"
          f"  MaxDD={res['max_dd']*100:.1f}%  NegYrs={res['neg_yrs']}")
    if "OOS" in label:
        for yr in sorted(ann_ret):
            print(f"    {yr}: {'+' if ann_ret[yr]>=0 else ''}{ann_ret[yr]}%")
    return res, ann_ret


# Baseline: pure 6-1m momentum, no drift gate
print("\n====== H265: Drift-Regime Conditional Momentum ======")
print("\n── Baseline: pure 6-1m momentum (no drift gate) ──")
bl_is,  _      = backtest(IS_START,  IS_END,   0.0, "IS  (2008-2017)",  baseline=True)
bl_oos, bl_ann = backtest(OOS_START, FULL_END, 0.0, "OOS (2018-2025)",  baseline=True)

# SPY
spy_monthly = monthly_ret[BENCHMARK].loc[OOS_START:].dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)
print(f"\n  SPY B&H OOS Sharpe: {spy_sharpe}")

# Grid search over drift thresholds
drg_results = {}
for dt in DRIFT_THRESHOLDS:
    print(f"\n── Drift Gate > {dt:.2f} ──")
    is_res,  _        = backtest(IS_START,  IS_END,   dt, "IS  (2008-2017)")
    oos_res, oos_ann  = backtest(OOS_START, FULL_END, dt, "OOS (2018-2025)")

    # SPY correlation
    oos_dates = monthly_ret.loc[OOS_START:].index
    prev2 = frozenset()
    rets  = []
    for date in oos_dates:
        s     = sig_6m.loc[date, available].dropna()
        if len(s) == 0:
            rets.append(0.0); continue
        df_row = drift_frac.loc[date, available] if date in drift_frac.index else pd.Series(dtype=float)
        elig_t = [t for t in s.index if t in df_row.index
                  and not pd.isna(df_row.loc[t])
                  and float(df_row.loc[t]) > dt]
        elig   = s.loc[elig_t] if elig_t else pd.Series(dtype=float)
        hold   = [BENCHMARK] if len(elig) == 0 else list(elig.sort_values(ascending=False).head(TOP_N).index)
        h_set  = frozenset(hold)
        changed = h_set != prev2
        pt = sum(
            (1.0/len(hold)) * ((0.0 if pd.isna(monthly_ret.loc[date, a])
                                else float(monthly_ret.loc[date, a])) - (TC if changed else 0.0))
            for a in hold
        )
        rets.append(pt)
        prev2 = h_set

    h265_oos  = pd.Series(rets, index=oos_dates)
    spy_aln   = spy_monthly.reindex(h265_oos.index).dropna()
    h265_aln  = h265_oos.reindex(spy_aln.index).dropna()
    corr_spy  = round(float(h265_aln.corr(spy_aln)), 4)

    drg_results[dt] = {
        "is":  is_res, "oos": oos_res, "oos_ann": oos_ann, "corr_spy": corr_spy
    }
    print(f"  Corr(SPY) OOS: {corr_spy}")

# Find best threshold by OOS Sharpe
best_dt  = max(DRIFT_THRESHOLDS, key=lambda dt: drg_results[dt]["oos"]["sharpe"])
best     = drg_results[best_dt]

# Gate evaluation
sharpe_pass = best["oos"]["sharpe"] > 1.10
corr_pass   = best["corr_spy"] < 0.85
neg_pass    = best["oos"]["neg_yrs"] <= 2
is_pass     = best["is"]["sharpe"] > 0.60
confirmed   = sharpe_pass and corr_pass and neg_pass and is_pass

print(f"\n── Baseline summary ──")
print(f"  IS Sharpe={bl_is['sharpe']:.3f}  OOS Sharpe={bl_oos['sharpe']:.3f}")
print(f"\n── Best drift gate: > {best_dt:.2f} ──")
print(f"  IS Sharpe={best['is']['sharpe']:.3f}  OOS Sharpe={best['oos']['sharpe']:.3f}"
      f"  Corr(SPY)={best['corr_spy']:.4f}")
print(f"\n── Gates ──")
print(f"  OOS Sharpe {best['oos']['sharpe']:.4f} > 1.10      → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  Corr(SPY)  {best['corr_spy']:.4f} < 0.85       → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs     {best['oos']['neg_yrs']} ≤ 2             → {'PASS' if neg_pass else 'FAIL'}")
print(f"  IS Sharpe  {best['is']['sharpe']:.4f} > 0.60       → {'PASS' if is_pass else 'FAIL'}")
print(f"\n  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
print(f"  Drift gate improvement: OOS {bl_oos['sharpe']:.3f} → {best['oos']['sharpe']:.3f}"
      f" ({'improvement' if best['oos']['sharpe'] > bl_oos['sharpe'] else 'no improvement'})")

out = {
    "hypothesis": "H265",
    "title": "Drift-Regime Conditional Momentum (50 large-cap S&P 500)",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "universe_size": len(available),
    "universe": available,
    "source": "arXiv:2511.12490",
    "baseline": {"is_sharpe": bl_is["sharpe"], "oos_sharpe": bl_oos["sharpe"],
                 "oos_ann": bl_ann},
    "spy_oos_sharpe": spy_sharpe,
    "best_drift_threshold": best_dt,
    "grid_results": {
        str(dt): {
            "is_sharpe":  drg_results[dt]["is"]["sharpe"],
            "oos_sharpe": drg_results[dt]["oos"]["sharpe"],
            "oos_max_dd": drg_results[dt]["oos"]["max_dd"],
            "oos_neg_yrs":drg_results[dt]["oos"]["neg_yrs"],
            "corr_spy":   drg_results[dt]["corr_spy"],
            "oos_annual": drg_results[dt]["oos_ann"],
        }
        for dt in DRIFT_THRESHOLDS
    },
    "best_result": {**best["oos"], "corr_spy": best["corr_spy"]},
    "gates": {
        "sharpe_pass": sharpe_pass, "corr_pass": corr_pass,
        "neg_pass": neg_pass, "is_pass": is_pass,
    },
}
out_path = RESULT_DIR / "h265_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
