# R35b Concept: Attention Factors for Statistical Arbitrage

**Source:** Epstein, Wang, Choi, Pelger (Stanford) — "Attention Factors for Statistical Arbitrage"  
**arXiv:** 2510.11616 | **Venue:** ACM ICAIF 2025  
**Staged:** 2026-04-14

---

## Core Idea

Replace the two-step pipeline (factor estimation → signal learning) with a **joint one-step optimization**:
1. **Attention Factor Construction** — Cross-sectional attention layer over firm characteristics → K=30 factor portfolios
2. **Residual Portfolio** — Project out the factor component → idiosyncratic return signal (ε)
3. **LongConv Signal** — Single-layer long convolution reads 30-day residual history → portfolio weights
4. **Training objective** — Maximize net-of-cost Sharpe ratio (5bps/turnover + 1bp shorting cost)

---

## Key Numbers

| Model | Net Sharpe | Annual Net Return |
|---|---|---|
| **Attention Factors (K=30)** | **2.28** | **9.52%** |
| PCA Factors (K=30) | 1.57 | 8.47% |
| OU Thresholding (PCA) | -6.45 | -14.74% |
| Market (SPX) | 0.42 | 8.61% |

- 24-year OOS: January 1998–December 2021
- Universe: 500 largest US stocks, 39 firm characteristics
- Market beta: ~0.05–0.07 (effectively market-neutral)

---

## Critical Insights for Current Framework

1. **Past returns dominate fundamentals** — Momentum/reversal characteristics are load-bearing (-62% SR if removed). Value/profitability chars contribute marginally. Implication: for current pairs harness, ensure factor residualization uses momentum-aware factors.

2. **Weak factors matter** — Don't prune to top-K by variance explained. Factors 9-30 that explain little variance still add meaningful net Sharpe. Use validation Sharpe to select K, not scree plot.

3. **Joint optimization is non-negotiable** — Cost-unaware factor construction (PCA) leaves 45% net SR on the table. The two-step decoupling is the root cause.

4. **LongConv > LSTM** for residual signal — O(T log T) scaling, better long-range memory, single layer sufficient. Lookback 30 days.

5. **OU-thresholding collapses after costs** — Gross SR 0.18 → Net SR -6.45. Classical mean-reversion signals trigger excessive rebalancing. **Near-term fix for R29: optimize OU thresholds against NET-OF-COST Sharpe on validation set.**

---

## Implementation Path

### Near-term (low effort, applicable to R29)
- Retrain OU entry/exit thresholds using net-of-cost Sharpe on validation set
- Add 5bps/unit-turnover cost term to threshold grid search objective
- Expected improvement: materially reduces excess trading; should lift net Sharpe

### Full R35b (high effort, new round)
- Gather firm characteristics for pairs universe (CRSP/Compustat or equivalent)
  - Must-have: past returns (r2_1, r12_2, r12_7, r36_13, ST_Rev, Ret_D1, Ret_W1)
  - Nice-to-have: volume, spread, beta, volatility
  - Skip: value, investment, profitability (marginal benefit)
- Implement attention factor construction (PyTorch):
  - Embedding: X̃_t = X_t · W^K (W^K ∈ ℝ^(M×32))
  - Factor weights: ω^F = Softmax(Q · X̃^T / √32), Q ∈ ℝ^(K×32) learnable
  - Factor loadings: β = ω^F (ω^F · ω^F^T + λI)^{-1} (ridge, closed-form)
  - Residuals: ε = R - β^T · F
- Implement LongConv signal on 30-day residual window
- Train joint objective: maximize [Net Sharpe] + λ_VAR·(1/N)Σ(1 - Var(ε_i)/Var(R_i))
  - λ_VAR = 100 ensures factors actually explain cross-sectional variance

### Hyperparameters (from paper)
- d=32, K=30, dropout=0.1, λ_squash=0.001
- Adam, lr=0.003, weight_decay=0.05 (LongConv only)
- Rolling window: 8yr train, retrain every 1yr, last 2yr of training = validation
- 30 epochs

---

## Risk Assessment

- **HIGH complexity**: Requires PyTorch training loop, CRSP-equivalent characteristic data (may need Compustat)
- **Data barrier**: 39 firm characteristics need a reliable source — Sharadar/WRDS or equivalent
- **Suggest**: Run as R35b after R33 (Drift Regimes) and R34 (AlphaLogics-style factor mining) complete
- **Near-term win**: Just adopt cost-aware threshold calibration for R29 (1-2 hours of work, potentially significant impact)

---

## No public code — paper provides sufficient implementation detail to reproduce.
Contact: mpelger@stanford.edu
