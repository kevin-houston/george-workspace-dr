---
created: 2026-05-29
updated: 2026-05-29
type: source_summary
arxiv: "2604.07355"
source_file: sources/2604.07355v1.pdf
authors: Jaden Zhang, Gardenia Liu, Oliver Johansson, Hileamlak Yitayew, Kamryn Ohly, Grace Li (Arcada Labs / Harvard)
evaluation_period: "2026-01-12 to 2026-03-09"
---

# Prediction Arena: Benchmarking AI Models on Real-World Prediction Markets

**arXiv:** 2604.07355v1 (submitted March 28, 2026)  
**Institutions:** Arcada Labs + Harvard University

Live benchmark evaluating six frontier AI models as autonomous prediction market traders with $10,000 real capital each on Kalshi and Polymarket.

---

## Setup

- **Cohort 1:** 6 frontier models, live trading, Jan 12–Mar 9 (57 days), real capital
- **Cohort 2:** 4 next-gen models, paper trading, Mar 6–9 (3 days), simulated capital
- Each model gets the same system prompt, tools (web search, note-taking, trading API), and $10,000 starting capital
- Cycles every 15–45 minutes; 15% position concentration limit per market
- Account value = cash + mark-to-market at bid prices (liquidation value)

**Kalshi:** Curated 29-market set across 7 categories — Financial, Crypto, Weather, Politics, Entertainment, Sports, Meta/AI  
**Polymarket:** Open discovery — models search the full market universe

---

## Cohort 1 Results — Kalshi (57 days, live capital)

| Model | Phase 1 Return | Total Return | Win Rate | Max DD |
|---|---|---|---|---|
| glm-4.7 (Zhipu AI) | −7.2% | **−16.0%** | 18.9% | 16.3% |
| grok-4-20-checkpoint (xAI) | −4.4% | −20.0% | 31.5% | 30.9% |
| gpt-5.2 (OpenAI) | −11.9% | −20.5% | 20.9% | 18.4% |
| claude-opus-4-5-20251101 | −7.2% | −25.9% | 24.4% | 25.9% |
| gemini-3-pro-preview | −25.3% | −30.5% | 24.3% | 30.8% |
| grok-4-1-fast-reasoning | −26.8% | **−30.8%** | 21.1% | 30.8% |

All models lost money. Phase 1 spread: $2,221. Total spread: $1,473 ($8,398 vs $6,925).

**Pre-evaluation historical run:** grok-4-20-checkpoint (labeled `mystery-model-alpha`) achieved +10.9% in a prior 23-day run — the **only profitable real-capital Kalshi run** recorded. Settlement win rate 55.2%, avg PnL when correct: +$63.89 vs when wrong: −$3.23.

---

## Cohort 1 Results — Polymarket (Feb 9–Mar 9, live capital)

| Model | Return | Win Rate | Trades |
|---|---|---|---|
| grok-4-20-checkpoint | −1.85% | **71.4%** | 18 |
| glm-4.7 | −0.09% | 10.5% | 95 |
| gpt-5.2 | −0.42% | 43.5% | 127 |
| gemini-3-pro-preview | −1.81% | 14.3% | 155 |
| claude-opus-4-5-20251101 | −2.68% | 33.3% | 86 |
| grok-4-1-fast-reasoning | 0.00% | N/A | 0 |

**Kalshi vs Polymarket:** avg −22.6% on Kalshi vs −1.1% on Polymarket over same period. Dramatic contrast.

---

## Cohort 2 Results (3-day paper trading, Mar 6–9)

**Kalshi:**
| Model | Return | Trades |
|---|---|---|
| gpt-5.4 | +1.22% | 5 |
| claude-opus-4-6 | −0.11% | 46 |
| glm-5 | −4.09% | 12 |
| gemini-3.1-pro-preview | 0.00% | 0 (no trades) |

