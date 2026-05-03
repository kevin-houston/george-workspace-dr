# Disaster Recovery Guide
**For:** Kevin Claw (kevinclaw26@gmail.com)
**Last updated:** 2026-04-03
**Estimated recovery time:** 15–30 minutes

---

## What Can Go Wrong

| Scenario | Impact | Recovery |
|----------|--------|----------|
| Container restart / reinstall | Tasks lost, pip packages cleared | Full recovery below |
| Files accidentally deleted | Scripts/data lost | Restore from host backup |
| .env file missing | Podcast emails stop | Re-create .env (Step 4) |
| Single task stops running | One function down | Re-schedule that task only |

---

## Full Recovery Procedure

### Step 1 — Copy files back to the group folder

On the host machine, copy your backup of `groups/main/` back into place. The critical files are:

```
groups/main/
  NANOCLAW_DIARY.md         ← Full context document, read this first
  MEMORY.md                 ← Persistent facts and research findings
  TASK_REGISTRY.md          ← Complete prompts for all scheduled tasks ← THIS FILE'S COMPANION
  DISASTER_RECOVERY_README.md ← You are here
  heuristics.md             ← Generalizable lessons pool
  skills_index.md           ← Index of available scripts
  herenow.py                ← Dashboard publisher
  daily_ai_podcast_generator.py
  generate_podcast_audio_edge.py
  generate_and_email_podcast.py
  .env                      ← Gmail app password (GMAIL_APP_PASSWORD=...)
  paper_trading/            ← All 8 strategy scripts + portfolio JSONs
  pead/                     ← PEAD scanner + trade log
  trading_eval/             ← All backtest harnesses + results
  robinhood-advisor/        ← Portfolio advisor scripts
  podcasts/                 ← Past podcast scripts + audio
  dream_cycle/              ← Staged proposals + changelogs
```

### Step 2 — Verify files are visible

Send Andy a message:
> "Check what files are in /workspace/group and tell me what you see."

Andy should list all the key directories and files above. If anything is missing, copy it over before proceeding.

### Step 3 — Re-create all scheduled tasks

Send Andy:
> "Read TASK_REGISTRY.md and recreate all the scheduled tasks listed there."

Andy will read the full prompts from `TASK_REGISTRY.md` and fire off `schedule_task` calls for all 14 tasks. This takes about 2–3 minutes.

Verify by asking:
> "List all your scheduled tasks."

You should see 14 active tasks.

### Step 4 — Restore the .env file (if missing)

The podcast audio pipeline needs a Gmail app password. If `/workspace/group/.env` is missing:

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Create a new app password (call it "Nanoclaw Podcast")
3. Tell Andy: "Create /workspace/group/.env with GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx"

### Step 5 — Verify everything is working

Ask Andy to run a quick system check:
> "Run a system health check — verify tasks are scheduled, paper trading files are intact, and do a test podcast generation."

---

## What Does NOT Need Recovery

These things survive container loss automatically:

- ✅ All files in `/workspace/group/` (host-mapped, always persisted)
- ✅ pip auto-installs itself on first run (scripts self-bootstrap)
- ✅ Paper trading portfolio state (stored in JSON files)
- ✅ All backtest results and harness scripts
- ✅ Past podcast scripts and audio files

---

## What DOES Need Recovery

- ❌ **Scheduled tasks** — stored in the nanoclaw database, may not survive a full reinstall. Always recreate from `TASK_REGISTRY.md`.
- ❌ **Pip packages** — cleared on container reset. Scripts auto-reinstall on first run, no manual action needed.
- ❌ **`.env` file** — if you didn't copy it back, podcast emails won't send.

---

## Keeping This Guide Current

This guide stays useful only if it's kept up to date. The rules:

- **TASK_REGISTRY.md** — Update it every time a task is added, changed, or removed. Andy should do this automatically; if you notice it's stale, ask Andy to update it.
- **This file** — Update the "Last updated" date at the top whenever the recovery procedure changes.
- **NANOCLAW_DIARY.md** — Updated nightly by the dream cycle. Always reflects the latest state of the trading research and system configuration.

---

## Quick Reference — Key File Locations

| What | Where |
|------|-------|
| Full system state document | `/workspace/group/NANOCLAW_DIARY.md` |
| Task prompts for recovery | `/workspace/group/TASK_REGISTRY.md` |
| Persistent facts + research | `/workspace/group/MEMORY.md` |
| Gmail app password | `/workspace/group/.env` |
| Paper trading portfolios | `/workspace/group/paper_trading/*.json` |
| PEAD trade log | `/workspace/group/pead/pead_trades.json` |
| Podcast scripts | `/workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md` |
| Backtest results | `/workspace/group/trading_eval/rounds/` |

---

## Contact

Kevin Claw — kevinclaw26@gmail.com
Portfolio advisor emails sent here daily (weekdays, 6:35 AM CT)
Podcast MP3 emails sent here daily (6:10 AM CT)
