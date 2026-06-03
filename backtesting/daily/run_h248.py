'''
H248 — Betting Against Bad Beta (BABB)
=======================================
Source: arXiv:2409.00416 (Herculano, August 2024)
  'Betting Against (Bad) Beta'
  Double-sort on total beta AND bad beta (downside component).
  Sharpe improvement: ~800 bps vs standard BAB (1963-2021).

H192-D baseline: Sector-neutral BAB, OOS Sharpe=1.367
BAB signal: low-beta stocks outperform high-beta stocks (Frazzini & Pedersen 2014)
BABB refinement: separate 'bad beta' (coskewness/downside beta) from 'good beta'
  to avoid holding stocks with high downside correlation even if low total beta.

Bad beta definition (Herculano):
  Bad beta = cov(R_i, R_m | R_m < threshold) / var(R_m | R_m < threshold)
  i.e., realized beta during market down-moves (use threshold = 0 or monthly median)
  Good beta = total beta - bad beta

Portfolio construction (BABB):
  1. Compute total beta (rolling 12-month daily returns)
  2. Compute bad beta (rolling 12-month, conditioning on down-market days)
  3. Double-sort: bottom tertile total beta + bottom tertile bad beta = BABB long
     Top tertile total beta + top tertile bad beta = BABB short
  4. Dollar-neutral, equal-weight within each leg
  5. Borrow cost: 0.75%/yr on short notional

IS: 2013-2020  OOS: 2021-2026
Confirm: OOS Sharpe >= 1.5
Key diagnostic: Corr(BABB, H228 momentum) OOS -- if < 0.3 -> production addition candidate

Universe: same 200-stock large-cap universe (H241 cache for monthly returns)
Additional data: daily prices for beta computation (from H245 daily cache or new download)
'''

# TODO: Implement H248
# Step 1: Load H241 cache (monthly prices for universe)
# Step 2: Download/load daily prices for beta computation
# Step 3: For each month-end date:
#   a. Compute total beta: regress daily stock returns on SPY daily returns (trailing 12 months)
#   b. Compute bad beta: same regression but only on days when SPY return < 0
#   c. Rank stocks on total beta (ascending) and bad beta (ascending)
# Step 4: Long bottom tertile on BOTH dimensions; short top tertile on BOTH
# Step 5: Dollar-neutral portfolio, monthly rebalance
# Step 6: Compute OOS Sharpe, correlation vs H228 monthly returns

import os
print('H248 BABB scaffold — implementation needed (see design comments)')
print('Key dependency: daily price data for beta computation (H245 daily cache usable)')
print('Baseline: H192-D BAB OOS Sharpe=1.367')
print('Confirm gate: OOS Sharpe >= 1.5')
print('Correlation gate: Corr(BABB, H228) < 0.3 for production addition')
