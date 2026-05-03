# Alpha-R1: RL-Trained Dynamic Factor Gating via LLM Reasoning

**Source:** arXiv:2512.23515 — "Alpha-R1: Alpha Screening with LLM Reasoning via Reinforcement Learning"
**Date:** December 2025
**Authors:** Zuoyou Jiang, Li Zhao, Rui Sun et al. (FinStep AI)
**GitHub:** https://github.com/FinStep-AI/Alpha-R1
**Relevance:** Future Round 33 — meta-layer for 146-strategy library

---

## Problem Statement

Classical alpha factor models suffer from "alpha decay" — factors that worked historically stop working as market conditions change. Static models can't distinguish "this factor is relevant today" from "this factor worked 5 years ago." Alpha-R1 solves this by using RL to train a reasoning model that dynamically activates/deactivates factors based on current context.

---

## Architecture

**Three-stage pipeline:**

1. **Data Preparation**
   - Abstracts raw technical indicators (82 Alpha101 factors) into natural language descriptions
   - Encodes financial news into semantic representations
   - Builds iterative weekly market state summaries (price dynamics + news narratives)

2. **Semantic State Representation**
   - For each factor: generates description explaining economic rationale + known failure conditions
   - For each trading date: synthesizes market state from recent price dynamics + news
   - These become natural-language decision inputs for the reasoning model

3. **RL Optimization (GRPO)**
   - Base model: 8B reasoning LLM (architecture similar to DeepSeek-R1 style)
   - Training algorithm: Group Relative Policy Optimization (GRPO) — critic-free, lower memory
   - At each trading date: model reasons over factor descriptions + market state → selects subset of factors
   - Portfolio: fixed linear model using only selected factors to rank stocks → long top decile, short bottom decile

**RL Reward Function (multi-component):**
```
if portfolio_return > 0:
    reward = portfolio_return × (1 - consistency_penalty)
else:
    reward = portfolio_return × (1 + consistency_penalty)
```
Where consistency_penalty = LLM-as-judge score for logical coherence of factor selection rationale.

This forces the model to explain *why* it selected factors in a way that makes economic sense, not just to chase returns.

---

## Performance Results (Jan–Jun 2025 holdout)

**CSI 300 (in-domain):**
- Cumulative Return: 12.99%
- Annualized Return: 27.59%
- Sharpe Ratio: 1.62
- Max Drawdown: 6.76%

**CSI 1000 (zero-shot, out-of-domain):**
- Cumulative Return: 42.49%
- Annualized Return: 78.18%
- Sharpe Ratio: 4.03
- Max Drawdown: 9.25%

**Baselines (CSI 300):**
- XGBoost: -21.65% annualized
- PPO: Sharpe 0.11
- DeepSeek-R1 (raw LLM, no RL): -11.93% annualized

---

## Key Insights

1. **Factor selection is the bottleneck, not factor construction.** Using all 82 Alpha101 factors simultaneously is noisier than using the right 10-20 on any given day.

2. **Semantic rationale improves RL stability.** By requiring the model to explain factor selection coherently, GRPO trains a more interpretable and robust policy. The consistency penalty prevents reward hacking.

3. **Slot rotation reduces turnover.** 5 concurrent 5-day sub-portfolios, rotating one slot daily → 20% turnover while staying responsive.

4. **Zero-shot generalization is strong.** A model trained on CSI 300 achieves Sharpe 4.03 on CSI 1000 without retraining. The semantic factor descriptions generalize better than pure numeric models.

---

## Application to George's 146-Strategy Library

**Round 33 concept:**
- Map each of the 146 strategies to its factor category: momentum, mean-reversion, event-driven, macro, candle-pattern, dividend
- Build weekly market state summaries from FRED macro data + VIX + SPY/QQQ trends
- Treat each strategy as a "factor" — describe its economic rationale and known failure conditions in natural language
- Train RL gating model: inputs = (strategy descriptions, market state), output = active strategy subset
- Execute: weekly, run only the activated strategy subset on new data; aggregate signals

**Caveats:**
- Original trained on Chinese equity market (CSI 300/1000) — US factors behave differently
- Requires at least 2-3 years of strategy-level performance data as training labels
- 8B model inference cost per day: manageable (~$0.10 per daily inference call)
- Start simpler: rule-based regime gating first (VIX thresholds, SMA trends), use Alpha-R1 as aspirational architecture
