"""
H191 — Low-Volatility Anomaly: 30-Stock Universe
==================================================
Tests the low-volatility anomaly (Blitz & Vliet 2007, Frazzini & Pedersen 2014)
on the same 30-stock large-cap S&P 500 universe used by H181/H188/H190.

Background: Low-vol stocks empirically earn higher risk-adjusted returns than
high-vol stocks — a direct contradiction of CAPM. Strongest on large-cap
US stocks over long horizons (Sharpe ~0.72–0.84, Blitz & Vliet 2007).

H150 (CONFIRMED) already tested low-vol on 11 sector ETFs:
  - Best variant: 50% vol + 50% momentum, OOS Sharpe 2.645
  - Corr with H026 production: very low (0.108–0.230)
H191 tests whether the same signal on individual large-cap stocks is:
  (a) itself useful as a standalone monthly strategy
  (b) low-correlation with H181 reversal — if so, could be added to satellite bucket

Signal variants tested:
  A: 1-year daily vol (252d rolling std × √252) — long bottom-6 (lowest vol)
  B: 3-year weekly vol (156-week rolling std × √52) — Blitz & Vliet original
  C: Hybrid 50/50 vol+momentum (12-1m) — replicating H150's best variant
  D: Sector-neutral 1yr vol (rank within GICS sector, long bottom-6)

Universe: 30 large-cap S&P 500 stocks, same as H181/H188
IS: 2013–2020, OOS: 2021–2026

Confirm: OOS Sharpe > 0.5, OOS cumul > 1.3×
Cross-check: Corr with H181, H188 OOS — looking for low correlation
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
QUINTILE_N = 6  # long bottom-6 (lowest vol)
ALT_START  = pd.Timestamp("2013-01-01")  # AltOOS = full 2013-2026


def load_prices() -> pd.DataFrame:
    cache = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading daily prices from H188 cache…")
        return pd.read_parquet(cache)
    print(f"  Downloading {len(UNIVERSE)} tickers from yfinance…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices.dropna(how="all", axis=0).to_parquet(cache)
    return pd.read_parquet(cache)


def run_vol_strategy(
    daily_prices: pd.DataFrame,
    variant: str = "A",
    label: str = "",
    n_long: int = QUINTILE_N,
) -> pd.Series:
    """
    Run monthly low-vol strategy. Returns monthly return series.

    variant A: 252-day daily vol
    variant B: 156-week (3yr) weekly vol
    variant C: 50/50 vol+12m momentum hybrid
    variant D: sector-neutral 252d vol (rank within GICS sector)
    """
    monthly_px = daily_prices.resample("ME").last()
    month_ends = monthly_px.index

    rets, dates = [], []

    for i, hold_date in enumerate(month_ends[1:], 1):
        rebal_date = month_ends[i - 1]

        hist = daily_prices[daily_prices.index <= rebal_date]

        # ── Signal computation ────────────────────────────────────────────
        if variant in ("A", "C", "D"):
            # 1-year daily vol
            if len(hist) < 253:
                continue
            daily_rets = hist.pct_change().tail(253)
            vol_1yr = daily_rets.std() * np.sqrt(252)
            vol_signal = vol_1yr.dropna()

        if variant == "B":
            # 3-year weekly vol (Blitz & Vliet original)
            weekly = hist.resample("W-FRI").last()
            weekly_rets = weekly.pct_change()
            if len(weekly_rets) < 157:
                continue
            vol_3yr = weekly_rets.rolling(156).std().iloc[-1] * np.sqrt(52)
            vol_signal = vol_3yr.dropna()

        if variant == "C":
            # 50/50 hybrid: combine 1yr daily vol rank + 12-1m momentum rank
            if len(hist) < 253 or len(monthly_px[:i]) < 13:
                continue
            mom_12 = (monthly_px.iloc[i-1] / monthly_px.iloc[max(0, i-13)] - 1).dropna()
            mom_1  = (monthly_px.iloc[i-1] / monthly_px.iloc[i-2] - 1).dropna() if i >= 2 else pd.Series()
            mom_12_1 = (mom_12 - mom_1) if len(mom_1) > 0 else mom_12
            common = vol_signal.index.intersection(mom_12_1.index)
            vol_s   = vol_signal[common]
            mom_s   = mom_12_1[common]
            # Low vol (low rank) good, high momentum (high rank) good
            # Combined score: low rank in vol = good, high rank in momentum = good
            vol_rank = vol_s.rank()         # lower vol → lower rank (want low)
            mom_rank = mom_s.rank()         # higher mom → higher rank (want high)
            n = len(common)
            # Invert vol rank: n+1-rank (so low vol → high combined score)
            combined = (n + 1 - vol_rank) * 0.5 + mom_rank * 0.5
            vol_signal = -combined  # we'll sort ascending → bottom-6 = highest combined

        if variant == "D":
            # Sector-neutral: rank within GICS sector
            sectors = pd.Series(UNIVERSE_SECTORS)
            common = vol_signal.index.intersection(sectors.index)
            df = pd.DataFrame({"vol": vol_signal[common], "sector": sectors[common]})
            df["rank_in_sector"] = df.groupby("sector")["vol"].rank(ascending=True)
            vol_signal = df["rank_in_sector"]  # lower within-sector vol rank = better

        if len(vol_signal) < n_long * 2:
            continue

        # Long bottom-N (lowest vol signal value)
        long_tickers = vol_signal.nsmallest(n_long).index.tolist()

        # Compute this month's returns
        port_rets = []
        for t in long_tickers:
            if t in monthly_px.columns:
                p1 = monthly_px.iloc[i - 1].get(t, np.nan)
                p2 = monthly_px.iloc[i].get(t, np.nan)
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    port_rets.append((p2 - p1) / p1)
        if port_rets:
            rets.append(np.mean(port_rets))
            dates.append(hold_date)

    return pd.Series(rets, index=dates, name=label)


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label, "cumul": 0, "sharpe": 0}
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
    print("  H191 — Low-Volatility Anomaly: 30-Stock Large-Cap Universe")
    print("  Blitz & Vliet (2007) + Frazzini & Pedersen (2014)")
    print("=" * 68)

    print(f"\n[1/3] Loading prices…")
    prices = load_prices()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 300]
    print(f"  Available: {len(available)}/{len(UNIVERSE)}, "
          f"{prices.index[0].date()} → {prices.index[-1].date()}")
    prices = prices[available]

    # SPY
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
    spy_oos = calc_metrics(
        spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)], "SPY OOS"
    )
    spy_alt = calc_metrics(
        spy_ret[(spy_ret.index >= ALT_START) & (spy_ret.index <= OOS_END)], "SPY Alt"
    )

    print(f"\n[2/3] Running 4 low-vol variants…")
    variants = [("A", "1yr Daily Vol"), ("B", "3yr Weekly Vol (B&V)"),
                ("C", "Hybrid 50/50 Mom"), ("D", "Sector-Neutral")]

    variant_results = {}
    for v, lbl in variants:
        print(f"  Running variant {v}: {lbl}…")
        ret_series = run_vol_strategy(prices, variant=v, label=lbl)
        is_m   = calc_metrics(ret_series[(ret_series.index >= IS_START)  & (ret_series.index <= IS_END)],  f"IS {lbl}")
        oos_m  = calc_metrics(ret_series[(ret_series.index >= OOS_START) & (ret_series.index <= OOS_END)], f"OOS {lbl}")
        alt_m  = calc_metrics(ret_series[(ret_series.index >= ALT_START) & (ret_series.index <= OOS_END)], f"Alt {lbl}")
        variant_results[v] = {"series": ret_series, "is": is_m, "oos": oos_m, "alt": alt_m, "label": lbl}

    print(f"\n[3/3] Results…")
    print(f"\n  {'Variant':<20} {'IS Sh':>6} {'IS DD':>7} {'OOS Sh':>7} {'OOS DD':>7} {'OOS Cum':>8} {'Alt Sh':>7}")
    print("  " + "-" * 65)
    for v, lbl in variants:
        r = variant_results[v]
        print(f"  {lbl:<20} {r['is'].get('sharpe', 0):>6.3f} {r['is'].get('max_dd_pct', 0):>7.1f}%"
              f" {r['oos'].get('sharpe', 0):>7.3f} {r['oos'].get('max_dd_pct', 0):>7.1f}%"
              f" {r['oos'].get('cumul', 0):>8.3f}× {r['alt'].get('sharpe', 0):>7.3f}")
    print(f"  {'SPY':<20} {'-':>6} {'-':>7}"
          f" {spy_oos.get('sharpe', 0):>7.3f} {spy_oos.get('max_dd_pct', 0):>7.1f}%"
          f" {spy_oos.get('cumul', 0):>8.3f}× {spy_alt.get('sharpe', 0):>7.3f}")

    # Correlation with H181 and H188 OOS
    print(f"\n  Correlations with H181/H188 OOS:")

    h181_cache = CACHE_DIR / "h188_h181_oos_ret.parquet"
    h181_oos_ret = None
    h188_oos_ret = None
    if h181_cache.exists():
        h181_oos_ret = pd.read_parquet(h181_cache)["ret"]

    # Rebuild H188 OOS returns (port_ret column from run_backtest DataFrame)
    try:
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(
            "run_h188", Path(__file__).parent / "run_h188.py")
        h188_mod = importlib.util.load_module_from_spec(spec)
        # Suppress re-downloading by using cached prices
        spec.loader.exec_module(h188_mod)
        h188_full_df = h188_mod.run_backtest(prices)
        h188_full_s  = h188_full_df["port_ret"]
        h188_oos_ret = h188_full_s[(h188_full_s.index >= OOS_START) & (h188_full_s.index <= OOS_END)]
    except Exception as e:
        print(f"  (H188 corr skipped: {e})")
        h188_oos_ret = None

    for v, lbl in variants:
        r = variant_results[v]
        s_oos = r["series"][(r["series"].index >= OOS_START) & (r["series"].index <= OOS_END)]
        if h181_oos_ret is not None:
            a, b = s_oos.align(h181_oos_ret, join="inner")
            c181 = float(a.corr(b)) if len(a) > 5 else float("nan")
        else:
            c181 = float("nan")
        if h188_oos_ret is not None:
            a, b = s_oos.align(h188_oos_ret, join="inner")
            c188 = float(a.corr(b)) if len(a) > 5 else float("nan")
        else:
            c188 = float("nan")
        print(f"  {lbl:<22}: Corr(H181)={c181:.3f}  Corr(H188)={c188:.3f}")

    # Best variant
    best_v = max(variant_results, key=lambda v: variant_results[v]["oos"].get("sharpe", 0))
    best = variant_results[best_v]
    oos_sh = best["oos"].get("sharpe", 0)
    oos_cumul = best["oos"].get("cumul", 0)
    confirmed = oos_sh > 0.5 and oos_cumul > 1.3

    print(f"\n  Best variant: {best['label']} (OOS Sharpe={oos_sh:.3f}, cumul={oos_cumul:.3f}×)")
    verdict = ("CONFIRMED" if confirmed else
               "PARTIAL" if oos_sh > 0.3 else "NOT CONFIRMED")
    print(f"  VERDICT: {verdict}")

    # Save results
    lines = [
        "H191 — Low-Volatility Anomaly: 30-Stock Large-Cap Universe",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(available)}/30 large-cap S&P 500 stocks",
        f"IS: 2013–2020  |  OOS: 2021–2026  |  AltOOS: 2013–2026",
        "",
        f"  {'Variant':<22} {'IS Sh':>6} {'IS DD':>7} {'OOS Sh':>7} {'OOS DD':>7} {'OOS×':>6} {'AltSh':>7}",
        "  " + "-" * 65,
    ]
    for v, lbl in variants:
        r = variant_results[v]
        lines.append(
            f"  {lbl:<22} {r['is'].get('sharpe', 0):>6.3f} {r['is'].get('max_dd_pct', 0):>7.1f}%"
            f" {r['oos'].get('sharpe', 0):>7.3f} {r['oos'].get('max_dd_pct', 0):>7.1f}%"
            f" {r['oos'].get('cumul', 0):>6.3f}× {r['alt'].get('sharpe', 0):>7.3f}"
        )
    lines += [
        f"  {'SPY':<22} {'—':>6} {'—':>7} {spy_oos.get('sharpe', 0):>7.3f}"
        f" {spy_oos.get('max_dd_pct', 0):>7.1f}% {spy_oos.get('cumul', 0):>6.3f}× {spy_alt.get('sharpe', 0):>7.3f}",
        "",
        f"Best variant: {best['label']} (OOS Sharpe={oos_sh:.3f}, cumul={oos_cumul:.3f}×)",
        f"VERDICT: {verdict}",
    ]

    out = RESULT_DIR / "h191_low_vol_30stock.txt"
    out.write_text("\n".join(lines))
    print(f"\n  Results saved: {out.name}")
    print("=" * 68)


if __name__ == "__main__":
    main()
