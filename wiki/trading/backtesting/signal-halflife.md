---
title: Signal Half-Life & Alpha Decay Measurement
added: 2026-05-31
category: backtesting / methodology
---

# Signal Half-Life & Alpha Decay Measurement

How long does a trading signal remain useful before it decays? This page covers the
measurement methodology, current empirical estimates for common factor classes, and
practical implications for IS/OOS window design and retraining frequency.

---

## 1. What is signal half-life?

The **half-life** of a signal is the lag `T` at which the signal's Information Coefficient
(IC) — or raw autocorrelation for the spread itself — falls to 50% of its initial value.

A signal with a 3-month half-life loses half its predictive edge every 3 months. One with a
3-year half-life is durable across multiple economic cycles.

Half-life determines:
- **Optimal holding period**: match your trade horizon to the signal's persistence window
- **IS window length**: IS period should span at least 3–5 half-lives to observe full decay
- **Retraining frequency**: retrain (or re-validate) at intervals no longer than the half-life
- **OOS window interpretation**: an OOS window shorter than one half-life may look strong even
  if the signal is dead — you haven't waited long enough to see decay

---

## 2. Computing half-life from autocorrelation

The simplest measurement: fit an AR(1) to the signal's spread (or rank IC time series) and
read off the half-life from the lag-1 autocorrelation φ.

```python
import numpy as np
import pandas as pd

def signal_halflife(series: pd.Series, method: str = "ar1") -> float:
    """
    Estimate signal half-life from spread or IC time series.

    Parameters
    ----------
    series : pd.Series
        The spread/residual series (for mean-reversion) or rolling IC series
        (for cross-sectional factor decay). Must be stationary (demeaned).
    method : 'ar1' | 'regression'
        ar1       : uses lag-1 autocorrelation directly
        regression: OLS regress series[t] on series[t-1], get beta; safer for noisy series

    Returns
    -------
    half_life : float (in same units as the series frequency)
    """
    series = series.dropna()

    if method == "ar1":
        phi = series.autocorr(lag=1)
        if phi <= 0 or phi >= 1:
            return float("inf") if phi >= 1 else 0.0
        return np.log(0.5) / np.log(phi)

    elif method == "regression":
        y = series.iloc[1:].values
        x = series.iloc[:-1].values
        phi = np.dot(x, y) / np.dot(x, x)  # OLS slope with no intercept
        if phi <= 0 or phi >= 1:
            return float("inf") if phi >= 1 else 0.0
        return np.log(0.5) / np.log(phi)

# Example: monthly IC time series for a 12-month momentum factor
# ic_series = pd.Series([...], index=pd.date_range('2013-01', periods=120, freq='ME'))
# hl = signal_halflife(ic_series, method='ar1')
# print(f"Factor half-life: {hl:.1f} months")
```

**Interpretation table**:

| Half-life | Signal class | Action |
|-----------|-------------|--------|
| < 1 bar | Noise / instant reversion | Scalping or discard |
| 1–5 bars | Intraday / short-term mean-reversion | Day-trade horizon; match execution timing |
| 5–20 bars | Swing / IBS-style | Weekly mean-reversion (H112/IBS strategies) |
| 1–6 months | Factor / trend following | Monthly rebalance makes sense |
| > 1 year | Fundamental / quality factor | Annual rebalance; long IS window required |

---

## 3. Rolling IC as decay diagnostics

Track **rolling Information Coefficient** to detect whether a signal's predictive power is
declining over calendar time. This diagnoses alpha decay vs. alpha stability.

