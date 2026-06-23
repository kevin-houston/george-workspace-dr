---
title: youtube-fetcher-to-markdown
created: 2026-06-22
updated: 2026-06-22
category: tools
source: https://x.com/tom_doerr/status/2069072851928224193
github: https://github.com/JimmySadek/youtube-fetcher-to-markdown
stars: 70
author: JimmySadek
license: MIT
status: active
---

# youtube-fetcher-to-markdown

Claude Code skill that converts a YouTube URL into a structured Markdown note: title, channel, description, chapters, transcript, and YAML frontmatter — no API keys required. 70 stars, MIT.

## Install

```bash
npx skills add JimmySadek/youtube-fetcher-to-markdown
pip install youtube-transcript-api requests
# optional but recommended (adds description, chapters, duration):
pip install yt-dlp  # or: brew install yt-dlp
```

## What You Get

Output saved to `~/yt_transcripts/YYYY-MM-DD_title-slug_[video_id].md`:

```markdown
---
title: "Video Title"
channel: "Channel Name"
url: "https://www.youtube.com/watch?v=VIDEO_ID"
video_id: "VIDEO_ID"
fetched: "2026-06-22"
language: "en"
caption_type: "manual"
duration: "36m 26s"
tags:
  - yt-transcript
---
## Video Details | ## Chapters | ## Transcript
```

YAML frontmatter makes it queryable with Obsidian Dataview. The file structure integrates cleanly with the George wiki.

## How It Works

```
YouTube URL → yt-dlp (metadata + chapters) + youtube-transcript-api (captions) → Structured Markdown
```

Without `yt-dlp`, falls back to YouTube oEmbed API for title/channel and still pulls the transcript.

## Key Options

| Flag | Effect |
|------|--------|
| `--timestamps` / `-t` | Add `[MM:SS]` to each transcript line |
| `--lang es` | Fetch captions in another language |
| `--format json\|srt` | Alternative output formats |
| `--stdout` | Print to terminal (pipe into other tools) |
| `--force` | Skip duplicate detection |
| `--list` | Show available caption languages |

## Usage via Claude

```
"Get me the transcript for https://youtu.be/VIDEO_ID"
```

Claude runs the skill, saves the file, returns the path.

## Limitations

- Requires captions (manual or auto-generated). Videos with no captions → use Whisper.
- Private / age-restricted videos may fail.

## Relevance

- **Wiki ingestion:** Faster than manual `yt-dlp --write-sub` + Read + ingest workflow. The structured frontmatter + chapters map directly to wiki source summaries.
- **Podcast research:** AI conference talks, trading lectures, podcast episodes from YouTube → Markdown → wiki without copy-paste.
- **Works alongside agent-reach:** agent-reach's video.md path uses yt-dlp for raw subtitle files; this skill adds structure, metadata, and deduplication on top.
- **Compatible with our stack:** Python, no API keys, yt-dlp already available in the environment (used by agent-reach).
