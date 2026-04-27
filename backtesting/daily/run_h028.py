"""
H028 — Optimal Blend of H020 (5-asset macro rotation) + H026 (sector ETF momentum)

Both strategies are rebuilt from scratch using the same common time window
(limited by H026's sector ETF data start ~2001) so blending is apples-to-apples.

Blend weights tested: 100/0, 80/20, 60/40, 50/50, 40/60, 20/80, 0/100 (H020 / H026)

Outputs:
  /workspace/agent/backtesting/results/h028_results.json
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FULL_START = "2000-01-01"
FULL_END   = "2026-04-25"

# H020 universe
H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF   = "SHY"
TOP_N_H20  = 2

# H026 universe
SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

BLEND_WEIGHTS = [
    (1.00, 0.00),
    (0.80, 0.20),
    (0.60, 0.40),
    (0.50, 0.50),
    (0.40, 0.60),
    (0.20, 0.80),
    (0.00, 1.00),
]


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h028_{h}.parquet"


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


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    eq = eq.dropna()
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr     = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol      = rets.std() * np.sqrt(252)
    sharpe   = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0
    win_rate = (rets > 0).mean()
    return {
        "cagr":         round(float(cagr),    4),
        "sharpe":       round(float(sharpe),   4),
        "max_drawdown": round(float(max_dd),   4),
        "calmar":       round(float(calmar),   4),
        "ann_vol":      round(float(vol),      4),
        "win_rate":     round(float(win_rate), 4),
        "n_years":      round(float(n_years),  1),
    }


# ─────────────────────────────────────────────
# H020 equity curve
# ─────────────────────────────────────────────

def h020_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    """
    SPY/QQQ/TLT/GLD/IEF — top-2 by rank(12m_mom) + rank(inv_6m_vol).
    Remaining 3 positions go to SHY (cash proxy).
    Returns daily equity series.
    """
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


# ─────────────────────────────────────────────
# H026 equity curve
# ─────────────────────────────────────────────

def h026_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    """
    11 sector ETFs — top-3 by rank(12m_mom) + rank(inv_6m_vol), equal-weight.
    No cash position.
    Returns daily equity series.
    """
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


# ─────────────────────────────────────────────
# Monthly return series from daily equity
# ─────────────────────────────────────────────

def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────
# Blend two monthly return series
# ─────────────────────────────────────────────

def blend_monthly_returns(
    r1: pd.Series,
    r2: pd.Series,
    w1: float,
    w2: float,
) -> pd.Series:
    common = r1.index.intersection(r2.index)
    return w1 * r1.loc[common] + w2 * r2.loc[common]


def stats_from_monthly_returns(monthly_rets: pd.Series) -> dict:
    """Compute CAGR, Sharpe, MaxDD, AnnVol from monthly return series."""
    if len(monthly_rets) < 12:
        return {"error": "insufficient data"}
    equity = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = (equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = monthly_rets.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = equity.expanding().max()
    max_dd   = (equity / roll_max - 1).min()
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
    }


# ─────────────────────────────────────────────
# H018 standalone monthly returns (H016+H009 blend)
# Inline recreation using H016 (3-asset: SPY/TLT/GLD)
# ─────────────────────────────────────────────

def h016_equity_curve(prices: pd.DataFrame, assets: list, start: str, end: str) -> pd.Series:
    """H016: 3-asset (SPY/TLT/GLD) macro rotation with SHY cash."""
    top_n = 2
    available = [a for a in assets if a in prices.columns]
    if len(available) < top_n + 1 or CASH_ETF not in prices.columns:
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
        if len(valid) < top_n + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top      = list(combined.nlargest(top_n).index)
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
                    port_ret += (p1 / p0 - 1) / top_n
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


def h009_equity_curve(ohlc: pd.DataFrame, start: str, end: str) -> pd.Series:
    """H009: SPY IBS mean-reversion daily."""
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
        ret    = c_curr / c_prev - 1 if c_prev > 0 else 0

        if position == 1:
            equity   *= (1 + ret)
            days_held += 1
            if float(ibs.iloc[i]) > 0.8 or days_held >= 5:
                position = days_held = 0
        else:
            if float(ibs.iloc[i - 1]) < 0.2:
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


def build_h018_monthly_returns(start: str, end: str) -> pd.Series:
    """Rebuild H018 (H016+H009 50/50 blend) monthly return series."""
    H16_ASSETS = ["SPY", "TLT", "GLD"]
    # Fetch close prices
    close_data = fetch_close(H16_ASSETS + [CASH_ETF], start, end, tag="h018_close")
    # Fetch SPY OHLC
    raw_ohlc = yf.download(["SPY"], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw_ohlc.columns, pd.MultiIndex):
        spy_ohlc = raw_ohlc.xs("SPY", axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        spy_ohlc = raw_ohlc[["Open", "High", "Low", "Close"]].rename(columns=str.lower)

    eq16 = h016_equity_curve(close_data, H16_ASSETS, start, end)
    eq09 = h009_equity_curve(spy_ohlc, start, end)

    if eq16.empty or eq09.empty:
        return pd.Series(dtype=float)

    common_start = max(eq16.index[0], eq09.index[0])
    common_end   = min(eq16.index[-1], eq09.index[-1])

    all_dates  = eq09.loc[common_start:common_end].index
    eq16_daily = eq16.reindex(all_dates).ffill()
    eq09_daily = eq09.reindex(all_dates).ffill()

    r16 = eq16_daily.pct_change().fillna(0)
    r09 = eq09_daily.pct_change().fillna(0)
    r_blend = 0.5 * r16 + 0.5 * r09

    eq_blend = INITIAL_EQUITY * (1 + r_blend).cumprod()
    return to_monthly_returns(eq_blend)


# ─────────────────────────────────────────────
# Efficient frontier search (min-var and max-Sharpe)
# ─────────────────────────────────────────────

def find_optimal_blends(
    r_h020: pd.Series,
    r_h026: pd.Series,
    n_points: int = 1001,
) -> dict:
    """
    Sweep w_h020 from 0 to 1 in fine steps to find min-var and max-Sharpe blends.
    Returns dict with both optimal weights plus stats at each.
    """
    common = r_h020.index.intersection(r_h026.index)
    r1 = r_h020.loc[common].values
    r2 = r_h026.loc[common].values

    weights = np.linspace(0, 1, n_points)
    best_sharpe_w = 0.5
    best_sharpe   = -np.inf
    min_var_w     = 0.5
    min_var       = np.inf

    for w in weights:
        r_blend = w * r1 + (1 - w) * r2
        n_years = len(r_blend) / 12.0
        cagr    = (np.prod(1 + r_blend)) ** (1 / n_years) - 1
        vol     = float(np.std(r_blend, ddof=1)) * np.sqrt(12)
        sharpe  = cagr / vol if vol > 0 else 0

        if vol < min_var:
            min_var   = vol
            min_var_w = w

        if sharpe > best_sharpe:
            best_sharpe   = sharpe
            best_sharpe_w = w

    return {
        "max_sharpe_h020_weight": round(float(best_sharpe_w), 4),
        "max_sharpe_h026_weight": round(float(1 - best_sharpe_w), 4),
        "max_sharpe_value":       round(float(best_sharpe), 4),
        "min_var_h020_weight":    round(float(min_var_w), 4),
        "min_var_h026_weight":    round(float(1 - min_var_w), 4),
        "min_var_ann_vol":        round(float(min_var), 4),
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H028 — H020 + H026 Optimal Blend")
    print("=" * 72)

    # ── 1. Fetch data ────────────────────────────────────────────────────

    print("\n[1] Fetching data …")
    all_tickers = list(set(H20_ASSETS + [CASH_ETF] + SECTOR_ETFS + ["SPY"]))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h028_all")

    # ── 2. Build individual equity curves ───────────────────────────────

    print("\n[2] Building H020 equity curve …")
    eq_h020 = h020_equity_curve(prices, FULL_START, FULL_END)

    print("[3] Building H026 equity curve …")
    eq_h026 = h026_equity_curve(prices, FULL_START, FULL_END)

    if eq_h020.empty or eq_h026.empty:
        print("ERROR: one or both equity curves are empty. Aborting.")
        return {}

    # ── 3. Get common monthly return series ─────────────────────────────

    print("\n[4] Computing monthly return series …")
    r_h020_daily = to_monthly_returns(eq_h020)
    r_h026_daily = to_monthly_returns(eq_h026)

    common_idx = r_h020_daily.index.intersection(r_h026_daily.index)
    r_h020 = r_h020_daily.loc[common_idx]
    r_h026 = r_h026_daily.loc[common_idx]

    common_start = common_idx[0]
    common_end   = common_idx[-1]
    n_months     = len(common_idx)
    n_years      = n_months / 12.0

    corr = float(r_h020.corr(r_h026))

    print(f"   Common window: {common_start.date()} → {common_end.date()} ({n_months} months, {n_years:.1f} yrs)")
    print(f"   Monthly return correlation (H020 vs H026): {corr:.4f}")

    # ── 4. Blend sweep ───────────────────────────────────────────────────

    print("\n[5] Computing blend statistics …")

    blend_results = []
    for w20, w26 in BLEND_WEIGHTS:
        r_blend = w20 * r_h020 + w26 * r_h026
        stats   = stats_from_monthly_returns(r_blend)
        stats["w_h020"] = w20
        stats["w_h026"] = w26
        blend_results.append(stats)

    # ── 5. Find optimal blends ───────────────────────────────────────────

    print("[6] Finding min-var and max-Sharpe optimal blends …")
    optimal = find_optimal_blends(r_h020, r_h026)

    # ── 6. Also compute H018 (H016+H009) monthly returns ────────────────

    print("\n[7] Building H018 monthly returns for comparison …")
    try:
        r_h018 = build_h018_monthly_returns("2007-01-01", FULL_END)
        # Align to the H028 common window where possible
        h018_common = r_h018.index.intersection(common_idx)
        if len(h018_common) > 12:
            r_h018_aligned = r_h018.loc[h018_common]
            h018_stats_common = stats_from_monthly_returns(r_h018_aligned)
        else:
            h018_stats_common = {"error": "insufficient overlap"}
        h018_stats_full = stats_from_monthly_returns(r_h018)
        print(f"   H018 full period: CAGR {h018_stats_full.get('cagr', 'n/a'):.2%}  "
              f"Sharpe {h018_stats_full.get('sharpe', 'n/a'):.3f}  "
              f"MaxDD {h018_stats_full.get('max_drawdown', 'n/a'):.2%}")
    except Exception as e:
        print(f"   WARNING: could not build H018: {e}")
        r_h018 = pd.Series(dtype=float)
        h018_stats_full = {"error": str(e)}
        h018_stats_common = {"error": str(e)}

    # ── 7. Print results table ───────────────────────────────────────────

    print(f"\n{'=' * 72}")
    print("  EFFICIENT FRONTIER: H020 / H026 BLEND")
    print(f"  Period: {common_start.date()} → {common_end.date()}  ({n_months} months)")
    print(f"  Correlation: {corr:.4f}")
    print(f"{'=' * 72}")
    print(f"  {'H020 wt':>8}  {'H026 wt':>8}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}")
    print(f"  {'-'*66}")
    for b in blend_results:
        if "error" in b:
            continue
        marker = ""
        if abs(b["w_h020"] - optimal["max_sharpe_h020_weight"]) < 0.11:
            marker = " <-- ~max-Sharpe"
        elif abs(b["w_h020"] - optimal["min_var_h020_weight"]) < 0.11:
            marker = " <-- ~min-var"
        print(
            f"  {b['w_h020']:>8.0%}  {b['w_h026']:>8.0%}  "
            f"{b['cagr']:>8.2%}  {b['sharpe']:>8.3f}  "
            f"{b['max_drawdown']:>8.2%}  {b['ann_vol']:>8.2%}"
            f"{marker}"
        )

    print(f"\n  Continuous-search optimals:")
    print(f"    Max-Sharpe blend:  H020={optimal['max_sharpe_h020_weight']:.1%}  H026={optimal['max_sharpe_h026_weight']:.1%}"
          f"  →  Sharpe {optimal['max_sharpe_value']:.4f}")
    print(f"    Min-Variance blend: H020={optimal['min_var_h020_weight']:.1%}  H026={optimal['min_var_h026_weight']:.1%}"
          f"  →  AnnVol {optimal['min_var_ann_vol']:.4f}")

    # ── 8. H028 best blend stats ─────────────────────────────────────────

    w_opt = optimal["max_sharpe_h020_weight"]
    r_h028 = w_opt * r_h020 + (1 - w_opt) * r_h026
    h028_stats = stats_from_monthly_returns(r_h028)

    print(f"\n  H028 (max-Sharpe blend: {w_opt:.0%}/{1-w_opt:.0%}):")
    print(f"    CAGR {h028_stats['cagr']:.2%}  Sharpe {h028_stats['sharpe']:.3f}  "
          f"MaxDD {h028_stats['max_drawdown']:.2%}  AnnVol {h028_stats['ann_vol']:.2%}")

    # ── 9. Compare H028 vs H018 ──────────────────────────────────────────

    print(f"\n{'=' * 72}")
    print("  H028 (H020+H026) vs H018 (H016+H009) COMPARISON")
    print(f"{'=' * 72}")

    h020_alone = stats_from_monthly_returns(r_h020)
    h026_alone = stats_from_monthly_returns(r_h026)

    rows = [
        ("H020 alone (5-asset macro)", h020_alone),
        ("H026 alone (sector ETF)",    h026_alone),
        ("H028 best blend",            h028_stats),
    ]
    if "error" not in h018_stats_full:
        rows.append(("H018 (H016+H009, full)",  h018_stats_full))
    if "error" not in h018_stats_common:
        rows.append(("H018 (H016+H009, common)", h018_stats_common))

    print(f"  {'Strategy':<30}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'N months':>9}")
    print(f"  {'-'*78}")
    for name, s in rows:
        if "error" in s:
            continue
        nm = s.get("n_months", "?")
        print(
            f"  {name:<30}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
            f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {nm:>9}"
        )

    # Could we add H018 as a 3rd component to H028? Quick check:
    print(f"\n  [Optional] 3-way blend: H028 + H018 …")
    if not r_h018.empty:
        h018_common_idx = r_h018.index.intersection(common_idx)
        if len(h018_common_idx) > 24:
            r1 = r_h020.loc[h018_common_idx]
            r2 = r_h026.loc[h018_common_idx]
            r3 = r_h018.loc[h018_common_idx]

            # Simple grid: equal thirds vs two-way
            r_equal3 = (r1 + r2 + r3) / 3.0
            r_h028_trimmed = w_opt * r1 + (1 - w_opt) * r2

            s_equal3    = stats_from_monthly_returns(r_equal3)
            s_h028_trim = stats_from_monthly_returns(r_h028_trimmed)
            s_h018_trim = stats_from_monthly_returns(r3)

            print(f"  (Aligned to common 3-way overlap: {h018_common_idx[0].date()} → {h018_common_idx[-1].date()}, {len(h018_common_idx)} months)")
            for name, s in [
                ("H028 (H020+H026)", s_h028_trim),
                ("H018 alone",       s_h018_trim),
                ("Equal 3-way",      s_equal3),
            ]:
                if "error" in s:
                    continue
                print(f"    {name:<28}  CAGR {s['cagr']:>6.2%}  Sharpe {s['sharpe']:.3f}  MaxDD {s['max_drawdown']:.2%}")
        else:
            print(f"    Not enough overlap for 3-way comparison ({len(h018_common_idx)} months)")

    # ── 10. Save results ─────────────────────────────────────────────────

    output = {
        "strategy": "H028 — H020 + H026 Optimal Blend",
        "common_window": {
            "start":    str(common_start.date()),
            "end":      str(common_end.date()),
            "n_months": n_months,
            "n_years":  round(n_years, 1),
        },
        "monthly_return_correlation": round(corr, 4),
        "blend_grid": [
            {k: v for k, v in b.items()} for b in blend_results
        ],
        "optimal": optimal,
        "h028_stats": h028_stats,
        "h020_standalone": h020_alone,
        "h026_standalone": h026_alone,
        "h018_full":       h018_stats_full,
        "h018_common":     h018_stats_common,
        "run_date": FULL_END,
    }

    out_path = Path("/workspace/agent/backtesting/results/h028_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
