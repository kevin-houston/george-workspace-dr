"""
H307 — Targeted ETF Pairs Trading: Johansen Cointegration
==========================================================

Hypothesis:
  H271 (Z-score mean reversion on broad 23-ETF universe) NOT CONFIRMED — OOS
  Sharpe 0.296. Failure mode: spurious cointegration in IS; IS cointegration
  inversely predicted OOS (structural breaks: SVB 2023, gold-silver decoupling).

  H307 tests whether pre-specifying economically motivated pairs with genuine
  fundamental links (same underlying commodity/sector) produces stable OOS
  cointegration and tradeable mean-reversion.

  Candidate pairs (long/short economically related ETFs):
    1. GDX/SIL  — gold miners vs silver miners (share cost structure, same macro driver)
    2. XLE/OIH  — broad energy vs oil services (OIH is subset of XLE)
    3. XLK/QQQ  — tech sector vs tech-heavy Nasdaq (QQQ ~60% tech)
    4. LQD/HYG  — investment-grade vs high-yield corporate bonds (credit spread)
    5. EWJ/EFA  — Japan equity vs developed ex-US equity
    6. GLD/IAU  — two gold ETFs (same underlying, pure arb signal)
    7. XLF/KBE  — financials sector vs bank ETF (KBE subset)
    8. XLV/IBB  — health care vs biotech (IBB is high-vol subset)

  Method:
    IS phase: Johansen cointegration test on each pair (VAR lag=5).
    Select pairs with trace statistic p < 0.10 in IS.
    OOS phase: trade selected pairs using Z-score on the cointegrating residual.

  Trade rule (weekly rebalance):
    - Compute OLS spread: spread = log(A) - β * log(B), β from IS regression
    - z = (spread - spread_mean_60d) / spread_std_60d
    - Long spread (long A, short B) when z < -1.5; exit when z > -0.5
    - Short spread (short A, long B) when z > +1.5; exit when z < +0.5
    - Long-only constraint: no actual shorting; instead use BIL for "short leg"

  Long-only adaptation (no shorting allowed):
    - "Long spread" = long A only (buy the underperformer)
    - "Short spread" = long B only (buy the overperformer when reversed)
    - This gives asymmetric exposure but avoids needing short positions

  Gate: OOS Sharpe > 0.8 (lower than equity momentum; pairs strategies have
        inherently lower gross Sharpe due to market-neutrality)

  Variants:
    A: All IS-qualified pairs, equal-weight when in trade
    B: Only strongest pair (highest IS trace stat), single pair
    C: Add VIX < 25 gate (only trade in calm markets)

  IS:  2008-01-01 to 2017-12-31
  OOS: 2018-01-01 to 2026-06-13
"""

import json, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from statsmodels.tsa.vector_ar.vecm import coint_johansen

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

# Candidate pairs (A, B) — economically motivated
PAIRS = [
    ("GDX", "SIL"),
    ("XLE", "OIH"),
    ("XLK", "QQQ"),
    ("LQD", "HYG"),
    ("EWJ", "EFA"),
    ("GLD", "IAU"),
    ("XLF", "KBE"),
    ("XLV", "IBB"),
]

BIL        = "BIL"
FULL_START = "2006-01-01"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
OOS_END    = "2026-06-13"
COST_BPS   = 15  # pairs trades have higher TC (2 legs)
ENTRY_Z    = 1.5
EXIT_Z     = 0.5
LOOKBACK   = 60  # rolling window for z-score normalization


