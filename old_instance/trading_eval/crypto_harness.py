#!/usr/bin/env python3
"""
Crypto Trading Eval Harness — Karpathy Autoresearch Edition
============================================================
Tests cryptocurrency trading strategies across 3 rounds.

Universe: BTC-USD, ETH-USD, SOL-USD, BNB-USD, ADA-USD, AVAX-USD, LINK-USD, DOT-USD

Rounds:
  C1: Baseline momentum + mean reversion strategies
  C2: Crypto-specific strategies (dominance, weekend effect, hash ribbon, etc.)
  C3: Cross-asset crypto signals (BTC leads alts, gold/BTC, dollar inverse, VIX)

Usage:
  PYTHONPATH=/tmp/eval_deps python3 crypto_harness.py
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: PYTHONPATH=/tmp/eval_deps python3 crypto_harness.py")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

# ── Universe ──────────────────────────────────────────────────────────────────

CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD",
    "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD",
]

# Extra tickers needed for cross-asset signals
EXTRA_TICKERS = ["DX-Y.NYB", "^VIX", "GLD"]

START_DATE = "2018-01-01"
TRANSACTION_COST = 0.0005  # 5bp per trade

# ── Data Fetching ─────────────────────────────────────────────────────────────

def fetch_prices(ticker: str, start: str = START_DATE) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data with caching."""
    cache_file = CACHE_DIR / f"crypto_{ticker.replace('^', '_').replace('/', '_')}.pkl"

    # Use cache if less than 4 hours old
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 4 * 3600:
            with open(cache_file, "rb") as f:
                return pickle.load(f)

    try:
        df = yf.download(ticker, start=start, auto_adjust=True, progress=False)
        if df is None or len(df) < 100:
            return None
        # Strip timezone
        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        with open(cache_file, "wb") as f:
            pickle.dump(df, f)
        return df
    except Exception as e:
        print(f"  Warning: could not fetch {ticker}: {e}")
        return None


def get_close(ticker: str, start: str = START_DATE) -> Optional[pd.Series]:
    """Return close price series."""
    df = fetch_prices(ticker, start)
    if df is None:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        try:
            return df["Close"][ticker].dropna()
        except Exception:
            return df["Close"].iloc[:, 0].dropna()
    return df["Close"].dropna()


def get_ohlcv(ticker: str, start: str = START_DATE) -> Optional[pd.DataFrame]:
    """Return OHLCV dataframe with single-level columns."""
    df = fetch_prices(ticker, start)
    if df is None:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df = df.droplevel(1, axis=1)
    return df

# ── Backtest Engine ───────────────────────────────────────────────────────────

def backtest(
    signal: pd.Series,
    prices: pd.Series,
    long_short: bool = False,
    label: str = "",
) -> Dict:
    """
    Core backtest engine.
    signal: daily signal (+1 long, -1 short, 0 flat) — already shifted to avoid lookahead
    prices: daily close prices
    long_short: if False, treats negative signals as 0 (long-only)
    """
    # Align
    common = signal.index.intersection(prices.index)
    if len(common) < 50:
        return {}

    sig = signal.reindex(common).fillna(0)
    px  = prices.reindex(common)

    # Compute daily returns
    daily_ret = px.pct_change().fillna(0)

    # Position: use signal as position
    pos = sig.copy()
    if not long_short:
        pos = pos.clip(lower=0)

    # Detect trades (position changes)
    trades = (pos.diff().abs() > 0.01).sum()

    # Strategy returns
    strat_ret = pos.shift(1).fillna(0) * daily_ret
    # Apply transaction costs on position changes
    cost = pos.diff().abs().fillna(0) * TRANSACTION_COST
    strat_ret = strat_ret - cost

    if strat_ret.std() < 1e-10 or trades < 2:
        return {}

    # Metrics
    ann_factor = 365  # crypto trades every day
    sharpe = (strat_ret.mean() / strat_ret.std()) * math.sqrt(ann_factor)
    n_years = len(strat_ret) / ann_factor
    total_ret = (1 + strat_ret).prod() - 1
    cagr = (1 + total_ret) ** (1 / max(n_years, 0.1)) - 1

    # Max drawdown
    cum = (1 + strat_ret).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    # Win rate (only on trading days)
    active = strat_ret[pos.shift(1).abs() > 0.01]
    win_rate = (active > 0).sum() / max(len(active), 1)

    return {
        "label": label,
        "sharpe": round(float(sharpe), 3),
        "cagr": round(float(cagr * 100), 2),
        "max_dd": round(float(max_dd * 100), 2),
        "win_rate": round(float(win_rate * 100), 1),
        "n_trades": int(trades),
        "n_days": len(strat_ret),
    }

