#!/usr/bin/env python3
"""
H373: MAX Factor Tilt Within H198 30-Stock Momentum Universe

Hypothesis: Within H198 top momentum candidates, prefer higher-MAX stocks
(maximum daily return over prior month). Tandfonline 2025: high-MAX ×
high-momentum = +2.5%/month vs H198 plain momentum +~0.9%/month OOS.

Baseline to beat: H198 OOS Sharpe 1.174, MaxDD -22.7%
Gate: OOS Sharpe > 1.174 AND MaxDD not worse than -30% (accept higher vol)

Variants:
  A: composite = 0.7 * mom_rank + 0.3 * max_rank (mild tilt)
  B: composite = 0.5 * mom_rank + 0.5 * max_rank (equal blend)
  C: filter: long top-1 only if MAX_rank > 0.7 (lottery threshold gate)
  D: Var A + OB filter (H343 Var B params: window=20, swing_len=3)

IS:  2013-2020 (same as H343/H344)
OOS: 2021-2026

NOTE: This is a stub requiring implementation.
Base off run_h343.py (H198 + OB filter) or run_h198.py.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# Universe: same 30-stock NASDAQ universe as H198
UNIVERSE = [
    'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','AVGO','COST','NFLX',
    'ASML','ADBE','AMD','QCOM','CSCO','AMAT','TXN','INTC','INTU','ISRG',
    'BKNG','VRTX','GILD','MRNA','REGN','BIIB','ILMN','IDXX','DXCM','ALGN'
]

IS_START  = '2013-01-01'
IS_END    = '2020-12-31'
OOS_START = '2021-01-01'
OOS_END   = '2026-12-31'

def compute_max_factor(daily_returns, lookback=21):
    """MAX = max daily return over prior month."""
    return daily_returns.rolling(lookback).max()

def compute_momentum(monthly_close, skip=1, lookback=6):
    """6-1m momentum: 6m return skipping most recent month."""
    r = monthly_close.pct_change(lookback + skip)
    r_skip = monthly_close.pct_change(skip)
    return r / (1 + r_skip) - 1  # Remove skip-month return

# TODO: Full H373 implementation
# 1. Download UNIVERSE daily + monthly price data
# 2. Compute momentum score (H198 method)
# 3. Compute MAX score (max daily return in prior month)
# 4. Rank both; form composite per variant
# 5. Long top-1 composite each month, monthly rebalance
# 6. Report Sharpe, MaxDD, WF ratio vs H198 baseline

print('H373 stub: MAX-momentum tilt within H198 - requires implementation')
print('Base: H198 OOS Sharpe 1.174. Gate: OOS Sharpe > 1.174')
print('Reference: Tandfonline 2025 — MAX×Momentum +2.5%/month pocket')
