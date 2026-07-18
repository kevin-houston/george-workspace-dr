---
title: End-to-End Parametric Portfolio Policies — When Do AI Models Beat Simple Rules?
tags: deep-learning, portfolio-optimization, futures-timing, TSMOM, transformer, LSTM
added: 2026-07-17
source: arXiv:2607.00475
category: Trading Algorithms
---

# End-to-End Parametric Portfolio Policies — When Do AI Models Beat Simple Rules?

**Paper:** Pollok & Robik (2026), arXiv:2607.00475, submitted July 1 2026.
**Focus:** Direct policy learning (market state → portfolio weights) vs. two-step approach (forecast → optimize) on 16 CME futures. Answers: when do transformers and LSTMs beat equal weighting, risk parity, and TSMOM?

---

## Core Innovation: End-to-End Policy

The **standard two-step approach** in systematic trading:
1. Forecast returns (linear regression, ML model, or factor model)
2. Optimize weights given forecasts (MVO, risk parity, Kelly)

The **end-to-end approach** collapses this into one step:
- Input: current market state (price/vol/macro features)
- Output: portfolio weights directly
- Loss: differentiable Sharpe ratio (backpropagated through the weight allocation)

This is structurally similar to [Deep RL for Trading](deep-rl-trading.md) but the policy is *parametric* (supervised on realized returns) rather than reinforcement-trained. Closer to DeepPM ([DeePM page](deepm-regime-portfolio.md)) than to PPO/SAC.

---

## Experimental Setup

- **Universe:** 16 most liquid CME futures (equity indices, bonds, commodities, currencies)
- **Data:** Full history of each futures contract; in-sample / out-of-sample splits not explicitly disclosed, but OOS period spans multiple macro regimes
- **Architectures tested:**
  - LSTM (Long Short-Term Memory): sequential memory, suited for trending signals
  - Transformer: attention-based, captures non-sequential feature interactions
- **Baselines:**
  - Equal weighting (EW)
  - Risk parity (inverse-vol weighting)
  - Time-series momentum (TSMOM) — the primary benchmark per [IBS Mean-Reversion](ibs-mean-reversion.md) and commodity trend context

---

## Key Results

### Gross Performance
- **Transformer > LSTM > risk parity** on the pooled cross-asset portfolio (gross Sharpe)
- Both AI models beat equal weighting on the full portfolio
- Sub-asset class performance varies: futures timing helps most on equity indices and bonds, less so on commodities and FX

### Transaction Costs — The Critical Divergence
| Model | Gross ranking | Net ranking | Turnover |
|---|---|---|---|
| Transformer | #1 | #1 | Low (~comparable to TSMOM) |
| LSTM | #2 | **drops significantly** | High (3–5× transformer) |
| TSMOM | #3 | #2 or near-match | Low (monthly rebalance) |
| Risk parity | #4 | #3 | Low |

The **LSTM's gross alpha is largely consumed by trading costs** due to high-frequency weight changes. The transformer's attention mechanism learns to trade less, concentrating on durable signals.

This confirms a general pattern seen across the wiki:
- **H320** (LightGBM crash filter): raw Sharpe 1.274 with non-trivial WF ratio concerns
- **H204** (Deep RL PPO): NOT CONFIRMED due to OOS implementation challenges
- [Signal Half-Life](../backtesting/signal-halflife.md): AI-driven compression of alpha half-life means higher turnover = faster decay

### Sub-Asset Class Findings
- **Equity index futures**: transformers clearly beat TSMOM — momentum is non-linear
- **Bond futures**: transformers and TSMOM perform similarly — duration signal is well-captured by simple momentum
- **Commodity futures**: AI models underperform vs. TSMOM — commodity trends are captured well by simple 12m momentum (aligns with H261b findings)
- **FX futures**: mixed; regime-sensitive

---

## Differentiable Sharpe Ratio Loss

The paper uses:

```
L = -E[r_p] / std(r_p)
```

where `r_p` is the portfolio return at each time step, and the weights are a softmax output of the policy network. This is differentiable end-to-end.

