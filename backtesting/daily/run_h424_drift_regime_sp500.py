#!/usr/bin/env python3
"""
H424 — Drift-Regime × Value+Reversal on S&P 500

Source: arXiv:2511.12490 (Singha, Nov 2025)
"Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden Cross-Sectional Predictability"

Paper claims: OOS Sharpe 13.19, CAGR 158.6%, MaxDD -11.9%, S&P500 universe 2004-2024.

Mechanism:
- Per-stock drift regime: fraction of positive-return days over trailing 63 trading days > 0.60
- Base signal: 0.7 × value_rank + 0.3 × reversal_rank
  - value = 1/price → cross-sectional percentile (connects to H411/H416 findings)
  - reversal = negated 10-day trailing return → z-score
- EDGE signal = BASE × REGIME (deactivate signal for stocks NOT in drift regime)
- Long-short: top/bottom z-score buckets, 50% gross each side, ~0% net

Connection to H411/H416:
- H411 confirmed OOS Sharpe 4.825 on 30-stock NASDAQ using 1/price rank × 20d drift gate (positive-day fraction > 0.60)
- H416 extended to top-3 picks → OOS Sharpe 5.342 (new H-series record)
- Paper uses 63d window vs H411's 20d; paper uses long-short vs H411's long-only
- S&P 500 universe (~500 stocks) vs H198's 30 NASDAQ large-cap
- CRITICAL: paper's 13-Sharpe may be inflated by daily rebalancing + L/S construction;
  long-only monthly rebalancing likely much lower; purpose of this test is to validate
  the mechanism and find a long-only monthly variant that beats gate

Test design (George's standard IS/OOS):
- Universe: S&P 500 component tickers (use survivorship-adjusted list from yfinance SPY holdings)
- IS: 2013-2020 / OOS: 2021-2026 (George's canonical split)
- Rebalancing: MONTHLY (not daily — minimize turnover and transaction costs)
- Long-only only (no short-selling in paper accounts)
- Gate: OOS Sharpe > 1.174 (H198 baseline) AND Corr(SPY) < 0.80

Variants:
- Var A: 63d drift window, 60% threshold, top-2 picks (replicating paper's core params)
- Var B: 20d drift window, 60% threshold, top-2 picks (H411 params on S&P500 universe)
- Var C: 63d drift window, 60% threshold, top-1 pick
- Var D: 63d drift window, 60% threshold, top-2 picks + H026 macro overlay (SPY > 200MA)
- Var E: paper's 0.7/0.3 value+reversal composite vs pure 1/price rank (H411 signal)

Note: Paper's extreme Sharpe (13.19) uses daily L/S rebalancing at 42% daily turnover
— not replicable in retail-scale monthly paper trading without leverage.
Expected realistic monthly long-only OOS Sharpe: 1.5-3.0 range.

If confirmed: potential addition to production portfolio as daily IBS-style strategy
or as enhancement to H026 ETF rotation selection.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# TODO: Implement H424 backtest
# 1. Download S&P 500 constituent list (yfinance SPY holdings or Wikipedia)
# 2. Get daily OHLC for all constituents 2010-2026
# 3. Compute per-stock drift regime: rolling 63d positive-day fraction > 0.60
# 4. Compute value rank (1/price percentile) and reversal rank (-10d return z-score)
# 5. Compute BASE = 0.7*value_rank + 0.3*reversal_rank
# 6. Compute EDGE = BASE * REGIME
# 7. Monthly rebalancing: top-2 EDGE stocks that are in drift regime
# 8. IS/OOS split 2013-2020 / 2021-2026
# 9. Report OOS Sharpe, MaxDD, CAGR, Corr(SPY), annual returns

if __name__ == '__main__':
    print('H424 stub — implement per design above')
    print('Source: arXiv:2511.12490 (Singha 2025)')
