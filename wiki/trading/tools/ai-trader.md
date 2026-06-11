---
added: 2026-06-11
category: tools/agent-platforms
url: https://github.com/HKUDS/AI-Trader
stars: trending (HKUDS — same group as Vibe-Trading)
license: MIT
status: active (updated 2026-06-11)
live_platform: https://ai4trade.ai
---

# AI-Trader — Agent-Native Social Trading Platform

**AI-Trader** is from HKUDS (Hong Kong University of Data Science) — the same group that built Vibe-Trading (already live in our stack). It's a social/collaborative trading platform designed specifically for AI agents: agents publish signals, debate positions, copy-trade each other, and earn reputation points.

> "Just like humans have their trading platforms, AI agents need their own."

---

## What it does

Three modes:

| Signal Type | Purpose |
|-------------|---------|
| Strategies | Discussion-only; share thesis, get community feedback |
| Operations | Copy-tradeable; followers can mirror positions in real-time |
| Discussions | Open collaboration; agents debate market views |

**Key features:**
- **Instant agent integration**: send one message to any agent — `Read https://ai4trade.ai/SKILL.md and register` — and the agent self-registers
- **Collective Intelligence**: agents collaborate and debate before publishing signals
- **Copy Trading**: follow top-performing agents and mirror their positions
- **Paper Trading**: $100K simulated capital; Polymarket paper trading also live (since 2026-03-03)
- **Universal markets**: Stocks, Crypto, Forex, Options, Futures
- **Reward system**: points for publishing signals + gaining followers → leaderboard

---

## Architecture

Self-hostable (MIT):
```
AI-Trader/
├── skills/              # Agent skill definitions (SKILL.md files)
├── docs/api/            # OpenAPI specifications
├── service/
│   ├── server/          # FastAPI backend
│   └── frontend/        # React frontend
```

Database: PostgreSQL (production) or SQLite (local). Copy `.env.example` → `.env`.

---

## Agent integration

One message wires George in:
```
Read https://ai4trade.ai/SKILL.md and register.
```

Once registered, George can:
- Publish signals from confirmed strategies (H026, H041a, PEAD)
- Subscribe to signals from top performers
- Sync trades across brokers
- Access real-time market data feeds

---

## Relationship to Vibe-Trading

HKUDS built both. Vibe-Trading (already in our MCP stack) focuses on backtesting/analysis tools. AI-Trader is the social/signal-sharing layer. They're designed as companions:
- Vibe-Trading = private research + backtesting
- AI-Trader = publish, collaborate, copy

---

## Relevance to George's work

**Potential uses:**
1. **Signal publishing**: publish H026/PEAD signals to the platform — build reputation, see community reception
2. **Strategy discovery**: monitor top performers on the leaderboard for novel alpha ideas
3. **Prediction market signals**: Polymarket paper trading integration is live — relevant to Kalshi/Polymarket work
4. **Benchmarking**: compare our confirmed strategy signals against community performance

**Caveats:**
- Copy-trading random agents is high-risk — no vetting of their backtests or live track records
- Platform is community/social — signal quality varies widely
- The self-registration via external SKILL.md URL is a security boundary to consider before wiring George in
- No published performance statistics for top performers yet

**Priority**: Low-medium. Interesting for signal publishing and community discovery, but not a core trading tool. Worth registering George to monitor; not worth blindly copying signals.

---

## Cross-references

- [Vibe-Trading MCP](../tools/quantdinger-notes.md) — companion project from HKUDS; already live in our stack
- [Multi-Agent LLM Trading Systems](multi-agent-llm-trading.md) — H274/H280 multi-agent designs; AI-Trader provides external agent collaboration layer
- [Prediction Markets](../prediction-markets/kalshi.md) — Polymarket paper trading now in AI-Trader
