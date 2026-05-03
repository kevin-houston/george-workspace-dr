#!/usr/bin/env python3.11
"""
Round 29 — Equity Pairs Trading with Factor Residualization and OU-Calibrated
Dynamic Thresholds
=================================================================================

Pipeline:
  Stage 0: Factor residualization (SPY + sector ETF rolling OLS, 60-day window)
  Stage 1: Cointegration filtering (Engle-Granger p < 0.05) on residuals
  Stage 2: OU parameter estimation + dynamic entry thresholds based on half-life
  Stage 3: Trade execution with stop-loss, Kelly sizing, rolling 60-day refitting

Variants tested:
  Baseline: raw returns + fixed ±2σ thresholds (R23 methodology comparison)
  R29 v1:   factor-residualized returns + fixed ±2σ thresholds
  R29 v2:   factor-residualized returns + OU-calibrated thresholds (full spec)

Universe: Fortune 100 subset (25 stocks)
Date range: 2020-01-01 to 2025-12-31
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

warnings.filterwarnings("ignore")

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
    from scipy.optimize import minimize
    from scipy.stats import norm
    from statsmodels.tsa.stattools import coint, adfuller
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: /usr/bin/python3.11 -m pip install yfinance scipy statsmodels numpy pandas --break-system-packages -q")
    sys.exit(1)

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

START_DATE = "2020-01-01"
END_DATE   = "2025-12-31"
CACHE_FILE = CACHE_DIR / "r29_universe.pkl"

# ── Universe ───────────────────────────────────────────────────────────────────
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'KO',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK', 'COST', 'NFLX',
    'QCOM', 'TXN', 'GE',
]

# Sector ETFs
SECTOR_ETFS = ['XLK', 'XLF', 'XLV', 'XLE', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE']

# Ticker → sector ETF mapping
TICKER_SECTOR = {
    'AAPL':  'XLK', 'MSFT':  'XLK', 'GOOGL': 'XLK', 'NVDA':  'XLK',
    'QCOM':  'XLK', 'TXN':   'XLK', 'NFLX':  'XLK',
    'JPM':   'XLF', 'BAC':   'XLF', 'V':     'XLF', 'MA':    'XLF',
    'JNJ':   'XLV', 'UNH':   'XLV', 'MRK':   'XLV',
    'XOM':   'XLE', 'CVX':   'XLE',
    'GE':    'XLI', 'HD':    'XLI',
    'AMZN':  'XLY', 'TSLA':  'XLY', 'COST':  'XLY',
    'WMT':   'XLP', 'PG':    'XLP', 'KO':    'XLP',
    'META':  'XLK',
}

# Sector groupings for pair selection (only within-sector pairs)
SECTOR_GROUPS = {
    'tech':        ['AAPL', 'MSFT', 'GOOGL', 'NVDA', 'QCOM', 'TXN', 'NFLX', 'META'],
    'finance':     ['JPM', 'BAC', 'V', 'MA'],
    'healthcare':  ['JNJ', 'UNH', 'MRK'],
    'energy':      ['XOM', 'CVX'],
    'industrial':  ['GE', 'HD'],
    'consumer_d':  ['AMZN', 'TSLA', 'COST'],
    'consumer_s':  ['WMT', 'PG', 'KO'],
}


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def extract_close_from_df(d: pd.DataFrame, symbol: str) -> Optional[pd.Series]:
    """Extract Close series from a DataFrame with potentially MultiIndex columns."""
    if d is None or not isinstance(d, pd.DataFrame):
        return None
    cols = d.columns
    # Try MultiIndex: ('Close', symbol)
    if hasattr(cols, 'levels'):
        try:
            s = d[('Close', symbol)]
            if isinstance(s, pd.Series) and len(s) > 200:
                return s.dropna()
        except Exception:
            pass
        # Try just the first level 'Close'
        try:
            close_cols = [c for c in cols if c[0] == 'Close']
            if close_cols:
                s = d[close_cols[0]]
                if isinstance(s, pd.Series) and len(s) > 200:
                    return s.dropna()
        except Exception:
            pass
    # Try plain 'Close'
    if 'Close' in cols:
        s = d['Close']
        if isinstance(s, pd.Series):
            return s.dropna()
        elif isinstance(s, pd.DataFrame) and len(s.columns) == 1:
            return s.iloc[:, 0].dropna()
    return None


def load_or_fetch(symbol: str, prices_cache: dict) -> Optional[pd.Series]:
    """Try existing caches first, then fetch if needed."""
    if symbol in prices_cache:
        s = prices_cache[symbol]
        # If already a clean Series, return it
        if isinstance(s, pd.Series):
            return s

    # Try existing cached pkl files (various naming conventions)
    candidates = [
        CACHE_DIR / f"{symbol}_2020-01-01_2025-12-31.pkl",
        CACHE_DIR / f"ohlcv_{symbol}_10yr.pkl",
        CACHE_DIR / f"ohlcv_{symbol}_15yr.pkl",
    ]
    for cp in candidates:
        if cp.exists():
            try:
                with open(cp, "rb") as f:
                    d = pickle.load(f)
                if isinstance(d, pd.DataFrame):
                    s = extract_close_from_df(d, symbol)
                    if s is not None and len(s) > 200:
                        if s.index.tz is not None:
                            s.index = s.index.tz_localize(None)
                        s = s[(s.index >= pd.Timestamp(START_DATE)) &
                              (s.index <= pd.Timestamp(END_DATE))]
                        if len(s) > 200:
                            prices_cache[symbol] = s
                            return s
                elif isinstance(d, pd.Series) and len(d) > 200:
                    s = d.copy()
                    if s.index.tz is not None:
                        s.index = s.index.tz_localize(None)
                    s = s[(s.index >= pd.Timestamp(START_DATE)) &
                          (s.index <= pd.Timestamp(END_DATE))]
                    if len(s) > 200:
                        prices_cache[symbol] = s
                        return s
            except Exception:
                pass

    # Try PEAD universe cache (MultiIndex columns format)
    pead_cache = CACHE_DIR / "pead_universe_2020-01-01_2025-12-31.pkl"
    if pead_cache.exists():
        try:
            with open(pead_cache, "rb") as f:
                d = pickle.load(f)
            if isinstance(d, pd.DataFrame):
                s = extract_close_from_df(d, symbol)
                if s is not None and len(s) > 200:
                    if s.index.tz is not None:
                        s.index = s.index.tz_localize(None)
                    prices_cache[symbol] = s
                    return s
        except Exception:
            pass

    # Fetch from yfinance
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        s = h["Close"].copy()
        if isinstance(s, pd.DataFrame):
            s = s.iloc[:, 0]
        if s.index.tz is not None:
            s.index = s.index.tz_localize(None)
        s = s.dropna()
        # Save for future use
        cp = CACHE_DIR / f"{symbol}_2020-01-01_2025-12-31.pkl"
        # Only save if it doesn't exist to avoid overwriting valid MultiIndex cache
        if not cp.exists():
            with open(cp, "wb") as f:
                pickle.dump(h[["Open","High","Low","Close","Volume"]], f)
        prices_cache[symbol] = s
        return s
    except Exception as e:
        print(f"  Could not fetch {symbol}: {e}", file=sys.stderr)
        return None


def fetch_all_prices() -> dict:
    """Load all universe + sector ETF prices."""
    if CACHE_FILE.exists():
        print("  Loading from R29 universe cache...")
        with open(CACHE_FILE, "rb") as f:
            return pickle.load(f)

    prices = {}
    all_syms = UNIVERSE + SECTOR_ETFS + ['SPY']
    print(f"  Fetching {len(all_syms)} symbols...")
    for sym in all_syms:
        s = load_or_fetch(sym, prices)
        status = f"{len(s)} bars" if s is not None else "FAILED"
        print(f"    {sym}: {status}")

    with open(CACHE_FILE, "wb") as f:
        pickle.dump(prices, f)
    print(f"  Saved universe cache → {CACHE_FILE}")
    return prices


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 0 — FACTOR RESIDUALIZATION
# ══════════════════════════════════════════════════════════════════════════════

def compute_rolling_residuals(
    stock_prices: pd.Series,
    spy_prices: pd.Series,
    sector_etf_prices: pd.Series,
    window: int = 60,
) -> pd.Series:
    """
    Rolling 60-day OLS: stock_ret ~ spy_ret + sector_ret
    Returns residuals (factor-orthogonalized returns).
    """
    stock_ret  = stock_prices.pct_change().dropna()
    spy_ret    = spy_prices.pct_change().dropna()
    sector_ret = sector_etf_prices.pct_change().dropna()

    # Align all three
    common = stock_ret.index.intersection(spy_ret.index).intersection(sector_ret.index)
    sr  = stock_ret.loc[common]
    spr = spy_ret.loc[common]
    ser = sector_ret.loc[common]

    residuals = pd.Series(np.nan, index=common)

    for i in range(window, len(common)):
        y  = sr.iloc[i-window:i].values
        x1 = spr.iloc[i-window:i].values
        x2 = ser.iloc[i-window:i].values
        X  = np.column_stack([np.ones(window), x1, x2])
        try:
            beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
            # Residual for current day
            xi = np.array([1.0, float(spr.iloc[i]), float(ser.iloc[i])])
            residuals.iloc[i] = float(sr.iloc[i]) - float(xi @ beta)
        except Exception:
            pass

    return residuals.dropna()


def build_residual_prices(
    prices: dict,
    window: int = 60,
) -> dict:
    """
    For each stock in universe, compute factor-residualized 'synthetic prices'
    by cumulating residual returns.
    Returns dict of synthetic price series.
    """
    spy = prices.get("SPY")
    if spy is None:
        raise ValueError("SPY not available in prices dict")

    residual_prices = {}
    for ticker in UNIVERSE:
        if ticker not in prices:
            continue
        sector_etf_sym = TICKER_SECTOR.get(ticker, "XLK")
        sector_etf = prices.get(sector_etf_sym)
        if sector_etf is None:
            sector_etf = spy  # fallback

        resid = compute_rolling_residuals(prices[ticker], spy, sector_etf, window=window)
        if len(resid) < 100:
            continue

        # Cumulate residuals into a synthetic price series
        synth = (1 + resid).cumprod()
        synth.name = ticker
        residual_prices[ticker] = synth

    return residual_prices


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 1 — COINTEGRATION FILTERING
# ══════════════════════════════════════════════════════════════════════════════

def align_pair(s1: pd.Series, s2: pd.Series) -> Tuple[pd.Series, pd.Series]:
    common = s1.index.intersection(s2.index)
    return s1.loc[common], s2.loc[common]


def test_cointegration(y: pd.Series, x: pd.Series, p_threshold: float = 0.05) -> dict:
    """Engle-Granger cointegration test. Returns stats and spread."""
    if len(y) < 60 or len(x) < 60:
        return {"cointegrated": False, "eg_p": 1.0}
    try:
        x_c    = add_constant(x.values)
        model  = OLS(y.values, x_c).fit()
        beta   = float(model.params[1])
        alpha  = float(model.params[0])
        spread = y - beta * x - alpha

        _, eg_p, _ = coint(y.values, x.values)

        return {
            "beta":          round(beta, 6),
            "alpha":         round(alpha, 6),
            "eg_p":          round(float(eg_p), 6),
            "spread":        spread,
            "cointegrated":  float(eg_p) < p_threshold,
        }
    except Exception:
        return {"cointegrated": False, "eg_p": 1.0}


def get_all_within_sector_pairs() -> List[Tuple[str, str, str]]:
    """Build list of (sym_a, sym_b, sector) within each sector."""
    import itertools
    pairs = []
    for sector, tickers in SECTOR_GROUPS.items():
        for a, b in itertools.combinations(tickers, 2):
            pairs.append((a, b, sector))
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
#  STAGE 2 — OU PARAMETER ESTIMATION
# ══════════════════════════════════════════════════════════════════════════════

def fit_ou_mle(spread: np.ndarray) -> dict:
    """
    MLE estimation of OU process: dX = theta*(mu - X)*dt + sigma*dW
    Uses discrete-time approximation:
    X_{t+1} = X_t + theta*(mu - X_t)*dt + sigma*sqrt(dt)*eps
    with dt = 1/252 (daily).
    """
    dt = 1.0 / 252.0
    n  = len(spread)
    if n < 20:
        return {"success": False}

    x0 = spread[:-1]
    x1 = spread[1:]

    def neg_log_likelihood(params):
        theta, mu, sigma = params
        if theta <= 0 or sigma <= 0:
            return 1e10
        e_x = np.exp(-theta * dt)
        cond_mean = x0 * e_x + mu * (1 - e_x)
        cond_var  = (sigma ** 2) * (1 - np.exp(-2 * theta * dt)) / (2 * theta)
        if cond_var <= 0:
            return 1e10
        ll = -0.5 * (np.log(2 * np.pi * cond_var) + (x1 - cond_mean) ** 2 / cond_var)
        return -np.sum(ll)

    # Initial guesses
    spread_mean = np.mean(spread)
    spread_std  = np.std(spread)
    theta0 = 10.0   # fast mean reversion
    mu0    = spread_mean
    sigma0 = spread_std * math.sqrt(2 * theta0)

    try:
        res = minimize(
            neg_log_likelihood,
            x0     = [theta0, mu0, sigma0],
            bounds = [(0.01, 500), (None, None), (1e-8, None)],
            method = "L-BFGS-B",
        )
        if not res.success and res.fun > 1e9:
            return {"success": False}

        theta, mu, sigma = res.x
        half_life = math.log(2) / max(theta, 1e-6)
        sigma_eq  = sigma / math.sqrt(max(2 * theta, 1e-8))

        return {
            "success":   True,
            "theta":     round(float(theta), 6),
            "mu":        round(float(mu), 8),
            "sigma":     round(float(sigma), 8),
            "half_life": round(half_life, 4),
            "sigma_eq":  round(float(sigma_eq), 8),
        }
    except Exception:
        return {"success": False}


def get_ou_thresholds(ou: dict) -> Tuple[float, float, float]:
    """
    Determine entry/exit/stop thresholds from OU params.
    Returns (entry_sigma_multiple, exit_sigma_multiple, stop_sigma_multiple).
    """
    half_life = ou["half_life"]
    if half_life < 3:
        entry_mult = 1.5
    elif half_life <= 7:
        entry_mult = 2.0
    else:
        entry_mult = 2.5
    return entry_mult, 0.5, 3.0


# ══════════════════════════════════════════════════════════════════════════════
#  BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def backtest_pair_fixed_z(
    y: pd.Series, x: pd.Series,
    entry_z: float = 2.0, exit_z: float = 0.5, stop_z: float = 4.0,
    cost_bps: float = 2.0,
) -> dict:
    """
    Raw-return pairs backtest with rolling z-score and fixed thresholds.
    Matches R23 methodology.
    """
    ya, xb = align_pair(y, x)
    if len(ya) < 252:
        return {}

    log_ratio = np.log(ya / xb)
    mean_r    = log_ratio.rolling(60, min_periods=30).mean()
    std_r     = log_ratio.rolling(60, min_periods=30).std().replace(0, np.nan)
    zscore    = (log_ratio - mean_r) / std_r

    return _run_zscore_backtest(ya, xb, zscore, entry_z, exit_z, stop_z, cost_bps)


def backtest_pair_residual_fixed(
    resid_y: pd.Series, resid_x: pd.Series,
    raw_y: pd.Series, raw_x: pd.Series,
    entry_z: float = 2.0, exit_z: float = 0.5, stop_z: float = 4.0,
    cost_bps: float = 2.0,
) -> dict:
    """
    Factor-residualized pairs backtest with fixed ±2σ thresholds (R29 v1).
    Spread is built from residual prices; execution uses raw prices.
    """
    # Align residual price series
    ry, rx = align_pair(resid_y, resid_x)
    if len(ry) < 252:
        return {}

    log_ratio = np.log(ry / rx)
    mean_r    = log_ratio.rolling(60, min_periods=30).mean()
    std_r     = log_ratio.rolling(60, min_periods=30).std().replace(0, np.nan)
    zscore    = (log_ratio - mean_r) / std_r

    # Use raw prices for actual P&L
    raw_ya, raw_xb = align_pair(raw_y, raw_x)
    # Align zscore with raw prices
    common = zscore.dropna().index.intersection(raw_ya.index).intersection(raw_xb.index)
    if len(common) < 100:
        return {}

    return _run_zscore_backtest(
        raw_ya.loc[common], raw_xb.loc[common],
        zscore.loc[common], entry_z, exit_z, stop_z, cost_bps
    )


def backtest_pair_ou(
    resid_y: pd.Series, resid_x: pd.Series,
    raw_y: pd.Series, raw_x: pd.Series,
    refit_window: int = 60,
    max_pairs: int = 10,
    cost_bps: float = 2.0,
) -> dict:
    """
    Full R29 v2: factor-residualized + OU-calibrated dynamic thresholds.
    Rolling OU re-fitting every 60 days.
    """
    ry, rx = align_pair(resid_y, resid_x)
    if len(ry) < 252:
        return {}

    # Get raw price returns aligned to residual series dates
    raw_ya, raw_xb = align_pair(raw_y, raw_x)
    common = ry.index.intersection(raw_ya.index).intersection(raw_xb.index)
    if len(common) < 252:
        return {}

    ry  = ry.loc[common]
    rx  = rx.loc[common]
    rya = raw_ya.loc[common]
    rxb = raw_xb.loc[common]

    # Compute spread from residual prices (OLS hedge ratio)
    x_c    = add_constant(rx.values)
    model  = OLS(ry.values, x_c).fit()
    beta   = float(model.params[1])
    alpha  = float(model.params[0])
    spread = ry - beta * rx - alpha

    # Build OU-driven signals with rolling refitting
    n = len(spread)
    position   = np.zeros(n)
    in_trade   = False
    direction  = 0
    ou_params  = {}
    last_refit = 0

    y_ret  = rya.pct_change().fillna(0).values
    x_ret  = rxb.pct_change().fillna(0).values
    spread_vals = spread.values

    for i in range(refit_window, n):
        # Re-fit OU every refit_window days
        if (i - last_refit) >= refit_window or not ou_params:
            window_spread = spread_vals[max(0, i - refit_window):i]
            ou_params = fit_ou_mle(window_spread)
            last_refit = i

        if not ou_params.get("success", False):
            position[i] = 0
            continue

        half_life = ou_params["half_life"]
        if half_life > 30:
            # Too slow — skip
            position[i] = 0
            if in_trade:
                in_trade, direction = False, 0
            continue

        ou_mu      = ou_params["mu"]
        sigma_eq   = ou_params["sigma_eq"]
        entry_mult, exit_mult, stop_mult = get_ou_thresholds(ou_params)

        entry_band = entry_mult * sigma_eq
        exit_band  = exit_mult  * sigma_eq
        stop_band  = stop_mult  * sigma_eq

        s = spread_vals[i]
        dev = s - ou_mu

        if not in_trade:
            if dev < -entry_band:        # spread below mean → long spread
                in_trade, direction = True, 1
            elif dev > entry_band:       # spread above mean → short spread
                in_trade, direction = True, -1
        else:
            if abs(dev) < exit_band:     # mean-reversion target reached
                in_trade, direction = False, 0
            elif abs(dev) > stop_band:   # stop-loss
                in_trade, direction = False, 0

        position[i] = direction

    # P&L calculation
    pos_series = pd.Series(position, index=common)
    y_ret_s    = pd.Series(y_ret, index=common)
    x_ret_s    = pd.Series(x_ret, index=common)

    spread_ret = (y_ret_s - x_ret_s) * pos_series.shift(1).fillna(0)
    trades     = pos_series.diff().abs().fillna(0)
    cost       = trades * (cost_bps / 10000) * 2
    strat_ret  = spread_ret - cost

    return _compute_metrics(strat_ret, pos_series)


def _run_zscore_backtest(
    ya: pd.Series, xb: pd.Series, zscore: pd.Series,
    entry_z: float, exit_z: float, stop_z: float,
    cost_bps: float,
) -> dict:
    """Execute z-score based pairs strategy and compute metrics."""
    n          = len(zscore)
    position   = pd.Series(0.0, index=zscore.index)
    in_trade   = False
    direction  = 0

    zscore_vals = zscore.squeeze().values  # ensure 1D array
    for i in range(1, n):
        z_raw = zscore_vals[i]
        if not np.isfinite(z_raw):
            position.iloc[i] = 0
            continue
        z = float(z_raw)
        if not in_trade:
            if z < -entry_z:
                in_trade, direction = True, 1
            elif z > entry_z:
                in_trade, direction = True, -1
            position.iloc[i] = 0
        else:
            if abs(z) < exit_z or abs(z) > stop_z:
                in_trade, direction = False, 0
            position.iloc[i] = direction

    # Align with prices
    common = position.index.intersection(ya.index).intersection(xb.index)
    pos    = position.loc[common]
    y_ret  = ya.loc[common].pct_change().fillna(0)
    x_ret  = xb.loc[common].pct_change().fillna(0)

    spread_ret = (y_ret - x_ret) * pos.shift(1).fillna(0)
    trades     = pos.diff().abs().fillna(0)
    cost       = trades * (cost_bps / 10000) * 2
    strat_ret  = spread_ret - cost

    return _compute_metrics(strat_ret, pos)


def _compute_metrics(strat_ret: pd.Series, position: pd.Series) -> dict:
    """Compute Sharpe, CAGR, max drawdown, trade stats."""
    if len(strat_ret) < 50 or strat_ret.std() == 0:
        return {}

    cum      = (1 + strat_ret).cumprod()
    raw      = float(cum.iloc[-1] - 1)
    n_years  = len(strat_ret) / 252
    cagr     = float((1 + raw) ** (1 / max(n_years, 0.1)) - 1) if raw > -1 else float("-inf")
    mu, std  = strat_ret.mean(), strat_ret.std()
    sharpe   = float(mu / std * math.sqrt(252)) if std > 0 else 0.0
    roll_max = cum.cummax()
    max_dd   = float(((cum - roll_max) / roll_max).min())

    # Trade counting
    trades_raw = position.diff().abs().fillna(0)
    n_trades   = int((trades_raw > 0.5).sum()) // 2

    # Average holding period
    in_pos      = (position != 0).astype(int)
    holds       = []
    cur_hold    = 0
    for v in in_pos:
        if v:
            cur_hold += 1
        elif cur_hold:
            holds.append(cur_hold)
            cur_hold = 0
    if cur_hold:
        holds.append(cur_hold)
    avg_hold = round(float(np.mean(holds)), 1) if holds else 0.0

    non_zero = strat_ret[strat_ret != 0]
    win_rate = float((non_zero > 0).mean() * 100) if len(non_zero) > 0 else 0.0

    return {
        "raw_return":    round(raw * 100, 2),
        "cagr":          round(cagr * 100, 2),
        "sharpe":        round(sharpe, 4),
        "max_drawdown":  round(max_dd * 100, 2),
        "n_trades":      n_trades,
        "avg_hold_days": avg_hold,
        "win_rate":      round(win_rate, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PORTFOLIO COMBINER
# ══════════════════════════════════════════════════════════════════════════════

def build_portfolio(pair_daily_returns: List[Tuple[str, pd.Series]], max_pairs: int = 10) -> dict:
    """Equal-weight multi-pair portfolio from top pairs by Sharpe."""
    if not pair_daily_returns:
        return {}

    pair_daily_returns = pair_daily_returns[:max_pairs]
    series_list = [r for _, r in pair_daily_returns]

    book     = pd.concat(series_list, axis=1).fillna(0)
    port_ret = book.mean(axis=1)

    cum      = (1 + port_ret).cumprod()
    raw      = float(cum.iloc[-1] - 1)
    n_years  = len(port_ret) / 252
    cagr     = float((1 + raw) ** (1 / max(n_years, 0.1)) - 1) if raw > -1 else float("-inf")
    mu, std  = port_ret.mean(), port_ret.std()
    sharpe   = float(mu / std * math.sqrt(252)) if std > 0 else 0.0
    roll_max = cum.cummax()
    max_dd   = float(((cum - roll_max) / roll_max).min())

    return {
        "sharpe":       round(sharpe, 4),
        "cagr":         round(cagr * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "n_pairs":      len(pair_daily_returns),
        "pairs":        [name for name, _ in pair_daily_returns],
    }


def pair_daily_returns_fixed(
    ya: pd.Series, xb: pd.Series,
    entry_z: float = 2.0, exit_z: float = 0.5, stop_z: float = 4.0,
    cost_bps: float = 2.0,
) -> Optional[pd.Series]:
    """Get daily return series for a pair using fixed z-score method."""
    log_ratio = np.log(ya / xb)
    mean_r    = log_ratio.rolling(60, min_periods=30).mean()
    std_r     = log_ratio.rolling(60, min_periods=30).std().replace(0, np.nan)
    zscore    = (log_ratio - mean_r) / std_r

    n         = len(zscore)
    position  = pd.Series(0.0, index=zscore.index)
    in_trade  = False
    direction = 0

    for i in range(1, n):
        z = float(zscore.iloc[i])
        if math.isnan(z):
            position.iloc[i] = 0
            continue
        if not in_trade:
            if z < -entry_z:
                in_trade, direction = True, 1
            elif z > entry_z:
                in_trade, direction = True, -1
            position.iloc[i] = 0
        else:
            if abs(z) < exit_z or abs(z) > stop_z:
                in_trade, direction = False, 0
            position.iloc[i] = direction

    y_ret      = ya.pct_change().fillna(0)
    x_ret      = xb.pct_change().fillna(0)
    trades     = position.diff().abs().fillna(0)
    cost       = trades * (cost_bps / 10000) * 2
    return (y_ret - x_ret) * position.shift(1).fillna(0) - cost


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN BACKTEST RUNNERS
# ══════════════════════════════════════════════════════════════════════════════

def run_baseline(prices: dict, all_pairs: list) -> Tuple[dict, List[dict]]:
    """
    Baseline: raw prices, fixed ±2σ z-score thresholds.
    Replicates R23 methodology for comparison.
    """
    print("\n  Running Baseline (raw returns + fixed ±2σ)...")
    pair_results = []
    pair_returns = []

    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        # Test cointegration first
        ct = test_cointegration(ya, xb)
        if not ct["cointegrated"]:
            continue

        r = backtest_pair_fixed_z(ya, xb, entry_z=2.0)
        if r and r.get("sharpe", 0) > 0:
            r.update({"sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                      "variant": "baseline", "eg_p": ct["eg_p"]})
            pair_results.append(r)

            # Build daily returns for portfolio
            ret = pair_daily_returns_fixed(ya, xb)
            if ret is not None:
                pair_returns.append((f"{sym_a}/{sym_b}", ret))

    # Sort by Sharpe and take top 10
    pair_results.sort(key=lambda x: x.get("sharpe", 0), reverse=True)
    top10_names = set(r["sym_a"] + "/" + r["sym_b"] for r in pair_results[:10])
    top10_returns = [(n, r) for n, r in pair_returns if n in top10_names]

    portfolio = build_portfolio(top10_returns, max_pairs=10)
    print(f"    Cointegrated pairs found: {len(pair_results)}")
    print(f"    Portfolio Sharpe: {portfolio.get('sharpe', 0):.4f}")

    return portfolio, pair_results


def run_r29v1(prices: dict, residual_prices: dict, all_pairs: list) -> Tuple[dict, List[dict]]:
    """
    R29 v1: Factor-residualized returns + fixed ±2σ thresholds.
    """
    print("\n  Running R29 v1 (residualized + fixed ±2σ)...")
    pair_results = []
    pair_returns = []

    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in residual_prices or sym_b not in residual_prices:
            continue
        if sym_a not in prices or sym_b not in prices:
            continue

        ry, rx = align_pair(residual_prices[sym_a], residual_prices[sym_b])
        if len(ry) < 252:
            continue

        # Cointegration test on residual prices
        ct = test_cointegration(ry, rx)
        if not ct["cointegrated"]:
            continue

        r = backtest_pair_residual_fixed(
            residual_prices[sym_a], residual_prices[sym_b],
            prices[sym_a], prices[sym_b],
            entry_z=2.0
        )
        if r and r.get("sharpe", 0) > 0:
            r.update({"sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                      "variant": "r29v1", "eg_p": ct["eg_p"]})
            pair_results.append(r)

            # Build daily returns for portfolio
            rya, rxb = align_pair(prices[sym_a], prices[sym_b])
            spread_y, spread_x = align_pair(residual_prices[sym_a], residual_prices[sym_b])
            common = spread_y.index.intersection(rya.index).intersection(rxb.index)
            if len(common) > 100:
                log_ratio = np.log(spread_y.loc[common] / spread_x.loc[common])
                mean_r    = log_ratio.rolling(60, min_periods=30).mean()
                std_r     = log_ratio.rolling(60, min_periods=30).std().replace(0, np.nan)
                zscore    = (log_ratio - mean_r) / std_r

                pos = pd.Series(0.0, index=zscore.index)
                in_tr, di = False, 0
                z_vals = zscore.squeeze().values
                for i in range(1, len(zscore)):
                    z_raw = z_vals[i]
                    if not np.isfinite(z_raw):
                        pos.iloc[i] = 0; continue
                    z = float(z_raw)
                    if not in_tr:
                        if z < -2.0: in_tr, di = True, 1
                        elif z > 2.0: in_tr, di = True, -1
                        pos.iloc[i] = 0
                    else:
                        if abs(z) < 0.5 or abs(z) > 4.0: in_tr, di = False, 0
                        pos.iloc[i] = di

                y_r = rya.loc[common].pct_change().fillna(0)
                x_r = rxb.loc[common].pct_change().fillna(0)
                tr  = pos.diff().abs().fillna(0)
                ret = (y_r - x_r) * pos.shift(1).fillna(0) - tr * (2.0/10000) * 2
                pair_returns.append((f"{sym_a}/{sym_b}", ret))

    pair_results.sort(key=lambda x: x.get("sharpe", 0), reverse=True)
    top10_names = set(r["sym_a"] + "/" + r["sym_b"] for r in pair_results[:10])
    top10_returns = [(n, r) for n, r in pair_returns if n in top10_names]

    portfolio = build_portfolio(top10_returns, max_pairs=10)
    print(f"    Cointegrated pairs found: {len(pair_results)}")
    print(f"    Portfolio Sharpe: {portfolio.get('sharpe', 0):.4f}")

    return portfolio, pair_results


def run_r29v2(prices: dict, residual_prices: dict, all_pairs: list) -> Tuple[dict, List[dict]]:
    """
    R29 v2: Full spec — factor-residualized + OU-calibrated dynamic thresholds.
    """
    print("\n  Running R29 v2 (residualized + OU-calibrated thresholds)...")
    pair_results = []
    pair_returns = []

    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in residual_prices or sym_b not in residual_prices:
            continue
        if sym_a not in prices or sym_b not in prices:
            continue

        ry, rx = align_pair(residual_prices[sym_a], residual_prices[sym_b])
        if len(ry) < 252:
            continue

        # Cointegration test on residual prices
        ct = test_cointegration(ry, rx)
        if not ct["cointegrated"]:
            continue

        r = backtest_pair_ou(
            residual_prices[sym_a], residual_prices[sym_b],
            prices[sym_a], prices[sym_b],
            refit_window=60,
        )
        if r and r.get("sharpe", 0) > 0:
            r.update({"sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                      "variant": "r29v2", "eg_p": ct["eg_p"]})
            pair_results.append(r)

            # Build daily return series for portfolio
            rya, rxb = align_pair(prices[sym_a], prices[sym_b])
            spread_y, spread_x = align_pair(residual_prices[sym_a], residual_prices[sym_b])
            common = spread_y.index.intersection(rya.index).intersection(rxb.index)
            if len(common) > 252:
                sy = spread_y.loc[common]
                sx = spread_x.loc[common]
                x_c    = add_constant(sx.values)
                model2 = OLS(sy.values, x_c).fit()
                beta2  = float(model2.params[1])
                alpha2 = float(model2.params[0])
                spread = sy - beta2 * sx - alpha2

                n = len(spread)
                pos    = np.zeros(n)
                in_tr  = False; di = 0
                ou_p   = {}; last_fit = 0

                for i in range(60, n):
                    if (i - last_fit) >= 60 or not ou_p:
                        ou_p = fit_ou_mle(spread.values[max(0, i-60):i])
                        last_fit = i
                    if not ou_p.get("success") or ou_p["half_life"] > 30:
                        pos[i] = 0
                        if in_tr: in_tr, di = False, 0
                        continue
                    em, exm, stm = get_ou_thresholds(ou_p)
                    dev = spread.values[i] - ou_p["mu"]
                    se  = ou_p["sigma_eq"]
                    if not in_tr:
                        if dev < -em * se: in_tr, di = True, 1
                        elif dev > em * se: in_tr, di = True, -1
                    else:
                        if abs(dev) < exm * se or abs(dev) > stm * se:
                            in_tr, di = False, 0
                    pos[i] = di

                pos_s = pd.Series(pos, index=common)
                y_r   = rya.loc[common].pct_change().fillna(0)
                x_r   = rxb.loc[common].pct_change().fillna(0)
                tr    = pos_s.diff().abs().fillna(0)
                ret   = (y_r - x_r) * pos_s.shift(1).fillna(0) - tr * (2.0/10000) * 2
                pair_returns.append((f"{sym_a}/{sym_b}", ret))

    pair_results.sort(key=lambda x: x.get("sharpe", 0), reverse=True)
    top10_names = set(r["sym_a"] + "/" + r["sym_b"] for r in pair_results[:10])
    top10_returns = [(n, r) for n, r in pair_returns if n in top10_names]

    portfolio = build_portfolio(top10_returns, max_pairs=10)
    print(f"    Cointegrated pairs found: {len(pair_results)}")
    print(f"    Portfolio Sharpe: {portfolio.get('sharpe', 0):.4f}")

    return portfolio, pair_results


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("ROUND 29 — Equity Pairs Trading: Factor Residualization + OU Thresholds")
    print(f"Universe: {len(UNIVERSE)} stocks | Period: {START_DATE} to {END_DATE}")
    print("=" * 72)

    # 1. Load prices
    print("\n[1] Loading price data...")
    prices = fetch_all_prices()
    available = [s for s in UNIVERSE if s in prices]
    print(f"  Universe: {len(available)}/{len(UNIVERSE)} stocks loaded")
    sector_avail = [s for s in SECTOR_ETFS if s in prices]
    print(f"  Sector ETFs: {len(sector_avail)}/{len(SECTOR_ETFS)} loaded")

    # 2. Build factor-residualized prices
    print("\n[2] Building factor-residualized prices (rolling 60-day OLS)...")
    residual_prices = build_residual_prices(prices, window=60)
    print(f"  Residualized: {len(residual_prices)} stocks")

    # 3. Get all within-sector pairs
    all_pairs = get_all_within_sector_pairs()
    print(f"\n[3] Pair universe: {len(all_pairs)} within-sector pairs")

    # 4. Run three variants
    print("\n[4] Running backtests...")

    baseline_portfolio, baseline_pairs = run_baseline(prices, all_pairs)
    v1_portfolio, v1_pairs             = run_r29v1(prices, residual_prices, all_pairs)
    v2_portfolio, v2_pairs             = run_r29v2(prices, residual_prices, all_pairs)

    # 5. Compile results
    print("\n[5] Results Summary")
    print("=" * 72)

    variants = {
        "baseline": {"portfolio": baseline_portfolio, "pairs": baseline_pairs},
        "r29v1":    {"portfolio": v1_portfolio,        "pairs": v1_pairs},
        "r29v2":    {"portfolio": v2_portfolio,        "pairs": v2_pairs},
    }

    for name, data in variants.items():
        p = data["portfolio"]
        label = {
            "baseline": "Baseline (raw + fixed ±2σ)",
            "r29v1":    "R29 v1 (residualized + fixed ±2σ)",
            "r29v2":    "R29 v2 (residualized + OU thresholds)",
        }[name]
        print(f"\n  {label}:")
        print(f"    Portfolio Sharpe: {p.get('sharpe', 'N/A')}")
        print(f"    CAGR:             {p.get('cagr', 'N/A')}%")
        print(f"    Max Drawdown:     {p.get('max_drawdown', 'N/A')}%")
        print(f"    Pairs in book:    {p.get('n_pairs', 0)}")

    # Top 5 pairs by Sharpe across all variants
    all_pair_results = baseline_pairs + v1_pairs + v2_pairs
    if all_pair_results:
        df_all = pd.DataFrame(all_pair_results)
        # Deduplicate by pair + variant
        df_all["pair_key"] = df_all["sym_a"] + "/" + df_all["sym_b"] + "_" + df_all["variant"]
        df_all = df_all.drop_duplicates("pair_key")
        top5   = df_all.nlargest(5, "sharpe")

        print("\n  TOP 5 PAIRS BY SHARPE (all variants):")
        print(f"  {'Pair':<16} {'Variant':<10} {'Sector':<14} {'Sharpe':>8} {'CAGR%':>7} {'MaxDD%':>8} {'Trades':>7}")
        print("  " + "-" * 76)
        for _, row in top5.iterrows():
            pair = f"{row['sym_a']}/{row['sym_b']}"
            print(f"  {pair:<16} {row['variant']:<10} {row['sector']:<14} "
                  f"{row['sharpe']:>8.4f} {row.get('cagr',0):>7.2f}% "
                  f"{row.get('max_drawdown',0):>8.2f}% {row.get('n_trades',0):>7}")

    # 6. Save results JSON
    results_out = {
        "round": 29,
        "timestamp": datetime.now().isoformat(),
        "date_range": {"start": START_DATE, "end": END_DATE},
        "universe": UNIVERSE,
        "variants": {
            name: {
                "portfolio": data["portfolio"],
                "top_pairs": sorted(
                    data["pairs"],
                    key=lambda x: x.get("sharpe", 0), reverse=True
                )[:20],
                "n_cointegrated": len(data["pairs"]),
            }
            for name, data in variants.items()
        },
        "comparison_r23_sharpe": 0.964,
    }

    results_path = ROUNDS_DIR / "r29_pairs_results.json"
    with open(results_path, "w") as f:
        json.dump(results_out, f, indent=2, default=str)
    print(f"\n  Saved results → {results_path}")

    # 7. Build markdown report
    write_report(variants, all_pair_results, results_out)

    print("\n  Done.")
    return results_out


def write_report(variants: dict, all_pair_results: list, results_out: dict):
    """Write R29_PAIRS_REPORT.md."""
    report_path = ROOT / "R29_PAIRS_REPORT.md"

    bl  = variants["baseline"]["portfolio"]
    v1  = variants["r29v1"]["portfolio"]
    v2  = variants["r29v2"]["portfolio"]

    # Top 5 pairs
    if all_pair_results:
        df_all = pd.DataFrame(all_pair_results)
        df_all["pair_key"] = df_all["sym_a"] + "/" + df_all["sym_b"] + "_" + df_all["variant"]
        df_all = df_all.drop_duplicates("pair_key")
        top5_df = df_all.nlargest(5, "sharpe")
        top5_rows = []
        for _, row in top5_df.iterrows():
            top5_rows.append(
                f"| {row['sym_a']}/{row['sym_b']} | {row['variant']} | {row['sector']} "
                f"| {row['sharpe']:.4f} | {row.get('cagr', 0):.2f}% "
                f"| {row.get('max_drawdown', 0):.2f}% | {row.get('n_trades', 0)} "
                f"| {row.get('avg_hold_days', 0):.1f} |"
            )
        top5_str = "\n".join(top5_rows)
    else:
        top5_str = "| No results | | | | | | | |"

    # Analysis
    bl_sharpe = bl.get("sharpe", 0.0)
    v1_sharpe = v1.get("sharpe", 0.0)
    v2_sharpe = v2.get("sharpe", 0.0)
    r23_sharpe = 0.964

    resid_lift = v1_sharpe - bl_sharpe
    ou_lift    = v2_sharpe - v1_sharpe
    total_lift = v2_sharpe - bl_sharpe

    resid_conclusion = "YES — factor residualization improves Sharpe" if resid_lift > 0.05 else (
        "MARGINAL improvement" if resid_lift > 0 else "NO improvement from residualization"
    )
    ou_conclusion = "YES — OU calibration improves over fixed thresholds" if ou_lift > 0.05 else (
        "MARGINAL improvement" if ou_lift > 0 else "NO improvement from OU calibration"
    )
    vs_r23 = "BEATS" if v2_sharpe > r23_sharpe else "BELOW"

    report = f"""# Round 29 — Equity Pairs Trading: Factor Residualization + OU Thresholds

