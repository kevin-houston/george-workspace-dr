---
title: ATLAS — Self-Improving AI Trading Agents
created: 2026-06-22
updated: 2026-06-22
category: trading/tools
source: https://x.com/tom_doerr/status/2068824434425610668
github: https://github.com/chrisworsey55/atlas-gic
stars: 1975
author: Chris Worsey, General Intelligence Capital
status: Open framework (MIT-adjacent) + SaaS (atlasagents.co); trained prompts NOT included
---

# ATLAS — Self-Improving AI Trading Agents

**ATLAS** (by General Intelligence Capital) is a multi-layer AI trading agent framework where agent prompts evolve through market feedback via Karpathy's autoresearch loop. The core insight: **agent prompts are the weights; Sharpe ratio is the loss function. No GPU needed.**

Shared by @tom_doerr on June 22, 2026. ~1,975 GitHub stars.

---

## Architecture — 4 Layers, 25+ Agents

### Layer 1 — Macro (10 agents)
Central bank, geopolitical, China, dollar, yield curve, commodities, volatility, emerging markets, news sentiment, institutional flow. Output: risk-on / risk-off regime backdrop.

### Layer 2 — Sector Desks (7 agents)
Semiconductor, energy, biotech, consumer, industrials, financials + a Bloomberg-style relationship mapper (supply chains, ownership, analyst coverage, competitive dynamics).

### Layer 3 — Superinvestors (4 agents)
- **Druckenmiller** — macro/momentum, asymmetric trades
- **Aschenbrenner** — AI/compute, capex cycle beneficiaries
- **Baker** — deep tech/biotech, IP moats
- **Ackman** — quality compounder, pricing power + FCF + catalyst

### Layer 4 — Decision (4 agents)
- **CRO** — adversarial risk officer (attacks every idea, finds correlated risks)
- **Alpha Discovery** — finds overlooked names
- **Autonomous Execution** — converts signals to sized trades
- **CIO** — synthesises all layers weighted by Darwinian agent scores, makes the final call

---

## The Autoresearch Loop

Inspired directly by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch):

1. System identifies **worst agent by rolling Sharpe**
2. Generates one targeted prompt modification
3. Runs for **5 trading days**
4. If agent's Sharpe improved → **git commit** (keep)
5. If not → **git reset** (revert)

Over 18-month backtest: 54 modifications attempted, 16 survived (30%). The system self-discovered that its CIO (portfolio manager) was its weakest component before humans diagnosed the same issue.

**Darwinian Weights:** Each agent's influence on the CIO is a float between 0.3–2.5. Top-quartile agents: ×1.05/day. Bottom-quartile: ×0.95/day. Good agents get louder; bad ones get quieter.

---

## Agent Spawning

When the same knowledge gap appears 3+ times in 5 days, the system creates a new specialist agent at neutral weight. In a 6-month test (Jul-Dec 2024):
- 9 agents spawned autonomously (credit markets, earnings calendar, options flow, liquidity, positioning, earnings guidance, retail sentiment, technical levels)
- 3 went extinct (stuck at minimum weight for 20+ days)
- 6 survived and reached maximum weight

The team grew from 25 → 31 agents with zero human involvement in deciding what to create or when.

---

## PRISM — Regime-Specific Cohort Training

Separate agent populations are trained on distinct historical market regimes:

| Cohort | Period | Return | Kept/Tried | Key Learning |
|--------|--------|--------|------------|--------------|
| Bull/Low Vol | 2016-2018 | +7.7% | 180/509 (35%) | Exit vol longs when events resolve peacefully |
| Crisis (COVID) | 2020 Q1-Q2 | -13.1% | 0/3 (0%) | **Crashes too fast for autoresearch — pre-train required** |
| Rate Tightening | 2022-2023 | -30.2% | 38/89 (43%) | 15-day minimum between reversals during Fed weeks |
| Recovery | 2020 Q2-Q4 | -29.0% | 0/1 (0%) | Same as crisis — too fast for feedback loop |
| Euphoria | 2021 | +14.3% | 119/243 (49%) | Cap conviction during political crises |

**Convergent evolution finding:** All 5 cohorts independently discovered the same meta-rules — cap conviction, VIX as regime filter, hard position limits, never override risk management. Nobody programmed caution; every cohort learned it from losses.

**Divergent evolution finding:** The same volatility agent (starting at 844 bytes) grew to 121k bytes in bull markets vs 10k in rate tightening — completely different survival strategies from the same starting prompt.

