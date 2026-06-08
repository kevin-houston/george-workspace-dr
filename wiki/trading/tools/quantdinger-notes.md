---
title: QuantDinger — Assessment Notes
added: 2026-06-07
category: tools
url: https://github.com/brokermr810/quantdinger
---

# QuantDinger

Self-hosted, open-source AI infrastructure platform for quantitative trading. Docker Compose stack: Python/Flask backend, Vue.js frontend, PostgreSQL 16, Redis 7.

## What it is

Aims to be an all-in-one platform: market data → signals → backtest → paper → live execution. Supports:
- **Crypto**: Binance, OKX, Bybit, Bitget, Coinbase, Kraken, Gate.io, HTX (via CCXT)
- **Equities**: Alpaca, IBKR
- **Forex/CFD**: MT5 (via TMGM)

Two strategy runtimes:
- `IndicatorStrategy` — vectorized dataframe signals, chart overlays
- `ScriptStrategy` — event-driven `on_bar` callbacks (mirrors Kevin's backtest loop patterns)

Agent Gateway at `/api/agent/v1`. Publishes `quantdinger-mcp` PyPI package for Claude Code / Cursor / Codex integration. Agent tokens paper-only by default; live requires explicit server-side unlock.

## License

- Backend: Apache 2.0 (clean)
- Frontend: Source-Available v1.0 — free for non-commercial, commercial requires paid license

## Assessment for Kevin's Setup

### Worth investigating
- **`quantdinger-mcp`** — PyPI package providing MCP tools for market reading, backtest execution, and trade placement directly within a Claude Code agent session. Could serve as a complementary or fallback tool when vibe-trading MCP disconnects. Install: `pip install quantdinger-mcp`. Requires a running QuantDinger server instance.
- **IBKR integration** — Kevin currently has Alpaca (equities/crypto) and Kraken (crypto/forex). IBKR would add margin accounts, options, and broader international equities. QuantDinger's IBKR adapter is worth reviewing if Kevin moves toward live execution with IBKR.

### Not worth pursuing now
- **Full Docker stack deployment** — overkill. Kevin already has a more sophisticated custom backtesting pipeline (H-series, PEAD, regime detection), Alpaca live execution, and vibe-trading MCP. QuantDinger's backtest engine is simpler (MA crossover, RSI examples) and would be redundant.
- **AI strategy generation features** — LLM-to-strategy generation is less rigorous than Kevin's hypothesis-driven approach. Risk of overfitting without the IS/OOS discipline we apply.
- **Frontend / community features** — not relevant for Kevin's setup.

### Bottom line
The `quantdinger-mcp` package is the one piece worth testing. Everything else is a stack Kevin has already built better. Check back if IBKR live execution becomes relevant.
