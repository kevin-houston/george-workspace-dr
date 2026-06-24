---
updated: 2026-06-24
stars: 943
url: https://github.com/quarkfin/qf-lib
---

# qf-lib — Event-Driven Python Backtester

**quarkfin/qf-lib** (943 stars, Python, actively maintained June 2026)

Modular Python library providing an advanced event-driven backtester and tools for quantitative finance. Integrated with various data vendors and brokers. Supports Crypto, Stocks, and Futures.

## Why it matters

- More modular and broker-integrated than backtrader (which is effectively unmaintained)
- Event-driven model handles corporate actions, dividends, and order types correctly
- Has portfolio analytics, risk metrics, and performance attribution built in
- Connects to multiple data providers and brokers out of the box

## Key Features

- `BacktestTradingSession` — full event-driven backtester with realistic order simulation
- `LiveTradingSession` — same interface for live trading
- Broker integrations: Interactive Brokers, Quandl, Bloomberg (enterprise), Crypto exchanges
- Data providers: Quandl, Bloomberg, Alpaca (community extensions)
- Built-in performance metrics: Sharpe, Sortino, drawdown, exposure, turnover

## When to use

| Scenario | Tool | Reason |
|----------|------|--------|
| Monthly ETF rotation (H026/H041a) | vectorbt | Faster vectorized BT, no event overhead |
| Options strategies with assignment risk | qf-lib | Event-driven handles exercise/assignment correctly |
| Intraday with complex order logic | qf-lib | OrderFactory supports bracket/OCA/contingent orders |
| Quick alpha screening across universe | vectorbt | Less overhead for pure signal testing |

## vs Backtrader

qf-lib is the maintained successor to backtrader for Python event-driven backtesting. Backtrader's last commit was 2023; qf-lib is actively developed with better modern Python compatibility and data vendor integrations.

## Relevance to pipeline

- H266 (iron condor): event-driven model handles options roll/assignment mechanics that vectorbt lacks
- H309 (dispersion): multi-leg options requires event ordering that vectorbt can't model
- Not replacing the existing vectorbt/yfinance setup for ETF rotation — overhead not worth it for monthly signals