**Key advantage over MSE prediction loss:** optimizing directly for Sharpe aligns the training objective with trading performance rather than forecast accuracy. A highly accurate return forecast that's poorly timed (wrong sign) contributes nothing to the portfolio; the Sharpe-loss captures this.

**Caveat:** Differentiable Sharpe is a *sample* Sharpe over training windows. Noisy in short windows; requires careful window sizing (typically 63-252 days for financial applications).

---

## Comparison to Other End-to-End Work

| Paper | Method | Universe | Key finding |
|---|---|---|---|
| Pollok & Robik 2026 (this) | Transformer/LSTM direct policy | 16 CME futures | Transformer ≈ TSMOM net; LSTM cost-killed |
| [DeePM](deepm-regime-portfolio.md) (arXiv:2601.05975) | Causal Sieve + macro graph prior | 50 futures 2010-2025 | 2× net risk-adjusted vs conventional |
| [FinRL](deep-rl-trading.md) | PPO/SAC RL | Stocks | H204 NOT CONFIRMED — RL instability |
| TSMOM simple baseline | 1-12m momentum sign | All futures | Strong gross; competitive net |

---

## Relevance to George's Trading Stack

### H318: Meta-Agent ETF Rotation Selector
The end-to-end policy concept directly informs **H318** (meta-agent that dynamically weights H026/H045/H041a by regime). Instead of the two-step approach (predict which strategy wins → allocate), a policy network trained with differentiable Sharpe loss could learn the weight allocation directly from market state features.

Key risk: H318's strategy universe is monthly-rebalanced. End-to-end policy at monthly frequency would have very few training observations. Alternative: use it as a feature rather than a policy — let the transformer's attention weights inform which market state favors which strategy.

### Futures Universe vs. ETF Universe
The paper works on liquid futures — no bid-ask spread concerns at the scale tested. Translating to ETFs:
- ETF bid-ask spreads are ~1-3bp vs. futures 0.1-0.3bp
- ETF monthly rebalancing reduces the turnover-cost problem that hurt the LSTM
- Monthly ETF rotation is *already* in the TSMOM regime where the transformer matched TSMOM — suggesting **for our ETF universe, simple TSMOM remains competitive with transformers**

### Design Note for Future Testing
If attempting transformer-based ETF timing:
1. Use **transformer** not LSTM (cost rationale)
2. Loss function: **differentiable Sharpe** not MSE
3. Features: 12m, 6m, 3m returns + VIX + macro regime dummies (SPY 200MA)
4. Horizon: monthly prediction, but train on daily sequences within each month
5. Minimum OOS: 5 years (60 monthly observations minimum for meaningful Sharpe test)

---

## Verdict for George's Pipeline

- **Immediate:** No change to production portfolio. This confirms TSMOM's cost-adjusted competitiveness.
- **H318 design:** Use transformer attention patterns as *features* for meta-learner, not as a direct policy — avoids the sample-size problem of monthly ETF data.
- **Research queue:** If testing end-to-end policies, use transformer architecture and differentiable Sharpe loss; benchmark against TSMOM gross *and* net of realistic costs.

---

## Cross-references

- [Deep RL for Trading](deep-rl-trading.md) — PPO/SAC RL context; H204 NOT CONFIRMED
- [DeePM — Regime-Robust Deep Portfolio Manager](deepm-regime-portfolio.md) — end-to-end approach on 50 futures with macro priors
- [Time-Series Foundation Models](ts-foundation-models.md) — Chronos/TimesFM/Moirai; feature engineering vs standalone signal
- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — FactorEngine dual-mode LLM+BayesHPO context
- [Signal Half-Life & Alpha Decay](../backtesting/signal-halflife.md) — AI compression of momentum half-life
- [Commodity Trend Following](commodity-trend-following.md) — H261b CONFIRMED OOS 0.922 on commodity futures
- [Market Timing Overlays](market-timing-overlays.md) — TSMOM as timing overlay context
- [Factor Models & Cross-Sectional Alpha](factor-models.md) — two-step approach context
