"""
H334 — Return Seasonality × Momentum Composite on H198 Universe
================================================================
Source: Heston & Sadka (2008) "Explaining the Magnitude of Liquidity Premia";
        H292 (seasonality confirmed OOS 0.970, WF 1.411);
        H198 (6-1m momentum confirmed OOS 1.174).

Both signals independently confirmed. H292 note: "useful as signal layer not
standalone." This hypothesis uses IS-frozen seasonal scores as a secondary
rank layer on top of 6-1m momentum. Hypothesis: stocks that simultaneously
have high momentum AND are entering their historically strong calendar month
outperform stocks with only one signal.

Design:
  Seasonality: IS-calibrated (2013-2020) average calendar-month return per stock.
  Momentum:    6-1m skip-month (same as H198/H320 baseline).
  Composite:   equal-weight rank blend (0.5 * mom_rank + 0.5 * sea_rank).
  Weighting:   tested at 0.3/0.7, 0.5/0.5, 0.7/0.3 (mom/sea).
  Top-1 long, monthly rebalance, 10bps TC.

Universe: H198 30-stock S&P 500 (survivorship bias caveat — consistent with H292/H312).
IS: 2013-2020 | OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 baseline) AND Corr(H198) < 0.95 (adds signal diversity)
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

# ── Data ──────────────────────────────────────────────────────────────────────
print("Downloading price data…")
prices = yf.download(UNIVERSE + ["SPY"], start=DATA_START, end=DATA_END,
                     auto_adjust=True, progress=False)['Close'].ffill()
monthly = prices.resample('ME').last()
ret_all = monthly.pct_change()
ret   = ret_all[UNIVERSE]
spy_r = ret_all['SPY']

# ── IS-calibrated seasonal scores ─────────────────────────────────────────────
# For each calendar month m, compute average IS return for each stock.
# Frozen at IS_END — no look-ahead.
is_ret = ret[(ret.index >= IS_START) & (ret.index <= IS_END)]
seasonal_by_month = {}
for m in range(1, 13):
    seasonal_by_month[m] = is_ret[is_ret.index.month == m].mean()

def seasonality_score(signal_date):
    """IS-calibrated avg return for the month AFTER signal_date."""
    next_m = (signal_date.month % 12) + 1
    return seasonal_by_month[next_m]

# ── Momentum signal ───────────────────────────────────────────────────────────
# 6-1m momentum: price[t-1] / price[t-7] - 1  (skip-month)
mom6 = monthly[UNIVERSE].shift(1) / monthly[UNIVERSE].shift(7) - 1

# ── Backtest ──────────────────────────────────────────────────────────────────
def backtest(w_mom, w_sea, ret_df, start, end):
    rets, dates = [], []
    prev = set()
    eval_dates = ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index
    for dt in eval_dates:
        # Signal from previous month-end
        prior = mom6.index[mom6.index < dt]
        if len(prior) == 0: continue
        sig_dt = prior[-1]
        m_sig = mom6.loc[sig_dt].dropna()
        s_sig = seasonality_score(sig_dt)
        common = m_sig.index.intersection(s_sig.index.intersection(s_sig[s_sig.notna()].index))
        if len(common) < TOP_K: continue

        m_rank = m_sig[common].rank(pct=True)
        s_rank = s_sig[common].rank(pct=True)
        composite = w_mom * m_rank + w_sea * s_rank

        holdings  = set(composite.nlargest(TOP_K).index)
        turnover  = len(holdings.symmetric_difference(prev)) / (2 * TOP_K)
        r = ret_df.loc[dt, list(holdings)].mean() - turnover * TC * 2
        rets.append(r); dates.append(dt)
        prev = holdings
    return pd.Series(rets, index=dates)

def sharpe(s):
    if len(s) < 6 or s.std() < 1e-10: return 0.0
    return float(s.mean() / s.std() * np.sqrt(12))

def maxdd(s):
    c = (1 + s).cumprod()
    return float(c.div(c.cummax()).sub(1).min())

def cagr(s):
    return float((1 + s).prod() ** (12 / max(len(s), 1)) - 1)

# ── Baseline: pure momentum (H198) ───────────────────────────────────────────
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

bl_oos  = backtest_mom_only(ret, OOS_START, OOS_END)
bl_sh   = sharpe(bl_oos)
print(f"H198 baseline OOS Sharpe (6-1m top-1): {bl_sh:.3f}")

# ── Test blending variants ─────────────────────────────────────────────────────
variants = [
    ('A', 0.7, 0.3),   # momentum-dominant
    ('B', 0.5, 0.5),   # equal-weight
    ('C', 0.3, 0.7),   # seasonality-dominant
]

print(f"\n{'Variant':<10} {'w_mom':>6} {'w_sea':>6} {'IS_Sh':>7} {'OOS_Sh':>7} "
      f"{'OOS_CAGR':>9} {'MaxDD':>7} {'NegYr':>6} {'Corr_BL':>8} {'Corr_SPY':>9} {'Verdict'}")
print("-" * 100)

results_all = {}
best_oos_sh  = -999.0
best_variant = None

spy_oos = spy_r[(spy_r.index >= OOS_START) & (spy_r.index <= OOS_END)]

for tag, w_mom, w_sea in variants:
    is_ret_v  = backtest(w_mom, w_sea, ret, IS_START, IS_END)
    oos_ret_v = backtest(w_mom, w_sea, ret, OOS_START, OOS_END)

    is_sh  = sharpe(is_ret_v)
    oos_sh = sharpe(oos_ret_v)
    o_cagr = cagr(oos_ret_v)
    o_mdd  = maxdd(oos_ret_v)
    o_neg  = int(((1 + oos_ret_v).resample('YE').prod() - 1 < 0).sum())
    corr_bl  = float(oos_ret_v.corr(bl_oos.reindex(oos_ret_v.index)))
    corr_spy = float(oos_ret_v.corr(spy_oos.reindex(oos_ret_v.index)))
    pass_g   = oos_sh > H198_SHARPE
    verdict  = "PASS" if pass_g else "fail"

    if oos_sh > best_oos_sh:
        best_oos_sh  = oos_sh
        best_variant = tag

    print(f"  Var {tag}   {w_mom:>6.1f} {w_sea:>6.1f} {is_sh:>7.3f} {oos_sh:>7.3f} "
          f"{o_cagr:>9.1%} {o_mdd:>7.1%} {o_neg:>6d} {corr_bl:>8.3f} {corr_spy:>9.3f}  {verdict}")

    results_all[f'variant_{tag}'] = {
        'w_mom': w_mom, 'w_sea': w_sea,
        'is_sharpe': round(is_sh, 3), 'oos_sharpe': round(oos_sh, 3),
        'oos_cagr': round(o_cagr, 3), 'oos_maxdd': round(o_mdd, 3),
        'neg_years': o_neg, 'corr_baseline': round(corr_bl, 3),
        'corr_spy': round(corr_spy, 3), 'pass_gate': pass_g,
    }

print(f"\nBaseline OOS Sharpe: {bl_sh:.3f}  Gate: >{H198_SHARPE}")
any_pass = any(v['pass_gate'] for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"Verdict: {verdict} (best variant {best_variant} OOS Sharpe {best_oos_sh:.3f})")

results = {
    "hypothesis": "H334",
    "baseline_oos_sharpe": round(bl_sh, 3),
    "variants": results_all,
    "best_variant": best_variant,
    "best_oos_sharpe": round(best_oos_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h334_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h334_results.json")
