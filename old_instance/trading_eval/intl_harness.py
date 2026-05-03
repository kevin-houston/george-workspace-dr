"""
International Equity Strategy Evaluation Harness
Karpathy autoresearch loop - International Equity ETFs
"""
import sys
sys.path.insert(0, '/tmp/eval_deps_intl')

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

# ─── Universe ───────────────────────────────────────────────────────────────
DEVELOPED = ['EWJ', 'EWG', 'EWU', 'EWC', 'EWA', 'EWQ', 'EWI', 'EWP', 'EWD', 'EWH']
EMERGING  = ['EEM', 'FXI', 'EWZ', 'INDA', 'EWY', 'EWW', 'EWT', 'TUR']
BENCHMARKS = ['SPY', 'VEA', 'VWO', 'EFA', 'TLT', 'UUP']
ALL_TICKERS = sorted(set(DEVELOPED + EMERGING + BENCHMARKS))

COUNTRY_NAMES = {
    'EWJ':'Japan','EWG':'Germany','EWU':'UK','EWC':'Canada','EWA':'Australia',
    'EWQ':'France','EWI':'Italy','EWP':'Spain','EWD':'Sweden','EWH':'Hong Kong',
    'EEM':'EM Broad','FXI':'China','EWZ':'Brazil','INDA':'India','EWY':'Korea',
    'EWW':'Mexico','EWT':'Taiwan','TUR':'Turkey',
    'SPY':'US','VEA':'Dev ex-US','VWO':'Emerging','EFA':'EAFE','TLT':'US Bonds','UUP':'USD'
}

START = '2015-01-01'
END   = '2025-01-01'

# ─── Helpers ─────────────────────────────────────────────────────────────────
def fetch_prices(tickers, start=START, end=END):
    print(f"Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw['Close']
    else:
        prices = raw[['Close']] if 'Close' in raw.columns else raw
    prices = prices.dropna(how='all')
    missing = [t for t in tickers if t not in prices.columns or prices[t].isna().all()]
    if missing:
        print(f"  Missing/empty tickers: {missing}")
    return prices

def returns(prices):
    return prices.pct_change().dropna(how='all')

def sharpe(rets, periods=252):
    ann_ret = rets.mean() * periods
    ann_std = rets.std() * np.sqrt(periods)
    return float(ann_ret / ann_std) if ann_std > 0 else 0.0

def cagr(rets, periods=252):
    n = len(rets)
    total = (1 + rets).prod()
    years = n / periods
    return float(total ** (1/years) - 1) if years > 0 else 0.0

def max_drawdown(rets):
    cum = (1 + rets).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    return float(dd.min())

def spy_corr(strat_rets, spy_rets):
    aligned = strat_rets.align(spy_rets, join='inner')
    if len(aligned[0]) < 20:
        return float('nan')
    return float(aligned[0].corr(aligned[1]))

def metrics(rets, spy_rets):
    rets = rets.dropna()
    return {
        'sharpe':  round(sharpe(rets), 3),
        'cagr':    round(cagr(rets) * 100, 2),
        'max_dd':  round(max_drawdown(rets) * 100, 2),
        'spy_corr':round(spy_corr(rets, spy_rets), 3),
        'n_days':  len(rets)
    }

def monthly_reindex(prices):
    """Return last business day of each month prices."""
    return prices.resample('ME').last()

# ─── Strategy 1: Cross-Country Momentum ──────────────────────────────────────
def strategy_cross_country_momentum(prices, spy_rets):
    """12-1 month momentum: long top 3, short bottom 3, monthly rebalance."""
    universe = [t for t in DEVELOPED + EMERGING if t in prices.columns]
    monthly = monthly_reindex(prices[universe])
    daily_ret = returns(prices[universe])

    portfolio_rets = []
    dates = monthly.index

    for i in range(13, len(dates)):
        d_start = dates[i-13]
        d_skip  = dates[i-2]
        d_end   = dates[i-1]
        d_trade = dates[i]

        # 12-1 momentum
        mom = {}
        for t in universe:
            try:
                r_12 = monthly[t].loc[d_end] / monthly[t].loc[d_start] - 1
                r_1  = monthly[t].loc[d_end] / monthly[t].loc[d_skip] - 1
                mom[t] = r_12 - r_1
            except Exception:
                pass

        if len(mom) < 6:
            continue

        ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)
        longs  = [t for t, _ in ranked[:3]]
        shorts = [t for t, _ in ranked[-3:]]

        # Get next month daily returns
        mask = (daily_ret.index > d_trade) & (daily_ret.index <= (dates[i+1] if i+1 < len(dates) else dates[-1]))
        period_rets = daily_ret.loc[mask]

        if period_rets.empty:
            continue

        long_ret  = period_rets[longs].mean(axis=1)
        short_ret = period_rets[shorts].mean(axis=1)
        port_ret  = long_ret - short_ret
        portfolio_rets.append(port_ret)

    if not portfolio_rets:
        return pd.Series(dtype=float), {}

    port = pd.concat(portfolio_rets).sort_index()
    port = port[~port.index.duplicated()]
    m = metrics(port, spy_rets)
    m['description'] = 'Long top-3 / Short bottom-3 12-1mo momentum, monthly rebalance'
    m['longs_example'] = longs
    m['shorts_example'] = shorts
    return port, m

