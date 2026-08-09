---
type: people-page
created: 2026-07-28
updated: 2026-07-28
tags: quantitative-finance, reinforcement-learning, physics-informed-ml, portfolio-optimization
---

# Igor Halperin

Quantitative researcher at the intersection of physics-informed machine learning and financial portfolio optimization. Primary relevance to the trading project: SciPhyRL framework (arXiv:2607.15195) and prior work on Information Ratio-optimal portfolio construction.

## Affiliation

NYU Tandon School of Engineering (as of 2026 papers). Previously at J.P. Morgan Quantitative Research.

## Key Contributions Relevant to This Project

### SciPhy RL (2026) — arXiv:2607.15195

Co-authored with Andrey Itkin. Applies Scientific Physics-Informed Reinforcement Learning to portfolio optimization:
- HJB equation projected onto historical data paths → pathwise Hamilton-Jacobi equation
- PINN solver in single offline sweep (no iterative RL training)
- Validated on 14-asset ETF universe with substantial OOS Sharpe improvement
- **H472 design basis**

See [SciPhy RL and Neural BL — Physics-Informed Portfolio Construction](../trading/algorithms/sciphy-rl-neural-bl-portfolio.md).

### QLBS Model (Halperin, 2017/2019)

Q-Learning Black-Scholes option pricing: treats option hedging as an MDP, uses fitted Q-iteration on historical data. Predecessor conceptually to SciPhyRL — the same "offline RL on historical paths" philosophy applied to derivatives.

Key insight (QLBS → SciPhyRL lineage): Halperin consistently avoids environment simulation in favor of offline learning on observed trajectories. SciPhyRL is the portfolio generalization of this principle with physics constraints added.

### Information Ratio Regularization

Earlier work on portfolio construction using information ratio as the optimization objective rather than Sharpe ratio, with ridge-regularization for high-dimensional factor models. Directly relevant to H202-XL / H415 multi-factor designs.

## Research Style

- Physics-informed approach: converts financial optimization problems to PDE form, then uses numerical PDE methods (PINN) rather than pure ML
- Avoids look-ahead bias by strictly separating offline training from OOS evaluation
- Emphasizes interpretability through physics-grounded loss functions

## Cross-references

- [SciPhy RL and Neural BL Portfolio](../trading/algorithms/sciphy-rl-neural-bl-portfolio.md) — primary paper page
- [Deep RL for Trading](../trading/algorithms/deep-rl-trading.md) — broader RL in finance context
- [Position Sizing & Portfolio Construction](../trading/algorithms/position-sizing.md)
- [H472](../../dream_cycle/staged/2026-07-28/h472_sciphy_rl_etf_portfolio.json) — SciPhyRL application to H026
- [From Text to Alpha (2026)](../trading/data-sources/from-text-to-alpha-disclosure-tracking-2026.md) — co-authored (13-author team) LLM disclosure-tracking paper, arXiv:2510.03195 ← new 2026-08-08
