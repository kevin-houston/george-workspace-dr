---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Rian Dolphin, Joe Dursun, Jarrett Blankenship, Katie Adams, Quinton Pike
published: 9 Jul 2026 (arXiv)
source: arXiv:2607.08346
url: https://arxiv.org/abs/2607.08346
category: data-sources
---

# Grounded Event Extraction from SEC 8-K Filings with a Fine-Grained Taxonomy — Dolphin et al. 2026

**Authors:** Rian Dolphin, Joe Dursun, Jarrett Blankenship, Katie Adams, Quinton Pike
**Venue:** arXiv:2607.08346, submitted 9 Jul 2026

## What this is

A structured data-source paper, not a strategy paper: a two-stage LLM pipeline that
classifies SEC 8-K disclosures against a **119-event-type taxonomy** organized in three
tiers, and grounds every classification in the source text via fuzzy n-gram validation
plus a quality score. Applied to **292,984 filings from 2022-2026**, producing
**601,088 tagged events**. Validation shows precision rises from 12% to 96% as the
quality score increases, with unsupported ("hallucinated") tags falling to near zero at
high quality thresholds. An event study confirms the fine-grained taxonomy separates
economically distinct outcomes that the SEC's own coarse Item-number codes (Item 2.02,
Item 5.02, etc.) conflate together.

## Why this matters for George's pipeline

H163/H174 currently score the *entire* 8-K press release with FinBERT and gate on a
single sentiment/surprise threshold. This paper offers a complementary, structural
layer sitting *upstream* of that scoring step: instead of (or in addition to) a
continuous sentiment score, tag each 8-K with a specific, economically-grounded event
type from a 119-way taxonomy — e.g., distinguishing a "guidance raise" 8-K from a
"guidance affirm" 8-K from a "restructuring/impairment" 8-K, all of which currently fall
under the same coarse SEC Item code and get scored identically by FinBERT.

This is directly relevant to the earlier finding in
[H175 NOT CONFIRMED](../backtesting/hypothesis-log.md): Item 2.02 text alone was *less*
discriminative than the full 8-K document (38 events, WR=68.4% vs H163's 26 events,
WR=80.8%). The taxonomy in this paper is a plausible explanation for that result — Item
2.02 alone conflates multiple distinct event types (pure EPS beat vs. EPS beat +
guidance cut vs. EPS beat + restructuring announcement) that a fine-grained tagger would
separate. A George-side replication would build the tagger on already-downloaded 8-Ks
and use event-type as a categorical pre-filter or interaction term alongside the
existing FinBERT score ≥ 0.18 gate, rather than replacing it.

Practically: the taxonomy and grounding methodology (fuzzy n-gram source validation +
quality score threshold) are directly reusable — George already has EDGAR 8-K text
ingestion built for H163 (see [NLP & Alternative Data](../tools/nlp-alternative-data.md))
and `$OPENAI_API_KEY` access for the LLM extraction step. No new data source is
required, only a new processing stage on data already being pulled nightly by
`pead_overnight.py`.

**Not yet a numbered hypothesis** — filed as a design candidate for a future H-series
entry: "119-way 8-K event-type tag as a categorical filter/interaction alongside H174's
FinBERT + EPS-surprise gate."

## See Also

- [PEAD — Post-Earnings Announcement Drift](../algorithms/pead.md) — H174 pipeline this would extend
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — existing EDGAR 8-K ingestion/FinBERT tooling
- [SEC EDGAR XBRL Fundamentals](edgar-fundamentals.md) — companion EDGAR data-source page (structured financials, not filing text)
- [The Stanford EDGAR Filings Dataset (2026)](stanford-edgar-filings-dataset-2026.md) — bulk EDGAR text corpus that could seed a taxonomy-tagging backfill beyond the 2022-2026 window
- [Earnings Calendar & Corporate Events](earnings-events.md) — earnings/8-K timing data this event taxonomy would layer onto
