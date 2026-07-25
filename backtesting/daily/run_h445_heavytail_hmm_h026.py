#!/usr/bin/env python3
"""
H445 — Heavy-Tail HMM Emission Families for Regime-Conditional VaR Position Sizing on H026
Source: arXiv:2606.23492 (Alswaidan, Jin, Varner 2026)

Tests whether Student-t / Laplace HMM emissions improve H026 ETF rotation
by providing better-calibrated regime-conditional VaR for position scaling.

Variants:
  A: Student-t emission (GMM approximation) + VaR scaling
  B: Laplace emission (moment-matching) + VaR scaling
  C: Student-t emission + binary bull/bear gate (no scaling)
  D: Gaussian emission + VaR scaling (ablation baseline)

IS:  2008-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-07-01

Gate: OOS Sharpe > 2.0 AND MaxDD > -8%
Baseline: H026 canonical top-1 with 200MA gate (H301)
"""

import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from hmmlearn.hmm import GaussianHMM, GMMHMM
from scipy.stats import t as t_dist, laplace

warnings.filterwarnings('ignore')

# ---------------------------------------------------------------------------
# H026 Universe (25-asset ETF rotation)
# ---------------------------------------------------------------------------
H026_UNIVERSE = [
    'XLB', 'XLC', 'XLE', 'XLF', 'XLI', 'XLK', 'XLP', 'XLRE', 'XLU', 'XLV', 'XLY',
    'GLD', 'SLV', 'DBC', 'USO', 'TLT', 'IEF', 'SHY', 'LQD', 'HYG',
    'EEM', 'EFA', 'IWM', 'QQQ', 'BIL'
]
SPY_TICKER = 'SPY'
START      = '2006-01-01'
IS_END     = '2017-12-31'
OOS_START  = '2018-01-01'
ROLL_YEARS = 3
VAR_LEVEL  = 0.95      # VaR confidence level
VAR_THRESHOLD = 0.030  # daily VaR above which we scale down (3%)
SCALE_MIN  = 0.25      # minimum position scale when VaR is extreme


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_h026_data():
    all_tickers = list(set(H026_UNIVERSE + [SPY_TICKER]))
    raw = yf.download(all_tickers, start=START, auto_adjust=True, progress=False)['Close']
    raw = raw.dropna(how='all').ffill()
    spy_prices = raw[SPY_TICKER]
    # H026 returns: use the universe ETFs
    universe_prices = raw[[t for t in H026_UNIVERSE if t in raw.columns]]
    returns = universe_prices.pct_change().dropna()
    spy_ret = spy_prices.pct_change().dropna()
    return universe_prices, returns, spy_prices, spy_ret


# ---------------------------------------------------------------------------
# H026 top-1 monthly momentum signal
# ---------------------------------------------------------------------------
def compute_h026_signal(prices_monthly):
    """12-month momentum rank, top-1 selection. Returns monthly selected ticker."""
    r12 = prices_monthly.pct_change(12).shift(1)  # avoid look-ahead
    selections = r12.idxmax(axis=1).dropna()
    return selections


# ---------------------------------------------------------------------------
# HMM fitting — Gaussian, GMM (Student-t approx), Laplace approx
# ---------------------------------------------------------------------------
def fit_gaussian_hmm(X, k=2, n_fits=5):
    best_ll = -np.inf
    best_m = None
    for seed in range(n_fits):
        try:
            m = GaussianHMM(n_components=k, covariance_type='diag',
                            n_iter=200, random_state=seed)
            m.fit(X)
            ll = m.score(X)
            if ll > best_ll:
                best_ll = ll
                best_m = m
        except Exception:
            continue
    return best_m


def fit_gmm_hmm(X, k=2, n_mix=3, n_fits=3):
    """
    GMMHMM as Student-t approximation:
    A mixture of 3 Gaussians per state can approximate a Student-t distribution.
    """
    best_ll = -np.inf
    best_m = None
    for seed in range(n_fits):
        try:
            m = GMMHMM(n_components=k, n_mix=n_mix, covariance_type='diag',
                       n_iter=200, random_state=seed)
            m.fit(X)
            ll = m.score(X)
            if ll > best_ll:
                best_ll = ll
                best_m = m
        except Exception:
            continue
    return best_m


def laplace_var(loc, scale, level=0.95):
    """Analytical VaR for Laplace distribution (loss side)."""
    if level > 0.5:
        return -(loc - scale * np.log(2 * (1 - level)))
    else:
        return -(loc + scale * np.log(2 * level))


def gaussian_var(mu, sigma, level=0.95):
    from scipy.stats import norm
    return -(mu + sigma * norm.ppf(1 - level))


