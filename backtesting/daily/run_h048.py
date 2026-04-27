"""
H048 — XLK IBS Mean-Reversion (H048a) and Sell-in-May Seasonality on H042 (H048b)
===================================================================================

H048a — XLK-only IBS Mean-Reversion
  Apply H037b rules to XLK (Technology ETF):
    Buy when prev IBS < 0.20 AND gap > -0.5%
    Sell when IBS > 0.80 OR held >= 5 days
    Position size: 100% of allocated capital
  Period: 2000-2026
  Metrics: CAGR, Sharpe, MaxDD, win rate, trade count
  Extra: correlation of H048a daily returns to H037b (SPY IBS)
  Compare to XLK buy-and-hold and H037b (SPY IBS)

H048b — "Sell in May" Calendar Seasonality on H042
  Variant 1: reduce H042 equity exposure by 50% in May-Oct, hold SHY for the other 50%
  Variant 2: go 100% SHY in May-Oct (hard switch)
  Variant 3: only apply in years where April momentum signal is negative (conditional)
  Period: 2003-2026
  Metrics: CAGR, Sharpe, MaxDD vs H042 baseline
  Sub-period analysis: pre-2015 vs post-2015

Outputs:
  /workspace/agent/backtesting/results/h048_results.json
  /workspace/agent/backtesting/daily/run_h048.py  (this file)
"""

import json
import math
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

DATA_START   = "2000-01-01"
FULL_END     = "2026-04-27"
H048B_START  = "2003-01-01"

# H037b / H048a parameters
IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5
GAP_FILTER = -0.005   # skip entry if gap < -0.5%

