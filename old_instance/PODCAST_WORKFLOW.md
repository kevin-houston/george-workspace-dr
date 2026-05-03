# Daily Podcast Workflow - NotebookLM Edition

## Overview

Your podcast system now uses **NotebookLM by default** for the highest quality, most natural-sounding podcasts.

## How It Works

### Option C: Share-as-You-Go (Current Setup)

1. **Throughout the week:** Share X.com URLs with me via WhatsApp
2. **When ready:** Say "generate podcast" (with 5+ posts)
3. **I automatically:**
   - Generate podcast script from your posts
   - Create NotebookLM podcast (~18 min, natural conversation)
   - Compress and email to you
   - Clear queue for next batch

## Quality Comparison

| Feature | Piper TTS | NotebookLM |
|---------|-----------|------------|
| **Duration** | Short (3-4 min) | Long (15-20 min) |
| **Quality** | Good, clear | Excellent, natural |
| **Sound** | Synthetic voices | Real podcast feel |
| **Content** | Reads script directly | Expands with discussion |
| **Banter** | None | Natural conversation |
| **Speed** | Fast (3 min) | Slower (10-15 min) |
| **Cost** | Free | Free |

**Winner:** NotebookLM (now default)

## Commands

**Check queue:**
```
queue status
```

**Generate podcast:**
```
generate podcast
```
or
```
python3 generate_daily_podcast.py
```

**Clear queue:**
```
clear queue
```

## Automation Options

### Current: Manual trigger
- You say "generate podcast"
- I create and email it
- **Time: 10-15 minutes wait**

### Future: Scheduled
- Every Monday 6 AM: Auto-generate from week's queue
- No interaction needed
- **Time: 0 minutes (fully automated)**

## What You Get

**Email subject:** "Daily AI Insights Podcast - [Date]"
**Attachment:** MP3 file (~8 MB, 64kbps)
**Duration:** 15-20 minutes
**Format:** Two AI hosts discussing your curated posts

## Technical Details

- **Engine:** Google NotebookLM
- **Auth:** Already set up ✅
- **Voices:** 2 AI hosts (natural conversation)
- **Processing:** Script → NotebookLM → Compress → Email
- **Quality:** 64kbps MP3 (good balance of size/quality)

## Next Steps

Just keep sharing X.com posts with me, and say "generate podcast" when you have 5-7!

The more posts you share over time, the better the content learning system gets at understanding your preferences.
