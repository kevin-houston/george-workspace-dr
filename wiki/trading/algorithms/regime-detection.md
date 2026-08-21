---
created: 2026-05-19
updated: 2026-08-20
status: active
relevance: H165 (VIX gate QUEUED), H205-B (bear-regime BAB), all momentum/BAB strategies
---

# Market Regime Detection

Regime detection identifies which "state" the market is in — bull, bear, or neutral — so that strategies can adapt their exposure. Nearly every confirmed strategy shows regime-dependent performance:

| Strategy | Bull Sharpe | Bear Sharpe | Action |
|----------|------------|-------------|--------|
| H026 ETF rotation | Strong | Weak (TSMOM exits) | TSMOM built in |
| H192-D BAB | Ann. 6.7% (H205 TOM analysis) | Ann. 13.8% | H205-B: reduce in bull, hold in bear |
| H198 momentum | High | Negative 2022 | Regime gate could cap MaxDD |
| H181 reversal | ~18% CAGR | Degrades | Unprotected |

H165a confirmed: VIX < 25 filter adds +0.429 OOS Sharpe on unlevered H026 (46 additional forced-BIL months avoided). H165 full (TradingAgents macro-regime gate) is still QUEUED.

---

## Method 1: Simple Threshold Rules

The baseline — fast, interpretable, no look-ahead if applied to daily data.

### 200-Day SMA
```python
import pandas as pd

def bull_regime_200sma(spy_prices: pd.Series) -> pd.Series:
    """True = bull market (SPY above 200-day MA)."""
    sma200 = spy_prices.rolling(200).mean()
    return spy_prices > sma200
```
- **Advantage**: robust, 100 years of academic validation, no training data
- **Disadvantage**: slow — reacts weeks after bear-market onset; many false signals in choppy markets
- **OOS note**: H205 regime split uses this; bear regime (SPY ≤ 200MA) covered 274 of 1,336 TOM days (20%) in 2021–2026

### VIX Threshold
```python
import yfinance as yf

def vix_regime(threshold: float = 25.0) -> pd.Series:
    vix = yf.download("^VIX", start="2013-01-01", auto_adjust=True)["Close"]
    return vix < threshold   # True = low-stress regime
```
- VIX < 25 is the confirmed threshold from H165a (tested 12, 15, 20, 25 — 25 optimal)
- **Why 25**: captures genuine stress regimes (2008, 2020, 2022) without over-filtering choppy but benign markets
- 46 additional forced-BIL months vs pure TSMOM gate alone; +0.429 Sharpe OOS on unlevered H026

### Combining SMA + VIX
```python
def composite_regime(spy: pd.Series, vix: pd.Series, vix_thresh=25.0) -> pd.Series:
    """Invested only when SPY > 200MA AND VIX < threshold."""
    sma_bull = spy > spy.rolling(200).mean()
    vix_calm = vix < vix_thresh
    return sma_bull & vix_calm
```

---

## Method 2: Markov Switching Models (statsmodels)

Hamilton (1989) regime model — assumes market switches between k regimes with fixed transition probabilities. Fitted by maximum likelihood via Hamilton filter + EM algorithm.

```python
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression
import numpy as np

def fit_markov_switching(returns: np.ndarray, k_regimes: int = 2):
    """
    Fit 2-regime Markov Switching model to return series.
    Returns filtered regime probabilities (T × k_regimes).
    """
    mod = MarkovRegression(
        returns,
        k_regimes=k_regimes,
        trend='c',          # constant mean per regime
        switching_variance=True  # different volatility per regime
    )
    res = mod.fit(search_reps=20, search_iter=10, disp=False)
    return res

# Use:
# res.smoothed_marginal_probabilities[:, 0]  → prob(regime 0) per day
# res.filtered_marginal_probabilities         → online version (no look-ahead)
# res.summary()                               → transition matrix, regime stats
```

**Interpretation**: Regime 0 = low-volatility (bull), Regime 1 = high-volatility (bear). Inspect `res.params` to confirm — the regime with lower variance is the calm state.

