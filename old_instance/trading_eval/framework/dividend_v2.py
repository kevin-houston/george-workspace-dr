#!/usr/bin/env python3
"""
Round 27: Dividend Strategies — Framework v2
=============================================
Re-implementation of dividend_harness.py using the TradeLogger framework.
Logs per-trade records for four dividend strategy groups; analysis layer
handles all Sharpe/metrics computation.

Strategies covered:
  - div_raise_signal   : Dividend raise signal (buy on raise announcement)
  - div_cc_exdiv       : Covered calls written around ex-dividend date
  - div_capture        : Dividend capture (buy before / sell after ex-date)
  - dogs_of_dow        : Dogs of the Dow annual rotation

Run with:
    /workspace/group/venv/bin/python3 trading_eval/framework/dividend_v2.py
"""

import sys
import os

# Insert framework dir so base_harness is importable, then project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

import warnings
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta

warnings.filterwarnings('ignore')

try:
    import yfinance as yf
    from scipy.stats import norm
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'pandas', 'yfinance', 'scipy', 'numpy',
                    '--break-system-packages', '-q'], capture_output=True)
    import yfinance as yf
    from scipy.stats import norm

from base_harness import TradeLogger, fetch_data, get_close, bs_call, bs_put, realized_vol

# ─────────────────────────────────────────────
# PATHS & CONFIG
# ─────────────────────────────────────────────

FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
CACHE_DIR     = EVAL_DIR / 'cache'
DIV_CACHE     = CACHE_DIR / 'dividends'
DIV_CACHE.mkdir(parents=True, exist_ok=True)

START = pd.Timestamp('2015-01-01')
END   = pd.Timestamp('2025-12-31')
RF    = 0.045

DOW30 = ['AAPL', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS', 'DOW', 'GS',
         'HD', 'HON', 'IBM', 'INTC', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM', 'MRK',
         'MSFT', 'NKE', 'PG', 'TRV', 'UNH', 'V', 'VZ', 'WBA', 'WMT', 'AMGN']

# ─────────────────────────────────────────────
# PRICE & DIVIDEND LOADERS
# ─────────────────────────────────────────────

def strip_tz(idx):
    """Remove timezone from DatetimeIndex."""
    if hasattr(idx, 'tz') and idx.tz is not None:
        return idx.tz_localize(None)
    return idx


def load_prices():
    """Load price series from *_15yr.pkl cache files."""
    prices = {}
    for f in CACHE_DIR.glob('*_15yr.pkl'):
        ticker = f.stem.replace('_15yr', '')
        if ticker.startswith('ohlcv_'):
            continue
        try:
            s = pickle.load(open(f, 'rb'))
            if isinstance(s, pd.DataFrame):
                s = s['Close'].squeeze()
            s.index = strip_tz(s.index)
            s = s.loc[START:END].dropna()
            if len(s) > 100:
                prices[ticker] = s
        except Exception:
            pass
    return prices


def load_dividends(tickers):
    """Load or fetch dividend series for each ticker."""
    divs = {}
    for ticker in tickers:
        cache_file = DIV_CACHE / f'{ticker}.pkl'
        if cache_file.exists():
            try:
                s = pickle.load(open(cache_file, 'rb'))
                s.index = strip_tz(s.index)
                divs[ticker] = s
                continue
            except Exception:
                pass
        try:
            s = yf.Ticker(ticker).dividends
            if s is not None and len(s) > 0:
                s.index = strip_tz(s.index)
                pickle.dump(s, open(cache_file, 'wb'))
                divs[ticker] = s
        except Exception:
            pass
    return divs

# ─────────────────────────────────────────────
# STRATEGY: div_raise_signal
# ─────────────────────────────────────────────

