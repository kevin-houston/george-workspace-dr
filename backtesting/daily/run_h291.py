"""
H291 — 52-Week High Proximity Momentum
=======================================

Hypothesis:
  George & Hwang (2004) "The 52-Week High and Momentum Investing" (JF).
  Stocks trading close to their 52-week high outperform because of anchoring bias:
  investors use the 52-wk high as a reference point, are reluctant to bid beyond
  it, then when fundamentals force a breakout the continuation is strong.

  Signal: R52 = P_t / max(P over prior 252 trading days)
  Portfolio: long top-10 stocks by R52 ratio, monthly rebalance, equal-weight.

  IS:  2008-2017  (10 years)
  OOS: 2018-present
  Gate: OOS Sharpe ≥ 0.9, walkforward ratio ≥ 0.45

  ⚠️ Survivorship bias: universe selected with 2026 knowledge.

Academic basis:
  - George & Hwang (2004, JF): 52-wk high explains more momentum profit than
    6m/12m raw returns
  - Bhootra & Hur (2013): +2.3%/month for stocks near but not AT their high
  - Li & Yu (2012): aggregate 52-wk proximity predicts market returns
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

IS_START  = "2008-01-01"
IS_END    = "2017-12-31"
OOS_START = "2018-01-01"
FULL_END  = "2026-06-01"

UNIVERSE = [
    "AAPL","MSFT","GOOGL","AMZN","META","INTC","CSCO","QCOM","TXN","ORCL",
    "JNJ","UNH","PFE","ABBV","MRK","LLY","BMY","AMGN","MDT","ABT",
    "HD","LOW","MCD","NKE","SBUX","TGT","CMG","YUM","DHI","PHM",
    "WMT","PG","KO","PEP","PM","MO","CL","GIS","SYY","CHD",
    "JPM","BAC","WFC","GS","MS","BLK","AXP","USB","PNC","TFC",
]

N_LONG     = 10
LOOKBACK   = 252  # trading days for 52-week window


def fetch_daily_prices(ticker):
    cache = CACHE_DIR / f"h291_daily_{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache).squeeze().rename(ticker)
    raw = yf.download(ticker, start="2007-01-01", end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    close = raw.xs(ticker, axis=1, level=1)["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
    close.to_frame().to_parquet(cache)
    return close.rename(ticker)


def stats(r):
    r = r.dropna()
    if len(r) < 12:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r), "neg_years": 0}
    eq   = (1 + r).cumprod()
    n_yr = len(r) / 12
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe   = cagr / vol if vol > 0 else 0.0
    max_dd   = float((eq / eq.expanding().max() - 1).min())
    annual   = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((annual < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r), "neg_years": neg_years}


def corr_s(r1, r2):
    idx = r1.dropna().index.intersection(r2.dropna().index)
    if len(idx) < 6:
        return float("nan")
    return round(float(r1.reindex(idx).corr(r2.reindex(idx))), 4)


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("H291 — 52-Week High Proximity Momentum (George & Hwang 2004)")
print("=" * 80)

print("\n[1] Fetching daily prices …")
daily = {}
for t in UNIVERSE + ["SPY"]:
    s = fetch_daily_prices(t)
    if len(s.dropna()) > 500:
        daily[t] = s
print(f"  Loaded {len(daily)} tickers")

# Build monthly returns from daily prices
print("\n[2] Computing monthly returns and 52-week-high ratios …")
monthly = {}
for t, s in daily.items():
    monthly[t] = s.resample("ME").last().pct_change().rename(t)

spy_monthly = monthly.get("SPY", pd.Series(dtype=float))

# For each month-end, compute R52 = price / max(price over prior 252 days)
# We compute this on monthly-rebalance dates using daily data
rebalance_dates = pd.date_range(start=IS_START, end=FULL_END, freq="ME")

port_returns = {}
for reb_date in rebalance_dates:
    scores = {}
    for t in UNIVERSE:
        if t not in daily:
            continue
        price_hist = daily[t]
        # Get prices up to and including rebalance date
        hist = price_hist[price_hist.index <= reb_date]
        if len(hist) < LOOKBACK:
            continue
        current_price = float(hist.iloc[-1])
        high_52w = float(hist.iloc[-LOOKBACK:].max())
        if high_52w <= 0:
            continue
        r52 = current_price / high_52w
        if np.isfinite(r52):
            scores[t] = r52

    if len(scores) < N_LONG:
        continue

    ranked = pd.Series(scores).sort_values(ascending=False)
    top    = list(ranked.head(N_LONG).index)

    # Next month's return
    next_month = reb_date + pd.DateOffset(months=1)
    cohort = []
    for t in top:
        if t in monthly:
            r = monthly[t]
            mask = (r.index.year == next_month.year) & (r.index.month == next_month.month)
            if mask.any():
                cohort.append(float(r[mask].iloc[0]))

    if cohort:
        port_returns[next_month] = np.mean(cohort)

print(f"  Portfolio return observations: {len(port_returns)}")

port_series = pd.Series(port_returns).sort_index()

IS_mask  = (port_series.index >= IS_START)  & (port_series.index <= IS_END)
OOS_mask = port_series.index >= OOS_START

is_ret  = port_series[IS_mask]
oos_ret = port_series[OOS_mask]

is_s  = stats(is_ret)
oos_s = stats(oos_ret)

spy_is  = stats(spy_monthly[(spy_monthly.index >= IS_START) & (spy_monthly.index <= IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= OOS_START])

wf     = oos_s["sharpe"] / is_s["sharpe"] if is_s["sharpe"] > 0 else 0.0
c_spy  = corr_s(oos_ret, spy_monthly.reindex(oos_ret.index))

# Production proxy: blend using approximate weights
prod_monthly = None
try:
    PROD_W = {"SPY": 0.70, "TLT": 0.21, "BIL": 0.09}
    prod_parts = []
    for t, w in PROD_W.items():
        raw = yf.download(t, start="2007-01-01", end=FULL_END, auto_adjust=True, progress=False)
        if not raw.empty:
            c = raw.xs(t, axis=1, level=1)["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
            prod_parts.append(w * c.resample("ME").last().pct_change().rename(t))
    if prod_parts:
        prod_monthly = pd.concat(prod_parts, axis=1).sum(axis=1)
except Exception:
    pass

c_prod = corr_s(oos_ret, prod_monthly.reindex(oos_ret.index)) if prod_monthly is not None else float("nan")

print(f"\n{'=' * 60}")
print("RESULTS — H291 52-Week High Proximity Momentum")
print(f"{'=' * 60}")
print(f"\nIS  (2008-2017): Sharpe={is_s['sharpe']:.4f}  CAGR={is_s['cagr']*100:.1f}%  MaxDD={is_s['max_drawdown']*100:.1f}%  NegYrs={is_s['neg_years']}")
print(f"OOS (2018-2025): Sharpe={oos_s['sharpe']:.4f}  CAGR={oos_s['cagr']*100:.1f}%  MaxDD={oos_s['max_drawdown']*100:.1f}%  NegYrs={oos_s['neg_years']}")
print(f"\nSPY IS: Sharpe={spy_is['sharpe']:.4f}  OOS: Sharpe={spy_oos['sharpe']:.4f}")
print(f"Walkforward ratio: {wf:.3f}")
print(f"Corr(H291, SPY) OOS:  {c_spy:.3f}")
print(f"Corr(H291, Prod) OOS: {c_prod:.3f}")

gate1 = oos_s["sharpe"] >= 0.9
gate2 = wf >= 0.45

print(f"\nGate 1 — OOS Sharpe >= 0.9:        {'PASS' if gate1 else 'FAIL'} ({oos_s['sharpe']:.4f})")
print(f"Gate 2 — Walkforward ratio >= 0.45: {'PASS' if gate2 else 'FAIL'} ({wf:.3f})")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")
print("⚠️  Survivorship bias caveat: fixed universe selected with 2026 knowledge.")

results = {
    "hypothesis": "H291",
    "description": "52-Week High Proximity Momentum (George & Hwang 2004)",
    "signal": "P_t / max(P over prior 252 trading days) → long top-10",
    "rebalance": "monthly", "n_long": N_LONG,
    "is_period": "2008-2017", "oos_period": "2018-2025",
    "is_stats": is_s, "oos_stats": oos_s,
    "spy_is": spy_is, "spy_oos": spy_oos,
    "walkforward_ratio": round(wf, 4),
    "corr_spy_oos": c_spy, "corr_prod_oos": c_prod,
    "verdict": verdict, "survivorship_bias": True,
}
out = RESULT_DIR / "h291_results.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out}")
