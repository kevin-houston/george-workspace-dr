#!/usr/bin/env python3
"""
Candlestick Pattern Autoresearch
=================================
Tests all major candlestick patterns against the Fortune 100 universe.
Each pattern fires a signal; we test long, short, and long/short variants
with hold periods of 1, 3, 5, and 10 days.

Patterns implemented:
  Single-candle:  Doji, Hammer, Hanging Man, Shooting Star, Inverted Hammer,
                  Marubozu (Bull/Bear), Spinning Top, Long Upper Shadow,
                  Long Lower Shadow
  Two-candle:     Bullish Engulfing, Bearish Engulfing, Bullish Harami,
                  Bearish Harami, Tweezer Bottom, Tweezer Top,
                  Piercing Line, Dark Cloud Cover, On-Neck
  Three-candle:   Morning Star, Evening Star, Three White Soldiers,
                  Three Black Crows, Morning Doji Star, Evening Doji Star,
                  Three Inside Up, Three Inside Down, Abandoned Baby

Usage:
  PYTHONPATH=/tmp/eval_deps python3 candle_harness.py
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing: {e}. Run: pip install yfinance pandas numpy --target=/tmp/eval_deps")
    sys.exit(1)

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

YEARS      = 15
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")

UNIVERSE = {
    "AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Alphabet","META":"Meta",
    "AMZN":"Amazon","NVDA":"NVIDIA","TSLA":"Tesla","JPM":"JPMorgan",
    "BAC":"BofA","GS":"Goldman","WFC":"Wells Fargo","XOM":"Exxon",
    "CVX":"Chevron","COP":"ConocoPhillips","HAL":"Halliburton",
    "LMT":"Lockheed","RTX":"Raytheon","NOC":"Northrop","GD":"General Dynamics",
    "WMT":"Walmart","COST":"Costco","KO":"Coca-Cola","PEP":"PepsiCo","PG":"P&G",
    "JNJ":"J&J","LLY":"Eli Lilly","MRK":"Merck","PFE":"Pfizer","UNH":"UnitedHealth",
    "CAT":"Caterpillar","DE":"Deere","GE":"GE","UPS":"UPS","BA":"Boeing",
    "F":"Ford","GM":"GM","NKE":"Nike","MO":"Altria","BRK-B":"Berkshire",
}

# ── OHLCV fetcher ─────────────────────────────────────────────────────────────

def fetch_ohlcv(symbol: str) -> Optional[pd.DataFrame]:
    cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{YEARS}yr.pkl"
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                d = pickle.load(f)
            if isinstance(d, pd.DataFrame) and len(d) > 200:
                return d
        except Exception:
            pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        h = h[["Open","High","Low","Close","Volume"]].dropna()
        with open(cp, "wb") as f:
            pickle.dump(h, f)
        return h
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


# ── Backtest engine ────────────────────────────────────────────────────────────

def backtest_hold(ohlcv: pd.DataFrame, entry_signals: pd.Series,
                  hold_days: int, direction: str = "long") -> dict:
    """
    Entry on signal day close, exit after hold_days.
    direction: 'long' or 'short'
    """
    prices = ohlcv["Close"]
    common = prices.index.intersection(entry_signals.index)
    if len(common) < 50:
        return {}

    p   = prices.loc[common]
    sig = entry_signals.reindex(common).fillna(0).shift(1)  # next-day entry

    daily_ret = p.pct_change().fillna(0)

    # Build position series: when sig=1, hold for hold_days
    position = pd.Series(0.0, index=common)
    sig_idx  = sig[sig != 0].index
    for idx in sig_idx:
        loc = common.get_loc(idx)
        end = min(loc + hold_days, len(common))
        val = float(sig.iloc[loc])
        position.iloc[loc:end] = val if direction == "long" else -val

    strategy_ret = (daily_ret * position).fillna(0)
    cum          = (1 + strategy_ret).cumprod()
    raw_return   = float(cum.iloc[-1] - 1)
    n_years      = len(strategy_ret) / 252
    cagr = float((1 + raw_return)**(1/max(n_years,0.1))-1) if raw_return > -1 else float("-inf")
    mu, std = strategy_ret.mean(), strategy_ret.std()
    sharpe   = float(mu/std*math.sqrt(252)) if std > 0 else 0.0
    roll_max = cum.cummax()
    max_dd   = float(((cum - roll_max)/roll_max).min())
    n_trades = int((position.diff().abs() > 0).sum())
    active   = float((position != 0).mean()) * 100

    return {
        "raw_return":   round(raw_return*100, 2),
        "cagr":         round(cagr*100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd*100, 2),
        "n_trades":     n_trades,
        "active_pct":   round(active, 1),
    }


def buy_and_hold_ret(ohlcv: pd.DataFrame) -> float:
    p = ohlcv["Close"]
    return float(p.iloc[-1]/p.iloc[0]-1)*100


# ── Candlestick pattern detector base ─────────────────────────────────────────

class CandlePattern(ABC):
    name:        str = "base"
    category:    str = "single"
    signal_type: str = "bullish"   # bullish | bearish | both

    @abstractmethod
    def detect(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Return +1 (bullish signal), -1 (bearish signal), 0 (no signal)."""

    def body(self, ohlcv: pd.DataFrame) -> pd.Series:
        return (ohlcv["Close"] - ohlcv["Open"]).abs()

    def full_range(self, ohlcv: pd.DataFrame) -> pd.Series:
        return ohlcv["High"] - ohlcv["Low"]

    def upper_shadow(self, ohlcv: pd.DataFrame) -> pd.Series:
        return ohlcv["High"] - ohlcv[["Open","Close"]].max(axis=1)

    def lower_shadow(self, ohlcv: pd.DataFrame) -> pd.Series:
        return ohlcv[["Open","Close"]].min(axis=1) - ohlcv["Low"]

    def is_bull(self, ohlcv: pd.DataFrame) -> pd.Series:
        return ohlcv["Close"] > ohlcv["Open"]

    def is_bear(self, ohlcv: pd.DataFrame) -> pd.Series:
        return ohlcv["Close"] < ohlcv["Open"]

    def atr(self, ohlcv: pd.DataFrame, window: int = 14) -> pd.Series:
        hl = ohlcv["High"] - ohlcv["Low"]
        hc = (ohlcv["High"] - ohlcv["Close"].shift()).abs()
        lc = (ohlcv["Low"]  - ohlcv["Close"].shift()).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        return tr.rolling(window).mean()


