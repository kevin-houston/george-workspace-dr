#!/usr/bin/env python3
"""
candle_v2.py — Candlestick + Candle-Macro Harness v2 (TradeLogger)
===================================================================
Covers BOTH candle_harness.py (Round 18) and candle_macro_harness.py (Round 19)
using TradeLogger for per-trade records.

Round 18 (candle_harness.py):
  - All 26 patterns x Fortune 100 universe x hold periods [1, 3, 5, 10]
  - round_num=18, category='candle'
  - One logger per (pattern, hold_period, direction) variant

Round 19 (candle_macro_harness.py):
  - Top 10 bullish patterns x hold periods [3, 10] x 3 filter variants (A/B/C)
  - round_num=19, category='candle'
  - One logger per (pattern, hold_period, variant)

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/candle_v2.py
  /workspace/group/venv/bin/python3 trading_eval/framework/candle_v2.py --round 18
  /workspace/group/venv/bin/python3 trading_eval/framework/candle_v2.py --round 19
"""

from __future__ import annotations

import sys
import os
import argparse

sys.path.insert(0, '/workspace/group/trading_eval/framework')
sys.path.insert(0, '/workspace/group/trading_eval')

import json
import math
import pickle
import time
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f'Missing: {e}. Run: /workspace/group/venv/bin/pip install yfinance pandas numpy')
    sys.exit(1)

from base_harness import TradeLogger, fetch_data, get_close

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path('/workspace/group/trading_eval')
CACHE_DIR  = ROOT / 'cache'
MACRO_DIR  = ROOT / 'macro_cache'
CACHE_DIR.mkdir(exist_ok=True)
MACRO_DIR.mkdir(exist_ok=True)

# ── Universe (Fortune 100, exact from both harnesses) ─────────────────────────

UNIVERSE = {
    'AAPL':'Apple','MSFT':'Microsoft','GOOGL':'Alphabet','META':'Meta',
    'AMZN':'Amazon','NVDA':'NVIDIA','TSLA':'Tesla','JPM':'JPMorgan',
    'BAC':'BofA','GS':'Goldman','WFC':'Wells Fargo','XOM':'Exxon',
    'CVX':'Chevron','COP':'ConocoPhillips','HAL':'Halliburton',
    'LMT':'Lockheed','RTX':'Raytheon','NOC':'Northrop','GD':'General Dynamics',
    'WMT':'Walmart','COST':'Costco','KO':'Coca-Cola','PEP':'PepsiCo','PG':'P&G',
    'JNJ':'J&J','LLY':'Eli Lilly','MRK':'Merck','PFE':'Pfizer','UNH':'UnitedHealth',
    'CAT':'Caterpillar','DE':'Deere','GE':'GE','UPS':'UPS','BA':'Boeing',
    'F':'Ford','GM':'GM','NKE':'Nike','MO':'Altria','BRK-B':'Berkshire',
}

# Top 10 bullish patterns from R18 (as in candle_macro_harness.py)
TOP_PATTERNS_R18 = [
    'SpinningTop',
    'BullishHarami',
    'PiercingLine',
    'LongLeggedDoji',
    'MorningStar',
    'InvertedHammer',
    'TweezerBottom',
    'BullishEngulfing',
    'BullMarubozu',
    'Doji',
]

# ── OHLCV fetchers ────────────────────────────────────────────────────────────

YEARS_R18 = 15
YEARS_R19 = 7

START_R18 = (datetime.now() - timedelta(days=YEARS_R18 * 365 + 30)).strftime('%Y-%m-%d')
START_R19 = (datetime.now() - timedelta(days=YEARS_R19 * 365 + 30)).strftime('%Y-%m-%d')
END_DATE  = datetime.now().strftime('%Y-%m-%d')


