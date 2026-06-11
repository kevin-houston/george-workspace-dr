# H281: Macro-LLM ETF Rotation
# Source: arXiv:2606.08283 — Macro Economists in the Machine (Wang, Dai, Ma — Jun 2026)
#
# Design: augment H026 ETF rotation with macro-LLM tilt signal
# Base signal: H026 momentum rank (3m+6m+12m) on 25-ETF universe
# LLM layer: monthly, compute FRED z-scores for:
#   - FEDFUNDS (Fed funds rate vs 12m avg)
#   - CPIAUCSL_YOY (CPI YoY vs 12m avg)
#   - UNRATE (unemployment vs 12m avg)
#   - T10Y2Y (yield curve)
#   - VIXCLS (VIX vs 12m avg)
# Feed z-scores to 3 agents:
#   Agent H (Hawkish): gpt-4o-mini, inflation-tightening prior
#     'Given these macro z-scores, adjust commodity/equity ETF weights for an inflation-fighting tightening environment'
#   Agent D (Dovish): gpt-4o-mini, growth-easing prior
#     'Given these macro z-scores, adjust ETF weights for a growth-supportive easing environment'
#   Agent B (Debate): runs after seeing both H and D outputs, synthesizes with bias correction
#     'Given Hawkish view X and Dovish view Y, provide a balanced macro allocation tilt'
# Each agent outputs weight modifiers for major sectors: equity (XLK/XLE/XLF etc), bonds (TLT/IEF), commodities (GLD/DBC/USO)
# Final signal = H026_rank * (1 + Debate_tilt_modifier) → renormalize
#
# Baseline: H026 OOS Sharpe 3.007 (2018+)
# Gate: OOS Sharpe >= H026 baseline (any degradation = reject) + must survive 2022 bear
# IS: 2018-2021 | OOS: 2022-2024
#
# Implementation notes:
# - FRED data: all signals must be .shift(1) (lag 1 month for release timing)
# - LLM calls: gpt-4o-mini, ~$0.01/month/agent for 3 agents = ~$0.36/year
# - Save agent outputs to log for attribution analysis
# - Compare: H026 baseline vs H_agent_only vs D_agent_only vs Debate_agent
# - Reference: wiki/algorithms/factor-models.md for Fama-French macro factor context
