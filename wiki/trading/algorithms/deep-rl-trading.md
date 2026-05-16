---
updated: 2026-05-16
type: reference + hypothesis seed
---

# Deep Reinforcement Learning for Trading

RL frames trading as a Markov Decision Process: the agent observes market state, takes an action (buy/sell/hold), receives a reward (P&L or Sharpe-adjusted return), and learns a policy that maximizes cumulative reward. Unlike supervised learning, it doesn't need labeled predictions — it learns directly from simulated trading outcomes.

**H204 queued**: test PPO ensemble vs H198 6-1m momentum baseline on our 30-stock universe.

---

## Why RL for trading (and the hard problems)

**Advantages over supervised methods:**
- Handles discrete action spaces naturally (long/flat/short, or portfolio weights)
- Learns position sizing implicitly through reward shaping
- Can model sequential dependencies (holding costs, slippage accumulation)
- No need for explicit price-direction labels

**Core difficulties:**
- **Non-stationarity**: the market regime changes; a policy trained 2013–2020 may be entirely wrong post-2022
- **Sparse, noisy rewards**: daily returns are mostly noise; the signal-to-noise ratio in financial data is far lower than Atari games
- **Look-ahead bias**: extremely easy to introduce in episode construction
- **Overfitting to IS data**: RL agents will exploit any statistical artifact in training data. OOS degradation is typically severe.
- **Benchmark ambiguity**: most published results cherry-pick favorable test periods

**Honest OOS benchmarks** (recent papers):
- DDPG-TiDE: Sharpe 1.13 OOS, no leverage (arXiv:2508.20103)
- PPO+A2C+DDPG ensemble: Sharpe > DJIA buy-and-hold OOS (arXiv:2511.12120)
- TD3: Sharpe 2.68 on unseen data (single period, cherry-picked)
- Our target to beat: H198 6-1m momentum, **OOS Sharpe 1.174** (2021–2026)

---

## Key frameworks

### FinRL (AI4Finance-Foundation)

**Repo**: github.com/AI4Finance-Foundation/FinRL — 10,000+ stars, MIT  
**Install**: `pip install finrl`  
**Algorithms**: PPO, A2C, DDPG, SAC, TD3 (via stable-baselines3)  
**Data sources**: Alpaca, Yahoo Finance, Binance, Interactive Brokers  
**Docs**: finrl.readthedocs.io

The standard starting point. Three-layer architecture: environment (historical data + technical indicators) → agent (DRL algorithm) → application (single asset / multi-asset / portfolio). Upgraded to PyTorch + stable-baselines3 in Dec 2020.

**FinRL-X**: next-gen evolution. More modular, production-oriented, designed for live deployment. Same AI4Finance foundation.

### stable-baselines3 (direct)

**Repo**: github.com/DLR-RM/stable-baselines3 — MIT  
**Install**: `pip install stable-baselines3`  
**When to use**: when you want to define your own gym environment without FinRL's abstractions

Best algorithms for financial data: **PPO** (most stable, less sample-efficient), **SAC** (better for continuous action spaces like portfolio weights), **TD3** (good for deterministic continuous actions).

---

## Environment design

The hardest part. Getting state/reward wrong invalidates everything.

### State space

```python
# Minimal state: price-based features only (avoid look-ahead)
state = [
    close_t / close_t-20,        # 20-day momentum
    close_t / close_t-60,        # 60-day momentum (6-1 skip in monthly terms)
    rolling_vol_20,               # realized vol (20d)
    rsi_14,                       # RSI
    current_position,             # {-1, 0, 1}
    days_held,                    # position age (penalizes holding costs)
]
```

Key rule: **all state features must use only information available at decision time**, computed from data up to and including `t-1`.

### Reward function options

| Reward | Formula | Notes |
|--------|---------|-------|
| Raw P&L | `r_t * position_t-1` | High variance, slow to converge |
| Sharpe-shaped | `mean(r) / std(r) * sqrt(252)` (rolling window) | Better signal, more complex |
| Differential Sharpe | `dSharpe/dt` at each step | López de Prado recommends; computationally stable |
| Sortino | `mean(r) / downside_std(r)` | Penalizes downside only |

**Recommendation**: start with raw P&L minus transaction cost, then upgrade to differential Sharpe once agent is learning at all.

### Transaction costs

```python
cost = 0.0010  # 10 bps round-trip per trade
reward_adjusted = raw_return - cost * abs(new_position - old_position)
```

---

## Working example: minimal RL environment (gym + stable-baselines3)

