"""
H263 — Commodity Trend CTA: 12m Signal & Dual-Confirm Variants
==============================================================
Source: H261b CONFIRMED (6m momentum, OOS Sharpe=0.922). H262 NOT CONFIRMED
        (3m/6m/12m composite, OOS Sharpe=0.814). Diagnosis: 3m signal introduced
        noise; strict ≥2-of-3 gate filtered out profitable OOS trades.

H262 failure analysis:
  - H262 3m/6m/12m composite ranked together → short-horizon noise swamped 12m signal
  - ≥2-of-3 positive gate is too restrictive in OOS commodity bulls
  - The IS/OOS disconnect is structural (2010-2017 = commodity bear market)
  - The fix should ONLY use longer-horizon signals, not add shorter ones

H263 tests two cleaner variants:
  A. Pure 12m momentum (drop 6m entirely; 12m signal persists longer → fewer entries
     in multi-year bears like 2014-2016 oil crash)
  B. 6m + 12m dual-confirm: H261b baseline (6m ranking, Top-2) but an asset is only
     eligible if its 12m signal is ALSO positive (softer gate than H262's composite;
     no 3m signal)

Hypothesis: In a multi-year commodity bear (IS 2010-2017), 12m signal stays negative
longer → fewer false entries → better IS Sharpe without losing OOS crisis-alpha.

Universe: GLD, SLV, DBC, USO, DBA (same as H261b; no UNG)
IS: 2010-2017, OOS: 2018-2025, TC: 10bp

Confirm gates (must meet or beat H261b):
  A: OOS Sharpe > 0.90 AND IS Sharpe > 0.40
  B: OOS Sharpe > 0.922 AND IS Sharpe > 0.40
  Both: Corr(SPY) OOS < 0.50, NegYrs OOS ≤ 3
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

FULL_START  = "2007-01-01"
FULL_END    = "2025-12-31"
IS_START    = "2010-01-01"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
TC          = 0.001
TOP_N       = 2

ASSETS      = ["GLD", "SLV", "DBC", "USO", "DBA"]
DEFENSIVE   = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]


def sharpe(ret_series, ann=12):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def max_drawdown(curve):
    ec = pd.Series(curve)
    roll_max = ec.cummax()
    return float(((ec - roll_max) / roll_max).min())


print("Downloading commodity universe...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)
raw = raw[ALL_TICKERS].ffill().dropna(how="all")
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# H261b signal: 6m momentum, skip-1m, lagged-1m
sig_6m  = (monthly.shift(1) / monthly.shift(7)  - 1).shift(1)
# H263 additional signal: 12m momentum
sig_12m = (monthly.shift(1) / monthly.shift(13) - 1).shift(1)


def backtest(start, end, variant, label=""):
    """
    variant='A': Pure 12m signal — rank by 12m momentum, absolute momentum gate = 12m > 0
    variant='B': Dual-confirm   — rank by 6m signal; 12m must also be positive to qualify
    """
    ret    = monthly_ret[ALL_TICKERS].loc[start:end]
    dates  = ret.index
    equity = 1.0
    curve  = []
    prev_hold = frozenset()
    annual = {}

    for date in dates:
        if variant == "A":
            sig = sig_12m.loc[date, ASSETS].dropna()
        else:
            sig = sig_6m.loc[date, ASSETS].dropna()

        sig12 = sig_12m.loc[date, ASSETS].dropna()

        if len(sig) == 0:
            curve.append(equity)
            continue

        if variant == "A":
            # rank by 12m; absolute gate = 12m > 0
            ranked = sig.sort_values(ascending=False)
            positive = [a for a in ranked.index
                        if a in sig.index and float(sig.loc[a]) > 0]
        else:
            # rank by 6m; must ALSO have 12m > 0
            ranked = sig.sort_values(ascending=False)
            positive = [a for a in ranked.index
                        if float(sig.loc[a]) > 0
                        and a in sig12.index and float(sig12.loc[a]) > 0]

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
            w  = 1.0 / len(hold_assets)
            r  = monthly_ret.loc[date, asset]
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
        "cagr":    round(float(pd.Series(curve).iloc[-1] ** (12/len(curve)) - 1), 4),
        "max_dd":  round(max_drawdown(curve), 4),
        "neg_yrs": neg_yrs,
        "months":  len(curve),
    }
    print(f"\n── {label} ──")
    print(f"  Sharpe={res['sharpe']:.3f}  CAGR={res['cagr']*100:.1f}%"
          f"  MaxDD={res['max_dd']*100:.1f}%  NegYrs={res['neg_yrs']}")
    if "OOS" in label:
        for yr in sorted(ann_ret):
            print(f"    {yr}: {'+' if ann_ret[yr]>=0 else ''}{ann_ret[yr]}%")
    return res, ann_ret


def oos_monthly_rets(variant):
    """Return OOS monthly return series for correlation analysis."""
    dates = monthly_ret.loc[OOS_START:].index
    prev  = frozenset()
    rets  = []

    for date in dates:
        sig   = (sig_12m if variant == "A" else sig_6m).loc[date, ASSETS].dropna()
        sig12 = sig_12m.loc[date, ASSETS].dropna()
        if len(sig) == 0:
            rets.append(0.0); continue

        if variant == "A":
            ranked   = sig.sort_values(ascending=False)
            positive = [a for a in ranked.index if float(sig.loc[a]) > 0]
        else:
            ranked   = sig.sort_values(ascending=False)
            positive = [a for a in ranked.index
                        if float(sig.loc[a]) > 0
                        and a in sig12.index and float(sig12.loc[a]) > 0]

        hold = ([DEFENSIVE] if not positive
                else positive[:1] if len(positive) == 1
                else positive[:TOP_N])
        h_set = frozenset(hold)
        changed = h_set != prev

        pt = sum(
            (1.0/len(hold)) * (
                (0.0 if pd.isna(monthly_ret.loc[date, a]) else float(monthly_ret.loc[date, a]))
                - (TC if changed else 0.0)
            )
            for a in hold
        )
        rets.append(pt)
        prev = h_set

    return pd.Series(rets, index=dates)


# Download SPY
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END,
                      auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)

print("\n====== H263-A: Pure 12m Signal ======")
a_is,  _       = backtest(IS_START,  IS_END,     "A", "IS  (2010-2017)")
a_oos, a_ann   = backtest(OOS_START, FULL_END,   "A", "OOS (2018-2025)")
a_rets = oos_monthly_rets("A")
a_corr = round(float(a_rets.reindex(spy_monthly.index).dropna().corr(
                spy_monthly.reindex(a_rets.index).dropna())), 4)

print("\n====== H263-B: 6m+12m Dual-Confirm ======")
b_is,  _       = backtest(IS_START,  IS_END,     "B", "IS  (2010-2017)")
b_oos, b_ann   = backtest(OOS_START, FULL_END,   "B", "OOS (2018-2025)")
b_rets = oos_monthly_rets("B")
b_corr = round(float(b_rets.reindex(spy_monthly.index).dropna().corr(
                spy_monthly.reindex(b_rets.index).dropna())), 4)

print(f"\n── Baseline (H261b) ──")
print(f"  IS Sharpe=0.256  OOS Sharpe=0.922  Corr(SPY)=0.218")

print(f"\n── H263-A gates (OOS Sharpe > 0.90, IS > 0.40, Corr < 0.50, NegYrs ≤ 3) ──")
a_pass = (a_oos["sharpe"] > 0.90 and a_is["sharpe"] > 0.40
          and a_corr < 0.50 and a_oos["neg_yrs"] <= 3)
print(f"  OOS {a_oos['sharpe']} {'PASS' if a_oos['sharpe']>0.90 else 'FAIL'} | "
      f"IS {a_is['sharpe']} {'PASS' if a_is['sharpe']>0.40 else 'FAIL'} | "
      f"Corr {a_corr} {'PASS' if a_corr<0.50 else 'FAIL'} | "
      f"NegYrs {a_oos['neg_yrs']} {'PASS' if a_oos['neg_yrs']<=3 else 'FAIL'}")
print(f"  VERDICT A: {'CONFIRMED' if a_pass else 'NOT CONFIRMED'}")

print(f"\n── H263-B gates (OOS Sharpe > 0.922, IS > 0.40, Corr < 0.50, NegYrs ≤ 3) ──")
b_pass = (b_oos["sharpe"] > 0.922 and b_is["sharpe"] > 0.40
          and b_corr < 0.50 and b_oos["neg_yrs"] <= 3)
print(f"  OOS {b_oos['sharpe']} {'PASS' if b_oos['sharpe']>0.922 else 'FAIL'} | "
      f"IS {b_is['sharpe']} {'PASS' if b_is['sharpe']>0.40 else 'FAIL'} | "
      f"Corr {b_corr} {'PASS' if b_corr<0.50 else 'FAIL'} | "
      f"NegYrs {b_oos['neg_yrs']} {'PASS' if b_oos['neg_yrs']<=3 else 'FAIL'}")
print(f"  VERDICT B: {'CONFIRMED' if b_pass else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H263",
    "title": "Commodity Trend CTA: 12m Signal & Dual-Confirm Variants",
    "h261b_baseline": {"is_sharpe": 0.256, "oos_sharpe": 0.922, "corr_spy": 0.218},
    "h263_a": {
        "description": "Pure 12m momentum",
        "status": "CONFIRMED" if a_pass else "NOT CONFIRMED",
        "is_result": a_is, "oos_result": a_oos, "oos_annual": a_ann,
        "corr_spy_oos": a_corr,
    },
    "h263_b": {
        "description": "6m rank + 12m dual-confirm",
        "status": "CONFIRMED" if b_pass else "NOT CONFIRMED",
        "is_result": b_is, "oos_result": b_oos, "oos_annual": b_ann,
        "corr_spy_oos": b_corr,
    },
    "spy_oos_sharpe": spy_sharpe,
}
out_path = RESULT_DIR / "h263_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
