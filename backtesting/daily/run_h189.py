"""
H189 — H026 + H181 Monthly Portfolio Blend
============================================
Portfolio construction test: does blending H026 (ETF sector rotation, Sharpe 3.007)
with H181 (industry-adjusted reversal, Sharpe 1.138) improve risk-adjusted returns?

H026 and H181 characteristics:
  - H026: OOS Sharpe 3.007, MaxDD -9.6%, 382× cumulative, 0 neg years (ETFs)
  - H181: OOS Sharpe 1.138, MaxDD -18.4%, 3.23× cumulative, 1 neg year (stocks)
  - Corr(H181, H026) OOS: 0.293 — low correlation → diversification potential

Hypothesis: A weighted blend of H026 and H181 monthly returns achieves:
  - Higher Sharpe than H181 alone (H026 Sharpe lifts the blend)
  - Lower MaxDD than H026 alone (H181's low correlation smooths equity curve)
  - Both OOS and IS improvement consistent

Blend weights tested: H026/(H026+H181) = 90/10, 80/20, 70/30, 60/40, 50/50

Confirm criteria (for any blend to beat pure H026):
  - OOS Sharpe ≥ 3.007 (must match or beat H026 solo)
  - OOS MaxDD > -9.6% (less severe drawdown)
  OR
  - MaxDD substantially improved while Sharpe ≥ 2.5 (risk-reduction case)

Note: This tests monthly return mixing, NOT a simultaneous position in both strategies.
In practice, H181 runs in a separate Alpaca account (separate capital allocation).
The blend test answers: "Is H181 worth capital allocation alongside H026?"
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

# ── H026 universe (H149 production configuration) ────────────────────────────
H026_ASSETS = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO",
]
TSMOM_THRESHOLD = 0.05   # +5% 12m return required (H139 confirmed optimal)

# ── H181 universe ────────────────────────────────────────────────────────────
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
H181_UNIVERSE = list(UNIVERSE_SECTORS.keys())
H181_N        = 6

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")


# ── H026 monthly return computation ─────────────────────────────────────────

def load_h026_prices() -> pd.DataFrame:
    cache = CACHE_DIR / f"h189_h026_prices_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    print("  Downloading H026 ETF prices (25 tickers)…")
    raw = yf.download(H026_ASSETS, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices.to_parquet(cache)
    return prices.dropna(how="all", axis=0)


def h026_signal(monthly_px: pd.DataFrame, monthly_rt: pd.DataFrame, i: int) -> str:
    """
    Compute H026 signal at month i (same as production h112_monthly.py).
    Returns top-1 ETF by rank ensemble, or BIL if TSMOM filter eliminates all.
    """
    ranking_assets = [a for a in H026_ASSETS if a != "BIL"]

    mom_12 = (monthly_px.iloc[i] / monthly_px.iloc[i-12] - 1)
    mom_6  = (monthly_px.iloc[i] / monthly_px.iloc[i-6]  - 1)
    mom_3  = (monthly_px.iloc[i] / monthly_px.iloc[i-3]  - 1)
    vol_6  = monthly_rt.rolling(6).std().iloc[i] * np.sqrt(12)

    passing = [t for t in ranking_assets
               if t in mom_12.index and pd.notna(mom_12.get(t)) and mom_12[t] > TSMOM_THRESHOLD]

    if not passing:
        return "BIL"

    score = (mom_12.reindex(passing).rank() +
             mom_6.reindex(passing).rank()  +
             mom_3.reindex(passing).rank()  +
             vol_6.reindex(passing).rank(ascending=False))
    return str(score.idxmax())


def run_h026_backtest(prices: pd.DataFrame) -> pd.Series:
    """Compute H026 monthly returns. Returns pd.Series indexed by month-end date."""
    monthly_px = prices.resample("ME").last()
    monthly_rt = prices.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    rets = []
    dates = []
    for i in range(13, len(monthly_px)):
        top = h026_signal(monthly_px, monthly_rt, i)
        if top in monthly_px.columns:
            ret = float(monthly_rt.iloc[i][top])
            rets.append(ret)
            dates.append(monthly_px.index[i])

    return pd.Series(rets, index=dates, name="h026")


# ── H181 monthly return computation ─────────────────────────────────────────

def load_h181_prices() -> pd.DataFrame:
    cache = CACHE_DIR / f"h189_h181_prices_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    print("  Downloading H181 stock prices (30 tickers)…")
    raw = yf.download(H181_UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices.to_parquet(cache)
    return prices.dropna(how="all", axis=0)


def industry_adjusted_reversal(monthly_returns: pd.Series) -> pd.Series:
    sectors = pd.Series(UNIVERSE_SECTORS)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


def run_h181_backtest(prices: pd.DataFrame) -> pd.Series:
    """Compute H181 monthly returns. Returns pd.Series indexed by month-end date."""
    monthly_px = prices.resample("ME").last()
    months = monthly_px.index
    rets, dates = [], []

    for i in range(2, len(months)):
        prior_close  = monthly_px.iloc[i - 2]
        signal_close = monthly_px.iloc[i - 1]
        hold_close   = monthly_px.iloc[i]

        prior_returns = {}
        current_returns = {}
        for t in H181_UNIVERSE:
            if t in prior_close.index and t in signal_close.index:
                p0, p1, p2 = prior_close.get(t), signal_close.get(t), hold_close.get(t, np.nan)
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    prior_returns[t] = (p1 - p0) / p0
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    current_returns[t] = (p2 - p1) / p1

        if len(prior_returns) < H181_N * 2:
            continue

        prior_ret_series = pd.Series(prior_returns)
        adj_rev = industry_adjusted_reversal(prior_ret_series)
        long_tickers = adj_rev.sort_values().head(H181_N).index.tolist()
        port_rets = [current_returns[t] for t in long_tickers if t in current_returns]
        if not port_rets:
            continue
        rets.append(np.mean(port_rets))
        dates.append(months[i])

    return pd.Series(rets, index=dates, name="h181")


# ── Performance metrics ───────────────────────────────────────────────────────

def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label, "sharpe": 0, "max_dd_pct": 0, "cumul": 1}
    cum    = (1 + returns).cumprod()
    n_yrs  = len(returns) / 12.0
    cagr   = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = (returns.mean() / returns.std() * np.sqrt(12)) if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1
    return {
        "label":      label,
        "n_months":   len(returns),
        "cumul":      round(float(cum.iloc[-1]), 4),
        "cagr_pct":   round(cagr * 100, 2),
        "sharpe":     round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(returns.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum()),
    }


# ── Blend test ────────────────────────────────────────────────────────────────

BLEND_WEIGHTS = [
    ("100% H026 + 0% H181",  1.00, 0.00),
    ("90% H026 + 10% H181",  0.90, 0.10),
    ("80% H026 + 20% H181",  0.80, 0.20),
    ("70% H026 + 30% H181",  0.70, 0.30),
    ("60% H026 + 40% H181",  0.60, 0.40),
    ("50% H026 + 50% H181",  0.50, 0.50),
    ("0% H026 + 100% H181",  0.00, 1.00),
]


def main():
    print("=" * 68)
    print("  H189 — H026 + H181 Monthly Blend Portfolio Construction")
    print("=" * 68)

    print(f"\n[1/5] Loading H026 ETF prices ({len(H026_ASSETS)} tickers)…")
    h026_prices = load_h026_prices()
    h026_avail  = [t for t in H026_ASSETS if t in h026_prices.columns]
    h026_prices = h026_prices[h026_avail].dropna(how="all")
    print(f"  H026 available: {len(h026_avail)}/{len(H026_ASSETS)} tickers")

    print(f"\n[2/5] Loading H181 stock prices ({len(H181_UNIVERSE)} tickers)…")
    h181_prices = load_h181_prices()
    h181_avail  = [t for t in H181_UNIVERSE if t in h181_prices.columns]
    h181_prices = h181_prices[h181_avail].dropna(how="all")
    print(f"  H181 available: {len(h181_avail)}/{len(H181_UNIVERSE)} tickers")

    print("\n[3/5] Running H026 and H181 backtests (2013–2026)…")
    h026_ret = run_h026_backtest(h026_prices)
    h181_ret = run_h181_backtest(h181_prices)

    # Align to common dates
    common_idx = h026_ret.index.intersection(h181_ret.index)
    h026_aligned = h026_ret[common_idx]
    h181_aligned = h181_ret[common_idx]

    print(f"  H026 months: {len(h026_ret)}, H181 months: {len(h181_ret)}, common: {len(common_idx)}")
    print(f"  Common period: {common_idx[0].date()} → {common_idx[-1].date()}")
    print(f"  Corr(H026, H181) full period: {h026_aligned.corr(h181_aligned):.3f}")

    # SPY benchmark
    spy_cache = CACHE_DIR / f"h181_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cache.exists():
        spy_close = pd.read_parquet(spy_cache)["close"]
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_close = raw["Close"].resample("ME").last().dropna()
    spy_ret = spy_close.pct_change().dropna()

    print("\n[4/5] Computing blend metrics for IS and OOS…")
    print(f"\n  {'Blend':<30} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'IS MaxDD':>10} {'OOS MaxDD':>10} {'OOS Cumul':>10} {'OOS NegYrs':>10}")
    print("  " + "-" * 92)

    results = []
    for label, w026, w181 in BLEND_WEIGHTS:
        blend_full = w026 * h026_aligned + w181 * h181_aligned
        is_blend   = blend_full[(blend_full.index >= IS_START)  & (blend_full.index <= IS_END)]
        oos_blend  = blend_full[(blend_full.index >= OOS_START) & (blend_full.index <= OOS_END)]

        is_m  = calc_metrics(is_blend,  label + " IS")
        oos_m = calc_metrics(oos_blend, label + " OOS")

        print(f"  {label:<30} {is_m['sharpe']:>10.3f} {oos_m['sharpe']:>10.3f} "
              f"{is_m['max_dd_pct']:>10.1f}% {oos_m['max_dd_pct']:>10.1f}% "
              f"{oos_m['cumul']:>10.2f}× {oos_m['neg_years']:>10}")

        results.append({
            "label":       label,
            "w026":        w026,
            "w181":        w181,
            "is_sharpe":   is_m["sharpe"],
            "oos_sharpe":  oos_m["sharpe"],
            "is_maxdd":    is_m["max_dd_pct"],
            "oos_maxdd":   oos_m["max_dd_pct"],
            "oos_cumul":   oos_m["cumul"],
            "oos_neg_yrs": oos_m["neg_years"],
            "oos_cagr":    oos_m["cagr_pct"],
        })

    # SPY benchmark
    spy_is  = calc_metrics(spy_ret[(spy_ret.index >= IS_START)  & (spy_ret.index <= IS_END)], "SPY IS")
    spy_oos = calc_metrics(spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)],"SPY OOS")
    print(f"  {'SPY benchmark':<30} {spy_is['sharpe']:>10.3f} {spy_oos['sharpe']:>10.3f} "
          f"{spy_is['max_dd_pct']:>10.1f}% {spy_oos['max_dd_pct']:>10.1f}% "
          f"{spy_oos['cumul']:>10.2f}× {spy_oos['neg_years']:>10}")

    print("\n[5/5] Interpretation…")
    # Best OOS Sharpe
    best_sharpe = max(results, key=lambda r: r["oos_sharpe"])
    best_dd     = max(results, key=lambda r: -r["oos_maxdd"])  # least negative
    pure_h026   = [r for r in results if r["w026"] == 1.0][0]

    print(f"  H026 solo OOS:  Sharpe={pure_h026['oos_sharpe']:.3f}, MaxDD={pure_h026['oos_maxdd']:.1f}%, Cumul={pure_h026['oos_cumul']:.2f}×")
    print(f"  Best Sharpe:    {best_sharpe['label']} → Sharpe={best_sharpe['oos_sharpe']:.3f}")
    print(f"  Best MaxDD:     {best_dd['label']} → MaxDD={best_dd['oos_maxdd']:.1f}%")

    # Does any blend beat pure H026 on Sharpe?
    better_sharpe = [r for r in results if r["oos_sharpe"] > pure_h026["oos_sharpe"] and r["w026"] < 1.0]
    better_dd     = [r for r in results if r["oos_maxdd"]  > pure_h026["oos_maxdd"]  and r["w026"] < 1.0]

    if better_sharpe:
        print(f"\n  ✓ Blends with higher OOS Sharpe than pure H026: {[r['label'] for r in better_sharpe]}")
    else:
        print(f"\n  ✗ No blend improves OOS Sharpe above pure H026 ({pure_h026['oos_sharpe']:.3f})")

    if better_dd:
        print(f"  ✓ Blends with better MaxDD than pure H026: {[r['label'] for r in better_dd]}")
    else:
        print(f"  ✗ No blend improves MaxDD above pure H026 ({pure_h026['oos_maxdd']:.1f}%)")

    # Verdict
    confirmed_blend = better_sharpe or (better_dd and any(r["oos_sharpe"] >= 2.5 for r in better_dd))
    verdict = "CONFIRMED (blend adds value)" if confirmed_blend else "NOT CONFIRMED (pure H026 optimal)"
    print(f"\n  VERDICT: {verdict}")

    # Correlation in OOS
    h026_oos = h026_aligned[(h026_aligned.index >= OOS_START) & (h026_aligned.index <= OOS_END)]
    h181_oos = h181_aligned[(h181_aligned.index >= OOS_START) & (h181_aligned.index <= OOS_END)]
    corr_oos = h026_oos.corr(h181_oos)
    print(f"\n  Corr(H026, H181) OOS: {corr_oos:.3f}")
    print(f"  Note: Sharpe of 50/50 blend = (w*SR1 + w*SR2 + 2*w²*ρ*SR1*SR2)^(1/2)")
    print(f"  At ρ={corr_oos:.2f}: expected blend Sharpe ≈ {0.5*pure_h026['oos_sharpe'] + 0.5*results[-1]['oos_sharpe']:.2f} (naive) vs actual shown above")

    out_lines = [
        "H189 — H026 + H181 Monthly Blend Portfolio Construction",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "Strategy descriptions:",
        "  H026: H149 ETF sector rotation, 25 ETFs, TSMOM filter >5%, top-1 monthly",
        "  H181: Industry-adjusted reversal, 30 stocks, long bottom-6, monthly",
        "",
        f"Common period: {common_idx[0].date()} → {common_idx[-1].date()}",
        f"Corr(H026, H181) OOS: {corr_oos:.3f}",
        "",
    ]
    for r in results:
        out_lines.append(
            f"{r['label']:<30}  IS_Sharpe={r['is_sharpe']:.3f}  OOS_Sharpe={r['oos_sharpe']:.3f}  "
            f"IS_MaxDD={r['is_maxdd']:.1f}%  OOS_MaxDD={r['oos_maxdd']:.1f}%  "
            f"OOS_Cumul={r['oos_cumul']:.2f}x  OOS_CAGR={r['oos_cagr']:.1f}%"
        )
    out_lines += ["", f"VERDICT: {verdict}"]

    result_path = RESULT_DIR / "h189_h026_h181_blend.txt"
    result_path.write_text("\n".join(out_lines))
    print(f"\n  Results saved: {result_path.name}")
    print("=" * 68)


if __name__ == "__main__":
    main()