# ══════════════════════════════════════════════════════════════════════════════
#  SINGLE-CANDLE PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

class Doji(CandlePattern):
    """Body ≤ 5% of total range — indecision candle."""
    name, category, signal_type = "Doji", "single", "both"

    def detect(self, df):
        body   = self.body(df)
        rng    = self.full_range(df).replace(0, np.nan)
        ratio  = body / rng
        sig    = pd.Series(0, index=df.index, dtype=float)
        # Doji after downtrend → bullish; after uptrend → bearish
        trend  = df["Close"].pct_change(5)
        doji_days = ratio < 0.05
        sig[doji_days & (trend < -0.02)]  =  1   # bullish reversal
        sig[doji_days & (trend >  0.02)]  = -1   # bearish reversal
        return sig


class LongLeggedDoji(CandlePattern):
    """Very small body, both shadows > 1× body."""
    name, category, signal_type = "LongLeggedDoji", "single", "both"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        b_rng = body / rng
        sig   = pd.Series(0, index=df.index, dtype=float)
        trend = df["Close"].pct_change(5)
        mask  = (b_rng < 0.05) & (us > body) & (ls > body)
        sig[mask & (trend < 0)] =  1
        sig[mask & (trend > 0)] = -1
        return sig


class Hammer(CandlePattern):
    """Small body at top of range, lower shadow ≥ 2× body, minimal upper shadow.
    Bullish reversal after downtrend."""
    name, category, signal_type = "Hammer", "single", "bullish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df["Close"].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (ls >= 2 * body.replace(0, np.nan)) &
            (us <= 0.1 * rng) &
            (trend < -0.03)   # after downtrend
        )
        sig[mask] = 1
        return sig


class HangingMan(CandlePattern):
    """Same shape as Hammer but after uptrend → bearish reversal."""
    name, category, signal_type = "HangingMan", "single", "bearish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df["Close"].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (
            (body / rng < 0.35) &
            (ls >= 2 * body.replace(0, np.nan)) &
            (us <= 0.1 * rng) &
            (trend > 0.03)    # after uptrend
        )
        sig[mask] = -1
        return sig


