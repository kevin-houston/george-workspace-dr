---
updated: 2026-05-26
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


---

## MASFIN: Multi-Agent Debate Framework for Financial Decision-Making

**Source**: arXiv:2512.21878 (Dec 2024). "MASFIN: A Multi-Agent System for Financial Investment."

### Architecture

MASFIN coordinates 4 specialized agents in a structured debate before each trading decision:

```
Input: stock + catalyst (earnings, news, etc.)

→ Bull Analyst Agent: generates positive thesis + supporting evidence
→ Bear Analyst Agent: generates counter-thesis + risk factors  
→ Risk Manager Agent: stress-tests both theses against historical analogs
→ Portfolio Allocator Agent: sizes position given thesis strength + risk budget
```

Each agent has access to:
- Relevant news/8-K text (via RAG over recent filings)
- Historical price context (52-week range, recent volatility)
- Sector comparables (how similar stocks reacted to similar catalysts)

### Benchmark Results vs. Single-Agent Baseline

| Metric | Single LLM | MASFIN (debate) | Improvement |
|--------|-----------|-----------------|-------------|
| OOS Sharpe | 0.71 | 0.94 | +32% |
| Max Drawdown | -28.3% | -19.5% | −31% |
| Win rate | 52% | 58% | +6pp |
| Avg position hold | 4.2 days | 3.8 days | shorter |

The drawdown improvement is the headline finding — the bear analyst consistently catches "fake" earnings beats where positive surprise is priced in or driven by one-time items.

### Application Pattern for H174 (PEAD Pipeline)

The MASFIN debate pattern could be added as a pre-filter layer before the H174 PEAD score triggers an OPG order:

1. **Existing pipeline**: 8-K detected → FinBERT scores sentiment → if score > threshold → place OPG order
2. **MASFIN upgrade**: 8-K detected → FinBERT scores → if score > threshold → **run bull/bear debate** → reduce position size if bear wins → place order

This is a `high` risk change to existing live pipeline — do not apply without Kevin review. File as future upgrade path.

### Implementation Note

MASFIN agents communicate via structured JSON (thesis: str, evidence: List[str], confidence: 0.0-1.0). A lightweight implementation using GPT-4o-mini (cost-effective for short financial texts) with 2 agents (bull + skeptic) rather than 4 would capture ~80% of the drawdown benefit at lower API cost.

## Multi-agent LLM with fine-grained task decomposition (arXiv:2602.23330, Feb 2026)

**Authors**: Miyazaki, Kawahara, Roberts, Zohren

Key finding: decomposing trading analysis into fine-grained specialist agents (separate agents for fundamental analysis, sentiment, technical analysis, risk management) significantly outperforms coarse-grained multi-agent designs. Critical driver is alignment between agent output format and downstream decision-maker's input expectations.

- Tested on Japanese equities with prices, financials, news, macro data
- Portfolio construction exploits low correlation with index + cross-agent variance
- Implication for our pipeline: adding a fine-grained LLM overlay *above* confirmed quant signals (H026, BAB, MOM) rather than replacing them could yield compounding alpha. H202+ territory.

Companion paper arXiv:2412.20138 (TradingAgents) shows ≥23.21% cumulative return, 24.90% annual return, +6.1% vs best baseline on three stocks using Bull/Bear researcher agents + risk management team.

---

## H202-XL: Gradient Boosting on Large Universe (200–500 stocks) — 2025–2026 Support

Three 2025–2026 papers collectively support expanding H202 XGBoost momentum from 30 to 200+ stocks.

**arXiv:2507.07107 (Du 2025)** — ML multi-factor cross-sectional on 500–1000 Chinese A-shares using gradient boosting + bias correction + cross-sectional neutralization: annualized return 20%, Sharpe >2.0. Key techniques: tensor-accelerated factor computation and geometric Brownian motion data augmentation to compensate for limited in-sample periods. Relevant to H202-XL: sector-neutral cross-sectional ranking is essential on large universes.

**arXiv:2511.12129 (Yang et al., Nov 2025)** — practical ML stock recommendation on S&P 500 top-20% selection using gradient boosted regression (among 5 methods), outperforming buy-and-hold on Sharpe and cumulative returns. Confirms gradient boosting is competitive vs linear methods on large universes (500 stocks).

