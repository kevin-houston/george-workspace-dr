#!/usr/bin/env python3
"""
Securities Trading Eval Harness — Autoresearch Edition
Inspired by Karpathy's autoresearch methodology:
  Generate → Test → Analyze → Improve → Repeat

Round structure:
  Each round runs all registered strategies against all tickers.
  Results are saved per-round. Insights are generated automatically
  to guide parameter refinement in future rounds.

Configuration:
  Tickers  : Fortune 100 (publicly traded subset, ~78 companies)
  History  : 15 years
  Metric   : Raw Return
  Positions: Long, Short, Long/Short (all three evaluated per strategy)

Usage:
  PYTHONPATH=/tmp/eval_deps python3 harness.py
  PYTHONPATH=/tmp/eval_deps python3 harness.py --symbols AAPL MSFT GOOGL
  PYTHONPATH=/tmp/eval_deps python3 harness.py --strategies momentum mean_reversion
  PYTHONPATH=/tmp/eval_deps python3 harness.py --list
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: pip install yfinance pandas numpy --target=/tmp/eval_deps")
    print("Then: PYTHONPATH=/tmp/eval_deps python3 harness.py")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

# ── Fortune 100 — publicly traded subset (~78 tickers) ───────────────────────
# Source: Fortune 100 2025. Private companies excluded (State Farm, Koch,
# Cargill, USAA, New York Life, Liberty Mutual, Nationwide, TIAA, Publix).

FORTUNE_100 = {
    # Technology
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "GOOGL": "Alphabet",
    "META":  "Meta Platforms",
    "AMZN":  "Amazon",
    "INTC":  "Intel",
    "CSCO":  "Cisco",
    "IBM":   "IBM",
    "HPQ":   "HP Inc",
    "HPE":   "Hewlett Packard Enterprise",
    "ORCL":  "Oracle",
    # Healthcare
    "UNH":   "UnitedHealth Group",
    "CVS":   "CVS Health",
    "MCK":   "McKesson",
    "COR":   "Cencora (AmerisourceBergen)",
    "CI":    "Cigna",
    "ELV":   "Elevance Health",
    "CAH":   "Cardinal Health",
    "HUM":   "Humana",
    "JNJ":   "Johnson & Johnson",
    "PFE":   "Pfizer",
    "MRK":   "Merck",
    "ABT":   "Abbott Laboratories",
    "BMY":   "Bristol-Myers Squibb",
    "LLY":   "Eli Lilly",
    "TMO":   "Thermo Fisher",
    # Financial
    "JPM":   "JPMorgan Chase",
    "BAC":   "Bank of America",
    "WFC":   "Wells Fargo",
    "C":     "Citigroup",
    "GS":    "Goldman Sachs",
    "MS":    "Morgan Stanley",
    "AXP":   "American Express",
    "MET":   "MetLife",
    "PRU":   "Prudential Financial",
    "AIG":   "AIG",
    "COF":   "Capital One",
    "AFL":   "Aflac",
    "ALL":   "Allstate",
    # Energy
    "XOM":   "Exxon Mobil",
    "CVX":   "Chevron",
    "MPC":   "Marathon Petroleum",
    "VLO":   "Valero Energy",
    "PSX":   "Phillips 66",
    "COP":   "ConocoPhillips",
    "HAL":   "Halliburton",
    # Retail / Consumer Staples
    "WMT":   "Walmart",
    "COST":  "Costco",
    "HD":    "Home Depot",
    "TGT":   "Target",
    "KR":    "Kroger",
    "LOW":   "Lowe's",
    "WBA":   "Walgreens",
    "BBY":   "Best Buy",
    "DG":    "Dollar General",
    "SYY":   "Sysco",
    # Industrials / Defense
    "BA":    "Boeing",
    "LMT":   "Lockheed Martin",
    "RTX":   "RTX (Raytheon)",
    "NOC":   "Northrop Grumman",
    "GD":    "General Dynamics",
    "GE":    "General Electric",
    "CAT":   "Caterpillar",
    "DE":    "Deere & Co",
    "UPS":   "UPS",
    "FDX":   "FedEx",
    "UNP":   "Union Pacific",
    # Automotive
    "F":     "Ford Motor",
    "GM":    "General Motors",
    "TSLA":  "Tesla",
    # Media / Telecom
    "CMCSA": "Comcast",
    "T":     "AT&T",
    "VZ":    "Verizon",
    "DIS":   "Walt Disney",
    "NFLX":  "Netflix",
    # Consumer Goods
    "PG":    "Procter & Gamble",
    "PEP":   "PepsiCo",
    "KO":    "Coca-Cola",
    "MO":    "Altria",
    "MDLZ":  "Mondelez",
    "TSN":   "Tyson Foods",
    "ADM":   "Archer Daniels Midland",
    # Diversified / Other
    "MMM":   "3M",
    "DOW":   "Dow Inc",
    "NUE":   "Nucor",
    "CRM":   "Salesforce",
    "NKE":   "Nike",
    "BRK-B": "Berkshire Hathaway",
}

YEARS       = 15
START_DATE  = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE    = datetime.now().strftime("%Y-%m-%d")

# ── Data layer ────────────────────────────────────────────────────────────────

def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol.replace('-','_')}_{YEARS}yr.pkl"


def fetch_prices(symbol: str) -> Optional[pd.Series]:
    """Fetch adjusted close prices with disk cache. Returns None on failure."""
    cp = cache_path(symbol)
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, pd.Series) and len(data) > 100:
                return data
        except Exception:
            pass

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if hist.empty or "Close" not in hist.columns:
            return None
        prices = hist["Close"].dropna()
        if len(prices) < 252:  # need at least 1 year
            return None
        with open(cp, "wb") as f:
            pickle.dump(prices, f)
        return prices
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


# ── Backtest engine ───────────────────────────────────────────────────────────

def backtest(prices: pd.Series, signals: pd.Series, position_type: str) -> dict:
    """
    Run a vectorised backtest.

    signals : pd.Series of {-1, 0, 1}  (aligned to prices index)
    position_type : 'long' | 'short' | 'long_short'

    Returns dict with raw_return, cagr, sharpe, max_drawdown, n_trades.
    """
    # Align
    common = prices.index.intersection(signals.index)
    if len(common) < 50:
        return {}
    p = prices.loc[common]
    s = signals.loc[common].shift(1).fillna(0)  # avoid look-ahead: act next day

    # Filter signals by position type
    if position_type == "long":
        pos = s.clip(lower=0)            # only long signals
    elif position_type == "short":
        pos = s.clip(upper=0).abs()      # only short signals, flip sign for return
        s_flipped = s.clip(upper=0)
    else:  # long_short
        pos = s

    # Daily returns
    daily_ret = p.pct_change().fillna(0)

    if position_type == "short":
        # short: profit when price falls
        strategy_ret = daily_ret * s.clip(upper=0) * -1
    else:
        strategy_ret = daily_ret * pos

    # Remove NaN
    strategy_ret = strategy_ret.fillna(0)

    # Raw return (total cumulative)
    cum = (1 + strategy_ret).cumprod()
    raw_return = float(cum.iloc[-1] - 1)

    # CAGR
    n_years = len(strategy_ret) / 252
    cagr = float((1 + raw_return) ** (1 / max(n_years, 0.1)) - 1) if raw_return > -1 else float("-inf")

    # Sharpe (annualised, rf=0)
    mu  = strategy_ret.mean()
    std = strategy_ret.std()
    sharpe = float(mu / std * math.sqrt(252)) if std > 0 else 0.0

    # Max drawdown
    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    max_dd   = float(drawdown.min())

    # Trade count (position changes)
    if position_type == "long":
        n_trades = int((s.clip(lower=0).diff().abs() > 0).sum())
    elif position_type == "short":
        n_trades = int((s.clip(upper=0).diff().abs() > 0).sum())
    else:
        n_trades = int((s.diff().abs() > 0).sum())

    return {
        "raw_return":   round(raw_return * 100, 2),   # %
        "cagr":         round(cagr * 100, 2),          # %
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),        # %
        "n_trades":     n_trades,
        "n_days":       len(strategy_ret),
    }


def buy_and_hold(prices: pd.Series) -> dict:
    """Benchmark: buy-and-hold raw return."""
    if prices is None or len(prices) < 2:
        return {}
    r = float(prices.iloc[-1] / prices.iloc[0] - 1)
    n_years = len(prices) / 252
    cagr = float((1 + r) ** (1 / max(n_years, 0.1)) - 1) if r > -1 else float("-inf")
    daily = prices.pct_change().fillna(0)
    sharpe = float(daily.mean() / daily.std() * math.sqrt(252)) if daily.std() > 0 else 0
    cum = (1 + daily).cumprod()
    max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
    return {
        "raw_return":   round(r * 100, 2),
        "cagr":         round(cagr * 100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "n_trades":     1,
        "n_days":       len(prices),
    }


# ── Strategy base class ───────────────────────────────────────────────────────

class Strategy(ABC):
    family:      str = "unknown"
    name:        str = "base"
    description: str = ""

    @abstractmethod
    def signals(self, prices: pd.Series) -> pd.Series:
        """Return pd.Series of {-1, 0, 1} aligned to prices.index."""

    def __repr__(self):
        return f"{self.family}/{self.name}"


# ── Strategy Family 1: Price Momentum ────────────────────────────────────────

class PriceMomentum(Strategy):
    """
    §3.1 Price Momentum (Jegadeesh & Titman 1993)
    Long when r(t-skip-window, t-skip) > 0, flat otherwise.
    In L/S mode: short when negative.
    """
    family = "momentum"

    def __init__(self, window: int = 252, skip: int = 21, name: str = "PM_12_1"):
        self.window = window
        self.skip   = skip
        self.name   = name
        self.description = f"Price Momentum {window}d skip {skip}d"

    def signals(self, prices: pd.Series) -> pd.Series:
        past   = prices.shift(self.skip)
        lagged = prices.shift(self.skip + self.window)
        ret    = (past - lagged) / lagged
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[ret > 0]  =  1
        sig[ret <= 0] = -1
        sig[ret.isna()] = 0
        return sig


class MomentumShortTerm(Strategy):
    """Short-term momentum (1-month)."""
    family = "momentum"
    name   = "PM_1_0"
    description = "1-month price momentum"

    def signals(self, prices: pd.Series) -> pd.Series:
        ret = prices.pct_change(21)
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[ret > 0]  =  1
        sig[ret <= 0] = -1
        sig[ret.isna()] = 0
        return sig


# ── Strategy Family 2: Mean Reversion ────────────────────────────────────────

class ZScoreMeanReversion(Strategy):
    """
    §3.9 Z-score mean reversion.
    Long when z < -threshold (oversold), short when z > +threshold (overbought).
    """
    family = "mean_reversion"

    def __init__(self, window: int = 20, threshold: float = 2.0, name: str = "MR_20_2"):
        self.window    = window
        self.threshold = threshold
        self.name      = name
        self.description = f"Z-score MR {window}d ±{threshold}σ"

    def signals(self, prices: pd.Series) -> pd.Series:
        roll_mean = prices.rolling(self.window).mean()
        roll_std  = prices.rolling(self.window).std()
        z         = (prices - roll_mean) / roll_std
        sig       = pd.Series(0, index=prices.index, dtype=float)
        sig[z < -self.threshold] =  1   # oversold → long
        sig[z >  self.threshold] = -1   # overbought → short
        return sig


class RSIMeanReversion(Strategy):
    """
    RSI-based mean reversion.
    Long when RSI < oversold (30), short when RSI > overbought (70).
    """
    family = "mean_reversion"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70,
                 name: str = "RSI_14"):
        self.period     = period
        self.oversold   = oversold
        self.overbought = overbought
        self.name       = name
        self.description = f"RSI({period}) <{oversold} long, >{overbought} short"

    def signals(self, prices: pd.Series) -> pd.Series:
        delta = prices.diff()
        gain  = delta.clip(lower=0).rolling(self.period).mean()
        loss  = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = 100 - (100 / (1 + rs))
        sig   = pd.Series(0, index=prices.index, dtype=float)
        sig[rsi < self.oversold]   =  1
        sig[rsi > self.overbought] = -1
        return sig


# ── Strategy Family 3: Trend Following (Moving Averages) ─────────────────────

class MovingAverageCrossover(Strategy):
    """
    §3.12 Two MA crossover.
    Long when fast MA > slow MA (golden cross), short otherwise.
    """
    family = "trend"

    def __init__(self, fast: int = 50, slow: int = 200, name: str = "MA_50_200"):
        self.fast = fast
        self.slow = slow
        self.name = name
        self.description = f"MA crossover {fast}/{slow}"

    def signals(self, prices: pd.Series) -> pd.Series:
        fast_ma = prices.rolling(self.fast).mean()
        slow_ma = prices.rolling(self.slow).mean()
        sig     = pd.Series(0, index=prices.index, dtype=float)
        sig[fast_ma > slow_ma] =  1
        sig[fast_ma < slow_ma] = -1
        sig[fast_ma.isna() | slow_ma.isna()] = 0
        return sig


class EMAcrossover(Strategy):
    """
    EMA crossover (basis of MACD signal).
    Long when fast EMA > slow EMA.
    """
    family = "trend"

    def __init__(self, fast: int = 12, slow: int = 26, name: str = "EMA_12_26"):
        self.fast = fast
        self.slow = slow
        self.name = name
        self.description = f"EMA crossover {fast}/{slow}"

    def signals(self, prices: pd.Series) -> pd.Series:
        fast_ema = prices.ewm(span=self.fast, adjust=False).mean()
        slow_ema = prices.ewm(span=self.slow, adjust=False).mean()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[fast_ema > slow_ema] =  1
        sig[fast_ema < slow_ema] = -1
        return sig


# ── Strategy Family 4: Breakout ───────────────────────────────────────────────

class DonchianChannel(Strategy):
    """
    §3.15 Donchian Channel breakout (Turtle Trading).
    Long on N-day high breakout, short on N-day low breakout.
    """
    family = "breakout"

    def __init__(self, window: int = 20, name: str = "DC_20"):
        self.window = window
        self.name   = name
        self.description = f"Donchian Channel {window}d"

    def signals(self, prices: pd.Series) -> pd.Series:
        roll_high = prices.rolling(self.window).max().shift(1)
        roll_low  = prices.rolling(self.window).min().shift(1)
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[prices >= roll_high] =  1
        sig[prices <= roll_low]  = -1
        return sig


class BollingerBand(Strategy):
    """
    Bollinger Band breakout.
    Long when price crosses above upper band (momentum mode),
    or long when price crosses below lower band (mean reversion mode).
    This implements the mean-reversion (fade) version.
    """
    family = "breakout"

    def __init__(self, window: int = 20, n_std: float = 2.0, name: str = "BB_20_fade"):
        self.window = window
        self.n_std  = n_std
        self.name   = name
        self.description = f"Bollinger Band {window}d ±{n_std}σ (fade)"

    def signals(self, prices: pd.Series) -> pd.Series:
        mid    = prices.rolling(self.window).mean()
        std    = prices.rolling(self.window).std()
        upper  = mid + self.n_std * std
        lower  = mid - self.n_std * std
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[prices < lower] =  1   # below lower band → long (mean reversion)
        sig[prices > upper] = -1   # above upper band → short (mean reversion)
        return sig


# ── Strategy Family 5: Volatility ─────────────────────────────────────────────

class LowVolatilityAnomaly(Strategy):
    """
    §3.4 Low Volatility Anomaly.
    For single-asset: long when trailing volatility is below its own median
    (the stock is in a low-vol regime → expected outperformance).
    Short when volatility is elevated.
    """
    family = "volatility"
    name   = "LV_60"
    description = "Low Volatility Anomaly — 60d vol regime"

    def __init__(self, window: int = 60, lookback: int = 252):
        self.window   = window
        self.lookback = lookback

    def signals(self, prices: pd.Series) -> pd.Series:
        ret    = prices.pct_change()
        vol    = ret.rolling(self.window).std() * math.sqrt(252)
        median = vol.rolling(self.lookback).median()
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[vol < median] =  1   # low-vol regime → long
        sig[vol > median] = -1   # high-vol regime → short / flat
        sig[vol.isna() | median.isna()] = 0
        return sig


# ── Strategy Family 6: Machine Learning (KNN) ────────────────────────────────

class KNNStrategy(Strategy):
    """
    §3.17 K-Nearest Neighbours.
    Features: 5d, 10d, 20d returns. Predict next-day direction.
    Train on first half of data; test on second half.
    """
    family = "ml"

    def __init__(self, k: int = 5, name: str = "KNN_5"):
        self.k    = k
        self.name = name
        self.description = f"KNN (k={k}) on 5/10/20d returns"

    def signals(self, prices: pd.Series) -> pd.Series:
        ret = prices.pct_change()
        df  = pd.DataFrame({
            "r5":   ret.rolling(5).sum(),
            "r10":  ret.rolling(10).sum(),
            "r20":  ret.rolling(20).sum(),
            "next": ret.shift(-1),
        }).dropna()

        sig = pd.Series(0, index=prices.index, dtype=float)
        if len(df) < 100:
            return sig

        split = len(df) // 2
        train = df.iloc[:split]
        test  = df.iloc[split:]

        X_train = train[["r5","r10","r20"]].values
        y_train = np.sign(train["next"].values)
        X_test  = test[["r5","r10","r20"]].values

        # Simple KNN (no sklearn dependency)
        predictions = []
        for x in X_test:
            dists = np.sqrt(((X_train - x) ** 2).sum(axis=1))
            top_k = y_train[np.argsort(dists)[:self.k]]
            pred  = np.sign(top_k.sum())
            predictions.append(pred)

        pred_series = pd.Series(predictions, index=test.index)
        sig.update(pred_series)
        return sig


# ── Strategy Family 7: MACD Histogram ────────────────────────────────────────

class MACDHistogram(Strategy):
    """
    MACD Histogram crossover.
    Long when histogram turns positive (MACD line crosses above signal line).
    Short when histogram turns negative.
    """
    family = "trend"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9,
                 name: str = "MACD_12_26_9"):
        self.fast   = fast
        self.slow   = slow
        self.signal = signal
        self.name   = name
        self.description = f"MACD histogram {fast}/{slow}/{signal}"

    def signals(self, prices: pd.Series) -> pd.Series:
        ema_fast = prices.ewm(span=self.fast,   adjust=False).mean()
        ema_slow = prices.ewm(span=self.slow,   adjust=False).mean()
        macd     = ema_fast - ema_slow
        sig_line = macd.ewm(span=self.signal, adjust=False).mean()
        hist     = macd - sig_line
        sig      = pd.Series(0, index=prices.index, dtype=float)
        sig[hist > 0] =  1
        sig[hist < 0] = -1
        return sig


class MACDZeroCross(Strategy):
    """
    MACD zero-line crossover (slower, fewer trades than histogram).
    Long when MACD line > 0, short when < 0.
    """
    family = "trend"

    def __init__(self, fast: int = 12, slow: int = 26, name: str = "MACD_zero"):
        self.fast = fast
        self.slow = slow
        self.name = name
        self.description = f"MACD zero-cross {fast}/{slow}"

    def signals(self, prices: pd.Series) -> pd.Series:
        ema_fast = prices.ewm(span=self.fast, adjust=False).mean()
        ema_slow = prices.ewm(span=self.slow, adjust=False).mean()
        macd     = ema_fast - ema_slow
        sig      = pd.Series(0, index=prices.index, dtype=float)
        sig[macd > 0] =  1
        sig[macd < 0] = -1
        return sig


# ── Strategy Family 8: Volume-Weighted ───────────────────────────────────────

class VWAPReversion(Strategy):
    """
    VWAP-style mean reversion using a rolling VWAP approximation.
    Long when price is significantly below rolling VWAP, short when above.
    (Uses daily close × volume as proxy since intraday VWAP not available.)
    """
    family = "mean_reversion"

    def __init__(self, window: int = 20, threshold: float = 0.02,
                 name: str = "VWAP_20"):
        self.window    = window
        self.threshold = threshold
        self.name      = name
        self.description = f"VWAP reversion {window}d ±{threshold*100:.0f}%"

    def signals(self, prices: pd.Series) -> pd.Series:
        # Rolling VWAP approximation using price only (volume not always available)
        vwap  = prices.rolling(self.window).mean()
        dev   = (prices - vwap) / vwap
        sig   = pd.Series(0, index=prices.index, dtype=float)
        sig[dev < -self.threshold] =  1   # below VWAP → long
        sig[dev >  self.threshold] = -1   # above VWAP → short
        return sig


# ── Strategy Family 9: Adaptive Momentum ─────────────────────────────────────

class AdaptiveMomentum(Strategy):
    """
    Momentum that only enters when volatility is within a healthy range
    (not too low = boring, not too high = dangerous).
    Combines PM_1_0 with a vol filter.
    """
    family = "momentum"

    def __init__(self, mom_window: int = 21, vol_window: int = 20,
                 vol_lo: float = 0.10, vol_hi: float = 0.50,
                 name: str = "APM_21_vf"):
        self.mom_window = mom_window
        self.vol_window = vol_window
        self.vol_lo     = vol_lo
        self.vol_hi     = vol_hi
        self.name       = name
        self.description = f"Adaptive momentum {mom_window}d + vol filter {vol_lo:.0%}-{vol_hi:.0%}"

    def signals(self, prices: pd.Series) -> pd.Series:
        ret = prices.pct_change()
        mom = prices.pct_change(self.mom_window)
        vol = ret.rolling(self.vol_window).std() * math.sqrt(252)
        # Vol filter: only trade when vol is in healthy range
        vol_ok = (vol >= self.vol_lo) & (vol <= self.vol_hi)
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[(mom > 0) & vol_ok] =  1
        sig[(mom < 0) & vol_ok] = -1
        return sig


# ── Strategy Family 10: Combo — Trend + Vol Filter ───────────────────────────

class ComboTrendVolFilter(Strategy):
    """
    Round 3: MA crossover that only trades when volatility is healthy.
    Combines R2's top trend family with R1's top volatility family insight.
    """
    family = "combo"

    def __init__(self, fast: int = 50, slow: int = 200, vol_window: int = 20,
                 vol_lo: float = 0.10, vol_hi: float = 0.60,
                 name: str = "MA_vf"):
        self.fast       = fast
        self.slow       = slow
        self.vol_window = vol_window
        self.vol_lo     = vol_lo
        self.vol_hi     = vol_hi
        self.name       = name
        self.description = f"MA {fast}/{slow} + vol filter {vol_lo:.0%}-{vol_hi:.0%}"

    def signals(self, prices: pd.Series) -> pd.Series:
        fast_ma = prices.rolling(self.fast).mean()
        slow_ma = prices.rolling(self.slow).mean()
        ret     = prices.pct_change()
        vol     = ret.rolling(self.vol_window).std() * math.sqrt(252)
        vol_ok  = (vol >= self.vol_lo) & (vol <= self.vol_hi)
        sig     = pd.Series(0, index=prices.index, dtype=float)
        sig[(fast_ma > slow_ma) & vol_ok] =  1
        sig[(fast_ma < slow_ma) & vol_ok] = -1
        sig[fast_ma.isna() | slow_ma.isna()] = 0
        return sig


class ComboMomMA(Strategy):
    """
    Round 3: Momentum confirmation with MA trend filter.
    Enter long only when short-term momentum is positive AND price is above slow MA.
    Enter short only when momentum is negative AND price is below slow MA.
    Both signals must agree — reduces whipsaws.
    """
    family = "combo"

    def __init__(self, mom_window: int = 21, fast: int = 50, slow: int = 200,
                 name: str = "PM_MA_combo"):
        self.mom_window = mom_window
        self.fast       = fast
        self.slow       = slow
        self.name       = name
        self.description = f"Momentum {mom_window}d + MA {fast}/{slow} confirmation"

    def signals(self, prices: pd.Series) -> pd.Series:
        mom     = prices.pct_change(self.mom_window)
        fast_ma = prices.rolling(self.fast).mean()
        slow_ma = prices.rolling(self.slow).mean()
        trend   = fast_ma > slow_ma   # True = uptrend
        sig     = pd.Series(0, index=prices.index, dtype=float)
        sig[(mom > 0) & trend]  =  1   # momentum + trend both up
        sig[(mom < 0) & ~trend] = -1   # momentum + trend both down
        sig[fast_ma.isna() | slow_ma.isna()] = 0
        return sig


# ── Round 4: LV55 Regime Gate ────────────────────────────────────────────────

class LV55RegimeGate(Strategy):
    """
    Round 4: LV_55 regime gate applied to MA crossover.
    Only enters MA positions when 55d realized vol < threshold (low-vol regime).
    Hypothesis: MA crossover works best in calm, trending markets.
    """
    family = "combo"

    def __init__(self, inner_fast: int = 50, inner_slow: int = 200,
                 vol_window: int = 55, vol_threshold: float = 0.35,
                 name: str = "LV55_gate_MA"):
        self.inner_fast    = inner_fast
        self.inner_slow    = inner_slow
        self.vol_window    = vol_window
        self.vol_threshold = vol_threshold
        self.name          = name
        self.description   = (
            f"LV55 regime gate + MA{inner_fast}/{inner_slow} "
            f"(vol<{vol_threshold:.0%})"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        fast_ma = prices.rolling(self.inner_fast).mean()
        slow_ma = prices.rolling(self.inner_slow).mean()
        ma_signal = np.sign(fast_ma - slow_ma)

        daily_ret = prices.pct_change()
        realized_vol = daily_ret.rolling(self.vol_window).std() * np.sqrt(252)
        in_low_vol = (realized_vol < self.vol_threshold).astype(float)

        return (ma_signal * in_low_vol).fillna(0)


class LV55MomGate(Strategy):
    """
    Round 4: LV_55 regime gate applied to price momentum.
    Only enters when 55d vol is below threshold — momentum in low-vol regime.
    """
    family = "combo"

    def __init__(self, mom_window: int = 252, vol_window: int = 55,
                 vol_threshold: float = 0.35, name: str = "LV55_mom_gate"):
        self.mom_window    = mom_window
        self.vol_window    = vol_window
        self.vol_threshold = vol_threshold
        self.name          = name
        self.description   = (
            f"LV55 gate + mom{mom_window} (vol<{vol_threshold:.0%})"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        mom = prices / prices.shift(self.mom_window) - 1
        mom_signal = np.sign(mom)

        daily_ret = prices.pct_change()
        realized_vol = daily_ret.rolling(self.vol_window).std() * np.sqrt(252)
        in_low_vol = (realized_vol < self.vol_threshold).astype(float)

        return (mom_signal * in_low_vol).fillna(0)


# ── Round 4: Triple Confirmation ─────────────────────────────────────────────

class TripleMomTrendVol(Strategy):
    """
    Round 4: Triple-confirmation — momentum + MA trend + low vol.
    All three must simultaneously agree for a long entry.
    Hypothesis: high-conviction entries from three independent signals.
    """
    family = "combo"

    def __init__(self, mom_window: int = 126, fast_ma: int = 50, slow_ma: int = 200,
                 vol_window: int = 55, vol_threshold: float = 0.35,
                 name: str = "triple_mtv"):
        self.mom_window    = mom_window
        self.fast_ma       = fast_ma
        self.slow_ma       = slow_ma
        self.vol_window    = vol_window
        self.vol_threshold = vol_threshold
        self.name          = name
        self.description   = (
            f"Triple: mom{mom_window}+MA{fast_ma}/{slow_ma}+LV{vol_window}"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        mom = prices / prices.shift(self.mom_window) - 1
        mom_bull = (mom > 0).astype(float)

        fast = prices.rolling(self.fast_ma).mean()
        slow = prices.rolling(self.slow_ma).mean()
        ma_bull = (fast > slow).astype(float)

        daily_ret = prices.pct_change()
        realized_vol = daily_ret.rolling(self.vol_window).std() * np.sqrt(252)
        low_vol = (realized_vol < self.vol_threshold).astype(float)

        # All three must agree — binary, long only (flat when any fails)
        return (mom_bull * ma_bull * low_vol).fillna(0)


# ── Round 4: Volatility-Adjusted Momentum ────────────────────────────────────

class VolAdjMomentum(Strategy):
    """
    Round 4: Volatility-adjusted (Sharpe-style) momentum.
    Signal = rolling_return / rolling_vol.
    Captures risk-adjusted return momentum rather than raw price change.
    """
    family = "momentum"

    def __init__(self, ret_window: int = 126, vol_window: int = 21,
                 name: str = "vol_adj_mom"):
        self.ret_window  = ret_window
        self.vol_window  = vol_window
        self.name        = name
        self.description = f"Vol-adj momentum {ret_window}d/{vol_window}d"

    def signals(self, prices: pd.Series) -> pd.Series:
        returns   = prices.pct_change()
        cum_ret   = prices / prices.shift(self.ret_window) - 1
        roll_vol  = returns.rolling(self.vol_window).std() * np.sqrt(252)
        roll_vol  = roll_vol.replace(0, np.nan)
        sharpe_sig = cum_ret / roll_vol
        return np.sign(sharpe_sig).fillna(0)


# ── Round 5: Vol-Adj Momentum + Trend Filter ─────────────────────────────────

class VolAdjMomTrend(Strategy):
    """
    Round 5: Volatility-adjusted momentum gated by MA trend filter.
    Combines R4's breakout winner (vol_adj_mom) with the reliable MA trend signal.
    Only enters when BOTH: Sharpe-style momentum > 0 AND fast MA > slow MA.
    """
    family = "combo"

    def __init__(self, ret_window: int = 126, vol_window: int = 21,
                 fast_ma: int = 50, slow_ma: int = 200,
                 name: str = "vam_trend"):
        self.ret_window = ret_window
        self.vol_window = vol_window
        self.fast_ma    = fast_ma
        self.slow_ma    = slow_ma
        self.name       = name
        self.description = (
            f"Vol-adj mom {ret_window}d/{vol_window}d + MA{fast_ma}/{slow_ma}"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        returns   = prices.pct_change()
        cum_ret   = prices / prices.shift(self.ret_window) - 1
        roll_vol  = returns.rolling(self.vol_window).std() * np.sqrt(252)
        roll_vol  = roll_vol.replace(0, np.nan)
        sharpe_sig = cum_ret / roll_vol                          # vol-adj momentum

        fast = prices.rolling(self.fast_ma).mean()
        slow = prices.rolling(self.slow_ma).mean()
        in_uptrend = (fast > slow).astype(float)

        raw = np.sign(sharpe_sig)
        return (raw * in_uptrend).fillna(0)


# ── Round 5: Dual Momentum ────────────────────────────────────────────────────

class DualMomentum(Strategy):
    """
    Round 5: Dual-timeframe momentum (inspired by Antonacci).
    Two independent lookback windows must both agree before entering.
    Long only when BOTH long-term (252d) AND medium-term (63d) momentum positive.
    Short only when both are negative. Reduces false signals vs single-window.
    """
    family = "momentum"

    def __init__(self, long_window: int = 252, short_window: int = 63,
                 name: str = "dual_mom"):
        self.long_window  = long_window
        self.short_window = short_window
        self.name         = name
        self.description  = f"Dual momentum {long_window}d + {short_window}d"

    def signals(self, prices: pd.Series) -> pd.Series:
        long_mom  = prices / prices.shift(self.long_window)  - 1
        short_mom = prices / prices.shift(self.short_window) - 1

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[(long_mom > 0) & (short_mom > 0)] =  1   # both bullish → long
        sig[(long_mom < 0) & (short_mom < 0)] = -1   # both bearish → short
        return sig.fillna(0)


# ── Round 5: Vol-Adj Momentum with Vol Regime Gate ───────────────────────────

class VolAdjMomLVGate(Strategy):
    """
    Round 5: Vol-adjusted momentum filtered by LV_55 low-vol regime.
    Applies the Sharpe-style momentum signal ONLY when the stock is in
    a low-vol regime (realized vol < threshold). Best of both R4 worlds.
    """
    family = "combo"

    def __init__(self, ret_window: int = 126, signal_vol_window: int = 21,
                 gate_vol_window: int = 55, gate_threshold: float = 0.40,
                 name: str = "vam_lv_gate"):
        self.ret_window        = ret_window
        self.signal_vol_window = signal_vol_window
        self.gate_vol_window   = gate_vol_window
        self.gate_threshold    = gate_threshold
        self.name              = name
        self.description       = (
            f"Vol-adj mom {ret_window}d + LV{gate_vol_window} gate"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        returns       = prices.pct_change()
        cum_ret       = prices / prices.shift(self.ret_window) - 1
        signal_vol    = returns.rolling(self.signal_vol_window).std() * np.sqrt(252)
        signal_vol    = signal_vol.replace(0, np.nan)
        sharpe_sig    = np.sign(cum_ret / signal_vol)

        gate_vol      = returns.rolling(self.gate_vol_window).std() * np.sqrt(252)
        low_vol_gate  = (gate_vol < self.gate_threshold).astype(float)

        return (sharpe_sig * low_vol_gate).fillna(0)


# ── Round 6: Dual Vol-Adj Momentum ───────────────────────────────────────────

class DualVolAdjMom(Strategy):
    """
    Round 6: Both a long-window AND short-window Sharpe-style momentum signal
    must agree before entering. Reduces false positives from either window alone.
    Inspired by dual_mom but using vol-adjusted (risk-normalized) signals.
    """
    family = "momentum"

    def __init__(self, long_ret: int = 252, short_ret: int = 63,
                 vol_window: int = 21, name: str = "dual_vam"):
        self.long_ret   = long_ret
        self.short_ret  = short_ret
        self.vol_window = vol_window
        self.name       = name
        self.description = (
            f"Dual vol-adj mom {long_ret}d+{short_ret}d / {vol_window}d vol"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        returns  = prices.pct_change()
        roll_vol = returns.rolling(self.vol_window).std() * np.sqrt(252)
        roll_vol = roll_vol.replace(0, np.nan)

        long_ret  = prices / prices.shift(self.long_ret)  - 1
        short_ret = prices / prices.shift(self.short_ret) - 1

        long_sharpe  = np.sign(long_ret  / roll_vol)
        short_sharpe = np.sign(short_ret / roll_vol)

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[(long_sharpe > 0) & (short_sharpe > 0)] =  1
        sig[(long_sharpe < 0) & (short_sharpe < 0)] = -1
        return sig.fillna(0)


# ── Round 6: MACD + LV Regime Gate ───────────────────────────────────────────

class MACDLVGate(Strategy):
    """
    Round 6: MACD histogram signal gated by LV low-vol regime.
    Only trades when the stock is in a calm (low-vol) phase.
    Hypothesis: MACD generates more reliable signals in low-noise environments.
    """
    family = "combo"

    def __init__(self, fast: int = 5, slow: int = 11, signal: int = 4,
                 vol_window: int = 55, vol_threshold: float = 0.35,
                 name: str = "macd_lv_gate"):
        self.fast          = fast
        self.slow          = slow
        self.signal        = signal
        self.vol_window    = vol_window
        self.vol_threshold = vol_threshold
        self.name          = name
        self.description   = (
            f"MACD {fast}/{slow}/{signal} + LV{vol_window} gate"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        ema_fast = prices.ewm(span=self.fast,   adjust=False).mean()
        ema_slow = prices.ewm(span=self.slow,   adjust=False).mean()
        macd     = ema_fast - ema_slow
        sig_line = macd.ewm(span=self.signal, adjust=False).mean()
        hist     = macd - sig_line
        macd_sig = pd.Series(0, index=prices.index, dtype=float)
        macd_sig[hist > 0] =  1
        macd_sig[hist < 0] = -1

        daily_ret    = prices.pct_change()
        realized_vol = daily_ret.rolling(self.vol_window).std() * np.sqrt(252)
        in_low_vol   = (realized_vol < self.vol_threshold).astype(float)

        return (macd_sig * in_low_vol).fillna(0)


# ── Round 7: ATR Channel Breakout ─────────────────────────────────────────────

class ATRChannelBreakout(Strategy):
    """
    Round 7: Breakout beyond an ATR-based volatility channel.
    Uses daily return std as ATR proxy (no OHLC data available).
    Long when price exceeds rolling mean + N * ATR (breakout momentum).
    """
    family = "breakout"

    def __init__(self, atr_window: int = 14, channel_window: int = 20,
                 multiplier: float = 1.5, name: str = "atr_break"):
        self.atr_window     = atr_window
        self.channel_window = channel_window
        self.multiplier     = multiplier
        self.name           = name
        self.description    = (
            f"ATR channel breakout {channel_window}d x{multiplier}"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        daily_ret = prices.pct_change()
        atr_pct   = daily_ret.abs().rolling(self.atr_window).mean()
        atr_price = prices * atr_pct          # ATR in price units

        mid   = prices.rolling(self.channel_window).mean()
        upper = mid + self.multiplier * atr_price
        lower = mid - self.multiplier * atr_price

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[prices > upper] =  1   # breakout above → long
        sig[prices < lower] = -1   # breakdown below → short
        return sig.fillna(0)


# ── Round 7: Price Momentum Oscillator ───────────────────────────────────────

class PMO(Strategy):
    """
    Round 7: Price Momentum Oscillator (Carl Swenlin).
    Double-smoothed rate-of-change.
    Long when PMO crosses above its signal line, short when it crosses below.
    """
    family = "momentum"

    def __init__(self, roc_periods: int = 1, smooth1: int = 35,
                 smooth2: int = 20, signal: int = 10, name: str = "PMO"):
        self.roc_periods = roc_periods
        self.smooth1     = smooth1
        self.smooth2     = smooth2
        self.signal      = signal
        self.name        = name
        self.description = f"PMO {smooth1}/{smooth2}/{signal}"

    def signals(self, prices: pd.Series) -> pd.Series:
        roc  = prices.pct_change(self.roc_periods) * 100
        pmo1 = roc.ewm(span=self.smooth1, adjust=False).mean() * 20
        pmo2 = pmo1.ewm(span=self.smooth2, adjust=False).mean()
        sig_line = pmo2.ewm(span=self.signal, adjust=False).mean()

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[pmo2 > sig_line] =  1
        sig[pmo2 < sig_line] = -1
        return sig.fillna(0)


# ── Round 7: Trend Consistency ────────────────────────────────────────────────

class TrendConsistency(Strategy):
    """
    Round 7: Enter when the fraction of up-days in the lookback exceeds
    a threshold — indicating a consistent, high-quality trend (not just
    a few big jumps). Short when fraction of down-days is high.
    """
    family = "trend"

    def __init__(self, window: int = 63, threshold: float = 0.56,
                 name: str = "trend_cons"):
        self.window    = window
        self.threshold = threshold
        self.name      = name
        self.description = f"Trend consistency {window}d >{threshold:.0%}"

    def signals(self, prices: pd.Series) -> pd.Series:
        daily_ret = prices.pct_change()
        up_frac   = (daily_ret > 0).rolling(self.window).mean()

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[up_frac >  self.threshold]       =  1
        sig[up_frac < (1 - self.threshold)]  = -1
        return sig.fillna(0)


# ── Round 8: Momentum Score ───────────────────────────────────────────────────

class MomentumScore(Strategy):
    """
    Round 8: Composite momentum score across multiple lookback windows.
    Scores +1 for each window where price has positive return, -1 for negative.
    Normalizes to [-1, +1] and uses sign threshold for entry.
    """
    family = "momentum"

    def __init__(self, windows: tuple = (21, 63, 126, 252),
                 entry_threshold: float = 0.5, name: str = "mom_score"):
        self.windows          = windows
        self.entry_threshold  = entry_threshold
        self.name             = name
        self.description      = (
            f"Momentum score {windows} thresh={entry_threshold}"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        n     = len(self.windows)
        score = pd.Series(0.0, index=prices.index)
        for w in self.windows:
            ret = prices / prices.shift(w) - 1
            score += np.sign(ret.fillna(0))
        score /= n   # normalise to [-1, +1]

        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[score >=  self.entry_threshold] =  1
        sig[score <= -self.entry_threshold] = -1
        return sig.fillna(0)


# ── Round 8: Best-of-3 Voting ─────────────────────────────────────────────────

class VotingStrategy(Strategy):
    """
    Round 8: Majority-vote ensemble of three proven top strategies.
    Uses LV_55 signal, PM_1_0 signal, and MACD_5_11 signal.
    Enters when at least 2 out of 3 agree.
    """
    family = "combo"
    name   = "vote_3"
    description = "Voting: LV_55 + PM_1_0 + MACD_5_11 (2/3 majority)"

    def signals(self, prices: pd.Series) -> pd.Series:
        # LV_55 signal
        ret     = prices.pct_change()
        vol_55  = ret.rolling(55).std() * np.sqrt(252)
        med_55  = vol_55.rolling(252).median()
        lv_sig  = pd.Series(0.0, index=prices.index)
        lv_sig[vol_55 < med_55] =  1
        lv_sig[vol_55 > med_55] = -1

        # PM_1_0 signal
        mom_21  = prices.pct_change(21)
        pm_sig  = pd.Series(0.0, index=prices.index)
        pm_sig[mom_21 > 0]  =  1
        pm_sig[mom_21 <= 0] = -1

        # MACD_5_11_4 signal
        ema5    = prices.ewm(span=5,  adjust=False).mean()
        ema11   = prices.ewm(span=11, adjust=False).mean()
        macd    = ema5 - ema11
        sig4    = macd.ewm(span=4, adjust=False).mean()
        hist    = macd - sig4
        mc_sig  = pd.Series(0.0, index=prices.index)
        mc_sig[hist > 0] =  1
        mc_sig[hist < 0] = -1

        # Majority vote
        vote = lv_sig + pm_sig + mc_sig
        sig  = pd.Series(0, index=prices.index, dtype=float)
        sig[vote >= 2]  =  1
        sig[vote <= -2] = -1
        return sig.fillna(0)


# ── Round 9: MACD Winner + LV Regime — Deep Combo ────────────────────────────

class MACDMomCombo(Strategy):
    """
    Round 9: MACD_5_11_4 confirmed by price momentum.
    Only enters MACD trade when medium-term price momentum agrees.
    Reduces MACD whipsaws by requiring trend confirmation.
    """
    family = "combo"

    def __init__(self, fast: int = 5, slow: int = 11, signal: int = 4,
                 mom_window: int = 63, name: str = "macd_mom_combo"):
        self.fast       = fast
        self.slow       = slow
        self.signal     = signal
        self.mom_window = mom_window
        self.name       = name
        self.description = (
            f"MACD {fast}/{slow}/{signal} + mom{mom_window} confirm"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        ema_fast = prices.ewm(span=self.fast,   adjust=False).mean()
        ema_slow = prices.ewm(span=self.slow,   adjust=False).mean()
        macd     = ema_fast - ema_slow
        sig_line = macd.ewm(span=self.signal, adjust=False).mean()
        hist     = macd - sig_line
        macd_sig = np.sign(hist)

        mom = prices / prices.shift(self.mom_window) - 1
        mom_sig = np.sign(mom)

        # Both must agree
        combined = macd_sig * (macd_sig == mom_sig).astype(float)
        return combined.fillna(0)


# ── Round 10: Vol-Adj Mom + MACD Triple Confirm ───────────────────────────────

class VAMMACDTriple(Strategy):
    """
    Round 10: Triple confirmation — vol-adj momentum + MACD + LV regime.
    All three independently proven signals must agree simultaneously.
    The most selective strategy in the harness.
    """
    family = "combo"

    def __init__(self, ret_window: int = 126, vol_win: int = 21,
                 macd_fast: int = 5, macd_slow: int = 11, macd_sig: int = 4,
                 lv_window: int = 55, lv_thresh: float = 0.40,
                 name: str = "vam_macd_lv"):
        self.ret_window  = ret_window
        self.vol_win     = vol_win
        self.macd_fast   = macd_fast
        self.macd_slow   = macd_slow
        self.macd_sig    = macd_sig
        self.lv_window   = lv_window
        self.lv_thresh   = lv_thresh
        self.name        = name
        self.description = (
            f"VAM{ret_window} + MACD{macd_fast}/{macd_slow} + LV{lv_window}"
        )

    def signals(self, prices: pd.Series) -> pd.Series:
        # Vol-adj momentum
        returns   = prices.pct_change()
        cum_ret   = prices / prices.shift(self.ret_window) - 1
        roll_vol  = returns.rolling(self.vol_win).std() * np.sqrt(252)
        roll_vol  = roll_vol.replace(0, np.nan)
        vam_sig   = np.sign(cum_ret / roll_vol)

        # MACD histogram
        ema_f = prices.ewm(span=self.macd_fast, adjust=False).mean()
        ema_s = prices.ewm(span=self.macd_slow, adjust=False).mean()
        macd  = ema_f - ema_s
        sl    = macd.ewm(span=self.macd_sig, adjust=False).mean()
        hist  = macd - sl
        macd_dir = np.sign(hist)

        # LV regime (long only when low-vol)
        realized_vol = returns.rolling(self.lv_window).std() * np.sqrt(252)
        low_vol_gate = (realized_vol < self.lv_thresh).astype(float)

        # All three must agree AND low-vol gate open
        combined = (vam_sig == macd_dir).astype(float) * vam_sig * low_vol_gate
        return combined.fillna(0)


# ── Strategy registry ─────────────────────────────────────────────────────────

def build_strategy_registry() -> Dict[str, Strategy]:
    return {
        # Momentum
        "PM_12_1":  PriceMomentum(252, 21, "PM_12_1"),
        "PM_6_1":   PriceMomentum(126, 21, "PM_6_1"),
        "PM_3_0":   PriceMomentum(63,   0, "PM_3_0"),
        "PM_1_0":   MomentumShortTerm(),
        # Mean Reversion
        "MR_20_2":  ZScoreMeanReversion(20, 2.0, "MR_20_2"),
        "MR_20_15": ZScoreMeanReversion(20, 1.5, "MR_20_15"),
        "MR_60_2":  ZScoreMeanReversion(60, 2.0, "MR_60_2"),
        "RSI_14":   RSIMeanReversion(14, 30, 70, "RSI_14"),
        "RSI_21":   RSIMeanReversion(21, 30, 70, "RSI_21"),
        # Trend
        "MA_50_200":  MovingAverageCrossover(50, 200, "MA_50_200"),
        "MA_20_50":   MovingAverageCrossover(20, 50,  "MA_20_50"),
        "MA_10_30":   MovingAverageCrossover(10, 30,  "MA_10_30"),
        "EMA_12_26":  EMAcrossover(12, 26, "EMA_12_26"),
        # Breakout
        "DC_20":     DonchianChannel(20, "DC_20"),
        "DC_55":     DonchianChannel(55, "DC_55"),
        "BB_20":     BollingerBand(20, 2.0, "BB_20"),
        # Volatility — Round 1 winner, parameter sweep Round 2
        "LV_60":     LowVolatilityAnomaly(60, 252),
        "LV_30":     LowVolatilityAnomaly(30, 252),
        "LV_45":     LowVolatilityAnomaly(45, 252),
        "LV_90":     LowVolatilityAnomaly(90, 252),
        "LV_120":    LowVolatilityAnomaly(120, 252),
        # ML
        "KNN_5":     KNNStrategy(5, "KNN_5"),
        "KNN_10":    KNNStrategy(10, "KNN_10"),
        # MACD — Round 2 new family
        "MACD_hist":    MACDHistogram(12, 26, 9, "MACD_hist"),
        "MACD_fast":    MACDHistogram(8,  17, 9, "MACD_fast"),
        "MACD_zero":    MACDZeroCross(12, 26,    "MACD_zero"),
        # Volume-weighted — Round 2
        "VWAP_20":   VWAPReversion(20, 0.02, "VWAP_20"),
        "VWAP_10":   VWAPReversion(10, 0.015, "VWAP_10"),
        "VWAP_40":   VWAPReversion(40, 0.03, "VWAP_40"),
        # Adaptive momentum — Round 2
        "APM_21_vf": AdaptiveMomentum(21, 20, 0.10, 0.50, "APM_21_vf"),
        "APM_10_vf": AdaptiveMomentum(10, 20, 0.10, 0.40, "APM_10_vf"),
        # PM short-term variants — refining Round 1 top performer PM_1_0
        "PM_5d":     PriceMomentum(5,  0, "PM_5d"),
        "PM_10d":    PriceMomentum(10, 0, "PM_10d"),
        "PM_15d":    PriceMomentum(15, 0, "PM_15d"),
        # Additional MA crossovers — refining top R1 MA combos
        "MA_5_20":   MovingAverageCrossover(5,  20,  "MA_5_20"),
        "MA_10_50":  MovingAverageCrossover(10, 50,  "MA_10_50"),
        "MA_100_200":MovingAverageCrossover(100,200, "MA_100_200"),
        # Round 3: MACD parameter sweep (R2 MACD_fast was top B&H beater at 7%)
        "MACD_6_13":    MACDHistogram(6,  13, 5, "MACD_6_13"),    # ultrafast
        "MACD_8_21":    MACDHistogram(8,  21, 9, "MACD_8_21"),    # mid
        "MACD_5_35":    MACDHistogram(5,  35, 5, "MACD_5_35"),    # Gerald Appel original
        "MACD_19_39":   MACDHistogram(19, 39, 9, "MACD_19_39"),   # weekly-equiv
        # Round 3: Trend family window sweep (R2 top family)
        "MA_3_10":   MovingAverageCrossover(3,  10,  "MA_3_10"),
        "MA_15_40":  MovingAverageCrossover(15, 40,  "MA_15_40"),
        "MA_30_60":  MovingAverageCrossover(30, 60,  "MA_30_60"),
        "MA_50_100": MovingAverageCrossover(50, 100, "MA_50_100"),
        # Round 3: LV fine-tune around R2 winner LV_45
        "LV_35":     LowVolatilityAnomaly(35, 252),
        "LV_40":     LowVolatilityAnomaly(40, 252),
        "LV_50":     LowVolatilityAnomaly(50, 252),
        "LV_55":     LowVolatilityAnomaly(55, 252),
        # Round 3: Combo strategies — trend + vol filter
        "MA_50_200_vf": ComboTrendVolFilter(50, 200, 20, 0.10, 0.60, "MA_50_200_vf"),
        "MA_10_30_vf":  ComboTrendVolFilter(10, 30,  20, 0.10, 0.55, "MA_10_30_vf"),
        # Round 3: Momentum + MA confirmation combo
        "PM_MA_combo":  ComboMomMA(21, 50, 200, "PM_MA_combo"),
        # Round 3: RSI wide bands (less selective, more exposure)
        "RSI_10_wide": RSIMeanReversion(10, 35, 65, "RSI_10_wide"),
        "RSI_5_wide":  RSIMeanReversion(5,  40, 60, "RSI_5_wide"),
        # Round 4: LV ultra-fine-tune (narrowing around R3 winner LV_55)
        "LV_52":     LowVolatilityAnomaly(52, 252),
        "LV_54":     LowVolatilityAnomaly(54, 252),
        "LV_56":     LowVolatilityAnomaly(56, 252),
        "LV_58":     LowVolatilityAnomaly(58, 252),
        # Round 4: MACD deep sweep (R3 winner MACD_6_13 had 8% B&H beat rate)
        "MACD_4_8_3":    MACDHistogram(4,  8,  3, "MACD_4_8_3"),    # ultra-fast scalp
        "MACD_5_10_4":   MACDHistogram(5,  10, 4, "MACD_5_10_4"),   # below 6/13
        "MACD_7_15_5":   MACDHistogram(7,  15, 5, "MACD_7_15_5"),   # above 6/13
        "MACD_6_13_3":   MACDHistogram(6,  13, 3, "MACD_6_13_3"),   # tighter signal
        "MACD_10_21_5":  MACDHistogram(10, 21, 5, "MACD_10_21_5"),  # mid-range
        # Round 4: LV55 regime gate combos
        "LV55_gate_MA50":  LV55RegimeGate(50, 200, 55, 0.35, "LV55_gate_MA50"),
        "LV55_gate_MA10":  LV55RegimeGate(10, 30,  55, 0.30, "LV55_gate_MA10"),
        "LV55_gate_MA25":  LV55RegimeGate(25, 100, 55, 0.35, "LV55_gate_MA25"),
        "LV55_mom_gate":   LV55MomGate(252, 55, 0.35, "LV55_mom_gate"),
        "LV55_mom_gate2":  LV55MomGate(126, 55, 0.30, "LV55_mom_gate2"),
        # Round 4: Triple confirmation strategies
        "triple_mtv":      TripleMomTrendVol(126, 50, 200, 55, 0.35, "triple_mtv"),
        "triple_mtv_hi":   TripleMomTrendVol(252, 50, 200, 55, 0.40, "triple_mtv_hi"),
        "triple_mtv_fast": TripleMomTrendVol(63,  20, 50,  30, 0.30, "triple_mtv_fast"),
        # Round 4: Volatility-adjusted momentum
        "vol_adj_mom_63":  VolAdjMomentum(63,  21, "vol_adj_mom_63"),
        "vol_adj_mom_126": VolAdjMomentum(126, 21, "vol_adj_mom_126"),
        "vol_adj_mom_252": VolAdjMomentum(252, 21, "vol_adj_mom_252"),
        # Round 5: Vol-adj momentum parameter sweep (R4 breakout winner)
        # Vary return lookback window
        "vam_21_5":   VolAdjMomentum(21,  5,  "vam_21_5"),    # very short-term
        "vam_42_10":  VolAdjMomentum(42,  10, "vam_42_10"),   # 2-month
        "vam_84_21":  VolAdjMomentum(84,  21, "vam_84_21"),   # 4-month
        "vam_168_21": VolAdjMomentum(168, 21, "vam_168_21"),  # 8-month
        # Vary vol window (shorter = more reactive signal)
        "vam_126_5":  VolAdjMomentum(126, 5,  "vam_126_5"),   # annual / 1-week vol
        "vam_126_10": VolAdjMomentum(126, 10, "vam_126_10"),  # annual / 2-week vol
        "vam_252_5":  VolAdjMomentum(252, 5,  "vam_252_5"),   # annual ret / 1-week vol
        "vam_252_10": VolAdjMomentum(252, 10, "vam_252_10"),  # annual ret / 2-week vol
        # Round 5: MACD ultra-fine around R4 winner MACD_5_10_4
        "MACD_4_9_3":   MACDHistogram(4,  9,  3, "MACD_4_9_3"),   # just below winner
        "MACD_5_9_3":   MACDHistogram(5,  9,  3, "MACD_5_9_3"),   # tighter params
        "MACD_5_11_4":  MACDHistogram(5,  11, 4, "MACD_5_11_4"),  # near winner
        "MACD_6_11_4":  MACDHistogram(6,  11, 4, "MACD_6_11_4"),  # above winner
        "MACD_4_10_3":  MACDHistogram(4,  10, 3, "MACD_4_10_3"),  # ultra-fast
        # Round 5: Vol-adj momentum + trend combo (new class)
        "vam_trend_126":  VolAdjMomTrend(126, 21, 50, 200, "vam_trend_126"),
        "vam_trend_252":  VolAdjMomTrend(252, 21, 50, 200, "vam_trend_252"),
        "vam_trend_63":   VolAdjMomTrend(63,  21, 20, 50,  "vam_trend_63"),
        # Round 5: Dual momentum (Antonacci-style)
        "dual_mom_252_63":  DualMomentum(252, 63,  "dual_mom_252_63"),
        "dual_mom_252_21":  DualMomentum(252, 21,  "dual_mom_252_21"),
        "dual_mom_126_21":  DualMomentum(126, 21,  "dual_mom_126_21"),
        "dual_mom_126_42":  DualMomentum(126, 42,  "dual_mom_126_42"),
        # Round 5: Vol-adj momentum + LV regime gate combo
        "vam_lv_gate_126":  VolAdjMomLVGate(126, 21, 55, 0.40, "vam_lv_gate_126"),
        "vam_lv_gate_252":  VolAdjMomLVGate(252, 21, 55, 0.40, "vam_lv_gate_252"),
        # ── Round 6 ──────────────────────────────────────────────────────────
        # MACD grid around R5 winner MACD_5_11_4 (9% B&H beat rate)
        "MACD_5_10_3":   MACDHistogram(5,  10, 3, "MACD_5_10_3"),
        "MACD_5_11_3":   MACDHistogram(5,  11, 3, "MACD_5_11_3"),
        "MACD_5_11_5":   MACDHistogram(5,  11, 5, "MACD_5_11_5"),
        "MACD_5_12_4":   MACDHistogram(5,  12, 4, "MACD_5_12_4"),
        "MACD_4_11_3":   MACDHistogram(4,  11, 3, "MACD_4_11_3"),
        "MACD_6_12_4":   MACDHistogram(6,  12, 4, "MACD_6_12_4"),
        "MACD_6_12_5":   MACDHistogram(6,  12, 5, "MACD_6_12_5"),
        # DualVolAdjMom — both Sharpe windows must agree
        "dual_vam_252_63":  DualVolAdjMom(252, 63,  21, "dual_vam_252_63"),
        "dual_vam_126_42":  DualVolAdjMom(126, 42,  21, "dual_vam_126_42"),
        "dual_vam_252_126": DualVolAdjMom(252, 126, 21, "dual_vam_252_126"),
        # MACD + LV regime gate
        "macd_lv_511":   MACDLVGate(5, 11, 4, 55, 0.35, "macd_lv_511"),
        "macd_lv_613":   MACDLVGate(6, 13, 5, 55, 0.35, "macd_lv_613"),
        "macd_lv_hist":  MACDLVGate(12, 26, 9, 55, 0.40, "macd_lv_hist"),
        # Very short vol-adj momentum (ultra-reactive signals)
        "vam_7_3":   VolAdjMomentum(7,  3,  "vam_7_3"),
        "vam_10_5":  VolAdjMomentum(10, 5,  "vam_10_5"),
        "vam_14_5":  VolAdjMomentum(14, 5,  "vam_14_5"),
        # ── Round 7 ──────────────────────────────────────────────────────────
        # ATR channel breakout (vol-normalized price channel)
        "atr_14_1.5":  ATRChannelBreakout(14, 20, 1.5, "atr_14_1.5"),
        "atr_14_2.0":  ATRChannelBreakout(14, 20, 2.0, "atr_14_2.0"),
        "atr_21_1.5":  ATRChannelBreakout(21, 30, 1.5, "atr_21_1.5"),
        # Price Momentum Oscillator (double-smoothed ROC)
        "PMO_35_20":   PMO(1, 35, 20, 10, "PMO_35_20"),
        "PMO_20_10":   PMO(1, 20, 10,  5, "PMO_20_10"),   # faster
        "PMO_50_30":   PMO(1, 50, 30, 15, "PMO_50_30"),   # slower
        # Trend consistency (% of up-days must exceed threshold)
        "tc_63_56":    TrendConsistency(63,  0.56, "tc_63_56"),
        "tc_126_55":   TrendConsistency(126, 0.55, "tc_126_55"),
        "tc_21_58":    TrendConsistency(21,  0.58, "tc_21_58"),
        # MACD_5_11 with adjusted vol-gate thresholds (from R6 expected winner)
        "macd_lv_511_40": MACDLVGate(5, 11, 4, 55, 0.40, "macd_lv_511_40"),
        "macd_lv_511_30": MACDLVGate(5, 11, 4, 55, 0.30, "macd_lv_511_30"),
        # ── Round 8 ──────────────────────────────────────────────────────────
        # Composite momentum score (votes across 4 time windows)
        "mom_score_50":  MomentumScore((21, 63, 126, 252), 0.50, "mom_score_50"),
        "mom_score_75":  MomentumScore((21, 63, 126, 252), 0.75, "mom_score_75"),
        "mom_score_3w":  MomentumScore((5, 21, 63, 126),   0.50, "mom_score_3w"),
        # Ensemble voting (top 3 proven strategies: LV_55, PM_1_0, MACD_5_11)
        "vote_3":        VotingStrategy(),
        # DualVolAdjMom variants with tighter windows
        "dual_vam_84_21": DualVolAdjMom(84, 21, 10, "dual_vam_84_21"),
        "dual_vam_63_21": DualVolAdjMom(63, 21, 10, "dual_vam_63_21"),
        # PMO with vol filter
        "pmo_vf":        PMO(1, 35, 20, 10, "pmo_vf"),    # same as PMO_35_20, combo tested separately
        # TrendConsistency with vol adjustment
        "tc_42_56":      TrendConsistency(42, 0.56, "tc_42_56"),
        # ── Round 9 ──────────────────────────────────────────────────────────
        # MACD winner + price momentum confirmation
        "macd_mom_511":  MACDMomCombo(5, 11, 4, 63,  "macd_mom_511"),
        "macd_mom_511b": MACDMomCombo(5, 11, 4, 126, "macd_mom_511b"),
        "macd_mom_613":  MACDMomCombo(6, 13, 5, 63,  "macd_mom_613"),
        # Vol-adj mom with trend: explore optimal MA windows
        "vam_tr_84_10_30":  VolAdjMomTrend(84,  21, 10, 30,  "vam_tr_84_10_30"),
        "vam_tr_126_10_30": VolAdjMomTrend(126, 21, 10, 30,  "vam_tr_126_10_30"),
        "vam_tr_252_20_50": VolAdjMomTrend(252, 21, 20, 50,  "vam_tr_252_20_50"),
        # Dual momentum with tighter agreement windows
        "dual_mom_84_21":   DualMomentum(84, 21, "dual_mom_84_21"),
        "dual_mom_63_14":   DualMomentum(63, 14, "dual_mom_63_14"),
        # ── Round 10 ──────────────────────────────────────────────────────────
        # Triple combo: vol-adj mom + MACD + LV regime (most selective)
        "vam_macd_lv":     VAMMACDTriple(126, 21, 5, 11, 4, 55, 0.40, "vam_macd_lv"),
        "vam_macd_lv_252": VAMMACDTriple(252, 21, 5, 11, 4, 55, 0.40, "vam_macd_lv_252"),
        "vam_macd_lv_63":  VAMMACDTriple(63,  21, 5, 11, 4, 55, 0.35, "vam_macd_lv_63"),
        # Mom score + LV regime combo
        "ms_lv_gate":    MACDLVGate(5, 11, 4, 55, 0.35, "ms_lv_gate"),  # refined macd_lv_511
        # Final parameter validation of top confirmed strategies
        "LV_53":     LowVolatilityAnomaly(53, 252),   # between R3/R4 fine-tune values
        "LV_57":     LowVolatilityAnomaly(57, 252),
        "MACD_5_11_4_v2": MACDHistogram(5, 11, 4, "MACD_5_11_4_v2"),  # confirm R5 leader
    }


POSITION_TYPES = ["long", "short", "long_short"]


# ── Round runner ──────────────────────────────────────────────────────────────

def run_round(
    round_num:   int,
    tickers:     Dict[str, str],
    strategies:  Dict[str, Strategy],
    verbose:     bool = True,
) -> dict:
    """
    Run a full autoresearch round.
    Returns structured results dict saved to rounds/round_NNN/.
    """
    round_dir = ROUNDS_DIR / f"round_{round_num:03d}"
    round_dir.mkdir(exist_ok=True)

    results = {
        "round":       round_num,
        "timestamp":   datetime.now().isoformat(),
        "start_date":  START_DATE,
        "end_date":    END_DATE,
        "years":       YEARS,
        "metric":      "raw_return",
        "n_tickers":   len(tickers),
        "n_strategies": len(strategies),
        "tickers":     {},
    }

    total = len(tickers)
    for i, (sym, name) in enumerate(tickers.items(), 1):
        if verbose:
            print(f"[{i:02d}/{total}] {sym:6s} {name[:30]}", end=" ", flush=True)

        prices = fetch_prices(sym)
        if prices is None:
            if verbose: print("✗ no data")
            continue

        n_years = len(prices) / 252
        if verbose: print(f"✓ {len(prices)}d ({n_years:.1f}yr)", end=" ", flush=True)

        bh = buy_and_hold(prices)

        ticker_results = {
            "name":         name,
            "n_days":       len(prices),
            "n_years":      round(n_years, 1),
            "buy_and_hold": bh,
            "strategies":   {},
        }

        for sname, strat in strategies.items():
            try:
                sigs = strat.signals(prices)
                strat_result = {}
                for pt in POSITION_TYPES:
                    bt = backtest(prices, sigs, pt)
                    if bt:
                        bt["vs_bh"] = round(bt["raw_return"] - bh.get("raw_return", 0), 2)
                        strat_result[pt] = bt
                ticker_results["strategies"][sname] = {
                    "family":      strat.family,
                    "description": strat.description,
                    "results":     strat_result,
                }
            except Exception as e:
                ticker_results["strategies"][sname] = {"error": str(e)}

        results["tickers"][sym] = ticker_results
        if verbose:
            print(f"| B&H {bh.get('raw_return', 0):+.0f}%")

        time.sleep(0.1)  # be polite

    return results


# ── Insight generation ────────────────────────────────────────────────────────

def generate_insights(results: dict, top_n: int = 20) -> str:
    """
    Karpathy autoresearch step: analyse round results and generate
    structured insights to guide the next round's parameter search.
    """
    lines = []
    lines.append(f"# Autoresearch Insights — Round {results['round']}")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Tickers: {results['n_tickers']}  |  Strategies: {results['n_strategies']}  |  Metric: raw return")
    lines.append("")

    # ── Collect all (ticker, strategy, position_type, raw_return) ─────────
    records = []
    for sym, td in results["tickers"].items():
        bh_ret = td.get("buy_and_hold", {}).get("raw_return", 0)
        for sname, sd in td.get("strategies", {}).items():
            if "error" in sd:
                continue
            for pt, bt in sd.get("results", {}).items():
                if bt:
                    records.append({
                        "ticker":        sym,
                        "strategy":      sname,
                        "family":        sd.get("family", "?"),
                        "position_type": pt,
                        "raw_return":    bt.get("raw_return", 0),
                        "cagr":          bt.get("cagr", 0),
                        "sharpe":        bt.get("sharpe", 0),
                        "max_drawdown":  bt.get("max_drawdown", 0),
                        "vs_bh":         bt.get("vs_bh", 0),
                        "bh_return":     bh_ret,
                    })

    if not records:
        return "No results to analyse."

    records.sort(key=lambda x: x["raw_return"], reverse=True)

    # ── Top combinations overall ───────────────────────────────────────────
    lines.append(f"## Top {top_n} Combinations by Raw Return")
    lines.append("")
    lines.append(f"{'Rank':<5} {'Ticker':<7} {'Strategy':<12} {'Type':<12} {'Return%':>9} {'CAGR%':>7} {'Sharpe':>7} {'vs B&H':>9}")
    lines.append("-" * 70)
    for rank, r in enumerate(records[:top_n], 1):
        lines.append(
            f"{rank:<5} {r['ticker']:<7} {r['strategy']:<12} {r['position_type']:<12} "
            f"{r['raw_return']:>8.1f}% {r['cagr']:>6.1f}% {r['sharpe']:>7.2f} {r['vs_bh']:>+8.1f}%"
        )
    lines.append("")

    # ── Bottom combinations ────────────────────────────────────────────────
    lines.append(f"## Bottom 10 Combinations by Raw Return")
    lines.append("")
    lines.append(f"{'Rank':<5} {'Ticker':<7} {'Strategy':<12} {'Type':<12} {'Return%':>9}")
    lines.append("-" * 50)
    for rank, r in enumerate(records[-10:], 1):
        lines.append(f"{rank:<5} {r['ticker']:<7} {r['strategy']:<12} {r['position_type']:<12} {r['raw_return']:>8.1f}%")
    lines.append("")

    # ── Strategy family ranking ────────────────────────────────────────────
    lines.append("## Strategy Family Ranking (avg raw return across all tickers)")
    lines.append("")
    family_stats: Dict[str, List[float]] = {}
    for r in records:
        fam = r["family"]
        family_stats.setdefault(fam, []).append(r["raw_return"])
    family_ranking = sorted(
        [(fam, sum(v)/len(v), max(v), min(v)) for fam, v in family_stats.items()],
        key=lambda x: x[1], reverse=True
    )
    lines.append(f"{'Family':<20} {'Avg%':>8} {'Max%':>8} {'Min%':>8}")
    lines.append("-" * 48)
    for fam, avg, mx, mn in family_ranking:
        lines.append(f"{fam:<20} {avg:>7.1f}% {mx:>7.1f}% {mn:>7.1f}%")
    lines.append("")

    # ── Per-strategy ranking (best position type) ──────────────────────────
    lines.append("## Strategy Ranking (best position type, avg across tickers)")
    lines.append("")
    strat_best: Dict[str, Dict] = {}
    for r in records:
        key = (r["strategy"], r["position_type"])
        if key not in strat_best:
            strat_best[key] = {"returns": [], "family": r["family"]}
        strat_best[key]["returns"].append(r["raw_return"])
    strat_summary = []
    for (sname, pt), v in strat_best.items():
        avg = sum(v["returns"]) / len(v["returns"])
        strat_summary.append((sname, pt, v["family"], avg, max(v["returns"]), min(v["returns"])))
    strat_summary.sort(key=lambda x: x[3], reverse=True)
    lines.append(f"{'Strategy':<12} {'Type':<12} {'Family':<14} {'Avg%':>8} {'Max%':>8}")
    lines.append("-" * 58)
    for sname, pt, fam, avg, mx, _mn in strat_summary[:20]:
        lines.append(f"{sname:<12} {pt:<12} {fam:<14} {avg:>7.1f}% {mx:>7.1f}%")
    lines.append("")

    # ── Beat B&H analysis ─────────────────────────────────────────────────
    beat_bh = [r for r in records if r["vs_bh"] > 0]
    lines.append(f"## Beat Buy-and-Hold Analysis")
    lines.append(f"Combinations that beat B&H: {len(beat_bh)} / {len(records)} ({100*len(beat_bh)/max(len(records),1):.1f}%)")
    lines.append("")
    # by strategy
    strat_beat: Dict[str, int] = {}
    strat_total: Dict[str, int] = {}
    for r in records:
        k = r["strategy"]
        strat_total[k] = strat_total.get(k, 0) + 1
        if r["vs_bh"] > 0:
            strat_beat[k] = strat_beat.get(k, 0) + 1
    lines.append(f"{'Strategy':<12} {'Beat%':>7} {'Count':>6}")
    lines.append("-" * 28)
    for sname in sorted(strat_total, key=lambda s: strat_beat.get(s, 0)/strat_total[s], reverse=True):
        beat_pct = 100 * strat_beat.get(sname, 0) / strat_total[sname]
        lines.append(f"{sname:<12} {beat_pct:>6.0f}% {strat_beat.get(sname,0):>4}/{strat_total[sname]}")
    lines.append("")

    # ── Next round recommendations ─────────────────────────────────────────
    lines.append("## Next Round Recommendations")
    lines.append("")
    top_fam = family_ranking[0][0] if family_ranking else "?"
    top_strats = [sname for sname, pt, fam, avg, mx, _mn in strat_summary[:3]]
    beat_rate  = 100 * len(beat_bh) / max(len(records), 1)
    lines.append(f"- Best performing family: *{top_fam}*")
    lines.append(f"- Top strategies to refine: {', '.join(top_strats)}")
    lines.append(f"- Overall B&H beat rate: {beat_rate:.1f}%")
    lines.append(f"- Suggested focus: parameter sweep on {top_fam} family window lengths")
    lines.append(f"- Consider: adding MACD histogram, volume-weighted signals, sector rotation")
    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by autoresearch harness round {results['round']}*")

    return "\n".join(lines)


# ── Summary report ────────────────────────────────────────────────────────────

def generate_report(results: dict, insights: str, round_dir: Path) -> str:
    """Write JSON results and markdown report to round directory."""
    # Save JSON
    json_path = round_dir / "results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)

    # Save insights
    insights_path = round_dir / "insights.md"
    insights_path.write_text(insights)

    # Save latest symlinks
    latest_json = ROOT / "latest_results.json"
    latest_md   = ROOT / "latest_insights.md"
    with open(latest_json, "w") as f:
        json.dump(results, f, indent=2)
    latest_md.write_text(insights)

    return str(json_path)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Trading Eval Harness — Autoresearch Edition")
    parser.add_argument("--symbols",    nargs="+", help="Override Fortune 100 with specific symbols")
    parser.add_argument("--strategies", nargs="+", help="Run specific strategy families only",
                        choices=["momentum","mean_reversion","trend","breakout","volatility","ml"])
    parser.add_argument("--round",      type=int,  default=None, help="Round number (auto-increments)")
    parser.add_argument("--list",       action="store_true", help="List all strategies and exit")
    parser.add_argument("--quiet",      action="store_true", help="Suppress per-ticker output")
    args = parser.parse_args()

    registry = build_strategy_registry()

    if args.list:
        print(f"\n{'Strategy':<12} {'Family':<16} Description")
        print("-" * 60)
        for name, strat in registry.items():
            print(f"{name:<12} {strat.family:<16} {strat.description}")
        print(f"\nTotal: {len(registry)} strategies × {len(POSITION_TYPES)} position types = {len(registry)*len(POSITION_TYPES)} combinations")
        print(f"Tickers: {len(FORTUNE_100)} Fortune 100 companies")
        print(f"Total backtests: {len(registry) * len(POSITION_TYPES) * len(FORTUNE_100):,}")
        return

    # Determine round number
    existing_rounds = sorted(ROUNDS_DIR.glob("round_*"))
    round_num = args.round if args.round else (len(existing_rounds) + 1)

    # Select tickers
    if args.symbols:
        tickers = {s: FORTUNE_100.get(s, s) for s in args.symbols}
    else:
        tickers = FORTUNE_100

    # Select strategies
    if args.strategies:
        strategies = {k: v for k, v in registry.items() if v.family in args.strategies}
    else:
        strategies = registry

    print(f"\n{'='*60}")
    print(f"  Autoresearch Trading Eval — Round {round_num}")
    print(f"{'='*60}")
    print(f"  Tickers   : {len(tickers)}")
    print(f"  Strategies: {len(strategies)} × {len(POSITION_TYPES)} position types")
    print(f"  Period    : {START_DATE} → {END_DATE} ({YEARS} years)")
    print(f"  Metric    : Raw Return")
    print(f"  Backtests : {len(tickers) * len(strategies) * len(POSITION_TYPES):,}")
    print(f"{'='*60}\n")

    t0 = time.time()
    results  = run_round(round_num, tickers, strategies, verbose=not args.quiet)
    elapsed  = time.time() - t0

    print(f"\n✓ Round {round_num} complete in {elapsed:.0f}s")

    insights = generate_insights(results)
    round_dir = ROUNDS_DIR / f"round_{round_num:03d}"
    json_path = generate_report(results, insights, round_dir)

    print(f"  Results : {json_path}")
    print(f"  Insights: {round_dir / 'insights.md'}")
    print(f"\n{insights[:3000]}")  # Print first 3000 chars of insights


if __name__ == "__main__":
    main()
