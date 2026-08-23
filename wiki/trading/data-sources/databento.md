---
updated: 2026-08-23
type: data-source
access: no account yet — reference only, not adopted
---

# Databento — Institutional-Grade Market Data API

Direct-from-exchange market data provider. First surfaced in this wiki only as a
passing mention in `tools/nautilus-trader.md` (listed as a supported data adapter
alongside Tardis and Blockchain feeds) — no dedicated evaluation existed until now.

- **Site**: https://databento.com
- **Docs / pricing**: https://databento.com/pricing
- **Python client**: `pip install -U databento` (Python 3.8+)
- **Also ships**: Rust and C++ client libraries
- **NautilusTrader integration**: native adapter, confirmed in `tools/nautilus-trader.md`

---

## What it is, in one line

Databento sells **direct exchange/prop feeds** (not consolidated SIP data) — the same
class of raw tick-level order-book data institutional HFT/quant desks buy, packaged
behind a modern API with usage-based pricing instead of the traditional
six-figure-minimum data-vendor contract.

---

## Coverage

| Asset class | Venues | Depth |
|---|---|---|
| US equities | 50+ venues: Nasdaq (Nasdaq/PSX/Texas), NYSE (NYSE/American/Arca/National/Texas), Cboe BZX/BYX/EDGA/EDGX, MEMX, MIAX, IEX, Blue Ocean ATS, FINRA TRFs | Since 2018, 20,000+ symbols, "19 PB" total coverage |
| Futures/options (CME complex) | CME, CBOT, NYMEX, COMEX (GLBX.MDP3 dataset) | 16+ years, 650,000+ symbols |

Schemas available: `mbo` (market-by-order, full L3 book), `mbp-10` (L2 depth),
`mbp-1` (L1 top-of-book), `trades` (tick-by-tick with aggressor side), `ohlcv-t`
(aggregated bars), `imbalance` (auction data). Notably includes **odd-lot trades**
(~50% of US equity trading activity) which consolidated SIP feeds and most retail
APIs (Polygon, Alpaca, yfinance) drop or aggregate away — relevant if a future
hypothesis ever needs true microstructure fidelity rather than SIP-derived bars.

---

## Pricing

| Tier | Cost | Notes |
|---|---|---|
| **Usage-based (pay-as-you-go)** | From **$0.40/GB** (equities), no subscription | Billed on uncompressed binary size; batch downloads free to re-fetch for 30 days |
| **Standard subscription** | $199/mo | Live data + 16yr L0 history, 1yr L1, 1mo L2/L3 |
| **Plus** | $1,750/mo (annual contract) | 16yr L1 history, external distribution rights, dedicated account manager |
| **Unlimited** | $4,500/mo (annual contract) | Full history, all schemas |
| **Free trial** | **$125 in credits**, expires 6 months after signup, one set per team | Usable against historical data |

For live streaming, license fees are pass-through per-exchange (CME/Nasdaq/etc.
charge their own data fees on top of Databento's platform fee) — this is standard
for direct exchange feeds and is why the entry price is much higher than Polygon's
consumer tiers.

---

## Python usage example

```python
import databento as db

client = db.Historical("YOUR_API_KEY")

data = client.timeseries.get_range(
    dataset="GLBX.MDP3",       # exchange venue identifier, e.g. CME Globex
    symbols="ESH4",            # up to 2,000 symbols per request, or 'ALL_SYMBOLS'
    schema="trades",           # trades | mbo | mbp-1 | mbp-10 | ohlcv-t | imbalance
    start="2024-02-12",        # UTC, inclusive
    end="2024-02-17",          # UTC, exclusive
)

df = data.to_df()
```

Delivers "over a million rows/sec" into pandas per the vendor's own benchmark
(not independently verified here) — the interesting part for us is the nanosecond
time-range addressing, which removes the day-boundary bucketing headaches common
in free EOD APIs.

---

## Databento vs. Polygon/Massive vs. Alpaca (for our pipeline)

| | Databento | Polygon/Massive (`data-sources/polygon.md`) | Alpaca (`data-sources/alpaca.md`) |
|---|---|---|---|
| Data type | Direct exchange feeds (L1-L3) | Consolidated/SIP-derived | Consolidated + IEX |
| Entry cost | $125 free credit, then $0.40/GB or $199/mo | Free tier (5 req/min, 2yr EOD) | Free (10yr history) |
| Odd lots | Included | No | No |
| Options | CME options only (GLBX) | Full US options chain, Greeks, IV | Multi-leg options orders |
| Best fit here | Tick-level microstructure research, NautilusTrader crypto/futures POC | Daily-bar backtesting at scale, options chain data | Paper/live equities+options execution, free long history |

**Verdict**: overkill for the current daily/monthly-rebalance H-series strategies —
none of them need L2/L3 order-book depth, and Polygon/Alpaca's free tiers already
cover the daily-bar use case at zero cost. Relevant narrowly for two open threads:
(1) **H276 crypto POC** and any future NautilusTrader live-execution work, where
Databento is a first-class supported adapter; (2) if a market-microstructure
hypothesis (in the vein of `algorithms/market-microstructure.md`'s OFI/Amihud work)
ever needs genuine order-book-level data instead of OHLCV proxies, Databento's
$125 free credit is enough to pull a few weeks of `mbp-10` data for a pilot before
committing to a paid tier.

---

## Sources

- https://databento.com/pricing
- https://databento.com/equities
- https://databento.com/blog/api-demo-python
