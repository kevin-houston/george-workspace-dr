# Task Registry

Living reference for all recurring tasks. Each section: trigger → success criteria → gotchas.

**Maintenance protocol:** When a task fails and you fix it, append the failure + fix to the relevant gotchas block before the session ends. This file compounds — every failure makes future runs more reliable. Commit changes to this file with the fix commit.

---

## Lithuanian Daily Phrase

**Trigger:** Scheduled daily (morning).
**Run:** `python3 /workspace/agent/lithuanian_daily.py`
**Success:** Audio file non-empty → `send_file(path, text=message_field, to="telegram-mg-17769")`.

**Gotchas:**
- `edge-tts` is wiped between container restarts. Always prepend install: `python3.11 -m pip install edge-tts --break-system-packages -q 2>/dev/null || true`
- Script outputs JSON — use the `message` field as the `text=` arg to `send_file`, not a hand-written caption.

---

## Daily AI Podcast — Script Generation

**Trigger:** 6 AM CT daily.
**Output:** `/workspace/agent/podcasts/ai_podcast_YYYY-MM-DD.md`
**Success:** File exists, word count 1,800–2,400, 4 segments, hosts Alex/Jordan.

**Gotchas:**
- Do NOT message Kevin on completion. The 6:10 AM audio task picks up the script automatically.
- Verify all claims with 2 independent sources. Single-source claims get "reports suggest / according to X."
- Filename date must match today (`date +%Y-%m-%d`). A mismatch causes the audio task to fail silently.
- Newsworthiness check: articles more than 3 days old do not count as "breaking." Drop or clearly date them.
- **Always get the day of the week from the shell** (`date +%A`) — never rely on the LLM to calculate it. Kevin noticed June 5 was written as "Thursday" when it was Friday. Run `date +"%A, %B %d, %Y"` at script-writing time and hardcode the result.

---

## Daily AI Podcast — Audio Generation & Email

**Trigger:** 6:10 AM CT daily.
**Run:** `PATH="/home/node/.local/bin:/usr/bin:$PATH" /usr/bin/python3.11 /workspace/agent/generate_and_email_podcast.py`
**Success:** Output contains `✅ Email sent to kevinclaw26@gmail.com`. Do NOT message Kevin on success.

**Gotchas:**
- `ffmpeg` is NOT installed and never will be. Python MP3 concat fallback is built into the script. The `⚠️ ffmpeg not available` warning is expected — not a failure.
- Must install `edge-tts` first: `python3.11 -m pip install edge-tts --break-system-packages -q`.
- Use `/usr/bin/python3.11` explicitly — bare `python3` may resolve to a different version without `edge-tts`.
- Email auth flows through OneCLI proxy. If 401/403, run `/onecli-gateway` — do not ask Kevin for credentials.
- Script finds today's markdown by date pattern. If the 6 AM script task ran late and the file was just written, give it a moment then retry.

---

## PEAD Overnight Pass

**Trigger:** ~11 PM CT nightly.
**Run:** `python3 /workspace/agent/backtesting/paper_trading/pead_overnight.py`
**Output:** `backtesting/paper_trading/pead_watchlist.json`
**Success:** Log ends with "Overnight pass complete." Watchlist written (empty is valid — no earnings tonight).

**Gotchas:**
- EDGAR requires `User-Agent` header with identity (real email). Fixed in commit `0a1d0f5`. If "User-Agent identity is not set" appears, the env var `EDGAR_USER_AGENT` is missing — check `.env` or set it inline.
- FinBERT model (`ProsusAI/finbert`) is ~400MB. First run on a fresh container downloads it — allow up to 5 min. Subsequent runs use cache.
- "No earnings tonight. Watchlist cleared." is normal — not an error. The strategy requires earnings + a qualifying 8-K.
- Entry thresholds are `score ≥ 0.18 AND surprise ≥ 0.02` (from H174 confirmation). Do NOT lower these to generate more candidates.

---

## PEAD Intraday Scanner

**Trigger:** Every 30 min, 6 AM–5:30 PM CT, weekdays (pre-task gated).
**Pre-task:** `node --input-type=module < backtesting/paper_trading/pead_intraday_check.mjs`
**Run:** `PEAD_INTRADAY_TICKERS='[...]' python3 backtesting/paper_trading/pead_intraday.py`
**Success:** Orders submitted, or log confirms filtered out. Only message Kevin if orders placed.

**Gotchas:**
- Pre-task polls EDGAR ATOM feed; resets cursor daily at midnight. Cursor: `pead_intraday_cursor.json`.
- No gap check (intraday entries). Instead requires stock up > 0% on the day.
- Entry thresholds same as overnight: score ≥ 0.18 AND surprise ≥ 0.02.
- Positions written to the shared `pead_positions.json` so `pead_exits.py` handles them automatically.
- FinBERT loads fresh each wakeup (~90s first time, cached after). Not a failure.
- On non-earnings days the ATOM feed has no universe tickers → `wakeAgent: false` → no credits used.

