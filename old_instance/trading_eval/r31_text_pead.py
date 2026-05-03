#!/usr/bin/env /usr/bin/python3.11
"""
R31: Text-based PEAD using FinBERT sentiment on earnings releases
with 3-day confirmation window.

Tests whether NLP sentiment from earnings text provides additional PEAD
signal beyond price gaps.

Text signal hierarchy:
1. Primary: EPS surprise % from cached earnings data (AlphaVantage format)
   as proxy for earnings text sentiment — maps to [-1, +1] via tanh
2. Secondary: yfinance .news headlines with FinBERT or word-count fallback
   (only recent news available, so coverage is sparse for historical periods)
3. Fallback: gap magnitude only (neutral = 0.0)
"""

import sys
sys.path.insert(0, '/home/node/.local/lib/python3.11/site-packages')
sys.path.insert(0, '/tmp/eval_deps_pead')

import json
import os
import pickle
import warnings
import time
import re
import math
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'KO',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'COST', 'NFLX', 'QCOM', 'TXN', 'GE'
]

START_DATE = '2020-01-01'
END_DATE   = '2025-12-31'
GAP_THRESHOLD = 0.05   # 5%+ gap-up
HOLD_PERIOD   = 20     # 20-day hold
CONFIRM_DAYS  = 3      # 3-day confirmation window

CACHE_DIR    = '/workspace/group/trading_eval/cache'
EARNINGS_DIR = '/workspace/group/trading_eval/cache/earnings'
ROUNDS_DIR   = '/workspace/group/trading_eval/rounds'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(ROUNDS_DIR, exist_ok=True)

# Text scoring method — will be set after load
TEXT_METHOD = 'unknown'

# ─────────────────────────────────────────────
# POSITIVE / NEGATIVE WORD DICTS (HEADLINE FALLBACK)
# ─────────────────────────────────────────────
POSITIVE_WORDS = {
    'beat', 'beats', 'exceeds', 'exceeded', 'record', 'surges', 'surge',
    'strong', 'raised', 'raises', 'above', 'growth', 'profit', 'gains',
    'better', 'top', 'tops', 'upbeat', 'positive', 'increase', 'increased',
    'climbs', 'rises', 'rally', 'rallies', 'upgraded', 'upgrade', 'high',
    'boom', 'booms', 'expansion', 'momentum', 'outperform', 'outperforms',
    'strength', 'robust', 'booming', 'highest', 'accelerating', 'success',
    'impressive', 'confidence', 'buy', 'bullish', 'upside', 'soars', 'soar',
    'optimistic', 'encouraging', 'winning', 'wins', 'excellent', 'stellar',
}
NEGATIVE_WORDS = {
    'miss', 'misses', 'missed', 'below', 'weak', 'cuts', 'cut', 'disappoints',
    'lowered', 'loss', 'decline', 'falls', 'drops', 'drop', 'fell',
    'worse', 'warning', 'warns', 'downturn', 'slows', 'slowdown', 'pressure',
    'disappointing', 'concern', 'concerns', 'risk', 'risks', 'uncertain',
    'uncertainty', 'fears', 'fear', 'sell', 'bearish', 'downgrade', 'downgraded',
    'weaker', 'challenging', 'difficulties', 'difficult', 'threat', 'threats',
    'negative', 'poor', 'struggles', 'struggle', 'lower', 'worst',
    'problems', 'problem', 'crisis', 'crash',
}


def word_count_sentiment(text: str) -> float:
    """Compute text surprise using positive/negative word counts."""
    tokens = re.findall(r'\b\w+\b', text.lower())
    pos = sum(1 for w in tokens if w in POSITIVE_WORDS)
    neg = sum(1 for w in tokens if w in NEGATIVE_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


# ─────────────────────────────────────────────
# FINBERT LOADER
# ─────────────────────────────────────────────
_finbert_pipeline = None
_finbert_attempted = False

def try_load_finbert():
    """Try to load FinBERT pipeline; return True on success."""
    global _finbert_pipeline, _finbert_attempted, TEXT_METHOD
    if _finbert_attempted:
        return _finbert_pipeline is not None
    _finbert_attempted = True
    try:
        from transformers import pipeline
        print("  Attempting to load FinBERT (ProsusAI/finbert)...")
        _finbert_pipeline = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            top_k=None,
            truncation=True,
            max_length=512,
        )
        TEXT_METHOD = 'finbert'
        print("  FinBERT loaded successfully.")
        return True
    except Exception as e:
        print(f"  FinBERT load failed: {e}")
        print("  Falling back to word-count sentiment.")
        TEXT_METHOD = 'word_count_fallback'
        return False


