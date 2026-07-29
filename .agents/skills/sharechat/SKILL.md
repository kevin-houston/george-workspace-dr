---
name: sharechat
description: Share, upload, or publish the current chat, session, or conversation as an unlisted web link. Use when the user says "share this chat", "upload this session", "give me a link to this conversation", or similar.
---

# sharechat

Publish the current coding session as an unlisted, deletable link on sharechat.val.run — by uploading the transcript file that is already on disk. Do not retype the conversation; that wastes tokens and loses fidelity.

1. Find the transcript file for this session:
   - Claude Code: newest file in `~/.claude/projects/<slug>/` where `<slug>` is `$PWD` with every non-alphanumeric character replaced by `-`
     (`ls -t ~/.claude/projects/$(pwd | sed 's/[^a-zA-Z0-9]/-/g')/*.jsonl | head -1`)
   - Codex: newest rollout (`ls -t ~/.codex/sessions/*/*/*/rollout-*.jsonl | head -1`)
   - opencode: `opencode export <sessionID>` writes the transcript JSON to stdout

2. Upload it gzipped (gzip is required — code-heavy uncompressed bodies get rejected upstream):

   ```sh
   gzip -c "$FILE" | curl -fsS https://sharechat.val.run/api/chats/import \
     -H 'content-encoding: gzip' --data-binary @-
   ```

   Shortcut: if the `sharechat` CLI is installed, it does both steps — plain `sharechat` (Claude Code, newest session for cwd) or `sharechat codex`. Install it with `curl -fsSL https://sharechat.val.run/install | sh`.

3. Show the user BOTH links from the JSON response: `url` (the shareable link) and `deleteUrl` (one DELETE request takes it down).

Notes: the server auto-detects the format and drops thinking, system prompts, and injected context; tool calls are kept, trimmed. The link is a snapshot — messages after upload are never included; share again for an update. For a curated or partial share instead, fetch https://sharechat.val.run and use the JSON API it documents.
