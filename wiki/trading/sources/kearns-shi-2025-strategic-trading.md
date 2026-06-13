---
added: 2026-06-13
category: theory / execution
url: https://arxiv.org/abs/2502.07606
---

# Algorithmic Aspects of Strategic Trading (Kearns & Shi, 2025)

**Authors**: Michael Kearns and Mirah Shi (University of Pennsylvania)
**Date**: June 10, 2025
**arXiv**: 2502.07606
**Source file**: `sources/arxiv_2502_07606.pdf`

---

## What This Paper Is

An algorithmic game theory paper about **optimal trade execution in a multi-player competitive setting**. Not a signal-generation or alpha-mining paper — it answers the question: *if multiple informed traders all need to acquire (or sell) a fixed position over a fixed window, what is the equilibrium execution schedule?*

Built on the Chriss (2024) series of papers that established the model. Kearns & Shi add the **algorithmic and learning perspective**: how do you compute equilibria efficiently, and what kind of equilibria can be reached by simple learning dynamics?

---

## The Model

**Setup**: N players. Each player i wants to acquire a net position of V_i shares over T time steps. Trading in discrete time; shares in whole units.

**Action**: Strategy a_i is a cumulative schedule: a_i(0)=0, a_i(T)=V_i. The flow at time t is a'_i(t) = a_i(t) - a_i(t-1). Strategies can include intermediate selling (a'_i(t) < 0).

**Two sources of market impact:**

```
Temporary impact:  c_temp(a_i, a_{-i}) = Σ_t  a'_i(t) · Σ_j a'_j(t)
                   — your flow × everyone's simultaneous flow

Permanent impact:  c_perm(a_i, a_{-i}) = Σ_t  a'_i(t) · Σ_j a_j(t-1)
                   — your flow × everyone's accumulated prior positions
```

**General cost** (κ ≥ 0 controls the permanent/temporary mix):

```
c(a_i, a_{-i}) = Σ_t a'_i(t) · [Σ_j a'_j(t)  +  κ · Σ_j a_j(t-1)]
```

**κ interpretation:**
- κ = 0: temporary impact only (spread orders to avoid simultaneous competition)
- κ = 2: permanent impact twice as large as temporary (front-run others)
- κ > 2: permanent increasingly dominates (aggressive front-running optimal)

**Order book interpretation**: Temporary impact = linear sell-book model (uniform price distribution). Permanent impact = shares consumed are never replenished. κ is a liquidity replenishment rate — intermediate κ = new sell orders arrive at prior prices at some rate.

---

## Key Theoretical Results

### 1. Best-Response DP (Section 3)

A best response for player i to any fixed profile of other players' strategies can be computed in O((θ_U − θ_L)^2 · T^2) time via dynamic programming.

Key insight: the optimal schedule from time t depends only on accumulated prior positions (the "state"), so the problem has optimal substructure.

### 2. Game Decomposition (Section 4)

The general cost function decomposes as:

```
c(a_i, a_{-i}) = (1 - κ/2) · c_temp  +  κ · c_perm-avg
```

where c_perm-avg averages the permanent cost over t-1 and t.

**Structural implications:**
- **c_temp defines a potential game** → best-response dynamics converge to pure NE when κ=0
- **c_perm-avg defines a constant-sum game** → when κ=2, the game is zero-sum
- **General game is a mixture**: potential (κ=0) → zero-sum (κ=2) → past zero-sum (κ>2)

**Formal proof that best-response dynamics can cycle** for any κ > 0: constructive example with T=5, two players; the strategies oscillate and never converge.

### 3. FTPL for Coarse Correlated Equilibria (Section 5)

Since Nash equilibrium is intractable for the general game, the paper targets **Coarse Correlated Equilibria (CCE)** — a weaker but practically useful equilibrium concept where no player can improve by deviating to any fixed strategy.

**Algorithm: Follow the Perturbed Leader (FTPL)**

```
For each round r:
  H_r = cumulative opponent cost vectors
  N_r ~ Uniform[0, η]^d  (noise vector)
  Choose a_{i,r} = argmin_{a ∈ A_i} ⟨f(a), H_r + N_r⟩
  Observe opponent actions; update H_r
```

The optimization in each round reduces to the best-response DP (Algorithm 1), keeping per-round cost polynomial.

