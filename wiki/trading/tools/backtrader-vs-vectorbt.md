---
updated: 2026-04-29
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
| Live trading | Yes (Alpaca, IB integrations) | No (research only) |
| ML integration | Awkward | Natural (NumPy/PyTorch) |
| Maintenance | Original unmaintained; use forks | Active (v1.0.0 released April 2026) |
| License | MIT | Apache 2.0 + Commons Clause (non-commercial restriction on free tier) |
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

### H-series ETF rotation in Backtrader

Implementing the H116 momentum + TSMOM filter strategy (top-1 by composite score, monthly rebalance):

```python
import backtrader as bt
import pandas as pd
import numpy as np
from datetime import date

class H116Rotation(bt.Strategy):
    """
    Monthly ETF rotation: top-1 by composite score (12m_mom_rank + inv_6m_vol_rank).
    TSMOM filter: asset must have positive 12m return to be eligible.
    """
    params = dict(
        universe=['SPY','QQQ','TLT','GLD','IEF','EFA','EEM','BIL',
                  'EWJ','EWH','EWT','EWY','EWS','EPHE','EWG','EWQ','EWU','EWD','EWN'],
        tsmom_filter=True,    # H116: only select positive-momentum assets
    )

    def __init__(self):
        self.last_rebalance_month = -1
        # Build dict of {name: datafeed} for easy lookup
        self.datas_by_name = {d._name: d for d in self.datas}

    def next(self):
        today = self.datas[0].datetime.date(0)
        if today.month == self.last_rebalance_month:
            return
        self.last_rebalance_month = today.month
        self._rebalance()

    def _rebalance(self):
        scores = {}
        for name, d in self.datas_by_name.items():
            if len(d) < 252:
                continue
            closes = np.array([d.close[-i] for i in range(252)])
            mom_12 = closes[0] / closes[-1] - 1
            if self.params.tsmom_filter and mom_12 <= 0:
                continue
            # 6m rolling vol (monthly proxy)
            monthly_rets = [closes[i*21] / closes[(i+1)*21] - 1 for i in range(6)]
            vol_6 = np.std(monthly_rets)
            scores[name] = (mom_12, vol_6)

        if not scores:
            return  # nothing qualifies; go to cash (hold BIL implicitly)

        # Composite rank: mom_12 rank + inv_vol rank
        mom_vals = {k: v[0] for k, v in scores.items()}
        vol_vals = {k: v[1] for k, v in scores.items()}
        sorted_mom = sorted(mom_vals, key=lambda k: mom_vals[k])
        sorted_vol = sorted(vol_vals, key=lambda k: vol_vals[k], reverse=True)
        composite = {k: sorted_mom.index(k) + sorted_vol.index(k) for k in scores}
        winner = max(composite, key=lambda k: composite[k])

        # Rebalance: sell all non-winners, buy winner to 100%
        for name, d in self.datas_by_name.items():
            target = 1.0 if name == winner else 0.0
            self.order_target_percent(d, target=target)
```

### Monthly rebalancing (simpler pattern)

Use `order_target_percent()` — handles buy/sell direction automatically:

```python
class ETFRotation(bt.Strategy):
    def __init__(self):
        self.month = -1

    def next(self):
        if self.data.datetime.date().month == self.month:
            return
        self.month = self.data.datetime.date().month
        # Rebalance to target weights
        self.order_target_percent(self.data0, target=0.5)
        self.order_target_percent(self.data1, target=0.5)
```

For explicit timer: `self.add_timer(bt.timer.SESSION_END, monthdays=[1], weekcarry=True)`

### Slippage & commission

```python
cerebro.broker.setcommission(commission=0.001)  # 0.1% per trade
cerebro.broker.set_slippage_perc(0.0005, slip_open=True, slip_match=True)
```

**Critical**: `slip_match=True` caps fills at high/low of bar. Without slippage modeling, profitable backtests can flip to losses in live trading.

---

## Vectorbt

- GitHub: https://github.com/polakowo/vectorbt
- Docs: https://vectorbt.dev/
- **Version**: 1.0.0 (released April 22, 2026) — Production/Stable; Python 3.10-3.13
- **Vectorbt Pro** (paid): https://vectorbt.pro/ — $20/month lock-in pricing
  - Pro adds: Rust-accelerated engine, intraday backtesting, private tutorials, AI workflow integration
  - Free version: non-commercial license restriction (Apache 2.0 + Commons Clause)

### Why it's fast

Everything is a NumPy array operation. Trades are simulated across all parameter combinations simultaneously. Optional Numba JIT and Rust kernels (Pro) push further. Net result: ~1M orders processed in under 100ms on M1.

### H-series ETF rotation in Vectorbt

Full implementation of the H116 cross-sectional momentum strategy (top-1 of N assets by composite score, monthly rebalance):

