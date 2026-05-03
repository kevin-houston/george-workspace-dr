#!/usr/bin/env python3
"""
Statistical Arbitrage / Pairs Trading Harness — Round 20-23
============================================================
Implements the core techniques from Isichenko's
"Quantitative Portfolio Management: The Art and Science of Statistical Arbitrage"

Rounds:
  R20: Baseline — ratio z-score on all sector pairs (no cointegration filter)
  R21: Cointegration-filtered — only trade pairs with ADF p < 0.05
  R22: Kalman filter — dynamic hedge ratio (vs fixed OLS ratio)
  R23: Multi-pair portfolio — combine best pairs into diversified stat-arb book

Universe: Fortune 100 grouped by sector (~40 sector-pairs + ~10 cross-sector)
Data: 10 years daily closes (yfinance, reuses cache from prior harnesses)

Usage:
  PYTHONPATH=/tmp/eval_deps python3 pairs_harness.py
  PYTHONPATH=/tmp/eval_deps python3 pairs_harness.py --round 20
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
    from statsmodels.tsa.stattools import coint, adfuller
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant
except ImportError as e:
    print(f"Missing: {e}")
    print("Run: python3 -m pip install yfinance pandas numpy statsmodels --target=/tmp/eval_deps")
    sys.exit(1)

ROOT       = Path(__file__).parent
CACHE_DIR  = ROOT / "cache"
ROUNDS_DIR = ROOT / "rounds"
CACHE_DIR.mkdir(exist_ok=True)
ROUNDS_DIR.mkdir(exist_ok=True)

YEARS      = 10
START_DATE = (datetime.now() - timedelta(days=YEARS * 365 + 30)).strftime("%Y-%m-%d")
END_DATE   = datetime.now().strftime("%Y-%m-%d")

# ── Universe by sector ─────────────────────────────────────────────────────────
SECTORS = {
    "energy":     ["XOM", "CVX", "COP", "HAL", "MPC"],
    "defense":    ["LMT", "RTX", "NOC", "GD"],
    "tech":       ["AAPL", "MSFT", "GOOGL", "META", "NVDA"],
    "finance":    ["JPM", "BAC", "GS", "WFC"],
    "consumer":   ["WMT", "COST", "KO", "PEP", "PG"],
    "healthcare": ["JNJ", "LLY", "MRK", "PFE", "UNH"],
    "industrial": ["CAT", "DE", "GE", "UPS", "BA"],
    "auto":       ["F", "GM", "TSLA"],
}

# Cross-sector pairs with fundamental economic relationship
CROSS_SECTOR_PAIRS = [
    ("XOM", "COP"),    # E&P vs integrated
    ("AAPL", "MSFT"),  # Tech duopoly
    ("JPM", "GS"),     # Money-center vs investment bank
    ("KO", "PEP"),     # The classic pairs trade
    ("LMT", "NOC"),    # Defense peers
    ("F", "GM"),       # Detroit duopoly
    ("WMT", "COST"),   # Retail peers
    ("JNJ", "PFE"),    # Big pharma
    ("CAT", "DE"),     # Industrial machinery
    ("UNH", "LLY"),    # Healthcare
]


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_close(symbol: str) -> Optional[pd.Series]:
    """Load close prices — reuse cache from other harnesses."""
    # Try multiple cache naming conventions
    for years_tag in [YEARS, 15, 7]:
        cp = CACHE_DIR / f"ohlcv_{symbol.replace('-','_')}_{years_tag}yr.pkl"
        if cp.exists():
            try:
                with open(cp, "rb") as f:
                    d = pickle.load(f)
                if isinstance(d, pd.DataFrame) and len(d) > 200:
                    c = d["Close"].copy()
                    if c.index.tz is not None:
                        c.index = c.index.tz_localize(None)
                    cutoff = pd.Timestamp(START_DATE)
                    return c[c.index >= cutoff]
            except Exception:
                pass

    # Fetch fresh
    cp = CACHE_DIR / f"ohlcv_{symbol}_{YEARS}yr.pkl"
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        df = h[["Open","High","Low","Close","Volume"]].dropna()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        with open(cp, "wb") as f:
            pickle.dump(df, f)
        return df["Close"]
    except Exception as e:
        print(f"  ✗ {symbol}: {e}", file=sys.stderr)
        return None


def align_pair(s1: pd.Series, s2: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Align two price series to common dates."""
    common = s1.index.intersection(s2.index)
    return s1.loc[common], s2.loc[common]


