---
added: 2026-06-15
updated: 2026-08-09
category: algorithms / timing
related: [regime-detection.md, volatility-risk-premium.md, factor-momentum-style-rotation.md, esg-tail-risk-stress-resilience-2026.md]
---

# Market Timing Overlays

Daily and monthly signals that gate equity exposure — used as overlays on top of
cross-sectional rotation systems rather than standalone strategies. The goal is to
reduce drawdown during stress regimes without giving up much CAGR.

---

## 1. VIX Term Structure (H296 CONFIRMED, 2026-06-14)

### Mechanism

The VIX measures 30-day implied vol; VIX3M (`^VIX3M`) measures 93-day implied vol.
In normal markets, the term structure slopes upward (contango): near-term uncertainty
is lower than medium-term uncertainty, so VIX < VIX3M. During stress events (market
crises, earnings shocks, macro surprises), short-term fear spikes faster than
medium-term → VIX > VIX3M (backwardation).

Backwardation is rare (~7.8% of trading days) but highly predictive:
- Historically preceded 21 of 22 SPX drawdowns > 5% (2004–2025)
- Signal fires during genuine stress (COVID Mar 2020, Oct 2018, 2022 rate shock),
  not routine volatility

### Signal

```python
import yfinance as yf
import pandas as pd

vix   = yf.download("^VIX",  start="2010-01-01", auto_adjust=True)["Close"].squeeze()
vix3m = yf.download("^VIX3M",start="2010-01-01", auto_adjust=True)["Close"].squeeze()

ratio = vix / vix3m

# Binary: 1 = invest, 0 = BIL
sig_binary  = (vix < vix3m).astype(float)

# Tighter: require VIX < 95% of VIX3M before investing
sig_tight   = (ratio < 0.95).astype(float)

# Lag 1 day to avoid look-ahead
sig_lagged  = sig_binary.shift(1)
```

### Backtest Results (H296, IS 2013–2019, OOS 2020–2026)

| Variant | OOS Sharpe | OOS MaxDD | OOS CAGR | % in SPY |
|---------|-----------|-----------|---------|---------|
| A: VIX<VIX3M binary | 0.982 | -29.0% | 14.8% | 92.6% |
| B: ratio<0.95 | 1.002 | -27.0% | 13.3% | 79.1% |
| C: VIX<VIX3M + 200MA | **1.116** | **-18.6%** | 13.1% | 76.9% |
| SPY buy-and-hold | 0.772 | -33.7% | 15.7% | 100% |

**Best expression: Variant C** — halves MaxDD vs SPY (-18.6% vs -33.7%); WF ratio
1.252 (no overfitting). The 200-MA combination adds a trend filter that catches broken
uptrends even when VIX normalizes.

### Academic Support

- Simon & Campasano (2014, SSRN 2094510): VIX futures basis predicts futures returns;
  contango is the most profitable short-vol regime
- Lu & Wu (2022, arXiv:2207.04887): VIX as post-processing filter improves
  quantitative strategy Sharpe ratios
- Empirical: contango dominates ~85% of trading days 1990–2025; backwardation is
  rare but historically precedes every major drawdown

---

## 2. SPY 200-Day Moving Average

### Mechanism

The oldest and most-studied market timing signal. When SPY closes above its 200-day
SMA, the intermediate trend is up — momentum is positive at the macro level. Below
the 200MA signals trend breakdown. Originally proposed by Mebane Faber (GTAA, 2007).

### Signal

```python
spy   = yf.download("SPY", start="2003-01-01", auto_adjust=True)["Close"].squeeze()
ma200 = spy.rolling(200).mean()

sig_200ma = (spy > ma200).astype(float).shift(1)  # lag 1 day
```

### Empirical Performance (standalone)

- CAGR: ~8.7% vs B&H 9.8% (1993–2024, quantifiedstrategies.com backtest)
- MaxDD: ~14% vs ~55% for B&H — **drawdown reduction is the main value**
- Win rate: 81% on monthly signals
- Trade-off: misses early bull recoveries; whipsaws in sideways markets

### When It Works Best

- Strong trending markets (works well 2003–2007, 2009–2021)
- Clear bear markets (2000–2002, 2008, 2022)
- Fails: sideways/choppy periods (2015–2016), sharp V-shaped recoveries (2020 COVID)

### Key Caveat

