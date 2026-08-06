---
created: 2026-08-06
updated: 2026-08-06
type: source_summary
authors: Boris Belyakov (HSE University, MIEM Faculty, Moscow)
published: 20 Jul 2026 (arXiv), accepted Financial Innovation (Springer)
source: arXiv:2607.18001
url: https://arxiv.org/abs/2607.18001
---

# AlphaZeroBeta: Deep Reinforcement Learning for Market-Neutral Portfolios — Belyakov 2026

**Authors:** Boris Belyakov (HSE University, MIEM Faculty, Moscow)
**Venue:** arXiv:2607.18001, submitted 20 Jul 2026; accepted for publication in *Financial Innovation* (Springer). 59 pages, 10 figures.

This paper occupies a genuinely open slot in the wiki: our RL-for-trading coverage ([Deep RL for Trading](../algorithms/deep-rl-trading.md), [DeePM](../algorithms/deepm-regime-portfolio.md), [SciPhy RL Neural-BL Portfolio](../algorithms/sciphy-rl-neural-bl-portfolio.md), [E2E Portfolio Policies](../algorithms/e2e-portfolio-policies.md)) trains agents to pick *what* to hold and *how much*, but none of it explicitly enforces **dollar/market-neutrality as a reward-shaped training objective** — every prior RL page in this wiki treats beta exposure as an emergent property, not a constraint the network is directly penalized for violating. AlphaZeroBeta bakes correlation-to-benchmark into the loss function itself.

---

## Core Idea

A CNN-GRU encoder (convolutional layers extract local price-pattern features, a GRU aggregates them over the lookback window) feeds a **Recurrent PPO** policy network that outputs raw portfolio weights. Those weights are then **projected onto an ℓ1-ball** at every rebalance — a hard mathematical constraint (not just a soft penalty) that caps gross exposure and forces long and short legs toward balance, guaranteeing the *shape* of a market-neutral book regardless of what the network learns.

On top of that structural constraint, the **reward function** is explicitly composite:

```
reward = risk_adjusted_excess_return
         − λ1 * corr(portfolio_return, benchmark_return)   # λ1 = 0.5
         − λ2 * turnover                                    # λ2 = 0.001
```

The correlation penalty (λ1=0.5) is the load-bearing term — it's what separates this from a generic long-short RL policy that merely *tends* toward low beta. The paper's own ablation (see below) shows removing it is catastrophic for the neutrality claim, not just a modest degradation.

---

## Backtest Design

- **Universe:** 7 major equity indices tested independently — S&P 500, NASDAQ-100, DJIA, FTSE 100, DAX, Hang Seng, SSE Composite (US + UK + Germany + Hong Kong + China — genuine cross-market test, not a single-country result dressed up as general)
- **Period:** 2014–2024, walk-forward validated across **K=22 rolling folds × 9 random seeds** (198 total train/test runs) — a materially more rigorous OOS protocol than a single IS/OOS split
- **Baselines:** Index buy-and-hold, Max-Sharpe (SLSQP convex optimizer), Min-Correlation Portfolio — all three are legitimate "should be hard to beat" benchmarks, not strawmen

---

## Results

| Metric | AlphaZeroBeta | Best baseline (avg across 3) |
|---|---|---|
| Average Sharpe (7 markets) | **1.25** (cross-market std 0.30) | 0.70 (std 0.19) |
| Sharpe range | 0.86 (DAX) – 1.63 (SSE Composite) | — |
| Correlation to underlying index | **within ±0.15, all 7 markets** | not neutrality-targeted |

**Ablation (paper's Table B1) — removing the correlation-penalty term (λ1=0):**
- Sharpe drops 30–45% relative to the full reward
- Correlation to benchmark drifts to **0.4–0.6** — i.e. without the explicit penalty, a pure return-maximizing PPO policy does NOT discover market-neutrality on its own; the reward shaping is doing real work, not window dressing.

**Factor attribution:** an extended Fama-French 5 + Carhart momentum + short-term reversal + QMJ regression finds residual alpha survives after controlling for known factors — i.e. the return isn't just a repackaged factor tilt (a check this wiki's own [Alpha Illusion checklist](../algorithms/llm-alpha-validation.md) repeatedly flags as missing from weaker RL papers).

---

## Why This Matters for Our Pipeline

