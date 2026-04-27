"""
H035 — H020 + Bitcoin (BTC-USD) as 6th asset

Same signal as H020: top-2 of universe by (12m momentum rank + inverse 6m vol rank).
Universe: SPY / QQQ / TLT / GLD / IEF / BTC-USD

Run periods:
  1. BTC era: 2015-01-01 to 2026-04-25
  2. H020 on same window for direct comparison

Key analyses:
  - How often does BTC rank in top-2?
  - BTC avg return when selected vs not selected
  - H035 vs H020 Sharpe on same window
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

INITIAL_EQUITY = 100_000.0
CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

BTC_START = "2015-01-01"
END       = "2026-04-25"

H20_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
H35_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF", "BTC-USD"]
CASH_ETF    = "SHY"
TOP_N       = 2


# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_path(tickers, start, end):
    import hashlib
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h035_{h}.parquet"


def fetch_close(tickers: list[str], start: str, end: str) -> pd.DataFrame:
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
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
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
# Strategy engine with BTC selection tracking
# ─────────────────────────────────────────────

def run_strategy(
    prices: pd.DataFrame,
    assets: list[str],
    cash_etf: str,
    start: str,
    end: str,
    top_n: int = 2,
    track_asset: str | None = None,
) -> tuple[pd.Series, list[dict]]:
    """
    Returns (daily equity curve, monthly selection log).
    monthly selection log entries: {date, selected, signal_rank, btc_selected}
    """
    available = [a for a in assets if a in prices.columns]
    if cash_etf not in prices.columns:
        print(f"  WARNING: cash ETF {cash_etf} not in prices")
        available_cash = available[0]  # fallback
    else:
        available_cash = cash_etf

    if len(available) < top_n + 1:
        print(f"  ERROR: only {len(available)} assets available, need {top_n+1}")
        return pd.Series(dtype=float), []

    px = prices[available + ([cash_etf] if cash_etf in prices.columns else [])].loc[start:end].dropna(how="all")

    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []
    selection_log = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n + 1:
            continue

        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top = list(combined.nlargest(top_n).index)

        # Build signal rank table for logging
        signal_ranks = combined[valid].sort_values(ascending=False)

        track_selected = track_asset is not None and track_asset in top
        track_rank = None
        if track_asset is not None and track_asset in signal_ranks.index:
            track_rank = int(signal_ranks.index.get_loc(track_asset)) + 1  # 1-based

        selection_log.append({
            "month_end":       str(month_end.date()),
            "selected":        top,
            "signal_scores":   {k: round(float(v), 3) for k, v in combined[valid].items()},
            "track_selected":  track_selected,
            "track_rank":      track_rank,
        })

        # Simulate returns for the following month
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        # Cash weight from non-selected assets (original H020 formula)
        rest = [s for s in valid if s not in top]
        cash_wt = len(rest) / len(valid)

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0, p1 = float(sub[sym].iloc[j-1]), float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / top_n
            if cash_wt > 0 and cash_etf in sub.columns:
                p0 = float(sub[cash_etf].iloc[j-1])
                p1 = float(sub[cash_etf].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float), selection_log

    eq_series = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    return eq_series, selection_log


# ─────────────────────────────────────────────
# BTC contribution analysis
# ─────────────────────────────────────────────

def btc_contribution_analysis(
    prices: pd.DataFrame,
    selection_log: list[dict],
    btc_ticker: str = "BTC-USD",
) -> dict:
    """
    For each month: compute BTC's actual return. Compare months BTC was
    selected vs not selected.
    """
    if btc_ticker not in prices.columns:
        return {"error": "BTC not in prices"}

    monthly_px = prices[[btc_ticker]].resample("ME").last()
    monthly_ret = monthly_px[btc_ticker].pct_change()

    selected_months = []
    not_selected_months = []

    for entry in selection_log:
        me = pd.Timestamp(entry["month_end"])
        # BTC return in THAT month (the month being traded)
        if me in monthly_ret.index:
            r = float(monthly_ret.loc[me])
            if not np.isnan(r):
                if entry["track_selected"]:
                    selected_months.append(r)
                else:
                    not_selected_months.append(r)

    n_selected     = len(selected_months)
    n_not_selected = len(not_selected_months)
    total_months   = n_selected + n_not_selected

    avg_ret_selected     = float(np.mean(selected_months))     if selected_months     else None
    avg_ret_not_selected = float(np.mean(not_selected_months)) if not_selected_months else None
    median_selected      = float(np.median(selected_months))   if selected_months     else None

    return {
        "total_months_evaluated":      total_months,
        "months_btc_in_top2":          n_selected,
        "months_btc_not_in_top2":      n_not_selected,
        "pct_months_btc_selected":     round(n_selected / total_months * 100, 1) if total_months > 0 else 0,
        "btc_avg_monthly_ret_selected":     round(avg_ret_selected * 100, 2)     if avg_ret_selected is not None else None,
        "btc_avg_monthly_ret_not_selected": round(avg_ret_not_selected * 100, 2) if avg_ret_not_selected is not None else None,
        "btc_median_monthly_ret_selected":  round(median_selected * 100, 2)      if median_selected is not None else None,
        "selected_months_list":        [entry["month_end"] for entry in selection_log if entry["track_selected"]],
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("\n" + "═"*72)
    print("H035 — H020 Universe + BTC-USD (SPY/QQQ/TLT/GLD/IEF/BTC-USD top-2)")
    print(f"Period: {BTC_START} → {END}")
    print("═"*72)

    # Fetch all data — H35 universe + cash
    all_tickers = H35_ASSETS + [CASH_ETF]
    print(f"\n  Fetching prices: {all_tickers}")
    prices_h35 = fetch_close(all_tickers, BTC_START, END)

    # Also fetch H20-only data for same period
    h20_tickers = H20_ASSETS + [CASH_ETF]
    prices_h20 = fetch_close(h20_tickers, BTC_START, END)

    print(f"  Data shape: {prices_h35.shape}")
    print(f"  Columns: {list(prices_h35.columns)}")

    # Verify BTC data
    if "BTC-USD" in prices_h35.columns:
        btc_start_actual = prices_h35["BTC-USD"].dropna().index[0]
        print(f"  BTC-USD data starts: {btc_start_actual.date()}")
    else:
        print("  ERROR: BTC-USD not found in fetched data!")
        return {}

    # ── Run H035 ──
    print("\n  Running H035 (6-asset with BTC)…")
    eq_h35, sel_log_h35 = run_strategy(
        prices_h35, H35_ASSETS, CASH_ETF, BTC_START, END, TOP_N, track_asset="BTC-USD"
    )

    # ── Run H020 on same BTC-era window ──
    print("  Running H020 (5-asset, same 2015-2026 window)…")
    eq_h20, sel_log_h20 = run_strategy(
        prices_h20, H20_ASSETS, CASH_ETF, BTC_START, END, TOP_N, track_asset=None
    )

    # ── SPY B&H on same window ──
    spy_px = prices_h20["SPY"].loc[BTC_START:END].dropna()
    eq_spy = INITIAL_EQUITY * (spy_px / spy_px.iloc[0])

    # ── Stats ──
    m35  = calc_stats(eq_h35)
    m20  = calc_stats(eq_h20)
    m_spy = calc_stats(eq_spy.reindex(eq_h20.index).ffill())

    # ── BTC contribution ──
    btc_analysis = btc_contribution_analysis(prices_h35, sel_log_h35, "BTC-USD")

    # ── Print results ──
    print(f"\n  {'Strategy':<35}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>8}  {'Calmar':>7}  {'AnnVol':>7}")
    print(f"  {'─'*75}")
    for name, m in [
        ("H035 (6-asset + BTC)",           m35),
        ("H020 (5-asset, same window)",     m20),
        ("SPY B&H",                         m_spy),
    ]:
        if "error" in m:
            print(f"  {name:<35}  ERROR: {m['error']}")
            continue
        print(f"  {name:<35}  {m['cagr']:>7.2%}  {m['sharpe']:>7.3f}  {m['max_drawdown']:>8.2%}  {m['calmar']:>7.3f}  {m['ann_vol']:>7.2%}")

    print(f"\n  BTC Selection Analysis:")
    print(f"  {'─'*50}")
    print(f"  Total months evaluated:           {btc_analysis['total_months_evaluated']}")
    print(f"  Months BTC in top-2:              {btc_analysis['months_btc_in_top2']}  ({btc_analysis['pct_months_btc_selected']:.1f}%)")
    print(f"  Months BTC NOT in top-2:          {btc_analysis['months_btc_not_in_top2']}")
    if btc_analysis['btc_avg_monthly_ret_selected'] is not None:
        print(f"  BTC avg monthly ret when selected: {btc_analysis['btc_avg_monthly_ret_selected']:+.2f}%")
    if btc_analysis['btc_avg_monthly_ret_not_selected'] is not None:
        print(f"  BTC avg monthly ret when NOT sel:  {btc_analysis['btc_avg_monthly_ret_not_selected']:+.2f}%")

    print(f"\n  First 10 selected months: {btc_analysis['selected_months_list'][:10]}")

    # ── Sharpe delta ──
    if "error" not in m35 and "error" not in m20:
        delta_sharpe = m35["sharpe"] - m20["sharpe"]
        delta_cagr   = m35["cagr"]   - m20["cagr"]
        delta_dd     = m35["max_drawdown"] - m20["max_drawdown"]
        print(f"\n  H035 vs H020 delta (same 2015-2026 window):")
        print(f"    Sharpe:  {delta_sharpe:+.3f}  ({'improved' if delta_sharpe > 0 else 'worsened'})")
        print(f"    CAGR:    {delta_cagr:+.2%}")
        print(f"    MaxDD:   {delta_dd:+.2%}  ({'less deep' if delta_dd > 0 else 'deeper'})")

    # ── BTC rank distribution ──
    rank_counts = {}
    for entry in sel_log_h35:
        r = entry.get("track_rank")
        if r is not None:
            rank_counts[r] = rank_counts.get(r, 0) + 1
    print(f"\n  BTC rank distribution (1=best signal, 6=worst):")
    for rank in sorted(rank_counts.keys()):
        bar = "█" * int(rank_counts[rank] / max(rank_counts.values()) * 20)
        print(f"    Rank {rank}: {rank_counts[rank]:>3}x  {bar}")

    # ── Save results ──
    result = {
        "hypothesis": "H035",
        "description": "H020 + BTC-USD as 6th asset (SPY/QQQ/TLT/GLD/IEF/BTC-USD top-2)",
        "period": f"{BTC_START} to {END}",
        "h035": m35,
        "h020_same_window": m20,
        "spy_bh_same_window": m_spy,
        "btc_selection_analysis": btc_analysis,
        "btc_rank_distribution": rank_counts,
        "delta_vs_h020": {
            "sharpe": round(float(m35["sharpe"] - m20["sharpe"]), 4) if "error" not in m35 and "error" not in m20 else None,
            "cagr":   round(float(m35["cagr"]   - m20["cagr"]),   4) if "error" not in m35 and "error" not in m20 else None,
            "max_drawdown": round(float(m35["max_drawdown"] - m20["max_drawdown"]), 4) if "error" not in m35 and "error" not in m20 else None,
        },
        "selection_log": sel_log_h35,
    }

    out_path = Path(__file__).parent.parent / "results" / "h035_results.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")

    return result


if __name__ == "__main__":
    main()
