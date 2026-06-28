---
updated: 2026-06-16
---

# Backtesting Design Principles

These constraints must be baked into the backtesting framework from the start, not bolted on later. Sections 1–3 are prerequisites; sections 4–7 are derived from running 163+ hypotheses through this system.

**Related pages**: [Hypothesis Log](hypothesis-log.md) | [Event-Driven Strategies](../algorithms/event-driven.md) | [Momentum Strategies](../algorithms/momentum-strategies.md) | [Signal Half-Life & Alpha Decay](signal-halflife.md) | [Survivorship Bias & Universe Construction](survivorship-bias.md)

---

## 1. Macroeconomic Regime Awareness

Strategies that work in a bull market often fail in a bear market or stagflation. Backtests must be evaluated across regimes, not just in aggregate.

### Regimes to model

| Regime | Key indicators | Asset behavior |
|--------|---------------|----------------|
| Expansion | Rising GDP, low unemployment, earnings growth | Growth/tech outperform |
| Peak | High inflation, Fed tightening, yield curve flat | Rotate to value, commodities |
| Contraction/Recession | Falling GDP, rising unemployment, credit spreads widen | Defensives, cash, short duration |
| Recovery | Stimulus, loose monetary policy, credit easing | Cyclicals, small caps outperform |

### Data sources for macro context

- **FRED (Federal Reserve)**: GDP, CPI, unemployment, Fed funds rate, yield curve — free via `fredapi`
- **EDGAR**: Earnings season context, sector financials
- **VIX**: Market fear/volatility regime proxy
- **Yield curve**: 2yr/10yr spread — key recession signal

### Implementation

- Tag each backtest period with the prevailing regime
- Report strategy performance broken out by regime (not just overall Sharpe)
- Flag strategies that only work in one regime as fragile
- Use a **dual OOS window**: primary OOS (most recent ~4 years) + alternative OOS (earlier period)
  - Both windows must confirm independently — one lucky OOS period is insufficient

---

## 2. Tax Burden

High gross returns can become mediocre after-tax returns, especially for high-turnover strategies.

### Key rules (US, 2026)

| Holding period | Tax treatment | Rate (approx, single filer) |
|---------------|--------------|---------------------------|
| < 1 year | Short-term capital gains | Ordinary income rate (up to 37%) |
| ≥ 1 year | Long-term capital gains | 0%, 15%, or 20% |
| Options (equity) | Short-term unless exercised into long-term position | Same as STCG |
| Index options (1256 contracts) | 60% long-term / 40% short-term (60/40 rule) | Blended ~26.8% max |

### Practical impact

- A momentum strategy with monthly rebalancing: all gains are STCG — subtract ~37% from gross returns
- **Rule of thumb**: high-turnover strategies need ~1.5–2× the gross return of low-turnover strategies to net the same after-tax income

### Wash sale rule

Selling at a loss and buying back within 30 days disallows the loss. High-frequency tax-loss harvesting strategies must track this carefully.

---

## 3. Real-World Costs to Model

- **Slippage**: 0.05–0.1% per trade for liquid large-caps; more for small-caps
- **Commission**: Alpaca is commission-free, but PFOF means fills may not be at best price
- **Bid-ask spread**: 1–5% of premium for short-dated options
- **Margin costs**: ~5–8% annually if using leverage
- **Dividends**: include in total return calculations

---

## 4. IS/OOS Validation Framework

The most important discipline in our backtesting system. A strategy that looks great in-sample but fails OOS is worthless.

### Split methodology

```
|─── In-Sample (IS) ────────────────────|── OOS ──────|── AltOOS ──|
   ~10 years for parameter estimation      ~4 years       ~4 years
   DO NOT touch after parameter lock       Primary test   Secondary test
```

- **IS**: Parameter selection, model training, threshold calibration. Touch freely.
- **OOS**: First out-of-sample test. Never adjust parameters after seeing OOS results.
- **AltOOS**: Independent second period (often earlier data). Guards against lucky OOS.
- Confirm criteria require BOTH OOS windows to pass independently.

