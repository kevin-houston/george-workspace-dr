# H274: Multi-Agent PEAD Upgrade
# Architecture: 3 LLM agents debate each 8-K before entry
# Agent 1: FinBERT sentiment (existing H163/H174 gate >= 0.18)
# Agent 2: Structured analyst — extract revenue guidance tone, mgmt language, forward guidance
# Agent 3: Contrarian — identify embedded negatives in positive-scoring 8-Ks
# Entry only if all 3 agents confirm positive
# Baseline: H174 WR=81.8%, MeanRet=6.89%, n=22
# Gate: WR > 81.8% with n >= 15 OOS events
# IS period: 2019-2021
# OOS period: 2022-2024
# Cost model: ~$0.05-0.20 per decision (3 agents x gpt-4o-mini)
# See wiki: tools/multi-agent-llm-trading.md for framework comparison
#
# Implementation notes:
# - Load same 8-K dataset used for H163/H174
# - Run FinBERT first (cheap filter) — only advance to agents if score >= 0.18 AND surprise >= 0.02
# - Use OpenAI API (OPENAI_API_KEY) for agents 2 and 3
# - Structured output: {confirmed: bool, confidence: 0-1, rationale: str}
# - Log all agent decisions for post-analysis
# - Apply same IS/OOS split and transaction cost model as H174