---

## PEAD Open Pass

**Trigger:** 9:32 AM CT on weekdays (market open + 2min).
**Run:** `python3 /workspace/agent/backtesting/paper_trading/pead_open.py`
**Success:** Orders submitted for watchlist candidates, or log confirms watchlist was empty.

**Gotchas:**
- Check `pead_watchlist.json` first. If empty (`[]`), the open pass is a no-op — that's correct behavior.
- Alpaca credentials flow through OneCLI proxy. Auth failures → `/onecli-gateway`.
- Paper account base URL is `https://paper-api.alpaca.markets` — do NOT use live endpoint.

---

## PEAD Exits Pass

**Trigger:** 2:46 PM CT on weekdays.
**Run:** `python3 /workspace/agent/backtesting/paper_trading/pead_exits.py`
**Success:** Log confirms positions checked; any 20-day-old positions closed.

**Gotchas:**
- "No positions to close" is valid. The strategy is intentionally patient — 20 trading days is ~4 calendar weeks.
- Hold period is 20 *trading* days from entry, not calendar days. Script calculates correctly — don't override.

---

## Here.now Dashboard Publishing

**Trigger:** Manual, or daily refresh (anonymous sites expire 24h).
**Skill:** `heredotnow/skill@here-now`

**Gotchas:**
- `jq` is NOT installed system-wide. `/tmp` is wiped on restart. Before every publish:
  ```bash
  curl -fsSL https://github.com/jqlang/jq/releases/download/jq-1.7.1/jq-linux-amd64 -o /tmp/jq && chmod +x /tmp/jq
  ```
- `file` command is NOT installed. Create stub at `/tmp/file` (one-liner):
  ```bash
  printf '#!/usr/bin/env node\nconst e=require("path").extname(process.argv[process.argv.length-1]).toLowerCase();const m={".html":"text/html",".css":"text/css",".js":"application/javascript",".json":"application/json",".png":"image/png",".jpg":"image/jpeg",".mp3":"audio/mpeg"};console.log(m[e]||"application/octet-stream");' > /tmp/file && chmod +x /tmp/file
  ```
