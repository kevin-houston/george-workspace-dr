---
created: 2026-07-16
updated: 2026-07-16
type: concept
category: Trading > Algorithms
source: arXiv:2607.08332
---

# XALPHA: Memory-Driven AI Quant Researcher for Alpha Discovery

Source: Liu, Fu, Wang & Liu (University of Hong Kong + Grace Investment Machine, July 2026). arXiv:2607.08332.

XALPHA represents the current frontier of fully automated alpha discovery: a closed-loop system that acts as an end-to-end AI quant researcher, absorbing financial reports, maintaining structured memory of prior experiments, generating testable hypotheses, writing executable factor code, backtesting it, and feeding empirical outcomes back into the next generation of ideas — all without human intervention.

---

## Problem Statement

Existing automated alpha mining approaches suffer from three structural weaknesses:

1. **One-shot generation**: Most LLM-based methods (FactorGPT, Alpha-GPT, QuantaAlpha) generate factors in a single pass without iterative refinement based on results. Each call to the LLM is independent — failed ideas are not remembered, successful patterns are not amplified.

2. **Knowledge amnesia**: LLMs don't inherently remember what signals have been tested, what failed, or what kinds of modifications improved weak signals. Without this memory, every generation risks re-exploring dead ends.

3. **Isolated steps**: Prior work automates either hypothesis generation OR code writing OR backtesting, but rarely all three in a tight continuous loop. The seams between these steps are where most information about what-works-and-why is lost.

XALPHA addresses all three by treating alpha discovery as a **report-grounded, memory-driven, continuous research loop** spanning multiple generations and research cycles.

---

## Architecture: Three Brains

XALPHA's core innovation is a **closed-loop multi-brain architecture** that separates concerns while maintaining tight feedback integration:

### Macro Brain — Research Planning

The Macro Brain operates at the highest level of abstraction. Its responsibilities:
- **Theme selection**: Given the accumulated memory of prior discovery cycles, selects the most promising research direction (e.g., "explore short-term reversal with vol-adjustment" or "test carry signals on fixed income ETFs")
- **Archetype routing**: Matches each theme to a research archetype (momentum, mean-reversion, quality, event-driven, microstructure) that shapes how the Micro Brain will generate and mutate hypotheses
- **Portfolio of themes**: Maintains a parallel portfolio of research directions, not a single sequential path — this prevents over-exploitation of one signal family

The Macro Brain reads structured summaries from the Cross Brain and a canonical set of financial research reports (arXiv papers, academic summaries) to ground its planning in empirically supported theory rather than unconstrained hallucination.

### Micro Brain — Hypothesis-to-Code Validation

The Micro Brain does the heavy execution work within each research cycle:
1. **Hypothesis pool construction**: Given a theme and archetype from Macro Brain, generates N candidate hypotheses (typically 5-15 per generation)
2. **Tri-alignment verification**: Before writing code, checks that each hypothesis satisfies three alignment criteria:
   - *Idea alignment*: the hypothesis is logically grounded in financial theory or empirical evidence
   - *Code alignment*: the proposed implementation is technically feasible and correctly implements the stated idea
   - *Financial plausibility*: expected magnitude, direction, and decay pattern of the signal are consistent with known market microstructure
3. **Factor code generation**: Writes executable Python/vectorized factor code implementing the hypothesis
4. **Automated backtesting**: Runs the factor against historical data, computes IC, ICIR, Sharpe, MaxDD
5. **Iteration**: Applies targeted mutations to underperforming factors based on the test results (e.g., "ICIR too low → try vol-normalizing", "Sharpe good but MaxDD too high → add momentum confirmation filter")

The tri-alignment verification step is XALPHA's most distinctive mechanism. Most LLM alpha miners generate factors that are logically coherent but financially implausible or code-correct but logically misspecified. The three-way check catches mismatches before they consume backtest budget.

### Cross Brain — Discovery Feedback Consolidation

