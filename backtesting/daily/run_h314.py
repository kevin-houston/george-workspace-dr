"""
H314 — Duration-Factor Overlay on Bond ETF Rotation (H045 Enhancement)
========================================================================

Source:
  Litterman & Scheinkman (1991) "Common Factors Affecting Bond Returns" (JFI)
  Diebold & Li (2006) "Forecasting the term structure of government bond yields" (JE)
  FRED T10Y3M: 10-Year minus 3-Month Treasury Constant Maturity spread

Hypothesis:
  H045 bond rotation uses pure momentum on a 13-asset universe. The yield curve
  slope (10Y-3M) contains forward-looking duration risk information:
  - Deep inversion (T10Y3M < -0.5%): momentum may signal duration extension
    but long bonds face headwinds from curve normalization. Restrict to short-
    duration instruments (SHY, BIL, IEI, VCSH).
  - Steep curve (T10Y3M > +1.5%): term premium is elevated; long bonds tend
    to outperform as curve normalizes. Relax TSMOM filter for TLT to allow
    entry even after short-term weakness.
  - Neutral zone (-0.5% to +1.5%): standard H045 signal, full 13-asset universe.

Variants:
  A: H045 baseline — full 13-asset universe, top-2, 3m+6m+12m rank + TSMOM(r3≥0)
  B: Inversion gate — when T10Y3M < -0.5%, restrict to short-duration only
  C: Steepness extension — when T10Y3M > +1.5%, relax TSMOM for TLT
  D: Full dual overlay — both B and C active

IS:  2008-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-06-20
Gate: OOS Sharpe > 1.351 (H045 confirmed baseline) AND WF ratio 0.50-4.00
"""

import json
import os
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from fredapi import Fred

warnings.filterwarnings("ignore")

RESULT_DIR  = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

FULL_START  = "2007-01-01"
IS_START    = "2008-01-01"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
OOS_END     = "2026-06-20"
GATE_SHARPE = 1.351   # H045 confirmed baseline
WF_LO, WF_HI = 0.50, 4.00
N_TOP = 2

UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "BIL", "HYG", "LQD",
            "VCIT", "VCSH", "VMBS", "TIP", "GLD", "AGG"]
SHORT_DUR = ["SHY", "BIL", "IEI", "VCSH"]   # duration < 5yr

print("=" * 65)
print("H314 — Duration-Factor Overlay on Bond ETF Rotation")
print("=" * 65)

# ── FRED yield curve ──────────────────────────────────────────────────────────
print("\n[1] Fetching FRED T10Y3M...")
fred = Fred(api_key=os.environ["FRED_API_KEY"])
yc_daily = fred.get_series("T10Y3M", observation_start=FULL_START)
yc_monthly = (yc_daily.resample("ME").last().ffill() / 100)   # % → decimal

print(f"    Range: {yc_monthly.first_valid_index().date()} → {yc_monthly.last_valid_index().date()}")
print(f"    Inverted (<-0.5%) months: {(yc_monthly < -0.005).sum()}")
print(f"    Steep   (>+1.5%) months: {(yc_monthly > 0.015).sum()}")

# ── Price data ────────────────────────────────────────────────────────────────
print("\n[2] Fetching bond ETF prices...")
raw = yf.download(UNIVERSE + ["SPY"], start=FULL_START, end=OOS_END,
                  auto_adjust=True, progress=False)["Close"].ffill()
monthly = raw.resample("ME").last()
ret     = monthly.pct_change()

# Rolling momentum returns (signals computed at month t, returns earned t+1)
r3  = monthly.pct_change(3)
r6  = monthly.pct_change(6)
r12 = monthly.pct_change(12)

print(f"    Tickers loaded: {[c for c in monthly.columns if c in UNIVERSE]}")


