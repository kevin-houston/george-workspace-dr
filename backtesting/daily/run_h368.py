"""
H368 — ML-Forecasted Asymmetric Beta as Factor Signal
Source: arXiv:2604.22933 (Conlon, Cotter, Kynigakis; April 2026)

Hypothesis: Forecast up-beta and down-beta separately per stock using ML on firm
characteristics. Long stocks with low down-beta + high up-beta. Key finding: trading
frictions, intangibles, momentum, growth drive future risk dynamics.

Gate: OOS Sharpe > 1.174 (H198 6-1m momentum baseline), Corr(SPY) < 0.70
Universe: S&P 500 constituents (survivorship-bias-caveat)
IS: 2014-01-01 to 2020-12-31
OOS: 2021-01-01 to 2026-06-30

Implementation notes:
- Estimate up-beta = Cov(r_i, r_m | r_m > 0) / Var(r_m | r_m > 0) rolling 36m
- Estimate down-beta = Cov(r_i, r_m | r_m < 0) / Var(r_m | r_m < 0) rolling 36m
- Features for ML forecast: size, B/M, momentum, intangibles ratio, trading volume
- Model: LightGBM (consistent with H320); predict next-month up-beta and down-beta
- Score = predicted up-beta - predicted down-beta; long top decile, short bottom decile
- Monthly rebalance; equal-weight within L/S legs
"""

UNIVERSE = 'SP500'  # use yfinance SP500 proxy or FMP screener
IS_END = '2020-12-31'
OOS_START = '2021-01-01'
ROLLING_BETA_WINDOW = 36  # months
GATE_SHARPE = 1.174

# TODO: implement asymmetric beta estimation and ML forecasting
# 1. Download monthly returns for S&P 500 universe + SPY
# 2. Compute rolling up-beta and down-beta for each stock
# 3. Build feature matrix: momentum, size, B/M, intangibles (R&D/assets), volume
# 4. Train LightGBM to forecast next-month up-beta and down-beta separately
# 5. Score = predicted_up_beta - predicted_down_beta
# 6. Long top quintile, short bottom quintile; evaluate L-only variant too
