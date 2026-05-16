# H204 — Deep Reinforcement Learning vs Momentum Baseline
# Based on: awesome-deep-trading survey; FinRL (AI4Finance); arXiv:2511.12120
#
# Hypothesis: A PPO agent trained on our 30-stock IS (2013-2020) achieves
# OOS Sharpe > H198 6-1m momentum baseline (1.174) on 2021-2026.
#
# Algorithm: PPO (stable-baselines3), 5-seed ensemble
# State: 60-day return history per stock + current portfolio weights
# Action: continuous portfolio weights [-1, 1] per stock
# Reward: daily return - 10bps turnover cost
# IS: 2013-2020  OOS: 2021-2026  Universe: same 30 S&P 500 stocks as H198
# Confirm: OOS Sharpe > 0.8 (beat risk-free but acknowledge momentum is hard to beat)
# Secondary: Corr(H204, H198) < 0.6 (useful for H203 blend regardless of absolute Sharpe)
#
# CRITICAL: strict temporal cutoff — state at step t uses only data from t-252 to t-1
# Train ONLY on IS data. No look-ahead in normalization windows.
#
# STATUS: QUEUED — stub created 2026-05-16
# See: wiki/trading/algorithms/deep-rl-trading.md
# Dependencies: pip install stable-baselines3 gymnasium
