"""
R28 Options Deep Dive: Wheel, Multi-Leg, Greeks
================================================
Evaluates 5 advanced options strategies using Black-Scholes simulation
against historical price data (2020-2025).

Strategies:
  1. Wheel Strategy       – CSP → assignment → CC → called away → repeat
  2. Iron Condor + IV Rank – sell condor when realized vol percentile is high
  3. Bull Put Spread       – defined-risk premium selling with IV rank filter
  4. VRP Harvesting        – sell straddle exploiting implied > realized vol gap
  5. Gamma Scalping        – buy straddle, delta-hedge daily, profit when RV > IV

Key assumption: IV is proxied as realized_vol * (1 + IV_PREMIUM) where
IV_PREMIUM = 0.03, reflecting the well-documented volatility risk premium
(implied vol is ~2-3 percentage points higher than realized on average).
This lets premium-selling strategies capture the VRP in simulation.

Author: George (NanoClaw R28)
Date: 2026-04-01
"""

import sys
import subprocess

def ensure_deps():
    pkgs = ['yfinance', 'scipy', 'numpy', 'pandas']
    for pkg in pkgs:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', pkg,
                '--break-system-packages', '--quiet'
            ])

ensure_deps()

import json
import os
import warnings
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import datetime, timedelta
import time

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

# Broad universe: liquid names across sectors, mix of growth + value
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'KO',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'T',   'VZ',  'IBM', 'MO',  'PFE',
    'COST','NFLX','QCOM','TXN', 'GE'
]

START_DATE  = '2020-01-01'
END_DATE    = '2025-12-31'
RISK_FREE   = 0.045
IV_PREMIUM  = 0.03   # Implied vol premium over realized (VRP)

CACHE_DIR = '/workspace/group/trading_eval/cache'
ROUNDS_DIR = '/workspace/group/trading_eval/rounds'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ROUNDS_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# BLACK-SCHOLES
# ─────────────────────────────────────────────

def bs_call(S, K, T, sigma, r=RISK_FREE):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return float(S * norm.cdf(d1) - K * np.exp(-r*T) * norm.cdf(d2))

def bs_put(S, K, T, sigma, r=RISK_FREE):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return float(K * np.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1))

def bs_delta_call(S, K, T, sigma, r=RISK_FREE):
    """Delta of a call option (∂C/∂S)."""
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return float(norm.cdf(d1))

def bs_delta_put(S, K, T, sigma, r=RISK_FREE):
    """Delta of a put option (∂P/∂S)."""
    return bs_delta_call(S, K, T, sigma, r) - 1.0

# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_data(tickers, start, end, retries=3):
    import yfinance as yf
    all_data = {}
    for ticker in tickers:
        cache_file = os.path.join(CACHE_DIR, f"{ticker}_{start}_{end}.pkl")
        if os.path.exists(cache_file):
            try:
                df = pd.read_pickle(cache_file)
                if len(df) > 100:
                    all_data[ticker] = df
                    continue
            except Exception:
                pass
        for attempt in range(retries):
            try:
                df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
                if df is not None and len(df) > 100:
                    df.to_pickle(cache_file)
                    all_data[ticker] = df
                    break
                time.sleep(0.5)
            except Exception as e:
                if attempt == retries - 1:
                    print(f"  Failed {ticker}: {e}")
                time.sleep(1)
    return all_data

def get_close(prices):
    """Extract clean Close series from yfinance DataFrame."""
    c = prices['Close']
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c = c.squeeze()
    return c.dropna()

# ─────────────────────────────────────────────
# VOLATILITY HELPERS
# ─────────────────────────────────────────────

def realized_vol(close, window=20):
    """Annualized realized vol (rolling)."""
    log_ret = np.log(close / close.shift(1)).dropna()
    return log_ret.rolling(window).std() * np.sqrt(252)

def iv_estimate(close, window=20):
    """
    Proxy for implied vol: realized_vol * (1 + IV_PREMIUM).
    Reflects that IV is systematically ~3% above realized.
    """
    rv = realized_vol(close, window)
    return rv * (1 + IV_PREMIUM)

def iv_rank(iv_series, lookback=252):
    """
    Percentile rank of current IV vs trailing lookback days.
    0 = historically cheap options, 100 = historically expensive.
    """
    return iv_series.rolling(lookback).rank(pct=True) * 100

def calc_sharpe(returns, annualize=12):
    r = np.array(returns)
    if len(r) < 5 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(annualize))

def calc_max_dd(equity_curve):
    eq = np.array(equity_curve)
    if len(eq) < 2:
        return 0.0
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(dd.min())

# ─────────────────────────────────────────────
# STRATEGY 1: WHEEL STRATEGY
# ─────────────────────────────────────────────

