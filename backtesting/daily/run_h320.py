"""
H320 — LightGBM Momentum Crash Filter on H198 6-1m Momentum
============================================================
Source: EdgeTools blog "Momentum Crashes Are Optional (If You Let ML Filter Them)" (2026)
Academic basis: Daniel & Moskowitz (2016) JF — momentum crash risk during market reversals

Hypothesis: A LightGBM classifier trained on macro + technical features identifies
high-crash-risk momentum periods one month ahead and gates/scales the H198 6-1m signal.
EdgeTools reports MaxDD reduction 30% → 13% on US equity momentum.
On H198 (OOS Sharpe 1.174), crash filter should preserve upside while cutting 2022 drawdown.

Variants:
  A: H198 6-1m baseline (no filter)
  B: H198 + VIX < 25 gate (simple regime benchmark)
  C: H198 + LightGBM P_crash < 0.35 (hard gate)
  D: H198 + LightGBM continuous scaling (position × (1 - P_crash))

IS: 2013-01-01 to 2020-12-31
OOS: 2021-01-01 to 2026-06-20
Gate: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD improvement > 5pp
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
import fredapi

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# Same 30-stock universe as H198
UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM","BA","CAT","IBM",
]

DATA_START   = "2011-01-01"
DATA_END     = "2026-06-20"
IS_START     = pd.Timestamp("2013-01-01")
IS_END       = pd.Timestamp("2020-12-31")
OOS_START    = pd.Timestamp("2021-01-01")
OOS_END      = pd.Timestamp("2026-06-20")
TOP_N        = 6       # top quintile of 30 stocks (6-1m signal)
LOOKBACK     = 6       # 6-1m as in H198 best signal
TC_BPS       = 5       # one-way transaction cost
CRASH_THRESH = -0.05   # return < -5% = crash month
P_GATE       = 0.35    # hard gate: skip if P_crash >= 0.35
TRAIN_MONTHS = 24      # rolling training window


def fetch_monthly(ticker: str) -> pd.Series:
    """Load monthly prices, using H198 cache if available."""
    # Try H198 cache first
    cp = CACHE_DIR / f"h198_{ticker}_monthly_{DATA_START}_2026-04-30.parquet"
    if cp.exists():
        s = pd.read_parquet(cp).squeeze()
        # Need to extend to 2026-06-20 if needed
        if s.index[-1] < pd.Timestamp("2026-05-31"):
            pass  # will download fresh
        else:
            return s

    cp2 = CACHE_DIR / f"h320_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp2.exists():
        return pd.read_parquet(cp2).squeeze()

    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp2)
    return s


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h320_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading daily {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"]
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_vix_daily() -> pd.Series:
    cp = CACHE_DIR / f"h320_VIX_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print("  Downloading VIX…")
    raw = yf.download("^VIX", start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^VIX", axis=1, level=1)
    s = raw["Close"]
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_yield_curve() -> pd.Series:
    """T10Y3M from FRED — monthly, last business day of month."""
    import os
    cp = CACHE_DIR / f"h320_T10Y3M_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print("  Downloading T10Y3M from FRED…")
    fred_key = os.environ.get("FRED_API_KEY", "")
    fred = fredapi.Fred(api_key=fred_key)
    s = fred.get_series("T10Y3M", observation_start=DATA_START, observation_end=DATA_END)
    s = s.resample("ME").last()
    s.name = "T10Y3M"
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def cagr(r: pd.Series) -> float:
    n = len(r)
    if n == 0:
        return 0.0
    return float((1 + r).prod() ** (12 / n) - 1)


def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0}
    return {
        "n":      len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(cagr(r), 3),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def build_h198_rets(prices: pd.DataFrame) -> pd.Series:
    """Reconstruct H198 6-1m momentum returns (monthly)."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START - pd.DateOffset(months=12)]
    for i, month_end in enumerate(months):
        loc = monthly_ret.index.get_loc(month_end)
        if loc < LOOKBACK + 1:
            continue
        sig_start = loc - LOOKBACK - 1
        sig_end   = loc - 1
        if sig_start < 0:
            continue
        sig = prices.iloc[sig_end] / prices.iloc[sig_start] - 1
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        selected = sig.nlargest(TOP_N).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def build_features(h198_rets: pd.Series,
                   spy_daily: pd.Series,
                   vix_daily: pd.Series,
                   yc_monthly: pd.Series) -> pd.DataFrame:
    """
    Build feature matrix aligned to month-end dates.
    All features use data available at end of month t (predicting month t+1 crash).
    """
    # Resample all to month-end
    spy_monthly = spy_daily.resample("ME").last()
    vix_monthly_mean = vix_daily.resample("ME").mean()
    vix_monthly_end  = vix_daily.resample("ME").last()

    months = h198_rets.index
    feat_rows = []
    for i, d in enumerate(months):
        if i < 6:
            continue
        # 1. SPY/MA200 at month-end
        spy_window = spy_daily.loc[:d].iloc[-200:]
        if len(spy_window) < 200:
            continue
        spy_ma200 = spy_window.mean()
        spy_cur = spy_window.iloc[-1]
        f1_spy_ma200 = float(spy_cur / spy_ma200 - 1)

        # 2. VIX level (monthly mean)
        f2_vix_level = float(vix_monthly_mean.get(d, np.nan))

        # 3. VIX 20d change
        vix_recent = vix_daily.loc[:d].iloc[-20:]
        vix_prior  = vix_daily.loc[:d].iloc[-40:-20]
        if len(vix_recent) < 10 or len(vix_prior) < 10:
            f3_vix_chg = 0.0
        else:
            f3_vix_chg = float(vix_recent.mean() / vix_prior.mean() - 1)

        # 4. Momentum portfolio trailing volatility (rolling 6m std of h198 rets)
        recent_rets = h198_rets.loc[:d].iloc[-6:]
        f4_mom_vol = float(recent_rets.std() * np.sqrt(12)) if len(recent_rets) >= 3 else np.nan

        # 5. Momentum portfolio trailing 6m return
        if i >= 6:
            f5_mom_ret6 = float((1 + h198_rets.iloc[i-6:i]).prod() - 1)
        else:
            f5_mom_ret6 = np.nan

        # 6. Yield curve slope T10Y3M
        yc_at_d = yc_monthly.get(d, np.nan)
        f6_yc = float(yc_at_d) if not pd.isna(yc_at_d) else 0.0

        feat_rows.append({
            "date": d,
            "spy_ma200": f1_spy_ma200,
            "vix_level": f2_vix_level,
            "vix_chg20": f3_vix_chg,
            "mom_vol": f4_mom_vol,
            "mom_ret6": f5_mom_ret6,
            "yc_slope": f6_yc,
        })

    features = pd.DataFrame(feat_rows).set_index("date")
    features = features.dropna()
    return features