def fetch_ohlcv_r18(symbol: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV for R18 (15yr). Exact logic from candle_harness.py."""
    cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{YEARS_R18}yr.pkl"
    if cp.exists():
        try:
            with open(cp, 'rb') as f:
                d = pickle.load(f)
            if isinstance(d, pd.DataFrame) and len(d) > 200:
                return d
        except Exception:
            pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_R18, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        h = h[['Open','High','Low','Close','Volume']].dropna()
        with open(cp, 'wb') as f:
            pickle.dump(h, f)
        return h
    except Exception as e:
        print(f'  {symbol}: {e}', file=sys.stderr)
        return None


def fetch_ohlcv_r19(symbol: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV for R19 (7yr), reusing R18 cache if available. Exact logic from candle_macro_harness.py."""
    for years_tag in [YEARS_R19, YEARS_R18]:
        cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{years_tag}yr.pkl"
        if cp.exists():
            try:
                with open(cp, 'rb') as f:
                    d = pickle.load(f)
                if isinstance(d, pd.DataFrame) and len(d) > 200:
                    cutoff = pd.Timestamp(START_R19)
                    if d.index.tz is not None:
                        cutoff = cutoff.tz_localize(d.index.tz)
                    return d[d.index >= cutoff]
            except Exception:
                pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_R19, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        h = h[['Open','High','Low','Close','Volume']].dropna()
        cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{YEARS_R19}yr.pkl"
        with open(cp, 'wb') as f:
            pickle.dump(h, f)
        return h
    except Exception as e:
        print(f'  {symbol}: {e}', file=sys.stderr)
        return None


# ── Candlestick pattern detector base (exact from candle_harness.py) ──────────

class CandlePattern(ABC):
    name:        str = 'base'
    category:    str = 'single'
    signal_type: str = 'bullish'

    @abstractmethod
    def detect(self, ohlcv: pd.DataFrame) -> pd.Series:
        pass

    def body(self, ohlcv):
        return (ohlcv['Close'] - ohlcv['Open']).abs()

    def full_range(self, ohlcv):
        return ohlcv['High'] - ohlcv['Low']

    def upper_shadow(self, ohlcv):
        return ohlcv['High'] - ohlcv[['Open','Close']].max(axis=1)

    def lower_shadow(self, ohlcv):
        return ohlcv[['Open','Close']].min(axis=1) - ohlcv['Low']

    def is_bull(self, ohlcv):
        return ohlcv['Close'] > ohlcv['Open']

    def is_bear(self, ohlcv):
        return ohlcv['Close'] < ohlcv['Open']

    def atr(self, ohlcv, window=14):
        hl = ohlcv['High'] - ohlcv['Low']
        hc = (ohlcv['High'] - ohlcv['Close'].shift()).abs()
        lc = (ohlcv['Low']  - ohlcv['Close'].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(window).mean()


class Doji(CandlePattern):
    name, category, signal_type = 'Doji', 'single', 'both'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        ratio = body / rng
        sig   = pd.Series(0, index=df.index, dtype=float)
        trend = df['Close'].pct_change(5)
        doji_days = ratio < 0.05
        sig[doji_days & (trend < -0.02)] =  1
        sig[doji_days & (trend >  0.02)] = -1
        return sig


class LongLeggedDoji(CandlePattern):
    name, category, signal_type = 'LongLeggedDoji', 'single', 'both'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        b_rng = body / rng
        sig   = pd.Series(0, index=df.index, dtype=float)
        trend = df['Close'].pct_change(5)
        mask  = (b_rng < 0.05) & (us > body) & (ls > body)
        sig[mask & (trend < 0)] =  1
        sig[mask & (trend > 0)] = -1
        return sig


class Hammer(CandlePattern):
    name, category, signal_type = 'Hammer', 'single', 'bullish'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (ls >= 2 * body.replace(0, np.nan)) &
            (us <= 0.1 * rng) &
            (trend < -0.03)
        )
        sig[mask] = 1
        return sig


class HangingMan(CandlePattern):
    name, category, signal_type = 'HangingMan', 'single', 'bearish'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (ls >= 2 * body.replace(0, np.nan)) &
            (us <= 0.1 * rng) &
            (trend > 0.03)
        )
        sig[mask] = -1
        return sig


class ShootingStar(CandlePattern):
    name, category, signal_type = 'ShootingStar', 'single', 'bearish'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (us >= 2 * body.replace(0, np.nan)) &
            (ls <= 0.1 * rng) &
            (trend > 0.03)
        )
        sig[mask] = -1
        return sig


class InvertedHammer(CandlePattern):
    name, category, signal_type = 'InvertedHammer', 'single', 'bullish'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (us >= 2 * body.replace(0, np.nan)) &
            (ls <= 0.1 * rng) &
            (trend < -0.03)
        )
        sig[mask] = 1
        return sig


class BullMarubozu(CandlePattern):
    name, category, signal_type = 'BullMarubozu', 'single', 'bullish'

    def detect(self, df):
        body = self.body(df)
        rng  = self.full_range(df).replace(0, np.nan)
        bull = self.is_bull(df)
        sig  = pd.Series(0, index=df.index, dtype=float)
        sig[(body/rng > 0.92) & bull] = 1
        return sig


class BearMarubozu(CandlePattern):
    name, category, signal_type = 'BearMarubozu', 'single', 'bearish'

    def detect(self, df):
        body = self.body(df)
        rng  = self.full_range(df).replace(0, np.nan)
        bear = self.is_bear(df)
        sig  = pd.Series(0, index=df.index, dtype=float)
        sig[(body/rng > 0.92) & bear] = -1
        return sig


class SpinningTop(CandlePattern):
    name, category, signal_type = 'SpinningTop', 'single', 'both'

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df['Close'].pct_change(5)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (body/rng < 0.3) & (us > body) & (ls > body)
        sig[mask & (trend < -0.02)] =  1
        sig[mask & (trend >  0.02)] = -1
        return sig


class BullishEngulfing(CandlePattern):
    name, category, signal_type = 'BullishEngulfing', 'two-candle', 'bullish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        engulfs   = (o <= c.shift(1)) & (c >= o.shift(1))
        trend     = c.pct_change(10)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bear & curr_bull & engulfs & (trend < -0.02)] = 1
        return sig


