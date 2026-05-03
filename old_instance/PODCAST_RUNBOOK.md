# Daily AI Insights Podcast — Disaster Recovery Runbook

*Last updated: 2026-04-18. This document is sufficient for a new agent to fully recover or rebuild the podcast pipeline from scratch.*

---

## Overview

The podcast pipeline has two stages:

| Stage | Task ID | Schedule | What it does |
|-------|---------|----------|--------------|
| **Script generation** | `task-1775234497467-6m3dye` | 6:00 AM CT daily | Agent runs web searches, selects 4 stories, writes markdown script |
| **Audio + email** | `task-1775234877680-edslc9` | 6:10 AM CT daily | Python script converts script to Edge TTS MP3, emails to Kevin |

The 10-minute gap lets the script generation finish before audio starts.

---

## File Locations

| File | Purpose |
|------|---------|
| `/workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md` | Daily script output |
| `/workspace/group/podcasts/podcast_audio_YYYY-MM-DD.mp3` | Daily audio output |
| `/workspace/group/generate_and_email_podcast.py` | Audio generator + emailer script |
| `/workspace/group/.env` | Gmail credentials (`GMAIL_APP_PASSWORD=...`) |
| `/workspace/group/podcasts/audio/` | Temp segment files (auto-created) |

---

## Stage 1: Script Generation

### What the agent does

The script generation task (Task 13) runs as an isolated agent with this prompt (current version, includes mandatory verification step added 2026-04-15):

```
You are Ernesto, generating today's Daily AI Insights podcast script (6 AM CT daily).

Do 6 WebSearches covering today's top stories in: generative AI, agentic engineering,
LLM releases, AI regulation, AI hardware/infrastructure, and AI research papers.

Score each story on: newsworthiness (breaking today?), relevance to builders/developers,
narrative richness (enough depth for 3-4 minutes of conversation?). Select the 4 best stories.

For each selected story, do a WebFetch on the primary source URL to get full article detail.

**VERIFICATION STEP — mandatory before writing the script:**
For any specific claim about a product launch, model release, funding round, or major
announcement, do a second WebSearch to cross-reference the claim. If two independent
sources do not confirm the claim, do NOT include it in the script. For claims that are
unverified or contested, either drop the story or note the uncertainty explicitly in the
dialogue (e.g., "reports suggest" / "according to X" rather than stating it as fact).
Never state a product was released, a deal closed, or a number is definitive unless at
least two independent sources confirm it.

Then write a complete podcast script following this format:
- Title: "Daily AI Insights — [Month Day, Year]"
- Episode title: a punchy 4-6 word phrase capturing the day's theme
- Runtime: ~12-14 minutes
- Hosts: Alex (male) and Jordan (female)
- Structure: INTRO → SEGMENT 1 → SEGMENT 2 → SEGMENT 3 → SEGMENT 4 → OUTRO → SOURCES
- Each segment: 3-5 minutes of back-and-forth dialogue, no monologues longer than 4 sentences
- Style: NPR-meets-tech-podcast. Substantive but conversational. Real facts, real numbers. Not hype.
- Word count: 1,800–2,400 words

Save the script to: /workspace/group/podcasts/ai_podcast_YYYY-MM-DD.md

Do NOT send Kevin a message — the 6:10 AM audio task picks up from here.
```

### Script format requirements

The audio generator parses the script looking for lines matching:
```
**Alex:** [dialogue text]
**Jordan:** [dialogue text]
```

Both structured (`## INTRO` / `## SOURCES` format) and unstructured (`**[INTRO]**` / `**[SEGMENT N]**`) are supported. The parser skips stage directions like `[laughs]`.

### Manual recovery — generate a script

Run the task manually as an agent or just write the script directly to the correct path:

```bash
# Verify today's script exists
ls /workspace/group/podcasts/ai_podcast_$(date +%Y-%m-%d).md
```

If missing, either trigger the scheduled task or run the script generation prompt manually in a new agent session.

---

## Stage 2: Audio Generation + Email

### The script

`/workspace/group/generate_and_email_podcast.py` does everything:
1. Finds today's script in `/workspace/group/podcasts/`
2. Parses `**Alex:**` and `**Jordan:**` dialogue lines
3. Calls Microsoft Edge TTS (via `edge-tts` Python library) for each line
   - Alex: voice `en-US-GuyNeural`
   - Jordan: voice `en-US-JennyNeural`
4. Merges segments using ffmpeg (falls back to raw byte concat if ffmpeg unavailable)
5. Sends MP3 as email attachment via Gmail SMTP

### Dependencies

