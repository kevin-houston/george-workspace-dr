#!/usr/bin/env python3
"""
Macro-Enhanced Trading Eval Harness — FRED + Karpathy Autoresearch Edition
===========================================================================
Extends the base harness with macroeconomic regime detection.

Hypothesis: Given the Iran war → oil shock → inflationary cascade scenario,
strategies conditioned on macro regime should significantly outperform
all-weather approaches. This harness tests that hypothesis.

Data Sources:
  Primary:  FRED API (st.louisFed) — CPI, Fed Funds, credit spreads, gold
  Fallback: yfinance — crude oil (CL=F), VIX (^VIX), gold (GC=F),
                       10-yr yield (^TNX), USD (DX-Y.NYB)

Macro Regimes Tested:
  1. OIL_SHOCK    — WTI > rolling_mean + 1.5σ  (supply disruption)
  2. INFLATIONARY — CPI YoY > 4% AND trending up
  3. STRESS       — VIX > 25 OR credit spread > 400bp
  4. TIGHTENING   — Fed Funds rising + yield curve flattening
  5. CALM         — None of the above (baseline/normal)

Autoresearch Rounds (11-15):
  R11: Regime filter — best R1-R10 strategies filtered to favorable regimes
  R12: Macro momentum signals — trade based on oil/inflation momentum
  R13: Sector rotation — energy vs. defensives vs. tech by regime
  R14: Regime-switching — different strategy per regime
  R15: Full ensemble — top macro-aware strategies combined

Usage:
  PYTHONPATH=/tmp/eval_deps python3 macro_harness.py --round 11
  PYTHONPATH=/tmp/eval_deps python3 macro_harness.py --round 11 --fred-key YOUR_KEY
  PYTHONPATH=/tmp/eval_deps python3 macro_harness.py --all
  PYTHONPATH=/tmp/eval_deps python3 macro_harness.py --show-regimes
"""

from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import sys
import time
import urllib.request
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Dependency guard ──────────────────────────────────────────────────────────

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: curl -s https://bootstrap.pypa.io/get-pip.py | python3 - --break-system-packages")
    print("Then: PATH=$PATH:/home/node/.local/bin pip install yfinance pandas numpy --target=/tmp/eval_deps")
    print("Then: PYTHONPATH=/tmp/eval_deps python3 macro_harness.py")
    sys.exit(1)

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
MACRO_DIR  = ROOT / "macro_cache"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)
MACRO_DIR.mkdir(exist_ok=True)

# ── Universe ──────────────────────────────────────────────────────────────────
# Same Fortune 100 universe as base harness, organized by sector for
# regime-based sector rotation strategies

UNIVERSE = {
    # ENERGY — primary beneficiaries of oil shock
    "XOM":  "Exxon Mobil",
    "CVX":  "Chevron",
    "COP":  "ConocoPhillips",
    "MPC":  "Marathon Petroleum",
    "VLO":  "Valero Energy",
    "PSX":  "Phillips 66",
    "HAL":  "Halliburton",
    # DEFENSE — geopolitical conflict beneficiaries
    "LMT":  "Lockheed Martin",
    "RTX":  "RTX (Raytheon)",
    "NOC":  "Northrop Grumman",
    "GD":   "General Dynamics",
    "BA":   "Boeing",
    # CONSUMER STAPLES — inflation defensive
    "WMT":  "Walmart",
    "PG":   "Procter & Gamble",
    "KO":   "Coca-Cola",
    "PEP":  "PepsiCo",
    "COST": "Costco",
    "KR":   "Kroger",
    "ADM":  "Archer Daniels Midland",
    "TSN":  "Tyson Foods",
    # INDUSTRIALS — inflation mixed
    "CAT":  "Caterpillar",
    "DE":   "Deere & Co",
    "GE":   "General Electric",
    "DOW":  "Dow Inc",
    "NUE":  "Nucor",
    "MMM":  "3M",
    # FINANCIALS — rate sensitive
    "JPM":  "JPMorgan Chase",
    "BAC":  "Bank of America",
    "GS":   "Goldman Sachs",
    "WFC":  "Wells Fargo",
    "MS":   "Morgan Stanley",
    "AXP":  "American Express",
    # TECHNOLOGY — growth/rate sensitive (inflation negative)
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "GOOGL":"Alphabet",
    "META": "Meta Platforms",
    "AMZN": "Amazon",
    "NVDA": "NVIDIA",
    "ORCL": "Oracle",
    "CRM":  "Salesforce",
    # HEALTHCARE — defensive
    "UNH":  "UnitedHealth Group",
    "JNJ":  "Johnson & Johnson",
    "LLY":  "Eli Lilly",
    "MRK":  "Merck",
    "ABT":  "Abbott",
    "PFE":  "Pfizer",
    "TMO":  "Thermo Fisher",
    # TRANSPORT / LOGISTICS — oil cost-sensitive
    "UPS":  "UPS",
    "FDX":  "FedEx",
    "UNP":  "Union Pacific",
    # AUTOS — oil demand sensitivity
    "TSLA": "Tesla",
    "F":    "Ford",
    "GM":   "General Motors",
}

SECTOR_MAP = {
    "energy":     ["XOM","CVX","COP","MPC","VLO","PSX","HAL"],
    "defense":    ["LMT","RTX","NOC","GD","BA"],
    "staples":    ["WMT","PG","KO","PEP","COST","KR","ADM","TSN"],
    "industrial": ["CAT","DE","GE","DOW","NUE","MMM"],
    "financial":  ["JPM","BAC","GS","WFC","MS","AXP"],
    "tech":       ["AAPL","MSFT","GOOGL","META","AMZN","NVDA","ORCL","CRM"],
    "healthcare": ["UNH","JNJ","LLY","MRK","ABT","PFE","TMO"],
    "transport":  ["UPS","FDX","UNP"],
    "auto":       ["TSLA","F","GM"],
}

YEARS      = 15
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")

# ── FRED Series Definitions ───────────────────────────────────────────────────

FRED_SERIES = {
    # Oil & Energy
    "DCOILWTICO":       "WTI Crude Oil Price (daily, $/barrel)",
    "DCOILBRENTEU":     "Brent Crude Oil Price (daily, $/barrel)",
    # Inflation
    "CPIAUCSL":         "CPI All Urban Consumers (monthly, SA)",
    "CPILFESL":         "Core CPI ex Food & Energy (monthly, SA)",
    "PCEPI":            "PCE Price Index (monthly)",
    "T10YIE":           "10-Year Breakeven Inflation Rate (daily)",
    "T5YIFR":           "5-Year Forward Inflation Expectation (daily)",
    # Interest Rates
    "DFF":              "Effective Federal Funds Rate (daily)",
    "GS10":             "10-Year Treasury Yield (daily)",
    "GS2":              "2-Year Treasury Yield (daily)",
    "T10Y2Y":           "10Y-2Y Yield Curve Spread (daily)",
    # Credit / Stress
    "BAMLH0A0HYM2":     "ICE BofA HY OAS Spread (daily, bp)",
    "BAMLC0A0CM":       "ICE BofA IG OAS Spread (daily, bp)",
    "KCFSI":            "KC Financial Stress Index (weekly)",
    "STLFSI4":          "St. Louis Fed Financial Stress Index (weekly)",
    # Volatility / Sentiment
    "VIXCLS":           "CBOE VIX (daily)",
    # Commodities
    "GOLDAMGBD228NLBM": "Gold Price London AM Fix (daily, $/oz)",
    "PIORECRUSDM":      "Iron Ore Price (monthly, $/DMT)",
    # FX
    "DEXUSEU":          "USD/EUR Exchange Rate (daily)",
    "DTWEXBGS":         "Broad Dollar Index (daily)",
    # Employment
    "UNRATE":           "Unemployment Rate (monthly)",
    "ICSA":             "Initial Jobless Claims (weekly)",
    # GDP / Activity
    "GDPC1":            "Real GDP (quarterly)",
    "INDPRO":           "Industrial Production Index (monthly)",
    "UMCSENT":          "U Michigan Consumer Sentiment (monthly)",
}

