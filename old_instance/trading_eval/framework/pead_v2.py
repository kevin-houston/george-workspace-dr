"""
pead_v2.py — PEAD Strategy Harness with TradeLogger instrumentation
====================================================================
Preserves exact strategy logic from pead_harness.py.
Emits one TradeLogger record per trade for each strategy variant.
Does NOT compute Sharpe/win_rate/etc — that is the analysis layer's job.

Runnable:
    /workspace/group/venv/bin/python3 trading_eval/framework/pead_v2.py
"""

import sys
import os

# Allow imports from the framework directory (this file's directory)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Also allow imports from the eval root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import time

warnings.filterwarnings('ignore')

from base_harness import TradeLogger, fetch_data, get_close, realized_vol

# ─────────────────────────────────────────────
# UNIVERSE & CONFIG  (identical to pead_harness.py)
# ─────────────────────────────────────────────
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'COST',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'NFLX', 'ADBE', 'QCOM', 'TXN', 'HON',
    'GE', 'CAT', 'MMM', 'LMT', 'RTX'
]

START_DATE = '2020-01-01'
END_DATE   = '2025-12-31'

THRESHOLDS   = [0.02, 0.03, 0.04, 0.05]
HOLD_PERIODS = [5, 10, 20, 40, 60]
DIRECTIONS   = ['long', 'short', 'both']

CACHE_DIR = '/workspace/group/trading_eval/cache'
os.makedirs(CACHE_DIR, exist_ok=True)

# Round number for all loggers in this file
ROUND_NUM = 30


# ─────────────────────────────────────────────
# DATA FETCHING  (identical logic to pead_harness.py)
# ─────────────────────────────────────────────
def fetch_pead_data(tickers, start, end, retries=3):
    """
    Download OHLCV data for all tickers with caching.
    Returns a multi-column DataFrame keyed by (field, ticker).
    Reuses the same cache file format as pead_harness.py.
    """
    import yfinance as yf

    cache_file = os.path.join(CACHE_DIR, f'pead_universe_{start}_{end}.pkl')
    if os.path.exists(cache_file):
        print(f"  Loading from cache: {cache_file}")
        return pd.read_pickle(cache_file)

    all_data = {}
    for ticker in tickers:
        for attempt in range(retries):
            try:
                df = yf.download(ticker, start=start, end=end,
                                 auto_adjust=True, progress=False)
                if df is not None and len(df) > 200:
                    df.index = pd.to_datetime(df.index)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    all_data[ticker] = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                    print(f"  {ticker}: {len(df)} rows")
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f"  {ticker} attempt {attempt+1} failed: {e}")
                time.sleep(1)

    combined = {}
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        combined[col] = pd.DataFrame(
            {t: all_data[t][col] for t in all_data if col in all_data[t].columns}
        )

    result = pd.concat({col: combined[col] for col in combined}, axis=1)
    result.to_pickle(cache_file)
    print(f"  Saved cache: {cache_file}")
    return result


# ─────────────────────────────────────────────
# GAP DETECTION  (identical to pead_harness.py)
# ─────────────────────────────────────────────
def compute_gaps(data, tickers):
    """
    Compute overnight gap = open / prev_close - 1 for each ticker.
    Returns dict of per-ticker DataFrames with gap column.
    """
    ticker_frames = {}
    for ticker in tickers:
        try:
            close  = data['Close'][ticker].dropna()
            open_  = data['Open'][ticker].dropna()
            volume = data['Volume'][ticker].dropna()

            df = pd.DataFrame({
                'close':  close,
                'open':   open_,
                'volume': volume
            }).dropna()

            df['prev_close'] = df['close'].shift(1)
            df['gap']        = df['open'] / df['prev_close'] - 1

            # 20-day average volume
            df['vol_avg20'] = df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['volume'] / df['vol_avg20']

            # 60-day trend (close vs 60d EMA)
            df['ema60']    = df['close'].ewm(span=60).mean()
            df['trend_up'] = df['close'] > df['ema60']

            ticker_frames[ticker] = df.dropna()
        except Exception as e:
            print(f"  Gap compute failed for {ticker}: {e}")

    return ticker_frames


# ─────────────────────────────────────────────
# SINGLE-TICKER BACKTEST  (identical to pead_harness.py)
# Returns list of trade dicts — same fields as original.
# ─────────────────────────────────────────────
def backtest_ticker(df, threshold, hold_period, direction,
                    volume_filter=False, trend_filter=False):
    """
    Backtest PEAD on a single ticker.
    Returns list of trade dicts.
    """
    trades = []
    in_trade_until = None

    dates = df.index.tolist()

    for i, date in enumerate(dates):
        row = df.loc[date]

        if in_trade_until is not None and date <= in_trade_until:
            continue

        gap = row['gap']

        signal = None
        if direction in ('long', 'both') and gap > threshold:
            signal = 'long'
        elif direction in ('short', 'both') and gap < -threshold:
            signal = 'short'

        if signal is None:
            continue

        if volume_filter and row['vol_ratio'] < 1.5:
            continue

        if trend_filter:
            if signal == 'long' and not row['trend_up']:
                continue
            if signal == 'short' and row['trend_up']:
                continue

        entry_idx = i + 1
        exit_idx  = i + 1 + hold_period

        if entry_idx >= len(dates) or exit_idx >= len(dates):
            continue

        entry_date = dates[entry_idx]
        exit_date  = dates[exit_idx]

        entry_price = df.loc[entry_date, 'open']
        exit_price  = df.loc[exit_date, 'open']

        if entry_price <= 0 or exit_price <= 0:
            continue

        raw_return   = exit_price / entry_price - 1
        trade_return = raw_return if signal == 'long' else -raw_return

        trades.append({
            'ticker':      df.attrs.get('ticker', '?'),
            'gap_date':    date,
            'entry_date':  entry_date,
            'exit_date':   exit_date,
            'gap':         gap,
            'signal':      signal,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'return':      trade_return,
            'vol_ratio':   row['vol_ratio'],
            'trend_up':    bool(row['trend_up'])
        })

        in_trade_until = exit_date

    return trades


