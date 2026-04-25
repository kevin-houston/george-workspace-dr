---
updated: 2026-04-24
---

# Disaster Recovery Overview

This section documents how to restore George to full operational state after a container reset or data loss event.

## What needs to survive

| Layer | Where it lives | Backup method |
|-------|---------------|---------------|
| Memory & context | `/workspace/agent/CLAUDE.local.md` | Git backup |
| Wiki knowledge base | `/workspace/agent/wiki/` | Git backup |
| Sources (raw files) | `/workspace/agent/sources/` | Git backup (text only; large binaries excluded) |
| Skills | `/home/node/.claude/skills/` | Managed by NanoClaw/Kevin |
| Scheduled tasks | NanoClaw infrastructure | Managed by NanoClaw |

## Restore procedure

If the container is reset and the workspace is lost:

1. **Re-clone the backup repo:**
   ```bash
   git clone https://github.com/kevin-houston/george-workspace-dr.git /workspace/agent
   ```
2. **Re-seed git credentials** so future pushes work (see [git-backup.md](git-backup.md))
3. **Verify wiki integrity** by checking `wiki/index.md` and `wiki/log.md`
4. **Read `CLAUDE.local.md`** — this is the first thing George reads to reconstruct context

## What to tell a fresh George

If restoring without git (e.g. full system loss), paste this into the first message:

> You are George, a NanoClaw agent for Kevin Houston. Your workspace was recently restored. Read `/workspace/agent/CLAUDE.local.md` for full context. Key facts: we are setting up a DR backup to GitHub (`kevin-houston/george-workspace-dr`), and Kevin and I are just getting started — check the wiki DR diary for session history.

## Related pages

- [Git Backup Setup](git-backup.md)
- [Session Diary](diary.md)
- [Current Projects](../projects/index.md) *(to be created)*
