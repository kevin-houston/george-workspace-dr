---
updated: 2026-07-05
type: reference + hypothesis seed
---

# Deep Reinforcement Learning for Trading

RL frames trading as a Markov Decision Process: the agent observes market state, takes an action (buy/sell/hold), receives a reward (P&L or Sharpe-adjusted return), and learns a policy that maximizes cumulative reward. Unlike supervised learning, it doesn't need labeled predictions — it learns directly from simulated trading outcomes.

**H204 queued**: test PPO ensemble vs H198 6-1m momentum baseline on our 30-stock universe.

**Related pages**: [Machine Learning for Trading](../tools/ml-for-trading.md) (supervised ML complement; XGBoost H202) | [Momentum Strategies](momentum-strategies.md) (H198 baseline this competes against) | [Hypothesis Log](../backtesting/hypothesis-log.md) | [Backtesting Design Principles](../backtesting/design-principles.md) (OOS safeguards critical for RL)

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
- **AlphaZeroBeta: Sharpe 1.25 avg (7 markets, 22-fold × 9-seed walk-forward, 2014-2024)** — market-neutral via ℓ1-ball-projected PPO + correlation-penalty reward (arXiv:2607.18001); see [source deep-dive](../sources/alphazerobeta-market-neutral-rl-2026.md). A rare RL result with a rigorous multi-fold OOS protocol rather than a single cherry-picked window — the more credible benchmark in this list alongside the ACM survey's caution below.
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

---

## AlphaCrafter Reference Architecture (for H209)

**Paper**: Yuan et al. (2026), arXiv:2605.05580 (May 7, 2026), Nanjing University

**Architecture**:
1. **Miner Agent** — continuously expands factor pool via LLM-guided search; treats factor discovery as ongoing process not one-time
2. **Screener Agent** — assesses market conditions; constructs regime-conditioned factor ensembles (which factors to use NOW)
3. **Trader Agent** — translates factor ensembles into positions under explicit risk constraints (max drawdown, sector limits)

**Key design insight**: factor efficacy varies by regime. A Screener that adapts ensemble weights to regime is more robust than a fixed multi-factor model.

**Adaptation plan for H209 (our implementation)**:
- Miner: use our confirmed factors (H192-D BAB, H198 MOM, H181 REV, H201 TOM) as fixed pool (skip open-ended LLM factor mining initially)
- Screener: regime-conditioned blending — VIX + SMA200 gate to switch between factor weights
- Trader: map to existing Alpaca execution pipeline
- Compare against static blend as baseline

---

### Fine-Grained Agent Input Design (H209 AlphaCrafter Screener)

**Reference**: arXiv:2602.23330 (Feb 2026) — 'Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks'

**Key finding**: LLM trading agents achieve Sharpe +0.08 to +0.26 improvement when given **pre-calculated, structured inputs** vs. raw data. The improvement comes from removing the compute-from-raw overhead and letting the agent focus on judgment.

**Applied to H209 AlphaCrafter Screener agent prompt design**:

```python
# GOOD: structured inputs per stock
screener_context = f"""
Stock: {ticker}
Date: {date}

== Pre-calculated signals ==
6-1m momentum rank: {mom_rank}/30 (1=top, 30=bottom)
Vol-scaled signal: {vol_scaled_signal:.3f} (vs universe mean {universe_mean:.3f})
Trailing 6m realized vol: {realized_vol:.2%}
Sector IC (trailing 3yr): {sector_ic:.3f}
Recent 8-K FinBERT score: {finbert_score:.3f}
Market regime (VIX): {vix_regime} (LOW/NORMAL/HIGH)

== Question ==
Given these pre-calculated signals, should this stock be included in
the top-6 momentum portfolio this month? Answer: YES/NO and 1-sentence rationale.
"""

# BAD: raw data dump
screener_context = f"Here is the OHLCV data for {ticker}: {raw_ohlcv_data}..."
```

**Design rule**: Always pre-compute factor values numerically before sending to LLM agent. The LLM's job is synthesis and judgment, not arithmetic. This also controls API costs (shorter inputs = lower token count).


