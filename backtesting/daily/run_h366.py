"""
H366: DeePM-inspired Regime-Robust Deep Learning on Commodity Futures Universe
Based on arXiv:2601.05975 (DeePM, Jan 2026)
Universe: 12 commodity ETFs (H261b universe)
IS: 2005-2017, Validation: 2018-2020, OOS: 2021-present
Gate: OOS Sharpe > 1.0 AND Corr(SPY) < 0.4

DeePM innovations (simplified for ETF universe):
1. Cross-asset attention over 12 ETF return series
2. Macro regime features: SPY 200MA, VIX, PPIACO YoY, USD index
3. EVaR-style robust objective: optimize worst-window rolling Sharpe
4. Causal sieve simplification: lag all features by 1 period (standard)

Prior: H261b top-2 momentum OOS Sharpe 0.922, Corr(SPY)=0.218
"""

import numpy as np
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

UNIVERSE = ['DBC', 'USO', 'UNG', 'GLD', 'SLV', 'PDBC', 'COMT', 'COMB', 'BCI', 'FTGC', 'GUNR', 'MOO']
BENCHMARK = 'SPY'
IS_START = '2005-01-01'
IS_END = '2017-12-31'
VAL_START = '2018-01-01'
VAL_END = '2020-12-31'
OOS_START = '2021-01-01'
CASH = 'BIL'

# TODO: Phase 1 — confirm H261b baseline on this exact universe/split
# TODO: Phase 2 — implement DeePM attention layer
#   - Input: (T, N, F) tensor: T months, N=12 assets, F features per asset
#   - Features: 1m/3m/6m/12m returns, realized vol, macro regime indicators
#   - Cross-asset attention: multi-head self-attention across N assets
#   - Output: portfolio weights (softmax over N assets)
# TODO: Phase 3 — macro feature integration
#   - FRED: PPIACO (commodity PPI), DTWEXBGS (USD index), VIXCLS
#   - SPY 200MA regime flag
# TODO: Phase 4 — EVaR robust training objective
#   - Rolling 12m Sharpe windows; optimize CVaR(5%) of the distribution
#   - Prevents overfit to favorable subperiods

# ---- Phase 1 baseline: reproduce H261b top-2 momentum on this universe/split ----


def get_data(tickers, start, end):
    raw = yf.download(tickers + [BENCHMARK, CASH], start=start, end=end,
                      auto_adjust=True, progress=False)['Close']
    monthly = raw.resample('ME').last()
    return monthly


def sharpe(returns, rf=0.0, ann=12):
    excess = returns - rf / ann
    if excess.std() == 0:
        return 0.0
    return (excess.mean() / excess.std()) * np.sqrt(ann)


def max_drawdown(equity):
    roll_max = equity.cummax()
    dd = (equity - roll_max) / roll_max
    return dd.min()


def run_top2_momentum(prices, universe, start, end):
    """H261b-style top-2 12m momentum, monthly rebalance."""
    px = prices[universe + [CASH]].loc[start:end]
    r12 = px[universe].pct_change(12).shift(1)
    spy_ret = prices[BENCHMARK].pct_change().shift(1).loc[start:end]

    port_returns = []
    dates = []

    for i in range(12, len(px)):
        date = px.index[i]
        signals = r12.iloc[i]
        valid = signals.dropna()
        if len(valid) < 2:
            ret = prices[CASH].pct_change().loc[date]
        else:
            top2 = valid.nlargest(2).index.tolist()
            month_ret = px[top2].pct_change().iloc[i]
            ret = month_ret.mean()
        port_returns.append(ret)
        dates.append(date)

    returns = pd.Series(port_returns, index=dates)
    return returns


def evaluate(returns, spy_returns, label):
    equity = (1 + returns).cumprod()
    spy_eq = (1 + spy_returns.reindex(returns.index).fillna(0)).cumprod()

    sr = sharpe(returns)
    mdd = max_drawdown(equity)
    cagr = equity.iloc[-1] ** (12 / len(returns)) - 1
    corr_spy = returns.corr(spy_returns.reindex(returns.index))

    neg_years = (returns.resample('YE').apply(lambda x: (1+x).prod()-1) < 0).sum()

    print(f"\n{'='*50}")
    print(f"{label}")
    print(f"{'='*50}")
    print(f"Sharpe:    {sr:.3f}")
    print(f"MaxDD:     {mdd:.1%}")
    print(f"CAGR:      {cagr:.1%}")
    print(f"Corr(SPY): {corr_spy:.3f}")
    print(f"Neg Years: {neg_years}")
    return {'sharpe': sr, 'maxdd': mdd, 'cagr': cagr, 'corr_spy': corr_spy}


def main():
    print("H366: DeePM regime-robust deep learning on commodity ETF universe")
    print("Phase 1: Confirming H261b baseline on new IS/OOS split")
    print("Downloading data...")

    all_tickers = UNIVERSE + [BENCHMARK, CASH]
    prices = get_data(all_tickers, IS_START, '2026-01-01')

    spy_ret = prices[BENCHMARK].pct_change()

    print("\n--- IS (2005-2017): H261b top-2 momentum ---")
    is_ret = run_top2_momentum(prices, UNIVERSE, IS_START, IS_END)
    is_metrics = evaluate(is_ret, spy_ret, "IS 2005-2017")

    print("\n--- Validation (2018-2020) ---")
    val_ret = run_top2_momentum(prices, UNIVERSE, VAL_START, VAL_END)
    val_metrics = evaluate(val_ret, spy_ret, "Validation 2018-2020")

    print("\n--- OOS (2021-present) ---")
    oos_ret = run_top2_momentum(prices, UNIVERSE, OOS_START, None)
    oos_metrics = evaluate(oos_ret, spy_ret, "OOS 2021-present")

    print("\n--- Full period (IS+Val+OOS) ---")
    full_ret = run_top2_momentum(prices, UNIVERSE, IS_START, None)
    full_metrics = evaluate(full_ret, spy_ret, "Full period")

    gate_sharpe = oos_metrics['sharpe'] > 1.0
    gate_corr = oos_metrics['corr_spy'] < 0.4
    print(f"\n{'='*50}")
    print(f"GATE CHECK (H261b baseline on new split)")
    print(f"  OOS Sharpe > 1.0: {'PASS' if gate_sharpe else 'FAIL'} ({oos_metrics['sharpe']:.3f})")
    print(f"  Corr(SPY) < 0.4:  {'PASS' if gate_corr else 'FAIL'} ({oos_metrics['corr_spy']:.3f})")
    if gate_sharpe and gate_corr:
        print("  H261b baseline CONFIRMED on this split — proceed to DeePM Phase 2")
    else:
        print("  H261b baseline FAILS gate on this split — DeePM Phase 2 deprioritized")

    print("\nNOTE: DeePM architecture (Phases 2-4) not yet implemented.")
    print("This script establishes the H261b baseline for the new train/val/OOS split.")
    print("Next: implement cross-asset attention layer + macro features.")


if __name__ == '__main__':
    main()
