---
title: Multiple Testing & Statistical Significance
added: 2026-05-26
category: backtesting / methodology
---

# Multiple Testing & Statistical Significance

The most common way quant research produces false positives: test many strategies on the same data, then report only the one that looks best. Even with honest intentions, the act of iterating on a hypothesis inflates apparent performance. This page covers the corrections, tests, and tools for detecting and controlling this.

## Why it matters for our pipeline

Our hypothesis log has 226+ tests. If we assume a 5% false-positive rate per test with no correction, we'd expect ~11 false confirmations by chance alone. The confirmed strategies (H163, H174, H192, H198, H215, H220) pass a stricter IS/OOS split — but DSR and PBO add formal guarantees on top.

---

## 1. The multiple testing problem

Running `N` independent tests each at significance `α` gives a family-wise error rate (FWER):

```
FWER = 1 − (1 − α)^N
```

For `N=50` tests at `α=0.05`: `FWER = 0.923` — almost certain false positive among the set.

**Naive p-value vs corrected p-value:** Selecting the best strategy from 100 trials and reporting its raw p-value is misleading. The effective p-value should account for how many trials were run.

---

## 2. Bonferroni & Benjamini-Hochberg

### Bonferroni (FWER control)
Divide target α by number of tests: `α_bonferroni = α / N`

- Too conservative when tests are correlated (most of ours are — same underlying data)
- Use only when N is small or independence is safe to assume

### Benjamini-Hochberg FDR (recommended for large test families)
Controls expected proportion of false discoveries rather than probability of any false discovery.

```python
from statsmodels.stats.multitest import multipletests

pvalues = [0.001, 0.008, 0.039, 0.041, 0.150, 0.210]  # raw p-values from N tests
reject, p_corrected, _, _ = multipletests(pvalues, alpha=0.05, method='fdr_bh')
# reject: boolean array — which hypotheses survive correction
# p_corrected: adjusted p-values
```

BH is appropriate when tests share underlying data (e.g., same return series) and some true effects exist.

---

## 3. Deflated Sharpe Ratio (DSR)

**Paper:** Bailey & López de Prado, "The Deflated Sharpe Ratio," JPM 2014. SSRN:2460551

**Problem:** Standard Sharpe ratio testing (is SR > 0?) ignores two biases:
1. **Selection bias** — we pick the best of many tried strategies
2. **Non-normality** — fat tails and negative skew inflate apparent SR

**DSR corrects both** by computing the benchmark SR that a selected strategy must exceed to be significant given:
- Number of trials `N`
- Skewness and kurtosis of the return distribution
- Track record length `T`

### Closed-form Python implementation

```python
import numpy as np
from scipy.stats import norm
from scipy.special import gamma

EULER_GAMMA = 0.5772156649015328606  # Euler-Mascheroni constant

def probabilistic_sharpe_ratio(sr_hat, sr_benchmark, T, skew, kurt):
    """
    PSR: probability that true SR > benchmark given observed SR.
    sr_hat, sr_benchmark: unannualized (monthly or daily)
    T: number of observations (months or days)
    """
    num = (sr_hat - sr_benchmark) * np.sqrt(T - 1)
    denom = np.sqrt(1 - skew * sr_hat + ((kurt - 1) / 4) * sr_hat**2)
    return norm.cdf(num / denom)

def dsr_benchmark(sr_list, T):
    """
    Compute the DSR benchmark SR from a list of all tested (unannualized) SRs.
    From Bailey & Lopez de Prado (2014), eq. 10.
    """
    N = len(sr_list)
    sr_arr = np.array(sr_list)
    V = np.var(sr_arr, ddof=1)  # dispersion across trials
    # Expected maximum of N iid standard normals (approximate)
    e_max = ((1 - EULER_GAMMA) * norm.ppf(1 - 1/N) + EULER_GAMMA * norm.ppf(1 - 1/(N * np.e)))
    sr_benchmark = np.sqrt(V) * e_max
    return sr_benchmark

def deflated_sharpe_ratio(returns, sr_monthly, sr_list_monthly):
    """
    Returns DSR p-value for the selected strategy.
    - returns: numpy array of monthly returns for the selected strategy
    - sr_monthly: its monthly Sharpe (observed)
    - sr_list_monthly: list of monthly Sharpes for all N tried strategies
    """
    from scipy.stats import skew, kurtosis
    T = len(returns)
    g3 = skew(returns)
    g4 = kurtosis(returns, fisher=False)  # excess=False → normal=3
    sr_bench = dsr_benchmark(sr_list_monthly, T)
    psr = probabilistic_sharpe_ratio(sr_monthly, sr_bench, T, g3, g4)
    return psr  # probability that true SR > benchmark; treat < 0.95 as not significant
```

