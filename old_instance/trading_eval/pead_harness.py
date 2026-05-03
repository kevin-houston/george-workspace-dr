"""
PEAD (Post-Earnings Announcement Drift) Research Harness
Karpathy autoresearch loop - systematic evaluation of PEAD strategies
Uses large overnight gaps as earnings announcement proxies
"""

import sys
sys.path.insert(0, '/tmp/eval_deps_pead')

import json
import os
import warnings
import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime, timedelta
import time

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# UNIVERSE & CONFIG
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
os.makedirs('/workspace/group/trading_eval/rounds', exist_ok=True)


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────
def fetch_data(tickers, start, end, retries=3):
    """Download OHLCV data for all tickers with caching."""
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
                    # Flatten multi-level columns if present
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    all_data[ticker] = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                    print(f"  {ticker}: {len(df)} rows")
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f"  {ticker} attempt {attempt+1} failed: {e}")
                time.sleep(1)

    # Build multi-column DataFrame
    combined = {}
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        combined[col] = pd.DataFrame({t: all_data[t][col] for t in all_data if col in all_data[t].columns})

    result = pd.concat({col: combined[col] for col in combined}, axis=1)
    result.to_pickle(cache_file)
    print(f"  Saved cache: {cache_file}")
    return result


# ─────────────────────────────────────────────
# GAP DETECTION
# ─────────────────────────────────────────────
def compute_gaps(data, tickers):
    """
    Compute overnight gap = open / prev_close - 1 for each ticker.
    Returns dict of per-ticker DataFrames with gap column.
    """
    ticker_frames = {}
    for ticker in tickers:
        try:
            close = data['Close'][ticker].dropna()
            open_ = data['Open'][ticker].dropna()
            volume = data['Volume'][ticker].dropna()

            df = pd.DataFrame({
                'close': close,
                'open': open_,
                'volume': volume
            }).dropna()

            df['prev_close'] = df['close'].shift(1)
            df['gap'] = df['open'] / df['prev_close'] - 1

            # 20-day average volume
            df['vol_avg20'] = df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['volume'] / df['vol_avg20']

            # 60-day trend (close vs 60d EMA)
            df['ema60'] = df['close'].ewm(span=60).mean()
            df['trend_up'] = df['close'] > df['ema60']

            ticker_frames[ticker] = df.dropna()
        except Exception as e:
            print(f"  Gap compute failed for {ticker}: {e}")

    return ticker_frames


# ─────────────────────────────────────────────
# SINGLE-TICKER BACKTEST
# ─────────────────────────────────────────────
def backtest_ticker(df, threshold, hold_period, direction,
                    volume_filter=False, trend_filter=False):
    """
    Backtest PEAD on a single ticker.
    Returns list of trade dicts.
    """
    trades = []
    in_trade_until = None  # index when current trade expires

    dates = df.index.tolist()

    for i, date in enumerate(dates):
        row = df.loc[date]

        # Skip if already in a trade
        if in_trade_until is not None and date <= in_trade_until:
            continue

        gap = row['gap']

        # Determine signal
        signal = None
        if direction in ('long', 'both') and gap > threshold:
            signal = 'long'
        elif direction in ('short', 'both') and gap < -threshold:
            signal = 'short'

        if signal is None:
            continue

        # Volume filter
        if volume_filter and row['vol_ratio'] < 1.5:
            continue

        # Trend filter
        if trend_filter:
            if signal == 'long' and not row['trend_up']:
                continue
            if signal == 'short' and row['trend_up']:
                continue

        # Entry: next day open (i+1) to avoid same-day execution
        entry_idx = i + 1
        exit_idx  = i + 1 + hold_period

        if entry_idx >= len(dates) or exit_idx >= len(dates):
            continue

        entry_date = dates[entry_idx]
        exit_date  = dates[exit_idx]

        entry_price = df.loc[entry_date, 'open']
        exit_price  = df.loc[exit_date, 'open']  # exit at open on exit day

        if entry_price <= 0 or exit_price <= 0:
            continue

        raw_return = exit_price / entry_price - 1
        trade_return = raw_return if signal == 'long' else -raw_return

        trades.append({
            'ticker': df.attrs.get('ticker', '?'),
            'gap_date': date,
            'entry_date': entry_date,
            'exit_date': exit_date,
            'gap': gap,
            'signal': signal,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'return': trade_return,
            'vol_ratio': row['vol_ratio'],
            'trend_up': bool(row['trend_up'])
        })

        in_trade_until = exit_date

    return trades


