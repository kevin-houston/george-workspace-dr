"""
H033 — Short Volatility Premium Overlay on H031
================================================

Concept
-------
VIX futures are almost always in contango: front-month < back-month because
market participants systematically overpay for portfolio insurance. Being
short VIX (via SVXY/XIV) earns this roll premium. We model the strategy
using VIX / VIX3M term structure rather than actual futures data, which
eliminates survivorship bias from ETF splits and gaps.

Signal
------
Contango ratio = VIX3M / VIX
  - Contango when > 1.0 (normal; VIX3M > VIX spot)
  - Backwardation when < 1.0 (crisis; front month elevated above back)

Position sizing: 10% overlay on top of H031 (H031 = 90%, H033 = 10%)

Approach A — Direct VIX roll proxy
  Signal: if VIX3M/VIX > 1.0 AND VIX_start < 30 at month-open:
    short_vol_return = (VIX_prev - VIX_curr) / VIX_prev  (× position)
  Spike guard: if monthly MAX_VIX > 30 during the month:
    return = -15% on the 10% overlay (= -1.5% drag on full portfolio)
  Otherwise flat.

Approach B — Rule-based (simpler, less noisy)
  if VIX_start > 30                : short_vol_return = -15%  (panic)
  elif VIX/VIX3M < 0.90 (steep)   : short_vol_return =  +2%  (full contango)
  elif VIX/VIX3M in [0.90, 1.0)   : short_vol_return =  +0%  (mild contango, flat)
  elif VIX/VIX3M >= 1.0           : short_vol_return =   0%  (backwardation, flat)

Both approaches use the PRIOR month-end VIX signal (no look-ahead).

Period: 2007-01-01 → 2026-04-27 (bounded by VIX3M data availability)

Outputs
-------
  /workspace/agent/backtesting/results/h033_results.json
"""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

FULL_START     = "2007-01-01"
FULL_END       = "2026-04-27"
INITIAL_EQUITY = 100_000.0

# H033 overlay parameters
OVERLAY_SIZE         = 0.10   # 10% of portfolio in short-vol position
BASE_SIZE            = 1.0 - OVERLAY_SIZE  # 90% rides H031

VIX_PANIC_THRESHOLD  = 30.0
CONTANGO_STEEP_RATIO = 0.90   # VIX/VIX3M < 0.90 = steep contango
RULE_BASED_MONTHLY   = 0.02   # +2%/month in steep contango
SPIKE_LOSS           = -0.15  # -15% on position during panic

# H031 component assets
H20_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF    = "SHY"
TOP_N_H20   = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

IBS_BUY  = 0.20
IBS_SELL = 0.80
MAX_HOLD = 5

CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h033_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw
    closes = closes.dropna(how="all")
    closes.columns = [str(c) for c in closes.columns]
    closes.to_parquet(cp)
    return closes


