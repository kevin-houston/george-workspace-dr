#!/usr/bin/env python3
"""
H409: Drift-Regime-Gated Value+Reversal on H198 30-Stock Universe
==================================================================
Source: arXiv:2511.12490 (Nov 2025) -- 'Discovery of a 13-Sharpe OOS Factor:
Drift Regimes Unlock Hidden Cross-Sectional Predictability'

Key idea: Value and short-term reversal signals only fire when a stock is in
a 'drift regime' -- defined as >60% positive return days in trailing 63-day
(3-month) window. The regime gate selectively activates the signal,
producing OOS Sharpe 13.19 long-short on S&P 500.

H409 adapts this to our long-only production pipeline:
  1. Compute drift_regime[i,t] = (positive_days_63d / 63) > 0.60 for each stock
  2. Compute BASE[i,t] = 0.7 * pct_rank(1/price) + 0.3 * (-zscore(ret_10d))
  3. GATED[i,t] = BASE[i,t] * drift_regime[i,t]  # zero if not in regime
  4. Blend with existing H041a momentum signal:
     COMPOSITE[i,t] = alpha * GATED[i,t] + (1-alpha) * h041a_score[i,t]
  5. Select top-N by COMPOSITE

Gate: OOS Sharpe > 4.068 (H041a/H398A baseline)
IS:  2013-2020  OOS: 2021-2026
Universe: H198 30-stock NASDAQ large-cap

Variants to test:
  A: Pure GATED replaces H041a signal (alpha=1.0)
  B: 50/50 blend with H041a (alpha=0.5)
  C: Regime as FILTER only -- require drift_regime=True to enter position,
     else hold cash or prior position
  D: Use 20-day window instead of 63-day (short-term version)

Caveats:
  - Original paper is long-short market-neutral; our long-only test may
    capture less of the factor's alpha (short leg likely contributes ~50%)
  - 'inverse price' as value proxy is unusual -- test with P/E or P/B too
  - Transaction costs: reversal signal has high daily turnover; weekly
    rebalancing may be needed to stay net-positive after costs
  - Capacity: original paper estimates $100-500M before degradation
"""

HYPOTHESIS = "H409"
GATE_SHARPE = 4.068
IS_START = "2013-01-01"
OOS_START = "2021-01-01"
UNIVERSE = "H198_30_stock"
DRIFT_THRESHOLD = 0.60  # >60% positive days in 63-day window
DRIFT_WINDOW = 63
VALUE_WEIGHT = 0.70
REVERSAL_WEIGHT = 0.30
REVERSAL_LOOKBACK = 10  # days

if __name__ == "__main__":
    print("H409 is a design stub -- full implementation pending.")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    print("Source: arXiv:2511.12490 drift-regime-gated value+reversal")
