---
title: birdclaw
created: 2026-06-22
updated: 2026-06-22
category: tools
source: https://birdclaw.sh/
github: https://github.com/steipete/birdclaw
license: MIT
status: active development — usable but not finished; schema churn expected
---

# birdclaw

Local-first Twitter/X workspace: offline archive, AI-ranked inbox, full-text search, and compose/reply flows — all in a single SQLite database + local web app + CLI.

**Not affiliated with X Corp.**

## Install

```bash
brew install steipete/tap/birdclaw
```

## What It Does

- **Single SQLite database** — stores tweets, DMs, likes, bookmarks, mentions, follows, blocks, mutes across multiple accounts
- **Archive import** — imports your Twitter data export; can selectively re-import outdated data
- **Full-text search** — FTS5 indexing across all stored content
- **Local web interface** — timeline views: Home, Mentions, Likes, Bookmarks, DMs, Inbox
- **AI-ranked inbox** — optional OpenAI integration to filter low-signal mentions and DMs
- **Streaming digest** — daily/weekly summaries from local data
- **Network mapping** — visualize followers/following by location
- **Compose + reply** — from CLI or web interface
- **Local media caching** — images, video, GIFs cached locally
- **Git-friendly backups** — yearly and per-conversation text shards

## Key CLI Commands

```bash
birdclaw archive find --json    # query local archive
birdclaw import archive         # import Twitter data export
birdclaw sync timeline          # pull latest timeline to local DB
birdclaw search tweets          # full-text search
birdclaw inbox --score          # AI-ranked inbox view
birdclaw compose reply          # reply from CLI
birdclaw today                  # today's digest
birdclaw digest week            # weekly summary
```

## Relevance

Useful if Kevin wants to archive and analyze X/Twitter data locally — for research, monitoring, or building a personal feed without relying on X's interface. The AI-ranked inbox could be useful for signal/noise filtering on large follow lists. MIT license means it's hackable.

**Status caveat:** Author explicitly notes schema churn and rough edges while core settles. Not production-stable yet.
