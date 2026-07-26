#!/usr/bin/env python3
"""
H447 — Wasserstein-Tracked Explainable Regime-Aware Investing
Source: arXiv:2603.04441 (Boukardagha, Columbia, 2026)

Extends H429 to cross-asset MVO allocation (SPY/TLT/GLD/DBC) with:
  - Dynamic BIC model-order selection (K = 2..4)
  - 2-Wasserstein state tracking across re-fits
  - Transaction-cost-aware MVO with L2 turnover penalty

Variants:
  A: 2-state Gaussian + TC-MVO
  B: BIC-selected K + TC-MVO
  C: 2-state + equal-weight (ablation)
  D: BIC-selected K + equal-weight (ablation)

IS:  2005-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-07-01

Gate: OOS Sharpe > 1.0 AND MaxDD > -20%
Baseline: EW-4 SPY/TLT/GLD/DBC static allocation
"""

import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from hmmlearn.hmm import GaussianHMM
from scipy.optimize import minimize
from itertools import permutations

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TICKERS      = ['SPY', 'TLT', 'GLD', 'DBC']
START        = '2004-01-01'
IS_END       = '2017-12-31'
OOS_START    = '2018-01-01'
ROLL_YEARS   = 3          # rolling re-fit window
TC_LAMBDA    = 0.001      # L2 turnover penalty coefficient
MIN_WEIGHT   = 0.05       # minimum per-asset weight
MAX_WEIGHT   = 0.60       # maximum per-asset weight
N_FITS       = 3          # HMM re-fits per window for robustness
RANDOM_SEED  = 42
REFIT_FREQ   = 21         # re-fit HMM every N trading days (monthly)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_data(tickers, start):
    raw = yf.download(tickers, start=start, auto_adjust=True, progress=False)['Close']
    raw = raw.dropna()
    returns = raw.pct_change().dropna()
    return raw, returns


# ---------------------------------------------------------------------------
# HMM with BIC model order selection
# ---------------------------------------------------------------------------
def fit_hmm_best_k(returns_window, k_range=(2, 4), n_fits=N_FITS):
    """
    Fit GaussianHMM for K in k_range, select by BIC.
    Returns (best_model, best_k, bic_dict).
    """
    X = returns_window.values
    best_bic = np.inf
    best_model = None
    best_k = k_range[0]
    bic_dict = {}

    for k in range(k_range[0], k_range[1] + 1):
        bic_k = np.inf
        model_k = None
        for seed in range(n_fits):
            try:
                m = GaussianHMM(n_components=k, covariance_type='full',
                                n_iter=200, random_state=seed + RANDOM_SEED)
                m.fit(X)
                n_params = k * (k - 1) + k * X.shape[1] + k * X.shape[1] * (X.shape[1] + 1) / 2
                bic = -2 * m.score(X) * len(X) + n_params * np.log(len(X))
                if bic < bic_k:
                    bic_k = bic
                    model_k = m
            except Exception:
                continue
        bic_dict[k] = bic_k
        if bic_k < best_bic:
            best_bic = bic_k
            best_model = model_k
            best_k = k

    return best_model, best_k, bic_dict


def fit_hmm_fixed_k(returns_window, k=2, n_fits=N_FITS):
    """Fit GaussianHMM with fixed K, return best over n_fits."""
    X = returns_window.values
    best_ll = -np.inf
    best_model = None
    for seed in range(n_fits):
        try:
            m = GaussianHMM(n_components=k, covariance_type='full',
                            n_iter=200, random_state=seed + RANDOM_SEED)
            m.fit(X)
            ll = m.score(X)
            if ll > best_ll:
                best_ll = ll
                best_model = m
        except Exception:
            continue
    return best_model


# ---------------------------------------------------------------------------
# 2-Wasserstein distance for Gaussian components
# Bures metric: W2^2(N(mu1,S1), N(mu2,S2)) = ||mu1-mu2||^2 + Bures(S1,S2)
# ---------------------------------------------------------------------------
def bures_distance(S1, S2):
    """Bures metric between two PSD matrices."""
    try:
        S1_half = np.linalg.cholesky(S1 + 1e-8 * np.eye(S1.shape[0]))
        M = S1_half @ S2 @ S1_half.T
        eigvals = np.linalg.eigvalsh(M)
        eigvals = np.maximum(eigvals, 0)
        sqrt_M_trace = np.sum(np.sqrt(eigvals))
        return np.trace(S1) + np.trace(S2) - 2 * sqrt_M_trace
    except Exception:
        return np.inf