# ── Core selection logic ───────────────────────────────────────────────────────
def get_holdings(t, eligible, relax_tsmom_for=None, n=N_TOP):
    """Pick top-N by rank-ensemble, applying TSMOM filter."""
    elig = [x for x in eligible if x in r3.columns and not pd.isna(r3.loc[t, x])]
    if not elig:
        return ["BIL"] if "BIL" in monthly.columns else []

    row = pd.DataFrame({
        "r3":  r3.loc[t, elig],
        "r6":  r6.loc[t, elig],
        "r12": r12.loc[t, elig],
    })
    row["score"] = (row["r3"].rank(na_option="bottom") +
                    row["r6"].rank(na_option="bottom") +
                    row["r12"].rank(na_option="bottom")) / 3

    # TSMOM: exclude assets with negative 3m return (unless relaxed)
    tsmom_ok = row["r3"] >= 0
    if relax_tsmom_for:
        tsmom_ok |= row.index.isin(relax_tsmom_for)
    filtered = row[tsmom_ok]

    if filtered.empty:
        return ["BIL"] if "BIL" in monthly.columns else elig[:1]

    return filtered.nlargest(min(n, len(filtered)), "score").index.tolist()


def get_yc(t):
    """Yield curve slope at month-end t, or NaN."""
    past = yc_monthly[yc_monthly.index <= t]
    return float(past.iloc[-1]) if len(past) > 0 else np.nan


# ── Run variants ──────────────────────────────────────────────────────────────
print("\n[3] Running variants...")

def run_variant(invert_gate=False, steep_ext=False):
    series = {}
    months = ret.index[ret.index >= IS_START]

    for t in months[:-1]:   # last month has no next-month return to measure
        i = ret.index.get_loc(t)
        t_next = ret.index[i + 1]

        yc = get_yc(t)

        if invert_gate and not np.isnan(yc) and yc < -0.005:
            eligible = SHORT_DUR
            relax    = None
        elif steep_ext and not np.isnan(yc) and yc > 0.015:
            eligible = UNIVERSE
            relax    = ["TLT"]
        else:
            eligible = UNIVERSE
            relax    = None

        if t not in r3.index:
            continue

        holdings = get_holdings(t, eligible, relax_tsmom_for=relax)
        valid_h  = [h for h in holdings if h in ret.columns]
        if not valid_h:
            series[t] = 0.0
            continue
        series[t] = float(ret.loc[t_next, valid_h].mean())

    return pd.Series(series)


variants = {
    "A: H045 baseline":        run_variant(False, False),
    "B: Inversion gate":       run_variant(True,  False),
    "C: Steepness extension":  run_variant(False, True),
    "D: Both overlays":        run_variant(True,  True),
}


# ── Stats ─────────────────────────────────────────────────────────────────────
def stats(s, start, end):
    x = s[(s.index >= start) & (s.index <= end)].dropna()
    if len(x) < 6:
        return dict(sharpe=np.nan, cagr=np.nan, maxdd=np.nan, neg_yrs=np.nan, n=0)
    ann  = x.mean() * 12
    vol  = x.std() * np.sqrt(12)
    sh   = ann / vol if vol > 0 else 0.0
    ec   = (1 + x).cumprod()
    mdd  = (ec / ec.cummax() - 1).min()
    neg  = int((x.groupby(x.index.year).apply(lambda g: (1+g).prod()-1) < 0).sum())
    return dict(sharpe=round(float(sh),3), cagr=round(float(ann),4),
                maxdd=round(float(mdd),4), neg_yrs=neg, n=len(x))


print(f"\n{'Variant':<28} {'IS Sh':>7} {'OOS Sh':>8} {'OOS CAGR':>10} "
      f"{'OOS MaxDD':>10} {'NegYrs':>7} {'WF':>6} {'Gate':>5}")
print("-" * 88)

results, all_stats = {}, {}
for label, s in variants.items():
    is_s  = stats(s, IS_START,  IS_END)
    oos_s = stats(s, OOS_START, OOS_END)
    wf    = (oos_s["sharpe"]/is_s["sharpe"]
             if (is_s["sharpe"] and not np.isnan(is_s["sharpe"]) and is_s["sharpe"] > 0.01)
             else np.nan)
    gate  = ("PASS"
             if (oos_s["sharpe"] >= GATE_SHARPE and not np.isnan(wf) and WF_LO <= wf <= WF_HI)
             else "fail")
    wf_str = f"{wf:.2f}" if not np.isnan(wf) else "n/a"
    print(f"{label:<28} {is_s['sharpe']:>7.3f} {oos_s['sharpe']:>8.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%} "
          f"{str(oos_s['neg_yrs']):>7} {wf_str:>6}  {gate}")
    results[label] = {"is": is_s, "oos": oos_s, "wf_ratio": round(wf,3) if not np.isnan(wf) else None, "gate": gate}
    all_stats[label] = s

