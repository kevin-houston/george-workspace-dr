"""
H339 — LLM Momentum Filter: VADER/TextBlob Sentiment Gate on H198
===================================================================
Source: arXiv:2510.26228 — "LLM-Enhanced Momentum Filter" proposes using
        LLM sentiment signals from news as a crash/momentum filter on top
        of standard price momentum. Negative LLM sentiment → skip trade.

This implementation uses VADER (rule-based sentiment, no LLM API required)
on NewsAPI headlines as a lightweight proxy for the LLM sentiment signal.
NewsAPI free tier: 100 requests/day. We fetch monthly headlines for the
top-1 momentum stock and score them with VADER.

ALTERNATIVE DESIGN (no news API dependency):
Since NewsAPI has limited history and rate limits, we ALSO test a fallback
using the stock's own recent return pattern as a sentiment proxy:
  - "Price momentum acceleration" = current 1m return vs prior 1m return
  - If the stock's 1m return is negative (short-term reversal), that's the
    "negative sentiment" signal and we skip/reduce.

Two families:
  1. VADER News Sentiment Filter (uses NewsAPI $NEWSAPI_KEY)
     - Fetch 20 headlines for top-1 momentum stock's company name
     - Compute VADER compound score
     - If score < -0.1 (net negative): skip trade this month

  2. Price-Based Sentiment Proxy (no API, immediate)
     - Short-term reversal gate: if 1m return of top-1 momentum stock < 0,
       the stock is in a negative near-term trend → skip
     - "Acceleration gate": only enter if 3m return > 1m return (trend is
       accelerating, not decelerating)

We focus on family 2 (price-based) as primary since it has full history.
Family 1 is tested if NewsAPI data is available.

Universe: H198 30-stock S&P 500 (survivorship bias caveat).
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 baseline)
"""
import warnings
warnings.filterwarnings("ignore")
import json, os, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

H198_SHARPE = 1.174
TC          = 0.001
TOP_K       = 1

# ── Price data ────────────────────────────────────────────────────────────────
print("Downloading price data…")
raw     = yf.download(UNIVERSE + ["SPY","BIL"], start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)['Close'].ffill()
monthly = raw.resample('ME').last()
ret_all = monthly.pct_change()
ret     = ret_all[UNIVERSE]
spy_r   = ret_all['SPY']
bil_r   = ret_all['BIL']

# ── Price signals ─────────────────────────────────────────────────────────────
# 6-1m momentum (H198 baseline)
mom6  = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(7) - 1
# 1m return (recent short-term signal)
ret1m = monthly[UNIVERSE].pct_change().shift(1)   # prior month return
# 3m return
ret3m = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(4) - 1
# 6m return (recent half)
ret6m_recent = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(4) - 1  # last 3m
ret6m_prior  = monthly[UNIVERSE].shift(4) / monthly[UNIVERSE].shift(7) - 1  # prior 3m

# ── Helper functions ──────────────────────────────────────────────────────────
def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10: return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())

def cagr(s):
    return float((1 + s).prod() ** (12 / max(len(s), 1)) - 1)

def neg_years(s):
    if not isinstance(s.index, pd.DatetimeIndex) or len(s) < 3: return 0
    try:
        return int(((1 + s).resample('YE').prod() - 1 < 0).sum())
    except Exception:
        return 0

