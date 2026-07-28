---
updated: 2026-07-28
---

# Other Prediction Market Platforms

## PredictIt

- CFTC DCM + DCO approval (September 2025, upgraded from no-action letter)
- Focus: US political markets (elections, policy, congressional votes)
- Free read-only JSON API: `predictit.org/api/marketdata/all/` — 60-second refresh
- **No programmatic trading API** — orders must be placed manually via web UI
- **Verdict**: Data source only; not viable for algorithmic trading

---

## Manifold Markets

- Play money (Mana) only — no cash value since March 2025 (Sweepcash model sunset)
- No financial risk; good sandbox for learning prediction market dynamics
- **Verdict**: Educational only

---

## Limitless Exchange (Base)

Launched 2024; by mid-2026 the leading prediction market on Base (Coinbase L2). Focuses on fast-settling crypto and macro markets with same-day resolution.

- **Chain**: Base (Coinbase L2) — low gas fees (~$0.001/trade), fast finality
- **Market types**: Crypto price bets (BTC, ETH, SOL), macro events, same-day short-expiry markets
- **Volume**: $1B+ traded to date
- **API**: REST + WebSocket; covers market data, order books, OHLCV candles, and order placement
- **Auth**: On-chain via wallet signature (no centralized account required)
- **Settlement**: Instant on-chain resolution; no withdrawal delay

### MCP integration

GitHub `joinQuantish/limitless-mcp` provides a self-hosted MCP server for trading Limitless from Claude Code agents — direct tool calls for market data, order placement, position monitoring.

```python
# Base connection via web3.py
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org"))
# limitless-sdk wraps contract calls into Python-friendly methods
# pip install limitless-sdk
from limitless import LimitlessClient
client = LimitlessClient(private_key=os.getenv("WALLET_KEY"), chain="base")
markets = client.get_markets(category="crypto", active=True)
```

**Verdict**: Best for short-horizon crypto/macro bets where Kalshi's economic contracts aren't available. No USD fiat ramp — requires on-chain USDC.

---

## Opinion (BNB Chain)

Third-largest prediction market by volume as of mid-2026. Distinguishes from Polymarket/Kalshi via an AI-powered oracle that handles both market creation and resolution.

- **Chain**: BNB Chain
- **Volume rank**: #3 globally by trading volume
- **AI oracle**: LLM-based automated market creation and resolution; reduces admin overhead but introduces oracle risk
- **Market types**: Macro events, crypto, and culture markets; strength in non-US geopolitical questions
- **Python SDK**: `opinion-clob-sdk` (PyPI, released February 2026)
- **API**: CLOB-based REST + WebSocket

```bash
pip install opinion-clob-sdk
```

```python
from opinion_clob import OpinionClient

client = OpinionClient(api_key=os.getenv("OPINION_KEY"))
markets = client.get_markets(status="open")
book = client.get_orderbook(market_id="BTCUSD-WEEK")
# Place limit order
client.place_order(market_id="BTCUSD-WEEK", side="YES", price=0.62, size=100)
```

**Verdict**: Useful for markets Kalshi doesn't list (non-US political, international events). AI oracle risk: resolution occasionally disputed on ambiguous questions.

---

## Interactive Brokers / CME ForecastTrader

CME-listed event contracts, accessed via IBKR account. Contracts treat binary outcomes as options: buy YES at $X (1–99), collect $100 if event occurs.

### Market coverage

| Contract | Underlying | Settlement |
|----------|-----------|-----------|
| CPIFC | CPI YoY band (e.g. 3.0–3.5%) | BLS release date |
| USIC | Unemployment rate band | BLS jobs report |
| FEDTC | Fed funds target rate | FOMC meeting date |
| SPX5C | S&P 500 weekly range | Friday close |
| BTCC | Bitcoin 1-week range | Friday |
| EURX | EUR/USD weekly range | Friday |

### Access and mechanics

- Access via IBKR account; no separate account required
- Priced in dollars ($1–$99 per contract); settles at $100 or $0
- **Commission**: Free (exchange spread-based)
- **Liquidity**: Lower than Kalshi CPI; expect wider spreads (often 2–5% on economic contracts)
- **Margin**: Covered option treatment for short positions
- API: IBKR TWS or IB Gateway (local process required); `ib_insync` Python wrapper

### Setup

