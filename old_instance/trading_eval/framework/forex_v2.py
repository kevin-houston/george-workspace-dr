#!/usr/bin/env python3
"""
forex_v2.py — Forex Strategy Trade Logger (Framework v2)
=========================================================
Replays all forex strategy variants from forex_harness.py and logs
individual trades via TradeLogger.

Strategy families:
  R1: Baseline — SMA crossover, momentum, simple mean reversion
  R2: Oscillator-based — RSI, Bollinger Bands, CCI
  R3: Volatility regime — ATR breakout, vol-scaled momentum
  R4: Carry trade — interest rate differential proxies
  R5: Session momentum — NY open, London breakout patterns (macro-enhanced)
  R6: Macro-enhanced — FRED rate/inflation differentials
  R7: Combo ensemble — top strategies from R1-R6 combined
  R8: Adaptive — regime-switching between trend and reversion

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/forex_v2.py
"""

from __future__ import annotations

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

# ── sys.path setup ─────────────────────────────────────────────────────────────
FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

from base_harness import TradeLogger, fetch_data, get_close as _bh_get_close

try:
    import numpy as np
    import pandas as pd
except ImportError as e:
    print(f"Missing: {e}")
    print("Activate venv and install: pip install numpy pandas yfinance")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────────

YEARS      = 10
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")
FRED_KEY   = os.environ.get("FRED_API_KEY", "")
MACRO_DIR  = EVAL_DIR / "macro_cache"
MACRO_DIR.mkdir(exist_ok=True)

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

RATES = {
    "USD": 3.5,
    "EUR": 2.5,
    "GBP": 4.0,
    "JPY": 0.5,
    "AUD": 4.0,
    "CAD": 3.0,
    "CHF": 0.5,
    "NZD": 3.5,
}


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

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


def load_pairs() -> Dict[str, pd.DataFrame]:
    """Fetch all forex pairs via base_harness fetch_data. Returns {symbol: df}."""
    symbols = list(PAIRS.keys())
    raw = fetch_data(symbols, START_DATE, END_DATE)
    result = {}
    for sym in symbols:
        if sym not in raw:
            print(f"    skipped {sym} (no data)")
            continue
        df = raw[sym]
        if df is None or len(df) < 200:
            print(f"    skipped {sym} (insufficient data: {len(df) if df is not None else 0} rows)")
            continue
        # Normalize columns if MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        df = df[["Open", "High", "Low", "Close"]].dropna()
        # Strip timezone
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        result[sym] = df
        print(f"    {PAIRS[sym]['label']} ({len(df)} days)")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY LIBRARY  (exact logic from forex_harness.py)
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
    sig[z < -threshold] =  1
    sig[z >  threshold] = -1
    return sig


def triple_sma(closes: pd.Series, fast: int, mid: int, slow: int) -> pd.Series:
    """Three-line SMA — all aligned for trend confirmation."""
    f = closes.rolling(fast).mean()
    m = closes.rolling(mid).mean()
    s = closes.rolling(slow).mean()
    sig = pd.Series(0.0, index=closes.index)
    sig[(f > m) & (m > s)] =  1
    sig[(f < m) & (m < s)] = -1
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
    sig[closes < lower] =  1
    sig[closes > upper] = -1
    return sig


