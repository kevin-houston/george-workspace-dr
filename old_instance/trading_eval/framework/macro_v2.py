#!/usr/bin/env python3
"""
macro_v2.py — Macro Harness v2 (Rounds 11-18 using TradeLogger)
================================================================
Converts macro_harness.py strategy logic into per-trade TradeLogger records.
- round_num from harness (11-18)
- category='macro'
- One TradeLogger per strategy variant
- Log per trade with all available fields
- No metrics computed (analysis layer's job)

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/macro_v2.py --round 11
  /workspace/group/venv/bin/python3 trading_eval/framework/macro_v2.py --all
  /workspace/group/venv/bin/python3 trading_eval/framework/macro_v2.py --show-regimes
"""

from __future__ import annotations

import sys
import os

# Bootstrap paths so framework imports work from any cwd
sys.path.insert(0, '/workspace/group/trading_eval/framework')
sys.path.insert(0, '/workspace/group/trading_eval')

import argparse
import json
import math
import pickle
import time
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: /workspace/group/venv/bin/pip install yfinance pandas numpy")
    sys.exit(1)

from base_harness import TradeLogger, fetch_data, get_close

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path('/workspace/group/trading_eval')
CACHE_DIR  = ROOT / 'cache'
ROUNDS_DIR = ROOT / 'rounds'
MACRO_DIR  = ROOT / 'macro_cache'
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)
MACRO_DIR.mkdir(exist_ok=True)

# ── Universe & Sector Map (exact copy from macro_harness.py) ──────────────────

UNIVERSE = {
    'XOM':  'Exxon Mobil',
    'CVX':  'Chevron',
    'COP':  'ConocoPhillips',
    'MPC':  'Marathon Petroleum',
    'VLO':  'Valero Energy',
    'PSX':  'Phillips 66',
    'HAL':  'Halliburton',
    'LMT':  'Lockheed Martin',
    'RTX':  'RTX (Raytheon)',
    'NOC':  'Northrop Grumman',
    'GD':   'General Dynamics',
    'BA':   'Boeing',
    'WMT':  'Walmart',
    'PG':   'Procter & Gamble',
    'KO':   'Coca-Cola',
    'PEP':  'PepsiCo',
    'COST': 'Costco',
    'KR':   'Kroger',
    'ADM':  'Archer Daniels Midland',
    'TSN':  'Tyson Foods',
    'CAT':  'Caterpillar',
    'DE':   'Deere & Co',
    'GE':   'General Electric',
    'DOW':  'Dow Inc',
    'NUE':  'Nucor',
    'MMM':  '3M',
    'JPM':  'JPMorgan Chase',
    'BAC':  'Bank of America',
    'GS':   'Goldman Sachs',
    'WFC':  'Wells Fargo',
    'MS':   'Morgan Stanley',
    'AXP':  'American Express',
    'AAPL': 'Apple',
    'MSFT': 'Microsoft',
    'GOOGL':'Alphabet',
    'META': 'Meta Platforms',
    'AMZN': 'Amazon',
    'NVDA': 'NVIDIA',
    'ORCL': 'Oracle',
    'CRM':  'Salesforce',
    'UNH':  'UnitedHealth Group',
    'JNJ':  'Johnson & Johnson',
    'LLY':  'Eli Lilly',
    'MRK':  'Merck',
    'ABT':  'Abbott',
    'PFE':  'Pfizer',
    'TMO':  'Thermo Fisher',
    'UPS':  'UPS',
    'FDX':  'FedEx',
    'UNP':  'Union Pacific',
    'TSLA': 'Tesla',
    'F':    'Ford',
    'GM':   'General Motors',
}

SECTOR_MAP = {
    'energy':     ['XOM','CVX','COP','MPC','VLO','PSX','HAL'],
    'defense':    ['LMT','RTX','NOC','GD','BA'],
    'staples':    ['WMT','PG','KO','PEP','COST','KR','ADM','TSN'],
    'industrial': ['CAT','DE','GE','DOW','NUE','MMM'],
    'financial':  ['JPM','BAC','GS','WFC','MS','AXP'],
    'tech':       ['AAPL','MSFT','GOOGL','META','AMZN','NVDA','ORCL','CRM'],
    'healthcare': ['UNH','JNJ','LLY','MRK','ABT','PFE','TMO'],
    'transport':  ['UPS','FDX','UNP'],
    'auto':       ['TSLA','F','GM'],
}

YEARS      = 15
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime('%Y-%m-%d')
END_DATE   = datetime.now().strftime('%Y-%m-%d')

