---
title: SkillsGate — Visual Skill Manager for AI Agents
added: 2026-08-01
category: tools
url: https://github.com/skillsgate/skillsgate
---

# SkillsGate

Desktop app + terminal UI for browsing, installing, and managing AI agent
skills across 20+ agent tools from one interface. Flagged by Kevin via
[@tom_doerr tweet](https://x.com/tom_doerr/status/2083261094559105431), Jul 31 2026.

**Stars:** 843 | **License:** MIT | **Created:** 2026-02-10 | **Lang:** TypeScript

## What it does

- Browses the public [skills.sh](https://skills.sh) catalog and installs
  skills to any combination of supported agents with one click/keystroke.
- Per-agent install/remove — add a skill to one agent without touching others.
- Built-in editor (CodeMirror) to view/edit raw skill source, saved to disk.
- Remote servers: connect over SSH to browse/sync skills on other machines.
- Private skills (local-only) vs. shared/team skills.
- Two front ends sharing one SQLite prefs store: Electron desktop app, and
  `npx skillsgate` TUI (keyboard-driven: `1-4` tabs, `j/k` nav, `/` search).

**Supported agents:** Claude Code, Cursor, Windsurf, GitHub Copilot, Cline,
Continue, Codex CLI, Droid CLI, OB-1, Amp, Goose, Junie, Kilo Code, OpenCode,
OpenClaw, Pear AI, Roo Code, Trae, Zed, Universal.

## Relevance to George's stack

Same underlying ecosystem George already uses: skill installs here go through
`npx skills add <name>@<publisher>` (see e.g. the here.now skill install in
`.local-fragments/task-registry.md`), which is the `skills.sh` CLI —
SkillsGate is a visual/TUI wrapper over that same catalog and install
mechanism, not a new one.

- **Low fit for George specifically** — George runs headless (Telegram-driven,
  no interactive terminal session with Kevin), so neither the desktop app nor
  the keyboard-driven TUI has anywhere to run *for* George. Skill installs
  here already happen via scripted `npx skills add` calls.
- **Possible fit for Kevin directly** — if Kevin manages skills across his own
  local Claude Code / Cursor / other agent installs, the TUI (`npx skillsgate`)
  or desktop app could be a faster way to browse skills.sh and push installs
  to multiple agents at once, vs. hand-copying markdown files per repo.
- Not trading-relevant; general dev-tooling note only.

**Verdict:** interesting but not actionable for George's own operation. Noted
in case Kevin wants a visual skill manager for his personal agent setups.
