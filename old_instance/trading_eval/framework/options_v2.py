#!/usr/bin/env python3
"""
Round 25: Options Strategies — Framework v2
============================================
Re-implementation of options_harness.py using the TradeLogger framework.
Logs per-trade records for three options strategy groups; analysis layer
handles all Sharpe/metrics computation.

Strategies covered:
  - covered_call      : Monthly covered call (3% OTM, 30d expiry)
  - cash_secured_put  : Monthly cash-secured ATM put (30d expiry)
  - earnings_straddle : Buy ATM straddle N days before gap event, sell on gap day

Run with:
    /workspace/group/venv/bin/python3 trading_eval/framework/options_v2.py
"""

import sys
import os

# Insert framework dir so base_harness is importable, then project root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))

import warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')

from base_harness import TradeLogger, fetch_data, get_close, bs_call, bs_put, realized_vol

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

UNIVERSE_OPTIONS = ['XOM', 'CVX', 'JNJ', 'PFE', 'KO', 'T', 'VZ', 'IBM', 'MO', 'PG']
UNIVERSE_PEAD    = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'COST',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'NFLX', 'ADBE', 'QCOM', 'TXN', 'HON',
    'GE', 'CAT', 'MMM', 'LMT', 'RTX',
]

START_DATE = '2020-01-01'
END_DATE   = '2025-12-31'
RISK_FREE  = 0.045

# ─────────────────────────────────────────────
# HELPERS (preserved exactly from options_harness.py)
# ─────────────────────────────────────────────

def calc_realized_vol(prices, window=20):
    """20-day realized vol (annualized)."""
    log_ret = np.log(prices / prices.shift(1)).dropna()
    vol = log_ret.rolling(window).std() * np.sqrt(252)
    return vol


def find_gap_events(close, threshold=0.03):
    """Find days with gap > threshold (overnight gap proxy for earnings)."""
    gap      = (close - close.shift(1)) / close.shift(1)
    gap_abs  = gap.abs()
    events   = close.index[gap_abs > threshold].tolist()
    return events, gap

# ─────────────────────────────────────────────
# STRATEGY: covered_call
# ─────────────────────────────────────────────

def run_covered_call(options_data):
    """
    Monthly covered call: sell 3% OTM call, 30d expiry.
    Logs one record per monthly period per ticker.
    """
    logger = TradeLogger(round_num=25, strategy='covered_call', category='options')

    for ticker, prices in options_data.items():
        close = get_close(prices)
        if len(close) < 252:
            continue

        rvol = calc_realized_vol(close, 20)

        monthly_idx = close.resample('MS').first().index
        monthly_idx = [idx for idx in monthly_idx
                       if idx in close.index or
                       close.index[close.index.searchsorted(idx)] < close.index[-1]]

        for i, entry_date in enumerate(monthly_idx[:-1]):
            idx_loc = close.index.searchsorted(entry_date)
            if idx_loc >= len(close) - 22:
                break

            S_entry   = float(close.iloc[idx_loc])
            vol_entry = float(rvol.iloc[idx_loc]) if not np.isnan(rvol.iloc[idx_loc]) else 0.20
            if vol_entry <= 0:
                vol_entry = 0.20

            # Strike 3% OTM
            K       = S_entry * 1.03
            T       = 30 / 365
            premium = bs_call(S_entry, K, T, vol_entry, r=RISK_FREE)

            exit_loc = min(idx_loc + 21, len(close) - 1)
            S_exit   = float(close.iloc[exit_loc])

            # Covered call payoff
            stock_return = (S_exit - S_entry) / S_entry
            if S_exit > K:
                cc_return = (K - S_entry + premium) / S_entry
            else:
                cc_return = stock_return + premium / S_entry

            actual_exit_date = close.index[exit_loc]
            hold_days = (actual_exit_date - close.index[idx_loc]).days

            logger.log(
                ticker            = ticker,
                entry_date        = close.index[idx_loc],
                exit_date         = actual_exit_date,
                return_pct        = cc_return,
                hold_days         = hold_days,
                direction         = 'short_call',
                entry_price       = S_entry,
                exit_price        = S_exit,
                strike            = K,
                option_type       = 'call',
                premium_collected = premium / S_entry,
                iv_at_entry       = vol_entry,
                params            = {'otm_pct': 0.03, 'expiry_days': 30},
                notes             = f'called_away={S_exit > K}',
            )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# STRATEGY: cash_secured_put
# ─────────────────────────────────────────────

