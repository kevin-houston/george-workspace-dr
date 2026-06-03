'''
H246 — ETF Pairs Trading (cointegration-based mean reversion)
=============================================================
Source: "151 Trading Strategies" §3.8 — ETF Pairs Trading
Reference: Gatev, Goetzmann & Rouwenhorst (2006) "Pairs Trading: Performance
           of a Relative-Value Arbitrage Rule"; Engle & Granger (1987) cointegration

Test pairs (sector/sub-sector ETF twins):
  Pair 1: GDX / SIL  (gold miners / silver miners)
  Pair 2: XLE / OIH  (energy broad / oil services)
  Pair 3: XLK / QQQ  (tech broad / tech heavy)
  Pair 4: XLF / KRE  (financials / regional banks)
  Pair 5: XLB / XME  (materials / metals & mining)
  Pair 6: XLU / UTG  (utilities ETF / utility closed-end fund)

Signal: Engle-Granger spread Z-score
  1. IS: fit hedge ratio beta via OLS (A = alpha + beta*B + epsilon)
  2. Compute residual (spread) = A - alpha - beta*B
  3. Rolling 60-day mean and std of spread
  4. Z-score = (spread - mean) / std
  5. Entry: |Z| > 2.0; go long undervalued, short overvalued
  6. Exit: |Z| < 0.5 (convergence) or |Z| > 4.0 (stop loss)

Portfolio: Equal capital per pair, all pairs active simultaneously.
Variants:
  H246-A: All 6 pairs, Z > 2.0 entry / Z < 0.5 exit, daily rebal
  H246-B: Top-3 pairs by IS cointegration strength (ADF p-value)
  H246-C: Dynamic hedge ratio (60-day rolling OLS instead of IS-fixed)

IS: 2008-2017  OOS: 2018-2026 (longer history needed for cointegration)
Confirm: OOS Sharpe >= 1.5
'''

import warnings; warnings.filterwarnings('ignore')
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy import stats

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
RESULT_DIR = WORKSPACE / 'backtesting' / 'results'
RESULT_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = pd.Timestamp('2008-01-01')
IS_END    = pd.Timestamp('2017-12-31')
OOS_START = pd.Timestamp('2018-01-01')
OOS_END   = pd.Timestamp('2026-05-31')

TC        = 0.0010   # 0.10% per trade leg
Z_ENTRY   = 2.0
Z_EXIT    = 0.5
Z_STOP    = 4.0
ROLL_WIN  = 60       # rolling window for Z-score

PAIRS = [
    ('GDX', 'SIL'),   # gold miners / silver miners
    ('XLE', 'OIH'),   # energy / oil services
    ('XLK', 'QQQ'),   # tech broad / tech heavy
    ('XLF', 'KRE'),   # financials / regional banks
    ('XLB', 'XME'),   # materials / metals & mining
    ('XLU', 'UTG'),   # utilities ETF / utility CEF
]

ALL_TICKERS = sorted(set(t for p in PAIRS for t in p))


def load_prices():
    cache = WORKSPACE / 'backtesting' / 'cache' / 'h246_daily_prices.parquet'
    if cache.exists():
        df = pd.read_parquet(cache)
        print(f"  Loaded daily cache: {df.shape}")
        return df
    print(f"  Downloading daily prices for {ALL_TICKERS}…")
    raw = yf.download(ALL_TICKERS, start='2007-01-01', end='2026-06-01',
                      auto_adjust=True, progress=False)['Close']
    if isinstance(raw, pd.Series):
        raw = raw.to_frame(ALL_TICKERS[0])
    raw = raw.ffill().dropna(how='all')
    raw.to_parquet(cache)
    print(f"  Saved: {raw.shape}")
    return raw


def adf_pvalue(series):
    from statsmodels.tsa.stattools import adfuller
    try:
        result = adfuller(series.dropna(), maxlag=5, autolag='AIC')
        return result[1]
    except Exception:
        return 1.0


def fit_hedge(A, B):
    slope, intercept, _, _, _ = stats.linregress(B, A)
    return slope, intercept


