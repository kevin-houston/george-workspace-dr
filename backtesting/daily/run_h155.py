"""
H155 — TLT/IEF Kalman Filter Pairs Trading
===========================================

H154 found TLT/IEF has 30d half-life mean reversion but static OLS β=1.51 is too
rigid as duration sensitivities shift with the rate cycle (especially 2022).

Hypothesis: a time-varying Kalman hedge ratio adapts to the changing TLT/IEF
relationship and improves on H154's best OOS Sharpe of 0.514 (Variant A, z_lb=30d).

Kalman state-space model (local linear):
  Observation:  y_t = β_t * x_t + α_t + ε_t      ε ~ N(0, R)
  State:         β_t = β_{t-1} + η_t              η ~ N(0, Q_β)
  (Optional)     α_t = α_{t-1} + ζ_t              ζ ~ N(0, Q_α)

Q controls adaptation speed:
  - High Q/R → β adapts quickly (tracks recent relationship, noisy)
  - Low Q/R  → β adapts slowly (smooth but lags regime changes)

Variants:
  A: β-only KF, Q=1e-4, z_lb=30d  (baseline — most similar to static OLS)
  B: β-only KF, Q=1e-3, z_lb=30d  (faster adaptation)
  C: β-only KF, Q=1e-5, z_lb=30d  (slower adaptation)
  D: β+α KF,   Q=1e-4, z_lb=30d  (allow intercept to drift too)
  E: β-only KF, Q=1e-4, z_lb=60d  (compare with H154 Variant B)
  F: β-only KF, Q=5e-4, z_lb=30d  (intermediate adaptation)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.tsa.stattools import coint, adfuller
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

PAIR       = ("IEF", "TLT")   # X = IEF, Y = TLT
FULL_START = "2007-01-01"
FULL_END   = "2026-04-30"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

ENTRY_Z = 2.0
EXIT_Z  = 0.5
STOP_Z  = 4.0
COST_RT = 0.0005

_PREFIXES = [f"h{i:03d}" for i in range(62, 156)]


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h155_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def kalman_hedge(x_arr, y_arr, Q_beta, Q_alpha=0.0, R=1.0, with_alpha=False):
    """
    Online Kalman filter for time-varying hedge ratio.

    State vector: [β] or [β, α] depending on with_alpha.
    Returns arrays of filtered β, α (intercept), and innovation residuals.
    """
    n = len(x_arr)
    betas  = np.full(n, np.nan)
    alphas = np.full(n, np.nan)

    if with_alpha:
        # 2D state: [β, α]
        beta0  = 1.5     # TLT/IEF ratio init
        alpha0 = 0.0
        P = np.eye(2) * 10.0   # large init uncertainty
        Q = np.diag([Q_beta, Q_alpha])
        state = np.array([beta0, alpha0])

        for i in range(n):
            xi = x_arr[i]
            yi = y_arr[i]
            H  = np.array([[xi, 1.0]])      # observation vector
            # Predict
            P = P + Q
            # Innovation
            y_pred = H @ state
            innov  = yi - y_pred[0]
            S = H @ P @ H.T + R
            # Kalman gain
            K = (P @ H.T) / S[0, 0]
            # Update
            state = state + K.flatten() * innov
            P = (np.eye(2) - np.outer(K.flatten(), H)) @ P
            betas[i]  = state[0]
            alphas[i] = state[1]
    else:
        # 1D state: β only
        beta  = 1.5
        P     = 10.0
        for i in range(n):
            xi = x_arr[i]
            yi = y_arr[i]
            # Predict
            P_pred = P + Q_beta
            # Innovation
            innov = yi - beta * xi
            S = xi * xi * P_pred + R
            K = P_pred * xi / S
            # Update
            beta = beta + K * innov
            P    = (1.0 - K * xi) * P_pred
            betas[i]  = beta
            alphas[i] = 0.0

    return betas, alphas


def compute_kalman_spread(prices, Q_beta, Q_alpha=0.0, zscore_lb=30,
                           with_alpha=False, warmup=252):
    """
    Compute Kalman-filtered spread and z-score.
    warmup: first N observations used to init; spread NaN for warmup period.
    """
    x = prices["X"].values
    y = prices["Y"].values

    betas, alphas = kalman_hedge(x, y, Q_beta, Q_alpha,
                                  R=1.0, with_alpha=with_alpha)

    spread = y - betas * x - alphas

    # z-score: rolling mean/std of spread
    spread_s = pd.Series(spread, index=prices.index)
    z = (spread_s - spread_s.rolling(zscore_lb).mean()) / \
        spread_s.rolling(zscore_lb).std()

    # NaN out warmup period
    z.iloc[:warmup] = np.nan

    return pd.DataFrame({
        "X": prices["X"], "Y": prices["Y"],
        "beta": betas, "alpha": alphas,
        "spread": spread_s, "z_score": z
    }, index=prices.index)


def compute_halflife(spread):
    s = spread.dropna()
    lag  = s.shift(1).dropna()
    diff = s.diff().dropna()
    aln  = pd.concat([diff, lag], axis=1).dropna()
    aln.columns = ["diff", "lag"]
    if len(aln) < 30: return np.nan
    theta = float(OLS(aln["diff"], add_constant(aln["lag"])).fit().params["lag"])
    return np.log(2) / (-theta) if theta < 0 else np.nan


def generate_signals(z):
    pos = np.zeros(len(z)); cur = 0
    for i in range(1, len(z)):
        zv = z.iloc[i]
        if np.isnan(zv): pos[i] = 0; cur = 0; continue
        if cur == 0:
            if zv < -ENTRY_Z: cur = 1
            elif zv > ENTRY_Z: cur = -1
        elif cur == 1:
            if zv > -EXIT_Z or abs(zv) > STOP_Z: cur = 0
        elif cur == -1:
            if zv < EXIT_Z or abs(zv) > STOP_Z: cur = 0
        pos[i] = cur
    return pd.Series(pos, index=z.index)


def backtest_pair(spread_df, positions):
    x_ret = spread_df["X"].pct_change()
    y_ret = spread_df["Y"].pct_change()
    spread_ret  = y_ret - spread_df["beta"].shift(1) * x_ret
    cost_series = (positions != positions.shift(1).fillna(0)).astype(float) * COST_RT
    return (positions.shift(1) * spread_ret - cost_series).fillna(0)


def stats_daily(r):
    r  = r.dropna()
    eq = (1 + r).cumprod()
    cagr    = float(eq.iloc[-1]) ** (252 / len(r)) - 1
    vol     = r.std(ddof=1) * np.sqrt(252)
    sharpe  = cagr / vol if vol > 0 else 0.0
    max_dd  = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cumul": float(eq.iloc[-1]), "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "max_dd": max_dd, "neg_yrs": neg_yrs}


def run_variant(prices, spy, Q_beta, zscore_lb, label, with_alpha=False, Q_alpha=0.0):
    spread_df = compute_kalman_spread(prices, Q_beta, Q_alpha=Q_alpha,
                                       zscore_lb=zscore_lb, with_alpha=with_alpha)
    hl_oos = compute_halflife(spread_df.loc[spread_df.index >= OOS_START, "spread"])
    pos    = generate_signals(spread_df["z_score"])
    strat  = backtest_pair(spread_df, pos)

    s_oos = stats_daily(strat[strat.index >= OOS_START])
    s_alt = stats_daily(strat[strat.index >= ALT_OOS_ST])
    s_is  = stats_daily(strat[(strat.index >= ALT_OOS_ST) & (strat.index <= IS_END)])
    s_spy = stats_daily(spy.pct_change().dropna().loc[lambda x: x.index >= OOS_START])

    pos_oos = pos[pos.index >= OOS_START]
    total   = len(pos_oos)
    n_long  = int((pos_oos == 1).sum())
    n_short = int((pos_oos == -1).sum())

    # Beta stats in OOS
    b_oos   = spread_df.loc[spread_df.index >= OOS_START, "beta"]
    b_mean  = b_oos.mean()
    b_std   = b_oos.std()

    print(f"\n  Variant {label}")
    print(f"    Q_beta={Q_beta:.0e}  z_lb={zscore_lb}d  alpha={'yes' if with_alpha else 'no'}")
    print(f"    OOS β: mean={b_mean:.4f}  std={b_std:.4f}  HL_spread={hl_oos:.1f}d")
    print(f"    OOS position: long={n_long/total*100:.1f}%  short={n_short/total*100:.1f}%  "
          f"flat={(total-n_long-n_short)/total*100:.1f}%")
    print(f"    IS: cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}  MaxDD={s_is['max_dd']:.2%}")
    print(f"    OOS: cumul={s_oos['cumul']:.4f}  CAGR={s_oos['cagr']:.2%}  "
          f"Sharpe={s_oos['sharpe']:.3f}  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
    print(f"    AltOOS: cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
    print(f"    SPY OOS: cumul={s_spy['cumul']:.4f}  Sharpe={s_spy['sharpe']:.3f}")

    return s_oos, s_alt, s_is, s_spy


def main():
    xt, yt = PAIR
    print(f"\nH155 — Kalman Filter Pairs Trading: {xt}/{yt}")
    print("=" * 60)

    print(f"\n[1] Loading price data…")
    px  = fetch_daily_close(xt, FULL_START, FULL_END)
    py  = fetch_daily_close(yt, FULL_START, FULL_END)
    spy = fetch_daily_close("SPY", FULL_START, FULL_END)
    prices = pd.concat([px, py], axis=1).dropna()
    prices.columns = ["X", "Y"]
    print(f"    {len(prices)} days  ({prices.index[0].date()} → {prices.index[-1].date()})")

    print(f"\n[2] H154 reference (static OLS Variant A, z_lb=30d):")
    print(f"    OOS Sharpe=0.514  cumul=1.226  MaxDD=-7.18%  (benchmark to beat)")

    print(f"\n[3] Kalman variants…")

    variants = [
        # label,  Q_beta, z_lb, with_alpha, Q_alpha
        ("A (Q=1e-4, z30)",  1e-4, 30, False, 0.0),
        ("B (Q=1e-3, z30)",  1e-3, 30, False, 0.0),
        ("C (Q=1e-5, z30)",  1e-5, 30, False, 0.0),
        ("D (Q=1e-4, z30, +α)", 1e-4, 30, True, 1e-4),
        ("E (Q=1e-4, z60)",  1e-4, 60, False, 0.0),
        ("F (Q=5e-4, z30)",  5e-4, 30, False, 0.0),
    ]

    results = {}
    for label, Q, zlb, wa, Qa in variants:
        s_oos, s_alt, s_is, s_spy = run_variant(prices, spy, Q, zlb, label,
                                                  with_alpha=wa, Q_alpha=Qa)
        results[label] = (s_oos, s_alt, s_is, s_spy)

    print(f"\n[4] Verdict:")
    spy_s = results[list(results.keys())[0]][3]   # same SPY for all
    h154_sharpe = 0.514   # H154 Variant A benchmark

    verdicts = {}
    for label, (s_oos, s_alt, s_is, _) in results.items():
        checks = [
            s_oos["sharpe"] > 1.0,
            s_oos["cumul"]  > spy_s["cumul"],
            s_oos["max_dd"] > -0.25,
            s_oos["sharpe"] > h154_sharpe,   # beats H154
        ]
        n = sum(checks)
        v = "CONFIRMED" if n >= 3 else "PARTIAL" if n >= 2 else "NOT CONFIRMED"
        verdicts[label] = (v, n, s_oos)
        print(f"    {label}: {v} ({n}/4)  Sharpe={s_oos['sharpe']:.3f}  "
              f"cumul={s_oos['cumul']:.4f}  MaxDD={s_oos['max_dd']:.2%}")

    best = max(verdicts.items(), key=lambda kv: kv[1][2]["sharpe"])
    best_label = best[0]; best_v = best[1][0]; best_s = best[1][2]
    overall = "CONFIRMED" if best_v == "CONFIRMED" else \
              ("PARTIAL" if best_v == "PARTIAL" else "NOT CONFIRMED")

    print(f"\n  H155 overall: {overall}  (best: {best_label})")
    print(f"  Best OOS: Sharpe={best_s['sharpe']:.3f}  cumul={best_s['cumul']:.4f}  "
          f"MaxDD={best_s['max_dd']:.2%}  vs H154 Sharpe=0.514")
    print(f"  SPY OOS: Sharpe={spy_s['sharpe']:.3f}  cumul={spy_s['cumul']:.4f}")

    # Write results
    lines = [
        f"H155 — {xt}/{yt} Kalman Filter Pairs Trading", "=" * 60, "",
        f"Data: {prices.index[0].date()} → {prices.index[-1].date()}",
        f"H154 benchmark: OOS Sharpe=0.514  cumul=1.226  MaxDD=-7.18%",
        f"SPY OOS: cumul={spy_s['cumul']:.4f}  Sharpe={spy_s['sharpe']:.3f}", "",
        "VARIANTS",
    ]
    for label, (s_oos, s_alt, s_is, _) in results.items():
        lines.append(
            f"  {label}: OOS cumul={s_oos['cumul']:.4f} CAGR={s_oos['cagr']:.2%} "
            f"Sharpe={s_oos['sharpe']:.3f} MaxDD={s_oos['max_dd']:.2%} NegYrs={s_oos['neg_yrs']}"
        )
    lines += ["", f"VERDICT: {overall}  (best: {best_label})",
              f"Best OOS Sharpe={best_s['sharpe']:.3f}  cumul={best_s['cumul']:.4f}"]
    (RESULT_DIR / "h155_tlt_ief_kalman.txt").write_text("\n".join(lines))
    return overall, best_s, spy_s


if __name__ == "__main__":
    main()