# ─── Strategy 2: DM vs EM Rotation ───────────────────────────────────────────
def strategy_dm_em_rotation(prices, spy_rets):
    """Rotate VEA/VWO using 3-month momentum, UUP regime, SPY MA regime."""
    needed = ['VEA', 'VWO', 'SPY', 'UUP']
    if not all(t in prices.columns for t in needed):
        return pd.Series(dtype=float), {'error': 'missing tickers'}

    monthly = monthly_reindex(prices[needed])
    daily_ret = returns(prices[needed])
    spy_200d = prices['SPY'].rolling(200).mean()

    portfolio_rets = []
    signals = []
    dates = monthly.index

    for i in range(4, len(dates)-1):
        d_3m  = dates[i-3]
        d_now = dates[i]
        d_next= dates[i+1]

        # Signal 1: relative 3m momentum
        vea_mom = monthly['VEA'].loc[d_now] / monthly['VEA'].loc[d_3m] - 1
        vwo_mom = monthly['VWO'].loc[d_now] / monthly['VWO'].loc[d_3m] - 1
        mom_signal = 'VEA' if vea_mom > vwo_mom else 'VWO'

        # Signal 2: UUP regime (20d momentum on UUP)
        uup_slice = prices['UUP'].loc[:d_now].tail(21)
        uup_rising = uup_slice.iloc[-1] > uup_slice.iloc[0] if len(uup_slice) >= 2 else True
        uup_signal = 'VEA' if uup_rising else 'VWO'

        # Signal 3: SPY vs 200d MA
        spy_now = prices['SPY'].loc[:d_now].iloc[-1]
        spy_ma  = spy_200d.loc[:d_now].iloc[-1]
        spy_signal = 'VEA' if spy_now > spy_ma else 'VWO'

        # Majority vote
        votes = [mom_signal, uup_signal, spy_signal]
        chosen = 'VEA' if votes.count('VEA') >= 2 else 'VWO'
        signals.append({'date': d_now, 'chosen': chosen, 'mom': mom_signal,
                        'uup': uup_signal, 'spy_ma': spy_signal})

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, chosen]
        portfolio_rets.append(period_rets)

    port = pd.concat(portfolio_rets).sort_index()
    port = port[~port.index.duplicated()]
    m = metrics(port, spy_rets)
    m['description'] = 'DM/EM rotation: majority vote of 3-month momentum, UUP regime, SPY MA'

    # Benchmark: buy-hold VEA and VWO
    vea_bh = returns(prices['VEA']).dropna()
    vwo_bh = returns(prices['VWO']).dropna()
    m['vea_buyhold_sharpe'] = round(sharpe(vea_bh), 3)
    m['vwo_buyhold_sharpe'] = round(sharpe(vwo_bh), 3)
    m['vea_buyhold_cagr']   = round(cagr(vea_bh)*100, 2)
    m['vwo_buyhold_cagr']   = round(cagr(vwo_bh)*100, 2)

    # Breakdown by signal agreement
    signal_df = pd.DataFrame(signals)
    m['pct_chose_vea'] = round(float((signal_df['chosen']=='VEA').mean()*100), 1)
    m['pct_chose_vwo'] = round(float((signal_df['chosen']=='VWO').mean()*100), 1)
    return port, m

