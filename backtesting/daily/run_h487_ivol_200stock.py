'''
H487 — Idiosyncratic Volatility Anomaly (200-stock universe)
==============================================================
Source: "151 Trading Strategies" §3.4 — Low-Volatility Anomaly family
Reference: Ang, Hodrick, Xing, Zhang (JF 2006) "The Cross-Section of
Volatility and Expected Returns" — the IVOL puzzle.

Retest-at-scale: H213 found HIGH idiosyncratic vol OUTPERFORMED (opposite of
Ang et al.) on the concentrated 30-stock mega-cap universe. Analogous signals
have already been retested on the H241 200-stock universe — total realized
vol (H245, NOT CONFIRMED, best OOS Sharpe 0.626) and market beta / BABB
(H248, NOT CONFIRMED) — but idiosyncratic vol specifically has not. This
hypothesis closes that gap using the same "retest prior 30-stock finding at
200-stock scale" pattern established by H241/H243/H245/H248.

IVOL_i(t) = std of residuals from OLS regression of stock monthly returns on
SPY monthly returns over a trailing 3-month window (same formula/window as
H213). Uses the same price cache/panel as H241/H245 plus a separately
fetched SPY monthly series.

Variants:
  H487-A: Long bottom quintile (40) by IVOL — Ang et al. direction (low IVOL)
  H487-B: Long bottom decile (20) by IVOL — Ang et al. direction, concentrated
  H487-C: Long top quintile (40) by IVOL — H213 direction (high IVOL, lottery demand)
  H487-D: IVOL(low) + momentum(high) blend, 0.5/0.5 — mirrors H245-D

IS: 2013-2020  OOS: 2021-2026
Confirm: OOS Sharpe >= 1.5 (200-stock family standard, matches H245/H248 gate)
'''

import warnings; warnings.filterwarnings('ignore')
import sys, json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy import stats

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / 'backtesting' / 'daily'))

from run_h241 import load_prices, build_panel

CACHE_DIR  = WORKSPACE / 'backtesting' / 'cache'
RESULT_DIR = WORKSPACE / 'backtesting' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = pd.Timestamp('2013-01-01')
IS_END    = pd.Timestamp('2020-12-31')
OOS_START = pd.Timestamp('2021-01-01')
OOS_END   = pd.Timestamp('2026-05-31')
TC        = 0.001
IVOL_WINDOW = 3  # months, same as H213


def load_spy_monthly():
    cp = CACHE_DIR / 'h487_SPY_monthly.parquet'
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    raw = yf.download('SPY', start='2012-01-01', end='2026-06-01',
                       auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs('SPY', axis=1, level=1)
    s = raw['Close'].resample('ME').last()
    s.name = 'SPY'
    pd.DataFrame(s).to_parquet(cp)
    return s


def compute_ivol_panel(monthly_ret: pd.DataFrame, spy_ret: pd.Series,
                        window: int = IVOL_WINDOW) -> pd.DataFrame:
    '''
    IVOL at index label `date` uses only returns strictly BEFORE `date`
    (loc-window .. loc-1) — same "as of this date, prior data only" alignment
    convention as build_panel()'s vol_12m/mom columns, so it can be merged
    directly onto the H241 panel without an extra shift.
    '''
    records = []
    for loc in range(window, len(monthly_ret)):
        date = monthly_ret.index[loc]
        slice_stk = monthly_ret.iloc[loc - window: loc]
        slice_spy = spy_ret.reindex(slice_stk.index).dropna()
        if len(slice_spy) < window:
            continue
        row = {}
        for ticker in monthly_ret.columns:
            stk = slice_stk[ticker].reindex(slice_spy.index).dropna()
            spy = slice_spy.reindex(stk.index)
            if len(stk) < window:
                row[ticker] = np.nan
                continue
            slope, intercept, _, _, _ = stats.linregress(spy.values, stk.values)
            resid = stk.values - (intercept + slope * spy.values)
            row[ticker] = float(resid.std() * np.sqrt(12))
        records.append((date, row))
    df = pd.DataFrame([r for _, r in records],
                       index=pd.DatetimeIndex([d for d, _ in records]))
    return df


def run_ivol_strategy(panel, ivol_df, n_long=40, long_low=True, blend_mom=False):
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_set = set()

    for date in dates:
        if date not in ivol_df.index:
            port_rets.append({'date': date, 'ret': 0.0})
            continue
        df_t = panel.loc[date].copy()
        ivol_row = ivol_df.loc[date].dropna()
        df_t = df_t.join(ivol_row.rename('ivol'), how='inner')
        df_t = df_t.dropna(subset=['ivol', 'mom_6_1', 'fwd_ret'])
        if len(df_t) < n_long * 2:
            port_rets.append({'date': date, 'ret': 0.0})
            continue

        if blend_mom:
            n = len(df_t)
            df_t['ivol_rank'] = df_t['ivol'].rank(ascending=True)     # low ivol = good
            df_t['mom_rank']  = df_t['mom_6_1'].rank(ascending=False)  # high mom = good
            df_t['score'] = 0.5 * (df_t['ivol_rank'] / n) + 0.5 * (df_t['mom_rank'] / n)
            selected = df_t.nsmallest(n_long, 'score').index
        elif long_low:
            selected = df_t.nsmallest(n_long, 'ivol').index
        else:
            selected = df_t.nlargest(n_long, 'ivol').index

        sel_set = set(selected)
        turnover = len(sel_set.symmetric_difference(prev_set)) / (2 * n_long)
        tc_drag = turnover * TC
        prev_set = sel_set

        port_ret = df_t.loc[selected, 'fwd_ret'].mean()
        port_rets.append({'date': date, 'ret': port_ret - tc_drag})

    rets = pd.DataFrame(port_rets).set_index('date')['ret']
    rets.index = pd.to_datetime(rets.index)
    return rets


def eval_series(rets, label):
    r_is  = rets[(rets.index >= IS_START)  & (rets.index <= IS_END)].dropna()
    r_oos = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)].dropna()

    def sharpe(r): return (r.mean() / r.std()) * np.sqrt(12) if r.std() > 0 else 0
    def maxdd(r):
        c = (1 + r).cumprod(); return float((c / c.cummax() - 1).min())
    def neg_yrs(r):
        return int((r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1) < 0).sum())
    def annual(r):
        return {str(y): round(float(v) * 100, 1)
                for y, v in r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1).items()}

    ar = annual(r_oos)
    ar_str = ' | '.join(f"{y}:{v:+.1f}%" for y, v in ar.items())
    cumul_oos = float((1 + r_oos).prod())

    print(f"--- {label} ---")
    print(f"  IS  Sharpe={sharpe(r_is):.3f}  Cumul={(1 + r_is).prod():.3f}x  MaxDD={maxdd(r_is):.1%}")
    print(f"  OOS Sharpe={sharpe(r_oos):.3f}  Cumul={cumul_oos:.3f}x  MaxDD={maxdd(r_oos):.1%}  NegYrs={neg_yrs(r_oos)}")
    print(f"  Annual OOS: {ar_str}")

    return {
        'is_sharpe':   round(sharpe(r_is), 3),
        'is_cumul':    round(float((1 + r_is).prod()), 3),
        'oos_sharpe':  round(sharpe(r_oos), 3),
        'oos_cumul':   round(cumul_oos, 3),
        'oos_maxdd':   round(maxdd(r_oos) * 100, 1),
        'oos_neg_yrs': neg_yrs(r_oos),
        'oos_annual':  ar,
    }