### BlindTrade — Anonymization-First LLM Portfolio (arXiv:2603.17692)

**Source**: Jeon & Lee, arXiv:2603.17692 (March 18, 2026) — "Can Blindfolded LLMs Still Trade? An Anonymization-First Framework for Portfolio Optimization"

**Key result**: Sharpe **1.40 ± 0.22** on 2025 YTD out-of-sample data — directly competitive with our confirmed H192-D BAB (1.367) and H198 momentum (1.174).

**Core innovation — anonymization to prevent memorization bias**:

LLMs trained on financial data have seen ticker symbols, company names, and historical price patterns. A naive LLM portfolio strategy risks: the model "remembering" that AAPL was at $150 in 2023 and hallucinating a buy signal from training data rather than genuine reasoning. BlindTrade removes this contamination by:

1. Replace all ticker symbols with anonymous codes (COMPANY_A, COMPANY_B, etc.)
2. Remove company names, descriptions, sector labels
3. Feed only anonymized numerical signals + relative rankings
4. Validate using **negative controls** — randomly shuffled anonymized signals should produce ~0 alpha; real signals should produce positive alpha

**Architecture**:
```
4 LLM Agents (GPT-4/Claude) → score each company (0-10)
         ↓
GNN (Graph Neural Network) → model inter-company relationships
         ↓
PPO-DSR (Proximal Policy Optimization + Differential Sharpe Ratio reward)
         ↓
Portfolio weights
```

**Why relevant to H209 (AlphaCrafter)**:
The anonymization methodology is a prerequisite for any LLM-based trading system to be trustworthy. Before implementing AlphaCrafter on our 30-stock universe, the BlindTrade validation protocol should be applied:
- Test: does anonymized-ticker LLM signal produce alpha?
- Control: does random-shuffled signal produce ~0 alpha?
- If both pass: signal is genuine; not memorization

**Companion paper — TrustTrade (arXiv:2603.22567)**:
"TrustTrade: Human-Inspired Selective Consensus Reduces Decision Uncertainty in LLM Trading Agents". Addresses LLM hallucination by weighting agent signals by cross-agent semantic agreement. Inconsistent/outlier signals downweighted. Complementary to BlindTrade (anonymization prevents memorization; TrustTrade prevents hallucination).

**H209 design update**: Before implementing AlphaCrafter multi-agent framework, apply (1) BlindTrade anonymization to our universe, (2) TrustTrade selective consensus aggregation. Both papers available 2026 — state-of-art for LLM trading validation.

---

## Deep Learning Benchmark for TSMOM (arXiv:2603.01820, March 2026)

**Source**: arxiv.org/abs/2603.01820  
**Authors**: Adir Saly-Kaufmann, Kieran Wood, Jan Peter-Calliess, Stefan Zohren (Oxford)

Large-scale evaluation of DL architectures for cross-asset time-series momentum on daily futures data (commodities, equity indices, bonds, FX), 2010–2025.

**Architectures tested**: Linear models, LSTM, xLSTM, Transformer, State Space Models, PatchTST, VSN (Variable Selection Network)

**Key results**:
- **Highest Sharpe**: VSN + LSTM combination
- **Best downside risk**: VSN + xLSTM and LSTM + PatchTST
- **Most TC-robust**: xLSTM (largest breakeven transaction cost buffer)
- Overall: "models explicitly designed to learn rich temporal representations consistently outperform linear benchmarks"

**Relevance to H220 (ETF TSMOM confirmed, OOS 0.961)**:

H220 used a simple binary rule: long if 6m return > 0, flat otherwise. The benchmark suggests this binary rule is the "linear baseline" that all DL models beat. The upgrade path:

1. Replace binary trend signal with **LSTM trend score** (continuous position from 0 to 1)
2. Use **vol-scaling** per Barroso & Santa-Clara (H212 analogue for TSMOM)
3. Target architecture: **xLSTM** for transaction-cost robustness (important for monthly rebalance with 14 ETFs)

**Estimated improvement**: Academic benchmarks show ~15–25% Sharpe improvement from binary → DL trend. On our H220 OOS Sharpe of 0.961: expected upgrade to ~1.1–1.2.