def run_wheel(ticker, prices):
    """
    Full wheel cycle:
      Phase A – SELL CSP: Sell ATM cash-secured put. If expires worthless → keep prem.
                If assigned (S < K) → acquire stock at K, move to Phase B.
      Phase B – SELL CC:  Sell CC at cost basis (K from assignment). If called away →
                return to Phase A. If expires worthless → sell new CC next month.

    Returns monthly returns across the full cycle.
    Key metric: does the wheel beat simple buy-and-hold on the same stock?
    """
    close = get_close(prices)
    if len(close) < 252:
        return None

    iv = iv_estimate(close, 20)
    monthly_idx = close.resample('MS').first().index
    valid_dates = [d for d in monthly_idx if d in close.index or close.index.searchsorted(d) < len(close)]

    phase       = 'CSP'          # CSP or CC
    stock_held  = 0.0            # number of shares (0 or 1 per $K notional)
    cost_basis  = 0.0            # price we were assigned at
    equity      = [1.0]
    cash        = 1.0            # normalized capital
    monthly_returns = []
    csp_trades  = []
    cc_trades   = []

    for i, entry_date in enumerate(valid_dates[:-1]):
        idx_loc = close.index.searchsorted(entry_date)
        exit_loc = min(idx_loc + 21, len(close) - 1)

        if idx_loc >= len(close) - 1:
            break

        S_entry = float(close.iloc[idx_loc])
        S_exit  = float(close.iloc[exit_loc])
        vol_now = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        if vol_now <= 0:
            vol_now = 0.22

        T = 21 / 365

        if phase == 'CSP':
            # Sell ATM put
            K = S_entry
            prem = bs_put(S_entry, K, T, vol_now)
            prem_pct = prem / K  # as fraction of cash secured

            if S_exit < K:
                # Assigned: acquire stock at K, lose (K - S_exit) but keep premium
                assignment_loss = (K - S_exit) / K
                trade_return = prem_pct - assignment_loss
                phase       = 'CC'
                stock_held  = 1.0
                cost_basis  = K  # our effective cost = K - prem, but track K for simplicity
                csp_trades.append({'type': 'assigned', 'ret': trade_return})
            else:
                # Expires worthless: keep premium
                trade_return = prem_pct
                csp_trades.append({'type': 'expired', 'ret': trade_return})
                # phase stays CSP

        else:  # phase == 'CC'
            # Sell CC at cost_basis (ATM relative to cost basis)
            K = cost_basis
            prem = bs_call(S_entry, K, T, vol_now)
            prem_pct = prem / S_entry

            if S_exit > K:
                # Called away: sell at K, gain = (K - cost_basis)/cost_basis + prem_pct
                stock_gain = (K - cost_basis) / cost_basis
                trade_return = stock_gain + prem_pct
                phase       = 'CSP'
                stock_held  = 0.0
                cc_trades.append({'type': 'called_away', 'ret': trade_return})
            else:
                # Expires worthless: keep stock + premium
                unrealized = (S_exit - S_entry) / S_entry
                trade_return = unrealized + prem_pct
                # Update cost_basis to current S_entry for next month
                cost_basis = S_entry
                cc_trades.append({'type': 'held', 'ret': trade_return})

        monthly_returns.append(trade_return)
        equity.append(equity[-1] * (1 + trade_return))

    # Buy-and-hold comparison
    bh_close = close.loc[close.index >= valid_dates[0]]
    bh_close = bh_close.loc[bh_close.index <= valid_dates[-1]]
    bh_return = (float(bh_close.iloc[-1]) / float(bh_close.iloc[0])) - 1

    if len(monthly_returns) < 10:
        return None

    total_ret = equity[-1] - 1
    years = len(monthly_returns) / 12
    ann_ret = (equity[-1] ** (1/years) - 1) if years > 0 else 0
    ann_bh  = ((1 + bh_return) ** (1/years) - 1) if years > 0 else 0
    sharpe  = calc_sharpe(monthly_returns, annualize=12)
    max_dd  = calc_max_dd(equity)

    n_assigned  = sum(1 for t in csp_trades if t['type'] == 'assigned')
    n_called    = sum(1 for t in cc_trades  if t['type'] == 'called_away')
    n_full_cycles = min(n_assigned, n_called)
    avg_prem_csp = float(np.mean([t['ret'] for t in csp_trades])) if csp_trades else 0
    avg_prem_cc  = float(np.mean([t['ret'] for t in cc_trades]))  if cc_trades  else 0

    return {
        'ticker':        ticker,
        'strategy':      f'wheel_{ticker}',
        'sharpe':        round(sharpe, 4),
        'total_return':  round(total_ret, 4),
        'ann_return':    round(ann_ret, 4),
        'vs_bh':         round(ann_ret - ann_bh, 4),
        'bh_annual':     round(ann_bh, 4),
        'max_dd':        round(max_dd, 4),
        'n_months':      len(monthly_returns),
        'n_csp_trades':  len(csp_trades),
        'n_cc_trades':   len(cc_trades),
        'n_assignments': n_assigned,
        'n_called_away': n_called,
        'n_full_cycles': n_full_cycles,
        'avg_prem_csp':  round(avg_prem_csp, 4),
        'avg_prem_cc':   round(avg_prem_cc, 4),
    }

# ─────────────────────────────────────────────
# STRATEGY 2: IRON CONDOR with IV RANK FILTER
# ─────────────────────────────────────────────