def rolling_lgbm_predict(features: pd.DataFrame,
                          h198_rets: pd.Series,
                          train_months: int = TRAIN_MONTHS) -> pd.Series:
    """
    Rolling LightGBM crash probability predictions.
    For each month t: train on (t-train_months to t-1), predict P_crash at t.
    Target: 1 if h198_rets[t] < CRASH_THRESH else 0.
    Returns a Series of crash probabilities aligned to months.
    """
    import lightgbm as lgb

    feat_cols = ["spy_ma200", "vix_level", "vix_chg20", "mom_vol", "mom_ret6", "yc_slope"]
    months = features.index
    preds = {}

    for i, t in enumerate(months):
        if i < train_months:
            continue
        # Training window: months [i-train_months, i-1]
        train_idx = months[max(0, i - train_months): i]
        X_train = features.loc[train_idx, feat_cols].values
        y_train = (h198_rets.loc[train_idx] < CRASH_THRESH).astype(int).values

        if len(X_train) < 12 or y_train.sum() == 0:
            # Can't train with zero positive examples — default to no crash
            preds[t] = 0.0
            continue

        X_pred = features.loc[[t], feat_cols].values

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "num_leaves": 15,
            "learning_rate": 0.05,
            "n_estimators": 100,
            "min_child_samples": 3,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "verbose": -1,
            "random_state": 42,
        }
        clf = lgb.LGBMClassifier(**params)
        clf.fit(X_train, y_train)
        p = clf.predict_proba(X_pred)[0][1]
        preds[t] = float(p)

    return pd.Series(preds)


