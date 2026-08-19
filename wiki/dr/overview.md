---
updated: 2026-08-19
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

## MemTxn: A Transaction Boundary for Agent Memory (Cui et al., arXiv:2607.27834, added 2026-08-05)

The Always-On Agents section above flags **recoverability** as an axis and specifically calls out paper trading state (`strategy_accounts.json`, positions files) as "the layer most likely to have write races" — citing the documented PEAD-GAP duplicate-open-pass and dream-cycle git-add race gotchas in the task registry. MemTxn (Hanshuai Cui, Zhiqing Tang, Zhi Yao, Fanshuai Meng, Qianli Ma, Weijia Jia; submitted 2026-07-30) is a direct answer to that gap: it proposes exactly the missing governance layer.

### What it does

MemTxn sits outside the answer model as a **transaction boundary** for writable agent memory, addressing the failure mode where "errors in writable memory can persist and corrupt future behavior." Three components:

1. **Ordered PatchTest** — validates whether a proposed memory update is actually supported by its cited source before accepting the write (source-grounding check, not just format validation).
2. **Temporal Resolver** — when facts conflict (e.g. two sessions write different values for the same key), selects which version is authoritative rather than silently overwriting or duplicating.
3. **Durable snapshot journal** — a versioned log that lets the system restore the last-known-good "declared active map" after a fault, without needing to know the actual physical write set that caused the corruption.

### Reported results

- Audit task: accepted all 60 source-supported writes, correctly rejected all 179 unsupported "hard negative" writes (zero false accepts in the reported setup).
- Fault recovery: fully restored the declared active state on LongMemEval-S and LoCoMo benchmark states after injected multi-key faults.
- On MemoryAgentBench FactConsolidation, outperformed a dense-retrieval baseline by 17–24 F1 points across five settings.

### Why this matters for George's DR posture specifically

George's current recovery mechanism for concurrent-write corruption is **manual and after-the-fact**: the task registry documents multiple incidents (dream-cycle git-add race 2026-08-01, cross-session commit sweep 2026-08-03, PEAD-GAP quadruple-invocation 2026-07-31) where the fix was "notice the anomaly, `git reset --soft`, hand-restore the correct file set." That's forensic reconstruction, not a designed recovery path — every incident report in the task registry is effectively a human/agent doing MemTxn's Temporal Resolver and snapshot-journal job by hand, after something already went wrong.

MemTxn's specific mechanisms map onto concrete George gaps:

| MemTxn mechanism | George's current equivalent | Gap |
|---|---|---|
| Ordered PatchTest (source-grounding before write) | None — dream cycle proposals write to wiki files based on `apply_status` field with no independent verification the JSON's cited source actually supports the claim | A staged proposal with a fabricated or misread source would be applied as-is |
| Temporal Resolver (conflict version selection) | None — "last write wins" via git; conflicts are discovered post-hoc via `git show --stat` diffing (documented practice in task registry) | No principled way to pick the "right" version when two sessions write conflicting `strategy_accounts.json` state, only after-the-fact detection |
| Durable snapshot journal (restore without knowing physical write set) | Git history — but only if the corrupting commit is identified and manually isolated; no automatic "restore active map" primitive | Recovery requires a human/agent to correctly diagnose which files were unintentionally swept into a commit before it can be fixed |

This isn't a call to build a full MemTxn implementation — git + `apply_status` + the task registry's documented gotchas are working well enough in practice. But the highest-leverage narrow adoption would be a lightweight **Temporal Resolver convention** for the two highest write-frequency files (`strategy_accounts.json` and `pead_positions.json`/`pead_gap_positions.json`): a monotonic version/timestamp field checked before write, so a stale concurrent write fails loudly instead of silently overwriting newer state. That's the one piece of MemTxn's design that's cheap to adopt without a dependency and directly targets the failure mode already observed twice this month.

## DFAH-Bench: Benchmarking Observable Agent Instability in Financial Decision-Making (arXiv:2607.20491, added 2026-08-19)

The Always-On Agents and MemTxn sections above both target **state corruption/write-race recoverability** — what happens when concurrent writes to `strategy_accounts.json` or `pead_positions.json` conflict. DFAH-Bench targets a related but distinct failure mode: **decision replayability** — whether re-running the same agent decision under nominally the same conditions produces the same *observable execution path* (same tools called, same order, same arguments), not just the same final answer.

