---
title: Crypto Market Data Sources
added: 2026-06-08
category: data-sources
---

# Crypto Market Data Sources

Reference for obtaining historical and live crypto OHLCV data for backtesting and live trading. Covers free-tier options suitable for the current setup (yfinance → ccxt/CoinGecko migration path as yfinance reliability degrades).

## TL;DR for Monthly Momentum Backtests

| Source | Free? | History | Reliability | Best For |
|--------|-------|---------|-------------|----------|
| yfinance | Yes | BTC 2015, ETH 2015, SOL 2020 | Fragile (109+ open issues) | Current backtest code — works now |
| CoinGecko | Yes (500-1k calls/day) | BTC 2013, ETH 2015, SOL 2020 | Stable | Drop-in yfinance fallback |
| ccxt + Kraken | Yes (public) | BTC 2013 | Production-grade | Live trading + backtest sync |
| Binance public | Yes (1200 req/min) | 2017+ | Stable | High-frequency, bulk downloads |
| CryptoCompare | Yes (100k calls/day) | BTC 2013 | Good | Daily data at scale |

---

## 1. yfinance (current)

**Tickers and history depth:**
- `BTC-USD`: 2015-01-01+
- `ETH-USD`: 2015-08-01+
- `SOL-USD`: **2020-08-11+** — critical constraint for IS periods
- `BNB-USD`: 2017-07-01+
- `ADA-USD`: 2017-10-01+

**Known issues:**
- Sep 2025: all tickers had data cutoff at Sep 28
- Feb 2025: major API breakage from Yahoo endpoint changes
- 429 rate limiting on rapid multi-ticker downloads
- Not thread-safe (RuntimeError on concurrent calls)
- ~109 open GitHub issues; expect intermittent breakage

**Current pattern (H264):**
```python
import yfinance as yf
_dl = yf.download(["BTC-USD", "ETH-USD", "SOL-USD"], start="2017-01-01",
                  auto_adjust=True, progress=False)
raw = _dl.xs("Close", axis=1, level=0)
monthly = raw.resample("ME").last()
```

`auto_adjust=True` is safe (crypto has no splits/dividends — adjusted = unadjusted).

---

## 2. CoinGecko API (recommended fallback)

**Free tier:** ~500–1,000 calls/day; no API key required for public endpoints.

**Key endpoints:**
- `/coins/{id}/ohlc` → `[timestamp_ms, open, high, low, close]` (no volume)
- `/coins/{id}/market_chart` → `{prices, market_caps, total_volumes}` over time

**Coin IDs:** `bitcoin`, `ethereum`, `solana`, `binancecoin`, `cardano`

**History depth:** Bitcoin from 2013, Ethereum from 2015, Solana from 2020.

**Python library:**
```bash
pip install pycoingecko
```

```python
from pycoingecko import CoinGecko
import pandas as pd

cg = CoinGecko()
# Returns [[timestamp_ms, o, h, l, c], ...]
ohlc = cg.get_coin_ohlc_by_id('bitcoin', vs_currency='usd', days='max')
df = pd.DataFrame(ohlc, columns=['ts','open','high','low','close'])
df['date'] = pd.to_datetime(df['ts'], unit='ms')
df = df.set_index('date').sort_index()
```

**Gotchas:**
- Timestamps in milliseconds (divide by 1000 or use `unit='ms'`)
- `/ohlc` has no volume; use `/market_chart` if volume needed
- Data aggregated from multiple exchanges (not single-source)
- Add `time.sleep(0.1)` between calls for multiple coins

---

## 3. ccxt (unified exchange library)

**What it is:** Unified Python/JS/Go API for 107+ exchanges (Binance, Kraken, Coinbase, OKX, Bybit, etc.). Handles rate limiting, pagination, normalization automatically.

```bash
pip install ccxt
```

**Normalized OHLCV format:** `[timestamp_ms, open, high, low, close, volume]`

**Basic fetch:**
```python
import ccxt, pandas as pd

exchange = ccxt.kraken()  # or ccxt.binance()
ohlcv = exchange.fetch_ohlcv('BTC/USD', timeframe='1d', limit=500)
df = pd.DataFrame(ohlcv, columns=['ts','open','high','low','close','volume'])
df['date'] = pd.to_datetime(df['ts'], unit='ms')
df = df.set_index('date')
```

**Full historical fetch (paginated):**
```python
since = exchange.parse8601('2015-01-01T00:00:00Z')
all_bars = []
while since < exchange.milliseconds():
    bars = exchange.fetch_ohlcv('BTC/USD', '1d', since=since, limit=1000)
    if not bars:
        break
    all_bars.extend(bars)
    since = bars[-1][0] + 1
```

**Per-exchange comparison:**

