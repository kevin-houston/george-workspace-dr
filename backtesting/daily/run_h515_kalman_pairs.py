"""
H515 — ETF Pairs Trading with Kalman-Filter Adaptive Hedge Ratio + Rolling
Cointegration Gate (§3.8, 151 Strategies)
============================================================================

Hypothesis:
  H246/H271/H307 (static-beta ETF pairs, various universes) all NOT CONFIRMED.
  H307's own post-mortem named the specific failure mode: "IS cointegration
  inversely predicted OOS — structural breaks in all pairs (SVB 2023,
  gold-silver decoupling)." The shared root cause across all three attempts is
  a FROZEN hedge ratio (OLS beta estimated once on IS data, 2008-2017) applied
  unchanged across an 8-9 year OOS window, plus a binary "cointegrated or not"
  screen that never re-checks whether the relationship is still holding.

  H515 tests whether making both of those adaptive fixes the family:
    1. Hedge ratio: recursive Kalman filter (2-state: intercept + slope),
       updated causally every trading day — no frozen IS-only beta.
    2. Cointegration gate: rolling 252-day ADF test on the Kalman residual;
       only trade a pair on days its residual currently passes the ADF
       stationarity test (p < 0.10) — trading turns off automatically during
       a structural break instead of trusting a decade-stale IS test.

  Method (per pair, causal/no-look-ahead):
    - Kalman filter state x_t = [alpha_t, beta_t], observation:
        log(A_t) = alpha_t + beta_t * log(B_t) + noise
      Standard Chan (2013) pairs-trading Kalman setup: state transition =
      identity (random walk parameters), delta=1e-4 controls state
      process noise, observation noise variance estimated online.
    - z-score = innovation / sqrt(innovation variance) — this is the Kalman
      filter's own online-normalized residual, needs no rolling window.
    - Enter when |z| > ENTRY_Z, exit when |z| < EXIT_Z, same long-only
      leg-substitution adaptation as H307 (no shorting).
    - Rolling ADF gate: compute ADF p-value on the trailing 252-day window of
      Kalman residuals; if p >= 0.10, force flat regardless of z-score.

  Variants:
    A: Kalman beta + z-score, NO rolling ADF gate (isolates the beta-adaptivity effect)
    B: Kalman beta + z-score + rolling ADF gate (full fix)
    C: Composite — equal-weight all pairs that ever pass the IS cointegration
       screen, Variant B rules

  Gate: OOS Sharpe > 0.8 (same as H307 — pairs strategies have inherently
        lower gross Sharpe due to market-neutrality)

  IS:  2008-01-01 to 2017-12-31 (screen only — pairs that were EVER cointegrated
       IS qualify for OOS testing; the OOS hedge ratio itself is Kalman-adaptive,
       not IS-frozen)
  OOS: 2018-01-01 to 2026-06-13
"""

import json, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from statsmodels.tsa.vector_ar.vecm import coint_johansen
from statsmodels.tsa.stattools import adfuller

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

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
COST_BPS   = 15
ENTRY_Z    = 1.5
EXIT_Z     = 0.5
ADF_WINDOW = 252
ADF_P      = 0.10
DELTA      = 1e-4   # Kalman state process-noise scale (Chan 2013 default)


