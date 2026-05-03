# Semantic Trading: LLM-Driven Clustering for Relationship Discovery

**Source:** arXiv:2512.02436 — "Semantic Trading: Agentic AI for Clustering and Relationship Discovery in Prediction Markets"
**Authors:** Agostino Capponi, Alfio Gliozzo, Brian Zhu
**Date:** December 2025
**Relevance:** R29 — LLM clustering approach; conceptual complement to graph-clustering + cointegration pipeline

---

## Core Idea

Rather than using pure statistical similarity (correlation) to identify candidate pairs, use LLM semantic understanding of market descriptions to cluster markets into coherent topical groups — then only look for statistical relationships within semantically coherent groups.

**Two-stage pipeline:**

1. **Semantic Clustering (LLM stage)**
   - LLM reads contract descriptions and metadata
   - Clusters markets/assets into topical groups based on natural language understanding
   - "Same-outcome" or "opposite-outcome" relationship types are identified

2. **Statistical Validation (statistical stage)**
   - Within each semantic cluster, test for empirical outcome dependence
   - Only keeps pairs where both semantic structure AND statistical evidence align

---

## Performance Results (Polymarket data, Oct 2021–Nov 2025)

- Relationship identification accuracy: **60–70%** (correctly identifies same/opposite outcome pairs)
- Trading strategy returns: **~20% average over week-long horizons**

---

## Domain: Prediction Markets (Not Equities)

This paper uses Polymarket (binary event prediction markets), not equity prices. The semantic clustering approach is domain-specific:
- Contract descriptions are short, explicit text (e.g., "Will Bitcoin exceed $100K by Dec 2025?")
- LLM can directly read and cluster these descriptions
- Equity pairs require inferring the economic relationship from company names + sector context

---

## Adaptation Notes for Equity R29

The Semantic Trading clustering idea is already implicitly captured in R29's LLM economic plausibility filter (arXiv:2602.07048). However, one useful adaptation:

**Pre-filter idea:** Before running the full pipeline, use a fast LLM semantic clustering step to group all S&P 500 stocks into 20-30 "economic relationship clusters" (supply chain, competitors, end market exposure, etc.) — then only test cointegration within the same cluster.

This would complement rather than replace the SPONGEsym statistical clustering (which uses return correlations). The two approaches are orthogonal:
- SPONGEsym: "Do these stocks statistically co-move in residuals?"
- Semantic clustering: "Do these stocks have a known economic relationship?"
- Best pairs: appear in BOTH clusters

**Implementation cost:** One-time LLM call per stock (e.g., "In 2-3 sentences, describe the main business and what economic factors drive this company's stock.") → embed descriptions → cluster on embeddings. ~500 calls × $0.001 = $0.50 one-time cost.

---

## Assessment

Strong conceptual paper, moderate direct applicability. The prediction market domain limits direct replication. Most value for R29 is the idea of semantic pre-clustering to narrow the candidate pair space — already partially implemented via Stage 0.5 (SPONGEsym) and Stage 2 (LLM plausibility score).
