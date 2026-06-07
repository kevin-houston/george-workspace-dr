"""
H262 — Commodity Trend CTA: Bayesian Short+Long Signal Decomposition
====================================================================
Source: arXiv:2507.15876 (2025) — 'Re-evaluating Short- and Long-Term Trend
        Factors in CTA Replication: A Bayesian Graphical Approach'

Hypothesis:
  H261b CONFIRMED (OOS Sharpe=0.922, Corr(SPY)=0.218) but has a notable
  IS/OOS disconnect: IS Sharpe=0.256 in the 2010-2017 commodity bear market.
  The referenced paper shows CTAs blend short-term (~3m) and long-term (~12m)
  trend signals independently. Adding a 12m signal alongside H261b's 6m signal
  may improve IS performance — the 12m signal shifts to BIL earlier during
  multi-year commodity bears (2014-2016 oil crash), reducing the IS MaxDD=-40.4%.

Design:
  Universe: GLD, SLV, DBC, USO, DBA (same as H261b, no UNG)
  Signals:
    short  = 3m momentum: monthly.shift(1)/monthly.shift(4)-1, lagged 1m
    medium = 6m momentum: monthly.shift(1)/monthly.shift(7)-1, lagged 1m (H261b)
    long   = 12m momentum: monthly.shift(1)/monthly.shift(13)-1, lagged 1m
  Blend: equal-weight rank-score from all 3 signals → composite rank
  Positive gate: hold Top-2 assets where composite rank is above median
    AND at least 2-of-3 individual signals are positive for that asset
    → otherwise hold BIL
  Monthly rebalance, 10bp TC

IS: 2010-2017, OOS: 2018-2025

Confirm gates (must beat H261b baseline):
  OOS Sharpe > 0.922  (improve on H261b OOS)
  IS Sharpe > 0.50    (fix H261b's IS weakness of 0.256)
  Corr(H262, SPY) OOS < 0.50  (maintain diversification)
  NegYrs OOS <= 2
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


print("Downloading commodity universe...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)
raw = raw[ALL_TICKERS].ffill().dropna(how="all")
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# Three momentum signals — all lagged 1m (no look-ahead)
sig_3m  = (monthly.shift(1) / monthly.shift(4)  - 1).shift(1)
sig_6m  = (monthly.shift(1) / monthly.shift(7)  - 1).shift(1)
sig_12m = (monthly.shift(1) / monthly.shift(13) - 1).shift(1)


def composite_signal(date):
    """
    Composite rank-score: equal-weight rank from 3m, 6m, 12m signals.
    Also count how many of the 3 signals are positive for each asset.
    Returns: (composite_rank Series, positive_count dict)
    """
    s3  = sig_3m.loc[date,  ASSETS].dropna()
    s6  = sig_6m.loc[date,  ASSETS].dropna()
    s12 = sig_12m.loc[date, ASSETS].dropna()

    common = s3.index.intersection(s6.index).intersection(s12.index)
    if len(common) == 0:
        return pd.Series(dtype=float), {}

    # Rank each signal (higher = better momentum)
    r3  = s3[common].rank()
    r6  = s6[common].rank()
    r12 = s12[common].rank()
    composite = (r3 + r6 + r12) / 3.0

    # Count how many signals are positive per asset
    pos_count = {a: int(s3[a] > 0) + int(s6[a] > 0) + int(s12[a] > 0)
                 for a in common}

    return composite, pos_count


def run_backtest(start, end, label=""):
    ret = monthly_ret[ALL_TICKERS].loc[start:end]
    dates = ret.index

    equity = 1.0
    curve  = []
    prev_hold = frozenset()
    annual = {}

    for date in dates:
        comp, pos_count = composite_signal(date)
        if len(comp) == 0:
            curve.append(equity)
            continue

        # Top-N assets by composite rank; must have >= 2 of 3 signals positive
        ranked = comp.sort_values(ascending=False)
        qualified = [a for a in ranked.index if pos_count.get(a, 0) >= 2]

        if len(qualified) == 0:
            hold_assets = [DEFENSIVE]
        elif len(qualified) == 1:
            hold_assets = qualified[:1]
        else:
            hold_assets = qualified[:TOP_N]

        hold_set = frozenset(hold_assets)
        changed  = hold_set != prev_hold

        period_total = 0.0
        for asset in hold_assets:
            w  = 1.0 / len(hold_assets)
            r  = monthly_ret.loc[date, asset]
            r  = 0.0 if pd.isna(r) else float(r)
            tc = TC if changed else 0.0
            period_total += w * (r - tc)

        equity *= (1 + period_total)
        curve.append(equity)
        prev_hold = hold_set

        yr = date.year
        annual.setdefault(yr, []).append(period_total)

    ret_series = pd.Series(curve, index=dates).pct_change().dropna()
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
    return result, ann_ret


is_result,  _        = run_backtest(IS_START, IS_END, "IS Results (2010-2017)")
oos_result, oos_ann  = run_backtest(OOS_START, FULL_END, "OOS Results (2018-2025)")

# SPY benchmark
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END,
                      auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)

# Correlation H262 vs SPY
oos_dates = monthly_ret.loc[OOS_START:].index
prev2 = frozenset()
monthly_rets2 = []
for date in oos_dates:
    comp, pos_count = composite_signal(date)
    if len(comp) == 0:
        monthly_rets2.append(0.0)
        continue
    ranked = comp.sort_values(ascending=False)
    qualified = [a for a in ranked.index if pos_count.get(a, 0) >= 2]
    hold_assets = (qualified[:TOP_N] if len(qualified) >= 2
                   else qualified[:1] if len(qualified) == 1
                   else [DEFENSIVE])
    hold_set = frozenset(hold_assets)
    changed  = hold_set != prev2
    period_total = sum(
        (1.0 / len(hold_assets)) * (
            (0.0 if pd.isna(monthly_ret.loc[date, a]) else float(monthly_ret.loc[date, a]))
            - (TC if changed else 0.0)
        )
        for a in hold_assets
    )
    monthly_rets2.append(period_total)
    prev2 = hold_set

h262_oos = pd.Series(monthly_rets2, index=oos_dates)
spy_aligned  = spy_monthly.reindex(h262_oos.index).dropna()
h262_aligned = h262_oos.reindex(spy_aligned.index).dropna()
corr_spy = round(float(h262_aligned.corr(spy_aligned)), 4)

# Gates (must beat H261b baseline)
sharpe_oos_pass = oos_result["sharpe"] > 0.922
sharpe_is_pass  = is_result["sharpe"]  > 0.50
corr_pass       = corr_spy < 0.50
neg_pass        = oos_result["neg_yrs"] <= 2
confirmed = sharpe_oos_pass and sharpe_is_pass and corr_pass and neg_pass

print(f"\n── Verdict ──")
print(f"  SPY B&H Sharpe: {spy_sharpe}")
print(f"  Corr(H262, SPY) OOS = {corr_spy}")
print(f"  H261b baseline: IS Sharpe=0.256, OOS Sharpe=0.922, Corr(SPY)=0.218")
print(f"  OOS Sharpe {oos_result['sharpe']} vs gate >0.922 (beat H261b) → {'PASS' if sharpe_oos_pass else 'FAIL'}")
print(f"  IS  Sharpe {is_result['sharpe']} vs gate >0.50 (fix IS)       → {'PASS' if sharpe_is_pass else 'FAIL'}")
print(f"  Corr {corr_spy} vs gate <0.50                                  → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs {oos_result['neg_yrs']} vs gate <=2                     → {'PASS' if neg_pass else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H262",
    "title": "Commodity Trend CTA — Bayesian Short+Long Signal Decomposition",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "is_result": is_result,
    "oos_result": oos_result,
    "oos_annual": oos_ann,
    "spy_oos_sharpe": spy_sharpe,
    "corr_h262_spy_oos": corr_spy,
    "h261b_baseline": {"is_sharpe": 0.256, "oos_sharpe": 0.922, "corr_spy": 0.218},
    "gates": {
        "oos_sharpe_gate": 0.922, "is_sharpe_gate": 0.50, "corr_gate": 0.50, "neg_gate": 2,
        "oos_sharpe_pass": sharpe_oos_pass, "is_sharpe_pass": sharpe_is_pass,
        "corr_pass": corr_pass, "neg_pass": neg_pass,
    },
}
out_path = RESULT_DIR / "h262_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
