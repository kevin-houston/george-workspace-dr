---
updated: 2026-05-01
---

# Options Data Sources

Backtesting options strategies requires historical contracts data with Greeks and IV. No truly free source exists for production-grade backtesting. This page covers data providers, their APIs, and the open-source libraries to process the data.

---

## Source Comparison

| Provider | Price/mo | Historical | Greeks | Best For |
|----------|----------|------------|--------|----------|
| ThetaData | $80 (Standard) | 2005+ tick-level | Must compute | Cheap historical bulk backtesting |
| ORATS | $99 (trial) | 2007+ EOD (25yr) | Pre-computed, 98 indicators | IV surface research, historical backtesting |
| FlashAlpha | Free / $79 / $299 | 2018+ minute | Pre-computed GEX/DEX/VEX | Dealer positioning, gamma exposure analytics |
| Polygon.io / Massive | $29 + $79 options | 2014+ tick | Current snapshot only | Live scanning, tick-level trade data |
| Tradier | $10 / free w/ acct | Real-time only | Yes, live | Simple broker-attached API, retail traders |
| Alpaca | Free (indicative) | 2024+ bars | Yes, in snapshots | Live trading integration; not backtesting |
| QuantConnect | Free (10 BT/day) | ~2010+ minute | Daily snapshots | LEAN backtesting without separate data cost |

**No historical Greeks for free.** Every provider gives current IV/Greeks in snapshots. For historical chain replay with Greeks, the minimum cost is ~$80/mo (ThetaData) and you compute Greeks yourself, or ~$99/mo for pre-computed (ORATS).

---

## Polygon.io / Massive — API Reference

Polygon.io (rebranded as Massive) provides options data via REST, WebSocket, SQL, and S3 flat files. Options data requires the options add-on ($79/mo) on top of the base plan ($29/mo).

### Key REST Endpoints

```
# Contract reference (metadata, multiplier, exercise style)
GET /v3/reference/options/contracts
    ?underlying_ticker=SPY
    &contract_type=call
    &expiration_date.gte=2026-05-01
    &expiration_date.lte=2026-06-30
    &strike_price.gte=490
    &strike_price.lte=530

# Snapshot — full chain with Greeks and IV
GET /v2/snapshot/options/{underlyingAsset}
    ?limit=250&apiKey=...
    # returns: delta, gamma, theta, vega, IV, OI, day bars, bid/ask per contract

# Single contract snapshot
GET /v3/snapshot/options/{underlyingAsset}/{optionContractTicker}

# Historical trades (tick-level)
GET /v3/trades/options/{optionsTicker}
    ?timestamp.gte=2026-05-01&limit=50000

# Aggregate bars (OHLCV)
GET /v2/aggs/ticker/{optionsTicker}/range/{multiplier}/{timespan}/{from}/{to}
    # timespan: minute, hour, day
```

### Python SDK (polygon-api-client)

```python
from polygon import RESTClient, build_option_symbol, OptionsClient

client = RESTClient("YOUR_KEY")

# Build OCC symbol: SPY 2026-06-20 C 520.00
sym = build_option_symbol("SPY", "260620", "call", 520.0)
# → "SPY260620C00520000"

# Snapshot — Greeks + IV for full SPY chain
for snap in client.list_snapshot_options_chain("SPY", limit=250):
    print(snap.details.strike_price, snap.greeks.delta, snap.implied_volatility)

# Option aggregate bars
oc = OptionsClient("YOUR_KEY")
bars = oc.get_aggregate_bars("O:SPY260620C00520000",
                              "2026-01-01", "2026-05-01",
                              timespan="day", multiplier=1)
```

**Free tier limit**: 5 calls/min; no options chain history. Historical Greeks are current-snapshot only — you cannot replay the chain at a past date without tick reconstruction.

---

## Alpaca — Options Data

Alpaca provides options data free on the `indicative` feed (delayed, modified quotes) or OPRA feed (requires paid subscription for real-time).

### REST: Option Chain Snapshot

