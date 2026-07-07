---
created: 2026-07-06
updated: 2026-07-06
type: concept
category: AI Industry
---

# LLM Trading Agent Benchmarks 2026

Synthesis of the 2026 generation of evaluation frameworks for LLM agents in trading contexts. Companion to [LLM Evaluation & Benchmarking for Finance 2026](llm-finance-benchmarks-2026.md) — this page focuses specifically on *trading agent* benchmarks (stock selection, portfolio construction) rather than general finance knowledge benchmarks.

**Related pages**: [LLM Evaluation & Benchmarking for Finance 2026](llm-finance-benchmarks-2026.md) | [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) | [AI Agent Frameworks Ecosystem 2026](agent-frameworks-2026.md) | [Event-Driven Strategies](../trading/algorithms/event-driven.md)

---

## The Core Evaluation Problem

Placing an LLM agent in a historical market and measuring portfolio returns produces misleading results for two reasons identified consistently across 2026 papers:

1. **Knowledge contamination**: frontier LLMs trained on data through 2025 have memorized tickers, price history, earnings dates, and market narratives for the eval period. The agent may be recalling rather than reasoning.
2. **Beta masquerading as alpha**: positive returns in a bull market do not require stock-selection skill — market exposure (beta), style tilts, or favorable regimes can explain most or all gains. Attributing these to LLM intelligence is a systematic error.

---

## KTD-Fin: Memory-Controlled LLM Trading Benchmark

**Source**: Zhu, Zhao, Sun, Luan (2026). "From Knowing to Doing: A Memory-Controlled Benchmark for LLM Trading Agents on Stock Markets." arXiv:2605.28359. Published 2026-05-27.

### Design

- **Universe**: CSI 300 (Chinese large-cap), evaluated 2024-2026 window
- **Data-side masking**: anonymizes tickers, dates, prices, and market narratives consistently across prompts and tools — separating historical market memory from genuine investment reasoning
- **Attribution framework**: Barra-style decomposition of portfolio returns into (a) market beta, (b) style factor exposure, (c) stock-selection alpha

### Key Findings (10 frontier LLM agents)

1. **Masking substantially changes agent rationales** — agents shift from narrative recall ("CATL is the leading battery manufacturer...") toward anonymized factor-based reasoning when identifiers are hidden
2. **Returns under leakage-controlled evaluation largely decompose into beta + style**, with *limited evidence of persistent stock-selection alpha* across any of the 10 agents
3. The benchmark is reproducible — released as a template for leakage-controlled evaluation

### Relevance to Production

- The KTD-Fin finding is a direct caution for H280 (MarketSenseAI) and H318 (meta-agent learner): LLM agents that appear to generate alpha may be recalling training data rather than applying transferable reasoning
- Mitigation: use post-cutoff data only in OOS evaluation; apply Barra attribution to any LLM-agent backtest result

---

## Strat-LLM: Stratified Strategy Alignment

**Source**: Huang & Yu (2026). "Strat-LLM: Stratified Strategy Alignment for LLM-based Stock Trading with Real-time Multi-Source Signals." arXiv:2605.06024. Published 2026-05-07.

### Design

- **Live-forward setting**: evaluated throughout 2025, integrating real-time prices, news, and annual reports
- **Strategy alignment modes**: Free Mode (internal LLM reasoning), Guided Mode (suggested strategy direction), Strict Mode (rigid rule anchor)
- **Markets**: A-share (China) and U.S. equities

### Key Findings

1. **Model scale is non-monotonic**: mid-scale models (35B) show optimal fidelity under strict constraints; ultra-large models (122B) suffer an *alignment tax* under rigid rules but gain a *performance premium* in Guided Mode
2. **Regime dependency**: Free and Guided modes capture momentum in uptrending markets; Strict Mode mitigates drawdowns in downtrends — no single mode dominates all regimes
3. **High win-rate trap**: standard LLMs often optimize for small gains at the expense of total returns — only deep reasoning or strict external guardrails mitigate this
4. **Reasoning-heavy models** (Claude Opus/GPT-5.5) achieve peak utility in Free Mode via internal logic; standard models require Strict Mode as a risk anchor

### Relevance to Production

- The regime-mode alignment finding maps directly onto H249's regime framework: in bear regimes (VIX high, SPY < 200MA), any LLM trading layer should run in Strict Mode; in bull regimes, Guided or Free Mode is more effective
- The high-win-rate trap is a known issue in H174 paper trading — FinBERT score threshold optimization may be inadvertently optimizing for trade frequency over mean return; watch for this in PEAD live graduation

---

## EarningsInOne: Fast/Slow Earnings Signal Separation

**Source**: Yu, Liu, Zhang, He (2026). "Fast Numbers, Slow Language: Bridging Quantitative and Qualitative Earnings Signals." arXiv:2606.29734. Published 2026-06-29.

### Design

- **Corpus**: EarningsInOne — first corpus aligning earnings news, earnings call transcripts (ECTs), and intraday + next-day prices across S&P 1500 (2022-2025)
- **Signal types**: quantitative surprise (EPS/revenue vs analyst estimate) vs qualitative ECT sentiment
- **Evaluation**: unified trading and evaluation tools applied to both signal types simultaneously

### Key Findings — the Speed Separation

| Signal | Peak timing | Persistence | Tradeable? |
|---|---|---|---|
| Quantitative EPS/revenue surprise | Within minutes of announcement | Eliminated by next market open | Only at open (OPG) |
| Qualitative ECT sentiment | Next trading day | Persists 1-2 days post-call | Yes — slow and hidden |

- **Prior ECT research was misled**: studies optimized MSE (mean squared error) on directional returns — sign-agnostic — and therefore missed that ECT sentiment is directionally predictive but noisy in magnitude
- Applying correct directional evaluation reveals ECT sentiment is *real and tradeable* on the next trading day after the earnings call

### Hypothesis Implication

**H376** (staged 2026-07-06): Add a slow ECT layer to H174 — hold positions when ECT confirms, exit early when ECT contradicts, rather than the current flat 20-day hold for all positions.

---

## Unified Assessment: Where LLMs Add Value in Trading

Based on 2026 benchmark evidence:

| Task | LLM Value | Caveat |
|---|---|---|
| EPS/revenue surprise scoring | Low — algorithmic models do this in <1ms | N/A |
| Qualitative earnings call tone | Medium-High — directional signal persists to next day (EarningsInOne) | Requires ECT availability; FMP H247 caveat |
| Cross-stock semantic lead-lag | Medium — H319 semantic network approach | Needs OpenAI API + EDGAR |
| Portfolio construction | Low — beta exposure explains most gains (KTD-Fin) | Post-cutoff data only |
| Regime-conditional strategy selection | Medium — regime-mode alignment improves drawdown (Strat-LLM) | Model-scale dependent |
| Multi-agent debate for PEAD | Proposed (H274) — 3-agent confirmation; untested | |

---

## Reproducibility Warning

All three 2026 papers independently identify reproducibility as the core crisis:
- KTD-Fin: anonymization reveals LLM agents recall rather than reason in non-masked settings
- Strat-LLM: live-forward evaluation (2025) is rare — most papers use historical simulation with LLM knowledge contamination
- EarningsInOne: prior ECT research used MSE instead of directional accuracy, systematically understating qualitative signal quality

For George's production pipeline: any LLM-based signal must be evaluated on events *after* the model's training cutoff, with Barra attribution applied to results.
