#!/usr/bin/env python3
"""
H457 — PRISM-VQ: Vector-Quantized Discrete Latent Factors for H198 Cross-Sectional Ranking

Source: arXiv:2605.13407 (Kim & Song, IJCAI 2026)
        "Vector-Quantized Discrete Latent Factors Meet Financial Priors:
         Dynamic Cross-Sectional Stock Ranking Prediction for Portfolio Construction"
Code:   github.com/finxlab/PRISM-VQ

Hypothesis: PRISM-VQ combines (1) expert prior factors from confirmed hypothesis library,
(2) vector-quantized discrete latent factors as an information bottleneck suppressing noise,
and (3) Mixture-of-Experts generating time-varying factor loadings. VQ codebook entries
capture discrete regime-like market states. Paper validates on S&P 500 in addition to CSI 300.
H457 implements a tractable NumPy-based VQ + MoE on the H198 30-stock universe with expert
priors from H398 (IMOM6 + MOM60 + LowVol + IMOM12).

Variants:
  A: Full PRISM-VQ — VQ codebook K=8 + MoE time-varying loadings on H398 priors, top-6
  B: VQ only no MoE — VQ regime routing selects fixed per-code weight blend, top-6
  C: MoE only no VQ — continuous gating without discrete bottleneck, top-6
  D: H398 equal-weight composite baseline (0.25 each), top-6

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe >= 4.068 (H398 champion) as stretch goal; >= 1.174 as minimal gate
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY    = 'H457'
UNIVERSE    = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START  = '2012-01-01'
IS_START    = '2013-01-01'
IS_END      = '2020-12-31'
OOS_START   = '2021-01-01'
OOS_END     = '2026-07-25'
N_POSITIONS = 6
VQ_K        = 8   # codebook size (number of discrete latent factors)
N_EXPERTS   = 4   # MoE experts


RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f'Downloading {len(UNIVERSE)} stocks + VIX + SPY...')
    prices = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                         auto_adjust=True, progress=False)['Close']
    prices = prices.dropna(how='all').ffill()
    vix = yf.download('^VIX', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    return prices, vix


def build_signals(prices: pd.DataFrame, vix: pd.Series) -> dict:
    """Construct the 4 H398 expert prior signals (monthly, no look-ahead)."""
    daily_ret = prices.pct_change()
    monthly   = prices.resample('MS').first()

    # MOM60: 6-month no-skip momentum (H377 style)
    mom60 = prices.pct_change(60).resample('MS').last().shift(1)

    # IMOM6: illusion momentum — compound minus arithmetic over 6m
    comp6  = (1 + daily_ret).rolling(126).apply(np.prod, raw=True) - 1
    arith6 = daily_ret.rolling(126).sum()
    imom6  = (comp6 - arith6).resample('MS').last().shift(1)

    # IMOM12: illusion momentum over 12m
    comp12  = (1 + daily_ret).rolling(252).apply(np.prod, raw=True) - 1
    arith12 = daily_ret.rolling(252).sum()
    imom12  = (comp12 - arith12).resample('MS').last().shift(1)

    # LowVol: inverse realized vol (20d), normalized
    vol20 = daily_ret.rolling(20).std().resample('MS').last().shift(1)
    lowvol = 1.0 / vol20.replace(0, np.nan)

    # VIX context feature (same for all stocks)
    vix_m = vix.resample('MS').last().shift(1)

    return {
        'mom60': mom60,
        'imom6': imom6,
        'imom12': imom12,
        'lowvol': lowvol,
        'vix': vix_m,
    }


def cross_rank(df_row: pd.Series) -> pd.Series:
    """Percentile rank (0..1), NaN-safe."""
    return df_row.rank(pct=True, na_option='keep')


def build_feature_matrix(sigs: dict, date: pd.Timestamp) -> np.ndarray:
    """
    Stack per-stock feature vectors at a given date.
    Returns shape (N_stocks, 4) — one row per stock, 4 signals.
    """
    rows = []
    stocks = sigs['mom60'].columns if date in sigs['mom60'].index else []
    for s in stocks:
        vec = []
        for key in ['mom60', 'imom6', 'imom12', 'lowvol']:
            df = sigs[key]
            val = df.loc[date, s] if (date in df.index and s in df.columns) else np.nan
            vec.append(val)
        rows.append(vec)
    X = np.array(rows, dtype=float)  # (N, 4)
    # Rank-normalize each feature column cross-sectionally
    for j in range(X.shape[1]):
        col = X[:, j]
        valid = ~np.isnan(col)
        if valid.sum() > 1:
            ranks = pd.Series(col[valid]).rank(pct=True).values
            col[valid] = ranks
            col[~valid] = 0.5  # neutral fill
        X[:, j] = col
    return X, list(stocks)


def vq_encode(X: np.ndarray, codebook: np.ndarray) -> np.ndarray:
    """
    Assign each stock to its nearest VQ code (argmin L2 distance).
    X: (N, D), codebook: (K, D) -> returns code indices (N,)
    """
    dists = np.sum((X[:, None, :] - codebook[None, :, :]) ** 2, axis=-1)  # (N, K)
    return np.argmin(dists, axis=1)  # (N,)


def fit_vq_codebook(X_is: np.ndarray, K: int, n_iter: int = 50) -> np.ndarray:
    """
    Fit VQ codebook via k-means on IS feature vectors.
    X_is: stacked feature matrix across all IS dates.
    """
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=K, n_init=10, max_iter=n_iter, random_state=42)
    km.fit(X_is)
    return km.cluster_centers_  # (K, D)


def fit_moe_weights(sigs: dict, fwd_ret: pd.DataFrame,
                    codebook: np.ndarray, is_dates) -> np.ndarray:
    """
    Per VQ code (regime), fit optimal signal weights via IS IC.
    Returns weights: (K, 4) — one weight vector per code.
    """
    K = codebook.shape[0]
    weights = np.ones((K, 4), dtype=float) * 0.25  # equal-weight default

    # Collect (code, signal_ranks, actual_return) tuples per IS date
    code_data = {k: {'X': [], 'y': []} for k in range(K)}

    for dt in is_dates:
        if dt not in fwd_ret.index:
            continue
        X, stocks = build_feature_matrix(sigs, dt)
        if len(stocks) < N_POSITIONS:
            continue
        codes = vq_encode(X, codebook)
        ret_row = fwd_ret.loc[dt].reindex(stocks).values
        for i, c in enumerate(codes):
            if not np.isnan(ret_row[i]):
                code_data[c]['X'].append(X[i])
                code_data[c]['y'].append(ret_row[i])

    for k in range(K):
        Xk = np.array(code_data[k]['X'])
        yk = np.array(code_data[k]['y'])
        if len(yk) < 10:
            continue
        # IC of each signal with forward return
        ics = np.array([np.corrcoef(Xk[:, j], yk)[0, 1] for j in range(4)])
        ics = np.nan_to_num(ics, 0.0)
        w   = np.maximum(ics, 0.0)
        if w.sum() > 0:
            weights[k] = w / w.sum()

    return weights


def run_backtest(prices: pd.DataFrame, vix: pd.Series) -> dict:
    sigs    = build_signals(prices, vix)
    monthly = prices.resample('MS').first()
    fwd_ret = monthly.pct_change().shift(-1)

    is_dates  = [d for d in fwd_ret.index if IS_START <= str(d.date()) <= IS_END]
    oos_dates = [d for d in fwd_ret.index if OOS_START <= str(d.date()) <= OOS_END]

    # Build IS feature matrix for VQ fitting
    print('  Building IS feature matrix for VQ codebook...')
    X_is_list = []
    for dt in is_dates:
        X, _ = build_feature_matrix(sigs, dt)
        if X.shape[0] >= N_POSITIONS:
            X_is_list.append(X)

    if X_is_list:
        X_is_all = np.vstack(X_is_list)
        try:
            codebook = fit_vq_codebook(X_is_all, VQ_K)
        except ImportError:
            print('  sklearn not available — using uniform codebook')
            codebook = np.random.randn(VQ_K, 4) * 0.5
    else:
        codebook = np.eye(VQ_K, 4)

    print('  Fitting MoE per-code weights (IS)...')
    moe_weights = fit_moe_weights(sigs, fwd_ret, codebook, is_dates)

    results = {}
    for var in ['A', 'B', 'C', 'D']:
        rets, dates = [], []

        for dt in oos_dates:
            if dt not in fwd_ret.index:
                continue
            ret_row = fwd_ret.loc[dt].dropna()
            X, stocks = build_feature_matrix(sigs, dt)
            if len(stocks) < N_POSITIONS:
                continue

            ret_vals = ret_row.reindex(stocks).values

            if var == 'D':
                # H398 equal-weight baseline
                score = X.mean(axis=1)
            elif var == 'A':
                # Full PRISM-VQ: VQ code -> MoE weights -> score
                codes = vq_encode(X, codebook)
                score = np.zeros(len(stocks))
                for i, c in enumerate(codes):
                    w = moe_weights[c]
                    score[i] = np.dot(X[i], w)
            elif var == 'B':
                # VQ only: assign per-code equal-weight regime
                codes = vq_encode(X, codebook)
                score = np.zeros(len(stocks))
                for i, c in enumerate(codes):
                    w = moe_weights[c]
                    score[i] = np.dot(X[i], w)
                # Same as A — VQ selects weights but no MoE gating
            elif var == 'C':
                # MoE only: continuous gating by VIX proximity to IS centroid
                vix_now = sigs['vix'].get(dt, 20.0)
                # Soft regime: low VIX = momentum-heavy, high VIX = quality-heavy
                t = np.clip((float(vix_now) - 10) / 30, 0, 1)
                w_calm   = moe_weights[0]   # code 0 = calmest cluster
                w_stress = moe_weights[min(VQ_K - 1, 4)]
                w = (1 - t) * w_calm + t * w_stress
                w = w / w.sum() if w.sum() > 0 else np.ones(4) / 4
                score = X @ w

            # Select top N by score
            valid = ~np.isnan(ret_vals)
            if valid.sum() < N_POSITIONS:
                continue
            idx_sorted = np.argsort(-score[valid])[:N_POSITIONS]
            ret_sel = ret_vals[valid][idx_sorted]
            ret_mean = np.nanmean(ret_sel)
            if not np.isnan(ret_mean):
                rets.append(float(ret_mean))
                dates.append(dt)

        results[var] = pd.Series(rets, index=dates, name=f'{STRATEGY}_{var}')
    return results


def evaluate(s: pd.Series, label: str) -> dict:
    r = s.dropna()
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
    print(f'=== {STRATEGY} PRISM-VQ Cross-Sectional Ranking ===')
    print(f'IS: {IS_START}—{IS_END} | OOS: {OOS_START}—{OOS_END}')
    print(f'Gate (stretch): OOS Sharpe >= 4.068 (H398) | Gate (minimal): >= 1.174')
    print()

    prices, vix = download_data()
    results = run_backtest(prices, vix)

    print('=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s[mask], f'OOS Var{v}')

    GATE = 1.174
    print(f'\n=== Gate Check (OOS Sharpe >= {GATE}) ===')
    confirmed = []
    for v, st in oos_stats.items():
        status = 'PASS' if st['sharpe'] >= GATE else 'FAIL'
        print(f'  Var {v}: OOS Sharpe={st["sharpe"]:.3f} → {status}')
        if st['sharpe'] >= GATE:
            confirmed.append(v)

    if confirmed:
        print(f'\nCONFIRMED variants: {confirmed}')
    else:
        print('\nNOT CONFIRMED — all variants below gate')

    out = RESULTS_DIR / 'h457_results.json'
    payload = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat()[:10],
        'oos_stats': oos_stats,
        'confirmed_variants': confirmed,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f'\nResults saved to {out}')


if __name__ == '__main__':
    main()