```python
import requests, os

BASE = "https://data.alpaca.markets/v1beta1"
HEADERS = {
    "APCA-API-KEY-ID":     os.environ["ALPACA_API_KEY"],
    "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"],
}

def get_option_chain(underlying, feed="indicative", contract_type=None,
                     exp_date=None, strike_gte=None, strike_lte=None):
    params = {"feed": feed, "limit": 1000}
    if contract_type: params["type"] = contract_type      # "call" or "put"
    if exp_date:      params["expiration_date"] = exp_date
    if strike_gte:    params["strike_price_gte"] = strike_gte
    if strike_lte:    params["strike_price_lte"] = strike_lte

    url  = f"{BASE}/options/snapshots/{underlying}"
    snap = {}
    while True:
        r = requests.get(url, headers=HEADERS, params=params).json()
        snap.update(r.get("snapshots", {}))
        next_tok = r.get("next_page_token")
        if not next_tok: break
        params["page_token"] = next_tok
    return snap

chain = get_option_chain("SPY", exp_date="2026-06-20",
                          strike_gte=490, strike_lte=540)
# Each entry has: latestTrade, latestQuote, greeks (delta/gamma/theta/vega/rho), impliedVolatility
```

**Response Greeks fields**: `delta`, `gamma`, `theta`, `vega`, `rho` (when available). Greeks come from the `indicative` feed model — not OPRA-sourced; treat as approximate for live scanning, not definitive.

### WebSocket: Real-time Options Stream

WebSocket endpoint: `wss://stream.data.alpaca.markets/v1beta1/{feed}`  
Feed: `indicative` (free) or `opra` (paid). **Options WS is msgpack-only** — set `Content-Type: application/msgpack`.

```python
import asyncio, msgpack, websockets, json, os

async def stream_options():
    uri = "wss://stream.data.alpaca.markets/v1beta1/indicative"
    async with websockets.connect(uri) as ws:
        # Auth
        await ws.send(msgpack.packb({"action": "auth",
            "key": os.environ["ALPACA_API_KEY"],
            "secret": os.environ["ALPACA_SECRET"]}))
        await ws.recv()

        # Subscribe — trades only (cannot subscribe to * for quotes)
        await ws.send(msgpack.packb({"action": "subscribe",
            "trades": ["SPY260620C00520000"],
            "quotes": ["SPY260620C00520000"]}))

        async for msg in ws:
            data = msgpack.unpackb(msg)
            for event in data:
                t = event.get("T")
                if t == "t":   # trade
                    print("trade:", event["S"], event["p"], event["s"])
                elif t == "q": # quote
                    print("quote:", event["S"], event["bp"], event["ap"])

asyncio.run(stream_options())
```

**Caveat**: Cannot wildcard-subscribe to quotes (`*`) due to volume. Subscribe per-contract. Greeks are not streamed — only trades and quotes. Compute Greeks from quote mid-price using `py_vollib` or `vollib`.

### Historical Bars

```python
# Historical options OHLCV bars (available from ~Feb 2024 only)
r = requests.get(
    f"{BASE}/options/bars/SPY260620C00520000",
    headers=HEADERS,
    params={"timeframe": "1Day", "start": "2026-01-01", "end": "2026-05-01"}
)
bars = r.json()["bars"]
```

---

## ThetaData — Bulk Historical

ThetaData is the best budget option for historical backtesting. It runs a local Java terminal process as a proxy — all API calls hit `http://127.0.0.1:25510`.

### Setup

```bash
# Download and run the terminal (requires Java 11+)
java -jar ThetaTerminal.jar YOUR_USERNAME YOUR_PASSWORD

# Install Python HTTP client
pip install httpx
```

### Python Examples (v2 REST)

