---
added: 2026-06-11
category: tools/backtesting-frameworks
url: https://github.com/0xemmkty/QuantMuse
license: MIT
status: active (Python 3.8+)
---

# QuantMuse — Comprehensive Quant Trading System with AI/ML

A Python quantitative trading framework combining traditional multi-factor models with LLM/ML integration. MIT license, no API keys required for basic use (Yahoo Finance is the free default data source).

---

## Architecture

```
Python layer (data_service/)
  ├── Data fetchers (Binance, Yahoo Finance, Alpha Vantage)
  ├── Factor analysis (FactorCalculator, FactorScreener)
  ├── Strategy framework (8+ built-in strategies)
  ├── Backtesting engine (BacktestEngine)
  ├── AI/ML (OpenAI GPT, XGBoost, Random Forest, Neural Nets)
  └── Web UI (FastAPI + Streamlit dashboard)
         ↓
C++ core engine (backend/)
  ├── Order execution (low-latency)
  ├── Risk management (VaR, CVaR, drawdown, leverage)
  └── Portfolio management
```

---

## Key APIs

**Factor analysis:**
```python
from data_service.factors import FactorCalculator, FactorScreener

# Calculate momentum, value, quality, size, volatility factors
calculator = FactorCalculator()
factors = calculator.calculate_all_factors(symbol, prices, volumes)

# Screen stocks with multi-factor filter
screener = FactorScreener()
results = screener.create_momentum_screener().screen_stocks(factor_data)
```

**Backtesting:**
```python
from data_service.backtest import BacktestEngine
from data_service.strategies import MomentumStrategy

engine = BacktestEngine(initial_capital=100000)
strategy = MomentumStrategy()
results = engine.run_backtest(strategy, historical_data)
```

**LLM integration:**
```python
from data_service.ai import LLMIntegration

llm = LLMIntegration(provider="openai")
analysis = llm.analyze_market(factor_data, price_data)
```

---

## Install

```bash
pip install -e .[ai,visualization,realtime,web]

# C++ backend (optional, for low-latency execution):
cd backend && mkdir build && cd build && cmake .. && make -j4
```

Data sources: Binance, Yahoo Finance (free, no key), Alpha Vantage.
API keys: all optional in `config.json`.

---

## Built-in strategies

8+ strategies included (exact list not documented in README). The strategy registry makes it easy to add custom strategies alongside built-ins.

---

## Relevance to George's work

**Moderate overlap with existing stack:**
- Factor analysis API (`FactorCalculator`) is cleaner than our raw pandas implementations — could speed up prototyping new factor hypotheses
- `BacktestEngine` is a higher-level abstraction vs. our raw `run_hNNN.py` scripts, but less flexible for custom IS/OOS splits and regime conditioning
- LLM integration design is similar to H279 (news-filtered momentum) and H280 (MarketSenseAI replication) — could borrow the `LLMIntegration` wrapper pattern
- Streamlit dashboard is a faster alternative to our custom HTML EOD dashboard for ad-hoc exploration

**Where it falls short for us:**
- No EDGAR/SEC filing support — can't replicate PEAD pipeline
- No FRED macro data integration — no regime conditioning
- Data sources (Binance, Yahoo Finance) already covered in our stack
- C++ execution engine is overkill at paper trading stage
- No after-tax return modeling or walk-forward CPCV rigor
- README has generic placeholders ("yourusername/tradingsystem") suggesting early-stage maturity

**Best use case:** quick factor screening prototypes or as a reference implementation for `FactorCalculator` patterns. Not a replacement for our `run_hNNN.py` pipeline.

---

## Cross-references

- [Machine Learning for Trading](ml-for-trading.md) — LightGBM/XGBoost cross-sectional prediction; QuantMuse overlaps here
- [Backtesting Design Principles](../backtesting/design-principles.md) — IS/OOS rigor; QuantMuse's BacktestEngine needs validation against these standards
- [Qlib](qlib.md) — Microsoft's AI quant platform; more rigorous and production-tested than QuantMuse
