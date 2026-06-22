---
added: 2026-06-21
updated: 2026-06-21
type: tool-guide
source: https://github.com/Smaug6739/Alexandrie
stars: 1666
license: MIT
---

# Alexandrie

Self-hosted open-source knowledge base. GitHub: https://github.com/Smaug6739/Alexandrie

**Tag line:** "A fast, self-hosted Markdown knowledge base that's easy to deploy and packed with features you actually need."

---

## What It Does

Wiki / note-taking platform with a focus on structured, shareable documents rather than a raw file store. Closer to Notion or Confluence than Obsidian.

**Key features:**
- **Extended Markdown editor** (CodeMirror 6): KaTeX math, colored containers, academic blocks, footnotes, interactive checkboxes, custom snippets, voice-to-text
- **Full-text search** with content snippets and relevance ranking
- **Granular permissions** — 5-level per-document ACL (None → Read → Write → Admin → Owner)
- **Workspaces + tree sidebar** — nested docs, tags, bookmarks, pinned notes
- **Kanban boards** built in (same space as Kan but integrated into the KB)
- **SSO / OIDC** — Google, GitHub, Microsoft, Discord, or any OpenID provider
- **PWA + offline support** — installable on any device, works without internet
- **One-command deploy** — `docker compose up -d` → http://localhost:8200
- **Backups** — export all docs + files + settings as ZIP

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | Nuxt 4 (Vue 3), TypeScript, Pinia, SCSS |
| Editor | CodeMirror 6 |
| Backend | Go (Gin), JWT, sqlx |
| Database | MySQL 8 |
| Storage | S3-compatible (RustFS, MinIO, AWS S3, Garage) |
| Auth | JWT + OIDC/SSO |
| Deploy | Docker Compose (4 services) |

## Comparison to Current Setup

| Feature | George's wiki (markdown files) | Alexandrie |
|---------|-------------------------------|------------|
| Storage | Git-tracked .md files | MySQL + S3 |
| Editing | Claude Code / text editor | Browser UI with rich editor |
| Search | grep / wiki/index.md | Full-text indexed |
| Sharing | Here.now publish | Built-in per-doc permissions |
| Kanban | — | Built in |
| Offline | ✓ (it's files) | ✓ (PWA) |
| AI integration | Native (I write the wiki) | None built-in |
| Deploy complexity | Zero (already running) | Docker Compose (4 services) |

## Relevance

Alexandrie is primarily a **human-facing knowledge base** — rich browser editing, sharing with other people via permissions, offline access on mobile. The current George wiki is optimized for agent-read/write (plain markdown, git-tracked, no UI needed).

**Potential use case:** If Kevin wants a browser-accessible, shareable version of the wiki for human reading — e.g., sharing research notes with collaborators or browsing on mobile with a richer UI — Alexandrie could serve as a companion layer. Would need a sync mechanism from George's markdown → Alexandrie (no native import pipeline, but markdown files could be batch-imported).

**Not a replacement** for the agent wiki: George needs direct file access to read/write pages. A MySQL-backed system requires API calls, not file reads.

**Compare with:** [Kan](kan-notes.md) (kanban only, no document editing); Alexandrie is strictly more capable but heavier (4 Docker services vs Kan's Postgres stack).