def score_text(text: str) -> float:
    """
    Return text_surprise in [-1, +1].
    Uses FinBERT if available, otherwise word-count fallback.
    """
    if not text or not text.strip():
        return 0.0
    global _finbert_pipeline
    if _finbert_pipeline is not None:
        try:
            results = _finbert_pipeline(text[:512])
            scores = {r['label'].lower(): r['score'] for r in results[0]}
            pos = scores.get('positive', 0.0)
            neg = scores.get('negative', 0.0)
            return float(pos - neg)
        except Exception:
            pass
    return word_count_sentiment(text)


# ─────────────────────────────────────────────
# EPS SURPRISE DATA (PRIMARY TEXT PROXY)
# ─────────────────────────────────────────────
def load_eps_surprise_lookup() -> dict:
    """
    Load EPS surprise data from cached earnings files.
    Returns: {ticker -> {date -> eps_surprise_score}}
    where eps_surprise_score is in [-1, +1] via tanh(surprise_pct / 20)
    """
    lookup = {}
    if not os.path.isdir(EARNINGS_DIR):
        print(f"  Earnings dir not found: {EARNINGS_DIR}")
        return lookup

    for fname in os.listdir(EARNINGS_DIR):
        if not fname.endswith('_earnings.json'):
            continue
        ticker = fname.replace('_earnings.json', '')
        if ticker not in UNIVERSE:
            continue
        try:
            with open(os.path.join(EARNINGS_DIR, fname)) as f:
                data = json.load(f)
            quarterly = data.get('quarterlyEarnings', [])
            by_date = {}
            for q in quarterly:
                report_date = q.get('reportedDate', '')
                surprise_pct = q.get('surprisePercentage', None)
                if report_date and surprise_pct is not None:
                    try:
                        pct = float(surprise_pct)
                        # tanh normalization: 20% surprise -> ~0.76, 5% -> ~0.24, -10% -> ~-0.46
                        score = float(np.tanh(pct / 20.0))
                        dt = datetime.strptime(report_date, '%Y-%m-%d').date()
                        by_date[dt] = score
                    except (ValueError, TypeError):
                        pass
            lookup[ticker] = by_date
            print(f"  {ticker}: {len(by_date)} EPS surprise dates loaded")
        except Exception as e:
            print(f"  Failed to load earnings for {ticker}: {e}")

    return lookup


def get_eps_surprise_near_date(eps_lookup: dict, ticker: str,
                                target_date, window_days: int = 5) -> float | None:
    """
    Return EPS surprise score for ticker within ±window_days of target_date.
    Returns None if no data found in window.
    """
    if hasattr(target_date, 'date'):
        target_date = target_date.date()

    by_date = eps_lookup.get(ticker, {})
    if not by_date:
        return None

    best_score = None
    best_dist = window_days + 1

    for d, score in by_date.items():
        dist = abs((d - target_date).days)
        if dist <= window_days and dist < best_dist:
            best_dist = dist
            best_score = score

    return best_score


# ─────────────────────────────────────────────
# NEWS FETCHING (SECONDARY — recent headlines only)
# ─────────────────────────────────────────────
def fetch_news_for_ticker(ticker: str) -> list:
    """
    Fetch yfinance news for a ticker (recent only).
    Returns list of dicts with 'title', 'date'.
    """
    import yfinance as yf

    cache_file = os.path.join(CACHE_DIR, f'r31_news_{ticker}.pkl')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass

    news_items = []
    try:
        tkr = yf.Ticker(ticker)
        raw = tkr.news or []
        for item in raw:
            # New yfinance format: item['content']['title'] and item['content']['pubDate']
            content = item.get('content', {})
            title = content.get('title', '') or item.get('title', '')
            pub_date = content.get('pubDate', '') or content.get('displayTime', '')
            ts = item.get('providerPublishTime', 0)

            if title:
                if pub_date:
                    try:
                        # Parse ISO date like "2026-04-11T19:31:09Z"
                        dt = datetime.strptime(pub_date[:10], '%Y-%m-%d').date()
                    except Exception:
                        dt = None
                elif ts:
                    dt = datetime.utcfromtimestamp(ts).date()
                else:
                    dt = None

                if dt:
                    news_items.append({'title': title, 'date': dt})
    except Exception as e:
        print(f"  News fetch failed for {ticker}: {e}")

    with open(cache_file, 'wb') as f:
        pickle.dump(news_items, f)
    return news_items


