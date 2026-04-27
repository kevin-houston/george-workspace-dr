"""
H038 — Factor ETF Momentum Rotation
=====================================

Universe (6 iShares/MSCI US equity factor ETFs):
  MTUM  momentum factor
  QUAL  quality factor
  VLUE  value factor
  SIZE  small-cap factor
  USMV  low-volatility factor
  DGRO  dividend growth

Signal: identical to H020 — rank by (12m momentum + inverse 6m vol),
hold top-2 at 50/50, monthly rebalance. Cash (SHY) for remainder.

Period: 2013-01-01 → 2026-04-27 (ETFs launched ~2013)
IS: 2013-01-01 → 2018-12-31
OOS: 2019-01-01 → 2026-04-27

Outputs:
  /workspace/agent/backtesting/results/h038_results.json
"""

import json
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FULL_START = "2013-01-01"
FULL_END   = "2026-04-27"
IS_START   = "2013-01-01"
IS_END     = "2018-12-31"
OOS_START  = "2019-01-01"
OOS_END    = "2026-04-27"

FACTOR_ETFS = ["MTUM", "QUAL", "VLUE", "SIZE", "USMV", "DGRO"]
CASH_ETF    = "SHY"
TOP_N       = 2

# H031 component universes (for blend correlation analysis)
H20_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
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
    return CACHE_DIR / f"h038_{h}.parquet"


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
    cp = CACHE_DIR / f"h038_spy_ohlc_{start}_{end}.parquet"
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

def calc_stats(monthly_rets: pd.Series) -> dict:
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data"}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr    = float(equity.iloc[-1] ** (1 / n_years) - 1)
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "cagr":         round(cagr,   4),
        "sharpe":       round(sharpe,  4),
        "max_drawdown": round(max_dd,  4),
        "calmar":       round(calmar,  4),
        "ann_vol":      round(vol,     4),
        "n_months":     len(monthly_rets),
        "n_years":      round(n_years, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H038 core engine — factor ETF rotation
# Returns (daily equity series, monthly holdings list)
# ─────────────────────────────────────────────────────────────────────────────

def h038_equity_curve(prices: pd.DataFrame, start: str, end: str):
    available = [t for t in FACTOR_ETFS if t in prices.columns]
    if len(available) < TOP_N + 1 or CASH_ETF not in prices.columns:
        print(f"  WARNING: insufficient tickers. Available: {available}")
        return pd.Series(dtype=float), []

    px = prices[available + [CASH_ETF]].loc[start:end].dropna(how="all")

    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    equity   = INITIAL_EQUITY
    series   = []
    holdings = []  # track monthly selections

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top      = list(combined.nlargest(TOP_N).index)
        rest     = [s for s in valid if s not in top]
        cash_wt  = len(rest) / len(valid)

        holdings.append({
            "month":    str(month_end.date()),
            "held":     top,
            "cash_pct": round(cash_wt, 4),
        })

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
                    port_ret += (p1 / p0 - 1) / TOP_N
            if cash_wt > 0:
                p0 = float(sub[CASH_ETF].iloc[j - 1])
                p1 = float(sub[CASH_ETF].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float), holdings

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq, holdings


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# H020 equity curve — rebuild for correlation analysis on 2013+ window
# ─────────────────────────────────────────────────────────────────────────────

def h020_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [a for a in H20_ASSETS if a in prices.columns]
    top_n = 2
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


# ─────────────────────────────────────────────────────────────────────────────
# H026 equity curve — rebuild for correlation analysis on 2013+ window
# ─────────────────────────────────────────────────────────────────────────────

def h026_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    top_n = 3
    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / top_n
    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n:
            continue

        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(top_n).index)

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
# H009 equity curve (SPY IBS mean-reversion)
# ─────────────────────────────────────────────────────────────────────────────

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
    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────────────────────────────────────
# H031 (56% H020 / 19% H026 / 25% H009) — rebuild on 2013+ window
# ─────────────────────────────────────────────────────────────────────────────

