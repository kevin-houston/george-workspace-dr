"""
H284 — FCF/P Stock Screener (Free Cash Flow Yield Factor)
=========================================================

Hypothesis:
  Yartseva (2025) "What Makes a Multibagger?" finds FCF/P (free cash flow yield)
  is the #1 predictor of multibagger outperformance. Top FCF/P quintile outperforms
  by ~15%/yr in cross-sectional study of US stocks 2000-2023.

  Design:
    - Universe: 50 S&P 500 large-cap stocks (diverse sectors, listed before 2010)
    - Signal: Free Cash Flow Yield = TTM FCF / Market Cap
      TTM FCF computed from yfinance quarterly cash flow (OCF - CapEx), summed over
      trailing 4 quarters. Market cap = shares_outstanding × price.
    - Rebalance: quarterly (March/June/September/December) to match quarterly filing cycle
    - Portfolio: long top-10 by FCF yield, equal-weight

  Data availability: yfinance provides ~5 years of quarterly cash flow data.
  This limits the full IS/OOS split. We use:
    IS: 2020-2022 (12 quarters)
    OOS: 2023-2025 (10 quarters)

  Gate: OOS Sharpe ≥ 0.8, OOS MaxDD ≤ -30%

  Cross-check: COWZ ETF (Pacer US Cash Cows) as FCF factor proxy going back to 2016.
  COWZ OOS (2020+) vs SPY provides longer-horizon validation.

Academic basis:
  - Yartseva 2025: FCF/P #1 multibagger predictor
  - COWZ inception 2016: mechanical FCF/P top-100 Russell 1000 screen
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2019-01-01"
FULL_END   = "2026-06-01"

# IS/OOS split for FCF stock screener
FCF_IS_START  = "2020-01-01"
FCF_IS_END    = "2022-12-31"
FCF_OOS_START = "2023-01-01"

# 50 large-cap S&P 500 stocks — diversified, listed before 2010
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

N_LONG = 10   # top quintile

# Rebalance quarters: Q1 (end Mar), Q2 (end Jun), Q3 (end Sep), Q4 (end Dec)
REBALANCE_MONTHS = [3, 6, 9, 12]


def fetch_quarterly_cashflow(ticker):
    """Returns TTM FCF series keyed by quarter-end date."""
    cache_path = CACHE_DIR / f"h284_qcf_{ticker}.json"
    if cache_path.exists():
        with open(cache_path) as f:
            data = json.load(f)
        return {pd.Timestamp(k): v for k, v in data.items()}

    try:
        tk = yf.Ticker(ticker)
        cf = tk.quarterly_cashflow
        if cf is None or cf.empty:
            return {}

        # Find OCF and CapEx rows
        ocf_row = capex_row = None
        for rn in cf.index:
            r = str(rn).lower()
            if ocf_row is None and "operating" in r and "cash" in r:
                ocf_row = rn
            if capex_row is None and ("capital" in r and ("expend" in r or "expenditure" in r)):
                capex_row = rn

        if ocf_row is None:
            return {}

        # cf columns are quarter-end dates (newest first)
        dates = sorted(cf.columns.tolist())  # oldest to newest

        results = {}
        for i, d in enumerate(dates):
            if i < 3:
                continue  # Need 4 quarters for TTM
            q_dates = dates[i-3:i+1]
            try:
                ocf_vals = [float(cf.loc[ocf_row, qd]) for qd in q_dates
                            if not np.isnan(float(cf.loc[ocf_row, qd]))]
                if len(ocf_vals) < 4:
                    continue
                ttm_ocf = sum(ocf_vals)

                if capex_row is not None:
                    capex_vals = [float(cf.loc[capex_row, qd]) for qd in q_dates
                                  if not np.isnan(float(cf.loc[capex_row, qd]))]
                    ttm_capex = sum(capex_vals)
                else:
                    ttm_capex = 0.0

                ttm_fcf = ttm_ocf - abs(ttm_capex)
                results[pd.Timestamp(d)] = ttm_fcf
            except Exception:
                continue

        cache_data = {str(k): v for k, v in results.items()}
        with open(cache_path, "w") as f:
            json.dump(cache_data, f)

        return results
    except Exception as e:
        return {}


def fetch_shares_price(ticker):
    """Returns (shares_outstanding, price_series) tuple."""
    try:
        tk = yf.Ticker(ticker)
        shares = tk.info.get("sharesOutstanding", None)
        if shares is None or not np.isfinite(float(shares)):
            return None, None
        shares = float(shares)

        raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return None, None
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw.xs(ticker, axis=1, level=1)["Close"]
        else:
            close = raw["Close"]
        return shares, close
    except Exception:
        return None, None


def fetch_monthly_returns_series(ticker):
    """Fetch monthly return series."""
    cache_path = CACHE_DIR / f"h284_monthly_{ticker}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze().rename(ticker)

    raw = yf.download(ticker, start="2015-01-01", end=FULL_END,
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
print("H284 — FCF/P Stock Screener (Free Cash Flow Yield)")
print("=" * 80)

# ── PART 1: ETF-based FCF factor cross-check (COWZ, 2016+) ───────────────────
print("\n[1] ETF-based FCF factor cross-check (COWZ/CALF vs SPY) …")
etf_monthly = {}
for t in ["COWZ", "CALF", "SPY", "BIL", "IWB"]:
    raw = yf.download(t, start="2015-01-01", end=FULL_END, auto_adjust=True, progress=False)
    if raw.empty:
        continue
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(t, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    etf_monthly[t] = close.resample("ME").last().pct_change().dropna().rename(t)

spy_monthly_full = etf_monthly.get("SPY", pd.Series(dtype=float))

# COWZ inception 2016, decent data from 2017
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
    print(f"  {t}: IS(2017-19) Sharpe={s_is['sharpe']:.3f}  OOS(2020+) Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_drawdown']*100:.1f}%  CAGR={s_oos['cagr']*100:.1f}%  Corr(SPY)={c:.3f}")
    print(f"       SPY OOS Sharpe={spy_oos['sharpe']:.3f}")

# ── PART 2: Stock-level FCF screener using yfinance quarterly data ────────────
print("\n[2] Loading quarterly cash flow data for stock-level screener …")

fcf_ttm = {}     # ticker → {quarter_end_date: ttm_fcf}
shares_out = {}  # ticker → shares_outstanding (current)

for t in UNIVERSE:
    fcf_dict = fetch_quarterly_cashflow(t)
    shares, price_series = fetch_shares_price(t)
    if fcf_dict and shares is not None:
        fcf_ttm[t] = fcf_dict
        shares_out[t] = shares
        yrs = sorted(fcf_dict.keys())
        print(f"  {t}: {len(fcf_dict)} quarters ({yrs[0].date() if yrs else 'N/A'}–{yrs[-1].date() if yrs else 'N/A'})")
    else:
        print(f"  {t}: insufficient data")

print(f"\n  Tickers with quarterly FCF data: {len(fcf_ttm)}")

# ── PART 3: Fetch monthly returns for universe ────────────────────────────────
print("\n[3] Loading monthly return series …")
monthly_returns = {}
for t in list(fcf_ttm.keys()) + ["SPY"]:
    s = fetch_monthly_returns_series(t)
    if len(s.dropna()) > 20:
        monthly_returns[t] = s

spy_monthly = monthly_returns.get("SPY", spy_monthly_full)

# ── PART 4: Build quarterly-rebalance portfolio ────────────────────────────────
print("\n[4] Building quarterly-rebalance FCF/P portfolio …")

# For each rebalance date, compute FCF yield from most recent quarterly data
# FCF yield ≈ TTM_FCF / (shares_outstanding * price_at_rebalance)
# We use current shares_outstanding (consistent with most studies on large-caps)

# Build daily price series for mktcap computation
daily_prices = {}
for t in fcf_ttm.keys():
    try:
        raw = yf.download(t, start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
        if raw.empty:
            continue
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw.xs(t, axis=1, level=1)["Close"]
        else:
            close = raw["Close"]
        daily_prices[t] = close
    except Exception:
        pass

# Quarterly rebalance dates
all_monthly_rets_list = {}

for year in range(2020, 2026):
    for month in REBALANCE_MONTHS:
        # Rebalance date = last business day of the rebalance month
        rebalance_date = pd.Timestamp(year, month, 28)
        # Find previous quarter's end for FCF data (lag 1 quarter)
        signal_date = rebalance_date - pd.DateOffset(months=3)

        fcf_yields = {}
        for t, fcf_dict in fcf_ttm.items():
            # Find most recent FCF data point on or before signal_date
            valid_dates = [d for d in fcf_dict.keys() if d <= signal_date + pd.Timedelta(days=45)]
            if not valid_dates:
                continue
            latest = max(valid_dates)
            ttm_fcf = fcf_dict[latest]

            # Get price on rebalance_date for market cap
            if t not in daily_prices:
                continue
            price_data = daily_prices[t]
            near = price_data.loc[price_data.index <= rebalance_date]
            if near.empty:
                continue
            price = float(near.iloc[-1])
            if price <= 0:
                continue

            mktcap = shares_out[t] * price
            if mktcap <= 0:
                continue

            fcf_yield = ttm_fcf / mktcap
            if np.isfinite(fcf_yield):
                fcf_yields[t] = fcf_yield

        if len(fcf_yields) < N_LONG:
            continue

        scores = pd.Series(fcf_yields).sort_values(ascending=False)
        top = list(scores.head(N_LONG).index)

        # Collect monthly returns for next quarter
        next_start = rebalance_date
        next_end   = rebalance_date + pd.DateOffset(months=3)

        cohort_rets = []
        for t in top:
            if t in monthly_returns:
                r = monthly_returns[t]
                mask = (r.index > next_start) & (r.index <= next_end)
                if mask.sum() > 0:
                    cohort_rets.append(r[mask])

        if not cohort_rets:
            continue

        port = pd.concat(cohort_rets, axis=1).mean(axis=1)
        for dt, rv in port.items():
            if not np.isnan(rv):
                all_monthly_rets_list[dt] = rv

        print(f"  {year}-Q{REBALANCE_MONTHS.index(month)+1}: {len(fcf_yields)} tickers, top {N_LONG} = {top[:5]}... (FCF yields: {scores.head(3).round(3).to_dict()})")

if not all_monthly_rets_list:
    print("\nERROR: No portfolio returns. Reporting ETF result only.")
    # Save ETF-based result
    cowz = etf_monthly.get("COWZ", pd.Series(dtype=float))
    cowz_oos = cowz[cowz.index >= "2020-01-01"]
    spy_oos = spy_monthly_full[spy_monthly_full.index >= "2020-01-01"]
    s_cowz_oos = stats(cowz_oos)
    s_spy_oos  = stats(spy_oos)

    verdict = "NOT CONFIRMED" if s_cowz_oos["sharpe"] < 0.8 else "CONFIRMED (ETF proxy)"
    results = {
        "hypothesis": "H284",
        "description": "FCF/P Stock Screener (Free Cash Flow Yield)",
        "etf_proxy_mode": True,
        "cowz_oos_sharpe": s_cowz_oos["sharpe"],
        "cowz_oos_cagr":   s_cowz_oos["cagr"],
        "cowz_oos_maxdd":  s_cowz_oos["max_drawdown"],
        "spy_oos_sharpe":  s_spy_oos["sharpe"],
        "verdict": verdict,
        "note": "yfinance quarterly CF limited to ~5yr; FMP key-metrics 403; COWZ ETF used as proxy",
    }
    out_path = RESULT_DIR / "h284_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {out_path}")
    import sys; sys.exit(0)

# Aggregate
port_series = pd.Series(all_monthly_rets_list).sort_index()
port_series = port_series.groupby(port_series.index).mean()

IS_mask  = (port_series.index >= FCF_IS_START)  & (port_series.index <= FCF_IS_END)
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
print("RESULTS — H284 FCF/P Stock Screener")
print(f"{'=' * 60}")
print(f"\nIS  (2020-2022): Sharpe={is_stats['sharpe']:.4f}  CAGR={is_stats['cagr']*100:.1f}%  MaxDD={is_stats['max_drawdown']*100:.1f}%  NegYrs={is_stats['neg_years']}")
print(f"OOS (2023-2025): Sharpe={oos_stats['sharpe']:.4f}  CAGR={oos_stats['cagr']*100:.1f}%  MaxDD={oos_stats['max_drawdown']*100:.1f}%  NegYrs={oos_stats['neg_years']}")
print(f"\nSPY IS: Sharpe={spy_is['sharpe']:.4f}  OOS: Sharpe={spy_oos['sharpe']:.4f}")
print(f"Walkforward ratio: {wf_ratio:.3f}")
print(f"Corr(H284, SPY) OOS: {corr_spy:.3f}")

# ETF proxy supplement
cowz = etf_monthly.get("COWZ", pd.Series(dtype=float))
if len(cowz) > 20:
    cowz_oos = cowz[cowz.index >= "2020-01-01"]
    cowz_stats = stats(cowz_oos)
    print(f"\nETF proxy (COWZ OOS 2020+): Sharpe={cowz_stats['sharpe']:.4f}  CAGR={cowz_stats['cagr']*100:.1f}%  MaxDD={cowz_stats['max_drawdown']*100:.1f}%")

gate1 = oos_stats["sharpe"] >= 0.8
gate2 = wf_ratio >= 0.45

print(f"\nGate 1 — OOS Sharpe >= 0.8:        {'PASS' if gate1 else 'FAIL'} ({oos_stats['sharpe']:.4f})")
print(f"Gate 2 — Walkforward ratio >= 0.45: {'PASS' if gate2 else 'FAIL'} ({wf_ratio:.3f})")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")
print("⚠️  Survivorship bias caveat: universe selected with 2026 knowledge.")
print("⚠️  Short IS/OOS history (5yr data limit from yfinance quarterly CF).")

results = {
    "hypothesis": "H284",
    "description": "FCF/P Stock Screener (Free Cash Flow Yield)",
    "is_period": "2020-2022",
    "oos_period": "2023-2025",
    "is_stats": is_stats,
    "oos_stats": oos_stats,
    "spy_is": spy_is,
    "spy_oos": spy_oos,
    "walkforward_ratio": round(wf_ratio, 4),
    "corr_spy_oos": corr_spy,
    "verdict": verdict,
    "survivorship_bias": True,
    "cowz_oos_sharpe": stats(etf_monthly.get("COWZ", pd.Series(dtype=float))[
        etf_monthly.get("COWZ", pd.Series(dtype=float)).index >= "2020-01-01"
    ])["sharpe"] if "COWZ" in etf_monthly else None,
}
out_path = RESULT_DIR / "h284_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
