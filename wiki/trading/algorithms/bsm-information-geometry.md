---
updated: 2026-04-28
type: paper-summary
source: sources/ssrn-6630259-bsm-flat-limit-info-geometry.pdf
author: Bruce H. Dean, Ph.D.
date: April 2026 (Draft v0.18)
ssrn: 6630259
---

# BSM as the Flat Limit of Information Geometry (Dean 2026)

**Full title**: "Black-Scholes-Merton as the Flat Limit of Information Geometry"  
**Author**: Bruce H. Dean, Ph.D. (symplectic.research@gmail.com)  
**SSRN**: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6630259  
**Date**: April 2026, Draft v0.18; 14 pages

---

## One-line thesis

BSM is the exact pricing rule on the flat sub-manifold of the Fisher information manifold of return distributions; the volatility smile is what the pricing problem records when the market wanders off that flat slice into the curved region.

---

## Background: The BSM Paradox

BSM is universally acknowledged to misprice options away from short-maturity and at-the-money, yet it remains the universal coordinate system through which implied volatilities are quoted. SABR fits are curves through implied vols. Heston calibrations are reported as σ_impl(K,T). Dupire's local-vol surface inverts BSM at every strike.

Why is a formula that is "wrong everywhere" the market's universal language? The paper argues there is a single geometric explanation.

---

## The framework: Gaussian Fisher manifold

The space of return distributions is naturally a Riemannian manifold. For lognormal distributions parametrized by (µ, σ), Čencov's theorem selects the Fisher information metric uniquely (up to scale):

```
g_ij(µ, σ) = [1/σ²    0   ]
              [  0    2/σ² ]
```

This makes (M, g) a **Poincaré upper half-plane** of constant scalar curvature R = -1.

---

## Theorem 1: BSM is the flat slice

BSM prices exactly on the 1-dimensional flat sub-manifold:

```
L_σ₀ = {(µ, σ) ∈ M : σ = σ₀}
```

On this slice the induced metric is flat (curvature = 0), pricing reduces to a Gaussian integral, and BSM is exact.

**Validity condition**: The flat-slice approximation holds when

```
ν²T ≪ σ₀²
```

where ν = vol-of-vol (the rate at which σ itself moves). At SPY parameters (σ₀ ≈ 0.170, ν ≈ 1.22), this gives **T ≪ 7 days** — BSM is only a valid approximation for roughly one-week ATM options.

Every option beyond ~7 days is in the curved regime, and the smile records the curvature.

---

## The sign paradox (and its resolution)

**Historical problem**: Naively inserting the Fisher manifold's curvature R = -1 into the heat-kernel coefficient a₁ = R/6 = -1/6 predicts a *frown* (deep OTM options below ATM). Real equity smiles do the opposite — deep OTM puts trade at 30–60% above ATM vol.

**Resolution**: The sign paradox is a **category error**. The coefficient a₁ governs time-dependence of the transition density; the smile is strike-dependence at fixed time. These are different. Strike-dependence comes from geodesic distance off the flat slice, not from the heat-kernel diagonal.

**The real fix**: Equity markets have leverage correlation ρ = corr(dS/S, dσ) < 0 (typically ρ ∈ [-0.8, -0.5] for indices). Adding ρ as an off-diagonal coupling in the metric gives the leverage-corrected metric:

```
g = 1/(1-ρ²) × [e^{-2y}    -ρe^{-y}]
                [-ρe^{-y}       1    ]
```
(in dimensionless coordinates x = log-moneyness, y = log(σ/σ₀))

Direct computation gives constant scalar curvature **R = -2** everywhere, independent of (x, y, ρ). The leverage correction universalizes the curvature.

---

## Theorem 2: The smile formula

On the leverage-corrected manifold, the leading-order smile expansion is:

```
σ_impl(K,T) / σ_ATM(T) = 1 + γ·m + (κ_eff/2)·m² + O(m³)
```

where m = log(K/F) is log-moneyness, F = forward price, and:

```
γ = ρν / (2σ₀)                              (skew)
κ_eff = (2 - 3ρ²)/6 × (ν/σ₀)²              (curvature)
```

### Reading the coefficients

**Skew γ**: Proportional to ρ. For ρ < 0 (equity indices), γ < 0, giving σ_impl > σ_ATM for K < F — the standard equity skew. Linear in ρ, so relatively insensitive to ρ estimation error.

