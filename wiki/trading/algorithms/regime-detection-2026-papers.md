---
title: Regime Detection 2026 — Wasserstein-HMM and Heavy-Tail Emission Papers
tags: regime-detection, HMM, Wasserstein, heavy-tail, portfolio-allocation, geometric-observables
added: 2026-07-25
updated: 2026-08-05
category: Trading / Algorithms
source_papers:
  - arXiv:2603.04441 (Boukardagha 2026, Columbia)
  - arXiv:2606.23492 (Alswaidan, Jin, Varner 2026)
  - arXiv:2605.17117 (Geometric Observables v2 / Berry Phase Rate)
hypothesis_refs: H444, H445, H252 (H252b candidate)
---

# Regime Detection 2026 — Wasserstein-HMM and Heavy-Tail Emissions

Extends the [Regime Detection](regime-detection.md) base page with two 2026 papers that directly
address unresolved weaknesses in H429 (rolling Wasserstein-HMM, confirmed) and the broader HMM
regime detection family.

---

## Paper 1: Explainable Regime-Aware Investing (arXiv:2603.04441)

**Boukardagha, Columbia University, February 2026**

### Core Contributions

1. **Dynamic model-order selection**: Number of HMM states adapts via rolling BIC on each window.
   - K = 2..4 tested; BIC selects K each period
   - Eliminates the K=2 hard-code assumption in H429
   - Minimum K=2 enforced to avoid degenerate 1-state solution

2. **2-Wasserstein state identity tracking**: When K stays constant, new states are matched to
   previous states by minimizing 2-Wasserstein distance between Gaussian components:
   ```
   W²(N(μ₁,Σ₁), N(μ₂,Σ₂)) = ||μ₁-μ₂||² + Bures(Σ₁, Σ₂)
   ```
   This preserves economic interpretability — "bull regime" in month t corresponds to the
   same distributional state as "bull regime" in month t+1.

3. **Transaction-cost-aware MVO (TC-MVO)**: Regime probabilities are embedded into a
   mean-variance optimization with an L2 turnover penalty:
   ```
   max  μ'w - (1/2) w'Σw - λ ||w - w_prev||²
   s.t. Σwᵢ = 1, wᵢ ∈ [w_min, w_max]
   ```
   Replacing hard binary allocations with TC-MVO reduces unnecessary turnover.

### Empirical Results

- Universe: daily cross-asset data (SPY/TLT/GLD + DBC) 2005-2026
- Wasserstein HMM: **Sharpe 2.18** vs. equal-weight 1.59 vs. SPX B&H 1.18
- MaxDD: **-5.43%** vs. -14.62% for SPX
- During Liberation Day 2025 (equity selloff): dynamically reduced equity, shifted to defensive
  assets — demonstrating real-time regime adaptiveness

### Relationship to H429

H429 confirmed rolling Wasserstein-HMM on SPY/TLT/GLD (Var C OOS Sharpe 1.144, MaxDD -17.2%).
This paper's improvements over H429:
- BIC model-order selection vs. fixed K=2
- TC-MVO vs. hard binary SPY/TLT/GLD weights
- Cross-asset universe including DBC (commodity exposure)

**H444 implements this design on the SPY/TLT/GLD/DBC universe.**

---

## Paper 2: Continuous Hidden Markov Models for Equity Returns: Heavy-Tail Emission Families (arXiv:2606.23492)

**Alswaidan, Jin, Varner, June 2026**

### Core Contributions

The paper revisits continuous HMMs by separating two failure modes of the classic Gaussian HMM:

1. **Temporal structure**: Governed by the regime chain (HMM transition matrix)
2. **Marginal distribution**: Governed by per-regime emission density

Classic HMMs conflate both. This paper fixes the emission side while keeping the temporal structure.

### Unified EM Framework

Places four emission families under shared forward-backward recursions:

