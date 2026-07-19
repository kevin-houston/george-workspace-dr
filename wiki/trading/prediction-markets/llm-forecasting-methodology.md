---
created: 2026-07-18
updated: 2026-07-18
type: research
tags: prediction-markets, LLM, forecasting, methodology, evaluation
---

# LLM Forecasting Methodology for Prediction Markets

This page synthesizes two July 2026 papers that directly address the two most critical methodological
challenges in using LLMs as prediction market forecasters: **evaluation leakage** (Hindcast) and
**deliberation collapse** (InfoDelphi).

---

## The Evaluation Leakage Problem — Hindcast (arXiv:2607.14051, Jul 2026)

**Authors:** Xiao Ye, Jacob Dineen, Evan Zhu, Shijie Lu, Kevin Song, Ben Zhou (Jul 15, 2026)
**Paper:** arXiv:2607.14051

### The Core Problem

Standard backtesting of LLM forecasters has two fundamental leaks that make benchmarks unreliable:

1. **Retrieval leak**: A model with internet access can surface reports *written after* the event it
   is asked to forecast, turning a forecasting task into a lookup. The backtester grades this as
   correct forecasting when it is actually recall.

2. **Training cutoff drift**: Each successive model version is trained on data that extends closer to
   the event date. A question that was genuinely future-dated for last year's model may now fall
   *inside* this year's training window. The evaluation grades training-set recall while claiming to
   test foresight.

Both leaks cause systematic over-estimation of LLM forecasting ability in retrospective benchmarks.

### Hindcast's Solution

Hindcast introduces a **temporal standpoint protocol**: it grades each model as if it stood at a
specific past date `t₀`, before the outcome existed in either channel (internet or training data).

**Mechanics:**
- Resolved Polymarket prediction markets are replayed against a **frozen Reddit snapshot**
- The model is only allowed to read posts written before `t₀`
- Each forecast is scored against *two* baselines:
  1. What actually happened (ground truth)
  2. The Polymarket price at `t₀` (human crowd forecast from the same information set)

**Key advantages:**
- The cutoff is set *per market*, not globally — this means the benchmark stays valid as new markets
  are resolved. The frozen snapshot never changes, so historical evaluations remain reproducible.
- Using the market price at `t₀` as a human baseline allows measuring LLM **edge over the crowd**,
  not just raw accuracy.

### Hindcast Findings

- Once temporal leaks are closed, **retrieval still helps** — but only where Reddit discussed the
  event *before* `t₀`.
- Where the archive contained only speculation (no substantive pre-event discussion), retrieval
  **hurts** accuracy (noise amplification).
- This suggests LLMs should be selective about when to invoke retrieval: events with early, rich
  information histories benefit; events that emerge suddenly or are inherently unpredictable do not.

### Practical Implications for the Pipeline

| Implication | Action |
|---|---|
| Backtesting PM bots requires temporal standpoint | Date-stamp all context used; don't allow post-event retrieval |
| Reddit pre-event signal is useful when dense | Add Reddit density check to H185 Phase 2 PolySwarm design |
| Market price at `t₀` is the correct baseline | Compare to market price, not just final outcome, when evaluating forecast quality |
| Models differ in training cutoff | When deploying different model versions, their effective forecasting windows differ |

---

## Deliberation Collapse — InfoDelphi (arXiv:2607.01661, Jul 2026)

**Authors:** Yuante Li, Yicheng Tao, Kate Zhang, Taozhi Wang, Gefei Gu, Yaxin Zhou (Jul 2, 2026)
**Paper:** arXiv:2607.01661
**Benchmark:** PolyGym — 375 binary forecasting questions from real-world prediction markets

### The Core Problem

Multi-agent deliberation systems assume that agents debating a question will converge toward better
calibrated forecasts than any single agent. But there is a critical design flaw in most implementations:
**when all agents receive identical evidence, deliberation collapses into herding.**

