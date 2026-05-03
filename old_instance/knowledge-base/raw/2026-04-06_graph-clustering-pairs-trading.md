# Graph Clustering for Statistical Arbitrage — SPONGEsym on Residual Correlations

**Source:** arXiv:2406.10695 — "Statistical arbitrage in multi-pair trading strategy based on graph clustering algorithms in US equities market"
**Date:** June 2024
**Relevance:** R29 — equity pairs trading with LLM semantic filter

---

## Core Methodology

The paper constructs a signed weighted graph of stocks where edge weights are 60-day rolling correlations of **factor-residualized returns** (not raw returns). Key innovation: using residuals already removes common market/sector exposure before building the correlation graph.

**Clustering algorithm: SPONGEsym**
- Stands for: Signed Positive Over Negative Generalized Eigenproblem (symmetric variant)
- Decomposes correlation matrix into separate positive and negative components
- Assigns stocks to clusters where intra-cluster correlation is maximally positive
- Optimal cluster count: number of eigenvectors explaining 90% of variance

**Pair selection:** Only pairs within the same positive cluster are candidates for cointegration testing. This eliminates the combinatorial explosion of testing all N*(N-1)/2 pairs in a 500-stock universe.

**Signal classification:** 5 ensemble ML classifiers filter individual trade signals using:
- Graph-based features: vertex degree, cluster density, centrality
- Traditional features: return deviations, spread z-score
- Time-variant take-profit: thresholds decrease as holding period extends (forces closure)
- Dynamic stop-loss: scales with ML signal probability estimate

**Position sizing:** Kelly criterion — long and short fractions sum to unity. Portfolios rebalanced every 10 trading days with 30-day lookback windows for cluster identification.

---

## Performance Results

Universe: S&P 500 historical constituents (avoiding survivorship bias)
Period: January 2000 – December 2022
Out-of-sample test: March 2006 – December 2022

| Metric | This Strategy | Cartea et al. Baseline |
|--------|---------------|----------------------|
| Annualized Return | 49.33% | 12.2% |
| Information Ratio | 1.30 | 1.10 |
| Sortino Ratio | 3.38 | — |
| Max Drawdown | 31.98% | — |

Note: max drawdown of ~32% is elevated — position sizing/risk management critical.

---

## Application to R29

The R29 pipeline now has 4 stages:

**Stage 0:** Factor residualization (already staged 2026-04-04)
- Regress each stock's returns on (SPY, sector ETF)
- Use residuals for all subsequent analysis

**Stage 0.5 (NEW):** SPONGEsym graph clustering
- Build 60-day correlation matrix of residual returns
- Apply SPONGEsym → identify positive-correlation clusters
- Only proceed with within-cluster pairs (reduces candidate set from ~125,000 to ~hundreds)

**Stage 1:** Engle-Granger cointegration test on within-cluster pairs

**Stage 2:** LLM economic plausibility score (arXiv:2602.07048)
- "Is there a coherent economic reason why [A] and [B] would mean-revert toward each other?"
- Score 0-100; skip pairs below 40

**Stage 3:** Trade the spread; Kelly-weighted position sizing; take-profit/stop-loss

---

## Implementation Notes

- SPONGEsym is available in the `SPONGE` Python library or can be implemented from scratch with scipy sparse solvers
- 60-day window is standard; shorter windows (30d) pick up recent relationships, longer (90d) are more stable
- Cluster count (eigen-90%) typically yields 5-15 clusters for S&P 500
- Rebalance clusters monthly (not daily) to reduce turnover