1. **Direct architectural contrast with our RL coverage.** [Deep RL for Trading](../algorithms/deep-rl-trading.md)'s honest-OOS benchmark table (DDPG-TiDE 1.13, PPO+A2C+DDPG ensemble beats DJIA B&H, TD3 2.68 cherry-picked) has nothing that targets neutrality explicitly — H204 (queued PPO ensemble vs H198) inherits whatever correlation-to-SPY the policy happens to converge on. AlphaZeroBeta's ℓ1-ball projection + correlation-penalty reward is a concrete, implementable pattern for making a future RL hypothesis *design for* low correlation from the start rather than measuring it post-hoc and hoping.
2. **Relevant to our stated diversification gap.** Per [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md), the production blend's biggest unmet need is genuinely SPY-uncorrelated alpha — H311 (static multi-asset, Corr~0.3-0.5), H261b (commodity trend, Corr(SPY)=0.218) are the best entries so far, both non-RL. A dollar-neutral RL sleeve that holds Corr ≤ 0.15 *by construction* (not by luck of a favorable backtest window) would be a structurally different diversifier than anything currently in the blend if it replicates.
3. **US equities (S&P 500) is one of the 7 tested markets** — Sharpe not broken out per-index beyond the 0.86–1.63 range and SSE Composite being the top performer, so the S&P 500-specific number needs pulling from the full results table before treating this as validated on our actual universe; flag this as the first thing to check before scoping a hypothesis.
4. **λ1/λ2 hyperparameters are disclosed** (0.5 correlation penalty, 0.001 turnover penalty) — unlike many RL papers that bury reward-shaping constants, these are copy-pasteable starting points for a from-scratch PyTorch implementation.

---

## Caveats

- **Single-author paper, HSE Moscow** — not a major-lab byline (no Oxford-Man/Two Sigma/etc. affiliation this wiki usually cross-checks against); treat the headline Sharpe 1.25 as a claim to independently replicate, not an established result, until it's been checked against our own free-data pipeline.
- **CNN-GRU + PPO is a non-trivial implementation lift** — requires a custom Gym-style trading environment with the ℓ1-ball projection layer, RL training infrastructure (stable-baselines3 or similar), and materially more engineering than our existing rule-based H-series scripts. This is a "stub + scope carefully" candidate, not a same-night backtest.
- **No transaction-cost-at-realistic-bps table disclosed in the abstract-level summary** — the turnover penalty (λ2=0.001) exists in training but whether reported Sharpe 1.25 is pre- or post-realistic-slippage needs verification from the full paper before trusting the headline number, consistent with this wiki's standard transaction-cost skepticism ([Transaction Cost Modeling](../backtesting/transaction-costs.md)).
- **Financial Innovation (Springer) is a legitimate but not top-tier finance journal** — acceptance there is a mild positive signal (peer review happened) but shouldn't be weighted like a Journal of Finance / JFE placement.

---

## Cross-References

- [Deep RL for Trading](../algorithms/deep-rl-trading.md) — existing RL coverage this extends; H204 PPO ensemble queue item
- [DeePM — Regime-Robust Deep Learning Portfolio](../algorithms/deepm-regime-portfolio.md) — nearest architectural cousin (V-VSN+LSTM+GAT, also reward/loss-engineered for robustness)
- [SciPhy RL Neural-BL Portfolio](../algorithms/sciphy-rl-neural-bl-portfolio.md) — another RL portfolio-construction page to compare reward design against
- [Strategy Blending & Correlation Management](../backtesting/strategy-blending-correlation.md) — production diversification gap this could address if replicated
- [Long/Short Equity](../algorithms/long-short-equity.md) — dollar-neutral 130/30 construction context, non-RL comparison point
- [Alpha Illusion — LLM Validation Checklist](../algorithms/llm-alpha-validation.md) — factor-attribution discipline this paper actually follows (unlike many RL/LLM trading papers this wiki has flagged)

**Proposed next hypothesis (not staged as a full hypothesis tonight — flagged in dream cycle scan as a scoping candidate):** if pursued, scope narrowly: replicate the ℓ1-ball-projected PPO + correlation-penalty reward on the H198/H241 S&P 500 universe (not all 7 international markets), IS 2013-2020/OOS 2021-2026 matched to our standard split, explicit post-cost Sharpe at 5bp/10bp, and a hard gate of Corr(SPY) ≤ 0.20 AND OOS Sharpe > 1.0 — the differentiator to prove is the *neutrality*, not just raw Sharpe (which H417/H492/H493 already beat handily at 3-5+).
