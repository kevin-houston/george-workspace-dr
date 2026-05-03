#!/usr/bin/env python3
"""
Candlestick × Macro Regime Filter — Autoresearch Round 19
==========================================================
Hypothesis: Bullish candlestick signals fired only during favorable macro
regimes (calm / easing / low_stress) produce materially higher Sharpe ratios
than unfiltered signals.

Test design:
  - Take the top 10 bullish candle patterns from Round 18
  - Run each at 3d and 10d hold (the optimal windows)
  - Compare 3 variants per pattern:
      A) Unfiltered   — all signals regardless of regime
      B) Favorable    — only when: calm OR (easing AND low_stress)
      C) Unfavorable  — only when: oil_shock OR stress OR tightening
                        (the inverse — shows what to AVOID)
  - Report: Sharpe lift, return improvement, signal count change

Usage:
  PYTHONPATH=/tmp/eval_deps python3 candle_macro_harness.py
"""

from __future__ import annotations

import json
import math
import os
import pickle
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
except ImportError as e:
    print(f"Missing: {e}. Run: pip install yfinance pandas numpy --target=/tmp/eval_deps")
    sys.exit(1)

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
MACRO_DIR  = ROOT / "macro_cache"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)
MACRO_DIR.mkdir(exist_ok=True)

YEARS      = 7   # 2019-2026 — enough macro cycles
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Universe — same Fortune 100 as candle_harness
UNIVERSE = {
    "AAPL":"Apple","MSFT":"Microsoft","GOOGL":"Alphabet","META":"Meta",
    "AMZN":"Amazon","NVDA":"NVIDIA","TSLA":"Tesla","JPM":"JPMorgan",
    "BAC":"BofA","GS":"Goldman","WFC":"Wells Fargo","XOM":"Exxon",
    "CVX":"Chevron","COP":"ConocoPhillips","HAL":"Halliburton",
    "LMT":"Lockheed","RTX":"Raytheon","NOC":"Northrop","GD":"General Dynamics",
    "WMT":"Walmart","COST":"Costco","KO":"Coca-Cola","PEP":"PepsiCo","PG":"P&G",
    "JNJ":"J&J","LLY":"Eli Lilly","MRK":"Merck","PFE":"Pfizer","UNH":"UnitedHealth",
    "CAT":"Caterpillar","DE":"Deere","GE":"GE","UPS":"UPS","BA":"Boeing",
    "F":"Ford","GM":"GM","NKE":"Nike","MO":"Altria","BRK-B":"Berkshire",
}

# ── Top patterns from Round 18 (by Sharpe, bullish only) ──────────────────────
# We focus on the patterns with proven edge before adding regime filter

TOP_PATTERNS_R18 = [
    "SpinningTop",
    "BullishHarami",
    "PiercingLine",
    "LongLeggedDoji",
    "MorningStar",
    "InvertedHammer",
    "TweezerBottom",
    "BullishEngulfing",
    "BullMarubozu",
    "Doji",
]

HOLD_PERIODS = [3, 10]  # optimal from R18


# ══════════════════════════════════════════════════════════════════════════════
#  DATA FETCHERS
# ══════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(symbol: str) -> pd.DataFrame | None:
    cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{YEARS}yr.pkl"
    # reuse cache from candle_harness if it exists (different YEARS value)
    # check both 7yr and 15yr
    for years_tag in [YEARS, 15]:
        cp2 = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{years_tag}yr.pkl"
        if cp2.exists():
            try:
                with open(cp2, "rb") as f:
                    d = pickle.load(f)
                if isinstance(d, pd.DataFrame) and len(d) > 200:
                    # Trim to YEARS if needed
                    cutoff = pd.Timestamp(START_DATE)
                    if d.index.tz is not None:
                        cutoff = cutoff.tz_localize(d.index.tz)
                    return d[d.index >= cutoff]
            except Exception:
                pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        h = h[["Open","High","Low","Close","Volume"]].dropna()
        with open(cp, "wb") as f:
            pickle.dump(h, f)
        return h
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


