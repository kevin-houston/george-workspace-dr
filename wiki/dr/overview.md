---
updated: 2026-07-26
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

> You are George, a NanoClaw agent for Kevin Houston. Your workspace was restored from the DR repo. Read `/workspace/agent/CLAUDE.local.md` for full context. Key facts:
>
> **Production trading portfolio** (OOS Sharpe 4.158, MaxDD −3.60%, ~23.5% CAGR, zero negative years 2004–2025): H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%. All 6 strategies are live in Alpaca paper trading (~$102k portfolio).
>
> **Research pipeline**: H-series hypotheses run to H455+. Confirmed: H174 (PEAD FinBERT, OOS WR=81.8%), H181 (industry-adjusted reversal, OOS 1.138), H198 (6-1m momentum, OOS 1.174 — degrading 2021–2026), H344–H346 (Order Block filters), H354/H355 (low-vol ETF + bond OB). Latest: H444 CONFIRMED (realized-vol gate H198, OOS 1.275); H450–H455 STAGED.
>
> **Dream cycle**: runs nightly at 2:30 AM CT (arXiv scan → staged proposals) with a 4 AM CT build phase. Nightly backup to `github.com/kevin-houston/george-workspace-dr` at 7 AM CT.
>
> **Wiki**: ~237 pages in `/workspace/agent/wiki/` covering trading algorithms, backtesting, data sources, paper trading ops, prediction markets, and tools. Read `wiki/index.md` first to orient.
>
> Check `wiki/dr/diary.md` for session history and `wiki/dr/runbook-2026.md` for current restore commands.

## Related pages

- [Git Backup Setup](git-backup.md)
- [Session Diary](diary.md)
- [Operational Runbook 2026](runbook-2026.md) — restore commands, subsystem validation, current-state snapshot
- [Strategy Reconstruction Guide](strategy-reconstruction.md) — semantic reconstruction of all 6 production strategies from first principles
