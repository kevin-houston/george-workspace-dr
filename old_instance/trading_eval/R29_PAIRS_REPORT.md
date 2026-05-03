# Round 29 — Equity Pairs Trading: Factor Residualization + OU Thresholds

**Date:** 2026-04-11
**Period:** 2020-01-01 to 2025-12-31
**Universe:** 25 Fortune 100 stocks

---

## Results Table (Portfolio-Level)

| Variant | Description | Sharpe | CAGR | Max Drawdown | Pairs |
|---------|-------------|--------|------|--------------|-------|
| Baseline | Raw returns + fixed ±2σ z-score | 0.4358 | 3.31% | -9.72% | 1 |
| R29 v1 | Residualized returns + fixed ±2σ | 1.3802 | 10.57% | -8.35% | 10 |
| R29 v2 (Full) | Residualized + OU thresholds | 0.9138 | 8.91% | -18.56% | 10 |
| **R23 (previous best)** | Multi-pair book | **0.9640** | — | — | 10 |

---

## Key Questions

### Does factor residualization help?
**YES — factor residualization improves Sharpe**
- Baseline Sharpe: 0.4358
- R29 v1 Sharpe:  1.3802
- Lift from residualization: +0.9444

### Does OU calibration improve over fixed thresholds?
**NO improvement from OU calibration**
- R29 v1 (fixed ±2σ) Sharpe: 1.3802
- R29 v2 (OU thresholds) Sharpe: 0.9138
- Lift from OU calibration: -0.4664

### Comparison to leaderboard (R23: Sharpe 0.964)
R29 v2 BELOW R23 benchmark: **0.9138** vs 0.9640
Total lift over baseline: +0.4780

---

## Top 5 Pairs by Sharpe

| Pair | Variant | Sector | Sharpe | CAGR | Max Drawdown | Trades | Avg Hold (days) |
|------|---------|--------|--------|------|--------------|--------|-----------------|
| MSFT/TXN | r29v1 | tech | 0.7906 | 12.04% | -27.79% | 24 | 15.4 |
| TXN/META | r29v1 | tech | 0.7400 | 13.45% | -23.61% | 20 | 20.9 |
| AMZN/TSLA | r29v2 | consumer_d | 0.7343 | 24.75% | -43.81% | 95 | 7.4 |
| NVDA/META | r29v1 | tech | 0.6808 | 16.11% | -51.84% | 23 | 20.6 |
| AMZN/TSLA | r29v1 | consumer_d | 0.6056 | 15.89% | -27.12% | 24 | 18.6 |

---

## Cointegrated Pairs Count

| Variant | Cointegrated Pairs Found |
|---------|--------------------------|
| Baseline | 1 |
| R29 v1 | 19 |
| R29 v2 | 17 |

---

## Methodology Notes

- **Stage 0**: Rolling 60-day OLS on (SPY returns, sector ETF returns) for each stock; residuals used as factor-orthogonalized returns
- **Stage 1**: Engle-Granger cointegration test (p < 0.05) applied to residual-price series
- **Stage 2**: OU MLE fitting (theta, mu, sigma) via discrete-time L-BFGS-B; half-life determines entry threshold multiplier
  - half_life < 3d → entry ±1.5σ_eq
  - half_life 3–7d → entry ±2.0σ_eq
  - half_life > 7d → entry ±2.5σ_eq
  - Skip if half_life > 30d (too slow)
- **Stage 3**: Long/short spread execution with stop at ±3σ_eq; OU re-fit every 60 days; portfolio = equal-weight top 10 pairs

---

## Leaderboard Update

| Round | Strategy | Sharpe | Notes |
|-------|----------|--------|-------|
| R27 | Div Raise ≥10% hold-40d | 4.403 | Best overall |
| R27 | Div Raise ≥5% hold-40d | 3.400 | |
| R29 v2 (this) | Pairs + Residualization + OU | 0.9138 | Full pipeline |
| R29 v1 | Pairs + Residualization | 1.3802 | |
| R23 | Multi-pair stat arb book | 0.964 | Previous pairs best |
| R29 Baseline | Raw pairs + fixed ±2σ | 0.4358 | |

*Data source: Yahoo Finance via yfinance. Transaction costs: 2 bps per leg.*
