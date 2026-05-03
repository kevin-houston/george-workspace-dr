#!/usr/bin/env python3
"""
vol_v2.py — Volatility / Inter-Market / Fixed Income Harness v2 (TradeLogger)
==============================================================================
Converts vol_intermarket_harness.py strategy logic into per-trade TradeLogger
records.
- round_num from harness: V1 (VIX strategies), V2 (intermarket), FI1 (fixed income)
  mapped to round_num 1, 2, 3 respectively
- category='volatility'
- One TradeLogger per strategy variant
- Log per trade with all available fields

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/vol_v2.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, '/workspace/group/trading_eval/framework')
sys.path.insert(0, '/workspace/group/trading_eval')

import pickle
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Optional

warnings.filterwarnings('ignore')

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f'Missing: {e}. Run: /workspace/group/venv/bin/pip install yfinance pandas numpy')
    sys.exit(1)

from base_harness import TradeLogger, fetch_data, get_close

# ── Paths ─────────────────────────────────────────────────────────────────────

CACHE_DIR = Path('/workspace/group/trading_eval/cache')
CACHE_DIR.mkdir(exist_ok=True)

# ── Price fetcher (same logic as vol_intermarket_harness.py) ──────────────────

def _cache_path(ticker: str) -> Path:
    safe = ticker.replace('^', 'IDX_')
    return CACHE_DIR / f'vol_{safe}.pkl'


def fetch_price(ticker: str, start: str = '2015-01-01') -> pd.DataFrame:
    cp = _cache_path(ticker)
    if cp.exists():
        try:
            df = pickle.load(open(cp, 'rb'))
            if not df.empty and (pd.Timestamp.today() - df.index[-1]).days < 5:
                return df
        except Exception:
            pass
    try:
        raw = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if raw.empty:
            return pd.DataFrame()
        raw.index = raw.index.tz_localize(None) if raw.index.tz is not None else raw.index
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        closes = raw[['Close']].copy()
        closes.columns = [ticker]
        pickle.dump(closes, open(cp, 'wb'))
        return closes
    except Exception as e:
        print(f'  [WARN] Could not fetch {ticker}: {e}')
        return pd.DataFrame()


def build_price_matrix(tickers: List[str], start: str = '2015-01-01') -> pd.DataFrame:
    frames = []
    for t in tickers:
        df = fetch_price(t, start)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, axis=1).sort_index()
    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    return out


# ── Trade extraction helpers ──────────────────────────────────────────────────

def extract_position_trades(prices: pd.Series, position: pd.Series,
                             direction: str = 'long') -> List[dict]:
    """
    Convert a position series (1 = in trade, 0 = flat) into individual trade records.
    direction: 'long' or 'short'
    """
    if prices.empty or position.empty:
        return []

    # Align
    common = prices.index.intersection(position.index)
    p = prices.loc[common]
    pos = position.loc[common]

    trades = []
    in_trade = False
    entry_i = None

    for i in range(len(pos)):
        val = pos.iloc[i]
        if not in_trade and val > 0:
            in_trade = True
            entry_i  = i
        elif in_trade and (val == 0 or i == len(pos) - 1):
            exit_i = i
            entry_price = float(p.iloc[entry_i])
            exit_price  = float(p.iloc[exit_i])
            entry_date  = p.index[entry_i]
            exit_date   = p.index[exit_i]
            hold_days   = (exit_date - entry_date).days

            if direction == 'long':
                ret_pct = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0.0
            else:
                ret_pct = (entry_price / exit_price - 1) * 100 if exit_price > 0 else 0.0

            trades.append({
                'entry_date':  entry_date,
                'exit_date':   exit_date,
                'entry_price': entry_price,
                'exit_price':  exit_price,
                'return_pct':  float(ret_pct),
                'hold_days':   int(max(hold_days, 1)),
                'direction':   direction,
            })
            in_trade = False

    return trades


def extract_allocation_trades(prices_dict: dict, weights: pd.DataFrame) -> List[dict]:
    """
    For multi-asset strategies: extract a synthetic 'trade' per rebalance period.
    Each rebalance period is treated as one trade record with blended return.
    """
    trades = []
    if weights.empty:
        return trades

    # Find rebalance dates (where weights change)
    weight_changes = weights.diff().abs().sum(axis=1)
    rebalance_dates = weight_changes[weight_changes > 0.01].index.tolist()

    if not rebalance_dates:
        return trades

    all_dates = weights.index.tolist()

    for k, rebal_dt in enumerate(rebalance_dates):
        next_rebal = rebalance_dates[k + 1] if k + 1 < len(rebalance_dates) else all_dates[-1]
        w = weights.loc[rebal_dt]
        active_assets = [a for a in w.index if abs(w[a]) > 0.01]
        if not active_assets:
            continue

        # Compute weighted return over this holding period
        period_ret = 0.0
        for asset in active_assets:
            if asset in prices_dict and rebal_dt in prices_dict[asset].index and next_rebal in prices_dict[asset].index:
                p_entry = float(prices_dict[asset].loc[rebal_dt])
                p_exit  = float(prices_dict[asset].loc[next_rebal])
                if p_entry > 0:
                    asset_ret = (p_exit / p_entry - 1) * 100
                    period_ret += float(w[asset]) * asset_ret

        hold_days = (next_rebal - rebal_dt).days
        # Use first active asset as ticker representative
        main_ticker = active_assets[0]
        entry_price = float(prices_dict[main_ticker].loc[rebal_dt]) if main_ticker in prices_dict else 0.0
        exit_price  = float(prices_dict[main_ticker].loc[next_rebal]) if main_ticker in prices_dict else 0.0

        trades.append({
            'entry_date':  rebal_dt,
            'exit_date':   next_rebal,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'return_pct':  float(period_ret),
            'hold_days':   int(max(hold_days, 1)),
            'direction':   'long',
        })

    return trades


# ── Round V1 — VIX Term Structure Strategies ──────────────────────────────────

def run_vix_strategies(prices: pd.DataFrame) -> None:
    """Log per-trade records for V1 VIX strategies. round_num=1."""
    if '^VIX' not in prices.columns:
        print('  [WARN] ^VIX not available, skipping VIX strategies')
        return

    vix       = prices['^VIX']
    spy_daily = prices['SPY'].pct_change()
    spy_close = prices['SPY']

    # --- V1-1: VIX Mean Reversion ---
    in_trade = False
    position = pd.Series(0.0, index=prices.index)
    for i, dt in enumerate(prices.index):
        v = vix.iloc[i]
        if pd.isna(v):
            continue
        if not in_trade and v > 30:
            in_trade = True
        elif in_trade and v < 22:
            in_trade = False
        position.iloc[i] = 1.0 if in_trade else 0.0

    logger_v1_mr = TradeLogger(round_num=1, strategy='V1-VIX_MeanReversion', category='volatility')
    trades = extract_position_trades(spy_close, position, 'long')
    for t in trades:
        logger_v1_mr.log(
            ticker      = 'SPY',
            entry_date  = t['entry_date'],
            exit_date   = t['exit_date'],
            return_pct  = t['return_pct'],
            hold_days   = t['hold_days'],
            direction   = t['direction'],
            entry_price = t['entry_price'],
            exit_price  = t['exit_price'],
            params      = {'vix_entry': 30, 'vix_exit': 22},
            notes       = 'Long SPY when VIX > 30, exit when VIX < 22',
        )
    if len(logger_v1_mr) > 0:
        logger_v1_mr.save()

    # --- V1-2: VIX Momentum ---
    vix_5d = vix.diff(5)
    position2 = pd.Series(0.0, index=prices.index)
    position2[vix_5d > 3]  = -1.0
    position2[vix_5d < -3] =  1.0
    pos2_shift = position2.shift(1).fillna(0)

    logger_v1_mom = TradeLogger(round_num=1, strategy='V1-VIX_Momentum', category='volatility')
    long_pos  = pos2_shift.clip(lower=0)
    short_pos = (-pos2_shift).clip(lower=0)
    for t in extract_position_trades(spy_close, long_pos, 'long'):
        logger_v1_mom.log(
            ticker='SPY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'vix_diff_window': 5, 'threshold': 3},
            notes='Long SPY when VIX falling (5d diff < -3)',
        )
    for t in extract_position_trades(spy_close, short_pos, 'short'):
        logger_v1_mom.log(
            ticker='SPY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='short',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'vix_diff_window': 5, 'threshold': 3},
            notes='Short SPY when VIX rising (5d diff > 3)',
        )
    if len(logger_v1_mom) > 0:
        logger_v1_mom.save()

    # --- V1-3: VIX Level Regime ---
    gld_close  = prices.get('GLD',  pd.Series(np.nan, index=prices.index))
    tlt_close  = prices.get('TLT',  pd.Series(np.nan, index=prices.index))
    uvxy_close = prices.get('UVXY', pd.Series(np.nan, index=prices.index))

    logger_v1_reg = TradeLogger(round_num=1, strategy='V1-VIX_LevelRegime', category='volatility')
    prev_regime = None
    entry_i = None
    regime_assets = {'UVXY': uvxy_close, 'SPY': spy_close, 'GLD': gld_close, 'TLT': tlt_close}

    for i in range(1, len(prices.index)):
        v = vix.iloc[i - 1]
        if pd.isna(v):
            continue
        if v < 15:
            regime = 'UVXY'
            asset_close = uvxy_close
        elif v <= 25:
            regime = 'SPY'
            asset_close = spy_close
        else:
            regime = 'GLD+TLT'
            asset_close = gld_close  # representative

        if regime != prev_regime:
            if prev_regime is not None and entry_i is not None:
                p_entry = float(regime_assets.get(prev_regime, spy_close).iloc[entry_i]) if prev_regime != 'GLD+TLT' else float(gld_close.iloc[entry_i])
                p_exit  = float(regime_assets.get(prev_regime, spy_close).iloc[i])     if prev_regime != 'GLD+TLT' else float(gld_close.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_v1_reg.log(
                    ticker      = prev_regime,
                    entry_date  = prices.index[entry_i],
                    exit_date   = prices.index[i],
                    return_pct  = float(ret),
                    hold_days   = int(max(hold, 1)),
                    direction   = 'long',
                    entry_price = p_entry,
                    exit_price  = p_exit,
                    params      = {'regime': prev_regime, 'vix_levels': (15, 25)},
                    notes       = f'VIX level regime: {prev_regime}',
                )
            prev_regime = regime
            entry_i = i
    if len(logger_v1_reg) > 0:
        logger_v1_reg.save()

    # --- V1-4: VIX Contango Roll ---
    svxy_close = prices.get('SVXY', pd.Series(np.nan, index=prices.index))
    in_contango = False
    pos4 = pd.Series(0.0, index=prices.index)
    for i in range(len(prices.index)):
        v = vix.iloc[i]
        if pd.isna(v):
            continue
        if not in_contango and v < 20:
            in_contango = True
        elif in_contango and v > 25:
            in_contango = False
        pos4.iloc[i] = 1.0 if in_contango else 0.0

    logger_v1_cont = TradeLogger(round_num=1, strategy='V1-VIX_ContangoRoll', category='volatility')
    for t in extract_position_trades(svxy_close, pos4, 'long'):
        logger_v1_cont.log(
            ticker='SVXY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'vix_entry': 20, 'vix_exit': 25},
            notes='Short vol (long SVXY) when VIX < 20; exit when VIX > 25',
        )
    if len(logger_v1_cont) > 0:
        logger_v1_cont.save()

    # --- V1-5: VIX Spike-and-Recover ---
    spike_signal = vix > 35
    pos5 = pd.Series(0.0, index=prices.index)
    active_days = 0
    in_spike = False
    for i in range(len(prices.index)):
        if spike_signal.iloc[i]:
            active_days = 3
            if not in_spike:
                in_spike = True
        if active_days > 0:
            pos5.iloc[i] = 1.0
            active_days -= 1
        else:
            pos5.iloc[i] = 0.0
            in_spike = False

    pos5_shift = pos5.shift(1).fillna(0)
    logger_v1_spike = TradeLogger(round_num=1, strategy='V1-VIX_SpikeRecover', category='volatility')
    for t in extract_position_trades(spy_close, pos5_shift, 'long'):
        logger_v1_spike.log(
            ticker='SPY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'vix_spike_threshold': 35, 'hold_window': 3},
            notes='Long SPY for 3 days after VIX closes > 35',
        )
    if len(logger_v1_spike) > 0:
        logger_v1_spike.save()


# ── Round V2 — Inter-Market Rotation ──────────────────────────────────────────

def run_intermarket_strategies(prices: pd.DataFrame) -> None:
    """Log per-trade records for V2 inter-market strategies. round_num=2."""

    spy_close = prices['SPY']

    def safe_c(ticker):
        if ticker in prices.columns:
            return prices[ticker]
        return pd.Series(np.nan, index=prices.index)

    tlt_close = safe_c('TLT')
    spy_r     = spy_close.pct_change()
    tlt_r     = tlt_close.pct_change()

    # --- IM1: Equity/Bond Rotation ---
    sma50  = spy_close.rolling(50).mean()
    sma200 = spy_close.rolling(200).mean()
    pos_im1 = (sma50 > sma200).astype(float)

    logger_im1 = TradeLogger(round_num=2, strategy='IM1-Equity_Bond_Rotation', category='volatility')
    # When in SPY
    spy_pos = pos_im1.shift(1).fillna(0)
    tlt_pos = (1 - pos_im1).shift(1).fillna(0)
    for t in extract_position_trades(spy_close, spy_pos, 'long'):
        logger_im1.log(
            ticker='SPY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'signal': 'SMA50>SMA200'},
            notes='Equity/Bond rotation: SPY leg',
        )
    for t in extract_position_trades(tlt_close, tlt_pos, 'long'):
        logger_im1.log(
            ticker='TLT', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'signal': 'SMA50<SMA200'},
            notes='Equity/Bond rotation: TLT leg',
        )
    if len(logger_im1) > 0:
        logger_im1.save()

    # --- IM4: Dual Momentum ---
    ief_close      = safe_c('IEF')
    ret252_spy     = spy_close.pct_change(252)
    ret252_ief     = ief_close.pct_change(252)
    pos_dm         = pd.Series(0.0, index=prices.index)
    for i in range(len(prices.index)):
        abs_mom = ret252_spy.iloc[i]
        rel_spy = ret252_spy.iloc[i]
        rel_ief = ret252_ief.iloc[i] if not pd.isna(ret252_ief.iloc[i]) else 0
        if pd.isna(abs_mom):
            continue
        if abs_mom > 0 and rel_spy > rel_ief:
            pos_dm.iloc[i] = 1.0
        else:
            pos_dm.iloc[i] = -1.0

    logger_im4 = TradeLogger(round_num=2, strategy='IM4-DualMomentum', category='volatility')
    dm_spy_pos = (pos_dm == 1).astype(float).shift(1).fillna(0)
    dm_tlt_pos = (pos_dm == -1).astype(float).shift(1).fillna(0)
    for t in extract_position_trades(spy_close, dm_spy_pos, 'long'):
        logger_im4.log(
            ticker='SPY', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'lookback': 252, 'signal': 'absolute+relative momentum'},
            notes='Dual Momentum: SPY when abs mom > 0 and SPY > IEF',
        )
    for t in extract_position_trades(tlt_close, dm_tlt_pos, 'long'):
        logger_im4.log(
            ticker='TLT', entry_date=t['entry_date'], exit_date=t['exit_date'],
            return_pct=t['return_pct'], hold_days=t['hold_days'], direction='long',
            entry_price=t['entry_price'], exit_price=t['exit_price'],
            params={'lookback': 252, 'signal': 'absolute+relative momentum'},
            notes='Dual Momentum: TLT when SPY fails momentum filter',
        )
    if len(logger_im4) > 0:
        logger_im4.save()

    # --- IM5: Dollar/Equity Inverse ---
    uup_close  = safe_c('UUP')
    uup_mom20  = uup_close.pct_change(20)
    strong_usd = uup_mom20 > 0
    logger_im5 = TradeLogger(round_num=2, strategy='IM5-Dollar_Equity_Inverse', category='volatility')

    prev_strong = None
    entry_i_spy = None
    entry_i_tlt = None
    for i in range(len(prices.index)):
        curr = bool(strong_usd.iloc[i]) if not pd.isna(strong_usd.iloc[i]) else None
        if curr is None:
            continue
        if prev_strong != curr:
            # Close previous and open new
            if prev_strong is not None and entry_i_spy is not None:
                spy_w = 0.25 if prev_strong else 0.75
                tlt_w = 0.75 if prev_strong else 0.25
                for (ticker, asset_close, w) in [('SPY', spy_close, spy_w), ('TLT', tlt_close, tlt_w)]:
                    p_entry = float(asset_close.iloc[entry_i_spy])
                    p_exit  = float(asset_close.iloc[i])
                    ret = (p_exit / p_entry - 1) * 100 * w if p_entry > 0 else 0.0
                    hold = (prices.index[i] - prices.index[entry_i_spy]).days
                    logger_im5.log(
                        ticker=ticker, entry_date=prices.index[entry_i_spy],
                        exit_date=prices.index[i], return_pct=float(ret),
                        hold_days=int(max(hold, 1)), direction='long',
                        entry_price=float(asset_close.iloc[entry_i_spy]),
                        exit_price=float(asset_close.iloc[i]),
                        params={'usd_strong': prev_strong, 'weight': w, 'uup_mom_window': 20},
                        notes=f'Dollar/Equity Inverse: USD {"strong" if prev_strong else "weak"}',
                    )
            prev_strong = curr
            entry_i_spy = i
    if len(logger_im5) > 0:
        logger_im5.save()

    # --- IM6: Oil Shock Signal ---
    uso_close = safe_c('USO')
    uso_r10   = uso_close.pct_change(10)
    oil_shock = uso_r10 > 0.08
    shy_close = safe_c('SHY')
    gld_close = safe_c('GLD')

    logger_im6 = TradeLogger(round_num=2, strategy='IM6-OilShock_Signal', category='volatility')
    in_shock = False
    entry_i  = None
    for i in range(len(prices.index)):
        shock = bool(oil_shock.iloc[i]) if not pd.isna(oil_shock.iloc[i]) else False
        if shock != in_shock:
            if entry_i is not None:
                ticker = 'SPY' if not in_shock else 'GLD'
                asset  = spy_close if not in_shock else gld_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_im6.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'oil_shock_threshold': 0.08, 'lookback': 10},
                    notes=f'Oil Shock: {"defensive (GLD+TLT+SHY)" if in_shock else "SPY"}',
                )
            in_shock = shock
            entry_i  = i
    if len(logger_im6) > 0:
        logger_im6.save()

    # --- IM7: Credit Spread Signal ---
    hyg_close = safe_c('HYG')
    hyg_ief_ratio = hyg_close / ief_close.replace(0, np.nan)
    hyg_ief_mom   = hyg_ief_ratio.pct_change(20)
    tight_spreads = hyg_ief_mom > 0

    logger_im7 = TradeLogger(round_num=2, strategy='IM7-CreditSpread_Signal', category='volatility')
    prev_tight = None
    entry_i    = None
    for i in range(len(prices.index)):
        tight = bool(tight_spreads.iloc[i]) if not pd.isna(tight_spreads.iloc[i]) else None
        if tight is None:
            continue
        if tight != prev_tight:
            if prev_tight is not None and entry_i is not None:
                ticker = 'SPY' if prev_tight else 'TLT'
                asset  = spy_close if prev_tight else tlt_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_im7.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'hyg_ief_mom_window': 20},
                    notes=f'Credit Spread: {"tight (SPY)" if prev_tight else "wide (TLT)"}',
                )
            prev_tight = tight
            entry_i    = i
    if len(logger_im7) > 0:
        logger_im7.save()


# ── Round FI1 — Fixed Income Strategies ───────────────────────────────────────

def run_fixed_income_strategies(prices: pd.DataFrame) -> None:
    """Log per-trade records for FI1 fixed income strategies. round_num=3."""

    def safe_c(ticker):
        if ticker in prices.columns:
            return prices[ticker]
        return pd.Series(np.nan, index=prices.index)

    tlt_close = safe_c('TLT')
    ief_close = safe_c('IEF')
    shy_close = safe_c('SHY')
    hyg_close = safe_c('HYG')
    lqd_close = safe_c('LQD')
    tip_close = safe_c('TIP')
    emb_close = safe_c('EMB')

    # --- FI1: Duration Momentum ---
    dur_assets = ['TLT', 'IEF', 'SHY']
    avail_dur  = [a for a in dur_assets if a in prices.columns]

    if len(avail_dur) >= 2:
        px_dur    = prices[avail_dur]
        ret60_dur = px_dur.pct_change(60)

        logger_fi1 = TradeLogger(round_num=3, strategy='FI1-Duration_Momentum', category='volatility')
        current_best = None
        entry_i      = None

        for i in range(1, len(px_dur)):
            r = ret60_dur.iloc[i].dropna()
            if r.empty:
                continue
            best = r.idxmax()
            if best != current_best:
                if current_best is not None and entry_i is not None:
                    asset_close = safe_c(current_best)
                    p_entry = float(asset_close.iloc[entry_i])
                    p_exit  = float(asset_close.iloc[i])
                    ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                    hold = (px_dur.index[i] - px_dur.index[entry_i]).days
                    logger_fi1.log(
                        ticker=current_best, entry_date=px_dur.index[entry_i],
                        exit_date=px_dur.index[i], return_pct=float(ret),
                        hold_days=int(max(hold, 1)), direction='long',
                        entry_price=p_entry, exit_price=p_exit,
                        params={'lookback': 60, 'universe': avail_dur},
                        notes='Duration Momentum: hold best 60d performing duration',
                    )
                current_best = best
                entry_i      = i
        if len(logger_fi1) > 0:
            logger_fi1.save()

    # --- FI2: Yield Curve Trade ---
    ief_mom = ief_close.pct_change(60)
    shy_mom = shy_close.pct_change(60)
    steepening = ief_mom > shy_mom

    logger_fi2 = TradeLogger(round_num=3, strategy='FI2-YieldCurve_Trade', category='volatility')
    prev_steep = None
    entry_i    = None
    for i in range(len(prices.index)):
        steep = bool(steepening.iloc[i]) if not pd.isna(steepening.iloc[i]) else None
        if steep is None:
            continue
        if steep != prev_steep:
            if prev_steep is not None and entry_i is not None:
                if prev_steep:
                    ticker = 'TLT'; asset = tlt_close
                else:
                    ticker = 'SHY'; asset = shy_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_fi2.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'lookback': 60},
                    notes=f'Yield Curve Trade: {"steepening -> TLT" if prev_steep else "flattening -> SHY"}',
                )
            prev_steep = steep
            entry_i    = i
    if len(logger_fi2) > 0:
        logger_fi2.save()

    # --- FI3: Credit Rotation ---
    hyg_mom60 = hyg_close.pct_change(60)
    lqd_mom60 = lqd_close.pct_change(60)
    ief_mom60 = ief_close.pct_change(60)
    risk_on   = (hyg_mom60 > lqd_mom60) & (lqd_mom60 > ief_mom60)

    logger_fi3 = TradeLogger(round_num=3, strategy='FI3-Credit_Rotation', category='volatility')
    prev_risk = None
    entry_i   = None
    for i in range(len(prices.index)):
        ron = bool(risk_on.iloc[i]) if not pd.isna(risk_on.iloc[i]) else None
        if ron is None:
            continue
        if ron != prev_risk:
            if prev_risk is not None and entry_i is not None:
                ticker = 'HYG' if prev_risk else 'IEF'
                asset  = hyg_close if prev_risk else ief_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_fi3.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'lookback': 60},
                    notes=f'Credit Rotation: {"risk-on HYG" if prev_risk else "risk-off IEF"}',
                )
            prev_risk = ron
            entry_i   = i
    if len(logger_fi3) > 0:
        logger_fi3.save()

    # --- FI4: Inflation Protection ---
    tip_mom60 = tip_close.pct_change(60)
    ief_m60   = ief_close.pct_change(60)
    inf_rising = tip_mom60 > ief_m60

    logger_fi4 = TradeLogger(round_num=3, strategy='FI4-Inflation_Protection', category='volatility')
    prev_inf = None
    entry_i  = None
    for i in range(len(prices.index)):
        inf = bool(inf_rising.iloc[i]) if not pd.isna(inf_rising.iloc[i]) else None
        if inf is None:
            continue
        if inf != prev_inf:
            if prev_inf is not None and entry_i is not None:
                ticker = 'TIP' if prev_inf else 'IEF'
                asset  = tip_close if prev_inf else ief_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_fi4.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'lookback': 60},
                    notes=f'Inflation Protection: {"TIP (inflation rising)" if prev_inf else "IEF"}',
                )
            prev_inf = inf
            entry_i  = i
    if len(logger_fi4) > 0:
        logger_fi4.save()

    # --- FI5: EM vs DM Bonds ---
    emb_mom60 = emb_close.pct_change(60)
    lqd_m60   = lqd_close.pct_change(60)
    em_wins   = emb_mom60 > lqd_m60

    logger_fi5 = TradeLogger(round_num=3, strategy='FI5-EM_vs_DM_Bonds', category='volatility')
    prev_em = None
    entry_i = None
    for i in range(len(prices.index)):
        em = bool(em_wins.iloc[i]) if not pd.isna(em_wins.iloc[i]) else None
        if em is None:
            continue
        if em != prev_em:
            if prev_em is not None and entry_i is not None:
                ticker = 'EMB' if prev_em else 'LQD'
                asset  = emb_close if prev_em else lqd_close
                p_entry = float(asset.iloc[entry_i])
                p_exit  = float(asset.iloc[i])
                ret = (p_exit / p_entry - 1) * 100 if p_entry > 0 else 0.0
                hold = (prices.index[i] - prices.index[entry_i]).days
                logger_fi5.log(
                    ticker=ticker, entry_date=prices.index[entry_i],
                    exit_date=prices.index[i], return_pct=float(ret),
                    hold_days=int(max(hold, 1)), direction='long',
                    entry_price=p_entry, exit_price=p_exit,
                    params={'lookback': 60},
                    notes=f'EM vs DM Bonds: {"EMB (EM winning)" if prev_em else "LQD (DM winning)"}',
                )
            prev_em = em
            entry_i = i
    if len(logger_fi5) > 0:
        logger_fi5.save()

    # --- FI6: Bond Ladder Baseline (monthly pseudo-trades) ---
    ladder_assets = [a for a in ['TLT', 'IEF', 'SHY'] if a in prices.columns]
    if ladder_assets:
        logger_fi6 = TradeLogger(round_num=3, strategy='FI6-BondLadder_Baseline', category='volatility')
        px_ladder = prices[ladder_assets]
        monthly_dates = px_ladder.resample('ME').last().index
        for k in range(1, len(monthly_dates)):
            dt_entry = monthly_dates[k - 1]
            dt_exit  = monthly_dates[k]
            if dt_entry not in px_ladder.index or dt_exit not in px_ladder.index:
                continue
            w = 1.0 / len(ladder_assets)
            total_ret = 0.0
            for a in ladder_assets:
                p_e = float(prices[a].loc[dt_entry])
                p_x = float(prices[a].loc[dt_exit])
                if p_e > 0:
                    total_ret += w * (p_x / p_e - 1) * 100
            hold = (dt_exit - dt_entry).days
            # Use first asset as representative price
            rep = ladder_assets[0]
            logger_fi6.log(
                ticker='+'.join(ladder_assets), entry_date=dt_entry, exit_date=dt_exit,
                return_pct=float(total_ret), hold_days=int(max(hold, 1)), direction='long',
                entry_price=float(prices[rep].loc[dt_entry]),
                exit_price=float(prices[rep].loc[dt_exit]),
                params={'assets': ladder_assets, 'weight': w},
                notes='Bond Ladder: equal-weight monthly rebalance',
            )
        if len(logger_fi6) > 0:
            logger_fi6.save()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('\n' + '='*70)
    print('  VOL V2 / INTERMARKET / FIXED INCOME TRADE LOGGER')
    print('  Period: 2015-01-01 to present')
    print('='*70)

    all_tickers = [
        '^VIX', 'UVXY', 'VXZ', 'SVXY', 'SPY',
        'TLT', 'GLD', 'SLV', 'USO', 'UUP', 'IEF', 'HYG', 'IWM',
        'SHY', 'LQD', 'TIP', 'EMB',
    ]

    print('\nFetching price data...')
    prices = build_price_matrix(all_tickers, start='2015-01-01')

    if prices.empty:
        print('ERROR: No price data fetched. Exiting.')
        return

    print(f'Price matrix shape: {prices.shape}')
    print(f'Date range: {prices.index[0].date()} to {prices.index[-1].date()}')
    print(f'Tickers loaded: {list(prices.columns)}')

    print('\nRunning Round V1 — VIX Strategies...')
    run_vix_strategies(prices)

    print('Running Round V2 — Inter-Market Rotation...')
    run_intermarket_strategies(prices)

    print('Running Round FI1 — Fixed Income...')
    run_fixed_income_strategies(prices)

    print('\nDone. Trade logs written to /workspace/group/trading_eval/trade_logs/')


if __name__ == '__main__':
    main()
