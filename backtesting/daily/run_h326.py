# H326 — Continuous Tanh-Gated H026/H041a/H045 Strategy Blend
# Source: arXiv:2605.20636 (2026)
# Hypothesis: Differentiable continuous scoring via tanh/softplus smoothing
# improves on H318's discrete regime switches without adding LLM complexity.
#
# Four continuous signals (FRED + SPY price data):
# 1. rate_relief = tanh(-delta_TNX_3m / 1.0)
#    +1 if rates falling fast (bond-friendly), -1 if rising
# 2. equity_stress = tanh(-SPY_drawdown_pct / 0.10)
#    -1 if SPY down >10% from peak (bear mode), +1 if near highs
# 3. vix_relief = tanh((20 - VIX) / 5.0)
#    +1 if VIX < 20 (calm), -1 if VIX > 30 (stressed)
# 4. growth_crowding = tanh(-(SPY_12m_return - 0.15) / 0.10)
#    penalize when equity has been very strong (crowding risk)
#
# Composite score = mean([rate_relief, equity_stress, vix_relief, growth_crowding])
# ranges from -1 (full bear) to +1 (full bull)
#
# Allocation:
# bull_w  = [H026=0.50, H041a=0.35, H045=0.15]  # equity-heavy
# base_w  = [H026=0.40, H041a=0.30, H045=0.30]  # balanced (H318 static B)
# bear_w  = [H026=0.20, H041a=0.15, H045=0.65]  # bond-heavy
# final_w = bear_w * (-score)/2 + base_w * (1 - |score|) + bull_w * score/2
#   (smoothly interpolates; softplus avoids discontinuity at edges)
#
# IS: 2010-2017 | OOS: 2018-2026 (same as H318)
# Gate: OOS Sharpe > H318 static blend B (2.501) AND MaxDD < -4.3%
# Data: FRED T10Y (TNX proxy from yfinance ^TNX), SPY, ^VIX
# No LLM, no sklearn, pure FRED + yfinance + pandas/numpy
#
# Note: H318 found the regime-switch variant D (VIX+200MA) achieved
# Sharpe 2.582 with MaxDD -4.4% — just missed the 1pp MaxDD gate.
# H326 targets that same improvement but via smooth continuous signals.
pass
