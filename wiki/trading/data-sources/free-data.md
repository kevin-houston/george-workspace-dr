---
updated: 2026-07-24
type: data-source
---

# Free / Low-Cost Data Sources

Comprehensive guide to data sources with no or low ongoing cost. See also [polygon.md](polygon.md) and [alpaca.md](alpaca.md) for the two primary sources in this project.

**Last reviewed: 2026-07-24.** The data landscape shifted substantially in early 2025: IEX Cloud shut down its retail API, Yahoo Finance broke yfinance again, and OpenBB Platform emerged as the best unified free alternative.

---

## OpenBB Platform — recommended unified layer (2026)

**GitHub**: https://github.com/OpenBB-finance/OpenBB (51k+ stars, MIT)  
**Docs**: https://docs.openbb.co/platform  
**PyPI**: `pip install openbb`  
**Latest release**: v4.5 (May 26, 2026)

OpenBB Platform is the most significant development in free quant data tooling since yfinance. It wraps 100+ data providers behind a single standardized API — switching providers is one argument change.

### Architecture

```
openbb.equity.price.historical(symbol="AAPL", provider="yfinance")
openbb.equity.price.historical(symbol="AAPL", provider="polygon")
openbb.equity.price.historical(symbol="AAPL", provider="tiingo")
```

All return the same schema. Provider is pluggable; defaults to whichever you have credentials for.

### Installation and startup

```bash
pip install openbb
# Optional: install provider extensions
pip install openbb-yfinance openbb-polygon openbb-tiingo
```

```python
from openbb import obb

# Historical OHLCV
df = obb.equity.price.historical("AAPL", start_date="2020-01-01", provider="tiingo").to_df()

# ETF data
etf = obb.etf.historical("SPY", provider="yfinance").to_df()

# Earnings calendar
cal = obb.equity.calendar.earnings(start_date="2026-07-20", provider="fmp").to_df()

# Macro (FRED)
gdp = obb.economy.fred_series(symbol="GDP").to_df()

# Options chain
chain = obb.derivatives.options.chains("AAPL", provider="polygon").to_df()
```

### API server mode (useful for MCP integration)

```bash
openbb api --host 127.0.0.1 --port 6900
```

Exposes a FastAPI REST server — compatible with MCP tooling and any HTTP client. Allows routing all data calls through a single service.

### MCP server

```bash
pip install openbb-mcp
openbb-mcp  # starts the MCP server
```

Direct Claude Code / MCP integration available via the `openbb-mcp` package — no extra wiring needed.

### Provider coverage (selected)

| Category | Providers available |
|----------|-------------------|
| EOD prices | Tiingo, Polygon, yfinance, Intrinio, FMP, Alpha Vantage |
| Fundamentals | FMP, SEC/EDGAR, Intrinio, Polygon |
| Options | Polygon, CBOE, Tradier |
| Macro | FRED, World Bank, IMF, OECD |
| News | Benzinga, Polygon, Tiingo, FMP |
| Crypto | CoinGecko, Binance, Kraken |

**Bottom line**: For this project, OpenBB is the preferred abstraction layer. Write once against OpenBB's standard schema; swap providers without code changes when one breaks.

---

## yfinance — EFFECTIVELY DEPRECATED (2026)

- **PyPI**: `pip install yfinance` — current version 1.3.0 (July 2026)
- Not an official API; scrapes Yahoo Finance's internal endpoints
- **Known critical issues (cumulative):**
  - **February 2025**: Yahoo Finance redesigned its data API — broke most yfinance versions; "delisted" errors on all tickers for weeks
  - September 2025: all tickers returned data only through Sep 28, 2025 for several weeks
  - 429 rate limiting / IP blocks under sustained use
  - `yf.download` is not thread-safe (RuntimeError on concurrent calls)
  - Current-day bar missing during market hours
- **Status as of mid-2026**: Multiple sources characterize yfinance as "effectively deprecated" — each maintainer fix is a stopgap until Yahoo's next breaking change. ~109+ open GitHub issues.
- **Disclaimer from library itself**: "designed for educational purposes, users should review Yahoo's ToS"

**Bottom line:** Do not add new yfinance dependencies. Use for quick ad-hoc research only. For automated pipelines and backtesting: Tiingo (free) or Alpaca (free with paper account).

