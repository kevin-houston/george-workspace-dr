"""
H284 REVISED — FCF/P Stock Screener (Free Cash Flow Yield via FMP)
===================================================================

Hypothesis:
  Yartseva (2025) "What Makes a Multibagger?" finds FCF/P (free cash flow yield)
  is the #1 predictor of multibagger outperformance.

  Design:
    - Universe: 50 S&P 500 large-cap stocks (diverse sectors, listed before 2010)
    - Signal: freeCashFlowYield from FMP stable/key-metrics (pre-computed annual)
    - Rebalance: annually (end of Q1 each year)
    - Data lag: use fiscal-year data ending on or before Dec 31 of prior year
      (ensures 3+ month reporting lag — most Dec FY 10-Ks filed by March)
    - Portfolio: long top-10 by FCF yield, equal-weight

  Data: FMP stable/key-metrics → freeCashFlowYield, 5 years annual history
  IS:  holding periods April 2022 – March 2024 (signals from FY2021, FY2022)
  OOS: holding periods April 2024 – present    (signals from FY2023, FY2024)

  Gate: OOS Sharpe ≥ 0.8, walkforward ratio ≥ 0.45

Academic basis:
  - Yartseva 2025: FCF/P #1 multibagger predictor
  - COWZ ETF: mechanical FCF/P top-100 Russell 1000 screen (inception 2016)
"""

import os
import json
import time
import warnings
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

FMP_KEY  = os.environ.get("FMP_API_KEY", "")
FMP_BASE = "https://financialmodelingprep.com/stable"

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2019-01-01"
FULL_END   = "2026-06-01"

# Annual rebalance end of Q1; signal = latest FY ending ≤ Dec 31 of prior year
# IS:  April 2022 – March 2024 (2 full holding years)
# OOS: April 2024 – present    (~1.5 years)
FCF_IS_START  = "2022-04-01"
FCF_IS_END    = "2024-03-31"
FCF_OOS_START = "2024-04-01"

UNIVERSE = [
    # Tech
    "AAPL","MSFT","GOOGL","AMZN","META","INTC","CSCO","QCOM","TXN","ORCL",
    # Healthcare
    "JNJ","UNH","PFE","ABBV","MRK","LLY","BMY","AMGN","MDT","ABT",
    # Consumer Disc
    "HD","LOW","MCD","NKE","SBUX","TGT","CMG","YUM","DHI","PHM",
    # Consumer Staples
    "WMT","PG","KO","PEP","PM","MO","CL","GIS","SYY","CHD",
    # Financials
    "JPM","BAC","WFC","GS","MS","BLK","AXP","USB","PNC","TFC",
]

N_LONG = 10
MAX_SIGNAL_AGE_MONTHS = 18  # Skip if most recent FY data is older than 18 months


def fetch_fmp_annual_fcf_yield(ticker):
    """Fetch annual freeCashFlowYield from FMP stable/key-metrics (5yr max, free tier)."""
    cache_path = CACHE_DIR / f"h284v2_fcf_{ticker}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            raw = json.load(f)
        return {pd.Timestamp(k): v for k, v in raw.items()}

    url = f"{FMP_BASE}/key-metrics?symbol={ticker}&limit=5&apikey={FMP_KEY}"
    try:
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return {}
        rows = resp.json()
        if not rows or not isinstance(rows, list):
            return {}

        result = {}
        for row in rows:
            date_str = row.get("date", "")
            val = row.get("freeCashFlowYield")
            if date_str and val is not None:
                try:
                    fval = float(val)
                    if np.isfinite(fval):
                        result[date_str] = fval
                except (TypeError, ValueError):
                    pass

        with open(cache_path, "w") as f:
            json.dump(result, f)
        time.sleep(0.12)  # polite rate limit
        return {pd.Timestamp(k): v for k, v in result.items()}
    except Exception:
        return {}


def fetch_monthly_returns_series(ticker):
    """Monthly return series from yfinance with disk cache."""
    cache_path = CACHE_DIR / f"h284_monthly_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze().rename(ticker)

    raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    monthly = close.resample("ME").last().pct_change().rename(ticker)
    monthly.to_frame().to_parquet(cache_path)
    return monthly