def fetch_fred(series_id: str, api_key: str) -> pd.Series | None:
    cp = MACRO_DIR / f"fred_{series_id}.pkl"
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series) and len(s) > 50:
                return s
        except Exception:
            pass
    if not api_key:
        return None
    try:
        params = urllib.parse.urlencode({
            "series_id":       series_id,
            "api_key":         api_key,
            "file_type":       "json",
            "observation_start": "2010-01-01",
        })
        url = f"https://api.stlouisfed.org/fred/series/observations?{params}"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read())
        obs = data.get("observations", [])
        if not obs:
            return None
        idx = pd.to_datetime([o["date"] for o in obs])
        vals = pd.to_numeric([o["value"] for o in obs], errors="coerce")
        s = pd.Series(vals.values, index=idx, name=series_id).dropna()
        with open(cp, "wb") as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f"  FRED {series_id}: {e}", file=sys.stderr)
        return None


def fetch_yfinance_macro(symbol: str, name: str) -> pd.Series | None:
    cp = MACRO_DIR / f"yf_{name}.pkl"
    if cp.exists():
        try:
            with open(cp, "rb") as f:
                s = pickle.load(f)
            if isinstance(s, pd.Series) and len(s) > 50:
                return s
        except Exception:
            pass
    try:
        t = yf.Ticker(symbol)
        h = t.history(start="2010-01-01", end=END_DATE, auto_adjust=True)
        if h.empty:
            return None
        s = h["Close"].rename(name)
        with open(cp, "wb") as f:
            pickle.dump(s, f)
        return s
    except Exception as e:
        print(f"  yf {symbol}: {e}", file=sys.stderr)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  MACRO REGIME BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def load_macro(api_key: str) -> dict[str, pd.Series]:
    print("  Loading macro data...")
    macro = {}

    fred_series = {
        "DCOILWTICO":    "WTI Crude",
        "CPIAUCSL":      "CPI",
        "T10YIE":        "10yr Breakeven",
        "DFF":           "Fed Funds",
        "T10Y2Y":        "10yr-2yr Spread",
        "BAMLH0A0HYM2":  "HY Spread",
        "VIXCLS":        "VIX",
        "GOLDAMGBD228NLBM": "Gold Fix",
    }
    for sid, label in fred_series.items():
        s = fetch_fred(sid, api_key)
        if s is not None and len(s) > 50:
            macro[sid] = s
            print(f"    ✓ FRED {label} ({len(s)} obs)")
        else:
            print(f"    ○ FRED {label} — trying yfinance fallback")

    # yfinance fallbacks
    fallbacks = {
        "DCOILWTICO":    ("CL=F",        "Oil WTI"),
        "VIXCLS":        ("^VIX",        "VIX"),
        "GOLDAMGBD228NLBM": ("GC=F",     "Gold"),
        "T10Y2Y":        ("^TNX",        "10yr Yield"),
    }
    for fred_id, (yf_sym, yf_name) in fallbacks.items():
        if fred_id not in macro:
            s = fetch_yfinance_macro(yf_sym, fred_id)
            if s is not None:
                macro[fred_id] = s
                print(f"    ✓ yfinance {yf_name} (fallback)")

    return macro


def build_regime_index(macro: dict[str, pd.Series], price_index: pd.DatetimeIndex) -> pd.DataFrame:
    """Align macro series to price index and classify regimes."""
    # Strip timezone for alignment
    if price_index.tz is not None:
        align_idx = price_index.tz_localize(None)
    else:
        align_idx = price_index

    frames = {}
    for k, s in macro.items():
        if hasattr(s.index, 'tz') and s.index.tz is not None:
            s = s.copy()
            s.index = s.index.tz_localize(None)
        frames[k] = s.reindex(align_idx, method="ffill")

    mf = pd.DataFrame(frames, index=align_idx)
    regimes = classify_regimes(mf)
    return regimes


