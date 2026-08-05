---
updated: 2026-08-04
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

## Theoretical Grounding: The Always-On Agents Framework (Ding et al., arXiv:2606.30306, added 2026-08-04)

"Always-On Agents: A Survey of Persistent Memory, State, and Governance in LLM Agents" (Tianyu Ding, Aditya Nannapaneni, Bingfan Liu, Ling Zhang; submitted 2026-06-29) reviews 435 works on LLM agent systems where "future behavior depends on durable state accumulated across earlier interactions" — retrievable memories, task records, permissions, credentials, audit trails, externally committed effects. This is George's own architecture, described from the outside.

### Six diagnostic axes

The paper's core contribution is a framework for classifying any piece of persistent agent state along six axes:

1. **Authority** — who/what can write or invalidate this state?
2. **Scope** — how broadly does this state apply (single session, all sessions, cross-agent)?
3. **Mutability** — can it change, and under what write-conflict rules?
4. **Provenance** — can we trace where this state came from and verify it?
5. **Recoverability** — can it be reconstructed or rolled back after loss/corruption?
6. **Actionability** — does this state directly drive future decisions, or is it inert record-keeping?

### Mapped onto George's DR layers

| George's state layer | Authority | Scope | Recoverability (current) |
|---|---|---|---|
| `CLAUDE.local.md` / memory | Kevin edits, George reads | Cross-session | Git-backed, single source of truth |
| `wiki/` knowledge base | George writes, Kevin can edit | Cross-session, cross-query | Git-backed; index.md + log.md as internal consistency check |
| `dream_cycle/staged/` proposals | George writes (scan), George applies (build phase) | Time-boxed (date-scoped folders) | Git-backed; `apply_status` field tracks lifecycle explicitly — this is unusually good provenance/mutability discipline by the paper's own standard |
| Scheduled tasks (`ncl tasks`) | NanoClaw infra | Cross-session | **Not git-backed** — explicitly flagged as "Managed by NanoClaw" in the table above; this is the weakest recoverability link per the paper's framework, since it's the one state layer this DR section cannot independently reconstruct |
| Paper trading state (`strategy_accounts.json`, positions) | George writes | Cross-session | Git-backed but **high mutation frequency** — the paper's "mutability" axis flags this as the layer most likely to have write races (already documented empirically in `.local-fragments/task-registry.md`'s PEAD-GAP duplicate-open-pass and dream-cycle git-add race gotchas) |

### Literature-gap finding, applied

The survey's headline finding — that agent research "concentrates more heavily on accumulating and retrieving state than on governing, recovering, or relinquishing it" — is a good diagnostic prompt for this DR section specifically. George's DR pages document restore *procedure* well (git clone, re-seed credentials, verify wiki integrity) but have no page addressing **relinquishing** state — e.g. is there a policy for when a stale hypothesis stub, an abandoned tool note, or a superseded strategy log should be pruned rather than accumulated indefinitely? The wiki has grown to ~284 pages with no pruning mechanism; per this paper's framework that's an unaddressed axis, not just a scale curiosity.

### Always-On Evaluation Protocol (AOEP-v0)

The paper proposes grading agent systems on state-mutation and recovery obligations rather than answer quality alone. A lightweight version of this for George: next time [runbook-2026.md](runbook-2026.md) is refreshed, consider adding a row per state layer scoring it on the six axes above — turns the DR section from a procedure list into a structured self-audit, consistent with how the trading side already runs the Shared Strategy Evaluation Checklist and LLM Alpha Validation Checklist as structured gates rather than prose.

## Related pages

- [Git Backup Setup](git-backup.md)
- [Session Diary](diary.md)
- [Operational Runbook 2026](runbook-2026.md) — restore commands, subsystem validation, current-state snapshot
- [Strategy Reconstruction Guide](strategy-reconstruction.md) — semantic reconstruction of all 6 production strategies from first principles
- [Bilevel Autoresearch](../concepts/bilevel-autoresearch.md) — related agent-architecture theory (mechanism injection vs. state governance are complementary concerns)
- [Hitchhiker's Guide to Agentic AI](../tools/hitchhikers-guide-agentic-ai.md) — broader agentic-stack survey; the Always-On Agents paper above is the state/memory-layer deep dive that guide only touches briefly
