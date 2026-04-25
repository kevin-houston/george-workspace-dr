---
updated: 2026-04-25
type: platform
regulatory: CFTC DCM (intermediated US access since Dec 2025)
status: active — secondary platform; useful for cross-platform arbitrage
---

# Polymarket

World's largest decentralized prediction market by volume. Blockchain-based, global reach. Re-entered US market (via regulated brokers) in December 2025.

- Website: https://polymarket.com
- Docs: https://docs.polymarket.com
- Python SDK: `pip install py-clob-client` (GitHub: Polymarket/py-clob-client)

## Regulatory status

- November 25, 2025: CFTC granted Amended Order of Designation as DCM
- US access: via regulated FCM intermediaries (not direct retail, as of April 2026)
- State-level challenge: Nevada Gaming Control Board (January 2026) — CFTC preempts state gaming law
- **Practical status for US traders**: accessible via broker intermediaries; direct offshore access still available internationally

## Technical structure

- **Blockchain**: Polygon PoS (Ethereum sidechain)
- **Collateral**: USDC (1:1 with USD)
- **Settlement**: UMA oracle — smart contract finality, ~1–2 hour oracle voting window on major events
- **Order matching**: Off-chain (centralized backend, sub-second); settlement on-chain (2–3 second block confirmation)
- **Gas costs**: ~$0.002/transaction (negligible)
- **V2 upgrade** (announced): 50% latency reduction, new Polymarket USD collateral token, reduced bridging friction

## API

```python
from clob_client.client import ClobClient

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,  # Polygon
    private_key="0x...",
)

book = client.get_order_book(token_id="...")
order = client.create_order(token_id="...", price=0.65, size=10, direction="buy")
```

## Liquidity vs. Kalshi

| Metric | Polymarket | Kalshi |
|--------|-----------|--------|
| Monthly volume | $8–12B | $4.5B |
| Bid-ask spread | 0.5–2% (major) | 0.1–0.5% (economic) |
| Asset breadth | Crypto, politics, sports, anything | Economics, politics, crypto, corporate |
| Geographic reach | Global | US-focused |

## Fees

- Taker: 1–2% of order value
- Maker: 0–1% (some markets offer rebates)
- Settlement fee: ~0.5% of profit on winning positions
- **Higher fees than Kalshi** — require larger edge to be profitable

## Known issues for algo traders

1. **Oracle settlement delay**: 1–2 hours post-event; avoid holding through oracle window
2. **Centralized order book**: front-running risk exists theoretically (operator-run backend)
3. **US access friction**: intermediated access adds latency vs. Kalshi's direct API
4. **Gas on-chain**: negligible but monitor during Polygon network congestion

## Primary use for this project

Cross-platform arbitrage: when Polymarket and Kalshi price the same outcome differently (~8% spread on average historically). Requires automated execution — average arbitrage window collapsed from 12.3s (2024) to 2.7s (2026).
