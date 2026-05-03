"""
R28: TradingAgents-style Multi-Agent PEAD Overlay
EarningsQualityAgent (statistical proxy) filter on top of PEAD gap signal strategy.

Phase 1: Statistical proxy (LLM API unavailable - 401 auth error)
Phase 2 (future): Replace quality_score with actual FinBERT/LLM calls once auth restored.
"""

import sys
sys.path.insert(0, '/workspace/group/robinhood-advisor/venv/lib/python3.11/site-packages')

import json
import os
import warnings
import numpy as np
import pandas as pd
from scipy import stats
from datetime import datetime, timedelta
import time

warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────
# UNIVERSE & CONFIG
# ─────────────────────────────────────────────
UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA',
    'JPM', 'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'KO',
    'XOM', 'CVX', 'BAC', 'WMT', 'MRK',
    'COST', 'NFLX', 'QCOM', 'TXN', 'GE',
    'LMT', 'GS', 'ADBE', 'CRM', 'HON'
]

START_DATE = '2020-01-01'
END_DATE   = '2025-12-31'

GAP_THRESHOLD = 0.05   # 5% minimum gap
HOLD_PERIOD   = 20     # 20-day hold
MAX_POSITIONS = 15     # max concurrent positions

CACHE_DIR = '/workspace/group/trading_eval/cache'
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs('/workspace/group/trading_eval/rounds', exist_ok=True)


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────
def fetch_price_data(tickers, start, end, retries=3):
    """Download OHLCV data for all tickers with caching."""
    import yfinance as yf

    cache_file = os.path.join(CACHE_DIR, f'pead_universe_{start}_{end}.pkl')
    if os.path.exists(cache_file):
        print(f"  Loading price data from cache: {cache_file}")
        return pd.read_pickle(cache_file)

    all_data = {}
    for ticker in tickers:
        for attempt in range(retries):
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
                time.sleep(0.3)
            except Exception as e:
                print(f"  {ticker} attempt {attempt+1} failed: {e}")
                time.sleep(1)

    combined = {}
    for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
        combined[col] = pd.DataFrame({t: all_data[t][col] for t in all_data if col in all_data[t].columns})

    result = pd.concat({col: combined[col] for col in combined}, axis=1)
    result.to_pickle(cache_file)
    print(f"  Saved cache: {cache_file}")
    return result


