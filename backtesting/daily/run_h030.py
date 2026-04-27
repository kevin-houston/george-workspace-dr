"""
H030 — Taxable-Optimised Blend: H022 + H026
=============================================
Find the allocation between H022 (tax-efficient multi-asset rotation)
and H026 (sector ETF top-3 momentum) that maximises after-tax Sharpe
for a taxable account.

Universe:
  H022: SPY, QQQ, TLT, GLD, IEF — top-2 momentum+carry, min-hold 12m
  H026: XLK, XLE, XLF, XLV, XLI, XLB, XLU, XLRE, XLY, XLP, XLC — top-3 monthly

Period   : 2008-01-01 → 2026-04-25 (common start driven by H022 warmup)
After-tax: blended effective rate = w_h022 × 20% + w_h026 × 37%
           applied to positive monthly portfolio gains

Outputs:
  /workspace/agent/backtesting/results/h030_results.json
  /workspace/agent/backtesting/daily/run_h030.py  (this file)
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import yfinance as yf

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

INITIAL_EQUITY  = 100_000.0
CACHE_DIR       = Path(__file__).parent.parent / "cache"
RESULTS_DIR     = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

COMMON_START    = "2008-01-01"
COMMON_END      = "2026-04-25"
FULL_FETCH_START = "2007-01-01"   # 12-month warmup for H022

# H022 universe
H022_UNIVERSE = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
H022_TOP_N    = 2
H022_N_ASSETS = len(H022_UNIVERSE)

# H026 universe
H026_SECTORS  = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
H026_TOP_N   = 3
H026_WEIGHT  = 1.0 / H026_TOP_N

# Tax rates
LTCG_RATE    = 0.20   # H022 gains (89.9% LTCG → effective ≈ 20%)
STCG_RATE    = 0.37   # H026 gains (monthly rebalance → all STCG)

# Blend steps
BLEND_STEPS  = [round(w, 1) for w in np.arange(0.0, 1.01, 0.10)]


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_path(label: str, tickers: list, start: str, end: str) -> Path:
    import hashlib
    key = label + "_".join(sorted(tickers)) + f"_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h030_{h}.parquet"


def fetch_close(label: str, tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = _cache_path(label, tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} ({start}→{end}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
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
    eq   = eq.dropna()
    if len(eq) < 10:
        return {"error": "insufficient data after dropna"}
    rets    = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr     = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol      = rets.std() * np.sqrt(12)     # monthly series → *sqrt(12)
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
        "final_value":  round(float(eq.iloc[-1]), 2),
    }


# ─────────────────────────────────────────────
# H022 return series builder
# ─────────────────────────────────────────────

def build_h022_monthly_returns(prices_h022: pd.DataFrame) -> pd.Series:
    """
    Reproduces H022 pre-tax logic:
      - top-2 of [SPY, QQQ, TLT, GLD, IEF] by (12m mom rank + inv 6m vol rank)
      - hold rule: don't sell unless held >=365 days OR score rank == 1 (worst)
    Returns monthly returns indexed by month-end dates.
    """
    assets   = [a for a in H022_UNIVERSE if a in prices_h022.columns]
    px       = prices_h022[assets].dropna(how="all")

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    # Build signal records for all months
    signals = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < H022_TOP_N:
            continue
        combined   = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        score_rank = combined.rank(ascending=True)   # 1=worst, 5=best
        top        = list(combined.nlargest(H022_TOP_N).index)
        signals.append({
            "date":       month_end,
            "top":        top,
            "score_rank": score_rank.to_dict(),
        })

    # Filter to common analysis window
    signals = [s for s in signals
               if s["date"] >= pd.Timestamp(COMMON_START)
               and s["date"] <= pd.Timestamp(COMMON_END)]

    if not signals:
        return pd.Series(dtype=float)

    # Simulate holdings with min-hold rule
    holdings: dict[str, pd.Timestamp] = {}   # ticker → buy_date
    monthly_port_returns = []

    signal_by_date = {s["date"]: s for s in signals}
    valid_months   = sorted(signal_by_date.keys())

    prev_month_end = None

    for idx, month_end in enumerate(valid_months):
        sig        = signal_by_date[month_end]
        desired    = sig["top"]
        score_rank = sig["score_rank"]

        if prev_month_end is None:
            # Initialise
            for ticker in desired:
                holdings[ticker] = month_end
            prev_month_end = month_end
            continue

        # Compute period return for current holdings
        period_px = px.loc[prev_month_end:month_end]
        if len(period_px) < 2:
            prev_month_end = month_end
            continue

        current_tickers = list(holdings.keys())
        # Monthly return = equal-weight average of holdings over the period
        start_prices = {t: float(period_px[t].iloc[0])  for t in current_tickers if t in period_px.columns}
        end_prices   = {t: float(period_px[t].iloc[-1]) for t in current_tickers if t in period_px.columns}
        valid_t      = [t for t in current_tickers if t in start_prices and start_prices[t] > 0]
        if valid_t:
            port_ret = sum((end_prices[t] / start_prices[t] - 1) for t in valid_t) / len(valid_t)
        else:
            port_ret = 0.0
        monthly_port_returns.append((month_end, port_ret))

        # Apply hold rule to determine new holdings
        new_holdings: dict[str, pd.Timestamp] = {}

        for ticker, buy_date in holdings.items():
            if ticker in desired:
                new_holdings[ticker] = buy_date
            else:
                days_held = (month_end - buy_date).days
                rank      = score_rank.get(ticker, 1)
                if days_held >= 365 or rank == 1:
                    pass   # sell (freed slot)
                else:
                    new_holdings[ticker] = buy_date  # hold override

        # Buy into any freed/needed slots
        desired_not_held = [t for t in desired if t not in new_holdings]
        slots_needed     = H022_TOP_N - len(new_holdings)
        for ticker in desired_not_held[:slots_needed]:
            new_holdings[ticker] = month_end

        holdings       = new_holdings
        prev_month_end = month_end

    if not monthly_port_returns:
        return pd.Series(dtype=float)

    rets = pd.Series(
        [r for _, r in monthly_port_returns],
        index=pd.DatetimeIndex([d for d, _ in monthly_port_returns]),
    )
    return rets


# ─────────────────────────────────────────────
# H026 return series builder
# ─────────────────────────────────────────────

def build_h026_monthly_returns(prices_h026: pd.DataFrame) -> pd.Series:
    """
    Sector ETF top-3 momentum rotation, monthly rebalance.
    Returns monthly returns over the common analysis window.
    """
    available = [t for t in H026_SECTORS if t in prices_h026.columns]
    px        = prices_h026[available].dropna(how="all")

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    monthly_port_returns = []
    prev_top      = None
    prev_month_end = None

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]

        if month_end < pd.Timestamp(COMMON_START) or month_end > pd.Timestamp(COMMON_END):
            # Still need to compute top for next period
            mom_row = mom_12.iloc[i].dropna()
            vol_row = vol_6.iloc[i].dropna()
            valid   = mom_row.index.intersection(vol_row.index)
            if len(valid) >= H026_TOP_N:
                score   = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
                prev_top       = list(score.nlargest(H026_TOP_N).index)
                prev_month_end = month_end
            continue

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < H026_TOP_N:
            prev_month_end = month_end
            continue

        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(H026_TOP_N).index)

        # For the *current* month's return, we need the holdings from the *previous* signal
        if prev_top is None or prev_month_end is None:
            prev_top       = top_hold
            prev_month_end = month_end
            continue

        # Period: prev_month_end → month_end
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
        prev_top       = top_hold
        prev_month_end = month_end

    if not monthly_port_returns:
        return pd.Series(dtype=float)

    rets = pd.Series(
        [r for _, r in monthly_port_returns],
        index=pd.DatetimeIndex([d for d, _ in monthly_port_returns]),
    )
    return rets


# ─────────────────────────────────────────────
# After-tax equity curve
# ─────────────────────────────────────────────

def apply_after_tax(monthly_rets: pd.Series, effective_tax_rate: float) -> pd.Series:
    """
    For each monthly return, apply after-tax adjustment:
      - If return > 0: after_tax_ret = ret * (1 - tax_rate)
      - If return <= 0: no tax (loss year; we don't model carryforward for the blend)
    Returns monthly after-tax return series.
    """
    at_rets = monthly_rets.copy()
    at_rets[at_rets > 0] *= (1 - effective_tax_rate)
    return at_rets


def rets_to_equity(monthly_rets: pd.Series, initial: float = INITIAL_EQUITY) -> pd.Series:
    """Convert monthly return series to equity curve."""
    equity = initial * (1 + monthly_rets).cumprod()
    return equity


# ─────────────────────────────────────────────
# SPY benchmark monthly returns
# ─────────────────────────────────────────────

def build_spy_monthly_returns(prices: pd.DataFrame) -> pd.Series:
    spy_px       = prices["SPY"].loc[COMMON_START:COMMON_END].dropna()
    monthly_spy  = spy_px.resample("ME").last()
    spy_rets     = monthly_spy.pct_change().dropna()
    return spy_rets


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 72)
    print("H030 — Taxable-Optimal Blend: H022 + H026")
    print(f"Period  : {COMMON_START} → {COMMON_END}")
    print(f"Blends  : {[f'{int(w*100)}%H022/{int((1-w)*100)}%H026' for w in BLEND_STEPS]}")
    print(f"Tax rates: H022={LTCG_RATE:.0%} LTCG  |  H026={STCG_RATE:.0%} STCG")
    print("=" * 72)

    # ── Fetch prices ───────────────────────────────────────────────────
    print("\n  Fetching H022 universe …")
    prices_h022 = fetch_close("h022", H022_UNIVERSE, FULL_FETCH_START, COMMON_END)
    print(f"    {len(prices_h022)} trading days, cols: {list(prices_h022.columns)}")

    print("\n  Fetching H026 universe …")
    # Use FULL_FETCH_START for warmup (need 12m before COMMON_START)
    prices_h026_raw = fetch_close("h026", H026_SECTORS, FULL_FETCH_START, COMMON_END)
    # Also fetch SPY for benchmark
    prices_spy = fetch_close("spy_bh", ["SPY"], COMMON_START, COMMON_END)
    print(f"    {len(prices_h026_raw)} trading days, cols: {list(prices_h026_raw.columns)}")

    # ── Build return series ─────────────────────────────────────────────
    print("\n  Building H022 monthly return series (with min-hold rule) …")
    h022_rets = build_h022_monthly_returns(prices_h022)
    print(f"    H022: {len(h022_rets)} months  "
          f"({h022_rets.index[0].date()} → {h022_rets.index[-1].date()})")

    print("\n  Building H026 monthly return series (sector momentum top-3) …")
    h026_rets = build_h026_monthly_returns(prices_h026_raw)
    print(f"    H026: {len(h026_rets)} months  "
          f"({h026_rets.index[0].date()} → {h026_rets.index[-1].date()})")

    # ── Align common period ─────────────────────────────────────────────
    common_idx = h022_rets.index.intersection(h026_rets.index)
    common_idx = common_idx[
        (common_idx >= pd.Timestamp(COMMON_START)) &
        (common_idx <= pd.Timestamp(COMMON_END))
    ]
    h022_rets = h022_rets.loc[common_idx]
    h026_rets = h026_rets.loc[common_idx]
    print(f"\n  Common period: {common_idx[0].date()} → {common_idx[-1].date()}  ({len(common_idx)} months)")

    # ── SPY benchmark ───────────────────────────────────────────────────
    spy_rets = build_spy_monthly_returns(prices_spy)
    spy_rets = spy_rets.reindex(common_idx).dropna()
    spy_eq   = rets_to_equity(spy_rets)
    spy_stats_pretax = calc_stats(spy_eq)
    # SPY B&H in taxable: assume long-term hold → LTCG on terminal gain only
    # Approximate: annual dividend yield ~1.5%, taxed at LTCG. Keep it simple — just use pretax.
    spy_at_rets  = apply_after_tax(spy_rets, LTCG_RATE)  # SPY LT hold → LTCG rate
    spy_at_eq    = rets_to_equity(spy_at_rets)
    spy_stats_at = calc_stats(spy_at_eq)

    # ── Correlation between H022 and H026 ──────────────────────────────
    corr_h022_h026 = float(h022_rets.corr(h026_rets))
    print(f"\n  H022 / H026 monthly return correlation: {corr_h022_h026:.4f}")

    # ── H022 standalone (after-tax) reference ─────────────────────────
    h022_at_rets = apply_after_tax(h022_rets, LTCG_RATE)
    h022_at_eq   = rets_to_equity(h022_at_rets)
    h022_pt_eq   = rets_to_equity(h022_rets)
    h022_pt_stats = calc_stats(h022_pt_eq)
    h022_at_stats = calc_stats(h022_at_eq)

    # ── H026 standalone (after-tax) reference ─────────────────────────
    h026_at_rets = apply_after_tax(h026_rets, STCG_RATE)
    h026_at_eq   = rets_to_equity(h026_at_rets)
    h026_pt_eq   = rets_to_equity(h026_rets)
    h026_pt_stats = calc_stats(h026_pt_eq)
    h026_at_stats = calc_stats(h026_at_eq)

    # ── Blend sweep ─────────────────────────────────────────────────────
    print("\n  Running blend sweep …")
    frontier = []

    for w_h022 in BLEND_STEPS:
        w_h026 = round(1.0 - w_h022, 1)
        label  = f"{int(w_h022*100)}%H022/{int(w_h026*100)}%H026"

        # Blended monthly returns (pre-tax)
        blend_rets_pt = w_h022 * h022_rets + w_h026 * h026_rets

        # Pre-tax equity and stats
        blend_eq_pt   = rets_to_equity(blend_rets_pt)
        pt_stats      = calc_stats(blend_eq_pt)

        # After-tax: blended effective rate
        eff_tax_rate  = w_h022 * LTCG_RATE + w_h026 * STCG_RATE
        blend_rets_at = apply_after_tax(blend_rets_pt, eff_tax_rate)
        blend_eq_at   = rets_to_equity(blend_rets_at)
        at_stats      = calc_stats(blend_eq_at)

        row = {
            "label":           label,
            "w_h022":          w_h022,
            "w_h026":          w_h026,
            "eff_tax_rate":    round(eff_tax_rate, 4),
            "pretax_cagr":     pt_stats.get("cagr"),
            "pretax_sharpe":   pt_stats.get("sharpe"),
            "pretax_maxdd":    pt_stats.get("max_drawdown"),
            "pretax_vol":      pt_stats.get("ann_vol"),
            "aftertax_cagr":   at_stats.get("cagr"),
            "aftertax_sharpe": at_stats.get("sharpe"),
            "aftertax_maxdd":  at_stats.get("max_drawdown"),
            "aftertax_vol":    at_stats.get("ann_vol"),
            "final_value_at":  at_stats.get("final_value"),
        }
        frontier.append(row)

    # ── Find optimal ────────────────────────────────────────────────────
    valid_rows  = [r for r in frontier if r["aftertax_sharpe"] is not None]
    best_at_sharpe = max(valid_rows, key=lambda r: r["aftertax_sharpe"])
    best_at_cagr   = max(valid_rows, key=lambda r: r["aftertax_cagr"])

    # Fine-grained sweep around the optimum (1% steps)
    opt_w = best_at_sharpe["w_h022"]
    fine_steps = [round(w, 2) for w in np.arange(
        max(0.0, opt_w - 0.15),
        min(1.0, opt_w + 0.15) + 0.005,
        0.01
    )]
    fine_frontier = []
    for w_h022 in fine_steps:
        w_h026 = round(1.0 - w_h022, 2)
        blend_rets_pt = w_h022 * h022_rets + w_h026 * h026_rets
        blend_eq_pt   = rets_to_equity(blend_rets_pt)
        pt_stats      = calc_stats(blend_eq_pt)
        eff_tax_rate  = w_h022 * LTCG_RATE + w_h026 * STCG_RATE
        blend_rets_at = apply_after_tax(blend_rets_pt, eff_tax_rate)
        blend_eq_at   = rets_to_equity(blend_rets_at)
        at_stats      = calc_stats(blend_eq_at)
        fine_frontier.append({
            "w_h022":          w_h022,
            "w_h026":          w_h026,
            "eff_tax_rate":    round(eff_tax_rate, 4),
            "pretax_cagr":     pt_stats.get("cagr"),
            "pretax_sharpe":   pt_stats.get("sharpe"),
            "pretax_maxdd":    pt_stats.get("max_drawdown"),
            "aftertax_cagr":   at_stats.get("cagr"),
            "aftertax_sharpe": at_stats.get("sharpe"),
            "aftertax_maxdd":  at_stats.get("max_drawdown"),
            "final_value_at":  at_stats.get("final_value"),
        })

    best_fine = max(fine_frontier, key=lambda r: r["aftertax_sharpe"])

    # ── Print results ────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  PRE-TAX EFFICIENT FRONTIER (10% blend steps)")
    print("=" * 80)
    print(f"  {'Blend':<26} {'CAGR':>7} {'Sharpe':>8} {'MaxDD':>8} {'EffTax':>8}")
    print("  " + "-" * 70)
    for row in frontier:
        print(f"  {row['label']:<26} {row['pretax_cagr']:>6.2%}  {row['pretax_sharpe']:>7.3f}  "
              f"{row['pretax_maxdd']:>7.2%}  {row['eff_tax_rate']:>7.2%}")

    print("\n" + "=" * 80)
    print("  AFTER-TAX RESULTS (blended effective tax rate on gains)")
    print("=" * 80)
    print(f"  {'Blend':<26} {'AT CAGR':>8} {'AT Sharpe':>10} {'AT MaxDD':>9} {'Final $':>12}")
    print("  " + "-" * 72)
    for row in frontier:
        marker = " ◀ OPTIMAL" if row["w_h022"] == best_at_sharpe["w_h022"] else ""
        print(f"  {row['label']:<26} {row['aftertax_cagr']:>7.2%}  {row['aftertax_sharpe']:>9.3f}  "
              f"{row['aftertax_maxdd']:>8.2%}  ${row['final_value_at']:>11,.0f}{marker}")

    print(f"\n  Fine-grained optimal (1% steps around {int(opt_w*100)}%H022):")
    print(f"    Best AT Sharpe: w_H022={best_fine['w_h022']:.2f} / w_H026={best_fine['w_h026']:.2f}  "
          f"AT Sharpe={best_fine['aftertax_sharpe']:.4f}  "
          f"AT CAGR={best_fine['aftertax_cagr']:.2%}  "
          f"MaxDD={best_fine['aftertax_maxdd']:.2%}  "
          f"EffTax={best_fine['eff_tax_rate']:.2%}")

    print("\n" + "=" * 80)
    print("  FINAL COMPARISON — H030 (after-tax optimal) vs Benchmarks")
    print("=" * 80)
    print(f"  {'Strategy':<30} {'AT CAGR':>8} {'AT Sharpe':>10} {'MaxDD':>8} {'Notes'}")
    print("  " + "-" * 72)

    opt_label = f"H030 ({int(best_fine['w_h022']*100)}%H022 / {int(best_fine['w_h026']*100)}%H026)"
    rows_cmp = [
        (opt_label,              best_fine["aftertax_cagr"],   best_fine["aftertax_sharpe"],   best_fine["aftertax_maxdd"],  "After-tax optimal blend"),
        ("H022 alone (AT)",      h022_at_stats["cagr"],        h022_at_stats["sharpe"],        h022_at_stats["max_drawdown"], "AT CAGR from prior run: 6.54%"),
        ("H020 alone (AT)",      0.0505,                        0.4081,                         -0.2522,                      "Prior run result"),
        ("SPY B&H (AT, LTCG)",   spy_stats_at["cagr"],         spy_stats_at["sharpe"],         spy_stats_at["max_drawdown"], f"Pre-tax: {spy_stats_pretax['cagr']:.2%}"),
        ("H026 alone (AT)",      h026_at_stats["cagr"],        h026_at_stats["sharpe"],        h026_at_stats["max_drawdown"], "AT approx (STCG rate)"),
    ]
    for label, cagr, sharpe, maxdd, note in rows_cmp:
        print(f"  {label:<30} {cagr:>7.2%}  {sharpe:>9.3f}  {maxdd:>7.2%}   {note}")

    # ── Calibration: simplified model vs known after-tax results ───────────
    # The simplified "tax every positive monthly return" approach significantly
    # understates after-tax performance by ignoring tax deferral.
    # H022's actual after-tax CAGR (from H022 run, lot-level sim) = 6.54%.
    # Here the simplified model gives 4.47%, a 2.07% understatement.
    # The calibration factor accounts for this deferral effect.
    KNOWN_H022_AT_CAGR  = 0.0654
    KNOWN_H020_AT_CAGR  = 0.0505
    h022_simpl_at_cagr  = h022_at_stats["cagr"]
    cagr_uplift_h022    = KNOWN_H022_AT_CAGR - h022_simpl_at_cagr   # deferral benefit

    print("\n" + "=" * 80)
    print("  CALIBRATION: Simplified Model vs Known After-Tax Results")
    print("=" * 80)
    print(f"  H022 simplified AT CAGR:   {h022_simpl_at_cagr:.2%}")
    print(f"  H022 actual AT CAGR (H022 run, lot-level): {KNOWN_H022_AT_CAGR:.2%}")
    print(f"  Deferral uplift (H022):    +{cagr_uplift_h022:.2%}  (tax NOT paid monthly, only on realization)")
    print(f"  H026 has no deferral benefit — monthly rebalance realises gains each month.")
    print(f"\n  Adjusted after-tax CAGR estimates (add deferral uplift proportional to H022 weight):")
    print(f"  {'Blend':<26} {'Model AT CAGR':>14} {'Adjusted AT CAGR':>18}")
    print("  " + "-" * 62)
    for row in frontier:
        adj_cagr = row["aftertax_cagr"] + row["w_h022"] * cagr_uplift_h022
        print(f"  {row['label']:<26} {row['aftertax_cagr']:>13.2%}   {adj_cagr:>16.2%}")

    # Adjusted optimal
    for row in frontier:
        row["adj_aftertax_cagr"] = round(row["aftertax_cagr"] + row["w_h022"] * cagr_uplift_h022, 4)
    best_adj = max(frontier, key=lambda r: r["adj_aftertax_cagr"])
    print(f"\n  Adjusted best AT CAGR blend: {best_adj['label']}  → {best_adj['adj_aftertax_cagr']:.2%}")

    # ── Save ─────────────────────────────────────────────────────────────
    output = {
        "strategy":     "H030 — Taxable-Optimal Blend (H022 + H026)",
        "period":       f"{common_idx[0].date()} → {common_idx[-1].date()}",
        "n_months":     int(len(common_idx)),
        "tax_rates":    {"h022_ltcg": LTCG_RATE, "h026_stcg": STCG_RATE},
        "h022_h026_correlation": round(corr_h022_h026, 4),

        # Standalone stats (on common period)
        "h022_standalone": {
            "pretax":    h022_pt_stats,
            "aftertax":  h022_at_stats,
        },
        "h026_standalone": {
            "pretax":    h026_pt_stats,
            "aftertax":  h026_at_stats,
        },
        "spy_bh": {
            "pretax":    spy_stats_pretax,
            "aftertax":  spy_stats_at,
        },

        # Full frontier table
        "frontier_10pct_steps": frontier,

        # Fine-grained sweep
        "fine_sweep": fine_frontier,

        # Optima
        "optimal_aftertax_sharpe": {
            "coarse": best_at_sharpe,
            "fine":   best_fine,
        },
        "optimal_aftertax_cagr": best_at_cagr,

        # H030 definition
        "h030_definition": {
            "w_h022":           best_fine["w_h022"],
            "w_h026":           best_fine["w_h026"],
            "eff_tax_rate":     best_fine["eff_tax_rate"],
            "aftertax_cagr":    best_fine["aftertax_cagr"],
            "aftertax_sharpe":  best_fine["aftertax_sharpe"],
            "pretax_cagr":      best_fine["pretax_cagr"],
            "pretax_sharpe":    best_fine["pretax_sharpe"],
            "pretax_maxdd":     best_fine["pretax_maxdd"],
            "aftertax_maxdd":   best_fine["aftertax_maxdd"],
        },

        # Comparison to benchmarks
        "benchmark_comparison": {
            "h030_at_cagr":    best_fine["aftertax_cagr"],
            "h030_at_sharpe":  best_fine["aftertax_sharpe"],
            "h022_at_cagr":    h022_at_stats["cagr"],
            "h022_at_cagr_prior_run": 0.0654,
            "h020_at_cagr":    0.0505,
            "spy_pretax_cagr": spy_stats_pretax["cagr"],
            "spy_at_cagr":     spy_stats_at["cagr"],
            "h026_at_cagr":    h026_at_stats["cagr"],
        },
        # Calibration analysis
        "calibration": {
            "h022_simplified_at_cagr":  h022_simpl_at_cagr,
            "h022_actual_at_cagr":      KNOWN_H022_AT_CAGR,
            "deferral_uplift_h022":     round(cagr_uplift_h022, 4),
            "note": ("Simplified model taxes every positive monthly return at the blended rate. "
                     "Actual after-tax benefit is higher for H022 due to tax deferral (positions "
                     "held 12+ months before realization). H026 has no deferral — monthly rebalance "
                     "realises gains each month. Adjusted CAGRs add the H022 deferral benefit "
                     "proportional to H022 weight."),
            "adjusted_frontier": [
                {**r, "adj_aftertax_cagr": round(r["aftertax_cagr"] + r["w_h022"] * cagr_uplift_h022, 4)}
                for r in frontier
            ],
        },
    }

    out_path = RESULTS_DIR / "h030_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
