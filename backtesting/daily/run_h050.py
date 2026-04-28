"""
H050 — Minimal Two-Component Portfolio: H045 + H037b
=====================================================

Tests whether the two most uncorrelated strategies found (corr ≈ 0.010 on H047)
form a competitive portfolio when blended optimally — without any of the complexity
of H042 (3-way) or H047 (4-way).

Components:
  H045 : Treasury ETF rotation (SHY/IEI/IEF/TLT/TIP/HYG/LQD)
          rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly
          Standalone Sharpe: ~1.505, MaxDD: -6.28%

  H037b: IBS mean-reversion SPY with gap < -0.5% filter, daily
          IBS < 0.20 AND gap >= -0.5% → buy at open; sell when IBS > 0.80 or 5 days
          Standalone Sharpe: ~1.021, MaxDD: -23.05%

Correlation (from H047): 0.010 — nearly perfectly uncorrelated.

Theory: for two uncorrelated strategies with Sharpes S1, S2 and annual vols σ1, σ2,
the optimal Sharpe approaches sqrt(S1² + S2²) ≈ sqrt(1.505² + 1.021²) ≈ 1.818.
This test verifies whether the actual data achieves this theoretical maximum.

Sweep: 100/0 to 0/100 in 5% steps (H045 / H037b weights).

Comparisons:
  H042: 3-way blend (H041a + H026 + H037b = 56/16/28), Sharpe ~1.949
  H047: 4-way blend, Sharpe ~1.984

Period: 2008-01 to 2026-04

Outputs:
  /workspace/agent/backtesting/results/h050_results.json
  /workspace/agent/backtesting/daily/run_h050.py  (this file)
"""

import json
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2000-01-01"   # data download start (warmup for 12m momentum)
FULL_END     = "2026-04-27"
WINDOW_START = "2008-01-01"   # common period start (IEI limited; 12m warmup → ~2008-07 effective)
WINDOW_END   = "2026-04-27"

# ── H045 params ───────────────────────────────────────────────────────────────
TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
TOP_N_H45 = 2

# ── H037b params ─────────────────────────────────────────────────────────────
IBS_BUY       = 0.20
IBS_SELL      = 0.80
MAX_HOLD      = 5
GAP_FILTER_B  = -0.005   # skip entry if gap < -0.5%


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h050_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        print(f"  Loaded {len(tickers)} tickers from cache ({tag})")
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    """Return SPY OHLC; reuse prior run caches when available."""
    for tag in ["h042", "h047", "h031", "h031b"]:
        for variant in [f"{tag}_spy_ohlc_{start}_{end}.parquet",
                        f"h031_spy_ohlc_{start}_{end}.parquet"]:
            cp = CACHE_DIR / variant
            if cp.exists():
                df = pd.read_parquet(cp)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df = df.rename(columns=str.lower) if not all(
                    c in df.columns for c in ["open", "high", "low", "close"]) else df
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
                    return df
    # download fresh
    cp = CACHE_DIR / f"h050_spy_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print("  Downloading SPY OHLC …")
    raw = yf.download(["SPY"], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs("SPY", axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets: pd.Series, label: str = "") -> dict:
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"error": "insufficient data", "label": label}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
        "start":        str(monthly_rets.index[0].date()) if len(monthly_rets) > 0 else "",
        "end":          str(monthly_rets.index[-1].date()) if len(monthly_rets) > 0 else "",
    }


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Equity curve builders (rebuilt from scratch for H050)
# ─────────────────────────────────────────────────────────────────────────────

