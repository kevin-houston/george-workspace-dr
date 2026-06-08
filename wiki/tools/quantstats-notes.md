---
title: QuantStats — Portfolio Analytics & Tearsheet Generator
added: 2026-06-08
category: tools
url: https://github.com/ranaroussi/quantstats
---

# QuantStats

Python library for portfolio performance analysis, risk analytics, and HTML tearsheet generation. Drop-in complement to any pandas/yfinance backtest workflow.

**Install:** `pip install quantstats --upgrade` (Python 3.10+)

## Key Features

- **50+ metrics:** Sharpe, Sortino, Calmar, volatility, max drawdown, win rate, alpha/beta, tail ratio, VaR, etc.
- **Plots:** Equity curve, rolling Sharpe, drawdown periods, monthly return heatmap, return distribution
- **Reports:** `qs.reports.html()` → full HTML tearsheet with benchmark comparison (SPY default); `qs.reports.basic()`, `qs.reports.metrics()`, `qs.reports.full()`
- **Monte Carlo:** Probabilistic analysis built-in

## Usage Pattern

```python
import quantstats as qs

# returns = pandas Series of period returns (daily or monthly)
qs.reports.html(returns, benchmark="SPY", output="tearsheet.html")
qs.plots.snapshot(returns, title="My Strategy")
print(qs.stats.sharpe(returns))
```

Accepts the same `pd.Series` that comes out of a yfinance + pandas backtest loop — no reformatting needed.

## Relevance to Backtesting

**High value.** Every run_hNNN.py script currently prints stats manually. QuantStats could:
- Generate polished HTML tearsheets for each confirmed hypothesis
- Add monthly return heatmaps and rolling Sharpe plots automatically
- Standardize benchmark comparison across all hypotheses

**Gotcha:** Win rate measures *periods* with positive returns, not individual trades — correct behavior for monthly-rebalance momentum strategies.

## Integration Idea

Add a `qs.reports.html(ret_series, benchmark="SPY", output=RESULT_DIR / "h{N}_tearsheet.html")` call at the end of each backtest script after gate evaluation.
