"""
H311 — Static Multi-Asset Diversification: Equal-Weight 4-Asset Portfolio
==========================================================================

Source:
  Markowitz (1952) "Portfolio Selection" (JF) — diversification reduces risk
  without proportional reduction in return.
  Ilmanen & Kizer (2012) "The Death of Diversification Has Been Greatly
  Exaggerated" (JPM) — cross-asset diversification remains robust when assets
  have low pairwise correlations.
  Asness, Frazzini & Pedersen (2012) "Leverage Aversion and Risk Parity"
  (FAJ) — equal risk contribution across uncorrelated asset classes.

Hypothesis:
  A simple equal-weight 4-asset portfolio (SPY/TLT/GLD/DBC) with no dynamic
  signal — just monthly calendar rebalance to 25% each — achieves OOS Sharpe
  > 1.0 due to the structural low correlation between:
    SPY  (US equities, risk-on, inflation benefit)
    TLT  (long bonds, risk-off, deflation benefit)
    GLD  (gold, real-asset, inflation/crisis hedge)
    DBC  (commodity basket, real-asset, supply-side inflation hedge)

  Why this outperforms SPY: in 2022 (SPY -18%, TLT -26%), commodities (DBC +26%,
  GLD +0%) provided partial shelter. In 2020 (SPY +18%), TLT +17% and GLD +24%
  also rose — diversification works both ways. The OOS period 2020-2026 includes
  multiple macro regimes (COVID reflation, inflation surge, rate-hike cycle,
  AI-led tech rally) where asset class correlations were broadly low.

  Enhancement variant: VIX regime gate — when VIX >= 25 (acute stress), move
  to BIL (T-bills) entirely. This captures the observation that cross-asset
  correlations spike to 1 during acute crises (March 2020), and BIL avoids the
  simultaneous drawdown across all 4 assets.

Variants:
  A: EW-4 25/25/25/25 (no gate) — always-on equal weight
  B: EW-4 + VIX<25 gate — move to BIL when VIX >= 25
  C: EW-5 + IEF 20/20/20/20/20 — add intermediate Treasuries
  D: EW-5 + VIX<25 gate
  E: Tilt 35/30/20/15 (SPY-heavy) — overweight equity
  F: EW-4 + VIX<20 gate (tighter stress filter)

Baseline: SPY buy-and-hold, 60/40 portfolio (noted for context, not tested).
IS:  2010-01-01 to 2019-12-31  (10 years)
OOS: 2020-01-01 to 2026-06-13  (6.5 years)
Gate: OOS Sharpe > 1.0 AND WF ratio 0.5-4.0

KEY FINDING EXPECTED:
  - 2022 is the key diversification test: DBC +26.4% partially offsets SPY -18.2%
    and TLT -26.0%; net portfolio loss -8.7% vs -18.2% for SPY alone.
  - GLD acts as insurance (near-flat in 2022 nominal terms).
  - The VIX gate adds value primarily in March 2020 (VIX spiked to 65),
    pivoting to BIL and avoiding the simultaneous crash.
  - WF ratio caveat: the 2010-2019 IS period was primarily US equity bull market
    where SPY dominated; the 4-asset portfolio necessarily underperforms SPY in
    that period but still achieves IS Sharpe ~0.7 (positive, diversified returns).
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

FULL_START  = "2006-01-01"
IS_START    = "2010-01-01"
IS_END      = "2019-12-31"
OOS_START   = "2020-01-01"
OOS_END     = "2026-06-13"
GATE_SHARPE = 1.0
WF_LO       = 0.50
WF_HI       = 4.00

ASSETS_4 = ["SPY", "TLT", "GLD", "DBC"]
ASSETS_5 = ["SPY", "TLT", "GLD", "DBC", "IEF"]

PROD_W = {"H041a": 0.22, "H026": 0.27, "H045": 0.21,
          "XLK_IBS": 0.20, "SMH_IBS": 0.08, "IGV_IBS": 0.02}

# ── Data ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("H311 — Static Multi-Asset Diversification (EW 4-Asset)")
print("=" * 60)

print("\n[1] Fetching prices…")
tickers = sorted(set(ASSETS_5 + ["BIL", "^VIX"]))
raw = yf.download(tickers, start=FULL_START, end=OOS_END,
                  auto_adjust=True, progress=False)["Close"].ffill()

monthly = raw.resample("ME").last()
ret     = monthly.pct_change()

vix_monthly  = raw["^VIX"].resample("ME").mean()
spy_monthly   = monthly["SPY"]


# ── Helper functions ──────────────────────────────────────────────────────────
def run_static(weights_dict, start=IS_START):
    """Fixed-weight monthly rebalanced portfolio."""
    assets = list(weights_dict.keys())
    ws     = list(weights_dict.values())
    result = []
    for dt in ret.index:
        if dt < pd.Timestamp(start):
            continue
        port_ret = sum(ws[i] * ret[assets[i]].loc[dt] for i in range(len(assets)))
        result.append((dt, port_ret))
    return pd.Series(dict(result))


def run_vix_gated(weights_dict, vix_gate, start=IS_START):
    """Fixed-weight portfolio with VIX stress gate — go to BIL when VIX >= gate."""
    assets = list(weights_dict.keys())
    ws     = list(weights_dict.values())
    result = []
    for dt in ret.index:
        if dt < pd.Timestamp(start):
            continue
        if dt in vix_monthly.index and vix_monthly.loc[dt] >= vix_gate:
            result.append((dt, ret["BIL"].loc[dt]))
        else:
            port_ret = sum(ws[i] * ret[assets[i]].loc[dt] for i in range(len(assets)))
            result.append((dt, port_ret))
    return pd.Series(dict(result))


def period_stats(series, start, end):
    x = series[(series.index >= start) & (series.index <= end)].dropna()
    if len(x) < 6:
        return {"sharpe": np.nan, "cagr": np.nan, "maxdd": np.nan, "neg_yrs": np.nan}
    ann    = x.mean() * 12
    vol    = x.std() * np.sqrt(12)
    sharpe = ann / vol if vol > 0 else 0.0
    ec     = (1 + x).cumprod()
    maxdd  = (ec / ec.cummax() - 1).min()
    by_yr  = x.groupby(x.index.year).apply(lambda g: (1 + g).prod() - 1)
    return {
        "sharpe":   round(float(sharpe), 3),
        "cagr":     round(float(ann), 4),
        "maxdd":    round(float(maxdd), 4),
        "neg_yrs":  int((by_yr < 0).sum()),
        "n_months": len(x),
    }


# ── Variants ──────────────────────────────────────────────────────────────────
print("\n[2] Running variants…")

variants = {
    "A: EW-4 25/25/25/25":
        run_static({"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "DBC": 0.25}),
    "B: EW-4 + VIX<25 gate":
        run_vix_gated({"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "DBC": 0.25}, vix_gate=25),
    "C: EW-5 +IEF 20/20/20/20/20":
        run_static({"SPY": 0.20, "TLT": 0.20, "GLD": 0.20, "DBC": 0.20, "IEF": 0.20}),
    "D: EW-5 + VIX<25 gate":
        run_vix_gated({"SPY": 0.20, "TLT": 0.20, "GLD": 0.20, "DBC": 0.20, "IEF": 0.20}, vix_gate=25),
    "E: Tilt 35/30/20/15 SPY-heavy":
        run_static({"SPY": 0.35, "TLT": 0.30, "GLD": 0.20, "DBC": 0.15}),
    "F: EW-4 + VIX<20 gate":
        run_vix_gated({"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "DBC": 0.25}, vix_gate=20),
}

results = {}
print(f"\n{'Variant':<32} {'IS Sh':>7} {'OOS Sh':>8} {'OOS CAGR':>10} "
      f"{'OOS MaxDD':>10} {'NegYrs':>7} {'WF':>6} {'Gate':>5}")
print("-" * 90)

for label, s in variants.items():
    is_s  = period_stats(s, IS_START, IS_END)
    oos_s = period_stats(s, OOS_START, OOS_END)
    wf    = (oos_s["sharpe"] / is_s["sharpe"]) if (is_s["sharpe"] and is_s["sharpe"] > 0.01) else np.nan
    gate  = ("PASS" if (oos_s["sharpe"] >= GATE_SHARPE
                        and not np.isnan(wf) and WF_LO <= wf <= WF_HI)
             else "fail")
    wf_str = f"{wf:.2f}" if not np.isnan(wf) else "n/a"
    print(f"{label:<32} {is_s['sharpe']:>7.3f} {oos_s['sharpe']:>8.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%} "
          f"{str(oos_s['neg_yrs']):>7} {wf_str:>6}  {gate}")
    results[label] = {
        "is": is_s, "oos": oos_s,
        "wf_ratio": round(wf, 3) if not np.isnan(wf) else None,
    }

spy_oos = period_stats(ret["SPY"], OOS_START, OOS_END)
print(f"{'SPY buy-hold':<32} {'—':>7} {spy_oos['sharpe']:>8.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")


# ── Correlation Analysis ──────────────────────────────────────────────────────
print("\n[3] OOS correlation matrix (SPY/TLT/GLD/DBC)…")
oos_ret = ret[ASSETS_4][(ret.index >= OOS_START) & (ret.index <= OOS_END)].dropna()
corr_oos = oos_ret.corr()
print(corr_oos.round(3).to_string())

is_ret  = ret[ASSETS_4][(ret.index >= IS_START) & (ret.index <= IS_END)].dropna()
corr_is = is_ret.corr()
print("\nIS correlation matrix:")
print(corr_is.round(3).to_string())


# ── Year-by-year breakdown ────────────────────────────────────────────────────
print("\n[4] Year-by-year comparison (Variant A vs SPY)…")
va = variants["A: EW-4 25/25/25/25"]
print(f"{'Year':<6} {'EW-4':>8} {'SPY':>8}")
print("-" * 25)
for yr in range(2010, 2027):
    r_ew4 = va[va.index.year == yr]
    r_spy = ret["SPY"][ret.index.year == yr]
    if len(r_ew4) < 3 or len(r_spy) < 3:
        continue
    ew4_ann = (1 + r_ew4).prod() - 1
    spy_ann = (1 + r_spy).prod() - 1
    print(f"{yr:<6} {ew4_ann:>8.2%} {spy_ann:>8.2%}")


# ── Verdict ───────────────────────────────────────────────────────────────────
passing = {k: v for k, v in results.items()
           if (v["oos"]["sharpe"] >= GATE_SHARPE
               and v["wf_ratio"] is not None
               and WF_LO <= v["wf_ratio"] <= WF_HI)}
confirmed = len(passing) > 0
best_label = max(passing, key=lambda k: passing[k]["oos"]["sharpe"]) if passing else None
best_oos   = passing[best_label]["oos"]["sharpe"] if best_label else 0
best_wf    = passing[best_label]["wf_ratio"] if best_label else 0

print("\n" + "=" * 60)
print(f"H311 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
if confirmed:
    print(f"  Best variant: {best_label}")
    print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: {GATE_SHARPE})")
    print(f"  WF ratio: {best_wf:.2f}  (gate: {WF_LO}–{WF_HI})")
    print(f"  SPY OOS Sharpe: {spy_oos['sharpe']:.3f}")
    print(f"  {len(passing)} of {len(results)} variants pass both gates")
print("=" * 60)


# ── Save Results ──────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H311",
    "title": "Static Multi-Asset Diversification: Equal-Weight 4-Asset Portfolio",
    "assets_4": ASSETS_4,
    "assets_5": ASSETS_5,
    "is_period":  f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": f"OOS Sharpe >= {GATE_SHARPE} AND WF ratio {WF_LO}–{WF_HI}",
    "confirmed": bool(confirmed),
    "best_variant": best_label,
    "best_oos_sharpe": round(best_oos, 3),
    "best_wf_ratio": round(best_wf, 3),
    "spy_oos": spy_oos,
    "variants": results,
    "correlations": {
        "oos": {k: {k2: round(float(v2), 3) for k2, v2 in corr_oos[k].items()}
                for k in corr_oos.columns},
        "is":  {k: {k2: round(float(v2), 3) for k2, v2 in corr_is[k].items()}
                for k in corr_is.columns},
    },
}
path = RESULT_DIR / "h311_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