The formal insight: when agents share the same information, their errors become positively correlated.
The averaging mechanism of multi-agent aggregation only reduces variance when agent forecasts are
independent or negatively correlated. Identical-evidence agents produce correlated errors, and
aggregation provides little benefit over a single agent.

### InfoDelphi's Solution: Designed Information Asymmetry

InfoDelphi introduces **principled evidence partitioning**:

- Evidence is split into **shared public** and **disjoint private** subsets
- Each agent receives the shared public evidence plus a unique private partition that no other agent sees
- Agents can only communicate private knowledge *through deliberation* — it cannot be looked up

The paper proves theoretically that this decomposition **reduces inter-agent error correlation**,
which in turn makes aggregation genuinely valuable.

**Three-component framework:**
1. **Relevance-aware evidence routing**: Evidence is classified and routed to agents based on
   topic relevance, not random partitioning
2. **Rationale-based iterative deliberation**: Agents share reasoning (not just probability outputs)
   across deliberation rounds, allowing private knowledge to propagate constructively
3. **Confidence-weighted aggregation**: Final forecasts weight each agent's contribution by its
   expressed confidence, not equally

### PolyGym Results

| System | Brier Score Improvement | Accuracy Gain |
|---|---|---|
| InfoDelphi vs strongest single-agent | +12–18% | +4–8 pp |
| InfoDelphi vs standard multi-agent (identical evidence) | Significant | Significant |
| Standard multi-agent vs single-agent | Minimal | Minimal |

**Key ablation finding:** Removing information asymmetry (reverting to identical evidence) eliminates
*most* of the deliberation gain. The improvement from standard single → multi-agent is minimal; the
improvement from identical-evidence multi-agent → asymmetric-evidence multi-agent is the dominant
effect.

### Relationship to H185 PolySwarm Design

The H185 Phase 2 PolySwarm design (50-agent swarm) is directly affected by these findings:

- The current PolySwarm design likely provides identical or overlapping context to all agents
- If agents all see the same retrieval results, deliberation will collapse into herding
- **Design upgrade**: implement evidence partitioning before H185 Phase 2 implementation
  - Partition retrieval sources: e.g., Agent A gets news feeds, Agent B gets social media,
    Agent C gets historical base rates, Agent D gets quantitative indicators
  - Use rationale sharing rather than probability outputs across debate rounds
  - Weight final aggregation by agent-expressed confidence

### Relationship to Trading Agent Architecture (H274, H318)

The information asymmetry principle extends beyond prediction markets:

- In multi-agent PEAD (H274), agents that each specialize in one data stream (FinBERT score,
  EPS surprise, price action, sector context) and then deliberate will outperform agents
  that each receive all signals
- In the meta-agent ETF selector (H318), regime-specialization of sub-agents (each sub-agent
  sees only one macro regime's historical data) before aggregation could reduce error correlation

---

## Combined Takeaways

Both papers point to the same underlying challenge: **information structure matters as much as
model capability** in LLM forecasting systems.

| Challenge | Paper | Solution |
|---|---|---|
| Temporal leakage in evaluation | Hindcast | Frozen snapshot + temporal standpoint |
| Deliberation collapse from shared info | InfoDelphi | Designed evidence asymmetry |
| Retrieval noise from speculative pre-event data | Hindcast | Selective retrieval by event information density |
| Identical-evidence herding | InfoDelphi | Private partition per agent |

For the George production pipeline, the highest-priority action from these papers is the
**H185 Phase 2 PolySwarm evidence partitioning design** — implementing the InfoDelphi architecture
before deploying a 50-agent prediction market swarm.

---

## Cross-references

- [AI Model Benchmarks on Prediction Markets](ai-model-benchmarks.md) — live capital evaluations
- [Prediction Market Algorithmic Strategies](algorithmic-strategies.md) — strategy taxonomy
- [Superforecasting Methods](superforecasting-methods.md) — calibration and Brier score context
- [Multi-Agent LLM Trading](../../trading/algorithms/multi-agent-llm-trading.md) — H274/H318 designs
- [Prediction Market Automated Pipeline](automated-pipeline.md) — H185 implementation context