**H223 design note** (DL-TSMOM on 14-ETF universe):
- Signal: LSTM trained on rolling 5yr window, predicting 1m forward return direction
- Position: continuous (not binary) — scale by LSTM confidence
- Universe: same 14 ETFs as H220
- IS: 2013-2019 (training), OOS: 2020-2026 (evaluation)
- Confirm: OOS Sharpe > 1.1 (beat H220's 0.961)

---

## 2026 Updates — New Benchmarks, Frameworks, and Regime-Adaptive RL

### RL in Quantitative Finance: ACM Computing Surveys (arXiv:2408.10932)

**Paper**: Pippas, Ludvig & Turkay — "The Evolution of Reinforcement Learning in Quantitative Finance: A Survey"  
**Published**: ACM Computing Surveys, April 2025. 167 papers reviewed.

**Key findings relevant to our pipeline:**

| Finding | Implication |
|---------|-------------|
| No single algorithm dominates — context-specific design matters more than choice of PPO vs SAC vs TD3 | H204 should test at least 3 algorithms |
| DQN (37 papers) and Q-learning (36) dominate published literature but are for **discrete** actions | PPO/SAC better for continuous portfolio weights |
| Financial data non-stationarity is the #1 failure mode | Train window should not exceed 7–8 years; rolling re-train |
| Most papers use fixed transaction costs — real-world slippage/spread dynamics are poorly modeled | Use H026/H198 calibrated 10bp round-trip cost model |
| Model-based RL (synthetic data generation) is underexplored — only 3 papers as of 2024 | High upside for future research; connects to H249 regime synthetic data |
| Recommendation: hybrid offline pre-train + online fine-tune | Pre-train PPO on H198 IS (2013–2020), brief online adaptation in paper trading |

**Critical summary**: "No RL approach demonstrates consistent superiority. The evaluation crisis — inconsistent benchmarks, cherry-picked test windows, single seeds — makes cross-paper comparison unreliable. Reproduce with 5+ seeds and walk-forward OOS."

---

### FinRL-X: Production-Ready Successor to FinRL (2026)

**Repo**: [github.com/AI4Finance-Foundation/FinRL-Trading](https://github.com/AI4Finance-Foundation/FinRL-Trading)  
**Install**: `git clone https://github.com/AI4Finance-Foundation/FinRL-Trading.git && pip install -r requirements.txt`

The original FinRL (2020, 10k+ stars) was DRL-exclusive and tightly coupled. FinRL-X (2026) uses a **weight-centric architecture**: portfolio weight vectors are the single interface between strategy components and execution layers, enabling seamless backtest-to-live transition.

| Aspect | FinRL (2020) | FinRL-X (2026) |
|--------|-------------|---------------|
| Approach | DRL-exclusive | AI-native (ML + DRL + LLM-ready) |
| Design | Monolithic coupling | Modular layers |
| Interface | Gym state/action spaces | Weight-centric contracts |
| Data Sources | 14 manual processors | Auto-select (Yahoo/FMP/WRDS) |
| Live Trading | Basic Alpaca support | Multi-account with risk controls |

**Benchmark results (Adaptive Rotation strategy, Jan 2018 – Oct 2025)**:
- Sharpe Ratio: **1.10** (vs QQQ: 0.81, SPY: 0.72)
- Cumulative Return: 4.80×
- Max Drawdown: −21.46% (vs QQQ: −35.12%)

**Paper trading validation (Oct 2025 – Mar 2026)**:
- Sharpe Ratio: **1.96** (live paper trading; n=6 months)
- Cumulative: 1.20×

**Key design patterns worth adopting for H204:**
```bash
# One-command backtest
./deploy.sh --strategy adaptive_rotation --mode backtest

# Available built-in strategies:
# 1. Portfolio Allocation: EW, MV, Min-Var, DRL Allocator, KAMA Timing
# 2. Rolling Selection + DRL: Quarterly top-25% NASDAQ-100 via ML scoring
# 3. Adaptive Multi-Asset Rotation: dynamic sector rotation + regime detection + risk controls
```

**Why better than raw stable-baselines3 for H204**: FinRL-X handles the data pipeline, multi-asset gym environment, and live Alpaca integration. Avoids rebuilding the `StockTradingEnv` from scratch. The weight-centric interface means the same trained agent can run in backtest or paper trading without code changes.

---

### HMM + RL Regime-Adaptive Portfolio (arXiv:2605.27848, May 2026)

**Paper**: Verma, Putri & Lesupi — "Regime-Based Portfolio Allocation Using Hidden Markov Models and Reinforcement Learning"  
**Submitted**: May 27, 2026  
**Universe**: SPY/TLT/GLD (3-asset)  
**Data**: Daily 2004–2025 (30% OOS, one-day execution lag)

**Architecture**: Two-layer approach that directly extends our confirmed H249 and H251 results:

1. **HMM layer**: 3-state Gaussian HMM (BIC model selection) identifies market regimes — low-volatility, transitional, high-volatility
2. **RL policy layer**: PPO-style policy learns regime-conditional allocation actions on top of HMM state

**Results**:
- HMM-only allocations outperform passive SPY benchmark OOS
- RL policy layer achieves **highest Sharpe** and **lowest MaxDD** among tested variants
- OOS test window: 2019–2025 (30% of 2004–2025 daily data, ~1,500 trading days)
- One-day execution lag: lag between signal and trade prevents look-ahead bias

**Connection to our confirmed hypotheses:**

| Our Result | This Paper's Extension |
|-----------|----------------------|
| H251 CONFIRMED (3-state HMM OOS 0.941) | HMM+RL outperforms HMM-only |
| H249 CONFIRMED (regime-conditional weights +0.282 Sharpe) | RL policy layer provides adaptive weight optimization |
| SPY/TLT/GLD 3-asset universe | Exact same universe — directly comparable |

**H371 candidate**: Replicate arXiv:2605.27848 on our universe. Train on 2004–2017, OOS 2018–2026. Add: (a) BIL as 4th asset (risk-free escape hatch), (b) regime transition penalty in reward to reduce whipsaw. Gate: OOS Sharpe > H251 baseline (0.941).

**Python skeleton (integration with existing H249 regime engine)**:

```python
import gymnasium as gym
import numpy as np
from hmmlearn import hmm
from stable_baselines3 import PPO

class RegimePortfolioEnv(gym.Env):
    """
    HMM-informed RL environment for SPY/TLT/GLD/BIL allocation.
    State: [regime_probs (3), current_weights (4), last_20d_returns (4)]
    Action: portfolio weights (4), continuous, softmax-normalized
    """
    ASSETS = ['SPY', 'TLT', 'GLD', 'BIL']

    def __init__(self, returns: np.ndarray, hmm_model: hmm.GaussianHMM,
                 lookback: int = 20, cost_bps: float = 10):
        super().__init__()
        self.returns = returns          # (T, 4) daily returns
        self.hmm = hmm_model
        self.lookback = lookback
        self.cost = cost_bps / 10_000
        self.n_assets = len(self.ASSETS)

        # State: regime probs (3) + weights (4) + recent returns (4*20)
        n_obs = 3 + self.n_assets + self.n_assets * lookback
        self.observation_space = gym.spaces.Box(-np.inf, np.inf, (n_obs,), dtype=np.float32)
        # Action: unconstrained; we softmax to portfolio weights
        self.action_space = gym.spaces.Box(-3, 3, (self.n_assets,), dtype=np.float32)

    def _get_obs(self):
        window = self.returns[self.t - self.lookback : self.t]  # (lookback, 4)
        regime_probs = self.hmm.predict_proba(window[-5:]).mean(axis=0)  # 3-state probs
        return np.concatenate([regime_probs, self.weights, window.flatten()]).astype(np.float32)

    def step(self, action):
        # Softmax to portfolio weights (no shorting)
        exp = np.exp(action - action.max())
        new_weights = exp / exp.sum()
        turnover = np.abs(new_weights - self.weights).sum()
        self.weights = new_weights

        day_ret = self.returns[self.t]
        port_ret = np.dot(new_weights, day_ret) - self.cost * turnover

        self.t += 1
        done = self.t >= len(self.returns) - 1
        return self._get_obs(), float(port_ret), done, False, {}

    def reset(self, seed=None):
        self.t = self.lookback
        self.weights = np.ones(self.n_assets) / self.n_assets  # EW start
        return self._get_obs(), {}

# Training flow:
# 1. Fit 3-state HMM on IS returns
# 2. Create RegimePortfolioEnv with fitted HMM
# 3. Train PPO for 200k timesteps
# 4. Evaluate on OOS period with fixed HMM parameters (no re-fitting OOS)
```

---

### LambdaRankIC: Direct IC Optimization (arXiv:2605.00501, May 2026)

**Paper**: Lin, Su & Yang — "LambdaRankIC: Directly Optimizing Rank IC for Financial Prediction"  
**Submitted**: May 2026  
**Dataset**: 2,746,083 stock-month observations, 21,396 securities, January 1964 – December 2024, 94 monthly characteristics

While not a deep RL method, LambdaRankIC is the state-of-art in cross-sectional momentum prediction and belongs here as a **high-performance alternative** to standard regression-trained factor models.

**Core insight**: Existing models (XGBoost, LightGBM, LSTM) are trained on MSE/classification losses — but the evaluation metric for cross-sectional stock selection is **Rank IC** (Spearman correlation between predicted and realized returns). LambdaRankIC derives closed-form lambda gradients for pairwise rank swaps and optimizes directly for Rank IC within the XGBoost framework.

**Results (OOS, 1964–2024, 94 characteristics)**:

| Method | Rank IC | ICIR | Monthly Return | Sharpe |
|--------|---------|------|---------------|--------|
| OLS regression | 0.0418 | 0.4561 | 1.25% | 0.696 |
| LambdaRank-NDCG | 0.0863 | 0.8122 | 1.20% | 0.501 |
| Pairwise ranking | 0.0828 | 0.7181 | 1.42% | — |
| **LambdaRankIC** | **0.1148** | **1.0308** | **2.22%** | **0.923** |

- **175% IC improvement** over OLS regression
- **126% ICIR improvement** over OLS
- **33% Sharpe improvement** over OLS
- ICIR = 1.03 means the IC signal is persistent, not just a lucky period

**Implementation**: Custom XGBoost objective — compatible with our existing `run_h198.py` pipeline. Replace the default regression objective with LambdaRankIC loss.

```python
import xgboost as xgb
import numpy as np

def lambdarankic_objective(y_pred: np.ndarray, dtrain: xgb.DMatrix):
    """
    Custom XGBoost objective: maximize Rank IC via pairwise lambda gradients.
    y_pred: predicted scores for each stock
    dtrain: contains true returns as labels
    Returns: (gradient, hessian) arrays
    """
    y_true = dtrain.get_label()
    n = len(y_true)

    # Compute pairwise rank differences
    rank_true = np.argsort(np.argsort(y_true))    # rank of each stock in y_true
    rank_pred = np.argsort(np.argsort(y_pred))    # rank of each stock in y_pred

    # Lambda gradient: for each stock i, sum over all stocks j with better true rank
    # but worse predicted rank (pairs to "fix" for IC improvement)
    grad = np.zeros(n)
    hess = np.zeros(n) + 1.0  # constant hessian (standard LambdaRank)

    for i in range(n):
        for j in range(n):
            if rank_true[i] > rank_true[j] and rank_pred[i] < rank_pred[j]:
                # i should rank higher than j but doesn't — push i up
                delta_ic = (rank_true[i] - rank_true[j]) / n   # IC contribution
                grad[i] -= delta_ic   # push predicted score for i up
                grad[j] += delta_ic   # push predicted score for j down

    return grad, hess

# Vectorized version for production (O(n^2) is too slow for large universes)
def lambdarankic_objective_fast(y_pred, dtrain):
    """Vectorized lambda gradients using broadcast operations."""
    y_true = dtrain.get_label()
    n = len(y_true)
    rank_true = np.argsort(np.argsort(y_true)).astype(float)
    rank_pred = np.argsort(np.argsort(y_pred)).astype(float)

    # Broadcasting: (n, n) pair matrices
    rt_diff = rank_true[:, None] - rank_true[None, :]   # i > j in true rank?
    rp_diff = rank_pred[:, None] - rank_pred[None, :]   # i < j in pred rank?

    # Pairs where true rank i > true rank j but pred rank i < pred rank j
    should_fix = (rt_diff > 0) & (rp_diff < 0)
    delta_ic = np.abs(rt_diff) / n * should_fix

    # Gradient for each stock: sum over pairs it's involved in
    grad = -(delta_ic.sum(axis=1) - delta_ic.sum(axis=0))
    hess = np.ones(n)
    return grad, hess

# Usage in training
params = {
    'max_depth': 6, 'learning_rate': 0.05,
    'n_estimators': 300, 'subsample': 0.8,
    'colsample_bytree': 0.8, 'random_state': 42
}
model = xgb.train(
    params,
    dtrain,
    num_boost_round=300,
    obj=lambdarankic_objective_fast,   # custom objective
    evals=[(dval, 'val')],
    early_stopping_rounds=20,
)
```

**H370 candidate**: Apply LambdaRankIC to our H198 30-stock universe. Replace MSE loss in any XGBoost/LightGBM layer with direct RankIC optimization. Gate: OOS Rank IC > 0.05 AND OOS Sharpe > 1.174 (H198 baseline). IS: 2013–2020, OOS: 2021–2026.

**Note on scale**: The paper used 94 characteristics on 21,396 securities. Our 30-stock universe is far smaller — Rank IC may be noisier. Start with 6-1m momentum as sole characteristic; add alpha101 factors (H217 confirmed) as additional features.

---

### Updated H204 Status and Upgrade Path

**H204 (PPO vs H198) status**: Still queued as of 2026-07-05. Not yet run.

**Recommended approach** given new 2026 evidence:

1. **Start with LambdaRankIC (H370)** — no RL complexity, custom XGBoost objective, Rank IC improvement is mathematically guaranteed vs OLS. Lower implementation risk than full PPO environment. Run first.

2. **If H370 passes gate**: Combine with RL timing layer (H204 variant) — use LambdaRankIC for cross-sectional stock ranking, PPO for timing (when to go long vs flat).

3. **HMM+RL regime approach (H371)** — parallel track for the SPY/TLT/GLD/BIL universe. Use existing H249 regime engine (confirmed +0.282 Sharpe) as HMM backbone; add PPO policy layer for dynamic weight optimization within regimes.

4. **FinRL-X for H204 implementation**: Instead of building the gym environment from scratch (as in the code above), use FinRL-X's weight-centric interface. Reduces implementation time from ~2 days to ~4 hours.

**H204 priority**: MEDIUM — LambdaRankIC (H370) has higher confidence due to 60-year OOS evidence base and simpler implementation. H204 full-RL is higher risk/reward.

---

## Cross-References (updated 2026-08-06)

- [Regime Detection](regime-detection.md) — H249/H251 confirmed results; HMM+RL (H371) extends these
- [Factor Models](factor-models.md) — LambdaRankIC (H370) bridges here; AlphaCrafter Screener design
- [Momentum Strategies](momentum-strategies.md) — H198 baseline that H204/H370 must beat (Sharpe 1.174)
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — AlphaCrafter full-stack, BlindTrade, TrustTrade
- [Time-Series Foundation Models](ts-foundation-models.md) — DL benchmark arXiv:2603.01820; xLSTM for TSMOM
- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — FactorMiner, TreEvo, QuantaAlpha (H365 area)
- [AlphaZeroBeta — Market-Neutral RL Source Deep-Dive](../sources/alphazerobeta-market-neutral-rl-2026.md) — ℓ1-ball-projected PPO + correlation-penalty reward, Sharpe 1.25 avg across 7 markets with Corr(benchmark) ≤0.15 by construction; concrete pattern for reward-shaping toward neutrality rather than measuring it post-hoc
- [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md) — production diversification gap AlphaZeroBeta's neutrality-by-construction approach targets
