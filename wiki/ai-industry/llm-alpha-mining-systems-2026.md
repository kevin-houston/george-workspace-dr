---
title: LLM Alpha Mining Systems 2026
added: 2026-07-07
updated: 2026-07-07
category: AI Industry
related: agent-frameworks-2026.md, llm-trading-agent-benchmarks-2026.md
trading_cross_refs: trading/algorithms/auto-alpha-discovery.md, trading/algorithms/factor-models.md, trading/algorithms/momentum-strategies.md
hypotheses: H380, H381, H382
---

# LLM Alpha Mining Systems 2026

Synthesis of the 2026 wave of LLM-powered automated alpha factor discovery systems. These tools operationalize the hypothesis that LLMs can replace or augment human financial intuition in the factor engineering loop, while maintaining the auditability and statistical rigor that quant research demands.

See the detailed method-level page at [AI-Driven Alpha Factor Discovery](../trading/algorithms/auto-alpha-discovery.md) for implementation code and backtesting results. This page covers the ecosystem landscape, new 2026 entrants, and cross-market factor transfer research.

---

## The Core Problem: Alpha Decay Acceleration

Alpha decay has compressed. The [Signal Half-Life & Alpha Decay](../trading/backtesting/signal-halflife.md) page documents that AI-driven compression has shortened momentum signal half-life from ~84 months to ~12 months (arXiv:2605.23905). This creates a structural pressure on human-speed hypothesis generation:

- **Old paradigm:** research team discovers factor → backtest → publish → live → 3-5 years before crowding kills it
- **New paradigm:** LLM mining systems generate dozens of factors per session → algorithmic selection → live → months before crowding

The systems below represent the quant community's response to this pressure: automated, high-throughput hypothesis generation with built-in statistical guardrails.

---

## 2026 New Entrants

### AlphaLogics — Market Logic as the Constraint Layer

**Source:** arXiv:2603.20247 | Weng, Zhang, Wang & Xia | March 2026  
**Hypothesis:** H381

AlphaLogics introduces the **market logic** abstraction: an explicit, human-readable statement of *why* a factor should work, extracted from prior factor libraries and used to guide new factor generation.

**Three-agent architecture:**

| Agent | Role |
|-------|------|
| Market Logic Mining Agent | Reverse-engineers market logics from existing confirmed factors (e.g., "momentum persists because of investor underreaction to earnings") |
| Factor Generation Agent | Uses market logics to propose new factor code + backtests against logic hypothesis |
| Logic Refinement Agent | Updates market logic library based on factor backtest outcomes; prunes logics whose generated factors consistently fail |

**Validated results:** S&P 500 — significant improvement in predictive metrics and risk-adjusted returns vs. baselines (QuantaAlpha, TreEvo, EoH). The market logic library remains *empirically useful* for guiding further discovery even after the initial session.

**Key distinction from other systems:** AlphaLogics is the only system that explicitly models *why* a factor should work, not just *that* it works. This addresses the core auditability concern in quant research — a factor without a causal mechanism is a mined artifact.

