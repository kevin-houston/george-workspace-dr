---
updated: 2026-04-28
type: data-source
---

# Free / Low-Cost Data Sources

Comprehensive guide to data sources with no or low ongoing cost. See also [polygon.md](polygon.md) and [alpaca.md](alpaca.md) for the two primary sources in this project.

---

## yfinance — current status (2026): fragile, use with care

- **PyPI**: `pip install yfinance` — current version 1.3.0 (April 2026)
- Not an official API; scrapes Yahoo Finance's internal endpoints
- **Known critical issues:**
  - September 2025: all tickers returned data only through Sep 28, 2025 for several weeks
  - February 2025: Yahoo API change broke most versions; "delisted" errors on all tickers
  - 429 rate limiting / IP blocks under sustained use
  - `yf.download` is not thread-safe (RuntimeError on concurrent calls)
  - Current-day bar missing during market hours
- **Status**: ~109 open GitHub issues as of April 2026; each maintainer fix is a stopgap until Yahoo's next change
- **Disclaimer from library itself**: "designed for educational purposes, users should review Yahoo's ToS"

**Bottom line:** Use only for quick ad-hoc research and cached backtesting. Never rely on it for live data or automated pipelines. The breakages are unpredictable.

**Alternative that's more stable**: `yahooquery` — uses Yahoo's official (but still unofficial) endpoints, fewer parsing errors.

---

## Tiingo — best free tier for historical EOD

**URL**: https://api.tiingo.com  
**Account required**: Yes (free)  
**Python library**: `pip install tiingo` or `pip install tiingo[pandas]`

### What's free

| Data type | Free limit |
|-----------|------------|
| EOD OHLCV | 50 symbols/hour; **30+ years** of history |
| Fundamentals | 5 years |
| Intraday (1min, 30min, 1hr) | Paid only |
| Forex | Paid only |
| Crypto | Paid only |
| News | Yes (free tier) |

**30 years of EOD data on the free tier makes Tiingo the best free alternative to yfinance for long-horizon backtesting.**

### Python usage

```python
from tiingo import TiingoClient

config = {"api_key": "YOUR_KEY", "session": True}
client = TiingoClient(config)

# EOD prices (returns list of dicts or pandas DataFrame)
prices = client.get_ticker_price("AAPL",
    startDate="2000-01-01",
    endDate="2024-12-31",
    fmt="json",
    resampleFreq="daily"
)
```

**Pandas DataFrame format:**
```python
from tiingo import TiingoClient
import pandas as pd

client = TiingoClient({"api_key": "YOUR_KEY"})
df = client.get_dataframe("AAPL", startDate="2000-01-01", columns=["open","high","low","close","volume","adjClose"])
```

**Response fields**: `date`, `open`, `high`, `low`, `close`, `volume`, `adjClose`, `adjHigh`, `adjLow`, `adjOpen`, `adjVolume`, `divCash`, `splitFactor`

### WebSocket (paid)
Real-time IEX data via `wss://api.tiingo.com/iex` — requires paid subscription.

**Verdict for this project**: Best free-tier drop-in replacement for yfinance. Same EOD data, 30-year history, more reliable. Get a free API key at tiingo.com.

---

## Nasdaq Data Link (formerly Quandl)

**URL**: https://data.nasdaq.com  
**API docs**: https://docs.data.nasdaq.com/  
**Python library**: `pip install nasdaq-data-link`

### Rate limits (free tier)

| Limit | Value |
|-------|-------|
| Calls per 10 seconds | 300 |
| Calls per 10 minutes | 2,000 |
| Calls per day | 50,000 |
| Concurrent connections | 1 |

### Free datasets

The API itself is free. Many datasets are free:
- **FRED** (Federal Reserve Economic Data) — macro indicators
- **WIKI** (Quandl Community) — EOD adjusted prices 1995–2018 (frozen)
- **Government datasets** — central banks, UN, World Bank, BIS
- **OWD** (Our World in Data) — economic indicators

Premium datasets (paid subscriptions): Zacks fundamentals, Sharadar, FactSet, Bloomberg.

```python
import nasdaqdatalink

nasdaqdatalink.ApiConfig.api_key = "YOUR_KEY"

# Get FRED GDP
gdp = nasdaqdatalink.get("FRED/GDP")

# Get stock fundamentals (Sharadar — paid dataset)
# nasdaqdatalink.get_table("SHARADAR/SF1", ticker="AAPL")
```

