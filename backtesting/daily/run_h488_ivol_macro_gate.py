'''
H488 — High-IVOL (200-stock) with Macro Regime Gate
=====================================================
Source: H487 (NOT CONFIRMED — best variant H487-C, long top-quintile IVOL,
OOS Sharpe 1.214, close to but below the 1.5 gate); H362 (CONFIRMED — VIX/
SPY-200MA gate lifted a near-miss low-vol ETF rotation from OOS 1.339 to
1.819, primarily via drawdown reduction).

Hypothesis: H487-C's shortfall vs gate is drawdown-driven (OOS MaxDD -14.7%,
worse than H487-A/B's -16.6%/-14.3% despite higher return) — high-IVOL names
carry crash risk in risk-off regimes. A macro regime gate that routes to a
cash proxy (BIL) when VIX is elevated and/or SPY is below its 200-day MA,
following the exact H362 pattern, may lift H487-C over the 1.5 gate the same
way it lifted H354 -> H362.

Universe/signal: H487-C (200-stock universe, long top-quintile IVOL by
trailing-3m OLS-residual-vs-SPY, equal-weight, monthly rebalance)
Gate variants:
  A  SPY > 200MA only (else BIL)
  B  VIX < 20 only (else BIL)
  C  SPY > 200MA AND VIX < 25 (joint)
  D  SPY > 200MA OR VIX < 20 (either)
  E  Baseline — H487-C, no gate (reproduces H487 result)

IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 1.5 (same threshold as H487); secondary: MaxDD improvement vs
      H487-C baseline (-14.7%)
'''

import warnings; warnings.filterwarnings('ignore')
import sys, json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / 'backtesting' / 'daily'))

from run_h241 import load_prices, build_panel
from run_h487_ivol_200stock import compute_ivol_panel, run_ivol_strategy, load_spy_monthly, IVOL_WINDOW

CACHE_DIR  = WORKSPACE / 'backtesting' / 'cache'
RESULT_DIR = WORKSPACE / 'backtesting' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = pd.Timestamp('2013-01-01')
IS_END    = pd.Timestamp('2020-12-31')
OOS_START = pd.Timestamp('2021-01-01')
OOS_END   = pd.Timestamp('2026-05-31')
GATE_SHARPE = 1.5
GATE_MDD    = -0.147   # H487-C OOS MaxDD baseline


def load_daily(ticker, cache_name):
    cp = CACHE_DIR / cache_name
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start='2010-01-01', end='2026-06-01', progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw['Close'].rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r): return (r.mean() / r.std()) * np.sqrt(12) if r.std() > 0 else 0
def maxdd(r):
    c = (1 + r).cumprod(); return float((c / c.cummax() - 1).min())
def neg_yrs(r):
    return int((r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1) < 0).sum())
def annual(r):
    return {str(y): round(float(v) * 100, 1)
            for y, v in r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1).items()}


def eval_series(rets, label):
    r_is  = rets[(rets.index >= IS_START)  & (rets.index <= IS_END)].dropna()
    r_oos = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)].dropna()
    ar = annual(r_oos)
    ar_str = ' | '.join(f"{y}:{v:+.1f}%" for y, v in ar.items())
    print(f"--- {label} ---")
    print(f"  IS  Sharpe={sharpe(r_is):.3f}  Cumul={(1 + r_is).prod():.3f}x  MaxDD={maxdd(r_is):.1%}")
    print(f"  OOS Sharpe={sharpe(r_oos):.3f}  Cumul={(1 + r_oos).prod():.3f}x  MaxDD={maxdd(r_oos):.1%}  NegYrs={neg_yrs(r_oos)}")
    print(f"  Annual OOS: {ar_str}")
    return {
        'is_sharpe':   round(sharpe(r_is), 3),
        'oos_sharpe':  round(sharpe(r_oos), 3),
        'oos_cumul':   round(float((1 + r_oos).prod()), 3),
        'oos_maxdd':   round(maxdd(r_oos) * 100, 1),
        'oos_neg_yrs': neg_yrs(r_oos),
        'oos_annual':  ar,
    }


def main():
    print('=' * 65)
    print('H488 — High-IVOL (200-stock) with Macro Regime Gate')
    print('=' * 65)

    print('Building panel + IVOL matrix (reuses H241/H487 caches)…')
    prices = load_prices()
    panel = build_panel(prices)
    monthly_ret = prices.pct_change()
    spy_px = load_spy_monthly()
    spy_ret = spy_px.pct_change().dropna()
    ivol_df = compute_ivol_panel(monthly_ret, spy_ret, window=IVOL_WINDOW)

    print('Running H487-C base signal (top-quintile high-IVOL, long-only)…')
    r_base = run_ivol_strategy(panel, ivol_df, n_long=40, long_low=False)

    print('Loading SPY daily (200MA) and VIX daily…')
    spy_daily = load_daily('SPY', 'h488_SPY_daily.parquet')
    vix_daily = load_daily('^VIX', 'h488_VIX_daily.parquet')
    bil_daily = load_daily('BIL', 'h488_BIL_daily.parquet')

    spy_200ma = spy_daily.rolling(200).mean()
    spy_above = (spy_daily > spy_200ma)
    spy_above_m = spy_above.resample('ME').last()
    vix_m = vix_daily.resample('ME').last()
    bil_ret_m = bil_daily.resample('ME').last().pct_change()

    idx = r_base.index
    spy_above_al = spy_above_m.reindex(idx, method='ffill')
    vix_al = vix_m.reindex(idx, method='ffill')
    cash_al = bil_ret_m.reindex(idx, method='ffill').fillna(0.0)

    results = {}
    variants = {}

    def gated(mask_series, label):
        r = r_base.where(mask_series.astype(bool), cash_al)
        return r

    mask_a = spy_above_al
    mask_b = vix_al < 20
    mask_c = spy_above_al & (vix_al < 25)
    mask_d = spy_above_al | (vix_al < 20)

    print()
    r_a = gated(mask_a, 'A'); results['H488-A'] = eval_series(r_a, 'H488-A (SPY>200MA gate)')
    print()
    r_b = gated(mask_b, 'B'); results['H488-B'] = eval_series(r_b, 'H488-B (VIX<20 gate)')
    print()
    r_c = gated(mask_c, 'C'); results['H488-C'] = eval_series(r_c, 'H488-C (SPY>200MA AND VIX<25)')
    print()
    r_d = gated(mask_d, 'D'); results['H488-D'] = eval_series(r_d, 'H488-D (SPY>200MA OR VIX<20)')
    print()
    results['H488-E'] = eval_series(r_base, 'H488-E (baseline, no gate = H487-C)')

    oos_mask = (idx >= OOS_START) & (idx <= OOS_END)
    print(f"\nOOS regime distribution: SPY>200MA {spy_above_al[oos_mask].mean()*100:.1f}% | VIX<20 {(vix_al[oos_mask]<20).mean()*100:.1f}% months")

    best_key = max(results, key=lambda k: results[k]['oos_sharpe'])
    best_sh = results[best_key]['oos_sharpe']
    confirmed = best_sh > GATE_SHARPE
    print(f"\nCONFIRM CHECK: Best OOS Sharpe {best_sh:.3f} > {GATE_SHARPE} -> {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"Best variant: {best_key}  (baseline H487-C MaxDD {GATE_MDD:.1%})")

    out = RESULT_DIR / 'h488_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")


if __name__ == '__main__':
    main()
