# H322 — FinBERT+Fundamentals Transformer for Earnings Direction
# Source: arXiv:2605.25894 (Multi-Modal Earnings Announcement Direction)
# Hypothesis: A Transformer jointly encoding FinBERT sentiment + 15 fundamentals
# + 3 technical indicators outperforms sequential filter approach (H317 NOT CONFIRMED)
# by learning feature interactions vs applying threshold gates.
#
# Key distinction from H317:
#   H317 uses sequential filters (FinBERT gate THEN EPS gate)
#   H322 uses Transformer to learn joint signal from all features simultaneously
#
# Design:
# - Universe: same 30-stock H163/H174 universe
# - FinBERT features: score, tone_surprise (as in H174)
# - Fundamental features (from yfinance): EPS growth, revenue growth, margins,
#   debt ratio, ROE, P/E, P/B, etc. — 15 features pre-announcement
# - Technical features: 21d momentum, 63d vol, RSI
# - Transformer: 2-layer, 4-head, trained on IS events; predict P(gap > 3%)
# - IS: 2020-2023 | OOS: 2024-2026
# - Gate: WR > 70% AND n >= 20 AND mean_ret > 4%
#
# Note: H163 FinBERT scores at backtesting/cache/h163_finbert_scores.parquet
# Note: yfinance earnings_dates has timezone issue — use tz_localize(None)
#
# See wiki/trading/algorithms/event-driven.md
pass
