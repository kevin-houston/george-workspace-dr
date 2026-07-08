---
title: ZVT — Quantitative Finance Framework (Python)
added: 2026-07-08
category: trading/tools
source: https://github.com/zvtvz/zvt
---

# ZVT

Python quantitative finance platform with a unified data schema, ML machine, and factor pipeline. Primary focus is **China A-shares**, with secondary coverage of US and HK equities.

Install: `pip install zvt` (Python 3.8+)

## Markets & Data Coverage

| Market | Provider | Tickers |
|--------|----------|---------|
| China A-shares | EastMoney (em), JoinQuant (joinquant), Sina | 4,136 stocks |
| US stocks | em provider | 5,826 stocks |
| HK stocks | em provider | 2,597 stocks |
| ETFs, Indices, Funds | em | ✓ |

Entity types: `stock`, `stockus`, `stockhk`, `etf`, `index`, `block`, `fund`

## Unified API

```python
# Record (download) data
Schema.record_data(provider='em', code='600519')  # Maotai

# Query data
Schema.query_data(
    filters=[Stock.market_cap > 1e10],
    columns=[Stock.entity_id, Stock.market_cap],
    index='timestamp'
)
```

**Available schemas:**
- `Stock1dHfqKdata` / `StockUsKdata` — OHLCV (forward/backward adjusted)
- `FinanceFactor` — EPS, ROE, revenue growth
- `BalanceSheet`, `IncomeStatement`, `CashFlowStatement`
- `StockActorSummary` — institutional holdings

## ML Machine

```python
MaStockMLMachine(entity_ids=['stock_sz_000001']).train().predict().draw_result()
```

Drop-in ML pipeline over the schema layer. Trains on historical data and outputs buy signals.

## Factor Pipeline

Three-stage pipeline:

```
data_df
  → Transformer (e.g. MacdTransformer, custom)
  → factor_df
  → result_df  (filter_result bool / score_result 0–1)
  → TargetSelector
  → Trader
```

Two strategy modes:
- **Solo**: `StockTrader.on_time()` callback — simple single-stock logic
- **Formal**: `BullFactor` + `Transformer` composition — multi-signal ranked selection

## UI & Server

| Component | Command | Port |
|-----------|---------|------|
| Dash/Plotly dashboard | `zvt` | 8050 |
| REST API | `zvt_server` | 8090 |
| Next.js frontend | separate `zvt_ui` repo | 3000 |

## Tag System

Hybrid AI + human tagging via `init_tag_system.py`. Tags are dynamic and influence screening.

## Relevance to Our Stack

**Moderate.** Key assessment:

- **Primary use case is China** — A-share universe is where ZVT shines; the em provider for US data is less comprehensive than our Polygon integration
- **Factor pipeline architecture** is the most interesting piece: data_df → transformer → factor_df → result_df mirrors the abstraction we'd need for H382 FactorEngine — worth studying as a design reference
- **ML machine** is a higher-level interface than our raw sklearn/LightGBM in H320; comparable in spirit to what H381 AlphaLogics proposes
- **NOT a replacement** for our current stack (Polygon + yfinance + custom backtesting scripts)
- **Potential niche**: If Kevin ever wants to test H198-style momentum on China A-shares, ZVT would be the fastest path to data

**Comparison to similar tools:**
- vs. **Qlib** (Microsoft): both target China first; Qlib has stronger ML integration and academic backing; ZVT has better UI/dashboard
- vs. **our H382 FactorEngine** (arXiv:2603.16365): ZVT's factor pipeline is a working production implementation of a similar concept — good reference architecture

## Cross-References

- [[auto-alpha-discovery.md]] — H382 FactorEngine shares the same data→factor→result pipeline concept
- [[qlib.md]] — Microsoft's China quant platform (comparable scope, different ML emphasis)
- [[quantdinger-notes.md]] — another quant platform in our stack; different focus (execution + MCP integration)
- [[hypothesis-log.md]] — H382 (FactorEngine), H381 (AlphaLogics) are the H-series analogs to ZVT's ML machine