**arXiv:2602.00196 (Rasekhschaffe, Jan 2026)** — Generative AI with gradient-boosted tabular models delivers Sharpe 1.14–1.63 on US equities. Critical finding: **cross-sectional standardization is essential** — equity prediction is fundamentally about relative stock positioning, not absolute values. Implementation: use `df.groupby("date")["feature"].rank(pct=True)` per-feature, per-date.

**H202-XL design implications** (staged 2026-05-18):
- Expand from 30-stock to 200-stock S&P 500 midcap-filtered universe (yfinance)
- Add cross-sectional rank normalization per Rasekhschaffe 2026
- Run sector-neutral version (rank within GICS, per Du 2025 neutralization)
- Test with and without bias-correction term
- H202 30-stock showed XGBoost +0.104 Sharpe OOS vs simple rank; larger universe should yield substantially more signal
- Queue H202-XL after H205 results are confirmed

---

## QuantaAlpha — Evolutionary LLM Alpha Mining (arXiv:2602.07085, 2026)

**Source**: arxiv.org/abs/2602.07085

LLM-driven closed-loop alpha factor discovery using evolutionary optimization. Each mining iteration is a trajectory; underperforming steps are localized and revised through "trajectory-level mutation and crossover" while maintaining semantic consistency between hypothesis, factor expression, and executable code.

**Results (CSI 300 universe, backtested)**:
- Information Coefficient (IC): **0.0472**
- Annual Return Rate: **4.68%**  
- Maximum Drawdown: **11.8%**
- Transfer to CSI 500: **40.28% cumulative excess** over 4 years
- Transfer to S&P 500: **19.1% cumulative excess** over 4 years

**Relevance**: Factors mined on one market transfer to others — suggests the discovered alphas are structural, not overfitted. CSI 300/500 results are Chinese market; S&P 500 transfer is the key proof of generality. The IC of 0.0472 is very strong (typical good factors: 0.02–0.04).

**Connection to our pipeline**: QuantaAlpha automates what we do manually in the dream cycle — scan for hypotheses, generate code, evaluate, iterate. The evolutionary approach applied to our 30-stock universe with our confirmed signal types (alpha101, reversal, momentum) could discover novel factor combinations. H209 (AlphaCrafter) is the closest analog in our queue.

---

## QuantEvolve — Multi-Agent Evolutionary Strategy Discovery (arXiv:2510.18569, 2025)

**Source**: arxiv.org/abs/2510.18569 (oral, ACM ICAIF 2025)

Combines quality-diversity optimization with hypothesis-driven multi-agent strategy generation. Maintains a feature map aligned with investor preferences (strategy type, risk profile, turnover, return characteristics) to ensure diverse coverage of the strategy space.

**Key innovation**: "Quality-diversity" means the framework doesn't just find the best strategy — it finds a *diverse set of good strategies* that cover different return profiles, correlations, and risk characteristics. Directly useful for portfolio construction (we want H181+H192+H198+H217 to be uncorrelated — quality-diversity optimization formalizes this).

**Relevance**: The quality-diversity framing matches our portfolio construction goal exactly. When adding H221/H222 to the portfolio, we care about both performance AND low correlation with existing strategies. QuantEvolve's approach would explicitly optimize for this.

## 2026 multi-agent LLM frameworks

### TradingAgents (UCLA/MIT, 2025)
- GitHub: https://github.com/TauricResearch/TradingAgents
- 7 specialized agent roles: fundamental analyst, sentiment expert, technical analyst, trader, risk manager (+ research debate layer)
- Outperformed 5 rule-based baselines by 6–25% cumulative return on 3-month backtest (Jan–Mar 2024, US tech stocks)
- Caveat: 3-month backtest is too short to be conclusive — treat as proof-of-concept framework

### Fine-Grained Task Decomposition (Miyazaki & Kawahara, Feb 2026)
- arXiv:2602.23330 — tested on Japanese stocks with price, financials, news, macro data
- Key finding: fine-grained task decomposition (explicit sub-tasks per agent) >> coarse-grained instructions
- **Critical insight:** alignment between intermediate agent analytical outputs and downstream portfolio manager preferences drives performance — not just the final signal
- Portfolio optimization exploiting low cross-agent correlation achieves further gains
- Design principle for any multi-agent overlay: decompose to concrete measurable tasks, not abstract mandates

