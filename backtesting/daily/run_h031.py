"""
H031 — Three-Way Blend: H020 + H026 + H009
============================================

Adds H009 (SPY IBS daily mean-reversion) to the H028 blend (H020+H026).
Finds optimal three-way weights by grid search.

Grid:
  H020: 40%, 50%, 60%, 70%
  H026: 10%, 20%, 30%, 40%
  H009: remainder (1 - H020 - H026), only valid combos where H009 >= 0

Includes:
  - Continuous optimisation (1001-point sweep in 2D) for max-Sharpe and min-MaxDD
  - Comparison to H028 (two-way), H018 (H020+H009 only), and each standalone

Common period: 2003-08-31 → 2026-04-26 (limited by H026 sector data warmup)

Outputs:
  /workspace/agent/backtesting/results/h031_results.json
"""

import json
import itertools
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FULL_START = "2000-01-01"
FULL_END   = "2026-04-27"

# ── Asset universes ──────────────────────────────────────────────────────────
H20_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF    = "SHY"
TOP_N_H20   = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26   = 3

IBS_BUY  = 0.20
IBS_SELL = 0.80
MAX_HOLD = 5


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h031_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc_spy(start: str, end: str) -> pd.DataFrame:
    """Return SPY OHLC with lowercase column names."""
    cp = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
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
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets: pd.Series) -> dict:
    """Compute CAGR, Sharpe, MaxDD, AnnVol from monthly return series."""
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"error": "insufficient data"}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = (equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H020 equity curve (SPY/QQQ/TLT/GLD/IEF macro rotation)
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
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / TOP_N_H20
            if cash_wt > 0:
                p0 = float(sub[CASH_ETF].iloc[j - 1])
                p1 = float(sub[CASH_ETF].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# H026 equity curve (11 sector ETF top-3 momentum)
# ─────────────────────────────────────────────────────────────────────────────

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
# H009 equity curve (SPY IBS daily mean-reversion, close-to-close simulation)
# ─────────────────────────────────────────────────────────────────────────────

def h009_equity_curve(ohlc: pd.DataFrame, start: str, end: str) -> pd.Series:
    """
    H009: IBS mean-reversion on SPY.

    Signal (no look-ahead):
      - IBS[t] = (Close[t] - Low[t]) / (High[t] - Low[t])
      - Enter long at Close[t] if IBS[t-1] < IBS_BUY and not in position
      - Exit at Close[t] if in position AND (IBS[t] > IBS_SELL OR days_held >= MAX_HOLD)
      - 100% of H009 capital when in position

    Returns daily equity series (starting at INITIAL_EQUITY).
    """
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
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# Convert daily equity → monthly returns
# ─────────────────────────────────────────────────────────────────────────────

def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Three-way grid search
# ─────────────────────────────────────────────────────────────────────────────

def threeway_grid(
    r_h020: pd.Series,
    r_h026: pd.Series,
    r_h009: pd.Series,
    h020_range,  # e.g. [0.4, 0.5, 0.6, 0.7]
    h026_range,  # e.g. [0.1, 0.2, 0.3, 0.4]
) -> list:
    """
    Test all valid (w20, w26, w09) combos where w09 = 1 - w20 - w26 >= 0.
    Returns list of dicts sorted by Sharpe descending.
    """
    common = r_h020.index.intersection(r_h026.index).intersection(r_h009.index)
    r1 = r_h020.loc[common].values
    r2 = r_h026.loc[common].values
    r3 = r_h009.loc[common].values

    results = []
    for w20 in h020_range:
        for w26 in h026_range:
            w09 = round(1.0 - w20 - w26, 6)
            if w09 < -1e-9:
                continue
            w09 = max(w09, 0.0)
            r_blend = w20 * r1 + w26 * r2 + w09 * r3
            n_years = len(r_blend) / 12.0
            cagr    = float(np.prod(1 + r_blend) ** (1 / n_years) - 1)
            vol     = float(np.std(r_blend, ddof=1)) * np.sqrt(12)
            sharpe  = cagr / vol if vol > 0 else 0.0
            equity  = np.cumprod(1 + r_blend)
            roll_max = np.maximum.accumulate(equity)
            max_dd  = float(np.min(equity / roll_max - 1))
            calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
            results.append({
                "w_h020":       round(w20, 4),
                "w_h026":       round(w26, 4),
                "w_h009":       round(w09, 4),
                "cagr":         round(cagr,   4),
                "sharpe":       round(sharpe,  4),
                "max_drawdown": round(max_dd,  4),
                "calmar":       round(calmar,  4),
                "ann_vol":      round(vol,     4),
                "n_months":     len(r_blend),
            })

    return sorted(results, key=lambda x: x["sharpe"], reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# Continuous 2D optimisation: sweep w20 and w26 on a fine grid
# ─────────────────────────────────────────────────────────────────────────────

def find_optimal_threeway(
    r_h020: pd.Series,
    r_h026: pd.Series,
    r_h009: pd.Series,
    n_steps: int = 101,  # steps per axis → ~5000 valid combos
) -> dict:
    """
    Fine sweep over (w20, w26) to find max-Sharpe and min-MaxDD blends.
    w09 = 1 - w20 - w26 is forced >= 0.
    """
    common = r_h020.index.intersection(r_h026.index).intersection(r_h009.index)
    r1 = r_h020.loc[common].values
    r2 = r_h026.loc[common].values
    r3 = r_h009.loc[common].values
    n_years = len(r1) / 12.0

    best_sharpe  = -np.inf
    best_sharpe_w = (0.6, 0.3, 0.1)
    min_maxdd    = -np.inf   # track the LEAST-negative drawdown (closest to zero)
    min_maxdd_w  = (0.6, 0.3, 0.1)

    axis = np.linspace(0, 1, n_steps)
    for w20 in axis:
        for w26 in axis:
            w09 = 1.0 - w20 - w26
            if w09 < 0:
                continue
            r_blend = w20 * r1 + w26 * r2 + w09 * r3
            cagr    = float(np.prod(1 + r_blend) ** (1 / n_years) - 1)
            vol     = float(np.std(r_blend, ddof=1)) * np.sqrt(12)
            sharpe  = cagr / vol if vol > 0 else 0.0
            equity  = np.cumprod(1 + r_blend)
            roll_max = np.maximum.accumulate(equity)
            max_dd  = float(np.min(equity / roll_max - 1))

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_sharpe_w = (w20, w26, w09)
            if max_dd > min_maxdd:
                min_maxdd = max_dd
                min_maxdd_w = (w20, w26, w09)

    def stats_at(w20, w26, w09):
        r_blend = w20 * r1 + w26 * r2 + w09 * r3
        cagr    = float(np.prod(1 + r_blend) ** (1 / n_years) - 1)
        vol     = float(np.std(r_blend, ddof=1)) * np.sqrt(12)
        sharpe  = cagr / vol if vol > 0 else 0.0
        equity  = np.cumprod(1 + r_blend)
        roll_max = np.maximum.accumulate(equity)
        max_dd  = float(np.min(equity / roll_max - 1))
        calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
        return {
            "w_h020":       round(w20, 4),
            "w_h026":       round(w26, 4),
            "w_h009":       round(w09, 4),
            "cagr":         round(cagr,  4),
            "sharpe":       round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "calmar":       round(calmar, 4),
            "ann_vol":      round(vol,   4),
            "n_months":     len(r_blend),
        }

    return {
        "max_sharpe": stats_at(*best_sharpe_w),
        "min_maxdd":  stats_at(*min_maxdd_w),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H018 (H020 + H009 blend) — replicate for comparison
# ─────────────────────────────────────────────────────────────────────────────

def build_h018_monthly_returns(
    r_h020: pd.Series,
    r_h009: pd.Series,
    w_h020: float = 0.5,
) -> pd.Series:
    """Simple w_h020 / (1-w_h020) blend of H020 and H009 on common dates."""
    common = r_h020.index.intersection(r_h009.index)
    return w_h020 * r_h020.loc[common] + (1 - w_h020) * r_h009.loc[common]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H031 — Three-Way Blend: H020 + H026 + H009")
    print("=" * 72)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H20_ASSETS + [CASH_ETF] + SECTOR_ETFS))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h031_all")
    spy_ohlc = fetch_ohlc_spy(FULL_START, FULL_END)

    # ── 2. Build individual equity curves ───────────────────────────────────
    print("\n[2] Building H020 equity curve …")
    eq_h020 = h020_equity_curve(prices, FULL_START, FULL_END)

    print("[3] Building H026 equity curve …")
    eq_h026 = h026_equity_curve(prices, FULL_START, FULL_END)

    print("[4] Building H009 daily equity curve …")
    eq_h009 = h009_equity_curve(spy_ohlc, FULL_START, FULL_END)

    if eq_h020.empty or eq_h026.empty or eq_h009.empty:
        print("ERROR: one or more equity curves are empty. Aborting.")
        return {}

    # ── 3. Convert to monthly returns ────────────────────────────────────────
    print("\n[5] Converting to monthly returns …")
    r_h020_all = to_monthly_returns(eq_h020)
    r_h026_all = to_monthly_returns(eq_h026)
    r_h009_all = to_monthly_returns(eq_h009)

    # Common period across all three
    common_idx = (
        r_h020_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h009_all.index)
    )
    r_h020 = r_h020_all.loc[common_idx]
    r_h026 = r_h026_all.loc[common_idx]
    r_h009 = r_h009_all.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    corr_20_26 = float(r_h020.corr(r_h026))
    corr_20_09 = float(r_h020.corr(r_h009))
    corr_26_09 = float(r_h026.corr(r_h009))

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")
    print(f"   Monthly correlations:  H020/H026={corr_20_26:.4f}  H020/H009={corr_20_09:.4f}  H026/H009={corr_26_09:.4f}")

    # ── 4. Standalone stats ───────────────────────────────────────────────────
    print("\n[6] Computing standalone stats …")
    s_h020 = stats_from_monthly_returns(r_h020)
    s_h026 = stats_from_monthly_returns(r_h026)
    s_h009 = stats_from_monthly_returns(r_h009)

    print(f"   H020: CAGR {s_h020['cagr']:.2%}  Sharpe {s_h020['sharpe']:.3f}  MaxDD {s_h020['max_drawdown']:.2%}")
    print(f"   H026: CAGR {s_h026['cagr']:.2%}  Sharpe {s_h026['sharpe']:.3f}  MaxDD {s_h026['max_drawdown']:.2%}")
    print(f"   H009: CAGR {s_h009['cagr']:.2%}  Sharpe {s_h009['sharpe']:.3f}  MaxDD {s_h009['max_drawdown']:.2%}")

    # ── 5. Grid search (coarse) ───────────────────────────────────────────────
    print("\n[7] Running three-way blend grid …")
    h020_range = [0.40, 0.50, 0.60, 0.70]
    h026_range = [0.10, 0.20, 0.30, 0.40]

    grid_results = threeway_grid(r_h020, r_h026, r_h009, h020_range, h026_range)

    print(f"\n{'=' * 84}")
    print("  THREE-WAY BLEND GRID: H020 / H026 / H009")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 84}")
    print(f"  {'H020':>6}  {'H026':>6}  {'H009':>6}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*80}")
    for row in grid_results:
        print(
            f"  {row['w_h020']:>6.0%}  {row['w_h026']:>6.0%}  {row['w_h009']:>6.0%}  "
            f"{row['cagr']:>8.2%}  {row['sharpe']:>8.3f}  {row['max_drawdown']:>8.2%}  "
            f"{row['ann_vol']:>8.2%}  {row['calmar']:>8.3f}"
        )

    best_sharpe_grid = grid_results[0]
    best_mindd_grid  = sorted(grid_results, key=lambda x: x["max_drawdown"], reverse=True)[0]
    print(f"\n  Grid best Sharpe : H020={best_sharpe_grid['w_h020']:.0%}  H026={best_sharpe_grid['w_h026']:.0%}  H009={best_sharpe_grid['w_h009']:.0%}  →  Sharpe {best_sharpe_grid['sharpe']:.4f}")
    print(f"  Grid min MaxDD   : H020={best_mindd_grid['w_h020']:.0%}  H026={best_mindd_grid['w_h026']:.0%}  H009={best_mindd_grid['w_h009']:.0%}  →  MaxDD {best_mindd_grid['max_drawdown']:.2%}")

    # ── 6. Continuous optimisation ────────────────────────────────────────────
    print("\n[8] Running continuous 2D optimisation (101×101 grid) …")
    optimal = find_optimal_threeway(r_h020, r_h026, r_h009, n_steps=101)

    opt_sharpe = optimal["max_sharpe"]
    opt_mindd  = optimal["min_maxdd"]

    print(f"\n  Continuous max-Sharpe : H020={opt_sharpe['w_h020']:.1%}  H026={opt_sharpe['w_h026']:.1%}  H009={opt_sharpe['w_h009']:.1%}")
    print(f"    CAGR {opt_sharpe['cagr']:.2%}  Sharpe {opt_sharpe['sharpe']:.4f}  MaxDD {opt_sharpe['max_drawdown']:.2%}  AnnVol {opt_sharpe['ann_vol']:.2%}")
    print(f"\n  Continuous min-MaxDD  : H020={opt_mindd['w_h020']:.1%}  H026={opt_mindd['w_h026']:.1%}  H009={opt_mindd['w_h009']:.1%}")
    print(f"    CAGR {opt_mindd['cagr']:.2%}  Sharpe {opt_mindd['sharpe']:.4f}  MaxDD {opt_mindd['max_drawdown']:.2%}  AnnVol {opt_mindd['ann_vol']:.2%}")

    # ── 7. H028 (two-way) on same window ────────────────────────────────────
    print("\n[9] Recomputing H028 (63/37) on three-way common window …")
    r_h028 = 0.628 * r_h020 + 0.372 * r_h026
    s_h028 = stats_from_monthly_returns(r_h028)
    print(f"   H028: CAGR {s_h028['cagr']:.2%}  Sharpe {s_h028['sharpe']:.3f}  MaxDD {s_h028['max_drawdown']:.2%}")

    # ── 8. H018 (H020+H009 50/50) on same window ────────────────────────────
    print("\n[10] Recomputing H018-style (H020+H009 50/50) on three-way common window …")
    r_h018 = build_h018_monthly_returns(r_h020, r_h009, w_h020=0.5)
    s_h018 = stats_from_monthly_returns(r_h018)
    print(f"   H018: CAGR {s_h018['cagr']:.2%}  Sharpe {s_h018['sharpe']:.3f}  MaxDD {s_h018['max_drawdown']:.2%}")

    # ── 9. Summary comparison table ──────────────────────────────────────────
    print(f"\n{'=' * 84}")
    print("  COMPARISON: Standalone vs Two-Way vs Three-Way")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 84}")
    print(f"  {'Strategy':<36}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*84}")

    comparison_rows = [
        ("H020 alone (5-asset macro)",         s_h020),
        ("H026 alone (sector ETF momentum)",   s_h026),
        ("H009 alone (SPY IBS daily)",         s_h009),
        ("H028 (H020 63%+H026 37%, two-way)",  s_h028),
        ("H018 (H020 50%+H009 50%, two-way)",  s_h018),
        ("H031 max-Sharpe (continuous)",       opt_sharpe),
        ("H031 min-MaxDD  (continuous)",       opt_mindd),
    ]

    for name, s in comparison_rows:
        if "error" in s:
            continue
        nm = s.get("n_months", "?")
        print(
            f"  {name:<36}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
            f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}"
        )

    # ── 10. Save results ──────────────────────────────────────────────────────
    output = {
        "strategy": "H031 — H020 + H026 + H009 Three-Way Blend",
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
        },
        "monthly_correlations": {
            "h020_h026": round(corr_20_26, 4),
            "h020_h009": round(corr_20_09, 4),
            "h026_h009": round(corr_26_09, 4),
        },
        "standalone": {
            "h020": s_h020,
            "h026": s_h026,
            "h009": s_h009,
        },
        "blend_grid": grid_results,
        "optimal": optimal,
        "comparisons": {
            "h028_two_way_on_common_window": s_h028,
            "h018_two_way_on_common_window": s_h018,
            "h031_max_sharpe": opt_sharpe,
            "h031_min_maxdd":  opt_mindd,
        },
        "run_date": FULL_END,
    }

    out_path = Path("/workspace/agent/backtesting/results/h031_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
