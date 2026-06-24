# H329 — Optimal Options Portfolio Under Skew-t Returns
# Source: arXiv:2606.17032 (2026-06-15)
# Hypothesis: BSM/Gaussian optimal options weights (iron condor delta selection,
# sizing) are suboptimal when returns follow skew-t. Skew-elliptical t captures
# fat tails + negative skew observed in equity returns. Analytical weights
# for Sharpe and Return-VaR ratio maximization differ from Gaussian-optimal,
# especially for OTM short options that are most exposed to tail risk.
#
# Implementation plan:
# 1. Fit skew-t to SPX daily returns: scipy.stats.t (symmetric) or
#    use statsmodels skew-t; estimate df + skewness from IS data (2010-2017)
# 2. Compute analytical optimal strike (delta) for short put under skew-t
#    vs BSM (Gaussian) — compare where divergence is largest
# 3. Optimal sizing: maximize Sharpe ratio using skew-t P&L distribution
#    vs equal-notional sizing (the default in H266)
# 4. Backtest: SPX iron condor with (a) standard 16-delta short, (b) skew-t-
#    optimal delta using closed-form from paper. OOS 2018-2026.
#
# Gate: OOS Sharpe > equal-notional condor baseline AND MaxDD improvement
# Universe: SPX options (synthetic via BSM+VIX, or LEAN QuantConnect free tier)
# Libraries: scipy.stats, numpy, py_vollib, pandas, yfinance
# Data: Tier 0 (synthetic) for feasibility; upgrade to LEAN for validation
#
# Cross-reference:
#   H266 iron condor (queued)
#   H309 SPX dispersion (PARTIAL CONFIRMED, Phase 2)
#   Options Backtesting Methodology: wiki/trading/backtesting/options-backtesting-methodology.md
pass