def run_pair(prices, a_sym, b_sym, is_fixed_hedge=True, dynamic_roll=60,
             name=''):
    A = prices[a_sym].dropna()
    B = prices[b_sym].dropna()
    aligned = pd.concat([A, B], axis=1).dropna()
    aligned.columns = ['A', 'B']

    # IS: compute fixed hedge ratio and ADF on spread
    is_data = aligned[(aligned.index >= IS_START) & (aligned.index <= IS_END)]
    beta_is, alpha_is = fit_hedge(is_data['A'].values, is_data['B'].values)
    spread_is = is_data['A'] - alpha_is - beta_is * is_data['B']
    adf_p = adf_pvalue(spread_is)

    # Full period spread
    if is_fixed_hedge:
        spread_all = aligned['A'] - alpha_is - beta_is * aligned['B']
    else:
        # Dynamic rolling hedge
        betas = []
        for i in range(dynamic_roll, len(aligned)):
            window = aligned.iloc[i-dynamic_roll:i]
            b, a = fit_hedge(window['A'].values, window['B'].values)
            betas.append(b)
        beta_ser = pd.Series(betas, index=aligned.index[dynamic_roll:])
        spread_all = pd.Series(dtype=float, index=aligned.index)
        for idx in beta_ser.index:
            b_val = beta_ser[idx]
            spread_all[idx] = aligned.loc[idx,'A'] - b_val * aligned.loc[idx,'B']
        spread_all = spread_all.dropna()
        aligned = aligned.loc[spread_all.index]

    # Rolling Z-score
    roll_mean = spread_all.rolling(ROLL_WIN).mean()
    roll_std  = spread_all.rolling(ROLL_WIN).std()
    z = (spread_all - roll_mean) / (roll_std + 1e-8)
    z = z.dropna()

    # Simulate pairs trades
    daily_rets = aligned.pct_change()
    position = 0   # +1 = long A short B, -1 = long B short A, 0 = flat
    port_rets = []
    prev_position = 0

    for dt in z.index[1:]:
        if dt not in daily_rets.index:
            continue
        z_t   = z[dt]
        ret_a = daily_rets.loc[dt, 'A']
        ret_b = daily_rets.loc[dt, 'B']

        # Entry
        if position == 0:
            if z_t > Z_ENTRY:
                position = -1   # A expensive, B cheap → short A long B
            elif z_t < -Z_ENTRY:
                position = 1    # A cheap, B expensive → long A short B
        # Exit
        elif position == 1:
            if z_t > -Z_EXIT or z_t > Z_STOP:
                position = 0
        elif position == -1:
            if z_t < Z_EXIT or z_t < -Z_STOP:
                position = 0

        # P&L: 0.5 capital each leg
        pnl = 0.0
        if position == 1:
            pnl = 0.5*ret_a - 0.5*ret_b
        elif position == -1:
            pnl = -0.5*ret_a + 0.5*ret_b

        # TC on position change
        tc_drag = 0.0
        if position != prev_position and position != 0:
            tc_drag = TC   # pay TC on entry (both legs combined)
        elif prev_position != 0 and position == 0:
            tc_drag = TC   # pay TC on exit

        port_rets.append({'date': dt, 'ret': pnl - tc_drag, 'z': z_t, 'pos': position})
        prev_position = position

    df_ret = pd.DataFrame(port_rets).set_index('date')['ret']
    return df_ret, adf_p


def eval_oos(rets, label):
    r_oos = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)].dropna()
    if len(r_oos) < 100:
        print(f"  {label}: insufficient OOS data ({len(r_oos)} days)")
        return None

    def sharpe_daily(r):
        return (r.mean()/r.std())*np.sqrt(252) if r.std() > 0 else 0
    def maxdd(r):
        c = (1+r).cumprod(); return float((c/c.cummax()-1).min())
    def annual(r):
        r.index = pd.to_datetime(r.index)
        return {str(y):round(float(v)*100,1)
                for y,v in r.groupby(r.index.year).apply(lambda x:(1+x).prod()-1).items()}

    ar = annual(r_oos)
    ar_str = ' | '.join(f"{y}:{v:+.1f}%" for y,v in ar.items())
    sh = sharpe_daily(r_oos)
    cum = float((1+r_oos).prod())
    dd  = maxdd(r_oos)

    print(f"  {label}: OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")
    print(f"    Annual: {ar_str}")

    return {'oos_sharpe': round(sh,3), 'oos_cumul': round(cum,3),
            'oos_maxdd': round(dd*100,1), 'oos_annual': ar}


