#!/usr/bin/env python3
"""
R35: Three-Layer Regime Detection Stack
========================================
Layer 1 (Primary):   Efficient Frontier Clustering  — portfolio-level behavior signal
Layer 2 (Secondary): Wasserstein HMM               — return distribution regime signal
Layer 3 (Tertiary):  Skewness Dispersion            — leading indicator

Based on:
- EF Coefficient Clustering: https://github.com/nolanalexander/efficient-frontier-coefficients
- Wasserstein HMM: arXiv:2603.04441
- Skewness Dispersion: arXiv:2604.07870

Usage:
    PYTHONPATH=/workspace/group/.venv/lib/python3.13/site-packages:/home/node/.local/lib/python3.13/site-packages \
    /usr/local/bin/python3.13 r35_regime_stack.py
"""

import sys
sys.path.insert(0, '/workspace/group/.venv/lib/python3.13/site-packages')
sys.path.insert(0, '/home/node/.local/lib/python3.13/site-packages')

import os
import json
import warnings
import traceback
from datetime import datetime, date
from typing import Dict, Optional, Tuple, List

import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial.distance import cdist
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings('ignore')

print("=" * 60)
print("R35: Three-Layer Regime Detection Stack")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
#  DATA LOADING
# ─────────────────────────────────────────────────────────────

# S&P 500 top-50 tickers (diversified across sectors)
SP500_TOP50 = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'BRK-B', 'LLY', 'AVGO', 'JPM',
    'TSLA', 'UNH', 'V', 'XOM', 'MA', 'JNJ', 'COST', 'PG', 'HD', 'WMT',
    'ABBV', 'CVX', 'MRK', 'NFLX', 'BAC', 'AMD', 'ORCL', 'CRM', 'PEP', 'KO',
    'TMO', 'ACN', 'ADBE', 'WFC', 'MCD', 'LIN', 'TXN', 'QCOM', 'DHR', 'GE',
    'NEE', 'PM', 'IBM', 'CAT', 'SPGI', 'NOW', 'INTU', 'AXP', 'RTX', 'GS',
]


def load_data(start="2015-01-01", end="2026-01-01", cache_path="/tmp/r35_data_cache.pkl"):
    """Load SPY + top-50 stock returns, with local cache."""
    import yfinance as yf
    import pickle

    if os.path.exists(cache_path):
        print(f"Loading cached data from {cache_path} ...")
        with open(cache_path, 'rb') as f:
            return pickle.load(f)

    print(f"Downloading SPY data ({start} to {end}) ...")
    spy_raw = yf.download("SPY", start=start, end=end, auto_adjust=True, progress=False)
    # Handle MultiIndex columns
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_raw.columns = spy_raw.columns.droplevel(1)
    spy_returns = spy_raw['Close'].pct_change().dropna()
    spy_returns.name = 'SPY'
    print(f"  SPY: {len(spy_returns)} trading days")

    print("Downloading top-50 stock data ...")
    tickers_to_try = SP500_TOP50[:]
    downloaded = {}
    for ticker in tickers_to_try:
        try:
            raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)
            if len(raw) > 1000:
                ret = raw['Close'].pct_change().dropna()
                ret.name = ticker
                downloaded[ticker] = ret
        except Exception as e:
            print(f"  Warning: {ticker} failed: {e}")

    print(f"  Downloaded {len(downloaded)} stocks")

    # Align all stock returns to common dates
    stock_df = pd.DataFrame(downloaded)
    stock_df = stock_df.dropna(how='all').ffill().dropna()

    # Align SPY to stock_df dates
    spy_aligned = spy_returns.reindex(stock_df.index).ffill().dropna()
    stock_df = stock_df.reindex(spy_aligned.index)

    result = {
        'spy_returns': spy_aligned,
        'stock_returns': stock_df,
    }

    with open(cache_path, 'wb') as f:
        import pickle
        pickle.dump(result, f)
    print(f"Data cached to {cache_path}")
    return result


# ─────────────────────────────────────────────────────────────
#  LAYER 1: Efficient Frontier Clustering
# ─────────────────────────────────────────────────────────────

def compute_ef_coefs(returns_df: pd.DataFrame) -> Tuple[float, float, float]:
    """
    Compute Efficient Frontier coefficients A, B, C from a window of returns.
    Based on get_ef_coefs() in the EF clustering library.

    The EF in mean-variance space is: sigma^2 = (A*mu^2 - 2*B*mu + C) / (A*C - B^2)
    where A = e'Sigma^{-1}e, B = mu'Sigma^{-1}e, C = mu'Sigma^{-1}mu
    """
    mu = returns_df.mean().values
    Sigma = returns_df.cov().values

    try:
        inv_sigma = np.linalg.pinv(Sigma)
    except Exception:
        return np.nan, np.nan, np.nan

    e = np.ones(len(mu))
    A = float(e @ inv_sigma @ e)
    B = float(mu @ inv_sigma @ e)
    C = float(mu @ inv_sigma @ mu)

    # Derived EF shape parameters (same as library)
    r_mvp   = B / A if A != 0 else np.nan          # Min-var portfolio return
    sigma_mvp = 1.0 / np.sqrt(A) if A > 0 else np.nan  # Min-var portfolio std
    ac_b2 = A * C - B ** 2
    u = np.sqrt(max(ac_b2 / A, 0)) if A > 0 else np.nan   # EF curvature

    return A, B, C, r_mvp, sigma_mvp, u