# ── Technical Indicators ──────────────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(period).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0)
    dn = (-delta).clip(lower=0)
    rs = up.rolling(period).mean() / dn.rolling(period).mean().replace(0, np.nan)
    return 100 - 100 / (1 + rs)

def bollinger(series: pd.Series, period: int = 20, std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(series, period)
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

# ── Round C1: Baseline Strategies ────────────────────────────────────────────

def run_round_c1(prices_dict: Dict[str, pd.Series]) -> List[Dict]:
    """Momentum and mean reversion baselines."""
    results = []
    total = 0

    # Count total strategies
    coins = list(prices_dict.keys())
    sma_pairs = [(5, 20), (10, 50), (20, 100), (50, 200)]
    mom_periods = [5, 10, 20, 60]
    rsi_bands = [(25, 75), (20, 80)]
    boll_stds = [1.5, 2.0]
    zscore_thresholds = [1.5, 2.0]
    modes = ["long_only", "long_short"]

    n_strategies = len(coins) * (
        len(sma_pairs) + len(mom_periods) + 2 * len(rsi_bands) +
        2 * len(boll_stds) + 2 * len(zscore_thresholds)
    ) * len(modes)

    done = 0
    milestone = max(1, n_strategies // 5)

    for coin in coins:
        px = prices_dict[coin]
        if px is None or len(px) < 200:
            continue

        for ls_mode in modes:
            ls = ls_mode == "long_short"

            # SMA Crossovers
            for fast, slow in sma_pairs:
                fast_sma = sma(px, fast)
                slow_sma = sma(px, slow)
                sig = (fast_sma > slow_sma).astype(float) * 2 - 1  # +1/-1
                sig = sig.shift(1)
                r = backtest(sig, px, long_short=ls, label=f"SMA_{fast}/{slow}_{coin}_{ls_mode}")
                if r:
                    r["round"] = "C1"
                    r["coin"] = coin
                    r["strategy_type"] = "sma_crossover"
                    r["mode"] = ls_mode
                    results.append(r)
                done += 1
                if done % milestone == 0:
                    pct = int(100 * done / n_strategies)
                    print(f"  [C1] {pct}% complete ({done}/{n_strategies})")

            # Momentum
            for period in mom_periods:
                mom_sig = px.pct_change(period)
                sig = (mom_sig > 0).astype(float) * 2 - 1
                sig = sig.shift(1)
                r = backtest(sig, px, long_short=ls, label=f"MOM_{period}d_{coin}_{ls_mode}")
                if r:
                    r["round"] = "C1"
                    r["coin"] = coin
                    r["strategy_type"] = "momentum"
                    r["mode"] = ls_mode
                    results.append(r)
                done += 1
                if done % milestone == 0:
                    pct = int(100 * done / n_strategies)
                    print(f"  [C1] {pct}% complete ({done}/{n_strategies})")

            # RSI Mean Reversion
            rsi_vals = rsi(px, 14)
            for lo_band, hi_band in rsi_bands:
                sig = pd.Series(0.0, index=px.index)
                sig[rsi_vals < lo_band] = 1.0   # oversold → long
                sig[rsi_vals > hi_band] = -1.0  # overbought → short
                # Carry signal forward until crossing midline
                sig = sig.replace(0, np.nan).ffill().fillna(0)
                # Reset at midline
                mid_cross = (rsi_vals > 50) & (sig < 0) | (rsi_vals < 50) & (sig > 0)
                sig[mid_cross] = 0
                sig = sig.shift(1)
                r = backtest(sig, px, long_short=ls, label=f"RSI_{lo_band}/{hi_band}_{coin}_{ls_mode}")
                if r:
                    r["round"] = "C1"
                    r["coin"] = coin
                    r["strategy_type"] = "rsi_reversion"
                    r["mode"] = ls_mode
                    results.append(r)
                done += 1
                if done % milestone == 0:
                    pct = int(100 * done / n_strategies)
                    print(f"  [C1] {pct}% complete ({done}/{n_strategies})")

            # Bollinger Reversion
            for std_mult in boll_stds:
                lower, mid, upper = bollinger(px, 20, std_mult)
                sig = pd.Series(0.0, index=px.index)
                sig[px < lower] = 1.0   # below lower band → long
                sig[px > upper] = -1.0  # above upper band → short
                sig[px.between(lower * 0.99, upper * 1.01)] = 0
                sig = sig.shift(1)
                r = backtest(sig, px, long_short=ls, label=f"BOLL_{std_mult}std_{coin}_{ls_mode}")
                if r:
                    r["round"] = "C1"
                    r["coin"] = coin
                    r["strategy_type"] = "bollinger_reversion"
                    r["mode"] = ls_mode
                    results.append(r)
                done += 1
                if done % milestone == 0:
                    pct = int(100 * done / n_strategies)
                    print(f"  [C1] {pct}% complete ({done}/{n_strategies})")

            # Z-score Mean Reversion
            for thresh in zscore_thresholds:
                zs = zscore(px, 20)
                sig = pd.Series(0.0, index=px.index)
                sig[zs < -thresh] = 1.0   # deeply oversold → long
                sig[zs > thresh] = -1.0   # deeply overbought → short
                sig[zs.abs() < 0.5] = 0   # flat near mean
                sig = sig.shift(1)
                r = backtest(sig, px, long_short=ls, label=f"ZSCORE_{thresh}_{coin}_{ls_mode}")
                if r:
                    r["round"] = "C1"
                    r["coin"] = coin
                    r["strategy_type"] = "zscore_reversion"
                    r["mode"] = ls_mode
                    results.append(r)
                done += 1
                if done % milestone == 0:
                    pct = int(100 * done / n_strategies)
                    print(f"  [C1] {pct}% complete ({done}/{n_strategies})")

    print(f"  [C1] 100% complete — {len(results)} valid results")
    return results


# ── Round C2: Crypto-Specific Strategies ─────────────────────────────────────

def run_round_c2(prices_dict: Dict[str, pd.Series], ohlcv_dict: Dict[str, pd.DataFrame]) -> List[Dict]:
    """Crypto-specific strategies."""
    results = []
    btc = prices_dict.get("BTC-USD")
    eth = prices_dict.get("ETH-USD")

    if btc is None or eth is None:
        print("  [C2] Warning: BTC or ETH data missing, skipping some strategies")

    total_strategies = 0
    done = 0

    # Count: dominance(8 alt coins) + weekend(8) + vol_breakout(8) + hash_ribbon(1) + fear(8)
    n_strats = 6 + 8 + 8 + 1 + 8  # approx
    milestone = max(1, n_strats // 5)

    # 1. BTC Dominance Proxy: BTC vs ETH relative strength
    if btc is not None and eth is not None:
        common = btc.index.intersection(eth.index)
        btc_c = btc.reindex(common)
        eth_c = eth.reindex(common)

        # Rolling 20-day relative performance
        btc_ret = btc_c.pct_change(20)
        eth_ret = eth_c.pct_change(20)
        btc_dominant = btc_ret > eth_ret  # BTC outperforms → altcoin season ending → defensive

        # Defensive: long BTC; Risk-on: long alts
        # Test on BTC itself (long when NOT dominant, i.e., altcoin season)
        sig_btc_dom = (~btc_dominant).astype(float).shift(1)  # long BTC when not dominant? Actually: when ETH outperforms → risk-on for alts
        # When BTC dominant → long BTC only
        sig_btc_safe = btc_dominant.astype(float).shift(1)

        for label_suffix, sig in [("dom_safe", sig_btc_safe), ("dom_riskon", sig_btc_dom)]:
            r = backtest(sig, btc_c, long_short=False, label=f"BTC_DOM_{label_suffix}_BTC-USD_long_only")
            if r:
                r["round"] = "C2"
                r["coin"] = "BTC-USD"
                r["strategy_type"] = "btc_dominance"
                r["mode"] = "long_only"
                results.append(r)
            done += 1

        # Test dominance signal on alts (risk-on when ETH outperforms)
        for coin in ["ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD"]:
            alt_px = prices_dict.get(coin)
            if alt_px is None:
                continue
            common2 = btc_dominant.index.intersection(alt_px.index)
            sig_alt = (~btc_dominant.reindex(common2)).astype(float).shift(1)
            r = backtest(sig_alt, alt_px.reindex(common2), long_short=False,
                         label=f"BTC_DOM_riskon_{coin}_long_only")
            if r:
                r["round"] = "C2"
                r["coin"] = coin
                r["strategy_type"] = "btc_dominance"
                r["mode"] = "long_only"
                results.append(r)
            done += 1
            if done % milestone == 0:
                pct = min(99, int(100 * done / n_strats))
                print(f"  [C2] {pct}% complete")

    # 2. Weekend Effect: Friday close → Monday open bias
    # Since we have daily closes, proxy: buy Thursday close, sell Monday close
    for coin, px in prices_dict.items():
        if px is None:
            continue
        dow = pd.Series(px.index.dayofweek, index=px.index)
        # Signal: long on Friday (day=4), flat otherwise
        # (capturing any weekend drift)
        sig = (dow == 4).astype(float).shift(1)
        r = backtest(sig, px, long_short=False, label=f"WEEKEND_{coin}_long_only")
        if r:
            r["round"] = "C2"
            r["coin"] = coin
            r["strategy_type"] = "weekend_effect"
            r["mode"] = "long_only"
            results.append(r)
        done += 1
        if done % milestone == 0:
            pct = min(99, int(100 * done / n_strats))
            print(f"  [C2] {pct}% complete")

    # 3. Volatility Breakout: ATR(14) channel
    for coin, df in ohlcv_dict.items():
        if df is None or len(df) < 50:
            continue
        px = prices_dict.get(coin)
        if px is None:
            continue
        try:
            atr_vals = atr(df, 14)
            rolling_high = df["High"].rolling(20).max()
            rolling_low  = df["Low"].rolling(20).min()
            close = df["Close"]
            # Enter long when price breaks 2xATR above 20d high
            breakout_up = close > (rolling_high + 2 * atr_vals)
            # Enter short when price breaks 2xATR below 20d low
            breakout_dn = close < (rolling_low  - 2 * atr_vals)
            sig = pd.Series(0.0, index=close.index)
            sig[breakout_up] = 1.0
            sig[breakout_dn] = -1.0
            sig = sig.shift(1)
            r = backtest(sig, px, long_short=True, label=f"VOL_BREAKOUT_{coin}_long_short")
            if r:
                r["round"] = "C2"
                r["coin"] = coin
                r["strategy_type"] = "vol_breakout"
                r["mode"] = "long_short"
                results.append(r)
        except Exception as e:
            pass
        done += 1
        if done % milestone == 0:
            pct = min(99, int(100 * done / n_strats))
            print(f"  [C2] {pct}% complete")

    # 4. Hash Ribbon Proxy (BTC only): 30d vs 60d SMA crossover after being below
    if btc is not None:
        sma30 = sma(btc, 30)
        sma60 = sma(btc, 60)
        was_below = (sma30 < sma60).rolling(5).sum() >= 3  # recently below
        cross_up   = (sma30 > sma60) & (sma30.shift(1) <= sma60.shift(1))
        # Long when crossing up from below (miner capitulation recovery)
        sig = pd.Series(0.0, index=btc.index)
        # Carry signal: enter on cross from below, exit when 30d goes below 60d again
        position = 0
        sig_vals = []
        for i in range(len(btc)):
            if cross_up.iloc[i] and was_below.iloc[i]:
                position = 1
            elif sma30.iloc[i] < sma60.iloc[i] * 0.99:  # clearly below
                position = 0
            sig_vals.append(position)
        sig = pd.Series(sig_vals, index=btc.index).shift(1)
        r = backtest(sig, btc, long_short=False, label="HASH_RIBBON_BTC-USD_long_only")
        if r:
            r["round"] = "C2"
            r["coin"] = "BTC-USD"
            r["strategy_type"] = "hash_ribbon"
            r["mode"] = "long_only"
            results.append(r)
        done += 1

    # 5. Fear Signal: 7-day return < -20% → strong buy (capitulation)
    for coin, px in prices_dict.items():
        if px is None:
            continue
        ret7 = px.pct_change(7)
        sig = (ret7 < -0.20).astype(float)
        # Carry: stay long for 14 days after signal
        # Simple approach: use forward fill for 14 bars
        raw_sig = sig.copy()
        sig_filled = pd.Series(0.0, index=px.index)
        last_signal = -999
        for i, (idx, v) in enumerate(raw_sig.items()):
            if v == 1.0:
                last_signal = i
            if i - last_signal <= 14:
                sig_filled.iloc[i] = 1.0
        sig_filled = sig_filled.shift(1)
        r = backtest(sig_filled, px, long_short=False, label=f"FEAR_CAPITULATION_{coin}_long_only")
        if r:
            r["round"] = "C2"
            r["coin"] = coin
            r["strategy_type"] = "fear_signal"
            r["mode"] = "long_only"
            results.append(r)
        done += 1
        if done % milestone == 0:
            pct = min(99, int(100 * done / n_strats))
            print(f"  [C2] {pct}% complete")

    print(f"  [C2] 100% complete — {len(results)} valid results")
    return results


# ── Round C3: Cross-Asset Crypto Signals ─────────────────────────────────────

def run_round_c3(prices_dict: Dict[str, pd.Series], extra_prices: Dict[str, pd.Series]) -> List[Dict]:
    """Cross-asset crypto signals."""
    results = []
    btc = prices_dict.get("BTC-USD")
    vix = extra_prices.get("^VIX")
    usd = extra_prices.get("DX-Y.NYB")
    gold = extra_prices.get("GLD")

    done = 0
    n_strats = 5 + 1 + 8 + 8  # rough count
    milestone = max(1, n_strats // 5)

    # 1. BTC Leads Alts: Use BTC 5d momentum as signal for alts (1-day lag)
    if btc is not None:
        btc_mom5 = btc.pct_change(5)
        # Signal: long alts when BTC momentum > 0, flat/short when < 0
        sig_base = (btc_mom5 > 0).astype(float) * 2 - 1

        alt_coins = ["ETH-USD", "SOL-USD", "ADA-USD", "AVAX-USD", "LINK-USD"]
        for coin in alt_coins:
            px = prices_dict.get(coin)
            if px is None:
                continue
            common = sig_base.index.intersection(px.index)
            # Lag 1: BTC signal from yesterday drives today's alt position
            sig = sig_base.reindex(common).shift(1)  # extra shift for 1-day lag
            r = backtest(sig, px.reindex(common), long_short=False,
                         label=f"BTC_LEADS_{coin}_long_only")
            if r:
                r["round"] = "C3"
                r["coin"] = coin
                r["strategy_type"] = "btc_leads_alts"
                r["mode"] = "long_only"
                results.append(r)
            done += 1
            if done % milestone == 0:
                pct = min(99, int(100 * done / n_strats))
                print(f"  [C3] {pct}% complete")

    # 2. Gold/BTC Correlation: When gold up >2% in 10d, go long BTC
    if gold is not None and btc is not None:
        gold_ret10 = gold.pct_change(10)
        common = gold_ret10.index.intersection(btc.index)
        sig = (gold_ret10.reindex(common) > 0.02).astype(float).shift(1)
        r = backtest(sig, btc.reindex(common), long_short=False,
                     label="GOLD_BTC_signal_BTC-USD_long_only")
        if r:
            r["round"] = "C3"
            r["coin"] = "BTC-USD"
            r["strategy_type"] = "gold_btc"
            r["mode"] = "long_only"
            results.append(r)
        done += 1

    # 3. Dollar Inverse: When USD falling, long crypto; rising = flat
    if usd is not None:
        usd_ret5 = usd.pct_change(5)
        # Falling USD → long crypto
        sig_usd = (usd_ret5 < 0).astype(float).shift(1)
        # Long/short: falling USD = +1, rising = -1
        sig_usd_ls = ((usd_ret5 < 0).astype(float) * 2 - 1).shift(1)

        for coin, px in prices_dict.items():
            if px is None:
                continue
            for label_sfx, sig, ls in [
                ("long_only", sig_usd, False),
                ("long_short", sig_usd_ls, True),
            ]:
                common = sig.index.intersection(px.index)
                r = backtest(sig.reindex(common), px.reindex(common),
                             long_short=ls,
                             label=f"USD_INVERSE_{coin}_{label_sfx}")
                if r:
                    r["round"] = "C3"
                    r["coin"] = coin
                    r["strategy_type"] = "dollar_inverse"
                    r["mode"] = label_sfx
                    results.append(r)
            done += 1
            if done % milestone == 0:
                pct = min(99, int(100 * done / n_strats))
                print(f"  [C3] {pct}% complete")

    # 4. Macro Regime Overlay: Only take long signals when VIX < 25
    # Combine with momentum signals filtered by VIX
    if vix is not None:
        vix_low = vix < 25  # calm regime → crypto friendly

        for coin, px in prices_dict.items():
            if px is None:
                continue
            # Base signal: 20d momentum
            mom20 = px.pct_change(20)
            base_sig = (mom20 > 0).astype(float)

            common = base_sig.index.intersection(vix_low.index)
            # Only long when momentum positive AND VIX < 25
            filtered_sig = (base_sig.reindex(common) * vix_low.reindex(common)).shift(1)

            r = backtest(filtered_sig, px.reindex(common), long_short=False,
                         label=f"VIX_FILTERED_MOM_{coin}_long_only")
            if r:
                r["round"] = "C3"
                r["coin"] = coin
                r["strategy_type"] = "vix_filtered"
                r["mode"] = "long_only"
                results.append(r)
            done += 1
            if done % milestone == 0:
                pct = min(99, int(100 * done / n_strats))
                print(f"  [C3] {pct}% complete")

    print(f"  [C3] 100% complete — {len(results)} valid results")
    return results


# ── Ranking & Reporting ───────────────────────────────────────────────────────

def coin_ranking(results: List[Dict]) -> Dict[str, float]:
    """Average Sharpe ratio per coin."""
    from collections import defaultdict
    coin_sharpes = defaultdict(list)
    for r in results:
        if "sharpe" in r and "coin" in r:
            coin_sharpes[r["coin"]].append(r["sharpe"])
    return {
        coin: round(float(np.mean(sharpes)), 3)
        for coin, sharpes in sorted(
            coin_sharpes.items(),
            key=lambda x: np.mean(x[1]),
            reverse=True
        )
    }


def round_summary(results: List[Dict]) -> Dict:
    """Per-round summary stats."""
    from collections import defaultdict
    by_round = defaultdict(list)
    for r in results:
        by_round[r.get("round", "?")].append(r["sharpe"])
    return {
        rnd: {
            "n_strategies": len(sharpes),
            "avg_sharpe": round(float(np.mean(sharpes)), 3),
            "max_sharpe": round(float(max(sharpes)), 3),
            "pct_positive": round(100 * sum(s > 0 for s in sharpes) / len(sharpes), 1),
        }
        for rnd, sharpes in sorted(by_round.items())
    }


def print_table(results: List[Dict], top_n: int = 15):
    """Print clean results table."""
    sorted_results = sorted(results, key=lambda x: x.get("sharpe", -99), reverse=True)
    top = sorted_results[:top_n]

    header = f"{'#':<4} {'Label':<52} {'Sharpe':>7} {'CAGR%':>7} {'MaxDD%':>8} {'WinRate%':>9} {'Trades':>7}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(top, 1):
        label = r.get("label", "")[:51]
        print(
            f"{i:<4} {label:<52} {r.get('sharpe', 0):>7.3f} "
            f"{r.get('cagr', 0):>7.2f} {r.get('max_dd', 0):>8.2f} "
            f"{r.get('win_rate', 0):>9.1f} {r.get('n_trades', 0):>7}"
        )


def print_coin_ranking(ranking: Dict[str, float]):
    print(f"\n{'Coin':<12} {'Avg Sharpe':>12}")
    print("-" * 26)
    for coin, sharpe in ranking.items():
        bar = "█" * max(0, int(sharpe * 5))
        print(f"{coin:<12} {sharpe:>12.3f}  {bar}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("CRYPTO TRADING BACKTEST HARNESS — Karpathy Autoresearch")
    print("=" * 70)
    print(f"Period: {START_DATE} to present | Transaction cost: {TRANSACTION_COST*10000:.0f}bp")
    print(f"Universe: {', '.join(CRYPTO_UNIVERSE)}")
    print()

    # Fetch all data
    print("Fetching price data...")
    prices_dict: Dict[str, Optional[pd.Series]] = {}
    ohlcv_dict: Dict[str, Optional[pd.DataFrame]] = {}

    for ticker in CRYPTO_UNIVERSE:
        print(f"  {ticker}...", end=" ", flush=True)
        px = get_close(ticker)
        df = get_ohlcv(ticker)
        if px is not None:
            print(f"{len(px)} days")
        else:
            print("FAILED")
        prices_dict[ticker] = px
        ohlcv_dict[ticker] = df

    print("\nFetching extra tickers (VIX, USD, Gold)...")
    extra_prices: Dict[str, Optional[pd.Series]] = {}
    for ticker in EXTRA_TICKERS:
        print(f"  {ticker}...", end=" ", flush=True)
        px = get_close(ticker)
        if px is not None:
            print(f"{len(px)} days")
        else:
            print("FAILED")
        extra_prices[ticker] = px

    print()

    all_results = []

    # Round C1
    print("=" * 70)
    print("ROUND C1: Baseline Momentum + Mean Reversion")
    print("=" * 70)
    c1 = run_round_c1(prices_dict)
    all_results.extend(c1)
    print(f"  Round C1: {len(c1)} valid strategies")

    # Round C2
    print("\n" + "=" * 70)
    print("ROUND C2: Crypto-Specific Strategies")
    print("=" * 70)
    c2 = run_round_c2(prices_dict, ohlcv_dict)
    all_results.extend(c2)
    print(f"  Round C2: {len(c2)} valid strategies")

    # Round C3
    print("\n" + "=" * 70)
    print("ROUND C3: Cross-Asset Crypto Signals")
    print("=" * 70)
    c3 = run_round_c3(prices_dict, extra_prices)
    all_results.extend(c3)
    print(f"  Round C3: {len(c3)} valid strategies")

    if not all_results:
        print("ERROR: No valid results generated!")
        sys.exit(1)

    # Sort and analyze
    sorted_all = sorted(all_results, key=lambda x: x.get("sharpe", -99), reverse=True)
    top15 = sorted_all[:15]
    ranking = coin_ranking(all_results)
    summaries = round_summary(all_results)
    champion = sorted_all[0] if sorted_all else {}

    # Print results
    print("\n" + "=" * 70)
    print("TOP 15 STRATEGIES (by Sharpe Ratio)")
    print("=" * 70)
    print_table(all_results, top_n=15)

    print("\n" + "=" * 70)
    print("COIN RANKING (avg Sharpe)")
    print("=" * 70)
    print_coin_ranking(ranking)

    print("\n" + "=" * 70)
    print("ROUND SUMMARIES")
    print("=" * 70)
    for rnd, stats in summaries.items():
        print(f"  {rnd}: {stats['n_strategies']} strategies | "
              f"Avg Sharpe: {stats['avg_sharpe']:.3f} | "
              f"Max Sharpe: {stats['max_sharpe']:.3f} | "
              f"{stats['pct_positive']:.0f}% positive")

    print("\n" + "=" * 70)
    print("CHAMPION STRATEGY")
    print("=" * 70)
    print(f"  Label:     {champion.get('label', 'N/A')}")
    print(f"  Round:     {champion.get('round', 'N/A')}")
    print(f"  Sharpe:    {champion.get('sharpe', 0):.3f}")
    print(f"  CAGR:      {champion.get('cagr', 0):.2f}%")
    print(f"  Max DD:    {champion.get('max_dd', 0):.2f}%")
    print(f"  Win Rate:  {champion.get('win_rate', 0):.1f}%")
    print(f"  N Trades:  {champion.get('n_trades', 0)}")

    # Save results
    output = {
        "timestamp": datetime.utcnow().isoformat(),
        "top15": top15,
        "coin_ranking": ranking,
        "champion": champion,
        "round_summaries": summaries,
        "total_strategies_tested": len(all_results),
    }

    out_path = ROUNDS_DIR / "crypto_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\nResults saved to: {out_path}")
    print("=" * 70)
    print("BACKTEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