# ─── Strategy 3: US vs International Global Momentum ─────────────────────────
def strategy_global_momentum(prices, spy_rets):
    """Rotate SPY / EFA / TLT based on 6-month relative momentum."""
    needed = ['SPY', 'EFA', 'TLT']
    if not all(t in prices.columns for t in needed):
        return pd.Series(dtype=float), {'error': 'missing tickers'}

    monthly = monthly_reindex(prices[needed])
    daily_ret = returns(prices[needed])

    portfolio_rets = []
    allocations = []
    dates = monthly.index

    for i in range(7, len(dates)-1):
        d_6m  = dates[i-6]
        d_now = dates[i]
        d_next= dates[i+1]

        spy_mom = monthly['SPY'].loc[d_now] / monthly['SPY'].loc[d_6m] - 1
        efa_mom = monthly['EFA'].loc[d_now] / monthly['EFA'].loc[d_6m] - 1
        tlt_mom = monthly['TLT'].loc[d_now] / monthly['TLT'].loc[d_6m] - 1

        # Both equity weak → TLT
        if spy_mom < 0 and efa_mom < 0:
            chosen = 'TLT'
        elif spy_mom > efa_mom:
            chosen = 'SPY'
        else:
            chosen = 'EFA'

        allocations.append({'date': d_now, 'chosen': chosen})

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, chosen]
        portfolio_rets.append(period_rets)

    port = pd.concat(portfolio_rets).sort_index()
    port = port[~port.index.duplicated()]
    m = metrics(port, spy_rets)
    m['description'] = 'Rotate SPY/EFA/TLT on 6-month momentum; TLT when both equity weak'

    alloc_df = pd.DataFrame(allocations)
    m['pct_spy'] = round(float((alloc_df['chosen']=='SPY').mean()*100), 1)
    m['pct_efa'] = round(float((alloc_df['chosen']=='EFA').mean()*100), 1)
    m['pct_tlt'] = round(float((alloc_df['chosen']=='TLT').mean()*100), 1)

    # EFA buy-hold benchmark
    efa_bh = returns(prices['EFA']).dropna()
    m['efa_buyhold_sharpe'] = round(sharpe(efa_bh), 3)
    m['efa_buyhold_cagr']   = round(cagr(efa_bh)*100, 2)
    return port, m

# ─── Strategy 4: Country Pairs Trading ───────────────────────────────────────
PAIRS = [
    ('EWG', 'EWU', 'Germany/UK'),
    ('EWJ', 'EWH', 'Japan/HK'),
    ('EWC', 'EWA', 'Canada/Australia'),
    ('EEM', 'VWO', 'EM Broad pair'),
    ('FXI', 'INDA', 'China/India'),
]

def pairs_strategy(prices, t1, t2, window=60, entry=1.5, exit_z=0.5):
    if t1 not in prices.columns or t2 not in prices.columns:
        return pd.Series(dtype=float)

    p1 = np.log(prices[t1])
    p2 = np.log(prices[t2])
    spread = p1 - p2

    roll_mean = spread.rolling(window).mean()
    roll_std  = spread.rolling(window).std()
    z = (spread - roll_mean) / roll_std

    # Compute returns aligned on common index
    r1_series = prices[t1].pct_change()
    r2_series = prices[t2].pct_change()

    # Use shared index (z, r1, r2 all on prices.index)
    port_rets = pd.Series(0.0, index=prices.index)
    position = 0  # 1 = long t1/short t2, -1 = reverse

    idx = prices.index
    for i in range(1, len(idx)):
        zi = z.iloc[i]
        if np.isnan(zi):
            continue

        # Entry signal is based on previous bar's z (signal on close, execute next bar)
        zi_prev = z.iloc[i-1]
        if np.isnan(zi_prev):
            continue

        # Update position based on previous z
        if position == 0:
            if zi_prev > entry:
                position = -1
            elif zi_prev < -entry:
                position = 1
        elif position == 1 and zi_prev > -exit_z:
            position = 0
        elif position == -1 and zi_prev < exit_z:
            position = 0

        if position != 0:
            r1 = r1_series.iloc[i]
            r2 = r2_series.iloc[i]
            if not (np.isnan(r1) or np.isnan(r2)):
                if position == 1:
                    port_rets.iloc[i] = r1 - r2
                else:
                    port_rets.iloc[i] = r2 - r1

    return port_rets

