---
updated: 2026-04-24
type: data-source + broker
access: Kevin has paper account; API key in OneCLI vault
---

# Alpaca Markets

Broker + data provider. Free paper trading + commission-free real trading for US equities and crypto.

**Related pages**: [Alpaca Automation Guide](alpaca-automation.md) — production trading patterns, order execution, Phase 3 foundation | [Paper Trading Index](../paper-trading/index.md) — active H149 position log

- Docs: https://docs.alpaca.markets/
- Python SDK: `pip install alpaca-py` (official, use this over legacy alpaca-trade-api)
- Paper trading: https://paper-api.alpaca.markets

## Paper trading

- Free, no deposit required
- Simulates real market conditions (PDT rules enforced, no dividends)
- Supports: Stocks, ETFs, options, crypto
- Order fill based on real-time quotes, not actual exchange routing

## Market data (free tier)

- **Source**: IEX only (~2% of market volume)
- **Rate limit**: 200 req/min
- **Historical**: 10 years of 1-minute bars — free even on unfunded account
- **Real-time**: IEX data (delayed/limited vs full SIP)
- **Paid ($99/mo)**: Full SIP real-time data

## API capabilities

- REST + WebSocket (RFC6455)
- Real-time streaming: 5000+ stocks, 20+ crypto
- JSON and MessagePack codecs
- Asset classes: Stocks/ETFs, Options, Crypto

## Paper trading limitations vs live

| | Paper | Live |
|--|-------|------|
| Dividends | Not simulated | Paid |
| Order emails | No | Yes |
| PDT rules | Enforced | Enforced |
| Margin/short costs | Not charged | Charged |
| Data | IEX only | IEX (free) or SIP (paid) |

## Key endpoints

```python
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

# Paper trading
client = TradingClient(api_key, secret_key, paper=True)

# Historical data
data_client = StockHistoricalDataClient(api_key, secret_key)
```

## Status for this project

Primary paper trading venue. Use for Phase 3 live strategy testing. Historical 1-min data is valuable for intraday backtesting without paying for Polygon paid tier.