**Curvature κ_eff**: Contains a sign-flip:
- ρ²/2 term: negative (bare hyperbolic geometry contribution)
- 1/3 term: positive (pure vol-of-vol, symmetric smile)
- Net: positive when **|ρ| < √(2/3) ≈ 0.816** (smile region), negative when |ρ| > 0.816 (frown region)

### The bifurcation locus

**|ρ| = √(2/3) ≈ 0.816** is the structural separator:
- Below this (|ρ| < 0.816): **smile** — OTM calls and puts both trade above ATM
- Above this (|ρ| > 0.816): **frown** — OTM options below ATM

**Phase-plane finding**: 22 years (2004–2026) of SPY/VIX data shows a **stable attractor at (ν/σ₀, ρ*) ≈ (9.2, -0.84)**, just below the bifurcation locus. The market spends 66% of days on the formal frown side, mean-reverting to an attractor adjacent to the locus.

---

## Empirical test: SPY LEAPS, zero free parameters

All three inputs (σ₀, ν, ρ) are estimated from the realized time-series only — no options panel calibration.

**SPY parameters (April 22, 2026, 5yr window):**
```
σ₀ ≈ 0.170    (realized vol, SDHO stationary value)
ν  ≈ 1.22     (annualized log-VIX vol: √252 × std(Δlog VIX))
ρ  ≈ -0.77    (Pearson corr: daily log-SPY vs log-VIX returns)
```

**Predicted smile coefficients:**
```
γ_pred  = (-0.77)(1.22) / (2×0.170) = -2.73
κ_pred  = (2 - 3×0.77²)/6 × (1.22/0.170)² = +2.00
```

**Observed SPY LEAPS (four expiries, 1.15–2.65yr):**

| Expiry (T yr) | σ_ATM | γ_obs | κ_obs | γ_pred | κ_pred |
|---------------|-------|-------|-------|--------|--------|
| 2027-06 (1.15) | 0.193 | -2.23 | +1.06 | -2.73 | +2.00 |
| 2027-12 (1.65) | 0.201 | -2.05 | -3.13 | -2.73 | +2.00 |
| 2028-06 (2.15) | 0.199 | -2.20 | +5.70 | -2.73 | +2.00 |
| 2028-12 (2.65) | 0.201 | -2.42 | +11.62 | -2.73 | +2.00 |

**Mean observed**: γ_obs = -2.22 ± 0.16 (CoV = 7%)

**Result**: Skew prediction is **within 19%** of observed (zero free parameters). The T-independence of γ_obs across four maturities matches the theoretical prediction exactly.

**The 19% gap**: Systematic — realized ν slightly overstates options-implied ν at long horizons (variance risk premium sign reversal at long maturity). Consistent with known stylized fact.

**Curvature**: Observed κ_obs scatters widely (-3.13 to +11.62); prediction κ_pred = +2.00 falls within range but noisy (sparse LEAPS strikes make second derivative estimation difficult). Both consistent with small positive curvature near the bifurcation locus.

---

## SABR connection

The smile coefficients (5.2) are exactly those of the SABR model with β = 1 at leading order. **This is not a coincidence.** SABR β = 1 is the geodesic-distance asymptotic of the leverage-corrected manifold of constant curvature R = -2, and β = 1 is fixed by Čencov's theorem — not a phenomenological choice.

For equity indices, β = 1 is therefore a structural prediction. For rates (β ≈ 0.5) and commodities (β = 0), the framework predicts these values arise from different parametric families with different Fisher metrics.

---

## Short-maturity regime

Below ~15 days, jump contributions dominate (scale as 1/T²) and the diffusion-only formula is not the right prediction. The short-maturity skew is T-dependent:

```
Observed: γ_obs(T) = -3.87 (1yr) to -7.16 (1wk)  [T-dependent]
Theorem 2: γ_pred = -2.73  [T-independent, diffusion only]
```

**Empirical curiosity**: Fitting γ_obs(T) = γ_∞ + b/√T across five maturities gives b/σ₀ ≈ -3.165 ≈ -π (within 0.75%). Flagged as possible structural feature of the geometry; not resolved.

---

## Connection to prior work (Dean series)

The author is building a geometric theory of markets across multiple papers using the same Čencov-Fisher manifold:

| SSRN | Title | Key result |
|------|-------|------------|
| 5990674 | Scale Invariant Dynamics in Market Price Momentum | Temporal evolution as geodesic flow |
| 6380118 | Scale-Dependent Dynamics in Equity Market Phase Space | Phase space structure |
| **6565418** | **Information Geometry of Market Dynamics: Pareto Frontier from Contact Geometry** | **SDHO Pareto frontier R² = Ω²/(1+Ω²) at Ω ≈ 1.16 for liquid markets** |
| 6630259 | **This paper** — BSM as flat limit | Smile = manifold curvature |
| (in prep) | VIX as Thermodynamic Control Parameter | Phase transitions via curvature divergence at |ρ|→1 |
| Working 2026 | **Phase Space Methods for Volatility Regime Classification** | VIX-based options trading practitioner framework |

**Key structural insight**: The Gaussian Fisher manifold has two orthogonal slices:
- **Time direction**: Characterized by dissipation parameter Ω ≈ 1.16, giving R² = Ω²/(1+Ω²) — how markets evolve over time
- **Strike direction** (this paper): Characterized by leverage correlation ρ ≈ -0.77, giving the smile expansion — how the vol surface looks across strikes

Approximate algebraic duality: 1/(1-R²) = 1+Ω² ↔ 1/(1-ρ²) = 1+Ω̃²_ρ. Time-direction Ω ≈ 1.16 vs strike-direction Ω̃*_ρ ≈ 1.55 — ~30% apart, suggestive but not exact.

---

## Trading implications

### 1. LEAPS skew is T-independent (diffusion regime)
Skew in the 1–3yr range is structurally flat across maturities (confirmed empirically: CoV = 7%). This means:
- Long-dated puts priced consistently relative to shorter dates
- No roll-down benefit from term structure of skew in the LEAPS regime
- Practical: selling puts at a specific delta looks the same across LEAPS maturities — use the nearest liquid expiry

### 2. Predicting skew from time-series parameters
Three parameters from SPY + VIX time-series predict LEAPS skew within 19%:
```python
# Inputs (from time-series only, no options calibration)
sigma0 = realized_vol_sdho_stationary()  # SDHO sigma estimate
nu = np.sqrt(252 * np.var(np.diff(np.log(vix_closes))))  # vol-of-VIX
rho = np.corrcoef(np.diff(np.log(spy_closes)),
                   np.diff(np.log(vix_closes)))[0,1]  # SPY/VIX correlation

# Predicted skew and curvature (Theorem 2)
gamma = rho * nu / (2 * sigma0)
kappa_eff = (2 - 3*rho**2) / 6 * (nu / sigma0)**2

# Implied vol at strike K (forward F)
def sigma_impl(K, F, sigma_atm):
    m = np.log(K / F)
    return sigma_atm * (1 + gamma * m + kappa_eff/2 * m**2)
```

The 19% gap is systematic (variance risk premium); can be corrected by using options-implied ν (from ATM IV term structure) instead of realized ν.

### 3. Bifurcation regime indicator
When ρ is near -0.816 (which it usually is), small changes in ρ strongly affect κ_eff. This is a regime sensitivity indicator:
- ρ estimate from 5yr window: -0.77 (smile side, κ_eff = +2.00)
- ρ estimate from 60-day window: -0.84 (frown side, κ_eff < 0)
- Market spends 66% of time in frown region but near the boundary

### 4. Variance risk premium at long maturities
Realized ν (~1.22) overstates options-implied ν at long horizons — the 19% gap is evidence of negative VRP at long maturities (options cheaper than realized vol would justify). Long LEAPS puts may be systematically underpriced relative to realized vol models.

### 5. Crossover at ~15 days
Below ~15 days, jumps dominate. Regime shift: short-dated skew is T-dependent and steeper (-7.16/wk vs -2.22/yr). Strategies that depend on skew being T-independent need maturities > 30 days minimum.

---

## Prior source context

The author's working paper [19] ("Phase Space Methods for Volatility Regime Classification: A Practitioner's Framework for VIX-Based Options Trading") is a direct practitioner extension. Worth tracking down — apply the geometric regime classification to VIX-based options strategies. Not yet on SSRN but referenced as "Working Paper 2026."

---

## Mathematical foundations

The stochastic calculus foundations underlying BSM (Itô's lemma, Girsanov theorem, risk-neutral measure, path integral formulation) are covered comprehensively in:

**Phynance** — Kakushadze (arXiv:1405.1948, 2014). PhD-level lecture notes from Stony Brook theoretical physics, recasting standard financial stochastic calculus in path-integral language. Covers BSM derivation, all Greeks, short-rate models (Vasicek/CIR/HJM/BGM), and worked pre-interview quant problems. See [sources/phynance-kakushadze-2014.md](../../sources/phynance-kakushadze-2014.md).