| Emission Family | Parameters | Fat-Tail? | VaR Property |
|---|---|---|---|
| **Gaussian** | μ, σ | No | Underestimates tail risk in stress |
| **Student-t** | μ, σ, ν (df) | Yes | Conditional VaR passes coverage tests |
| **Laplace** | μ, b | Moderate | Analytical VaR: b·log(2(1-p)) |
| **Generalized Error** | μ, σ, β | Flexible | Nests Gaussian (β=2) and Laplace (β=1) |

All four use identical E-step (forward-backward) with emission-specific M-step.

**Quantile-based initialization**: Rather than K-means initialization (which ignores tail structure),
the paper initializes emission parameters from empirical quantiles of the training data. More robust
convergence, especially for heavy-tailed distributions.

### Key Empirical Findings

On daily US equity returns (individual stocks + ETFs, 2000-2025):

- **Gaussian HMM**: Severely underestimates tail risk; regime-conditional VaR fails coverage tests
  (observed tail exceedances > theoretical 5% frequency)
- **Student-t HMM**: Closes ~80% of the fit gap; passes conditional VaR coverage tests
- **Laplace HMM**: Similar to Student-t; slightly better in left-tail (crash scenarios)
- **Key result**: "On daily US equities, a simple interpretable Markov model with heavy-tail
  emissions suffices and yields regime-conditional VaR that passes conditional-coverage tests"

### Regime-Conditional VaR as Position Sizing Tool

The paper demonstrates that regime-conditional VaR from heavy-tail HMMs can serve as a
position sizing signal:

```
Scale(t) = min(1, VaR_threshold / VaR_regime(t))
```

In bear/high-vol regimes, the Student-t/Laplace VaR is substantially higher than Gaussian VaR,
triggering earlier de-risking before drawdowns materialize.

### Relationship to H429 and H165a

- H429 used Gaussian emissions (hmmlearn default) — this paper suggests Student-t improves VaR calibration
- H165a (VIX < 25 gate): the VIX threshold is a crude proxy for what heavy-tail HMM does analytically
- H445 tests whether replacing the binary VIX gate with Student-t HMM VaR scaling improves H026

---

## Implementation Notes

### Fitting Heavy-Tail HMMs in Python

`hmmlearn` only supports Gaussian and GMM emissions natively:
- **Student-t approximation**: Use GMMHMM (3-component GMM per state approximates t-distribution)
- **Laplace (exact)**: Implement custom M-step via moment matching (var(Laplace) = 2b² → b = σ/√2)
- **Full custom**: Use PyTorch for differentiable EM (avoids hmmlearn limitations)

```python
from hmmlearn.hmm import GMMHMM

# Student-t approximation via 3-component GMM
model_t = GMMHMM(n_components=2, n_mix=3, covariance_type='diag',
                 n_iter=200, random_state=42)
model_t.fit(returns.values.reshape(-1, 1))
```

### Laplace VaR (Analytical)

```python
def laplace_var(mu: float, sigma: float, confidence: float = 0.95) -> float:
    """Analytical VaR for Laplace distribution. Returns positive loss."""
    b = sigma / (2 ** 0.5)  # Laplace scale from variance: Var = 2b^2
    if confidence > 0.5:
        var = -(mu - b * np.log(2 * (1 - confidence)))
    else:
        var = -(mu + b * np.log(2 * confidence))
    return max(var, 0.0)
```

### Wasserstein State Matching (Bures Metric)

```python
def bures_distance(S1: np.ndarray, S2: np.ndarray) -> float:
    """Bures metric between two PSD matrices for Wasserstein-2 distance."""
    S1h = np.linalg.cholesky(S1 + 1e-8 * np.eye(S1.shape[0]))
    M = S1h @ S2 @ S1h.T
    eigvals = np.maximum(np.linalg.eigvalsh(M), 0)
    return np.trace(S1) + np.trace(S2) - 2 * np.sum(np.sqrt(eigvals))

def w2_distance_gaussians(mu1, S1, mu2, S2) -> float:
    return np.sum((mu1 - mu2)**2) + bures_distance(S1, S2)
```

---

## Research Gaps and Open Questions

