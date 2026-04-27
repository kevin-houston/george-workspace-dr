"""
H039 — Commodity ETF Expansion
================================
Tests whether the momentum+carry signal (12m mom rank + inverse 6m vol rank)
extends to commodity ETFs.

H039a — Expanded H020 (8-asset):
    Universe : SPY, QQQ, TLT, GLD, IEF + DJP, USO, DBA
    Signal   : top-2 by (12m mom rank + inv 6m vol rank), 50/50
    Rebalance: monthly (last trading day of month)

H039b — Commodity-only rotation (3-asset):
    Universe : DJP, GLD, USO
    Signal   : top-1 by (12m mom rank + inv 6m vol rank), 100%
    Rebalance: monthly

Data availability: DJP ~2006, USO 2006, DBA 2007 → common start 2008-01-01
(12m warmup means first signal month = Jan 2008)

Outputs:
  /workspace/agent/backtesting/results/h039_results.json
  /workspace/agent/backtesting/daily/run_h039.py  (this file)

Comparison window: 2008-01-01 → 2026-04-25 (same as H020 analysis period)
"""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# DBA starts 2007-01-05, so we need warmup from 2006-01-01
FULL_FETCH_START = "2006-01-01"
ANALYSIS_START   = "2008-01-01"   # after 12-month warmup for DBA (starts Jan 2007)
ANALYSIS_END     = "2026-04-25"

# H039a universe
H039A_UNIVERSE = ["SPY", "QQQ", "TLT", "GLD", "IEF", "DJP", "USO", "DBA"]
H039A_TOP_N = 2

# H039b universe
H039B_UNIVERSE = ["DJP", "GLD", "USO"]
H039B_TOP_N = 1

# H020 original universe (for comparison)
H020_UNIVERSE = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
H020_TOP_N = 2

# Commodity tickers for selection-frequency analysis
COMMODITY_ETFS = {"DJP", "USO", "DBA"}
ORIGINAL_H020_ETFS = {"SPY", "QQQ", "TLT", "GLD", "IEF"}


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h039_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} ({start} → {end}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Signal: 12m momentum + inverse 6m vol rank
# ─────────────────────────────────────────────

def build_monthly_returns(
    prices: pd.DataFrame,
    assets: list,
    top_n: int,
    analysis_start: str,
    analysis_end: str,
) -> tuple[pd.Series, list]:
    """
    Build monthly return series for a momentum+carry rotation strategy.

    Returns:
        (monthly_return_series, list_of_selection_records)
    """
    available = [a for a in assets if a in prices.columns]
    if len(available) < top_n:
        raise ValueError(f"Need >= {top_n} assets, only have {available}")

    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    monthly_port_returns = []
    selection_records    = []  # for selection-frequency analysis

    prev_top       = None
    prev_month_end = None

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)

        if len(valid) < top_n:
            prev_month_end = month_end
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(combined.nlargest(top_n).index)

        # Only compute returns once inside analysis window
        if month_end < pd.Timestamp(analysis_start) or month_end > pd.Timestamp(analysis_end):
            prev_top       = top_hold
            prev_month_end = month_end
            continue

        if prev_top is None or prev_month_end is None:
            prev_top       = top_hold
            prev_month_end = month_end
            continue

        # Period return: prev_month_end → month_end using prev_top holdings
        period_px = px.loc[prev_month_end:month_end]
        if len(period_px) < 2:
            prev_top       = top_hold
            prev_month_end = month_end
            continue

        valid_t = [t for t in prev_top if t in period_px.columns]
        if valid_t:
            start_p = {t: float(period_px[t].iloc[0])  for t in valid_t}
            end_p   = {t: float(period_px[t].iloc[-1]) for t in valid_t}
            port_ret = sum(
                (end_p[t] / start_p[t] - 1) for t in valid_t if start_p[t] > 0
            ) / len(valid_t)
        else:
            port_ret = 0.0

        monthly_port_returns.append((month_end, port_ret))
        # Record which assets were held this month (what was selected LAST month to hold now)
        selection_records.append({
            "date":     str(month_end.date()),
            "holdings": list(prev_top),
            "selected": list(top_hold),   # what was just selected for next month
            "scores":   {k: round(float(v), 4) for k, v in combined.items()},
        })

        prev_top       = top_hold
        prev_month_end = month_end

    if not monthly_port_returns:
        return pd.Series(dtype=float), []

    rets = pd.Series(
        [r for _, r in monthly_port_returns],
        index=pd.DatetimeIndex([d for d, _ in monthly_port_returns]),
    )
    return rets, selection_records


