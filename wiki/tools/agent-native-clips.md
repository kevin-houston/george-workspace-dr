---
title: Agent-Native Clips
created: 2026-06-22
updated: 2026-06-22
category: tools
source: https://clips.agent-native.com/
framework_github: https://github.com/BuilderIO/agent-native
framework_stars: 1689
author: Builder.io
status: sign-in gated web app (free tier available)
---

# Agent-Native Clips

Web app that transcribes, summarizes, and searches everything you record. Built on the Agent-Native framework by Builder.io.

> "Your AI agent transcribes, summarizes, and searches everything you record alongside you."

Access: https://clips.agent-native.com/ (requires account)

---

## What It Is

An AI-native meeting / recording companion:
- **Transcription** — converts audio recordings to text
- **Summarization** — AI agent produces structured summaries
- **Search** — full-text and semantic search across all your recorded sessions

Positioned as an alternative to tools like Otter.ai or Fireflies, but built agent-natively — the AI agent and the UI share the same underlying state, so the agent can act on recordings rather than just reading them.

---

## The Underlying Framework: Agent-Native

Clips is an example app built on **agent-native** (github.com/BuilderIO/agent-native, 1.7k stars, TypeScript). The framework's core idea:

> AI agents and UI share the same database and state. One action powers the agent, UI, HTTP, MCP, A2A, and CLI simultaneously.

```typescript
// One action definition serves all surfaces:
export default defineAction({
  description: "Say hello from the local app-agent loop.",
  schema: z.object({ name: z.string().default("world") }),
  http: { method: "GET" },
  readOnly: true,
  run: async ({ name }) => { ... }
})
```

**Primitives:** shared actions, SQL-backed state, identity, tools, skills, jobs, observability, UI surfaces.

**Philosophy:** Start with a chat-first or headless agent, then add UI, scheduled jobs, and collaboration as the product grows — rather than bolting an AI layer onto an existing app.

### Quick start
```bash
npx @agent-native/core@latest create my-chat-app --template chat
```

Bring your own: database, hosting, model stack, and app code.

---

## Relevance

- **Clips itself:** Useful if Kevin wants automatic transcription + search across recorded meetings, calls, or research sessions without manual tooling.
- **Framework pattern:** The "one action → agent + UI + HTTP + MCP + A2A + CLI" pattern is architecturally interesting for George — it's how a production agentic app might be structured to serve both automated agent workflows and a human-facing UI from the same codebase.
- **Comparison to NanoClaw:** Agent-Native is a self-hosted OSS alternative path. NanoClaw/George is the hosted equivalent with more communication channels; Agent-Native gives you the framework to build something similar locally.
- **MCP support:** Framework has native MCP integration, meaning agent-native apps can expose tools to Claude Code.

## Cross-References

- [hermes-gpt](hermes-gpt.md) — similar local-first "model + local tool stack" pattern
- [OpenAlice](openalice.md) — another agent-native trading-focused framework with MCP + broker integrations