def run_iron_condor(ticker, prices, iv_rank_threshold=50.0):
    """
    Iron Condor:
      Sell 5% OTM call + Buy 10% OTM call (call spread)
      Sell 5% OTM put  + Buy 10% OTM put  (put spread)
      Enter only when IV rank > threshold (sell when options are expensive).
      Hold 30 days. Max profit = net premium. Max loss = wing width - premium.
    """
    close = get_close(prices)
    if len(close) < 300:  # need 252 for IV rank lookback
        return None

    iv = iv_estimate(close, 20)
    ivr = iv_rank(iv, lookback=252)
    monthly_idx = close.resample('MS').first().index

    returns = []
    equity  = [1.0]
    n_entered = 0
    n_skipped = 0
    n_max_loss = 0

    for entry_date in monthly_idx[:-1]:
        idx_loc = close.index.searchsorted(entry_date)
        if idx_loc >= len(close) - 22 or idx_loc < 252:
            continue

        current_ivr = float(ivr.iloc[idx_loc])
        if np.isnan(current_ivr):
            continue

        if current_ivr < iv_rank_threshold:
            n_skipped += 1
            continue

        S = float(close.iloc[idx_loc])
        vol = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        if vol <= 0:
            vol = 0.22

        T = 30 / 365

        # Define strikes
        K_call_sell = S * 1.05   # sell 5% OTM call
        K_call_buy  = S * 1.10   # buy  10% OTM call (wing)
        K_put_sell  = S * 0.95   # sell 5% OTM put
        K_put_buy   = S * 0.90   # buy  10% OTM put (wing)

        # Premiums at entry
        c_sell = bs_call(S, K_call_sell, T, vol)
        c_buy  = bs_call(S, K_call_buy,  T, vol)
        p_sell = bs_put(S, K_put_sell,   T, vol)
        p_buy  = bs_put(S, K_put_buy,    T, vol)

        net_credit = (c_sell - c_buy) + (p_sell - p_buy)
        if net_credit <= 0:
            continue

        wing_width = S * 0.05   # 5% = max risk per spread
        max_loss   = wing_width - net_credit   # per spread, per side
        max_loss_condor = max_loss  # loss if one side goes deep ITM

        # Exit after 30 calendar days
        exit_loc = min(idx_loc + 21, len(close) - 1)
        S_exit = float(close.iloc[exit_loc])

        # Calculate PnL: intrinsic value of short options at exit
        # Call spread: if S_exit > K_call_sell, short call is ITM
        if S_exit > K_call_buy:
            call_spread_loss = wing_width  # full loss on call side
        elif S_exit > K_call_sell:
            call_spread_loss = S_exit - K_call_sell
        else:
            call_spread_loss = 0.0

        # Put spread: if S_exit < K_put_sell, short put is ITM
        if S_exit < K_put_buy:
            put_spread_loss = wing_width  # full loss on put side
        elif S_exit < K_put_sell:
            put_spread_loss = K_put_sell - S_exit
        else:
            put_spread_loss = 0.0

        total_loss = call_spread_loss + put_spread_loss
        pnl = net_credit - total_loss
        pnl_pct = pnl / S  # as fraction of underlying price (capital at risk = 2 * wing_width)

        # Normalize by capital at risk (max_loss_condor per condor)
        capital_at_risk = max(max_loss_condor, 0.01 * S)
        pnl_on_risk = pnl / capital_at_risk if capital_at_risk > 0 else 0.0

        # Clip to avoid extreme outliers from tiny credit
        pnl_on_risk = float(np.clip(pnl_on_risk, -3.0, 3.0))

        returns.append(pnl_pct)
        equity.append(equity[-1] * (1 + pnl_pct))
        n_entered += 1
        if total_loss >= max_loss_condor:
            n_max_loss += 1

    if n_entered < 8:
        return None

    wins = sum(1 for r in returns if r > 0)
    sharpe  = calc_sharpe(returns, annualize=12)
    max_dd  = calc_max_dd(equity)
    total_ret = equity[-1] - 1

    return {
        'ticker':       ticker,
        'strategy':     f'iron_condor_{ticker}',
        'sharpe':       round(sharpe, 4),
        'total_return': round(total_ret, 4),
        'max_dd':       round(max_dd, 4),
        'win_rate':     round(wins / n_entered, 4),
        'n_entered':    n_entered,
        'n_skipped':    n_skipped,
        'n_max_loss':   n_max_loss,
        'entry_rate':   round(n_entered / max(n_entered + n_skipped, 1), 4),
        'avg_return':   round(float(np.mean(returns)), 4),
        'iv_rank_threshold': iv_rank_threshold,
    }

# ─────────────────────────────────────────────
# STRATEGY 3: BULL PUT SPREAD with IV RANK
# ─────────────────────────────────────────────

def run_bull_put_spread(ticker, prices, iv_rank_threshold=50.0):
    """
    Bull Put Spread (defined-risk premium selling):
      Sell ATM put, buy 5% OTM put
      Enter when IV rank > threshold (expensive options)
      Directional bias: bullish (profits if stock stays flat or rises)
      Defined max risk = width of spread - premium

    Compares vs simply selling naked CSP on same entry days.
    """
    close = get_close(prices)
    if len(close) < 300:
        return None

    iv  = iv_estimate(close, 20)
    ivr = iv_rank(iv, lookback=252)
    monthly_idx = close.resample('MS').first().index

    spread_returns  = []
    naked_returns   = []
    equity_spread   = [1.0]
    equity_naked    = [1.0]
    n_entered = 0

    for entry_date in monthly_idx[:-1]:
        idx_loc = close.index.searchsorted(entry_date)
        if idx_loc >= len(close) - 22 or idx_loc < 252:
            continue

        current_ivr = float(ivr.iloc[idx_loc])
        if np.isnan(current_ivr) or current_ivr < iv_rank_threshold:
            continue

        S   = float(close.iloc[idx_loc])
        vol = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        if vol <= 0:
            vol = 0.22

        T  = 30 / 365
        K_sell = S          # sell ATM put
        K_buy  = S * 0.95   # buy 5% OTM put (wing)
        wing   = K_sell - K_buy   # = 0.05 * S

        p_sell = bs_put(S, K_sell, T, vol)
        p_buy  = bs_put(S, K_buy,  T, vol)
        net_credit = p_sell - p_buy

        if net_credit <= 0:
            continue

        exit_loc = min(idx_loc + 21, len(close) - 1)
        S_exit   = float(close.iloc[exit_loc])

        # Bull put spread P&L at expiry
        if S_exit >= K_sell:
            spread_pnl = net_credit  # full profit: both puts expire worthless
        elif S_exit <= K_buy:
            spread_pnl = net_credit - wing  # full loss: capped by wing
        else:
            spread_pnl = net_credit - (K_sell - S_exit)  # partial loss

        # Naked CSP P&L at expiry
        naked_prem = bs_put(S, K_sell, T, vol)
        if S_exit >= K_sell:
            naked_pnl = naked_prem
        else:
            naked_pnl = naked_prem - (K_sell - S_exit)

        # Normalize by capital secured (K for naked, wing for spread)
        spread_ret = spread_pnl / wing if wing > 0 else 0.0
        naked_ret  = naked_pnl  / K_sell

        # Clip at -1 / +2
        spread_ret = float(np.clip(spread_ret, -1.0, 2.0))
        naked_ret  = float(np.clip(naked_ret, -1.0, 2.0))

        spread_returns.append(spread_ret)
        naked_returns.append(naked_ret)
        equity_spread.append(equity_spread[-1] * (1 + spread_ret))
        equity_naked.append(equity_naked[-1] * (1 + naked_ret))
        n_entered += 1

    if n_entered < 8:
        return None

    wins_spread = sum(1 for r in spread_returns if r > 0)
    wins_naked  = sum(1 for r in naked_returns  if r > 0)

    sharpe_spread = calc_sharpe(spread_returns, annualize=12)
    sharpe_naked  = calc_sharpe(naked_returns,  annualize=12)
    max_dd_spread = calc_max_dd(equity_spread)
    max_dd_naked  = calc_max_dd(equity_naked)

    return {
        'ticker':           ticker,
        'strategy':         f'bull_put_spread_{ticker}',
        'sharpe_spread':    round(sharpe_spread, 4),
        'sharpe_naked_csp': round(sharpe_naked,  4),
        'sharpe':           round(sharpe_spread, 4),  # primary metric
        'win_rate_spread':  round(wins_spread / n_entered, 4),
        'win_rate_naked':   round(wins_naked  / n_entered, 4),
        'max_dd_spread':    round(max_dd_spread, 4),
        'max_dd_naked':     round(max_dd_naked,  4),
        'total_return':     round(equity_spread[-1] - 1, 4),
        'n_entered':        n_entered,
    }