FRED_SERIES = {
    'DCOILWTICO':       'WTI Crude Oil Price (daily, $/barrel)',
    'DCOILBRENTEU':     'Brent Crude Oil Price (daily, $/barrel)',
    'CPIAUCSL':         'CPI All Urban Consumers (monthly, SA)',
    'CPILFESL':         'Core CPI ex Food & Energy (monthly, SA)',
    'PCEPI':            'PCE Price Index (monthly)',
    'T10YIE':           '10-Year Breakeven Inflation Rate (daily)',
    'T5YIFR':           '5-Year Forward Inflation Expectation (daily)',
    'DFF':              'Effective Federal Funds Rate (daily)',
    'GS10':             '10-Year Treasury Yield (daily)',
    'GS2':              '2-Year Treasury Yield (daily)',
    'T10Y2Y':           '10Y-2Y Yield Curve Spread (daily)',
    'BAMLH0A0HYM2':     'ICE BofA HY OAS Spread (daily, bp)',
    'BAMLC0A0CM':       'ICE BofA IG OAS Spread (daily, bp)',
    'KCFSI':            'KC Financial Stress Index (weekly)',
    'STLFSI4':          'St. Louis Fed Financial Stress Index (weekly)',
    'VIXCLS':           'CBOE VIX (daily)',
    'GOLDAMGBD228NLBM': 'Gold Price London AM Fix (daily, $/oz)',
    'PIORECRUSDM':      'Iron Ore Price (monthly, $/DMT)',
    'DEXUSEU':          'USD/EUR Exchange Rate (daily)',
    'DTWEXBGS':         'Broad Dollar Index (daily)',
    'UNRATE':           'Unemployment Rate (monthly)',
    'ICSA':             'Initial Jobless Claims (weekly)',
    'GDPC1':            'Real GDP (quarterly)',
    'INDPRO':           'Industrial Production Index (monthly)',
    'UMCSENT':          'U Michigan Consumer Sentiment (monthly)',
}

YFINANCE_FALLBACKS = {
    'DCOILWTICO':       'CL=F',
    'VIXCLS':           '^VIX',
    'GOLDAMGBD228NLBM': 'GC=F',
    'GS10':             '^TNX',
    'DEXUSEU':          'EURUSD=X',
    'DTWEXBGS':         'DX-Y.NYB',
}


# ── FRED / yfinance data fetchers (exact logic from macro_harness.py) ─────────

def fetch_fred_series(series_id: str, api_key: str) -> Optional[pd.Series]:
    cache_file = MACRO_DIR / f'fred_{series_id}.pkl'
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            try:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception:
                pass
    try:
        params = urllib.parse.urlencode({
            'series_id':     series_id,
            'api_key':       api_key,
            'file_type':     'json',
            'observation_start': START_DATE,
            'observation_end':   END_DATE,
        })
        url = f'https://api.stlouisfed.org/fred/series/observations?{params}'
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if 'observations' not in data:
            return None
        records = [(o['date'], o['value']) for o in data['observations']
                   if o['value'] != '.']
        if not records:
            return None
        dates, values = zip(*records)
        s = pd.Series(
            [float(v) for v in values],
            index=pd.to_datetime(dates),
            name=series_id,
        ).sort_index()
        with open(cache_file, 'wb') as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f'  FRED {series_id}: {e}', file=sys.stderr)
        return None


def fetch_yf_series(symbol: str, name: str) -> Optional[pd.Series]:
    safe = symbol.replace('^','').replace('=','').replace('/','')
    cache_file = MACRO_DIR / f'yf_{safe}.pkl'
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            try:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
            except Exception:
                pass
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if hist.empty:
            return None
        s = hist['Close'].dropna()
        s.name = name
        with open(cache_file, 'wb') as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f'  yf {symbol}: {e}', file=sys.stderr)
        return None


def load_macro_data(fred_key: Optional[str] = None) -> Dict[str, pd.Series]:
    print('  Loading macro data...')
    macro = {}
    for series_id in FRED_SERIES:
        if fred_key:
            s = fetch_fred_series(series_id, fred_key)
            if s is not None:
                macro[series_id] = s
                print(f'    FRED {series_id} ({len(s)} obs)')
                continue
        if series_id in YFINANCE_FALLBACKS:
            yf_sym = YFINANCE_FALLBACKS[series_id]
            s = fetch_yf_series(yf_sym, series_id)
            if s is not None:
                if series_id == 'GS10':
                    s = s / 10.0
                if series_id == 'DEXUSEU':
                    s = 1.0 / s
                macro[series_id] = s
                print(f'    yf fallback {yf_sym} -> {series_id} ({len(s)} obs)')
    print(f'  Loaded {len(macro)} macro series')
    return macro


def build_macro_frame(macro: Dict[str, pd.Series],
                      prices_index: pd.DatetimeIndex) -> pd.DataFrame:
    if prices_index.tzinfo is not None:
        align_index = prices_index.tz_localize(None)
    else:
        align_index = prices_index
    frames = {}
    for k, s in macro.items():
        if hasattr(s.index, 'tzinfo') and s.index.tzinfo is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        frames[k] = s.reindex(align_index, method='ffill')
    return pd.DataFrame(frames, index=align_index)