**Our alignment:** The market logic concept maps directly onto our hypothesis format (each H### has a rationale section). AlphaLogics could be initialized with our hypothesis-log.md as the knowledge base, starting from 380+ prior experiments.

---

### FactorEngine — Program-Level Factor Code with Dual-Mode LLM

**Source:** arXiv:2603.16365 | Lin et al. (10 authors, Tsinghua lineage) | March 2026  
**Hypothesis:** H382

FactorEngine casts factors as **Turing-complete code** and separates three orthogonal concerns that prior systems conflate:

1. **Logic revision vs. parameter optimization** — LLM handles the structural change (replace RSI with a momentum derivative); Bayesian HPO handles the numerical tuning (window length, threshold)
2. **LLM-guided directional search vs. Bayesian HPO** — LLM proposes *which direction* to mutate; BO finds the *best parameters* within that direction
3. **LLM API calls vs. local computation** — LLM proposes code fragments; all evaluation runs locally, minimizing API costs

**Knowledge-Infused Bootstrapping module:** takes unstructured financial research (academic papers, existing factor formulas) → multi-agent pipeline (extraction agent → verification agent → code generation agent) → executable factor programs. This is the key innovation: FactorEngine can ingest our wiki as initialization context.

**Experience Knowledge Base:** unlike QuantaAlpha's trajectory evolution (which can forget failed paths), FactorEngine maintains a persistent database of:
- Which factor structures worked in which regimes
- Which directions were explored and failed (avoids re-exploration)
- Bayesian surrogate model for parameter spaces

**Our fit:** FactorEngine's experience knowledge base is directly initialized from our hypothesis-log.md — we have 380+ factor experiments with failure reasons, which is exactly what the "trajectory-aware refinement" module needs.

---

### Cross-Market Alpha Transfer — Alpha191 to S&P 500

**Source:** arXiv:2601.06499 | Du, Walter & Ulrich (KIT) | January 2026  
**Hypothesis:** H380

The Chinese A-share market's retail-dominated, high-frequency structure has produced the **Alpha191 library** — 191 short-term price-volume signals originally designed for intraday momentum, reversal, and microstructure patterns in Chinese stocks.

Du et al. (2026) systematically test whether these signals transfer to the US S&P 500 large-cap universe (2002–2022):

**Methodology:** Double-Selection LASSO — first selects for the 191 Alpha191 factors with unconditional predictive power, then controls for 151 established US fundamental factors (the "US factor zoo"). This two-stage selection identifies factors with *incremental* explanatory power beyond what US researchers already know.

**Key findings:**
- 168 of 191 Alpha191 factors are computable on S&P 500 (23 excluded: unstable time series)
- **17 factors survive double-selection at 5% significance** after controlling for the full US factor zoo
- Surviving factors span: Volume & Flow, Mean Reversion, Trend & Momentum, Volatility & Risk, Liquidity & VWAP, Price Action
- The surviving signals are primarily **microstructure-based** — not the momentum/reversal signals that transferred most obviously, but the volume-flow and liquidity signals

**Why this matters for H198 and H380:** Our current H198 6-1m momentum uses only price returns. The 17 surviving Alpha191 signals (mostly OHLCV-based) are orthogonal to our existing signal and represent incremental alpha on the same stock universe.

---

## State of the Field: What Works and What Doesn't

Based on 2025-2026 papers across auto-alpha-discovery.md and new 2026 entrants:

### What consistently works

| Pattern | Evidence |
|---------|----------|
| Symbolic / code-based factors | TreEvo IC 0.0317 SPX; AlphaLogics improvement on SPX; FactorEngine OOS improvement |
| Experience memory / anti-redundancy | FactorMiner's Ralph Loop; FactorEngine experience KB; AlphaLogics logic refinement |
| Volume & microstructure signals | Alpha191 cross-transfer: 17/168 survive, mostly microstructure |
| Regime-aware factor selection | Hubble tracking factor decay by family; ReCAP continual learning |

### What consistently fails

| Pattern | Evidence |
|---------|----------|
| Neural factors without GPU infra | Attention Factors: OOS 2.3 net but requires A6000 cluster |
| Single-pass LLM generation (no iteration) | All methods need feedback loop; one-shot factor proposals decay quickly |
| Cross-market transfer of macro factors | Fundamental/value signals (P/E, ROE) don't transfer; microstructure does |
| LLM portfolio allocation (not factor mining) | PortBench: 90% of models fail vs equal-weight on correlation-aware tasks |

### The LLM roles that add value

The 2026 consensus is that LLMs are valuable as **proposal generators and logic validators**, not as direct portfolio allocators:

```
LLM VALUE:                     LLM FAILS:
Factor hypothesis → ✓          Portfolio weights → ✗
Market logic → ✓               Covariance estimation → ✗  
Code generation → ✓            Risk-adjusted allocation → ✗
Failure explanation → ✓        Stress-period prediction → ✗
```

See [LLM Trading Agent Benchmarks 2026](llm-trading-agent-benchmarks-2026.md) for full evidence on the allocation failure pattern (PortBench: 90% below equal-weight).

---

## Regime-Adaptive Learning: The Next Frontier

Two 2026 papers address the non-stationarity problem that causes all alpha mining systems to eventually fail:

### ReCAP — Regime-Adaptive Continual Portfolio Management

**Source:** arXiv:2606.00143 | May 2026  
**Hypothesis:** H384

ReCAP integrates continual learning into portfolio management via:
1. **Adaptive regime detection** — change-point detection on return series, variable-length regimes
2. **Policy library** — a DRL policy is trained per detected regime, stored for reuse
3. **Rapid adaptation** — when a new regime is detected, retrieves most similar historical regime policy and fine-tunes, avoiding catastrophic forgetting

The continual learning framing addresses the deepest problem in quant research: IS/OOS splits assume the OOS period is stationary. ReCAP treats every regime shift as a new task and adapts without forgetting prior regimes.

**Our application:** H384 applies ReCAP to H026 ETF rotation, building a policy library indexed by (SPY 200MA × VIX × yield curve) regime vectors — directly extending our H249 regime-conditional framework with online learning.

### HMM + RL — Regime-Based ETF Allocation

**Source:** arXiv:2605.27848 | May 2026  
**Hypothesis:** H383

3-state Gaussian HMM (Low-Vol, Transitional, High-Vol) + RL policy on SPY/TLT/GLD. Both HMM-only and RL+HMM outperform passive SPY; RL achieves highest Sharpe and lowest drawdown. The discrete regime-dependent actions maintain interpretability — a key advantage over black-box DRL.

See [Regime Detection](../trading/algorithms/regime-detection.md) for the full HMM implementation framework.

---

## Practical Prioritization

For immediate execution (ordered by cost-effectiveness):

| Priority | System | Cost | Expected Impact | Status |
|----------|--------|------|----------------|--------|
| 1 | H380 (Alpha191 → US) | Low (OHLCV data only, no API) | 17 new signal candidates for H198 augmentation | Proposed |
| 2 | H381 (AlphaLogics) | Medium ($15-40 OpenAI) | New factor expressions validated on SPX | Proposed |
| 3 | H382 (FactorEngine) | Medium ($20-50 OpenAI) | Knowledge-bootstrapped from our hypothesis-log | Proposed |
| 4 | H383 (HMM+RL) | Low (hmmlearn + stable-baselines3) | SPY/TLT/GLD capital-preservation sleeve | Proposed |
| 5 | H384 (ReCAP) | High (PyTorch + ruptures + SB3) | H026 regime-adaptive production upgrade | Proposed |

---

## Cross-References

**Trading algorithms:**
- [AI-Driven Alpha Factor Discovery](../trading/algorithms/auto-alpha-discovery.md) — implementation details for H347/H349/H288/H352/H365
- [Factor Models & Cross-Sectional Alpha](../trading/algorithms/factor-models.md) — academic foundations (FF5, alpha101, WorldQuant)
- [Momentum Strategies](../trading/algorithms/momentum-strategies.md) — H198 6-1m baseline that H380 augments
- [Regime Detection](../trading/algorithms/regime-detection.md) — HMM/SJM framework for H383/H384
- [Smart Money Concepts (ICT)](../trading/algorithms/smart-money-concepts-ict.md) — Order Block mechanism as complement to LLM-discovered signals

**AI Industry:**
- [LLM Trading Agent Benchmarks 2026](llm-trading-agent-benchmarks-2026.md) — PortBench/KTD-Fin/Strat-LLM evidence on LLM allocation failures
- [LLM Evaluation & Benchmarking for Finance 2026](llm-finance-benchmarks-2026.md) — BacktestBench/ReCAP benchmark context
- [AI Agent Frameworks Ecosystem 2026](agent-frameworks-2026.md) — LangGraph/CrewAI/AutoGen used in alpha mining multi-agent pipelines

**Backtesting:**
- [Signal Half-Life & Alpha Decay](../trading/backtesting/signal-halflife.md) — alpha decay compression context
- [Multiple Testing & Statistical Significance](../trading/backtesting/multiple-testing.md) — critical for LLM-generated factor pools
- [Survivorship Bias & Universe Construction](../trading/backtesting/survivorship-bias.md) — all LLM mining systems inherit universe bias