class BearishEngulfing(CandlePattern):
    name, category, signal_type = 'BearishEngulfing', 'two-candle', 'bearish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        prev_bull = c.shift(1) > o.shift(1)
        curr_bear = c < o
        engulfs   = (o >= c.shift(1)) & (c <= o.shift(1))
        trend     = c.pct_change(10)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bull & curr_bear & engulfs & (trend > 0.02)] = -1
        return sig


class BullishHarami(CandlePattern):
    name, category, signal_type = 'BullishHarami', 'two-candle', 'bullish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        prev_body_hi = df[['Open','Close']].shift(1).max(axis=1)
        prev_body_lo = df[['Open','Close']].shift(1).min(axis=1)
        curr_body_hi = df[['Open','Close']].max(axis=1)
        curr_body_lo = df[['Open','Close']].min(axis=1)
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        inside    = (curr_body_hi < prev_body_hi) & (curr_body_lo > prev_body_lo)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bear & curr_bull & inside] = 1
        return sig


class BearishHarami(CandlePattern):
    name, category, signal_type = 'BearishHarami', 'two-candle', 'bearish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        prev_body_hi = df[['Open','Close']].shift(1).max(axis=1)
        prev_body_lo = df[['Open','Close']].shift(1).min(axis=1)
        curr_body_hi = df[['Open','Close']].max(axis=1)
        curr_body_lo = df[['Open','Close']].min(axis=1)
        prev_bull = c.shift(1) > o.shift(1)
        curr_bear = c < o
        inside    = (curr_body_hi < prev_body_hi) & (curr_body_lo > prev_body_lo)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bull & curr_bear & inside] = -1
        return sig


class TweezerBottom(CandlePattern):
    name, category, signal_type = 'TweezerBottom', 'two-candle', 'bullish'

    def detect(self, df):
        lo    = df['Low']
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        same_low = (lo - lo.shift(1)).abs() / lo.replace(0, np.nan) < 0.002
        sig[same_low & self.is_bull(df) & (trend < -0.02)] = 1
        return sig


class TweezerTop(CandlePattern):
    name, category, signal_type = 'TweezerTop', 'two-candle', 'bearish'

    def detect(self, df):
        hi    = df['High']
        trend = df['Close'].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        same_high = (hi - hi.shift(1)).abs() / hi.replace(0, np.nan) < 0.002
        sig[same_high & self.is_bear(df) & (trend > 0.02)] = -1
        return sig


class PiercingLine(CandlePattern):
    name, category, signal_type = 'PiercingLine', 'two-candle', 'bullish'

    def detect(self, df):
        o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bear = c.shift(1) < o.shift(1)
        day2_bull = c > o
        opens_low = o < l.shift(1)
        closes_above_mid = c > mid1
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[day1_bear & day2_bull & opens_low & closes_above_mid] = 1
        return sig


class DarkCloudCover(CandlePattern):
    name, category, signal_type = 'DarkCloudCover', 'two-candle', 'bearish'

    def detect(self, df):
        o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bull = c.shift(1) > o.shift(1)
        day2_bear = c < o
        opens_high = o > h.shift(1)
        closes_below_mid = c < mid1
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[day1_bull & day2_bear & opens_high & closes_below_mid] = -1
        return sig


