#!/usr/bin/env python3
"""
intl_v2.py — International Equity Strategy Trade Logger (Framework v2)
=======================================================================
Replays all international equity strategy variants from intl_harness.py
and logs individual trades via TradeLogger.

Strategy variants (one logger each):
  intl_cross_country_momentum  — 12-1 month momentum, long top-3 / short bottom-3
  intl_dm_em_rotation          — DM/EM rotation via majority vote
  intl_global_momentum         — SPY/EFA/TLT rotation on 6-month momentum
  intl_country_pairs_{name}    — mean-reversion pairs (one per pair + combo)
  intl_em_momentum_dollar      — EM momentum filtered by USD weakness
  intl_valuation_momentum      — cheapest 3 countries with positive 3m momentum

round_num=1, category='international'

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/intl_v2.py
"""

import sys
import os
from pathlib import Path

# ── sys.path setup ─────────────────────────────────────────────────────────────
FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

from base_harness import TradeLogger, fetch_data, get_close

# ─── Universe ───────────────────────────────────────────────────────────────
DEVELOPED  = ['EWJ', 'EWG', 'EWU', 'EWC', 'EWA', 'EWQ', 'EWI', 'EWP', 'EWD', 'EWH']
EMERGING   = ['EEM', 'FXI', 'EWZ', 'INDA', 'EWY', 'EWW', 'EWT', 'TUR']
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

ROUND_NUM = 1

PAIRS = [
    ('EWG', 'EWU', 'Germany_UK'),
    ('EWJ', 'EWH', 'Japan_HK'),
    ('EWC', 'EWA', 'Canada_Australia'),
    ('EEM', 'VWO', 'EM_Broad_pair'),
    ('FXI', 'INDA', 'China_India'),
]

# ─── Helpers ─────────────────────────────────────────────────────────────────
def fetch_prices(tickers, start=START, end=END):
    print(f"Downloading {len(tickers)} tickers ...")
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

def monthly_reindex(prices):
    """Return last business day of each month prices."""
    return prices.resample('ME').last()

# ─── Strategy 1: Cross-Country Momentum ──────────────────────────────────────
def run_cross_country_momentum(prices, logger):
    """12-1 month momentum: long top 3, short bottom 3, monthly rebalance."""
    universe = [t for t in DEVELOPED + EMERGING if t in prices.columns]
    monthly  = monthly_reindex(prices[universe])
    daily_ret = returns(prices[universe])
    dates = monthly.index

    n_logged = 0
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
        d_next = dates[i+1] if i+1 < len(dates) else dates[-1]
        mask = (daily_ret.index > d_trade) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask]

        if period_rets.empty:
            continue

        hold_days_actual = len(period_rets)

        # Log each long position
        for t in longs:
            if t not in period_rets.columns:
                continue
            t_rets = period_rets[t].dropna()
            if len(t_rets) == 0:
                continue
            ret_pct = float((1 + t_rets).prod() - 1)
            entry_price = float(prices[t].asof(d_trade)) if t in prices.columns else float('nan')
            exit_price  = float(prices[t].asof(d_next))  if t in prices.columns else float('nan')
            logger.log(
                ticker        = t,
                entry_date    = d_trade,
                exit_date     = d_next,
                return_pct    = ret_pct,
                hold_days     = hold_days_actual,
                direction     = 'long',
                entry_price   = entry_price,
                exit_price    = exit_price,
                params        = {
                    'strategy':    'cross_country_momentum',
                    'signal':      '12-1 month momentum',
                    'top_n':       3,
                    'rebalance':   'monthly',
                },
                notes         = (
                    f"long leg; mom_score={mom.get(t, float('nan')):.4f}; "
                    f"longs={longs}; shorts={shorts}"
                ),
                momentum_score = float(mom.get(t, float('nan'))),
                leg            = 'long',
                longs          = longs,
                shorts         = shorts,
                country_name   = COUNTRY_NAMES.get(t, t),
            )
            n_logged += 1

        # Log each short position
        for t in shorts:
            if t not in period_rets.columns:
                continue
            t_rets = period_rets[t].dropna()
            if len(t_rets) == 0:
                continue
            ret_pct = float(-((1 + t_rets).prod() - 1))  # short = negative of return
            entry_price = float(prices[t].asof(d_trade)) if t in prices.columns else float('nan')
            exit_price  = float(prices[t].asof(d_next))  if t in prices.columns else float('nan')
            logger.log(
                ticker        = t,
                entry_date    = d_trade,
                exit_date     = d_next,
                return_pct    = ret_pct,
                hold_days     = hold_days_actual,
                direction     = 'short',
                entry_price   = entry_price,
                exit_price    = exit_price,
                params        = {
                    'strategy':    'cross_country_momentum',
                    'signal':      '12-1 month momentum',
                    'bottom_n':    3,
                    'rebalance':   'monthly',
                },
                notes         = (
                    f"short leg; mom_score={mom.get(t, float('nan')):.4f}; "
                    f"longs={longs}; shorts={shorts}"
                ),
                momentum_score = float(mom.get(t, float('nan'))),
                leg            = 'short',
                longs          = longs,
                shorts         = shorts,
                country_name   = COUNTRY_NAMES.get(t, t),
            )
            n_logged += 1

    print(f"  cross_country_momentum: {n_logged} trades logged")

