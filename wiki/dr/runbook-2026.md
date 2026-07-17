---
updated: 2026-07-16
status: CURRENT
---

# George Agent — Operational Runbook 2026

Comprehensive operational runbook for restoring, validating, and re-activating George after a container reset, full system loss, or major configuration change. Updated to reflect the full 2026 operational state.

This document covers everything [DR Overview](overview.md) doesn't: specific commands, validation checks, timing sequences, and what "working" looks like for each subsystem.

---

## Section 1: What Has Changed Since Setup (April 2026)

The [DR Overview](overview.md) and [Git Backup](git-backup.md) pages were written in April 2026 when the project was just starting. Since then, the system has grown significantly. A fresh George reading only those pages would miss:

| Capability | Status | Notes |
|-----------|--------|-------|
| Git DR backup | LIVE | Nightly 7 AM CT push; `NO_PROXY` required |
| Alpaca paper trading | LIVE | ~$102k portfolio, ~$204k buying power |
| H174 PEAD overnight | LIVE | pead_overnight.py, 11 PM CT nightly |
| PEAD-GAP overnight | LIVE | pead_gap_overnight.py, 11 PM CT nightly |
| PEAD intraday scanner | LIVE | 30-min intervals 6 AM–5:30 PM CT weekdays |
| PEAD open pass | LIVE | 9:32 AM CT weekdays |
| PEAD exits | LIVE | 2:46 PM CT weekdays |
| PEAD-GAP open/exits | LIVE | 9:32 AM and 2:46 PM CT weekdays |
| H112 monthly rebalancer | LIVE | First trading day of each month |
| Daily AI podcast | LIVE | 6 AM (script) + 6:10 AM (audio + email) CT daily |
| Lithuanian phrase | LIVE | Daily morning, edge-tts audio to Telegram |
| Dream cycle scan | LIVE | ~11 PM CT nightly (background Agent tool) |
| Dream cycle build | LIVE | 4 AM CT daily scheduled task |
| Nightly session summary | LIVE | After dream cycle build; here.now URL to Kevin |
| Wiki knowledge base | LIVE | 209 pages as of 2026-07-16 |
| QuantMind, Hyper-Extract | AVAILABLE | pip installable; not in venv permanently |
| Vibe-Trading MCP | LIVE | 22 tools via `mcp__vibe-trading__*` |
| Kraken CLI | INSTALLED | `/home/node/.cargo/bin/kraken`; MCP server pending |

---

## Section 2: Restore Sequence (Full Loss)

Use this if the container workspace is completely gone and you're starting from scratch.

### Step 1: Re-clone the DR backup

```bash
git clone https://github.com/kevin-houston/george-workspace-dr.git /workspace/agent
```

This restores: wiki, memory, instructions, source files, backtesting code, paper trading scripts.

**Does NOT restore**: Python venv (must rebuild), node_modules (auto-rebuilt on first use), installed system packages like edge-tts (reinstall as needed), Alpaca open positions (tracked in strategy_accounts.json but Alpaca shows actuals).

### Step 2: Rebuild the Python venv

```bash
python3.11 -m venv /workspace/agent/venv
source /workspace/agent/venv/bin/activate
pip install numpy pandas requests torch transformers alpaca-py yfinance scikit-learn lightgbm
```

Note: full requirements are not pinned in a requirements.txt. The above installs the core packages. Additional ones (like `edge-tts`) are installed on-demand with `--break-system-packages`.

### Step 3: Verify git credentials

```bash
# Test that GITHUB_TOKEN is available
echo $GITHUB_TOKEN | cut -c1-4  # Should show 'ghp_' or 'github_pat_'

# Test that NO_PROXY push works (the correct push method)
NO_PROXY=github.com no_proxy=github.com GIT_SSL_CAINFO=/tmp/onecli-combined-ca.pem \
  git -C /workspace/agent push --dry-run \
  https://x-access-token:${GITHUB_TOKEN}@github.com/kevin-houston/george-workspace-dr.git main
```

If this fails, run `/onecli-gateway` to diagnose credential injection.

### Step 4: Verify Alpaca connectivity

```bash
source /workspace/agent/venv/bin/activate
python3 -c "
import os
from alpaca.trading.client import TradingClient
c = TradingClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET'], paper=True)
acct = c.get_account()
print(f'Portfolio value: \${float(acct.portfolio_value):,.2f}')
print(f'Buying power: \${float(acct.buying_power):,.2f}')
"
```

Expected: portfolio value ~$100-110k, buying power ~$200-220k (2× leverage via margin). If `credential_not_found`, use `NO_PROXY=paper-api.alpaca.markets,api.alpaca.markets`.

### Step 5: Check scheduled tasks

```bash
ncl tasks list
```