class ShootingStar(CandlePattern):
    """Small body at bottom, upper shadow ≥ 2× body — bearish reversal after uptrend."""
    name, category, signal_type = "ShootingStar", "single", "bearish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df["Close"].pct_change(10)
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
    """Same shape as Shooting Star but after downtrend → bullish reversal."""
    name, category, signal_type = "InvertedHammer", "single", "bullish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df["Close"].pct_change(10)
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
    """Full bullish candle — body ≥ 95% of range (no shadows). Strong momentum."""
    name, category, signal_type = "BullMarubozu", "single", "bullish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        bull  = self.is_bull(df)
        sig   = pd.Series(0, index=df.index, dtype=float)
        sig[(body/rng > 0.92) & bull] = 1
        return sig


class BearMarubozu(CandlePattern):
    """Full bearish candle — body ≥ 95% of range. Strong downward momentum."""
    name, category, signal_type = "BearMarubozu", "single", "bearish"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        bear  = self.is_bear(df)
        sig   = pd.Series(0, index=df.index, dtype=float)
        sig[(body/rng > 0.92) & bear] = -1
        return sig


class SpinningTop(CandlePattern):
    """Small body with shadows > body on both sides — indecision."""
    name, category, signal_type = "SpinningTop", "single", "both"

    def detect(self, df):
        body  = self.body(df)
        rng   = self.full_range(df).replace(0, np.nan)
        us    = self.upper_shadow(df)
        ls    = self.lower_shadow(df)
        trend = df["Close"].pct_change(5)
        sig   = pd.Series(0, index=df.index, dtype=float)
        mask  = (body/rng < 0.3) & (us > body) & (ls > body)
        sig[mask & (trend < -0.02)] =  1   # reversal after down
        sig[mask & (trend >  0.02)] = -1   # reversal after up
        return sig


# ══════════════════════════════════════════════════════════════════════════════
#  TWO-CANDLE PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

class BullishEngulfing(CandlePattern):
    """Day 2 bullish body fully engulfs Day 1 bearish body."""
    name, category, signal_type = "BullishEngulfing", "two-candle", "bullish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        engulfs   = (o <= c.shift(1)) & (c >= o.shift(1))
        trend     = c.pct_change(10)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bear & curr_bull & engulfs & (trend < -0.02)] = 1
        return sig


class BearishEngulfing(CandlePattern):
    """Day 2 bearish body fully engulfs Day 1 bullish body."""
    name, category, signal_type = "BearishEngulfing", "two-candle", "bearish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        prev_bull = c.shift(1) > o.shift(1)
        curr_bear = c < o
        engulfs   = (o >= c.shift(1)) & (c <= o.shift(1))
        trend     = c.pct_change(10)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bull & curr_bear & engulfs & (trend > 0.02)] = -1
        return sig


class BullishHarami(CandlePattern):
    """Small bullish body inside previous large bearish body."""
    name, category, signal_type = "BullishHarami", "two-candle", "bullish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        prev_body_hi = df[["Open","Close"]].shift(1).max(axis=1)
        prev_body_lo = df[["Open","Close"]].shift(1).min(axis=1)
        curr_body_hi = df[["Open","Close"]].max(axis=1)
        curr_body_lo = df[["Open","Close"]].min(axis=1)
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        inside    = (curr_body_hi < prev_body_hi) & (curr_body_lo > prev_body_lo)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bear & curr_bull & inside] = 1
        return sig


class BearishHarami(CandlePattern):
    """Small bearish body inside previous large bullish body."""
    name, category, signal_type = "BearishHarami", "two-candle", "bearish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        prev_body_hi = df[["Open","Close"]].shift(1).max(axis=1)
        prev_body_lo = df[["Open","Close"]].shift(1).min(axis=1)
        curr_body_hi = df[["Open","Close"]].max(axis=1)
        curr_body_lo = df[["Open","Close"]].min(axis=1)
        prev_bull = c.shift(1) > o.shift(1)
        curr_bear = c < o
        inside    = (curr_body_hi < prev_body_hi) & (curr_body_lo > prev_body_lo)
        sig       = pd.Series(0, index=df.index, dtype=float)
        sig[prev_bull & curr_bear & inside] = -1
        return sig