# ─── Strategy 2: DM vs EM Rotation ───────────────────────────────────────────
def run_dm_em_rotation(prices, logger):
    """Rotate VEA/VWO using 3-month momentum, UUP regime, SPY MA regime."""
    needed = ['VEA', 'VWO', 'SPY', 'UUP']
    if not all(t in prices.columns for t in needed):
        print("  dm_em_rotation: missing tickers, skipping")
        return

    monthly   = monthly_reindex(prices[needed])
    daily_ret = returns(prices[needed])
    spy_200d  = prices['SPY'].rolling(200).mean()
    dates     = monthly.index

    n_logged = 0
    for i in range(4, len(dates)-1):
        d_3m  = dates[i-3]
        d_now = dates[i]
        d_next= dates[i+1]

        # Signal 1: relative 3m momentum
        vea_mom = monthly['VEA'].loc[d_now] / monthly['VEA'].loc[d_3m] - 1
        vwo_mom = monthly['VWO'].loc[d_now] / monthly['VWO'].loc[d_3m] - 1
        mom_signal = 'VEA' if vea_mom > vwo_mom else 'VWO'

        # Signal 2: UUP regime (20d momentum on UUP)
        uup_slice  = prices['UUP'].loc[:d_now].tail(21)
        uup_rising = uup_slice.iloc[-1] > uup_slice.iloc[0] if len(uup_slice) >= 2 else True
        uup_signal = 'VEA' if uup_rising else 'VWO'

        # Signal 3: SPY vs 200d MA
        spy_now = prices['SPY'].loc[:d_now].iloc[-1]
        spy_ma  = spy_200d.loc[:d_now].iloc[-1]
        spy_signal = 'VEA' if spy_now > spy_ma else 'VWO'

        # Majority vote
        votes  = [mom_signal, uup_signal, spy_signal]
        chosen = 'VEA' if votes.count('VEA') >= 2 else 'VWO'

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, chosen].dropna()

        if len(period_rets) == 0:
            continue

        ret_pct     = float((1 + period_rets).prod() - 1)
        hold_days   = len(period_rets)
        entry_price = float(prices[chosen].asof(d_now))
        exit_price  = float(prices[chosen].asof(d_next))

        logger.log(
            ticker      = chosen,
            entry_date  = d_now,
            exit_date   = d_next,
            return_pct  = ret_pct,
            hold_days   = hold_days,
            direction   = 'long',
            entry_price = entry_price,
            exit_price  = exit_price,
            params      = {
                'strategy':    'dm_em_rotation',
                'signal':      'majority vote of 3m momentum, UUP regime, SPY 200d MA',
                'rebalance':   'monthly',
            },
            notes       = (
                f"chosen={chosen}; mom_signal={mom_signal}; "
                f"uup_signal={uup_signal}; spy_signal={spy_signal}; "
                f"vea_mom={vea_mom:.4f}; vwo_mom={vwo_mom:.4f}"
            ),
            chosen      = chosen,
            mom_signal  = mom_signal,
            uup_signal  = uup_signal,
            spy_signal  = spy_signal,
            vea_mom     = float(vea_mom),
            vwo_mom     = float(vwo_mom),
            uup_rising  = bool(uup_rising),
        )
        n_logged += 1

    print(f"  dm_em_rotation: {n_logged} trades logged")

