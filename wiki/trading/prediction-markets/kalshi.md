---
updated: 2026-04-29
type: platform
regulatory: CFTC-regulated DCM
status: active — recommended primary prediction market platform
---

# Kalshi

CFTC-regulated prediction market exchange. The institutional-grade option for US-based algorithmic traders.

- Website: https://kalshi.com
- API docs: https://docs.kalshi.com
- Python SDK: `pip install kalshi-py` (official, sync + async)
- Base URL: `https://api.elections.kalshi.com/trade-api/v2`

## Regulatory status

- Designated Contract Market (DCM) under CFTC since November 2020
- Landmark October 2024 judicial ruling legalized election trading
- Settlement by official government data (BLS, Fed, etc.) — no interpretation disputes
- **Safest regulatory choice for US traders in 2026**

## Scale (as of early 2026)

- ~$52 billion in event contracts outstanding
- ~$4.5 billion monthly trading volume (up from $1B earlier in 2025)
- $867M total volume in 2025 (32× growth from $27M in 2024)

## Markets offered

| Category | Examples |
|----------|---------|
| Economic events | CPI, unemployment, Fed decisions, GDP, jobless claims, housing |
| Politics | Elections, policy outcomes (post-Oct 2024) |
| Crypto | Crypto price ranges, network events |
| Corporate | Earnings surprises, M&A announcements |

## Market structure

- Binary contracts: YES = $1.00, NO = $0.00
- Contracts trade $0.01–$0.99 (= implied probability in cents)
- Tick size: $0.01 increments
- CLOB (Central Limit Order Book), FIFO matching
- Transparent order book

---

## API authentication

Kalshi uses RSA-PSS key pairs. Keys are generated in the Kalshi dashboard under Account & Security > API Keys. **Private key cannot be retrieved after creation — save it immediately.**

**Required headers on every authenticated request:**
```
KALSHI-ACCESS-KEY: <api-key-id>
KALSHI-ACCESS-TIMESTAMP: <unix-timestamp-milliseconds>
KALSHI-ACCESS-SIGNATURE: <base64-encoded RSA-PSS-SHA256 signature>
```

**Signature construction:** sign `timestamp_str + HTTP_METHOD + url_path` (no query params). Use RSA-PSS padding with MGF1(SHA256) and `salt_length=PSS.DIGEST_LENGTH`.

**Environment variable setup:**
```bash
export KALSHI_API_KEY_ID="your-key-id"
export KALSHI_PY_PRIVATE_KEY_PEM="$(cat /path/to/private-key.pem)"
# or: KALSHI_PRIVATE_KEY_PATH=/path/to/private-key.pem
```

**Signature code (if not using SDK):**
```python
import base64, time, hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

def sign_request(method: str, path: str, private_key_pem: str) -> dict:
    ts = str(int(time.time() * 1000))
    message = (ts + method.upper() + path).encode()
    key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
    sig = key.sign(message, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH
    ), hashes.SHA256())
    return {
        "KALSHI-ACCESS-KEY": KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
    }
```

---

## REST API endpoints

### Public (no auth)

```python
import requests

BASE = "https://api.elections.kalshi.com/trade-api/v2"

# List open markets (filter by event series)
markets = requests.get(f"{BASE}/markets", params={
    "status": "open",
    "series_ticker": "KXINFL",  # CPI series
    "limit": 50,
}).json()["markets"]

# Get single market
market = requests.get(f"{BASE}/markets/KXINFL-25JAN").json()["market"]
print(market["yes_bid"], market["yes_ask"], market["volume"])

# Orderbook (YES side; NO side is reciprocal: 100 - yes_price)
book = requests.get(f"{BASE}/markets/KXINFL-25JAN/orderbook").json()["orderbook"]
# book = {"yes": [[price_cents, qty], ...], "no": [[price_cents, qty], ...]}

# OHLC candlesticks
candles = requests.get(f"{BASE}/markets/KXINFL-25JAN/candlesticks", params={
    "start_ts": 1700000000,
    "end_ts":   1710000000,
    "period_interval": 60,  # seconds
}).json()
```

### Authenticated

```python
from kalshi import KalshiClient

client = KalshiClient()  # reads from env vars

# Portfolio balance (amounts in cents)
bal = client.portfolio.get_balance()
available_cents = bal["available"]   # cash available to trade
total_value     = bal["portfolio_value"]

# Current positions
positions = client.portfolio.get_positions()
for pos in positions["market_positions"]:
    print(pos["ticker"], pos["position"], pos["market_exposure"])

# List open orders
orders = client.portfolio.get_orders(status="open")

# Place limit order
order = client.portfolio.place_order(
    ticker="KXINFL-25JAN-B0.03",  # CPI < 0.03% MoM
    action="buy",
    side="yes",
    count=100,           # number of contracts
    yes_price=45,        # 45 cents = 45% implied probability
    time_in_force="good_till_canceled",
    client_order_id="cpi_nowcast_001",  # for deduplication
)

# Amend resting order
client.portfolio.amend_order(
    order_id=order["order_id"],
    count=50,
    yes_price=47,
)

# Cancel
client.portfolio.cancel_order(order_id=order["order_id"])
```

