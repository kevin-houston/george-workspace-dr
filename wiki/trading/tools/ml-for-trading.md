---
updated: 2026-05-10
type: tool-guide
status: active — H167 FLAGGED; H176 QUEUED; H171 QUEUED
---

# Machine Learning for Trading — Library Guide

Practical reference for ML tools used in the quantitative trading pipeline. Covers gradient boosting for cross-sectional prediction, financial NLP models, factor analysis, and portfolio optimization. Directly relevant to H167 (LightGBM sector-neutral momentum), H176 (ModernFinBERT upgrade), H171 (GPT-4o-mini NLP), and future cross-sectional work.

**Related pages**: [NLP & Alternative Data](nlp-alternative-data.md) | [Walk-Forward & CPCV](../backtesting/walk-forward-cpcv.md) | [Position Sizing](../algorithms/position-sizing.md) | [Qlib Deep Dive](qlib.md)

---

## 1. Gradient Boosting for Cross-Sectional Prediction

The dominant approach for cross-sectional alpha factor modeling: rank stocks each period by a score from a gradient boosting model trained on lagged features, then go long top quintile / short bottom quintile.

### LightGBM — primary recommendation

- **GitHub**: [microsoft/LightGBM](https://github.com/microsoft/LightGBM) — 18.3k stars
- **Version**: v4.6.0 (Feb 2025) | **License**: MIT
- **Install**: `pip install lightgbm`
- **Speed**: 3–10× faster than XGBoost on large datasets; 30% less memory
- **Key advantage**: leaf-wise tree growth captures complex interactions; superior with high-cardinality features (sectors, factor ranks)

```python
import lightgbm as lgb
import pandas as pd

# Cross-sectional ranking pipeline
# features: lagged returns, momentum ranks, sector dummies
# target: 1-month forward return rank (not raw return — rank is more stable)

train = lgb.Dataset(X_train, label=y_train)
val   = lgb.Dataset(X_val, label=y_val, reference=train)

params = {
    "objective":    "regression",       # or "lambdarank" for ranking
    "metric":       "rmse",
    "num_leaves":   63,
    "learning_rate": 0.05,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq":  5,
    "verbose":      -1,
    "n_jobs":       -1,
}
model = lgb.train(
    params, train, num_boost_round=500,
    valid_sets=[val],
    callbacks=[lgb.early_stopping(50), lgb.log_evaluation(100)],
)

# Cross-sectional signal: rank predictions each period
df["lgbm_signal"] = df.groupby("date")["pred"].rank(pct=True)
# Long top quintile (>0.8), short bottom quintile (<0.2)
```

**Key parameters for finance**:
- `min_data_in_leaf=20` — prevents overfitting on thin sectors
- `lambda_l2=0.1` — L2 regularization (prevents memorizing individual stocks)
- `max_depth=6` — shallow trees generalize better cross-sectionally
- Use `objective="lambdarank"` if training directly on rank ordering (pairs loss)

### XGBoost

- **GitHub**: [dmlc/xgboost](https://github.com/dmlc/xgboost) — 28.4k stars
- **Version**: 3.2.0 (Feb 2026) | **License**: Apache 2.0
- **Install**: `pip install xgboost`
- Level-wise growth (safer on noisy financial data); slightly slower than LightGBM but more stable
- `xgb.XGBRegressor` is drop-in compatible with scikit-learn pipelines

### CatBoost

- **GitHub**: [catboost/catboost](https://github.com/catboost/catboost) — 8.9k stars
- **Install**: `pip install catboost`
- Best for datasets with native categorical features (sector codes, exchange) — no encoding needed
- `CatBoostRegressor(cat_features=["sector"])` — pass column names directly

### Reference implementation

**Stefan Jansen's ML4T repo** ([github.com/stefan-jansen/machine-learning-for-trading](https://github.com/stefan-jansen/machine-learning-for-trading)) — 150+ notebooks covering end-to-end pipeline from raw data → features → LightGBM → Alphalens evaluation → Zipline backtest. Chapter 12 (GBM), Chapter 6 (cross-sectional momentum) most relevant.

---

## 2. Financial NLP Models

### ModernFinBERT — current best-performing

- **HuggingFace**: `tabularisai/ModernFinBERT`
- **Downloads**: 33,925/month | **License**: Apache 2.0
- **Architecture**: ModernBERT-base (0.1B params) — modernized attention, 2024 architecture
- **Training**: Real + synthetic financial text with LLM-label correction; covers news, tweets, crypto, macro, earnings
- **Claimed lift**: 48% accuracy improvement over ProsusAI/finbert on diverse out-of-domain datasets
- **Directly relevant to**: H176 (queued upgrade from ProsusAI/finbert)

```python
from transformers import pipeline

classifier = pipeline("text-classification", model="tabularisai/ModernFinBERT")

results = classifier([
    "Strong quarterly earnings with 15% YoY growth",
    "Federal Reserve increases interest rates due to inflation",
    "Revenue missed consensus estimates by $200M",
])
# Returns: [{"label": "positive"/"negative"/"neutral", "score": float}, ...]
```

**Caveats**: The "48% improvement" claim is on their own benchmark mix — independent validation on our EDGAR 8-K corpus is needed (i.e., run H176 before trusting). ProsusAI/finbert is still the proven baseline (H163 CONFIRMED).

### ProsusAI/finbert — proven baseline

- **HuggingFace**: `ProsusAI/finbert` | 6.4M downloads/month
- See [NLP & Alternative Data](nlp-alternative-data.md) for full details
- **Use**: H163/H174 production pipeline; score range `positive_prob - negative_prob ∈ [-1, 1]`

### Other variants (2025)

| Model | HuggingFace | Notes |
|-------|-------------|-------|
| `clapAI/Fin-ModernBERT` | Latest ModernBERT variant (2025) | Very new, less validated |
| `yiyanghkust/finbert-tone` | Alt FinBERT fine-tune | Good on news headlines |
| `ProsusAI/finbert` | Proven production baseline | Use until H176 validates replacement |

---

## 3. Feature Engineering: Technical Indicators

### TA-Lib — 150+ indicators, fastest

- **GitHub**: [ta-lib/ta-lib-python](https://github.com/ta-lib/ta-lib-python) — 12k stars
- **Install**: `pip install TA-Lib` (note: requires C library; on Linux: `apt-get install libta-lib-dev`)
- **Speed**: 2–4× faster than pandas-ta for batch computation (Cython backend)
- **Python**: numpy arrays and DataFrames; 3.10–3.13 supported; numpy 2 support in v0.6+

```python
import talib
import numpy as np

# Function API (numpy arrays)
rsi   = talib.RSI(close, timeperiod=14)
macd, signal, hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
bbands_upper, bbands_mid, bbands_lower = talib.BBANDS(close, timeperiod=20)
atr   = talib.ATR(high, low, close, timeperiod=14)

# Pattern recognition (returns array of 0/±100/±200 signals)
engulfing = talib.CDLENGULFING(open_, high, low, close)
hammer    = talib.CDLHAMMER(open_, high, low, close)

# List all available functions
print(talib.get_functions())        # All 150+ function names
print(talib.get_function_groups())  # Grouped by category
```

**Coverage**: Overlap studies (SMA/EMA/BBANDS), Momentum (RSI/MACD/Stochastic/ADX/CCI/ROC), Volume (OBV/AD), Volatility (ATR/NATR), Cycle indicators (Hilbert transform), Pattern recognition (60+ candlestick patterns), Math operators.

### pandas-ta — easier API, DataFrame-native

- **GitHub**: [twopirllc/pandas-ta](https://github.com/twopirllc/pandas-ta) — high fork count (1.3k)
- **Install**: `pip install pandas_ta`
- 70+ indicators; all auto-append to DataFrame via `.ta` accessor

```python
import pandas_ta as ta

df.ta.rsi(length=14, append=True)       # Adds RSI_14 column
df.ta.macd(fast=12, slow=26, append=True)  # Adds MACD_12_26_9, MACDh_, MACDs_
df.ta.bbands(length=20, append=True)    # Adds BBL, BBM, BBU, BBB, BBP

# Bulk: run all indicators at once
df.ta.strategy(ta.AllStrategy)  # warning: slow, lots of columns
```

**Recommendation**: Use **TA-Lib** when performance matters (large universes, 5+ years of daily data); use **pandas-ta** for quick exploration on a single ticker. Both coexist fine in the same pipeline.

---

## 4. Alpha Factor Analysis: Alphalens-Reloaded

The standard tool for evaluating cross-sectional alpha factors before committing to a full backtest.

- **GitHub**: [stefan-jansen/alphalens-reloaded](https://github.com/stefan-jansen/alphalens-reloaded) — 586 stars (active maintained fork of the deprecated quantopian/alphalens)
- **Version**: 0.4.6 (June 2025) | **License**: Apache 2.0
- **Install**: `pip install alphalens-reloaded`
- **Docs**: [alphalens.ml4trading.io](https://alphalens.ml4trading.io/)

```python
import alphalens

# Inputs:
# - factor: pd.Series indexed by (date, asset) — your signal
# - prices: pd.DataFrame indexed by date, columns=tickers — forward prices

factor_data = alphalens.utils.get_clean_factor_and_forward_returns(
    factor=my_signal,     # pd.Series(index=[date, ticker], values=signal)
    prices=price_df,      # pd.DataFrame(index=date, columns=tickers)
    quantiles=5,          # quintile buckets
    periods=(1, 5, 20),   # forward return horizons (trading days)
    groupby=sector_map,   # optional: pd.Series(ticker → sector) for group analysis
)

# Full tear sheet (IC, returns, turnover, quantile analysis)
alphalens.tears.create_full_tear_sheet(factor_data)

# Component sheets
alphalens.tears.create_returns_tear_sheet(factor_data)       # quantile returns
alphalens.tears.create_information_tear_sheet(factor_data)   # IC / ICIR
alphalens.tears.create_turnover_tear_sheet(factor_data)      # monthly turnover
```

**Key metrics Alphalens reports**:
- **IC (Information Coefficient)**: Spearman rank correlation of signal with forward return. IC > 0.05 is meaningful; IC > 0.10 is strong.
- **ICIR (IC Information Ratio)**: IC mean / IC std. ICIR > 0.5 is publication-quality.
- **Quantile returns**: Long top quantile minus short bottom quantile return — the actual tradeable spread.
- **Turnover**: How much the top/bottom quintiles change per period — directly related to transaction costs.

**Workflow**: Use Alphalens to screen factor ideas before building a full backtest. A factor with IC < 0.03 or ICIR < 0.3 is unlikely to survive transaction costs — save the backtest effort.

---

## 5. Purged Cross-Validation (free alternative to mlfinlab)

**mlfinlab** (Hudson & Thames) is NOT open source — requires a commercial license despite appearing on PyPI. Use **skfolio** or **timeseriescv** instead for purged CV.

### skfolio CPCV (recommended)

- **GitHub**: [skfolio/skfolio](https://github.com/skfolio/skfolio) — 2k stars
- **Install**: `pip install skfolio`
- Includes `CombinatorialPurgedCV` — fully open-source sklearn-compatible implementation

```python
from skfolio.model_selection import CombinatorialPurgedCV, WalkForward
from sklearn.model_selection import cross_val_score

cv = CombinatorialPurgedCV(n_splits=5, n_test_splits=2, purged_size=0.02)

# Use with any sklearn estimator
scores = cross_val_score(lgbm_model, X, y, cv=cv, scoring="neg_mean_squared_error")
```

### timeseriescv (lightweight)

- **GitHub**: [MiguelAngelLV/timeseriescv](https://github.com/elephaint/timeseriescv) — 500+ stars
- **Install**: `pip install timeseriescv`
- Purged k-fold + embargo, minimal dependencies

```python
from timeseriescv import PurgedWalkForwardCV

cv = PurgedWalkForwardCV(n_splits=10, purge_gap=20)   # 20-day embargo
```

**Why purging matters**: standard k-fold on financial data leaks future information. If your label is a 20-day forward return, any training sample within 20 days of a test sample will contaminate the fold. Purging removes those samples; embargoing adds a buffer after the test window.

---

## 6. Portfolio Optimization: skfolio vs PyPortfolioOpt

### skfolio — advanced, sklearn-native

- **GitHub**: [skfolio/skfolio](https://github.com/skfolio/skfolio) — 2k stars | v0.20.1 (Apr 2026)
- 20+ risk measures (CVaR, drawdown, entropic, omega, sortino), sklearn pipeline integration, GroupConstraint, cardinality constraints, vine copulas for stress testing

```python
from skfolio import MeanRisk, RiskMeasure, Objective
from skfolio.optimization import HierarchicalRiskParity

# Mean-CVaR optimal portfolio
model = MeanRisk(
    risk_measure=RiskMeasure.CVAR,
    objective=Objective.MAXIMIZE_RATIO,
    portfolio_params=dict(name="MeanCVaR"),
)
model.fit(returns_train)
portfolio = model.predict(returns_test)
print(portfolio.summary())   # Sharpe, CVaR, MaxDD, etc.

# Hierarchical Risk Parity (robust, no covariance inversion)
hrp = HierarchicalRiskParity()
hrp.fit(returns_train)
```

### PyPortfolioOpt — simpler, widely used

- **GitHub**: [robertmartin8/PyPortfolioOpt](https://github.com/robertmartin8/PyPortfolioOpt) — 5.7k stars
- **Install**: `pip install pyportfolioopt`
- Faster for quick prototyping; Black-Litterman view incorporation; discrete allocation helper

```python
from pypfopt import EfficientFrontier, risk_models, expected_returns, HRPOpt

mu  = expected_returns.mean_historical_return(prices)
cov = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
ef  = EfficientFrontier(mu, cov, weight_bounds=(0, 0.15))
ef.max_sharpe()
weights = ef.clean_weights()
```

**When to use which**: skfolio for production systems and research (sklearn pipeline, CPCV-compatible); PyPortfolioOpt for quick allocation calculations or when you need Black-Litterman views.

---

## Pipeline Architecture

```
Raw Data (yfinance / Polygon / Alpaca)
  ↓
Feature Engineering
  ├── TA-Lib: 150+ technical indicators
  ├── Fundamental ratios (if available)
  └── NLP sentiment (ModernFinBERT / ProsusAI/finbert)
  ↓
Factor Screening
  └── Alphalens-Reloaded: IC, ICIR, quantile analysis
  ↓  (only proceed if IC > 0.03, ICIR > 0.3)
Model Training
  ├── LightGBM (primary — fast, handles cat features)
  ├── XGBoost (alternative — level-wise, more stable)
  └── PurgedCV (skfolio / timeseriescv — no data leakage)
  ↓
Signal Generation
  └── Cross-sectional rank of model predictions
  ↓
Portfolio Construction
  ├── Quintile long/short (simple)
  └── skfolio MeanRisk / HRP (sophisticated)
  ↓
Backtest Validation
  └── IS/OOS split, walk-forward, DSR confirmation
```

---

## Key gotchas

**Look-ahead in features**: TA-Lib functions are synchronous — `RSI(close)[-1]` at time `t` uses data through `t`. But if you compute features on the full series and then split, you haven't leaked future data. The danger is in pandas `.shift()` errors — always verify feature lag with `.head()` checks.

**Cross-sectional vs time-series**: LightGBM trained on cross-sectional data (one row per stock-date, target = forward return) generalizes better OOS than time-series LSTM models on monthly data. The cross-sectional structure means the model sees many stocks per training epoch, not just one stock's history.

**Feature normalization**: gradient boosting doesn't need normalization, but **cross-sectional rank normalization** (rank each feature within the cross-section on each date) removes survivorship bias and distributional shifts over time. Standard practice: `df.groupby("date")["feature"].rank(pct=True)`.

**mlfinlab is not free**: despite existing on PyPI, mlfinlab requires a commercial license from Hudson & Thames. The `pip install mlfinlab` will install but usage requires license agreement. Use skfolio for CPCV instead.

---

## Factor-Axis Tokenization: Self-Attention over Factor Space

**Source**: arXiv:2507.07107 (2025). "Machine Learning Enhanced Multi-Factor Quantitative Trading: A Cross-Sectional Portfolio Optimization Approach with Bias Correction."

**Core innovation**: Instead of feeding all factors as independent features into LightGBM/MLP, treat each factor as a *token* in a transformer sequence. Self-attention learns which factor combinations are predictive — effectively discovering interaction effects like:
- Momentum conditioned on low volatility → stronger signal
- Value conditioned on sector → avoids value traps in cyclicals
- Quality conditioned on earnings surprise → confirms fundamental shift

**Architecture sketch**:
```
Input: [F1, F2, ..., Fn]  # n factors for each stock
Tokenize: each factor → embedding vector (value + positional)
Transformer encoder: multi-head attention over factor tokens
Output: pooled representation → linear score
```

**Why this beats H188 (LightGBM)**:
- LightGBM learns interaction trees but only low-order (depth-limited)
- Transformer learns ALL pairwise factor interactions simultaneously
- Bias correction layer (novel addition) reduces overfitting on small cross-sections

**H194 implementation plan**:
1. Take H188's factor stack (momentum-12m, reversal-1m, vol, quality, value)
2. Build factor tokenization layer (linear projection per factor → 32-dim embedding)
3. 2-layer transformer encoder (4 heads, 32-dim)
4. Pooling → scalar score per stock
5. WFO same as H188 (IS 2014-2020, OOS 2021-2024)
6. Compare Sharpe vs H188 (baseline 1.07) and H191-C hybrid (1.110)

**Bias correction detail**: The paper adds a hold-out validation loss term that penalizes factor loadings that are inconsistent across sub-periods — reduces the tendency to overfit to whichever factor happened to work in the training window.

---

## STORM: Dual VQ-VAE Spatio-Temporal Factor Model

**Source**: arXiv:2412.09468 (2024). "STORM: A Spatio-Temporal Factor Model Based on Dual Vector Quantized Variational Autoencoders for Financial Trading." *WSDM '26* (Nineteenth ACM International Conference on Web Search and Data Mining, Feb 2026, Boise ID).

**Key idea**: Standard cross-sectional factor models assume factors are independent and globally stable. In reality, factors interact across time *and* across stocks. STORM captures both:

- **Time-series encoder** (LSTM): learns how each stock's factor exposures evolve through time
- **Cross-sectional encoder** (GNN / graph attention): learns how stock relationships (sector, correlation) affect factor loadings
- **Dual VQ-VAE**: each encoder outputs a discrete codebook vector, forcing factor representations to be distinct and reusable
  - Codebook commitment loss ensures representations don't collapse
  - Diversity loss ensures the two encoders don't converge to the same latent

**Why orthogonality matters**: In H188, LightGBM features include both momentum-12m and volatility. These are correlated but not orthogonal — the model wastes capacity on their overlap. VQ-VAE codebooks enforce orthogonality structurally.

**H195 plan**:
- Scope: same 30-stock universe as H188/H191/H192
- Implement STORM: LSTM time encoder (20-day lookback) + simple correlation GNN (no sector labels needed)
- Dual VQ-VAE with 64-vector codebook each
- Output: combined latent → linear rank score per stock
- WFO: IS 2015-2021, OOS 2022-2024
- Baseline: H188 (Sharpe 1.07), target H195 > 1.2

**Complexity note**: Requires PyTorch (~2 days to implement cleanly). Approved for immediate build (Kevin, 2026-05-13).