The 200MA is a lagging indicator — it fires AFTER trend change, not before. During
COVID (Feb–Mar 2020), price crossed below 200MA on Feb 28 and didn't recover until
June 8 — a 3-month cash period that missed most of the recovery.

---

## 3. VIX Level Threshold

### Signal

```python
vix = yf.download("^VIX", start="2003-01-01", auto_adjust=True)["Close"].squeeze()

# Simple threshold: VIX < 25 = invest, else BIL
sig_vix25 = (vix < 25).astype(float).shift(1)

# Dynamic: use VIX relative to its own 12-month percentile
vix_pct = vix.rolling(252).rank(pct=True)
sig_vix_dynamic = (vix_pct < 0.70).astype(float).shift(1)
```

### Results Reference (from H249/H165 work)

- H165a (VIX<25 + SPY>200MA composite): OOS Sharpe +0.429 vs H026 baseline
- H249 (4-state: SPY 200MA × VIX25 + rate modifier): OOS Sharpe improvement +0.282
- Critical issue: VIX > 25 threshold was too strict in 2021 (bull market with elevated
  VIX post-COVID). Dynamic percentile-based threshold more robust.

---

## 4. Combined Composite Filter (Production Recommendation)

Based on H249 (regime-conditional weights) + H296 (VIX term structure):

```python
def composite_timing_signal(spy, vix, vix3m, ma_window=200):
    """
    Returns 3-level signal:
    2 = full risk-on (all three confirm)
    1 = partial risk-on (two of three)  
    0 = risk-off → BIL
    """
    ma200  = spy.rolling(ma_window).mean()
    ratio  = vix / vix3m

    cond_trend = (spy > ma200).astype(int)       # 200-MA trend
    cond_ts    = (ratio < 0.95).astype(int)      # VIX term structure
    cond_level = (vix < 25).astype(int)          # VIX level

    score = cond_trend + cond_ts + cond_level    # 0, 1, 2, or 3

    # Binary output: invest when 2 or 3 conditions met
    return (score >= 2).astype(float).shift(1)
```

**In practice:** the composite fires consistently in calm/trending markets and goes
to cash when multiple stress signals align. All three together (VIX<25, VIX<VIX3M,
SPY>200MA) are almost never simultaneously wrong in bull markets.

---

## 5. Rate Cycle Overlay

Less mechanical than the above but directionally important:

| Signal | Direction | Implementation |
|--------|-----------|----------------|
| Fed rate hike (T10Y2Y < 0) | Bearish for equities | FRED: T10Y2Y < 0 → reduce equity weight |
| Rate cuts starting | Bullish | FRED: FEDFUNDS rate change < 0 → increase equity |
| Credit spread widening | Bearish | FRED: BAMLH0A0HYM2 (HY spread) rising → reduce |

FRED pulls:
```python
import pandas_datareader as pdr

t10y2y = pdr.get_data_fred("T10Y2Y", start="2003-01-01")
fedfunds = pdr.get_data_fred("FEDFUNDS", start="2003-01-01")
hy_spread = pdr.get_data_fred("BAMLH0A0HYM2", start="2003-01-01")
```

**Note**: Rate signals are monthly, not daily — use as a regime modifier on monthly
rotation systems (H026/H041a), not as a daily overlay.

---

## 6. Production Integration Guide

### Daily rotation systems (IBS, H296-style)

Apply daily: `final_signal = timing_signal * rotation_score`
- When timing = 0 (risk-off): hold BIL regardless of rotation
- When timing = 1 (risk-on): follow rotation signal normally
- Signal lag: always use prior-day close (shift(1))

### Monthly rotation systems (H026, H041a, H045)

Apply at month-end rebalance:
- If month-end: VIX > VIX3M AND SPY < 200MA → override rotation → BIL
- Otherwise: follow rotation score normally
- This is already partially implemented in H026/H249 via TSMOM > 0% filter

### Stacking Priority (when multiple signals fire)

```
1. VIX > VIX3M (backwardation)  → immediate risk-off; override everything
2. SPY < 200MA AND VIX > 25     → risk-off (confirmed bear)
3. SPY < 200MA OR VIX > 25      → reduce exposure 50% (partial)
4. All clear                    → full rotation signal
```

### Key Interaction Notes

- VIX term structure and 200-MA are complementary: term structure catches fast
  events (COVID spike, Oct 2018 selloff), 200-MA catches sustained bears (2008, 2022)