def classify_regimes(mf: pd.DataFrame) -> pd.DataFrame:
    regimes = pd.DataFrame(index=mf.index)

    oil_col = 'DCOILWTICO'
    if oil_col in mf.columns and mf[oil_col].notna().sum() > 90:
        oil = mf[oil_col].ffill()
        roll_mean = oil.rolling(90, min_periods=30).mean()
        roll_std  = oil.rolling(90, min_periods=30).std()
        regimes['oil_shock'] = oil > (roll_mean + 1.5 * roll_std)
        regimes['oil_high']  = oil > roll_mean
        regimes['oil_low']   = oil < (roll_mean - 0.5 * roll_std)
    else:
        regimes['oil_shock'] = False
        regimes['oil_high']  = False
        regimes['oil_low']   = True

    if 'CPIAUCSL' in mf.columns and mf['CPIAUCSL'].notna().sum() > 12:
        cpi = mf['CPIAUCSL'].ffill()
        cpi_yoy = cpi.pct_change(252) * 100
        regimes['inflationary']  = cpi_yoy > 3.5
        regimes['low_inflation'] = cpi_yoy < 2.0
    elif 'T10YIE' in mf.columns and mf['T10YIE'].notna().sum() > 90:
        bie = mf['T10YIE'].ffill()
        regimes['inflationary']  = bie > 2.8
        regimes['low_inflation'] = bie < 2.0
    else:
        regimes['inflationary']  = False
        regimes['low_inflation'] = True

    stress_flags = pd.Series(False, index=mf.index)
    if 'VIXCLS' in mf.columns and mf['VIXCLS'].notna().sum() > 90:
        vix = mf['VIXCLS'].ffill()
        stress_flags |= (vix > 25)
    if 'BAMLH0A0HYM2' in mf.columns and mf['BAMLH0A0HYM2'].notna().sum() > 90:
        hy = mf['BAMLH0A0HYM2'].ffill()
        stress_flags |= (hy > 500)
    regimes['stress']     = stress_flags
    regimes['low_stress'] = ~stress_flags

    tight_flags = pd.Series(False, index=mf.index)
    if 'T10Y2Y' in mf.columns and mf['T10Y2Y'].notna().sum() > 90:
        spread = mf['T10Y2Y'].ffill()
        tight_flags |= (spread < 0)
    elif 'GS10' in mf.columns and 'GS2' in mf.columns:
        gs10 = mf['GS10'].ffill()
        gs2  = mf['GS2'].ffill()
        spread = gs10 - gs2
        tight_flags |= (spread < 0)
    if 'DFF' in mf.columns and mf['DFF'].notna().sum() > 90:
        ff = mf['DFF'].ffill()
        ff_trend = ff - ff.shift(126)
        tight_flags |= (ff_trend > 0.25)
    regimes['tightening'] = tight_flags
    regimes['easing'] = pd.Series(False, index=mf.index)
    if 'DFF' in mf.columns and mf['DFF'].notna().sum() > 90:
        ff = mf['DFF'].ffill()
        ff_trend = ff - ff.shift(126)
        regimes['easing'] = (ff_trend < -0.25)

    if 'GOLDAMGBD228NLBM' in mf.columns and mf['GOLDAMGBD228NLBM'].notna().sum() > 90:
        gold = mf['GOLDAMGBD228NLBM'].ffill()
        gold_mom = gold.pct_change(126)
        regimes['gold_bull'] = gold_mom > 0.05
    else:
        regimes['gold_bull'] = False

    if 'DTWEXBGS' in mf.columns and mf['DTWEXBGS'].notna().sum() > 90:
        usd = mf['DTWEXBGS'].ffill()
        usd_mom = usd.pct_change(126)
        regimes['strong_dollar'] = usd_mom > 0.03
        regimes['weak_dollar']   = usd_mom < -0.03
    else:
        regimes['strong_dollar'] = False
        regimes['weak_dollar']   = False

    regimes['iran_proxy'] = regimes['oil_shock'] & (
        regimes['inflationary'] | regimes['stress']
    )
    regimes['calm'] = (
        ~regimes['oil_shock'] &
        ~regimes['inflationary'] &
        ~regimes['stress'] &
        ~regimes['tightening']
    )

    return regimes.fillna(False)


# ── Price fetcher ─────────────────────────────────────────────────────────────

def fetch_prices(symbol: str) -> Optional[pd.Series]:
    cp = CACHE_DIR / f"{symbol.replace('-','_').replace('^','')}_{YEARS}yr.pkl"
    if cp.exists():
        try:
            with open(cp, 'rb') as f:
                data = pickle.load(f)
            if isinstance(data, pd.Series) and len(data) > 100:
                return data
        except Exception:
            pass
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if hist.empty or 'Close' not in hist.columns:
            return None
        prices = hist['Close'].dropna()
        if len(prices) < 252:
            return None
        with open(cp, 'wb') as f:
            pickle.dump(prices, f)
        return prices
    except Exception as e:
        print(f'  {symbol}: {e}', file=sys.stderr)
        return None


