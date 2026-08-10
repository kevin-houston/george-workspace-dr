---
title: MOSS-TTS-Nano — CPU-Only Realtime Multilingual TTS (0.1B params)
added: 2026-08-10
category: tools
url: https://github.com/OpenMOSS/MOSS-TTS-Nano
---

# MOSS-TTS-Nano

Open-source multilingual text-to-speech model from MOSI.AI / the OpenMOSS
team. Only 0.1B parameters — small enough to run realtime speech generation
directly on CPU, no GPU required. Surfaced via a tweet from Tom Dörr
(@tom_doerr, 2026-08-10) linking the repo.

**Stars:** 4,085 | **Forks:** 522 | **License:** Apache 2.0 | **Language:**
Python | **Created:** April 2026 | **Last push:** 2026-08-10 — actively
maintained.

## What it does

- Tiny (0.1B param) speech generation model, explicitly designed for
  realtime output on CPU-only hardware — no GPU dependency at all.
- Multilingual.
- Per the repo description, the deployment stack is kept "simple enough for
  local demos, web serving, and lightweight product integration" — i.e.
  positioned as an easy self-hosted alternative to cloud TTS APIs, not a
  research artifact.

## Relevance to George's Stack

**Higher than the usual speculative tool note.** George runs two live TTS
pipelines today, both dependent on Microsoft's free `edge-tts` package:

- **Lithuanian Daily Phrase** (`lithuanian_daily.py`) — `edge-tts` gets wiped
  every container restart, requiring a reinstall prepended to every run.
- **Daily AI Podcast audio** (`generate_and_email_podcast.py`) —
  `edge-tts` install additionally requires explicit
  `SSL_CERT_FILE`/`REQUESTS_CA_BUNDLE` env vars pointed at the OneCLI combined
  CA bundle, or it fails with an SSL cert error under the OneCLI proxy.

Both are documented recurring gotchas in `.local-fragments/task-registry.md`.
A local, CPU-only, pip-installable TTS model that doesn't depend on
Microsoft's cloud endpoint (and therefore doesn't route through the OneCLI
proxy or need reinstalling per container restart, if weights are cached in
the persistent workspace) could plausibly remove both failure modes at once.
Untested — no audio quality/voice-variety comparison done yet against
`edge-tts`'s `en-US-GuyNeural`/`en-US-JennyNeural` voices used for the podcast's
Alex/Jordan dialogue, and Lithuanian-language coverage specifically is
unconfirmed. Logged for reference; a real evaluation (install, generate a
sample line, compare latency/quality/voice options) would be needed before
swapping either production script over.

# Citations

- Tweet: https://x.com/tom_doerr/status/2086777084953641295
- Repo: https://github.com/OpenMOSS/MOSS-TTS-Nano
