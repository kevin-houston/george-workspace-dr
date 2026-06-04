'''
H251 — 3-State HMM Regime Detection for SPY/TLT/GLD Tactical Allocation
=========================================================================
Source: arXiv:2605.27848 (Verma, Putri & Lesupi, May 2026)
  'Regime-Based Portfolio Allocation Using Hidden Markov Models and RL'
  3-state Gaussian HMM (low-vol, transitional, high-vol) on SPY/TLT/GLD.
  RL-enhanced HMM outperforms rule-based; strong Sharpe vs SPY benchmark.

Baseline: SPY buy-and-hold (~Sharpe 0.5, MaxDD -50%+ in 2008/2020/2022)
H026 comparison: our ETF rotation (sector momentum top-1) OOS Sharpe ~1.5
H251 target: OOS Sharpe > 0.8, MaxDD < 30%

Implementation:
  Universe: SPY, TLT, GLD daily returns
  HMM: hmmlearn GaussianHMM, n_components=3, covariance_type="full", n_iter=300
  Features: [daily_return, rolling_21d_vol, rolling_21d_return]
  State labels (post-hoc, by vol level):
    State 0 = low-volatility (stable bull)
    State 1 = transitional (regime shift)
    State 2 = high-volatility (bear/stress)
  Allocation rules (monthly rebalance on state at prior month-end):
    State 0 (low-vol):    SPY=80%, TLT=10%, GLD=10%
    State 1 (transition): SPY=50%, TLT=30%, GLD=20%
    State 2 (high-vol):   SPY=20%, TLT=50%, GLD=30%

IS: 2004-2017  OOS: 2018-2025 (70/30 split as in paper)
Transaction costs: 10bp per rebalance
Confirm: OOS Sharpe > 0.8

Note: for OOS deployment, retrain HMM annually on expanding window.
      Use predict() not decode() (forward-only, no look-ahead).
Note: if H251 confirms, evaluate correlation vs H026/H041a for production blend.

Key library: hmmlearn (pip install hmmlearn -- already used in regime-detection.md)
'''

# TODO: Implement H251
# Step 1: Download SPY, TLT, GLD daily data 2004-2025 (yfinance)
# Step 2: Build feature matrix: [log_return, rolling_21d_vol, rolling_21d_return]
# Step 3: Fit GaussianHMM (n_components=3) on IS window (2004-2017)
# Step 4: Identify regime states by examining regime means/variances
# Step 5: Define allocation rules per state (see above)
# Step 6: Backtest OOS 2018-2025:
#   a. At each month-end, predict current state using IS-trained model
#   b. Apply next-month allocation based on state
#   c. Compute monthly returns
# Step 7: Report OOS Sharpe, MaxDD, vs SPY benchmark
# Step 8: Compute correlation of monthly returns vs H026 OOS returns

import os
print('H251 scaffold — 3-state HMM tactical allocation')
print('Source: arXiv:2605.27848 (Verma et al., May 2026)')
print('Universe: SPY/TLT/GLD; 3-state HMM (low-vol / transition / high-vol)')
print('Confirm: OOS Sharpe > 0.8')
print('Key: use predict() not decode() -- forward-only, no look-ahead')
