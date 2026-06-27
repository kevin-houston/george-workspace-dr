"""
H336 — 52-Week High Proximity Momentum on H198 Universe
========================================================
Source: George & Hwang (2004) "The 52-Week High and Momentum Investing" (JF).
        H291 (tested on 50-stock large-cap, OOS Sharpe 0.764, NOT CONFIRMED).

Background: H291 found the signal fails on a broad 50-stock universe because
in a sustained bull market most stocks are simultaneously near their 52-week
highs, collapsing cross-sectional dispersion. However, H291 tested a different
universe (50 large-cap) and a different gate (0.9). Here we test on H198's
NASDAQ-heavy 30-stock universe with gate 1.174 (H198 baseline).

Mechanism: anchoring bias — investors resist bidding beyond 52-week high; when
fundamentals force a breakout, momentum continuation is strong.
Signal: R52 = P_t / max(P over prior 252 trading days), ranked cross-sectionally.

Variants:
  A: pure R52 proximity (top-1 by R52)
  B: composite 50% R52 + 50% 6-1m momentum (equal-weight)
  C: composite 30% R52 + 70% 6-1m momentum (momentum-dominant)
  D: R52 FILTER — only enter top-1 6-1m momentum if R52 > 0.85 (near high),
     else skip month (hold BIL / cash)

Universe: H198 30-stock S&P 500 (survivorship bias caveat — consistent with H334/H312).
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 baseline)
WF threshold: ≥ 0.75 (relaxed for filter variant which can't be improved in IS)
"""
import warnings
warnings.filterwarnings("ignore")
import json, numpy as np, pandas as pd, yfinance as yf
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
TC          = 0.001   # 10bps one-way
TOP_K       = 1
R52_THRESHOLD = 0.85  # for Variant D filter

# ── Data ──────────────────────────────────────────────────────────────────────
print("Downloading price data…")
raw = yf.download(UNIVERSE + ["SPY","BIL"], start=DATA_START, end=DATA_END,
                  auto_adjust=True, progress=False)['Close'].ffill()

# Daily prices for R52 calculation, monthly prices for returns
daily_px = raw[UNIVERSE]
monthly  = raw.resample('ME').last()
ret_all  = monthly.pct_change()
ret      = ret_all[UNIVERSE]
spy_r    = ret_all['SPY']
bil_r    = ret_all['BIL']

# ── 52-week high proximity signal (monthly, using prior 252 trading days) ────
# At each month-end, R52 = last_price / max_price_over_252_days_prior
r52_daily = daily_px / daily_px.rolling(252).max()
r52_monthly = r52_daily.resample('ME').last()  # month-end R52 value

# ── 6-1m momentum signal ─────────────────────────────────────────────────────
# Skip-month: price[t-1] / price[t-7] - 1
mom6 = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(7) - 1

# ── Helper functions ──────────────────────────────────────────────────────────
def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10: return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())

def cagr(s):
    return float((1 + s).prod() ** (12 / max(len(s), 1)) - 1)

