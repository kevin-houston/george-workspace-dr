---
updated: 2026-04-29
type: platform
regulatory: CFTC DCM (intermediated US access since Dec 2025)
status: active — secondary platform; cross-platform arbitrage vs. Kalshi
---

# Polymarket

World's largest decentralized prediction market by volume. Blockchain-based, global reach. Re-entered US market via regulated brokers in December 2025.

- Website: https://polymarket.com
- Docs: https://docs.polymarket.com
- Python SDK: `pip install py-clob-client` (GitHub: Polymarket/py-clob-client)
- CLOB API base: `https://clob.polymarket.com`
- Gamma API (market metadata): `https://gamma-api.polymarket.com`

## Regulatory status

- November 25, 2025: CFTC granted Amended Order of Designation as DCM
- US access: via regulated FCM intermediaries (not direct retail, as of April 2026)
- State-level challenge: Nevada Gaming Control Board (January 2026) — CFTC preempts state gaming law
- **Practical status for US traders**: accessible via broker intermediaries; direct offshore access still available internationally

## Technical structure

- **Blockchain**: Polygon PoS (Ethereum sidechain), chain ID 137
- **Collateral**: USDC (1:1 with USD) bridged to Polygon
- **Settlement**: UMA oracle — smart contract finality, ~1–2 hour oracle voting window on major events
- **Order matching**: Off-chain CLOB (centralized backend, sub-second); settlement on-chain (2–3 second block confirmation)
- **Gas costs**: ~$0.002/transaction (negligible)
- **V2 upgrade** (announced): 50% latency reduction, new Polymarket USD collateral token, reduced bridging friction

---

## API authentication

Polymarket uses **Ethereum private key authentication** (ECDSA), not RSA like Kalshi. Two credential types:

1. **L1 (Polygon wallet)**: Standard Ethereum private key — used for on-chain settlement
2. **L2 (CLOB API key)**: Derived from L1 signature — used for all API calls

### Setup

```bash
# Install
pip install py-clob-client eth-account

# Required env vars
export POLYMARKET_PRIVATE_KEY="0x<your-64-hex-char-private-key>"  # Polygon wallet
# Optional: separate API key if using CLOB key pair flow
```

### Get L2 API key from L1 key

```python
from clob_client.client import ClobClient
from clob_client.clob_types import ApiCreds

client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    private_key=os.environ["POLYMARKET_PRIVATE_KEY"],
)

# One-time derivation — save the returned creds, don't regenerate each run
creds = client.create_or_derive_api_creds()
# creds: ApiCreds(api_key, api_secret, api_passphrase)
# Store these for subsequent calls

# With stored creds:
client = ClobClient(
    host="https://clob.polymarket.com",
    chain_id=137,
    private_key=os.environ["POLYMARKET_PRIVATE_KEY"],
    creds=ApiCreds(
        api_key=os.environ["POLY_API_KEY"],
        api_secret=os.environ["POLY_API_SECRET"],
        api_passphrase=os.environ["POLY_API_PASSPHRASE"],
    ),
)
```

### USDC funding

You need USDC on Polygon to place orders. Bridge path:
1. Buy USDC on Coinbase/Kraken → withdraw to Polygon address
2. Or use Polygon Bridge: https://wallet.polygon.technology/polygon/bridge
3. Minimum useful amount: $100+ (gas is negligible but bridging has minimums)

---

## REST API endpoints

### Public (no auth needed)

```python
import requests

CLOB = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"

# Search markets (via Gamma API — richer metadata)
markets = requests.get(f"{GAMMA}/markets", params={
    "active": True,
    "closed": False,
    "limit": 50,
    "tag": "economics",       # filter by category
    "keyword": "inflation",   # text search
}).json()

# Single market by condition ID (Gamma)
market = requests.get(f"{GAMMA}/markets/{condition_id}").json()
# Fields: condition_id, question, outcomes, end_date, volume, liquidity

# Orderbook (CLOB)
book = requests.get(f"{CLOB}/book", params={
    "token_id": token_id,     # YES token ID (from market data)
}).json()
# Returns: {"market": ticker, "asset_id": token_id,
#           "bids": [{"price": "0.65", "size": "100"}, ...],
#           "asks": [{"price": "0.67", "size": "80"}, ...]}

# Best bid/ask
spread = requests.get(f"{CLOB}/spread", params={"token_id": token_id}).json()
# {"mid_point": "0.660", "spread": "0.020", "best_bid": "0.650", "best_ask": "0.670"}

# Recent trades
trades = requests.get(f"{CLOB}/trades", params={
    "token_id": token_id,
    "limit": 100,
}).json()
```

### Markets: key fields

