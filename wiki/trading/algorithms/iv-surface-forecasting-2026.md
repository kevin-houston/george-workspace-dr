---
updated: 2026-07-26
category: options-strategies
sources:
  - arXiv:2511.07571
  - arXiv:2603.17151
---

# Implied Volatility Surface Forecasting — 2026 Papers

Two recent papers materially advance the state of the art in IV surface modeling: one on **generative forecasting** (DDPM) and one on **compact representation** (shallow NN). Both are design bases for H448 and H449 respectively.

---

## Paper 1: Diffusion Model IV Surface Forecasting

**Citation:** Jin, C. & Agarwal, A. (2025, revised May 2026). "Forecasting implied volatility surface with generative diffusion models." arXiv:2511.07571.

**Code:** https://github.com/Austinjinc/diffusion-paper-code

### What it does
Trains a **conditional Denoising Diffusion Probabilistic Model (DDPM)** to generate arbitrage-free one-day-ahead implied volatility surfaces for SPX options. Conditioning variables:
- Exponential weighted moving averages (EWMAs) of historical IV surfaces across maturities and strikes
- Returns and squared returns of the underlying (SPY/SPX)
- Scalar risk indicators including VIX

### Key technical contribution
Historical option data frequently contains calendar or butterfly arbitrage violations. The paper introduces a **parameter-free SNR (signal-to-noise ratio) weighting scheme** that incorporates an arbitrage penalty into the DDPM loss function without needing a separate constraint optimizer.

### Empirical results
- Significantly outperforms leading GAN-based models (VolGAN, etc.) in capturing stylized facts of IV dynamics
- Conditioning on EWMAs of historical surfaces (the tractable ablation) captures ~80% of the full DDPM benefit — useful approximation for backtesting
- Evaluated on SPX index options

### Relevance to our stack
- **H448 design basis**: the VRP signal (predicted IV − realized vol) is cleaner when the IV forecast enforces no-arbitrage. Even without running the full DDPM, the EWMA-surface approximation is tractable.
- **H309 context (SPX Dispersion)**: the diffusion model could supply the implied correlation surface estimates needed for Phase 2 of H309.
- **Practical note**: requires CBOE DataShop or Polygon options data for full implementation. Var B/C of H448 use EMA approximation.

---

## Paper 2: Shallow Representation of Option Implied Information

**Citation:** Lin, J. (2026, March). "Shallow Representation of Option Implied Information." arXiv:2603.17151. Published in *q-fin.CP* (Computational Finance).

### What it does
Provides a systematic approach to build neural representations of the option-implied information embedded in the IV surface. Core insight: **a single-hidden-layer feedforward network with a specific activation is sufficient** to represent both implied density and implied volatility — deeper or wider architectures add noise rather than signal.

### Theoretical grounding
The paper revisits the explicit link between implied density and implied volatility through an alternative lens: IV is a *pointwise corrector* that maps the Black-Scholes quasi-density into the implied risk-neutral density. This framing naturally motivates shallow architectures because the corrector is low-complexity by construction.

### Key finding
Extensive experiments confirm: adding depth/width to the IV representation network **does not improve** and often degrades performance. This mirrors the general principle from the bilevel-autoresearch literature (arXiv:2603.23420): mechanism-level simplicity beats model complexity.

### Relevance to our stack
- **H449 design basis**: the shallow IV representation produces stable, low-noise implied skewness and kurtosis moments that can serve as cross-sectional equity return predictors.
- **H309 (SPX Dispersion)**: compact IV surface representation reduces data requirements for building the implied correlation surface.
- **General principle**: when building option-based features for factor models, shallow representations (rolling windows of IV moments: ATM IV, skew slope, curvature) outperform learned deep embeddings. This validates our existing approach of using VIX/VIX3M/VIX9D as IV surface proxies.

---

## Connecting to H448 and H449

| Hypothesis | Paper | Mechanism | Key variant | Gate |
|-----------|-------|-----------|-------------|------|
| H448 | arXiv:2511.07571 | DDPM-forecast IV → cleaner VRP signal for SPX | Var C: VRP + term-structure slope | OOS Sharpe ≥ 1.0, MaxDD ≤ 25% |
| H449 | arXiv:2603.17151 | Shallow IV moments as cross-section equity factor | Var C: L/S dollar-neutral quintiles on IVSKEW+IVKURT | OOS Sharpe ≥ 1.0 |

---

## Prior Related Work in Wiki

- [Volatility Risk Premium](volatility-risk-premium.md) — IV > RV ~85% of time; VRP 2–4 vol pts; short-vol Sharpe ~1.0; H266 queued
- [SPX Dispersion Trading & Variance Risk Premium](spx-dispersion-variance.md) — H309 PARTIAL; implied correlation premium 6–18pp historically
- [BSM as Flat Limit of Information Geometry](bsm-information-geometry.md) — SSRN 6630259; smile = manifold curvature; zero-free-parameter LEAPS prediction within 19%
- [Options Data Sources](../data-sources/options-data.md) — ThetaData (cheapest), ORATS (best IV surface), Polygon (real-time only)
- [Options Backtesting Methodology](../backtesting/options-backtesting-methodology.md) — path-dependency, vol surface evolution, 4-tier data pipeline

---

## Practical Implementation Notes

### Getting IV surface data without CBOE DataShop
1. **VIX family proxies** (free): `^VIX` (30d ATM), `^VIX9D` (9d ATM), `^VIX3M` (93d ATM) via yfinance — sufficient for Var A/B/C of H448
2. **Polygon options** (`$POLYGON_API_KEY`): end-of-day option chains with greeks for S&P 500 stocks — required for H449 cross-section
3. **ThetaData** ($20/mo student tier): full SPX options history — ideal for H448 full DDPM implementation
4. **ORATS** ($99/mo): best IV surface data with historical smoothed IV surface

### Arbitrage-free surface check (quick)
For any IV surface snapshot, check:
- **Calendar spread**: IV(T2) > IV(T1) for T2 > T1 at same strike (otherwise calendar arb exists)
- **Butterfly spread**: IV(K-dk) + IV(K+dk) > 2*IV(K) for any strike K (otherwise butterfly arb)
- Use `py_vollib` or `FinancePy` for fast arbitrage screening
