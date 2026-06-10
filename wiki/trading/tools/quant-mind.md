---
added: 2026-06-10
category: tools/research-infrastructure
url: https://github.com/LLMQuant/quant-mind
stars: ~500 (early — NeurIPS 2025 Workshop paper)
license: MIT
status: active development (mid-migration to OpenAI Agents SDK)
---

# QuantMind — Intelligent Knowledge Extraction for Quant Finance

**QuantMind** is an AI-powered knowledge extraction and retrieval framework from LLMQuant. It ingests unstructured financial content (arXiv papers, news, blogs, SEC filings) and transforms it into a queryable semantic knowledge base.

Accepted at the **NeurIPS 2025 GenAI in Finance Workshop**.

---

## What it does (current capabilities)

Two-stage architecture:

**Stage 1 — Knowledge Extraction:**
```
Source APIs (arXiv, news, blogs) → Intelligent Parser → Workflow/Agent → Structured Knowledge Base
```
- Connects to arXiv, news feeds, financial blogs, Perplexity search
- Parses PDFs, HTML, tables, figures
- Auto-tags content into research categories
- Deduplicates via agent orchestration

**Stage 2 — Intelligent Retrieval:**
```
Knowledge Base → Embeddings → DeepResearch / RAG / Data MCP
```
- Embedding generation for semantic search
- RAG for natural-language Q&A against the knowledge base
- "Data MCP" for structured access (planned)
- "DeepResearch" for multi-hop reasoning across documents (partially planned)

---

## Installation & Quick Start

```bash
git clone https://github.com/LLMQuant/quant-mind.git
cd quant-mind
uv venv && source .venv/bin/activate
uv pip install -e .
```

Requires: Python 3.8+, OpenAI API key (uses GPT-4o-mini).

## Core API

**Process a single arXiv paper:**
```python
import asyncio
from quantmind.configs import PaperFlowCfg
from quantmind.configs.paper import ArxivIdentifier
from quantmind.flows import paper_flow

async def main():
    paper = await paper_flow(
        ArxivIdentifier(id="2602.23330"),  # Expert Investment Teams
        cfg=PaperFlowCfg(model="gpt-4o-mini"),
    )
    print(paper.model_dump_json(indent=2))

asyncio.run(main())
```

**Batch process multiple papers:**
```python
inputs = [ArxivIdentifier(id=aid) for aid in ("2412.20138", "2502.13165", "2603.27539")]
result = await batch_run(
    paper_flow, inputs,
    cfg=PaperFlowCfg(model="gpt-4o-mini"),
    concurrency=3,
    on_error="skip",
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

## Development status (as of 2026-06-10)

| Feature | Status |
|---------|--------|
| `paper_flow` (single paper) | ✅ Stable |
| `batch_run` (concurrent) | ✅ Stable |
| `resolve_magic_input` | ✅ Stable |
| OpenAI Agents SDK migration | 🔄 In progress (PR5 lands `flows/`+`magic.py`) |
| `FilesystemMemory` (persistent) | ⏳ Planned (PR6) |
| Semantic knowledge graph | ⏳ Aspirational (not yet built) |
| Cross-document DeepResearch | ⏳ Aspirational |

---

## Relevance to George's dream cycle

The dream cycle already does a manual version of what QuantMind automates:
1. Search arXiv for relevant papers
2. Fetch + read full content
3. Extract key findings
4. Write wiki pages with structured knowledge

QuantMind's `paper_flow` would replace steps 1–3 with structured JSON output, and could feed directly into step 4 (wiki writing). The output is a Pydantic model with parsed metadata, key findings, and category tags — much cleaner than raw HTML scraping.

**Practical integration points:**
- **Dream cycle Phase 2**: instead of manual `curl` + LLM-read + manual extraction, call `paper_flow` on each arXiv candidate → get structured paper object → write wiki page from it
- **Batch hypothesis discovery**: run `batch_run` on 20-30 recent quant papers per night → LLM-summarized and tagged output → faster relevance scoring
- **Search interface**: build a semantic index over our accumulated arXiv papers for "find all papers about PEAD" style queries (once the memory/embedding layer is stable)

**Caution**: Memory/embedding layer (FilesystemMemory) is not yet available — semantic search is aspirational. Current value is in structured paper ingestion and batch processing, not as a queryable knowledge graph.

---

## Cost estimate

- `paper_flow` uses GPT-4o-mini
- ~2,000–5,000 tokens per paper
- At $0.15/1M input + $0.60/1M output: ~$0.003 per paper
- Processing 30 papers/night: ~$0.09/night
- Annual cost for nightly batch: ~$33/year

---

## Cross-references

- [Multi-Agent LLM Trading Systems](multi-agent-llm-trading.md) — TradingAgents, HedgeAgents, Expert Investment Teams (papers QuantMind can process)
- [Machine Learning for Trading](ml-for-trading.md) — Alpha-GPT, FinAgent (similar LLM-in-the-loop approaches)
- [NLP & Alternative Data](nlp-alternative-data.md) — FinBERT, LLM annotators, domain gap findings
