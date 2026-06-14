"""
H292 — Return Seasonality (Same Calendar Month, 1-Year Lag)
============================================================

Hypothesis:
  Heston & Sadka (2008) "Seasonality in the Cross-Section of Stock Returns" (JFE).
  Stocks that performed well in the same calendar month one year ago continue to
  outperform in that month the following year. The pattern persists for up to 20
  annual lags and holds across global equity markets.

  Signal: R_seasonal(i, M, Y) = return of stock i in month M of year Y-1
  Portfolio: long top-10 by seasonal return, monthly rebalance.

  IS:  2008-2017  (10 years)
  OOS: 2018-present
  Gate: OOS Sharpe ≥ 0.9, walkforward ratio ≥ 0.45

  ⚠️ Survivorship bias: fixed universe selected with 2026 knowledge.

Academic basis:
  - Heston & Sadka (2008, JFE): 0.40%/month alpha at 1-year lag, significant
    after Fama-French 3-factor risk adjustment
  - Keloharju et al. (2016): explains ~30% of annual stock return variation
    by sector; earnings seasonality and investor preference are root causes
  - Bogousslavsky (2016): intraday seasonality consistent with return seasonality
  - Robust to: transaction costs, risk adjustments, global replication

Mechanism:
  - Q4 retailers (HD, WMT, TGT) earn more every December → Dec returns repeat
  - Tax-loss harvesting sells stocks in December → January bounce is predictable
  - Earnings release timing is stable year-to-year → CAR patterns repeat
  - Fund manager window dressing: consistent end-of-quarter buying
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

N_LONG = 10


def fetch_monthly_returns(ticker):
    cache = CACHE_DIR / f"h292_monthly_{ticker}.parquet"
    if cache.exists():
        return pd.read_parquet(cache).squeeze().rename(ticker)
    raw = yf.download(ticker, start="2006-01-01", end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)
    close = raw.xs(ticker, axis=1, level=1)["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw["Close"]
    m = close.resample("ME").last().pct_change().rename(ticker)
    m.to_frame().to_parquet(cache)
    return m


def stats(r):
    r = r.dropna()
    if len(r) < 12:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r), "neg_years": 0}
    eq   = (1 + r).cumprod()
    n_yr = len(r) / 12
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    annual = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
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
print("H292 — Return Seasonality (Same Calendar Month, Y-1 Lag)")
print("=" * 80)

print("\n[1] Fetching monthly returns …")
monthly = {}
for t in UNIVERSE + ["SPY"]:
    s = fetch_monthly_returns(t)
    if len(s.dropna()) > 60:
        monthly[t] = s

spy_monthly = monthly.get("SPY", pd.Series(dtype=float))
print(f"  Loaded {len(monthly)} tickers")

# ── Backtest ─────────────────────────────────────────────────────────────────
print("\n[2] Running monthly-rebalance seasonal portfolio …")
port_returns = {}
date_range   = pd.date_range(start=IS_START, end=FULL_END, freq="ME")

for reb_date in date_range:
    year  = reb_date.year
    month = reb_date.month

    # Signal: same calendar month, prior year (12m ago)
    signal_year  = year - 1
    signal_month = month

    scores = {}
    for t in UNIVERSE:
        if t not in monthly:
            continue
        r = monthly[t]
        # Find return for same month of prior year
        mask = (r.index.year == signal_year) & (r.index.month == signal_month)
        if not mask.any():
            continue
        val = float(r[mask].iloc[0])
        if np.isfinite(val):
            scores[t] = val

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

print(f"  Portfolio observations: {len(port_returns)}")

port_series = pd.Series(port_returns).sort_index()

IS_mask  = (port_series.index >= IS_START)  & (port_series.index <= IS_END)
OOS_mask = port_series.index >= OOS_START

is_ret  = port_series[IS_mask]
oos_ret = port_series[OOS_mask]

is_s  = stats(is_ret)
oos_s = stats(oos_ret)

spy_is  = stats(spy_monthly[(spy_monthly.index >= IS_START) & (spy_monthly.index <= IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= OOS_START])

wf    = oos_s["sharpe"] / is_s["sharpe"] if is_s["sharpe"] > 0 else 0.0
c_spy = corr_s(oos_ret, spy_monthly.reindex(oos_ret.index))

# ── Monthly breakdown: does the seasonal signal work in specific months? ─────
print("\n[3] Monthly breakdown (which calendar months drive the signal) …")
for m_num in range(1, 13):
    m_obs = [(d, v) for d, v in port_returns.items()
             if d.month == m_num and d >= pd.Timestamp(OOS_START)]
    if m_obs:
        vals = [v for _, v in m_obs]
        print(f"  Month {m_num:02d}: n={len(vals)}  mean={np.mean(vals)*100:.2f}%  "
              f"win_rate={sum(v>0 for v in vals)/len(vals)*100:.0f}%")

# ── Results ──────────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("RESULTS — H292 Return Seasonality")
print(f"{'=' * 60}")
print(f"\nIS  (2008-2017): Sharpe={is_s['sharpe']:.4f}  CAGR={is_s['cagr']*100:.1f}%  MaxDD={is_s['max_drawdown']*100:.1f}%  NegYrs={is_s['neg_years']}")
print(f"OOS (2018-2025): Sharpe={oos_s['sharpe']:.4f}  CAGR={oos_s['cagr']*100:.1f}%  MaxDD={oos_s['max_drawdown']*100:.1f}%  NegYrs={oos_s['neg_years']}")
print(f"\nSPY IS: Sharpe={spy_is['sharpe']:.4f}  OOS: Sharpe={spy_oos['sharpe']:.4f}")
print(f"Walkforward ratio: {wf:.3f}")
print(f"Corr(H292, SPY) OOS: {c_spy:.3f}")

gate1 = oos_s["sharpe"] >= 0.9
gate2 = wf >= 0.45

print(f"\nGate 1 — OOS Sharpe >= 0.9:        {'PASS' if gate1 else 'FAIL'} ({oos_s['sharpe']:.4f})")
print(f"Gate 2 — Walkforward ratio >= 0.45: {'PASS' if gate2 else 'FAIL'} ({wf:.3f})")

verdict = "CONFIRMED" if (gate1 and gate2) else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")
print("⚠️  Survivorship bias caveat: fixed universe selected with 2026 knowledge.")

results = {
    "hypothesis": "H292",
    "description": "Return Seasonality — same calendar month, 1-year lag (Heston & Sadka 2008)",
    "signal": "return in same calendar month 1 year prior → long top-10",
    "rebalance": "monthly", "n_long": N_LONG,
    "is_period": "2008-2017", "oos_period": "2018-2025",
    "is_stats": is_s, "oos_stats": oos_s,
    "spy_is": spy_is, "spy_oos": spy_oos,
    "walkforward_ratio": round(wf, 4),
    "corr_spy_oos": c_spy,
    "verdict": verdict, "survivorship_bias": True,
}
out = RESULT_DIR / "h292_results.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out}")
