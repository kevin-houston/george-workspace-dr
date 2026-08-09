---
added: 2026-06-10
category: tools/diagramming
url: https://github.com/yizhiyanhua-ai/fireworks-tech-graph
stars: ~100 (early — MIT, by Brad Zhang)
license: MIT
status: active
---

# fireworks-tech-graph — Claude Code Diagram Generation Skill

A Claude Code skill that generates polished SVG/PNG technical architecture diagrams from natural language descriptions. Install via `npx skills add yizhiyanhua-ai/fireworks-tech-graph`.

---

## What it does

Converts a plain-English description into a rendered diagram (SVG + 1920px PNG). You describe the architecture; the skill produces publication-ready output.

**8 visual styles:**
| Style | Use case |
|-------|----------|
| Flat Icon | Clean product/explainer diagrams |
| Dark Terminal | Dev/engineering internal docs |
| Blueprint | Technical spec, infrastructure |
| Notion Clean | Lightweight, minimal |
| Glassmorphism | Polished marketing/slides |
| Claude Official | Anthropic ecosystem diagrams |
| OpenAI Official | OpenAI ecosystem diagrams |
| Dark Luxury | High-contrast premium (AI-authored) |

**14 diagram types:** Architecture, Sequence, Flow, Data Flow, UML (Class, State Machine, ER), Use Case, Deployment, Network, Component, System Context, Process, Concept Map.

---

## AI/Agent domain built-ins

Pre-baked semantic vocabulary and named patterns specifically for LLM/agent architectures:

**Semantic shapes:**
- LLM = double-border rectangle
- Agent = hexagon
- Vector Store = ringed cylinder
- Tool = gear/cog

**Color-coded arrows:**
- Write → solid dark
- Read → dashed
- Async → dotted
- Feedback → curved

**Named flow templates:**
- RAG pipeline
- Agentic Search
- Mem0 memory architecture
- Multi-Agent orchestration
- Tool Call sequence

**40+ product icons**: OpenAI, Anthropic, LangChain, Pinecone, Weaviate, ChromaDB, Redis, Postgres, etc.

---

## Output

- SVG (scalable, embeddable in markdown/HTML)
- 1920px PNG via `cairosvg`, `rsvg-convert`, or `puppeteer` (first available)
- Files written to workspace; can be sent via `send_file`

---

## Relevance to George's work

Primarily a documentation and communication tool, not a trading signal:

1. **Wiki architecture diagrams** — visualize multi-agent PEAD (H274 3-agent debate flow), production portfolio structure (H041a/H026/H045/IBS blend), dream cycle pipeline
2. **EOD reports** — add architecture snapshots to HTML dashboard
3. **Presentation-ready diagrams** — for Kevin's strategy explainers or investor-facing materials
4. **Agent system design** — clarify NautilusTrader execution layer (H276), Kraken MCP integration topology

The AI/Agent domain patterns are directly applicable: can render the H274 multi-agent PEAD architecture, the dream cycle scan→stage→build pipeline, or the PEAD overnight→intraday→open→exit sequence.

---

## Cross-references

- [Multi-Agent LLM Trading Systems](../trading/tools/multi-agent-llm-trading.md) — H274 PEAD upgrade; diagram candidate
- [QuantMind](quant-mind-notes.md) — paper ingestion pipeline; diagram candidate
- [Mermaid Skill](mermaid-skill.md) — lighter-weight diagramming via Mermaid syntax (already in wiki)
