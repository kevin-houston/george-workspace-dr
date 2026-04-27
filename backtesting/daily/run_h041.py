"""
H041 — International Equity Expansion of H020 Multi-Asset Universe
═══════════════════════════════════════════════════════════════════
H020 universe: SPY, QQQ, TLT, GLD, IEF  (5 assets, top-2, equal weight)
H041a:  7-asset (SPY/QQQ/TLT/GLD/IEF/EFA/EEM), top-2
H041b:  8-asset (SPY/QQQ/TLT/GLD/IEF/EFA/EEM/VWO), top-2

Hypothesis:
  EFA/EEM get selected when US equity is weak, providing equity diversity
  without adding duplicate bonds or gold. They're less correlated within
  a multi-asset universe than within H026's all-equity sector rotation.

Signal:    rank(12m_momentum) + rank(inv_6m_vol)  — identical to H020
Hold:      top-2 at 50/50, monthly rebalance
Period:    2003-01-01 to 2026-04-27
IS/OOS:    IS through 2017-12-31, OOS 2018-01-01 onward (fresh split)
           (EFA/EEM data available from ~2001)

Outputs:
  /workspace/agent/backtesting/results/h041_results.json
  /workspace/agent/backtesting/daily/run_h041.py  (this file)
"""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# ── Universe definitions ─────────────────────────────────────────────────────

H020_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H041B_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "VWO"]
INTL_ETFS    = ["EFA", "EEM", "VWO"]

TOP_N  = 2
WEIGHT = 1.0 / TOP_N  # 50/50


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, prefix: str, start: str, end: str) -> Path:
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"{prefix}_{h}.parquet"