---

## Council of High Intelligence (0xNyk, 2025)

**GitHub**: https://github.com/0xNyk/council-of-high-intelligence — 787 stars, 81 forks | **License**: CC0

Shell-based multi-agent deliberation framework using 18 AI personas with structured debate mechanics. Designed for decisions that benefit from adversarial stress-testing and diverse analytical lenses.

### Personas
18 archetypes across philosophy, science, and finance: Aristotle, Socrates, Confucius, Feynman, Turing, Shannon, Kahneman, Taleb, Karpathy, Sutskever, Nakamoto, Hamilton, and others. Each persona has a fixed reasoning style (e.g. Kahneman = dual-system bias lens, Taleb = tail-risk / fragility focus).

### Modes
| Mode | Rounds | Members | Use case |
|------|--------|---------|----------|
| Full | 3 rounds | All 18 | High-stakes decisions requiring max coverage |
| Quick | 2 rounds | All 18 | Standard analysis |
| Duo | 2 rounds | 2 chosen | Rapid dialectic on a specific tension |

### Anti-groupthink mechanics
- **Dissent quotas**: minimum number of personas must disagree with the emerging consensus each round
- **Novelty gates**: contributions that merely rephrase prior points are filtered out
- **Anti-recursion**: prevents circular reasoning loops
- **Verdict leads with uncertainties**: final output explicitly names what the council doesn't know

### Multi-provider routing
Auto-routes across Claude, OpenAI, Gemini, Ollama, NVIDIA NIM based on availability and task type. Allows mixing local (Ollama) and API-based models per session.

### 20 pre-built domain triads
Curated 3-persona subsets optimized for specific domains: `architecture`, `ai-safety`, `financial-analysis`, `risk-assessment`, `strategy`, etc. Triads select complementary reasoning styles rather than random sampling.

### Claude Code integration
Native `/council` slash command installs to Claude Code: `./install.sh` from repo root. Invoked as `/council [question]` directly in a Claude Code session — no context-switching needed.

### Relevance to trading workflow
- **Hypothesis stress-testing**: run a council session before committing a new hypothesis to the queue — Taleb will probe tail risks, Kahneman will surface cognitive biases in the backtest design, Shannon will check information-theoretic assumptions
- **Portfolio allocation decisions**: before live deployment, Full mode across a position sizing / strategy blend question
- **H-queue prioritization**: Duo mode (Aristotle + Feynman) for "should we run H222-full before H227?" type trade-off calls
- **Practical note**: 3-round Full mode with 18 personas is expensive — reserve for decisions where the stakes justify it; use Duo or Quick for routine judgment calls

## QuantaAlpha — Evolutionary LLM Alpha Factor Mining (arXiv:2602.07085, Feb 2026)

**GitHub:** https://github.com/QuantaAlpha/QuantaAlpha (981 stars, MIT, actively maintained)  
**Paper:** arXiv:2602.07085 — "QuantaAlpha: An Evolutionary Framework for LLM-Driven Alpha Mining"  
**Authors:** Prof. Liwen Zhang et al., Shanghai University of Finance and Economics  

### What it does
Automates alpha factor discovery by combining LLM code generation with evolutionary strategies:
1. LLM proposes new factor expressions from a research direction prompt
2. Each run is a "trajectory" — the system identifies low-reward steps and applies mutation/crossover
3. Semantic consistency is enforced between hypothesis, factor code, and backtest result
4. Complexity constraints prevent crowded/redundant factors

### Results
| Metric | CSI 300 (with GPT-5.2) | S&P 500 (transfer) |
|--------|------------------------|---------------------|
| IC | 0.1501 | — |
| ARR | 27.75% | ~19.1% cumulative excess return over 4yr |
| MDD | 7.98% | — |
| Calmar | 3.48 | — |

### Installation (our environment)
```bash
git clone https://github.com/QuantaAlpha/QuantaAlpha.git
conda create -n quantaalpha python=3.10 && conda activate quantaalpha
SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0 pip install -e .
pip install -r requirements.txt

# Download Qlib data (~500MB)
huggingface-cli download QuantaAlpha/qlib_csi300 --repo-type dataset

# Run with our API key
export OPENAI_API_KEY=$OPENAI_API_KEY
./run.sh "Cross-sectional OHLCV price efficiency signals for US large-cap equities"
```

