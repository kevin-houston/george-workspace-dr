"""
H029 — H020 with VIX Term Structure Hard Overlay

H020 baseline:
  Hold top-2 of SPY/QQQ/TLT/GLD/IEF (by momentum+vol rank), 50/50, monthly rebalance.
  Engine: identical to run_h018_h020.py h016_equity_curve (includes SHY cash overlay).

H029 overlay rule (VIX/VIX3M ratio at each month-end):
  If VIX/VIX3M > 1.05 (backwardation):
    H029a: override to 100% IEF (safe-haven), SHY cash overlay removed
    H029b: halve equity (SPY/QQQ) weight, shift to IEF — SHY cash overlay unchanged
  Else: run normal H020

Start: 2007-01-01 (need 12-month momentum warmup, simulate from 2008+)
Data: yfinance SPY/QQQ/TLT/GLD/IEF/SHY + ^VIX/^VIX3M
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

FULL_START      = "2007-01-01"
OOS_END         = "2026-04-26"
INITIAL_EQUITY  = 100_000.0
BACKWARDATION_THRESHOLD = 1.05

H20_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
EQUITY_ASSETS = {"SPY", "QQQ"}
SAFE_HAVEN  = "IEF"
CASH_ETF    = "SHY"
TOP_N       = 2

CACHE_DIR   = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path(__file__).parent.parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────

def _cache_key(tickers, start, end):
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h029_{h}.parquet"


def fetch_closes(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = _cache_key(tickers, start, end)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"]
    else:
        closes = raw[["Close"]]
        closes.columns = [tickers[0]] if len(tickers) == 1 else tickers
    closes.columns = [str(c) for c in closes.columns]
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna().sort_index()
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets     = eq.pct_change().dropna()
    n_years  = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    total_ret = eq.iloc[-1] / eq.iloc[0] - 1
    cagr      = (1 + total_ret) ** (1 / n_years) - 1
    vol       = rets.std() * np.sqrt(252)
    sharpe    = cagr / vol if vol > 0 else 0.0
    roll_max  = eq.expanding().max()
    max_dd    = float((eq / roll_max - 1).min())
    calmar    = abs(cagr / max_dd) if max_dd < 0 else 0.0
    win_rate  = float((rets > 0).mean())
    return {
        "cagr":         round(float(cagr),      4),
        "sharpe":       round(float(sharpe),     4),
        "max_drawdown": round(float(max_dd),     4),
        "calmar":       round(float(calmar),     4),
        "ann_vol":      round(float(vol),        4),
        "win_rate":     round(float(win_rate),   4),
        "n_years":      round(float(n_years),    1),
        "total_return": round(float(total_ret),  4),
    }


# ─────────────────────────────────────────────
# H029 equity-curve engine
# Replicates h016_equity_curve from run_h018_h020.py exactly for mode="h020",
# then applies VIX overlay for mode="h029a" / "h029b".
# ─────────────────────────────────────────────

def h029_equity_curve(
    prices: pd.DataFrame,
    assets: list,
    cash_etf: str,
    start: str,
    end: str,
    top_n: int = 2,
    vix_monthly: pd.Series = None,   # month-end VIX/VIX3M ratios
    mode: str = "h020",               # "h020" | "h029a" | "h029b"
) -> tuple[pd.Series, list]:
    """
    Returns (daily_equity_series, month_records).

    month_records: list of dicts with per-month info for analysis.
    """
    available = [a for a in assets if a in prices.columns]
    if len(available) < top_n:
        return pd.Series(dtype=float), []

    px = prices[available + [cash_etf]].loc[start:end].dropna(how="all")

    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6   = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12  = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []
    month_records = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n:
            continue

        # H020 momentum + inverse-vol rank
        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top  = list(combined.nlargest(top_n).index)
        rest = [s for s in valid if s not in top]
        cash_wt = len(rest) / len(valid)   # SHY overlay weight (same as original h016)

        # ── VIX overlay ────────────────────────────────────────────────
        is_backwardation = False
        vix_ratio = None
        if mode != "h020" and vix_monthly is not None:
            ratio_dates = vix_monthly.index[vix_monthly.index <= month_end]
            if len(ratio_dates) > 0:
                vix_ratio = float(vix_monthly.loc[ratio_dates[-1]])
                is_backwardation = vix_ratio > BACKWARDATION_THRESHOLD

        if is_backwardation:
            if mode == "h029a":
                # Full safe-haven: 100% IEF, no SHY overlay
                top      = [SAFE_HAVEN, SAFE_HAVEN]   # both slots → IEF
                top_n_eff = 2
                cash_wt  = 0.0
            elif mode == "h029b":
                # Half-hedge: halve equity allocation, redirect to IEF
                # Equity assets in top get halved; freed weight goes to IEF
                equity_in_top = [sym for sym in top if sym in EQUITY_ASSETS]
                non_equity_in_top = [sym for sym in top if sym not in EQUITY_ASSETS]

                if equity_in_top:
                    # Replace equity slots with "HALF_EQUITY + half IEF"
                    # We encode this by doubling the top list: keep non-equity slots,
                    # replace each equity slot with the equity at half-weight + IEF at half-weight.
                    # Simpler: track weights dict
                    wts = {}
                    for sym in top:
                        base = 1.0 / top_n
                        if sym in EQUITY_ASSETS:
                            wts[sym]    = wts.get(sym, 0.0) + base / 2.0
                            wts[SAFE_HAVEN] = wts.get(SAFE_HAVEN, 0.0) + base / 2.0
                        else:
                            wts[sym] = wts.get(sym, 0.0) + base
                    # cash_wt (SHY) unchanged from H020 computation
                    top  = None   # signals use wts dict below
                    mode_wts = wts
                else:
                    # No equity in top → H020 unchanged
                    is_backwardation = False
                    mode_wts = None
            else:
                mode_wts = None
        else:
            mode_wts = None

        # ── Apply weights to daily prices ──────────────────────────────
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        equity_start = equity

        for j in range(1, len(sub)):
            port_ret = 0.0

            if mode_wts is not None:
                # H029b variable-weight path
                for sym, wt in mode_wts.items():
                    if sym in sub.columns:
                        p0 = float(sub[sym].iloc[j - 1])
                        p1 = float(sub[sym].iloc[j])
                        if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                            port_ret += wt * (p1 / p0 - 1)
                # SHY cash overlay (unchanged from H020)
                if cash_wt > 0 and cash_etf in sub.columns:
                    p0 = float(sub[cash_etf].iloc[j - 1])
                    p1 = float(sub[cash_etf].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += cash_wt * (p1 / p0 - 1)

            elif is_backwardation and mode == "h029a":
                # 100% IEF, no SHY overlay
                if SAFE_HAVEN in sub.columns:
                    p0 = float(sub[SAFE_HAVEN].iloc[j - 1])
                    p1 = float(sub[SAFE_HAVEN].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret = p1 / p0 - 1

            else:
                # Normal H020 path (exact replica of h016_equity_curve)
                for sym in top:
                    p0 = float(sub[sym].iloc[j - 1])
                    p1 = float(sub[sym].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += (p1 / p0 - 1) / top_n
                if cash_wt > 0 and cash_etf in sub.columns:
                    p0 = float(sub[cash_etf].iloc[j - 1])
                    p1 = float(sub[cash_etf].iloc[j])
                    if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                        port_ret += cash_wt * (p1 / p0 - 1)

            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

        month_ret = equity / equity_start - 1
        # Build descriptor
        if mode_wts is not None:
            wt_desc = {k: round(v, 3) for k, v in mode_wts.items()}
            overlay  = "h029b_half_hedge"
        elif is_backwardation and mode == "h029a":
            wt_desc  = {SAFE_HAVEN: 1.0}
            overlay  = "h029a_full_ief"
        else:
            wt_desc  = {sym: round(1.0 / top_n, 3) for sym in top}
            overlay  = "none"

        month_records.append({
            "month_end":     str(month_end.date()),
            "weights":       wt_desc,
            "overlay":       overlay,
            "vix_ratio":     round(vix_ratio, 4) if vix_ratio is not None else None,
            "month_return":  round(float(month_ret), 6),
            "equity_end":    round(float(equity), 2),
        })

    if not series:
        return pd.Series(dtype=float), []

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    ).sort_index()
    return eq, month_records


# ─────────────────────────────────────────────
# Backwardation-month comparison analysis
# ─────────────────────────────────────────────

def analyze_backwardation(
    months_h020: list,
    months_h029: list,
    label: str = "H029",
) -> dict:
    """
    Compare H020 vs H029 in months where overlay triggered.
    The month_return in records is for the month FOLLOWING the signal.
    We match by month_end (the signal month).
    """
    h020_map = {r["month_end"]: r for r in months_h020}
    h029_map = {r["month_end"]: r for r in months_h029}

    triggered = [r for r in months_h029 if r.get("overlay") != "none"]

    rows = []
    for rec in triggered:
        me  = rec["month_end"]
        h20 = h020_map.get(me, {})
        rows.append({
            "signal_month":     me,
            "vix_ratio":        rec.get("vix_ratio"),
            "h020_return":      h20.get("month_return"),
            "h029_return":      rec.get("month_return"),
            "h020_weights":     h20.get("weights"),
            "h029_weights":     rec.get("weights"),
        })

    if not rows:
        return {"count": 0, "months": []}

    h020_rets = [r["h020_return"] for r in rows if r["h020_return"] is not None]
    h029_rets = [r["h029_return"] for r in rows if r["h029_return"] is not None]

    # Also compute average return in NON-backwardation months for context
    normal_h020 = [r["month_return"] for r in months_h020
                   if h020_map.get(r["month_end"], {}).get("overlay", "none") == "none"
                   and r.get("month_return") is not None]
    # Normal months for H029 (those where overlay didn't trigger)
    normal_h029 = [r["month_return"] for r in months_h029
                   if r.get("overlay") == "none" and r.get("month_return") is not None]

    return {
        "count":          len(rows),
        "pct_of_months":  round(len(rows) / len(months_h029), 4) if months_h029 else 0,
        "h020_avg_return":     round(float(np.mean(h020_rets)), 6) if h020_rets else None,
        "h029_avg_return":     round(float(np.mean(h029_rets)), 6) if h029_rets else None,
        "h020_win_rate":       round(float(np.mean([r > 0 for r in h020_rets])), 4) if h020_rets else None,
        "h029_win_rate":       round(float(np.mean([r > 0 for r in h029_rets])), 4) if h029_rets else None,
        "avg_return_lift":     round(float(np.mean(h029_rets)) - float(np.mean(h020_rets)), 6)
                               if h020_rets and h029_rets else None,
        "normal_h020_avg_return": round(float(np.mean(normal_h020)), 6) if normal_h020 else None,
        "months": rows,
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H029 — H020 + VIX/VIX3M Term Structure Hard Overlay")
    print("=" * 70)

    # ── 1. Fetch price data ─────────────────────────────────────────
    print("\nFetching asset prices …")
    all_tickers = H20_ASSETS + [CASH_ETF]
    prices = fetch_closes(all_tickers, FULL_START, OOS_END)
    prices.columns = [str(c) for c in prices.columns]

    print("Fetching VIX / VIX3M …")
    vix_raw = fetch_closes(["^VIX", "^VIX3M"], "2004-01-01", OOS_END)
    vix_raw.columns = [str(c) for c in vix_raw.columns]

    vix_col   = next((c for c in vix_raw.columns if "VIX"  in c and "3M" not in c), None)
    vix3m_col = next((c for c in vix_raw.columns if "3M" in c), None)

    if not vix_col or not vix3m_col:
        raise ValueError(f"Could not find VIX/VIX3M columns: {vix_raw.columns.tolist()}")

    print(f"  VIX:  {vix_col}")
    print(f"  VIX3M: {vix3m_col}")

    vix_daily = vix_raw[[vix_col, vix3m_col]].dropna()
    vix_daily = vix_daily.rename(columns={vix_col: "VIX", vix3m_col: "VIX3M"})
    vix_daily["ratio"] = vix_daily["VIX"] / vix_daily["VIX3M"]
    vix_monthly = vix_daily["ratio"].resample("ME").last().dropna()

    print(f"  VIX3M range: {vix_daily.index[0].date()} → {vix_daily.index[-1].date()}")
    print(f"  Monthly VIX observations (full history): {len(vix_monthly)}")

    # Restrict to sim period for reporting
    vix_sim = vix_monthly.loc[FULL_START:OOS_END]
    n_backward_full = int((vix_sim > BACKWARDATION_THRESHOLD).sum())
    print(f"  Backwardation months since {FULL_START}: "
          f"{n_backward_full} / {len(vix_sim)} ({n_backward_full/len(vix_sim):.1%})")

    # ── 2. Run backtests ────────────────────────────────────────────
    print("\nRunning backtests …")

    eq_h020, months_h020 = h029_equity_curve(
        prices, H20_ASSETS, CASH_ETF, FULL_START, OOS_END,
        top_n=TOP_N, vix_monthly=None, mode="h020",
    )
    eq_h029a, months_h029a = h029_equity_curve(
        prices, H20_ASSETS, CASH_ETF, FULL_START, OOS_END,
        top_n=TOP_N, vix_monthly=vix_monthly, mode="h029a",
    )
    eq_h029b, months_h029b = h029_equity_curve(
        prices, H20_ASSETS, CASH_ETF, FULL_START, OOS_END,
        top_n=TOP_N, vix_monthly=vix_monthly, mode="h029b",
    )

    # SPY buy-and-hold
    spy = prices["SPY"].loc[FULL_START:OOS_END].dropna()
    eq_spy = INITIAL_EQUITY * (spy / spy.iloc[0])

    # ── 3. Stats ────────────────────────────────────────────────────
    stats_h020  = calc_stats(eq_h020)
    stats_h029a = calc_stats(eq_h029a)
    stats_h029b = calc_stats(eq_h029b)
    stats_spy   = calc_stats(eq_spy)

    # ── 4. Backwardation-month analysis ─────────────────────────────
    print("Analyzing backwardation months …")
    bwd_a = analyze_backwardation(months_h020, months_h029a, "H029a")
    bwd_b = analyze_backwardation(months_h020, months_h029b, "H029b")

    # ── 5. Print results ─────────────────────────────────────────────
    print()
    print(f"{'='*70}")
    print(f"  {'Strategy':<12}  {'CAGR':>7}  {'Sharpe':>7}  {'MaxDD':>8}  {'Calmar':>7}  {'AnnVol':>7}")
    print(f"  {'-'*62}")
    for name, s in [("H020",   stats_h020), ("H029a", stats_h029a),
                    ("H029b",  stats_h029b), ("SPY B&H", stats_spy)]:
        if "error" in s:
            print(f"  {name:<12}  ERROR: {s['error']}")
            continue
        print(f"  {name:<12}  {s['cagr']:>6.2%}  {s['sharpe']:>7.3f}  "
              f"{s['max_drawdown']:>7.2%}  {s['calmar']:>7.3f}  {s['ann_vol']:>6.2%}")

    print(f"\n  Full period: {FULL_START} → {OOS_END}  ({stats_h020.get('n_years','?')} yrs)")

    print(f"\n  Overlay triggered:  {bwd_a['count']} months  "
          f"({bwd_a.get('pct_of_months',0):.1%} of total months)")

    print(f"\n  Returns DURING backwardation months:")
    print(f"  {'Metric':<35}  {'H029a':>10}  {'H029b':>10}")
    print(f"  {'-'*58}")
    print(f"  {'H020 avg monthly return':<35}  "
          f"{bwd_a.get('h020_avg_return', 0):>10.2%}  "
          f"{bwd_b.get('h020_avg_return', 0):>10.2%}")
    print(f"  {'H029 avg monthly return':<35}  "
          f"{bwd_a.get('h029_avg_return', 0) or 0:>10.2%}  "
          f"{bwd_b.get('h029_avg_return', 0) or 0:>10.2%}")
    print(f"  {'Return lift (H029 - H020)':<35}  "
          f"{bwd_a.get('avg_return_lift', 0) or 0:>10.2%}  "
          f"{bwd_b.get('avg_return_lift', 0) or 0:>10.2%}")
    print(f"  {'H020 win rate in backwardation':<35}  "
          f"{bwd_a.get('h020_win_rate', 0):>10.1%}  "
          f"{bwd_b.get('h020_win_rate', 0):>10.1%}")
    print(f"  {'H029 win rate in backwardation':<35}  "
          f"{bwd_a.get('h029_win_rate', 0) or 0:>10.1%}  "
          f"{bwd_b.get('h029_win_rate', 0) or 0:>10.1%}")
    print(f"  {'Normal months H020 avg return':<35}  "
          f"{bwd_a.get('normal_h020_avg_return', 0) or 0:>10.2%}  "
          f"(for context)")

    # Backwardation month detail
    if bwd_a["count"] > 0:
        print(f"\n  Month-by-month overlay detail (H029a):")
        print(f"  {'Signal Month':<14}  {'VIX Ratio':>10}  {'H020 Ret':>10}  {'H029a Ret':>10}  {'H020 Holdings'}")
        print(f"  {'-'*70}")
        for row in bwd_a["months"]:
            h020_ret = row['h020_return']
            h029_ret = row['h029_return']
            h020_wts = row.get('h020_weights', {})
            wt_str = "/".join(h020_wts.keys()) if h020_wts else "?"
            print(f"  {row['signal_month']:<14}  {(row['vix_ratio'] or 0):>10.4f}  "
                  f"{(h020_ret or 0):>10.2%}  {(h029_ret or 0):>10.2%}  {wt_str}")

    # Top asset selections
    selections = {}
    for m in months_h020:
        key = "/".join(sorted(m["weights"].keys()))
        selections[key] = selections.get(key, 0) + 1
    top_sel = sorted(selections.items(), key=lambda x: -x[1])[:8]
    print(f"\n  H020 asset combinations (most frequent):")
    for combo, cnt in top_sel:
        print(f"    {combo:<30} {cnt:>4} months")

    # ── 6. Save results ──────────────────────────────────────────────
    output = {
        "strategy":    "H029",
        "description": "H020 + VIX/VIX3M Term Structure Hard Overlay",
        "variants": {
            "h029a": "Backwardation months → 100% IEF (no SHY overlay)",
            "h029b": "Backwardation months → halve equity weight, shift to IEF",
        },
        "period":      {"start": FULL_START, "end": OOS_END},
        "parameters": {
            "assets":                  H20_ASSETS,
            "top_n":                   TOP_N,
            "backwardation_threshold": BACKWARDATION_THRESHOLD,
            "safe_haven_asset":        SAFE_HAVEN,
            "cash_etf":                CASH_ETF,
            "initial_equity":          INITIAL_EQUITY,
            "engine_note": (
                "Replicates h016_equity_curve: top-2 at 1/top_n weight each "
                "+ SHY cash overlay at len(rest)/len(valid) weight. "
                "H029a replaces all with 100% IEF and removes SHY overlay. "
                "H029b halves equity weight, redirects to IEF, keeps SHY overlay."
            ),
        },
        "stats": {
            "h020":   stats_h020,
            "h029a":  stats_h029a,
            "h029b":  stats_h029b,
            "spy_bh": stats_spy,
        },
        "overlay_summary": {
            "vix_months_in_period":    len(vix_sim),
            "backwardation_months":    n_backward_full,
            "pct_backwardation":       round(n_backward_full / len(vix_sim), 4),
        },
        "backwardation_analysis": {
            "h029a": {k: v for k, v in bwd_a.items() if k != "months"},
            "h029b": {k: v for k, v in bwd_b.items() if k != "months"},
        },
        "backwardation_months_detail": bwd_a.get("months", []),
        "h020_asset_selections": dict(top_sel),
    }

    out_path = RESULTS_DIR / "h029_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
