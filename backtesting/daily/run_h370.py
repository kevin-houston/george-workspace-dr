#!/usr/bin/env python3
"""
H370 — LambdaRankIC: Direct IC Optimization on H198 30-Stock Universe
=======================================================================
Source: arXiv:2605.00501 (Lin, Su & Yang, May 2026)

Hypothesis: Replacing MSE regression objective with a custom lambda-gradient
objective that directly maximizes Spearman Rank IC across monthly
cross-sections improves OOS return prediction vs H198's plain 6-1m momentum.

Baseline to beat: H198 6-1m momentum, OOS Sharpe 1.174
Gate: OOS Sharpe > 1.174 (H198 baseline) AND OOS Rank IC > 0.05
IS:  2013-2020
OOS: 2021-2026

Features (per stock, per month-end):
  - 6-1m momentum (H198 core signal, skip most recent month)
  - 3m momentum
  - 12m momentum
  - 1m return (skip-month indicator)
  - Alpha101 signal, monthly-median aggregated (H217 confirmed OOS 1.559):
    (close - open) / (0.001 + high - low), clipped to [-1, 1]

Method: XGBoost with a custom lambda-gradient objective approximating
LambdaRankIC — a pairwise objective whose gradient pushes predictions toward
maximizing Spearman rank correlation with realized next-month returns, rather
than minimizing squared error. Trained via expanding-window monthly
walk-forward: at each OOS month, refit on all data up to t-1, predict month t,
rank stocks by predicted score, and long top-1 (matching H198 production
logic) plus a top-3 variant for lower concentration risk.
"""

import warnings
warnings.filterwarnings("ignore")
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import yfinance as yf
from scipy.stats import spearmanr

WORKSPACE = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

H198_UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]

DATA_START = "2012-01-01"
DATA_END = "2026-07-31"
IS_START = pd.Timestamp("2013-01-01")
IS_END = pd.Timestamp("2020-12-31")
OOS_START = pd.Timestamp("2021-01-01")
OOS_END = pd.Timestamp("2026-07-31")

GATE_SHARPE = 1.174
GATE_IC = 0.05
MIN_TRAIN_MONTHS = 24  # need at least 2 years of monthly cross-sections before first OOS prediction


def fetch_daily(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h370_{ticker}_daily.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}...")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df.to_parquet(cp)
    return df


def compute_alpha101_monthly(df: pd.DataFrame) -> pd.Series:
    a = (df["close"] - df["open"]) / (0.001 + df["high"] - df["low"])
    a = a.clip(-1, 1)
    return a.resample("MS").median()


def build_features(daily_data: dict) -> pd.DataFrame:
    """Build a long-format DataFrame: rows = (date, ticker), columns = features + fwd_ret."""
    monthly_close = pd.DataFrame({t: d["close"].resample("MS").last() for t, d in daily_data.items()})
    monthly_close = monthly_close.sort_index()
    alpha101 = pd.DataFrame({t: compute_alpha101_monthly(d) for t, d in daily_data.items()})
    alpha101 = alpha101.reindex(monthly_close.index)

    rows = []
    idx = monthly_close.index
    for i in range(12, len(idx) - 1):
        dt = idx[i]
        p_now = monthly_close.iloc[i]
        p_1m = monthly_close.iloc[i - 1]
        p_3m = monthly_close.iloc[i - 3]
        p_6m = monthly_close.iloc[i - 6]
        p_12m = monthly_close.iloc[i - 12]
        fwd_ret = monthly_close.iloc[i + 1] / p_now - 1

        r6_skip = (p_now / p_6m - 1) - (p_now / p_1m - 1)
        r3 = p_now / p_3m - 1
        r12 = p_now / p_12m - 1
        r1 = p_now / p_1m - 1
        a101 = alpha101.iloc[i]

        for t in monthly_close.columns:
            if pd.isna(r6_skip[t]) or pd.isna(fwd_ret[t]):
                continue
            rows.append({
                "date": dt, "ticker": t,
                "mom_6_1": r6_skip[t], "mom_3": r3[t], "mom_12": r12[t], "ret_1m": r1[t],
                "alpha101": a101[t] if not pd.isna(a101[t]) else 0.0,
                "fwd_ret": fwd_ret[t],
            })
    return pd.DataFrame(rows)