### H236 design
Proposed hypothesis: Run QuantaAlpha on our 30-stock (or 107-stock H234 universe) for 3 evolutionary iterations. Evaluate IC and OOS Sharpe vs H217 baseline (1.559). Use `CHAT_MODEL=gpt-4o` (cost-efficient).
- **Confirm threshold:** OOS Sharpe > 1.6 (beat H217) OR IC > 0.08 on US large-cap
- **Script:** `backtesting/daily/run_h236.py`
- **Prerequisites:** Qlib data download, conda environment setup
- **Cost estimate:** ~$2-5 in OpenAI API credits per mining run (3 iterations)

### Comparison to H209 (AlphaCrafter)
AlphaCrafter (arXiv:2605.05580, queued H209) is a similar LLM alpha mining framework but focused on end-to-end portfolio construction. QuantaAlpha is narrower (factor expression only) and has cleaner open-source implementation. Run QuantaAlpha first since it requires less infrastructure.

**Related:** [Factor Models & Cross-Sectional Alpha](../algorithms/factor-models.md), [WorldQuant 101 Alphas](../algorithms/alpha101-overlap.md), H217 (current best cross-sectional), H209 (AlphaCrafter, queued)


---

## AlphaAgent: LLM Alpha Mining with Anti-Crowding Regularization (2025)

**Source:** arXiv:2502.16789 — Tang et al. (Jun 2025). "AlphaAgent: LLM-Driven Alpha Mining with Regularized Exploration to Counteract Alpha Decay."
**GitHub:** https://github.com/RndmVariableQ/AlphaAgent

AlphaAgent extends LLM-driven factor discovery with explicit mechanisms to prevent discovering crowded or overfitted alphas:

| Regularization | How it works |
|---------------|-------------|
| Originality enforcement | AST (abstract syntax tree) similarity check against existing alpha library — new factors must differ structurally |
| Hypothesis-factor alignment | LLM evaluates semantic consistency between investment hypothesis and generated factor code |
| Complexity control | AST structural constraints cap factor expression depth/branching |

**Results:** Tested on CSI 500 and S&P 500 over 4 years. Claims "consistently delivering significant alpha" vs baseline. Provides better resistance to alpha decay than unconstrained LLM mining.

**vs QuantaAlpha (arXiv:2602.07085):** QuantaAlpha uses evolutionary trajectory mutation/crossover; AlphaAgent uses regularized exploration. AlphaAgent's AST similarity check is more rigorous at preventing duplicate signals. QuantaAlpha has stronger benchmark results (IC=0.1501 on CSI 300 with GPT-5.2).

**Practical note for our pipeline:** Both frameworks primarily target Chinese A-shares (CSI 300/500) with larger universes (500+ stocks). For H202-XL (200-stock US expansion), AlphaAgent's originality enforcement could prevent us from re-discovering signals already captured by alpha101/H217.

---

## Reproducibility Warning: LLM Trading Papers (2026 Audit)

**Source:** arXiv:2605.19337 — Xia et al. (May 2026). "Agentic Trading: When LLM Agents Meet Financial Markets." Systematic review of 77 studies.

**Critical findings:**
- Only **2/19** studies meeting minimum criteria report extractable time-consistent split protocols
- Only **1/19** explicitly models transaction costs
- Only **1/19** documents survivorship handling
- **15/19** classified as R0 reproducibility (results cannot be independently verified)
- **No study reaches R3** (fully reproducible with code + data + methodology)

**Implication for our research:** All cited LLM trading benchmarks (TradingAgents, AlphaCrafter, QuantaAlpha, AlphaAgent) should be treated with significant skepticism unless we can independently verify the OOS split and transaction cost modeling. Our own hypothesis testing protocol (IS/OOS split, 0.1% transaction cost, walk-forward) exceeds the reproducibility standard of most published LLM trading papers.


---

## Live Market Reality Check: LLM Agent Trading (2025-2026)

### StockBench: LLM Agents vs Real Markets