```python
# market object from Gamma API:
{
    "condition_id": "0xabc...",      # unique market ID
    "question": "Will CPI exceed 3.0% in June 2026?",
    "outcomes": ["Yes", "No"],
    "clob_token_ids": ["0x111...", "0x222..."],  # [YES token, NO token]
    "volume": 1250000,               # lifetime USD volume
    "volume24hr": 45000,             # 24-hour volume
    "liquidity": 32000,              # current order book depth (USD)
    "end_date_iso": "2026-07-15T...",
    "tags": ["economics", "inflation"],
    "closed": False,
    "archived": False,
}

# token_id for ordering = clob_token_ids[0] for YES, [1] for NO
```

---

## Order placement

```python
from clob_client.client import ClobClient
from clob_client.clob_types import OrderArgs, OrderType

# BUY YES at limit price
order_args = OrderArgs(
    token_id="0x111...",   # YES token ID
    price=0.65,            # limit price (0–1 decimal, not cents)
    size=50,               # contracts (= shares = USDC if price=1.0)
    side="BUY",
)
order = client.create_order(order_args)
resp = client.post_order(order, OrderType.GTC)  # GTC = good-till-cancelled
# resp: {"success": True, "orderID": "0xabc..."}

# BUY NO (equivalent to shorting YES)
order_no = OrderArgs(
    token_id="0x222...",   # NO token ID
    price=0.38,            # NO price = 1 - YES price (approximately)
    size=50,
    side="BUY",
)

# Market order (FOK — fill-or-kill at best available)
order = client.create_market_order(OrderArgs(
    token_id=token_id,
    amount=100,            # USDC amount (not contracts)
    side="BUY",
))
resp = client.post_order(order, OrderType.FOK)

# Cancel open order
client.cancel(order_id="0xabc...")

# Cancel all open orders
client.cancel_all()

# Check open orders
open_orders = client.get_orders(OrderArgs(token_id=token_id))
```

### Order types

| Type | Code | Notes |
|------|------|-------|
| Good-till-cancelled | `OrderType.GTC` | Rests in book; maker rate |
| Fill-or-kill | `OrderType.FOK` | Fill fully or cancel; taker rate |
| Good-till-day | `OrderType.GTD` | Expires end of day UTC |

---

## Portfolio and positions

```python
# USDC balance (in USDC, not wei)
balance = client.get_balance()
# {"USDC": 450.50}

# Open positions
positions = client.get_positions()
for pos in positions:
    print(pos["market"], pos["asset_id"], pos["size"], pos["avg_price"])

# Trade history
trades = client.get_trades(token_id=token_id)

# P&L tracking: compute yourself — Polymarket doesn't expose realized P&L via API
# P&L = (current_mid - avg_price) * size  for unrealized
```

---

## WebSocket streaming

Real-time data feed on Polygon network (not to be confused with the blockchain):

```python
import asyncio, json, websockets

POLY_WS = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

async def stream_polymarket(token_ids: list[str]):
    async with websockets.connect(POLY_WS) as ws:
        # Subscribe
        await ws.send(json.dumps({
            "assets_ids": token_ids,
            "type": "market",          # market = price/book updates
        }))
        async for msg in ws:
            data = json.loads(msg)
            for update in data:
                event_type = update.get("event_type")  # "book" | "price_change" | "trade"
                if event_type == "book":
                    # Full orderbook snapshot
                    bids = update["buys"]   # [{"price": "0.65", "size": "100"}, ...]
                    asks = update["sells"]
                elif event_type == "price_change":
                    # Tick: best bid/ask
                    print(update["market"], update["price"])
                elif event_type == "trade":
                    # Completed trade
                    print(update["price"], update["size"], update["side"])

# User orders channel (requires auth headers)
POLY_WS_USER = "wss://ws-subscriptions-clob.polymarket.com/ws/user"
# Subscribe with: {"type": "user", "auth": {"apiKey": ..., "secret": ..., "passphrase": ...}}
```

---

## Fee structure

- **Taker**: 2% of gross transaction value (`price × size × 0.02`)
- **Maker**: 0% on most markets (some markets charge 0.5–1%)
- **Settlement fee**: None (UMA oracle is free to market participants)
- **Gas**: ~$0.002/tx on Polygon (negligible)

**Fee comparison vs. Kalshi:**

| Scenario | Kalshi (taker) | Polymarket (taker) |
|----------|---------------|-------------------|
| 100 contracts @ $0.50 | $1.75 | $1.00 |
| 100 contracts @ $0.30 | $1.47 | $0.60 |
| 100 contracts @ $0.70 | $1.47 | $1.40 |
| 1000 contracts @ $0.50 | $17.50 | $10.00 |

