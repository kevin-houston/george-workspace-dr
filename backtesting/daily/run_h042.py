"""
H042 — Ultimate Three-Way Blend: H041a + H026 + H037b
======================================================

Upgrades H031b by replacing H020 (5-asset) with H041a (7-asset, +EFA/EEM).
All three components use their best-known versions:

  H041a : 7-asset macro rotation (SPY/QQQ/TLT/GLD/IEF/EFA/EEM)
          rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly
          Standalone Sharpe: 1.223

  H026  : 11 sector ETF top-3 momentum, 33.3% each, monthly rebalance
          Same signal as H041a but all-equity sectors
          Standalone Sharpe: 0.872

  H037b : H009 IBS daily mean-reversion + gap < -0.5% exclusion filter
          Buy SPY at open when IBS[t-1] < 0.20 AND gap >= -0.5%
          Sell when IBS > 0.80 or held >= 5 days
          Standalone Sharpe: 1.021

H031b reference (H020 + H026 + H037b, optimal 51/20/29):
  Sharpe 1.883, MaxDD -9.20%

Grid:
  H041a: 40–70% (step 10)
  H026:  10–40% (step 10)
  H037b: remainder = 1 - H041a - H026

Continuous sweep: 101×101 for max-Sharpe and min-MaxDD.

Common period: 2003-08-31 → 2026-04-30 (aligned to EFA/EEM availability + H037b)

Outputs:
  /workspace/agent/backtesting/results/h042_results.json
  /workspace/agent/backtesting/daily/run_h042.py  (this file)
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

FULL_START   = "2000-01-01"    # data download start (warmup)
FULL_END     = "2026-04-27"
WINDOW_START = "2003-08-01"    # common analysis start (same as H031/H031b, EFA/EEM available)

# ── Asset universes ──────────────────────────────────────────────────────────
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
TOP_N_H41A   = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

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
    return CACHE_DIR / f"h042_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
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
    """Return SPY OHLC; reuse existing h031 cache when possible."""
    # check common caches from prior runs
    for fname in [
        f"h031_spy_ohlc_{start}_{end}.parquet",
        f"h031b_spy_ohlc_{start}_{end}.parquet",
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
    cp = CACHE_DIR / f"h042_spy_ohlc_{start}_{end}.parquet"
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
# H041a equity curve (7-asset macro rotation)
# ─────────────────────────────────────────────────────────────────────────────

def h041a_equity_curve(prices: pd.DataFrame) -> pd.Series:
    """
    7-asset macro rotation: SPY/QQQ/TLT/GLD/IEF/EFA/EEM
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50
    Monthly rebalance.
    """
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H41A:
        return pd.Series(dtype=float)

    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H41A   # 50/50
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
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# H026 equity curve (11 sector top-3)
# ─────────────────────────────────────────────────────────────────────────────

def h026_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
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
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# H037b equity curve (H009 + gap filter -0.5%)
# ─────────────────────────────────────────────────────────────────────────────

def h037b_equity_curve(ohlc: pd.DataFrame) -> pd.Series:
    """
    H037b: IBS mean-reversion on SPY with gap-down exclusion filter.
    Entry: IBS[t-1] < IBS_BUY AND gap[t] >= GAP_FILTER_B
    Exit:  IBS[t] > IBS_SELL OR days_held >= MAX_HOLD
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

        ret_oc = (c / o - 1)      if o > 0     else 0.0   # open→close (entry day)
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0  # close→close (hold days)

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
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Grid search
# ─────────────────────────────────────────────────────────────────────────────