# ─────────────────────────────────────────────
# LOGGING HELPER
# ─────────────────────────────────────────────
def log_trades(trades, logger, gap_threshold, hold_days, variant_name):
    """
    Emit one TradeLogger record per trade with all available fields.

    For 'both' direction variants, each trade's actual direction is stored
    in the 'direction' field (determined by signal in backtest_ticker).
    For single-direction variants, direction is always that direction.
    """
    for t in trades:
        actual_direction = t['signal']  # 'long' or 'short' as determined by signal
        gap_pct = t['gap'] * 100        # e.g. +6.2 or -4.1
        hold_actual = (t['exit_date'] - t['entry_date']).days

        logger.log(
            ticker      = t['ticker'],
            entry_date  = t['entry_date'],
            exit_date   = t['exit_date'],
            return_pct  = float(t['return']),
            hold_days   = hold_actual,
            direction   = actual_direction,
            entry_price = float(t['entry_price']),
            exit_price  = float(t['exit_price']),
            params      = {
                'gap_threshold': gap_threshold,
                'hold_days':     hold_days,
                'variant':       variant_name,
            },
            notes       = f"gap={gap_pct:+.1f}%",
            gap_date    = t['gap_date'],
            gap_raw     = float(t['gap']),
            vol_ratio   = float(t['vol_ratio']),
            trend_up    = t['trend_up'],
        )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("PEAD v2 — TradeLogger Harness")
    print("=" * 60)

    # 1. Fetch data
    print("\n[1] Downloading market data...")
    data = fetch_pead_data(UNIVERSE, START_DATE, END_DATE)
    tickers_available = [
        t for t in UNIVERSE
        if t in data['Close'].columns and data['Close'][t].dropna().shape[0] > 200
    ]
    print(f"  Available tickers: {len(tickers_available)}")

    # 2. Compute gaps
    print("\n[2] Computing overnight gaps...")
    ticker_frames = compute_gaps(data, tickers_available)
    for ticker, df in ticker_frames.items():
        df.attrs['ticker'] = ticker
    print(f"  Processed {len(ticker_frames)} tickers")

    # ── SECTION 3: Base variants (threshold × hold × direction) ──────────────
    print("\n[3] Running base strategy variants...")

    for threshold in THRESHOLDS:
        for hold in HOLD_PERIODS:
            for direction in DIRECTIONS:
                variant_name = f'gap{int(threshold*100)}pct_hold{hold}d_{direction}'
                logger = TradeLogger(
                    round_num=ROUND_NUM,
                    strategy=variant_name,
                    category='pead'
                )

                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                log_trades(all_trades, logger, threshold, hold, variant_name)
                logger.save()
                print(f"  {variant_name}: {len(all_trades)} trades logged")

    # ── SECTION 4: Volume filter variants ────────────────────────────────────
    print("\n[4] Volume filter variants...")

    for threshold in THRESHOLDS:
        for hold in [10, 20, 40]:
            for direction in DIRECTIONS:
                variant_name = f'gap{int(threshold*100)}pct_hold{hold}d_{direction}_vol'
                logger = TradeLogger(
                    round_num=ROUND_NUM,
                    strategy=variant_name,
                    category='pead'
                )

                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction,
                                            volume_filter=True)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                log_trades(all_trades, logger, threshold, hold, variant_name)
                logger.save()
                print(f"  {variant_name}: {len(all_trades)} trades logged")

    # ── SECTION 5: Trend filter variants ─────────────────────────────────────
    print("\n[5] Trend filter variants...")

    for threshold in [0.03, 0.04]:
        for hold in [20, 40]:
            for direction in DIRECTIONS:
                variant_name = f'gap{int(threshold*100)}pct_hold{hold}d_{direction}_trend'
                logger = TradeLogger(
                    round_num=ROUND_NUM,
                    strategy=variant_name,
                    category='pead'
                )

                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction,
                                            trend_filter=True)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                log_trades(all_trades, logger, threshold, hold, variant_name)
                logger.save()
                print(f"  {variant_name}: {len(all_trades)} trades logged")

    # ── SECTION 6: Combined filter variants ──────────────────────────────────
    print("\n[6] Combined filter variants...")

    for threshold in [0.03, 0.04]:
        for hold in [20, 40]:
            variant_name = f'gap{int(threshold*100)}pct_hold{hold}d_both_combined'
            logger = TradeLogger(
                round_num=ROUND_NUM,
                strategy=variant_name,
                category='pead'
            )

            all_trades = []
            for ticker, df in ticker_frames.items():
                df_copy = df.copy()
                df_copy.attrs['ticker'] = ticker
                trades = backtest_ticker(df_copy, threshold, hold, 'both',
                                        volume_filter=True, trend_filter=True)
                for t in trades:
                    t['ticker'] = ticker
                all_trades.extend(trades)

            log_trades(all_trades, logger, threshold, hold, variant_name)
            logger.save()
            print(f"  {variant_name}: {len(all_trades)} trades logged")

    print("\nAll strategy variants complete.")
    print("Trade logs written to: /workspace/group/trading_eval/trade_logs/")


if __name__ == '__main__':
    main()
    print("\nDone.")