def build_news_lookup(tickers: list) -> dict:
    """Build {ticker -> {date -> [headlines]}}"""
    lookup = {}
    total_items = 0
    for ticker in tickers:
        news = fetch_news_for_ticker(ticker)
        by_date = defaultdict(list)
        for item in news:
            if item.get('date'):
                by_date[item['date']].append(item['title'])
        lookup[ticker] = by_date
        total_items += len(news)
    print(f"  Total recent headlines fetched: {total_items}")
    return lookup


def get_headlines_around_date(news_lookup: dict, ticker: str,
                               target_date, window_days: int = 2) -> list:
    """Return headlines within ±window_days of target_date."""
    if hasattr(target_date, 'date'):
        target_date = target_date.date()
    elif isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    by_date = news_lookup.get(ticker, {})
    headlines = []
    for d_offset in range(-window_days, window_days + 1):
        check_date = target_date + timedelta(days=d_offset)
        headlines.extend(by_date.get(check_date, []))
    return headlines


# ─────────────────────────────────────────────
# COMBINED TEXT SCORE
# ─────────────────────────────────────────────
def get_text_surprise(ticker: str, gap_date, eps_lookup: dict,
                      news_lookup: dict) -> tuple[float, str]:
    """
    Get text surprise score for a gap event.
    Returns (score, source) where source is one of:
      'eps_surprise', 'finbert_headlines', 'word_count_headlines', 'neutral'
    """
    # Primary: EPS surprise
    eps_score = get_eps_surprise_near_date(eps_lookup, ticker, gap_date, window_days=5)
    if eps_score is not None:
        return eps_score, 'eps_surprise'

    # Secondary: headlines with FinBERT or word-count
    headlines = get_headlines_around_date(news_lookup, ticker, gap_date, window_days=2)
    if headlines:
        scores = [score_text(h) for h in headlines]
        avg_score = float(np.mean(scores))
        source = 'finbert_headlines' if TEXT_METHOD == 'finbert' else 'word_count_headlines'
        return avg_score, source

    # No data: neutral
    return 0.0, 'neutral'


# ─────────────────────────────────────────────
# MARKET DATA
# ─────────────────────────────────────────────
def fetch_price_data(tickers, start, end):
    """Download OHLCV data with caching."""
    import yfinance as yf

    cache_file = os.path.join(CACHE_DIR, f'pead_universe_{start}_{end}.pkl')
    if os.path.exists(cache_file):
        print(f"  Loading price data from cache: {cache_file}")
        return pd.read_pickle(cache_file)

    all_data = {}
    for ticker in tickers:
        for attempt in range(3):
            try:
                df = yf.download(ticker, start=start, end=end,
                                 auto_adjust=True, progress=False)
                if df is not None and len(df) > 200:
                    df.index = pd.to_datetime(df.index)
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    all_data[ticker] = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                    print(f"  {ticker}: {len(df)} rows")
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f"  {ticker} attempt {attempt+1} failed: {e}")
                time.sleep(1)

    combined = {}
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        combined[col] = pd.DataFrame(
            {t: all_data[t][col] for t in all_data if col in all_data[t].columns}
        )
    result = pd.concat({col: combined[col] for col in combined}, axis=1)
    result.to_pickle(cache_file)
    return result


# ─────────────────────────────────────────────
# GAP DETECTION
# ─────────────────────────────────────────────
def compute_gap_signals(data, tickers, threshold=GAP_THRESHOLD):
    """Find gap-up events for each ticker."""
    ticker_frames = {}
    for ticker in tickers:
        try:
            close  = data['Close'][ticker].dropna()
            open_  = data['Open'][ticker].dropna()
            volume = data['Volume'][ticker].dropna()

            df = pd.DataFrame({'close': close, 'open': open_, 'volume': volume}).dropna()
            df['prev_close'] = df['close'].shift(1)
            df['gap'] = df['open'] / df['prev_close'] - 1
            df['vol_avg20'] = df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['volume'] / df['vol_avg20']

            df.attrs['ticker'] = ticker
            ticker_frames[ticker] = df.dropna()
        except Exception as e:
            print(f"  Gap compute failed for {ticker}: {e}")
    return ticker_frames