# H042 asset universes (replicated here for H048b seasonality layer)
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
SECTOR_ETFS  = ["XLK", "XLE", "XLF", "XLV", "XLI",
                "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
TOP_N_H41A = 2
TOP_N_H26  = 3

# H042 optimal weights (from h042_results.json)
W_H041A = 0.50
W_H026  = 0.20
W_H037B = 0.30


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker: str, start: str, end: str) -> pd.DataFrame:
    tag = f"h048_{ticker}_ohlc_{start}_{end}"
    h   = hashlib.md5(tag.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h048_{ticker.lower()}_{h}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        print(f"  Loaded {ticker} OHLC from cache ({len(df)} rows)")
        return df

    # Try to reuse existing SPY caches
    if ticker == "SPY":
        for fname in [
            f"h031_spy_ohlc_{start}_{end}.parquet",
            f"h042_spy_ohlc_{start}_{end}.parquet",
        ]:
            cp2 = CACHE_DIR / fname
            if cp2.exists():
                df = pd.read_parquet(cp2)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df = df.rename(columns=str.lower)
                if not all(c in df.columns for c in ["open", "high", "low", "close"]):
                    continue
                print(f"  Loaded {ticker} OHLC from existing cache ({len(df)} rows)")
                return df

    print(f"  Downloading {ticker} OHLC {start} → {end} …")
    raw = yf.download([ticker], start=start, end=end,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]]
    else:
        df = raw[["Open", "High", "Low", "Close"]]
    df = df.rename(columns=str.lower).dropna()
    df.index = pd.to_datetime(df.index)
    df.to_parquet(cp)
    print(f"  Downloaded and cached ({len(df)} rows)")
    return df


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h048_{tag}_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)

    # Try to reuse h042 cache
    for fname in CACHE_DIR.glob("h042_*.parquet"):
        try:
            df = pd.read_parquet(fname)
            if all(t in df.columns for t in tickers):
                print(f"  Reusing h042 price cache for {len(tickers)} tickers")
                return df
        except Exception:
            pass

    print(f"  Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end,
                      auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def build_ibs_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add ibs and gap columns (no look-ahead)."""
    df = df.copy()
    denom        = (df["high"] - df["low"]).replace(0, np.nan)
    df["ibs"]    = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0)
    df["prev_cl"] = df["close"].shift(1)
    df["gap"]    = (df["open"] - df["prev_cl"]) / df["prev_cl"]
    return df.dropna(subset=["prev_cl", "ibs", "gap"])


# ─────────────────────────────────────────────────────────────────────────────
# IBS mean-reversion engine (H037b rules)
# ─────────────────────────────────────────────────────────────────────────────

def run_ibs_strategy(df: pd.DataFrame, label: str = "IBS") -> tuple:
    """
    Run H037b IBS mean-reversion rules on any OHLC DataFrame.
    Returns: (equity_series, daily_returns_series, trades_list)
    """
    dates      = list(df.index)
    opens      = df["open"].values
    closes     = df["close"].values
    ibs_vals   = df["ibs"].values
    gap_vals   = df["gap"].values
    n          = len(df)

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    entry_idx = 0

    equity_list = []
    daily_rets  = []
    trades      = []

    for i in range(1, n):
        date     = dates[i]
        prev_ibs = ibs_vals[i - 1]
        cur_ibs  = ibs_vals[i]
        gap      = gap_vals[i]
        o        = opens[i]
        c        = closes[i]
        c_prev   = closes[i - 1]

        ret_oc = c / o - 1     if o > 0     else 0.0
        ret_cc = c / c_prev - 1 if c_prev > 0 else 0.0

        if position == 0:
            if prev_ibs < IBS_BUY and gap >= GAP_FILTER:
                position  = 1
                days_held = 1
                entry_idx = i
                equity   *= (1 + ret_oc)
                daily_rets.append(ret_oc)
            else:
                daily_rets.append(0.0)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            daily_rets.append(ret_cc)

            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                total_ret = float(closes[i]) / float(opens[entry_idx]) - 1
                trades.append({
                    "date_entry":    str(dates[entry_idx].date()),
                    "date_exit":     str(date.date()),
                    "days_held":     days_held,
                    "gap_pct":       round(float(gap_vals[entry_idx]) * 100, 4),
                    "prev_ibs":      round(float(ibs_vals[entry_idx - 1]), 4),
                    "trade_ret_pct": round(total_ret * 100, 4),
                    "win":           int(total_ret > 0),
                    "exit_reason":   "ibs" if cur_ibs > IBS_SELL else "maxhold",
                })
                position  = 0
                days_held = 0

        equity_list.append((date, equity))

    eq = pd.Series(
        [v for _, v in equity_list],
        index=pd.DatetimeIndex([d for d, _ in equity_list]),
        name="equity",
    )
    dr = pd.Series(
        daily_rets,
        index=pd.DatetimeIndex([d for d, _ in equity_list]),
        name="daily_ret",
    )
    return eq, dr, trades


def compute_ibs_stats(eq: pd.Series, trades: list, label: str,
                      n_years_override: float | None = None) -> dict:
    if eq.empty or len(eq) < 2:
        return {"period": label, "error": "insufficient data"}

    n_years = n_years_override if n_years_override is not None else len(eq) / 252.0
    cagr = (eq.iloc[-1] / INITIAL_EQUITY) ** (1.0 / n_years) - 1 if n_years > 0 else 0.0

    daily_rets = eq.pct_change().dropna()
    if len(daily_rets) > 1 and daily_rets.std() > 0:
        sharpe = float(daily_rets.mean() / daily_rets.std() * math.sqrt(252))
    else:
        sharpe = 0.0

    roll_max = eq.expanding().max()
    max_dd   = float((eq / roll_max - 1).min())

    n_trades = len(trades)
    if n_trades > 0:
        wins     = sum(t["win"] for t in trades)
        win_rate = wins / n_trades
        avg_ret  = sum(t["trade_ret_pct"] for t in trades) / n_trades
    else:
        win_rate = 0.0
        avg_ret  = 0.0

    trades_per_year = n_trades / n_years if n_years > 0 else 0.0

    return {
        "period":            label,
        "n_years":           round(n_years, 1),
        "cagr_pct":          round(float(cagr) * 100, 3),
        "sharpe":            round(sharpe, 4),
        "max_dd_pct":        round(max_dd * 100, 3),
        "n_trades":          n_trades,
        "trades_per_year":   round(trades_per_year, 1),
        "win_rate_pct":      round(win_rate * 100, 2),
        "avg_trade_ret_pct": round(avg_ret, 4),
        "final_equity":      round(float(eq.iloc[-1]), 2),
    }


def bnh_stats(df_ohlc: pd.DataFrame, start: str, end: str, label: str) -> dict:
    """Buy-and-hold stats for a given ticker."""
    df = df_ohlc.loc[start:end]
    if df.empty:
        return {"label": label, "error": "no data"}
    total_ret = float(df["close"].iloc[-1]) / float(df["close"].iloc[0]) - 1
    n_years   = len(df) / 252.0
    cagr      = (1 + total_ret) ** (1 / n_years) - 1 if n_years > 0 else 0.0
    daily_rets = df["close"].pct_change().dropna()
    sharpe     = float(daily_rets.mean() / daily_rets.std() * math.sqrt(252)) if daily_rets.std() > 0 else 0.0
    roll_max   = (1 + daily_rets).cumprod().expanding().max()
    cum        = (1 + daily_rets).cumprod()
    max_dd     = float((cum / roll_max - 1).min())
    return {
        "label":      label,
        "cagr_pct":   round(float(cagr) * 100, 3),
        "sharpe":     round(sharpe, 4),
        "max_dd_pct": round(max_dd * 100, 3),
        "n_years":    round(n_years, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H042 equity curve reconstruction (for H048b seasonality overlay)
# ─────────────────────────────────────────────────────────────────────────────

def h041a_monthly_returns(prices: pd.DataFrame) -> pd.Series:
    available = [a for a in H041A_ASSETS if a in prices.columns]
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H41A
    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H41A:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H41A).index)
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


def h026_monthly_returns(prices: pd.DataFrame) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H26
    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H26:
            continue
        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N_H26).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
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


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# H048b: Seasonality variants on H042 daily returns
# ─────────────────────────────────────────────────────────────────────────────

def h042_daily_equity(prices: pd.DataFrame, spy_ohlc: pd.DataFrame,
                      shy_daily: pd.Series,
                      start: str, end: str) -> pd.Series:
    """
    Reconstruct H042 as a *daily* equity curve by blending:
      W_H041A * h041a_daily + W_H026 * h026_daily + W_H037B * h037b_daily
    Monthly strategies are held between rebalance dates (daily marks-to-market).
    """
    # 1. Build h037b daily equity (already daily)
    df_spy = spy_ohlc.loc[start:end].copy()
    df_spy_feat = build_ibs_features(df_spy)
    eq_h037b, dr_h037b, _ = run_ibs_strategy(df_spy_feat, "H037b")

    # 2. Build h041a daily equity from the equity series
    eq_h041a = h041a_monthly_returns(prices.loc[start:end])
    eq_h041a = eq_h041a.loc[start:end]

    # 3. Build h026 daily equity
    eq_h026 = h026_monthly_returns(prices.loc[start:end])
    eq_h026 = eq_h026.loc[start:end]

    # 4. Align to a common daily index
    common_days = eq_h037b.index.intersection(eq_h041a.index).intersection(eq_h026.index)
    eq_h041a_c = eq_h041a.loc[common_days]
    eq_h026_c  = eq_h026.loc[common_days]
    eq_h037b_c = eq_h037b.loc[common_days]

    # Convert each to daily returns (relative to INITIAL_EQUITY)
    dr_h041a = eq_h041a_c.pct_change().fillna(0)
    dr_h026  = eq_h026_c.pct_change().fillna(0)
    dr_h037b = eq_h037b_c.pct_change().fillna(0)

    # Blend
    blend_dr = W_H041A * dr_h041a + W_H026 * dr_h026 + W_H037B * dr_h037b

    # Build equity
    eq = INITIAL_EQUITY * (1 + blend_dr).cumprod()
    return eq.rename("h042_equity")


def apply_sell_in_may_v1(dr_h042: pd.Series, dr_shy: pd.Series,
                          common_idx: pd.DatetimeIndex) -> pd.Series:
    """
    Variant 1: 50% equity, 50% SHY during May-Oct; 100% equity rest of year.
    """
    dr_h042 = dr_h042.loc[common_idx]
    dr_shy  = dr_shy.reindex(common_idx, fill_value=0.0)
    may_oct = dr_h042.index.month.isin([5, 6, 7, 8, 9, 10])
    blended = dr_h042.copy()
    blended[may_oct] = 0.5 * dr_h042[may_oct] + 0.5 * dr_shy[may_oct]
    return blended


def apply_sell_in_may_v2(dr_h042: pd.Series, dr_shy: pd.Series,
                          common_idx: pd.DatetimeIndex) -> pd.Series:
    """
    Variant 2: 100% SHY during May-Oct; 100% equity rest of year.
    """
    dr_h042 = dr_h042.loc[common_idx]
    dr_shy  = dr_shy.reindex(common_idx, fill_value=0.0)
    may_oct = dr_h042.index.month.isin([5, 6, 7, 8, 9, 10])
    blended = dr_h042.copy()
    blended[may_oct] = dr_shy[may_oct]
    return blended


def apply_sell_in_may_v3(dr_h042: pd.Series, dr_shy: pd.Series,
                          prices: pd.DataFrame,
                          common_idx: pd.DatetimeIndex) -> pd.Series:
    """
    Variant 3: apply Variant 2 only in years where April momentum is negative.
    April momentum = SPY return in April (previous 1-month return).
    """
    # SPY monthly return in April
    spy_month = prices["SPY"].resample("ME").last().pct_change() if "SPY" in prices.columns else None
    if spy_month is None:
        return apply_sell_in_may_v2(dr_h042, dr_shy, common_idx)

    april_rets = spy_month[spy_month.index.month == 4]
    negative_april_years = set(april_rets[april_rets < 0].index.year)

    dr_h042 = dr_h042.loc[common_idx]
    dr_shy  = dr_shy.reindex(common_idx, fill_value=0.0)
    blended = dr_h042.copy()

    for date in blended.index:
        if date.month in [5, 6, 7, 8, 9, 10] and date.year in negative_april_years:
            blended[date] = dr_shy.get(date, 0.0)

    return blended


def equity_stats_from_daily_returns(dr: pd.Series, label: str,
                                     start: str | None = None,
                                     end: str | None = None) -> dict:
    dr = dr.dropna()
    if start:
        dr = dr.loc[start:]
    if end:
        dr = dr.loc[:end]
    if dr.empty or len(dr) < 2:
        return {"label": label, "error": "insufficient data"}

    eq = INITIAL_EQUITY * (1 + dr).cumprod()
    n_years = len(dr) / 252.0
    cagr  = (eq.iloc[-1] / INITIAL_EQUITY) ** (1.0 / n_years) - 1 if n_years > 0 else 0.0
    sharpe = float(dr.mean() / dr.std() * math.sqrt(252)) if dr.std() > 0 else 0.0
    roll_max = eq.expanding().max()
    max_dd   = float((eq / roll_max - 1).min())
    ann_vol  = float(dr.std() * math.sqrt(252))
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0

    return {
        "label":    label,
        "period":   f"{dr.index[0].date()} → {dr.index[-1].date()}",
        "n_years":  round(n_years, 1),
        "cagr_pct": round(float(cagr) * 100, 3),
        "sharpe":   round(sharpe, 4),
        "max_dd_pct": round(max_dd * 100, 3),
        "ann_vol_pct": round(ann_vol * 100, 3),
        "calmar":   round(calmar, 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H048 — XLK IBS (H048a) + Sell-in-May Seasonality on H042 (H048b)")
    print("=" * 80)

    # ── 1. Fetch data ─────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    xlk_ohlc = fetch_ohlc("XLK", DATA_START, FULL_END)
    spy_ohlc = fetch_ohlc("SPY", DATA_START, FULL_END)
    shy_ohlc = fetch_ohlc("SHY", DATA_START, FULL_END)

    all_tickers = list(set(H041A_ASSETS + SECTOR_ETFS + ["SHY"]))
    prices = fetch_close(all_tickers, DATA_START, FULL_END, tag="h048_all")

    # SHY daily returns
    shy_dr = shy_ohlc["close"].pct_change().fillna(0)

    # ── 2. H048a: XLK IBS mean-reversion ─────────────────────────────────────
    print("\n[2] H048a — XLK IBS mean-reversion (2000-2026) …")

    xlk_feat = build_ibs_features(xlk_ohlc)
    spy_feat = build_ibs_features(spy_ohlc)

    # Full period: 2000-2026
    xlk_feat_full = xlk_feat.loc["2000-01-01":"2026-04-27"]
    spy_feat_full = spy_feat.loc["2003-01-01":"2026-04-27"]  # H037b reference period

    eq_h048a, dr_h048a, trades_h048a = run_ibs_strategy(xlk_feat_full, "H048a")
    eq_h037b_spy, dr_h037b_spy, trades_h037b = run_ibs_strategy(spy_feat_full, "H037b")

    n_years_xlk = len(xlk_feat_full) / 252.0
    n_years_spy = len(spy_feat_full) / 252.0

    stats_h048a = compute_ibs_stats(eq_h048a, trades_h048a, "H048a XLK IBS Full (2000-2026)", n_years_xlk)
    stats_h037b = compute_ibs_stats(eq_h037b_spy, trades_h037b, "H037b SPY IBS Full (2003-2026)", n_years_spy)

    # XLK buy-and-hold
    bnh_xlk = bnh_stats(xlk_ohlc, "2000-01-01", "2026-04-27", "XLK Buy-and-Hold (2000-2026)")
    bnh_spy = bnh_stats(spy_ohlc, "2000-01-01", "2026-04-27", "SPY Buy-and-Hold (2000-2026)")

    # Correlation of H048a daily returns to H037b daily returns
    # Align both series to a common period (2003-01-01 to 2026-04-27)
    dr_h048a_aligned = dr_h048a.loc["2003-01-01":"2026-04-27"]
    dr_h037b_aligned = dr_h037b_spy.loc["2003-01-01":"2026-04-27"]
    common_corr = dr_h048a_aligned.index.intersection(dr_h037b_aligned.index)
    if len(common_corr) > 0:
        corr_h048a_h037b = float(
            dr_h048a_aligned.loc[common_corr].corr(dr_h037b_aligned.loc[common_corr])
        )
    else:
        corr_h048a_h037b = float("nan")

    print(f"  H048a XLK IBS: CAGR {stats_h048a['cagr_pct']:.2f}%  Sharpe {stats_h048a['sharpe']:.4f}"
          f"  MaxDD {stats_h048a['max_dd_pct']:.2f}%  Trades {stats_h048a['n_trades']}"
          f"  WinRate {stats_h048a['win_rate_pct']:.1f}%")
    print(f"  H037b SPY IBS: CAGR {stats_h037b['cagr_pct']:.2f}%  Sharpe {stats_h037b['sharpe']:.4f}"
          f"  MaxDD {stats_h037b['max_dd_pct']:.2f}%  Trades {stats_h037b['n_trades']}"
          f"  WinRate {stats_h037b['win_rate_pct']:.1f}%")
    print(f"  XLK BnH:       CAGR {bnh_xlk['cagr_pct']:.2f}%  Sharpe {bnh_xlk['sharpe']:.4f}  MaxDD {bnh_xlk['max_dd_pct']:.2f}%")
    print(f"  SPY BnH:       CAGR {bnh_spy['cagr_pct']:.2f}%  Sharpe {bnh_spy['sharpe']:.4f}  MaxDD {bnh_spy['max_dd_pct']:.2f}%")
    print(f"  Correlation H048a vs H037b daily returns: {corr_h048a_h037b:.4f}")
    if corr_h048a_h037b < 0.5:
        print(f"  → Correlation < 0.5: H048a could supplement H037b")
    else:
        print(f"  → Correlation >= 0.5: H048a is too correlated with H037b to add much")

    # ── 3. H048b: Sell-in-May overlay on H042 ─────────────────────────────────
    print("\n[3] H048b — Sell-in-May seasonality overlay on H042 (2003-2026) …")

    # Reconstruct H042 daily equity
    print("  Building H042 daily equity curve …")
    eq_h042_daily = h042_daily_equity(
        prices, spy_ohlc, shy_dr,
        start=H048B_START, end=FULL_END
    )
    dr_h042_daily = eq_h042_daily.pct_change().fillna(0)

    # H042 baseline stats
    stats_h042_base = equity_stats_from_daily_returns(
        dr_h042_daily, "H042 baseline", H048B_START, FULL_END
    )
    print(f"  H042 baseline: CAGR {stats_h042_base['cagr_pct']:.2f}%  "
          f"Sharpe {stats_h042_base['sharpe']:.4f}  MaxDD {stats_h042_base['max_dd_pct']:.2f}%")

    # Common index for seasonality overlay
    common_idx = dr_h042_daily.index.intersection(shy_dr.index)
    common_idx = common_idx[common_idx >= pd.Timestamp(H048B_START)]
    common_idx = common_idx[common_idx <= pd.Timestamp(FULL_END)]

    # Variant 1: 50% equity / 50% SHY in May-Oct
    dr_v1 = apply_sell_in_may_v1(dr_h042_daily, shy_dr, common_idx)
    stats_v1 = equity_stats_from_daily_returns(dr_v1, "H048b V1: 50% SHY May-Oct", H048B_START, FULL_END)

    # Variant 2: 100% SHY in May-Oct
    dr_v2 = apply_sell_in_may_v2(dr_h042_daily, shy_dr, common_idx)
    stats_v2 = equity_stats_from_daily_returns(dr_v2, "H048b V2: 100% SHY May-Oct", H048B_START, FULL_END)

    # Variant 3: conditional on negative April
    dr_v3 = apply_sell_in_may_v3(dr_h042_daily, shy_dr, prices, common_idx)
    stats_v3 = equity_stats_from_daily_returns(dr_v3, "H048b V3: Conditional (neg April)", H048B_START, FULL_END)

    print(f"  V1 (50/50 SHY May-Oct):   CAGR {stats_v1['cagr_pct']:.2f}%  Sharpe {stats_v1['sharpe']:.4f}  MaxDD {stats_v1['max_dd_pct']:.2f}%")
    print(f"  V2 (100% SHY May-Oct):    CAGR {stats_v2['cagr_pct']:.2f}%  Sharpe {stats_v2['sharpe']:.4f}  MaxDD {stats_v2['max_dd_pct']:.2f}%")
    print(f"  V3 (Conditional neg Apr): CAGR {stats_v3['cagr_pct']:.2f}%  Sharpe {stats_v3['sharpe']:.4f}  MaxDD {stats_v3['max_dd_pct']:.2f}%")

    # Pre/post 2015 analysis
    print("\n  Pre/post-2015 sub-period analysis …")
    sub_periods = [
        ("Pre-2015",  H048B_START, "2014-12-31"),
        ("Post-2015", "2015-01-01", FULL_END),
    ]

    sub_results = {}
    for lbl, s, e in sub_periods:
        sub_results[lbl] = {
            "h042_base": equity_stats_from_daily_returns(dr_h042_daily, f"H042 {lbl}", s, e),
            "v1":        equity_stats_from_daily_returns(dr_v1, f"V1 {lbl}", s, e),
            "v2":        equity_stats_from_daily_returns(dr_v2, f"V2 {lbl}", s, e),
            "v3":        equity_stats_from_daily_returns(dr_v3, f"V3 {lbl}", s, e),
        }
        print(f"\n  {lbl}:")
        print(f"    H042 base:   CAGR {sub_results[lbl]['h042_base']['cagr_pct']:.2f}%  "
              f"Sharpe {sub_results[lbl]['h042_base']['sharpe']:.4f}  "
              f"MaxDD {sub_results[lbl]['h042_base']['max_dd_pct']:.2f}%")
        print(f"    V1 (50/50):  CAGR {sub_results[lbl]['v1']['cagr_pct']:.2f}%  "
              f"Sharpe {sub_results[lbl]['v1']['sharpe']:.4f}  "
              f"MaxDD {sub_results[lbl]['v1']['max_dd_pct']:.2f}%")
        print(f"    V2 (100%):   CAGR {sub_results[lbl]['v2']['cagr_pct']:.2f}%  "
              f"Sharpe {sub_results[lbl]['v2']['sharpe']:.4f}  "
              f"MaxDD {sub_results[lbl]['v2']['max_dd_pct']:.2f}%")
        print(f"    V3 (cond.):  CAGR {sub_results[lbl]['v3']['cagr_pct']:.2f}%  "
              f"Sharpe {sub_results[lbl]['v3']['sharpe']:.4f}  "
              f"MaxDD {sub_results[lbl]['v3']['max_dd_pct']:.2f}%")

    # May-Oct return seasonality analysis: SPY
    print("\n  May-Oct vs Nov-Apr return analysis (SPY) …")
    spy_dr_daily = spy_ohlc["close"].pct_change().dropna()
    spy_dr_daily = spy_dr_daily.loc[H048B_START:FULL_END]
    may_oct_mask  = spy_dr_daily.index.month.isin([5, 6, 7, 8, 9, 10])
    nov_apr_mask  = ~may_oct_mask

    spy_may_oct_ann  = float(spy_dr_daily[may_oct_mask].mean() * 252 * 100)
    spy_nov_apr_ann  = float(spy_dr_daily[nov_apr_mask].mean() * 252 * 100)
    spy_may_oct_sr   = float(spy_dr_daily[may_oct_mask].mean() / spy_dr_daily[may_oct_mask].std() * math.sqrt(252)) if spy_dr_daily[may_oct_mask].std() > 0 else 0.0
    spy_nov_apr_sr   = float(spy_dr_daily[nov_apr_mask].mean() / spy_dr_daily[nov_apr_mask].std() * math.sqrt(252)) if spy_dr_daily[nov_apr_mask].std() > 0 else 0.0

    # Pre/post 2015 split for seasonality effect
    spy_pre  = spy_dr_daily.loc[H048B_START:"2014-12-31"]
    spy_post = spy_dr_daily.loc["2015-01-01":FULL_END]

    def season_sharpe(dr):
        m = dr.mean()
        s = dr.std()
        return float(m / s * math.sqrt(252)) if s > 0 else 0.0

    may_oct_pre  = spy_pre[spy_pre.index.month.isin([5,6,7,8,9,10])]
    nov_apr_pre  = spy_pre[~spy_pre.index.month.isin([5,6,7,8,9,10])]
    may_oct_post = spy_post[spy_post.index.month.isin([5,6,7,8,9,10])]
    nov_apr_post = spy_post[~spy_post.index.month.isin([5,6,7,8,9,10])]

    seasonality = {
        "full_period": {
            "may_oct_ann_ret_pct":  round(spy_may_oct_ann, 3),
            "nov_apr_ann_ret_pct":  round(spy_nov_apr_ann, 3),
            "may_oct_sharpe":       round(spy_may_oct_sr, 4),
            "nov_apr_sharpe":       round(spy_nov_apr_sr, 4),
            "spread_ann_pct":       round(spy_nov_apr_ann - spy_may_oct_ann, 3),
        },
        "pre_2015": {
            "may_oct_ann_ret_pct":  round(float(may_oct_pre.mean() * 252 * 100), 3),
            "nov_apr_ann_ret_pct":  round(float(nov_apr_pre.mean() * 252 * 100), 3),
            "may_oct_sharpe":       round(season_sharpe(may_oct_pre), 4),
            "nov_apr_sharpe":       round(season_sharpe(nov_apr_pre), 4),
        },
        "post_2015": {
            "may_oct_ann_ret_pct":  round(float(may_oct_post.mean() * 252 * 100), 3),
            "nov_apr_ann_ret_pct":  round(float(nov_apr_post.mean() * 252 * 100), 3),
            "may_oct_sharpe":       round(season_sharpe(may_oct_post), 4),
            "nov_apr_sharpe":       round(season_sharpe(nov_apr_post), 4),
        },
    }

    print(f"  Full period: May-Oct ann {spy_may_oct_ann:.2f}%  Sharpe {spy_may_oct_sr:.3f}"
          f" | Nov-Apr ann {spy_nov_apr_ann:.2f}%  Sharpe {spy_nov_apr_sr:.3f}"
          f" | spread {seasonality['full_period']['spread_ann_pct']:.2f}%")
    print(f"  Pre-2015:   May-Oct {seasonality['pre_2015']['may_oct_ann_ret_pct']:.2f}%"
          f"  Nov-Apr {seasonality['pre_2015']['nov_apr_ann_ret_pct']:.2f}%")
    print(f"  Post-2015:  May-Oct {seasonality['post_2015']['may_oct_ann_ret_pct']:.2f}%"
          f"  Nov-Apr {seasonality['post_2015']['nov_apr_ann_ret_pct']:.2f}%")

    # ── 4. Summary comparison table ───────────────────────────────────────────
    print("\n" + "=" * 90)
    print("  H048 SUMMARY")
    print("=" * 90)

    print("\n  H048a — XLK IBS mean-reversion vs benchmarks")
    print(f"  {'Strategy':<42}  {'CAGR%':>7}  {'Sharpe':>7}  {'MaxDD%':>7}  {'Trades':>7}  {'WinRate%':>9}")
    print("  " + "-" * 85)
    rows_a = [
        (stats_h048a["period"], stats_h048a["cagr_pct"], stats_h048a["sharpe"],
         stats_h048a["max_dd_pct"], stats_h048a["n_trades"], stats_h048a["win_rate_pct"]),
        (stats_h037b["period"], stats_h037b["cagr_pct"], stats_h037b["sharpe"],
         stats_h037b["max_dd_pct"], stats_h037b["n_trades"], stats_h037b["win_rate_pct"]),
        (bnh_xlk["label"], bnh_xlk["cagr_pct"], bnh_xlk["sharpe"],
         bnh_xlk["max_dd_pct"], "-", "-"),
        (bnh_spy["label"], bnh_spy["cagr_pct"], bnh_spy["sharpe"],
         bnh_spy["max_dd_pct"], "-", "-"),
    ]
    for r in rows_a:
        print(f"  {r[0]:<42}  {r[1]:>7.2f}  {r[2]:>7.4f}  {r[3]:>7.2f}  {str(r[4]):>7}  {str(r[5]):>9}")

    print(f"\n  XLK IBS ↔ SPY IBS daily return correlation: {corr_h048a_h037b:.4f}")
    if corr_h048a_h037b < 0.5:
        corr_verdict = "LOW correlation — XLK IBS can supplement H037b as an independent signal"
    else:
        corr_verdict = "HIGH correlation — XLK IBS is redundant with H037b; blending adds little diversification"
    print(f"  Verdict: {corr_verdict}")

    print("\n  H048b — Sell-in-May variants vs H042 baseline (2003-2026)")
    print(f"  {'Strategy':<45}  {'CAGR%':>7}  {'Sharpe':>7}  {'MaxDD%':>7}")
    print("  " + "-" * 72)
    rows_b = [
        ("H042 baseline",              stats_h042_base),
        ("V1: 50% SHY May-Oct",        stats_v1),
        ("V2: 100% SHY May-Oct",       stats_v2),
        ("V3: Conditional neg-April",  stats_v3),
    ]
    for name, s in rows_b:
        if "error" not in s:
            print(f"  {name:<45}  {s['cagr_pct']:>7.2f}  {s['sharpe']:>7.4f}  {s['max_dd_pct']:>7.2f}")

    # ── 5. Construct and save JSON ────────────────────────────────────────────
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):    return int(obj)
        if isinstance(obj, (np.floating,)):   return float(obj)
        if isinstance(obj, (np.bool_,)):      return bool(obj)
        return str(obj)

    output = {
        "run_date": "2026-04-27",
        "h048a": {
            "strategy": "H048a — XLK IBS Mean-Reversion (H037b rules applied to XLK)",
            "rules": {
                "entry": "IBS[t-1] < 0.20 AND gap[t] >= -0.5% → buy XLK at open",
                "exit":  "IBS[t] > 0.80 OR held >= 5 days → sell at close",
                "position_size": "100% of allocated capital",
            },
            "period": f"{DATA_START} → {FULL_END}",
            "results": {
                "h048a_xlk_ibs":    stats_h048a,
                "h037b_spy_ibs":    stats_h037b,
                "xlk_buy_and_hold": bnh_xlk,
                "spy_buy_and_hold": bnh_spy,
            },
            "correlation": {
                "h048a_vs_h037b_daily":  round(corr_h048a_h037b, 4),
                "supplement_h037b":      corr_h048a_h037b < 0.5,
                "verdict": corr_verdict,
            },
        },
        "h048b": {
            "strategy": "H048b — Sell-in-May Seasonality Overlay on H042",
            "baseline_period": f"{H048B_START} → {FULL_END}",
            "h042_weights": {"h041a": W_H041A, "h026": W_H026, "h037b": W_H037B},
            "variants": {
                "v1_description": "50% equity exposure, 50% SHY during May-October",
                "v2_description": "100% SHY during May-October (hard switch)",
                "v3_description": "100% SHY May-Oct only in years with negative April SPY return",
            },
            "full_period_results": {
                "h042_baseline": stats_h042_base,
                "v1":            stats_v1,
                "v2":            stats_v2,
                "v3":            stats_v3,
            },
            "sub_period_results": sub_results,
            "spy_seasonality_analysis": seasonality,
        },
    }

    out_path = RESULT_DIR / "h048_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=_json_safe))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