```python
def rolling_ic_decay(signal_df: pd.DataFrame,
                     returns_df: pd.DataFrame,
                     window: int = 12) -> pd.Series:
    """
    Compute rolling cross-sectional IC between signal ranks and forward returns.

    signal_df  : stocks × time, signal values at rebalance date
    returns_df : stocks × time, 1-period forward returns at each date
    window     : rolling window in periods (e.g., 12 for 12-month rolling)
    """
    dates = signal_df.columns.intersection(returns_df.columns)
    ic_series = []
    for t in dates:
        sig = signal_df[t].dropna()
        ret = returns_df[t].dropna()
        common = sig.index.intersection(ret.index)
        if len(common) < 5:
            ic_series.append(np.nan)
            continue
        from scipy.stats import spearmanr
        rho, _ = spearmanr(sig[common], ret[common])
        ic_series.append(rho)

    ic = pd.Series(ic_series, index=dates).dropna()
    rolling_ic = ic.rolling(window).mean()

    # Compute half-life of the rolling IC trend
    ic_hl = signal_halflife(ic, method='regression')
    print(f"IC time-series half-life: {ic_hl:.1f} periods")
    print(f"Mean IC (full period): {ic.mean():.4f}")
    print(f"IC ratio (last 2yr / first 2yr): {ic.tail(24).mean() / ic.head(24).mean():.3f}")

    return rolling_ic


# Usage diagnostic:
# If IC ratio last_2yr / first_2yr < 0.6: signal is decaying fast — consider retraining or retiring
# If IC ratio > 0.9: signal is stable — IS/OOS comparison is reliable
```

---

## 4. Decay functions: empirical evidence

**From arXiv:2512.11913 (Dec 2025) — "Not All Factors Crowd Equally":**

Factor alphas follow different decay functional forms:

| Factor type | Best-fit decay model | R² | Decay mechanism |
|-------------|--------------------|----|-----------------|
| Momentum | Hyperbolic: α(t) = K/(1+λt) | 0.65 | Mechanical factor flows + ETF crowding |
| Reversal | Hyperbolic | ~0.60 | High-frequency arbitrage |
| Value | No clear decay | — | Signal-ambiguity barriers to crowding |
| Quality | No clear decay | — | Requires judgment; hard to crowd |

**Hyperbolic vs exponential for momentum**:
```python
from scipy.optimize import curve_fit
import numpy as np

def hyperbolic_decay(t, K, lam):
    return K / (1 + lam * t)

def exponential_decay(t, K, lam):
    return K * np.exp(-lam * t)

def fit_decay_model(t_vals, alpha_vals):
    """
    Fit both decay models and compare R².
    t_vals: time index (months since signal discovery)
    alpha_vals: rolling Sharpe or IC at each time
    """
    # Hyperbolic fit
    p_hyp, _ = curve_fit(hyperbolic_decay, t_vals, alpha_vals, p0=[alpha_vals[0], 0.01],
                          bounds=([0, 0], [np.inf, np.inf]), maxfev=5000)
    hyp_pred = hyperbolic_decay(t_vals, *p_hyp)
    ss_res = np.sum((alpha_vals - hyp_pred) ** 2)
    ss_tot = np.sum((alpha_vals - np.mean(alpha_vals)) ** 2)
    r2_hyp = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # Exponential fit
    p_exp, _ = curve_fit(exponential_decay, t_vals, alpha_vals, p0=[alpha_vals[0], 0.01],
                          bounds=([0, 0], [np.inf, np.inf]), maxfev=5000)
    exp_pred = exponential_decay(t_vals, *p_exp)
    ss_res_e = np.sum((alpha_vals - exp_pred) ** 2)
    r2_exp = 1 - ss_res_e / ss_tot if ss_tot > 0 else 0

    print(f"Hyperbolic R²={r2_hyp:.3f}, λ={p_hyp[1]:.4f}")
    print(f"Exponential R²={r2_exp:.3f}, λ={p_exp[1]:.4f}")

    if r2_hyp > r2_exp:
        implied_hl_hyp = 1 / p_hyp[1]  # hyperbolic: HL = 1/λ (when K/(1+λt) = K/2 → t = 1/λ)
        print(f"Best fit: hyperbolic. Implied half-life: {implied_hl_hyp:.1f} months")
    else:
        implied_hl_exp = np.log(2) / p_exp[1]
        print(f"Best fit: exponential. Implied half-life: {implied_hl_exp:.1f} months")

    return r2_hyp, r2_exp
```

