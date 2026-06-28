"""
H341 — Residual Momentum on H198 Universe
==========================================
Source: Blitz, Huij & Martens (2011) "Residual Momentum" (SSRN);
        Gutierrez & Prinsky (2007) "Momentum, Business Cycle, and Time-Varying
        Expected Returns."

Hypothesis: Market-orthogonalized momentum (strip SPY beta from each stock's
return history) outperforms raw 12-1m momentum by reducing systematic crash
risk. The residual captures stock-specific alpha momentum, not market drift.

Signal construction (monthly):
  1. For each stock i, at formation month t:
     - Collect prior 11 monthly returns (t-12 to t-2, skip t-1)
     - OLS regression: R_i ~ alpha + beta * R_SPY (11 data points)
     - Residual momentum = sum of OLS residuals over the 11-month window
  2. Rank stocks by residual momentum (highest = buy)
  3. Long top-N stocks, equal-weight

Universe: H198 30-stock S&P 500 (survivorship bias caveat — same as H198).
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 raw momentum baseline)

Variants:
  A: Top-1, residual momentum signal
  B: Top-3, residual momentum signal
  C: Top-1, raw 12-1m (H198 reproduction)
  D: Top-1, 50% residual + 50% raw momentum (blended rank)
  E: Top-3, 50% residual + 50% raw momentum
"""
import warnings
warnings.filterwarnings("ignore")
import json, os, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path
from scipy import stats

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]
BENCHMARK = "SPY"

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

# ── Data download ─────────────────────────────────────────────────────────────
print("Downloading price data...")
tickers = UNIVERSE + [BENCHMARK]
raw = yf.download(tickers, start=DATA_START, end=DATA_END, progress=False, auto_adjust=True)["Close"]
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(0)
raw = raw.ffill().dropna(how="all")

# Monthly returns (end-of-month close)
monthly = raw.resample("ME").last()
rets    = monthly.pct_change().dropna(how="all")
rets    = rets.loc[IS_START:]

spy_ret = rets[BENCHMARK]
stock_rets = rets[UNIVERSE]

print(f"  Monthly periods: {len(rets)} | Stocks: {stock_rets.shape[1]}")

# ── Signal computation ────────────────────────────────────────────────────────

def residual_momentum(stock_rets, spy_ret, t_idx, lookback=11):
    """
    Compute residual momentum for each stock at time t_idx.
    Uses months [t-12 .. t-2] (11 months, skip t-1).
    Returns dict {ticker: residual_mom_sum}.
    """
    if t_idx < lookback + 1:
        return None
    # Indices: skip last month (t-1), use t-2 back 11 months
    end_idx   = t_idx - 1   # skip most recent month
    start_idx = end_idx - lookback
    if start_idx < 0:
        return None

    spy_window = spy_ret.iloc[start_idx:end_idx].values
    signals = {}
    for ticker in UNIVERSE:
        if ticker not in stock_rets.columns:
            continue
        stk_window = stock_rets[ticker].iloc[start_idx:end_idx].values
        if np.isnan(stk_window).any() or np.isnan(spy_window).any():
            signals[ticker] = np.nan
            continue
        # OLS regression: R_i ~ alpha + beta * R_spy
        slope, intercept, _, _, _ = stats.linregress(spy_window, stk_window)
        residuals = stk_window - (intercept + slope * spy_window)
        signals[ticker] = residuals.sum()
    return signals

def raw_momentum(stock_rets, t_idx, lookback=11):
    """12-1m raw momentum (H198 reproduction)."""
    if t_idx < lookback + 1:
        return None
    end_idx   = t_idx - 1
    start_idx = end_idx - lookback
    signals = {}
    for ticker in UNIVERSE:
        if ticker not in stock_rets.columns:
            continue
        # 12-1m: product of monthly returns from start_idx to end_idx
        window = stock_rets[ticker].iloc[start_idx:end_idx].values
        if np.isnan(window).any():
            signals[ticker] = np.nan
            continue
        signals[ticker] = (1 + window).prod() - 1
    return signals

# ── Backtest engine ───────────────────────────────────────────────────────────

def backtest(signal_series, returns_series, dates, top_n=1):
    """
    signal_series: list of dicts {ticker: signal_value} aligned to dates
    returns_series: df of next-month returns
    """
    port_rets = []
    for i, (t, signals) in enumerate(zip(dates, signal_series)):
        if signals is None or len(signals) == 0:
            port_rets.append(np.nan)
            continue
        # Filter NaN
        valid = {k: v for k, v in signals.items() if not np.isnan(v)}
        if not valid:
            port_rets.append(np.nan)
            continue
        ranked = sorted(valid.items(), key=lambda x: x[1], reverse=True)
        selected = [t[0] for t in ranked[:top_n]]
        # Next-month return
        if t not in returns_series.index:
            port_rets.append(np.nan)
            continue
        next_idx = returns_series.index.get_loc(t)
        if next_idx + 1 >= len(returns_series):
            port_rets.append(np.nan)
            continue
        next_t   = returns_series.index[next_idx + 1]
        r = returns_series.loc[next_t, selected].mean()
        port_rets.append(r)
    return pd.Series(port_rets, index=dates).dropna()

# ── Compute signals for all periods ──────────────────────────────────────────
dates = rets.index[13:]   # need 13+ periods for lookback
print(f"  Formation dates: {len(dates)} months")

res_signals  = []
raw_signals  = []
blend_signals = []

