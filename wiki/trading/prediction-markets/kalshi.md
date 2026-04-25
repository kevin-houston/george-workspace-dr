---
updated: 2026-04-25
type: platform
regulatory: CFTC-regulated DCM
status: active — recommended primary prediction market platform
---

# Kalshi

CFTC-regulated prediction market exchange. The institutional-grade option for US-based algorithmic traders.

- Website: https://kalshi.com
- API docs: https://docs.kalshi.com
- Python SDK: `pip install kalshi-python` (sync + async variants)

## Regulatory status

- Designated Contract Market (DCM) under CFTC since November 2020
- Landmark October 2024 judicial ruling legalized election trading
- Settlement by official government data (BLS, Fed) — no interpretation disputes
- **Safest regulatory choice for US traders in 2026**

## Scale (as of March 2026)

- ~$52 billion in event contracts outstanding
- ~$4.5 billion monthly trading volume (late 2025, up from $1B earlier in 2025)
- $867M total volume in 2025 (32× growth from $27M in 2024)

## Markets offered

| Category | Examples |
|----------|---------|
| Economic events | CPI, unemployment, Fed decisions, GDP, jobless claims, housing |
| Politics | Elections, policy outcomes (post-Oct 2024) |
| Crypto | Crypto price ranges, network events |
| Corporate/Financial | Earnings surprises, M&A announcements |

## Market structure

- Binary contracts: YES = $1.00, NO = $0.00
- Contracts trade $0.01–$0.99 (= implied probability)
- Tick size: $0.01 increments
- CLOB (Central Limit Order Book), FIFO matching
- Transparent order book

## API

```python
from kalshi_python.async_client import Kalshi

client = Kalshi(api_key="YOUR_API_KEY", private_key=private_key_pem)
market = await client.get_market(ticker="YES")
orderbook = await client.get_market_orderbook(ticker="YES")
await client.place_order(ticker="YES", price=0.65, count=10, side="buy")
```

- REST + WebSocket (real-time orderbook streaming)
- Auth: API key + RSA private key (PEM format)
- Sandbox environment available for testing

## Fees

- Percentage fee: 0.01–0.05% per transaction (volume-tiered)
- Per-contract fee: `$0.07 × p × (1 - p)` — peaks at $0.0175 at $0.50, lowest at extremes
- Maker rebates available via Liquidity Incentive Program (effective Feb 28, 2026)
- **Model fees carefully** — can consume 10–30% of thin arbitrage edges

## Liquidity

- Sufficient for algorithmic strategies under ~$1M notional
- Core markets (Fed decisions, CPI, major elections): tight spreads, good depth
- Thin liquidity: exotic outcomes, immediately pre-event (traders reduce inventory)
- Professional participants: Susquehanna, Tower Research, quant funds

## Key upcoming feature

**Kalshi Timeless** — launching April 27, 2026: leveraged/perpetual contracts with funding rates (like crypto perps). Enables new strategies: funding arbitrage, longer-horizon positions without contract expiration.

## Edge sources (see also: algorithmic-strategies.md)

1. Cross-derivative arbitrage vs. CME Fed funds futures
2. Event nowcasting (CPI, unemployment) using FRED + high-frequency data
3. Sentiment models on Fed communications
4. Market microstructure (order flow, FIFO queue prediction)
