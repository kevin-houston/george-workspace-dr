"""
H251 — 3-State HMM Regime Detection for SPY/TLT/GLD Tactical Allocation
=========================================================================
Source: arXiv:2605.27848 (Verma, Putri & Lesupi, May 2026)
  'Regime-Based Portfolio Allocation Using Hidden Markov Models and RL'
  3-state Gaussian HMM (low-vol, transitional, high-vol) on SPY/TLT/GLD.
  RL-enhanced HMM outperforms rule-based; strong Sharpe vs SPY benchmark.

Baseline: SPY buy-and-hold (~Sharpe 0.5, MaxDD -50%+ in 2008/2020/2022)
H026 comparison: our ETF rotation (sector momentum top-1) OOS Sharpe ~1.5
H251 target: OOS Sharpe > 0.8, MaxDD < 30%

Implementation:
  Universe: SPY, TLT, GLD daily returns
  HMM: hmmlearn GaussianHMM, n_components=3, covariance_type="full", n_iter=300
  Features: [daily_return, rolling_21d_vol, rolling_21d_return]
  State labels (post-hoc, by vol level):
    State 0 = low-volatility (stable bull)
    State 1 = transitional (regime shift)
    State 2 = high-volatility (bear/stress)
  Allocation rules (monthly rebalance on state at prior month-end):
    State 0 (low-vol):    SPY=80%, TLT=10%, GLD=10%
    State 1 (transition): SPY=50%, TLT=30%, GLD=20%
    State 2 (high-vol):   SPY=20%, TLT=50%, GLD=30%

IS: 2004-2017  OOS: 2018-2025 (70/30 split as in paper)
Transaction costs: 10bp per rebalance
Confirm: OOS Sharpe > 0.8

Note: for OOS deployment, retrain HMM annually on expanding window.
      Use predict() not decode() (forward-only, no look-ahead).
Note: if H251 confirms, evaluate correlation vs H026/H041a for production blend.
"""

import warnings; warnings.filterwarnings("ignore")
import json
import os
import sys
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

# Install hmmlearn if needed
try:
    from hmmlearn import hmm as hmmlib
