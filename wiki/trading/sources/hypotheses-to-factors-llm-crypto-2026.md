---
created: 2026-08-08
updated: 2026-08-08
type: source_summary
authors: Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye
published: 29 Apr 2026 (arXiv)
source: arXiv:2604.26747
url: https://arxiv.org/abs/2604.26747
---

# From Hypotheses to Factors: Constrained LLM Agents in Cryptocurrency Markets — Huang, Fan, Hu & Ye 2026

**Authors:** Yikuan Huang, Zheqi Fan, Kaiqi Hu, Yifan Ye
**Venue:** arXiv:2604.26747, submitted 29 Apr 2026

## Core idea: governance mechanism, not a new discovery algorithm

Most LLM alpha-mining papers George has already logged (AlphaLogics/H381, FactorEngine/H382 — see [AI-Driven Alpha Factor Discovery](../algorithms/auto-alpha-discovery.md)) focus on *how* an agent searches for signal. This paper instead focuses on *constraining what the agent is allowed to do* so the search process stays reproducible and auditable — a governance layer that sits on top of any discovery algorithm.

The mechanism:

1. Factor discovery is framed as a **controlled sequential search process**: agents propose testable investment hypotheses.
2. Every hypothesis is validated through a **deterministic evaluation system** with strict, structural controls on data separation, transaction costs, and portfolio testing — these controls live in the framework itself, not as a post-hoc checklist.
3. Agent actions are constrained to a **point-in-time factor DSL** (domain-specific language) — the agent literally cannot express a factor that violates PIT data separation, because the DSL doesn't have the vocabulary for it.
4. An **append-only experiment log** records every hypothesis, successful or not, mapped to its executable DSL operations — permanent audit trail.

## Results

A ridge-combined portfolio, trained exclusively on **2020-2022 data**, was evaluated out-of-sample on **2024-2026**: ~44.55% annualized return, Sharpe ratio 1.55, net of 5 bps trading costs.

## Relevance to George's process

This is close to a formalization of what George's own dream-cycle + hypothesis-log + LLM Alpha Validation Checklist already do by convention (staged JSON proposals with `apply_status`, the hypothesis-log's H-numbering, the 6-test pre-deployment gate). The DSL-level enforcement is the interesting delta: instead of a human/agent *checking* for look-ahead bias after writing a backtest script, the factor language itself makes the violation inexpressible. Concretely transferable idea: George's `run_hNNN.py` scripts could adopt a thin wrapper class (e.g., `PITSeries.shift(1)`-enforcing accessor) that raises at construction time if a signal is read before its as-of date, rather than relying on discipline alone — this would have caught the H256 unlagged-signal incident and the FRI/IBS look-ahead traps documented elsewhere in the backtesting section structurally rather than by review.

Application domain is cryptocurrency, not George's equity/ETF focus, and the specific factor DSL isn't released as open source per the abstract summary reviewed — so this is filed as a **process/tooling reference**, not a new trading hypothesis.

## See Also

- [AI-Driven Alpha Factor Discovery](../algorithms/auto-alpha-discovery.md) — algorithmic discovery methods this paper's governance layer would sit on top of
- [LLM Alpha Validation Checklist](../algorithms/llm-alpha-validation.md) — George's manual equivalent of this paper's structural DSL constraints
- [Hypothesis Log](../backtesting/hypothesis-log.md) — George's own append-only experiment log, same pattern as this paper's audit trail
- [Look-Ahead-Freedom as Temporal Non-Interference](../backtesting/lookahead-formal-verification.md) — formal treatment of the exact bias class the PIT DSL is designed to make inexpressible