def wasserstein2_gaussian(mu1, S1, mu2, S2):
    mean_dist = np.sum((mu1 - mu2) ** 2)
    return mean_dist + bures_distance(S1, S2)


def match_states_wasserstein(prev_model, curr_model):
    """
    Use 2-Wasserstein to match states of curr_model to prev_model.
    Returns permutation mapping curr state -> prev state.
    """
    k_prev = prev_model.n_components
    k_curr = curr_model.n_components

    if k_prev != k_curr:
        # Different number of states — use means only for greedy match
        cost = np.zeros((k_curr, k_prev))
        for i in range(k_curr):
            for j in range(k_prev):
                cost[i, j] = np.sum((curr_model.means_[i] - prev_model.means_[j]) ** 2)
        # Greedy minimum cost match
        perm = np.argmin(cost, axis=1)
        return perm

    # Same K: optimal assignment via min-cost permutation
    k = k_prev
    costs = {}
    for perm in permutations(range(k)):
        total = 0.0
        for i, j in enumerate(perm):
            total += wasserstein2_gaussian(
                curr_model.means_[i], curr_model.covars_[i],
                prev_model.means_[j], prev_model.covars_[j]
            )
        costs[perm] = total
    best_perm = min(costs, key=costs.get)
    return list(best_perm)


# ---------------------------------------------------------------------------
# Transaction-cost-aware MVO
# ---------------------------------------------------------------------------
def tc_mvo(mu, Sigma, prev_w, lam=TC_LAMBDA, min_w=MIN_WEIGHT, max_w=MAX_WEIGHT):
    """
    Maximize: mu'w - (1/2) * w'Sigma*w - lambda * ||w - prev_w||^2
    Subject to: sum(w)=1, min_w <= w_i <= max_w
    """
    n = len(mu)
    if prev_w is None:
        prev_w = np.ones(n) / n

    def neg_utility(w):
        ret = mu @ w
        risk = 0.5 * w @ Sigma @ w
        turnover_penalty = lam * np.sum((w - prev_w) ** 2)
        return -(ret - risk - turnover_penalty)

    bounds = [(min_w, max_w)] * n
    constraints = [{'type': 'eq', 'fun': lambda w: np.sum(w) - 1}]
    w0 = prev_w.copy()

    result = minimize(neg_utility, w0, method='SLSQP', bounds=bounds,
                      constraints=constraints,
                      options={'maxiter': 500, 'ftol': 1e-9})
    if result.success:
        return result.x
    else:
        # Fallback: equal weight
        return np.ones(n) / n


# ---------------------------------------------------------------------------
# Rolling regime-aware allocation
# ---------------------------------------------------------------------------
def rolling_regime_allocation(returns, roll_years=ROLL_YEARS, variant='A'):
    """
    variant:
      A: fixed K=2 Gaussian + TC-MVO
      B: BIC K-selection + TC-MVO
      C: fixed K=2 Gaussian + equal-weight per regime
      D: BIC K-selection + equal-weight per regime
    """
    roll_days = int(roll_years * 252)
    dates = returns.index
    n_assets = returns.shape[1]

    weights = pd.DataFrame(index=dates, columns=returns.columns, dtype=float)
    prev_model = None
    prev_w = np.ones(n_assets) / n_assets

    last_refit = roll_days  # force first refit at start
    current_w = prev_w.copy()

    for t in range(roll_days, len(dates)):
        # Re-fit HMM only every REFIT_FREQ days
        if t == roll_days or (t - last_refit) >= REFIT_FREQ:
            window = returns.iloc[t - roll_days:t]

            # Fit HMM
            if variant in ('A', 'C'):
                model = fit_hmm_fixed_k(window, k=2)
            else:  # B, D
                model, k_sel, _ = fit_hmm_best_k(window, k_range=(2, 4))

            if model is None:
                weights.iloc[t] = current_w
                last_refit = t
                continue

            # Match states to previous fit if available
            if prev_model is not None and prev_model.n_components == model.n_components:
                try:
                    perm = match_states_wasserstein(prev_model, model)
                    model.means_ = model.means_[perm]
                    model.covars_ = model.covars_[perm]
                    model.transmat_ = model.transmat_[np.ix_(perm, perm)]
                    model.startprob_ = model.startprob_[perm]
                except Exception:
                    pass

            # Get current regime (filtered, causal — use last day of window)
            try:
                state_seq = model.predict(window.values)
                current_state = state_seq[-1]
            except Exception:
                weights.iloc[t] = current_w
                last_refit = t
                continue

            # Regime-conditional expected return and covariance
            regime_returns = window[state_seq == current_state]
            if len(regime_returns) < 10:
                regime_returns = window

            mu_reg = regime_returns.mean().values * 252
            Sigma_reg = regime_returns.cov().values * 252

            # Allocation
            if variant in ('A', 'B'):
                new_w = tc_mvo(mu_reg, Sigma_reg, current_w)
            else:
                new_w = np.ones(n_assets) / n_assets

            current_w = new_w.copy()
            prev_w = new_w.copy()
            prev_model = model
            last_refit = t

        weights.iloc[t] = current_w

    # Fill early rows
    weights = weights.ffill().bfill()
    weights = weights.div(weights.sum(axis=1), axis=0)
    return weights