class EFClusteringLayer:
    """
    Layer 1: Portfolio-level regime detection via EF coefficient clustering.

    Adapted from the nolanalexander/efficient-frontier-coefficients library.
    Uses K-Means on rolling EF coefficients to identify regime clusters,
    then tracks Markov-style state transitions.
    """

    def __init__(self, lookback: int = 63, n_clusters: int = 3):
        self.lookback = lookback        # ~1 quarter
        self.n_clusters = n_clusters
        self.scaler = StandardScaler()
        self.kmeans = None
        self.coef_history: pd.DataFrame = None
        self.cluster_labels: pd.Series = None
        self.cluster_returns: Dict[int, float] = {}
        self.is_fitted = False

    def _compute_rolling_coefs(self, stock_returns: pd.DataFrame) -> pd.DataFrame:
        """Compute EF coefficients on rolling windows."""
        dates = stock_returns.index[self.lookback:]
        rows = []
        for dt in dates:
            window = stock_returns.loc[:dt].iloc[-self.lookback:]
            A, B, C, r_mvp, sigma_mvp, u = compute_ef_coefs(window)
            rows.append({
                'date': dt,
                'A': A, 'B': B, 'C': C,
                'r_mvp': r_mvp, 'sigma_mvp': sigma_mvp, 'u': u,
            })
        df = pd.DataFrame(rows).set_index('date')
        return df.dropna()

    def fit(self, stock_returns: pd.DataFrame, spy_returns: pd.Series):
        """Fit EF clustering on historical stock returns."""
        print("  [Layer 1] Computing rolling EF coefficients ...")
        self.coef_history = self._compute_rolling_coefs(stock_returns)
        print(f"  [Layer 1] Got {len(self.coef_history)} EF coef observations")

        # Use key EF shape parameters for clustering (r_MVP, sigma_MVP, u)
        feature_cols = ['r_mvp', 'sigma_mvp', 'u']
        X = self.coef_history[feature_cols].values
        X_scaled = self.scaler.fit_transform(X)

        print(f"  [Layer 1] Fitting K-Means with {self.n_clusters} clusters ...")
        self.kmeans = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=20)
        raw_labels = self.kmeans.fit_predict(X_scaled)
        self.cluster_labels = pd.Series(raw_labels, index=self.coef_history.index)

        # Assign regime labels based on average SPY return in each cluster
        self.cluster_returns = {}
        for c in range(self.n_clusters):
            mask = self.cluster_labels == c
            cluster_dates = self.cluster_labels[mask].index
            c_spy = spy_returns.reindex(cluster_dates).dropna()
            self.cluster_returns[c] = float(c_spy.mean()) if len(c_spy) > 0 else 0.0

        # Sort clusters: 0 = lowest return (bear), 1 = neutral, 2 = bull
        sorted_clusters = sorted(self.cluster_returns, key=lambda c: self.cluster_returns[c])
        self.cluster_map = {old: new for new, old in enumerate(sorted_clusters)}
        self.cluster_labels = self.cluster_labels.map(self.cluster_map)

        # Re-compute cluster returns after remapping
        for c in range(self.n_clusters):
            mask = self.cluster_labels == c
            cluster_dates = self.cluster_labels[mask].index
            c_spy = spy_returns.reindex(cluster_dates).dropna()
            self.cluster_returns[c] = float(c_spy.mean()) if len(c_spy) > 0 else 0.0

        regime_names = {0: 'bear', 1: 'neutral', 2: 'bull'}
        for c, name in regime_names.items():
            pct = (self.cluster_labels == c).mean() * 100
            avg_ret = self.cluster_returns[c] * 252  # annualized
            print(f"  [Layer 1] Cluster {c} ({name}): {pct:.1f}% of time, "
                  f"ann. avg SPY return: {avg_ret:.1%}")

        self.is_fitted = True

    def predict(self, stock_returns_window: pd.DataFrame) -> Dict:
        """Predict regime for the latest window."""
        if not self.is_fitted:
            return {'signal': 1, 'regime': 'neutral', 'confidence': 0.0}

        A, B, C, r_mvp, sigma_mvp, u = compute_ef_coefs(stock_returns_window)
        if np.isnan(A):
            return {'signal': 1, 'regime': 'neutral', 'confidence': 0.5}

        X = np.array([[r_mvp, sigma_mvp, u]])
        X_scaled = self.scaler.transform(X)
        raw_cluster = int(self.kmeans.predict(X_scaled)[0])
        cluster = self.cluster_map.get(raw_cluster, raw_cluster)

        # Confidence: 1 - (distance to centroid / max distance)
        dists = cdist(X_scaled, self.kmeans.cluster_centers_[raw_cluster:raw_cluster+1])[0][0]
        all_dists = cdist(X_scaled, self.kmeans.cluster_centers_).flatten()
        max_dist = all_dists.max() if all_dists.max() > 0 else 1.0
        confidence = float(1.0 - dists / max_dist)

        regime_names = {0: 'bear', 1: 'neutral', 2: 'bull'}
        signal_map = {0: -1, 1: 0, 2: 1}

        return {
            'signal': signal_map.get(cluster, 0),
            'regime': regime_names.get(cluster, 'neutral'),
            'cluster_id': cluster,
            'confidence': confidence,
            'ef_coefs': {'A': A, 'B': B, 'C': C, 'r_mvp': r_mvp, 'sigma_mvp': sigma_mvp, 'u': u},
        }


# ─────────────────────────────────────────────────────────────
#  LAYER 2: Wasserstein HMM
# ─────────────────────────────────────────────────────────────

