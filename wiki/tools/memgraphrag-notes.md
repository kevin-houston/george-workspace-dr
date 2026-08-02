---
title: MemGraphRAG — Memory-Based Multi-Agent Graph RAG
added: 2026-08-02
category: tools
url: https://github.com/XMUDeepLIT/MemGraphRAG
---

# MemGraphRAG

Research prototype from Xiamen University's DeepLIT lab implementing a
memory-based multi-agent system for Graph Retrieval-Augmented Generation.
Backed by a paper accepted at KDD 2026 (arXiv:2606.00610, Wu/Xiang/Tang/Chen/
Zhang/Su). Surfaced via a tweet from Tom Dörr (@tom_doerr), 2026-08-02.

**Stars:** 129 | **Forks:** 27 | **License:** MIT | **Language:** Python
**Created:** 2026-02-02 | **Last push:** 2026-06-20 (~6 weeks stale — single
burst of commits then silent; no CI, no PyPI package, 3 open issues)

## What it does

Builds a knowledge store with three linked layers instead of a flat graph
(extends HippoRAG):

- **Passage layer** — raw text chunks from the source corpus.
- **Fact layer** — concrete `(subject, relation, object)` triples extracted
  via OpenIE from those passages, each linked back to its source chunk.
- **Schema layer** — abstract ontology triples (e.g. `(PersonType, relation,
  OrgType)`) induced by generalizing over facts; low-frequency/noisy patterns
  are filtered out.

**Conflict-aware construction**: after extraction, facts are checked against
each other and against passage evidence for contradictions; connected
conflicts are grouped and resolved before the graph is finalized — aimed at
reducing hallucinated/contradictory triples that plague naive GraphRAG
pipelines.

**Memory-derived graph**: post-resolution, type/entity/passage nodes are
materialized into a queryable graph (igraph, `.graphml`/JSON) rather than
building the graph directly from raw extraction output.

**Retrieval**: hybrid embedding similarity + Personalized PageRank over the
three-layer graph, plus a fact-reranking/filtering step, feeding a batch QA
pipeline that logs answers, retrieved docs, scores, latency, and token usage.

## Tech Stack

- Python 3.10+
- OpenAI-compatible LLM API (default `gpt-4o-mini`, configurable base URL)
- Local HuggingFace embedding models (e.g. `bge-large-en-v1.5`), optional
  `gritlm` backend
- igraph for graph storage (file-based `.graphml`/JSON — no Neo4j or other
  graph DB dependency)
- Optional vLLM/llama-factory for offline OpenIE
- `pip install -r requirements.txt`; CLI entry points `code/index.py` and
  `code/retrieval_dataset_test.py`, shell templates provided

## Relevance to George's Stack

Moderate, speculative. The three-layer schema/fact/passage architecture with
explicit conflict-aware resolution is a genuinely different pattern than
QuantMind (retrieval-first) and Hyper-Extract (structure-first), both already
logged in the wiki — MemGraphRAG is the only one of the three with explicit
cross-document contradiction detection, which could matter for reconciling
conflicting analyst statements or contradictory 8-K/earnings-call claims
across time (relevant to the H163/H174/H317 PEAD line of work).

Caveats: unmaintained (6+ weeks since last commit, no released package),
GPU/local-embedding-heavy, and adds real infra weight (igraph, offline OpenIE,
optional vLLM) for a benefit that's speculative until cross-document conflict
resolution is actually a bottleneck. Logging as a reference only — no action
recommended now.

# Citations

- Tweet: https://x.com/tom_doerr/status/2083804327433351580
- Paper: https://arxiv.org/abs/2606.00610 (KDD 2026)
- Repo: https://github.com/XMUDeepLIT/MemGraphRAG
