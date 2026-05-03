# Knowledge Base Schema
**Owner:** Kevin Claw (kevinclaw26@gmail.com)
**Maintained by:** Andy (AI assistant)
**Last compiled:** (updated by AI on each wiki build)

---

## What This Is

A personal knowledge base covering Kevin's primary domains of interest: systematic trading research, quantitative finance, AI/ML developments, and agentic engineering. Raw materials flow in from the dream cycle nightly research, daily AI podcast sourcing, and anything Kevin explicitly adds. The AI organizes it into a structured wiki.

## Folder Structure

- `raw/` — Unprocessed source material. Articles, paper summaries, notes, clippings. **Never modify these files manually** — drop things in and let the AI process them.
- `wiki/` — The organized wiki. AI maintains this entirely. One `.md` file per topic. Do not edit by hand.
- `outputs/` — Generated answers, research reports, briefings produced in response to questions.

## Wiki Rules

- Every topic gets its own `.md` file in `wiki/`
- Every wiki file starts with a one-paragraph summary
- Link related topics using `[[topic-name]]` format
- Maintain an `INDEX.md` in `wiki/` that lists every topic with a one-line description
- When new raw sources are added, update relevant wiki articles
- Mark sources at the bottom of each wiki file under `## Sources`
- Date-stamp all significant updates

## Kevin's Core Interests (priority order)

1. **Systematic trading strategies** — backtesting, quantitative signals, options, PEAD, pairs trading, dividend strategies
2. **AI/ML for finance** — LLM signal filtering, foundation models (TimesFM), deep learning for price prediction
3. **Agentic AI engineering** — Claude Code, multi-agent systems, MCP, tool use, autonomous agents
4. **Generative AI developments** — model releases, benchmarks, company moves (OpenAI/Anthropic/Google)
5. **AI regulation & policy** — state laws, federal preemption, military AI debates
6. **Portfolio management** — Robinhood portfolio, rebalancing, real-money allocation

## How to Add Raw Material

**Manually:** Drop any `.md`, `.txt`, or `.pdf` file into `raw/` and tell Andy "update the knowledge base."

**Via agent-browser (automated scraping):**
```
agent-browser open <url>
agent-browser get text "article"
# Save output to raw/YYYY-MM-DD_title.md
```

**Via dream cycle (automatic):** The nightly dream cycle research phase automatically saves research summaries to `raw/` as part of its scan-reflect-stage pipeline.

## Compilation Command

Tell Andy:
> "Read everything new in knowledge-base/raw/ since the last compile. Update the wiki in knowledge-base/wiki/ following the SCHEMA.md rules. Update INDEX.md. Flag any contradictions or gaps."

## Health Check Command (Monthly)

Tell Andy:
> "Run a knowledge base health check: review wiki/, flag contradictions between articles, find topics mentioned but never explained, list unsourced claims, suggest 3 new articles to fill gaps."

---

## Current Wiki Topics (maintained by AI)

*(Updated automatically on each compile — see wiki/INDEX.md for the live list)*