The Cross Brain operates between research cycles, synthesizing what the Micro Brain learned:
- **Generation-level feedback**: "In generation 3, vol-adjusted reversal outperformed raw reversal by 0.15 IC. Hypothesis: normalization matters most for factors with high microstructure noise."
- **Cycle-level summaries**: Aggregates across all generations within a cycle — "Momentum archetype, this cycle: 6m no-skip dominates; carry augmentation helps bonds but hurts equities."
- **Archetype-level research cues**: Long-lived insights that persist across multiple cycles — "Trend signals on ETFs: need longer formation windows than equities; monthly rebalance not daily."

These consolidated insights are fed back to the Macro Brain as structured memory, completing the loop. The memory grows richer over time — XALPHA after 10 research cycles is fundamentally more capable than XALPHA after 1, because it has accumulated experiment-validated knowledge rather than just statistical associations from training data.

---

## Key Innovations vs Prior Work

| Feature | Alpha-GPT | QuantaAlpha | FactorEngine | XALPHA |
|---------|-----------|-------------|--------------|--------|
| Memory across generations | No | Partial (trajectory) | KB (static) | Yes (Cross Brain) |
| Theory grounding | User-provided | Minimal | Partial | Financial reports |
| Tri-alignment check | No | No | No | Yes |
| Multi-brain separation | No | No | No | Yes |
| Continuous loop | No | Yes | Partial | Yes |
| Evaluation on US stocks | Limited | Yes (transfer) | Limited | CSI300 (primary) |

### Comparison to H381 (AlphaLogics) and H382 (FactorEngine)

**AlphaLogics** (H381, arXiv:2603.20247) uses an explicit "market logic" abstraction layer between hypothesis generation and code production. Validated on S&P500. Its strength is interpretability — you can inspect what market reasoning drove each factor.

**FactorEngine** (H382, arXiv:2603.16365) separates factor logic from parameter optimization, using Bayesian HPO for parameter search and LLM for logic revision. Strong on structured search but limited memory across experiments.

**XALPHA** is more ambitious: the tri-alignment check and three-brain architecture enable it to self-correct and accumulate knowledge continuously. However, the primary validation is on CSI300 (Chinese A-shares), raising the usual transfer-to-US-equities question.

---

## Results

Primary evaluation on **CSI300** (Chinese A-share index constituents):

- XALPHA discovers factors with **stronger and more robust IC** than representative baselines (Alpha-GPT, FactorGPT, evolutionary mutation without memory)
- **CSI300 OOS annual IC**: XALPHA achieves statistically significant positive IC in all evaluation years, with lower IC decay than alternatives — consistent with the memory mechanism preventing re-exploration of decaying factor families
- **Qualitative pattern**: Factors generated in later research cycles tend to be more complex and targeted than early-cycle factors, showing genuine knowledge accumulation

Important caveat: the paper does not report Sharpe ratios or Calmar ratios for a portfolio built on XALPHA factors — it reports information coefficients, which are a rank correlation between predicted and realized returns. IC > 0.05 is generally considered economically meaningful; IC > 0.10 is strong.

---

## Relevance to George's Alpha Discovery Pipeline

### Immediate structural analog

George's **dream cycle** is a manual implementation of roughly the same research loop:
- Macro Brain → George reads arXiv, identifies themes
- Micro Brain → George generates hypothesis stubs with gate criteria
- Cross Brain → `hypothesis-log.md` accumulates outcomes; CLAUDE.local.md carries forward key lessons

XALPHA shows what a fully automated version of this loop looks like. The tri-alignment check is directly analogous to George's pre-hypothesis validation:
- Idea: "does this signal have a theoretical basis?"
- Code: "is the implementation clean and bias-free?"
- Financial plausibility: "is the expected effect size realistic given our confirmed base rates?"

### H407 path

H407 (proposed below) tests XALPHA's three-brain architecture on H198's 30-stock US large-cap universe, bootstrapped with the 400+ experiment history in `hypothesis-log.md` as pre-loaded Cross Brain memory. The key research question: does memory of prior US large-cap experiments improve discovery speed vs starting cold?

