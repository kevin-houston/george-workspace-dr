# H214 scaffold — Conditional Vol-Scaled Momentum with Regime Gating
# Method: vol-scaled 6-1m momentum (H212) + regime gate + 52-week-high filter
# References:
#   - Daniel & Moskowitz (RFS 2016): crash risk concentrated in high-vol regimes
#     and near-52-week-high stocks
#   - Bongaerts et al. (2020): conditional vol-scaling (reduce in high-vol regimes)
#
# Two experiments:
# A. Regime gate: pause momentum exposure when market realized_vol > 80th pct of
#    trailing 1-year vol. Hold BIL during gate-off periods.
# B. 52-week-high filter: exclude stocks within 5% of their 52-week high from
#    the momentum ranking (these are the crash-prone overextended winners)
#
# Key hyperparameters:
# - VOL_GATE_PERCENTILE: 80 or 90 (market-level: use SPY 1m realized vol)
# - HI52W_BUFFER: 0.95 (exclude stocks with price > 95% of 52w high)
# - VOL_WINDOW_SIGNAL: 6 (months trailing vol for signal scaling, same as H212)
#
# Expected: OOS Sharpe > 1.3 (beat H212's 1.244) with MaxDD < -13.8%
# Baseline: H212 (vol-scaled, OOS Sharpe 1.244, MaxDD -13.8%)
#           H198 (raw 6-1m, OOS Sharpe 1.174, MaxDD -22.7%)
#
# TODO: implement full backtest body — use run_h212.py as starting point
# Add: SPY vol regime computation; per-stock 52w high price filter
pass
