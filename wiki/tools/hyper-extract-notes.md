---
title: Hyper-Extract
url: https://github.com/yifanfeng97/Hyper-Extract
added: 2026-06-26
category: tools/knowledge-extraction
stars: ~2500
license: Apache-2.0
---

# Hyper-Extract

LLM-powered knowledge extraction framework that transforms unstructured text into structured, queryable knowledge formats.

## What it does

Takes raw documents (papers, filings, transcripts) and extracts them into one of 8 structured formats using LLMs. The extracted structures are queryable and can be exported to Obsidian or used via MCP.

## Knowledge structure types

| Format | Use case |
|--------|----------|
| Collection | Simple list extraction |
| Pydantic Model | Typed structured fields |
| Knowledge Graph | Entity-relation triples |
| Hypergraph | Multi-way relationships (beyond binary) |
| Temporal Graph | Events with time ordering |
| Spatial Graph | Location-aware entities |
| Spatio-Temporal Graph | Combined space + time |

## Extraction engines (10+)

GraphRAG, LightRAG, Hyper-RAG, KG-Gen, and others.

## Templates

80+ prebuilt YAML extraction templates across domains:
- **Finance**: earnings entities, market events, risk factors
- **Legal**: contract clauses, obligations
- **Medical / TCM**: clinical entities
- **General**: default patterns

## Integration

- **MCP server**: Claude Desktop and IDE agent integration
- **CLI**: `hyper-extract parse`, `hyper-extract query`, `hyper-extract viz`
- **Obsidian export**: generates `[[wikilinks]]` Markdown vaults
- **Incremental learning**: add docs to existing knowledge bases

## Model support

- OpenAI: GPT-4o, GPT-4o-mini
- Anthropic: claude-opus-4-8, claude-sonnet-4-6, claude-haiku-4-5
- Alibaba: Qwen series
- Local: vLLM (Qwen3.5-9B tested)

## Installation

```bash
pip install hyper-extract
```

## Relevance to George's workflow

1. **Dream cycle / arXiv ingestion**: extract hypothesis entities, method graphs, and result tables from papers automatically → feed into wiki pages
2. **PEAD / 8-K parsing**: Finance templates could extract earnings entities (EPS, revenue, guidance) into Pydantic models, supplementing FinBERT sentiment
3. **Wiki ingestion skill**: replace manual summarization with structured KG extraction for complex multi-entity sources
4. **Hypergraph mode**: useful for multi-variable macro research (e.g., CPI → FOMC → Kalshi market chains for H334)

## Status

Noted only. Not yet installed. Would need OpenAI API key or local vLLM for extraction (Anthropic Claude supported directly via env var).
