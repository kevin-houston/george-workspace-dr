#!/usr/bin/env python3
"""
H448 — Diffusion IV Surface VRP Signal
Source: arXiv:2511.07571 (Jin & Agarwal, May 2026)

Hypothesis: DDPM-forecast implied volatility minus realized vol produces a
cleaner VRP signal than raw IV-RV spread, because the model enforces
no-arbitrage and conditions on the full surface geometry.

Variants:
  A — raw ATM IV - 20d RV baseline (H266 replication)
  B — EMA-smoothed IV forecast - RV as VRP proxy signal
  C — add term-structure slope (30d vs 90d ATM IV spread)
  D — full-surface PCA → XGBoost SPX return sign classifier

Gate: OOS Sharpe >= 1.0, MaxDD <= 25%
IS:  2018-01-01 to 2022-12-31
OOS: 2023-01-01 to 2026-06-30
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# ── Parameters ────────────────────────────────────────────────────────────────
IS_START   = '2018-01-01'
IS_END     = '2022-12-31'
OOS_START  = '2023-01-01'
OOS_END    = '2026-06-30'

# VRP thresholds (annualised vol points)
VRP_ENTRY_THRESHOLD  = 2.0   # sell vol when VRP > 2 vol pts
VRP_EXIT_THRESHOLD   = 0.5   # exit short-vol when VRP < 0.5

# EMA decay for IV surface smoothing (approximates DDPM conditioning)
EMA_SPAN = 5  # 5-day EMA of IV (papers optimal was ~5 trading days)

# RV window
RV_WINDOW = 20  # 20-day realized vol

# ── Data loading ──────────────────────────────────────────────────────────────
def load_spx_data(start: str, end: str) -> pd.DataFrame:
    """Load SPX daily OHLCV."""
    spx = yf.download('^GSPC', start=start, end=end, progress=False, auto_adjust=True)
    spx = spx[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    spx.index = pd.to_datetime(spx.index)
    return spx


def load_vix_data(start: str, end: str) -> pd.Series:
    """Load VIX (ATM 30d IV proxy for SPX options)."""
    vix = yf.download('^VIX', start=start, end=end, progress=False, auto_adjust=True)['Close']
    vix.index = pd.to_datetime(vix.index)
    return vix.squeeze()


def load_vix9d_vix3m(start: str, end: str) -> tuple:
    """
    Load VIX9D (9-day IV) and VIX3M (93-day IV) for term-structure slope.
    Approximates 30d vs 90d ATM IV spread from the DDPM surface.
    """
    vix9d = yf.download('^VIX9D', start=start, end=end, progress=False, auto_adjust=True)['Close']
    vix3m = yf.download('^VIX3M', start=start, end=end, progress=False, auto_adjust=True)['Close']
    vix9d.index = pd.to_datetime(vix9d.index)
    vix3m.index = pd.to_datetime(vix3m.index)
    return vix9d.squeeze(), vix3m.squeeze()


def compute_realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """20-day annualised realized vol from log returns."""
    log_ret = np.log(close / close.shift(1))
    rv = log_ret.rolling(window).std() * np.sqrt(252) * 100  # convert to vol %
    return rv


def compute_ema_iv_forecast(iv: pd.Series, span: int = 5) -> pd.Series:
    """
    EMA-smoothed IV as tractable proxy for DDPM one-day-ahead forecast.
    Paper's conditional EWMA ablation shows this captures ~80% of model benefit.
    """
    return iv.ewm(span=span, adjust=False).mean().shift(1)  # shift(1) = yesterday's EMA


# ── Signal construction ────────────────────────────────────────────────────────
def build_signals(spx: pd.DataFrame, vix: pd.Series,
                   vix9d: pd.Series, vix3m: pd.Series) -> pd.DataFrame:
    """Construct all variant signals."""
    df = pd.DataFrame(index=spx.index)
    df['spx_ret'] = spx['Close'].pct_change()

    # Realized vol
    df['rv20'] = compute_realized_vol(spx['Close'], RV_WINDOW)

    # ATM IV proxies
    df['vix']   = vix.reindex(df.index).ffill()     # 30d IV (annualised %)
    df['vix9d'] = vix9d.reindex(df.index).ffill()
    df['vix3m'] = vix3m.reindex(df.index).ffill()

    # Var A: raw VRP = VIX - RV20 (baseline)
    df['vrp_raw'] = df['vix'] - df['rv20']

    # Var B: EMA-smoothed IV forecast minus RV (DDPM proxy)
    df['vix_ema_fcst'] = compute_ema_iv_forecast(df['vix'], EMA_SPAN)
    df['vrp_ema']      = df['vix_ema_fcst'] - df['rv20']

    # Var C: term-structure slope (9d vs 3m IV spread)
    df['ts_slope'] = df['vix3m'] - df['vix9d']  # positive = normal contango

    # Combined Var C signal: vrp_ema with ts_slope momentum filter
    # Enter short-vol only when both vrp > threshold AND term structure in contango
    df['vrp_ts_combined'] = df['vrp_ema'] * (df['ts_slope'] > 0).astype(float)

    # Var D: XGBoost feature matrix from VRP components
    df['vix_zscore']   = (df['vix']   - df['vix'].rolling(252).mean()) / df['vix'].rolling(252).std()
    df['rv20_zscore']  = (df['rv20']  - df['rv20'].rolling(252).mean())  / df['rv20'].rolling(252).std()
    df['ts_zscore']    = (df['ts_slope'] - df['ts_slope'].rolling(252).mean()) / df['ts_slope'].rolling(252).std()
    df['vrp_zscore']   = (df['vrp_ema'] - df['vrp_ema'].rolling(252).mean()) / df['vrp_ema'].rolling(252).std()
    df['vix_mom5']     = df['vix'].pct_change(5)
    df['vix_mom21']    = df['vix'].pct_change(21)

    return df.dropna()


# ── Strategy simulation ────────────────────────────────────────────────────────
def simulate_var_a(df: pd.DataFrame) -> pd.Series:
    """Var A: long SPX when VRP > threshold (raw IV - RV)."""
    signal = (df['vrp_raw'] > VRP_ENTRY_THRESHOLD).astype(float)
    signal = signal.shift(1)  # trade next day
    return signal * df['spx_ret']


def simulate_var_b(df: pd.DataFrame) -> pd.Series:
    """Var B: long SPX when EMA-forecast VRP > threshold."""
    signal = (df['vrp_ema'] > VRP_ENTRY_THRESHOLD).astype(float)
    signal = signal.shift(1)
    return signal * df['spx_ret']


def simulate_var_c(df: pd.DataFrame) -> pd.Series:
    """Var C: VRP + term-structure slope filter."""
    in_position = False
    positions = []
    for i, row in df.iterrows():
        if not in_position and row['vrp_ts_combined'] > VRP_ENTRY_THRESHOLD:
            in_position = True
        elif in_position and row['vrp_ema'] < VRP_EXIT_THRESHOLD:
            in_position = False
        positions.append(1.0 if in_position else 0.0)
    pos_series = pd.Series(positions, index=df.index).shift(1)
    return pos_series * df['spx_ret']


def simulate_var_d_xgboost(train_df: pd.DataFrame, test_df: pd.DataFrame) -> pd.Series:
    """Var D: XGBoost classifier on IV surface features to predict SPX weekly return sign."""
    try:
        from xgboost import XGBClassifier
    except ImportError:
        print("XGBoost not available; skipping Var D")
        return pd.Series(0.0, index=test_df.index)

    feature_cols = ['vix_zscore', 'rv20_zscore', 'ts_zscore', 'vrp_zscore',
                    'vix_mom5', 'vix_mom21']

    # Weekly forward return as target
    train_df = train_df.copy()
    train_df['fwd5'] = train_df['spx_ret'].shift(-5).rolling(5).sum()
    train_df['target'] = (train_df['fwd5'] > 0).astype(int)
    train_df = train_df.dropna()

    X_train = train_df[feature_cols]
    y_train = train_df['target']

    clf = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8,
                        use_label_encoder=False, eval_metric='logloss',
                        random_state=42)
    clf.fit(X_train, y_train)

    X_test = test_df[feature_cols]
    proba = clf.predict_proba(X_test)[:, 1]
    signal = pd.Series((proba > 0.55).astype(float), index=test_df.index)
    signal = signal.shift(1)
    return signal * test_df['spx_ret']


# ── Performance metrics ────────────────────────────────────────────────────────
def performance_metrics(returns: pd.Series, label: str) -> dict:
    """Compute Sharpe, MaxDD, CAGR, annual returns."""
    daily = returns.dropna()
    if len(daily) == 0:
        return {}

    ann_ret  = daily.mean() * 252
    ann_vol  = daily.std()  * np.sqrt(252)
    sharpe   = ann_ret / ann_vol if ann_vol > 0 else 0.0

    cum      = (1 + daily).cumprod()
    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    max_dd   = drawdown.min()

    cagr = cum.iloc[-1] ** (252 / len(daily)) - 1 if len(daily) > 0 else 0.0

    # Annual breakdown
    annual = daily.groupby(daily.index.year).apply(lambda x: (1 + x).prod() - 1)
    neg_years = (annual < 0).sum()

    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  Sharpe:      {sharpe:.3f}")
    print(f"  CAGR:        {cagr*100:.1f}%")
    print(f"  MaxDD:       {max_dd*100:.1f}%")
    print(f"  Ann Vol:     {ann_vol*100:.1f}%")
    print(f"  Neg Years:   {neg_years}")
    print(f"  Annual returns:")
    for yr, r in annual.items():
        print(f"    {yr}: {r*100:+.1f}%")

    return {'sharpe': sharpe, 'cagr': cagr, 'max_dd': max_dd, 'neg_years': int(neg_years)}


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("H448 — Diffusion IV Surface VRP Signal")
    print(f"IS:  {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print("Loading data...")

    full_start = '2017-01-01'  # need extra history for EMA warmup
    spx   = load_spx_data(full_start, OOS_END)
    vix   = load_vix_data(full_start, OOS_END)
    vix9d, vix3m = load_vix9d_vix3m(full_start, OOS_END)

    print("Building signals...")
    df = build_signals(spx, vix, vix9d, vix3m)

    is_df  = df.loc[IS_START:IS_END]
    oos_df = df.loc[OOS_START:OOS_END]

    results = {}

    # Baseline: buy-and-hold SPX
    for label, subset in [('IS', is_df), ('OOS', oos_df)]:
        bh = subset['spx_ret']
        performance_metrics(bh, f"SPX Buy & Hold [{label}]")

    # Var A: raw VRP
    for label, subset in [('IS', is_df), ('OOS', oos_df)]:
        ret = simulate_var_a(subset)
        results[f'VarA_{label}'] = performance_metrics(ret, f"Var A — Raw VRP [{label}]")

    # Var B: EMA-forecast VRP
    for label, subset in [('IS', is_df), ('OOS', oos_df)]:
        ret = simulate_var_b(subset)
        results[f'VarB_{label}'] = performance_metrics(ret, f"Var B — EMA VRP [{label}]")

    # Var C: VRP + term-structure filter
    for label, subset in [('IS', is_df), ('OOS', oos_df)]:
        ret = simulate_var_c(subset)
        results[f'VarC_{label}'] = performance_metrics(ret, f"Var C — VRP + TS Slope [{label}]")

    # Var D: XGBoost surface classifier
    ret_d = simulate_var_d_xgboost(is_df, oos_df)
    results['VarD_OOS'] = performance_metrics(ret_d, "Var D — XGBoost Surface Classifier [OOS]")

    # Gate check
    print("\n" + "="*55)
    print("  GATE CHECK (OOS Sharpe >= 1.0, MaxDD <= 25%)")
    print("="*55)
    for k, v in results.items():
        if 'OOS' in k and v:
            passed = (v.get('sharpe', 0) >= 1.0 and abs(v.get('max_dd', -1)) <= 0.25)
            print(f"  {k}: Sharpe={v.get('sharpe',0):.3f}, MaxDD={v.get('max_dd',0)*100:.1f}% → {'PASS' if passed else 'FAIL'}")


if __name__ == '__main__':
    main()