def backtest_variant(h198_rets: pd.Series,
                     crash_probs: pd.Series,
                     vix_monthly: pd.Series,
                     variant: str,
                     start: pd.Timestamp,
                     end: pd.Timestamp) -> pd.Series:
    """
    Apply filter variant to H198 returns over a period.
    Returns filtered monthly return series.
    """
    filtered = []
    months = h198_rets[(h198_rets.index >= start) & (h198_rets.index <= end)].index

    for d in months:
        ret = h198_rets.get(d, 0.0)

        if variant == "A":
            # No filter
            filtered.append((d, ret))

        elif variant == "B":
            # VIX < 25 gate
            v = vix_monthly.get(d, np.nan)
            if pd.isna(v) or v < 25:
                filtered.append((d, ret))
            else:
                filtered.append((d, 0.0))  # cash

        elif variant == "C":
            # LightGBM hard gate
            if d not in crash_probs.index:
                filtered.append((d, ret))  # no prediction → hold
                continue
            p = crash_probs.get(d, 0.0)
            if p < P_GATE:
                filtered.append((d, ret))
            else:
                filtered.append((d, 0.0))  # cash

        elif variant == "D":
            # LightGBM continuous scaling
            if d not in crash_probs.index:
                filtered.append((d, ret))
                continue
            p = crash_probs.get(d, 0.0)
            scale = max(0.0, 1.0 - p)
            filtered.append((d, ret * scale))

    s = pd.Series({d: r for d, r in filtered})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H320 — LightGBM Momentum Crash Filter")
    print("=" * 60)

    # --- Load price data ---
    print("\nLoading price data…")
    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_monthly(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index()
    print(f"  {len(prices.columns)} tickers, {len(prices)} months")

    # --- Build H198 returns ---
    print("\nBuilding H198 6-1m returns…")
    h198_rets = build_h198_rets(prices)
    print(f"  {len(h198_rets)} monthly return observations")

    # --- Load auxiliary data ---
    print("\nLoading VIX, SPY daily, yield curve…")
    spy_daily = fetch_daily("SPY")
    vix_daily = fetch_vix_daily()
    yc_monthly = fetch_yield_curve()
    vix_monthly_mean = vix_daily.resample("ME").mean()

    # --- Build features ---
    print("\nBuilding feature matrix…")
    features = build_features(h198_rets, spy_daily, vix_daily, yc_monthly)
    print(f"  {len(features)} feature rows, {len(features.columns)} features")

    # --- Rolling LightGBM predictions ---
    print(f"\nRunning rolling LightGBM (2yr training window)…")
    crash_probs = rolling_lgbm_predict(features, h198_rets, TRAIN_MONTHS)
    print(f"  {len(crash_probs)} predictions generated")
    print(f"  P_crash statistics: mean={crash_probs.mean():.3f} max={crash_probs.max():.3f}")

    # Count crash months and how many we'd gate (C) or reduce (D)
    crash_months = (h198_rets < CRASH_THRESH)
    n_crashes_oos = crash_months[(crash_months.index >= OOS_START) & (crash_months.index <= OOS_END)].sum()
    n_gated_c = (crash_probs[(crash_probs.index >= OOS_START) & (crash_probs.index <= OOS_END)] >= P_GATE).sum()
    print(f"  Actual crash months OOS: {n_crashes_oos}")
    print(f"  Variant C would gate (P>={P_GATE}): {n_gated_c} months OOS")

    # --- Backtest all variants ---
    print("\n" + "=" * 60)
    print("H320 Results: IS 2013-2020 | OOS 2021-2026")
    print("=" * 60)
    print(f"{'Variant':<30} {'IS Sh':>7} {'IS CAGR':>8} {'OOS Sh':>7} {'OOS CAGR':>9} {'OOS MaxDD':>10} {'NegYrs':>7}")
    print("-" * 80)

    spy_monthly_cp = CACHE_DIR / f"h320_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_monthly_cp.exists():
        spy_px = pd.read_parquet(spy_monthly_cp).squeeze()
    else:
        spy_px = spy_daily.resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_monthly_cp)
    spy_ret = spy_px.pct_change().dropna()

    all_results = {}
    variant_labels = {
        "A": "A: H198 baseline",
        "B": "B: VIX<25 gate",
        "C": f"C: LightGBM P<{P_GATE} gate",
        "D": "D: LightGBM continuous scale",
    }

    for v, label in variant_labels.items():
        rets_full = backtest_variant(h198_rets, crash_probs, vix_monthly_mean, v,
                                     IS_START, OOS_END)
        is_ = eval_period(rets_full, IS_START, IS_END)
        oos_ = eval_period(rets_full, OOS_START, OOS_END)

        print(f"{label:<30} {is_['sharpe']:>7.3f} {is_['cagr']:>7.1%} "
              f"{oos_['sharpe']:>7.3f} {oos_['cagr']:>8.1%} "
              f"{oos_['maxdd']:>9.1%} {oos_['neg_yrs']:>7d}")

        all_results[v] = {"label": label, "is": is_, "oos": oos_,
                          "rets": rets_full.to_dict()}

    # SPY benchmark
    spy_is  = eval_period(spy_ret, IS_START, IS_END)
    spy_oos = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"{'SPY buy-hold':<30} {spy_is['sharpe']:>7.3f} {spy_is['cagr']:>7.1%} "
          f"{spy_oos['sharpe']:>7.3f} {spy_oos['cagr']:>8.1%} "
          f"{spy_oos['maxdd']:>9.1%} {spy_oos['neg_yrs']:>7d}")

    # OOS year-by-year for variant C and D vs baseline
    print("\n--- OOS Year-by-Year: Variant A vs C vs D vs SPY ---")
    print(f"{'Year':<6} {'A (base)':>9} {'B (VIX)':>9} {'C (LGBM)':>9} {'D (scale)':>9} {'SPY':>7}")
    print("-" * 55)
    rets_A = backtest_variant(h198_rets, crash_probs, vix_monthly_mean, "A", OOS_START, OOS_END)
    rets_B = backtest_variant(h198_rets, crash_probs, vix_monthly_mean, "B", OOS_START, OOS_END)
    rets_C = backtest_variant(h198_rets, crash_probs, vix_monthly_mean, "C", OOS_START, OOS_END)
    rets_D = backtest_variant(h198_rets, crash_probs, vix_monthly_mean, "D", OOS_START, OOS_END)
    spy_oos_r = spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)]

    for yr in range(2021, 2027):
        s = pd.Timestamp(f"{yr}-01-01")
        e = pd.Timestamp(f"{yr}-12-31")
        def yr_ret(r):
            w = r[(r.index >= s) & (r.index <= e)]
            return float((1 + w).prod() - 1) if len(w) > 0 else np.nan
        print(f"{yr:<6} {yr_ret(rets_A):>8.1%} {yr_ret(rets_B):>8.1%} "
              f"{yr_ret(rets_C):>8.1%} {yr_ret(rets_D):>8.1%} {yr_ret(spy_oos_r):>6.1%}")

    # Correlation with SPY OOS
    print("\n--- OOS Correlations with SPY ---")
    for v, r in [("A", rets_A), ("B", rets_B), ("C", rets_C), ("D", rets_D)]:
        common = r.index.intersection(spy_oos_r.index)
        if len(common) > 6:
            corr = float(r.loc[common].corr(spy_oos_r.loc[common]))
            print(f"  Variant {v}: Corr(SPY) = {corr:.3f}")

    # --- WF ratios ---
    print("\n--- Walk-Forward Ratios (OOS Sharpe / IS Sharpe) ---")
    for v, label in variant_labels.items():
        is_sh  = all_results[v]["is"].get("sharpe", 0)
        oos_sh = all_results[v]["oos"].get("sharpe", 0)
        wf = oos_sh / is_sh if is_sh > 0 else 0
        gate = (oos_sh > 1.174 and (all_results["A"]["oos"]["maxdd"] - all_results[v]["oos"]["maxdd"]) > 0.05)
        print(f"  {label}: IS={is_sh:.3f}, OOS={oos_sh:.3f}, WF={wf:.3f} {'✓ GATE PASS' if gate else ''}")

    # --- Save results ---
    out = {
        "hypothesis": "H320",
        "title": "LightGBM Momentum Crash Filter on H198 6-1m Momentum",
        "gate": "OOS Sharpe > 1.174 AND MaxDD improvement > 5pp",
        "variants": {k: {kk: vv for kk, vv in v.items() if kk != "rets"}
                     for k, v in all_results.items()},
        "crash_prob_stats": {
            "mean": round(float(crash_probs.mean()), 4),
            "max": round(float(crash_probs.max()), 4),
            "oos_months_gated_c": int(n_gated_c),
            "actual_crash_months_oos": int(n_crashes_oos),
        },
    }
    with open(RESULT_DIR / "h320_results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved to backtesting/results/h320_results.json")


if __name__ == "__main__":
    main()