# ─────────────────────────────────────────────
# COMPUTE METRICS
# ─────────────────────────────────────────────
def compute_metrics(trades):
    """Compute Sharpe, win rate, avg return, t-test."""
    if len(trades) < 5:
        return None

    returns = np.array([t['return'] for t in trades])
    n = len(returns)
    mean_ret = returns.mean()
    std_ret  = returns.std(ddof=1) if n > 1 else 1e-9

    avg_hold = np.mean([(t['exit_date'] - t['entry_date']).days for t in trades])
    trades_per_year = 252 / max(avg_hold, 1)
    sharpe = (mean_ret / (std_ret + 1e-9)) * math.sqrt(trades_per_year)

    win_rate = (returns > 0).mean()
    t_stat, p_value = stats.ttest_1samp(returns, 0)

    return {
        'n_trades': n,
        'sharpe': round(float(sharpe), 4),
        'win_rate': round(float(win_rate), 4),
        'avg_return': round(float(mean_ret), 5),
        'std_return': round(float(std_ret), 5),
        't_stat': round(float(t_stat), 4),
        'p_value': round(float(p_value), 4)
    }


# ─────────────────────────────────────────────
# VARIANT BACKTESTS
# ─────────────────────────────────────────────

def backtest_baseline(ticker_frames):
    """
    Variant 1: Standard gap PEAD, enter day 0 (next open), hold 20d.
    No text filter. Reproduces prior result for comparison.
    """
    trades = []
    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            if in_trade_until is not None and date <= in_trade_until:
                continue
            row = df.loc[date]
            if row['gap'] < GAP_THRESHOLD:
                continue

            entry_idx = i + 1
            exit_idx  = i + 1 + HOLD_PERIOD
            if entry_idx >= len(dates) or exit_idx >= len(dates):
                continue

            entry_date  = dates[entry_idx]
            exit_date   = dates[exit_idx]
            entry_price = df.loc[entry_date, 'open']
            exit_price  = df.loc[exit_date, 'open']

            if entry_price <= 0 or exit_price <= 0:
                continue

            raw_return = exit_price / entry_price - 1
            trades.append({
                'ticker': ticker,
                'gap_date': date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'gap': float(row['gap']),
                'return': float(raw_return),
                'text_surprise': None,
                'text_source': 'none',
                'size': 1.0,
                'variant': 'baseline'
            })
            in_trade_until = exit_date
    return trades


def _collect_text_stats(trades_with_source):
    """Summarize text source distribution."""
    source_counts = defaultdict(int)
    for t in trades_with_source:
        source_counts[t.get('text_source', 'none')] += 1
    return dict(source_counts)


def backtest_text_filter(ticker_frames, eps_lookup, news_lookup):
    """
    Variant 2: Text filter — skip negatives, enter day 0.
    text_surprise < 0: skip
    text_surprise >= 0: enter full size
    """
    trades = []
    total_signals = 0
    signals_with_real_text = 0

    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            if in_trade_until is not None and date <= in_trade_until:
                continue
            row = df.loc[date]
            if row['gap'] < GAP_THRESHOLD:
                continue
            total_signals += 1

            text_surprise, source = get_text_surprise(ticker, date, eps_lookup, news_lookup)
            if source != 'neutral':
                signals_with_real_text += 1

            # Skip negatives
            if text_surprise < 0:
                continue

            entry_idx = i + 1
            exit_idx  = i + 1 + HOLD_PERIOD
            if entry_idx >= len(dates) or exit_idx >= len(dates):
                continue

            entry_date  = dates[entry_idx]
            exit_date   = dates[exit_idx]
            entry_price = df.loc[entry_date, 'open']
            exit_price  = df.loc[exit_date, 'open']

            if entry_price <= 0 or exit_price <= 0:
                continue

            raw_return = exit_price / entry_price - 1
            trades.append({
                'ticker': ticker,
                'gap_date': date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'gap': float(row['gap']),
                'return': float(raw_return),
                'text_surprise': float(text_surprise),
                'text_source': source,
                'size': 1.0,
                'variant': 'text_filter'
            })
            in_trade_until = exit_date

    pct = signals_with_real_text / max(total_signals, 1) * 100
    print(f"    Text filter: {total_signals} signals, {signals_with_real_text} with real text ({pct:.1f}%)")
    return trades, total_signals, signals_with_real_text


