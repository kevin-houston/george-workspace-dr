---
updated: 2026-05-20
type: tool
status: not relevant — TypeScript/Tradier, abandoned in favor of commercial SaaS
---

# NextTrade

Web-based GUI for composing, backtesting, optimizing, and deploying trading strategies.

- **GitHub**: https://github.com/austin-starks/NextTrade
- **Stars**: 1.8k stars, 282 forks
- **Language**: TypeScript 98.9%
- **License**: MIT
- **Status**: Effectively abandoned — README redirects to NexusTrade (commercial SaaS)
- **Last meaningful code commit**: ~3–4 years ago; only README updated since

---

## What it does

Full-stack Node.js app (MongoDB + React frontend):

1. **Visual strategy builder** — compound conditions (AND/OR logic over price/vol/mean signals), composed in a GUI
2. **Portfolio management** — multiple portfolios with different strategy combos
3. **Backtesting** — historical data; stocks only (crypto/options "baked into architecture" but not implemented)
4. **Genetic algorithm optimization** — evolves strategy parameters; tune mutation rate, population size, training/validation windows; optimize for Sharpe/Sortino/gain/drawdown
5. **Live deployment** — one-button live trading via Tradier broker

---

## Why it's not relevant

- **TypeScript, not Python** — incompatible with our research stack
- **Tradier broker only** — no Alpaca support
- **Abandoned** — author replaced it with NexusTrade (paid cloud platform); no active maintenance
- **GUI-first** — designed for non-programmers composing strategies visually, not factor research or ML pipelines
- **No ML/factor layer** — no Qlib-style feature engineering or cross-sectional ranking

The genetic algorithm parameter optimization is the one genuinely interesting feature we lack. If we ever need it, `deap` or `scipy.optimize` in Python would be the implementation path.

---

## vs our existing tools

| Feature | NextTrade | Our Stack |
|---------|-----------|-----------|
| Language | TypeScript | Python |
| Broker | Tradier | Alpaca |
| ML/factors | ✗ | Qlib, LightGBM |
| Vector backtest | ✗ | Vectorbt |
| Event-driven | basic | Backtrader, LEAN |
| Genetic algo optimization | ✓ | ✗ (could add via deap) |
| Active maintenance | ✗ | ✓ |

**Verdict**: Skip. Nothing here improves our stack.