def lambdarankic_objective_factory():
    """
    Approximate LambdaRankIC pairwise gradient (arXiv:2605.00501).
    For each pair (i, j) in a cross-section where true rank(y_i) > rank(y_j),
    push pred_i > pred_j. Gradient magnitude scaled by |rank_i - rank_j| swap
    contribution to Spearman rho (NDCG-style lambda weighting), applied per
    monthly group. Simplified O(n^2) pairwise lambda per group, tractable at
    n<=30 stocks/month.
    """
    def obj(preds, dtrain):
        y = dtrain.get_label()
        grad = np.zeros_like(preds)
        hess = np.ones_like(preds) * 1e-6

        for (start, end) in dtrain.custom_group_boundaries:
            p = preds[start:end]
            yy = y[start:end]
            n = len(p)
            if n < 2:
                continue
            true_rank = pd.Series(yy).rank().values
            for a in range(n):
                for b in range(a + 1, n):
                    if true_rank[a] == true_rank[b]:
                        continue
                    sign = 1.0 if true_rank[a] > true_rank[b] else -1.0
                    delta_rank = abs(true_rank[a] - true_rank[b]) / n
                    sigma = 1.0 / (1.0 + np.exp(-(p[a] - p[b])))
                    g = -sign * (1 - sigma) * delta_rank
                    grad[start + a] += g
                    grad[start + b] -= g
                    h = sigma * (1 - sigma) * delta_rank + 1e-6
                    hess[start + a] += h
                    hess[start + b] += h
        return grad, hess
    return obj


def train_predict_walkforward(feat_df: pd.DataFrame):
    """Expanding-window walk-forward: refit monthly, predict next cross-section."""
    dates = sorted(feat_df["date"].unique())
    feature_cols = ["mom_6_1", "mom_3", "mom_12", "ret_1m", "alpha101"]

    preds_by_date = {}

    for i, dt in enumerate(dates):
        if i < MIN_TRAIN_MONTHS:
            continue
        train_dates = dates[:i]  # expanding window, all data strictly before dt
        train_df = feat_df[feat_df["date"].isin(train_dates)].copy()
        test_df = feat_df[feat_df["date"] == dt].copy()
        if len(test_df) < 5 or len(train_df) < 100:
            continue

        train_df = train_df.sort_values("date")
        group_sizes = train_df.groupby("date").size().values
        boundaries = []
        pos = 0
        for gs in group_sizes:
            boundaries.append((pos, pos + gs))
            pos += gs

        dtrain = xgb.DMatrix(train_df[feature_cols].values, label=train_df["fwd_ret"].values)
        dtrain.custom_group_boundaries = boundaries

        params = {"max_depth": 3, "eta": 0.1, "lambda": 1.0}
        try:
            bst = xgb.train(params, dtrain, num_boost_round=40, obj=lambdarankic_objective_factory())
            dtest = xgb.DMatrix(test_df[feature_cols].values)
            scores = bst.predict(dtest)
        except Exception as e:
            print(f"    [warn] {dt}: {e}")
            continue

        test_df = test_df.copy()
        test_df["score"] = scores
        preds_by_date[dt] = test_df[["ticker", "score", "fwd_ret"]].set_index("ticker")

    return preds_by_date


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0


def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)].dropna()
    if len(r) < 6:
        return {"n": 0, "sharpe": 0, "cagr": 0, "maxdd": 0, "neg_yrs": 0}
    cagr = float((1 + r).prod() ** (12 / len(r)) - 1)
    return {
        "n": len(r), "sharpe": round(sharpe(r), 3), "cagr": round(cagr, 3),
        "maxdd": round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0)),
    }


