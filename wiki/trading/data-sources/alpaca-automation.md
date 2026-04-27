---
updated: 2026-04-27
type: guide
status: Phase 3 foundation
---

# Alpaca Paper Trading Automation

How to wire our confirmed strategies (H020 ETF rotation, H009 IBS) to the Alpaca paper account for Phase 3.

## SDK

**Use `alpaca-py` — not `alpaca-trade-api`** (legacy, deprecated Dec 2022).

```bash
pip install alpaca-py
```

- GitHub: https://github.com/alpacahq/alpaca-py
- Docs: https://alpaca.markets/sdks/python/
- Requires Python 3.8+

## Authentication

```python
from alpaca.trading.client import TradingClient

client = TradingClient(
    api_key=os.environ['ALPACA_API_KEY'],
    secret_key=os.environ['ALPACA_SECRET'],
    paper=True        # paper=False for live
)
```

Keys are in `$ALPACA_API_KEY` + `$ALPACA_SECRET`. Current paper account: ~$102k equity, $204k buying power.

---

## Core operations

### Check account & portfolio value

```python
account = client.get_account()
print(f"Equity:        ${float(account.equity):,.2f}")
print(f"Buying power:  ${float(account.buying_power):,.2f}")
print(f"P&L today:     ${float(account.equity) - float(account.last_equity):+,.2f}")
```

### Check current positions

```python
positions = client.get_all_positions()
holdings = {p.symbol: {
    "qty":          float(p.qty),
    "market_value": float(p.market_value),
    "avg_cost":     float(p.avg_entry_price),
    "unrealized_pl":float(p.unrealized_pl),
} for p in positions}
```

### Submit a market order

```python
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

def submit_market_order(symbol: str, qty: float, side: str):
    order = MarketOrderRequest(
        symbol=symbol,
        qty=qty,
        side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        time_in_force=TimeInForce.DAY
    )
    return client.submit_order(order)
```

Alpaca supports fractional shares for ETFs — you can specify dollar amounts instead of share counts using `notional` instead of `qty`.

---

## Monthly ETF rotation (H020)

Full automation pattern: compute signal, diff against current holdings, rebalance.

```python
import yfinance as yf
import numpy as np
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

ASSETS   = ["SPY", "QQQ", "TLT", "GLD", "IEF"]
CASH_ETF = "SHY"
TOP_N    = 2


def compute_h020_signal() -> tuple[list[str], list[str]]:
    """Return (top2_to_hold, rest_to_cash)."""
    tickers = ASSETS + [CASH_ETF]
    raw = yf.download(tickers, period="15mo", auto_adjust=True, progress=False)
    prices = raw["Close"]

    monthly = prices[ASSETS].resample("ME").last()
    monthly_rets = prices[ASSETS].pct_change().resample("ME").apply(
        lambda x: (1 + x).prod() - 1)

    mom_12  = (monthly / monthly.shift(12) - 1).iloc[-1].dropna()
    vol_6   = monthly_rets.rolling(6).std().iloc[-1].dropna() * np.sqrt(12)

    valid    = mom_12.index.intersection(vol_6.index)
    combined = mom_12[valid].rank() + vol_6[valid].rank(ascending=False)
    top2     = list(combined.nlargest(TOP_N).index)
    rest     = [s for s in valid if s not in top2]
    return top2, rest


def rebalance(client: TradingClient, top2: list[str], rest: list[str]):
    """Sell assets not in top2, buy top2 at equal weight. Rest → SHY."""
    account   = client.get_account()
    equity    = float(account.equity)
    positions = {p.symbol: float(p.market_value)
                 for p in client.get_all_positions()}

    target = {s: equity / TOP_N for s in top2}
    target[CASH_ETF] = equity * (len(rest) / len(ASSETS))

    # SELL FIRST (frees cash)
    for sym, curr_val in positions.items():
        if sym not in target:
            pos = client.get_open_position(sym)
            client.submit_order(MarketOrderRequest(
                symbol=sym, qty=float(pos.qty),
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY))

    # BUY / ADJUST to target
    current_prices = {s: float(yf.download(s, period="1d",
                      auto_adjust=True, progress=False)["Close"].iloc[-1])
                      for s in target}

    for sym, tgt_val in target.items():
        curr_val = positions.get(sym, 0.0)
        diff     = tgt_val - curr_val
        price    = current_prices[sym]
        qty      = abs(diff) / price

        if diff > price * 0.01:   # buy if >1 share worth of difference
            client.submit_order(MarketOrderRequest(
                symbol=sym, qty=round(qty, 4),
                side=OrderSide.BUY, time_in_force=TimeInForce.DAY))
        elif diff < -price * 0.01:
            client.submit_order(MarketOrderRequest(
                symbol=sym, qty=round(qty, 4),
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY))
```

