---
title: Trend-Following System Theory — Frequency Domain, Autocorrelation, and ARFIMA
added: 2026-07-23
category: trading/algorithms
source: arXiv:2607.19497 (Sepp & Lucic, Jul 2026)
---

# Trend-Following System Theory

## Overview

Trend-following (TF) systems — the oldest and most studied systematic strategies — have a deep theoretical structure that is often obscured by purely empirical results. Sepp & Lucic (2026) provide the most complete unified treatment, connecting three previously siloed literatures: signal processing, time-series econometrics, and portfolio construction. Understanding this theory helps explain *why* specific TF variants work and when they will fail.

## Taxonomy of Trend-Following Systems

Sepp & Lucic classify TF into three families:

### 1. European TF (Signal-Based)

A signal $s_t$ is computed from historical prices and position is proportional to $s_t$. The P&L of a European TF system is:

$$\text{PnL}_t = s_t \cdot r_{t+1}$$

**Key identity** (Sepp & Lucic 2026, Theorem 1): The expected return of any European TF equals:

$$E[\text{PnL}] = \text{Cov}(s_t, r_{t+1}) = \sum_{k \geq 1} w_k \cdot \text{Autocorr}(r_t, r_{t-k}) \cdot \text{Var}(r)$$

where $w_k$ are the signal's lag weights. **Implication**: a European TF system is profitable if and only if the weighted sum of lagged autocorrelations (at the signal's lookback frequencies) is positive. This is the theoretical justification for TSMOM (H220) and H261b.

### 2. American TF (Threshold-Based)

Position is $\pm 1$ (binary), flipping when a threshold is crossed. Profitability requires positive *drift* in volatility-normalized returns, not just autocorrelation. This is the classic "trend" rule.

### 3. Time Series Momentum (TSMOM)

Position sized proportional to the past return (signed). This is the academically standard formulation (Moskowitz et al. 2012). H220 confirmed this on H026 ETF universe (OOS Sharpe 0.961).

## The Frequency Domain View

Any TF signal can be analyzed through its frequency response $H(f)$. The expected return in frequency domain is:

$$E[\text{PnL}] = \int H(f) \cdot S_{rr}(f) \, df$$

where $S_{rr}(f)$ is the spectral density of returns. This is the **Poisson-kernel reading** of the return spectrum:

- **A system profits at zero drift when the kernel aligns with spectral mass at positive frequencies** (persistent trends)
- **A system loses when spectral mass concentrates at negative frequencies** (mean-reverting regimes)

### Practical implication for our strategies

The multi-memory factor model (H411, arXiv:2607.03858) identifies 5 spectral components of US equity returns:
- F1: 4-year persistent autocorrelation → captured by slow TSMOM signals
- F2: 6-18 month antipersistent → captured by skip-month (reduces mean-reversion drag)
- F3: 1-6 month momentum → H198 formation window
- F4: 1-4 week short reversal → IBS daily mean-reversion
- F5: Noise

Different TF systems **spectrally filter** for different components. H198's 6-1m formation window picks up F3; IBS picks up F4. The frequency domain explains why mixing windows (e.g., H395 4-signal composite) improves Sharpe: each signal targets a different spectral band.

## ARFIMA Processes and Long-Memory

Sepp & Lucic show TF profitability is tractable under fractional ARFIMA(p, d, q) processes:

$$\Delta^d r_t = \phi(L) r_t + \theta(L) \varepsilon_t$$

where $d \in (-0.5, 0.5)$ is the fractional integration order:
- $d > 0$: long-memory, persistent (positive autocorrelation at all lags) → TF profitable
- $d < 0$: antipersistent, mean-reverting (negative autocorrelation) → TF loses, reversal profitable
- $d = 0$: I(0), no long-memory → TF breaks even on expectation

**Key result**: Under ARFIMA(0, d, 0), a TF system with equal lag weights $w_k = 1/K$ earns expected return proportional to $d \cdot \ln(K)$, increasing logarithmically with lookback window. This explains why H261b (commodity CTA) benefits from longer formation periods than equity momentum strategies.

## Short-Term Mean Reversion Coexisting with Long-Term Trend

The most counterintuitive result (Sepp & Lucic 2026, Section 3): **a TF system can be profitable even in the presence of short-term mean reversion**, provided the *long-term* autocorrelation is positive. The Poisson kernel ensures the long-run spectral mass (F1, F3) dominates the short-run reversal (F4) in the profitability formula.

This theoretically justifies:
- H198's 1-month skip (excludes reversal noise, keeps momentum signal)
- H376's no-skip 6-0m discovery: the 1-month reversal in NASDAQ-heavy universe is smaller than the continued momentum, so skip-month is net-negative (confirmed OOS 3.120 no-skip vs 1.174 with skip)
- IBS mean-reversion (H112): profits from F4 at daily frequency, orthogonal to momentum

## Transaction Costs and the Signal-to-Noise Ratio

The break-even transaction cost threshold for a TF system is:

$$\bar{c} = \frac{E[\text{PnL}]}{\text{Turnover}}$$

For monthly-rebalance strategies (H198, H026, H045): turnover ~ 1-2 ETF/month → costs are manageable. For daily IBS (H112): high turnover but large per-trade edge from the F4 spectral band.

**Conclusion for production**: the spectral model predicts all three production families (momentum, IBS, bond rotation) are complementary because they target different return spectrum components. This is the theoretical grounding for why the H041a/H026/H045/IBS blend achieves OOS Sharpe 4.158 with MaxDD -3.6%.

## Regime Shifts and Spectral Non-Stationarity

The spectral density $S_{rr}(f)$ is **not constant over time**. During rate-hike cycles (2022), the low-frequency spectral mass (F1, F2) shifts — long-term bonds become mean-reverting instead of trending. This explains:
- H045 bond rotation OOS degradation in 2017-2026 vs H045's canonical split (includes 2022 rate shock)
- H355 OB filter on H045: routes to SHY when OBs don't form, which is a frequency-domain regime detector

## Relevance to H429 (Text-Enhanced Regime Detection)

If central-bank hawkish language shifts the long-run spectral mass of Treasury returns from positive (F1 persistent) to negative (F2 antipersistent), then text detection of this regime shift should precede the price signal by the LLM's "information advantage" period (~2-4 weeks per arXiv:2605.30363). This is the theoretical justification for H429.

## References

- Sepp, A. & Lucic, V. (2026). "The Science and Practice of Trend-Following Systems." arXiv:2607.19497
- Frøseth, M. (2026). "Multi-Memory Factor Model of US Equity Returns." arXiv:2607.03858 → [wiki page](../backtesting/multi-memory-factor-model-equity.md)
- Moskowitz, T.J., Ooi, Y.H. & Pedersen, L.H. (2012). "Time series momentum." JFE 104(2):228-250
- Portnaya, A. (2026). "The Bounce Has No Direction." arXiv:2606.29591 → [wiki page](../backtesting/fri-magnitude-mean-reversion.md)

## Cross-References

- [Multi-Memory Factor Model](../backtesting/multi-memory-factor-model-equity.md) — spectral decomposition of US equity returns
- [IBS Mean-Reversion](ibs-mean-reversion.md) — F4 daily reversal spectrum
- [Momentum Strategies](momentum-strategies.md) — F3 momentum spectrum
- [FRI Decomposition](../backtesting/fri-magnitude-mean-reversion.md) — sign vs magnitude channels
- [Signal Half-Life](../backtesting/signal-halflife.md) — alpha decay and TF windows
- [Commodity Trend Following](commodity-trend-following.md) — H261b long-lookback validation