**Order parameters:**
- `action`: `"buy"` or `"sell"`
- `side`: `"yes"` or `"no"`
- `count`: number of contracts (integer)
- `yes_price`: 1–99 (cents); for `side="no"`, pass `no_price` instead
- `time_in_force`: `"fill_or_kill"` | `"immediate_or_cancel"` | `"good_till_canceled"`

---

## WebSocket streaming

For real-time orderbook and price data (required for arbitrage strategies):

```python
import asyncio, json, websockets

async def stream_market(ticker: str, headers: dict):
    ws_url = "wss://api.elections.kalshi.com/trade-api/ws/v2"
    async with websockets.connect(ws_url, extra_headers=headers) as ws:
        # Subscribe to orderbook deltas
        await ws.send(json.dumps({
            "id": 1,
            "cmd": "subscribe",
            "params": {
                "channels": ["orderbook_delta", "ticker"],
                "market_ticker": ticker,
            }
        }))
        async for msg in ws:
            data = json.loads(msg)
            if data.get("type") == "orderbook_delta":
                process_book_update(data["msg"])
            elif data.get("type") == "ticker":
                process_tick(data["msg"])

# Available channels:
# orderbook_delta   — incremental book updates
# ticker            — best bid/ask, last price, volume
# trade             — completed trades
# fill              — your executed fills (auth required)
# market_lifecycle_v2 — market open/close/settle events
# user_orders       — your order state changes (auth required)
```

---

## Fee structure

**Per-contract fee formula:**
- Taker: `round_up(0.07 × C × P × (1 − P))`
- Maker: `round_up(0.0175 × C × P × (1 − P))` — 4× cheaper than taker

Where C = contracts, P = price as decimal (0.45 not 45).

**Fee examples (100 contracts):**

| Price | Taker fee | Maker fee |
|-------|-----------|-----------|
| $0.10 | $0.63 | $0.16 |
| $0.30 | $1.47 | $0.37 |
| $0.50 | $1.75 | $0.44 |
| $0.70 | $1.47 | $0.37 |
| $0.90 | $0.63 | $0.16 |

**Key insight**: Fees peak at $0.50 (maximum uncertainty), are lowest at extreme prices. Strategies trading near-certain outcomes (e.g., CPI between 2.5% and 3.5%) are naturally fee-advantaged. **Prefer limit orders (maker) whenever latency allows.**

---

## Rate limits

| Tier | Read (tokens/sec) | Write (tokens/sec) |
|------|-------------------|-------------------|
| Basic (default) | 200 | 100 |
| Advanced (apply) | 300 | 300 |
| Premier (request) | 1,000 | 1,000 |
| Paragon | 2,000 | 2,000 |
| Prime | 4,000 | 4,000 |

Most calls cost 10 tokens. Order cancellations ~1 token. Rate limited → `429 Too Many Requests` → exponential backoff.

---

## Kalshi Timeless (perpetual contracts)

Launched April 27, 2026. Leveraged perpetual futures on crypto, regulated under CFTC.

- No expiration, continuous funding rate
- Initial assets: Bitcoin and select crypto
- Collateral: USD (stablecoins planned Q2 2026)
- Enables: funding rate arbitrage, longer-horizon positions without contract rollover
- API endpoints follow same REST/WebSocket pattern — check docs.kalshi.com for Timeless-specific routes

---

## Complete algorithmic implementation: CPI nowcasting

End-to-end strategy: build a CPI forecast, trade when model diverges from Kalshi price by >3pp.

