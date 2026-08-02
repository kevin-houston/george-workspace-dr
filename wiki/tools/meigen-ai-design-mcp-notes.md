---
title: MeiGen-AI-Design-MCP — AI Image/Video Generation MCP Server
added: 2026-08-02
category: tools
url: https://github.com/jau123/MeiGen-AI-Design-MCP
---

# MeiGen-AI-Design-MCP

MCP server that gives Claude Code / Cursor / Windsurf-type AI coding tools
access to AI image and video generation, positioned as "a local Lovart" for
Claude Code. Shared by Kevin 2026-08-02.

**Stars:** 1,634 | **Forks:** 210 | **License:** MIT | **Language:** TypeScript
**Created:** 2026-02-07 | **Last push:** 2026-06-23 | **Contributors:** 1 (solo
maintainer, `jau123`, GitHub account since 2023 — not a burner)

## What it does

Bundles a ~1,400-prompt curated library, prompt search/enhancement, gallery
search, reference-image upload, and multi-task/parallel-agent orchestration
for batch generation. "MeiGen" is the vendor's own self-branded product
(meigen.ai) — not a known Alibaba/Tongyi model or other established AI brand,
and not a typosquat of a recognizable name.

Three backend options:
- **MeiGen Cloud** — vendor's paid API, 9+ models (GPT Image 2, Seedance,
  Veo 3.1, Grok Imagine)
- **OpenAI-compatible APIs** — bring-your-own-key to any compatible image endpoint
- **Local ComfyUI** — free, fully local/offline, needs own GPU, no API key

Prompt search/enhancement/model listing work with no key; actual generation
via MeiGen Cloud needs a paid key from meigen.ai.

## Install

npm package `meigen`: `npx -y meigen@latest`, or as a Claude Code plugin via
`/plugin marketplace add jau123/MeiGen-Art`. Requires Node.js >=18.
Dependencies are minimal/legitimate: `@modelcontextprotocol/sdk`, `sharp`,
`zod` — nothing suspicious.

## Legitimacy assessment

Organic ~5-month commit history with real version bumps (1.2.0→1.3.3),
mixed feature/fix/docs commits, 15 tags — not a single-dump repo. Cross-listed
on independent MCP directories (Glama, LobeHub). Real MIT license, working
homepage. Bus-factor risk (single maintainer) and a few open issues that look
like unsolicited ad/sponsorship pitches riding on its popularity, but the
project itself reads as a genuine, actively-maintained solo OSS project —
no hallusquatting/scam signals.

## Relevance to George's Stack

Low/none. Not a trading tool — no market data, no LLM analysis, no
backtesting tie-in. Only plausible tangential use: generating chart/dashboard
graphics or illustrative images for the podcast/session-summary/here.now
outputs, but that's speculative and no current need. Logged for reference
per Kevin's request; no action recommended.