class MorningStar(CandlePattern):
    name, category, signal_type = 'MorningStar', 'three-candle', 'bullish'

    def detect(self, df):
        o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        d1_bear  = (c.shift(2) < o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        d2_small = body.shift(1) / rng.shift(1) < 0.3
        d2_gap   = df[['Open','Close']].shift(1).max(axis=1) < c.shift(2)
        d3_bull  = (c > o) & (body/rng > 0.4)
        d3_close = c > (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bear & d2_small & d3_bull & d3_close] = 1
        return sig


class EveningStar(CandlePattern):
    name, category, signal_type = 'EveningStar', 'three-candle', 'bearish'

    def detect(self, df):
        o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        d1_bull  = (c.shift(2) > o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        d2_small = body.shift(1)/rng.shift(1) < 0.3
        d2_gap   = df[['Open','Close']].shift(1).min(axis=1) > c.shift(2)
        d3_bear  = (c < o) & (body/rng > 0.4)
        d3_close = c < (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bull & d2_small & d3_bear & d3_close] = -1
        return sig


class ThreeWhiteSoldiers(CandlePattern):
    name, category, signal_type = 'ThreeWhiteSoldiers', 'three-candle', 'bullish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        bull1 = (c.shift(2) > o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        bull2 = (c.shift(1) > o.shift(1)) & (body.shift(1)/rng.shift(1) > 0.5)
        bull3 = (c > o)                    & (body/rng > 0.5)
        open2_in = (o.shift(1) > o.shift(2)) & (o.shift(1) < c.shift(2))
        open3_in = (o > o.shift(1))           & (o < c.shift(1))
        consecutive = c.shift(2) < c.shift(1)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[bull1 & bull2 & bull3 & open2_in & open3_in & consecutive] = 1
        return sig


class ThreeBlackCrows(CandlePattern):
    name, category, signal_type = 'ThreeBlackCrows', 'three-candle', 'bearish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        bear1 = (c.shift(2) < o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        bear2 = (c.shift(1) < o.shift(1)) & (body.shift(1)/rng.shift(1) > 0.5)
        bear3 = (c < o)                    & (body/rng > 0.5)
        open2_in = (o.shift(1) < o.shift(2)) & (o.shift(1) > c.shift(2))
        open3_in = (o < o.shift(1))           & (o > c.shift(1))
        consecutive = c.shift(2) > c.shift(1)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[bear1 & bear2 & bear3 & open2_in & open3_in & consecutive] = -1
        return sig


class MorningDojiStar(CandlePattern):
    name, category, signal_type = 'MorningDojiStar', 'three-candle', 'bullish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        d1_bear  = (c.shift(2) < o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        d2_doji  = body.shift(1)/rng.shift(1) < 0.05
        d3_bull  = (c > o) & (body/rng > 0.4)
        d3_close = c > (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bear & d2_doji & d3_bull & d3_close] = 1
        return sig


class EveningDojiStar(CandlePattern):
    name, category, signal_type = 'EveningDojiStar', 'three-candle', 'bearish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        d1_bull  = (c.shift(2) > o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        d2_doji  = body.shift(1)/rng.shift(1) < 0.05
        d3_bear  = (c < o) & (body/rng > 0.4)
        d3_close = c < (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bull & d2_doji & d3_bear & d3_close] = -1
        return sig


class ThreeInsideUp(CandlePattern):
    name, category, signal_type = 'ThreeInsideUp', 'three-candle', 'bullish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        d1_bear = c.shift(2) < o.shift(2)
        d2_bull_inside = (
            (c.shift(1) > o.shift(1)) &
            (c.shift(1) < o.shift(2)) &
            (o.shift(1) > c.shift(2))
        )
        d3_confirm = c > o.shift(2)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bear & d2_bull_inside & d3_confirm] = 1
        return sig


class ThreeInsideDown(CandlePattern):
    name, category, signal_type = 'ThreeInsideDown', 'three-candle', 'bearish'

    def detect(self, df):
        o, c = df['Open'], df['Close']
        d1_bull = c.shift(2) > o.shift(2)
        d2_bear_inside = (
            (c.shift(1) < o.shift(1)) &
            (c.shift(1) > o.shift(2)) &
            (o.shift(1) < c.shift(2))
        )
        d3_confirm = c < o.shift(2)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bull & d2_bear_inside & d3_confirm] = -1
        return sig


# Pattern registry (exact from candle_harness.py)
ALL_PATTERNS = [
    Doji(), LongLeggedDoji(), Hammer(), HangingMan(),
    ShootingStar(), InvertedHammer(), BullMarubozu(), BearMarubozu(),
    SpinningTop(),
    BullishEngulfing(), BearishEngulfing(),
    BullishHarami(), BearishHarami(),
    TweezerBottom(), TweezerTop(),
    PiercingLine(), DarkCloudCover(),
    MorningStar(), EveningStar(),
    ThreeWhiteSoldiers(), ThreeBlackCrows(),
    MorningDojiStar(), EveningDojiStar(),
    ThreeInsideUp(), ThreeInsideDown(),
]

HOLD_PERIODS_R18 = [1, 3, 5, 10]
HOLD_PERIODS_R19 = [3, 10]


# ── detect_pattern function (exact from candle_macro_harness.py, for R19) ─────