# ── Strategy classes (exact logic from macro_harness.py) ─────────────────────

class Strategy(ABC):
    family:      str = 'unknown'
    name:        str = 'base'
    description: str = ''

    @abstractmethod
    def signals(self, prices: pd.Series) -> pd.Series:
        pass

    def __repr__(self):
        return f'{self.family}/{self.name}'


class RegimeGated(Strategy):
    def __init__(self, base: Strategy, regime: pd.Series, regime_name: str):
        self.base        = base
        self.regime      = regime
        self.regime_name = regime_name
        self.family      = base.family + '_macro'
        self.name        = f'{base.name}_IN_{regime_name}'
        self.description = f'{base.description} [only in {regime_name}]'

    def signals(self, prices: pd.Series) -> pd.Series:
        raw = self.base.signals(prices)
        reg = self.regime.reindex(prices.index, method='ffill').fillna(False)
        masked = raw.copy()
        masked[~reg] = 0
        return masked


class OilMomentum(Strategy):
    family = 'macro'

    def __init__(self, oil: pd.Series, fast: int = 20, slow: int = 60):
        self.oil  = oil
        self.fast = fast
        self.slow = slow
        self.name = f'OilMom_{fast}_{slow}'
        self.description = f'Long when WTI {fast}d > {slow}d SMA'

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method='ffill').ffill()
        fast_ma = oil.rolling(self.fast, min_periods=10).mean()
        slow_ma = oil.rolling(self.slow, min_periods=20).mean()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[fast_ma > slow_ma]  =  1
        sig[fast_ma <= slow_ma] = -1
        sig[fast_ma.isna() | slow_ma.isna()] = 0
        return sig


class OilShockLong(Strategy):
    family = 'macro'

    def __init__(self, oil: pd.Series, window: int = 90, threshold: float = 1.0):
        self.oil       = oil
        self.window    = window
        self.threshold = threshold
        self.name      = f'OilShock_{window}_{threshold}'
        self.description = f'Long during WTI oil shock (>{threshold}s above {window}d mean)'

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method='ffill').ffill()
        mean = oil.rolling(self.window, min_periods=30).mean()
        std  = oil.rolling(self.window, min_periods=30).std()
        z    = (oil - mean) / std.replace(0, np.nan)
        sig  = pd.Series(0, index=prices.index, dtype=float)
        sig[z >  self.threshold] =  1
        sig[z < -self.threshold] = -1
        sig[z.isna()] = 0
        return sig


class InflationBreakoutLong(Strategy):
    family = 'macro'

    def __init__(self, bie: pd.Series, window: int = 63):
        self.bie    = bie
        self.window = window
        self.name   = f'InfBreakout_{window}'
        self.description = f'Long when breakeven inflation rising over {window}d'

    def signals(self, prices: pd.Series) -> pd.Series:
        bie = self.bie.reindex(prices.index, method='ffill').ffill()
        trend = bie - bie.shift(self.window)
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[trend > 0.1]  =  1
        sig[trend < -0.1] = -1
        sig[trend.isna()] =  0
        return sig


class YieldCurveTrend(Strategy):
    family = 'macro'

    def __init__(self, gs10: pd.Series, gs2: pd.Series, window: int = 63):
        self.gs10   = gs10
        self.gs2    = gs2
        self.window = window
        self.name   = f'YieldCurve_{window}'
        self.description = f'Trade yield curve steepening/inversion ({window}d trend)'

    def signals(self, prices: pd.Series) -> pd.Series:
        gs10 = self.gs10.reindex(prices.index, method='ffill').ffill()
        gs2  = self.gs2.reindex(prices.index, method='ffill').ffill()
        spread = gs10 - gs2
        trend  = spread - spread.shift(self.window)
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[spread > 0.5]  =  1
        sig[spread < 0.0]  = -1
        sig[trend.isna()]  =  0
        return sig


class GoldFlightSafety(Strategy):
    family = 'macro'

    def __init__(self, gold: pd.Series, window: int = 63):
        self.gold   = gold
        self.window = window
        self.name   = f'GoldFlight_{window}'
        self.description = f'Long when gold rising over {window}d (flight-to-safety)'

    def signals(self, prices: pd.Series) -> pd.Series:
        gold = self.gold.reindex(prices.index, method='ffill').ffill()
        mom  = gold.pct_change(self.window)
        sig  = pd.Series(0, index=prices.index, dtype=float)
        sig[mom > 0.05]  =  1
        sig[mom < -0.05] = -1
        sig[mom.isna()]  =  0
        return sig


