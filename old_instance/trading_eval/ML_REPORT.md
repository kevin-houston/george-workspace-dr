# ML Trading Strategies Report
Date: 2026-03-30
Universe: 20 large-cap stocks (Fortune 100)
Models: XGBoost, Random Forest, Logistic Regression, Gradient Boosting, Ensemble
Backtests: Walk-forward validation, 252d train / 21d test windows, 5-year data

---

## Summary

ML models produce real but modest alpha over price-signal rules. Best single result: Random Forest on XOM, Sharpe +1.744. Average Sharpe across all models ~0.297-0.527. Models beat buy-and-hold on only 20-35% of stock/model combinations — the bull market 2020-2025 is a high bar.

---

## Model Rankings (Average Sharpe across 20 stocks)

| Model              | Avg Sharpe | Beat Buy-and-Hold % |
|--------------------|------------|---------------------|
| Ensemble (avg all) | +0.527     | 25%                 |
| Random Forest      | +0.518     | 35%                 |
| XGBoost            | +0.497     | 35%                 |
| Gradient Boosting  | +0.448     | 30%                 |
| Logistic Regression| +0.297     | 20%                 |

---

## Top 5 Individual Results

| Model           | Symbol | Sharpe | Win Rate | N Trades |
|-----------------|--------|--------|----------|----------|
| Random Forest   | XOM    | +1.744 | 61.1%    | 599      |
| Ensemble        | WMT    | +1.502 | 60.7%    | 803      |
| Logistic        | WMT    | +1.471 | 59.8%    | 743      |
| Logistic        | PG     | +1.452 | 58.0%    | 738      |
| Gradient Boost  | XOM    | +1.392 | 58.0%    | 890      |

Key observation: Energy (XOM) and defensive/consumer staples (WMT, PG) work best. These sectors have more predictable mean-reverting behavior. High-volatility tech (NVDA, META) is harder to predict — noise drowns out features.

---

## Top Predictive Features (XGBoost importance ranking)

1. vol_20d — 20-day volatility (most important)
2. close/SMA60 — price relative to 60-day MA
3. RSI_14 — standard RSI
4. close/SMA200 — long-term trend position
5. ret_20d — 20-day return (momentum)
6. RSI_28 — longer RSI
7. vol_10d — short-term volatility
8. close/SMA20 — short-term MA position
9. spy_20d_ret — market regime proxy
10. ret_10d — 10-day return

Interpretation: Volatility regime + trend position are most predictive. Not surprising — mean reversion signals (high vol + extended price) are what the model is learning.

---

## Key Findings

### 1. ML adds modest but real edge
Average Sharpe of 0.5 is meaningful — comparable to a good traditional signal. But it's not magic. The models are essentially learning to systematize mean-reversion and momentum rules.

### 2. Ensemble > any single model
Averaging all 4 model predictions gives the best average Sharpe (0.527). No single model dominates consistently — ensembling is the right approach.

### 3. Bull market makes buy-and-hold hard to beat
Beating a 13% CAGR SPY from 2020-2025 is genuinely difficult. The 35% beat rate for XGBoost/Random Forest is respectable given the base rate.

### 4. Feature engineering matters more than model choice
XGBoost vs Random Forest vs GBM produces similar results. The features (vol regime, trend position, RSI) do the heavy lifting. A logistic regression with the same features captures 60% of the ML edge.

### 5. Energy and staples outperform tech for ML
XOM Random Forest Sharpe 1.744. WMT Ensemble Sharpe 1.502. NVDA Sharpe ~0.15 (noise-dominated). The paradox: high-vol growth stocks are "exciting" but too random for ML; boring value stocks have better signal-to-noise.

---

## What Doesn't Work

- Short signals from ML: consistently worse than long signals (asymmetric market)
- LSTM not tested (requires GPU for meaningful performance, too slow on CPU)
- Overfitting risk: results on out-of-sample windows but still within a single bull market regime
- Transaction costs not included — high-frequency signals would be eroded by costs

---

## Comparison to Other Strategies

| Strategy            | Sharpe | Notes                          |
|---------------------|--------|--------------------------------|
| Best ML individual  | +1.744 | RF on XOM                      |
| ML ensemble avg     | +0.527 | Average across 20 stocks       |
| PEAD (gap 5%, 20d)  | +1.137 | Much simpler, higher Sharpe    |
| Pairs portfolio     | +0.964 | Market neutral, lower DD       |
| Crypto momentum     | +1.682 | Higher CAGR, extreme DD        |

ML is competitive but PEAD beats it with less complexity. The value of ML is in combining signals — a future enhancement would be to use ML to time entries on the best traditional strategies (pairs, PEAD, seasonal).