# ─── Strategy 3: US vs International Global Momentum ─────────────────────────
def run_global_momentum(prices, logger):
    """Rotate SPY / EFA / TLT based on 6-month relative momentum."""
    needed = ['SPY', 'EFA', 'TLT']
    if not all(t in prices.columns for t in needed):
        print("  global_momentum: missing tickers, skipping")
        return

    monthly   = monthly_reindex(prices[needed])
    daily_ret = returns(prices[needed])
    dates     = monthly.index

    n_logged = 0
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

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, chosen].dropna()

        if len(period_rets) == 0:
            continue

        ret_pct     = float((1 + period_rets).prod() - 1)
        hold_days   = len(period_rets)
        entry_price = float(prices[chosen].asof(d_now))
        exit_price  = float(prices[chosen].asof(d_next))

        logger.log(
            ticker      = chosen,
            entry_date  = d_now,
            exit_date   = d_next,
            return_pct  = ret_pct,
            hold_days   = hold_days,
            direction   = 'long',
            entry_price = entry_price,
            exit_price  = exit_price,
            params      = {
                'strategy':    'global_momentum',
                'signal':      '6-month momentum; TLT when both equity weak',
                'rebalance':   'monthly',
            },
            notes       = (
                f"chosen={chosen}; spy_mom={spy_mom:.4f}; "
                f"efa_mom={efa_mom:.4f}; tlt_mom={tlt_mom:.4f}"
            ),
            chosen      = chosen,
            spy_mom     = float(spy_mom),
            efa_mom     = float(efa_mom),
            tlt_mom     = float(tlt_mom),
        )
        n_logged += 1

    print(f"  global_momentum: {n_logged} trades logged")

# ─── Strategy 4: Country Pairs Trading ───────────────────────────────────────
def pairs_strategy_signals(prices, t1, t2, window=60, entry=1.5, exit_z=0.5):
    """Reproduce pairs_strategy from intl_harness.py; returns list of trade dicts."""
    if t1 not in prices.columns or t2 not in prices.columns:
        return []

    p1     = np.log(prices[t1])
    p2     = np.log(prices[t2])
    spread = p1 - p2

    roll_mean = spread.rolling(window).mean()
    roll_std  = spread.rolling(window).std()
    z = (spread - roll_mean) / roll_std

    r1_series = prices[t1].pct_change()
    r2_series = prices[t2].pct_change()

    position = 0  # 1 = long t1/short t2, -1 = reverse
    trade_start   = None
    trade_entry_p1 = None
    trade_entry_p2 = None
    daily_rets_in_trade = []
    trades = []

    idx = prices.index
    for i in range(1, len(idx)):
        zi      = z.iloc[i]
        zi_prev = z.iloc[i-1]
        if np.isnan(zi) or np.isnan(zi_prev):
            continue

        prev_position = position

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

        # Track trade open/close
        if prev_position == 0 and position != 0:
            trade_start    = idx[i]
            trade_entry_p1 = float(prices[t1].iloc[i])
            trade_entry_p2 = float(prices[t2].iloc[i])
            daily_rets_in_trade = []

        if prev_position != 0 and position == 0 and trade_start is not None:
            # Trade just closed
            trade_exit   = idx[i]
            exit_p1 = float(prices[t1].iloc[i])
            exit_p2 = float(prices[t2].iloc[i])
            hold_d  = (trade_exit - trade_start).days

            if len(daily_rets_in_trade) > 0:
                cum_ret = float(sum(daily_rets_in_trade))
            else:
                cum_ret = 0.0

            direction = 'long_spread' if prev_position == 1 else 'short_spread'
            trades.append({
                'entry_date':    trade_start,
                'exit_date':     trade_exit,
                'direction':     direction,
                'return_pct':    cum_ret,
                'hold_days':     hold_d,
                'entry_price_t1': trade_entry_p1,
                'entry_price_t2': trade_entry_p2,
                'exit_price_t1':  exit_p1,
                'exit_price_t2':  exit_p2,
                'z_at_entry':    float(z.iloc[i - hold_d]) if (i - hold_d) >= 0 else float('nan'),
            })
            trade_start = None
            daily_rets_in_trade = []

        # Accrue daily P&L
        if position != 0:
            r1 = r1_series.iloc[i]
            r2 = r2_series.iloc[i]
            if not (np.isnan(r1) or np.isnan(r2)):
                if position == 1:
                    daily_rets_in_trade.append(float(r1 - r2))
                else:
                    daily_rets_in_trade.append(float(r2 - r1))

    return trades

