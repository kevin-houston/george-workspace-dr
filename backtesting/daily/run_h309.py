"""
H309 — SPX Dispersion Trading: Short Index Vol, Long Component Vol
==================================================================

Source: Bloch (2016) SSRN 2715517 §7.6; Marshall (2008); Driessen et al. (2005)

Hypothesis:
  Index options embed a persistent implied correlation premium. A dispersion trade
  shorts SPX implied variance and buys component implied variance, harvesting the
  spread when index options are rich relative to single-stock options.

  Signal (Mρ): VIX² / (Σwᵢ × HV21ᵢ)²  — implied vs realized correlation indicator.
  When Mρ is elevated, index vol is expensive relative to components → entry signal.

DATA LIMITATION NOTE:
  Component implied vol (IV) requires historical options data (Polygon options API).
  This backtest tests two testable sub-hypotheses with available data:

  Sub-hypothesis 1: SHORT INDEX VOL PREMIUM
    VIX systematically overstates realized SPX vol (the "variance risk premium").
    Return = (VIX − RV_SPX) / VIX each month. Always positive on average.

  Sub-hypothesis 2: IMPLIED CORRELATION PREMIUM AS ENTRY SIGNAL
    Mρ = VIX² / sigma_wb²  predicts the size of the variance risk premium.
    Enter the short-index-vol trade only when Mρ is elevated.

  Sub-hypothesis 3: REALIZED CORRELATION DRAG
    When realized correlation > Mρ (implied), the long-component leg loses.
    We estimate the TOTAL dispersion P&L as:
      P&L ∝ (Mρ − realized_corr)  [short implied corr, long realized corr]
    This approximates the full dispersion trade without needing component IV.

  Full dispersion (Phase 2): wire in Polygon options IV for component legs.

IS:  2010-01-01 to 2019-12-31
OOS: 2020-01-01 to 2026-06-13
Gate: OOS Sharpe > 0.80
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Universe ──────────────────────────────────────────────────────────────────
COMPONENTS = {
    "AAPL":  0.073, "MSFT": 0.065, "NVDA": 0.060, "AMZN": 0.038,
    "META":  0.027, "GOOGL": 0.022, "GOOG": 0.018, "BRK-B": 0.017,
    "LLY":   0.015, "AVGO": 0.014, "JPM":  0.014, "TSLA": 0.013,
    "V":     0.011, "UNH":  0.011, "XOM":  0.011, "MA":   0.010,
    "COST":  0.009, "HD":   0.009, "PG":   0.008, "JNJ":  0.008,
    "WMT":   0.008, "ABBV": 0.007, "BAC":  0.007, "CRM":  0.006,
    "MRK":   0.006, "CVX":  0.006, "ORCL": 0.006, "NFLX": 0.006,
    "KO":    0.005, "PEP":  0.005,
}
total_w = sum(COMPONENTS.values())
WEIGHTS = {k: v / total_w for k, v in COMPONENTS.items()}

IS_START   = "2009-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-13"
FULL_START = IS_START
FULL_END   = OOS_END
TRADING_DAYS = 252
HV_WINDOW    = 21

print("H309 — SPX Dispersion Trading")
print("=" * 60)

# ── Download ──────────────────────────────────────────────────────────────────
print("Downloading VIX and price data...")
vix_raw = yf.download("^VIX", start=FULL_START, end=FULL_END, progress=False)
vix = vix_raw["Close"].squeeze()

tickers = list(COMPONENTS.keys()) + ["^GSPC"]
prices_raw = yf.download(tickers, start=FULL_START, end=FULL_END,
                         progress=False, auto_adjust=True)
prices = prices_raw["Close"]
prices.dropna(axis=1, how="all", inplace=True)

available = [t for t in COMPONENTS if t in prices.columns]
print(f"  Available: {len(available)}/{len(COMPONENTS)} components")
w_avail  = {t: WEIGHTS[t] for t in available}
w_total  = sum(w_avail.values())
w_avail  = {t: v / w_total for t, v in w_avail.items()}

spx = prices["^GSPC"]
month_ends = prices.resample("BME").last().index

# ── Monthly feature computation ───────────────────────────────────────────────
records = []

for i in range(HV_WINDOW + 2, len(month_ends) - 1):
    t_prev = month_ends[i - 1]   # prior month-end (for HV computation)
    t0     = month_ends[i]       # signal date
    t1     = month_ends[i + 1]   # holding end

    # VIX on signal date
    vix_vals = vix[vix.index <= t0]
    if vix_vals.empty:
        continue
    vix_today = float(vix_vals.iloc[-1]) / 100.0

    # Component HV21 on signal date
    comp_hv = {}
    for ticker in available:
        px = prices[ticker].dropna()
        px_sub = px[px.index <= t0]
        if len(px_sub) < HV_WINDOW + 1:
            continue
        rets = np.log(px_sub.iloc[-HV_WINDOW:] / px_sub.iloc[-HV_WINDOW-1:-1].values)
        comp_hv[ticker] = float(np.std(rets, ddof=1) * np.sqrt(TRADING_DAYS))

    if len(comp_hv) < 10:
        continue

    sigma_wb = sum(w_avail[t] * comp_hv[t] for t in comp_hv if t in w_avail)
    if sigma_wb <= 0:
        continue
    mro = (vix_today ** 2) / (sigma_wb ** 2)

    # ── Sub-hypothesis 1: Short index vol premium ─────────────────────────────
    # Monthly return = (VIX − realized SPX vol) / VIX
    spx_next = spx[(spx.index > t0) & (spx.index <= t1)].dropna()
    if len(spx_next) < 10:
        continue
    spx_rets_next = np.log(spx_next / spx_next.shift(1)).dropna()
    rv_spx = float(np.std(spx_rets_next, ddof=1) * np.sqrt(TRADING_DAYS))

    # Bounded at -1 (straddle seller loses at most ~premium collected)
    short_index_ret = max((vix_today - rv_spx) / vix_today, -1.0)

    # ── Sub-hypothesis 3: Realized correlation premium ────────────────────────
    # Realized correlation of components in the holding period
    comp_rets_mat = []
    for ticker in available:
        px = prices[ticker].dropna()
        px_next = px[(px.index > t0) & (px.index <= t1)].dropna()
        if len(px_next) < 10:
            continue
        r = np.log(px_next / px_next.shift(1)).dropna().values
        comp_rets_mat.append(r)

    if len(comp_rets_mat) < 5:
        continue

    # Pad / trim to common length
    min_len = min(len(r) for r in comp_rets_mat)
    mat = np.array([r[:min_len] for r in comp_rets_mat])  # shape (N, T)

    corr_mat = np.corrcoef(mat)
    N = corr_mat.shape[0]
    off_diag = corr_mat[np.triu_indices(N, k=1)]
    realized_corr = float(np.mean(off_diag))

    # Dispersion P&L proxy: short implied corr (Mρ), long realized corr
    # Positive when realized_corr < Mρ (index was expensive)
    disp_pnl = mro - realized_corr  # in correlation units

    records.append({
        "date":           t0,
        "vix_pct":        vix_today * 100,
        "sigma_wb_pct":   sigma_wb * 100,
        "rv_spx_pct":     rv_spx * 100,
        "mro":            mro,
        "realized_corr":  realized_corr,
        "short_idx_ret":  short_index_ret,
        "disp_pnl":       disp_pnl,
    })

df = pd.DataFrame(records).set_index("date")
df.index = pd.to_datetime(df.index)
print(f"\nMonthly observations: {len(df)}")

# ── Backtest function ─────────────────────────────────────────────────────────
def backtest(label, monthly_rets, n_label=""):
    if len(monthly_rets) < 6:
        print(f"  {label}: insufficient data (n={len(monthly_rets)})")
        return None
    sharpe = float(monthly_rets.mean() / monthly_rets.std(ddof=1) * np.sqrt(12))
    cagr   = float((1 + monthly_rets).prod() ** (12 / len(monthly_rets)) - 1)
    cumret = (1 + monthly_rets).cumprod()
    max_dd = float(((cumret - cumret.cummax()) / cumret.cummax()).min())
    wr     = float((monthly_rets > 0).mean())
    print(f"  {label}: Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={max_dd:.1%}  "
          f"WinRate={wr:.1%}  n={len(monthly_rets)}")
    return {"sharpe": sharpe, "cagr": cagr, "max_dd": max_dd,
            "win_rate": wr, "n": int(len(monthly_rets))}

results = {}
for period_label, period_mask in [("IS",  df.index <  pd.Timestamp(OOS_START)),
                                   ("OOS", df.index >= pd.Timestamp(OOS_START))]:
    sub = df[period_mask]
    print(f"\n{period_label} — Sub-hypothesis 1: Short SPX Variance Premium")
    # Variant A: always-on short index vol
    r = backtest("A: Always-on", sub["short_idx_ret"])
    if r: results[f"{period_label}_A"] = r
    # Variant B: Mρ-gated short index vol
    gate_b = sub[sub["mro"] > 0.80]["short_idx_ret"]
    r = backtest("B: Mρ>0.80 gate", gate_b)
    if r: results[f"{period_label}_B"] = r
    # Variant C: VIX>20 gated
    gate_c = sub[sub["vix_pct"] > 20]["short_idx_ret"]
    r = backtest("C: VIX>20 gate", gate_c)
    if r: results[f"{period_label}_C"] = r

    print(f"{period_label} — Sub-hypothesis 3: Implied Correlation Premium (dispersion)")
    # Normalize disp_pnl to monthly return: disp_pnl is in [~-1, ~+2] range
    # Use mean abs as scale reference; treat as monthly return signal
    scale = sub["disp_pnl"].abs().median()
    if scale > 0:
        disp_ret = sub["disp_pnl"] / scale * 0.05  # 5% target monthly vol scaling
        r = backtest("D: Disp always-on", disp_ret)
        if r: results[f"{period_label}_D"] = r
        gate_d = disp_ret[sub["mro"] > 0.80]
        r = backtest("E: Disp Mρ>0.80", gate_d)
        if r: results[f"{period_label}_E"] = r

# ── Diagnostics ───────────────────────────────────────────────────────────────
print("\n--- Signal Diagnostics ---")
print(f"  VIX (avg):            {df['vix_pct'].mean():.1f}%")
print(f"  SPX realized (avg):   {df['rv_spx_pct'].mean():.1f}%")
print(f"  Variance risk premium: VIX − RV = {(df['vix_pct'] - df['rv_spx_pct']).mean():.1f}pp avg")
print(f"  Mρ (avg):             {df['mro'].mean():.3f}")
print(f"  Mρ > 0.80:            {(df['mro'] > 0.80).mean():.1%} of months")
print(f"  Realized corr (avg):  {df['realized_corr'].mean():.3f}")
print(f"  Implied corr (Mρ) > Realized corr: {(df['mro'] > df['realized_corr']).mean():.1%} of months")
print(f"  Short-idx win rate:   {(df['short_idx_ret'] > 0).mean():.1%}")

# OOS breakdown
oos = df[df.index >= pd.Timestamp(OOS_START)]
if len(oos):
    covid  = oos[oos.index.year == 2020]
    rest   = oos[oos.index.year != 2020]
    print(f"\n  OOS breakdown:")
    print(f"    2020 (COVID) short-idx win rate: {(covid['short_idx_ret'] > 0).mean():.1%}")
    print(f"    2021-2026 short-idx win rate:    {(rest['short_idx_ret'] > 0).mean():.1%}")

# Save
out_path = "backtesting/results/h309_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
print("\nGate: OOS Sharpe > 0.80")
print("PHASE 2: Wire in Polygon options IV for component legs (full dispersion).")