spy_oos = stats(ret["SPY"], OOS_START, OOS_END)
spy_is  = stats(ret["SPY"], IS_START,  IS_END)
print(f"{'SPY buy-hold':<28} {spy_is['sharpe']:>7.3f} {spy_oos['sharpe']:>8.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")


# ── Year-by-year OOS (best variant) ──────────────────────────────────────────
print("\n[4] OOS year-by-year breakdown...")
best_label = max((l for l in results if results[l]["oos"]["sharpe"] is not None
                  and not np.isnan(results[l]["oos"]["sharpe"])),
                 key=lambda l: results[l]["oos"]["sharpe"])
best_s = all_stats[best_label]
spy_m  = ret["SPY"]

print(f"\n    Best variant: {best_label}")
print(f"    {'Year':<6} {'Strategy':>10} {'SPY':>8} {'Excess':>8}")
print("    " + "-" * 35)
for yr in range(2018, 2027):
    s_yr  = best_s[best_s.index.year == yr]
    sp_yr = spy_m[spy_m.index.year == yr]
    if len(s_yr) < 3:
        continue
    s_ann  = (1 + s_yr).prod() - 1
    sp_ann = (1 + sp_yr).prod() - 1
    excess = s_ann - sp_ann
    print(f"    {yr:<6} {s_ann:>10.1%} {sp_ann:>8.1%} {excess:>+8.1%}")


# ── Yield curve regime analysis ───────────────────────────────────────────────
print("\n[5] Yield curve regime breakdown (OOS)...")
oos_mask = (yc_monthly.index >= OOS_START) & (yc_monthly.index <= OOS_END)
oos_yc   = yc_monthly[oos_mask]
print(f"    Inverted (<-0.5%): {(oos_yc < -0.005).sum()} months "
      f"({(oos_yc < -0.005).mean():.0%})")
print(f"    Neutral  (-0.5% to +1.5%): {((oos_yc >= -0.005) & (oos_yc <= 0.015)).sum()} months")
print(f"    Steep    (>+1.5%): {(oos_yc > 0.015).sum()} months "
      f"({(oos_yc > 0.015).mean():.0%})")


# ── Verdict ───────────────────────────────────────────────────────────────────
best_oos = max((v["oos"]["sharpe"] for v in results.values()
                if v["oos"]["sharpe"] is not None), default=0.0)
best_wf  = next((results[l]["wf_ratio"] for l in results
                 if results[l]["oos"]["sharpe"] == best_oos and results[l]["wf_ratio"]), None)
any_pass = any(v["gate"] == "PASS" for v in results.values())

print("\n" + "=" * 65)
print(f"H314 RESULT: {'CONFIRMED' if any_pass else 'NOT CONFIRMED'}")
print(f"  Best variant:   {best_label}")
print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: > {GATE_SHARPE})")
print(f"  Best WF ratio:   {best_wf if best_wf else 'n/a'}")
print(f"  Baseline (H045 gate): {GATE_SHARPE}")
print("=" * 65)


# ── Save ──────────────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H314",
    "title": "Duration-Factor Overlay on Bond ETF Rotation",
    "universe": UNIVERSE,
    "short_dur_subset": SHORT_DUR,
    "is_period":  f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": f"OOS Sharpe >= {GATE_SHARPE} AND WF in [{WF_LO},{WF_HI}]",
    "confirmed": bool(any_pass),
    "best_oos_sharpe": round(best_oos, 3),
    "best_variant": best_label,
    "spy_oos": spy_oos,
    "variants": results,
}
path = RESULT_DIR / "h314_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