```bash
# Install IB Gateway (headless TWS alternative) — download from IBKR
# Start: ibgateway start --mode=paper

pip install ib_insync
```

```python
from ib_insync import IB, Contract, Order

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)   # 7497=paper, 7496=live

# Describe a ForecastTrader contract
c = Contract(
    secType="BINARY",
    symbol="CPIFC",
    exchange="IBKRFCST",
    currency="USD",
    lastTradeDateOrContractMonth="202606",
)
details = ib.reqContractDetails(c)
print(details[0].longName)  # e.g. "US CPI YoY Jun 2026 3.0-3.5%"
```

### Comparison vs. Kalshi

| Feature | IBKR ForecastTrader | Kalshi |
|---------|--------------------|----|
| Regulatory | CFTC DCM (CME) | CFTC DCM (Kalshi) |
| Liquidity | Low–Moderate | Moderate–High |
| Markets | Economic, FX, equities, crypto | Economic + broader |
| API | IBKR TWS (requires local process) | REST + WebSocket (cloud-friendly) |
| Fees | None (spread) | Per-contract fee |
| Min account | IBKR standard | $10 |
| Best for | Traders with existing IBKR setup | Standalone algo deployment |

**Verdict**: Good for traders who already use IBKR for equities/options — no separate account needed. Competes directly with Kalshi's economic contracts. Use Kalshi for standalone prediction market algos; IBKR ForecastTrader for cross-asset strategies within an existing IBKR account.

---

## Kalshi Timeless (perpetual contracts)

Launched April 27, 2026 — the first CFTC-regulated perpetual prediction market contracts.

### Structure

- **No expiration**: Unlike regular Kalshi contracts that expire on a specific event date, Timeless contracts are perpetual
- **Underlying**: Crypto prices at scheduled times (BTC, ETH at launch)
- **Example**: "Is BTC above $X at 8 PM ET tonight?" — resets daily, no single expiry
- **Settlement**: Rolling — contract resolves at the scheduled observation time, a new one opens
- **CFTC-regulated**: Full DCM status; USD settlement; margin-based

### Funding rate mechanism

Analogous to crypto perpetual futures. Paid every 8 hours:

- If perp price > exchange's fair value estimate → **longs pay shorts** (funding rate > 0)
- If perp price < fair value → **shorts pay longs** (funding rate < 0)
- Rate magnitude: 0.01–0.15% per 8-hour period, depending on deviation size
- Fair value = exchange's probabilistic estimate of the outcome (derived from options/spot prices)

**Key implication**: You can earn passive income by taking the side of a mispriced perp without caring about the outcome direction — you just need the funding rate payment to exceed your expected loss from gap moves.

### Volume

Kalshi reported $100B+ annualized notional at launch (April 27, 2026). Primarily from crypto traders familiar with perp mechanics.

### Access

Uses the same Kalshi REST API (`/trade-api/v2/timeless/` endpoint namespace). Authentication and order placement are identical to regular Kalshi contracts. See algorithmic-strategies.md for the full `KalshiClient` implementation.

```python
# Timeless-specific fields in market response
{
    "series_id": "KXBTCUSD-TIMELESS",
    "yes_bid": 62,              # current perp price for YES (cents)
    "yes_ask": 64,
    "funding_rate": 0.0023,     # 0.23% per 8h; positive = longs pay
    "next_funding_ts": 1746720000,
    "fair_value": 60,           # exchange's fair value estimate
    "mark_price": 63,
}
```

### Risks vs. regular Kalshi contracts

| Risk | Regular contract | Timeless |
|------|-----------------|----------|
| Event gap | Low (priced in) | High (BTC can gap ±10% overnight) |
| Rollover cost | None | Funding rate if wrong side |
| Margin call | No (max loss = premium) | Yes (margin-based) |
| Liquidity | Moderate | Early-stage; wide spreads |

---

## Cross-Platform Arbitrage (Kalshi × Polymarket)

The same binary event is listed on both platforms with different implied probabilities — a guaranteed-profit opportunity if prices diverge beyond combined fees.

### Mechanics

If `Kalshi_YES + Polymarket_NO < $1.00`, buy both sides and collect $1.00 on resolution regardless of outcome. Profit = $1.00 − (cost_YES + cost_NO) − fees.

### Fee structure (2026)