def detect_pattern_r19(name: str, df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['Open'], df['High'], df['Low'], df['Close']
    body    = (c - o).abs()
    rng     = (h - l).replace(0, np.nan)
    us      = h - df[['Open','Close']].max(axis=1)
    ls      = df[['Open','Close']].min(axis=1) - l
    trend5  = c.pct_change(5)
    trend10 = c.pct_change(10)
    sig     = pd.Series(0.0, index=df.index)

    if name == 'SpinningTop':
        mask = (body/rng < 0.3) & (us > body) & (ls > body)
        sig[mask & (trend5 < -0.02)] = 1
    elif name == 'BullishHarami':
        prev_bhi = df[['Open','Close']].shift(1).max(axis=1)
        prev_blo = df[['Open','Close']].shift(1).min(axis=1)
        curr_bhi = df[['Open','Close']].max(axis=1)
        curr_blo = df[['Open','Close']].min(axis=1)
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        inside    = (curr_bhi < prev_bhi) & (curr_blo > prev_blo)
        sig[prev_bear & curr_bull & inside] = 1
    elif name == 'PiercingLine':
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bear = c.shift(1) < o.shift(1)
        day2_bull = c > o
        opens_low = o < l.shift(1)
        closes_above_mid = c > mid1
        sig[day1_bear & day2_bull & opens_low & closes_above_mid] = 1
    elif name == 'LongLeggedDoji':
        b_rng = body / rng
        mask  = (b_rng < 0.05) & (us > body) & (ls > body)
        sig[mask & (trend5 < 0)] = 1
    elif name == 'MorningStar':
        body2 = body.shift(2); rng2 = rng.shift(2)
        d1_bear  = (c.shift(2) < o.shift(2)) & (body2/rng2 > 0.5)
        d2_small = body.shift(1) / rng.shift(1) < 0.3
        d2_gap   = df[['Open','Close']].shift(1).max(axis=1) < c.shift(2)
        d3_bull  = (c > o) & (body/rng > 0.4)
        d3_close = c > (o.shift(2) + c.shift(2)) / 2
        sig[d1_bear & d2_small & d3_bull & d3_close] = 1
    elif name == 'InvertedHammer':
        mask = (
            (body / rng < 0.35) &
            (us >= 2 * body.replace(0, np.nan)) &
            (ls <= 0.1 * rng) &
            (trend10 < -0.03)
        )
        sig[mask] = 1
    elif name == 'TweezerBottom':
        same_low = (l - l.shift(1)).abs() / l.replace(0, np.nan) < 0.002
        sig[same_low & (c > o) & (trend10 < -0.02)] = 1
    elif name == 'BullishEngulfing':
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        engulfs   = (o <= c.shift(1)) & (c >= o.shift(1))
        sig[prev_bear & curr_bull & engulfs & (trend10 < -0.02)] = 1
    elif name == 'BullMarubozu':
        sig[(body/rng > 0.92) & (c > o)] = 1
    elif name == 'Doji':
        doji_days = body / rng < 0.05
        sig[doji_days & (trend5 < -0.02)] = 1

    return sig


# ── Backtest engine (exact from candle_harness.py) ────────────────────────────

def backtest_hold_trades(ohlcv: pd.DataFrame, entry_signals: pd.Series,
                         hold_days: int, direction: str = 'long') -> List[dict]:
    """
    Entry on signal day close, exit after hold_days.
    Returns list of per-trade dicts with entry_date, exit_date, return_pct, etc.
    """
    prices = ohlcv['Close']
    common = prices.index.intersection(entry_signals.index)
    if len(common) < 50:
        return []

    p   = prices.loc[common]
    sig = entry_signals.reindex(common).fillna(0).shift(1)  # next-day entry

    sig_idx = sig[sig != 0].index
    trades  = []

    for idx in sig_idx:
        loc = common.get_loc(idx)
        end = min(loc + hold_days, len(common) - 1)
        if end <= loc:
            continue

        entry_date  = common[loc]
        exit_date   = common[end]
        entry_price = float(p.iloc[loc])
        exit_price  = float(p.iloc[end])
        hold_actual = (exit_date - entry_date).days

        if direction == 'long':
            ret_pct = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0.0
        else:
            ret_pct = (entry_price / exit_price - 1) * 100 if exit_price > 0 else 0.0

        trades.append({
            'entry_date':  entry_date,
            'exit_date':   exit_date,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'return_pct':  float(ret_pct),
            'hold_days':   int(max(hold_actual, 1)),
            'direction':   direction,
        })

    return trades


# ── Macro regime builder (exact from candle_macro_harness.py) ─────────────────

def fetch_fred_r19(series_id: str, api_key: str) -> Optional[pd.Series]:
    cp = MACRO_DIR / f'fred_{series_id}.pkl'
    if cp.exists():
        try:
            with open(cp, 'rb') as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series) and len(s) > 50:
                return s
        except Exception:
            pass
    if not api_key:
        return None
    try:
        params = urllib.parse.urlencode({
            'series_id':       series_id,
            'api_key':         api_key,
            'file_type':       'json',
            'observation_start': '2010-01-01',
        })
        url = f'https://api.stlouisfed.org/fred/series/observations?{params}'
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        obs = data.get('observations', [])
        if not obs:
            return None
        idx  = pd.to_datetime([o['date'] for o in obs])
        vals = pd.to_numeric([o['value'] for o in obs], errors='coerce')
        s    = pd.Series(vals.values, index=idx, name=series_id).dropna()
        with open(cp, 'wb') as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f'  FRED {series_id}: {e}', file=sys.stderr)
        return None


def fetch_yfinance_macro_r19(symbol: str, name: str) -> Optional[pd.Series]:
    cp = MACRO_DIR / f'yf_{name}.pkl'
    if cp.exists():
        try:
            with open(cp, 'rb') as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series) and len(s) > 50:
                return s
        except Exception:
            pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start='2010-01-01', end=END_DATE, auto_adjust=True)
        if h.empty:
            return None
        s = h['Close'].rename(name)
        with open(cp, 'wb') as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f'  yf {symbol}: {e}', file=sys.stderr)
        return None


