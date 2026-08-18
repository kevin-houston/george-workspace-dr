---
created: 2026-08-18
updated: 2026-08-18
type: source_summary
authors: Alireza Kargarzadeh, Nariman Khaledian, Navid Parvini, Arman Khaledian
published: 12 August 2026 (arXiv)
source: arXiv:2608.12283
url: https://arxiv.org/abs/2608.12283
affiliation: Tailstate Intelligence Ltd. / Zanista AI Ltd. / independent
---

# Large Language Model-Driven Small-Capitalization Trading — Kargarzadeh, Khaledian, Parvini & Khaledian (2026)

**Authors:** Alireza Kargarzadeh (Tailstate Intelligence), Nariman Khaledian (independent), Navid Parvini (Zanista AI), Arman Khaledian (Tailstate Intelligence / Zanista AI)
**Venue:** arXiv:2608.12283, submitted 12 August 2026

## What This Paper Is

A Russell 2000 (small-cap) trading pipeline combining LLM news sentiment, a macro-indicator panel, and technical signals — most relevant not for its headline Sharpe but for two mechanisms genuinely new to this wiki: (1) a **pure-alpha / pure-beta / intersection** stock-selection regime split, and (2) feeding **aleatoric + epistemic risk decomposition directly into the portfolio covariance matrix** rather than treating risk as purely historical/backward-looking. Neither idea exists anywhere in our current [Alpha Illusion checklist](../algorithms/llm-alpha-validation.md), [Behavioral Finance Signals](../algorithms/behavioral-finance-signals.md), or [Position Sizing](../algorithms/position-sizing.md) pages.

## Method

**Sentiment scoring**: GPT-4o mini returns a calibrated probability distribution (negative/neutral/positive) per headline; directional score = P(positive) − P(negative). Near-duplicate/syndicated articles are de-duped via single-linkage agglomerative clustering (cosine distance, 0.90 threshold, 30-day trailing window) — only the article nearest each cluster centroid counts, preventing wire-service repeats from inflating signal weight. Score then goes through entity-prior correction, trailing winsorized-median demeaning, and cross-sectional z-scoring (all point-in-time safe by construction). Alternative scorers tested: FinBERT, Mistral 7B Instruct, Llama 2 13B Chat.

**Three regime triggers** (against a 58-indicator macro panel — sector ETFs, indices, VIX, commodities, rates, FRED releases):
- **Pure Alpha**: stock return z-score |Z_i| ≥ 2 over a 120-day lookback, WITHOUT a corresponding macro-indicator trigger
- **Pure Beta**: an indicator's z-score fires (|Z_ind| ≥ 2) AND the stock's rolling beta to it exceeds 1 in both unconditional and tail-conditional terms, but the stock hasn't moved yet
- **Beta (intersection)**: both fire together

**Risk decomposition**: a dropout-based (rate 0.2, 50 stochastic passes) multimodal network produces per-asset representations; aleatoric covariance is a rank-2-plus-diagonal head averaged across passes, epistemic covariance is the cross-pass variance of the mean prediction. Combined Σ̂ = Σ̂^Aleatoric + Σ̂^Epistemic feeds standard allocators (MVO, Black-Litterman, HRP, risk parity) directly — so allocation is penalized more when the *model* is uncertain, not just when the asset has been historically volatile.

## Result

Universe: Russell 2000. IS train Oct 2023–Dec 2024 (80/20 split), **OOS is a single calendar year, 2025** — a real limitation, noted below. Costs tested at {0,1,2,5,10,20,50,100}bp + 5bp slippage.

Best conservative-cost configuration (100bp): **pure-beta trigger, GPT-4o mini sentiment, Student-t target distribution, 40-day holding, risk-parity allocator → OOS Sharpe 2.33, MaxDD -18.3%, annualized return 95.9%.** At lower/more realistic cost assumptions (20bp) the same configuration reaches Sharpe 2.51. A second strong cell: pure-alpha + Mistral-7B + 60-day + HRP → Sharpe 1.96-2.05 across cost levels.