```python
import vectorbt as vbt
import pandas as pd
import numpy as np

# Download H041a universe
UNIVERSE = ['SPY','QQQ','TLT','GLD','IEF','EFA','EEM','BIL',
            'EWJ','EWH','EWT','EWY','EWS']
close = vbt.YFData.download(UNIVERSE, start='2008-01-01').get('Close')

# ── Signal computation ────────────────────────────────────────────────
monthly_px  = close.resample('ME').last()
monthly_ret = close.pct_change().resample('ME').apply(lambda x: (1+x).prod()-1)

vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
mom_12 = monthly_px / monthly_px.shift(12) - 1

# ── Allocation array (NaN except on first day of each month) ──────────
monthly_mask = ~close.index.to_period('M').duplicated()
alloc = np.full((len(close), len(UNIVERSE)), np.nan, dtype=float)

for idx in np.where(monthly_mask)[0]:
    date = close.index[idx]
    # Get monthly index for lookups
    m_idx = monthly_px.index.searchsorted(date) - 1
    if m_idx < 12:
        continue  # not enough history

    vol_row = vol_6.iloc[m_idx].dropna()
    mom_row = mom_12.iloc[m_idx].dropna()
    valid   = mom_row.index.intersection(vol_row.index)

    # TSMOM filter: only positive-12m assets eligible
    valid = [t for t in valid if mom_row[t] > 0]
    if not valid:
        # Nothing qualifies → 100% BIL (cash proxy)
        alloc[idx, UNIVERSE.index('BIL')] = 1.0
        continue

    # Composite score: rank(12m_mom) + rank(inv_6m_vol)
    valid_idx = pd.Index(valid)
    score = mom_row[valid_idx].rank() + vol_row[valid_idx].rank(ascending=False)
    winner = score.idxmax()

    # Allocate 100% to winner
    alloc[idx, :] = 0.0
    alloc[idx, UNIVERSE.index(winner)] = 1.0

# ── Backtest ─────────────────────────────────────────────────────────
pf = vbt.Portfolio.from_orders(
    close=close,
    size=alloc,
    size_type='targetpercent',
    group_by=True,          # treat as single portfolio
    cash_sharing=True,      # share cash across positions
    call_seq='auto',        # CRITICAL: sell before buy
    fees=0.001,             # 0.1% per trade
    init_cash=100_000,
    freq='1D',
)

print(f"Total return:  {pf.total_return():.2%}")
print(f"Sharpe ratio:  {pf.sharpe_ratio():.3f}")
print(f"Max drawdown:  {pf.max_drawdown():.2%}")
print(f"Annual return: {pf.annualized_return():.2%}")
```

**Key parameters explained:**
- `size_type='targetpercent'` — interpret `size` array as target % allocations (0→100%)
- `cash_sharing=True` — pool cash so selling one asset frees capital for buying another
- `call_seq='auto'` — **must be set** — processes sells before buys to prevent "insufficient cash" errors
- `group_by=True` — treat all assets as one portfolio rather than independent

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

pf = vbt.Portfolio.from_signals(price, entries, exits, fees=0.001, freq='1D')

# Results are a DataFrame — one column per param combo
print(pf.total_return().sort_values(ascending=False).head(10))
```

### Common pitfalls

1. **Forget `call_seq='auto'`**: Rebalance silently fails with "insufficient cash"
2. **`group_by` missing**: Without it, each asset is an independent portfolio — cash isn't shared
3. **NaN allocation rows**: Only fill on rebalance dates; leave as NaN otherwise (holds current position)
4. **12m momentum lookback**: Need `i < 12` guard at start of history to avoid NaN scores

### No live trading

Vectorbt is research-only. For execution, use Alpaca SDK directly (see `data-sources/alpaca-automation.md`).

---

## Recommendation for this project

| Use case | Tool |
|----------|------|
| H-series backtesting (classical momentum) | Custom yfinance+pandas engine (already built) |
| Parameter optimization sweeps | **Vectorbt** — speed decisive |
| Phase 3: Alpaca live execution | Alpaca SDK directly (see `alpaca-automation.md`) |
| ML-based signal research | Vectorbt or Qlib |
| Live execution simulation | Backtrader (event-driven mirrors real fills) |
| Cross-validation / walk-forward | Vectorbt or custom rolling-window engine |

For current H116 work, the custom engine is sufficient and already optimized. Vectorbt becomes valuable when scanning parameter spaces (e.g., testing 100 momentum lookback windows) or building ML signal pipelines.

---

## Spectre (GPU-Accelerated)

**GitHub**: search 'spectre factor backtesting GPU' on GitHub  
**Use case**: Large cross-sectional factor studies (500+ stocks, multi-year rolling windows)  

GPU acceleration via PyTorch/CUDA makes rolling-window factor computation 10–50× faster than pandas for large universes. Relevant when expanding beyond the current 30-stock universe for H167 (LightGBM cross-sectional) or low-vol decile studies (H191–H193) across full S&P 500.

**When to evaluate**: When current yfinance + pandas pipeline takes >10 minutes per backtest run — that's the crossover point where GPU setup overhead pays off.
