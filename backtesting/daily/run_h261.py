"""
H261 — Commodity Trend CTA (Single-Best, Absolute Momentum Gate)
=================================================================
Thesis:
  Commodity trend following has shown negative or near-zero correlation with
  equity momentum strategies across multiple historical cycles. During inflationary
  bear markets (2022: SPY -18%, TLT -26%), commodity trend captured
  oil/energy/metals uptrends that were invisible to H257's equity/credit modules.
  A focused 6-ETF commodity universe with a dual momentum signal may provide
  genuine diversification to the production portfolio (H041a+H026+H045).

Universe (all ETFs live by 2007):
  GLD  — Gold (2004)
  SLV  — Silver (2006)
  DBC  — Broad Commodities (2006)
  USO  — Oil/Energy (2006)
  DBA  — Agriculture (2007)
  UNG  — Natural Gas (2007)

Signal: 6-month momentum, skip-1m, lagged-1m (identical to H257/H256)
  signal(t) = price(t-2) / price(t-8) - 1   [no look-ahead]

Rules:
  1. Rank all 6 assets by signal
  2. If best asset has positive absolute momentum → hold it (top-1)
  3. If all assets have negative absolute momentum → hold BIL (defensive)
  Monthly rebalance, 10bp TC

IS:  2010-01-01 to 2017-12-31
OOS: 2018-01-01 to 2025-12-31

Confirm gates:
  OOS Sharpe > 0.70  (lower bar: commodities are noisy)
  Corr(H261, SPY)_OOS < 0.50  (key thesis: diversification)
  NegYrs OOS <= 3

Key question: Is H261 uncorrelated enough with H041a/H026/H045 to add as a
  diversifying sleeve? Target: Corr < 0.30 with production blend.
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

ASSETS    = ["GLD", "SLV", "DBC", "USO", "DBA", "UNG"]
DEFENSIVE = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]

# ─────────────────────────────────────────────
# 1. Download
# ─────────────────────────────────────────────
print("Downloading commodity universe...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)
raw = raw[ALL_TICKERS].ffill().dropna(how="all")
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# ─────────────────────────────────────────────
# 2. Signal: 6m momentum, skip 1m, lagged 1m
# r6(t) = price(t-2) / price(t-8) - 1
# ─────────────────────────────────────────────
r6_raw = monthly.shift(1) / monthly.shift(7) - 1
signal = r6_raw.shift(1)


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


def run_backtest(start, end, label=""):
    sig = signal[ASSETS].loc[start:end]
    ret = monthly_ret[ALL_TICKERS].loc[start:end]
    common = sig.index.intersection(ret.index)

    equity = 1.0
    curve  = []
    prev   = None
    annual = {}

    for date in common:
        s = sig.loc[date].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        best_asset   = s.idxmax()
        best_abs_mom = float(s.loc[best_asset])
        hold = best_asset if best_abs_mom > 0 else DEFENSIVE

        tc_cost    = TC if hold != prev else 0.0
        period_ret = monthly_ret.loc[date, hold]
        if pd.isna(period_ret):
            period_ret = 0.0
        equity *= (1 + period_ret - tc_cost)
        curve.append(equity)
        prev = hold

        yr = date.year
        annual[yr] = annual.get(yr, [])
        annual[yr].append(period_ret - tc_cost)

    ret_series = pd.Series(curve, index=common).pct_change().dropna()
    neg_yrs = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

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
    return result, ann_ret


is_result,  _     = run_backtest(IS_START, IS_END, "IS Results (2010-2017)")
oos_result, oos_ann = run_backtest(OOS_START, FULL_END, "OOS Results (2018-2025)")

# SPY benchmark
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END, auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)

# Correlation H261 vs SPY
sig2  = signal[ASSETS].loc[OOS_START:]
ret2  = monthly_ret[ALL_TICKERS].loc[OOS_START:]
common2 = sig2.index.intersection(ret2.index)
prev2 = None
curve2 = []
for date in common2:
    s = sig2.loc[date].dropna()
    if len(s) == 0:
        curve2.append(0.0)
        continue
    best_asset   = s.idxmax()
    best_abs_mom = float(s.loc[best_asset])
    hold = best_asset if best_abs_mom > 0 else DEFENSIVE
    tc_cost    = TC if hold != prev2 else 0.0
    period_ret = monthly_ret.loc[date, hold]
    if pd.isna(period_ret):
        period_ret = 0.0
    curve2.append(period_ret - tc_cost)
    prev2 = hold

h261_oos_ret = pd.Series(curve2, index=common2)
spy_aligned  = spy_monthly.reindex(h261_oos_ret.index).dropna()
h261_aligned = h261_oos_ret.reindex(spy_aligned.index).dropna()
corr_spy = round(float(h261_aligned.corr(spy_aligned)), 4)

# Gates
sharpe_pass = oos_result["sharpe"] >= 0.70
corr_pass   = corr_spy < 0.50
neg_pass    = oos_result["neg_yrs"] <= 3
confirmed   = sharpe_pass and corr_pass and neg_pass

print(f"\n── Verdict ──")
print(f"  SPY B&H Sharpe: {spy_sharpe}")
print(f"  Corr(H261, SPY) OOS = {corr_spy}")
print(f"  OOS Sharpe {oos_result['sharpe']} vs gate 0.70 → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  Corr {corr_spy} vs gate <0.50 → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs {oos_result['neg_yrs']} vs gate <=3 → {'PASS' if neg_pass else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H261",
    "title": "Commodity Trend CTA",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "is_result": is_result,
    "oos_result": oos_result,
    "oos_annual": oos_ann,
    "spy_oos_sharpe": spy_sharpe,
    "corr_h261_spy_oos": corr_spy,
    "gates": {
        "sharpe_gate": 0.70, "corr_gate": 0.50, "neg_gate": 3,
        "sharpe_pass": sharpe_pass, "corr_pass": corr_pass, "neg_pass": neg_pass,
    },
}
out_path = RESULT_DIR / "h261_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
