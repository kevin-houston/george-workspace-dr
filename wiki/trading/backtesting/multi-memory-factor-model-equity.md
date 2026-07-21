---
type: backtesting-methodology
title: Multi-Memory Factor Model of US Equity Returns
description: Spectral generalization of the Lo-MacKinlay variance ratio decomposing US equity returns into five persistent/antipersistent memory factors. Identifies 1988 volatility regime shift. Return and volatility memory channels are structurally decoupled — key implication for cross-factor signal design.
tags: [factor-models, memory, variance-ratio, regime-detection, volatility, equity-structure, signal-design]
updated: 2026-07-20
---

# Multi-Memory Factor Model of US Equity Returns

**Source:** arXiv:2607.03858 (Anders G. Frøseth, July 2026) — "A Spectral Generalisation of the Variance Ratio: Eigenstructure of Long-Horizon Portfolio Covariance and a Multi-Memory Factor Model of U.S. Equity Returns"

## Background

The Lo-MacKinlay (1988) variance ratio tests whether returns exhibit mean reversion (anti-persistence) or momentum (persistence) at different horizons. Frøseth (2026) extends this single-asset VR test to a **multivariate spectral decomposition** across portfolios, extracting the eigenstructure of long-horizon portfolio covariance and identifying a stable five-factor memory model.

Unlike the standard Fama-French factor taxonomy (which categorizes by economic theme: market, size, value, profitability, investment), this model categorizes factors by **temporal horizon of predictability** — directly relevant to choosing signal windows for systematic strategies.

## The Five Memory Factors

The spectral decomposition identifies five eigenvalues that dominate long-horizon covariance across portfolio panels:

| Factor | Memory Type | Approximate Horizon | Economic Interpretation |
|--------|-------------|---------------------|------------------------|
| F1 | Strongly persistent | 4+ years | Long-run trend; value premium convergence zone |
| F2 | Antipersistent | 6-18 months | Intermediate-horizon mean reversion |
| F3 | Multi-scale / mixed | 1-6 months | Cross-sectional momentum — the classical anomaly window |
| F4 | Short antipersistent | 1-4 weeks | Short-term reversal zone; microstructure effects |
| F5 | Weak / noise | Days-weeks | Microstructure noise floor |

**Cross-sectional robustness:** The same five-factor structure appears consistently across:
- Fama-French 49-industry portfolios
- Fama-French 100 size × book-to-market sorted portfolios
- Pre-1988 and post-1988 US subsamples
- European equity markets

The robustness across sorting variables and international markets is strong evidence that this is a structural property of equity return dynamics, not a dataset artifact.

## The 1988 Volatility Regime Shift

### Discovery

Using bootstrap confidence bands on the spectral estimator, Frøseth identifies a **structural regime change in US equity volatility memory circa 1988** — notably, *not* the commonly assumed 1998 breakpoint (often attributed to the dot-com era or late-1990s equity culture shift).

Before 1988:
- Slowest component of the volatility cascade: effective memory ~2 years

After 1988:
- Same component lengthened to ~4 years
- Consistent with increasing institutional holding periods, rise of index funds, and algorithmic market-making extending vol persistence

### Implications for Backtesting Design

This finding matters for regime detection models (H251 HMM, H249 regime-conditional, H383 HMM+RL):

1. **IS data should start no earlier than 1990** for volatility-based regime models — pre-1988 data belongs to a structurally different volatility regime
2. **George's IS periods are correctly chosen**: canonical IS 2008-2017 and standard IS 2013-2020 both fall in the post-1988 regime
3. The 1998 breakpoint commonly cited in academic literature may be a second-order effect layered on top of the 1988 structural change

## Return vs. Volatility Memory Decoupling

### The Core Finding

The paper's second major result: **return-channel and volatility-channel memory are structurally decoupled**.

> "Characteristics that predict return-momentum patterns therefore need not predict volatility-persistence patterns — cross-channel loadings show anti-alignment rather than shared structure."

In mathematical terms: the eigenvectors of the return-memory covariance matrix are **not** aligned with those of the volatility-memory covariance matrix — they span largely orthogonal subspaces.

### Why This Matters for Signal Design

**Implication 1 — Do not treat return-predictive and volatility-predictive features as interchangeable:**
- Momentum signals (H198 6-1m, IMOM6, IMOM12) predict *return* continuation → return channel (F3)
- Low-volatility signals (H270 LowVol tiebreaker, H192 BAB) predict *volatility* behavior → volatility channel
- The two should be treated as orthogonal alpha sources, not substitutes