Verify these tasks exist and are ACTIVE:
- `pead-overnight-*` — 11 PM CT nightly
- `pead-gap-overnight-*` — 11 PM CT nightly
- `pead-intraday-*` — 30-min weekday intervals
- `pead-open-*` — 9:32 AM CT weekdays
- `pead-exits-*` — 2:46 PM CT weekdays
- `pead-gap-open-*` — 9:32 AM CT weekdays
- `pead-gap-exits-*` — 2:46 PM CT weekdays
- `h112-monthly-*` — first trading day each month
- `podcast-script-*` — 6 AM CT daily
- `podcast-audio-*` — 6:10 AM CT daily
- `lithuanian-*` — morning daily
- `dream-cycle-*` — ~11 PM CT nightly
- `dream-build-*` — 4 AM CT daily
- `git-backup-*` — ~7 AM CT daily

If any are missing, check `ncl tasks list --all` to see paused/cancelled ones. Re-create if needed.

### Step 6: Reconcile open positions

```bash
source /workspace/agent/venv/bin/activate
python3 -c "
import json
from pathlib import Path

# Check what strategy files think we hold
for f in ['pead_positions.json', 'pead_gap_positions.json']:
    p = Path(f'/workspace/agent/backtesting/paper_trading/{f}')
    if p.exists():
        data = json.loads(p.read_text())
        print(f'{f}: {len(data)} positions')
        for sym, info in list(data.items())[:3]:
            print(f'  {sym}: entry {info.get(\"entry_date\",\"?\")}, qty {info.get(\"qty\",\"?\")}')
"
```

Then verify in Alpaca that these positions actually exist. If there's a mismatch (strategy file says we hold X but Alpaca doesn't), the position was likely closed manually or by error. Remove from strategy JSON to prevent orphan exit logic.

---

## Section 3: Common Operational Failures and Fixes

### PEAD Overnight: FinBERT download on first run

**Symptom**: pead_overnight.py hangs for 5+ minutes then succeeds, OR fails with `ConnectionError` on `from transformers import pipeline`.

**Fix**: First run downloads `ProsusAI/finbert` (~400MB). Allow 5 minutes. If it fails with SSL, run:
```bash
SSL_CERT_FILE=/tmp/onecli-combined-ca.pem \
REQUESTS_CA_BUNDLE=/tmp/onecli-combined-ca.pem \
source /workspace/agent/venv/bin/activate && python3 /workspace/agent/backtesting/paper_trading/pead_overnight.py
```

### Alpaca: credential_not_found when placing orders

**Symptom**: `{"code": 40110000, "message": "credential not found for: paper-api.alpaca.markets"}` or similar.

**Fix**: OneCLI proxy is intercepting Alpaca API calls and stripping the authorization headers it doesn't recognize. Bypass the proxy for Alpaca endpoints:
```bash
NO_PROXY=paper-api.alpaca.markets,api.alpaca.markets \
no_proxy=paper-api.alpaca.markets,api.alpaca.markets \
source /workspace/agent/venv/bin/activate && python3 [script].py
```

This is already baked into the task definitions for H112 and PEAD-GAP. If running PEAD overnight/exits manually, add these env vars.

### GitHub push fails: authentication error

**Symptom**: `remote: Repository not found` or `fatal: Authentication failed`.

**Fix**: Use the full NO_PROXY form:
```bash
NO_PROXY=github.com no_proxy=github.com \
GIT_SSL_CAINFO=/tmp/onecli-combined-ca.pem \
git push https://x-access-token:${GITHUB_TOKEN}@github.com/kevin-houston/george-workspace-dr.git main
```

**Do NOT** use: `git push origin main` — the credential helper form fails when OneCLI proxy is active.

### Git push fails: non-fast-forward

**Symptom**: `error: failed to push some refs` / `Updates were rejected because the remote contains work`.

**Fix**: Another session pushed while this one was running. Pull and rebase:
```bash
NO_PROXY=github.com no_proxy=github.com GIT_SSL_CAINFO=/tmp/onecli-combined-ca.pem \
git pull --rebase https://x-access-token:${GITHUB_TOKEN}@github.com/kevin-houston/george-workspace-dr.git main
# Then push again
```

### edge-tts not found (podcast audio / Lithuanian phrase)

**Symptom**: `ModuleNotFoundError: No module named 'edge_tts'`

**Fix**: Reinstall with the correct CA bundle:
```bash
SSL_CERT_FILE=/tmp/onecli-combined-ca.pem \
REQUESTS_CA_BUNDLE=/tmp/onecli-combined-ca.pem \
/usr/bin/python3.11 -m pip install edge-tts --break-system-packages -q
```

Then re-run the script with the same SSL env vars.

### Dream cycle: duplicate scan running

**Symptom**: Two `Agent` tool calls visible in the session with dream cycle IDs.