**Kalshi** — tiered by monthly volume, charged as % of profit:
| Monthly volume | Fee rate |
|---------------|----------|
| < $50K | 7% of profit |
| $50K–$250K | 5% |
| $250K–$1M | 3% |
| > $1M | 1% |

**Polymarket Global** — no direct fee; gas costs ~$0.001–$0.01/trade on Polygon. Sports/politics markets: some markets now charge 1–2% maker fee. Geopolitics markets: **zero fee** (strictly dominant for arb).

### Minimum edge required

At 7% Kalshi fee tier: need **~5%+ gross edge** after fees. At 3% tier: **~2.5%+ gross edge**. A 3% raw spread evaporates entirely at the highest Kalshi fee tier.

**Practical threshold**: For retail arbers at the 7% tier, only spreads ≥ 5 cents per dollar contract are worth executing.

### Typical spread sizes

| Market type | Typical spread | Notes |
|------------|----------------|-------|
| Major elections | 0.5–2% | Closes within minutes |
| NBA/NFL outcomes | 1–3% | More persistent |
| Crypto price bets | 2–5% | Kalshi BTCC vs Polymarket crypto |
| Thin sports | 3–8% | Lower volume, wider spreads |

### Execution requirements

Detection latency must be **< 25ms** to capture spreads before they close on high-liquidity markets. Both platforms expose WebSocket order books for real-time monitoring.

```python
import asyncio, websockets, json

async def monitor_kalshi_orderbook(market_ticker: str, on_update):
    url = f"wss://api.elections.kalshi.com/trade-api/ws/v2"
    async with websockets.connect(url, extra_headers={"Authorization": f"Bearer {TOKEN}"}) as ws:
        await ws.send(json.dumps({"id": 1, "cmd": "subscribe", "params": {
            "channels": ["orderbook_delta"],
            "market_tickers": [market_ticker],
        }}))
        async for msg in ws:
            data = json.loads(msg)
            await on_update(data)

# Run both WebSockets concurrently; trigger arb logic when YES_kalshi + NO_poly < 0.95
# Use asyncio.gather(monitor_kalshi(...), monitor_polymarket(...))
```

**Key constraint**: Pre-fund both platforms. Polymarket requires on-chain USDC (bridging from Ethereum). Kalshi uses USD bank transfer (ACH, 1–3 days) or wire.

### Turnkey tools

- **pmxt** (`pip install pmxt`) — unified Python SDK for Polymarket + Kalshi + Limitless + Opinion. Cross-platform arb scanner built in: `pmxt.ArbScanner([kalshi, poly]).scan(min_edge=0.025)`
- **Claw Arbs** (`clawarbs.com`) — commercial subscription service; 25ms detection WebSocket feeds already built out

---

## AI Trading Agents (2026)

Prediction markets have become a proving ground for autonomous AI agents. As of mid-2026, **14 of the top 20 most profitable Polymarket wallets are bots**, and AI agents represent over 30% of wallet activity. Retail traders pick the right side more often than bots — the bot advantage is microstructure: earlier entry at better prices.

### Platform overview

| Platform | Venues | Model | Notes |
|----------|--------|-------|-------|
| **Turbine Studio** | Kalshi + Polymarket | Natural-language strategy builder + cloud execution | Handles API version migrations; Pro tier required for cross-platform arb |
| **Simmer** | Kalshi + Polymarket | SDK-first; user writes strategy code | Built-in risk rails: $100/trade, $500/day defaults |
| **Polystrat (Olas/Pearl)** | Polymarket only | Autonomous NLP-driven agent; self-custodial Safe wallet | 4,200+ trades in first month; 37%+ positive P&L vs 7–13% for humans |
| **OctoBot PM Module** | Polymarket | Rule-based; GPL-3.0 self-hosted Docker | No LLM; good for pure arb rules |
| **PredictEngine** | Polymarket only | Cloud; $0–$99/mo; server-side key (exportable) | Simple NLP signals |
| **Polymarket Agents** | Polymarket | Archived May 2026 | No longer maintained |

### Polystrat implementation

Polystrat runs via Pearl's local agent runtime. Key features:
- Uses NLP to let users set high-level goals in plain text ("maximize profit on crypto markets with max 2% per-trade risk")
- Selects markets autonomously across sports, politics, economics
- Runs locally via Pearl on user's machine; funds controlled by self-custodial Safe account
- Full audit trail on-chain

