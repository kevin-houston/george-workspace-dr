"""
H190 — H188 + H181 Momentum/Reversal Blend (same universe)
============================================================
Tests whether blending H188 (52-week high proximity momentum, Sharpe 0.774)
with H181 (industry-adjusted short-term reversal, Sharpe 1.138) improves
risk-adjusted returns. Both strategies operate on the same 30-stock universe.

H188: Long top-6 stocks by proximity to 52-week high (momentum anchor)
H181: Long bottom-6 stocks by industry-adjusted last-month return (reversal)

Since they pick opposite ends of the return distribution, they may hold
DIFFERENT stocks in the same month → low overlap → diversification benefit.

Key from H188 results:
  - Corr(H188, H181) OOS = 0.389 (positive correlation despite opposite signals
    because both are long-only and share market beta)
  - H188 OOS Sharpe=0.774, MaxDD=-13.6%, NegYrs=0
  - H181 OOS Sharpe=1.138, MaxDD=-18.4%, NegYrs=1

Hypothesis: The blend achieves better Sharpe than H188 pure (lifts weak strategy),
while the low portfolio overlap between H188 and H181 selections reduces MaxDD.

Blend weights tested: H188/(H188+H181) = 100/0, 80/20, 60/40, 50/50, 40/60, 20/80, 0/100

Confirm: Any blend achieves OOS Sharpe > 1.138 (beats H181 alone) with MaxDD < -15%.
"""

import warnings
warnings.filterwarnings("ignore")

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
QUINTILE_N = 6

BLEND_WEIGHTS = [
    (1.00, 0.00, "H188 pure"),
    (0.80, 0.20, "80/20"),
    (0.60, 0.40, "60/40"),
    (0.50, 0.50, "50/50"),
    (0.40, 0.60, "40/60"),
    (0.20, 0.80, "20/80"),
    (0.00, 1.00, "H181 pure"),
]


def load_prices() -> pd.DataFrame:
    """Reuse H188 daily cache if available, else H181 monthly cache."""
    # Try H188 daily cache first
    cache_daily = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache_daily.exists():
        print("  Loading daily prices from H188 cache…")
        return pd.read_parquet(cache_daily)

    # Fallback: download
    print(f"  Downloading {len(UNIVERSE)} tickers from yfinance…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices = prices.dropna(how="all", axis=0)
    prices.to_parquet(cache_daily)
    return prices


def run_h188_backtest(daily_prices: pd.DataFrame) -> pd.Series:
    """H188: long top-6 by 52-week high proximity. Returns monthly returns."""
    monthly_px = daily_prices.resample("ME").last()
    month_ends = monthly_px.index

    rets, dates = [], []
    for i in range(1, len(month_ends)):
        rebal_date = month_ends[i - 1]
        hold_date  = month_ends[i]

        if rebal_date < pd.Timestamp(DATA_START) + pd.DateOffset(months=13):
            continue

        hist = daily_prices[daily_prices.index <= rebal_date]
        if len(hist) < 253:
            continue

        last_close = hist.iloc[-1]
        high_252d  = hist.tail(252).max()
        prox = (last_close / high_252d).dropna()
        if len(prox) < QUINTILE_N * 2:
            continue

        long_tickers = prox.nlargest(QUINTILE_N).index.tolist()
        port_rets = []
        for t in long_tickers:
            p1 = monthly_px.loc[rebal_date, t] if (rebal_date in monthly_px.index and t in monthly_px.columns) else np.nan
            p2 = monthly_px.loc[hold_date,  t] if (hold_date  in monthly_px.index and t in monthly_px.columns) else np.nan
            if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                port_rets.append((p2 - p1) / p1)
        if port_rets:
            rets.append(np.mean(port_rets))
            dates.append(hold_date)

    return pd.Series(rets, index=dates, name="h188")


def industry_adjusted_reversal(monthly_returns: pd.Series) -> pd.Series:
    sectors = pd.Series(UNIVERSE_SECTORS)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


def run_h181_backtest(daily_prices: pd.DataFrame) -> pd.Series:
    """H181: long bottom-6 by industry-adjusted last-month return. Returns monthly returns."""
    monthly_px = daily_prices.resample("ME").last()
    months = monthly_px.index

    rets, dates = [], []
    for i in range(2, len(months)):
        prior_close  = monthly_px.iloc[i - 2]
        signal_close = monthly_px.iloc[i - 1]
        hold_close   = monthly_px.iloc[i]

        prior_returns, current_returns = {}, {}
        for t in UNIVERSE:
            if t in prior_close.index and t in signal_close.index:
                p0 = prior_close.get(t)
                p1 = signal_close.get(t)
                p2 = hold_close.get(t, np.nan)
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    prior_returns[t] = (p1 - p0) / p0
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    current_returns[t] = (p2 - p1) / p1

        if len(prior_returns) < QUINTILE_N * 2:
            continue

        adj_rev = industry_adjusted_reversal(pd.Series(prior_returns))
        long_tickers = adj_rev.sort_values().head(QUINTILE_N).index.tolist()
        port_rets = [current_returns[t] for t in long_tickers if t in current_returns]
        if port_rets:
            rets.append(np.mean(port_rets))
            dates.append(months[i])

    return pd.Series(rets, index=dates, name="h181")


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label}
    cum   = (1 + returns).cumprod()
    n_yrs = len(returns) / 12.0
    cagr  = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = returns.mean() / returns.std() * np.sqrt(12) if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1
    annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":      label,
        "n_months":   len(returns),
        "cumul":      round(float(cum.iloc[-1]), 4),
        "cagr_pct":   round(cagr * 100, 2),
        "sharpe":     round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(annual.lt(0).sum()),
    }


