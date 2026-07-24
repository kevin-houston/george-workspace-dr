#!/usr/bin/env python3
"""H436 — AlphaZeroBeta: Market-Neutral DRL on H026 ETF Universe.

Source: arXiv:2607.18001 (Belyakov, Jul 2026)
'AlphaZeroBeta: Deep Reinforcement Learning for Market-Neutral Portfolios'

Key innovations over H204 (failed DRL PPO):
  1. Composite reward = alpha_sharpe - lambda_beta * |corr(portfolio, SPY)| - cost_penalty
  2. CNN-GRU policy: CNN captures local price patterns, GRU tracks temporal context
  3. Recurrent PPO with walk-forward validation (rolling 3Y train / 1Y eval windows)
  4. Explicit near-zero beta constraint via reward shaping

Paper result: Sharpe > baselines (equal-weight, min-var, traditional PPO) on 7 equity
indices 2014-2024. Near-zero benchmark correlations maintained throughout.

Universe: H026 25-ETF (sector ETFs + alts + bonds + BIL)
IS: 2008-2017   OOS: 2018-2026
Gate: OOS Sharpe > 1.200 AND Corr(SPY) < 0.50

Variants:
  A: Full AlphaZeroBeta CNN-GRU + composite reward
  B: Standard PPO (MLP policy) + composite reward (ablation: architecture matters?)
  C: CNN-GRU + Sharpe-only reward (ablation: reward shaping matters?)
  D: H026 baseline momentum top-1 (sanity check)

Requires: stable-baselines3, torch, gymnasium
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────────────────
UNIVERSE_H026 = [
    'XLK', 'XLV', 'XLE', 'XLF', 'XLU', 'XLI', 'XLB', 'XLY', 'XLP',
    'XLC', 'XLRE', 'GLD', 'TLT', 'IEF', 'TIP', 'DBC', 'AGG', 'GDX',
    'DBA', 'SLV', 'UNG', 'EWZ', 'IBB', 'XME', 'BIL'
]

IS_START  = '2008-01-01'
IS_END    = '2017-12-31'
OOS_START = '2018-01-01'
OOS_END   = '2026-12-31'

LOOKBACK  = 60   # days of price history as CNN-GRU input
LAMBDA_BETA = 0.3  # beta penalty weight in composite reward
COST_BPS  = 10    # round-trip transaction cost per rebalance

# ── Feature engineering ───────────────────────────────────────────────────────

def build_feature_matrix(prices: pd.DataFrame, as_of: pd.Timestamp,
                          lookback: int = LOOKBACK) -> np.ndarray:
    """Build (lookback, n_assets, n_features) CNN-GRU input tensor.

    Features per asset per day:
      0: daily return
      1: 5-day rolling return
      2: 21-day rolling volatility (normalized)
      3: price relative to 20-day SMA
      4: volume (if available, else 0)
    """
    hist = prices.loc[:as_of].iloc[-lookback:]
    if len(hist) < lookback:
        return None

    n_assets = len(prices.columns)
    n_features = 4
    X = np.zeros((lookback, n_assets, n_features), dtype=np.float32)

    for j, ticker in enumerate(prices.columns):
        p = hist[ticker].fillna(method='ffill').fillna(0)
        r = p.pct_change().fillna(0)
        X[:, j, 0] = r.values                                    # daily return
        X[:, j, 1] = r.rolling(5).sum().fillna(0).values         # 5d cum return
        X[:, j, 2] = r.rolling(21).std().fillna(0).values        # 21d vol
        sma20 = p.rolling(20).mean().fillna(p.iloc[0])
        X[:, j, 3] = (p / sma20 - 1).values                     # price vs SMA

    return X


def composite_reward(portfolio_rets: np.ndarray,
                     spy_rets: np.ndarray,
                     costs: float,
                     lambda_beta: float = LAMBDA_BETA) -> float:
    """Composite reward: alpha-Sharpe - lambda_beta * |beta_corr| - costs."""
    if len(portfolio_rets) < 5:
        return 0.0
    port_sr = portfolio_rets.mean() / (portfolio_rets.std() + 1e-8) * np.sqrt(252)
    corr = np.corrcoef(portfolio_rets, spy_rets[-len(portfolio_rets):])[0, 1]
    beta_penalty = lambda_beta * abs(corr)
    return port_sr - beta_penalty - costs


def run_momentum_baseline(prices: pd.DataFrame,
                           spy_rets: pd.Series,
                           start: str, end: str) -> dict:
    """H026 momentum top-1 baseline (sanity check, Variant D)."""
    month_ends = prices.resample('ME').last().index
    rets = []
    for i, rebal in enumerate(month_ends[:-1]):
        p_hist = prices.loc[:rebal]
        mom12 = (p_hist.iloc[-1] / p_hist.iloc[-252] - 1) if len(p_hist) >= 252 else p_hist.iloc[-1] / p_hist.iloc[0] - 1
        top1 = mom12.idxmax()
        try:
            next_slice = prices[top1].loc[rebal:month_ends[i + 1]]
            ret = next_slice.iloc[-1] / next_slice.iloc[0] - 1 - COST_BPS / 10000
            rets.append(ret)
        except Exception:
            rets.append(0.0)
    s = pd.Series(rets, index=month_ends[1:])
    is_s = s.loc[start:IS_END]
    oos_s = s.loc[OOS_START:end]
    return {
        'IS_Sharpe':  round((is_s.mean() / is_s.std() * np.sqrt(12)) if is_s.std() > 0 else 0, 3),
        'OOS_Sharpe': round((oos_s.mean() / oos_s.std() * np.sqrt(12)) if oos_s.std() > 0 else 0, 3),
        'OOS_MaxDD':  round(((1 + oos_s).cumprod() / (1 + oos_s).cumprod().cummax() - 1).min(), 3),
    }


def main():
    try:
        import torch
        import gymnasium as gym
        from stable_baselines3 import RecurrentPPO
        HAS_SB3 = True
    except ImportError:
        HAS_SB3 = False
        print('WARNING: stable-baselines3 or torch not available. '
              'Installing... (pip install stable-baselines3[extra] torch)')
        import subprocess
        subprocess.run(['pip', 'install', 'stable-baselines3[extra]', 'torch', '-q'],
                       capture_output=True)

    import yfinance as yf

    print('H436 — AlphaZeroBeta Market-Neutral DRL')
    print('=' * 60)
    print(f'Universe: {len(UNIVERSE_H026)} ETFs (H026)')
    print(f'IS: {IS_START}–{IS_END}   OOS: {OOS_START}–{OOS_END}')
    print(f'Gate: OOS Sharpe > 1.200 AND Corr(SPY) < 0.50')
    print()

    # Download data
    tickers = UNIVERSE_H026 + ['SPY']
    raw = yf.download(tickers, start='2007-01-01', end=OOS_END,
                      auto_adjust=True, progress=False)
    prices = raw['Close'][UNIVERSE_H026]
    spy_close = raw['Close']['SPY']
    spy_rets = spy_close.pct_change().dropna()

    # Variant D: H026 baseline (always runnable)
    print('Variant D — H026 momentum baseline...')
    res_D = run_momentum_baseline(prices, spy_rets, IS_START, OOS_END)
    print(f'  IS Sharpe={res_D["IS_Sharpe"]}  OOS Sharpe={res_D["OOS_Sharpe"]}  MaxDD={res_D["OOS_MaxDD"]}')

    results = {'D_baseline': res_D}

    if not HAS_SB3:
        print('\nSkipping Variants A/B/C — RL libraries not installed.')
        print('Run: pip install stable-baselines3[extra] torch sb3-contrib')
        print('Then rerun this script.')
    else:
        # Variants A/B/C require custom gymnasium environment + CNN-GRU policy
        # TODO: implement ETFRotationEnv(gym.Env) with:
        #   - observation_space: Box(lookback, n_assets, n_features)
        #   - action_space: Box(n_assets,) continuous portfolio weights
        #   - reward: composite_reward() defined above
        # Use sb3-contrib RecurrentPPO with CnnLstmPolicy
        print('\nVariants A/B/C: CNN-GRU gym environment scaffold — implement ETFRotationEnv')
        print('See: stable-baselines3, sb3-contrib RecurrentPPO, gymnasium')
        print('Architecture: CNN(3 conv layers) -> GRU(hidden=128) -> Linear -> weights')
        results['A_note'] = 'Requires ETFRotationEnv gymnasium implementation'
        results['B_note'] = 'Ablation: MLP policy with composite reward'
        results['C_note'] = 'Ablation: CNN-GRU with Sharpe-only reward'

    # Save results
    os.makedirs('backtesting/results', exist_ok=True)
    with open('backtesting/results/h436_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    print('\nResults saved to backtesting/results/h436_results.json')


if __name__ == '__main__':
    main()