**Rule of thumb:** DSR < 0.95 → not significant even if raw Sharpe looks good. Use monthly returns for all inputs (not annualized).

---

## 4. Probability of Backtest Overfitting (PBO)

**Paper:** Bailey et al., "The Probability of Backtest Overfitting," JCF 2015. SSRN:2326253  
**Library:** `pip install pypbo` — https://github.com/esvhd/pypbo

Uses **Combinatorial Purged Cross-Validation (CPCV)** over `S` sub-periods to ask: what fraction of parameter configurations that are IS-optimal underperform a benchmark OOS?

```python
import pypbo as pbo
import pypbo.perf as perf
import numpy as np

def metric(x):
    """Strategy performance metric — annualized Sharpe."""
    return np.sqrt(252) * perf.sharpe_iid(x)

# rtns_df: DataFrame of daily returns, columns = parameter configurations (N strategies)
# S: number of sub-periods (8–16 typical)
pbox = pbo.pbo(
    rtns_df,
    S=16,
    metric_func=metric,
    threshold=0.0,   # benchmark (0 = beat cash)
    n_jobs=4,
    plot=False,
    verbose=False
)
print(f"PBO: {pbox.pbo:.3f}")  # fraction of trials where IS-best is OOS-worst
```

**Interpretation:**
- PBO < 0.10 → good (IS selection reliably finds OOS-good configs)
- PBO > 0.50 → severe overfitting — parameter sweep meaningless
- For a single-strategy with no parameter search: PBO = 0 (not applicable)

**Additional pypbo tools:**
- `pbo.psr(returns, sr_benchmark)` — Probabilistic Sharpe Ratio
- `pbo.min_track_record_length(sr, sr_benchmark, skew, kurt, alpha)` — minimum months needed
- `pbo.min_backtest_length(N, alpha, target_sr)` — minimum history to test N strategies

### MinTRL (Minimum Track Record Length)

Given an observed monthly Sharpe and return distribution, how many months of live track record do we need before we can be confident the strategy is real?

```python
from pypbo import min_track_record_length

# sr: monthly Sharpe (observed live)
# sr0: benchmark monthly Sharpe (e.g., 0 for cash-beat)
# skew_, kurt_: skewness and excess kurtosis of live returns
# alpha: significance level (0.05)
min_months = min_track_record_length(sr=0.15, sr0=0.0, skew_=-0.5, kurt_=1.0, alpha=0.05)
print(f"Need {min_months:.0f} months of live trading to confirm at 5% significance")
```

---

## 5. Block Bootstrap — Sharpe confidence intervals

Standard error bars on Sharpe ratios assume i.i.d. returns. Financial returns are autocorrelated (momentum, mean-reversion), so we need time-series-aware bootstrap.

**Library:** `pip install arch` — https://github.com/bashtage/arch

```python
from arch.bootstrap import StationaryBootstrap, optimal_block_length
import numpy as np
import pandas as pd

def sharpe_ratio(x):
    mu = 252 * x.mean()
    sigma = np.sqrt(252 * x.var())
    return pd.Series([mu, sigma, mu / sigma], index=["mu", "sigma", "SR"])

# returns: daily return series (pandas Series or numpy array)
# 1. Find optimal block length
opt = optimal_block_length(returns**2)  # use squared returns (autocorrelated)
block_len = opt["stationary"].iloc[0]

# 2. Run stationary bootstrap (Politis-Romano 1994)
bs = StationaryBootstrap(block_len, returns, seed=42)
results = bs.apply(sharpe_ratio, 1000)

# 3. Confidence intervals
ci = bs.conf_int(sharpe_ratio, 1000, method="percentile")
sr_ci = ci[:, 2]  # [lower, upper] for Sharpe
print(f"Sharpe 95% CI: [{sr_ci[0]:.3f}, {sr_ci[1]:.3f}]")
```

**Bootstrap variants (all in arch):**

| Class | Method | When to use |
|-------|--------|-------------|
| `StationaryBootstrap(b, data)` | Politis-Romano 1994 | Default choice — random block lengths |
| `CircularBlockBootstrap(b, data)` | Circular blocks | Wraps end to start; equal block lengths |
| `MovingBlockBootstrap(b, data)` | Fixed windows | Simple; slight edge bias |
| `IIDBootstrap(data)` | Plain resampling | Only for confirmed i.i.d. series |

Use `optimal_block_length(returns**2)` to estimate `b` — the `**2` matters because it detects autocorrelation in variance (GARCH effects).

---

## 6. White's Reality Check & Hansen's SPA test

**White (2000):** Tests whether the best strategy in a set of `N` strategies genuinely outperforms a benchmark, after accounting for data snooping. Bootstrap p-value controls FWER across all N comparisons.