**Complexity:**
- Per-round: O(θ^2 T^2) per player
- Rounds to ε-CCE: R = O(n^2 θ^5 T^6 / ε^2)
- Regret bound: O(nθ^(5/2) T^3 / √R)

**No-regret property**: FTPL guarantees vanishing regret against *any* adversarial sequence of opponent actions — not just equilibrium play. A single player can run FTPL for no-regret guarantees even if others behave adversarially.

---

## Experimental Findings (Section 6)

**Setup**: 2 players, T=5, V_1=V_2=10, θ_L=−5, θ_U=5. 100 runs × 2500 rounds each. Varying κ.

**Convergence rate** (Figure 3): In practice, FTPL converges to approximate CCE in 500–1000 rounds across all κ — much faster than the O(T^6/ε^2) theory bound.

**κ-dependent behavior:**

| κ | Game type | Equilibrium structure | Convergence |
|---|-----------|----------------------|-------------|
| 0 | Potential | Pure NE found quickly | Fast, smooth regret |
| 0.5–1.5 | Mixed | Converges to pure NE after ~200 rounds | Fast |
| 2 | Zero-sum | Oscillating regret; NE is mixed | Medium, oscillatory |
| >2 | Past zero-sum | High correlation in joint equilibrium; no pure NE | Slow oscillation |

**Correlation** (Figure 6): At κ=0 and κ=2, TV distance between joint distribution and product of marginals is near zero (close to NE). For κ>2, high correlation — equilibrium requires coordinated action schedules.

**Welfare** (Figure 8): Total cost (welfare) increases with κ — more permanent impact → more harmful competition, larger potential gains from coordination/collusion. Collusion can emerge organically from FTPL learning.

**FTPL vs no-swap-regret** (Figure 5): FTPL achieves lower distance to CE than an explicit no-swap-regret algorithm (which theoretically guarantees CE) — a striking empirical finding.

---

## Practical Implications

### For current pipeline (ETF rotation, IBS, PEAD)
**Not directly relevant.** At our scale (paper trading, $100k portfolio, ETF-level liquidity), market impact from our trades is negligible. We are price-takers.

### If scaling to institutional size ($1M+ per trade, single equities)
**Directly applicable.** The FTPL execution algorithm would provide no-regret TWAP/VWAP-style scheduling that is robust to adversarial order flow. Key insight for large-block execution:

- **κ ≈ 0 (liquid market, fast replenishment)**: Spread the order evenly — avoid competing with simultaneous flows
- **κ > 1 (illiquid, slow replenishment)**: Trade early and aggressively — permanent impact makes front-running optimal
- **Practical test**: estimate κ by comparing realized impact of spread vs. concentrated orders in the same stock

### Theoretical grounding for market phenomena
- **Front-running is a Nash equilibrium**, not just opportunistic predation — rational response to permanent impact
- **VWAP as an approximation**: Standard VWAP scheduling is approximately optimal in the κ=0 regime only
- **Block trade signaling**: Large institutional buys trigger permanent impact, making other players want to front-run — this is the mechanism, not just intuition

### Connection to AI alpha decay (arXiv:2605.23905)
Companion piece to the monoculture equilibrium paper already in our wiki. That paper deals with **strategy-layer crowding** (many funds use same signals → alpha = 0). This paper deals with **execution-layer crowding** (many funds execute same direction simultaneously → market impact explodes). Both are equilibrium failures from homogeneous AI adoption.

When FTPL is run by many players simultaneously, the joint distribution converges to a CCE that is still costly — crowding at the execution layer doesn't disappear just because everyone is individually optimal.

---

## Cross-References

- [Market Microstructure & HFT](../algorithms/market-microstructure.md) — order book dynamics, Almgren-Chriss single-player execution model (this paper extends to multi-player)
- [Signal Half-Life & Alpha Decay](../backtesting/signal-halflife.md) — AI alpha decay (arXiv:2605.23905) is the strategy-layer analog; this paper is the execution-layer analog
- [Transaction Cost Modeling](../backtesting/transaction-costs.md) — square-root impact law vs. linear impact model used here (Chriss simplification)

---

## Citation

Kearns, M. and Shi, M. (2025). "Algorithmic Aspects of Strategic Trading." arXiv:2502.07606.