### Dream cycle integration

The Cross Brain's "edit motif" concept closely parallels H396 (AlphaMemo, arXiv:2606.20625). The combination — XALPHA's three-brain loop + AlphaMemo's edit-motif library — would give George a systematic way to both generate new hypotheses AND avoid re-running confirmed failures.

---

## Implementation Path

XALPHA is not open-sourced in the July 2026 paper. However, the architecture can be implemented with existing tools:

```python
# Pseudo-implementation sketch

class MacroBrain:
    """Plans research themes and archetype routing."""
    def select_theme(self, memory: CrossBrainMemory, financial_reports: list) -> ResearchTheme:
        # Prompt GPT-4o with memory summary + recent arXiv abstracts
        # Returns: theme, archetype, N_hypotheses, exploration vs exploitation balance
        ...

class MicroBrain:
    """Generates and validates hypothesis-to-code pipeline."""
    def generate_factors(self, theme: ResearchTheme) -> list[Factor]:
        ...
    
    def tri_align_check(self, factor: Factor) -> bool:
        """Checks idea/code/plausibility alignment before backtesting."""
        ...
    
    def backtest_and_iterate(self, factors: list[Factor]) -> list[FactorResult]:
        ...

class CrossBrain:
    """Consolidates results into persistent memory."""
    def consolidate(self, results: list[FactorResult], memory: CrossBrainMemory) -> CrossBrainMemory:
        ...
```

OpenAI API cost estimate for a 3-cycle XALPHA run on H198 universe:
- Macro Brain: ~3 GPT-4o calls per cycle = ~$0.30/cycle
- Micro Brain: ~20 hypothesis × 3 validation steps × 3 cycles = ~$5-10
- Cross Brain: ~3 consolidation calls = ~$0.60/cycle
- **Total: ~$20-35 per 3-cycle run** (similar to H381/H382 estimates)

---

## Connections and Cross-References

- [AI-Driven Alpha Factor Discovery](auto-alpha-discovery.md) — taxonomy of LLM alpha mining systems; XALPHA fits as "Method 10"
- [LLM Alpha Validation Checklist](llm-alpha-validation.md) — XALPHA's tri-alignment check is a pre-validation variant of this checklist
- [Bilevel Autoresearch](../concepts/bilevel-autoresearch.md) — XALPHA is an applied instance of the Level 2 mechanism injection framework
- [Hypothesis Log](../backtesting/hypothesis-log.md) — H407 stub: XALPHA on H198 US large-cap universe
- [Smart Money Concepts ICT](smart-money-concepts-ict.md) — H396 AlphaMemo edit motifs are a complementary mechanism to XALPHA's Cross Brain

---

## H407 Stub

```
h407_status: STUB (2026-07-16) — XALPHA Three-Brain Alpha Discovery on H198 US Large-Cap Universe.
Source: Liu et al. (2026) arXiv:2607.08332, University of Hong Kong + Grace Investment Machine.
Design: Implement simplified XALPHA architecture bootstrapped from hypothesis-log.md as Cross Brain
memory (400+ experiments with outcomes). Three phases:
  Phase 1 (Macro Brain): seed 3 research themes from highest-IC signals in hypothesis-log.md
    — 6m no-skip momentum variants, IMOM signal family, OB overlay patterns.
  Phase 2 (Micro Brain): for each theme, generate 10 hypotheses, apply tri-alignment check
    (theory/code/plausibility), backtest survivors, iterate 2-3 generations per theme.
  Phase 3 (Cross Brain): consolidate into updated research memo; flag top-3 factors for full OOS.
Gate: At least 1 generated factor achieves OOS IC > 0.05 AND OOS Sharpe > 1.174 on H198 universe.
IS: 2013-2020, OOS: 2021-2026. API cost: ~$20-40 OpenAI.
Script: backtesting/daily/run_h407_xalpha.py (stub).
```
