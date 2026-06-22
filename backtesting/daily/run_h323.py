# H323 — HMM + RL Regime-Aware ETF Rotation
# Source: arXiv:2605.27848 (HMM+RL Portfolio Optimization, May 2026)
# Hypothesis: 3-state HMM (low-vol/transition/high-vol) + RL allocation policy
# outperforms static H026/H041a/H045 blend by adapting allocations to regime.
#
# Key distinction from H318 (meta-agent LLM):
#   H323 uses statistical HMM (no LLM cost) + RL policy (PPO or DDPG)
#   H318 uses GPT-4o to dynamically weight strategies
#   Horse-race: if H323 matches H318 Sharpe at zero LLM cost, prefer H323
#
# Design:
# - Universe: H026 (25-asset sector+alts) output monthly returns as portfolio
# - Regime features: SPY daily return, VIX, T10Y3M, realized vol 20d
# - HMM: 3 states via hmmlearn GaussianHMM, smooth with min_duration=5
#   (SJM approximation — see wiki/trading/algorithms/regime-detection.md)
# - RL: PPO on monthly state → weight adjustment for H026/H041a/H045
# - IS: 2004-2018 | OOS: 2019-2026
# - Gate: OOS Sharpe > 4.158 (production portfolio baseline) AND MaxDD < -5%
# - Note: production baseline is already 4.158 — regime layer needs to add value
#
# Note: hmmlearn already in venv
# Note: stable-baselines3 for RL (H204 scaffold exists at run_h204.py)
pass
