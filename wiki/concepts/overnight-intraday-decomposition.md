---
title: Overnight-Intraday Return Decomposition — Tail Heterogeneity and IBS Applications
description: Structural separation of daily returns into overnight and intraday components; tail parameter differences across sessions; implications for IBS mean-reversion and regime detection
tags: market-microstructure, ibs, volatility, garch, overnight-returns, intraday, tail-risk, regime-detection
added: 2026-07-30
category: Trading / Concepts
---

# Overnight-Intraday Return Decomposition

## Core Concept

Daily equity returns can be decomposed into two structurally distinct components:

- **Overnight return**: log(open_t / close_{t-1}) — price movement while the market is closed
- **Intraday return**: log(close_t / open_t) — price movement during trading hours

These two components have different statistical properties, different information-content drivers,
and — critically for trading strategy design — different tail behavior and mean-reversion dynamics.

---

## Empirical Findings — Chen, Hansen & Tong (2026)

**Source**: arXiv:2607.03669, "Split-Session Cluster GARCH for Overnight and Intraday Returns:
The Role of Tail Heterogeneity" (Chen, Hansen, Tong; Jul 2026)

### Key Results

| Property | Overnight Returns | Intraday Returns |
|-----------|-------------------|------------------|
| Average tail index (ν) | ~3.8 (heavier tails) | ~5.2 (lighter tails) |
| Information content | News accumulation during close | Order flow, market making |
| Mean-reversion tendency | Lower (more directional) | Higher (reversal-prone) |
| Tail clustering | Sector-aligned | Within-session correlated |
| VaR coverage | Heavy-tail models needed | Gaussian adequate |

The paper uses **convolution-t distributions** (sum of overnight + intraday t-distributions) with
separate tail parameters for each session, embedded in a multivariate GARCH framework (SSC-GARCH:
Split-Session Cluster GARCH). Block-structured conditional correlation matrices preserve parsimony
at scale (100-asset applications tested).

### Why Tail Heterogeneity Matters

When using end-of-day risk measures (VaR, CVaR) calibrated on total daily returns, overnight
fat tails are masked by the lighter-tailed intraday distribution. This leads to:

1. **VaR underestimation on overnight positions** — overnight news shocks (earnings, macro,
   geopolitical) generate fat-tail moves that Gaussian daily VaR misses
2. **Incorrect attribution** — "crash days" are often driven by overnight gaps, not intraday
   order flow, requiring different hedging responses
3. **Strategy filtering** — mean-reversion strategies (like IBS) that depend on intraday
   dynamics should be conditioned on the overnight regime

---

## IBS Strategy Implications

The **Internal Bar Strength (IBS)** strategy (H062–H112, 30% of production portfolio) exploits
intraday mean reversion: when `IBS = (close - low) / (high - low) < 0.2`, buy at close,
exit next day at close. This exploits the magnitude-driven bid-ask bounce (FRI mechanism from
arXiv:2606.29591).

**Hypothesis from Chen et al. (2026):** Days with large overnight return (top tail of overnight
distribution) are likely "news arrival" days. On these days:

- The stock has likely gapped open significantly
- Intraday price action is more **trend-following** (continuation of the overnight move)
  rather than mean-reverting
- IBS may find low readings not because the stock is oversold relative to the day's range,
  but because the gap-down continues intraday → false reversal signal

Conversely, days with **small overnight return** (thin tail of overnight distribution) are
"no-news" days. Intraday returns are dominated by bid-ask bounce and market-making dynamics —
exactly the regime where IBS mean-reversion works best.

### Testable Prediction (H476)

```python
# Overnight realized variance proxy
overnight_rv = (np.log(open_t / close_prev))**2

# Rolling IS-window percentile rank
overnight_rv_rank = overnight_rv.rolling(252).rank(pct=True)

# IBS entry condition with session filter
entry_condition = (ibs < 0.2) & (overnight_rv_rank < 0.8)
# Var A: gate out top 20% overnight variance days
```

