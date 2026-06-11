# H280: MarketSenseAI 4-Agent Equity Signal Replication
# Source: arXiv:2604.17327 — Signal or Noise in Multi-Agent LLM-based Stock Recommendations?
#
# Architecture (simplified MarketSenseAI):
# Agent 1: News — 7-day news sentiment for ticker (NewsAPI + gpt-4o-mini)
# Agent 2: Fundamentals — latest earnings beat/miss, revenue growth, margins (FMP API)
# Agent 3: Dynamics — price momentum + volume dynamics (yfinance momentum signals)
# Agent 4: Macro — current FRED regime (SPY 200MA + VIX + yield curve)
# Synthesis: combine 4 agent outputs into a monthly thesis + BUY/HOLD/SELL recommendation
#
# Universe: S&P 100 (100 largest stocks) — manageable API cost
# Signal: strong_buy = synthesis scores 8+ out of 10
# Portfolio: equal-weight top-10 strong_buy recommendations per month
#
# IS: 2023-2024 | OOS: 2025 (truly after arXiv paper's study period)
# Baseline: S&P 500 equal-weight return (RSP benchmark)
# Gate: OOS Sharpe >= 1.0, IS p-value <= 0.05 on monthly IC
#
# Cost estimate: ~$0.50-1.00/stock/month for 4 LLM calls
# For 100 stocks: $50-100/month → ~$600-1200/yr
# Only run in backtest mode initially (historical news via NewsAPI + cached FMP data)
#
# Key implementation guard:
# - Use strict timestamp controls: news_query_date = signal_date - 1 day
# - FMP fundamentals: last earnings released BEFORE signal_date
# - FRED data: use .shift(1) on all macro signals
# - Log each agent decision for post-hoc attribution analysis
# - See wiki: tools/multi-agent-llm-trading.md for architecture reference
