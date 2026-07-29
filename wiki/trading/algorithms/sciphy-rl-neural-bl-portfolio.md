---
type: wiki-page
created: 2026-07-28
updated: 2026-07-28
tags: reinforcement-learning, portfolio-optimization, black-litterman, neural-networks, HJB, PINN, H472, H473
---

# SciPhy RL and Neural Black-Litterman: Physics-Informed Portfolio Construction (2026)

Two July 2026 arXiv papers attack the same problem — moving from ad-hoc rule-based portfolio construction to principled, data-driven weight allocation — from complementary directions. SciPhy RL (arXiv:2607.15195) solves the dynamic control problem via physics-informed neural networks; Neural BL (arXiv:2607.20533) replaces subjective Bayesian views with learned neural predicates. Both are candidates for upgrading the production ETF allocation layer beyond simple top-1 selection.

---

## SciPhy RL: Portfolio Optimization via HJB-PINN (arXiv:2607.15195)

**Authors:** Igor Halperin & Andrey Itkin  
**Hypothesis stub:** H472

### Core Idea

Standard deep RL for portfolio optimization requires iterative environment simulation (rollouts, value iteration, policy gradient updates). SciPhy RL eliminates the simulation loop by:

1. **Casting the problem as a continuous-time HJB equation** — the Hamilton-Jacobi-Bellman PDE that characterizes the optimal policy when state dynamics are known (or estimated from data).
2. **Projecting HJB onto historical trajectories** — the "pathwise Hamilton-Jacobi" trick converts the PDE into a regression problem over observed paths, solvable from fixed historical data.
3. **Solving with PINN** (Physics-Informed Neural Network) in a **single offline sweep** — no iterative policy updates, no environment.reset() calls.

The result is an offline-learned Gibbs optimal policy that can be applied directly to new market data.

### Technical Details

| Component | Implementation |
|-----------|---------------|
| State space | Portfolio weights, cumulative transaction costs, momentum features |
| Control variable | Discrete target holdings (not continuous trading rate) |
| Transaction cost model | Quadratic price impact (microstructure-grounded) |
| Solver | PINN with physics residual loss (HJB residual) + data fitting loss |
| Training regime | Single offline pass over historical IS period |

**Key advantage over FinRL/PPO:** No environment simulation, no reward shaping, no gym wrappers. The entire optimization collapses to supervised learning on historical data with physics constraints.

### Validation

- **Universe:** 14-asset ETF portfolio (not named in abstract; estimated to be diverse multi-asset)
- **Signal:** Engineered oracle signal (paper uses artificial signal to isolate portfolio construction from signal quality)
- **Result:** Gibbs policy achieves "substantial OOS Sharpe improvement" over static and myopic baselines
- **Paper length:** 69 pages; full empirical detail

### Adaptation to H026/H041a/H045