```python
import gymnasium as gym
import numpy as np
import pandas as pd
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv

class StockTradingEnv(gym.Env):
    def __init__(self, prices: pd.DataFrame, lookback: int = 20, cost_bps: float = 10):
        super().__init__()
        self.prices  = prices
        self.returns = prices.pct_change().fillna(0)
        self.lookback = lookback
        self.cost     = cost_bps / 10_000
        self.n_assets = prices.shape[1]

        # Action: continuous weights [-1, 1] per asset
        self.action_space = gym.spaces.Box(-1, 1, (self.n_assets,), dtype=np.float32)
        # Obs: n_assets × lookback returns + current positions
        n_obs = self.n_assets * lookback + self.n_assets
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (n_obs,), dtype=np.float32)

        self.t = lookback
        self.positions = np.zeros(self.n_assets)

    def _get_obs(self):
        window = self.returns.iloc[self.t - self.lookback : self.t].values  # (lookback, n_assets)
        return np.concatenate([window.flatten(), self.positions]).astype(np.float32)

    def reset(self, seed=None):
        self.t = self.lookback
        self.positions = np.zeros(self.n_assets)
        return self._get_obs(), {}

    def step(self, action):
        # Normalize action to portfolio weights
        weights = np.clip(action, -1, 1)
        turnover = np.abs(weights - self.positions).sum()
        self.positions = weights

        # Daily return
        day_ret = self.returns.iloc[self.t].values
        port_ret = np.dot(weights, day_ret) - self.cost * turnover

        self.t += 1
        done = self.t >= len(self.prices) - 1
        return self._get_obs(), float(port_ret), done, False, {}


def train_rl_agent(train_prices: pd.DataFrame, timesteps: int = 200_000) -> PPO:
    env = DummyVecEnv([lambda: StockTradingEnv(train_prices)])
    model = PPO("MlpPolicy", env, verbose=0,
                learning_rate=3e-4, n_steps=2048, batch_size=64,
                n_epochs=10, gamma=0.99, clip_range=0.2)
    model.learn(total_timesteps=timesteps)
    return model


def eval_rl_agent(model: PPO, test_prices: pd.DataFrame) -> pd.Series:
    env = StockTradingEnv(test_prices)
    obs, _ = env.reset()
    returns = []
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, done, _, _ = env.step(action)
        returns.append(reward)
    return pd.Series(returns, index=test_prices.index[env.lookback:])
```

---

## Key papers

### Foundational

| Paper | Method | Key result |
|-------|--------|------------|
| Jiang, Xu, Liang (2017) arXiv:1706.10059 | Policy gradient (PGPortfolio) | Crypto portfolio > buy-and-hold IS |
| Théate & Ernst (2020) arXiv:2004.06627 | DQN (single asset) | First clean IS/OOS backtest framework |
| Theate (2022) | TD3 | Sharpe 2.68 OOS (single cherry-picked period) |

### Momentum + DL (most relevant to H204)

| Paper | Method | Key result |
|-------|--------|------------|
| **Lim, Zohren, Roberts (2019) arXiv:1904.04912** | LSTM for time-series momentum | Outperforms linear TSMOM across 88 assets |
| Takács & Xiao (2019) | DNN for momentum | Moderate improvement over simple momentum |
| AlphaStock (2019) arXiv:1908.02646 | Attention-based DRL | Interpretable winners/losers portfolio |

The Lim/Zohren/Roberts paper is the most directly relevant — it's by the same group (Oxford) behind arXiv:2602.23330 and tests LSTM-enhanced momentum on a large cross-asset universe. Their LSTM learns to time *entry/exit* of momentum positions, not just signal ranking.

### Recent ensembles

| Paper | Method | OOS Sharpe |
|-------|--------|------------|
| arXiv:2511.12120 (Nov 2025) | PPO+A2C+DDPG ensemble, DJIA 30 | > DJIA, > min-variance |
| arXiv:2508.20103 (2025) | DDPG + TiDE encoder | 1.13 (no leverage) |

---

## Application to our 30-stock universe (H204 design)

**Hypothesis**: A PPO agent trained on our 30-stock IS (2013–2020) achieves OOS Sharpe > H198 baseline (1.174) on 2021–2026.

**Baseline to beat**: H198 6-1m momentum, OOS Sharpe 1.174, Cumul 1.897×

**Design choices for H204:**

| Choice | Value | Reason |
|--------|-------|--------|
| Algorithm | PPO | Most stable; good for continuous actions |
| State | 60-day return history per stock + current weights | Directly encodes the momentum signal |
| Action | Portfolio weights, continuous [-1, 1] | Allows short; more expressive than long-only |
| Reward | Raw return minus 10bps turnover cost | Simple to debug |
| IS training | 2013–2020 only | Strict temporal cutoff |
| OOS eval | 2021–2026 | Same as H198 |
| Timesteps | 500,000 | ~3 full passes over IS data |
| Ensemble | 5 seeds, average | Reduce seed variance |

**Critical safeguard**: the gym environment must use only data up to and including `t-1` for the state at step `t`. Even one day of look-ahead in the normalization window invalidates the OOS result.

---

## Honest expectations

Most published RL trading results that look impressive suffer from:
1. **Training on full available history** (including the test period)
2. **No transaction costs** or unrealistically low (1 bps)
3. **Single random seed** — RL results have high variance
4. **Favorable test period** selection

The 2021–2026 OOS period includes the 2022 bear market, the 2023–2024 AI boom, and elevated macro volatility. A policy trained on 2013–2020 (mostly bull market) will struggle unless it explicitly learns a defensive regime.

**Realistic target**: OOS Sharpe 0.8–1.2 — likely below H198 momentum, but with lower correlation, making it useful for blending (H203 extension).

---

## Install

```bash
pip install stable-baselines3 gymnasium finrl
# For FinRL data pipeline:
pip install pyfolio-reloaded alpaca-py yfinance
```