**Critical**: use `filtered_marginal_probabilities` (not smoothed) in live/OOS trading to avoid look-ahead bias. Smoothed probabilities use future data.

**Limitations**:
- Assumes fixed transition probabilities — markets shift regime character over time
- Requires retraining periodically (recommend: annual rolling window or expanding IS window)
- EM algorithm sensitive to initialization: use `search_reps=20`

---

## Method 3: Hidden Markov Models (hmmlearn)

Unsupervised — learns regimes from multi-feature input without specifying transition structure explicitly. More flexible than statsmodels for multi-feature regimes.

```python
from hmmlearn.hmm import GaussianHMM
import numpy as np

def fit_hmm_regime(features: np.ndarray, n_states: int = 3):
    """
    Fit Gaussian HMM to feature matrix.
    features: (T × n_features) — e.g. [returns, vol, vix, ma_spread, yield]
    Returns: regime labels (T,) array
    """
    model = GaussianHMM(
        n_components=n_states,
        covariance_type="full",
        n_iter=200,
        random_state=42
    )
    model.fit(features)
    return model, model.predict(features)

# Recommended features (PyQuantLab 2025):
# - returns (daily log-return)
# - rolling volatility (21-day)
# - VIX level
# - trend spread (50MA − 200MA, normalized)
# - 10-year yield level
```

**n_states = 2 vs 3**: 2-state is simpler and more robust OOS. 3-state (bull/bear/neutral) is more interpretable but the "neutral" state often overfits to transitional periods.

**OOS deployment**:
```python
# At each new bar, predict regime from last N days of features (no look-ahead):
def predict_regime_online(model, features_window):
    return model.predict(features_window)[-1]  # last state = current
```

**Benchmark result** (QuantStart 2014 study, SPY SMA crossover + HMM filter):
- No regime filter: MaxDD −56%, Sharpe 0.37
- HMM regime filter: MaxDD −24%, Sharpe 0.48
- Drawdown reduction is the primary benefit; Sharpe improvement is modest

---

## Method 4: Statistical Jump Model (recommended — superior to HMM)

**Reference**: Shu, Yu & Mulvey (2024), "Downside Risk Reduction Using Regime-Switching Signals: A Statistical Jump Model Approach", arXiv:2402.05272

The Statistical Jump Model (JM) improves over HMM by adding a **jump penalty** at each state transition — this enforces regime persistence (markets stay in a regime for weeks, not hours). Consistently outperforms HMM on US, German, and Japanese equities 1990–2023 across volatility, drawdown, and Sharpe metrics.

