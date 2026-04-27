---
updated: 2026-04-26
status: active
phase: 2 — backtesting
---

# Trading & Prediction Markets Project

Goal: establish an income stream for Kevin via algorithmic securities trading and prediction markets. Work autonomously — research nightly, build incrementally, paper trade to prove results, then go live.

## Phases

| Phase | Status | Description |
|-------|--------|-------------|
| 1 | ✅ Done | Research & wiki-building |
| 2 | Active | Backtesting infrastructure + hypothesis testing |
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
| 2026-04-26 | yfinance as data fallback (Alpaca SDK not installable in container) | Alpaca module unavailable; yfinance works for EOD |
| 2026-04-26 | BIL preferred over TLT as risk-off refuge in dual momentum (H006 result) | TLT has duration risk; BIL immune to rate-hike bears |

## API access

| Service | Env var | Status |
|---------|---------|--------|
| Polygon.io | `$POLYGON_API_KEY` | ✓ Tested — free tier, EOD bars |
| FRED | `$FRED_API_KEY` | ✓ Tested — macro data (Fed funds, GDP, etc.) |
| Alpha Vantage | `$ALPHA_VANTAGE_API_KEY` | ✓ Present |
| Financial Modeling Prep | `$FMP_API_KEY` | ✓ Present — fundamentals |
| NewsAPI | `$NEWSAPI_KEY` | ✓ Present — sentiment/news |
| EDGAR | `$EDGAR_KEY` | ✓ Present |
| OpenAI | `$OPENAI_API_KEY` | ✓ Present — ML/NLP tasks |
| Alpaca (paper) | `$ALPACA_API_KEY` + `$ALPACA_SECRET` | ✓ Active — $102k portfolio, $204k buying power |
| GitHub | `$GITHUB_TOKEN` | ✓ Active |
| Massive.com | `$MASSIVE_KEY` | ✓ Active — delayed prices, options contract reference; Polygon backend |
