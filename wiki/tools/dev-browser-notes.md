---
title: dev-browser — Sandboxed Browser Automation for AI Agents
added: 2026-08-05
category: tools
url: https://github.com/SawyerHood/dev-browser
---

# dev-browser

Browser automation tool built specifically for AI coding agents (Claude Code
and others), giving them the ability to drive a real browser through
sandboxed JavaScript. Shared by Kevin 2026-08-05 (via a newsletter link,
join.theaigent.xyz).

**Stars:** 6,507 | **License:** MIT | **Language:** TypeScript
**Created:** 2025-12-02 | **Last push:** 2026-08-05 (actively maintained)
**Author:** Sawyer Hood (`SawyerHood`), real GitHub account, established repo
history — not a burner/hallusquat.

## What it does

- Runs agent-authored scripts inside a **QuickJS WASM sandbox** — no host
  filesystem/process access from the script itself.
- Full **Playwright API** surface: navigation, clicking, form filling,
  screenshots, etc.
- Persistent page/session state across multiple script invocations (doesn't
  reset the browser between calls).
- Can attach to an already-running Chrome (`--connect`) or launch a fresh
  headless Chromium (`--headless`).
- Ships both pixel-level (computer-use style) and DOM-level interaction
  toolsets.
- Positioned as faster/cheaper than comparable agent-browser-automation tools
  per the README's own benchmarks (not independently verified here).

## Install / usage

```
npm install -g dev-browser
dev-browser --headless    # scripted/CI use
dev-browser --connect     # attach to a running Chrome
```
Scripts are piped as stdin. Also installable as a Claude Code skill via the
skill marketplace, with pre-approval settings available to skip
per-execution permission prompts.

## Legitimacy assessment

Confirmed via npm registry (`dev-browser`, latest `0.2.9`, author Sawyer Hood
with a real contact email) and GitHub API (6,507 stars, created Dec 2025,
pushed as recently as today — Aug 5, 2026). No hallusquatting signals: real
maintainer identity, consistent versioning, matches its own GitHub
description ("A Claude Skill to give your agent the ability to use a web
browser"). Per standing package-installation-security instructions, verified
on both npm and GitHub before this note — not yet installed.

## Relevance to George's Stack

Direct overlap with the existing **agent-browser** skill already in use here
(see `.claude/skills/agent-browser`) for the same job — driving a browser
for JS-rendered pages, screenshots, and form interaction (e.g. wiki source
ingestion for paywalled/JS-heavy pages, `here.now` publishing checks).
Sandboxing (QuickJS WASM) is the notable differentiator over the current
agent-browser CLI-command approach — worth a side-by-side eval if
agent-browser ever needs replacing, but no current pain point that demands
a switch. Logged for reference; no action taken.