def classify_regimes(mf: pd.DataFrame) -> pd.DataFrame:
    regimes = pd.DataFrame(index=mf.index)

    # Oil shock
    oil_col = "DCOILWTICO"
    if oil_col in mf.columns and mf[oil_col].notna().sum() > 90:
        oil = mf[oil_col].ffill()
        rm  = oil.rolling(90, min_periods=30).mean()
        rs  = oil.rolling(90, min_periods=30).std()
        regimes["oil_shock"] = oil > (rm + 1.5 * rs)
        regimes["oil_high"]  = oil > rm
    else:
        regimes["oil_shock"] = False
        regimes["oil_high"]  = False

    # Inflation
    if "CPIAUCSL" in mf.columns and mf["CPIAUCSL"].notna().sum() > 12:
        cpi = mf["CPIAUCSL"].ffill()
        cpi_yoy = cpi.pct_change(252) * 100
        regimes["inflationary"] = cpi_yoy > 3.5
    elif "T10YIE" in mf.columns and mf["T10YIE"].notna().sum() > 90:
        bie = mf["T10YIE"].ffill()
        regimes["inflationary"] = bie > 2.8
    else:
        regimes["inflationary"] = False

    # Stress
    stress = pd.Series(False, index=mf.index)
    if "VIXCLS" in mf.columns and mf["VIXCLS"].notna().sum() > 90:
        stress |= (mf["VIXCLS"].ffill() > 25)
    if "BAMLH0A0HYM2" in mf.columns and mf["BAMLH0A0HYM2"].notna().sum() > 90:
        stress |= (mf["BAMLH0A0HYM2"].ffill() > 500)
    regimes["stress"]     = stress
    regimes["low_stress"] = ~stress

    # Tightening / Easing
    tight = pd.Series(False, index=mf.index)
    if "T10Y2Y" in mf.columns and mf["T10Y2Y"].notna().sum() > 90:
        tight |= (mf["T10Y2Y"].ffill() < 0)
    if "DFF" in mf.columns and mf["DFF"].notna().sum() > 90:
        ff = mf["DFF"].ffill()
        ff_trend = ff - ff.shift(126)
        tight |= (ff_trend > 0.25)
        regimes["easing"] = ff_trend < -0.25
    else:
        regimes["easing"] = False
    regimes["tightening"] = tight

    # Calm — ideal conditions
    regimes["calm"] = (
        ~regimes["oil_shock"] &
        ~regimes["inflationary"] &
        ~regimes["stress"] &
        ~regimes["tightening"]
    )

    # Composite: favorable for long equity
    regimes["favorable"] = (
        regimes["calm"] |
        (regimes["easing"] & regimes["low_stress"])
    )

    # Composite: unfavorable for long equity
    regimes["unfavorable"] = (
        regimes["oil_shock"] |
        regimes["stress"] |
        regimes["tightening"]
    )

    return regimes.fillna(False)


# ══════════════════════════════════════════════════════════════════════════════
#  PATTERN DETECTORS (subset — top 10 from R18)
# ══════════════════════════════════════════════════════════════════════════════

