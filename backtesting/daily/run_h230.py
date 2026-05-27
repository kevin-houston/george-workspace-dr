"""
H230 — Alpha Decay Optimization for H217 Rebalancing Frequency
==============================================================
arXiv:2512.11913 (Dec 2025): Hyperbolic alpha decay modeling across
Fama-French factors. Momentum decays fastest (~40% in 3 months).
alpha101 is an intraday microstructure signal — may decay faster than
monthly momentum, potentially favoring bi-monthly rebalancing.

Test rebalancing frequencies: monthly, bi-monthly (every 2 weeks),
weekly — applying H217 signal (median alpha101 top-6) at each frequency.
Include transaction cost model: 0.1% round-trip per rebalance event.

Universe: 30 large-cap (same as H217)
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe after transaction costs > H217 monthly (1.559)
Note: Requires daily close data (already cached as h215_*_daily_*.parquet)
"""

# SCAFFOLD — implement using run_h217.py pattern
# Key change: instead of monthly rebalance, test bi-monthly (every 2 weeks)
# Rebalance dates: 1st and 3rd Friday of each month
# Each rebalance: recompute median alpha101 signal over trailing 22 days
# Apply transaction cost: 0.1% on full portfolio turnover per rebalance
# Compare OOS Sharpe after costs vs H217 monthly baseline (1.559)