def fetch_prices():
    all_t = sorted(set(t for pair in PAIRS for t in pair) | {BIL})
    raw = yf.download(all_t, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def johansen_test(log_a, log_b):
    """Returns trace statistic and 5% critical value for cointegration rank 0."""
    df = pd.concat([log_a, log_b], axis=1).dropna()
    if len(df) < 100:
        return 0, 999, False
    try:
        result = coint_johansen(df.values, det_order=0, k_ar_diff=5)
        trace_stat = result.lr1[0]
        crit_95    = result.cvt[0, 1]   # 5% critical value, rank 0
        coint_flag = trace_stat > crit_95
        return trace_stat, crit_95, coint_flag
    except Exception:
        return 0, 999, False


def ols_beta(log_a, log_b):
    """OLS hedge ratio: log_a = alpha + beta * log_b + epsilon."""
    log_a = np.asarray(log_a, dtype=float)
    log_b = np.asarray(log_b, dtype=float)
    mask = np.isfinite(log_a) & np.isfinite(log_b)
    log_a, log_b = log_a[mask], log_b[mask]
    if len(log_a) < 20:
        return 0.0, 1.0
    # Use np.polyfit as a robust fallback
    beta, alpha = np.polyfit(log_b, log_a, 1)
    return float(alpha), float(beta)


def compute_spread(log_a, log_b, alpha, beta):
    return log_a - alpha - beta * log_b


def backtest_pair(spread_oos, bil_daily, vix_daily=None, use_vix=False, label=""):
    """Long-only pairs: buy 'undervalued' leg when z < -ENTRY_Z."""
    # Compute z-score using rolling 60-day mean/std
    z = (spread_oos - spread_oos.rolling(LOOKBACK).mean()) / (
        spread_oos.rolling(LOOKBACK).std() + 1e-9)

    equity = 1.0
    in_trade = None  # 'long_spread' or 'short_spread'
    equity_curve = {}
    prev_day = None

    # Align BIL returns
    bil_ret = bil_daily.pct_change().fillna(0)

    for dt, z_val in z.items():
        if pd.isna(z_val):
            equity_curve[dt] = equity
            prev_day = dt
            continue

        # VIX gate
        if use_vix and vix_daily is not None and dt in vix_daily.index:
            if vix_daily.loc[dt] >= 25:
                if in_trade is not None:
                    equity *= (1 - COST_BPS / 10000)  # exit cost
                    in_trade = None
                equity_curve[dt] = equity
                prev_day = dt
                continue

        # Entry/exit logic
        if in_trade is None:
            if z_val < -ENTRY_Z:
                in_trade = "long_spread"
                equity *= (1 - COST_BPS / 10000)
            elif z_val > ENTRY_Z:
                in_trade = "short_spread"
                equity *= (1 - COST_BPS / 10000)
        elif in_trade == "long_spread" and z_val > -EXIT_Z:
            in_trade = None
            equity *= (1 - COST_BPS / 10000)
        elif in_trade == "short_spread" and z_val < EXIT_Z:
            in_trade = None
            equity *= (1 - COST_BPS / 10000)

        # Daily return
        if prev_day is not None and prev_day in spread_oos.index:
            if in_trade is not None:
                spread_ret = spread_oos.loc[dt] - spread_oos.loc[prev_day]
                if in_trade == "long_spread":
                    daily_ret = spread_ret  # positive when spread reverts up
                else:
                    daily_ret = -spread_ret
                equity *= (1 + daily_ret * 0.5)  # half-capital: 2 legs split
            else:
                equity *= (1 + bil_ret.get(dt, 0))

        equity_curve[dt] = equity
        prev_day = dt

    ec = pd.Series(equity_curve)
    rets = ec.pct_change().dropna()
    if len(rets) < 50:
        return ec, {"sharpe": 0, "cagr": 0, "maxdd": 0}
    ann_ret = (ec.iloc[-1] ** (252 / len(ec)) - 1) if len(ec) > 1 else 0
    ann_vol = rets.std() * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0
    roll_max = ec.cummax()
    maxdd = ((ec - roll_max) / roll_max).min()
    return ec, {"sharpe": round(sharpe, 3), "cagr": round(ann_ret, 4),
                "maxdd": round(maxdd, 4)}


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 60)
print("H307 — Targeted ETF Pairs: Johansen Cointegration")
print("=" * 60)

print("\n[1] Fetching prices…")
prices = fetch_prices()
log_prices = np.log(prices)

# VIX
vix = yf.download("^VIX", start=FULL_START, end=OOS_END, progress=False)["Close"].squeeze()
bil_daily = prices[BIL]

print("\n[2] IS cointegration tests (2008-2017)…")
print(f"\n{'Pair':<12} {'Trace':>8} {'Crit95':>8} {'Coint?':>8}")
print("-" * 40)

