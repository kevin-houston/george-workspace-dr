---
updated: 2026-05-12
type: data-source + broker
access: Kevin has paper account; API keys in OneCLI vault
related: alpaca-automation.md (production patterns), paper-trading/pead-nlp-alpaca.md (live pipeline)
---

# Alpaca Markets — Complete Reference

Commission-free equities, options, and crypto broker with a developer-first REST + WebSocket API. The primary execution venue for Phases 3 and 4.

- Docs: https://docs.alpaca.markets/
- SDK: `pip install alpaca-py` (official; replaces deprecated `alpaca-trade-api`)
- Paper trading: https://paper-api.alpaca.markets
- GitHub: https://github.com/alpacahq/alpaca-py

---

## SDK Quick Start

```python
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Paper account
tc = TradingClient(api_key, secret_key, paper=True)

# Account info
account = tc.get_account()
print(f"Equity: ${float(account.equity):,.2f}")
print(f"Buying power: ${float(account.buying_power):,.2f}")

# Historical data
dc = StockHistoricalDataClient(api_key, secret_key)
```

---

## Order Types

### Equity Order Types

| Type | Description | Fractional OK? |
|------|-------------|----------------|
| `market` | Executes at best available price | ✓ |
| `limit` | Executes at limit price or better | ✗ |
| `stop` | Market order triggered at stop price | ✗ |
| `stop_limit` | Limit order triggered at stop price | ✗ |
| `trailing_stop` | Stop tracks market at fixed distance | ✗ |

Fractional shares require `market` order type. Use `qty` (non-integer) or `notional` parameter:

```python
# Notional buy ($500 of AAPL, fractional)
order = tc.submit_order(MarketOrderRequest(
    symbol="AAPL",
    notional=500,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,
))

# Fractional qty
from alpaca.trading.requests import MarketOrderRequest
order = tc.submit_order(MarketOrderRequest(
    symbol="MSFT",
    qty=0.5,
    side=OrderSide.BUY,
    time_in_force=TimeInForce.DAY,
))
```

### Time in Force (TIF)

| TIF | Code | Description |
|-----|------|-------------|
| Day | `day` | Cancel at end of regular session if unfilled |
| Good Till Cancelled | `gtc` | Persist until filled or cancelled (max 90 days) |
| On Open | `opg` | Participates in opening auction only (MOO/LOO) |
| On Close | `cls` | Participates in closing auction only (MOC/LOC) |
| Immediate or Cancel | `ioc` | Fill immediately; cancel remainder |
| Fill or Kill | `fok` | Fill entire order immediately or cancel entirely |

**For our strategies:**
- Monthly rebalances → `gtc` with limit price or `day` market order at open
- PEAD gap detection → `opg` (market-on-open) to capture the gap
- PEAD exits → `cls` (market-on-close) for 20-day hold exit

### Advanced Order Classes

| Class | Description | Notes |
|-------|-------------|-------|
| `simple` | Standard single-leg order | Default |
| `bracket` | Entry + take-profit limit + stop-loss | Time-in-force must be `day` or `gtc`; no extended hours |
| `oco` | One-Cancels-Other (take-profit + stop) | Must use `limit` type |
| `oto` | One-Triggers-Other | Primary fills → secondary submitted |

```python
from alpaca.trading.requests import LimitOrderRequest, OrderClass
from alpaca.trading.enums import OrderSide, TimeInForce

# Bracket order: entry + 5% take-profit + 3% stop-loss
bracket = tc.submit_order(LimitOrderRequest(
    symbol="NVDA",
    qty=10,
    side=OrderSide.BUY,
    type="limit",
    time_in_force=TimeInForce.GTC,
    limit_price=900.00,
    order_class=OrderClass.BRACKET,
    take_profit={"limit_price": 945.00},
    stop_loss={"stop_price": 873.00},
))
```

---

## Extended Hours Trading

- Supported via `extended_hours=True` parameter
- **Restrictions**: limit orders only, `day` or `gtc` TIF
- No bracket or OCO orders in extended hours
- Available: pre-market (4 AM–9:30 AM ET), after-hours (4 PM–8 PM ET)

```python
from alpaca.trading.requests import LimitOrderRequest

order = tc.submit_order(LimitOrderRequest(
    symbol="AAPL",
    qty=10,
    side=OrderSide.BUY,
    limit_price=195.00,
    time_in_force=TimeInForce.DAY,
    extended_hours=True,
))
```

---

## Account Types and Requirements

### Paper Trading
- Free for all users
- No deposit required
- Simulates PDT enforcement
- No dividends credited
- Data: IEX feed (free) — represents ~2% of market volume

### Live Trading (US Residents)
- No minimum deposit required
- `$2,000` equity threshold to unlock margin + short selling
- `$25,000` minimum equity if designated as Pattern Day Trader (PDT)
- Commission-free equities and crypto; options have per-contract fees

### PDT Rule (Updated)
FINRA retired the traditional PDT rule in 2025. Alpaca now uses an **Intraday Buying Power** (IDTBP) framework:
- `Intraday Buying Power` = running balance updated throughout the day, replacing static Day Trade Buying Power
- Accounts below $25k equity face intraday margin constraints, not outright trade count limits
- Accounts with ≥$25k equity have `4×` intraday, `2×` overnight buying power

### Non-US Residents
- $30,000 minimum initial deposit
- Full feature access otherwise identical to US accounts

---

## WebSocket Streaming

### TradingStream — Order/Account Updates

Real-time stream for order fills, cancels, and account changes:

```python
from alpaca.trading.stream import TradingStream

stream = TradingStream(api_key, secret_key, paper=True)

@stream.on("trade_updates")
async def on_trade_update(data):
    """Called on order fill, cancel, partial fill, etc."""
    print(f"Event: {data.event}  Symbol: {data.order.symbol}  "
          f"Fill: {data.order.filled_qty} @ {data.order.filled_avg_price}")

stream.run()  # blocking; run in a thread for non-blocking use
```

Event types: `new`, `fill`, `partial_fill`, `cancelled`, `expired`, `pending_cancel`, `replaced`.

### StockDataStream — Real-Time Quotes/Trades

```python
from alpaca.data.live import StockDataStream

data_stream = StockDataStream(api_key, secret_key)

async def on_bar(bar):
    print(f"{bar.symbol}  close={bar.close}  vol={bar.volume}")

async def on_quote(quote):
    print(f"{quote.symbol}  ask={quote.ask_price}  bid={quote.bid_price}")

data_stream.subscribe_bars(on_bar, "AAPL", "MSFT")
data_stream.subscribe_quotes(on_quote, "NVDA")
data_stream.run()
```

**Data sources**: `iex` (free, ~2% market volume) or `sip` ($99/mo, full consolidated tape). For live trading signals, the SIP feed is strongly recommended — IEX can miss short-lived quotes.

---

## Rate Limits

| Endpoint category | Rate limit |
|-------------------|-----------|
| Trading REST (orders, positions) | 200 req/min |
| Market data REST | 200 req/min |
| WebSocket connections | 1 connection per auth stream |
| Max WebSocket subscriptions | 5,000 symbols per stream |

---

## Short Selling

Requirements:
- Account equity ≥ $2,000 (margin account threshold)
- Security must be available to borrow (check `asset.shortable` field)
- Borrowed shares charged overnight borrow fee (varies; typically 0.25%–5% annual for liquid large-caps)

```python
# Check if a stock is shortable before submitting short
asset = tc.get_asset("TSLA")
if asset.shortable:
    short_order = tc.submit_order(MarketOrderRequest(
        symbol="TSLA",
        qty=10,
        side=OrderSide.SELL,  # sells a short position
        time_in_force=TimeInForce.DAY,
    ))
```

---

## Positions and Portfolio

```python
# Get all positions
positions = tc.get_all_positions()
for p in positions:
    print(f"{p.symbol}: {p.qty} shares @ avg ${p.avg_entry_price}  "
          f"P&L: ${float(p.unrealized_pl):+.2f}")

# Close a position entirely
tc.close_position("AAPL")

# Close fraction of position
tc.close_position("AAPL", qty=5)

# Close all positions (nuclear option — use carefully)
tc.close_all_positions(cancel_orders=True)
```

---

## Options Trading

Alpaca supports up to **Level 3 options** (depending on account approval). Key differences from equity orders:

- Options require `symbol` in OCC format: `AAPL240119C00150000` (AAPL Jan 2024 $150 call)
- Use `OptionOrderRequest` instead of `MarketOrderRequest`
- Bracket orders NOT supported for options (use `oco` for protective spread)
- Data: options chain via `OptionHistoricalDataClient`

```python
from alpaca.trading.requests import OptionOrderRequest, LimitOrderRequest

# Buy a call option
call_order = tc.submit_order(OptionOrderRequest(
    symbol="AAPL240119C00150000",
    qty=1,
    side=OrderSide.BUY,
    type="limit",
    limit_price=5.50,
    time_in_force=TimeInForce.DAY,
))
```

For options data (IV surface, chains): see [Options Data Sources](options-data.md).

---

## Paper → Live Transition Checklist

For Phase 3 → Phase 4 (live trading):

- [ ] Fund live account (no minimum for US; $2k unlocks margin)
- [ ] Copy API keys from paper env vars to live env vars (different key pair)
- [ ] Change `paper=True` → `paper=False` in all `TradingClient` / `TradingStream` calls
- [ ] Switch `StockDataStream` data feed from `iex` to `sip` ($99/mo) for reliable fill detection
- [ ] Test with 1-share orders before deploying at full position size
- [ ] Verify `asset.tradable` and `asset.fractionable` before placing orders programmatically
- [ ] Monitor initial trades manually for 2–3 weeks before enabling full automation
- [ ] Set hard position-size limits in code ($500 max per position initially) until proven live

---

## Common Gotchas

- **Paper ≠ live fills**: Paper fills on market orders assume exact mid-price. Live fills slop on the spread — for H181 monthly rebalance with 6 stocks, expect 2–5 bps of slippage per side.
- **IEX data gaps**: IEX misses ~98% of tape. Don't use IEX for gap detection (PEAD `pead_open.py` must use SIP or Polygon for accurate open-price gap calculation).
- **PDT in paper**: Paper account enforces PDT detection even on simulated positions — you'll get blocked from day trading if < $25k equity and make 4+ day trades in 5 days.
- **Options approval**: Paper account approves all options levels automatically. Live account requires a separate application with Apex Clearing.
- **Cancel/replace latency**: Order replacements have a ~200ms round-trip. For MOO/MOC orders, modifications must be submitted > 5 min before auction.
- **`unrealized_pl` vs `unrealized_plpc`**: `unrealized_pl` is dollar P&L; `unrealized_plpc` is percentage. Both are available on `Position` objects.

---

## Related Pages

- [Alpaca Automation Guide](alpaca-automation.md) — production patterns: position sizing, rebalance logic, Phase 3 infrastructure
- [PEAD-NLP Alpaca Deployment](../paper-trading/pead-nlp-alpaca.md) — live H163/H174 pipeline
- [Options Data Sources](options-data.md) — chains, IV surface, OPRA feed
- [Free / Low-Cost Data Sources](free-data.md) — using Alpaca's 1-min bars for free intraday backtest data
