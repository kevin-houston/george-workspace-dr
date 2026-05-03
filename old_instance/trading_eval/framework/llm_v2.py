#!/usr/bin/env python3
"""
llm_v2.py — LLM Signal Interpretation Harness v2 (TradeLogger)
===============================================================
Converts llm_signal_harness.py (Round 26) into per-trade TradeLogger records.

- round_num=26, category='llm_signal'
- One TradeLogger per strategy variant:
    * pead_unfiltered     — all PEAD gap signals (baseline)
    * pead_llm_confirmed  — signals where LLM confidence > 60 and direction = 'bullish'
    * pead_llm_rejected   — signals rejected by LLM (confidence < 40 or direction = 'bearish')
    * pairs_unfiltered    — all pairs mean-reversion signals
    * pairs_llm_confirmed — signals where LLM confidence > 60
- Extra fields per trade:
    llm_confirmed (bool), llm_score, signal_type, direction, reasoning
- Preserves EXACT strategy logic from llm_signal_harness.py

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/llm_v2.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, '/workspace/group/trading_eval/framework')
sys.path.insert(0, '/workspace/group/trading_eval')

import json
import random
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

warnings.filterwarnings('ignore')

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f'Missing: {e}. Run: /workspace/group/venv/bin/pip install yfinance pandas numpy')
    sys.exit(1)

from base_harness import TradeLogger, fetch_data, get_close

# ── Config (exact from llm_signal_harness.py) ─────────────────────────────────

UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'COST',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'NFLX', 'ADBE', 'QCOM', 'TXN', 'HON',
    'GE', 'CAT', 'MMM', 'LMT', 'RTX',
]

TOP_PAIRS = [
    ('JNJ', 'UNH'),
    ('LMT', 'NOC'),
    ('CVX', 'COP'),
    ('BAC', 'GS'),
    ('COST', 'PG'),
]

START_DATE = '2020-01-01'
END_DATE   = '2025-01-01'

CACHE_DIR  = Path('/workspace/group/trading_eval/cache')
ROUNDS_DIR = Path('/workspace/group/trading_eval/rounds')
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

PEAD_GAP_THRESHOLD = 0.03
PEAD_HOLD_DAYS     = 20
PAIRS_ZSCORE_ENTRY = 1.5
SAMPLE_PEAD        = 100
SAMPLE_PAIRS       = 50

api_calls_made = 0
random.seed(42)
np.random.seed(42)


# ── Data fetching (exact from llm_signal_harness.py) ──────────────────────────

def _fetch_closes(tickers, start=START_DATE, end=END_DATE) -> pd.DataFrame:
    all_tickers = sorted(set(tickers))
    cache_key   = '_'.join(all_tickers[:5]) + f'_{start}_{end}'
    cache_path  = CACHE_DIR / f'llm_{cache_key[:60]}.pkl'

    if cache_path.exists():
        print(f'  [cache] Loading {cache_path.name}')
        return pd.read_pickle(cache_path)

    print(f'  [yfinance] Downloading {len(all_tickers)} tickers ...')
    try:
        raw = yf.download(all_tickers, start=start, end=end,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            closes = raw['Close']
        else:
            closes = raw[['Close']].rename(columns={'Close': all_tickers[0]})
        closes.dropna(how='all', inplace=True)
        closes.to_pickle(cache_path)
        return closes
    except Exception as e:
        print(f'  [error] Download failed: {e}')
        return pd.DataFrame()


def _fetch_volume(tickers, start=START_DATE, end=END_DATE) -> pd.DataFrame:
    all_tickers = sorted(set(tickers))
    cache_key   = '_'.join(all_tickers[:5]) + f'_vol_{start}_{end}'
    cache_path  = CACHE_DIR / f'llm_vol_{cache_key[:60]}.pkl'

    if cache_path.exists():
        return pd.read_pickle(cache_path)

    try:
        raw = yf.download(all_tickers, start=start, end=end,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            vol = raw['Volume']
        else:
            vol = raw[['Volume']].rename(columns={'Volume': all_tickers[0]})
        vol.dropna(how='all', inplace=True)
        vol.to_pickle(cache_path)
        return vol
    except Exception as e:
        print(f'  [error] Volume download failed: {e}')
        return pd.DataFrame()


# ── LLM Interface (exact from llm_signal_harness.py) ─────────────────────────

def call_claude(prompt: str, model: str = 'claude-haiku-4-5') -> str:
    global api_calls_made
    import subprocess
    try:
        result = subprocess.run(
            [
                'claude', '-p', prompt,
                '--model', model,
                '--setting-sources', 'user',
                '--system-prompt', 'You are a quantitative trading signal analyst. Respond only with valid JSON, no markdown fences.',
                '--tools', '',
            ],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            api_calls_made += 1
            return result.stdout.strip()
        else:
            err = (result.stderr or 'unknown error')[:200]
            print(f'  [API error] rc={result.returncode} {err}')
            return '{"confidence": 50, "direction": "neutral", "reasoning": "API error"}'
    except Exception as e:
        print(f'  [API error] {e}')
        return '{"confidence": 50, "direction": "neutral", "reasoning": "API error"}'


def call_claude_narrative(prompt: str, model: str = 'claude-haiku-4-5') -> str:
    import subprocess
    try:
        result = subprocess.run(
            [
                'claude', '-p', prompt,
                '--model', model,
                '--setting-sources', 'user',
                '--system-prompt', 'You are a financial analyst writing clear, concise trading signal narratives for retail investors.',
                '--tools', '',
            ],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return 'Narrative unavailable.'
    except Exception as e:
        return f'Narrative error: {e}'


def parse_llm_json(text: str) -> dict:
    try:
        start = text.find('{')
        end   = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {'confidence': 50, 'direction': 'neutral', 'reasoning': 'parse error'}


# ── Indicator helpers (exact from llm_signal_harness.py) ─────────────────────

def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    delta  = prices.diff().dropna()
    gains  = delta.clip(lower=0)
    losses = (-delta).clip(lower=0)
    avg_g  = gains.ewm(com=period - 1, adjust=False).mean()
    avg_l  = losses.ewm(com=period - 1, adjust=False).mean()
    rs     = avg_g / avg_l.replace(0, np.nan)
    rsi    = 100 - (100 / (1 + rs))
    return float(rsi.iloc[-1]) if len(rsi) > 0 else 50.0


def build_indicator_context(prices: pd.Series, volumes: pd.Series,
                             idx: int, symbol: str) -> dict:
    window = prices.iloc[max(0, idx - 40): idx + 1]
    if len(window) < 20:
        return {}

    price  = float(window.iloc[-1])
    sma20  = float(window.iloc[-20:].mean())
    above_below = 'above' if price > sma20 else 'below'
    pct    = abs(price - sma20) / sma20 * 100

    rsi = compute_rsi(window)

    rets = window.pct_change().dropna()
    vol  = float(rets.iloc[-20:].std() * np.sqrt(252) * 100) if len(rets) >= 20 else 20.0

    ret5d  = float((price / window.iloc[-6] - 1) * 100) if len(window) > 5 else 0.0
    ret20d = float((price / window.iloc[-21] - 1) * 100) if len(window) > 20 else 0.0

    vol_ratio = 1.0
    if volumes is not None and len(volumes) > 20:
        vol_window = volumes.iloc[max(0, idx - 20): idx + 1]
        if len(vol_window) >= 2:
            avg_vol   = float(vol_window.iloc[:-1].mean())
            today_vol = float(vol_window.iloc[-1])
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0

    return {
        'symbol':      symbol,
        'price':       price,
        'sma20':       sma20,
        'above_below': above_below,
        'pct':         pct,
        'rsi':         rsi,
        'vol':         vol,
        'ret5d':       ret5d,
        'ret20d':      ret20d,
        'vol_ratio':   vol_ratio,
    }


# ── Indicator Agent (exact from llm_signal_harness.py) ───────────────────────

INDICATOR_PROMPT = (
    'Rate {strategy} signal. '
    'Symbol: {symbol}. Trigger: {trigger_desc}. '
    'Price: ${price:.2f}. SMA20: ${sma20:.2f} (price {above_below} by {pct:.1f}%). '
    'RSI14: {rsi:.1f}. AnnVol: {vol:.1f}%. '
    '5d ret: {ret5d:+.1f}%. 20d ret: {ret20d:+.1f}%. VolRatio: {vol_ratio:.2f}x. '
    'Reply ONLY valid JSON: {{"confidence": <0-100>, "direction": "<bullish|bearish|neutral>", "reasoning": "<one sentence>"}}'
)


def call_indicator_agent(ctx: dict, strategy: str, trigger_desc: str) -> dict:
    if not ctx:
        return {'confidence': 50, 'direction': 'neutral', 'reasoning': 'no context'}
    prompt = INDICATOR_PROMPT.format(strategy=strategy, trigger_desc=trigger_desc, **ctx)
    raw    = call_claude(prompt)
    return parse_llm_json(raw)


# ── Test 1: PEAD (exact logic from llm_signal_harness.py) ─────────────────────

def run_test1_pead() -> dict:
    """
    Run PEAD gap test and log per-trade records to:
      - pead_unfiltered    (all signals)
      - pead_llm_confirmed (confidence > 60 and direction = bullish)
      - pead_llm_rejected  (confidence < 40 or direction = bearish)
    """
    print('\n=== TEST 1: LLM Filter on PEAD Signals ===')

    closes  = _fetch_closes(UNIVERSE)
    volumes = _fetch_volume(UNIVERSE)
    if closes.empty:
        return {}

    all_events = []
    for symbol in UNIVERSE:
        if symbol not in closes.columns:
            continue
        prices = closes[symbol].dropna()
        vols   = volumes[symbol].dropna() if symbol in volumes.columns else None

        if len(prices) < 60:
            continue

        gaps = prices.pct_change()

        for i in range(30, len(prices) - PEAD_HOLD_DAYS - 1):
            gap = float(gaps.iloc[i])
            if gap < PEAD_GAP_THRESHOLD:
                continue

            fwd_ret = float(prices.iloc[i + PEAD_HOLD_DAYS] / prices.iloc[i] - 1)

            vol_idx = None
            if vols is not None:
                price_date = prices.index[i]
                if price_date in vols.index:
                    vol_idx = vols.index.get_loc(price_date)

            all_events.append({
                'symbol':    symbol,
                'date':      prices.index[i],
                'price_idx': i,
                'gap_pct':   gap,
                'fwd_ret':   fwd_ret,
                'prices':    prices,
                'vols':      vols,
                'vol_idx':   vol_idx,
                'entry_price': float(prices.iloc[i]),
                'exit_price':  float(prices.iloc[i + PEAD_HOLD_DAYS]),
            })

    print(f'  Found {len(all_events)} raw gap events (gap > {PEAD_GAP_THRESHOLD:.0%})')

    if len(all_events) == 0:
        return {}

    sample = random.sample(all_events, min(SAMPLE_PEAD, len(all_events)))
    sample.sort(key=lambda x: x['date'])
    print(f'  Sampled {len(sample)} events for LLM evaluation ...')

    # TradeLoggers
    logger_unfilt = TradeLogger(round_num=26, strategy='pead_unfiltered',    category='llm_signal')
    logger_conf   = TradeLogger(round_num=26, strategy='pead_llm_confirmed',  category='llm_signal')
    logger_rej    = TradeLogger(round_num=26, strategy='pead_llm_rejected',   category='llm_signal')

    records = []
    for ev in sample:
        ctx = build_indicator_context(
            ev['prices'], ev['vols'], ev['price_idx'], ev['symbol']
        )
        trigger_desc = (
            f"Gap-up of {ev['gap_pct']:.1%} on {ev['date'].date()}, "
            f"potential post-earnings drift continuation"
        )
        resp = call_indicator_agent(ctx, 'PEAD gap-up', trigger_desc)
        time.sleep(0.3)

        confidence = resp.get('confidence', 50)
        direction  = resp.get('direction', 'neutral')
        reasoning  = resp.get('reasoning', '')

        llm_confirmed = confidence > 60 and direction == 'bullish'
        llm_rejected  = confidence < 40 or direction == 'bearish'

        entry_price = ev['entry_price']
        exit_price  = ev['exit_price']
        ret_pct     = (exit_price / entry_price - 1) * 100 if entry_price > 0 else 0.0

        base_fields = dict(
            ticker      = ev['symbol'],
            entry_date  = ev['date'],
            exit_date   = ev['date'] + pd.Timedelta(days=PEAD_HOLD_DAYS),
            return_pct  = float(ret_pct),
            hold_days   = PEAD_HOLD_DAYS,
            direction   = 'long',
            entry_price = entry_price,
            exit_price  = exit_price,
            params      = {
                'gap_pct':            ev['gap_pct'],
                'pead_hold_days':     PEAD_HOLD_DAYS,
                'gap_threshold':      PEAD_GAP_THRESHOLD,
            },
            signal_type   = 'pead_gap_up',
            llm_confirmed = llm_confirmed,
            llm_score     = confidence,
            llm_direction = direction,
            notes         = f'PEAD gap {ev["gap_pct"]:.1%} | LLM: {direction} conf={confidence} | {reasoning[:100]}',
        )

        logger_unfilt.log(**base_fields)

        if llm_confirmed:
            logger_conf.log(**base_fields)

        if llm_rejected:
            logger_rej.log(**base_fields)

        records.append({
            'symbol':     ev['symbol'],
            'date':       str(ev['date'].date()),
            'gap_pct':    ev['gap_pct'],
            'fwd_ret_20': ev['fwd_ret'],
            'confidence': confidence,
            'direction':  direction,
            'reasoning':  reasoning,
        })
        print(f"    {ev['symbol']} {ev['date'].date()} gap={ev['gap_pct']:.1%} "
              f"conf={confidence} dir={direction} fwd={ev['fwd_ret']:.1%}")

    logger_unfilt.save()
    if len(logger_conf) > 0:
        logger_conf.save()
    if len(logger_rej) > 0:
        logger_rej.save()

    # Summary metrics (for reporting only, not stored in trade logs)
    df = pd.DataFrame(records)

    def sharpe(rets):
        r = np.array(rets, dtype=float)
        if len(r) == 0 or r.std() == 0:
            return 0.0
        return float(r.mean() / r.std() * np.sqrt(252 / PEAD_HOLD_DAYS))

    def winrate(rets):
        r = np.array(rets, dtype=float)
        return float((r > 0).mean()) if len(r) > 0 else 0.0

    baseline  = df['fwd_ret_20'].values
    confirmed = df[(df['confidence'] > 60) & (df['direction'] == 'bullish')]['fwd_ret_20'].values
    rejected  = df[(df['confidence'] < 40) | (df['direction'] == 'bearish')]['fwd_ret_20'].values

    conf_rate = len(confirmed) / len(df) if len(df) > 0 else 0
    prec_lift = winrate(confirmed) - winrate(baseline) if len(confirmed) > 0 else 0

    result = {
        'baseline_sharpe':      round(sharpe(baseline), 4),
        'baseline_winrate':     round(winrate(baseline), 4),
        'llm_filtered_sharpe':  round(sharpe(confirmed), 4),
        'llm_filtered_winrate': round(winrate(confirmed), 4),
        'llm_rejected_sharpe':  round(sharpe(rejected), 4),
        'llm_rejected_winrate': round(winrate(rejected), 4),
        'confirmation_rate':    round(conf_rate, 4),
        'precision_lift':       round(prec_lift, 4),
        'n_baseline':           len(df),
        'n_filtered':           len(confirmed),
        'n_rejected':           len(rejected),
        'records':              records,
    }
    print(f"\n  PEAD baseline  : Sharpe={result['baseline_sharpe']:.3f}  WR={result['baseline_winrate']:.1%}")
    print(f"  PEAD LLM-conf  : Sharpe={result['llm_filtered_sharpe']:.3f}  WR={result['llm_filtered_winrate']:.1%}  n={len(confirmed)}")
    print(f"  PEAD LLM-rej   : Sharpe={result['llm_rejected_sharpe']:.3f}  WR={result['llm_rejected_winrate']:.1%}  n={len(rejected)}")
    print(f"  Confirmation rate: {conf_rate:.1%}  |  Precision lift: {prec_lift:+.1%}")
    return result


# ── Test 2: Pairs (exact logic from llm_signal_harness.py) ────────────────────

def run_test2_pairs() -> dict:
    """
    Run pairs mean-reversion test and log per-trade records to:
      - pairs_unfiltered    (all signals)
      - pairs_llm_confirmed (confidence > 60)
    """
    print('\n=== TEST 2: LLM Filter on Pairs Signals ===')

    all_tickers = list({t for pair in TOP_PAIRS for t in pair})
    closes = _fetch_closes(all_tickers, start='2023-01-01', end='2025-01-01')
    if closes.empty:
        return {}

    all_events = []

    for sym_a, sym_b in TOP_PAIRS:
        if sym_a not in closes.columns or sym_b not in closes.columns:
            print(f'  Skipping {sym_a}/{sym_b}: missing data')
            continue

        pa = closes[sym_a].dropna()
        pb = closes[sym_b].dropna()
        common = pa.index.intersection(pb.index)
        pa, pb = pa[common], pb[common]

        if len(pa) < 60:
            continue

        spread   = pa / pb
        roll_mu  = spread.rolling(60).mean()
        roll_std = spread.rolling(60).std()
        z_score  = (spread - roll_mu) / roll_std

        for i in range(60, len(spread) - 5):
            z = float(z_score.iloc[i])
            if abs(z) < PAIRS_ZSCORE_ENTRY:
                continue

            expected_dir = 'bearish' if z > 0 else 'bullish'
            fwd_ret_spread = float((spread.iloc[i + 5] - spread.iloc[i]) / abs(spread.iloc[i]))
            if z > 0:
                trade_ret = -fwd_ret_spread
            else:
                trade_ret = fwd_ret_spread

            all_events.append({
                'pair':        f'{sym_a}/{sym_b}',
                'sym_a':       sym_a,
                'sym_b':       sym_b,
                'date':        spread.index[i],
                'idx_a':       pa.index.get_loc(spread.index[i]),
                'z_score':     z,
                'spread_val':  float(spread.iloc[i]),
                'spread_mu':   float(roll_mu.iloc[i]),
                'spread_std':  float(roll_std.iloc[i]),
                'trade_ret':   trade_ret,
                'prices_a':    pa,
                'prices_b':    pb,
                'expected_dir': expected_dir,
            })

    print(f'  Found {len(all_events)} pairs signal events (|z| > {PAIRS_ZSCORE_ENTRY})')

    if len(all_events) == 0:
        return {}

    sample = random.sample(all_events, min(SAMPLE_PAIRS, len(all_events)))
    sample.sort(key=lambda x: x['date'])
    print(f'  Sampled {len(sample)} events for LLM evaluation ...')

    logger_unfilt = TradeLogger(round_num=26, strategy='pairs_unfiltered',    category='llm_signal')
    logger_conf   = TradeLogger(round_num=26, strategy='pairs_llm_confirmed',  category='llm_signal')

    records = []
    for ev in sample:
        ctx = build_indicator_context(ev['prices_a'], None, ev['idx_a'], ev['sym_a'])
        trigger_desc = (
            f"Pairs z-score = {ev['z_score']:.2f} for {ev['pair']} spread. "
            f"Spread is {abs(ev['z_score']):.1f} std devs from 60-day mean. "
            f"Mean-reversion setup: {'short' if ev['z_score']>0 else 'long'} spread."
        )
        resp = call_indicator_agent(ctx, 'pairs mean-reversion', trigger_desc)
        time.sleep(0.3)

        confidence = resp.get('confidence', 50)
        direction  = resp.get('direction', 'neutral')
        reasoning  = resp.get('reasoning', '')

        llm_confirmed = confidence > 60

        entry_price = float(ev['prices_a'].iloc[ev['idx_a']])
        exit_idx    = min(ev['idx_a'] + 5, len(ev['prices_a']) - 1)
        exit_price  = float(ev['prices_a'].iloc[exit_idx])
        ret_pct     = ev['trade_ret'] * 100
        trade_dir   = 'short' if ev['z_score'] > 0 else 'long'

        base_fields = dict(
            ticker      = ev['sym_a'],
            entry_date  = ev['date'],
            exit_date   = ev['date'] + pd.Timedelta(days=5),
            return_pct  = float(ret_pct),
            hold_days   = 5,
            direction   = trade_dir,
            entry_price = entry_price,
            exit_price  = exit_price,
            params      = {
                'pair':              ev['pair'],
                'z_score':           ev['z_score'],
                'zscore_entry':      PAIRS_ZSCORE_ENTRY,
                'spread_lookback':   60,
                'hold_days':         5,
            },
            signal_type   = 'pairs_mean_reversion',
            llm_confirmed = llm_confirmed,
            llm_score     = confidence,
            llm_direction = direction,
            notes         = (
                f"Pairs {ev['pair']} z={ev['z_score']:.2f} "
                f"| LLM: {direction} conf={confidence} | {reasoning[:100]}"
            ),
        )

        logger_unfilt.log(**base_fields)

        if llm_confirmed:
            logger_conf.log(**base_fields)

        records.append({
            'pair':       ev['pair'],
            'date':       str(ev['date'].date()),
            'z_score':    ev['z_score'],
            'trade_ret':  ev['trade_ret'],
            'confidence': confidence,
            'direction':  direction,
            'reasoning':  reasoning,
        })
        print(f"    {ev['pair']} {ev['date'].date()} z={ev['z_score']:.2f} "
              f"conf={confidence} dir={direction} ret={ev['trade_ret']:.1%}")

    logger_unfilt.save()
    if len(logger_conf) > 0:
        logger_conf.save()

    df = pd.DataFrame(records)

    def sharpe(rets):
        r = np.array(rets, dtype=float)
        if len(r) == 0 or r.std() == 0:
            return 0.0
        return float(r.mean() / r.std() * np.sqrt(252 / 5))

    def winrate(rets):
        r = np.array(rets, dtype=float)
        return float((r > 0).mean()) if len(r) > 0 else 0.0

    baseline  = df['trade_ret'].values
    confirmed = df[df['confidence'] > 60]['trade_ret'].values
    rejected  = df[df['confidence'] < 40]['trade_ret'].values

    conf_rate = len(confirmed) / len(df) if len(df) > 0 else 0
    prec_lift = winrate(confirmed) - winrate(baseline) if len(confirmed) > 0 else 0

    result = {
        'baseline_sharpe':      round(sharpe(baseline), 4),
        'baseline_winrate':     round(winrate(baseline), 4),
        'llm_filtered_sharpe':  round(sharpe(confirmed), 4),
        'llm_filtered_winrate': round(winrate(confirmed), 4),
        'confirmation_rate':    round(conf_rate, 4),
        'precision_lift':       round(prec_lift, 4),
        'n_baseline':           len(df),
        'n_filtered':           len(confirmed),
        'n_rejected':           len(rejected),
        'records':              records,
    }
    print(f"\n  Pairs baseline : Sharpe={result['baseline_sharpe']:.3f}  WR={result['baseline_winrate']:.1%}")
    print(f"  Pairs LLM-conf : Sharpe={result['llm_filtered_sharpe']:.3f}  WR={result['llm_filtered_winrate']:.1%}  n={len(confirmed)}")
    print(f"  Confirmation rate: {conf_rate:.1%}  |  Precision lift: {prec_lift:+.1%}")
    return result


# ── Test 3: Narratives (exact from llm_signal_harness.py) ─────────────────────

NARRATIVE_PROMPT = (
    'Write exactly 2 sentences for a retail investor explaining why {symbol} gapping up {gap_pct:.1f}% '
    'on {vol_ratio:.1f}x volume represents a post-earnings drift opportunity. '
    'Use these indicators: RSI={rsi:.0f}, price {pct:.1f}% {above_below} 20d SMA ${sma20:.2f}, '
    '5d return {ret5d:+.1f}%. Be specific and concrete.'
)


def run_test3_narratives(pead_records: list) -> list:
    print('\n=== TEST 3: LLM Signal Narratives ===')

    if not pead_records:
        return []

    recent = sorted(pead_records, key=lambda x: x['date'], reverse=True)[:5]

    narratives = []
    for ev in recent:
        prompt = NARRATIVE_PROMPT.format(
            symbol=ev['symbol'],
            gap_pct=ev['gap_pct'] * 100,
            vol_ratio=ev.get('vol_ratio', 1.5),
            rsi=ev.get('rsi', 60),
            pct=ev.get('pct', 2.0),
            above_below=ev.get('above_below', 'above'),
            sma20=ev.get('sma20', ev.get('price', 100.0)),
            ret5d=ev.get('ret5d', 0.0),
        )
        narrative = call_claude_narrative(prompt)
        time.sleep(0.3)

        narratives.append({
            'symbol':    ev['symbol'],
            'date':      ev['date'],
            'gap_pct':   ev['gap_pct'],
            'narrative': narrative.strip(),
        })
        print(f"  {ev['symbol']} ({ev['date']}): {narrative[:120]} ...")

    return narratives


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print('=' * 60)
    print('LLM V2 Signal Interpretation Harness - Round 26 (TradeLogger)')
    print('=' * 60)

    os.makedirs('/tmp/eval_deps_llm', exist_ok=True)

    t1 = run_test1_pead()
    t2 = run_test2_pairs()

    # Enrich PEAD records with indicator context for narrative test
    pead_records_for_narr = []
    if t1 and 'records' in t1:
        closes  = _fetch_closes(UNIVERSE)
        volumes = _fetch_volume(UNIVERSE)
        for rec in t1.get('records', []):
            if rec['symbol'] in closes.columns:
                prices = closes[rec['symbol']].dropna()
                vols   = volumes[rec['symbol']].dropna() if rec['symbol'] in volumes.columns else None
                try:
                    idx = prices.index.get_loc(rec['date'])
                except KeyError:
                    idx = None
                if idx is not None:
                    ctx = build_indicator_context(prices, vols, idx, rec['symbol'])
                    pead_records_for_narr.append({**rec, **ctx})
                else:
                    pead_records_for_narr.append(rec)
            else:
                pead_records_for_narr.append(rec)

    t3_narratives = run_test3_narratives(pead_records_for_narr)

    estimated_cost = round(api_calls_made * 0.00052, 4)

    pead_lift   = t1.get('precision_lift', 0) if t1 else 0
    pead_reduce = 1 - t1.get('confirmation_rate', 1) if t1 else 0
    key_finding = (
        f"LLM filtering improves PEAD precision by {pead_lift:+.1%} at cost of "
        f"{pead_reduce:.1%} signal reduction (confirmation rate "
        f"{t1.get('confirmation_rate',0):.1%}). "
        f"Pairs strategy confirmation rate: {t2.get('confirmation_rate',0):.1%}."
    )

    t1_out = {k: v for k, v in t1.items() if k != 'records'} if t1 else {}
    t2_out = {k: v for k, v in t2.items() if k != 'records'} if t2 else {}

    output = {
        'category':           'llm_signal_interpretation',
        'round':              26,
        'timestamp':          datetime.now().isoformat(),
        'test_1_pead':        t1_out,
        'test_2_pairs':       t2_out,
        'sample_narratives':  t3_narratives,
        'key_finding':        key_finding,
        'api_calls_made':     api_calls_made,
        'estimated_cost_usd': estimated_cost,
        'strategy_variants': [
            'pead_unfiltered',
            'pead_llm_confirmed',
            'pead_llm_rejected',
            'pairs_unfiltered',
            'pairs_llm_confirmed',
        ],
    }

    out_path = ROUNDS_DIR / 'llm_signal_results_v2.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f'\nResults saved to {out_path}')
    print('Trade logs written to /workspace/group/trading_eval/trade_logs/')

    return output


if __name__ == '__main__':
    result = main()
    print('\nDone. Summary:')
    print(f"  API calls: {result['api_calls_made']}")
    print(f"  Est. cost: ${result['estimated_cost_usd']:.4f}")
    print(f"  Key finding: {result['key_finding']}")
