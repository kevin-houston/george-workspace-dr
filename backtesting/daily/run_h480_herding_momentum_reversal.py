#!/usr/bin/env python3
"""
H477 — Network-Herding Momentum-Reversal Transition Signal on H198 Stock Universe
Source: arXiv:2607.27063 (Jul 2026)

Local herding creates momentum (phase 3-9 months); as information fully
diffuses through the investor network, late adopters reverse direction.
Momentum STREAK COUNTER: stocks in top-6 for 6+ consecutive months are
approaching network saturation and reversal risk — exclude or penalize them.

Variants:
  Var A: Exclude stocks with 6+ consecutive months in top-6 momentum rank
  Var B: Penalize: adj_score = raw_score × exp(-0.1 × streak)
  Var C: Overweight NEW top-6 entrants (first month in top-6): 2× weight
  Var D: Reversal gate — if streak >= 9 months, route to short
  Var E: H198 baseline 6-1m top-6 (sanity check)

Gate: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD improvement
IS: 2013-2020  OOS: 2021-2026
Universe: NASDAQ_30 (H198 30-stock universe)
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

VENV_SITE = "/workspace/agent/venv/lib/python3.11/site-packages"
if VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)

NASDAQ_30 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "TSLA", "AVGO", "COST",
    "NFLX", "ASML", "AMD", "AZN", "ISRG", "QCOM", "CSCO", "INTU", "CMCSA", "TXN",
    "AMGN", "HON", "BKNG", "VRTX", "REGN", "PANW", "MU", "LRCX", "KLAC", "MELI",
]
IS_START, IS_END = "2013-01-01", "2020-12-31"
OOS_START, OOS_END = "2021-01-01", "2026-06-30"
TOP_N = 6
GATE_SHARPE = 1.174
STREAK_EXCLUDE = 6     # Var A: exclude stocks in top-N for >= this many months
STREAK_REVERSAL = 9    # Var D: route to "short list" when streak >= 9


def monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.resample("MS").last().pct_change().shift(-1)


def compute_momentum(prices: pd.DataFrame, skip: int = 1, window: int = 6) -> pd.DataFrame:
    monthly = prices.resample("MS").last()
    return monthly.pct_change(window).shift(skip)


def run_variant(monthly_ret: pd.DataFrame, signal: pd.DataFrame, variant: str) -> pd.Series:
    streaks = pd.DataFrame(0, index=signal.index, columns=signal.columns)
    prev_top = set()

    portfolio_returns = []
    dates = signal.index

    for i, date in enumerate(dates):
        row = signal.loc[date].dropna()
        if len(row) < TOP_N:
            portfolio_returns.append(np.nan)
            continue

        # Update streak counters
        for tkr in row.index:
            if tkr in prev_top:
                streaks.loc[date, tkr] = streaks.iloc[i - 1][tkr] + 1 if i > 0 else 1
            else:
                streaks.loc[date, tkr] = 0

        cur_streaks = streaks.loc[date]

        if variant == "E":
            selected = row.nlargest(TOP_N).index.tolist()
            weights = {t: 1 / TOP_N for t in selected}

        elif variant == "A":
            eligible = row[cur_streaks[row.index] < STREAK_EXCLUDE]
            if len(eligible) < 1:
                eligible = row  # fallback if all are mature
            selected = eligible.nlargest(min(TOP_N, len(eligible))).index.tolist()
            weights = {t: 1 / len(selected) for t in selected}

        elif variant == "B":
            adj = row * np.exp(-0.1 * cur_streaks[row.index])
            selected = adj.nlargest(TOP_N).index.tolist()
            weights = {t: 1 / TOP_N for t in selected}

        elif variant == "C":
            is_new = cur_streaks[row.index] == 0
            scores = row.copy()
            scores[is_new] *= 2.0
            selected = scores.nlargest(TOP_N).index.tolist()
            weights = {t: 1 / TOP_N for t in selected}

        elif variant == "D":
            reversal_list = cur_streaks[row.index][cur_streaks[row.index] >= STREAK_REVERSAL].index.tolist()
            fresh_list = row[cur_streaks[row.index] < STREAK_REVERSAL].nlargest(TOP_N).index.tolist()
            selected = fresh_list
            weights = {t: 1 / len(selected) for t in selected} if selected else {}

        else:
            selected = row.nlargest(TOP_N).index.tolist()
            weights = {t: 1 / TOP_N for t in selected}

        prev_top = set(selected)

        if date not in monthly_ret.index or not weights:
            portfolio_returns.append(np.nan)
            continue

        ret_row = monthly_ret.loc[date]
        port_ret = sum(weights.get(t, 0) * ret_row.get(t, 0) for t in weights)
        portfolio_returns.append(port_ret)

    return pd.Series(portfolio_returns, index=dates).dropna()


def evaluate(returns: pd.Series, label: str):
    ann = returns.mean() * 12
    vol = returns.std() * np.sqrt(12)
    sharpe = ann / vol if vol > 0 else 0.0
    cum = (1 + returns).cumprod()
    mdd = (cum / cum.cummax() - 1).min()
    neg_years = (returns.resample("YE").sum() < 0).sum()
    print(f"  {label}: Sharpe={sharpe:.3f}  CAGR={ann:.1%}  MaxDD={mdd:.1%}  NegYears={neg_years}")
    return sharpe, mdd


if __name__ == "__main__":
    print("H477 — Herding Network Momentum Streak Signal")
    print("Downloading data...")
    raw = yf.download(NASDAQ_30, start="2012-01-01", end=OOS_END, auto_adjust=True, progress=False)
    prices = raw["Close"].dropna(axis=1, how="all")

    signal = compute_momentum(prices)
    monthly_ret = monthly_returns(prices)

    results = {}
    for var in ["A", "B", "C", "D", "E"]:
        print(f"\nVar {var}:")
        strat = run_variant(monthly_ret, signal, var)
        is_r = strat.loc[IS_START:IS_END]
        oos_r = strat.loc[OOS_START:OOS_END]
        is_sh, _ = evaluate(is_r, "IS")
        oos_sh, oos_mdd = evaluate(oos_r, "OOS")
        results[f"Var{var}"] = {"is_sharpe": round(is_sh, 3), "oos_sharpe": round(oos_sh, 3), "oos_mdd": round(float(oos_mdd), 4)}

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement vs H198")
    for k, v in results.items():
        passed = v["oos_sharpe"] > GATE_SHARPE
        print(f"  {k}: OOS={v['oos_sharpe']:.3f}  MDD={v['oos_mdd']:.1%}  {'PASS' if passed else 'FAIL'}")
