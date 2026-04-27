"""
H045 — Treasury ETF Momentum Rotation (Pure Fixed-Income Strategy)
===================================================================

Universe (7 Treasury/bond ETFs spanning the yield curve):
  SHY  — iShares 1-3yr Treasury
  IEI  — iShares 3-7yr Treasury
  IEF  — iShares 7-10yr Treasury
  TLT  — iShares 20yr+ Treasury
  TIP  — iShares TIPS / inflation-protected
  HYG  — iShares High-Yield Corporate Bond
  LQD  — iShares Investment-Grade Corporate Bond

Signal: rank(12m_mom) + rank(inv_6m_vol) — same as H020/H041a
  Hold top-2 ETFs at 50/50, monthly rebalance

Hypothesis: The yield curve creates genuine momentum in bond ETFs.
  Rising rates hurt long-duration (TLT) but help short-duration (SHY/IEI).
  This rotation should capture regime shifts in interest-rate cycles.

Period: 2007-01-01 → 2026-04-27 (IEI starts ~2007, full universe available)
  IS: 2007-2016  |  OOS: 2017-2026 (OOS includes 2022 rate-hike cycle)

Benchmarks:
  AGG — iShares Core U.S. Aggregate Bond ETF (buy-and-hold)

Outputs:
  /workspace/agent/backtesting/results/h045_results.json
  /workspace/agent/backtesting/daily/run_h045.py  (this file)
"""

import json
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from collections import defaultdict

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# ── Date ranges ───────────────────────────────────────────────────────────────
FULL_START    = "2002-01-01"   # data download start (warmup for SHY etc.)
FULL_END      = "2026-04-27"
WINDOW_START  = "2007-01-01"   # analysis start (IEI full-universe available)
IS_END        = "2016-12-31"   # In-Sample end
OOS_START     = "2017-01-01"   # Out-of-Sample start

# ── Universe ──────────────────────────────────────────────────────────────────
BOND_UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
BENCHMARK     = "AGG"
TOP_N         = 2


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(tickers: list, start: str, end: str, tag: str = "") -> Path:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h045_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    cp = _cache_path(tickers, start, end, tag)
    if cp.exists():
        print(f"  Loaded {len(tickers)} tickers from cache")
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets: pd.Series, label: str = "") -> dict:
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "label": label}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
        "start":        str(monthly_rets.index[0].date()),
        "end":          str(monthly_rets.index[-1].date()),
    }


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# H045 core strategy
# ─────────────────────────────────────────────────────────────────────────────

def h045_equity_curve(prices: pd.DataFrame, start: str, end: str,
                       track_holdings: bool = False):
    """
    Treasury ETF momentum rotation.
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50, monthly rebalance.

    Returns:
      equity_curve: pd.Series (daily)
      holdings_log: list of dicts (monthly holdings) — only populated if track_holdings=True
    """
    available = [a for a in BOND_UNIVERSE if a in prices.columns]
    if len(available) < TOP_N:
        print(f"ERROR: only {len(available)} tickers available, need {TOP_N}")
        return pd.Series(dtype=float), []

    # Clip to requested window
    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float), []

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N   # 50/50
    equity = INITIAL_EQUITY
    series = []
    holdings_log = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N:
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N).index)

        if track_holdings:
            scores_dict = {sym: round(float(score[sym]), 3) for sym in available if sym in score.index}
            holdings_log.append({
                "month":    str(month_end.date()),
                "holdings": top,
                "scores":   scores_dict,
                "mom_12m":  {sym: round(float(mom_row[sym]), 4) if sym in mom_row else None
                             for sym in available},
                "vol_6m":   {sym: round(float(vol_row[sym]), 4) if sym in vol_row else None
                             for sym in available},
            })

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float), holdings_log

    eq_curve = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq_curve, holdings_log


def benchmark_equity_curve(prices: pd.DataFrame, ticker: str, start: str, end: str) -> pd.Series:
    """Buy-and-hold benchmark."""
    if ticker not in prices.columns:
        return pd.Series(dtype=float)
    px = prices[ticker].loc[start:end].dropna()
    if px.empty:
        return pd.Series(dtype=float)
    return INITIAL_EQUITY * px / px.iloc[0]


# ─────────────────────────────────────────────────────────────────────────────
# Holdings analysis — which ETFs dominate?
# ─────────────────────────────────────────────────────────────────────────────