def fetch_vix_data(start, end):
    """Fetch VIX data for RegimeGuard."""
    import yfinance as yf
    cache_file = os.path.join(CACHE_DIR, f'vix_{start}_{end}.pkl')
    if os.path.exists(cache_file):
        df = pd.read_pickle(cache_file)
        print(f"  VIX loaded from cache")
        return df
    try:
        vix = yf.download('^VIX', start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        vix.index = pd.to_datetime(vix.index)
        vix.to_pickle(cache_file)
        print(f"  VIX downloaded: {len(vix)} rows")
        return vix
    except Exception as e:
        print(f"  VIX fetch failed: {e}")
        return None


def fetch_spy_data(start, end):
    """Fetch SPY data for RegimeGuard (50d/200d SMA cross)."""
    import yfinance as yf
    cache_file = os.path.join(CACHE_DIR, f'spy_{start}_{end}.pkl')
    if os.path.exists(cache_file):
        df = pd.read_pickle(cache_file)
        print(f"  SPY loaded from cache")
        return df
    try:
        spy = yf.download('SPY', start=start, end=end, auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        spy.index = pd.to_datetime(spy.index)
        spy.to_pickle(cache_file)
        print(f"  SPY downloaded: {len(spy)} rows")
        return spy
    except Exception as e:
        print(f"  SPY fetch failed: {e}")
        return None


# ─────────────────────────────────────────────
# GAP DETECTION & FEATURE COMPUTATION
# ─────────────────────────────────────────────
def compute_gap_features(data, tickers):
    """
    Compute overnight gaps and all quality score features per ticker.
    Returns dict of per-ticker DataFrames.
    """
    ticker_frames = {}
    for ticker in tickers:
        try:
            close  = data['Close'][ticker].dropna()
            open_  = data['Open'][ticker].dropna()
            volume = data['Volume'][ticker].dropna()

            df = pd.DataFrame({
                'close': close,
                'open':  open_,
                'volume': volume
            }).dropna()

            df['prev_close'] = df['close'].shift(1)
            df['gap'] = df['open'] / df['prev_close'] - 1

            # 20-day avg volume
            df['vol_avg20'] = df['volume'].rolling(20).mean()
            df['vol_ratio'] = df['volume'] / df['vol_avg20']

            # 3-day forward return (for price persistence score)
            df['ret_3d'] = df['close'].shift(-3) / df['close'] - 1

            # SPY 50/200 SMA regime flags (filled in later)
            df['regime_bull'] = True  # default; overwritten below

            ticker_frames[ticker] = df.dropna(subset=['prev_close', 'gap', 'vol_avg20'])
        except Exception as e:
            print(f"  Gap compute failed for {ticker}: {e}")

    return ticker_frames


def attach_regime_data(ticker_frames, vix_df, spy_df):
    """
    Attach VIX and SPY SMA regime data to each ticker frame.
    Modifies ticker_frames in-place.
    """
    # Build VIX series
    vix_close = None
    if vix_df is not None and 'Close' in vix_df.columns:
        vix_close = vix_df['Close']

    # Build SPY regime (True = bull = 50d SMA > 200d SMA)
    spy_regime = None
    if spy_df is not None and 'Close' in spy_df.columns:
        spy_close = spy_df['Close']
        sma50  = spy_close.rolling(50).mean()
        sma200 = spy_close.rolling(200).mean()
        spy_regime = (sma50 > sma200)

    for ticker, df in ticker_frames.items():
        if vix_close is not None:
            df['vix'] = vix_close.reindex(df.index, method='ffill')
        else:
            df['vix'] = 15.0  # neutral default

        if spy_regime is not None:
            df['regime_bull'] = spy_regime.reindex(df.index, method='ffill').fillna(True)
        else:
            df['regime_bull'] = True

        ticker_frames[ticker] = df


# ─────────────────────────────────────────────
# EARNINGS QUALITY AGENT
# ─────────────────────────────────────────────
class EarningsQualityAgent:
    """
    Phase 1 statistical proxy for LLM/NLP earnings quality scoring.

    Computes quality_score (0-100) from three components:
    1. Beat Magnitude (40 pts) — EPS actual vs estimate
    2. Price Persistence (30 pts) — 3-day return after gap
    3. Volume Confirmation (30 pts) — gap-day volume vs 20d avg

    NOTE: EPS beat magnitude is approximated from gap size as a proxy
    (since yfinance historical EPS beat data is unreliable for historical dates).
    Gap size itself is a reasonable proxy for earnings beat magnitude in PEAD research.
    """

    def __init__(self):
        self.score_cache = {}

    def compute_quality_score(self, row, ticker=None):
        """
        Compute quality score for a signal row.
        row must have: gap, vol_ratio, ret_3d
        Returns (quality_score, component_dict)
        """
        gap      = float(row.get('gap', 0))
        vol_ratio = float(row.get('vol_ratio', 1.0))
        ret_3d   = float(row.get('ret_3d', 0))

        # ── Component 1: Beat Magnitude (40 pts) ──
        # Use gap magnitude as proxy for earnings beat magnitude
        # (large positive gap on earnings day = strong beat proxy)
        abs_gap = abs(gap)
        if abs_gap > 0.10:      # >10% gap = very strong beat
            beat_score = 40
        elif abs_gap > 0.05:    # 5-10%
            beat_score = 25
        elif abs_gap > 0.02:    # 2-5%
            beat_score = 15
        else:
            beat_score = 0

        # ── Component 2: Price Persistence (30 pts) ──
        # 3-day return after gap day (same direction as gap)
        if gap > 0:
            persistence = ret_3d
        else:
            persistence = -ret_3d  # for short signals

        if persistence > 0.02:
            persist_score = 30
        elif persistence >= 0:
            persist_score = 15
        else:
            persist_score = 0

        # ── Component 3: Volume Confirmation (30 pts) ──
        if vol_ratio > 2.0:
            vol_score = 30
        elif vol_ratio > 1.5:
            vol_score = 20
        elif vol_ratio > 1.0:
            vol_score = 10
        else:
            vol_score = 0

        quality_score = beat_score + persist_score + vol_score

        return quality_score, {
            'beat_score': beat_score,
            'persist_score': persist_score,
            'vol_score': vol_score,
            'abs_gap': round(abs_gap, 4),
            'vol_ratio': round(vol_ratio, 3),
            'ret_3d': round(ret_3d, 4)
        }

    def check_veto(self, row):
        """
        Returns (vetoed: bool, reason: str)
        VETO if:
        - VIX > 30 on entry day (RegimeGuard)
        """
        vix = float(row.get('vix', 15.0))
        if vix > 30:
            return True, f"VIX={vix:.1f}>30"
        return False, ""

    def size_multiplier(self, row, quality_score, variant):
        """
        Compute position size multiplier based on variant and regime.
        Returns multiplier (float).
        """
        regime_bull = bool(row.get('regime_bull', True))
        vol_ratio   = float(row.get('vol_ratio', 1.0))
        abs_gap     = abs(float(row.get('gap', 0)))
        vix         = float(row.get('vix', 15.0))

        base = 1.0

        # Bear regime: reduce 50%
        if not regime_bull:
            base *= 0.5

        # Variant-specific sizing
        if variant == 'baseline':
            mult = base

        elif variant == 'hard_filter':
            # Only called when quality_score >= 50, equal weight
            mult = base

        elif variant == 'soft_filter':
            # Scale by quality_score/100
            mult = base * (quality_score / 100.0)

        elif variant == 'full':
            # Hard filter (>=50) + NOR amplifier + RegimeGuard
            mult = base
            # NOR amplifier: vol > 3x AND beat > 10%
            if vol_ratio > 3.0 and abs_gap > 0.10:
                mult *= 1.25

        elif variant == 'full_vix_kelly':
            # Full + VIX-based Kelly reduction
            mult = base
            if vol_ratio > 3.0 and abs_gap > 0.10:
                mult *= 1.25
            # VIX Kelly: reduce size as VIX rises above 20
            if vix > 20:
                kelly_reduction = max(0.3, 1.0 - (vix - 20) / 40.0)
                mult *= kelly_reduction
        else:
            mult = base

        return max(0.05, mult)  # floor at 5%


# ─────────────────────────────────────────────
# SIGNAL GENERATION WITH QUALITY FILTER
# ─────────────────────────────────────────────
def generate_signals(ticker_frames, threshold, variant, qa_agent):
    """
    Generate trading signals for a given variant.
    Returns list of signal dicts with quality scores.
    """
    all_signals = []

    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            row = df.loc[date]

            # Skip if in existing trade
            if in_trade_until is not None and date <= in_trade_until:
                continue

            gap = float(row['gap'])

            # Only long gaps (upside PEAD)
            if gap < threshold:
                continue

            # Compute quality score
            quality_score, components = qa_agent.compute_quality_score(row, ticker)

            # ── VETO checks ──
            vetoed, veto_reason = qa_agent.check_veto(row)
            if vetoed:
                all_signals.append({
                    'ticker': ticker,
                    'gap_date': date,
                    'gap': gap,
                    'quality_score': quality_score,
                    'components': components,
                    'status': 'vetoed',
                    'veto_reason': veto_reason,
                    'variant_included': False
                })
                continue

            # ── Variant filter logic ──
            included = True
            if variant in ('hard_filter', 'full', 'full_vix_kelly'):
                if quality_score < 50:
                    included = False

            # Size multiplier
            size_mult = qa_agent.size_multiplier(row, quality_score, variant)

            # Entry/Exit indices
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

            raw_return  = exit_price / entry_price - 1
            trade_return = raw_return  # long only

            sig = {
                'ticker':         ticker,
                'gap_date':       date,
                'entry_date':     entry_date,
                'exit_date':      exit_date,
                'gap':            gap,
                'quality_score':  quality_score,
                'components':     components,
                'size_mult':      size_mult,
                'entry_price':    entry_price,
                'exit_price':     exit_price,
                'return':         trade_return,
                'status':         'included' if included else 'filtered',
                'veto_reason':    '',
                'variant_included': included
            }
            all_signals.append(sig)

            if included:
                in_trade_until = exit_date

    return all_signals


# ─────────────────────────────────────────────
# PORTFOLIO SIMULATION
# ─────────────────────────────────────────────
def simulate_portfolio(all_signals, max_positions=15):
    """
    Simulate portfolio from list of signals.
    Uses size_mult for weighted allocation.
    Returns metrics dict.
    """
    # Only use variant_included signals
    active_signals = [s for s in all_signals if s.get('variant_included', False)]

    if len(active_signals) < 10:
        return None

    # Sort by entry date
    active_signals.sort(key=lambda x: x['entry_date'])

    completed = []
    active    = []  # currently active trades

    for sig in active_signals:
        entry = sig['entry_date']
        # Remove expired
        active = [a for a in active if a['exit_date'] > entry]

        if len(active) >= max_positions:
            continue

        active.append(sig)
        completed.append(sig)

    if not completed:
        return None

    # Build daily returns
    port_returns = []
    for t in completed:
        hold_days = max((t['exit_date'] - t['entry_date']).days, 1)
        daily_r = (t['return'] * t['size_mult']) / hold_days
        dates = pd.date_range(t['entry_date'],
                              t['exit_date'] - timedelta(days=1), freq='B')
        for d in dates:
            port_returns.append({'date': d, 'weighted_return': daily_r, 'weight': t['size_mult']})

    port_df = pd.DataFrame(port_returns)

    # Equal-weighted daily return (mean of position returns)
    daily_weighted = port_df.groupby('date')['weighted_return'].mean()

    ann_return = daily_weighted.mean() * 252
    ann_vol    = daily_weighted.std() * np.sqrt(252)
    sharpe     = ann_return / (ann_vol + 1e-9)

    # Max drawdown
    equity = (1 + daily_weighted).cumprod()
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = float(drawdown.min())

    # CAGR
    total_days = (daily_weighted.index[-1] - daily_weighted.index[0]).days
    total_return = float(equity.iloc[-1] - 1)
    years = total_days / 365.25
    cagr = (1 + total_return) ** (1 / max(years, 0.1)) - 1

    # Win rate
    trade_returns = [t['return'] for t in completed]
    win_rate = np.mean([r > 0 for r in trade_returns])

    returns_arr = daily_weighted.values
    t_stat, p_val = stats.ttest_1samp(returns_arr, 0)

    return {
        'n_signals_total':    len(all_signals),
        'n_signals_included': len(active_signals),
        'n_trades':           len(completed),
        'pct_filtered':       round(100 * (1 - len(active_signals) / max(len(all_signals), 1)), 1),
        'sharpe':             round(float(sharpe), 4),
        'ann_return':         round(float(ann_return), 4),
        'ann_vol':            round(float(ann_vol), 4),
        'cagr':               round(float(cagr), 4),
        'max_dd':             round(float(max_dd), 4),
        'win_rate':           round(float(win_rate), 4),
        't_stat':             round(float(t_stat), 4),
        'p_value':            round(float(p_val), 4),
    }


# ─────────────────────────────────────────────
# BASELINE PORTFOLIO (reproduces prior result)
# ─────────────────────────────────────────────
def baseline_portfolio(ticker_frames, threshold, hold_period, max_positions=15):
    """
    Pure PEAD baseline — no quality filter, equal weight.
    Direct port from pead_harness.py logic.
    """
    all_trades = []

    for ticker, df in ticker_frames.items():
        dates = df.index.tolist()
        in_trade_until = None

        for i, date in enumerate(dates):
            row = df.loc[date]
            if in_trade_until is not None and date <= in_trade_until:
                continue

            gap = float(row['gap'])
            if gap < threshold:
                continue

            entry_idx = i + 1
            exit_idx  = i + 1 + hold_period

            if entry_idx >= len(dates) or exit_idx >= len(dates):
                continue

            entry_date  = dates[entry_idx]
            exit_date   = dates[exit_idx]
            entry_price = df.loc[entry_date, 'open']
            exit_price  = df.loc[exit_date, 'open']

            if entry_price <= 0 or exit_price <= 0:
                continue

            trade_return = exit_price / entry_price - 1

            all_trades.append({
                'ticker':       ticker,
                'gap_date':     date,
                'entry_date':   entry_date,
                'exit_date':    exit_date,
                'gap':          gap,
                'return':       trade_return,
                'size_mult':    1.0,
                'variant_included': True
            })
            in_trade_until = exit_date

    return simulate_portfolio(all_trades, max_positions)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 70)
    print("R28: TradingAgents PEAD EarningsQualityAgent Overlay")
    print("Phase 1 — Statistical Proxy (LLM API unavailable)")
    print("=" * 70)

    # 1. Fetch data
    print("\n[1] Loading price data...")
    data = fetch_price_data(UNIVERSE, START_DATE, END_DATE)
    tickers_available = [t for t in UNIVERSE if t in data['Close'].columns
                         and data['Close'][t].dropna().shape[0] > 200]
    print(f"  Available tickers: {len(tickers_available)}")

    print("\n[2] Loading regime data (VIX, SPY)...")
    vix_df = fetch_vix_data(START_DATE, END_DATE)
    spy_df = fetch_spy_data(START_DATE, END_DATE)

    # 2. Compute gap features
    print("\n[3] Computing gap features...")
    ticker_frames = compute_gap_features(data, tickers_available)
    attach_regime_data(ticker_frames, vix_df, spy_df)
    print(f"  Processed {len(ticker_frames)} tickers")

    # 3. Initialize quality agent
    qa_agent = EarningsQualityAgent()

    # 4. Run all variants
    print("\n[4] Running strategy variants...")
    results = {}

    # ── Variant 1: Baseline PEAD ──
    print("\n  [V1] Baseline PEAD (no filter, equal weight)...")
    v1 = baseline_portfolio(ticker_frames, GAP_THRESHOLD, HOLD_PERIOD, MAX_POSITIONS)
    results['baseline'] = v1
    if v1:
        print(f"       Sharpe={v1['sharpe']:.4f}  CAGR={v1['cagr']:.2%}  "
              f"MaxDD={v1['max_dd']:.2%}  N={v1['n_trades']}")

    # ── Variant 2: R28 Hard Filter (quality >= 50) ──
    print("\n  [V2] R28 Hard Filter (quality_score >= 50)...")
    sigs_hard = generate_signals(ticker_frames, GAP_THRESHOLD, 'hard_filter', qa_agent)
    v2 = simulate_portfolio(sigs_hard, MAX_POSITIONS)
    results['hard_filter'] = v2
    if v2:
        print(f"       Sharpe={v2['sharpe']:.4f}  CAGR={v2['cagr']:.2%}  "
              f"MaxDD={v2['max_dd']:.2%}  N={v2['n_trades']}  "
              f"Filtered={v2['pct_filtered']:.1f}%")

    # ── Variant 3: R28 Soft Filter (scale by quality/100) ──
    print("\n  [V3] R28 Soft Filter (scale position by quality_score/100)...")
    sigs_soft = generate_signals(ticker_frames, GAP_THRESHOLD, 'soft_filter', qa_agent)
    v3 = simulate_portfolio(sigs_soft, MAX_POSITIONS)
    results['soft_filter'] = v3
    if v3:
        print(f"       Sharpe={v3['sharpe']:.4f}  CAGR={v3['cagr']:.2%}  "
              f"MaxDD={v3['max_dd']:.2%}  N={v3['n_trades']}  "
              f"Filtered={v3['pct_filtered']:.1f}%")

    # ── Variant 4: R28 Full (hard filter + NOR amplifier + RegimeGuard) ──
    print("\n  [V4] R28 Full (hard filter + NOR + RegimeGuard)...")
    sigs_full = generate_signals(ticker_frames, GAP_THRESHOLD, 'full', qa_agent)
    v4 = simulate_portfolio(sigs_full, MAX_POSITIONS)
    results['full'] = v4
    if v4:
        print(f"       Sharpe={v4['sharpe']:.4f}  CAGR={v4['cagr']:.2%}  "
              f"MaxDD={v4['max_dd']:.2%}  N={v4['n_trades']}  "
              f"Filtered={v4['pct_filtered']:.1f}%")

    # ── Variant 5: R28 Full + VIX Kelly ──
    print("\n  [V5] R28 Full + VIX Kelly sizing...")
    sigs_vk = generate_signals(ticker_frames, GAP_THRESHOLD, 'full_vix_kelly', qa_agent)
    v5 = simulate_portfolio(sigs_vk, MAX_POSITIONS)
    results['full_vix_kelly'] = v5
    if v5:
        print(f"       Sharpe={v5['sharpe']:.4f}  CAGR={v5['cagr']:.2%}  "
              f"MaxDD={v5['max_dd']:.2%}  N={v5['n_trades']}  "
              f"Filtered={v5['pct_filtered']:.1f}%")

    # 5. Signal analysis
    print("\n[5] Signal quality analysis...")
    # Use soft filter signals for analysis (all signals present)
    all_sigs = sigs_soft  # all signals with quality scores computed

    total_sigs    = len([s for s in all_sigs if s.get('return') is not None])
    vetoed_sigs   = len([s for s in all_sigs if s['status'] == 'vetoed'])
    q50_plus      = len([s for s in all_sigs if s.get('quality_score', 0) >= 50 and s.get('return') is not None])
    q70_plus      = len([s for s in all_sigs if s.get('quality_score', 0) >= 70 and s.get('return') is not None])

    qs_by_decile = {}
    for q_min in range(0, 100, 10):
        q_max = q_min + 10
        sigs_in_decile = [s for s in all_sigs
                          if q_min <= s.get('quality_score', 0) < q_max
                          and s.get('return') is not None]
        if sigs_in_decile:
            avg_ret = np.mean([s['return'] for s in sigs_in_decile])
            qs_by_decile[f'{q_min}-{q_max}'] = {
                'n': len(sigs_in_decile),
                'avg_return': round(float(avg_ret), 4)
            }

    print(f"  Total gap signals:    {total_sigs}")
    print(f"  Vetoed (VIX>30):      {vetoed_sigs}")
    print(f"  Quality score >= 50:  {q50_plus} ({100*q50_plus/max(total_sigs,1):.1f}%)")
    print(f"  Quality score >= 70:  {q70_plus} ({100*q70_plus/max(total_sigs,1):.1f}%)")
    print(f"\n  Return by quality decile:")
    for decile, stats_d in qs_by_decile.items():
        print(f"    {decile}: N={stats_d['n']:3d}  AvgRet={stats_d['avg_return']:+.2%}")

    # 6. Best variant
    valid_results = {k: v for k, v in results.items() if v is not None}
    best_variant  = max(valid_results, key=lambda k: valid_results[k]['sharpe'])
    best_result   = valid_results[best_variant]
    baseline_sharpe = results['baseline']['sharpe'] if results['baseline'] else 0.0

    print(f"\n[6] Best variant: {best_variant}")
    print(f"    Sharpe={best_result['sharpe']:.4f}  (Baseline={baseline_sharpe:.4f})")
    improved = best_result['sharpe'] > 2.394
    print(f"    Beats prior best (2.394)? {'YES' if improved else 'NO'}")

    # 7. Save results
    output = {
        'round': 'R28',
        'strategy': 'PEAD EarningsQualityAgent Overlay',
        'phase': 'Phase 1 — Statistical Proxy',
        'note': 'LLM API unavailable (401). Using gap/volume/persistence as quality proxies.',
        'run_date': datetime.now().isoformat(),
        'config': {
            'universe': UNIVERSE,
            'gap_threshold': GAP_THRESHOLD,
            'hold_period': HOLD_PERIOD,
            'max_positions': MAX_POSITIONS,
            'date_range': f'{START_DATE} to {END_DATE}'
        },
        'results': {
            'baseline':       results.get('baseline'),
            'hard_filter':    results.get('hard_filter'),
            'soft_filter':    results.get('soft_filter'),
            'full':           results.get('full'),
            'full_vix_kelly': results.get('full_vix_kelly'),
        },
        'signal_analysis': {
            'total_gap_signals':    total_sigs,
            'vetoed_vix30':         vetoed_sigs,
            'quality_ge_50_pct':    round(100 * q50_plus / max(total_sigs, 1), 1),
            'quality_ge_70_pct':    round(100 * q70_plus / max(total_sigs, 1), 1),
            'returns_by_quality_decile': qs_by_decile,
        },
        'best_variant':         best_variant,
        'best_sharpe':          best_result['sharpe'],
        'prior_best_sharpe':    2.394,
        'beats_prior_best':     improved,
        'key_finding': (
            f"Best variant '{best_variant}' achieved Sharpe {best_result['sharpe']:.4f} "
            f"({'ABOVE' if improved else 'BELOW'} prior best 2.394). "
            f"Quality filter removed {best_result.get('pct_filtered', 0):.1f}% of signals."
        )
    }

    out_path = '/workspace/group/trading_eval/rounds/r28_pead_quality_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults saved to {out_path}")

    return output


if __name__ == '__main__':
    result = main()
    print("\nDone.")