def strategy_country_pairs(prices, spy_rets):
    results = {}
    all_rets = []

    for t1, t2, name in PAIRS:
        if t1 not in prices.columns or t2 not in prices.columns:
            print(f"  Skipping pair {name}: missing data")
            continue
        port = pairs_strategy(prices, t1, t2)
        port = port.dropna()
        if len(port) < 100:
            continue
        m = metrics(port, spy_rets)
        m['pair'] = name
        results[name] = m
        all_rets.append(port)

    # Equal-weight combo
    if all_rets:
        combo = pd.concat(all_rets, axis=1).mean(axis=1).dropna()
        combo_m = metrics(combo, spy_rets)
        combo_m['pair'] = 'equal_weight_combo'
        results['equal_weight_combo'] = combo_m

    best = max(results.items(), key=lambda x: x[1].get('sharpe', -99)) if results else ('none', {})
    summary = {
        'description': 'Mean-reversion pairs: 60d z-score, ±1.5σ entry, ±0.5σ exit',
        'pairs': results,
        'best_pair': best[0],
        'best_pair_sharpe': best[1].get('sharpe', None),
    }
    return summary

# ─── Strategy 5: EM Momentum + Dollar Filter ─────────────────────────────────
def strategy_em_momentum_dollar(prices, spy_rets):
    """EM ETFs with strongest 3-month momentum, filtered by USD weakness."""
    em_universe = [t for t in EMERGING if t in prices.columns]
    if 'UUP' not in prices.columns:
        return pd.Series(dtype=float), {'error': 'missing UUP'}

    monthly = monthly_reindex(prices[em_universe + ['UUP']])
    daily_ret = returns(prices[em_universe])

    portfolio_rets_filtered = []
    portfolio_rets_unfiltered = []
    dates = monthly.index

    for i in range(4, len(dates)-1):
        d_3m  = dates[i-3]
        d_1m  = dates[i-1]
        d_now = dates[i]
        d_next= dates[i+1]

        # UUP 20d momentum
        uup_slice = prices['UUP'].loc[:d_now].tail(21)
        usd_weakening = uup_slice.iloc[-1] < uup_slice.iloc[0] if len(uup_slice) >= 2 else False

        # 3-month momentum for EM ETFs
        mom = {}
        for t in em_universe:
            try:
                mom[t] = monthly[t].loc[d_now] / monthly[t].loc[d_3m] - 1
            except Exception:
                pass

        if len(mom) < 3:
            continue

        ranked = sorted(mom.items(), key=lambda x: x[1], reverse=True)
        top3 = [t for t, _ in ranked[:3]]

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, top3]

        if period_rets.empty:
            continue

        port_r = period_rets.mean(axis=1)
        portfolio_rets_unfiltered.append(port_r)

        if usd_weakening:
            portfolio_rets_filtered.append(port_r)
        else:
            portfolio_rets_filtered.append(pd.Series(0.0, index=port_r.index))

    port_unfiltered = pd.concat(portfolio_rets_unfiltered).sort_index()
    port_unfiltered = port_unfiltered[~port_unfiltered.index.duplicated()]

    port_filtered = pd.concat(portfolio_rets_filtered).sort_index()
    port_filtered = port_filtered[~port_filtered.index.duplicated()]

    m_filtered   = metrics(port_filtered, spy_rets)
    m_unfiltered = metrics(port_unfiltered, spy_rets)

    m_filtered['description']        = 'Top-3 EM momentum, only invested when USD weakening'
    m_filtered['unfiltered_sharpe']  = m_unfiltered['sharpe']
    m_filtered['unfiltered_cagr']    = m_unfiltered['cagr']
    m_filtered['filter_adds_value']  = m_filtered['sharpe'] > m_unfiltered['sharpe']

    return port_filtered, m_filtered

# ─── Strategy 6: Valuation-Momentum Combo ────────────────────────────────────
def strategy_valuation_momentum(prices, spy_rets):
    """Cheapest 3 countries (lowest 3yr return) with positive 3m momentum, annual rebalance."""
    universe = [t for t in DEVELOPED + EMERGING if t in prices.columns]
    monthly = monthly_reindex(prices[universe])
    daily_ret = returns(prices[universe])

    portfolio_rets = []
    annual_dates = [d for d in monthly.index if d.month == 1]

    for i in range(1, len(annual_dates)-1):
        d_3yr  = annual_dates[i] - pd.DateOffset(years=3)
        d_3m   = annual_dates[i] - pd.DateOffset(months=3)
        d_now  = annual_dates[i]
        d_next = annual_dates[i+1]

        val_mom = {}
        for t in universe:
            try:
                # Find closest available dates
                p_3yr = monthly[t].asof(d_3yr)
                p_3m  = monthly[t].asof(d_3m)
                p_now = monthly[t].asof(d_now)
                if pd.isna(p_3yr) or pd.isna(p_3m) or pd.isna(p_now):
                    continue
                val  = p_now / p_3yr - 1   # 3yr return (proxy for cheapness → negative = cheap)
                mom3 = p_now / p_3m - 1    # 3m momentum
                val_mom[t] = (val, mom3)
            except Exception:
                pass

        if len(val_mom) < 6:
            continue

        # Cheapest 3 with positive 3m momentum
        sorted_by_val = sorted(val_mom.items(), key=lambda x: x[1][0])
        candidates = [(t, v) for t, v in sorted_by_val if v[1] > 0]
        if len(candidates) < 3:
            candidates = sorted_by_val[:3]

        top3 = [t for t, _ in candidates[:3]]

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, top3]
        if period_rets.empty:
            continue
        portfolio_rets.append(period_rets.mean(axis=1))

    if not portfolio_rets:
        return pd.Series(dtype=float), {}

    port = pd.concat(portfolio_rets).sort_index()
    port = port[~port.index.duplicated()]
    m = metrics(port, spy_rets)
    m['description'] = 'Cheapest 3 countries (lowest 3yr return) with positive 3m momentum, annual rebalance'
    m['last_picks'] = top3 if 'top3' in dir() else []
    return port, m

