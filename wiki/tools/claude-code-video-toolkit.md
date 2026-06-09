---
title: claude-code-video-toolkit — AI-Native Video Production for Claude Code
added: 2026-06-08
category: tools
url: https://github.com/digitalsamba/claude-code-video-toolkit
---

# claude-code-video-toolkit

AI-native video production workspace for Claude Code. Automates the full pipeline: NARRATE → SCORE → GENERATE → COMPOSE → RENDER. Produces explainer videos, product demos, sprint reviews, presentations.

**Stars:** ~1,354 | **License:** MIT | **Last commit:** 2026-05-20

## Tech Stack

- **Video framework:** Remotion (React-based), TypeScript, Node.js 18+
- **TTS:** ElevenLabs API / Qwen3
- **Music gen:** ACE-Step
- **Image gen:** FLUX.2 | **Video gen:** LTX-2 | **Image editing:** QwenEdit
- **Talking heads:** SadTalker
- **Cloud GPU:** Modal (recommended, $30/mo free tier) or RunPod
- **Storage:** Cloudflare R2 (10GB free)
- **Optional:** FFmpeg, Playwright (browser recording)

## Claude Code Integration

Fully native — ships with:
- `.claude/skills/` — Remotion, ElevenLabs, FFmpeg, Qwen-Edit, LTX2, MoviePy, etc.
- `.claude/commands/` — 12 slash commands: `/video`, `/brand`, `/template`, `/scene-review`, `/generate-voiceover`, `/redub`, `/voice-clone`, etc.

## Relevance to George's Stack

**Some overlap:** Voiceover generation mirrors existing edge-tts podcast pipeline. Python tooling compatible.

**Potential use cases:**
- Visual recap videos from trading research sessions
- Animated intro/outro for the daily AI podcast
- Screencasted wiki walk-throughs

**Not a fit for:** Lithuanian TTS (different pipeline), algo trading, knowledge management.

**Verdict:** Worth knowing about if Kevin wants video output from any research/podcast work. No immediate integration need — the podcast currently stays audio-only.
