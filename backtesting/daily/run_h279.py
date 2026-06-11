# H279: LLM-Enhanced Cross-Sectional Momentum
# Source: arXiv:2510.26228 — ChatGPT in Systematic Investing (Anic et al. 2025)
#
# Architecture:
# 1. Compute H228 alpha101+reversal signal (or H198 6-1m momentum) as base
# 2. For each stock about to enter a long position:
#    a. Fetch last 3 days of news headlines via NewsAPI ($NEWSAPI_KEY)
#    b. Query gpt-4o-mini: 'Do these headlines support momentum continuation for [ticker]?'
#    c. If response = NO (reversal risk) → skip this stock, fill with next-ranked substitute
# 3. Measure: coverage rate (what % of positions pass LLM filter), IS Sharpe delta
#
# Baseline: H228 OOS Sharpe 1.572, H198 OOS Sharpe 1.174
# Gate: net OOS Sharpe >= baseline × 0.95 (tolerate up to 5% degradation from coverage loss)
#       AND mean coverage rate >= 80% (LLM should filter edge cases, not gut the portfolio)
# IS: 2019-2021 | OOS: 2022-2024
# Cost: ~$0.02-0.05 per filtered stock (gpt-4o-mini, 3 headlines input)
#
# Implementation notes:
# - Use NewsAPI /everything endpoint with q=ticker, from=3_days_ago, sortBy=publishedAt
# - Prompt: '{headlines} Context: {ticker} has had {momentum_return:.1%} return over past 6 months.
#   Given these recent news items, rate 1-5 whether news SUPPORTS (5) or CONTRADICTS (1) momentum continuation.'
# - Threshold: skip if score <= 2 (strong contradiction)
# - Cache LLM responses — same date+ticker+news combo should not re-query
# - Apply H228 cost model (5 bps/leg spread + 3 bps slippage = 8 bps round-trip)
# - See wiki: algorithms/momentum-strategies.md for H228 signal spec
