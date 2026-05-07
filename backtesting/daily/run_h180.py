# H180: Spatio-Temporal Momentum
# Source: arXiv:2302.10175 (JTFDS 2023)
# Hypothesis: A simple MLP that learns both cross-sectional ranks AND time-series
# momentum features (rolling 1m, 3m, 6m, 12m returns) as inputs will outperform
# the pure rank-based H026 sector rotation signal.
#
# Universe: H026's 25-asset sector ETF universe
# Signal: MLP(cross_sectional_rank, ts_1m, ts_3m, ts_6m, ts_12m) → score
# Training: IS 2008–2017, OOS 2018+
# Architecture: 2-layer MLP, 32 hidden units, ReLU, dropout 0.2
# Loss: cross-entropy on next-month winner label (top-1 = 1, else 0)
# Confirm criteria: OOS Sharpe > 3.0 (must beat production H026 baseline)
#
# Implementation notes:
# - Normalize features monthly (z-score across cross-section)
# - Use sklearn MLPClassifier for simplicity (no PyTorch dependency)
# - Key test: does adding time-series features improve over pure rank?
# - Do NOT overfit: IS 2008-2017 has ~120 months, 25 assets = small dataset
#   Use heavy regularization (alpha=0.01, max_iter=100, early_stopping)
# - Compare variants: A (cross-sectional only), B (TS only), C (combined)
# PREREQUISITE: None — can run standalone
# ESTIMATE: 3h implementation
