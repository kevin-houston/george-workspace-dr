#!/usr/bin/env python3
"""
Forex Autoresearch Harness — Karpathy Loop Edition
====================================================
Applies systematic generate→test→analyze→improve cycles to forex trading.

Universe: 10 major/minor pairs via yfinance (EURUSD=X format)
Strategy families tested across 8 rounds:
  R1: Baseline — SMA crossover, momentum, simple mean reversion
  R2: Oscillator-based — RSI, Bollinger Bands, CCI
  R3: Volatility regime — ATR breakout, vol-scaled momentum
  R4: Carry trade — interest rate differential proxies
  R5: Session momentum — NY open, London breakout patterns
  R6: Macro-enhanced — FRED rate/inflation differentials
  R7: Combo ensemble — top strategies from R1-R6 combined
  R8: Adaptive — regime-switching between trend and reversion

Each round: Generate hypotheses → Backtest all pairs → Rank by Sharpe → Analyze
Results saved to: rounds/forex_round_N.json

Usage:
  PYTHONPATH=/tmp/eval_deps python3 forex_harness.py
  PYTHONPATH=/tmp/eval_deps python3 forex_harness.py --round 1
  PYTHONPATH=/tmp/eval_deps python3 forex_harness.py --all
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing: {e}")
    print("Run: curl -s https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages")
    print("Then: python3 -m pip install yfinance pandas numpy --target=/tmp/eval_deps")
    sys.exit(1)

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
MACRO_DIR  = ROOT / "macro_cache"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)
MACRO_DIR.mkdir(exist_ok=True)

YEARS      = 10
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")
FRED_KEY   = os.environ.get("FRED_API_KEY", "")

# ── Forex universe ─────────────────────────────────────────────────────────────
# Format: yfinance symbol → human label + base/quote currencies
PAIRS = {
    "EURUSD=X":  {"label": "EUR/USD", "base": "EUR", "quote": "USD"},
    "GBPUSD=X":  {"label": "GBP/USD", "base": "GBP", "quote": "USD"},
    "USDJPY=X":  {"label": "USD/JPY", "base": "USD", "quote": "JPY"},
    "AUDUSD=X":  {"label": "AUD/USD", "base": "AUD", "quote": "USD"},
    "USDCAD=X":  {"label": "USD/CAD", "base": "USD", "quote": "CAD"},
    "USDCHF=X":  {"label": "USD/CHF", "base": "USD", "quote": "CHF"},
    "NZDUSD=X":  {"label": "NZD/USD", "base": "NZD", "quote": "USD"},
    "EURGBP=X":  {"label": "EUR/GBP", "base": "EUR", "quote": "GBP"},
    "EURJPY=X":  {"label": "EUR/JPY", "base": "EUR", "quote": "JPY"},
    "GBPJPY=X":  {"label": "GBP/JPY", "base": "GBP", "quote": "JPY"},
}

# Approximate central bank rates (% annualized) for carry trade calculations
# Updated to reflect approximate 2026 rates
RATES = {
    "USD": 3.5,   # Fed Funds (easing cycle)
    "EUR": 2.5,   # ECB
    "GBP": 4.0,   # Bank of England
    "JPY": 0.5,   # Bank of Japan (very slowly normalizing)
    "AUD": 4.0,   # RBA
    "CAD": 3.0,   # Bank of Canada
    "CHF": 0.5,   # SNB
    "NZD": 3.5,   # RBNZ
}


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_pair(symbol: str) -> Optional[pd.DataFrame]:
    cp = CACHE_DIR / f"fx_{symbol.replace('=','_')}_{YEARS}yr.pkl"
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
        h = h[["Open","High","Low","Close"]].dropna()
        # Normalize index: strip timezone
        if h.index.tz is not None:
            h.index = h.index.tz_localize(None)
        with open(cp, "wb") as f:
            pickle.dump(h, f)
        return h
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


def fetch_fred(series_id: str) -> Optional[pd.Series]:
    cp = MACRO_DIR / f"fred_{series_id}.pkl"
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series) and len(s) > 50:
                return s
        except Exception:
            pass
    if not FRED_KEY:
        return None
    try:
        params = urllib.parse.urlencode({
            "series_id": series_id, "api_key": FRED_KEY,
            "file_type": "json", "observation_start": "2010-01-01",
        })
        url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        obs  = data.get("observations", [])
        if not obs:
            return None
        idx  = pd.to_datetime([o["date"] for o in obs])
        vals = pd.to_numeric([o["value"] for o in obs], errors="coerce")
        s    = pd.Series(vals.values, index=idx, name=series_id).dropna()
        with open(cp, "wb") as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f"  FRED {series_id}: {e}", file=sys.stderr)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def backtest(closes: pd.Series, signals: pd.Series, cost_bps: float = 1.0) -> dict:
    """
    closes:  daily close prices (already a return series if pct_change applied externally)
    signals: +1 (long), -1 (short), 0 (flat) — applied NEXT day (avoid look-ahead)
    cost_bps: round-trip transaction cost in basis points per trade
    """
    sig = signals.reindex(closes.index).ffill().fillna(0).shift(1).fillna(0)
    ret = closes.pct_change().fillna(0)

    # Transaction cost: apply when position changes
    trades    = sig.diff().abs().fillna(0)
    cost      = trades * (cost_bps / 10000)
    strat_ret = ret * sig - cost

    cum       = (1 + strat_ret).cumprod()
    raw       = float(cum.iloc[-1] - 1)
    n_years   = len(strat_ret) / 252
    cagr      = float((1+raw)**(1/max(n_years,0.1))-1) if raw > -1 else float("-inf")
    mu, std   = strat_ret.mean(), strat_ret.std()
    sharpe    = float(mu/std*math.sqrt(252)) if std > 0 else 0.0
    roll_max  = cum.cummax()
    max_dd    = float(((cum - roll_max)/roll_max).min())
    win_rate  = float((strat_ret > 0).mean() * 100)
    n_trades  = int((trades > 0).sum())

    # Buy-and-hold benchmark
    bnh_cum  = (1 + ret).cumprod()
    bnh_ret  = float(bnh_cum.iloc[-1] - 1)

    return {
        "raw_return":   round(raw*100, 2),
        "cagr":         round(cagr*100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd*100, 2),
        "win_rate":     round(win_rate, 1),
        "n_trades":     n_trades,
        "bnh_return":   round(bnh_ret*100, 2),
    }


def run_strategy(name: str, pair_symbol: str, closes: pd.Series,
                 signal_fn, cost_bps: float = 1.0, **kwargs) -> Optional[dict]:
    try:
        signals = signal_fn(closes, **kwargs)
        r = backtest(closes, signals, cost_bps)
        r["strategy"] = name
        r["pair"]     = pair_symbol
        r["label"]    = PAIRS[pair_symbol]["label"]
        return r
    except Exception as e:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY LIBRARY
# ══════════════════════════════════════════════════════════════════════════════

# ── R1: Baseline ──────────────────────────────────────────────────────────────

def sma_cross(closes: pd.Series, fast: int, slow: int) -> pd.Series:
    """Classic dual SMA crossover — long when fast > slow."""
    f = closes.rolling(fast).mean()
    s = closes.rolling(slow).mean()
    sig = pd.Series(0.0, index=closes.index)
    sig[f > s] =  1
    sig[f < s] = -1
    return sig


def momentum(closes: pd.Series, lookback: int) -> pd.Series:
    """Raw price momentum — long if positive return over lookback."""
    ret = closes.pct_change(lookback)
    sig = pd.Series(0.0, index=closes.index)
    sig[ret > 0] =  1
    sig[ret < 0] = -1
    return sig


def mean_reversion(closes: pd.Series, window: int, threshold: float) -> pd.Series:
    """Z-score mean reversion — fade extremes."""
    roll_mean = closes.rolling(window).mean()
    roll_std  = closes.rolling(window).std().replace(0, np.nan)
    z         = (closes - roll_mean) / roll_std
    sig       = pd.Series(0.0, index=closes.index)
    sig[z < -threshold] =  1   # oversold → long
    sig[z >  threshold] = -1   # overbought → short
    return sig


def triple_sma(closes: pd.Series, fast: int, mid: int, slow: int) -> pd.Series:
    """Three-line SMA — all aligned for trend confirmation."""
    f = closes.rolling(fast).mean()
    m = closes.rolling(mid).mean()
    s = closes.rolling(slow).mean()
    sig = pd.Series(0.0, index=closes.index)
    sig[(f > m) & (m > s)] =  1   # full bull alignment
    sig[(f < m) & (m < s)] = -1   # full bear alignment
    return sig


# ── R2: Oscillators ───────────────────────────────────────────────────────────

def rsi_signal(closes: pd.Series, period: int = 14,
               oversold: float = 30, overbought: float = 70) -> pd.Series:
    """RSI-based mean reversion."""
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    sig   = pd.Series(0.0, index=closes.index)
    sig[rsi < oversold]   =  1
    sig[rsi > overbought] = -1
    return sig


def rsi_trend(closes: pd.Series, period: int = 14,
              bull_line: float = 50, bear_line: float = 50) -> pd.Series:
    """RSI trend — long when RSI > 50 (momentum mode), not reversion."""
    delta = closes.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = 100 - 100 / (1 + rs)
    sig   = pd.Series(0.0, index=closes.index)
    sig[rsi > bull_line] =  1
    sig[rsi < bear_line] = -1
    return sig


def bollinger_breakout(closes: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.Series:
    """Breakout above upper band → long; below lower band → short."""
    mid   = closes.rolling(window).mean()
    std   = closes.rolling(window).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    sig   = pd.Series(0.0, index=closes.index)
    sig[closes > upper] =  1
    sig[closes < lower] = -1
    return sig


def bollinger_reversion(closes: pd.Series, window: int = 20, n_std: float = 2.0) -> pd.Series:
    """Mean reversion from Bollinger extremes — fade the move."""
    mid   = closes.rolling(window).mean()
    std   = closes.rolling(window).std()
    upper = mid + n_std * std
    lower = mid - n_std * std
    sig   = pd.Series(0.0, index=closes.index)
    sig[closes < lower] =  1   # below lower → buy (expect reversion)
    sig[closes > upper] = -1   # above upper → sell
    return sig


def cci_signal(closes: pd.Series, window: int = 20, threshold: float = 100) -> pd.Series:
    """CCI — Commodity Channel Index trend/reversion hybrid."""
    typ = closes  # using close only (simplified CCI)
    ma  = typ.rolling(window).mean()
    md  = typ.rolling(window).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (typ - ma) / (0.015 * md.replace(0, np.nan))
    sig = pd.Series(0.0, index=closes.index)
    sig[cci >  threshold] =  1   # trending up
    sig[cci < -threshold] = -1
    return sig


# ── R3: Volatility-regime strategies ─────────────────────────────────────────

def atr_breakout(df: pd.DataFrame, atr_window: int = 14,
                 mult: float = 1.5, lookback: int = 20) -> pd.Series:
    """ATR-based channel breakout — only trade significant moves."""
    hl    = df["High"] - df["Low"]
    hc    = (df["High"] - df["Close"].shift()).abs()
    lc    = (df["Low"]  - df["Close"].shift()).abs()
    atr   = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(atr_window).mean()
    high_ = df["Close"].rolling(lookback).max()
    low_  = df["Close"].rolling(lookback).min()
    sig   = pd.Series(0.0, index=df.index)
    sig[df["Close"] > high_.shift(1)]               =  1
    sig[df["Close"] < low_.shift(1)]                = -1
    return sig


def vol_scaled_momentum(closes: pd.Series, mom_window: int = 20,
                        vol_window: int = 20, target_vol: float = 0.10) -> pd.Series:
    """Momentum signal scaled by inverse volatility — size down in high-vol regimes."""
    ret    = closes.pct_change()
    mom    = closes.pct_change(mom_window)
    vol    = ret.rolling(vol_window).std() * math.sqrt(252)
    scale  = (target_vol / vol.replace(0, np.nan)).clip(0, 3)
    raw_sig = np.sign(mom).fillna(0)
    return raw_sig * scale


def vol_regime_switch(closes: pd.Series, fast: int = 10, slow: int = 50,
                      vol_window: int = 20) -> pd.Series:
    """
    Use trend-following in low-vol regimes, mean reversion in high-vol regimes.
    Regime boundary: compare current vol to its 60-day median.
    """
    ret   = closes.pct_change()
    vol   = ret.rolling(vol_window).std()
    med   = vol.rolling(60).median()
    trend = np.sign(closes.rolling(fast).mean() - closes.rolling(slow).mean())
    rev   = -np.sign(closes - closes.rolling(slow).mean())
    sig   = pd.Series(0.0, index=closes.index)
    sig[vol < med]  = trend[vol < med]
    sig[vol >= med] = rev[vol >= med]
    return sig.fillna(0)


# ── R4: Carry trade ───────────────────────────────────────────────────────────

def carry_trade(closes: pd.Series, pair_symbol: str,
                carry_threshold: float = 0.5) -> pd.Series:
    """
    Static carry — hold long if base currency has higher rate than quote.
    In reality carry is held for months; we implement as always-on with
    trend confirmation filter.
    """
    meta      = PAIRS[pair_symbol]
    base_rate = RATES.get(meta["base"], 2.0)
    quote_rate = RATES.get(meta["quote"], 2.0)
    carry_diff = base_rate - quote_rate  # positive = long base is carry-positive

    # No signal if carry is neutral
    if abs(carry_diff) < carry_threshold:
        return pd.Series(0.0, index=closes.index)

    direction = 1.0 if carry_diff > 0 else -1.0

    # Trend confirmation: only take carry if not in strong counter-trend
    sma50 = closes.rolling(50).mean()
    sig   = pd.Series(direction, index=closes.index)
    # Cut carry position if strongly counter-trend
    if direction > 0:
        sig[closes < sma50 * 0.98] = 0  # trend filter: don't fight strong downtrend
    else:
        sig[closes > sma50 * 1.02] = 0
    return sig.fillna(0)


def carry_momentum_combo(closes: pd.Series, pair_symbol: str,
                         mom_window: int = 20) -> pd.Series:
    """Carry direction confirmed by momentum — only trade when both agree."""
    meta      = PAIRS[pair_symbol]
    base_rate = RATES.get(meta["base"], 2.0)
    quote_rate = RATES.get(meta["quote"], 2.0)
    carry_dir = np.sign(base_rate - quote_rate)
    if carry_dir == 0:
        return pd.Series(0.0, index=closes.index)
    mom = closes.pct_change(mom_window)
    sig = pd.Series(0.0, index=closes.index)
    sig[(np.sign(mom) == carry_dir)] = carry_dir
    return sig.fillna(0)


# ── R5: Time-of-week patterns ─────────────────────────────────────────────────

def day_of_week_effect(closes: pd.Series, pair_symbol: str) -> pd.Series:
    """
    Exploit well-documented day-of-week patterns in forex.
    EUR/USD and GBP/USD tend to trend Mon-Wed, mean-revert Thu-Fri.
    JPY pairs often reverse Friday.
    """
    ret  = closes.pct_change()
    sig  = pd.Series(0.0, index=closes.index)
    dow  = closes.index.dayofweek  # 0=Mon, 4=Fri
    mom5 = closes.pct_change(5)

    label = PAIRS[pair_symbol]["label"]
    if "JPY" in label:
        # Buy Mon/Tue dips in JPY pairs (they tend to recover mid-week)
        sig[(dow <= 1) & (mom5 < 0)] =  1
        sig[(dow == 4) & (mom5 > 0)] = -1  # fade Friday rallies in JPY
    else:
        # Trend Mon-Wed, fade Thu-Fri
        sig[(dow <= 2) & (mom5 > 0)] =  1
        sig[(dow <= 2) & (mom5 < 0)] = -1
        sig[(dow >= 3) & (mom5 > 0.01)] = -1  # fade big runs into weekend
    return sig.fillna(0)


def monday_breakout(closes: pd.Series) -> pd.Series:
    """
    Monday price action sets the weekly tone — buy Monday morning breakout.
    Hold through Wednesday, close before weekend.
    """
    sig = pd.Series(0.0, index=closes.index)
    dow = closes.index.dayofweek
    fri_close = closes.shift(3)   # Friday close (3 days before Monday)
    # Monday: long if opens above Friday close
    sig[(dow == 0) & (closes > fri_close)] =  1
    sig[(dow == 0) & (closes < fri_close)] = -1
    # Hold Tue-Wed
    sig[(dow == 1) | (dow == 2)] = sig[(dow == 1) | (dow == 2)].ffill()
    # Flat Thu-Fri
    sig[dow >= 3] = 0
    return sig.fillna(0)


# ── R6: Macro-enhanced forex ──────────────────────────────────────────────────

def macro_rate_diff_signal(closes: pd.Series, pair_symbol: str,
                           us_rate: pd.Series, foreign_rate: pd.Series) -> pd.Series:
    """
    Trade direction based on yield spread changes.
    Widening US premium → USD strength (long USD pairs, short EUR/GBP vs USD).
    """
    meta  = PAIRS[pair_symbol]
    # Align both to close index
    idx   = closes.index
    if us_rate is None or foreign_rate is None:
        return pd.Series(0.0, index=idx)

    us_r  = us_rate.reindex(idx, method="ffill")
    fo_r  = foreign_rate.reindex(idx, method="ffill")
    spread = us_r - fo_r
    spread_mom = spread - spread.shift(21)  # 1-month change in spread

    is_usd_base  = meta["base"] == "USD"
    is_usd_quote = meta["quote"] == "USD"

    sig = pd.Series(0.0, index=idx)
    if is_usd_base:
        # USD/JPY, USD/CAD, USD/CHF — long when US rate premium rising
        sig[spread_mom > 0.1]  =  1
        sig[spread_mom < -0.1] = -1
    elif is_usd_quote:
        # EUR/USD, GBP/USD — opposite: rising US rates = short EUR/USD
        sig[spread_mom > 0.1]  = -1
        sig[spread_mom < -0.1] =  1
    else:
        # Cross pair — use ratio of rates
        base_rate  = RATES.get(meta["base"], 2.0)
        quote_rate = RATES.get(meta["quote"], 2.0)
        sig[:] = np.sign(base_rate - quote_rate)
    return sig.fillna(0)


def oil_fx_correlation(closes: pd.Series, pair_symbol: str,
                       oil: pd.Series) -> pd.Series:
    """
    Oil-correlated pairs: CAD and NOK strengthen with oil, JPY weakens.
    USD/CAD: inverse oil correlation (oil up → USD/CAD down = CAD strength)
    """
    meta  = PAIRS[pair_symbol]
    label = meta["label"]
    idx   = closes.index
    if oil is None:
        return pd.Series(0.0, index=idx)

    oil_aligned = oil.reindex(idx, method="ffill")
    oil_mom  = oil_aligned.pct_change(10)

    sig = pd.Series(0.0, index=idx)
    if "CAD" in label:
        # USD/CAD — oil up → CAD strengthens → short USD/CAD
        if meta["base"] == "USD":
            sig[oil_mom > 0.02]  = -1  # oil rising = short USD/CAD
            sig[oil_mom < -0.02] =  1
        else:
            sig[oil_mom > 0.02]  =  1
            sig[oil_mom < -0.02] = -1
    elif "JPY" in label and meta["quote"] == "JPY":
        # USD/JPY, EUR/JPY — oil shock + risk-off → JPY safe haven = short crosses vs JPY
        sig[oil_mom > 0.05] = -1  # major oil spike = risk-off = JPY strength
        sig[oil_mom < -0.02] =  1
    return sig.fillna(0)


# ── R7: Ensemble ──────────────────────────────────────────────────────────────

def ensemble_top3(closes: pd.Series, pair_symbol: str) -> pd.Series:
    """
    Combine top 3 strategies from R1-R6 by vote.
    Each casts ±1 vote; take position when ≥2 agree.
    """
    s1 = triple_sma(closes, 5, 20, 60)
    s2 = vol_scaled_momentum(closes, 20, 20)
    s3 = carry_trade(closes, pair_symbol)
    vote = s1 + s2 + s3
    sig  = pd.Series(0.0, index=closes.index)
    sig[vote >= 2]  =  1
    sig[vote <= -2] = -1
    return sig


def trend_carry_combo(closes: pd.Series, pair_symbol: str) -> pd.Series:
    """SMA trend + carry direction must agree."""
    trend = np.sign(closes.rolling(20).mean() - closes.rolling(60).mean())
    carry = carry_trade(closes, pair_symbol)
    sig   = pd.Series(0.0, index=closes.index)
    same  = (np.sign(trend) == np.sign(carry)) & (carry != 0)
    sig[same] = carry[same]
    return sig.fillna(0)


# ── R8: Adaptive / regime-switching ─────────────────────────────────────────

def adaptive_regime(closes: pd.Series, vol_window: int = 20,
                    trend_fast: int = 10, trend_slow: int = 40,
                    rev_window: int = 20, rev_thresh: float = 1.5) -> pd.Series:
    """
    Full adaptive: detect trending vs ranging regime,
    apply SMA trend in trending regime, z-score reversion in ranging.
    Regime detection: ADX-proxy using rolling return autocorrelation.
    """
    ret    = closes.pct_change().fillna(0)
    # Autocorrelation(1) as trend indicator — positive = trending, negative = mean-reverting
    autocorr = ret.rolling(40).apply(
        lambda x: pd.Series(x).autocorr(lag=1) if len(x) > 10 else 0.0, raw=False
    ).fillna(0)

    trend = np.sign(closes.rolling(trend_fast).mean() - closes.rolling(trend_slow).mean())
    roll_mean = closes.rolling(rev_window).mean()
    roll_std  = closes.rolling(rev_window).std().replace(0, np.nan)
    z_rev     = -(closes - roll_mean) / roll_std   # flip: oversold → long

    sig = pd.Series(0.0, index=closes.index)
    sig[autocorr > 0.05]  = trend[autocorr > 0.05]    # trending market → follow trend
    sig[autocorr < -0.05] = np.sign(z_rev[autocorr < -0.05])  # ranging → mean revert
    return sig.fillna(0)


def keltner_breakout(closes: pd.Series, df: pd.DataFrame,
                     ema_period: int = 20, atr_mult: float = 1.5,
                     atr_period: int = 10) -> pd.Series:
    """Keltner Channel breakout — better than Bollinger for forex trending."""
    ema  = closes.ewm(span=ema_period).mean()
    hl   = df["High"] - df["Low"]
    hc   = (df["High"] - df["Close"].shift()).abs()
    lc   = (df["Low"]  - df["Close"].shift()).abs()
    atr  = pd.concat([hl, hc, lc], axis=1).max(axis=1).ewm(span=atr_period).mean()
    upper = ema + atr_mult * atr
    lower = ema - atr_mult * atr
    sig   = pd.Series(0.0, index=closes.index)
    sig[closes > upper] =  1
    sig[closes < lower] = -1
    return sig


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

def build_round_results(round_num: int, pairs_data: dict,
                        macro: dict) -> List[dict]:
    results = []

    for sym, df in pairs_data.items():
        c = df["Close"]

        if round_num == 1:
            # Baseline: SMA crossovers, momentum, mean reversion
            configs = [
                ("SMA_5_20",    lambda c=c: sma_cross(c, 5, 20)),
                ("SMA_10_50",   lambda c=c: sma_cross(c, 10, 50)),
                ("SMA_20_100",  lambda c=c: sma_cross(c, 20, 100)),
                ("SMA_50_200",  lambda c=c: sma_cross(c, 50, 200)),
                ("MOM_5",       lambda c=c: momentum(c, 5)),
                ("MOM_10",      lambda c=c: momentum(c, 10)),
                ("MOM_20",      lambda c=c: momentum(c, 20)),
                ("MOM_60",      lambda c=c: momentum(c, 60)),
                ("MeanRev_20_1.5", lambda c=c: mean_reversion(c, 20, 1.5)),
                ("MeanRev_20_2.0", lambda c=c: mean_reversion(c, 20, 2.0)),
                ("MeanRev_40_1.5", lambda c=c: mean_reversion(c, 40, 1.5)),
                ("TriSMA_5_20_60",  lambda c=c: triple_sma(c, 5, 20, 60)),
                ("TriSMA_10_50_200",lambda c=c: triple_sma(c, 10, 50, 200)),
            ]

        elif round_num == 2:
            # Oscillators: RSI, Bollinger, CCI
            configs = [
                ("RSI_14_Rev",      lambda c=c: rsi_signal(c, 14, 30, 70)),
                ("RSI_14_Rev_Tight",lambda c=c: rsi_signal(c, 14, 20, 80)),
                ("RSI_7_Rev",       lambda c=c: rsi_signal(c, 7, 25, 75)),
                ("RSI_14_Trend",    lambda c=c: rsi_trend(c, 14)),
                ("RSI_21_Trend",    lambda c=c: rsi_trend(c, 21)),
                ("BB_Break_2.0",    lambda c=c: bollinger_breakout(c, 20, 2.0)),
                ("BB_Break_2.5",    lambda c=c: bollinger_breakout(c, 20, 2.5)),
                ("BB_Rev_2.0",      lambda c=c: bollinger_reversion(c, 20, 2.0)),
                ("BB_Rev_1.5",      lambda c=c: bollinger_reversion(c, 20, 1.5)),
                ("CCI_100",         lambda c=c: cci_signal(c, 20, 100)),
                ("CCI_150",         lambda c=c: cci_signal(c, 20, 150)),
            ]

        elif round_num == 3:
            # Volatility strategies
            configs = [
                ("ATR_Break_20",    lambda c=c, df=df: atr_breakout(df, 14, 1.5, 20)),
                ("ATR_Break_10",    lambda c=c, df=df: atr_breakout(df, 14, 1.5, 10)),
                ("VolMom_10",       lambda c=c: vol_scaled_momentum(c, 10, 20)),
                ("VolMom_20",       lambda c=c: vol_scaled_momentum(c, 20, 20)),
                ("VolMom_40",       lambda c=c: vol_scaled_momentum(c, 40, 20)),
                ("VolSwitch_10_50", lambda c=c: vol_regime_switch(c, 10, 50)),
                ("VolSwitch_5_20",  lambda c=c: vol_regime_switch(c, 5, 20)),
                ("Keltner_20_1.5",  lambda c=c, df=df: keltner_breakout(c, df, 20, 1.5)),
                ("Keltner_20_2.0",  lambda c=c, df=df: keltner_breakout(c, df, 20, 2.0)),
                ("Keltner_40_2.0",  lambda c=c, df=df: keltner_breakout(c, df, 40, 2.0)),
            ]

        elif round_num == 4:
            # Carry trade strategies
            configs = [
                ("Carry_0.5",       lambda c=c, s=sym: carry_trade(c, s, 0.5)),
                ("Carry_1.0",       lambda c=c, s=sym: carry_trade(c, s, 1.0)),
                ("CarryMom_20",     lambda c=c, s=sym: carry_momentum_combo(c, s, 20)),
                ("CarryMom_10",     lambda c=c, s=sym: carry_momentum_combo(c, s, 10)),
                ("TrendCarry",      lambda c=c, s=sym: trend_carry_combo(c, s)),
                ("DayOfWeek",       lambda c=c, s=sym: day_of_week_effect(c, s)),
                ("MonBreakout",     lambda c=c: monday_breakout(c)),
            ]

        elif round_num == 5:
            # Macro-enhanced
            us_10y  = macro.get("GS10")
            eu_10y  = macro.get("IRLTLT01EZM156N")  # ECB 10yr
            oil     = macro.get("DCOILWTICO")

            configs = [
                ("OilFX",        lambda c=c, s=sym, o=oil: oil_fx_correlation(c, s, o)),
                ("MacroRate_US_EU", lambda c=c, s=sym, u=us_10y, f=eu_10y:
                                     macro_rate_diff_signal(c, s, u, f)),
            ]
            # Also test best from R1-R3 with higher cost threshold
            configs += [
                ("SMA_20_100_HC", lambda c=c: sma_cross(c, 20, 100)),
                ("VolMom_20_HC",  lambda c=c: vol_scaled_momentum(c, 20, 20)),
            ]

        elif round_num == 6:
            # Deeper macro: FRED rate differentials
            dff   = macro.get("DFF")    # US Fed Funds
            t10y2y = macro.get("T10Y2Y")

            configs = [
                ("FedFunds_Trend",   lambda c=c, s=sym, r=dff:
                                      macro_rate_diff_signal(c, s, r, r)),  # uses static rates
                ("YieldCurve_FX",    lambda c=c, s=sym: _yield_curve_fx(c, s, t10y2y)),
                ("Adaptive",         lambda c=c: adaptive_regime(c)),
                ("Adaptive_Tight",   lambda c=c: adaptive_regime(c, 20, 5, 20, 20, 2.0)),
            ]

        elif round_num == 7:
            # Ensemble combinations from best R1-R6 strategies
            configs = [
                ("Ensemble_Top3",   lambda c=c, s=sym: ensemble_top3(c, s)),
                ("SMA_VolMom",      lambda c=c: _combo_sma_volmom(c)),
                ("Carry_Adaptive",  lambda c=c, s=sym: _combo_carry_adaptive(c, s)),
            ]

        elif round_num == 8:
            # Final best-of: adaptive + vol scaling + carry
            configs = [
                ("VolMom_10_Scaled",  lambda c=c: vol_scaled_momentum(c, 10, 15, 0.12)),
                ("Adaptive_v2",       lambda c=c: adaptive_regime(c, 15, 8, 40, 25, 1.5)),
                ("TriSMA_Keltner",    lambda c=c, df=df: _combo_trisma_keltner(c, df)),
                ("Full_Ensemble",     lambda c=c, df=df, s=sym:
                                       _full_ensemble(c, df, s)),
            ]
        else:
            configs = []

        for strat_name, fn in configs:
            try:
                signals = fn()
                if signals is None or len(signals) == 0:
                    continue
                r = backtest(c, signals)
                r["strategy"] = strat_name
                r["pair"]     = sym
                r["label"]    = PAIRS[sym]["label"]
                r["round"]    = round_num
                results.append(r)
            except Exception as e:
                pass

    return results


# ── Helper combos ─────────────────────────────────────────────────────────────

def _yield_curve_fx(closes: pd.Series, pair_symbol: str,
                    t10y2y: pd.Series) -> pd.Series:
    """Yield curve inversion → USD safe haven → trade accordingly."""
    meta  = PAIRS[pair_symbol]
    idx   = closes.index
    if t10y2y is None:
        return pd.Series(0.0, index=idx)
    yc    = t10y2y.reindex(idx, method="ffill")
    sig   = pd.Series(0.0, index=idx)
    is_usd_base = meta["base"] == "USD"
    if is_usd_base:
        sig[yc < -0.2] =  1   # inverted curve = recession fear = USD safe haven up
        sig[yc >  0.5] = -1   # steep = risk-on = USD soft
    elif meta["quote"] == "USD":
        sig[yc < -0.2] = -1
        sig[yc >  0.5] =  1
    return sig.fillna(0)


def _combo_sma_volmom(closes: pd.Series) -> pd.Series:
    s1 = sma_cross(closes, 10, 50)
    s2 = vol_scaled_momentum(closes, 20, 20)
    vote = s1 + s2
    sig  = pd.Series(0.0, index=closes.index)
    sig[vote > 0.5]  =  1
    sig[vote < -0.5] = -1
    return sig


def _combo_carry_adaptive(closes: pd.Series, pair_symbol: str) -> pd.Series:
    s1 = carry_trade(closes, pair_symbol)
    s2 = adaptive_regime(closes)
    sig = pd.Series(0.0, index=closes.index)
    # Trade only when carry and adaptive agree
    same = (np.sign(s1) == np.sign(s2)) & (s1 != 0)
    sig[same] = s1[same]
    return sig.fillna(0)


def _combo_trisma_keltner(closes: pd.Series, df: pd.DataFrame) -> pd.Series:
    s1 = triple_sma(closes, 5, 20, 60)
    s2 = keltner_breakout(closes, df, 20, 1.5)
    vote = s1 + s2
    sig  = pd.Series(0.0, index=closes.index)
    sig[vote > 0.5]  =  1
    sig[vote < -0.5] = -1
    return sig


def _full_ensemble(closes: pd.Series, df: pd.DataFrame, pair_symbol: str) -> pd.Series:
    s1 = triple_sma(closes, 5, 20, 60)
    s2 = vol_scaled_momentum(closes, 20, 20)
    s3 = carry_trade(closes, pair_symbol)
    s4 = adaptive_regime(closes)
    s5 = keltner_breakout(closes, df, 20, 1.5)
    vote = s1 + s2 + s3 + s4 + s5
    sig  = pd.Series(0.0, index=closes.index)
    sig[vote >= 3]  =  1
    sig[vote <= -3] = -1
    return sig


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS & REPORTING
# ══════════════════════════════════════════════════════════════════════════════

def print_round_summary(round_num: int, results: List[dict], top_n: int = 10):
    if not results:
        print(f"  No results for round {round_num}")
        return

    df = pd.DataFrame(results)
    agg = (
        df.groupby("strategy")
          .agg(
              avg_sharpe   = ("sharpe", "mean"),
              avg_cagr     = ("cagr",   "mean"),
              avg_dd       = ("max_drawdown", "mean"),
              avg_winrate  = ("win_rate", "mean"),
              best_pair    = ("label", lambda x:
                                df.loc[x.index].sort_values("sharpe").iloc[-1]["label"]),
              n_pairs      = ("pair", "count"),
          )
          .reset_index()
          .sort_values("avg_sharpe", ascending=False)
    )

    print(f"\n  ROUND {round_num} — TOP {top_n} STRATEGIES (avg across pairs):")
    print(f"  {'Strategy':<22} {'Sharpe':>8} {'CAGR%':>8} {'MaxDD%':>8} {'WinRate':>8} {'BestPair':<14}")
    print("  " + "-" * 78)
    for _, r in agg.head(top_n).iterrows():
        print(f"  {r['strategy']:<22} {r['avg_sharpe']:>+8.3f} {r['avg_cagr']:>8.2f}% "
              f"{r['avg_dd']:>8.2f}% {r['avg_winrate']:>7.1f}%  {r['best_pair']:<14}")

    return agg


def save_round(round_num: int, results: List[dict], agg: pd.DataFrame):
    out = ROUNDS_DIR / f"forex_round_{round_num}.json"
    data = {
        "round":     round_num,
        "timestamp": datetime.now().isoformat(),
        "n_results": len(results),
        "top10":     agg.head(10).to_dict("records") if agg is not None else [],
        "all":       results,
    }
    with open(out, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved → {out}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=None)
    parser.add_argument("--all",   action="store_true")
    args = parser.parse_args()

    print("=" * 72)
    print("FOREX AUTORESEARCH HARNESS — Karpathy Loop")
    print(f"Pairs: {len(PAIRS)}  |  Period: {YEARS} years  |  Cost: 1bp per trade")
    print("=" * 72)

    # Load all pair data
    print("\n  Loading forex pairs...")
    pairs_data = {}
    for sym in PAIRS:
        df = fetch_pair(sym)
        if df is not None:
            pairs_data[sym] = df
            print(f"    ✓ {PAIRS[sym]['label']} ({len(df)} days)")
        else:
            print(f"    ✗ {PAIRS[sym]['label']} — skipped")

    # Load macro data
    print("\n  Loading macro data...")
    macro = {}
    for sid in ["DFF", "T10Y2Y", "GS10", "DCOILWTICO",
                "IRLTLT01EZM156N", "BAMLH0A0HYM2", "VIXCLS"]:
        s = fetch_fred(sid)
        if s is not None:
            macro[sid] = s
            print(f"    ✓ FRED {sid}")

    # Determine which rounds to run
    rounds_to_run = list(range(1, 9)) if args.all else (
        [args.round] if args.round else list(range(1, 9))
    )

    all_top = {}
    for rnd in rounds_to_run:
        print(f"\n{'='*72}")
        print(f"  ROUND {rnd}")
        print(f"{'='*72}")
        results = build_round_results(rnd, pairs_data, macro)
        agg = print_round_summary(rnd, results)
        save_round(rnd, results, agg)
        if agg is not None and len(agg) > 0:
            all_top[rnd] = agg.head(3).to_dict("records")

    # Final cross-round champion
    print(f"\n{'='*72}")
    print("  CROSS-ROUND CHAMPIONS")
    print(f"{'='*72}")
    for rnd, top in all_top.items():
        if top:
            best = top[0]
            print(f"  R{rnd}: {best['strategy']:<22} Sharpe {best['avg_sharpe']:+.3f}  "
                  f"CAGR {best['avg_cagr']:.2f}%")

    print("\n  Done.")


if __name__ == "__main__":
    main()
