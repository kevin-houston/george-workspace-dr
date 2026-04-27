"""
H026 — Sector ETF Momentum Rotation
Universe: 11 S&P 500 sector ETFs
Signal:   rank(12m_momentum) + rank(inv_6m_vol)  — identical to H020
Hold:     top 3 at 33.33% each, monthly rebalance
Period:   2000-01-01 to 2026-04-25 (note: XLRE started 2015, XLC started 2018)

Outputs:
  /workspace/agent/backtesting/results/h026_results.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FULL_START  = "2000-01-01"
FULL_END    = "2026-04-25"
IS_END      = "2015-12-31"
OOS_START   = "2016-01-01"

SECTOR_ETFS = [
    "XLK",   # Technology
    "XLE",   # Energy
    "XLF",   # Financials
    "XLV",   # Healthcare
    "XLI",   # Industrials
    "XLB",   # Materials
    "XLU",   # Utilities
    "XLRE",  # Real Estate (started ~Oct 2015)
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLC",   # Communication Services (started ~Jun 2018)
]

TOP_N = 3
WEIGHT = 1.0 / TOP_N  # 33.33%


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str) -> Path:
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h026_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, start, end)
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
# H026 core engine
# ─────────────────────────────────────────────

def h026_equity_curve(
    prices: pd.DataFrame,
    start: str,
    end: str,
) -> pd.Series:
    """
    Monthly momentum+carry rotation across sector ETFs.
    Always holds exactly top-3 at 33.33% each (no cash position).
    Requires >= 12 months of data per ticker to include in ranking.

    Returns daily equity series.
    """
    # Only use tickers present in the data
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].loc[start:end].dropna(how="all")

    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)

    # Monthly prices and returns
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    # 6-month realized vol (annualized), 12-month momentum
    vol_6   = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12  = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []
    holdings_log = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()

        # Only rank tickers with both signals available
        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue

        # Score = rank(12m_mom, ascending) + rank(inv_6m_vol, ascending=False)
        # ascending=False for vol: lowest vol gets highest rank => best score contribution
        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N).index)

        # Daily returns for the next month (from day after previous month-end to this month-end)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]

        if len(sub) < 2:
            continue

        holdings_log.append({
            "month": str(month_end.date()),
            "holdings": top_hold,
        })

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += WEIGHT * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float), []

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq, holdings_log


# ─────────────────────────────────────────────
# H020 monthly returns (for correlation)
# ─────────────────────────────────────────────

def load_h020_monthly_returns() -> pd.Series:
    """
    Reconstruct H020 equity curve to get monthly returns.
    H020 = SPY/QQQ/TLT/GLD/IEF top-2 with SHY as cash.
    Inlined here to avoid module import dependency.
    """
    H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
    CASH_ETF   = "SHY"
    TOP_N_H20  = 2
    IE         = INITIAL_EQUITY

    all_close = fetch_close(H20_ASSETS + [CASH_ETF], "2007-01-01", FULL_END)

    available = [a for a in H20_ASSETS if a in all_close.columns]
    px_all    = all_close[available + [CASH_ETF]].dropna(how="all")

    monthly_px   = px_all[available].resample("ME").last()
    monthly_rets = px_all[available].pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    equity = IE
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
        sub       = px_all.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0, p1 = float(sub[sym].iloc[j-1]), float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / TOP_N_H20
            if cash_wt > 0 and CASH_ETF in sub.columns:
                p0 = float(sub[CASH_ETF].iloc[j-1])
                p1 = float(sub[CASH_ETF].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)

    eq_daily = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    # Resample to monthly returns
    monthly_eq   = eq_daily.resample("ME").last().ffill()
    monthly_rets = monthly_eq.pct_change().dropna()
    return monthly_rets


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def run_h026():
    print("\n" + "═" * 72)
    print("H026 — Sector ETF Momentum Rotation (top-3 of 11, monthly rebalance)")
    print("═" * 72)

    # Fetch all sector ETF data + SPY as benchmark
    prices_raw = fetch_close(SECTOR_ETFS + ["SPY"], FULL_START, FULL_END)
    spy_all = prices_raw["SPY"] if "SPY" in prices_raw.columns else None
    prices  = prices_raw[[t for t in SECTOR_ETFS if t in prices_raw.columns]]

    # Note which tickers actually have data and their start dates
    ticker_starts = {}
    for t in SECTOR_ETFS:
        if t in prices.columns:
            first_valid = prices[t].first_valid_index()
            ticker_starts[t] = str(first_valid.date()) if first_valid is not None else "N/A"

    print("\n  Ticker data availability:")
    for t, s in ticker_starts.items():
        print(f"    {t:<6}: starts {s}")

    # Determine effective start date (when at least TOP_N + 1 tickers have 12+ months of data)
    actual_start = prices.dropna(thresh=TOP_N + 1).index[0]
    print(f"\n  Effective strategy start: ~2001 (after 12-month lookback from {actual_start.date()})")

    results = {}

    # Full period
    print(f"\n  ── FULL PERIOD ({FULL_START} → {FULL_END}) ──")
    eq_full, holdings_log = h026_equity_curve(prices, FULL_START, FULL_END)
    if isinstance(eq_full, pd.Series) and not eq_full.empty:
        spy_full = spy_all.loc[eq_full.index[0]:eq_full.index[-1]] if spy_all is not None else None
        eq_spy   = INITIAL_EQUITY * (spy_full / spy_full.iloc[0]) if spy_full is not None else None
        m_full   = calc_stats(eq_full)
        m_spy    = calc_stats(eq_spy.reindex(eq_full.index).ffill()) if eq_spy is not None else {"error": "no spy"}
        results["full_period"] = {"h026": m_full, "spy_bh": m_spy}
        print(f"    H026:   CAGR {m_full['cagr']:>6.2%}  Sharpe {m_full['sharpe']:.3f}  MaxDD {m_full['max_drawdown']:.2%}  AnnVol {m_full['ann_vol']:.2%}")
        if "error" not in m_spy:
            print(f"    SPY BH: CAGR {m_spy['cagr']:>6.2%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.2%}  AnnVol {m_spy['ann_vol']:.2%}")
        print(f"    Period: {eq_full.index[0].date()} → {eq_full.index[-1].date()}  ({m_full['n_years']} yrs)")
    else:
        print("    ERROR: empty equity curve")
        results["full_period"] = {"error": "empty"}

    # In-sample
    print(f"\n  ── IN-SAMPLE ({FULL_START} → {IS_END}) ──")
    eq_is, _ = h026_equity_curve(prices, FULL_START, IS_END)
    if isinstance(eq_is, pd.Series) and not eq_is.empty:
        spy_is = spy_all.loc[eq_is.index[0]:eq_is.index[-1]] if spy_all is not None else None
        eq_spy_is = (INITIAL_EQUITY * (spy_is / spy_is.iloc[0])) if spy_is is not None else None
        m_is  = calc_stats(eq_is)
        m_spy_is = calc_stats(eq_spy_is.reindex(eq_is.index).ffill()) if eq_spy_is is not None else {"error": "no spy"}
        results["in_sample"] = {"h026": m_is, "spy_bh": m_spy_is}
        print(f"    H026:   CAGR {m_is['cagr']:>6.2%}  Sharpe {m_is['sharpe']:.3f}  MaxDD {m_is['max_drawdown']:.2%}")
        if "error" not in m_spy_is:
            print(f"    SPY BH: CAGR {m_spy_is['cagr']:>6.2%}  Sharpe {m_spy_is['sharpe']:.3f}  MaxDD {m_spy_is['max_drawdown']:.2%}")
    else:
        print("    ERROR: empty equity curve")
        results["in_sample"] = {"error": "empty"}

    # Out-of-sample
    print(f"\n  ── OUT-OF-SAMPLE ({OOS_START} → {FULL_END}) ──")
    eq_oos, _ = h026_equity_curve(prices, OOS_START, FULL_END)
    if isinstance(eq_oos, pd.Series) and not eq_oos.empty:
        spy_oos = spy_all.loc[eq_oos.index[0]:eq_oos.index[-1]] if spy_all is not None else None
        eq_spy_oos = (INITIAL_EQUITY * (spy_oos / spy_oos.iloc[0])) if spy_oos is not None else None
        m_oos  = calc_stats(eq_oos)
        m_spy_oos = calc_stats(eq_spy_oos.reindex(eq_oos.index).ffill()) if eq_spy_oos is not None else {"error": "no spy"}
        results["out_of_sample"] = {"h026": m_oos, "spy_bh": m_spy_oos}
        print(f"    H026:   CAGR {m_oos['cagr']:>6.2%}  Sharpe {m_oos['sharpe']:.3f}  MaxDD {m_oos['max_drawdown']:.2%}")
        if "error" not in m_spy_oos:
            print(f"    SPY BH: CAGR {m_spy_oos['cagr']:>6.2%}  Sharpe {m_spy_oos['sharpe']:.3f}  MaxDD {m_spy_oos['max_drawdown']:.2%}")
    else:
        print("    ERROR: empty equity curve")
        results["out_of_sample"] = {"error": "empty"}

    # IS/OOS degradation
    is_sharpe  = results.get("in_sample",     {}).get("h026", {}).get("sharpe")
    oos_sharpe = results.get("out_of_sample", {}).get("h026", {}).get("sharpe")
    oos_deg = None
    if is_sharpe and oos_sharpe and is_sharpe > 0:
        oos_deg = round((is_sharpe - oos_sharpe) / is_sharpe * 100, 1)
        label = "(acceptable <50%)" if oos_deg < 50 else "(OVERFIT WARNING >50%)"
        print(f"\n  IS/OOS degradation (Sharpe): IS={is_sharpe:.3f}  OOS={oos_sharpe:.3f}  deg={oos_deg:.1f}% {label}")

    # Correlation to H020
    print("\n  ── H026 vs H020 MONTHLY RETURN CORRELATION ──")
    corr_h020 = None
    try:
        h020_monthly = load_h020_monthly_returns()

        if not eq_full.empty:
            h026_monthly_eq  = eq_full.resample("ME").last().ffill()
            h026_monthly_ret = h026_monthly_eq.pct_change().dropna()

            common = h026_monthly_ret.index.intersection(h020_monthly.index)
            if len(common) > 12:
                corr_h020 = round(float(h026_monthly_ret.loc[common].corr(h020_monthly.loc[common])), 4)
                print(f"    H026 vs H020 monthly return correlation: {corr_h020:.4f}  (n={len(common)} months)")
            else:
                print(f"    Not enough overlapping months ({len(common)}) to compute correlation")
        else:
            print("    Skipped (no H026 equity curve)")
    except Exception as e:
        print(f"    WARNING: could not compute H020 correlation: {e}")

    # Sector frequency analysis (from holdings log)
    sector_count = {}
    if holdings_log:
        for h in holdings_log:
            for sym in h["holdings"]:
                sector_count[sym] = sector_count.get(sym, 0) + 1
        total_months = len(holdings_log)
        print(f"\n  Sector holding frequency ({total_months} months):")
        for sym, cnt in sorted(sector_count.items(), key=lambda x: -x[1]):
            print(f"    {sym:<6}: {cnt:>3} months  ({cnt/total_months:.1%})")

    # Build output
    output = {
        "strategy":        "H026 — Sector ETF Momentum Rotation",
        "universe":        SECTOR_ETFS,
        "signal":          "rank(12m_momentum) + rank(inv_6m_vol), hold top-3 equal weight",
        "rebalance":       "monthly",
        "full_start":      FULL_START,
        "full_end":        FULL_END,
        "is_cutoff":       IS_END,
        "oos_start":       OOS_START,
        "ticker_starts":   ticker_starts,
        "results":         results,
        "oos_degradation_pct_sharpe": oos_deg,
        "h020_monthly_corr": corr_h020,
        "sector_frequency": sector_count,
    }

    out_path = Path("/workspace/agent/backtesting/results/h026_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    result = run_h026()

    print(f"\n{'═'*72}")
    print("  SUMMARY")
    print(f"{'═'*72}")
    full = result["results"].get("full_period", {}).get("h026", {})
    if full and "error" not in full:
        print(f"  Full period:  CAGR {full['cagr']:.2%}  Sharpe {full['sharpe']:.3f}  MaxDD {full['max_drawdown']:.2%}")
    is_m  = result["results"].get("in_sample",     {}).get("h026", {})
    oos_m = result["results"].get("out_of_sample", {}).get("h026", {})
    if is_m and "error" not in is_m:
        print(f"  IS  (→2015):  CAGR {is_m['cagr']:.2%}  Sharpe {is_m['sharpe']:.3f}  MaxDD {is_m['max_drawdown']:.2%}")
    if oos_m and "error" not in oos_m:
        print(f"  OOS (2016→):  CAGR {oos_m['cagr']:.2%}  Sharpe {oos_m['sharpe']:.3f}  MaxDD {oos_m['max_drawdown']:.2%}")
    deg = result.get("oos_degradation_pct_sharpe")
    if deg is not None:
        print(f"  OOS deg (Sharpe): {deg:.1f}%")
    corr = result.get("h020_monthly_corr")
    if corr is not None:
        print(f"  H026/H020 monthly corr: {corr:.4f}")
