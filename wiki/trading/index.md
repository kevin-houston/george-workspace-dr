---
updated: 2026-04-24
status: active
phase: 1 — research
---

# Trading & Prediction Markets Project

Goal: establish an income stream for Kevin via algorithmic securities trading and prediction markets. Work autonomously — research nightly, build incrementally, paper trade to prove results, then go live.

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | Active | Research & wiki-building |
| 2 | Pending | Backtesting infrastructure |
| 3 | Pending | Paper trading (Alpaca) |
| 4 | Pending | Live trading |

## Wiki sections

- [Algorithms](algorithms/) — trading strategy catalog
- [Tools](tools/) — open-source libraries (Qlib, Backtrader, Vectorbt, etc.)
- [Data Sources](data-sources/) — market data, fundamentals, alt data
- [Prediction Markets](prediction-markets/) — Kalshi, Polymarket, etc.
- [Backtesting](backtesting/) — setup, results, methodology
- [Paper Trading](paper-trading/) — Alpaca results log
- [Research Log](research-log/) — nightly research summaries

## Key decisions log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-04-24 | Start with research phase, paper trading before real money | Prudent — prove before risking capital |
| 2026-04-24 | Focus: equities and options first | Kevin's priority |
| 2026-04-24 | Data: Polygon.io free tier + Alpaca free tier | Both accounts exist; keys in OneCLI |
| 2026-04-24 | Paper trading via Alpaca | Kevin has existing paper account |
| 2026-04-24 | Backtesting must model macro regimes + after-tax returns | Kevin's requirement — real-world accuracy |

## API access

| Service | Status | Key location |
|---------|--------|-------------|
| Polygon.io | Free account | OneCLI vault |
| Alpaca (paper) | Account exists | OneCLI vault |
| GitHub | Active | `$GITHUB_TOKEN` env var |