# ─────────────────────────────────────────────
# STRATEGY 4: VRP HARVESTING (SELL STRADDLE)
# ─────────────────────────────────────────────

def run_vrp_harvest(ticker, prices, iv_rank_threshold=40.0):
    """
    Volatility Risk Premium (VRP) Harvesting:
      The VRP is the persistent premium between implied vol (IV) and
      realized vol (RV). Implied vol is ~3% above realized on average
      (Carr & Wu 2009, Simon & Campasano 2014). This simulation models
      that gap via IV_PREMIUM.

    Strategy: sell ATM straddle when IV rank is elevated (options expensive).
      Premium collected at BS price (uses IV = RV * 1.03).
      Payoff at expiry = |S_exit - K| (intrinsic value we're short).
      Since IV > RV on average, premium > realized move → positive edge.

    Also tests: simple monthly straddle sale regardless of IV rank.
    """
    close = get_close(prices)
    if len(close) < 300:
        return None

    iv  = iv_estimate(close, 20)  # IV = RV * (1 + IV_PREMIUM)
    rv  = realized_vol(close, 20) # RV (no premium)
    ivr = iv_rank(iv, lookback=252)
    monthly_idx = close.resample('MS').first().index

    vrp_returns   = []   # IV-rank filtered straddle sales
    always_returns = []  # always sell straddle (no filter)
    equity_vrp    = [1.0]
    equity_always = [1.0]
    n_filtered = 0

    for entry_date in monthly_idx[:-1]:
        idx_loc = close.index.searchsorted(entry_date)
        if idx_loc >= len(close) - 22 or idx_loc < 252:
            continue

        S   = float(close.iloc[idx_loc])
        iv_now = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        rv_now = float(rv.iloc[idx_loc]) if not np.isnan(rv.iloc[idx_loc]) else 0.20
        if iv_now <= 0:
            iv_now = 0.22
        if rv_now <= 0:
            rv_now = 0.20

        T  = 30 / 365
        K  = S  # ATM straddle

        # Premium collected using IV (= RV * 1.03): options are "overpriced" vs realized
        call_prem_iv = bs_call(S, K, T, iv_now)
        put_prem_iv  = bs_put(S, K, T, iv_now)
        straddle_prem = call_prem_iv + put_prem_iv

        exit_loc = min(idx_loc + 21, len(close) - 1)
        S_exit   = float(close.iloc[exit_loc])

        # Short straddle payoff at expiry: prem_collected - |S_exit - K|
        move     = abs(S_exit - K)
        pnl      = straddle_prem - move
        pnl_pct  = pnl / S

        # Clip to avoid catastrophic single trades
        pnl_pct  = float(np.clip(pnl_pct, -0.50, 0.50))

        # Always version: trade regardless of IV rank
        always_returns.append(pnl_pct)
        equity_always.append(equity_always[-1] * (1 + pnl_pct))

        # IV rank filtered version
        current_ivr = float(ivr.iloc[idx_loc])
        if not np.isnan(current_ivr) and current_ivr >= iv_rank_threshold:
            vrp_returns.append(pnl_pct)
            equity_vrp.append(equity_vrp[-1] * (1 + pnl_pct))
            n_filtered += 1

    if len(always_returns) < 10:
        return None

    wins_always  = sum(1 for r in always_returns if r > 0)
    wins_filtered = sum(1 for r in vrp_returns   if r > 0) if vrp_returns else 0

    sharpe_always   = calc_sharpe(always_returns, annualize=12)
    sharpe_filtered = calc_sharpe(vrp_returns,    annualize=12) if vrp_returns else 0.0
    max_dd_always   = calc_max_dd(equity_always)
    max_dd_filtered = calc_max_dd(equity_vrp) if equity_vrp else 0.0

    # VRP metrics: avg premium collected vs avg realized move
    avg_premium = float(np.mean([straddle_prem for _ in always_returns]))  # approx
    avg_move_pct = float(np.mean([abs(close.iloc[min(close.index.searchsorted(d) + 21, len(close)-1)]
                                      / float(close.iloc[close.index.searchsorted(d)]) - 1)
                                  for d in monthly_idx[:-1]
                                  if close.index.searchsorted(d) < len(close) - 22
                                  and close.index.searchsorted(d) >= 252]))

    return {
        'ticker':            ticker,
        'strategy':          f'vrp_harvest_{ticker}',
        'sharpe_always':     round(sharpe_always,   4),
        'sharpe_iv_filtered': round(sharpe_filtered, 4),
        'sharpe':            round(sharpe_filtered if vrp_returns else sharpe_always, 4),
        'win_rate_always':   round(wins_always / len(always_returns), 4),
        'win_rate_filtered': round(wins_filtered / max(n_filtered, 1), 4),
        'max_dd_always':     round(max_dd_always,   4),
        'max_dd_filtered':   round(max_dd_filtered, 4),
        'total_return':      round(equity_vrp[-1] - 1 if equity_vrp else 0.0, 4),
        'n_always':          len(always_returns),
        'n_filtered':        n_filtered,
        'avg_move_pct':      round(avg_move_pct, 4),
    }

# ─────────────────────────────────────────────
# STRATEGY 5: GAMMA SCALPING
# ─────────────────────────────────────────────