```python
import os
import numpy as np
import pandas as pd
from fredapi import Fred
from statsmodels.tsa.arima.model import ARIMA
from scipy.stats import norm
from kalshi import KalshiClient

# ── 1. Pull FRED data ────────────────────────────────────────────────
fred = Fred(api_key=os.environ["FRED_API_KEY"])
cpi_all    = fred.get_series("CPIAUCSL")          # Headline CPI
cpi_core   = fred.get_series("CPILFESL")          # Core CPI
pce_prices = fred.get_series("PCEPI")             # PCE deflator
jobless    = fred.get_series("ICSA")              # Initial claims
adp        = fred.get_series("ADPWNUSNERSA")      # ADP employment

# Month-over-month changes
cpi_mom = cpi_all.pct_change() * 100              # % MoM

# ── 2. ARIMA baseline ────────────────────────────────────────────────
model = ARIMA(cpi_mom.dropna().iloc[-36:], order=(2, 0, 1))
fit = model.fit()
forecast = fit.get_forecast(steps=1)
pred_mean = float(forecast.predicted_mean.iloc[0])
pred_se   = float(forecast.se_mean.iloc[0])

# ── 3. Ensemble with Atlanta Fed GDPNow (proxy: lagged PCE) ──────────
# In production: hit Atlanta Fed's nowcast endpoint directly
# Here: use PCE as a correlated nowcast signal
pce_mom = pce_prices.pct_change().iloc[-1] * 100
ensemble_mean = 0.7 * pred_mean + 0.3 * pce_mom  # simple weighted blend

# ── 4. Convert to probability ─────────────────────────────────────────
threshold = 0.3   # Kalshi contract threshold (e.g., CPI ≥ 0.3% MoM)
prob_above = float(1 - norm.cdf(threshold, loc=ensemble_mean, scale=pred_se))

# ── 5. Fetch Kalshi market price ──────────────────────────────────────
client = KalshiClient()
import requests
BASE = "https://api.elections.kalshi.com/trade-api/v2"
# Find the relevant CPI market (series changes each month — search for open)
mkts = requests.get(f"{BASE}/markets", params={
    "status": "open", "series_ticker": "KXINFL"
}).json()["markets"]
# Pick the contract matching our threshold
market = next((m for m in mkts if "0.3" in m["ticker"]), None)
if not market:
    raise ValueError("Target CPI market not found")
kalshi_prob = market["yes_bid"] / 100   # convert cents to probability

# ── 6. Kelly-sized entry ─────────────────────────────────────────────
def kelly(p: float, market_price: float) -> float:
    """Fraction of bankroll to wager (pre-fee)."""
    if market_price <= 0 or market_price >= 1:
        return 0.0
    M = 1.0 / market_price          # payout multiplier on YES win
    f = (p * M - (1 - p)) / (M - 1)
    return max(0.0, f * 0.25)       # quarter-Kelly for safety

BANKROLL = 10_000   # USD allocated to this strategy
THRESHOLD_EDGE = 0.03

edge = abs(prob_above - kalshi_prob)
if edge >= THRESHOLD_EDGE:
    f = kelly(prob_above, kalshi_prob if prob_above > kalshi_prob else 1 - kalshi_prob)
    usd_bet = BANKROLL * f
    contracts = int(usd_bet / (kalshi_prob if prob_above > kalshi_prob else 1 - kalshi_prob))

    # Fee estimate (taker)
    p_trade = kalshi_prob
    fee_per_contract = round(0.07 * p_trade * (1 - p_trade), 4)
    total_fee = fee_per_contract * contracts
    net_edge_after_fee = edge - (total_fee / contracts)

    if net_edge_after_fee > 0.005 and contracts >= 5:
        side_to_trade = "yes" if prob_above > kalshi_prob else "no"
        print(f"Signal: model={prob_above:.3f}  market={kalshi_prob:.3f}  "
              f"edge={edge:.3f}  fee={total_fee:.2f}  net_edge={net_edge_after_fee:.3f}")
        print(f"Order: {contracts} contracts {side_to_trade.upper()} @ "
              f"{int(kalshi_prob*100) if side_to_trade=='yes' else int((1-kalshi_prob)*100)}¢")

        order = client.portfolio.place_order(
            ticker=market["ticker"],
            action="buy",
            side=side_to_trade,
            count=contracts,
            yes_price=int(kalshi_prob * 100),
            time_in_force="immediate_or_cancel",  # don't queue stale limit orders
        )
        print(f"Submitted: {order['order_id']}  filled={order['filled_count']}")
```

### Realistic performance expectations

- Nowcast models reduce forecast error 20–40% vs. simple historical averages
- Win rate boost: 2–5% over market consensus
- After fees: **3–8% annualized edge** for well-calibrated models
- Peak edge window: **3–6 hours before official data release** when nowcast diverges from stale market

---

## Edge sources

1. **Cross-derivative arbitrage vs. CME Fed funds futures** — when Kalshi and CME price Fed decisions differently
2. **Event nowcasting** — CPI, unemployment using FRED + high-frequency data (see code above)
3. **Sentiment models** — Fed minutes via FinBERT/OpenAI API (keys available in env)
4. **Market microstructure** — order flow, FIFO queue dynamics at tight spreads
5. **Cross-platform arbitrage** — Kalshi vs Polymarket when pricing diverges; requires sub-2s execution

## Liquidity assessment

- Core markets (Fed decisions, CPI, major elections): tight spreads, adequate depth
- Thin markets: exotic outcomes, pre-event inventory reduction by MMs
- Professional participants: Susquehanna, Tower Research, quant funds (competition is real)
- **Suitable for algo strategies under ~$500k notional per market**

## Sandbox

Kalshi provides a demo environment for testing. Use `https://demo-api.kalshi.co/trade-api/v2` with demo credentials before going live. Paper trading works identically — orders execute against real market data but no real money.
