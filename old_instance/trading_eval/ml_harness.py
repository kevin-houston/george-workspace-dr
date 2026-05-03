import sys
sys.path.insert(0, '/tmp/eval_deps')

import os
import json
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
import xgboost as xgb

# ─── Universe ───────────────────────────────────────────────────────────────

UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'JPM', 'JNJ', 'UNH', 'V',
    'MA', 'HD', 'PG', 'COST', 'XOM', 'CVX', 'BAC', 'WMT', 'MRK', 'PFE'
]

START = '2020-01-01'
END   = '2025-12-31'

CACHE_DIR = '/workspace/group/trading_eval/cache'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs('/workspace/group/trading_eval/rounds', exist_ok=True)

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
    Returns dict of model_name -> list of (date, signal, fwd_ret) tuples.
    """
    X = feat_df[FEATURE_COLS].values
    y = feat_df['target'].values
    fwd = feat_df['fwd_ret'].values
    dates = feat_df.index

    n = len(feat_df)
    results = {name: [] for name in make_models()}

    scaler_for = {name: StandardScaler() for name in make_models()}

    start_idx = train_window
    while start_idx + test_window <= n:
        train_slice = slice(start_idx - train_window, start_idx)
        test_slice  = slice(start_idx, start_idx + test_window)

        X_train, y_train = X[train_slice], y[train_slice]
        X_test  = X[test_slice]
        fwd_test = fwd[test_slice]
        dates_test = dates[test_slice]

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

                for d, p, r in zip(dates_test, probs, fwd_test):
                    if p > buy_thresh:
                        signal = 1
                    elif p < sell_thresh:
                        signal = -1
                    else:
                        signal = 0
                    results[name].append({
                        'date': d,
                        'prob': float(p),
                        'signal': signal,
                        'fwd_ret': float(r) if not np.isnan(r) else 0.0,
                    })
            except Exception as e:
                pass  # skip failed windows

        start_idx += test_window

    return results

def compute_metrics(trades):
    """Compute Sharpe, win rate, avg return, n_trades from trade list."""
    active = [t for t in trades if t['signal'] != 0]
    if len(active) < 5:
        return None

    rets = np.array([t['signal'] * t['fwd_ret'] for t in active])
    n = len(rets)
    mean_ret = rets.mean()
    std_ret  = rets.std() + 1e-10
    # Annualise: ~252 trading days / 21 days per period
    sharpe = (mean_ret / std_ret) * np.sqrt(252 / 5)
    win_rate = (rets > 0).mean()
    avg_ret  = mean_ret

    return {
        'sharpe': float(sharpe),
        'win_rate': float(win_rate),
        'avg_ret': float(avg_ret),
        'n_trades': int(n),
    }

def compute_bh_sharpe(feat_df):
    """Buy-and-hold Sharpe on 5-day non-overlapping returns."""
    fwd = feat_df['fwd_ret'].dropna().values[::5]  # non-overlapping ~5d
    if len(fwd) < 5:
        return 0.0
    mean_r = fwd.mean()
    std_r  = fwd.std() + 1e-10
    return float((mean_r / std_r) * np.sqrt(252 / 5))

def get_xgb_feature_importance(feat_df, top_n=5):
    """Train XGB on full data, return top features."""
    X = feat_df[FEATURE_COLS].values
    y = feat_df['target'].values
    if len(np.unique(y)) < 2:
        return []
    model = xgb.XGBClassifier(
        n_estimators=100, max_depth=3, learning_rate=0.1,
        use_label_encoder=False, eval_metric='logloss',
        verbosity=0, random_state=42
    )
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model.fit(Xs, y)
    imp = model.feature_importances_
    idx = np.argsort(imp)[::-1][:top_n]
    return [(FEATURE_COLS[i], float(imp[i])) for i in idx]

# ─── Ensemble ────────────────────────────────────────────────────────────────

def ensemble_signals(model_results, buy_thresh=0.6, sell_thresh=0.4):
    """Average probability across models, recompute signal."""
    # Collect all dates
    all_dates = {}
    for name, trades in model_results.items():
        for t in trades:
            d = t['date']
            if d not in all_dates:
                all_dates[d] = {'probs': [], 'fwd_ret': t['fwd_ret']}
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
        ensemble.append({'date': d, 'prob': avg_p, 'signal': sig, 'fwd_ret': v['fwd_ret']})

    return ensemble

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ML Trading Harness — Karpathy AutoResearch Loop")
    print("=" * 60)

    data = download_data()
    spy_df = data.get('SPY')
    if spy_df is None:
        print("ERROR: SPY data not available")
        return

    all_results = []      # list of dicts for top_results
    model_stats  = {m: {'sharpes': [], 'bh_sharpes': []} for m in
                    ['xgboost', 'random_forest', 'logistic', 'gradient_boosting', 'ensemble']}
    all_feature_imp = []

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

        bh_sharpe = compute_bh_sharpe(feat_df)

        # Feature importance from XGBoost
        try:
            fi = get_xgb_feature_importance(feat_df)
            all_feature_imp.extend(fi)
        except Exception as e:
            print(f"  Feature importance error: {e}")

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
            metrics = compute_metrics(trades)
            if metrics is None:
                continue

            metrics['model']  = model_name
            metrics['symbol'] = ticker
            metrics['bh_sharpe'] = bh_sharpe

            all_results.append(metrics)
            model_stats[model_name]['sharpes'].append(metrics['sharpe'])
            model_stats[model_name]['bh_sharpes'].append(bh_sharpe)

            print(f"  {model_name:20s} sharpe={metrics['sharpe']:+.3f}  "
                  f"win={metrics['win_rate']:.2%}  n={metrics['n_trades']}")

    # ── Aggregate results ────────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("Aggregating results...")

    model_summary = {}
    for mname, stats in model_stats.items():
        if not stats['sharpes']:
            continue
        sharpes = np.array(stats['sharpes'])
        bh_sharpes = np.array(stats['bh_sharpes'])
        beat_bh = (sharpes > bh_sharpes).mean() if len(bh_sharpes) > 0 else 0.0
        model_summary[mname] = {
            'avg_sharpe': float(sharpes.mean()),
            'median_sharpe': float(np.median(sharpes)),
            'std_sharpe': float(sharpes.std()),
            'beat_bh_pct': float(beat_bh),
            'n_stocks': int(len(sharpes)),
        }
        print(f"  {mname:22s}  avg_sharpe={sharpes.mean():+.3f}  "
              f"beat_bh={beat_bh:.1%}  n={len(sharpes)}")

    # Top results sorted by Sharpe
    top_results = sorted(all_results, key=lambda x: x['sharpe'], reverse=True)[:20]

    # Feature importance aggregation
    feat_counter = {}
    for fname, importance in all_feature_imp:
        feat_counter[fname] = feat_counter.get(fname, 0.0) + importance
    top_features = sorted(feat_counter, key=feat_counter.get, reverse=True)[:10]

    # Best strategy
    if top_results:
        best = top_results[0]
        best_strategy = f"{best['model']} on {best['symbol']}"
        best_sharpe = best['sharpe']
    else:
        best_strategy = "N/A"
        best_sharpe = 0.0

    output = {
        'category': 'ml_trading',
        'run_date': datetime.now().isoformat(),
        'universe': UNIVERSE,
        'top_results': [
            {
                'model': r['model'],
                'symbol': r['symbol'],
                'sharpe': round(r['sharpe'], 4),
                'win_rate': round(r['win_rate'], 4),
                'avg_ret': round(r['avg_ret'], 6),
                'n_trades': r['n_trades'],
                'bh_sharpe': round(r['bh_sharpe'], 4),
            }
            for r in top_results
        ],
        'model_summary': model_summary,
        'top_features': top_features,
        'top_feature_importances': {f: round(v, 4) for f, v in
                                    sorted(feat_counter.items(), key=lambda x: -x[1])[:10]},
        'best_strategy': best_strategy,
        'best_sharpe': round(best_sharpe, 4),
        'all_results_count': len(all_results),
    }

    out_path = '/workspace/group/trading_eval/rounds/ml_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    return output

if __name__ == '__main__':
    result = main()
    if result:
        print("\nDone.")
        print(f"Best strategy : {result['best_strategy']}")
        print(f"Best Sharpe   : {result['best_sharpe']}")