```python
import httpx, io, csv

BASE = "http://127.0.0.1:25510/v2"

def get_bulk_snapshot(root: str, exp: str = "0"):
    """Fetch full chain OHLC snapshot. exp='0' = all expirations."""
    params = {"root": root, "exp": exp, "use_csv": "true"}
    rows = []
    url = f"{BASE}/bulk_snapshot/option/ohlc"
    while url:
        r = httpx.get(url, params=params, timeout=60)
        reader = csv.reader(io.StringIO(r.text))
        rows.extend(list(reader))
        url = r.headers.get("Next-Page")  # pagination
        params = {}  # next-page url is fully qualified
    return rows

def get_hist_eod(root: str, exp: str, right: str, strike: int,
                 start: str, end: str):
    """Historical EOD OHLC for a single contract."""
    # strike in integer cents: 520.00 → 52000000 (ThetaData internal format)
    r = httpx.get(f"{BASE}/hist/option/ohlc", params={
        "root": root, "exp": exp, "right": right,
        "strike": strike, "start_date": start, "end_date": end,
        "use_csv": "true"
    })
    return list(csv.reader(io.StringIO(r.text)))

def get_hist_greeks(root: str, exp: str, right: str, strike: int,
                    start: str, end: str):
    """Historical EOD Greeks (delta/gamma/theta/vega/IV). Standard tier+."""
    r = httpx.get(f"{BASE}/hist/option/greeks", params={
        "root": root, "exp": exp, "right": right,
        "strike": strike, "start_date": start, "end_date": end,
        "use_csv": "true"
    })
    return list(csv.reader(io.StringIO(r.text)))
```

**Tier note**: Standard tier ($80/mo) gives full historical chain + Greeks. Free tier gives very limited access. Greeks are pre-computed EOD by ThetaData.

---

## Open-Source Analytics Libraries

These libraries compute IV, Greeks, and option prices client-side from price + market data.

### vollib / py_vollib (Recommended — Fastest)

```bash
pip install vollib           # base (Python 3.9–3.12)
pip install py_vollib        # same + faster LetsBeRational IV solver
pip install py_vollib_vectorized  # numpy-vectorized: 1M+ calculations/sec
```

```python
from py_vollib.black_scholes import black_scholes as bs
from py_vollib.black_scholes.implied_volatility import implied_volatility as bsiv
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho

flag = "c"    # "c" call, "p" put
S    = 525.0  # spot
K    = 520.0  # strike
t    = 30/365 # time to expiry in years
r    = 0.053  # risk-free rate (fed funds)
sigma= 0.18   # known vol (for pricing)

price = bs(flag, S, K, t, r, sigma)
iv    = bsiv(price, S, K, t, r, flag)   # recover sigma from market price
d     = delta(flag, S, K, t, r, sigma)
g     = gamma(flag, S, K, t, r, sigma)
th    = theta(flag, S, K, t, r, sigma)  # per calendar day
v     = vega(flag, S, K, t, r, sigma)   # per 1% move in vol

# Vectorized batch (py_vollib_vectorized)
import numpy as np
from py_vollib_vectorized import price_dataframe
import pandas as pd

df = pd.DataFrame({"flag":["c","p"], "S":[525,525], "K":[520,530],
                   "t":[30/365,30/365], "r":[0.053,0.053], "sigma":[0.18,0.20]})
result = price_dataframe(df, flag_col="flag", underlying_col="S",
                          strike_col="K", annualized_tte_col="t",
                          riskfree_col="r", sigma_col="sigma",
                          model="black_scholes", inplace=False)
# Adds: price, delta, gamma, theta, vega, rho columns
```

### QuantLib-Python (Full-Featured, Slower)

Best for: term structure modeling, American options (binomial/FD), SABR/Heston calibration.

```bash
pip install QuantLib
```

```python
import QuantLib as ql

today = ql.Date(1, 5, 2026)
ql.Settings.instance().evaluationDate = today

S    = ql.SimpleQuote(525.0)
r    = ql.SimpleQuote(0.053)
q    = ql.SimpleQuote(0.015)   # dividend yield
vol  = ql.SimpleQuote(0.18)

rf_ts  = ql.FlatForward(today, ql.QuoteHandle(r), ql.Actual365Fixed())
div_ts = ql.FlatForward(today, ql.QuoteHandle(q), ql.Actual365Fixed())
vol_ts = ql.BlackConstantVol(today, ql.NullCalendar(), ql.QuoteHandle(vol), ql.Actual365Fixed())

process = ql.BlackScholesMertonProcess(
    ql.QuoteHandle(S),
    ql.YieldTermStructureHandle(div_ts),
    ql.YieldTermStructureHandle(rf_ts),
    ql.BlackVolTermStructureHandle(vol_ts)
)

expiry  = ql.Date(20, 6, 2026)
payoff  = ql.PlainVanillaPayoff(ql.Option.Call, 520.0)
exercise = ql.EuropeanExercise(expiry)
option  = ql.VanillaOption(payoff, exercise)
option.setPricingEngine(ql.AnalyticEuropeanEngine(process))

print(option.NPV(), option.delta(), option.gamma(), option.theta(), option.vega())
```