**Source detail level:** gathered via WebSearch at abstract/methodology granularity; full-text has not been independently fetched/verified in this pass, so treat specific numbers below as reported-by-abstract, not independently confirmed.

### What it measures

DFAH-Bench operationalizes a "Determinism-Faithfulness Assurance Harness" (DFAH), where **faithfulness means fidelity of observable execution under replay, not answer correctness**. The key insight: a financial AI agent can reach the *same decision* twice while using different tools, a different call order, or different recorded arguments/results to get there — and outcome-only evaluation (did it get the right answer?) misses this variation entirely, even though it matters for replay, audit, and change control.

Two metrics: **Decision Agreement Rate (DAR)** — do repeated runs reach the same decision? — and **Tool-path Agreement Rate (TAR)** — do repeated runs use the same sequence of tools/arguments to get there?

### Reported findings (abstract-level)

- Across 4,157 retrospective episodes (719 synthetic compliance/financial DataOps groups) plus a 570-episode/190-group argument-aware prospective extension: decisions agree 94.2–95.1% of the time, but exact tool-name paths agree only 66.9–69.4% — a 25.8–27.3 point gap between "got the same answer" and "got there the same way."
- Argument-and-result agreement (did the tool calls use the same arguments and get the same results, not just the same tool names) falls further, to 45.0–51.5%.
- Small models (7–20B) show near-perfect determinism through rigid pattern matching, but at the cost of accuracy (20–42%). Frontier models show moderate determinism (50–96%) with better accuracy. **No model tested achieves both high determinism and high accuracy** — these appear to trade off against each other.

### Why this matters for George's DR posture specifically

The task registry's documented dream-cycle duplication incidents (2026-08-16, 2026-08-17) are exactly a DAR/TAR gap in miniature: two independent sessions reached the *same decision* (flag the same staged proposal, write the same changelog) via *different execution paths* (different tool-call sequences, different session contexts) at the same 4 AM trigger slot. High DAR (both sessions converged on the correct action) combined with unverifiable TAR (no record of *how* each session got there, only that a `git diff` after the fact showed identical output) is precisely the failure DFAH-Bench is built to detect and quantify, rather than leaving it to manual `git log`/`git diff` forensics as the task registry's detection pattern currently does.

**Practical implication, not yet actioned:** George's existing detection pattern ("before writing anything in the build phase, `git log`/`git diff HEAD` — if a commit already touched the file today, verify contents match and stop") is a *DAR-only* check — it confirms the final decision matches, but has no visibility into *how* the other session got there. A DFAH-style TAR record (a lightweight log of which tools/steps were taken to reach a build-phase decision, not just the final commit) would let a future session distinguish "the other session did the same reasoning correctly" from "the other session got lucky/took a shortcut that happened to converge" — a distinction that matters more as build-phase logic grows more complex. No hypothesis or action item assigned here; this is a design-reference note logged the same way the Always-On Agents and MemTxn sections were, for future runbook refinement.

### Related work note

A companion paper surfaced in the same search, "Harness as an Asset: Enforcing Determinism via the Convergent AI Agent Framework (CAAF)" (arXiv:2604.17025), proposes an enforcement-side answer to the same problem DFAH-Bench measures — not yet reviewed in depth, flagged here for a possible follow-up pass.

## Related pages

- [Git Backup Setup](git-backup.md)
- [Session Diary](diary.md)
- [Operational Runbook 2026](runbook-2026.md) — restore commands, subsystem validation, current-state snapshot; Section 3 documents the concurrent-write incidents MemTxn's design targets
- [Strategy Reconstruction Guide](strategy-reconstruction.md) — semantic reconstruction of all 6 production strategies from first principles
- [Bilevel Autoresearch](../concepts/bilevel-autoresearch.md) — related agent-architecture theory (mechanism injection vs. state governance are complementary concerns)
- [Hitchhiker's Guide to Agentic AI](../tools/hitchhikers-guide-agentic-ai.md) — broader agentic-stack survey; the Always-On Agents paper above is the state/memory-layer deep dive that guide only touches briefly