class CreditSpreadFilter(Strategy):
    family = 'macro'

    def __init__(self, hy_spread: pd.Series, long_thresh: float = 400,
                 short_thresh: float = 600, name: str = 'CreditFilter'):
        self.hy_spread    = hy_spread
        self.long_thresh  = long_thresh
        self.short_thresh = short_thresh
        self.name         = name
        self.description  = f'Long when HY spread <{long_thresh}bp, short >{short_thresh}bp'

    def signals(self, prices: pd.Series) -> pd.Series:
        hy = self.hy_spread.reindex(prices.index, method='ffill').ffill()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[hy < self.long_thresh]  =  1
        sig[hy > self.short_thresh] = -1
        sig[hy.isna()]              =  0
        return sig


class VIXRegimeMomentum(Strategy):
    family = 'macro'

    def __init__(self, vix: pd.Series, mom_window: int = 63,
                 vix_low: float = 18, vix_high: float = 30):
        self.vix        = vix
        self.mom_window = mom_window
        self.vix_low    = vix_low
        self.vix_high   = vix_high
        self.name       = f'VIXMom_{mom_window}_{vix_low}_{vix_high}'
        self.description = f'Momentum {mom_window}d, gated by VIX ({vix_low}/{vix_high})'

    def signals(self, prices: pd.Series) -> pd.Series:
        vix = self.vix.reindex(prices.index, method='ffill').ffill()
        mom = prices.pct_change(self.mom_window)
        sig = pd.Series(0, index=prices.index, dtype=float)
        low_vix_mask  = vix < self.vix_low
        sig[low_vix_mask & (mom > 0)]  =  1
        sig[low_vix_mask & (mom <= 0)] = -1
        high_vix_mask = vix > self.vix_high
        sig[high_vix_mask] = -1
        sig[vix.isna() | mom.isna()] = 0
        return sig


class MacroComposite(Strategy):
    family = 'macro'

    def __init__(self, oil=None, bie=None, gold=None,
                 gs10=None, gs2=None, vix=None, name='MacroComposite'):
        self.oil  = oil
        self.bie  = bie
        self.gold = gold
        self.gs10 = gs10
        self.gs2  = gs2
        self.vix  = vix
        self.name = name
        self.description = 'Composite: oil+inflation+gold+yieldcurve macro vote'

    def signals(self, prices: pd.Series) -> pd.Series:
        votes = pd.DataFrame(index=prices.index)
        if self.oil is not None:
            oil = self.oil.reindex(prices.index, method='ffill').ffill()
            oil_ma20 = oil.rolling(20, min_periods=10).mean()
            oil_ma60 = oil.rolling(60, min_periods=20).mean()
            votes['oil'] = 0.0
            votes.loc[oil_ma20 > oil_ma60,  'oil'] =  1
            votes.loc[oil_ma20 <= oil_ma60, 'oil'] = -1
        if self.bie is not None:
            bie = self.bie.reindex(prices.index, method='ffill').ffill()
            bie_trend = bie - bie.shift(63)
            votes['bie'] = 0.0
            votes.loc[bie_trend > 0.1,  'bie'] =  1
            votes.loc[bie_trend < -0.1, 'bie'] = -1
        if self.gold is not None:
            gold = self.gold.reindex(prices.index, method='ffill').ffill()
            gold_mom = gold.pct_change(63)
            votes['gold'] = 0.0
            votes.loc[gold_mom > 0.05,  'gold'] =  1
            votes.loc[gold_mom < -0.05, 'gold'] = -1
        if self.gs10 is not None and self.gs2 is not None:
            g10 = self.gs10.reindex(prices.index, method='ffill').ffill()
            g2  = self.gs2.reindex(prices.index, method='ffill').ffill()
            spread = g10 - g2
            votes['yc'] = 0.0
            votes.loc[spread > 0.5, 'yc'] =  1
            votes.loc[spread < 0.0, 'yc'] = -1
        if self.vix is not None:
            vix = self.vix.reindex(prices.index, method='ffill').ffill()
            votes['vix'] = 0.0
            votes.loc[vix < 18, 'vix'] =  0.5
            votes.loc[vix > 30, 'vix'] = -1.5
        if votes.empty:
            return pd.Series(0, index=prices.index, dtype=float)
        score = votes.mean(axis=1)
        sig   = pd.Series(0, index=prices.index, dtype=float)
        sig[score >  0.3] =  1
        sig[score < -0.3] = -1
        return sig


class OilInflationCombo(Strategy):
    family = 'macro'

    def __init__(self, oil: pd.Series, bie_or_cpi: pd.Series,
                 oil_window: int = 90, inf_window: int = 63,
                 name: str = 'OilInflationCombo'):
        self.oil        = oil
        self.inf        = bie_or_cpi
        self.oil_window = oil_window
        self.inf_window = inf_window
        self.name       = name
        self.description = 'Oil shock + inflation combo (Iran scenario)'

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method='ffill').ffill()
        inf = self.inf.reindex(prices.index, method='ffill').ffill()
        oil_mean = oil.rolling(self.oil_window, min_periods=30).mean()
        oil_std  = oil.rolling(self.oil_window, min_periods=30).std()
        oil_z    = (oil - oil_mean) / oil_std.replace(0, np.nan)
        inf_trend = inf - inf.shift(self.inf_window)
        sig = pd.Series(0, index=prices.index, dtype=float)
        both_bullish = (oil_z > 1.0) & (inf_trend > 0)
        sig[both_bullish] = 1
        both_bearish = (oil_z < -0.5) & (inf_trend < 0)
        sig[both_bearish] = -1
        sig[oil_z.isna() | inf_trend.isna()] = 0
        return sig


