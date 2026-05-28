---
created: 2026-05-28
updated: 2026-05-28
source: https://github.com/TraderAlice/OpenAlice
stars: 4426
---

# OpenAlice — AI Trading Agent (Full Lifecycle)

**Repo**: github.com/TraderAlice/OpenAlice  
**Language**: TypeScript  
**License**: see repo  
**Tagline**: "Your one-person Wall Street"

Full-lifecycle AI trading agent: research → position entry → ongoing management → exit, across equities, crypto, commodities, forex, and macro. Runs locally (private keys never leave your machine). 4.4k stars, actively maintained (last commit 2026-05-28).

> ⚠️ Experimental. Authors caution against live trading with real funds.

---

## Core Design

**Two long-lived processes:**

1. **Alice process** — AI runtime + research domain. Owns the *deciding*: what to research, when to act, what to say. Holds no broker credentials.
2. **UTA service** (Unified Trading Account) — broker connections, git-like trading state machine, guards, FX. Owns the *doing*: order construction, execution, state.

The separation mirrors a hardware wallet — Alice can run on a VPS or desktop; UTA can detach to a phone or home server holding broker keys. Today they co-run under a Docker/Guardian supervisor; UTA is designed to separate in future.

---

## Key Features

### Trading
- **Unified Trading Account (UTA)** — CCXT + Alpaca + Interactive Brokers combined into unified workspace. AI interacts with UTA, never directly with brokers.
- **Trading-as-Git** — stage orders, commit with a message, push to execute. Full history with commit hashes. Reviewable and stoppable at every step.
- **Guard pipeline** — pre-execution safety checks per account: max position size, cooldown, symbol whitelist.
- **Account snapshots** — periodic state capture with equity curve visualization.

### Research & Analysis
- **Market data** — equity, crypto, commodity, currency, macro via TypeScript-native OpenBB engine
- **Fundamental research** — financial statements, ratios, analyst estimates, earnings calendar, insider trading, market movers (deepest for equities)
- **News** — background RSS collection with archive search

### Automation / Scheduling
Two-layer automation:
- **Scheduling layer** — cron expressions, intervals, one-shot timestamps, heartbeat with active-hours filter, webhooks (planned)
- **Execution layer** — legacy: event → AgentCenter → AI run → notify; new path: workspace-resident executions (scheduled event fires a task inside a Workspace with persistent session)

### Interface
- **Web UI** — chat with SSE streaming, sub-channels, portfolio dashboard, equity curve, config management
- **Workspace** — per-task directory + git repo + persistent terminal running `claude` / `codex` / `shell` with OpenAlice MCP tools. Native prompt cache and rendering. Recommended path for non-trivial AI work.
- **Inbox** — workspace-to-user push channel. Agents call `inbox_push` to surface a document + markdown comment; click to jump back into workspace.
- **Telegram** — mobile access with trading panel
- **MCP server** — exposes tools to external agents

### AI Providers
- Claude via Agent SDK (OAuth or API key)
- Vercel AI SDK (Anthropic, OpenAI, Google) — switchable at runtime
- **Evolution mode** — permission escalation giving Alice full project access + Bash for self-modification

---

## Relevance to Our Pipeline

| Feature | Relevance |
|---------|-----------|
| Unified Trading Account (CCXT + Alpaca) | **HIGH** — our Alpaca paper account + Kraken could unify under UTA |
| Trading-as-Git | **MEDIUM** — interesting audit trail concept for paper trading |
| Workspace with MCP tools | **HIGH** — mirrors our current Claude Code + NanoClaw setup; could inspire architecture |
| Guard pipeline | **MEDIUM** — similar to our entry threshold gates (score ≥ 0.18, surprise ≥ 0.02) |
| Inbox push from agent | **HIGH** — direct analogue to our `send_message` pattern for trade alerts |
| Scheduling layer | **MEDIUM** — more robust than our nanoclaw scheduled tasks for complex multi-step flows |
| MCP server exposure | **LOW** — could expose our backtesting tools to external agents |

**Priority use case**: The UTA abstraction (CCXT + Alpaca + IBKR) is directly useful when we expand from Alpaca paper to live trading with multiple brokers. The Workspace + Inbox pattern mirrors how we already work and could provide a more robust foundation than the current nanoclaw + venv setup.

---

## Quick Start

```bash
git clone https://github.com/TraderAlice/OpenAlice
cd OpenAlice
pnpm install
cp .env.example .env  # add broker keys, AI provider keys
pnpm dev              # starts Alice + UTA under Guardian supervisor
```

Docs: openalice.ai/docs