**Polymarket:**
| Model | Return | Win Rate | Trades |
|---|---|---|---|
| gemini-3.1-pro-preview | **+6.02%** | 50% | 76 |
| glm-5 | +0.30% | N/A | 4 |
| gpt-5.4 | −0.02% | N/A | 1 |
| claude-opus-4-6 | **−10.06%** | 33.3% | 59 |

gemini-3.1-pro-preview made zero Kalshi trades but achieved the best return of any model (+6.02%) on Polymarket — platform design profoundly shapes which capabilities are expressed.

---

## Key Findings

### 1. Hierarchy of Success Factors (in order)
1. **Initial prediction accuracy** — quality of first call on a market; highest Phase 1 predictor
2. **Capitalizing when correct** — adding to winners; some models >80% win rate when doubling down, others <40%
3. **Position sizing under uncertainty** — lower MaxDD models manage risk better
4. **Exit timing** — holding to settlement generally beats early exit (early exits average negative PnL across models)
5. **Research quality** — matters more than quantity
6. **Research quantity** — NO correlation with performance. Most computationally intensive model (claude-opus-4-5, 886 trades) was NOT the best.

### 2. Platform Design Matters Enormously
- Kalshi's curated markets functioned as a **weather-forecasting benchmark**: 71–97% of each model's settled positions were weather markets
- grok-4-20-checkpoint led Kalshi performance by having the best weather accuracy (53.3%)
- Polymarket's open discovery format suits models with strong market-search capabilities
- Same model can perform very differently on the two platforms (gemini: 0 Kalshi trades, +6.02% Polymarket)

### 3. Weather Dominated Kalshi Evaluation
- Temperature/precipitation contracts (short-duration, daily) flooded the curated market set
- Weather win rates ranged from 15.8% (grok-4-1) to 53.3% (grok-4-20) — closely mirrors overall leaderboard
- In effect, the benchmark tested weather forecasting ability, not general intelligence

### 4. Model Behavioral Profiles
- **grok-4-20-checkpoint:** selective, high-accuracy, occasional large concentrated bets outside core domain
- **gpt-5.2:** conservative, low settlement rate (16.6%), controlled losses, disciplined sizing
- **claude-opus-4-5:** high-volume generalist, meaningful exposure across 6/7 categories, controlled drawdown despite 886 trades
- **glm-4.7:** asymmetric exits (quick profit-take, holds losers), 0% win rate in Financial category
- **gemini-3-pro:** high frequency, monotonic decline from day 1 — high activity without accuracy accelerates loss
- **grok-4-1-fast:** low frequency, large concentrated bets in weather, systematically wrong

### 5. Research ≠ Performance
Token usage per cycle shows no correlation with trading performance. Prediction Arena rewards decision quality, not computational throughput.

---

## Limitations Acknowledged
- Kalshi curated set skewed heavily toward weather → results may not generalize
- Paper trading (Cohort 2) has execution advantage — no counterparty rejection
- 3-day Cohort 2 window is statistically insufficient
- Standardized system prompt may not elicit best performance from all models
- Bid-ask spreads and counterparty rejection affect live trading in ways paper trading doesn't capture

---

## Relevance to Our Pipeline

| Finding | Relevance |
|---|---|
| All Kalshi models lost money | Our Kalshi strategies need to account for AI agent difficulty; human judgment supplement likely needed |
| Polymarket dramatically better for AI | Future prediction market work should prioritize Polymarket over Kalshi |
| claude-opus-4-6 poor Polymarket performance (−10.06%) | Concerning early signal — our current model runs at this version |
| Research quality > quantity | Validates lean approach (don't over-search; synthesize well) |
| Initial accuracy is #1 factor | Focus on first-call quality over position management |
| Weather dominated Kalshi benchmark | Kalshi evaluation may not reflect real general forecasting ability |

---

## Cross-References
- [Kalshi](../trading/prediction-markets/kalshi.md)
- [Polymarket](../trading/prediction-markets/polymarket.md)
- [Prediction Market Algorithmic Strategies](../trading/prediction-markets/algorithmic-strategies.md)
- [AI Model Benchmarks on Prediction Markets](../trading/prediction-markets/ai-model-benchmarks.md)
