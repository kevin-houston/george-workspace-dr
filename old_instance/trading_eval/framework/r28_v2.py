"""
r28_v2.py — R28 Options Deep Dive (Framework v1.0 version)
===========================================================
Proof-of-concept demonstrating the new harness architecture.
Reproduces R28's bull put spread strategy using base_harness.py
and emits a standardized .trades.jsonl log.

Original results are preserved in:
  trading_eval/r28_harness.py (original)
  trading_eval/rounds/r28_options_advanced.json (original results)

This file produces:
  trading_eval/trade_logs/bull_put_spread_r28.trades.jsonl
  trading_eval/trade_logs/wheel_r28.trades.jsonl
  trading_eval/trade_logs/iron_condor_r28.trades.jsonl

Run this, then run analysis_layer.py to see the full regime-aware analysis.
"""

import sys
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

# Allow imports from parent when run directly
_framework_dir = Path(__file__).parent
_eval_dir      = _framework_dir.parent
sys.path.insert(0, str(_framework_dir))
sys.path.insert(0, str(_eval_dir))

from base_harness import (
    ensure_deps, TradeLogger, fetch_data, get_close,
    bs_call, bs_put,
    realized_vol, iv_estimate, iv_rank,
    RF
)
ensure_deps()

warnings.filterwarnings('ignore')

UNIVERSE   = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM',  'JNJ',  'UNH',   'V',    'MA',   'HD',   'PG',  'KO',
    'XOM',  'CVX',  'BAC',   'WMT',  'MRK',
    'T',    'VZ',   'IBM',   'MO',   'PFE',
    'COST', 'NFLX', 'QCOM',  'TXN',  'GE'
]
START = '2020-01-01'
END   = '2025-12-31'

# ─────────────────────────────────────────────
# BULL PUT SPREAD
# ─────────────────────────────────────────────

def run_bull_put_spread_v2(ticker: str, prices, logger: TradeLogger,
                            iv_rank_threshold: float = 50.0) -> int:
    """
    Emit one trade record per monthly entry. Returns number of trades logged.
    Strategy logic identical to r28_harness.py — only the output format changes.
    """
    close = get_close(prices)
    if len(close) < 300:
        return 0

    iv  = iv_estimate(close, 20)
    ivr = iv_rank(iv, lookback=252)
    monthly_idx = close.resample('MS').first().index
    n_logged = 0

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

        T      = 30 / 365
        K_sell = S
        K_buy  = S * 0.95
        wing   = K_sell - K_buy

        p_sell     = bs_put(S, K_sell, T, vol)
        p_buy      = bs_put(S, K_buy,  T, vol)
        net_credit = p_sell - p_buy
        if net_credit <= 0:
            continue

        exit_loc = min(idx_loc + 21, len(close) - 1)
        S_exit   = float(close.iloc[exit_loc])
        exit_date = close.index[exit_loc]

        # P&L
        if S_exit >= K_sell:
            spread_pnl = net_credit
        elif S_exit <= K_buy:
            spread_pnl = net_credit - wing
        else:
            spread_pnl = net_credit - (K_sell - S_exit)

        spread_ret = float(np.clip(spread_pnl / wing if wing > 0 else 0.0, -1.0, 2.0))

        logger.log(
            ticker              = ticker,
            entry_date          = entry_date,
            exit_date           = exit_date,
            return_pct          = spread_ret,
            hold_days           = (exit_date - entry_date).days,
            direction           = 'short_put',
            entry_price         = S,
            exit_price          = S_exit,
            option_type         = 'spread',
            strike              = K_sell,
            expiry_date         = exit_date,
            premium_collected   = round(net_credit / S, 6),
            iv_at_entry         = round(vol, 4),
            iv_rank_at_entry    = round(current_ivr, 2),
            params              = {'iv_rank_threshold': iv_rank_threshold,
                                   'wing_width': 0.05, 'expiry_days': 30},
        )
        n_logged += 1

    return n_logged

# ─────────────────────────────────────────────
# WHEEL STRATEGY
# ─────────────────────────────────────────────

