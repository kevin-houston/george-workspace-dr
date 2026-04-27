---
updated: 2026-04-27
type: tool
---

# Backtrader vs Vectorbt

Two dominant Python backtesting frameworks with very different philosophies.

## Quick comparison

| | Backtrader | Vectorbt |
|--|-----------|---------|
| Architecture | Event-driven, sequential | Fully vectorized (NumPy/Numba) |
| Speed | Baseline | ~1000x faster for param sweeps |
| Learning curve | Beginner-friendly | Steeper (vectorized mindset) |
| Live trading | Yes (Alpaca, IB integrations) | No |
| ML integration | Awkward | Natural (NumPy/PyTorch) |
| Maintenance | Original unmaintained; use forks | Active (Pro paid tier) |
| Best for | Classical strategies, paper trading wiring | Param optimization, ML strategies |

---

## Backtrader

- Original repo: https://github.com/mementum/backtrader — **effectively unmaintained**
- **Recommended fork**: `backtrader2` — https://github.com/backtrader2/backtrader (active bug fixes, PR approvals)
- Alternative fork: `cloudQuant` — https://github.com/cloudQuant/backtrader (Python 3.8-3.13, cross-sectional + TS optimizations)
- Community: https://community.backtrader.com/

### Architecture

Event-driven: walks data bar-by-bar, just like real execution. Each bar, Backtrader calls your `next()` method. This mirrors live trading closely and makes the backtest→live transition clean.

Key classes: `Strategy`, `Indicator`, `Cerebro` (the engine), `Broker`, `DataFeed`.

### Alpaca integration

Package: `alpaca-backtrader-api` (https://github.com/alpacahq/alpaca-backtrader-api)

```python
import alpaca_backtrader_api
import backtrader as bt

class MyStrategy(bt.Strategy):
    def next(self):
        pass  # your logic

cerebro = bt.Cerebro()
cerebro.addstrategy(MyStrategy)

store = alpaca_backtrader_api.AlpacaStore(
    key_id='KEY',
    secret_key='SECRET',
    paper=True        # paper=False for live
)

data = store.getdata(
    dataname='SPY',
    historical=True,
    fromdate=datetime(2020, 1, 1),
    timeframe=bt.TimeFrame.Days
)
cerebro.adddata(data)
cerebro.run()
```

### Monthly rebalancing pattern

Use `order_target_percent()` — it figures out whether to buy or sell automatically:

```python
class ETFRotation(bt.Strategy):
    def __init__(self):
        self.month = -1

    def next(self):
        if self.data.datetime.date().month == self.month:
            return
        self.month = self.data.datetime.date().month

        # Rebalance to target weights
        self.order_target_percent(self.data0, target=0.5)  # 50% SPY
        self.order_target_percent(self.data1, target=0.5)  # 50% TLT
```

For monthly timer-based triggers: `self.add_timer(bt.timer.SESSION_END, monthdays=[1], weekcarry=True)`

### Slippage & commission gotchas

```python
# Commission (0.1% per trade)
cerebro.broker.setcommission(commission=0.001)

# Slippage (0.05% of price)
cerebro.broker.set_slippage_perc(0.0005, slip_open=True, slip_match=True)
```

**Critical**: `slip_match=True` caps fills at high/low of bar. Without slippage modeling, profitable backtests can flip to losses in live trading.

**Yahoo Finance data quirk**: CSV files come newest-first — always pass `reversed=True`:
```python
data = bt.feeds.YahooFinanceCSVData(dataname='spy.csv', reversed=True)
```

---

## Vectorbt

- Open source: https://github.com/polakowo/vectorbt
- Docs: https://vectorbt.dev/
- **Vectorbt Pro** (paid): https://vectorbt.pro/ — $20/month (lock-in pricing, will rise)
  - Pro adds: faster large-scale testing, advanced analysis tools, private docs, Discord
  - Free version has non-commercial license restriction — check before commercial use

### Why it's fast

Everything is a NumPy array operation. Trades are simulated across all parameter combinations simultaneously, not sequentially. Optional Numba JIT and Rust kernels push it further. Net result: test 1,000 strategy variants in the time Backtrader runs one.

### Parameter sweep pattern

```python
import vectorbt as vbt
import numpy as np

price = vbt.YFData.download('SPY').get('Close')

# Test all fast/slow MA pairs in one shot
windows = np.arange(2, 101)
fast_ma = vbt.MA.run(price, window=windows[:-1], short_name='fast')
slow_ma = vbt.MA.run(price, window=windows[1:], short_name='slow')

entries = fast_ma.ma_crossed_above(slow_ma)
exits   = fast_ma.ma_crossed_below(slow_ma)

pf = vbt.Portfolio.from_signals(
    price, entries, exits,
    fees=0.001,   # 0.1% per trade
    freq='1D'
)

# Results are a DataFrame with MultiIndex columns — one column per param combo
print(pf.total_return().sort_values(ascending=False).head(10))
```

Results include every metric (Sharpe, max drawdown, etc.) for all parameter combos simultaneously.

### No live trading

Vectorbt is research-only. For execution, you need a separate live layer (Alpaca, IB, etc.). This makes it ideal for the research phase but you'll need Backtrader or direct Alpaca SDK for Phase 3.

---

## Recommendation for this project

| Use case | Tool |
|----------|------|
| Classical ETF rotation (H016/H020) backtesting | Either — our custom engine is fine |
| Parameter optimization sweeps | Vectorbt — speed advantage decisive |
| Phase 3: wiring strategies to Alpaca paper account | Alpaca SDK directly (see `data-sources/alpaca-automation.md`) |
| ML-based signal research | Vectorbt or Qlib |
| Live execution simulation | Backtrader (event-driven mirrors real fills) |

For our current work (H016–H020 confirmed strategies), our custom yfinance + pandas engine is sufficient. Vectorbt becomes valuable when we start optimizing parameters or testing ML signals at scale.
