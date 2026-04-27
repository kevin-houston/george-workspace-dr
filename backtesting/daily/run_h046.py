"""
H046 — Multi-Sector IBS Mean-Reversion (H037b rules applied to sector ETFs)
============================================================================

H037b recap (SPY-only):
  Buy when prev IBS < 0.20 AND gap > -0.5%.
  Sell when IBS > 0.80 or held >= 5 days.
  Full-period Sharpe 1.021, CAGR 12.02%.

H046 — 5-sector multi-IBS:
  Apply identical H037b rules to each of: XLK, XLE, XLF, XLV, XLI
  Each sector gets 20% of total capital (equal slice).
  Positions can overlap (both XLK and XLF can be in position simultaneously).
  When a sector signal fires, trade that 20% slice; the other 80% sits in cash.

H046b — dynamic top-3 sector variant:
  Apply H037b rules to the H026 top-3 current momentum sectors only.
  Those 3 sectors each get 33.3% of capital.
  The H026 selection is updated monthly (last trading day of month → next month).

Correlation analysis vs H037b (SPY):
  Compute monthly returns of H046 and H037b (SPY).
  Report correlation and blending benefit vs H042 (the current optimal blend).

Period: 2000-2026 (full download), analysis from 2003-01-01 (matches H009/H037b history).

Outputs:
  /workspace/agent/backtesting/results/h046_results.json
  /workspace/agent/backtesting/daily/run_h046.py  (this file)
"""

import json
import math
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from itertools import product

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