def wasserstein_distance_1d(p: np.ndarray, q: np.ndarray) -> float:
    """
    1D Wasserstein distance (Earth Mover's Distance) between two empirical distributions.
    For 1D distributions, W_1 = integral |F_p - F_q|.
    Efficiently computed via sorted order statistics.
    """
    p_sorted = np.sort(p)
    q_sorted = np.sort(q)

    # Interpolate to same grid size
    n = max(len(p_sorted), len(q_sorted))
    p_interp = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(p_sorted)), p_sorted)
    q_interp = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(q_sorted)), q_sorted)

    return float(np.mean(np.abs(p_interp - q_interp)))


class WassersteinHMMLayer:
    """
    Layer 2: Return distribution regime detection using Wasserstein-distance-based HMM.

    Inspired by arXiv:2603.04441. Rather than raw returns, we:
    1. Compute rolling return distributions (60-day windows)
    2. Compute pairwise Wasserstein distances between consecutive distributions
    3. Use hmmlearn GaussianHMM on the Wasserstein distance series to detect regime shifts
    4. Map states to bull/bear based on average SPY return in each state
    """

    def __init__(self, window: int = 60, n_states: int = 2):
        self.window = window
        self.n_states = n_states
        self.hmm = None
        self.state_series: pd.Series = None
        self.state_returns: Dict[int, float] = {}
        self.state_map: Dict[int, int] = {}
        self.w_dist_series: pd.Series = None
        self.is_fitted = False

    def _compute_wasserstein_series(self, spy_returns: pd.Series) -> pd.Series:
        """
        Compute Wasserstein distance between two non-overlapping windows:
        - Previous window: [i-2*window, i-window]
        - Current window:  [i-window, i]
        This cleanly captures distribution shifts over time.
        """
        dists = {}
        dates = spy_returns.index
        for i in range(2 * self.window, len(dates)):
            prev_window = spy_returns.iloc[i - 2 * self.window: i - self.window].values
            curr_window = spy_returns.iloc[i - self.window: i].values
            w_dist = wasserstein_distance_1d(prev_window, curr_window)
            dists[dates[i]] = w_dist
        return pd.Series(dists)

    def fit(self, spy_returns: pd.Series):
        """Fit Wasserstein HMM on SPY returns."""
        from hmmlearn import hmm

        print("  [Layer 2] Computing rolling Wasserstein distances ...")
        self.w_dist_series = self._compute_wasserstein_series(spy_returns)
        print(f"  [Layer 2] Got {len(self.w_dist_series)} Wasserstein distance observations")

        # Build multi-feature set for HMM:
        # - Wasserstein distance (distribution shift)
        # - Rolling return (trend)
        # - Rolling volatility (risk)
        # - Rolling skewness (tail risk)
        # - Realized drawdown (current market stress)
        roll_ret_21 = spy_returns.rolling(21).mean().reindex(self.w_dist_series.index)
        roll_vol_21 = spy_returns.rolling(21).std().reindex(self.w_dist_series.index)
        roll_skew_42 = spy_returns.rolling(42).skew().reindex(self.w_dist_series.index)
        # Drawdown from 252-day high
        price_idx = (1 + spy_returns).cumprod()
        rolling_max = price_idx.rolling(252, min_periods=20).max()
        drawdown = (price_idx / rolling_max - 1).reindex(self.w_dist_series.index)

        feature_df = pd.DataFrame({
            'w_dist': self.w_dist_series,
            'roll_ret': roll_ret_21,
            'roll_vol': roll_vol_21,
            'roll_skew': roll_skew_42,
            'drawdown': drawdown,
        }).dropna()

        # Standardize features
        scaler = StandardScaler()
        X = scaler.fit_transform(feature_df.values)
        self._feature_scaler = scaler
        self._feature_cols = list(feature_df.columns)

        print(f"  [Layer 2] Fitting GaussianHMM with {self.n_states} states on {len(X)} obs ...")
        self.hmm = hmm.GaussianHMM(
            n_components=self.n_states,
            covariance_type='full',
            n_iter=500,
            random_state=42,
            tol=1e-5,
        )
        self.hmm.fit(X)

        raw_states = self.hmm.predict(X)
        self.state_series = pd.Series(raw_states, index=feature_df.index)
        self._spy_returns_ref = spy_returns  # store for drawdown calculation in predict

        # Map states to bull/bear based on average SPY return
        self.state_returns = {}
        for s in range(self.n_states):
            mask = self.state_series == s
            s_spy = spy_returns.reindex(self.state_series[mask].index).dropna()
            self.state_returns[s] = float(s_spy.mean()) if len(s_spy) > 0 else 0.0

        # Sort: state 0 = lowest return (bear/high-risk), state 1 = higher return (bull/low-risk)
        sorted_states = sorted(self.state_returns, key=lambda s: self.state_returns[s])
        self.state_map = {old: new for new, old in enumerate(sorted_states)}
        self.state_series = self.state_series.map(self.state_map)

        # Update state returns after remapping
        for s in range(self.n_states):
            mask = self.state_series == s
            s_spy = spy_returns.reindex(self.state_series[mask].index).dropna()
            self.state_returns[s] = float(s_spy.mean()) if len(s_spy) > 0 else 0.0

        regime_names = {0: 'risk-off', 1: 'risk-on'}
        for s, name in regime_names.items():
            pct = (self.state_series == s).mean() * 100
            avg_ret = self.state_returns.get(s, 0) * 252
            print(f"  [Layer 2] State {s} ({name}): {pct:.1f}% of time, "
                  f"ann. avg SPY return: {avg_ret:.1%}")

        self._feature_df = feature_df  # store original (unscaled) for reference
        self.is_fitted = True

    def _compute_features(self, spy_window: pd.Series) -> Optional[np.ndarray]:
        """Compute feature vector for a given SPY window."""
        min_len = 2 * self.window
        if len(spy_window) < min_len:
            return None

        # Wasserstein between two non-overlapping windows
        prev_w = spy_window.iloc[-2 * self.window: -self.window].values
        curr_w = spy_window.iloc[-self.window:].values
        w_dist = wasserstein_distance_1d(prev_w, curr_w)

        roll_ret = float(spy_window.iloc[-21:].mean()) if len(spy_window) >= 21 else float(spy_window.mean())
        roll_vol = float(spy_window.iloc[-21:].std()) if len(spy_window) >= 21 else float(spy_window.std())
        roll_skew = float(stats.skew(spy_window.iloc[-42:].values)) if len(spy_window) >= 42 else float(stats.skew(spy_window.values))

        # Drawdown from recent high
        price_idx = (1 + spy_window).cumprod()
        roll_max = price_idx.rolling(min(252, len(price_idx)), min_periods=20).max().iloc[-1]
        drawdown = float(price_idx.iloc[-1] / roll_max - 1) if roll_max > 0 else 0.0

        return np.array([[w_dist, roll_ret, roll_vol, roll_skew, drawdown]])

    def predict(self, spy_window: pd.Series, latest_date=None) -> Dict:
        """Predict HMM state for recent window."""
        if not self.is_fitted:
            return {'signal': 0, 'regime': 'unknown', 'confidence': 0.5}

        X_raw = self._compute_features(spy_window)
        if X_raw is None:
            return {'signal': 0, 'regime': 'unknown', 'confidence': 0.5}

        # Scale features using fitted scaler
        X_new = self._feature_scaler.transform(X_raw)

        # Use posterior probabilities from HMM predict_proba
        try:
            log_posteriors = self.hmm.predict_proba(X_new)  # shape (1, n_states)
            probs = log_posteriors[0]
            # Handle any numerical issues
            probs = np.nan_to_num(probs, nan=1.0/self.n_states)
            if probs.sum() > 0:
                probs = probs / probs.sum()
            else:
                probs = np.ones(self.n_states) / self.n_states
            raw_state = int(np.argmax(probs))
            confidence = float(probs.max())
        except Exception as e:
            try:
                raw_state = int(self.hmm.predict(X_new)[0])
                confidence = 0.65
            except Exception:
                return {'signal': 0, 'regime': 'unknown', 'confidence': 0.5}

        mapped_state = self.state_map.get(raw_state, raw_state)
        regime_names = {0: 'risk-off', 1: 'risk-on'}
        signal_map = {0: -1, 1: 1}

        return {
            'signal': signal_map.get(mapped_state, 0),
            'regime': regime_names.get(mapped_state, 'unknown'),
            'state_id': mapped_state,
            'confidence': confidence,
            'w_distance': float(X_raw[0][0]),
        }


