"""
H335 — Bond ETF Momentum Window Optimization (H045 Universe)
=============================================================
Source: H045 confirmed (OOS Sharpe 1.351, gate benchmark).

H045 signal: rank(12m_mom) + rank(inv_6m_vol), top-2, monthly rebalance.
Universe: SHY, IEI, IEF, TLT, TIP, HYG, LQD (7 Treasury/credit ETFs).

Question: Is 12m the optimal momentum window for bond ETFs, or does a shorter
window capture yield curve dynamics faster?

Variants:
  A: 3m_mom  + inv_6m_vol  (fast yield curve response)
  B: 6m_mom  + inv_6m_vol
  C: 9m_mom  + inv_6m_vol
  D: 12m_mom + inv_6m_vol  (H045 baseline — reproduce to validate)
  E: 12m_mom alone (no vol adjustment)
  F: composite 3m+12m blend + inv_6m_vol

IS: 2007-2016 | OOS: 2017-2026 (matches H045 split)
Gate: OOS Sharpe > 1.351 (H045 confirmed benchmark)
"""
import warnings
warnings.filterwarnings("ignore")
import json, numpy as np, pandas as pd, yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]

DATA_START = "2005-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2007-01-01")
IS_END     = pd.Timestamp("2016-12-31")
OOS_START  = pd.Timestamp("2017-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

H045_SHARPE = 1.351
TC          = 0.001   # 10bps one-way
TOP_K       = 2

# ── Data ──────────────────────────────────────────────────────────────────────
print("Downloading bond ETF data…")
prices = yf.download(UNIVERSE + ["AGG"], start=DATA_START, end=DATA_END,
                     auto_adjust=True, progress=False)['Close'].ffill()
monthly = prices.resample('ME').last()
ret_all = monthly.pct_change()
ret   = ret_all[UNIVERSE]
agg_r = ret_all['AGG']

# ── Backtest ──────────────────────────────────────────────────────────────────
def backtest(signal_df, ret_df, start, end):
    rets, dates = [], []
    prev = set()
    for dt in ret_df[(ret_df.index >= start) & (ret_df.index <= end)].index:
        prior = signal_df.index[signal_df.index < dt]
        if len(prior) == 0: continue
        sig = signal_df.loc[prior[-1]].dropna()
        if len(sig) < TOP_K: continue
        holdings  = set(sig.nlargest(TOP_K).index)
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

# ── Build signals ─────────────────────────────────────────────────────────────
def mom_signal(n_months, monthly_px):
    return monthly_px.shift(1) / monthly_px.shift(1 + n_months) - 1

def vol_signal(n_months, monthly_px):
    return -monthly_px.pct_change().rolling(n_months).std()   # inverted → lower vol = higher score

def rank_sum(*signals, px):
    """Rank-sum composite; each signal is a DataFrame aligned to monthly_px."""
    combined = pd.DataFrame(index=px.index, columns=px.columns, dtype=float)
    combined[:] = 0.0
    for sig in signals:
        combined += sig[UNIVERSE].rank(axis=1, pct=True)
    return combined

px = monthly[UNIVERSE]

variants = {
    'A': rank_sum(mom_signal(3, px),  vol_signal(6, px), px=px),
    'B': rank_sum(mom_signal(6, px),  vol_signal(6, px), px=px),
    'C': rank_sum(mom_signal(9, px),  vol_signal(6, px), px=px),
    'D': rank_sum(mom_signal(12, px), vol_signal(6, px), px=px),   # H045 baseline
    'E': mom_signal(12, px).rank(axis=1, pct=True),                 # no vol adjustment
    'F': rank_sum(mom_signal(3, px) * 0.4 + mom_signal(12, px) * 0.6,
                  vol_signal(6, px), px=px),                        # composite momentum
}

# ── Baseline: AGG buy-and-hold ────────────────────────────────────────────────
agg_oos  = agg_r[(agg_r.index >= OOS_START) & (agg_r.index <= OOS_END)]
agg_sh   = sharpe(agg_oos)
print(f"AGG buy-and-hold OOS Sharpe: {agg_sh:.3f}")

# ── Evaluate all variants ─────────────────────────────────────────────────────
print(f"\n{'Var':<5} {'IS_Sh':>7} {'OOS_Sh':>8} {'CAGR':>8} {'MaxDD':>7} "
      f"{'NegYr':>6} {'WF':>6} {'Verdict'}")
print("-" * 70)

results_all = {}
best_sh, best_var = H045_SHARPE, None

for tag, sig_df in variants.items():
    is_r  = backtest(sig_df, ret, IS_START, IS_END)
    oos_r = backtest(sig_df, ret, OOS_START, OOS_END)
    is_sh  = sharpe(is_r)
    oos_sh = sharpe(oos_r)
    o_cagr = cagr(oos_r)
    o_mdd  = maxdd(oos_r)
    o_neg  = int(((1 + oos_r).resample('YE').prod() - 1 < 0).sum())
    wf     = oos_sh / is_sh if is_sh > 0 else 0.0
    passes = oos_sh > H045_SHARPE
    if oos_sh > best_sh:
        best_sh  = oos_sh
        best_var = tag

    print(f"  {tag:<4} {is_sh:>7.3f} {oos_sh:>8.3f} {o_cagr:>8.1%} {o_mdd:>7.1%} "
          f"{o_neg:>6d} {wf:>6.3f}  {'PASS' if passes else 'fail'}")

    results_all[f'variant_{tag}'] = {
        'is_sharpe': round(is_sh, 3), 'oos_sharpe': round(oos_sh, 3),
        'oos_cagr': round(o_cagr, 3), 'oos_maxdd': round(o_mdd, 3),
        'neg_years': o_neg, 'wf_ratio': round(wf, 3), 'pass_gate': passes,
    }

print(f"\nH045 baseline gate: >{H045_SHARPE}  |  AGG B&H: {agg_sh:.3f}")
any_pass = any(v['pass_gate'] for v in results_all.values())
verdict  = "CONFIRMED" if any_pass else "NOT CONFIRMED"
print(f"Verdict: {verdict} (best variant {best_var}, OOS Sharpe {best_sh:.3f})")

results = {
    "hypothesis": "H335",
    "h045_baseline_sharpe": H045_SHARPE,
    "agg_bh_sharpe": round(agg_sh, 3),
    "variants": results_all,
    "best_variant": best_var,
    "best_oos_sharpe": round(best_sh, 3),
    "verdict": verdict,
}
(RESULT_DIR / "h335_results.json").write_text(json.dumps(results, indent=2))
print(f"Saved → h335_results.json")