**Hansen (2005) SPA (Superior Predictive Ability):** Refinement that gives more power when many strategies are clearly below benchmark (studentizes the test statistic). Preferred over White's RC.

Neither has a maintained Python package as of 2026 — implement directly with arch:

```python
from arch.bootstrap import StationaryBootstrap, optimal_block_length
import numpy as np

def reality_check(excess_returns_matrix, n_boot=999, block_len=None):
    """
    White's Reality Check p-value.
    excess_returns_matrix: (T, N) array — each column is one strategy's excess return vs benchmark
    Returns p-value: probability the best strategy beats benchmark by chance.
    """
    T, N = excess_returns_matrix.shape
    means = excess_returns_matrix.mean(axis=0)
    best_mean = means.max()
    
    if block_len is None:
        block_len = max(1, int(np.sqrt(T)))
    
    bs = StationaryBootstrap(block_len, excess_returns_matrix, seed=42)
    boot_maxes = []
    for data, _ in bs.bootstrap(n_boot):
        boot_means = data[0].mean(axis=0)
        # Re-center: subtract in-sample mean (White's correction)
        boot_maxes.append((boot_means - means).max())
    
    p_value = np.mean(np.array(boot_maxes) >= best_mean)
    return p_value
```

**Rule:** p-value < 0.05 → the best strategy is statistically significant even after data snooping correction.

---

## 7. Application to our pipeline

| Tool | When to apply | How |
|------|---------------|-----|
| **BH FDR** | After a family of related hypotheses (e.g., all alpha101 variants H215–H219) | Collect raw p-values from each OOS t-test; `multipletests(pvals, method='fdr_bh')` |
| **DSR** | After parameter sweeps (threshold tuning in H174, window scan in H198) | Pass all tried configs' monthly Sharpes as `sr_list`; require DSR > 0.95 |
| **PBO** | Only when testing 8+ parameter configs on the same data | `pypbo.pbo(rtns_df, S=16)` |
| **Bootstrap CI** | Always on confirmed hypotheses before going live | `arch.StationaryBootstrap` → Sharpe 95% CI; reject if lower bound ≤ 0 |
| **MinTRL** | After each live paper trading month | `pypbo.min_track_record_length` — tracks when paper trading crosses significance |

**Caveat (2026-08 update)**: don't add within-strategy MCPT on drawdown-family stats (MaxDD/Calmar/Ulcer) to this table as a selection filter — Gatto (SSRN, March 2026, 6B+ permutations across 437,911 configs) found it forward-predicts close to nothing over a simple IS-profitability gate, and at the portfolio level the smoothest-looking IS equity curves actually underperformed OOS by −3.48pp. See [Design Principles § MCPT Predictive Validity — 2026 Update](design-principles.md#mcpt-predictive-validity--2026-update-important-caveat) for the full writeup. IS-profitability MCPT (testing return/profit-factor, not curve shape) is unaffected by this caveat.

### H174 DSR check (example)

H174 tested ~8 threshold combinations. Monthly Sharpe of selected config ≈ 0.24 (annualized 0.83). With 22 OOS monthly observations:

```python
# All 8 threshold combo monthly Sharpes (rough estimates from OOS runs)
sr_list = [0.24, 0.18, 0.12, 0.08, 0.22, 0.15, 0.10, 0.06]
# Note: these are monthly (divide annualized by sqrt(12))

from scipy.stats import skew, kurtosis
returns_monthly = ...  # 22 monthly OOS returns from H174
dsr_pval = deflated_sharpe_ratio(returns_monthly, sr_monthly=0.24, sr_list_monthly=sr_list)
# Target: dsr_pval > 0.95
```

---

## Key references

| Paper | SSRN | Key contribution |
|-------|------|-----------------|
| Bailey & López de Prado (2014) | 2460551 | Deflated Sharpe Ratio + selection bias correction |
| Bailey et al. (2015) | 2326253 | Probability of Backtest Overfitting (CPCV) |
| Bailey & López de Prado (2012) | 1821643 | Probabilistic Sharpe Ratio + MinTRL |
| White (2000) | — | Reality Check bootstrap for data snooping |
| Hansen (2005) | — | Superior Predictive Ability test (White RC upgrade) |
| Harvey, Liu & Zhu (2016) | 2347298 | t-ratio thresholds adjusting for multiple testing in finance |

### Harvey, Liu & Zhu t-ratio thresholds

Most cited rule for academic finance publications:
- First factor ever reported: t > 1.96 (p < 0.05)
- 1990s factor: t > 2.78 (p < 0.005)  
- 2000–2012 factor: t > 3.00 (p < 0.003)
- **Current benchmark (post-2012):** t > 3.00–3.39 to be taken seriously

Our OOS t-statistics for confirmed strategies: H192 (t≈4.2), H174 (t≈3.6), H198 (t≈3.1) — all above the modern threshold.