def main():
    print("=" * 68)
    print("  H190 — H188 (52wk Momentum) + H181 (Industry Reversal) Blend")
    print("  Same 30-stock universe, 7 blend weights tested")
    print("=" * 68)

    print(f"\n[1/4] Loading prices…")
    prices = load_prices()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 300]
    print(f"  Available: {len(available)}/{len(UNIVERSE)} tickers, "
          f"{prices.index[0].date()} → {prices.index[-1].date()}")
    prices = prices[available]

    # SPY benchmark
    spy_cache = CACHE_DIR / f"h181_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cache.exists():
        spy_close = pd.read_parquet(spy_cache)["close"]
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        close_col = "Close" if "Close" in raw.columns else raw.columns[0]
        spy_close = raw[close_col].resample("ME").last().dropna()
    spy_ret = spy_close.pct_change().dropna()
    spy_oos = spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)]
    spy_oos_m = calc_metrics(spy_oos, "SPY OOS")

    print(f"\n[2/4] Computing H188 monthly returns (52-week high proximity)…")
    h188_ret = run_h188_backtest(prices)
    print(f"  H188 months: {len(h188_ret)}")

    print(f"\n[3/4] Computing H181 monthly returns (industry reversal)…")
    h181_ret = run_h181_backtest(prices)
    print(f"  H181 months: {len(h181_ret)}")

    # Align both series
    h188_oos = h188_ret[(h188_ret.index >= OOS_START) & (h188_ret.index <= OOS_END)]
    h181_oos = h181_ret[(h181_ret.index >= OOS_START) & (h181_ret.index <= OOS_END)]
    common_oos = h188_oos.index.intersection(h181_oos.index)
    h188_oos_a = h188_oos.reindex(common_oos)
    h181_oos_a = h181_oos.reindex(common_oos)
    corr_oos = h188_oos_a.corr(h181_oos_a)

    h188_is = h188_ret[(h188_ret.index >= IS_START) & (h188_ret.index <= IS_END)]
    h181_is = h181_ret[(h181_ret.index >= IS_START) & (h181_ret.index <= IS_END)]
    common_is = h188_is.index.intersection(h181_is.index)
    h188_is_a = h188_is.reindex(common_is)
    h181_is_a = h181_is.reindex(common_is)
    corr_is = h188_is_a.corr(h181_is_a)

    print(f"\n  Corr(H188, H181) IS: {corr_is:.3f}  OOS: {corr_oos:.3f}")

    print(f"\n[4/4] Testing {len(BLEND_WEIGHTS)} blend weights…")
    print(f"\n  {'Label':<14} {'IS Sharpe':>9} {'IS MaxDD':>9} {'OOS Sharpe':>10} {'OOS MaxDD':>9} {'OOS Cumul':>9} {'OOS NegYr':>9}")
    print("  " + "-" * 70)

    results = []
    best_oos_sharpe = -999
    best_label = ""

    for w188, w181, label in BLEND_WEIGHTS:
        # IS blend
        blend_is = w188 * h188_is_a + w181 * h181_is_a
        is_m = calc_metrics(blend_is, label)
        # OOS blend
        blend_oos = w188 * h188_oos_a + w181 * h181_oos_a
        oos_m = calc_metrics(blend_oos, label)

        print(f"  {label:<14} {is_m.get('sharpe', 0):>9.3f} {is_m.get('max_dd_pct', 0):>9.1f}%"
              f" {oos_m.get('sharpe', 0):>10.3f} {oos_m.get('max_dd_pct', 0):>9.1f}%"
              f" {oos_m.get('cumul', 0):>9.3f}× {oos_m.get('neg_years', 0):>9d}")

        results.append({
            "w188": w188, "w181": w181, "label": label,
            "is_sharpe": is_m.get("sharpe", 0),
            "is_maxdd":  is_m.get("max_dd_pct", 0),
            "oos_sharpe": oos_m.get("sharpe", 0),
            "oos_maxdd":  oos_m.get("max_dd_pct", 0),
            "oos_cumul":  oos_m.get("cumul", 0),
            "oos_negyrs": oos_m.get("neg_years", 0),
        })
        if oos_m.get("sharpe", 0) > best_oos_sharpe:
            best_oos_sharpe = oos_m.get("sharpe", 0)
            best_label = label

    print(f"\n  SPY OOS:       {'—':>9} {'—':>9}  {spy_oos_m.get('sharpe', 0):>10.3f} "
          f"{spy_oos_m.get('max_dd_pct', 0):>9.1f}% {spy_oos_m.get('cumul', 0):>9.3f}×")

    h181_oos_pure = results[-1]  # pure H181
    h188_oos_pure = results[0]   # pure H188

    print(f"\n  Best blend by OOS Sharpe: {best_label} (Sharpe={best_oos_sharpe:.3f})")
    print(f"  H181 pure OOS Sharpe:     {h181_oos_pure['oos_sharpe']:.3f} (baseline to beat)")
    print(f"  H188 pure OOS Sharpe:     {h188_oos_pure['oos_sharpe']:.3f}")
    print(f"  Corr(H188, H181) OOS:     {corr_oos:.3f}")

    # Confirm criteria: any blend beats H181 pure AND has lower MaxDD
    best_r = max(results, key=lambda x: x["oos_sharpe"])
    confirms = (best_r["oos_sharpe"] > h181_oos_pure["oos_sharpe"] and
                best_r["oos_maxdd"] > h181_oos_pure["oos_maxdd"])

    if confirms:
        verdict = f"CONFIRMED — blend {best_r['label']} improves both Sharpe and MaxDD vs H181 alone"
    elif best_r["oos_sharpe"] > h181_oos_pure["oos_sharpe"]:
        verdict = f"PARTIAL — blend {best_r['label']} improves Sharpe but not MaxDD"
    elif best_r["oos_sharpe"] > h188_oos_pure["oos_sharpe"]:
        verdict = f"PARTIAL — some blends improve over H188 but not H181 baseline"
    else:
        verdict = "NOT CONFIRMED — H181 pure dominates all blends"

    print(f"\n  VERDICT: {verdict}")

    # Key insight
    overlap_note = ("NOTE: H188 and H181 select OPPOSITE tickers (top vs bottom of momentum), "
                    f"but Corr={corr_oos:.3f} is positive (both long-only, share market beta).")
    print(f"\n  {overlap_note}")

    # Stock holding overlap analysis
    print("\n  Checking holding overlap (do they hold the same stocks?)…")
    monthly_px = prices.resample("ME").last()
    overlap_months = []
    for dt in h188_oos_a.index[-12:]:
        # Get H188 picks
        hist = prices[prices.index <= dt]
        if len(hist) < 253:
            continue
        prox = (hist.iloc[-1] / hist.tail(252).max()).dropna()
        h188_picks = set(prox.nlargest(QUINTILE_N).index)

        # Get H181 picks from prior month
        if dt not in monthly_px.index:
            continue
        idx_dt = monthly_px.index.get_loc(dt)
        if idx_dt < 2:
            continue
        prior_ret = {}
        for t in UNIVERSE:
            p0 = monthly_px.iloc[idx_dt-2].get(t)
            p1 = monthly_px.iloc[idx_dt-1].get(t)
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                prior_ret[t] = (p1 - p0) / p0
        if len(prior_ret) >= QUINTILE_N * 2:
            adj_rev = industry_adjusted_reversal(pd.Series(prior_ret))
            h181_picks = set(adj_rev.sort_values().head(QUINTILE_N).index)
            overlap = len(h188_picks & h181_picks)
            overlap_months.append(overlap)

    if overlap_months:
        avg_overlap = np.mean(overlap_months)
        print(f"  Avg stocks shared between H188 and H181 (last 12m): {avg_overlap:.1f} / {QUINTILE_N}")
        print(f"  (0 = fully distinct baskets, {QUINTILE_N} = identical baskets)")

    # Save results
    lines = [
        "H190 — H188 (52wk Momentum) + H181 (Industry Reversal) Blend",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(available)}/30 large-cap S&P 500 stocks (same for both strategies)",
        f"H188: long top-{QUINTILE_N} by 52wk high proximity (OOS Sharpe 0.774)",
        f"H181: long bottom-{QUINTILE_N} by industry-adjusted reversal (OOS Sharpe 1.138)",
        f"IS: 2013–2020  |  OOS: 2021–2026",
        f"Corr(H188, H181) IS={corr_is:.3f}  OOS={corr_oos:.3f}",
        f"Avg portfolio overlap (last 12m): {np.mean(overlap_months) if overlap_months else 'N/A':.1f} stocks",
        "",
    ]
    lines.append(f"  {'Label':<14} {'IS Sharpe':>9} {'IS MaxDD':>9} {'OOS Sharpe':>10} {'OOS MaxDD':>9} {'OOS Cumul':>9}")
    lines.append("  " + "-" * 64)
    for r in results:
        lines.append(f"  {r['label']:<14} {r['is_sharpe']:>9.3f} {r['is_maxdd']:>9.1f}%"
                     f" {r['oos_sharpe']:>10.3f} {r['oos_maxdd']:>9.1f}% {r['oos_cumul']:>9.3f}×")
    lines += [
        "",
        f"SPY OOS: Sharpe={spy_oos_m.get('sharpe', 0):.3f}  Cumul={spy_oos_m.get('cumul', 0):.3f}×",
        "",
        f"VERDICT: {verdict}",
        "",
        overlap_note,
    ]

    result_path = RESULT_DIR / "h190_h188_h181_blend.txt"
    result_path.write_text("\n".join(lines))
    print(f"\n  Results saved: {result_path.name}")
    print("=" * 68)


if __name__ == "__main__":
    main()
