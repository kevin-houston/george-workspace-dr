#!/usr/bin/env python3
"""
H429 — Wasserstein-Tracked Rolling HMM Regime Detector (H251 upgrade)
Source: arXiv:2603.04441 (Boukardagha 2026, Columbia)
Gate: OOS Sharpe > 0.941 (H251) AND no single OOS state > 80% of months (degeneracy check)
Universe: SPY / TLT / GLD
IS: 2004-01-01 – 2017-12-31 | OOS: 2018-01-01 – 2026-07-01

Key improvement over H251:
  1. Wasserstein-distance state matching: when rolling/retraining, align state labels
     between old and new model using min-cost Hungarian assignment on 2-Wasserstein
     distance between 1D Gaussian components (SPY return channel). Closed form:
     W2(N(mu1,s1), N(mu2,s2)) = sqrt((mu1-mu2)^2 + (s1-s2)^2)
  2. Rolling window retraining (Var C/D/F) — model stays fresh vs H251 IS-frozen model
  3. Adaptive n_components via BIC (Var E)
  4. Causal OOS prediction: Viterbi over accumulated path (no look-ahead)
"""

import numpy as np
import pandas as pd
import yfinance as yf
import json, warnings
from hmmlearn import hmm
from scipy.optimize import linear_sum_assignment

warnings.filterwarnings('ignore')

TICKERS      = ['SPY', 'TLT', 'GLD']
IS_START     = '2003-01-01'   # extra lead for features
IS_CUTOFF    = '2017-12-31'
OOS_START    = '2018-01-01'
OOS_END      = '2026-07-01'
TC           = 0.001   # 10 bp per rebalance leg

ALLOC = {
    'bull':    [0.80, 0.10, 0.10],
    'neutral': [0.50, 0.30, 0.20],
    'bear':    [0.20, 0.50, 0.30],
}

# ── helpers ──────────────────────────────────────────────────────────────────

def w2_1d(mu1, s1, mu2, s2):
    """2-Wasserstein distance between N(mu1,s1^2) and N(mu2,s2^2)."""
    return np.sqrt((mu1 - mu2) ** 2 + (s1 - s2) ** 2)


def wasserstein_match(old_model, new_model):
    """
    Hungarian assignment minimising total W2 distance between state Gaussians.
    Returns permutation p such that new_model.state[i] -> old_label[p[i]].
    Uses only the first feature channel (SPY log-return, index 0).
    """
    n = old_model.n_components
    C = np.zeros((n, n))
    for i in range(n):
        mu_old = old_model.means_[i, 0]
        s_old  = np.sqrt(old_model.covars_[i, 0, 0])
        for j in range(n):
            mu_new = new_model.means_[j, 0]
            s_new  = np.sqrt(new_model.covars_[j, 0, 0])
            C[i, j] = w2_1d(mu_old, s_old, mu_new, s_new)
    _, col_ind = linear_sum_assignment(C)
    return col_ind   # new state j → old label col_ind[j]


def label_by_spy_ret(model):
    """
    Assign semantic labels by SPY log-return mean (feature index 0).
    Returns list: index of bull / neutral (if 3-state) / bear state.
    """
    mu = model.means_[:, 0]
    order = np.argsort(mu)[::-1]   # highest SPY return first
    return order


def state_to_alloc(state_rank, n_states):
    """state_rank: position in sorted order (0 = most bullish)."""
    if n_states == 2:
        return ALLOC['bull'] if state_rank == 0 else ALLOC['bear']
    else:
        if state_rank == 0:
            return ALLOC['bull']
        elif state_rank == n_states - 1:
            return ALLOC['bear']
        else:
            return ALLOC['neutral']


def fit_hmm(X, n_components, seeds=5):
    """Fit GaussianHMM; return best model by log-likelihood over seeds."""
    best, best_ll = None, -np.inf
    for rs in range(seeds):
        try:
            m = hmm.GaussianHMM(
                n_components=n_components,
                covariance_type='full',
                n_iter=300,
                random_state=rs * 7,
            )
            m.fit(X)
            ll = m.score(X)
            if ll > best_ll:
                best_ll, best = ll, m
        except Exception:
            pass
    return best


def bic_score(model, X):
    n, d = X.shape
    k = model.n_components
    # parameters: transition (k^2-k), start (k-1), means (k*d), covars (k*d^2)
    n_params = (k * k - k) + (k - 1) + k * d + k * d * d
    return -2 * model.score(X) * n + n_params * np.log(n)


def build_features(prices_daily):
    """
    Month-end feature matrix: for each asset: log_return, vol_21d, cum_ret_21d.
    Returns (monthly DataFrame, feature array).
    """
    feat = {}
    for t in TICKERS:
        p = prices_daily[t]
        lr = np.log(p / p.shift(1))
        v21 = lr.rolling(21).std() * np.sqrt(252)
        c21 = p.pct_change(21)
        feat[f'{t}_lr']  = lr
        feat[f'{t}_v21'] = v21
        feat[f'{t}_c21'] = c21
    df = pd.DataFrame(feat, index=prices_daily.index)
    monthly = df.resample('ME').last().dropna()
    return monthly