def run_country_pairs(prices, loggers):
    """Log each pair and the equal-weight combo."""
    all_pair_trades = {}

    for t1, t2, name in PAIRS:
        if t1 not in prices.columns or t2 not in prices.columns:
            print(f"  Skipping pair {name}: missing data")
            continue

        logger = loggers.get(f'intl_country_pairs_{name}')
        if logger is None:
            continue

        trade_list = pairs_strategy_signals(prices, t1, t2)
        all_pair_trades[name] = trade_list

        for trade in trade_list:
            logger.log(
                ticker       = f'{t1}/{t2}',
                entry_date   = trade['entry_date'],
                exit_date    = trade['exit_date'],
                return_pct   = trade['return_pct'],
                hold_days    = trade['hold_days'],
                direction    = trade['direction'],
                entry_price  = trade['entry_price_t1'],
                exit_price   = trade['exit_price_t1'],
                params       = {
                    'strategy':  f'country_pairs_{name}',
                    'ticker1':   t1,
                    'ticker2':   t2,
                    'z_window':  60,
                    'entry_z':   1.5,
                    'exit_z':    0.5,
                },
                notes        = (
                    f"pair={name}; direction={trade['direction']}; "
                    f"entry_p2={trade['entry_price_t2']:.4f}; "
                    f"exit_p2={trade['exit_price_t2']:.4f}"
                ),
                ticker1       = t1,
                ticker2       = t2,
                pair_name     = name,
                entry_price_t2 = trade['entry_price_t2'],
                exit_price_t2  = trade['exit_price_t2'],
                z_at_entry     = trade.get('z_at_entry', float('nan')),
            )

        print(f"  country_pairs_{name}: {len(trade_list)} trades logged")

    # Equal-weight combo logger: log all trades from all pairs
    combo_logger = loggers.get('intl_country_pairs_equal_weight_combo')
    if combo_logger is not None:
        total = 0
        for name, trade_list in all_pair_trades.items():
            t1_name, t2_name, _ = next(
                ((a, b, n) for a, b, n in PAIRS if n == name), (name, name, name)
            )
            for trade in trade_list:
                combo_logger.log(
                    ticker       = f'{t1_name}/{t2_name}',
                    entry_date   = trade['entry_date'],
                    exit_date    = trade['exit_date'],
                    return_pct   = trade['return_pct'],
                    hold_days    = trade['hold_days'],
                    direction    = trade['direction'],
                    entry_price  = trade['entry_price_t1'],
                    exit_price   = trade['exit_price_t1'],
                    params       = {
                        'strategy':  'country_pairs_equal_weight_combo',
                        'source_pair': name,
                        'z_window':  60,
                        'entry_z':   1.5,
                        'exit_z':    0.5,
                    },
                    notes        = f"combo; source_pair={name}",
                    pair_name    = name,
                    entry_price_t2 = trade['entry_price_t2'],
                    exit_price_t2  = trade['exit_price_t2'],
                )
                total += 1
        print(f"  country_pairs_equal_weight_combo: {total} trades logged")

