#!/usr/bin/env python3
"""
H473 — Neural Predicates for Data-Driven Black-Litterman Views on H026 ETF Portfolio
Source: arXiv:2607.20533 (Florencio, Jul 2026)

Replaces subjective BL view specification with neural predicates (logistic classifiers)
that generate P, q, Omega from momentum/macro signals. BL posterior weights replace
H026 top-1 allocation.

Variants:
  Var A: BL with momentum-only neural predicates (12m/3m/1m signals)
  Var B: BL with momentum + macro predicates (VIX, SPY 200MA)
  Var C: Var B + H301 SPY 200MA safety overlay (→ BIL when SPY < 200MA)
  Var D: Equal-weight BL (flat prior, no predicate — sanity check)

Gate: OOS Sharpe > 2.610 (H346 OB-filter H026 baseline) AND MaxDD not worse than -5%
IS: 2008-2020  OOS: 2021-2026
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

H026_TICKERS = [
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "XLC", "GLD", "SLV", "DBC", "USO", "TLT", "IEF", "LQD", "HYG", "EMB",
    "EFA", "EEM", "IWM", "QQQ", "BIL",
]
RISKY_TICKERS = [t for t in H026_TICKERS if t != "BIL"]

IS_START = "2008-01-01"
OOS_START, OOS_END = "2021-01-01", "2026-12-31"
TAU = 0.05


def get_all_prices() -> pd.DataFrame:
    tickers = H026_TICKERS + ["SPY", "^VIX"]
    raw = yf.download(tickers, start=IS_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.resample("ME").last().ffill()


def build_features(prices: pd.DataFrame, tickers: list, include_macro: bool = False) -> pd.DataFrame:
    r12 = prices[tickers].pct_change(12).rank(axis=1, pct=True).add_suffix("_r12")
    r3 = prices[tickers].pct_change(3).rank(axis=1, pct=True).add_suffix("_r3")
    r1 = prices[tickers].pct_change(1).rank(axis=1, pct=True).add_suffix("_r1")
    feat = pd.concat([r12, r3, r1], axis=1)
    if include_macro and "^VIX" in prices.columns and "SPY" in prices.columns:
        vix = prices["^VIX"]
        spy = prices["SPY"]
        spy_ma = spy.rolling(10).mean()
        feat["vix_norm"] = (vix - vix.rolling(24).mean()) / (vix.rolling(24).std() + 1e-6)
        feat["spy_above_200ma"] = (spy > spy_ma).astype(float)
    return feat


class NeuralPredicateBL:
    def __init__(self):
        self.models: dict = {}
        self.scaler = StandardScaler()
        self.fitted = False

    def fit(self, features: pd.DataFrame, returns: pd.DataFrame, tickers: list):
        common = features.dropna().index.intersection(returns.dropna(how="all").index)
        X = features.loc[common].fillna(0)
        R = returns.loc[common, tickers]
        next_R = R.shift(-1).loc[common]
        median_R = next_R.median(axis=1)
        feat_cols = [c for c in X.columns if not c.startswith("^")]
        Xf = self.scaler.fit_transform(X[feat_cols])
        for j, t in enumerate(tickers):
            y = (next_R[t] > median_R).dropna().astype(int)
            n = len(y)
            if n < 20:
                continue
            clf = LogisticRegression(C=1.0, max_iter=500, random_state=42)
            clf.fit(Xf[:n], y.values)
            self.models[t] = clf
        self.fitted = True

    def predict_views(self, feat_row: pd.Series, tickers: list):
        feat_cols = [c for c in feat_row.index if not c.startswith("^")]
        x = feat_row[feat_cols].fillna(0).values.reshape(1, -1)
        x_scaled = self.scaler.transform(x)
        q = pd.Series(0.0, index=tickers)
        omega_diag = pd.Series(0.1, index=tickers)
        for t in tickers:
            if t not in self.models:
                continue
            prob = self.models[t].predict_proba(x_scaled)[0][1]
            q[t] = (prob - 0.5) * 0.06
            omega_diag[t] = max(0.001, prob * (1 - prob))
        return q, omega_diag

    def bl_weights(self, cov: pd.DataFrame, tickers: list, q: pd.Series,
                   omega_diag: pd.Series, risk_aversion: float = 3.0) -> pd.Series:
        n = len(tickers)
        Sigma = cov.loc[tickers, tickers].values + 1e-6 * np.eye(n)
        pi = risk_aversion * Sigma @ np.ones(n) / n
        tau_sigma_inv = np.linalg.inv(TAU * Sigma)
        Omega_inv = np.diag(1.0 / (omega_diag[tickers].values + 1e-8))
        posterior_prec = tau_sigma_inv + Omega_inv
        posterior_mean = np.linalg.solve(
            posterior_prec, tau_sigma_inv @ pi + Omega_inv @ q[tickers].values
        )
        w = np.linalg.solve(risk_aversion * Sigma, posterior_mean)
        w = np.maximum(w, 0)
        return pd.Series(w / w.sum() if w.sum() > 0 else np.ones(n) / n, index=tickers)


def run_backtest(variant: str, prices: pd.DataFrame) -> dict:
    print(f"\n=== H473 {variant} | H026 BL Neural Predicates ===")
    rets = prices[H026_TICKERS].pct_change().dropna(how="all")
    tickers = RISKY_TICKERS
    include_macro = variant in ("B", "C")
    features = build_features(prices, tickers, include_macro)

    is_end = pd.Timestamp("2020-12-31")
    is_idx = rets.index[rets.index <= is_end]

    if variant != "D":
        predictor = NeuralPredicateBL()
        predictor.fit(features.loc[is_idx], rets.loc[is_idx], tickers)
    else:
        predictor = None

    oos_rets_list = []
    for i, date in enumerate(rets.index):
        if date < pd.Timestamp(OOS_START):
            continue
        history = rets.iloc[:i]
        if len(history) < 24:
            continue

        if variant == "C":
            spy = prices["SPY"].iloc[:i + 1]
            if spy.iloc[-1] < spy.rolling(10).mean().iloc[-1]:
                oos_rets_list.append({"date": date, "ret": rets.loc[date, "BIL"]})
                continue

        if predictor is None or variant == "D":
            w = pd.Series(1.0 / len(tickers), index=tickers)
        else:
            feat_row = features.loc[date] if date in features.index else features.iloc[-1]
            q, omega = predictor.predict_views(feat_row, tickers)
            cov = history[tickers].tail(36).cov()
            w = predictor.bl_weights(cov, tickers, q, omega)

        actual = rets.loc[date, tickers].fillna(0)
        port_ret = (w * actual).sum()
        oos_rets_list.append({"date": date, "ret": port_ret})

    if not oos_rets_list:
        return {}
    oos = pd.DataFrame(oos_rets_list).set_index("date")["ret"]
    sharpe = oos.mean() / oos.std() * np.sqrt(12) if oos.std() > 0 else 0
    cum = (1 + oos).cumprod()
    max_dd = ((cum.cummax() - cum) / cum.cummax()).max()
    cagr = cum.iloc[-1] ** (12 / len(oos)) - 1
    neg_years = sum(1 for yr, g in oos.groupby(oos.index.year) if g.sum() < 0)
    print(f"  OOS Sharpe: {sharpe:.3f}  MaxDD: {-max_dd:.1%}  CAGR: {cagr:.1%}  NegYrs: {neg_years}")
    return {"sharpe": sharpe, "max_dd": max_dd, "cagr": cagr, "neg_years": neg_years}


if __name__ == "__main__":
    print("Downloading data...")
    prices = get_all_prices()
    results = {v: run_backtest(v, prices) for v in ["A", "B", "C", "D"]}

    print("\n=== H473 Summary ===")
    gate = 2.610
    for name, r in results.items():
        if r:
            passed = r["sharpe"] > gate and r["max_dd"] < 0.05
            print(f"  Var {name}: Sharpe={r['sharpe']:.3f}  MaxDD={-r['max_dd']:.1%}  "
                  f"{'PASS' if passed else 'FAIL'} (gate>{gate})")
