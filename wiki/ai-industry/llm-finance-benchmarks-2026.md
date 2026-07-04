---
created: 2026-07-03
updated: 2026-07-03
type: concept
category: AI Industry
---

# LLM Evaluation & Benchmarking for Finance 2026

Synthesizes the emerging landscape of LLM evaluation frameworks specifically designed for finance and trading tasks. Distinct from general AI benchmarks (GPQA, SWE-bench) — these evaluate whether LLMs can act as credible quantitative analysts, portfolio managers, and trading agents.

Key insight: most existing LLM finance benchmarks rank by raw returns over fixed windows — a metric dominated by market path, not agent skill. The 2026 generation of benchmarks is correcting this with diagnostic, cost-aware, and reproducibility-focused designs.

---

## Why General Benchmarks Don't Transfer to Finance

Standard benchmarks (MMLU, GPQA Diamond, SWE-bench) measure:
- Knowledge recall accuracy
- Code generation quality
- Logical reasoning steps

Finance tasks require an additional layer:
- **Temporal consistency**: no look-ahead leakage across train/test splits
- **Transaction cost realism**: alpha must survive execution friction
- **Strategy consistency**: does the agent apply the same logic repeatedly, or does it cherry-pick?
- **Regime coverage**: does performance hold across 2022 (bear), 2020 (crash), 2009 (recovery)?

Without these properties, a benchmark's "top performer" can be the worst real-money performer.

---

## Key Benchmarks (2025–2026)

### CLQT — Closed-Loop, Cost-Aware, Strategy-Consistent (June 2026)

**Source:** arXiv:2606.29771 — Bo Qu, Mingguang Chen; submitted June 2026

**Design philosophy:** Benchmark as *diagnosis*, not *ranking*. Reframes evaluation as "where and why does this agent's process succeed or fail?" rather than "which agent made the most money?"

**Five-stage evaluation cycle:**
1. **Gather** — agent collects market data and news under strict temporal controls
2. **Synthesize** — converts raw inputs to a market view
3. **Allocate** — produces portfolio weights
4. **Execute** — simulates orders with realistic transaction costs
5. **Monitor** — reviews outcomes and updates priors

**Three failure modes diagnosed:**
- *Reasoning gap*: agent has data but draws wrong conclusions
- *Consistency gap*: applies different logic to similar situations
- *Cost gap*: alpha exists pre-cost but not post-cost

**Key finding:** Most LLM portfolio agents fail primarily on consistency — they "reason" their way to different conclusions from identical market conditions across repeated trials. This is distinct from the knowledge or reasoning gaps that general benchmarks measure.

**Implication for George:** Our H174 pipeline is rule-based (FinBERT score threshold + EPS surprise gate), not LLM-delegated — it has built-in consistency. The benchmark validates using deterministic signal thresholds rather than LLM judgment for entry/exit decisions.

---

### BacktestBench — LLM Quantitative Backtesting (May 2026)

**Source:** arXiv:2605.17937 — Wang, Yang, Wu et al.; May 2026

**First large-scale benchmark for automated quantitative backtesting by LLMs.** Built from 6+ million real market records; 18,246 annotated QA pairs across four task categories:

| Task Category | What's Tested |
|---|---|
| Metrics Calculation | Sharpe, Calmar, drawdown, turnover given returns |
| Ticker Selection | Identify which stocks satisfy momentum/value/quality screens |
| Strategy Selection | Choose the right strategy given a market regime description |
| Parameter Confirmation | Validate lookback windows, threshold values, hold periods |

**Key results:**
- All tested frontier LLMs (GPT-5, Gemini 3.1, Claude Opus 4.7) score above 70% on metrics calculation
- Ticker selection and strategy selection: most models score 45–65% — barely above random for parameter confirmation
- **No model reliably combines all four tasks end-to-end** in a way that produces a coherent strategy

**Design note:** The benchmark explicitly separates "does the LLM understand quantitative finance?" from "can the LLM execute a backtest?" These are different skills. George's architecture uses LLMs for the first (reasoning about strategy design) and Python scripts for the second (actual execution) — which aligns with how the benchmark's "best" LLM use case looks.

**Relevance:** Validates our human-in-loop approach: LLMs propose hypotheses; vectorbt/pandas execute them; OOS statistics confirm/reject. Pure LLM backtesting agents fail systematically.

---

### PortBench — Correlation-Aware Portfolio Benchmark (May 2026)

**Source:** arXiv:2605.27887 — Zhao, Chen, Su; submitted May 2026
*(See also: multi-agent-llm-trading.md — this paper is cross-referenced there)*

**Summary:** First benchmark with explicit asset correlation modeling. Spans 6 asset classes over a decade. Tests 10 frontier LLMs.

**Key result:** 90% of model-profile combinations fail to beat equal-weight allocation.

**Novel metrics introduced:**
- *Dual-layer correlation score*: hedging effectiveness + concentration avoidance
- *CEPS (Cascaded Error Propagation Score)*: tracks reasoning errors across retrieval → analysis → decision pipeline stages

**Implication:** Static blends (our 40/30/30 H026/H041a/H045) outperform what 90% of LLM portfolio managers achieve. LLMs as autonomous portfolio managers are unproven; as signal components they add value at clearly defined stages.

