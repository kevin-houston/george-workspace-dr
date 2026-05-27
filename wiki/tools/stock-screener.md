---
created: 2026-05-27
updated: 2026-05-27
status: active
relevance: scan methodology (Minervini/CANSLIM), IBD industry groups (H181), market breadth (H165), MCP integration candidate
---

# xang1234/stock-screener

**GitHub:** https://github.com/xang1234/stock-screener  
**Static demo:** https://xang1234.github.io/stock-screener/  
**License:** Apache 2.0  
**Latest tag:** v1.1.2  
**Stack:** FastAPI · React 18/Vite · Celery · Redis · PostgreSQL · Docker · yfinance · Finviz · Alpha Vantage · SEC EDGAR

A self-hosted, full-stack stock screening platform with multi-market coverage, six screening methodologies, AI research chatbot, theme discovery, market breadth analysis, and IBD-style industry group rankings. Docker-deployable as a single-tenant server stack.

---

## Markets supported

10 markets with independent exchange calendars and per-market Celery refresh queues:

| Flag | Market | Exchanges/Index |
|------|--------|----------------|
| 🇺🇸 | US | NYSE, NASDAQ, AMEX, S&P 500 |
| 🇭🇰 | Hong Kong | HSI |
| 🇮🇳 | India | NSE, BSE |
| 🇯🇵 | Japan | Nikkei 225 |
| 🇰🇷 | Korea | KOSPI, KOSDAQ |
| 🇹🇼 | Taiwan | TAIEX |
| 🇨🇳 | China A-shares | SSE, SZSE, BJSE |
| 🇩🇪 | Germany | XETRA, DAX |
| 🇨🇦 | Canada | TSX, TSXV |
| 🇸🇬 | Singapore | SGX |

US, Asia, and Europe refresh in parallel via separate `data_fetch_{us,hk,jp,...}` queue workers.

---

## Screening methodologies

All screeners inherit from `BaseStockScreener`. The `DataPreparationLayer` fetches data once and fans it to all active screeners. Composite scoring supports `weighted_average`, `maximum`, or `minimum` aggregation.

| Screener | Key Criteria |
|----------|-------------|
| **Minervini Template** | RS > 70–80, Stage 2 uptrend, 50MA > 150MA > 200MA, price 30%+ above 52w low |
| **CANSLIM** | Q EPS > 25%, Annual EPS growth > 25% (3yr), volume patterns, RS > 70 |
| **IPO Scanner** | Recent IPO status, momentum, volume/price action |
| **Volume Breakthrough** | Unusual volume spikes with confirming price action |
| **Setup Engine** | Base detection, breakout confirmation, Bollinger squeeze, RS line strength |
| **Custom Scanner** | 80+ configurable filters (price, volume, technicals, fundamentals, scores) |

### Relevance to our strategies

- **Minervini Stage 2 + RS criteria** — directly actionable as a pre-filter before applying H217 (alpha101) or H228 (blend) signals. Keeps the universe in confirmed uptrends.
- **CANSLIM EPS growth criteria** — complements H222 (quality factor); Piotroski F-Score targets similar fundamentally strong names.
- **Volume Breakthrough** — may flag the same names that H217 alpha101 picks (strong close-within-range days often coincide with high-volume breakouts).
- **Setup Engine base detection** — could serve as a regime filter for H198 (momentum): only trade breakouts from valid bases.

---

## Industry group rankings

197 IBD industry groups ranked by relative strength with 1W/1M/3M/6M movers, historical rank charts, and constituent stock analysis. This is the same IBD Group Ranking framework used as a reference in:
- **H181 (industry-adjusted reversal)** — the H181 sector map uses GICS 11 sectors; IBD's 197 groups are more granular and could improve within-industry signal precision
- **H215/H217 (alpha101)** — IBD group rank could serve as a universe filter (only apply alpha101 within top-ranked groups)

The platform stores ranks in `ibd_industry_groups` and `ibd_group_ranks` tables. This data would be directly useful if we self-host.

---

## Market breadth dashboard

StockBee-style advance/decline analysis with:
- SPY overlay
- Stocks up/down 4%+ daily movers
- Multi-period trends: quarterly, monthly, 34-day windows
- Pre-computed via scheduled Celery task, stored in `market_breadth` table

**Relevance to H165 (regime detection):** The advance/decline data is a leading indicator of regime transitions, complementing the VIX < 25 + 200MA composite already in production. A breadth deterioration signal (e.g., % stocks above 50MA falling below 50% while VIX still calm) often precedes VIX spikes by 2–4 weeks.