def backtest_text_confirm(ticker_frames, eps_lookup, news_lookup):
    """
    Variant 3: FinBERT/EPS + 3-day confirmation.
    Enter on DAY 3 (not day 0).

    Strong: text_surprise > 0.3 AND 3d return > 0: full size (1.0), 20d hold
    Conflicted: text_surprise > 0.3 BUT 3d return < -1%: skip
    Weak text: 0 to 0.3: half size (0.5)
    Negative text: < 0: skip entirely
    """
    trades = []
    total_signals = 0
    signals_with_real_text = 0

    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            if in_trade_until is not None and date <= in_trade_until:
                continue
            row = df.loc[date]
            if row['gap'] < GAP_THRESHOLD:
                continue
            total_signals += 1

            text_surprise, source = get_text_surprise(ticker, date, eps_lookup, news_lookup)
            if source != 'neutral':
                signals_with_real_text += 1

            # Negative text: skip entirely
            if text_surprise < 0:
                continue

            # Entry is DAY 3 confirmation
            entry_idx = i + CONFIRM_DAYS
            exit_idx  = i + CONFIRM_DAYS + HOLD_PERIOD
            if entry_idx >= len(dates) or exit_idx >= len(dates):
                continue

            entry_date     = dates[entry_idx]
            exit_date      = dates[exit_idx]
            gap_day_close  = df.loc[date, 'close']
            entry_price    = df.loc[entry_date, 'open']
            exit_price     = df.loc[exit_date, 'open']

            if gap_day_close <= 0 or entry_price <= 0 or exit_price <= 0:
                continue

            three_day_ret = entry_price / gap_day_close - 1

            # Apply confirmation rules
            if text_surprise > 0.3:
                if three_day_ret < -0.01:
                    # Conflicted: skip
                    continue
                size = 1.0  # strong signal
            else:  # 0 to 0.3: weak text
                size = 0.5

            raw_return = exit_price / entry_price - 1
            trades.append({
                'ticker': ticker,
                'gap_date': date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'gap': float(row['gap']),
                'three_day_ret': float(three_day_ret),
                'return': float(raw_return * size),  # size-adjusted return
                'text_surprise': float(text_surprise),
                'text_source': source,
                'size': float(size),
                'variant': 'text_confirm'
            })
            in_trade_until = exit_date

    pct = signals_with_real_text / max(total_signals, 1) * 100
    print(f"    Text+3d confirm: {total_signals} signals, {signals_with_real_text} with real text ({pct:.1f}%)")
    return trades, total_signals, signals_with_real_text


def backtest_text_weighted(ticker_frames, eps_lookup, news_lookup):
    """
    Variant 4: Position size proportional to text_surprise score.
    size = clamp(text_surprise + 0.5, 0.1, 1.0)
    Enter day 0. Skip negatives.
    """
    trades = []
    total_signals = 0
    signals_with_real_text = 0

    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            if in_trade_until is not None and date <= in_trade_until:
                continue
            row = df.loc[date]
            if row['gap'] < GAP_THRESHOLD:
                continue
            total_signals += 1

            text_surprise, source = get_text_surprise(ticker, date, eps_lookup, news_lookup)
            if source != 'neutral':
                signals_with_real_text += 1

            # Skip negative
            if text_surprise < 0:
                continue

            # Proportional sizing
            size = max(0.1, min(1.0, text_surprise + 0.5))

            entry_idx = i + 1
            exit_idx  = i + 1 + HOLD_PERIOD
            if entry_idx >= len(dates) or exit_idx >= len(dates):
                continue

            entry_date  = dates[entry_idx]
            exit_date   = dates[exit_idx]
            entry_price = df.loc[entry_date, 'open']
            exit_price  = df.loc[exit_date, 'open']

            if entry_price <= 0 or exit_price <= 0:
                continue

            raw_return = exit_price / entry_price - 1
            trades.append({
                'ticker': ticker,
                'gap_date': date,
                'entry_date': entry_date,
                'exit_date': exit_date,
                'gap': float(row['gap']),
                'return': float(raw_return * size),
                'text_surprise': float(text_surprise),
                'text_source': source,
                'size': float(size),
                'variant': 'text_weighted'
            })
            in_trade_until = exit_date

    pct = signals_with_real_text / max(total_signals, 1) * 100
    print(f"    Text weighted: {total_signals} signals, {signals_with_real_text} with real text ({pct:.1f}%)")
    return trades, total_signals, signals_with_real_text


