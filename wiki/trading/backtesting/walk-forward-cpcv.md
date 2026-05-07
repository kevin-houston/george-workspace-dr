---
updated: 2026-05-07
type: methodology
status: active
---

# Walk-Forward Validation & Combinatorial Purged Cross-Validation (CPCV)

The formal validation methodology behind all IS/OOS splits in the hypothesis pipeline. Standard k-fold CV is **wrong** for financial time series — it shuffles data and creates lookahead bias. This page covers the correct approaches.

---

## Why Standard Cross-Validation Fails in Finance

Standard k-fold shuffles data, destroying temporal order. Financial labels (e.g., "20-day return") are forward-looking — the label for day T depends on prices at T+1 through T+20. If a test sample is placed at T and a training sample is at T+10, the training sample *embeds information about the test period's outcome*. This is lookahead bias at the CV level, not just at the feature level.

Three failure modes in financial CV:
1. **Temporal leakage**: training samples overlap with test sample labels
2. **Single-path variance**: one backtest is one draw from many possible paths — high variance, often lucky
3. **Multiple testing**: testing 100 parameter variants and reporting the best inflates the apparent Sharpe by 2–3×

---

## Walk-Forward Optimization (WFO)

The simplest correct approach. Core idea: at each evaluation step, the test window is strictly in the future relative to all training data.

### Anchored WFO

```
IS window grows forward with each step:

T  [────────IS────────][OOS]
T' [──────────IS──────────][OOS]
T'' [────────────IS────────────][OOS]
```

- IS grows; same start date throughout
- Best for strategies where long history improves calibration (trend-following, sector rotation)
- Our `backtesting/daily/` engine uses anchored WFO: IS = 2008–2017, OOS = 2018+

### Rolling WFO

```
IS window shifts forward at fixed length:

T  [────IS────][OOS]
T' ──[────IS────][OOS]
T''   ──[────IS────][OOS]
```

- IS length fixed; recent history only
- Best for regime-adaptive strategies (ML models, macro signals)
- Typical ratio: 80/20 (4 years IS → 1 year OOS)

### WFO Limitations

Single-path WFO still only produces **one time series of returns**. If 2018–2026 happened to be a good regime for your strategy, you'll look great; if bad, you'll look terrible. The result depends heavily on which historical period was realized.

---

## Combinatorial Purged Cross-Validation (CPCV)

From Marcos López de Prado, *Advances in Financial Machine Learning* (2018), Chapter 12.

Solves WFO's single-path variance problem by generating **a distribution of backtest paths** from all possible train/test splits, while eliminating lookahead bias through purging and embargoing.

### Algorithm

1. **Partition** T observations into **N sequential, non-overlapping groups** (no shuffling — temporal order preserved throughout)
2. **Choose k** = number of test groups per fold (k < N)
3. Enumerate all **C(N, k)** combinations of k test groups
4. For each combination:
   - Training set = all groups NOT in the test combination
   - **Purge** from training any observations whose label horizon overlaps the test period
   - **Embargo** a gap of `embargo_pct × test_period_length` observations after each test block
   - Fit model, evaluate on test block, record metric
5. Output: **distribution** of C(N, k) Sharpe ratios, not a single number

```
Number of paths: φ = C(N, k) = N! / (k! × (N−k)!)

Examples:
  N=10, k=2 → C(10,2) = 45 paths
  N=15, k=3 → C(15,3) = 455 paths
  N=20, k=3 → C(20,3) = 1,140 paths
  N=30, k=4 → C(30,4) = 27,405 paths  ← expensive
```

### Purging

Remove training samples whose label horizon overlaps the test window.

Example: if label = 20-day forward return and a training sample is at date T-5 from the start of the test window, its label runs into the test period. Remove it.

```python
# Pseudo-code for purge
for train_idx in train_set:
    label_end = train_idx + holding_period
    if label_end >= test_start:
        train_set.remove(train_idx)  # purge it
```

### Embargoing

After the test block ends, exclude a buffer of observations from training for the next fold — they may have absorbed market-impact or information leakage from the test period.