SECTOR_ETFS_5  = ["XLK", "XLE", "XLF", "XLV", "XLI"]
SECTOR_ETFS_11 = ["XLK", "XLE", "XLF", "XLV", "XLI",
                   "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]

DATA_START  = "2000-01-01"
FULL_START  = "2003-01-01"
FULL_END    = "2026-04-27"
OOS_START   = "2017-01-01"

IBS_BUY   = 0.20
IBS_SELL  = 0.80
MAX_HOLD  = 5
GAP_FILTER = -0.005   # H037b: skip entry if gap < -0.5%

INITIAL_EQUITY = 100_000.0

CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(tickers: list, start: str, end: str) -> dict:
    """
    Download OHLC for a list of tickers. Returns dict {ticker: DataFrame}.
    Each DataFrame has columns: open, high, low, close (lower-case).
    Uses per-ticker parquet cache.
    """
    result = {}
    for t in tickers:
        key = f"h046_{t}_{start}_{end}"
        h   = hashlib.md5(key.encode()).hexdigest()[:12]
        cp  = CACHE_DIR / f"h046_{t}_{h}.parquet"

        if cp.exists():
            df = pd.read_parquet(cp)
            print(f"    {t}: loaded from cache ({len(df)} rows)")
        else:
            print(f"    {t}: downloading {start} → {end} …")
            raw = yf.download([t], start=start, end=end,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                df = raw.xs(t, axis=1, level=1)[["Open", "High", "Low", "Close"]]
            else:
                df = raw[["Open", "High", "Low", "Close"]]
            df = df.rename(columns=str.lower).dropna()
            df.index = pd.to_datetime(df.index)
            df.to_parquet(cp)
            print(f"      → {len(df)} rows cached")

        result[t] = df
    return result


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add ibs and gap columns. No look-ahead."""
    df = df.copy()
    denom            = (df["high"] - df["low"]).replace(0, np.nan)
    df["ibs"]        = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0)
    df["prev_close"] = df["close"].shift(1)
    df["gap"]        = (df["open"] - df["prev_close"]) / df["prev_close"]
    return df.dropna(subset=["prev_close", "ibs", "gap"])


def fetch_close_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Fetch adjusted close for a list of tickers — for momentum ranking."""
    key = "_".join(sorted(tickers)) + f"_close_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h046_close_{h}.parquet"

    if cp.exists():
        df = pd.read_parquet(cp)
        print(f"    Close prices: loaded from cache ({len(df)} rows × {len(df.columns)} tickers)")
        return df

    print(f"    Downloading close prices for {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw
    closes.index = pd.to_datetime(closes.index)
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    print(f"      → {len(closes)} rows")
    return closes


# ─────────────────────────────────────────────────────────────────────────────
# Per-sector IBS engine (single sector)
# ─────────────────────────────────────────────────────────────────────────────

def run_ibs_on_sector(
    df: pd.DataFrame,
    capital_fraction: float = 1.0,
    label: str = "?",
) -> tuple:
    """
    Run H037b IBS strategy on a single sector's OHLC DataFrame.

    - capital_fraction: fraction of INITIAL_EQUITY allocated to this sector.
    - Returns: (daily_returns pd.Series, trades list)

    daily_returns is indexed by trading date, values are the sector P&L
    as a fraction of INITIAL_EQUITY (not just the sector slice).
    This lets us add returns across sectors for the portfolio.
    """
    dates    = list(df.index)
    opens    = df["open"].values
    closes   = df["close"].values
    ibs_v    = df["ibs"].values
    gap_v    = df["gap"].values
    n        = len(df)

    equity   = INITIAL_EQUITY * capital_fraction  # just for tracking
    position = 0
    days_held = 0
    entry_open = 0.0
    entry_idx  = 0

    daily_pnl = []   # (date, portfolio_return_fraction)
    trades    = []

    for i in range(1, n):
        date     = dates[i]
        prev_ibs = ibs_v[i - 1]
        cur_ibs  = ibs_v[i]
        gap      = gap_v[i]
        o        = opens[i]
        c        = closes[i]
        c_prev   = closes[i - 1]

        ret_oc = c / o - 1 if o > 0 else 0.0
        ret_cc = c / c_prev - 1 if c_prev > 0 else 0.0

        day_ret_sector = 0.0  # sector's return this day

        if position == 0:
            if prev_ibs < IBS_BUY and gap >= GAP_FILTER:
                position   = 1
                days_held  = 1
                entry_open = o
                entry_idx  = i
                day_ret_sector = ret_oc
                equity    *= (1 + ret_oc)
        else:
            days_held += 1
            day_ret_sector = ret_cc
            equity    *= (1 + ret_cc)

            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                total_ret = float(closes[i]) / float(opens[entry_idx]) - 1
                trades.append({
                    "ticker":        label,
                    "date_entry":    str(dates[entry_idx].date()),
                    "date_exit":     str(date.date()),
                    "days_held":     days_held,
                    "gap_pct":       round(float(gap_v[entry_idx]) * 100, 4),
                    "prev_ibs":      round(float(ibs_v[entry_idx - 1]), 4),
                    "entry_open":    round(float(opens[entry_idx]), 4),
                    "exit_close":    round(float(c), 4),
                    "trade_ret_pct": round(total_ret * 100, 4),
                    "win":           int(total_ret > 0),
                    "exit_reason":   "ibs" if cur_ibs > IBS_SELL else "maxhold",
                })
                position  = 0
                days_held = 0

        # Convert sector return to portfolio return (scaled by capital_fraction)
        daily_pnl.append((date, day_ret_sector * capital_fraction))

    series = pd.Series(
        [v for _, v in daily_pnl],
        index=pd.DatetimeIndex([d for d, _ in daily_pnl]),
        name=label,
    )
    return series, trades


# ─────────────────────────────────────────────────────────────────────────────
# H026 momentum ranking (for H046b)
# ─────────────────────────────────────────────────────────────────────────────

def build_h026_monthly_top3(closes: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """
    For each month-end, rank the 11 sector ETFs by:
        score = rank(12m_mom) + rank(inv_6m_vol)
    Return top 3 for the NEXT month.
    Returns a DataFrame indexed by month-start date → list of top-3 tickers.
    """
    # resample to month-end
    mth_close = closes.resample("ME").last()

    mom_12m   = mth_close.pct_change(12)
    vol_6m_daily = closes.pct_change().rolling(126).std() * math.sqrt(252)
    vol_6m_mth   = vol_6m_daily.resample("ME").last()

    rankings = {}
    for dt in mth_close.index:
        m = mom_12m.loc[dt]
        v = vol_6m_mth.loc[dt]
        valid = m.dropna().index.intersection(v.dropna().index)
        if len(valid) < 3:
            continue
        m_r = m[valid].rank(ascending=True)
        v_r = v[valid].rank(ascending=False)  # lower vol = higher rank
        score = m_r + v_r
        top3  = list(score.nlargest(3).index)
        rankings[dt] = top3

    # Convert to dict: next-month first day → top3 list
    monthly_map = {}
    sorted_keys = sorted(rankings.keys())
    for i, dt in enumerate(sorted_keys):
        if i + 1 < len(sorted_keys):
            next_start = sorted_keys[i + 1]
        else:
            next_start = pd.Timestamp(end)
        monthly_map[next_start] = rankings[dt]

    return monthly_map


# ─────────────────────────────────────────────────────────────────────────────
# H046: 5-sector multi-IBS backtest
# ─────────────────────────────────────────────────────────────────────────────

def run_h046(ohlc_data: dict, start: str, end: str) -> tuple:
    """
    Run H046: apply H037b rules to each of the 5 sectors simultaneously.
    Each sector gets 20% of capital (capital_fraction = 0.20).
    Portfolio daily return = sum of sector daily returns.
    """
    n_sectors        = len(SECTOR_ETFS_5)
    cap_frac         = 1.0 / n_sectors  # 20% each
    portfolio_series = {}
    all_trades       = []

    for ticker in SECTOR_ETFS_5:
        df_raw  = ohlc_data[ticker]
        df_feat = build_features(df_raw)
        df_win  = df_feat.loc[start:end]
        if df_win.empty:
            print(f"  WARNING: {ticker} has no data in {start}:{end}")
            continue
        series, trades = run_ibs_on_sector(df_win, cap_frac, ticker)
        portfolio_series[ticker] = series
        all_trades.extend(trades)

    # Align all series to common date index (union)
    port_df = pd.DataFrame(portfolio_series).fillna(0.0)
    port_daily_ret = port_df.sum(axis=1)  # portfolio-level daily return

    # Build equity curve
    equity = INITIAL_EQUITY * (1 + port_daily_ret).cumprod()

    return equity, port_daily_ret, all_trades, portfolio_series


# ─────────────────────────────────────────────────────────────────────────────
# H046b: dynamic top-3 momentum sectors with IBS
# ─────────────────────────────────────────────────────────────────────────────

def run_h046b(ohlc_data: dict, close_prices: pd.DataFrame, start: str, end: str) -> tuple:
    """
    H046b: apply H037b rules to H026 top-3 momentum sectors.
    Each of the 3 active sectors gets 33.3% of capital.
    The active set changes monthly.
    """
    # Build monthly top-3 map
    monthly_top3 = build_h026_monthly_top3(close_prices, start, end)

    # Build per-sector feature DataFrames
    sector_features = {}
    for t in SECTOR_ETFS_5:  # only use the 5 from H046 universe
        df_raw  = ohlc_data[t]
        df_feat = build_features(df_raw)
        sector_features[t] = df_feat.loc[start:end]

    # Build a common trading calendar
    all_dates = sorted(set().union(*[df.index for df in sector_features.values()]))
    all_dates = [d for d in all_dates if pd.Timestamp(start) <= d <= pd.Timestamp(end)]

    # Track positions per sector (independent state machines)
    positions  = {t: 0  for t in SECTOR_ETFS_5}
    days_held  = {t: 0  for t in SECTOR_ETFS_5}
    entry_open = {t: 0.0 for t in SECTOR_ETFS_5}
    entry_date = {t: None for t in SECTOR_ETFS_5}
    entry_ibs  = {t: 0.0 for t in SECTOR_ETFS_5}

    # Active sectors for the current month
    current_top3 = []
    daily_pnl    = []
    all_trades   = []
    cap_frac     = 1.0 / 3.0  # 33.3% each when active

    for i, date in enumerate(all_dates):
        # Update active sectors at month boundary (use last known top-3)
        # Find the most recent monthly signal on or before this date
        relevant = [k for k in sorted(monthly_top3.keys()) if k <= date]
        if relevant:
            current_top3 = monthly_top3[relevant[-1]]
            # Restrict to sectors we have OHLC data for
            current_top3 = [t for t in current_top3 if t in sector_features]

        day_total_ret = 0.0

        for t in SECTOR_ETFS_5:
            df = sector_features[t]
            if date not in df.index:
                continue

            loc_i = df.index.get_loc(date)
            if loc_i < 1:
                continue

            prev_ibs_val = float(df["ibs"].iloc[loc_i - 1])
            cur_ibs_val  = float(df["ibs"].iloc[loc_i])
            gap_val      = float(df["gap"].iloc[loc_i])
            o            = float(df["open"].iloc[loc_i])
            c            = float(df["close"].iloc[loc_i])
            c_prev       = float(df["prev_close"].iloc[loc_i])

            ret_oc = c / o - 1 if o > 0 else 0.0
            ret_cc = c / c_prev - 1 if c_prev > 0 else 0.0

            sector_ret = 0.0

            if positions[t] == 0:
                # Only enter if this sector is in the current top-3
                if t in current_top3 and prev_ibs_val < IBS_BUY and gap_val >= GAP_FILTER:
                    positions[t]  = 1
                    days_held[t]  = 1
                    entry_open[t] = o
                    entry_date[t] = date
                    entry_ibs[t]  = prev_ibs_val
                    sector_ret    = ret_oc
            else:
                days_held[t] += 1
                sector_ret    = ret_cc

                if cur_ibs_val > IBS_SELL or days_held[t] >= MAX_HOLD:
                    total_ret = c / entry_open[t] - 1
                    all_trades.append({
                        "ticker":        t,
                        "date_entry":    str(entry_date[t].date()),
                        "date_exit":     str(date.date()),
                        "days_held":     days_held[t],
                        "prev_ibs":      round(entry_ibs[t], 4),
                        "entry_open":    round(entry_open[t], 4),
                        "exit_close":    round(c, 4),
                        "trade_ret_pct": round(total_ret * 100, 4),
                        "win":           int(total_ret > 0),
                        "exit_reason":   "ibs" if cur_ibs_val > IBS_SELL else "maxhold",
                    })
                    positions[t]  = 0
                    days_held[t]  = 0

            day_total_ret += sector_ret * cap_frac

        daily_pnl.append((date, day_total_ret))

    port_daily_ret = pd.Series(
        [v for _, v in daily_pnl],
        index=pd.DatetimeIndex([d for d, _ in daily_pnl]),
        name="h046b",
    )
    equity = INITIAL_EQUITY * (1 + port_daily_ret).cumprod()
    return equity, port_daily_ret, all_trades


# ─────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(eq: pd.Series, trades: list, label: str) -> dict:
    if eq.empty or len(eq) < 2:
        return {"period": label, "error": "insufficient data"}

    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr    = (eq.iloc[-1] / INITIAL_EQUITY) ** (1.0 / n_years) - 1 if n_years > 0 else 0.0

    daily_rets = eq.pct_change().dropna()
    sharpe = float(daily_rets.mean() / daily_rets.std() * math.sqrt(252)) if daily_rets.std() > 0 else 0.0

    roll_max = eq.expanding().max()
    max_dd   = float((eq / roll_max - 1).min())

    n_trades = len(trades)
    if n_trades > 0:
        wins     = sum(t["win"] for t in trades)
        win_rate = wins / n_trades
        avg_ret  = sum(t["trade_ret_pct"] for t in trades) / n_trades
    else:
        win_rate = avg_ret = 0.0

    return {
        "period":            label,
        "n_years":           round(n_years, 1),
        "cagr_pct":          round(float(cagr) * 100, 3),
        "sharpe":            round(sharpe, 4),
        "max_dd_pct":        round(max_dd * 100, 3),
        "n_trades":          n_trades,
        "trades_per_year":   round(n_trades / n_years, 1) if n_years > 0 else 0,
        "win_rate_pct":      round(win_rate * 100, 2),
        "avg_trade_ret_pct": round(avg_ret, 4),
        "final_equity":      round(float(eq.iloc[-1]), 2),
    }


def per_sector_stats(trades: list, sectors: list) -> dict:
    out = {}
    for t in sectors:
        t_trades = [tr for tr in trades if tr["ticker"] == t]
        n = len(t_trades)
        if n == 0:
            out[t] = {"n_trades": 0}
            continue
        wins    = sum(tr["win"] for tr in t_trades)
        avg_ret = sum(tr["trade_ret_pct"] for tr in t_trades) / n
        out[t] = {
            "n_trades":          n,
            "win_rate_pct":      round(wins / n * 100, 2),
            "avg_trade_ret_pct": round(avg_ret, 4),
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Correlation analysis
# ─────────────────────────────────────────────────────────────────────────────

def monthly_returns_from_daily(daily_ret: pd.Series) -> pd.Series:
    """Convert daily return series to monthly returns."""
    equity = (1 + daily_ret).cumprod()
    monthly = equity.resample("ME").last().pct_change().dropna()
    return monthly


def correlation_analysis(
    h046_daily: pd.Series,
    h037b_daily: pd.Series,
) -> dict:
    """Compute monthly return correlation between H046 and H037b."""
    m046  = monthly_returns_from_daily(h046_daily)
    m037b = monthly_returns_from_daily(h037b_daily)

    # Align
    common = m046.index.intersection(m037b.index)
    m046_a  = m046.loc[common]
    m037b_a = m037b.loc[common]

    corr = float(m046_a.corr(m037b_a))
    return {
        "correlation_monthly": round(corr, 4),
        "n_months": len(common),
        "interpretation": (
            "low (<0.4)"   if abs(corr) < 0.4 else
            "medium (0.4–0.7)" if abs(corr) < 0.7 else
            "high (>0.7)"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Blend analysis: H046 + H042 components
# ─────────────────────────────────────────────────────────────────────────────

def monthly_equity_series(daily_ret: pd.Series, initial: float = INITIAL_EQUITY) -> pd.Series:
    """Build monthly equity series from daily return series."""
    eq = initial * (1 + daily_ret).cumprod()
    return eq.resample("ME").last()


def run_blend_analysis(
    h046_daily: pd.Series,
    h037b_spy_daily: pd.Series,
    h042_ref_sharpe: float = 1.9492,
    h042_ref_cagr:   float = 0.1449,
) -> dict:
    """
    Test: what happens if we replace H037b (SPY) in H042 with H046?
    Blend: H041a (56%) + H026 (16%) + H046 (28%)  [same weights as H042 optimal]

    Since we don't have H041a and H026 equity curves here, we approximate:
    - Compute monthly correlation of H046 vs H037b
    - Show the Sharpe of H046 alone vs H037b alone
    - Show what blending H046 into a portfolio should do

    For a rigorous 4-way blend we'd need all 4 components aligned.
    Here we focus on the correlation impact.
    """
    # Monthly returns
    m046  = monthly_returns_from_daily(h046_daily)
    m037b = monthly_returns_from_daily(h037b_spy_daily)

    common = m046.index.intersection(m037b.index)
    m046_a  = m046.loc[common]
    m037b_a = m037b.loc[common]

    corr   = float(m046_a.corr(m037b_a))
    n_months = len(common)
    n_years  = n_months / 12

    # Sharpe of a 50/50 blend of H046 + H037b (monthly resampled)
    blend_50_50 = 0.5 * m046_a + 0.5 * m037b_a
    sh_046  = float(m046_a.mean() / m046_a.std() * math.sqrt(12))
    sh_037b = float(m037b_a.mean() / m037b_a.std() * math.sqrt(12))
    sh_blend = float(blend_50_50.mean() / blend_50_50.std() * math.sqrt(12))

    cagr_046  = (1 + m046_a).prod() ** (1 / n_years) - 1
    cagr_037b = (1 + m037b_a).prod() ** (1 / n_years) - 1
    cagr_blend = (1 + blend_50_50).prod() ** (1 / n_years) - 1

    return {
        "correlation_monthly": round(corr, 4),
        "n_months": n_months,
        "monthly_sharpe_h046":  round(sh_046, 4),
        "monthly_sharpe_h037b": round(sh_037b, 4),
        "monthly_sharpe_50_50_blend": round(sh_blend, 4),
        "cagr_h046_pct":  round(float(cagr_046) * 100, 3),
        "cagr_h037b_pct": round(float(cagr_037b) * 100, 3),
        "cagr_blend_pct": round(float(cagr_blend) * 100, 3),
        "blend_benefit": round(sh_blend - max(sh_046, sh_037b), 4),
        "note": (
            "Positive blend_benefit means H046 adds diversification value. "
            "For full H042 4-way blend, run_h047 would be needed."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H037b SPY daily return series (for correlation)
# ─────────────────────────────────────────────────────────────────────────────

def run_h037b_spy(df: pd.DataFrame, start: str, end: str) -> pd.Series:
    """Re-run H037b on SPY to get daily return series aligned to analysis window."""
    df_feat = build_features(df)
    df_win  = df_feat.loc[start:end]

    dates    = list(df_win.index)
    opens    = df_win["open"].values
    closes   = df_win["close"].values
    ibs_v    = df_win["ibs"].values
    gap_v    = df_win["gap"].values
    n        = len(df_win)

    position  = 0
    days_held = 0
    entry_open = 0.0

    daily_ret = []

    for i in range(1, n):
        prev_ibs = ibs_v[i - 1]
        cur_ibs  = ibs_v[i]
        gap      = gap_v[i]
        o        = opens[i]
        c        = closes[i]
        c_prev   = closes[i - 1]

        ret_oc = c / o - 1 if o > 0 else 0.0
        ret_cc = c / c_prev - 1 if c_prev > 0 else 0.0
        day_ret = 0.0

        if position == 0:
            if prev_ibs < IBS_BUY and gap >= GAP_FILTER:
                position   = 1
                days_held  = 1
                entry_open = o
                day_ret    = ret_oc
        else:
            days_held += 1
            day_ret    = ret_cc
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0

        daily_ret.append((dates[i], day_ret))

    return pd.Series(
        [v for _, v in daily_ret],
        index=pd.DatetimeIndex([d for d, _ in daily_ret]),
        name="h037b_spy",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H046 — Multi-Sector IBS Mean-Reversion")
    print("=" * 72)

    # ── 1. Download data ──────────────────────────────────────────────────────
    print("\n[1] Fetching OHLC for 5 sector ETFs + SPY …")
    all_tickers = SECTOR_ETFS_5 + ["SPY"]
    ohlc_data   = fetch_ohlc(all_tickers, DATA_START, FULL_END)

    print("\n[2] Fetching close prices for H046b (momentum ranking, 11 sectors + SPY) …")
    close_prices = fetch_close_prices(
        SECTOR_ETFS_5 + ["SPY"],  # only need 5 sectors for H046b
        DATA_START, FULL_END
    )

    # ── 2. Run H046 full period ───────────────────────────────────────────────
    print(f"\n[3] Running H046 (5-sector multi-IBS) {FULL_START} → {FULL_END} …")
    eq46_full, ret46_full, trades46_full, per_sector_ret = run_h046(
        ohlc_data, FULL_START, FULL_END
    )
    stats46_full = compute_stats(eq46_full, trades46_full, f"Full {FULL_START}–{FULL_END}")

    print(f"\n[4] Running H046 OOS {OOS_START} → {FULL_END} …")
    eq46_oos, ret46_oos, trades46_oos, _ = run_h046(
        ohlc_data, OOS_START, FULL_END
    )
    stats46_oos = compute_stats(eq46_oos, trades46_oos, f"OOS {OOS_START}–{FULL_END}")

    # Per-sector trade stats (full period)
    sector_stats = per_sector_stats(trades46_full, SECTOR_ETFS_5)

    print(f"\n[5] Running H046b (top-3 momentum + IBS) {FULL_START} → {FULL_END} …")
    eq46b_full, ret46b_full, trades46b_full = run_h046b(
        ohlc_data, close_prices, FULL_START, FULL_END
    )
    stats46b_full = compute_stats(eq46b_full, trades46b_full, f"Full {FULL_START}–{FULL_END}")

    print(f"\n[6] Running H046b OOS {OOS_START} → {FULL_END} …")
    eq46b_oos, ret46b_oos, trades46b_oos = run_h046b(
        ohlc_data, close_prices, OOS_START, FULL_END
    )
    stats46b_oos = compute_stats(eq46b_oos, trades46b_oos, f"OOS {OOS_START}–{FULL_END}")

    # ── 3. H037b SPY for correlation ──────────────────────────────────────────
    print(f"\n[7] Running H037b (SPY) for correlation baseline …")
    spy_df     = ohlc_data["SPY"]
    ret037b_full = run_h037b_spy(spy_df, FULL_START, FULL_END)

    # ── 4. Correlation H046 vs H037b ─────────────────────────────────────────
    print(f"\n[8] Correlation analysis …")
    corr_h046_vs_037b  = correlation_analysis(ret46_full,  ret037b_full)
    corr_h046b_vs_037b = correlation_analysis(ret46b_full, ret037b_full)

    # ── 5. Blend analysis ─────────────────────────────────────────────────────
    print(f"\n[9] Blend analysis (H046 vs H037b) …")
    blend_h046  = run_blend_analysis(ret46_full,  ret037b_full)
    blend_h046b = run_blend_analysis(ret46b_full, ret037b_full)

    # ── 6. Print summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 90)
    print("  H046 SUMMARY")
    print("=" * 90)

    for label, s in [
        ("H046 Full",  stats46_full),
        ("H046 OOS",   stats46_oos),
        ("H046b Full", stats46b_full),
        ("H046b OOS",  stats46b_oos),
    ]:
        print(f"\n  {label}:")
        print(f"    CAGR {s['cagr_pct']:.2f}%  Sharpe {s['sharpe']:.4f}"
              f"  MaxDD {s['max_dd_pct']:.2f}%  Trades {s['n_trades']}"
              f"  WinRate {s['win_rate_pct']:.1f}%  AvgPnL {s['avg_trade_ret_pct']:.4f}%")

    print("\n  Per-Sector Stats (H046, Full Period):")
    print(f"  {'Sector':<8}  {'Trades':>7}  {'WinRate%':>9}  {'AvgPnL%':>9}")
    print("  " + "-" * 38)
    for t in SECTOR_ETFS_5:
        s = sector_stats.get(t, {})
        n = s.get("n_trades", 0)
        wr = s.get("win_rate_pct", 0.0)
        ar = s.get("avg_trade_ret_pct", 0.0)
        print(f"  {t:<8}  {n:>7}  {wr:>9.2f}  {ar:>9.4f}")

    print(f"\n  Correlation H046 vs H037b (SPY): {corr_h046_vs_037b['correlation_monthly']:.4f}"
          f"  ({corr_h046_vs_037b['interpretation']})")
    print(f"  Correlation H046b vs H037b (SPY): {corr_h046b_vs_037b['correlation_monthly']:.4f}"
          f"  ({corr_h046b_vs_037b['interpretation']})")

    print(f"\n  Blend analysis (H046 replacing H037b as 50/50 blend):")
    print(f"    H046  monthly Sharpe: {blend_h046['monthly_sharpe_h046']:.4f}")
    print(f"    H037b monthly Sharpe: {blend_h046['monthly_sharpe_h037b']:.4f}")
    print(f"    50/50 blend Sharpe:   {blend_h046['monthly_sharpe_50_50_blend']:.4f}")
    print(f"    Blend benefit: {blend_h046['blend_benefit']:+.4f}")

    # ── 7. Save results ───────────────────────────────────────────────────────
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)): return float(obj)
        if isinstance(obj, (np.bool_,)):   return bool(obj)
        return str(obj)

    output = {
        "strategy":    "H046 — Multi-Sector IBS Mean-Reversion",
        "hypothesis":  (
            "The H009/H037b IBS oversold-bounce effect is not SPY-specific. "
            "Sector ETFs (XLK, XLE, XLF, XLV, XLI) should respond similarly. "
            "Trading multiple sectors simultaneously creates more trade opportunities "
            "with potentially lower correlation to H037b (SPY-only)."
        ),
        "rules": {
            "H046":  "H037b applied to XLK, XLE, XLF, XLV, XLI equally; 20% capital each; positions can overlap",
            "H046b": "H037b applied to H026 top-3 momentum sectors only; 33.3% each; updated monthly",
            "entry": "prev IBS < 0.20 AND gap >= -0.5% → buy at open",
            "exit":  "IBS > 0.80 OR held >= 5 days → exit at close",
        },
        "periods": {
            "full": f"{FULL_START} → {FULL_END}",
            "oos":  f"{OOS_START} → {FULL_END}",
        },
        "H046": {
            "full_period":     stats46_full,
            "oos_period":      stats46_oos,
            "per_sector_stats_full": sector_stats,
            "n_total_trades_full": len(trades46_full),
        },
        "H046b": {
            "full_period":     stats46b_full,
            "oos_period":      stats46b_oos,
            "per_sector_stats_full": per_sector_stats(trades46b_full, SECTOR_ETFS_5),
            "n_total_trades_full": len(trades46b_full),
        },
        "correlation_vs_h037b_spy": {
            "H046":  corr_h046_vs_037b,
            "H046b": corr_h046b_vs_037b,
        },
        "blend_analysis": {
            "H046":  blend_h046,
            "H046b": blend_h046b,
        },
        "H037b_reference": {
            "description": "H037b SPY-only (from h037_results.json)",
            "full_period_sharpe": 1.0207,
            "full_period_cagr_pct": 12.022,
            "full_period_max_dd_pct": -23.045,
            "full_period_n_trades": 623,
            "full_period_win_rate_pct": 65.33,
        },
        "H042_reference": {
            "description": "H042 optimal blend: H041a(56%) + H026(16%) + H037b(28%)",
            "sharpe": 1.9492,
            "cagr_pct": 14.49,
            "max_dd_pct": -9.02,
        },
        "run_date": FULL_END,
    }

    out_path = RESULTS_DIR / "h046_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=_json_safe))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