def load_macro_r19(api_key: str) -> dict:
    print('  Loading macro data for R19...')
    macro = {}
    fred_series = {
        'DCOILWTICO':    'WTI Crude',
        'CPIAUCSL':      'CPI',
        'T10YIE':        '10yr Breakeven',
        'DFF':           'Fed Funds',
        'T10Y2Y':        '10yr-2yr Spread',
        'BAMLH0A0HYM2':  'HY Spread',
        'VIXCLS':        'VIX',
        'GOLDAMGBD228NLBM': 'Gold Fix',
    }
    for sid, label in fred_series.items():
        s = fetch_fred_r19(sid, api_key)
        if s is not None and len(s) > 50:
            macro[sid] = s
            print(f'    FRED {label} ({len(s)} obs)')
        else:
            print(f'    FRED {label} -- trying yfinance fallback')

    fallbacks = {
        'DCOILWTICO':    ('CL=F',  'Oil WTI'),
        'VIXCLS':        ('^VIX',  'VIX'),
        'GOLDAMGBD228NLBM': ('GC=F', 'Gold'),
        'T10Y2Y':        ('^TNX',  '10yr Yield'),
    }
    for fred_id, (yf_sym, yf_name) in fallbacks.items():
        if fred_id not in macro:
            s = fetch_yfinance_macro_r19(yf_sym, fred_id)
            if s is not None:
                macro[fred_id] = s
                print(f'    yfinance {yf_name} (fallback)')

    return macro


def build_regime_index_r19(macro: dict, price_index: pd.DatetimeIndex) -> pd.DataFrame:
    if price_index.tz is not None:
        align_idx = price_index.tz_localize(None)
    else:
        align_idx = price_index

    frames = {}
    for k, s in macro.items():
        if hasattr(s.index, 'tz') and s.index.tz is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        frames[k] = s.reindex(align_idx, method='ffill')

    mf = pd.DataFrame(frames, index=align_idx)
    return classify_regimes_r19(mf)


def classify_regimes_r19(mf: pd.DataFrame) -> pd.DataFrame:
    regimes = pd.DataFrame(index=mf.index)

    oil_col = 'DCOILWTICO'
    if oil_col in mf.columns and mf[oil_col].notna().sum() > 90:
        oil = mf[oil_col].ffill()
        rm  = oil.rolling(90, min_periods=30).mean()
        rs  = oil.rolling(90, min_periods=30).std()
        regimes['oil_shock'] = oil > (rm + 1.5 * rs)
        regimes['oil_high']  = oil > rm
    else:
        regimes['oil_shock'] = False
        regimes['oil_high']  = False

    if 'CPIAUCSL' in mf.columns and mf['CPIAUCSL'].notna().sum() > 12:
        cpi = mf['CPIAUCSL'].ffill()
        cpi_yoy = cpi.pct_change(252) * 100
        regimes['inflationary'] = cpi_yoy > 3.5
    elif 'T10YIE' in mf.columns and mf['T10YIE'].notna().sum() > 90:
        bie = mf['T10YIE'].ffill()
        regimes['inflationary'] = bie > 2.8
    else:
        regimes['inflationary'] = False

    stress = pd.Series(False, index=mf.index)
    if 'VIXCLS' in mf.columns and mf['VIXCLS'].notna().sum() > 90:
        stress |= (mf['VIXCLS'].ffill() > 25)
    if 'BAMLH0A0HYM2' in mf.columns and mf['BAMLH0A0HYM2'].notna().sum() > 90:
        stress |= (mf['BAMLH0A0HYM2'].ffill() > 500)
    regimes['stress']     = stress
    regimes['low_stress'] = ~stress

    tight = pd.Series(False, index=mf.index)
    if 'T10Y2Y' in mf.columns and mf['T10Y2Y'].notna().sum() > 90:
        tight |= (mf['T10Y2Y'].ffill() < 0)
    if 'DFF' in mf.columns and mf['DFF'].notna().sum() > 90:
        ff = mf['DFF'].ffill()
        ff_trend = ff - ff.shift(126)
        tight |= (ff_trend > 0.25)
        regimes['easing'] = ff_trend < -0.25
    else:
        regimes['easing'] = False
    regimes['tightening'] = tight

    regimes['calm'] = (
        ~regimes['oil_shock'] &
        ~regimes['inflationary'] &
        ~regimes['stress'] &
        ~regimes['tightening']
    )
    regimes['favorable'] = (
        regimes['calm'] |
        (regimes['easing'] & regimes['low_stress'])
    )
    regimes['unfavorable'] = (
        regimes['oil_shock'] |
        regimes['stress'] |
        regimes['tightening']
    )

    return regimes.fillna(False)


# ── R19 filtered backtest (exact logic from candle_macro_harness.py) ──────────

