"""
H516 — Kalman-Filter Adaptive-Beta ETF Pairs, Rolling-Percentile Entry
Threshold (fix for H515's degenerate-signal finding) (§3.8, 151 Strategies)
============================================================================

Hypothesis:
  H515 (Kalman-adaptive hedge ratio + rolling ADF gate) found that its FIXED
  ENTRY_Z=1.5 threshold almost never fires for 2 of 3 IS-qualified pairs
  (XLF/KBE: 0.00% of OOS days above threshold; LQD/HYG: 0.05%) because the
  Kalman filter's online-adapted observation-noise estimate shrinks the
  innovation z-score scale over time for tightly-cointegrated pairs. The
  reported "CONFIRMED" Sharpe (10.377) for those two pairs was a spurious
  artifact of the strategy staying 100% parked in BIL cash — it matched
  standalone BIL's own OOS Sharpe (10.385) almost exactly.

  H516 tests whether a ROLLING-PERCENTILE entry/exit threshold (recalibrated
  to each pair's own trailing z-score distribution, causal, 252-day window)
  gives XLF/KBE and LQD/HYG a fair chance to trade, instead of a fixed
  absolute level miscalibrated to the Kalman filter's shrinking noise scale.

  Method: identical Kalman filter + rolling ADF gate as H515. Only the
  entry/exit rule changes:
    - pos_entry[i] = 90th percentile of z[i-252:i] (causal, inclusive of day i)
    - neg_entry[i] = 10th percentile of z[i-252:i]
    - pos_exit[i]  = 60th percentile of z[i-252:i]
    - neg_exit[i]  = 40th percentile of z[i-252:i]
  Enter long_spread when z < neg_entry, short_spread when z > pos_entry.
  Exit long_spread when z > neg_exit, short_spread when z < pos_exit.
  Same causal two-pass decide/credit design H515 was corrected to use.

  Gate: OOS Sharpe > 0.8 (same as H307/H515)
  IS:  2008-01-01 to 2017-12-31 (Johansen screen only, reused from H515 —
       same 3 pairs qualify: GDX/SIL, LQD/HYG, XLF/KBE)
  OOS: 2018-01-01 to 2026-06-13
"""

import json, warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from statsmodels.tsa.stattools import adfuller

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

QUALIFIED_PAIRS = [("GDX", "SIL", 15.68), ("LQD", "HYG", 27.51), ("XLF", "KBE", 23.69)]

BIL         = "BIL"
FULL_START  = "2006-01-01"
OOS_START   = "2018-01-01"
OOS_END     = "2026-06-13"
COST_BPS    = 15
PCTILE_WIN  = 252
ENTRY_PCTILE = 0.90   # and its mirror 1-0.90 = 0.10
EXIT_PCTILE  = 0.60   # and its mirror 1-0.60 = 0.40
ADF_WINDOW  = 252
ADF_P       = 0.10
DELTA       = 1e-4