---

## 5. AI-driven half-life compression

**From arXiv:2605.23905 (May 2026) — "AI-Driven Alpha Decay":**

The paper derives an equilibrium half-life formula incorporating AI adoption:

```
h(φ) = ln(2) / [θ + δ(φ)]
```

Where:
- `θ ≈ 0.012 month⁻¹` = natural mean-reversion rate (baseline, pre-AI era)
- `φ ≈ 0.7` = current AI adoption level across institutional market participants
- `δ(φ)` = AI-accelerated decay: convex function of adoption (crowding + performative erosion)
- At φ ≈ 0.7: implied half-life **~18 months** vs pre-AI **5–7 years (≈60–84 months)**

**Three decay channels** at high AI adoption:
1. **Signal crowding**: many participants discover the same signal → faster arbitrage
2. **Performative erosion**: the signal's own trading impact changes the data it predicts
3. **Red Queen competition**: rival systems continuously improve, requiring constant improvement to maintain edge

**Empirical calibration**: SEC 13F data (2013–2024, 99.5M holdings) shows 42% increase in
portfolio convergence among institutions — consistent with signal homogenization.

**Practical implication for our backtesting**:

| Factor class | Pre-AI HL (McLean & Pontiff 2016) | Estimated 2026 HL |
|-------------|----------------------------------|------------------|
| Short-term reversal | ~3 months | ~1–2 months |
| Cross-sectional momentum (12-1m) | ~18 months | ~10 months |
| Value (P/B, P/E) | ~60 months | ~30–40 months |
| Quality (Piotroski, GP/Assets) | >72 months | ~40–50 months |

The H231 test (May 2026) applied decay-weighted windows to alpha101 (H217 baseline) and
found NOT CONFIRMED — the compression primarily affects longer-horizon momentum factors
(months to years), not intraday-aggregated alpha101 signals. This is consistent with the
theory: lower-frequency signals face more crowding from AI-driven quant funds.

---

## 6. IS window length guidance

A common mistake: choosing a 5-year IS window because "that seems long enough" without
checking whether it spans the relevant decay timescale for the factor being tested.

**Rule of thumb**: IS window should be at least **3–5× the expected half-life**.

```python
def recommended_is_window(half_life_months: float,
                           multiplier: float = 4.0) -> float:
    """
    Recommended IS window to adequately sample factor decay.
    Uses 4× half-life as default (captures ~94% of initial alpha decay).
    """
    return half_life_months * multiplier


# Momentum (HL ~10 months): IS should be >= 40 months (~3.3 years)
# Value (HL ~35 months): IS should be >= 140 months (~11.7 years)
# Our standard: IS 2013-2020 (84 months) = 8.4x for momentum, adequate for all

# For OOS window:
# OOS should be at least 1 half-life to observe first meaningful decay
# Better: 1-2 half-lives (for momentum: 10-20 months minimum meaningful OOS)
```

**Our standard split (IS 2013-2020, OOS 2021-2026) assessment**:

| Factor | HL estimate | IS coverage | OOS coverage | Verdict |
|--------|------------|-------------|--------------|---------|
| Short-term reversal (H181) | ~2 months | 42× ✓✓ | 30× ✓✓ | Excellent |
| Momentum 12-1m (H198) | ~10 months | 8.4× ✓ | 6× ✓ | Good |
| Alpha101 intraday (H217) | ~2 months | 42× ✓✓ | 30× ✓✓ | Excellent |
| Quality factor (H222) | ~45 months | 1.9× ✗ | 0.5× ✗ | Inadequate — need EDGAR data |
| PEAD event-driven (H174) | ~0.5 months | N/A (event count matters) | n=22 events | Low n; use event count not time |

---

## 7. Measuring half-life for our confirmed strategies

Quick diagnostic to run when adding a new OOS period or suspecting decay:

```python
import yfinance as yf
import pandas as pd
import numpy as np

def measure_strategy_halflife(strategy_monthly_returns: pd.Series,
                               min_ic_window: int = 6) -> dict:
    """
    Diagnostic for strategy-level half-life.
    Works on a time series of monthly strategy returns.
    Outputs: rolling Sharpe trend, apparent decay rate.
    """
    r = strategy_monthly_returns.dropna()

    # Annual rolling Sharpe
    rolling_sharpe = (
        r.rolling(12).mean() / r.rolling(12).std(ddof=1) * np.sqrt(12)
    ).dropna()

    # Half-life of the rolling Sharpe trend
    hl = signal_halflife(rolling_sharpe - rolling_sharpe.mean(), method='regression')

    # IC of raw returns: do early returns predict later returns?
    # (positive IC = strategy is stable; negative IC = mean-reversion / decay)
    ic_list = []
    step = 6  # 6-month blocks
    for i in range(0, len(r) - 2 * step, step):
        early = r.iloc[i:i+step].mean()
        later = r.iloc[i+step:i+2*step].mean()
        ic_list.append((early, later))
    ic_corr = np.corrcoef([x[0] for x in ic_list], [x[1] for x in ic_list])[0,1] if ic_list else np.nan

    # Sharpe trend slope
    t = np.arange(len(rolling_sharpe))
    slope = np.polyfit(t, rolling_sharpe.values, 1)[0]

    return {
        "rolling_sharpe_trend_slope_per_month": round(slope, 4),
        "rolling_sharpe_halflife_months": round(hl, 1) if hl < 1000 else "stable",
        "early_late_ic": round(ic_corr, 3) if not np.isnan(ic_corr) else "insufficient_data",
        "interpretation": (
            "DECAYING" if slope < -0.02 else
            "STABLE" if abs(slope) < 0.02 else
            "IMPROVING"
        )
    }

# Usage after adding new OOS data:
# result = measure_strategy_halflife(h181_oos_returns)
# if result["interpretation"] == "DECAYING":
#     print("WARNING: H181 OOS Sharpe declining — consider re-validating signal")
```

---

## 8. Retraining frequency guidance

Once you know a factor's half-life, use it to set retraining schedules:

| Factor | HL | Recommended retrain frequency |
|--------|----|-------------------------------|
| IBS/reversal (H112) | ~2 months | Annual; signal is stable per-ETF calibration |
| Industry reversal (H181) | ~2 months | Annual parameter check (sector assignments) |
| Momentum (H198) | ~10 months | Annual OOS re-evaluation; retrain if Sharpe drops |
| Alpha101 (H217) | ~2 months | Annual; LightGBM model retrain every 12-18 months |
| PEAD NLP (H174) | Event-driven | Re-validate every 50 OOS events or if WR drops <75% |
| Quality factor (H222) | ~45 months | EDGAR data update annually; model stable |

---

## 9. Key references

| Source | Key contribution | Link |
|--------|----------------|------|
| McLean & Pontiff 2016 | First large-scale post-publication decay study (97 factors, 58 months avg HL) | doi:10.1111/jofi.12365 |
| arXiv:2512.11913 (Dec 2025) | Hyperbolic decay model; momentum vs value classification | [link](https://arxiv.org/abs/2512.11913) |
| arXiv:2605.23905 (May 2026) | AI adoption compresses HL from 58 → 18 months | [link](https://arxiv.org/abs/2605.23905) |
| Medium: MagPi AI (Dec 2025) | Practical AR(1) half-life formula + Python | [link](https://medium.com/@magpiai/stop-guessing-the-quant-science-of-signal-half-life-and-market-context-ba934a13dd21) |

---

## See also

- [Multiple Testing & Statistical Significance](multiple-testing.md) — DSR/PBO methods
- [Walk-Forward & CPCV](walk-forward-cpcv.md) — OOS methodology
- [Design Principles](design-principles.md) — IS/OOS split design
- [Momentum Strategies — Factor Crowding](../algorithms/momentum-strategies.md) — crowding and crash risk
- H231 in [hypothesis log](hypothesis-log.md) — tested decay-weighted alpha101 (NOT CONFIRMED)
