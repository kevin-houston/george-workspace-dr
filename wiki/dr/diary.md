---
updated: 2026-08-20
---

# Session Diary

Append-only log of sessions with Kevin. Each entry captures: what we worked on, decisions made, and what's next. This is the human-readable narrative layer of disaster recovery.

**Maintenance note (2026-08-20):** This file sat frozen at the Session 1 entry for nearly four months while the DR git-backup mechanism, the wiki (now 301+ pages), the trading hypothesis pipeline (500+ H-numbers), and PEAD paper trading all went from "not yet built" to "running in production nightly." The entry below is a compressed catch-up rather than a full session-by-session backfill — treat [DR Overview](overview.md) and [Operational Runbook 2026](runbook-2026.md) as the authoritative current-state references; this diary's job is narrative continuity, not exhaustive detail.

---

## 2026-04-24 | Session 1 — First contact & DR setup

**Who:** Kevin Houston (telegram-mg-17769), George

**What we did:**
- Kevin connected to George for the first time via Telegram
- Established goal: set up disaster recovery so our work persists
- Kevin installed the `wiki` skill, which initialized the wiki at `/workspace/agent/wiki/`
- Started DR setup: initialized local git repo at `/workspace/agent/`, created initial commit
- Added remote: `https://github.com/kevin-houston/george-workspace-dr.git`
- Kevin added a GitHub Personal Access Token to the OneCLI vault under `github.com`
- Hit a blocker: vault proxy doesn't surface the token for git HTTPS operations — need to resolve

**Decisions made:**
- Repo name: `george-workspace-dr` under `kevin-houston` GitHub account
- Wiki will serve dual purpose: knowledge base AND DR diary (this file)
- Git backup is the raw-file layer; wiki is the semantic/narrative layer
- Strategy: DR diary first (this), git backup second once auth is resolved

**Blocked on:**
- GitHub credential access — see [git-backup.md](git-backup.md)

**Next session:**
- Resolve GitHub token access
- Create the remote repo and push
- Set up nightly scheduled push
- Begin working on whatever Kevin wants to build together

---

## 2026-04-24 → 2026-08-20 | Catch-up entry — four months compressed

**Who:** Kevin Houston, George (unattended nightly sessions form the bulk of this period)

**What happened, in arc form:**
- **Git backup unblocked.** The vault-proxy blocker from Session 1 was resolved by bypassing the OneCLI proxy for `github.com` specifically (`NO_PROXY=github.com` + explicit CA bundle) rather than routing GitHub auth through the proxy at all — see [git-backup.md](git-backup.md) for the working mechanism. Nightly pushes have run reliably since, with `git pull --rebase` as the standard fix on the rare "remote rejected" race against a concurrent session.
- **The trading research program became the dominant workstream.** What Session 1 called "whatever Kevin wants to build together" turned out to be a systematic algorithmic-trading hypothesis pipeline: `wiki/trading/backtesting/hypothesis-log.md` now tracks 500+ numbered hypotheses (H001-H524+), each independently backtested with IS/OOS splits, walk-forward validation, and (critically, learned the hard way) explicit look-ahead-bias audits.
- **A recurring look-ahead-bias bug family became the single biggest lesson of the whole project.** Starting mid-2026, a systematic audit found the same `as_of` date bug (an order-block/FVG filter reading the *current* holding month's own closing price instead of the prior month's) had silently inflated Sharpe ratios across at least 8 separate "confirmed" hypotheses (H343-H346, H355-H356, H411/H416-H418, H470, H483-H484, H492-H493, H509-H510). Corrected re-runs retracted or narrowed nearly every one of them — several claimed 3-5x Sharpe ratios corrected down to below their gate thresholds. This is now the standing methodological caution for all future backtest work: any signal computed "as of" a rebalance date must be checked for whether that date's own close is visible to the signal.
- **A production portfolio went live in paper trading.** Current allocation: H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%, OOS Sharpe ~4.16, near-zero negative years 2004-2025 in backtest. PEAD (post-earnings-announcement-drift, H163/H174) runs as a separate 5-account paper-trading system with overnight/open/intraday/exit passes on a fixed schedule.
- **The "dream cycle" nightly research loop was built** — an unattended 11 PM scan (WebSearch for new arXiv finance/agent papers, wiki expansion, staged proposals) feeding a 4 AM build phase (apply/flag staged proposals, changelog). This mechanism is itself responsible for a chunk of the wiki's growth from a handful of pages to 301+.
- **Operational scar tissue accumulated fast enough to need its own living document** — `.local-fragments/task-registry.md` now documents ~15 recurring tasks (PEAD passes, dream cycle, podcast generation, git backup, wiki maintenance) with per-task gotchas, most discovered via race conditions between overlapping scheduled triggers (duplicate 9:32 AM PEAD-GAP opens, duplicate dream-cycle build phases, git-add sweeping in concurrent sessions' files). The pattern is consistent enough across tasks that it's treated as a standing operational hazard class, not a one-off bug per task.

**Where things stand now (2026-08-20):**
- Wiki: 301+ pages across Trading & Prediction Markets (dominant section), Impact Investing, General Tech, AI Industry, Disaster Recovery, Meta/Maintenance.
- DR: git backup running nightly and unattended; this diary and git-backup.md refreshed today after being the two most neglected DR pages (untouched since this file's Session 1 entry).
- Trading: production paper portfolio live; hypothesis pipeline active with the look-ahead-bias audit as an ongoing background task working through older "confirmed" results.

**Next session:**
- Continue the look-ahead-bias audit blast-radius review for any remaining un-audited OB/FVG-filter hypotheses.
- Keep this diary updated per-session going forward rather than letting it lapse again — the four-month gap made this catch-up entry necessary and it should not recur.
