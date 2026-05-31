"""
H233 — Alpha101 Cross-Sectional with Adjusted-MSE Sign-Penalty Loss
====================================================================
Source: arXiv:2507.07107 v2 (Du, May 2026)

Hypothesis: Replacing standard MSE loss with Adjusted-MSE (wrong-sign
predictions penalized 11x more heavily) in a LightGBM model trained on
H217's alpha101 signals + TA features improves directional accuracy and
OOS Sharpe vs H217 baseline (1.559).

Signal construction:
- Base: H217's alpha101 = (close-open)/(0.001+high-low), monthly median
- TA features (monthly close): MACD(12/26/9), RSI(14), Stoch %K/%D(14/3), ROC(10)
- Model: LightGBM with custom Adjusted-MSE objective
- Universe: same 30 large-cap stocks as H217
- IS: 2013-2020, OOS: 2021-2026
- Confirm: OOS Sharpe > 1.559 (H217 baseline)
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 6
CONFIRM_THRESHOLD = 1.559   # H217 OOS Sharpe baseline


# ── Custom LightGBM Adjusted-MSE objective ────────────────────────────────────

def adjusted_mse(y_pred, dtrain):
    """Wrong-sign predictions penalized 11x vs standard MSE."""
    y_true = dtrain.get_label()
    residual = y_pred - y_true
    sign_wrong = (np.sign(y_pred) != np.sign(y_true)).astype(float)
    weight = 1.0 + 10.0 * sign_wrong   # baseline 1, wrong-sign 11
    grad = weight * residual
    hess = weight
    return grad, hess


# ── Data loading ─────────────────────────────────────────────────────────────

def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    """Reuse H215/H217 cache where available."""
    for prefix in ["h215", "h217"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h233_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df.to_parquet(cp)
    return df


# ── Alpha101 (H217 signal) ────────────────────────────────────────────────────

def compute_alpha101(df: pd.DataFrame) -> pd.Series:
    """(close - open) / (0.001 + high - low), clipped to [-1, 1]."""
    a = (df["close"] - df["open"]) / (0.001 + df["high"] - df["low"])
    return a.clip(-1, 1)


# ── TA features on daily close, then resample monthly ───────────────────────

def compute_ta_features_daily(close: pd.Series, high: pd.Series = None,
                               low: pd.Series = None) -> pd.DataFrame:
    """
    Compute MACD, RSI, Stochastic %K/%D, ROC on daily prices.
    Returns daily DataFrame of features.
    """
    c = close.copy()

    # MACD (12/26/9 EMA)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line

    # RSI (14-period), normalized to [0, 1]
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = (100 - 100 / (1 + rs)) / 100.0  # normalize to [0,1]

    # Stochastic %K/%D (14/3)
    if high is not None and low is not None:
        low14  = low.rolling(14).min()
        high14 = high.rolling(14).max()
        denom = (high14 - low14).replace(0, np.nan)
        stoch_k = (c - low14) / denom
    else:
        # fallback: use close rolling range
        low14  = c.rolling(14).min()
        high14 = c.rolling(14).max()
        denom = (high14 - low14).replace(0, np.nan)
        stoch_k = (c - low14) / denom
    stoch_d = stoch_k.rolling(3).mean()

    # ROC (10-period)
    roc = c.pct_change(10)

    return pd.DataFrame({
        "macd_line":   macd_line,
        "signal_line": signal_line,
        "macd_hist":   macd_hist,
        "rsi":         rsi,
        "stoch_k":     stoch_k,
        "stoch_d":     stoch_d,
        "roc":         roc,
    })


# ── Metrics ──────────────────────────────────────────────────────────────────

def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r):  return float((1 + r).prod())
def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0}
    return {
        "label":   label,
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 12), 3),
        "cumul":   round(cumul(r), 4),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import lightgbm as lgb

    print("H233 — Alpha101 + TA Features with Adjusted-MSE LightGBM")
    print("=" * 60)

    # ── Step 1: Load daily OHLCV ─────────────────────────────────────────────
    print("\nStep 1: Loading daily OHLCV…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    print(f"  Loaded {len(daily_data)} tickers")

    # ── Step 2: Compute alpha101 and TA features, aggregate monthly ──────────
    print("\nStep 2: Computing alpha101 + TA features…")

    alpha_daily_dict = {}
    ta_daily_dict = {}

    for t, df in daily_data.items():
        alpha_daily_dict[t] = compute_alpha101(df)
        ta_df = compute_ta_features_daily(
            df["close"],
            high=df.get("high"),
            low=df.get("low"),
        )
        ta_daily_dict[t] = ta_df

    # Monthly aggregation: alpha101 via MEDIAN, TA features via LAST value of month
    alpha_daily = pd.DataFrame(alpha_daily_dict).sort_index()
    alpha_monthly_median = alpha_daily.resample("ME").median()

    # Monthly close prices for return computation
    close_monthly = {}
    for t, df in daily_data.items():
        close_monthly[t] = df["close"].resample("ME").last()
    close_px = pd.DataFrame(close_monthly).sort_index()
    monthly_ret = close_px.pct_change()

    # TA features: take last value of each month (end-of-month state)
    # Shape: (n_months, n_features) per ticker
    ta_monthly = {}
    for t, ta_df in ta_daily_dict.items():
        ta_monthly[t] = ta_df.resample("ME").last()

    print(f"  Alpha monthly shape: {alpha_monthly_median.shape}")
    print(f"  Monthly ret shape:   {monthly_ret.shape}")

    # ── Step 3: Build ML feature matrix ─────────────────────────────────────
    print("\nStep 3: Building ML feature matrix…")

    # For each month M, signal is formed at end of M (no lookahead):
    # - features: alpha101 median of month M, TA values at end of month M
    # - target: forward 1-month return (month M+1)
    # Apply 1-month shift so features at M predict return at M+1
    alpha_signal = alpha_monthly_median.shift(1)   # known at start of M+1

    FEATURE_COLS = ["alpha101", "macd_line", "signal_line", "macd_hist",
                    "rsi", "stoch_k", "stoch_d", "roc"]

    # Build long-form training dataset: one row per (month, stock)
    rows = []
    months = sorted(set(alpha_signal.index) & set(monthly_ret.index))
    months = [m for m in months if m >= IS_START]

    for m in months:
        if m not in alpha_signal.index:
            continue
        alpha_row = alpha_signal.loc[m]       # alpha101 signals (shifted)
        ret_row   = monthly_ret.loc[m]        # forward return at month m

        for t in UNIVERSE:
            if t not in alpha_row.index or pd.isna(alpha_row[t]):
                continue
            if t not in ret_row.index or pd.isna(ret_row[t]):
                continue
            # TA features: take the month-M end value (already shifted via signal logic)
            # We use alpha_signal shift(1) means these TA features are from month M-1
            # To match: TA at M-1 (lagged), predicts M return
            ta_m_idx = pd.Timestamp(m) - pd.offsets.MonthEnd(1)
            if t in ta_monthly and ta_m_idx in ta_monthly[t].index:
                ta_row = ta_monthly[t].loc[ta_m_idx]
                ta_vals = [ta_row.get(c, np.nan) for c in
                           ["macd_line", "signal_line", "macd_hist", "rsi", "stoch_k", "stoch_d", "roc"]]
            else:
                ta_vals = [np.nan] * 7

            rows.append({
                "month":    m,
                "ticker":   t,
                "alpha101": alpha_row[t],
                "macd_line":   ta_vals[0],
                "signal_line": ta_vals[1],
                "macd_hist":   ta_vals[2],
                "rsi":         ta_vals[3],
                "stoch_k":     ta_vals[4],
                "stoch_d":     ta_vals[5],
                "roc":         ta_vals[6],
                "target":   ret_row[t],
            })

    full_df = pd.DataFrame(rows)
    full_df = full_df.dropna(subset=FEATURE_COLS + ["target"])
    print(f"  Total samples: {len(full_df)} ({len(full_df['month'].unique())} months × ~{len(UNIVERSE)} stocks)")

    # ── Step 4: IS/OOS split and LightGBM training ──────────────────────────
    print("\nStep 4: Training LightGBM with Adjusted-MSE…")

    is_df  = full_df[(full_df["month"] >= IS_START) & (full_df["month"] <= IS_END)]
    oos_df = full_df[(full_df["month"] >= OOS_START) & (full_df["month"] <= OOS_END)]

    print(f"  IS samples:  {len(is_df)}")
    print(f"  OOS samples: {len(oos_df)}")

    X_train = is_df[FEATURE_COLS].values
    y_train = is_df["target"].values

    dtrain = lgb.Dataset(X_train, label=y_train, feature_name=FEATURE_COLS)

    base_params = {
        "num_leaves":        31,
        "learning_rate":     0.05,
        "min_child_samples": 10,
        "subsample":         0.8,
        "colsample_bytree":  0.8,
        "verbose":           -1,
        "random_state":      42,
    }

    # Train with custom Adjusted-MSE objective (passed via params in LightGBM 4.x)
    print("  Training with Adjusted-MSE (sign-penalty 11x)…")
    params_adj = dict(base_params)
    params_adj["objective"] = adjusted_mse
    model_adj = lgb.train(
        params_adj,
        dtrain,
        num_boost_round=200,
        valid_sets=[dtrain],
        callbacks=[lgb.log_evaluation(period=50)],
    )

    # Also train standard MSE for comparison
    print("  Training standard MSE baseline…")
    params_std = dict(base_params)
    params_std["objective"] = "regression"
    model_std = lgb.train(
        params_std,
        dtrain,
        num_boost_round=200,
        valid_sets=[dtrain],
        callbacks=[lgb.log_evaluation(period=50)],
    )

    # Feature importance
    fi = dict(zip(FEATURE_COLS, model_adj.feature_importance(importance_type="gain").tolist()))
    fi_sorted = sorted(fi.items(), key=lambda x: x[1], reverse=True)
    print("\n  Feature importance (Adjusted-MSE model, gain):")
    for fname, fval in fi_sorted:
        print(f"    {fname:<15} {fval:.1f}")

    # ── Step 5: Generate predictions and backtest ────────────────────────────
    print("\nStep 5: Generating predictions and running backtest…")

    def run_strategy(model, df_full, label):
        """For each month, predict scores cross-sectionally, long top-N."""
        port_rets = []
        for m, grp in df_full.groupby("month"):
            X = grp[FEATURE_COLS].values
            preds = model.predict(X)
            grp = grp.copy()
            grp["pred"] = preds
            # Cross-sectional rank within the month, long top-N
            grp_sorted = grp.nlargest(TOP_N, "pred")
            avg_ret = grp_sorted["target"].mean()
            port_rets.append((m, avg_ret))
        rets = pd.Series({d: r for d, r in port_rets})
        rets.index = pd.DatetimeIndex(rets.index)
        return rets

    rets_adj = run_strategy(model_adj, full_df, "Adjusted-MSE")
    rets_std = run_strategy(model_std, full_df, "Standard-MSE")

    # H217 baseline: pure median alpha101 rank (no ML)
    port_rets_h217 = []
    months_all = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months_all:
        if month_end not in alpha_signal.index:
            continue
        signal_row = alpha_signal.loc[month_end].dropna()
        if len(signal_row) < TOP_N * 2:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        top_sel = signal_row.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][top_sel].mean()
        port_rets_h217.append((month_end, ret))
    rets_h217 = pd.Series({d: r for d, r in port_rets_h217})
    rets_h217.index = pd.DatetimeIndex(rets_h217.index)

    # SPY
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    # ── Step 6: Results ──────────────────────────────────────────────────────
    print("\n" + "=" * 75)
    print(f"{'Strategy':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}")
    print("-" * 75)

    results = {}
    for label, rets in [
        ("H233 Adjusted-MSE", rets_adj),
        ("H233 Standard-MSE", rets_std),
        ("H217 alpha101 baseline", rets_h217),
        ("SPY B&H", spy_ret),
    ]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<30} {is_.get('sharpe',0):>10.3f} {is_.get('cumul',0):>10.4f} "
              f"{oos_.get('sharpe',0):>10.3f} {oos_.get('cumul',0):>10.4f} "
              f"{oos_.get('maxdd',0):>8.1%} {oos_.get('neg_yrs',0):>7d}")
        results[label] = {"is": is_, "oos": oos_}

    # Correlation: Adjusted-MSE vs H217
    common = rets_adj.index.intersection(rets_h217.index)
    corr_h217 = rets_adj.reindex(common).corr(rets_h217.reindex(common))
    print(f"\n  Corr(H233 Adj-MSE, H217): {corr_h217:.3f}")

    adj_oos_sharpe = results["H233 Adjusted-MSE"]["oos"].get("sharpe", 0)
    confirmed = adj_oos_sharpe > CONFIRM_THRESHOLD

    print(f"\n=== Verdict ===")
    print(f"H233 Adjusted-MSE OOS Sharpe: {adj_oos_sharpe:.3f} (threshold > {CONFIRM_THRESHOLD})")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis":          "H233",
        "confirm_threshold":   CONFIRM_THRESHOLD,
        "confirmed":           confirmed,
        "adj_mse_is":          results["H233 Adjusted-MSE"]["is"],
        "adj_mse_oos":         results["H233 Adjusted-MSE"]["oos"],
        "std_mse_is":          results["H233 Standard-MSE"]["is"],
        "std_mse_oos":         results["H233 Standard-MSE"]["oos"],
        "h217_is":             results["H217 alpha101 baseline"]["is"],
        "h217_oos":            results["H217 alpha101 baseline"]["oos"],
        "spy_oos":             results["SPY B&H"]["oos"],
        "corr_adj_vs_h217":    round(corr_h217, 3),
        "feature_importance":  fi_sorted,
    }
    out_path = RESULT_DIR / "h233_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {out_path}")
    return out


if __name__ == "__main__":
    main()
