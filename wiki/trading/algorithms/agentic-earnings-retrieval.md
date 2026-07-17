---
created: 2026-07-16
updated: 2026-07-16
type: concept
category: Trading > Algorithms
source: arXiv:2507.07906
---

# Agentic Retrieval of Topics and Insights from Earnings Calls

Source: Gupta, Bhowmik & Gunow (July 2025). arXiv:2507.07906. Presented at the 2nd Workshop on Financial Information Retrieval in the Era of Generative AI, SIGIR 2025, Padua.

This paper introduces a dynamic LLM-agent system for continuously extracting and organizing **emerging topics** from quarterly earnings calls into a self-evolving knowledge graph (topic ontology). Rather than scoring each call independently with a fixed sentiment model, the system builds a cumulative understanding of what topics are structurally important to each company and flags when a company introduces a new, anomalous topic — a potentially stronger PEAD signal than raw sentiment.

---

## Problem: Static Sentiment Misses Emerging Surprises

The H174 PEAD pipeline uses FinBERT to score the overall sentiment of 8-K press releases. FinBERT produces a single positive/negative/neutral classification per document. This captures aggregate tone but misses a crucial dimension: **topic novelty and emphasis shift**.

Consider these two scenarios:
- **Scenario A**: A company's 8-K is modestly positive. But for the first time, management introduces the word "supply chain constraints" in their guidance section — a new topic that wasn't in any prior quarter's call.
- **Scenario B**: A company's 8-K has the same modestly positive tone. But all topics are familiar continuations of prior quarter themes — cost efficiency, market share, product launches.

FinBERT scores both identically. But Scenario A represents a qualitatively different information event: the **introduction of a new risk or opportunity theme** that analysts have no prior expectation for, creating stronger information asymmetry and thus a larger potential PEAD drift.

Gupta et al.'s system is designed to detect exactly this: the **novelty and hierarchical integration** of topics across quarters, not just within-quarter sentiment.

---

## System Architecture

### Component 1: Topic Extraction Agent

For each earnings call transcript, the agent:
1. **Segments** the call into structural sections: opening remarks, financial results, segment performance, guidance, Q&A (with analyst/exec speaker separation)
2. **Extracts topics** from each section using LLM prompt: "What are the distinct financial topics discussed in this segment? List as concise noun phrases (e.g., 'GPU supply constraints', 'China revenue decline', 'margin expansion from automation')."
3. **Normalizes** topics to remove paraphrase variation: "gross margin headwinds", "margin pressure", and "profitability compression" are mapped to the canonical topic "gross margin pressure"
4. **Assesses novelty**: compares extracted topics against the company's existing topic ontology to determine which are:
   - **Established**: appeared in ≥2 prior quarters
   - **Recurring-but-weakened**: present but with less emphasis than prior quarter
   - **Strengthening**: present with stronger emphasis than prior quarter
   - **Novel**: appears for the first time in this company's earnings history
   - **Discontinued**: was present in prior quarters but absent this quarter

### Component 2: Topic Ontology Manager

The agent maintains a **hierarchical topic ontology** per company:

```
[Company: NVDA]
  ├── Demand drivers
  │     ├── Data center AI [established, strengthening 2024-2026]
  │     ├── Gaming [established, weakening since 2022]
  │     └── Automotive [established, emerging 2025]
  ├── Supply chain
  │     ├── TSMC capacity [established]
  │     └── CoWoS packaging constraints [novel, 2024-Q1]
  ├── Competition
  │     ├── AMD RDNA GPU [established]
  │     └── Custom silicon from hyperscalers [novel, 2025-Q2]
  └── Geographic risk
        ├── China export controls [established, critical]
        └── [DISCONTINUED: US tariff uncertainty, 2023-Q2 → Q3]
```

This ontology is updated after each earnings call and persisted. The agent uses it to assess novelty of topics in the next call.

### Component 3: Insight Retrieval Agent

Given a query (e.g., "What are the most significant new topics introduced in Q4 2025 earnings calls?"), the retrieval agent:
1. **Filters** to companies where novelty score exceeds threshold
2. **Ranks** by estimated information content (novel + high-emphasis > novel + low-emphasis)
3. **Generates** a structured insight: "TSMC (2025-Q4): Introduced 'CoWoS-S capacity expansion' as a new supply chain topic. Prior quarters mentioned general CoWoS tightness; this is the first mention of a specific product line. High novelty score (0.87). Sentiment: positive (guidance raised)."

---

## Evaluation Results

The paper evaluates on a corpus of earnings call transcripts from S&P 500 companies (2020-2025):

- **Ontology coherence**: human judges rated topic clusters as coherent and distinct (4.1/5.0 avg) vs flat topic modeling baselines (3.1/5.0)
- **Topic evolution accuracy**: the system correctly identified 78% of analyst-annotated "material topic changes" across the test set
- **Novel topic recall**: 71% of topics that analysts flagged as "new this quarter" were identified by the system (vs 38% by LDA baseline)