def cci_signal(closes: pd.Series, window: int = 20, threshold: float = 100) -> pd.Series:
    """CCI — Commodity Channel Index trend/reversion hybrid."""
    typ = closes
    ma  = typ.rolling(window).mean()
    md  = typ.rolling(window).apply(lambda x: np.abs(x - x.mean()).mean())
    cci = (typ - ma) / (0.015 * md.replace(0, np.nan))
    sig = pd.Series(0.0, index=closes.index)
    sig[cci >  threshold] =  1
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
    sig[df["Close"] > high_.shift(1)] =  1
    sig[df["Close"] < low_.shift(1)]  = -1
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
    """
    meta      = PAIRS[pair_symbol]
    base_rate = RATES.get(meta["base"], 2.0)
    quote_rate = RATES.get(meta["quote"], 2.0)
    carry_diff = base_rate - quote_rate

    if abs(carry_diff) < carry_threshold:
        return pd.Series(0.0, index=closes.index)

    direction = 1.0 if carry_diff > 0 else -1.0

    sma50 = closes.rolling(50).mean()
    sig   = pd.Series(direction, index=closes.index)
    if direction > 0:
        sig[closes < sma50 * 0.98] = 0
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
    """
    ret  = closes.pct_change()
    sig  = pd.Series(0.0, index=closes.index)
    dow  = closes.index.dayofweek
    mom5 = closes.pct_change(5)

    label = PAIRS[pair_symbol]["label"]
    if "JPY" in label:
        sig[(dow <= 1) & (mom5 < 0)] =  1
        sig[(dow == 4) & (mom5 > 0)] = -1
    else:
        sig[(dow <= 2) & (mom5 > 0)] =  1
        sig[(dow <= 2) & (mom5 < 0)] = -1
        sig[(dow >= 3) & (mom5 > 0.01)] = -1
    return sig.fillna(0)


def monday_breakout(closes: pd.Series) -> pd.Series:
    """
    Monday price action sets the weekly tone — buy Monday morning breakout.
    """
    sig = pd.Series(0.0, index=closes.index)
    dow = closes.index.dayofweek
    fri_close = closes.shift(3)
    sig[(dow == 0) & (closes > fri_close)] =  1
    sig[(dow == 0) & (closes < fri_close)] = -1
    sig[(dow == 1) | (dow == 2)] = sig[(dow == 1) | (dow == 2)].ffill()
    sig[dow >= 3] = 0
    return sig.fillna(0)


# ── R6: Macro-enhanced forex ──────────────────────────────────────────────────

def macro_rate_diff_signal(closes: pd.Series, pair_symbol: str,
                           us_rate: pd.Series, foreign_rate: pd.Series) -> pd.Series:
    """Trade direction based on yield spread changes."""
    meta  = PAIRS[pair_symbol]
    idx   = closes.index
    if us_rate is None or foreign_rate is None:
        return pd.Series(0.0, index=idx)

    us_r  = us_rate.reindex(idx, method="ffill")
    fo_r  = foreign_rate.reindex(idx, method="ffill")
    spread = us_r - fo_r
    spread_mom = spread - spread.shift(21)

    is_usd_base  = meta["base"] == "USD"
    is_usd_quote = meta["quote"] == "USD"

    sig = pd.Series(0.0, index=idx)
    if is_usd_base:
        sig[spread_mom > 0.1]  =  1
        sig[spread_mom < -0.1] = -1
    elif is_usd_quote:
        sig[spread_mom > 0.1]  = -1
        sig[spread_mom < -0.1] =  1
    else:
        base_rate  = RATES.get(meta["base"], 2.0)
        quote_rate = RATES.get(meta["quote"], 2.0)
        sig[:] = np.sign(base_rate - quote_rate)
    return sig.fillna(0)


def oil_fx_correlation(closes: pd.Series, pair_symbol: str,
                       oil: pd.Series) -> pd.Series:
    """Oil-correlated pairs: CAD and NOK strengthen with oil, JPY weakens."""
    meta  = PAIRS[pair_symbol]
    label = meta["label"]
    idx   = closes.index
    if oil is None:
        return pd.Series(0.0, index=idx)

    oil_aligned = oil.reindex(idx, method="ffill")
    oil_mom  = oil_aligned.pct_change(10)

    sig = pd.Series(0.0, index=idx)
    if "CAD" in label:
        if meta["base"] == "USD":
            sig[oil_mom > 0.02]  = -1
            sig[oil_mom < -0.02] =  1
        else:
            sig[oil_mom > 0.02]  =  1
            sig[oil_mom < -0.02] = -1
    elif "JPY" in label and meta["quote"] == "JPY":
        sig[oil_mom > 0.05]  = -1
        sig[oil_mom < -0.02] =  1
    return sig.fillna(0)


# ── R7: Ensemble ──────────────────────────────────────────────────────────────

def ensemble_top3(closes: pd.Series, pair_symbol: str) -> pd.Series:
    """Combine top 3 strategies from R1-R6 by vote."""
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