def main():
    print("=== H370: LambdaRankIC Direct IC Optimization on H198 Universe ===")
    print(f"IS: {IS_START.date()}–{IS_END.date()} | OOS: {OOS_START.date()}–{OOS_END.date()}")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND OOS Rank IC > {GATE_IC}\n")

    print("Downloading daily OHLC for H198 universe...")
    daily_data = {}
    for t in H198_UNIVERSE:
        try:
            df = fetch_daily(t)
            if len(df) > 500:
                daily_data[t] = df
        except Exception as e:
            print(f"  {t} failed: {e}")
    print(f"Loaded {len(daily_data)}/{len(H198_UNIVERSE)} tickers\n")

    print("Building monthly feature panel...")
    feat_df = build_features(daily_data)
    print(f"Feature panel: {len(feat_df)} rows, {feat_df['date'].nunique()} months\n")

    print("Running expanding-window walk-forward LambdaRankIC training...")
    preds_by_date = train_predict_walkforward(feat_df)
    print(f"Generated predictions for {len(preds_by_date)} months\n")

    baseline_rets, baseline_dates = [], []
    top1_rets, top1_dates = [], []
    top3_rets, top3_dates = [], []
    ic_list = []

    for dt in sorted(preds_by_date.keys()):
        block = preds_by_date[dt]
        if len(block) >= 5:
            ic, _ = spearmanr(block["score"], block["fwd_ret"])
            if not np.isnan(ic):
                ic_list.append((dt, ic))

        ranked = block.sort_values("score", ascending=False)
        top1_rets.append(ranked["fwd_ret"].iloc[0])
        top1_dates.append(dt)
        top3_rets.append(ranked["fwd_ret"].iloc[:3].mean())
        top3_dates.append(dt)

        month_feat = feat_df[feat_df["date"] == dt].set_index("ticker")
        base_ranked = month_feat.sort_values("mom_6_1", ascending=False)
        baseline_rets.append(base_ranked["fwd_ret"].iloc[0])
        baseline_dates.append(dt)

    top1_series = pd.Series(top1_rets, index=pd.to_datetime(top1_dates)).sort_index()
    top3_series = pd.Series(top3_rets, index=pd.to_datetime(top3_dates)).sort_index()
    baseline_series = pd.Series(baseline_rets, index=pd.to_datetime(baseline_dates)).sort_index()
    ic_series = pd.Series({pd.Timestamp(d): v for d, v in ic_list}).sort_index()

    print("=== Results ===")
    results = {}
    for label, series in [("LambdaRankIC_top1", top1_series),
                           ("LambdaRankIC_top3", top3_series),
                           ("momentum_baseline_top1", baseline_series)]:
        is_stats = eval_period(series, IS_START, IS_END)
        oos_stats = eval_period(series, OOS_START, OOS_END)
        oos_ic = ic_series[(ic_series.index >= OOS_START) & (ic_series.index <= OOS_END)]
        oos_ic_mean = float(oos_ic.mean()) if len(oos_ic) > 0 else 0.0
        print(f"{label}: IS Sharpe={is_stats['sharpe']}, OOS Sharpe={oos_stats['sharpe']}, "
              f"OOS MaxDD={oos_stats['maxdd']:.1%}, OOS IC={oos_ic_mean:.4f}, NegYrs={oos_stats['neg_yrs']}")
        results[label] = {"is": is_stats, "oos": oos_stats, "oos_rank_ic": round(oos_ic_mean, 4)}

    print(f"\n=== Gate Check (OOS Sharpe > {GATE_SHARPE} AND OOS Rank IC > {GATE_IC}) ===")
    confirmed = []
    for label in ["LambdaRankIC_top1", "LambdaRankIC_top3"]:
        s = results[label]["oos"]["sharpe"]
        ic = results[label]["oos_rank_ic"]
        passed = (s > GATE_SHARPE) and (ic > GATE_IC)
        print(f"  {label}: OOS Sharpe={s} ({'PASS' if s > GATE_SHARPE else 'FAIL'}), "
              f"OOS IC={ic} ({'PASS' if ic > GATE_IC else 'FAIL'}) => {'CONFIRMED' if passed else 'FAIL'}")
        if passed:
            confirmed.append(label)

    out = {
        "hypothesis": "H370",
        "description": "LambdaRankIC direct IC optimization on H198 30-stock universe",
        "gate": {"oos_sharpe": GATE_SHARPE, "oos_rank_ic": GATE_IC},
        "results": results,
        "confirmed_variants": confirmed,
        "verdict": "CONFIRMED" if confirmed else "NOT CONFIRMED",
        "n_months_predicted": len(preds_by_date),
    }
    outpath = RESULT_DIR / "h370_results.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nResults saved to {outpath}")
    print(f"\nVERDICT: {out['verdict']}")

    top1_series.to_csv(RESULT_DIR / "h370_top1_returns.csv", header=["ret"])
    top3_series.to_csv(RESULT_DIR / "h370_top3_returns.csv", header=["ret"])


if __name__ == "__main__":
    main()
