#!/usr/bin/env python3
"""
crypto_v2.py — Crypto Strategy Trade Logger (Framework v2)
===========================================================
Replays all crypto strategy variants from crypto_harness.py and logs
individual trades via TradeLogger.

Rounds:
  C1: Baseline momentum + mean reversion strategies
  C2: Crypto-specific strategies (dominance, weekend effect, hash ribbon, etc.)
  C3: Cross-asset crypto signals (BTC leads alts, gold/BTC, dollar inverse, VIX)

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/crypto_v2.py
"""

from __future__ import annotations

import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── sys.path setup ─────────────────────────────────────────────────────────────
FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

from base_harness import TradeLogger, fetch_data, get_close as _bh_get_close

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Activate venv and install: pip install numpy pandas yfinance")
    sys.exit(1)

# ── Constants ──────────────────────────────────────────────────────────────────

START_DATE       = "2018-01-01"
END_DATE         = datetime.now().strftime("%Y-%m-%d")
TRANSACTION_COST = 0.0005  # 5bp per trade (preserved from crypto_harness.py)

CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD",
    "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD",
]

EXTRA_TICKERS = ["DX-Y.NYB", "^VIX", "GLD"]


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def load_prices() -> Tuple[Dict[str, Optional[pd.Series]],
                           Dict[str, Optional[pd.DataFrame]],
                           Dict[str, Optional[pd.Series]]]:
    """
    Fetch all crypto and extra tickers via base_harness fetch_data.
    Returns (prices_dict, ohlcv_dict, extra_prices).
    """
    all_tickers = CRYPTO_UNIVERSE + EXTRA_TICKERS
    print(f"  Fetching {len(all_tickers)} tickers via base_harness fetch_data...")
    raw = fetch_data(all_tickers, START_DATE, END_DATE)

    prices_dict: Dict[str, Optional[pd.Series]] = {}
    ohlcv_dict:  Dict[str, Optional[pd.DataFrame]] = {}
    extra_prices: Dict[str, Optional[pd.Series]] = {}

    for ticker in CRYPTO_UNIVERSE:
        if ticker not in raw or raw[ticker] is None or len(raw[ticker]) < 100:
            print(f"    {ticker}: FAILED or insufficient data")
            prices_dict[ticker] = None
            ohlcv_dict[ticker]  = None
            continue
        df = raw[ticker]
        # Normalize MultiIndex columns (yfinance batch download)
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        # Strip timezone
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        # Close series
        close = df["Close"].dropna() if "Close" in df.columns else df.iloc[:, 0].dropna()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        prices_dict[ticker] = close.squeeze()
        ohlcv_dict[ticker]  = df
        print(f"    {ticker}: {len(close)} days")

    for ticker in EXTRA_TICKERS:
        if ticker not in raw or raw[ticker] is None or len(raw[ticker]) < 50:
            print(f"    {ticker}: FAILED or insufficient data")
            extra_prices[ticker] = None
            continue
        df = raw[ticker]
        if isinstance(df.columns, pd.MultiIndex):
            df = df.droplevel(1, axis=1)
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        close = df["Close"].dropna() if "Close" in df.columns else df.iloc[:, 0].dropna()
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        extra_prices[ticker] = close.squeeze()
        print(f"    {ticker}: {len(close)} days")

    return prices_dict, ohlcv_dict, extra_prices


