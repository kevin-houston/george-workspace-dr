---
added: 2026-06-10
updated: 2026-08-05
category: algorithms
status: active research area — important reliability caveats
---

# Multi-Agent LLM Trading

Research and synthesis on multi-agent LLM architectures for trading: frameworks, coordination patterns, reliability caveats, production design lessons, and hypothesis integration.

**Related pages**: [NLP & Alternative Data](../tools/nlp-alternative-data.md) | [Machine Learning for Trading](../tools/ml-for-trading.md) | [Event-Driven Strategies](event-driven.md) | [Shared Evaluation Checklist](../shared-eval-checklist.md)

---

## Taxonomy: LLM Role in Trading Systems

Two fundamentally different roles for LLMs:

| Role | What the LLM does | Risk |
|------|-------------------|------|
| **Signal generator** | Converts unstructured text (8-K, earnings call) to numeric signal; downstream quantitative system makes decisions | Hallucination is bounded; signal validated by backtest |
| **Decision maker** | LLM directly decides position size, entry/exit, portfolio construction | Hallucination has direct P&L impact; hard to backtest reliably |

**Production preference**: signal generator role. H163/H174 (FinBERT on 8-K) is the confirmed example — LLM produces a sentiment score, a fixed threshold rule makes the trade. H274 (multi-agent PEAD debate) extends this: agents debate, but a score still gates entry.

---

## Overview & State of the Field (2026)

Multi-agent LLM trading systems decompose investment analysis across specialized agents that debate and synthesize findings before a portfolio decision is made. The pattern mirrors institutional trading firms: fundamental analysts, sentiment analysts, technical analysts, risk managers, and traders with distinct mandates.

**Key architectural insight (arXiv:2510.11695, Agent Market Arena):** "Agent frameworks display markedly distinct behavioral patterns, spanning from aggressive risk-taking to conservative decision-making, whereas model backbones contribute less to outcome variation." The framework design matters more than which LLM (GPT-4 vs Sonnet) powers it.

**Critical reliability issue (arXiv:2603.27539):** A March 2026 taxonomy paper identifies five evaluation failures that "can reverse the sign of reported returns":
1. Look-ahead bias — future information leaked into signals
2. Survivorship bias — only winning systems analyzed
3. Backtesting overfitting — excessive historical tuning
4. Transaction cost neglect — fees erode reported alpha
5. Regime-shift blindness — strategy works in one market regime only

Apply the [shared evaluation checklist](../shared-eval-checklist.md) to ALL multi-agent papers before treating results as credible.

---

## Major Frameworks

### TradingAgents (arXiv:2412.20138)

**GitHub**: https://github.com/TauricResearch/TradingAgents | **Stars**: ~84,900 | **License**: Apache-2.0

**Agent roles:**
- Fundamental, Sentiment, Technical Analysts (parallel, specialized)
- Bull & Bear Researchers — debate contradictory positions
- Risk Management Team — portfolio exposure monitoring
- Portfolio Manager — synthesizes debate + risk into final order

**Signal flow:**
```
Market data → Analyst agents (parallel)
                    ↓
             Bull/Bear debaters (sequential)
                    ↓
             Risk Manager (filters, sizes)
                    ↓
             Portfolio Manager → Order
```

**Results (paper, S&P 500 2024):** +15–30% cumulative vs buy-and-hold over 6 months. Debate reduces single-model overconfidence. GPT-4o > GPT-4 > GPT-3.5-turbo.

**Limitations:** 6-month eval window insufficient; 0% transaction costs; prompt sensitivity (small wording changes alter decisions ~30% of the time); no OOS Sharpe > 1.0 benchmark.

**Data sources:** Yahoo Finance (US, HK, Tokyo, London, India, Canada, A-shares, crypto), StockTwits, Reddit, MACD/RSI. Supported LLM providers: OpenAI, Anthropic, Google, xAI, DeepSeek, Qwen, GLM, MiniMax, OpenRouter.

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph

ta = TradingAgentsGraph(debug=False, llm_provider="openai",
                        deep_think_llm="gpt-4o", quick_think_llm="gpt-4o-mini",
                        max_debate_rounds=2, online_tools=False)
_, decision = ta.propagate("NVDA", "2026-06-21")
# {"action": "BUY|SELL|HOLD", "confidence": 0.73, "rationale": "..."}
```

**Relevance:** Architecture directly informs H274. Debater pattern: use for screening 8-K candidates before FinBERT scoring.

---

### HedgeAgents (arXiv:2502.13165)

**Paper**: "HedgeAgents: A Balanced-aware Multi-agent Financial Trading System" (Feb 2026)

**Architecture**: Fund manager (Otto) + 3 specialist experts + 23 financial tools + 3 memory categories.

| Agent | Domain | Key tools |
|-------|--------|-----------|
| Dave | Bitcoin/crypto | 60 technical indicators |
| Bob | Dow Jones/equities | Fundamental + price action |
| Emily | Forex | Currency analysis, macro factors |
| Otto | Fund manager | Budget allocation, portfolio coordination |

**Coordination:** Budget Allocation Conference (every 30 days), Experience Sharing Conference, Extreme Market Conference (triggered on >5%/day moves).

**Reported performance (2021–2023):** Sharpe 2.41 / MaxDD 14.21% vs FinGPT baseline Sharpe 1.93.

**Critical caveat:** Test period includes 2021 crypto bubble. $15 total LLM cost over 3 years is implausibly low. Single test window — fails regime coverage check. **Do not trust numeric claims; use for architecture reference only.**

---

### Expert Investment Teams (arXiv:2602.23330)

**Paper**: "Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks" (Feb 26, 2026) — Miyazaki, Kawahara, Roberts, Zohren (Oxford + Kyoto)

**Key innovation**: Fine-grained task decomposition vs. abstract "be an analyst" instructions — exact sub-tasks (extract revenue trend, compare vs consensus, flag narrative/numbers divergence) rather than role mimicry.

**Main finding:** Fine-grained decomposition "substantially enhanced risk-adjusted returns" vs. coarse-grained roles. **Leakage-controlled backtesting** (timestamp-locked information access) — a rare rigor standard. +8.7% annualized alpha vs S&P 500 (2022–2024 backtest, 50-stock).

**Relevance:** Dynamic routing complement to H174/H163 PEAD — on earnings events, activate NLP agents; on non-earnings days, fall back to momentum signals. Template for H274 upgrade.

---

### Agent Market Arena (arXiv:2510.11695)

**Paper**: "When Agents Trade: Live Multi-Market Trading Benchmark for LLM Agents" (Oct 2025)

First lifelong real-time benchmark across multiple markets. Four architectures (InvestorAgent, TradeAgent, HedgeFundAgent, DeepFundAgent) × five LLMs (GPT-4o, GPT-4.1, Claude-3.5-Haiku, Claude-Sonnet-4, Gemini-2.0-Flash).

**Key finding:** Framework architecture (conservative vs. aggressive) drives more behavioral variation than which LLM backend is used. DeepFundAgent (memory-based reasoning) shows distinct regime behavior. Validates that system design > model selection.

---

### MadEvolve — Evolutionary Optimization (arXiv:2605.23007, 2025)

**Paradigm:** Island-model genetic algorithm with LLM agents as mutation/crossover operators.

1. Initialize population of strategy parameter sets
2. Split into isolated "islands"; each runs LLM-guided evolution independently
3. Periodic migration: share best strategies across islands to prevent local optima
4. Fitness function: Sharpe on IS window; OOS validation before acceptance

**Results (BTC futures 2020–2024):** Outperforms baseline momentum on Sharpe and MaxDD. Island migration critical — single-population evolution converges prematurely. GPT-4-class significantly outperforms GPT-3.5 as mutation operator.

**Key distinction:** No consensus/voting — pure evolutionary pressure. LLM role is generating strategy variants (code mutations), not market analysis. Can evolve any parameterized strategy.

**Relevance:** Could auto-optimize H302/H303 crypto lookbacks. No immediate production path — future research direction.

---

## Coordination Patterns Compared

| Pattern | Example | Strength | Weakness |
|---------|---------|----------|---------|
| **Sequential debate** (bull/bear) | TradingAgents | Reduces overconfidence | Slow; 2× token cost |
| **Hierarchical authority** | HedgeAgents | Clear accountability; risk control | CEO agent can be wrong too |
| **Dynamic routing** | Expert Investment Teams | Token-efficient; context-aware | Routing layer adds latency |
| **Evolutionary** | MadEvolve | No bias; explores novel params | Slow convergence; large eval budget |
| **Diversity ensemble** | Self-Driving Portfolio | Each agent uses different methodology | Meta-agent weighting adds complexity |
| **Fixed scorer** | H163/H174 FinBERT | Backtestable; bounded hallucination | No context adaptation |

---

## Reliability Taxonomy (arXiv:2603.27539)

**Paper**: "Toward Reliable Evaluation of LLM-Based Financial Multi-Agent Systems" (Mar 2026)

### Four-Dimensional Taxonomy

| Dimension | Key questions |
|-----------|---------------|
| Architecture | Role decomposition, hierarchy, task granularity |
| Coordination | Protocol type, information flow, conflict resolution |
| Memory | Short-term context, long-term episodic, experience replay |
| Tool integration | Data sources, execution APIs, risk controls |

### Coordination Primacy Hypothesis (CPH)

"Inter-agent coordination protocol design drives trading performance more than model scaling alone." Supported by Agent Market Arena findings — framework design > LLM backbone.

### Coordination Breakeven Spread (CBS)

```python
def coordination_breakeven_spread(alpha_vs_single_agent, coordination_cost_per_trade,
                                  avg_trade_size, n_trades_per_year):
    total_extra_cost = coordination_cost_per_trade * n_trades_per_year
    total_portfolio_value = avg_trade_size * 20
    cost_drag = total_extra_cost / total_portfolio_value
    net_alpha = alpha_vs_single_agent - cost_drag
    return net_alpha, cost_drag

