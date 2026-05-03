"""
base_harness.py — NanoClaw Trading Eval Framework v1.0
=======================================================
Base module for all eval harnesses (R29+). Provides:
  - TradeLogger: standardized trade record writer
  - Shared data fetching with disk cache
  - Black-Scholes pricing functions
  - Volatility helpers
  - Regime calendar (downloaded from SPY/VIX)

Usage in a new harness:
    from framework.base_harness import TradeLogger, fetch_data, bs_call, bs_put, \
                                        realized_vol, iv_estimate, iv_rank

    logger = TradeLogger(round_num=29, strategy='my_strategy', category='options')

    # Inside your backtest loop:
    logger.log(
        ticker     = 'XOM',
        entry_date = entry_dt,
        exit_date  = exit_dt,
        return_pct = pnl_pct,
        hold_days  = n_days,
        direction  = 'short_put',
        params     = {'iv_rank_threshold': 50, 'wing_width': 0.05},
        # any extra kwargs become additional fields
        iv_rank_at_entry = current_ivr,
        premium_collected = net_credit / S,
    )

    logger.save()   # writes trade_logs/{strategy}_r{round:02d}.trades.jsonl

The analysis layer then reads that file and computes all metrics.
NEVER compute Sharpe/Sortino/etc inside a harness — that's the analysis layer's job.
"""

import os
import sys
import json
import time
import subprocess
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, date
from pathlib import Path
from scipy.stats import norm

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────

FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
CACHE_DIR     = EVAL_DIR / 'cache'
TRADE_LOG_DIR = EVAL_DIR / 'trade_logs'

CACHE_DIR.mkdir(exist_ok=True)
TRADE_LOG_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────
# DEPENDENCY BOOTSTRAP
# ─────────────────────────────────────────────

def ensure_deps():
    """Bootstrap pip and install required packages if missing."""
    for pkg in ['yfinance', 'scipy', 'numpy', 'pandas']:
        try:
            __import__(pkg.replace('-', '_'))
        except ImportError:
            try:
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', pkg,
                    '--break-system-packages', '--quiet'
                ])
            except Exception:
                # pip not installed — bootstrap it first
                import urllib.request
                pip_url = 'https://bootstrap.pypa.io/get-pip.py'
                with urllib.request.urlopen(pip_url) as r:
                    pip_src = r.read()
                exec(compile(pip_src, '<get-pip>', 'exec'), {'__name__': '__main__'})
                subprocess.check_call([
                    sys.executable, '-m', 'pip', 'install', pkg,
                    '--break-system-packages', '--quiet'
                ])

# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_data(tickers: list, start: str, end: str, retries: int = 3) -> dict:
    """
    Download OHLCV data for a list of tickers. Caches to disk by ticker+period.
    Returns dict of {ticker: DataFrame}.
    """
    import yfinance as yf
    all_data = {}
    for ticker in tickers:
        safe_ticker = ticker.replace('^', 'idx_')
        cache_file  = CACHE_DIR / f"{safe_ticker}_{start}_{end}.pkl"
        if cache_file.exists():
            try:
                df = pd.read_pickle(cache_file)
                if len(df) > 50:
                    all_data[ticker] = df
                    continue
            except Exception:
                pass
        for attempt in range(retries):
            try:
                df = yf.download(ticker, start=start, end=end,
                                 progress=False, auto_adjust=True)
                if df is not None and len(df) > 50:
                    df.to_pickle(cache_file)
                    all_data[ticker] = df
                    break
                time.sleep(0.5)
            except Exception as e:
                if attempt == retries - 1:
                    print(f"  [fetch] Failed {ticker}: {e}")
                time.sleep(1)
    return all_data


def get_close(prices: pd.DataFrame) -> pd.Series:
    """Extract clean Close series from a yfinance DataFrame."""
    c = prices['Close']
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    return c.squeeze().dropna()