def backtest_filtered_r19(ohlcv: pd.DataFrame, signals: pd.Series,
                           regime_mask: Optional[pd.Series],
                           hold_days: int) -> List[dict]:
    """
    Backtest bullish signals with optional regime mask.
    Returns per-trade dicts.
    """
    prices = ohlcv['Close']
    common = prices.index
    if common.tz is not None:
        common_tz_naive = common.tz_localize(None)
    else:
        common_tz_naive = common

    sig = signals.copy()
    if sig.index.tz is not None:
        sig.index = sig.index.tz_localize(None)
    sig = sig.reindex(common_tz_naive, fill_value=0).shift(1).fillna(0)

    if regime_mask is not None:
        rm = regime_mask.copy()
        if rm.index.tz is not None:
            rm.index = rm.index.tz_localize(None)
        rm  = rm.reindex(common_tz_naive, method='ffill').fillna(False)
        sig = sig * rm.astype(float)

    prices_tz = prices.copy()
    prices_tz.index = common_tz_naive

    sig_idx = sig[sig > 0].index
    trades  = []

    for idx in sig_idx:
        try:
            loc = common_tz_naive.get_loc(idx)
        except KeyError:
            continue
        end = min(loc + hold_days, len(common_tz_naive) - 1)
        if end <= loc:
            continue

        entry_date  = common_tz_naive[loc]
        exit_date   = common_tz_naive[end]
        entry_price = float(prices_tz.iloc[loc])
        exit_price  = float(prices_tz.iloc[end])
        hold_actual = (exit_date - entry_date).days
        ret_pct     = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0.0

        trades.append({
            'entry_date':  entry_date,
            'exit_date':   exit_date,
            'entry_price': entry_price,
            'exit_price':  exit_price,
            'return_pct':  float(ret_pct),
            'hold_days':   int(max(hold_actual, 1)),
            'direction':   'long',
        })

    return trades


# ── Round 18 runner ───────────────────────────────────────────────────────────

def run_round_18() -> None:
    """
    Run candle_harness.py equivalent as TradeLogger round 18.
    One logger per (pattern_name, hold_period, direction).
    """
    print('=' * 70)
    print('CANDLE V2 — ROUND 18: Candlestick Pattern Backtest (TradeLogger)')
    total = len(ALL_PATTERNS) * len(UNIVERSE) * len(HOLD_PERIODS_R18) * 2
    print(f'{len(ALL_PATTERNS)} patterns x {len(UNIVERSE)} tickers x '
          f'{len(HOLD_PERIODS_R18)} hold periods x 2 directions = {total:,} backtests')
    print('=' * 70)

    # Build loggers: key = (pattern_name, hold_days, direction)
    loggers: Dict[tuple, TradeLogger] = {}
    for pat in ALL_PATTERNS:
        for hold in HOLD_PERIODS_R18:
            for direction in ['long', 'short']:
                key = (pat.name, hold, direction)
                strat_name = f'{pat.name}_h{hold}_{direction}'
                loggers[key] = TradeLogger(
                    round_num=18,
                    strategy=strat_name,
                    category='candle',
                )

    done = 0
    for sym in UNIVERSE:
        ohlcv = fetch_ohlcv_r18(sym)
        if ohlcv is None:
            continue

        for pat in ALL_PATTERNS:
            try:
                sigs = pat.detect(ohlcv)
            except Exception:
                continue

            bull_sigs = sigs.clip(lower=0)
            bear_sigs = (-sigs).clip(lower=0)

            for hold in HOLD_PERIODS_R18:
                if (bull_sigs > 0).any():
                    for t in backtest_hold_trades(ohlcv, bull_sigs, hold, 'long'):
                        key = (pat.name, hold, 'long')
                        loggers[key].log(
                            ticker      = sym,
                            entry_date  = t['entry_date'],
                            exit_date   = t['exit_date'],
                            return_pct  = t['return_pct'],
                            hold_days   = t['hold_days'],
                            direction   = 'long',
                            entry_price = t['entry_price'],
                            exit_price  = t['exit_price'],
                            params      = {
                                'pattern':    pat.name,
                                'category':   pat.category,
                                'signal':     'bullish',
                                'hold_days':  hold,
                            },
                            pattern_category = pat.category,
                            signal_type      = 'bullish',
                            notes       = f'{pat.name} bullish signal, {hold}d hold',
                        )

                if (bear_sigs > 0).any():
                    for t in backtest_hold_trades(ohlcv, bear_sigs, hold, 'short'):
                        key = (pat.name, hold, 'short')
                        loggers[key].log(
                            ticker      = sym,
                            entry_date  = t['entry_date'],
                            exit_date   = t['exit_date'],
                            return_pct  = t['return_pct'],
                            hold_days   = t['hold_days'],
                            direction   = 'short',
                            entry_price = t['entry_price'],
                            exit_price  = t['exit_price'],
                            params      = {
                                'pattern':    pat.name,
                                'category':   pat.category,
                                'signal':     'bearish',
                                'hold_days':  hold,
                            },
                            pattern_category = pat.category,
                            signal_type      = 'bearish',
                            notes       = f'{pat.name} bearish signal, {hold}d hold',
                        )

            done += 1
            if done % 100 == 0:
                print(f'  Progress: {done} ticker-pattern combos done')

    total_trades = 0
    for key, logger in loggers.items():
        if len(logger) > 0:
            logger.save()
            total_trades += len(logger)

    print(f'\nRound 18 complete: {total_trades} trades logged across active loggers.')


# ── Round 19 runner ───────────────────────────────────────────────────────────

