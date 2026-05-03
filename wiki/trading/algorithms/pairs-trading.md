---
updated: 2026-04-30
type: strategy-guide
status: active — H152+ backtesting planned
---

# ETF Pairs Trading (Statistical Arbitrage)

Mean-reversion strategy exploiting temporary deviations from a long-run equilibrium between two or more co-moving ETFs. The alpha source is cointegration — two price series that individually follow random walks but share a stationary spread.

**Related pages**: [Momentum Strategies](momentum-strategies.md) — opposite alpha source; low correlation to pairs | [Event-Driven Strategies](event-driven.md) — H160 factor-residualized pairs design | [Hypothesis Log](../backtesting/hypothesis-log.md) — H152–H155 NOT CONFIRMED; H160 QUEUED

**Academic foundation**: Engle & Granger (1987) — Error Correction Models; Gatev, Goetzmann & Rouwenhorst (2006) — classic pairs trading study on US stocks (60-day formation, 6-month trading window).

---

## Why ETFs (not stocks)

- Structural cointegration: ETF pairs in the same segment (GDX/SIL, XLE/OIH) are cointegrated by economic necessity — they track correlated underlying factors
- No overnight/fundamental jump risk that breaks stock pairs
- No borrowing cost or short-squeeze risk (ETFs are liquid and borrowable)
- Pairs persist for years; stock pairs break at earnings or M&A

**Risk**: sector composition drift. XLE/OIH partially diverged 2020-2024 after energy transition changed the sub-industry weights. Retest cointegration quarterly.

---

## Known Cointegrated ETF Pairs

| Pair | Economic link | Notes |
|------|--------------|-------|
| GDX / SIL | Gold miners / Silver miners | Share underlying metal prices, royalty economics |
| XLE / OIH | Energy broad / Oil services | Services sector depends on E&P capex |
| XLK / QQQ | Technology sector / Nasdaq-100 | QQQ is ~50% tech; cointegration tight but OHLCs differ |
| EWA / EWC | Australia / Canada iShares | Both commodity-exporting economies |
| TLT / IEF | 20yr+ Treasury / 7-10yr Treasury | Yield-curve spread play; same issuer |
| SPY / IVV | Two S&P 500 trackers | Near-arbitrage — spreads tiny, eaten by fees |
| XLF / KRE | Financials broad / Regional banks | KRE is a subset of XLF |
| GLD / IAU | Two gold ETFs | Same underlying, expense ratio arbitrage only |

**Most promising for backtesting**: GDX/SIL and XLE/OIH — large spreads (lower transaction cost hurdle), clear economic narrative, liquid options for hedging.

---

## Step 1: Test for Cointegration

### Engle-Granger (two-asset pairs)

```python
from statsmodels.tsa.stattools import coint
import yfinance as yf

# Load ETF prices
tickers = ["GDX", "SIL"]
prices = yf.download(tickers, start="2010-01-01", auto_adjust=True)["Close"]

stat, pvalue, critical_values = coint(prices["GDX"], prices["SIL"])
print(f"p-value: {pvalue:.4f}")   # p < 0.05 → cointegrated
# critical_values: [1%, 5%, 10%] thresholds for test stat
```

**Interpretation**: p < 0.05 rejects null of no cointegration. p < 0.01 is high confidence. Always test over the full available history, then re-test on sub-periods to check stability.

### Johansen Test (3+ assets or validation)

```python
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import numpy as np

data = prices[["GDX", "SIL"]].dropna().values
result = coint_johansen(data, det_order=0, k_ar_diff=1)
# result.lr1: trace statistics; result.cvt: critical values [90%, 95%, 99%]
print("Trace stat:", result.lr1)
print("Critical values (90/95/99%):", result.cvt)
```

Johansen avoids the two-step error accumulation of Engle-Granger and is required when testing 3+ asset groups.

---

## Step 2: Estimate the Hedge Ratio

The hedge ratio β tells you how many units of Y to hold per unit of X. Two approaches:

### Static OLS (simple but degrades)

```python
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

X = add_constant(prices["GDX"])
model = OLS(prices["SIL"], X).fit()
beta = model.params["GDX"]          # hedge ratio
spread = prices["SIL"] - beta * prices["GDX"] - model.params["const"]
```

**Problem**: OLS estimates a single β over the full sample. For pairs held over years, β drifts. TLT/IEI hedge ratio dropped from 1.38 to 0.9 over 2011–2016 (Chan, 2013).

### Rolling OLS (better, but noisy)

```python
window = 252  # 1 year
rolling_beta = prices["SIL"].rolling(window).apply(
    lambda y: np.polyfit(prices["GDX"].loc[y.index], y, 1)[0], raw=False)
spread_rolling = prices["SIL"] - rolling_beta * prices["GDX"]
```

### Kalman Filter (best for dynamic pairs)

Treats β as a hidden state that evolves as a random walk. Updates continuously; most stationary spreads in practice.

```python
from pykalman import KalmanFilter
import numpy as np

# Observation matrix: [GDX, 1] (slope + intercept)
obs_mat = np.vstack([prices["GDX"].values, np.ones(len(prices))]).T[:, np.newaxis, :]

kf = KalmanFilter(
    n_dim_obs=1,
    n_dim_state=2,
    initial_state_mean=[1.0, 0.0],
    initial_state_covariance=np.eye(2),
    transition_matrices=np.eye(2),          # β follows random walk
    observation_matrices=obs_mat,
    observation_covariance=1.0,
    transition_covariance=0.01 * np.eye(2), # how fast β can change
)
state_means, _ = kf.filter(prices["SIL"].values[:, np.newaxis])
beta_kf = state_means[:, 0]
intercept_kf = state_means[:, 1]
spread_kf = prices["SIL"].values - beta_kf * prices["GDX"].values - intercept_kf
```

Use Kalman when holding > 6 months. For short-term (< 3 month rolling tests), rolling OLS is sufficient.

---

## Step 3: Calculate the Z-Score

```python
import pandas as pd

spread = pd.Series(spread_kf, index=prices.index).dropna()

lookback = 60  # trading days (~3 months)
z_score = (spread - spread.rolling(lookback).mean()) / spread.rolling(lookback).std()
```

**Critical**: use rolling statistics computed *only from past data*. Never use full-sample mean/std (look-ahead bias).

---

## Step 4: Generate Signals

Standard thresholds (Gatev et al. 2006, Chan 2013):

| Action | Z-score condition | Direction |
|--------|------------------|-----------|
| Enter long spread | z < −2.0 | Long Y (SIL), Short X (GDX) |
| Enter short spread | z > +2.0 | Short Y, Long X |
| Exit | \|z\| < 0.5 | Close both legs |
| Stop-loss | \|z\| > 4.0 | Regime break — exit and pause |

```python
long_entry   = z_score < -2.0
short_entry  = z_score > +2.0
exit_signal  = z_score.abs() < 0.5
stop_loss    = z_score.abs() > 4.0
```

**Optimized thresholds** (from parameter search): entry ~1.4–1.5σ reduces whipsaw; exit ~0.3–0.5σ locks profits earlier. Test on OOS data.

---

## Step 5: Measure Half-Life of Mean Reversion

Half-life tells you how quickly the spread reverts. Short half-life (< 20 days) = fast mean-reversion strategy; long half-life (> 60 days) = slower, monthly-rebalance appropriate.

```python
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant
import numpy as np

spread_lag  = spread.shift(1).dropna()
spread_diff = spread.diff().dropna()
aligned = pd.concat([spread_diff, spread_lag], axis=1).dropna()
aligned.columns = ["diff", "lag"]

model = OLS(aligned["diff"], add_constant(aligned["lag"])).fit()
theta = model.params["lag"]           # mean-reversion coefficient (should be negative)
half_life = np.log(2) / (-theta)      # days to 50% reversion

print(f"Half-life: {half_life:.1f} trading days")
```

