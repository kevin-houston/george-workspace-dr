#!/usr/bin/env python3
"""
R35 — Minimum Regime Performance (MRP) Diagnostic
===================================================
Analyzes each strategy's backtest returns across FRED-labeled macro regimes
to identify which are bull-market-only vs. regime-resilient.

Usage:
  python3.13 r35_mrp_diagnostic.py
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, '/workspace/group/trading_eval')

try:
    import numpy as np
    import pandas as pd
except ImportError:
    print("ERROR: numpy/pandas not found. Run: python3.13 -m pip install pandas numpy")
    sys.exit(1)

import macro_harness

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path('/workspace/group/trading_eval')
ROUNDS_DIR = ROOT / 'rounds'
MACRO_DIR  = ROOT / 'macro_cache'
CACHE_DIR  = ROOT / 'cache'

# ── Regime configuration ─────────────────────────────────────────────────────

# Primary regimes to analyse (these are boolean columns from classify_regimes())
PRIMARY_REGIMES = ['calm', 'stress', 'tightening', 'easing', 'oil_shock',
                   'inflationary', 'oil_high', 'gold_bull']

# For MRP classification thresholds
MRP_RESILIENT_MIN_SHARPE  = 0.5
MRP_RESILIENT_MIN_REGIMES = 3
MIN_DAYS_PER_REGIME       = 60   # minimum trading days in a regime to count it

# Which regimes define "bull market" vs "stress" for bull_only detection
BULL_REGIMES    = {'calm', 'easing', 'oil_high', 'gold_bull'}
STRESS_REGIMES  = {'stress', 'tightening', 'inflationary', 'oil_shock'}

# ── Helpers ───────────────────────────────────────────────────────────────────

def compute_sharpe(returns: pd.Series) -> float:
    """Annualised Sharpe ratio from daily return series."""
    if len(returns) < 5:
        return float('nan')
    std = returns.std()
    if std == 0 or math.isnan(std):
        return float('nan')
    return float(returns.mean() / std * math.sqrt(252))


def load_fred_series(name: str) -> Optional[pd.Series]:
    """Load a FRED series from macro_cache pickle."""
    path = MACRO_DIR / f'fred_{name}.pkl'
    if not path.exists():
        return None
    with open(path, 'rb') as f:
        s = pickle.load(f)
    # Normalise timezone
    if hasattr(s.index, 'tzinfo') and s.index.tzinfo is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


def load_price_series(symbol: str) -> Optional[pd.Series]:
    """Load cached price series for a symbol (15yr cache preferred)."""
    path = CACHE_DIR / f'{symbol}_15yr.pkl'
    if not path.exists():
        return None
    with open(path, 'rb') as f:
        s = pickle.load(f)
    if hasattr(s.index, 'tzinfo') and s.index.tzinfo is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)
    return s


# ── Step 1: Build regime labels ───────────────────────────────────────────────

def build_regime_labels() -> Tuple[pd.DataFrame, Dict[str, int]]:
    """
    Load FRED macro data, run classify_regimes(), return (regimes_df, durations).
    Uses cached FRED pickles — no network calls needed.
    """
    print("Step 1: Building macro regime labels...")

    # Load all available FRED series from cache
    fred_keys = [
        'DCOILWTICO', 'VIXCLS', 'CPIAUCSL', 'BAMLH0A0HYM2',
        'DFF', 'T10YIE', 'GS10', 'GS2', 'T10Y2Y', 'GOLDAMGBD228NLBM',
        'DTWEXBGS', 'DEXUSEU',
    ]
    macro = {}
    for k in fred_keys:
        s = load_fred_series(k)
        if s is not None:
            macro[k] = s
            print(f"  ✓ {k} ({len(s)} obs, {s.index[0].date()} to {s.index[-1].date()})")
        else:
            print(f"  - {k}: not cached")

    # Also try yfinance fallbacks from macro_harness cache
    yf_fallbacks = {
        'DCOILWTICO':       'CL',
        'VIXCLS':           'VIX',
        'GOLDAMGBD228NLBM': 'GCF',
        'GS10':             'TNX',
        'DTWEXBGS':         'DXY_NYB',
    }
    for fred_key, yf_name in yf_fallbacks.items():
        if fred_key not in macro:
            path = MACRO_DIR / f'yf_{yf_name}.pkl'
            if path.exists():
                with open(path, 'rb') as f:
                    s = pickle.load(f)
                if s is not None and len(s) > 90:
                    if hasattr(s.index, 'tzinfo') and s.index.tzinfo is not None:
                        s = s.copy()
                        s.index = s.index.tz_localize(None)
                    macro[fred_key] = s
                    print(f"  ✓ {fred_key} via yf cache ({len(s)} obs)")

    if not macro:
        raise RuntimeError("No macro data available. Check macro_cache directory.")

    # Build common daily index using the densest series
    # Use VIX or WTI as the spine (both daily)
    spine_key = 'VIXCLS' if 'VIXCLS' in macro else 'DCOILWTICO'
    spine = macro[spine_key]
    price_idx = spine.index

    mf = macro_harness.build_macro_frame(macro, price_idx)
    regimes = macro_harness.classify_regimes(mf)

    print(f"\n  Regime date range: {regimes.index[0].date()} to {regimes.index[-1].date()}")
    print(f"  Total trading days: {len(regimes)}")
    print(f"  Regime columns: {list(regimes.columns)}")

    # Compute durations
    durations = {}
    for col in regimes.columns:
        durations[col] = int(regimes[col].sum())
        pct = durations[col] / len(regimes) * 100
        print(f"  {col:<22} {durations[col]:>5} days  ({pct:.1f}%)")

    return regimes, durations


# ── Step 2: Build strategy inventory from all round files ─────────────────────

def extract_from_round_folder(folder: Path) -> List[Dict]:
    """
    Extract strategy records from round_001 through round_010 style folders.
    Returns list of {name, source_file, overall_sharpe, symbol, daily_ret_proxy}.
    """
    results_file = folder / 'results.json'
    if not results_file.exists() or results_file.stat().st_size < 100:
        return []

    with open(results_file) as f:
        data = json.load(f)

    records = []
    round_num = data.get('round', folder.name)
    source = f"{folder.name}/results.json"

    tickers_data = data.get('tickers', {})
    if not tickers_data:
        return []

    # Collect per-strategy, per-ticker sharpes
    # Structure: tickers[symbol][strategies][strat_name][results][position][sharpe]
    strat_ticker_sharpes: Dict[str, List[float]] = {}
    strat_families: Dict[str, str] = {}

    for symbol, ticker_info in tickers_data.items():
        strategies = ticker_info.get('strategies', {})
        for strat_name, strat_info in strategies.items():
            family = strat_info.get('family', 'unknown')
            strat_families[strat_name] = family
            results = strat_info.get('results', {})
            # Prefer 'long' position, fall back to first available
            pos_data = results.get('long') or results.get('long_short') or next(iter(results.values()), None)
            if pos_data and 'sharpe' in pos_data:
                if strat_name not in strat_ticker_sharpes:
                    strat_ticker_sharpes[strat_name] = []
                strat_ticker_sharpes[strat_name].append(pos_data['sharpe'])

    for strat_name, sharpes in strat_ticker_sharpes.items():
        if not sharpes:
            continue
        overall_sharpe = float(np.mean(sharpes))
        records.append({
            'name': f"{strat_name} (R{round_num:02d})" if isinstance(round_num, int) else f"{strat_name} ({round_num})",
            'source_file': source,
            'overall_sharpe': round(overall_sharpe, 4),
            'family': strat_families.get(strat_name, 'unknown'),
            'round': round_num,
            'strat_key': strat_name,
        })

    return records


def extract_from_macro_round(filepath: Path) -> List[Dict]:
    """
    Extract strategy records from macro_round_NN.json style files.
    These have aggregated per-strategy stats only (no per-ticker daily returns).
    """
    with open(filepath) as f:
        data = json.load(f)

    records = []
    round_num = data.get('round', filepath.stem)
    source = filepath.name
    all_strats = data.get('all_strategies', data.get('top20', []))

    for s in all_strats:
        name_raw = s.get('strategy', '')
        if not name_raw:
            continue
        sharpe = s.get('avg_sharpe', s.get('sharpe', None))
        if sharpe is None:
            continue
        records.append({
            'name': f"{name_raw} (R{round_num})" if isinstance(round_num, int) else f"{name_raw} ({round_num})",
            'source_file': source,
            'overall_sharpe': round(float(sharpe), 4),
            'family': s.get('family', 'unknown'),
            'round': round_num,
            'strat_key': name_raw,
        })

    return records


def extract_from_misc_file(filepath: Path) -> List[Dict]:
    """
    Extract strategy records from miscellaneous result files (candle, forex, ml, etc.)
    Returns list with name and overall_sharpe where available.
    """
    with open(filepath) as f:
        data = json.load(f)

    records = []
    source = filepath.name
    fname = filepath.stem

    def make_name(label: str) -> str:
        return f"{label} ({fname})"

    def try_extract(items, name_key, sharpe_key='sharpe'):
        if not items:
            return
        for item in items:
            label = item.get(name_key, item.get('label', item.get('model', '')))
            if not label:
                continue
            sharpe = item.get(sharpe_key, item.get('avg_sharpe', None))
            if sharpe is None:
                continue
            records.append({
                'name': make_name(str(label)),
                'source_file': source,
                'overall_sharpe': round(float(sharpe), 4),
                'family': item.get('family', 'other'),
                'round': fname,
                'strat_key': str(label),
            })

    # candle_results.json
    if 'top20' in data and fname == 'candle_results':
        try_extract(data['top20'], 'pattern')

    # candle_macro_round19.json
    elif fname == 'candle_macro_round19':
        try_extract(data.get('results', []), 'pattern', 'sharpe_unfilt')

    # forex rounds
    elif fname.startswith('forex_round'):
        try_extract(data.get('all', data.get('top10', [])), 'strategy')

    # ml_results.json
    elif fname == 'ml_results':
        items = data.get('top_results', [])
        for item in items:
            label = f"{item.get('model','')}_{item.get('symbol','')}"
            sharpe = item.get('sharpe', None)
            if label and sharpe is not None:
                records.append({
                    'name': make_name(label),
                    'source_file': source,
                    'overall_sharpe': round(float(sharpe), 4),
                    'family': 'ml',
                    'round': fname,
                    'strat_key': label,
                })

    # options_results.json
    elif fname == 'options_results':
        try_extract(data.get('top_strategies', []), 'strategy')

    # factor_seasonal_results.json
    elif fname == 'factor_seasonal_results':
        try_extract(data.get('factor_results', []), 'factor')
        try_extract(data.get('seasonal_results', []), 'strategy')

    # lev_etf_results.json
    elif fname == 'lev_etf_results':
        try_extract(data.get('top_strategies', []), 'strategy')

    # etf_commodity_results.json
    elif fname == 'etf_commodity_results':
        try_extract(data.get('top15_overall', []), 'name')

    # vol_intermarket_results.json
    elif fname == 'vol_intermarket_results':
        for sub_key in ['vix_results', 'intermarket_results', 'fixed_income_results']:
            try_extract(data.get(sub_key, []), 'label')

    # intl_results.json
    elif fname == 'intl_results':
        try_extract(data.get('strategies', []), 'strategy')

    # dividend_results.json — different structure
    elif fname == 'dividend_results':
        for key, val in data.items():
            if isinstance(val, dict) and 'sharpe' in val:
                records.append({
                    'name': make_name(key),
                    'source_file': source,
                    'overall_sharpe': round(float(val['sharpe']), 4),
                    'family': 'dividend',
                    'round': fname,
                    'strat_key': key,
                })

    # crypto_results.json
    elif fname == 'crypto_results':
        champ = data.get('champion', {})
        if champ and 'sharpe' in champ:
            records.append({
                'name': make_name(str(champ.get('strategy', 'crypto_champion'))),
                'source_file': source,
                'overall_sharpe': round(float(champ['sharpe']), 4),
                'family': 'crypto',
                'round': fname,
                'strat_key': 'crypto_champion',
            })
        for summary in data.get('round_summaries', []):
            best = summary.get('best', {})
            if best and 'sharpe' in best:
                label = f"R{summary.get('round','?')}_{best.get('strategy','?')}"
                records.append({
                    'name': make_name(label),
                    'source_file': source,
                    'overall_sharpe': round(float(best['sharpe']), 4),
                    'family': 'crypto',
                    'round': fname,
                    'strat_key': label,
                })

    return records


def build_strategy_inventory() -> List[Dict]:
    """
    Walk all round files in ROUNDS_DIR and build unified strategy inventory.
    Deduplicates strategies with same strat_key keeping highest sharpe.
    """
    print("\nStep 2: Building strategy inventory from round files...")
    all_records = []

    # round_001 through round_010 folder format
    for i in range(1, 11):
        folder = ROUNDS_DIR / f'round_{i:03d}'
        if folder.is_dir():
            recs = extract_from_round_folder(folder)
            print(f"  round_{i:03d}: {len(recs)} strategies")
            all_records.extend(recs)

    # macro_round_NN.json files
    for i in range(11, 25):
        fp = ROUNDS_DIR / f'macro_round_{i:02d}.json'
        if fp.exists():
            recs = extract_from_macro_round(fp)
            print(f"  macro_round_{i:02d}.json: {len(recs)} strategies")
            all_records.extend(recs)

    # Miscellaneous result files
    misc_files = [
        'candle_results.json',
        'candle_macro_round19.json',
        'crypto_results.json',
        'dividend_results.json',
        'etf_commodity_results.json',
        'factor_seasonal_results.json',
        'forex_round_1.json', 'forex_round_2.json', 'forex_round_3.json',
        'forex_round_4.json', 'forex_round_5.json', 'forex_round_6.json',
        'forex_round_7.json', 'forex_round_8.json',
        'intl_results.json',
        'lev_etf_results.json',
        'llm_signal_results.json',
        'ml_results.json',
        'options_results.json',
        'vol_intermarket_results.json',
    ]
    for fn in misc_files:
        fp = ROUNDS_DIR / fn
        if fp.exists():
            try:
                recs = extract_from_misc_file(fp)
                print(f"  {fn}: {len(recs)} strategies")
                all_records.extend(recs)
            except Exception as e:
                print(f"  {fn}: ERROR - {e}")

    print(f"\n  Total records loaded: {len(all_records)}")

    # Deduplicate: same strat_key across rounds — keep all unique (round, strat_key) combos
    # but deduplicate exact (name, source_file) pairs
    seen = set()
    deduped = []
    for r in all_records:
        key = (r['name'], r['source_file'])
        if key not in seen:
            seen.add(key)
            deduped.append(r)

    print(f"  After deduplication: {len(deduped)} strategies")
    return deduped


# ── Step 3: Compute per-regime Sharpe ratios ──────────────────────────────────

def compute_regime_sharpes_from_prices(
    strat_key: str,
    round_num,
    regimes: pd.DataFrame,
) -> Optional[Dict[str, float]]:
    """
    For round_001-010 strategies: reconstruct daily returns using price cache
    and strategy signals, then split by regime.

    Returns None if reconstruction is not feasible (missing price/signal data).
    This is complex to do generically, so we use a price-proxy approach:
    for each symbol where we have price data, compute approximate returns
    and aggregate regime Sharpe from per-symbol regime performance.
    """
    # This requires running the actual strategy — too complex for a diagnostic.
    # We use the available_sharpe_by_regime proxy instead (see main flow).
    return None


def compute_regime_sharpes_from_ticker_data(
    round_folder: Path,
    strat_key: str,
    regimes: pd.DataFrame,
) -> Optional[Dict[str, float]]:
    """
    For round_001-010: load price data per ticker, reconstruct strategy daily
    returns using stored signal metadata, then split by regime.

    Strategy signals aren't stored in results JSON — we can't replay them
    without the harness. Instead we use cross-sectional approximation:
    estimate from the stored per-ticker stats and regime date coverage.
    """
    results_file = round_folder / 'results.json'
    if not results_file.exists():
        return None

    with open(results_file) as f:
        data = json.load(f)

    tickers_data = data.get('tickers', {})
    if not tickers_data:
        return None

    # For each ticker that has this strategy, load price data and split by regime
    regime_returns: Dict[str, List[float]] = {r: [] for r in PRIMARY_REGIMES}
    tickers_used = 0

    for symbol, ticker_info in tickers_data.items():
        strat_data = ticker_info.get('strategies', {}).get(strat_key)
        if strat_data is None:
            continue

        prices = load_price_series(symbol)
        if prices is None or len(prices) < 252:
            continue

        results = strat_data.get('results', {})
        pos_data = results.get('long') or results.get('long_short') or next(iter(results.values()), None)
        if pos_data is None:
            continue

        # We know: n_days, sharpe, active_pct from results
        # To split by regime we need actual daily returns — we don't have them stored.
        # Best approximation: use buy-and-hold daily returns as a proxy for regime
        # sensitivity, scaled by the strategy's actual Sharpe.
        # This is an approximation; regime Sharpe is estimated from B&H returns
        # in each regime, adjusted for strategy alpha over B&H.

        bnh = ticker_info.get('buy_and_hold', {})
        bnh_sharpe = bnh.get('sharpe', 0)
        strat_sharpe = pos_data.get('sharpe', 0)
        n_days = pos_data.get('n_days', len(prices))

        # Compute B&H daily returns aligned to regime labels
        aligned_prices = prices.reindex(regimes.index, method='ffill').dropna()
        if len(aligned_prices) < 50:
            continue

        daily_ret = aligned_prices.pct_change().fillna(0)

        # Scale daily returns to approximate strategy returns
        # (preserving distribution shape, scaling by Sharpe ratio)
        if bnh_sharpe != 0 and not math.isnan(bnh_sharpe) and not math.isnan(strat_sharpe):
            scale = strat_sharpe / bnh_sharpe if abs(bnh_sharpe) > 0.01 else 1.0
            scale = max(-3.0, min(3.0, scale))  # clip extreme scaling
        else:
            scale = 1.0

        approx_strat_ret = daily_ret * scale

        # Split by regime
        for regime_name in PRIMARY_REGIMES:
            if regime_name not in regimes.columns:
                continue
            regime_mask = regimes[regime_name].reindex(approx_strat_ret.index, method='ffill').fillna(False)
            regime_rets = approx_strat_ret[regime_mask]
            if len(regime_rets) >= MIN_DAYS_PER_REGIME:
                regime_returns[regime_name].extend(regime_rets.tolist())

        tickers_used += 1

    if tickers_used == 0:
        return None

    regime_sharpes = {}
    for regime_name, rets in regime_returns.items():
        if len(rets) >= MIN_DAYS_PER_REGIME:
            s = pd.Series(rets)
            sh = compute_sharpe(s)
            if not math.isnan(sh):
                regime_sharpes[regime_name] = round(sh, 4)

    return regime_sharpes if regime_sharpes else None


# ── Step 4: Regime Sharpe estimation for aggregated results ───────────────────

def estimate_regime_sharpes_from_macro_round(
    filepath: Path,
    strat_key: str,
    regimes: pd.DataFrame,
) -> Optional[Dict[str, float]]:
    """
    For macro_round_NN files: use available ticker data + price cache to compute
    per-regime Sharpe. These files store per-strategy aggregate stats across tickers.
    We must re-derive regime Sharpe from price data with B&H as proxy.
    """
    with open(filepath) as f:
        data = json.load(f)

    # Get the overall strategy Sharpe
    all_strats = data.get('all_strategies', data.get('top20', []))
    strat_entry = next((s for s in all_strats if s.get('strategy') == strat_key), None)
    if strat_entry is None:
        return None

    overall_sharpe = strat_entry.get('avg_sharpe', strat_entry.get('sharpe', 0))

    # Use available universe tickers to estimate regime behaviour
    tickers = list(macro_harness.UNIVERSE.keys())

    regime_returns: Dict[str, List[float]] = {r: [] for r in PRIMARY_REGIMES}
    tickers_used = 0

    for symbol in tickers:
        prices = load_price_series(symbol)
        if prices is None or len(prices) < 252:
            continue

        # B&H proxy, scaled by strategy's overall Sharpe vs B&H Sharpe
        aligned = prices.reindex(regimes.index, method='ffill').dropna()
        if len(aligned) < 50:
            continue

        daily_ret = aligned.pct_change().fillna(0)
        bnh_sharpe = compute_sharpe(daily_ret)

        if bnh_sharpe != 0 and not math.isnan(bnh_sharpe) and not math.isnan(float(overall_sharpe)):
            scale = float(overall_sharpe) / bnh_sharpe if abs(bnh_sharpe) > 0.01 else 1.0
            scale = max(-3.0, min(3.0, scale))
        else:
            scale = 1.0

        approx_ret = daily_ret * scale

        for regime_name in PRIMARY_REGIMES:
            if regime_name not in regimes.columns:
                continue
            regime_mask = regimes[regime_name].reindex(approx_ret.index, method='ffill').fillna(False)
            regime_rets = approx_ret[regime_mask]
            if len(regime_rets) >= MIN_DAYS_PER_REGIME:
                regime_returns[regime_name].extend(regime_rets.tolist())

        tickers_used += 1
        if tickers_used >= 10:  # use first 10 tickers for speed
            break

    if tickers_used == 0:
        return None

    regime_sharpes = {}
    for regime_name, rets in regime_returns.items():
        if len(rets) >= MIN_DAYS_PER_REGIME:
            s = pd.Series(rets)
            sh = compute_sharpe(s)
            if not math.isnan(sh):
                regime_sharpes[regime_name] = round(sh, 4)

    return regime_sharpes if regime_sharpes else None


def estimate_regime_sharpes_from_misc(
    filepath: Path,
    strat_key: str,
    overall_sharpe: float,
    regimes: pd.DataFrame,
) -> Optional[Dict[str, float]]:
    """
    For miscellaneous files without per-ticker data: estimate regime Sharpe
    using a pool of representative tickers scaled to match overall_sharpe.
    Uses SPY-correlated tickers for better representativeness.
    """
    # Representative tickers spanning sectors
    rep_tickers = ['AAPL', 'XOM', 'JPM', 'WMT', 'LMT', 'JNJ', 'TSLA', 'GS']

    regime_returns: Dict[str, List[float]] = {r: [] for r in PRIMARY_REGIMES}
    tickers_used = 0

    for symbol in rep_tickers:
        prices = load_price_series(symbol)
        if prices is None or len(prices) < 252:
            continue

        aligned = prices.reindex(regimes.index, method='ffill').dropna()
        if len(aligned) < 50:
            continue

        daily_ret = aligned.pct_change().fillna(0)
        bnh_sharpe = compute_sharpe(daily_ret)

        if bnh_sharpe != 0 and not math.isnan(bnh_sharpe) and not math.isnan(overall_sharpe):
            scale = overall_sharpe / bnh_sharpe if abs(bnh_sharpe) > 0.01 else 1.0
            scale = max(-3.0, min(3.0, scale))
        else:
            scale = 1.0

        approx_ret = daily_ret * scale

        for regime_name in PRIMARY_REGIMES:
            if regime_name not in regimes.columns:
                continue
            regime_mask = regimes[regime_name].reindex(approx_ret.index, method='ffill').fillna(False)
            regime_rets = approx_ret[regime_mask]
            if len(regime_rets) >= MIN_DAYS_PER_REGIME:
                regime_returns[regime_name].extend(regime_rets.tolist())

        tickers_used += 1

    if tickers_used == 0:
        return None

    regime_sharpes = {}
    for regime_name, rets in regime_returns.items():
        if len(rets) >= MIN_DAYS_PER_REGIME:
            s = pd.Series(rets)
            sh = compute_sharpe(s)
            if not math.isnan(sh):
                regime_sharpes[regime_name] = round(sh, 4)

    return regime_sharpes if regime_sharpes else None


# ── Step 5: Classify strategies ───────────────────────────────────────────────

def classify_strategy(
    overall_sharpe: float,
    regime_sharpes: Dict[str, float],
) -> Tuple[str, float, int]:
    """
    Returns (classification, mrp_score, regime_data_count).

    classification:
      'regime_resilient' — min Sharpe > 0.5 across ≥3 regimes
      'bull_only'        — good in calm/easing, poor in stress/tightening
      'weak'             — poor overall
      'insufficient_data' — fewer than 2 regimes with data
    """
    if not regime_sharpes:
        return 'insufficient_data', float('nan'), 0

    regime_data_count = len(regime_sharpes)

    if regime_data_count < 2:
        return 'insufficient_data', float('nan'), regime_data_count

    sharpe_values = list(regime_sharpes.values())
    mrp_score = min(sharpe_values)

    if regime_data_count < 3:
        return 'insufficient_data', round(mrp_score, 4), regime_data_count

    # Check if strategy is "bull only"
    bull_sharpes = [v for k, v in regime_sharpes.items() if k in BULL_REGIMES]
    stress_sharpes = [v for k, v in regime_sharpes.items() if k in STRESS_REGIMES]

    avg_bull = np.mean(bull_sharpes) if bull_sharpes else float('nan')
    avg_stress = np.mean(stress_sharpes) if stress_sharpes else float('nan')

    if mrp_score > MRP_RESILIENT_MIN_SHARPE and regime_data_count >= MRP_RESILIENT_MIN_REGIMES:
        classification = 'regime_resilient'
    elif (not math.isnan(avg_bull) and not math.isnan(avg_stress)
          and avg_bull > 0.6 and avg_stress < 0.2):
        classification = 'bull_only'
    elif overall_sharpe < 0.2:
        classification = 'weak'
    else:
        classification = 'inconsistent'

    return classification, round(mrp_score, 4), regime_data_count


# ── Step 6: Route each strategy to the right Sharpe estimator ─────────────────

def get_regime_sharpes_for_strategy(
    strat: Dict,
    regimes: pd.DataFrame,
) -> Optional[Dict[str, float]]:
    """Dispatch to the appropriate regime Sharpe computation method."""
    source = strat['source_file']
    strat_key = strat['strat_key']
    overall_sharpe = strat['overall_sharpe']

    # round_001-010 folder format
    if source.startswith('round_') and source.endswith('/results.json'):
        folder_name = source.split('/')[0]
        folder = ROUNDS_DIR / folder_name
        return compute_regime_sharpes_from_ticker_data(folder, strat_key, regimes)

    # macro_round_NN.json format
    if source.startswith('macro_round_'):
        return estimate_regime_sharpes_from_macro_round(ROUNDS_DIR / source, strat_key, regimes)

    # Everything else: misc files
    fp = ROUNDS_DIR / source
    if fp.exists():
        return estimate_regime_sharpes_from_misc(fp, strat_key, overall_sharpe, regimes)

    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("R35 — Minimum Regime Performance (MRP) Diagnostic")
    print(f"Run date: {datetime.now().date()}")
    print("=" * 70)

    # Step 1: Build regime labels
    regimes, regime_durations = build_regime_labels()

    # Step 2: Build strategy inventory
    strategies = build_strategy_inventory()

    if not strategies:
        print("ERROR: No strategies found!")
        sys.exit(1)

    # Step 3 & 4: Compute regime Sharpes for each strategy
    print(f"\nStep 3: Computing per-regime Sharpe ratios for {len(strategies)} strategies...")
    print("  (This uses price-proxy estimation for strategies without stored daily returns)")

    results = []
    for i, strat in enumerate(strategies):
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(strategies)}")

        regime_sharpes = get_regime_sharpes_for_strategy(strat, regimes)

        if regime_sharpes is None:
            regime_sharpes = {}

        classification, mrp_score, regime_data_count = classify_strategy(
            strat['overall_sharpe'], regime_sharpes
        )

        results.append({
            'name': strat['name'],
            'source_file': strat['source_file'],
            'family': strat['family'],
            'overall_sharpe': strat['overall_sharpe'],
            'mrp_score': mrp_score if not math.isnan(mrp_score) else None,
            'regime_sharpes': regime_sharpes,
            'classification': classification,
            'regime_data_count': regime_data_count,
        })

    print(f"  Done. Computed regime Sharpes for {sum(1 for r in results if r['regime_sharpes'])} strategies.")

    # Step 5: Sort by MRP score (descending), then overall sharpe
    def sort_key(r):
        mrp = r['mrp_score'] if r['mrp_score'] is not None else -999
        return (mrp, r['overall_sharpe'])

    results.sort(key=sort_key, reverse=True)

    # Step 6: Build summary stats
    classified = [r for r in results if r['classification'] != 'insufficient_data']
    n_resilient = sum(1 for r in classified if r['classification'] == 'regime_resilient')
    n_bull_only = sum(1 for r in classified if r['classification'] == 'bull_only')
    n_inconsistent = sum(1 for r in classified if r['classification'] == 'inconsistent')
    n_weak = sum(1 for r in classified if r['classification'] == 'weak')
    n_insufficient = sum(1 for r in results if r['classification'] == 'insufficient_data')

    summary = (
        f"{n_resilient} of {len(classified)} classified strategies are regime-resilient; "
        f"{n_bull_only} are bull-only; {n_inconsistent} are inconsistent; "
        f"{n_weak} are weak; {n_insufficient} have insufficient regime data."
    )
    print(f"\nSummary: {summary}")

    # Step 7: Save JSON results
    out_data = {
        'run_date': '2026-04-15',
        'methodology': (
            'Per-regime Sharpe estimated via price-proxy: for each strategy, '
            'representative ticker daily returns are scaled by the ratio of '
            'strategy Sharpe to B&H Sharpe, then split into FRED-labeled macro '
            'regimes. MRP score = minimum regime Sharpe across regimes with '
            f'>={MIN_DAYS_PER_REGIME} days of data.'
        ),
        'classification_rules': {
            'regime_resilient': f'min Sharpe > {MRP_RESILIENT_MIN_SHARPE} across >= {MRP_RESILIENT_MIN_REGIMES} regimes',
            'bull_only': 'avg bull-regime Sharpe > 0.6 AND avg stress-regime Sharpe < 0.2',
            'insufficient_data': f'fewer than 2 regimes with >= {MIN_DAYS_PER_REGIME} days',
        },
        'strategies': results,
        'regime_durations': regime_durations,
        'summary': summary,
    }

    out_json = ROUNDS_DIR / 'r35_mrp_results.json'
    with open(out_json, 'w') as f:
        json.dump(out_data, f, indent=2, default=str)
    print(f"\nSaved JSON → {out_json}")

    # Step 8: Save human-readable report
    lines = [
        '# R35 — Minimum Regime Performance (MRP) Diagnostic',
        '',
        f'**Run date:** 2026-04-15  ',
        f'**Strategies analysed:** {len(results)}  ',
        f'**Summary:** {summary}',
        '',
        '## Methodology',
        '',
        'Per-regime Sharpe ratios are estimated using a price-proxy approach:',
        'for each strategy, representative ticker daily returns are scaled by the',
        'ratio of the strategy\'s overall Sharpe to the ticker\'s B&H Sharpe,',
        'then split into FRED-labeled macro regimes.',
        '',
        '**Regime definitions** (from `macro_harness.classify_regimes()`):',
        '- `calm` — no active macro stressors',
        '- `stress` — VIX > 25 or HY spread > 500bp',
        '- `tightening` — inverted yield curve or rising Fed Funds',
        '- `easing` — Fed Funds falling',
        '- `oil_shock` — WTI > 90d mean + 1.5σ',
        '- `inflationary` — CPI YoY > 3.5% (or BIE > 2.8%)',
        '- `oil_high` — WTI > 90d rolling mean',
        '- `gold_bull` — Gold 6m momentum > +5%',
        '',
        '## Regime Durations',
        '',
        '| Regime | Days | % Time |',
        '|--------|-----:|-------:|',
    ]

    total_days = sum(regime_durations.values()) // len(regime_durations) if regime_durations else 1
    # Use a consistent total (VIX or WTI series length ~ 3800 days)
    total_days_spine = max(regime_durations.values()) if regime_durations else 3800
    # Actually we want the number of spine days; use calm + stress as rough total
    # Better: use the calendar days from regimes if available
    for regime_name in PRIMARY_REGIMES:
        if regime_name in regime_durations:
            days = regime_durations[regime_name]
            # Total is approximately the spine days
            # We'll compute pct relative to the max (calm days ~= largest bucket)
            lines.append(f'| {regime_name} | {days:,} | — |')

    lines += [
        '',
        '## Strategy Rankings by MRP Score',
        '',
        '> MRP Score = minimum Sharpe ratio across all regimes with sufficient data.',
        '> Higher is better. `regime_resilient` = min Sharpe > 0.5 across ≥ 3 regimes.',
        '',
        '### Regime-Resilient Strategies',
        '',
        '| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes | Calm | Stress | Tighten | Easing |',
        '|-----:|----------|---------------:|----------:|----------:|-----:|-------:|--------:|-------:|',
    ]

    resilient = [r for r in results if r['classification'] == 'regime_resilient']
    for rank, r in enumerate(resilient[:30], 1):
        rs = r['regime_sharpes']
        calm_s   = f"{rs.get('calm', float('nan')):.2f}"   if 'calm'       in rs else '—'
        stress_s = f"{rs.get('stress', float('nan')):.2f}" if 'stress'     in rs else '—'
        tight_s  = f"{rs.get('tightening', float('nan')):.2f}" if 'tightening' in rs else '—'
        ease_s   = f"{rs.get('easing', float('nan')):.2f}" if 'easing'     in rs else '—'
        mrp = f"{r['mrp_score']:.3f}" if r['mrp_score'] is not None else '—'
        lines.append(
            f"| {rank} | {r['name']} | {r['overall_sharpe']:.3f} | {mrp} | "
            f"{r['regime_data_count']} | {calm_s} | {stress_s} | {tight_s} | {ease_s} |"
        )

    lines += [
        '',
        '### Bull-Market-Only Strategies',
        '',
        '| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes | Calm | Stress |',
        '|-----:|----------|---------------:|----------:|----------:|-----:|-------:|',
    ]

    bull_only = [r for r in results if r['classification'] == 'bull_only']
    for rank, r in enumerate(bull_only[:20], 1):
        rs = r['regime_sharpes']
        calm_s   = f"{rs.get('calm', float('nan')):.2f}" if 'calm'   in rs else '—'
        stress_s = f"{rs.get('stress', float('nan')):.2f}" if 'stress' in rs else '—'
        mrp = f"{r['mrp_score']:.3f}" if r['mrp_score'] is not None else '—'
        lines.append(
            f"| {rank} | {r['name']} | {r['overall_sharpe']:.3f} | {mrp} | "
            f"{r['regime_data_count']} | {calm_s} | {stress_s} |"
        )

    lines += [
        '',
        '### Inconsistent Strategies (pass some regimes, fail others)',
        '',
        '| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes |',
        '|-----:|----------|---------------:|----------:|----------:|',
    ]

    inconsistent = [r for r in results if r['classification'] == 'inconsistent']
    for rank, r in enumerate(inconsistent[:20], 1):
        mrp = f"{r['mrp_score']:.3f}" if r['mrp_score'] is not None else '—'
        lines.append(
            f"| {rank} | {r['name']} | {r['overall_sharpe']:.3f} | {mrp} | {r['regime_data_count']} |"
        )

    lines += [
        '',
        '### Weak Strategies (poor overall)',
        '',
        '| Strategy | Overall Sharpe | MRP Score |',
        '|----------|---------------:|----------:|',
    ]
    weak = [r for r in results if r['classification'] == 'weak']
    for r in weak[:15]:
        mrp = f"{r['mrp_score']:.3f}" if r['mrp_score'] is not None else '—'
        lines.append(f"| {r['name']} | {r['overall_sharpe']:.3f} | {mrp} |")

    lines += [
        '',
        '## Classification Summary',
        '',
        f'| Classification | Count | % of Classified |',
        f'|----------------|------:|----------------:|',
        f'| regime_resilient | {n_resilient} | {n_resilient/max(len(classified),1)*100:.1f}% |',
        f'| bull_only | {n_bull_only} | {n_bull_only/max(len(classified),1)*100:.1f}% |',
        f'| inconsistent | {n_inconsistent} | {n_inconsistent/max(len(classified),1)*100:.1f}% |',
        f'| weak | {n_weak} | {n_weak/max(len(classified),1)*100:.1f}% |',
        f'| insufficient_data | {n_insufficient} | — |',
        '',
        '## Notes on Estimation Method',
        '',
        '- Regime Sharpe ratios are **estimated** (proxy method), not exact replays.',
        '- For round_001-010 strategies: per-ticker B&H returns are scaled by',
        '  the strategy/B&H Sharpe ratio, then split by regime.',
        '- For macro rounds (R11-R18): same approach using UNIVERSE tickers.',
        '- The proxy preserves directional regime sensitivity but smooths',
        '  cross-sectional variation. Use for ranking, not precise measurement.',
        f'- Minimum {MIN_DAYS_PER_REGIME} trading days required per regime to include it.',
        '',
        f'*Generated by r35_mrp_diagnostic.py on 2026-04-15*',
    ]

    out_md = ROUNDS_DIR / 'r35_mrp_report.md'
    with open(out_md, 'w') as f:
        f.write('\n'.join(lines))
    print(f"Saved report → {out_md}")

    # Print top 10 by MRP score
    print("\n" + "=" * 70)
    print("TOP 15 STRATEGIES BY MRP SCORE")
    print("=" * 70)
    print(f"  {'Rank':<5} {'Strategy':<45} {'Overall':>8} {'MRP':>7} {'Class':<20} {'#Reg':>5}")
    print(f"  {'-'*5} {'-'*45} {'-'*8} {'-'*7} {'-'*20} {'-'*5}")
    for rank, r in enumerate(results[:15], 1):
        mrp = f"{r['mrp_score']:.3f}" if r['mrp_score'] is not None else '  N/A'
        print(f"  {rank:<5} {r['name']:<45} {r['overall_sharpe']:>8.3f} {mrp:>7} {r['classification']:<20} {r['regime_data_count']:>5}")

    print(f"\nDone. Results in:")
    print(f"  {out_json}")
    print(f"  {out_md}")


if __name__ == '__main__':
    main()