def build_h031_monthly_returns(prices: pd.DataFrame, spy_ohlc: pd.DataFrame,
                                start: str, end: str) -> pd.Series:
    eq20 = h020_equity_curve(prices, start, end)
    eq26 = h026_equity_curve(prices, start, end)
    eq09 = h009_equity_curve(spy_ohlc, start, end)

    if eq20.empty or eq26.empty or eq09.empty:
        return pd.Series(dtype=float)

    r20 = to_monthly_returns(eq20)
    r26 = to_monthly_returns(eq26)
    r09 = to_monthly_returns(eq09)

    common = r20.index.intersection(r26.index).intersection(r09.index)
    return 0.56 * r20.loc[common] + 0.19 * r26.loc[common] + 0.25 * r09.loc[common]


# ─────────────────────────────────────────────────────────────────────────────
# SPY buy-and-hold on the same window (monthly returns)
# ─────────────────────────────────────────────────────────────────────────────

def spy_bah_monthly_returns(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    if "SPY" not in prices.columns:
        return pd.Series(dtype=float)
    spy_daily = prices["SPY"].loc[start:end].dropna()
    spy_monthly = spy_daily.resample("ME").last()
    return spy_monthly.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Blend H038 into H031 at various H038 weights
# ─────────────────────────────────────────────────────────────────────────────

def blend_into_h031(r_h031: pd.Series, r_h038: pd.Series) -> list:
    """
    Test adding H038 at 10% (and nearby), scaling H031 down proportionally.
    Returns list of dicts sorted by Sharpe.
    """
    common = r_h031.index.intersection(r_h038.index)
    r1 = r_h031.loc[common]
    r2 = r_h038.loc[common]

    results = []
    for w38 in [0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
        w31 = 1.0 - w38
        r_blend = w31 * r1 + w38 * r2
        stats = calc_stats(r_blend)
        stats["w_h031"] = round(w31, 2)
        stats["w_h038"] = round(w38, 2)
        results.append(stats)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H038 — Factor ETF Momentum Rotation")
    print("=" * 72)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching data …")
    all_tickers = list(set(
        FACTOR_ETFS + [CASH_ETF] + H20_ASSETS + SECTOR_ETFS + ["SPY"]
    ))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h038_all")
    spy_ohlc = fetch_ohlc_spy(FULL_START, FULL_END)

    # Check which factor ETFs are present
    available_factors = [t for t in FACTOR_ETFS if t in prices.columns]
    print(f"  Factor ETFs available: {available_factors}")

    # ── 2. Full period H038 equity curve ─────────────────────────────────────
    print("\n[2] Building H038 full-period equity curve …")
    eq_h038_full, holdings_full = h038_equity_curve(prices, FULL_START, FULL_END)

    if eq_h038_full.empty:
        print("ERROR: H038 equity curve is empty.")
        return {}

    r_h038_full = to_monthly_returns(eq_h038_full)

    # ── 3. IS/OOS split ──────────────────────────────────────────────────────
    print("\n[3] Building IS/OOS equity curves …")
    eq_is, holdings_is  = h038_equity_curve(prices, IS_START,  IS_END)
    eq_oos, holdings_oos = h038_equity_curve(prices, OOS_START, OOS_END)

    r_is  = to_monthly_returns(eq_is)  if not eq_is.empty  else pd.Series(dtype=float)
    r_oos = to_monthly_returns(eq_oos) if not eq_oos.empty else pd.Series(dtype=float)

    stats_full = calc_stats(r_h038_full)
    stats_is   = calc_stats(r_is)  if not r_is.empty  else {"error": "no data"}
    stats_oos  = calc_stats(r_oos) if not r_oos.empty else {"error": "no data"}

    # ── 4. Factor dominance ──────────────────────────────────────────────────
    print("\n[4] Counting factor holding frequency …")
    all_held = []
    for row in holdings_full:
        all_held.extend(row["held"])
    holding_counts = Counter(all_held)
    n_months_traded = len(holdings_full)
    holding_pct = {k: round(v / n_months_traded, 4) for k, v in holding_counts.most_common()}

    print(f"  Months evaluated: {n_months_traded}")
    for sym, cnt in holding_counts.most_common():
        pct = cnt / n_months_traded
        print(f"    {sym}: {cnt}/{n_months_traded} months ({pct:.1%})")

    # ── 5. H020 correlation on same window ──────────────────────────────────
    print("\n[5] Building H020 + H026 for correlation analysis …")
    eq_h020 = h020_equity_curve(prices, FULL_START, FULL_END)
    eq_h026 = h026_equity_curve(prices, FULL_START, FULL_END)

    r_h020_full = to_monthly_returns(eq_h020) if not eq_h020.empty else pd.Series(dtype=float)
    r_h026_full = to_monthly_returns(eq_h026) if not eq_h026.empty else pd.Series(dtype=float)

    # Correlations on common H038 window
    common_38_20 = r_h038_full.index.intersection(r_h020_full.index)
    common_38_26 = r_h038_full.index.intersection(r_h026_full.index)
    common_all   = r_h038_full.index.intersection(r_h020_full.index).intersection(r_h026_full.index)

    corr_h038_h020 = float(r_h038_full.loc[common_38_20].corr(r_h020_full.loc[common_38_20])) if len(common_38_20) > 12 else None
    corr_h038_h026 = float(r_h038_full.loc[common_38_26].corr(r_h026_full.loc[common_38_26])) if len(common_38_26) > 12 else None

    print(f"  H038 ↔ H020 monthly return correlation: {corr_h038_h020:.4f}" if corr_h038_h020 is not None else "  n/a")
    print(f"  H038 ↔ H026 monthly return correlation: {corr_h038_h026:.4f}" if corr_h038_h026 is not None else "  n/a")

    # ── 6. SPY B&H comparison on same window ────────────────────────────────
    print("\n[6] Computing SPY B&H on H038 window …")
    r_spy = spy_bah_monthly_returns(prices, FULL_START, FULL_END)
    common_spy = r_h038_full.index.intersection(r_spy.index)
    r_spy_aligned = r_spy.loc[common_spy]
    stats_spy = calc_stats(r_spy_aligned)

    # ── 7. H031 rebuild on 2013+ window + blend analysis ────────────────────
    print("\n[7] Rebuilding H031 on 2013+ window for blend analysis …")
    r_h031_13plus = build_h031_monthly_returns(prices, spy_ohlc, FULL_START, FULL_END)

    if not r_h031_13plus.empty:
        # Align H038 to H031 common dates
        common_blend = r_h031_13plus.index.intersection(r_h038_full.index)
        r_h031_aligned = r_h031_13plus.loc[common_blend]
        r_h038_aligned = r_h038_full.loc[common_blend]

        stats_h031_13 = calc_stats(r_h031_aligned)
        corr_h038_h031 = float(r_h038_aligned.corr(r_h031_aligned))

        print(f"  H031 (2013+ window): CAGR {stats_h031_13.get('cagr', 'n/a'):.2%}  "
              f"Sharpe {stats_h031_13.get('sharpe', 'n/a'):.3f}  "
              f"MaxDD {stats_h031_13.get('max_drawdown', 'n/a'):.2%}")
        print(f"  H038 ↔ H031 monthly return correlation: {corr_h038_h031:.4f}")

        blend_results = blend_into_h031(r_h031_aligned, r_h038_aligned)
    else:
        stats_h031_13   = {"error": "could not rebuild H031 on 2013+ window"}
        corr_h038_h031  = None
        blend_results   = []
        print("  WARNING: Could not rebuild H031 on 2013+ window.")

    # ── 8. H020 standalone on same 2013+ window ─────────────────────────────
    stats_h020_13 = {"error": "no data"}
    stats_h026_13 = {"error": "no data"}
    if not r_h020_full.empty and len(common_all) > 12:
        stats_h020_13 = calc_stats(r_h020_full.loc[common_all])
    if not r_h026_full.empty and len(common_all) > 12:
        stats_h026_13 = calc_stats(r_h026_full.loc[common_all])

    # ── 9. Print summary ─────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print("  H038 RESULTS SUMMARY")
    print(f"  Full period: {FULL_START} → {FULL_END}")
    print(f"{'=' * 72}")

    print(f"\n  FULL PERIOD ({stats_full.get('n_months', '?')} months / {stats_full.get('n_years', '?')} yrs):")
    print(f"    CAGR {stats_full.get('cagr', 0):.2%}  Sharpe {stats_full.get('sharpe', 0):.3f}  "
          f"MaxDD {stats_full.get('max_drawdown', 0):.2%}  AnnVol {stats_full.get('ann_vol', 0):.2%}")

    print(f"\n  IN-SAMPLE ({IS_START} → {IS_END}):")
    if "error" not in stats_is:
        print(f"    CAGR {stats_is.get('cagr', 0):.2%}  Sharpe {stats_is.get('sharpe', 0):.3f}  "
              f"MaxDD {stats_is.get('max_drawdown', 0):.2%}")
    else:
        print(f"    {stats_is}")

    print(f"\n  OUT-OF-SAMPLE ({OOS_START} → {OOS_END}):")
    if "error" not in stats_oos:
        print(f"    CAGR {stats_oos.get('cagr', 0):.2%}  Sharpe {stats_oos.get('sharpe', 0):.3f}  "
              f"MaxDD {stats_oos.get('max_drawdown', 0):.2%}")
    else:
        print(f"    {stats_oos}")

    print(f"\n  FACTOR DOMINANCE (most → least held):")
    for sym, cnt in holding_counts.most_common():
        pct = cnt / n_months_traded
        print(f"    {sym}: {cnt}/{n_months_traded} months ({pct:.1%})")

    print(f"\n  CORRELATIONS TO EXISTING STRATEGIES (monthly returns):")
    if corr_h038_h020 is not None:
        print(f"    H038 ↔ H020:  {corr_h038_h020:.4f}")
    if corr_h038_h026 is not None:
        print(f"    H038 ↔ H026:  {corr_h038_h026:.4f}")
    if corr_h038_h031 is not None:
        print(f"    H038 ↔ H031:  {corr_h038_h031:.4f}")

    print(f"\n  COMPARISON ON H038 WINDOW (2013–2026):")
    header = f"  {'Strategy':<30}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}"
    print(header)
    print("  " + "-" * 68)
    rows = [
        ("H038 (factor rotation)", stats_full),
        ("H020 (macro rotation)",  stats_h020_13),
        ("H026 (sector ETF)",      stats_h026_13),
        ("H031 (3-way blend)",     stats_h031_13),
        ("SPY B&H",                stats_spy),
    ]
    for name, s in rows:
        if "error" in s:
            continue
        print(f"  {name:<30}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
              f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}")

    print(f"\n  BLEND ANALYSIS: H038 added into H031 at various weights:")
    print(f"  {'H031 wt':>7}  {'H038 wt':>7}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}")
    print("  " + "-" * 60)
    for b in blend_results:
        if "error" in b:
            continue
        print(f"  {b['w_h031']:>7.0%}  {b['w_h038']:>7.0%}  "
              f"{b['cagr']:>8.2%}  {b['sharpe']:>8.3f}  "
              f"{b['max_drawdown']:>8.2%}  {b['ann_vol']:>8.2%}")

    # ── 10. Save results ─────────────────────────────────────────────────────
    output = {
        "strategy": "H038 — Factor ETF Momentum Rotation",
        "universe": FACTOR_ETFS,
        "available_factors": available_factors,
        "signal": "rank(12m_mom) + rank(inv_6m_vol), hold top-2, monthly rebalance",
        "cash_proxy": CASH_ETF,
        "full_period": {
            "start": FULL_START,
            "end":   FULL_END,
            "stats": stats_full,
        },
        "in_sample": {
            "start": IS_START,
            "end":   IS_END,
            "stats": stats_is,
        },
        "out_of_sample": {
            "start": OOS_START,
            "end":   OOS_END,
            "stats": stats_oos,
        },
        "factor_dominance": {
            "n_months_evaluated": n_months_traded,
            "hold_counts": dict(holding_counts.most_common()),
            "hold_pct":    holding_pct,
        },
        "monthly_holdings": holdings_full,
        "correlations": {
            "h038_vs_h020": round(corr_h038_h020, 4) if corr_h038_h020 is not None else None,
            "h038_vs_h026": round(corr_h038_h026, 4) if corr_h038_h026 is not None else None,
            "h038_vs_h031": round(corr_h038_h031, 4) if corr_h038_h031 is not None else None,
        },
        "comparisons_on_h038_window": {
            "h038": stats_full,
            "h020": stats_h020_13,
            "h026": stats_h026_13,
            "h031": stats_h031_13,
            "spy_bah": stats_spy,
        },
        "blend_h038_into_h031": blend_results,
        "run_date": FULL_END,
    }

    out_path = Path("/workspace/agent/backtesting/results/h038_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