**Rule of thumb**: set lookback window = 2–4× half-life.

---

## Backtesting Methodology

### Walk-Forward (mandatory)

```python
TRAIN_MONTHS = 12   # estimate β and z-score params
TEST_MONTHS  = 3    # trade on OOS signals

results = []
for start in pd.date_range("2010-01", "2025-01", freq="3MS"):
    train_end  = start + pd.DateOffset(months=TRAIN_MONTHS)
    test_end   = train_end + pd.DateOffset(months=TEST_MONTHS)
    train = prices[start:train_end]
    test  = prices[train_end:test_end]
    # fit β on train, generate signals on test
    beta = fit_ols(train)
    signals = generate_signals(test, beta)
    results.append(backtest(test, signals))
```

Never fit β or the z-score window on the data you're trading. This is the most common error in pairs backtests.

### Transaction costs

ETF pairs are relatively cheap to trade but:
- Two-sided round trip: 2× commission + 2× half-spread
- For IB: ~$0.005/share × 2 legs × 4 trades (entry + exit) = ~$0.04/share
- Rule of thumb: require >0.5% spread width to cover costs

---

## Common Failure Modes

### 1. Cointegration breakdown

Signs: z-score drifts to extreme values without reverting; ADF p-value on spread rises > 0.1 in rolling re-test.

**Response**: close positions, pause until rolling cointegration test confirms reinstatement. Re-test monthly.

### 2. Look-ahead bias in hedge ratio

Fitting β on the full sample and then "backtesting" produces falsely smooth P&L. Always fit on train window only.

### 3. Overcrowded pairs

SPY/IVV and GLD/IAU are near-arbitrage relationships. The spread is so tight that any transaction costs eliminate edge. Only trade pairs where the spread justifies costs.

### 4. 2020 Energy sector break (XLE/OIH)

OIH composition shifted from diversified oil services to tech-heavy (SLB, HAL lost weight; newer names added). XLE/OIH spread widened permanently 2020-2022 before partially normalizing. **Lesson**: sector ETF composition changes — re-test cointegration after any major reconstitution.

---

## Python Library Stack

| Library | Purpose | Install |
|---------|---------|---------|
| `statsmodels` | Cointegration tests (Engle-Granger, Johansen), ADF test | `pip install statsmodels` |
| `pykalman` | Kalman filter for dynamic hedge ratio | `pip install pykalman` |
| `pandas` | Rolling z-score, resampling | standard |
| `scikit-learn` | Rolling OLS alternative, feature engineering | standard |
| `arch` | GARCH volatility for dynamic position sizing | `pip install arch` |
| `hurst` | Hurst exponent (measures mean-reversion strength) | `pip install hurst` |

### Alternative: Hudson & Thames ArbitrageLab

Academic-grade pairs trading library:
- GitHub: https://github.com/hudson-and-thames/arbitragelab
- Covers: distance approach, cointegration, Copula-based pairs, OU model fitting
- License: BSL 1.1 (non-commercial free; commercial ~$3k/year)
- Overkill for ETF pairs but useful for stock-universe stat arb

---

## Correlation with H026 Momentum Strategy

H150 (Low-Vol Anomaly) showed that sector strategies can have OOS corr ~0.18 with H026. Pairs trading is structurally different — it's market-neutral (long one ETF, short another), so correlation with a long-only momentum strategy should be near zero or even negative.

Target: monthly return correlation with H026 < 0.30. If a pairs strategy confirms (H152+), it could provide genuine diversification — the blending case is much stronger than low-vol vs H026.

---

## Implementation Plan (H152+)

1. **H152**: Test GDX/SIL cointegration + OLS spread backtest (2010-2026, IS/OOS split)
2. **H153**: Test XLE/OIH pair
3. **H154**: Add Kalman filter hedge ratio to best confirmed pair
4. **H155**: If confirmed — test blend with H026 (target 10-20% allocation)

See [Hypothesis Log](../backtesting/hypothesis-log.md) for results.