Expected effect: by excluding fat-tail overnight days, the strategy concentrates on
clean intraday-reversal days where the bid-ask bounce mechanism operates reliably.

---

## Connection to FRI Decomposition

The **Fourier-Residue Identity (FRI)** from arXiv:2606.29591 (Portnaya 2026) decomposes
return autocorrelation into:

- **Sign channel** (direction): statistically insignificant for SPY (p=0.11)
- **Magnitude channel**: highly significant (p<10⁻¹²)

This confirms that equity mean-reversion is a **magnitude effect**, not a directional effect —
the bid-ask bounce mechanism operates through the size of the prior price move, not its direction.

The overnight/intraday decomposition adds a **session-level** filter to this: the magnitude
effect (bounce) is strongest in intraday returns, while overnight returns are more directional
(news-driven). Combining both insights:

- IBS entry works best when: prior |overnight return| is small (low-magnitude overnight)
  AND intraday position is extreme (IBS < 0.2 or > 0.8)
- This is the regime where pure intraday bid-ask bounce dominates

---

## Macro-Regime Interaction

The overnight/intraday distinction also interacts with macro regimes (VIX, SPY 200MA):

| Regime | Overnight tails | Intraday reversal quality |
|--------|----------------|--------------------------|
| Low VIX (< 15) | Thin, rare news shocks | High — clean reversal days |
| Moderate VIX (15-25) | Moderate | Moderate — some trend days |
| High VIX (> 25) | Fat — frequent shocks | Low — trend days dominate |

This is consistent with H444 (realized vol gate on H198) and H249 (regime-conditional weights):
volatility regimes affect strategy performance through the ratio of news-shock days to pure
market-making days.

---

## Practical Data Construction

Using yfinance daily OHLCV data (no additional cost):

```python
import yfinance as yf
import numpy as np

def session_decomposition(ticker, start, end):
    df = yf.download(ticker, start=start, end=end)
    df['overnight_ret'] = np.log(df['Open'] / df['Close'].shift(1))
    df['intraday_ret'] = np.log(df['Close'] / df['Open'])
    df['overnight_rv'] = df['overnight_ret'] ** 2
    df['intraday_rv'] = df['intraday_ret'] ** 2
    
    # Rolling tail regime indicator
    df['overnight_rv_rank'] = df['overnight_rv'].rolling(252).rank(pct=True)
    df['is_fat_tail_day'] = df['overnight_rv_rank'] > 0.80
    
    # IBS
    df['ibs'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'])
    
    # H476 filtered entry
    df['h476_entry'] = (df['ibs'] < 0.2) & ~df['is_fat_tail_day']
    return df
```

---

## Cross-References

- [IBS Mean-Reversion](../trading/algorithms/ibs-mean-reversion.md) — H062–H112 production strategy
- [FRI Decomposition — Magnitude vs Direction in Equity Mean Reversion](../trading/backtesting/fri-magnitude-mean-reversion.md) — theoretical FRI grounding
- [Market Microstructure & HFT](../trading/algorithms/market-microstructure.md) — bid-ask bounce mechanism
- [Regime Detection Signals](../trading/backtesting/regime-detection-signals.md) — VIX regime context
- H476 (staged 2026-07-30) — IBS overnight tail gate backtest

---

## References

- Chen, X., Hansen, P.R., Tong, C. (2026). "Split-Session Cluster GARCH for Overnight and Intraday
  Returns: The Role of Tail Heterogeneity." arXiv:2607.03669.
- Portnaya, G. (2026). "The Bounce Has No Direction: Sign, Magnitude, and the Microstructure of
  Equity Return Predictability." arXiv:2606.29591.
- French, K.R. & Roll, R. (1986). "Stock Return Variances: The Arrival of Information and the
  Reaction of Traders." Journal of Financial Economics, 17(1), 5-26.
  (Original evidence that overnight returns are more volatile per unit time than intraday)