```bash
# Install Pearl and run Polystrat locally
# https://www.pearl.you/polystrat
pip install olas-pearl
pearl start polystrat --config polystrat_config.yaml
```

### Bot performance context (2026)

- 37%+ of Polystrat agents show positive P&L vs 7–13% of human traders on the same platform
- Bot advantage is speed and consistency, not superior forecasting accuracy
- A single automated bot reportedly earned ~$150K executing 8,894 trades on short-term crypto contracts
- **Strategic implication**: If building a Kalshi nowcasting strategy (H185), the human-vs-bot performance gap suggests that price discovery in liquid markets already reflects LLM-level forecasting. Edge must come from niche markets, data sources unavailable to bots, or execution quality rather than pure prediction accuracy.

---

## Emerging Platforms 2025–2026

| Platform | Chain | Launch | Notes |
|----------|-------|--------|-------|
| OG Markets | Polygon | Feb 2026 | Multi-outcome (non-binary) contracts; Gen-Z positioning |
| FanDuel Predicts | Off-chain | Dec 2025 | All 50 states; sports-focused; Flutter Entertainment |
| DraftKings Predictions | Off-chain | Dec 2025 | 38 states; DFS ecosystem integration |
| ADI Predictstreet | Off-chain | Jun 2026 | Official FIFA World Cup 2026 partner; near real-time in-game settlement |
| Phantom-Kalshi integration | Solana | Dec 2025 | Phantom wallet native Kalshi access |
| Jupiter-Polymarket integration | Solana | Jan 2026 | Jupiter DEX aggregator + Polymarket liquidity |
| Inframarkets | Solana | Feb 2026 | Solana-native prediction market |
| Epoch | Solana | Feb 2026 | Short-duration Solana prediction markets |

**Solana trend**: A cluster of Solana-native and wallet-integrated prediction market products launched Dec 2025–Feb 2026, reflecting the broader AI-agent activity on Solana where gas costs are minimal.

**Assessment**: All sports-focused platforms (FanDuel, DraftKings, DraftKings, ADI) have no trading APIs. Solana-native platforms have early liquidity and wide spreads — arb opportunities exist but execution infrastructure not yet mature. Kalshi and Polymarket remain the only institutional-grade options for systematic algorithmic strategies.

---

## Open Datasets & Unified APIs

### prediction-market-analysis (github.com/Jon-Becker/prediction-market-analysis)

- **Stars**: 2.3K
- **Dataset size**: 36GB historical data
- **Coverage**: Both Polymarket AND Kalshi — largest public PM dataset as of 2026
- **Granularity**: Minute-level price time series + complete order books + resolution data
- **Format**: Parquet with DuckDB interface (fast querying without loading full 36GB into RAM)
- **Included notebooks**: Calibration curves, Brier score analysis, market efficiency testing
- **Use case**: Backtesting PM strategies, calibration research, liquidity analysis
- **Relevance**: Directly enables H185 Kalshi nowcasting strategy validation with historical fill data

```python
import duckdb
# Query without loading 36GB into RAM
conn = duckdb.connect()
df = conn.execute("SELECT * FROM read_parquet('kalshi/*.parquet') WHERE market_slug LIKE '%CPI%'").df()
```

### pmxt — Unified Prediction Market API (github.com/pmxt-dev/pmxt)

- **Stars**: 1.2K
- **Coverage**: Polymarket, Kalshi, Limitless, Opinion, and 8+ more venues via single interface
- **Data model**: Event → Market → Outcome hierarchy unified across platforms
- **Features**: Standardized order types, cross-platform market discovery, portfolio aggregation, webhook notifications, built-in ArbScanner
- **Install**: `pip install pmxt`
- **Key benefit**: Swap exchange backends without refactoring business logic

```python
import pmxt

kalshi = pmxt.Kalshi(api_key=os.getenv("KALSHI_KEY"))
poly   = pmxt.Polymarket()

# Find arbitrage: same event on both platforms
arb_scanner = pmxt.ArbScanner([kalshi, poly])
opportunities = arb_scanner.scan(min_edge=0.02)  # 2% minimum gross edge

# Switch venue without changing strategy code
for venue in [kalshi, poly]:
    markets = venue.get_markets(category="economics", active=True)
    book    = venue.get_orderbook(markets[0].id)
```

**Relevance**: Replaces per-platform Kalshi/Polymarket auth boilerplate; enables cross-platform strategies in automated-pipeline.md with one SDK.
