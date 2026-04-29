"""
H126 — Bond ETF Carry: Yield-Augmented Momentum
================================================

Baseline (H045): rank(12m_mom) + rank(inv_6m_vol), hold top-2, monthly rebalance.

H126 adds a carry (yield) term:
  score = rank(12m_mom) + rank(inv_6m_vol) + W * rank(yield)

FRED yield mappings for H045 universe:
  SHY  → DGS2             (2-yr Treasury constant maturity)
  IEI  → DGS5             (5-yr Treasury constant maturity)
  IEF  → DGS10            (10-yr Treasury constant maturity)
  TLT  → DGS20            (20-yr Treasury constant maturity)
  TIP  → DFII10           (10-yr TIPS real yield)
  HYG  → BAMLH0A0HYM2EY  (ICE BofA US HY effective yield)
  LQD  → BAMLC0A0CMEY    (ICE BofA US IG Corp effective yield)

Hypothesis: Among bond ETFs, higher yield predicts better forward return (carry).
  This is especially powerful when momentum is flat (yield-range-bound periods).

Variants:
  W = 0.0  — H045 baseline
  W = 0.5  — light carry
  W = 1.0  — balanced (carry == one momentum term)
  W = 1.5  — carry-leaning
  W = 2.0  — strong carry

Reference H045 OOS (2017–): CAGR and Sharpe vs AGG benchmark.
Requires: FRED_API_KEY environment variable
"""

import os
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from fredapi import Fred

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2002-01-01"
FULL_END     = "2026-04-27"
WINDOW_START = "2007-01-01"   # IEI fully available
IS_END       = "2016-12-31"
OOS_START    = "2017-01-01"
ALT_OOS_ST   = "2013-01-01"   # second OOS window for robustness

BOND_UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
BENCHMARK     = "AGG"
TOP_N         = 2

# FRED series for each ETF's yield
YIELD_MAP = {
    "SHY": "DGS2",
    "IEI": "DGS5",
    "IEF": "DGS10",
    "TLT": "DGS20",
    "TIP": "DFII10",        # 10-yr TIPS real yield
    "HYG": "BAMLH0A0HYM2EY",
    "LQD": "BAMLC0A0CMEY",
}

CARRY_WEIGHTS = [0.0, 0.5, 1.0, 1.5, 2.0]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    tag = "h126_prices"
    cp  = CACHE_DIR / f"{tag}_{start}_{end}.parquet"
    if cp.exists():
        print("  [prices] loaded from cache")
        return pd.read_parquet(cp)
    print(f"  [prices] downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_yield_data(fred: Fred) -> dict[str, pd.Series]:
    """Return dict of {ticker: monthly yield series (end-of-month)}."""
    monthly_yields: dict[str, pd.Series] = {}
    for ticker, fred_id in YIELD_MAP.items():
        try:
            raw = fred.get_series(fred_id, observation_start=FULL_START)
            # resample to month-end, take last observation, forward-fill short gaps
            monthly = raw.resample("ME").last().ffill(limit=3)
            monthly_yields[ticker] = monthly
            print(f"  [yield] {ticker} ({fred_id}): {raw.index[0].date()} → {raw.index[-1].date()}")
        except Exception as e:
            print(f"  [yield] WARNING: could not fetch {fred_id} for {ticker}: {e}")
    return monthly_yields


# ─────────────────────────────────────────────────────────────────────────────
# Core backtest
# ─────────────────────────────────────────────────────────────────────────────

def run_h045_carry(prices: pd.DataFrame, yield_data: dict[str, pd.Series],
                   start: str, end: str, carry_weight: float) -> tuple[pd.Series, list]:
    """
    H045 with optional carry term.

    score = rank(12m_mom) + rank(inv_6m_vol) + carry_weight * rank(yield)
    Hold top-2 at 50/50, monthly rebalance.

    Returns: (equity_curve: pd.Series, holdings_log: list)
    """
    available = [t for t in BOND_UNIVERSE if t in prices.columns]
    if len(available) < TOP_N:
        return pd.Series(dtype=float), []

    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty:
        return pd.Series(dtype=float), []

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    # Align yield data to the same monthly index
    yield_frames: dict[str, pd.Series] = {}
    if carry_weight > 0:
        for t in available:
            if t in yield_data:
                ys = yield_data[t].reindex(monthly_px.index, method="ffill")
                yield_frames[t] = ys

    weight = 1.0 / TOP_N
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

        if carry_weight > 0 and yield_frames:
            yield_vals = {t: float(yield_frames[t].iloc[i])
                          for t in valid
                          if t in yield_frames and not np.isnan(float(yield_frames[t].iloc[i]))}
            yield_valid = list(yield_vals.keys())
            if len(yield_valid) >= TOP_N:
                yield_series = pd.Series(yield_vals)
                # rank ascending: higher yield = better carry = higher rank
                yield_ranks = yield_series.rank()
                valid_with_yield = valid.intersection(yield_series.index)
                score = score.reindex(valid_with_yield).dropna()
                score = score + carry_weight * yield_ranks.reindex(valid_with_yield)
                valid = valid_with_yield
                if len(valid) < TOP_N:
                    continue

        top = list(score.nlargest(TOP_N).index)
        holdings_log.append({"month": str(month_end.date()), "holdings": top})

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

    eq = pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )
    return eq, holdings_log


