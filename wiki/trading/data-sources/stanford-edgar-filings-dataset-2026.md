---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Nick Bettencourt, Xiaowei Ding, Kay Giesecke
published: 16 Jun 2026 (arXiv, v2 17 Jun 2026)
source: arXiv:2606.18192
url: https://arxiv.org/abs/2606.18192
category: data-sources
---

# The Stanford EDGAR Filings Dataset — Bettencourt, Ding & Giesecke 2026

**Authors:** Nick Bettencourt, Xiaowei Ding, Kay Giesecke (Stanford)
**Venue:** arXiv:2606.18192, submitted 16 Jun 2026, revised 17 Jun 2026

## What this is

A pure data-source / infrastructure paper: an open-source reconstruction of the full
SEC EDGAR corpus into **layout-faithful, token-efficient MultiMarkdown**, designed for
financial language modeling and evaluation. The initial public release (SEFD-v1)
contains **152 billion tokens**, with an estimated **550 billion tokens** available
across the full archive spanning **18.5 million filings**. Less than 0.1% overlap with
Common Crawl-derived pretraining corpora — i.e., this is genuinely new text most
foundation models have not already seen, not a re-packaging of data already baked into
model weights. The authors also release two benchmarks: **EDGAR-Forecast** (numerical
prediction from filing text) and **EDGAR-OCR** (financial table transcription).

## Why this matters for George's data-sources page

George's existing EDGAR tooling ([SEC EDGAR XBRL Fundamentals](edgar-fundamentals.md))
covers **structured** data — XBRL-tagged numeric facts via the `data.sec.gov` API,
company-by-company, rate-limited to 10 req/s. This paper is the complementary
**unstructured text** layer: full filing bodies (10-K risk factors, MD&A, 8-K
narrative text) already parsed, cleaned, and reformatted at bulk scale, which is
exactly the raw material H163/H174's FinBERT scoring currently downloads and cleans
itself, filing-by-filing, at ingestion time.

Two concrete uses:

1. **Backfill / historical breadth**: George's H163/H174 pipeline scores 8-Ks as they
   arrive via `pead_overnight.py`. This dataset (spanning the full EDGAR archive, not
   just recent filings) would let a historical backtest re-score *every* 8-K back to
   whenever the dataset's coverage begins, without re-implementing EDGAR text cleaning
   and rate-limit handling from scratch — directly useful for widening H163/H174's
   OOS sample beyond the current n=22 events (H174's current sample size is a
   recurring caveat across PEAD hypothesis entries).
2. **EDGAR-Forecast benchmark as a sanity check**: before trusting a new LLM-based
   filing-text signal (e.g., the taxonomy tagger in
   [Grounded Event Extraction from SEC 8-K Filings](sec-8k-event-taxonomy-2026.md), or
   the moving-target signal in
   [From Text to Alpha](from-text-to-alpha-disclosure-tracking-2026.md)), EDGAR-Forecast
   gives an independent, standardized numerical-prediction benchmark to validate the
   underlying LLM extraction quality against, separate from George's own live PEAD
   backtest results.

Access/cost note: dataset hosting/download mechanics (HuggingFace vs. direct download,
size in GB for the initial 152B-token release) were not confirmed in this pass — flag
for follow-up before committing engineering time.

**Not yet a numbered hypothesis** — filed as an infrastructure/data-source candidate
supporting future PEAD sample-size expansion work.

## See Also

- [SEC EDGAR XBRL Fundamentals](edgar-fundamentals.md) — the structured-data companion to this unstructured-text corpus
- [Grounded Event Extraction from SEC 8-K Filings (2026)](sec-8k-event-taxonomy-2026.md) — a concrete downstream use case (bulk taxonomy tagging beyond 2022-2026)
- [From Text to Alpha (2026)](from-text-to-alpha-disclosure-tracking-2026.md) — another LLM-on-filings signal this corpus could backfill/validate
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — FinBERT/EDGAR tooling this bulk corpus would feed
- [Point-in-Time Constituent & Vintage Data Sources](point-in-time-constituents.md) — companion PIT-data-quality framing for any historical backfill built on this corpus
