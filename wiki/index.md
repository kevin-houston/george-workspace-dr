---
updated: 2026-04-25
sources_indexed: 1
pages: 19
---

# Wiki Index

Content catalog — updated on every ingest. Read this first when answering queries.

## How to use this index

Each entry: `[Page title](path.md) — one-line summary`

When answering a query:
1. Scan the relevant category sections here
2. Open the linked pages that look relevant
3. Synthesize; cite by page title

---

## Categories

### Trading & Prediction Markets

- [Project Index](trading/index.md) — phases, decisions, API access status
- [Qlib](trading/tools/qlib.md) — Microsoft's AI quant platform; ML strategies, production-grade
- [Backtrader vs Vectorbt](trading/tools/backtrader-vs-vectorbt.md) — framework comparison; Backtrader for classical/paper, Vectorbt for fast optimization
- [Kraken CLI](trading/tools/kraken-cli.md) — official Kraken AI-native CLI; 151 MCP tools, paper trading built-in, crypto/forex/xStocks
- [OpenAlgo](trading/tools/openalgo.md) — open-source algo trading platform; India-only now, US broker support on 2026 roadmap
- [Polygon.io](trading/data-sources/polygon.md) — market data (free: EOD only; paid: options, ticks, Greeks)
- [Alpaca](trading/data-sources/alpaca.md) — broker + data; paper trading; 10yr 1-min data free
- [Free Data Sources](trading/data-sources/free-data.md) — EDGAR (EdgarTools), Alpha Vantage, Finnhub; avoid yfinance
- [Research Log 2026-04-24](trading/research-log/2026-04-24.md) — session 1: tools and data sources
- [Research Log 2026-04-25](trading/research-log/2026-04-25.md) — session 2: prediction markets deep dive
- [151 Trading Strategies (Kakushadze & Serur)](trading/strategies/151-trading-strategies.md) — comprehensive strategy catalog; 151+ strategies with formulas; Tier 1/2/3 implementation priority
- [Backtesting Design Principles](trading/backtesting/design-principles.md) — macro regime modeling, after-tax returns, real-world costs
- [Hypothesis Log](trading/backtesting/hypothesis-log.md) — falsifiable experiment cards; H001 REJECTED (ATR mode dominates ORB H/L mode)
- [Kalshi](trading/prediction-markets/kalshi.md) — primary prediction market platform; CFTC-regulated, economic events, Python SDK
- [Polymarket](trading/prediction-markets/polymarket.md) — secondary; highest global volume, blockchain-based, US re-entry Dec 2025
- [Other Prediction Market Platforms](trading/prediction-markets/other-platforms.md) — PredictIt, Manifold, IBKR/CME, emerging platforms
- [Prediction Market Algorithmic Strategies](trading/prediction-markets/algorithmic-strategies.md) — Kelly criterion, event modeling, arbitrage, NLP; code examples

### Disaster Recovery

- [DR Overview](dr/overview.md) — restore procedure, what survives, what to tell a fresh George
- [Git Backup Setup](dr/git-backup.md) — git repo config, current status, blocked items
- [Session Diary](dr/diary.md) — append-only log of sessions; narrative recovery layer