```python
embargo_size = int(embargo_pct * test_length)  # typically 5–10%
# Exclude: [test_end : test_end + embargo_size] from training
```

### CPCV vs k-Fold: Key Differences

| Aspect | Standard k-Fold | CPCV |
|--------|-----------------|------|
| Data shuffling | Yes (destroys order) | No |
| Lookahead bias | Yes, pervasive | Eliminated via purging |
| Test set size | 1/k of data | k/N of data |
| Paths generated | 1 | C(N, k) |
| Embargo | None | Yes (5–10%) |
| Output | Single Sharpe | Distribution of Sharpes |

### 2024 Academic Result

Arian et al. (2024, *Knowledge-Based Systems*) ran a controlled synthetic comparison. CPCV showed significantly lower **Probability of Backtest Overfitting (PBO)** than k-fold, purged k-fold, and single-path WFO. CPCV's DSR test statistic was also more favorable. Conclusion: CPCV is the gold standard when overfitting risk is the primary concern.

---

## Deflated Sharpe Ratio (DSR)

Companion to CPCV. Corrects for **multiple testing** — the inflation of apparent Sharpe from running many strategy variants and reporting the best.

### The Problem

Run 100 parameter variants on random noise. The expected maximum Sharpe ≈ 0.8. A researcher who reports "Sharpe = 1.2" after 100 trials is likely reporting a lucky draw.

### Formulas

**Probabilistic Sharpe Ratio (PSR)** — probability that true Sharpe exceeds a benchmark:

```
PSR(ŜR*) = Φ[ (ŜR - ŜR*) × √(T-1) / √(1 - γ₃ŜR + ((γ₄-1)/4)ŜR²) ]

where:
  ŜR = observed annualized Sharpe
  ŜR* = benchmark Sharpe (usually 0 or 1)
  T   = number of return observations
  γ₃  = skewness of returns
  γ₄  = excess kurtosis of returns
  Φ   = standard normal CDF
```

**Deflated Sharpe Ratio (DSR)** — PSR adjusted for M trials:

```
Expected max Sharpe from M independent trials ≈ √(2 log M) × (1 - γE)/√T + γE × √(2 log M)

DSR = PSR evaluated at this expected-max threshold instead of 0
```

Practical impact of multiple testing:

| Observed Sharpe | M = 1 trial | M = 10 trials | M = 100 trials | M = 1000 trials |
|----------------|-------------|----------------|-----------------|-----------------|
| 1.0 | ~0.90 | ~0.70 | ~0.45 | ~0.25 |
| 1.5 | ~0.98 | ~0.88 | ~0.70 | ~0.50 |
| 2.0 | ~0.99+ | ~0.96 | ~0.85 | ~0.68 |

*Approximate DSR scores. Use mlfinlab's exact implementation.*

### Connection to Our Pipeline

In our threshold sweeps (e.g., H139 tests 6 variants of TSMOM threshold), M = 6. At Sharpe 3.0, DSR ≈ 2.8 — minor deflation. But in H026's full optimization history (H108 through H149, dozens of weight and parameter tests), M ≈ 50–100. The confirmed Sharpe of ~3.0 should probably be deflated to ~2.0–2.5 for the "true" expectation. Our OOS window confirmation criteria (require both OOS + AltOOS windows to confirm) is a practical substitute for DSR.

---

## Python Libraries

### timeseriescv (lightweight, sklearn-compatible)

```
pip install timeseriescv
```

```python
from timeseriescv import CombPurgedKFoldCV
import numpy as np
import pandas as pd

# X: feature matrix, y: labels, t_pred: prediction times, t_eval: label evaluation end times
cv = CombPurgedKFoldCV(
    n_splits=10,        # N = number of groups
    n_test_splits=2,    # k = test groups per path
    embargo_td=pd.Timedelta("5 days"),
)

for train_idx, test_idx in cv.split(X, pred_times=t_pred, eval_times=t_eval):
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    # fit, eval, record
```

GitHub: https://github.com/sam31415/timeseriescv | License: MIT | ~500 stars

### skfolio (portfolio optimization focus)

```
pip install skfolio
```

