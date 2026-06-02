'''
H243 — Long/Short Cross-Sectional Momentum (dollar-neutral)
============================================================
H241-A baseline: OOS Sharpe=1.222 (long-only, top-20 of 200 stocks, EW)
H242 confirmed: negative SPY correlation is genuine stock-selection alpha

This test: dollar-neutral L/S portfolio on same signal
  - Long: top quintile (top-40) by 6-1m momentum
  - Short: bottom quintile (bottom-40) by 6-1m momentum
  - Net exposure: 0 (dollar-neutral)
  - Borrow cost: 0.75%/yr on short notional (~0.0625%/month)
  - TC: 0.10% on turnover (both legs)

Variants:
  H243-A: Top/bottom quintile (40 stocks each), equal-weight
  H243-B: Top/bottom quintile, vol-scaled weights
  H243-C: Top/bottom decile (20 stocks each), equal-weight (stronger signal)
  H243-D: Sector-neutral L/S (top-2 long / bottom-2 short per sector)

IS: 2013-2020  OOS: 2021-2026
Confirm: OOS Sharpe >= 1.5 (vs H241-A baseline 1.222)
Key diagnostic: split attribution between long leg and short leg

Reference wiki: wiki/trading/algorithms/long-short-equity.md
'''

import warnings; warnings.filterwarnings('ignore')
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / 'backtesting' / 'cache'
RESULT_DIR = WORKSPACE / 'backtesting' / 'results'

IS_START  = pd.Timestamp('2013-01-01')
IS_END    = pd.Timestamp('2020-12-31')
OOS_START = pd.Timestamp('2021-01-01')
OOS_END   = pd.Timestamp('2026-05-31')
TC        = 0.001   # 0.10% per side on turnover
BORROW_ANNUAL = 0.0075  # 0.75%/yr on short notional
BORROW_MONTHLY = BORROW_ANNUAL / 12

SECTOR_MAP = {
    'AAPL':'IT','MSFT':'IT','NVDA':'IT','AVGO':'IT','AMD':'IT','QCOM':'IT','ORCL':'IT',
    'CRM':'IT','ADBE':'IT','INTC':'IT','TXN':'IT','ACN':'IT','IBM':'IT','AMAT':'IT',
    'LRCX':'IT','MU':'IT','NOW':'IT','INTU':'IT','ADI':'IT','NXPI':'IT','MCHP':'IT',
    'KLAC':'IT','CDNS':'IT','SNPS':'IT','FTNT':'IT','GLW':'IT','HPE':'IT','KEYS':'IT',
    'ZBRA':'IT','JNPR':'IT',
    'AMZN':'CD','TSLA':'CD','HD':'CD','MCD':'CD','NKE':'CD','SBUX':'CD','LOW':'CD',
    'TJX':'CD','F':'CD','GM':'CD','CMG':'CD','BKNG':'CD','ROST':'CD','DRI':'CD',
    'DHI':'CD','LEN':'CD','PHM':'CD','NVR':'CD','TOL':'CD','EXPE':'CD',
    'JPM':'FIN','BAC':'FIN','WFC':'FIN','GS':'FIN','MS':'FIN','C':'FIN','BLK':'FIN',
    'AXP':'FIN','CB':'FIN','PGR':'FIN','MET':'FIN','PRU':'FIN','TRV':'FIN','ICE':'FIN',
    'CME':'FIN','SCHW':'FIN','USB':'FIN','PNC':'FIN','TFC':'FIN','SPGI':'FIN',
    'MCO':'FIN','COF':'FIN','DFS':'FIN','AIG':'FIN','MMC':'FIN',
    'UNH':'HC','LLY':'HC','JNJ':'HC','ABBV':'HC','MRK':'HC','PFE':'HC','TMO':'HC',
    'ABT':'HC','AMGN':'HC','GILD':'HC','MDT':'HC','BMY':'HC','ISRG':'HC','CVS':'HC',
    'CI':'HC','HUM':'HC','ELV':'HC','REGN':'HC','VRTX':'HC','ZBH':'HC','BDX':'HC',
    'BSX':'HC','EW':'HC','DXCM':'HC','HOLX':'HC',
    'WMT':'CS','COST':'CS','PG':'CS','KO':'CS','PEP':'CS','PM':'CS','MO':'CS',
    'MDLZ':'CS','CL':'CS','GIS':'CS','K':'CS','CPB':'CS','HRL':'CS','SJM':'CS','CAG':'CS',
    'XOM':'EN','CVX':'EN','COP':'EN','EOG':'EN','PSX':'EN','VLO':'EN','MPC':'EN',
    'SLB':'EN','HAL':'EN','OXY':'EN','HES':'EN','APA':'EN','DVN':'EN','FANG':'EN','KMI':'EN',
    'HON':'IND','UPS':'IND','RTX':'IND','LMT':'IND','CAT':'IND','GE':'IND','NOC':'IND',
    'BA':'IND','DE':'IND','EMR':'IND','ETN':'IND','ITW':'IND','CTAS':'IND','WM':'IND',
    'RSG':'IND','CSX':'IND','NSC':'IND','UNP':'IND','FDX':'IND','MMM':'IND',
    'LIN':'MAT','APD':'MAT','SHW':'MAT','ECL':'MAT','NEM':'MAT','FCX':'MAT',
    'NUE':'MAT','ALB':'MAT','CF':'MAT','MOS':'MAT',
    'PLD':'RE','AMT':'RE','EQIX':'RE','CCI':'RE','SPG':'RE','O':'RE',
    'DLR':'RE','EXR':'RE','AVB':'RE','EQR':'RE',
    'NEE':'UT','DUK':'UT','SO':'UT','D':'UT','AEP':'UT','EXC':'UT',
    'PCG':'UT','SRE':'UT','XEL':'UT','PPL':'UT',
    'GOOGL':'CS2','META':'CS2','NFLX':'CS2','DIS':'CS2','CMCSA':'CS2','VZ':'CS2',
    'T':'CS2','TMUS':'CS2','CHTR':'CS2','FOXA':'CS2','EA':'CS2','TTWO':'CS2',
    'OMC':'CS2','IPG':'CS2','LDOS':'CS2',
}

