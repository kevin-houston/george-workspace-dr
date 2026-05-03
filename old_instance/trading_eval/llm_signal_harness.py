"""
LLM Signal Interpretation Harness - Round 26
==============================================
Tests whether an LLM (IndicatorAgent) can improve trading signal accuracy
by filtering/confirming rule-based signals before entry.

Inspired by QuantAgent (arXiv:2509.09995).

Tests:
  1. LLM filter on PEAD gap signals (100 sampled events)
  2. LLM filter on Pairs mean-reversion signals (50 sampled events)
  3. LLM signal narratives for 5 most recent PEAD gaps (product feature)
"""

import sys
sys.path.insert(0, '/tmp/eval_deps_llm')

import json
import os
import random
import time
import warnings
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'COST',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'NFLX', 'ADBE', 'QCOM', 'TXN', 'HON',
    'GE', 'CAT', 'MMM', 'LMT', 'RTX'
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

PEAD_GAP_THRESHOLD = 0.03   # 3% gap
PEAD_HOLD_DAYS     = 20
PAIRS_ZSCORE_ENTRY = 1.5
SAMPLE_PEAD        = 100
SAMPLE_PAIRS       = 50

api_calls_made = 0
random.seed(42)
np.random.seed(42)


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────
def fetch_data(tickers, start=START_DATE, end=END_DATE):
    """Download OHLCV with caching."""
    all_tickers = sorted(set(tickers))
    cache_key   = '_'.join(all_tickers[:5]) + f"_{start}_{end}"
    cache_path  = CACHE_DIR / f"llm_{cache_key[:60]}.pkl"

    if cache_path.exists():
        print(f"  [cache] Loading {cache_path.name}")
        return pd.read_pickle(cache_path)

    print(f"  [yfinance] Downloading {len(all_tickers)} tickers …")
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
        print(f"  [error] Download failed: {e}")
        return pd.DataFrame()


def fetch_volume(tickers, start=START_DATE, end=END_DATE):
    """Download Volume data with caching."""
    all_tickers = sorted(set(tickers))
    cache_key   = '_'.join(all_tickers[:5]) + f"_vol_{start}_{end}"
    cache_path  = CACHE_DIR / f"llm_vol_{cache_key[:60]}.pkl"

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
        print(f"  [error] Volume download failed: {e}")
        return pd.DataFrame()


