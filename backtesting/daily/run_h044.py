"""
H044 — Volatility Targeting Applied to H042
============================================

H042 recap: H041a 56% / H026 16% / H037b 28%
  Sharpe 1.949, CAGR 14.5%, MaxDD -9.0%, AnnVol 7.4%

Concept: scale the entire H042 portfolio up or down each month to target a
fixed annualized volatility. When realized vol is low → lever up slightly.
When realized vol is high → reduce exposure.

Implementation:
  1. Build H042 daily returns from the three component daily series
     (H041a and H026 use month-end signals applied daily; H037b uses daily IBS signal)
  2. Compute realized portfolio vol each month-end: 21-day EWM std of H042 daily returns
  3. Scale factor = target_vol / realized_vol, capped at 1.5× and floored at 0.3×
  4. Next month's H042 return = scale_factor × raw_H042_return
                               + (1 - scale_factor) × cash_return  (SHY ~0.3%/month)

Test three target vols: 8%, 10%, 12%

Regime analysis:
  High-vol periods: 2008-09, 2020, 2022
  Low-vol periods:  2012-14, 2016-17

Outputs:
  /workspace/agent/backtesting/results/h044_results.json
  /workspace/agent/backtesting/daily/run_h044.py  (this file)
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

FULL_START    = "2000-01-01"
FULL_END      = "2026-04-27"
WINDOW_START  = "2003-08-01"   # common period aligned to EFA/EEM availability

# H042 optimal weights (max-Sharpe)
W_H041A = 0.56
W_H026  = 0.16
W_H037B = 0.28

# H037b parameters
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005

# Asset universes
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
TOP_N_H41A   = 2
SECTOR_ETFS  = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

# Volatility targeting parameters
TARGET_VOLS    = [0.08, 0.10, 0.12]
SCALE_CAP      = 1.5
SCALE_FLOOR    = 0.3
EWM_HALFLIFE   = 21   # days, for EWM std estimate
CASH_RETURN_MO = 0.003   # SHY ~0.3%/month

# Regime windows
HIGH_VOL_REGIMES = [
    ("2008-01-01", "2009-12-31", "GFC 2008-09"),
    ("2020-01-01", "2020-12-31", "COVID 2020"),
    ("2022-01-01", "2022-12-31", "Rate shock 2022"),
]
LOW_VOL_REGIMES = [
    ("2012-01-01", "2014-12-31", "Low-vol 2012-14"),
    ("2016-01-01", "2017-12-31", "Low-vol 2016-17"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h044_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    # Reuse existing H042 caches
    key = "_".join(sorted(tickers)) + f"_h042_all_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    h42_cp = CACHE_DIR / f"h042_{h}.parquet"
    if h42_cp.exists():
        print(f"  Loaded close prices from H042 cache")
        return pd.read_parquet(h42_cp)

    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    """Return SPY OHLC; reuse existing caches when possible."""
    for fname in [
        f"h031_spy_ohlc_{start}_{end}.parquet",
        f"h031b_spy_ohlc_{start}_{end}.parquet",
        f"h042_spy_ohlc_{start}_{end}.parquet",
    ]:
        cp = CACHE_DIR / fname
        if cp.exists():
            df = pd.read_parquet(cp)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("SPY", axis=1, level=1)
            df = df.rename(columns=str.lower)
            needed = ["open", "high", "low", "close"]
            if all(c in df.columns for c in needed):
                print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
                return df[needed]
    cp = CACHE_DIR / f"h044_spy_ohlc_{start}_{end}.parquet"
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
# Component daily return builders
# ─────────────────────────────────────────────────────────────────────────────

def h041a_daily_returns(prices: pd.DataFrame) -> pd.Series:
    """
    7-asset macro rotation daily returns.
    Signal computed at month-end; position applied for the entire following month.
    Returns a daily return series (0 on days not in position).
    """
    available = [a for a in H041A_ASSETS if a in prices.columns]
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H41A

    # Build a daily position DataFrame: each day's weights for each asset
    daily_idx = px.index
    # Map each day to the position determined at the prior month-end
    daily_returns = pd.Series(0.0, index=daily_idx)

    prev_close = px.iloc[0]
    for i in range(12, len(monthly_px)):
        month_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        month_end   = monthly_px.index[i]

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H41A:
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H41A).index)

        # Daily returns within this month for the chosen assets
        mask = (daily_idx >= month_start) & (daily_idx <= month_end)
        sub_px = px[top].loc[mask]
        if len(sub_px) < 2:
            continue
        sub_daily_ret = sub_px.pct_change()
        # Portfolio daily return = equal-weight average of the top assets
        port_daily = sub_daily_ret[top].mean(axis=1)
        port_daily.iloc[0] = 0.0  # first day: no return (prev day was end of prev month)
        daily_returns.loc[mask] = port_daily.values

    return daily_returns


def h026_daily_returns(prices: pd.DataFrame) -> pd.Series:
    """
    11-sector top-3 momentum daily returns.
    Monthly signal; daily returns applied throughout each month.
    """
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float)

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H26
    daily_idx = px.index
    daily_returns = pd.Series(0.0, index=daily_idx)

    for i in range(12, len(monthly_px)):
        month_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        month_end   = monthly_px.index[i]

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H26:
            continue

        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N_H26).index)

        mask = (daily_idx >= month_start) & (daily_idx <= month_end)
        sub_px = px[top_hold].loc[mask]
        if len(sub_px) < 2:
            continue
        sub_daily_ret = sub_px.pct_change()
        port_daily = sub_daily_ret[top_hold].mean(axis=1)
        port_daily.iloc[0] = 0.0
        daily_returns.loc[mask] = port_daily.values

    return daily_returns


def h037b_daily_returns(ohlc: pd.DataFrame) -> pd.Series:
    """
    H037b: IBS mean-reversion on SPY with gap-down exclusion filter.
    Returns daily returns (0 when not in position; open-to-close on entry, close-to-close thereafter).
    """
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    gap     = (df["open"] - prev_cl) / prev_cl

    daily_returns = pd.Series(0.0, index=df.index)
    position  = 0
    days_held = 0

    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])

        ret_oc = (c / o - 1)      if o > 0     else 0.0
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0

        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER_B:
                position  = 1
                days_held = 1
                daily_returns.iloc[i] = ret_oc
        else:
            days_held += 1
            daily_returns.iloc[i] = ret_cc
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0

    return daily_returns


# ─────────────────────────────────────────────────────────────────────────────
# H042 daily returns (blended)
# ─────────────────────────────────────────────────────────────────────────────

def h042_daily_returns(prices: pd.DataFrame, ohlc: pd.DataFrame) -> pd.Series:
    """Build H042 daily returns from the three component series at 56/16/28."""
    print("  Building H041a daily returns …")
    r1 = h041a_daily_returns(prices)
    print("  Building H026 daily returns …")
    r2 = h026_daily_returns(prices)
    print("  Building H037b daily returns …")
    r3 = h037b_daily_returns(ohlc)

    # Align to common index
    common = r1.index.intersection(r2.index).intersection(r3.index)
    window_ts = pd.Timestamp(WINDOW_START)
    common = common[common >= window_ts]
    r1 = r1.loc[common]
    r2 = r2.loc[common]
    r3 = r3.loc[common]

    blended = W_H041A * r1 + W_H026 * r2 + W_H037B * r3
    return blended


# ─────────────────────────────────────────────────────────────────────────────
# Volatility targeting
# ─────────────────────────────────────────────────────────────────────────────

def apply_vol_targeting(
    daily_rets: pd.Series,
    target_vol: float,
    scale_cap: float = SCALE_CAP,
    scale_floor: float = SCALE_FLOOR,
    ewm_halflife: int = EWM_HALFLIFE,
    cash_return_mo: float = CASH_RETURN_MO,
) -> pd.Series:
    """
    Apply monthly volatility targeting to H042 daily returns.

    At each month-end, compute 21-day EWM std of H042 daily returns,
    annualize it, compute scale_factor = target_vol / realized_vol,
    cap at scale_cap and floor at scale_floor.

    Apply that scale factor to all daily returns in the NEXT calendar month.
    The undeployed fraction (1 - scale_factor) earns cash_return_mo/trading_days_in_month.

    Returns scaled daily return series.
    """
    dr = daily_rets.copy()

    # Compute EWM annualized vol (rolling, updated daily)
    ewm_std_daily = dr.ewm(halflife=ewm_halflife, min_periods=5).std()
    ann_vol = ewm_std_daily * np.sqrt(252)

    # Month-end dates within the series
    monthly_ends = dr.resample("ME").last().index

    # Build a scale_factor series indexed to trading days
    scale_series = pd.Series(1.0, index=dr.index)  # default: no scaling

    for i in range(len(monthly_ends) - 1):
        me_date   = monthly_ends[i]
        next_me   = monthly_ends[i + 1]

        # Look up realized vol at this month-end
        if me_date not in ann_vol.index:
            # find nearest prior date
            prior = ann_vol[ann_vol.index <= me_date]
            if prior.empty:
                continue
            rv = float(prior.iloc[-1])
        else:
            rv = float(ann_vol.loc[me_date])

        if rv <= 0 or np.isnan(rv):
            sf = 1.0
        else:
            sf = target_vol / rv
        sf = max(scale_floor, min(scale_cap, sf))

        # Apply to next month
        mask = (dr.index > me_date) & (dr.index <= next_me)
        scale_series.loc[mask] = sf

    # Scaled daily returns
    cash_daily = cash_return_mo / 21.0  # approximate trading days per month
    scaled_rets = scale_series * dr + (1.0 - scale_series) * cash_daily

    return scaled_rets, scale_series


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_daily(daily_rets: pd.Series) -> dict:
    dr = daily_rets.dropna()
    if len(dr) < 50:
        return {"error": "insufficient data"}
    equity  = (1 + dr).cumprod()
    n_years = len(dr) / 252.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(dr.std(ddof=1)) * np.sqrt(252)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_days":       len(dr),
    }


def stats_in_window(daily_rets: pd.Series, start: str, end: str) -> dict:
    mask = (daily_rets.index >= pd.Timestamp(start)) & (daily_rets.index <= pd.Timestamp(end))
    sub = daily_rets.loc[mask]
    if len(sub) < 20:
        return {"error": "insufficient data", "n_days": len(sub)}
    return stats_from_daily(sub)


def scale_stats_in_window(scale_series: pd.Series, start: str, end: str) -> dict:
    mask = (scale_series.index >= pd.Timestamp(start)) & (scale_series.index <= pd.Timestamp(end))
    sub = scale_series.loc[mask]
    if sub.empty:
        return {}
    return {
        "mean_scale": round(float(sub.mean()), 4),
        "min_scale":  round(float(sub.min()),  4),
        "max_scale":  round(float(sub.max()),  4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H044 — Volatility Targeting Applied to H042")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices   = fetch_close(all_tickers, FULL_START, FULL_END, tag="h044_all")
    spy_ohlc = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build H042 daily returns ──────────────────────────────────────────
    print("\n[2] Building H042 daily returns (three-component blend) …")
    h042_dr = h042_daily_returns(prices, spy_ohlc)
    print(f"   H042 daily: {h042_dr.index[0].date()} → {h042_dr.index[-1].date()} ({len(h042_dr)} days)")

    # ── 3. Baseline H042 stats ────────────────────────────────────────────────
    print("\n[3] Computing H042 baseline stats (unscaled) …")
    baseline_stats = stats_from_daily(h042_dr)
    print(f"   CAGR {baseline_stats['cagr']:.2%}  Sharpe {baseline_stats['sharpe']:.3f}  "
          f"MaxDD {baseline_stats['max_drawdown']:.2%}  AnnVol {baseline_stats['ann_vol']:.2%}")

    # ── 4. Vol targeting for each target vol ─────────────────────────────────
    print("\n[4] Running volatility targeting …")
    vt_results = {}

    for tv in TARGET_VOLS:
        print(f"\n  Target vol = {tv:.0%} …")
        scaled_dr, scale_ser = apply_vol_targeting(h042_dr, target_vol=tv)
        stats = stats_from_daily(scaled_dr)
        print(f"    CAGR {stats['cagr']:.2%}  Sharpe {stats['sharpe']:.3f}  "
              f"MaxDD {stats['max_drawdown']:.2%}  AnnVol {stats['ann_vol']:.2%}")
        print(f"    Scale factor: mean {scale_ser.mean():.3f}  "
              f"min {scale_ser.min():.3f}  max {scale_ser.max():.3f}")

        # Regime analysis
        regime_stats = {}
        for (rs, re, rlabel) in HIGH_VOL_REGIMES + LOW_VOL_REGIMES:
            raw_s = stats_in_window(h042_dr, rs, re)
            vt_s  = stats_in_window(scaled_dr, rs, re)
            sc_s  = scale_stats_in_window(scale_ser, rs, re)
            regime_stats[rlabel] = {
                "period": f"{rs} — {re}",
                "h042_unscaled": raw_s,
                "h044_scaled":   vt_s,
                "scale_factor":  sc_s,
            }

        vt_results[f"target_{int(tv*100)}pct"] = {
            "target_vol": tv,
            "stats": stats,
            "scale_factor_summary": {
                "mean": round(float(scale_ser.mean()), 4),
                "median": round(float(scale_ser.median()), 4),
                "min":  round(float(scale_ser.min()),  4),
                "max":  round(float(scale_ser.max()),  4),
                "pct_above_1": round(float((scale_ser > 1.0).mean()), 4),
                "pct_at_cap":  round(float((scale_ser >= SCALE_CAP).mean()), 4),
                "pct_at_floor": round(float((scale_ser <= SCALE_FLOOR).mean()), 4),
            },
            "regime_analysis": regime_stats,
        }

    # ── 5. Summary table ──────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  H044 VOLATILITY TARGETING SUMMARY")
    print(f"  Period: {h042_dr.index[0].date()} → {h042_dr.index[-1].date()}")
    print(f"{'=' * 90}")
    print(f"  {'Scenario':<30}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*86}")
    print(f"  {'H042 baseline (unscaled)':<30}  "
          f"{baseline_stats['cagr']:>8.2%}  {baseline_stats['sharpe']:>8.3f}  "
          f"{baseline_stats['max_drawdown']:>8.2%}  {baseline_stats['ann_vol']:>8.2%}  "
          f"{baseline_stats['calmar']:>8.3f}")
    for tv in TARGET_VOLS:
        key = f"target_{int(tv*100)}pct"
        s = vt_results[key]["stats"]
        print(f"  {'H044 target vol ' + f'{tv:.0%}':<30}  "
              f"{s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
              f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  "
              f"{s['calmar']:>8.3f}")

    # ── 6. Regime comparison for best target vol ─────────────────────────────
    # Pick target vol = 10% as reference
    best_key = "target_10pct"
    print(f"\n  REGIME ANALYSIS (H044 target vol=10% vs H042 unscaled)")
    print(f"  {'Regime':<25}  {'H042 Sharpe':>12}  {'H044 Sharpe':>12}  {'Delta':>8}  {'H042 MaxDD':>12}  {'H044 MaxDD':>12}  {'Avg Scale':>10}")
    print(f"  {'-'*100}")
    regime_data = vt_results[best_key]["regime_analysis"]
    for rlabel, rd in regime_data.items():
        h42_s  = rd["h042_unscaled"]
        h44_s  = rd["h044_scaled"]
        sc_s   = rd.get("scale_factor", {})
        if "error" in h42_s or "error" in h44_s:
            continue
        delta = h44_s["sharpe"] - h42_s["sharpe"]
        avg_sc = sc_s.get("mean_scale", float("nan"))
        print(f"  {rlabel:<25}  {h42_s['sharpe']:>12.3f}  {h44_s['sharpe']:>12.3f}  "
              f"{delta:>+8.3f}  {h42_s['max_drawdown']:>12.2%}  {h44_s['max_drawdown']:>12.2%}  "
              f"{avg_sc:>10.3f}")

    # ── 7. Save results ───────────────────────────────────────────────────────
    output = {
        "strategy": "H044 — Volatility Targeting Applied to H042",
        "description": (
            "Scales H042 (H041a 56% / H026 16% / H037b 28%) monthly based on "
            "21-day EWM realized vol. Target vols tested: 8%, 10%, 12%. "
            "Scale factor capped at 1.5× (max leverage) and floored at 0.3×. "
            "Undeployed fraction earns SHY cash return (~0.3%/month)."
        ),
        "parameters": {
            "h042_weights": {"h041a": W_H041A, "h026": W_H026, "h037b": W_H037B},
            "ewm_halflife_days": EWM_HALFLIFE,
            "scale_cap":   SCALE_CAP,
            "scale_floor": SCALE_FLOOR,
            "cash_return_monthly": CASH_RETURN_MO,
        },
        "common_window": {
            "start": str(h042_dr.index[0].date()),
            "end":   str(h042_dr.index[-1].date()),
            "n_days": len(h042_dr),
        },
        "h042_baseline": baseline_stats,
        "h044_vol_targeting": vt_results,
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h044_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
