"""
H031b — Three-Way Blend: H020 + H026 + H037b (gap-filtered IBS)
================================================================

H031 recap:   H020 56% + H026 19% + H009 25%  → Sharpe 1.843, CAGR 14.63%, MaxDD -11.52%

H037b recap:  H009 IBS strategy with extra entry filter — skip entry if
              today's open gapped down > 0.5% vs yesterday's close.
              H009 standalone Sharpe improved from 0.873 → 1.021 (+17%).
              OOS Sharpe improved from 0.745 → 0.952 (+28%).

H031b changes only one thing vs H031: H009 → H037b (gap_filter = -0.005).

Grid:
  H020: 40%, 50%, 60%, 70%
  H026: 10%, 20%, 30%, 40%
  H037b: remainder (1 - H020 - H026), valid combos only

Includes:
  - Same coarse grid as H031
  - Continuous 101×101 sweep for max-Sharpe and min-MaxDD
  - Fixed-weight comparison: H031 optimal weights (56/19/25) applied to H037b
  - Side-by-side vs H031

Common period: 2003-08-31 → 2026-04-30 (same as H031)

Outputs:
  /workspace/agent/backtesting/results/h031b_results.json
  /workspace/agent/backtesting/daily/run_h031b.py  (this file)
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

FULL_START = "2000-01-01"
FULL_END   = "2026-04-27"

# ── Asset universes ──────────────────────────────────────────────────────────
H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF   = "SHY"
TOP_N_H20  = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26  = 3

# ── H009 / H037b params ──────────────────────────────────────────────────────
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005   # H037b: skip entry if gap < -0.5%


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h031_{h}.parquet"


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
    """Return SPY OHLC; reuses H031 cache when available."""
    cp_h031 = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
    if cp_h031.exists():
        df = pd.read_parquet(cp_h031)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs("SPY", axis=1, level=1) if "SPY" in df.columns.get_level_values(1) else df
        if not all(c in df.columns for c in ["open", "high", "low", "close"]):
            df = df.rename(columns=str.lower)
        return df
    cp = CACHE_DIR / f"h031b_spy_ohlc_{start}_{end}.parquet"
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
# H020 equity curve
# ─────────────────────────────────────────────────────────────────────────────

def h020_equity_curve(prices: pd.DataFrame) -> pd.Series:
    available = [a for a in H20_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H20 + 1 or CASH_ETF not in prices.columns:
        return pd.Series(dtype=float)

    px = prices[available + [CASH_ETF]].dropna(how="all")
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

        combined  = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top       = list(combined.nlargest(TOP_N_H20).index)
        rest      = [s for s in valid if s not in top]
        cash_wt   = len(rest) / len(valid)

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
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# H026 equity curve
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

        score     = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold  = list(score.nlargest(TOP_N_H26).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
                p0, p1 = float(sub[sym].iloc[j - 1]), float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# H037b equity curve (H009 + gap filter at -0.5%)
# ─────────────────────────────────────────────────────────────────────────────

def h037b_equity_curve(ohlc: pd.DataFrame) -> pd.Series:
    """
    H037b: IBS mean-reversion on SPY with gap-down filter.

    Entry signal (no look-ahead):
      - IBS[t-1] < IBS_BUY  (low IBS yesterday)
      - gap[t] = (Open[t] / Close[t-1]) - 1 >= -0.005  (not a big gap-down today)
      - Enter at Open[t]; equity change day 1 = Open→Close return

    Exit:
      - IBS[t] > IBS_SELL  OR  days_held >= MAX_HOLD
      - Exit at Close[t]; equity change = Close/prev_Close - 1

    Returns daily equity series starting at INITIAL_EQUITY.
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
        date      = df.index[i]
        prev_ibs  = float(ibs.iloc[i - 1])
        cur_ibs   = float(ibs.iloc[i])
        cur_gap   = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o         = float(df["open"].iloc[i])
        c         = float(df["close"].iloc[i])
        c_prev    = float(df["close"].iloc[i - 1])

        ret_oc = (c / o - 1)  if o > 0 else 0.0   # open→close (entry day)
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0   # close→close (hold days)

        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER_B:
                # Valid entry
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
# Grid search & continuous optimisation
# ─────────────────────────────────────────────────────────────────────────────