for i, t in enumerate(rets.index):
    idx = rets.index.get_loc(t)
    rs  = residual_momentum(stock_rets, spy_ret, idx)
    rm  = raw_momentum(stock_rets, idx)
    res_signals.append(rs)
    raw_signals.append(rm)
    # Blend: rank-average of residual + raw
    if rs is not None and rm is not None:
        tickers_valid = [k for k in UNIVERSE if k in rs and k in rm
                         and not np.isnan(rs[k]) and not np.isnan(rm[k])]
        if tickers_valid:
            res_ranks = {k: sorted(tickers_valid, key=lambda x: rs[x], reverse=True).index(k)
                         for k in tickers_valid}
            raw_ranks = {k: sorted(tickers_valid, key=lambda x: rm[x], reverse=True).index(k)
                         for k in tickers_valid}
            blend = {k: -(res_ranks[k] + raw_ranks[k]) for k in tickers_valid}  # lower rank sum = better
            blend_signals.append(blend)
        else:
            blend_signals.append(None)
    else:
        blend_signals.append(None)

# Trim to dates (offset by 13 periods)
offset = 13
res_signals_trim   = res_signals[offset:]
raw_signals_trim   = raw_signals[offset:]
blend_signals_trim = blend_signals[offset:]

# ── Variants ──────────────────────────────────────────────────────────────────
print("\nRunning variants...")

variants = {
    "A_residual_top1" : backtest(res_signals_trim,   stock_rets, dates, top_n=1),
    "B_residual_top3" : backtest(res_signals_trim,   stock_rets, dates, top_n=3),
    "C_raw_top1"      : backtest(raw_signals_trim,   stock_rets, dates, top_n=1),
    "D_blend_top1"    : backtest(blend_signals_trim, stock_rets, dates, top_n=1),
    "E_blend_top3"    : backtest(blend_signals_trim, stock_rets, dates, top_n=3),
}

spy_monthly = spy_ret.loc[dates[0]:OOS_END]

# ── Metrics ────────────────────────────────────────────────────────────────────
def metrics(rets_series, period_start, period_end):
    r = rets_series.loc[period_start:period_end].dropna()
    if len(r) < 6:
        return dict(sharpe=np.nan, cagr=np.nan, maxdd=np.nan, neg_years=np.nan, n=0)
    ann  = r.mean() * 12
    vol  = r.std() * np.sqrt(12)
    sharpe = ann / vol if vol > 0 else np.nan
    cumulative = (1 + r).cumprod()
    rolling_max = cumulative.cummax()
    drawdown = (cumulative - rolling_max) / rolling_max
    maxdd = drawdown.min()
    years = r.resample("YE").sum()
    neg_years = (years < 0).sum()
    cagr = cumulative.iloc[-1] ** (12 / len(r)) - 1
    return dict(sharpe=round(sharpe,3), cagr=round(cagr,3), maxdd=round(maxdd,3),
                neg_years=int(neg_years), n=len(r))

print("\n{'':25s} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'OOS MaxDD':>10} {'OOS CAGR':>9} {'Neg Yrs':>8}")
print("-"*75)

results = {}
for name, rets_v in variants.items():
    is_m  = metrics(rets_v, IS_START,  IS_END)
    oos_m = metrics(rets_v, OOS_START, OOS_END)
    results[name] = {"is": is_m, "oos": oos_m}
    print(f"  {name:23s}  {is_m['sharpe']:>10.3f}  {oos_m['sharpe']:>11.3f}  "
          f"{oos_m['maxdd']:>10.3f}  {oos_m['cagr']:>9.3f}  {oos_m['neg_years']:>8}")

spy_oos = metrics(spy_monthly, OOS_START, OOS_END)
print(f"  {'SPY (benchmark)':23s}  {'—':>10}  {spy_oos['sharpe']:>11.3f}  "
      f"{spy_oos['maxdd']:>10.3f}  {spy_oos['cagr']:>9.3f}  {spy_oos['neg_years']:>8}")
print(f"  {'H198 gate':23s}  {'—':>10}  {'1.174':>11}  {'—':>10}")

# ── WF ratio & verdict ────────────────────────────────────────────────────────
print("\nWalk-forward ratios (OOS/IS Sharpe):")
best_oos = -np.inf
best_name = ""
for name, r in results.items():
    wf = r['oos']['sharpe'] / r['is']['sharpe'] if r['is']['sharpe'] > 0 else np.nan
    print(f"  {name}: {wf:.3f}")
    if r['oos']['sharpe'] > best_oos:
        best_oos = r['oos']['sharpe']
        best_name = name

gate = 1.174
verdict = "CONFIRMED" if best_oos >= gate else "NOT CONFIRMED"
print(f"\nBest OOS Sharpe: {best_oos:.3f} ({best_name})")
print(f"Gate: {gate} → {verdict}")

# ── Correlation with H026 production ─────────────────────────────────────────
print("\nCorrelation vs SPY (OOS):")
for name, rets_v in variants.items():
    v_oos = rets_v.loc[OOS_START:OOS_END].dropna()
    s_oos = spy_monthly.loc[OOS_START:OOS_END].dropna()
    common = v_oos.index.intersection(s_oos.index)
    if len(common) > 5:
        c = np.corrcoef(v_oos.loc[common], s_oos.loc[common])[0,1]
        print(f"  Corr({name}, SPY): {c:.3f}")

# ── Save results ──────────────────────────────────────────────────────────────
out = {
    "hypothesis": "H341",
    "description": "Residual Momentum (Market-Orthogonal 12-1m Signal) on H198 Universe",
    "source": "Blitz, Huij & Martens (2011) SSRN Residual Momentum",
    "baseline_oos_sharpe": 1.174,
    "gate": 1.174,
    "variants": {k: v for k, v in results.items()},
    "best_variant": best_name,
    "best_oos_sharpe": best_oos,
    "verdict": verdict,
}
with open(RESULT_DIR / "h341_results.json", "w") as f:
    json.dump(out, f, indent=2)
print(f"\nResults saved to backtesting/results/h341_results.json")
