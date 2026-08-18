"""
H518 — Kalman Pairs, True Leg-Level Dollar P&L Rebuild (fix for H516's
P&L-proxy caveat) (§3.8, 151 Strategies)
============================================================================

Hypothesis:
  H516 fixed H515's degenerate fixed-threshold problem with a rolling-
  percentile entry/exit rule (90th/10th percentile entry, 60th/40th exit,
  252-day rolling window) — all 3 Johansen-qualified pairs (GDX/SIL,
  LQD/HYG, XLF/KBE) now trade 24-25% of OOS days with reported OOS Sharpe
  4.6-6.2 and MaxDD < 2.5%. But H516's P&L was a *proxy*: the day-over-day
  change in the Kalman filter's own residual (model fit error), scaled by
  an arbitrary 0.5x notional factor — not a real dollar-neutral pairs P&L.

  H518 rebuilds the P&L on true leg-level dollar terms: at each rebalance
  point, go long $1 notional of leg A and short beta_t dollars of leg B
  (dollar-neutral pairs sizing using the Kalman filter's own online-adapted
  beta_t as the hedge ratio), mark both legs to market using ACTUAL price
  changes (not the abstract Kalman residual delta), and let position value
  drift with beta_t re-hedged only when a new trade opens (not continuously
  rebalanced within a held trade, which would be unrealistic turnover).

  Entry/exit rule is UNCHANGED from H516 (already validated as the correct
  fix for H515's degeneracy) — rolling 90th/10th percentile entry, 60th/40th
  percentile exit, 252-day window, same causal two-pass decide/credit design.

  Gate: OOS Sharpe > 0.8 (same as H307/H515/H516), degeneracy-filtered
        (trade_frac > 2% AND |Sharpe - BIL_Sharpe| > 0.5)
  IS:  2008-01-01 to 2017-12-31 (Johansen screen reused from H515, unchanged)
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
ENTRY_PCTILE = 0.90
EXIT_PCTILE  = 0.60
ADF_WINDOW  = 252
ADF_P       = 0.10
DELTA       = 1e-4


def fetch_prices():
    all_t = sorted(set(t for a, b, _ in QUALIFIED_PAIRS for t in (a, b)) | {BIL})
    raw = yf.download(all_t, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def kalman_pair(log_a, log_b):
    """Same causal 2-state Kalman filter as H515/H516. Now also returns the
    online-adapted beta_t series (x[1] each step) needed for leg sizing."""
    n = len(log_a)
    x = np.zeros(2)
    P = np.eye(2) * 1.0
    Vw = DELTA / (1 - DELTA) * np.eye(2)
    Ve = 1e-3
    residuals = np.full(n, np.nan)
    resid_std = np.full(n, np.nan)
    beta_series = np.full(n, np.nan)
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
        beta_series[t] = x[1]
    return residuals, resid_std, beta_series


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


def backtest_pair_dollar(dates, z, adf_pass, bil_ret, price_a, price_b, beta_t,
                          pos_entry, neg_entry, pos_exit, neg_exit, use_adf):
    """
    True leg-level dollar-neutral pairs P&L.

    Position sizing at trade OPEN (not re-hedged intra-trade — realistic,
    since continuous re-hedging would imply unrealistic daily turnover):
      long_spread  (spread cheap, expect a_t to rise vs b_t): long $1 of A,
        short beta_t dollars of B (beta_t clipped to [0.1, 10] to avoid
        degenerate hedge ratios blowing up notional).
      short_spread (spread rich): short $1 of A, long beta_t dollars of B.

    Daily P&L on a held position = long_leg_shares * d(price) - ... expressed
    as dollar P&L on the ORIGINAL notional (marked to market daily using
    actual price returns of each leg, not the Kalman residual):
      pnl_$ = sign_A * 1.0 * ret_A[i] + sign_B * beta_open * ret_B[i]
    where ret_A/ret_B are simple daily returns on the actual (non-log) prices.
    Return on capital is pnl_$ / (1 + beta_open) — the total dollar notional
    deployed across both legs (long $1 + short $beta_open, capital basis).
    """
    n = len(dates)
    in_trade = None
    position_series = [None] * n
    trade_change = [False] * n
    beta_open_series = [np.nan] * n

    beta_at_open = np.nan
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
                beta_at_open = float(np.clip(beta_t[i], 0.1, 10.0)) if np.isfinite(beta_t[i]) else 1.0
            elif z_val > pos_entry[i]:
                in_trade = "short_spread"
                beta_at_open = float(np.clip(beta_t[i], 0.1, 10.0)) if np.isfinite(beta_t[i]) else 1.0
        elif in_trade == "long_spread" and z_val > neg_exit[i]:
            in_trade = None
        elif in_trade == "short_spread" and z_val < pos_exit[i]:
            in_trade = None

        position_series[i] = in_trade
        beta_open_series[i] = beta_at_open if in_trade is not None else np.nan
        trade_change[i] = (in_trade != prev_trade)

    ret_a = price_a.pct_change().fillna(0.0).values
    ret_b = price_b.pct_change().fillna(0.0).values

    equity = 1.0
    equity_curve = {}
    for i, dt in enumerate(dates):
        if i > 0:
            held_position = position_series[i - 1]
            beta_open = beta_open_series[i - 1]
            if held_position == "long_spread" and np.isfinite(beta_open):
                # long $1 leg A, short $beta_open leg B
                pnl_dollars = 1.0 * ret_a[i] - beta_open * ret_b[i]
                capital = 1.0 + beta_open
                equity *= (1 + pnl_dollars / capital)
            elif held_position == "short_spread" and np.isfinite(beta_open):
                # short $1 leg A, long $beta_open leg B
                pnl_dollars = -1.0 * ret_a[i] + beta_open * ret_b[i]
                capital = 1.0 + beta_open
                equity *= (1 + pnl_dollars / capital)
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
print("H518 — Kalman Pairs, True Leg-Level Dollar P&L Rebuild")
print("=" * 60)

print("\n[1] Fetching prices…")
prices = fetch_prices()
log_prices = np.log(prices)
bil_ret_full = prices[BIL].pct_change().fillna(0)

pair_results = {}
ec_list = []

print("\n[2] Kalman filter + rolling-percentile thresholds + dollar-P&L OOS backtests…")
for a, b, trace in QUALIFIED_PAIRS:
    df = pd.concat([log_prices[a], log_prices[b], prices[a], prices[b], bil_ret_full], axis=1).dropna()
    df.columns = ["log_a", "log_b", "price_a", "price_b", "bil_ret"]
    residuals, resid_std, beta_series = kalman_pair(df["log_a"].values, df["log_b"].values)
    z_full = residuals / np.where(resid_std > 0, resid_std, np.nan)
    z_series = pd.Series(z_full, index=df.index)

    pos_entry = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(ENTRY_PCTILE).values
    neg_entry = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(1 - ENTRY_PCTILE).values
    pos_exit  = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(EXIT_PCTILE).values
    neg_exit  = z_series.rolling(PCTILE_WIN, min_periods=PCTILE_WIN).quantile(1 - EXIT_PCTILE).values

    adf_pass = rolling_adf_pass(pd.Series(residuals, index=df.index))

    oos_mask = (df.index >= OOS_START) & (df.index <= OOS_END)
    dates_oos = df.index[oos_mask]

    _, stats_a, tf_a = backtest_pair_dollar(
        dates_oos, z_full[oos_mask], adf_pass[oos_mask], df["bil_ret"].values[oos_mask],
        df["price_a"][oos_mask], df["price_b"][oos_mask], beta_series[oos_mask],
        pos_entry[oos_mask], neg_entry[oos_mask], pos_exit[oos_mask], neg_exit[oos_mask], use_adf=False)
    ec_b, stats_b, tf_b = backtest_pair_dollar(
        dates_oos, z_full[oos_mask], adf_pass[oos_mask], df["bil_ret"].values[oos_mask],
        df["price_a"][oos_mask], df["price_b"][oos_mask], beta_series[oos_mask],
        pos_entry[oos_mask], neg_entry[oos_mask], pos_exit[oos_mask], neg_exit[oos_mask], use_adf=True)

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
non_degenerate_sharpes = []
for name, r in pair_results.items():
    for var_key, tf_key in [("varA_no_adf_gate", "varA_trade_frac_of_oos_days"),
                             ("varB_with_adf_gate", "varB_trade_frac_of_oos_days")]:
        if r[tf_key] > 0.02 and abs(r[var_key]["sharpe"] - bil_sharpe) > 0.5:
            non_degenerate_sharpes.append(r[var_key]["sharpe"])
best_non_degenerate = max(non_degenerate_sharpes) if non_degenerate_sharpes else 0.0
confirmed = best_non_degenerate >= 0.8

print("\n" + "=" * 60)
print(f"H518 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'} (degeneracy-filtered, true dollar P&L)")
print(f"  Best raw OOS Sharpe: {best_sharpe:.3f}  |  Best non-degenerate OOS Sharpe: {best_non_degenerate:.3f}  (gate: 0.8)")
print("=" * 60)

out = {
    "hypothesis": "H518",
    "title": "Kalman Pairs, True Leg-Level Dollar P&L Rebuild",
    "qualified_pairs": [f"{a}/{b}" for a, b, _ in QUALIFIED_PAIRS],
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": "OOS Sharpe > 0.8 (degeneracy-filtered: trade_frac>2% AND |sharpe-BIL_sharpe|>0.5)",
    "bil_standalone_oos_sharpe": round(float(bil_sharpe), 3),
    "confirmed": bool(confirmed),
    "best_raw_oos_sharpe": best_sharpe,
    "best_non_degenerate_oos_sharpe": best_non_degenerate,
    "pair_results": pair_results,
    "composite_varC": stats_composite,
    "methodology_note": "P&L is now true leg-level dollar terms: long $1 leg A vs short beta_t $ leg B "
                         "(or inverse for short_spread), beta_t = Kalman filter's own online-adapted hedge "
                         "ratio at trade open (clipped [0.1,10]), marked to market using actual daily price "
                         "returns of both legs (not the H516 Kalman-residual-delta proxy). Beta fixed at "
                         "trade-open value for the life of the trade (no intra-trade re-hedging).",
}
Path(RESULT_DIR / "h518_results.json").write_text(json.dumps(out, indent=2))
print(f"\nResults → {RESULT_DIR / 'h518_results.json'}")
