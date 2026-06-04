"""
H249 — Regime-Conditional Portfolio Weights
============================================
Design: Adjust H041a/H026/H045/IBS weights dynamically based on macro regime.
Static baseline: H041a 22% / H026 27% / H045 21% / IBS 30%

Regime signals:
  1. SPY vs 200-day MA (bull/bear)
  2. VIX level from FRED (calm/volatile, threshold 20 and 25)
  3. 10Y yield direction from FRED DGS10 (rising/falling, 3M change)

Regime weight table (monthly, determined at prior month-end):
  Bull + Calm (SPY>200MA, VIX<20):
    H041a 30%, H026 35%, H045 12%, IBS 23%
  Bull + Volatile (SPY>200MA, VIX 20-25):
    H041a 25%, H026 30%, H045 18%, IBS 27%
  Bear + Calm (SPY<200MA, VIX 20-25):
    H041a 18%, H026 22%, H045 32%, IBS 28%
  Bear + Volatile (SPY<200MA, VIX>25):
    H041a 12%, H026 15%, H045 40%, IBS 33%
  Rate hike modifier (10Y rising >50bps in prior quarter):
    Shift +8% from H045 to IBS

Sub-strategies:
  H041a: 7-asset top-1 monthly momentum
         (SPY, QQQ, TLT, GLD, IEF, EFA, EEM)
  H026:  11-sector ETF top-1 monthly momentum
         (XLK, XLE, XLF, XLV, XLI, XLB, XLU, XLRE, XLY, XLP, XLC + cash=BIL)
  H045:  7-bond ETF top-2 equal-weight monthly momentum
         (SHY, IEI, IEF, TLT, TIP, HYG, LQD)
  IBS:   Mean-reversion on XLK (20%), SMH (8%), IGV (2%) within IBS bucket (30%)
         IBS = (Close-Low)/(High-Low); buy when IBS < 0.25

IS: 2008-2017  OOS: 2018-2026
Confirm: OOS Sharpe improvement > 0.2 vs static blend (historical ~4.158)
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

# Sub-strategy universes
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H026_SECTORS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLY","XLP","XLC","XLRE"]
H045_BONDS   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD"]
IBS_TICKERS  = ["XLK","SMH","IGV","SPY"]  # SPY needed for regime
BIL          = "BIL"

# IBS weights within the IBS sub-portfolio (sum to 1.0)
IBS_WEIGHTS = {"XLK": 20/30, "SMH": 8/30, "IGV": 2/30}

# Static production weights
STATIC_WEIGHTS = {"H041a": 0.22, "H026": 0.27, "H045": 0.21, "IBS": 0.30}

# Regime weight tables [H041a, H026, H045, IBS]
# Regime = (bull/bear, calm/volatile)
REGIME_WEIGHTS = {
    ("bull", "calm"):     {"H041a": 0.30, "H026": 0.35, "H045": 0.12, "IBS": 0.23},
    ("bull", "volatile"): {"H041a": 0.25, "H026": 0.30, "H045": 0.18, "IBS": 0.27},
    ("bear", "calm"):     {"H041a": 0.18, "H026": 0.22, "H045": 0.32, "IBS": 0.28},
    ("bear", "volatile"): {"H041a": 0.12, "H026": 0.15, "H045": 0.40, "IBS": 0.33},
}

# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, tag=""):
    all_tickers = sorted(set(tickers))
    cache_path = CACHE_DIR / f"h249_{tag}_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        # check all tickers present
        missing = [t for t in all_tickers if t not in df.columns]
        if not missing:
            return df
    print(f"  Downloading {len(all_tickers)} tickers [{tag}]...")
    raw = yf.download(all_tickers, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw.rename(columns={all_tickers[0]: all_tickers[0]}) if len(all_tickers)==1 else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cache_path)
    return closes

def fetch_ohlcv(tickers, tag=""):
    """Fetch daily OHLCV for IBS computation."""
    cache_path = CACHE_DIR / f"h249_ohlcv_{tag}_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    print(f"  Downloading OHLCV for {tickers}...")
    raw = yf.download(sorted(tickers), start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        # Stack: (metric, ticker) -> store as (Date, ticker_metric)
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
    """Fetch a FRED series as a daily Series."""
    cache_path = CACHE_DIR / f"h249_fred_{series_id}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df["value"]
    print(f"  Fetching FRED {series_id}...")
    api_key = FRED_API_KEY
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={api_key}&file_type=json"
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
# Sub-strategy: monthly return series
# ─────────────────────────────────────────────────────────────────────────────

def compute_momentum_strategy(prices_monthly, top_n=1):
    """
    Monthly momentum signal: rank(12m_return) + rank(inv_6m_vol).
    Returns monthly portfolio return series.
    """
    # Monthly returns
    ret_m = prices_monthly.pct_change()
    # 12m momentum (use 11-month lookback to avoid lookahead - signal at prior month-end)
    mom12 = prices_monthly.pct_change(12)
    # 6m volatility (use 6-month rolling std of monthly returns)
    vol6  = ret_m.rolling(6).std()

    port_returns = []
    dates = prices_monthly.index
    for i in range(13, len(dates)):
        # Signal at end of month i-1, hold during month i
        sig_date = dates[i-1]
        hold_date = dates[i]

        m12 = mom12.loc[sig_date]
        v6  = vol6.loc[sig_date]

        # Composite rank
        valid = m12.notna() & v6.notna() & (v6 > 0)
        if valid.sum() < max(top_n, 2):
            port_returns.append((hold_date, 0.0))
            continue

        rank_mom = m12[valid].rank(ascending=False)
        rank_vol = (1.0 / v6[valid]).rank(ascending=False)
        composite = (rank_mom + rank_vol)

        # Select top_n
        selected = composite.nlargest(top_n).index.tolist()
        if not selected:
            port_returns.append((hold_date, 0.0))
            continue

        # Equal-weight return in hold month
        hold_rets = ret_m.loc[hold_date, selected]
        port_ret  = hold_rets.mean()
        port_returns.append((hold_date, port_ret if not np.isnan(port_ret) else 0.0))

    if not port_returns:
        return pd.Series(dtype=float)
    dates_out, rets_out = zip(*port_returns)
    return pd.Series(rets_out, index=pd.DatetimeIndex(dates_out))

def compute_ibs_strategy(ohlcv_df, tickers, weights_dict):
    """
    IBS mean-reversion: Buy at close when (Close-Low)/(High-Low) < 0.25.
    Sell at close when IBS > 0.75 or after 5 days.
    Returns daily portfolio return series.
    """
    daily_rets = {}
    for t in tickers:
        close = ohlcv_df.get(f"{t}_Close")
        high  = ohlcv_df.get(f"{t}_High")
        low   = ohlcv_df.get(f"{t}_Low")
        if close is None or high is None or low is None:
            continue

        ibs   = (close - low) / (high - low + 1e-10)
        ret_d = close.pct_change()

        # IBS strategy: held=1 if in position (max 5-day hold)
        in_pos  = False
        days_held = 0
        strat_rets = []

        for j in range(1, len(close)):
            prev_ibs = ibs.iloc[j-1]
            if not in_pos:
                if prev_ibs < 0.25:
                    in_pos = True
                    days_held = 0
            if in_pos:
                strat_rets.append(ret_d.iloc[j])
                days_held += 1
                # Exit when IBS > 0.75 or after 5 days
                if ibs.iloc[j] > 0.75 or days_held >= 5:
                    in_pos = False
            else:
                strat_rets.append(0.0)

        ser = pd.Series(strat_rets, index=close.index[1:])
        daily_rets[t] = ser

    if not daily_rets:
        return pd.Series(dtype=float)

    df = pd.DataFrame(daily_rets)
    # Weighted sum within IBS tickers
    wts = pd.Series({t: weights_dict.get(t, 0.0) for t in df.columns})
    wts = wts / wts.sum()
    port_daily = (df * wts).sum(axis=1)
    return port_daily


# ─────────────────────────────────────────────────────────────────────────────
# Regime detection
# ─────────────────────────────────────────────────────────────────────────────

def compute_monthly_regime(spy_prices_daily, vix_monthly, spy_start="2005-01-01"):
    """
    For each month-end, determine regime:
      Market: bull if SPY > 200-day MA, else bear
      Vol:    calm if VIX < 20, volatile if VIX >= 20
    Returns DataFrame with monthly regime columns.
    """
    # SPY 200-day MA
    spy = spy_prices_daily.dropna()
    spy_ma200 = spy.rolling(200).mean()

    # Monthly snapshots at month-end
    spy_m = spy.resample("ME").last()
    ma_m  = spy_ma200.resample("ME").last()

    market_regime = pd.Series(
        np.where(spy_m >= ma_m, "bull", "bear"),
        index=spy_m.index
    )

    # VIX monthly (average of available daily data for the month)
    if vix_monthly is not None:
        vix_m = vix_monthly.resample("ME").mean()
        vol_regime = pd.Series(
            np.where(vix_m < 20, "calm", "volatile"),
            index=vix_m.index
        )
    else:
        # Fallback: all calm
        vol_regime = pd.Series("calm", index=spy_m.index)

    regime_df = pd.DataFrame({
        "market": market_regime,
        "vol":    vol_regime
    })
    return regime_df


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio statistics
# ─────────────────────────────────────────────────────────────────────────────

def calc_stats(returns_series, label=""):
    """Compute stats from monthly return series."""
    r = returns_series.dropna()
    if len(r) < 12:
        return {}
    eq = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr    = (eq.iloc[-1]) ** (1/n_years) - 1
    vol     = r.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    neg_yrs = (r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
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
    print("H249 — Regime-Conditional Portfolio Weights")
    print("=" * 60)

    # ── 1. Download price data ────────────────────────────────────────────────

    all_tickers = sorted(set(
        H041A_ASSETS + H026_SECTORS + H045_BONDS + list(IBS_WEIGHTS.keys()) + [BIL, "SPY"]
    ))
    print(f"\n[1] Downloading close prices for {len(all_tickers)} tickers...")
    closes = fetch_close(all_tickers, tag="all")
    print(f"    Shape: {closes.shape}, range: {closes.index[0].date()} to {closes.index[-1].date()}")

    # OHLCV for IBS
    print("[1b] Downloading OHLCV for IBS tickers...")
    ohlcv = fetch_ohlcv(list(IBS_WEIGHTS.keys()), tag="ibs")

    # FRED: VIX
    print("[1c] Fetching FRED VIX...")
    vix = fetch_fred("VIXCLS")

    # FRED: 10Y yield
    print("[1d] Fetching FRED 10Y yield...")
    dgs10 = fetch_fred("DGS10")

    # ── 2. Resample to monthly ────────────────────────────────────────────────
    print("\n[2] Resampling to monthly...")
    closes_m = closes.resample("ME").last()

    # ── 3. Compute sub-strategy monthly returns ───────────────────────────────
    print("\n[3] Computing sub-strategy monthly returns...")

    # H041a: 7-asset top-1
    h041a_cols = [c for c in H041A_ASSETS if c in closes_m.columns]
    print(f"    H041a universe: {len(h041a_cols)} assets")
    r_h041a = compute_momentum_strategy(closes_m[h041a_cols], top_n=1)
    print(f"    H041a returns: {len(r_h041a)} months, mean={r_h041a.mean():.4f}")

    # H026: 11-sector top-1 (use BIL if top asset is negative)
    h026_cols = [c for c in H026_SECTORS if c in closes_m.columns]
    print(f"    H026 universe: {len(h026_cols)} sectors")
    r_h026 = compute_momentum_strategy(closes_m[h026_cols], top_n=1)
    print(f"    H026 returns: {len(r_h026)} months, mean={r_h026.mean():.4f}")

    # H045: 7-bond top-2
    h045_cols = [c for c in H045_BONDS if c in closes_m.columns]
    print(f"    H045 universe: {len(h045_cols)} bonds")
    r_h045 = compute_momentum_strategy(closes_m[h045_cols], top_n=2)
    print(f"    H045 returns: {len(r_h045)} months, mean={r_h045.mean():.4f}")

    # IBS: daily strategy -> aggregate to monthly
    print("    Computing IBS strategy...")
    ibs_cols = [c for c in IBS_WEIGHTS.keys()]
    r_ibs_daily = compute_ibs_strategy(ohlcv, ibs_cols, IBS_WEIGHTS)
    # Compound daily to monthly
    r_ibs_monthly = r_ibs_daily.resample("ME").apply(lambda x: (1+x).prod()-1)
    print(f"    IBS returns: {len(r_ibs_monthly)} months, mean={r_ibs_monthly.mean():.4f}")

    # ── 4. Regime signals ─────────────────────────────────────────────────────
    print("\n[4] Computing regime signals...")
    spy_daily = closes["SPY"].dropna() if "SPY" in closes.columns else None
    regime_m = compute_monthly_regime(spy_daily, vix)
    print(f"    Regime series: {len(regime_m)} months")
    print(f"    Bull months: {(regime_m['market']=='bull').sum()}")
    print(f"    Calm months: {(regime_m['vol']=='calm').sum()}")

    # 10Y yield rate hike modifier
    if dgs10 is not None:
        dgs10_m = dgs10.resample("ME").last()
        # 3-month change in 10Y
        dgs10_3m_chg = dgs10_m.diff(3)  # change in pp over last 3 months
        rate_hike = (dgs10_3m_chg > 0.5)  # rising >50bps in 3m
    else:
        rate_hike = pd.Series(False, index=regime_m.index)

    # ── 5. Align all return series ────────────────────────────────────────────
    print("\n[5] Aligning return series...")
    # Common date range
    start = pd.Timestamp("2008-01-01")
    end   = pd.Timestamp("2026-05-31")

    # Align monthly returns
    def align(s):
        s = s[s.index >= start]
        s = s[s.index <= end]
        return s

    r_h041a   = align(r_h041a)
    r_h026    = align(r_h026)
    r_h045    = align(r_h045)
    r_ibs_m   = align(r_ibs_monthly)
    regime_df = align(regime_m)
    rate_hike = align(rate_hike)

    # Build a common monthly index
    common_idx = r_h041a.index.intersection(r_h026.index).intersection(
        r_h045.index).intersection(r_ibs_m.index)
    common_idx = common_idx[(common_idx >= start) & (common_idx <= end)]
    print(f"    Common months: {len(common_idx)}")

    r_h041a   = r_h041a.reindex(common_idx)
    r_h026    = r_h026.reindex(common_idx)
    r_h045    = r_h045.reindex(common_idx)
    r_ibs_m   = r_ibs_m.reindex(common_idx)
    regime_df = regime_df.reindex(common_idx, method="ffill")
    rate_hike = rate_hike.reindex(common_idx, method="ffill").fillna(False)

    # ── 6. Build static and regime-conditional portfolios ────────────────────
    print("\n[6] Building portfolios...")

    ret_components = pd.DataFrame({
        "H041a": r_h041a,
        "H026":  r_h026,
        "H045":  r_h045,
        "IBS":   r_ibs_m,
    })
    ret_components = ret_components.fillna(0.0)

    # Static portfolio
    static_w = pd.Series(STATIC_WEIGHTS)
    r_static = (ret_components * static_w).sum(axis=1)

    # Regime-conditional portfolio
    regime_ret = []
    regime_wt_used = []
    for dt in common_idx:
        # Regime determined by PRIOR month-end signal (lag 1)
        # Find prior month
        prior_dt = dt - pd.offsets.MonthEnd(1)
        mkt = regime_df.loc[dt, "market"] if dt in regime_df.index else "bull"
        vol = regime_df.loc[dt, "vol"] if dt in regime_df.index else "calm"
        hike = rate_hike.loc[dt] if dt in rate_hike.index else False

        # Get regime weights
        regime_key = (mkt, vol)
        wts = dict(REGIME_WEIGHTS.get(regime_key, STATIC_WEIGHTS))

        # Rate hike modifier: shift 8% from H045 to IBS
        if hike:
            shift = 0.08
            wts["H045"] = max(0.0, wts["H045"] - shift)
            wts["IBS"]  = min(1.0, wts["IBS"] + shift)

        # Normalize weights
        total = sum(wts.values())
        wts   = {k: v/total for k, v in wts.items()}

        row = ret_components.loc[dt]
        r   = sum(wts[k] * row[k] for k in wts if k in row)
        regime_ret.append(r)
        regime_wt_used.append(wts)

    r_regime = pd.Series(regime_ret, index=common_idx)

    # ── 7. Compute statistics ─────────────────────────────────────────────────
    print("\n[7] Computing statistics...")

    # IS: 2008-2017, OOS: 2018-2026
    is_mask  = common_idx <= pd.Timestamp(IS_END)
    oos_mask = common_idx >= pd.Timestamp(OOS_START)

    # Component strategies IS/OOS
    for name, series in [("H041a", r_h041a), ("H026", r_h026),
                          ("H045", r_h045), ("IBS", r_ibs_m)]:
        is_s  = calc_stats(series[is_mask],  label=f"{name} IS")
        oos_s = calc_stats(series[oos_mask], label=f"{name} OOS")
        print(f"    {name}: IS Sharpe={is_s.get('sharpe','N/A'):.3f}  "
              f"OOS Sharpe={oos_s.get('sharpe','N/A'):.3f}")

    print()
    # Static blend
    static_is  = calc_stats(r_static[is_mask],  label="Static IS")
    static_oos = calc_stats(r_static[oos_mask], label="Static OOS")
    print(f"    Static blend: IS  Sharpe={static_is['sharpe']:.3f}  "
          f"MaxDD={static_is['max_dd']:.3f}  NegYrs={static_is['neg_yrs']}")
    print(f"    Static blend: OOS Sharpe={static_oos['sharpe']:.3f}  "
          f"MaxDD={static_oos['max_dd']:.3f}  NegYrs={static_oos['neg_yrs']}")

    # Regime-conditional
    regime_is  = calc_stats(r_regime[is_mask],  label="Regime IS")
    regime_oos = calc_stats(r_regime[oos_mask], label="Regime OOS")
    print(f"    Regime blend: IS  Sharpe={regime_is['sharpe']:.3f}  "
          f"MaxDD={regime_is['max_dd']:.3f}  NegYrs={regime_is['neg_yrs']}")
    print(f"    Regime blend: OOS Sharpe={regime_oos['sharpe']:.3f}  "
          f"MaxDD={regime_oos['max_dd']:.3f}  NegYrs={regime_oos['neg_yrs']}")

    sharpe_improvement = regime_oos["sharpe"] - static_oos["sharpe"]
    print(f"\n    OOS Sharpe improvement: {sharpe_improvement:+.3f}")
    print(f"    Confirm gate: > +0.20")
    confirmed = sharpe_improvement > 0.20
    print(f"    Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── 8. Regime breakdown ───────────────────────────────────────────────────
    print("\n[8] OOS regime breakdown...")
    oos_regime_df = regime_df[oos_mask]
    regime_counts = oos_regime_df.groupby(["market","vol"]).size()
    print("    Regime counts (OOS):")
    for (m,v), cnt in regime_counts.items():
        print(f"      {m}+{cnt}... wait, {m}+{v}: {cnt} months")

    hike_months = int(rate_hike[oos_mask].sum())
    print(f"    Rate hike months (OOS): {hike_months}")

    # Correlation: regime vs static
    corr = r_regime[oos_mask].corr(r_static[oos_mask])
    print(f"    Corr(Regime, Static) OOS: {corr:.3f}")

    # ── 9. Save results ───────────────────────────────────────────────────────
    print("\n[9] Saving results...")
    results = {
        "hypothesis":          "H249",
        "description":         "Regime-Conditional Portfolio Weights",
        "confirmed":           confirmed,
        "confirm_gate":        "OOS Sharpe improvement > 0.20 vs static",
        "sharpe_improvement":  round(sharpe_improvement, 4),
        "static_is":           static_is,
        "static_oos":          static_oos,
        "regime_is":           regime_is,
        "regime_oos":          regime_oos,
        "regime_weights": {
            "bull_calm":     REGIME_WEIGHTS[("bull","calm")],
            "bull_volatile": REGIME_WEIGHTS[("bull","volatile")],
            "bear_calm":     REGIME_WEIGHTS[("bear","calm")],
            "bear_volatile": REGIME_WEIGHTS[("bear","volatile")],
        },
        "component_oos": {
            "H041a": calc_stats(r_h041a[oos_mask], "H041a OOS"),
            "H026":  calc_stats(r_h026[oos_mask],  "H026 OOS"),
            "H045":  calc_stats(r_h045[oos_mask],  "H045 OOS"),
            "IBS":   calc_stats(r_ibs_m[oos_mask], "IBS OOS"),
        },
        "oos_regime_counts": {
            f"{m}+{v}": int(cnt)
            for (m,v), cnt in regime_counts.items()
        },
        "oos_rate_hike_months": hike_months,
        "corr_regime_static_oos": round(float(corr), 4),
        "data_source": "yfinance + FRED",
    }

    out_path = RESULT_DIR / "h249_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"    Saved → {out_path}")

    return results


if __name__ == "__main__":
    main()