# ══════════════════════════════════════════════════════════════════════════════
#  TECHNICAL INDICATORS  (exact logic from crypto_harness.py)
# ══════════════════════════════════════════════════════════════════════════════

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    rs = up.rolling(period).mean() / dn.rolling(period).mean().replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def bollinger(series: pd.Series, period: int = 20,
              std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid   = sma(series, period)
    sigma = series.rolling(period).std()
    return mid - std * sigma, mid, mid + std * sigma

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift(1)).abs(),
        (lo - cl.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def zscore(series: pd.Series, window: int) -> pd.Series:
    m = series.rolling(window).mean()
    s = series.rolling(window).std()
    return (series - m) / s.replace(0, np.nan)


# ══════════════════════════════════════════════════════════════════════════════
#  TRADE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_trades(prices: pd.Series, signal: pd.Series,
                   ticker: str, long_short: bool,
                   params_dict: dict, notes_str: str = "") -> list:
    """
    Convert a signal series into per-trade records.

    In crypto_harness.py, signals are already shifted once when constructed,
    then shifted again inside backtest(). We replicate that behaviour here:
    the signal passed in has one shift applied; we apply a second shift to
    determine effective positions, matching actual return computation.
    """
    # Align
    common = signal.index.intersection(prices.index)
    if len(common) < 50:
        return []

    sig = signal.reindex(common).fillna(0)
    px  = prices.reindex(common)

    # Apply long-only clip if needed (matches backtest engine)
    pos = sig.copy()
    if not long_short:
        pos = pos.clip(lower=0)

    # Second shift: matches pos.shift(1) inside backtest()
    pos_shifted = pos.shift(1).fillna(0)
    pos_discrete = np.sign(pos_shifted).astype(int)

    trades = []
    current_pos = 0
    entry_i = None
    entry_price = None

    for i in range(len(common)):
        dt    = common[i]
        price = float(px.iloc[i])
        new_pos = int(pos_discrete.iloc[i])

        if new_pos != current_pos:
            # Close existing position
            if current_pos != 0 and entry_i is not None:
                exit_price = price
                ret_pct    = (exit_price / entry_price - 1.0) * current_pos
                hold_days  = max(1, (dt - common[entry_i]).days)
                trades.append({
                    "ticker":       ticker,
                    "entry_date":   common[entry_i],
                    "exit_date":    dt,
                    "return_pct":   round(ret_pct * 100, 6),
                    "hold_days":    hold_days,
                    "direction":    "long" if current_pos > 0 else "short",
                    "entry_price":  round(entry_price, 6),
                    "exit_price":   round(exit_price, 6),
                    "long_short":   long_short,
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

    # Close open position at end of series
    if current_pos != 0 and entry_i is not None:
        last_price = float(px.iloc[-1])
        last_dt    = common[-1]
        ret_pct    = (last_price / entry_price - 1.0) * current_pos
        hold_days  = max(1, (last_dt - common[entry_i]).days)
        trades.append({
            "ticker":       ticker,
            "entry_date":   common[entry_i],
            "exit_date":    last_dt,
            "return_pct":   round(ret_pct * 100, 6),
            "hold_days":    hold_days,
            "direction":    "long" if current_pos > 0 else "short",
            "entry_price":  round(entry_price, 6),
            "exit_price":   round(last_price, 6),
            "long_short":   long_short,
            "params":       params_dict,
            "notes":        notes_str,
        })

    return trades


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND C1: Baseline Strategies
# ══════════════════════════════════════════════════════════════════════════════

def build_c1_loggers(prices_dict: Dict[str, Optional[pd.Series]]) -> Dict[str, TradeLogger]:
    """
    Baseline momentum + mean reversion strategies.
    One TradeLogger per (strategy_type + params + mode) variant.
    Exact signal logic preserved from crypto_harness.py run_round_c1().
    """
    loggers: Dict[str, TradeLogger] = {}

    sma_pairs          = [(5, 20), (10, 50), (20, 100), (50, 200)]
    mom_periods        = [5, 10, 20, 60]
    rsi_bands          = [(25, 75), (20, 80)]
    boll_stds          = [1.5, 2.0]
    zscore_thresholds  = [1.5, 2.0]
    modes              = ["long_only", "long_short"]

    coins = [c for c, px in prices_dict.items() if px is not None and len(px) >= 200]

    for ls_mode in modes:
        ls = ls_mode == "long_short"

        # SMA Crossovers
        for fast, slow in sma_pairs:
            key = f"crypto_sma_crossover_{fast}_{slow}_{ls_mode}"
            logger = TradeLogger(round_num=3, strategy=key, category="crypto")
            for coin in coins:
                px = prices_dict[coin]
                fast_sma = sma(px, fast)
                slow_sma = sma(px, slow)
                sig = (fast_sma > slow_sma).astype(float) * 2 - 1
                sig = sig.shift(1)  # matches crypto_harness.py
                params = {"fast": fast, "slow": slow, "mode": ls_mode}
                notes  = f"round=C1 strategy_type=sma_crossover coin={coin}"
                for trade in extract_trades(px, sig, coin, ls, params, notes):
                    logger.log(**trade)
            loggers[key] = logger

        # Momentum
        for period in mom_periods:
            key = f"crypto_momentum_{period}d_{ls_mode}"
            logger = TradeLogger(round_num=3, strategy=key, category="crypto")
            for coin in coins:
                px = prices_dict[coin]
                mom_sig = px.pct_change(period)
                sig = (mom_sig > 0).astype(float) * 2 - 1
                sig = sig.shift(1)
                params = {"period": period, "mode": ls_mode}
                notes  = f"round=C1 strategy_type=momentum coin={coin}"
                for trade in extract_trades(px, sig, coin, ls, params, notes):
                    logger.log(**trade)
            loggers[key] = logger

        # RSI Mean Reversion
        for lo_band, hi_band in rsi_bands:
            key = f"crypto_rsi_reversion_{lo_band}_{hi_band}_{ls_mode}"
            logger = TradeLogger(round_num=3, strategy=key, category="crypto")
            for coin in coins:
                px = prices_dict[coin]
                rsi_vals = rsi(px, 14)
                sig = pd.Series(0.0, index=px.index)
                sig[rsi_vals < lo_band] =  1.0
                sig[rsi_vals > hi_band] = -1.0
                sig = sig.replace(0, np.nan).ffill().fillna(0)
                mid_cross = ((rsi_vals > 50) & (sig < 0)) | ((rsi_vals < 50) & (sig > 0))
                sig[mid_cross] = 0
                sig = sig.shift(1)
                params = {"period": 14, "lo_band": lo_band, "hi_band": hi_band, "mode": ls_mode}
                notes  = f"round=C1 strategy_type=rsi_reversion coin={coin}"
                for trade in extract_trades(px, sig, coin, ls, params, notes):
                    logger.log(**trade)
            loggers[key] = logger

        # Bollinger Reversion
        for std_mult in boll_stds:
            key = f"crypto_bollinger_reversion_{std_mult}std_{ls_mode}"
            logger = TradeLogger(round_num=3, strategy=key, category="crypto")
            for coin in coins:
                px = prices_dict[coin]
                lower, mid, upper = bollinger(px, 20, std_mult)
                sig = pd.Series(0.0, index=px.index)
                sig[px < lower] =  1.0
                sig[px > upper] = -1.0
                sig[px.between(lower * 0.99, upper * 1.01)] = 0
                sig = sig.shift(1)
                params = {"window": 20, "std_mult": std_mult, "mode": ls_mode}
                notes  = f"round=C1 strategy_type=bollinger_reversion coin={coin}"
                for trade in extract_trades(px, sig, coin, ls, params, notes):
                    logger.log(**trade)
            loggers[key] = logger

        # Z-score Mean Reversion
        for thresh in zscore_thresholds:
            key = f"crypto_zscore_reversion_{thresh}_{ls_mode}"
            logger = TradeLogger(round_num=3, strategy=key, category="crypto")
            for coin in coins:
                px = prices_dict[coin]
                zs = zscore(px, 20)
                sig = pd.Series(0.0, index=px.index)
                sig[zs < -thresh] =  1.0
                sig[zs >  thresh] = -1.0
                sig[zs.abs() < 0.5] = 0
                sig = sig.shift(1)
                params = {"window": 20, "threshold": thresh, "mode": ls_mode}
                notes  = f"round=C1 strategy_type=zscore_reversion coin={coin}"
                for trade in extract_trades(px, sig, coin, ls, params, notes):
                    logger.log(**trade)
            loggers[key] = logger

    return loggers


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND C2: Crypto-Specific Strategies
# ══════════════════════════════════════════════════════════════════════════════

def build_c2_loggers(prices_dict: Dict[str, Optional[pd.Series]],
                     ohlcv_dict:  Dict[str, Optional[pd.DataFrame]]) -> Dict[str, TradeLogger]:
    """
    Crypto-specific strategies.
    One TradeLogger per named strategy variant.
    Exact signal logic preserved from crypto_harness.py run_round_c2().
    """
    loggers: Dict[str, TradeLogger] = {}
    btc = prices_dict.get("BTC-USD")
    eth = prices_dict.get("ETH-USD")

    # 1. BTC Dominance Proxy ──────────────────────────────────────────────────
    if btc is not None and eth is not None:
        common = btc.index.intersection(eth.index)
        btc_c  = btc.reindex(common)
        eth_c  = eth.reindex(common)

        btc_ret = btc_c.pct_change(20)
        eth_ret = eth_c.pct_change(20)
        btc_dominant = btc_ret > eth_ret

        sig_btc_safe   = btc_dominant.astype(float).shift(1)
        sig_btc_dom    = (~btc_dominant).astype(float).shift(1)

        # BTC Dominance Safe (long BTC when dominant)
        key = "crypto_btc_dominance_safe"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        params = {"lookback": 20, "mode": "long_only", "variant": "dom_safe"}
        notes  = "round=C2 strategy_type=btc_dominance coin=BTC-USD"
        for trade in extract_trades(btc_c, sig_btc_safe, "BTC-USD", False, params, notes):
            logger.log(**trade)
        loggers[key] = logger

        # BTC Dominance Risk-On (long BTC when NOT dominant)
        key = "crypto_btc_dominance_riskon"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        params = {"lookback": 20, "mode": "long_only", "variant": "dom_riskon"}
        for label_suffix, sig in [("dom_riskon", sig_btc_dom)]:
            notes = f"round=C2 strategy_type=btc_dominance coin=BTC-USD"
            for trade in extract_trades(btc_c, sig, "BTC-USD", False, params, notes):
                logger.log(**trade)
        # Also test on alts (risk-on when ETH outperforms)
        for coin in ["ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD"]:
            alt_px = prices_dict.get(coin)
            if alt_px is None:
                continue
            common2 = btc_dominant.index.intersection(alt_px.index)
            sig_alt = (~btc_dominant.reindex(common2)).astype(float).shift(1)
            notes = f"round=C2 strategy_type=btc_dominance coin={coin}"
            params_alt = {"lookback": 20, "mode": "long_only", "variant": "dom_riskon"}
            for trade in extract_trades(alt_px.reindex(common2), sig_alt, coin,
                                        False, params_alt, notes):
                logger.log(**trade)
        loggers[key] = logger

    # 2. Weekend Effect ────────────────────────────────────────────────────────
    key = "crypto_weekend_effect"
    logger = TradeLogger(round_num=3, strategy=key, category="crypto")
    for coin, px in prices_dict.items():
        if px is None:
            continue
        dow = pd.Series(px.index.dayofweek, index=px.index)
        sig = (dow == 4).astype(float).shift(1)
        params = {"day_of_week": 4, "mode": "long_only"}
        notes  = f"round=C2 strategy_type=weekend_effect coin={coin}"
        for trade in extract_trades(px, sig, coin, False, params, notes):
            logger.log(**trade)
    loggers[key] = logger

    # 3. Volatility Breakout ───────────────────────────────────────────────────
    key = "crypto_vol_breakout"
    logger = TradeLogger(round_num=3, strategy=key, category="crypto")
    for coin, df in ohlcv_dict.items():
        if df is None or len(df) < 50:
            continue
        px = prices_dict.get(coin)
        if px is None:
            continue
        try:
            atr_vals     = atr(df, 14)
            rolling_high = df["High"].rolling(20).max()
            rolling_low  = df["Low"].rolling(20).min()
            close        = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            breakout_up = close > (rolling_high + 2 * atr_vals)
            breakout_dn = close < (rolling_low  - 2 * atr_vals)
            sig = pd.Series(0.0, index=close.index)
            sig[breakout_up] =  1.0
            sig[breakout_dn] = -1.0
            sig = sig.shift(1)
            params = {"atr_period": 14, "rolling_window": 20, "atr_mult": 2, "mode": "long_short"}
            notes  = f"round=C2 strategy_type=vol_breakout coin={coin}"
            for trade in extract_trades(px, sig, coin, True, params, notes):
                logger.log(**trade)
        except Exception:
            pass
    loggers[key] = logger

    # 4. Hash Ribbon Proxy (BTC only) ─────────────────────────────────────────
    if btc is not None:
        key = "crypto_hash_ribbon"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        sma30 = sma(btc, 30)
        sma60 = sma(btc, 60)
        was_below  = (sma30 < sma60).rolling(5).sum() >= 3
        cross_up   = (sma30 > sma60) & (sma30.shift(1) <= sma60.shift(1))
        sig = pd.Series(0.0, index=btc.index)
        position = 0
        sig_vals = []
        for i in range(len(btc)):
            if cross_up.iloc[i] and was_below.iloc[i]:
                position = 1
            elif sma30.iloc[i] < sma60.iloc[i] * 0.99:
                position = 0
            sig_vals.append(position)
        sig = pd.Series(sig_vals, index=btc.index).shift(1)
        params = {"sma_short": 30, "sma_long": 60, "was_below_window": 5, "mode": "long_only"}
        notes  = "round=C2 strategy_type=hash_ribbon coin=BTC-USD"
        for trade in extract_trades(btc, sig, "BTC-USD", False, params, notes):
            logger.log(**trade)
        loggers[key] = logger

    # 5. Fear Capitulation Signal ─────────────────────────────────────────────
    key = "crypto_fear_capitulation"
    logger = TradeLogger(round_num=3, strategy=key, category="crypto")
    for coin, px in prices_dict.items():
        if px is None:
            continue
        ret7    = px.pct_change(7)
        raw_sig = (ret7 < -0.20).astype(float)
        sig_filled = pd.Series(0.0, index=px.index)
        last_signal = -999
        for i, (idx, v) in enumerate(raw_sig.items()):
            if v == 1.0:
                last_signal = i
            if i - last_signal <= 14:
                sig_filled.iloc[i] = 1.0
        sig_filled = sig_filled.shift(1)
        params = {"ret_window": 7, "threshold": -0.20, "hold_bars": 14, "mode": "long_only"}
        notes  = f"round=C2 strategy_type=fear_signal coin={coin}"
        for trade in extract_trades(px, sig_filled, coin, False, params, notes):
            logger.log(**trade)
    loggers[key] = logger

    return loggers


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND C3: Cross-Asset Crypto Signals
# ══════════════════════════════════════════════════════════════════════════════

def build_c3_loggers(prices_dict:  Dict[str, Optional[pd.Series]],
                     extra_prices: Dict[str, Optional[pd.Series]]) -> Dict[str, TradeLogger]:
    """
    Cross-asset crypto signals.
    One TradeLogger per named strategy variant.
    Exact signal logic preserved from crypto_harness.py run_round_c3().
    """
    loggers: Dict[str, TradeLogger] = {}
    btc  = prices_dict.get("BTC-USD")
    vix  = extra_prices.get("^VIX")
    usd  = extra_prices.get("DX-Y.NYB")
    gold = extra_prices.get("GLD")

    # 1. BTC Leads Alts ────────────────────────────────────────────────────────
    if btc is not None:
        key = "crypto_btc_leads_alts"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        btc_mom5 = btc.pct_change(5)
        sig_base = (btc_mom5 > 0).astype(float) * 2 - 1

        alt_coins = ["ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "LINK-USD"]
        for coin in alt_coins:
            px = prices_dict.get(coin)
            if px is None:
                continue
            common = sig_base.index.intersection(px.index)
            # Lag 1 extra shift for 1-day lag (as in crypto_harness.py)
            sig = sig_base.reindex(common).shift(1)
            params = {"btc_mom_window": 5, "lag_days": 1, "mode": "long_only"}
            notes  = f"round=C3 strategy_type=btc_leads_alts coin={coin}"
            for trade in extract_trades(px.reindex(common), sig, coin,
                                        False, params, notes):
                logger.log(**trade)
        loggers[key] = logger

    # 2. Gold/BTC Correlation ─────────────────────────────────────────────────
    if gold is not None and btc is not None:
        key = "crypto_gold_btc"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        gold_ret10 = gold.pct_change(10)
        common = gold_ret10.index.intersection(btc.index)
        sig = (gold_ret10.reindex(common) > 0.02).astype(float).shift(1)
        params = {"gold_ret_window": 10, "threshold": 0.02, "mode": "long_only"}
        notes  = "round=C3 strategy_type=gold_btc coin=BTC-USD"
        for trade in extract_trades(btc.reindex(common), sig, "BTC-USD",
                                    False, params, notes):
            logger.log(**trade)
        loggers[key] = logger

    # 3. Dollar Inverse ────────────────────────────────────────────────────────
    if usd is not None:
        usd_ret5   = usd.pct_change(5)
        # long_only variant
        key_lo = "crypto_dollar_inverse_long_only"
        logger_lo = TradeLogger(round_num=3, strategy=key_lo, category="crypto")
        sig_lo = (usd_ret5 < 0).astype(float).shift(1)
        # long_short variant
        key_ls = "crypto_dollar_inverse_long_short"
        logger_ls = TradeLogger(round_num=3, strategy=key_ls, category="crypto")
        sig_ls = ((usd_ret5 < 0).astype(float) * 2 - 1).shift(1)

        for coin, px in prices_dict.items():
            if px is None:
                continue
            params_lo = {"usd_ret_window": 5, "mode": "long_only"}
            params_ls = {"usd_ret_window": 5, "mode": "long_short"}
            notes_lo  = f"round=C3 strategy_type=dollar_inverse coin={coin}"
            notes_ls  = f"round=C3 strategy_type=dollar_inverse coin={coin}"

            common = sig_lo.index.intersection(px.index)
            for trade in extract_trades(px.reindex(common),
                                        sig_lo.reindex(common), coin,
                                        False, params_lo, notes_lo):
                logger_lo.log(**trade)

            common2 = sig_ls.index.intersection(px.index)
            for trade in extract_trades(px.reindex(common2),
                                        sig_ls.reindex(common2), coin,
                                        True, params_ls, notes_ls):
                logger_ls.log(**trade)

        loggers[key_lo] = logger_lo
        loggers[key_ls] = logger_ls

    # 4. VIX-Filtered Momentum ─────────────────────────────────────────────────
    if vix is not None:
        key = "crypto_vix_filtered_momentum"
        logger = TradeLogger(round_num=3, strategy=key, category="crypto")
        vix_low = vix < 25

        for coin, px in prices_dict.items():
            if px is None:
                continue
            mom20    = px.pct_change(20)
            base_sig = (mom20 > 0).astype(float)
            common   = base_sig.index.intersection(vix_low.index)
            filtered_sig = (base_sig.reindex(common) * vix_low.reindex(common)).shift(1)
            params = {"mom_window": 20, "vix_threshold": 25, "mode": "long_only"}
            notes  = f"round=C3 strategy_type=vix_filtered coin={coin}"
            for trade in extract_trades(px.reindex(common), filtered_sig, coin,
                                        False, params, notes):
                logger.log(**trade)
        loggers[key] = logger

    return loggers


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 70)
    print("CRYPTO V2 — Trade Logger (Framework Edition)")
    print(f"Period: {START_DATE} to present  |  Universe: {', '.join(CRYPTO_UNIVERSE)}")
    print("=" * 70)

    # Fetch all data
    print("\n  Loading price data...")
    prices_dict, ohlcv_dict, extra_prices = load_prices()

    valid_coins = [c for c, px in prices_dict.items() if px is not None]
    if not valid_coins:
        print("ERROR: No crypto data loaded. Check network / yfinance.")
        sys.exit(1)
    print(f"\n  Loaded {len(valid_coins)}/{len(CRYPTO_UNIVERSE)} coins, "
          f"{sum(1 for v in extra_prices.values() if v is not None)}/{len(EXTRA_TICKERS)} extras")

    all_loggers: Dict[str, TradeLogger] = {}

    # Round C1
    print("\n  --- Round C1: Baseline Momentum + Mean Reversion ---")
    c1_loggers = build_c1_loggers(prices_dict)
    all_loggers.update(c1_loggers)
    c1_trades = sum(len(lg) for lg in c1_loggers.values())
    print(f"    {len(c1_loggers)} strategy loggers, {c1_trades} trades")

    # Round C2
    print("\n  --- Round C2: Crypto-Specific Strategies ---")
    c2_loggers = build_c2_loggers(prices_dict, ohlcv_dict)
    all_loggers.update(c2_loggers)
    c2_trades = sum(len(lg) for lg in c2_loggers.values())
    print(f"    {len(c2_loggers)} strategy loggers, {c2_trades} trades")

    # Round C3
    print("\n  --- Round C3: Cross-Asset Signals ---")
    c3_loggers = build_c3_loggers(prices_dict, extra_prices)
    all_loggers.update(c3_loggers)
    c3_trades = sum(len(lg) for lg in c3_loggers.values())
    print(f"    {len(c3_loggers)} strategy loggers, {c3_trades} trades")

    # Save all loggers
    total_trades = sum(len(lg) for lg in all_loggers.values())
    print(f"\n  Saving {len(all_loggers)} strategy loggers ({total_trades} total trades)...")
    for key in sorted(all_loggers):
        logger = all_loggers[key]
        if len(logger) > 0:
            logger.save()
        else:
            print(f"  [TradeLogger] {key}: 0 trades — skipped")

    print("\n  Done.")


if __name__ == "__main__":
    main()