| Exchange | Rate limit | History depth | Pair naming |
|----------|-----------|---------------|-------------|
| Kraken | 15 req/sec | 2013+ | `BTC/USD` |
| Binance | 1200 req/min | 2017+ | `BTC/USDT` |
| Coinbase | 10 req/sec | 2014+ | `BTC-USD` |

**For live trading sync:** Use `ccxt.kraken()` — consistent with Kraken CLI and Kraken MCP tools already in setup.

---

## 4. Binance Public REST API

No authentication required for public OHLCV data.

**Endpoint:** `GET https://api.binance.com/api/v3/klines`  
**Params:** `symbol=BTCUSDT`, `interval=1d`, `startTime`, `endTime`, `limit` (max 1000)

**Bulk historical downloads (free CSV):** https://data.binance.vision/  
→ Organized by pair/interval, full history from 2017, no API calls needed.

```python
from binance.client import Client
client = Client()  # No API key for public data
klines = client.get_historical_klines('BTCUSDT', Client.KLINE_INTERVAL_1DAY,
                                      '2017-01-01', '2025-12-31')
# [[openTime, o, h, l, c, v, closeTime, quoteVol, trades, ...], ...]
```

**Gotcha:** Binance history starts 2017-07-01 for BTC/USDT — no pre-2017 coverage.

---

## 5. CryptoCompare

**Free tier:** 100,000 calls/day (~67/min average). No auth required.

**Endpoint:** `GET https://min-api.cryptocompare.com/data/v2/histoday`  
**Params:** `fsym=BTC`, `tsym=USD`, `limit=2000`, `toTs={unix_timestamp}`

**History:** Bitcoin from 2013, Ethereum from 2015. Paginate via `toTs` parameter.

**Vs CoinGecko:** Higher daily cap (100k vs ~1k) but less convenient Python library. CoinGecko preferred for monthly backtests.

---

## Kraken-Specific: Asset Code Mapping

Kraken uses legacy asset codes. Mapping for common tokens:

| Human name | Kraken REST | ccxt symbol | yfinance |
|------------|-------------|-------------|----------|
| Bitcoin | XXBTZUSD | BTC/USD | BTC-USD |
| Ethereum | XETHZUSD | ETH/USD | ETH-USD |
| Solana | SOLUSDT | SOL/USD | SOL-USD |
| BNB | BNBUSD | BNB/USD | BNB-USD |
| Cardano | ADAUSD | ADA/USD | ADA-USD |

---

## Backtesting Gotchas

**Survivorship bias:** Crypto has extreme survivorship — hundreds of tokens listed then delisted. For top-5 major coins (BTC/ETH/SOL/BNB/ADA), this is less severe but still present for lower-cap coins.

**Exchange-specific prices:** BTC/USD price differs across Kraken, Binance, Coinbase. For consistency within a single backtest, use one source. yfinance aggregates Yahoo's feed (typically close to Coinbase pricing).

**SOL availability:** SOL mainnet launched March 2020, exchange listings by August 2020. No reliable pre-2020 SOL data exists on any source — not a data quality issue, simply the launch date.

**Adjusted close:** Crypto has no corporate actions (splits, dividends). `close == adjusted_close` always. No need for adjustment.

**Volume units:** Most sources report volume in the base currency (BTC quantity, not USD notional). For USD volume, use `volume * close` or fetch `quoteVolume` separately.

---

## Recommended Migration Path

Current state: yfinance works but is fragile.

**Phase 1 (now):** Keep yfinance for backtests; add a CoinGecko cache builder:
```python
# run once to build parquet cache
from pycoingecko import CoinGecko
import pandas as pd, time

COINS = {'BTC-USD': 'bitcoin', 'ETH-USD': 'ethereum', 
         'SOL-USD': 'solana', 'BNB-USD': 'binancecoin', 'ADA-USD': 'cardano'}
cg = CoinGecko()
frames = {}
for ticker, cg_id in COINS.items():
    ohlc = cg.get_coin_ohlc_by_id(cg_id, vs_currency='usd', days='max')
    df = pd.DataFrame(ohlc, columns=['ts','open','high','low','close'])
    df['date'] = pd.to_datetime(df['ts'], unit='ms')
    frames[ticker] = df.set_index('date')['close']
    time.sleep(1.0)
pd.DataFrame(frames).to_parquet('crypto_monthly_close.parquet')
```

**Phase 2 (H264b / live):** Switch to `ccxt.kraken()` for both backtest data and live execution — single source eliminates data/execution discrepancy.

---

## Related Pages

| [Free / Low-Cost Data Sources](free-data.md) | [Kraken CLI](../tools/kraken-cli.md) | [H264 Crypto Momentum](../backtesting/hypothesis-log.md) |
