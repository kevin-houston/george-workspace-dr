"""
H312 — GenAI Stock Selection: Price-Volume Factor Baseline
===========================================================

Source: arXiv:2602.00196 "Can Large Language Models Beat Wall Street?
         Generative AI for Stock Selection" (Kim et al., 2025)

Hypothesis:
  The paper reports 14–91% Sharpe improvement when adding LLM+RAG features
  (analyst reports, options surface, price-volume) over price-volume-only
  baselines. This script tests the PRICE-VOLUME BASELINE — establishing the
  floor the full LLM version must beat.

Factors (price-volume only):
  1. mom_12_1 — 12-month total return, skip most-recent month (reversal avoidance)
  2. mom_3    — 3-month total return
  3. low_vol  — inverse 21-day realized annualized volatility (low-vol premium)
  4. hi52     — close / 52-week high (52-wk-high proximity; George & Hwang 2004)
  5. risk_adj — 3m return / 3m realized vol (Sharpe-ratio proxy)

Signal: equal-weight z-score composite → rank descending → long top-20 stocks
Rebalance: monthly (month-end)
Portfolio: equal-weight top 20, no leverage

SURVIVORSHIP BIAS NOTE:
  Universe is ~85 large S&P 500 names liquid since 2010. Stocks with IPOs
  after 2010 (TSLA IPO 2010, META IPO 2012) are included but create modest
  upward bias. Phase 2 uses historical constituents via Polygon or CRSP.

IS:  2010-01-01 to 2019-12-31
OOS: 2020-01-01 to 2026-06-19
Gate: OOS Sharpe > 1.20
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Universe ──────────────────────────────────────────────────────────────────
UNIVERSE = [
    # Technology
    "AAPL","MSFT","NVDA","AVGO","ORCL","CSCO","INTC","TXN","QCOM","AMD",
    "IBM","AMAT","MU","ADI","KLAC",
    # Communication / Media
    "GOOGL","META","NFLX","CMCSA","DIS","VZ","T",
    # Consumer Discretionary
    "AMZN","HD","MCD","NKE","SBUX","TGT","LOW","COST","BKNG",
    # Consumer Staples
    "KO","PEP","PG","WMT","CL","MO","PM",
    # Healthcare
    "JNJ","LLY","UNH","ABBV","MRK","BMY","PFE","AMGN","GILD","MDT","ABT",
    # Financials
    "JPM","BAC","WFC","GS","MS","BLK","AXP","V","MA","SCHW","C","USB","PNC",
    # Industrials
    "CAT","DE","HON","MMM","GE","UPS","FDX","BA","LMT","RTX",
    # Energy
    "XOM","CVX","COP","SLB","EOG","PSX","VLO",
    # Materials / Utilities / REITs
    "LIN","SHW","FCX","NEE","DUK","PLD","AMT",
    # Benchmark
    "SPY",
]
UNIVERSE = sorted(set(UNIVERSE))

IS_START   = "2009-01-01"   # extra year for warm-up
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-19"
FULL_START = IS_START
FULL_END   = OOS_END
TRADING_DAYS = 252
VOL_WINDOW   = 21
N_HOLD       = 20

print("H312 — GenAI Stock Selection: Price-Volume Factor Baseline")
print("=" * 60)

# ── Download ──────────────────────────────────────────────────────────────────
print("Downloading price data…")
raw = yf.download(UNIVERSE, start=FULL_START, end=FULL_END,
                  progress=False, auto_adjust=True)
prices = raw["Close"]
prices.dropna(axis=1, how="all", inplace=True)

spx = prices["SPY"]
stocks = [t for t in UNIVERSE if t != "SPY" and t in prices.columns]
prices_s = prices[stocks]
print(f"  Universe: {len(stocks)} stocks loaded")

month_ends = prices_s.resample("BME").last().index

# ── Monthly factor computation ─────────────────────────────────────────────────
print("Computing monthly factors…")

def monthly_return(px: pd.Series, t_end, months: int) -> float:
    end   = px[px.index <= t_end]
    if end.empty: return np.nan
    # Approximate: use ~21*months trading-day lookback
    td    = int(months * 21)
    start = end.iloc[-min(len(end), td+1):-1]  # exclude the month itself for 12-1
    if start.empty: return np.nan
    return float(end.iloc[-1] / start.iloc[0] - 1)

records = []
for i in range(14, len(month_ends) - 1):  # need ~12m warm-up
    t0 = month_ends[i]   # signal date
    t1 = month_ends[i+1] # hold-period end

    row = {"date": t0}
    scores = {}

    for sym in stocks:
        px = prices_s[sym].dropna()
        px_to = px[px.index <= t0]
        if len(px_to) < 260:  # need ~1 year
            continue

        # 1-month return (most recent month)
        m1 = float(px_to.iloc[-1] / px_to.iloc[-22] - 1) if len(px_to) >= 22 else np.nan
        # 3-month return
        m3 = float(px_to.iloc[-1] / px_to.iloc[-63] - 1) if len(px_to) >= 63 else np.nan
        # 12-month return
        m12 = float(px_to.iloc[-1] / px_to.iloc[-252] - 1) if len(px_to) >= 252 else np.nan
        # skip-month momentum: 12m minus 1m
        mom_12_1 = (m12 - m1) if (not np.isnan(m12) and not np.isnan(m1)) else np.nan
        # 21-day realized vol
        rets_21 = np.log(px_to.iloc[-22:] / px_to.iloc[-22:].shift(1)).dropna()
        vol_21 = float(rets_21.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(rets_21) >= 15 else np.nan
        # 52-week high proximity
        hi52 = float(px_to.iloc[-1] / px_to.iloc[-252:].max()) if len(px_to) >= 252 else np.nan
        # Risk-adjusted 3m
        if m3 is not None and vol_21 is not None and not np.isnan(m3) and not np.isnan(vol_21) and vol_21 > 0:
            risk_adj = m3 / (vol_21 / np.sqrt(4))  # annualized to quarterly
        else:
            risk_adj = np.nan

        scores[sym] = {
            "mom_12_1": mom_12_1,
            "mom_3":    m3,
            "low_vol":  -vol_21 if vol_21 is not None and not np.isnan(vol_21) else np.nan,
            "hi52":     hi52,
            "risk_adj": risk_adj,
        }

    # Build factor matrix and z-score
    factors = ["mom_12_1", "mom_3", "low_vol", "hi52", "risk_adj"]
    df_f = pd.DataFrame(scores).T[factors].dropna(how="all")
    if len(df_f) < N_HOLD + 5:
        continue

    # Cross-sectional z-score each factor, then average
    z = df_f.apply(lambda col: (col - col.mean()) / col.std(ddof=1), axis=0)
    composite = z.mean(axis=1)
    top20 = composite.nlargest(N_HOLD).index.tolist()

    # Compute equal-weight return over [t0, t1]
    port_rets = []
    for sym in top20:
        px = prices_s[sym].dropna()
        px_hold = px[(px.index > t0) & (px.index <= t1)]
        if len(px_hold) < 5:
            continue
        r = float(px_hold.iloc[-1] / px_hold.iloc[0] - 1)
        port_rets.append(r)

    if not port_rets:
        continue

    # SPY benchmark return same period
    spy_hold = spx[(spx.index > t0) & (spx.index <= t1)]
    spy_ret = float(spy_hold.iloc[-1] / spy_hold.iloc[0] - 1) if len(spy_hold) >= 5 else np.nan

    records.append({
        "date":    t0,
        "ret":     float(np.mean(port_rets)),
        "spy_ret": spy_ret,
        "top20":   top20,
        "n_scored": len(df_f),
    })

df = pd.DataFrame(records).set_index("date")
df.index = pd.to_datetime(df.index)
print(f"  Monthly observations: {len(df)}")

# ── Backtest ───────────────────────────────────────────────────────────────────
def backtest(label, rets, spy_rets=None):
    if len(rets) < 6:
        print(f"  {label}: insufficient data (n={len(rets)})")
        return None
    s = float(rets.mean() / rets.std(ddof=1) * np.sqrt(12))
    cagr = float((1 + rets).prod() ** (12 / len(rets)) - 1)
    cum = (1 + rets).cumprod()
    dd = float(((cum - cum.cummax()) / cum.cummax()).min())
    wr = float((rets > 0).mean())
    te = excess = ic = ""
    if spy_rets is not None and len(spy_rets) == len(rets):
        excess_ret = rets - spy_rets
        te = float(excess_ret.std(ddof=1) * np.sqrt(12))
        ir = float(excess_ret.mean() / excess_ret.std(ddof=1) * np.sqrt(12))
        corr = float(rets.corr(spy_rets))
        ic = f"  IR={ir:.3f}  TE={te:.1%}  Corr(SPY)={corr:.3f}"
    print(f"  {label}: Sharpe={s:.3f}  CAGR={cagr:.1%}  MaxDD={dd:.1%}  WR={wr:.0%}  n={len(rets)}{ic}")
    return {"sharpe": s, "cagr": cagr, "max_dd": dd, "win_rate": wr, "n": len(rets)}

print("\n─── In-Sample (2010–2019) ───")
is_mask  = df.index <  pd.Timestamp(OOS_START)
oos_mask = df.index >= pd.Timestamp(OOS_START)

r_is  = backtest("H312 Top-20 EW",  df[is_mask]["ret"],  df[is_mask]["spy_ret"])
r_spy_is = backtest("SPY buy-hold",  df[is_mask]["spy_ret"])

print("\n─── Out-of-Sample (2020–2026) ───")
r_oos = backtest("H312 Top-20 EW",  df[oos_mask]["ret"],  df[oos_mask]["spy_ret"])
r_spy_oos = backtest("SPY buy-hold", df[oos_mask]["spy_ret"])

# Walk-forward ratio
wf = None
if r_is and r_oos:
    wf = r_oos["sharpe"] / r_is["sharpe"] if r_is["sharpe"] > 0 else None
    print(f"\n  Walk-forward ratio: {wf:.3f}" if wf else "\n  Walk-forward ratio: n/a (IS Sharpe ≤ 0)")

# ── Variant: 12-1 momentum only (baseline comparison) ─────────────────────────
print("\n─── Variant B: 12-1 Momentum Only ───")
records_b = []
for i in range(14, len(month_ends) - 1):
    t0 = month_ends[i]
    t1 = month_ends[i+1]
    scores_b = {}
    for sym in stocks:
        px = prices_s[sym].dropna()
        px_to = px[px.index <= t0]
        if len(px_to) < 260: continue
        m1  = float(px_to.iloc[-1] / px_to.iloc[-22] - 1) if len(px_to) >= 22 else np.nan
        m12 = float(px_to.iloc[-1] / px_to.iloc[-252] - 1) if len(px_to) >= 252 else np.nan
        if not np.isnan(m1) and not np.isnan(m12):
            scores_b[sym] = m12 - m1
    if len(scores_b) < N_HOLD + 5: continue
    top20b = sorted(scores_b, key=lambda s: -scores_b[s])[:N_HOLD]
    port_rets_b = []
    for sym in top20b:
        px = prices_s[sym].dropna()
        px_h = px[(px.index > t0) & (px.index <= t1)]
        if len(px_h) < 5: continue
        port_rets_b.append(float(px_h.iloc[-1] / px_h.iloc[0] - 1))
    if not port_rets_b: continue
    spy_h = spx[(spx.index > t0) & (spx.index <= t1)]
    spy_r = float(spy_h.iloc[-1] / spy_h.iloc[0] - 1) if len(spy_h) >= 5 else np.nan
    records_b.append({"date": t0, "ret": float(np.mean(port_rets_b)), "spy_ret": spy_r})

df_b = pd.DataFrame(records_b).set_index("date")
df_b.index = pd.to_datetime(df_b.index)

is_b  = df_b[df_b.index <  pd.Timestamp(OOS_START)]
oos_b = df_b[df_b.index >= pd.Timestamp(OOS_START)]
print("  IS :")
backtest("  Momentum-only", is_b["ret"],  is_b["spy_ret"])
print("  OOS:")
backtest("  Momentum-only", oos_b["ret"], oos_b["spy_ret"])

# ── Recent top-20 holdings ─────────────────────────────────────────────────────
print("\n─── Most Recent Holdings (for reference) ───")
last = df.iloc[-1]
print(f"  Signal date: {df.index[-1].date()}")
print(f"  Top-20: {', '.join(last['top20'])}")

# ── OOS year-by-year ───────────────────────────────────────────────────────────
print("\n─── OOS Year-by-Year ───")
oos = df[oos_mask].copy()
for yr in sorted(oos.index.year.unique()):
    yr_df = oos[oos.index.year == yr]
    if len(yr_df) < 2: continue
    cum = float((1 + yr_df["ret"]).prod() - 1)
    spy_c = float((1 + yr_df["spy_ret"]).prod() - 1)
    print(f"  {yr}: H312={cum:>+6.1%}  SPY={spy_c:>+6.1%}  "
          f"excess={cum-spy_c:>+5.1%}")

# ── Save results ───────────────────────────────────────────────────────────────
results = {
    "IS":  r_is,
    "OOS": r_oos,
    "WF":  round(wf, 3) if wf else None,
    "SPY_IS":  r_spy_is,
    "SPY_OOS": r_spy_oos,
}
out = "backtesting/results/h312_results.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults → {out}")

gate = "PASS" if r_oos and r_oos["sharpe"] > 1.20 else "FAIL"
print(f"Gate (OOS Sharpe > 1.20): {gate}")
print("Phase 2: add LLM+RAG features (EDGAR analyst reports + Polygon options IV).")
print("  Expected improvement vs this baseline: +14–91% Sharpe per arXiv:2602.00196")