**Drop-in alternative within OpenBB**: `obb.equity.price.historical("AAPL", provider="tiingo")` — same DataFrame output.

---

## IEX Cloud — SHUT DOWN (dead as of 2025)

IEX Cloud announced in 2025 that it was sunsetting its retail stock data API. The endpoint no longer accepts new requests for EOD historical data or fundamentals on the free/paid retail tiers. Do not implement any new code against IEX Cloud. Any existing code referencing `api.iex.cloud` or the `iexfinance` Python package will fail.

**Replacement**: Tiingo (free EOD), Alpaca (free EOD), or OpenBB (provider-agnostic).

---

## Stooq — free historical data, no key required

**URL**: https://stooq.com  
**Python access**: via `pandas-datareader`  
**No API key, no account, no rate limit documentation**

Stooq is a Polish financial data provider that allows free CSV download of decades of historical OHLCV data for stocks, indices, ETFs, and currencies — no authentication required.

```python
import pandas_datareader.data as web
from datetime import datetime

# S&P 500 index (no $ prefix needed)
sp500 = web.DataReader("^SPX", "stooq", start=datetime(2000,1,1), end=datetime(2026,7,24))

# Individual stock
aapl = web.DataReader("AAPL.US", "stooq", start=datetime(2010,1,1), end=datetime(2026,7,24))

# ETF
spy = web.DataReader("SPY.US", "stooq", start=datetime(2000,1,1), end=datetime(2026,7,24))
```

Note: stooq returns data sorted descending; call `.sort_index()` to get chronological order.

### Coverage

| Asset class | Availability |
|-------------|-------------|
| US stocks (daily) | 1990s–present for major names |
| US indices (^SPX, ^DJI, ^NDX) | 1900s–present |
| US ETFs | 2000s–present |
| Forex pairs | Multi-decade |
| Intraday (5-min, 60-min) | Last ~180 days |

**Key limitation**: Ticker naming convention differs (`AAPL.US` not `AAPL`); intraday limited to ~180 days. Not suitable for live trading.

**Use case for this project**: Long-horizon backtesting back-fill when Tiingo free limits are hit. Index data (^SPX) going back to the 1900s is useful for long-run regime analysis.

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

client = TiingoClient({"api_key": "YOUR_KEY"})
df = client.get_dataframe("AAPL", startDate="2000-01-01", columns=["open","high","low","close","volume","adjClose"])
```

**Response fields**: `date`, `open`, `high`, `low`, `close`, `volume`, `adjClose`, `adjHigh`, `adjLow`, `adjOpen`, `adjVolume`, `divCash`, `splitFactor`

**Via OpenBB**: `obb.equity.price.historical("AAPL", provider="tiingo", start_date="2000-01-01")`

**Verdict for this project**: Best free-tier drop-in replacement for yfinance. Same EOD data, 30-year history, more reliable. Get a free API key at tiingo.com.

---

## Alpaca — free with paper account

**URL**: https://alpaca.markets  
**Account required**: Yes (paper account is free)  
**Python**: `pip install alpaca-py`  
**Keys**: `$ALPACA_API_KEY`, `$ALPACA_SECRET` — already in project

### Free data tier (as of 2026)

| Data type | Free limit |
|-----------|------------|
| Historical EOD | **7+ years** of history |
| Historical intraday (1min bars) | 7+ years |
| API rate limit | 10,000 calls/min |
| Real-time quotes (IEX feed) | Yes |

The 10k calls/min rate limit makes Alpaca practical for multi-ticker batch downloads.

```python
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
import datetime

client = StockHistoricalDataClient(api_key, secret_key)

