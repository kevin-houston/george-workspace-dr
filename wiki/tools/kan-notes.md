---
title: Kan — Self-Hosted Kanban / Project Management
added: 2026-06-08
category: tools
url: https://github.com/kanbn/kan
---

# Kan

Open-source, self-hostable Trello alternative. Kanban boards with cards, lists, labels, comments, activity logs, collaboration.

**Stars:** ~5k | **License:** AGPLv3 | **Last commit:** 2026-05-31

## Tech Stack

- Next.js + React + TypeScript + Tailwind CSS
- tRPC backend, PostgreSQL + Drizzle ORM
- Monorepo: pnpm workspaces + Turbo
- Auth: Better Auth (Google/Discord/GitHub/OIDC OAuth)
- Deploy: Docker Compose, Railway

## Integration Points

- **Webhooks:** `card.created`, `card.updated`, `card.moved`, `card.deleted`
- **Admin API:** `KAN_ADMIN_API_KEY` for stats/admin endpoints
- **Imports:** Trello import built-in; GitHub integration
- **tRPC routers:** OpenAPI metadata present

## Relevance to George's Stack

Not a trading tool — it's a project management UI. Potential uses:
- Track research hypotheses and portfolio goals as kanban cards
- Organize wiki ingest queue visually
- Pipe trade events via webhooks into project boards

Low priority to set up unless Kevin wants a visual task/project dashboard separate from NanoClaw's internal task system.
