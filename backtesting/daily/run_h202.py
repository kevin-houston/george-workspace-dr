# H202 — ML-Enhanced Cross-Sectional Momentum with Bias Correction
# Based on arXiv:2507.07107: bias elimination mask adds 0.44 Sharpe-point
# Test: XGBoost signal selector vs simple 6-1m return rank (H198 baseline)
# Universe: same 30-stock S&P 500 universe as H198
# Features: 9 Alpha101-derived factors including momentum, volume-intraday corr, open-volume divergence
# IS: 2013-2020, OOS: 2021-2026
# Confirm: OOS Sharpe > H198 baseline (1.174), Cumul > 1.3x
# NOTE: requires proper bias mask — train only on IS data, strict temporal cutoff
#
# STATUS: QUEUED — stub created 2026-05-16 by dream cycle
# See: dream_cycle/staged/2026-05-16/3_momentum_ml_bias_correction.json