# ── R8: Adaptive / regime-switching ──────────────────────────────────────────

def adaptive_regime(closes: pd.Series, vol_window: int = 20,
                    trend_fast: int = 10, trend_slow: int = 40,
                    rev_window: int = 20, rev_thresh: float = 1.5) -> pd.Series:
    """
    Full adaptive: detect trending vs ranging regime,
    apply SMA trend in trending regime, z-score reversion in ranging.
    """
    ret    = closes.pct_change().fillna(0)
    autocorr = ret.rolling(40).apply(
        lambda x: pd.Series(x).autocorr(lag=1) if len(x) > 10 else 0.0, raw=False
    ).fillna(0)

    trend = np.sign(closes.rolling(trend_fast).mean() - closes.rolling(trend_slow).mean())
    roll_mean = closes.rolling(rev_window).mean()
    roll_std  = closes.rolling(rev_window).std().replace(0, np.nan)
    z_rev     = -(closes - roll_mean) / roll_std

    sig = pd.Series(0.0, index=closes.index)
    sig[autocorr > 0.05]  = trend[autocorr > 0.05]
    sig[autocorr < -0.05] = np.sign(z_rev[autocorr < -0.05])
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
        sig[yc < -0.2] =  1
        sig[yc >  0.5] = -1
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
#  TRADE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_trades(closes: pd.Series, raw_signals: pd.Series,
                   ticker_label: str, params_dict: dict,
                   notes_str: str = "") -> list:
    """
    Convert a raw signal series into per-trade records.
    Applies one-bar shift (next-day execution) to avoid lookahead bias,
    matching the original forex_harness backtest engine.
    """
    # Apply same shift as original backtest: signal on day T → position applied T+1
    sig = raw_signals.reindex(closes.index).ffill().fillna(0).shift(1).fillna(0)
    pos_series = np.sign(sig).astype(int)

    trades = []
    current_pos = 0
    entry_i = None
    entry_price = None

    for i in range(len(closes)):
        dt    = closes.index[i]
        price = float(closes.iloc[i])
        new_pos = int(pos_series.iloc[i])

        if new_pos != current_pos:
            # Close existing position
            if current_pos != 0 and entry_i is not None:
                exit_price = price
                ret_pct = (exit_price / entry_price - 1.0) * current_pos
                hold_days = max(1, (dt - closes.index[entry_i]).days)
                trades.append({
                    "ticker":       ticker_label,
                    "entry_date":   closes.index[entry_i],
                    "exit_date":    dt,
                    "return_pct":   round(ret_pct * 100, 6),
                    "hold_days":    hold_days,
                    "direction":    "long" if current_pos > 0 else "short",
                    "entry_price":  round(entry_price, 8),
                    "exit_price":   round(exit_price, 8),
                    "params":       params_dict,
                    "notes":        notes_str,
                })

            # Open new position
            if new_pos != 0:
                entry_i = i
                entry_price = price
            else:
                entry_i = None
                entry_price = None
            current_pos = new_pos

    # Close any open position at end of series
    if current_pos != 0 and entry_i is not None:
        last_price = float(closes.iloc[-1])
        last_dt    = closes.index[-1]
        ret_pct    = (last_price / entry_price - 1.0) * current_pos
        hold_days  = max(1, (last_dt - closes.index[entry_i]).days)
        trades.append({
            "ticker":       ticker_label,
            "entry_date":   closes.index[entry_i],
            "exit_date":    last_dt,
            "return_pct":   round(ret_pct * 100, 6),
            "hold_days":    hold_days,
            "direction":    "long" if current_pos > 0 else "short",
            "entry_price":  round(entry_price, 8),
            "exit_price":   round(last_price, 8),
            "params":       params_dict,
            "notes":        notes_str,
        })

    return trades


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND CONFIGS
# ══════════════════════════════════════════════════════════════════════════════

