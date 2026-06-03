'''
H245 — Low-Volatility Anomaly (long-only, 200-stock universe)
=============================================================
Source: "151 Trading Strategies" §3.4 — Low-Volatility Anomaly
Reference: Baker, Bradley & Wurgler (2011); Blitz & van Vliet (2007);
           Frazzini & Pedersen (2014) AQR BAB factor

Signal: 12-month realized monthly return volatility (annualized).
Long the lowest-vol stocks (bottom quintile) in the 200-stock universe.
Uses the same price cache and panel as H241.

Variants:
  H245-A: Bottom quintile (40 stocks) by vol_12m, equal-weight
  H245-B: Bottom decile (20 stocks) by vol_12m, equal-weight
  H245-C: Bottom quintile, inverse-vol weighted
  H245-D: Vol-momentum blend — low vol + high mom (0.5 each)

IS: 2013-2020  OOS: 2021-2026
Confirm: OOS Sharpe >= 1.5
'''

import warnings; warnings.filterwarnings('ignore')
import sys, json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / 'backtesting' / 'daily'))

from run_h241 import load_prices, build_panel

RESULT_DIR = WORKSPACE / 'backtesting' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = pd.Timestamp('2013-01-01')
IS_END    = pd.Timestamp('2020-12-31')
OOS_START = pd.Timestamp('2021-01-01')
OOS_END   = pd.Timestamp('2026-05-31')
TC        = 0.001

def run_low_vol(panel, n_long=40, inv_vol_weighted=False, blend_mom=False):
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_set = set()

    for date in dates:
        df_t = panel.loc[date].copy()
        df_t = df_t.dropna(subset=['vol_12m', 'mom_6_1', 'fwd_ret'])
        if len(df_t) < n_long * 2:
            port_rets.append({'date': date, 'ret': 0.0})
            continue

        if blend_mom:
            n = len(df_t)
            df_t['vol_rank'] = df_t['vol_12m'].rank(ascending=True)
            df_t['mom_rank'] = df_t['mom_6_1'].rank(ascending=False)
            df_t['score']    = 0.5*(df_t['vol_rank']/n) + 0.5*(df_t['mom_rank']/n)
            selected = df_t.nsmallest(n_long, 'score').index
        else:
            selected = df_t.nsmallest(n_long, 'vol_12m').index

        sel_set = set(selected)
        turnover = len(sel_set.symmetric_difference(prev_set)) / (2 * n_long)
        tc_drag = turnover * TC
        prev_set = sel_set

        sel_data = df_t.loc[selected]
        if inv_vol_weighted:
            inv_v = 1.0 / (sel_data['vol_12m'] + 1e-8)
            w = inv_v / inv_v.sum()
            port_ret = (w * sel_data['fwd_ret']).sum()
        else:
            port_ret = sel_data['fwd_ret'].mean()

        port_rets.append({'date': date, 'ret': port_ret - tc_drag})

    rets = pd.DataFrame(port_rets).set_index('date')['ret']
    rets.index = pd.to_datetime(rets.index)
    return rets

def eval_series(rets, label):
    r_is  = rets[(rets.index >= IS_START)  & (rets.index <= IS_END)].dropna()
    r_oos = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)].dropna()

    def sharpe(r): return (r.mean()/r.std())*np.sqrt(12) if r.std() > 0 else 0
    def maxdd(r):
        c = (1+r).cumprod(); return float((c/c.cummax()-1).min())
    def neg_yrs(r):
        return int((r.groupby(r.index.year).apply(lambda x:(1+x).prod()-1)<0).sum())
    def annual(r):
        return {str(y):round(float(v)*100,1)
                for y,v in r.groupby(r.index.year).apply(lambda x:(1+x).prod()-1).items()}

    ar = annual(r_oos)
    ar_str = ' | '.join(f"{y}:{v:+.1f}%" for y,v in ar.items())
    cumul_oos = float((1+r_oos).prod())

    print(f"--- {label} ---")
    print(f"  IS  Sharpe={sharpe(r_is):.3f}  Cumul={(1+r_is).prod():.3f}x  MaxDD={maxdd(r_is):.1%}")
    print(f"  OOS Sharpe={sharpe(r_oos):.3f}  Cumul={cumul_oos:.3f}x  MaxDD={maxdd(r_oos):.1%}  NegYrs={neg_yrs(r_oos)}")
    print(f"  Annual OOS: {ar_str}")

    return {
        'is_sharpe':   round(sharpe(r_is),3),
        'is_cumul':    round(float((1+r_is).prod()),3),
        'oos_sharpe':  round(sharpe(r_oos),3),
        'oos_cumul':   round(cumul_oos,3),
        'oos_maxdd':   round(maxdd(r_oos)*100,1),
        'oos_neg_yrs': neg_yrs(r_oos),
        'oos_annual':  ar,
    }

