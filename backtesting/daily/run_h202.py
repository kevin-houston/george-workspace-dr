"""
H202 — ML-Enhanced Cross-Sectional Momentum with Bias Correction
================================================================
§arXiv:2507.07107: bias elimination mask contributes +0.44 Sharpe-point,
exceeding the contribution from model architecture choice.

Hypothesis: XGBoost with bias mask outperforms simple 6-1m rank (H198, OOS Sharpe 1.174)
on the same 30-stock S&P 500 universe.

Variants:
  A — Baseline: simple 6-1m return rank (H198 reproduction)
  B — Bias-masked: same signal but exclude stocks with extreme short-term moves
      (|prior_month_return| > 25%, or vol_ratio > 2.5) — these are likely biased
      by corporate events, data errors, or regime breaks
  C — XGBoost signal: 8 features, trained IS-only, predict forward return rank
      Features: mom_6_1, mom_12_1, mom_3_1, rev_1m, vol_12m, vol_1m,
                vol_change (vol_1m/vol_12m), mom_risk_adj (mom_6_1/vol_12m)

IS: 2013–2020   OOS: 2021–2026   Universe: same 30 S&P 500 stocks as H198
Confirm: OOS Sharpe > 1.474 (= H198 1.174 + 0.30 conservative bias-mask lift)
Secondary: any variant beats H198 OOS Sharpe

IMPORTANT: strict temporal cutoff — all features at month t use only data ≤ t-1
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

try:
    from xgboost import XGBRegressor
    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    print("WARNING: xgboost not installed — Variant C will be skipped")

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2010-01-01"   # extra history for 12m lookback + IS warm-up
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N    = 6
TC_BPS   = 5


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 204)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    # try the h198 cache with original dates
    for date_suffix in ["2011-01-01_2026-04-30", "2010-01-01_2026-04-30"]:
        cp = CACHE_DIR / f"h198_{ticker}_monthly_{date_suffix}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h202_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r: pd.Series) -> int:
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cumul": 1.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 12), 4),
        "cumul":   round(cumul(r), 4),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


def build_features(prices: pd.DataFrame, month_idx: int) -> pd.DataFrame:
    """
    Build feature matrix for all stocks at decision point `month_idx`.
    All features use strictly historical data (data[0..month_idx-1]).
    Returns DataFrame with index=ticker, columns=features.
    """
    monthly_ret = prices.pct_change()
    t = month_idx  # current month index (returns realized this month = future)

    if t < 14:
        return pd.DataFrame()

    rows = {}
    for tkr in prices.columns:
        p = prices[tkr]
        r = monthly_ret[tkr]

        # --- price at t-1 and earlier ---
        if pd.isna(p.iloc[t-1]) or pd.isna(p.iloc[t-13]):
            continue

        # mom_6_1: 6-month return skipping last month
        mom_6_1 = (p.iloc[t-1] / p.iloc[t-7] - 1) if not pd.isna(p.iloc[t-7]) else np.nan
        # mom_12_1: 12-month return skipping last month
        mom_12_1 = (p.iloc[t-1] / p.iloc[t-13] - 1) if t >= 14 and not pd.isna(p.iloc[t-13]) else np.nan
        # mom_3_1: 3-month return skipping last month
        mom_3_1 = (p.iloc[t-1] / p.iloc[t-4] - 1) if t >= 5 and not pd.isna(p.iloc[t-4]) else np.nan
        # rev_1m: last month return (expect reversal)
        rev_1m = r.iloc[t-1] if not pd.isna(r.iloc[t-1]) else np.nan

        # vol_12m: annualized 12-month realized vol (past 12 monthly returns)
        past_12 = r.iloc[max(0, t-13):t-1]  # up to but not including last month
        vol_12m = float(past_12.std() * np.sqrt(12)) if len(past_12) >= 6 else np.nan

        # vol_1m: last month absolute return as proxy for recent vol
        vol_1m = abs(rev_1m) if not pd.isna(rev_1m) else np.nan

        # vol_change: recent vol vs long-run vol
        vol_change = (vol_1m / vol_12m - 1) if (vol_12m and vol_12m > 0) else np.nan

        # mom_risk_adj: risk-adjusted momentum
        mom_risk_adj = (mom_6_1 / vol_12m) if (vol_12m and vol_12m > 0 and not pd.isna(mom_6_1)) else np.nan

        rows[tkr] = {
            "mom_6_1":     mom_6_1,
            "mom_12_1":    mom_12_1,
            "mom_3_1":     mom_3_1,
            "rev_1m":      rev_1m,
            "vol_12m":     vol_12m,
            "vol_1m":      vol_1m,
            "vol_change":  vol_change,
            "mom_risk_adj": mom_risk_adj,
        }

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).T


def bias_mask(feat: pd.DataFrame) -> pd.Index:
    """
    Return index of stocks that PASS the bias filter (should be included).
    Excludes:
      - Stocks with any NaN in core features
      - Stocks with |rev_1m| > 0.25 (>25% last-month move = likely corporate event)
      - Stocks with vol_change > 2.5 (vol explosion = regime break)
    """
    if feat.empty:
        return pd.Index([])
    ok = feat.dropna(subset=["mom_6_1", "rev_1m", "vol_12m"])
    ok = ok[ok["rev_1m"].abs() <= 0.25]
    ok = ok[ok["vol_change"].fillna(0) <= 2.5]
    return ok.index


# ─── Variant A: simple 6-1m rank (H198 baseline reproduction) ────────────────

def backtest_A(prices: pd.DataFrame) -> pd.Series:
    """Simple 6-1m rank, no bias mask."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]
    for i, month_end in enumerate(months):
        loc = prices.index.get_loc(month_end)
        if loc < 8:
            continue
        sig = prices.iloc[loc-1] / prices.iloc[loc-7] - 1  # 6-1m
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        selected = sig.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ─── Variant B: bias-masked 6-1m rank ───────────────────────────────────────