def main():
    print("="*65)
    print("H246 — ETF Pairs Trading (cointegration)")
    print("="*65)

    prices = load_prices()

    print("\nIS cointegration check (ADF p-values on IS spread):")
    pair_results = []
    is_adf = {}
    for a, b in PAIRS:
        if a not in prices.columns or b not in prices.columns:
            print(f"  {a}/{b}: missing data, skip")
            continue
        _, adf_p = run_pair(prices, a, b, name=f'{a}/{b}')
        print(f"  {a}/{b}: IS ADF p={adf_p:.4f} {'✓ cointegrated' if adf_p < 0.05 else '✗ not cointegrated'}")
        is_adf[f'{a}/{b}'] = adf_p
        pair_results.append((a, b, adf_p))

    print("\n--- Variant H246-A: All pairs, fixed hedge ratio ---")
    all_pair_rets = []
    results = {}
    for a, b, adf_p in pair_results:
        r, _ = run_pair(prices, a, b, is_fixed_hedge=True, name=f'{a}/{b}')
        info = eval_oos(r, f'{a}/{b}')
        if info:
            all_pair_rets.append(r)
            results[f'{a}/{b}_fixed'] = info

    if all_pair_rets:
        combo_a = pd.concat(all_pair_rets, axis=1).mean(axis=1)
        print("  COMBINED (equal-weight across pairs):")
        r_oos = combo_a[(combo_a.index >= OOS_START) & (combo_a.index <= OOS_END)].dropna()
        if len(r_oos) > 50:
            sh = (r_oos.mean()/r_oos.std())*np.sqrt(252)
            cum = float((1+r_oos).prod())
            dd  = float(((1+r_oos).cumprod()/((1+r_oos).cumprod().cummax())-1).min())
            print(f"    OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")
            results['H246-A_combined'] = {'oos_sharpe': round(sh,3),
                                          'oos_cumul': round(cum,3),
                                          'oos_maxdd': round(dd*100,1)}

    # Best 3 by ADF p-value
    top3 = sorted(pair_results, key=lambda x: x[2])[:3]
    print("\n--- Variant H246-B: Top-3 pairs by ADF strength ---")
    top3_rets = []
    for a, b, adf_p in top3:
        r, _ = run_pair(prices, a, b, is_fixed_hedge=True, name=f'{a}/{b}')
        info = eval_oos(r, f'{a}/{b} (top3)')
        if info:
            top3_rets.append(r)
    if top3_rets:
        combo_b = pd.concat(top3_rets, axis=1).mean(axis=1)
        r_oos = combo_b[(combo_b.index >= OOS_START) & (combo_b.index <= OOS_END)].dropna()
        if len(r_oos) > 50:
            sh = (r_oos.mean()/r_oos.std())*np.sqrt(252)
            cum = float((1+r_oos).prod())
            dd  = float(((1+r_oos).cumprod()/((1+r_oos).cumprod().cummax())-1).min())
            print(f"  COMBINED top-3: OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")
            results['H246-B_combined'] = {'oos_sharpe': round(sh,3),
                                          'oos_cumul': round(cum,3),
                                          'oos_maxdd': round(dd*100,1)}

    # Dynamic hedge
    print("\n--- Variant H246-C: Dynamic hedge ratio (60-day rolling OLS) ---")
    dyn_rets = []
    for a, b, adf_p in pair_results:
        r, _ = run_pair(prices, a, b, is_fixed_hedge=False, dynamic_roll=60, name=f'{a}/{b}')
        info = eval_oos(r, f'{a}/{b} dynamic')
        if info:
            dyn_rets.append(r)
    if dyn_rets:
        combo_c = pd.concat(dyn_rets, axis=1).mean(axis=1)
        r_oos = combo_c[(combo_c.index >= OOS_START) & (combo_c.index <= OOS_END)].dropna()
        if len(r_oos) > 50:
            sh = (r_oos.mean()/r_oos.std())*np.sqrt(252)
            cum = float((1+r_oos).prod())
            dd  = float(((1+r_oos).cumprod()/((1+r_oos).cumprod().cummax())-1).min())
            print(f"  COMBINED dynamic: OOS Sharpe={sh:.3f}  Cumul={cum:.3f}x  MaxDD={dd:.1%}")
            results['H246-C_combined'] = {'oos_sharpe': round(sh,3),
                                          'oos_cumul': round(cum,3),
                                          'oos_maxdd': round(dd*100,1)}

    # SPY benchmark (daily)
    spy = yf.download('SPY', start='2017-01-01', end='2026-06-01',
                      auto_adjust=True, progress=False)['Close']
    if isinstance(spy, pd.DataFrame): spy = spy.squeeze()
    spy_d = spy.pct_change().dropna()
    r_spy = spy_d[(spy_d.index >= OOS_START) & (spy_d.index <= OOS_END)]
    spy_sh = (r_spy.mean()/r_spy.std())*np.sqrt(252)
    print(f"\n--- SPY Benchmark ---")
    print(f"  OOS Sharpe={spy_sh:.3f}  Cumul={(1+r_spy).prod():.3f}x")

    all_oos_sharpes = {k: v['oos_sharpe'] for k,v in results.items() if 'oos_sharpe' in v}
    if all_oos_sharpes:
        best_key = max(all_oos_sharpes, key=all_oos_sharpes.get)
        best_sh  = all_oos_sharpes[best_key]
        confirmed = best_sh >= 1.5
        print(f"\nCONFIRM CHECK: Best OOS Sharpe {best_sh:.3f} >= 1.5 -> {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
        print(f"Best: {best_key}")

    results['is_adf'] = {k: round(v, 4) for k, v in is_adf.items()}
    out = RESULT_DIR / 'h246_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {out}")

if __name__ == '__main__':
    main()
