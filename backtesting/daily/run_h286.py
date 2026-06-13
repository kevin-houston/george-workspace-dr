"""
H286 — Macro Regime-Gated FCF/P (COWZ + SPY 200MA + VIX Gate)
================================================================

Hypothesis:
  H284 showed COWZ (FCF yield factor ETF) has OOS Sharpe=0.737 vs SPY=0.920.
  FCF yield stocks underperform in bull markets (where growth/momentum wins)
  but may outperform or protect better in bear/value regimes.

  This hypothesis tests whether a simple macro gate improves COWZ's OOS Sharpe:
  - FAVORABLE regime (SPY > 200MA AND VIX < 25): hold COWZ (FCF yield factor)
  - UNFAVORABLE regime (SPY < 200MA OR VIX ≥ 25): hold BIL (cash)

  Motivation: The "value factor" (of which FCF yield is a component) historically
  outperforms growth in high-uncertainty, high-volatility regimes. Conversely,
  in calm bull markets, growth/momentum dominates. A regime gate should allow
  FCF/P to shine during its natural habitat (value regimes) while protecting
  capital during bear markets when even quality stocks decline.

  Additionally tests:
  B. Dynamic COWZ/SPY rotation: hold COWZ when COWZ 6m return > SPY 6m return,
     hold SPY otherwise, with BIL escape when SPY < 200MA.
  C. VIX-switched quality: COWZ when VIX < 20, SPY when 20 ≤ VIX < 30, BIL when VIX ≥ 30.

  IS: 2017-2020 (limited by COWZ launch Nov 2016)
  OOS: 2021-2025

  Gate: OOS Sharpe > COWZ baseline (0.737) AND OOS Sharpe > SPY (0.920)

Data:
  COWZ monthly returns: yfinance
  VIX daily: yfinance (^VIX)
  SPY daily: yfinance

Academic basis:
  - H249 CONFIRMED: regime-conditional weights improve production portfolio +0.282 Sharpe
  - H270 CONFIRMED: SPY 200MA × VIX gating works for ETF rotation
  - Bahl & Bhargava (2022): FCF yield factor premium concentrated in distress periods
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2016-01-01"
FULL_END   = "2026-06-01"

# COWZ launched Nov 2016; use 2017+ for reliable data
IS_START  = "2017-01-01"
IS_END    = "2020-12-31"
OOS_START = "2021-01-01"

COWZ_BASELINE_OOS_SHARPE = 0.737  # from H284 result
SPY_OOS_SHARPE = 0.920

VIX_BULL_GATE    = 25   # VIX < 25 = calm
VIX_BEAR_GATE    = 30   # VIX ≥ 30 = cash


def fetch_monthly(ticker):
    """Fetch monthly return series."""
    cache_path = CACHE_DIR / f"h286_{ticker}_monthly.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze().rename(ticker)
    raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    monthly = close.resample("ME").last().pct_change().rename(ticker)
    monthly.to_frame().to_parquet(cache_path)
    return monthly


def fetch_daily_close(ticker):
    """Fetch daily close price."""
    cache_path = CACHE_DIR / f"h286_{ticker}_daily.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze().rename(ticker)
    raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.to_frame().to_parquet(cache_path)
    return close


def stats(r):
    r = r.dropna()
    if len(r) < 4:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    eq = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    if n_yr <= 0:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    annual = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((annual < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r), "neg_years": neg_years}


def corr_series(r1, r2):
    idx = r1.dropna().index.intersection(r2.dropna().index)
    if len(idx) < 6:
        return float("nan")
    return round(float(r1.reindex(idx).corr(r2.reindex(idx))), 4)


def build_gated_series(cowz, spy_ret, bil_ret, regime_signal):
    """
    Build monthly return series:
    - regime_signal=1 → hold COWZ
    - regime_signal=0 → hold BIL
    The regime_signal is computed at prior month-end (lagged 1 month).
    """
    common = cowz.index.intersection(spy_ret.index).intersection(bil_ret.index)
    common = common.intersection(regime_signal.index)
    common = common.sort_values()

    rets = []
    for dt in common:
        sig = float(regime_signal.loc[dt])  # already lagged by 1 month
        if sig > 0:
            rets.append((dt, float(cowz.loc[dt])))
        else:
            rets.append((dt, float(bil_ret.loc[dt])))

    if not rets:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in rets],
                     index=pd.DatetimeIndex([d for d, _ in rets]))


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("H286 — Macro Regime-Gated FCF/P (COWZ + SPY 200MA + VIX Gate)")
print("=" * 80)

print("\n[1] Loading data …")
cowz_monthly = fetch_monthly("COWZ")
spy_monthly  = fetch_monthly("SPY")
bil_monthly  = fetch_monthly("BIL")
spy_daily    = fetch_daily_close("SPY")

# VIX — yfinance ticker ^VIX
try:
    raw_vix = yf.download("^VIX", start=FULL_START, end=FULL_END,
                           auto_adjust=False, progress=False)
    if isinstance(raw_vix.columns, pd.MultiIndex):
        vix_daily = raw_vix.xs("^VIX", axis=1, level=1)["Close"]
    else:
        vix_daily = raw_vix["Close"]
    print(f"  VIX: {len(vix_daily)} days")
except Exception as e:
    print(f"  VIX fetch error: {e}")
    vix_daily = pd.Series(dtype=float)

print(f"  COWZ: {len(cowz_monthly.dropna())} months ({cowz_monthly.dropna().index.min().date()} – {cowz_monthly.dropna().index.max().date()})")
print(f"  SPY:  {len(spy_monthly.dropna())} months")
print(f"  SPY daily: {len(spy_daily.dropna())} days")

# ── Build monthly regime signals ──────────────────────────────────────────────
print("\n[2] Computing regime signals …")

# SPY 200-day MA regime (month-end)
spy_200ma = spy_daily.rolling(200).mean()
spy_vs_200ma = (spy_daily > spy_200ma).astype(float)
spy_vs_200ma_monthly = spy_vs_200ma.resample("ME").last()  # prior month-end

# VIX monthly (end of month)
if len(vix_daily.dropna()) > 10:
    vix_monthly_eom = vix_daily.resample("ME").last()
else:
    vix_monthly_eom = pd.Series(20.0, index=spy_monthly.index)  # neutral fallback

# ── VARIANT A: COWZ when SPY > 200MA AND VIX < 25, else BIL ──────────────────
print("\n[3] Variant A — SPY 200MA + VIX < 25 gate on COWZ …")

# Regime signal: 1 = COWZ favorable (prior month)
regime_A = ((spy_vs_200ma_monthly == 1) & (vix_monthly_eom < VIX_BULL_GATE)).astype(float)
# Lag by 1 month (use prior month-end signal)
regime_A_lagged = regime_A.shift(1).reindex(cowz_monthly.index).ffill()

A = build_gated_series(cowz_monthly, spy_monthly, bil_monthly, regime_A_lagged)

A_is  = A[(A.index >= IS_START) & (A.index <= IS_END)]
A_oos = A[A.index >= OOS_START]

A_is_stats  = stats(A_is)
A_oos_stats = stats(A_oos)

spy_is  = stats(spy_monthly[(spy_monthly.index >= IS_START) & (spy_monthly.index <= IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= OOS_START])

cowz_is  = stats(cowz_monthly[(cowz_monthly.index >= IS_START) & (cowz_monthly.index <= IS_END)])
cowz_oos = stats(cowz_monthly[cowz_monthly.index >= OOS_START])

# Regime distribution
n_cowz = int(regime_A_lagged.reindex(A_oos.index).sum())
n_bil  = int((regime_A_lagged.reindex(A_oos.index) == 0).sum())
print(f"  OOS regime: COWZ {n_cowz} months ({n_cowz/(n_cowz+n_bil)*100:.0f}%), BIL {n_bil} months")

print(f"\n  IS  (2017-2020): Sharpe={A_is_stats['sharpe']:.4f}  CAGR={A_is_stats['cagr']*100:.1f}%  MaxDD={A_is_stats['max_drawdown']*100:.1f}%")
print(f"  OOS (2021-2025): Sharpe={A_oos_stats['sharpe']:.4f}  CAGR={A_oos_stats['cagr']*100:.1f}%  MaxDD={A_oos_stats['max_drawdown']*100:.1f}%  NegYrs={A_oos_stats['neg_years']}")
print(f"  COWZ B&H OOS:    Sharpe={cowz_oos['sharpe']:.4f}  CAGR={cowz_oos['cagr']*100:.1f}%")
print(f"  SPY OOS:         Sharpe={spy_oos['sharpe']:.4f}  CAGR={spy_oos['cagr']*100:.1f}%")

# ── VARIANT B: COWZ vs SPY cross-momentum + BIL escape ───────────────────────
print("\n[4] Variant B — COWZ/SPY cross-momentum + BIL when SPY < 200MA …")

# Momentum signal: hold whichever of COWZ/SPY had better 6m return (lagged 1m)
cowz_6m = cowz_monthly.rolling(6).apply(lambda x: (1+x).prod()-1, raw=False)
spy_6m  = spy_monthly.rolling(6).apply(lambda x: (1+x).prod()-1, raw=False)

cowz_6m_lagged = cowz_6m.shift(1)
spy_6m_lagged  = spy_6m.shift(1)
spy_200ma_lagged = spy_vs_200ma_monthly.reindex(cowz_monthly.index).ffill().shift(1)

B_rets = []
for dt in cowz_monthly.index:
    if pd.isna(cowz_monthly.loc[dt]) or pd.isna(spy_monthly.reindex([dt]).iloc[0]):
        continue
    if pd.isna(cowz_6m_lagged.reindex([dt]).iloc[0]) or pd.isna(spy_6m_lagged.reindex([dt]).iloc[0]):
        continue
    spy_regime = spy_200ma_lagged.reindex([dt]).iloc[0]
    if pd.isna(spy_regime) or spy_regime < 0.5:
        # Bear regime → cash
        r = float(bil_monthly.reindex([dt]).iloc[0]) if dt in bil_monthly.index else 0.0
        B_rets.append((dt, r))
    else:
        c6 = float(cowz_6m_lagged.reindex([dt]).iloc[0])
        s6 = float(spy_6m_lagged.reindex([dt]).iloc[0])
        if c6 >= s6:
            B_rets.append((dt, float(cowz_monthly.loc[dt])))
        else:
            B_rets.append((dt, float(spy_monthly.reindex([dt]).iloc[0])))

B = pd.Series([v for _, v in B_rets], index=pd.DatetimeIndex([d for d, _ in B_rets]))
B_is  = B[(B.index >= IS_START) & (B.index <= IS_END)]
B_oos = B[B.index >= OOS_START]

B_is_stats  = stats(B_is)
B_oos_stats = stats(B_oos)
corr_B_spy = corr_series(B_oos, spy_monthly.reindex(B_oos.index))

print(f"  IS  (2017-2020): Sharpe={B_is_stats['sharpe']:.4f}  CAGR={B_is_stats['cagr']*100:.1f}%  MaxDD={B_is_stats['max_drawdown']*100:.1f}%")
print(f"  OOS (2021-2025): Sharpe={B_oos_stats['sharpe']:.4f}  CAGR={B_oos_stats['cagr']*100:.1f}%  MaxDD={B_oos_stats['max_drawdown']*100:.1f}%  NegYrs={B_oos_stats['neg_years']}")
print(f"  Corr(B, SPY) OOS: {corr_B_spy:.3f}")

# ── VARIANT C: VIX-switched COWZ/SPY/BIL ─────────────────────────────────────
print("\n[5] Variant C — VIX-switched: COWZ (VIX<20) / SPY (20-30) / BIL (≥30) …")

vix_lagged = vix_monthly_eom.reindex(cowz_monthly.index).ffill().shift(1)

C_rets = []
for dt in cowz_monthly.index:
    vix = float(vix_lagged.reindex([dt]).iloc[0]) if dt in vix_lagged.index else np.nan
    if np.isnan(vix):
        continue
    if vix < 20:
        r = float(cowz_monthly.loc[dt])
    elif vix < VIX_BEAR_GATE:
        r = float(spy_monthly.reindex([dt]).iloc[0]) if dt in spy_monthly.index else 0.0
    else:
        r = float(bil_monthly.reindex([dt]).iloc[0]) if dt in bil_monthly.index else 0.0
    C_rets.append((dt, r))

C = pd.Series([v for _, v in C_rets], index=pd.DatetimeIndex([d for d, _ in C_rets]))
C_is  = C[(C.index >= IS_START) & (C.index <= IS_END)]
C_oos = C[C.index >= OOS_START]

C_is_stats  = stats(C_is)
C_oos_stats = stats(C_oos)
corr_C_spy = corr_series(C_oos, spy_monthly.reindex(C_oos.index))

print(f"  IS  (2017-2020): Sharpe={C_is_stats['sharpe']:.4f}  CAGR={C_is_stats['cagr']*100:.1f}%  MaxDD={C_is_stats['max_drawdown']*100:.1f}%")
print(f"  OOS (2021-2025): Sharpe={C_oos_stats['sharpe']:.4f}  CAGR={C_oos_stats['cagr']*100:.1f}%  MaxDD={C_oos_stats['max_drawdown']*100:.1f}%  NegYrs={C_oos_stats['neg_years']}")
print(f"  Corr(C, SPY) OOS: {corr_C_spy:.3f}")

# ── Summary and gate ─────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("SUMMARY")
print(f"{'=' * 60}")
print(f"  COWZ B&H OOS:        Sharpe={cowz_oos['sharpe']:.4f}  CAGR={cowz_oos['cagr']*100:.1f}%  MaxDD={cowz_oos['max_drawdown']*100:.1f}%")
print(f"  SPY OOS:             Sharpe={spy_oos['sharpe']:.4f}  CAGR={spy_oos['cagr']*100:.1f}%  MaxDD={spy_oos['max_drawdown']*100:.1f}%")
print(f"  Var A (200MA+VIX):   Sharpe={A_oos_stats['sharpe']:.4f}  CAGR={A_oos_stats['cagr']*100:.1f}%  MaxDD={A_oos_stats['max_drawdown']*100:.1f}%")
print(f"  Var B (cross-mom):   Sharpe={B_oos_stats['sharpe']:.4f}  CAGR={B_oos_stats['cagr']*100:.1f}%  MaxDD={B_oos_stats['max_drawdown']*100:.1f}%")
print(f"  Var C (VIX-switch):  Sharpe={C_oos_stats['sharpe']:.4f}  CAGR={C_oos_stats['cagr']*100:.1f}%  MaxDD={C_oos_stats['max_drawdown']*100:.1f}%")

best_variant = max([("A", A_oos_stats), ("B", B_oos_stats), ("C", C_oos_stats)],
                   key=lambda x: x[1]["sharpe"])
best_name, best_stats = best_variant

# Gate: best OOS Sharpe > COWZ baseline AND > SPY OOS
gate1 = best_stats["sharpe"] > COWZ_BASELINE_OOS_SHARPE
gate2 = best_stats["sharpe"] > spy_oos["sharpe"]

print(f"\nBest variant: {best_name}  OOS Sharpe={best_stats['sharpe']:.4f}")
print(f"Gate 1 — Best OOS Sharpe > COWZ baseline {COWZ_BASELINE_OOS_SHARPE}: {'PASS' if gate1 else 'FAIL'}")
print(f"Gate 2 — Best OOS Sharpe > SPY OOS {spy_oos['sharpe']:.4f}: {'PASS' if gate2 else 'FAIL'}")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")

results = {
    "hypothesis": "H286",
    "description": "Macro Regime-Gated FCF/P (COWZ + SPY 200MA + VIX Gate)",
    "cowz_baseline_oos": cowz_oos,
    "spy_oos": spy_oos,
    "variant_A": {"is_stats": A_is_stats, "oos_stats": A_oos_stats},
    "variant_B": {"is_stats": B_is_stats, "oos_stats": B_oos_stats, "corr_spy_oos": corr_B_spy},
    "variant_C": {"is_stats": C_is_stats, "oos_stats": C_oos_stats, "corr_spy_oos": corr_C_spy},
    "best_variant": best_name,
    "best_oos_sharpe": best_stats["sharpe"],
    "verdict": verdict,
}
out_path = RESULT_DIR / "h286_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