def run_cash_secured_put(options_data):
    """
    Monthly cash-secured put: sell ATM put, 30d expiry.
    Logs one record per monthly period per ticker.
    """
    logger = TradeLogger(round_num=25, strategy='cash_secured_put', category='options')

    for ticker, prices in options_data.items():
        close = get_close(prices)
        if len(close) < 252:
            continue

        rvol        = calc_realized_vol(close, 20)
        monthly_idx = close.resample('MS').first().index

        for i, entry_date in enumerate(monthly_idx[:-1]):
            idx_loc = close.index.searchsorted(entry_date)
            if idx_loc >= len(close) - 22:
                break

            S_entry   = float(close.iloc[idx_loc])
            vol_entry = float(rvol.iloc[idx_loc]) if not np.isnan(rvol.iloc[idx_loc]) else 0.20
            if vol_entry <= 0:
                vol_entry = 0.20

            # ATM put
            K       = S_entry
            T       = 30 / 365
            premium = bs_put(S_entry, K, T, vol_entry, r=RISK_FREE)

            exit_loc = min(idx_loc + 21, len(close) - 1)
            S_exit   = float(close.iloc[exit_loc])

            if S_exit < K:
                # Assigned: loss = K - S_exit - premium, per dollar secured
                csp_return = -(K - S_exit - premium) / K
            else:
                # Keep premium
                csp_return = premium / K

            actual_exit_date = close.index[exit_loc]
            hold_days = (actual_exit_date - close.index[idx_loc]).days

            logger.log(
                ticker            = ticker,
                entry_date        = close.index[idx_loc],
                exit_date         = actual_exit_date,
                return_pct        = csp_return,
                hold_days         = hold_days,
                direction         = 'short_put',
                entry_price       = S_entry,
                exit_price        = S_exit,
                strike            = K,
                option_type       = 'put',
                premium_collected = premium / S_entry,
                iv_at_entry       = vol_entry,
                params            = {'strike_pct': 1.00, 'expiry_days': 30},
                notes             = f'assigned={S_exit < K}',
            )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# STRATEGY: earnings_straddle
# ─────────────────────────────────────────────

def run_earnings_straddle(pead_data):
    """
    Buy ATM straddle N days before a gap event; sell at gap day.
    entry_days_before in [5, 2, 1] (preserved from original harness).
    Logs one record per event per entry-timing per ticker.
    """
    logger = TradeLogger(round_num=25, strategy='earnings_straddle', category='options')

    entry_days_before = [5, 2, 1]

    for ticker, prices in pead_data.items():
        close = get_close(prices)
        if len(close) < 252:
            continue

        rvol        = calc_realized_vol(close, 20)
        gap_events, gap = find_gap_events(close, threshold=0.03)

        if len(gap_events) < 5:
            continue

        for n_before in entry_days_before:
            for event_date in gap_events:
                event_loc = close.index.get_loc(event_date)
                entry_loc = event_loc - n_before
                if entry_loc < 20:
                    continue

                S_entry   = float(close.iloc[entry_loc])
                vol_entry = float(rvol.iloc[entry_loc]) if not np.isnan(rvol.iloc[entry_loc]) else 0.20
                if vol_entry <= 0:
                    vol_entry = 0.20

                # ATM straddle cost
                K = S_entry
                T = (n_before + 1) / 365   # same as original
                T = max(T, 5 / 365)
                call_cost    = bs_call(S_entry, K, T, vol_entry, r=RISK_FREE)
                put_cost     = bs_put(S_entry, K, T, vol_entry, r=RISK_FREE)
                straddle_cost = call_cost + put_cost

                # At gap day: stock price
                S_gap  = float(close.iloc[event_loc])
                payoff = abs(S_gap - K) - straddle_cost
                pnl_pct = payoff / S_entry

                entry_date_actual = close.index[entry_loc]
                hold_days = (event_date - entry_date_actual).days

                logger.log(
                    ticker        = ticker,
                    entry_date    = entry_date_actual,
                    exit_date     = event_date,
                    return_pct    = pnl_pct,
                    hold_days     = hold_days,
                    direction     = 'long_straddle',
                    entry_price   = S_entry,
                    exit_price    = S_gap,
                    strike        = K,
                    option_type   = 'straddle',
                    premium_paid  = straddle_cost / S_entry,
                    iv_at_entry   = vol_entry,
                    params        = {'entry_days_before': n_before, 'gap_threshold': 0.03},
                    notes         = f'gap={float(gap.iloc[event_loc]) * 100:.2f}% n_before={n_before}',
                    gap_pct       = float(gap.iloc[event_loc]),
                )

    logger.save()
    return logger


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print('=' * 60)
    print('OPTIONS STRATEGIES HARNESS (framework v2) - Round 25')
    print('=' * 60)

    print('\n[1/3] Fetching options universe...')
    options_data = fetch_data(UNIVERSE_OPTIONS, START_DATE, END_DATE)
    print(f'  Loaded {len(options_data)} tickers')

    print('\n[2/3] Fetching PEAD universe...')
    pead_data = fetch_data(UNIVERSE_PEAD, START_DATE, END_DATE)
    print(f'  Loaded {len(pead_data)} tickers')

    print('\n[3/3] Running strategies...')

    print('\n  Running covered_call...')
    logger_cc = run_covered_call(options_data)
    print(f'    {len(logger_cc)} trade records logged')

    print('\n  Running cash_secured_put...')
    logger_csp = run_cash_secured_put(options_data)
    print(f'    {len(logger_csp)} trade records logged')

    print('\n  Running earnings_straddle...')
    logger_straddle = run_earnings_straddle(pead_data)
    print(f'    {len(logger_straddle)} trade records logged')

    print('\nDone.')


if __name__ == '__main__':
    main()