def run_round_19() -> None:
    """
    Run candle_macro_harness.py equivalent as TradeLogger round 19.
    One logger per (pattern_name, hold_period, variant).
    Variants: A=unfiltered, B=favorable, C=unfavorable.
    """
    print('=' * 72)
    print('CANDLE V2 — ROUND 19: Candlestick x Macro Regime Filter (TradeLogger)')
    total = len(TOP_PATTERNS_R18) * len(HOLD_PERIODS_R19) * len(UNIVERSE) * 3
    print(f'Top 10 patterns x 2 hold periods x 3 variants x {len(UNIVERSE)} tickers = {total:,} backtests')
    print('=' * 72)

    api_key = os.environ.get('FRED_API_KEY', '')
    if not api_key:
        print('  FRED_API_KEY not set -- using cached data only')

    macro = load_macro_r19(api_key)
    print(f'  Macro series loaded: {len(macro)}')

    # Build regime index using reference stock
    print('\n  Building regime index...')
    ref_data = fetch_ohlcv_r19('AAPL')
    if ref_data is None:
        ref_data = fetch_ohlcv_r19(list(UNIVERSE.keys())[0])

    regimes = build_regime_index_r19(macro, ref_data.index)
    fav_pct   = float(regimes['favorable'].mean() * 100)
    unfav_pct = float(regimes['unfavorable'].mean() * 100)
    calm_pct  = float(regimes['calm'].mean() * 100)
    print(f'  Regime coverage: favorable={fav_pct:.1f}%  unfavorable={unfav_pct:.1f}%  calm={calm_pct:.1f}%')

    # Build loggers: key = (pattern_name, hold_days, variant)
    loggers: Dict[tuple, TradeLogger] = {}
    for pat_name in TOP_PATTERNS_R18:
        for hold in HOLD_PERIODS_R19:
            for variant in ['A', 'B', 'C']:
                key = (pat_name, hold, variant)
                strat_name = f'R19_{pat_name}_h{hold}_v{variant}'
                loggers[key] = TradeLogger(
                    round_num=19,
                    strategy=strat_name,
                    category='candle',
                )

    done = 0
    for sym in UNIVERSE:
        ohlcv = fetch_ohlcv_r19(sym)
        if ohlcv is None:
            continue

        for pat_name in TOP_PATTERNS_R18:
            try:
                sigs = detect_pattern_r19(pat_name, ohlcv)
            except Exception as e:
                continue

            for hold in HOLD_PERIODS_R19:
                # Variant A: unfiltered
                for t in backtest_filtered_r19(ohlcv, sigs, None, hold):
                    loggers[(pat_name, hold, 'A')].log(
                        ticker=sym, entry_date=t['entry_date'], exit_date=t['exit_date'],
                        return_pct=t['return_pct'], hold_days=t['hold_days'],
                        direction='long', entry_price=t['entry_price'], exit_price=t['exit_price'],
                        params={'pattern': pat_name, 'hold': hold, 'variant': 'A', 'filter': 'none'},
                        regime_filter='unfiltered',
                        notes=f'{pat_name} {hold}d unfiltered',
                    )
                # Variant B: favorable regime only
                for t in backtest_filtered_r19(ohlcv, sigs, regimes['favorable'], hold):
                    loggers[(pat_name, hold, 'B')].log(
                        ticker=sym, entry_date=t['entry_date'], exit_date=t['exit_date'],
                        return_pct=t['return_pct'], hold_days=t['hold_days'],
                        direction='long', entry_price=t['entry_price'], exit_price=t['exit_price'],
                        params={'pattern': pat_name, 'hold': hold, 'variant': 'B', 'filter': 'favorable'},
                        regime_filter='favorable',
                        notes=f'{pat_name} {hold}d favorable regime only',
                    )
                # Variant C: unfavorable regime only
                for t in backtest_filtered_r19(ohlcv, sigs, regimes['unfavorable'], hold):
                    loggers[(pat_name, hold, 'C')].log(
                        ticker=sym, entry_date=t['entry_date'], exit_date=t['exit_date'],
                        return_pct=t['return_pct'], hold_days=t['hold_days'],
                        direction='long', entry_price=t['entry_price'], exit_price=t['exit_price'],
                        params={'pattern': pat_name, 'hold': hold, 'variant': 'C', 'filter': 'unfavorable'},
                        regime_filter='unfavorable',
                        notes=f'{pat_name} {hold}d unfavorable regime only',
                    )
                done += 3

        if done % 1500 == 0 and done > 0:
            print(f'  Progress: {done:,}/{total:,} ({done/total*100:.0f}%)')

    total_trades = 0
    for key, logger in loggers.items():
        if len(logger) > 0:
            logger.save()
            total_trades += len(logger)

    print(f'\nRound 19 complete: {total_trades} trades logged across active loggers.')


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Candle V2 — TradeLogger harness (R18+R19)')
    parser.add_argument('--round', type=int, choices=[18, 19],
                        help='Run only round 18 or 19 (default: both)')
    args = parser.parse_args()

    if args.round == 18:
        run_round_18()
    elif args.round == 19:
        run_round_19()
    else:
        run_round_18()
        run_round_19()

    print('\nDone. Trade logs written to /workspace/group/trading_eval/trade_logs/')


if __name__ == '__main__':
    main()