**Date:** {datetime.now().strftime("%Y-%m-%d")}
**Period:** {START_DATE} to {END_DATE}
**Universe:** {len(UNIVERSE)} Fortune 100 stocks

---

## Results Table (Portfolio-Level)

| Variant | Description | Sharpe | CAGR | Max Drawdown | Pairs |
|---------|-------------|--------|------|--------------|-------|
| Baseline | Raw returns + fixed ±2σ z-score | {bl_sharpe:.4f} | {bl.get('cagr', 0):.2f}% | {bl.get('max_drawdown', 0):.2f}% | {bl.get('n_pairs', 0)} |
| R29 v1 | Residualized returns + fixed ±2σ | {v1_sharpe:.4f} | {v1.get('cagr', 0):.2f}% | {v1.get('max_drawdown', 0):.2f}% | {v1.get('n_pairs', 0)} |
| R29 v2 (Full) | Residualized + OU thresholds | {v2_sharpe:.4f} | {v2.get('cagr', 0):.2f}% | {v2.get('max_drawdown', 0):.2f}% | {v2.get('n_pairs', 0)} |
| **R23 (previous best)** | Multi-pair book | **0.9640** | — | — | 10 |

---

## Key Questions

### Does factor residualization help?
**{resid_conclusion}**
- Baseline Sharpe: {bl_sharpe:.4f}
- R29 v1 Sharpe:  {v1_sharpe:.4f}
- Lift from residualization: {resid_lift:+.4f}