# ---------------------------------------------------------------------------
# Regime-conditional VaR estimation
# ---------------------------------------------------------------------------
def estimate_var_for_state(state_returns, variant, level=VAR_LEVEL):
    """
    Estimate daily VaR at `level` confidence for a given regime.
    Returns positive number (loss expressed as positive VaR).
    """
    if len(state_returns) < 20:
        return np.percentile(np.abs(state_returns), level * 100)

    mu = state_returns.mean()
    sig = state_returns.std()

    if variant == 'D':  # Gaussian
        return gaussian_var(mu, sig, level)

    elif variant == 'A':  # Student-t moment matching
        # Estimate df from kurtosis: kurtosis = 6/(df-4) for df>4 => df = 6/kurtosis + 4
        from scipy.stats import kurtosis as kurt
        excess_kurt = kurt(state_returns, fisher=True)
        excess_kurt = max(0.1, excess_kurt)  # must be positive for heavy tail
        df_est = max(4.1, 6.0 / excess_kurt + 4)
        var_t = -t_dist.ppf(1 - level, df=df_est, loc=mu, scale=sig * np.sqrt((df_est - 2) / df_est))
        return max(var_t, 0.0)

    elif variant == 'B':  # Laplace
        b = sig / np.sqrt(2)  # Laplace scale from variance: var = 2*b^2
        return laplace_var(mu, b, level)

    elif variant == 'C':  # Student-t, binary gate (no VaR scaling)
        return 0.0  # handled separately

    return gaussian_var(mu, sig, level)


# ---------------------------------------------------------------------------
# Rolling HMM + VaR position scale
# ---------------------------------------------------------------------------
def compute_var_scale(spy_returns, variant='A'):
    """
    For each month, look back 3Y of daily SPY returns, fit HMM, get current regime,
    estimate regime-conditional VaR, compute position scale.
    """
    roll_days = int(ROLL_YEARS * 252)
    dates = spy_returns.index

    daily_scale = pd.Series(index=dates, dtype=float)
    daily_bull = pd.Series(index=dates, dtype=bool)

    for t in range(roll_days, len(dates)):
        window = spy_returns.iloc[t - roll_days:t].values.reshape(-1, 1)
        date = dates[t]

        # Fit model
        if variant in ('A', 'C'):
            model = fit_gmm_hmm(window, k=2, n_mix=3)
        else:  # B, D
            model = fit_gaussian_hmm(window, k=2)

        if model is None:
            daily_scale[date] = 1.0
            daily_bull[date] = True
            continue

        # Predict current state
        try:
            states = model.predict(window)
            curr_state = states[-1]
        except Exception:
            daily_scale[date] = 1.0
            daily_bull[date] = True
            continue

        # Identify bull state (higher mean return)
        if hasattr(model, 'means_'):
            # GaussianHMM
            means = model.means_.flatten()
        elif hasattr(model, 'gmms_'):
            # GMMHMM — use weighted mean of mixture components
            means = np.array([np.sum(model.weights_[k] * model.means_[k].flatten())
                              for k in range(model.n_components)])
        else:
            means = np.array([0.0, 0.0])

        bull_state = np.argmax(means)
        is_bull = (curr_state == bull_state)
        daily_bull[date] = is_bull

        # Variant C: binary gate
        if variant == 'C':
            daily_scale[date] = 1.0 if is_bull else 0.0
            continue

        # VaR-based scaling
        state_ret = spy_returns.iloc[t - roll_days:t].values[states == curr_state]
        var95 = estimate_var_for_state(state_ret, variant, level=VAR_LEVEL)

        if var95 <= VAR_THRESHOLD:
            scale = 1.0
        else:
            # Linear scale-down: at 2x threshold, reduce to SCALE_MIN
            excess = (var95 - VAR_THRESHOLD) / VAR_THRESHOLD
            scale = max(SCALE_MIN, 1.0 - excess * (1 - SCALE_MIN))

        daily_scale[date] = scale

    daily_scale = daily_scale.ffill().fillna(1.0)
    daily_bull = daily_bull.ffill().fillna(True)
    return daily_scale, daily_bull


