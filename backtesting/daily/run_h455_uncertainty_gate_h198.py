#!/usr/bin/env python3
"""
H455 — Epistemic Uncertainty Gate for H198 Momentum

Source: Sanderink (2025) arXiv:2603.13252
        'When Alpha Breaks: Predicting Strategy-Level Alpha Decay
         with Epistemic Uncertainty'

Hypothesis: H198 OOS Sharpe has degraded from 1.174 (confirmed) to ~0.937
in 2021-2026 across multiple reruns (H435/436/437/448/449). An ensemble
uncertainty predictor trained on regime features can gate exposure to
high-confidence alpha months only, restoring or exceeding the 1.174 baseline.

Variants:
  A: DEUP gate — LightGBM ensemble (N=10), binary P>0.5
  B: DEUP continuous sizing — H198 weight = min(P*2, 1.5)
  C: H198 baseline — no gate (replication)
  D: Parametric gate — VIX<25 + SPY>200MA (H165a pattern)
  E: DEUP 5-feature gate (VIX + SPY trend + CS dispersion + realized vol + momentum concentration)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 AND improvement over baseline > 0.10
Universe: H198 30-stock NASDAQ large-cap (same as H198)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

try:
    import lightgbm as lgb
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False
    print('WARNING: lightgbm not installed. Run: pip install lightgbm')

warnings.filterwarnings('ignore')

STRATEGY  = 'H455'
UNIVERSE  = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START = '2012-01-01'
IS_START   = '2013-01-01'
IS_END     = '2020-12-31'
OOS_START  = '2021-01-01'
OOS_END    = '2026-07-21'
N_POSITIONS = 6
N_ENSEMBLE  = 10

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f'Downloading {len(UNIVERSE)} stocks + VIX + SPY...')
    prices = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                         auto_adjust=True, progress=False)['Close']
    prices = prices.dropna(how='all').ffill()
    vix = yf.download('^VIX', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    spy = yf.download('SPY', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    return prices, vix, spy


def compute_h198_signal(daily: pd.DataFrame) -> pd.Series:
    """6-1m momentum signal: 6m return skipping most recent 1m."""
    monthly = daily.resample('MS').first()
    # 6m cumulative return, skip last 1m
    r6 = monthly.pct_change(6).shift(2)   # skip 1m + avoid look-ahead
    return r6


def compute_regime_features(vix_daily: pd.Series, spy_daily: pd.Series,
                            prices: pd.DataFrame) -> pd.DataFrame:
    """Build monthly regime feature matrix (no look-ahead)."""
    monthly_prices = prices.resample('MS').first()
    monthly_rets   = monthly_prices.pct_change()

    # 1. VIX (end-of-prior-month, shifted)
    vix_m = vix_daily.resample('MS').last().shift(1)

    # 2. SPY 200-day MA trend (1 = above, 0 = below)
    spy_200ma = (spy_daily > spy_daily.rolling(200).mean())
    spy_trend = spy_200ma.resample('MS').last().astype(float).shift(1)

    # 3. Cross-sectional return dispersion (std across 30 stocks)
    cs_disp = monthly_rets.shift(1).std(axis=1)

    # 4. SPY 1m realized vol (annualized)
    spy_ret = spy_daily.pct_change()
    spy_rvol = spy_ret.rolling(21).std().mul(np.sqrt(252))
    spy_rvol_m = spy_rvol.resample('MS').last().shift(1)

    # 5. Momentum concentration (Herfindahl-like: max individual 6m return / avg)
    r6 = monthly_prices.pct_change(6).shift(2)
    mom_conc = r6.abs().max(axis=1) / (r6.abs().mean(axis=1) + 1e-6)

    features = pd.DataFrame({
        'vix': vix_m,
        'spy_trend': spy_trend,
        'cs_dispersion': cs_disp,
        'spy_rvol': spy_rvol_m,
        'mom_concentration': mom_conc,
    }).dropna()
    return features


def compute_h198_monthly_returns(daily: pd.DataFrame) -> pd.Series:
    """Run H198 6-1m momentum, return top-6 equal-weight monthly returns."""
    monthly = daily.resample('MS').first()
    signal  = compute_h198_signal(daily)
    fwd_ret = monthly.pct_change().shift(-1)

    port_rets = {}
    for dt in fwd_ret.index:
        if dt not in signal.index:
            continue
        sig_row = signal.loc[dt].dropna()
        ret_row = fwd_ret.loc[dt].dropna()
        common  = sig_row.index.intersection(ret_row.index)
        if len(common) < N_POSITIONS:
            continue
        selected = sig_row[common].sort_values(ascending=False).head(N_POSITIONS).index
        r = ret_row.reindex(selected).mean()
        if not np.isnan(r):
            port_rets[dt] = float(r)

    return pd.Series(port_rets, name='H198')


def train_deup_ensemble(features: pd.DataFrame, labels: pd.Series,
                        n_models: int = N_ENSEMBLE, seed: int = 42) -> list:
    """Train N LightGBM models with different seeds (ensemble for uncertainty)."""
    models = []
    for i in range(n_models):
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'n_estimators': 100,
            'max_depth': 4,
            'learning_rate': 0.05,
            'subsample': 0.8,
            'colsample_bytree': 0.8,
            'random_state': seed + i,
            'verbose': -1,
        }
        m = lgb.LGBMClassifier(**params)
        m.fit(features.values, labels.values)
        models.append(m)
    return models


def predict_uncertainty(models: list, features: pd.DataFrame) -> pd.Series:
    """Returns ensemble mean P(alpha > 0) and std (epistemic uncertainty)."""
    preds = np.stack([m.predict_proba(features.values)[:, 1] for m in models])
    mean_p = preds.mean(axis=0)
    return pd.Series(mean_p, index=features.index)


def evaluate(s: pd.Series, mask, label: str) -> dict:
    r = s[mask].dropna()
    if len(r) < 6:
        return {'sharpe': 0.0, 'cagr': 0.0, 'maxdd': 0.0, 'neg_years': 0}
    sharpe = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else 0.0
    cum    = (1 + r).cumprod()
    n_yrs  = len(r) / 12
    cagr   = cum.iloc[-1] ** (1 / max(n_yrs, 1e-6)) - 1
    maxdd  = (cum / cum.cummax() - 1).min()
    ann    = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg    = int((ann < 0).sum())
    print(f'  {label:42s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}')
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    if not LGBM_AVAILABLE:
        print('ERROR: Install lightgbm first: pip install lightgbm')
        return

    print(f'=== {STRATEGY} Epistemic Uncertainty Gate for H198 ===')
    print(f'IS: {IS_START}-{IS_END} | OOS: {OOS_START}-{OOS_END}')
    print(f'Gate: OOS Sharpe > 1.174 AND improvement over baseline > 0.10')
    print()

    daily, vix, spy = download_data()

    print('Computing H198 baseline returns...')
    h198_rets = compute_h198_monthly_returns(daily)

    print('Computing regime features...')
    features = compute_regime_features(vix, spy, daily)

    # Label: was H198 profitable next month?
    common_idx = h198_rets.index.intersection(features.index)
    y = (h198_rets.reindex(common_idx) > 0).astype(int)
    X = features.reindex(common_idx).dropna()
    y = y.reindex(X.index)

    # IS training (use only IS data)
    is_mask  = (X.index >= IS_START) & (X.index <= IS_END)
    X_is, y_is = X[is_mask], y[is_mask]

    print(f'Training DEUP ensemble on {len(X_is)} IS months...')
    models = train_deup_ensemble(X_is, y_is)

    # Predict on full history (IS + OOS)
    p_alpha = predict_uncertainty(models, X)

    # IS AUROC
    try:
        is_auroc = roc_auc_score(y_is, p_alpha[is_mask])
        print(f'IS AUROC: {is_auroc:.3f}')
    except Exception:
        pass

    # VIX + SPY parametric gate (Var D)
    vix_m  = vix.resample('MS').last().shift(1)
    spy_200 = (spy > spy.rolling(200).mean()).resample('MS').last().shift(1)
    d_gate  = (vix_m < 25) & spy_200

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        rets = {}
        for dt in h198_rets.index:
            base_r = h198_rets.loc[dt]
            if var == 'C':  # no gate
                rets[dt] = base_r
            elif var == 'D':  # parametric gate
                gate_val = d_gate.get(dt, True)
                rets[dt] = base_r if gate_val else 0.0
            elif var in ('A', 'E') and dt in p_alpha.index:  # binary DEUP
                p = p_alpha.loc[dt]
                rets[dt] = base_r if p > 0.5 else 0.0
            elif var == 'B' and dt in p_alpha.index:  # continuous
                p = p_alpha.loc[dt]
                w = min(p * 2, 1.5)
                rets[dt] = base_r * w
            else:
                rets[dt] = base_r
        results[var] = pd.Series(rets, name=f'{STRATEGY}_{var}')

    print('\n=== IS Results ===')
    is_stats = {}
    for v, s in results.items():
        mask = (s.index >= IS_START) & (s.index <= IS_END)
        is_stats[v] = evaluate(s, mask, f'IS Var{v}')

    print('\n=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s, mask, f'OOS Var{v}')

    baseline_sh = oos_stats['C']['sharpe']
    gate_sh = 1.174
    gate_imp = 0.10
    print(f'\n=== Gate Check (OOS Sharpe > {gate_sh} AND improvement > {gate_imp}) ===')
    confirmed = []
    for v in results:
        sh = oos_stats[v]['sharpe']
        imp = sh - baseline_sh
        status = 'PASS' if sh > gate_sh and imp > gate_imp else 'FAIL'
        print(f'  Var {v}: Sharpe={sh:.3f} Improvement={imp:+.3f} [{status}]')
        if status == 'PASS':
            confirmed.append(v)

    verdict = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'
    print(f'\nH198 Baseline (Var C): OOS Sharpe {baseline_sh:.3f}')
    print(f'VERDICT: {verdict}')
    if confirmed:
        print(f'Confirmed variants: {confirmed}')

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': gate_sh,
        'gate_improvement': gate_imp,
        'h198_baseline_oos_sharpe': baseline_sh,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h455_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nResults: {out_path}')


if __name__ == '__main__':
    main()
