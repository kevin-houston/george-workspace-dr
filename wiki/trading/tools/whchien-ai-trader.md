---
added: 2026-06-24
category: tools/backtesting
url: https://github.com/whchien/ai-trader
stars: 744
forks: 108
license: GPL-3.0
install: pip install ai-trader
status: active (updated 2026-06-24)
---

# whchien/ai-trader — Backtrader + MCP Backtesting Framework

**Not the same as HKUDS/AI-Trader** (social trading platform at `wiki/trading/tools/ai-trader.md`). This is a standalone backtesting engine.

Config-driven Backtrader framework with 20+ built-in strategies, multi-market support, and an MCP server that lets Claude run backtests with natural language commands.

---

## Key Features

| Feature | Detail |
|---------|--------|
| Engine | Backtrader (event-driven Python backtester) |
| Strategies | 20+ built-in: classic indicators → adaptive models |
| Markets | US stocks, Taiwan stocks, crypto, forex |
| Config | YAML-driven — version-controllable, reproducible |
| Data | `ai-trader fetch` CLI; SQLite caching (~50ms repeated loads) |
| MCP Server | `python -m ai_trader.mcp` — Claude can run backtests directly |
| Install | `pip install ai-trader` |

---

## MCP Server Integration

The most relevant feature for our stack. Once installed, Claude can run backtests and fetch data via tool calls — no Python scripting required for quick experiments.

**Start server:**
```bash
python -m ai_trader.mcp
```

**Add to NanoClaw via ncl:**
```bash
ncl groups config add-mcp-server \
  --name ai-trader \
  --command python3 \
  --args '["-m", "ai_trader.mcp"]'
```
Then restart: `ncl groups restart`

**Natural-language commands once live:**
- "Run a backtest of CrossSMAStrategy on SPY from 2020–2025"
- "Fetch AAPL data and run an RSI strategy"
- "List available strategies"

---

## CLI Reference

```bash
# Install
pip install ai-trader

# Run backtest from YAML config
ai-trader run my_backtest.yaml

# Quick backtest (no config file)
ai-trader quick CrossSMAStrategy data.csv --cash 100000

# Fetch market data
ai-trader fetch SPY --market us_stock --start-date 2020-01-01
ai-trader fetch BTC-USD --market crypto --start-date 2022-01-01

# Persistent SQLite cache (fast repeated loads)
ai-trader fetch AAPL --market us_stock --start-date 2024-01-01 --storage sqlite

# Data management
ai-trader data list
ai-trader data info
ai-trader data clean --market us_stock --before 2020-01-01
```

---

## YAML Config Example

```yaml
broker:
  cash: 100000
  commission: 0.001

data:
  file: "data/us_stock/SPY.csv"
  start_date: "2018-01-01"
  end_date: "2025-12-31"

strategy:
  class: "CrossSMAStrategy"
  params:
    fast: 10
    slow: 30

sizer:
  type: "percent"
  params:
    percents: 95
```

---

## Relevance to Pipeline

| Use case | Verdict |
|----------|---------|
| Quick signal prototyping (SMA/RSI/momentum) | ✓ Useful — YAML config faster than writing run_hNNN.py |
| Reference implementations for 20+ strategies | ✓ Good signal library to cross-check our implementations |
| MCP server for natural-language backtesting | ✓ High value if added to NanoClaw config |
| Replace vectorbt for ETF rotation | ✗ Backtrader event overhead not needed for monthly signals |
| Options backtesting | ✗ Not supported |

**Not a replacement** for the existing vectorbt/yfinance pipeline — Backtrader's event-driven overhead is unnecessary for monthly ETF rotation. Most useful as an MCP tool for ad-hoc exploration and as a strategy reference library.

---

## vs HKUDS/AI-Trader (existing `tools/ai-trader.md`)

| Dimension | whchien/ai-trader | HKUDS/AI-Trader |
|-----------|------------------|-----------------|
| Purpose | Backtesting framework | Social trading platform |
| Stars | 744 | Trending |
| Install | `pip install ai-trader` | Docker / web platform |
| MCP | Built-in server | SKILL.md agent registration |
| Markets | US/TW/crypto/forex | US equity focus |