# Example: ~$100k portfolio, 50 trades/year, $0.50 extra LLM cost per decision
net_alpha, cost_drag = coordination_breakeven_spread(0.05, 0.50, 5000, 50)
# Cost drag ~0.005% — negligible at paper trading scale
# Becomes material at 10k+ trades/year
```

---

## NautilusTrader — Production Execution Engine

**GitHub**: https://github.com/nautechsystems/nautilus_trader | **Stars**: 25.4k | **License**: LGPL-3.0 | **Language**: Rust core + Python control plane

Not an LLM framework — the most relevant **production execution engine** for running strategies at scale with nanosecond-resolution backtesting. Full deep-dive (installation, adapter list, pricing, working backtest code, verdict) now at [tools/nautilus-trader.md](../tools/nautilus-trader.md) — updated 2026-08-10.

**Supported venues:** Binance, Coinbase, Kraken, Bybit, OKX, Deribit, Hyperliquid, dYdX, IBKR, Betfair, Polymarket. No native Alpaca adapter.

**Relevance:** If/when moving beyond Alpaca to IBKR or crypto execution — see tools/nautilus-trader.md for the H276/Kraken and Polymarket-backtester specifics. For Alpaca paper trading today, vectorbt + custom scripts remains simpler.

---

## Design Principles

### When LLM multi-agent adds value

1. **Qualitative signal synthesis** — earnings call tone, news context, macro narrative → structured signal, then quantitative pipeline (H163/H174 pattern)
2. **Hypothesis generation** — debate surfaces competing hypotheses before committing to a backtest (dream cycle application)
3. **Anomaly explanation** — when strategy underperforms, multi-agent reasoning over macro + micro context is faster than manual review

### When NOT to use

1. **Pure quantitative signals** — momentum, reversal, factor models don't benefit from LLM debate
2. **High-frequency decisions** — LLM latency (1–30s/call) incompatible with intraday execution; PEAD intraday scanner stays script-based
3. **Confirmed rule-based strategies** — don't add LLM complexity to H026/H041a/IBS that work well as pure rule-based systems

### Cost model (June 2026 pricing)

| Task | Calls | Model | Cost |
|------|-------|-------|------|
| Single-agent (GPT-4o-mini) | 1 | gpt-4o-mini | ~$0.002 |
| TradingAgents full debate (6 agents) | ~20 | gpt-4o-mini mix | ~$0.05–0.20 |
| HedgeAgents full conference | ~50 | GPT-4o | ~$0.50–2.00 |
| Expert Investment Teams (deep) | ~30 | gpt-4o | ~$0.30–1.50 |

At ~50 paper trades/year, even the most expensive setup costs <$100/year. Not a constraint until 1000+ decisions/year.

---

## Key Papers Summary

| Paper | arXiv | Year | Key Finding | Relevance |
|-------|-------|------|-------------|-----------|
| TradingAgents | 2412.20138 | 2024 | Specialized debate > single agent; 84.9k★ | High — try for H163/H174 upgrade |
| HedgeAgents | 2502.13165 | 2025 | Sharpe 2.41 reported; regime caveat | Medium — architecture only; numbers not trusted |
| Expert Investment Teams | 2602.23330 | 2026 | Fine-grained tasks > role mimicry; leakage-controlled | High — design template for PEAD upgrade |
| Agent Market Arena | 2510.11695 | 2025 | Framework > LLM backbone | High — benchmark validates architecture primacy |
| Reliability Taxonomy | 2603.27539 | 2026 | 5 eval failures; CBS metric | Critical — apply before trusting any paper |
| MadEvolve | 2605.23007 | 2025 | Evolutionary island model for strategy params | Low-medium — crypto only, future direction |
| Reproducibility Audit | 2605.19337 | 2026 | 2/19 extractable protocols; 0/19 fully reproducible artifacts | Critical — validates our eval checklist |
| StockBench | 2510.02209 | 2025 | Most LLMs fail to beat buy-and-hold | High — validates signal-generator role |
| Self-Driving Portfolio | 2604.02279 | 2026 | 50-agent diversity ensemble; meta-agent weighting | Medium — informs H318 proposal |

---

## Integration with H274 (Multi-Agent PEAD)

H274 (staged, not yet production) upgrades the PEAD pipeline to a 3-agent debate:

1. **FinBERT agent** (existing H163/H174): scores 8-K sentiment → score ≥ 0.18
2. **Analyst agent**: structured extraction of revenue guidance, management tone, forward guidance
3. **Contrarian agent**: identifies negative signals in otherwise positive releases

Architecture note: agents 1+2 are deterministic (existing code); agent 3 adds the LLM debate layer. Estimated cost: ~$0.02/candidate. Given H174 passes ~22 OOS events/year, cost ≈ $0.44/year — negligible.

**Implementation path:**
- Install TradingAgents in `/workspace/agent/venv/`
- Wire debate agent as post-filter on H174 candidates
- Backtest by replaying H174's 22 OOS events through debate; measure WR improvement
- Gate: WR improvement ≥ 2pp (H174 baseline 81.8%)

**Inspired by:** Expert Investment Teams (arXiv:2602.23330) fine-grained decomposition pattern + StockBench finding that LLMs should be signal-generators not decision-makers.

---

## Reproducibility Crisis (arXiv:2605.19337, May 2026)

Systematic audit of 77 LLM-based trading agent studies (screened through 2026-03-09); primary empirical subset n=19 satisfying Action Output + Closed-Loop Evaluation:
- **2/19** reported extractable, time-consistent evaluation protocols (extractable = train/test split clearly stated and recoverable)
- **1/19** included realistic transaction costs
- **1/19** addressed survivorship/universe handling
- **0/19** achieved R3 reproducibility (full re-runnable artifacts with code + data)

**Distinction**: "2/19 extractable protocol" (this audit) vs "0/19 fully reproducible" (arXiv:2603.27539 May 2026 reliability taxonomy) are different metrics — an extractable protocol means the split was stated; full reproducibility means code, data, and environment are available to re-run. Both metrics converge on the same conclusion: LLM trading research is not reproducible.

### 5-Component LLM Trading Agent Taxonomy (Xia et al. 2026)

The paper reframes LLM trading agents as **expert-system decision pipelines** with five components:

| Component | What it does | Common failure modes |
|-----------|-------------|---------------------|
| **Perceive** | Market data + news ingestion | Look-ahead via LLM training data |
| **Retrieve** | Context from memory/RAG | Stale context, retrieval hallucination |
| **Reason** | Decision logic (CoT, debate, vote) | Reasoning errors on quantitative inputs |
| **Emit** | Tradable action output | Ambiguous sizing, missing risk limits |
| **Adapt** | Feedback loop from outcomes | Catastrophic forgetting, overfitting to recent trades |

Most papers implement Perceive+Reason+Emit only; Retrieve and Adapt are frequently omitted.

**Implication for H274/H279/H280:** Reported Sharpe ratios (e.g., HedgeAgents 2.41) should be treated with extreme skepticism. Likely inflated by: (1) LLM knowledge lookahead (training data includes test period), (2) missing transaction costs, (3) cherry-picked windows.

**Action:** Before implementing any LLM-as-signal hypothesis, require: (1) strict OOS data cutoff (after LLM training cutoff), (2) transaction cost model, (3) comparison to H312-B (OOS Sharpe 1.202) as hurdle — not SPY.

---

## StockBench: LLMs Fail to Beat Buy-and-Hold (arXiv:2510.02209)

Most state-of-the-art LLMs **fail to outperform simple buy-and-hold** in real-world sequential trading, even models with strong financial QA performance.

- Strong static financial knowledge ≠ effective sequential decision-making
- Thinking models (o1, Gemini 2.0) make fewer arithmetic errors → better for position sizing
- Gap between financial knowledge and practical execution is substantial

**Design implication for H274:** Use LLMs in analyst role (signal extraction), not portfolio management (entry/exit decisions). FinBERT score + EPS surprise gate remain action triggers — not an LLM deciding to trade.

---

## FinRL-Trading & Lumibot

### FinRL-Trading (AI4Finance-Foundation)
**GitHub:** https://github.com/AI4Finance-Foundation/FinRL-Trading

Full-stack ML platform: ML stock selection → backtesting → live brokerage. Supports Alpaca live trading; built-in factor models compatible with H217/H228. **Relevance:** Potential Phase 4 infrastructure for H217 (alpha101, OOS 1.559) and H228 (alpha101+reversal, OOS 1.572) instead of bespoke Alpaca automation. **Risk:** ML pipeline complexity → harder fill attribution vs direct Alpaca API calls.

### Lumibot (Lumibot-Community)
Simpler backtesting + live trading for stocks and crypto. Lower learning curve than NautilusTrader. Pre-built risk management hooks. **Relevance:** H276 crypto POC alternative to NautilusTrader.

---

## The Self-Driving Portfolio (arXiv:2604.02279, April 2026)

**Source:** Andrew Ang (BlackRock), Nazym Azimbayev, Andrey Kim

**Architecture:** ~50 specialized agents, each implementing a different portfolio construction methodology. A **meta-agent** tracks past forecast accuracy against realized returns and weights outputs accordingly — learning which models to trust in which regimes. Constrained by an Investment Policy Statement (IPS) encoding risk limits and benchmark tracking error.

**Key difference from TradingAgents/HedgeAgents:** Diversity-maximizing ensemble (each agent = different methodology) rather than bull vs. bear debate. Meta-agent learns model-averaging weights dynamically.

**Relevance to production portfolio:** H026, H045, H041a are three different rotation methodologies with static allocations (27/21/22%). H318 proposal: simple meta-learner (logistic regression or rolling IC-weighting) that dynamically adjusts these weights monthly based on regime signals — e.g., if VIX > 25, weight H045 (bonds) higher; if momentum IC is high, weight H041a higher.

---

## Regime-Aware Communication Design (arXiv:2511.13614)

**Source:** arXiv:2511.13614 — "Market-Dependent Communication in Multi-Agent Alpha Generation" (Jerick Shi, Burton Hollifield, Nov 2025)

**Experiment:** 5-agent LLM trading systems tested across 450 experiments, 21 months. 5 communication structures: competitive debate, collaborative consensus, hierarchical, round-robin, broadcast.

**Key findings:**
- Competitive conversation outperforms in volatile tech stocks (high information uncertainty)
- Collaborative conversation outperforms in stable general stocks (shared signals dominate)
- Finance stocks resist all communication structures — fundamentals dominate
- All structures converge to similar agent *alignments* regardless of communication type

**Implication for H316/H319:**
Don't use a single communication structure for all pair types. Route by regime:
- Tech pairs (AAPL/MSFT/NVDA): Use competitive debate agents
- Utility/consumer pairs: Use collaborative consensus agents
- Financial pairs (BAC/JPM/WFC): Use fundamental-only agents, skip LLM communication

**Implementation:**
```python
def get_communication_structure(ticker_a, ticker_b, sector_map):
    sector = sector_map.get(ticker_a, 'Unknown')
    if sector in ['Technology', 'Communication Services']:
        return 'competitive'
    elif sector in ['Financials']:
        return 'fundamental_only'
    else:
        return 'collaborative'