### Does OU calibration improve over fixed thresholds?
**{ou_conclusion}**
- R29 v1 (fixed ±2σ) Sharpe: {v1_sharpe:.4f}
- R29 v2 (OU thresholds) Sharpe: {v2_sharpe:.4f}
- Lift from OU calibration: {ou_lift:+.4f}

### Comparison to leaderboard (R23: Sharpe 0.964)
R29 v2 {vs_r23} R23 benchmark: **{v2_sharpe:.4f}** vs 0.9640
Total lift over baseline: {total_lift:+.4f}

---

## Top 5 Pairs by Sharpe

| Pair | Variant | Sector | Sharpe | CAGR | Max Drawdown | Trades | Avg Hold (days) |
|------|---------|--------|--------|------|--------------|--------|-----------------|
{top5_str}

---

## Cointegrated Pairs Count

| Variant | Cointegrated Pairs Found |
|---------|--------------------------|
| Baseline | {len(variants['baseline']['pairs'])} |
| R29 v1 | {len(variants['r29v1']['pairs'])} |
| R29 v2 | {len(variants['r29v2']['pairs'])} |

---

## Methodology Notes

- **Stage 0**: Rolling 60-day OLS on (SPY returns, sector ETF returns) for each stock; residuals used as factor-orthogonalized returns
- **Stage 1**: Engle-Granger cointegration test (p < 0.05) applied to residual-price series
- **Stage 2**: OU MLE fitting (theta, mu, sigma) via discrete-time L-BFGS-B; half-life determines entry threshold multiplier
  - half_life < 3d → entry ±1.5σ_eq
  - half_life 3–7d → entry ±2.0σ_eq
  - half_life > 7d → entry ±2.5σ_eq
  - Skip if half_life > 30d (too slow)
- **Stage 3**: Long/short spread execution with stop at ±3σ_eq; OU re-fit every 60 days; portfolio = equal-weight top 10 pairs

---

## Leaderboard Update

| Round | Strategy | Sharpe | Notes |
|-------|----------|--------|-------|
| R27 | Div Raise ≥10% hold-40d | 4.403 | Best overall |
| R27 | Div Raise ≥5% hold-40d | 3.400 | |
| R29 v2 (this) | Pairs + Residualization + OU | {v2_sharpe:.4f} | Full pipeline |
| R29 v1 | Pairs + Residualization | {v1_sharpe:.4f} | |
| R23 | Multi-pair stat arb book | 0.964 | Previous pairs best |
| R29 Baseline | Raw pairs + fixed ±2σ | {bl_sharpe:.4f} | |

*Data source: Yahoo Finance via yfinance. Transaction costs: 2 bps per leg.*
"""

    with open(report_path, "w") as f:
        f.write(report)
    print(f"  Saved report → {report_path}")


if __name__ == "__main__":
    main()