# ── Strategy builder (rounds 11-18, no harness import) ───────────────────────

def build_strategies(macro: Dict[str, pd.Series],
                     regimes: Optional[pd.DataFrame],
                     round_num: int) -> List[Strategy]:
    oil  = macro.get('DCOILWTICO')
    bie  = macro.get('T10YIE')
    gold = macro.get('GOLDAMGBD228NLBM')
    gs10 = macro.get('GS10')
    gs2  = macro.get('GS2')
    vix  = macro.get('VIXCLS')
    hy   = macro.get('BAMLH0A0HYM2')

    strategies = []

    # R11
    if round_num == 11:
        if oil is not None:
            strategies += [
                OilMomentum(oil, 20, 60),
                OilMomentum(oil, 10, 30),
                OilMomentum(oil, 30, 90),
                OilShockLong(oil, 90, 1.0),
                OilShockLong(oil, 90, 1.5),
                OilShockLong(oil, 60, 1.0),
            ]
        if bie is not None:
            strategies += [
                InflationBreakoutLong(bie, 63),
                InflationBreakoutLong(bie, 126),
            ]
        if vix is not None:
            strategies += [
                VIXRegimeMomentum(vix, 63, 18, 30),
                VIXRegimeMomentum(vix, 21, 20, 28),
                VIXRegimeMomentum(vix, 126, 15, 25),
            ]
        if gold is not None:
            strategies += [
                GoldFlightSafety(gold, 63),
                GoldFlightSafety(gold, 126),
            ]
        if hy is not None:
            strategies += [
                CreditSpreadFilter(hy, 400, 600, 'CreditFilter_400_600'),
                CreditSpreadFilter(hy, 350, 500, 'CreditFilter_350_500'),
                CreditSpreadFilter(hy, 450, 700, 'CreditFilter_450_700'),
            ]

    # R12
    elif round_num == 12:
        if oil is not None and bie is not None:
            strategies += [
                OilInflationCombo(oil, bie, 90, 63, 'OilInfCombo_90_63'),
                OilInflationCombo(oil, bie, 60, 42, 'OilInfCombo_60_42'),
                OilInflationCombo(oil, bie, 120, 90, 'OilInfCombo_120_90'),
            ]
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies += [
                MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull'),
                MacroComposite(oil, bie, gold, None, None, vix, 'MacroNoYC'),
                MacroComposite(oil, bie, None, gs10, gs2, None, 'MacroRates'),
            ]
        elif oil is not None and vix is not None:
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroAvail'))
        if oil is not None:
            for fast, slow in [(5,20),(10,50),(15,45),(20,60),(30,90),(5,50),(10,30)]:
                strategies.append(OilMomentum(oil, fast, slow))
        if vix is not None:
            for window, lo, hi in [(21,15,25),(42,18,30),(63,20,35),(126,18,30)]:
                strategies.append(VIXRegimeMomentum(vix, window, lo, hi))
        if gold is not None:
            for w in [21, 42, 63, 126, 189]:
                strategies.append(GoldFlightSafety(gold, w))
        if gs10 is not None and gs2 is not None:
            for w in [21, 42, 63, 126]:
                strategies.append(YieldCurveTrend(gs10, gs2, w))

    # R13
    elif round_num == 13:
        if oil is not None:
            for thresh in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
                strategies.append(OilShockLong(oil, 90, thresh))
        if vix is not None:
            for lo, hi in [(15,25),(18,28),(18,30),(20,30),(20,35),(15,35)]:
                strategies.append(VIXRegimeMomentum(vix, 63, lo, hi))
        if oil is not None and vix is not None:
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_v2'))
        if gold is not None:
            for w in [30, 45, 60, 90, 120, 180]:
                strategies.append(GoldFlightSafety(gold, w))
        if hy is not None:
            for lt, st in [(300,500),(350,550),(400,600),(450,650),(500,750)]:
                strategies.append(CreditSpreadFilter(hy, lt, st, f'Credit_{lt}_{st}'))

    # R14
    elif round_num == 14:
        if oil is not None:
            strategies += [
                OilMomentum(oil, 10, 50),
                OilMomentum(oil, 5, 20),
                OilShockLong(oil, 90, 1.0),
            ]
        if vix is not None:
            strategies.append(VIXRegimeMomentum(vix, 63, 18, 30))
        if oil is not None and bie is not None:
            strategies.append(OilInflationCombo(oil, bie, 90, 63, 'IranScenario'))
        if all(x is not None for x in [oil, bie, gold, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_R14'))

    # R15
    elif round_num == 15:
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if vix is not None:
            strategies.append(VIXRegimeMomentum(vix, 63, 18, 30))
        if oil is not None and bie is not None:
            strategies.append(OilInflationCombo(oil, bie, 90, 63, 'IranScenario'))
        if all(x is not None for x in [oil, bie, gold, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_Final'))

    # R16
    elif round_num == 16:
        if bie is not None:
            for w in [21, 42, 63, 126, 189]:
                strategies.append(InflationBreakoutLong(bie, w))
        if oil is not None and bie is not None:
            for ow, iw in [(60,42),(90,63),(90,42),(120,63),(120,90)]:
                strategies.append(OilInflationCombo(oil, bie, ow, iw, f'OilInf_{ow}_{iw}'))
        if hy is not None:
            for lt, st in [(250,400),(300,500),(350,550),(400,600),
                           (450,650),(500,750),(300,600),(400,700)]:
                strategies.append(CreditSpreadFilter(hy, lt, st, f'HY_{lt}_{st}'))
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_FRED'))
        if all(x is not None for x in [oil, bie, vix]):
            strategies.append(MacroComposite(oil, bie, None, None, None, vix, 'MacroCore_FRED'))
        if oil is not None:
            for fast, slow in [(5,20),(8,30),(10,50),(12,40),(15,50),(20,80)]:
                strategies.append(OilMomentum(oil, fast, slow))
        if vix is not None:
            for win, lo, hi in [(21,15,25),(42,18,28),(63,18,30),(63,20,30),(63,20,35),(126,18,30)]:
                strategies.append(VIXRegimeMomentum(vix, win, lo, hi))
        if gold is not None:
            for w in [90, 100, 110, 120, 130, 140, 150]:
                strategies.append(GoldFlightSafety(gold, w))
        if gs10 is not None and gs2 is not None:
            for w in [21, 42, 63, 126]:
                strategies.append(YieldCurveTrend(gs10, gs2, w))

    # R17
    elif round_num == 17:
        if bie is not None:
            strategies += [
                InflationBreakoutLong(bie, 63),
                InflationBreakoutLong(bie, 126),
            ]
        if hy is not None:
            strategies += [
                CreditSpreadFilter(hy, 300, 500, 'HY_300_500'),
                CreditSpreadFilter(hy, 350, 550, 'HY_350_550'),
            ]
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if gold is not None:
            strategies.append(GoldFlightSafety(gold, 120))
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_R17'))

    # R18
    elif round_num == 18:
        if gold is not None:
            strategies.append(GoldFlightSafety(gold, 120))
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if bie is not None:
            strategies.append(InflationBreakoutLong(bie, 63))
        if hy is not None:
            strategies.append(CreditSpreadFilter(hy, 300, 500, 'HY_300_500'))
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, 'MacroFull_Champion'))

    return strategies


# ── Trade extraction from signal series ──────────────────────────────────────

def extract_trades(prices: pd.Series, signals: pd.Series) -> List[dict]:
    """
    Convert a signal series (+1 long, -1 short, 0 flat) into individual trades.
    Entry on signal day close (shifted by 1 for next-day entry), exit on flip/exit.
    """
    common = prices.index.intersection(signals.index)
    if len(common) < 10:
        return []

    p = prices.loc[common]
    s = signals.loc[common].shift(1).fillna(0)

    # Normalize tz
    if p.index.tz is not None:
        p = p.copy()
        p.index = p.index.tz_localize(None)
    if s.index.tz is not None:
        s = s.copy()
        s.index = s.index.tz_localize(None)

    trades = []
    in_trade = False
    entry_date = None
    entry_price = None
    direction = None

    dates = p.index.tolist()
    for i, dt in enumerate(dates):
        sig_val = s.iloc[i]
        price_val = p.iloc[i]

        if not in_trade:
            if sig_val != 0:
                in_trade    = True
                entry_date  = dt
                entry_price = price_val
                direction   = 'long' if sig_val > 0 else 'short'
        else:
            # Exit when signal flips or goes to 0
            current_dir = 'long' if sig_val > 0 else ('short' if sig_val < 0 else 'flat')
            if sig_val == 0 or current_dir != direction or i == len(dates) - 1:
                exit_date  = dt
                exit_price = price_val
                hold_days  = (exit_date - entry_date).days
                if direction == 'long':
                    ret_pct = (exit_price / entry_price - 1) * 100
                else:
                    ret_pct = (entry_price / exit_price - 1) * 100

                trades.append({
                    'entry_date':  entry_date,
                    'exit_date':   exit_date,
                    'entry_price': float(entry_price),
                    'exit_price':  float(exit_price),
                    'return_pct':  float(ret_pct),
                    'hold_days':   int(hold_days),
                    'direction':   direction,
                })
                in_trade = False
                # Check if new trade starts immediately
                if sig_val != 0:
                    in_trade    = True
                    entry_date  = dt
                    entry_price = price_val
                    direction   = 'long' if sig_val > 0 else 'short'

    return trades


# ── Main runner ───────────────────────────────────────────────────────────────

def run_round(round_num: int, strategies: List[Strategy],
              tickers: Optional[List[str]] = None,
              macro: Optional[Dict] = None,
              regimes: Optional[pd.DataFrame] = None) -> None:
    """
    Run a single eval round.
    Creates one TradeLogger per strategy variant, logs all trades, saves JSONL.
    """
    tickers = tickers or list(UNIVERSE.keys())

    print(f'\n{"="*70}')
    print(f'MACRO V2 ROUND {round_num} — {len(strategies)} strategies x {len(tickers)} tickers')
    print(f'{"="*70}\n')

    # One logger per strategy
    loggers: Dict[str, TradeLogger] = {}
    for strat in strategies:
        loggers[strat.name] = TradeLogger(
            round_num=round_num,
            strategy=strat.name,
            category='macro',
        )

    for sym in tickers:
        prices = fetch_prices(sym)
        if prices is None:
            continue

        sector = next((s for s, tks in SECTOR_MAP.items() if sym in tks), 'other')

        for strat in strategies:
            try:
                sigs = strat.signals(prices)
            except Exception as e:
                print(f'  [WARN] {strat.name} on {sym}: {e}')
                continue

            trades = extract_trades(prices, sigs)
            logger = loggers[strat.name]

            for t in trades:
                logger.log(
                    ticker      = sym,
                    entry_date  = t['entry_date'],
                    exit_date   = t['exit_date'],
                    return_pct  = t['return_pct'],
                    hold_days   = t['hold_days'],
                    direction   = t['direction'],
                    entry_price = t['entry_price'],
                    exit_price  = t['exit_price'],
                    params      = {
                        'family':      strat.family,
                        'description': strat.description,
                    },
                    sector       = sector,
                    strategy_family = strat.family,
                    notes        = f'{strat.description}',
                )

    # Save all loggers
    total_trades = 0
    for strat_name, logger in loggers.items():
        if len(logger) > 0:
            logger.save()
            total_trades += len(logger)

    print(f'\n  Round {round_num} complete: {total_trades} trades logged across {len(loggers)} strategies')


def analyze_regimes(regimes: pd.DataFrame) -> None:
    print('\n' + '='*70)
    print('MACRO REGIME ANALYSIS')
    print('='*70)
    total = len(regimes)
    print(f'\nPeriod: {regimes.index[0].date()} to {regimes.index[-1].date()} ({total} trading days)')
    for col in regimes.columns:
        days = int(regimes[col].sum())
        pct  = days / total * 100
        print(f'  {col:<25} {days:>6,} {pct:>6.1f}%')
    print(f'\n  CURRENT REGIME (as of {regimes.index[-1].date()}):')
    last = regimes.iloc[-1]
    active = [c for c in last.index if last[c]]
    if active:
        for r in active:
            print(f'    {r}')
    else:
        print('    (no active regimes detected)')


def main():
    parser = argparse.ArgumentParser(description='Macro V2 — TradeLogger harness')
    parser.add_argument('--round',        type=int, help='Run specific round (11-18)')
    parser.add_argument('--all',          action='store_true', help='Run rounds 11-18')
    parser.add_argument('--show-regimes', action='store_true', help='Print regime analysis and exit')
    parser.add_argument('--fred-key',     type=str,
                        default=os.environ.get('FRED_API_KEY', ''),
                        help='FRED API key (or set FRED_API_KEY env var)')
    parser.add_argument('--symbols',      nargs='+', help='Override ticker list')
    args = parser.parse_args()

    fred_key = args.fred_key or None

    macro = load_macro_data(fred_key)
    if not macro:
        print('ERROR: No macro data loaded.')
        sys.exit(1)

    # Build common price index
    ref_prices = fetch_prices('AAPL')
    if ref_prices is None:
        print('ERROR: Cannot fetch price data.')
        sys.exit(1)

    price_idx = ref_prices.index
    mf        = build_macro_frame(macro, price_idx)
    regimes   = classify_regimes(mf)

    if args.show_regimes:
        analyze_regimes(regimes)
        return

    tickers = args.symbols or list(UNIVERSE.keys())

    rounds_to_run = []
    if args.all:
        rounds_to_run = list(range(11, 19))
    elif args.round:
        rounds_to_run = [args.round]
    else:
        print('Specify --round N or --all. Use --show-regimes to inspect macro data.')
        return

    for rnum in rounds_to_run:
        print(f'\n{"#"*70}')
        print(f'# STARTING ROUND {rnum}')
        print(f'{"#"*70}')
        strategies = build_strategies(macro, regimes, rnum)
        if not strategies:
            print(f'  No strategies built for round {rnum}. Skipping.')
            continue
        run_round(rnum, strategies, tickers, macro, regimes)


if __name__ == '__main__':
    main()