```python
from skfolio.model_selection import CombinatorialPurgedCV

cv = CombinatorialPurgedCV(
    n_splits=5,
    n_test_splits=2,
)
# Works as sklearn CV splitter — plug into GridSearchCV
```

GitHub: https://github.com/skfolio/skfolio | License: BSD-3 | ~1k stars

### mlfinlab (full financial ML toolkit)

```
pip install mlfinlab
```

```python
from mlfinlab.cross_validation.combinatorial import CombinatorialPurgedKFoldCV

cv = CombinatorialPurgedKFoldCV(
    n_splits=10,
    n_test_splits=2,
    pct_embargo=0.05,
)
for train, test in cv.split(X):
    ...
```

GitHub: https://github.com/hudson-and-thames/mlfinlab | Production-ready, integrates DSR

---

## Practical Parameter Guide

| Parameter | Symbol | Typical | Notes |
|-----------|--------|---------|-------|
| Number of groups | N | 10–25 | More = more paths but slower |
| Test groups per fold | k | 2–3 | k=2 is standard; k≥4 is expensive |
| Minimum paths for stability | φ | ≥100 | Below 100 paths, distribution is noisy |
| Embargo pct | ε | 5–10% | Guard against market microstructure lag |
| Min train/test ratio | — | 3:1 | Need enough training to fit meaningfully |

**Combinatorial explosion warning:**
- N=20, k=3 → 1,140 paths (minutes on modern hardware)
- N=30, k=4 → 27,405 paths (hours; needs parallelization)
- N=40, k=5 → 658,008 paths (only feasible with cloud/GPU)

Practical mitigation: each path is embarrassingly parallel — use `joblib.Parallel`.

---

## When to Use What

| Scenario | Method |
|----------|--------|
| Quick hypothesis research (days 1–3) | Single-path anchored WFO |
| Threshold sweep (6–20 variants) | WFO + apply DSR correction |
| ML model selection (100+ variants tested) | CPCV required |
| Publishing or capital allocation decision | CPCV + DSR |
| Live trading parameter refresh | Rolling WFO (recent data only) |
| Comparing two confirmed strategies | CPCV with shared paths |

### Our Pipeline's Approach

**Research phase** (current): Anchored WFO with two independent OOS windows (IS 2008–2017, OOS 2018+, AltOOS 2013+). Requiring both to confirm is a practical proxy for CPCV's multi-path requirement — a strategy must be robust to two different endpoint choices.

**Before live deployment**: Run CPCV on any strategy with >20 parameter variants tested. Specifically needed for H026's full optimization history and any ML-fitted models (H172, H176, H171).

---

## Connection to Current Hypothesis Pipeline

| Hypothesis | Notes on validation |
|------------|---------------------|
| H026–H149 (rotation system) | M≈100 variants tested over time → DSR deflates Sharpe from ~3.0 to ~2.0–2.5; dual OOS window is practical substitute |
| H163/H174 (FinBERT PEAD) | M≈20 threshold variants; OOS n≥15 + WR≥68% criteria implicitly handle multiple testing |
| H172 (FinBERT CLS embedding) | ML classifier → CPCV required before live deployment |
| H176 (GPT-4o-mini sentiment) | Tested on H168 transcripts; threshold sweep M≈7 → DSR deflation modest |
| H178/H179 (rotation variants) | M=5 variants each; failed — no deflation concern |

---

## References

- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley. Ch. 7 (purging), Ch. 12 (CPCV)
- Bailey, D.H. & López de Prado, M. (2014). *The Deflated Sharpe Ratio*. SSRN 2460551
- Arian, H. et al. (2024). *Backtest overfitting in the ML era*. Knowledge-Based Systems. doi:10.1016/j.knosys.2024.111110
- arXiv:2512.12924 — Interpretable walk-forward framework for microstructure signals (2025)
- https://github.com/sam31415/timeseriescv — Lightweight CPCV (MIT)
- https://github.com/skfolio/skfolio — Portfolio-focused CPCV (BSD-3)
- https://github.com/hudson-and-thames/mlfinlab — Full toolkit with DSR integration