def run_gamma_scalp(ticker, prices, hedge_freq_days=5):
    """
    Gamma Scalping (Long Gamma / Delta-Neutral):
      1. Buy ATM straddle at start of period
      2. Delta-hedge every N trading days (rebalance stock position to stay neutral)
      3. P&L = realized vol gains from rehedging MINUS theta decay

    Profit condition: realized vol > implied vol (RV > IV)
    The simulation uses IV = RV * (1 + IV_PREMIUM), so by construction:
      - IV is always slightly above RV
      - Gamma scalping should be slightly negative (theta > gamma profits)
      - But for high-vol events where RV spikes >> IV, it can be positive

    This tests the realistic result: gamma scalping is a slight drag on average
    because you're paying the VRP (buying expensive options).
    """
    close = get_close(prices)
    if len(close) < 252:
        return None

    iv = iv_estimate(close, 20)
    rv = realized_vol(close, 20)
    monthly_idx = close.resample('MS').first().index

    returns      = []
    equity       = [1.0]
    n_positive   = 0  # months where RV > IV (gamma scalp wins)
    n_negative   = 0  # months where RV < IV (theta dominates)

    for entry_date in monthly_idx[:-1]:
        idx_loc  = close.index.searchsorted(entry_date)
        exit_loc = min(idx_loc + 21, len(close) - 1)

        if idx_loc >= len(close) - 22 or idx_loc < 20:
            continue

        S0   = float(close.iloc[idx_loc])
        iv_entry = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        if iv_entry <= 0:
            iv_entry = 0.22

        T0 = 21 / 365
        K  = S0  # ATM straddle

        # Cost to buy straddle (at IV price = expensive options)
        call_cost = bs_call(S0, K, T0, iv_entry)
        put_cost  = bs_put(S0, K, T0, iv_entry)
        straddle_cost = call_cost + put_cost

        # Delta-hedging P&L simulation over 21-day holding period
        hedge_pnl  = 0.0
        delta_prev = 0.0  # start delta-neutral (long straddle is near 0 delta)
        S_prev     = S0

        # Simulate daily price path (use actual prices if available)
        locs = range(idx_loc, min(exit_loc + 1, len(close)))
        for j, loc in enumerate(locs):
            S_curr = float(close.iloc[loc])
            T_rem  = max((exit_loc - loc) / 252, 1/365)

            # Current option delta (net delta of long ATM straddle ≈ 0 at entry,
            # drifts as stock moves)
            call_delta = bs_delta_call(S_curr, K, T_rem, iv_entry)
            put_delta  = bs_delta_put(S_curr, K, T_rem, iv_entry)
            net_delta  = call_delta + put_delta  # long call + long put

            # Hedge every hedge_freq_days: trade stock to neutralize delta
            if j % hedge_freq_days == 0 and j > 0:
                # We need to trade (net_delta - delta_prev) shares
                delta_change = net_delta - delta_prev
                # PnL from hedge: -delta_change * S_curr (cost to rebalance)
                # But gamma scalp earns: the stock moved (S_curr - S_prev) * delta_prev
                gamma_pnl = delta_prev * (S_curr - S_prev)
                hedge_pnl += gamma_pnl
                delta_prev = net_delta
                S_prev     = S_curr

        # Final value of straddle at expiry
        straddle_value = abs(float(close.iloc[exit_loc]) - K)

        # Total P&L: straddle gain/loss + gamma scalping hedge gains
        total_pnl = (straddle_value - straddle_cost) + hedge_pnl
        pnl_pct   = total_pnl / S0

        # Clip
        pnl_pct = float(np.clip(pnl_pct, -0.30, 0.30))

        # Track whether RV > IV this month
        rv_month = float(rv.iloc[exit_loc]) if exit_loc < len(rv) and not np.isnan(rv.iloc[exit_loc]) else 0.20
        if rv_month > iv_entry:
            n_positive += 1
        else:
            n_negative += 1

        returns.append(pnl_pct)
        equity.append(equity[-1] * (1 + pnl_pct))

    if len(returns) < 10:
        return None

    wins    = sum(1 for r in returns if r > 0)
    sharpe  = calc_sharpe(returns, annualize=12)
    max_dd  = calc_max_dd(equity)

    return {
        'ticker':          ticker,
        'strategy':        f'gamma_scalp_{ticker}',
        'sharpe':          round(sharpe, 4),
        'total_return':    round(equity[-1] - 1, 4),
        'max_dd':          round(max_dd, 4),
        'win_rate':        round(wins / len(returns), 4),
        'n_months':        len(returns),
        'n_rv_gt_iv':      n_positive,
        'n_rv_lt_iv':      n_negative,
        'rv_gt_iv_pct':    round(n_positive / max(n_positive + n_negative, 1), 4),
        'hedge_freq_days': hedge_freq_days,
        'avg_return':      round(float(np.mean(returns)), 4),
    }

# ─────────────────────────────────────────────
# STRATEGY 6: VIX OPTIONS
# ─────────────────────────────────────────────

