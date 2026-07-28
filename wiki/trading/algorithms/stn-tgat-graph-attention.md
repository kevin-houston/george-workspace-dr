---
title: STN-TGAT — Graph Attention Networks for Cross-Sectional Portfolio Construction
tags: deep-learning, graph-neural-network, portfolio-construction, cross-sectional, momentum, NMI, attention
added: 2026-07-27
category: Trading / Algorithms
---

# STN-TGAT — Graph Attention Networks for Cross-Sectional Portfolio Construction

**Source**: arXiv:2607.19385 (Guo, Lu & Zhang, Jul 2026) "STN-TGAT: Top-K Portfolio Construction via Prior-Guided Graph Attention with Learnable Soft-Threshold Sparsification"

## Overview

STN-TGAT (Soft-Threshold NMI-prior Transformer Graph Attention Network) addresses a fundamental limitation of prior cross-sectional stock selection models: they process each stock's time series independently, missing inter-stock dependencies that carry predictive information. The paper proposes two components that work jointly:

1. **Temporal Transformer**: captures long-horizon sequential patterns in each stock's daily returns
2. **Graph Attention Network (GAT)**: models dynamic pairwise dependencies between stocks

---

## Key Innovations

### NMI-Based Prior Graph
The standard approach builds stock correlation graphs from Pearson correlation coefficients, which are noisy and include many spurious edges (e.g., correlated simply because both stocks had the same sector beta).

STN-TGAT uses **Normalized Mutual Information (NMI)** to build the prior graph:
- NMI captures non-linear dependencies, not just linear correlation
- Computed over a rolling lookback window (60 days)
- Applied strictly on lagged data to prevent look-ahead bias

### Soft-Threshold Sparsification
Rather than a fixed edge-count cutoff, STN-TGAT learns a soft threshold per layer:

```
edge_weight = max(0, NMI - threshold)
```

where `threshold` is a learned parameter. This creates a sparse graph that:
- Removes weak/noisy edges (NMI below threshold → zero weight)
- Preserves strong informative connections
- Adapts dynamically as market structure changes

### Decision-Aligned Training
Loss function directly optimizes portfolio return (Sharpe-like objective), not a surrogate ranking loss. This aligns training with actual investment goal — avoiding the misalignment between IC/rank-accuracy metrics and portfolio returns that plagues many stock prediction models.

---

## Experimental Results

- **Universe**: Top-50 S&P 500 constituents by market cap
- **Strategy**: Top-5 selection with explicit weight allocation and TC adjustment
- **Evaluation**: predictive accuracy + portfolio returns (both measured)
- **Conclusion**: STN-TGAT consistently outperforms benchmark models (Transformer-only, GAT-only, static correlation graph)

Key advantage over simple factor models: **the graph structure adapts to regime changes**. In a sector rotation, the NMI graph captures the emerging correlations between newly-correlated stocks before factor loadings update.

---

## H464 Design — H198 Application

H464 ports STN-TGAT to the H198 30-stock NASDAQ large-cap universe.

**Adaptation challenges**:
1. **Small universe (n=30)**: NMI graph has 30×30 = 900 potential edges; with 60-day NMI lookback, only ~60 data points per edge — statistically noisy. Solution: use longer lookback (120 days) or reduce sparsification threshold.

2. **Look-ahead in prior graph**: NMI must be computed from returns at t-1 for predictions at t. Full recomputation each period is expensive; rolling update is needed.

3. **PyTorch Geometric**: requires GNN infrastructure not in current venv. Lightweight alternative: static GICS sector adjacency matrix as prior graph (binary: same sector = 1.0, different sector = 0.0).

**Simplified proxy architecture**:
```
Signal = α × Transformer_score(stock_i) + (1-α) × Σ_j(w_ij × Transformer_score(stock_j))
```
where w_ij = sector_adjacency[i,j] / Σ_j(sector_adjacency[i,j]) (sector peer averaging). This is a tractable approximation without full GNN training.

---

## Comparison to Related Methods

| Method | Temporal | Cross-Sectional | Prior Knowledge | Look-Ahead Safe |
|--------|----------|-----------------|-----------------|-----------------|
| H198 6-1m momentum | rolling sum | none | none | yes (shift(1)) |
| H395 IMOM6+MOM60+LowVol | rolling | none | volatility proxy | yes |
| H456 AFT (regime-gated) | Transformer | none | regime labels | yes (corrected) |
| H457 PRISM-VQ | MoE | codebook | factor priors | yes |
| **STN-TGAT (H464)** | **Transformer** | **GAT** | **NMI graph** | **yes (lagged)** |

**Key differentiation**: STN-TGAT is the only approach that explicitly models pairwise stock relationships at each prediction step, not just at factor construction time.

---

## Relevance to H198 Family

The H198 NASDAQ large-cap universe is dominated by tech mega-caps with high mutual correlations (AAPL, MSFT, NVDA, META, GOOGL all correlate at ρ > 0.70 in 2024-2026). This creates a situation where:

- Simple momentum picks from a highly-correlated cluster → low effective diversification
- STN-TGAT's GAT layer would assign high NMI weights to all tech stocks, potentially concentrating further
- **The graph's value on H198 may be limited**: sector homogeneity means the "cross-sectional relational" information is already captured by the momentum factor

**Contrast**: On a heterogeneous universe (H026's 25 ETFs spanning bonds, commodities, equities, alts), the NMI graph would capture meaningful inter-asset regime dynamics not in any single momentum factor. H464 should consider H026 universe as a secondary test.

---

## Cross-References
- [Attention Mechanisms and Vector Quantization for Cross-Sectional Factor Models](attention-cross-sectional-factor-models.md) — H456 AFT + H457 PRISM-VQ (related deep learning approaches)
- [Momentum Strategies](momentum-strategies.md) — H198 baseline and confirmed family
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — network effects in trading signal propagation
- [Factor Models & Cross-Sectional Alpha](factor-models.md) — Fama-French context for cross-sectional models
- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — H381/H382 LLM factor mining context