### mibian (Simple, Lightweight)

```bash
pip install mibian
```

```python
import mibian

# Black-Scholes: [S, K, r (%), DTE (days)]
c = mibian.BS([525, 520, 5.3, 30], callPrice=6.50)
print(c.impliedVolatility)    # from call price
print(c.callDelta, c.callGamma, c.callTheta, c.callVega)

# Black-76 for options on futures
f = mibian.Black76([525, 520, 5.3, 30], callPrice=6.40)
```

---

## IV Surface Construction

Building an IV surface requires: raw chain data → per-contract IV → parametric surface fit.

### Step 1: Extract Per-Contract IV

```python
import pandas as pd, numpy as np
from py_vollib.black_scholes.implied_volatility import implied_volatility

def build_iv_chain(chain_df, spot, r, today):
    """
    chain_df columns: strike, expiry (date), type (call/put), mid_price
    Returns: iv per contract
    """
    rows = []
    for _, row in chain_df.iterrows():
        dte = (pd.Timestamp(row["expiry"]) - pd.Timestamp(today)).days
        t   = dte / 365.0
        if t <= 0 or row["mid_price"] <= 0: continue
        flag = "c" if row["type"] == "call" else "p"
        try:
            iv = implied_volatility(row["mid_price"], spot,
                                    row["strike"], t, r, flag)
            rows.append({"strike": row["strike"], "expiry": row["expiry"],
                         "dte": dte, "type": row["type"], "iv": iv,
                         "moneyness": np.log(spot / row["strike"])})
        except Exception:
            pass
    return pd.DataFrame(rows)
```

### Step 2: SVI Surface Fit (Optional, Research-Grade)

SVI (Stochastic Volatility Inspired) — 5-parameter model for the vol smile per expiry. Most commonly used in prop/HF options research.

```bash
pip install scipy  # SVI uses scipy.optimize
```

```python
from scipy.optimize import minimize
import numpy as np

def svi_variance(k, a, b, rho, m, sigma):
    """SVI raw parameterization. k = log-moneyness = log(K/F)."""
    return a + b * (rho * (k - m) + np.sqrt((k - m)**2 + sigma**2))

def fit_svi(k_arr, iv_arr):
    """Fit SVI to one expiry slice. Returns (a, b, rho, m, sigma)."""
    w_arr = iv_arr**2  # total variance
    def loss(params):
        a, b, rho, m, sigma = params
        if b <= 0 or abs(rho) >= 1 or sigma <= 0: return 1e10
        w_hat = svi_variance(k_arr, a, b, rho, m, sigma)
        return np.sum((w_hat - w_arr)**2)
    x0 = [0.04, 0.1, -0.3, 0.0, 0.1]
    res = minimize(loss, x0, method="Nelder-Mead")
    return res.x

# Usage: for each expiry in chain_df.groupby("expiry")
# fit_svi(slice["moneyness"].values, slice["iv"].values)
```

**Open-source IV surface repo**: `github.com/XanderRobbins/Arbitrage-Free-Volatility-Surface`  
Includes SVI + Heston calibration, no-arbitrage constraints, Python 3.10+.

### No-Arbitrage Constraints

A valid IV surface must satisfy:
- **Vertical spread arbitrage**: IV non-decreasing in strike monotonicity per expiry (calendar-free lower bound)
- **Calendar spread arbitrage**: Total variance non-decreasing in time — `σ²(K,T₂)·T₂ ≥ σ²(K,T₁)·T₁` for T₂>T₁
- **Butterfly arbitrage**: Convexity in strike (d²C/dK² ≥ 0)

Violating these means the surface implies negative risk-neutral probability mass — a free money arbitrage. QuantLib's `NoArbSabrVolSurface` enforces this numerically.

---

## What You Actually Need for Each Strategy