def fetch_close(tickers: list, prefix: str, start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(tickers, prefix, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw
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
# Core engine
# ─────────────────────────────────────────────────────────────────────────────

def run_strategy(
    prices: pd.DataFrame,
    universe: list,
    start: str,
    end: str,
    top_n: int = TOP_N,
) -> tuple:
    """
    Monthly dual-rank rotation (momentum + inverse vol) across universe.
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

        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(top_n).index)

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
# Intl contribution analysis
# ─────────────────────────────────────────────────────────────────────────────

def holding_frequency(holdings_log: list) -> dict:
    counts = {}
    total = len(holdings_log)
    for h in holdings_log:
        for sym in h["holdings"]:
            counts[sym] = counts.get(sym, 0) + 1
    return {
        sym: {"count": cnt, "pct": round(cnt / total, 4)}
        for sym, cnt in sorted(counts.items(), key=lambda x: -x[1])
    } if total > 0 else {}


def intl_selection_stats(holdings_log: list, intl: list, top_n: int = TOP_N) -> dict:
    total = len(holdings_log)
    if total == 0:
        return {}
    months_with_intl = sum(1 for h in holdings_log if any(s in intl for s in h["holdings"]))
    intl_slots = sum(sum(1 for s in h["holdings"] if s in intl) for h in holdings_log)
    total_slots = total * top_n
    return {
        "months_with_any_intl":      months_with_intl,
        "pct_months_with_any_intl":  round(months_with_intl / total, 4),
        "intl_slot_fraction":        round(intl_slots / total_slots, 4),
        "total_months":              total,
    }


def intl_contribution(
    prices: pd.DataFrame,
    holdings_log: list,
    intl: list,
) -> dict:
    """
    Compute average monthly return for intl ETFs when they ARE selected,
    and compare to the full portfolio return in those same months.
    """
    intl_months   = [h for h in holdings_log if any(s in intl for s in h["holdings"])]
    if not intl_months:
        return {"note": "never selected"}

    px_m = prices.resample("ME").last()
    ret_m = px_m.pct_change()

    intl_rets  = []
    port_rets  = []

    for h in intl_months:
        dt = pd.Timestamp(h["month"])
        if dt not in ret_m.index:
            continue
        row = ret_m.loc[dt]
        holdings = h["holdings"]
        port_ret = float(np.mean([row[s] for s in holdings if s in row and not np.isnan(row[s])]))
        for s in holdings:
            if s in intl and s in row and not np.isnan(row[s]):
                intl_rets.append(float(row[s]))
        port_rets.append(port_ret)

    return {
        "avg_monthly_ret_when_selected": round(float(np.mean(intl_rets)), 5) if intl_rets else None,
        "avg_port_ret_those_months":     round(float(np.mean(port_rets)), 5) if port_rets else None,
        "n_intl_holding_months":         len(intl_rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Correlation to H020
# ─────────────────────────────────────────────────────────────────────────────

def compute_correlation(eq_a: pd.Series, eq_b: pd.Series) -> float | None:
    if eq_a.empty or eq_b.empty:
        return None
    ma = eq_a.resample("ME").last().ffill().pct_change().dropna()
    mb = eq_b.resample("ME").last().ffill().pct_change().dropna()
    common = ma.index.intersection(mb.index)
    if len(common) < 12:
        return None
    return round(float(ma.loc[common].corr(mb.loc[common])), 4)


# ─────────────────────────────────────────────────────────────────────────────
# Per-variant runner
# ─────────────────────────────────────────────────────────────────────────────

def run_variant(
    name: str,
    variant_key: str,
    universe: list,
    prices: pd.DataFrame,
    spy_all: pd.Series,
    h020_eq_full: pd.Series,
    intl_list: list,
) -> dict:
    print(f"\n{'═'*72}")
    print(f"  {name}  — universe: {universe}")
    print(f"{'═'*72}")

    # Ticker availability
    ticker_starts = {}
    for t in universe:
        if t in prices.columns:
            fv = prices[t].first_valid_index()
            ticker_starts[t] = str(fv.date()) if fv is not None else "N/A"
    print("\n  Ticker availability:")
    for t, s in ticker_starts.items():
        print(f"    {t:<6}: starts {s}")

    results      = {}
    all_holdings = []
    eq_full      = pd.Series(dtype=float)

    for period_name, s, e in [
        ("full_period",   FULL_START, FULL_END),
        ("in_sample",     FULL_START, IS_END),
        ("out_of_sample", OOS_START,  FULL_END),
    ]:
        eq, hlog = run_strategy(prices, universe, s, e)
        if period_name == "full_period":
            all_holdings = hlog
            eq_full      = eq

        if eq.empty:
            results[period_name] = {"error": "empty equity curve"}
            print(f"\n  ── {period_name.upper()} → empty curve")
            continue

        spy_sub = spy_all.loc[eq.index[0]:eq.index[-1]]
        eq_spy  = (INITIAL_EQUITY * (spy_sub / spy_sub.iloc[0])).reindex(eq.index).ffill() if not spy_sub.empty else None
        m     = calc_stats(eq)
        m_spy = calc_stats(eq_spy) if eq_spy is not None and not eq_spy.empty else {"error": "no spy"}
        results[period_name] = {variant_key: m, "spy_bh": m_spy}

        label = {
            "full_period":   f"FULL ({s}→{e})",
            "in_sample":     f"IS (→{IS_END})",
            "out_of_sample": f"OOS ({OOS_START}→)",
        }[period_name]
        print(f"\n  ── {label} ──")
        print(f"    {variant_key:<8}: CAGR {m['cagr']:>6.2%}  Sharpe {m['sharpe']:.3f}  MaxDD {m['max_drawdown']:.2%}  AnnVol {m['ann_vol']:.2%}")
        if "error" not in m_spy:
            print(f"    SPY BH  : CAGR {m_spy['cagr']:>6.2%}  Sharpe {m_spy['sharpe']:.3f}  MaxDD {m_spy['max_drawdown']:.2%}")
        print(f"    Period  : {eq.index[0].date()} → {eq.index[-1].date()}  ({m['n_years']} yrs)")

    # IS/OOS degradation
    is_s  = results.get("in_sample",     {}).get(variant_key, {}).get("sharpe")
    oos_s = results.get("out_of_sample", {}).get(variant_key, {}).get("sharpe")
    oos_deg = None
    if is_s and oos_s and is_s != 0:
        oos_deg = round((is_s - oos_s) / abs(is_s) * 100, 1)
        flag = "(acceptable <50%)" if oos_deg < 50 else "(OVERFIT WARNING >50%)"
        print(f"\n  IS/OOS degradation (Sharpe): IS={is_s:.3f}  OOS={oos_s:.3f}  deg={oos_deg:.1f}% {flag}")

    # Holding frequency
    freq      = holding_frequency(all_holdings)
    intl_sel  = intl_selection_stats(all_holdings, intl_list, TOP_N)
    intl_cont = intl_contribution(prices, all_holdings, intl_list)

    total_months = len(all_holdings)
    print(f"\n  Holding frequency ({total_months} months):")
    for sym, v in freq.items():
        tag = " [INTL]" if sym in intl_list else ""
        print(f"    {sym:<6}: {v['count']:>3} months  ({v['pct']:.1%}){tag}")

    if intl_sel:
        print(f"\n  International ETF selection stats:")
        print(f"    Months with ≥1 intl ETF : {intl_sel['months_with_any_intl']} / {intl_sel['total_months']} ({intl_sel['pct_months_with_any_intl']:.1%})")
        print(f"    Intl slot fraction       : {intl_sel['intl_slot_fraction']:.1%} of all portfolio slots")
    if intl_cont and "note" not in intl_cont:
        print(f"\n  Intl ETF return contribution:")
        print(f"    Avg monthly ret (intl, when held) : {intl_cont['avg_monthly_ret_when_selected']:.3%}")
        print(f"    Avg port ret in those same months : {intl_cont['avg_port_ret_those_months']:.3%}")
        print(f"    Intl holding-months               : {intl_cont['n_intl_holding_months']}")

    # Correlation to H020
    corr_h020 = compute_correlation(eq_full, h020_eq_full)
    if corr_h020 is not None:
        print(f"\n  vs H020 monthly return correlation: {corr_h020:.4f}")

    return {
        "universe":         universe,
        "ticker_starts":    ticker_starts,
        "results":          results,
        "oos_degradation_pct_sharpe": oos_deg,
        "h020_monthly_corr":  corr_h020,
        "holding_frequency":  freq,
        "intl_selection":     intl_sel,
        "intl_contribution":  intl_cont,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "═" * 72)
    print("H041 — International Equity Expansion of H020 Multi-Asset Universe")
    print("═" * 72)
    print(f"  Period: {FULL_START} → {FULL_END}")
    print(f"  IS/OOS split: IS through {IS_END}, OOS from {OOS_START}")
    print(f"  Hold: top-{TOP_N} equal weight (50/50), monthly rebalance")

    # Fetch all needed prices
    all_tickers = list(set(H041B_ASSETS + ["SPY"]))
    prices_raw  = fetch_close(all_tickers, "h041", FULL_START, FULL_END)
    spy_all     = prices_raw["SPY"] if "SPY" in prices_raw.columns else pd.Series(dtype=float)
    prices      = prices_raw  # include SPY in prices (it's in universe)

    # H020 baseline equity curve (5-asset, same signal, top-2, same period)
    print("\n  Building H020 baseline equity curve …")
    h020_eq_full, h020_hlog = run_strategy(prices, H020_ASSETS, FULL_START, FULL_END)
    h020_stats_full = calc_stats(h020_eq_full)
    h020_freq       = holding_frequency(h020_hlog)
    print(f"  H020 full period: CAGR {h020_stats_full['cagr']:.2%}  Sharpe {h020_stats_full['sharpe']:.3f}  MaxDD {h020_stats_full['max_drawdown']:.2%}")

    h020_is_eq,  _ = run_strategy(prices, H020_ASSETS, FULL_START, IS_END)
    h020_oos_eq, _ = run_strategy(prices, H020_ASSETS, OOS_START,  FULL_END)
    h020_is_stats  = calc_stats(h020_is_eq)
    h020_oos_stats = calc_stats(h020_oos_eq)
    h020_is_s      = h020_is_stats.get("sharpe")
    h020_oos_s     = h020_oos_stats.get("sharpe")
    h020_oos_deg   = round((h020_is_s - h020_oos_s) / abs(h020_is_s) * 100, 1) if h020_is_s and h020_oos_s and h020_is_s != 0 else None

    # Run H041a (7 assets)
    h041a = run_variant(
        "H041a",
        "h041a",
        H041A_ASSETS,
        prices,
        spy_all,
        h020_eq_full,
        intl_list=["EFA", "EEM"],
    )

    # Run H041b (8 assets)
    h041b = run_variant(
        "H041b",
        "h041b",
        H041B_ASSETS,
        prices,
        spy_all,
        h020_eq_full,
        intl_list=["EFA", "EEM", "VWO"],
    )

    # ── Summary comparison ───────────────────────────────────────────────────
    print(f"\n{'═'*72}")
    print("  SUMMARY COMPARISON")
    print(f"{'═'*72}")
    print(f"  {'Strategy':<12}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>8}  {'AnnVol':>7}  {'OOS Sharpe':>10}  {'vs H020':>8}")
    print(f"  {'-'*74}")

    def get_m(variant_results, key, period):
        return variant_results["results"].get(period, {}).get(key, {})

    rows = [
        ("H020",  h020_stats_full, h020_oos_stats, h020_oos_deg,  None),
        ("H041a", get_m(h041a, "h041a", "full_period"), get_m(h041a, "h041a", "out_of_sample"),
                  h041a.get("oos_degradation_pct_sharpe"), h041a.get("h020_monthly_corr")),
        ("H041b", get_m(h041b, "h041b", "full_period"), get_m(h041b, "h041b", "out_of_sample"),
                  h041b.get("oos_degradation_pct_sharpe"), h041b.get("h020_monthly_corr")),
    ]

    for label, mfull, moos, deg, corr in rows:
        if mfull and "error" not in mfull:
            oos_s_str = f"{moos['sharpe']:.3f}" if moos and "error" not in moos else "  N/A"
            deg_str   = f"{deg:.1f}%" if deg is not None else "  N/A"
            corr_str  = f"{corr:.4f}" if corr is not None else "  N/A"
            print(
                f"  {label:<12}  {mfull['cagr']:>6.2%}  {mfull['sharpe']:>7.3f}"
                f"  {mfull['max_drawdown']:>7.2%}  {mfull['ann_vol']:>6.2%}"
                f"  {oos_s_str:>10}  {corr_str:>8}"
            )
        else:
            print(f"  {label:<12}  (no data)")

    print(f"\n  IS/OOS Sharpe degradation (IS through {IS_END}):")
    print(f"    H020:  {h020_oos_deg:.1f}%" if h020_oos_deg is not None else "    H020:  N/A")
    for v, vkey in [(h041a, "H041a"), (h041b, "H041b")]:
        deg = v.get("oos_degradation_pct_sharpe")
        print(f"    {vkey}: {deg:.1f}%" if deg is not None else f"    {vkey}: N/A")

    print(f"\n  International ETF selection rates (full period):")
    for v, vname, ilist in [
        (h041a, "H041a", ["EFA", "EEM"]),
        (h041b, "H041b", ["EFA", "EEM", "VWO"]),
    ]:
        sel = v.get("intl_selection", {})
        if sel:
            print(f"    {vname}: {sel['pct_months_with_any_intl']:.1%} of months have ≥1 intl ETF "
                  f"| {sel['intl_slot_fraction']:.1%} of all slots")
        cont = v.get("intl_contribution", {})
        if cont and "note" not in cont:
            print(f"           avg intl return when held: {cont['avg_monthly_ret_when_selected']:.3%}/mo "
                  f"vs port avg: {cont['avg_port_ret_those_months']:.3%}/mo")

    # Assemble output
    output = {
        "strategy":    "H041 — International Equity Expansion of H020",
        "signal":      "rank(12m_momentum) + rank(inv_6m_vol), hold top-2 equal weight (50/50)",
        "rebalance":   "monthly",
        "full_start":  FULL_START,
        "full_end":    FULL_END,
        "is_cutoff":   IS_END,
        "oos_start":   OOS_START,
        "note":        "Fresh IS/OOS split: IS through 2017 (never used in H020 dev), OOS 2018-2026",
        "h020_baseline": {
            "universe":          H020_ASSETS,
            "full_period_stats": h020_stats_full,
            "is_stats":          h020_is_stats,
            "oos_stats":         h020_oos_stats,
            "oos_degradation_pct_sharpe": h020_oos_deg,
            "holding_frequency": h020_freq,
        },
        "h041a": h041a,
        "h041b": h041b,
    }

    out_path = RESULTS_DIR / "h041_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