The H026 canonical signal (12m momentum rank) can replace the oracle signal as input. Key adaptations:
- Monthly rebalancing → discretize continuous-time formulation at Δt = 1/12 year
- 25-asset H026 universe (larger than paper's 14-asset test)
- PINN overfitting guard: IS/validation split within training window

**H472 design:** Test whether SciPhyRL portfolio weights outperform top-1 selection when the underlying signal is H026 momentum.

---

## Neural Predicates in Black-Litterman (arXiv:2607.20533)

**Author:** Marcos Florencio  
**Hypothesis stub:** H473  
**Submitted:** July 10, 2026

### Core Idea

The Black-Litterman (BL) model shrinks portfolio weights toward market equilibrium, scaled by investor views (P matrix, q vector) and view uncertainty (Omega matrix). The problem: views are historically subjective and require expert judgment to calibrate.

Neural predicates replace subjective views with a learned compositional hierarchy:

```
Raw financial data
    → Lower-level predicates (classify momentum/value/macro signals)
    → Higher-level predicates (compose into market stances)
    → BL inputs: P (pick matrix), q (view returns), Omega (view uncertainty)
    → BL posterior weights
    → Portfolio
```

**Key insight:** View confidence is derived from predicate output *distributions* — not hand-specified. A predicate with high output entropy → high Omega (uncertain view). A predicate with sharp output distribution → low Omega (confident view).

### BL Model Refresher

$$\mu_{BL} = \left[(\tau\Sigma)^{-1} + P^T \Omega^{-1} P\right]^{-1} \left[(\tau\Sigma)^{-1} \Pi + P^T \Omega^{-1} q\right]$$

Where:
- $\Pi = \lambda \Sigma w_{mktcap}$ — equilibrium returns (risk aversion × covariance × market weights)
- $P$ — which assets the views relate to
- $q$ — the expected excess return of each view
- $\Omega$ — uncertainty of each view
- $\tau$ — scaling parameter (typically 0.01–0.05)

Neural predicates generate P, q, and Omega from data, eliminating subjective calibration.

### Adaptation to H026

For our 25-asset H026 ETF universe:
- **Market cap weights:** yfinance `.info['marketCap']` for AUM-weighted equilibrium
- **Predicate inputs:** [r_12m, r_3m, r_1m, VIX_z, above_200MA] per ETF
- **Predicate architecture:** 2-layer MLP, softmax output → probability distribution over {outperform, neutral, underperform}
- **View generation:** Top-k ETFs with outperform probability > 0.6 → P rows; magnitude → q entries; entropy → Omega diagonal

**Expected benefit vs H026 top-1:** On high-uncertainty months (many ETFs with similar momentum scores), BL shrinkage toward equilibrium reduces overconfidence. On low-uncertainty months (clear leader), BL concentrates weights similarly to top-1.

### H473 Variants

| Variant | Description |
|---------|-------------|
| Var A | Momentum-only predicates (3 signals) |
| Var B | Momentum + macro predicates (VIX, SPY 200MA, yield curve) |
| Var C | Var B + H301 safety overlay (BIL when SPY < 200MA) |
| Var D | Equal-weight BL (flat prior — sanity check) |

**Gate:** OOS Sharpe > 2.610 (H346 OB-filter baseline), MaxDD not worse than -5%.

---

## Comparison: SciPhy RL vs Neural BL

| Dimension | SciPhy RL (H472) | Neural BL (H473) |
|-----------|-----------------|-----------------|
| **Paradigm** | Dynamic control (HJB) | Bayesian portfolio (BL) |
| **Training** | PINN offline on historical paths | MLP predicates, cross-validated |
| **Uncertainty** | Embedded in cost model | Explicit in Omega matrix |
| **Market equilibrium** | No (learned from signal alone) | Yes (Pi shrinkage toward mktcap) |
| **Interpretability** | Low (PINN black box) | Medium (predicate hierarchy) |
| **Implementation complexity** | High (PINN setup) | Medium (BL + small MLPs) |
| **Expected alpha source** | Better turnover/cost control | Better diversification on ambiguous months |

---

## Cross-references

- [Position Sizing & Portfolio Construction](position-sizing.md) — Kelly and vol-targeting framework
- [Portfolio Optimization Libraries](../tools/portfolio-optimization.md) — PyPortfolioOpt BL implementation
- [Momentum Strategies](momentum-strategies.md) — H026 canonical signal used as input
- [Regime Detection](regime-detection.md) — macro regime gate analog
- [DeePM — Regime-Robust Deep Portfolio Manager](deepm-regime-portfolio.md) — related deep learning portfolio approach
- [Deep RL for Trading](deep-rl-trading.md) — FinRL/PPO context for why SciPhy avoids simulation loop
- [H472 Staged Proposal](../../dream_cycle/staged/2026-07-28/h472_sciphy_rl_etf_portfolio.json)
- [H473 Staged Proposal](../../dream_cycle/staged/2026-07-28/h473_neural_predicates_black_litterman.json)
