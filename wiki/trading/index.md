---
updated: 2026-05-05
status: active
phase: 2→3 — backtesting complete, paper trading active
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
  - [Position Sizing & Portfolio Construction](algorithms/position-sizing.md) ← new 2026-04-27
  - [Momentum Strategies](algorithms/momentum-strategies.md) ← new 2026-04-30 (H001–H151 findings, implementation guide)
  - [Pairs Trading / Stat Arb](algorithms/pairs-trading.md) ← updated 2026-05-05 (family EXHAUSTED — H152-H160 all NOT CONFIRMED at daily frequency)
  - [Event-Driven Strategies](algorithms/event-driven.md) ← updated 2026-05-05 (H163 **CONFIRMED** — FinBERT NLP signal real; H161/H162 PARTIAL CONFIRMED; H168 IN-PROGRESS)
- [Tools](tools/) — open-source libraries (Qlib, Backtrader, Vectorbt, etc.)
  - [Qlib Deep Dive](tools/qlib.md) ← expanded 2026-04-28 (architecture, model zoo, benchmarks, RD-Agent)
  - [Backtrader vs Vectorbt](tools/backtrader-vs-vectorbt.md) ← expanded 2026-04-29 (H116 rotation in Vectorbt, `Portfolio.from_orders` multi-asset pattern)
  - [Kraken CLI](tools/kraken-cli.md) ← expanded 2026-05-01 (all 50 agent skills, MCP service groups, full command reference)
  - [NLP & Alternative Data](tools/nlp-alternative-data.md) ← updated 2026-05-05 (analyst belief asymmetry arXiv:2511.15214, H171 GPT-4o-mini alternative, AlphaVantage transcripts)
- [Data Sources](data-sources/) — market data, fundamentals, alt data
  - [Alpaca Automation Guide](data-sources/alpaca-automation.md) ← new 2026-04-27 (Phase 3 foundation)
  - [Polygon.io](data-sources/polygon.md) ← expanded 2026-04-28 (API endpoints, WebSocket, pricing, vs Alpaca)
  - [Free / Low-Cost Sources](data-sources/free-data.md) ← expanded 2026-04-28 (Tiingo, EDGAR, Finnhub, FRED, yfinance status)
- [Prediction Markets](prediction-markets/) — Kalshi, Polymarket, etc.
  - [Kalshi](prediction-markets/kalshi.md) ← expanded 2026-04-29 (full auth/API/WebSocket, RSA signing, CPI nowcasting implementation, fee modeling, rate limits, Timeless perps)
  - [Algorithmic Strategies](prediction-markets/algorithmic-strategies.md) ← expanded 2026-05-02 (cross-market arb, nowcasting with full Python lifecycle, calibration, Timeless funding arb, IBKR ForecastTrader API)
  - [Other Platforms](prediction-markets/other-platforms.md) ← expanded 2026-05-02 (IBKR ForecastTrader full API, Kalshi Timeless mechanics, emerging platforms)
- [Backtesting](backtesting/) — setup, results, methodology
  - [Design Principles](backtesting/design-principles.md) ← expanded 2026-05-05 (IS/OOS framework, bias taxonomy, confirmation criteria, deflated Sharpe, López de Prado)
  - [Walk-Forward & CPCV](backtesting/walk-forward-cpcv.md) ← new 2026-05-07 (WFO variants, CPCV algorithm, purging/embargoing, DSR formulas, Python libs: timeseriescv/skfolio/mlfinlab, when to use what)
- [Paper Trading](paper-trading/) — Alpaca results log
  - [H149 Alpaca ETF Rotation](paper-trading/h122-alpaca.md) ← active (100% H026, $102k paper)
  - [PEAD-NLP Alpaca Deployment](paper-trading/pead-nlp-alpaca.md) ← new 2026-05-06 (H163/H174 live pipeline: gap detection, 8-K scoring, OPG orders)
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
| 2026-04-27 | H020 (5-asset rotation) supersedes H016 as primary ETF strategy | Sharpe 1.23 vs 0.78; 6.7% OOS degradation (vs 50% typical); generalizes across universes |
| 2026-04-27 | H018 blend (H020 + H009, 50/50) is the target portfolio for Phase 3 | Sharpe 1.255, MaxDD -18.4%, corr=0.31 — diversification benefit confirmed |
| 2026-04-27 | Use alpaca-py (not alpaca-trade-api) for all Alpaca automation | legacy SDK deprecated Dec 2022 |

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
