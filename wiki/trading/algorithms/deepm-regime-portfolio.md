---
title: DeePM — Regime-Robust Deep Learning for Macro Portfolio Management
added: 2026-07-07
category: algorithms
url: https://arxiv.org/abs/2601.05975
code: https://github.com/kieranjwood/deepm
---

# DeePM: Regime-Robust Deep Learning for Systematic Macro Portfolio Management

**Paper**: arXiv:2601.05975 | Wood, Roberts, Zohren (Oxford ML, Jan 2026)

## Core Contribution

DeePM (Deep Portfolio Manager) is a structured deep-learning macro portfolio manager trained end-to-end to maximize a robust, risk-adjusted utility. It achieves ~2x net risk-adjusted returns vs conventional approaches and ~50% improvement over the Momentum Transformer architecture, on 50 diversified futures 2010-2025 with realistic transaction costs.

## Three Architectural Innovations

### 1. Directed Delay (Causal Sieve)
Solves the "ragged filtration" problem — different macro data series (GDP, CPI, earnings) arrive asynchronously. The Causal Sieve mechanism learns to prioritize causal impulse-response patterns over information freshness, preventing look-ahead contamination.

### 2. Macroeconomic Graph Prior
Regularizes cross-asset dependence using economic first-principles graph structure. Forces the model to learn economically meaningful co-movement rather than spurious correlations in low-signal-to-noise financial data.

### 3. Distributionally Robust Objective
Optimizes a smooth worst-window penalty as a differentiable proxy for Entropic Value-at-Risk (EVaR). This directly targets tail risk and regime robustness rather than average Sharpe.

## Performance

- Universe: 50 diversified futures (commodities, equity indices, bonds, FX)
- Period: 2010-2025 with realistic transaction costs
- Net risk-adjusted return: ~2x conventional approaches
- vs Momentum Transformer: ~+50% improvement

## Relevance to Production Pipeline

| Hypothesis | Connection |
|-----------|------------|
| H249 (regime-conditional weights) | DeePM's regime-robustness approach complements H249's 4-state engine |
| H318 (meta-agent ETF rotation) | Macroeconomic Graph Prior directly addresses H318's cross-ETF dependence modeling |
| H251 (HMM portfolio) | DeePM outperforms HMM-based approaches; regime learning is implicit not explicit |
| H273 (vol-targeted overlay) | Robust objective function generalizes H273's vol-targeting logic |

## Implementation Notes

- Code available at `github.com/kieranjwood/deepm`
- Same Oxford group (Zohren) as arXiv:2603.01820 (DL time series benchmark)
- Requires PyTorch; futures universe not directly applicable to ETF rotation without adaptation
- Causal Sieve mechanism directly applicable to H198's async macro regime signals

## Related Papers

- arXiv:2603.01820 — same group, DL benchmark on futures confirming rich temporal representations > linear
- arXiv:2507.15876 — CTA trend factor Bayesian decomposition (short vs long horizon blend)
