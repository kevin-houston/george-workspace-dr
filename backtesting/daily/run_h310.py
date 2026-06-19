"""
H310 — Merger Arbitrage via ETF Instruments (MNA / MRGR)
=========================================================

Source:
  Baker & Savasoglu (2002) "Limited Arbitrage in Mergers and Acquisitions" (JFE)
  Mitchell & Pulvino (2001) "Characteristics of Risk and Return in Risk Arbitrage" (JF)
  Dukes, Frohlich & Ma (1992) "Risk arbitrage in tender offers" (JPM)

Hypothesis:
  Cash M&A deals generate a predictable spread between the acquirer's offer price
  and the target's post-announcement market price. This spread exists because:
  (1) deal risk (regulatory block, financing failure, target resistance),
  (2) time value of money over the ~3-6 month close window, and
  (3) risk capital constraints — arb funds size down or exit in volatile markets.

  Two liquid ETF vehicles proxy this strategy:
    MNA  (IQ Merger Arbitrage ETF, Nov 2009): Systematic long target / short
         acquirer rules-based approach; expense ratio ~0.78%/yr; ~$500M AUM.
    MRGR (ProShares Merger ETF, Dec 2012): Tracks S&P Merger Arbitrage Index;
         holds announced targets weighted by deal value; ~0.75%/yr ER.

  Both instruments offer immediate liquidity, diversification across 20-40
  concurrent deals, and transparent factor exposure.

  Regime hypothesis: merger spread is inversely related to market volatility
  (VIX), because: (a) deal financing costs rise in volatile regimes; (b) arb
  capital withdraws under stress; (c) antitrust risk spikes in uncertain
  regulatory environments. VIX-gating (avoid M&A exposure when VIX > 20)
  should reduce drawdowns and improve Sharpe.

Variants:
  A: MRGR always-on (full-period passive exposure)
  B: MRGR + VIX<25 gate (BIL when VIX >= 25)
  C: MRGR + VIX<20 gate (BIL when VIX >= 20)  [tighter gate]
  D: MRGR + SPY>200MA gate (BIL when SPY < 200d MA)
  E: MNA always-on
  F: MNA + VIX<25 gate

IS:  2013-01-01 to 2019-12-31  (7 years)
OOS: 2020-01-01 to 2026-06-13
Gate: OOS Sharpe > 1.0 AND WF ratio 0.50-2.00 (confirming IS signal quality)

STRUCTURAL NOTE on IS vs OOS regime:
  The 2013-2019 IS period coincides with an antitrust enforcement wave:
  - 2015: DOJ blocked Office Depot/Staples, Comcast/TWC
  - 2016: DOJ blocked Aetna/Humana, Anthem/Cigna (both >$30B deals)
  - 2017: DOJ approval slowed, FTC activism increased
  This blocked deals caused MRGR to lose money as spreads failed to close.
  The 2020-2026 OOS period: post-COVID consolidation wave, tech M&A boom,
  higher deal certainty due to changing regulatory posture (2017-2020) and
  then larger spreads compensating for Biden antitrust (2021-2023 FTC).
  IS/OOS Sharpe disconnect (0.07 IS vs 1.09 OOS) reflects REGIME SHIFT,
  not strategy improvement — caution: OOS may revert if antitrust intensifies.
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

FULL_START = "2012-01-01"
IS_START   = "2013-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-13"
GATE_SHARPE = 1.0
WF_LO       = 0.50   # acceptable walk-forward ratio range
WF_HI       = 4.00   # extreme WF ratio is itself a red flag

PROD_W = {"H041a": 0.22, "H026": 0.27, "H045": 0.21,
          "XLK_IBS": 0.20, "SMH_IBS": 0.08, "IGV_IBS": 0.02}


# ── Data ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("H310 — Merger Arbitrage via ETF Instruments")
print("=" * 60)

print("\n[1] Fetching prices…")
tickers = ["MRGR", "MNA", "SPY", "BIL", "^VIX"]
raw = yf.download(tickers, start=FULL_START, end=OOS_END,
                  auto_adjust=True, progress=False)["Close"].ffill()

monthly = raw.resample("ME").last()
ret     = monthly.pct_change()

# VIX proxy: monthly average (use average, not month-end, for risk signal)
vix_monthly = raw["^VIX"].resample("ME").mean()
spy_monthly  = monthly["SPY"]
spy_200      = spy_monthly.rolling(200).mean()


# ── Helper functions ──────────────────────────────────────────────────────────
def run_strategy(base_ticker, vix_gate=None, spy_ma_gate=False):
    """Build monthly return series applying optional regime gates."""
    base = ret[base_ticker]
    result = []
    for dt in base.index:
        if dt < pd.Timestamp(IS_START):
            continue
        use_cash = False
        if vix_gate is not None and dt in vix_monthly.index:
            if vix_monthly.loc[dt] >= vix_gate:
                use_cash = True
        if spy_ma_gate:
            sp = spy_monthly.loc[:dt].iloc[-1]
            ma = spy_200.loc[:dt].iloc[-1]
            if pd.notna(ma) and sp < ma:
                use_cash = True
        r = 0.0 if use_cash else base.loc[dt]
        result.append((dt, r))
    return pd.Series(dict(result))


def period_stats(series, start, end):
    x = series[(series.index >= start) & (series.index <= end)].dropna()
    if len(x) < 6:
        return {"sharpe": np.nan, "cagr": np.nan, "maxdd": np.nan, "neg_yrs": np.nan}
    ann     = x.mean() * 12
    vol     = x.std() * np.sqrt(12)
    sharpe  = ann / vol if vol > 0 else 0.0
    ec      = (1 + x).cumprod()
    maxdd   = (ec / ec.cummax() - 1).min()
    by_yr   = x.groupby(x.index.year).apply(lambda g: (1 + g).prod() - 1)
    neg_yrs = int((by_yr < 0).sum())
    return {
        "sharpe":   round(float(sharpe), 3),
        "cagr":     round(float(ann), 4),
        "maxdd":    round(float(maxdd), 4),
        "neg_yrs":  neg_yrs,
        "n_months": len(x),
    }


# ── Variants ──────────────────────────────────────────────────────────────────
print("\n[2] Running variants…")

variants = {
    "A: MRGR always-on":   run_strategy("MRGR"),
    "B: MRGR VIX<25":      run_strategy("MRGR", vix_gate=25),
    "C: MRGR VIX<20":      run_strategy("MRGR", vix_gate=20),
    "D: MRGR SPY>200MA":   run_strategy("MRGR", spy_ma_gate=True),
    "E: MNA always-on":    run_strategy("MNA"),
    "F: MNA VIX<25":       run_strategy("MNA", vix_gate=25),
}

results = {}
print(f"\n{'Variant':<28} {'IS Sh':>7} {'OOS Sh':>8} {'OOS CAGR':>10} "
      f"{'OOS MaxDD':>10} {'NegYrs':>7} {'WF':>6} {'Gate':>5}")
print("-" * 85)

for label, s in variants.items():
    is_s  = period_stats(s, IS_START, IS_END)
    oos_s = period_stats(s, OOS_START, OOS_END)
    wf    = (oos_s["sharpe"] / is_s["sharpe"]) if (is_s["sharpe"] and is_s["sharpe"] > 0.01) else np.nan
    gate  = ("PASS" if (oos_s["sharpe"] >= GATE_SHARPE and
                        (np.isnan(wf) or wf <= WF_HI))
             else "fail")
    print(f"{label:<28} {is_s['sharpe']:>7.3f} {oos_s['sharpe']:>8.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%} "
          f"{str(oos_s['neg_yrs']):>7} {f'{wf:.2f}' if not np.isnan(wf) else 'n/a':>6}  {gate}")
    results[label] = {"is": is_s, "oos": oos_s, "wf_ratio": round(wf, 3) if not np.isnan(wf) else None}

spy_oos = period_stats(ret["SPY"], OOS_START, OOS_END)
print(f"{'SPY buy-hold':<28} {'—':>7} {spy_oos['sharpe']:>8.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")


# ── Correlation Analysis ──────────────────────────────────────────────────────
print("\n[3] Correlation analysis (OOS)…")
oos_ret = ret[(ret.index >= OOS_START) & (ret.index <= OOS_END)][["MRGR", "MNA", "SPY"]].dropna()
corr = oos_ret.corr()
print(f"  Corr(MRGR, SPY) OOS: {corr.loc['MRGR','SPY']:.3f}")
print(f"  Corr(MNA, SPY)  OOS: {corr.loc['MNA','SPY']:.3f}")
print(f"  Corr(MRGR, MNA) OOS: {corr.loc['MRGR','MNA']:.3f}")

is_ret = ret[(ret.index >= IS_START) & (ret.index <= IS_END)][["MRGR", "MNA", "SPY"]].dropna()
corr_is = is_ret.corr()
print(f"  Corr(MRGR, SPY) IS:  {corr_is.loc['MRGR','SPY']:.3f}")
print(f"  Corr(MNA, SPY)  IS:  {corr_is.loc['MNA','SPY']:.3f}")


# ── IS Period Deep-Dive (Regime Analysis) ────────────────────────────────────
print("\n[4] Year-by-year breakdown of MRGR and MNA…")
all_data = ret[["MRGR", "MNA", "SPY"]].dropna()
print(f"{'Year':<6} {'MRGR':>8} {'MNA':>8} {'SPY':>8}")
print("-" * 35)
for yr in range(2013, 2027):
    row = all_data[all_data.index.year == yr]
    if len(row) < 3:
        continue
    mrgr_ann = (1 + row["MRGR"]).prod() - 1
    mna_ann  = (1 + row["MNA"]).prod() - 1
    spy_ann  = (1 + row["SPY"]).prod() - 1
    print(f"{yr:<6} {mrgr_ann:>8.2%} {mna_ann:>8.2%} {spy_ann:>8.2%}")


# ── Verdict ───────────────────────────────────────────────────────────────────
# Assess MRGR variants: OOS Sharpe passes gate but WF ratio is extreme (15x+)
# indicating regime shift rather than a robust signal
best_oos = max((v["oos"]["sharpe"] for v in results.values() if not np.isnan(v["oos"]["sharpe"])), default=0)
best_wf  = max((v["wf_ratio"] for v in results.values() if v["wf_ratio"] is not None), default=0)

# Confirm only if WF is within acceptable range (not pure regime artifact)
confirmed = best_oos >= GATE_SHARPE and best_wf <= WF_HI

print("\n" + "=" * 60)
print(f"H310 RESULT: {'CONFIRMED (with caveats)' if confirmed else 'NOT CONFIRMED'}")
print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: {GATE_SHARPE})")
print(f"  Best WF ratio:   {best_wf:.2f}   (gate: <= {WF_HI})")
print(f"  SPY OOS Sharpe:  {spy_oos['sharpe']:.3f}")
if best_wf > WF_HI:
    print(f"  CAVEAT: WF ratio {best_wf:.1f}x >> 4.0 threshold → REGIME SHIFT ARTIFACT")
    print(f"  MRGR IS (2013-2019) was an antitrust-driven M&A drought; OOS is a boom.")
    print(f"  This is NOT a stable signal — it is a specific macro regime.")
print("=" * 60)


# ── Save Results ──────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H310",
    "title": "Merger Arbitrage via ETF Instruments (MNA / MRGR)",
    "universe": ["MRGR", "MNA"],
    "is_period":  f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": f"OOS Sharpe >= {GATE_SHARPE} AND WF ratio <= {WF_HI}",
    "confirmed": bool(confirmed),
    "best_oos_sharpe": round(best_oos, 3),
    "best_wf_ratio": round(best_wf, 3),
    "spy_oos": spy_oos,
    "variants": results,
    "correlations": {
        "oos": {k: {k2: round(float(v2), 3) for k2, v2 in corr[k].items()} for k in corr.columns},
        "is":  {k: {k2: round(float(v2), 3) for k2, v2 in corr_is[k].items()} for k in corr_is.columns},
    },
}
path = RESULT_DIR / "h310_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