request = StockBarsRequest(
    symbol_or_symbols=["AAPL", "SPY", "GLD"],
    timeframe=TimeFrame.Day,
    start=datetime.datetime(2018, 1, 1),
    end=datetime.datetime(2026, 7, 1),
)
bars = client.get_stock_bars(request).df
```

**Already used in this project** for paper trading execution and monthly rebalancing.

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
- **WIKI** (Quandl Community) — EOD adjusted prices 1995–2018 (frozen; do not use for recent data)
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

**No rate limits, no auth, parses XBRL filings as structured data.** Best free source for fundamentals and the backbone of PEAD signal generation (H163/H174).

---

## Alpha Vantage

- **URL**: https://www.alphavantage.co  
- **Free tier**: **25 API calls/day** — effectively unusable for systematic research
- **Premium**: $50–250/mo; free tier throttle is 5 calls/minute
- **Includes**: OHLCV, 50+ technical indicators, forex, crypto, fundamentals, economic indicators

**Use case**: Sanity-check data or one-off queries only. The 25 req/day free ceiling is binding — a single 25-ticker universe exhausts it in one pass.

**Note**: `$ALPHA_VANTAGE_API_KEY` is in project env, currently used for H168 transcript downloads only. Do not add new systematic usage without upgrading to a paid tier.

---

## Finnhub

- **URL**: https://finnhub.io  
- **Free tier**: 60 calls/min; **20-minute delay** on real-time quotes
- **Coverage**: Stocks, forex, crypto, economic calendar, earnings, company profiles, insider trades, news
- **Python library**: `pip install finnhub-python`

```python
import finnhub

client = finnhub.Client(api_key="YOUR_KEY")
quote = client.quote("AAPL")  # 20-min delayed on free tier
candles = client.stock_candles("AAPL", "D", 1609459200, 1640995200)  # daily OHLCV
```

**60 calls/min free** is substantially better than Alpha Vantage. Useful for historical OHLCV, earnings calendars, and news without a paid subscription. The 20-minute delay makes it unsuitable for live execution signals but fine for end-of-day pipelines.

---

## CBOE Data Shop (options / volatility)

- **URL**: https://datashop.cboe.com
- **Free tier**: VIX history, VIX term structure (free CSV download)
- **Paid**: Full historical options quotes, settlement prices, indices

**Key free datasets:**
- VIX daily history (1990–present): `cboe.com/tradable_products/vix/vix_historical_data/` — direct CSV download, no key
- VIX futures settlement (2004–present)
- S&P 500 daily returns

Already used in this project via yfinance (`^VIX`). CBOE's own CSV is more reliable and doesn't break.

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

## Twelve Data

**Repo**: github.com/twelvedata/twelvedata-python (MIT)  
**Free tier**: 800 calls/day, 8/min; **4-hour delay** on historical data  
**Paid**: Grow $79/mo, Pro $149–229/mo (adds WebSocket + real-time EU), Ultra $329+/mo

Covers OHLC time series, 100+ server-side technical indicators, earnings calendars, fundamentals (income/balance/CF statements), insider transactions, institutional holders, IPO calendars. WebSocket only on Pro+.

**4-hour delay on free tier** means Twelve Data's free tier is not suitable for end-of-day data in a live pipeline (data not available until ~4 PM ET for a 9:30 AM open bar). Fine for historical backtesting with a lag.

**vs current stack**: Overlaps with Polygon (prices) and FMP (fundamentals). Marginal at free tier. Most useful potential: `get_earnings_calendar()` / `get_earnings()` for PEAD event detection. Noted for future evaluation — no account yet.

---

## Recommended stack for this project (updated 2026-07-24)

| Need | Best free source | Notes |
|------|-----------------|-------|
| Historical EOD (daily, 30yr) | **Tiingo** | 30yr free; most reliable; use via OpenBB |
| Historical EOD (daily, 7yr) | **Alpaca** | 10k req/min free; already have account |
| Historical intraday (1min, 7yr) | **Alpaca** | Free with paper account |
| Real-time quotes (free) | **Finnhub** | 60 calls/min; 20-min delay on free |
| Long-run index history (1900s) | **Stooq** | No key; pandas-datareader |
| Options data | **Polygon paid** | No free option for live Greeks |
| Fundamentals / earnings | **EdgarTools** | EDGAR, completely free |
| Macro time series | **FRED** | 800k series, free, key already active |
| News / sentiment | **Finnhub** or NewsAPI | Both have free tiers |
| Unified abstraction layer | **OpenBB Platform** | pip install openbb; swap providers freely |

### Dead / avoid

| Source | Status |
|--------|--------|
| IEX Cloud | **DEAD** — shut down retail API 2025 |
| yfinance | **Effectively deprecated** — use only for one-off research |
| Nasdaq WIKI dataset | Frozen at 2018 — historical only |

**Migration plan from yfinance**: Switch to `obb.equity.price.historical(symbol, provider="tiingo")` — same DataFrame output, 30yr history, same free tier.
