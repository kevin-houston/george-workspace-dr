---
updated: 2026-08-20
status: COMPLETE — running nightly for 4+ months, credential mechanism changed since original setup
---

# Git Backup Setup

## Goal

Push `/workspace/agent/` to `https://github.com/kevin-houston/george-workspace-dr` nightly (or after significant sessions) so workspace survives container resets.

## Current state (refreshed 2026-08-20 — was stale at the April 24 setup-day snapshot)

- Local git repo initialized at `/workspace/agent/` ✓
- Remote set to `https://github.com/kevin-houston/george-workspace-dr.git` (public repo) ✓
- Nightly push scheduled ~7 AM CT daily (task registry lists this as the current trigger time — note the original setup targeted 2am Chicago time; the schedule appears to have shifted since April, treat 7 AM CT as authoritative) ✓
- **Credential mechanism resolved and changed** — the April 24 "blocked on vault proxy doesn't surface the token for git HTTPS operations" issue from the diary is no longer the mechanism in use. See below.
- Confirmed working via ongoing history: this file itself is version 2 of a chain of `nightly backup` commits (e.g. `93f1be6 nightly backup 2026-08-20`, `dbe5284 nightly backup 2026-08-19`) plus daily `dream cycle` commits, all landing on `main` without manual intervention.

## Credential mechanism (current, supersedes April's plan)

`GITHUB_TOKEN` env var is injected by OneCLI. The original plan was a git `credential.helper` reading that var directly — **this does not work in practice**: plain `git push origin main` fails with "invalid credentials" because the OneCLI proxy intercepts and strips git auth before it reaches GitHub. The working fix bypasses the proxy for `github.com` explicitly and supplies the CA bundle for everything else:

```bash
NO_PROXY=github.com no_proxy=github.com \
GIT_SSL_CAINFO=/tmp/onecli-combined-ca.pem \
git push https://x-access-token:${GITHUB_TOKEN}@github.com/kevin-houston/george-workspace-dr.git main
```

`/tmp/onecli-combined-ca.pem` is the combined CA bundle (system + OneCLI MITM cert), refreshed by OneCLI on container start. If the push fails with "remote rejected," another concurrent session may have pushed already — `git pull --rebase` first before retrying. See `.local-fragments/task-registry.md` → "Nightly Git Backup" for the full gotchas list this section summarizes.

## Setup steps (historical — repo and credentials already exist, kept for full-rebuild scenario only)

```bash
# 1. Create the GitHub repo (already done — only needed if the remote repo itself is lost)
curl -s -X POST https://api.github.com/user/repos \
  -H "Authorization: token $GITHUB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"george-workspace-dr","description":"Disaster recovery backup of George agent workspace","private":false}'

# 2. Push (use the NO_PROXY form above, not a bare push)
# 3. Schedule nightly push via `ncl tasks create` (NanoClaw's current task CLI — `schedule_task` in the original note is the old tool name)
```

## .gitignore (already in place)

```
container.json        # runtime config, not worth backing up
sources/*.pdf         # large binaries
sources/*.html
sources/*.mp4
sources/*.mp3
```

## See Also

- [DR Overview](overview.md) — restore procedure and what survives a container reset
- [Operational Runbook 2026](runbook-2026.md) — current-state restore commands and common failure modes, including the same NO_PROXY/CA-bundle pattern applied to Alpaca order submission
- `.local-fragments/task-registry.md` → "Nightly Git Backup" — living gotchas list this page is derived from; check there first for any new failure mode before trusting this snapshot
