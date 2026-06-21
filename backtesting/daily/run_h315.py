"""
H315 — Credit-Regime Gate on Bond ETF Rotation (H045 Enhancement)
===================================================================

Source:
  Bleaney & Vickery (1998) "Do Risk Premiums Fluctuate over Time?" (JIFMIM)
  Asness, Frazzini & Pedersen (2013) "Quality Minus Junk" (RFS — credit spread)
  FRED BAMLH0A0HYM2: ICE BofA US High Yield Index OAS (Option-Adjusted Spread)

Hypothesis:
  H045 uses backward-looking momentum to exclude HYG/LQD. But early in a credit
  event (widening spreads), HYG/LQD may still have positive trailing 3m momentum
  while the forward environment has deteriorated. The BAMLH0A0HYM2 OAS spread
  is a contemporaneous credit risk signal:

  - Stress (HY OAS > 450bps): Exclude all credit-risk bonds (HYG, LQD, VCIT, AGG)
    from the eligible universe. Only hold rate-risk or defensive bonds.
  - Neutral (300–450bps): Standard H045 full universe.
  - Rally (<300bps): Include HYG/LQD normally; they tend to lead in spread
    compression environments.

  Core question: Can a credit regime filter improve early exit from spread blowouts
  beyond what the momentum TSMOM filter provides?

Variants:
  A: H045 baseline (for direct comparison with H314-A)
  B: Credit stress gate (HY > 450bps → exclude HYG, LQD, VCIT, AGG)
  C: Tight stress gate (HY > 350bps → exclude credit bonds)
  D: Regime-tiered (HY > 500bps → SHY/BIL/IEI only; 350-500bps → no HYG;
     < 350bps → standard universe)

IS:  2008-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-06-20
Gate: OOS Sharpe > 1.044 (H314-A baseline this OOS period) AND WF ratio 0.5-4.0
Note: Full H045 target is 1.351 (OOS 2020-2026 basis); 1.044 is the realistic
      target for 2018-2026 which includes 2018-2019 rising-rate headwinds.
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

RESULT_DIR   = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2007-01-01"
IS_START     = "2008-01-01"
IS_END       = "2017-12-31"
OOS_START    = "2018-01-01"
OOS_END      = "2026-06-20"
GATE_SHARPE  = 1.044   # H314-A baseline (OOS 2018-2026)
WF_LO, WF_HI = 0.50, 4.00
N_TOP = 2

UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "BIL", "HYG", "LQD",
            "VCIT", "VCSH", "VMBS", "TIP", "GLD", "AGG"]
CREDIT_BONDS  = ["HYG", "LQD", "VCIT", "AGG"]   # spread-sensitive
RATE_SAFE     = ["SHY", "IEI", "IEF", "TLT", "BIL", "VCSH", "VMBS", "TIP", "GLD"]
CORE_SAFE     = ["SHY", "BIL", "IEI"]

print("=" * 65)
print("H315 — Credit-Regime Gate on Bond ETF Rotation")
print("=" * 65)

# ── FRED HY spread ────────────────────────────────────────────────────────────
print("\n[1] Fetching FRED BAMLH0A0HYM2 (HY OAS)...")
fred = Fred(api_key=os.environ["FRED_API_KEY"])
hy_daily = fred.get_series("BAMLH0A0HYM2", observation_start=FULL_START)
hy_monthly = hy_daily.resample("ME").last().ffill()   # already in %, e.g. 4.5 = 450bps

print(f"    Range: {hy_monthly.first_valid_index().date()} → {hy_monthly.last_valid_index().date()}")
print(f"    Stress  (>450bps) months: {(hy_monthly > 4.5).sum()}")
print(f"    Neutral (350-450bps):     {((hy_monthly >= 3.5) & (hy_monthly <= 4.5)).sum()}")
print(f"    Rally   (<350bps) months: {(hy_monthly < 3.5).sum()}")
print(f"    Min: {hy_monthly.min():.2f}%  Max: {hy_monthly.max():.2f}%  "
      f"Current: {hy_monthly.iloc[-1]:.2f}%")

# ── Price data ────────────────────────────────────────────────────────────────
print("\n[2] Fetching bond ETF prices...")
raw = yf.download(UNIVERSE + ["SPY"], start=FULL_START, end=OOS_END,
                  auto_adjust=True, progress=False)["Close"].ffill()
monthly = raw.resample("ME").last()
ret     = monthly.pct_change()
r3  = monthly.pct_change(3)
r6  = monthly.pct_change(6)
r12 = monthly.pct_change(12)


# ── Core selection logic ───────────────────────────────────────────────────────
def get_holdings(t, eligible, n=N_TOP):
    elig = [x for x in eligible if x in r3.columns and not pd.isna(r3.loc[t, x])]
    if not elig:
        return ["BIL"] if "BIL" in monthly.columns else []
    row = pd.DataFrame({
        "r3": r3.loc[t, elig], "r6": r6.loc[t, elig], "r12": r12.loc[t, elig],
    })
    row["score"] = (row["r3"].rank(na_option="bottom") +
                    row["r6"].rank(na_option="bottom") +
                    row["r12"].rank(na_option="bottom")) / 3
    filtered = row[row["r3"] >= 0]   # TSMOM filter
    if filtered.empty:
        return ["BIL"] if "BIL" in monthly.columns else elig[:1]
    return filtered.nlargest(min(n, len(filtered)), "score").index.tolist()


def get_hy(t):
    past = hy_monthly[hy_monthly.index <= t]
    return float(past.iloc[-1]) if len(past) > 0 else np.nan


# ── Variants ──────────────────────────────────────────────────────────────────
print("\n[3] Running variants...")

def run_variant(stress_threshold=None, tight_threshold=None, tiered=False):
    """
    stress_threshold: above this OAS%, exclude credit bonds (CREDIT_BONDS)
    tight_threshold:  above this OAS%, exclude credit bonds (tighter variant)
    tiered: three-regime model
    """
    series = {}
    months = ret.index[ret.index >= IS_START]
    for t in months[:-1]:
        i      = ret.index.get_loc(t)
        t_next = ret.index[i + 1]
        hy     = get_hy(t)
        if t not in r3.index:
            continue

        if tiered:
            if not np.isnan(hy) and hy > 5.0:
                eligible = CORE_SAFE   # extreme stress → only short Treasuries
            elif not np.isnan(hy) and hy > 3.5:
                eligible = RATE_SAFE   # moderate stress → no credit
            else:
                eligible = UNIVERSE    # rally → full universe
        elif stress_threshold and not np.isnan(hy) and hy > stress_threshold:
            eligible = RATE_SAFE
        else:
            eligible = UNIVERSE

        holdings = get_holdings(t, eligible)
        valid_h  = [h for h in holdings if h in ret.columns]
        series[t] = float(ret.loc[t_next, valid_h].mean()) if valid_h else 0.0

    return pd.Series(series)


variants = {
    "A: H045 baseline":       run_variant(),
    "B: Credit gate >450bps": run_variant(stress_threshold=4.5),
    "C: Tight gate >350bps":  run_variant(stress_threshold=3.5),
    "D: Tiered (500/350bps)": run_variant(tiered=True),
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


print(f"\n{'Variant':<30} {'IS Sh':>7} {'OOS Sh':>8} {'OOS CAGR':>10} "
      f"{'OOS MaxDD':>10} {'NegYrs':>7} {'WF':>6} {'Gate':>5}")
print("-" * 90)

results, all_series = {}, {}
for label, s in variants.items():
    is_s  = stats(s, IS_START,  IS_END)
    oos_s = stats(s, OOS_START, OOS_END)
    wf    = (oos_s["sharpe"] / is_s["sharpe"]
             if (is_s["sharpe"] and not np.isnan(is_s["sharpe"]) and is_s["sharpe"] > 0.01)
             else np.nan)
    gate  = ("PASS"
             if (oos_s["sharpe"] > GATE_SHARPE and not np.isnan(wf) and WF_LO <= wf <= WF_HI)
             else "fail")
    wf_str = f"{wf:.2f}" if not np.isnan(wf) else "n/a"
    print(f"{label:<30} {is_s['sharpe']:>7.3f} {oos_s['sharpe']:>8.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%} "
          f"{str(oos_s['neg_yrs']):>7} {wf_str:>6}  {gate}")
    results[label] = {"is": is_s, "oos": oos_s,
                      "wf_ratio": round(wf, 3) if not np.isnan(wf) else None, "gate": gate}
    all_series[label] = s

spy_oos = stats(ret["SPY"], OOS_START, OOS_END)
spy_is  = stats(ret["SPY"], IS_START,  IS_END)
print(f"{'SPY buy-hold':<30} {spy_is['sharpe']:>7.3f} {spy_oos['sharpe']:>8.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")


# ── Year-by-year OOS ──────────────────────────────────────────────────────────
print("\n[4] OOS year-by-year (all variants vs SPY)...")
print(f"\n{'Year':<6}", end="")
for lbl in variants:
    short = lbl.split(":")[0]
    print(f"  {short:>8}", end="")
print(f"  {'SPY':>8}")
print("-" * (6 + 10 * (len(variants) + 1)))

for yr in range(2018, 2027):
    sp_yr = ret["SPY"][ret["SPY"].index.year == yr]
    if len(sp_yr) < 3:
        continue
    print(f"{yr:<6}", end="")
    for lbl, s in all_series.items():
        yr_ret = s[s.index.year == yr]
        ann = (1 + yr_ret).prod() - 1 if len(yr_ret) >= 3 else np.nan
        print(f"  {ann:>8.1%}" if not np.isnan(ann) else f"  {'n/a':>8}", end="")
    sp_ann = (1 + sp_yr).prod() - 1
    print(f"  {sp_ann:>8.1%}")


# ── Credit regime performance ──────────────────────────────────────────────────
print("\n[5] Performance during credit stress periods (OOS, HY > 450bps)...")
stress_months = hy_monthly[(hy_monthly > 4.5) &
                            (hy_monthly.index >= OOS_START) &
                            (hy_monthly.index <= OOS_END)].index
print(f"    Stress months (OOS): {len(stress_months)}")
if len(stress_months) > 0:
    print(f"    Dates: {[str(d.date()) for d in stress_months[:10]]}")
    for lbl, s in all_series.items():
        stress_ret = s[s.index.isin(stress_months)]
        if len(stress_ret) > 0:
            print(f"    {lbl[:30]:<30} avg monthly ret: {stress_ret.mean():+.2%}")


# ── Verdict ───────────────────────────────────────────────────────────────────
best_oos  = max((v["oos"]["sharpe"] for v in results.values() if v["oos"]["sharpe"] is not None), default=0.0)
best_label = max((l for l in results), key=lambda l: results[l]["oos"]["sharpe"] or 0)
any_pass  = any(v["gate"] == "PASS" for v in results.values())

print("\n" + "=" * 65)
print(f"H315 RESULT: {'CONFIRMED' if any_pass else 'NOT CONFIRMED'}")
print(f"  Best variant:    {best_label}")
print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: > {GATE_SHARPE})")
print(f"  Baseline (H314-A / H045 2018-2026): {GATE_SHARPE}")
print("=" * 65)


# ── Save ──────────────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H315",
    "title": "Credit-Regime Gate on Bond ETF Rotation",
    "universe": UNIVERSE,
    "credit_bonds": CREDIT_BONDS,
    "is_period":  f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": f"OOS Sharpe > {GATE_SHARPE} AND WF in [{WF_LO},{WF_HI}]",
    "confirmed": bool(any_pass),
    "best_oos_sharpe": round(best_oos, 3),
    "best_variant": best_label,
    "spy_oos": spy_oos,
    "variants": results,
}
path = RESULT_DIR / "h315_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
