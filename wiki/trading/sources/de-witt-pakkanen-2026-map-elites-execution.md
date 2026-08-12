---
added: 2026-08-12
category: theory / execution
url: https://arxiv.org/abs/2601.22113
---

# Diverse Approaches to Optimal Execution Schedule Generation (de Witt & Pakkanen, 2026)

**Authors**: Robert de Witt (Imperial College London / Bank of America Securities), Mikko S. Pakkanen (Imperial College London)
**Date**: February 2, 2026
**arXiv**: 2601.22113
**Source file**: `sources/arxiv_2601.22113.pdf`

---

## What This Paper Is

An RL-for-execution paper, not a signal-generation/alpha paper. It answers: *given a fixed parent order that must be filled within a time horizon H, how should you schedule the child trades to minimize implementation shortfall (slippage vs. arrival price)?* This is the same problem family as Almgren-Chriss and the Kearns & Shi (2025) strategic-trading paper already in this wiki, but tackled with model-free RL (PPO) plus a quality-diversity algorithm (MAP-Elites) borrowed from robotics/evolutionary computation.

Two contributions:
1. **GEO** (Gymnasium for Executing Optimally) — a calibrated execution simulator built on ~400 US equities' full year of 2022 minute-bar data (bid/ask/mid, depth, sided/hidden volume), with a transient market-impact model (exponential decay, square-root volume scaling, calibrated R²≈0.02-0.10 out-of-sample — modest but consistent with realistic microstructure noise).
2. **MAP-Elites over PPO** — instead of training one universal execution policy, evolve a grid of regime-specialist policies indexed by (volatility × liquidity) behavioral descriptors (3×3 grid), seeded from a baseline PPO-CNN.

---

## The Environment

- Episode = execution of one parent order over H minutes (H sampled 1-390 min, i.e. up to a full day).
- Baseline schedule = target % of expected market volume (POV-style); the RL agent scales this baseline up/down each minute via a 9-way discrete action `{-1, -0.75, ..., 1}` (-1 = pause, +1 = max acceleration).
- 13-dim observation: mid price, market volume, time remaining, remaining inventory, order size relative to ADV/expected-horizon-volume, last fill price/qty, immediate + cumulative impact cost, arrival benchmark, 1-day and 5-day Parkinson volatility.
- Orders are randomly sampled (symbol, date, horizon, size as % of expected horizon volume, side) from historical order flow characteristics — train/test split is strictly chronological (no leakage).

## Results

**PPO vs. baselines** (4,900 OOS orders, $21B total notional, ~$4.3M avg order size):

| Strategy | Arrival slippage (bps) | Total cost (bps) |
|---|---|---|
| VWAP | 5.23 | 476.11 |
| TWAP | 7.01 | 302.89 |
| POV | 4.07 | 211.71 |
| Random | 3.77 | 217.58 |
| PPO-MLP | 3.78 | 178.26 |
| **PPO-CNN** | **2.13** | **178.70** |

PPO-CNN beats VWAP by 59% and TWAP by 70% on arrival slippage; both PPO variants roughly halve total cost vs. TWAP. Both agents front-load execution (Almgren-Chriss-consistent), with the CNN moderating front-loading during adverse price drift — the architectural edge over MLP comes from the CNN jointly modeling correlated price/volume/inventory features rather than treating the 13 observation dims independently.

**MAP-Elites specialists**: 3 of 9 volatility×liquidity cells beat the baseline PPO-CNN by 8-10% (best: high-vol/medium-liquidity, +10.3%), but the high-vol/low-liquidity cell *degraded* -30.2% (overfitting on a data-sparse cell), and the grid-wide average was -2.4% *below* the CNN baseline. Authors' honest conclusion: quality-diversity execution specialists show promise but need validation-gated routing (deploy a specialist only where it's shown robust OOS gains, fall back to baseline elsewhere) rather than blanket deployment — this routing layer is left as future work, not built here.

---

## Practical Implications

### For current pipeline (ETF rotation, IBS, PEAD paper trading)
**Not directly relevant**, for the same reason the Kearns & Shi (2025) execution-game paper already logged in this wiki isn't: at ~$100k portfolio scale trading ETFs/large-caps in a handful of thousand-dollar clips per signal, we are price-takers. The paper's test set averages ~$4.3M per parent order against 400 mid/large-cap names — three orders of magnitude larger than any single order this portfolio places. Market impact and multi-bps arrival slippage are not a measurable drag at our size; the bid-ask spread and Alpaca's own fill mechanics dominate whatever residual cost exists, and neither VWAP-vs-market-order nor RL scheduling would move the needle on a $3-4k IBS entry.

### Where it would matter
If the portfolio scaled into the $1M+ per-trade range (single-name equity positions, not ETF baskets), GEO's PPO-CNN policy (or the underlying front-loaded scheduling intuition) would be directly actionable — it's a genuine, replicable execution-quality result, not multi-agent hype. The MAP-Elites piece is earlier-stage and, per the authors' own numbers, not yet net-positive to deploy as an ensemble.

### A scoped-down check worth doing instead
Rather than building an RL execution research project disproportionate to current position sizes (this paper alone required a custom Gymnasium environment, calibrated impact model on 400-name minute data, and 5.5 hours of MAP-Elites compute), the actionable next step — if this line is worth pursuing — is empirical, not a backtest: pull our own Alpaca paper-trading fills and compare fill price to mid-price at signal time across H174/H112/H026 order history. If realized slippage is already near-zero (expected, given order size vs. ADV for XLK/SMH/SPY-class names), that settles whether execution-cost optimization is worth any further research time here. If it's meaningfully non-zero, that would be the trigger to revisit this paper's approach at smaller scale.

---

## Cross-References

- [Strategic Trading Game — Kearns & Shi (2025)](kearns-shi-2025-strategic-trading.md) — same problem family (optimal execution / market impact), game-theoretic multi-player treatment instead of single-agent RL; same "not relevant at our scale, price-takers" conclusion
- [Market Microstructure & HFT](../algorithms/market-microstructure.md) — order book dynamics, Almgren-Chriss baseline this paper builds on
- [Deep RL for Trading](../algorithms/deep-rl-trading.md) — PPO/FinRL framework context; this paper is PPO applied to execution scheduling rather than signal generation/position sizing
- [Transaction Cost Modeling](../backtesting/transaction-costs.md) — square-root vs. linear impact law comparison (this paper empirically favors square-root, R²-tested)

---

## Citation

de Witt, R. and Pakkanen, M.S. (2026). "Diverse Approaches to Optimal Execution Schedule Generation." arXiv:2601.22113.
