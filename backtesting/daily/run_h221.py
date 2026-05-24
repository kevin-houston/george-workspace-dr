"""
H221 — Drift Regime + Short-Term Reversal (arXiv:2511.12490)
==============================================================
Singha (2025): activate value/reversal signals ONLY during individual stock
'drift regimes' = stocks with >60% positive days in trailing 63 trading days.

Our implementation: apply H181 (1-month short-term reversal) signal exclusively
to stocks that are in a drift regime. Out-of-regime stocks get zero allocation.

Hypothesis: reversal is strongest when a stock has been in a sustained uptrend
(mean-reversion risk is elevated, crowded long positions build up).

Universe: same 30 large-cap stocks as H181
IS: 2013-2020, OOS: 2021-2026
Drift regime threshold: >60% positive days in trailing 63 trading days
Signal: monthly close return (1-month reversal, same as H181)
Portfolio: long bottom-3 by last month return among drift-regime stocks
Confirm: OOS Sharpe > 1.4 (must beat H181's 1.138 meaningfully)
"""

# TODO: implement — use H181 price cache + H215 daily OHLCV for drift regime
# Step 1: compute drift_regime_i(t) = fraction of positive daily returns in
#         trailing 63 trading days for stock i at month end t
# Step 2: filter to stocks where drift_regime_i(t) > 0.60
# Step 3: among filtered stocks, long bottom-N by last month return
# Step 4: evaluate IS/OOS with standard framework
pass
