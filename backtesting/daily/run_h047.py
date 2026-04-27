"""
H047 — Four-Way Blend: H042 (H041a + H026 + H037b) + H045 (Treasury ETF Rotation)
====================================================================================

Tests whether adding H045 (7-ETF Treasury rotation: SHY/IEI/IEF/TLT/TIP/HYG/LQD)
as a 4th component to H042 improves portfolio Sharpe, CAGR, and MaxDD.

  H041a : 7-asset macro rotation (SPY/QQQ/TLT/GLD/IEF/EFA/EEM), top-2
          rank(12m_mom) + rank(inv_6m_vol), monthly

  H026  : 11 sector ETF top-3 momentum, 33.3% each, monthly rebalance

  H037b : IBS mean-reversion SPY with gap < -0.5% filter, daily

  H045  : 7-ETF Treasury rotation (SHY/IEI/IEF/TLT/TIP/HYG/LQD), top-2
          rank(12m_mom) + rank(inv_6m_vol), monthly

Common period: 2008-01 → 2026-04 (limited by IEI data availability)

Grid: H042 bundle at (56/16/28 relative weights kept fixed, scaled down)
  + H045 at 10%, 20%, 30%, 40% total allocation
  e.g. H045=20% → H041a=44.8%, H026=12.8%, H037b=22.4%, H045=20%

Also: full unconstrained 4-way optimization sweep.

Outputs:
  /workspace/agent/backtesting/results/h047_results.json
  /workspace/agent/backtesting/daily/run_h047.py  (this file)
"""

import json
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from itertools import product

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START    = "2000-01-01"    # data download start (warmup)
FULL_END      = "2026-04-27"
WINDOW_START  = "2008-01-01"    # IEI (H045) data starts ~2007-07, need 12m warmup → 2008-07 effective

# ── Asset universes ──────────────────────────────────────────────────────────
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
TOP_N_H41A   = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
TOP_N_H45 = 2

# H042 optimal weights (H041a / H026 / H037b = 56 / 16 / 28)
H042_OPT_41A  = 0.56
H042_OPT_H26  = 0.16
H042_OPT_H37B = 0.28

# ── H037b params ─────────────────────────────────────────────────────────────
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005   # skip entry if gap < -0.5%


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h047_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    """Return SPY OHLC; reuse prior run caches when available."""
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
            if not all(c in df.columns for c in ["open", "high", "low", "close"]):
                df = df.rename(columns=str.lower)
            print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
            return df
    cp = CACHE_DIR / f"h047_spy_ohlc_{start}_{end}.parquet"
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

def stats_from_monthly_returns(monthly_rets: pd.Series) -> dict:
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"error": "insufficient data"}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
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
        "n_months":     len(monthly_rets),
    }


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Equity curve builders
# ─────────────────────────────────────────────────────────────────────────────

def h041a_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H41A:
        return pd.Series(dtype=float)
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


def h026_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
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


def h037b_equity_curve(ohlc: pd.DataFrame) -> pd.Series:
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
        ret_oc = (c / o - 1)      if o > 0     else 0.0
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


def h045_equity_curve(prices: pd.DataFrame) -> pd.Series:
    """
    H045: 7-bond-ETF Treasury rotation (SHY/IEI/IEF/TLT/TIP/HYG/LQD)
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly.
    """
    available = [t for t in TREASURY_ETFS if t in prices.columns]
    if len(available) < TOP_N_H45:
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


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio statistics helper
# ─────────────────────────────────────────────────────────────────────────────

def blend_stats_4way(r1, r2, r3, r4, w1, w2, w3, w4,
                     label1="h041a", label2="h026", label3="h037b", label4="h045") -> dict:
    """Compute 4-way blend stats on the common index."""
    common = r1.index.intersection(r2.index).intersection(r3.index).intersection(r4.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    a4 = r4.loc[common].values
    n_years = len(a1) / 12.0
    rb     = w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
    cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
    vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    eq     = np.cumprod(1 + rb)
    roll_mx = np.maximum.accumulate(eq)
    max_dd  = float(np.min(eq / roll_mx - 1))
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        f"w_{label1}": round(w1, 4),
        f"w_{label2}": round(w2, 4),
        f"w_{label3}": round(w3, 4),
        f"w_{label4}": round(w4, 4),
        "cagr":         round(cagr,   4),
        "sharpe":       round(sharpe,  4),
        "max_drawdown": round(max_dd,  4),
        "calmar":       round(calmar,  4),
        "ann_vol":      round(vol,     4),
        "n_months":     len(rb),
    }