YFINANCE_FALLBACKS = {
    "DCOILWTICO":       "CL=F",      # WTI crude futures
    "VIXCLS":           "^VIX",      # VIX
    "GOLDAMGBD228NLBM": "GC=F",      # Gold futures
    "GS10":             "^TNX",      # 10-yr yield (scaled ×10 in yf)
    "DEXUSEU":          "EURUSD=X",  # EUR/USD (inverse)
    "DTWEXBGS":         "DX-Y.NYB",  # USD index
}

# ── FRED Data Fetcher ─────────────────────────────────────────────────────────

def fetch_fred_series(series_id: str, api_key: str,
                      start: str = START_DATE, end: str = END_DATE) -> Optional[pd.Series]:
    """Fetch a single FRED series via API. Returns None on failure."""
    cache_file = MACRO_DIR / f"fred_{series_id}.pkl"

    # Check cache (1-day TTL)
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            try:
                with open(cache_file, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        params = urllib.parse.urlencode({
            "series_id":     series_id,
            "api_key":       api_key,
            "file_type":     "json",
            "observation_start": start,
            "observation_end":   end,
        })
        url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())

        if "observations" not in data:
            print(f"  FRED {series_id}: no observations in response", file=sys.stderr)
            return None

        records = [(o["date"], o["value"]) for o in data["observations"]
                   if o["value"] != "."]
        if not records:
            return None

        dates, values = zip(*records)
        s = pd.Series(
            [float(v) for v in values],
            index=pd.to_datetime(dates),
            name=series_id,
        )
        s = s.sort_index()

        with open(cache_file, "wb") as f:
            pickle.dump(s, f)
        return s

    except Exception as e:
        print(f"  FRED {series_id}: {e}", file=sys.stderr)
        return None


def fetch_yf_series(symbol: str, name: str,
                    start: str = START_DATE, end: str = END_DATE) -> Optional[pd.Series]:
    """Fetch a daily series from yfinance. Returns None on failure."""
    cache_file = MACRO_DIR / f"yf_{symbol.replace('^','').replace('=','').replace('/','')}.pkl"

    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < 86400:
            try:
                with open(cache_file, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass

    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            return None
        s = hist["Close"].dropna()
        s.name = name
        with open(cache_file, "wb") as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f"  yf {symbol}: {e}", file=sys.stderr)
        return None


def load_macro_data(fred_key: Optional[str] = None) -> Dict[str, pd.Series]:
    """
    Load all macro series. Uses FRED if key provided, yfinance fallbacks otherwise.
    Returns dict of {series_id: pd.Series} with daily frequency (forward-filled).
    """
    print("  Loading macro data...")
    macro = {}

    # Series to fetch — FRED preferred, yfinance fallback
    for series_id in FRED_SERIES:
        if fred_key:
            s = fetch_fred_series(series_id, fred_key)
            if s is not None:
                macro[series_id] = s
                print(f"    ✓ FRED {series_id} ({len(s)} obs)")
                continue

        # yfinance fallback
        if series_id in YFINANCE_FALLBACKS:
            yf_sym = YFINANCE_FALLBACKS[series_id]
            s = fetch_yf_series(yf_sym, series_id)
            if s is not None:
                # Special transforms
                if series_id == "GS10":
                    s = s / 10.0   # yfinance TNX is yield × 10
                if series_id == "DEXUSEU":
                    s = 1.0 / s    # EUR/USD → USD/EUR
                macro[series_id] = s
                print(f"    ✓ yf fallback {yf_sym} → {series_id} ({len(s)} obs)")

    print(f"  Loaded {len(macro)} macro series")
    return macro


