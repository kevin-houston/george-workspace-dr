# Tools & APIs

Useful external services, libraries, and APIs for trading research and agent development.

---

## Optopsy — Options Strategy Backtesting Library

**URL**: https://github.com/goldspanlabs/optopsy  
**Docs**: https://goldspanlabs.github.io/optopsy/  
**Added**: 2026-04-13  
**License**: AGPL-3.0 (research/educational use)

### What It Is

Python library for backtesting options strategies against historical EOD options data. 38 built-in strategies, a full simulator with equity curve output, portfolio simulation across multiple legs/symbols, and 80+ technical entry signals. Fills the gap that prevents paper trading the bull put spread strategies (R28, Sharpe 2.58/2.47) which are backtested but not live due to lack of options infrastructure.

### Install

```bash
pip install optopsy           # core
pip install optopsy[data]     # + EODHD data CLI
```

Requirements: Python 3.12–3.13, Pandas 2.0+, NumPy 1.26+

### Built-in Strategies (38 total)

Single leg, straddles, strangles, vertical spreads (call/put), ratio spreads, butterfly (call/put), iron condor, iron butterfly, condor, covered call, protective put, collar, cash-secured put, calendar spreads, diagonal spreads.

### Core Usage

```python
import optopsy as op

# Single strategy stats grouped by DTE and delta
results = op.short_puts(data)

# Full simulation with equity curve
result = op.simulate(
    data, op.short_puts,
    capital=100_000, quantity=1, max_positions=1,
    max_entry_dte=45, exit_dte=14,
    stop_loss=0.50, take_profit=0.25,  # 50% loss / 25% profit exits
    slippage="mid",
)
print(result.summary)       # Sharpe, Sortino, max DD, win rate, profit factor
print(result.equity_curve)  # portfolio value over time

# Bull put spread (directly relevant to R28)
results = op.put_vertical_spread(
    data,
    max_entry_dte=45, exit_dte=21,
    leg1_delta={"target": 0.30},   # short put
    leg2_delta={"target": 0.15},   # long put
)
```

### Data Sources

**Free historical data**: HistoricalOptionData.com / DeltaNeutral — one free symbol per month (going back to 2003). Fill form at https://historicaloptiondata.com/free-data/ to receive FTP download link. Format: EOD bid/ask, all strikes, all expirations. The `rut-eod` dataset in the @pyquantnews tweet is this format (2.37M rows, 2008–2013).

**Paid / live data**: EODHD API integration via CLI:
```bash
optopsy-data download SPY XOM CVX     # downloads and caches as Parquet
```
EODHD options data is ~$20-50/mo depending on tier.

### Relevance to Kevin's Research

- **R28 bull put spreads** (Sharpe 2.58 on XOM, 2.47 on CVX): backtested with custom code but no paper trading. Optopsy + free HistoricalOptionData.com data could reproduce and extend the R28 backtest, then enable a proper `pt_bull_put_spread.py` paper trader.
- **R32 SPX put-writing**: directly supported via `op.short_puts()` with VIX-Kelly sizing overlay.
- **Squid Programs**: the VA leg (short UX1, long UX3) isn't options but the VIX term structure signal could gate entries into `op.short_puts()` on SPX.
- **Risk metrics**: Sharpe, Sortino, VaR, CVaR, Calmar all built-in — no need to compute manually.

### Notes

- AGPL license means any app using it must be open-sourced. Fine for personal research, not for commercial deployment.
- Cash-settled index options (SPX, RUT) have no assignment risk despite the tweet's framing.
- The @pyquantnews tweet references an older fork (12 strategies). The active goldspanlabs fork has 38 strategies + simulator + portfolio simulation.

---

## "I Turned Claude Opus 4.7 Into a 24/7 Trader" — Tutorial Video

**URL**: https://www.youtube.com/watch?v=6MC1XqZSltw  
**Channel**: Nate Herk | AI Automation (663K subscribers)  
**Published**: April 16, 2026  
**Added**: 2026-04-17

### What It Covers

Step-by-step tutorial for building a fully autonomous AI trading agent using Claude Code + Alpaca brokerage API. No persistent Python process — Claude itself is the bot. 5 cloud routines cover the full trading day:

1. Pre-market research
2. Market-open order execution
3. Midday scan
4. End-of-day summary
5. Friday weekly review

**Tech stack**: Claude Code (Opus 4.7) · Alpaca (live trade execution) · Markdown files on a git branch (persistent memory/state) · n8n (automation) · Cron scheduling

**Key concepts**: Strategy guardrails gate every order before it fires. Memory is plain markdown in version control — simple, inspectable, no vector DB needed.

### Relevance

