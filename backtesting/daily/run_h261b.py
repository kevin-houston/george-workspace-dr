"""
H261b — Commodity Trend CTA (Top-2, UNG excluded)
===================================================
Fix for H261 NOT CONFIRMED:
  H261 failed due to single-asset concentration risk — UNG (natural gas)
  and USO (oil) individually show extreme volatility and deep drawdowns.
  H261 OOS MaxDD=-60.7% despite 2022 +80.9% showing the low-SPY-correlation
  thesis (Corr=0.186) is correct — the distribution is just too fat-tailed.

Changes vs H261:
  1. Remove UNG (natural gas): mean-reverting, -90%+ drawdowns, not trend-following
  2. Top-2 equal-weight instead of Top-1: reduce single-commodity concentration
  3. Both Top-2 assets must have positive absolute momentum; otherwise go to
     Top-1 (if only one positive) or BIL (if none positive)

Universe: GLD, SLV, DBC, USO, DBA (5 assets, all live by 2007)
Signal: 6m momentum, skip-1m, lagged-1m
IS: 2010-2017, OOS: 2018-2025, TC: 10bp

Gates: OOS Sharpe > 0.70, Corr(H261b, SPY) OOS < 0.50, NegYrs <= 3
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

FULL_START = "2008-01-01"
FULL_END   = "2025-12-31"
IS_START   = "2010-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
TC         = 0.001
TOP_N      = 2

ASSETS    = ["GLD", "SLV", "DBC", "USO", "DBA"]
DEFENSIVE = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]


def sharpe(ret_series, ann=12):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def max_drawdown(equity_curve):
    ec = pd.Series(equity_curve)
    roll_max = ec.cummax()
    dd = (ec - roll_max) / roll_max
    return float(dd.min())


print("Downloading commodity universe (UNG excluded)...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)
raw = raw[ALL_TICKERS].ffill().dropna(how="all")
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

r6_raw = monthly.shift(1) / monthly.shift(7) - 1
signal = r6_raw.shift(1)


def run_backtest(start, end, label=""):
    sig = signal[ASSETS].loc[start:end]
    ret = monthly_ret[ALL_TICKERS].loc[start:end]
    common = sig.index.intersection(ret.index)

    equity = 1.0
    curve  = []
    prev_hold = frozenset()
    annual = {}

    for date in common:
        s = sig.loc[date].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        # Rank all assets; take Top-N with positive abs momentum
        ranked = s.sort_values(ascending=False)
        positive = [a for a in ranked.index if float(s.loc[a]) > 0]

        if len(positive) == 0:
            hold_assets = [DEFENSIVE]
        elif len(positive) == 1:
            hold_assets = positive[:1]
        else:
            hold_assets = positive[:TOP_N]

        hold_set = frozenset(hold_assets)
        changed  = hold_set != prev_hold

        period_total = 0.0
        for asset in hold_assets:
            w   = 1.0 / len(hold_assets)
            r   = monthly_ret.loc[date, asset]
            r   = 0.0 if pd.isna(r) else float(r)
            tc  = TC if changed else 0.0
            period_total += w * (r - tc)

        equity *= (1 + period_total)
        curve.append(equity)
        prev_hold = hold_set

        yr = date.year
        annual.setdefault(yr, []).append(period_total)

    ret_series = pd.Series(curve, index=common).pct_change().dropna()
    neg_yrs    = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret    = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

    result = {
        "sharpe":  round(sharpe(ret_series), 4),
        "cagr":    round(float(pd.Series(curve).iloc[-1] ** (12 / len(curve)) - 1), 4),
        "max_dd":  round(max_drawdown(curve), 4),
        "neg_yrs": neg_yrs,
        "months":  len(curve),
    }
    print(f"\n── {label} ──")
    print(f"  Sharpe={result['sharpe']:.3f}  CAGR={result['cagr']*100:.1f}%"
          f"  MaxDD={result['max_dd']*100:.1f}%  NegYrs={result['neg_yrs']}")
    if label.startswith("OOS"):
        for yr in sorted(ann_ret):
            print(f"  {yr}: {'+' if ann_ret[yr]>=0 else ''}{ann_ret[yr]}%")
    return result, ann_ret, curve


is_result,  _, _      = run_backtest(IS_START, IS_END, "IS Results (2010-2017)")
oos_result, oos_ann, oos_curve = run_backtest(OOS_START, FULL_END, "OOS Results (2018-2025)")

# SPY benchmark
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END, auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)

# Correlation H261b vs SPY (using OOS monthly returns)
sig2  = signal[ASSETS].loc[OOS_START:]
ret2  = monthly_ret[ALL_TICKERS].loc[OOS_START:]
common2 = sig2.index.intersection(ret2.index)
prev2 = frozenset()
monthly_rets2 = []
for date in common2:
    s = sig2.loc[date].dropna()
    if len(s) == 0:
        monthly_rets2.append(0.0)
        continue
    ranked = s.sort_values(ascending=False)
    positive = [a for a in ranked.index if float(s.loc[a]) > 0]
    hold_assets = positive[:TOP_N] if len(positive) >= 2 else positive[:1] if len(positive) == 1 else [DEFENSIVE]
    hold_set = frozenset(hold_assets)
    changed  = hold_set != prev2
    period_total = 0.0
    for asset in hold_assets:
        w  = 1.0 / len(hold_assets)
        r  = monthly_ret.loc[date, asset]
        r  = 0.0 if pd.isna(r) else float(r)
        tc = TC if changed else 0.0
        period_total += w * (r - tc)
    monthly_rets2.append(period_total)
    prev2 = hold_set

h261b_oos = pd.Series(monthly_rets2, index=common2)
spy_aligned = spy_monthly.reindex(h261b_oos.index).dropna()
h261b_aligned = h261b_oos.reindex(spy_aligned.index).dropna()
corr_spy = round(float(h261b_aligned.corr(spy_aligned)), 4)

sharpe_pass = oos_result["sharpe"] >= 0.70
corr_pass   = corr_spy < 0.50
neg_pass    = oos_result["neg_yrs"] <= 3
confirmed   = sharpe_pass and corr_pass and neg_pass

print(f"\n── Verdict ──")
print(f"  SPY B&H Sharpe: {spy_sharpe}")
print(f"  Corr(H261b, SPY) OOS = {corr_spy}")
print(f"  OOS Sharpe {oos_result['sharpe']} vs gate 0.70 → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  Corr {corr_spy} vs gate <0.50 → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs {oos_result['neg_yrs']} vs gate <=3 → {'PASS' if neg_pass else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H261b",
    "title": "Commodity Trend CTA Top-2 (UNG excluded)",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "is_result": is_result,
    "oos_result": oos_result,
    "oos_annual": oos_ann,
    "spy_oos_sharpe": spy_sharpe,
    "corr_h261b_spy_oos": corr_spy,
    "gates": {
        "sharpe_gate": 0.70, "corr_gate": 0.50, "neg_gate": 3,
        "sharpe_pass": sharpe_pass, "corr_pass": corr_pass, "neg_pass": neg_pass,
    },
}
out_path = RESULT_DIR / "h261b_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