# ─── Strategy 5: EM Momentum + Dollar Filter ─────────────────────────────────
def run_em_momentum_dollar(prices, logger):
    """EM ETFs with strongest 3-month momentum, filtered by USD weakness."""
    em_universe = [t for t in EMERGING if t in prices.columns]
    if 'UUP' not in prices.columns:
        print("  em_momentum_dollar: missing UUP, skipping")
        return

    monthly   = monthly_reindex(prices[em_universe + ['UUP']])
    daily_ret = returns(prices[em_universe])
    dates     = monthly.index

    n_logged = 0
    for i in range(4, len(dates)-1):
        d_3m  = dates[i-3]
        d_now = dates[i]
        d_next= dates[i+1]

        # UUP 20d momentum
        uup_slice    = prices['UUP'].loc[:d_now].tail(21)
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
        top3   = [t for t, _ in ranked[:3]]

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, top3]

        if period_rets.empty:
            continue

        hold_days = len(period_rets)

        for t in top3:
            if t not in period_rets.columns:
                continue
            t_rets = period_rets[t].dropna()
            if len(t_rets) == 0:
                continue

            # Filtered: invested only when USD weakening; else 0 return recorded
            if usd_weakening:
                ret_pct   = float((1 + t_rets).prod() - 1)
                invested  = True
            else:
                ret_pct   = 0.0
                invested  = False

            entry_price = float(prices[t].asof(d_now))
            exit_price  = float(prices[t].asof(d_next))

            logger.log(
                ticker          = t,
                entry_date      = d_now,
                exit_date       = d_next,
                return_pct      = ret_pct,
                hold_days       = hold_days,
                direction       = 'long',
                entry_price     = entry_price,
                exit_price      = exit_price,
                params          = {
                    'strategy':       'em_momentum_dollar_filter',
                    'signal':         'top-3 EM 3m momentum, USD weakness filter',
                    'rebalance':      'monthly',
                    'top_n':          3,
                },
                notes           = (
                    f"usd_weakening={usd_weakening}; invested={invested}; "
                    f"mom_score={mom.get(t, float('nan')):.4f}; top3={top3}"
                ),
                usd_weakening   = bool(usd_weakening),
                invested        = bool(invested),
                momentum_score  = float(mom.get(t, float('nan'))),
                top3            = top3,
                country_name    = COUNTRY_NAMES.get(t, t),
            )
            n_logged += 1

    print(f"  em_momentum_dollar: {n_logged} trades logged")

# ─── Strategy 6: Valuation-Momentum Combo ────────────────────────────────────
def run_valuation_momentum(prices, logger):
    """Cheapest 3 countries (lowest 3yr return) with positive 3m momentum, annual rebalance."""
    universe  = [t for t in DEVELOPED + EMERGING if t in prices.columns]
    monthly   = monthly_reindex(prices[universe])
    daily_ret = returns(prices[universe])

    annual_dates = [d for d in monthly.index if d.month == 1]

    n_logged = 0
    for i in range(1, len(annual_dates)-1):
        d_3yr  = annual_dates[i] - pd.DateOffset(years=3)
        d_3m   = annual_dates[i] - pd.DateOffset(months=3)
        d_now  = annual_dates[i]
        d_next = annual_dates[i+1]

        val_mom = {}
        for t in universe:
            try:
                p_3yr = monthly[t].asof(d_3yr)
                p_3m  = monthly[t].asof(d_3m)
                p_now = monthly[t].asof(d_now)
                if pd.isna(p_3yr) or pd.isna(p_3m) or pd.isna(p_now):
                    continue
                val  = p_now / p_3yr - 1
                mom3 = p_now / p_3m - 1
                val_mom[t] = (val, mom3)
            except Exception:
                pass

        if len(val_mom) < 6:
            continue

        sorted_by_val = sorted(val_mom.items(), key=lambda x: x[1][0])
        candidates    = [(t, v) for t, v in sorted_by_val if v[1] > 0]
        if len(candidates) < 3:
            candidates = sorted_by_val[:3]

        top3 = [t for t, _ in candidates[:3]]

        mask = (daily_ret.index > d_now) & (daily_ret.index <= d_next)
        period_rets = daily_ret.loc[mask, top3]
        if period_rets.empty:
            continue

        hold_days = len(period_rets)

        for t in top3:
            if t not in period_rets.columns:
                continue
            t_rets = period_rets[t].dropna()
            if len(t_rets) == 0:
                continue

            val_score, mom3_score = val_mom.get(t, (float('nan'), float('nan')))
            ret_pct     = float((1 + t_rets).prod() - 1)
            entry_price = float(prices[t].asof(d_now))
            exit_price  = float(prices[t].asof(d_next))

            logger.log(
                ticker           = t,
                entry_date       = d_now,
                exit_date        = d_next,
                return_pct       = ret_pct,
                hold_days        = hold_days,
                direction        = 'long',
                entry_price      = entry_price,
                exit_price       = exit_price,
                params           = {
                    'strategy':   'valuation_momentum',
                    'signal':     'cheapest 3 (3yr return) with positive 3m momentum',
                    'rebalance':  'annual',
                    'top_n':      3,
                },
                notes            = (
                    f"val_score={val_score:.4f}; mom3={mom3_score:.4f}; top3={top3}"
                ),
                val_score        = float(val_score),
                mom3_score       = float(mom3_score),
                top3             = top3,
                country_name     = COUNTRY_NAMES.get(t, t),
            )
            n_logged += 1

    print(f"  valuation_momentum: {n_logged} trades logged")

# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("International Equity Strategy Harness v2 — Trade Logger")
    print("=" * 60)

    prices  = fetch_prices(ALL_TICKERS)
    spy_rets_series = prices['SPY'].pct_change().dropna() if 'SPY' in prices.columns else None

    # Build all loggers
    pair_names_for_loggers = [name for _, _, name in PAIRS] + ['equal_weight_combo']
    loggers = {}

    loggers['cross_country_momentum'] = TradeLogger(
        round_num=ROUND_NUM, strategy='intl_cross_country_momentum', category='international'
    )
    loggers['dm_em_rotation'] = TradeLogger(
        round_num=ROUND_NUM, strategy='intl_dm_em_rotation', category='international'
    )
    loggers['global_momentum'] = TradeLogger(
        round_num=ROUND_NUM, strategy='intl_global_momentum', category='international'
    )
    for pname in pair_names_for_loggers:
        key = f'intl_country_pairs_{pname}'
        loggers[f'intl_country_pairs_{pname}'] = TradeLogger(
            round_num=ROUND_NUM, strategy=key, category='international'
        )
    loggers['em_momentum_dollar'] = TradeLogger(
        round_num=ROUND_NUM, strategy='intl_em_momentum_dollar', category='international'
    )
    loggers['valuation_momentum'] = TradeLogger(
        round_num=ROUND_NUM, strategy='intl_valuation_momentum', category='international'
    )

    # Run each strategy and log trades
    print("\n[1/6] Cross-Country Momentum ...")
    try:
        run_cross_country_momentum(prices, loggers['cross_country_momentum'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[2/6] DM/EM Rotation ...")
    try:
        run_dm_em_rotation(prices, loggers['dm_em_rotation'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[3/6] Global Momentum Rotation ...")
    try:
        run_global_momentum(prices, loggers['global_momentum'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[4/6] Country Pairs Trading ...")
    try:
        run_country_pairs(prices, loggers)
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[5/6] EM Momentum + Dollar Filter ...")
    try:
        run_em_momentum_dollar(prices, loggers['em_momentum_dollar'])
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n[6/6] Valuation-Momentum Combo ...")
    try:
        run_valuation_momentum(prices, loggers['valuation_momentum'])
    except Exception as e:
        print(f"  ERROR: {e}")

    # Save all trade logs
    print("\nSaving trade logs...")
    for key, logger in loggers.items():
        logger.save()

    print("\nDone.")
    for key, logger in loggers.items():
        print(f"  {key}: {len(logger)} trades")

if __name__ == '__main__':
    main()