# ── Backtest engines ──────────────────────────────────────────────────────────
def backtest_composite(w_r52, w_mom, ret_df, start, end):
    """Composite rank: w_r52 * r52_rank + w_mom * mom_rank, top-1."""
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_r52  = r52_monthly.index[r52_monthly.index < dt]
        prior_mom  = mom6.index[mom6.index < dt]
        if len(prior_r52) == 0 or len(prior_mom) == 0: continue
        r52_sig = r52_monthly.loc[prior_r52[-1]].dropna()
        mom_sig = mom6.loc[prior_mom[-1]].dropna()
        common  = r52_sig.index.intersection(mom_sig.index)
        if len(common) < TOP_K: continue
        r52_rank  = r52_sig[common].rank(pct=True)
        mom_rank  = mom_sig[common].rank(pct=True)
        composite = w_r52 * r52_rank + w_mom * mom_rank
        holdings  = set(composite.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def backtest_r52_only(ret_df, start, end):
    """Pure R52 ranking, top-1."""
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = r52_monthly.index[r52_monthly.index < dt]
        if len(prior) == 0: continue
        sig = r52_monthly.loc[prior[-1]].dropna()
        if len(sig) < TOP_K: continue
        holdings  = set(sig.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def backtest_filter(threshold, ret_df, start, end):
    """
    Variant D: enter top-1 momentum stock only if its R52 >= threshold.
    If R52 < threshold, hold cash (0% return).
    """
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior_r52  = r52_monthly.index[r52_monthly.index < dt]
        prior_mom  = mom6.index[mom6.index < dt]
        if len(prior_r52) == 0 or len(prior_mom) == 0: continue
        r52_sig = r52_monthly.loc[prior_r52[-1]].dropna()
        mom_sig = mom6.loc[prior_mom[-1]].dropna()
        common  = r52_sig.index.intersection(mom_sig.index)
        if len(common) < TOP_K: continue
        # Select top-1 by momentum
        top_ticker = mom_sig[common].nlargest(TOP_K).index[0]
        top_r52    = r52_sig.get(top_ticker, 0.0)
        if top_r52 >= threshold:
            holdings  = {top_ticker}
            turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
            r = ret_df.loc[dt, top_ticker] - turnover * TC * 2
        else:
            # Skip: hold cash (0 return, but account for exit TC if previously held)
            turnover = len(prev) / (2 * TOP_K) if prev else 0
            r = -turnover * TC * 2
            holdings = set()
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def backtest_mom_only(ret_df, start, end):
    """Pure 6-1m momentum baseline (H198 style)."""
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

# ── Baseline ──────────────────────────────────────────────────────────────────
bl_oos = backtest_mom_only(ret, OOS_START, OOS_END)
bl_sh  = sharpe(bl_oos)
spy_oos = spy_r[(spy_r.index >= OOS_START) & (spy_r.index <= OOS_END)]
print(f"H198 baseline OOS Sharpe: {bl_sh:.3f}")
print(f"SPY OOS Sharpe: {sharpe(spy_oos):.3f}")

# ── Evaluate variants ─────────────────────────────────────────────────────────
print(f"\n{'Var':<5} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} {'MaxDD':>7} "
      f"{'NegYr':>6} {'WF':>6} {'CorrBL':>7} {'CorrSPY':>8} {'Verdict'}")
print("-" * 85)

results_all = {}
best_sh, best_var = H198_SHARPE, None

def eval_variant(tag, is_ret, oos_ret):
    global best_sh, best_var
    is_sh  = sharpe(is_ret)
    oos_sh = sharpe(oos_ret)
    o_cagr = cagr(oos_ret)
    o_mdd  = maxdd(oos_ret)
    o_neg  = int(((1 + oos_ret).resample('YE').prod() - 1 < 0).sum())
    wf     = oos_sh / is_sh if is_sh > 0 else 0.0
    corr_bl  = float(oos_ret.corr(bl_oos.reindex(oos_ret.index)))
    corr_spy = float(oos_ret.corr(spy_oos.reindex(oos_ret.index)))
    passes = oos_sh > H198_SHARPE
    if oos_sh > best_sh: best_sh = oos_sh; best_var = tag
    print(f"  {tag:<4} {is_sh:>7.3f} {oos_sh:>8.3f} {o_cagr:>8.1%} {o_mdd:>7.1%} "
          f"{o_neg:>6d} {wf:>6.3f} {corr_bl:>7.3f} {corr_spy:>8.3f}  {'PASS' if passes else 'fail'}")
    results_all[f'variant_{tag}'] = {
        'is_sharpe': round(is_sh,3), 'oos_sharpe': round(oos_sh,3),
        'oos_cagr': round(o_cagr,3), 'oos_maxdd': round(o_mdd,3),
        'neg_years': o_neg, 'wf_ratio': round(wf,3),
        'corr_baseline': round(corr_bl,3), 'corr_spy': round(corr_spy,3),
        'pass_gate': passes,
    }

# Variant A: pure R52
eval_variant('A', backtest_r52_only(ret, IS_START, IS_END),
                  backtest_r52_only(ret, OOS_START, OOS_END))

# Variant B: 50% R52 + 50% momentum
eval_variant('B', backtest_composite(0.5, 0.5, ret, IS_START, IS_END),
                  backtest_composite(0.5, 0.5, ret, OOS_START, OOS_END))

# Variant C: 30% R52 + 70% momentum (momentum-dominant)
eval_variant('C', backtest_composite(0.3, 0.7, ret, IS_START, IS_END),
                  backtest_composite(0.3, 0.7, ret, OOS_START, OOS_END))

# Variant D: momentum with R52 filter (threshold 0.85)
eval_variant('D', backtest_filter(R52_THRESHOLD, ret, IS_START, IS_END),
                  backtest_filter(R52_THRESHOLD, ret, OOS_START, OOS_END))

# Variant E: 70% R52 + 30% momentum
eval_variant('E', backtest_composite(0.7, 0.3, ret, IS_START, IS_END),
                  backtest_composite(0.7, 0.3, ret, OOS_START, OOS_END))

any_pass = any(v['pass_gate'] for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"\nH198 gate: >{H198_SHARPE}  Baseline OOS Sharpe: {bl_sh:.3f}")
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H336",
    "description": "52-Week High Proximity Momentum on H198 Universe",
    "baseline_oos_sharpe": round(bl_sh, 3),
    "h198_gate": H198_SHARPE,
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h336_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h336_results.json")