# ─────────────────────────────────────────────
# BLACK-SCHOLES
# ─────────────────────────────────────────────

RF = 0.045   # default risk-free rate

def bs_call(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    """Black-Scholes European call price. T in years."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return float(S * norm.cdf(d1) - K * np.exp(-r*T) * norm.cdf(d2))

def bs_put(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    """Black-Scholes European put price. T in years."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    return float(K * np.exp(-r*T) * norm.cdf(-d2) - S * norm.cdf(-d1))

def bs_delta_call(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    if T <= 0 or sigma <= 0:
        return 1.0 if S > K else 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return float(norm.cdf(d1))

def bs_delta_put(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    return bs_delta_call(S, K, T, sigma, r) - 1.0

def bs_gamma(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    """Gamma (same for calls and puts)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))

def bs_theta_call(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    """Daily theta decay for a call (negative = time decay cost)."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    theta = (-(S * norm.pdf(d1) * sigma) / (2*np.sqrt(T))
             - r * K * np.exp(-r*T) * norm.cdf(d2))
    return float(theta / 365)  # per calendar day

def bs_vega(S: float, K: float, T: float, sigma: float, r: float = RF) -> float:
    """Vega (same for calls and puts). Per 1% change in vol."""
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return float(S * norm.pdf(d1) * np.sqrt(T) * 0.01)

# ─────────────────────────────────────────────
# VOLATILITY HELPERS
# ─────────────────────────────────────────────

IV_PREMIUM = 0.03   # Persistent VRP: IV is ~3% above realized vol

def realized_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Annualized realized volatility (rolling log-return std)."""
    log_ret = np.log(close / close.shift(1)).dropna()
    return log_ret.rolling(window).std() * np.sqrt(252)

def iv_estimate(close: pd.Series, window: int = 20,
                premium: float = IV_PREMIUM) -> pd.Series:
    """
    Proxy for implied vol: realized_vol * (1 + premium).
    Reflects that IV is systematically above realized (VRP).
    """
    return realized_vol(close, window) * (1 + premium)

def iv_rank(iv_series: pd.Series, lookback: int = 252) -> pd.Series:
    """
    Percentile rank of current IV vs trailing `lookback` days.
    0 = historically cheap options. 100 = historically expensive.
    """
    return iv_series.rolling(lookback).rank(pct=True) * 100

# ─────────────────────────────────────────────
# REGIME CALENDAR
# ─────────────────────────────────────────────

REGIME_CRISIS    = 'crisis'       # VIX monthly avg > 35
REGIME_BEAR      = 'bear'         # SPY 3-month return < -8%
REGIME_HIGH_VOL  = 'high_vol'     # VIX 20-35
REGIME_BULL      = 'bull'         # VIX < 20 AND SPY 3m > 0
REGIME_LOW_VOL   = 'low_vol_bull' # VIX < 15 (calm bull)
REGIME_UNKNOWN   = 'unknown'


def build_regime_calendar(start: str, end: str) -> pd.DataFrame:
    """
    Download SPY and ^VIX, label each calendar month with a macro regime.

    Returns a DataFrame indexed by month-start date with columns:
      regime, spy_3m_ret, vix_avg, spy_ret_1m
    """
    raw = fetch_data(['SPY', '^VIX'], start, end)
    if 'SPY' not in raw or '^VIX' not in raw:
        return pd.DataFrame()

    spy_close = get_close(raw['SPY']).resample('MS').last()
    vix_close = get_close(raw['^VIX']).resample('MS').mean()

    df = pd.DataFrame({'spy': spy_close, 'vix': vix_close}).dropna()
    df['spy_ret_1m'] = df['spy'].pct_change()
    df['spy_3m_ret'] = df['spy'].pct_change(3)

    def _label(row):
        vix = row['vix']
        r3  = row['spy_3m_ret'] if not np.isnan(row['spy_3m_ret']) else 0
        if vix > 35:
            return REGIME_CRISIS
        elif r3 < -0.08:
            return REGIME_BEAR
        elif vix > 20:
            return REGIME_HIGH_VOL
        elif vix < 15:
            return REGIME_LOW_VOL
        else:
            return REGIME_BULL

    df['regime'] = df.apply(_label, axis=1)
    df = df.rename(columns={'vix': 'vix_avg'})
    return df[['regime', 'spy_3m_ret', 'vix_avg', 'spy_ret_1m']]


def get_trade_regime(entry_date: str, calendar: pd.DataFrame) -> str:
    """Look up the regime for a given trade entry date."""
    if calendar is None or len(calendar) == 0:
        return REGIME_UNKNOWN
    try:
        dt = pd.Timestamp(entry_date).to_period('M').to_timestamp()
        if dt in calendar.index:
            return calendar.loc[dt, 'regime']
        # fallback: nearest month
        nearest = calendar.index[calendar.index.searchsorted(dt)]
        return calendar.loc[nearest, 'regime'] if nearest in calendar.index else REGIME_UNKNOWN
    except Exception:
        return REGIME_UNKNOWN

# ─────────────────────────────────────────────
# TRADE LOGGER
# ─────────────────────────────────────────────

class TradeLogger:
    """
    Standardized trade record collector.

    Usage:
        logger = TradeLogger(round_num=29, strategy='bull_put_spread',
                             category='options')
        logger.log(ticker='XOM', entry_date='2022-06-01', exit_date='2022-07-01',
                   return_pct=0.182, hold_days=30, direction='short_put',
                   params={'iv_rank_threshold': 50},
                   iv_rank_at_entry=72.3)
        logger.save()   # → trade_logs/bull_put_spread_r29.trades.jsonl
    """

    REQUIRED = {'ticker', 'entry_date', 'exit_date', 'return_pct', 'hold_days'}

    def __init__(self, round_num: int, strategy: str, category: str = ''):
        self.round_num = round_num
        self.strategy  = strategy
        self.category  = category
        self.records   = []
        self._out_path = TRADE_LOG_DIR / f"{strategy}_r{round_num:02d}.trades.jsonl"

    def log(self, **kwargs) -> None:
        """Record a single trade. All kwargs become fields in the JSON record."""
        missing = self.REQUIRED - set(kwargs.keys())
        if missing:
            raise ValueError(f"TradeLogger.log() missing required fields: {missing}")

        record = {
            'round':    self.round_num,
            'strategy': self.strategy,
            'category': self.category,
        }
        record.update(kwargs)

        # Normalize dates to ISO strings
        for key in ('entry_date', 'exit_date', 'expiry_date'):
            if key in record and record[key] is not None:
                v = record[key]
                if hasattr(v, 'strftime'):
                    record[key] = v.strftime('%Y-%m-%d')
                else:
                    record[key] = str(v)[:10]

        # Normalize floats
        for key, val in record.items():
            if isinstance(val, (np.floating, np.integer)):
                record[key] = float(val)

        self.records.append(record)

    def save(self, verbose: bool = True) -> str:
        """Write all records to JSONL file. Returns path."""
        with open(self._out_path, 'w') as f:
            for rec in self.records:
                f.write(json.dumps(rec, default=str) + '\n')
        if verbose:
            print(f"  [TradeLogger] {len(self.records)} trades → {self._out_path}")
        return str(self._out_path)

    def load_existing(self) -> int:
        """Load records from existing file (for appending). Returns count loaded."""
        if not self._out_path.exists():
            return 0
        with open(self._out_path) as f:
            self.records = [json.loads(line) for line in f if line.strip()]
        return len(self.records)

    def __len__(self):
        return len(self.records)

    def __repr__(self):
        return (f"TradeLogger(round={self.round_num}, strategy={self.strategy!r}, "
                f"n_trades={len(self.records)})")
