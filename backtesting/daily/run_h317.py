# H317 — Multi-Modal PEAD: FinBERT + Fundamentals + Price Momentum
# Source: Noseda, Soldati, Paina arXiv:2605.25894 (May 2026)
# Hypothesis: Adding fundamental metrics and pre-announcement price momentum
# to the existing FinBERT 8-K signal improves PEAD entry win rate above 81.8%.
#
# Current pipeline (H174): FinBERT score >= 0.18 AND EPS surprise >= 0.02
# Proposed extension:
#   score_composite = 0.5*finbert_score + 0.3*fundamentals_score + 0.2*price_momentum_score
#   where:
#     fundamentals_score = norm(revenue_growth_yoy) + norm(eps_trajectory_3q)
#     price_momentum_score = -1 if stock up >10% pre-announcement (mean reversion risk)
#                            +1 if stock flat/down (low expectations, room to beat)
#
# IS: 2021-2023 (H174 OOS period becomes IS for H317)
# OOS: 2024-2026
# Gate: Win rate > 70% AND mean return > 4% per trade on 20+ OOS events
#
# Data sources:
#   - FinBERT score: existing pead_overnight.py pipeline
#   - Fundamentals: yfinance.Ticker.quarterly_financials (free)
#   - Price momentum: yfinance.download() trailing 21d return pre-announcement
#
# Integration path: if confirmed, update pead_overnight.py to use composite score
# See backtesting/paper_trading/pead_overnight.py for base implementation
pass
