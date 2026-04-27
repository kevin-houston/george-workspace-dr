"""
H032 — ML Regime Classifier Overlay on H031
=============================================

Concept:
  Train a RandomForestClassifier (and LogisticRegression for comparison) to predict
  "good" vs "bad" months for the H031 blend (56% H020 / 19% H026 / 25% H009).
  A "good" month is defined as H031 return > 0.

  When the classifier predicts a bad month (prob < 0.45), substitute SHY returns
  for H031 returns (i.e. hold SHY instead of H031 that month).

Feature set (all lagged 1 month — known at month-end before the next month begins):
  1. VIX level (raw)
  2. VIX/VIX3M ratio (term structure)
  3. SPY 1-month return
  4. SPY 12-month return
  5. 10Y-2Y yield spread (FRED T10Y2Y)
  6. SPY realized vol (21-day std of daily returns × sqrt(252))
  7. HYG/IEF ratio (credit spread proxy / risk appetite)

Walk-forward validation:
  - Initial training window: 10 years (120 months)
  - Expand: train on [0..t-1], predict month t, roll forward
  - OOS period starts at month 120 (roughly 2013-08 onward)

H032 rule:
  if RF classifier predicts bad month (prob_good < 0.45) → hold SHY that month
  else → hold H031

Outputs:
  /workspace/agent/backtesting/results/h032_results.json
  /workspace/agent/backtesting/daily/run_h032.py (this file)
"""

import json
import hashlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score

warnings.filterwarnings("ignore")

# ─── Constants ────────────────────────────────────────────────────────────────
INITIAL_EQUITY = 100_000.0
CACHE_DIR      = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

FULL_START = "2000-01-01"
FULL_END   = "2026-04-27"

# H031 optimal weights (from H031 max-Sharpe result)
W_H020 = 0.56
W_H026 = 0.19
W_H009 = 0.25

# ML parameters
TRAIN_MONTHS      = 120   # 10-year initial training window
PROB_THRESHOLD    = 0.45  # prob_good < 0.45 → predict bad month → hold SHY

# H020 universe
H20_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF   = "SHY"
TOP_N_H20  = 2

# H026 sector universe
SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

# H009 IBS parameters
IBS_BUY  = 0.20
IBS_SELL = 0.80
MAX_HOLD = 5

# Feature tickers
FEATURE_TICKERS = ["SPY", "^VIX", "^VIX3M", "HYG", "IEF", "SHY"]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cache_path(key: str) -> Path:
    h = hashlib.md5(key.encode()).hexdigest()[:12]
    return CACHE_DIR / f"h032_{h}.parquet"


def fetch_close(tickers: list, start: str, end: str, tag: str = "") -> pd.DataFrame:
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    cp = _cache_path(key)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {tickers} ...")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc_spy(start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print("  Downloading SPY OHLC ...")
    raw = yf.download(["SPY"], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs("SPY", axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_fred_t10y2y() -> pd.Series:
    """Load FRED 10Y-2Y yield spread. Use cached parquet if available."""
    cp = CACHE_DIR / "fred_t10y2y.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        # Handle different column name possibilities
        if "T10Y2Y" in df.columns:
            return df["T10Y2Y"].dropna()
        elif df.shape[1] == 1:
            return df.iloc[:, 0].dropna()
    # Fallback: download fresh
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=T10Y2Y"
    try:
        df = pd.read_csv(url, parse_dates=["DATE"], index_col="DATE")
        df.columns = ["T10Y2Y"]
        df = df.replace(".", np.nan).astype(float).dropna()
        df.to_parquet(cp)
        return df["T10Y2Y"]
    except Exception as e:
        print(f"  WARNING: Could not fetch FRED T10Y2Y: {e}. Returning zeros.")
        return pd.Series(dtype=float)


# ─────────────────────────────────────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets: pd.Series) -> dict:
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"error": "insufficient data"}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# H020 equity curve (copied from H031)
# ─────────────────────────────────────────────────────────────────────────────

def h020_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [a for a in H20_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H20 + 1 or CASH_ETF not in prices.columns:
        return pd.Series(dtype=float)

    px = prices[available + [CASH_ETF]].loc[start:end].dropna(how="all")
    monthly_px   = px[available].resample("ME").last()
    monthly_rets = px[available].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H20 + 1:
            continue
        combined = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top      = list(combined.nlargest(TOP_N_H20).index)
        rest     = [s for s in valid if s not in top]
        cash_wt  = len(rest) / len(valid)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px.loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += (p1 / p0 - 1) / TOP_N_H20
            if cash_wt > 0:
                p0 = float(sub[CASH_ETF].iloc[j - 1])
                p1 = float(sub[CASH_ETF].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += cash_wt * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# H026 equity curve
# ─────────────────────────────────────────────────────────────────────────────

def h026_equity_curve(prices: pd.DataFrame, start: str, end: str) -> pd.Series:
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].loc[start:end].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1
    )
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    weight = 1.0 / TOP_N_H26
    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H26:
            continue
        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N_H26).index)

        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# H009 equity curve