| Dependency | Install command | Notes |
|-----------|----------------|-------|
| `edge-tts` | `python3.11 -m pip install edge-tts --break-system-packages` | Microsoft neural TTS, free, no API key needed |
| `ffmpeg` | Usually pre-installed | Falls back to Python byte-concat if missing — output is valid but may lack ID3 tags |
| Gmail app password | Already in `/workspace/group/.env` as `GMAIL_APP_PASSWORD=...` | Kevin's Gmail app password, not the main account password |

### ⚠️ Known issue: edge-tts PATH problem

The auto-install logic in the script installs edge-tts to `/tmp/podcast_deps` but the import fails if PATH doesn't include `/home/node/.local/bin`. **Always run with this command:**

```bash
PATH="/home/node/.local/bin:/usr/bin:$PATH" \
PYTHONPATH="/home/node/.local/lib/python3.11/site-packages:$PYTHONPATH" \
/usr/bin/python3.11 /workspace/group/generate_and_email_podcast.py
```

Or pre-install with `--break-system-packages`:
```bash
/usr/bin/python3.11 -m pip install edge-tts --break-system-packages -q
```

After that, the plain `python3.11 generate_and_email_podcast.py` invocation works.

The Task 14 prompt uses `curl | python3 get-pip.py` bootstrap but this can fail. If Task 14 fails with `ModuleNotFoundError: No module named 'edge_tts'`, run the pre-install above and re-run manually.

### Manual recovery — generate audio for today

```bash
cd /workspace/group

# Option A — with PATH fix
PATH="/home/node/.local/bin:/usr/bin:$PATH" /usr/bin/python3.11 generate_and_email_podcast.py

# Option B — if edge-tts is already installed
/usr/bin/python3.11 generate_and_email_podcast.py
```

Expected output:
```
📄 Using most recent script: ai_podcast_YYYY-MM-DD.md
✅ Extracted NN dialogue segments
🎙️  Generating audio (NN segments)...
✅ Audio saved: podcast_audio_YYYY-MM-DD.mp3 (X.XX MB)
✅ Email sent to kevinclaw26@gmail.com
```

### Gmail credentials

The script reads `GMAIL_APP_PASSWORD` from `/workspace/group/.env`. If this is missing:
1. Go to myaccount.google.com → Security → App passwords
2. Create an app password for "Mail"
3. Add `GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx` to `/workspace/group/.env`

---

## Scheduled Task Configuration

Both tasks are managed by NanoClaw. To verify or recreate:

```python
# List tasks (use mcp__nanoclaw__list_tasks)
# Task IDs as of 2026-04-18:
# Script gen: task-1775234497467-6m3dye  (cron: 0 6 * * *)
# Audio+email: task-1775234877680-edslc9  (cron: 10 6 * * *)
```

To recreate Task 14 (audio + email) if lost:
```python
mcp__nanoclaw__schedule_task(
    prompt="""You are Ernesto, running the daily podcast audio generation and email task (6:10 AM CT daily).

Bootstrap pip if needed, then run:
```
/usr/bin/python3.11 -m pip install edge-tts --break-system-packages -q 2>/dev/null || true
PATH="/home/node/.local/bin:/usr/bin:$PATH" /usr/bin/python3.11 /workspace/group/generate_and_email_podcast.py
```

The script finds today's podcast markdown in /workspace/group/podcasts/, generates Edge TTS audio
for each Alex/Jordan dialogue line, merges into MP3, and emails to kevinclaw26@gmail.com.

Do NOT send Kevin a message on success. Only message him if generation or email fails.""",
    schedule_type="cron",
    schedule_value="10 6 * * *"
)
```

---

## Diagnostic Checklist

If the podcast wasn't received:

1. **Check if script exists**: `ls /workspace/group/podcasts/ai_podcast_$(date +%Y-%m-%d).md`
   - Missing → Task 13 failed or was skipped. Run script generation manually.
   
2. **Check if audio exists**: `ls /workspace/group/podcasts/podcast_audio_$(date +%Y-%m-%d).mp3`
   - Missing → Task 14 failed. Run `generate_and_email_podcast.py` manually.
   
3. **Check email credentials**: `grep GMAIL_APP_PASSWORD /workspace/group/.env`
   - Missing → Set up Gmail app password (see above).

4. **Check edge-tts**: `/usr/bin/python3.11 -c "import edge_tts; print('ok')"`
   - Fails → Run `python3.11 -m pip install edge-tts --break-system-packages`

5. **Check task status**: Use `mcp__nanoclaw__list_tasks` to verify both tasks are active.

---

## History

- **2026-02-23**: Pipeline created, scripts saved to `/workspace/group/podcasts/`
- **2026-04-15**: Mandatory verification step added to Task 13 prompt after GPT-6 false claim
- **2026-04-18**: This runbook created; edge-tts PATH issue documented

---

*See also: TASK_REGISTRY.md (Tasks 13–14 for full prompts)*
