---
updated: 2026-04-25
type: tool
status: watch — not ready for US markets yet
---

# OpenAlgo

Open-source algorithmic trading platform by @marketcallsHQ (Rajandran R). Abstracts 30+ broker APIs behind a unified REST layer. Self-hosted Flask backend + React frontend.

- GitHub: https://github.com/marketcalls/openalgo (1.7k stars, 847 forks, active)
- Docs: https://docs.openalgo.in
- License: AGPL-3.0
- Latest: v2.0.0.5 (April 2026)

## What it does

Single REST API (`/api/v1/`) works across all connected brokers without code changes. Core value: write a strategy once, deploy to any supported broker. Includes:
- Unified order placement, position management, market data
- Strategy hosting (upload Python files, schedule, monitor with process isolation)
- Vectorized backtesting via OpenEngine (VectorBT-based)
- 12 built-in analytics dashboards (Options Greeks, IV surface, GEX, max pain)
- MCP server (25+ tools) — works with Claude, Cursor, ChatGPT
- WebSocket normalized feed (port 8765) across all connected brokers

## Critical limitation: India-only for now

**Supported brokers: 30+ Indian brokers only** (Zerodha, Angel One, Upstox, Dhan, etc.)

No Alpaca, no Kraken, no US brokers. Supported exchanges: NSE, BSE, MCX (India).

**2026 roadmap includes**: US broker support (Alpaca), crypto exchange support (Kraken). Not shipped yet.

## Architecture

```
Signal source (TradingView, webhook, Python script)
        ↓
OpenAlgo Flask backend (port 5000)
        ↓
Normalized broker API layer → 30+ Indian brokers
        ↓
WebSocket feed (port 8765) → React dashboard
```

## vs. our current stack

| Need | OpenAlgo | Our stack |
|------|----------|-----------|
| US equities | ❌ Not yet | ✅ Alpaca |
| US options | ❌ Not yet | ✅ Alpaca |
| Crypto | ❌ Not yet | ✅ Kraken CLI |
| Backtesting | ✅ VectorBT-based | ✅ Vectorbt/Backtrader |
| MCP trading tools | ✅ Yes | ✅ Kraken MCP |
| Strategy hosting | ✅ Built-in | Manual |

## Verdict for this project

**Not useful now.** Our stack (Alpaca + Kraken MCP + Python) already covers US equities, options, and crypto better than OpenAlgo can today.

**Watch for 2026**: If Alpaca/Kraken broker support ships, OpenAlgo would become a strong unified execution layer worth integrating — especially for the MCP + strategy hosting features.

## MCP integration (when relevant)

```json
{
  "mcpServers": {
    "openalgo": {
      "command": "uvx",
      "args": ["openalgo-mcp"]
    }
  }
}
```