def analyze_holdings(holdings_log: list, label: str = "") -> dict:
    """Count how many months each ETF was held."""
    counts = defaultdict(int)
    total  = len(holdings_log)
    for entry in holdings_log:
        for sym in entry["holdings"]:
            counts[sym] += 1
    freq = {sym: round(counts[sym] / total, 3) for sym in sorted(counts, key=lambda x: -counts[x])}
    return {
        "label":         label,
        "total_months":  total,
        "hold_counts":   dict(counts),
        "hold_frequency": freq,
    }


def holdings_by_year(holdings_log: list) -> dict:
    """Break down holdings by year to see regime shifts."""
    by_year = defaultdict(lambda: defaultdict(int))
    for entry in holdings_log:
        year = entry["month"][:4]
        for sym in entry["holdings"]:
            by_year[year][sym] += 1
    # convert to plain dicts, sort by most held
    result = {}
    for year in sorted(by_year):
        counts = dict(by_year[year])
        total  = sum(counts.values())
        result[year] = {
            "top": sorted(counts, key=lambda x: -counts[x]),
            "counts": counts,
            "n_months": total // TOP_N,
        }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Correlation to H042
# ─────────────────────────────────────────────────────────────────────────────

def correlation_to_h042(h045_monthly: pd.Series) -> dict:
    """Load H042 monthly returns and compute correlation."""
    result_path = RESULT_DIR / "h042_results.json"
    if not result_path.exists():
        return {"error": "h042_results.json not found"}

    # Reconstruct H042 monthly returns from the standalone H041a stats
    # We need the actual equity curve — load from the H042 script's logic indirectly
    # Actually, we can use a simpler approach: compute correlation via shared AGG benchmark
    # as a proxy. Better: return note that full correlation requires H042 equity curve.
    # We'll compute this from the prices data.
    return {"note": "Computed separately — see h045_vs_h042 key in results"}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H045 — Treasury ETF Momentum Rotation (Pure Fixed-Income)")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = BOND_UNIVERSE + [BENCHMARK]
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h045_all")

    # Also fetch H042-relevant tickers for correlation
    H042_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
    h042_prices = fetch_close(H042_ASSETS, FULL_START, FULL_END, tag="h045_h042assets")

    print(f"  Available tickers: {sorted(prices.columns.tolist())}")
    for t in BOND_UNIVERSE + [BENCHMARK]:
        if t in prices.columns:
            first_valid = prices[t].first_valid_index()
            print(f"    {t}: data from {first_valid.date() if first_valid else 'N/A'}")

    # ── 2. Full-period equity curves ─────────────────────────────────────────
    print(f"\n[2] Building H045 equity curve ({WINDOW_START} → {FULL_END}) …")
    eq_h045_full, holdings_full = h045_equity_curve(
        prices, WINDOW_START, FULL_END, track_holdings=True
    )

    eq_agg_full = benchmark_equity_curve(prices, BENCHMARK, WINDOW_START, FULL_END)

    if eq_h045_full.empty:
        print("ERROR: H045 equity curve is empty. Aborting.")
        return {}

    print(f"   H045: {eq_h045_full.index[0].date()} → {eq_h045_full.index[-1].date()} ({len(eq_h045_full)} days)")

    # ── 3. IS/OOS split ──────────────────────────────────────────────────────
    print(f"\n[3] Building IS ({WINDOW_START} → {IS_END}) equity curves …")
    eq_h045_is, holdings_is = h045_equity_curve(
        prices, WINDOW_START, IS_END, track_holdings=True
    )
    eq_agg_is = benchmark_equity_curve(prices, BENCHMARK, WINDOW_START, IS_END)

    print(f"[4] Building OOS ({OOS_START} → {FULL_END}) equity curves …")
    eq_h045_oos, holdings_oos = h045_equity_curve(
        prices, OOS_START, FULL_END, track_holdings=True
    )
    eq_agg_oos = benchmark_equity_curve(prices, BENCHMARK, OOS_START, FULL_END)

    # ── 4. H042 equity curve for correlation ─────────────────────────────────
    print("\n[5] Building H041a equity curve for H042 correlation …")
    from run_h042 import h041a_equity_curve, to_monthly_returns as tmr_42, INITIAL_EQUITY as IE_42

    # Reuse the h041a function from run_h042 if importable, else inline
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from run_h042 import h041a_equity_curve as h041a_fn
        eq_h041a = h041a_fn(h042_prices)
        r_h041a_monthly = to_monthly_returns(eq_h041a)
        h042_available = True
        print("   H041a (H042 proxy) loaded successfully")
    except Exception as e:
        print(f"   Could not load H041a: {e} — skipping H042 correlation")
        r_h041a_monthly = pd.Series(dtype=float)
        h042_available = False

    # ── 5. Monthly returns ────────────────────────────────────────────────────
    print("\n[6] Computing statistics …")
    r_h045_full = to_monthly_returns(eq_h045_full)
    r_agg_full  = to_monthly_returns(eq_agg_full)

    r_h045_is   = to_monthly_returns(eq_h045_is)
    r_agg_is    = to_monthly_returns(eq_agg_is)

    r_h045_oos  = to_monthly_returns(eq_h045_oos)
    r_agg_oos   = to_monthly_returns(eq_agg_oos)

    # ── 6. Stats ─────────────────────────────────────────────────────────────
    s_full_h045 = stats_from_monthly_returns(r_h045_full, "H045 full")
    s_full_agg  = stats_from_monthly_returns(r_agg_full,  "AGG full")
    s_is_h045   = stats_from_monthly_returns(r_h045_is,   "H045 IS")
    s_is_agg    = stats_from_monthly_returns(r_agg_is,    "AGG IS")
    s_oos_h045  = stats_from_monthly_returns(r_h045_oos,  "H045 OOS")
    s_oos_agg   = stats_from_monthly_returns(r_agg_oos,   "AGG OOS")

    # ── 7. Holdings analysis ─────────────────────────────────────────────────
    print("[7] Analyzing holdings …")
    holdings_summary_full = analyze_holdings(holdings_full, "Full period")
    holdings_summary_is   = analyze_holdings(holdings_is,   "IS 2007-2016")
    holdings_summary_oos  = analyze_holdings(holdings_oos,  "OOS 2017-2026")
    by_year               = holdings_by_year(holdings_full)

    # ── 8. Correlation to H042 ────────────────────────────────────────────────
    print("[8] Computing correlation to H042 …")
    h045_vs_h042 = {}
    if h042_available and not r_h041a_monthly.empty:
        common_idx = r_h045_full.index.intersection(r_h041a_monthly.index)
        if len(common_idx) > 12:
            corr_val = float(r_h045_full.loc[common_idx].corr(r_h041a_monthly.loc[common_idx]))
            h045_vs_h042 = {
                "correlation_to_h041a": round(corr_val, 4),
                "n_common_months":      len(common_idx),
                "interpretation": (
                    "Low correlation (|r| < 0.30) → good 4th component candidate"
                    if abs(corr_val) < 0.30 else
                    "Moderate correlation (0.30 ≤ |r| < 0.50) → partial diversifier"
                    if abs(corr_val) < 0.50 else
                    "High correlation (|r| ≥ 0.50) → limited diversification vs H042"
                ),
            }
            print(f"   H045 vs H041a (H042 proxy) correlation: {corr_val:.4f}")
        else:
            h045_vs_h042 = {"error": "insufficient overlap"}
    else:
        h045_vs_h042 = {"note": "H042 equity curve unavailable for correlation"}

    # ── 9. Print summary tables ───────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  H045 SUMMARY — Treasury Momentum Rotation vs AGG Buy-and-Hold")
    print(f"{'=' * 90}")
    print(f"  {'Period':<20}  {'Strategy':<15}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-'*85}")

    rows = [
        ("Full 2007-2026",    "H045",   s_full_h045),
        ("Full 2007-2026",    "AGG B&H", s_full_agg),
        ("IS   2007-2016",    "H045",   s_is_h045),
        ("IS   2007-2016",    "AGG B&H", s_is_agg),
        ("OOS  2017-2026",    "H045",   s_oos_h045),
        ("OOS  2017-2026",    "AGG B&H", s_oos_agg),
    ]
    for period, strat, s in rows:
        if "error" in s:
            print(f"  {period:<20}  {strat:<15}  (insufficient data)")
            continue
        print(
            f"  {period:<20}  {strat:<15}  "
            f"{s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
            f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}"
        )

    # Holdings breakdown
    print(f"\n{'=' * 90}")
    print("  HOLDINGS FREQUENCY BY ETF")
    print(f"{'=' * 90}")
    print(f"  {'Period':<18}  ", end="")
    for sym in BOND_UNIVERSE:
        print(f"  {sym:>5}", end="")
    print()
    print(f"  {'-'*75}")

    for lbl, summary in [
        ("Full 2007-2026", holdings_summary_full),
        ("IS 2007-2016",   holdings_summary_is),
        ("OOS 2017-2026",  holdings_summary_oos),
    ]:
        print(f"  {lbl:<18}  ", end="")
        for sym in BOND_UNIVERSE:
            freq = summary["hold_frequency"].get(sym, 0.0)
            print(f"  {freq:>5.1%}", end="")
        print()

    # Year-by-year dominant ETF
    print(f"\n  DOMINANT ETF BY YEAR (full period):")
    for year, info in by_year.items():
        top2 = info["top"][:2]
        print(f"    {year}: {', '.join(top2):<18}  ({info['n_months']} months)")

    # H042 correlation
    if "correlation_to_h041a" in h045_vs_h042:
        print(f"\n  H045 vs H041a (H042 proxy) correlation: {h045_vs_h042['correlation_to_h041a']:.4f}")
        print(f"  → {h045_vs_h042['interpretation']}")

    # IS/OOS comparison
    is_sharpe_delta  = s_is_h045.get("sharpe",  0) - s_is_agg.get("sharpe",  0)
    oos_sharpe_delta = s_oos_h045.get("sharpe", 0) - s_oos_agg.get("sharpe", 0)
    print(f"\n  Sharpe alpha vs AGG: IS {is_sharpe_delta:+.3f}  |  OOS {oos_sharpe_delta:+.3f}")

    if oos_sharpe_delta > 0.2:
        verdict = "Strong OOS outperformance — yield-curve momentum is robust; real diversifier candidate"
    elif oos_sharpe_delta > 0.0:
        verdict = "Positive OOS alpha — strategy adds value over AGG in the OOS period"
    elif oos_sharpe_delta > -0.2:
        verdict = "Near-neutral OOS — strategy roughly matches AGG in 2017-2026"
    else:
        verdict = "OOS underperformance — 2022 rate shock may have hurt rotational timing"

    print(f"\n  Verdict: {verdict}")

    # ── 10. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H045 — Treasury ETF Momentum Rotation (Pure Fixed-Income)",
        "description": (
            "7-bond-ETF universe (SHY/IEI/IEF/TLT/TIP/HYG/LQD) rotated by "
            "rank(12m_mom) + rank(inv_6m_vol), holding top-2 at 50/50, monthly rebalance. "
            "Tests whether yield-curve regime shifts create exploitable momentum."
        ),
        "universe":  BOND_UNIVERSE,
        "benchmark": BENCHMARK,
        "signal":    "rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50",
        "rebalance": "monthly",
        "periods": {
            "full":  {"start": WINDOW_START, "end": FULL_END},
            "is":    {"start": WINDOW_START, "end": IS_END},
            "oos":   {"start": OOS_START,    "end": FULL_END},
        },
        "stats": {
            "full_h045": s_full_h045,
            "full_agg":  s_full_agg,
            "is_h045":   s_is_h045,
            "is_agg":    s_is_agg,
            "oos_h045":  s_oos_h045,
            "oos_agg":   s_oos_agg,
        },
        "sharpe_alpha_vs_agg": {
            "is":  round(is_sharpe_delta,  4),
            "oos": round(oos_sharpe_delta, 4),
            "interpretation": {
                "is":  "higher is better; IS 2007-2016 includes low-rate bull market",
                "oos": "OOS 2017-2026 includes 2022 rate-hike cycle — true out-of-sample test",
            },
        },
        "holdings_analysis": {
            "full_period": holdings_summary_full,
            "is_period":   holdings_summary_is,
            "oos_period":  holdings_summary_oos,
            "by_year":     by_year,
        },
        "recent_holdings": holdings_full[-6:] if len(holdings_full) >= 6 else holdings_full,
        "h045_vs_h042": h045_vs_h042,
        "is_oos_delta": {
            "cagr_is":        s_is_h045.get("cagr"),
            "cagr_oos":       s_oos_h045.get("cagr"),
            "sharpe_is":      s_is_h045.get("sharpe"),
            "sharpe_oos":     s_oos_h045.get("sharpe"),
            "max_drawdown_is":  s_is_h045.get("max_drawdown"),
            "max_drawdown_oos": s_oos_h045.get("max_drawdown"),
            "note": "OOS includes 2022 rate-hike cycle — hardest test for bond momentum",
        },
        "verdict": verdict,
        "hypothesis_result": (
            "SUPPORTED" if oos_sharpe_delta > 0 else
            "PARTIALLY SUPPORTED" if oos_sharpe_delta > -0.2 else
            "NOT SUPPORTED"
        ),
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h045_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
