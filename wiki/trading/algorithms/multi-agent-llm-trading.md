---
updated: 2026-06-17
---

# Multi-Agent LLM Trading

Research and synthesis on multi-agent Large Language Model architectures applied to trading strategy development and execution.

**Related pages**: [Crypto Trading Strategies](crypto-trading-strategies.md) | [Market Timing Overlays](market-timing-overlays.md) | [Backtesting Design Principles](../backtesting/design-principles.md) | [PEAD Strategy](../strategies/pead.md)

---

## Taxonomy: LLM Role in Trading Systems

Two fundamentally different roles for LLMs:

| Role | What the LLM does | Risk |
|------|-------------------|------|
| **Signal generator** | Converts unstructured text (8-K, earnings call) to numeric signal; downstream quantitative system makes decisions | Hallucination is bounded; signal validated by backtest |
| **Decision maker** | LLM directly decides position size, entry/exit, portfolio construction | Hallucination has direct P&L impact; hard to backtest reliably |

**Production preference**: signal generator role. H163/H174 (FinBERT on 8-K) is a confirmed example — LLM produces a sentiment score, a fixed threshold rule makes the trade. H274 (multi-agent PEAD debate) extends this: agents debate, but a score still gates entry.

---

## TradingAgents — Multi-Agent Framework (arXiv:2412.20138, 2024)

**Stars:** ~84,900 (GitHub: TauricResearch/TradingAgents)

**Architecture:**
- Specialized analyst agents: fundamentals, sentiment, technicals, macro
- Bull/bear debater agents that argue opposite sides of each trade
- Risk manager agent with position-sizing and stop-loss authority
- Portfolio manager agent synthesizes debate + risk output into final order

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

**Results (paper, S&P 500 stocks 2024):**
- +15–30% cumulative returns vs buy-and-hold over 6-month evaluation
- Debate pattern reduces single-model overconfidence substantially
- GPT-4o > GPT-4 > GPT-3.5-turbo; model quality gates outcome

**Limitations (paper-reported):**
- Evaluation window only 6 months — insufficient for full market cycle
- Transaction costs modeled at 0; live slippage would compress returns
- Prompt sensitivity: small wording changes alter decisions
- No OOS Sharpe > 1.0 benchmark; not production-ready as standalone

**Relevance to this project:**
- Architecture directly informs H274 (multi-agent PEAD debate)
- Debater pattern: use for screening 8-K candidates before FinBERT scoring
- Code: MIT license, pip installable (`pip install tradingagents`)

---

## HedgeAgents — Hedge Fund Simulation (arXiv:2502.13165, 2025)

**Architecture:** Simulates a hedge fund with C-suite + analyst hierarchy:
- CEO agent sets mandate and risk budget
- Sector analysts (technology, financials, healthcare, energy) generate per-sector alpha signals
- Risk officer enforces portfolio constraints
- Compliance agent checks regulatory limits (position concentration, restricted lists)

**Key finding:** Hierarchical authority structure outperforms flat peer-agent voting:
- CEO veto power prevents "groupthink" consensus that ignores tail risk
- Compliance agent catches 23% of trades that would breach simulated risk limits

**Coordination protocol:** Structured JSON memos passed between agents; strict turn order prevents circular dependencies.

**Why it matters here:** Risk management delegation (H249 regime-conditional weights) maps well to this architecture. A "risk officer" agent could dynamically adjust H249 regime weights based on real-time VIX + breadth signals rather than static monthly rebalance.

---

## Expert Investment Teams (arXiv:2602.23330, 2025)

**Paradigm:** Assemble specialist agents dynamically based on the *type* of instrument or market condition — a "team composition" layer sits above individual agents.

**Innovation:**
- Routing module selects which agents to activate for each decision
- E.g., earnings-day → FinBERT + macro agent; normal day → technical + momentum only
- Reduces token cost ~40% vs always-on full panel

**Results:** +8.7% annualized alpha vs S&P 500 (2022–2024 backtest, 50-stock universe)

**Relevance:** Dynamic routing = natural complement to H174/H163 PEAD. On earnings events, activate NLP agents; on non-earnings days, fall back to momentum signals. Staged as H274 extension.

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

**Key distinction from debater architectures:**
- No consensus or voting — pure evolutionary pressure selects strategies
- LLM role: generate strategy variants (code mutations), not market analysis
- Can evolve *any* parameterized strategy, not just sentiment-driven ones

**Relevance to production pipeline:**
- Could auto-optimize H302 (BTC MA lookback) or H303 (crypto momentum lookback/hold period)
- Crypto-native: BTC futures evaluation aligns with Kraken paper account
- No immediate production path — file as future research direction

**Code:** Not open-sourced in paper; island model implementable with LangChain + DEAP library

---

## Coordination Patterns Compared