except ImportError:
    print("Installing hmmlearn...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "hmmlearn", "-q"], check=True)
    from hmmlearn import hmm as hmmlib

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"   # warmup for features
FULL_END   = "2026-01-01"
IS_START   = "2004-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
OOS_END    = "2025-12-31"

UNIVERSE = ["SPY", "TLT", "GLD"]

# Allocation per regime state (will be relabeled by vol after fitting)
# Keys: 0=low-vol, 1=transition, 2=high-vol
ALLOC = {
    "low_vol":    {"SPY": 0.80, "TLT": 0.10, "GLD": 0.10},
    "transition": {"SPY": 0.50, "TLT": 0.30, "GLD": 0.20},
    "high_vol":   {"SPY": 0.20, "TLT": 0.50, "GLD": 0.30},
}

TXCOST = 0.0010   # 10bp per rebalance per asset


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_prices():
    cache_path = CACHE_DIR / f"h251_prices_{FULL_START}_{FULL_END}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    print("  Downloading SPY, TLT, GLD...")
    raw = yf.download(UNIVERSE, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"][UNIVERSE]
    else:
        closes = raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cache_path)
    return closes


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def build_features(prices):
    """
    Build feature matrix: for each asset [log_return, rolling_21d_vol, rolling_21d_return]
    → 9 features total. Rows where any feature is NaN are dropped.
    """
    feats = {}
    for t in UNIVERSE:
        log_ret = np.log(prices[t] / prices[t].shift(1))
        vol21   = log_ret.rolling(21).std() * np.sqrt(252)
        ret21   = prices[t].pct_change(21)
        feats[f"{t}_logret"] = log_ret
        feats[f"{t}_vol21"]  = vol21
        feats[f"{t}_ret21"]  = ret21

    df = pd.DataFrame(feats, index=prices.index).dropna()
    return df


# ─────────────────────────────────────────────────────────────────────────────
# HMM fitting and state labeling
# ─────────────────────────────────────────────────────────────────────────────

def fit_hmm(X_is):
    """
    Fit a 3-state GaussianHMM on IS feature matrix.
    Returns trained model.
    """
    model = hmmlib.GaussianHMM(
        n_components=3,
        covariance_type="full",
        n_iter=300,
        random_state=42,
    )
    model.fit(X_is)
    return model


def label_states(model, X_is, feature_names):
    """
    Assign semantic labels to HMM states based on mean volatility of each state.
    SPY_vol21 feature used (index 1 = 'SPY_vol21').
    Returns dict: {original_state_int: 'low_vol'|'transition'|'high_vol'}
    """
    states_is = model.predict(X_is)

    # Find index of SPY_vol21 in feature matrix
    spy_vol_idx = feature_names.index("SPY_vol21")
    means = model.means_  # shape (n_states, n_features)

    state_vols = {s: means[s, spy_vol_idx] for s in range(3)}
    sorted_states = sorted(state_vols, key=state_vols.get)  # ascending vol

    # sorted_states[0] = lowest vol → 'low_vol'
    # sorted_states[1] = mid vol   → 'transition'
    # sorted_states[2] = highest   → 'high_vol'
    label_map = {
        sorted_states[0]: "low_vol",
        sorted_states[1]: "transition",
        sorted_states[2]: "high_vol",
    }
    return label_map


# ─────────────────────────────────────────────────────────────────────────────
# Backtest
# ─────────────────────────────────────────────────────────────────────────────

def backtest_hmm(model, label_map, feat_df, prices, oos_start, oos_end):
    """
    OOS backtest:
      - Monthly rebalance (end of month signals)
      - State predicted at prior month-end using model.predict() (no lookahead)
      - Allocation applied for next calendar month
      - 10bp transaction cost per rebalance

    Returns (monthly_returns Series, state_series Series, spy_monthly_returns Series)
    """
    # Monthly prices and returns
    prices_m = prices.resample("ME").last()
    ret_m    = prices_m.pct_change()

    # Monthly features (last day of each month)
    feat_m   = feat_df.resample("ME").last()

    oos_start_ts = pd.Timestamp(oos_start)
    oos_end_ts   = pd.Timestamp(oos_end)

    oos_months = prices_m.index[
        (prices_m.index >= oos_start_ts) &
        (prices_m.index <= oos_end_ts)
    ]

    port_rets  = []
    state_hist = []
    prev_alloc = None

    # Feature columns ordered as we built them
    feat_cols = feat_df.columns.tolist()

    for i, dt in enumerate(oos_months):
        # Signal: use prior month-end feature vector
        prior_dt = dt - pd.offsets.MonthEnd(1)

        # Find closest available date in feat_m
        avail = feat_m.index[feat_m.index <= prior_dt]
        if len(avail) == 0:
            port_rets.append((dt, 0.0))
            state_hist.append((dt, "unknown"))
            continue

        sig_dt = avail[-1]
        x_row  = feat_m.loc[[sig_dt]].values  # shape (1, 9)

        # Predict state (forward-only, no look-ahead)
        try:
            raw_state = int(model.predict(x_row)[0])
        except Exception:
            raw_state = 0

        regime_label = label_map.get(raw_state, "low_vol")
        alloc = ALLOC[regime_label]
        state_hist.append((dt, regime_label))

        # Monthly return of the portfolio
        if dt in ret_m.index:
            port_ret = sum(alloc.get(t, 0.0) * ret_m.loc[dt, t]
                           for t in UNIVERSE)
        else:
            port_ret = 0.0

        # Transaction cost: 10bp per asset when weights change
        if prev_alloc is not None:
            turnover = sum(abs(alloc.get(t, 0.0) - prev_alloc.get(t, 0.0))
                          for t in UNIVERSE)
            port_ret -= TXCOST * turnover / 1.0   # weight-adjusted cost

        prev_alloc = alloc
        port_rets.append((dt, port_ret))

    dates_out, rets_out = zip(*port_rets) if port_rets else ([], [])
    monthly_returns = pd.Series(list(rets_out), index=pd.DatetimeIndex(list(dates_out)))

    dates_st, st_out = zip(*state_hist) if state_hist else ([], [])
    state_series = pd.Series(list(st_out), index=pd.DatetimeIndex(list(dates_st)))

    # SPY monthly returns for benchmark
    spy_m = ret_m["SPY"][(ret_m.index >= oos_start_ts) & (ret_m.index <= oos_end_ts)]

    return monthly_returns, state_series, spy_m


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio statistics
# ─────────────────────────────────────────────────────────────────────────────

def calc_stats(returns_series, label=""):
    r = returns_series.dropna()
    if len(r) < 6:
        return {}
    eq = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr    = eq.iloc[-1] ** (1/n_years) - 1
    vol     = r.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    roll_max = eq.expanding().max()
    max_dd   = (eq / roll_max - 1).min()
    neg_yrs  = (r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    return {
        "label":    label,
        "n_months": len(r),
        "cagr":     round(float(cagr), 4),
        "sharpe":   round(float(sharpe), 4),
        "max_dd":   round(float(max_dd), 4),
        "ann_vol":  round(float(vol), 4),
        "neg_yrs":  int(neg_yrs),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("H251 — 3-State HMM Tactical Allocation (SPY/TLT/GLD)")
    print("=" * 60)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print(f"\n[1] Loading price data {FULL_START} to {FULL_END}...")
    prices = fetch_prices()
    prices = prices[UNIVERSE].dropna()
    print(f"    Shape: {prices.shape}, range: {prices.index[0].date()} to {prices.index[-1].date()}")

    # ── 2. Build features ─────────────────────────────────────────────────────
    print("\n[2] Building feature matrix...")
    feat_df = build_features(prices)
    print(f"    Features: {feat_df.columns.tolist()}")
    print(f"    Feature rows: {len(feat_df)}, range: {feat_df.index[0].date()} to {feat_df.index[-1].date()}")

    # IS window
    feat_is = feat_df[(feat_df.index >= IS_START) & (feat_df.index <= IS_END)]
    print(f"    IS feature rows: {len(feat_is)}")

    X_is = feat_is.values.astype(float)

    # ── 3. Fit HMM on IS ─────────────────────────────────────────────────────
    print("\n[3] Fitting 3-state GaussianHMM on IS 2004-2017...")
    model = fit_hmm(X_is)
    print(f"    HMM converged. Log-likelihood: {model.score(X_is):.2f}")

    # ── 4. Label states ───────────────────────────────────────────────────────
    print("\n[4] Labeling states by volatility...")
    feat_cols = feat_df.columns.tolist()
    label_map = label_states(model, X_is, feat_cols)
    for state_int, state_label in label_map.items():
        spy_vol_idx = feat_cols.index("SPY_vol21")
        print(f"    State {state_int} → {state_label}  "
              f"(SPY_vol21 mean = {model.means_[state_int, spy_vol_idx]:.4f})")

    # IS state distribution
    is_states = model.predict(X_is)
    is_state_labels = [label_map.get(s, "unknown") for s in is_states]
    for lbl in ["low_vol", "transition", "high_vol"]:
        cnt = is_state_labels.count(lbl)
        print(f"    IS {lbl}: {cnt} days ({cnt/len(is_state_labels)*100:.1f}%)")

    # ── 5. OOS backtest ───────────────────────────────────────────────────────
    print("\n[5] Running OOS backtest 2018-2025...")
    oos_returns, oos_states, spy_oos = backtest_hmm(
        model, label_map, feat_df, prices, OOS_START, OOS_END
    )
    print(f"    OOS months: {len(oos_returns)}")

    # ── 6. Statistics ─────────────────────────────────────────────────────────
    print("\n[6] Computing statistics...")
    h251_stats  = calc_stats(oos_returns,           label="H251 OOS")
    spy_stats   = calc_stats(spy_oos,               label="SPY OOS")

    # IS backtest for reference (using IS model predictions on IS data)
    is_months_idx = prices.resample("ME").last().index
    is_months_idx = is_months_idx[(is_months_idx >= IS_START) & (is_months_idx <= IS_END)]
    is_returns_list = []
    prev_alloc = None
    prices_m = prices.resample("ME").last()
    ret_m    = prices_m.pct_change()
    feat_m   = feat_df.resample("ME").last()
    for dt in is_months_idx:
        prior_dt = dt - pd.offsets.MonthEnd(1)
        avail = feat_m.index[feat_m.index <= prior_dt]
        if len(avail) == 0:
            is_returns_list.append((dt, 0.0))
            continue
        sig_dt = avail[-1]
        x_row = feat_m.loc[[sig_dt]].values
        try:
            raw_state = int(model.predict(x_row)[0])
        except Exception:
            raw_state = 0
        regime_label = label_map.get(raw_state, "low_vol")
        alloc = ALLOC[regime_label]
        if dt in ret_m.index:
            port_ret = sum(alloc.get(t, 0.0) * ret_m.loc[dt, t] for t in UNIVERSE)
        else:
            port_ret = 0.0
        if prev_alloc is not None:
            turnover = sum(abs(alloc.get(t, 0.0) - prev_alloc.get(t, 0.0)) for t in UNIVERSE)
            port_ret -= TXCOST * turnover
        prev_alloc = alloc
        is_returns_list.append((dt, port_ret))

    if is_returns_list:
        is_dates, is_rets = zip(*is_returns_list)
        is_monthly = pd.Series(list(is_rets), index=pd.DatetimeIndex(list(is_dates)))
    else:
        is_monthly = pd.Series(dtype=float)

    h251_is_stats = calc_stats(is_monthly, label="H251 IS")

    print(f"\n    SPY B&H OOS: Sharpe={spy_stats.get('sharpe','N/A'):.3f}  "
          f"MaxDD={spy_stats.get('max_dd','N/A'):.3f}")
    print(f"    H251 IS:     Sharpe={h251_is_stats.get('sharpe','N/A'):.3f}  "
          f"MaxDD={h251_is_stats.get('max_dd','N/A'):.3f}")
    print(f"    H251 OOS:    Sharpe={h251_stats.get('sharpe','N/A'):.3f}  "
          f"MaxDD={h251_stats.get('max_dd','N/A'):.3f}  "
          f"CAGR={h251_stats.get('cagr','N/A'):.3f}")

    confirmed = h251_stats.get("sharpe", 0.0) > 0.8
    print(f"\n    Confirm gate: OOS Sharpe > 0.8")
    print(f"    Result: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── 7. State distribution (OOS) ───────────────────────────────────────────
    print("\n[7] OOS state distribution...")
    for lbl in ["low_vol", "transition", "high_vol"]:
        cnt = (oos_states == lbl).sum()
        print(f"    {lbl}: {cnt} months ({cnt/len(oos_states)*100:.1f}%)")

    # ── 8. H026 correlation ───────────────────────────────────────────────────
    print("\n[8] Diversification check vs H026...")
    h026_results_path = RESULT_DIR / "h026_results.json"
    corr_vs_h026 = None
    if h026_results_path.exists():
        # Try to load H026 monthly returns from cache
        h026_cache = None
        for f in CACHE_DIR.glob("h026_*.parquet"):
            try:
                df = pd.read_parquet(f)
                if "returns" in df.columns or len(df.columns) == 1:
                    h026_cache = df.iloc[:, 0]
                    break
            except Exception:
                continue

        if h026_cache is not None:
            h026_oos = h026_cache[
                (h026_cache.index >= pd.Timestamp(OOS_START)) &
                (h026_cache.index <= pd.Timestamp(OOS_END))
            ]
            common = oos_returns.index.intersection(h026_oos.index)
            if len(common) > 12:
                corr_vs_h026 = float(oos_returns.reindex(common).corr(h026_oos.reindex(common)))
                print(f"    Corr(H251, H026) OOS: {corr_vs_h026:.4f}")
            else:
                print("    H026 cache insufficient for correlation (different date range)")
        else:
            print("    H026 monthly return cache not found — skipping correlation")
    else:
        print("    H026 results not found — skipping correlation")

    if corr_vs_h026 is None:
        # Try loading from the h249 all-prices cache
        try:
            h249_cache = CACHE_DIR / f"h249_all_{FULL_START}_{FULL_END}.parquet"
            if not h249_cache.exists():
                # Try other FULL_END variants
                for f in CACHE_DIR.glob("h249_all_*.parquet"):
                    h249_cache = f
                    break

            if h249_cache.exists():
                all_prices = pd.read_parquet(h249_cache)
                h026_secs  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLY","XLP","XLC","XLRE"]
                h026_cols  = [c for c in h026_secs if c in all_prices.columns]
                if h026_cols:
                    prices_m2 = all_prices[h026_cols].resample("ME").last()
                    ret_m2    = prices_m2.pct_change()
                    mom12     = prices_m2.pct_change(12)
                    vol6      = ret_m2.rolling(6).std()
                    h026_r    = []
                    dates2    = prices_m2.index
                    for ii in range(13, len(dates2)):
                        m12  = mom12.iloc[ii-1]
                        v6   = vol6.iloc[ii-1]
                        valid = m12.notna() & v6.notna() & (v6 > 0)
                        if valid.sum() < 2:
                            h026_r.append((dates2[ii], 0.0))
                            continue
                        rank_m = m12[valid].rank(ascending=False)
                        rank_v = (1.0/v6[valid]).rank(ascending=False)
                        sel    = (rank_m + rank_v).nlargest(1).index.tolist()
                        r_val  = float(ret_m2.loc[dates2[ii], sel].mean()) if sel else 0.0
                        h026_r.append((dates2[ii], 0.0 if np.isnan(r_val) else r_val))
                    h026_series = pd.Series(
                        [v for _, v in h026_r],
                        index=pd.DatetimeIndex([d for d, _ in h026_r])
                    )
                    h026_oos2 = h026_series[
                        (h026_series.index >= pd.Timestamp(OOS_START)) &
                        (h026_series.index <= pd.Timestamp(OOS_END))
                    ]
                    common2 = oos_returns.index.intersection(h026_oos2.index)
                    if len(common2) > 12:
                        corr_vs_h026 = float(oos_returns.reindex(common2).corr(
                            h026_oos2.reindex(common2)
                        ))
                        print(f"    Corr(H251, H026) OOS [rebuilt]: {corr_vs_h026:.4f}")
        except Exception as e:
            print(f"    H026 correlation rebuild failed: {e}")

    # ── 9. Save results ───────────────────────────────────────────────────────
    print("\n[9] Saving results...")
    oos_state_counts = oos_states.value_counts().to_dict()

    results = {
        "hypothesis":    "H251",
        "description":   "3-State HMM Tactical Allocation (SPY/TLT/GLD)",
        "source":        "arXiv:2605.27848 (Verma, Putri & Lesupi, May 2026)",
        "confirmed":     confirmed,
        "confirm_gate":  "OOS Sharpe > 0.8",
        "h251_is":       h251_is_stats,
        "h251_oos":      h251_stats,
        "spy_bnh_oos":   spy_stats,
        "oos_state_counts": {str(k): int(v) for k, v in oos_state_counts.items()},
        "state_labels":  {str(k): v for k, v in label_map.items()},
        "state_vol_means": {
            str(k): round(float(model.means_[k, feat_cols.index("SPY_vol21")]), 4)
            for k in range(3)
        },
        "allocation_rules": {k: v for k, v in ALLOC.items()},
        "corr_vs_h026":  round(corr_vs_h026, 4) if corr_vs_h026 is not None else None,
        "data_source":   "yfinance",
        "hmm_params": {
            "n_components":    3,
            "covariance_type": "full",
            "n_iter":          300,
        },
    }

    out_path = RESULT_DIR / "h251_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"    Saved: {out_path}")

    print("\n" + "=" * 60)
    print(f"H251 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  OOS Sharpe: {h251_stats.get('sharpe', 0):.4f}  (gate: > 0.8)")
    print(f"  OOS MaxDD:  {h251_stats.get('max_dd', 0):.4f}")
    print(f"  SPY B&H:    {spy_stats.get('sharpe', 0):.4f}")
    if corr_vs_h026 is not None:
        print(f"  Corr vs H026: {corr_vs_h026:.4f}")
    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