def run_vix_options(vix_prices):
    """
    VIX Options — three sub-strategies using VIX as underlying:

    VIX has unique option dynamics vs equity options:
      • VIX is mean-reverting (not a random walk) → different BS assumptions
      • VIX call skew is steep: OTM calls are expensive (spike insurance)
      • VIX put skew is inverted: OTM puts are cheap (VIX floor ~9-10)
      • VIX options settle to VIX futures, not spot — creates pricing edge

    We simulate using VIX spot as underlying (simplification). Modeled strategies:

    A) Long VIX Call (Tail Hedge): Buy 20% OTM call when VIX is below 20
       (cheap insurance period). Measure payoff on spike events.

    B) Short VIX Put (Floor Seller): Sell 20% OTM put (strike ~12-15 when VIX=15).
       VIX has a practical floor ~9-10 (Fed/dealers don't let it go to zero).
       Collect premium; put rarely goes deep ITM.

    C) Long VIX Call on Equity Dips (Tactical): Buy VIX call when S&P drops >2%
       in a day (volatility clustering — spikes tend to follow dips). Hold 5 days.
    """
    close = get_close(vix_prices)
    if len(close) < 252:
        return None

    rv    = realized_vol(close, 20)
    daily_ret = close.pct_change()

    # ── Sub-strategy A: Long VIX call as tail hedge ──────────
    A_returns = []
    A_equity  = [1.0]

    monthly_idx = close.resample('MS').first().index

    for entry_date in monthly_idx[:-1]:
        idx_loc  = close.index.searchsorted(entry_date)
        exit_loc = min(idx_loc + 21, len(close) - 1)
        if idx_loc >= len(close) - 22 or idx_loc < 20:
            continue

        vix_entry = float(close.iloc[idx_loc])
        if vix_entry >= 25:  # only buy when VIX is "cheap" (below 25)
            A_returns.append(0.0)
            A_equity.append(A_equity[-1])
            continue

        vol_proxy = float(rv.iloc[idx_loc]) if not np.isnan(rv.iloc[idx_loc]) else 0.80
        if vol_proxy <= 0:
            vol_proxy = 0.80
        # VIX itself has ~80-100% vol of vol

        K_call  = vix_entry * 1.20  # 20% OTM call
        T       = 21 / 365
        prem    = bs_call(vix_entry, K_call, T, vol_proxy)
        prem_pct = prem / vix_entry

        vix_exit = float(close.iloc[exit_loc])

        # Payoff: max(vix_exit - K_call, 0) / vix_entry - prem_pct
        intrinsic = max(vix_exit - K_call, 0.0)
        pnl_pct   = (intrinsic - prem) / vix_entry
        pnl_pct   = float(np.clip(pnl_pct, -1.0, 5.0))  # VIX can 3-5x in a month

        A_returns.append(pnl_pct)
        A_equity.append(A_equity[-1] * (1 + pnl_pct))

    # ── Sub-strategy B: Short VIX put (floor seller) ──────────
    B_returns = []
    B_equity  = [1.0]

    for entry_date in monthly_idx[:-1]:
        idx_loc  = close.index.searchsorted(entry_date)
        exit_loc = min(idx_loc + 21, len(close) - 1)
        if idx_loc >= len(close) - 22 or idx_loc < 20:
            continue

        vix_entry = float(close.iloc[idx_loc])
        vol_proxy = float(rv.iloc[idx_loc]) if not np.isnan(rv.iloc[idx_loc]) else 0.80
        if vol_proxy <= 0:
            vol_proxy = 0.80

        # Sell 20% OTM put (strike well below VIX level)
        K_put   = max(vix_entry * 0.80, 9.0)  # floor at 9 — VIX practical minimum
        T       = 21 / 365
        prem    = bs_put(vix_entry, K_put, T, vol_proxy)
        prem_pct = prem / vix_entry

        vix_exit = float(close.iloc[exit_loc])

        # Short put payoff: +prem if VIX > K_put, else prem - (K_put - vix_exit)
        if vix_exit < K_put:
            pnl = prem - (K_put - vix_exit)
        else:
            pnl = prem

        pnl_pct = pnl / vix_entry
        pnl_pct = float(np.clip(pnl_pct, -1.0, 2.0))

        B_returns.append(pnl_pct)
        B_equity.append(B_equity[-1] * (1 + pnl_pct))

    # ── Sub-strategy C: Tactical long VIX call on equity dip ───
    # We need SPY data — approximate equity dips using VIX spikes instead
    # Proxy: on days VIX jumps > 10% (stress day), buy VIX calls for 5-day hold
    C_returns = []
    C_equity  = [1.0]

    for i, date in enumerate(close.index[21:-5]):
        vix_val = float(close.iloc[i + 21])
        vix_prev = float(close.iloc[i + 20])
        if vix_prev <= 0:
            continue

        vix_spike = (vix_val - vix_prev) / vix_prev

        if vix_spike < 0.10:  # require >10% VIX spike (stress event)
            continue

        vol_proxy = float(rv.iloc[i + 21]) if not np.isnan(rv.iloc[i + 21]) else 0.80
        if vol_proxy <= 0:
            vol_proxy = 0.80

        # Buy ATM call, hold 5 days
        K    = vix_val
        T    = 5 / 365
        prem = bs_call(vix_val, K, T, vol_proxy)

        exit_loc   = min(i + 21 + 5, len(close) - 1)
        vix_exit   = float(close.iloc[exit_loc])

        intrinsic  = max(vix_exit - K, 0.0)
        pnl_pct    = (intrinsic - prem) / vix_val
        pnl_pct    = float(np.clip(pnl_pct, -1.0, 5.0))

        C_returns.append(pnl_pct)
        C_equity.append(C_equity[-1] * (1 + pnl_pct))

    # Filter out empties
    def safe_stats(rets, equity_curve, annualize=12):
        if len(rets) < 5:
            return {'sharpe': 0.0, 'win_rate': 0.0, 'total_return': 0.0,
                    'max_dd': 0.0, 'n_trades': 0, 'avg_return': 0.0}
        wins = sum(1 for r in rets if r > 0)
        return {
            'sharpe':       round(calc_sharpe(rets, annualize=annualize), 4),
            'win_rate':     round(wins / len(rets), 4),
            'total_return': round(equity_curve[-1] - 1, 4),
            'max_dd':       round(calc_max_dd(equity_curve), 4),
            'n_trades':     len(rets),
            'avg_return':   round(float(np.mean(rets)), 4),
        }

    A_stats = safe_stats(A_returns, A_equity, annualize=12)
    B_stats = safe_stats(B_returns, B_equity, annualize=12)
    C_stats = safe_stats(C_returns, C_equity, annualize=252)

    print(f"  VIX Long Call (tail hedge): Sharpe={A_stats['sharpe']:+.3f}  "
          f"WR={A_stats['win_rate']:.1%}  n={A_stats['n_trades']}")
    print(f"  VIX Short Put (floor sell): Sharpe={B_stats['sharpe']:+.3f}  "
          f"WR={B_stats['win_rate']:.1%}  n={B_stats['n_trades']}")
    print(f"  VIX Tactical Long (on spk): Sharpe={C_stats['sharpe']:+.3f}  "
          f"WR={C_stats['win_rate']:.1%}  n={C_stats['n_trades']}")

    # Best sub-strategy Sharpe for summary table
    best_sharpe = max(A_stats['sharpe'], B_stats['sharpe'], C_stats['sharpe'])

    return {
        'strategy':    'vix_options',
        'sharpe':      best_sharpe,  # best sub-strategy
        'A_long_call_tail_hedge': A_stats,
        'B_short_put_floor':      B_stats,
        'C_tactical_long_spike':  C_stats,
        'interpretation': (
            f"VIX tail hedge call: typically small drag (theta cost) but spikes pay "
            f"out big. Short VIX put: high win rate as VIX floor ~9-10 protects. "
            f"Tactical long on spikes: attempts to catch second-leg vol moves."
        )
    }