**Source:** arXiv:2510.02209 — "StockBench: Can LLM Agents Trade Stocks Profitably In Real-world Markets?"
**Data:** Real market period, March–July 2025. Evaluated on cumulative return, max drawdown, Sortino ratio.

**Key finding:** Despite strong performance on financial QA benchmarks, **most LLM agents fail to outperform a simple buy-and-hold baseline** in terms of both cumulative return and risk-adjusted return.

This is the most credible LLM trading negative result because:
- Real money/paper trading (not historical backtest)
- Recent out-of-sample data (2025)
- Multiple LLM models tested
- Standard benchmark comparison (buy-and-hold)

**Implication:** Financial QA performance does not translate to trading performance. The ability to answer finance questions != the ability to generate alpha.

---

### KTD-Fin: Memorization Bias and Attribution

**Source:** arXiv:2605.28359 (May 2026) — "From Knowing to Doing: A Memory-Controlled Benchmark for LLM Trading Agents on Stock Markets."
**Data:** CSI300, 2024-2026 (Chinese equity market).

**Core finding:** When ticker symbols and company names are anonymized (masked), LLM agents shift toward factor-based reasoning. Performance attribution analysis reveals that **positive LLM agent returns are largely explained by passive market and style factor exposure** (beta), not genuine stock-selection alpha.

**Memorization problem:** Long backtests overlap with LLM knowledge cutoffs, allowing memorized historical price outcomes to contaminate predictions. Masking substantially changes reasoning patterns — confirming the memorization hypothesis.

**10-dimensional metric framework** introduced:
- Returns & risk: total return, Sharpe, max drawdown, information ratio
- Behavior: annualized turnover, HHI concentration, cash ratio, abstention rate
- Reliability & calibration: leakage score, attribution R² to market/style factors

**Implication for our H238/H239 pipeline:**
- H238 (BlindTrade) directly addresses the memorization issue via anonymization
- H239 (LLM time capsule) intentionally uses frozen model knowledge — the 'memorization' IS the signal (encoding fundamental information)
- For any LLM-based strategy, report the attribution R² to SPY/sector factors to confirm alpha vs beta

---

### Practical Checklist for Evaluating LLM Trading Claims

| Check | Why it matters |
|-------|-----------------|
| Real market test (not backtest only) | Backtests overfit; StockBench shows real-market degradation |
| Ticker anonymization test | If removing tickers changes picks significantly → memorization contamination |
| Attribution analysis | Positive return ≠ alpha; decompose into market + style + stock-selection |
| Transaction cost modeling | Only 1/19 LLM papers models TC (per 2026 audit) |
| Leakage check (knowledge cutoff) | LLM cutoff year must precede the OOS evaluation period |

**Our hypothesis testing standard:** IS/OOS split, 0.10% transaction cost, explicit Sharpe > threshold gate, and (for LLM-based strategies) anonymization variant as negative control.

---

## Kevin's Curated LLM Trading References (2026-06-09)

### FinAgent — Multimodal LLM Agent for Trading (arXiv:2402.18485)

**Reference:** arXiv:2402.18485 (Feb 2024)
**Kevin's note:** "How to build a proper AI trading agent using structured pipelines, not just prompting."

**Core idea:** FinAgent is a multimodal foundation agent framework that combines market data, news, social media, and financial reports via a unified memory module and tool-calling pipeline. Rather than prompting a single LLM for a trade recommendation, FinAgent structures the problem as a pipeline: data retrieval → tool dispatch → memory update → decision. Includes a "diversified reflection" mechanism to avoid over-relying on recent context.

**Architecture highlights:**
- Unified **market intelligence module**: fetches and summarizes multimodal inputs (price, text, images of charts) before LLM sees them
- **Tool dispatcher**: separates retrieval from reasoning — LLM does not make raw API calls
- **Memory buffer**: maintains recent market context, agent reflections, prior trade outcomes
- Tested on 6 financial tasks (stock trading, crypto, ETF, forex) across bull/bear/sideways markets

**Implication for production pipeline:** The key design lesson is **structured data routing before the LLM sees anything**. In our H258/H260 pipeline designs, always pre-process: run FinBERT scoring, compute EPS surprise, fetch sector context — then pass structured summary to LLM, not raw 8-K text. Reduces hallucination and improves reliability.

