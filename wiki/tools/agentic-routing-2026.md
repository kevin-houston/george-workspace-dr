---
title: "Agentic Routing: The Harness-Native Data Flywheel"
added: 2026-07-13
updated: 2026-07-13
category: AI / agent systems / infrastructure
arxiv: "2607.11399"
url: https://arxiv.org/abs/2607.11399
authors: Xinchen Liu, Hang Zhou, Yingjie Zong et al. (Huawei Noah's Ark Lab, 2026)
repo: OpenSquilla
---

# Agentic Routing — The Harness-Native Data Flywheel

**What it is:** A framework for routing between LLMs inside an agent execution harness — selecting the right model at each step rather than committing to one model for the entire task. Introduces the concept of a *harness-native data flywheel* where routing decisions self-improve through logged execution traces. Published July 13, 2026.

## The Core Problem

Modern AI agents are executed by a **harness** that manages observation, context, control, action, state, and verification. Meanwhile, frontier models are becoming structurally specialized:
- Code editing: one model dominates
- Long-context recovery: another
- Tool use: another
- Mathematical reasoning: another
- Low-latency response: another

No single model dominates on all axes. This makes **model selection inside an agent** a core systems problem.

**Existing routing methods fail here:** They optimize single-turn cost-quality trade-offs and miss the execution state, intermediate failures, and feedback loops that make agents different from chat completion.

## Harness-Native Agentic Routing

The paper proposes routing at the **step level** (not query level), conditioned on the full harness state at each decision point:
- What observation just arrived?
- What actions have been taken so far?
- What intermediate failures occurred?
- What is the remaining budget (tokens, calls)?

Two routing modes:
1. **Singleton routing** — select one best-fit model for cost-effective execution
2. **Ensemble routing** — select multiple complementary models for higher accuracy

## The Data Flywheel

Every routing decision naturally produces a **structured record**:
```
{query, harness_state, model_choice, execution_trace, outcome, cost}
```

Labels are supplied by the environment (task success/failure, cost), not by a human annotator. These records form a **flywheel**:
1. Execute tasks → log routing records
2. Train better router on logged records
3. Better router improves cost-quality trade-off
4. Better routing generates more informative traces
5. Repeat

## OpenSquilla Implementation

The paper instantiates the approach in **OpenSquilla** with:
- **Four-layer routing stack**: cold-start ranker → router → harness-native model → ensemble merge
- **LightGBM cold-start ranker**: works from day 1 without logged traces (uses query features)
- **Staged router-model path**: logged arena records improve routing policies progressively

Benchmarks: DRACO and PinchBench (agentic task suites). Results show singleton routing cuts cost vs. fixed model; ensemble routing improves accuracy on hard tasks.

## Relevance to George's Architecture

**Multi-agent trading (H274, H318):** The H318 meta-agent selector that dynamically routes between H026/H041a/H045 sleeves is conceptually analogous to harness-native routing — pick the best "strategy model" given current market state, not a static allocation.

**Dream cycle design:** The dream cycle uses a single model (George/sonnet-4-6) for all steps. Agentic routing suggests the scan phase (broad search) vs. build phase (structured writing) might benefit from different model selections.

**George's NanoClaw harness:** NanoClaw itself is a harness managing George's execution across turns. The flywheel insight applies: logging George's tool call sequences + outcomes creates training data for future routing improvements.

**Practical note:** OpenSquilla is open-source and includes the LightGBM cold-start ranker — could be adapted for step-level model selection in a Python-based multi-agent trading system.

## Key Insight (Quotable)

> "Agentic routing is not merely cost control, but a data engine for agent-native training."

Every agent execution generates signal. Systems that harvest this signal compound over time; systems that discard it restart from zero each run.

## Cross-References

- [AI Agent Frameworks Ecosystem 2026](../ai-industry/agent-frameworks-2026.md) — routing sits above framework layer
- [Hitchhiker's Guide to Agentic AI](hitchhikers-guide-agentic-ai.md) — Layer 4 multi-agent topology; routing is the model-selection sub-problem
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — H318 meta-learner proposal is the trading analog
- [Bilevel Autoresearch](../concepts/bilevel-autoresearch.md) — outer loop that selects search mechanisms is structurally analogous to harness-native routing