```


---

## Reliability taxonomy & evaluation failures (arXiv:2603.27539, 2026)

**Source**: Nguyen & Pham, DMO-FinTech Workshop @ PAKDD 2026, Hong Kong.

**Coordination Primacy Hypothesis (CPH)**: Agent *coordination protocol design* matters more than model scale for trading quality. A well-coordinated smaller-model swarm can outperform a poorly-coordinated GPT-4 system.

**5 pervasive evaluation failures** the paper documents across 12 published systems:
1. Look-ahead bias — LLMs with training data that post-dates backtest period
2. Survivorship bias — only testing on surviving tickers
3. Backtesting overfitting — hyperparams tuned on the same OOS window
4. Transaction cost neglect — reporting gross not net returns
5. Regime-shift blindness — single-regime OOS window

**CBS (Coordination Breakeven Spread)**: minimum alpha the multi-agent system must generate, above a single-agent baseline, to justify the coordination overhead (extra API calls, latency, cost). If CBS > achievable alpha, revert to single agent.

**H274 implication**: Our PEAD 3-agent debate design should be evaluated against CBS before going live. If the 3-agent debate costs $X more per trade than a single FinBERT pass, the win-rate uplift must exceed that threshold.

---

## Profit Mirage: information leakage in LLM backtests (arXiv:2510.07920, 2025)

**Source**: Li et al., October 2025.

**Core finding**: LLM-based trading agent backtests show 'dazzling returns' that evaporate once the model's knowledge cutoff ends. The agent is effectively look-ahead biased via training data, not model architecture.

**4 leakage dimensions** examined:
1. Direct event memorization (LLM recalls specific price moves from training)
2. Sentiment bias from post-event reporting (training corpus skewed toward post-hoc explanations)
3. Company trajectory embedding (LLM knows which companies succeeded/failed)
4. Macro narrative leakage (LLM knows outcomes of 2022 rate hikes, etc.)

**Defense — FactFin**: Counterfactual perturbations at inference time force the model to reason causally rather than recall. Specifically: inject counterfactual event descriptions ('What if CPI had come in at 2.5% instead of 3.1%?') and test whether the model's conviction changes appropriately. Consistent-conviction models are memorizing; variable-conviction models are reasoning.

**Key implication for H163/H174 (PEAD)**: Our OOS window is 2023-2026 for a model trained through 2024. There is potential leakage for 2023 events that fall within training data. Safest evaluation: use only 2025-2026 events as the 'clean' OOS window and re-run H174 confirmation on that subset.

---

## 2026 Reproducibility Audit — Expanded Evidence

### PortBench: Correlation-Aware Portfolio Benchmark (May 2026)

**Source:** arXiv:2605.27887 — Zhao, Chen, Su; submitted May 27, 2026

First benchmark to evaluate LLM portfolio management with explicit asset correlation modeling. Spans six asset classes over a decade. Tests ten frontier LLMs.

**Key finding:** 90% of model-profile combinations fail to outperform a basic equal-weight allocation.

Even models that meet all procedural requirements still suffer catastrophic drawdowns under stress. Two novel metrics:
- **Dual-layer correlation score**: measures hedging effectiveness + concentration avoidance
- **CEPS**: tracks how reasoning errors accumulate across pipeline stages (retrieval → analysis → decision)

**Implication for our pipeline**: Our 40/30/30 static blend (H026/H041a/H045) outperforms what 90% of LLM portfolio agents achieve. LLMs as *portfolio managers* are unproven; as *signal components* (H163/H174 FinBERT, H343 OB filter) they add proven value at a well-defined stage.

### Agentic Trading Survey: 77 Studies Audited (May 2026)

**Source:** arXiv:2605.19337 — surveyed through 2026-03-09

Protocol-coded survey of 77 LLM trading studies. Only 19 meet the minimum bar (action output + closed-loop evaluation).

| Criterion | Studies passing (n=19) |
|-----------|------------------------|
| Time-consistent data splits | 2/19 (11%) |
| Explicit transaction cost model | 1/19 (5%) |
| Universe/survivorship handling | 1/19 (5%) |
| Execution timing documented | 11/19 (58%) |
| R3 reproducibility | **0/19 (0%)** |

Reframes LLM-based trading agents as expert-system decision pipelines rather than autonomous traders.

**Conclusion**: Our research checklist (shared-eval-checklist.md) already requires time-consistent splits and transaction costs — this survey confirms these are rare in the academic literature, meaning our results are more rigorous than 94-95% of published work in this space.

---

## Reproducibility Audit Update (2026-07-04)

### Agentic Trading Survey (arXiv:2605.19337)

**"Agentic Trading: When LLM Agents Meet Financial Markets"**
- **arXiv**: 2605.19337 | Protocol-coded review through 2026-03-09
- **Scope**: 77 studies screened; 19 primary studies meeting minimum standards for analysis
- **Framework**: Architecture-Capability-Adaptation lens; expert-system decision pipeline characterization

**Key reproducibility findings (extends prior 0/19 audit):**

| Metric | Count (of 19 primary studies) |
|--------|-------------------------------|
| Extractable time-consistent protocols | 2 |
| Explicitly models transaction costs | 1 |
| R0 (lowest reproducibility) | 15 |
| R3 (fully reproducible) | 0 |

This is the largest systematic audit of LLM trading research to date. The prior finding ("0/19 fully reproducible" in the multi-agent section) now has a broader base: 77-study sample, 2026 systematic methodology, same conclusion.

**Implication for our pipeline**: Any LLM trading system (H274 PEAD upgrade, H280 MarketSenseAI, H318 meta-learner) that does NOT meet minimum standards — realistic transaction costs, time-consistent signals, OOS evaluation — should not be prioritized. The CBS cost metric remains the right screening gate.

---

## New GitHub Reference: ai-hedge-fund (49.6k★)

**Repository**: [github.com/virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund)  
**Stars**: 49,600+ (most popular AI finance repo on GitHub as of 2026-07)

**Architecture:**
- Distinct investment philosophy agents: bull analyst, bear analyst, fundamentals analyst, technicals analyst, risk manager, portfolio manager
- Agents debate investment decisions; votes weighted by **recent accuracy** (dynamic accuracy weighting, not static role weights)
- Outcome: weighted aggregation across all views

**Key difference from TradingAgents (84.9k★)**: ai-hedge-fund uses accuracy-weighted voting rather than static role hierarchy. Bull/bear research agents that have been right recently get higher weight — adaptive credibility scoring.

**Practical takeaway for H274/H280**: The accuracy-weighted aggregation pattern is directly applicable to multi-agent PEAD (H274). If we run multiple scoring agents (FinBERT, GPT-4o, BART) and track each agent's realized WR per quarter, weighting by recent accuracy could improve the ensemble signal vs equal-weight averaging.

---

## Adversarial Robustness: AutoRedTrader (arXiv:2605.09185, May 2026)

**Source**: "AutoRedTrader: Automated Red-Teaming for LLM-Based Trading Agents" (May 2026)

First systematic adversarial robustness framework specifically for LLM trading agents. Generates synthetic misinformation (fake earnings leaks, fabricated analyst upgrades, spoofed regulatory filings) and injects it into the agent's information feed.

### Key Quantitative Findings

| Metric | Value | Notes |
|--------|-------|-------|
| Misinformation exposure rate | **69%** | Fraction of trading decisions where synthetic misinformation was present in context |
| Attack success rate | **26.67%** | Fraction of adversarial injections that caused a wrong trade |
| Return degradation | **2–3×** | Performance drop under adversarial vs clean conditions |
| Best defense: RAG filtering | **46% reduction** in attack success | Source credibility scoring + retrieval filtering |

### Attack Taxonomy

1. **Direct injection** — fake news article in information feed; agent cites it in reasoning
2. **Semantic camouflage** — misinformation framed as analyst commentary; bypasses keyword filters
3. **Temporal displacement** — old, real negative news re-dated to look current
4. **Consensus forgery** — multiple synthetic sources agree on wrong fact; social proof exploited

### Defense Strategies Evaluated

| Defense | Attack success reduction | Implementation cost |
|---------|--------------------------|---------------------|
| Source credibility scoring | ~35% | Low — add source domain reputation filter |
| RAG-based filtering | ~46% | Medium — retrieval pipeline modification |
| Adversarial fine-tuning | ~28% | High — requires labeled adversarial examples |
| Multi-source consensus (majority vote) | ~22% | Medium — only effective vs direct injection |

### Implications for H274 / H280

**H274 (Multi-Agent PEAD)**: Our pipeline uses EDGAR 8-K filings (official SEC source) — direct injection risk is low. Primary risk is semantic camouflage in earnings call transcripts or management commentary. Mitigation: source-lock all LLM context to EDGAR URLs; reject any non-SEC content.

**H280 (MarketSenseAI)**: Uses external news APIs — higher injection risk. Require source credibility score > 0.7 on all ingested news before LLM processing.

**Production guardrail**: Add source-origin assertion to every LLM context block:
```python
context = f"[SOURCE: SEC EDGAR, filing_id={accession_number}, verified]"
# Never pass unverified third-party content to trading agent LLMs
```

**H274 CBS implication**: The 26.67% attack success rate under adversarial conditions means multi-agent systems without source verification could underperform a single-source FinBERT baseline. The Coordination Breakeven Spread (CBS) analysis must include adversarial exposure risk, not just API cost.

---

## TS-Agent: Structured Agentic Workflow for Financial Time Series (arXiv:2508.13915)

**Source**: Ang, Bao et al. (August 2025). "Structured Agentic Workflows for Financial Time-Series Modeling." arXiv:2508.13915. GitHub: yinshuo-thu/TS-Agent.

**Architecture** (4-stage closed-loop pipeline):
1. **Planner LLM** — receives forecasting task, decomposes into model selection + refinement subproblems with contextual reasoning
2. **Model knowledge bank** — catalog of time-series architectures (ARIMA, LSTM, Transformer, XGBoost) with performance metadata per market regime
3. **Code refinement loop** — generates, executes, evaluates Python code; feeds back error/metric signals to planner
4. **Fine-tuning controller** — adjusts hyperparameters based on experimental feedback

**Beats AutoML**: +12% forecasting accuracy over traditional AutoML on financial benchmarks (Sharpe +0.3–0.5). Outperforms existing agentic systems (ReAct, Reflexion) by adding domain-specific model bank.

**Relevance to production stack**:
- **H274 (multi-agent PEAD upgrade)**: TS-Agent's refinement loop pattern maps to H274's 3-agent debate structure. Add a code-refinement agent that generates and evaluates scoring thresholds.
- **H318 (meta-agent ETF rotation selector)**: TS-Agent's model bank pattern maps to H318's regime-to-strategy routing. Use TS-Agent as the planner that selects H026/H041a/H045 weighting by regime.

**Install**: `pip install ts-agent` (verify current install path at yinshuo-thu/TS-Agent)

---

## 2026 Research Synthesis (added 2026-07-07)

### arXiv:2602.23330 — Expert Investment Teams via Fine-Grained Task Decomposition

**Authors**: Miyazaki, Kawahara, Roberts, Zohren (Feb 2026, Japanese stock data)

**Core finding**: Fine-grained task decomposition (explicit workflows: data fetch → signal compute → portfolio construction → risk check) significantly improves risk-adjusted returns vs coarse-grained instructions ("analyze and trade"). Conventional multi-agent approaches relying on abstract instructions degrade inference performance and reduce transparency.

**Relevance to H274**: H274's 3-agent PEAD debate currently uses coarse-grained prompts. Upgrading to fine-grained roles (Agent 1: 8-K section extractor, Agent 2: FinBERT scorer, Agent 3: EPS surprise validator) should improve consistency and reduce hallucination.

---

### arXiv:2603.27539 — Reliable Evaluation of LLM Financial Multi-Agent Systems

**Authors**: Nguyen (Georgia Tech), Pham (Adobe) — March 2026

**Key contributions**:
1. **4-D taxonomy**: architecture pattern, coordination mechanism, memory architecture, tool integration
2. **Coordination Primacy Hypothesis (CPH)**: inter-agent coordination protocol is the primary driver of quality — greater influence than model scaling
3. **5 pervasive evaluation failures** that can reverse reported return signs:
   - Look-ahead bias (unlagged signals)
   - Survivorship bias (H312 caveat applies)
   - Backtesting overfitting
   - Transaction cost neglect
   - Regime-shift blindness
4. **Coordination Breakeven Spread (CBS)**: metric for whether coordination adds value net of transaction costs

**Critical implication for H274**: Apply CBS framework before production deployment. The paper warns that many reported multi-agent improvements vanish after applying realistic costs and regime-shift tests.

**Alignment with existing pipeline**: The 5 evaluation failure checks are already in the production hypothesis gate (look-ahead: .shift(1) note in H256; survivorship: caveat on H272/H277/H312). This paper formalizes what the pipeline already does empirically.

---

### arXiv:2604.19476 — Cross-Stock Predictability via LLM-Augmented Semantic Networks

**Authors**: Huang, Fan, Hu, Ye (April 2026, S&P 500 2011-2019)

**Method**: Two-stage — (1) build sparse candidate graph from 10-K embeddings, (2) LLM classifies candidate edges by economic relation type (supply chain, competitor, customer), (3) aggregate pair-level mean-reversion signals into stock-level trading signals.

**Results**: LLM edge filtering improves long-short Sharpe 0.742 → 0.820 and reduces MaxDD from -10.47% to -7.85% on S&P 500 constituents.

**Relevance to H316 (LLM pairs trading)**: This is a direct refinement of the H316 concept. The method avoids pure cointegration pair selection (which H307 confirmed fails OOS) by using LLM semantic economic relations as the primary filter. Key question: does it hold OOS 2020-2026 (COVID + rate shock regimes)?

**Implementation path for H316**: Replace Johansen cointegration scan with 10-K embedding graph → LLM edge classification → mean-reversion signal aggregation. Start with 50 S&P 500 names from H198 universe.

---

### arXiv:2602.07048 — LLM Semantic Filtering for Lead-Lag Trading

**Authors**: (Feb 2026, Kalshi prediction markets)

**Method**: Two-stage causal screener: (1) Granger causality identifies candidate leader-follower pairs, (2) LLM semantic stage re-ranks by economic plausibility of transmission mechanism.

**Key finding**: Semantic filtering is most valuable during large leader moves and outperforms Granger screening alone across 18 rolling evaluations.

**Relevance**: Parallel approach to arXiv:2604.19476. Note: tested on prediction markets (Kalshi), not traditional equities — transferability uncertain.

---

### PortBench: LLMs Fail at Portfolio Allocation (arXiv:2605.27887, May 2026)

**Title**: PortBench: A Correlation-Aware, Full-Pipeline Benchmark for LLM-Driven Portfolio Management
**Authors**: Wisdomchain Research (2026)
**Key finding**: Evaluating 10 frontier LLMs on 183-instrument dataset (6 asset classes, 10 years), **90% of model-profile combinations fail to outperform equal-weight diversification**. Models treat covariance structures as noise and output near-uniform weights.

**Why this matters for H318 and production strategy**:
- H318 proposed using LLM meta-agents to dynamically weight H026/H041a/H045 — PortBench suggests LLMs cannot reliably optimize portfolio weights even with full data access
- Momentum rules (H026 top-1 selection) outperform LLM allocation precisely because they exploit a structural pricing anomaly, not optimize a covariance matrix
- LLM value: constraint adaptation (e.g., "avoid sectors with negative TSMOM") and tail-risk awareness (e.g., "reduce exposure when VIX>30"), NOT return-to-covariance optimization

**H318 implication**: Rather than LLM-driven weight allocation, meta-learner should use momentum rules for selection (H026/H041a/H045 unchanged) and LLM as a regime-conditional *filter* or *risk manager* only.

---

## Summary Table (2026)

| Paper | Method | Relevance | Hypothesis |
|-------|--------|-----------|------------|
| 2602.23330 | Fine-grained task decomposition | High | H274 PEAD upgrade |
| 2603.27539 | Evaluation taxonomy + CBS metric | High | All multi-agent work |
| 2604.19476 | 10-K semantic graph + LLM edge filter | High | H316 LLM pairs |
| 2602.07048 | Granger + LLM semantic filter | Medium | H316, H319 |
| 2605.27887 | PortBench portfolio allocation | High | H318 redesign |

## Reproducibility Crisis in LLM Trading Research (arXiv:2605.19337)

**Source**: Xia et al. (Mar 2026 review cutoff, 77 studies) — 'Agentic Trading: When LLM Agents Meet Financial Markets'
**Scope**: Systematic audit of ALL published LLM trading agent studies through March 2026

**Findings**:
- 77 total studies reviewed; only **19/77 met minimum evaluation criteria**
- Of the 19 qualifying studies:
  - **2/19** report extractable time-consistent train/test split protocols
  - **1/19** reports an explicit transaction-cost model
  - **1/19** documents universe construction or survivorship handling
  - **0/19** achieved R3 (full) reproducibility — none
- Primary bottleneck: 'comparable evaluation protocols, execution semantics, and reproducible artifacts remain the field's immediate bottlenecks'

**Implication for H274/H381/H382 (multi-agent PEAD / LLM alpha discovery)**:
- This is empirical evidence that the Alpha Illusion checklist (H389) is NECESSARY, not paranoid
- Any LLM trading hypothesis must satisfy ALL 7 shared-eval-checklist.md criteria before being counted as confirmed
- The H174 PEAD pipeline (FinBERT on 8-Ks) passes this bar: time-consistent split (IS 2018-2022 / OOS 2023-2026), explicit $0 commission model (fractional shares), documented universe (S&P 500 8-K filers with earnings), and published in peer-reviewed JFQA (PEAD.txt precedent)
- H381/H382/H384 LLM-generated alpha hypotheses should be flagged as 'unconfirmed until reproducibility protocol documented'

---

## Fine-Grained Task Decomposition (arXiv:2602.23330, Feb 2026)

Miyazaki, Kawahara, Roberts & Zohren (Univ. Tokyo + Oxford) find that multi-agent trading system performance is driven by **task granularity**, not agent count. Evaluated on Japanese equity universe with financial statements, news, and macro data; leakage-controlled backtesting.

**Key findings:**

1. **Coarse role mimicry underperforms**: Systems assigning abstract 'analyst' and 'manager' roles reduce inference transparency and degrade returns — agents try to imitate a role without defined task boundaries.
2. **Fine-grained decomposition wins**: Breaking the investment workflow into specific bounded sub-tasks significantly improves risk-adjusted returns. Each sub-task produces structured output consumed by the next stage.
3. **Output alignment is load-bearing**: Intermediate outputs must explicitly encode what the next stage needs. A FinBERT score that isn't formatted for the synthesis agent is wasted computation.
4. **Portfolio optimization compounds the gain**: Low cross-correlation among sub-task agent outputs (e.g., EPS surprise vs. 8-K sentiment vs. momentum rank) can be explicitly exploited in the final combination step.

### Application to H274 (PEAD Multi-Agent Debate)

H274's current 3-agent debate design (advocate / skeptic / judge) is role-based. Per arXiv:2602.23330, a task-decomposed pipeline would likely outperform:

| Agent | Task | Output format |
|-------|------|---------------|
| Agent 1 | EPS surprise quantification | `{"eps_surprise": 0.08, "vs_consensus": "beat"}` |
| Agent 2 | 8-K FinBERT sentiment scoring | `{"score": 0.22, "uncertainty": "low"}` |
| Agent 3 | Pre-announcement momentum check | `{"mom_6m_rank": 0.82, "trend": "up"}` |
| Agent 4 | Synthesis + position sizing | Buy / No-buy + conviction weight |

This restructuring should be evaluated before implementing H274 in production.

---

## PortBench: Correlation-Aware LLM Portfolio Evaluation (arXiv:2605.27887, May 2026)

Zhao, Chen & Su introduce PortBench — the first portfolio management benchmark that evaluates LLM systems on **cross-asset correlation understanding**, not just return maximization.

**Dataset**: 183 instruments across 6 heterogeneous asset classes, 10 years, with stress-regime and investor-profile evaluation.

**Two evaluation layers:**
1. **Static QA** (6,269 questions, 7 task templates): Tests whether the LLM correctly answers questions about correlation structures, diversification tradeoffs, and regime-conditional volatility — without any trading.
2. **Dynamic 5-stage pipeline**: Market scanning → Signal generation → Portfolio construction → Risk management → Execution timing. Scored by **CEPS** (Correlation-adjusted Expected Portfolio Score).

**Key gap PortBench addresses**: Existing benchmarks reward concentrated high-return portfolios that are undiversified. Standard Sharpe rewards an LLM that piles into the best single asset. CEPS penalizes portfolios that ignore cross-asset correlation structure.

**Application to H318 (meta-agent ETF rotation selector)**:
- H318's known failure (NOT CONFIRMED): meta-agent selects ETFs that are all correlated with SPY — same risk, no diversification.
- PortBench's CEPS metric would have caught this: a correlated H026/H041a/H045 blend that all decline together scores poorly on CEPS even with high individual Sharpe.
- When H318 is revisited, use PortBench's evaluation framework: test whether the meta-agent can correctly answer correlation questions (static QA) before trusting its allocation decisions (dynamic pipeline).


---

## HedgeAgents: Balanced-Aware Multi-Agent Trading with Hedging Specialists (arXiv:2502.13165, Feb 2025)

Li, Zeng, Xing, Xu & Xu introduce HedgeAgents — a multi-agent LLM system specifically designed to prevent the ~20% drawdown that standard LLM trading systems suffer during volatility spikes.

**Core problem it solves**: Existing LLM trading agents optimize for return but lack structured hedging logic. When the market reverses, agents continue following momentum signals because there's no dedicated loss-mitigation mechanism.

**Architecture:**
- **Central fund manager agent**: Coordinates overall allocation; receives and synthesizes reports from hedging experts; makes final position decisions
- **Specialized hedging experts**: One per asset class (equities, bonds, commodities, FX, derivatives). Each expert independently assesses downside risk and hedging options in its domain
- **Three-conference coordination protocol**: (1) Pre-market conference — assess overnight developments; (2) Intraday conference — real-time reallocation triggers; (3) Post-market conference — performance review and strategy update

**Key Results:**
- 70% annualized return
- 400% total return over 3-year test period
- Explicitly reduces catastrophic drawdown during volatility events
- 'Investment experience comparable to human experts' (self-reported)

**Application to Current Pipeline:**

*H274 (multi-agent PEAD upgrade)*: The 3-stage conference mechanism maps cleanly onto the PEAD event-driven flow:
  - Pre-earnings conference: FinBERT agent + EPS agent align on entry signal
  - Intraday conference: momentum agent monitors post-entry drift
  - Post-event conference: exit signal synthesis (align with H378 ECT signal)

*H318 (meta-agent ETF selector)*: The central fund manager pattern directly addresses H318's known failure mode — selecting correlated ETFs — by requiring each ETF-domain specialist to independently assess correlation risk before the manager allocates.

**Critique**: 70% annualized return likely includes survivorship bias and favorable test period selection. No IS/OOS split described in abstract. Treat as architecture reference, not performance benchmark.

**Code**: No public release. Architecture can be replicated with Claude multi-agent via NanoClaw `create_agent` tool.

---

## Multi-Agent LLM Trading: 2026 State of Research

### Finding 1: Fine-Grained Task Decomposition Wins (Feb 2026)

**Source**: arXiv:2602.23330 — "Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks"

- Tested on Japanese equity market
- Fine-grained task decomposition (concrete analyst subtasks) significantly outperforms coarse-grained designs (generic 'analyst' + 'manager' roles)
- Key insight: **intermediate agent outputs** (what analysts hand off to decision-makers) are the critical performance driver
- Market-neutral strategy, equal long/short positions
- Integrates with standard portfolio optimization

**Implication for H274**: our 3-agent PEAD debate (H274 proposed) should decompose into SPECIFIC tasks: (1) 8-K sentiment scorer, (2) EPS surprise calculator, (3) risk screener — NOT generic 'analyst' and 'manager' roles.

### Finding 2: LLMs Fail at Portfolio Management (May 2026)

**Source**: arXiv:2605.27887 — PortBench: A Correlation-Aware, Full-Pipeline Benchmark for LLM-Driven Portfolio Management

- 6,269 correlation-aware QA questions across 6 asset classes, 10 years
- **90% of model-profile combinations fail to outperform equal-weight allocation**
- Even models scoring high on static financial QA had catastrophic drawdowns under stress
- Gap confirmed: financial knowledge != portfolio management skill

**Implication for our pipeline**: validates using LLMs as **narrow signal generators** (FinBERT on 8-K text = H174) rather than end-to-end portfolio managers. Do NOT use Claude to allocate between H026/H041a/H045 — that is better handled by our fixed production weights.

### Synthesis: Where LLMs Add Value

| Use case | LLM effectiveness | Our analog |
|---|---|---|
| Narrow NLP scoring (sentiment, tone) | HIGH | H174 FinBERT 8-K scoring |
| Fine-grained task decomposition | HIGH | H274 3-agent debate (if implemented) |
| Broad portfolio allocation | LOW (90% fail) | Do NOT use for H026/H041a/H045 weights |
| Factor selection from 200+ signals | MEDIUM | H406/H411 (alpha101 attention) |
| Earnings call transcript scoring | HIGH | H410 proposed ECT layer |


## MetaPS — Adaptive Programmatic Strategy Selection (arXiv:2606.22385)

**Paper:** Chen, Luo et al. (2026), arXiv:2606.22385, submitted June 21 2026. Chinese-language team (Zenglin Xu group).

**Core insight:** Instead of asking LLMs to directly generate market actions, let them *select among a library of programmatic strategies* (implemented as code modules). The selection model is trained via simulation.

### Architecture

1. **Strategy Library:** A fixed set of algorithmic strategies implemented as Python code modules. Each module accepts market state → outputs position/action. Examples: momentum (12-1m), mean reversion (RSI oversold), risk control (VIX>30 → cash), event-driven (earnings drift).

2. **Simulation-Guided Training:**
   - Roll out each candidate strategy in simulated/backtested markets
   - Identify market states where each strategy leads to better future outcomes
   - Convert (state, winning_strategy) pairs into **supervised fine-tuning (SFT) data**
   - Fine-tune a small LLM (0.8B–9B params) on this SFT dataset

3. **Inference (deployment):** No simulator needed. LLM observes current market state + strategy library descriptions → selects a strategy module → the strategy module executes and produces the final action.

### Key Results

| Configuration | Multi-stock Trading Sharpe | Goods-exchange Sharpe |
|---|---|---|
| Fixed-strategy baseline | ~0.8 | ~1.1 |
| Direct LLM decision-making | ~0.9 | ~1.2 |
| MetaPS (0.8B) | ~1.1 | ~1.5 |
| MetaPS (9B) | ~1.3 | ~1.7 |
| API-based LLM (GPT-4) baseline | ~1.0 | ~1.3 |

**Key finding:** Compact fine-tuned models (9B) can match or exceed GPT-4 on strategy selection because they're fine-tuned specifically on the simulation data. "Scaling" in this domain is about domain-specific fine-tuning, not raw parameter count.

### Connection to H318 Meta-Agent ETF Rotation Selector

**H318 PROPOSED:** Dynamically weight H026/H041a/H045 by regime (Ang et al. arXiv:2604.02279). MetaPS suggests a concrete implementation path:

1. Build a **strategy library** with three modules: H026 (sector/alts momentum), H041a (19-asset top-1), H045 (bond ETF rotation)
2. Use the last 12 months of walk-forward backtest results to identify which market states favor each strategy
3. Fine-tune a small LLM (or use XGBoost as a simpler substitute) to select the active strategy given current market state features (VIX, SPY 200MA, yield curve)
4. At each monthly rebalance: LLM selects strategy → strategy executes its pick

**Why MetaPS approach matters for H318:**
- The existing XALPHA / FactorEngine approaches generate new alphas; MetaPS *selects among confirmed alphas*
- Selection among a small confirmed library avoids overfitting risk better than generating new signals
- The SFT data from backtests is already available (all walk-forward results in the hypothesis log)
- Fine-tuning can be done with local models (llama.cpp or Ollama on the workspace) without OpenAI costs

### Differences from TradingAgents / HedgeAgents (already in this page)

| Framework | LLM role | Action type | Strategy library |
|---|---|---|---|
| TradingAgents | Decision-maker via debate | Direct position | None — LLM generates actions |
| HedgeAgents | Multi-agent portfolio | Direct allocation | None |
| **MetaPS** | **Selector** | **Picks code module** | **Fixed programmatic library** |
| H318 design | Selector | Picks confirmed strategy | H026/H041a/H045 |

MetaPS is the closest published analog to H318. The critical insight: **keeping LLMs as selectors rather than actors** dramatically improves reproducibility and cost-adjusted performance — consistent with the [Agentic Trading Survey 2026](../../ai-industry/agentic-trading-survey-2026.md) finding that only Pattern A (tool-augmented with fixed execution) shows consistent real-money results.

### Practical Caution

All MetaPS experiments are on simulated/backtested markets. No real-money OOS validation. The goods-exchange sandbox is synthetic. This is consistent with the reproducibility findings from the [LLM Alpha Validation Checklist](llm-alpha-validation.md): simulation results need paper-trading gate before production.

For H318, the right path: implement MetaPS selection logic with XGBoost (not LLM) as the selector first — avoids LLM inference cost at monthly rebalance — then consider LLM fine-tuning only if XGBoost selector shows positive OOS lift.

---

## TrustTrade: Selective Consensus Gate for H274 (arXiv:2603.22567, Mar 2026)

**Source**: Zhong et al. (Mar 2026) — "TrustTrade: Human-Inspired Selective Consensus Reduces Decision Uncertainty in LLM Trading Agents"

**Core finding**: Prior multi-agent trading systems apply *uniform trust* — all agent signals equally weighted regardless of inter-agent agreement. TrustTrade fixes this with **selective consensus**: aggregate only when agents show high semantic AND numerical agreement; route divergent signals to a no-trade decision rather than forcing a synthetic average.

**Additional components:**
- Deterministic temporal signals anchor each agent's reasoning to calendar context
- Reflective memory adjusts risk preferences based on recent outcome history (without retraining)
- Tested on high-noise periods (2024 Q1 and 2026 Q1); shows "mid-risk/mid-return" calibration vs extreme-regime behavior common in vanilla multi-agent systems

**Application to H274 (3-agent PEAD debate):**

H274 currently produces majority-vote signals from 3 agents (bear/bull/devil's advocate). TrustTrade's selective consensus pattern extends this:

1. Each agent outputs stance + reasoning text
2. Embed reasoning texts via `text-embedding-3-small` (OpenAI)
3. Compute pairwise cosine similarity between all reasoning pairs
4. **Entry gate**: only enter PEAD trade when ≥ 2/3 agents agree on direction AND mean cosine similarity > 0.70
5. High-divergence cases (cosine sim ≤ 0.70) → skip trade

```python
from openai import OpenAI
import numpy as np