# ---------------------------------------------------------------------------
# Backtest engine
# ---------------------------------------------------------------------------
def backtest(returns, weights, label='Strategy'):
    """Compute daily portfolio returns from daily asset returns and weights."""
    # Weights are set at close of day t, so returns are at day t+1
    w_shifted = weights.shift(1).dropna()
    common_idx = returns.index.intersection(w_shifted.index)
    r = returns.loc[common_idx]
    w = w_shifted.loc[common_idx]
    port_ret = (r * w).sum(axis=1)
    return port_ret


def compute_metrics(port_ret, label='Strategy'):
    ann_ret = port_ret.mean() * 252
    ann_vol = port_ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum = (1 + port_ret).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()
    n_years = len(port_ret) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0.0
    print(f"{label:40s}  CAGR={cagr:6.2%}  Sharpe={sharpe:5.3f}  MaxDD={max_dd:6.2%}")
    return {'sharpe': sharpe, 'maxdd': max_dd, 'cagr': cagr}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("H447 — Wasserstein-Tracked Explainable Regime-Aware Investing")
    print("Source: arXiv:2603.04441 | Universe: SPY/TLT/GLD/DBC")
    print("=" * 70)

    _, returns = load_data(TICKERS, START)
    returns.columns = TICKERS

    is_ret  = returns.loc[:IS_END]
    oos_ret = returns.loc[OOS_START:]

    print(f"IS:  {is_ret.index[0].date()} to {is_ret.index[-1].date()} ({len(is_ret)} days)")
    print(f"OOS: {oos_ret.index[0].date()} to {oos_ret.index[-1].date()} ({len(oos_ret)} days)")
    print()

    # Baseline: static EW-4
    ew_oos = oos_ret.mean(axis=1)
    print("--- Baseline ---")
    compute_metrics(ew_oos, 'EW-4 static baseline')

    # SPY B&H
    spy_oos = oos_ret['SPY']
    compute_metrics(spy_oos, 'SPY Buy-and-Hold')
    print()

    results = {}
    for var in ('A', 'B', 'C', 'D'):
        print(f"--- Variant {var} ---")
        all_weights = rolling_regime_allocation(returns, roll_years=ROLL_YEARS, variant=var)
        is_weights  = all_weights.loc[:IS_END]
        oos_weights = all_weights.loc[OOS_START:]
        is_port  = backtest(is_ret,  is_weights,  label=f'H447-{var}-IS')
        oos_port = backtest(oos_ret, oos_weights, label=f'H447-{var}')
        compute_metrics(is_port,  f'H447 Var {var} IS ')
        metrics = compute_metrics(oos_port, f'H447 Var {var} OOS')
        results[var] = metrics

    print()
    print("=" * 70)
    print("GATE: OOS Sharpe > 1.0 AND MaxDD > -20%")
    for var, m in results.items():
        gate = 'PASS' if m['sharpe'] > 1.0 and m['maxdd'] > -0.20 else 'FAIL'
        print(f"  Var {var}: Sharpe={m['sharpe']:.3f}  MaxDD={m['maxdd']:.2%}  -> {gate}")


if __name__ == '__main__':
    main()
