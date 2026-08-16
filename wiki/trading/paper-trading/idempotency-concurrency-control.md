---
created: 2026-08-16
updated: 2026-08-16
category: paper-trading
tags: [idempotency, concurrency, locking, scheduling, filelock, apscheduler, race-conditions, ops]
---

# Idempotency & Concurrency Control for Scheduled Trading Automation

Practical mitigations for a failure class this project hits repeatedly: two overlapping
sessions running the same scheduled task (PEAD-GAP open pass, dream-cycle scan, dream-cycle
build phase, git DR backup) at or near the same trigger time. See
`.local-fragments/task-registry.md` gotchas for the incident log — this page collects the
concrete library-level fixes rather than just the incident writeups.

**Related pages**: [Dynamic / Adaptive Multi-Strategy Capital Allocation](dynamic-strategy-allocation.md) | [Risk Controls & Live Trading Monitoring](risk-controls-and-monitoring.md)

---

## Why this keeps happening here

Nearly every documented race in this project shares the same shape: **at-least-once
trigger delivery + no exclusivity guard around the side-effecting work.**

- PEAD-GAP open pass: 4 invocations within a 65-second window on 2026-07-31 (task
  scheduler + a second session racing the same 9:32 AM slot). Only one order placed
  because `pead_gap_open.py` happens to check `positions.json` before ordering — an
  *incidental* guard, not a designed one.
- Dream-cycle build phase: a compaction-interrupted run resumed and re-executed the
  wiki-append step after the pre-compaction portion had already committed, producing
  duplicate `## Research Lead: ...` sections (found 2026-08-01).
  git add/commit races: two concurrent sessions committing within the same ~10-second
  window swept files from one session into the other's commit (2026-08-03, twice).

