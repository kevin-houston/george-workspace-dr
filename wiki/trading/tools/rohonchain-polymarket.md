---
added: 2026-06-24
category: tools/prediction-markets
url: https://x.com/RohOnChain
status: active
---

# @RohOnChain — Polymarket Arbitrage Math

Roan (@RohOnChain) writes technical deep-dives on prediction market quantitative trading, specifically Polymarket CLOB arbitrage.

## Focus

- **Venue:** Polymarket Central Limit Order Book (CLOB)
- **Strategy:** Arbitrage extraction via mathematical optimization
- **Core algorithms:** Adaptive Fully-Corrective Frank-Wolfe + Bregman Projection
- **Position sizing:** Kelly Criterion (Optimal position = (Edge × Win Prob) / Odds)
- **Key result documented:** Top Polymarket bots extracted $40M guaranteed arbitrage in one year; top single trader made $2M+

## Key Article (June 2026)

"The Math Needed for Trading on Polymarket (Complete Roadmap)" — covers:

1. **Bregman projections** for portfolio rebalancing under constraints
2. **Frank-Wolfe algorithm** for convex optimization in CLOB execution
3. **Proposition 4.1** — guaranteed profit formula: `D(μ̂||θ) - g(μ̂)`, stop at 90% extraction
4. **Kelly Criterion** for bet sizing
5. **Execution risk** — CLOB sequential execution creates timing gaps that naive bots miss

## Relevance to Pipeline

**Low.** Different asset class (prediction markets, not equities/ETFs/options). However:

- Kelly Criterion position sizing is universal — cross-reference with `wiki/trading/backtesting/position-sizing.md`
- Frank-Wolfe optimization appears in H329 (options portfolio under skew-t) — conceptual overlap
- Prediction market math is distinct enough from equity market structure that strategies don't transfer directly

Not worth implementing for our pipeline; useful as background reading on optimization-based execution.