# ─────────────────────────────────────────────────────────────
#  LAYER 3: Skewness Dispersion
# ─────────────────────────────────────────────────────────────

class SkewnessDispersionLayer:
    """
    Layer 3: Cross-sectional skewness dispersion as a leading indicator.

    Based on arXiv:2604.07870. Key insight: before major regime transitions
    (esp. market crashes), there is typically a spike in the cross-sectional
    dispersion of individual stock return skewness. This acts as an early
    warning signal.

    We compute:
    1. Rolling 20-day skewness for each stock
    2. Cross-sectional std of those skewness values (dispersion)
    3. Z-score the dispersion vs historical mean/std
    4. High positive z-score = warning signal (potential regime shift)
    """

    def __init__(self, skew_window: int = 20, z_window: int = 252):
        self.skew_window = skew_window
        self.z_window = z_window
        self.dispersion_history: pd.Series = None
        self.disp_mean: float = None
        self.disp_std: float = None
        self.threshold_high: float = None  # z > this = bearish warning
        self.is_fitted = False

    def _compute_dispersion_series(self, stock_returns: pd.DataFrame) -> pd.Series:
        """
        Compute rolling cross-sectional skewness dispersion.
        For each date, compute rolling skewness of each stock, then take
        the cross-sectional std.
        """
        print("  [Layer 3] Computing rolling skewness for each stock ...")
        # Rolling skewness per stock
        rolling_skew = stock_returns.rolling(self.skew_window).skew()
        # Cross-sectional std of skewness
        dispersion = rolling_skew.std(axis=1)
        return dispersion.dropna()

    def fit(self, stock_returns: pd.DataFrame, spy_returns: pd.Series):
        """Fit skewness dispersion model."""
        self.dispersion_history = self._compute_dispersion_series(stock_returns)
        print(f"  [Layer 3] Got {len(self.dispersion_history)} dispersion observations")

        self.disp_mean = float(self.dispersion_history.mean())
        self.disp_std = float(self.dispersion_history.std())

        # Rolling z-scores
        roll_mean = self.dispersion_history.rolling(self.z_window).mean()
        roll_std = self.dispersion_history.rolling(self.z_window).std()
        z_scores = (self.dispersion_history - roll_mean) / roll_std.clip(lower=1e-8)
        z_scores = z_scores.dropna()
        self.z_history = z_scores

        # Determine threshold: above 80th percentile = warning
        self.threshold_high = float(np.percentile(z_scores.values, 80))
        self.threshold_very_high = float(np.percentile(z_scores.values, 95))

        # Check correlation with future SPY drawdowns (validation)
        future_ret_20d = spy_returns.shift(-20).rolling(20).sum().reindex(z_scores.index)
        valid = pd.DataFrame({'z': z_scores, 'fwd_ret': future_ret_20d}).dropna()
        if len(valid) > 100:
            corr = float(valid['z'].corr(valid['fwd_ret']))
            print(f"  [Layer 3] Z-score vs 20-day forward SPY return correlation: {corr:.3f}")

        print(f"  [Layer 3] Dispersion mean={self.disp_mean:.4f}, std={self.disp_std:.4f}")
        print(f"  [Layer 3] Warning threshold (80th pctile z): {self.threshold_high:.2f}")

        self.is_fitted = True

    def predict(self, stock_window: pd.DataFrame, spy_window: pd.Series) -> Dict:
        """Predict dispersion signal for recent window."""
        if not self.is_fitted or len(stock_window) < self.skew_window:
            return {'signal': 0, 'regime': 'neutral', 'confidence': 0.5}

        # Compute rolling skewness for latest window
        recent_skew = stock_window.rolling(self.skew_window).skew().iloc[-1]
        dispersion = float(recent_skew.std())

        # Z-score vs historical
        if self.disp_std > 0:
            z_score = (dispersion - self.disp_mean) / self.disp_std
        else:
            z_score = 0.0

        # Interpret signal
        if z_score > self.threshold_very_high:
            signal = -1
            regime = 'high-dispersion-warning'
            confidence = min(0.95, 0.7 + (z_score - self.threshold_very_high) * 0.05)
        elif z_score > self.threshold_high:
            signal = -1
            regime = 'elevated-dispersion'
            confidence = 0.6 + (z_score - self.threshold_high) / max(self.threshold_very_high - self.threshold_high, 0.1) * 0.1
        elif z_score < -1.0:
            signal = 1
            regime = 'low-dispersion-stable'
            confidence = min(0.85, 0.6 + abs(z_score) * 0.05)
        else:
            signal = 0
            regime = 'neutral-dispersion'
            confidence = 0.5

        return {
            'signal': signal,
            'regime': regime,
            'z_score': float(z_score),
            'dispersion': dispersion,
            'confidence': float(confidence),
        }