---

### Agentic Trading Survey: 77 Studies (May 2026)

**Source:** arXiv:2605.19337 — surveyed through 2026-03-09
*(Cross-referenced in multi-agent-llm-trading.md)*

**Protocol-coded review of 77 LLM trading studies.** 19 meet minimum bar (action output + closed-loop evaluation).

| Criterion | Pass rate (n=19) |
|---|---|
| Time-consistent data splits | 2/19 (11%) |
| Explicit transaction cost model | 1/19 (5%) |
| Survivorship-bias handling | 1/19 (5%) |
| R3 reproducibility | 0/19 (0%) |

**Context:** Our shared-eval-checklist.md requires time-consistent splits and explicit cost modeling — placing our work in the top ~5% of published research by this standard.

---

## Regime-Adaptive Evaluation: The Missing Piece

Most benchmarks evaluate over a single fixed window. The 2026 consensus is that any strategy must be tested across at least three distinct regimes:

| Regime | Dates | Character |
|---|---|---|
| Bull/low-vol | 2019, 2023-2024 | Momentum dominates |
| Crisis/crash | 2020-03, 2022 | Diversification and carry matter |
| Recovery | 2009, 2020-Q4 | Mean-reversion + value outperform |

**ReCAP Framework (arXiv:2606.00143, June 2026)** — Regime-aware Continual Adaptive Portfolio management:
- Integrates continual learning into portfolio management to handle non-stationarity
- Regime detection layer → task-specific learning modules → knowledge transfer across regimes
- Reports OOS improvements vs rolling-window retraining: ~+15% Sharpe, −30% MaxDD
- Directly relevant to H249 (regime-conditional weights) and H318 (meta-learner design)

**Key design principle from ReCAP:** Regime transitions should trigger *knowledge transfer*, not a complete model wipe. A retraining approach that discards crisis-era learning before the next crisis is structurally brittle.

---

## HMM + RL Regime Allocation (May 2026)

**Source:** arXiv:2605.27848 — Verma, Putri, Lesupi; May 2026

Three-state Gaussian HMM on daily SPY/TLT/GLD data (2004–2025), combined with RL policy for dynamic allocation.

**Regime identification:**
- State 1 (Low volatility): SPY-dominant, Sharpe ~1.4 in-state
- State 2 (Transitional): Mixed, frequently preceding both State 1 and State 3
- State 3 (High volatility): TLT and GLD outperform; SPY underperforms

**RL policy result:** Dynamic RL allocation achieves Sharpe 1.68 vs static 60/20/20 Sharpe 0.92 on the same window.

**Comparison with H251 (our HMM result):**
- H251 tested SPY/TLT/GLD with 3-state HMM; OOS Sharpe 0.941
- The gap (0.941 vs 1.68) is entirely attributable to the RL policy — H251 used static regime-conditional weights; this paper's RL policy dynamically adjusts within states
- **Proposed as H362** — adding RL allocation on top of the H251 regime detector

---

## Practical Guidance for George's Pipeline

### When to trust LLM judgment vs. deterministic rules

| Task | Use LLM | Use Deterministic Rule |
|---|---|---|
| Hypothesis generation | Yes | |
| Paper synthesis | Yes | |
| 8-K text scoring (FinBERT) | Use trained model | |
| Entry threshold decision | | Yes (score >= 0.18) |
| Position sizing | | Yes (Kelly formula) |
| Exit timing | | Yes (20 trading days) |
| Portfolio weight allocation | | Yes (static 40/30/30 or bounded) |

LLMs are poor at consistent application of numerical thresholds — BacktestBench and CLQT both confirm this. Keep the signal generation LLM-assisted; keep the rule application deterministic.

### Backtesting hygiene checklist (updated from benchmarks)

From CLQT + BacktestBench synthesis, three checks most commonly missed in published work:

1. **Strategy consistency test**: Run the same strategy code 5× with identical inputs — verify identical outputs. (Obvious for deterministic code; critical to confirm if LLM is in the loop.)
2. **Transaction cost checkpoint**: Does the strategy maintain positive Sharpe after 0.1% per-trade friction? (Only 1/19 published agentic trading papers include this.)
3. **Temporal integrity scan**: Grep your data loading for any `.shift(0)` where `.shift(1)` should appear; any `pd.merge` without explicit date guards.

---

## See Also

- [AI Model Landscape 2026](model-landscape-2026.md) — frontier model snapshot
- [AI Agent Frameworks Ecosystem](agent-frameworks-2026.md) — LangGraph, CrewAI, PydanticAI
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — PortBench + reproducibility crisis
- [Shared Strategy Evaluation Checklist](../trading/shared-eval-checklist.md) — 7-point pre-production gate
- [Backtesting Design Principles](../trading/backtesting/design-principles.md) — IS/OOS framework
- [Regime Detection](../trading/algorithms/regime-detection.md) — HMM, VJM, Statistical Jump Model
- [Regime Detection Signals — Practical Data Guide](../trading/backtesting/regime-detection-signals.md) — SPY 200MA, VIX, yield curve
