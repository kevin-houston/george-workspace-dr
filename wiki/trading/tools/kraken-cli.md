---
updated: 2026-04-30
type: tool + broker
status: binary not installed (needs reinstall); MCP config ready
---

# Kraken CLI

Official open-source AI-native CLI from Kraken exchange. Built specifically for trading agents. MIT licensed.

- GitHub: https://github.com/krakenfx/kraken-cli
- Site: https://www.kraken.com/kraken-cli
- Version installed previously: 0.3.2 (binary missing as of 2026-04-30 — reinstall via `cargo install kraken-cli`)

## What makes it agent-native

- Built-in MCP server: `kraken mcp -s all` exposes 151 commands directly as agent tools
- All output is machine-readable JSON
- Safety model: service groups control scope; dangerous ops require `acknowledged=true`
- 50 pre-built **agent skills** (strategy recipes — see full list below)

## Asset classes

| Class | Coverage |
|-------|---------|
| Crypto spot | 1,400+ pairs, up to 10x margin |
| xStocks (tokenized) | 79 assets (AAPL, TSLA, SPY, etc.) — crypto-wrapped, not actual US equities |
| Forex perpetuals | EUR/USD, GBP/USD, 11 pairs |
| Crypto futures | 317 contracts, up to 50x leverage |
| Earn/staking | Flexible and bonded |

## Paper trading

- No account or API keys needed
- Uses live Kraken market prices
- Initialized: $10,000 USD starting balance, 0.26% fee simulation
- Commands: `kraken paper buy`, `kraken paper sell`, `kraken paper balance`, `kraken paper orders`
- Same interface as live trading — switch by replacing `paper` with `order`

---

## MCP Integration

### Config (Claude Desktop / NanoClaw)

```json
{
  "mcpServers": {
    "kraken": {
      "command": "kraken",
      "args": ["mcp", "-s", "all"]
    }
  }
}
```

Or scope to read-only + paper only (safer during testing):

```json
{
  "mcpServers": {
    "kraken": {
      "command": "kraken",
      "args": ["mcp", "-s", "market,paper"]
    }
  }
}
```

### Service groups

| Group | Scope | Auth required |
|-------|-------|---------------|
| `market` | Public data — ticker, OHLC, orderbook, streaming | No |
| `account` | Read-only account data | Yes |
| `paper` | Spot paper trading | No |
| `trade` | Live order placement | Yes + acknowledged |
| `funding` | Withdrawals, deposits | Yes + acknowledged |
| `earn` | Staking / earn strategies | Yes |
| `subaccount` | Subaccount management | Yes |
| `futures` | Futures live trading | Yes + acknowledged |
| `futures-paper` | Futures paper trading | No |
| `auth` | Authentication operations | Yes |

Dangerous operations (trade, funding) require `acknowledged=true` in the request unless the `--allow-dangerous` CLI flag is set. This is the safety model.

---

## The 50 Agent Skills

Skills are pre-built strategy recipes and reference guides loaded into the agent's context via MCP. Each skill is a markdown file that teaches an agent how to use specific Kraken capabilities.

### Core Skills (7)

| Skill | Description |
|-------|-------------|
| `kraken-setup` | Install, credentials, and first paper-trading session |
| `kraken-shared` | Auth, invocation contract, parsing, and safety rules |
| `kraken-autonomy-levels` | Progress from read-only to fully autonomous agent trading |
| `kraken-mcp-integration` | Connect MCP clients to kraken-cli |
| `kraken-rate-limits` | API rate limit budgets across spot and futures tiers |
| `kraken-order-types` | Complete reference for all spot and futures order types |
| `kraken-error-recovery` | Handle order failures, duplicates, and network errors safely |

### Market Data Skills (4)

| Skill | Description |
|-------|-------------|
| `kraken-market-intel` | Ticker, orderbook, OHLC, and streaming market reads |
| `kraken-multi-pair` | Multi-pair screening, watchlists, spread, and volume comparison |
| `kraken-alert-patterns` | Price alerts, threshold monitoring, and notification triggers |
| `kraken-ws-streaming` | Real-time WebSocket streaming for spot and futures |

### Spot Trading Skills (6)

| Skill | Description |
|-------|-------------|
| `kraken-spot-execution` | Safe spot order execution with validation gates |
| `kraken-stop-take-profit` | Stop-loss and take-profit management |
| `kraken-fee-optimization` | Minimize fees through maker orders and volume tiers |
| `kraken-paper-strategy` | Test spot strategies on paper trading |
| `kraken-paper-to-live` | Promote validated strategies to live trading |
| `kraken-risk-operations` | Operational risk controls for live agent trading |

### Futures Skills (5)