def get_round_configs(round_num: int, sym: str, df: pd.DataFrame,
                      c: pd.Series, macro: dict) -> list:
    """
    Returns list of (strat_name, signal_fn, params_dict) for a given round.
    Matches exact configs from forex_harness.py build_round_results().
    """
    configs = []

    if round_num == 1:
        configs = [
            ("SMA_5_20",         lambda c=c: sma_cross(c, 5, 20),
             {"fast": 5, "slow": 20}),
            ("SMA_10_50",        lambda c=c: sma_cross(c, 10, 50),
             {"fast": 10, "slow": 50}),
            ("SMA_20_100",       lambda c=c: sma_cross(c, 20, 100),
             {"fast": 20, "slow": 100}),
            ("SMA_50_200",       lambda c=c: sma_cross(c, 50, 200),
             {"fast": 50, "slow": 200}),
            ("MOM_5",            lambda c=c: momentum(c, 5),
             {"lookback": 5}),
            ("MOM_10",           lambda c=c: momentum(c, 10),
             {"lookback": 10}),
            ("MOM_20",           lambda c=c: momentum(c, 20),
             {"lookback": 20}),
            ("MOM_60",           lambda c=c: momentum(c, 60),
             {"lookback": 60}),
            ("MeanRev_20_1.5",   lambda c=c: mean_reversion(c, 20, 1.5),
             {"window": 20, "threshold": 1.5}),
            ("MeanRev_20_2.0",   lambda c=c: mean_reversion(c, 20, 2.0),
             {"window": 20, "threshold": 2.0}),
            ("MeanRev_40_1.5",   lambda c=c: mean_reversion(c, 40, 1.5),
             {"window": 40, "threshold": 1.5}),
            ("TriSMA_5_20_60",   lambda c=c: triple_sma(c, 5, 20, 60),
             {"fast": 5, "mid": 20, "slow": 60}),
            ("TriSMA_10_50_200", lambda c=c: triple_sma(c, 10, 50, 200),
             {"fast": 10, "mid": 50, "slow": 200}),
        ]

    elif round_num == 2:
        configs = [
            ("RSI_14_Rev",       lambda c=c: rsi_signal(c, 14, 30, 70),
             {"period": 14, "oversold": 30, "overbought": 70}),
            ("RSI_14_Rev_Tight", lambda c=c: rsi_signal(c, 14, 20, 80),
             {"period": 14, "oversold": 20, "overbought": 80}),
            ("RSI_7_Rev",        lambda c=c: rsi_signal(c, 7, 25, 75),
             {"period": 7, "oversold": 25, "overbought": 75}),
            ("RSI_14_Trend",     lambda c=c: rsi_trend(c, 14),
             {"period": 14, "bull_line": 50, "bear_line": 50}),
            ("RSI_21_Trend",     lambda c=c: rsi_trend(c, 21),
             {"period": 21, "bull_line": 50, "bear_line": 50}),
            ("BB_Break_2.0",     lambda c=c: bollinger_breakout(c, 20, 2.0),
             {"window": 20, "n_std": 2.0}),
            ("BB_Break_2.5",     lambda c=c: bollinger_breakout(c, 20, 2.5),
             {"window": 20, "n_std": 2.5}),
            ("BB_Rev_2.0",       lambda c=c: bollinger_reversion(c, 20, 2.0),
             {"window": 20, "n_std": 2.0}),
            ("BB_Rev_1.5",       lambda c=c: bollinger_reversion(c, 20, 1.5),
             {"window": 20, "n_std": 1.5}),
            ("CCI_100",          lambda c=c: cci_signal(c, 20, 100),
             {"window": 20, "threshold": 100}),
            ("CCI_150",          lambda c=c: cci_signal(c, 20, 150),
             {"window": 20, "threshold": 150}),
        ]

    elif round_num == 3:
        configs = [
            ("ATR_Break_20",    lambda c=c, df=df: atr_breakout(df, 14, 1.5, 20),
             {"atr_window": 14, "mult": 1.5, "lookback": 20}),
            ("ATR_Break_10",    lambda c=c, df=df: atr_breakout(df, 14, 1.5, 10),
             {"atr_window": 14, "mult": 1.5, "lookback": 10}),
            ("VolMom_10",       lambda c=c: vol_scaled_momentum(c, 10, 20),
             {"mom_window": 10, "vol_window": 20, "target_vol": 0.10}),
            ("VolMom_20",       lambda c=c: vol_scaled_momentum(c, 20, 20),
             {"mom_window": 20, "vol_window": 20, "target_vol": 0.10}),
            ("VolMom_40",       lambda c=c: vol_scaled_momentum(c, 40, 20),
             {"mom_window": 40, "vol_window": 20, "target_vol": 0.10}),
            ("VolSwitch_10_50", lambda c=c: vol_regime_switch(c, 10, 50),
             {"fast": 10, "slow": 50, "vol_window": 20}),
            ("VolSwitch_5_20",  lambda c=c: vol_regime_switch(c, 5, 20),
             {"fast": 5, "slow": 20, "vol_window": 20}),
            ("Keltner_20_1.5",  lambda c=c, df=df: keltner_breakout(c, df, 20, 1.5),
             {"ema_period": 20, "atr_mult": 1.5}),
            ("Keltner_20_2.0",  lambda c=c, df=df: keltner_breakout(c, df, 20, 2.0),
             {"ema_period": 20, "atr_mult": 2.0}),
            ("Keltner_40_2.0",  lambda c=c, df=df: keltner_breakout(c, df, 40, 2.0),
             {"ema_period": 40, "atr_mult": 2.0}),
        ]

    elif round_num == 4:
        configs = [
            ("Carry_0.5",   lambda c=c, s=sym: carry_trade(c, s, 0.5),
             {"carry_threshold": 0.5}),
            ("Carry_1.0",   lambda c=c, s=sym: carry_trade(c, s, 1.0),
             {"carry_threshold": 1.0}),
            ("CarryMom_20", lambda c=c, s=sym: carry_momentum_combo(c, s, 20),
             {"mom_window": 20}),
            ("CarryMom_10", lambda c=c, s=sym: carry_momentum_combo(c, s, 10),
             {"mom_window": 10}),
            ("TrendCarry",  lambda c=c, s=sym: trend_carry_combo(c, s),
             {}),
            ("DayOfWeek",   lambda c=c, s=sym: day_of_week_effect(c, s),
             {}),
            ("MonBreakout", lambda c=c: monday_breakout(c),
             {}),
        ]

    elif round_num == 5:
        us_10y = macro.get("GS10")
        eu_10y = macro.get("IRLTLT01EZM156N")
        oil    = macro.get("DCOILWTICO")
        configs = [
            ("OilFX",           lambda c=c, s=sym, o=oil: oil_fx_correlation(c, s, o),
             {}),
            ("MacroRate_US_EU", lambda c=c, s=sym, u=us_10y, f=eu_10y:
                                  macro_rate_diff_signal(c, s, u, f),
             {"us_series": "GS10", "foreign_series": "IRLTLT01EZM156N"}),
            ("SMA_20_100_HC",   lambda c=c: sma_cross(c, 20, 100),
             {"fast": 20, "slow": 100, "high_cost": True}),
            ("VolMom_20_HC",    lambda c=c: vol_scaled_momentum(c, 20, 20),
             {"mom_window": 20, "vol_window": 20, "high_cost": True}),
        ]

    elif round_num == 6:
        dff    = macro.get("DFF")
        t10y2y = macro.get("T10Y2Y")
        configs = [
            ("FedFunds_Trend",  lambda c=c, s=sym, r=dff:
                                  macro_rate_diff_signal(c, s, r, r),
             {"us_series": "DFF"}),
            ("YieldCurve_FX",   lambda c=c, s=sym: _yield_curve_fx(c, s, t10y2y),
             {"t10y2y_series": "T10Y2Y"}),
            ("Adaptive",        lambda c=c: adaptive_regime(c),
             {"vol_window": 20, "trend_fast": 10, "trend_slow": 40}),
            ("Adaptive_Tight",  lambda c=c: adaptive_regime(c, 20, 5, 20, 20, 2.0),
             {"vol_window": 20, "trend_fast": 5, "trend_slow": 20, "rev_thresh": 2.0}),
        ]

    elif round_num == 7:
        configs = [
            ("Ensemble_Top3",  lambda c=c, s=sym: ensemble_top3(c, s),
             {}),
            ("SMA_VolMom",     lambda c=c: _combo_sma_volmom(c),
             {}),
            ("Carry_Adaptive", lambda c=c, s=sym: _combo_carry_adaptive(c, s),
             {}),
        ]

    elif round_num == 8:
        configs = [
            ("VolMom_10_Scaled", lambda c=c: vol_scaled_momentum(c, 10, 15, 0.12),
             {"mom_window": 10, "vol_window": 15, "target_vol": 0.12}),
            ("Adaptive_v2",      lambda c=c: adaptive_regime(c, 15, 8, 40, 25, 1.5),
             {"vol_window": 15, "trend_fast": 8, "trend_slow": 40, "rev_thresh": 1.5}),
            ("TriSMA_Keltner",   lambda c=c, df=df: _combo_trisma_keltner(c, df),
             {}),
            ("Full_Ensemble",    lambda c=c, df=df, s=sym: _full_ensemble(c, df, s),
             {}),
        ]

    return configs


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("FOREX V2 — Trade Logger (Framework Edition)")
    print(f"Pairs: {len(PAIRS)}  |  Period: {YEARS} years  |  Rounds: 1-8")
    print("=" * 72)

    # Load pair data
    print("\n  Loading forex pairs...")
    pairs_data = load_pairs()
    if not pairs_data:
        print("ERROR: No pair data loaded. Check network / yfinance.")
        sys.exit(1)

    # Load macro data
    print("\n  Loading macro data (FRED)...")
    macro = {}
    for sid in ["DFF", "T10Y2Y", "GS10", "DCOILWTICO",
                "IRLTLT01EZM156N", "BAMLH0A0HYM2", "VIXCLS"]:
        s = fetch_fred(sid)
        if s is not None:
            macro[sid] = s
            print(f"    FRED {sid}: {len(s)} obs")
        else:
            print(f"    FRED {sid}: unavailable (no key or network error)")

    # Round → TradeLogger round_num mapping:
    #   R1 (basic baseline)     → round_num 1
    #   R2-R8 (more complex)    → round_num 2
    ROUND_NUM_MAP = {1: 1, 2: 2, 3: 2, 4: 2, 5: 2, 6: 2, 7: 2, 8: 2}

    # Collect all loggers: {strat_name: TradeLogger}
    loggers: Dict[str, TradeLogger] = {}

    total_trades = 0

    for forex_round in range(1, 9):
        round_num = ROUND_NUM_MAP[forex_round]
        print(f"\n  --- Forex Round {forex_round} (logger round_num={round_num}) ---")

        for sym, df in pairs_data.items():
            c          = df["Close"]
            pair_label = PAIRS[sym]["label"].replace("/", "_")

            configs = get_round_configs(forex_round, sym, df, c, macro)

            for strat_name, fn, params_dict in configs:
                try:
                    raw_signals = fn()
                    if raw_signals is None or len(raw_signals) == 0:
                        continue
                except Exception as e:
                    continue

                # Get or create logger for this strategy variant
                logger_key = f"forex_{strat_name}"
                if logger_key not in loggers:
                    loggers[logger_key] = TradeLogger(
                        round_num=round_num,
                        strategy=f"forex_{strat_name}",
                        category="forex",
                    )

                logger = loggers[logger_key]
                notes = f"forex_round={forex_round} pair={PAIRS[sym]['label']}"

                trades = extract_trades(c, raw_signals, pair_label, params_dict, notes)

                for trade in trades:
                    try:
                        logger.log(**trade)
                        total_trades += 1
                    except Exception as e:
                        pass

    # Save all loggers
    print(f"\n  Saving {len(loggers)} strategy loggers ({total_trades} total trades)...")
    for logger_key, logger in sorted(loggers.items()):
        if len(logger) > 0:
            logger.save()
        else:
            print(f"  [TradeLogger] {logger_key}: 0 trades — skipped")

    print("\n  Done.")


if __name__ == "__main__":
    main()