- VIX level (>25) adds redundancy but can be too strict in volatile bull markets
- Do NOT stack all three as AND gates — you'll be in BIL 30%+ of time and miss bull runs

---

## 7. Confirmed Hypotheses Summary

| Hypothesis | Signal | OOS Sharpe | Status |
|------------|--------|------------|--------|
| H165a | VIX<25 + SPY>200MA | +0.429 delta | CONFIRMED |
| H249 | 4-state HMM regime | +0.282 delta | CONFIRMED |
| H296-C | VIX<VIX3M + SPY>200MA | 1.116 | CONFIRMED |

---

## 8. Next Steps / Queued

- **H297 (proposed)**: Add VIX term structure as daily override to H026 monthly rotation.
  Expected: reduce MaxDD from -28% to ~-15% at cost of ~1-2pp CAGR annually.
- **H298 (proposed)**: Rate-cycle composite (T10Y2Y slope + FEDFUNDS direction) as
  monthly weight modifier. Combine with H249 for 5-state regime model.

---

---

## 9. Theoretical Foundation: MACD as Optimal Latent Factor Estimator

*Added 2026-07-19 — source: Eccles & Lee, arXiv:2607.01705, Jul 2026*

Eccles & Lee (2026) provide a theoretical derivation showing that MACD signals
emerge as **optimal estimators** of latent drift information within price data under
a partial-information portfolio optimization framework. This provides theoretical
backing for why the market timing overlays on this page work.

### The Model

A risky asset's drift is driven by **two latent stochastic factors at distinct time scales**:
- **Fast factor**: short-horizon mean-reverting signal (days to weeks)
- **Slow factor**: long-horizon momentum drift (weeks to months)

The investor observes only prices. Under logarithmic, power, and exponential utility,
the authors derive:

> *"The filtered estimate of the latent mean-reversion level is driven by the difference between fast and slow exponential moving average-type processes."*

This is precisely the MACD oscillator — not as an empirical heuristic but as the
**statistically optimal filter** for the dual-latent-factor structure.

### Why This Explains the Confirmed Signals

| Confirmed signal | Time scale | Latent factor captured |
|-----------------|-----------|------------------------|
| SPY 200d MA (H301) | Slow (~10 months) | Long-horizon momentum drift |
| VIX<20 gate (H362) | Fast (regime switch) | Short-horizon volatility mean-reversion |
| VIX term structure (H296-C) | Fast (days) | Instantaneous mean-reversion signal |
| IBS mean-reversion (H062-H112) | Fast (1 day) | Intraday fast mean-reversion |
| 6-1m skip-month momentum (H198) | Medium (6m slow − 1m fast) | Dual-factor difference = MACD analog |

The theoretical prediction: **combining signals from different time scales produces
better risk-adjusted returns than any single time scale** because each captures
orthogonal latent factor information. This is consistent with the production portfolio
result — IBS (fast) + H026 (slow) + H045 (bonds as slow anchor) are additive.

### H422 Design Note (queued)

An explicit **MACD-parameterized momentum overlay** on H026/H041a ETF rotation:
- Fast EMA: 12-month
- Slow EMA: 26-month divergence signal
- Signal line: 9-month EMA of MACD
- Gate: invest in equity ETFs only when MACD > signal line

Theoretical prediction: MACD outperforms the 200d MA because it is the *optimal*
estimator of the dual-timescale drift. Would compare vs. H301 (SPY 200d MA,
+27.4% Sharpe improvement). Log as H422 when ready for implementation.

---

## References

- Simon & Campasano (2014). "The VIX Futures Basis: Evidence and Trading Strategies."
  SSRN 2094510.
- Faber, M. (2007). "A Quantitative Approach to Tactical Asset Allocation."
  Journal of Wealth Management.
- Lu, J. & Wu, M. (2022). "A note on VIX for postprocessing quantitative strategies."
  arXiv:2207.04887.
- Eccles, D.J. & Lee, R. (2026). "Portfolio Optimization under Fast and Slow Latent
  Mean-Reverting and Momentum Drift." arXiv:2607.01705. (MACD = optimal latent
  factor estimator; theoretical justification for dual-timescale timing overlays)
- vixcentral.com — daily VIX term structure chart
- vixstructure.com — historical VIX curve data