### IS/OOS Sharpe gap as overfitting signal

From 163+ hypothesis tests, these thresholds identify overfitting:

| IS/OOS gap | Interpretation |
|-----------|----------------|
| IS Sharpe ≈ OOS Sharpe | Clean generalisation |
| IS Sharpe 2× OOS | Moderate overfitting — worth investigating |
| IS Sharpe 4× OOS | Severe overfitting — reject or redesign |
| IS Sharpe > 1.5 but OOS < 0.3 | Structural decay / regime change |

**Real example from H159b (beta-neutral PEAD)**:
IS Sharpe = 1.6, OOS Sharpe = 0.38 → ratio 4.2× → confirmed structural decay of PEAD post-2018 (HFT arbitrage eroded the drift).

### T-statistic threshold for event studies

For event-based strategies (PEAD, dividend raises, etc.), require:

```
t-stat = mean_return / (std_return / sqrt(n))  ≥  2.0  (p < 0.05)
```

- Our minimum: **t-stat ≥ 2.0** in OOS to consider the raw event effect real
- H159 gap-up drift: OOS t-stat = 5.64 → effect confirmed even with poor portfolio metrics
- H161 dividend raise: OOS t-stat = 4.10 → effect confirmed

A strategy with a real event effect but poor portfolio Sharpe is still valuable — it tells you the signal is real and the problem is execution/portfolio construction, not signal quality.

### Walk-forward validation

For strategies with rolling parameter updates (adaptive strategies), use walk-forward analysis:

```
|─ IS ─|─ WF1 ─|─ WF2 ─|─ WF3 ─| ... |─ OOS ─|
  Train   Test    Re-train  Test           Test
          ↓ roll window
```

1. Train on window [t₀, t₀ + IS_length]
2. Test on next [t₀ + IS_length, t₀ + IS_length + WF_step]
3. Roll forward: new IS = [t₀ + WF_step, t₀ + IS_length + WF_step], repeat
4. Concatenate all WF test periods into an out-of-sample equity curve

This is the industry standard for momentum strategies because parameters (lookback windows, thresholds) can drift over time. Our static H026 ETF rotation uses simple IS/OOS split instead because the signal is highly robust and low-parameter.

---

## 5. Bias Detection and Prevention

### Five bias types ranked by impact

**1. Survivorship bias** (most dangerous)
- Definition: using today's index members to represent the past
- Impact: eliminates all stocks that went bankrupt, merged, or were delisted
- Example: 5-stock momentum strategy Sharpe 0.09 → 0.66 when including delistings
- **Prevention**: use point-in-time constituent lists (CRSP, Compustat) or explicitly note the bias in results
- Our system: CONFIRMED caveats always note survivorship bias where applicable

**2. Look-ahead bias**
- Definition: using information that wasn't available at the trade entry time
- Examples:
  - Using earnings announced after close as "same-day" signal
  - Using revised GDP figures (FRED data is revised retroactively)
  - Forward-split-adjusted prices for older data without checking split dates
- **Prevention**: always use `earnings_dates` with time-of-day; check FRED for real-time vs revised data; use `auto_adjust=True` only after validating corporate action dates

**3. Data snooping / multiple testing bias**
- Definition: running 100 parameter combinations and reporting the best
- The López de Prado / Bailey **Deflated Sharpe Ratio (DSR)** corrects for this:

```python
import numpy as np
from scipy.stats import norm

def deflated_sharpe_ratio(sr_hat, n_trials, sr_std, obs_length, skew=0, kurt=3):
    """
    Corrects SR for multiple testing and non-normality.
    sr_hat: observed Sharpe (annualized)
    n_trials: number of parameter combinations tested
    sr_std: expected std of SR across trials
    obs_length: number of monthly observations
    """
    # Expected maximum SR from n_trials draws of N(0, sr_std)
    e_max = sr_std * ((1 - np.euler_gamma) * norm.ppf(1 - 1/n_trials)
                      + np.euler_gamma * norm.ppf(1 - 1/(n_trials * np.e)))
    
    # Adjusted SR accounting for non-normality
    sr_adj = sr_hat * np.sqrt(obs_length) / np.sqrt(
        1 - skew * sr_hat + (kurt - 1)/4 * sr_hat**2
    )
    dsr = norm.cdf((sr_adj - e_max) / np.sqrt(1 / obs_length))
    return dsr  # probability SR is genuine (not from chance)
```