# ─────────────────────────────────────────────────────────────
#  REGIME STACK: Combines all three layers
# ─────────────────────────────────────────────────────────────

class RegimeStack:
    """
    Three-layer regime detection stack.

    Layers:
      1. EF Clustering (portfolio-level behavior, primary)
      2. Wasserstein HMM (return distribution shifts, secondary)
      3. Skewness Dispersion (cross-sectional leading indicator, tertiary)

    Consensus logic:
      - Layer 3 acts as early warning (override/caution flag)
      - Layer 1 and 2 provide the core regime signal
      - Consensus: weighted vote with Layer 1 = 40%, Layer 2 = 40%, Layer 3 = 20%
    """

    WEIGHTS = {1: 0.40, 2: 0.40, 3: 0.20}
    LAYER1_LOOKBACK = 63   # ~1 quarter
    LAYER2_LOOKBACK = 60   # 60-day distributions
    LAYER3_LOOKBACK = 20   # 20-day skewness window

    def __init__(self):
        self.layer1 = EFClusteringLayer(lookback=self.LAYER1_LOOKBACK, n_clusters=3)
        self.layer2 = WassersteinHMMLayer(window=self.LAYER2_LOOKBACK, n_states=2)
        self.layer3 = SkewnessDispersionLayer(skew_window=self.LAYER3_LOOKBACK)
        self._spy_returns = None
        self._stock_returns = None
        self.is_fitted = False
        self._last_predictions: Optional[Dict] = None

    def fit(self, returns_df: pd.DataFrame, spy_returns: Optional[pd.Series] = None):
        """
        Fit all three layers on historical data.

        Args:
            returns_df: DataFrame of individual stock returns (date x ticker)
            spy_returns: Optional SPY returns series. If None, uses SPY column from returns_df
                         or mean of returns_df.
        """
        if spy_returns is None:
            if 'SPY' in returns_df.columns:
                spy_returns = returns_df['SPY']
                stock_returns = returns_df.drop(columns=['SPY'])
            else:
                spy_returns = returns_df.mean(axis=1)
                stock_returns = returns_df
        else:
            stock_returns = returns_df

        self._spy_returns = spy_returns
        self._stock_returns = stock_returns

        print("\n--- Fitting Layer 1: EF Clustering ---")
        self.layer1.fit(stock_returns, spy_returns)

        print("\n--- Fitting Layer 2: Wasserstein HMM ---")
        self.layer2.fit(spy_returns)

        print("\n--- Fitting Layer 3: Skewness Dispersion ---")
        self.layer3.fit(stock_returns, spy_returns)

        self.is_fitted = True
        print("\n[RegimeStack] All layers fitted successfully.")

    def predict(self, date_str: Optional[str] = None) -> Dict:
        """
        Predict regime for a given date (or latest available date).

        Args:
            date_str: Date string like '2024-06-01' or None for latest.

        Returns:
            Dict with signal from each layer and consensus.
        """
        if not self.is_fitted:
            raise RuntimeError("RegimeStack.fit() must be called before predict()")

        # Determine prediction date
        if date_str is not None:
            pred_date = pd.Timestamp(date_str)
        else:
            pred_date = self._spy_returns.index[-1]

        # Get data up to prediction date
        spy_up_to = self._spy_returns[self._spy_returns.index <= pred_date]
        stocks_up_to = self._stock_returns[self._stock_returns.index <= pred_date]

        if len(spy_up_to) == 0:
            return {'error': f'No data available up to {pred_date}'}

        # Layer 1: Need stock returns window
        min_stocks = max(self.LAYER1_LOOKBACK + 10, 80)
        if len(stocks_up_to) >= min_stocks:
            stock_window_l1 = stocks_up_to.iloc[-self.LAYER1_LOOKBACK:]
            l1_pred = self.layer1.predict(stock_window_l1)
        else:
            l1_pred = {'signal': 0, 'regime': 'neutral', 'confidence': 0.5}

        # Layer 2: Need SPY window (at least 2*window + 252 for drawdown + extra)
        min_spy = max(self.LAYER2_LOOKBACK * 2 + 252 + 50, 400)
        if len(spy_up_to) >= min_spy:
            spy_window_l2 = spy_up_to.iloc[-max(self.LAYER2_LOOKBACK * 2 + 300, 400):]
            l2_pred = self.layer2.predict(spy_window_l2, latest_date=pred_date)
        else:
            l2_pred = {'signal': 0, 'regime': 'unknown', 'confidence': 0.5}

        # Layer 3: Need stock returns
        min_stocks_l3 = max(self.LAYER3_LOOKBACK + 10, 50)
        if len(stocks_up_to) >= min_stocks_l3:
            stock_window_l3 = stocks_up_to.iloc[-max(self.LAYER3_LOOKBACK * 3, 100):]
            spy_window_l3 = spy_up_to.iloc[-50:]
            l3_pred = self.layer3.predict(stock_window_l3, spy_window_l3)
        else:
            l3_pred = {'signal': 0, 'regime': 'neutral', 'confidence': 0.5}

        # Consensus: weighted vote
        signals = {
            1: l1_pred.get('signal', 0),
            2: l2_pred.get('signal', 0),
            3: l3_pred.get('signal', 0),
        }
        confidences = {
            1: l1_pred.get('confidence', 0.5),
            2: l2_pred.get('confidence', 0.5),
            3: l3_pred.get('confidence', 0.5),
        }

        # Weighted signal
        weighted_signal = sum(signals[l] * self.WEIGHTS[l] * confidences[l] for l in [1, 2, 3])
        total_weight = sum(self.WEIGHTS[l] * confidences[l] for l in [1, 2, 3])
        consensus_score = weighted_signal / total_weight if total_weight > 0 else 0.0

        if consensus_score > 0.15:
            consensus_regime = 'bull'
            consensus_signal = 1
        elif consensus_score < -0.15:
            consensus_regime = 'bear'
            consensus_signal = -1
        else:
            consensus_regime = 'neutral'
            consensus_signal = 0

        # Overall confidence
        overall_conf = self.get_regime_confidence(signals, confidences)

        result = {
            'date': str(pred_date.date()),
            'layer1_ef_clustering': l1_pred,
            'layer2_wasserstein_hmm': l2_pred,
            'layer3_skew_dispersion': l3_pred,
            'consensus': {
                'signal': consensus_signal,
                'regime': consensus_regime,
                'score': float(consensus_score),
                'confidence': float(overall_conf),
            },
        }
        self._last_predictions = result
        return result

    def get_regime_confidence(self, signals=None, confidences=None) -> float:
        """
        Compute 0-1 confidence score for the current regime prediction.

        Higher confidence when:
        - Multiple layers agree
        - Individual layer confidences are high
        """
        if signals is None or confidences is None:
            if self._last_predictions is None:
                return 0.5
            p = self._last_predictions
            signals = {
                1: p['layer1_ef_clustering'].get('signal', 0),
                2: p['layer2_wasserstein_hmm'].get('signal', 0),
                3: p['layer3_skew_dispersion'].get('signal', 0),
            }
            confidences = {
                1: p['layer1_ef_clustering'].get('confidence', 0.5),
                2: p['layer2_wasserstein_hmm'].get('confidence', 0.5),
                3: p['layer3_skew_dispersion'].get('confidence', 0.5),
            }

        # Agreement score: fraction of layers pointing same direction as consensus
        signal_values = list(signals.values())
        if all(s > 0 for s in signal_values if s != 0) or all(s < 0 for s in signal_values if s != 0):
            agreement = 1.0
        else:
            nonzero = [s for s in signal_values if s != 0]
            if len(nonzero) == 0:
                agreement = 0.5
            else:
                # fraction agreeing with majority direction
                majority = 1 if sum(s > 0 for s in nonzero) > len(nonzero) / 2 else -1
                agreement = sum(1 for s in signal_values if s == majority) / len(signal_values)

        # Weighted average confidence
        avg_conf = sum(self.WEIGHTS[l] * confidences[l] for l in [1, 2, 3])

        # Combined: geometric mean of agreement and avg confidence
        return float(np.sqrt(agreement * avg_conf))