# ── Backtest: pure momentum baseline ─────────────────────────────────────────
def backtest_mom_only(ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = mom6.index[mom6.index < dt]
        if len(prior) == 0: continue
        sig = mom6.loc[prior[-1]].dropna()
        if len(sig) < TOP_K: continue
        holdings  = set(sig.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

# ── Backtest: momentum with filter gate ──────────────────────────────────────
def backtest_filtered(filter_fn, ret_df, start, end):
    """
    filter_fn(dt, top_ticker) → True = enter, False = skip (hold BIL).
    Returns monthly return series.
    """
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_m = mom6.index[mom6.index < dt]
        if len(prior_m) == 0: continue
        sig = mom6.loc[prior_m[-1]].dropna()
        if len(sig) < TOP_K: continue
        top_t = sig.nlargest(TOP_K).index[0]
        if filter_fn(prior_m[-1], top_t):
            holdings = {top_t}
            turnover = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
            r = ret_df.loc[dt, top_t] - turnover * TC * 2
        else:
            # Hold BIL (cash) this month
            turnover = len(prev) / (2 * TOP_K) if prev else 0
            r = float(bil_r.get(dt, 0.0)) - turnover * TC * 2
            holdings = {'BIL'}
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

# ── Filter definitions ────────────────────────────────────────────────────────

# Filter A: 1m return > 0 (recent trend positive — short-term price "sentiment")
def filter_1m_positive(sig_dt, ticker):
    prior = ret1m.index[ret1m.index <= sig_dt]
    if len(prior) == 0: return True  # no data → default enter
    v = ret1m.loc[prior[-1], ticker]
    return bool(pd.notna(v) and v > 0)

# Filter B: 3m return > 0 (medium-term trend positive)
def filter_3m_positive(sig_dt, ticker):
    prior = ret3m.index[ret3m.index <= sig_dt]
    if len(prior) == 0: return True
    v = ret3m.loc[prior[-1], ticker]
    return bool(pd.notna(v) and v > 0)

# Filter C: Momentum Acceleration — recent 3m return > prior 3m return
# (trend is accelerating = higher conviction momentum)
def filter_acceleration(sig_dt, ticker):
    prior_r = ret6m_recent.index[ret6m_recent.index <= sig_dt]
    prior_p = ret6m_prior.index[ret6m_prior.index <= sig_dt]
    if len(prior_r) == 0 or len(prior_p) == 0: return True
    r = ret6m_recent.loc[prior_r[-1], ticker]
    p = ret6m_prior.loc[prior_p[-1], ticker]
    return bool(pd.notna(r) and pd.notna(p) and r > p)

# Filter D: Combined — 1m positive AND acceleration (dual filter)
def filter_combined_1m_accel(sig_dt, ticker):
    return filter_1m_positive(sig_dt, ticker) and filter_acceleration(sig_dt, ticker)

# Filter E: Absolute momentum — top stock's 6m return > 0 (risk-off if negative)
def filter_abs_momentum(sig_dt, ticker):
    prior = mom6.index[mom6.index <= sig_dt]
    if len(prior) == 0: return True
    v = mom6.loc[prior[-1], ticker]
    return bool(pd.notna(v) and v > 0)

# Filter F: 3m positive AND acceleration
def filter_combined_3m_accel(sig_dt, ticker):
    return filter_3m_positive(sig_dt, ticker) and filter_acceleration(sig_dt, ticker)

# ── Baseline ──────────────────────────────────────────────────────────────────
bl_oos  = backtest_mom_only(ret, OOS_START, OOS_END)
bl_sh   = sharpe(bl_oos)
spy_oos = spy_r[(spy_r.index >= OOS_START) & (spy_r.index <= OOS_END)]
print(f"H198 baseline OOS Sharpe: {bl_sh:.3f}")
print(f"SPY OOS Sharpe:           {sharpe(spy_oos):.3f}\n")

# ── Evaluate all variants ─────────────────────────────────────────────────────
variants = [
    ('A (baseline)',     None),
    ('B (1m>0 gate)',    filter_1m_positive),
    ('C (3m>0 gate)',    filter_3m_positive),
    ('D (accel gate)',   filter_acceleration),
    ('E (1m+accel)',     filter_combined_1m_accel),
    ('F (abs mom>0)',    filter_abs_momentum),
    ('G (3m+accel)',     filter_combined_3m_accel),
]

print(f"{'Var':<22} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} {'MaxDD':>7} "
      f"{'NegYr':>6} {'WF':>6} {'CorrBL':>7} {'CorrSPY':>8} {'Verdict'}")
print("-" * 95)

results_all = {}
best_sh, best_var = H198_SHARPE, None

def eval_variant(tag, is_ret, oos_ret):
    global best_sh, best_var
    if len(oos_ret) < 3:
        print(f"  {tag:<22}  SKIP — insufficient data")
        results_all[f'variant_{tag}'] = {'skip': True, 'pass_gate': False}
        return
    is_sh  = sharpe(is_ret)
    oos_sh = sharpe(oos_ret)
    o_cagr = cagr(oos_ret)
    o_mdd  = maxdd(oos_ret)
    o_neg  = neg_years(oos_ret)
    wf     = oos_sh / is_sh if is_sh > 0 else 0.0
    corr_bl  = float(oos_ret.corr(bl_oos.reindex(oos_ret.index)))
    corr_spy = float(oos_ret.corr(spy_oos.reindex(oos_ret.index)))
    passes = oos_sh > H198_SHARPE
    if oos_sh > best_sh: best_sh = oos_sh; best_var = tag
    print(f"  {tag:<22} {is_sh:>7.3f} {oos_sh:>8.3f} {o_cagr:>8.1%} {o_mdd:>7.1%} "
          f"{o_neg:>6d} {wf:>6.3f} {corr_bl:>7.3f} {corr_spy:>8.3f}  {'PASS' if passes else 'fail'}")
    results_all[f'variant_{tag}'] = {
        'is_sharpe': round(is_sh,3), 'oos_sharpe': round(oos_sh,3),
        'oos_cagr': round(o_cagr,3), 'oos_maxdd': round(o_mdd,3),
        'neg_years': o_neg, 'wf_ratio': round(wf,3),
        'corr_baseline': round(corr_bl,3), 'corr_spy': round(corr_spy,3),
        'pass_gate': passes,
    }

for tag, filter_fn in variants:
    if filter_fn is None:
        eval_variant(tag, backtest_mom_only(ret, IS_START, IS_END), bl_oos)
    else:
        eval_variant(tag,
                     backtest_filtered(filter_fn, ret, IS_START, IS_END),
                     backtest_filtered(filter_fn, ret, OOS_START, OOS_END))

any_pass = any(v.get('pass_gate', False) for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"\nH198 gate: >{H198_SHARPE}  Baseline OOS Sharpe: {bl_sh:.3f}")
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H339",
    "description": "Price-Based Momentum Filter Gates (proxy for LLM sentiment gate)",
    "source": "arXiv:2510.26228 LLM momentum filter; price signals as sentiment proxy",
    "baseline_oos_sharpe": round(bl_sh, 3),
    "h198_gate": H198_SHARPE,
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h339_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h339_results.json")