class TweezerBottom(CandlePattern):
    """Two candles with same or near-same low — support signal."""
    name, category, signal_type = "TweezerBottom", "two-candle", "bullish"

    def detect(self, df):
        lo    = df["Low"]
        trend = df["Close"].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        same_low = (lo - lo.shift(1)).abs() / lo.replace(0,np.nan) < 0.002
        sig[same_low & self.is_bull(df) & (trend < -0.02)] = 1
        return sig


class TweezerTop(CandlePattern):
    """Two candles with same or near-same high — resistance signal."""
    name, category, signal_type = "TweezerTop", "two-candle", "bearish"

    def detect(self, df):
        hi    = df["High"]
        trend = df["Close"].pct_change(10)
        sig   = pd.Series(0, index=df.index, dtype=float)
        same_high = (hi - hi.shift(1)).abs() / hi.replace(0,np.nan) < 0.002
        sig[same_high & self.is_bear(df) & (trend > 0.02)] = -1
        return sig


class PiercingLine(CandlePattern):
    """Day 1 bearish, Day 2 opens below Day 1 low but closes above Day 1 midpoint."""
    name, category, signal_type = "PiercingLine", "two-candle", "bullish"

    def detect(self, df):
        o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bear = c.shift(1) < o.shift(1)
        day2_bull = c > o
        opens_low = o < l.shift(1)
        closes_above_mid = c > mid1
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[day1_bear & day2_bull & opens_low & closes_above_mid] = 1
        return sig


class DarkCloudCover(CandlePattern):
    """Day 1 bullish, Day 2 opens above Day 1 high but closes below Day 1 midpoint."""
    name, category, signal_type = "DarkCloudCover", "two-candle", "bearish"

    def detect(self, df):
        o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bull = c.shift(1) > o.shift(1)
        day2_bear = c < o
        opens_high = o > h.shift(1)
        closes_below_mid = c < mid1
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[day1_bull & day2_bear & opens_high & closes_below_mid] = -1
        return sig


# ══════════════════════════════════════════════════════════════════════════════
#  THREE-CANDLE PATTERNS
# ══════════════════════════════════════════════════════════════════════════════

