---
title: Job Seek — Direct-Source Job Aggregator
added: 2026-08-02
category: tools
url: https://github.com/colophon-group/jobseek
---

# Job Seek

Open-source job aggregator that scrapes 4,400+ company career pages directly
rather than pulling from third-party job boards (no LinkedIn/Indeed) — new
postings surface within hours of going live on the company's own site.

**Stars:** 115 | **Forks:** 15 | **License:** code MIT, job-listing data CC BY-NC 4.0 (non-commercial)

## Tech Stack

- Crawler: Python 3.12+, asyncio + Playwright
- Web app: TypeScript, Next.js 16, Drizzle ORM
- Data: PostgreSQL + Redis + Typesense (search) + Supabase (CDC mirror)
- Auth: Better Auth

## Key Features

- Faceted search: seniority, tech stack, location, salary
- Company pages with historical posting counts + "similar companies"
- Application tracker (free tier: saved/applied/interviewing/offered; Pro adds watchlists + email alerts)
- Multi-language (EN/DE/FR/IT), self-hostable
- 40+ monitor/scraper combos (Greenhouse, Lever, Workday, JSON-LD, generic DOM) to hit career pages directly; dedupe at origin
- Tracks major tech company career pages (Stripe, Anthropic, OpenAI, Figma, Vercel, Datadog, etc.)

## Notable

- **Agent-driven contribution workflow**: ships a `ws` CLI tool that guides coding agents (e.g. Claude Code) through onboarding a new company's career page into the scraper — a concrete example of the "agent as contributor, not just user" pattern.
- No MCP server, no LLM API usage in the core pipeline.

## Relevance to George's Stack

Not a trading tool. No direct tie-in to the trading project or NanoClaw
infra. Logged as a general tools note per Kevin's request — potential
future relevance if Kevin wants self-hosted job-market monitoring or is
interested in the agent-contribution CLI pattern as a design reference for
other self-mod / agent-onboarding workflows.
