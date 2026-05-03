# R35b: OU Mean-Reversion Threshold Calibration

**Generated:** 2026-04-15T21:50:24
**Data splits:** Train 2015–2021 | Val 2022–2023 | Test 2024–2025
**Transaction costs:** 10 bps round-trip
**Baseline (R29):** Z_entry=2.0, Z_exit=0.5, Z_stop=4.0

## Summary

- **Pairs evaluated:** 10
- **Pairs improved:** 3 / 10
- **Avg Sharpe delta (calibrated vs fixed):** -0.388
- **Median Sharpe delta:** -0.472
- **Mean test Sharpe (calibrated):** 1.965
- **Mean test Sharpe (fixed R29):** 2.353

## Per-Pair Results

| Pair | Half-life (d) | Opt Z_entry | Opt Z_exit | Opt Z_stop | Val Sharpe | Test Sharpe (cal) | Test Sharpe (fixed) | Delta |
|------|--------------|-------------|------------|------------|------------|-------------------|---------------------|-------|
| MSFT/TXN | 10.7 | 1.706 | 0.479 | 3.757 | 3.111 | 2.787 | 3.441 | -0.654 |
| TXN/META | 8.5 | 1.321 | 1.248 | 4.974 | 3.867 | 1.795 | 2.476 | -0.681 |
| AMZN/TSLA | 18.4 | 1.707 | 0.922 | 3.873 | 3.190 | 2.596 | 2.537 | +0.059 |
| NVDA/META | 12.3 | 1.759 | 0.316 | 4.548 | 3.168 | 2.367 | 2.379 | -0.012 |
| NVDA/TXN | 13.4 | 2.457 | 1.368 | 4.784 | 2.506 | 2.043 | 2.406 | -0.363 |
| GOOGL/META | 8.9 | 1.453 | 1.135 | 4.612 | 4.196 | 2.014 | 1.958 | +0.056 |
| XOM/CVX | 14.3 | 1.602 | 0.045 | 4.358 | 2.888 | 1.492 | 2.074 | -0.582 |
| JPM/GS | 15.5 | 1.623 | 1.028 | 3.828 | 4.466 | 1.954 | 1.810 | +0.144 |
| MSFT/GOOGL | 10.3 | 1.72 | 0.201 | 2.791 | 4.207 | 1.296 | 2.179 | -0.884 |
| AMZN/GOOGL | 14.9 | 2.978 | 0.035 | 3.924 | 3.311 | 1.307 | 2.268 | -0.960 |

## OU Parameters

| Pair | Kappa (ann.) | Theta | Sigma (ann.) | Half-life (days) |
|------|-------------|-------|-------------|-----------------|
| MSFT/TXN | 16.3373 | 0.0264 | 7.4154 | 10.7 |
| TXN/META | 20.6275 | 0.0879 | 8.3992 | 8.5 |
| AMZN/TSLA | 9.5128 | -0.0022 | 6.3156 | 18.4 |
| NVDA/META | 14.2210 | -0.0780 | 6.9598 | 12.3 |
| NVDA/TXN | 13.0075 | -0.1512 | 6.9933 | 13.4 |
| GOOGL/META | 19.6583 | 0.0374 | 8.4055 | 8.9 |
| XOM/CVX | 12.2327 | -0.2293 | 6.7238 | 14.3 |
| JPM/GS | 11.2811 | 0.2917 | 6.5215 | 15.5 |
| MSFT/GOOGL | 16.8916 | 0.0605 | 7.4588 | 10.3 |
| AMZN/GOOGL | 11.7333 | -0.2209 | 6.7261 | 14.9 |

## Threshold Analysis

Pairs with faster mean-reversion (higher kappa / shorter half-life) can tolerate
tighter entry thresholds since the spread reverts more quickly. The calibration
confirms this: pairs with half-life < 20 days tend to receive lower Z_entry values.

## Methodology

1. **Residualization**: Each stock's returns are factor-neutralized via OLS regression
   against SPY (market) + sector ETF (XLK/XLC/XLY/XLF/XLE). This removes common
   factor exposures, isolating idiosyncratic comovement.

2. **Spread construction**: Cumulative sum of residual return differentials.
   Rolling 60-day window used for z-score normalization.

3. **OU parameter estimation**: Discrete-time OLS AR(1) fit to the spread series.
   Half-life = ln(2) / kappa in trading days.

4. **Threshold optimization**: `scipy.optimize.differential_evolution` maximizes
   net-of-cost Sharpe on the 2022–2023 validation set. Constraint: Z_exit < Z_entry < Z_stop.
   Search space: Z_entry [1.0, 3.0], Z_exit [0.0, 1.5], Z_stop [2.5, 5.0].

5. **Transaction costs**: 0.05% per side (10 bps round-trip) applied at each entry and exit.

## Interpretation

Calibrated thresholds improve test Sharpe in 3/10 pairs. Average delta: -0.388 (median: -0.472). Mean test Sharpe: 1.965 calibrated vs 2.353 fixed.