# ─────────────────────────────────────────────
# AGGREGATION HELPERS
# ─────────────────────────────────────────────

def aggregate(results, key='sharpe', exclude_zeros=True):
    vals = [r[key] for r in results if r and key in r]
    if exclude_zeros:
        vals = [v for v in vals if v != 0]
    if not vals:
        return 0.0, 0.0, None
    best_r = max(results, key=lambda x: x.get(key, -999) if x else -999)
    return round(float(np.mean(vals)), 4), round(float(np.std(vals)), 4), best_r

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 65)
    print("R28 — OPTIONS DEEP DIVE: Wheel / Multi-Leg / Greeks")
    print("=" * 65)
    print(f"Universe: {len(UNIVERSE)} tickers | Period: {START_DATE}–{END_DATE}")
    print(f"IV_PREMIUM: {IV_PREMIUM:.0%} above realized vol (VRP simulation)")
    print()

    # ── Fetch data ──────────────────────────────────────────────
    print("[1/6] Fetching price data...")
    data = fetch_data(UNIVERSE, START_DATE, END_DATE)
    print(f"  Loaded {len(data)} tickers")

    # ── Strategy 1: Wheel ────────────────────────────────────────
    print("\n[2/6] Strategy 1: WHEEL STRATEGY")
    wheel_results = []
    for ticker, prices in data.items():
        r = run_wheel(ticker, prices)
        if r:
            wheel_results.append(r)
            print(f"  {ticker:6s} Sharpe={r['sharpe']:+.3f}  vs_BH={r['vs_bh']:+.3f}  "
                  f"cycles={r['n_full_cycles']}  assignments={r['n_assignments']}")

    w_avg, w_std, w_best = aggregate(wheel_results)
    print(f"  → Avg Sharpe: {w_avg:+.3f} | Best: {w_best['ticker'] if w_best else 'N/A'} @ {w_best['sharpe'] if w_best else 0:+.3f}")

    # ── Strategy 2: Iron Condor ──────────────────────────────────
    print("\n[3/6] Strategy 2: IRON CONDOR (IV rank > 50%)")
    ic_results = []
    for ticker, prices in data.items():
        r = run_iron_condor(ticker, prices, iv_rank_threshold=50.0)
        if r:
            ic_results.append(r)
            print(f"  {ticker:6s} Sharpe={r['sharpe']:+.3f}  WR={r['win_rate']:.1%}  "
                  f"n={r['n_entered']}  max_loss_rate={r['n_max_loss']/max(r['n_entered'],1):.1%}")

    ic_avg, ic_std, ic_best = aggregate(ic_results)
    print(f"  → Avg Sharpe: {ic_avg:+.3f} | Best: {ic_best['ticker'] if ic_best else 'N/A'} @ {ic_best['sharpe'] if ic_best else 0:+.3f}")

    # ── Strategy 3: Bull Put Spread ──────────────────────────────
    print("\n[4/6] Strategy 3: BULL PUT SPREAD (IV rank > 50%)")
    bps_results = []
    for ticker, prices in data.items():
        r = run_bull_put_spread(ticker, prices, iv_rank_threshold=50.0)
        if r:
            bps_results.append(r)
            print(f"  {ticker:6s} Sharpe(spread)={r['sharpe_spread']:+.3f}  "
                  f"Sharpe(naked)={r['sharpe_naked_csp']:+.3f}  "
                  f"WR_spread={r['win_rate_spread']:.1%}  n={r['n_entered']}")

    bps_avg, bps_std, bps_best = aggregate(bps_results, key='sharpe_spread')
    print(f"  → Avg Sharpe: {bps_avg:+.3f} | Best: {bps_best['ticker'] if bps_best else 'N/A'} @ {bps_best['sharpe'] if bps_best else 0:+.3f}")

    # ── Strategy 4: VRP Harvesting ───────────────────────────────
    print("\n[5/6] Strategy 4: VRP HARVESTING (Sell Straddle)")
    vrp_results = []
    for ticker, prices in data.items():
        r = run_vrp_harvest(ticker, prices, iv_rank_threshold=40.0)
        if r:
            vrp_results.append(r)
            print(f"  {ticker:6s} Sharpe(always)={r['sharpe_always']:+.3f}  "
                  f"Sharpe(filtered)={r['sharpe_iv_filtered']:+.3f}  "
                  f"WR_filtered={r['win_rate_filtered']:.1%}  "
                  f"avg_move={r['avg_move_pct']:.2%}")

    vrp_avg, vrp_std, vrp_best = aggregate(vrp_results, key='sharpe_iv_filtered')
    vrp_avg_always, _, _       = aggregate(vrp_results, key='sharpe_always')
    print(f"  → Avg Sharpe (IV filtered): {vrp_avg:+.3f} | Always sell: {vrp_avg_always:+.3f}")

    # ── Strategy 5: Gamma Scalping ───────────────────────────────
    print("\n[6/6] Strategy 5: GAMMA SCALPING (hedge every 5 days)")
    gs_results = []
    for ticker, prices in data.items():
        r = run_gamma_scalp(ticker, prices, hedge_freq_days=5)
        if r:
            gs_results.append(r)
            print(f"  {ticker:6s} Sharpe={r['sharpe']:+.3f}  "
                  f"WR={r['win_rate']:.1%}  "
                  f"RV>IV: {r['rv_gt_iv_pct']:.1%} of months")

    gs_avg, gs_std, gs_best = aggregate(gs_results)
    gs_rv_gt_iv = float(np.mean([r['rv_gt_iv_pct'] for r in gs_results])) if gs_results else 0.0
    print(f"  → Avg Sharpe: {gs_avg:+.3f} | RV > IV in {gs_rv_gt_iv:.1%} of months")

    # ── Strategy 6: VIX Options ──────────────────────────────────
    print("\n[7/7] Strategy 6: VIX OPTIONS (tail hedge / floor sell / tactical)")
    vix_data = fetch_data(['^VIX'], START_DATE, END_DATE)
    vix_result = None
    if '^VIX' in vix_data and len(vix_data['^VIX']) > 200:
        vix_result = run_vix_options(vix_data['^VIX'])
    else:
        print("  ^VIX data unavailable — skipping VIX options section")

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("RESULTS SUMMARY")
    print("=" * 65)
    print(f"{'Strategy':<28} {'Avg Sharpe':>12} {'Best Sharpe':>12} {'Tickers':>8}")
    print("-" * 65)

    vix_sharpe = vix_result['sharpe'] if vix_result else 0.0
    rows = [
        ("Wheel (CSP→CC cycle)",        w_avg,     w_best['sharpe']   if w_best   else 0, len(wheel_results)),
        ("Iron Condor (IV rank>50%)",    ic_avg,    ic_best['sharpe']  if ic_best  else 0, len(ic_results)),
        ("Bull Put Spread (IV rank>50%)",bps_avg,   bps_best['sharpe'] if bps_best else 0, len(bps_results)),
        ("VRP Harvest (Sell Straddle)",  vrp_avg,   vrp_best['sharpe_iv_filtered'] if vrp_best else 0, len(vrp_results)),
        ("Gamma Scalping",               gs_avg,    gs_best['sharpe']  if gs_best  else 0, len(gs_results)),
        ("VIX Options (best sub-strat)", vix_sharpe, vix_sharpe, 1 if vix_result else 0),
    ]
    for name, avg, best, n in rows:
        print(f"  {name:<26} {avg:>+12.3f} {best:>+12.3f} {n:>8}")

    print()

    # Key findings
    best_strategy = max(rows, key=lambda x: x[1])
    wheel_vs_bh   = float(np.mean([r['vs_bh'] for r in wheel_results])) if wheel_results else 0
    wheel_asgn    = float(np.mean([r['n_assignments'] for r in wheel_results])) if wheel_results else 0
    ic_win_rate   = float(np.mean([r['win_rate'] for r in ic_results])) if ic_results else 0
    vrp_win_rate  = float(np.mean([r['win_rate_filtered'] for r in vrp_results])) if vrp_results else 0

    key_findings = {
        "best_strategy":     best_strategy[0],
        "best_avg_sharpe":   best_strategy[1],
        "wheel_vs_bh_annual": round(wheel_vs_bh, 4),
        "wheel_avg_assignments_per_5yr": round(wheel_asgn, 2),
        "ic_avg_win_rate":   round(ic_win_rate, 4),
        "vrp_harvest_win_rate": round(vrp_win_rate, 4),
        "vrp_always_sharpe":  vrp_avg_always,
        "gamma_scalp_rv_gt_iv_pct": round(gs_rv_gt_iv, 4),
        "vrp_premium_gap_modeled": IV_PREMIUM,
        "interpretation": (
            f"Best strategy is {best_strategy[0]} (avg Sharpe {best_strategy[1]:+.3f}). "
            f"Wheel returns {wheel_vs_bh:+.3f} annualized vs buy-and-hold. "
            f"Iron condor win rate {ic_win_rate:.1%} — high but watch max-loss events. "
            f"VRP harvesting win rate {vrp_win_rate:.1%} reflects IV>RV premium. "
            f"Gamma scalping: RV > IV in {gs_rv_gt_iv:.1%} of months — paying the VRP "
            f"makes this a slight drag on average."
        )
    }

    for line in key_findings['interpretation'].split('. '):
        if line:
            print(f"  ► {line}")

    # ── Save JSON ────────────────────────────────────────────────
    output = {
        "round":          28,
        "category":       "options_advanced",
        "run_date":       datetime.now().isoformat(),
        "config":         {
            "universe":     UNIVERSE,
            "start":        START_DATE,
            "end":          END_DATE,
            "iv_premium":   IV_PREMIUM,
            "risk_free":    RISK_FREE
        },
        "strategies": {
            "wheel": {
                "avg_sharpe":     w_avg,
                "std_sharpe":     w_std,
                "best_ticker":    w_best['ticker'] if w_best else None,
                "best_sharpe":    w_best['sharpe'] if w_best else 0,
                "avg_vs_bh":      round(wheel_vs_bh, 4),
                "avg_assignments": round(wheel_asgn, 2),
                "detail":         wheel_results
            },
            "iron_condor": {
                "avg_sharpe":     ic_avg,
                "std_sharpe":     ic_std,
                "best_ticker":    ic_best['ticker'] if ic_best else None,
                "best_sharpe":    ic_best['sharpe'] if ic_best else 0,
                "avg_win_rate":   round(ic_win_rate, 4),
                "iv_rank_threshold": 50.0,
                "detail":         ic_results
            },
            "bull_put_spread": {
                "avg_sharpe":     bps_avg,
                "std_sharpe":     bps_std,
                "best_ticker":    bps_best['ticker'] if bps_best else None,
                "best_sharpe":    bps_best['sharpe'] if bps_best else 0,
                "iv_rank_threshold": 50.0,
                "detail":         bps_results
            },
            "vrp_harvest": {
                "avg_sharpe_filtered": vrp_avg,
                "avg_sharpe_always":   vrp_avg_always,
                "best_ticker":    vrp_best['ticker'] if vrp_best else None,
                "avg_win_rate":   round(vrp_win_rate, 4),
                "iv_rank_threshold": 40.0,
                "detail":         vrp_results
            },
            "gamma_scalp": {
                "avg_sharpe":     gs_avg,
                "std_sharpe":     gs_std,
                "best_ticker":    gs_best['ticker'] if gs_best else None,
                "best_sharpe":    gs_best['sharpe'] if gs_best else 0,
                "rv_gt_iv_pct":   round(gs_rv_gt_iv, 4),
                "hedge_freq_days": 5,
                "detail":         gs_results
            },
            "vix_options": vix_result if vix_result else {"note": "VIX data unavailable"},
        },
        "key_findings":   key_findings,
        "leaderboard_entry": sorted(rows, key=lambda x: -x[1])
    }

    out_path = f'{ROUNDS_DIR}/r28_options_advanced.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved → {out_path}")
    print("=" * 65)

    return output


if __name__ == '__main__':
    main()
