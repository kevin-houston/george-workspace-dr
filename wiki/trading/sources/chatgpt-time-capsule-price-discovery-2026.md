---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Sebastian Lehner, Alejandro Lopez-Lira
published: 23 Apr 2026 (arXiv)
source: arXiv:2604.21433
url: https://arxiv.org/abs/2604.21433
---

# ChatGPT as a Time Capsule: The Limits of Price Discovery — Lehner & Lopez-Lira 2026

**Authors:** Sebastian Lehner, Alejandro Lopez-Lira
**Venue:** arXiv:2604.21433, submitted 23 Apr 2026

Lopez-Lira previously co-authored the influential 2023 paper "Can ChatGPT Forecast Stock Price Movements?" This is a methodological follow-up that addresses that line of work's biggest weakness: contamination from the model's training-cutoff knowledge of what actually happened next.

## Method: frozen snapshots as a historical text-information proxy

The paper's key design choice is using **frozen ChatGPT snapshots from 2021-2025** — each snapshot representing exactly the publicly available textual information the model had ingested up to that point — rather than a single current model asked to reason about the past. This sidesteps the look-ahead risk that plagues most LLM-finance backtests (see [Look-Ahead-Freedom as Temporal Non-Interference](../backtesting/lookahead-formal-verification.md) for the formal treatment of this failure class, and George's own H256 GEM incident where an unlagged signal inflated OOS Sharpe from 0.646 to 1.956).

From each snapshot, the authors construct an **LLM outlook score** for ~7,000 U.S. equities.

## Key findings

- The outlook score has statistically significant associations with analyst revisions, price-target adjustments, and **one-month cross-sectional returns** (t-statistic = 6.02).
- Predictive power holds **beyond standard contemporaneous valuation measures** — the score captures forward-looking fundamental information not yet reflected in prices.
- Predictability generally **strengthens over longer horizons**, with a non-monotonic pattern at intermediate horizons.
- Mechanism: the authors argue the market's constraint is not investor inattention (the standard PEAD explanation, per Ball & Brown 1968 as covered in [PEAD](../algorithms/pead.md)) but **the cost of aggregating dispersed qualitative information across many documents at once**.

## Relevance to George's PEAD pipeline

H163/H174 score a *single* document (the 8-K press release) with FinBERT at the moment of earnings release. This paper's aggregation-cost mechanism suggests a distinct, complementary signal: a **multi-document synthesis score** (recent news + analyst notes + prior filings, aggregated) that captures information the market hasn't yet had time/resources to piece together — conceptually adjacent to but distinct from H408's earnings-call topic-novelty design and H419's supply-chain-network PEAD extension.

Operationally, this is expensive: reproducing "frozen snapshot" behavior would require either (a) point-in-time restricted retrieval (only serve the LLM documents dated before the prediction date) or (b) accepting current-model contamination risk and controlling for it statistically. Given George's OneCLI-gated `$OPENAI_API_KEY` access, (a) is feasible without a frozen-snapshot API — implement as a strict `published_date <= signal_date` filter on the retrieval corpus.

**Not yet a numbered hypothesis** — filed as a design candidate. A concrete next step would be H4xx: "multi-document aggregation score, PIT-filtered retrieval, entry alongside H174's single-document score" — test whether the two scores are correlated or additive using George's existing PEAD event set.

## See Also

- [PEAD — Post-Earnings Announcement Drift](../algorithms/pead.md) — H174 confirmed single-document pipeline this paper's mechanism complements
- [PEAD LLM Architecture Comparison (2025)](pead-llm-architecture-comparison-2025.md) — adjacent FinNLP-2025 paper on encoder-decoder vs FinBERT for the same problem class
- [Look-Ahead-Freedom as Temporal Non-Interference](../backtesting/lookahead-formal-verification.md) — the exact bias class this paper's frozen-snapshot design is built to avoid
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — FinBERT/EDGAR tooling this would extend
