---
updated: 2026-04-24
type: data-source
---

# Free / Low-Cost Data Sources

## EDGAR (SEC filings)

- URL: https://data.sec.gov
- Cost: Free, no API key required
- Coverage: All filings since 1993, 20M+ filings, 800K+ entities
- Use for: Fundamentals, insider trades, 13F institutional holdings, earnings

### Best Python library: EdgarTools

```bash
pip install edgartools
```

- GitHub: https://github.com/dgunning/edgartools
- Docs: https://edgartools.readthedocs.io/
- No rate limits, no auth, parses 10-K/10-Q/8-K as structured data

```python
from edgar import Company
company = Company("AAPL")
filings = company.get_filings(form="10-K")
```

## yfinance — avoid for production

- Not an official API; scrapes Yahoo Finance
- Increasingly unreliable: 429 errors, IP blocks, layout changes break it
- Use only for quick ad-hoc lookups, never in production
- Alternative: `yahooquery` (uses official endpoints, more stable)

## Alpha Vantage

- Free tier: 25 calls/day (too low for backtesting)
- Includes: OHLCV, 50+ technical indicators, forex, crypto, fundamentals
- Useful as a sanity-check source, not primary

## Finnhub

- Free: Real-time stocks, forex, crypto, economic calendar, fundamentals
- Higher throughput than Alpha Vantage on free tier
- https://finnhub.io

## Summary: recommended stack for this project

| Need | Source |
|------|--------|
| Historical OHLCV (daily) | Polygon.io (free tier) or Alpaca |
| Historical OHLCV (minute) | Alpaca (10yr free) |
| Options data | Polygon.io (paid when needed) |
| Fundamentals / earnings | EdgarTools (EDGAR, free) |
| Quick testing | Alpha Vantage or Finnhub |
