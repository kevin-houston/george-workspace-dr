"""
H223 — Cross-Sectional Factor Momentum: Multi-Window Blend
==========================================================
Applied Economics Letters (2025): factor momentum across multiple formation
periods (1–1, 2–6, 7–12, 13–60 months) consistently outperforms single-window.

This extends H198 (6-1m momentum, OOS Sharpe 1.174) by blending signals:
  S_i = rank(R_1m) + rank(R_6m) + rank(R_12m)  (equal-weighted rank sum)
Alternative: IC-weighted blend (weight each window by its IS information coefficient).

Universe: same 30 large-cap stocks as H198
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 1.4 (must beat H198's 1.174 meaningfully)
Experiment B: test all 4 windows from paper (1-1, 2-6, 7-12, 13-60)
"""

# SCAFFOLD — implement using pattern from run_h198.py
# Key changes vs H198:
# 1. Compute 3 separate return signals: 1m, 6m, 12m
# 2. Rank each signal cross-sectionally each month
# 3. Average ranks → composite momentum score
# 4. Long top-5 by composite score
# Note: H198 skips the most recent 1 month (6-1m). H223 should test:
#   Option A: include 1m return in blend (may add reversal noise)
#   Option B: exclude 1m (12-2m + 6-2m blend to avoid short-term reversal)
