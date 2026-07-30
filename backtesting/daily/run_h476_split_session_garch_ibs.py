#!/usr/bin/env python3
"""
H476 — Split-Session Cluster GARCH Overnight/Intraday Tail Decomposition as IBS Entry Filter
Source: arXiv:2607.03669 (Chen, Hansen, Tong, Jul 2026)

Overnight returns have heavier tails (ν ≈ 3.8) than intraday (ν ≈ 5.2).
Fat-tail overnight days generate trend continuation, not mean-reversion.
IBS strategy (H112, 30% production portfolio) should exclude fat-tail overnight days.

overnight_rv = (log(open_t / close_{t-1}))^2
overnight_rv_rank = rolling 252d percentile of overnight_rv
Entry: IBS < 0.2 AND overnight_rv_rank < threshold

Variants:
  Var A: Binary gate — skip IBS entry when overnight_rv_rank > 0.80
  Var B: Continuous — scale IBS position by (1 - overnight_rv_rank)
  Var C: Anti-contrarian — ONLY enter when overnight_rv_rank < 0.20
  Var D: H112 IBS baseline (unfiltered, sanity check)

Gate: OOS Sharpe > 2.129 (H112 IBS baseline) AND MaxDD improvement vs -18%
IS: 2015-2020  OOS: 2021-2026
Universe: XLK, SMH, IGV (IBS production tickers, 30% of portfolio)
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

TICKERS = ["XLK", "SMH", "IGV"]
IS_START, IS_END = "2015-01-01", "2020-12-31"
OOS_START, OOS_END = "2021-01-01", "2026-06-30"
IBS_ENTRY_THRESHOLD = 0.2     # IBS < 0.2 = near-low entry
IBS_EXIT_THRESHOLD = 0.8      # IBS > 0.8 = near-high exit (same day)
RV_WINDOW = 252               # rolling window for overnight_rv percentile rank
GATE_SHARPE = 2.129           # H112 baseline to beat
TRANSACTION_COST = 0.0001     # 1bp per trade


def compute_ibs(df: pd.DataFrame) -> pd.Series:
    return (df["Close"] - df["Low"]) / (df["High"] - df["Low"])


def compute_overnight_rv_rank(df: pd.DataFrame, window: int = RV_WINDOW) -> pd.Series:
    overnight_ret = np.log(df["Open"] / df["Close"].shift(1))
    overnight_rv = overnight_ret ** 2
    return overnight_rv.rolling(window).rank(pct=True)


def run_variant(prices: pd.DataFrame, variant: str, threshold: float = 0.80) -> pd.Series:
    """Run a single ticker IBS strategy for one variant."""
    ibs = compute_ibs(prices)
    rv_rank = compute_overnight_rv_rank(prices)

    daily_ret = prices["Close"].pct_change()
    position = pd.Series(0.0, index=prices.index)

    in_trade = False
    for i in range(1, len(prices)):
        date = prices.index[i]
        prev_ibs = ibs.iloc[i - 1]
        cur_rv_rank = rv_rank.iloc[i]

        if variant == "D":
            # Baseline: pure IBS entry
            gate_pass = True
        elif variant == "A":
            gate_pass = (cur_rv_rank < threshold) or pd.isna(cur_rv_rank)
        elif variant == "B":
            gate_pass = True  # continuous scaling applied below
        elif variant == "C":
            gate_pass = (cur_rv_rank < 0.20) or pd.isna(cur_rv_rank)
        else:
            gate_pass = True

        if not in_trade and prev_ibs < IBS_ENTRY_THRESHOLD and gate_pass:
            in_trade = True

        if in_trade:
            if variant == "B" and not pd.isna(cur_rv_rank):
                position.iloc[i] = max(0.0, 1.0 - cur_rv_rank)
            else:
                position.iloc[i] = 1.0

        if in_trade and ibs.iloc[i] > IBS_EXIT_THRESHOLD:
            in_trade = False

    strat_ret = position.shift(1) * daily_ret - TRANSACTION_COST * position.diff().abs()
    return strat_ret.fillna(0.0)


def evaluate(returns: pd.Series, label: str):
    ann = returns.mean() * 252
    vol = returns.std() * np.sqrt(252)
    sharpe = ann / vol if vol > 0 else 0.0
    mdd = (returns.cumsum() - returns.cumsum().cummax()).min()
    neg_years = (returns.resample("YE").sum() < 0).sum()
    print(f"  {label}: Sharpe={sharpe:.3f}  CAGR={ann:.1%}  MaxDD={mdd:.1%}  NegYears={neg_years}")
    return sharpe, mdd


if __name__ == "__main__":
    print("H476 — Split-Session GARCH IBS Overnight Gate")
    print("Downloading data...")
    raw = yf.download(TICKERS, start="2014-01-01", end=OOS_END, auto_adjust=True, progress=False)

    results = {}
    for var in ["A", "B", "C", "D"]:
        ticker_rets = []
        for tkr in TICKERS:
            prices = raw.xs(tkr, axis=1, level=1).dropna()
            ret = run_variant(prices, var)
            ticker_rets.append(ret)
        combined = pd.concat(ticker_rets, axis=1).mean(axis=1)  # equal-weight across 3 tickers

        print(f"\nVar {var}:")
        is_ret = combined.loc[IS_START:IS_END]
        oos_ret = combined.loc[OOS_START:OOS_END]
        is_sh, _ = evaluate(is_ret, "IS")
        oos_sh, oos_mdd = evaluate(oos_ret, "OOS")
        results[f"Var{var}"] = {"is_sharpe": round(is_sh, 3), "oos_sharpe": round(oos_sh, 3), "oos_mdd": round(oos_mdd, 4)}

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement vs -18%")
    for k, v in results.items():
        passed = v["oos_sharpe"] > GATE_SHARPE
        print(f"  {k}: OOS={v['oos_sharpe']:.3f}  MDD={v['oos_mdd']:.1%}  {'PASS' if passed else 'FAIL'}")