def stats(r, freq="monthly"):
    r = r.dropna()
    if len(r) < 4:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    periods = 12 if freq == "monthly" else 4
    eq = (1 + r).cumprod()
    n_yr = len(r) / periods
    if n_yr <= 0:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std(ddof=1)) * np.sqrt(periods)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    if freq == "monthly":
        annual = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    else:
        annual = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((annual < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "n_months": len(r), "neg_years": neg_years}


def corr_series(r1, r2):
    idx = r1.dropna().index.intersection(r2.dropna().index)
    if len(idx) < 6:
        return float("nan")
    return round(float(r1.reindex(idx).corr(r2.reindex(idx))), 4)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("H284 REVISED — FCF/P Stock Screener (Free Cash Flow Yield via FMP)")
print("=" * 80)

# ── PART 1: ETF-based FCF factor cross-check (COWZ/CALF, 2016+) ──────────────
print("\n[1] ETF-based FCF factor cross-check (COWZ/CALF vs SPY) …")
etf_monthly = {}
for t in ["COWZ", "CALF", "SPY", "BIL"]:
    raw = yf.download(t, start="2016-01-01", end=FULL_END, auto_adjust=True, progress=False)
    if raw.empty:
        continue
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(t, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    etf_monthly[t] = close.resample("ME").last().pct_change().dropna().rename(t)

spy_monthly_full = etf_monthly.get("SPY", pd.Series(dtype=float))

for t in ["COWZ", "CALF"]:
    if t not in etf_monthly:
        continue
    r = etf_monthly[t]
    is_r  = r[(r.index >= "2017-01-01") & (r.index <= "2019-12-31")]
    oos_r = r[r.index >= "2020-01-01"]
    s_is  = stats(is_r)
    s_oos = stats(oos_r)
    spy_oos = stats(spy_monthly_full[spy_monthly_full.index >= "2020-01-01"])
    c = corr_series(oos_r, spy_monthly_full.reindex(oos_r.index))
    print(f"  {t}: IS(2017-19) Sharpe={s_is['sharpe']:.3f}  OOS(2020+) Sharpe={s_oos['sharpe']:.3f}"
          f"  MaxDD={s_oos['max_drawdown']*100:.1f}%  CAGR={s_oos['cagr']*100:.1f}%  Corr(SPY)={c:.3f}")
    print(f"       SPY OOS Sharpe={spy_oos['sharpe']:.3f}")

# ── PART 2: Fetch annual FCF yield from FMP key-metrics ───────────────────────
print(f"\n[2] Fetching annual FCF yield from FMP stable/key-metrics …")
if not FMP_KEY:
    print("  ERROR: FMP_API_KEY not set — cannot fetch fundamental data")
    import sys; sys.exit(1)

fcf_annual = {}  # ticker → {fiscal_year_end_date: freeCashFlowYield}
for t in UNIVERSE:
    yield_dict = fetch_fmp_annual_fcf_yield(t)
    if yield_dict:
        fcf_annual[t] = yield_dict
        dates = sorted(yield_dict.keys())
        latest = yield_dict[dates[-1]]
        print(f"  {t}: {len(yield_dict)} years ({dates[0].date()}–{dates[-1].date()})  latest_yield={latest:.3%}")
    else:
        print(f"  {t}: no FMP data")

print(f"\n  Tickers with annual FCF yield: {len(fcf_annual)}")

# ── PART 3: Monthly return series ─────────────────────────────────────────────
print("\n[3] Loading monthly return series …")
monthly_returns = {}
for t in list(fcf_annual.keys()) + ["SPY"]:
    s = fetch_monthly_returns_series(t)
    if len(s.dropna()) > 20:
        monthly_returns[t] = s

spy_monthly = monthly_returns.get("SPY", spy_monthly_full)

# ── PART 4: Annual-rebalance FCF/P portfolio ──────────────────────────────────
print("\n[4] Building annual-rebalance FCF/P portfolio …")
# Rebalance: end of March each year
# Signal cutoff: Dec 31 of prior year (3-month reporting lag)
# FY ending Dec gets filed by March; other FYs (Sep, Jun) are filed even earlier

all_monthly_rets_list = {}

for year in range(2022, 2026):
    rebalance_date  = pd.Timestamp(year, 3, 31)
    signal_cutoff   = pd.Timestamp(year - 1, 12, 31)

    fcf_yields = {}
    for t, yield_dict in fcf_annual.items():
        valid = {d: v for d, v in yield_dict.items() if d <= signal_cutoff}
        if not valid:
            continue
        latest_date = max(valid.keys())
        age_months = (signal_cutoff - latest_date).days / 30.44
        if age_months > MAX_SIGNAL_AGE_MONTHS:
            continue
        fcf_yields[t] = valid[latest_date]

    if len(fcf_yields) < N_LONG:
        print(f"  {year}: only {len(fcf_yields)} tickers with valid FCF yield — skipping")
        continue

    scores = pd.Series(fcf_yields).sort_values(ascending=False)
    top    = list(scores.head(N_LONG).index)
    print(f"  {year}: {len(fcf_yields)} ranked; top {N_LONG} = {top}")
    print(f"         FCF yields: {scores.head(5).round(4).to_dict()}")

    # Hold April of this year through March of next year
    hold_start = rebalance_date
    hold_end   = pd.Timestamp(year + 1, 3, 31)

    cohort_rets = []
    for t in top:
        if t in monthly_returns:
            r = monthly_returns[t]
            mask = (r.index > hold_start) & (r.index <= hold_end)
            if mask.sum() > 0:
                cohort_rets.append(r[mask])

    if not cohort_rets:
        continue

    port = pd.concat(cohort_rets, axis=1).mean(axis=1)
    for dt, rv in port.items():
        if not np.isnan(rv):
            all_monthly_rets_list[dt] = rv

if not all_monthly_rets_list:
    print("\nERROR: No portfolio returns generated.")
    import sys; sys.exit(1)

# ── PART 5: Performance metrics ───────────────────────────────────────────────
port_series = pd.Series(all_monthly_rets_list).sort_index()
port_series = port_series.groupby(port_series.index).mean()

IS_mask  = (port_series.index >= FCF_IS_START) & (port_series.index <= FCF_IS_END)
OOS_mask = port_series.index >= FCF_OOS_START

is_ret  = port_series[IS_mask]
oos_ret = port_series[OOS_mask]

is_stats  = stats(is_ret)
oos_stats = stats(oos_ret)

spy_is  = stats(spy_monthly[(spy_monthly.index >= FCF_IS_START) & (spy_monthly.index <= FCF_IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= FCF_OOS_START])

corr_spy = corr_series(oos_ret, spy_monthly.reindex(oos_ret.index))
wf_ratio = oos_stats["sharpe"] / is_stats["sharpe"] if is_stats["sharpe"] > 0 else 0.0

print(f"\n{'=' * 60}")
print("RESULTS — H284 REVISED FCF/P Stock Screener (FMP data)")
print(f"{'=' * 60}")
print(f"\nIS  (Apr 2022 – Mar 2024): Sharpe={is_stats['sharpe']:.4f}  CAGR={is_stats['cagr']*100:.1f}%"
      f"  MaxDD={is_stats['max_drawdown']*100:.1f}%  NegYrs={is_stats['neg_years']}")
print(f"OOS (Apr 2024 – present):  Sharpe={oos_stats['sharpe']:.4f}  CAGR={oos_stats['cagr']*100:.1f}%"
      f"  MaxDD={oos_stats['max_drawdown']*100:.1f}%  NegYrs={oos_stats['neg_years']}")
print(f"\nSPY IS:  Sharpe={spy_is['sharpe']:.4f}  OOS: Sharpe={spy_oos['sharpe']:.4f}")
print(f"Walkforward ratio: {wf_ratio:.3f}")
print(f"Corr(H284, SPY) OOS: {corr_spy:.3f}")

cowz = etf_monthly.get("COWZ", pd.Series(dtype=float))
if len(cowz) > 20:
    cowz_oos   = cowz[cowz.index >= "2020-01-01"]
    cowz_stats = stats(cowz_oos)
    print(f"\nETF proxy (COWZ OOS 2020+): Sharpe={cowz_stats['sharpe']:.4f}"
          f"  CAGR={cowz_stats['cagr']*100:.1f}%  MaxDD={cowz_stats['max_drawdown']*100:.1f}%")

gate1 = oos_stats["sharpe"] >= 0.8
gate2 = wf_ratio >= 0.45

print(f"\nGate 1 — OOS Sharpe >= 0.8:        {'PASS' if gate1 else 'FAIL'} ({oos_stats['sharpe']:.4f})")
print(f"Gate 2 — Walkforward ratio >= 0.45: {'PASS' if gate2 else 'FAIL'} ({wf_ratio:.3f})")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")
print("⚠️  Survivorship bias caveat: universe selected with 2026 knowledge.")
print("⚠️  Short history: FMP free tier = 5yr annual → 2 IS + 1.5 OOS years.")
print("⚠️  Annual rebalance (not quarterly): fewer data points but cleaner signal.")

results = {
    "hypothesis": "H284",
    "description": "FCF/P Stock Screener (Free Cash Flow Yield via FMP)",
    "data_source": "FMP stable/key-metrics → freeCashFlowYield",
    "rebalance": "annual (end of Q1)",
    "signal_lag": "FY ending <= Dec 31 of prior year (3-month reporting lag)",
    "is_period": "2022-04 to 2024-03",
    "oos_period": "2024-04 to present",
    "is_stats":  is_stats,
    "oos_stats": oos_stats,
    "spy_is":    spy_is,
    "spy_oos":   spy_oos,
    "walkforward_ratio": round(wf_ratio, 4),
    "corr_spy_oos": corr_spy,
    "verdict": verdict,
    "survivorship_bias": True,
    "n_tickers_with_data": len(fcf_annual),
    "cowz_oos_sharpe": stats(cowz[cowz.index >= "2020-01-01"])["sharpe"] if len(cowz) > 20 else None,
}
out_path = RESULT_DIR / "h284_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