Polymarket taker fees are lower in absolute terms but:
- Kalshi maker rate (0.0175 formula) is often cheaper at moderate prices
- Polymarket spreads tend to be wider (0.5–2%) vs Kalshi core markets (0.1–0.5%)
- **Net cost is comparable** — don't assume Polymarket is cheaper

---

## Liquidity vs. Kalshi

| Metric | Polymarket | Kalshi |
|--------|-----------|--------|
| Monthly volume | $8–12B | $4.5B |
| Bid-ask spread | 0.5–2% (major markets) | 0.1–0.5% (economic markets) |
| Asset breadth | Crypto, politics, sports, culture, anything | Economics, politics, crypto, corporate |
| Economic markets depth | Thin vs. Kalshi | Deep — institutional MMs |
| Settlement finality | 1–2h oracle delay | Instant (official data) |
| Geographic reach | Global | US-focused |

**Key insight**: Polymarket dominates in volume and breadth, but Kalshi has tighter spreads on economic events (CPI, Fed, unemployment). For nowcasting strategies, **Kalshi is the primary execution venue**; Polymarket is best for cross-platform arbitrage or non-economic events.

---

## Cross-platform arbitrage: Kalshi ↔ Polymarket

Same outcome priced differently on both platforms. Buy YES cheap on one, buy NO cheap on the other.

### Finding opportunities

```python
import requests, time

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"

def get_kalshi_price(series_ticker: str) -> dict[str, float]:
    """Return {ticker: mid_price} for open Kalshi markets."""
    resp = requests.get(f"{KALSHI_BASE}/markets", params={
        "status": "open", "series_ticker": series_ticker, "limit": 50,
    }).json()
    return {
        m["ticker"]: ((m["yes_bid"] + m["yes_ask"]) / 2 / 100)
        for m in resp.get("markets", [])
        if m.get("yes_bid") and m.get("yes_ask")
    }

def find_poly_match(kalshi_ticker: str, keyword: str) -> dict | None:
    """Find a Polymarket market matching the same underlying event."""
    resp = requests.get(f"{GAMMA}/markets", params={
        "active": True, "keyword": keyword, "limit": 10,
    }).json()
    # Manual curation required — no universal ticker mapping exists
    return resp[0] if resp else None

def get_poly_mid(token_id: str) -> float:
    spread = requests.get(f"{CLOB}/spread", params={"token_id": token_id}).json()
    return float(spread.get("mid_point", 0))

def scan_arb_opportunities(kalshi_series: str, poly_keyword: str,
                            min_edge: float = 0.04) -> list[dict]:
    """
    Print arbitrage opportunities above min_edge (4pp by default).
    Note: actual arb requires simultaneous execution — this is a scanner only.
    """
    opportunities = []
    kalshi_prices = get_kalshi_price(kalshi_series)
    for k_ticker, k_price in kalshi_prices.items():
        poly_market = find_poly_match(k_ticker, poly_keyword)
        if not poly_market:
            continue
        token_id = poly_market["clob_token_ids"][0]
        p_price = get_poly_mid(token_id)
        if p_price <= 0:
            continue
        # YES cheaper on Polymarket: buy YES on Poly, buy NO on Kalshi
        if p_price < k_price - min_edge:
            edge = k_price - p_price
            opportunities.append({
                "kalshi": k_ticker, "poly": poly_market["condition_id"],
                "buy": "YES on Polymarket", "sell": "YES on Kalshi (buy NO)",
                "k_price": k_price, "p_price": p_price, "edge": edge,
            })
        # YES cheaper on Kalshi: buy YES on Kalshi, buy NO on Poly
        elif k_price < p_price - min_edge:
            edge = p_price - k_price
            opportunities.append({
                "kalshi": k_ticker, "poly": poly_market["condition_id"],
                "buy": "YES on Kalshi", "sell": "YES on Polymarket (buy NO)",
                "k_price": k_price, "p_price": p_price, "edge": edge,
            })
    return sorted(opportunities, key=lambda x: -x["edge"])
```

### Realistic execution constraints

- **Average arb window**: 2.7 seconds (2026) — down from 12.3s in 2024
- **Execution approach**: websocket listeners on both platforms, simultaneous IOC orders
- **Slippage**: spreads widen during execution; model 50% slippage on paper edge
- **Settlement risk**: Polymarket oracle can take 1–2 hours; price can drift before final settlement
- **Gross edge threshold to be worthwhile**: ~4% (covers both fees + slippage)

### Verdict

Arbitrage edge exists but is shrinking fast. Institutional players with co-located infrastructure dominate. For a retail algo operation, **nowcasting on Kalshi** has better risk-adjusted return than chasing 2.7-second arb windows.

---

