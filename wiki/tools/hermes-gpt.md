---
title: hermes-gpt
created: 2026-06-22
updated: 2026-06-22
category: tools
source: https://x.com/tonysimons_/status/2067773819322831061
github: https://github.com/asimons81/hermes-gpt
site: https://hermes-gpt.tonysimons.dev/
author: "@tonysimons_"
status: v0.1.0 — local-dev focused, intentionally conservative
---

# hermes-gpt

A standalone MCP sidecar that bridges ChatGPT (or any MCP-capable frontier model) to the Hermes Agent local tool system. Built by @tonysimons_ (published June 19, 2026).

## What It Solves

Frontier models are powerful reasoners but disconnected from your local environment. The standard workaround — pasting files, schemas, and context manually into the chat — burns Codex quota and resets each session. Hermes GPT eliminates that by giving ChatGPT a live MCP connection to the local operator stack.

**The Codex quota angle:** Because ChatGPT fetches exactly what it needs via MCP (rather than loading entire codebases into context), Codex usage limits are completely untouched. The claim is 80-90%+ token reduction on typical dev sessions.

## What Hermes Agent Is

Hermes Agent is @tonysimons_'s local agent stack — a system with its own memory store, skill library, and tool set. It is the "operator stack" that hermes-gpt exposes to frontier models. Think of it as a local equivalent to NanoClaw: persistent memory, learned skills, and execution tools.

hermes-gpt does **not** modify Hermes Agent's source code. It is a clean sidecar — the bridge, not a fork.

## Architecture

```
ChatGPT (or any MCP client)
        ↓  MCP protocol
hermes-gpt (local MCP server)
        ↓  internal API
Hermes Agent (local: memory, skills, files, tools)
```

## Capabilities by Default / Opt-In

**Default (read-only, safe):**
- Read local files
- Search files
- Search Hermes memory
- List and view Hermes skills

**Explicit opt-in (write / destructive):**
- File writes and patches
- Memory writes
- Session search
- Terminal access

Design principle: "Start with eyes. Add hands only when the operator asks for them."

## Key Insight — Composable Local-First Agents

The article articulates a broader architectural philosophy:

> Models should be able to talk to tools. Tools should be able to talk to memory. Local systems should be able to expose safe interfaces. Operators should be able to choose which model gets access to which surface.

This is the same pattern NanoClaw uses: persistent local memory + skill system + MCP-connected frontier model. The difference is the underlying agent runtime (Hermes Agent vs NanoClaw) and the bridge implementation.

## Relevance

- **Pattern match:** hermes-gpt is essentially what George already is for Kevin — a frontier model connected to a local operator stack via a message protocol. The "no context stuffing" insight is exactly why MCP-based tool access is more quota-efficient than manual file pasting.
- **Codex quota preservation:** Relevant if Kevin uses ChatGPT/Codex in parallel with George. The MCP-fetch-on-demand pattern eliminates context walls.
- **Hermes Agent as alternative runtime:** If Kevin wants a standalone local agent stack that isn't cloud-hosted, Hermes Agent + hermes-gpt is a viable path.
- **Status caveat:** v0.1.0, local-dev focused. Not production-tested.

## Cross-References

- [OpenAlice](openalice.md) — similar local-first agent with MCP + Alpaca/IBKR integration
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — agent composition patterns for trading workflows