Importantly, the paper does not evaluate **trading performance** — it evaluates information extraction quality. The hypothesis that novel topics → larger PEAD is supported by:
1. H317 findings (H174's 81.8% WR; 77% of events already have EPS beats → remaining variance is qualitative)
2. EarningsInOne (arXiv:2606.29734) finding that qualitative ECT signal peaks next day = tradeable
3. General information asymmetry theory: analyst coverage focuses on expected topics; novel topics require analysts to rebuild models from scratch

---

## Application to PEAD Pipeline

### Current H174 Stack
```
8-K filing text
    → FinBERT score (continuous)
    → EPS surprise filter (≥ 0.02)
    → Score filter (≥ 0.18)
    → OPG entry if both gates pass
```

### Proposed H408 Upgrade
```
8-K filing text + historical earnings transcripts (company ontology)
    → FinBERT score (unchanged)
    → EPS surprise filter (unchanged)
    → Topic novelty score (NEW: proportion of topics that are novel/discontinued)
    → Topic emphasis shift score (NEW: delta in emphasis for key topics vs prior quarter)
    → Composite gate: (score ≥ 0.18 AND surprise ≥ 0.02) OR (score ≥ 0.15 AND novelty ≥ 0.3)
    → OPG entry
```

The composite gate has two paths:
1. **Standard path** (H174 unchanged): high score + high EPS surprise → enter
2. **Novelty path** (H408 new): lower score acceptable if topic novelty is high (information asymmetry mechanism)

The novelty path is the key innovation: events where a company introduces a genuinely new topic for the first time may generate PEAD even when the overall 8-K tone is only moderately positive, because the new topic creates structural uncertainty that takes analysts multiple quarters to fully incorporate.

---

## Implementation Notes

### Transcript source problem
H247 found that FMP transcript API returns 403 on the free plan. Alternatives:
- **EDGAR full-text**: 8-K Item 7.01 (Regulation FD Disclosure) sometimes contains the transcript text or key excerpts
- **AlphaVantage transcripts**: Available (25 req/day limit, sufficient for our H174 universe of ~20 events/year)
- **Alpaca News API**: Covers major earnings events but inconsistent format

For Phase 1, use AlphaVantage transcripts (existing `$ALPHA_VANTAGE_API_KEY`) with fallback to 8-K Item 7.01 EDGAR text.

### Ontology persistence
The company topic ontology should be stored in a JSON file per company:
```
backtesting/paper_trading/earnings_ontology/
    AAPL.json
    NVDA.json
    MSFT.json
    ... (30 stocks in H198 universe)
```

Initialize from first available transcript (likely 2020-2021 for most); update after each earnings quarter.

### Computational cost
- GPT-4o-mini for topic extraction: ~$0.005/call at 2026 pricing; ~20 events/year × 4 sections = ~$0.40/year
- GPT-4o for ontology management and novelty assessment: ~$0.03/event = ~$0.60/year
- **Total**: <$2/year in API costs — negligible

---

## H408 Stub

```
h408_status: STUB (2026-07-16) — Agentic Earnings Topic Ontology as PEAD Pre-Filter.
Source: Gupta, Bhowmik & Gunow (2025) arXiv:2507.07906; SIGIR 2025 FIRE Workshop.
Design:
  Phase 1 — Build topic ontology for H198 30-stock universe using AlphaVantage transcripts
    (2022-2024 history, 25 req/day limit). Store per-company JSON at
    backtesting/paper_trading/earnings_ontology/TICKER.json.
  Phase 2 — For each OOS PEAD event (2025-present), compute:
    - novelty_score: fraction of topics novel or discontinued vs prior 2 quarters
    - emphasis_shift: cosine distance from current to prior quarter topic vector
  Phase 3 — Test composite gate:
    Var A (standard gate unchanged): H174 baseline (score ≥ 0.18 AND surprise ≥ 0.02)
    Var B (novelty OR standard): (score ≥ 0.18 AND surprise ≥ 0.02) OR (score ≥ 0.15 AND novelty ≥ 0.3)
    Var C (novelty filter on H174): H174 gate + require novelty ≥ 0.2
Gate: OOS WR > 81.8% AND n ≥ 15 (H174 baseline).
IS: 2022-2024 (ontology build); OOS: 2025-present.
CAVEAT: H247 (FMP 403); use AlphaVantage fallback. H168 transcript coverage bias applies.
Script: backtesting/daily/run_h408_topic_ontology_pead.py (stub).
Cost: <$2/year API; medium engineering effort (ontology build is one-time).
```

---

## Connections and Cross-References

- [Event-Driven Strategies](event-driven.md) — H174 PEAD production context; H408 is a direct upgrade
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — FinBERT pipeline; transcript ingestion notes
- [Multi-Agent LLM Trading](multi-agent-llm-trading.md) — H274 multi-agent PEAD debate; H408 provides better input signal quality
- [Free Data Sources](../data-sources/free-data.md) — AlphaVantage transcript API (25 req/day)
- [Earnings Calendar & Events](../data-sources/earnings-events.md) — event trigger pipeline for PEAD scanner
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H408 stub; also related H378 (EarningsInOne fast/slow signal)
- [PEAD-NLP Alpaca Deployment](../paper-trading/pead-nlp-alpaca.md) — live pipeline that H408 would upgrade