## Economic markets on Polymarket

Polymarket does carry economic event markets, but they're thinner than Kalshi:

| Event | Polymarket volume | Kalshi volume | Better venue |
|-------|-----------------|---------------|-------------|
| Fed rate decision | ~$3–5M | ~$50M+ | Kalshi |
| CPI MoM | ~$1–2M | ~$10M | Kalshi |
| Unemployment rate | ~$500K | ~$5M | Kalshi |
| Presidential election | ~$1B | ~$400M | Polymarket |
| Crypto prices | ~$200M | ~$50M | Polymarket |
| Sports | ~$100M | Minimal | Polymarket |

For nowcasting strategies: execute on Kalshi, monitor Polymarket for divergences.

---

## Known issues for algo traders

1. **Oracle settlement delay**: 1–2 hours post-event; avoid holding through oracle window on volatile markets
2. **Centralized order book**: front-running risk exists theoretically (operator-run backend)
3. **US access friction**: intermediated access adds latency vs. Kalshi's direct API
4. **Gas on-chain**: negligible but monitor during Polygon network congestion
5. **Token ID vs condition ID confusion**: market has a `condition_id`; orders use `token_id` (YES/NO tokens differ)
6. **Price is 0–1 decimal** (not 0–100 cents like Kalshi) — common source of bugs
7. **API key rotation**: L2 keys expire; re-derive from L1 key if getting 401 errors

---

## Complete implementation: Polymarket market scanner

```python
"""
Scan Polymarket for economic markets and compare to Kalshi.
Run before major data releases to spot cross-platform divergences.
"""
import os, requests
from clob_client.client import ClobClient
from clob_client.clob_types import ApiCreds

GAMMA = "https://gamma-api.polymarket.com"
CLOB_HOST = "https://clob.polymarket.com"

def build_client() -> ClobClient:
    return ClobClient(
        host=CLOB_HOST,
        chain_id=137,
        private_key=os.environ["POLYMARKET_PRIVATE_KEY"],
        creds=ApiCreds(
            api_key=os.environ.get("POLY_API_KEY", ""),
            api_secret=os.environ.get("POLY_API_SECRET", ""),
            api_passphrase=os.environ.get("POLY_API_PASSPHRASE", ""),
        ),
    )

def get_economic_markets(limit=50) -> list[dict]:
    """Fetch active economic prediction markets from Polymarket."""
    resp = requests.get(f"{GAMMA}/markets", params={
        "active": True,
        "closed": False,
        "tag_slug": "economics",
        "limit": limit,
        "_order": "volume24hr",
    }, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_book_mid(token_id: str) -> float | None:
    """Return YES mid-price as decimal. Returns None if no valid book."""
    try:
        resp = requests.get(f"{CLOB_HOST}/spread", params={"token_id": token_id}, timeout=5)
        d = resp.json()
        mid = float(d.get("mid_point") or 0)
        return mid if 0 < mid < 1 else None
    except Exception:
        return None

def main():
    markets = get_economic_markets()
    print(f"\nTop Polymarket economic markets (by 24hr volume):\n")
    print(f"  {'Volume24h':>10}  {'Mid':>6}  {'Question'}")
    print(f"  {'─'*10}  {'─'*6}  {'─'*50}")
    for m in markets:
        token_id = (m.get("clob_token_ids") or [None])[0]
        mid = get_book_mid(token_id) if token_id else None
        mid_str = f"{mid:.2%}" if mid else "—"
        vol = m.get("volume24hr") or 0
        print(f"  ${vol:>9,.0f}  {mid_str:>6}  {m['question'][:60]}")

if __name__ == "__main__":
    main()
```

---

## Environment variables needed

```bash
export POLYMARKET_PRIVATE_KEY="0x..."      # Polygon wallet private key
export POLY_API_KEY="..."                  # L2 CLOB API key
export POLY_API_SECRET="..."               # L2 secret
export POLY_API_PASSPHRASE="..."           # L2 passphrase
```

To generate L2 credentials from an existing Polygon wallet:
```python
from clob_client.client import ClobClient
client = ClobClient("https://clob.polymarket.com", chain_id=137,
                    private_key=os.environ["POLYMARKET_PRIVATE_KEY"])
creds = client.create_or_derive_api_creds()
print(creds.api_key, creds.api_secret, creds.api_passphrase)  # store these
```

---

## Primary use for this project

1. **Cross-platform arbitrage scanner**: monitor Polymarket for divergences vs. Kalshi on Fed/CPI/unemployment markets
2. **Non-economic event exposure**: political/sports/crypto events not available on Kalshi
3. **Calibration reference**: Polymarket's larger volume can validate Kalshi prices for nowcasting strategies
