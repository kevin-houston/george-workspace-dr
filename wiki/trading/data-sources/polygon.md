---
updated: 2026-04-24
type: data-source
access: Kevin has free account; API key in OneCLI vault
---

# Polygon.io (now Massive.com)

Rebranded to Massive.com on Oct 30, 2025. APIs and SDKs still work under polygon.io URLs.

- Docs: https://polygon.io/docs
- Python client: `pip install polygon-api-client` (Python 3.9+)
- Community wrapper: `pip install polygon` (simpler API)

## What's available on free tier

- Rate limit: **5 requests/minute**
- Data: End-of-day aggregates, historical OHLCV
- No real-time data
- Sufficient for: backtesting with daily bars, initial strategy research

## Data types (across paid tiers)

| Type | Details |
|------|---------|
| OHLCV | Minute-to-daily bars for stocks, options, forex, crypto, futures, indices |
| Ticks | Real-time and historical trade/quote ticks |
| Options | Trades, quotes, Greeks, IV — full US options market |
| Fundamentals | SEC XBRL filings (10-K, 10-Q, 8-K, etc.) |

## Asset classes

Stocks, options, forex, crypto, futures, indices — broadest coverage of any provider reviewed.

## Pricing

| Tier | Cost | Notes |
|------|------|-------|
| Free | $0 | 5 req/min, EOD only |
| Advanced (stocks) | ~$200/mo | Real-time, higher limits |
| Unlimited | Custom | Enterprise |

## vs Alpaca data

- Free tier: Polygon loses (5 req/min vs Alpaca's 200); Alpaca has 10yr of 1-min free
- Paid: Polygon wins for **options and fundamentals** — Alpaca doesn't offer these
- For equities only: Alpaca is better value
- For options: Polygon is the right choice once we need options data

## Status for this project

Kevin has free account. Use for daily-bar backtesting now. When we move to options strategies, evaluate upgrading to paid tier for options data (Greeks, IV surfaces).
