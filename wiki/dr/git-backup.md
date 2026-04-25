---
updated: 2026-04-24
status: IN PROGRESS — blocked on GitHub auth
---

# Git Backup Setup

## Goal

Push `/workspace/agent/` to `https://github.com/kevin-houston/george-workspace-dr` nightly (or after significant sessions) so workspace survives container resets.

## Current state

- Local git repo initialized at `/workspace/agent/` ✓
- Initial commit made ✓
- Remote set to `https://github.com/kevin-houston/george-workspace-dr.git` ✓
- GitHub repo created on remote: **NOT YET** — blocked on auth
- Nightly push scheduled: **NOT YET**

## Blocked: credential access

Kevin added a GitHub Personal Access Token to the OneCLI vault (`github.com`). However, the vault proxy uses CONNECT tunnels for HTTPS — it cannot inject the token as an HTTP header into encrypted git traffic. The token is not surfacing as an env var either.

**Outstanding question:** How does the OneCLI vault surface the GitHub token to the container? Options to explore:
- Env var injection (not yet visible)
- A credential helper API endpoint
- Kevin sharing the token directly for one-time git credential store seeding

## Setup steps (once auth is resolved)

```bash
# 1. Create the GitHub repo
curl -s -X POST https://api.github.com/user/repos \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"george-workspace-dr","description":"Disaster recovery backup of George agent workspace","private":false}'

# 2. Push
git push -u origin main

# 3. Schedule nightly push via NanoClaw schedule_task
```

## .gitignore (already in place)

```
container.json        # runtime config, not worth backing up
sources/*.pdf         # large binaries
sources/*.html
sources/*.mp4
sources/*.mp3
```
