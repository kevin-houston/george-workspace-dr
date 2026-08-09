---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Chanyeol Choi, Yoon Kim, Yu Yu, Young Cha, V. Zach Golkhou, Igor Halperin, Georgios Papaioannou, Minkyu Kim, Zhangyang Wang, Jihoon Kwon, Minjae Kim, Alejandro Lopez-Lira, Yongjae Lee
published: 3 Oct 2025 (arXiv v1); revised 15 Mar 2026 (v5)
source: arXiv:2510.03195
url: https://arxiv.org/abs/2510.03195
category: data-sources
---

# From Text to Alpha: Can LLMs Track Evolving Signals in Corporate Disclosures? — Choi et al. 2026

**Authors:** Chanyeol Choi, Yoon Kim, Yu Yu, Young Cha, V. Zach Golkhou, Igor Halperin,
Georgios Papaioannou, Minkyu Kim, Zhangyang Wang, Jihoon Kwon, Minjae Kim,
Alejandro Lopez-Lira, Yongjae Lee
**Venue:** arXiv:2510.03195, submitted 3 Oct 2025, revised through v5 (15 Mar 2026)

Two co-authors are already cross-referenced elsewhere in this wiki: **Igor Halperin**
(see [people page](../../people/igor-halperin.md), SciPhyRL) and **Alejandro Lopez-Lira**
(co-author of [ChatGPT as a Time Capsule](../sources/chatgpt-time-capsule-price-discovery-2026.md),
ingested 2026-08-08, and the original "Can ChatGPT Forecast Stock Price Movements?" 2023
paper).

## Method: "LLM as extractor, embedding as ruler"

The paper's core idea is tracking how a company's own emphasis **shifts between
consecutive disclosure periods** — what the authors call "moving targets." Rather than
scoring a single filing's sentiment in isolation (the H163/H174 approach), the method:

1. Uses an LLM to **extract** metrics/claims/emphasis points from each disclosure.
2. Uses **embedding distance** as the "ruler" to measure how much a given metric's
   framing, context, or prominence has shifted from the prior period's disclosure.

Benchmarked against a named-entity-recognition (NER) baseline, this approach achieves
**more than twice the risk-adjusted alpha**, with the gain attributed specifically to
**preserving contextual qualifiers and filtering out non-metric terms** — i.e., the NER
baseline treats "revenue" the same whether it's framed as "revenue grew despite
headwinds" or "revenue growth decelerated materially," while the embedding-based
approach captures that qualitative shift in framing.

## Why this is distinct from what's already indexed

This wiki already has three adjacent LLM-on-disclosures papers:
[PEAD LLM Architecture Comparison](pead-llm-architecture-comparison-2025.md) (FinBERT vs
BART vs LLaMA on static 10-Q MD&A classification), [ChatGPT as a Time Capsule](../sources/chatgpt-time-capsule-price-discovery-2026.md)
(frozen-snapshot multi-document aggregation score), and H163/H174 (single-filing FinBERT
sentiment score). This paper's mechanism is genuinely different from all three: it is
explicitly **inter-period** — the signal only exists by comparing filing *N* to filing
*N-1* for the same company, not by scoring any single document. That makes it a natural
complement to H163/H174 rather than a competitor: a "moving target" divergence score
computed period-over-period could be layered as a second gate alongside the existing
FinBERT ≥ 0.18 + EPS surprise ≥ 2% dual filter.

## Data-source implication

Operationally this requires each company's **prior-period disclosure** at scoring time,
which is a data-pipeline requirement, not just a modeling one — George's current 8-K
ingestion (`pead_overnight.py`) pulls the *current* filing only. Implementing this would
mean caching the last N filings per ticker (10-K/10-Q/8-K history), which the
[Stanford EDGAR Filings Dataset](stanford-edgar-filings-dataset-2026.md)'s bulk corpus
could backfill cheaply, avoiding a cold-start problem of re-downloading years of prior
filings per ticker via the rate-limited `data.sec.gov` API.

**Not yet a numbered hypothesis** — filed as a design candidate: "period-over-period
disclosure embedding-shift score as a secondary gate alongside H174's single-document
FinBERT score."

## See Also

- [PEAD — Post-Earnings Announcement Drift](../algorithms/pead.md) — H174 single-document pipeline this inter-period signal complements
- [ChatGPT as a Time Capsule (2026)](../sources/chatgpt-time-capsule-price-discovery-2026.md) — another Lopez-Lira paper on LLM-derived disclosure signals, multi-document aggregation angle
- [The Stanford EDGAR Filings Dataset (2026)](stanford-edgar-filings-dataset-2026.md) — bulk corpus that would solve the prior-period-filing cold-start problem
- [Igor Halperin](../../people/igor-halperin.md) — co-author, existing wiki person page (SciPhyRL)
- [PEAD LLM Architecture Comparison (2025)](pead-llm-architecture-comparison-2025.md) — adjacent static-classification comparison (FinBERT/BART/LLaMA)