Key structural finding, stated directly by the authors: **separating pure-alpha and pure-beta consistently beats requiring both to fire together** (the intersection regime "consistently underperforms") — and **regime selection and allocator choice matter at least as much as which sentiment model is used.** FinBERT shows the widest score dispersion of the four backends tested but only modest performance differences once aggregated across regime/allocator combinations — a similar "architecture/pipeline choices matter more than base model" finding to what H320's LightGBM-crash-filter and H517's OPT-vs-FinBERT work have already surfaced independently.

## Relevance to George's stack

1. **Single-year OOS is a hard limitation, not a footnote.** 2025-only OOS on a Russell 2000 universe cannot distinguish genuine alpha from a lucky small-cap regime — this wiki's standard is multi-year OOS with regime coverage (see [Design Principles](../backtesting/design-principles.md)); the reported Sharpe 2.33 should be treated the way this wiki treats any single-fold claim, i.e. as a hypothesis to test on our own IS/OOS split, not an established number.
2. **Pure-alpha/pure-beta separation is a directly reusable idea for H174/PEAD.** Our current H163/H174 pipeline treats every 8-K/earnings event identically regardless of whether the surprise coincides with a broad macro move. This paper's finding — that separating "stock moved for its own reasons" from "stock is exposed to a macro factor that just moved" produces a cleaner signal than requiring both — maps onto a concrete PEAD refinement: split H174-qualifying events into "pure-alpha" (earnings surprise with no same-day sector/macro co-mover) vs. "pure-beta" (earnings surprise riding a broader move) and check whether one subgroup has a materially different win rate, rather than pooling all 22 confirmed H174 events together.
3. **Aleatoric/epistemic covariance feed is a genuinely new position-sizing mechanism** — distinct from our existing SALVOC/Kelly-VIX/SJM-factor sizing approaches in [Position Sizing](../algorithms/position-sizing.md), all of which size off realized/historical vol. A model-uncertainty-aware covariance term would be a non-trivial build (requires training a dropout-based multimodal net) — flagged as a scoping candidate, not a same-night backtest.
4. **The de-duplication clustering step (single-linkage, 0.90 cosine threshold) is a small, immediately portable fix** for our existing NLP pipeline — H163/H174/H517 currently score each 8-K/news item independently with no check for syndicated/duplicate coverage inflating apparent signal strength across multiple wire sources reporting the same event.

## Caveats

- OOS = 1 calendar year only (2025); no multi-regime validation.
- Russell 2000 small-cap universe — liquidity/borrow/slippage assumptions (100bp "conservative" cost) may not transfer to our current large-cap-leaning universes (H198, H411).
- Anonymous GitHub repo referenced in-paper but not independently verified here — do not treat as a ready-to-run reference implementation without checking it first.
- No named-lab affiliation (Tailstate Intelligence / Zanista AI are small/boutique shops, not university or major-fund research) — treat headline Sharpe with the same skepticism this wiki applies to AlphaZeroBeta (single-author HSE paper) pending independent replication.

## See Also

- [PEAD Comprehensive Reference](../algorithms/pead.md) — H163/H174 pipeline this paper's pure-alpha/pure-beta split could refine
- [Alpha Illusion — LLM Validation Checklist](../algorithms/llm-alpha-validation.md) — single-year-OOS and small-boutique-affiliation skepticism this paper should be run through before any hypothesis is staged
- [Position Sizing & Portfolio Construction](../algorithms/position-sizing.md) — existing vol-based sizing approaches (SALVOC, Kelly-VIX, SJM) this paper's aleatoric/epistemic covariance mechanism would sit alongside
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — sentiment-scoring pipeline family (FinBERT, LLM annotators) this paper's GPT-4o mini scorer extends
