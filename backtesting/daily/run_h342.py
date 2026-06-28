"""
H342 — VIX Term Structure Premium Harvest (SVXY Timing)
=========================================================
Source: Simon & Campasano (2014) "The VIX Futures Basis: Evidence and Trading
        Strategies" (JFM); Whaley (2009) "Understanding the VIX" (JPI);
        Eraker & Yang (2013) "The Price of Variance Risk" (JFE).

Hypothesis: The volatility risk premium (VRP) is most harvestable when the VIX
term structure is in contango (front < back) — i.e., VIX/VXV < 1.0.
SVXY (-0.5x inverse VIX futures ETF) profits from roll yield when contango is
steep. In backwardation, switch to BIL to avoid short-squeeze risk.

Note: SVXY changed from -1x to -0.5x leverage on Feb 28, 2018 (Volmageddon
response). Pre-2018 returns are for a more aggressive instrument.

Signal (monthly, using month-end VIX/VXV):
  - VIX/VXV < 0.90  → hold SVXY  (strong contango, high roll yield)
  - 0.90 ≤ ratio < 1.0 → hold SPY  (mild contango, vol premium but safer)
  - ratio ≥ 1.0     → hold BIL  (backwardation, avoid SVXY)

Universe tickers: SVXY, SPY, BIL, ^VIX (spot), ^VXV / ^VIX3M (3-month VIX)
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.0 (new family; higher gate applied to confirmed variants)

Variants:
  A: SVXY/BIL (contango threshold 1.0 — pure VRP harvest vs defensive)
  B: SVXY/SPY/BIL (three-way: strong contango / mild contango / backwardation)
  C: SVXY/SPY (no cash; always in vol premium or equity)
  D: SVXY/BIL with VIX < 20 entry gate (add low-vol filter on top)
  E: SPY-only momentum baseline (hold SPY if VIX/VXV < 1.0, else BIL)
"""
import warnings
warnings.filterwarnings("ignore")
import json, os, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

DATA_START = "2010-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

# ── Data download ─────────────────────────────────────────────────────────────
print("Downloading price data...")
asset_tickers = ["SVXY", "SPY", "BIL"]
raw = yf.download(asset_tickers, start=DATA_START, end=DATA_END, progress=False, auto_adjust=True)["Close"]
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(0)
raw = raw.ffill().dropna(how="all")

# VIX data
print("Downloading VIX term structure...")
vix_raw = yf.download(["^VIX", "^VXV"], start=DATA_START, end=DATA_END, progress=False)["Close"]
if isinstance(vix_raw.columns, pd.MultiIndex):
    vix_raw.columns = vix_raw.columns.get_level_values(0)

# ^VXV might not be available — try ^VIX3M as fallback
if "^VXV" not in vix_raw.columns or vix_raw["^VXV"].isna().mean() > 0.5:
    print("  ^VXV not available, trying ^VIX3M...")
    vix3m_raw = yf.download(["^VIX3M"], start=DATA_START, end=DATA_END, progress=False)["Close"]
    if isinstance(vix3m_raw, pd.DataFrame):
        if isinstance(vix3m_raw.columns, pd.MultiIndex):
            vix3m_raw.columns = vix3m_raw.columns.get_level_values(0)
        if "^VIX3M" in vix3m_raw.columns:
            vix_raw["^VXV"] = vix3m_raw["^VIX3M"]

vix_raw = vix_raw.ffill().dropna(how="all")
vix_spot = vix_raw["^VIX"] if "^VIX" in vix_raw.columns else None
vxv_3m   = vix_raw["^VXV"] if "^VXV" in vix_raw.columns else None

if vix_spot is None or vxv_3m is None:
    print("ERROR: Could not load VIX/VXV data")
    exit(1)

# Term structure ratio (daily, then resample monthly)
ratio_daily = (vix_spot / vxv_3m).dropna()
print(f"  VIX/VXV ratio: mean={ratio_daily.mean():.3f}, std={ratio_daily.std():.3f}")
print(f"  Contango pct (ratio<1.0): {(ratio_daily < 1.0).mean():.1%}")

