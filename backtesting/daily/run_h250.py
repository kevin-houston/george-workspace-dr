"""
H250 — Continuous Macro-Regime Score for Production Portfolio
=============================================================
Source: arXiv:2605.20636 (Xiong, May 2026)
  'Continuous Timing Signals for Growth-Defensive Style Allocation'
  Replaces discrete regime bins with tanh-mapped continuous score.
  OOS Sharpe 1.01, CAGR 19.24%, MaxDD -31.63% (growth/defensive ETF, 2017-2026).

H249 baseline: discrete 4-state regime (bull/bear × calm/volatile) on production blend.
H250 tests: replace 4-state with continuous score; expect smoother transitions,
  lower turnover, and potentially improved OOS Sharpe/MaxDD.

Continuous score construction (Xiong 2026 adaptation for our pipeline):
  1. Rate relief      = -DGS10.diff(63)  (negative = rates rising = defensive signal)
  2. SPY drawdown     = (SPY / SPY.rolling(252).max() - 1)  (negative in bear market)
  3. VIX stress       = (25 - VIX) / 10   (negative when VIX > 25)
  4. Combined score   = mean(normalize(components)) -> tanh -> [-1, 1]

Weight mapping (tanh output s in [-1, 1]):
  H041a weight = 0.22 + s * 0.08   (range: 0.14 to 0.30)
  H026  weight = 0.27 + s * 0.08   (range: 0.19 to 0.35)
  H045  weight = 0.21 - s * 0.12   (range: 0.09 to 0.33)
  IBS   weight = 0.30 - s * 0.04   (range: 0.26 to 0.34)
  (weights renormalized to sum to 1.0 after rate-hike modifier if needed)

Rate-hike modifier (same as H249): if DGS10 rising >50bps in prior quarter,
  shift +8% from H045 to IBS (tech ETFs benefit from rate-driven growth momentum).

IS: 2008-2017  OOS: 2018-2026 (same as H249 for direct comparison)
Confirm: OOS Sharpe >= H249_static + 0.1  OR  MaxDD improvement >= 2%
         where H249_static is the static blend benchmark in run_h249.py

Sub-strategy setup is identical to H249 (H041a/H026/H045/IBS).
Reuse H249 cache files where possible.
"""

import warnings; warnings.filterwarnings("ignore")
import json
import os
import numpy as np
import pandas as pd
import yfinance as yf
import requests
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

FULL_START = "2005-01-01"   # warmup
FULL_END   = "2026-05-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# Sub-strategy universes (identical to H249)
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H026_SECTORS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLY","XLP","XLC","XLRE"]
H045_BONDS   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD"]
IBS_TICKERS  = ["XLK","SMH","IGV"]
BIL          = "BIL"

IBS_WEIGHTS = {"XLK": 20/30, "SMH": 8/30, "IGV": 2/30}
STATIC_WEIGHTS = {"H041a": 0.22, "H026": 0.27, "H045": 0.21, "IBS": 0.30}

# H249 static OOS Sharpe from results file
H249_STATIC_OOS_SHARPE = 0.8458  # from h249_results.json
H249_STATIC_OOS_MAXDD  = -0.2154


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers (reuse H249 caches)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, tag="all"):
    all_tickers = sorted(set(tickers))
    cache_path = CACHE_DIR / f"h249_{tag}_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        missing = [t for t in all_tickers if t not in df.columns]
        if not missing:
            return df
    print(f"  Downloading {len(all_tickers)} tickers [{tag}]...")
    raw = yf.download(all_tickers, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cache_path)
    return closes


