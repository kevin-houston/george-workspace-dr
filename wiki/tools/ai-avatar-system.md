---
created: 2026-05-28
updated: 2026-05-28
source: https://github.com/PunithVT/ai-avatar-system
stars: 114
---

# ai-avatar-system (AvatarAI) — Real-Time AI Avatar Platform

**Repo**: github.com/PunithVT/ai-avatar-system  
**Language**: Python + TypeScript (Next.js 14 + FastAPI)  
**License**: MIT  
**Stack**: FastAPI · Next.js · PostgreSQL · Redis · Docker Compose · CUDA 11.8

Upload a photo, clone a voice from 5 seconds of audio, have a real-time conversation with lip-sync video on every response.

```
[mic] → Whisper STT → Claude/GPT-4/Llama → XTTS v2 TTS → MuseTalk lip-sync → [video]
                       < 2–4s first chunk on AWS GPU >
```

---

## Key Features

| Feature | Details |
|---------|---------|
| Voice cloning | XTTS v2 zero-shot — 5–30s clip is enough |
| STT | faster-whisper (CUDA), 18+ languages |
| Lip-sync video | MuseTalk V1.5, 30 FPS on GPU; FFmpeg CPU fallback |
| LLM backends | Claude · GPT-4o · Llama 3 (Ollama, local) |
| Streaming | Sentence-chunked WebSocket — first video chunk plays while rest generates |
| Idle animation | CSS breathing animation while waiting |
| Auth | JWT, conversation history, persistent sessions |
| Local mode | `USE_LOCAL_STORAGE=true` — fully offline dev |
| AWS deploy | One-command `g5.xlarge` with Terraform IaC |
| Observability | Prometheus, Celery Flower, Sentry, structured logging |

---

## Architecture

Two core services under Docker Compose:
- **FastAPI backend** — WebSocket manager, sentence chunking, TTS → MuseTalk pipeline, Celery workers for async video generation
- **Next.js frontend** — Avatar Studio (upload), Voice Studio (cloning), Chat Interface (streaming video)

Storage: local filesystem (`USE_LOCAL_STORAGE=true`) or S3. Auth: JWT. DB: PostgreSQL + Redis.

---

## Quick Start

```bash
git clone https://github.com/PunithVT/ai-avatar-system
cd ai-avatar-system
cp .env.example .env  # add ANTHROPIC_API_KEY or OPENAI_API_KEY
docker compose up     # CPU mode
# OR for GPU:
docker compose -f docker-compose.gpu.yml up
```

First run downloads MuseTalk V1.5 weights (~2GB) and Whisper model automatically.

---

## Use Cases

- Custom AI personas with a specific voice and face (e.g., video FAQ bots, virtual presenters)
- Voice-cloned digital twins for demos or content
- Multilingual conversational avatars (18 languages via Whisper + XTTS v2)
- Local-first private avatar conversations (no cloud required in CPU mode)
