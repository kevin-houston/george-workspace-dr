---
type: people-page
created: 2026-08-09
updated: 2026-08-09
tags: reinforcement-learning, markov-decision-process, education, quantitative-finance
---

# Ashwin Rao

Author (with Tikhon Jelvis) of [Foundations of Reinforcement Learning with Applications in Finance](../sources/rl-for-finance-book-rao-jelvis.md), a from-scratch MDP/RL textbook built around a Stanford course of the same name. Teaches RL for finance with an emphasis on deriving the theory (Bellman equations, HJB, MDP formalization) before touching any algorithm, and implementing everything in bare-bones Python rather than relying on RL libraries.

## Key Contributions Relevant to This Project

### Foundations of RL with Applications in Finance (book, with Tikhon Jelvis)

Rigorous MDP/Bellman/HJB framework applied to five financial control problems: dynamic asset allocation & consumption (Merton's Portfolio Problem), derivatives pricing & hedging (American options, incomplete markets), and order-book trading (optimal execution, optimal market-making). See the [source page](../sources/rl-for-finance-book-rao-jelvis.md) for full breakdown.

Notably derives the **Avellaneda-Stoikov market-making model** and the **Bertsimas-Lo-style linear-impact optimal execution result** (`N*_t = R_t/(T-t)`, uniform split of remaining shares over remaining time) from first principles via backward-induction Bellman recursion — both already referenced in [Market Microstructure & HFT](../trading/algorithms/market-microstructure.md) without derivation until now.

## Research Style

- Principles-first: derive the Bellman equation and MDP formalism before introducing any specific algorithm.
- Builds working code from scratch (numpy-level) rather than wrapping RL libraries, to keep the underlying math visible.
- Treats Dynamic Programming and Reinforcement Learning as two solution methods for the same recursive equation (known vs. unknown transition probabilities), not as separate fields.

## Cross-references

- [Foundations of Reinforcement Learning with Applications in Finance](../sources/rl-for-finance-book-rao-jelvis.md) — primary work
- [MDP / Bellman Equations / HJB — Concept Reference](../concepts/mdp-bellman-equations.md)
- [Market Microstructure & HFT](../trading/algorithms/market-microstructure.md) — Avellaneda-Stoikov and optimal execution derivations
- [Igor Halperin](igor-halperin.md) — related MDP/RL-in-finance lineage (QLBS, SciPhyRL)
- [Deep RL for Trading](../trading/algorithms/deep-rl-trading.md)
