---
updated: 2026-05-02
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

## Emerging platforms (2025–2026)

| Platform | Launch | Notes |
|----------|--------|-------|
| OG Markets | Feb 2026 | Multi-outcome contracts; Gen-Z positioning; early stage |
| FanDuel Predicts | Dec 2025 | All 50 states; sports-focused; Flutter Entertainment |
| DraftKings Predictions | Dec 2025 | 38 states; DFS ecosystem integration |

**Assessment**: All emerging platforms are retail-focused with limited/no trading APIs. Kalshi and Polymarket remain the only institutional-grade options for algorithmic strategies. IBKR ForecastTrader is institutional-grade but requires the IBKR account setup overhead.


---

## prediction-market-analysis (Historical Data)

**GitHub:** https://github.com/topics/quantitative-finance (search: prediction-market-analysis)
**Stars:** 2.3k | **Data size:** 36GB

The largest publicly available prediction market historical dataset:
- Full order book history for Polymarket and Kalshi markets
- Resolution data (actual outcomes) for calibration research
- Pre-built analysis notebooks: calibration curves, liquidity analysis, market efficiency tests
- Cleaned format suitable for pandas/polars

**Use cases for George:**
- Backtest Kalshi CPI nowcasting strategy (H185) on historical data instead of paper-trading forward
- Test cross-platform arb between Polymarket and Kalshi on historical overlapping markets
- Calibration validation for LLM-based prediction (PolyBench H213 baseline)

**Download:** Requires ~40GB free disk. Consider subset download by market category.

---

## pmxt — Unified Prediction Market API

**GitHub:** https://github.com (search: pmxt)
**Stars:** 1.2k

CCXT-style unified API for multiple prediction market platforms. Key features:
- Single interface for Polymarket, Kalshi, and other platforms
- Cross-platform order book aggregation
- Unified position tracking and P&L
- WebSocket streaming for real-time price feeds

**Python example:**
```python
import pmxt

# Connect to both platforms
kalshi = pmxt.Kalshi(api_key=...)
poly   = pmxt.Polymarket()

# Find arbitrage: same event on both platforms
arb_scanner = pmxt.ArbScanner([kalshi, poly])
opportunities = arb_scanner.scan(min_edge=0.02)  # 2% minimum edge
```

**Use case for George:** Cross-platform arb scanner to find the same question priced
differently on Kalshi vs Polymarket. Historically, pricing gaps of 2-5% exist on
non-trivial markets with lower liquidity. pmxt automates the discovery layer.