def benchmark_equity(prices: pd.DataFrame, ticker: str, start: str, end: str) -> pd.Series:
    if ticker not in prices.columns:
        return pd.Series(dtype=float)
    px = prices[ticker].loc[start:end].dropna()
    return INITIAL_EQUITY * px / px.iloc[0]


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def monthly_rets(eq_daily: pd.Series) -> pd.Series:
    return eq_daily.resample("ME").last().ffill().pct_change().dropna()


def cumul_return(rets: pd.Series) -> float:
    if rets.empty:
        return float("nan")
    return float((1 + rets).prod()) - 1


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


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 90)
    print("H126 — Bond ETF Carry: Yield-Augmented Momentum (H045 + rank(yield))")
    print("=" * 90)

    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        print("ERROR: FRED_API_KEY not set")
        return
    fred = Fred(api_key=fred_key)

    # ── 1. Data ──────────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = BOND_UNIVERSE + [BENCHMARK]
    prices = fetch_prices(all_tickers, FULL_START, FULL_END)

    print("\n[2] Fetching FRED yield data …")
    yield_data = fetch_yield_data(fred)
    print(f"  Yields available for: {sorted(yield_data.keys())}")

    # ── 2. AGG benchmark returns ──────────────────────────────────────────────
    eq_agg_oos  = benchmark_equity(prices, BENCHMARK, OOS_START,  FULL_END)
    eq_agg_alt  = benchmark_equity(prices, BENCHMARK, ALT_OOS_ST, FULL_END)
    r_agg_oos   = monthly_rets(eq_agg_oos)
    r_agg_alt   = monthly_rets(eq_agg_alt)
    s_agg_oos   = stats(r_agg_oos,  "AGG OOS")
    s_agg_alt   = stats(r_agg_alt,  "AGG AltOOS")

    # ── 3. Variant sweep ──────────────────────────────────────────────────────
    print("\n[3] Running carry weight variants …")
    results = []

    for W in CARRY_WEIGHTS:
        label = "H045 baseline" if W == 0.0 else f"W={W:.1f}"
        print(f"  {label} …", end=" ", flush=True)

        eq_oos, _ = run_h045_carry(prices, yield_data, OOS_START,  FULL_END, W)
        eq_alt, _ = run_h045_carry(prices, yield_data, ALT_OOS_ST, FULL_END, W)
        eq_is,  _ = run_h045_carry(prices, yield_data, WINDOW_START, IS_END,  W)

        r_oos = monthly_rets(eq_oos)
        r_alt = monthly_rets(eq_alt)
        r_is  = monthly_rets(eq_is)

        s_oos = stats(r_oos, f"{label} OOS")
        s_alt = stats(r_alt, f"{label} AltOOS")
        s_is  = stats(r_is,  f"{label} IS")

        cumul_oos = round(cumul_return(r_oos) * 100, 2)
        cumul_alt = round(cumul_return(r_alt) * 100, 2)

        results.append({
            "W":          W,
            "label":      label,
            "oos":        s_oos,
            "altoos":     s_alt,
            "is_":        s_is,
            "cumul_oos":  cumul_oos,
            "cumul_alt":  cumul_alt,
        })
        print(f"OOS cumul {cumul_oos:+.2f}%  AltOOS {cumul_alt:+.2f}%")

    # ── 4. Print results table ────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    print("  H126 RESULTS — Bond ETF Carry (yield-augmented momentum)")
    print(f"{'=' * 90}")
    print(f"  {'Variant':<20}  {'OOS Cumul':>10}  {'OOS Sharpe':>10}  {'OOS MaxDD':>10}  {'AltOOS Cumul':>13}  {'AltOOS Sharpe':>13}")
    print(f"  {'-'*85}")

    baseline_oos  = results[0]["cumul_oos"]
    baseline_alt  = results[0]["cumul_alt"]
    for r in results:
        d_oos = r["cumul_oos"] - baseline_oos
        d_alt = r["cumul_alt"] - baseline_alt
        s_oos = r["oos"]
        s_alt = r["altoos"]
        flag = " ←" if (d_oos > 0 and d_alt > 0) else ""
        print(
            f"  {r['label']:<20}  {r['cumul_oos']:>+9.2f}%  "
            f"{s_oos.get('sharpe', float('nan')):>10.3f}  "
            f"{s_oos.get('max_drawdown', float('nan')):>10.2%}  "
            f"{r['cumul_alt']:>+12.2f}%  "
            f"{s_alt.get('sharpe', float('nan')):>13.3f}{flag}"
        )

    print(f"\n  AGG (OOS):    cumul {cumul_return(r_agg_oos)*100:+.2f}%  sharpe {s_agg_oos.get('sharpe', float('nan')):.3f}")
    print(f"  AGG (AltOOS): cumul {cumul_return(r_agg_alt)*100:+.2f}%  sharpe {s_agg_alt.get('sharpe', float('nan')):.3f}")

    # ── 5. Verdict ────────────────────────────────────────────────────────────
    print(f"\n{'=' * 90}")
    # Find best W where BOTH OOS and AltOOS improve
    improvements = [r for r in results[1:] if r["cumul_oos"] > baseline_oos and r["cumul_alt"] > baseline_alt]
    if improvements:
        best = max(improvements, key=lambda r: r["cumul_oos"] + r["cumul_alt"])
        print(f"  CONFIRMED candidates: {[r['label'] for r in improvements]}")
        print(f"  Best: {best['label']}  OOS +{best['cumul_oos'] - baseline_oos:.2f}pp  AltOOS +{best['cumul_alt'] - baseline_alt:.2f}pp")
        verdict = "CONFIRMED"
    else:
        print("  No variant improves BOTH OOS and AltOOS vs baseline H045.")
        verdict = "NOT CONFIRMED"
    print(f"  Verdict: {verdict}")

    # ── 6. Yield data snapshot ────────────────────────────────────────────────
    print("\n  Current yields (most recent available):")
    for ticker in BOND_UNIVERSE:
        if ticker in yield_data:
            y = yield_data[ticker]
            last_val  = float(y.dropna().iloc[-1])
            last_date = y.dropna().index[-1].date()
            print(f"    {ticker} ({YIELD_MAP[ticker]}): {last_val:.2f}%  [{last_date}]")

    print()
    return results


if __name__ == "__main__":
    main()