def fetch_prices():
    all_t = sorted(set(t for a, b, _ in QUALIFIED_PAIRS for t in (a, b)) | {BIL})
    raw = yf.download(all_t, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def kalman_pair(log_a, log_b):
    n = len(log_a)
    x = np.zeros(2)
    P = np.eye(2) * 1.0
    Vw = DELTA / (1 - DELTA) * np.eye(2)
    Ve = 1e-3
    residuals = np.full(n, np.nan)
    resid_std = np.full(n, np.nan)
    for t in range(n):
        a_t, b_t = log_a[t], log_b[t]
        if not (np.isfinite(a_t) and np.isfinite(b_t)):
            continue
        H = np.array([1.0, b_t])
        R = P + Vw
        y_hat = H @ x
        e = a_t - y_hat
        Q = H @ R @ H.T + Ve
        residuals[t] = e
        resid_std[t] = np.sqrt(max(Q, 1e-12))
        K = (R @ H) / Q
        x = x + K * e
        P = R - np.outer(K, H) @ R
        Ve = 0.98 * Ve + 0.02 * (e ** 2)
    return residuals, resid_std


def rolling_adf_pass(residuals_series):
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


def backtest_pair_pctile(dates, z, adf_pass, bil_ret, spread_diff,
                          pos_entry, neg_entry, pos_exit, neg_exit, use_adf):
    """Causal two-pass design, same as H515's corrected backtest_pair, but
    entry/exit levels are per-day rolling-percentile arrays instead of a
    fixed ENTRY_Z/EXIT_Z."""
    n = len(dates)
    in_trade = None
    position_series = [None] * n
    trade_change = [False] * n

    for i in range(n):
        z_val = z[i]
        gated_flat = use_adf and not adf_pass[i]
        prev_trade = in_trade
        has_thresh = np.isfinite(pos_entry[i]) and np.isfinite(neg_entry[i])

        if pd.isna(z_val) or gated_flat or not has_thresh:
            in_trade = None
        elif in_trade is None:
            if z_val < neg_entry[i]:
                in_trade = "long_spread"
            elif z_val > pos_entry[i]:
                in_trade = "short_spread"
        elif in_trade == "long_spread" and z_val > neg_exit[i]:
            in_trade = None
        elif in_trade == "short_spread" and z_val < pos_exit[i]:
            in_trade = None

        position_series[i] = in_trade
        trade_change[i] = (in_trade != prev_trade)

    equity = 1.0
    equity_curve = {}
    for i, dt in enumerate(dates):
        if i > 0:
            held_position = position_series[i - 1]
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
        return ec, {"sharpe": 0, "cagr": 0, "maxdd": 0}, 0.0
    ann_ret = (ec.iloc[-1] ** (252 / len(ec)) - 1) if len(ec) > 1 else 0
    ann_vol = rets.std() * np.sqrt(252)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0
    roll_max = ec.cummax()
    maxdd = ((ec - roll_max) / roll_max).min()
    trade_frac = float(np.mean([p is not None for p in position_series]))
    return ec, {"sharpe": round(float(sharpe), 3), "cagr": round(float(ann_ret), 4),
                "maxdd": round(float(maxdd), 4)}, trade_frac


print("=" * 60)
print("H516 — Kalman Pairs, Rolling-Percentile Entry Threshold")
print("=" * 60)

print("\n[1] Fetching prices…")
prices = fetch_prices()
log_prices = np.log(prices)
bil_ret_full = prices[BIL].pct_change().fillna(0)

pair_results = {}
ec_list = []

print("\n[2] Kalman filter + rolling-percentile thresholds + OOS backtests…")
for a, b, trace in QUALIFIED_PAIRS:
    df = pd.concat([log_prices[a], log_prices[b], bil_ret_full], axis=1).dropna()
    df.columns = ["log_a", "log_b", "bil_ret"]
    residuals, resid_std = kalman_pair(df["log_a"].values, df["log_b"].values)
    z_full = residuals / np.where(resid_std > 0, resid_std, np.nan)
    z_series = pd.Series(z_full, index=df.index)

    pos_entry = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(ENTRY_PCTILE).values
    neg_entry = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(1 - ENTRY_PCTILE).values
    pos_exit  = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(EXIT_PCTILE).values
    neg_exit  = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(1 - EXIT_PCTILE).values

    adf_pass = rolling_adf_pass(pd.Series(residuals, index=df.index))
    spread_diff = np.concatenate([[0.0], np.diff(residuals)])

    oos_mask = (df.index >= OOS_START) & (df.index <= OOS_END)
    dates_oos = df.index[oos_mask]

    _, stats_a, tf_a = backtest_pair_pctile(
        dates_oos, z_full[oos_mask], adf_pass[oos_mask], df["bil_ret"].values[oos_mask],
        spread_diff[oos_mask], pos_entry[oos_mask], neg_entry[oos_mask],
        pos_exit[oos_mask], neg_exit[oos_mask], use_adf=False)
    ec_b, stats_b, tf_b = backtest_pair_pctile(
        dates_oos, z_full[oos_mask], adf_pass[oos_mask], df["bil_ret"].values[oos_mask],
        spread_diff[oos_mask], pos_entry[oos_mask], neg_entry[oos_mask],
        pos_exit[oos_mask], neg_exit[oos_mask], use_adf=True)

    pair_results[f"{a}/{b}"] = {
        "trace": trace,
        "varA_no_adf_gate": stats_a, "varA_trade_frac_of_oos_days": round(tf_a, 3),
        "varB_with_adf_gate": stats_b, "varB_trade_frac_of_oos_days": round(tf_b, 3),
    }
    ec_list.append(ec_b)
    print(f"  {a}/{b:<5} VarA Sharpe={stats_a['sharpe']:>7.3f} (trade_frac={tf_a:.1%})  "
          f"VarB Sharpe={stats_b['sharpe']:>7.3f} (trade_frac={tf_b:.1%})  MaxDD(B)={stats_b['maxdd']:.1%}")

ec_composite = pd.concat(ec_list, axis=1).mean(axis=1)
rets_c = ec_composite.pct_change().dropna()
ann_ret_c = (ec_composite.iloc[-1] ** (252 / len(ec_composite)) - 1)
ann_vol_c = rets_c.std() * np.sqrt(252)
sharpe_c = ann_ret_c / ann_vol_c if ann_vol_c > 0 else 0
maxdd_c = ((ec_composite - ec_composite.cummax()) / ec_composite.cummax()).min()
stats_composite = {"sharpe": round(float(sharpe_c), 3), "cagr": round(float(ann_ret_c), 4),
                    "maxdd": round(float(maxdd_c), 4)}
print(f"\n  Composite (VarC, equal-weight VarB equity curves): Sharpe={stats_composite['sharpe']:.3f} "
      f"CAGR={stats_composite['cagr']:.1%} MaxDD={stats_composite['maxdd']:.1%}")

# BIL standalone Sharpe over same OOS window, as a degeneracy check
bil_oos = bil_ret_full[(bil_ret_full.index >= OOS_START) & (bil_ret_full.index <= OOS_END)]
bil_ann_ret = (1 + bil_oos).prod() ** (252 / len(bil_oos)) - 1
bil_ann_vol = bil_oos.std() * np.sqrt(252)
bil_sharpe = bil_ann_ret / bil_ann_vol if bil_ann_vol > 0 else 0
print(f"  [degeneracy check] BIL standalone OOS Sharpe: {bil_sharpe:.3f}")

best_sharpe = max(
    max(r["varA_no_adf_gate"]["sharpe"] for r in pair_results.values()),
    max(r["varB_with_adf_gate"]["sharpe"] for r in pair_results.values()),
    stats_composite["sharpe"],
)
# Degeneracy check: flag any result within 0.5 of the BIL cash-parking Sharpe
# with low trade frequency as suspect, do not count it toward confirmation.
non_degenerate_sharpes = []
for name, r in pair_results.items():
    for var_key, tf_key in [("varA_no_adf_gate", "varA_trade_frac_of_oos_days"),
                             ("varB_with_adf_gate", "varB_trade_frac_of_oos_days")]:
        if r[tf_key] > 0.02 and abs(r[var_key]["sharpe"] - bil_sharpe) > 0.5:
            non_degenerate_sharpes.append(r[var_key]["sharpe"])
best_non_degenerate = max(non_degenerate_sharpes) if non_degenerate_sharpes else 0.0
confirmed = best_non_degenerate >= 0.8

print("\n" + "=" * 60)
print(f"H516 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'} (degeneracy-filtered)")
print(f"  Best raw OOS Sharpe: {best_sharpe:.3f}  |  Best non-degenerate OOS Sharpe: {best_non_degenerate:.3f}  (gate: 0.8)")
print("=" * 60)

out = {
    "hypothesis": "H516",
    "title": "Kalman-Filter Adaptive-Beta ETF Pairs, Rolling-Percentile Entry Threshold",
    "qualified_pairs": [f"{a}/{b}" for a, b, _ in QUALIFIED_PAIRS],
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": "OOS Sharpe > 0.8 (degeneracy-filtered: trade_frac>2% AND |sharpe-BIL_sharpe|>0.5)",
    "bil_standalone_oos_sharpe": round(float(bil_sharpe), 3),
    "confirmed": bool(confirmed),
    "best_raw_oos_sharpe": best_sharpe,
    "best_non_degenerate_oos_sharpe": best_non_degenerate,
    "pair_results": pair_results,
    "composite_varC": stats_composite,
}
Path(RESULT_DIR / "h516_results.json").write_text(json.dumps(out, indent=2))
print(f"\nResults → {RESULT_DIR / 'h516_results.json'}")
