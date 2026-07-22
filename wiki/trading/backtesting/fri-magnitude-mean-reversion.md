---
title: FRI Decomposition — Magnitude vs Direction in Equity Mean Reversion
added: 2026-07-22
updated: 2026-07-22
category: backtesting
source: arXiv:2606.29591 (Portnaya, Jun 2026)
---

# FRI Decomposition: Magnitude vs Direction in Equity Mean Reversion

## Overview

Victoria Portnaya (arXiv:2606.29591, Jun 2026) introduces the **Fourier-Residue Identity (FRI)**, a decomposition of return autocorrelation into two independently testable channels:

- **Sign (direction) channel**: does the direction of today's return predict tomorrow's direction?
- **Magnitude channel**: does the size of today's return predict tomorrow's size (regardless of direction)?

Applied to 33 years of daily US equity data (SPY, QQQ, IWM, AAPL, MSFT, GLD) and a 21-instrument cross-asset panel (1993–2026), the paper finds a decisive result:

> **SPY lag-1 autocorrelation is driven entirely by the magnitude channel.** The sign channel has p = 0.11 (not significant). The magnitude channel has p < 10⁻¹².

This means: **A large return yesterday predicts a smaller return today regardless of direction.** Prices do not systematically flip signs — they systematically shrink in amplitude.

---

## The FRI Framework

### Construction

For a return series r_t, define:

- **Circular mean** of |lag-k autocorrelation|: measures the k-th harmonic of the autocorrelation function
- **k=2 harmonic** = sign autocorrelation (directional flip)  
- **k=4 harmonic** = magnitude autocorrelation (size shrinkage)

The **Fourier-Residue Identity** decomposes the lag-1 autocorrelation ρ₁ into:

    ρ₁ = sign_component + magnitude_component + residual

These components are each independently testable via their own null distributions, unlike the full autocorrelation test that conflates both effects.

### Key Empirical Results (SPY 1993–2026)

| Test | Statistic | p-value | Conclusion |
|------|-----------|---------|------------|
| Full lag-1 autocorrelation (ρ₁ = -0.081) | -7.4 σ | < 10⁻¹² | Highly significant |
| Sign channel (k=2) | 1.6 σ | 0.11 | NOT significant |
| Magnitude channel (k=4) | >8 σ | < 10⁻¹² | Highly significant |

The SPY lag-1 autocorrelation of -0.081 is entirely explained by magnitude compression, not directional reversal.

### Cross-Asset Findings

Mean reversion (magnitude-driven) is present in:
- US exchange-traded equities (SPY, QQQ, IWM, AAPL, MSFT)
- Sovereign bonds (TLT analog)
- Gold (GLD)

Mean reversion is **absent** from:
- Credit ETFs (HYG, LQD) — indistinguishable from random walks
- Commodities (DBC) — random walk
- FX — random walk
- Crypto (BTC) — random walk

**Theoretical interpretation:** Magnitude-driven autocorrelation is the fingerprint of bid-ask bounce and non-synchronous constituent trading in diversified instruments. It is a market microstructure artifact, not an information effect.

---

## Implications for the George Trading Pipeline

### 1. IBS Mean-Reversion Validation (H062–H112)

The IBS signal captures magnitude: `IBS = (Close - Low) / (High - Low)`. A low IBS day (close near the low) implies:
1. A large intraday range (high magnitude)
2. Close skewed toward the extreme (directional stress)

FRI says mean reversion is driven by magnitude → **IBS is implicitly filtering for high-magnitude days**, which is precisely where FRI says the bounce effect is strongest. This provides theoretical grounding for why IBS works on XLK/SMH/IGV.

**H428 extension**: Add an explicit prior-day magnitude filter (`|prior_return| > threshold`) to IBS entries, concentrating the strategy on days where the FRI effect is strongest.

### 2. Design Principle: Magnitude Filters Improve Mean-Reversion Strategies

Any mean-reversion strategy should be stronger conditioned on large prior moves. When designing reversals, test the magnitude-conditional version:

```python
# Standard reversal: buy when 1m return < -threshold
signal = monthly_return < -0.03

# FRI-improved reversal: same filter but also require magnitude
# (prior day or prior week return was large)
signal = (monthly_return < -0.03) & (abs_prior_return > prior_mag_threshold)
```