def run_wheel_v2(ticker: str, prices, logger: TradeLogger) -> int:
    """Emit one trade record per monthly cycle leg."""
    close = get_close(prices)
    if len(close) < 252:
        return 0

    iv = iv_estimate(close, 20)
    monthly_idx = close.resample('MS').first().index
    phase      = 'CSP'
    cost_basis = 0.0
    n_logged   = 0

    for entry_date in monthly_idx[:-1]:
        idx_loc  = close.index.searchsorted(entry_date)
        exit_loc = min(idx_loc + 21, len(close) - 1)
        if idx_loc >= len(close) - 1:
            break

        S_entry   = float(close.iloc[idx_loc])
        S_exit    = float(close.iloc[exit_loc])
        exit_date = close.index[exit_loc]
        vol       = float(iv.iloc[idx_loc]) if not np.isnan(iv.iloc[idx_loc]) else 0.22
        if vol <= 0:
            vol = 0.22

        T = 21 / 365

        if phase == 'CSP':
            K    = S_entry
            prem = bs_put(S_entry, K, T, vol)
            if S_exit < K:
                trade_ret = (prem - (K - S_exit)) / K
                leg_type  = 'csp_assigned'
                phase     = 'CC'
                cost_basis = K
            else:
                trade_ret = prem / K
                leg_type  = 'csp_expired'
        else:
            K    = cost_basis
            prem = bs_call(S_entry, K, T, vol)
            if S_exit > K:
                trade_ret = (K - cost_basis + prem) / cost_basis
                leg_type  = 'cc_called_away'
                phase     = 'CSP'
            else:
                trade_ret = (S_exit - S_entry + prem) / S_entry
                leg_type  = 'cc_held'
                cost_basis = S_entry

        trade_ret = float(np.clip(trade_ret, -0.5, 0.5))

        logger.log(
            ticker       = ticker,
            entry_date   = entry_date,
            exit_date    = exit_date,
            return_pct   = trade_ret,
            hold_days    = (exit_date - entry_date).days,
            direction    = 'short_put' if 'csp' in leg_type else 'short_call',
            entry_price  = S_entry,
            exit_price   = S_exit,
            option_type  = 'put' if 'csp' in leg_type else 'call',
            strike       = K,
            iv_at_entry  = round(vol, 4),
            notes        = leg_type,
            params       = {'strategy_phase': phase,
                            'cost_basis': round(cost_basis, 4)},
        )
        n_logged += 1

    return n_logged

# ─────────────────────────────────────────────
# IRON CONDOR
# ─────────────────────────────────────────────

def run_iron_condor_v2(ticker: str, prices, logger: TradeLogger,
                        iv_rank_threshold: float = 50.0) -> int:
    close = get_close(prices)
    if len(close) < 300:
        return 0

    iv  = iv_estimate(close, 20)
    ivr = iv_rank(iv, lookback=252)
    monthly_idx = close.resample('MS').first().index
    n_logged = 0

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

        T = 30 / 365
        K_cs, K_cb = S * 1.05, S * 1.10
        K_ps, K_pb = S * 0.95, S * 0.90
        wing       = S * 0.05

        net_credit = ((bs_call(S, K_cs, T, vol) - bs_call(S, K_cb, T, vol)) +
                      (bs_put(S,  K_ps, T, vol) - bs_put(S,  K_pb, T, vol)))
        if net_credit <= 0:
            continue

        exit_loc  = min(idx_loc + 21, len(close) - 1)
        S_exit    = float(close.iloc[exit_loc])
        exit_date = close.index[exit_loc]

        call_loss = min(max(S_exit - K_cs, 0), wing)
        put_loss  = min(max(K_ps - S_exit, 0), wing)
        pnl       = net_credit - call_loss - put_loss
        pnl_pct   = float(np.clip(pnl / S, -0.20, 0.20))

        logger.log(
            ticker            = ticker,
            entry_date        = entry_date,
            exit_date         = exit_date,
            return_pct        = pnl_pct,
            hold_days         = (exit_date - entry_date).days,
            direction         = 'short',
            entry_price       = S,
            exit_price        = S_exit,
            option_type       = 'condor',
            premium_collected = round(net_credit / S, 6),
            iv_at_entry       = round(vol, 4),
            iv_rank_at_entry  = round(current_ivr, 2),
            params            = {'iv_rank_threshold': iv_rank_threshold,
                                 'call_wing': 0.05, 'put_wing': 0.05,
                                 'expiry_days': 30},
        )
        n_logged += 1

    return n_logged

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("R28 v2 — Options Deep Dive (Framework Edition)")
    print("=" * 60)

    print("\n[1/4] Fetching price data...")
    data = fetch_data(UNIVERSE, START, END)
    print(f"  Loaded {len(data)} tickers")

    # Create loggers for each strategy
    bps_logger = TradeLogger(round_num=28, strategy='bull_put_spread',
                              category='options')
    wheel_logger = TradeLogger(round_num=28, strategy='wheel',
                                category='options')
    ic_logger = TradeLogger(round_num=28, strategy='iron_condor',
                             category='options')

    print("\n[2/4] Running Bull Put Spread (IV rank > 50%)...")
    for ticker, prices in data.items():
        n = run_bull_put_spread_v2(ticker, prices, bps_logger)
        if n > 0:
            print(f"  {ticker:6s}: {n} trades logged")
    bps_logger.save()

    print("\n[3/4] Running Wheel Strategy...")
    for ticker, prices in data.items():
        n = run_wheel_v2(ticker, prices, wheel_logger)
        if n > 0:
            print(f"  {ticker:6s}: {n} trades logged")
    wheel_logger.save()

    print("\n[4/4] Running Iron Condor (IV rank > 50%)...")
    for ticker, prices in data.items():
        n = run_iron_condor_v2(ticker, prices, ic_logger)
        if n > 0:
            print(f"  {ticker:6s}: {n} trades logged")
    ic_logger.save()

    print("\n✓ Trade logs written. Now run:")
    print("  python framework/analysis_layer.py")
    print("  to compute Sharpe, Sortino, Calmar, regime-conditional stats, etc.")


if __name__ == '__main__':
    main()