- Run all publish commands with `PATH="/tmp:$PATH"` prefix.
- Pass directory path WITHOUT trailing slash: `publish.sh /workspace/agent/dashboard` ✓ — `dashboard/` ✗
- Skill install: `npx skills add heredotnow/skill@here-now -y -g` (not bare `here-now` — that name doesn't resolve).
- To update an anonymous site you need the original `claimToken`. Once cleared from `.herenow/state.json`, that slug cannot be updated — publish as a new site.
- Without `HERENOW_API_KEY`, every publish gets a new slug and expires in 24h. Kevin claims by visiting the `claimUrl` in a browser, or add key to OneCLI vault for permanent auto-update.

---

## Nightly Git Backup

**Trigger:** Scheduled ~7 AM CT daily.
**Success:** `git push origin main` confirms remote updated.

**Gotchas:**
- `GITHUB_TOKEN` is injected by OneCLI proxy — BUT `git push origin main` fails with "invalid credentials" because the proxy intercepts and strips git auth. **Workaround:** `NO_PROXY=github.com no_proxy=github.com GIT_SSL_CAINFO=/tmp/onecli-combined-ca.pem git push https://x-access-token:${GITHUB_TOKEN}@github.com/kevin-houston/george-workspace-dr.git main` — bypasses proxy for github.com while keeping CA bundle for other HTTPS.
- If push fails "remote rejected," another session may have pushed — `git pull --rebase` first.
- Avoid `git add -A` if there are large temp files in workspace root. Prefer explicit paths or a curated `.gitignore`.
- `/tmp/onecli-combined-ca.pem` is the combined CA bundle (system + OneCLI MITM cert). It's refreshed by OneCLI on start — use this for any git push that needs the CA.

---

## Dream Cycle Scan (Nightly Research)

**Trigger:** Spawned ~11 PM CT as background `Agent` tool call.
**Output:** `dream_cycle/staged/YYYY-MM-DD/*.json` + scan summary JSON.
**Success:** Both a "wiki expansion" commit and a "dream cycle scan" commit appear in `git log`.

**Gotchas:**
- Never spawn a duplicate. Check the system-reminder for a running agent ID before launching. Duplicate scans waste tokens and create conflicting staged files.
- Staged files should have `apply_status: "pending"`. If the build phase already ran before the scan completed, the proposals will need manual application.
- The wiki expansion target is the *thinnest* section (fewest pages, least cross-linking) — check `wiki/index.md` page counts, not just topic coverage.

---

## Dream Cycle Build Phase

**Trigger:** 4 AM CT daily (scheduled task from nanoclaw).
**Input:** `dream_cycle/staged/YYYY-MM-DD/*.json`
**Output:** Stub files, hypothesis-log entries, changelog at `dream_cycle/changelogs/YYYY-MM-DD.md`.
**Success:** All pending proposals marked "applied" or "flagged." Changelog committed. Kevin messaged ONLY if high-risk items flagged.

**Gotchas:**
- If proposals were already applied before this task runs (e.g., applied inline when scan completed), still write the changelog — it may not exist yet.
- medium-risk = new script: copy target to `.bak` first. For NEW files (no existing target), skip the backup.
- Changelog commit: `"dream cycle: changelog YYYY-MM-DD"`. Proposal commit: `"dream cycle: apply YYYY-MM-DD staged proposals (H###, H###)"`.
- Do NOT message Kevin for routine low/medium runs. Only flag high-risk items.
- **After committing**, run the session summary script and text Kevin the URL (see Nightly Session Summary below).

---

## Nightly Session Summary

**Trigger:** End of Dream Cycle Build Phase (4 AM CT).
**Run:** `python3 /workspace/agent/generate_session_summary.py YYYY-MM-DD`
**Output:** `summaries/session-summary-YYYY-MM-DD.html` published to here.now.
**Success:** Script prints a here.now URL. Text Kevin: "Session summary: <URL>"

**Gotchas:**
- Script auto-installs `/tmp/jq`, `/tmp/file` stub, and `heredotnow/skill@here-now` if missing.
- Pass the explicit date (`date +%Y-%m-%d`) — do not rely on the default (script may run at 4 AM on the next calendar day if the build phase spans midnight).
- Script publishes the `summaries/` directory. Only one HTML file per date goes there — do NOT put other files in `summaries/`.
- here.now anonymous sites expire in 24h. Kevin can claim via the URL in `.herenow/state.json` for permanent hosting.

---

## Paper Trading Reset (reset_paper_accounts.py)

**Trigger:** Manual, when restarting paper trading from scratch.
**Run:** `python3 backtesting/paper_trading/reset_paper_accounts.py` (use `--dry-run` first)
**Success:** All 6 strategy virtual accounts at $5,000. Alpaca positions closed. Legacy logs archived.

**Gotchas:**
- OneCLI proxy credential sessions can time out mid-run when closing many positions sequentially. The first few closes succeed, then `credential_not_found` errors appear for the rest.
- If proxy times out: the **virtual accounts** (strategy_accounts.json) are the critical part and reset atomically at the end. Alpaca position cleanup is secondary — retry next trading day.
- Market must be open to close Alpaca positions. If run after hours, `close_position()` will fail anyway. Plan reset for trading hours.
- Residual Alpaca positions from old strategies don't affect new per-strategy $5k virtual tracking. New strategies size from `se.current_equity()`, not Alpaca account total.
- After a partial close: re-run without `--dry-run` — it's safe to re-run; it only closes still-open positions.

---

## H112 Monthly Rebalancer (h112_monthly.py)

**Trigger:** First trading day of each month (or `--force` to override).
**Run:** `NO_PROXY=paper-api.alpaca.markets,api.alpaca.markets no_proxy=paper-api.alpaca.markets,api.alpaca.markets source /workspace/agent/venv/bin/activate && python3 backtesting/paper_trading/h112_monthly.py`
**Success:** "✓ Logged N trades" printed. BUY order submitted to Alpaca.

**Gotchas:**
- **Alpaca proxy**: `credential_not_found` error for `paper-api.alpaca.markets` means OneCLI proxy is intercepting Alpaca traffic and stripping credentials. Fix: `NO_PROXY=paper-api.alpaca.markets,api.alpaca.markets` to bypass proxy — the Alpaca SDK sends its own API key headers directly.
- **urllib3 may be missing** in the venv: `pip install urllib3 -q` first if `ModuleNotFoundError: No module named 'urllib3'`.
- **Position isolation bug (fixed 2026-06-19)**: earlier version used `get_positions(client)` (ALL Alpaca positions) as current holdings. This caused SELL orders for IBS/H041a positions sharing the same paper account. Fixed: now uses `se.get_open_positions(STRATEGY_ID)` — only H026-tracked positions.
- **Stale SELL orders**: if a buggy run submitted SELL orders, cancel ALL pending orders via `c.cancel_orders()` before resubmitting. Check with `c.get_orders()` first.
- Market holidays: DAY orders submit fine but queue for next market open. Strategy engine records them immediately.
- Dry-run first on any doubt: add `--dry-run` flag.

---

## Wiki Index Maintenance

**Trigger:** On every wiki edit.
**File:** `wiki/index.md`

**Gotchas:**
- The index uses NO leading spaces before `- [` list items in most sections. Always `grep -n` the surrounding lines before `Edit` to confirm exact indentation — the Edit tool will fail on whitespace mismatch.
- Bump the `updated:` frontmatter date on every edit.
- New pages need: `added:` date, `category:`, `url:` (if applicable) in frontmatter.