def build_macro_frame(macro: Dict[str, pd.Series],
                      prices_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Align all macro series to a common daily price index.
    Monthly/weekly FRED series are forward-filled to daily.
    Normalizes timezones: FRED series are tz-naive, yfinance index may be tz-aware.
    """
    # Strip timezone from price index for alignment (FRED data is always tz-naive)
    if prices_index.tzinfo is not None:
        align_index = prices_index.tz_localize(None)
    else:
        align_index = prices_index

    frames = {}
    for k, s in macro.items():
        # Normalize series index timezone
        if hasattr(s.index, 'tzinfo') and s.index.tzinfo is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        # Reindex to price dates, forward fill (lag = data release delay)
        reindexed = s.reindex(align_index, method="ffill")
        frames[k] = reindexed

    df = pd.DataFrame(frames, index=align_index)
    return df


# ── Macro Regime Classifier ───────────────────────────────────────────────────

def classify_regimes(mf: pd.DataFrame) -> pd.DataFrame:
    """
    Given aligned macro DataFrame, return boolean regime flags per day.

    Regimes:
      oil_shock    : WTI > 90-day rolling mean + 1.5 std
      oil_high     : WTI > 90-day rolling mean (weaker signal)
      inflationary : CPI YoY > 3.5% (uses T10YIE as proxy if CPI unavailable)
      stress       : VIX > 25 OR HY spread > 500
      tightening   : 2y10y spread < 0 OR Fed Funds rising 6m
      calm         : none of the above
      iran_proxy   : oil_shock AND (inflationary OR stress)  [current scenario]
    """
    regimes = pd.DataFrame(index=mf.index)

    # ── Oil shock ──────────────────────────────────────────────────────────────
    oil_col = "DCOILWTICO"
    if oil_col in mf.columns and mf[oil_col].notna().sum() > 90:
        oil = mf[oil_col].ffill()
        roll_mean = oil.rolling(90, min_periods=30).mean()
        roll_std  = oil.rolling(90, min_periods=30).std()
        regimes["oil_shock"] = oil > (roll_mean + 1.5 * roll_std)
        regimes["oil_high"]  = oil > roll_mean
        regimes["oil_low"]   = oil < (roll_mean - 0.5 * roll_std)
    else:
        regimes["oil_shock"] = False
        regimes["oil_high"]  = False
        regimes["oil_low"]   = True

    # ── Inflation regime ───────────────────────────────────────────────────────
    if "CPIAUCSL" in mf.columns and mf["CPIAUCSL"].notna().sum() > 12:
        cpi = mf["CPIAUCSL"].ffill()
        cpi_yoy = cpi.pct_change(252) * 100   # approx YoY (daily index)
        regimes["inflationary"] = cpi_yoy > 3.5
        regimes["low_inflation"] = cpi_yoy < 2.0
    elif "T10YIE" in mf.columns and mf["T10YIE"].notna().sum() > 90:
        # Breakeven as inflation proxy
        bie = mf["T10YIE"].ffill()
        regimes["inflationary"] = bie > 2.8    # breakeven above 2.8% = market pricing inflation
        regimes["low_inflation"] = bie < 2.0
    else:
        regimes["inflationary"] = False
        regimes["low_inflation"] = True

    # ── Stress regime ─────────────────────────────────────────────────────────
    stress_flags = pd.Series(False, index=mf.index)
    if "VIXCLS" in mf.columns and mf["VIXCLS"].notna().sum() > 90:
        vix = mf["VIXCLS"].ffill()
        stress_flags |= (vix > 25)
    if "BAMLH0A0HYM2" in mf.columns and mf["BAMLH0A0HYM2"].notna().sum() > 90:
        hy = mf["BAMLH0A0HYM2"].ffill()
        stress_flags |= (hy > 500)
    regimes["stress"] = stress_flags
    regimes["low_stress"] = ~stress_flags

    # ── Tightening regime ─────────────────────────────────────────────────────
    tight_flags = pd.Series(False, index=mf.index)
    if "T10Y2Y" in mf.columns and mf["T10Y2Y"].notna().sum() > 90:
        spread = mf["T10Y2Y"].ffill()
        tight_flags |= (spread < 0)         # inverted yield curve
    elif "GS10" in mf.columns and "GS2" in mf.columns:
        gs10 = mf["GS10"].ffill()
        gs2  = mf["GS2"].ffill()
        spread = gs10 - gs2
        tight_flags |= (spread < 0)
    if "DFF" in mf.columns and mf["DFF"].notna().sum() > 90:
        ff = mf["DFF"].ffill()
        # Rising if 6-month change > 0.25%
        ff_trend = ff - ff.shift(126)
        tight_flags |= (ff_trend > 0.25)
    regimes["tightening"] = tight_flags
    regimes["easing"] = pd.Series(False, index=mf.index)
    if "DFF" in mf.columns and mf["DFF"].notna().sum() > 90:
        ff = mf["DFF"].ffill()
        ff_trend = ff - ff.shift(126)
        regimes["easing"] = (ff_trend < -0.25)

    # ── Gold bull ─────────────────────────────────────────────────────────────
    if "GOLDAMGBD228NLBM" in mf.columns and mf["GOLDAMGBD228NLBM"].notna().sum() > 90:
        gold = mf["GOLDAMGBD228NLBM"].ffill()
        gold_mom = gold.pct_change(126)    # 6-month gold momentum
        regimes["gold_bull"] = gold_mom > 0.05
    else:
        regimes["gold_bull"] = False

    # ── Dollar regime ─────────────────────────────────────────────────────────
    if "DTWEXBGS" in mf.columns and mf["DTWEXBGS"].notna().sum() > 90:
        usd = mf["DTWEXBGS"].ffill()
        usd_mom = usd.pct_change(126)
        regimes["strong_dollar"] = usd_mom > 0.03
        regimes["weak_dollar"]   = usd_mom < -0.03
    else:
        regimes["strong_dollar"] = False
        regimes["weak_dollar"]   = False

    # ── Iran proxy scenario ───────────────────────────────────────────────────
    # The specific current scenario: oil shock + inflation + possible stress
    regimes["iran_proxy"] = regimes["oil_shock"] & (
        regimes["inflationary"] | regimes["stress"]
    )

    # ── Calm ──────────────────────────────────────────────────────────────────
    regimes["calm"] = (
        ~regimes["oil_shock"] &
        ~regimes["inflationary"] &
        ~regimes["stress"] &
        ~regimes["tightening"]
    )

    return regimes.fillna(False)


# ── Price data fetcher (same as base harness) ─────────────────────────────────

def cache_path(symbol: str) -> Path:
    return CACHE_DIR / f"{symbol.replace('-','_').replace('^','')}_{YEARS}yr.pkl"


def fetch_prices(symbol: str) -> Optional[pd.Series]:
    """Fetch adjusted close prices with disk cache."""
    cp = cache_path(symbol)
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, pd.Series) and len(data) > 100:
                return data
        except Exception:
            pass
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if hist.empty or "Close" not in hist.columns:
            return None
        prices = hist["Close"].dropna()
        if len(prices) < 252:
            return None
        with open(cp, "wb") as f:
            pickle.dump(prices, f)
        return prices
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


# ── Backtest engine ───────────────────────────────────────────────────────────

def backtest(prices: pd.Series, signals: pd.Series, position_type: str) -> dict:
    common = prices.index.intersection(signals.index)
    if len(common) < 50:
        return {}
    p = prices.loc[common]
    s = signals.loc[common].shift(1).fillna(0)

    if position_type == "long":
        pos = s.clip(lower=0)
    elif position_type == "short":
        pos = s.clip(upper=0).abs()
    else:
        pos = s

    daily_ret = p.pct_change().fillna(0)
    if position_type == "short":
        strategy_ret = daily_ret * s.clip(upper=0) * -1
    else:
        strategy_ret = daily_ret * pos

    strategy_ret = strategy_ret.fillna(0)
    cum = (1 + strategy_ret).cumprod()
    raw_return = float(cum.iloc[-1] - 1)
    n_years = len(strategy_ret) / 252
    cagr = float((1 + raw_return) ** (1 / max(n_years, 0.1)) - 1) if raw_return > -1 else float("-inf")

    mu  = strategy_ret.mean()
    std = strategy_ret.std()
    sharpe = float(mu / std * math.sqrt(252)) if std > 0 else 0.0

    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    max_dd = float(drawdown.min())

    if position_type == "long":
        n_trades = int((s.clip(lower=0).diff().abs() > 0).sum())
    elif position_type == "short":
        n_trades = int((s.clip(upper=0).diff().abs() > 0).sum())
    else:
        n_trades = int((s.diff().abs() > 0).sum())

    return {
        "raw_return":   round(raw_return * 100, 2),
        "cagr":         round(cagr * 100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "n_trades":     n_trades,
        "n_days":       len(strategy_ret),
        "active_pct":   round(float((pos != 0).mean()) * 100, 1),
    }


def buy_and_hold(prices: pd.Series) -> dict:
    if prices is None or len(prices) < 2:
        return {}
    r = float(prices.iloc[-1] / prices.iloc[0] - 1)
    n_years = len(prices) / 252
    cagr = float((1 + r) ** (1 / max(n_years, 0.1)) - 1) if r > -1 else float("-inf")
    daily = prices.pct_change().fillna(0)
    sharpe = float(daily.mean() / daily.std() * math.sqrt(252)) if daily.std() > 0 else 0
    cum = (1 + daily).cumprod()
    max_dd = float(((cum - cum.cummax()) / cum.cummax()).min())
    return {
        "raw_return":   round(r * 100, 2),
        "cagr":         round(cagr * 100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "n_trades":     1,
        "n_days":       len(prices),
    }


# ── Strategy base ─────────────────────────────────────────────────────────────

class Strategy(ABC):
    family:      str = "unknown"
    name:        str = "base"
    description: str = ""

    @abstractmethod
    def signals(self, prices: pd.Series) -> pd.Series:
        """Return pd.Series of {-1, 0, 1} aligned to prices.index."""

    def __repr__(self):
        return f"{self.family}/{self.name}"


# ── Macro Regime Gate Wrapper ─────────────────────────────────────────────────

class RegimeGated(Strategy):
    """
    Wraps any Strategy, masking signals to zero outside a specified regime.
    The regime is a boolean pd.Series aligned to dates.
    """
    def __init__(self, base: Strategy, regime: pd.Series, regime_name: str):
        self.base        = base
        self.regime      = regime
        self.regime_name = regime_name
        self.family      = base.family + "_macro"
        self.name        = f"{base.name}_IN_{regime_name}"
        self.description = f"{base.description} [only in {regime_name}]"

    def signals(self, prices: pd.Series) -> pd.Series:
        raw = self.base.signals(prices)
        # Align regime to price dates (forward fill for gaps)
        reg = self.regime.reindex(prices.index, method="ffill").fillna(False)
        # Zero out signals outside the regime
        masked = raw.copy()
        masked[~reg] = 0
        return masked


# ── Macro Signal Strategies (new for rounds 11-15) ───────────────────────────

class OilMomentum(Strategy):
    """
    Go long on energy stocks when WTI oil is in uptrend.
    Signal: oil 20d > oil 60d SMA.
    """
    family = "macro"

    def __init__(self, oil: pd.Series, fast: int = 20, slow: int = 60):
        self.oil  = oil
        self.fast = fast
        self.slow = slow
        self.name = f"OilMom_{fast}_{slow}"
        self.description = f"Long when WTI {fast}d > {slow}d SMA"

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method="ffill").ffill()
        fast_ma = oil.rolling(self.fast, min_periods=10).mean()
        slow_ma = oil.rolling(self.slow, min_periods=20).mean()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[fast_ma > slow_ma]  =  1
        sig[fast_ma <= slow_ma] = -1
        sig[fast_ma.isna() | slow_ma.isna()] = 0
        return sig


class OilShockLong(Strategy):
    """
    Long when oil is in an acute shock (>1σ above 90d mean).
    Hypothesis: energy stocks rally during oil shocks.
    """
    family = "macro"

    def __init__(self, oil: pd.Series, window: int = 90, threshold: float = 1.0):
        self.oil       = oil
        self.window    = window
        self.threshold = threshold
        self.name      = f"OilShock_{window}_{threshold}"
        self.description = f"Long during WTI oil shock (>{threshold}σ above {window}d mean)"

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method="ffill").ffill()
        mean = oil.rolling(self.window, min_periods=30).mean()
        std  = oil.rolling(self.window, min_periods=30).std()
        z    = (oil - mean) / std.replace(0, np.nan)
        sig  = pd.Series(0, index=prices.index, dtype=float)
        sig[z >  self.threshold] =  1
        sig[z < -self.threshold] = -1
        sig[z.isna()] = 0
        return sig


class InflationBreakoutLong(Strategy):
    """
    Long when 10Y breakeven inflation is rising (inflation expectations accelerating).
    Favors real assets, energy, materials.
    """
    family = "macro"

    def __init__(self, bie: pd.Series, window: int = 63):
        self.bie    = bie
        self.window = window
        self.name   = f"InfBreakout_{window}"
        self.description = f"Long when breakeven inflation rising over {window}d"

    def signals(self, prices: pd.Series) -> pd.Series:
        bie = self.bie.reindex(prices.index, method="ffill").ffill()
        trend = bie - bie.shift(self.window)
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[trend > 0.1]   =  1
        sig[trend < -0.1]  = -1
        sig[trend.isna()]  =  0
        return sig


class YieldCurveTrend(Strategy):
    """
    Long when yield curve steepening (easing / recovery), short when inverting.
    Hypothesis: steepening → risk-on, inversion → caution.
    """
    family = "macro"

    def __init__(self, gs10: pd.Series, gs2: pd.Series, window: int = 63):
        self.gs10   = gs10
        self.gs2    = gs2
        self.window = window
        self.name   = f"YieldCurve_{window}"
        self.description = f"Trade yield curve steepening/inversion ({window}d trend)"

    def signals(self, prices: pd.Series) -> pd.Series:
        gs10 = self.gs10.reindex(prices.index, method="ffill").ffill()
        gs2  = self.gs2.reindex(prices.index, method="ffill").ffill()
        spread = gs10 - gs2
        trend  = spread - spread.shift(self.window)
        sig    = pd.Series(0, index=prices.index, dtype=float)
        sig[spread > 0.5]  =  1   # steep & positive
        sig[spread < 0.0]  = -1   # inverted
        sig[trend.isna()]  =  0
        return sig


class GoldFlightSafety(Strategy):
    """
    Long when gold is rallying (flight to safety indicator).
    Gold up = risk-off = favor defensives over tech.
    """
    family = "macro"

    def __init__(self, gold: pd.Series, window: int = 63):
        self.gold   = gold
        self.window = window
        self.name   = f"GoldFlight_{window}"
        self.description = f"Long when gold rising over {window}d (flight-to-safety)"

    def signals(self, prices: pd.Series) -> pd.Series:
        gold = self.gold.reindex(prices.index, method="ffill").ffill()
        mom  = gold.pct_change(self.window)
        sig  = pd.Series(0, index=prices.index, dtype=float)
        sig[mom > 0.05]   =  1   # gold up >5% in window
        sig[mom < -0.05]  = -1   # gold down >5%
        sig[mom.isna()]   =  0
        return sig


class CreditSpreadFilter(Strategy):
    """
    Long only when HY credit spread < threshold (low systemic risk).
    Short when spreads blow out (financial stress).
    """
    family = "macro"

    def __init__(self, hy_spread: pd.Series, long_thresh: float = 400,
                 short_thresh: float = 600, name: str = "CreditFilter"):
        self.hy_spread    = hy_spread
        self.long_thresh  = long_thresh
        self.short_thresh = short_thresh
        self.name         = name
        self.description  = f"Long when HY spread <{long_thresh}bp, short >{short_thresh}bp"

    def signals(self, prices: pd.Series) -> pd.Series:
        hy = self.hy_spread.reindex(prices.index, method="ffill").ffill()
        sig = pd.Series(0, index=prices.index, dtype=float)
        sig[hy < self.long_thresh]  =  1
        sig[hy > self.short_thresh] = -1
        sig[hy.isna()]              =  0
        return sig


class VIXRegimeMomentum(Strategy):
    """
    Momentum-based strategy gated by VIX regime.
    High VIX (>30): go defensive / short.
    Low VIX (<18): follow momentum aggressively.
    Mid VIX: neutral.
    """
    family = "macro"

    def __init__(self, vix: pd.Series, mom_window: int = 63,
                 vix_low: float = 18, vix_high: float = 30):
        self.vix        = vix
        self.mom_window = mom_window
        self.vix_low    = vix_low
        self.vix_high   = vix_high
        self.name       = f"VIXMom_{mom_window}_{vix_low}_{vix_high}"
        self.description = f"Momentum {mom_window}d, gated by VIX ({vix_low}/{vix_high})"

    def signals(self, prices: pd.Series) -> pd.Series:
        vix = self.vix.reindex(prices.index, method="ffill").ffill()
        mom = prices.pct_change(self.mom_window)
        sig = pd.Series(0, index=prices.index, dtype=float)

        # Low VIX: follow momentum
        low_vix_mask = vix < self.vix_low
        sig[low_vix_mask & (mom > 0)]  =  1
        sig[low_vix_mask & (mom <= 0)] = -1

        # High VIX: contrarian / short
        high_vix_mask = vix > self.vix_high
        sig[high_vix_mask] = -1   # defensive in panic

        sig[vix.isna() | mom.isna()] = 0
        return sig


class MacroComposite(Strategy):
    """
    Composite macro signal: oil_mom + inflation + gold + yield_curve.
    Long when ≥2 macro signals agree bullish, short when ≥2 bearish.
    """
    family = "macro"

    def __init__(self, oil: Optional[pd.Series] = None,
                 bie: Optional[pd.Series] = None,
                 gold: Optional[pd.Series] = None,
                 gs10: Optional[pd.Series] = None,
                 gs2: Optional[pd.Series] = None,
                 vix: Optional[pd.Series] = None,
                 name: str = "MacroComposite"):
        self.oil  = oil
        self.bie  = bie
        self.gold = gold
        self.gs10 = gs10
        self.gs2  = gs2
        self.vix  = vix
        self.name = name
        self.description = "Composite: oil+inflation+gold+yieldcurve macro vote"

    def signals(self, prices: pd.Series) -> pd.Series:
        votes = pd.DataFrame(index=prices.index)

        # Oil momentum (+1 if oil uptrend, -1 if downtrend)
        if self.oil is not None:
            oil = self.oil.reindex(prices.index, method="ffill").ffill()
            oil_ma20 = oil.rolling(20, min_periods=10).mean()
            oil_ma60 = oil.rolling(60, min_periods=20).mean()
            votes["oil"] = 0.0
            votes.loc[oil_ma20 > oil_ma60, "oil"] =  1
            votes.loc[oil_ma20 <= oil_ma60, "oil"] = -1

        # Inflation breakeven (+1 if rising, -1 if falling)
        if self.bie is not None:
            bie = self.bie.reindex(prices.index, method="ffill").ffill()
            bie_trend = bie - bie.shift(63)
            votes["bie"] = 0.0
            votes.loc[bie_trend > 0.1, "bie"] =  1
            votes.loc[bie_trend < -0.1, "bie"] = -1

        # Gold momentum (+1 if gold rising = risk-off defensive)
        if self.gold is not None:
            gold = self.gold.reindex(prices.index, method="ffill").ffill()
            gold_mom = gold.pct_change(63)
            votes["gold"] = 0.0
            votes.loc[gold_mom > 0.05, "gold"] =  1
            votes.loc[gold_mom < -0.05, "gold"] = -1

        # Yield curve (+1 if steep/positive = risk-on)
        if self.gs10 is not None and self.gs2 is not None:
            g10 = self.gs10.reindex(prices.index, method="ffill").ffill()
            g2  = self.gs2.reindex(prices.index, method="ffill").ffill()
            spread = g10 - g2
            votes["yc"] = 0.0
            votes.loc[spread > 0.5, "yc"] =  1
            votes.loc[spread < 0.0, "yc"] = -1

        # VIX gate (override: -1 in panic)
        if self.vix is not None:
            vix = self.vix.reindex(prices.index, method="ffill").ffill()
            votes["vix"] = 0.0
            votes.loc[vix < 18, "vix"] =  0.5
            votes.loc[vix > 30, "vix"] = -1.5  # strong veto

        if votes.empty:
            return pd.Series(0, index=prices.index, dtype=float)

        score = votes.mean(axis=1)
        sig   = pd.Series(0, index=prices.index, dtype=float)
        sig[score >  0.3] =  1
        sig[score < -0.3] = -1
        return sig


class OilInflationCombo(Strategy):
    """
    CURRENT SCENARIO: Iran war oil shock + inflationary cascade.
    Long energy/materials when oil shock active + inflation rising.
    Hypothesis: best strategy for the current macro environment.
    """
    family = "macro"

    def __init__(self, oil: pd.Series, bie_or_cpi: pd.Series,
                 oil_window: int = 90, inf_window: int = 63,
                 name: str = "OilInflationCombo"):
        self.oil         = oil
        self.inf         = bie_or_cpi
        self.oil_window  = oil_window
        self.inf_window  = inf_window
        self.name        = name
        self.description = "Oil shock + inflation combo (Iran scenario)"

    def signals(self, prices: pd.Series) -> pd.Series:
        oil = self.oil.reindex(prices.index, method="ffill").ffill()
        inf = self.inf.reindex(prices.index, method="ffill").ffill()

        # Oil: is it elevated vs history?
        oil_mean = oil.rolling(self.oil_window, min_periods=30).mean()
        oil_std  = oil.rolling(self.oil_window, min_periods=30).std()
        oil_z    = (oil - oil_mean) / oil_std.replace(0, np.nan)

        # Inflation: is it rising?
        inf_trend = inf - inf.shift(self.inf_window)

        sig = pd.Series(0, index=prices.index, dtype=float)

        # Both elevated → strong long (energy/materials benefit)
        both_bullish = (oil_z > 1.0) & (inf_trend > 0)
        sig[both_bullish] = 1

        # Oil shock but deflating → unclear, stay flat
        # Oil falling + deflation → short
        both_bearish = (oil_z < -0.5) & (inf_trend < 0)
        sig[both_bearish] = -1

        sig[oil_z.isna() | inf_trend.isna()] = 0
        return sig


# ── Regime analysis reporter ──────────────────────────────────────────────────

def analyze_regimes(regimes: pd.DataFrame, start: str = "2010-01-01") -> None:
    """Print summary of how much time the market spent in each regime."""
    print("\n" + "="*70)
    print("MACRO REGIME ANALYSIS")
    print("="*70)
    idx = regimes.index.tz_localize(None) if regimes.index.tzinfo is not None else regimes.index
    subset = regimes.iloc[idx >= pd.Timestamp(start)]
    total  = len(subset)
    print(f"\nPeriod: {subset.index[0].date()} to {subset.index[-1].date()} ({total} trading days)")
    print(f"\n{'Regime':<25} {'Days':>6} {'%Time':>7} {'Description'}")
    print("-"*70)

    descriptions = {
        "oil_shock":    "WTI >1.5σ above 90d rolling mean",
        "oil_high":     "WTI above 90d rolling mean",
        "oil_low":      "WTI below rolling mean -0.5σ",
        "inflationary": "CPI YoY >3.5% or BIE >2.8%",
        "low_inflation":"CPI YoY <2% or BIE <2%",
        "stress":       "VIX >25 or HY spread >500bp",
        "low_stress":   "VIX <25 and HY spread <500bp",
        "tightening":   "Inverted curve OR FF rising",
        "easing":       "Fed Funds falling",
        "gold_bull":    "Gold 6m momentum >+5%",
        "strong_dollar":"USD Broad index 6m >+3%",
        "weak_dollar":  "USD Broad index 6m <-3%",
        "iran_proxy":   "Oil shock + (inflation or stress)",
        "calm":         "No active macro stressors",
    }

    for col in subset.columns:
        days = int(subset[col].sum())
        pct  = days / total * 100
        desc = descriptions.get(col, "")
        print(f"  {col:<23} {days:>6,} {pct:>6.1f}%  {desc}")

    # Regime co-occurrence
    print(f"\n  CURRENT REGIME STATUS (as of {subset.index[-1].date()}):")
    last = subset.iloc[-1]
    active = [c for c in last.index if last[c]]
    if active:
        for r in active:
            print(f"    ✓ {r}")
    else:
        print("    (no active regimes detected)")
    print()


# ── Round runner ─────────────────────────────────────────────────────────────

def run_round(round_num: int, strategies: List[Strategy],
              position_types: List[str] = None,
              tickers: Optional[List[str]] = None,
              macro_data: Optional[Dict] = None,
              regimes: Optional[pd.DataFrame] = None) -> dict:
    """Run a single eval round. Returns results dict."""
    if position_types is None:
        position_types = ["long"]   # Macro rounds: long only (most practical)

    tickers = tickers or list(UNIVERSE.keys())
    results = []
    bnh_results = []

    print(f"\n{'='*70}")
    print(f"ROUND {round_num} — {len(strategies)} strategies × {len(tickers)} tickers × {len(position_types)} positions")
    total = len(strategies) * len(tickers) * len(position_types)
    print(f"Total backtests: {total:,}")
    print(f"{'='*70}\n")

    done = 0
    for sym in tickers:
        prices = fetch_prices(sym)
        if prices is None:
            continue

        bnh = buy_and_hold(prices)
        bnh["symbol"] = sym
        bnh_results.append(bnh)

        for strat in strategies:
            try:
                sigs = strat.signals(prices)
            except Exception as e:
                continue

            for pt in position_types:
                res = backtest(prices, sigs, pt)
                if not res:
                    continue
                res["symbol"]   = sym
                res["strategy"] = strat.name
                res["family"]   = strat.family
                res["position"] = pt
                res["sector"]   = next(
                    (s for s, tks in SECTOR_MAP.items() if sym in tks), "other"
                )
                results.append(res)
                done += 1

        if done % 500 == 0 and done > 0:
            print(f"  Progress: {done:,}/{total:,} ({done/total*100:.0f}%)")

    # Summarize
    if not results:
        print("  No results generated!")
        return {}

    df = pd.DataFrame(results)
    bnh_df = pd.DataFrame(bnh_results)
    bnh_avg = bnh_df["raw_return"].mean() if not bnh_df.empty else 0

    # Strategy-level aggregation
    strat_agg = (
        df.groupby(["strategy", "family", "position"])
          .agg(
              avg_return   = ("raw_return",   "mean"),
              median_return= ("raw_return",   "median"),
              avg_sharpe   = ("sharpe",        "mean"),
              avg_cagr     = ("cagr",          "mean"),
              beat_bnh_pct = ("raw_return",    lambda x: (x > bnh_avg).mean() * 100),
              avg_active   = ("active_pct",    "mean") if "active_pct" in df.columns else ("raw_return", "count"),
              n_tickers    = ("symbol",        "nunique"),
          )
          .reset_index()
          .sort_values("avg_return", ascending=False)
    )

    # Family-level
    family_agg = (
        df.groupby("family")
          .agg(avg_return=("raw_return", "mean"))
          .sort_values("avg_return", ascending=False)
    )

    # Sector analysis
    sector_agg = (
        df.groupby("sector")
          .agg(avg_return=("raw_return", "mean"),
               bnh=("raw_return", "count"))
          .sort_values("avg_return", ascending=False)
    )

    round_results = {
        "round":        round_num,
        "timestamp":    datetime.now().isoformat(),
        "n_strategies": len(strategies),
        "n_tickers":    len(tickers),
        "n_results":    len(results),
        "bnh_avg":      round(bnh_avg, 2),
        "top20":        strat_agg.head(20).to_dict("records"),
        "family_ranking": family_agg.to_dict()["avg_return"],
        "sector_ranking": sector_agg["avg_return"].to_dict(),
        "all_strategies": strat_agg.to_dict("records"),
    }

    out_path = ROUNDS_DIR / f"macro_round_{round_num:02d}.json"
    with open(out_path, "w") as f:
        json.dump(round_results, f, indent=2, default=str)

    # Print summary
    print(f"\n  B&H avg: {bnh_avg:.1f}%")
    print(f"\n  TOP 10 STRATEGIES (Round {round_num}):")
    print(f"  {'Strategy':<35} {'AvgRet%':>8} {'Sharpe':>7} {'BeatB&H%':>9}")
    print(f"  {'-'*63}")
    for _, row in strat_agg.head(10).iterrows():
        print(f"  {row['strategy']:<35} {row['avg_return']:>8.1f}% {row['avg_sharpe']:>7.3f} {row['beat_bnh_pct']:>8.1f}%")

    print(f"\n  FAMILY RANKING:")
    for fam, ret in family_agg["avg_return"].items():
        print(f"    {fam:<25} {ret:>8.1f}%")

    print(f"\n  SECTOR RANKING:")
    for sec, ret in sector_agg["avg_return"].items():
        print(f"    {sec:<20} {ret:>8.1f}%")

    print(f"\n  Saved → {out_path}")
    return round_results


# ── Main autoresearch runner ───────────────────────────────────────────────────

def build_strategies(macro: Dict[str, pd.Series],
                     regimes: Optional[pd.DataFrame],
                     round_num: int) -> List[Strategy]:
    """Build strategy list for a given round number."""

    # Extract macro series (with None fallbacks)
    oil  = macro.get("DCOILWTICO")
    bie  = macro.get("T10YIE")
    gold = macro.get("GOLDAMGBD228NLBM")
    gs10 = macro.get("GS10")
    gs2  = macro.get("GS2")
    vix  = macro.get("VIXCLS")
    hy   = macro.get("BAMLH0A0HYM2")
    ff   = macro.get("DFF")

    strategies = []

    # ── R11: Best existing strategies + regime gates ──────────────────────────
    if round_num == 11:
        # Import top strategies from base harness results
        # MACD variants (known best from rounds 1-10)
        from harness import MACDHistogram as MACD, PriceMomentum, VolAdjMomentum as VolAdjMom, MomentumShortTerm

        base_strats = [
            MACD(5, 11, 4,  name="MACD_5_11_4"),
            MACD(5, 12, 4,  name="MACD_5_12_4"),
            MACD(6, 12, 5,  name="MACD_6_12_5"),
            MACD(8, 17, 9,  name="MACD_8_17_9"),
            MACD(5, 13, 4,  name="MACD_5_13_4"),
            PriceMomentum(252, 21, "PM_12_1"),
            PriceMomentum(126, 21, "PM_6_1"),
            MomentumShortTerm(),
            VolAdjMom(252, 21, "VAM_252"),
            VolAdjMom(126, 21, "VAM_126"),
        ]

        # Add base strategies (all-weather)
        strategies.extend(base_strats)

        # Add regime-gated versions
        if regimes is not None:
            for regime_name in ["oil_shock", "oil_high", "inflationary", "low_stress",
                                 "calm", "iran_proxy", "gold_bull", "tightening"]:
                if regime_name in regimes.columns:
                    reg_series = regimes[regime_name]
                    for s in base_strats[:5]:  # top 5 with all regime variants
                        strategies.append(RegimeGated(s, reg_series, regime_name))

        # Pure macro strategies
        if oil is not None:
            strategies.append(OilMomentum(oil, 20, 60))
            strategies.append(OilMomentum(oil, 10, 30))
            strategies.append(OilMomentum(oil, 30, 90))
            strategies.append(OilShockLong(oil, 90, 1.0))
            strategies.append(OilShockLong(oil, 90, 1.5))
            strategies.append(OilShockLong(oil, 60, 1.0))

        if bie is not None:
            strategies.append(InflationBreakoutLong(bie, 63))
            strategies.append(InflationBreakoutLong(bie, 126))

        if vix is not None:
            strategies.append(VIXRegimeMomentum(vix, 63, 18, 30))
            strategies.append(VIXRegimeMomentum(vix, 21, 20, 28))
            strategies.append(VIXRegimeMomentum(vix, 126, 15, 25))

        if gold is not None:
            strategies.append(GoldFlightSafety(gold, 63))
            strategies.append(GoldFlightSafety(gold, 126))

        if hy is not None:
            strategies.append(CreditSpreadFilter(hy, 400, 600, "CreditFilter_400_600"))
            strategies.append(CreditSpreadFilter(hy, 350, 500, "CreditFilter_350_500"))
            strategies.append(CreditSpreadFilter(hy, 450, 700, "CreditFilter_450_700"))

    # ── R12: Macro momentum combos ────────────────────────────────────────────
    elif round_num == 12:
        from harness import MACDHistogram as MACD

        if oil is not None and bie is not None:
            strategies.append(OilInflationCombo(oil, bie, 90, 63, "OilInfCombo_90_63"))
            strategies.append(OilInflationCombo(oil, bie, 60, 42, "OilInfCombo_60_42"))
            strategies.append(OilInflationCombo(oil, bie, 120, 90, "OilInfCombo_120_90"))

        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull"))
            strategies.append(MacroComposite(oil, bie, gold, None, None, vix, "MacroNoYC"))
            strategies.append(MacroComposite(oil, bie, None, gs10, gs2, None, "MacroRates"))
        elif oil is not None and vix is not None:
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroAvail"))

        # Oil momentum with different parameters
        if oil is not None:
            for fast, slow in [(5,20), (10,50), (15,45), (20,60), (30,90), (5,50), (10,30)]:
                strategies.append(OilMomentum(oil, fast, slow))

        # VIX momentum variants
        if vix is not None:
            for window, lo, hi in [(21,15,25), (42,18,30), (63,20,35), (126,18,30)]:
                strategies.append(VIXRegimeMomentum(vix, window, lo, hi))

        # Gold variants
        if gold is not None:
            for w in [21, 42, 63, 126, 189]:
                strategies.append(GoldFlightSafety(gold, w))

        # Yield curve
        if gs10 is not None and gs2 is not None:
            for w in [21, 42, 63, 126]:
                strategies.append(YieldCurveTrend(gs10, gs2, w))

    # ── R13: Best macro strategies refined ────────────────────────────────────
    elif round_num == 13:
        # Load R12 insights to identify best parameters
        r12_path = ROUNDS_DIR / "macro_round_12.json"
        if r12_path.exists():
            with open(r12_path) as f:
                r12 = json.load(f)
            top_names = {r["strategy"] for r in r12.get("top20", [])}
            print(f"  R12 top strategies: {top_names}")

        # All combinations of macro signals vs. best base strategy
        from harness import MACDHistogram as MACD
        best_base = MACD(5, 11, 4, name="MACD_5_11_4")

        if oil is not None:
            # Test oil shock filtering on best base
            for thresh in [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]:
                s = OilShockLong(oil, 90, thresh)
                strategies.append(s)
                if regimes is not None and "oil_shock" in regimes:
                    strategies.append(RegimeGated(best_base, regimes["oil_shock"], "oil_shock"))

        if vix is not None:
            for lo, hi in [(15,25), (18,28), (18,30), (20,30), (20,35), (15,35)]:
                strategies.append(VIXRegimeMomentum(vix, 63, lo, hi))

        if oil is not None and vix is not None:
            # Oil × VIX composite
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_v2"))

        if gold is not None:
            for w in [30, 45, 60, 90, 120, 180]:
                strategies.append(GoldFlightSafety(gold, w))

        if hy is not None:
            for lt, st in [(300,500), (350,550), (400,600), (450,650), (500,750)]:
                strategies.append(CreditSpreadFilter(hy, lt, st, f"Credit_{lt}_{st}"))

    # ── R14: Regime-switching ensemble ────────────────────────────────────────
    elif round_num == 14:
        # Use best macro strategies from R12/R13
        from harness import MACDHistogram as MACD

        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
            strategies.append(OilMomentum(oil, 5, 20))
            strategies.append(OilShockLong(oil, 90, 1.0))
        if vix is not None:
            strategies.append(VIXRegimeMomentum(vix, 63, 18, 30))
        if oil is not None and bie is not None:
            strategies.append(OilInflationCombo(oil, bie, 90, 63, "IranScenario"))
        if all(x is not None for x in [oil, bie, gold, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_R14"))

        # Best from base harness, regime-filtered
        macd_best = MACD(5, 11, 4, name="MACD_5_11_4")
        if regimes is not None:
            for rname in ["oil_shock", "inflationary", "iran_proxy", "low_stress", "gold_bull"]:
                if rname in regimes.columns:
                    strategies.append(RegimeGated(macd_best, regimes[rname], rname))

    # ── R15: Best of everything ────────────────────────────────────────────────
    elif round_num == 15:
        from harness import MACDHistogram as MACD, VolAdjMomentum as VolAdjMom

        # Top all-weather
        strategies.extend([
            MACD(5, 11, 4, name="MACD_5_11_4"),
            MACD(5, 12, 4, name="MACD_5_12_4"),
            VolAdjMom(252, 21, "VAM_252"),
        ])

        # Top macro
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if vix is not None:
            strategies.append(VIXRegimeMomentum(vix, 63, 18, 30))
        if oil is not None and bie is not None:
            strategies.append(OilInflationCombo(oil, bie, 90, 63, "IranScenario"))
        if all(x is not None for x in [oil, bie, gold, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_Final"))

    # ── R16: Full FRED signal sweep ───────────────────────────────────────────
    elif round_num == 16:
        # Now we have CPI, Fed Funds, HY spreads, breakeven — use them all
        from harness import MACDHistogram as MACD, VolAdjMomentum as VolAdjMom

        # Breakeven inflation signal (T10YIE) — now available from FRED
        if bie is not None:
            for w in [21, 42, 63, 126, 189]:
                strategies.append(InflationBreakoutLong(bie, w))

        # Oil + inflation combo — now has real BIE data
        if oil is not None and bie is not None:
            for ow, iw in [(60,42), (90,63), (90,42), (120,63), (120,90)]:
                strategies.append(OilInflationCombo(oil, bie, ow, iw,
                                   f"OilInf_{ow}_{iw}"))

        # HY credit spread strategies — now available
        if hy is not None:
            for lt, st in [(250,400), (300,500), (350,550), (400,600),
                           (450,650), (500,750), (300,600), (400,700)]:
                strategies.append(CreditSpreadFilter(hy, lt, st, f"HY_{lt}_{st}"))

        # Full composite — now has all signals
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_FRED"))
        if all(x is not None for x in [oil, bie, vix]):
            strategies.append(MacroComposite(oil, bie, None, None, None, vix, "MacroCore_FRED"))

        # Oil + VIX combo (strong pair from R11-R15)
        if oil is not None:
            for fast, slow in [(5,20),(8,30),(10,50),(12,40),(15,50),(20,80)]:
                strategies.append(OilMomentum(oil, fast, slow))
        if vix is not None:
            for win, lo, hi in [(21,15,25),(42,18,28),(63,18,30),(63,20,30),(63,20,35),(126,18,30)]:
                strategies.append(VIXRegimeMomentum(vix, win, lo, hi))

        # Gold — refined around 120d winner
        if gold is not None:
            for w in [90, 100, 110, 120, 130, 140, 150]:
                strategies.append(GoldFlightSafety(gold, w))

        # Yield curve (GS10 vs GS2 from FRED — now monthly but forward-filled)
        if gs10 is not None and gs2 is not None:
            for w in [21, 42, 63, 126]:
                strategies.append(YieldCurveTrend(gs10, gs2, w))

    # ── R17: Regime-gated MACD with full FRED regimes ────────────────────────
    elif round_num == 17:
        from harness import MACDHistogram as MACD, VolAdjMomentum as VolAdjMom

        macd_best = MACD(5, 11, 4, name="MACD_5_11_4")
        vam_best  = VolAdjMom(252, 21, "VAM_252")

        # Gate best strategies on all FRED-informed regimes
        if regimes is not None:
            for base in [macd_best, vam_best]:
                for rname in regimes.columns:
                    strategies.append(RegimeGated(base, regimes[rname], rname))

        # Best standalone macro from R16 guesses (will be refined from R16 results)
        if bie is not None:
            strategies.append(InflationBreakoutLong(bie, 63))
            strategies.append(InflationBreakoutLong(bie, 126))
        if hy is not None:
            strategies.append(CreditSpreadFilter(hy, 300, 500, "HY_300_500"))
            strategies.append(CreditSpreadFilter(hy, 350, 550, "HY_350_550"))
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if gold is not None:
            strategies.append(GoldFlightSafety(gold, 120))
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_R17"))

    # ── R18: Champion strategies head-to-head ─────────────────────────────────
    elif round_num == 18:
        from harness import MACDHistogram as MACD, VolAdjMomentum as VolAdjMom

        # Load R16 results to find best
        r16_path = ROUNDS_DIR / "macro_round_16.json"
        top_r16 = []
        if r16_path.exists():
            with open(r16_path) as f:
                r16 = json.load(f)
            top_r16 = [r["strategy"] for r in r16.get("top20", [])[:5]]
            print(f"  R16 top 5: {top_r16}")

        # All-weather champions
        strategies.extend([
            MACD(5, 11, 4, name="MACD_5_11_4"),
            VolAdjMom(252, 21, "VAM_252"),
        ])

        # Best macro from all rounds
        if gold is not None:
            strategies.append(GoldFlightSafety(gold, 120))
        if oil is not None:
            strategies.append(OilMomentum(oil, 10, 50))
        if bie is not None:
            strategies.append(InflationBreakoutLong(bie, 63))
        if hy is not None:
            strategies.append(CreditSpreadFilter(hy, 300, 500, "HY_300_500"))
        if all(x is not None for x in [oil, bie, gold, gs10, gs2, vix]):
            strategies.append(MacroComposite(oil, bie, gold, gs10, gs2, vix, "MacroFull_Champion"))

        # Regime-gated best
        if regimes is not None:
            macd = MACD(5, 11, 4, name="MACD_5_11_4")
            for rname in ["low_stress", "oil_high", "gold_bull", "inflationary", "easing"]:
                if rname in regimes.columns:
                    strategies.append(RegimeGated(macd, regimes[rname], rname))

    return strategies


def generate_insights(results: dict, round_num: int) -> str:
    """Generate text insights from round results."""
    top20 = results.get("top20", [])
    bnh   = results.get("bnh_avg", 0)
    fam   = results.get("family_ranking", {})
    sec   = results.get("sector_ranking", {})

    lines = [
        f"ROUND {round_num} MACRO INSIGHTS",
        "=" * 50,
        f"B&H avg benchmark: {bnh:.1f}%",
        "",
        "Top 5 strategies:",
    ]
    for i, r in enumerate(top20[:5], 1):
        lines.append(f"  {i}. {r['strategy']:<35} {r['avg_return']:.1f}% avg (Sharpe {r['avg_sharpe']:.3f})")

    lines += ["", "Family performance:"]
    for f, v in list(fam.items())[:5]:
        lines.append(f"  {f:<25} {v:.1f}%")

    lines += ["", "Sector performance:"]
    for s, v in list(sec.items())[:5]:
        lines.append(f"  {s:<20} {v:.1f}%")

    # Macro-specific observations
    macro_strats = [r for r in top20 if "macro" in r.get("family","").lower() or
                    any(kw in r.get("strategy","").lower()
                        for kw in ["oil", "vix", "macro", "iran", "gold", "credit", "yield"])]
    if macro_strats:
        lines += ["", f"Macro strategies in top 20: {len(macro_strats)}"]
        for r in macro_strats[:3]:
            lines.append(f"  {r['strategy']:<35} {r['avg_return']:.1f}%")

    regime_strats = [r for r in top20 if "_IN_" in r.get("strategy","")]
    if regime_strats:
        lines += ["", f"Regime-gated strategies in top 20: {len(regime_strats)}"]
        for r in regime_strats[:3]:
            lines.append(f"  {r['strategy']:<35} {r['avg_return']:.1f}%")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Macro-Enhanced Trading Eval")
    parser.add_argument("--round",        type=int, help="Run specific round (11-15)")
    parser.add_argument("--all",          action="store_true", help="Run rounds 11-15 autonomously")
    parser.add_argument("--show-regimes", action="store_true", help="Print macro regime analysis")
    parser.add_argument("--fred-key",     type=str, default=os.environ.get("FRED_API_KEY",""),
                        help="FRED API key (or set FRED_API_KEY env var)")
    parser.add_argument("--symbols",      nargs="+", help="Override ticker list")
    args = parser.parse_args()

    fred_key = args.fred_key or None

    # Load macro data
    macro = load_macro_data(fred_key)

    if not macro:
        print("ERROR: No macro data loaded. Check FRED key or yfinance connectivity.")
        sys.exit(1)

    # Build a common price index using SPY
    spy_prices = fetch_prices("AAPL")
    if spy_prices is None:
        print("ERROR: Cannot fetch price data.")
        sys.exit(1)

    price_idx = spy_prices.index

    # Build aligned macro frame + classify regimes
    mf      = build_macro_frame(macro, price_idx)
    regimes = classify_regimes(mf)

    if args.show_regimes or args.all:
        analyze_regimes(regimes)

    if args.show_regimes and not args.round and not args.all:
        return

    tickers = args.symbols or list(UNIVERSE.keys())

    rounds_to_run = []
    if args.all:
        rounds_to_run = [11, 12, 13, 14, 15]
    elif args.round:
        rounds_to_run = [args.round]
    else:
        print("Specify --round N or --all. Use --show-regimes to inspect macro data.")
        print("Example: PYTHONPATH=/tmp/eval_deps python3 macro_harness.py --round 11")
        return

    all_insights = []
    for rnum in rounds_to_run:
        print(f"\n{'#'*70}")
        print(f"# STARTING ROUND {rnum}")
        print(f"{'#'*70}")

        strategies = build_strategies(macro, regimes, rnum)
        if not strategies:
            print(f"  No strategies built for round {rnum}. Skipping.")
            continue

        results = run_round(rnum, strategies, ["long"], tickers, macro, regimes)
        if results:
            insights = generate_insights(results, rnum)
            print(f"\n{insights}")
            all_insights.append(insights)

    # Save insights
    if all_insights:
        insights_path = ROOT / "macro_insights.md"
        with open(insights_path, "w") as f:
            f.write(f"# Macro Autoresearch Insights\n\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n\n")
            f.write("\n\n---\n\n".join(all_insights))
        print(f"\nInsights saved → {insights_path}")


if __name__ == "__main__":
    main()
