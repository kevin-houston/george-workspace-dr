---
title: QuantMind — LLM Knowledge Extraction for Quant Finance
added: 2026-06-10
updated: 2026-07-26
category: tools
url: https://github.com/LLMQuant/quant-mind
stars: 1.7k
license: MIT
---

# QuantMind — Intelligent Knowledge Extraction for Quant Finance

**Repo:** github.com/LLMQuant/quant-mind  
**Org:** LLMQuant  
**Stars:** 1.7k | **Forks:** 271 | **License:** MIT | **Language:** Python 98.5%

Accepted at the **NeurIPS 2025 Workshop on Generative AI in Finance**.

---

## Two-Stage Pipeline

**Stage 1 — Knowledge Extraction:**
```
Source APIs (arXiv, news, blogs, SEC) → Intelligent Parser → Agent → Structured Knowledge Base
```
- Connects to arXiv, news feeds, financial blogs, Perplexity search
- Parses PDFs, HTML, tables
- Auto-tags content into research categories; deduplicates via agent orchestration

**Stage 2 — Intelligent Retrieval:**
```
Knowledge Base → Embeddings → DeepResearch / RAG / Data MCP
```
- Semantic search via embeddings
- RAG for natural-language Q&A against accumulated knowledge
- "Data MCP" for structured access (planned)
- "DeepResearch" for multi-hop reasoning (partially planned)

---

## Installation

```bash
git clone https://github.com/LLMQuant/quant-mind.git
cd quant-mind
uv venv && source .venv/bin/activate
uv pip install -e .
```

Requires: Python 3.8+, OpenAI API key (GPT-4o-mini).

---

## Core API

**Process a single arXiv paper:**
```python
import asyncio
from quantmind.configs import PaperFlowCfg
from quantmind.configs.paper import ArxivIdentifier
from quantmind.flows import paper_flow

async def main():
    paper = await paper_flow(
        ArxivIdentifier(id="2602.23330"),
        cfg=PaperFlowCfg(model="gpt-4o-mini"),
    )
    print(paper.model_dump_json(indent=2))

asyncio.run(main())
```

**Batch processing:**
```python
inputs = [ArxivIdentifier(id=aid) for aid in ("2412.20138", "2502.13165", "2603.27539")]
result = await batch_run(
    paper_flow, inputs,
    cfg=PaperFlowCfg(model="gpt-4o-mini"),
    concurrency=3, on_error="skip",
)
```

**Free-form intent resolution:**
```python
inp, cfg = await resolve_magic_input(
    "Pull arXiv 2402.18485 about LLM trading agents; use gpt-4o-mini.",
    target_flow=paper_flow,
)
paper = await paper_flow(inp, cfg=cfg)
```

---

## Development Status

| Feature | Status |
|---------|--------|
| `paper_flow` (single paper) | ✅ Stable |
| `batch_run` (concurrent) | ✅ Stable |
| `resolve_magic_input` | ✅ Stable |
| OpenAI Agents SDK migration | 🔄 In progress |
| `FilesystemMemory` (persistent) | ⏳ Planned |
| Semantic knowledge graph | ⏳ Aspirational |
| Cross-document DeepResearch | ⏳ Aspirational |

**Caution**: Memory/embedding layer not yet available — semantic search is aspirational. Current value is in structured paper ingestion and batch processing.

---

## Relevance to George's Pipeline

| Use case | Fit |
|----------|-----|
| Dream cycle arXiv scans | High — automates paper-to-knowledge extraction |
| Wiki ingestion of new papers | High — replaces manual read+summarize for high-volume ingestion |
| SEC 8-K ingestion for PEAD | Medium — EDGAR pipeline exists; QuantMind adds structured facts layer |
| Factor discovery (H288/H349/H352) | High — queries across accumulated quant literature |
| Hypothesis ideation | High — "what momentum anomalies exist in bond ETFs?" |

**Dream cycle integration path:** `paper_flow` would replace the manual `curl` + LLM-read + extraction steps with a structured Pydantic output, feeding directly into wiki page writing. `batch_run` on 20–30 nightly candidates → faster relevance scoring.

---

## Cost Estimate

- `paper_flow` uses GPT-4o-mini
- ~2,000–5,000 tokens per paper
- At $0.15/1M input + $0.60/1M output: ~$0.003 per paper
- 30 papers/night: ~$0.09/night → ~$33/year

---

## Comparison to Hyper-Extract

Both extract knowledge from unstructured text. Key differences:
- **QuantMind**: finance-domain-specific, arXiv+SEC native, retrieval-first
- **Hyper-Extract**: domain-agnostic, 8 structural output formats (KG, hypergraph, temporal graph, Pydantic), better for entity extraction

Complementary: QuantMind for research queries against a corpus; Hyper-Extract for structured entity and graph output.

---

## Cross-references

- [Multi-Agent LLM Trading Systems](../trading/algorithms/multi-agent-llm-trading.md)
- [Machine Learning for Trading](../trading/tools/ml-for-trading.md)
- [NLP & Alternative Data](../trading/tools/nlp-alternative-data.md)
- [Hyper-Extract](hyper-extract-notes.md)