def run_div_raise_signal(prices, divs):
    """
    Buy on dividend raise announcement. Log each event as a trade.

    Params grid from original harness:
      min_raise in [0.03, 0.05, 0.10]
      hold      in [10, 20, 40]
    """
    logger = TradeLogger(round_num=27, strategy='div_raise_signal', category='dividend')

    param_grid = [
        {'min_raise': 0.03, 'hold_days': 10},
        {'min_raise': 0.03, 'hold_days': 20},
        {'min_raise': 0.03, 'hold_days': 40},
        {'min_raise': 0.05, 'hold_days': 10},
        {'min_raise': 0.05, 'hold_days': 20},
        {'min_raise': 0.05, 'hold_days': 40},
        {'min_raise': 0.10, 'hold_days': 10},
        {'min_raise': 0.10, 'hold_days': 20},
        {'min_raise': 0.10, 'hold_days': 40},
    ]

    for p in param_grid:
        hold       = p['hold_days']
        min_raise  = p['min_raise']

        for ticker, closes in prices.items():
            d = divs.get(ticker)
            if d is None or len(d) < 3:
                continue
            idx_list = closes.index.tolist()
            d2i = {dt: i for i, dt in enumerate(idx_list)}
            amounts = d.values
            dates   = d.index.tolist()

            for i in range(1, len(dates)):
                prev, cur = amounts[i - 1], amounts[i]
                if prev <= 0:
                    continue
                chg = (cur - prev) / prev
                if chg < min_raise:
                    continue
                ev_date = dates[i]
                if ev_date < START or ev_date > END:
                    continue
                ei = next((d2i[dt] for dt in idx_list if dt >= ev_date), None)
                if ei is None:
                    continue
                xi = ei + hold
                if xi >= len(idx_list):
                    continue

                entry_price = float(closes.iloc[ei])
                exit_price  = float(closes.iloc[xi])
                ret         = (exit_price - entry_price) / entry_price
                entry_date  = idx_list[ei]
                exit_date   = idx_list[xi]

                logger.log(
                    ticker       = ticker,
                    entry_date   = entry_date,
                    exit_date    = exit_date,
                    return_pct   = ret,
                    hold_days    = hold,
                    direction    = 'long',
                    entry_price  = entry_price,
                    exit_price   = exit_price,
                    params       = {'raise_threshold': min_raise, 'hold_days': hold},
                    notes        = f'div_raise=+{chg * 100:.1f}%',
                    div_raise_pct = float(chg),
                    div_amount    = float(cur),
                )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# STRATEGY: div_cc_exdiv
# ─────────────────────────────────────────────

def run_div_cc_exdiv(prices, divs):
    """
    Covered calls written N days before ex-dividend date (2% OTM).

    Params grid from original harness:
      days_before in [3, 5, 10]
      otm_pct = 0.02 (fixed)
    """
    logger = TradeLogger(round_num=27, strategy='div_cc_exdiv', category='dividend')

    param_grid = [
        {'days_before': 3,  'otm_pct': 0.02},
        {'days_before': 5,  'otm_pct': 0.02},
        {'days_before': 10, 'otm_pct': 0.02},
    ]

    for p in param_grid:
        days_before = p['days_before']
        otm_pct     = p['otm_pct']

        for ticker, closes in prices.items():
            d = divs.get(ticker)
            if d is None or len(d) == 0:
                continue
            idx_list     = closes.index.tolist()
            d2i          = {dt: i for i, dt in enumerate(idx_list)}
            rets_series  = closes.pct_change()
            vol20        = rets_series.rolling(20).std() * np.sqrt(252)

            for ex_date, div_amt in d.items():
                if ex_date < START or ex_date > END:
                    continue
                ex_i = next((d2i[dt] for dt in idx_list if dt >= ex_date), None)
                if ex_i is None:
                    continue
                sell_i = ex_i - days_before
                if sell_i < 20:
                    continue

                S     = float(closes.iloc[sell_i])
                sigma = float(vol20.iloc[sell_i])
                if np.isnan(sigma) or sigma <= 0:
                    continue

                K        = S * (1 + otm_pct)
                T        = days_before / 252
                premium  = bs_call(S, K, T, sigma)
                prem_pct = premium / S

                S_ex      = float(closes.iloc[ex_i])
                # Adjusted prices: stock_ret already incorporates dividend
                # reinvestment, so we do NOT add div_amount separately.
                stock_ret = min((S_ex - S) / S, (K - S) / S)  # capped if called away
                total_ret = stock_ret + prem_pct

                entry_date = idx_list[sell_i]
                exit_date  = idx_list[ex_i]

                logger.log(
                    ticker            = ticker,
                    entry_date        = entry_date,
                    exit_date         = exit_date,
                    return_pct        = total_ret,
                    hold_days         = days_before,
                    direction         = 'short_call',
                    entry_price       = S,
                    exit_price        = S_ex,
                    strike            = K,
                    option_type       = 'call',
                    premium_collected = prem_pct,
                    iv_at_entry       = sigma,
                    params            = {'days_before': days_before, 'otm_pct': otm_pct},
                    notes             = f'ex_date={str(ex_date.date())}',
                    div_amount        = float(div_amt),
                    ex_date           = str(ex_date.date()),
                )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# STRATEGY: div_capture
# ─────────────────────────────────────────────