# ─── Individual country buy-hold analysis ────────────────────────────────────
def individual_country_analysis(prices, spy_rets):
    results = {}
    for t in DEVELOPED + EMERGING:
        if t not in prices.columns:
            continue
        r = returns(prices[t]).dropna()
        if len(r) < 200:
            continue
        results[t] = {
            'name': COUNTRY_NAMES.get(t, t),
            'sharpe': round(sharpe(r), 3),
            'cagr':   round(cagr(r)*100, 2),
            'max_dd': round(max_drawdown(r)*100, 2),
            'spy_corr': round(spy_corr(r, spy_rets), 3),
        }
    return results

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("International Equity Strategy Harness")
    print("=" * 60)

    prices = fetch_prices(ALL_TICKERS)
    spy_rets = returns(prices['SPY']).dropna() if 'SPY' in prices.columns else pd.Series(dtype=float)

    # ── SPY buy-hold benchmark
    spy_bh = metrics(spy_rets, spy_rets) if len(spy_rets) > 0 else {}
    print(f"\nSPY buy-hold: Sharpe={spy_bh.get('sharpe')}, CAGR={spy_bh.get('cagr')}%")

    results = {
        'category': 'international_equities',
        'run_date': datetime.now().isoformat(),
        'data_range': f'{START} to {END}',
        'spy_benchmark': spy_bh,
        'strategies': {},
        'top_strategies': [],
    }

    # ── Strategy 1: Cross-Country Momentum
    print("\n[1/6] Cross-Country Momentum …")
    try:
        port1, m1 = strategy_cross_country_momentum(prices, spy_rets)
        results['strategies']['cross_country_momentum'] = m1
        print(f"  Sharpe={m1.get('sharpe')}, CAGR={m1.get('cagr')}%, MaxDD={m1.get('max_dd')}%")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['cross_country_momentum'] = {'error': str(e)}

    # ── Strategy 2: DM vs EM Rotation
    print("\n[2/6] DM/EM Rotation …")
    try:
        port2, m2 = strategy_dm_em_rotation(prices, spy_rets)
        results['strategies']['dm_em_rotation'] = m2
        print(f"  Sharpe={m2.get('sharpe')}, CAGR={m2.get('cagr')}%, MaxDD={m2.get('max_dd')}%")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['dm_em_rotation'] = {'error': str(e)}

    # ── Strategy 3: Global Momentum (US vs Intl)
    print("\n[3/6] Global Momentum Rotation …")
    try:
        port3, m3 = strategy_global_momentum(prices, spy_rets)
        results['strategies']['global_momentum'] = m3
        print(f"  Sharpe={m3.get('sharpe')}, CAGR={m3.get('cagr')}%, MaxDD={m3.get('max_dd')}%")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['global_momentum'] = {'error': str(e)}

    # ── Strategy 4: Country Pairs
    print("\n[4/6] Country Pairs Trading …")
    try:
        pairs_result = strategy_country_pairs(prices, spy_rets)
        results['strategies']['country_pairs'] = pairs_result
        print(f"  Best pair: {pairs_result.get('best_pair')}, Sharpe={pairs_result.get('best_pair_sharpe')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['country_pairs'] = {'error': str(e)}

    # ── Strategy 5: EM Momentum + Dollar Filter
    print("\n[5/6] EM Momentum + Dollar Filter …")
    try:
        port5, m5 = strategy_em_momentum_dollar(prices, spy_rets)
        results['strategies']['em_momentum_dollar_filter'] = m5
        print(f"  Sharpe={m5.get('sharpe')}, CAGR={m5.get('cagr')}%, Filter adds value: {m5.get('filter_adds_value')}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['em_momentum_dollar_filter'] = {'error': str(e)}

    # ── Strategy 6: Valuation-Momentum Combo
    print("\n[6/6] Valuation-Momentum Combo …")
    try:
        port6, m6 = strategy_valuation_momentum(prices, spy_rets)
        results['strategies']['valuation_momentum'] = m6
        print(f"  Sharpe={m6.get('sharpe')}, CAGR={m6.get('cagr')}%, MaxDD={m6.get('max_dd')}%")
    except Exception as e:
        print(f"  ERROR: {e}")
        results['strategies']['valuation_momentum'] = {'error': str(e)}

    # ── Individual country analysis
    print("\nIndividual country buy-hold analysis …")
    try:
        country_results = individual_country_analysis(prices, spy_rets)
        results['individual_countries'] = country_results
        sorted_countries = sorted(country_results.items(), key=lambda x: x[1].get('sharpe', -99), reverse=True)
        print("  Top 5 countries by Sharpe:")
        for t, m in sorted_countries[:5]:
            print(f"    {t} ({m['name']}): Sharpe={m['sharpe']}, CAGR={m['cagr']}%")
    except Exception as e:
        print(f"  ERROR: {e}")

    # ── Compile top strategies list
    strategy_list = []
    strat_map = {
        'cross_country_momentum': results['strategies'].get('cross_country_momentum', {}),
        'dm_em_rotation': results['strategies'].get('dm_em_rotation', {}),
        'global_momentum': results['strategies'].get('global_momentum', {}),
        'em_momentum_dollar_filter': results['strategies'].get('em_momentum_dollar_filter', {}),
        'valuation_momentum': results['strategies'].get('valuation_momentum', {}),
    }
    # Pairs best
    pairs = results['strategies'].get('country_pairs', {})
    if 'pairs' in pairs:
        best_pair_name = pairs.get('best_pair', '')
        best_pair_data = pairs.get('pairs', {}).get(best_pair_name, {})
        strat_map[f'pairs_{best_pair_name}'] = best_pair_data

    for name, m in strat_map.items():
        if 'sharpe' in m:
            strategy_list.append({
                'strategy': name,
                'sharpe': m.get('sharpe'),
                'cagr': m.get('cagr'),
                'max_dd': m.get('max_dd'),
                'spy_corr': m.get('spy_corr'),
            })

    strategy_list.sort(key=lambda x: x.get('sharpe', -99), reverse=True)
    results['top_strategies'] = strategy_list

    # Best strategy
    if strategy_list:
        best = strategy_list[0]
        results['best_strategy'] = best['strategy']
        results['best_sharpe'] = best['sharpe']
    else:
        results['best_strategy'] = 'unknown'
        results['best_sharpe'] = None

    # Best diversifier (lowest SPY correlation)
    if strategy_list:
        best_div = min(strategy_list, key=lambda x: abs(x.get('spy_corr') or 1.0))
        results['best_diversifier'] = best_div

    # Key finding
    spy_sharpe = spy_bh.get('sharpe', 0)
    best_sh = results.get('best_sharpe', 0) or 0
    intl_beats_spy = best_sh > spy_sharpe

    if intl_beats_spy:
        results['key_finding'] = (
            f"Best intl strategy ({results['best_strategy']}) achieves Sharpe {best_sh:.2f} "
            f"vs SPY Sharpe {spy_sharpe:.2f}, demonstrating alpha over passive US exposure."
        )
    else:
        results['key_finding'] = (
            f"SPY (Sharpe {spy_sharpe:.2f}) outperforms best intl strategy (Sharpe {best_sh:.2f}). "
            f"International strategies provide diversification value but not direct alpha over SPY."
        )

    # ── Save JSON
    out_path = '/workspace/group/trading_eval/rounds/intl_results.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    return results

if __name__ == '__main__':
    results = main()
    print("\n=== FINAL SUMMARY ===")
    print(f"Best strategy:  {results.get('best_strategy')}")
    print(f"Best Sharpe:    {results.get('best_sharpe')}")
    print(f"SPY benchmark:  Sharpe={results['spy_benchmark'].get('sharpe')}, CAGR={results['spy_benchmark'].get('cagr')}%")
    print(f"Key finding: {results.get('key_finding')}")