def threeway_grid(r1: pd.Series, r2: pd.Series, r3: pd.Series,
                  w1_range, w2_range,
                  label1="H041a", label2="H026", label3="H037b") -> list:
    common = r1.index.intersection(r2.index).intersection(r3.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    n_years = len(a1) / 12.0

    results = []
    for w1 in w1_range:
        for w2 in w2_range:
            w3 = round(1.0 - w1 - w2, 6)
            if w3 < -1e-9:
                continue
            w3 = max(w3, 0.0)
            rb = w1 * a1 + w2 * a2 + w3 * a3
            cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
            vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
            sharpe = cagr / vol if vol > 0 else 0.0
            eq     = np.cumprod(1 + rb)
            roll_mx = np.maximum.accumulate(eq)
            max_dd = float(np.min(eq / roll_mx - 1))
            calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0
            results.append({
                f"w_{label1.lower()}": round(w1, 4),
                f"w_{label2.lower()}": round(w2, 4),
                f"w_{label3.lower()}": round(w3, 4),
                "cagr":         round(cagr,   4),
                "sharpe":       round(sharpe,  4),
                "max_drawdown": round(max_dd,  4),
                "calmar":       round(calmar,  4),
                "ann_vol":      round(vol,     4),
                "n_months":     len(rb),
            })
    return sorted(results, key=lambda x: x["sharpe"], reverse=True)


def find_optimal_threeway(r1: pd.Series, r2: pd.Series, r3: pd.Series,
                          n_steps: int = 101,
                          label1="h041a", label2="h026", label3="h037b") -> dict:
    common = r1.index.intersection(r2.index).intersection(r3.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    n_years = len(a1) / 12.0

    best_sharpe   = -np.inf
    best_sharpe_w = (0.5, 0.2, 0.3)
    min_maxdd     = -np.inf
    min_maxdd_w   = (0.5, 0.2, 0.3)

    axis = np.linspace(0, 1, n_steps)
    for w1 in axis:
        for w2 in axis:
            w3 = 1.0 - w1 - w2
            if w3 < 0:
                continue
            rb     = w1 * a1 + w2 * a2 + w3 * a3
            cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
            vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
            sharpe = cagr / vol if vol > 0 else 0.0
            eq     = np.cumprod(1 + rb)
            roll_mx = np.maximum.accumulate(eq)
            max_dd = float(np.min(eq / roll_mx - 1))
            if sharpe > best_sharpe:
                best_sharpe   = sharpe
                best_sharpe_w = (w1, w2, w3)
            if max_dd > min_maxdd:
                min_maxdd   = max_dd
                min_maxdd_w = (w1, w2, w3)

    def _stats(w1, w2, w3):
        rb     = w1 * a1 + w2 * a2 + w3 * a3
        cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
        vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
        sharpe = cagr / vol if vol > 0 else 0.0
        eq     = np.cumprod(1 + rb)
        roll_mx = np.maximum.accumulate(eq)
        max_dd = float(np.min(eq / roll_mx - 1))
        calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0
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

    return {
        "max_sharpe": _stats(*best_sharpe_w),
        "min_maxdd":  _stats(*min_maxdd_w),
    }


def blend_stats_at_weights(r1: pd.Series, r2: pd.Series, r3: pd.Series,
                           w1: float, w2: float, w3: float,
                           label1="h041a", label2="h026", label3="h037b") -> dict:
    """Compute blend stats at fixed weights."""
    common = r1.index.intersection(r2.index).intersection(r3.index)
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
    max_dd = float(np.min(eq / roll_mx - 1))
    calmar = abs(cagr / max_dd) if max_dd < 0 else 0.0
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


# ─────────────────────────────────────────────────────────────────────────────
# Marginal Sharpe contribution
# ─────────────────────────────────────────────────────────────────────────────

def marginal_sharpe_contribution(r1: pd.Series, r2: pd.Series, r3: pd.Series,
                                  w1: float, w2: float, w3: float,
                                  labels=("h041a", "h026", "h037b"),
                                  epsilon: float = 0.01) -> dict:
    """
    Estimate marginal Sharpe contribution of each strategy.
    For each component i, compute dSharpe/dw_i numerically:
      nudge w_i by +epsilon, reduce others proportionally,
      compute delta Sharpe.
    """
    common = r1.index.intersection(r2.index).intersection(r3.index)
    arrays = [r1.loc[common].values, r2.loc[common].values, r3.loc[common].values]
    weights = [w1, w2, w3]
    n_years = len(arrays[0]) / 12.0

    def portfolio_sharpe(ws):
        rb  = sum(w * a for w, a in zip(ws, arrays))
        vol = float(np.std(rb, ddof=1)) * np.sqrt(12)
        cagr = float(np.prod(1 + rb) ** (1 / n_years) - 1)
        return cagr / vol if vol > 0 else 0.0

    base_sharpe = portfolio_sharpe(weights)
    contributions = {}
    for i, lbl in enumerate(labels):
        others = [j for j in range(3) if j != i]
        w_new = list(weights)
        w_new[i] += epsilon
        # reduce others proportionally
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
    print("H042 — Ultimate Three-Way Blend: H041a + H026 + H037b")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices   = fetch_close(all_tickers, FULL_START, FULL_END, tag="h042_all")
    spy_ohlc = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build individual equity curves ────────────────────────────────────
    print("\n[2] Building H041a equity curve (7-asset macro rotation) …")
    eq_h041a = h041a_equity_curve(prices)

    print("[3] Building H026 equity curve (11-sector top-3) …")
    eq_h026 = h026_equity_curve(prices)

    print("[4] Building H037b equity curve (gap-filtered IBS) …")
    eq_h037b = h037b_equity_curve(spy_ohlc)

    for name, eq in [("H041a", eq_h041a), ("H026", eq_h026), ("H037b", eq_h037b)]:
        if eq.empty:
            print(f"ERROR: {name} equity curve is empty. Aborting.")
            return {}
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} days)")

    # ── 3. Monthly returns ────────────────────────────────────────────────────
    print("\n[5] Converting to monthly returns …")
    r_h041a_all  = to_monthly_returns(eq_h041a)
    r_h026_all   = to_monthly_returns(eq_h026)
    r_h037b_all  = to_monthly_returns(eq_h037b)

    common_idx = (
        r_h041a_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h037b_all.index)
    )
    # Clip to WINDOW_START so all three strategies are on the same 2003-08 → 2026-04 period
    # (matches H031/H031b common window; avoids 2001-2003 dot-com era where H041a was immature)
    window_ts  = pd.Timestamp(WINDOW_START)
    common_idx = common_idx[common_idx >= window_ts]
    r_h041a = r_h041a_all.loc[common_idx]
    r_h026  = r_h026_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")

    # ── 4. Pairwise correlations ──────────────────────────────────────────────
    corr_41a_26   = float(r_h041a.corr(r_h026))
    corr_41a_37b  = float(r_h041a.corr(r_h037b))
    corr_26_37b   = float(r_h026.corr(r_h037b))

    print(f"\n   Pairwise monthly correlations:")
    print(f"     H041a / H026  : {corr_41a_26:.4f}")
    print(f"     H041a / H037b : {corr_41a_37b:.4f}")
    print(f"     H026  / H037b : {corr_26_37b:.4f}")

    # ── 5. Standalone stats ───────────────────────────────────────────────────
    print("\n[6] Computing standalone stats …")
    s_h041a = stats_from_monthly_returns(r_h041a)
    s_h026  = stats_from_monthly_returns(r_h026)
    s_h037b = stats_from_monthly_returns(r_h037b)

    print(f"   H041a : CAGR {s_h041a['cagr']:.2%}  Sharpe {s_h041a['sharpe']:.3f}  MaxDD {s_h041a['max_drawdown']:.2%}")
    print(f"   H026  : CAGR {s_h026['cagr']:.2%}  Sharpe {s_h026['sharpe']:.3f}  MaxDD {s_h026['max_drawdown']:.2%}")
    print(f"   H037b : CAGR {s_h037b['cagr']:.2%}  Sharpe {s_h037b['sharpe']:.3f}  MaxDD {s_h037b['max_drawdown']:.2%}")

    # ── 6. Coarse grid ────────────────────────────────────────────────────────
    print("\n[7] Running three-way grid search …")
    h041a_range = [0.40, 0.50, 0.60, 0.70]
    h026_range  = [0.10, 0.20, 0.30, 0.40]

    grid_results = threeway_grid(r_h041a, r_h026, r_h037b,
                                  h041a_range, h026_range,
                                  "H041a", "H026", "H037b")

    print(f"\n{'=' * 92}")
    print("  THREE-WAY BLEND GRID: H041a / H026 / H037b")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 92}")
    print(f"  {'H041a':>6}  {'H026':>6}  {'H037b':>6}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*86}")
    for row in grid_results:
        print(
            f"  {row['w_h041a']:>6.0%}  {row['w_h026']:>6.0%}  {row['w_h037b']:>6.0%}  "
            f"{row['cagr']:>8.2%}  {row['sharpe']:>8.3f}  {row['max_drawdown']:>8.2%}  "
            f"{row['ann_vol']:>8.2%}  {row['calmar']:>8.3f}"
        )

    best_sharpe_grid = grid_results[0]
    best_mindd_grid  = sorted(grid_results, key=lambda x: x["max_drawdown"], reverse=True)[0]
    print(f"\n  Grid best Sharpe : H041a={best_sharpe_grid['w_h041a']:.0%}  H026={best_sharpe_grid['w_h026']:.0%}  "
          f"H037b={best_sharpe_grid['w_h037b']:.0%}  →  Sharpe {best_sharpe_grid['sharpe']:.4f}")
    print(f"  Grid min MaxDD   : H041a={best_mindd_grid['w_h041a']:.0%}  H026={best_mindd_grid['w_h026']:.0%}  "
          f"H037b={best_mindd_grid['w_h037b']:.0%}  →  MaxDD {best_mindd_grid['max_drawdown']:.2%}")

    # ── 7. Continuous optimisation ────────────────────────────────────────────
    print("\n[8] Running continuous 2D optimisation (101×101 grid) …")
    optimal = find_optimal_threeway(r_h041a, r_h026, r_h037b, n_steps=101)

    opt_sharpe = optimal["max_sharpe"]
    opt_mindd  = optimal["min_maxdd"]

    print(f"\n  Continuous max-Sharpe : H041a={opt_sharpe['w_h041a']:.1%}  H026={opt_sharpe['w_h026']:.1%}  "
          f"H037b={opt_sharpe['w_h037b']:.1%}")
    print(f"    CAGR {opt_sharpe['cagr']:.2%}  Sharpe {opt_sharpe['sharpe']:.4f}  "
          f"MaxDD {opt_sharpe['max_drawdown']:.2%}  AnnVol {opt_sharpe['ann_vol']:.2%}")
    print(f"\n  Continuous min-MaxDD  : H041a={opt_mindd['w_h041a']:.1%}  H026={opt_mindd['w_h026']:.1%}  "
          f"H037b={opt_mindd['w_h037b']:.1%}")
    print(f"    CAGR {opt_mindd['cagr']:.2%}  Sharpe {opt_mindd['sharpe']:.4f}  "
          f"MaxDD {opt_mindd['max_drawdown']:.2%}  AnnVol {opt_mindd['ann_vol']:.2%}")

    # ── 8. H031b fixed-weight comparison (51/20/29 but with H041a) ───────────
    print("\n[9] Computing H031b optimal weights (51/20/29) applied to H041a …")
    h031b_weights = (0.51, 0.20, 0.29)
    s_h031b_fixed = blend_stats_at_weights(r_h041a, r_h026, r_h037b, *h031b_weights)
    print(f"   H042 @H031b-weights(51/20/29): CAGR {s_h031b_fixed['cagr']:.2%}  "
          f"Sharpe {s_h031b_fixed['sharpe']:.4f}  MaxDD {s_h031b_fixed['max_drawdown']:.2%}")

    # ── 9. Marginal Sharpe contributions ──────────────────────────────────────
    print("\n[10] Computing marginal Sharpe contributions at optimal weights …")
    opt_w = (opt_sharpe["w_h041a"], opt_sharpe["w_h026"], opt_sharpe["w_h037b"])
    marginal = marginal_sharpe_contribution(r_h041a, r_h026, r_h037b, *opt_w)
    print(f"   Base portfolio Sharpe: {marginal['base_sharpe']:.4f}")
    print(f"   Marginal contributions (dSharpe/dw, epsilon=0.01):")
    for k, v in marginal["marginal_sharpe_per_unit"].items():
        print(f"     {k:<10}: {v:+.4f}")

    # ── 10. Reference values ─────────────────────────────────────────────────
    H031B_REF = {
        "weights":      {"w_h020": 0.51, "w_h026": 0.20, "w_h037b": 0.29},
        "cagr":         0.1430,
        "sharpe":       1.8833,
        "max_drawdown": -0.0920,
        "calmar":       1.554,
        "ann_vol":      0.0759,
        "n_months":     273,
        "note":         "H031b continuous max-Sharpe result (H020+H026+H037b), from h031b_results.json",
    }

    # ── 11. Summary comparison ────────────────────────────────────────────────
    print(f"\n{'=' * 92}")
    print("  H042 vs H031b COMPARISON SUMMARY")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 92}")
    print(f"  {'Scenario':<48}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*90}")

    comparison = [
        ("H041a standalone (7-asset macro)",          s_h041a),
        ("H026  standalone (sector top-3)",           s_h026),
        ("H037b standalone (gap-filtered IBS)",       s_h037b),
        ("H042 @H031b-weights 51/20/29",              s_h031b_fixed),
        ("H042 max-Sharpe (re-optimised)",            opt_sharpe),
        ("H042 min-MaxDD  (re-optimised)",            opt_mindd),
    ]

    print(f"  {'[H031b ref] 51/20/29 H020+H026+H037b':<48}  "
          f"{H031B_REF['cagr']:>8.2%}  {H031B_REF['sharpe']:>8.3f}  "
          f"{H031B_REF['max_drawdown']:>8.2%}  {'N/A':>8}  {H031B_REF['calmar']:>8.3f}")

    for name, s in comparison:
        if "error" in s:
            continue
        print(
            f"  {name:<48}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
            f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}"
        )

    sharpe_delta_fixed = s_h031b_fixed["sharpe"] - H031B_REF["sharpe"]
    sharpe_delta_opt   = opt_sharpe["sharpe"] - H031B_REF["sharpe"]
    maxdd_delta_fixed  = s_h031b_fixed["max_drawdown"] - H031B_REF["max_drawdown"]
    maxdd_delta_opt    = opt_sharpe["max_drawdown"] - H031B_REF["max_drawdown"]

    print(f"\n  Sharpe delta vs H031b (@same weights 51/20/29): {sharpe_delta_fixed:+.4f}")
    print(f"  Sharpe delta vs H031b (re-optimised H042)     : {sharpe_delta_opt:+.4f}")
    print(f"  MaxDD  delta vs H031b (@same weights 51/20/29): {maxdd_delta_fixed:+.4f}")
    print(f"  MaxDD  delta vs H031b (re-optimised H042)     : {maxdd_delta_opt:+.4f}")

    if sharpe_delta_opt > 0.02:
        verdict = "H041a upgrade clearly improves the portfolio — EFA/EEM diversification adds Sharpe"
    elif sharpe_delta_opt > 0.0:
        verdict = "H041a upgrade provides marginal improvement — EFA/EEM add modest diversification"
    elif sharpe_delta_opt > -0.02:
        verdict = "H041a substitution is roughly neutral — EFA/EEM neither help nor hurt materially"
    else:
        verdict = "H041a substitution hurts the portfolio — H020 5-asset blend was better in this window"

    print(f"\n  Verdict: {verdict}")

    # ── 12. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H042 — Ultimate Three-Way Blend: H041a + H026 + H037b",
        "description": (
            "H031b upgraded: H020 (5-asset) replaced by H041a (7-asset +EFA/EEM). "
            "Tests whether expanding macro universe to international equities improves portfolio Sharpe."
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
                "signal": "IBS < 0.20 AND gap >= -0.5%  →  buy SPY at open; sell when IBS > 0.80 or held >= 5 days",
                "rebalance": "daily",
                "gap_filter": GAP_FILTER_B,
            },
        },
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
        },
        "monthly_correlations": {
            "h041a_h026":  round(corr_41a_26,  4),
            "h041a_h037b": round(corr_41a_37b, 4),
            "h026_h037b":  round(corr_26_37b,  4),
        },
        "standalone": {
            "h041a": s_h041a,
            "h026":  s_h026,
            "h037b": s_h037b,
        },
        "blend_grid": grid_results,
        "optimal": optimal,
        "fixed_weight_comparison": {
            "weights": {"w_h041a": 0.51, "w_h026": 0.20, "w_h037b": 0.29},
            "description": "H031b optimal weights (51/20/29) applied with H041a replacing H020",
            "stats": s_h031b_fixed,
        },
        "marginal_sharpe_at_optimal": marginal,
        "h031b_reference": H031B_REF,
        "vs_h031b": {
            "sharpe_delta_same_weights":  round(sharpe_delta_fixed, 4),
            "sharpe_delta_reoptimised":   round(sharpe_delta_opt,   4),
            "maxdd_delta_same_weights":   round(maxdd_delta_fixed,  4),
            "maxdd_delta_reoptimised":    round(maxdd_delta_opt,    4),
            "verdict": verdict,
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h042_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
