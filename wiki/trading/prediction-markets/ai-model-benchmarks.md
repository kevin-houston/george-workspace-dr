---
created: 2026-05-29
updated: 2026-05-29
type: research
---

# AI Model Benchmarks on Prediction Markets

How well do frontier AI models actually perform as autonomous prediction market traders? This page synthesizes findings from the only known live real-capital evaluation.

---

## Prediction Arena (arXiv:2604.07355, Mar 2026)

**Setup:** 6 frontier models, each with $10,000 real capital, trading autonomously on Kalshi (57 days, Jan–Mar 2026). Same models also ran concurrently on Polymarket (real capital). 4 next-gen models ran a 3-day paper trading trial.

### Kalshi Leaderboard (57 days, real capital)

| Rank | Model | Total Return | Settlement Win Rate |
|---|---|---|---|
| 1 | glm-4.7 (Zhipu AI) | −16.0% | 18.9% |
| 2 | grok-4-20-checkpoint (xAI) | −20.0% | 31.5% |
| 3 | gpt-5.2 (OpenAI) | −20.5% | 20.9% |
| 4 | claude-opus-4-5 (Anthropic) | −25.9% | 24.4% |
| 5 | gemini-3-pro (Google) | −30.5% | 24.3% |
| 6 | grok-4-1-fast-reasoning (xAI) | −30.8% | 21.1% |

**Every model lost money** over 57 days. Key caveat: Kalshi's curated market set was dominated by weather contracts (71–97% of settled positions per model) — the benchmark effectively measured weather-forecasting accuracy.

### Polymarket Performance (same period, real capital)

Dramatically better results. Cohort 1 averaged −1.1% on Polymarket vs −22.6% on Kalshi over the concurrent Feb 9–Mar 9 window:

| Model | Polymarket Return | Win Rate |
|---|---|---|
| grok-4-20-checkpoint | −1.85% | **71.4%** — highest across all settings |
| glm-4.7 | −0.09% | 10.5% |
| gpt-5.2 | −0.42% | 43.5% |

Platform design explains much of the difference: Polymarket's open discovery format lets models search the full universe for favorable markets, rather than being confined to a curated set where weather dominates.

### Next-Gen Models (3-day paper trading, Mar 2026)

| Model | Kalshi | Polymarket |
|---|---|---|
| gpt-5.4 | +1.22% (5 trades) | −0.02% |
| claude-opus-4-6 | −0.11% (46 trades) | **−10.06%** (59 trades) |
| glm-5 | −4.09% (12 trades) | +0.30% |
| gemini-3.1-pro | 0 trades | **+6.02%** (76 trades) — best across any model |

Notable: gemini-3.1-pro-preview made zero Kalshi trades but achieved the best return of any model (+6.02%) on Polymarket. And claude-opus-4-6 was the worst Polymarket performer in Cohort 2 (−10.06%, 33.3% win rate).

---

## What Drives Performance

The paper identifies a stable hierarchy of success factors across both phases of the 57-day evaluation:

1. **Initial prediction accuracy** — the accuracy of a model's very first trade on each market is the strongest predictor of final outcome. Models that assess correctly from the start compound gains; those that don't spiral.

2. **Capitalizing when correct** — doubling down on winning positions. Win rates on added positions range from <40% (poor) to >80% (excellent) across models.

3. **Position sizing under uncertainty** — appropriately small sizing when conviction is low limits drawdown.

4. **Exit timing** — holding to settlement generally beats early exits. Most models show negative average PnL on early exits, suggesting they exit winners too soon and hold losers too long.

5. **Research quality** — quality of web search synthesis matters. Quantity does not.

6. **Research quantity** — **NO correlation with performance.** The most computationally intensive model (claude-opus-4-5, 886 trades) was not the best. "Prediction Arena rewards decision quality, not computational throughput."

---

## Behavioral Profiles

| Model | Style | Key Insight |
|---|---|---|
| grok-4-20-checkpoint | Selective, high-accuracy | 53.3% weather win rate — best in cohort. Occasionally takes large concentrated bets in unfamiliar domains (biggest single loss $927) |
| gpt-5.2 | Conservative, risk-controlled | Lowest settlement rate (16.6%) but exits small; biggest loss only $124 — disciplined |
| claude-opus-4-5 | High-volume generalist | 886 trades, spread across 6/7 market categories. Drawdown lower than bottom 2 despite high activity |
| glm-4.7 | Asymmetric exits | Quick profit-taking, holds losers. 0% win rate in Financial category (−$420 total) |
| gemini-3-pro | High-frequency, low-accuracy | Monotonic decline from day 1 — activity without accuracy accelerates loss |
| grok-4-1 | Low-frequency, concentrated | Fewest trades (129), largest concentrated bets, worst weather accuracy (15.8%) |

---

## Platform Choice Is Critical

| Platform | Avg Return (Cohort 1, concurrent period) | Best Model |
|---|---|---|
| Kalshi (curated) | −22.6% | grok-4-20 (−1.85%) |
| Polymarket (discovery) | −1.1% | grok-4-20 (71.4% win rate) |

Kalshi advantages: controlled comparison, same opportunity set for all models.  
Polymarket advantages: open universe, models can find favorable markets, suits models with strong search/synthesis.

**Strategic implication:** If deploying an AI agent on prediction markets, Polymarket is likely the better venue. The curated Kalshi format becomes a domain-specific test (currently weather) rather than a general intelligence benchmark.

---

## Practical Takeaways for Our Pipeline

1. **Don't over-search** — research quantity is uncorrelated with prediction market performance. Lean, high-quality synthesis beats exhaustive search.

2. **First-call quality is paramount** — before entering any market, the first assessment must be high-conviction. Models that were right early compounded; those that were wrong early spiraled.

3. **Holding vs. exiting** — hold winning positions to settlement rather than taking early exits. Early exits average negative PnL across all models.

4. **Polymarket > Kalshi for AI agents** — if we expand Kalshi strategy work to include AI-agent execution, Polymarket's open discovery format likely produces better outcomes.

5. **claude-opus-4-6 Polymarket caveat** — early 3-day result was −10.06%, worst in Cohort 2. Too small a window for conclusions, but worth monitoring.

---

## Only Profitable Run on Record

Before the formal evaluation, grok-4-20-checkpoint (labeled `mystery-model-alpha`) ran a prior 23-day live Kalshi trial and achieved **+10.9%** — the only profitable real-capital Kalshi run recorded in the study. Key characteristics:
- Settlement win rate: 55.2%
- Average PnL when correct: **+$63.89**
- Average PnL when wrong: **−$3.23**
- Max drawdown: only 4.1%

This represents the ideal profile: high accuracy + highly asymmetric win/loss outcomes + low drawdown.

---

## Source
[Prediction Arena (arXiv:2604.07355)](../../sources/prediction-arena-2026.md)

## See Also
- [Kalshi](kalshi.md)
- [Polymarket](polymarket.md)
- [Prediction Market Algorithmic Strategies](algorithmic-strategies.md)
