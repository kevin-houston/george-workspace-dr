---
created: 2026-07-03
updated: 2026-08-19
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

---

## MacroLens — Multi-Task Multi-Modal Financial Benchmark (2026)

**Source**: arXiv:2606.24950 (Trirat, Kwak, Heo, Lee & Hwang, Jun 2026)

### What It Is
MacroLens covers 4,416 US small/micro-cap equities over 2021-2026 with four jointly evaluated signal types:
1. **Price history** — OHLCV time series
2. **XBRL fundamentals** — 46.8M accounting facts with point-in-time dating
3. **Macroeconomic regimes** — 53 FRED series, 1,130 macro events across 49 types
4. **Filing text** — 295,860 SEC filings + 215,882 news articles (gated by publication date)

Seven tasks: contextual return forecasting, public/private valuation, statement generation, scenario-conditioned returns, real-estate valuation.

### Key Findings from 19-Method Evaluation
- **Gradient-boosted baseline + price features outperforms zero-shot LLMs** on return forecasting
- **LLMs excel at scenario-conditioned return prediction** — qualitative reasoning over macro events (Fed rate hikes, earnings surprises)
- **Text + fundamentals jointly > either alone** — confirmed by five-step ablation on frontier LLMs
- **Macro regime series (FRED) add incremental lift** beyond price + fundamentals on medium-horizon tasks
- **Look-ahead discipline** is the critical challenge: text must be gated by SEC publication date, fundamentals by reporting date + lag

### Implications for Production Pipeline
- **H026** (signal type 1 only — pure price momentum) is theoretically improvable with macro regime overlay
- **H174** (types 1+2+4 — price gap + EPS surprise + FinBERT 8-K) already implements three of four signal types. The gap: no explicit macro regime conditioning (type 3)
- H444's realized-vol gate is an implicit macro regime proxy (type 3 approximation)
- MacroLens focuses on small/micro-cap; H198/H026 are large-cap — results may not transfer directly

### Design Note: H174 Macro Regime Gate
H174 MacroLens-style four-signal composite:
- Signal 1 (price): gap-up filter (production)
- Signal 2 (fundamental): EPS surprise ≥ 0.02 (production)
- Signal 3 (macro): VIX<25 + SPY>200MA gate (H301/H165a-style)
- Signal 4 (text): FinBERT 8-K score ≥ 0.18 (production)

Hypothesis: adding an explicit macro regime gate (signal 3) would improve H174 OOS win rate from 81.8% by filtering earnings-beat entries in bear markets where PEAD is empirically weakened.

---

## Backtrader-Bench — LLM Coding Agents on Algorithmic Trading via Self-Generated MCQs (arXiv:2608.11232, Aug 2026)

**Source**: Zhao et al., "Backtrader-Bench: Benchmarking LLM Agents on Algorithmic Trading with Self-Generated MCQs," submitted 2026-08-14, accepted FinLLM Workshop @ IJCAI 2026. Detail gathered via WebSearch at abstract/README level; the paper's full text has not been independently fetched in this pass, so treat specifics below as reported, not independently verified.

### What it does differently

Existing LLM-trading benchmarks (BacktestBench, CLQT, PortBench — all already cited above) evaluate whether an LLM's *trading decisions* are good. Backtrader-Bench instead evaluates whether an LLM *coding agent* can correctly answer quantitative questions about a backtest's own numerical output — e.g. "what was the Sharpe ratio of variant X after changing parameter Y" — where getting the right answer strictly requires actually running the code, not pattern-matching from training data. This sidesteps the data-contamination risk that plagues static benchmarks: a deterministic multiple-choice pipeline generates questions from real backtest configurations (5 strategies, 33 templates, 3 difficulty tiers), and a **generator-solver filtering pipeline** discards any question a no-tool solver can already answer without executing code — so the retained question set specifically targets code-execution-dependent reasoning, not memorized facts.

### Reported results

- 11 models evaluated without tools (10 runs each) plus 4 tool-augmented configurations on a 30-question curated set.
- **Tool-augmented agents reach 90.0% accuracy** (best: GPT-5.5 and Claude Opus 4.7), a wide margin over the **best no-tools baseline at 73.0%** — i.e. actually executing the backtest code, rather than reasoning about it in the abstract, is worth roughly 17 percentage points.
- Full question sets (160-question and a balanced 30-question set) and code released on GitHub (`rzhao999/Backtrader-Bench`).

### Relevance to George's pipeline

This is a direct evidentiary counterpart to the [cloudQuant/backtrader tooling note](../trading/tools/cloudquant-backtrader-notes.md) logged the previous night (2026-08-19): that note flagged an MCP server exposing typed tools for building/running backtrader strategies from an agent session but took no position on whether an agent using such tools is actually more reliable than one reasoning without them. Backtrader-Bench supplies exactly that evidence for the `backtrader` framework specifically (17pp accuracy gap, tools vs. no tools) — reinforcing the wiki's existing "LLM-as-filter-not-allocator" pattern (PortBench above) with an adjacent, code-execution-specific finding: even for questions with a single verifiable numeric answer, an LLM without the ability to execute code is a meaningfully worse source of truth than one that can. For any future work wiring an LLM agent to read `run_hNNN.py` backtest results (e.g. summarizing a hypothesis run, or a natural-language interface over `hypothesis-log.md`), this argues for tool-executed verification over free-text LLM summary whenever a specific number is being reported, not just narrative interpretation.

**Not staged as a new hypothesis** — this is a benchmark/tooling-reliability finding, not a trading signal. Logged as a design-reference note alongside the existing BacktestBench/CLQT/PortBench entries above.

## See Also

- [AI Model Landscape 2026](model-landscape-2026.md) — frontier model snapshot
- [AI Agent Frameworks Ecosystem](agent-frameworks-2026.md) — LangGraph, CrewAI, PydanticAI
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — PortBench + reproducibility crisis
- [cloudQuant/backtrader Notes](../trading/tools/cloudquant-backtrader-notes.md) — MCP-native backtest tooling; Backtrader-Bench is the reliability evidence for agent-executed backtests
- [Shared Strategy Evaluation Checklist](../trading/shared-eval-checklist.md) — 7-point pre-production gate
- [Backtesting Design Principles](../trading/backtesting/design-principles.md) — IS/OOS framework
- [Regime Detection](../trading/algorithms/regime-detection.md) — HMM, VJM, Statistical Jump Model
- [Regime Detection Signals — Practical Data Guide](../trading/backtesting/regime-detection-signals.md) — SPY 200MA, VIX, yield curve
- [FinBench — Calibration Benchmarking](finbench-calibration-2026.md) — probabilistic uncertainty for financial LLMs
