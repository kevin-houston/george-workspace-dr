---
added: 2026-06-10
updated: 2026-06-21
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

**GitHub**: https://github.com/nautechsystems/nautilus_trader | **Stars**: 23.4k | **License**: LGPL-3.0 | **Language**: Python (API) + Rust (core)

Not an LLM framework — the most relevant **production execution engine** for running strategies at scale with nanosecond-resolution backtesting.

| Feature | NautilusTrader | Vectorbt | Backtrader |
|---------|---------------|----------|------------|
| Core | Rust | Python/Numba | Python |
| Backtest resolution | Nanosecond (tick) | Bar | Bar |
| Live trading | 20+ venues | ✗ | Limited |
| Research→prod | Same code | ✗ | ✗ |
| Crypto | 10+ native | ✗ | ✗ |

**Supported venues:** Binance, Coinbase, Kraken, Bybit, OKX, Deribit, Hyperliquid, dYdX, IBKR, Betfair, Polymarket.

**Relevance:** If/when moving beyond Alpaca to IBKR or crypto execution. For Alpaca paper trading today, vectorbt + custom scripts remains simpler.

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
