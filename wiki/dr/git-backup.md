---
updated: 2026-04-24
status: COMPLETE
---

# Git Backup Setup

## Goal

Push `/workspace/agent/` to `https://github.com/kevin-houston/george-workspace-dr` nightly (or after significant sessions) so workspace survives container resets.

## Current state

- Local git repo initialized at `/workspace/agent/` ✓
- Initial commit made ✓
- Remote set to `https://github.com/kevin-houston/george-workspace-dr.git` ✓
- GitHub repo created on remote ✓
- Credential helper configured (reads `$GITHUB_TOKEN` env var) ✓
- Nightly push scheduled at 2am Chicago time ✓

## Credential mechanism

`GITHUB_TOKEN` env var is injected by OneCLI into the container. Git credential helper reads it:
```
credential.helper = !f() { echo "username=kevin-houston"; echo "password=$GITHUB_TOKEN"; }; f
```

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
