---
updated: 2026-04-28
type: data-source
access: Kevin has free account; API key in OneCLI vault
---

# Polygon.io (now Massive.com)

Rebranded to Massive.com on October 30, 2025. APIs and SDKs still work under polygon.io URLs and api.polygon.io. The service is unchanged — just new branding.

- **Docs**: https://polygon.io/docs
- **Python client**: `pip install polygon-api-client` (Python 3.9+)
- **Official rebranded client**: `pip install massive` (from massive-com/client-python on GitHub)
- **MCP server**: Available in this project via `$MASSIVE_KEY` — use for interactive queries

---

## Pricing tiers

| Tier | Cost | Rate Limit | Historical | Real-time |
|------|------|------------|-----------|-----------|
| **Free** | $0 | 5 req/min | 2 years EOD | No |
| **Stocks Starter** | $29/mo | Unlimited | 5 years | No |
| **Stocks Advanced** | ~$200/mo | Unlimited | Full | Yes (WebSocket) |
| **Options** | Add-on | — | Full | Yes |
| **Enterprise** | Custom | Unlimited | Full | Full tick |

Free tier is sufficient for daily-bar backtesting with short lookbacks. For the H-series strategies (2004–present), need either Alpaca (10yr free) or Polygon paid.

---

## Asset classes covered

Broadest coverage of any reviewed provider:
- US equities (stocks, ETFs, ADRs)
- US options (OHLCV, Greeks, IV, full options chain)
- Forex (FX spot pairs)
- Crypto (BTC, ETH, all major pairs)
- Futures (limited)
- US indices (SPX, NDX, etc.)

---

## Core REST endpoints

### Aggregates (bars) — most used

```
GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
```

**Parameters:**
- `ticker`: Stock symbol (case-sensitive: "AAPL" not "aapl")
- `multiplier`: Integer — number of timespan units per bar
- `timespan`: `minute`, `hour`, `day`, `week`, `month`, `quarter`, `year`
- `from` / `to`: `YYYY-MM-DD` or Unix milliseconds
- `adjusted`: `true` (default) — applies splits/dividends
- `sort`: `asc` or `desc`
- `limit`: Max 50,000 per request (default 5,000)

**Response fields:**
```json
{
  "ticker": "AAPL",
  "queryCount": 2,
  "resultsCount": 2,
  "adjusted": true,
  "results": [
    {
      "o": 175.20,    // open
      "h": 178.50,    // high
      "l": 174.80,    // low
      "c": 177.30,    // close
      "v": 45123000,  // volume
      "vw": 176.85,   // VWAP
      "t": 1704067200000,  // timestamp (Unix ms)
      "n": 89432      // transaction count
    }
  ]
}
```

**Python example:**
```python
from polygon import RESTClient

client = RESTClient(api_key="YOUR_KEY")  # or set POLYGON_API_KEY env var

# Get daily OHLCV for AAPL
bars = client.get_aggs("AAPL", 1, "day", "2024-01-01", "2024-12-31", adjusted=True)
for bar in bars:
    print(bar.open, bar.high, bar.low, bar.close, bar.volume, bar.timestamp)
```

### Ticker details

```
GET /v3/reference/tickers/{ticker}
```
Returns: name, market, exchange, primary_exchange, type, active status, CIK, composite FIGI, share class FIGI, currency, SIC code, address, phone, description.

### Options contracts reference

```
GET /v3/reference/options/contracts?underlying_ticker=AAPL&contract_type=call&limit=100
```
Returns full options chain with strikes, expiration dates, Greeks.

### News / headlines

```
GET /v2/reference/news?ticker=AAPL&limit=10
```
Returns article title, author, publisher, URL, published timestamp, tickers mentioned.

---

## WebSocket real-time feeds (paid tiers)

**Endpoint**: `wss://socket.polygon.io/stocks`

**Authentication:**
```json
{"action": "auth", "params": "YOUR_API_KEY"}
```

**Subscribe to NBBO quotes:**
```json
{"action": "subscribe", "params": "Q.AAPL"}
```

**Subscribe to all trades:**
```json
{"action": "subscribe", "params": "T.*"}
```

**Message types:**
- `T.*` — trade ticks (price, size, conditions, exchange)
- `Q.*` — NBBO quotes (bid/ask price and size)
- `A.*` — per-second aggregate bars
- `AM.*` — per-minute aggregate bars

**Python WebSocket example:**
```python
from polygon import WebSocketClient
from polygon.websocket.models import WebSocketMessage

def handle_msg(msgs: list[WebSocketMessage]):
    for m in msgs:
        print(m)

ws = WebSocketClient(api_key="YOUR_KEY", feed="stocks", market="stocks")
ws.run(handle_msg, subscriptions=["T.AAPL", "Q.AAPL"])
```

---

## vs Alpaca data (free tier comparison)

| | Polygon Free | Alpaca Free |
|--|-------------|------------|
| Rate limit | 5 req/min | 10,000 req/min |
| Historical depth | 2 years EOD | 6+ years |
| Bar frequency | Daily only | 1-min, hourly, daily |
| Real-time | No | IEX only |
| Options data | Yes (via paid) | No |
| Asset classes | Equities+options+FX+crypto | Equities only |
| API key cost | Free | Free (Alpaca account) |

**Conclusion:** For equities-only backtesting, Alpaca's free tier is significantly better. Polygon becomes relevant when you need options data (Greeks, IV surface) or multi-asset (FX, crypto alongside equities).

---

## vs yfinance (backtesting)

| | Polygon | yfinance |
|--|---------|---------|
| Reliability | Production-grade | Fragile (unofficial API) |
| Rate limit | 5 req/min free | Unofficial, blocks frequently |
| Historical depth | 2yr free / 5yr paid | ~7 years (when working) |
| Splits/divs adjusted | Yes, explicit control | Yes |
| Options | Yes (paid) | Partial (unreliable) |
| Status | Stable, supported | Breaking changes ~quarterly |

---

## Current usage in this project

Kevin has free-tier key available as `$POLYGON_API_KEY` and via the Massive MCP server. For the H-series daily-bar backtesting, yfinance has been used as fallback (free, no rate limit concern for cached data). Polygon would be the upgrade path if yfinance reliability degrades further.

**When to upgrade to paid Polygon:**
- Moving to live options strategies (need Greeks, IV surface)
- Need intraday bars for IBS strategy live execution
- yfinance breaks and Alpaca historical doesn't cover needed assets