# ══════════════════════════════════════════════════════════════════════════════
#  STATISTICAL TESTS
# ══════════════════════════════════════════════════════════════════════════════

def test_cointegration(y: pd.Series, x: pd.Series) -> dict:
    """
    Engle-Granger cointegration test.
    Returns: p-value, hedge ratio (beta), spread series, ADF stat on spread.
    """
    try:
        # OLS hedge ratio: y = beta * x + alpha
        x_c   = add_constant(x.values)
        model = OLS(y.values, x_c).fit()
        beta  = float(model.params[1])
        alpha = float(model.params[0])
        spread = y - beta * x - alpha

        # ADF test on spread — stationary spread = cointegrated
        adf_stat, adf_p, _, _, _, _ = adfuller(spread.dropna(), maxlags=1)

        # Engle-Granger cointegration test
        _, eg_p, _ = coint(y.values, x.values)

        return {
            "beta":     round(beta, 4),
            "alpha":    round(alpha, 4),
            "adf_stat": round(float(adf_stat), 4),
            "adf_p":    round(float(adf_p), 4),
            "eg_p":     round(float(eg_p), 4),
            "spread":   spread,
            "cointegrated": float(eg_p) < 0.05,
        }
    except Exception as e:
        return {"cointegrated": False, "eg_p": 1.0, "spread": None}


