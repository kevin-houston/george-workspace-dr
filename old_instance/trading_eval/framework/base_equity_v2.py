#!/usr/bin/env python3
"""
base_equity_v2.py — Base Equity Strategy Trade Logger (Framework v2)
=====================================================================
Re-instruments harness.py strategy families to emit standardized trade logs.
Each strategy family produces one .trades.jsonl file.

Strategy families (mirrors harness.py R1-R14):
  R1:  momentum           — PriceMomentum (12-1), ShortTermMomentum (1-0)
  R2:  mean_reversion     — ZScore, RSI-based MR
  R3:  trend_following    — MA Crossover (20/50, 50/200), EMA, Donchian
  R4:  volatility_filter  — BollingerBand, LowVolatilityAnomaly
  R5:  macd               — MACDHistogram, MACDZeroCross
  R6:  combo_trend        — ComboTrendVolFilter, ComboMomMA
  R7:  regime_gate        — LV55RegimeGate, LV55MomGate
  R8:  vol_adj_momentum   — VolAdjMomentum, VolAdjMomTrend
  R9:  dual_momentum      — DualMomentum, DualVolAdjMom
  R10: atr_breakout       — ATRChannelBreakout
  R11: pmo                — PMO (Price Momentum Oscillator)
  R12: trend_consistency  — TrendConsistency
  R13: momentum_score     — MomentumScore (composite)
  R14: ensemble           — VotingStrategy, VAMMACDTriple

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/base_equity_v2.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

import numpy as np
import pandas as pd

from base_harness import (
    TradeLogger, fetch_data, get_close, realized_vol,
    EVAL_DIR as _EVAL_DIR
)

warnings.filterwarnings('ignore')

# ── Universe ───────────────────────────────────────────────────────────────────
# Fortune 100 subset (25 most liquid for speed; harness uses ~78)
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM',  'JNJ',  'UNH',   'V',    'MA',   'HD',   'PG',  'KO',
    'XOM',  'CVX',  'BAC',   'WMT',  'MRK',
    'T',    'VZ',   'IBM',   'MO',   'PFE',
]
START = '2010-01-01'
END   = '2025-12-31'

# ── Signal-to-trade converter ──────────────────────────────────────────────────

def signals_to_trades(close: pd.Series, signals: pd.Series,
                       ticker: str, logger: TradeLogger,
                       strategy_name: str, hold_days_max: int = 20,
                       params: dict = None) -> int:
    """
    Convert a daily signal series (+1 long, -1 short, 0 flat) into
    discrete trade records: entry when signal changes to non-zero,
    exit when signal changes or max hold reached.
    """
    if params is None:
        params = {}
    signals = signals.reindex(close.index).fillna(0)
    in_trade  = False
    entry_idx = None
    direction = 0
    n_logged  = 0

    for i in range(1, len(close)):
        sig = int(signals.iloc[i])
        if not in_trade:
            if sig != 0:
                in_trade  = True
                entry_idx = i
                direction = sig
        else:
            hold = i - entry_idx
            signal_changed = (sig != direction and sig != 0) or sig == 0
            max_hold_hit   = hold >= hold_days_max

            if signal_changed or max_hold_hit:
                exit_idx   = i
                entry_price = float(close.iloc[entry_idx])
                exit_price  = float(close.iloc[exit_idx])
                if entry_price > 0:
                    raw_ret = (exit_price - entry_price) / entry_price
                    trade_ret = raw_ret * direction   # short flips sign
                    trade_ret = float(np.clip(trade_ret, -0.5, 0.5))
                    logger.log(
                        ticker      = ticker,
                        entry_date  = close.index[entry_idx],
                        exit_date   = close.index[exit_idx],
                        return_pct  = trade_ret,
                        hold_days   = hold,
                        direction   = 'long' if direction == 1 else 'short',
                        entry_price = entry_price,
                        exit_price  = exit_price,
                        params      = {**params, 'strategy': strategy_name},
                    )
                    n_logged += 1
                # start new trade if signal is non-zero
                if sig != 0:
                    in_trade  = True
                    entry_idx = i
                    direction = sig
                else:
                    in_trade  = False

    return n_logged


# ── Strategy Implementations ───────────────────────────────────────────────────

def momentum_signals(close: pd.Series, window: int = 252, skip: int = 21) -> pd.Series:
    past   = close.shift(skip)
    lagged = close.shift(skip + window)
    ret    = (past - lagged) / lagged.replace(0, np.nan)
    sig    = pd.Series(0.0, index=close.index)
    sig[ret > 0]  =  1.0
    sig[ret <= 0] = -1.0
    sig[ret.isna()] = 0.0
    return sig


def short_term_momentum_signals(close: pd.Series, window: int = 21) -> pd.Series:
    ret = close.pct_change(window)
    sig = pd.Series(0.0, index=close.index)
    sig[ret > 0]  =  1.0
    sig[ret <= 0] = -1.0
    sig[ret.isna()] = 0.0
    return sig


def zscore_mr_signals(close: pd.Series, window: int = 20, threshold: float = 2.0) -> pd.Series:
    roll_mean = close.rolling(window).mean()
    roll_std  = close.rolling(window).std()
    z = (close - roll_mean) / roll_std.replace(0, np.nan)
    sig = pd.Series(0.0, index=close.index)
    sig[z < -threshold] =  1.0
    sig[z >  threshold] = -1.0
    return sig


def rsi_signals(close: pd.Series, period: int = 14,
                oversold: float = 30, overbought: float = 70) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - (100 / (1 + rs))
    sig   = pd.Series(0.0, index=close.index)
    sig[rsi < oversold]   =  1.0
    sig[rsi > overbought] = -1.0
    return sig


def ma_crossover_signals(close: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    fast_ma = close.rolling(fast).mean()
    slow_ma = close.rolling(slow).mean()
    sig = pd.Series(0.0, index=close.index)
    sig[fast_ma > slow_ma] =  1.0
    sig[fast_ma < slow_ma] = -1.0
    return sig


def ema_crossover_signals(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
    fast_ema = close.ewm(span=fast).mean()
    slow_ema = close.ewm(span=slow).mean()
    sig = pd.Series(0.0, index=close.index)
    sig[fast_ema > slow_ema] =  1.0
    sig[fast_ema < slow_ema] = -1.0
    return sig


def donchian_signals(close: pd.Series, window: int = 20) -> pd.Series:
    upper = close.rolling(window).max().shift(1)
    lower = close.rolling(window).min().shift(1)
    sig   = pd.Series(0.0, index=close.index)
    sig[close > upper] =  1.0
    sig[close < lower] = -1.0
    return sig


def bollinger_signals(close: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.Series:
    ma  = close.rolling(window).mean()
    std = close.rolling(window).std()
    upper = ma + n_std * std
    lower = ma - n_std * std
    sig   = pd.Series(0.0, index=close.index)
    sig[close < lower] =  1.0   # oversold
    sig[close > upper] = -1.0   # overbought
    return sig


def low_vol_anomaly_signals(close: pd.Series, vol_window: int = 21,
                             rank_window: int = 252) -> pd.Series:
    """Buy low-volatility (bottom 20%), avoid high-volatility."""
    vol   = close.pct_change().rolling(vol_window).std()
    rank  = vol.rolling(rank_window).rank(pct=True)
    sig   = pd.Series(0.0, index=close.index)
    sig[rank < 0.2] =  1.0   # low vol: long
    sig[rank > 0.8] = -1.0   # high vol: short
    return sig


def macd_histogram_signals(close: pd.Series,
                            fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
    fast_ema   = close.ewm(span=fast).mean()
    slow_ema   = close.ewm(span=slow).mean()
    macd_line  = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal).mean()
    histogram  = macd_line - signal_line
    sig        = pd.Series(0.0, index=close.index)
    sig[histogram > 0] =  1.0
    sig[histogram < 0] = -1.0
    return sig


def macd_zero_cross_signals(close: pd.Series,
                             fast: int = 12, slow: int = 26) -> pd.Series:
    fast_ema  = close.ewm(span=fast).mean()
    slow_ema  = close.ewm(span=slow).mean()
    macd_line = fast_ema - slow_ema
    sig       = pd.Series(0.0, index=close.index)
    sig[macd_line > 0] =  1.0
    sig[macd_line < 0] = -1.0
    return sig


def combo_trend_vol_signals(close: pd.Series) -> pd.Series:
    """MA trend filter + vol regime gate."""
    trend  = ma_crossover_signals(close, 20, 50)
    vol    = realized_vol(close, 20)
    vol_ok = vol < vol.rolling(252).quantile(0.7)
    sig    = trend.copy()
    sig[~vol_ok] = 0.0
    return sig


def lv55_regime_signals(close: pd.Series) -> pd.Series:
    """Low-volatility 55-day regime gate on MA crossover."""
    ma_sig = ma_crossover_signals(close, 50, 200)
    vol    = realized_vol(close, 55)
    low_vol = vol < 0.20
    sig = pd.Series(0.0, index=close.index)
    sig[ma_sig == 1.0] = 1.0
    sig[(ma_sig == 1.0) & ~low_vol] = 0.0
    return sig


def vol_adj_momentum_signals(close: pd.Series, window: int = 126) -> pd.Series:
    """Momentum signal scaled by inverse volatility."""
    mom = close.pct_change(window)
    vol = realized_vol(close, 21)
    score = mom / vol.replace(0, np.nan)
    sig   = pd.Series(0.0, index=close.index)
    sig[score > 0] =  1.0
    sig[score < 0] = -1.0
    return sig


def dual_momentum_signals(close: pd.Series, spy_close: pd.Series = None,
                           window: int = 252) -> pd.Series:
    """Absolute + relative momentum filter."""
    abs_mom = close.pct_change(window)
    sig     = pd.Series(0.0, index=close.index)
    if spy_close is not None:
        spy_mom = spy_close.reindex(close.index).pct_change(window)
        sig[(abs_mom > 0) & (abs_mom > spy_mom)] =  1.0
        sig[(abs_mom < 0)] = -1.0
    else:
        sig[abs_mom > 0] =  1.0
        sig[abs_mom < 0] = -1.0
    return sig


def atr_breakout_signals(close: pd.Series, window: int = 14,
                          multiplier: float = 2.0) -> pd.Series:
    """ATR channel breakout."""
    tr  = close.diff().abs()
    atr = tr.rolling(window).mean()
    upper = close.shift(window).add(multiplier * atr)
    lower = close.shift(window).sub(multiplier * atr)
    sig   = pd.Series(0.0, index=close.index)
    sig[close > upper] =  1.0
    sig[close < lower] = -1.0
    return sig


def pmo_signals(close: pd.Series, roc1: int = 35, roc2: int = 20,
                 signal_period: int = 10) -> pd.Series:
    """Price Momentum Oscillator."""
    roc   = close.pct_change(1) * 10
    ema1  = roc.ewm(span=roc1).mean()
    pmo   = ema1.ewm(span=roc2).mean()
    sig_l = pmo.ewm(span=signal_period).mean()
    sig   = pd.Series(0.0, index=close.index)
    sig[pmo > sig_l] =  1.0
    sig[pmo < sig_l] = -1.0
    return sig


def trend_consistency_signals(close: pd.Series,
                               periods: list = None) -> pd.Series:
    """Vote across multiple timeframes for trend consistency."""
    if periods is None:
        periods = [20, 50, 100, 200]
    votes = pd.Series(0.0, index=close.index)
    for p in periods:
        ma = close.rolling(p).mean()
        votes[close > ma] += 1
        votes[close < ma] -= 1
    thresh = len(periods) // 2
    sig = pd.Series(0.0, index=close.index)
    sig[votes >= thresh]  =  1.0
    sig[votes <= -thresh] = -1.0
    return sig


def ensemble_voting_signals(close: pd.Series) -> pd.Series:
    """Ensemble vote across momentum, MA, MACD, RSI."""
    v1 = ma_crossover_signals(close, 20, 50)
    v2 = macd_histogram_signals(close)
    v3 = momentum_signals(close, 252, 21)
    v4 = rsi_signals(close, 14, 35, 65)
    vote = v1 + v2 + v3 + v4
    sig  = pd.Series(0.0, index=close.index)
    sig[vote >= 2]  =  1.0
    sig[vote <= -2] = -1.0
    return sig


# ── Strategy groups ────────────────────────────────────────────────────────────

STRATEGY_GROUPS = [
    # (logger_key, round_num, signal_func, params)
    ('price_momentum',       1,  lambda c, spy: momentum_signals(c, 252, 21),
     {'window': 252, 'skip': 21}),
    ('short_term_momentum',  1,  lambda c, spy: short_term_momentum_signals(c, 21),
     {'window': 21}),
    ('zscore_mean_reversion', 2, lambda c, spy: zscore_mr_signals(c, 20, 2.0),
     {'window': 20, 'threshold': 2.0}),
    ('rsi_mean_reversion',   2,  lambda c, spy: rsi_signals(c, 14, 30, 70),
     {'period': 14, 'oversold': 30, 'overbought': 70}),
    ('ma_crossover_2050',    3,  lambda c, spy: ma_crossover_signals(c, 20, 50),
     {'fast': 20, 'slow': 50}),
    ('ma_crossover_50200',   3,  lambda c, spy: ma_crossover_signals(c, 50, 200),
     {'fast': 50, 'slow': 200}),
    ('ema_crossover',        3,  lambda c, spy: ema_crossover_signals(c, 12, 26),
     {'fast': 12, 'slow': 26}),
    ('donchian_channel',     3,  lambda c, spy: donchian_signals(c, 20),
     {'window': 20}),
    ('bollinger_band',       4,  lambda c, spy: bollinger_signals(c, 20, 2.0),
     {'window': 20, 'n_std': 2.0}),
    ('low_vol_anomaly',      4,  lambda c, spy: low_vol_anomaly_signals(c, 21, 252),
     {'vol_window': 21, 'rank_window': 252}),
    ('macd_histogram',       5,  lambda c, spy: macd_histogram_signals(c, 12, 26, 9),
     {'fast': 12, 'slow': 26, 'signal': 9}),
    ('macd_zero_cross',      5,  lambda c, spy: macd_zero_cross_signals(c, 12, 26),
     {'fast': 12, 'slow': 26}),
    ('combo_trend_vol',      6,  lambda c, spy: combo_trend_vol_signals(c),
     {'description': 'ma20/50_with_vol_gate'}),
    ('lv55_regime_gate',     7,  lambda c, spy: lv55_regime_signals(c),
     {'ma': '50/200', 'vol_threshold': 0.20}),
    ('vol_adj_momentum',     8,  lambda c, spy: vol_adj_momentum_signals(c, 126),
     {'window': 126}),
    ('dual_momentum',        9,  lambda c, spy: dual_momentum_signals(c, spy, 252),
     {'window': 252, 'uses_spy': True}),
    ('atr_breakout',        10,  lambda c, spy: atr_breakout_signals(c, 14, 2.0),
     {'atr_window': 14, 'multiplier': 2.0}),
    ('pmo',                 11,  lambda c, spy: pmo_signals(c, 35, 20, 10),
     {'roc1': 35, 'roc2': 20, 'signal': 10}),
    ('trend_consistency',   12,  lambda c, spy: trend_consistency_signals(c, [20, 50, 100, 200]),
     {'periods': [20, 50, 100, 200]}),
    ('ensemble_voting',     14,  lambda c, spy: ensemble_voting_signals(c),
     {'components': ['ma2050', 'macd_hist', 'momentum_12_1', 'rsi14_35_65']}),
]


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Base Equity v2 — R1-R14 Technical Strategy Trade Logger")
    print("=" * 60)

    print(f"\n[1/3] Fetching price data for {len(UNIVERSE)} tickers...")
    tickers_to_fetch = UNIVERSE + ['SPY']
    raw_data = fetch_data(tickers_to_fetch, START, END)
    print(f"  Loaded {len(raw_data)} tickers")

    spy_close = None
    if 'SPY' in raw_data:
        spy_close = get_close(raw_data['SPY'])

    print(f"\n[2/3] Building trade loggers for {len(STRATEGY_GROUPS)} strategies...")
    loggers = {}
    for (strat_name, round_num, _, _) in STRATEGY_GROUPS:
        loggers[strat_name] = TradeLogger(
            round_num=round_num,
            strategy=strat_name,
            category='equity_technical'
        )

    print(f"\n[3/3] Running strategies across {len(UNIVERSE)} tickers...")
    total_trades = 0

    for ticker in UNIVERSE:
        if ticker not in raw_data:
            continue
        close = get_close(raw_data[ticker])
        if len(close) < 300:
            continue

        for (strat_name, _, signal_fn, params) in STRATEGY_GROUPS:
            try:
                signals = signal_fn(close, spy_close)
                n = signals_to_trades(
                    close, signals, ticker,
                    loggers[strat_name], strat_name,
                    hold_days_max=20, params=params
                )
                total_trades += n
            except Exception as e:
                print(f"  [{strat_name}] {ticker}: {e}")

    print(f"\n  Total trades logged: {total_trades:,}")

    print("\nSaving trade logs...")
    for strat_name, logger in loggers.items():
        if len(logger) > 0:
            logger.save()

    print("\n✓ Base equity harness complete.")
    print("  Run: /workspace/group/venv/bin/python3 trading_eval/framework/analysis_layer.py")
    print("  to compute regime-aware metrics across all strategies.")


if __name__ == '__main__':
    main()
