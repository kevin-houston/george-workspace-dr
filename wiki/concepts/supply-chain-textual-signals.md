---
created: 2026-07-18
updated: 2026-07-18
type: research
tags: NLP, LLM-finance, factor-models, supply-chain, cross-sectional-returns
---

# Supply Chain Propagation of Textual Signals

**Source:** arXiv:2606.29290 — "Supply Chain Propagation of Textual Signals: LLM Embeddings and
Cross-Sectional Return Predictability" by Asef Yılkı (Jun 28, 2026)

---

## Core Idea

Standard NLP-based factor models embed a firm's own disclosures (10-K MD&A) into a return predictor.
This paper argues that **inter-firm supply chain linkages propagate information that is priced but
not captured by firm-level embeddings alone.**

The key insight: if a supplier discloses meaningful information in its 10-K, that information is
also relevant for its customers and downstream firms — and markets may take time to price this
propagation, creating cross-sectional alpha.

---

## Methodology

**Data:**
- 255 S&P 500 firms, 2011–2025
- Annual 10-K MD&A sections, embedded using FinBERT
- Supply chain linkages from Bloomberg Supply Chain (SPLC) and SEC Form 10-K supplier disclosures

**Embedding pipeline:**
1. Extract MD&A text from EDGAR 10-K filings for each firm-year
2. Embed using FinBERT (same model as H163/H174 PEAD pipeline)
3. Reduce to principal components — firm-level embedding vector

**Network augmentation:**
- For each firm `i`, compute a network-augmented signal: weighted average of supplier/customer
  embeddings, where weights proportional to supply chain exposure
- Formally: `net_embed_i = α × own_embed_i + (1-α) × Σ_j w_{ij} × embed_j`
- Reduce the augmented embedding to principal components: `net_pc_5` = top 5 network PCs

**Signal construction:**
- Direct: top principal components of own-firm embedding
- Network: top principal components of network-augmented embedding
- Both used as predictors in Fama-MacBeth cross-sectional regressions

---

## Results

| Signal | Newey-West t-stat | Alpha direction |
|---|---|---|
| net_pc_5 (network-augmented PC 5) | **-2.64** | Negative loading |
| own_pc_* (direct firm embedding) | < 2.0 (not significant) | Mixed |

**Long-short portfolio on net_pc_5:**
- Annualized Sharpe ratio: **0.86**
- Fama-French 5-factor alpha: **+7.27% per year** (t = 2.30)
- Survival in out-of-sample tests, placebo experiments, sector-neutralization, and subsample analysis

**Critical finding:** The *own-firm embedding* alone does not generate significant cross-sectional
return predictability. The return signal emerges only after propagation through supply chain linkages.
This suggests **markets underprice supply chain information cascades** — investors focus on direct
disclosures and miss the signal in supplier/customer networks.

---

## Relationship to George's Pipeline

### Connection to H163/H174 (PEAD FinBERT)

The current PEAD pipeline (H163/H174) uses FinBERT on a single firm's 8-K press release. This paper
suggests an upgrade path:

- Embed the 8-K text for any firm that reports earnings
- Identify that firm's major suppliers and customers from SPLC/EDGAR
- Weight the FinBERT score by supply chain exposure: firms that are major suppliers to a reporter
  may see secondary drift effects
- This could generate a PEAD watchlist expansion — catching supply chain beneficiaries of a strong
  earnings report even when those firms haven't reported yet

**Proposed H419 (stub concept):** Supply-chain-augmented PEAD pre-filter
- For each H174 qualifying event (score ≥ 0.18, surprise ≥ 0.02), identify top-3 downstream customers
- Score customer firms' most recent 10-K embedding and weight by supply chain exposure
- Generate secondary watchlist of customer firms for 2-5 day entry window

### Connection to Factor Models (wiki/trading/algorithms/factor-models.md)

The paper validates the broader concept of network-based factor construction:
- Pure firm-level signals on the S&P 500 are crowded and weak
- Network propagation of information creates differentiated signal
- This is consistent with H179 (global equity rotation) and H319 (LLM semantic network, arXiv:2604.19476)

H319 (semantic network: 10-K embeddings + GPT-4o-mini edge classification) is the closest existing
hypothesis. The supply chain version uses *known* inter-firm links rather than embedding-derived
similarity — more robust to specification error.

### Connection to AI Alpha Mining (auto-alpha-discovery.md)

The paper's network embedding approach is an instance of the "graph-augmented alpha factor" paradigm
that XALPHA and FactorEngine also explore. Key difference: supply chain linkages are exogenous
(Bloomberg SPLC) rather than endogenously learned from embeddings, which reduces overfitting risk.

---

## Data Requirements and Practical Barriers

| Requirement | Status | Notes |
|---|---|---|
| FinBERT embeddings (EDGAR 10-K MD&A) | Available | edgartools + ProsusAI/finbert already deployed |
| Supply chain linkage data | **Barrier** | Bloomberg SPLC requires Bloomberg Terminal (~$25k/yr) |
| SEC Form 10-K supplier disclosures | Partial | Free via EDGAR but requires parsing "key suppliers" sections |
| Sector-neutralization | Available | build_sector_cache() from H181 pipeline |

**Practical path without Bloomberg SPLC:**
1. Use SEC EDGAR to extract supplier mentions from 10-K Item 1 (Business Description) sections
2. Cross-reference with Compustat customer segment data (via WRDS, academic access) or
   Revelio supply chain alternative (~$500/mo)
3. Build approximate supply chain linkage graph from free sources

Given the data barrier, this is a **medium-priority research direction** — compelling in theory,
but requires supply chain data access before implementation.

---

## Caveats and Limitations

1. **S&P 500 only**: The 255-firm sample is large-cap US equities. Supply chain signals may be
   stronger in mid/small-cap where analyst coverage is thinner.
2. **Annual frequency**: 10-K embeddings are annual. Supply chain shocks propagate faster than
   annual disclosure cycles — intra-year filings (8-Ks, 10-Qs) would capture this better.
3. **Static linkages**: The paper uses point-in-time supply chain relationships. Relationships
   change dynamically (COVID supply chain disruptions, nearshoring trends).
4. **Survivorship bias**: 255 S&P 500 firms over 2011–2025 — the index composition changed
   significantly. Unclear if point-in-time index is used.
5. **Bloomberg SPLC access**: The paper's supply chain graph requires proprietary data most
   researchers can't replicate.

---

## Cross-references

- [Factor Models & Cross-Sectional Alpha](../trading/algorithms/factor-models.md) — Fama-MacBeth framework
- [Event-Driven Strategies (PEAD)](../trading/algorithms/event-driven.md) — H163/H174 FinBERT pipeline
- [NLP & Alternative Data](../trading/tools/nlp-alternative-data.md) — FinBERT embedding tooling
- [AI-Driven Alpha Factor Discovery](../trading/algorithms/auto-alpha-discovery.md) — H319 semantic network
- [SEC EDGAR Fundamentals](../trading/data-sources/edgar-fundamentals.md) — 10-K data extraction