**Implication 2 — Multiplicative interactions across channels are theoretically suspect:**
- H413 NOT CONFIRMED result (BAB × lagged realized-vol regime gate) is consistent with the decoupling finding: cross-channel multiplicative interactions don't compound alpha, they introduce noise
- H398's additive composite (0.25×IMOM6 + 0.25×MOM60 + 0.25×LowVol + 0.25×IMOM12) is the correct form — additive combination of channel-orthogonal signals, not multiplicative gates

**Implication 3 — The H411/H416 drift gate is a pure return-channel signal:**
- 20d positive-day fraction measures return-channel F3/F4 persistence
- The 1/price value signal is F1/F2 (long-run value convergence)
- Their combination is an intra-return-channel interaction — theoretically coherent
- Adding a volatility-channel gate (VIX, realized vol) on top would be cross-channel and theoretically suspect

## Connection to Production Portfolio Signals

### H198 Composite (H395 Var C / H398)

The four signals decompose across memory factors:

| Signal | Memory Channel | Factor Zone | Role |
|--------|----------------|-------------|------|
| IMOM6 (illusion momentum 6m) | Return | F3 | Core momentum |
| MOM60 (12-1m skip-month) | Return | F3/F2 boundary | Extended momentum |
| LowVol (low volatility rank) | Volatility | Volatility-channel | Diversifying signal |
| IMOM12 (compound-arithmetic gap 12m) | Return | F3/F1 boundary | Long-horizon consistency |

H398's orthogonality finding (IMOM12 corr with IMOM6=0.484, MOM60=0.479) is explained: IMOM12 captures a different spectral regime (longer-horizon F1/F3 boundary) from IMOM6's F3 core.

### IBS Mean-Reversion (H062-H112 Production)

IBS exploits F4 — the short-term antipersistent zone (1-4 weeks). The spectral model provides theoretical grounding: there IS a genuine memory mode at this frequency in equity returns, justifying IBS as a mechanistic (not purely empirical) signal.

### H411/H416 Drift × Value (Production Research)

The 20d drift gate (F3/F4 boundary) combined with 1/price value (slow F1 component) represents a multi-frequency signal: fast-memory drift filter selects a subset of stocks for which the slow-memory value signal is activated. The spectral framework suggests this multi-scale activation is sound — you're combining signals from compatible regions of the memory spectrum.

## The Spectral Method Explained

The key technical innovation is a **multivariate generalization of the Lo-MacKinlay variance ratio** that:
1. Computes the cross-asset covariance matrix at multiple horizons h = 2, 4, 8, ..., H trading days
2. Stacks these into a 3D tensor indexed by horizon
3. Contracts the horizon dimension using spectral weights → eigendecomposition of the resulting matrix
4. Each eigenvector = "memory mode" spanning specific frequency bands; each eigenvalue = strength of that memory signature

This connects to signal processing: the eigenvectors are the "principal oscillation patterns" of equity return memory across scales.

## Summary for Practitioners

1. **Five stable memory modes exist in US equity returns**: persistent (F1), intermediate reverting (F2), momentum (F3), short reversal (F4), noise (F5)
2. **1988 is the correct structural breakpoint** for volatility-based models — not 1998
3. **Return and volatility predictors are structurally orthogonal** — design composites additively, not multiplicatively
4. **Signal windows are theoretically grounded**: 1-6 month momentum (F3), 10-day reversal (F4), 20-day drift gate (F3/F4 boundary)
5. **H398 additive composite design is correct**: mixes return-channel and volatility-channel signals additively

## Cross-References

- [Factor Models & Cross-Sectional Alpha](../algorithms/factor-models.md) — Fama-French structure
- [Regime Detection](../algorithms/regime-detection.md) — HMM/VIX regime approaches, 1988 vs 1998 breakpoints
- [Signal Half-Life & Alpha Decay](signal-halflife.md) — empirical decay rates across factors
- [IBS Mean-Reversion](../algorithms/ibs-mean-reversion.md) — short-term antipersistence (F4 zone)
- [Momentum Strategies](../algorithms/momentum-strategies.md) — H198 6-1m, IMOM, MOM60 (F3 zone)
- [Smart Money Concepts — Order Blocks](../algorithms/smart-money-concepts-ict.md) — OB filter as implicit F3/F4 regime gate
- [Look-Ahead-Freedom as Temporal Non-Interference](lookahead-formal-verification.md) — pipeline integrity for spectral feature computation