# ─────────────────────────────────────────────
# COMPUTE METRICS
# ─────────────────────────────────────────────
def compute_metrics(trades):
    """Compute Sharpe, win rate, avg return, t-test."""
    if len(trades) < 5:
        return None

    returns = np.array([t['return'] for t in trades])
    n = len(returns)
    mean_ret = returns.mean()
    std_ret  = returns.std(ddof=1) if n > 1 else 1e-9

    # Annualised Sharpe (assume ~252 trading days, each trade is independent)
    # Use trade-level Sharpe scaled by sqrt(252/avg_hold)
    avg_hold = np.mean([(t['exit_date'] - t['entry_date']).days for t in trades])
    trades_per_year = 252 / max(avg_hold, 1)
    sharpe = (mean_ret / (std_ret + 1e-9)) * np.sqrt(trades_per_year)

    win_rate = (returns > 0).mean()

    t_stat, p_value = stats.ttest_1samp(returns, 0)

    return {
        'n_trades': n,
        'sharpe': round(float(sharpe), 4),
        'win_rate': round(float(win_rate), 4),
        'avg_return': round(float(mean_ret), 5),
        'std_return': round(float(std_ret), 5),
        't_stat': round(float(t_stat), 4),
        'p_value': round(float(p_value), 4)
    }


# ─────────────────────────────────────────────
# PORTFOLIO SIMULATION
# ─────────────────────────────────────────────
def portfolio_backtest(ticker_frames, threshold, hold_period,
                       volume_filter=False, trend_filter=False,
                       max_positions=5):
    """
    Equal-weight portfolio of all gap signals, max N concurrent positions.
    Returns daily portfolio equity curve and summary stats.
    """
    # Collect ALL signals across universe
    all_signals = []
    for ticker, df in ticker_frames.items():
        df = df.copy()
        df.attrs['ticker'] = ticker
        trades = backtest_ticker(df, threshold, hold_period, 'both',
                                 volume_filter, trend_filter)
        for t in trades:
            t['ticker'] = ticker
        all_signals.extend(trades)

    if len(all_signals) < 10:
        return None

    # Sort by entry date
    all_signals.sort(key=lambda x: x['entry_date'])

    # Simulate portfolio with max_positions cap
    # Track active positions by date
    # Build a daily P&L series
    all_dates = sorted(set(
        d for t in all_signals
        for d in pd.date_range(t['entry_date'], t['exit_date'], freq='B')
    ))
    if not all_dates:
        return None

    date_index = pd.DatetimeIndex(all_dates)
    daily_pnl = pd.Series(0.0, index=date_index)

    active = []  # list of active trade dicts
    completed = []

    for sig in all_signals:
        entry = sig['entry_date']
        # Remove expired positions
        active = [a for a in active if a['exit_date'] > entry]

        if len(active) >= max_positions:
            continue  # skip, at capacity

        active.append(sig)
        completed.append(sig)

    # Build daily returns from completed trades
    # Each trade contributes return / hold_period per day (rough approx)
    port_returns = []
    for t in completed:
        hold_days = max((t['exit_date'] - t['entry_date']).days, 1)
        daily_r = t['return'] / hold_days
        dates = pd.date_range(t['entry_date'], t['exit_date'] - timedelta(days=1), freq='B')
        for d in dates:
            port_returns.append({'date': d, 'return': daily_r})

    if not port_returns:
        return None

    port_df = pd.DataFrame(port_returns)
    daily = port_df.groupby('date')['return'].mean()  # equal weight average

    # Metrics
    ann_return = daily.mean() * 252
    ann_vol = daily.std() * np.sqrt(252)
    sharpe = ann_return / (ann_vol + 1e-9)

    # Max drawdown
    equity = (1 + daily).cumprod()
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = float(drawdown.min())

    returns_arr = daily.values
    t_stat, p_value = stats.ttest_1samp(returns_arr, 0)

    return {
        'n_trades': len(completed),
        'portfolio_sharpe': round(float(sharpe), 4),
        'portfolio_ann_return': round(float(ann_return), 4),
        'portfolio_ann_vol': round(float(ann_vol), 4),
        'portfolio_max_dd': round(float(max_dd), 4),
        'p_value': round(float(p_value), 4),
        't_stat': round(float(t_stat), 4),
    }


# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("PEAD Research Harness - Karpathy Autoresearch Loop")
    print("=" * 60)

    # 1. Fetch data
    print("\n[1] Downloading market data...")
    data = fetch_data(UNIVERSE, START_DATE, END_DATE)
    tickers_available = [t for t in UNIVERSE if t in data['Close'].columns
                         and data['Close'][t].dropna().shape[0] > 200]
    print(f"  Available tickers: {len(tickers_available)}")

    # 2. Compute gaps
    print("\n[2] Computing overnight gaps...")
    ticker_frames = compute_gaps(data, tickers_available)
    for ticker, df in ticker_frames.items():
        df.attrs['ticker'] = ticker
    print(f"  Processed {len(ticker_frames)} tickers")

    # 3. Variant backtests
    print("\n[3] Running strategy variants...")
    results_matrix = []

    # Base variants: threshold x hold x direction
    for threshold in THRESHOLDS:
        for hold in HOLD_PERIODS:
            for direction in DIRECTIONS:
                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                m = compute_metrics(all_trades)
                if m:
                    row = {
                        'threshold': threshold,
                        'hold': hold,
                        'direction': direction,
                        'volume_filter': False,
                        'trend_filter': False,
                        'variant': f'gap{int(threshold*100)}pct_hold{hold}d_{direction}',
                        **m
                    }
                    results_matrix.append(row)
                    print(f"  {row['variant']}: Sharpe={m['sharpe']:.3f} "
                          f"WR={m['win_rate']:.2%} N={m['n_trades']} p={m['p_value']:.3f}")

    # Volume filter variants
    print("\n[4] Volume filter variants...")
    for threshold in THRESHOLDS:
        for hold in [10, 20, 40]:
            for direction in DIRECTIONS:
                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction,
                                            volume_filter=True)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                m = compute_metrics(all_trades)
                if m:
                    row = {
                        'threshold': threshold,
                        'hold': hold,
                        'direction': direction,
                        'volume_filter': True,
                        'trend_filter': False,
                        'variant': f'gap{int(threshold*100)}pct_hold{hold}d_{direction}_vol',
                        **m
                    }
                    results_matrix.append(row)
                    print(f"  {row['variant']}: Sharpe={m['sharpe']:.3f} "
                          f"WR={m['win_rate']:.2%} N={m['n_trades']} p={m['p_value']:.3f}")

    # Trend filter variants
    print("\n[5] Trend filter variants...")
    for threshold in [0.03, 0.04]:
        for hold in [20, 40]:
            for direction in DIRECTIONS:
                all_trades = []
                for ticker, df in ticker_frames.items():
                    df_copy = df.copy()
                    df_copy.attrs['ticker'] = ticker
                    trades = backtest_ticker(df_copy, threshold, hold, direction,
                                            trend_filter=True)
                    for t in trades:
                        t['ticker'] = ticker
                    all_trades.extend(trades)

                m = compute_metrics(all_trades)
                if m:
                    row = {
                        'threshold': threshold,
                        'hold': hold,
                        'direction': direction,
                        'volume_filter': False,
                        'trend_filter': True,
                        'variant': f'gap{int(threshold*100)}pct_hold{hold}d_{direction}_trend',
                        **m
                    }
                    results_matrix.append(row)

    # Combined filter
    print("\n[6] Combined filter variants...")
    for threshold in [0.03, 0.04]:
        for hold in [20, 40]:
            all_trades = []
            for ticker, df in ticker_frames.items():
                df_copy = df.copy()
                df_copy.attrs['ticker'] = ticker
                trades = backtest_ticker(df_copy, threshold, hold, 'both',
                                        volume_filter=True, trend_filter=True)
                for t in trades:
                    t['ticker'] = ticker
                all_trades.extend(trades)

            m = compute_metrics(all_trades)
            if m:
                row = {
                    'threshold': threshold,
                    'hold': hold,
                    'direction': 'both',
                    'volume_filter': True,
                    'trend_filter': True,
                    'variant': f'gap{int(threshold*100)}pct_hold{hold}d_both_combined',
                    **m
                }
                results_matrix.append(row)
                print(f"  {row['variant']}: Sharpe={m['sharpe']:.3f} "
                      f"WR={m['win_rate']:.2%} N={m['n_trades']} p={m['p_value']:.3f}")

    # 4. Find best variant
    if not results_matrix:
        print("ERROR: No valid results generated")
        return

    best = max(results_matrix, key=lambda x: x['sharpe'])
    print(f"\n[7] Best variant: {best['variant']}")
    print(f"    Sharpe={best['sharpe']:.4f} WR={best['win_rate']:.2%} "
          f"N={best['n_trades']} p={best['p_value']:.4f}")

    # 5. Portfolio backtest with best params
    print("\n[8] Portfolio backtest...")
    port = portfolio_backtest(
        ticker_frames,
        threshold=best['threshold'],
        hold_period=best['hold'],
        volume_filter=best.get('volume_filter', False),
        trend_filter=best.get('trend_filter', False),
        max_positions=5
    )
    print(f"  Portfolio Sharpe: {port['portfolio_sharpe'] if port else 'N/A'}")
    print(f"  Portfolio Max DD: {port['portfolio_max_dd'] if port else 'N/A'}")

    # Also run portfolio with 3% / 20d / no filters as canonical reference
    port_canonical = portfolio_backtest(
        ticker_frames,
        threshold=0.03,
        hold_period=20,
        volume_filter=False,
        trend_filter=False,
        max_positions=5
    )

    # 6. Long vs Short asymmetry analysis
    print("\n[9] Long vs Short asymmetry analysis...")
    asymmetry = {}
    for threshold in THRESHOLDS:
        long_trades, short_trades = [], []
        for ticker, df in ticker_frames.items():
            df_copy = df.copy()
            df_copy.attrs['ticker'] = ticker
            lt = backtest_ticker(df_copy, threshold, 20, 'long')
            st = backtest_ticker(df_copy, threshold, 20, 'short')
            long_trades.extend(lt)
            short_trades.extend(st)

        lm = compute_metrics(long_trades)
        sm = compute_metrics(short_trades)
        asymmetry[f'thr_{int(threshold*100)}pct'] = {
            'long': lm,
            'short': sm,
            'long_n': len(long_trades),
            'short_n': len(short_trades)
        }
        print(f"  Thr={threshold:.0%}: Long Sharpe={lm['sharpe'] if lm else 'N/A':.3f} "
              f"Short Sharpe={sm['sharpe'] if sm else 'N/A':.3f}")

    # 7. Statistical significance on best variant
    best_all_trades = []
    for ticker, df in ticker_frames.items():
        df_copy = df.copy()
        df_copy.attrs['ticker'] = ticker
        trades = backtest_ticker(
            df_copy,
            best['threshold'],
            best['hold'],
            best['direction'],
            volume_filter=best.get('volume_filter', False),
            trend_filter=best.get('trend_filter', False)
        )
        for t in trades:
            t['ticker'] = ticker
        best_all_trades.extend(trades)

    returns_arr = np.array([t['return'] for t in best_all_trades])
    t_stat, p_value = stats.ttest_1samp(returns_arr, 0) if len(returns_arr) > 1 else (0, 1)

    # 8. Summary stats by year
    print("\n[10] Year-by-year analysis...")
    year_stats = {}
    for year in range(2020, 2026):
        year_trades = [t for t in best_all_trades
                       if t['entry_date'].year == year]
        ym = compute_metrics(year_trades)
        year_stats[str(year)] = ym
        if ym:
            print(f"  {year}: Sharpe={ym['sharpe']:.3f} N={ym['n_trades']} WR={ym['win_rate']:.2%}")

    # ─────────────────────────────────────────
    # SAVE RESULTS
    # ─────────────────────────────────────────
    output = {
        "category": "pead",
        "run_date": datetime.now().isoformat(),
        "universe_size": len(tickers_available),
        "date_range": f"{START_DATE} to {END_DATE}",
        "best_variant": best['variant'],
        "best_sharpe": best['sharpe'],
        "best_winrate": best['win_rate'],
        "best_avg_return": best['avg_return'],
        "best_n_trades": best['n_trades'],
        "best_p_value": best['p_value'],
        "results_matrix": results_matrix,
        "portfolio_sharpe": port['portfolio_sharpe'] if port else None,
        "portfolio_max_dd": port['portfolio_max_dd'] if port else None,
        "portfolio_ann_return": port['portfolio_ann_return'] if port else None,
        "portfolio_n_trades": port['n_trades'] if port else None,
        "canonical_portfolio": port_canonical,
        "long_short_asymmetry": asymmetry,
        "year_by_year": year_stats,
        "stat_significance": {
            "p_value": round(float(p_value), 4),
            "t_stat": round(float(t_stat), 4),
            "n_trades": len(best_all_trades)
        },
        "key_finding": (
            f"{best['variant']} achieved Sharpe {best['sharpe']:.2f} "
            f"with {best['n_trades']} trades (p={p_value:.3f}). "
            f"Portfolio Sharpe: {port['portfolio_sharpe'] if port else 'N/A'}."
        )
    }

    out_path = '/workspace/group/trading_eval/rounds/pead_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    # Print top 10 variants
    sorted_results = sorted(results_matrix, key=lambda x: x['sharpe'], reverse=True)
    print("\nTop 10 variants by Sharpe:")
    for r in sorted_results[:10]:
        print(f"  {r['variant']:<50} Sharpe={r['sharpe']:6.3f} "
              f"WR={r['win_rate']:.2%} N={r['n_trades']:4d} p={r['p_value']:.3f}")

    return output


if __name__ == '__main__':
    result = main()
    print("\nDone.")
