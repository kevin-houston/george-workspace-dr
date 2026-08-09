---
type: concept-page
created: 2026-08-09
updated: 2026-08-09
tags: reinforcement-learning, markov-decision-process, dynamic-programming, hjb-equation
---

# Markov Decision Processes, Bellman Equations, and the HJB Equation

Core theoretical framework underlying every RL-in-finance approach in this wiki. Extracted primarily from [Foundations of Reinforcement Learning with Applications in Finance (Rao & Jelvis)](../sources/rl-for-finance-book-rao-jelvis.md), which builds it up from first principles.

## The framework

- **Markov Process**: a sequence of states where the next state depends only on the current state (Markov Property), not on history.
- **Markov Decision Process (MDP)**: adds an Agent taking Actions and receiving Rewards on top of the state transitions. Defined by (State space, Action space, transition probabilities `p(r, s' | s, a)`, discount factor `γ`).
- **Policy** `π`: a (possibly stochastic) mapping from states to actions.
- **Value Function**: `V^π(s) = E_π,p[G_t | S_t = s]`, the expected discounted return from state `s` under policy `π`.
- **Bellman Equation**: the recursive relationship expressing `V^π(s)` in terms of `V^π` at the *next* state:

      V^π(s) = Σ_{r,s'} p(r,s' | s, π(s)) · (r + γ·V^π(s'))

  This recursion is the load-bearing idea of the entire field — nearly every algorithm (value iteration, policy iteration, TD-learning, Q-learning, DQN, policy gradient) is a different way of solving or approximating this one equation.

## Dynamic Programming vs. Reinforcement Learning

Both are answers to the same Bellman equation:

- **Dynamic Programming (Planning)**: transition probabilities `p` are known. Solve directly via value/policy iteration.
- **Reinforcement Learning (Learning)**: `p` is unknown. Learn `V` or the optimal policy from sampled experience (Monte Carlo returns, Temporal-Difference updates, or model-based estimation of `p` itself).

## Continuous time: the Hamilton-Jacobi-Bellman (HJB) equation

Taking the Bellman equation's discrete-time recursion to the continuous-time limit produces the **HJB equation** — a PDE characterizing the optimal value function and policy when state dynamics are continuous (e.g., an asset price following a diffusion process). Solving an HJB equation, in closed form or numerically, is equivalent to solving the control problem optimally.

This is the same PDE machinery used by:
- [SciPhy RL](../trading/algorithms/sciphy-rl-neural-bl-portfolio.md) — solves the HJB equation via a Physics-Informed Neural Network (PINN) in a single offline sweep over historical paths, rather than deriving a closed form.
- The **Avellaneda-Stoikov** optimal market-making model in [Market Microstructure & HFT](../trading/algorithms/market-microstructure.md) — derived from an HJB PDE with a closed-form perturbation-series solution in inventory.
- **Merton's Portfolio Problem** (dynamic asset allocation and consumption) — the classical continuous-time HJB solution for optimal investment/consumption splits over a lifetime.

## Why this matters here

Every applied RL-trading paper in [Deep RL for Trading](../trading/algorithms/deep-rl-trading.md) (FinRL/PPO/DDPG benchmarks, H204, H370, H371) is implicitly solving or approximating a Bellman/HJB equation via a neural network, without necessarily stating so explicitly. Understanding the underlying MDP formalism makes it possible to evaluate whether a given paper's "novel" architecture is actually doing something structurally new, or just approximating the classical Bellman recursion with more parameters.

## Cross-references

- [Foundations of Reinforcement Learning with Applications in Finance (Rao & Jelvis)](../sources/rl-for-finance-book-rao-jelvis.md) — primary source
- [SciPhy RL and Neural Black-Litterman](../trading/algorithms/sciphy-rl-neural-bl-portfolio.md) — HJB-PINN application
- [Market Microstructure & HFT](../trading/algorithms/market-microstructure.md) — Avellaneda-Stoikov HJB derivation
- [Deep RL for Trading](../trading/algorithms/deep-rl-trading.md) — applied RL context
- [Igor Halperin](../people/igor-halperin.md) — QLBS, option hedging as MDP
- [Ashwin Rao](../people/ashwin-rao.md)