---

## AI chatbot and theme discovery

- **Chatbot:** Groq-first LLM routing, optional Tavily/Serper web search, persistent conversation history. API keys: `GROQ_API_KEY` (free tier), `GEMINI_API_KEY` (free tier), `MINIMAX_API_KEY`, `ZAI_API_KEY`.
- **Theme discovery:** RSS + Twitter/X + news feeds → AI clustering → trending/emerging theme lifecycle tracking. Stores in `theme_clusters`, `theme_constituents`, `theme_metrics`.

---

## MCP integration (8 tools)

The platform exposes an MCP server (stdio + Streamable HTTP) — connectible to any MCP-capable agent including Claude Code:

| Tool | What it returns |
|------|----------------|
| `market_overview` | Current breadth, sentiment, key indices snapshot |
| `compare_feature_runs` | Diff two daily feature runs — biggest movers |
| `find_candidates` | Query stocks with opinionated filters |
| `explain_symbol` | Stock's rating explanation (brief or full depth) |
| `watchlist_snapshot` | Named watchlist with current data |
| `theme_state` | Theme rankings, momentum, lifecycle |
| `task_status` | Background job health and last execution times |
| `watchlist_add` | Add symbols to watchlist (opt-in, off by default) |

Every tool returns a structured envelope: `summary`, `facts`, `citations`, `freshness`, `next_actions`.

**George as MCP client:** If self-hosted, George could connect to this MCP server as a data layer — querying `market_overview` for the H165 breadth signal, `find_candidates` to pre-filter before alpha101, or `theme_state` to flag thematic momentum before earnings plays. This would require Docker deployment on Kevin's server.

---

## Architecture summary

```
Frontend (React/nginx) → Backend (FastAPI) → PostgreSQL
                                ↕
                        Celery Workers → Redis (broker DB0, results DB1, cache DB2)
```

**Domain-Driven Design layering:** `domain/` (ports/value objects) → `use_cases/` (orchestration) → `infra/` (repos, Celery, external APIs) → `api/` (FastAPI routes).

**Feature store:** daily `stock_feature_daily` snapshots scored for all universe stocks, published via pointer swap (`feature_run_pointers`). Scan API endpoints read from the latest published run for fast queries.

**Cache strategy:** Redis > PostgreSQL > External API. Price data: 7-day TTL, 5y OHLCV. Fundamentals: 7-day TTL. SPY benchmark: 24h TTL with distributed lock.

---

## Data sources

| Source | Used for |
|--------|----------|
| yfinance | OHLCV, fundamentals (free) |
| Finviz | Fundamentals, ratings, RS |
| Alpha Vantage | Supplemental price/fundamental data |
| SEC EDGAR | Fundamentals for US stocks |
| Official exchange feeds | Asia/EU universe refresh (HK, JP, TW, CN, etc.) |

---

## Deployment

```bash
# Production (GHCR images)
cp .env.docker.example .env.docker
# set SERVER_AUTH_PASSWORD, GROQ_API_KEY
ENABLED_MARKETS=US docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.release.yml up -d --no-build

# Local dev
cp .env.docker.example .env
scripts/docker-compose-enabled-markets.sh up
```

First-run bootstrap wizard stages: universe refresh → prices → fundamentals → breadth → group rankings → feature snapshot (US) → initial scan. Workspace opens when primary market reaches `ready`.

---

## Relevance summary for Kevin's trading project

| Use case | Priority | Notes |
|----------|----------|-------|
| IBD 197 industry groups for H181 (more granular than 11 GICS sectors) | Medium | Would require self-hosting or scraping group ranks |
| Minervini/CANSLIM pre-filter for H217/H228 stock selection | Medium | Could tighten universe quality vs. pure large-cap list |
| Market breadth data as H165 regime signal complement | Medium | StockBee-style A/D better leading indicator than VIX alone |
| MCP integration → George queries `market_overview` / `find_candidates` | Low | Requires Docker self-host; useful but not blocking |
| Theme discovery as PEAD universe expansion | Low | Thematic momentum may pre-screen earnings plays |

**Bottom line:** This is the most comprehensive open-source screening platform in the stack. It doesn't add a new alpha signal directly, but it provides the infrastructure (breadth data, IBD groups, pre-built scan methodologies) that could sharpen existing confirmed strategies. The MCP integration is the most novel capability — if self-hosted, George gains a live market state query layer.