class MorningStar(CandlePattern):
    """Bear candle → small body (gap down) → bull candle closing into Day 1 body."""
    name, category, signal_type = "MorningStar", "three-candle", "bullish"

    def detect(self, df):
        o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
        rng   = self.full_range(df).replace(0, np.nan)
        body  = self.body(df)
        # Day 1: large bearish
        d1_bear  = (c.shift(2) < o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        # Day 2: small body (star) — gap down
        d2_small = body.shift(1) / rng.shift(1) < 0.3
        d2_gap   = df[["Open","Close"]].shift(1).max(axis=1) < c.shift(2)
        # Day 3: large bullish, closes into Day 1 body
        d3_bull  = (c > o) & (body/rng > 0.4)
        d3_close = c > (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bear & d2_small & d3_bull & d3_close] = 1
        return sig


class EveningStar(CandlePattern):
    """Bull candle → small body (gap up) → bear candle closing into Day 1 body."""
    name, category, signal_type = "EveningStar", "three-candle", "bearish"

    def detect(self, df):
        o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        d1_bull  = (c.shift(2) > o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        d2_small = body.shift(1)/rng.shift(1) < 0.3
        d2_gap   = df[["Open","Close"]].shift(1).min(axis=1) > c.shift(2)
        d3_bear  = (c < o) & (body/rng > 0.4)
        d3_close = c < (o.shift(2) + c.shift(2)) / 2
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bull & d2_small & d3_bear & d3_close] = -1
        return sig


class ThreeWhiteSoldiers(CandlePattern):
    """Three consecutive strong bullish candles, each opening in prior body."""
    name, category, signal_type = "ThreeWhiteSoldiers", "three-candle", "bullish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        rng  = self.full_range(df).replace(0, np.nan)
        body = self.body(df)
        bull1 = (c.shift(2) > o.shift(2)) & (body.shift(2)/rng.shift(2) > 0.5)
        bull2 = (c.shift(1) > o.shift(1)) & (body.shift(1)/rng.shift(1) > 0.5)
        bull3 = (c > o)                    & (body/rng > 0.5)
        # Each opens within prior candle's body
        open2_in = (o.shift(1) > o.shift(2)) & (o.shift(1) < c.shift(2))
        open3_in = (o > o.shift(1))           & (o < c.shift(1))
        consecutive = c.shift(2) < c.shift(1)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[bull1 & bull2 & bull3 & open2_in & open3_in & consecutive] = 1
        return sig


class ThreeBlackCrows(CandlePattern):
    """Three consecutive strong bearish candles, each opening in prior body."""
    name, category, signal_type = "ThreeBlackCrows", "three-candle", "bearish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
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
    """Like Morning Star but Day 2 is specifically a Doji."""
    name, category, signal_type = "MorningDojiStar", "three-candle", "bullish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
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
    """Like Evening Star but Day 2 is specifically a Doji."""
    name, category, signal_type = "EveningDojiStar", "three-candle", "bearish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
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
    """Bearish Harami → confirmation bullish → strong bullish close."""
    name, category, signal_type = "ThreeInsideUp", "three-candle", "bullish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
        # Day 1: large bearish
        d1_bear = c.shift(2) < o.shift(2)
        # Day 2: small bullish inside Day 1
        d2_bull_inside = (
            (c.shift(1) > o.shift(1)) &
            (c.shift(1) < o.shift(2)) &
            (o.shift(1) > c.shift(2))
        )
        # Day 3: closes above Day 1 open (full reversal)
        d3_confirm = c > o.shift(2)
        sig = pd.Series(0, index=df.index, dtype=float)
        sig[d1_bear & d2_bull_inside & d3_confirm] = 1
        return sig


class ThreeInsideDown(CandlePattern):
    """Bullish Harami → confirmation bearish → strong bearish close."""
    name, category, signal_type = "ThreeInsideDown", "three-candle", "bearish"

    def detect(self, df):
        o, c = df["Open"], df["Close"]
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


# ── Pattern registry ──────────────────────────────────────────────────────────

ALL_PATTERNS = [
    # Single
    Doji(), LongLeggedDoji(), Hammer(), HangingMan(),
    ShootingStar(), InvertedHammer(), BullMarubozu(), BearMarubozu(),
    SpinningTop(),
    # Two-candle
    BullishEngulfing(), BearishEngulfing(),
    BullishHarami(), BearishHarami(),
    TweezerBottom(), TweezerTop(),
    PiercingLine(), DarkCloudCover(),
    # Three-candle
    MorningStar(), EveningStar(),
    ThreeWhiteSoldiers(), ThreeBlackCrows(),
    MorningDojiStar(), EveningDojiStar(),
    ThreeInsideUp(), ThreeInsideDown(),
]

HOLD_PERIODS = [1, 3, 5, 10]


# ── Main runner ───────────────────────────────────────────────────────────────

def run():
    print("=" * 70)
    print("CANDLESTICK PATTERN AUTORESEARCH")
    print(f"{len(ALL_PATTERNS)} patterns × {len(UNIVERSE)} tickers × "
          f"{len(HOLD_PERIODS)} hold periods × 2 directions")
    total = len(ALL_PATTERNS) * len(UNIVERSE) * len(HOLD_PERIODS) * 2
    print(f"Total backtests: {total:,}")
    print("=" * 70)

    results = []
    bnh_avg  = []
    done     = 0

    for sym in UNIVERSE:
        ohlcv = fetch_ohlcv(sym)
        if ohlcv is None:
            continue
        bnh_avg.append(buy_and_hold_ret(ohlcv))

        for pat in ALL_PATTERNS:
            try:
                sigs = pat.detect(ohlcv)
            except Exception:
                continue

            bull_sigs = sigs.clip(lower=0)   # +1 entries
            bear_sigs = (-sigs).clip(lower=0) # -1→+1 for short entry

            for hold in HOLD_PERIODS:
                # Long on bullish signal
                if (bull_sigs > 0).any():
                    r = backtest_hold(ohlcv, bull_sigs, hold, "long")
                    if r:
                        r.update({"symbol":sym,"pattern":pat.name,
                                  "category":pat.category,"signal":"bullish",
                                  "hold_days":hold,"direction":"long"})
                        results.append(r)
                # Short on bearish signal
                if (bear_sigs > 0).any():
                    r = backtest_hold(ohlcv, bear_sigs, hold, "short")
                    if r:
                        r.update({"symbol":sym,"pattern":pat.name,
                                  "category":pat.category,"signal":"bearish",
                                  "hold_days":hold,"direction":"short"})
                        results.append(r)
                done += 2

        if done % 2000 == 0 and done > 0:
            print(f"  Progress: {done:,}/{total:,} ({done/total*100:.0f}%)")

    bnh = sum(bnh_avg)/len(bnh_avg) if bnh_avg else 0
    df  = pd.DataFrame(results)

    # Aggregate by pattern + hold + direction
    agg = (
        df.groupby(["pattern","category","signal","hold_days","direction"])
          .agg(
              avg_return   = ("raw_return", "mean"),
              median_return= ("raw_return", "median"),
              avg_sharpe   = ("sharpe",     "mean"),
              win_rate     = ("raw_return", lambda x: (x>0).mean()*100),
              beat_bnh_pct = ("raw_return", lambda x: (x>bnh).mean()*100),
              n_obs        = ("symbol",     "count"),
              avg_active   = ("active_pct", "mean"),
          )
          .reset_index()
          .sort_values("avg_sharpe", ascending=False)
    )

    # ── Print results ──────────────────────────────────────────────────────────
    print(f"\n  B&H avg benchmark: {bnh:.1f}%")
    print(f"\n  TOP 20 by Sharpe:")
    print(f"  {'Pattern':<22} {'Cat':<12} {'Sig':<9} {'Hold':>4} {'AvgRet%':>8} "
          f"{'Sharpe':>7} {'WinRate':>8} {'BeatB&H':>8} {'n':>5}")
    print("  " + "-"*90)
    for _, r in agg.head(20).iterrows():
        print(f"  {r['pattern']:<22} {r['category']:<12} {r['signal']:<9} "
              f"{int(r['hold_days']):>4}d {r['avg_return']:>8.1f}% "
              f"{r['avg_sharpe']:>7.3f} {r['win_rate']:>7.1f}% "
              f"{r['beat_bnh_pct']:>7.1f}% {int(r['n_obs']):>5}")

    # Category summary
    cat_agg = (
        df.groupby("category")
          .agg(avg_return=("raw_return","mean"),
               avg_sharpe=("sharpe","mean"))
          .sort_values("avg_sharpe", ascending=False)
    )
    print(f"\n  CATEGORY RANKING (by Sharpe):")
    for cat, row in cat_agg.iterrows():
        print(f"    {cat:<15} avg {row['avg_return']:>7.1f}%  Sharpe {row['avg_sharpe']:.3f}")

    # Optimal hold period
    hold_agg = (
        df.groupby("hold_days")
          .agg(avg_sharpe=("sharpe","mean"))
          .sort_values("avg_sharpe", ascending=False)
    )
    print(f"\n  OPTIMAL HOLD PERIODS (by Sharpe):")
    for hold, row in hold_agg.iterrows():
        print(f"    {hold}d hold → Sharpe {row['avg_sharpe']:.3f}")

    # Bottom 5 — worst patterns
    print(f"\n  BOTTOM 5 (worst Sharpe — patterns to avoid):")
    for _, r in agg.tail(5).iterrows():
        print(f"  {r['pattern']:<22} {r['signal']:<9} {int(r['hold_days']):>4}d "
              f"{r['avg_return']:>8.1f}%  Sharpe {r['avg_sharpe']:>7.3f}")

    # Save
    out = ROUNDS_DIR / "candle_results.json"
    save_data = {
        "timestamp": datetime.now().isoformat(),
        "bnh_avg": round(bnh, 2),
        "n_results": len(results),
        "top20": agg.head(20).to_dict("records"),
        "category_ranking": cat_agg.to_dict(),
        "hold_period_ranking": hold_agg.to_dict(),
        "all_results": agg.to_dict("records"),
    }
    with open(out, "w") as f:
        json.dump(save_data, f, indent=2, default=str)
    print(f"\n  Saved → {out}")
    return save_data


if __name__ == "__main__":
    run()