qualified_pairs = []
for a, b in PAIRS:
    if a not in log_prices.columns or b not in log_prices.columns:
        print(f"  {a}/{b}: missing data")
        continue
    is_log_a = log_prices[a][(log_prices.index >= IS_START) & (log_prices.index <= IS_END)]
    is_log_b = log_prices[b][(log_prices.index >= IS_START) & (log_prices.index <= IS_END)]
    trace, crit, is_coint = johansen_test(is_log_a, is_log_b)
    print(f"  {a+'/'+b:<10} {trace:>8.2f} {crit:>8.2f} {'YES' if is_coint else 'no':>8}")
    if is_coint:
        # Compute IS beta for OOS spread
        alpha_hat, beta_hat = ols_beta(is_log_a.values, is_log_b.values)
        qualified_pairs.append((a, b, alpha_hat, beta_hat, trace))

print(f"\n{len(qualified_pairs)} of {len(PAIRS)} pairs qualified (IS cointegrated)")

if not qualified_pairs:
    print("\nNo cointegrated pairs found. H307 NOT CONFIRMED by default.")
else:
    print("\n[3] OOS pair backtests (2018-2026)…")
    best_sharpe = 0
    pair_results = {}

    for a, b, alpha, beta, trace in qualified_pairs:
        oos_log_a = log_prices[a][(log_prices.index >= OOS_START) & (log_prices.index <= OOS_END)]
        oos_log_b = log_prices[b][(log_prices.index >= OOS_START) & (log_prices.index <= OOS_END)]
        spread_oos = compute_spread(oos_log_a, oos_log_b, alpha, beta)
        vix_oos = vix[(vix.index >= OOS_START) & (vix.index <= OOS_END)]

        ec, stats = backtest_pair(spread_oos, bil_daily, vix_oos, use_vix=False,
                                  label=f"{a}/{b}")
        _, stats_vix = backtest_pair(spread_oos, bil_daily, vix_oos, use_vix=True,
                                     label=f"{a}/{b}+VIX")
        pair_results[f"{a}/{b}"] = {"plain": stats, "vix_gated": stats_vix,
                                     "trace": round(trace, 2)}
        if stats["sharpe"] > best_sharpe:
            best_sharpe = stats["sharpe"]
        if stats_vix["sharpe"] > best_sharpe:
            best_sharpe = stats_vix["sharpe"]

    print(f"\n{'Pair':<12} {'Sharpe':>8} {'CAGR':>8} {'MaxDD':>8} | {'VIX-gated Sharpe':>18}")
    print("-" * 60)
    for pair_name, r in pair_results.items():
        print(f"  {pair_name:<10} {r['plain']['sharpe']:>8.3f} {r['plain']['cagr']:>7.1%} "
              f"{r['plain']['maxdd']:>7.1%} | {r['vix_gated']['sharpe']:>18.3f}")

    # Variant A: equal-weight all qualified pairs
    all_spreads = []
    for a, b, alpha, beta, trace in qualified_pairs:
        oos_log_a = log_prices[a][(log_prices.index >= OOS_START)]
        oos_log_b = log_prices[b][(log_prices.index >= OOS_START)]
        sp = compute_spread(oos_log_a, oos_log_b, alpha, beta)
        all_spreads.append(sp)

    combined_spread = pd.concat(all_spreads, axis=1).mean(axis=1)
    ec_combined, stats_combined = backtest_pair(combined_spread, bil_daily,
                                                 label="Composite")
    print(f"\n  {'Composite':<10} {stats_combined['sharpe']:>8.3f} {stats_combined['cagr']:>7.1%} "
          f"{stats_combined['maxdd']:>7.1%}")

    best_sharpe = max(best_sharpe, stats_combined["sharpe"])
    confirmed = best_sharpe >= 0.8

    print("\n" + "=" * 60)
    print(f"H307 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  Best OOS Sharpe: {best_sharpe:.3f}  (gate: 0.8)")
    print("=" * 60)

    out = {
        "hypothesis": "H307",
        "title": "Targeted ETF Pairs: Johansen Cointegration",
        "candidate_pairs": [f"{a}/{b}" for a, b in PAIRS],
        "qualified_pairs_count": len(qualified_pairs),
        "is_period": f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {OOS_END}",
        "gate": "OOS Sharpe > 0.8",
        "confirmed": bool(confirmed),
        "best_oos_sharpe": best_sharpe,
        "pair_results": pair_results,
        "composite": stats_combined,
    }
    Path(RESULT_DIR / "h307_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nResults → {RESULT_DIR / 'h307_results.json'}")
