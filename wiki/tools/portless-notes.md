---
title: Portless (vercel-labs/portless)
added: 2026-06-29
category: developer-tools / local-tunneling
url: https://github.com/vercel-labs/portless
article: https://ai.sulat.com/how-portless-gives-every-local-app-a-stable-url-31f1be374ab8
---

# Portless

**What it is:** Replaces localhost port numbers with stable, human-readable `.localhost` URLs for local development. Designed for both humans and AI agents (Vercel Labs).

**Key features:**
- Each local app gets a named `.localhost` URL instead of `localhost:3000`, `localhost:8080`, etc.
- `--ngrok` flag: exposes any portless app publicly via ngrok
- `--tailscale` flag: shares over Tailscale network (root-mounted on HTTPS ports 443/8443/…)
- `--funnel` flag: public internet exposure via Tailscale Funnel

**Relevance to George:**
- Useful for exposing webhook endpoints during local development of agent integrations
- Could replace ad-hoc `ngrok` usage when testing NanoClaw webhooks or MCP servers locally
- "For humans and agents" framing — likely designed to work well with AI agents making HTTP calls

**Install:** See GitHub repo (vercel-labs/portless)

**Noted:** Kevin flagged 2026-06-29 via sulat.com writeup.
