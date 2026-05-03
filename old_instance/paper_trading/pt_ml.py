#!/usr/bin/env python3
"""
Strategy 5: ML Ensemble Paper Trader
Weekly signal on top 5 ML stocks (XOM, WMT, PG, JPM, HD).
Uses XGBoost + Random Forest + Gradient Boosting ensemble.
Features: vol_20d, RSI_14, price/SMA ratios, ret_10d, ret_20d.
Signal: prob > 0.60 → long 5 days. Retrains every Sunday.
"""

import sys, json
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'yfinance', 'pandas', 'numpy', 'scikit-learn', 'xgboost',
                    '--target=/tmp/eval_deps', '--quiet'])
    import yfinance as yf
    import pandas as pd
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb

PORTFOLIO_FILE  = Path(__file__).parent / 'ml_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 1000.0   # $1,000 per stock (max 5 positions)
SYMBOLS         = ['XOM', 'WMT', 'PG', 'JPM', 'HD']
HOLD_DAYS       = 5
PROB_LONG       = 0.60
TRAIN_DAYS      = 504   # ~2 years

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'ML Ensemble',
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None,
        'last_retrain': None,
        'signals': {}
    }

def save(data):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    c = df['Close'].squeeze()
    v = df['Volume'].squeeze()
    feat = pd.DataFrame(index=c.index)
    feat['ret_1d']     = c.pct_change(1)
    feat['ret_5d']     = c.pct_change(5)
    feat['ret_10d']    = c.pct_change(10)
    feat['ret_20d']    = c.pct_change(20)
    feat['vol_10d']    = feat['ret_1d'].rolling(10).std()
    feat['vol_20d']    = feat['ret_1d'].rolling(20).std()
    feat['sma5_r']     = c / c.rolling(5).mean()
    feat['sma20_r']    = c / c.rolling(20).mean()
    feat['sma60_r']    = c / c.rolling(60).mean()
    feat['sma200_r']   = c / c.rolling(200).mean()
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / (loss + 1e-9)
    feat['rsi_14']     = 100 - 100 / (1 + rs)
    delta28 = c.diff()
    g28 = delta28.clip(lower=0).rolling(28).mean()
    l28 = (-delta28.clip(upper=0)).rolling(28).mean()
    rs28 = g28 / (l28 + 1e-9)
    feat['rsi_28']     = 100 - 100 / (1 + rs28)
    feat['vol_ratio']  = v / v.rolling(20).mean()
    feat['range']      = (df['High'].squeeze() - df['Low'].squeeze()) / c
    feat['target']     = (c.pct_change(5).shift(-5) > 0).astype(int)
    return feat.dropna()

def train_and_predict(sym: str) -> tuple[float, str]:
    """Returns (ensemble_prob_long, signal) or (0.5, 'neutral') on failure."""
    df = yf.download(sym, period='3y', interval='1d', progress=False, auto_adjust=True)
    if df.empty or len(df) < 250:
        return 0.5, 'neutral'
    feat = build_features(df)
    if len(feat) < 200:
        return 0.5, 'neutral'

    cols = [c for c in feat.columns if c != 'target']
    X    = feat[cols].values
    y    = feat['target'].values

    X_train, y_train = X[:-HOLD_DAYS-1], y[:-HOLD_DAYS-1]
    X_pred           = X[-1:].copy()

    if len(np.unique(y_train)) < 2:
        return 0.5, 'neutral'

    scaler  = StandardScaler().fit(X_train)
    Xtr_sc  = scaler.transform(X_train)
    Xpr_sc  = scaler.transform(X_pred)

    models = [
        RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42, n_jobs=1),
        GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.1, random_state=42),
        LogisticRegression(max_iter=1000, random_state=42),
        xgb.XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.1,
                           use_label_encoder=False, eval_metric='logloss',
                           verbosity=0, random_state=42),
    ]

    probs = []
    for m in models:
        try:
            if isinstance(m, (LogisticRegression,)):
                m.fit(Xtr_sc, y_train)
                p = m.predict_proba(Xpr_sc)[0][1]
            else:
                m.fit(X_train, y_train)
                p = m.predict_proba(X_pred)[0][1]
            probs.append(p)
        except Exception:
            pass

    if not probs:
        return 0.5, 'neutral'

    ensemble_prob = np.mean(probs)
    if ensemble_prob >= PROB_LONG:
        return ensemble_prob, 'long'
    return ensemble_prob, 'neutral'

def add_trading_days(start: date, n: int) -> date:
    cur, added = start, 0
    while added < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5: added += 1
    return cur

def run():
    data = load()
    today = str(date.today())
    today_d = date.today()

    # Check exits first
    to_exit = []
    for sym, pos in list(data['open_positions'].items()):
        exit_d = date.fromisoformat(pos['exit_date'])
        if today_d >= exit_d:
            to_exit.append(sym)

    for sym in to_exit:
        pos    = data['open_positions'][sym]
        hist   = yf.download(sym, period='3d', interval='1d', progress=False, auto_adjust=True)
        price  = float(hist['Close'].squeeze().iloc[-1]) if not hist.empty else pos['entry_price']
        pnl    = pos['shares'] * (price - pos['entry_price'])
        ret    = (price / pos['entry_price'] - 1) * 100
        win    = pnl > 0
        data['trades'].append({'symbol': sym, 'entry_date': pos['entry_date'],
                                'exit_date': today, 'entry_price': pos['entry_price'],
                                'exit_price': price, 'return_pct': round(ret/100, 4),
                                'pnl_usd': round(pnl, 2), 'win': win,
                                'entry_prob': pos.get('entry_prob', 0)})
        data['stats']['n_trades'] += 1
        data['stats']['total_pnl'] += pnl
        if win: data['stats']['wins'] += 1
        del data['open_positions'][sym]
        print(f"  EXIT {sym} @ ${price:.2f}  P&L=${pnl:+.2f}  ({'WIN' if win else 'LOSS'})")

    # Generate new signals (weekly on Monday, or first run)
    last_retrain = data.get('last_retrain')
    should_retrain = (last_retrain is None or
                      (today_d - date.fromisoformat(last_retrain)).days >= 5)

    if should_retrain:
        print(f"  Retraining ML ensemble on {today}...")
        signals = {}
        for sym in SYMBOLS:
            prob, sig = train_and_predict(sym)
            signals[sym] = {'prob': round(prob, 3), 'signal': sig}
            print(f"    {sym}: prob={prob:.3f}  signal={sig}")
        data['signals']      = signals
        data['last_retrain'] = today
    else:
        signals = data.get('signals', {})
        print(f"  Using cached signals from {last_retrain}")

    # Enter new positions
    for sym, sig_info in signals.items():
        if sig_info['signal'] == 'long' and sym not in data['open_positions']:
            hist  = yf.download(sym, period='3d', interval='1d', progress=False, auto_adjust=True)
            if hist.empty: continue
            price  = float(hist['Close'].squeeze().iloc[-1])
            shares = POSITION_SIZE / price
            exit_d = add_trading_days(today_d, HOLD_DAYS)
            data['open_positions'][sym] = {
                'entry_price': price, 'shares': shares,
                'entry_date': today, 'exit_date': str(exit_d),
                'entry_prob': sig_info['prob']
            }
            print(f"  ENTER {sym} @ ${price:.2f}  prob={sig_info['prob']:.3f}  exit {exit_d}")

    data['last_update'] = today
    save(data)
    return data

if __name__ == '__main__':
    print(f"=== ML Ensemble — {date.today()} ===")
    run()
    print("Done.")