# ─────────────────────────────────────────────
# LLM INTERFACE
# ─────────────────────────────────────────────
def call_claude(prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Call Claude via the CLI (which handles auth automatically)."""
    global api_calls_made
    import subprocess
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--setting-sources", "user",  # skip project CLAUDE.md for speed
                "--system-prompt", "You are a quantitative trading signal analyst. Respond only with valid JSON, no markdown fences.",
                "--tools", "",
            ],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            out = result.stdout.strip()
            api_calls_made += 1
            return out
        else:
            err = (result.stderr or "unknown error")[:200]
            print(f"  [API error] rc={result.returncode} {err}")
            return '{"confidence": 50, "direction": "neutral", "reasoning": "API error"}'
    except Exception as e:
        print(f"  [API error] {e}")
        return '{"confidence": 50, "direction": "neutral", "reasoning": "API error"}'


def call_claude_narrative(prompt: str, model: str = "claude-haiku-4-5") -> str:
    """Call Claude for free-text narrative output."""
    import subprocess
    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--model", model,
                "--setting-sources", "user",
                "--system-prompt", "You are a financial analyst writing clear, concise trading signal narratives for retail investors.",
                "--tools", "",
            ],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "Narrative unavailable."
    except Exception as e:
        return f"Narrative error: {e}"


def parse_llm_json(text: str) -> dict:
    """Extract JSON from LLM response."""
    try:
        # Find the JSON object in the response
        start = text.find('{')
        end   = text.rfind('}') + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception:
        pass
    return {"confidence": 50, "direction": "neutral", "reasoning": "parse error"}


# ─────────────────────────────────────────────
# INDICATOR HELPERS
# ─────────────────────────────────────────────
def compute_rsi(prices: pd.Series, period: int = 14) -> float:
    """Compute RSI(14) for a price series, return most recent value."""
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
    """
    Build market state dict at position idx (requires >= 30 bars before).
    Returns dict with all fields needed for LLM prompt.
    """
    window = prices.iloc[max(0, idx - 40): idx + 1]
    if len(window) < 20:
        return {}

    price  = float(window.iloc[-1])
    sma20  = float(window.iloc[-20:].mean())
    above_below = "above" if price > sma20 else "below"
    pct    = abs(price - sma20) / sma20 * 100

    # RSI
    rsi = compute_rsi(window)

    # Annualised volatility from 20-day returns
    rets = window.pct_change().dropna()
    vol  = float(rets.iloc[-20:].std() * np.sqrt(252) * 100) if len(rets) >= 20 else 20.0

    # Recent returns
    ret5d  = float((price / window.iloc[-6] - 1) * 100) if len(window) > 5 else 0.0
    ret20d = float((price / window.iloc[-21] - 1) * 100) if len(window) > 20 else 0.0

    # Volume ratio
    vol_ratio = 1.0
    if volumes is not None and len(volumes) > 20:
        vol_window = volumes.iloc[max(0, idx - 20): idx + 1]
        if len(vol_window) >= 2:
            avg_vol   = float(vol_window.iloc[:-1].mean())
            today_vol = float(vol_window.iloc[-1])
            vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0

    return {
        "symbol":      symbol,
        "price":       price,
        "sma20":       sma20,
        "above_below": above_below,
        "pct":         pct,
        "rsi":         rsi,
        "vol":         vol,
        "ret5d":       ret5d,
        "ret20d":      ret20d,
        "vol_ratio":   vol_ratio,
    }


# ─────────────────────────────────────────────
# INDICATOR AGENT
# ─────────────────────────────────────────────
INDICATOR_PROMPT = (
    "Rate {strategy} signal. "
    "Symbol: {symbol}. Trigger: {trigger_desc}. "
    "Price: ${price:.2f}. SMA20: ${sma20:.2f} (price {above_below} by {pct:.1f}%). "
    "RSI14: {rsi:.1f}. AnnVol: {vol:.1f}%. "
    "5d ret: {ret5d:+.1f}%. 20d ret: {ret20d:+.1f}%. VolRatio: {vol_ratio:.2f}x. "
    'Reply ONLY valid JSON: {{"confidence": <0-100>, "direction": "<bullish|bearish|neutral>", "reasoning": "<one sentence>"}}'
)


def call_indicator_agent(ctx: dict, strategy: str, trigger_desc: str) -> dict:
    """Call IndicatorAgent with market context, return parsed JSON."""
    if not ctx:
        return {"confidence": 50, "direction": "neutral", "reasoning": "no context"}

    prompt = INDICATOR_PROMPT.format(
        strategy=strategy,
        trigger_desc=trigger_desc,
        **ctx,
    )
    raw  = call_claude(prompt)
    resp = parse_llm_json(raw)
    return resp


# ─────────────────────────────────────────────
# TEST 1: LLM FILTER ON PEAD SIGNALS
# ─────────────────────────────────────────────
def run_test1_pead():
    """Test LLM filtering on PEAD gap signals."""
    print("\n=== TEST 1: LLM Filter on PEAD Signals ===")

    closes  = fetch_data(UNIVERSE)
    volumes = fetch_volume(UNIVERSE)
    if closes.empty:
        return {}

    # Collect all gap events
    all_events = []
    for symbol in UNIVERSE:
        if symbol not in closes.columns:
            continue
        prices = closes[symbol].dropna()
        vols   = volumes[symbol].dropna() if symbol in volumes.columns else None

        if len(prices) < 60:
            continue

        # Compute overnight gaps
        gaps = prices.pct_change()

        for i in range(30, len(prices) - PEAD_HOLD_DAYS - 1):
            gap = float(gaps.iloc[i])
            if gap < PEAD_GAP_THRESHOLD:
                continue

            # Forward return over 20 days
            fwd_ret = float(prices.iloc[i + PEAD_HOLD_DAYS] / prices.iloc[i] - 1)

            # Build volume index alignment
            vol_idx = None
            if vols is not None:
                price_date = prices.index[i]
                if price_date in vols.index:
                    vol_idx = vols.index.get_loc(price_date)

            all_events.append({
                "symbol":    symbol,
                "date":      prices.index[i],
                "price_idx": i,
                "gap_pct":   gap,
                "fwd_ret":   fwd_ret,
                "prices":    prices,
                "vols":      vols,
                "vol_idx":   vol_idx,
            })

    print(f"  Found {len(all_events)} raw gap events (gap > {PEAD_GAP_THRESHOLD:.0%})")

    if len(all_events) == 0:
        return {}

    # Sample
    sample = random.sample(all_events, min(SAMPLE_PEAD, len(all_events)))
    sample.sort(key=lambda x: x['date'])

    print(f"  Sampled {len(sample)} events for LLM evaluation …")

    records = []
    for ev in sample:
        ctx = build_indicator_context(
            ev['prices'], ev['vols'], ev['price_idx'], ev['symbol']
        )
        trigger_desc = (
            f"Gap-up of {ev['gap_pct']:.1%} on {ev['date'].date()}, "
            f"potential post-earnings drift continuation"
        )
        resp = call_indicator_agent(ctx, "PEAD gap-up", trigger_desc)
        time.sleep(0.3)  # gentle rate limiting

        records.append({
            "symbol":     ev['symbol'],
            "date":       str(ev['date'].date()),
            "gap_pct":    ev['gap_pct'],
            "fwd_ret_20": ev['fwd_ret'],
            "confidence": resp.get("confidence", 50),
            "direction":  resp.get("direction", "neutral"),
            "reasoning":  resp.get("reasoning", ""),
        })
        print(f"    {ev['symbol']} {ev['date'].date()} gap={ev['gap_pct']:.1%} "
              f"conf={resp.get('confidence',50)} dir={resp.get('direction','?')} "
              f"fwd={ev['fwd_ret']:.1%}")

    # ── Metrics ──
    df = pd.DataFrame(records)

    def sharpe(rets):
        r = np.array(rets, dtype=float)
        if len(r) == 0 or r.std() == 0:
            return 0.0
        return float(r.mean() / r.std() * np.sqrt(252 / PEAD_HOLD_DAYS))

    def winrate(rets):
        r = np.array(rets, dtype=float)
        return float((r > 0).mean()) if len(r) > 0 else 0.0

    baseline     = df['fwd_ret_20'].values
    confirmed    = df[
        (df['confidence'] > 60) & (df['direction'] == 'bullish')
    ]['fwd_ret_20'].values
    rejected     = df[
        (df['confidence'] < 40) | (df['direction'] == 'bearish')
    ]['fwd_ret_20'].values

    conf_rate    = len(confirmed) / len(df) if len(df) > 0 else 0
    prec_lift    = winrate(confirmed) - winrate(baseline) if len(confirmed) > 0 else 0

    result = {
        "baseline_sharpe":      round(sharpe(baseline), 4),
        "baseline_winrate":     round(winrate(baseline), 4),
        "llm_filtered_sharpe":  round(sharpe(confirmed), 4),
        "llm_filtered_winrate": round(winrate(confirmed), 4),
        "llm_rejected_sharpe":  round(sharpe(rejected), 4),
        "llm_rejected_winrate": round(winrate(rejected), 4),
        "confirmation_rate":    round(conf_rate, 4),
        "precision_lift":       round(prec_lift, 4),
        "n_baseline":           len(df),
        "n_filtered":           len(confirmed),
        "n_rejected":           len(rejected),
        "records":              records,
    }
    print(f"\n  PEAD baseline  : Sharpe={result['baseline_sharpe']:.3f}  WR={result['baseline_winrate']:.1%}")
    print(f"  PEAD LLM-conf  : Sharpe={result['llm_filtered_sharpe']:.3f}  WR={result['llm_filtered_winrate']:.1%}  n={len(confirmed)}")
    print(f"  PEAD LLM-rej   : Sharpe={result['llm_rejected_sharpe']:.3f}  WR={result['llm_rejected_winrate']:.1%}  n={len(rejected)}")
    print(f"  Confirmation rate: {conf_rate:.1%}  |  Precision lift: {prec_lift:+.1%}")
    return result


# ─────────────────────────────────────────────
# TEST 2: LLM FILTER ON PAIRS SIGNALS
# ─────────────────────────────────────────────
def run_test2_pairs():
    """Test LLM filtering on pairs mean-reversion signals."""
    print("\n=== TEST 2: LLM Filter on Pairs Signals ===")

    all_tickers = list({t for pair in TOP_PAIRS for t in pair})
    # Use last 60 days + enough history for indicators
    closes = fetch_data(all_tickers, start='2023-01-01', end='2025-01-01')
    if closes.empty:
        return {}

    all_events = []

    for sym_a, sym_b in TOP_PAIRS:
        if sym_a not in closes.columns or sym_b not in closes.columns:
            print(f"  Skipping {sym_a}/{sym_b}: missing data")
            continue

        pa = closes[sym_a].dropna()
        pb = closes[sym_b].dropna()
        common = pa.index.intersection(pb.index)
        pa, pb = pa[common], pb[common]

        if len(pa) < 60:
            continue

        # Compute spread ratio and z-score
        spread   = pa / pb
        roll_mu  = spread.rolling(60).mean()
        roll_std = spread.rolling(60).std()
        z_score  = (spread - roll_mu) / roll_std

        for i in range(60, len(spread) - 5):
            z = float(z_score.iloc[i])
            if abs(z) < PAIRS_ZSCORE_ENTRY:
                continue

            # Expected direction: spread reverts toward mean
            # If z > 0 (spread high): short spread = short A, long B → bearish A
            # If z < 0 (spread low):  long spread = long A, short B → bullish A
            expected_dir = "bearish" if z > 0 else "bullish"
            fwd_ret_spread = float((spread.iloc[i + 5] - spread.iloc[i]) / abs(spread.iloc[i]))
            # Profit: if spread reverts, short spread profits when z > 0
            if z > 0:
                trade_ret = -fwd_ret_spread  # short spread
            else:
                trade_ret = fwd_ret_spread   # long spread

            all_events.append({
                "pair":        f"{sym_a}/{sym_b}",
                "sym_a":       sym_a,
                "sym_b":       sym_b,
                "date":        spread.index[i],
                "idx_a":       pa.index.get_loc(spread.index[i]),
                "z_score":     z,
                "spread_val":  float(spread.iloc[i]),
                "spread_mu":   float(roll_mu.iloc[i]),
                "spread_std":  float(roll_std.iloc[i]),
                "trade_ret":   trade_ret,
                "prices_a":    pa,
                "prices_b":    pb,
                "expected_dir": expected_dir,
            })

    print(f"  Found {len(all_events)} pairs signal events (|z| > {PAIRS_ZSCORE_ENTRY})")

    if len(all_events) == 0:
        return {}

    sample = random.sample(all_events, min(SAMPLE_PAIRS, len(all_events)))
    sample.sort(key=lambda x: x['date'])
    print(f"  Sampled {len(sample)} events for LLM evaluation …")

    records = []
    for ev in sample:
        ctx = build_indicator_context(ev['prices_a'], None, ev['idx_a'], ev['sym_a'])
        trigger_desc = (
            f"Pairs z-score = {ev['z_score']:.2f} for {ev['pair']} spread. "
            f"Spread is {abs(ev['z_score']):.1f} std devs from 60-day mean. "
            f"Mean-reversion setup: {'short' if ev['z_score']>0 else 'long'} spread."
        )
        resp = call_indicator_agent(ctx, "pairs mean-reversion", trigger_desc)
        time.sleep(0.3)

        records.append({
            "pair":       ev['pair'],
            "date":       str(ev['date'].date()),
            "z_score":    ev['z_score'],
            "trade_ret":  ev['trade_ret'],
            "confidence": resp.get("confidence", 50),
            "direction":  resp.get("direction", "neutral"),
            "reasoning":  resp.get("reasoning", ""),
        })
        print(f"    {ev['pair']} {ev['date'].date()} z={ev['z_score']:.2f} "
              f"conf={resp.get('confidence',50)} dir={resp.get('direction','?')} "
              f"ret={ev['trade_ret']:.1%}")

    # ── Metrics ──
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

    conf_rate  = len(confirmed) / len(df) if len(df) > 0 else 0
    prec_lift  = winrate(confirmed) - winrate(baseline) if len(confirmed) > 0 else 0

    result = {
        "baseline_sharpe":      round(sharpe(baseline), 4),
        "baseline_winrate":     round(winrate(baseline), 4),
        "llm_filtered_sharpe":  round(sharpe(confirmed), 4),
        "llm_filtered_winrate": round(winrate(confirmed), 4),
        "confirmation_rate":    round(conf_rate, 4),
        "precision_lift":       round(prec_lift, 4),
        "n_baseline":           len(df),
        "n_filtered":           len(confirmed),
        "n_rejected":           len(rejected),
        "records":              records,
    }
    print(f"\n  Pairs baseline : Sharpe={result['baseline_sharpe']:.3f}  WR={result['baseline_winrate']:.1%}")
    print(f"  Pairs LLM-conf : Sharpe={result['llm_filtered_sharpe']:.3f}  WR={result['llm_filtered_winrate']:.1%}  n={len(confirmed)}")
    print(f"  Confirmation rate: {conf_rate:.1%}  |  Precision lift: {prec_lift:+.1%}")
    return result


# ─────────────────────────────────────────────
# TEST 3: LLM SIGNAL NARRATIVES
# ─────────────────────────────────────────────
NARRATIVE_PROMPT = (
    "Write exactly 2 sentences for a retail investor explaining why {symbol} gapping up {gap_pct:.1f}% "
    "on {vol_ratio:.1f}x volume represents a post-earnings drift opportunity. "
    "Use these indicators: RSI={rsi:.0f}, price {pct:.1f}% {above_below} 20d SMA ${sma20:.2f}, "
    "5d return {ret5d:+.1f}%. Be specific and concrete."
)


def run_test3_narratives(pead_records: list) -> list:
    """Generate LLM narratives for the 5 most recent PEAD gap events."""
    print("\n=== TEST 3: LLM Signal Narratives ===")

    if not pead_records:
        return []

    # Sort by date descending, take 5 most recent
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
            "symbol":    ev['symbol'],
            "date":      ev['date'],
            "gap_pct":   ev['gap_pct'],
            "narrative": narrative.strip(),
        })
        print(f"  {ev['symbol']} ({ev['date']}): {narrative[:120]} …")

    return narratives


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("LLM Signal Interpretation Harness - Round 26")
    print("=" * 60)

    # Install deps
    os.makedirs('/tmp/eval_deps_llm', exist_ok=True)

    t1 = run_test1_pead()
    t2 = run_test2_pairs()

    # Enrich PEAD records with indicator context for narrative test
    pead_records_for_narr = []
    if t1 and 'records' in t1:
        # Re-fetch closes to get indicator data for narratives
        closes  = fetch_data(UNIVERSE)
        volumes = fetch_volume(UNIVERSE)
        for rec in t1.get('records', []):
            if rec['symbol'] in closes.columns:
                prices = closes[rec['symbol']].dropna()
                vols   = volumes[rec['symbol']].dropna() if rec['symbol'] in volumes.columns else None
                # Find index for this date
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

    # ── Estimated cost ──
    # Haiku-4-5: ~$0.0008 per 1K input tokens, ~$0.004 per 1K output tokens
    # Average ~250 input + 80 output tokens per call → ~$0.00052/call
    estimated_cost = round(api_calls_made * 0.00052, 4)

    # ── Key finding ──
    pead_lift   = t1.get('precision_lift', 0) if t1 else 0
    pead_reduce = 1 - t1.get('confirmation_rate', 1) if t1 else 0
    key_finding = (
        f"LLM filtering improves PEAD precision by {pead_lift:+.1%} at cost of "
        f"{pead_reduce:.1%} signal reduction (confirmation rate "
        f"{t1.get('confirmation_rate',0):.1%}). "
        f"Pairs strategy confirmation rate: {t2.get('confirmation_rate',0):.1%}."
    )

    # ── Strip heavy records before saving ──
    t1_out = {k: v for k, v in t1.items() if k != 'records'} if t1 else {}
    t2_out = {k: v for k, v in t2.items() if k != 'records'} if t2 else {}

    output = {
        "category":           "llm_signal_interpretation",
        "round":              26,
        "timestamp":          datetime.now().isoformat(),
        "test_1_pead":        t1_out,
        "test_2_pairs":       t2_out,
        "sample_narratives":  t3_narratives,
        "key_finding":        key_finding,
        "api_calls_made":     api_calls_made,
        "estimated_cost_usd": estimated_cost,
    }

    out_path = Path('/workspace/group/trading_eval/rounds/llm_signal_results.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    return output


if __name__ == '__main__':
    result = main()
    print("\nDone. Summary:")
    print(f"  API calls: {result['api_calls_made']}")
    print(f"  Est. cost: ${result['estimated_cost_usd']:.4f}")
    print(f"  Key finding: {result['key_finding']}")