# ---------------------------------------------------------------------------
# H026 Backtest with VaR overlay
# ---------------------------------------------------------------------------
def run_h026_var_overlay(prices, spy_prices, daily_scale, daily_bull, variant):
    """
    Monthly H026 top-1, with position scale from daily VaR computation.
    Scale is resampled to month-end for allocation.
    """
    # Monthly prices and returns
    monthly_prices = prices.resample('ME').last()
    monthly_returns = monthly_prices.pct_change()
    daily_returns = prices.pct_change()

    # H026 signal: top-1 by 12m momentum
    selections = compute_h026_signal(monthly_prices)

    # 200MA SPY gate
    spy_200ma = spy_prices.rolling(200).mean()
    spy_above_200 = spy_prices > spy_200ma
    spy_monthly_gate = spy_above_200.resample('ME').last()

    # Position scale: month-end value of daily scale
    scale_monthly = daily_scale.resample('ME').last().reindex(monthly_prices.index).ffill()

    portfolio_returns = []
    portfolio_dates = []

    for i in range(1, len(monthly_prices)):
        month_start = monthly_prices.index[i - 1]
        month_end = monthly_prices.index[i]
        sel_date = month_start

        if sel_date not in selections.index:
            continue

        selected = selections[sel_date]
        if selected not in prices.columns:
            continue

        # Apply 200MA gate
        in_market = spy_monthly_gate.get(sel_date, True)
        if not in_market:
            selected = 'BIL' if 'BIL' in prices.columns else selected

        # Get scale for this month
        sc = scale_monthly.get(sel_date, 1.0)
        if pd.isna(sc):
            sc = 1.0

        # Daily returns within this month for selected ticker
        mask = (daily_returns.index > month_start) & (daily_returns.index <= month_end)
        month_daily = daily_returns.loc[mask]

        if selected not in month_daily.columns or len(month_daily) == 0:
            continue

        # Scale: sc in selected + (1-sc) in BIL (assume BIL = 0)
        ticker_ret = month_daily[selected]
        if 'BIL' in month_daily.columns:
            bil_ret = month_daily['BIL']
        else:
            bil_ret = pd.Series(0.0, index=ticker_ret.index)

        port_daily = sc * ticker_ret + (1.0 - sc) * bil_ret
        portfolio_returns.extend(port_daily.tolist())
        portfolio_dates.extend(port_daily.index.tolist())

    if not portfolio_dates:
        return pd.Series(dtype=float)

    port_series = pd.Series(portfolio_returns, index=portfolio_dates)
    return port_series


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def compute_metrics(port_ret, label='Strategy'):
    if len(port_ret) == 0:
        print(f"{label}: NO DATA")
        return {}
    ann_ret = port_ret.mean() * 252
    ann_vol = port_ret.std() * np.sqrt(252)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0
    cum = (1 + port_ret).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()
    n_years = len(port_ret) / 252
    cagr = cum.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else 0.0
    print(f"{label:45s}  CAGR={cagr:6.2%}  Sharpe={sharpe:5.3f}  MaxDD={max_dd:6.2%}")
    return {'sharpe': sharpe, 'maxdd': max_dd, 'cagr': cagr}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("H445 — Heavy-Tail HMM Regime-Conditional VaR Overlay on H026")
    print("Source: arXiv:2606.23492 | Universe: H026 25-ETF rotation")
    print("=" * 70)

    prices, returns, spy_prices, spy_ret = load_h026_data()
    spy_ret_full = spy_ret.dropna()

    # Baseline: H026 canonical (no overlay) — run plain version
    print("Computing H026 canonical baseline (no VaR overlay)...")
    baseline_scale = pd.Series(1.0, index=spy_ret_full.index)
    baseline_bull  = pd.Series(True,  index=spy_ret_full.index)
    baseline_port = run_h026_var_overlay(prices, spy_prices, baseline_scale, baseline_bull, 'D')
    oos_baseline = baseline_port.loc[OOS_START:]
    print()
    compute_metrics(oos_baseline, 'H026 canonical OOS (no overlay)')
    print()

    # Variants
    results = {}
    for var in ('A', 'B', 'C', 'D'):
        print(f"Computing daily VaR scale for Variant {var}...")
        daily_scale, daily_bull = compute_var_scale(spy_ret_full, variant=var)
        port = run_h026_var_overlay(prices, spy_prices, daily_scale, daily_bull, var)
        oos_port = port.loc[OOS_START:]
        metrics = compute_metrics(oos_port, f'H445 Var {var} OOS')
        results[var] = metrics
        print()

    print("=" * 70)
    print("GATE: OOS Sharpe > 2.0 AND MaxDD > -8%")
    for var, m in results.items():
        if not m:
            continue
        gate = 'PASS' if m['sharpe'] > 2.0 and m['maxdd'] > -0.08 else 'FAIL'
        print(f"  Var {var}: Sharpe={m['sharpe']:.3f}  MaxDD={m['maxdd']:.2%}  -> {gate}")


if __name__ == '__main__':
    main()
