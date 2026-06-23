# H328 — Student-t Emission HMM (H251 heavy-tail fix)
# Source: arXiv:2606.23492 (2026)
# Hypothesis: Replacing Gaussian emissions with Student-t in the H251
# 3-state HMM on SPY/TLT/GLD fixes state degeneracy (H251 predicted
# low_vol 100% of OOS months), enabling meaningful regime-conditional allocation.
#
# Implementation approach:
# Option A: hmmlearn GaussianHMM + fat-tail preprocessing
#   - Transform returns: r_t* = sign(r_t) * |r_t|^(1/nu) where nu=4 (df)
#   - This approximates Student-t without custom EM
#   - Quick to implement, baseline test
# Option B: Custom Student-t EM (exact)
#   - E-step: standard forward-backward
#   - M-step: update mu, Sigma, nu via ML equations (iterative)
#   - scipy.stats.t.fit per state per feature
#   - More correct, slower to implement
# Start with Option A; upgrade to B if A doesn't fix degeneracy.
#
# Universe: SPY / TLT / GLD (same as H251)
# States: 3 (low_vol/bull, mid/neutral, high_vol/bear)
# Features: monthly returns of SPY, TLT, GLD (same as H251)
# IS: 2004-2017 | OOS: 2018-2026
#
# Allocation (same as H251, now conditioned on non-degenerate states):
#   low_vol:  SPY 0.80, TLT 0.10, GLD 0.10
#   neutral:  SPY 0.50, TLT 0.30, GLD 0.20
#   high_vol: SPY 0.20, TLT 0.50, GLD 0.30
# Use smooth_regime_labels(min_duration=2) to avoid excessive trading
#
# Gate: OOS Sharpe > H251 0.941 AND state distribution not degenerate
#   (no single state > 80% of OOS months)
# Also report: Corr with H026 (H251 was 0.71 — want <0.70)
#
# Libraries: hmmlearn (GaussianHMM), scipy.stats, numpy, yfinance
# No external APIs beyond yfinance
#
# Cross-reference:
#   H251 CONFIRMED (degenerate): wiki/trading/algorithms/regime-detection.md
#   SJM design note in CLAUDE.local.md (2026-05-19)
pass