def detect_pattern(name: str, df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df["Open"], df["High"], df["Low"], df["Close"]
    body    = (c - o).abs()
    rng     = (h - l).replace(0, np.nan)
    us      = h - df[["Open","Close"]].max(axis=1)
    ls      = df[["Open","Close"]].min(axis=1) - l
    trend5  = c.pct_change(5)
    trend10 = c.pct_change(10)
    sig     = pd.Series(0.0, index=df.index)

    if name == "SpinningTop":
        mask = (body/rng < 0.3) & (us > body) & (ls > body)
        sig[mask & (trend5 < -0.02)] = 1

    elif name == "BullishHarami":
        prev_bhi = df[["Open","Close"]].shift(1).max(axis=1)
        prev_blo = df[["Open","Close"]].shift(1).min(axis=1)
        curr_bhi = df[["Open","Close"]].max(axis=1)
        curr_blo = df[["Open","Close"]].min(axis=1)
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        inside    = (curr_bhi < prev_bhi) & (curr_blo > prev_blo)
        sig[prev_bear & curr_bull & inside] = 1

    elif name == "PiercingLine":
        mid1      = (o.shift(1) + c.shift(1)) / 2
        day1_bear = c.shift(1) < o.shift(1)
        day2_bull = c > o
        opens_low = o < l.shift(1)
        closes_above_mid = c > mid1
        sig[day1_bear & day2_bull & opens_low & closes_above_mid] = 1

    elif name == "LongLeggedDoji":
        b_rng = body / rng
        mask  = (b_rng < 0.05) & (us > body) & (ls > body)
        sig[mask & (trend5 < 0)] = 1

    elif name == "MorningStar":
        body2  = body.shift(2);  rng2 = rng.shift(2)
        d1_bear  = (c.shift(2) < o.shift(2)) & (body2/rng2 > 0.5)
        d2_small = body.shift(1) / rng.shift(1) < 0.3
        d2_gap   = df[["Open","Close"]].shift(1).max(axis=1) < c.shift(2)
        d3_bull  = (c > o) & (body/rng > 0.4)
        d3_close = c > (o.shift(2) + c.shift(2)) / 2
        sig[d1_bear & d2_small & d3_bull & d3_close] = 1

    elif name == "InvertedHammer":
        mask = (
            (body / rng < 0.35) &
            (us >= 2 * body.replace(0, np.nan)) &
            (ls <= 0.1 * rng) &
            (trend10 < -0.03)
        )
        sig[mask] = 1

    elif name == "TweezerBottom":
        same_low = (l - l.shift(1)).abs() / l.replace(0, np.nan) < 0.002
        sig[same_low & (c > o) & (trend10 < -0.02)] = 1

    elif name == "BullishEngulfing":
        prev_bear = c.shift(1) < o.shift(1)
        curr_bull = c > o
        engulfs   = (o <= c.shift(1)) & (c >= o.shift(1))
        sig[prev_bear & curr_bull & engulfs & (trend10 < -0.02)] = 1

    elif name == "BullMarubozu":
        sig[(body/rng > 0.92) & (c > o)] = 1

    elif name == "Doji":
        doji_days = body / rng < 0.05
        sig[doji_days & (trend5 < -0.02)] = 1

    return sig


# ══════════════════════════════════════════════════════════════════════════════
#  BACKTEST ENGINE WITH REGIME FILTER
# ══════════════════════════════════════════════════════════════════════════════

def backtest_filtered(ohlcv: pd.DataFrame, signals: pd.Series,
                      regime_mask: pd.Series | None, hold_days: int) -> dict:
    """
    Backtest bullish signals, optionally masked by regime.
    regime_mask: boolean series (True = trade allowed). None = no filter.
    """
    prices = ohlcv["Close"]

    # Align to common index
    common = prices.index
    if common.tz is not None:
        common_tz_naive = common.tz_localize(None)
    else:
        common_tz_naive = common

    # Rebuild signals on tz-naive index
    sig = signals.copy()
    if sig.index.tz is not None:
        sig.index = sig.index.tz_localize(None)
    sig = sig.reindex(common_tz_naive, fill_value=0).shift(1).fillna(0)

    if regime_mask is not None:
        rm = regime_mask.copy()
        if rm.index.tz is not None:
            rm.index = rm.index.tz_localize(None)
        rm = rm.reindex(common_tz_naive, method="ffill").fillna(False)
        sig = sig * rm.astype(float)

    prices_tz = prices.copy()
    prices_tz.index = common_tz_naive
    daily_ret = prices_tz.pct_change().fillna(0)

    # Build hold positions
    position = pd.Series(0.0, index=common_tz_naive)
    sig_idx  = sig[sig > 0].index
    for idx in sig_idx:
        try:
            loc = common_tz_naive.get_loc(idx)
        except KeyError:
            continue
        end = min(loc + hold_days, len(common_tz_naive))
        position.iloc[loc:end] = 1.0

    if (position > 0).sum() < 10:
        return {}

    strategy_ret = (daily_ret * position).fillna(0)
    cum          = (1 + strategy_ret).cumprod()
    raw_return   = float(cum.iloc[-1] - 1)
    n_years      = len(strategy_ret) / 252
    cagr = float((1 + raw_return)**(1/max(n_years,0.1))-1) if raw_return > -1 else float("-inf")
    mu, std = strategy_ret.mean(), strategy_ret.std()
    sharpe  = float(mu / std * math.sqrt(252)) if std > 0 else 0.0
    n_trades = int((sig > 0).sum())
    active   = float((position != 0).mean()) * 100

    return {
        "raw_return":  round(raw_return * 100, 2),
        "cagr":        round(cagr * 100, 2),
        "sharpe":      round(sharpe, 3),
        "n_trades":    n_trades,
        "active_pct":  round(active, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN RUNNER
# ══════════════════════════════════════════════════════════════════════════════

def run():
    print("=" * 72)
    print("CANDLESTICK × MACRO REGIME FILTER — Round 19")
    print(f"Top 10 bullish patterns × 2 hold periods × 3 filter variants")
    total = len(TOP_PATTERNS_R18) * len(HOLD_PERIODS) * len(UNIVERSE) * 3
    print(f"Total backtests: {total:,}")
    print("=" * 72)

    api_key = FRED_API_KEY
    if not api_key:
        print("  ⚠ FRED_API_KEY not set — using cached data only")

    macro = load_macro(api_key)
    print(f"  Macro series loaded: {len(macro)}")

    # We'll build regime index lazily per stock (same dates)
    # First load one stock to get the index
    print("\n  Building regime index...")
    ref_sym = "SPY" if "SPY" in UNIVERSE else list(UNIVERSE.keys())[0]
    ref_data = fetch_ohlcv(ref_sym)
    if ref_data is None:
        ref_data = fetch_ohlcv(list(UNIVERSE.keys())[0])

    regimes = build_regime_index(macro, ref_data.index)

    # Report current regime stats
    fav_pct  = float(regimes["favorable"].mean() * 100)
    unfav_pct = float(regimes["unfavorable"].mean() * 100)
    calm_pct  = float(regimes["calm"].mean() * 100)
    print(f"  Regime coverage: favorable={fav_pct:.1f}%  unfavorable={unfav_pct:.1f}%  calm={calm_pct:.1f}%")

    results = {pat: {hold: {"A": [], "B": [], "C": []}
                     for hold in HOLD_PERIODS}
               for pat in TOP_PATTERNS_R18}

    done = 0
    for sym in UNIVERSE:
        ohlcv = fetch_ohlcv(sym)
        if ohlcv is None:
            continue

        for pat_name in TOP_PATTERNS_R18:
            try:
                sigs = detect_pattern(pat_name, ohlcv)
            except Exception as e:
                continue

            for hold in HOLD_PERIODS:
                # Variant A: unfiltered
                r_a = backtest_filtered(ohlcv, sigs, None, hold)
                if r_a:
                    results[pat_name][hold]["A"].append(r_a)

                # Variant B: favorable regime only
                r_b = backtest_filtered(ohlcv, sigs, regimes["favorable"], hold)
                if r_b:
                    results[pat_name][hold]["B"].append(r_b)

                # Variant C: unfavorable regime only
                r_c = backtest_filtered(ohlcv, sigs, regimes["unfavorable"], hold)
                if r_c:
                    results[pat_name][hold]["C"].append(r_c)

                done += 3

        if done % 1500 == 0 and done > 0:
            print(f"  Progress: {done:,}/{total:,} ({done/total*100:.0f}%)")

    # ── Aggregate and print results ────────────────────────────────────────────

    def avg(lst, key):
        vals = [r[key] for r in lst if key in r and not math.isnan(r[key]) and not math.isinf(r[key])]
        return sum(vals)/len(vals) if vals else 0.0

    print("\n")
    print("=" * 72)
    print("RESULTS — Sharpe Comparison: Unfiltered vs Regime-Filtered")
    print("=" * 72)
    print(f"\n{'Pattern':<22} {'Hold':>5}  {'Unfilt Sharpe':>13}  {'Fav Sharpe':>10}  {'Unfav Sharpe':>12}  {'Lift':>6}  {'Sig%':>5}")
    print("-" * 85)

    summary_rows = []
    for pat in TOP_PATTERNS_R18:
        for hold in HOLD_PERIODS:
            a_list = results[pat][hold]["A"]
            b_list = results[pat][hold]["B"]
            c_list = results[pat][hold]["C"]
            if not a_list:
                continue

            sh_a = avg(a_list, "sharpe")
            sh_b = avg(b_list, "sharpe")
            sh_c = avg(c_list, "sharpe")
            lift = sh_b - sh_a

            # Signal retention: how many trades survive the filter
            n_a = avg(a_list, "n_trades")
            n_b = avg(b_list, "n_trades")
            sig_kept_pct = (n_b / n_a * 100) if n_a > 0 else 0

            ret_a = avg(a_list, "raw_return")
            ret_b = avg(b_list, "raw_return")

            print(f"  {pat:<22} {hold:>3}d   "
                  f"{sh_a:>+7.3f}       {sh_b:>+7.3f}    {sh_c:>+7.3f}     "
                  f"{lift:>+6.3f}  {sig_kept_pct:>4.0f}%")

            summary_rows.append({
                "pattern":        pat,
                "hold_days":      hold,
                "sharpe_unfilt":  round(sh_a, 3),
                "sharpe_fav":     round(sh_b, 3),
                "sharpe_unfav":   round(sh_c, 3),
                "sharpe_lift":    round(lift, 3),
                "ret_unfilt":     round(ret_a, 2),
                "ret_fav":        round(ret_b, 2),
                "sig_kept_pct":   round(sig_kept_pct, 1),
            })

    # ── Top lifts ──────────────────────────────────────────────────────────────
    sorted_by_lift = sorted(summary_rows, key=lambda x: x["sharpe_lift"], reverse=True)

    print("\n\nTOP 5 — Biggest Sharpe Lift from Regime Filter:")
    print(f"  {'Pattern':<22} {'Hold':>5}  {'Unfilt':>8}  {'Fav':>8}  {'Lift':>7}  {'Sigs kept':>10}")
    print("  " + "-" * 65)
    for r in sorted_by_lift[:5]:
        print(f"  {r['pattern']:<22} {r['hold_days']:>3}d  "
              f"{r['sharpe_unfilt']:>+8.3f}  {r['sharpe_fav']:>+8.3f}  "
              f"{r['sharpe_lift']:>+7.3f}  {r['sig_kept_pct']:>8.0f}%")

    # ── Regime filter summary ──────────────────────────────────────────────────
    avg_lift = sum(r["sharpe_lift"] for r in summary_rows) / len(summary_rows) if summary_rows else 0
    improved = sum(1 for r in summary_rows if r["sharpe_lift"] > 0.05)
    print(f"\n  Average Sharpe lift across all patterns: {avg_lift:+.3f}")
    print(f"  Patterns improved by >0.05 Sharpe:       {improved}/{len(summary_rows)}")
    print(f"\n  Regime coverage (when filter is 'favorable'):")
    print(f"    Favorable days: {fav_pct:.1f}% of all trading days")
    print(f"    Unfavorable:    {unfav_pct:.1f}% of all trading days")
    print(f"    Calm:           {calm_pct:.1f}% of all trading days")

    # ── Save results ───────────────────────────────────────────────────────────
    out = ROUNDS_DIR / "candle_macro_round19.json"
    save_data = {
        "timestamp":    datetime.now().isoformat(),
        "round":        19,
        "description":  "Candlestick × Macro Regime Filter",
        "regime_stats": {
            "favorable_pct":  round(fav_pct, 2),
            "unfavorable_pct": round(unfav_pct, 2),
            "calm_pct":       round(calm_pct, 2),
        },
        "avg_sharpe_lift": round(avg_lift, 3),
        "n_improved":      improved,
        "results":         summary_rows,
        "top5_by_lift":    sorted_by_lift[:5],
    }
    with open(out, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\n  Saved → {out}")

    return save_data


if __name__ == "__main__":
    run()