None of these are scheduler bugs — every mainstream scheduler (including whatever
triggers NanoClaw's `ncl tasks`) gives **at-least-once**, not exactly-once, execution.
The fix has to live in the job itself: make re-running the same slot a safe no-op.

---

## Pattern 1: File lock around the critical section (best fit for this project)

This project's automation runs as single-machine Python scripts writing local JSON/log
files, not a distributed fleet — so a plain advisory file lock is the right weight class,
not Redis or Postgres.

**`filelock`** — PyPI: https://pypi.org/project/filelock/ · GitHub: https://github.com/tox-dev/py-filelock
(975 stars, MIT, actively maintained — v3.32.3 released 2026-08-13). Pure-Python,
platform-independent (`fcntl.flock` on Unix, `msvcrt` on Windows), no dependencies.

```python
from filelock import FileLock, Timeout

lock = FileLock("/workspace/agent/backtesting/paper_trading/.pead_gap_open.lock", timeout=5)
try:
    with lock:
        # entire order-submission critical section goes here
        run_open_pass()
except Timeout:
    # another instance already holds the lock — this run is the duplicate, exit quietly
    print("pead_gap_open: lock held by another process, skipping this run")
```

Limitations worth knowing before relying on it: locks are **advisory** (a process that
doesn't use the same lock file can still write concurrently — fine here since we control
all callers), and file locks are unreliable over NFS. Not a concern for this project —
everything runs in a single container's local filesystem.

Concrete fit for the documented incidents:
- `pead_gap_open.py` / `pead_open.py` / `pead_exits.py` / `pead_gap_exits.py`: wrap the
  whole run in a `FileLock(".pead_<name>.lock", timeout=5)`, skip-and-exit on `Timeout`
  instead of relying on the incidental "already in positions" check.
- Dream-cycle build phase: wrap the staged-proposal-apply loop so a compaction-resumed
  session can't re-enter the append step while (or after) another instance already
  completed it — combine with the existing `grep -c` idempotency check already documented
  in task-registry.md (belt + suspenders: the lock prevents the race, the grep check
  catches it if the lock is somehow bypassed, e.g. a stale lock from a killed process).

## Pattern 2: Idempotency key / "already done" check (cheap, no new dependency)

For jobs that write a single dated artifact (git commits, JSON watchlists, wiki pages),
the cheapest guard is checking whether today's output already exists *and is complete*
before doing any work — this project already does this in several places
(`ls dream_cycle/staged/$(date +%Y-%m-%d)/`, the podcast script's `ls ai_podcast_$(date +%Y-%m-%d).md`
check). The 2026-08-12 podcast incident showed the gap: an existence check at the *start*
of a run doesn't protect against a concurrent session finishing *during* the run. Two
layers close that gap without any new library:

1. Check-before-work (avoids redundant research/compute).
2. Re-check immediately before the final write, or rely on a tool/API that itself refuses
   to blindly overwrite (this project's `Write` tool already enforces "must Read before
   Write" — that built-in guard is what actually saved the 2026-08-12 podcast race, per
   the task-registry.md postmortem).

This is the local, no-dependency version of what a distributed system does with an
idempotency key: "have I already produced the artifact for key `(job_name, date)`? If yes,
no-op."

## Pattern 3: Scheduler-level guards, if the trigger layer supports them

If NanoClaw's `ncl tasks` scheduler ever exposes per-task concurrency controls, the
reference design is APScheduler's (https://apscheduler.readthedocs.io/en/master/userguide.html):

```python
scheduler.add_job(
    run_pead_gap_open,
    "cron", hour=9, minute=32,
    id="pead_gap_open",
    replace_existing=True,   # re-registering the same id doesn't create a duplicate job
    max_instances=1,          # refuses to start a 2nd concurrent run of this job id
    coalesce=True,             # collapses multiple queued/missed firings into one
    misfire_grace_time=60,     # don't fire at all if more than 60s late (avoid stacking)
)
```

`max_instances=1` is the closest thing to a built-in mutex a scheduler offers — it tracks
in-process, so it only helps if all runs go through the *same* scheduler instance. It would
not have prevented the PEAD-GAP 4-invocation race, since that involved two separate
trigger sources (task scheduler + a second session), which is exactly why the
job-level file lock (Pattern 1) is the more robust fix here: it works regardless of how
many independent processes think they should run the job.

## Pattern 4 (reference only, not needed at this scale): distributed locks

For completeness — if this project ever runs across multiple machines/containers instead
of one, the standard escalation path is a Redis `SET key value NX PX <ttl>` lock
(TTL = 2× expected max job duration, so a crashed holder's lock self-expires) or a
Postgres `SELECT ... FOR UPDATE NOWAIT` semaphore row. Neither is warranted here today —
introducing a Redis/Postgres dependency purely to serialize a handful of single-container
cron-style scripts would be solving a distributed-systems problem this project doesn't
have. Flagging only so a future "should we add Redis for locking" question has a
documented "no, not yet, here's why" on file.

---

## Recommended next step (not yet implemented)

Retrofit `FileLock` (Pattern 1) into the four PEAD/PEAD-GAP execution scripts
(`pead_open.py`, `pead_exits.py`, `pead_gap_open.py`, `pead_gap_exits.py`) and the
dream-cycle build phase — these are the scripts with real-money-adjacent side effects
(order submission) or destructive-if-doubled effects (wiki double-append), so they carry
the highest cost when the incidental guards fail. `filelock` is not currently installed in
`venv/` — per standing package-installation security policy, do not `pip install` it
during this off-hours session; verified it exists on PyPI (975★, MIT, tox-dev org) above,
so it's a `pip install filelock` away whenever a session with room to test the retrofit
picks this up. Staged as a dream-cycle proposal (see 2026-08-16 scan).

---

## Sources

- [filelock on PyPI](https://pypi.org/project/filelock/) — v3.32.3, MIT, platform-independent
- [py-filelock on GitHub](https://github.com/tox-dev/py-filelock) — 975★, tox-dev org
- [APScheduler user guide](https://apscheduler.readthedocs.io/en/master/userguide.html) — `max_instances`/`coalesce`/`misfire_grace_time`
- [APScheduler job reference](https://apscheduler.readthedocs.io/en/latest/modules/job.html)
