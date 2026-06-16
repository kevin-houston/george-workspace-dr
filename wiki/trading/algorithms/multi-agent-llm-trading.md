---
updated: 2026-06-16
---

# Multi-Agent LLM Trading

Research and synthesis on multi-agent Large Language Model architectures applied to trading strategy development and execution.

**Related pages**: [Crypto Trading Strategies](crypto-trading-strategies.md) | [Market Timing Overlays](market-timing-overlays.md) | [Backtesting Design Principles](../backtesting/design-principles.md)

---

## MadEvolve — Evolutionary Optimization (arXiv:2605.23007, 2025)

**Paradigm:** Island-model genetic algorithm with LLM agents as mutation/crossover operators.

**How it works:**
1. Initialize population of trading strategy parameter sets (lookbacks, thresholds, position sizing)
2. Split into isolated "islands"; each island runs LLM-guided evolution independently
3. Periodic migration: share best strategies across islands to prevent local optima
4. Fitness function: Sharpe ratio on IS window; OOS validation before acceptance

**Results (BTC futures, 2020–2024):**
- Outperforms baseline momentum and buy-and-hold on Sharpe and MaxDD
- Island migration critical: single-population LLM evolution converges prematurely
- GPT-4-class models significantly outperform GPT-3.5 as mutation operators

**Key distinction from MarketSenseAI / debater architectures:**
- No consensus or voting — pure evolutionary pressure selects strategies
- LLM role: generate strategy variants (code mutations), not market analysis
- Can evolve *any* parameterized strategy, not just sentiment-driven ones

**Relevance to production pipeline:**
- Could auto-optimize H302 (BTC MA lookback) or H303 (crypto momentum lookback/hold period)
- Crypto-native: BTC futures evaluation aligns with Kraken paper account
- No immediate production path — file as future research direction

**Code:** Not open-sourced in paper; island model implementable with LangChain + DEAP library

See also: [Market Timing Overlays](market-timing-overlays.md) (H296 VIX overlay), [Crypto Trading Strategies](crypto-trading-strategies.md) (H302/H303)
