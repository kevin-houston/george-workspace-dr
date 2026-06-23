# H327 — kNN Macro-Analog Factor Ranker for H026/H041a/H045
# Source: arXiv:2606.22719 (2026-06-21)
# Hypothesis: kNN on lag-shifted FRED macro features identifies historically
# analogous market months and predicts which rotation strategy will
# outperform next month, matching LLM-level IC at zero API cost.
#
# Design:
# Feature vector (monthly, lagged by 1 month to avoid lookahead):
#   - VIX level (^VIX from yfinance)
#   - VIX change 1m
#   - SPY 12m return
#   - SPY distance from 200MA (%)
#   - T10Y3M yield curve slope (FRED)
#   - CPI monthly change (FRED)
#   - Credit spread proxy: HYG/IEI relative momentum
#   - Realized vol of SPY 20d
#
# kNN lookup:
#   At each month t, compute feature vector f(t-1).
#   Find k=10 most similar historical months by cosine similarity.
#   Average H026/H041a/H045 returns in those k months.
#   Rank predicted returns: overweight top-predicted strategy by +15%.
#
# Base allocation: H026=0.40, H041a=0.30, H045=0.30
# Adjustment: +0.15 to top-predicted, -0.075 each from other two
# Min weight: 0.10 (prevent zero-weight on any strategy)
#
# IS: 2010-2017 (train kNN feature matrix)
# OOS: 2018-2026 (rolling: each month extends the kNN library)
# Gate: OOS Sharpe > 2.501 (H318 static B) AND MaxDD < -4.3%
#
# Libraries: sklearn.neighbors.KNeighborsRegressor or manual cosine sim
# Data: yfinance (SPY, ^VIX, HYG, IEI) + FRED (T10Y3M, CPIAUCSL)
# No LLM, no neural network — pure kNN
#
# Cross-reference: H318 NOT CONFIRMED (logistic/IC-weighted both failed)
# Key question: is non-parametric kNN more robust than parametric logit?
pass