| Pattern | Example | Strength | Weakness |
|---------|---------|----------|---------|
| **Sequential debate** (bull/bear) | TradingAgents | Reduces overconfidence | Slow; 2× token cost |
| **Hierarchical authority** | HedgeAgents | Clear accountability; risk control | CEO agent can be wrong too |
| **Dynamic routing** | Expert Investment Teams | Token-efficient; context-aware | Routing layer adds latency |
| **Evolutionary** | MadEvolve | No bias; explores novel params | Slow convergence; large eval budget |
| **Fixed scorer** | H163/H174 FinBERT | Backtestable; bounded hallucination | No context adaptation |

---

## Reliability Considerations

**Hallucination in trading context:**
- Factual errors (wrong ticker, wrong price) → direct loss if LLM is decision-maker
- Reasoning errors (inverted logic) → systematic bias if LLM drives signal
- Mitigation: treat LLM output as *one input to a quant model*, not final decision

**Prompt sensitivity:**
- Multiple papers report >10% decision variance from rephrasing the same context
- TradingAgents tested: "Is NVDA a buy?" vs "Should we enter NVDA?" → different answer 30% of the time
- Mitigation: structured JSON output schemas + temperature=0 + chain-of-thought

**Cost model (GPT-4o, 2025 pricing):**
- TradingAgents full panel: ~8,000 tokens/decision × $5/M = ~$0.04/stock/day
- 50-stock daily scan: ~$2/day, ~$500/year — manageable
- MadEvolve island evolution: ~$50–200/optimization run — use sparingly

---

## Integration with H274 (Multi-Agent PEAD)

H274 (staged, not yet production) proposed upgrading the PEAD pipeline to a 3-agent debate:

1. **FinBERT agent** (existing H163/H174): scores 8-K sentiment → score ≥ 0.18
2. **Surprise agent**: validates EPS surprise ≥ 0.02 (existing gate)
3. **Debate agent**: bull/bear argue the specific filing — final veto if bear case is strong

Architecture note: agents 1+2 are deterministic (existing code); agent 3 adds the LLM debate layer. Estimated cost: ~$0.02/candidate. Given H174 passes ~22 OOS events/year, cost ≈ $0.44/year — negligible.

Implementation path:
- Install TradingAgents (`pip install tradingagents`) in `/workspace/agent/venv/`
- Wire debate agent as post-filter on H174 candidates
- Backtest by replaying H174's 22 OOS events through debate; measure WR improvement
- Gate: WR improvement ≥ 2pp to justify latency + cost

---

## Quick-Start: TradingAgents

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["llm_provider"] = "openai"
config["deep_think_llm"] = "gpt-4o"
config["quick_think_llm"] = "gpt-4o-mini"
config["max_debate_rounds"] = 2
config["online_tools"] = False  # use our own data pipeline

ta = TradingAgentsGraph(debug=False, config=config)
state, decision = ta.propagate("NVDA", "2024-01-15")
# decision: {"action": "buy", "confidence": 0.73, "rationale": "..."}
```

---

## Related Research Directions

- **arXiv:2606.08283** (staged H281): Macro-LLM ETF tilt — LLM reads FOMC minutes to adjust factor exposure
- **arXiv:2604.17327** (staged H280): MarketSenseAI — 4-agent architecture with news/sentiment/technical/fundamental analysts
- **arXiv:2510.26228** (staged H279): LLM momentum filter — NLP signal layered on 12-1 momentum
- **H163/H174** (CONFIRMED): FinBERT on EDGAR 8-K — the confirmed anchor for NLP signal generation

See also: [Market Timing Overlays](market-timing-overlays.md) (H296 VIX overlay), [Crypto Trading Strategies](crypto-trading-strategies.md) (H302/H303), [PEAD Strategy](../strategies/pead.md)

## Reproducibility Crisis in LLM Trading Research (Xia et al., May 2026)

**Source:** arXiv:2605.19337 — "Agentic Trading: When LLM Agents Meet Financial Markets"

A systematic review of 77 LLM-based trading agent studies identified severe evaluation deficits:
- **2/19** empirical studies report extractable, time-consistent evaluation protocols
- **1/19** includes realistic transaction costs
- **0/19** achieves R3 reproducibility (full re-runnable implementation with data)

**Implication for H274/H279/H280:** Reported Sharpe ratios from multi-agent LLM papers (e.g., HedgeAgents 2.41, Expert Investment Teams) should be treated with extreme skepticism until independently replicated. The architectural innovations are real, but performance claims are likely inflated by:
1. Lookahead bias in LLM financial knowledge (training data includes the test period)
2. Missing transaction costs
3. Cherry-picked evaluation windows

**Action for dream cycle:** Before implementing any LLM-as-signal hypothesis (H279/H280), require: (1) strict OOS data cutoff, (2) transaction cost model included, (3) comparison to momentum baseline H312-B (OOS Sharpe 1.202) as the hurdle, not SPY.