**Fix**: Do NOT launch a new scan. The second run will create conflicting staged proposals. Wait for the first to complete, then launch a new one for the next day if needed.

### Strategy accounts JSON out of sync

**Symptom**: `strategy_accounts.json` shows balance that doesn't match expected after several months of paper trading.

**Validation**: Cross-check with Alpaca account:
```bash
source /workspace/agent/venv/bin/activate
python3 -c "
import json, os
from alpaca.trading.client import TradingClient
from pathlib import Path

c = TradingClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET'], paper=True)
acct = c.get_account()
print(f'Alpaca total: \${float(acct.portfolio_value):,.2f}')

sa = json.loads(Path('/workspace/agent/backtesting/paper_trading/strategy_accounts.json').read_text())
total_virtual = sum(v.get('current_equity', 5000) for v in sa.values())
print(f'Virtual total: \${total_virtual:,.2f}')
print('Note: virtual tracks per-strategy P&L, not Alpaca account directly')
"
```

The virtual accounts track per-strategy allocation; Alpaca holds the actual shares. They're not expected to be exactly equal.

---

## Section 4: Paper Trading Validation Checks

Run these after any gap in monitoring to verify the paper trading pipeline is healthy.

### Check open positions

```bash
source /workspace/agent/venv/bin/activate
python3 -c "
import os
from alpaca.trading.client import TradingClient
c = TradingClient(os.environ['ALPACA_API_KEY'], os.environ['ALPACA_SECRET'], paper=True)
positions = c.get_all_positions()
print(f'Open positions: {len(positions)}')
for p in positions:
    print(f'  {p.symbol}: {p.qty} shares, P&L \${float(p.unrealized_pl):,.2f}')
"
```

### Check last PEAD log

```bash
tail -20 /workspace/agent/backtesting/paper_trading/pead_open.log
tail -20 /workspace/agent/backtesting/paper_trading/pead_exits.log
tail -20 /workspace/agent/backtesting/paper_trading/pead_gap_open.log
tail -20 /workspace/agent/backtesting/paper_trading/pead_gap_exits.log
```

### Check watchlists

```bash
python3 -c "
import json
from pathlib import Path
for f in ['pead_watchlist.json', 'pead_gap_watchlist.json']:
    p = Path(f'/workspace/agent/backtesting/paper_trading/{f}')
    if p.exists():
        data = json.loads(p.read_text())
        print(f'{f}: {len(data)} tickers waiting')
"
```

---

## Section 5: Wiki Health Indicators

The wiki is the primary knowledge layer. Signs of degradation:

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `wiki/index.md` `updated:` date >7 days old | Dream cycle build failing | Check task log; rerun build manually |
| New hypothesis in CLAUDE.local.md not in hypothesis-log.md | Build phase skipped | Run dream cycle build for that date |
| Wiki pages with links to non-existent paths | Page deleted without updating index | Run `/wiki lint` |
| `wiki/log.md` last entry >3 days old | Wiki not being updated | Check if any wiki changes happened; update log |

Current page count as of 2026-07-16: **209 pages** across 6 sections.

---

## Section 6: What to Tell a Fresh George (Current Version)

Use this instead of the outdated text in [DR Overview](overview.md):

> You are George, a NanoClaw agent for Kevin Houston. Your workspace was recently restored from the GitHub DR backup at `kevin-houston/george-workspace-dr`. Read these files in order to reconstruct full context:
>
> 1. `/workspace/agent/CLAUDE.local.md` — your full standing instructions, trading project state, and system overview
> 2. `/workspace/agent/wiki/index.md` — the knowledge base catalog (209 pages as of July 2026)
> 3. `/workspace/agent/wiki/dr/runbook-2026.md` — this file (operational state and validation)
>
> Active paper trading strategies:
> - H174 PEAD (FinBERT 8-K, OPG entries, 20-day holds)
> - PEAD-GAP (gap-up at open filter, same hold)
> - H026 monthly ETF rotation (H112 rebalancer)
>
> The production portfolio target is H041a 22% / H026 27% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%, OOS Sharpe 4.158.
>
> Run `ncl tasks list` to see all scheduled tasks. Run `tail -5 wiki/log.md` to see the latest wiki activity.

---

## Related Pages

- [DR Overview](overview.md) — high-level restore procedure (needs update for 2026 state)
- [Git Backup Setup](git-backup.md) — git credential mechanism
- [Session Diary](diary.md) — narrative history of sessions
- [Task Registry](../../.local-fragments/task-registry.md) — per-task gotchas and failure fixes
- [Paper Trading Index](../trading/paper-trading/index.md) — active strategies and positions
- [Risk Controls and Monitoring](../trading/paper-trading/risk-controls-and-monitoring.md) — circuit breakers and kill switches
