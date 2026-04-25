---
updated: 2026-04-25
type: tool + broker
status: installed; MCP approval pending
---

# Kraken CLI

Official open-source AI-native CLI from Kraken exchange. Built specifically for trading agents. MIT licensed.

- GitHub: https://github.com/krakenfx/kraken-cli
- Site: https://www.kraken.com/kraken-cli
- Version installed: 0.3.2
- Binary: `/home/node/.cargo/bin/kraken`

## What makes it agent-native

- Built-in MCP server: `kraken mcp -s all` exposes 151 commands directly as agent tools
- All output is machine-readable JSON
- Safety model: service groups (market/trade/paper/funding/earn) control scope; dangerous ops require `acknowledged=true`
- 50 pre-built "agent skills" (strategy recipes: DCA, grid, TWAP, portfolio rebalancing, etc.)

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

## MCP integration

```json
{
  "mcpServers": {
    "kraken": {
      "command": "/home/node/.cargo/bin/kraken",
      "args": ["mcp", "-s", "all"]
    }
  }
}
```

Status: submitted for admin approval (2026-04-25)

## Role in this project

Complements Alpaca:
- **Kraken**: crypto, forex, derivatives paper trading via MCP tools
- **Alpaca**: US equities + options paper trading via Python SDK

Together they give coverage across all asset classes Kevin wants to trade.

## Key commands

```bash
kraken paper init              # Initialize paper account
kraken paper balance           # Check balances
kraken paper buy XBTUSD 0.01   # Paper buy 0.01 BTC
kraken paper orders            # List open orders
kraken market ticker XBTUSD    # Get live price
kraken mcp -s market,paper     # Start MCP (read + paper only)
kraken mcp -s all              # Start MCP (all commands)
```