**Verdict for this project**: Most useful for macro/economic data (FRED is already available directly via `$FRED_API_KEY`). Limited for stock price data since the free WIKI dataset is frozen at 2018.

---

## EDGAR (SEC filings) — free fundamentals

- **URL**: https://data.sec.gov (no key required)
- **Coverage**: All filings since 1993, 20M+ filings, 800K+ entities
- **Best Python library**: `edgartools` — `pip install edgartools`
- **GitHub**: https://github.com/dgunning/edgartools
- **Docs**: https://edgartools.readthedocs.io/

```python
from edgar import Company

company = Company("AAPL")
filings = company.get_filings(form="10-K")
tenk = filings.latest()
income = tenk.obj()  # structured income statement
```

**Available data**: 10-K/10-Q financial statements (income, balance sheet, cash flow), 8-K events, 13F institutional holdings, insider trades (Form 4), DEF 14A proxy statements.

**No rate limits, no auth, parses XBRL filings as structured data.** Best free source for fundamentals.

---

## Alpha Vantage

- **URL**: https://www.alphavantage.co  
- **Free tier**: **25 API calls/day** (too low for backtesting multiple assets)
- **Premium**: $50–250/mo for higher limits
- **Includes**: OHLCV, 50+ technical indicators, forex, crypto, fundamentals, economic indicators

**Use case**: Sanity-check data or quick one-off queries. 25 calls/day is not usable for systematic research.

---

## Finnhub

- **URL**: https://finnhub.io  
- **Free tier**: Real-time US stocks, 60 calls/min
- **Coverage**: Stocks, forex, crypto, economic calendar, earnings, company profiles, insider trades, news
- **Python library**: `pip install finnhub-python`

```python
import finnhub

client = finnhub.Client(api_key="YOUR_KEY")
quote = client.quote("AAPL")  # real-time price
candles = client.stock_candles("AAPL", "D", 1609459200, 1640995200)  # daily OHLCV
```

**60 calls/min free** is substantially better than Alpha Vantage. Useful for real-time quotes and news without a paid Polygon/Alpaca subscription.

---

## CBOE Data Shop (options / volatility)

- **URL**: https://datashop.cboe.com
- **Free tier**: VIX history, VIX term structure (free download)
- **Paid**: Full historical options quotes, settlement prices, indices

**Key free datasets:**
- VIX daily history (1990–present): `cboe.com/tradable_products/vix/vix_historical_data/` — direct CSV download, no key
- VIX futures settlement (2004–present)
- S&P 500 daily returns

Already used in this project via yfinance (`^VIX`). CBOE's own CSV is more reliable.

---

## Federal Reserve FRED API

- **URL**: https://fred.stlouisfed.org/docs/api/fred/  
- **Key**: `$FRED_API_KEY` — already in this project  
- **Free**: Yes, completely free
- **Python library**: `pip install fredapi`

```python
from fredapi import Fred

fred = Fred(api_key="YOUR_KEY")

# 10Y-2Y Treasury spread (recession indicator)
spread = fred.get_series("T10Y2Y")

# Fed Funds rate
ffr = fred.get_series("FEDFUNDS")

# US CPI
cpi = fred.get_series("CPIAUCSL")
```

**Over 800,000 economic time series.** Already integral to H-series macro regime modeling.

---

## Recommended stack for this project

| Need | Best free source | Notes |
|------|-----------------|-------|
| Historical EOD (daily, long-horizon) | **Tiingo** | 30yr free; more reliable than yfinance |
| Historical EOD (daily, 6yr) | **Alpaca** | 10k req/min free; already have account |
| Historical intraday (1min, 6yr) | **Alpaca** | Free with paper account |
| Real-time quotes (free) | **Finnhub** | 60 calls/min free |
| Options data | **Polygon paid** | No free option for live Greeks |
| Fundamentals / earnings | **EdgarTools** | EDGAR, completely free |
| Macro time series | **FRED** | 800k series, free, key already active |
| News / sentiment | **Finnhub** or NewsAPI | Both have free tiers |

**Migration plan from yfinance**: When yfinance next breaks (likely), switch backtesting data downloads to Tiingo (`tiingo` Python client). Same interface pattern, better reliability, 30yr history covers all H-series IS windows.