def spy_benchmark():
    spy = load_spy_monthly()
    spy_m = spy.pct_change().dropna()
    r = spy_m[(spy_m.index >= OOS_START) & (spy_m.index <= OOS_END)]
    sh = (r.mean() / r.std()) * np.sqrt(12)
    cum = float((1 + r).prod())
    dd = float(((1 + r).cumprod() / ((1 + r).cumprod().cummax()) - 1).min())
    print(f"--- SPY Benchmark ---")
    print(f"  OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")


def main():
    print("=" * 65)
    print("H487 — Idiosyncratic Volatility Anomaly (200-stock universe)")
    print("=" * 65)

    print("Building panel from H241 cache…")
    prices = load_prices()
    panel = build_panel(prices)
    print(f"  Panel rows: {len(panel)}")

    print("Computing IVOL matrix (trailing 3m OLS residuals vs SPY)…")
    monthly_ret = prices.pct_change()
    spy_px = load_spy_monthly()
    spy_ret = spy_px.pct_change().dropna()
    ivol_df = compute_ivol_panel(monthly_ret, spy_ret, window=IVOL_WINDOW)
    print(f"  IVOL matrix: {ivol_df.shape[0]} rows x {ivol_df.shape[1]} cols")

    results = {}

    print()
    r_a = run_ivol_strategy(panel, ivol_df, n_long=40, long_low=True)
    results['H487-A'] = eval_series(r_a, 'H487-A (bottom quintile IVOL, EW)')

    print()
    r_b = run_ivol_strategy(panel, ivol_df, n_long=20, long_low=True)
    results['H487-B'] = eval_series(r_b, 'H487-B (bottom decile IVOL, EW)')

    print()
    r_c = run_ivol_strategy(panel, ivol_df, n_long=40, long_low=False)
    results['H487-C'] = eval_series(r_c, 'H487-C (top quintile IVOL, EW — H213 direction)')

    print()
    r_d = run_ivol_strategy(panel, ivol_df, n_long=40, blend_mom=True)
    results['H487-D'] = eval_series(r_d, 'H487-D (low-IVOL + high-mom blend)')

    print()
    spy_benchmark()

    best_key = max(results, key=lambda k: results[k]['oos_sharpe'])
    best_sh = results[best_key]['oos_sharpe']
    confirmed = best_sh >= 1.5
    print(f"\nCONFIRM CHECK: Best OOS Sharpe {best_sh:.3f} >= 1.5 -> {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"Best variant: {best_key}")

    # Correlation vs H241-A momentum (diversification check)
    panel_oos = panel.loc[
        (panel.index.get_level_values('date') >= OOS_START) &
        (panel.index.get_level_values('date') <= OOS_END)
    ]
    h241_monthly = {}
    for dt, grp in panel_oos.groupby(level='date'):
        grp = grp.dropna(subset=['mom_6_1', 'fwd_ret'])
        h241_monthly[dt] = grp.nlargest(20, 'mom_6_1')['fwd_ret'].mean()
    h241_rets = pd.Series(h241_monthly).sort_index()

    best_rets = {'H487-A': r_a, 'H487-B': r_b, 'H487-C': r_c, 'H487-D': r_d}[best_key]
    aligned = pd.concat([best_rets.rename('h487'), h241_rets.rename('h241')], axis=1).dropna()
    corr_h241 = float(aligned.corr().iloc[0, 1]) if len(aligned) > 12 else float('nan')
    print(f"Corr(best H487, H241-A momentum) OOS: {corr_h241:.3f}")
    results['corr_h241_oos'] = round(corr_h241, 3)

    out = RESULT_DIR / 'h487_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")


if __name__ == '__main__':
    main()
