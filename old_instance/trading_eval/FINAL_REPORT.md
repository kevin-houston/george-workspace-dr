# Autoresearch Trading Eval — Final Synthesis Report
**Fortune 100 × 10 Rounds × 146 Strategies**
Generated: 2026-03-28

---

## Overview

10 rounds of Karpathy-style autoresearch completed.
- *Tickers*: 87 Fortune 100 companies (WBA delisted, excluded)
- *Period*: 2011-03-02 → 2026-03-28 (15 years)
- *Final strategy count*: 146 strategies × 3 position types = 438 combinations
- *Backtests per round*: 38,544 (R6-R10); cumulative across all rounds: ~285,000+
- *Convergence*: Rankings stabilised at Round 7; Rounds 8-10 produced identical Top 20

---

## Autoresearch Progression

| Round | Strategies | Backtests | B&H Beat Rate | Key Addition |
|-------|-----------|-----------|----------------|--------------|
| 1 | 19 | 4,959 | 3.0% | Baseline: momentum, MR, trend, breakout, vol, ML |
| 2 | 33 | 9,768 | 3.6% | MACD, VWAP, Adaptive Momentum |
| 3 | 47 | 14,256 | 4.0% | MACD sweep, LV fine-tune, combo strategies |
| 4 | 74 | 19,536 | 4.2% | LV ultra-fine (52-58), MACD deep sweep, LV55 gate, triple combos |
| 5 | 96 | 25,344 | 4.3% | Vol-adj momentum, DualMomentum, MACD 5/11 area |
| 6 | 146 | 38,544 | 4.1% | MACD grid, DualVolAdjMom, MACDLVGate, ATR breakout |
| 7-10 | 146 | 38,544 | 4.1% | PMO, TrendConsistency, voting ensemble — *converged* |

---

## Final Strategy Family Ranking

| Family | Avg Return | Max | Notes |
|--------|-----------|-----|-------|
| volatility | 159.4% | 26,022% | LV_55 short dominant |
| momentum | 137.6% | 18,268% | PM_1_0, vam_21_5 tied #2 |
| trend | 136.1% | 12,389% | MA crossovers & MACD |
| combo | 88.7% | 8,518% | Filters hurt more than help |
| breakout | 58.8% | 9,284% | ATR breakout surprise |
| mean_reversion | 58.6% | 8,648% | VWAP short on TSLA |
| ml | 40.1% | 629% | KNN underperformed |

---

## Top 10 Confirmed Strategies (avg return across all tickers, best position type)

| Rank | Strategy | Type | Family | Avg% | Max% | Sharpe |
|------|----------|------|--------|------|------|--------|
| 1 | LV_55 | short | volatility | 468% | 26,022% | 1.07 |
| 2 | PM_1_0 | long | momentum | 444% | 18,268% | 1.06 |
| 3 | vam_21_5 | long | momentum | 444% | 18,268% | 1.06 |
| 4 | vol_adj_mom_126 | long | momentum | 392% | 7,236% | 0.98 |
| 5 | LV_56 | short | volatility | 368% | 17,058% | 1.00 |
| 6 | LV_54 | short | volatility | 357% | 16,262% | 1.00 |
| 7 | MACD_19_39 | long | trend | 350% | 12,389% | 0.99 |
| 8 | MA_10_30 | long | trend | 341% | 11,596% | 0.98 |
| 9 | LV_45 | short | volatility | 328% | 13,365% | 0.97 |
| 10 | vam_168_21 | long | momentum | 324% | 2,913% | — |

---

## Top B&H-Beating Strategies (% of Fortune 100 stocks beaten)

| Strategy | Beat Rate | Beaten / Total | Family |
|----------|-----------|----------------|--------|
| MACD_5_11_4 | *9%* | 23/261 | trend |
| MACD_5_12_4 | *9%* | 23/261 | trend |
| MACD_6_12_5 | *9%* | 23/261 | trend |
| MACD_6_11_4 | 8% | 22/261 | trend |
| MACD_5_10_4 | 8% | 22/261 | trend |
| MACD_6_13_3 | 8% | 21/261 | trend |
| MACD_6_13 | 8% | 21/261 | trend |
| LV_55 | 7% | 19/261 | volatility |
| PMO_20_10 | 7% | 19/261 | momentum |

---

## Key Findings

### 1. The MACD 5/11 Cluster Beats B&H Most Reliably
Ultra-fast MACD (fast=5, slow=11-12, signal=3-5) beats buy-and-hold on ~9% of Fortune 100 stocks.
This is 3x the baseline beat rate. The fast/slow ratio of ~2.2x appears optimal.

### 2. LV_55 Short Is the Raw Return Champion
Shorting Tesla (and high-momentum stocks generally) when volatility exceeds its 55-day median
produced +26,022% over 15 years — the *only* strategy that beats TSLA's own B&H (+2,807% margin).
The exact window is 55 days; 52-58d degrades smoothly in both directions.

### 3. Vol-Adjusted Momentum Converges at Short Windows
vam_21_5 (21-day return / 5-day vol) produces identical results to PM_1_0 (raw 1-month momentum).
At longer windows (126d+), the vol window makes no difference — sign() normalisation washes it out.
Conclusion: vol-adjustment only matters for very short lookback windows.

### 4. Long/Short Position Type Universally Destroys Value
All bottom-10 results across every round are long_short on volatile stocks.
Fortune 100 companies are structurally long-biased — alternating long/short destroys the natural uptrend.
*Rule: never use long_short on Fortune 100 stocks with trending behaviour.*

### 5. Combo/Filter Strategies Consistently Underperform
Every regime gate, triple confirmation, and ensemble strategy underperformed standalone signals.
Adding filters reduces the number of trades below the point where winners compound.
*Rule: simplicity wins for single-stock systematic strategies.*

### 6. The Search Has Converged
Rounds 7-10 produced byte-identical top 20 rankings. The parameter space of classical technical strategies
is exhausted at this resolution. Future gains require: (a) alternative data, (b) cross-sectional signals,
(c) intraday data, or (d) ML with better features than price/volume.

---

## Recommended Production Strategies

For a single-stock systematic approach on Fortune 100:

*For high-growth momentum stocks (TSLA, NFLX, AMZN):*
- LV_55 short — short during high-vol regimes, long during low-vol
- CAGR ~44%, Sharpe 1.07 on TSLA over 15 years

*For broad Fortune 100 application (highest B&H beat rate):*
- MACD_5_11_4 — ultra-fast MACD histogram (fast EMA 5, slow EMA 11, signal 4)
- 9% of stocks beaten, consistent across 5 rounds of validation

*For risk-adjusted returns (best Sharpe outside TSLA):*
- dual_mom_126_21 — 126d AND 21d momentum must agree (Sharpe 1.06 on TSLA)
- PM_1_0 — raw 1-month price momentum (simple, robust, Sharpe 1.06)

---

*Generated by autoresearch harness — 10 rounds complete*