def h045_equity_curve(prices: pd.DataFrame) -> pd.Series:
    """
    H045: Treasury ETF rotation.
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly rebalance.
    """
    available = [t for t in TREASURY_ETFS if t in prices.columns]
    if len(available) < TOP_N_H45:
        print(f"ERROR H045: only {len(available)} tickers available")
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H45
    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H45:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H45).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def h037b_equity_curve(ohlc: pd.DataFrame) -> pd.Series:
    """
    H037b: IBS mean-reversion SPY with gap < -0.5% entry filter.
    Entry: IBS < 0.20 (prior day) AND gap >= -0.5% (today open vs prior close).
    Exit:  IBS > 0.80 (today) OR held >= 5 days.
    """
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    gap     = (df["open"] - prev_cl) / prev_cl

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []

    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])

        ret_oc = (c / o - 1)      if o > 0      else 0.0
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0

        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER_B:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        series.append((date, equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio blend helpers
# ─────────────────────────────────────────────────────────────────────────────

def blend_stats_2way(r45: pd.Series, r37b: pd.Series, w45: float, w37b: float,
                     label: str = "") -> dict:
    """Compute 2-way blend statistics on the common monthly index."""
    common = r45.index.intersection(r37b.index)
    if len(common) < 12:
        return {"error": "insufficient overlap", "w_h045": w45, "w_h037b": w37b}

    a45  = r45.loc[common].values
    a37b = r37b.loc[common].values
    n_years = len(common) / 12.0

    rb     = w45 * a45 + w37b * a37b
    cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
    vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    eq     = np.cumprod(1 + rb)
    roll_mx = np.maximum.accumulate(eq)
    max_dd  = float(np.min(eq / roll_mx - 1))
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0

    return {
        "label":        label if label else f"H045={w45:.0%} / H037b={w37b:.0%}",
        "w_h045":       round(w45,   4),
        "w_h037b":      round(w37b,  4),
        "cagr":         round(cagr,   4),
        "sharpe":       round(sharpe,  4),
        "max_drawdown": round(max_dd,  4),
        "calmar":       round(calmar,  4),
        "ann_vol":      round(vol,     4),
        "n_months":     len(common),
    }


def theoretical_max_sharpe(s1: float, s2: float, corr: float,
                            vol1: float, vol2: float) -> dict:
    """
    For a 2-asset portfolio with monthly return correlation 'corr',
    compute the theoretical maximum Sharpe ratio and the optimal weight.
    Uses the classic mean-variance optimal weight formula.

    When corr = 0:
      max_sharpe ≈ sqrt(S1² + S2²) only if returns per unit vol are equal.
      In general: max_sharpe = sqrt(S1² + S2²) * factor
    """
    # Theoretical upper bound (zero correlation, no CAGR/vol mismatch):
    theoretical_upper = np.sqrt(s1**2 + s2**2)

    # More precise: using actual Sharpes as proxies for mean/vol,
    # optimal blend on Sharpe-per-unit-vol basis
    # mu_i = s_i * vol_i  (annualised)
    # optimal weight in terms of Sharpe maximisation:
    # w1* = (S1*σ2² - S2*σ1*σ2*ρ) / (S1*σ2² + S2*σ1² - (S1+S2)*σ1*σ2*ρ)  [approximation]
    # This uses S_i as excess return per unit of vol

    # Actual portfolio Sharpe at each blend:
    best_sharpe = -np.inf
    best_w1 = 0.5
    for w1 in np.linspace(0, 1, 1001):
        w2 = 1.0 - w1
        port_var = (w1*vol1)**2 + (w2*vol2)**2 + 2*w1*w2*vol1*vol2*corr
        port_vol = np.sqrt(port_var)
        port_return = w1 * s1 * vol1 + w2 * s2 * vol2   # mu_i = S_i * sigma_i
        ps = port_return / port_vol if port_vol > 0 else 0.0
        if ps > best_sharpe:
            best_sharpe = ps
            best_w1 = w1

    return {
        "theoretical_uncorrelated_upper": round(theoretical_upper, 4),
        "mv_optimal_sharpe":              round(best_sharpe, 4),
        "mv_optimal_w_h045":              round(best_w1, 4),
        "mv_optimal_w_h037b":             round(1 - best_w1, 4),
        "note": (
            "theoretical_uncorrelated_upper = sqrt(S1^2+S2^2) = uncorrelated limit. "
            "mv_optimal_sharpe uses mean=Sharpe*vol, finds max Sharpe across blends."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H050 — Minimal Two-Component Portfolio: H045 + H037b")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    prices_tr = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h050_treasury")
    spy_ohlc  = fetch_spy_ohlc(FULL_START, FULL_END)

    print(f"   Treasury ETFs available: {sorted(prices_tr.columns.tolist())}")
    print(f"   SPY OHLC: {spy_ohlc.index[0].date()} → {spy_ohlc.index[-1].date()} ({len(spy_ohlc)} rows)")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building H045 equity curve (Treasury ETF rotation) …")
    eq_h045 = h045_equity_curve(prices_tr)

    print("[3] Building H037b equity curve (gap-filtered IBS) …")
    eq_h037b = h037b_equity_curve(spy_ohlc)

    for name, eq in [("H045", eq_h045), ("H037b", eq_h037b)]:
        if eq.empty:
            print(f"ERROR: {name} equity curve is empty. Aborting.")
            return {}
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} days)")

    # ── 3. Monthly returns ─────────────────────────────────────────────────────
    print("\n[4] Converting to monthly returns …")
    r_h045_all  = to_monthly_returns(eq_h045)
    r_h037b_all = to_monthly_returns(eq_h037b)

    # Clip to common window 2008-01 → 2026-04
    window_ts = pd.Timestamp(WINDOW_START)
    window_end_ts = pd.Timestamp(WINDOW_END)

    common_idx = (
        r_h045_all.index
        .intersection(r_h037b_all.index)
    )
    common_idx = common_idx[(common_idx >= window_ts) & (common_idx <= window_end_ts)]

    r_h045  = r_h045_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")

    # ── 4. Correlation ────────────────────────────────────────────────────────
    corr = float(r_h045.corr(r_h037b))
    print(f"\n[5] H045 / H037b monthly return correlation: {corr:.4f}")

    # ── 5. Standalone stats on common window ─────────────────────────────────
    print("\n[6] Standalone statistics on common window …")
    s_h045  = stats_from_monthly_returns(r_h045,  "H045  standalone")
    s_h037b = stats_from_monthly_returns(r_h037b, "H037b standalone")

    print(f"   H045  : CAGR {s_h045['cagr']:.2%}  Sharpe {s_h045['sharpe']:.4f}  MaxDD {s_h045['max_drawdown']:.2%}  AnnVol {s_h045['ann_vol']:.2%}")
    print(f"   H037b : CAGR {s_h037b['cagr']:.2%}  Sharpe {s_h037b['sharpe']:.4f}  MaxDD {s_h037b['max_drawdown']:.2%}  AnnVol {s_h037b['ann_vol']:.2%}")

    # ── 6. Theoretical max Sharpe ──────────────────────────────────────────────
    print("\n[7] Theoretical maximum Sharpe analysis …")
    theory = theoretical_max_sharpe(
        s1=s_h045["sharpe"],  s2=s_h037b["sharpe"],
        corr=corr,
        vol1=s_h045["ann_vol"], vol2=s_h037b["ann_vol"]
    )
    print(f"   Theoretical uncorrelated upper bound: sqrt({s_h045['sharpe']:.3f}² + {s_h037b['sharpe']:.3f}²) = {theory['theoretical_uncorrelated_upper']:.4f}")
    print(f"   MV-optimal Sharpe (using actual vols): {theory['mv_optimal_sharpe']:.4f}")
    print(f"   MV-optimal weight: H045={theory['mv_optimal_w_h045']:.1%}  H037b={theory['mv_optimal_w_h037b']:.1%}")

    # ── 7. Blend sweep: 100/0 → 0/100 in 5% steps ────────────────────────────
    print("\n[8] Sweeping blend weights (100/0 → 0/100 in 5% steps) …")
    blend_steps = np.arange(0, 1.01, 0.05)
    blend_results = []

    for w45 in blend_steps:
        w37b = 1.0 - w45
        row = blend_stats_2way(r_h045, r_h037b, float(w45), float(w37b))
        blend_results.append(row)

    # Print frontier
    print(f"\n  {'H045':>6}  {'H037b':>6}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*66}")
    for row in blend_results:
        if "error" in row:
            continue
        print(f"  {row['w_h045']:>6.0%}  {row['w_h037b']:>6.0%}  "
              f"{row['cagr']:>8.2%}  {row['sharpe']:>8.4f}  "
              f"{row['max_drawdown']:>8.2%}  {row['ann_vol']:>8.2%}  {row['calmar']:>8.3f}")

    # ── 8. Find optimal blends ─────────────────────────────────────────────────
    valid_blends = [r for r in blend_results if "error" not in r]

    max_sharpe_row = max(valid_blends, key=lambda r: r["sharpe"])
    min_maxdd_row  = max(valid_blends, key=lambda r: r["max_drawdown"])  # least negative
    max_calmar_row = max(valid_blends, key=lambda r: r["calmar"])

    print(f"\n[9] Optimal blends:")
    print(f"   Max Sharpe : H045={max_sharpe_row['w_h045']:.0%}  H037b={max_sharpe_row['w_h037b']:.0%} → "
          f"Sharpe={max_sharpe_row['sharpe']:.4f}  CAGR={max_sharpe_row['cagr']:.2%}  MaxDD={max_sharpe_row['max_drawdown']:.2%}")
    print(f"   Min MaxDD  : H045={min_maxdd_row['w_h045']:.0%}  H037b={min_maxdd_row['w_h037b']:.0%} → "
          f"Sharpe={min_maxdd_row['sharpe']:.4f}  CAGR={min_maxdd_row['cagr']:.2%}  MaxDD={min_maxdd_row['max_drawdown']:.2%}")
    print(f"   Max Calmar : H045={max_calmar_row['w_h045']:.0%}  H037b={max_calmar_row['w_h037b']:.0%} → "
          f"Sharpe={max_calmar_row['sharpe']:.4f}  CAGR={max_calmar_row['cagr']:.2%}  MaxDD={max_calmar_row['max_drawdown']:.2%}")

    # ── 9. Fine-grained optimum via 1% steps ─────────────────────────────────
    print("\n[10] Fine-grained optimisation (1% steps) …")
    fine_steps = np.arange(0, 1.001, 0.01)
    fine_results = []
    for w45 in fine_steps:
        w37b = 1.0 - w45
        row = blend_stats_2way(r_h045, r_h037b, float(w45), float(w37b))
        fine_results.append(row)

    valid_fine = [r for r in fine_results if "error" not in r]
    fine_max_sharpe = max(valid_fine, key=lambda r: r["sharpe"])
    fine_min_maxdd  = max(valid_fine, key=lambda r: r["max_drawdown"])
    fine_max_calmar = max(valid_fine, key=lambda r: r["calmar"])

    print(f"   Fine max Sharpe : H045={fine_max_sharpe['w_h045']:.0%}  H037b={fine_max_sharpe['w_h037b']:.0%} → "
          f"Sharpe={fine_max_sharpe['sharpe']:.4f}  CAGR={fine_max_sharpe['cagr']:.2%}  MaxDD={fine_max_sharpe['max_drawdown']:.2%}")
    print(f"   Fine min MaxDD  : H045={fine_min_maxdd['w_h045']:.0%}  H037b={fine_min_maxdd['w_h037b']:.0%} → "
          f"Sharpe={fine_min_maxdd['sharpe']:.4f}  CAGR={fine_min_maxdd['cagr']:.2%}  MaxDD={fine_min_maxdd['max_drawdown']:.2%}")
    print(f"   Fine max Calmar : H045={fine_max_calmar['w_h045']:.0%}  H037b={fine_max_calmar['w_h037b']:.0%} → "
          f"Sharpe={fine_max_calmar['sharpe']:.4f}  CAGR={fine_max_calmar['cagr']:.2%}  MaxDD={fine_max_calmar['max_drawdown']:.2%}")

    # ── 10. Theoretical vs actual comparison ──────────────────────────────────
    actual_max_sharpe = fine_max_sharpe["sharpe"]
    theoretical_upper = theory["theoretical_uncorrelated_upper"]
    achievement_pct   = 100.0 * actual_max_sharpe / theoretical_upper

    print(f"\n[11] Theoretical vs actual:")
    print(f"   sqrt(S1² + S2²)  = {theoretical_upper:.4f}   (theoretical upper bound)")
    print(f"   MV-optimal       = {theory['mv_optimal_sharpe']:.4f}  (mean-variance formula)")
    print(f"   Actual max Sharpe= {actual_max_sharpe:.4f}   (empirical optimum)")
    print(f"   Achievement      = {achievement_pct:.1f}% of theoretical upper")

    # ── 11. H050 vs H042 / H047 comparison ───────────────────────────────────
    # Load from actual result files for accuracy
    h042_sharpe_ref = 1.8674
    h047_sharpe_ref = 2.1128
    try:
        _h47 = json.loads((RESULT_DIR / "h047_results.json").read_text())
        h042_sharpe_ref = _h47["h042_baseline"]["stats"]["sharpe"]
        h047_sharpe_ref = _h47["best_4way_sharpe"]
    except Exception:
        pass

    H042_SHARPE = h042_sharpe_ref
    H047_SHARPE = h047_sharpe_ref
    H042_CAGR   = 0.147
    H047_CAGR   = 0.0823

    print(f"\n[12] Comparison to H042 / H047:")
    print(f"   H050 max-Sharpe blend : {fine_max_sharpe['sharpe']:.4f}  (H045={fine_max_sharpe['w_h045']:.0%} / H037b={fine_max_sharpe['w_h037b']:.0%})")
    print(f"   H042 (3-way)          : {H042_SHARPE:.4f}")
    print(f"   H047 (4-way)          : {H047_SHARPE:.4f}")
    sharpe_gap_vs_h042 = fine_max_sharpe["sharpe"] - H042_SHARPE
    sharpe_gap_vs_h047 = fine_max_sharpe["sharpe"] - H047_SHARPE
    print(f"   H050 vs H042 gap      : {sharpe_gap_vs_h042:+.4f}")
    print(f"   H050 vs H047 gap      : {sharpe_gap_vs_h047:+.4f}")

    # Is H050 competitive? (within 0.1 Sharpe of H042/H047)
    if fine_max_sharpe["sharpe"] >= H042_SHARPE + 0.02:
        verdict = "H050 EXCEEDS H042 — 2-component simplicity outperforms 3-way complexity (extraordinary)"
    elif fine_max_sharpe["sharpe"] >= H042_SHARPE - 0.05:
        verdict = "H050 is COMPETITIVE with H042 — 2-component simplicity matches 3-way complexity"
    elif fine_max_sharpe["sharpe"] >= H042_SHARPE - 0.15:
        verdict = "H050 is NEAR-COMPETITIVE with H042 — small Sharpe gap, much simpler construction"
    elif fine_max_sharpe["sharpe"] >= H042_SHARPE - 0.30:
        verdict = "H050 is MODERATELY BEHIND H042 — multi-component diversity pays off"
    else:
        verdict = "H050 UNDERPERFORMS H042 — three diversified strategies clearly dominate two"

    print(f"\n  Verdict: {verdict}")

    # ── 12. Summary table ─────────────────────────────────────────────────────
    print(f"\n{'=' * 95}")
    print("  H050 EFFICIENT FRONTIER — H045 / H037b blend sweep (2008-01 → 2026-04)")
    print(f"  Correlation: {corr:.4f}  |  H045 standalone Sharpe: {s_h045['sharpe']:.4f}  |  H037b standalone Sharpe: {s_h037b['sharpe']:.4f}")
    print(f"{'=' * 95}")
    print(f"  {'H045':>6}  {'H037b':>6}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*68}")
    for row in blend_results:
        if "error" in row:
            continue
        marker = ""
        if abs(row["w_h045"] - fine_max_sharpe["w_h045"]) < 0.001:
            marker = " ← max Sharpe"
        elif abs(row["w_h045"] - fine_min_maxdd["w_h045"]) < 0.051:
            marker = " ← min MaxDD"
        print(f"  {row['w_h045']:>6.0%}  {row['w_h037b']:>6.0%}  "
              f"{row['cagr']:>8.2%}  {row['sharpe']:>8.4f}  "
              f"{row['max_drawdown']:>8.2%}  {row['ann_vol']:>8.2%}  {row['calmar']:>8.3f}{marker}")

    # ── 13. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H050 — Minimal Two-Component Portfolio: H045 + H037b",
        "description": (
            "Blends the two most uncorrelated strategies found (H045 Treasury ETF rotation + "
            "H037b IBS mean-reversion). Tests whether near-zero correlation enables a simple "
            "2-component portfolio to compete with complex multi-component blends."
        ),
        "components": {
            "h045": {
                "name":      "Treasury ETF Rotation",
                "universe":  TREASURY_ETFS,
                "signal":    "rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50",
                "rebalance": "monthly",
            },
            "h037b": {
                "name":      "IBS Mean-Reversion (gap-filtered)",
                "signal":    "IBS < 0.20 AND gap >= -0.5% → buy SPY at open; sell when IBS > 0.80 or held >= 5 days",
                "rebalance": "daily",
                "gap_filter": GAP_FILTER_B,
            },
        },
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 2),
        },
        "correlation": {
            "h045_h037b": round(corr, 4),
            "source": "Rebuilt from scratch on 2008-01 to 2026-04 common window",
            "note":   "Near-zero correlation is the primary motivation for this blend",
        },
        "standalone_stats": {
            "h045":  s_h045,
            "h037b": s_h037b,
        },
        "theoretical_analysis": theory,
        "blend_frontier_5pct_steps": blend_results,
        "optimal_blends": {
            "max_sharpe":  max_sharpe_row,
            "min_max_dd":  min_maxdd_row,
            "max_calmar":  max_calmar_row,
        },
        "fine_optimal_blends_1pct": {
            "max_sharpe":  fine_max_sharpe,
            "min_max_dd":  fine_min_maxdd,
            "max_calmar":  fine_max_calmar,
        },
        "vs_theoretical": {
            "theoretical_upper":     theory["theoretical_uncorrelated_upper"],
            "mv_optimal":            theory["mv_optimal_sharpe"],
            "actual_max_sharpe":     actual_max_sharpe,
            "achievement_pct":       round(achievement_pct, 1),
            "gap_from_theoretical":  round(theoretical_upper - actual_max_sharpe, 4),
        },
        "comparison_to_complex_blends": {
            "H050_max_sharpe_blend": fine_max_sharpe["sharpe"],
            "H042_sharpe":           H042_SHARPE,
            "H047_sharpe":           H047_SHARPE,
            "gap_vs_h042":           round(sharpe_gap_vs_h042, 4),
            "gap_vs_h047":           round(sharpe_gap_vs_h047, 4),
            "note": "H042 and H047 Sharpe values from their respective runs on same common period",
        },
        "verdict": verdict,
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h050_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