def spy_benchmark():
    spy = yf.download('SPY', start='2012-01-01', end='2026-06-01',
                      auto_adjust=True, progress=False)['Close']
    if isinstance(spy, pd.DataFrame): spy = spy.squeeze()
    spy_m = spy.resample('ME').last().pct_change().dropna()
    r = spy_m[(spy_m.index >= OOS_START) & (spy_m.index <= OOS_END)]
    sh = (r.mean()/r.std())*np.sqrt(12)
    cum = float((1+r).prod())
    dd  = float(((1+r).cumprod()/((1+r).cumprod().cummax())-1).min())
    print(f"--- SPY Benchmark ---")
    print(f"  OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")

def main():
    print("="*65)
    print("H245 — Low-Volatility Anomaly (200-stock universe)")
    print("="*65)

    print("Building panel from H241 cache…")
    prices = load_prices()
    panel  = build_panel(prices)
    print(f"  Panel rows: {len(panel)}")

    results = {}

    print()
    r_a = run_low_vol(panel, n_long=40)
    results['H245-A'] = eval_series(r_a, 'H245-A (bottom quintile EW)')

    print()
    r_b = run_low_vol(panel, n_long=20)
    results['H245-B'] = eval_series(r_b, 'H245-B (bottom decile EW)')

    print()
    r_c = run_low_vol(panel, n_long=40, inv_vol_weighted=True)
    results['H245-C'] = eval_series(r_c, 'H245-C (bottom quintile inv-vol weighted)')

    print()
    r_d = run_low_vol(panel, n_long=40, blend_mom=True)
    results['H245-D'] = eval_series(r_d, 'H245-D (vol-momentum blend)')

    print()
    spy_benchmark()

    best_key = max(results, key=lambda k: results[k]['oos_sharpe'])
    best_sh  = results[best_key]['oos_sharpe']
    confirmed = best_sh >= 1.5
    print(f"\nCONFIRM CHECK: Best OOS Sharpe {best_sh:.3f} >= 1.5 -> {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"Best variant: {best_key}")

    # Correlation vs H241-A momentum (portfolio diversification check)
    panel_oos = panel.loc[
        (panel.index.get_level_values('date') >= OOS_START) &
        (panel.index.get_level_values('date') <= OOS_END)
    ]
    h241_monthly = {}
    for dt, grp in panel_oos.groupby(level='date'):
        grp = grp.dropna(subset=['mom_6_1','fwd_ret'])
        h241_monthly[dt] = grp.nlargest(20,'mom_6_1')['fwd_ret'].mean()
    h241_rets = pd.Series(h241_monthly).sort_index()

    best_rets = {'H245-A':r_a,'H245-B':r_b,'H245-C':r_c,'H245-D':r_d}[best_key]
    aligned = pd.concat([best_rets.rename('h245'), h241_rets.rename('h241')], axis=1).dropna()
    corr_h241 = float(aligned.corr().iloc[0,1]) if len(aligned) > 12 else float('nan')
    print(f"Corr(best H245, H241-A momentum) OOS: {corr_h241:.3f}")
    results['corr_h241_oos'] = round(corr_h241, 3)

    out = RESULT_DIR / 'h245_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")

if __name__ == '__main__':
    main()