- Practical rule: if you tested more than 10 parameter combinations, divide your OOS Sharpe by ~1.3 as a rough deflator
- Our H026 rotation: ~5 parameters tested → modest multiple-testing concern; OOS Sharpe 3.0 → deflated ~2.3 (still excellent)

**4. Overfitting via parameter mining**
- Danger signal: IS/OOS gap > 4×, or OOS Sharpe > 3.0 on first attempt (too good)
- Red flags from AQR: moving average strategy dropped from Sharpe 1.2 (IS) to −0.2 (OOS)
- **Prevention**: freeze parameters at IS-end; use fewer free parameters; require monotonic sensitivity (if strategy only works at one specific threshold, it's overfit)

**5. Reporting bias**
- Definition: only publishing winners; hiding failed hypotheses
- **Prevention**: maintain a complete hypothesis log with ALL results, including NOT CONFIRMED — this is mandatory in our system
- Hypothesis log at `backtesting/hypothesis-log.md` contains all 163+ results including failures

---

## 6. Confirmation Criteria System

We use a tiered confirmation system based on lessons from H001–H163:

### Tier 1: Raw event effect (event studies)
Minimum to proceed — the underlying effect must be real:
```
OOS t-stat ≥ 2.0 (p < 0.05)
OOS n ≥ 30 events
```

### Tier 2: Portfolio-level confirmation (full CONFIRMED)
```
OOS Sharpe ≥ 1.0
OOS MaxDD ≥ −20%  (less severe than −20%)
OOS WinRate ≥ 55%  (or positive mean return with high t-stat)
Both OOS + AltOOS pass
```

### Tier 3: PARTIAL CONFIRMED
```
Genuine event effect confirmed (t-stat ≥ 2.0)
Portfolio metrics don't meet all 3 criteria above
Known root cause for the gap (beta, idiosyncratic risk, data limitations)
Improvement path exists
```

### Historical outcomes from 163+ tests

| Verdict | Count | Typical root cause |
|---------|-------|-------------------|
| CONFIRMED | ~30 | Robust signal, proper construction |
| PARTIAL CONFIRMED | ~15 | Real signal, portfolio problem (beta, regime) |
| NOT CONFIRMED | ~80 | Signal weak OOS or structural decay |
| BLOCKED | ~10 | Data unavailable or methodology flaw |
| IN-PROGRESS | ~5 | Currently running |

**Key insight**: NOT CONFIRMED is valuable data — it tells you what *doesn't* work and why. The hypothesis log preserves all failure modes.

---

## 7. Performance Metrics (after-tax)

Report in this order for every hypothesis:

```
Primary:
  OOS Sharpe ratio
  OOS MaxDrawdown
  OOS Cumulative return (×)
  OOS Win rate (event studies)
  OOS Mean return per event

Secondary:
  AltOOS Sharpe (independent confirmation)
  IS/OOS ratio (overfitting flag)
  Corr(SPY) — market beta exposure
  t-statistic on mean return
  Number of events / observations

Context:
  IS Sharpe (for gap check)
  Negative years count
  CAGR
```

### Sharpe calibration reference

| Sharpe | Quality |
|--------|---------|
| < 0.5 | Poor — don't deploy |
| 0.5–1.0 | Marginal — track only |
| 1.0–2.0 | Good — paper trade |
| 2.0–4.0 | Excellent — move to live |
| > 4.0 | Suspicious — check for bias; if clean, deploy at lower leverage |

Our production portfolio (H026 sector rotation): OOS Sharpe 3.007 — verified across multiple OOS windows and 20+ years of data.

### After-tax Calmar ratio

```python
def after_tax_calmar(gross_cagr, max_dd, tax_rate=0.37, turnover=1.0):
    """
    turnover: annual portfolio turnover (1.0 = 100%)
    Returns after-tax Calmar (CAGR/MaxDD).
    """
    tax_drag = gross_cagr * turnover * tax_rate
    after_tax_cagr = gross_cagr - tax_drag
    return after_tax_cagr / abs(max_dd)
```

---

## 8. NLP / ML Strategy Additional Checks

For FinBERT, GPT-4o-mini, ElasticNet, and similar ML-based strategies:

### IS sample size requirements

| Model type | Minimum IS events |
|-----------|------------------|
| Simple threshold (SUE > X) | 50 |
| Logistic regression | 200 |
| ElasticNet multi-factor | 500 |
| Fine-tuned transformer | 5,000+ |
| Zero-shot FinBERT | 30 (model pre-trained) |

FinBERT is zero-shot (no fine-tuning) — lower IS requirement. H163 had IS=112 events, sufficient.

### Data snooping in NLP threshold selection

After running a threshold sweep (e.g., finbert_score > 0.10, 0.15, 0.20…), the chosen threshold has been selected from multiple trials. Apply a ~1.3× Sharpe deflation or require the threshold effect to be monotonic (higher threshold → higher win rate, not just one lucky threshold level).

### Model staleness risk

Pre-trained models like FinBERT were trained on financial text from specific eras. Check:
- Is the training corpus era-appropriate? (FinBERT: Reuters/Bloomberg 2007-2018)
- Does OOS performance degrade monotonically over time (model aging)?
- Is the signal still present in the most recent 12 months?

---

## 9. Practical Pipeline

```
1. Literature search: find academic anchor with replication code or clear method
2. IS design: define signal, entry/exit rules, hold period
3. IS calibration: test 3–5 parameter variants on IS only
4. Lock parameters: freeze all choices; never look at OOS until this step
5. OOS run: single pass; record all metrics
6. Verdict: apply confirmation criteria
7. AltOOS confirmation: independent second window
8. Log: add full result to hypothesis-log.md (pass or fail)
9. If CONFIRMED: paper trade → live
10. If NOT CONFIRMED: document root cause; flag improvement paths
```

---

## Further Reading

- Bailey & López de Prado (2014) — "The Deflated Sharpe Ratio" — SSRN 2460551
- Bailey et al. (2016) — "The Probability of Backtest Overfitting" — SSRN 2326253
- López de Prado (2018) — *Advances in Financial Machine Learning* (AFML)
- Combinatorial Purged Cross-Validation (CPCV): López de Prado 2020, for ML strategies with time-series data
- QuantStart: [Successful Backtesting Part I](https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-I/)

**Related pages**: [Walk-Forward & CPCV](walk-forward-cpcv.md) | [Transaction Cost Modeling](transaction-costs.md) | [Hypothesis Log](hypothesis-log.md) | [Signal Half-Life & Alpha Decay](signal-halflife.md) | [Survivorship Bias & Universe Construction](survivorship-bias.md)


---

## Monte Carlo Permutation Test (MCPT) — Reference

**Source**: Phosphen (@phosphenq) long-form thread, May 2026 — https://x.com/phosphenq/status/2057129225593741768
**Original book**: Timothy Masters, *Permutation and Randomization Tests for Trading System Development* (2020)
**Open-source impl**: `mcpt` by neurotrader888 on GitHub

MCPT answers: "Could a worthless strategy have looked this good on random noise?"

Every backtest sits somewhere on the spectrum between pure alpha and pure data-mining bias. MCPT tells you where.

### How it works

Decompose each OHLC bar into 5 relative components (gap, intra-bar high/low/close). Shuffle the intra-bar trio (h/l/c) together and gaps separately. Reassemble from original first bar. Result: same first open, same last close, same return distribution, same vol/skew/kurtosis — but all patterns destroyed.

```python
# pip install mcpt  (neurotrader888 open-source)
# or use get_permutation() from the SSRN article code

def run_insample_mcpt(df, optimize_fn, n_permutations=1000):
    real_lb, real_pf = optimize_fn(df)
    perm_better_count = 1
    for i in range(1, n_permutations):
        perm = get_permutation(df, seed=i)
        _, perm_pf = optimize_fn(perm)
        if perm_pf >= real_pf:
            perm_better_count += 1
    return perm_better_count / n_permutations  # p-value
```

### Thresholds

- **p < 1%**: strong pass — fewer than 10 of 1,000 random shuffles beat the strategy
- **p < 5%**: acceptable for short data history (< 1yr walk-forward window)
- **p ≥ 5%**: fail — optimization is eating noise

### Two tests in sequence

1. **In-sample MCPT**: does the optimized IS performance beat permuted-data IS performance? Catches overfitting early, before spending OOS data.
2. **Walk-forward MCPT**: re-run full WF on 200+ permuted series (only the post-training-window data permuted; training data stays real). Catches lucky sample-path alignment.

### Failure modes MCPT can't catch

- **Volatility-clustering strategies**: MCPT destroys vol clustering (GARCH-style regimes look "easier" on permuted data → optimistic bias against the strategy). Fix: block bootstrap (5–10 bar blocks).
- **Lead-lag multi-market strategies**: default shuffle preserves contemporaneous correlation but destroys lead-lag → MCPT incorrectly rejects real edge. Fix: phase-randomization in frequency domain.
- **Target-fiddling**: iterating strategy parameters until MCPT passes = data-mining the test. Fix: lock strategy spec before running MCPT. If it fails, discard — don't tweak.

### Our backtest integration status

- Currently NOT applied to confirmed strategies (H026, H181, H192-D, H198, H201).
- IS/OOS split + Sharpe threshold + Deflated Sharpe Ratio is our current framework.
- MCPT would be a stronger secondary validation, especially for strategies with many optimized parameters.
- IAF (Investing Algorithm Framework) has Monte Carlo permutation testing built in — potential integration point.
- **Queued action**: apply MCPT to all confirmed strategies as a retrospective audit.

---

## Monte Carlo Equity Curve Simulation (Stats Edge, 2026-05-29)

Source: Stats Edge Trading "The 25-Year Backtest" — visualizing the distribution of equity paths under random trade sequencing.

### What it is

Rather than (or in addition to) permuting the data, resample the **trade return sequence** itself. Given a set of N historical trade returns:
1. Draw N returns with replacement from the empirical trade distribution
2. Compute the cumulative equity curve
3. Repeat 100–1,000 times
4. Plot the distribution of equity paths; highlight worst 5%

This shows the range of plausible outcomes from the same edge, under different luck in trade ordering.

### Why it's valuable (different from MCPT)

- MCPT asks: "Is this edge real or noise?" Monte Carlo equity simulation asks: "If the edge is real, what's the worst realistic outcome?"
- It answers: what drawdown should a live trader expect in the worst 5% of luck? This is the number to use for position sizing.
- Stats Edge shows that even with a confirmed edge and positive 26-year equity curve, individual simulated paths can hit −20% drawdowns. Without seeing this, a live trader stops out of a real edge during a bad-luck streak.

### Implementation sketch

```python
def monte_carlo_equity(trade_returns, n_sims=500, n_trades=None):
    """Simulate equity paths by resampling trade return sequence."""
    returns = np.array(trade_returns)
    n = n_trades or len(returns)
    equity_paths = []
    for _ in range(n_sims):
        sample = np.random.choice(returns, size=n, replace=True)
        equity = np.cumprod(1 + sample)
        equity_paths.append(equity)
    equity_matrix = np.array(equity_paths)
    
    percentiles = {
        "p5":    np.percentile(equity_matrix[:, -1], 5),
        "p25":   np.percentile(equity_matrix[:, -1], 25),
        "p50":   np.percentile(equity_matrix[:, -1], 50),
        "p75":   np.percentile(equity_matrix[:, -1], 75),
        "p95":   np.percentile(equity_matrix[:, -1], 95),
        "max_dd_p5": min(
            (np.min(p / np.maximum.accumulate(p)) - 1) for p in equity_matrix[:int(n_sims * 0.05)]
        ),
    }
    return equity_matrix, percentiles
```

### When to apply

After a strategy passes OOS confirmation, before going live:
1. Extract the trade-by-trade return series from the OOS period
2. Run 500 Monte Carlo simulations
3. Report the p5 ending equity and p5 max drawdown
4. Set position size so that p5 max drawdown ≤ acceptable loss (e.g., 10% of allocated capital)

### Queued action

Apply to all confirmed production strategies (H026, H041a, H045, H174, H181, H192-D, H217, H228) to establish realistic drawdown bounds for live position sizing.


---

## GT-Score: Composite Objective for Reducing Overfitting (2026)

**Source:** arXiv:2602.00080 — Sheppert (Jan 2026). "The GT-Score: A Robust Objective Function for Reducing Overfitting in Data-Driven Trading Strategies."

The GT-Score addresses Sharpe ratio's vulnerability to in-sample overfitting by combining four dimensions:

| Dimension | What it measures |
|-----------|------------------|
| Performance | Return-adjusted returns |
| Statistical significance | p-value on returns vs null |
| Consistency | Uniformity of returns across sub-periods |
| Downside risk | Drawdown and negative return frequency |

**Key result:** 98% relative improvement in IS→OOS generalization ratio vs Sharpe-only optimization. Tested on 50 S&P 500 stocks 2010-2024 with 9 sequential time splits and 15 random seeds (p < 0.01).

**Practical application for our pipeline:**
- When running parameter sweeps (e.g., selecting TSMOM threshold, blend ratios, vol-target), use GT-Score as the optimization objective instead of IS Sharpe
- GT-Score should be computed on the IS period; OOS Sharpe is still the validation metric
- Particularly valuable for H202-XL (200-stock XGBoost) where hyperparameter search risk is high

**Implementable approximation:**
```python
def gt_score(monthly_returns, alpha=0.05):
    """Approximate GT-Score composite objective.
    Returns positive float; higher = better generalization."""
    from scipy import stats
    import numpy as np
    r = np.array(monthly_returns)
    if len(r) < 12:
        return -np.inf
    # Performance dimension
    ann_sharpe = r.mean() / r.std(ddof=1) * np.sqrt(12)
    # Statistical significance
    t_stat, p_val = stats.ttest_1samp(r, 0, alternative='greater')
    sig = (1 - p_val) if not np.isnan(p_val) else 0
    # Consistency (fraction of positive months)
    consistency = (r > 0).mean()
    # Downside risk (inverse of MaxDD severity)
    cumr = np.cumprod(1 + r)
    max_dd = (cumr / np.maximum.accumulate(cumr) - 1).min()
    downside = 1 + max_dd  # 0 = total loss, 1 = no drawdown
    # Composite (equal weights; tune as needed)
    return np.mean([ann_sharpe / 3, sig, consistency, downside])
```

**Limitation:** No public code released with the paper. The above is a practical approximation based on the paper's described dimensions.

## Minimum Regime Performance (MRP) — Strategy Durability Metric

**Source**: arXiv:2604.08356 (Alexander & Fabozzi, 2026). Published in Journal of Portfolio Management.

MRP = the **lowest realized risk-adjusted return across distinct historical regimes** (bull market, bear market, rising rates, low-vol, high-vol, crisis).

**Key insight**: "Strategies with higher long-term Sharpe ratios do not always exhibit higher MRPs." A high aggregate Sharpe can mask catastrophic failure in one regime — which is exactly how real capital gets lost.

### Practical application to our pipeline

For any confirmed hypothesis (Sharpe gate met), additionally report:
1. **MRP across 4 regimes**: bull (SPY > 200MA, VIX < 20), bear (SPY < 200MA, VIX > 20), rate-rising (T10Y2Y inverted), rate-falling
2. **Worst-regime Sharpe**: minimum Sharpe across these 4 states
3. **Regime coverage**: did the OOS window include all 4 regimes? 2022 = bear+rate-rising; 2020 = crisis; 2019 = bull+low-vol

```python
def compute_mrp(returns: pd.Series, regime_labels: pd.Series) -> dict:
    """
    Compute MRP: min Sharpe across regimes.
    regime_labels: pd.Series aligned to returns with categorical regime names.
    Returns dict of {regime: sharpe, 'MRP': min_sharpe}.
    """
    import numpy as np
    regime_sharpes = {}
    for regime in regime_labels.unique():
        mask = regime_labels == regime
        r = returns[mask]
        if len(r) < 12:  # skip regimes with < 12 months of data
            continue
        sharpe = r.mean() / r.std() * np.sqrt(12)
        regime_sharpes[regime] = round(sharpe, 3)
    regime_sharpes['MRP'] = min(regime_sharpes.values()) if regime_sharpes else None
    return regime_sharpes
```

**Minimum standard**: MRP > 0 (strategy never loses money on a risk-adjusted basis in any regime). MRP > 0.4 = robust.

**Applied to confirmed hypotheses** — regimes based on H249 4-state (SPY 200MA × VIX):
- H026 (sector rotation): MRP pending — 2022 bear regime is the critical test
- H041a (19-asset top-1): MRP pending — check 2022 bear regime
- H273 (vol-targeting overlay): confirmed — reduces MRP variance by dampening bear-regime exposure
- H270 (low-vol dual ranking): confirmed — check rate-rising regime (2022-2023 known weakness per H245)


---

## External Validation: LLM Trading Paper Reproducibility Crisis

**Source:** Xia et al. (2026), "Agentic Trading: When LLM Agents Meet Financial Markets," arXiv:2605.19337

An audit of 19 LLM trading studies found:
- Only **2 of 19** had extractable, time-consistent IS/OOS split protocols
- Only **1 of 19** documented explicit transaction costs
- **0 of 19** achieved R3 reproducibility level (open code + data + results)

This validates George's backtesting discipline: fixed IS/OOS windows, lagged signals (shift(1)), realistic cost models, and committed result JSONs. When evaluating papers for hypothesis proposals, require at minimum: stated IS/OOS dates, transaction cost model, and specific Sharpe/MaxDD numbers before staging.

---

## Mask-First Contamination Prevention (arXiv:2507.07107, 2025)

**Problem:** Standard ML pipelines apply cross-sectional normalization (z-score, rank) or rolling imputation *before* the train/test split. This leaks future distribution information into the training window — a subtle but significant look-ahead bias.

**Mask-first rule:** Apply any preprocessing that sees cross-sectional data (normalization, imputation, rolling stats) with future dates masked to NaN *before* computing the feature. Only then split into train/test.

**Measured impact:** +0.44 Sharpe points contamination inflation on Chinese A-shares. Pipelines not following this rule systematically overstate backtested performance.

**Check these in our run_hNNN.py scripts:**
- `df.rolling(N).mean()` is safe — backward-looking by construction
- `df.rank(axis=0)` on the full DataFrame **is contaminated** if axis=0 is the time axis
- `df.rank(axis=1)` (cross-sectional rank at each time step) is safe
- `StandardScaler().fit_transform(X)` on full X **is contaminated** — must fit on train only
- `df.fillna(df.mean())` **is contaminated** if mean computed on full sample

**GPU speedup:** PyTorch vectorized rolling ops are 51× faster than pandas `.rolling()` for large cross-sections (relevant for H303 crypto momentum with 30+ coins).

**Action items:**
- In H303 (crypto cross-sectional momentum): ensure `mom.rank(axis=1)` not `rank(axis=0)` ✓ (our code already uses axis=1 by default in `.rank(pct=True)` along columns)
- In H304 (LLM PEAD): fit sentence-BERT scaler on IS only, apply to OOS
- When adding ML models: always use `Pipeline` with `TimeSeriesSplit` to enforce mask-first

See also: [Hypothesis Log](hypothesis-log.md) (H256 look-ahead bias note: .shift(1) on r12 signal), [Crypto Trading Strategies](../algorithms/crypto-trading-strategies.md) (H303 implementation)

## Tradability Mask: Single Largest Bias Driver (arXiv:2507.07107)

**Source:** arXiv:2507.07107 (ML Enhanced Multi-Factor Quantitative Trading, 2025)

**Finding:** In a 213-factor PyTorch-vectorized cross-sectional system, a Boolean *tradability mask* — constructed at data load time and threaded through every computational operator — was the single largest performance contributor, adding +0.44 Sharpe-points in ablation. Without it, the system learned to predict returns it could never actually trade (price-limit violations in Chinese A-shares), inflating apparent IC by ~18%.

**US market analog:**
- Halted stocks, low-float stocks with thin liquidity, or stocks with gaps > 10% on signal date should be masked at the factor-computation step, not filtered post-hoc
- ETF creation/redemption mechanics can cause similar distortions in ETF rotation backtests
- For PEAD (H174): stocks with trading halts around earnings announcements should be masked before scoring

**Implementation pattern:**
```python
# Mask non-tradable rows BEFORE factor computation
is_tradable = (
    df['volume'] > 100_000     # minimum liquidity
    & df['close'] > 1.0        # minimum price (penny stock filter)
    & ~df['halt_flag']         # not halted
    & df['close'].notna()      # no data gaps
)
df_clean = df[is_tradable].copy()  # Apply FIRST, then compute factors
# NEVER: compute factors on full df, then filter afterwards
```

**Performance (China A-share 2022-2024):** IS Sharpe 2.05, OOS Sharpe 1.63, Deflated Sharpe 0.978. US market transfer not yet tested.

**Lesson for H217/H228 (alpha101):** The alpha101 formula library computes signals on full price history. Adding a tradability mask before computing each alpha could improve IC and reduce overfitting on illiquid/halted events.

---

## Prediction Market Backtesting (PredictionMarketBench)

**Source**: arXiv:2602.00133 (Arora & Malpani, Feb 2026)
**GitHub**: [Oddpool/PredictionMarketBench](https://github.com/Oddpool/PredictionMarketBench)

The first SWE-bench-style framework for deterministic, event-driven replay of historical Kalshi prediction market data. Enables reproducible backtesting of trading agents before live deployment.

### What it provides
- **Episode replay**: historical Kalshi LOB data (orderbooks, trades, lifecycle, settlement) parsed into 4 episodes (crypto, weather, sports)
- **Execution-realistic simulator**: maker/taker semantics, fee modeling (maker ~0% vs taker ~2%)
- **Agent interface**: tool-calling LLM agents or classical strategy code; reproducible trajectories

### Baseline results (4 episodes)

| Agent | PnL | MaxDD | Key insight |
|-------|-----|-------|-------------|
| RandomAgent | −0.13% | ~0% | fee drag only |
| GPT-4.1-nano | **−2.77%** | 36% | taker fees + wrong direction |
| Bollinger Bands (post-only) | **+1.67%** | 3.18% | maker orders avoid fee drag |

### Critical lesson
Fee structure dominates at small scale. Taker fees on Kalshi (~2%) erode LLM agent returns even when directionally correct. The Bollinger Bands strategy wins by:
1. Using post-only limit orders (maker, near-zero fee)
2. Mean-reverting logic that happens to work on volatile BTC episode
3. Conservative sizing that limits drawdown

**Implication for H185**: Any Kalshi agent we deploy must use **post-only limit orders** only. Market orders (taker) on Kalshi will drain returns even if the CPI nowcast is correct. Build limit-order logic into pead_overnight.py equivalent for PM trades.

### Integration with H185

```bash
git clone https://github.com/Oddpool/PredictionMarketBench
cd PredictionMarketBench
pip install -r requirements.txt
# Run Bollinger Bands baseline to validate setup
python run_agent.py --agent bollinger_bands --episodes all
# Then swap in H185-style CPI signal agent
python run_agent.py --agent h185_cpi --episodes crypto weather
```
