---
added: 2026-05-08
category: ai-infrastructure
url: https://livekit.com/
---

# LiveKit

Open-source framework and cloud platform for building voice, video, and multimodal AI agents.

## What it does

LiveKit handles the real-time communication layer so developers can focus on agent logic. Core components:

- **Agent framework** — build conversational AI agents with voice/video/data channels
- **Media server** — WebRTC-based, low-latency, open source (self-hostable)
- **SDKs** — Python, JS/TS, Go, Swift, Kotlin, Unity, Rust
- **Cloud dashboard** — managed hosting at cloud.livekit.io (free tier available)

## Key capabilities

- Real-time audio/video streaming between agents and users
- Voice activity detection, noise cancellation, transcription hooks
- Support for embodied/physical AI agents (robotics)
- Native integration points for LLMs and STT/TTS pipelines
- Multi-participant rooms — can connect multiple agents + humans

## Relevance to this project

- **Voice-enabled trading interface** — could wire a voice agent to paper trading scripts (speak orders, hear P&L updates)
- **Podcast generation upgrade** — real-time TTS with better latency than edge-tts batch approach
- **Agent-to-agent communication** — LiveKit rooms can serve as a comms layer between multiple specialized agents
- **Dashboard enhancement** — streaming audio/video into the trading dashboard

## Self-host vs cloud

| | Self-host | Cloud |
|---|---|---|
| Cost | Free (infra costs only) | Free tier + paid plans |
| Setup | Docker compose, ~15 min | Instant |
| Control | Full | Managed |

GitHub: https://github.com/livekit/livekit

## See also

- edge-tts (current podcast TTS) — `generate_and_email_podcast.py`
- Dashboard: `dashboard/index.html`