# Monthly prices and returns
monthly = raw.resample("ME").last().ffill()
rets    = monthly.pct_change()
ratio_m = ratio_daily.resample("ME").last()  # month-end ratio signal

# Align all series
common_idx = rets.index.intersection(ratio_m.index)
rets    = rets.loc[common_idx]
ratio_m = ratio_m.loc[common_idx]

print(f"  Monthly periods: {len(rets)} | from {rets.index[0].date()} to {rets.index[-1].date()}")

# VIX level (monthly) for Variant D gate
vix_m = vix_spot.resample("ME").last().reindex(common_idx)

# ── Backtest engine ───────────────────────────────────────────────────────────

def backtest(signal_fn, rets, ratio_m, vix_m):
    """
    signal_fn: function(ratio, vix) → ticker to hold
    Returns portfolio returns series.
    """
    port_rets = []
    dates = []
    for i in range(len(rets) - 1):
        t       = rets.index[i]
        t_next  = rets.index[i + 1]
        ratio   = ratio_m.iloc[i]
        vix_lvl = vix_m.iloc[i] if vix_m is not None else np.nan
        if np.isnan(ratio):
            continue
        ticker  = signal_fn(ratio, vix_lvl)
        if ticker not in rets.columns:
            continue
        r = rets.loc[t_next, ticker]
        if np.isnan(r):
            continue
        port_rets.append(r)
        dates.append(t_next)
    return pd.Series(port_rets, index=dates)

# Signal functions
def sig_A(ratio, vix):   return "SVXY" if ratio < 1.0 else "BIL"
def sig_B(ratio, vix):
    if ratio < 0.90: return "SVXY"
    if ratio < 1.0:  return "SPY"
    return "BIL"
def sig_C(ratio, vix):   return "SVXY" if ratio < 1.0 else "SPY"
def sig_D(ratio, vix):
    # Add VIX < 20 gate for SVXY entry
    if ratio < 1.0 and not np.isnan(vix) and vix < 20:
        return "SVXY"
    return "BIL"
def sig_E(ratio, vix):   return "SPY" if ratio < 1.0 else "BIL"

# ── Run variants ──────────────────────────────────────────────────────────────
print("\nRunning variants...")
rets_fill = rets[["SVXY","SPY","BIL"]].fillna(method="ffill")

variants = {
    "A_SVXY_BIL_contango1.0"  : backtest(sig_A, rets_fill, ratio_m, vix_m),
    "B_three_way"             : backtest(sig_B, rets_fill, ratio_m, vix_m),
    "C_SVXY_SPY"              : backtest(sig_C, rets_fill, ratio_m, vix_m),
    "D_SVXY_BIL_VIX20"        : backtest(sig_D, rets_fill, ratio_m, vix_m),
    "E_SPY_BIL_baseline"      : backtest(sig_E, rets_fill, ratio_m, vix_m),
}

spy_rets = rets_fill["SPY"].dropna()

# ── Metrics ────────────────────────────────────────────────────────────────────
def metrics(r_series, period_start, period_end):
    r = r_series.loc[period_start:period_end].dropna()
    if len(r) < 6:
        return dict(sharpe=np.nan, cagr=np.nan, maxdd=np.nan, neg_years=np.nan, n=0)
    ann  = r.mean() * 12
    vol  = r.std() * np.sqrt(12)
    sharpe = ann / vol if vol > 0 else np.nan
    cumulative = (1 + r).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    maxdd = drawdown.min()
    years = r.resample("YE").sum()
    neg_years = (years < 0).sum()
    cagr = cumulative.iloc[-1] ** (12 / len(r)) - 1
    return dict(sharpe=round(sharpe,3), cagr=round(cagr,3), maxdd=round(maxdd,3),
                neg_years=int(neg_years), n=len(r))