client = OpenAI()

def get_embedding(text: str) -> list[float]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=text)
    return resp.data[0].embedding

def selective_consensus_gate(agent_stances: list[str], agent_reasonings: list[str],
                             min_agreement: float = 0.70) -> tuple[str, float]:
    """
    Returns (decision, consensus_score).
    decision: 'enter' | 'skip'
    """
    embeddings = [get_embedding(r) for r in agent_reasonings]
    emb = np.array(embeddings)
    # Pairwise cosine similarities
    norms = np.linalg.norm(emb, axis=1, keepdims=True)
    normed = emb / norms
    sim_matrix = normed @ normed.T
    # Mean off-diagonal similarity
    n = len(embeddings)
    off_diag = [(sim_matrix[i, j]) for i in range(n) for j in range(n) if i != j]
    mean_sim = float(np.mean(off_diag))

    positive_votes = sum(1 for s in agent_stances if s.lower() in ('buy', 'long', 'bullish'))
    majority_direction = 'buy' if positive_votes >= 2 else 'skip'

    if majority_direction == 'buy' and mean_sim >= min_agreement:
        return 'enter', mean_sim
    return 'skip', mean_sim
```

**Expected effect on H274**: reduces trade count from ~22/year (H174 baseline) to ~12–15 high-confidence events; should raise WR above 81.8% baseline by filtering low-consensus false positives.

**Implementation path**: (1) extend H274 agent debate to log per-agent stance + reasoning text, (2) add embedding-based consensus gate above, (3) backtest on H174's 22 OOS events, gate: OOS WR ≥ 85% at n ≥ 10/year.

**Cost**: `text-embedding-3-small` is $0.02/MTok. Three reasoning texts × ~300 tokens each = 0.9k tokens per event. At 22 events/year: ~$0.0002/year — negligible.

**Cross-references**: [H274 multi-agent PEAD], [H454 FinCom DoC], multi-agent-llm-trading.md#integration-with-h274

---

## Fine-Grained Task Decomposition for PEAD Multi-Agent (arXiv:2602.23330, Feb 2026)

**Source**: 'Toward Expert Investment Teams: A Multi-Agent LLM System with Fine-Grained Trading Tasks' (Submitted Feb 2026). Deployed on Japanese equities with prices, financials, news, macro data. Key finding: fine-grained task decomposition significantly improves risk-adjusted returns vs. coarse-grained designs.

**Implication for H274 PEAD multi-agent design**: The current H274 architecture (3-agent debate: bull/bear/neutral) is coarse-grained. The fine-grained pattern suggests 5 specialist agents instead:
1. **EPS Agent**: Classifies quantitative earnings surprise (magnitude, beat vs. miss, trend)
2. **Guidance Agent**: Extracts and scores management guidance tone and specificity
3. **Uncertainty Agent**: Weights risk/uncertainty language (analyst under-reaction target per arXiv:2511.15214)
4. **Analyst Divergence Agent**: Checks analyst consensus spread pre/post announcement
5. **Exit Trigger Agent**: Monitors for ECT reversal signals, hold duration, next-earnings proximity

Fine-grained decomposition: each agent sees a narrow slice of the problem → less hallucination, clearer accountability, easier debugging. Consensus rule: Enter if ≥ 3 of 5 agents give green signal; Exit if ≥ 2 agents give red signal.

**Cross-reference**: H274 (multi-agent PEAD upgrade); H423 (MTL-PEAD auxiliary signals); arXiv:2511.15214 (analyst behavioral bias).

---

## Research Lead: RAPTOR — Black-Litterman Aggregation of Agent Debate Views (CEUR-WS/OpenReview 2025, flagged 2026-08-03)

"RAPTOR: Reasoned Agentic Portfolio Trading with Orchestrated Rebalancing" (CEUR-WS/OpenReview 2025 workshop paper -- not core arXiv) proposes per-asset agent threads (analyst/researcher/risk-manager roles) that communicate via a schema-constrained JSON blackboard and debate bull/bear theses into confidence-scored BUY/HOLD/SELL views. The distinguishing contribution vs. TradingAgents (already in this page) and the H274 PEAD debate design: instead of a facilitator agent picking a single winning thesis per position, RAPTOR feeds every agent's confidence-scored view into a **Black-Litterman optimizer** as the model's 'investor views' input, blended with market-equilibrium priors to produce final portfolio weights across the whole book at once.

**Why this is a distinct lever, not a competing architecture**: H274 and TradingAgents both solve "what should agents conclude about position X" (a signal-generation problem). RAPTOR solves "how do N per-asset agent conclusions become a coherent set of portfolio weights" (a portfolio-construction/aggregation problem) -- it could in principle sit downstream of H274's PEAD debate output rather than replacing it, using Black-Litterman instead of e.g. equal-weighting all debate-approved PEAD candidates.

**Evidence caveats (why this is logged as awareness-only, not staged as a hypothesis)**:
- Workshop venue (CEUR-WS/OpenReview), not peer-reviewed or core arXiv -- lower vetting bar than most sources in this wiki
- No disclosed backtest Sharpe/return numbers found in the accessible material
- Black-Litterman itself requires a market-equilibrium prior (typically CAPM-implied) and a view-confidence-to-uncertainty-matrix mapping -- both are nontrivial design choices the paper's abstract doesn't specify in enough detail to replicate directly

**Action needed before staging a hypothesis**: locate the full paper text (not just abstract) to extract the confidence-to-uncertainty mapping method, and check whether `skfolio` or `Riskfolio-Lib` (both already have Black-Litterman implementations per their documentation) could serve as the aggregation-layer backend rather than hand-rolling BL math -- would turn this into a much smaller build if pursued.

---

## Design Input for H274: Multi-Agent Debate Strategies Survey (Motger et al., arXiv:2607.26212, added 2026-08-04)

"Multi-Agent Debate Strategies: Survey, Taxonomy, and Challenges" (Quim Motger, Marc Oriol, Jordi Marco, Xavier Franch; submitted 2026-07-28) systematically reviews 141 multi-agent-debate studies and finds the field has converged on one dominant pattern largely by convention:

> Static, fully connected topologies, verbatim exchange, short-term memory, and voting-based agreement protocols

— adopted across most reviewed systems without rigorous head-to-head comparison against alternatives. The paper explicitly notes "promising alternatives remain marginal" and calls for future cost-aware benchmarking and automated tuning, neither of which the field has produced yet.

### Taxonomy: three axes for designing H274's debate

1. **Participants** — who's in the debate, and are roles symmetric or asymmetric? (H274's design intent, per cross-references in quant-terminal-notes.md and fireworks-tech-graph.md, is a 3-agent structure — the paper's survey implies this should have deliberately *asymmetric* roles, e.g. a bull case, a bear case, and an evidence-auditor, rather than three symmetric agents voting.)
2. **Interaction mechanism** — how do agents exchange information? Default is verbatim full-text exchange (expensive, unstructured); the paper flags structured/constrained exchange formats as an underexplored alternative — relevant given the Quant Desktop Market Terminal's "Signal Desk evidence model" (already cross-referenced for H274) is exactly this kind of structured-evidence alternative to verbatim debate.
3. **Agreement protocol** — how does the debate resolve to a decision? Default is majority/plurality voting; the paper implies voting can mask disagreement that a scoring/weighting protocol would preserve as useful signal (e.g. a PEAD debate that ends 2-1 bullish contains different information than one that ends unanimous, and a pure vote discards that distinction).

### Actionable takeaway for H274

Before implementing H274, explicitly decide participants/interaction/agreement rather than defaulting to the convention this paper documents as unexamined. Concretely: (a) consider asymmetric roles (e.g. bull / bear / FinBERT-evidence-auditor) instead of three generic debaters; (b) consider structured evidence objects (score + citation + confidence, analogous to the Signal Desk journal schema already noted for H274) instead of free-text exchange, which also reduces token cost — directly relevant given the CrewAI ~18% token-overhead finding logged in agent-frameworks-2026.md; (c) preserve the vote split as a feature (e.g. confidence-weighted signal) rather than collapsing to a binary decision, consistent with how H174's FinBERT score is used continuously (≥ 0.18 threshold) rather than binarized.

**Not a new hypothesis number** — this is a design-input paper for the already-staged H274, filed so H274's eventual implementation starts from a deliberate protocol choice instead of the field's unexamined default.

## See Also

- [Quant Desktop Market Terminal](../../tools/quant-terminal-notes.md) — Signal Desk evidence model as a structured-exchange alternative to verbatim debate
- [Agentic Routing: Harness-Native Data Flywheel](../../tools/agentic-routing-2026.md) — H274/H318 routing analogy
- [Hitchhiker's Guide to Agentic AI](../../tools/hitchhikers-guide-agentic-ai.md) — Layer 4 multi-agent topology guidance
- [Agent Framework Ecosystem 2026](../../ai-industry/agent-frameworks-2026.md) — CrewAI token-overhead finding relevant to debate-exchange cost

---

## Research Lead: TradeLens — Agent Cost-Attribution Diagnostic (2026-08-05)

**Source**: Duan, Li, Wang, Zhang et al., "Can Agentic Trading Systems Pay for Their Own Intelligence?" arXiv:2607.10286, Jul 11 2026.

A diagnostic toolkit, not another architecture proposal: reconstructs trading trajectories to attribute P&L to specific agent decisions, then asks whether LLM inference cost is actually justified by incremental profit ("intelligence-to-profit conversion"). Flags concrete model-specific failure modes -- in the paper's tests, one model fails specifically at asset selection while another fails at timing, meaning cost-justification failures are not uniform across the pipeline but localized to specific agent roles.

**Why it matters here**: This maps directly onto the wiki's existing Coordination Breakeven Spread (CBS) metric already defined in this page -- TradeLens is effectively a more rigorous, trace-level version of the same cost-justification question CBS asks at a coarser grain. Directly applicable to auditing **H274** (the staged 3-agent PEAD debate design) once it goes live: per-agent-role attribution would answer whether each of the three debating agents is earning its token cost, or whether (as TradeLens found elsewhere) the failure is concentrated in one role.

## Research Lead: CGX — Consensus-Gated Execution, Bull/Bear Debate + Zero-Trade Meta-Evaluator (MDPI Electronics 15(15):3453, flagged 2026-08-18)

**Source:** https://doi.org/10.3390/electronics15153453 (MDPI *Electronics*, published ~early August 2026). WebFetch blocked with HTTP 403 on the MDPI page; the summary below is abstract/search-result level detail only, not full-text -- noted honestly rather than invented, consistent with this wiki's practice for fetch-blocked sources (cf. market-making.md's arXiv:2607.17991 entry).

**What it is:** A crypto-trading multi-agent architecture: two debating agents (Bull, Bear) argue a position, and a separate **Meta-Evaluator** agent gates execution -- critically, the Meta-Evaluator can produce **zero trades** when the Bull/Bear debate fails to reach sufficient convergence, rather than falling back to a majority-vote signal.

**Reported results (abstract-level, unverified against full text):**
- OOS Sharpe 1.90, MaxDD -11.6%
- ~3x the Sharpe of a trend-following baseline
- Validated in two experiments: a 52-week 2024 aggregation run, and a four-year 2022-2025 multi-regime run spanning 417 biweekly sessions

**How this differs from our existing designs:**
- **H274** (3-agent PEAD debate: advocate/skeptic/judge) always resolves to a signal via majority vote.
- **H461** (TrustTrade Selective Consensus Gate, arXiv:2603.22567) adds an embedding-based similarity gate on top of H274's vote, filtering low-consensus events, but still ultimately votes rather than abstains as a first-class agent output.
- **CGX's distinguishing feature** is that "produce no trade" is an explicit, first-class Meta-Evaluator output, not a downstream filter applied after a vote already happened. This is architecturally cleaner: the abstain decision is made by an agent with visibility into *why* the debate didn't converge, rather than a post-hoc embedding-distance threshold.

**Relevance / possible future direction (not staged as a hypothesis tonight):** If H274 is ever built out, consider whether the Meta-Evaluator's explicit-abstain pattern is a better fit than H461's post-hoc consensus gate -- it may reduce false-positive low-consensus trades earlier in the pipeline rather than filtering them after the fact. This is a crypto-domain result; translating the Bull/Bear + Meta-Evaluator pattern to 8-K/PEAD text signals and defining an equivalent "insufficient convergence" criterion for our domain is unscoped work, and the reported numbers are abstract-level only pending full-text verification. No hypothesis number assigned -- logged as a design reference only, same treatment as the 2026-08-03 RAPTOR and 2026-08-04 Motger et al. survey entries above.

**Cross-references:** [H274 multi-agent PEAD], [H461 TrustTrade Selective Consensus Gate], multi-agent-llm-trading.md#trusttrade-selective-consensus-gate-for-h274-arxiv260322567-mar-2026

**Caveat**: Abstract discloses no Sharpe/return/cost numbers -- this is a methodology/tooling paper, not evidence of alpha. Adopt the attribution technique when H274 is instrumented for live/paper trading; not a source of a new hypothesis on its own.

## Research Lead: CGX — Consensus-Gated Execution, Bull/Bear Debate + Zero-Trade Meta-Evaluator (MDPI Electronics 15(15):3453, flagged 2026-08-18)

**Source:** https://doi.org/10.3390/electronics15153453 (MDPI *Electronics*, published ~early August 2026). WebFetch blocked with HTTP 403 on the MDPI page; the summary below is abstract/search-result level detail only, not full-text -- noted honestly rather than invented, consistent with this wiki's practice for fetch-blocked sources (cf. market-making.md's arXiv:2607.17991 entry).

**What it is:** A crypto-trading multi-agent architecture: two debating agents (Bull, Bear) argue a position, and a separate **Meta-Evaluator** agent gates execution -- critically, the Meta-Evaluator can produce **zero trades** when the Bull/Bear debate fails to reach sufficient convergence, rather than falling back to a majority-vote signal.

**Reported results (abstract-level, unverified against full text):**
- OOS Sharpe 1.90, MaxDD -11.6%
- ~3x the Sharpe of a trend-following baseline
- Validated in two experiments: a 52-week 2024 aggregation run, and a four-year 2022-2025 multi-regime run spanning 417 biweekly sessions

**How this differs from our existing designs:**
- **H274** (3-agent PEAD debate: advocate/skeptic/judge) always resolves to a signal via majority vote.
- **H461** (TrustTrade Selective Consensus Gate, arXiv:2603.22567) adds an embedding-based similarity gate on top of H274's vote, filtering low-consensus events, but still ultimately votes rather than abstains as a first-class agent output.
- **CGX's distinguishing feature** is that "produce no trade" is an explicit, first-class Meta-Evaluator output, not a downstream filter applied after a vote already happened. This is architecturally cleaner: the abstain decision is made by an agent with visibility into *why* the debate didn't converge, rather than a post-hoc embedding-distance threshold.

**Relevance / possible future direction (not staged as a hypothesis tonight):** If H274 is ever built out, consider whether the Meta-Evaluator's explicit-abstain pattern is a better fit than H461's post-hoc consensus gate -- it may reduce false-positive low-consensus trades earlier in the pipeline rather than filtering them after the fact. This is a crypto-domain result; translating the Bull/Bear + Meta-Evaluator pattern to 8-K/PEAD text signals and defining an equivalent "insufficient convergence" criterion for our domain is unscoped work, and the reported numbers are abstract-level only pending full-text verification. No hypothesis number assigned -- logged as a design reference only, same treatment as the 2026-08-03 RAPTOR and 2026-08-04 Motger et al. survey entries above.

**Cross-references:** [H274 multi-agent PEAD], [H461 TrustTrade Selective Consensus Gate], multi-agent-llm-trading.md#trusttrade-selective-consensus-gate-for-h274-arxiv260322567-mar-2026