def fetch_ohlcv(tickers, tag="ibs"):
    cache_path = CACHE_DIR / f"h249_ohlcv_{tag}_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    print(f"  Downloading OHLCV for {tickers}...")
    raw = yf.download(sorted(tickers), start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        data = {}
        for metric in ["Open","High","Low","Close"]:
            for t in tickers:
                if (metric, t) in raw.columns:
                    data[f"{t}_{metric}"] = raw[(metric, t)]
        df = pd.DataFrame(data)
    else:
        df = raw
    df = df.dropna(how="all")
    df.to_parquet(cache_path)
    return df


def fetch_fred(series_id):
    cache_path = CACHE_DIR / f"h249_fred_{series_id}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df["value"]
    print(f"  Fetching FRED {series_id}...")
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
        f"&observation_start=2004-01-01&limit=10000"
    )
    try:
        r = requests.get(url, timeout=30)
        data = r.json()
        obs = data.get("observations", [])
        records = [(o["date"], o["value"]) for o in obs if o["value"] != "."]
        df = pd.DataFrame(records, columns=["date", "value"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna()
        df.to_parquet(cache_path)
        return df["value"]
    except Exception as e:
        print(f"  FRED fetch failed for {series_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Sub-strategy return series (identical to H249)
# ─────────────────────────────────────────────────────────────────────────────

def compute_momentum_strategy(prices_monthly, top_n=1):
    ret_m = prices_monthly.pct_change()
    mom12 = prices_monthly.pct_change(12)
    vol6  = ret_m.rolling(6).std()

    port_returns = []
    dates = prices_monthly.index
    for i in range(13, len(dates)):
        sig_date  = dates[i-1]
        hold_date = dates[i]
        m12 = mom12.loc[sig_date]
        v6  = vol6.loc[sig_date]
        valid = m12.notna() & v6.notna() & (v6 > 0)
        if valid.sum() < max(top_n, 2):
            port_returns.append((hold_date, 0.0))
            continue
        rank_mom = m12[valid].rank(ascending=False)
        rank_vol = (1.0 / v6[valid]).rank(ascending=False)
        composite = rank_mom + rank_vol
        selected = composite.nlargest(top_n).index.tolist()
        if not selected:
            port_returns.append((hold_date, 0.0))
            continue
        port_ret = ret_m.loc[hold_date, selected].mean()
        port_returns.append((hold_date, float(port_ret) if not np.isnan(port_ret) else 0.0))

    if not port_returns:
        return pd.Series(dtype=float)
    dates_out, rets_out = zip(*port_returns)
    return pd.Series(rets_out, index=pd.DatetimeIndex(dates_out))


def compute_ibs_strategy(ohlcv_df, tickers, weights_dict):
    daily_rets = {}
    for t in tickers:
        close = ohlcv_df.get(f"{t}_Close")
        high  = ohlcv_df.get(f"{t}_High")
        low   = ohlcv_df.get(f"{t}_Low")
        if close is None or high is None or low is None:
            continue
        ibs   = (close - low) / (high - low + 1e-10)
        ret_d = close.pct_change()
        in_pos, days_held, strat_rets = False, 0, []
        for j in range(1, len(close)):
            prev_ibs = ibs.iloc[j-1]
            if not in_pos:
                if prev_ibs < 0.25:
                    in_pos, days_held = True, 0
            if in_pos:
                strat_rets.append(ret_d.iloc[j])
                days_held += 1
                if ibs.iloc[j] > 0.75 or days_held >= 5:
                    in_pos = False
            else:
                strat_rets.append(0.0)
        daily_rets[t] = pd.Series(strat_rets, index=close.index[1:])

    if not daily_rets:
        return pd.Series(dtype=float)
    df = pd.DataFrame(daily_rets)
    wts = pd.Series({t: weights_dict.get(t, 0.0) for t in df.columns})
    wts = wts / wts.sum()
    return (df * wts).sum(axis=1)


# ─────────────────────────────────────────────────────────────────────────────
# H250 continuous score
# ─────────────────────────────────────────────────────────────────────────────

def compute_continuous_score(spy_daily, vix_daily, dgs10_daily):
    """
    Compute the continuous tanh regime score on daily frequency.
    Returns a daily Series of score values in [-1, 1].

    Components:
      rate_relief = -DGS10.diff(63)
      spy_dd      = SPY / SPY.rolling(252).max() - 1
      vix_stress  = (25 - VIX) / 10

    Each normalized to zero-mean unit-std (expanding window from IS period),
    then averaged and tanh-mapped.
    """
    # 1. Rate relief: 63-day change in 10Y yield (negative = rates rising)
    dgs10 = dgs10_daily.reindex(spy_daily.index, method="ffill")
    rate_relief = -dgs10.diff(63)

    # 2. SPY drawdown from 252d high
    spy_dd = spy_daily / spy_daily.rolling(252).max() - 1

    # 3. VIX stress: positive when VIX < 25
    vix = vix_daily.reindex(spy_daily.index, method="ffill")
    vix_stress = (25 - vix) / 10

    # Stack into DataFrame
    signals = pd.DataFrame({
        "rate_relief": rate_relief,
        "spy_dd":      spy_dd,
        "vix_stress":  vix_stress,
    })

    # Normalize each component using IS-period (through 2017) rolling stats
    # to avoid lookahead: use expanding window capped at IS end
    is_end_dt = pd.Timestamp(IS_END)

    normalized = pd.DataFrame(index=signals.index)
    for col in signals.columns:
        s = signals[col].dropna()
        # Compute expanding mean/std using only IS data, then apply to full series
        is_s = s[s.index <= is_end_dt]
        is_mean = is_s.expanding().mean()
        is_std  = is_s.expanding().std()
        # For OOS, use final IS mean/std (frozen at IS end)
        final_mean = float(is_mean.iloc[-1]) if len(is_mean) > 0 else 0.0
        final_std  = float(is_std.iloc[-1])  if len(is_std) > 0 and is_std.iloc[-1] > 0 else 1.0

        # Apply: IS uses expanding, OOS uses frozen IS stats
        norm_vals = pd.Series(index=s.index, dtype=float)
        is_mask = s.index <= is_end_dt
        if is_mask.sum() > 0:
            is_norm = (s[is_mask] - is_mean) / is_std.replace(0, 1)
            norm_vals[is_mask] = is_norm
        oos_mask = s.index > is_end_dt
        if oos_mask.sum() > 0:
            norm_vals[oos_mask] = (s[oos_mask] - final_mean) / final_std
        normalized[col] = norm_vals

    # Combined score: mean of normalized components
    combined = normalized.mean(axis=1)

    # Tanh mapping to [-1, 1]
    score = np.tanh(combined)
    return score


def score_to_weights(s, rate_hike=False):
    """
    Map scalar score s in [-1, 1] to portfolio weights.
    Returns dict with H041a, H026, H045, IBS.
    """
    wts = {
        "H041a": 0.22 + s * 0.08,
        "H026":  0.27 + s * 0.08,
        "H045":  0.21 - s * 0.12,
        "IBS":   0.30 - s * 0.04,
    }
    # Clip to [0, 1]
    wts = {k: float(np.clip(v, 0.0, 1.0)) for k, v in wts.items()}

    # Rate-hike modifier: shift +8% from H045 to IBS
    if rate_hike:
        shift = 0.08
        wts["H045"] = max(0.0, wts["H045"] - shift)
        wts["IBS"]  = min(1.0, wts["IBS"]  + shift)

    # Renormalize
    total = sum(wts.values())
    if total > 0:
        wts = {k: v / total for k, v in wts.items()}
    return wts


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio statistics
# ─────────────────────────────────────────────────────────────────────────────

def calc_stats(returns_series, label=""):
    r = returns_series.dropna()
    if len(r) < 12:
        return {}
    eq = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr    = eq.iloc[-1] ** (1/n_years) - 1
    vol     = r.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    neg_yrs  = (r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    return {
        "label":    label,
        "n_months": len(r),
        "cagr":     round(float(cagr), 4),
        "sharpe":   round(float(sharpe), 4),
        "max_dd":   round(float(max_dd), 4),
        "ann_vol":  round(float(vol), 4),
        "neg_yrs":  int(neg_yrs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("H250 — Continuous Macro-Regime Score")
    print("=" * 60)

    # ── 1. Load data (reuse H249 caches) ─────────────────────────────────────
    all_tickers = sorted(set(
        H041A_ASSETS + H026_SECTORS + H045_BONDS + list(IBS_WEIGHTS.keys()) + [BIL, "SPY"]
    ))
    print(f"\n[1] Loading close prices ({len(all_tickers)} tickers)...")
    closes = fetch_close(all_tickers, tag="all")
    print(f"    Range: {closes.index[0].date()} to {closes.index[-1].date()}")

    print("[1b] Loading OHLCV for IBS...")
    ohlcv = fetch_ohlcv(list(IBS_WEIGHTS.keys()), tag="ibs")

    print("[1c] Loading FRED VIX...")
    vix = fetch_fred("VIXCLS")

    print("[1d] Loading FRED DGS10...")
    dgs10 = fetch_fred("DGS10")

    # ── 2. Monthly close prices ───────────────────────────────────────────────
    print("\n[2] Resampling to monthly...")
    closes_m = closes.resample("ME").last()

    # ── 3. Sub-strategy monthly returns ──────────────────────────────────────
    print("\n[3] Computing sub-strategy monthly returns...")

    h041a_cols = [c for c in H041A_ASSETS if c in closes_m.columns]
    r_h041a = compute_momentum_strategy(closes_m[h041a_cols], top_n=1)
    print(f"    H041a: {len(r_h041a)} months, mean={r_h041a.mean():.4f}")

    h026_cols = [c for c in H026_SECTORS if c in closes_m.columns]
    r_h026 = compute_momentum_strategy(closes_m[h026_cols], top_n=1)
    print(f"    H026:  {len(r_h026)} months, mean={r_h026.mean():.4f}")

    h045_cols = [c for c in H045_BONDS if c in closes_m.columns]
    r_h045 = compute_momentum_strategy(closes_m[h045_cols], top_n=2)
    print(f"    H045:  {len(r_h045)} months, mean={r_h045.mean():.4f}")

    r_ibs_daily   = compute_ibs_strategy(ohlcv, list(IBS_WEIGHTS.keys()), IBS_WEIGHTS)
    r_ibs_monthly = r_ibs_daily.resample("ME").apply(lambda x: (1+x).prod()-1)
    print(f"    IBS:   {len(r_ibs_monthly)} months, mean={r_ibs_monthly.mean():.4f}")

    # ── 4. Continuous regime score (daily, then sample to month-end) ──────────
    print("\n[4] Computing continuous regime score...")
    spy_daily = closes["SPY"].dropna()
    score_daily = compute_continuous_score(spy_daily, vix, dgs10)
    # Monthly score: use last trading day of each month (lagged signal)
    score_m = score_daily.resample("ME").last()
    print(f"    Score: {len(score_m)} months, mean={score_m.mean():.4f}, "
          f"min={score_m.min():.4f}, max={score_m.max():.4f}")

    # 10Y yield rate-hike modifier (3-month change > 50bps)
    if dgs10 is not None:
        dgs10_m = dgs10.resample("ME").last()
        rate_hike = (dgs10_m.diff(3) > 0.5)
    else:
        rate_hike = pd.Series(False, index=score_m.index)

    # ── 5. Align series ───────────────────────────────────────────────────────
    print("\n[5] Aligning return series...")
    start = pd.Timestamp("2008-01-01")
    end   = pd.Timestamp("2026-05-31")

    def align(s):
        return s[(s.index >= start) & (s.index <= end)]

    r_h041a  = align(r_h041a)
    r_h026   = align(r_h026)
    r_h045   = align(r_h045)
    r_ibs_m  = align(r_ibs_monthly)
    score_a  = align(score_m)
    rh_a     = align(rate_hike)

    common_idx = (r_h041a.index
                  .intersection(r_h026.index)
                  .intersection(r_h045.index)
                  .intersection(r_ibs_m.index))
    common_idx = common_idx[(common_idx >= start) & (common_idx <= end)]
    print(f"    Common months: {len(common_idx)}")

    r_h041a = r_h041a.reindex(common_idx)
    r_h026  = r_h026.reindex(common_idx)
    r_h045  = r_h045.reindex(common_idx)
    r_ibs_m = r_ibs_m.reindex(common_idx)
    score_a = score_a.reindex(common_idx, method="ffill").fillna(0.0)
    rh_a    = rh_a.reindex(common_idx, method="ffill").fillna(False)

    ret_components = pd.DataFrame({
        "H041a": r_h041a,
        "H026":  r_h026,
        "H045":  r_h045,
        "IBS":   r_ibs_m,
    }).fillna(0.0)

    # ── 6. Build portfolios ───────────────────────────────────────────────────
    print("\n[6] Building static and H250 continuous portfolios...")

    # Static portfolio (H249 static baseline)
    static_w  = pd.Series(STATIC_WEIGHTS)
    r_static  = (ret_components * static_w).sum(axis=1)

    # H250: continuous score drives weights each month
    # Use PRIOR month-end score (signal → signal lagged by one month)
    score_lagged = score_a.shift(1).fillna(0.0)
    rh_lagged    = rh_a.shift(1).fillna(False)

    h250_rets = []
    h250_wts_track = []
    for i, dt in enumerate(common_idx):
        s     = float(score_lagged.iloc[i])
        hike  = bool(rh_lagged.iloc[i])
        wts   = score_to_weights(s, rate_hike=hike)
        row   = ret_components.loc[dt]
        r     = sum(wts[k] * row[k] for k in wts if k in row)
        h250_rets.append(r)
        h250_wts_track.append(wts)

    r_h250 = pd.Series(h250_rets, index=common_idx)

    # ── 7. Statistics ─────────────────────────────────────────────────────────
    print("\n[7] Computing statistics...")
    is_mask  = common_idx <= pd.Timestamp(IS_END)
    oos_mask = common_idx >= pd.Timestamp(OOS_START)

    static_is   = calc_stats(r_static[is_mask],  label="Static IS")
    static_oos  = calc_stats(r_static[oos_mask], label="Static OOS")
    h250_is     = calc_stats(r_h250[is_mask],    label="H250 IS")
    h250_oos    = calc_stats(r_h250[oos_mask],   label="H250 OOS")

    print(f"\n    Static IS:  Sharpe={static_is['sharpe']:.3f}  "
          f"MaxDD={static_is['max_dd']:.3f}  CAGR={static_is['cagr']:.3f}")
    print(f"    Static OOS: Sharpe={static_oos['sharpe']:.3f}  "
          f"MaxDD={static_oos['max_dd']:.3f}  CAGR={static_oos['cagr']:.3f}")
    print(f"    H250   IS:  Sharpe={h250_is['sharpe']:.3f}  "
          f"MaxDD={h250_is['max_dd']:.3f}  CAGR={h250_is['cagr']:.3f}")
    print(f"    H250   OOS: Sharpe={h250_oos['sharpe']:.3f}  "
          f"MaxDD={h250_oos['max_dd']:.3f}  CAGR={h250_oos['cagr']:.3f}")

    sharpe_vs_static   = h250_oos["sharpe"] - H249_STATIC_OOS_SHARPE
    maxdd_improvement  = H249_STATIC_OOS_MAXDD - h250_oos["max_dd"]  # positive = better

    print(f"\n    H250 OOS Sharpe vs H249 static: {sharpe_vs_static:+.3f} (gate: >= +0.10)")
    print(f"    MaxDD improvement vs H249 static: {maxdd_improvement:+.4f} (gate: >= 0.02)")

    gate1_pass = sharpe_vs_static >= 0.10
    gate2_pass = maxdd_improvement >= 0.02
    confirmed  = gate1_pass or gate2_pass
    print(f"    Gate 1 (Sharpe): {'PASS' if gate1_pass else 'FAIL'}")
    print(f"    Gate 2 (MaxDD):  {'PASS' if gate2_pass else 'FAIL'}")
    print(f"    Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── 8. Score distribution and weight analysis ─────────────────────────────
    print("\n[8] Score and weight analysis...")
    score_oos = score_lagged[oos_mask]
    print(f"    OOS score distribution:")
    print(f"      Mean:  {score_oos.mean():.3f}")
    print(f"      Std:   {score_oos.std():.3f}")
    print(f"      < -0.5 (defensive):  {(score_oos < -0.5).sum()} months")
    print(f"      -0.5 to 0.0:         {((score_oos >= -0.5) & (score_oos < 0)).sum()} months")
    print(f"      0.0 to 0.5:          {((score_oos >= 0) & (score_oos < 0.5)).sum()} months")
    print(f"      > 0.5 (growth):      {(score_oos >= 0.5).sum()} months")

    # Average weights in OOS
    oos_wts_df = pd.DataFrame(h250_wts_track, index=common_idx)[oos_mask]
    print(f"\n    Average OOS weights:")
    for k in ["H041a","H026","H045","IBS"]:
        print(f"      {k}: {oos_wts_df[k].mean():.3f} "
              f"(min {oos_wts_df[k].min():.3f}, max {oos_wts_df[k].max():.3f})")

    # Correlation vs H249 regime OOS (load from results)
    corr_vs_static = r_h250[oos_mask].corr(r_static[oos_mask])
    print(f"\n    Corr(H250, Static) OOS: {corr_vs_static:.4f}")

    # ── 9. Save results ───────────────────────────────────────────────────────
    print("\n[9] Saving results...")
    results = {
        "hypothesis":   "H250",
        "description":  "Continuous Macro-Regime Score (tanh-mapped)",
        "source":       "arXiv:2605.20636 (Xiong, May 2026)",
        "confirmed":    confirmed,
        "confirm_gate": "OOS Sharpe >= H249_static+0.10 OR MaxDD improvement >= 2%",
        "h249_static_oos_sharpe": H249_STATIC_OOS_SHARPE,
        "h249_static_oos_maxdd":  H249_STATIC_OOS_MAXDD,
        "sharpe_vs_h249_static":  round(sharpe_vs_static, 4),
        "maxdd_improvement":       round(maxdd_improvement, 4),
        "gate1_sharpe_pass":       gate1_pass,
        "gate2_maxdd_pass":        gate2_pass,
        "static_is":               static_is,
        "static_oos":              static_oos,
        "h250_is":                 h250_is,
        "h250_oos":                h250_oos,
        "score_oos_stats": {
            "mean":  round(float(score_oos.mean()), 4),
            "std":   round(float(score_oos.std()), 4),
            "min":   round(float(score_oos.min()), 4),
            "max":   round(float(score_oos.max()), 4),
        },
        "avg_oos_weights": {k: round(float(oos_wts_df[k].mean()), 4)
                            for k in ["H041a","H026","H045","IBS"]},
        "corr_vs_static_oos": round(float(corr_vs_static), 4),
        "data_source": "yfinance + FRED (H249 cache)",
    }

    out_path = RESULT_DIR / "h250_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"    Saved: {out_path}")

    print("\n" + "=" * 60)
    print(f"H250 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  OOS Sharpe: {h250_oos['sharpe']:.4f} vs static {H249_STATIC_OOS_SHARPE:.4f}")
    print(f"  OOS MaxDD:  {h250_oos['max_dd']:.4f} vs static {H249_STATIC_OOS_MAXDD:.4f}")
    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