| Strategy | Minimum Data Needed | Provider |
|----------|---------------------|----------|
| Iron condor backtest | Historical chain: bid/ask + delta + DTE | ThetaData ($80) |
| VRP harvesting | Historical IV vs realized vol; daily Greeks | ORATS ($99) or ThetaData + compute |
| IV surface research | Full term structure + skew (SVI params) | ORATS or FlashAlpha Historical ($79) |
| Gamma exposure (GEX) | Pre-computed dealer positioning | FlashAlpha (free tier: 5 req/day) |
| Live scanning / entry signals | Current Greeks/IV snapshot | Polygon free or Alpaca indicative |
| 0DTE strategies | Minute-level chains + real-time Greeks | FlashAlpha $79 (2018+) or ThetaData |

---

## Practical Path Forward

1. **Now — live scanning**: Polygon free tier or Alpaca `indicative` feed gives current Greeks/IV for entry signal construction. No cost.

2. **Now — IV computation**: `py_vollib` or `vollib` lets you compute Greeks from any bid/ask mid-price. No data subscription needed if you have live quotes.

3. **Month 2 — backtesting**: ThetaData Standard ($80/mo) for historical chain bulk download. Use `httpx` against local terminal. Compute IV with `py_vollib_vectorized`.

4. **If doing IV surface / VRP research**: ORATS 14-day trial ($100 deposit, applied to invoice) for pre-computed IV surface parameters back to 2007.

5. **If doing gamma exposure / dealer positioning**: FlashAlpha free tier (5 req/day) for GEX/DEX — useful for timing IC entries around gamma flip levels.

**Keys in OneCLI as of 2026-05-01**: None for options providers. Polygon/Alpaca free tiers work for live scanning without additional keys.

---

## Key Python Packages Summary

| Package | Install | Use Case |
|---------|---------|----------|
| `vollib` | `pip install vollib` | BS pricing, IV, Greeks (single calc) |
| `py_vollib` | `pip install py_vollib` | Same + faster IV solver |
| `py_vollib_vectorized` | `pip install py_vollib_vectorized` | Bulk DataFrame Greeks (vectorized) |
| `mibian` | `pip install mibian` | Simple BS/Black-76, easy API |
| `QuantLib` | `pip install QuantLib` | American options, SABR/Heston, term structure |
| `scipy` | `pip install scipy` | SVI surface fitting, custom optimization |
| `httpx` | `pip install httpx` | ThetaData API calls (sync + async) |
| `polygon-api-client` | `pip install polygon-api-client` | Polygon REST + WebSocket |

---

## philippdubach/options-data — Free Historical Options Chains

**GitHub**: https://github.com/philippdubach/options-data  
**Cost**: Free (Cloudflare R2 download)  
**Coverage**: 104+ US equities and ETFs, 2008–Dec 2025, EOD snapshots  
**Format**: Parquet files per symbol-year with strike, expiry, call/put, bid/ask, IV, OI, volume  

Direct alternative to ThetaData/ORATS for backtesting. No intraday, no tick-level — EOD chain snapshots only. Adequate for:
- 45-DTE iron condor entry (H007/H170): select strikes from EOD chain, assume fill at mid
- Covered call strategy (H162): validate strike selection and premium at EOD
- Any strategy that enters at end of day and doesn't need intraday tick-level fills

### Download pattern

```python
import pandas as pd

# Files named: {SYMBOL}_{YEAR}_options.parquet
# Hosted at Cloudflare R2 — check repo README for current bucket URL
base_url = "https://pub-XXXX.r2.dev"  # see repo for current URL
df = pd.read_parquet(f"{base_url}/SPY_2023_options.parquet")
# Columns: date, expiration, strike, type, bid, ask, iv, delta, gamma, theta, vega, oi, volume
```

### Limitations vs ThetaData
- EOD only (no intraday) — can't backtest 0DTE intraday entry/exit precisely
- No fill simulation (bid/ask spread needs to be modeled manually)
- Greeks may be end-of-day computed, not real-time mid-day
- Coverage ends Dec 2025 (will need ThetaData for 2026+ live data)

### Use for H170

Sufficient for **overnight/multi-day options strategies** and for **monthly 45-DTE iron condor** (H007). For H170 specifically (0DTE same-day expiry with intraday entry), EOD data is insufficient — still need ThetaData for accurate 0DTE fills. But use this to validate the iron condor setup and strike selection logic before paying for ThetaData.
