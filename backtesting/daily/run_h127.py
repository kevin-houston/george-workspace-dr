"""
H127 — TSMOM Filter on H045 Bond ETF Rotation
==============================================

Baseline (H045): rank(12m_mom) + rank(inv_6m_vol), hold top-2 at 50/50.

TSMOM filter: only hold bond ETFs with POSITIVE absolute momentum.
  If only 1 ETF passes → hold 1 at 100%.
  If 0 pass → hold 0 (equity stays in cash; simulated as no return that month).

This mirrors H116's TSMOM upgrade for H026 (sector ETF rotation), which
confirmed +14.6% OOS improvement. H045 currently has no absolute filter —
the cross-sectional rank can select the "best" bond ETF even in a broad
rising-rate selloff (2022: all bonds negative but TLT worst, so SHY selected).

The hypothesis: an absolute quality gate prevents holding any bond ETF
during rate-hike shocks where even the "best" bond is destroying capital.

Variants:
  A) 12m return > 0 filter  (base case — same lookback as primary signal)
  B) 6m return > 0 filter   (faster response)
  C) Both 12m AND 6m > 0    (stricter dual filter)
  D) 3m return > 0 filter   (short-window — tests if recent trend is enough)

Reference (H045 baseline): OOS cumul +44.92%, Sharpe 1.351, MaxDD -6.28%
  AltOOS (2013–): cumul +70.03%, Sharpe 1.397
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2002-01-01"
FULL_END     = "2026-04-27"
WINDOW_START = "2007-01-01"
IS_END       = "2016-12-31"
OOS_START    = "2017-01-01"
ALT_OOS_ST   = "2013-01-01"

BOND_UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
BENCHMARK     = "AGG"
TOP_N         = 2


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h127_prices_{start}_{end}.parquet"
    if cp.exists():
        print("  [prices] loaded from cache")
        return pd.read_parquet(cp)
    # try h126 cache first
    cp126 = CACHE_DIR / f"h126_prices_{start}_{end}.parquet"
    if cp126.exists():
        print("  [prices] reusing h126 cache")
        return pd.read_parquet(cp126)
    print(f"  [prices] downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def benchmark_equity(prices: pd.DataFrame, ticker: str, start: str, end: str) -> pd.Series:
    if ticker not in prices.columns:
        return pd.Series(dtype=float)
    px = prices[ticker].loc[start:end].dropna()
    return INITIAL_EQUITY * px / px.iloc[0]


# ─────────────────────────────────────────────────────────────────────────────
# Core backtest
# ─────────────────────────────────────────────────────────────────────────────

def run_h045_tsmom(prices: pd.DataFrame, start: str, end: str,
                   tsmom_lookbacks: list[int]) -> tuple[pd.Series, list]:
    """
    H045 with TSMOM filter.
    tsmom_lookbacks: list of lookback months that ALL must be positive.
      e.g. [12] = 12m filter, [6] = 6m filter, [12, 6] = both.
    """
    available = [t for t in BOND_UNIVERSE if t in prices.columns]
    if len(available) < 1:
        return pd.Series(dtype=float), []

    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float), []

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    # Precompute all needed momentum lookbacks for TSMOM filter
    mom_by_lb: dict[int, pd.DataFrame] = {}
    max_lb = max(tsmom_lookbacks + [12])
    for lb in set(tsmom_lookbacks):
        mom_by_lb[lb] = monthly_px / monthly_px.shift(lb) - 1

    equity = INITIAL_EQUITY
    series = []
    holdings_log = []
    warmup = max_lb

    for i in range(warmup, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < 1:
            continue

        # Score all candidates
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)

        # Apply TSMOM filter: keep only assets where ALL lookbacks > 0
        passing = list(valid)
        for lb in tsmom_lookbacks:
            lb_row = mom_by_lb[lb].iloc[i]
            passing = [t for t in passing if t in lb_row.index and not np.isnan(float(lb_row[t])) and float(lb_row[t]) > 0]

        if len(passing) == 0:
            # All filtered out: stay in cash (no return this month)
            holdings_log.append({"month": str(month_end.date()), "holdings": [], "filtered_all": True})
            # Keep equity flat — no monthly return
            sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
            sub = px[available].loc[sub_start:month_end]
            for j in range(1, len(sub)):
                series.append((sub.index[j], equity))
            continue

        # Select top-N from passing (or fewer if not enough)
        n_hold = min(TOP_N, len(passing))
        top = list(score.reindex(passing).nlargest(n_hold).index)
        holdings_log.append({"month": str(month_end.date()), "holdings": top})

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        weight = 1.0 / n_hold
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

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq, holdings_log


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def monthly_rets(eq: pd.Series) -> pd.Series:
    return eq.resample("ME").last().ffill().pct_change().dropna()


def cumul_return(rets: pd.Series) -> float:
    return float((1 + rets).prod()) - 1 if not rets.empty else float("nan")


def stats(rets: pd.Series, label: str = "") -> dict:
    rets = rets.dropna()
    if len(rets) < 6:
        return {"label": label, "error": "insufficient data"}
    equity  = (1 + rets).cumprod()
    n_years = len(rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    neg_yrs  = sum(1 for y in rets.groupby(rets.index.year).apply(lambda r: (1 + r).prod() - 1) if y < 0)
    cumul    = float(equity.iloc[-1]) - 1
    return {
        "label": label, "cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4), "calmar": round(calmar, 4),
        "ann_vol": round(vol, 4), "neg_years": neg_yrs,
        "cumul_return": round(cumul, 4), "n_months": len(rets),
    }


def cash_months(holdings_log: list) -> int:
    return sum(1 for h in holdings_log if h.get("filtered_all", False))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 90)
    print("H127 — TSMOM Filter on H045 Bond ETF Rotation")
    print("=" * 90)

    print("\n[1] Fetching prices …")
    prices = fetch_prices(BOND_UNIVERSE + [BENCHMARK], FULL_START, FULL_END)

    eq_agg_oos = benchmark_equity(prices, BENCHMARK, OOS_START,  FULL_END)
    eq_agg_alt = benchmark_equity(prices, BENCHMARK, ALT_OOS_ST, FULL_END)
    r_agg_oos  = monthly_rets(eq_agg_oos)
    r_agg_alt  = monthly_rets(eq_agg_alt)

    VARIANTS = [
        ("Baseline (no filter)", []),
        ("A: 12m>0 filter",      [12]),
        ("B: 6m>0 filter",       [6]),
        ("C: 12m+6m>0 (dual)",   [12, 6]),
        ("D: 3m>0 filter",       [3]),
    ]

    print("\n[2] Running variants …")
    results = []
    for label, lookbacks in VARIANTS:
        print(f"  {label} …", end=" ", flush=True)
        eq_oos, hl_oos = run_h045_tsmom(prices, OOS_START,   FULL_END, lookbacks)
        eq_alt, hl_alt = run_h045_tsmom(prices, ALT_OOS_ST,  FULL_END, lookbacks)
        eq_is,  hl_is  = run_h045_tsmom(prices, WINDOW_START, IS_END,  lookbacks)

        r_oos = monthly_rets(eq_oos)
        r_alt = monthly_rets(eq_alt)
        r_is  = monthly_rets(eq_is)

        s_oos = stats(r_oos, f"{label} OOS")
        s_alt = stats(r_alt, f"{label} AltOOS")
        s_is  = stats(r_is,  f"{label} IS")

        c_oos = round(cumul_return(r_oos) * 100, 2)
        c_alt = round(cumul_return(r_alt) * 100, 2)
        cm    = cash_months(hl_oos)

        results.append({
            "label": label, "lookbacks": lookbacks,
            "oos": s_oos, "altoos": s_alt, "is_": s_is,
            "cumul_oos": c_oos, "cumul_alt": c_alt,
            "cash_months_oos": cm,
        })
        print(f"OOS {c_oos:+.2f}%  AltOOS {c_alt:+.2f}%  cash_mo={cm}")

    # ── Print table ──────────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  H127 RESULTS — TSMOM Filter on H045")
    print(f"{'=' * 90}")
    print(f"  {'Variant':<26}  {'OOS Cumul':>10}  {'OOS Sharpe':>10}  {'MaxDD':>8}  {'AltOOS Cumul':>12}  {'AltOOS Sharpe':>13}  {'CashMo':>7}")
    print(f"  {'-'*92}")

    baseline_oos = results[0]["cumul_oos"]
    baseline_alt = results[0]["cumul_alt"]

    for r in results:
        d_oos = r["cumul_oos"] - baseline_oos
        d_alt = r["cumul_alt"] - baseline_alt
        flag  = " ◄ BOTH" if (d_oos > 0 and d_alt > 0) else ""
        s_oos = r["oos"]
        s_alt = r["altoos"]
        print(
            f"  {r['label']:<26}  {r['cumul_oos']:>+9.2f}%  "
            f"{s_oos.get('sharpe', float('nan')):>10.3f}  "
            f"{s_oos.get('max_drawdown', float('nan')):>8.2%}  "
            f"{r['cumul_alt']:>+11.2f}%  "
            f"{s_alt.get('sharpe', float('nan')):>13.3f}  "
            f"{r['cash_months_oos']:>7}{flag}"
        )

    print(f"\n  AGG OOS: {cumul_return(r_agg_oos)*100:+.2f}%  Sharpe {stats(r_agg_oos).get('sharpe', float('nan')):.3f}")
    print(f"  AGG AltOOS: {cumul_return(r_agg_alt)*100:+.2f}%  Sharpe {stats(r_agg_alt).get('sharpe', float('nan')):.3f}")

    # ── Verdict ──────────────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    improvements = [r for r in results[1:] if r["cumul_oos"] > baseline_oos and r["cumul_alt"] > baseline_alt]
    if improvements:
        best = max(improvements, key=lambda r: r["cumul_oos"] + r["cumul_alt"])
        print(f"  CONFIRMED candidates: {[r['label'] for r in improvements]}")
        print(f"  Best: {best['label']}")
        print(f"    OOS: {baseline_oos:+.2f}% → {best['cumul_oos']:+.2f}% ({best['cumul_oos']-baseline_oos:+.2f}pp)")
        print(f"    AltOOS: {baseline_alt:+.2f}% → {best['cumul_alt']:+.2f}% ({best['cumul_alt']-baseline_alt:+.2f}pp)")
        print(f"  Verdict: CONFIRMED")
    else:
        print("  No variant improves BOTH OOS and AltOOS.")
        print("  Verdict: NOT CONFIRMED")

    return results


if __name__ == "__main__":
    main()
