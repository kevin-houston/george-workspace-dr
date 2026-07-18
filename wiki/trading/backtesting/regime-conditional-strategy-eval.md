---
title: Regime-Conditional Distributional Strategy Evaluation — GAMLSS/ZAGA Framework
tags: backtesting, regime-detection, statistical-testing, walk-forward
added: 2026-07-17
source: arXiv:2606.31251
category: Backtesting
---

# Regime-Conditional Distributional Strategy Evaluation — GAMLSS/ZAGA Framework

**Paper:** Ozimek (2026), arXiv:2606.31251, submitted June 30 2026.
**Key insight:** Comparing two strategies by a single backtest-period Sharpe discards all information about *how* performance varies with market conditions. This paper proposes replacing point-metric comparison with distributional comparison conditioned on regime covariates.

---

## The Problem with Conventional Strategy Comparison

Standard practice:
1. Run walk-forward backtest → compute Sharpe, CAGR, MaxDD over the full test period
2. Compare two strategies: if Strategy A's Sharpe > Strategy B's Sharpe, prefer A

**What this misses:**
- Strategy A may dominate in low-volatility regimes but catastrophically underperform in high-volatility regimes
- Strategy B may have lower average performance but more consistent performance across regimes
- For portfolio construction, the correlation of performance with regime matters as much as the level

---

## The GAMLSS/ZAGA Approach

### Walk-Forward Design
The paper runs **146 walk-forward out-of-sample folds** on the S&P 500 (2002–2025). Each fold produces one Adjusted Information Ratio (IR*) observation for each strategy.

**Adjusted Information Ratio (IR*):** A Sharpe-like metric normalized by benchmark performance. Defined so IR* > 0 means the strategy beats the benchmark in that fold.

### The Statistical Model
The 146 IR* observations are modelled as draws from a **Zero-Adjusted Gamma (ZAGA)** distribution — a mixed distribution:
- Mass at zero (strategy ties the benchmark exactly)
- Gamma-distributed positive tail (strategy beats benchmark by a continuous amount)
- The mass-at-zero probability and the Gamma shape/scale are both functions of regime covariates

**GAMLSS** (Generalised Additive Model for Location, Scale and Shape) fits this joint distribution:
```
IR*(fold_t) ~ ZAGA(mu=f1(volatility_t, momentum_t), sigma=f2(volatility_t, momentum_t), nu=f3(...))
```

**Regime covariates used:**
- Realised volatility (20-day RV of S&P 500 returns)
- Cumulative market momentum (12-month SPY total return)

---

## Key Results

### SVMP vs. Buy-and-Hold
The paper tests a polynomial Support Vector Machine strategy (SVMP) against buy-and-hold (BH).

**Aggregated summary:**
- SVMP beats BH in many folds
- But the dominance relationship is **highly regime-conditional**:
  - Low volatility + positive momentum: SVMP significantly outperforms BH (ΔE > 0, significant)
  - High volatility + negative momentum (bear markets): BH matches or outperforms SVMP

**At six representative regime points:**
| Volatility | Momentum | SVMP vs BH (ΔE) | Variance ratio |
|---|---|---|---|
| Low | Positive | +0.28 (sig) | BH more variable |
| Low | Neutral | +0.12 (sig) | Similar |
| Low | Negative | +0.05 (ns) | SVMP more variable |
| High | Positive | -0.03 (ns) | BH more stable |
| High | Neutral | -0.11 (sig) | BH more stable |
| High | Negative | -0.19 (sig) | Both volatile |

---

## Connection to George's Research

### Backtesting Methodology Upgrade
The GAMLSS/ZAGA framework is a rigorous extension of the [Regime Detection Signals](regime-detection-signals.md) work. Instead of just checking "does the strategy pass gate VIX<25?", it models the full distribution of performance across regime states.

Practical benefit for the [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md):
- Add regime-conditional distribution test as Step 8: "Does the strategy show consistent positive IR* across both bull and bear regimes in walk-forward folds?"
- Strategies that only work in low-vol bull markets (possible artifact) should be flagged even if aggregate OOS Sharpe passes the gate

### Walk-Forward Fold Count
The paper uses 146 folds (2002–2025). This is substantially more than our typical 5–10 walk-forward windows. For monthly strategies on a 20-year history, 146 folds means:
- Each fold tests ~1–2 months
- This is feasible only with frequent rebalancing (daily/weekly strategies)
- For **monthly ETF rotation** (H026/H045/H041a): only 20×12 = 240 months available; with 18-month IS minimum, ~100–120 valid monthly folds — marginal but workable

### H249: Regime-Conditional Portfolio Weights
**H249 CONFIRMED** (regime-conditional portfolio weights, OOS Sharpe +0.282 improvement). The GAMLSS/ZAGA framework provides a formal statistical test of whether H249's improvement is regime-uniform or regime-specific. If the improvement only exists in low-vol regimes, production reliance on it in high-vol regimes is unjustified.

---

## Practical Implementation

```python
import statsmodels.formula.api as smf
from statsmodels.genmod import gamlss
import pandas as pd
import numpy as np

# Assume: wf_results = DataFrame with columns [ir_star, vix_20d, mom_12m]
# ir_star > 0 = strategy beat benchmark in this fold

# Step 1: Compute regime covariates
wf_results['rv20'] = wf_results['strategy_returns'].rolling(20).std() * np.sqrt(252)
wf_results['mom12'] = wf_results['benchmark_price'].pct_change(252)

# Step 2: Model IR* distribution (simplified logistic regression for prob>0)
from sklearn.linear_model import LogisticRegression
X = wf_results[['rv20','mom12']]
y = (wf_results['ir_star'] > 0).astype(int)
lr = LogisticRegression().fit(X, y)

# Step 3: For regime-specific expected IR*, subset folds
bull_folds = wf_results[(wf_results['rv20']<0.15) & (wf_results['mom12']>0)]
bear_folds = wf_results[(wf_results['rv20']>0.25) & (wf_results['mom12']<0)]

print(f'Bull regime mean IR*: {bull_folds.ir_star.mean():.3f}')
print(f'Bear regime mean IR*: {bear_folds.ir_star.mean():.3f}')
```

Full GAMLSS in R: `library(gamlss); fit <- gamlss(ir_star ~ cs(rv20) + cs(mom12), data=wf_df, family=ZAGA)`

---

## Relationship to Existing Backtesting Framework

| Existing page | Connection |
|---|---|
| [Walk-Forward & CPCV](walk-forward-cpcv.md) | GAMLSS/ZAGA uses walk-forward folds as raw data |
| [Regime Detection Signals](regime-detection-signals.md) | Covariates: VIX/vol + SPY momentum = same variables already used |
| [Multiple Testing & Statistical Significance](multiple-testing.md) | ZAGA replaces single t-test with distributional test |
| [Shared Eval Checklist](../shared-eval-checklist.md) | Add regime-distributional check as Step 8 |
| [Signal Half-Life](signal-halflife.md) | Half-life varies by regime — GAMLSS can model this |

---

## Cross-references

- [Walk-Forward & CPCV](walk-forward-cpcv.md) — walk-forward framework; CPCV purging
- [Regime Detection Signals — Practical Data Guide](regime-detection-signals.md) — covariate definitions (VIX, SPY 200MA)
- [Multiple Testing & Statistical Significance](multiple-testing.md) — distributional tests vs point estimates
- [Regime Detection](../algorithms/regime-detection.md) — HMM, SJM, VIX threshold methods
- [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md) — production gate framework
- [Backtesting Design Principles](design-principles.md) — IS/OOS framework, bias taxonomy
