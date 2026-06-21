# H320 — LightGBM Momentum Crash Filter on H198 6-1m Momentum
# Source: EdgeTools blog "Momentum Crashes Are Optional (If You Let ML Filter Them)" (2026)
# Academic basis: Daniel & Moskowitz (2016) — momentum crash risk during market reversals
# Hypothesis: A LightGBM classifier trained on macro + technical features identifies
# high-crash-risk momentum periods and gates the H198 signal. EdgeTools reports MaxDD
# reduction from 30% to 13% on US equity momentum. On H198 (OOS Sharpe 1.174),
# crash filter should preserve upside while reducing the 2022 drawdown.
#
# Variants:
#   A: H198 baseline (no filter)
#   B: H198 + VIX < 25 gate (simple regime benchmark)
#   C: H198 + LightGBM crash probability < 0.35 gate (hard gate)
#   D: H198 + LightGBM continuous scaling (position × (1 - P_crash))
#
# Features (6 total):
#   1. SPY 200d MA relative position (SPY / MA200 - 1)
#   2. VIX level (monthly average)
#   3. VIX 20d change
#   4. Momentum portfolio trailing volatility (rolling 20d std of winner-loser spread)
#   5. Momentum portfolio trailing 6m return (winner minus loser decile spread)
#   6. FRED T10Y3M yield curve slope (via FRED API)
#   (Feature 7, market cap dispersion, is optional — lower importance per EdgeTools)
#
# Target variable: 1 if H198 monthly return < -5% (momentum crash), 0 otherwise
# Expected crash months in IS: ~8–12 out of 96 months (2013–2020)
# Training: 2-year rolling window (no IS/OOS contamination)
#
# IS: 2013-01-01 to 2020-12-31
# OOS: 2021-01-01 to 2026-06-20
# Gate: OOS Sharpe > 1.174 (H198 baseline) AND MaxDD improvement > 5pp
#
# Data sources:
#   - H198 signals: recompute or load from backtesting/daily/run_h198.py output
#   - VIX: yfinance '^VIX' daily
#   - SPY 200d MA: yfinance 'SPY' daily
#   - FRED T10Y3M: fredapi (T10Y3M series)
#   - lightgbm: pip install lightgbm
#
# Implementation plan:
# 1. Load H198 monthly returns (winner-loser portfolio, 30-stock universe)
# 2. Build feature matrix from VIX, SPY/MA200, momentum spread stats, yield curve
# 3. Train LightGBM with rolling 2yr window, predict crash probability month t+1
# 4. Backtest variants A-D: compare Sharpe and MaxDD vs baseline
# 5. Compare against simple VIX<25 gate (Variant B) to confirm ML adds value
#
# See wiki/trading/algorithms/ for H198 methodology
# See dream_cycle/staged/2026-06-20/6_momentum_crash_llm_filter_h320.json for design spec
pass
