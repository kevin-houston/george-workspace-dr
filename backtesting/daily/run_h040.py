"""
H040 — International Equity Expansion of H026
═══════════════════════════════════════════════════════════════════════════
H040:  11 US sector ETFs + 4 international equity ETFs (15 total), hold top-3
H040b: 9 US sector ETFs (drop XLRE/XLC) + EFA + EEM (11 total), hold top-3

International ETFs added:
  EFA  — Developed markets ex-US (iShares MSCI EAFE, ~2001)
  EEM  — Emerging markets        (iShares MSCI EM,   ~2003)
  VGK  — Europe                  (Vanguard FTSE Europe, ~2005)
  EWJ  — Japan                   (iShares MSCI Japan, ~2001)

Signal:   rank(12m_momentum) + rank(inv_6m_vol)  — same as H026
Hold:     top 3 at 33.33% each, monthly rebalance
Period:   longest common history (EFA/EEM earliest → ~2001/2004 start)
IS/OOS:   IS through 2015, OOS 2016-2026

Outputs:
  /workspace/agent/backtesting/results/h040_results.json
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

FULL_START = "2000-01-01"
FULL_END   = "2026-04-27"
IS_END     = "2015-12-31"
OOS_START  = "2016-01-01"

# ── Universe definitions ─────────────────────────────────────────────────────

SECTOR_ETFS = [
    "XLK",   # Technology
    "XLE",   # Energy
    "XLF",   # Financials
    "XLV",   # Healthcare
    "XLI",   # Industrials
    "XLB",   # Materials
    "XLU",   # Utilities
    "XLRE",  # Real Estate (Oct 2015)
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLC",   # Communication Services (Jun 2018)
]

INTL_ETFS = ["EFA", "EEM", "VGK", "EWJ"]

# H040: full 15-ETF universe
H040_UNIVERSE = SECTOR_ETFS + INTL_ETFS

# H040b: drop XLRE + XLC, add EFA + EEM → 11 total
H040B_UNIVERSE = [
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLY", "XLP",  # 9 core sectors
    "EFA", "EEM",
]

TOP_N  = 3
WEIGHT = 1.0 / TOP_N


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, prefix: str, start: str, end: str) -> Path:
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{prefix}_{h}.parquet"


def fetch_close(tickers: list, prefix: str, start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, prefix, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────────────────────
# Core engine — reusable for any universe
# ─────────────────────────────────────────────────────────────────────────────

def run_strategy(
    prices: pd.DataFrame,
    universe: list,
    start: str,
    end: str,
    top_n: int = TOP_N,
) -> tuple[pd.Series, list]:
    """
    Monthly momentum+carry rotation across `universe` tickers.
    Returns (equity_series, holdings_log).
    """
    available = [t for t in universe if t in prices.columns]
    px = prices[available].loc[start:end].dropna(how="all")

    if px.empty or len(px) < 20:
        return pd.Series(dtype=float), []

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / top_n
    equity = INITIAL_EQUITY
    series = []
    holdings_log = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)

        if len(valid) < top_n:
            continue

        score     = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold  = list(score.nlargest(top_n).index)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]

        if len(sub) < 2:
            continue

        holdings_log.append({
            "month":    str(month_end.date()),
            "holdings": top_hold,
        })

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
        return pd.Series(dtype=float), []

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq, holdings_log


# ─────────────────────────────────────────────────────────────────────────────
# H020 monthly returns (for correlation)
# ─────────────────────────────────────────────────────────────────────────────

def load_h020_monthly_returns(prices_cache: pd.DataFrame | None = None) -> pd.Series:
    H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
    CASH_ETF   = "SHY"
    TOP_N_H20  = 2

    all_close = fetch_close(H20_ASSETS + [CASH_ETF], "h040_h020ref", "2007-01-01", FULL_END)
    available = [a for a in H20_ASSETS if a in all_close.columns]
    px_all    = all_close[available + [CASH_ETF]].dropna(how="all")

    monthly_px   = px_all[available].resample("ME").last()
    monthly_rets = px_all[available].pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

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
    monthly_eq   = eq_daily.resample("ME").last().ffill()
    monthly_rets = monthly_eq.pct_change().dropna()
    return monthly_rets


# ─────────────────────────────────────────────────────────────────────────────
# Holdings analysis
# ─────────────────────────────────────────────────────────────────────────────

def holding_frequency(holdings_log: list, universe_label: list) -> dict:
    counts = {}
    for h in holdings_log:
        for sym in h["holdings"]:
            counts[sym] = counts.get(sym, 0) + 1
    total = len(holdings_log)
    return {
        sym: {"count": cnt, "pct": round(cnt / total, 4)}
        for sym, cnt in sorted(counts.items(), key=lambda x: -x[1])
    } if total > 0 else {}


def intl_vs_sector_pct(holdings_log: list, intl: list = INTL_ETFS) -> dict:
    """What fraction of holding-months contain at least 1 intl ETF."""
    total = len(holdings_log)
    if total == 0:
        return {}
    months_with_intl  = sum(1 for h in holdings_log if any(s in intl for s in h["holdings"]))
    intl_slot_months  = sum(sum(1 for s in h["holdings"] if s in intl) for h in holdings_log)
    total_slots       = total * TOP_N
    return {
        "months_with_any_intl":     months_with_intl,
        "pct_months_with_any_intl": round(months_with_intl / total, 4),
        "intl_slot_pct":            round(intl_slot_months / total_slots, 4),
        "total_months":             total,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-variant runner
# ─────────────────────────────────────────────────────────────────────────────

def run_variant(
    name: str,
    universe: list,
    prices: pd.DataFrame,
    spy_all: pd.Series,
    h020_monthly: pd.Series,
    h026_eq_full: pd.Series,
    intl_list: list = INTL_ETFS,
) -> dict:
    print(f"\n{'═'*72}")
    print(f"  {name}")
    print(f"{'═'*72}")

    ticker_starts = {}
    for t in universe:
        if t in prices.columns:
            fv = prices[t].first_valid_index()
            ticker_starts[t] = str(fv.date()) if fv is not None else "N/A"

    print("\n  Ticker availability:")
    for t, s in ticker_starts.items():
        print(f"    {t:<6}: starts {s}")

    results     = {}
    all_holdings = []

    for period_name, s, e in [
        ("full_period",    FULL_START, FULL_END),
        ("in_sample",      FULL_START, IS_END),
        ("out_of_sample",  OOS_START,  FULL_END),
    ]:
        eq, hlog = run_strategy(prices, universe, s, e)
        if period_name == "full_period":
            all_holdings = hlog

        if eq.empty:
            results[period_name] = {"error": "empty equity curve"}
            print(f"\n  ── {period_name.upper()} → empty curve")
            continue

        spy_sub = spy_all.loc[eq.index[0]:eq.index[-1]]
        eq_spy  = INITIAL_EQUITY * (spy_sub / spy_sub.iloc[0]) if not spy_sub.empty else None
        m       = calc_stats(eq)
        m_spy   = calc_stats(eq_spy.reindex(eq.index).ffill()) if eq_spy is not None else {"error": "no spy"}
        results[period_name] = {name.split()[0].lower(): m, "spy_bh": m_spy}

        label = {"full_period": f"FULL ({s}→{e})", "in_sample": f"IS (→{IS_END})", "out_of_sample": f"OOS ({OOS_START}→)"}[period_name]
        print(f"\n  ── {label} ──")
        print(f"    {name.split()[0]:<8}: CAGR {m['cagr']:>6.2%}  Sharpe {m['sharpe']:.3f}  MaxDD {m['max_drawdown']:.2%}  AnnVol {m['ann_vol']:.2%}")
        if "error" not in m_spy:
            print(f"    SPY BH  : CAGR {m_spy['cagr']:>6.2%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.2%}")
        print(f"    Period  : {eq.index[0].date()} → {eq.index[-1].date()}  ({m['n_years']} yrs)")

    # IS/OOS degradation
    variant_key = name.split()[0].lower()
    is_s  = results.get("in_sample",     {}).get(variant_key, {}).get("sharpe")
    oos_s = results.get("out_of_sample", {}).get(variant_key, {}).get("sharpe")
    oos_deg = None
    if is_s and oos_s and is_s > 0:
        oos_deg = round((is_s - oos_s) / is_s * 100, 1)
        label = "(acceptable <50%)" if oos_deg < 50 else "(OVERFIT WARNING >50%)"
        print(f"\n  IS/OOS degradation (Sharpe): IS={is_s:.3f}  OOS={oos_s:.3f}  deg={oos_deg:.1f}% {label}")

    # Holding frequency
    freq = holding_frequency(all_holdings, universe)
    intl_stats = intl_vs_sector_pct(all_holdings, intl_list)
    total_months = len(all_holdings)

    print(f"\n  Holding frequency ({total_months} months):")
    for sym, v in freq.items():
        tag = " [INTL]" if sym in intl_list else ""
        print(f"    {sym:<6}: {v['count']:>3} months  ({v['pct']:.1%}){tag}")

    if intl_stats:
        print(f"\n  International ETF selection rate:")
        print(f"    Months with ≥1 intl ETF: {intl_stats['months_with_any_intl']} / {intl_stats['total_months']} ({intl_stats['pct_months_with_any_intl']:.1%})")
        print(f"    Intl slot fraction:      {intl_stats['intl_slot_pct']:.1%} of all portfolio slots")

    # Correlation to H020
    corr_h020 = None
    eq_full, _ = run_strategy(prices, universe, FULL_START, FULL_END)
    if not eq_full.empty and not h020_monthly.empty:
        mq = eq_full.resample("ME").last().ffill()
        mr = mq.pct_change().dropna()
        common = mr.index.intersection(h020_monthly.index)
        if len(common) > 12:
            corr_h020 = round(float(mr.loc[common].corr(h020_monthly.loc[common])), 4)
            print(f"\n  vs H020 monthly return correlation: {corr_h020:.4f}  (n={len(common)} months)")

    # Correlation to H026
    corr_h026 = None
    if not eq_full.empty and not h026_eq_full.empty:
        mq1 = eq_full.resample("ME").last().ffill()
        mr1 = mq1.pct_change().dropna()
        mq2 = h026_eq_full.resample("ME").last().ffill()
        mr2 = mq2.pct_change().dropna()
        common = mr1.index.intersection(mr2.index)
        if len(common) > 12:
            corr_h026 = round(float(mr1.loc[common].corr(mr2.loc[common])), 4)
            print(f"  vs H026 monthly return correlation: {corr_h026:.4f}  (n={len(common)} months)")

    return {
        "universe":          universe,
        "ticker_starts":     ticker_starts,
        "results":           results,
        "oos_degradation_pct_sharpe": oos_deg,
        "h020_monthly_corr": corr_h020,
        "h026_monthly_corr": corr_h026,
        "holding_frequency": freq,
        "intl_selection":    intl_stats,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 72)
    print("H040 — International Equity Expansion of H026")
    print("═" * 72)

    # Fetch all needed tickers
    all_tickers = list(set(H040_UNIVERSE + H040B_UNIVERSE + ["SPY"]))
    prices_raw  = fetch_close(all_tickers, "h040", FULL_START, FULL_END)

    spy_all = prices_raw["SPY"] if "SPY" in prices_raw.columns else pd.Series(dtype=float)
    prices  = prices_raw[[t for t in prices_raw.columns if t != "SPY"]]

    # H026 equity curve (for correlation baseline)
    print("\n  Building H026 equity curve for correlation baseline …")
    h026_eq_full, _ = run_strategy(prices, SECTOR_ETFS, FULL_START, FULL_END)

    # H020 monthly returns
    print("  Building H020 monthly returns …")
    h020_monthly = load_h020_monthly_returns()

    # Run H040
    h040_results = run_variant(
        "H040 (15 ETFs: 11 sectors + EFA/EEM/VGK/EWJ)",
        H040_UNIVERSE,
        prices,
        spy_all,
        h020_monthly,
        h026_eq_full,
        intl_list=INTL_ETFS,
    )

    # Run H040b
    h040b_results = run_variant(
        "H040b (11 ETFs: 9 sectors + EFA/EEM)",
        H040B_UNIVERSE,
        prices,
        spy_all,
        h020_monthly,
        h026_eq_full,
        intl_list=["EFA", "EEM"],
    )

    # H026 reference stats (from saved results)
    h026_ref = {
        "full_period": {"cagr": 0.1416, "sharpe": 0.8721, "max_drawdown": -0.317, "ann_vol": 0.1623},
        "in_sample":   {"cagr": 0.1212, "sharpe": 0.7419, "max_drawdown": -0.2934},
        "out_of_sample": {"cagr": 0.1710, "sharpe": 1.0335, "max_drawdown": -0.317},
        "oos_degradation_pct_sharpe": -39.3,
        "h020_monthly_corr": 0.4829,
    }

    output = {
        "strategy":    "H040 — International Equity Expansion of H026",
        "signal":      "rank(12m_momentum) + rank(inv_6m_vol), hold top-3 equal weight",
        "rebalance":   "monthly",
        "full_start":  FULL_START,
        "full_end":    FULL_END,
        "is_cutoff":   IS_END,
        "oos_start":   OOS_START,
        "intl_etfs":   INTL_ETFS,
        "h026_reference": h026_ref,
        "h040":        h040_results,
        "h040b":       h040b_results,
    }

    out_path = Path("/workspace/agent/backtesting/results/h040_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")

    # ── Summary table ────────────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print("  SUMMARY COMPARISON")
    print(f"{'═'*72}")
    print(f"  {'Strategy':<12}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>7}  {'AnnVol':>7}  {'vs H026 corr':>12}")
    print(f"  {'-'*68}")

    rows = [
        ("H026 (ref)",  h026_ref["full_period"], None),
        ("H040",        h040_results["results"].get("full_period", {}).get("h040", {}), h040_results.get("h026_monthly_corr")),
        ("H040b",       h040b_results["results"].get("full_period", {}).get("h040b", {}), h040b_results.get("h026_monthly_corr")),
    ]

    for label, m, corr in rows:
        if m and "error" not in m:
            corr_str = f"{corr:.4f}" if corr is not None else "  N/A"
            print(f"  {label:<12}  {m['cagr']:>6.2%}  {m['sharpe']:>7.3f}  {m['max_drawdown']:>6.2%}  {m['ann_vol']:>6.2%}  {corr_str:>12}")
        else:
            print(f"  {label:<12}  (no data)")

    print(f"\n  IS/OOS Sharpe degradation:")
    print(f"    H026:  {h026_ref['oos_degradation_pct_sharpe']:.1f}%")
    if h040_results.get("oos_degradation_pct_sharpe") is not None:
        print(f"    H040:  {h040_results['oos_degradation_pct_sharpe']:.1f}%")
    if h040b_results.get("oos_degradation_pct_sharpe") is not None:
        print(f"    H040b: {h040b_results['oos_degradation_pct_sharpe']:.1f}%")

    return output


if __name__ == "__main__":
    main()