def backtest_B(prices: pd.DataFrame) -> pd.Series:
    """6-1m rank with bias mask applied before selection."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = prices.index[prices.index >= IS_START]
    for i, month_end in enumerate(months):
        loc = prices.index.get_loc(month_end)
        if loc < 14:
            continue
        feat = build_features(prices, loc)
        if feat.empty:
            continue
        valid = bias_mask(feat)
        if len(valid) < TOP_N:
            continue
        sig = feat.loc[valid, "mom_6_1"].dropna()
        if len(sig) < TOP_N:
            continue
        selected = sig.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ─── Variant C: XGBoost signal ──────────────────────────────────────────────

FEATURE_COLS = ["mom_6_1", "mom_12_1", "mom_3_1", "rev_1m",
                "vol_12m", "vol_1m", "vol_change", "mom_risk_adj"]


def backtest_C(prices: pd.DataFrame) -> pd.Series:
    """XGBoost trained on IS, predict forward return rank each month."""
    if not HAS_XGB:
        return pd.Series(dtype=float)

    monthly_ret = prices.pct_change()

    # ── Phase 1: build IS training set ──────────────────────────────────────
    X_train, y_train = [], []
    all_months = prices.index

    for loc in range(14, len(all_months)):
        month_end = all_months[loc]
        # training only on IS months where we also know the forward return
        if not (IS_START <= month_end <= IS_END):
            continue
        if loc + 1 >= len(all_months):
            continue

        feat = build_features(prices, loc)
        if feat.empty:
            continue
        valid = bias_mask(feat)
        feat_valid = feat.loc[feat.index.intersection(valid)][FEATURE_COLS].dropna()
        if len(feat_valid) < TOP_N:
            continue

        # forward 1-month return = target
        fwd_ret = monthly_ret.iloc[loc + 1].reindex(feat_valid.index)
        # target: rank of forward return (higher = better), normalized 0-1
        rank = fwd_ret.rank(ascending=True, pct=True)
        if rank.isna().all():
            continue

        for tkr in feat_valid.index:
            if pd.notna(rank.get(tkr)):
                X_train.append(feat_valid.loc[tkr].values)
                y_train.append(float(rank[tkr]))

    if len(X_train) < 50:
        print("  WARNING: insufficient IS training samples for XGBoost")
        return pd.Series(dtype=float)

    X_arr = np.array(X_train)
    y_arr = np.array(y_train)

    model = XGBRegressor(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbosity=0,
    )
    model.fit(X_arr, y_arr)
    print(f"  XGBoost trained on {len(X_train)} IS samples ({X_arr.shape[1]} features)")

    # ── Phase 2: apply model OOS ─────────────────────────────────────────────
    port_rets = []
    for loc in range(14, len(all_months)):
        month_end = all_months[loc]
        if not (month_end >= IS_START):
            continue

        feat = build_features(prices, loc)
        if feat.empty:
            continue
        valid = bias_mask(feat)
        feat_valid = feat.loc[feat.index.intersection(valid)][FEATURE_COLS].dropna()
        if len(feat_valid) < TOP_N:
            continue

        scores = model.predict(feat_valid.values)
        score_s = pd.Series(scores, index=feat_valid.index)
        selected = score_s.nlargest(TOP_N).index.tolist()
        ret = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H202 — ML-Enhanced Cross-Sectional Momentum with Bias Correction")
    print("=" * 68)

    # ── Load prices ──────────────────────────────────────────────────────────
    print("Loading price data…")
    price_list = []
    for t in UNIVERSE:
        try:
            price_list.append(fetch_price(t))
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(price_list).T.sort_index()
    prices = prices.loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers, {len(prices)} monthly bars")

    spy_path = CACHE_DIR / f"h198_SPY_monthly_2011-01-01_2026-04-30.parquet"
    if not spy_path.exists():
        spy_path = CACHE_DIR / f"h202_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_path.exists():
        spy_px = pd.read_parquet(spy_path).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_path)
    spy_ret = spy_px.pct_change().dropna()
    spy_oos = eval_period(spy_ret, OOS_START, OOS_END)

    results = {}

    # ── Variant A ─────────────────────────────────────────────────────────────
    print("\nVariant A — Simple 6-1m rank (H198 baseline)…")
    rets_A = backtest_A(prices)
    results["A"] = {
        "label": "Simple 6-1m rank",
        "is":  eval_period(rets_A, IS_START, IS_END),
        "oos": eval_period(rets_A, OOS_START, OOS_END),
        "rets": rets_A,
    }

    # ── Variant B ─────────────────────────────────────────────────────────────
    print("Variant B — Bias-masked 6-1m rank…")
    rets_B = backtest_B(prices)
    results["B"] = {
        "label": "Bias-masked 6-1m rank",
        "is":  eval_period(rets_B, IS_START, IS_END),
        "oos": eval_period(rets_B, OOS_START, OOS_END),
        "rets": rets_B,
    }

    # ── Variant C ─────────────────────────────────────────────────────────────
    print("Variant C — XGBoost multi-factor signal…")
    rets_C = backtest_C(prices)
    if len(rets_C) > 0:
        results["C"] = {
            "label": "XGBoost multi-factor",
            "is":  eval_period(rets_C, IS_START, IS_END),
            "oos": eval_period(rets_C, OOS_START, OOS_END),
            "rets": rets_C,
        }

    # ── Print results ─────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"{'Variant':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}")
    print("-" * 80)
    for key, r in results.items():
        is_, oos_ = r["is"], r["oos"]
        print(f"{r['label']:<30} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    is_s  = results["A"]["is"]["sharpe"]
    oos_s = results["A"]["oos"]["sharpe"]
    print(f"{'SPY benchmark':<30} {eval_period(spy_ret, IS_START, IS_END)['sharpe']:>10.3f} "
          f"{'':>10} {spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f}")

    # ── Correlation analysis ──────────────────────────────────────────────────
    print("\n=== Correlation (OOS) ===")
    for key, r in results.items():
        rets = r["rets"]
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        corr_spy = oos_rets.corr(spy_ret.reindex(oos_rets.index))
        corr_A = ""
        if key != "A":
            a_rets = results["A"]["rets"]
            a_oos = a_rets[(a_rets.index >= OOS_START) & (a_rets.index <= OOS_END)]
            corr_a = oos_rets.corr(a_oos.reindex(oos_rets.index))
            corr_A = f", corr(A)={corr_a:.3f}"
        print(f"  {key} ({r['label']}): corr(SPY)={corr_spy:.3f}{corr_A}")

    # ── Bias mask statistics ──────────────────────────────────────────────────
    print("\n=== Bias mask exclusion stats ===")
    excluded_months = []
    months = prices.index[prices.index >= IS_START]
    for month_end in months:
        loc = prices.index.get_loc(month_end)
        if loc < 14:
            continue
        feat = build_features(prices, loc)
        if feat.empty:
            continue
        all_stocks = len(feat.dropna(subset=["mom_6_1"]))
        valid = len(bias_mask(feat))
        excluded = all_stocks - valid
        if excluded > 0:
            excluded_months.append(excluded)
    if excluded_months:
        print(f"  Months with exclusions: {len(excluded_months)}/{len(months)}")
        print(f"  Avg stocks excluded per month: {np.mean(excluded_months):.1f}")
        print(f"  Max stocks excluded in one month: {max(excluded_months)}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    h198_oos_sharpe = 1.174  # confirmed baseline
    confirm_threshold = h198_oos_sharpe + 0.30  # conservative: 1.474

    print("\n=== Verdict ===")
    print(f"H198 baseline OOS Sharpe: {h198_oos_sharpe:.3f}")
    print(f"Confirm threshold: {confirm_threshold:.3f}")
    for key, r in results.items():
        oos_sharpe = r["oos"]["sharpe"]
        beats_h198 = oos_sharpe > h198_oos_sharpe
        confirmed  = oos_sharpe > confirm_threshold
        print(f"  {key} ({r['label']}): OOS Sharpe {oos_sharpe:.3f} — "
              f"{'beats H198' if beats_h198 else 'below H198'}, "
              f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── Save results ──────────────────────────────────────────────────────────
    out = {
        "hypothesis": "H202",
        "description": "ML-Enhanced Momentum with Bias Correction vs H198 baseline",
        "h198_baseline_oos_sharpe": h198_oos_sharpe,
        "confirm_threshold": confirm_threshold,
        "variants": {
            k: {"label": v["label"], "is": v["is"], "oos": v["oos"]}
            for k, v in results.items()
        },
        "spy_oos": spy_oos,
        "bias_mask_avg_exclusions": round(float(np.mean(excluded_months)), 2) if excluded_months else 0,
    }
    outpath = RESULT_DIR / "h202_ml_momentum_bias.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
