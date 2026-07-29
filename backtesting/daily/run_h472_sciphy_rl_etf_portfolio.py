#!/usr/bin/env python3
"""
H472 — SciPhy Reinforcement Learning for ETF Portfolio Optimization via HJB-PINN
Source: arXiv:2607.15195 (Halperin & Itkin, Jul 2026)

Applies Scientific Physics-Informed RL to H026/H041a/H045 ETF universes.
Core idea: reduce portfolio optimization to solving HJB equation projected onto
historical price paths (pathwise HJ equation), solved via PINN in one offline pass.

Variants:
  Var A: SciPhyRL on H026 25-asset universe with 12m momentum signal
  Var B: SciPhyRL on H045 13-asset bond universe with TSMOM signal
  Var C: SciPhyRL on H041a 19-asset universe
  Var D: Myopic mean-variance baseline (control)

Gate: OOS Sharpe > 2.5 AND MaxDD not worse than -5%
IS: 2008-2017  OOS: 2018-2026
"""

import sys
import numpy as np
import pandas as pd
import yfinance as yf

H026_TICKERS = [
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    "XLC", "GLD", "SLV", "DBC", "USO", "TLT", "IEF", "LQD", "HYG", "EMB",
    "EFA", "EEM", "IWM", "QQQ", "BIL",
]
H041A_TICKERS = [
    "XLK", "XLV", "XLF", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB",
    "GLD", "SLV", "TLT", "IEF", "EFA", "EEM", "IWM", "QQQ", "DBC", "BIL",
]
H045_TICKERS = [
    "TLT", "IEF", "SHY", "LQD", "HYG", "EMB", "TIP", "MUB",
    "BWX", "PCY", "BNDX", "AGG", "BIL",
]

IS_START, IS_END = "2008-01-01", "2017-12-31"
OOS_START, OOS_END = "2018-01-01", "2026-12-31"


def momentum_signal(prices: pd.DataFrame, lookback: int = 12, skip: int = 1) -> pd.Series:
    r = prices.shift(skip).pct_change(lookback)
    return r.iloc[-1].rank(ascending=False)


def myopic_mv_weights(returns_window: pd.DataFrame) -> pd.Series:
    """Simple mean-variance optimal weights (long-only)."""
    mu = returns_window.mean()
    sigma = returns_window.cov()
    try:
        inv_sigma = np.linalg.inv(sigma.values + 1e-6 * np.eye(len(sigma)))
        w = inv_sigma @ mu.values
        w = np.maximum(w, 0)
        if w.sum() > 0:
            w = w / w.sum()
        else:
            w = np.ones(len(mu)) / len(mu)
    except np.linalg.LinAlgError:
        w = np.ones(len(mu)) / len(mu)
    return pd.Series(w, index=mu.index)


def sciphy_rl_weights(
    returns_history: pd.DataFrame,
    momentum_ranks: pd.Series,
    alpha_momentum: float = 0.8,
    alpha_sciphy: float = 0.2,
) -> pd.Series:
    """
    Soft-blend SciPhyRL approximation:
    - 80% top-1 momentum (main signal)
    - 20% myopic MV (SciPhyRL proxy pending full PINN implementation)

    Full PINN implementation: train neural net to approximate V(t,w,x) from HJB:
        dV/dt + H(t, w, x, dV/dw) = 0
    projected onto observed price trajectories. See arXiv:2607.15195 Algorithm 1.
    """
    top_ticker = momentum_ranks.idxmin()
    w_momentum = pd.Series(0.0, index=momentum_ranks.index)
    w_momentum[top_ticker] = 1.0

    if len(returns_history) >= 12:
        w_mv = myopic_mv_weights(returns_history.tail(36))
    else:
        w_mv = pd.Series(1.0 / len(momentum_ranks), index=momentum_ranks.index)

    w_blend = alpha_momentum * w_momentum + alpha_sciphy * w_mv
    return w_blend / w_blend.sum()


def run_backtest(tickers: list, variant: str) -> dict:
    print(f"\n=== H472 {variant} | {len(tickers)} assets ===")
    prices = yf.download(tickers, start=IS_START, end=OOS_END,
                         auto_adjust=True, progress=False)["Close"]
    prices = prices.resample("ME").last().ffill()
    rets = prices.pct_change().dropna(how="all")

    oos_rets_list = []
    for i, date in enumerate(rets.index):
        if date < pd.Timestamp(OOS_START):
            continue
        history = rets.iloc[:i]
        if len(history) < 13:
            continue
        prices_hist = prices.iloc[:i + 1]
        ranks = momentum_signal(prices_hist)
        valid = ranks.dropna().index.tolist()
        if not valid:
            continue

        if variant == "D":
            w = myopic_mv_weights(history[valid].tail(36))
        else:
            w = sciphy_rl_weights(history[valid], ranks[valid])

        actual = rets.loc[date, valid].fillna(0)
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
    results = {
        "A_H026": run_backtest(H026_TICKERS, "A"),
        "B_H045": run_backtest(H045_TICKERS, "B"),
        "C_H041a": run_backtest(H041A_TICKERS, "C"),
        "D_MV_H026": run_backtest(H026_TICKERS, "D"),
    }

    print("\n=== H472 Summary ===")
    gate = 2.5
    for name, r in results.items():
        if r:
            passed = r["sharpe"] > gate and r["max_dd"] < 0.05
            print(f"  {name}: Sharpe={r['sharpe']:.3f}  MaxDD={-r['max_dd']:.1%}  "
                  f"{'PASS' if passed else 'FAIL'} (gate>{gate})")