def fetch_ohlc_spy(start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h033_spy_ohlc_{start}_{end}.parquet"
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
# H031 sub-strategy equity curves  (copied & adapted from run_h031.py)
# ─────────────────────────────────────────────────────────────────────────────

def h020_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [a for a in H20_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H20 + 1 or CASH_ETF not in prices.columns:
        return pd.Series(dtype=float)

    px = prices[available + [CASH_ETF]].loc[start:end].dropna(how="all")
    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H20 + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top      = list(combined.nlargest(TOP_N_H20).index)
        rest     = [s for s in valid if s not in top]
        cash_wt  = len(rest) / len(valid)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0, p1 = float(sub[sym].iloc[j - 1]), float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / TOP_N_H20
            if cash_wt > 0:
                p0, p1 = float(sub[CASH_ETF].iloc[j - 1]), float(sub[CASH_ETF].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def h026_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].loc[start:end].dropna(how="all")
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
            port_ret = sum(
                weight * (float(sub[sym].iloc[j]) / float(sub[sym].iloc[j - 1]) - 1)
                for sym in top_hold
                if float(sub[sym].iloc[j - 1]) > 0
                and not np.isnan(float(sub[sym].iloc[j - 1]))
                and not np.isnan(float(sub[sym].iloc[j]))
            )
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def h009_equity_curve(ohlc: pd.DataFrame, start: str, end: str) -> pd.Series:
    df = ohlc.loc[start:end].copy()
    ibs = ((df["close"] - df["low"]) /
           (df["high"] - df["low"])).replace([np.inf, -np.inf], np.nan).fillna(0.5)

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []

    for i in range(1, len(ibs)):
        c_prev = float(df["close"].iloc[i - 1])
        c_curr = float(df["close"].iloc[i])
        ret    = c_curr / c_prev - 1 if c_prev > 0 else 0.0

        if position == 1:
            equity   *= (1 + ret)
            days_held += 1
            if float(ibs.iloc[i]) > IBS_SELL or days_held >= MAX_HOLD:
                position = days_held = 0
        else:
            if float(ibs.iloc[i - 1]) < IBS_BUY:
                position  = 1
                days_held = 1
                equity   *= (1 + ret)

        series.append((df.index[i], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


def build_h031_monthly(
    r_h020: pd.Series,
    r_h026: pd.Series,
    r_h009: pd.Series,
    w_h020: float = 0.60,
    w_h026: float = 0.20,
    w_h009: float = 0.20,
) -> pd.Series:
    """Blend three strategies on their common date range."""
    common = r_h020.index.intersection(r_h026.index).intersection(r_h009.index)
    return (w_h020 * r_h020.loc[common]
            + w_h026 * r_h026.loc[common]
            + w_h009 * r_h009.loc[common])


# ─────────────────────────────────────────────────────────────────────────────
# VIX / VIX3M data
# ─────────────────────────────────────────────────────────────────────────────

def load_vix_monthly(start: str, end: str) -> pd.DataFrame:
    """
    Returns monthly DataFrame with columns:
      vix_close    - VIX spot at month-end
      vix3m_close  - VIX3M at month-end
      vix_ratio    - VIX / VIX3M (< 1.0 = contango)
      contango_ratio - VIX3M / VIX (> 1.0 = contango)
      vix_max      - max VIX level during the month
    """
    cp = CACHE_DIR / f"h033_vix_monthly_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)

    print("  Downloading ^VIX and ^VIX3M …")
    vix_raw = yf.download(["^VIX", "^VIX3M"], start=start, end=end,
                          auto_adjust=True, progress=False)
    vix_raw.columns = [str(c) for c in vix_raw.columns]

    # Find close columns — yfinance MultiIndex is (Price, Ticker) or (Ticker, Price)
    if isinstance(vix_raw.columns, pd.MultiIndex):
        # Detect level ordering
        lvl0 = [str(v) for v in vix_raw.columns.get_level_values(0).unique()]
        lvl1 = [str(v) for v in vix_raw.columns.get_level_values(1).unique()]
        if "Close" in lvl0:
            # (Price, Ticker) ordering
            vix_close   = vix_raw["Close"]["^VIX"].dropna()
            vix3m_close = vix_raw["Close"]["^VIX3M"].dropna()
            vix_high    = vix_raw["High"]["^VIX"].dropna()
        elif "Close" in lvl1:
            # (Ticker, Price) ordering
            vix_close   = vix_raw["^VIX"]["Close"].dropna()
            vix3m_close = vix_raw["^VIX3M"]["Close"].dropna()
            vix_high    = vix_raw["^VIX"]["High"].dropna()
        else:
            raise ValueError(f"Cannot find 'Close' in MultiIndex levels: lvl0={lvl0} lvl1={lvl1}")
    else:
        # Single ticker flat download (unexpected but handle gracefully)
        cols = [str(c) for c in vix_raw.columns]
        vix_col   = next((c for c in cols if "VIX" in c and "3M" not in c), None)
        vix3m_col = next((c for c in cols if "3M" in c), None)
        if not vix_col or not vix3m_col:
            raise ValueError(f"Flat columns don't contain VIX/VIX3M: {cols}")
        vix_close   = vix_raw[vix_col].dropna()
        vix3m_close = vix_raw[vix3m_col].dropna()
        vix_high    = vix_raw[vix_col].dropna()  # no High available, use Close as proxy

    # Build daily frame
    daily = pd.DataFrame({
        "vix":     vix_close,
        "vix3m":   vix3m_close,
        "vix_high": vix_high,
    }).dropna()

    # Monthly aggregation
    monthly = pd.DataFrame({
        "vix_close":     daily["vix"].resample("ME").last(),
        "vix3m_close":   daily["vix3m"].resample("ME").last(),
        "vix_max":       daily["vix_high"].resample("ME").max(),   # intra-month spike
        "vix_start":     daily["vix"].resample("ME").first(),      # month-open VIX
    }).dropna()

    monthly["vix_ratio"]     = monthly["vix_close"] / monthly["vix3m_close"]
    monthly["contango_ratio"] = monthly["vix3m_close"] / monthly["vix_close"]
    monthly.to_parquet(cp)
    return monthly


# ─────────────────────────────────────────────────────────────────────────────
# H033 signal engines
# ─────────────────────────────────────────────────────────────────────────────

def h033_returns_approach_a(
    vix_monthly: pd.DataFrame,
    overlay_size: float = OVERLAY_SIZE,
    panic_threshold: float = VIX_PANIC_THRESHOLD,
    min_contango_ratio: float = 1.0,
) -> pd.Series:
    """
    Approach A — Direct VIX Roll Proxy.

    For each month:
      Signal is set at PRIOR month-end (no look-ahead):
        if prev_vix < panic_threshold AND prev_vix3m/prev_vix > min_contango_ratio:
          hold short-vol (position = 1)
        else:
          flat (position = 0)

      When position = 1:
        If VIX max during month exceeds panic_threshold:
          return = SPIKE_LOSS  (simulate futures blow-up)
        Else:
          return = (vix_prev_close - vix_curr_close) / vix_prev_close
          (positive when VIX falls, negative when VIX rises)

    Final overlay return = position * raw_return * overlay_size
    """
    records = []
    months = vix_monthly.index

    for i in range(1, len(months)):
        curr_month = months[i]
        prev_month = months[i - 1]

        vix_prev     = float(vix_monthly.loc[prev_month, "vix_close"])
        vix3m_prev   = float(vix_monthly.loc[prev_month, "vix3m_close"])
        vix_curr     = float(vix_monthly.loc[curr_month, "vix_close"])
        vix_max_curr = float(vix_monthly.loc[curr_month, "vix_max"])

        # Signal: use prior month-end levels
        contango = vix3m_prev > vix_prev * min_contango_ratio
        is_panic_entry = vix_prev >= panic_threshold

        position = 1 if (contango and not is_panic_entry) else 0

        if position == 0:
            raw_return = 0.0
            signal_type = "flat"
        elif vix_max_curr >= panic_threshold:
            # VIX spiked during the month — simulate futures stop-out
            raw_return  = SPIKE_LOSS
            signal_type = "spike_loss"
        else:
            # Normal short-vol return: profit from VIX mean reversion
            raw_return  = (vix_prev - vix_curr) / vix_prev
            signal_type = "short_vol"

        overlay_return = position * raw_return * overlay_size

        records.append({
            "month":          curr_month,
            "vix_prev":       round(vix_prev, 2),
            "vix3m_prev":     round(vix3m_prev, 2),
            "vix_ratio_prev": round(vix_prev / vix3m_prev, 4),
            "vix_curr":       round(vix_curr, 2),
            "vix_max_curr":   round(vix_max_curr, 2),
            "position":       position,
            "raw_return":     round(raw_return, 6),
            "overlay_return": round(overlay_return, 6),
            "signal_type":    signal_type,
        })

    df = pd.DataFrame(records).set_index("month")
    return df["overlay_return"], df


def h033_returns_approach_b(
    vix_monthly: pd.DataFrame,
    overlay_size: float = OVERLAY_SIZE,
    panic_threshold: float = VIX_PANIC_THRESHOLD,
    steep_contango_ratio: float = CONTANGO_STEEP_RATIO,
    rule_return: float = RULE_BASED_MONTHLY,
) -> pd.Series:
    """
    Approach B — Rule-based (simpler, more conservative).

    Signal at PRIOR month-end:
      if prev_vix > panic_threshold     → position: "panic" → SPIKE_LOSS this month
      elif prev_vix/prev_vix3m < steep  → position: "steep_contango" → +rule_return
      elif prev_vix/prev_vix3m < 1.0    → position: "mild_contango" → +0% (flat)
      else (backwardation)               → position: "flat" → +0%

    Final overlay return = raw_return * overlay_size
    """
    records = []
    months = vix_monthly.index

    for i in range(1, len(months)):
        curr_month = months[i]
        prev_month = months[i - 1]

        vix_prev   = float(vix_monthly.loc[prev_month, "vix_close"])
        vix3m_prev = float(vix_monthly.loc[prev_month, "vix3m_close"])
        ratio_prev = vix_prev / vix3m_prev

        if vix_prev > panic_threshold:
            raw_return  = SPIKE_LOSS
            signal_type = "panic"
        elif ratio_prev < steep_contango_ratio:
            raw_return  = rule_return
            signal_type = "steep_contango"
        elif ratio_prev < 1.0:
            raw_return  = 0.0
            signal_type = "mild_contango"
        else:
            raw_return  = 0.0
            signal_type = "backwardation"

        overlay_return = raw_return * overlay_size

        records.append({
            "month":          curr_month,
            "vix_prev":       round(vix_prev, 2),
            "vix3m_prev":     round(vix3m_prev, 2),
            "vix_ratio_prev": round(ratio_prev, 4),
            "raw_return":     round(raw_return, 6),
            "overlay_return": round(overlay_return, 6),
            "signal_type":    signal_type,
        })

    df = pd.DataFrame(records).set_index("month")
    return df["overlay_return"], df


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets: pd.Series, label: str = "") -> dict:
    monthly_rets = monthly_rets.dropna()
    n = len(monthly_rets)
    if n < 12:
        return {"error": "insufficient data"}
    equity  = (1 + monthly_rets).cumprod()
    n_years = n / 12.0
    cagr    = float(equity.iloc[-1] ** (1 / n_years) - 1)
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    win_rate = float((monthly_rets > 0).mean())
    worst_m  = float(monthly_rets.min())
    best_m   = float(monthly_rets.max())
    # worst month label
    worst_idx = monthly_rets.idxmin()
    best_idx  = monthly_rets.idxmax()

    return {
        "label":            label,
        "cagr":             round(cagr,   4),
        "sharpe":           round(sharpe, 4),
        "max_drawdown":     round(max_dd, 4),
        "calmar":           round(calmar, 4),
        "ann_vol":          round(vol,    4),
        "win_rate":         round(win_rate, 4),
        "worst_month":      round(worst_m, 4),
        "worst_month_date": str(worst_idx.date()) if hasattr(worst_idx, "date") else str(worst_idx),
        "best_month":       round(best_m, 4),
        "best_month_date":  str(best_idx.date()) if hasattr(best_idx, "date") else str(best_idx),
        "n_months":         n,
        "n_years":          round(n_years, 1),
    }


def signal_summary(detail_df: pd.DataFrame) -> dict:
    """Summarise H033 signal regime counts and average returns per regime."""
    counts = detail_df["signal_type"].value_counts().to_dict()
    total  = len(detail_df)
    avg_by_regime = (
        detail_df.groupby("signal_type")["raw_return"]
        .agg(["mean", "count"])
        .round(6)
        .to_dict(orient="index")
    )
    return {
        "total_months": total,
        "regime_counts": {k: int(v) for k, v in counts.items()},
        "regime_pct":    {k: round(int(v) / total, 4) for k, v in counts.items()},
        "avg_raw_return_by_regime": {
            k: {"mean": round(v["mean"], 6), "count": int(v["count"])}
            for k, v in avg_by_regime.items()
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H033 — Short Volatility Premium Overlay on H031")
    print("=" * 72)

    # ── 1. Fetch price data ──────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H20_ASSETS + [CASH_ETF] + SECTOR_ETFS))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h033_base")

    spy_ohlc = fetch_ohlc_spy(FULL_START, FULL_END)

    # ── 2. VIX data ──────────────────────────────────────────────────────────
    print("\n[2] Fetching VIX / VIX3M term structure data …")
    vix_monthly = load_vix_monthly("2004-01-01", FULL_END)

    vix_start_actual = vix_monthly.index[0]
    vix_end_actual   = vix_monthly.index[-1]
    n_vix_months     = len(vix_monthly)
    print(f"  VIX3M data: {vix_start_actual.date()} → {vix_end_actual.date()} ({n_vix_months} months)")

    # VIX statistics
    n_contango    = int((vix_monthly["vix_ratio"] < 1.0).sum())
    n_steep       = int((vix_monthly["vix_ratio"] < CONTANGO_STEEP_RATIO).sum())
    n_backwardation = int((vix_monthly["vix_ratio"] >= 1.0).sum())
    n_panic       = int((vix_monthly["vix_close"] > VIX_PANIC_THRESHOLD).sum())
    print(f"  Regime breakdown ({n_vix_months} months):")
    print(f"    Contango (VIX/VIX3M < 1.0) : {n_contango:>4}  ({n_contango/n_vix_months:.1%})")
    print(f"    Steep contango (ratio<0.90): {n_steep:>4}  ({n_steep/n_vix_months:.1%})")
    print(f"    Backwardation (ratio>=1.0) : {n_backwardation:>4}  ({n_backwardation/n_vix_months:.1%})")
    print(f"    Panic (VIX>30)             : {n_panic:>4}  ({n_panic/n_vix_months:.1%})")

    # ── 3. Build H031 monthly returns ────────────────────────────────────────
    print("\n[3] Building H031 component equity curves …")
    eq_h020 = h020_equity_curve(prices, FULL_START, FULL_END)
    eq_h026 = h026_equity_curve(prices, FULL_START, FULL_END)
    eq_h009 = h009_equity_curve(spy_ohlc, FULL_START, FULL_END)

    r_h020_all = to_monthly_returns(eq_h020)
    r_h026_all = to_monthly_returns(eq_h026)
    r_h009_all = to_monthly_returns(eq_h009)

    # Common date range across all three H031 components
    common_idx = (
        r_h020_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h009_all.index)
    )
    r_h020 = r_h020_all.loc[common_idx]
    r_h026 = r_h026_all.loc[common_idx]
    r_h009 = r_h009_all.loc[common_idx]

    # Best H031 weights from prior optimisation (from h031_results.json continuous grid)
    # max-Sharpe: H020=60%, H026=20%, H009=20%
    W_H020, W_H026, W_H009 = 0.60, 0.20, 0.20
    r_h031_all = build_h031_monthly(r_h020, r_h026, r_h009, W_H020, W_H026, W_H009)

    # ── 4. Align to VIX3M availability window ────────────────────────────────
    # VIX3M data starts mid-2007; restrict common window
    vix_in_range = vix_monthly.loc[FULL_START:]
    common_with_vix = r_h031_all.index.intersection(
        vix_in_range.index[1:]  # shift by 1 because we use PRIOR month signal
    )

    r_h031 = r_h031_all.loc[common_with_vix]
    vix_window = vix_in_range.loc[
        vix_in_range.index[vix_in_range.index < common_with_vix[0]].union(common_with_vix)
    ]

    sim_start = common_with_vix[0]
    sim_end   = common_with_vix[-1]
    n_months  = len(common_with_vix)
    n_years   = n_months / 12.0

    print(f"\n  Common simulation window: {sim_start.date()} → {sim_end.date()}")
    print(f"  {n_months} months ({n_years:.1f} years)")
    print(f"  H031 weights used: H020={W_H020:.0%}  H026={W_H026:.0%}  H009={W_H009:.0%}")

    # ── 5. H033 overlay: both approaches ────────────────────────────────────
    print("\n[4] Computing H033 overlay returns (Approach A — direct VIX proxy) …")
    r_a_raw, detail_a = h033_returns_approach_a(vix_window)
    r_a = r_a_raw.reindex(common_with_vix).fillna(0.0)

    print("[5] Computing H033 overlay returns (Approach B — rule-based) …")
    r_b_raw, detail_b = h033_returns_approach_b(vix_window)
    r_b = r_b_raw.reindex(common_with_vix).fillna(0.0)

    # ── 6. Blend: H031 (90%) + H033 (10%) ───────────────────────────────────
    print("\n[6] Blending: H031×90% + H033×10% …")
    r_blend_a = BASE_SIZE * r_h031 + r_a   # overlay_return already scaled by overlay_size
    r_blend_b = BASE_SIZE * r_h031 + r_b

    # ── 7. SPY benchmark on same window ──────────────────────────────────────
    print("[7] Building SPY benchmark …")
    spy_prices = prices["SPY"].loc[sim_start:sim_end].dropna() if "SPY" in prices.columns else pd.Series()
    if len(spy_prices) > 1:
        spy_monthly_eq = INITIAL_EQUITY * (spy_prices / spy_prices.iloc[0])
        r_spy = to_monthly_returns(spy_monthly_eq).reindex(common_with_vix).dropna()
    else:
        r_spy = pd.Series(dtype=float)

    # ── 8. Statistics ────────────────────────────────────────────────────────
    print("\n[8] Computing statistics …")

    # H031 alone stats (restricted to VIX window)
    s_h031 = stats_from_monthly_returns(r_h031, "H031 alone (90% base)")
    s_blend_a = stats_from_monthly_returns(r_blend_a, "H031×90% + H033-A×10%")
    s_blend_b = stats_from_monthly_returns(r_blend_b, "H031×90% + H033-B×10%")
    s_spy     = stats_from_monthly_returns(r_spy, "SPY buy-and-hold") if len(r_spy) > 12 else {}

    # Overlay-only stats (for analysis)
    s_h033_a = stats_from_monthly_returns(r_a / OVERLAY_SIZE, "H033-A short-vol standalone")
    s_h033_b = stats_from_monthly_returns(r_b / OVERLAY_SIZE, "H033-B short-vol standalone")

    # ── 9. VIX regime signal summary ────────────────────────────────────────
    detail_a_window = detail_a.loc[detail_a.index.isin(common_with_vix)]
    detail_b_window = detail_b.loc[detail_b.index.isin(common_with_vix)]
    sig_summary_a = signal_summary(detail_a_window)
    sig_summary_b = signal_summary(detail_b_window)

    # ── 10. Print comparison table ───────────────────────────────────────────
    print()
    print("=" * 80)
    print("  H033 RESULTS — Short Volatility Premium Overlay")
    print(f"  Period: {sim_start.date()} → {sim_end.date()}  ({n_months} months, {n_years:.1f} yrs)")
    print("=" * 80)

    header = f"  {'Strategy':<38}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>8}  {'Calmar':>7}  {'AnnVol':>7}  {'WinRate':>8}"
    print(header)
    print("  " + "-" * 76)

    rows = [
        ("H031 alone (baseline, 90% scale)",  s_h031),
        ("H031×90% + H033-A (direct proxy)",  s_blend_a),
        ("H031×90% + H033-B (rule-based)",    s_blend_b),
        ("H033-A standalone  (×10 unscaled)", s_h033_a),
        ("H033-B standalone  (×10 unscaled)", s_h033_b),
        ("SPY buy-and-hold",                  s_spy),
    ]
    for name, s in rows:
        if not s or "error" in s:
            print(f"  {name:<38}  (no data)")
            continue
        print(
            f"  {name:<38}  {s['cagr']:>6.2%}  {s['sharpe']:>7.3f}  "
            f"{s['max_drawdown']:>7.2%}  {s['calmar']:>7.3f}  "
            f"{s['ann_vol']:>6.2%}  {s['win_rate']:>8.1%}"
        )

    print()
    print("  Worst single month:")
    for name, s in [("H031 alone", s_h031), ("H031+H033-A", s_blend_a), ("H031+H033-B", s_blend_b)]:
        if not s or "error" in s:
            continue
        print(f"    {name:<20}  {s['worst_month']:>7.2%}  ({s['worst_month_date']})")

    print()
    print("  Approach A signal regimes (months in window):")
    for regime, info in sig_summary_a["avg_raw_return_by_regime"].items():
        pct = sig_summary_a["regime_counts"].get(regime, 0) / sig_summary_a["total_months"]
        print(f"    {regime:<22}  {sig_summary_a['regime_counts'].get(regime,0):>4} months "
              f"({pct:.1%})  avg raw return = {info['mean']:>+.2%}")

    print()
    print("  Approach B signal regimes (months in window):")
    for regime, info in sig_summary_b["avg_raw_return_by_regime"].items():
        pct = sig_summary_b["regime_counts"].get(regime, 0) / sig_summary_b["total_months"]
        print(f"    {regime:<22}  {sig_summary_b['regime_counts'].get(regime,0):>4} months "
              f"({pct:.1%})  avg raw return = {info['mean']:>+.2%}")

    # Lift analysis
    print()
    print("  Overlay lift vs H031 baseline (CAGR/Sharpe/MaxDD):")
    for name, s_blend in [("H033-A", s_blend_a), ("H033-B", s_blend_b)]:
        if s_blend and "error" not in s_blend and s_h031 and "error" not in s_h031:
            cagr_lift   = s_blend["cagr"] - s_h031["cagr"]
            sharpe_lift = s_blend["sharpe"] - s_h031["sharpe"]
            dd_change   = s_blend["max_drawdown"] - s_h031["max_drawdown"]
            print(f"    {name}:  CAGR {cagr_lift:>+.2%}  "
                  f"Sharpe {sharpe_lift:>+.3f}  "
                  f"MaxDD {dd_change:>+.2%}")

    # ── 11. Save results ─────────────────────────────────────────────────────
    output = {
        "strategy": "H033 — Short Volatility Premium Overlay on H031",
        "description": (
            "10% short-vol overlay using VIX/VIX3M term structure. "
            "90% of portfolio stays in H031 (60% H020 + 20% H026 + 20% H009). "
            "Approach A: direct VIX return proxy. Approach B: rule-based monthly returns."
        ),
        "simulation_window": {
            "start":    str(sim_start.date()),
            "end":      str(sim_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
        },
        "parameters": {
            "overlay_size":          OVERLAY_SIZE,
            "base_size":             BASE_SIZE,
            "h031_weights":          {"h020": W_H020, "h026": W_H026, "h009": W_H009},
            "vix_panic_threshold":   VIX_PANIC_THRESHOLD,
            "steep_contango_ratio":  CONTANGO_STEEP_RATIO,
            "rule_based_monthly_b":  RULE_BASED_MONTHLY,
            "spike_loss":            SPIKE_LOSS,
        },
        "vix_regime_summary": {
            "n_months":         n_vix_months,
            "n_contango":       n_contango,
            "pct_contango":     round(n_contango / n_vix_months, 4),
            "n_steep_contango": n_steep,
            "pct_steep":        round(n_steep / n_vix_months, 4),
            "n_backwardation":  n_backwardation,
            "pct_backwardation": round(n_backwardation / n_vix_months, 4),
            "n_panic":          n_panic,
            "pct_panic":        round(n_panic / n_vix_months, 4),
        },
        "stats": {
            "h031_alone":     s_h031,
            "h031_h033a":     s_blend_a,
            "h031_h033b":     s_blend_b,
            "h033a_standalone": s_h033_a,
            "h033b_standalone": s_h033_b,
            "spy_bh":         s_spy,
        },
        "signal_summary": {
            "approach_a": sig_summary_a,
            "approach_b": sig_summary_b,
        },
        "overlay_lift": {
            "h033a_vs_h031": {
                "cagr_lift":   round(s_blend_a["cagr"] - s_h031["cagr"], 4)
                               if s_blend_a and "error" not in s_blend_a else None,
                "sharpe_lift": round(s_blend_a["sharpe"] - s_h031["sharpe"], 4)
                               if s_blend_a and "error" not in s_blend_a else None,
                "maxdd_change": round(s_blend_a["max_drawdown"] - s_h031["max_drawdown"], 4)
                               if s_blend_a and "error" not in s_blend_a else None,
            },
            "h033b_vs_h031": {
                "cagr_lift":   round(s_blend_b["cagr"] - s_h031["cagr"], 4)
                               if s_blend_b and "error" not in s_blend_b else None,
                "sharpe_lift": round(s_blend_b["sharpe"] - s_h031["sharpe"], 4)
                               if s_blend_b and "error" not in s_blend_b else None,
                "maxdd_change": round(s_blend_b["max_drawdown"] - s_h031["max_drawdown"], 4)
                               if s_blend_b and "error" not in s_blend_b else None,
            },
        },
        "month_detail": {
            "approach_a": detail_a_window.reset_index().to_dict(orient="records"),
            "approach_b": detail_b_window.reset_index().to_dict(orient="records"),
        },
        "run_date": FULL_END,
    }

    out_path = RESULTS_DIR / "h033_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