def threeway_grid(r1: pd.Series, r2: pd.Series, r3: pd.Series,
                  w1_range, w2_range,
                  label1="H020", label2="H026", label3="H037b") -> list:
    common = r1.index.intersection(r2.index).intersection(r3.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values

    results = []
    for w1 in w1_range:
        for w2 in w2_range:
            w3 = round(1.0 - w1 - w2, 6)
            if w3 < -1e-9:
                continue
            w3 = max(w3, 0.0)
            rb = w1 * a1 + w2 * a2 + w3 * a3
            n_years = len(rb) / 12.0
            cagr    = float(np.prod(1 + rb) ** (1 / n_years) - 1)
            vol     = float(np.std(rb, ddof=1)) * np.sqrt(12)
            sharpe  = cagr / vol if vol > 0 else 0.0
            eq      = np.cumprod(1 + rb)
            roll_mx = np.maximum.accumulate(eq)
            max_dd  = float(np.min(eq / roll_mx - 1))
            calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
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
                          label1="h020", label2="h026", label3="h037b") -> dict:
    common = r1.index.intersection(r2.index).intersection(r3.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    n_years = len(a1) / 12.0

    best_sharpe   = -np.inf
    best_sharpe_w = (0.6, 0.2, 0.2)
    min_maxdd     = -np.inf
    min_maxdd_w   = (0.6, 0.2, 0.2)

    axis = np.linspace(0, 1, n_steps)
    for w1 in axis:
        for w2 in axis:
            w3 = 1.0 - w1 - w2
            if w3 < 0:
                continue
            rb      = w1 * a1 + w2 * a2 + w3 * a3
            cagr    = float(np.prod(1 + rb) ** (1 / n_years) - 1)
            vol     = float(np.std(rb, ddof=1)) * np.sqrt(12)
            sharpe  = cagr / vol if vol > 0 else 0.0
            eq      = np.cumprod(1 + rb)
            roll_mx = np.maximum.accumulate(eq)
            max_dd  = float(np.min(eq / roll_mx - 1))
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
                           label1="h020", label2="h026", label3="h037b") -> dict:
    """Compute blend stats at fixed weights (for the H031 56/19/25 comparison)."""
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
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H031b — Three-Way Blend: H020 + H026 + H037b (gap-filtered IBS)")
    print("=" * 72)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H20_ASSETS + [CASH_ETF] + SECTOR_ETFS))
    prices   = fetch_close(all_tickers, FULL_START, FULL_END, tag="h031_all")
    spy_ohlc = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build individual equity curves ────────────────────────────────────
    print("\n[2] Building H020 equity curve …")
    eq_h020 = h020_equity_curve(prices)

    print("[3] Building H026 equity curve …")
    eq_h026 = h026_equity_curve(prices)

    print("[4] Building H037b equity curve (gap-filtered IBS) …")
    eq_h037b = h037b_equity_curve(spy_ohlc)

    for name, eq in [("H020", eq_h020), ("H026", eq_h026), ("H037b", eq_h037b)]:
        if eq.empty:
            print(f"ERROR: {name} equity curve is empty. Aborting.")
            return {}

    # ── 3. Convert to monthly returns ─────────────────────────────────────────
    print("\n[5] Converting to monthly returns …")
    r_h020_all  = to_monthly_returns(eq_h020)
    r_h026_all  = to_monthly_returns(eq_h026)
    r_h037b_all = to_monthly_returns(eq_h037b)

    common_idx = (
        r_h020_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h037b_all.index)
    )
    r_h020  = r_h020_all.loc[common_idx]
    r_h026  = r_h026_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    corr_20_26   = float(r_h020.corr(r_h026))
    corr_20_37b  = float(r_h020.corr(r_h037b))
    corr_26_37b  = float(r_h026.corr(r_h037b))

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")
    print(f"   Monthly correlations:  H020/H026={corr_20_26:.4f}  H020/H037b={corr_20_37b:.4f}  H026/H037b={corr_26_37b:.4f}")

    # ── 4. Standalone stats ───────────────────────────────────────────────────
    print("\n[6] Computing standalone stats …")
    s_h020  = stats_from_monthly_returns(r_h020)
    s_h026  = stats_from_monthly_returns(r_h026)
    s_h037b = stats_from_monthly_returns(r_h037b)

    print(f"   H020 : CAGR {s_h020['cagr']:.2%}  Sharpe {s_h020['sharpe']:.3f}  MaxDD {s_h020['max_drawdown']:.2%}")
    print(f"   H026 : CAGR {s_h026['cagr']:.2%}  Sharpe {s_h026['sharpe']:.3f}  MaxDD {s_h026['max_drawdown']:.2%}")
    print(f"   H037b: CAGR {s_h037b['cagr']:.2%}  Sharpe {s_h037b['sharpe']:.3f}  MaxDD {s_h037b['max_drawdown']:.2%}")

    # ── 5. Coarse grid ────────────────────────────────────────────────────────
    print("\n[7] Running three-way grid search …")
    h020_range = [0.40, 0.50, 0.60, 0.70]
    h026_range = [0.10, 0.20, 0.30, 0.40]

    grid_results = threeway_grid(r_h020, r_h026, r_h037b,
                                  h020_range, h026_range,
                                  "H020", "H026", "H037b")

    print(f"\n{'=' * 90}")
    print("  THREE-WAY BLEND GRID: H020 / H026 / H037b")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 90}")
    print(f"  {'H020':>6}  {'H026':>6}  {'H037b':>6}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*84}")
    for row in grid_results:
        print(
            f"  {row['w_h020']:>6.0%}  {row['w_h026']:>6.0%}  {row['w_h037b']:>6.0%}  "
            f"{row['cagr']:>8.2%}  {row['sharpe']:>8.3f}  {row['max_drawdown']:>8.2%}  "
            f"{row['ann_vol']:>8.2%}  {row['calmar']:>8.3f}"
        )

    best_sharpe_grid = grid_results[0]
    best_mindd_grid  = sorted(grid_results, key=lambda x: x["max_drawdown"], reverse=True)[0]
    print(f"\n  Grid best Sharpe : H020={best_sharpe_grid['w_h020']:.0%}  H026={best_sharpe_grid['w_h026']:.0%}  H037b={best_sharpe_grid['w_h037b']:.0%}  →  Sharpe {best_sharpe_grid['sharpe']:.4f}")
    print(f"  Grid min MaxDD   : H020={best_mindd_grid['w_h020']:.0%}  H026={best_mindd_grid['w_h026']:.0%}  H037b={best_mindd_grid['w_h037b']:.0%}  →  MaxDD {best_mindd_grid['max_drawdown']:.2%}")

    # ── 6. Continuous optimisation ────────────────────────────────────────────
    print("\n[8] Running continuous 2D optimisation (101×101 grid) …")
    optimal = find_optimal_threeway(r_h020, r_h026, r_h037b, n_steps=101)

    opt_sharpe = optimal["max_sharpe"]
    opt_mindd  = optimal["min_maxdd"]

    print(f"\n  Continuous max-Sharpe : H020={opt_sharpe['w_h020']:.1%}  H026={opt_sharpe['w_h026']:.1%}  H037b={opt_sharpe['w_h037b']:.1%}")
    print(f"    CAGR {opt_sharpe['cagr']:.2%}  Sharpe {opt_sharpe['sharpe']:.4f}  MaxDD {opt_sharpe['max_drawdown']:.2%}  AnnVol {opt_sharpe['ann_vol']:.2%}")
    print(f"\n  Continuous min-MaxDD  : H020={opt_mindd['w_h020']:.1%}  H026={opt_mindd['w_h026']:.1%}  H037b={opt_mindd['w_h037b']:.1%}")
    print(f"    CAGR {opt_mindd['cagr']:.2%}  Sharpe {opt_mindd['sharpe']:.4f}  MaxDD {opt_mindd['max_drawdown']:.2%}  AnnVol {opt_mindd['ann_vol']:.2%}")

    # ── 7. Fixed-weight comparison: H031 weights (56/19/25) ──────────────────
    print("\n[9] Computing H031 fixed weights (56/19/25) on H037b …")
    h031_weights = (0.56, 0.19, 0.25)
    s_fixed = blend_stats_at_weights(r_h020, r_h026, r_h037b, *h031_weights)
    print(f"   H031b @H031-weights(56/19/25): CAGR {s_fixed['cagr']:.2%}  Sharpe {s_fixed['sharpe']:.4f}  MaxDD {s_fixed['max_drawdown']:.2%}")

    # ── 8. H031 reference values (from saved results) ────────────────────────
    H031_REF = {
        "weights":      {"w_h020": 0.56, "w_h026": 0.19, "w_h009": 0.25},
        "cagr":         0.1463,
        "sharpe":       1.843,
        "max_drawdown": -0.1152,
        "ann_vol":      0.0794,
        "calmar":       1.269,
        "n_months":     273,
        "source":       "H031 continuous max-Sharpe result",
    }
    # Also include the coarse-grid H031 best for fair coarse comparison
    H031_COARSE_BEST = {
        "weights": {"w_h020": 0.60, "w_h026": 0.20, "w_h009": 0.20},
        "sharpe":  1.8374,
        "cagr":    0.1473,
        "max_drawdown": -0.1242,
    }

    # ── 9. Summary comparison ─────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  H031b vs H031 COMPARISON SUMMARY")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"{'=' * 90}")
    print(f"  {'Scenario':<42}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*88}")

    comparison = [
        ("H020 standalone",                                s_h020),
        ("H026 standalone",                                s_h026),
        ("H037b standalone (gap-filtered IBS)",            s_h037b),
        ("H031b @H031-weights 56/19/25",                   s_fixed),
        ("H031b max-Sharpe (re-optimised)",                opt_sharpe),
        ("H031b min-MaxDD  (re-optimised)",                opt_mindd),
    ]

    # Pad H031_REF to match format
    h031_display = {
        "cagr": H031_REF["cagr"], "sharpe": H031_REF["sharpe"],
        "max_drawdown": H031_REF["max_drawdown"], "ann_vol": H031_REF["ann_vol"],
        "calmar": H031_REF["calmar"],
    }

    print(f"  {'[H031 ref] max-Sharpe 56/19/25 H009':<42}  "
          f"{H031_REF['cagr']:>8.2%}  {H031_REF['sharpe']:>8.3f}  "
          f"{H031_REF['max_drawdown']:>8.2%}  {H031_REF['ann_vol']:>8.2%}  "
          f"{H031_REF['calmar']:>8.3f}")

    for name, s in comparison:
        if "error" in s:
            continue
        print(
            f"  {name:<42}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
            f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}"
        )

    # Deltas for key scenarios
    sharpe_delta_fixed = s_fixed["sharpe"] - H031_REF["sharpe"]
    sharpe_delta_opt   = opt_sharpe["sharpe"] - H031_REF["sharpe"]
    maxdd_delta_fixed  = s_fixed["max_drawdown"] - H031_REF["max_drawdown"]
    maxdd_delta_opt    = opt_sharpe["max_drawdown"] - H031_REF["max_drawdown"]

    print(f"\n  Sharpe delta vs H031 (@same weights 56/19/25): {sharpe_delta_fixed:+.4f}")
    print(f"  Sharpe delta vs H031 (re-optimised H031b)    : {sharpe_delta_opt:+.4f}")
    print(f"  MaxDD  delta vs H031 (@same weights 56/19/25): {maxdd_delta_fixed:+.4f}")
    print(f"  MaxDD  delta vs H031 (re-optimised H031b)    : {maxdd_delta_opt:+.4f}")

    # ── 10. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H031b — H020 + H026 + H037b Three-Way Blend",
        "description": (
            "H031 with H009 replaced by H037b (gap-down filter -0.5%). "
            "Tests whether improved signal quality translates to a better portfolio."
        ),
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
        },
        "gap_filter_threshold": GAP_FILTER_B,
        "monthly_correlations": {
            "h020_h026":  round(corr_20_26,  4),
            "h020_h037b": round(corr_20_37b, 4),
            "h026_h037b": round(corr_26_37b, 4),
        },
        "standalone": {
            "h020":  s_h020,
            "h026":  s_h026,
            "h037b": s_h037b,
        },
        "blend_grid": grid_results,
        "optimal": optimal,
        "fixed_weight_comparison": {
            "weights": {"w_h020": 0.56, "w_h026": 0.19, "w_h037b": 0.25},
            "description": "H031 optimal weights (56/19/25) applied to H037b instead of H009",
            "stats": s_fixed,
        },
        "h031_reference": H031_REF,
        "vs_h031": {
            "sharpe_delta_same_weights":   round(sharpe_delta_fixed, 4),
            "sharpe_delta_reoptimised":    round(sharpe_delta_opt,   4),
            "maxdd_delta_same_weights":    round(maxdd_delta_fixed,  4),
            "maxdd_delta_reoptimised":     round(maxdd_delta_opt,    4),
            "verdict": (
                "H037b signal improvement carries through to portfolio" if sharpe_delta_opt > 0.02
                else "H037b improvement is partially diluted in the blend" if sharpe_delta_opt > 0.0
                else "H037b substitution provides no net benefit in the blend"
            ),
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h031b_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