print(f"\n{'':30s} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'OOS MaxDD':>10} {'OOS CAGR':>9} {'Neg Yrs':>8}")
print("-"*80)

results = {}
for name, rv in variants.items():
    is_m  = metrics(rv, IS_START,  IS_END)
    oos_m = metrics(rv, OOS_START, OOS_END)
    results[name] = {"is": is_m, "oos": oos_m}
    print(f"  {name:28s}  {is_m['sharpe']:>10.3f}  {oos_m['sharpe']:>11.3f}  "
          f"{oos_m['maxdd']:>10.3f}  {oos_m['cagr']:>9.3f}  {oos_m['neg_years']:>8}")

spy_is_m  = metrics(spy_rets, IS_START, IS_END)
spy_oos_m = metrics(spy_rets, OOS_START, OOS_END)
print(f"  {'SPY (benchmark)':28s}  {spy_is_m['sharpe']:>10.3f}  {spy_oos_m['sharpe']:>11.3f}  "
      f"{spy_oos_m['maxdd']:>10.3f}  {spy_oos_m['cagr']:>9.3f}  {spy_oos_m['neg_years']:>8}")
print(f"  {'Gate':28s}  {'—':>10}  {'1.000':>11}  {'—':>10}")

# ── Walk-forward ratios ────────────────────────────────────────────────────────
print("\nWalk-forward ratios (OOS/IS Sharpe):")
best_oos  = -np.inf
best_name = ""
for name, r in results.items():
    wf = r['oos']['sharpe'] / r['is']['sharpe'] if r['is']['sharpe'] > 0 else np.nan
    print(f"  {name}: {wf:.3f}" if not np.isnan(wf) else f"  {name}: n/a")
    if not np.isnan(r['oos']['sharpe']) and r['oos']['sharpe'] > best_oos:
        best_oos  = r['oos']['sharpe']
        best_name = name

gate = 1.0
verdict = "CONFIRMED" if best_oos >= gate else "NOT CONFIRMED"
print(f"\nBest OOS Sharpe: {best_oos:.3f} ({best_name})")
print(f"Gate: {gate} → {verdict}")

# ── Contango regime summary ───────────────────────────────────────────────────
ratio_oos = ratio_m.loc[OOS_START:OOS_END].dropna()
print(f"\nOOS regime summary (2021-2026):")
print(f"  Contango (<1.0): {(ratio_oos < 1.0).mean():.1%}")
print(f"  Mild contango (0.9-1.0): {((ratio_oos >= 0.9) & (ratio_oos < 1.0)).mean():.1%}")
print(f"  Strong contango (<0.9): {(ratio_oos < 0.9).mean():.1%}")
print(f"  Backwardation (>=1.0): {(ratio_oos >= 1.0).mean():.1%}")

# ── SPY correlation ───────────────────────────────────────────────────────────
print("\nCorrelation vs SPY (OOS):")
spy_oos_v = spy_rets.loc[OOS_START:OOS_END].dropna()
for name, rv in variants.items():
    v_oos = rv.loc[OOS_START:OOS_END].dropna()
    common = v_oos.index.intersection(spy_oos_v.index)
    if len(common) > 5:
        c = np.corrcoef(v_oos.loc[common], spy_oos_v.loc[common])[0,1]
        print(f"  Corr({name}, SPY): {c:.3f}")

# ── Save results ──────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H342",
    "description": "VIX Term Structure Premium Harvest — SVXY/SPY/BIL Timing via VIX/VXV Ratio",
    "source": "Simon & Campasano (2014) JFM; Whaley (2009) JPI; Eraker & Yang (2013) JFE",
    "gate": gate,
    "variants": {k: v for k, v in results.items()},
    "best_variant": best_name,
    "best_oos_sharpe": round(best_oos, 3),
    "verdict": verdict,
}
with open(RESULT_DIR / "h342_results.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to backtesting/results/h342_results.json")