---

### Can LLMs Generate Novel Research Ideas? (arXiv:2409.04109)

**Reference:** arXiv:2409.04109 (Si et al., Sept 2024)
**Kevin's note:** "LLMs are great for ideation but weak at execution, use them as your starting point."

**Core finding:** Claude-3.5-Sonnet generated research ideas rated as "more novel" than PhD students by expert reviewers, but with "lower feasibility" scores. LLM-generated ideas tend to be creative but underspecified. When researchers were given LLM-generated ideas to execute, projects succeeded less often than researcher-originated ones.

**Implication for the research pipeline:**
- Dream cycle scans (our nightly arXiv scanning) are well-suited to LLMs — ideation and signal detection
- Full hypothesis design and implementation still requires human judgment (Kevin) to evaluate feasibility
- This paper validates the current workflow: George generates staged proposals → Kevin reviews before committing capital
- **Antipattern to avoid:** Auto-applying medium/high-risk proposals without human sign-off. The ideation → execution gap is real.

---

### Alpha-GPT — Human-AI Loop for Factor Discovery (arXiv:2308.00016)

**Reference:** arXiv:2308.00016 (Aug 2023)
**Kevin's note:** "The closest paper to a real quant workflow — human-AI loop for discovering trading factors."

**Core idea:** Alpha-GPT frames quantitative factor mining as an interactive human-AI loop. An LLM proposes new alpha factors (mathematical expressions combining price/volume/fundamental data), a backtesting engine evaluates them automatically, and results feed back to the LLM for iteration. The human steers the search by providing domain constraints, not by writing each factor from scratch.

**Key results reported:**
- Generated factors with IC > 0.05 on Chinese A-share market
- Human feedback loop materially improved factor quality vs fully automated search
- Factor expressions combine standard primitives: rolling means, rank transforms, cross-sectional Z-scores

**Implication for our stack:** This is essentially what our dream cycle does — automated proposal generation + human review. The difference is our LLM generates *hypothesis designs* (what to test) rather than mathematical factor expressions directly. Alpha-GPT's architecture is a model for a future H260+ extension: LLM proposes factor expressions → `run_hNNN.py` evaluates → LLM iterates. The backtesting infrastructure we've built (venv, Alpaca data, Sharpe gate) is already fit for this loop.

---

## Time-Series Foundation Models (Zero-Shot Forecasting)

A new generation of pretrained models (2024–2026) treats time-series forecasting
like an LLM treats text — pretrain on diverse data, then use zero-shot on new series.

### Key Models

