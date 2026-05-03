#!/usr/bin/env python3
"""
pairs_v2.py — Pairs Trading Harness with TradeLogger (Round 23)
================================================================
Replicates the exact strategy logic from pairs_harness.py (Rounds 20-23)
but logs every individual trade via TradeLogger instead of computing
aggregate stats.

One combined TradeLogger is used for all pairs/rounds.

Usage:
  /workspace/group/venv/bin/python3 trading_eval/framework/pairs_v2.py
"""

from __future__ import annotations

import itertools
import math
import os
import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Path setup so we can import from framework/ ───────────────────────────────
FRAMEWORK_DIR = Path(__file__).parent
EVAL_DIR      = FRAMEWORK_DIR.parent
sys.path.insert(0, str(FRAMEWORK_DIR))
sys.path.insert(0, str(EVAL_DIR))

try:
    import numpy as np
    import pandas as pd
    import yfinance as yf
    from statsmodels.tsa.stattools import coint, adfuller
    from statsmodels.regression.linear_model import OLS
    from statsmodels.tools import add_constant
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Run: python3 -m pip install yfinance pandas numpy statsmodels")
    sys.exit(1)

from base_harness import TradeLogger, fetch_data, get_close

# ── Paths ──────────────────────────────────────────────────────────────────────
CACHE_DIR  = EVAL_DIR / "cache"
ROUNDS_DIR = EVAL_DIR / "rounds"
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

CROSS_SECTOR_PAIRS = [
    ("XOM", "COP"),
    ("AAPL", "MSFT"),
    ("JPM", "GS"),
    ("KO", "PEP"),
    ("LMT", "NOC"),
    ("F", "GM"),
    ("WMT", "COST"),
    ("JNJ", "PFE"),
    ("CAT", "DE"),
    ("UNH", "LLY"),
]


# ══════════════════════════════════════════════════════════════════════════════
#  DATA LAYER  (mirrors pairs_harness.py fetch_close exactly)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_close(symbol: str) -> Optional[pd.Series]:
    """Load close prices — reuse cache from other harnesses."""
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

    cp = CACHE_DIR / f"ohlcv_{symbol}_{YEARS}yr.pkl"
    try:
        t = yf.Ticker(symbol)
        h = t.history(start=START_DATE, end=END_DATE, auto_adjust=True)
        if h.empty or len(h) < 200:
            return None
        df = h[["Open", "High", "Low", "Close", "Volume"]].dropna()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        with open(cp, "wb") as f:
            pickle.dump(df, f)
        return df["Close"]
    except Exception as e:
        print(f"  x {symbol}: {e}", file=sys.stderr)
        return None


def align_pair(s1: pd.Series, s2: pd.Series) -> Tuple[pd.Series, pd.Series]:
    """Align two price series to common dates."""
    common = s1.index.intersection(s2.index)
    return s1.loc[common], s2.loc[common]


# ══════════════════════════════════════════════════════════════════════════════
#  STATISTICAL TESTS  (exact copy from pairs_harness.py)
# ══════════════════════════════════════════════════════════════════════════════

def test_cointegration(y: pd.Series, x: pd.Series) -> dict:
    try:
        x_c   = add_constant(x.values)
        model = OLS(y.values, x_c).fit()
        beta  = float(model.params[1])
        alpha = float(model.params[0])
        spread = y - beta * x - alpha

        adf_stat, adf_p, _, _, _, _ = adfuller(spread.dropna(), maxlags=1)
        _, eg_p, _ = coint(y.values, x.values)

        return {
            "beta":         round(beta, 4),
            "alpha":        round(alpha, 4),
            "adf_stat":     round(float(adf_stat), 4),
            "adf_p":        round(float(adf_p), 4),
            "eg_p":         round(float(eg_p), 4),
            "spread":       spread,
            "cointegrated": float(eg_p) < 0.05,
        }
    except Exception:
        return {"cointegrated": False, "eg_p": 1.0, "spread": None}