# ─────────────────────────────────────────────
# Stats (on monthly return series)
# ─────────────────────────────────────────────

def calc_stats(rets: pd.Series) -> dict:
    """Stats from monthly return series."""
    if len(rets) < 10:
        return {"error": "insufficient data"}
    rets = rets.dropna()
    eq   = INITIAL_EQUITY * (1 + rets).cumprod()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr     = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol      = rets.std() * np.sqrt(12)
    sharpe   = cagr / vol if vol > 0 else 0.0
    roll_max = eq.expanding().max()
    max_dd   = float((eq / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    win_rate = float((rets > 0).mean())
    return {
        "cagr":         round(float(cagr),    4),
        "sharpe":       round(float(sharpe),   4),
        "max_drawdown": round(float(max_dd),   4),
        "calmar":       round(float(calmar),   4),
        "ann_vol":      round(float(vol),      4),
        "win_rate":     round(float(win_rate), 4),
        "n_years":      round(float(n_years),  1),
        "final_value":  round(float(eq.iloc[-1]), 2),
    }


# ─────────────────────────────────────────────
# Selection frequency analysis
# ─────────────────────────────────────────────

def selection_freq(selection_records: list, assets: list) -> dict:
    """Count how often each asset appears in holdings."""
    counts = {a: 0 for a in assets}
    total  = 0
    for rec in selection_records:
        for h in rec["holdings"]:
            if h in counts:
                counts[h] += 1
        total += 1
    if total == 0:
        return {a: 0.0 for a in assets}
    return {a: round(counts[a] / total, 4) for a in assets}


def commodity_vs_original_freq(selection_records: list) -> dict:
    """Compute aggregate commodity vs original-5 selection rate."""
    commodity_months = 0
    original_months  = 0
    total_slots      = 0

    for rec in selection_records:
        for h in rec["holdings"]:
            total_slots += 1
            if h in COMMODITY_ETFS:
                commodity_months += 1
            elif h in ORIGINAL_H020_ETFS:
                original_months += 1

    if total_slots == 0:
        return {"commodity_slot_pct": 0.0, "original_slot_pct": 0.0, "total_slots": 0}

    return {
        "commodity_slot_pct": round(commodity_months / total_slots, 4),
        "original_slot_pct":  round(original_months  / total_slots, 4),
        "total_slots":        total_slots,
        "commodity_months":   commodity_months,
        "original_months":    original_months,
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 72)
    print("H039 — Commodity ETF Expansion")
    print(f"Period  : {ANALYSIS_START} → {ANALYSIS_END}")
    print(f"H039a   : {H039A_UNIVERSE}  top-{H039A_TOP_N}")
    print(f"H039b   : {H039B_UNIVERSE}  top-{H039B_TOP_N}")
    print("=" * 72)

    # ── Fetch data ─────────────────────────────────────────────────────
    print("\n  Fetching H039a universe (8-asset) …")
    prices_a = fetch_close(H039A_UNIVERSE, FULL_FETCH_START, ANALYSIS_END, "h039a")
    print(f"    {len(prices_a)} days  cols: {list(prices_a.columns)}")

    # Check actual data availability per ticker
    print("\n  Data availability per ticker:")
    for t in H039A_UNIVERSE:
        if t in prices_a.columns:
            first = prices_a[t].dropna().index[0].date()
            last  = prices_a[t].dropna().index[-1].date()
            n     = prices_a[t].dropna().shape[0]
            print(f"    {t:<5}  {first} → {last}  ({n} days)")
        else:
            print(f"    {t:<5}  NOT FOUND")

    # ── H020 baseline (same period) ────────────────────────────────────
    print(f"\n  Building H020 baseline ({ANALYSIS_START} → {ANALYSIS_END}) …")
    h020_rets, h020_sel = build_monthly_returns(
        prices_a, H020_UNIVERSE, H020_TOP_N, ANALYSIS_START, ANALYSIS_END
    )
    h020_stats = calc_stats(h020_rets)
    print(f"    H020: {len(h020_rets)} months  CAGR={h020_stats.get('cagr', 'ERR'):.2%}  "
          f"Sharpe={h020_stats.get('sharpe', 0):.3f}  MaxDD={h020_stats.get('max_drawdown', 0):.2%}")

    # ── H039a ──────────────────────────────────────────────────────────
    print(f"\n  Building H039a (8-asset expanded, {ANALYSIS_START} → {ANALYSIS_END}) …")
    h039a_rets, h039a_sel = build_monthly_returns(
        prices_a, H039A_UNIVERSE, H039A_TOP_N, ANALYSIS_START, ANALYSIS_END
    )
    h039a_stats = calc_stats(h039a_rets)
    print(f"    H039a: {len(h039a_rets)} months  CAGR={h039a_stats.get('cagr', 0):.2%}  "
          f"Sharpe={h039a_stats.get('sharpe', 0):.3f}  MaxDD={h039a_stats.get('max_drawdown', 0):.2%}")

    # Selection frequency for H039a
    freq_a    = selection_freq(h039a_sel, H039A_UNIVERSE)
    comm_freq = commodity_vs_original_freq(h039a_sel)

    print(f"\n  H039a selection frequency (% of months held):")
    for t in H039A_UNIVERSE:
        bar = "#" * int(freq_a.get(t, 0) * 40)
        print(f"    {t:<5}  {freq_a.get(t, 0):>6.1%}  {bar}")
    print(f"\n  Commodity slots: {comm_freq['commodity_slot_pct']:.1%}  |  "
          f"Original-5 slots: {comm_freq['original_slot_pct']:.1%}  "
          f"(total slots: {comm_freq['total_slots']})")

    # H039a correlation to H020
    common_idx_a = h039a_rets.index.intersection(h020_rets.index)
    if len(common_idx_a) > 10:
        corr_a_h020 = float(h039a_rets.loc[common_idx_a].corr(h020_rets.loc[common_idx_a]))
    else:
        corr_a_h020 = float("nan")
    print(f"\n  H039a correlation to H020: {corr_a_h020:.4f}")

    # ── H039b ──────────────────────────────────────────────────────────
    print(f"\n  Building H039b (commodity-only 3-asset, {ANALYSIS_START} → {ANALYSIS_END}) …")
    h039b_rets, h039b_sel = build_monthly_returns(
        prices_a, H039B_UNIVERSE, H039B_TOP_N, ANALYSIS_START, ANALYSIS_END
    )
    h039b_stats = calc_stats(h039b_rets)
    print(f"    H039b: {len(h039b_rets)} months  CAGR={h039b_stats.get('cagr', 0):.2%}  "
          f"Sharpe={h039b_stats.get('sharpe', 0):.3f}  MaxDD={h039b_stats.get('max_drawdown', 0):.2%}")

    freq_b = selection_freq(h039b_sel, H039B_UNIVERSE)
    print(f"\n  H039b selection frequency:")
    for t in H039B_UNIVERSE:
        bar = "#" * int(freq_b.get(t, 0) * 40)
        print(f"    {t:<5}  {freq_b.get(t, 0):>6.1%}  {bar}")

    # H039b correlation to H020
    common_idx_b = h039b_rets.index.intersection(h020_rets.index)
    if len(common_idx_b) > 10:
        corr_b_h020 = float(h039b_rets.loc[common_idx_b].corr(h020_rets.loc[common_idx_b]))
    else:
        corr_b_h020 = float("nan")
    print(f"\n  H039b correlation to H020: {corr_b_h020:.4f}")

    # ── SPY Buy & Hold benchmark ───────────────────────────────────────
    print(f"\n  Building SPY B&H benchmark …")
    spy_px    = prices_a["SPY"].dropna()
    spy_px    = spy_px.loc[ANALYSIS_START:ANALYSIS_END]
    spy_m     = spy_px.resample("ME").last().pct_change().dropna()
    # Align to same window as strategies
    spy_stats = calc_stats(spy_m)
    print(f"    SPY B&H: CAGR={spy_stats.get('cagr', 0):.2%}  "
          f"Sharpe={spy_stats.get('sharpe', 0):.3f}  MaxDD={spy_stats.get('max_drawdown', 0):.2%}")

    # ── GLD Buy & Hold (commodity baseline) ───────────────────────────
    gld_px  = prices_a["GLD"].dropna().loc[ANALYSIS_START:ANALYSIS_END]
    gld_m   = gld_px.resample("ME").last().pct_change().dropna()
    gld_stats = calc_stats(gld_m)

    # ── DJP Buy & Hold ─────────────────────────────────────────────────
    djp_px  = prices_a["DJP"].dropna().loc[ANALYSIS_START:ANALYSIS_END]
    djp_m   = djp_px.resample("ME").last().pct_change().dropna()
    djp_stats = calc_stats(djp_m)

    # ── Print comparison table ─────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  COMPARISON TABLE — Post-2007 Window")
    print("=" * 80)
    print(f"  {'Strategy':<28} {'CAGR':>7} {'Sharpe':>8} {'MaxDD':>8} {'Vol':>7} {'Months':>7}")
    print("  " + "-" * 72)

    rows = [
        ("H039a  8-asset expanded",  h039a_stats, len(h039a_rets)),
        ("H039b  Commodity-only",    h039b_stats, len(h039b_rets)),
        ("H020   5-asset baseline",  h020_stats,  len(h020_rets)),
        ("SPY    Buy & Hold",        spy_stats,   len(spy_m)),
        ("GLD    Buy & Hold",        gld_stats,   len(gld_m)),
        ("DJP    Buy & Hold",        djp_stats,   len(djp_m)),
    ]
    for label, st, n_months in rows:
        if "error" in st:
            print(f"  {label:<28}  ERROR")
        else:
            print(f"  {label:<28} {st['cagr']:>6.2%}  {st['sharpe']:>7.3f}  "
                  f"{st['max_drawdown']:>7.2%}  {st['ann_vol']:>6.2%}  {n_months:>6}")

    print("\n" + "=" * 80)
    print("  CORRELATIONS TO H020 (monthly returns)")
    print("=" * 80)
    print(f"  H039a  8-asset  vs H020:  {corr_a_h020:.4f}")
    print(f"  H039b  Commodity-only  vs H020:  {corr_b_h020:.4f}")

    print("\n" + "=" * 80)
    print("  H039a SELECTION FREQUENCY (% months each ETF is held)")
    print("=" * 80)
    for t in H039A_UNIVERSE:
        category = "COMMODITY" if t in COMMODITY_ETFS else "original"
        print(f"  {t:<5}  {freq_a.get(t, 0):>6.1%}  [{category}]")
    print(f"\n  Aggregate commodity slot rate: {comm_freq['commodity_slot_pct']:.1%}")
    print(f"  Aggregate original-5 slot rate: {comm_freq['original_slot_pct']:.1%}")

    print("\n" + "=" * 80)
    print("  H039b COMMODITY-ONLY SELECTION FREQUENCY")
    print("=" * 80)
    for t in H039B_UNIVERSE:
        print(f"  {t:<5}  {freq_b.get(t, 0):>6.1%}")

    # ── Save results ───────────────────────────────────────────────────
    output = {
        "strategy":       "H039 — Commodity ETF Expansion",
        "analysis_period": f"{ANALYSIS_START} → {ANALYSIS_END}",
        "fetch_start":    FULL_FETCH_START,

        "h039a": {
            "name":        "Expanded H020 (8-asset)",
            "universe":    H039A_UNIVERSE,
            "top_n":       H039A_TOP_N,
            "stats":       h039a_stats,
            "n_months":    int(len(h039a_rets)),
            "correlation_to_h020": round(corr_a_h020, 4),
            "selection_frequency": {k: round(v, 4) for k, v in freq_a.items()},
            "commodity_vs_original": comm_freq,
            "selection_records_sample": h039a_sel[:12],
        },

        "h039b": {
            "name":        "Commodity-only rotation (3-asset)",
            "universe":    H039B_UNIVERSE,
            "top_n":       H039B_TOP_N,
            "stats":       h039b_stats,
            "n_months":    int(len(h039b_rets)),
            "correlation_to_h020": round(corr_b_h020, 4),
            "selection_frequency": {k: round(v, 4) for k, v in freq_b.items()},
            "selection_records_sample": h039b_sel[:12],
        },

        "h020_baseline": {
            "name":     "H020 5-asset baseline (same window)",
            "universe": H020_UNIVERSE,
            "top_n":    H020_TOP_N,
            "stats":    h020_stats,
            "n_months": int(len(h020_rets)),
        },

        "benchmarks": {
            "spy_bh":  spy_stats,
            "gld_bh":  gld_stats,
            "djp_bh":  djp_stats,
        },

        "data_availability": {
            t: {
                "first_date": str(prices_a[t].dropna().index[0].date()) if t in prices_a.columns else None,
                "n_days":     int(prices_a[t].dropna().shape[0]) if t in prices_a.columns else 0,
            }
            for t in H039A_UNIVERSE
        },
    }

    out_path = RESULTS_DIR / "h039_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