1. **BIC model-order selection on daily financial returns**: BIC penalizes complexity by log(n).
   For 3Y rolling windows (~750 days), log(750) ≈ 6.6. Does this provide adequate penalization
   against over-fitting to K=4 states during volatile sub-periods?

2. **TC-MVO vs. binary gate on concentrated momentum universes**: H026 top-1 selection is
   already concentration-maximizing. Applying TC-MVO may be at odds with the strategy's
   design philosophy of maximum conviction allocation.

3. **Heavy-tail emissions and HMM degeneracy**: H429 found that IS-frozen Gaussian HMM degenerates
   to a single dominant state. Does Student-t prevent degeneracy by better fitting extreme returns,
   or does degeneracy recur regardless of emission family?

4. **Cross-asset vs. single-asset regime estimation**: Both papers use multi-asset return vectors
   for HMM estimation. H445 uses SPY returns only (univariate HMM). Joint SPY/TLT/GLD estimation
   for H026 overlay could improve state discrimination.

---

## Research Lead: Geometric Observables v2 / Berry Phase Rate (arXiv:2605.17117, added 2026-08-05)

H252 (Berry Phase Rate regime detector) was NOT CONFIRMED on its original 3-asset
SPY/TLT/GLD universe — OOS AUC 0.550 fell short of the 0.65 gate, and the finding at the
time was that the universe was likely too narrow to give the geometric-phase estimator
enough cross-sectional structure to detect regime transitions reliably (VIX independence
was confirmed, |ρ|=0.095, so the signal isn't just re-deriving VIX — it just wasn't
strong enough standalone). This paper is a v2 revision of the same geometric-observables
approach and is the natural design basis for a **H252b** revival.

### Core idea

Treats a rolling window of asset return covariance structure as a path on a statistical
manifold and computes a discretized **Berry phase rate** — a geometric holonomy measure
of how much the covariance structure's principal-axis orientation rotates over the
window, rather than a purely statistical (HMM/BIC) state-transition detector. The
claim is that regime transitions manifest as measurable geometric curvature/rotation in
the return-covariance manifold before they show up as a clean shift in mean/variance
that a Gaussian HMM would pick up — i.e. a potentially earlier or orthogonal detection
signal to the Wasserstein-HMM approach in the two papers above.

### Relevance to H252b

The original H252 finding flagged the 3-asset universe as the likely bottleneck, not the
geometric method itself. This v2 paper's design is a candidate blueprint for widening
the input universe to 10+ sector ETFs (as flagged in the H252 hypothesis-log entry) —
more assets give the covariance manifold more dimensions to exhibit measurable curvature
in, which is exactly the axis the original test under-powered. Not yet backtested; this
is a design-basis note for whoever picks up H252b, not a confirmed result. Should be
read in full (only abstract/summary reviewed so far) before scoping the H252b backtest,
and cross-checked against the Boukardagha and Alswaidan/Jin/Varner papers above for
whether geometric holonomy and Wasserstein state-tracking could be combined (e.g. use
Berry phase rate as an early-warning trigger for when to re-run the Wasserstein state
matching) rather than treated as competing standalone detectors.

---

## Cross-references

- [Regime Detection](regime-detection.md) — VIX threshold, 200MA, base HMM methods; H165a confirmed
- [Trend-Following System Theory](trend-following-theory.md) — arXiv:2607.19497; spectral grounding for regime regimes
- [Multi-Memory Factor Model of US Equity Returns](../backtesting/multi-memory-factor-model-equity.md) — 5 memory factors; volatility regime shift 1988
- [Momentum Strategies](momentum-strategies.md) — H026 production strategy; H198 stock momentum
- [Regime Detection Signals — Practical Data Guide](../backtesting/regime-detection-signals.md) — SPY/VIX data pipeline for regime overlays
- [Regime-Conditional Distributional Strategy Evaluation](../backtesting/regime-conditional-strategy-eval.md) — GAMLSS distributional comparison conditioned on regimes
- [Regime-Conditional ESG Momentum](../../concepts/regime-conditional-esg-momentum.md) — ESG tilt design using regime-conditional scaling