### 3. Signal Decay Rate Insight

FRI shows that mean reversion at lag-2, lag-3 etc. is essentially noise (both sign and magnitude channels lose significance). This supports:
- IBS as a **1-day** hold strategy (not 2-day or weekly)
- H181 industry reversal as a **1-month** hold (not multi-month)
- Discrediting "extended reversal" hypotheses

### 4. Where to NOT apply mean-reversion logic

Credit ETFs (HYG, LQD), commodities, crypto are all random walks in the FRI framework. Mean-reversion IBS strategies on these instruments would not have the same FRI foundation. This explains why H045 bond ETFs require a **momentum** (not reversal) signal.

### 5. IBS in Production (XLK/SMH/IGV — 30% production portfolio weight)

The FRI result retroactively validates the design choice to deploy IBS only on **liquid exchange-traded equity sector ETFs** (XLK/SMH/IGV). These instruments display the bid-ask bounce / non-synchronous trading signature that FRI identifies as the mechanism. Bond ETFs (HYG, LQD) and commodities do not.

---

## Backtesting Implication: Avoid Directional Reversal Framing

A common framing for mean-reversion strategies is: "stocks that went down reverse up." FRI shows this framing is incorrect — it's "stocks that had large moves have smaller moves next day." For strategy testing:

- **Correct framing**: test whether large-magnitude down days are followed by smaller moves (profit from magnitude compression)
- **Misleading framing**: test whether negative days are followed by positive days (conflates sign and magnitude effects; inflates apparent edge)
- **Testing protocol**: run the FRI sign and magnitude tests separately using circular mean statistics; do not rely on standard autocorrelation alone

---

## Comparison to Multi-Memory Factor Model (Frøseth 2026)

Both papers operate on return autocorrelation structure but at different timescales:

| Paper | Frøseth arXiv:2607.03858 | Portnaya arXiv:2606.29591 |
|-------|--------------------------|--------------------------|
| Timescale | Spectral (all frequencies) | Lag-1 daily |
| Decomposition | 5 memory factors (F1-F5) | Sign vs magnitude (k=2 vs k=4) |
| Key finding | 5 regime-periods since 1963 | Magnitude-only (no directional flip) |
| Relevant to | H198 window choices, IBS hold periods | IBS entry filtering (H428) |
| Related wiki | [Multi-Memory Factor Model](multi-memory-factor-model-equity.md) | This page |

Frøseth's F5 factor (short-reversal, 1–4 week) is consistent with Portnaya's finding: the reversal is magnitude-driven (big moves shrink) not directional (down days flip up).

---

## Implementation Notes for H428

```python
# FRI-grounded IBS entry filter
def fri_ibs_entry(close, high, low, ibs_threshold=0.2, mag_threshold=0.015):
    """
    Enter IBS mean-reversion trade only on high-magnitude prior-day moves.
    Grounded in Portnaya (2026): magnitude drives mean reversion, not sign.
    
    ibs_threshold: standard IBS signal (0.2 recommended from H062-H112)
    mag_threshold: prior day |return| threshold (FRI strength condition)
    """
    ibs = (close - low) / (high - low + 1e-8)
    prior_abs_return = (close / close.shift(1) - 1).abs().shift(1)
    
    # Both conditions required: IBS signal + magnitude condition
    entry = (ibs < ibs_threshold) & (prior_abs_return > mag_threshold)
    return entry
```

Key parameters to test in H428:
- `mag_threshold`: 1.0%, 1.5%, 2.0% (Var A, B, C)
- `ibs_threshold`: 0.2, 0.3 (standard vs relaxed)
- IS-calibrated percentile (60th–70th percentile of |return| distribution)

---

## Related Pages

- [IBS Mean-Reversion](../algorithms/ibs-mean-reversion.md) — H062-H112 confirmed production deployment
- [Market Microstructure & HFT](../algorithms/market-microstructure.md) — FRI mechanism connects to bid-ask bounce theory
- [Multi-Memory Factor Model](multi-memory-factor-model-equity.md) — Frøseth spectral decomposition (same timescale family)
- [Signal Half-Life & Alpha Decay](signal-halflife.md) — FRI shows lag-1 is where the effect lives; lag-2 is noise
- [H428 stub](../../backtesting/daily/run_h428_fri_ibs.py) — proposed test of magnitude-filtered IBS