def run_div_capture(prices, divs):
    """
    Dividend capture: buy N days before ex-date, sell M days after.

    Params grid from original harness:
      buy_before in [1, 2, 3]
      hold_after in [1, 3, 5, 10]

    NOTE: Using adjusted prices — no double-counting of dividend.
    """
    logger = TradeLogger(round_num=27, strategy='div_capture', category='dividend')

    param_grid = [
        {'buy_before': bb, 'hold_after': ha}
        for bb in [1, 2, 3]
        for ha in [1, 3, 5, 10]
    ]

    for p in param_grid:
        buy_before = p['buy_before']
        hold_after = p['hold_after']

        for ticker, closes in prices.items():
            d = divs.get(ticker)
            if d is None or len(d) == 0:
                continue
            idx_list = closes.index.tolist()
            d2i      = {dt: i for i, dt in enumerate(idx_list)}

            for ex_date, div_amt in d.items():
                if ex_date < START or ex_date > END:
                    continue
                ex_i = next((d2i[dt] for dt in idx_list if dt >= ex_date), None)
                if ex_i is None:
                    continue
                bi, si = ex_i - buy_before, ex_i + hold_after
                if bi < 0 or si >= len(idx_list):
                    continue

                entry_price = float(closes.iloc[bi])
                exit_price  = float(closes.iloc[si])
                ret         = (exit_price - entry_price) / entry_price
                entry_date  = idx_list[bi]
                exit_date   = idx_list[si]
                total_hold  = buy_before + hold_after

                logger.log(
                    ticker       = ticker,
                    entry_date   = entry_date,
                    exit_date    = exit_date,
                    return_pct   = ret,
                    hold_days    = total_hold,
                    direction    = 'long',
                    entry_price  = entry_price,
                    exit_price   = exit_price,
                    params       = {'buy_before': buy_before, 'hold_after': hold_after},
                    notes        = f'ex_date={str(ex_date.date())}',
                    div_amount   = float(div_amt),
                    ex_date      = str(ex_date.date()),
                )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# STRATEGY: dogs_of_dow
# ─────────────────────────────────────────────

def run_dogs_of_dow(prices, divs):
    """
    Dogs of the Dow: each year buy the N highest-yield Dow 30 stocks.
    Logs one trade record per stock per year.

    Params grid from original harness:
      n_dogs in [5, 10]
    """
    logger = TradeLogger(round_num=27, strategy='dogs_of_dow', category='dividend')

    for n_dogs in [5, 10]:
        for year in range(2015, 2026):
            start_dt = pd.Timestamp(f'{year}-01-02')
            end_dt   = pd.Timestamp(f'{year}-12-31')

            yields = {}
            for ticker in DOW30:
                if ticker not in prices or ticker not in divs:
                    continue
                closes      = prices[ticker]
                year_closes = closes.loc[start_dt:end_dt]
                if len(year_closes) < 50:
                    continue
                p0         = float(year_closes.iloc[0])
                prior_divs = divs[ticker].loc[
                    (divs[ticker].index >= start_dt - timedelta(days=365)) &
                    (divs[ticker].index < start_dt)
                ]
                ann_div = float(prior_divs.sum())
                if p0 > 0 and ann_div > 0:
                    yields[ticker] = ann_div / p0

            if len(yields) < n_dogs:
                continue

            portfolio = [t for t, _ in
                         sorted(yields.items(), key=lambda x: x[1], reverse=True)[:n_dogs]]

            for ticker in portfolio:
                year_closes = prices[ticker].loc[start_dt:end_dt]
                if len(year_closes) < 50:
                    continue
                entry_price = float(year_closes.iloc[0])
                exit_price  = float(year_closes.iloc[-1])
                div_income  = float(divs[ticker].loc[start_dt:end_dt].sum()) if ticker in divs else 0.0
                ret         = (exit_price + div_income - entry_price) / entry_price
                entry_date  = year_closes.index[0]
                exit_date   = year_closes.index[-1]
                hold        = (exit_date - entry_date).days

                logger.log(
                    ticker       = ticker,
                    entry_date   = entry_date,
                    exit_date    = exit_date,
                    return_pct   = ret,
                    hold_days    = hold,
                    direction    = 'long',
                    entry_price  = entry_price,
                    exit_price   = exit_price,
                    params       = {'n_dogs': n_dogs, 'year': year},
                    notes        = f'yield={yields[ticker] * 100:.2f}% year={year} n_dogs={n_dogs}',
                    div_amount   = div_income,
                    div_yield    = float(yields[ticker]),
                )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print('=' * 60)
    print('ROUND 27: DIVIDEND STRATEGIES (framework v2)')
    print('=' * 60)

    print('\nLoading price cache...')
    prices = load_prices()
    print(f'  {len(prices)} tickers loaded from cache')

    print('Fetching dividends...')
    divs = load_dividends(list(prices.keys()))
    print(f'  {len(divs)} tickers with dividend data')

    print('\n[1] Running div_raise_signal...')
    logger_raise = run_div_raise_signal(prices, divs)
    print(f'    {len(logger_raise)} trade records logged')

    print('\n[2] Running div_cc_exdiv...')
    logger_cc = run_div_cc_exdiv(prices, divs)
    print(f'    {len(logger_cc)} trade records logged')

    print('\n[3] Running div_capture...')
    logger_cap = run_div_capture(prices, divs)
    print(f'    {len(logger_cap)} trade records logged')

    print('\n[4] Running dogs_of_dow...')
    logger_dogs = run_dogs_of_dow(prices, divs)
    print(f'    {len(logger_dogs)} trade records logged')

    print('\nDone.')


if __name__ == '__main__':
    main()