# ─────────────────────────────────────────────────────────────────────────────

def h009_equity_curve(ohlc: pd.DataFrame, start: str, end: str) -> pd.Series:
    df = ohlc.loc[start:end].copy()
    ibs = ((df["close"] - df["low"]) /
           (df["high"] - df["low"])).replace([np.inf, -np.inf], np.nan).fillna(0.5)

    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []

    for i in range(1, len(ibs)):
        c_prev = float(df["close"].iloc[i - 1])
        c_curr = float(df["close"].iloc[i])
        ret    = c_curr / c_prev - 1 if c_prev > 0 else 0.0

        if position == 1:
            equity   *= (1 + ret)
            days_held += 1
            if float(ibs.iloc[i]) > IBS_SELL or days_held >= MAX_HOLD:
                position = days_held = 0
        else:
            if float(ibs.iloc[i - 1]) < IBS_BUY:
                position  = 1
                days_held = 1
                equity   *= (1 + ret)

        series.append((df.index[i], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly_returns(eq_daily: pd.Series) -> pd.Series:
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Build H031 monthly return series
# ─────────────────────────────────────────────────────────────────────────────

def build_h031_monthly_returns(prices: pd.DataFrame, spy_ohlc: pd.DataFrame) -> pd.Series:
    print("\n  Building H020 equity curve ...")
    eq_h020 = h020_equity_curve(prices, FULL_START, FULL_END)
    print("  Building H026 equity curve ...")
    eq_h026 = h026_equity_curve(prices, FULL_START, FULL_END)
    print("  Building H009 daily equity curve ...")
    eq_h009 = h009_equity_curve(spy_ohlc, FULL_START, FULL_END)

    r_h020 = to_monthly_returns(eq_h020)
    r_h026 = to_monthly_returns(eq_h026)
    r_h009 = to_monthly_returns(eq_h009)

    common = r_h020.index.intersection(r_h026.index).intersection(r_h009.index)
    r_h031 = W_H020 * r_h020.loc[common] + W_H026 * r_h026.loc[common] + W_H009 * r_h009.loc[common]
    r_h031.name = "H031"
    print(f"  H031 returns: {len(r_h031)} months ({r_h031.index[0].date()} → {r_h031.index[-1].date()})")
    return r_h031, r_h020.loc[common], r_h026.loc[common], r_h009.loc[common]


# ─────────────────────────────────────────────────────────────────────────────
# Build feature matrix
# ─────────────────────────────────────────────────────────────────────────────

def build_feature_matrix(prices_all: pd.DataFrame, spy_ohlc: pd.DataFrame) -> pd.DataFrame:
    """
    Build feature matrix at monthly frequency (month-end).
    All features are known at month-end; they will be lagged 1 month before use
    in prediction (to avoid lookahead).

    Columns:
      vix          - VIX level at month-end
      vix_vix3m    - VIX / VIX3M ratio
      spy_ret_1m   - SPY 1-month return
      spy_ret_12m  - SPY 12-month return
      spread_10y2y - 10Y-2Y yield spread (FRED T10Y2Y, last trading day of month)
      spy_rvol_21d - SPY 21-day realized vol annualised
      hyg_ief_rat  - HYG / IEF ratio (credit spread proxy)
    """
    print("\n  Building feature matrix ...")

    # Monthly end-of-month prices
    spy_daily = spy_ohlc["close"].copy()
    spy_daily.index = pd.to_datetime(spy_daily.index)

    # VIX and VIX3M — try to get from prices_all
    vix   = prices_all["^VIX"].copy()  if "^VIX"   in prices_all.columns else None
    vix3m = prices_all["^VIX3M"].copy() if "^VIX3M" in prices_all.columns else None

    # HYG, IEF
    hyg = prices_all["HYG"].copy() if "HYG" in prices_all.columns else None
    ief = prices_all["IEF"].copy() if "IEF" in prices_all.columns else None
    shy = prices_all["SHY"].copy() if "SHY" in prices_all.columns else None

    # FRED T10Y2Y
    fred = fetch_fred_t10y2y()
    if not fred.empty:
        fred.index = pd.to_datetime(fred.index)
        fred_monthly = fred.resample("ME").last()
    else:
        fred_monthly = pd.Series(dtype=float)

    # SPY daily returns for realized vol
    spy_ret_daily = spy_daily.pct_change()

    # Monthly SPY prices
    spy_monthly = spy_daily.resample("ME").last()
    spy_ret_1m  = spy_monthly.pct_change()
    spy_ret_12m = spy_monthly / spy_monthly.shift(12) - 1

    # VIX monthly (month-end)
    if vix is not None:
        vix_monthly = vix.resample("ME").last()
    else:
        vix_monthly = pd.Series(dtype=float)

    # VIX3M monthly
    if vix3m is not None:
        vix3m_monthly = vix3m.resample("ME").last()
        # VIX/VIX3M ratio
        vix_vix3m = vix_monthly / vix3m_monthly
        # Clean extreme values
        vix_vix3m = vix_vix3m.clip(0.5, 2.0)
    else:
        vix_vix3m = pd.Series(dtype=float)

    # SPY realized vol: 21-day std × sqrt(252)
    spy_rvol_21d_daily = spy_ret_daily.rolling(21).std() * np.sqrt(252)
    spy_rvol_21d = spy_rvol_21d_daily.resample("ME").last()

    # HYG/IEF ratio
    if hyg is not None and ief is not None:
        hyg_monthly = hyg.resample("ME").last()
        ief_monthly = ief.resample("ME").last()
        hyg_ief_rat = hyg_monthly / ief_monthly
    else:
        hyg_ief_rat = pd.Series(dtype=float)

    # Combine into DataFrame
    feat_dict = {
        "spy_ret_1m":  spy_ret_1m,
        "spy_ret_12m": spy_ret_12m,
        "spy_rvol_21d": spy_rvol_21d,
    }
    if not vix_monthly.empty:
        feat_dict["vix"] = vix_monthly
    if not vix_vix3m.empty:
        feat_dict["vix_vix3m"] = vix_vix3m
    if not fred_monthly.empty:
        feat_dict["spread_10y2y"] = fred_monthly
    if not hyg_ief_rat.empty:
        feat_dict["hyg_ief_rat"] = hyg_ief_rat

    features = pd.DataFrame(feat_dict)
    features.index = pd.to_datetime(features.index)

    feature_cols = list(features.columns)
    print(f"  Features built: {feature_cols}")
    print(f"  Feature matrix shape: {features.shape}  ({features.index[0].date()} → {features.index[-1].date()})")

    # Report missing data
    missing = features.isna().sum()
    if missing.any():
        print(f"  Missing values per feature: {missing[missing > 0].to_dict()}")

    return features, feature_cols


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward ML validation
# ─────────────────────────────────────────────────────────────────────────────

def walk_forward_ml(
    h031_rets: pd.Series,
    features:  pd.DataFrame,
    feature_cols: list,
    shy_rets:  pd.Series,
    train_months: int = TRAIN_MONTHS,
    prob_threshold: float = PROB_THRESHOLD,
) -> dict:
    """
    Walk-forward validation.

    At each step t (starting at train_months):
      - Features at t-1 (1-month lag) are used to predict label at t
      - Label: 1 if h031_rets[t] > 0, else 0
      - Train on [0..t-1]
      - Predict label for month t using features[t-1]

    Returns dict with:
      - oos_dates, oos_labels (actual), oos_preds (RF), oos_probs (RF prob_good)
      - oos_preds_lr (LogReg)
      - h032 monthly returns (use SHY when prob_good < threshold)
      - h031 monthly returns (same OOS window for comparison)
    """
    # Align features and returns on the same monthly index
    # features at month t = features known at end of month t
    # h031_rets at month t = return earned during month t
    # For prediction: at start of month t, we know features[t-1]
    # So X for predicting month t = features[t-1], y[t] = label(h031_rets[t])

    # First, find common monthly index
    feat_filled = features[feature_cols].copy()
    feat_filled = feat_filled.ffill(limit=3)  # forward-fill up to 3 months for sparse FRED data

    common = h031_rets.index.intersection(feat_filled.dropna(how="any").index)
    common = common.sort_values()

    h031_common = h031_rets.loc[common]
    feat_common = feat_filled.loc[common]
    shy_common  = shy_rets.loc[common] if not shy_rets.empty else pd.Series(0.0, index=common)

    n = len(common)
    print(f"\n  Walk-forward window: {common[0].date()} → {common[-1].date()}  ({n} months)")
    print(f"  Training window: {train_months} months; OOS starts at month {train_months}")
    print(f"  OOS period: {common[train_months].date()} → {common[-1].date()}  ({n - train_months} months)")

    # Labels: 1 = good (H031 > 0), 0 = bad
    labels = (h031_common > 0).astype(int)

    # Walk-forward loop
    oos_indices  = []
    oos_y_true   = []
    oos_prob_rf  = []
    oos_pred_rf  = []
    oos_pred_lr  = []
    oos_prob_lr  = []

    for t in range(train_months, n):
        # Features for predicting month t = lagged 1 month = features at month t-1
        feat_train = feat_common.iloc[:t].values        # [0..t-1]
        y_train    = labels.iloc[:t].values
        feat_pred  = feat_common.iloc[t - 1].values.reshape(1, -1)  # features at t-1

        # Skip if training data has NaNs
        mask = ~np.isnan(feat_train).any(axis=1)
        if mask.sum() < 30:
            continue

        feat_train_clean = feat_train[mask]
        y_train_clean    = y_train[mask]

        # Skip degenerate cases (only one class)
        if len(np.unique(y_train_clean)) < 2:
            continue

        # Scale features
        scaler = StandardScaler()
        feat_train_scaled = scaler.fit_transform(feat_train_clean)
        feat_pred_scaled  = scaler.transform(feat_pred)

        # Random Forest
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=4,
            min_samples_leaf=10,
            max_features="sqrt",
            random_state=42,
            class_weight="balanced",
        )
        rf.fit(feat_train_scaled, y_train_clean)
        prob_rf = rf.predict_proba(feat_pred_scaled)[0]
        prob_good_rf = prob_rf[1] if rf.classes_[1] == 1 else prob_rf[0]
        pred_rf = 1 if prob_good_rf >= prob_threshold else 0

        # Logistic Regression (for comparison)
        lr = LogisticRegression(
            C=0.1, max_iter=1000, class_weight="balanced", random_state=42
        )
        lr.fit(feat_train_scaled, y_train_clean)
        prob_lr = lr.predict_proba(feat_pred_scaled)[0]
        prob_good_lr = prob_lr[1] if lr.classes_[1] == 1 else prob_lr[0]
        pred_lr = 1 if prob_good_lr >= prob_threshold else 0

        oos_indices.append(common[t])
        oos_y_true.append(int(labels.iloc[t]))
        oos_prob_rf.append(float(prob_good_rf))
        oos_pred_rf.append(int(pred_rf))
        oos_prob_lr.append(float(prob_good_lr))
        oos_pred_lr.append(int(pred_lr))

    oos_indices = pd.DatetimeIndex(oos_indices)
    oos_y_true  = np.array(oos_y_true)
    oos_prob_rf = np.array(oos_prob_rf)
    oos_pred_rf = np.array(oos_pred_rf)
    oos_prob_lr = np.array(oos_prob_lr)
    oos_pred_lr = np.array(oos_pred_lr)

    n_oos = len(oos_indices)
    print(f"\n  OOS predictions generated: {n_oos} months")

    # ── Classifier metrics ──────────────────────────────────────────────────
    def clf_metrics(y_true, y_pred, y_prob, name):
        acc  = accuracy_score(y_true, y_pred)
        prec = precision_score(y_true, y_pred, zero_division=0)
        rec  = recall_score(y_true, y_pred, zero_division=0)
        try:
            auc = roc_auc_score(y_true, y_prob)
        except Exception:
            auc = float("nan")
        n_bad_pred   = int((y_pred == 0).sum())
        n_good_pred  = int((y_pred == 1).sum())
        base_rate    = float(y_true.mean())
        print(f"\n  [{name}] Classifier metrics (OOS walk-forward):")
        print(f"    Accuracy:  {acc:.3f}  |  Base rate (% good months): {base_rate:.3f}")
        print(f"    Precision: {prec:.3f}  (when predicting good, how often right)")
        print(f"    Recall:    {rec:.3f}  (of actual good months, how many caught)")
        print(f"    ROC AUC:   {auc:.3f}")
        print(f"    Predicted BAD months: {n_bad_pred} / {n_oos}  ({n_bad_pred/n_oos:.1%})")
        print(f"    Predicted GOOD months: {n_good_pred} / {n_oos}  ({n_good_pred/n_oos:.1%})")
        return {
            "accuracy":      round(acc,  4),
            "precision":     round(prec, 4),
            "recall":        round(rec,  4),
            "roc_auc":       round(auc,  4) if not np.isnan(auc) else None,
            "base_rate":     round(base_rate, 4),
            "n_bad_predicted":  n_bad_pred,
            "n_good_predicted": n_good_pred,
            "n_oos_months":  n_oos,
        }

    rf_metrics = clf_metrics(oos_y_true, oos_pred_rf, oos_prob_rf, "RandomForest")
    lr_metrics = clf_metrics(oos_y_true, oos_pred_lr, oos_prob_lr, "LogisticReg")

    # ── H032 returns ────────────────────────────────────────────────────────
    # When RF predicts bad month → hold SHY; else → hold H031
    h031_oos = h031_common.loc[oos_indices]
    shy_oos  = shy_common.loc[oos_indices]

    # Also grab H031 and SHY for OOS period (from common index)
    h032_rets = pd.Series(
        np.where(oos_pred_rf == 0, shy_oos.values, h031_oos.values),
        index=oos_indices,
        name="H032_RF",
    )
    h032_lr_rets = pd.Series(
        np.where(oos_pred_lr == 0, shy_oos.values, h031_oos.values),
        index=oos_indices,
        name="H032_LR",
    )

    # Months when H032 switches to SHY vs H031
    switch_months_rf = oos_indices[oos_pred_rf == 0]
    switch_months_lr = oos_indices[oos_pred_lr == 0]

    # Return lift analysis: H032 vs H031 in switched months
    if len(switch_months_rf) > 0:
        h031_in_switch = h031_oos.loc[switch_months_rf]
        shy_in_switch  = shy_oos.loc[switch_months_rf]
        h031_in_good   = h031_oos.loc[oos_indices[oos_pred_rf == 1]]

        avg_h031_switch  = float(h031_in_switch.mean())
        avg_shy_switch   = float(shy_in_switch.mean())
        lift_switch      = avg_shy_switch - avg_h031_switch

        print(f"\n  RF switch-month analysis:")
        print(f"    Months switched to SHY: {len(switch_months_rf)}")
        print(f"    H031 avg return in those months: {avg_h031_switch:.4f}  ({avg_h031_switch*100:.2f}%)")
        print(f"    SHY avg return in those months:  {avg_shy_switch:.4f}   ({avg_shy_switch*100:.2f}%)")
        print(f"    Lift (SHY - H031):               {lift_switch:.4f}   ({lift_switch*100:.2f}%)")

        correct_switches = int((h031_in_switch < 0).sum())
        print(f"    H031 was actually negative in {correct_switches}/{len(switch_months_rf)} switched months")
    else:
        avg_h031_switch = 0.0
        avg_shy_switch  = 0.0
        lift_switch     = 0.0
        correct_switches = 0

    # ── Performance stats ──────────────────────────────────────────────────
    s_h031_oos = stats_from_monthly_returns(h031_oos)
    s_h032_rf  = stats_from_monthly_returns(h032_rets)
    s_h032_lr  = stats_from_monthly_returns(h032_lr_rets)
    s_shy_oos  = stats_from_monthly_returns(shy_oos)

    print(f"\n{'=' * 76}")
    print("  PERFORMANCE: H031 vs H032 (OOS period only)")
    print(f"  OOS: {oos_indices[0].date()} → {oos_indices[-1].date()}  ({n_oos} months)")
    print(f"{'=' * 76}")
    print(f"  {'Strategy':<28}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'AnnVol':>8}  {'Calmar':>8}")
    print(f"  {'-' * 76}")
    for name, s in [
        ("H031 (baseline)",  s_h031_oos),
        ("H032-RF (ML overlay)", s_h032_rf),
        ("H032-LR (LogReg overlay)", s_h032_lr),
        ("SHY (T-bill cash)", s_shy_oos),
    ]:
        print(f"  {name:<28}  {s['cagr']:>8.2%}  {s['sharpe']:>8.3f}  "
              f"{s['max_drawdown']:>8.2%}  {s['ann_vol']:>8.2%}  {s['calmar']:>8.3f}")

    # ── Feature importances (RF trained on ALL data for final model) ─────
    feat_all   = feat_common.values
    y_all      = labels.values
    mask_all   = ~np.isnan(feat_all).any(axis=1)
    feat_clean = feat_all[mask_all]
    y_clean    = y_all[mask_all]

    scaler_final = StandardScaler()
    feat_scaled  = scaler_final.fit_transform(feat_clean)
    rf_final     = RandomForestClassifier(
        n_estimators=200, max_depth=4, min_samples_leaf=10,
        max_features="sqrt", random_state=42, class_weight="balanced"
    )
    rf_final.fit(feat_scaled, y_clean)
    importances = dict(zip(feature_cols, rf_final.feature_importances_.tolist()))
    importances_sorted = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))

    print(f"\n  RF Feature Importances (trained on full period):")
    for feat, imp in importances_sorted.items():
        bar = "█" * int(imp * 40)
        print(f"    {feat:<18}  {imp:.4f}  {bar}")

    # ── Monthly series for JSON ─────────────────────────────────────────────
    monthly_records = []
    for i, dt in enumerate(oos_indices):
        monthly_records.append({
            "date":       str(dt.date()),
            "h031_ret":   round(float(h031_oos.iloc[i]), 6),
            "h032_ret":   round(float(h032_rets.iloc[i]), 6),
            "shy_ret":    round(float(shy_oos.iloc[i]), 6),
            "true_label": int(oos_y_true[i]),
            "rf_pred":    int(oos_pred_rf[i]),
            "rf_prob_good": round(float(oos_prob_rf[i]), 4),
            "lr_pred":    int(oos_pred_lr[i]),
            "lr_prob_good": round(float(oos_prob_lr[i]), 4),
            "switched":   bool(oos_pred_rf[i] == 0),
        })

    return {
        "oos_period": {
            "start": str(oos_indices[0].date()),
            "end":   str(oos_indices[-1].date()),
            "n_months": n_oos,
        },
        "classifier_rf": rf_metrics,
        "classifier_lr": lr_metrics,
        "performance": {
            "h031_oos":  s_h031_oos,
            "h032_rf":   s_h032_rf,
            "h032_lr":   s_h032_lr,
            "shy_oos":   s_shy_oos,
        },
        "switch_analysis_rf": {
            "n_months_switched":    len(switch_months_rf),
            "h031_avg_in_switch":   round(avg_h031_switch, 6),
            "shy_avg_in_switch":    round(avg_shy_switch, 6),
            "lift_per_switch":      round(lift_switch, 6),
            "correct_switches":     correct_switches,
            "switch_accuracy":      round(correct_switches / len(switch_months_rf), 4) if switch_months_rf is not None and len(switch_months_rf) > 0 else 0,
        },
        "feature_importances": importances_sorted,
        "monthly_series": monthly_records,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 76)
    print("H032 — ML Regime Classifier Overlay on H031")
    print("=" * 76)

    # ── 1. Fetch price data ────────────────────────────────────────────────
    print("\n[1] Fetching price data ...")
    all_tickers = list(set(H20_ASSETS + [CASH_ETF] + SECTOR_ETFS))
    prices = fetch_close(all_tickers, FULL_START, FULL_END, tag="h031_all")
    spy_ohlc = fetch_ohlc_spy(FULL_START, FULL_END)

    print("\n[2] Fetching feature tickers ...")
    feat_prices = fetch_close(FEATURE_TICKERS, FULL_START, FULL_END, tag="h032_features")

    # ── 2. Build H031 monthly returns ─────────────────────────────────────
    print("\n[3] Building H031 monthly return series ...")
    h031_rets, r_h020, r_h026, r_h009 = build_h031_monthly_returns(prices, spy_ohlc)

    # H031 full-period stats
    s_h031_full = stats_from_monthly_returns(h031_rets)
    print(f"\n  H031 full-period: CAGR {s_h031_full['cagr']:.2%}  Sharpe {s_h031_full['sharpe']:.3f}  MaxDD {s_h031_full['max_drawdown']:.2%}")

    # Label distribution
    n_good = int((h031_rets > 0).sum())
    n_bad  = len(h031_rets) - n_good
    print(f"  H031 label distribution: {n_good} good months ({n_good/len(h031_rets):.1%}), {n_bad} bad ({n_bad/len(h031_rets):.1%})")

    # ── 3. Build feature matrix ──────────────────────────────────────────
    print("\n[4] Building feature matrix ...")
    features, feature_cols = build_feature_matrix(feat_prices, spy_ohlc)

    # SHY returns for switching
    if "SHY" in feat_prices.columns:
        shy_monthly = feat_prices["SHY"].resample("ME").last().pct_change().dropna()
    else:
        shy_monthly = pd.Series(0.001, index=h031_rets.index)

    # ── 4. Walk-forward ML ────────────────────────────────────────────────
    print(f"\n[5] Running walk-forward ML validation ...")
    print(f"    Training window: {TRAIN_MONTHS} months  |  Prob threshold: {PROB_THRESHOLD}")
    wf_results = walk_forward_ml(
        h031_rets, features, feature_cols, shy_monthly,
        train_months=TRAIN_MONTHS, prob_threshold=PROB_THRESHOLD,
    )

    # ── 5. Full-period comparison (H031 vs H032 on same OOS window) ───────
    print(f"\n{'=' * 76}")
    print("  SUMMARY: ML Overlay Assessment")
    print(f"{'=' * 76}")

    h031_perf = wf_results["performance"]["h031_oos"]
    h032_perf = wf_results["performance"]["h032_rf"]

    delta_cagr   = h032_perf["cagr"]   - h031_perf["cagr"]
    delta_sharpe = h032_perf["sharpe"] - h031_perf["sharpe"]
    delta_maxdd  = h032_perf["max_drawdown"] - h031_perf["max_drawdown"]

    verdict = "ADDITIVE" if delta_sharpe > 0.05 else ("MARGINAL" if delta_sharpe > -0.05 else "DETRACTED")
    print(f"\n  CAGR  delta:   {delta_cagr:+.2%}  (H032-RF vs H031 OOS)")
    print(f"  Sharpe delta:  {delta_sharpe:+.3f}")
    print(f"  MaxDD  delta:  {delta_maxdd:+.2%}")
    print(f"\n  ML OVERLAY VERDICT: {verdict}")

    rf_clf = wf_results["classifier_rf"]
    print(f"\n  RF classifier OOS accuracy: {rf_clf['accuracy']:.3f}  "
          f"precision: {rf_clf['precision']:.3f}  recall: {rf_clf['recall']:.3f}  "
          f"AUC: {rf_clf.get('roc_auc', 'N/A')}")
    print(f"  Bad months called: {rf_clf['n_bad_predicted']} / {rf_clf['n_oos_months']}")

    print(f"\n  Top features by importance:")
    for feat, imp in list(wf_results["feature_importances"].items())[:4]:
        print(f"    {feat:<18}  {imp:.4f}")

    # ── 6. Save results ───────────────────────────────────────────────────
    output = {
        "strategy": "H032 — ML Regime Classifier Overlay on H031",
        "concept": (
            f"RandomForest + LogisticRegression walk-forward overlay on H031 "
            f"({W_H020:.0%} H020 / {W_H026:.0%} H026 / {W_H009:.0%} H009). "
            f"Switches to SHY when RF prob_good < {PROB_THRESHOLD}."
        ),
        "config": {
            "h031_weights": {"h020": W_H020, "h026": W_H026, "h009": W_H009},
            "train_months": TRAIN_MONTHS,
            "prob_threshold": PROB_THRESHOLD,
            "features": feature_cols,
        },
        "h031_full_period": {
            **s_h031_full,
            "n_good_months": n_good,
            "n_bad_months":  n_bad,
            "pct_good": round(n_good / len(h031_rets), 4),
        },
        "walk_forward": wf_results,
        "verdict": {
            "overlay_effect": verdict,
            "cagr_delta":   round(delta_cagr,   4),
            "sharpe_delta": round(delta_sharpe,  4),
            "maxdd_delta":  round(delta_maxdd,   4),
        },
        "run_date": FULL_END,
    }

    out_path = Path("/workspace/agent/backtesting/results/h032_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