---

## JANUS Meta-Layer

Sits above all trained cohorts. Weights each cohort by recent predictive accuracy. The weight differential is an **emergent regime detector**:
- Short-window cohorts outperform → NOVEL REGIME
- Long-window cohorts outperform → HISTORICAL REGIME
- Roughly equal → MIXED

This is exactly what **H318** (meta-agent ETF rotation selector) proposes — JANUS is a working implementation of that concept.

---

## Soros Reflexivity Engine

Five feedback loops modelled explicitly:
1. **Price → Fundamentals**: drops >15% → credit downgrades, talent flight; rises >20% → cheap capital
2. **P&L → Behaviour**: fund drawdown >10% → forced selling cascade; gains >15% → concentration increases
3. **Narrative → Flows**: 3+ analysts converge → retail follows; contrarian narratives emerge after extended consensus
4. **Market → Policy**: equity drawdown >15% → CB signals easing; oil >$130 → SPR releases
5. **Reflexive Reversal Detection**: 5+ simulation rounds in one direction → crowded trade flag

---

## MiroFish Swarm Integration

Agents train overnight on **simulated futures** (not just historical data). Thousands of simulated market participants interact via MiroFish swarm engine; branching scenarios include geopolitical escalation, Fed policy shifts, earnings shocks, black swans. Agents that navigate these futures well get upweighted.

---

## Reported Results

- **18-month backtest (Sep 2024 – Mar 2026):** +22% in 173 deployment days
- **Best single pick:** AVGO at $152, +128%
- **SaaS live signals:** claimed "up 30% since launch" and "60% win rate on Kalshi" (marketing, not independently audited)
- PRISM cohorts: crisis and recovery cohorts both lost ~30% — important caveat

---

## What's Included vs. Not

**Included (open):** Framework architecture, autoresearch loop design, backtest methodology and results, PRISM design, agent spawning mechanism, JANUS design, Soros reflexivity engine, MiroFish bridge, **placeholder prompts only**.

**NOT included (proprietary):** Trained agent prompts, PRISM evolved prompts per regime, CIO active management rules, Darwinian weight values, live positions, MiroFish outputs. The trained prompts are the core IP — "a competitor starting today is hundreds of iterations behind."

---

## Tech Stack

- **Model:** Claude Sonnet (Anthropic API)
- **Data:** FMP, Finnhub, Polygon, FRED — same stack as George's trading pipeline
- **Infrastructure:** Azure VM, ~$20/month
- **Cost:** ~$50-80 for full 18-month backtest, ~$30 for five PRISM cohorts

---

## Key Insight

> The orchestration layer matters as much as the intelligence layer. Individual agents improved measurably through autoresearch. But portfolio returns depend on how signals are converted to sized positions. The synthesis/decision layer is the bottleneck. Improving individual agent intelligence without improving orchestration yields diminishing returns.

---

## Relevance to Production Portfolio

| ATLAS Component | Analogous George Hypothesis |
|---|---|
| JANUS meta-layer (weights cohorts by accuracy) | **H318** — meta-agent ETF rotation selector |
| PRISM regime-specific cohort training | **H323** — HMM+RL regime-aware ETF rotation |
| Darwinian agent weighting | H320 LightGBM crash filter (fitness-based gating) |
| Autoresearch loop (Sharpe = loss function) | Nightly dream cycle (arXiv scan + hypothesis proposals) |

**Practical observation:** PRISM crisis/recovery cohorts both failed (~-30%) because the autoresearch loop (5-day test) is too slow for fast-moving regimes. This is a direct validation of H323's hypothesis that HMM pre-trained regime detection outperforms reactive adaptation.

**Using the SaaS:** atlasagents.co, Pro at $49/month gives live signals + Alpaca copy-trading. Builder at $499/month adds full API, 18-month backtest dataset, marketplace publishing. Use code GITHUB20 for 20% off.

## Cross-References

- [Multi-Agent LLM Trading](../algorithms/multi-agent-llm-trading.md) — taxonomy and context; ATLAS fits "LLM as decision-maker" tier
- [Regime Detection](../algorithms/regime-detection.md) — PRISM is a Darwinian take on regime-specific training
- [Time-Series Foundation Models](../algorithms/ts-foundation-models.md) — ATLAS uses Claude Sonnet, not TSFMs; complementary rather than overlapping
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H318 (meta-agent), H323 (HMM+RL regime)
