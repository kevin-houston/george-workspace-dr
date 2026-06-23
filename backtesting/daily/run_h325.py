# H325 — AEGIS Sortino-Optimized Cross-Sectional Momentum
# Source: arXiv:2604.09060 (2026)
# Hypothesis: Volatility-adjusted momentum + minimax-correlation filter +
# SLSQP Sortino optimization improves H198 OOS Sharpe and MaxDD while
# reducing SPY correlation.
#
# Three-stage AEGIS framework:
# Stage 1: Volatility-adjusted momentum score
#   score_i = momentum_i / (realized_vol_i + epsilon)  # vol-normalize each stock
#   where momentum = 6m-1m (same as H198), vol = 63d realized vol
# Stage 2: Minimax-correlation filter
#   From top-N candidates, greedily select k stocks such that:
#   max_pairwise_correlation among selected <= threshold (0.60)
#   ensures structural diversification, reduces momentum crash risk
# Stage 3: SLSQP Sortino optimization
#   maximize Sortino = mean(r) / downside_std(r) subject to:
#     sum(w) = 1, w >= 0.05 (min position), w <= 0.30 (max position)
#   use rolling 12m IS window to estimate mean/downside_std
#
# Universe: H198 30-stock S&P 500 universe
# IS: 2013-2020 | OOS: 2021-2026
# Gate: OOS Sharpe > H198 1.174 AND MaxDD improvement > 5pp AND Corr(SPY) < 0.70
# Libraries: scipy.optimize.minimize (SLSQP), numpy, pandas, yfinance
#
# Note: survivorship bias same as H198 (fixed 2026 constituents)
# Note: SLSQP may fail to converge for short windows — add fallback to equal-weight
# See wiki/trading/algorithms/momentum-strategies.md for H198 baseline
pass
