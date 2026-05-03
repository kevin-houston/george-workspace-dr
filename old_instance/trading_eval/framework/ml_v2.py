#!/usr/bin/env python3
"""
ml_v2.py — ML Trading Strategy Trade Logger (Framework v2)
===========================================================
Replays the walk-forward ML backtest from ml_harness.py and logs
individual trades via TradeLogger.

Strategy variants (one logger each):
  ML R1: xgboost
  ML R1: random_forest
  ML R1: logistic
  ML R1: gradient_boosting
  ML R1: ensemble (average of all model probabilities)

round_num=1, category='ml'

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/ml_v2.py
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

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import xgboost as xgb

from base_harness import TradeLogger, fetch_data, get_close

# ─── Universe ───────────────────────────────────────────────────────────────

UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'JPM', 'JNJ', 'UNH', 'V',
    'MA', 'HD', 'PG', 'COST', 'XOM', 'CVX', 'BAC', 'WMT', 'MRK', 'PFE'
]

START = '2020-01-01'
END   = '2025-12-31'

CACHE_DIR = '/workspace/group/trading_eval/cache'
os.makedirs(CACHE_DIR, exist_ok=True)

ROUND_NUM = 1

# ─── Data download ──────────────────────────────────────────────────────────

def download_data():
    """Download OHLCV data for universe + SPY."""
    tickers = UNIVERSE + ['SPY']
    cache_path = os.path.join(CACHE_DIR, 'ml_raw_data.pkl')

    if os.path.exists(cache_path):
        print("Loading cached data...")
        data = pd.read_pickle(cache_path)
        return data

    print(f"Downloading data for {len(tickers)} tickers...")
    data = {}
    for ticker in tickers:
        try:
            df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
            if len(df) > 200:
                # Flatten MultiIndex columns if present
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [col[0] if col[1] == '' else col[0] for col in df.columns]
                data[ticker] = df
                print(f"  {ticker}: {len(df)} rows")
            else:
                print(f"  {ticker}: insufficient data ({len(df)} rows)")
        except Exception as e:
            print(f"  {ticker}: download failed - {e}")

    pd.to_pickle(data, cache_path)
    return data

# ─── Feature engineering ────────────────────────────────────────────────────

def compute_rsi(prices, period):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / (avg_loss + 1e-10)
    return 100 - (100 / (1 + rs))

def build_features(stock_df, spy_df):
    """Build feature matrix for one stock."""
    df = stock_df.copy()
    close = df['Close']
    high  = df['High']
    low   = df['Low']
    vol   = df['Volume']

    feat = pd.DataFrame(index=df.index)

    # Price / SMA features
    for w in [5, 20, 60, 200]:
        sma = close.rolling(w).mean()
        feat[f'close_sma{w}'] = close / sma

    # Return features
    for d in [1, 5, 10, 20]:
        feat[f'ret_{d}d'] = close.pct_change(d)

    # Volatility
    ret_1d = close.pct_change()
    feat['vol_10d'] = ret_1d.rolling(10).std()
    feat['vol_20d'] = ret_1d.rolling(20).std()

    # Volume
    feat['vol_ratio'] = vol / vol.rolling(20).mean()

    # Momentum / RSI
    feat['rsi_14'] = compute_rsi(close, 14)
    feat['rsi_28'] = compute_rsi(close, 28)

    # Intraday range
    feat['range'] = (high - low) / close

    # Macro proxy: SPY 20d return
    spy_ret = spy_df['Close'].pct_change(20).reindex(df.index)
    feat['spy_20d_ret'] = spy_ret

    # Target: next 5-day return > 0
    fwd_ret = close.pct_change(5).shift(-5)
    feat['target'] = (fwd_ret > 0).astype(int)
    feat['fwd_ret'] = fwd_ret  # keep for backtest

    # Store close for logging entry/exit prices
    feat['close_price'] = close

    return feat.dropna()

# ─── Walk-forward backtest ───────────────────────────────────────────────────

FEATURE_COLS = [
    'close_sma5', 'close_sma20', 'close_sma60', 'close_sma200',
    'ret_1d', 'ret_5d', 'ret_10d', 'ret_20d',
    'vol_10d', 'vol_20d', 'vol_ratio',
    'rsi_14', 'rsi_28', 'range', 'spy_20d_ret'
]

def make_models():
    return {
        'xgboost': xgb.XGBClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            use_label_encoder=False, eval_metric='logloss',
            verbosity=0, random_state=42
        ),
        'random_forest': RandomForestClassifier(
            n_estimators=100, max_depth=5, random_state=42, n_jobs=1
        ),
        'logistic': LogisticRegression(
            max_iter=500, random_state=42, C=1.0
        ),
        'gradient_boosting': GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42
        ),
    }

def walk_forward(feat_df, train_window=252, test_window=21, buy_thresh=0.6, sell_thresh=0.4):
    """
    Rolling walk-forward: train on 252 days, test on 21 days, slide 21 days.
    Returns dict of model_name -> list of (date, signal, fwd_ret, prob, entry_price) tuples.
    """
    X = feat_df[FEATURE_COLS].values
    y = feat_df['target'].values
    fwd = feat_df['fwd_ret'].values
    dates = feat_df.index
    closes = feat_df['close_price'].values

    n = len(feat_df)
    results = {name: [] for name in make_models()}

    start_idx = train_window
    while start_idx + test_window <= n:
        train_slice = slice(start_idx - train_window, start_idx)
        test_slice  = slice(start_idx, start_idx + test_window)

        X_train, y_train = X[train_slice], y[train_slice]
        X_test  = X[test_slice]
        fwd_test = fwd[test_slice]
        dates_test = dates[test_slice]
        closes_test = closes[test_slice]

        # Skip if target is all one class
        if len(np.unique(y_train)) < 2:
            start_idx += test_window
            continue

        models = make_models()
        for name, model in models.items():
            try:
                scaler = StandardScaler()
                Xtr = scaler.fit_transform(X_train)
                Xte = scaler.transform(X_test)

                model.fit(Xtr, y_train)
                probs = model.predict_proba(Xte)[:, 1]

                for d, p, r, entry_price in zip(dates_test, probs, fwd_test, closes_test):
                    if p > buy_thresh:
                        signal = 1
                    elif p < sell_thresh:
                        signal = -1
                    else:
                        signal = 0
                    results[name].append({
                        'date':        d,
                        'prob':        float(p),
                        'signal':      signal,
                        'fwd_ret':     float(r) if not np.isnan(r) else 0.0,
                        'entry_price': float(entry_price),
                    })
            except Exception:
                pass  # skip failed windows

        start_idx += test_window

    return results

def ensemble_signals(model_results, buy_thresh=0.6, sell_thresh=0.4):
    """Average probability across models, recompute signal."""
    all_dates = {}
    for name, trades in model_results.items():
        for t in trades:
            d = t['date']
            if d not in all_dates:
                all_dates[d] = {'probs': [], 'fwd_ret': t['fwd_ret'],
                                'entry_price': t['entry_price']}
            all_dates[d]['probs'].append(t['prob'])

    ensemble = []
    for d, v in all_dates.items():
        avg_p = np.mean(v['probs'])
        if avg_p > buy_thresh:
            sig = 1
        elif avg_p < sell_thresh:
            sig = -1
        else:
            sig = 0
        ensemble.append({
            'date':        d,
            'prob':        avg_p,
            'signal':      sig,
            'fwd_ret':     v['fwd_ret'],
            'entry_price': v['entry_price'],
        })

    return ensemble

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ML Trading Harness v2 — Trade Logger")
    print("=" * 60)

    data = download_data()
    spy_df = data.get('SPY')
    if spy_df is None:
        print("ERROR: SPY data not available")
        return

    # One TradeLogger per model type
    model_names = ['xgboost', 'random_forest', 'logistic', 'gradient_boosting', 'ensemble']
    loggers = {
        name: TradeLogger(round_num=ROUND_NUM, strategy=f'ml_{name}', category='ml')
        for name in model_names
    }

    hold_days = 5  # walk_forward uses 5-day forward return window

    for ticker in UNIVERSE:
        if ticker not in data:
            print(f"Skipping {ticker} (no data)")
            continue

        stock_df = data[ticker]
        print(f"\nProcessing {ticker}...")

        try:
            feat_df = build_features(stock_df, spy_df)
        except Exception as e:
            print(f"  Feature build failed: {e}")
            continue

        if len(feat_df) < 300:
            print(f"  Too few rows ({len(feat_df)}), skipping")
            continue

        # Walk-forward
        try:
            wf_results = walk_forward(feat_df)
        except Exception as e:
            print(f"  Walk-forward failed: {e}")
            continue

        # Ensemble
        ens_trades = ensemble_signals(wf_results)
        wf_results['ensemble'] = ens_trades

        for model_name, trades in wf_results.items():
            logger = loggers[model_name]
            active_trades = [t for t in trades if t['signal'] != 0]

            for t in active_trades:
                entry_date = t['date']
                # Exit date is approximately 5 trading days later
                entry_idx = feat_df.index.get_loc(entry_date) if entry_date in feat_df.index else None
                if entry_idx is not None and entry_idx + hold_days < len(feat_df):
                    exit_date  = feat_df.index[entry_idx + hold_days]
                    exit_price = float(feat_df['close_price'].iloc[entry_idx + hold_days])
                else:
                    exit_date  = entry_date
                    exit_price = t['entry_price']

                direction = 'long' if t['signal'] == 1 else 'short'
                # return_pct is signed: signal * fwd_ret
                return_pct = float(t['signal'] * t['fwd_ret'])

                logger.log(
                    ticker      = ticker,
                    entry_date  = entry_date,
                    exit_date   = exit_date,
                    return_pct  = return_pct,
                    hold_days   = hold_days,
                    direction   = direction,
                    entry_price = t['entry_price'],
                    exit_price  = exit_price,
                    params      = {
                        'model_type': model_name,
                        'features':   FEATURE_COLS,
                        'train_window': 252,
                        'test_window':  21,
                        'buy_thresh':   0.6,
                        'sell_thresh':  0.4,
                    },
                    notes       = (
                        f"signal={t['signal']} prob={t['prob']:.3f} "
                        f"fwd_ret={t['fwd_ret']:.4f}"
                    ),
                    prob        = t['prob'],
                    signal      = t['signal'],
                    fwd_ret     = t['fwd_ret'],
                )

            print(f"  {model_name:22s}  logged {len(active_trades)} active trades")

    # Save all loggers
    print("\nSaving trade logs...")
    for name, logger in loggers.items():
        logger.save()

    print("\nDone.")
    for name, logger in loggers.items():
        print(f"  {name}: {len(logger)} trades")

if __name__ == '__main__':
    main()