**Run on the first trading day of each month.** The H016 signal file `backtesting/paper_trading/h016_signal.py` already computes the signal; the rebalancer above wires it to live orders.

---

## Daily IBS (H009)

```python
def check_h009_signal() -> str | None:
    """Returns 'buy', 'flat', or None (no change)."""
    spy = yf.download("SPY", period="5d", auto_adjust=True, progress=False)
    spy.columns = spy.columns.str.lower()
    last = spy.iloc[-1]
    ibs = (last["close"] - last["low"]) / (last["high"] - last["low"])

    positions = {p.symbol for p in client.get_all_positions()}
    if "SPY" in positions:
        # Exit if IBS > 0.8 (checked next day)
        if ibs > 0.8:
            return "sell"
    else:
        # Enter if previous day IBS < 0.2
        prev_ibs = (spy.iloc[-2]["close"] - spy.iloc[-2]["low"]) / \
                   (spy.iloc[-2]["high"] - spy.iloc[-2]["low"])
        if prev_ibs < 0.2:
            return "buy"
    return None
```

**Run daily at market open** (9:31 ET). The IBS signal uses previous-day bar data, so pre-market calculation is fine.

---

## Rate limits & gotchas

| Limit | Value |
|-------|-------|
| API calls (free tier) | 200/min |
| API calls (funded account) | 1,000/min |
| WebSocket connections | Unlimited |
| Pattern day trade rule | Triggered if 4+ day trades in 5 days with <$25k account |

**Key gotchas:**
- **Sell before buy**: always sell first to free cash. Alpaca rejects buys when buying power is insufficient.
- **Paper ≠ live**: paper fills assume unlimited liquidity. Real fills for ETFs like SPY/TLT are usually fine but very small ETFs may not fill cleanly.
- **Data feed**: free Alpaca data (IEX) covers ~8-10% of market volume. Use yfinance or Polygon for signal computation; Alpaca for execution only.
- **Fractional shares**: use `notional` (dollar amount) instead of `qty` if you want exact dollar allocations.
- **Market hours**: orders outside 9:30-16:00 ET queue for next session by default; set `extended_hours=True` for pre/post market.

---

## Streaming fills

For real-time fill confirmation:

```python
from alpaca.trading.stream import TradingStream

stream = TradingStream('API_KEY', 'SECRET', paper=True)

@stream.on('trade_updates')
async def on_trade_update(data):
    if data.event == 'fill':
        print(f"Filled {data.order.symbol}: {data.qty} @ ${data.price}")

stream.run()
```

Useful for logging actual fill prices vs. assumed prices in the backtest.

---

## Automation schedule (recommended)

| Task | When | Script |
|------|------|--------|
| H020 signal check + rebalance | 1st trading day of month, 9:45 ET | `paper_trading/h020_rebalancer.py` (to build) |
| H009 IBS check | Daily, 9:31 ET | `paper_trading/h009_daily.py` (to build) |
| Position P&L check | Daily, 16:01 ET | `paper_trading/check_positions.py` |
| H016 signal log | Monthly, any time | `paper_trading/h016_signal.py` |

Use `mcp__nanoclaw__schedule_task` to register the monthly and daily tasks once scripts are production-ready.