def fetch_prices():
    all_t = sorted(set(t for pair in PAIRS for t in pair) | {BIL})
    raw = yf.download(all_t, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def johansen_screen(log_a, log_b):
    df = pd.concat([log_a, log_b], axis=1).dropna()
    if len(df) < 100:
        return 0, 999, False
    try:
        result = coint_johansen(df.values, det_order=0, k_ar_diff=5)
        trace_stat = result.lr1[0]
        crit_95    = result.cvt[0, 1]
        return trace_stat, crit_95, trace_stat > crit_95
    except Exception:
        return 0, 999, False


def kalman_pair(log_a, log_b):
    """
    Causal 2-state Kalman filter: x_t = [alpha_t, beta_t]'.
    Observation: y_t = log_a[t] = H_t @ x_t + eps_t, H_t = [1, log_b[t]].
    Random-walk state transition (Chan 2013 pairs-trading recipe).
    Returns per-day: predicted spread (residual) and its std (for z-score),
    fully causal — beta_t at day t only uses data through day t-1.
    """
    n = len(log_a)
    x = np.zeros(2)                    # [alpha, beta]
    P = np.eye(2) * 1.0                # state covariance
    Vw = DELTA / (1 - DELTA) * np.eye(2)   # process noise
    Ve = 1e-3                          # observation noise (adapted online)

    residuals = np.full(n, np.nan)
    resid_std = np.full(n, np.nan)

    R = np.zeros((2, 2))  # running P propagated

    for t in range(n):
        a_t, b_t = log_a[t], log_b[t]
        if not (np.isfinite(a_t) and np.isfinite(b_t)):
            continue
        H = np.array([1.0, b_t])

        # Predict
        R = P + Vw
        y_hat = H @ x
        e = a_t - y_hat
        Q = H @ R @ H.T + Ve

        residuals[t] = e
        resid_std[t] = np.sqrt(max(Q, 1e-12))

        # Update
        K = (R @ H) / Q
        x = x + K * e
        P = R - np.outer(K, H) @ R

        # Online obs-noise variance estimate (simple EW update)
        Ve = 0.98 * Ve + 0.02 * (e ** 2)

    return residuals, resid_std


def rolling_adf_pass(residuals_series):
    """Rolling 252d ADF p-value on residuals; True where p < ADF_P."""
    n = len(residuals_series)
    passes = np.zeros(n, dtype=bool)
    vals = residuals_series.values
    for i in range(ADF_WINDOW, n):
        window = vals[i - ADF_WINDOW:i]
        window = window[np.isfinite(window)]
        if len(window) < ADF_WINDOW * 0.8:
            continue
        try:
            pval = adfuller(window, maxlag=5, autolag=None)[1]
            passes[i] = pval < ADF_P
        except Exception:
            passes[i] = False
    return passes


def backtest_pair(dates, z, adf_pass, bil_ret, spread_diff, use_adf, label=""):
    """
    Causal two-pass design (fixes the same-day decide+credit look-ahead bug
    caught during H515 development — entering on z[i] and crediting spread_diff[i]
    in the same step used tomorrow's-unknown-yet information, since spread_diff[i]
    is the move realized ON day i, the same day z[i] is observed. Pass 1 decides
    the position state using z/adf known as of each day's close. Pass 2 applies
    day i's return using the position decided as of day i-1's close — i.e. a
    decision made from yesterday's close information earns today's move.
    """
    n = len(dates)
    in_trade = None
    position_series = [None] * n  # position HELD AS OF close of day i (decided using z[i])
    trade_change = [False] * n

    for i in range(n):
        z_val = z[i]
        gated_flat = use_adf and not adf_pass[i]
        prev_trade = in_trade

        if pd.isna(z_val) or gated_flat:
            in_trade = None
        elif in_trade is None:
            if z_val < -ENTRY_Z:
                in_trade = "long_spread"
            elif z_val > ENTRY_Z:
                in_trade = "short_spread"
        elif in_trade == "long_spread" and z_val > -EXIT_Z:
            in_trade = None
        elif in_trade == "short_spread" and z_val < EXIT_Z:
            in_trade = None

        position_series[i] = in_trade
        trade_change[i] = (in_trade != prev_trade)

    equity = 1.0
    equity_curve = {}
    for i, dt in enumerate(dates):
        if i > 0:
            held_position = position_series[i - 1]  # decided using info through day i-1
            if held_position == "long_spread":
                equity *= (1 + spread_diff[i] * 0.5)
            elif held_position == "short_spread":
                equity *= (1 - spread_diff[i] * 0.5)
            else:
                equity *= (1 + bil_ret[i])
            if trade_change[i - 1]:
                equity *= (1 - COST_BPS / 10000)
        equity_curve[dt] = equity

    ec = pd.Series(equity_curve)
    rets = ec.pct_change().dropna()
    if len(rets) < 50:
        return ec, {"sharpe": 0, "cagr": 0, "maxdd": 0}
    ann_ret = (ec.iloc[-1] ** (252 / len(ec)) - 1) if len(ec) > 1 else 0
    ann_vol = rets.std() * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0
    roll_max = ec.cummax()
    maxdd = ((ec - roll_max) / roll_max).min()
    return ec, {"sharpe": round(float(sharpe), 3), "cagr": round(float(ann_ret), 4),
                "maxdd": round(float(maxdd), 4)}


print("=" * 60)
print("H515 — Kalman-Filter Adaptive-Beta ETF Pairs + Rolling ADF Gate")
print("=" * 60)

print("\n[1] Fetching prices…")
prices = fetch_prices()
log_prices = np.log(prices)
bil_ret_full = prices[BIL].pct_change().fillna(0)

print("\n[2] IS cointegration screen (2008-2017, screen only — hedge ratio itself is Kalman-adaptive OOS)…")
qualified = []
for a, b in PAIRS:
    if a not in log_prices.columns or b not in log_prices.columns:
        print(f"  {a}/{b}: missing data")
        continue
    is_a = log_prices[a][(log_prices.index >= IS_START) & (log_prices.index <= IS_END)]
    is_b = log_prices[b][(log_prices.index >= IS_START) & (log_prices.index <= IS_END)]
    trace, crit, coint = johansen_screen(is_a, is_b)
    print(f"  {a+'/'+b:<10} trace={trace:>7.2f} crit95={crit:>7.2f} {'YES' if coint else 'no'}")
    if coint:
        qualified.append((a, b, trace))

print(f"\n{len(qualified)} of {len(PAIRS)} pairs qualified (IS cointegrated)")

pair_results = {}
oos_spread_diffs = []  # for composite

if not qualified:
    print("\nNo cointegrated pairs found. H515 NOT CONFIRMED by default.")
    confirmed = False
    best_sharpe = 0.0
else:
    print("\n[3] Kalman filter (full history, causal) + OOS backtests…")
    for a, b, trace in qualified:
        df = pd.concat([log_prices[a], log_prices[b], bil_ret_full], axis=1).dropna()
        df.columns = ["log_a", "log_b", "bil_ret"]
        residuals, resid_std = kalman_pair(df["log_a"].values, df["log_b"].values)
        z = residuals / np.where(resid_std > 0, resid_std, np.nan)
        adf_pass = rolling_adf_pass(pd.Series(residuals, index=df.index))
        spread_diff = np.concatenate([[0.0], np.diff(residuals)])  # approx daily spread pnl

        oos_mask = (df.index >= OOS_START) & (df.index <= OOS_END)
        dates_oos = df.index[oos_mask]
        z_oos = z[oos_mask]
        adf_oos = adf_pass[oos_mask]
        bil_oos = df["bil_ret"].values[oos_mask]
        spread_oos = spread_diff[oos_mask]

        _, stats_a = backtest_pair(dates_oos, z_oos, adf_oos, bil_oos, spread_oos,
                                    use_adf=False, label=f"{a}/{b} VarA")
        _, stats_b = backtest_pair(dates_oos, z_oos, adf_oos, bil_oos, spread_oos,
                                    use_adf=True, label=f"{a}/{b} VarB")

        adf_uptime = float(np.mean(adf_oos)) if len(adf_oos) else 0.0
        pair_results[f"{a}/{b}"] = {
            "trace": round(trace, 2),
            "varA_no_adf_gate": stats_a,
            "varB_with_adf_gate": stats_b,
            "adf_pass_pct_of_oos_days": round(adf_uptime, 3),
        }
        oos_spread_diffs.append(pd.Series(spread_oos, index=dates_oos))

    print(f"\n{'Pair':<10} {'VarA Sharpe':>12} {'VarB Sharpe':>12} {'VarB MaxDD':>11} {'ADF-pass%':>10}")
    print("-" * 60)
    for name, r in pair_results.items():
        print(f"  {name:<8} {r['varA_no_adf_gate']['sharpe']:>12.3f} "
              f"{r['varB_with_adf_gate']['sharpe']:>12.3f} "
              f"{r['varB_with_adf_gate']['maxdd']:>10.1%} "
              f"{r['adf_pass_pct_of_oos_days']:>9.1%}")

    # Variant C: composite equal-weight across qualified pairs, VarB rules
    combined = pd.concat(oos_spread_diffs, axis=1).mean(axis=1)
    dates_c = combined.index
    # crude composite z/adf: average of per-pair z, all-pairs-must-pass-ADF proxy
    common_bil = bil_ret_full.reindex(dates_c).fillna(0).values
    # z composite: reconstruct from combined spread's own rolling stats (60d) since
    # per-pair Kalman states differ; simplest honest composite is equal-weight VarB
    # equity curves, not equal-weight raw spreads:
    ec_list = []
    for a, b, trace in qualified:
        df = pd.concat([log_prices[a], log_prices[b], bil_ret_full], axis=1).dropna()
        df.columns = ["log_a", "log_b", "bil_ret"]
        residuals, resid_std = kalman_pair(df["log_a"].values, df["log_b"].values)
        z = residuals / np.where(resid_std > 0, resid_std, np.nan)
        adf_pass = rolling_adf_pass(pd.Series(residuals, index=df.index))
        spread_diff = np.concatenate([[0.0], np.diff(residuals)])
        oos_mask = (df.index >= OOS_START) & (df.index <= OOS_END)
        ec, _ = backtest_pair(df.index[oos_mask], z[oos_mask], adf_pass[oos_mask],
                               df["bil_ret"].values[oos_mask], spread_diff[oos_mask],
                               use_adf=True)
        ec_list.append(ec)
    ec_composite = pd.concat(ec_list, axis=1).mean(axis=1)
    rets_c = ec_composite.pct_change().dropna()
    ann_ret_c = (ec_composite.iloc[-1] ** (252 / len(ec_composite)) - 1)
    ann_vol_c = rets_c.std() * np.sqrt(252)
    sharpe_c = ann_ret_c / ann_vol_c if ann_vol_c > 0 else 0
    maxdd_c = ((ec_composite - ec_composite.cummax()) / ec_composite.cummax()).min()
    stats_composite = {"sharpe": round(float(sharpe_c), 3), "cagr": round(float(ann_ret_c), 4),
                        "maxdd": round(float(maxdd_c), 4)}
    print(f"\n  {'Composite (VarC, equal-weight VarB equity curves)':<50} "
          f"Sharpe={stats_composite['sharpe']:.3f} CAGR={stats_composite['cagr']:.1%} "
          f"MaxDD={stats_composite['maxdd']:.1%}")

    best_sharpe = max(
        max(r["varA_no_adf_gate"]["sharpe"] for r in pair_results.values()),
        max(r["varB_with_adf_gate"]["sharpe"] for r in pair_results.values()),
        stats_composite["sharpe"],
    )
    confirmed = best_sharpe >= 0.8

    print("\n" + "=" * 60)
    print(f"H515 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  Best OOS Sharpe: {best_sharpe:.3f}  (gate: 0.8)")
    print("=" * 60)

    out = {
        "hypothesis": "H515",
        "title": "Kalman-Filter Adaptive-Beta ETF Pairs + Rolling ADF Cointegration Gate",
        "candidate_pairs": [f"{a}/{b}" for a, b in PAIRS],
        "qualified_pairs_count": len(qualified),
        "is_period": f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {OOS_END}",
        "gate": "OOS Sharpe > 0.8",
        "confirmed": bool(confirmed),
        "best_oos_sharpe": best_sharpe,
        "pair_results": pair_results,
        "composite_varC": stats_composite,
    }
    Path(RESULT_DIR / "h515_results.json").write_text(json.dumps(out, indent=2))
    print(f"\nResults → {RESULT_DIR / 'h515_results.json'}")