| Skill | Description |
|-------|-------------|
| `kraken-futures-trading` | Futures order lifecycle and paper trading |
| `kraken-futures-risk` | Leverage, funding rates, margin health, and liquidation awareness |
| `kraken-liquidation-guard` | Prevent futures liquidation through margin monitoring |
| `kraken-basis-trading` | Delta-neutral spot-futures basis trades |
| `kraken-funding-carry` | Earn funding rate payments with hedged carry positions |

### Trading Strategy Skills (4)

| Skill | Description |
|-------|-------------|
| `kraken-dca-strategy` | Dollar cost averaging with scheduled buys |
| `kraken-grid-trading` | Grid trading with layered orders across price ranges |
| `kraken-rebalancing` | Portfolio rebalancing to maintain target allocations |
| `kraken-twap-execution` | Time-weighted average price execution |

### Funding & Account Skills (5)

| Skill | Description |
|-------|-------------|
| `kraken-funding-ops` | Deposits, withdrawals, and wallet transfers |
| `kraken-earn-staking` | Earn strategies and staking allocation |
| `kraken-tax-export` | Export trade history, ledgers, and cost basis data |
| `kraken-portfolio-intel` | Balance analysis, P&L tracking, and exports |
| `kraken-subaccount-ops` | Subaccount creation, transfers, and strategy isolation |

### Strategy Recipes (7)

Recipes are step-by-step agent playbooks — not just reference, but executable workflows.

| Recipe | Description |
|--------|-------------|
| `recipe-start-dca-bot` | Set up and run a DCA bot from paper to live |
| `recipe-launch-grid-bot` | Deploy a grid trading bot with safety controls |
| `recipe-trailing-stop-runner` | Ride a trend with a trailing stop mechanism |
| `recipe-basis-trade-entry` | Enter spot-futures basis trades at premium thresholds |
| `recipe-futures-hedge-spot` | Hedge a spot holding with a short futures position |
| `recipe-funding-rate-scan` | Scan perpetuals for attractive funding rate opportunities |
| `recipe-paper-strategy-backtest` | Backtest strategies using paper trading |

### Portfolio Recipes (5)

| Recipe | Description |
|--------|-------------|
| `recipe-weekly-rebalance` | Weekly portfolio rebalance to target allocations |
| `recipe-daily-pnl-report` | Daily profit and loss summary from trades |
| `recipe-portfolio-snapshot-csv` | Export portfolio snapshot to CSV |
| `recipe-subaccount-capital-rotation` | Rotate capital between subaccounts |
| `recipe-fee-tier-progress` | Track 30-day volume progress toward fee tier advancement |

### Market Data Recipes (4)

| Recipe | Description |
|--------|-------------|
| `recipe-morning-market-brief` | Morning summary with prices and portfolio state |
| `recipe-multi-pair-breakout-watch` | Monitor pairs for price breakouts |
| `recipe-track-orderbook-depth` | Monitor orderbook depth and bid-ask imbalance |
| `recipe-price-level-alerts` | Set up alerts for key price level crossings |

### Risk Recipes (2)

| Recipe | Description |
|--------|-------------|
| `recipe-emergency-flatten` | Cancel all orders and close all positions |
| `recipe-drawdown-circuit-breaker` | Stop trading when drawdown exceeds threshold |

### Funding Recipes (2)

| Recipe | Description |
|--------|-------------|
| `recipe-withdrawal-to-cold-storage` | Safely withdraw funds to pre-approved addresses |
| `recipe-earn-yield-compare` | Compare yield strategies to find optimal rates |

---

## Key Commands

```bash
# Setup
cargo install kraken-cli          # (re)install binary
kraken paper init                 # Initialize paper account ($10k USD)

# Market data
kraken market ticker XBTUSD       # Live BTC/USD price
kraken market ohlc XBTUSD 1h      # 1-hour candles

# Paper trading
kraken paper balance               # Check balances
kraken paper buy XBTUSD 0.01      # Paper buy 0.01 BTC
kraken paper sell ETHUSD 0.5      # Paper sell 0.5 ETH
kraken paper orders                # List open orders

# MCP server
kraken mcp -s market,paper         # Start MCP (read + paper only)
kraken mcp -s all                  # Start MCP (all 151 commands)
```

---

## Role in this project

Complements Alpaca:
- **Kraken**: crypto, forex, tokenized equity (xStocks), and crypto futures paper/live trading via MCP
- **Alpaca**: US equities + options paper trading via Python SDK

Together they give coverage across all asset classes Kevin wants to trade. xStocks are crypto-wrapped equivalents of US equities (not real shares) — useful for 24/7 momentum rotation testing but not a replacement for Alpaca for actual US equities.