def rolling_zscore(spread: pd.Series, window: int = 60) -> pd.Series:
    """Z-score of spread relative to rolling mean/std."""
    mean = spread.rolling(window, min_periods=window // 2).mean()
    std  = spread.rolling(window, min_periods=window // 2).std().replace(0, np.nan)
    return (spread - mean) / std


# ══════════════════════════════════════════════════════════════════════════════
#  KALMAN FILTER  (exact copy from pairs_harness.py)
# ══════════════════════════════════════════════════════════════════════════════

def kalman_spread(y: pd.Series, x: pd.Series,
                  delta: float = 1e-5, Ve: float = 0.001) -> Tuple[pd.Series, pd.Series]:
    n    = len(y)
    Vw   = delta / (1 - delta) * np.eye(2)
    P    = np.zeros((2, 2))
    beta = np.zeros((n, 2))
    e    = np.zeros(n)
    Q    = np.zeros(n)

    for t in range(n):
        xt = np.array([float(x.iloc[t]), 1.0])
        if t == 0:
            beta[t] = [1.0, 0.0]
            P = Vw
        else:
            beta[t] = beta[t-1]
            P       = P + Vw

        Q[t]    = float(xt @ P @ xt) + Ve
        K       = P @ xt / Q[t]
        e[t]    = float(y.iloc[t]) - float(xt @ beta[t])
        beta[t] = beta[t] + K * e[t]
        P       = P - np.outer(K, xt) @ P

    hedge_ratio = pd.Series(beta[:, 0], index=y.index, name="hedge_ratio")
    intercept   = pd.Series(beta[:, 1], index=y.index, name="intercept")
    spread      = y - hedge_ratio * x - intercept
    return spread, hedge_ratio


# ══════════════════════════════════════════════════════════════════════════════
#  PAIR UNIVERSE BUILDER
# ══════════════════════════════════════════════════════════════════════════════

def build_all_pairs() -> List[Tuple[str, str, str]]:
    """Returns list of (sym1, sym2, sector_label) tuples."""
    pairs = []
    for sector, tickers in SECTORS.items():
        for a, b in itertools.combinations(tickers, 2):
            pairs.append((a, b, sector))
    for a, b in CROSS_SECTOR_PAIRS:
        pairs.append((a, b, "cross"))
    return pairs


# ══════════════════════════════════════════════════════════════════════════════
#  TRADE-LEVEL BACKTEST  (same logic as backtest_pair, but yields trade records)
# ══════════════════════════════════════════════════════════════════════════════

def backtest_pair_trades(
    ya: pd.Series,
    xb: pd.Series,
    zscore: pd.Series,
    leg_a: str,
    leg_b: str,
    entry_z: float = 2.0,
    exit_z: float  = 0.5,
    stop_z: float  = 4.0,
    cost_bps: float = 2.0,
    method: str    = "log_ratio",
    round_num: int = 23,
    extra_params: dict = None,
) -> List[dict]:
    """
    Same entry/exit logic as pairs_harness.backtest_pair(), but instead of
    computing aggregate metrics, returns a list of individual trade dicts
    ready to be passed to TradeLogger.log(**trade).

    direction refers to leg_a:
      +1 position (long spread = long ya, short xb) -> direction 'long'
      -1 position (short spread = short ya, long xb) -> direction 'short'
    """
    if zscore is None or len(zscore) < 100:
        return []

    trades_out = []
    in_trade   = False
    direction  = 0       # +1 long spread, -1 short spread
    entry_idx  = None
    entry_z_val = None

    for i in range(1, len(zscore)):
        z = float(zscore.iloc[i])
        if math.isnan(z):
            continue

        if not in_trade:
            if z < -entry_z:
                in_trade    = True
                direction   = 1
                entry_idx   = i
                entry_z_val = z
            elif z > entry_z:
                in_trade    = True
                direction   = -1
                entry_idx   = i
                entry_z_val = z
        else:
            exit_triggered = (abs(z) < exit_z) or (abs(z) > stop_z)
            if exit_triggered:
                # Build trade record
                entry_date = zscore.index[entry_idx]
                exit_date  = zscore.index[i]
                hold_days  = (exit_date - entry_date).days

                # leg_a prices at entry and exit
                ep = float(ya.iloc[entry_idx]) if entry_idx < len(ya) else float("nan")
                xp = float(ya.iloc[i])         if i < len(ya)         else float("nan")

                # Spread (log-ratio or OLS spread) as proxy for "price"
                entry_spread = float(zscore.index.map(lambda d: d).get_loc if False else 0)
                # We use leg_a price as entry_price/exit_price per the spec.
                # The zscore at entry/exit is captured in spread_zscore / exit_zscore.

                # Return: long spread => (ya_ret - xb_ret) over hold period
                ya_entry = float(ya.iloc[entry_idx])
                ya_exit  = float(ya.iloc[i])
                xb_entry = float(xb.iloc[entry_idx])
                xb_exit  = float(xb.iloc[i])

                if ya_entry > 0 and xb_entry > 0:
                    ya_ret = (ya_exit - ya_entry) / ya_entry
                    xb_ret = (xb_exit - xb_entry) / xb_entry
                    # long spread: long ya short xb -> return = ya_ret - xb_ret
                    # short spread: short ya long xb -> return = xb_ret - ya_ret
                    spread_ret = direction * (ya_ret - xb_ret)
                    # transaction cost: 2 legs in + 2 legs out = 4 legs total
                    cost = 4 * (cost_bps / 10000)
                    return_pct = round((spread_ret - cost) * 100, 4)
                else:
                    return_pct = 0.0

                leg_a_dir = "long" if direction == 1 else "short"

                params_dict = {
                    "entry_z": entry_z,
                    "exit_z":  exit_z,
                    "window":  60,
                    "pair":    f"{leg_a}_{leg_b}",
                    "method":  method,
                    "round":   round_num,
                }
                if extra_params:
                    params_dict.update(extra_params)

                exit_zscore_val = round(z, 4)
                entry_zscore_val = round(entry_z_val, 4)

                trades_out.append(dict(
                    ticker        = f"{leg_a}_{leg_b}",
                    entry_date    = entry_date,
                    exit_date     = exit_date,
                    return_pct    = return_pct,
                    hold_days     = hold_days,
                    direction     = leg_a_dir,
                    entry_price   = round(ya_entry, 4),
                    exit_price    = round(ya_exit, 4),
                    params        = params_dict,
                    notes         = (f"zscore={entry_zscore_val:+.4f} entry, "
                                     f"exit={exit_zscore_val:+.4f}"),
                    leg_a         = leg_a,
                    leg_b         = leg_b,
                    spread_zscore = entry_zscore_val,
                    exit_zscore   = exit_zscore_val,
                ))

                in_trade  = False
                direction = 0
                entry_idx = None

    return trades_out


# ══════════════════════════════════════════════════════════════════════════════
#  ROUND RUNNERS — same logic as pairs_harness.py, now log trades
# ══════════════════════════════════════════════════════════════════════════════

def run_round20_trades(prices: dict, logger: TradeLogger) -> List[dict]:
    """
    R20: Baseline — ratio z-score on all pairs, no cointegration pre-filter.
    Tests entry z: 1.5, 2.0, 2.5 | exit z: 0.5 | z-window: 60
    """
    all_pairs = build_all_pairs()
    print(f"  [R20] Testing {len(all_pairs)} pairs x 3 entry thresholds = "
          f"{len(all_pairs)*3} backtests")

    results_meta = []

    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        log_ratio = np.log(ya / xb)

        for entry_z in [1.5, 2.0, 2.5]:
            z = rolling_zscore(log_ratio, window=60)
            trades = backtest_pair_trades(
                ya, xb, z,
                leg_a      = sym_a,
                leg_b      = sym_b,
                entry_z    = entry_z,
                exit_z     = 0.5,
                stop_z     = 4.0,
                cost_bps   = 2.0,
                method     = "log_ratio",
                round_num  = 20,
                extra_params = {"sector": sector},
            )
            for t in trades:
                logger.log(**t)
            results_meta.append({
                "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                "method": "log_ratio", "entry_z": entry_z, "round": 20,
                "n_trades": len(trades),
            })

    total = sum(r["n_trades"] for r in results_meta)
    print(f"  [R20] Logged {total} trades across {len(results_meta)} param combos")
    return results_meta


def run_round21_trades(prices: dict, logger: TradeLogger):
    """
    R21: Cointegration-filtered (Engle-Granger p < 0.05).
    Uses OLS hedge ratio. Tests entry z: 1.5, 2.0, 2.5 | exit z: 0.5
    Returns (results_meta, cointegrated_pairs)
    """
    all_pairs = build_all_pairs()
    cointegrated = []

    print(f"  [R21] Testing cointegration on {len(all_pairs)} pairs...")
    for sym_a, sym_b, sector in all_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue
        cr = test_cointegration(ya, xb)
        if cr["cointegrated"]:
            cointegrated.append((sym_a, sym_b, sector, cr))

    print(f"  [R21] Cointegrated pairs (p<0.05): {len(cointegrated)} / {len(all_pairs)}")

    results_meta = []
    for sym_a, sym_b, sector, cr in cointegrated:
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        spread = cr.get("spread")
        if spread is None or len(spread) < 252:
            continue
        for entry_z in [1.5, 2.0, 2.5]:
            z = rolling_zscore(spread, window=60)
            trades = backtest_pair_trades(
                ya, xb, z,
                leg_a      = sym_a,
                leg_b      = sym_b,
                entry_z    = entry_z,
                exit_z     = 0.5,
                stop_z     = 4.0,
                cost_bps   = 2.0,
                method     = "coint_ols",
                round_num  = 21,
                extra_params = {
                    "sector": sector,
                    "eg_p":   cr["eg_p"],
                    "beta":   cr["beta"],
                },
            )
            for t in trades:
                logger.log(**t)
            results_meta.append({
                "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                "method": "coint_ols", "entry_z": entry_z,
                "eg_p": cr["eg_p"], "beta": cr["beta"],
                "round": 21, "n_trades": len(trades),
            })

    total = sum(r["n_trades"] for r in results_meta)
    print(f"  [R21] Logged {total} trades across {len(results_meta)} param combos")
    return results_meta, cointegrated


def run_round22_trades(prices: dict, cointegrated_pairs: list,
                       logger: TradeLogger) -> List[dict]:
    """
    R22: Kalman filter dynamic hedge ratio on cointegrated pairs.
    Tests delta: 1e-5, 1e-4, 5e-4 | entry_z: 2.0 | exit_z: 0.5
    """
    results_meta = []
    for sym_a, sym_b, sector, cr in cointegrated_pairs:
        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        for delta in [1e-5, 1e-4, 5e-4]:
            try:
                k_spread, k_beta = kalman_spread(ya, xb, delta=delta)
                z = rolling_zscore(k_spread, window=60)
                method_tag = f"kalman_d{delta:.0e}"
                trades = backtest_pair_trades(
                    ya, xb, z,
                    leg_a      = sym_a,
                    leg_b      = sym_b,
                    entry_z    = 2.0,
                    exit_z     = 0.5,
                    stop_z     = 4.0,
                    cost_bps   = 2.0,
                    method     = method_tag,
                    round_num  = 22,
                    extra_params = {"sector": sector, "delta": delta},
                )
                for t in trades:
                    logger.log(**t)
                results_meta.append({
                    "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
                    "method": method_tag, "entry_z": 2.0, "delta": delta,
                    "round": 22, "n_trades": len(trades),
                })
            except Exception:
                continue

    total = sum(r["n_trades"] for r in results_meta)
    print(f"  [R22] Logged {total} trades across {len(results_meta)} param combos")
    return results_meta


def run_round23_trades(prices: dict,
                       all_r20: List[dict],
                       all_r21: List[dict],
                       all_r22: List[dict],
                       logger: TradeLogger) -> List[dict]:
    """
    R23: Multi-pair portfolio — combine top 10 pairs from R20-R22.
    Selects top pairs by highest trade count (proxy for activity, since we
    don't compute Sharpe here). Logs each pair's trades tagged round=23.
    """
    # Pool all meta results and pick top 10 unique pairs by most traded
    pool = all_r20 + all_r21 + all_r22
    if not pool:
        print("  [R23] No upstream results to build portfolio from.")
        return []

    df_pool = pd.DataFrame(pool)

    # De-duplicate: keep highest-trade-count row per (sym_a, sym_b)
    top_pairs = (
        df_pool.sort_values("n_trades", ascending=False)
               .drop_duplicates(subset=["sym_a", "sym_b"])
               .head(10)
    )

    print(f"  [R23] Building portfolio from top {len(top_pairs)} pairs...")

    results_meta = []
    for _, row in top_pairs.iterrows():
        sym_a  = row["sym_a"]
        sym_b  = row["sym_b"]
        sector = row.get("sector", "")
        method = row.get("method", "log_ratio")

        if sym_a not in prices or sym_b not in prices:
            continue
        ya, xb = align_pair(prices[sym_a], prices[sym_b])
        if len(ya) < 252:
            continue

        # Rebuild spread using same method as the source round
        if "kalman" in method:
            delta = row.get("delta", 1e-5)
            k_spread, _ = kalman_spread(ya, xb, delta=float(delta))
            spread = k_spread
        elif "coint" in method:
            cr = test_cointegration(ya, xb)
            spread = cr.get("spread") if cr.get("spread") is not None else np.log(ya / xb)
        else:
            spread = np.log(ya / xb)

        z = rolling_zscore(spread, window=60)

        # R23 always uses entry_z=2.0, exit_z=0.5 (same as run_round23 in harness)
        trades = backtest_pair_trades(
            ya, xb, z,
            leg_a      = sym_a,
            leg_b      = sym_b,
            entry_z    = 2.0,
            exit_z     = 0.5,
            stop_z     = 4.0,
            cost_bps   = 2.0,
            method     = method,
            round_num  = 23,
            extra_params = {"sector": sector, "portfolio": "top10"},
        )
        for t in trades:
            logger.log(**t)
        results_meta.append({
            "sym_a": sym_a, "sym_b": sym_b, "sector": sector,
            "method": method, "round": 23, "n_trades": len(trades),
        })

    total = sum(r["n_trades"] for r in results_meta)
    print(f"  [R23] Logged {total} trades for {len(results_meta)} pairs in portfolio")
    return results_meta


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 72)
    print("PAIRS TRADING / STAT ARB — TradeLogger Version (pairs_v2)")
    print(f"Round 23 | Based on Isichenko 'Quantitative Portfolio Management'")
    print("=" * 72)

    # One combined logger for all rounds/pairs
    logger = TradeLogger(round_num=23, strategy="pairs", category="stat_arb")

    # Build universe
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

    # Run all rounds in order, collecting meta for cross-round portfolio (R23)
    print(f"\n{'='*72}")
    print("  ROUND 20 — Baseline (log-ratio z-score, no coint filter)")
    print(f"{'='*72}")
    r20_meta = run_round20_trades(prices, logger)

    print(f"\n{'='*72}")
    print("  ROUND 21 — Cointegration-Filtered (OLS hedge ratio)")
    print(f"{'='*72}")
    r21_meta, cointegrated_pairs = run_round21_trades(prices, logger)

    print(f"\n{'='*72}")
    print("  ROUND 22 — Kalman Filter Dynamic Hedge Ratio")
    print(f"{'='*72}")
    r22_meta = run_round22_trades(prices, cointegrated_pairs, logger)

    print(f"\n{'='*72}")
    print("  ROUND 23 — Multi-Pair Portfolio (Top 10 pairs)")
    print(f"{'='*72}")
    r23_meta = run_round23_trades(prices, r20_meta, r21_meta, r22_meta, logger)

    # Save
    print(f"\n{'='*72}")
    print(f"  Total trades logged: {len(logger)}")
    logger.save()

    print("\n  Done.")


if __name__ == "__main__":
    main()