# ─────────────────────────────────────────────
# YEAR-BY-YEAR ANALYSIS
# ─────────────────────────────────────────────
def year_breakdown(trades):
    result = {}
    for year in range(2020, 2026):
        yt = [t for t in trades if t['entry_date'].year == year]
        m = compute_metrics(yt)
        result[str(year)] = m
    return result


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 65)
    print("R31: Text-Based PEAD with FinBERT Sentiment + EPS Proxy")
    print("=" * 65)

    # 1. Load FinBERT
    print("\n[1] Loading text scoring model...")
    finbert_ok = try_load_finbert()
    print(f"  Headline text method: {TEXT_METHOD}")

    # 2. Price data
    print("\n[2] Loading price data...")
    data = fetch_price_data(UNIVERSE, START_DATE, END_DATE)
    tickers_available = [
        t for t in UNIVERSE
        if t in data['Close'].columns and data['Close'][t].dropna().shape[0] > 200
    ]
    print(f"  Available tickers: {len(tickers_available)}")

    # 3. EPS surprise data (primary text proxy)
    print("\n[3] Loading EPS surprise data (primary text proxy)...")
    eps_lookup = load_eps_surprise_lookup()
    tickers_with_eps = sum(1 for t in tickers_available if t in eps_lookup and eps_lookup[t])
    total_eps_dates = sum(len(v) for t, v in eps_lookup.items() if t in tickers_available)
    print(f"  Tickers with EPS data: {tickers_with_eps}/{len(tickers_available)}")
    print(f"  Total EPS data points: {total_eps_dates}")

    # 4. News headlines (secondary, recent only)
    print("\n[4] Fetching recent news headlines (secondary)...")
    news_lookup = build_news_lookup(tickers_available)
    total_news = sum(len(v) for v in news_lookup.values())
    tickers_with_news = sum(1 for v in news_lookup.values() if len(v) > 0)
    print(f"  Total headlines: {total_news}, tickers with news: {tickers_with_news}/{len(tickers_available)}")

    # 5. Compute gap signals
    print("\n[5] Computing gap signals...")
    ticker_frames = compute_gap_signals(data, tickers_available)
    for ticker, df in ticker_frames.items():
        df.attrs['ticker'] = ticker

    total_gaps = sum((df['gap'] >= GAP_THRESHOLD).sum() for df in ticker_frames.values())
    print(f"  Total {GAP_THRESHOLD*100:.0f}%+ gap-up signals: {total_gaps}")

    # Quick test of text signal coverage
    sample_ticker = 'AAPL'
    sample_gaps = ticker_frames.get(sample_ticker, pd.DataFrame())
    if len(sample_gaps) > 0:
        gap_dates = sample_gaps[sample_gaps['gap'] >= GAP_THRESHOLD].index.tolist()
        eps_hits = sum(
            1 for d in gap_dates
            if get_eps_surprise_near_date(eps_lookup, sample_ticker, d, window_days=5) is not None
        )
        print(f"  {sample_ticker} gap events: {len(gap_dates)}, EPS matches: {eps_hits}")

    # 6. Run all variants
    print("\n[6] Running strategy variants...")

    print("\n  --- Variant 1: Baseline (no text filter) ---")
    v1_trades = backtest_baseline(ticker_frames)
    v1_metrics = compute_metrics(v1_trades)
    print(f"    Trades: {len(v1_trades)}, Sharpe: {v1_metrics['sharpe'] if v1_metrics else 'N/A'}")

    print("\n  --- Variant 2: Text Filter (skip negatives, enter day 0) ---")
    v2_trades, v2_total, v2_with_text = backtest_text_filter(ticker_frames, eps_lookup, news_lookup)
    v2_metrics = compute_metrics(v2_trades)
    print(f"    Trades: {len(v2_trades)}, Sharpe: {v2_metrics['sharpe'] if v2_metrics else 'N/A'}")

    print("\n  --- Variant 3: Text + 3-Day Confirmation ---")
    v3_trades, v3_total, v3_with_text = backtest_text_confirm(ticker_frames, eps_lookup, news_lookup)
    v3_metrics = compute_metrics(v3_trades)
    print(f"    Trades: {len(v3_trades)}, Sharpe: {v3_metrics['sharpe'] if v3_metrics else 'N/A'}")

    print("\n  --- Variant 4: Text Score Weighted ---")
    v4_trades, v4_total, v4_with_text = backtest_text_weighted(ticker_frames, eps_lookup, news_lookup)
    v4_metrics = compute_metrics(v4_trades)
    print(f"    Trades: {len(v4_trades)}, Sharpe: {v4_metrics['sharpe'] if v4_metrics else 'N/A'}")

    # 7. Year-by-year for V3
    print("\n[7] Year-by-year breakdown (Variant 3)...")
    v3_yearly = year_breakdown(v3_trades) if v3_trades else {}
    for yr, ym in v3_yearly.items():
        if ym:
            print(f"  {yr}: Sharpe={ym['sharpe']:.3f} N={ym['n_trades']} WR={ym['win_rate']:.2%}")

    # 8. Text source distribution
    v2_sources = _collect_text_stats(v2_trades)
    v3_sources = _collect_text_stats(v3_trades)
    print(f"\n  Text sources V2: {v2_sources}")
    print(f"  Text sources V3: {v3_sources}")

    # 9. Coverage stats
    pct_text_v2 = v2_with_text / max(v2_total, 1) * 100
    pct_text_v3 = v3_with_text / max(v3_total, 1) * 100
    pct_text_v4 = v4_with_text / max(v4_total, 1) * 100

    # 10. Assemble results
    variants = [
        {
            'variant': '1_baseline',
            'description': 'Standard gap PEAD, enter day 0, hold 20d (no text)',
            'metrics': v1_metrics,
            'n_trades': len(v1_trades),
        },
        {
            'variant': '2_text_filter',
            'description': 'EPS/FinBERT filter, skip negatives, enter day 0',
            'metrics': v2_metrics,
            'n_trades': len(v2_trades),
            'signals_total': v2_total,
            'signals_with_text': v2_with_text,
            'pct_with_text': round(pct_text_v2, 1),
            'text_sources': v2_sources,
        },
        {
            'variant': '3_text_3d_confirm',
            'description': 'EPS/FinBERT filter + 3-day confirmation, enter day 3',
            'metrics': v3_metrics,
            'n_trades': len(v3_trades),
            'signals_total': v3_total,
            'signals_with_text': v3_with_text,
            'pct_with_text': round(pct_text_v3, 1),
            'text_sources': v3_sources,
            'year_by_year': v3_yearly,
        },
        {
            'variant': '4_text_weighted',
            'description': 'Position size proportional to text_surprise score',
            'metrics': v4_metrics,
            'n_trades': len(v4_trades),
            'signals_total': v4_total,
            'signals_with_text': v4_with_text,
            'pct_with_text': round(pct_text_v4, 1),
        },
    ]

    baseline_sharpe = v1_metrics['sharpe'] if v1_metrics else None

    output = {
        'category': 'r31_text_pead',
        'run_date': datetime.now().isoformat(),
        'universe_size': len(tickers_available),
        'date_range': f'{START_DATE} to {END_DATE}',
        'gap_threshold': GAP_THRESHOLD,
        'hold_period': HOLD_PERIOD,
        'confirm_days': CONFIRM_DAYS,
        'text_method_headlines': TEXT_METHOD,
        'text_method_primary': 'eps_surprise_tanh',
        'total_gap_signals': int(total_gaps),
        'total_news_headlines': total_news,
        'tickers_with_eps_data': tickers_with_eps,
        'tickers_with_news': tickers_with_news,
        'total_eps_data_points': total_eps_dates,
        'baseline_sharpe': baseline_sharpe,
        'prior_best_sharpe': 2.394,
        'variants': variants,
    }

    out_path = os.path.join(ROUNDS_DIR, 'r31_text_pead_results.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    # Summary table
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"  Prior best PEAD Sharpe (R30/baseline): 2.394")
    print(f"  Headline text method: {TEXT_METHOD}")
    print(f"  Primary text method:  EPS surprise (tanh-normalized)")
    print()
    print(f"{'Variant':<38} {'Sharpe':>8} {'N':>6} {'WR':>8} {'p-val':>8}")
    print("-" * 70)
    for v in variants:
        m = v['metrics']
        if m:
            print(f"{v['variant']:<38} {m['sharpe']:>8.4f} {m['n_trades']:>6} "
                  f"{m['win_rate']:>8.2%} {m['p_value']:>8.4f}")
        else:
            print(f"{v['variant']:<38} {'N/A':>8} {'<5':>6}")

    return output


if __name__ == '__main__':
    result = main()
    print("\nDone.")