**Key insight**: Standard HMM assigns equal cost to frequent regime switches and stable periods. JM adds λ × (# transitions) to the cost function, producing smoother, more actionable regime sequences. Fewer false signals than HMM.

```python
# No dedicated Python library yet — implementation via optimization
# The paper provides pseudocode; a practical approximation uses hmmlearn
# with post-processing to enforce persistence:

def smooth_regime_labels(labels: np.ndarray, min_duration: int = 5) -> np.ndarray:
    """
    Post-process HMM labels to enforce minimum regime duration.
    Eliminates single-day regime flips (often noise).
    min_duration: minimum consecutive days a regime must hold.
    """
    smoothed = labels.copy()
    n = len(smoothed)
    i = 0
    while i < n:
        j = i
        while j < n and smoothed[j] == smoothed[i]:
            j += 1
        if j - i < min_duration:
            # Too short — merge with surrounding regime
            prev_regime = smoothed[i - 1] if i > 0 else smoothed[j] if j < n else smoothed[i]
            smoothed[i:j] = prev_regime
        i = j
    return smoothed
```

Until a pip-installable JM library exists, use `hmmlearn + smooth_regime_labels` as an approximation.

---

## Comparison Table

| Method | Complexity | Speed | Look-ahead risk | OOS quality | Best for |
|--------|-----------|-------|-----------------|-------------|---------|
| 200-day SMA | Trivial | O(n) | None | Good — simple, robust | Bull/bear gate on daily |
| VIX threshold | Trivial | O(n) | None | Good (H165a confirmed) | Stress regime filter |
| VIX + SMA combined | Simple | O(n) | None | Best of simple methods | H026 / H192-D gate |
| Markov Switching (statsmodels) | Medium | O(n·iter) | Use filtered probs | Moderate | Regime-conditional parameters |
| HMM (hmmlearn) | Medium | O(n·iter) | Use online predict | Moderate | Multi-feature regimes |
| Statistical JM (arXiv:2402.05272) | High | O(n·iter) | None | Best | Production regime gate |

---

## Application to Our Strategies

### H165 (TradingAgents macro-regime gate) — QUEUED
- H165a confirmed: VIX < 25 gate adds +0.429 Sharpe on unlevered H026
- Full H165 proposal: use 200MA + VIX + yield curve (2/10 spread) as composite regime score
- Implementation path: start with composite threshold rule; add statsmodels Markov if threshold insufficient

### H205-B (regime-conditional BAB) — QUEUED
```python
def h205b_regime_conditional(date, spy_prices, vix, bab_return, tom_mask):
    """
    In bull regime: hold full H192-D (no TOM filter).
    In bear regime: apply TOM filter (H205 design).
    """
    is_bull = spy_prices[date] > spy_prices[:date].rolling(200).mean()[date]
    is_vix_calm = vix[date] < 25.0
    
    if is_bull and is_vix_calm:
        return bab_return[date]           # Full H192-D exposure
    elif tom_mask[date]:
        return bab_return[date]           # TOM window only in bear
    else:
        return 0.0                         # BIL in bear non-TOM days
```
**Hypothesis**: bear regime ann_ret 13.8% on 19% of days → per-invested-day return is ~3.6× better in bear regime. Conditional application captures this without sacrificing bull CAGR.

### General momentum strategies (H198, H181)
```python
def momentum_with_regime_gate(returns, spy_prices, vix, threshold=25.0):
    """Apply momentum signal only in bull+calm regimes."""
    bull = spy_prices > spy_prices.rolling(200).mean()
    calm = vix < threshold
    regime = (bull & calm).astype(float)
    return returns * regime  # zero return (hold BIL) in bear/stress regime
```

---

## Production Recommendations

1. **Start simple**: VIX < 25 + SPY > 200MA composite rule. Already backtested (H165a). Add complexity only if simple rule fails.

2. **Avoid look-ahead**: For live trading, use only information available at decision time:
   - 200MA: close of previous trading day
   - VIX: close of previous trading day  
   - HMM: use `filtered_marginal_probabilities` (not smoothed)

3. **Regime persistence threshold**: A single-day regime break is noise. Apply `smooth_regime_labels(min_duration=5)` to filter flips shorter than one week.

4. **Retraining**: Annual full retrain of any ML regime model. Use expanding window (include all history), not rolling window alone.

5. **Test regime labels before deploying**: Print the regime sequence — regimes should correspond to recognizable market periods (2020 COVID = bear, 2021 = bull, H2 2022 = bear). If labels don't match intuition, the model is fitting noise.

---

## Install

```bash
pip install hmmlearn statsmodels
```

Both are available in standard Python quant environments. No venv rebuild needed — these are lightweight.

---

## Implementation Reference: QuhiQuhihi/regime_model

**GitHub**: https://github.com/QuhiQuhihi/regime_model — 61 stars, 18 forks

Python implementation of two regime detection approaches, originally inspired by Two Sigma's public article on ML regime modeling (Alex Botte & Doris Bao).

### 1. Gaussian Mixture Model + Hidden Markov Model (multi-asset)
- Uses GMM/HMM on **multiple asset classes simultaneously**: equities, bonds, real estate, commodities
- Source: Two Sigma article — "A Machine Learning Approach to Regime Modeling"
- Multi-asset approach produces more robust regime signals than single-asset HMM — asset classes disagree during transitions, which the model captures

### 2. Greedy Gaussian Segmentation (single asset)
- GGS on US equities only — Stanford paper (Hallac, Nystrup, Boyd, https://web.stanford.edu/~boyd/papers/pdf/ggs.pdf)
- Segments a time series into contiguous blocks with distinct Gaussian distributions — finds structural break points without assuming a fixed number of states
- Useful diagnostic tool: run on SPY returns to visually validate that regime labels correspond to recognizable market periods

### Relevance to our pipeline
- The multi-asset GMM/HMM approach directly matches our CLAUDE.local.md design note: use `hmmlearn GaussianHMM` on multi-feature inputs; this repo provides working reference code
- H165 full (macro-regime gate) and H205-B (bear-regime BAB) both need a regime signal — this repo is the closest runnable starting point
- **Key addition**: the multi-asset version using bonds + commodities as co-inputs is more robust than our current VIX + 200MA composite, and could serve as the ML upgrade path once H165a is in production

---

## References

- Hamilton, J.D. (1989). "A New Approach to the Economic Analysis of Nonstationary Time Series." *Econometrica* 57(2): 357-384.
- Shu, Yu & Mulvey (2024). "Downside Risk Reduction Using Regime-Switching Signals: A Statistical Jump Model Approach." arXiv:2402.05272.
- Botte & Bao, Two Sigma: "A Machine Learning Approach to Regime Modeling" — https://www.twosigma.com/articles/a-machine-learning-approach-to-regime-modeling/
- Hallac, Nystrup & Boyd (Stanford): "Greedy Gaussian Segmentation" — https://web.stanford.edu/~boyd/papers/pdf/ggs.pdf
- QuhiQuhihi/regime_model: https://github.com/QuhiQuhihi/regime_model
- QuantStart: [Market Regime Detection using HMM in QSTrader](https://www.quantstart.com/articles/market-regime-detection-using-hidden-markov-models-in-qstrader/)
- statsmodels docs: [Markov Switching Dynamic Regression](https://www.statsmodels.org/stable/examples/notebooks/generated/markov_regression.html)
- hmmlearn: https://hmmlearn.readthedocs.io/

---

## Regime Drift + Factor Combination (arXiv:2511.12490)

**Reference**: "Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hidden Cross-Sectional Predictability", arXiv:2511.12490 (Nov 2025)

**Finding**: Value + short-term reversal signals, when gated on a 'drift regime' detector, achieve OOS Sharpe 13+ in the study's universe. The extraordinary Sharpe likely reflects a specific regime definition and universe, but the key structural insight is validated: the same factor signal applied conditionally during detected drift periods dramatically outperforms unconditional application.

**Drift regime definition** (from paper): A stock is in a 'drift regime' when its 30-day price trend is statistically significant (t-stat of rolling OLS slope > 2.0) AND volume is confirming (positive correlation between price and volume over the window). This is more precise than our H221 'drift regime' which used a simple >5% prior-month return threshold.

**Relevance to our pipeline**:
- H221 (NOT CONFIRMED at OOS 0.343) used a too-simple drift detector; the statistical significance approach here is more rigorous
- H165-full design: the paper's drift detector could replace or complement the VIX < 25 + SPY > 200MA composite
- H181 (industry reversal, OOS 1.138): applying H181 only during detected drift periods (per this paper's method) is worth testing as H181-regime variant

**Caution**: OOS Sharpe 13+ is implausibly high for a general strategy; this may reflect a cherry-picked regime definition, small sample, or universe selection. Treat as design inspiration, not a benchmark target.

---

## Continuous Cash-Overlay Filter (Jun 2026)

**Source**: arXiv:2606.09025 — "Continuous Cash-Overlay Filters for a Static Growth-Defensive Risk Sleeve: Slow-Tail Compensation, V-Shape Crash Brakes, Walk-Forward Validation, and Max-Cash Combination" (Zheli Xiong, Jun 2026)

### Two-Filter Architecture

**Filter 1: Slow-Tail** (macro regime)
- Inputs: compensation signal, rate-headwind, risk-premium-compression, rate-path-stress
- Output: continuous cash weight (0 to max-cash cap)
- 30% trading gate (only rebalance if weight change exceeds threshold)

**Filter 2: V-Shape Crash Brake** (fast tactical)
- Inputs: VIX level, rate move, credit spread, portfolio drawdown, re-entry conditions
- Output: binary or continuous emergency cash shift
- Fast-acting: responds within days to crash signals

### Performance (2017-2026)
- CAGR: 19.35% vs 17.59% baseline (+1.76pp)
- MaxDD: -22.05% vs -33.59% (-11.54pp) = 34% improvement
- Walk-forward validated with expanding window

### Connection to Our Pipeline

| Existing gate | Type | Limitation | Overlay improvement |
|---|---|---|---|
| H362 VIX<20 on H354 | Binary | Whipsaw at threshold | Slow-tail continuous weight |
| H301 SPY>200MA on H026 | Binary | Delayed signal | V-shape crash brake |
| H311 VIX<20 on EW-4 | Binary | Only one variable | Multi-variable slow-tail |

### Proposed H412
Apply slow-tail + V-shape overlay as a portfolio-level cash buffer on our H026+H045 allocation:
  - IS: 2017-2020 (parameter selection), OOS: 2021-2026
  - Baseline: H026 + H045 combined allocation (current production weight 48%)
  - Gate: OOS Sharpe improvement > 0.2 above H026+H045 without overlay
  - Transaction cost model: 5bp per shift (ETF liquidity is high)
  - Key test: does the V-shape brake add value beyond our existing SPY>200MA overlay (H301)?

**Note**: Paper authors frame results as 'drawdown-control tool not return-enhancement' — consistent with our MaxDD priority for the 4.158 Sharpe production portfolio.

---

## See Also

- [Regime Detection 2026 Papers — Wasserstein-HMM and Heavy-Tail Emissions](regime-detection-2026-papers.md) — H444/H445 design basis; BIC K-selection, 2-Wasserstein state tracking, Student-t/Laplace emissions
- [ESG Tail-Risk / Stress Resilience (Hu et al. 2026)](../../concepts/esg-tail-risk-stress-resilience-2026.md) — 2026 paper finding ESG's crisis-resilience effect is stress-conditional, not static; candidate use case for this page's regime-gate infrastructure applied outside the core H165/H249/H301 stack

---

## Research Lead: Real Statistical Jump Model Implementation Found (jump-models, 2026-08-03)

Method 4 above (line 149) has flagged since this page's creation that 'no dedicated Python library yet' exists for the Shu/Yu/Mulvey (2024) Statistical Jump Model, forcing the `hmmlearn + smooth_regime_labels` approximation used throughout H165/H205-B/H251/H429. Tonight's dream-cycle scan found a direct reference implementation:

- **Repo**: [Yizhan-Oliver-Shu/jump-models](https://github.com/Yizhan-Oliver-Shu/jump-models) — 157 stars, Apache-2.0, sklearn-style `fit`/`predict` API with pandas DataFrame I/O
- Implements discrete JM, continuous JM, and sparse JM (feature-selecting variant) — i.e. the exact three variants described across the arXiv:2402.05272 paper family, not a partial or reinterpreted version
- Single-author project (bus-factor risk — watch for maintenance lapses before depending on it in a scheduled/production script) but code maps directly onto the paper already cited at line 151

**Why this matters**: the `smooth_regime_labels(min_duration=5)` post-processing hack (line 162-180) approximates JM's core innovation — a persistence penalty baked into the *fitting* objective (λ × transition count) — by bolting a fixed-window smoother onto HMM's *output* after the fact. These are not equivalent: HMM+smoothing can still fit noisy short-lived states during training (the smoother only cleans up the label sequence afterward), while true JM never fits those states in the first place because the penalty is inside the optimization. H429's finding that IS-frozen HMM variants degenerate to a single dominant state (replicating the H251 root cause) is exactly the kind of instability a real jump-penalty objective is designed to avoid.

**Suggested next step**: swap `jump-models`' discrete-JM class in for the `hmmlearn GaussianHMM` step in a follow-up to H429 (Wasserstein-Tracked Rolling HMM), keeping the same 5Y rolling-window retraining + Wasserstein state-matching wrapper that made H429's Var C/F pass gate, and compare OOS Sharpe/MaxDD/MaxStateFrac against the existing HMM-based Var C (1.144 / -17.2% / 47%) and Var F (1.067 / -16.6% / 41%). See a staged new_script proposal (H489 stub) filed alongside this wiki update for a concrete build plan.

**Caveat**: not yet installed or run — per standing off-hours install-security rule, this is a wiki note flagging the find, not a live pip install. Verify on PyPI (if published) or install from GitHub source with `pip-audit` run afterward before using in any scheduled script.

## Research Lead: Autoencoder-Gated Dual-Node Transformer Regime Detection (arXiv:2603.19136, flagged 2026-08-20)

**Source:** Mohammad Al Ridhawi, Mahtab Haj Ali, Hussein Al Osman, "Adaptive Regime-Aware Stock Price Prediction Using Autoencoder-Gated Dual Node Transformers with Reinforcement Learning Control," submitted 2026-03-19 to Applied Intelligence (Springer), not yet accepted.

**What it is:** A three-component regime-aware price-prediction architecture, distinct from every regime-detection approach already on this page (HMM, SJM, VIX/200MA composite, Berry Phase Rate): (1) an **autoencoder trained only on normal-market conditions** flags regime shifts via reconstruction error -- high error means "this doesn't look like normal market behavior," a fully unsupervised anomaly-detection framing rather than a labeled or mixture-model state classification; (2) **dual node transformer networks**, one specialized for stable conditions and one for event-driven/volatile conditions, with the autoencoder's anomaly score routing data between them; (3) a **Soft Actor-Critic RL controller** that adaptively tunes both the regime-detection threshold and the blending weight between the two transformer pathways based on live prediction-performance feedback, rather than using a fixed threshold set once at training time.

**Results reported:** 20 S&P 500 stocks, 1982-2025. One-day-ahead MAPE 0.80% (baseline single transformer) -> 0.68% (dual-node, no RL controller) -> 0.59% (full system with RL controller). Directional accuracy 72% with the complete framework. Note this is a point-prediction/MAPE study, not a portfolio backtest -- no Sharpe, MaxDD, or transaction-cost figures are reported, so it cannot be directly compared to this wiki's hypothesis-log gate thresholds without first converting predictions into a tradeable signal and running it through the standard IS/OOS backtest harness.

**Relevance to George's regime-detection line:** The wiki's existing approach (per the CLAUDE.local.md standing design note) is Statistical Jump Model as an SJM-approximation via hmmlearn GaussianHMM + smoothed labels, validated against a VIX<25 + SPY>200MA composite baseline. This paper's autoencoder-reconstruction-error approach is a genuinely different detection mechanism -- unsupervised anomaly scoring rather than a state-transition model -- and could in principle serve as a third detector to ensemble against HMM/SJM and the VIX/200MA composite the way H429's Wasserstein-tracked rolling HMM was validated against a static baseline. The RL-tuned adaptive threshold is the most novel piece relative to anything currently on this page: every existing regime gate here (VIX<20, VIX<25, SPY 200MA) uses a fixed, hand-set threshold.

**Not staged as a new hypothesis** -- point-prediction accuracy (MAPE, directional accuracy) is not the same evaluation frame as this wiki's portfolio-level Sharpe/MaxDD/WF-ratio gates; a hypothesis attempt would first need to define how autoencoder reconstruction error becomes a position-sizing or regime-gate signal, closer in spirit to H429/H523 than a direct replication. Logged as a design-reference note pending a scoping pass.

**Cross-references:** [Regime Detection](../algorithms/regime-detection.md) -- HMM/SJM/VIX-composite methods this autoencoder approach would sit alongside as a third detection mechanism, [Hypothesis Log](../backtesting/hypothesis-log.md) -- H429 (Wasserstein-Tracked Rolling HMM, CONFIRMED) and H523 (ML regime selector, NOT CONFIRMED) as the nearest prior art for how a new regime detector would need to be validated here