# ─────────────────────────────────────────────────────────────
#  BACKTEST: Walk-Forward Regime Analysis
# ─────────────────────────────────────────────────────────────

def run_backtest(regime_stack: RegimeStack, spy_returns: pd.Series,
                 start_date: str = "2017-01-01") -> Dict:
    """
    Walk-forward backtest of the regime stack.

    After fitting on all historical data, we step through time and record:
    - The regime at each month-end
    - Transitions between regimes
    - SPY returns in each regime state
    """
    print("\n--- Running Walk-Forward Backtest ---")

    # Get all month-end dates from start_date
    test_dates = spy_returns[spy_returns.index >= start_date].resample('ME').last().index
    print(f"Testing {len(test_dates)} monthly observation points")

    monthly_regimes = []
    transitions = []
    prev_regime = None

    for i, dt in enumerate(test_dates):
        if i % 12 == 0:
            print(f"  Progress: {dt.date()} ({i+1}/{len(test_dates)})")

        try:
            pred = regime_stack.predict(str(dt.date()))
            regime = pred['consensus']['regime']
            signal = pred['consensus']['signal']
            confidence = pred['consensus']['confidence']
            score = pred['consensus']['score']

            l1_regime = pred['layer1_ef_clustering'].get('regime', 'unknown')
            l2_regime = pred['layer2_wasserstein_hmm'].get('regime', 'unknown')
            l3_regime = pred['layer3_skew_dispersion'].get('regime', 'unknown')
            l3_z = pred['layer3_skew_dispersion'].get('z_score', 0.0)

            # 1-month forward SPY return
            fwd_dates = spy_returns[spy_returns.index > dt]
            fwd_return = float(fwd_dates.iloc[:21].sum()) if len(fwd_dates) >= 21 else np.nan

            monthly_regimes.append({
                'date': str(dt.date()),
                'regime': regime,
                'signal': signal,
                'confidence': round(confidence, 4),
                'score': round(score, 4),
                'l1_regime': l1_regime,
                'l2_regime': l2_regime,
                'l3_regime': l3_regime,
                'l3_z_score': round(l3_z, 3) if not np.isnan(l3_z) else None,
                'fwd_21d_spy': round(fwd_return, 5) if not np.isnan(fwd_return) else None,
            })

            # Track transitions
            if prev_regime is not None and regime != prev_regime:
                transitions.append({
                    'date': str(dt.date()),
                    'from_regime': prev_regime,
                    'to_regime': regime,
                    'signal': signal,
                    'confidence': round(confidence, 4),
                })
            prev_regime = regime

        except Exception as e:
            print(f"  Warning: prediction failed for {dt}: {e}")
            traceback.print_exc()

    # Compute regime statistics
    regime_df = pd.DataFrame(monthly_regimes)
    regime_df['date'] = pd.to_datetime(regime_df['date'])
    regime_df = regime_df.set_index('date')

    stats_by_regime = {}
    for reg in ['bull', 'neutral', 'bear']:
        mask = regime_df['regime'] == reg
        if mask.sum() > 0:
            fwd_rets = regime_df.loc[mask, 'fwd_21d_spy'].dropna()
            stats_by_regime[reg] = {
                'count': int(mask.sum()),
                'pct_of_time': round(float(mask.mean()) * 100, 1),
                'avg_fwd_21d_return': round(float(fwd_rets.mean()), 5) if len(fwd_rets) > 0 else None,
                'median_fwd_21d_return': round(float(fwd_rets.median()), 5) if len(fwd_rets) > 0 else None,
                'win_rate': round(float((fwd_rets > 0).mean()), 3) if len(fwd_rets) > 0 else None,
            }

    # Compute signal performance
    regime_df_valid = regime_df.dropna(subset=['fwd_21d_spy'])
    if len(regime_df_valid) > 0:
        signal_performance = {
            'bull_avg_fwd': round(float(regime_df_valid[regime_df_valid['signal'] == 1]['fwd_21d_spy'].mean()), 5),
            'bear_avg_fwd': round(float(regime_df_valid[regime_df_valid['signal'] == -1]['fwd_21d_spy'].mean()), 5),
            'neutral_avg_fwd': round(float(regime_df_valid[regime_df_valid['signal'] == 0]['fwd_21d_spy'].mean()), 5),
            'unconditional_avg_fwd': round(float(regime_df_valid['fwd_21d_spy'].mean()), 5),
        }
    else:
        signal_performance = {}

    print(f"\nRegime statistics:")
    for reg, s in stats_by_regime.items():
        print(f"  {reg}: {s['pct_of_time']:.1f}% of time, "
              f"avg fwd return: {s.get('avg_fwd_21d_return', 'N/A'):.4f}, "
              f"win rate: {s.get('win_rate', 'N/A')}")

    if signal_performance:
        print(f"\nSignal performance (21-day forward SPY return):")
        print(f"  Bull signal:   {signal_performance.get('bull_avg_fwd', 'N/A'):.4f}")
        print(f"  Neutral signal: {signal_performance.get('neutral_avg_fwd', 'N/A'):.4f}")
        print(f"  Bear signal:   {signal_performance.get('bear_avg_fwd', 'N/A'):.4f}")
        print(f"  Unconditional: {signal_performance.get('unconditional_avg_fwd', 'N/A'):.4f}")

    return {
        'monthly_regimes': [
            {k: (v if not (isinstance(v, float) and np.isnan(v)) else None)
             for k, v in row.items()}
            for row in regime_df.reset_index().to_dict('records')
            if row
        ],
        'transitions': transitions,
        'regime_stats': stats_by_regime,
        'signal_performance': signal_performance,
        'n_transitions': len(transitions),
    }


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    output_dir = "/workspace/group/trading_eval/rounds"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "r35_regime_stack_results.json")

    # ── 1. Load data ──────────────────────────────────────────
    print("\n[Step 1] Loading data ...")
    data = load_data(start="2015-01-01", end="2026-01-01")
    spy_returns = data['spy_returns']
    stock_returns = data['stock_returns']

    print(f"\nData summary:")
    print(f"  SPY returns: {len(spy_returns)} days, {spy_returns.index[0].date()} to {spy_returns.index[-1].date()}")
    print(f"  Stock returns: {stock_returns.shape[0]} days x {stock_returns.shape[1]} tickers")

    # ── 2. Build and fit RegimeStack ──────────────────────────
    print("\n[Step 2] Fitting RegimeStack ...")
    stack = RegimeStack()
    stack.fit(stock_returns, spy_returns)

    # ── 3. Current regime prediction ─────────────────────────
    print("\n[Step 3] Current regime prediction ...")
    latest_pred = stack.predict()
    print(f"\nLatest prediction ({latest_pred['date']}):")
    print(f"  Layer 1 (EF Clustering):    {latest_pred['layer1_ef_clustering'].get('regime', 'N/A')} "
          f"(signal={latest_pred['layer1_ef_clustering'].get('signal', 0):+d}, "
          f"conf={latest_pred['layer1_ef_clustering'].get('confidence', 0):.2f})")
    print(f"  Layer 2 (Wasserstein HMM):  {latest_pred['layer2_wasserstein_hmm'].get('regime', 'N/A')} "
          f"(signal={latest_pred['layer2_wasserstein_hmm'].get('signal', 0):+d}, "
          f"conf={latest_pred['layer2_wasserstein_hmm'].get('confidence', 0):.2f})")
    print(f"  Layer 3 (Skew Dispersion):  {latest_pred['layer3_skew_dispersion'].get('regime', 'N/A')} "
          f"(signal={latest_pred['layer3_skew_dispersion'].get('signal', 0):+d}, "
          f"z={latest_pred['layer3_skew_dispersion'].get('z_score', 0):.2f})")
    print(f"  Consensus: {latest_pred['consensus']['regime'].upper()} "
          f"(signal={latest_pred['consensus']['signal']:+d}, "
          f"score={latest_pred['consensus']['score']:.3f}, "
          f"conf={latest_pred['consensus']['confidence']:.2f})")

    # ── 4. Backtest ───────────────────────────────────────────
    print("\n[Step 4] Running backtest ...")
    backtest_results = run_backtest(stack, spy_returns, start_date="2017-01-01")

    # ── 5. Save results ───────────────────────────────────────
    print(f"\n[Step 5] Saving results to {output_path} ...")

    # Convert latest_pred to JSON-serializable form
    def clean_for_json(obj):
        if isinstance(obj, dict):
            return {k: clean_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [clean_for_json(v) for v in obj]
        elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
            return None
        elif isinstance(obj, (np.integer,)):
            return int(obj)
        elif isinstance(obj, (np.floating,)):
            return float(obj)
        elif isinstance(obj, pd.Timestamp):
            return str(obj.date())
        return obj

    results = {
        'metadata': {
            'round': 'R35',
            'name': 'Three-Layer Regime Detection Stack',
            'run_date': str(date.today()),
            'data_range': {
                'start': str(spy_returns.index[0].date()),
                'end': str(spy_returns.index[-1].date()),
            },
            'layers': {
                'layer1': 'EF Clustering (portfolio-level regime, K-Means on EF coefficients)',
                'layer2': 'Wasserstein HMM (return distribution shift, GaussianHMM)',
                'layer3': 'Skewness Dispersion (cross-sectional leading indicator)',
            },
            'consensus_weights': RegimeStack.WEIGHTS,
        },
        'current_regime': clean_for_json(latest_pred),
        'backtest': clean_for_json(backtest_results),
        'layer1_params': {
            'lookback_days': stack.layer1.lookback,
            'n_clusters': stack.layer1.n_clusters,
            'cluster_returns_annualized': {
                str(k): round(v * 252, 4) for k, v in stack.layer1.cluster_returns.items()
            },
        },
        'layer2_params': {
            'window_days': stack.layer2.window,
            'n_states': stack.layer2.n_states,
            'state_returns_annualized': {
                str(k): round(v * 252, 4) for k, v in stack.layer2.state_returns.items()
            },
        },
        'layer3_params': {
            'skew_window_days': stack.layer3.skew_window,
            'z_window_days': stack.layer3.z_window,
            'dispersion_mean': round(stack.layer3.disp_mean, 6),
            'dispersion_std': round(stack.layer3.disp_std, 6),
            'warning_threshold_z': round(stack.layer3.threshold_high, 3),
            'high_warning_threshold_z': round(stack.layer3.threshold_very_high, 3),
        },
    }

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"Results saved to {output_path}")

    # ── 6. Print summary ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"\nCurrent market regime: {latest_pred['consensus']['regime'].upper()}")
    print(f"Consensus confidence:  {latest_pred['consensus']['confidence']:.2%}")
    print(f"Regime transitions detected: {backtest_results['n_transitions']}")
    print(f"\nRegime performance (21-day forward SPY):")
    sp = backtest_results.get('signal_performance', {})
    if sp:
        print(f"  Bull:        {sp.get('bull_avg_fwd', 0)*100:+.2f}%")
        print(f"  Neutral:     {sp.get('neutral_avg_fwd', 0)*100:+.2f}%")
        print(f"  Bear:        {sp.get('bear_avg_fwd', 0)*100:+.2f}%")
        print(f"  Baseline:    {sp.get('unconditional_avg_fwd', 0)*100:+.2f}%")
    print("\nTop 10 regime transitions:")
    for t in backtest_results['transitions'][:10]:
        print(f"  {t['date']}: {t['from_regime']} -> {t['to_regime']} (conf={t['confidence']:.2f})")
    print(f"\nFull results saved to: {output_path}")


if __name__ == "__main__":
    main()