def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())
def neg_yrs(r):
    return int((r.groupby(r.index.year).apply(lambda x: (1+x).prod()-1) < 0).sum())

def load_panel() -> pd.DataFrame:
    cache = CACHE_DIR / 'h241_monthly_prices.parquet'
    prices = pd.read_parquet(cache)
    ret = prices.pct_change()
    rows = []
    dates = prices.index
    for i in range(13, len(dates) - 1):
        date = dates[i]
        r1m = ret.iloc[i - 1]
        mom_6_1  = prices.iloc[i-1] / prices.iloc[i-7]  - 1
        vol_12m  = ret.iloc[i-12:i].std() * np.sqrt(12)
        fwd_ret  = ret.iloc[i + 1]
        tickers = prices.columns[prices.iloc[i-1].notna() & prices.iloc[i+1].notna()]
        for t in tickers:
            rows.append({
                'date': date,
                'ticker': t,
                'sector': SECTOR_MAP.get(t, 'OTHER'),
                'fwd_ret': fwd_ret[t],
                'mom_6_1': mom_6_1[t],
                'rev_1m': r1m[t],
                'vol_12m': vol_12m[t],
            })
    df = pd.DataFrame(rows).dropna(subset=['mom_6_1', 'fwd_ret'])
    return df.set_index(['date', 'ticker'])


def run_long_short(panel, n_long=40, n_short=40, vol_scaled=False):
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets, long_rets, short_rets = [], [], []
    prev_weights = {}

    for date in dates:
        df = panel.loc[date].copy()
        signal = df['mom_6_1'].dropna()
        n = len(signal)

        if n < n_long + n_short:
            port_rets.append(0.0)
            long_rets.append(0.0)
            short_rets.append(0.0)
            continue

        ranked = signal.rank(ascending=False)
        longs  = ranked[ranked <= n_long].index
        shorts = ranked[ranked > n - n_short].index

        if vol_scaled:
            lw = 1.0 / (df.loc[longs, 'vol_12m'].replace(0, np.nan).fillna(0.20) + 1e-8)
            sw = 1.0 / (df.loc[shorts, 'vol_12m'].replace(0, np.nan).fillna(0.20) + 1e-8)
            long_w  = (lw / lw.sum()).to_dict()
            short_w = (sw / sw.sum()).to_dict()
        else:
            long_w  = {t: 1.0/n_long  for t in longs}
            short_w = {t: 1.0/n_short for t in shorts}

        # Turnover
        all_cur = set(long_w) | set(short_w)
        all_prev = set(prev_weights)
        turnover = len(all_cur.symmetric_difference(all_prev)) / max(1, 2 * (n_long + n_short))
        tc_drag = turnover * TC
        borrow_drag = 1.0 * BORROW_MONTHLY  # short leg is 100% notional

        fwd = df['fwd_ret']
        lr = sum(long_w.get(t, 0) * fwd.get(t, 0) for t in longs)
        sr = sum(short_w.get(t, 0) * fwd.get(t, 0) for t in shorts)
        ls_ret = lr - sr - tc_drag - borrow_drag

        port_rets.append(ls_ret)
        long_rets.append(lr)
        short_rets.append(sr)
        prev_weights = {**long_w, **{t: -v for t, v in short_w.items()}}

    idx = pd.to_datetime(dates)
    return (pd.Series(port_rets, index=idx),
            pd.Series(long_rets,  index=idx),
            pd.Series(short_rets, index=idx))