def causal_predict(model, X_arr):
    """
    For each time t, predict state using Viterbi over X_arr[:t+1].
    Returns array of state indices (causal, no look-ahead).
    """
    states = []
    for t in range(len(X_arr)):
        seg = X_arr[:t+1]
        try:
            s = model.predict(seg)[-1]
        except Exception:
            s = 0
        states.append(s)
    return np.array(states)


def run_backtest(monthly_feat, monthly_ret, variant, n_comp_fixed=3,
                 roll_months=None, bic_select=False):
    """
    monthly_feat : DataFrame of features (full date range)
    monthly_ret  : DataFrame of monthly returns (full date range)
    variant      : label string
    n_comp_fixed : number of HMM states (ignored if bic_select=True)
    roll_months  : retrain every roll_months months using last LOOKBACK data
                   None = IS-only train (H251 style)
    bic_select   : if True, select n_components in {2,3} by BIC each training step

    Returns dict of results.
    """
    LOOKBACK = 60   # months for rolling window (5 years)
    RETRAIN_EVERY = 6   # retrain cadence for rolling

    is_feat = monthly_feat.loc[:IS_CUTOFF]
    oos_feat = monthly_feat.loc[OOS_START:OOS_END]
    oos_ret  = monthly_ret.loc[OOS_START:OOS_END]

    is_X  = is_feat.values.astype(float)
    oos_X = oos_feat.values.astype(float)
    oos_dates = oos_feat.index

    if roll_months is None:
        # IS-only training — fit once, predict OOS causally
        if bic_select:
            models, scores = [], []
            for nc in [2, 3]:
                m = fit_hmm(is_X, nc)
                if m is not None:
                    models.append(m)
                    scores.append(bic_score(m, is_X))
            model = models[np.argmin(scores)]
        else:
            model = fit_hmm(is_X, n_comp_fixed)

        if model is None:
            return None

        bull_order = label_by_spy_ret(model)
        rank_of_state = np.empty(model.n_components, dtype=int)
        for rank, state in enumerate(bull_order):
            rank_of_state[state] = rank

        raw_states = causal_predict(model, oos_X)
        state_ranks = rank_of_state[raw_states]
    else:
        # Rolling window — retrain periodically, Wasserstein state matching
        full_feat = monthly_feat.loc[:OOS_END]
        all_X     = full_feat.values.astype(float)
        all_dates = full_feat.index

        oos_idx_start = all_dates.get_loc(oos_dates[0])

        state_ranks = []
        current_model = None
        bull_order = None
        rank_of_state = None

        for t_global in range(oos_idx_start, len(all_dates)):
            t_oos = t_global - oos_idx_start  # position within OOS

            # Retrain at start and every RETRAIN_EVERY months
            if t_oos % RETRAIN_EVERY == 0 or current_model is None:
                train_end = t_global   # up to but not including current month
                train_start = max(0, train_end - roll_months)
                X_train = all_X[train_start:train_end]
                if len(X_train) < 24:
                    state_ranks.append(0)
                    continue

                if bic_select:
                    candidates, bics = [], []
                    for nc in [2, 3]:
                        m = fit_hmm(X_train, nc)
                        if m is not None:
                            candidates.append(m)
                            bics.append(bic_score(m, X_train))
                    new_model = candidates[np.argmin(bics)] if candidates else None
                else:
                    new_model = fit_hmm(X_train, n_comp_fixed)

                if new_model is None:
                    state_ranks.append(0 if not state_ranks else state_ranks[-1])
                    continue

                if current_model is None or current_model.n_components != new_model.n_components:
                    # First fit or n_components changed: label by SPY return
                    bull_order = label_by_spy_ret(new_model)
                    rank_of_state = np.empty(new_model.n_components, dtype=int)
                    for rank, state in enumerate(bull_order):
                        rank_of_state[state] = rank
                else:
                    # Wasserstein state matching to preserve label continuity
                    perm = wasserstein_match(current_model, new_model)
                    # perm[j] = old_label for new state j
                    # We know old_state's rank, so new state j → old_label perm[j]
                    # rank_of_state[old_state] was set; new state j has same rank
                    new_rank_of_state = np.empty(new_model.n_components, dtype=int)
                    for j in range(new_model.n_components):
                        old_state = perm[j]
                        new_rank_of_state[j] = rank_of_state[old_state]
                    rank_of_state = new_rank_of_state

                current_model = new_model

            # Predict current month's state using data seen so far
            X_seen = all_X[max(0, t_global - roll_months): t_global + 1]
            try:
                raw_state = current_model.predict(X_seen)[-1]
                rank = rank_of_state[raw_state]
            except Exception:
                rank = 0
            state_ranks.append(rank)

        state_ranks = np.array(state_ranks)

    # Compute OOS portfolio returns
    n_states = model.n_components if roll_months is None else current_model.n_components
    T = len(oos_dates)
    port_rets = []
    weights_prev = np.array(ALLOC['bull'])   # start bull

    for t in range(T):
        rank = state_ranks[t]
        w_new = np.array(state_to_alloc(rank, n_states if roll_months is None else current_model.n_components))

        # Transaction cost (apply to prior month's return, then rebalance)
        monthly_asset_rets = oos_ret.iloc[t].values
        gross = np.dot(weights_prev, monthly_asset_rets)
        tc = np.sum(np.abs(w_new - weights_prev)) * TC
        port_rets.append(gross - tc)
        weights_prev = w_new

    port_rets = np.array(port_rets)
    port_series = pd.Series(port_rets, index=oos_dates[:T])

    sharpe = port_series.mean() / port_series.std() * np.sqrt(12) if port_series.std() > 0 else 0
    cum = (1 + port_series).cumprod()
    maxdd = (cum / cum.cummax() - 1).min()
    cagr = cum.iloc[-1] ** (12 / len(port_series)) - 1

    state_frac = {int(r): float((state_ranks == r).mean()) for r in np.unique(state_ranks)}
    max_frac = max(state_frac.values())

    return {
        'variant': variant,
        'sharpe': round(float(sharpe), 3),
        'maxdd': round(float(maxdd), 3),
        'cagr': round(float(cagr * 100), 1),
        'n_months': int(T),
        'state_fracs': state_frac,
        'max_state_frac': round(max_frac, 3),
        'degenerate': bool(max_frac > 0.80),
        'pass_sharpe': bool(sharpe > 0.941),
        'pass_degen': bool(max_frac <= 0.80),
        'gate_pass': bool(sharpe > 0.941 and max_frac <= 0.80),
    }


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("H429 — Wasserstein-Tracked Rolling HMM")
    print("Downloading price data…")

    raw = yf.download(TICKERS, start='2003-01-01', end='2026-07-15',
                      auto_adjust=True, progress=False)['Close']
    raw.columns = TICKERS

    daily_ret = raw.pct_change()
    monthly_ret = (1 + daily_ret).resample('ME').prod() - 1

    monthly_feat = build_features(raw)

    # Align indices
    common = monthly_feat.index.intersection(monthly_ret.index)
    monthly_feat = monthly_feat.loc[common]
    monthly_ret  = monthly_ret.loc[common]

    variants = [
        # (label, n_comp, roll_months, bic_select)
        ('A: n=3, IS-only',           3, None, False),
        ('B: n=2, IS-only',           2, None, False),
        ('C: n=3, roll-5Y',           3, 60,   False),
        ('D: n=2, roll-5Y',           2, 60,   False),
        ('E: n=auto-BIC, IS-only',    3, None, True),
        ('F: n=3, roll-3Y',           3, 36,   False),
    ]

    results = []
    for label, nc, roll, bic in variants:
        print(f"  Running {label}…")
        try:
            r = run_backtest(monthly_feat, monthly_ret,
                             variant=label,
                             n_comp_fixed=nc,
                             roll_months=roll,
                             bic_select=bic)
            if r:
                results.append(r)
                degen_flag = "⚠️ DEGENERATE" if r['degenerate'] else "✓"
                gate_flag  = "✓ GATE" if r['gate_pass'] else "✗"
                print(f"    Sharpe={r['sharpe']:.3f}  MaxDD={r['maxdd']:.1%}  "
                      f"CAGR={r['cagr']:.1f}%  MaxStateFrac={r['max_state_frac']:.0%}  "
                      f"{degen_flag}  {gate_flag}")
        except Exception as e:
            print(f"    ERROR: {e}")

    # ── results table ───────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"{'Variant':<30} {'Sharpe':>7} {'MaxDD':>7} {'CAGR':>7} {'MaxFrac':>8} {'Pass?':>6}")
    print("-" * 80)
    for r in results:
        tag = "✓" if r['gate_pass'] else "✗"
        dg  = " ⚠degen" if r['degenerate'] else ""
        print(f"{r['variant']:<30} {r['sharpe']:>7.3f} {r['maxdd']:>7.1%} "
              f"{r['cagr']:>6.1f}% {r['max_state_frac']:>7.0%}  {tag}{dg}")

    # Save
    out = {
        'hypothesis': 'H429',
        'date': '2026-07-22',
        'source': 'arXiv:2603.04441 (Boukardagha 2026)',
        'gate': 'OOS Sharpe > 0.941 AND max_state_frac <= 0.80',
        'results': results,
    }
    with open('/workspace/agent/backtesting/results/h429_results.json', 'w') as f:
        json.dump(out, f, indent=2)
    print("\nSaved → backtesting/results/h429_results.json")