The architecture directly mirrors the current NanoClaw setup (Claude as agent, cron tasks, markdown memory). Relevant for:
- **Alpaca integration**: Alpaca has a free paper trading API — could replace the manual `pt_*.py` scripts with live Alpaca paper trades and remove the yfinance price-fetch dependency
- **Guardrails pattern**: The pre-order guardrail layer (strategy rules checked before every trade fires) maps onto what RegimeGuard does for R28 — could formalize this pattern across all strategies
- **State management**: Git-branch-as-memory is an interesting alternative to JSON portfolio files for auditability

---

## ChartLibrary — Chart Pattern Intelligence API

**URL**: https://chartlibrary.io/developers  
**Operator**: AlphaForge LLC  
**Added**: 2026-04-12

### What It Is

REST API (+ MCP server + Python SDK) that provides **chart pattern similarity search** for stocks. Given a ticker, returns the 10 most historically similar chart patterns from a database of 24 million pre-computed embeddings, plus forward returns at 1/3/5/10-day horizons, regime context, and an AI-generated summary.

### Key Stats

- 24 million pre-computed pattern embeddings
- 10 years of history
- 15,000+ stocks at minute-bar resolution
- <3 second response time
- Example (2026-04-02): NVDA query → 7/8 similar patterns positive after 5 days, avg 5d return +3.21%, avg 10d return +5.62%

### API Base URL

```
https://chartlibrary.io/api/v1
```

Authentication: `Authorization: Bearer YOUR_API_KEY` (NOT `X-API-Key` header — that returns 404).  
`api.chartlibrary.io` does not exist; the subdomain-less path is correct.

**Confirmed working (2026-04-21):**
```bash
curl "https://chartlibrary.io/api/v1/intelligence/AAPL" \
  -H "Authorization: Bearer cl_YOUR_KEY_HERE"
```

### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /intelligence/{symbol}` | All-in-one: matches + regime + summary |
| `GET /market-context` | SPY/QQQ/IWM, VIX, realized vol, regime label, sector leaders/laggards, crowding |
| `POST /analyze` | Pattern search + forward returns; `context_weight` for regime-aware matching; `format=agent` cuts tokens ~80% |
| `POST /portfolio/analyze` | Batch health check up to 20 symbols |
| `GET /accuracy/by-regime` | Pattern accuracy bucketed by VIX, breadth, VRP |
| `GET /regime-win-rates` | Win rates filtered by current regime |
| `GET /exit-signal` | Pattern-based exit recommendation for open position |
| `GET /risk-adjusted-picks` | Daily picks ranked by risk-adjusted return |
| `GET /pattern-degradation` | Signals losing accuracy vs historical baseline |
| `GET /anomaly/{symbol}` | Volume/price anomaly detection |
| `GET /earnings-reaction/{symbol}` | Historical earnings gap reactions |
| `GET /correlation-shift` | Rolling correlation breakdown between symbols |
| `POST /scenario` | Stress-test symbol against a market move |
| `GET /crowding` | Cross-symbol pattern crowding detector |
| `GET /sector-rotation` | Sector momentum rotation analysis |

### MCP Server

```bash
pip install chartlibrary-mcp  # v1.2.0, 23 tools
```

Works with Claude Desktop, Claude Code, ChatGPT, any MCP-compatible agent. Key tools: `get_market_context`, `analyze_pattern`, `check_ticker`, `get_portfolio_health`, `get_regime_accuracy`.

### Pricing

| Tier | Cost | Calls/Day | Rate Limit |
|------|------|-----------|------------|
| Sandbox | Free | 200 | 10 req/min |
| Builder | $29/mo | ~1,667/day (50k/mo) | 60 req/min |
| Scale | $99/mo | ~16,667/day (500k/mo) | 300 req/min |
| Enterprise | Custom | Unlimited | 1,000+ req/min |

### Relevance to Kevin's Research

- **R33 / PEAD enhancement**: `GET /earnings-reaction/{symbol}` could complement the Kim et al. LLM fundamental score — add historical earnings gap analog as a third layer
- **Pattern context for entries**: Before entering a PEAD trade, check if current chart analog has historically followed through at 5/10d horizons
- **Regime filtering**: `context_weight` parameter weights matches from similar market regimes — directly applicable to any regime-conditional strategy
- **LLM agent pipelines**: `format=agent` strips visual payload, ~80% token reduction — useful when calling from within a research agent
- **Not a price feed** — positions itself as complementary to Polygon/Alpha Vantage; adds historical analog layer on top

### Notes

- Sandbox tier (free) covers the core `GET /intelligence/{symbol}` endpoint — enough to test integration before committing to Builder
- Could be useful as an MCP tool added directly to the research container for live strategy context