def blend_stats_3way_on_common(r1, r2, r3, r4, w1, w2, w3,
                                label1="h041a", label2="h026", label3="h037b") -> dict:
    """3-way blend stats on the 4-way common index (for apples-to-apples H042 reference)."""
    common = r1.index.intersection(r2.index).intersection(r3.index).intersection(r4.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    n_years = len(a1) / 12.0
    rb     = w1 * a1 + w2 * a2 + w3 * a3
    cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
    vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    eq     = np.cumprod(1 + rb)
    roll_mx = np.maximum.accumulate(eq)
    max_dd  = float(np.min(eq / roll_mx - 1))
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        f"w_{label1}": round(w1, 4),
        f"w_{label2}": round(w2, 4),
        f"w_{label3}": round(w3, 4),
        "cagr":         round(cagr,   4),
        "sharpe":       round(sharpe,  4),
        "max_drawdown": round(max_dd,  4),
        "calmar":       round(calmar,  4),
        "ann_vol":      round(vol,     4),
        "n_months":     len(rb),
    }


def find_optimal_4way(r1, r2, r3, r4, n_steps: int = 51) -> dict:
    """
    Full unconstrained 4-way optimization on a grid of n_steps^3 points.
    Uses n_steps for w1, w2, w3 axis; w4 = 1 - w1 - w2 - w3.
    """
    common = r1.index.intersection(r2.index).intersection(r3.index).intersection(r4.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    a4 = r4.loc[common].values
    n_years = len(a1) / 12.0

    best_sharpe = -np.inf
    best_sw     = (0.4, 0.12, 0.22, 0.26)
    min_maxdd   = -np.inf
    min_dd_w    = (0.4, 0.12, 0.22, 0.26)

    axis = np.linspace(0, 1, n_steps)
    for w1 in axis:
        for w2 in axis:
            if w1 + w2 > 1:
                continue
            for w3 in axis:
                w4 = 1.0 - w1 - w2 - w3
                if w4 < 0:
                    continue
                rb     = w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
                cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
                vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
                sharpe = cagr / vol if vol > 0 else 0.0
                eq     = np.cumprod(1 + rb)
                roll_mx = np.maximum.accumulate(eq)
                max_dd = float(np.min(eq / roll_mx - 1))
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_sw     = (w1, w2, w3, w4)
                if max_dd > min_maxdd:
                    min_maxdd = max_dd
                    min_dd_w  = (w1, w2, w3, w4)

    def _stats(ws):
        w1, w2, w3, w4 = ws
        rb     = w1 * a1 + w2 * a2 + w3 * a3 + w4 * a4
        cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
        vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
        sharpe = cagr / vol if vol > 0 else 0.0
        eq     = np.cumprod(1 + rb)
        roll_mx = np.maximum.accumulate(eq)
        max_dd = float(np.min(eq / roll_mx - 1))
        calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0
        return {
            "w_h041a": round(w1, 4),
            "w_h026":  round(w2, 4),
            "w_h037b": round(w3, 4),
            "w_h045":  round(w4, 4),
            "cagr":         round(cagr,   4),
            "sharpe":       round(sharpe,  4),
            "max_drawdown": round(max_dd,  4),
            "calmar":       round(calmar,  4),
            "ann_vol":      round(vol,     4),
            "n_months":     len(rb),
        }

    return {
        "max_sharpe": _stats(best_sw),
        "min_maxdd":  _stats(min_dd_w),
    }


def marginal_sharpe_4way(r1, r2, r3, r4,
                          w1, w2, w3, w4,
                          labels=("h041a", "h026", "h037b", "h045"),
                          epsilon=0.01) -> dict:
    """Numerical marginal Sharpe contribution for each of 4 strategies."""
    common = r1.index.intersection(r2.index).intersection(r3.index).intersection(r4.index)
    arrays  = [r1.loc[common].values, r2.loc[common].values,
               r3.loc[common].values, r4.loc[common].values]
    weights = [w1, w2, w3, w4]
    n_years = len(arrays[0]) / 12.0

    def portfolio_sharpe(ws):
        rb  = sum(w * a for w, a in zip(ws, arrays))
        vol = float(np.std(rb, ddof=1)) * np.sqrt(12)
        cagr = float(np.prod(1 + rb) ** (1 / n_years) - 1)
        return cagr / vol if vol > 0 else 0.0

    base_sharpe = portfolio_sharpe(weights)
    contributions = {}
    for i, lbl in enumerate(labels):
        others = [j for j in range(4) if j != i]
        w_new = list(weights)
        w_new[i] += epsilon
        other_total = sum(weights[j] for j in others)
        if other_total > 0:
            for j in others:
                w_new[j] -= epsilon * (weights[j] / other_total)
        ds = portfolio_sharpe(w_new) - base_sharpe
        contributions[lbl] = round(float(ds / epsilon), 4)
    return {
        "base_sharpe": round(base_sharpe, 4),
        "weights": {lbl: round(w, 4) for lbl, w in zip(labels, weights)},
        "marginal_sharpe_per_unit": contributions,
        "note": "dSharpe/dw_i: increase in portfolio Sharpe per 1 unit increase in weight (epsilon=0.01)",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H047 — Four-Way Blend: H041a + H026 + H037b + H045")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    equity_tickers   = list(set(H041A_ASSETS + SECTOR_ETFS))
    treasury_tickers = TREASURY_ETFS

    prices_eq   = fetch_close(equity_tickers,   FULL_START, FULL_END, tag="h047_equity")
    prices_tr   = fetch_close(treasury_tickers, FULL_START, FULL_END, tag="h047_treasury")
    spy_ohlc    = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building H041a equity curve (7-asset macro rotation) …")
    eq_h041a = h041a_equity_curve(prices_eq)

    print("[3] Building H026 equity curve (11-sector top-3) …")
    eq_h026 = h026_equity_curve(prices_eq)

    print("[4] Building H037b equity curve (gap-filtered IBS) …")
    eq_h037b = h037b_equity_curve(spy_ohlc)

    print("[5] Building H045 equity curve (7-bond Treasury rotation) …")
    eq_h045 = h045_equity_curve(prices_tr)

    for name, eq in [("H041a", eq_h041a), ("H026", eq_h026),
                     ("H037b", eq_h037b), ("H045", eq_h045)]:
        if eq.empty:
            print(f"ERROR: {name} equity curve is empty. Aborting.")
            return {}
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} days)")

    # ── 3. Monthly returns ─────────────────────────────────────────────────────
    print("\n[6] Converting to monthly returns …")
    r_h041a_all = to_monthly_returns(eq_h041a)
    r_h026_all  = to_monthly_returns(eq_h026)
    r_h037b_all = to_monthly_returns(eq_h037b)
    r_h045_all  = to_monthly_returns(eq_h045)

    # Common window: all 4 strategies, 2008-01 onward (IEI limited)
    common_idx = (
        r_h041a_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h037b_all.index)
        .intersection(r_h045_all.index)
    )
    window_ts  = pd.Timestamp(WINDOW_START)
    common_idx = common_idx[common_idx >= window_ts]

    r_h041a = r_h041a_all.loc[common_idx]
    r_h026  = r_h026_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]
    r_h045  = r_h045_all.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")

    # ── 4. Pairwise correlations ──────────────────────────────────────────────
    corr_41a_26   = float(r_h041a.corr(r_h026))
    corr_41a_37b  = float(r_h041a.corr(r_h037b))
    corr_41a_45   = float(r_h041a.corr(r_h045))
    corr_26_37b   = float(r_h026.corr(r_h037b))
    corr_26_45    = float(r_h026.corr(r_h045))
    corr_37b_45   = float(r_h037b.corr(r_h045))

    print(f"\n   Pairwise monthly correlations (4-way common window):")
    print(f"     H041a / H026  : {corr_41a_26:.4f}")
    print(f"     H041a / H037b : {corr_41a_37b:.4f}")
    print(f"     H041a / H045  : {corr_41a_45:.4f}")
    print(f"     H026  / H037b : {corr_26_37b:.4f}")
    print(f"     H026  / H045  : {corr_26_45:.4f}")
    print(f"     H037b / H045  : {corr_37b_45:.4f}")

    # ── 5. Standalone stats ───────────────────────────────────────────────────
    print("\n[7] Computing standalone stats on common window …")
    s_h041a = stats_from_monthly_returns(r_h041a)
    s_h026  = stats_from_monthly_returns(r_h026)
    s_h037b = stats_from_monthly_returns(r_h037b)
    s_h045  = stats_from_monthly_returns(r_h045)

    print(f"   H041a : CAGR {s_h041a['cagr']:.2%}  Sharpe {s_h041a['sharpe']:.3f}  MaxDD {s_h041a['max_drawdown']:.2%}")
    print(f"   H026  : CAGR {s_h026['cagr']:.2%}  Sharpe {s_h026['sharpe']:.3f}  MaxDD {s_h026['max_drawdown']:.2%}")
    print(f"   H037b : CAGR {s_h037b['cagr']:.2%}  Sharpe {s_h037b['sharpe']:.3f}  MaxDD {s_h037b['max_drawdown']:.2%}")
    print(f"   H045  : CAGR {s_h045['cagr']:.2%}  Sharpe {s_h045['sharpe']:.3f}  MaxDD {s_h045['max_drawdown']:.2%}")

    # ── 6. H042 reference on same 4-way common window ────────────────────────
    print("\n[8] H042 baseline (56/16/28) on 4-way common window …")
    h042_ref = blend_stats_3way_on_common(
        r_h041a, r_h026, r_h037b, r_h045,
        H042_OPT_41A, H042_OPT_H26, H042_OPT_H37B
    )
    print(f"   H042 @(56/16/28) : CAGR {h042_ref['cagr']:.2%}  Sharpe {h042_ref['sharpe']:.4f}  MaxDD {h042_ref['max_drawdown']:.2%}")

    # ── 7. H045 proportion grid: H042 bundle scaled down + H045 ──────────────
    print("\n[9] Running H045 proportion grid (10%/20%/30%/40%) …")
    h045_allocations = [0.10, 0.20, 0.30, 0.40]

    # H042 relative weights (56 / 16 / 28, sum=100)
    h042_rel_41a  = H042_OPT_41A  / (H042_OPT_41A + H042_OPT_H26 + H042_OPT_H37B)
    h042_rel_h26  = H042_OPT_H26  / (H042_OPT_41A + H042_OPT_H26 + H042_OPT_H37B)
    h042_rel_h37b = H042_OPT_H37B / (H042_OPT_41A + H042_OPT_H26 + H042_OPT_H37B)

    h045_grid = []
    for w45 in h045_allocations:
        h042_alloc = 1.0 - w45
        w41a  = h042_rel_41a  * h042_alloc
        w26   = h042_rel_h26  * h042_alloc
        w37b  = h042_rel_h37b * h042_alloc
        row = blend_stats_4way(r_h041a, r_h026, r_h037b, r_h045,
                                w41a, w26, w37b, w45)
        row["h042_alloc"] = round(h042_alloc, 4)
        h045_grid.append(row)
        print(
            f"   H045={w45:.0%}: H041a={w41a:.1%} H026={w26:.1%} H037b={w37b:.1%} → "
            f"Sharpe {row['sharpe']:.4f}  CAGR {row['cagr']:.2%}  MaxDD {row['max_drawdown']:.2%}"
        )

    # ── 8. Marginal Sharpe at each H045 weight ────────────────────────────────
    print("\n[10] Marginal Sharpe contributions at each grid point …")
    marginal_grid = []
    for row in h045_grid:
        mg = marginal_sharpe_4way(
            r_h041a, r_h026, r_h037b, r_h045,
            row["w_h041a"], row["w_h026"], row["w_h037b"], row["w_h045"]
        )
        mg["h045_alloc"] = row["w_h045"]
        marginal_grid.append(mg)
        h45_contrib = mg["marginal_sharpe_per_unit"]["h045"]
        print(f"   H045={row['w_h045']:.0%}  H045 marginal dSharpe/dw: {h45_contrib:+.4f}")

    # ── 9. Full unconstrained 4-way optimisation ──────────────────────────────
    print("\n[11] Running full 4-way unconstrained optimization (51^3 grid) …")
    optimal_4way = find_optimal_4way(r_h041a, r_h026, r_h037b, r_h045, n_steps=51)

    opt_s = optimal_4way["max_sharpe"]
    opt_d = optimal_4way["min_maxdd"]

    print(f"\n  4-Way max-Sharpe: H041a={opt_s['w_h041a']:.1%}  H026={opt_s['w_h026']:.1%}  "
          f"H037b={opt_s['w_h037b']:.1%}  H045={opt_s['w_h045']:.1%}")
    print(f"    CAGR {opt_s['cagr']:.2%}  Sharpe {opt_s['sharpe']:.4f}  MaxDD {opt_s['max_drawdown']:.2%}")
    print(f"\n  4-Way min-MaxDD:  H041a={opt_d['w_h041a']:.1%}  H026={opt_d['w_h026']:.1%}  "
          f"H037b={opt_d['w_h037b']:.1%}  H045={opt_d['w_h045']:.1%}")
    print(f"    CAGR {opt_d['cagr']:.2%}  Sharpe {opt_d['sharpe']:.4f}  MaxDD {opt_d['max_drawdown']:.2%}")

    # ── 10. Marginal Sharpe at optimal 4-way ─────────────────────────────────
    print("\n[12] Marginal Sharpe contributions at 4-way optimal …")
    marginal_opt = marginal_sharpe_4way(
        r_h041a, r_h026, r_h037b, r_h045,
        opt_s["w_h041a"], opt_s["w_h026"], opt_s["w_h037b"], opt_s["w_h045"]
    )
    print(f"   Base Sharpe: {marginal_opt['base_sharpe']:.4f}")
    for k, v in marginal_opt["marginal_sharpe_per_unit"].items():
        print(f"     {k:<10}: {v:+.4f}")

    # ── 11. Summary table ─────────────────────────────────────────────────────
    sharpe_delta_grid = {f"h045_{int(row['w_h045']*100)}pct": round(row["sharpe"] - h042_ref["sharpe"], 4)
                         for row in h045_grid}
    best_grid_row = max(h045_grid, key=lambda r: r["sharpe"])
    best_4way_row = opt_s

    print(f"\n{'=' * 100}")
    print("  H047 SUMMARY: H042 vs H047 blend variants (common 4-way window)")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months, {n_years:.1f} yrs)")
    print(f"{'=' * 100}")
    hdr = f"  {'Scenario':<52}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}"
    print(hdr)
    print(f"  {'-'*96}")

    rows_to_print = [
        ("H041a standalone",                      s_h041a),
        ("H026  standalone",                      s_h026),
        ("H037b standalone",                      s_h037b),
        ("H045  standalone",                      s_h045),
        ("H042 baseline (56/16/28), H045=0%",     h042_ref),
        *[(f"H047 grid H045={int(r['w_h045']*100)}% (H041a/H026/H037b scaled)", r)
          for r in h045_grid],
        ("H047 4-way max-Sharpe (unconstrained)", opt_s),
        ("H047 4-way min-MaxDD  (unconstrained)", opt_d),
    ]
    for name, s in rows_to_print:
        if "error" in s:
            continue
        print(f"  {name:<52}  {s['cagr']:>8.2%}  {s['sharpe']:>8.4f}  "
              f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}")

    # ── 12. Verdict ───────────────────────────────────────────────────────────
    best_grid_sharpe  = best_grid_row["sharpe"]
    best_4way_sharpe  = opt_s["sharpe"]
    h042_sharpe       = h042_ref["sharpe"]

    if best_4way_sharpe > h042_sharpe + 0.02:
        verdict = "H045 addition meaningfully improves H042 — Treasury rotation is a genuine 4th diversifier"
    elif best_4way_sharpe > h042_sharpe:
        verdict = "H045 addition marginally improves H042 — modest Sharpe gain; diversification benefit at optimal weight"
    elif best_4way_sharpe >= h042_sharpe - 0.01:
        verdict = "H045 addition is neutral to H042 — no clear benefit; diversification limited at best tested weights"
    else:
        verdict = "H045 addition hurts H042 — Treasury rotation acts as drag; H042 3-way is superior"

    print(f"\n  Verdict: {verdict}")
    print(f"  H042 baseline Sharpe    : {h042_sharpe:.4f}")
    print(f"  Best H047 grid Sharpe   : {best_grid_sharpe:.4f}  (H045={int(best_grid_row['w_h045']*100)}%)")
    print(f"  Best H047 4-way Sharpe  : {best_4way_sharpe:.4f}  "
          f"(H041a={opt_s['w_h041a']:.0%} H026={opt_s['w_h026']:.0%} "
          f"H037b={opt_s['w_h037b']:.0%} H045={opt_s['w_h045']:.0%})")

    # ── 13. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H047 — Four-Way Blend: H041a + H026 + H037b + H045",
        "description": (
            "Tests whether adding H045 (7-ETF Treasury rotation) as a 4th component to H042 "
            "(H041a + H026 + H037b) improves portfolio Sharpe, CAGR, and MaxDD."
        ),
        "components": {
            "h041a": {
                "universe": H041A_ASSETS,
                "signal": "rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50",
                "rebalance": "monthly",
            },
            "h026": {
                "universe": SECTOR_ETFS,
                "signal": "rank(12m_mom) + rank(inv_6m_vol), hold top-3 at 33.3%",
                "rebalance": "monthly",
            },
            "h037b": {
                "signal": "IBS < 0.20 AND gap >= -0.5% → buy SPY at open; sell when IBS > 0.80 or held >= 5 days",
                "rebalance": "daily",
                "gap_filter": GAP_FILTER_B,
            },
            "h045": {
                "universe": TREASURY_ETFS,
                "signal": "rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50",
                "rebalance": "monthly",
            },
        },
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
            "note":     "Limited by IEI (H045) availability; 12m momentum warmup → effective start 2008",
        },
        "monthly_correlations": {
            "h041a_h026":  round(corr_41a_26,  4),
            "h041a_h037b": round(corr_41a_37b, 4),
            "h041a_h045":  round(corr_41a_45,  4),
            "h026_h037b":  round(corr_26_37b,  4),
            "h026_h045":   round(corr_26_45,   4),
            "h037b_h045":  round(corr_37b_45,  4),
        },
        "standalone_on_common_window": {
            "h041a": s_h041a,
            "h026":  s_h026,
            "h037b": s_h037b,
            "h045":  s_h045,
        },
        "h042_baseline": {
            "weights": {"w_h041a": H042_OPT_41A, "w_h026": H042_OPT_H26, "w_h037b": H042_OPT_H37B},
            "description": "H042 optimal (56/16/28) on the same 4-way common window (H045=0%)",
            "stats": h042_ref,
        },
        "h045_proportion_grid": h045_grid,
        "marginal_sharpe_grid": marginal_grid,
        "optimal_4way": optimal_4way,
        "marginal_sharpe_at_optimal": marginal_opt,
        "sharpe_delta_vs_h042": sharpe_delta_grid,
        "best_blend": {
            "from_grid":          best_grid_row,
            "from_unconstrained": opt_s,
        },
        "verdict": verdict,
        "h042_baseline_sharpe":    round(h042_sharpe,      4),
        "best_grid_sharpe":        round(best_grid_sharpe,  4),
        "best_grid_h045_alloc":    best_grid_row["w_h045"],
        "best_4way_sharpe":        round(best_4way_sharpe,  4),
        "sharpe_improvement_grid": round(best_grid_sharpe - h042_sharpe, 4),
        "sharpe_improvement_4way": round(best_4way_sharpe  - h042_sharpe, 4),
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h047_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