def run_sn_long_short(panel, tops_per_sector=2, bottoms_per_sector=2):
    dates = panel.index.get_level_values('date').unique().sort_values()
    port_rets = []
    prev_weights = {}

    for date in dates:
        df = panel.loc[date].copy()
        weights = {}
        n_sectors = df['sector'].nunique()

        for sector, grp in df.groupby('sector'):
            ranked = grp['mom_6_1'].rank(ascending=False)
            n = len(grp)
            if n < tops_per_sector + bottoms_per_sector:
                continue
            longs  = ranked[ranked <= tops_per_sector].index
            shorts = ranked[ranked > n - bottoms_per_sector].index
            sw = 1.0 / n_sectors
            for t in longs:  weights[t] =  sw / tops_per_sector
            for t in shorts: weights[t] = -sw / bottoms_per_sector

        if not weights:
            port_rets.append(0.0)
            continue

        turnover = len(set(weights).symmetric_difference(set(prev_weights))) / max(1, 2*len(weights))
        tc_drag = turnover * TC
        short_notional = sum(abs(w) for w in weights.values() if w < 0)
        borrow_drag = short_notional * BORROW_MONTHLY

        fwd = df['fwd_ret']
        ret = sum(weights.get(t, 0) * fwd.get(t, 0) for t in weights) - tc_drag - borrow_drag
        port_rets.append(ret)
        prev_weights = weights

    return pd.Series(port_rets, index=pd.to_datetime(dates))


def main():
    print('=' * 65)
    print('H243 — Long/Short Cross-Sectional Momentum (dollar-neutral)')
    print('H241-A baseline: OOS Sharpe=1.222, long-only')
    print('=' * 65)

    print('\nLoading panel from H241 cache...')
    panel = load_panel()
    print(f'  Panel: {len(panel):,} stock-months')

    spy_raw = yf.download('SPY', start='2010-01-01', end='2026-05-31',
                          auto_adjust=True, progress=False)['Close']
    if isinstance(spy_raw, pd.DataFrame):
        spy_raw = spy_raw.squeeze()
    spy_ret = spy_raw.resample('ME').last().pct_change().squeeze()
    spy_oos = spy_ret.loc[OOS_START:OOS_END].dropna()

    variants = {
        'H243-A': dict(n_long=40, n_short=40, vol_scaled=False, mode='ls'),
        'H243-B': dict(n_long=40, n_short=40, vol_scaled=True,  mode='ls'),
        'H243-C': dict(n_long=20, n_short=20, vol_scaled=False, mode='ls'),
        'H243-D': dict(mode='sn_ls'),
    }

    results = {}
    for name, cfg in variants.items():
        if cfg['mode'] == 'ls':
            all_ret, long_ret, short_ret = run_long_short(
                panel,
                n_long=cfg['n_long'], n_short=cfg['n_short'],
                vol_scaled=cfg['vol_scaled'],
            )
        else:
            all_ret = run_sn_long_short(panel)
            long_ret = short_ret = None

        is_ret  = all_ret.loc[IS_START:IS_END]
        oos_ret = all_ret.loc[OOS_START:OOS_END]
        aligned_spy = spy_oos.reindex(oos_ret.index).squeeze()
        corr_spy = float(oos_ret.corr(aligned_spy))

        ann_oos = oos_ret.groupby(oos_ret.index.year).apply(lambda x: (1+x).prod()-1)
        ann_str = ' | '.join(f'{y}:{v*100:+.1f}%' for y, v in ann_oos.items())

        print(f'--- Variant {name} ---')
        print(f'  IS  Sharpe={sharpe(is_ret):.3f}  Cumul={cumul(is_ret):.3f}x  MaxDD={maxdd(is_ret)*100:.1f}%')
        print(f'  OOS Sharpe={sharpe(oos_ret):.3f}  Cumul={cumul(oos_ret):.3f}x  MaxDD={maxdd(oos_ret)*100:.1f}%  NegYrs={neg_yrs(oos_ret)}')
        print(f'  Corr(OOS,SPY)={corr_spy:.3f}')
        print(f'  Annual OOS: {ann_str}')
        if long_ret is not None:
            lr_oos = long_ret.loc[OOS_START:OOS_END]
            sr_oos = short_ret.loc[OOS_START:OOS_END]
            print(f'  Long-leg OOS Sharpe={sharpe(lr_oos):.3f}  Short-leg OOS Sharpe={sharpe(sr_oos):.3f} (should be negative = short wins)')
        print()

        results[name] = {
            'is_sharpe':    round(sharpe(is_ret), 3),
            'oos_sharpe':   round(sharpe(oos_ret), 3),
            'oos_cumul':    round(cumul(oos_ret), 3),
            'oos_maxdd':    round(maxdd(oos_ret)*100, 1),
            'oos_neg_yrs':  neg_yrs(oos_ret),
            'corr_spy_oos': round(corr_spy, 3),
        }

    print('--- SPY Benchmark ---')
    print(f'  OOS Sharpe={sharpe(spy_oos):.3f}  Cumul={cumul(spy_oos):.3f}x  MaxDD={maxdd(spy_oos)*100:.1f}%')

    best_sharpe = max(v['oos_sharpe'] for v in results.values())
    confirmed = best_sharpe >= 1.5
    best_name = max(results, key=lambda k: results[k]['oos_sharpe'])
    print(f'\nCONFIRM CHECK: Best OOS Sharpe {best_sharpe:.3f} >= 1.5 -> {"CONFIRMED" if confirmed else "NOT CONFIRMED"}')
    print(f'Best variant: {best_name}')

    out = RESULT_DIR / 'h243_results.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved: {out}')


if __name__ == '__main__':
    main()
