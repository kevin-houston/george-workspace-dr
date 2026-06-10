# H268 — Alpha-GPT Factor Expression Auto-Search Loop
# Source: arXiv:2308.00016 (Alpha-GPT, 2023) + Kevin direction 2026-06-09
#
# Idea: LLM generates concrete mathematical factor expressions from a primitive set,
# this script backtests each, feeds results back to LLM for iteration.
#
# Expression primitives: close, open, high, low, volume, returns_1d/5d/21d, vwap
# Operators: rank, delay, delta, zscore, rolling_mean, rolling_std, correlation, abs, log, sign
#
# Loop:
#   1. Claude receives primitives + prior results + domain constraints
#   2. Generates 5 candidate factor expressions (Python-evaluable strings)
#   3. This script evaluates: IS Sharpe (2013-2020), OOS Sharpe (2021-2025)
#      on H181's 30-stock large-cap universe
#   4. Results fed back to Claude; repeat 3-5 rounds
#
# Gate: OOS Sharpe > 1.0 AND Corr(new factor, H026) < 0.5
# Universe: H181's 30-stock large-cap S&P 500
# API keys: $OPENAI_API_KEY or $ANTHROPIC_API_KEY (Claude preferred)
#
# Scaffold only — full implementation pending