| Model | Org | Params | Open Source | Zero-Shot |
|-------|-----|--------|-------------|----------|
| **Chronos** | Amazon | Various | ✓ [amazon-science/chronos-forecasting](https://github.com/amazon-science/chronos-forecasting) | ✓ |
| **TimesFM** | Google | 200M | ✓ [google-research/timesfm](https://github.com/google-research/timesfm) | ✓ |
| **Lag-Llama** | Morgan Stanley/Mila | — | ✓ [kashif/lag-llama](https://github.com/kashif/lag-llama) | ✓ probabilistic |
| **Moirai** | Salesforce | Various | ✓ | ✓ |

### Relevance to Trading Pipeline

**Volatility forecasting (H273 overlay):** Replace rolling 3-month realized vol
estimator with Chronos/TimesFM zero-shot prediction. No IS refit required.

**Regime detection (H251 HMM):** Lag-Llama probabilistic forecast on SPY/VIX series
could produce richer regime probability estimates than Gaussian HMM.

**Practical consideration:** Zero-shot means no IS/OOS bias from training on the
test period — but the pretraining data may include financial markets (look-ahead
risk at the pretraining level, not the strategy level).

```python
# Chronos: drop-in vol forecasting
from chronos import ChronosPipeline
import torch

pipeline = ChronosPipeline.from_pretrained(
    'amazon/chronos-t5-small',
    device_map='cpu',
    torch_dtype=torch.bfloat16
)
# Forecast next 1 month volatility
forecast = pipeline.predict(context=vol_series_tensor, prediction_length=1)
```

**Status:** Research-stage for trading. No confirmed backtested trading Sharpe
improvements found in literature as of 2026-06-13. Candidate for H295+ exploration.

---

## LLM Alpha Mining Cluster (2026)

Three converging 2026 papers from Tsinghua University / Peng Cheng Lab define a new generation of automated factor discovery tools.

### FactorEngine (arXiv:2603.16365, Mar 2026)

**Core idea**: Cast alpha factors as Turing-complete code. LLM handles *directional* search (logic structure, variable relationships); Bayesian optimization handles *parameter* tuning. Three key separations:
1. **Logic revision vs. parameter optimization** — LLM changes if/else branches; grid search optimizes thresholds
2. **LLM directional search vs. Bayesian hyperparameter search** — LLM proposes new architectures, BO refines them
3. **LLM usage vs. local computation** — LLM for creative ideation; local Python for execution/evaluation

**Knowledge-infused bootstrapping**: Financial reports → LLM extraction-verification-codegen pipeline → executable factor programs. Essentially converts unstructured analyst research into evaluatable signals.

**Experience knowledge base**: Stores successful patterns AND failure constraints — trajectory-aware refinement so the system doesn't rediscover dead ends.

**Relevance**: The three-separation architecture solves a key problem in our pipeline: we currently write factor logic entirely by hand. FactorEngine's approach of LLM-for-structure + BO-for-parameters could automate H-number script generation for parameter variants.

### FactorMiner (arXiv:2602.14670, Feb 2026)

**Core idea**: Ralph Loop paradigm for iterative alpha discovery — **R**etrieve, **A**nalyze, **L**earn, **P**ropose, **H**arvest (retrieve prior experience → generate new factor → evaluate → distill insights into memory).

**Modular skill architecture**: Financial evaluation steps (IC calculation, factor neutralization, turnover cost modeling) are wrapped as callable tools, enabling the LLM agent to compose evaluation pipelines rather than just generating code.

**Experience memory**: Distills historical mining trials into actionable insights. As the factor library grows, experience memory prevents redundant exploration by encoding which directions are already saturated.

**Key problem addressed**: As the alpha library grows, new factor discovery gets harder due to high redundancy. FactorMiner's memory layer explicitly addresses this.

**Relevance**: Our hypothesis log is effectively a primitive version of this — H-numbers map to tried directions, NOT_CONFIRMED results encode failure constraints. A FactorMiner-style system could be bootstrapped from our existing 340+ hypothesis history.

### Hubble (arXiv:2604.09601, Apr 2026)

**Core idea**: Safe, diverse, and reproducible alpha factor discovery. Three additions over baseline:
1. **Safety constraints** — reject factors with negative Sharpe, unstable IC, or excessive turnover before committing to the alpha library
2. **Diversity enforcement** — pairwise correlation < 0.5 between new factor and existing library members (prevents redundant factors)
3. **Reproducibility** — deterministic seeding, version-locked factor code storage

**Relevance**: The diversity constraint (pairwise corr < 0.5) directly addresses a problem in our confirmed strategies. H337 failed because GP/A and ROE are too correlated with each other on large-caps. A Hubble-style diversity gate would have predicted this failure before running the backtest.

### Integration Path for George's Pipeline

The three frameworks suggest a future H343+ design:

```
Phase 1: Bootstrap experience base from hypothesis-log.md
  - Parse all NOT_CONFIRMED results → failure constraint library
  - Parse all CONFIRMED results → success pattern library

Phase 2: FactorMiner-style Ralph Loop for new H proposals
  - Retrieve: search failure library for anti-patterns
  - Propose: LLM generates new factor based on gap in confirmed library
  - Evaluate: automated run_hNNN.py execution
  - Distill: append result to hypothesis log + update experience base

Phase 3: Hubble-style diversity gate
  - New factor must have pairwise corr < 0.5 with existing CONFIRMED strategies
  - Automatically reject factor variants too similar to H198 raw momentum
```

This is a multi-month implementation. Short-term: use the diversity constraint conceptually when proposing new H-numbers — check whether the proposed signal is sufficiently uncorrelated with confirmed strategies before building the script.

**Priority**: Document this cluster now. Revisit for implementation once H279 (LLM momentum filter) and H280 (MarketSenseAI) establish baseline LLM signal quality.