def rolling_zscore(spread: pd.Series, window: int = 60) -> pd.Series:
    """Z-score of spread relative to rolling mean/std."""
    mean = spread.rolling(window, min_periods=window // 2).mean()
    std  = spread.rolling(window, min_periods=window // 2).std().replace(0, np.nan)
    return (spread - mean) / std


# ══════════════════════════════════════════════════════════════════════════════
#  KALMAN FILTER DYNAMIC HEDGE RATIO
# ══════════════════════════════════════════════════════════════════════════════

def kalman_spread(y: pd.Series, x: pd.Series,
                  delta: float = 1e-5, Ve: float = 0.001) -> Tuple[pd.Series, pd.Series]:
    """
    Kalman filter to estimate dynamic hedge ratio beta(t).
    State: [beta, alpha] — two-dimensional
    Observation: y_t = beta_t * x_t + alpha_t + noise

    delta: process noise (how fast beta can change — higher = more adaptive)
    Ve:    observation noise variance

    Returns: (spread series, beta series)
    """
    n     = len(y)
    Vw    = delta / (1 - delta) * np.eye(2)   # state transition noise
    P     = np.zeros((2, 2))                   # state covariance
    beta  = np.zeros((n, 2))                   # [beta, alpha]
    e     = np.zeros(n)                        # innovations
    Q     = np.zeros(n)                        # innovation variance

    for t in range(n):
        xt = np.array([float(x.iloc[t]), 1.0])  # [x, 1] for [beta, alpha]
        if t == 0:
            beta[t] = [1.0, 0.0]
            P = Vw
        else:
            # Predict
            beta[t] = beta[t-1]
            P       = P + Vw

        # Update
        Q[t]      = float(xt @ P @ xt) + Ve
        K         = P @ xt / Q[t]                # Kalman gain
        e[t]      = float(y.iloc[t]) - float(xt @ beta[t])
        beta[t]   = beta[t] + K * e[t]
        P         = P - np.outer(K, xt) @ P

    hedge_ratio = pd.Series(beta[:, 0], index=y.index, name="hedge_ratio")
    intercept   = pd.Series(beta[:, 1], index=y.index, name="intercept")
    spread      = y - hedge_ratio * x - intercept
    return spread, hedge_ratio


# ══════════════════════════════════════════════════════════════════════════════
#  BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def backtest_pair(y: pd.Series, x: pd.Series, zscore: pd.Series,
                  entry_z: float = 2.0, exit_z: float = 0.5,
                  stop_z: float = 4.0, cost_bps: float = 2.0) -> dict:
    """
    Pairs trade: enter when |z| > entry_z, exit when |z| < exit_z.
    Long/short the SPREAD — long y, short x when z < -entry_z (y cheap vs x).
    Short y, long x when z > +entry_z (y expensive vs x).
    Stop out when |z| > stop_z (regime break).

    Returns: strategy metrics + leg PnL breakdown.
    """
    if zscore is None or len(zscore) < 100:
        return {}

    y_ret = y.pct_change().fillna(0)
    x_ret = x.pct_change().fillna(0)

    position = pd.Series(0.0, index=zscore.index)
    in_trade = False
    direction = 0  # +1 = long spread (long y, short x), -1 = short spread

    for i in range(1, len(zscore)):
        z = float(zscore.iloc[i])
        if math.isnan(z):
            position.iloc[i] = 0
            continue

        if not in_trade:
            if z < -entry_z:       # y cheap → long spread
                in_trade, direction = True, 1
            elif z > entry_z:      # y expensive → short spread
                in_trade, direction = True, -1
            position.iloc[i] = 0
        else:
            # Exit conditions
            if abs(z) < exit_z:
                in_trade, direction = False, 0
            elif abs(z) > stop_z:  # stop-loss — regime breaking
                in_trade, direction = False, 0
            position.iloc[i] = direction

    # P&L: long spread = long y + short x (equal dollar value)
    # When position = +1: return = y_ret - x_ret
    # When position = -1: return = x_ret - y_ret
    spread_ret = (y_ret - x_ret) * position.shift(1).fillna(0)

    # Transaction cost: 2 legs, charged on entry/exit
    trades     = position.diff().abs().fillna(0)
    cost       = trades * (cost_bps / 10000) * 2  # both legs
    strat_ret  = spread_ret - cost

    cum       = (1 + strat_ret).cumprod()
    raw       = float(cum.iloc[-1] - 1)
    n_years   = len(strat_ret) / 252
    cagr      = float((1+raw)**(1/max(n_years,0.1))-1) if raw > -1 else float("-inf")
    mu, std   = strat_ret.mean(), strat_ret.std()
    sharpe    = float(mu / std * math.sqrt(252)) if std > 0 else 0.0
    roll_max  = cum.cummax()
    max_dd    = float(((cum - roll_max) / roll_max).min())
    n_trades  = int((trades > 0.5).sum()) // 2   # entry + exit = 1 trade
    pct_time  = float((position != 0).mean() * 100)
    win_rate  = float((strat_ret[strat_ret != 0] > 0).mean() * 100) if (strat_ret != 0).any() else 0.0

    return {
        "raw_return":   round(raw * 100, 2),
        "cagr":         round(cagr * 100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "n_trades":     n_trades,
        "pct_invested": round(pct_time, 1),
        "win_rate":     round(win_rate, 1),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  PAIR UNIVERSE BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_all_pairs() -> List[Tuple[str, str, str]]:
    """Returns list of (sym1, sym2, sector_label) tuples."""
    pairs = []
    # Within-sector pairs
    for sector, tickers in SECTORS.items():
        for a, b in itertools.combinations(tickers, 2):
            pairs.append((a, b, sector))
    # Cross-sector known pairs
    for a, b in CROSS_SECTOR_PAIRS:
        pairs.append((a, b, "cross"))
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND RUNNERS
# ══════════════════════════════════════════════════════════════════════════════

def run_round20(prices: dict) -> List[dict]:
    """
    R20: Baseline — ratio z-score on all pairs, no cointegration pre-filter.
    Tests entry z: 1.5, 2.0, 2.5 | exit z: 0.5 | z-window: 60
    """
    results = []
    all_pairs = build_all_pairs()
    print(f"  Testing {len(all_pairs)} pairs × 3 entry thresholds = {len(all_pairs)*3} backtests")

    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        # Simple log-ratio spread
        log_ratio = np.log(ya / xb)
        for entry_z in [1.5, 2.0, 2.5]:
            z = rolling_zscore(log_ratio, window=60)
            r = backtest_pair(ya, xb, z, entry_z=entry_z, exit_z=0.5, cost_bps=2.0)
            if r:
                r.update({
                    "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                    "method": "log_ratio", "entry_z": entry_z,
                    "round": 20,
                })
                results.append(r)
    return results


def run_round21(prices: dict) -> List[dict]:
    """
    R21: Cointegration-filtered — only trade pairs with Engle-Granger p < 0.05.
    Uses OLS hedge ratio. Tests entry z: 1.5, 2.0 | exit z: 0.5
    """
    results = []
    all_pairs = build_all_pairs()
    cointegrated = []

    print(f"  Testing cointegration on {len(all_pairs)} pairs...")
    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue
        coint_result = test_cointegration(ya, xb)
        if coint_result["cointegrated"]:
            cointegrated.append((sym_a, sym_b, sector, coint_result))

    print(f"  Cointegrated pairs (p<0.05): {len(cointegrated)} / {len(all_pairs)}")

    for sym_a, sym_b, sector, cr in cointegrated:
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        spread = cr.get("spread")
        if spread is None or len(spread) < 252:
            continue
        for entry_z in [1.5, 2.0, 2.5]:
            z = rolling_zscore(spread, window=60)
            r = backtest_pair(ya, xb, z, entry_z=entry_z, exit_z=0.5, cost_bps=2.0)
            if r:
                r.update({
                    "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                    "method": "coint_ols", "entry_z": entry_z,
                    "eg_p": cr["eg_p"], "beta": cr["beta"],
                    "round": 21,
                })
                results.append(r)
    return results, cointegrated


def run_round22(prices: dict, cointegrated_pairs: list) -> List[dict]:
    """
    R22: Kalman filter dynamic hedge ratio on the cointegrated pairs from R21.
    Compares fixed OLS beta vs adaptive Kalman beta.
    """
    results = []
    for sym_a, sym_b, sector, cr in cointegrated_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        # Kalman spread with different delta (responsiveness) values
        for delta in [1e-5, 1e-4, 5e-4]:
            try:
                k_spread, k_beta = kalman_spread(ya, xb, delta=delta)
                z = rolling_zscore(k_spread, window=60)
                r = backtest_pair(ya, xb, z, entry_z=2.0, exit_z=0.5, cost_bps=2.0)
                if r:
                    r.update({
                        "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                        "method": f"kalman_d{delta:.0e}",
                        "entry_z": 2.0, "delta": delta,
                        "round": 22,
                    })
                    results.append(r)
            except Exception:
                continue
    return results


def run_round23(prices: dict, all_r20: List[dict], all_r21: List[dict],
                all_r22: List[dict]) -> dict:
    """
    R23: Multi-pair portfolio — combine top 10 pairs from R20-R22 into a book.
    Equal-weight: each pair gets 1/N of portfolio. Sum of spread returns.
    """
    # Pool all results and pick top 10 by Sharpe
    pool = all_r20 + all_r21 + all_r22
    df_pool = pd.DataFrame(pool)
    if df_pool.empty:
        return {}

    top10 = (df_pool.sort_values("sharpe", ascending=False)
                    .drop_duplicates(subset=["sym_a","sym_b"])
                    .head(10))

    print(f"  Building portfolio from top {len(top10)} pairs...")

    # Rebuild daily returns for each top pair
    pair_returns = []
    for _, row in top10.iterrows():
        sym_a, sym_b = row["sym_a"], row["sym_b"]
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        method = row.get("method","log_ratio")
        if "kalman" in method:
            delta = row.get("delta", 1e-5)
            k_spread, _ = kalman_spread(ya, xb, delta=delta)
            spread = k_spread
        elif "coint" in method:
            cr = test_cointegration(ya, xb)
            spread = cr.get("spread", np.log(ya / xb))
        else:
            spread = np.log(ya / xb)

        z       = rolling_zscore(spread, window=60)
        position = pd.Series(0.0, index=z.index)
        in_trade, direction = False, 0
        for i in range(1, len(z)):
            zv = float(z.iloc[i])
            if math.isnan(zv):
                continue
            if not in_trade:
                if zv < -2.0:
                    in_trade, direction = True, 1
                elif zv > 2.0:
                    in_trade, direction = True, -1
            else:
                if abs(zv) < 0.5 or abs(zv) > 4.0:
                    in_trade, direction = False, 0
            position.iloc[i] = direction

        y_ret = ya.pct_change().fillna(0)
        x_ret = xb.pct_change().fillna(0)
        trades = position.diff().abs().fillna(0)
        cost   = trades * (2.0 / 10000) * 2
        pret   = (y_ret - x_ret) * position.shift(1).fillna(0) - cost
        pair_returns.append(pret.rename(f"{sym_a}/{sym_b}"))

    if not pair_returns:
        return {}

    # Align and equal-weight
    book = pd.concat(pair_returns, axis=1).fillna(0)
    port_ret = book.mean(axis=1)

    cum     = (1 + port_ret).cumprod()
    raw     = float(cum.iloc[-1] - 1)
    n_years = len(port_ret) / 252
    cagr    = float((1+raw)**(1/max(n_years,0.1))-1) if raw > -1 else float("-inf")
    mu, std = port_ret.mean(), port_ret.std()
    sharpe  = float(mu/std*math.sqrt(252)) if std > 0 else 0.0
    roll_max = cum.cummax()
    max_dd  = float(((cum-roll_max)/roll_max).min())

    return {
        "raw_return":   round(raw*100, 2),
        "cagr":         round(cagr*100, 2),
        "sharpe":       round(sharpe, 3),
        "max_drawdown": round(max_dd*100, 2),
        "n_pairs":      len(pair_returns),
        "pairs":        [f"{r['sym_a']}/{r['sym_b']}" for _, r in top10.iterrows()],
        "round":        23,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  REPORTING
# ══════════════════════════════════════════════════════════════════════════════

def print_top(results: List[dict], n: int = 15, label: str = ""):
    if not results:
        print("  No results.")
        return
    df = pd.DataFrame(results)
    df = df.sort_values("sharpe", ascending=False)
    print(f"\n  TOP {n} PAIRS{' — '+label if label else ''}:")
    print(f"  {'Pair':<14} {'Sector':<12} {'Method':<20} {'EntryZ':>6} "
          f"{'Sharpe':>8} {'CAGR%':>7} {'MaxDD%':>8} {'Trades':>7} {'WinRate':>8}")
    print("  " + "-" * 92)
    for _, r in df.head(n).iterrows():
        pair = f"{r['sym_a']}/{r['sym_b']}"
        print(f"  {pair:<14} {r['sector']:<12} {r.get('method',''):<20} "
              f"{r.get('entry_z',0):>6.1f} {r['sharpe']:>+8.3f} "
              f"{r['cagr']:>7.2f}% {r['max_drawdown']:>8.2f}% "
              f"{r.get('n_trades',0):>7} {r.get('win_rate',0):>7.1f}%")

    # Summary by sector
    if "sector" in df.columns:
        sec_agg = (df.groupby("sector")
                    .agg(avg_sharpe=("sharpe","mean"), count=("sharpe","count"))
                    .sort_values("avg_sharpe", ascending=False))
        print(f"\n  SECTOR RANKING:")
        for sec, row in sec_agg.iterrows():
            print(f"    {sec:<12} avg Sharpe {row['avg_sharpe']:+.3f}  ({int(row['count'])} pairs)")


def save_round(round_num: int, results, extra: dict = None):
    out = ROUNDS_DIR / f"pairs_round_{round_num}.json"
    data = {
        "round":     round_num,
        "timestamp": datetime.now().isoformat(),
        "n_results": len(results) if isinstance(results, list) else 1,
        "results":   results if isinstance(results, list) else [results],
    }
    if extra:
        data.update(extra)
    with open(out, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved → {out}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=None)
    args = parser.parse_args()

    print("=" * 72)
    print("PAIRS TRADING / STAT ARB HARNESS — Rounds 20-23")
    print(f"Based on: Isichenko 'Quantitative Portfolio Management'")
    print("=" * 72)

    # Build pair universe
    all_pairs = build_all_pairs()
    all_syms  = list({s for pair in all_pairs for s in pair[:2]})
    print(f"\n  Universe: {len(all_pairs)} pairs across {len(all_syms)} symbols")

    # Load all prices
    print("  Loading price data...")
    prices = {}
    for sym in all_syms:
        s = fetch_close(sym)
        if s is not None and len(s) > 252:
            prices[sym] = s
    print(f"  Loaded: {len(prices)}/{len(all_syms)} symbols")

    rounds_to_run = [args.round] if args.round else [20, 21, 22, 23]

    r20_results = []
    r21_results = []
    r22_results = []
    cointegrated_pairs = []

    for rnd in rounds_to_run:
        print(f"\n{'='*72}")
        print(f"  ROUND {rnd}")
        print(f"{'='*72}")

        if rnd == 20:
            r20_results = run_round20(prices)
            print_top(r20_results, n=15, label="R20 Baseline (no coint filter)")
            save_round(20, r20_results)

        elif rnd == 21:
            if not r20_results:
                r20_results = json.load(open(ROUNDS_DIR / "pairs_round_20.json"))["results"]
            r21_results, cointegrated_pairs = run_round21(prices)
            print_top(r21_results, n=15, label="R21 Cointegration-Filtered")
            save_round(21, r21_results,
                       {"n_cointegrated": len(cointegrated_pairs)})

        elif rnd == 22:
            if not cointegrated_pairs:
                # Rebuild from R21 saved results
                r21_saved = json.load(open(ROUNDS_DIR / "pairs_round_21.json"))["results"]
                seen = set()
                for r in r21_saved:
                    k = (r["sym_a"], r["sym_b"])
                    if k not in seen:
                        seen.add(k)
                        ya, xb = align_pair(prices.get(r["sym_a"], pd.Series()),
                                            prices.get(r["sym_b"], pd.Series()))
                        if len(ya) > 252:
                            cr = test_cointegration(ya, xb)
                            cointegrated_pairs.append((r["sym_a"], r["sym_b"],
                                                       r["sector"], cr))
            r22_results = run_round22(prices, cointegrated_pairs)
            print_top(r22_results, n=15, label="R22 Kalman Filter Dynamic Hedge")
            save_round(22, r22_results)

        elif rnd == 23:
            if not r20_results:
                r20_results = json.load(open(ROUNDS_DIR / "pairs_round_20.json"))["results"]
            if not r21_results:
                r21_results = json.load(open(ROUNDS_DIR / "pairs_round_21.json"))["results"]
            if not r22_results and (ROUNDS_DIR / "pairs_round_22.json").exists():
                r22_results = json.load(open(ROUNDS_DIR / "pairs_round_22.json"))["results"]
            r23 = run_round23(prices, r20_results, r21_results, r22_results)
            print(f"\n  PORTFOLIO RESULT (R23 — Multi-Pair Book):")
            print(f"  Sharpe: {r23.get('sharpe',0):+.3f}  CAGR: {r23.get('cagr',0):.2f}%  "
                  f"MaxDD: {r23.get('max_drawdown',0):.2f}%  Pairs: {r23.get('n_pairs',0)}")
            print(f"  Pairs in book: {', '.join(r23.get('pairs', []))}")
            save_round(23, r23)

    # Cross-round champion summary
    print(f"\n{'='*72}")
    print("  CROSS-ROUND SUMMARY")
    print(f"{'='*72}")
    all_results = r20_results + r21_results + r22_results
    if all_results:
        df_all = pd.DataFrame(all_results)
        best = df_all.sort_values("sharpe", ascending=False).head(5)
        print(f"\n  TOP 5 PAIRS OVERALL:")
        for _, r in best.iterrows():
            print(f"  {r['sym_a']}/{r['sym_b']:<10} R{r['round']}  "
                  f"Sharpe {r['sharpe']:+.3f}  CAGR {r['cagr']:.2f}%  "
                  f"DD {r['max_drawdown']:.2f}%  ({r['sector']})")

    print("\n  Done.")


if __name__ == "__main__":
    main()
