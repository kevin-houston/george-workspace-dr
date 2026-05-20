---
updated: 2026-05-20
type: lecture-notes
source: arxiv-1405.1948.pdf
author: Zura Kakushadze
arxiv: 1405.1948
date: May 2014 (v2 March 2015)
pages: ~120
---

# Phynance — Kakushadze (2014)

**Full title**: "Phynance"  
**Author**: Zura Kakushadze (Quantigic Solutions LLC; University of Connecticut)  
**arXiv**: https://arxiv.org/abs/1405.1948  
**Origin**: Lecture notes for an advanced Ph.D. course at C.N. Yang Institute for Theoretical Physics, Stony Brook (Spring 2002). Dedicated to the author's father.

---

## What it is

A complete graduate-level treatment of stochastic calculus and derivative pricing, written for physicists. The "phynance" framing uses path integrals (the language of quantum field theory) to reformulate standard financial stochastic calculus, making the mathematics immediately legible to anyone with a physics background. Also includes pre-interview quant questions (2 quizzes with full solutions).

The primary text reference is Baxter & Rennie, *Financial Calculus: An Introduction to Derivative Pricing* (Cambridge, 1996).

---

## Coverage by section

### Foundations
- **Bookmaker / arbitrage pricing** — how a bookie guarantees profit via implied probability inflation; direct analogy to no-arbitrage pricing in finance
- **Bid-ask spread** — market-making, half-spread cost, locked/crossed markets
- **Stocks, bonds, free markets** — why demand exists for each; yield/price inverse relationship; credit risk hierarchy (Treasuries < munis < corporate)
- **Arbitrage pricing** — one-price principle, no-riskless-free-lunch, replication

### Stochastic calculus
- **Binomial tree** — risk-neutral measure construction; example: Baseball World Series
- **Martingales** — Tower Law, martingale measure, Binomial Representation Theorem, self-financing hedging strategies
- **Brownian motion** — discrete vs. continuous limit; quadratic variation
- **Itô calculus** — Itô's formula, Itô's lemma, stochastic differential equations
- **Radon-Nikodym process** — change of probability measure
- **Path integral formulation** — stochastic integral recast as Wiener path integral (physicist-native language); exact equivalence to Itô calculus
- **Cameron-Martin-Girsanov theorem** — change of drift via change of measure; how risk-neutral pricing works mathematically

### Continuous martingales and hedging
- Driftlessness condition; Martingale Representation Theorem
- Change of measure in general one-stock model; terminal value pricing; heat kernel method

### Options
- European call, put, binary option definitions
- **Black-Scholes model** — full derivation via risk-neutral measure; closed-form for call/put/binary
- BSM Greeks: Delta, Gamma, Theta, Vega, Rho — explicit formulas and economic interpretation
- American options; early exercise; upper/lower bounds
- Equities with dividends (continuous and periodic)

### Multi-asset and interest rates
- Multiple stock models; completeness; arbitrage-free conditions
- Numeraires; change of numeraire technique
- Foreign exchange models
- **Interest rate market**:
  - Heath-Jarrow-Morton (HJM) framework — forward rate dynamics
  - Multi-factor HJM
- **Short-rate models**:
  - Ho-Lee model
  - Vasicek / Hull-White model
  - Cox-Ingersoll-Ross (CIR) model
  - Black-Karasinski model
- Interest rate products: forward measures, coupon bonds, floating rate bonds, swaps, bond options (Vasicek), caps/floors, swaptions
- **BGM (Brace-Gatarek-Musiela) / LIBOR Market Model** — log-normal forward LIBOR dynamics
- Foreign currency interest rate models; quantos; forward quanto contracts
- **Optimal hedge ratio** — minimum variance hedge derivation

### Quiz problems (Appendices B & C)
Two full quizzes with solutions covering: no-arbitrage arguments, binomial tree pricing, put-call parity, Black-Scholes application, yield/price relationships, delta hedging mechanics. Pre-interview questions from circa 2002 bulge-bracket quant desks.

---

## Key formulas

**Itô's lemma** (core of all derivative pricing):
```
df(t, S) = (∂f/∂t + μS ∂f/∂S + ½σ²S² ∂²f/∂S²) dt + σS ∂f/∂S dW
```

**Black-Scholes PDE**:
```
∂V/∂t + rS ∂V/∂S + ½σ²S² ∂²V/∂S² - rV = 0
```

**Black-Scholes call price**:
```
C = S·N(d₁) - K·e^{-rT}·N(d₂)
d₁ = [ln(S/K) + (r + σ²/2)T] / (σ√T)
d₂ = d₁ - σ√T
```

**Girsanov**: Under risk-neutral measure Q, Brownian motion gains a drift correction:
```
dW̃ = dW + (μ - r)/σ · dt
```

**Path integral formulation**:
```
V(t, S) = e^{-r(T-t)} · E_Q[payoff(S_T)]
        = ∫ payoff(S_T) · K(S, t; S_T, T) dS_T
```
where K is the log-normal Green's function (heat kernel in physics language).

---

## Why relevant to Kevin's project

| Topic | Connection |
|-------|-----------|
| BSM derivation + Greeks | Foundation for `bsm-information-geometry.md` (Dean 2026 builds on this) |
| Risk-neutral pricing | Used implicitly in H162 options income (CSP/wheel; iron condor) |
| Optimal hedge ratio | Relevant to any delta-hedged options position |
| Path integral framing | Connects to Dean 2026 information geometry — both use differential geometry language |
| Short-rate models (Vasicek, CIR) | Background for interest rate risk in TLT/IEF pairs (H154); BIL preference rationale |
| Quiz problems | Useful for interview prep / quant reasoning practice |

---

## Relationship to other wiki pages

- [BSM & Information Geometry](../trading/algorithms/bsm-information-geometry.md) — Dean 2026 works in the curved-space generalization; Phynance covers the flat-BSM foundations that Dean extends
- [Options Income Strategies](../trading/algorithms/options-income-strategies.md) — BSM Greeks (Delta, Vega, Theta) are the operational language for H162
- [Options Data Sources](../trading/data-sources/options-data.md) — vollib/py_vollib implement the formulas derived here

---

## Note on the author

Zura Kakushadze is a physicist-turned-quant known for a large body of practical quant finance papers (Quantigic Solutions). His other widely cited work includes papers on statistical risk models, alpha factors, and machine learning in finance. The "Phynance" name is his portmanteau of physics + finance, reflecting the path-integral reformulation.
