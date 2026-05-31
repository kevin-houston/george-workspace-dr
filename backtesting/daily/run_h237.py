#!/usr/bin/env python3
"""
H237: Drift-Regime-Conditional Industry-Adjusted Reversal

Source: arXiv:2511.12490 (Singha, Nov 2025)
  'Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden
  Cross-Sectional Predictability'

Drift regime: stock shows >60% positive days in trailing 63-day window.
Hypothesis: reversal signal (H181) is strongest in NON-trending stocks.
Filter: exclude stocks in drift regime from H181 selection pool.

Universe: 30 large-cap S&P 500 (same as H181/H217)
IS: 2013-2020, OOS: 2021-2026
Baseline: H181 OOS Sharpe=1.138
Confirm gate: OOS Sharpe > 1.138 with MaxDD < -20%
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

UNIVERSE = [
    'AAPL','MSFT','NVDA','AVGO','QCOM','AMD','IBM',
    'V','MA','BAC','WFC','JPM',
    'UNH','LLY','PFE','JNJ','ABBV',
    'AMZN','TSLA','HD','SBUX','LOW',
    'WMT','COST',
    'GOOGL','META',
    'CVX','XOM',
    'BA','CAT'
]

UNIVERSE_SECTORS = {
    'AAPL': 'IT', 'MSFT': 'IT', 'NVDA': 'IT', 'AVGO': 'IT',
    'QCOM': 'IT', 'AMD': 'IT', 'IBM': 'IT',
    'V': 'FIN', 'MA': 'FIN', 'BAC': 'FIN', 'WFC': 'FIN', 'JPM': 'FIN',
    'UNH': 'HC', 'LLY': 'HC', 'PFE': 'HC', 'JNJ': 'HC', 'ABBV': 'HC',
    'AMZN': 'CD', 'TSLA': 'CD', 'HD': 'CD', 'SBUX': 'CD', 'LOW': 'CD',
    'WMT': 'CS', 'COST': 'CS',
    'GOOGL': 'COMM', 'META': 'COMM',
    'CVX': 'ENE', 'XOM': 'ENE',
    'BA': 'IND', 'CAT': 'IND'
}

DRIFT_WINDOW = 63       # trading days for drift regime detection
DRIFT_THRESHOLD = 0.60  # >60% positive days = drift regime
N_LONG = 6              # stocks to hold


def compute_drift_regime(daily_closes, reference_date, window=63, threshold=0.60):
    """
    For each stock at reference_date, check if >threshold fraction of the
    trailing `window` days had positive returns.
    Returns dict: {ticker: True/False (True = in drift regime)}
    """
    drift = {}
    for ticker in daily_closes.columns:
        series = daily_closes[ticker].dropna()
        # get last `window` days before reference_date
        hist = series[series.index < reference_date].tail(window)
        if len(hist) < window // 2:
            drift[ticker] = False
            continue
        daily_rets = hist.pct_change().dropna()
        pct_positive = (daily_rets > 0).mean()
        drift[ticker] = (pct_positive >= threshold)
    return drift


def run_h237(start_is='2013-01-01', end_is='2020-12-31',
             start_oos='2021-01-01', end_oos='2026-05-30'):
    """
    H237: Drift-Regime-Conditional Industry Reversal
    
    Three variants:
    A: H181 baseline (no drift filter)
    B: Exclude drift-regime stocks from reversal selection
    C: Only select from drift-regime stocks (momentum continuation)
    """
    print('H237: Drift-Regime-Conditional Industry Reversal')
    print(f'Universe: {len(UNIVERSE)} stocks, IS {start_is}:{end_is}, OOS {start_oos}:{end_oos}')
    
    # Download daily price data (need extra 63 days for drift window)
    dl_start = (pd.Timestamp(start_is) - pd.Timedelta(days=120)).strftime('%Y-%m-%d')
    print(f'Downloading daily data from {dl_start} to {end_oos}...')
    raw = yf.download(UNIVERSE, start=dl_start, end=end_oos, auto_adjust=True, progress=False)
    daily_closes = raw['Close'].dropna(how='all')
    
    # Monthly rebalance dates (month-end)
    monthly_closes = daily_closes.resample('ME').last()
    
    results = {}
    for variant, drift_filter in [('A', None), ('B', 'exclude'), ('C', 'only_drift')]:
        portfolio_returns = []
        dates = []
        
        for i in range(1, len(monthly_closes)):
            rebalance_date = monthly_closes.index[i]  # signal formation date
            
            # Skip months before IS start
            if rebalance_date < pd.Timestamp(start_is):
                continue
            
            # Prior month returns
            if i < 1:
                continue
            prior_month_ret = (monthly_closes.iloc[i] / monthly_closes.iloc[i-1] - 1)
            
            # Sector-adjusted reversal
            sector_means = {}
            for sector in set(UNIVERSE_SECTORS.values()):
                tickers_in_sector = [t for t in UNIVERSE if UNIVERSE_SECTORS.get(t) == sector
                                     and t in prior_month_ret.index]
                if tickers_in_sector:
                    sector_means[sector] = prior_month_ret[tickers_in_sector].mean()
            
            adj_reversal = {}
            for ticker in UNIVERSE:
                if ticker not in prior_month_ret.index:
                    continue
                sector = UNIVERSE_SECTORS.get(ticker)
                sector_mean = sector_means.get(sector, 0)
                adj_reversal[ticker] = prior_month_ret[ticker] - sector_mean
            
            # Compute drift regime for each stock at rebalance_date
            if drift_filter is not None:
                drift = compute_drift_regime(daily_closes, rebalance_date,
                                           DRIFT_WINDOW, DRIFT_THRESHOLD)
            
            # Filter candidates based on variant
            if drift_filter == 'exclude':
                # Exclude stocks in drift regime (trending up)
                eligible = [t for t in adj_reversal if not drift.get(t, False)]
            elif drift_filter == 'only_drift':
                # Only select from drift-regime stocks
                eligible = [t for t in adj_reversal if drift.get(t, False)]
            else:
                eligible = list(adj_reversal.keys())
            
            if len(eligible) < N_LONG:
                # Not enough eligible — use all available
                selected = sorted(adj_reversal.keys(),
                                  key=lambda t: adj_reversal[t])[:N_LONG]
            else:
                # Select bottom N_LONG (most negative adj-reversal)
                eligible_scores = {t: adj_reversal[t] for t in eligible}
                selected = sorted(eligible_scores, key=lambda t: eligible_scores[t])[:N_LONG]
            
            # Forward return: from this month-end to next month-end
            if i + 1 < len(monthly_closes):
                fwd_ret = (monthly_closes.iloc[i+1][selected] /
                           monthly_closes.iloc[i][selected] - 1)
                port_ret = fwd_ret.mean()
            else:
                break
            
            portfolio_returns.append(port_ret)
            dates.append(rebalance_date)
        
        ret_series = pd.Series(portfolio_returns, index=pd.DatetimeIndex(dates))
        
        # Split IS / OOS
        is_mask  = (ret_series.index >= start_is) & (ret_series.index <= end_is)
        oos_mask = (ret_series.index >= start_oos) & (ret_series.index <= end_oos)
        
        for period_name, mask in [('IS', is_mask), ('OOS', oos_mask)]:
            r = ret_series[mask]
            if len(r) < 2:
                continue
            ann_sharpe = r.mean() / r.std(ddof=1) * np.sqrt(12)
            cumul = (1 + r).prod()
            cagr = cumul ** (12 / len(r)) - 1
            max_dd = (r.cumsum() - r.cumsum().cummax()).min()
            neg_yrs = (r.resample('YE').sum() < 0).sum()
            
            results[f'{variant}_{period_name}'] = {
                'sharpe': round(ann_sharpe, 3),
                'cagr': round(cagr, 3),
                'cumul': round(float(cumul), 3),
                'maxdd': round(float(max_dd), 3),
                'neg_years': int(neg_yrs),
                'n_months': len(r)
            }
        
        if drift_filter is not None:
            # Report average eligible pool size
            avg_eligible = []
            for i in range(1, len(monthly_closes)):
                rebalance_date = monthly_closes.index[i]
                if rebalance_date < pd.Timestamp(start_is) or rebalance_date > pd.Timestamp(end_oos):
                    continue
                drift = compute_drift_regime(daily_closes, rebalance_date, DRIFT_WINDOW, DRIFT_THRESHOLD)
                in_drift = sum(1 for t in UNIVERSE if drift.get(t, False))
                avg_eligible.append(in_drift if drift_filter == 'only_drift' else len(UNIVERSE) - in_drift)
            results[f'{variant}_avg_eligible'] = round(np.mean(avg_eligible), 1)
        
        print(f'\nVariant {variant}:')
        for k, v in results.items():
            if k.startswith(variant):
                print(f'  {k}: {v}')
    
    # SPY benchmark
    spy = yf.download('SPY', start=start_oos, end=end_oos, auto_adjust=True, progress=False)
    spy_m = spy['Close'].resample('ME').last().pct_change().dropna()
    spy_m = spy_m[spy_m.index >= start_oos]
    spy_sharpe = spy_m.mean() / spy_m.std(ddof=1) * np.sqrt(12)
    results['SPY_OOS_sharpe'] = round(float(spy_sharpe), 3)
    
    # Save results
    out_path = 'backtesting/results/h237_drift_regime_reversal.json'
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f'\nResults saved to {out_path}')
    print(f'H181 baseline OOS Sharpe: 1.138')
    print(f'H237-B OOS Sharpe: {results.get("B_OOS", {}).get("sharpe", "N/A")}')
    print(f'SPY OOS Sharpe: {results.get("SPY_OOS_sharpe", "N/A")}')
    
    return results


if __name__ == '__main__':
    run_h237()
