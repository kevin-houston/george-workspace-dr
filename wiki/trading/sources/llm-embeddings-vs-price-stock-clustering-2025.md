---
created: 2026-08-14
updated: 2026-08-14
type: source_summary
authors: Bingyang Wang, Grant Johnson, Maria Hybinette, Tucker Balch
published: September 2025 (arXiv), Georgia Tech / J.P. Morgan AI Research affiliation (Balch)
source: arXiv:2509.01590
url: https://arxiv.org/abs/2509.01590
license: CC BY 4.0
---

# Is All the Information in the Price? LLM Embeddings versus the EMH in Stock Clustering (Wang, Johnson, Hybinette & Balch, 2025)

**Authors:** Bingyang Wang, Grant Johnson, Maria Hybinette, Tucker Balch
**Venue:** arXiv:2509.01590, September 2025

## The question

A direct empirical test of the semi-strong Efficient Market Hypothesis using a modern tool: if LLM embeddings of stock-related news headlines encode economically meaningful information, then clustering stocks by those embeddings should group similarly-behaving stocks together *at least as well* as clustering by raw historical price correlation. If EMH's semi-strong form holds — public information is already impounded in price — then price-based clustering should win, because news text carries no residual signal price hasn't already captured.

## Method

Three independent stock-grouping methods, held to the same downstream test:

1. **Price-based clustering** — K-means (MacQueen 1967) on historical return correlations.
2. **Human-defined clusters** — GICS industry/sector classification (2024 standard) as the "ground truth" baseline practitioners already use.
3. **LLM-embedding clusters** — embeddings of stock-related news headlines (embedding model cited: Mistral 7B family) fed through the same K-means clustering, so the *only* variable that changes is the information source (text vs. price), not the clustering algorithm.

Evaluation: each clustering is scored by how well it predicts out-of-sample return behavior (RMSE on held-out returns) — i.e., does knowing "which cluster a stock is in" reduce prediction error for that stock's future returns, and by how much depending on which clustering method defined the clusters. Data sourced from Compustat NA / WRDS.

## Result

**Price-based clustering wins decisively:**

| Comparison | RMSE reduction from price-based clustering |
|---|---|
| vs. GICS (human-defined sectors) | −15.9% |
| vs. LLM-embedding clusters (news headlines) | −14.7% |

Both alternative methods were beaten by simple historical-return K-means by a comparable margin (~15%). The authors' interpretation is stated directly: "short-horizon return information is largely contained in prices" — a clean empirical point *for* semi-strong EMH, and against the assumption (implicit in several of George's queued LLM-pairs-trading angles) that news-embedding similarity adds return-predictive information beyond what price co-movement already captures.

## Relevance to George's stack — a caution, not a green light

This is the most direct evidence yet reviewed against the "LLM semantic embeddings improve pair/cluster selection" thesis that motivates H316 (Moira, arXiv:2605.01954) and the already-noted Cross-Stock Predictability via LLM-Augmented Semantic Networks (arXiv:2604.19476, [Pairs Trading / Stat Arb](../algorithms/pairs-trading.md)). Two things reconcile this paper's negative result with those two positive ones, and both matter for scoping any future LLM-pairs hypothesis:

1. **Different embedding source.** This paper embeds *news headlines* (broad, low-signal-density text). arXiv:2604.19476 embeds **10-K filings** (dense, firm-specific, updated quarterly) and then uses an LLM as a *classifier/filter* on a price-correlation-derived candidate graph — not as the primary similarity signal. The winning design in 2604.19476 is "price co-movement finds candidates, LLM removes economically implausible edges" — which is actually *consistent* with this paper's finding that price carries most of the signal; the LLM's job there is pruning false positives, not discovering new pairs from text alone.
2. **Different task.** This paper measures unconditional return-prediction RMSE from *static* clustering. 2604.19476 measures long-short Sharpe from mean-reversion trading on *pairs*, a much narrower and more path-dependent target where a filter that removes ~20% of spurious candidate pairs can move Sharpe from 0.742→0.820 even while adding no standalone predictive power.

**Practical takeaway for any future LLM-pairs-trading hypothesis on George's universe:** do not treat LLM text embeddings as a standalone stock-similarity signal (this paper says that loses to price by ~15% RMSE) — treat them strictly as a *filter on top of* a price/cointegration-derived candidate list, matching the architecture that already worked in 2604.19476 rather than a from-scratch text-clustering approach. This closes off one naive implementation path before it gets proposed as a hypothesis.

## See Also

- [Pairs Trading / Stat Arb](../algorithms/pairs-trading.md) — H316 Moira design note and the LLM-semantic-networks reference this paper directly qualifies
- [Alpha Illusion — LLM Validation Checklist](../algorithms/llm-alpha-validation.md) — general skepticism-toward-LLM-alpha-claims framework this paper's result fits into
- [Factor Models & Cross-Sectional Alpha](../algorithms/factor-models.md) — price-based clustering is a cross-sectional grouping method in the same family as sector-neutral factor construction
