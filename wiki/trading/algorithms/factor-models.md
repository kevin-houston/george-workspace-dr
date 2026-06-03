---
updated: 2026-05-25
status: active
sources:
  - Kenneth French Data Library (https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
  - AQR Data Library (https://www.aqr.com/Insights/Datasets)
  - pandas-datareader 0.10 docs
  - alphalens-reloaded PyPI
  - Fama & French (1993, 1996, 2015, 2016)
  - Asness, Moskowitz & Pedersen (2013) — Value & Momentum Everywhere
---

# Factor Models & Cross-Sectional Alpha

Reference for Fama-French factor data, cross-sectional feature construction, and factor evaluation. Directly needed for H202-XL (200-stock XGBoost momentum) and future multi-factor work.

---

## 1. Fama-French Factor Models

### 1.1 Three-Factor Model (1993)

$$R_i - R_f = \alpha + \beta_{\text{MKT}}(R_m - R_f) + \beta_{\text{SMB}} \cdot SMB + \beta_{\text{HML}} \cdot HML + \varepsilon$$

| Factor | Construction | Economic story |
|--------|-------------|----------------|
| **MKT** | Excess return of market over T-bill | Market risk premium |
| **SMB** | Small-minus-big (size) | Small-cap outperformance |
| **HML** | High-minus-low (value) | Value stock premium (B/M ratio) |

### 1.2 Five-Factor Model (2015)

Adds two quality factors to the three-factor model:

| Factor | Construction | Economic story |
|--------|-------------|----------------|
| **RMW** | Robust-minus-weak (profitability) | Profitable firms outperform |
| **CMA** | Conservative-minus-aggressive (investment) | Low-capex firms outperform |

Fama & French (2015) found MOM (momentum) was redundant in US but still included in international versions. For US cross-sectional work, add MOM separately.

### 1.3 Six-Factor Model (with Momentum)

Standard in industry: 5-factor + MOM (12-1 month momentum, skipping most recent month):

```python
factors = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
```

---

## 2. Data Sources

### 2.1 Kenneth French Data Library (Free, authoritative)

Direct download via `pandas-datareader`:

```python
import pandas_datareader.data as web

# 3-factor monthly (1926-present)
ff3 = web.DataReader('F-F_Research_Data_Factors', 'famafrench', start='2000')[0]
ff3.columns = ['Mkt-RF', 'SMB', 'HML', 'RF']
ff3 = ff3 / 100  # returns are in percent

# 5-factor monthly
ff5 = web.DataReader('F-F_Research_Data_5_Factors_2x3', 'famafrench', start='2000')[0]
ff5 = ff5 / 100

# Momentum factor
mom = web.DataReader('F-F_Momentum_Factor', 'famafrench', start='2000')[0]
mom.columns = ['Mom']
mom = mom / 100

# Daily versions — append _daily to name
ff3_daily = web.DataReader('F-F_Research_Data_Factors_daily', 'famafrench', start='2020')[0]
ff3_daily = ff3_daily / 100

# Combine
import pandas as pd
factors_m = ff5.join(mom[['Mom']])
```

Available datasets (run `web.get_available_datasets('famafrench')` for full list):
- `F-F_Research_Data_Factors` — 3-factor monthly + annual
- `F-F_Research_Data_5_Factors_2x3` — 5-factor monthly
- `F-F_Momentum_Factor` — MOM monthly
- `F-F_ST_Reversal_Factor` — short-term reversal
- `F-F_LT_Reversal_Factor` — long-term reversal
- `49_Industry_Portfolios` — sector breakdowns
- `25_Portfolios_5x5` — size × value sorted portfolios

### 2.2 AQR Data Library (Free, institutional quality)

AQR publishes several datasets not in French's library:

| Dataset | URL | Content |
|---------|-----|---------|
| QMJ — Quality Minus Junk | aqr.com/Insights/Datasets/Quality-Minus-Junk-Factors | Profitability, safety, growth, payout factors |
| BAB — Betting Against Beta | aqr.com/Insights/Datasets/Betting-Against-Beta-Equity-Factors | H192 source |
| Value and Momentum Everywhere | aqr.com/Insights/Datasets/Value-and-Momentum-Everywhere-Factors | 8 asset classes |
| Time Series Momentum | aqr.com/Insights/Datasets/Time-Series-Momentum-Factors | TSMOM factor |

Download as Excel, clean with pandas. No API — wget/requests + openpyxl:

```python
import pandas as pd
# AQR data comes as Excel with multiple sheets
df = pd.read_excel('qmj.xlsx', sheet_name='QMJ Factors', skiprows=18, index_col=0)
```

### 2.3 OpenBB (Free API wrapper)

```python
from openbb import obb
# Fama-French factors via obb
factors = obb.equity.fundamental.multiples("AAPL", provider="fmp")
```

### 2.4 Direct yfinance for Custom Factor Construction

For 200-stock universe (H202-XL), build factors from raw price/fundamental data:

```python
import yfinance as yf
import pandas as pd

def fetch_universe(tickers, start, end):
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    return raw['Close']

def build_momentum_factor(prices, skip=21, lookback=252):
    """12-1 month momentum (skip most recent month)."""
    returns = prices.shift(skip) / prices.shift(lookback) - 1
    return returns  # cross-sectional signal, rank later
```

---

## 3. Factor Construction in Python

### 3.1 Standard Cross-Sectional Factors

These are the building blocks for H202-XL feature engineering:

```python
import numpy as np
import pandas as pd

def cs_rank(series):
    """Cross-sectional rank-normalize to [-0.5, 0.5]."""
    r = series.rank(pct=True)
    return r - 0.5

# ── Momentum factors ────────────────────────────────────────────────────────
def mom_12_1(prices):
    """12-1 month momentum. Most important single predictor."""
    return prices.shift(21) / prices.shift(252) - 1

def mom_6_1(prices):
    """6-1 month momentum. H198 confirmed (OOS Sharpe 1.174)."""
    return prices.shift(21) / prices.shift(126) - 1

def mom_1m(prices):
    """1-month return (short-term reversal signal — inverted)."""
    return prices / prices.shift(21) - 1

# ── Value factors (requires fundamentals) ───────────────────────────────────
def book_to_market(book_value, market_cap):
    """HML proxy. Higher = more value."""
    return book_value / market_cap

def earnings_yield(eps_ttm, price):
    """E/P ratio. Alternative value measure."""
    return eps_ttm / price

# ── Quality factors ──────────────────────────────────────────────────────────
def roe(net_income, book_equity):
    """Return on equity. RMW proxy."""
    return net_income / book_equity

def asset_growth(total_assets):
    """CMA proxy — low investment predicts outperformance."""
    return total_assets / total_assets.shift(252) - 1

# ── Low-volatility factor ────────────────────────────────────────────────────
def realized_vol(returns, window=63):
    """63-day realized volatility. Lower = lower beta."""
    return returns.rolling(window).std() * np.sqrt(252)

# ── Liquidity proxy ──────────────────────────────────────────────────────────
def amihud_illiquidity(returns, volume, window=21):
    """Amihud (2002): avg(|ret|/volume). Invert for liquidity."""
    return (returns.abs() / volume).rolling(window).mean()
```

### 3.2 Feature Matrix for H202-XL

```python
def build_feature_matrix(prices, volumes=None):
    """
    Build cross-sectional feature matrix for XGBoost.
    Returns DataFrame: rows=dates, cols=MultiIndex(ticker, feature)
    """
    ret = prices.pct_change()
    
    features = {
        'mom_12_1':    mom_12_1(prices),
        'mom_6_1':     mom_6_1(prices),
        'mom_3_1':     prices.shift(21) / prices.shift(63) - 1,
        'mom_1m':      mom_1m(prices),
        'vol_63':      ret.rolling(63).std() * np.sqrt(252),
        'vol_252':     ret.rolling(252).std() * np.sqrt(252),
        'vol_ratio':   ret.rolling(21).std() / ret.rolling(63).std(),
        'ret_1d':      ret,
        'ret_5d':      prices / prices.shift(5) - 1,
        'ma_ratio':    prices / prices.rolling(200).mean(),  # 200-day SMA gate signal
    }
    
    # Cross-sectionally rank each feature
    ranked = {k: v.apply(cs_rank, axis=1) for k, v in features.items()}
    return pd.concat(ranked, axis=1, keys=ranked.keys())
```

### 3.3 Fama-MacBeth Regression

Test whether a factor has cross-sectional predictive power:

```python
from linearmodels.panel import FamaMacBeth

# Prepare panel data: long format
panel = feature_matrix.stack().reset_index()
panel.columns = ['date', 'ticker', *feature_matrix.columns.levels[0]]
panel['fwd_ret'] = (prices / prices.shift(-21) - 1).shift(-21).stack().values

# Run Fama-MacBeth
panel = panel.set_index(['date', 'ticker'])
mod = FamaMacBeth(panel['fwd_ret'], panel[['mom_12_1', 'vol_63', 'mom_1m']])
res = mod.fit(cov_type='kernel')
print(res.summary)
```

---

## 4. Factor Evaluation with Alphalens

`alphalens-reloaded` (maintained fork of Quantopian's alphalens):

```bash
pip install alphalens-reloaded
```

```python
import alphalens

# Prepare inputs
factor_data = alphalens.utils.get_clean_factor_and_forward_returns(
    factor=cs_rank(mom_12_1(prices)).stack(),  # MultiIndex (date, ticker)
    prices=prices,
    groupby=sector_map,  # optional sector dict
    quantiles=5,
    periods=(1, 5, 21),  # 1d, 1w, 1m forward returns
)

# Full tearsheet
alphalens.tears.create_full_tear_sheet(factor_data)

# Just returns analysis
mean_return_by_q, _ = alphalens.performance.mean_return_by_quantile(factor_data)
alphalens.plotting.plot_quantile_returns_bar(mean_return_by_q)

# IC analysis
ic = alphalens.performance.factor_information_coefficient(factor_data)
print(f"Mean IC: {ic.mean():.3f}  IR: {ic.mean()/ic.std():.3f}")
```

Key metrics to check:
- **IC (Information Coefficient)**: Spearman correlation between factor rank and forward return. IC > 0.03 is meaningful; IC > 0.05 is strong.
- **IR (Information Ratio)**: IC mean / IC std. IR > 0.5 is good.
- **Q1-Q5 spread**: Top quintile minus bottom quintile annualized return.
- **Factor decay**: How fast IC decays over days — signals momentum persistence vs. reversal.

---

## 5. Factor Regression (Style Analysis)

How much of a strategy's return is explained by known factors:

```python
import statsmodels.api as sm

def factor_regression(strategy_returns, factor_returns, annualize=True):
    """
    Regress strategy returns on Fama-French factors.
    Returns alpha, betas, R², t-stats.
    """
    # Align
    idx = strategy_returns.index.intersection(factor_returns.index)
    y = strategy_returns.loc[idx]
    X = sm.add_constant(factor_returns.loc[idx])
    
    model = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': 6})
    
    n = len(y)
    freq = 252 if len(y) > 500 else 12  # daily vs monthly
    ann_alpha = model.params['const'] * freq
    
    return {
        'alpha_ann': ann_alpha,
        'alpha_t': model.tvalues['const'],
        'alpha_p': model.pvalues['const'],
        'betas': model.params.drop('const').to_dict(),
        'r2': model.rsquared,
        'n': n,
    }

# Example: check how much of H198 momentum is FF MOM factor
ff_daily = web.DataReader('F-F_Research_Data_Factors_daily', 'famafrench', start='2018')[0] / 100
result = factor_regression(h198_returns, ff_daily[['Mkt-RF', 'SMB', 'HML']])
print(f"Alpha: {result['alpha_ann']:.2%}/yr  t={result['alpha_t']:.2f}")
```

---

## 6. Sector-Neutral Factor Construction

H202-XL uses 200 stocks across sectors. Sector-neutral factors remove sector bias:

```python
def sector_neutral(factor_values, sector_map):
    """
    Subtract sector median from each stock's factor score.
    sector_map: dict {ticker: sector_code}
    """
    sectors = pd.Series(sector_map)
    result = factor_values.copy()
    
    for date in factor_values.index:
        row = factor_values.loc[date]
        sector_medians = row.groupby(sectors).transform('median')
        result.loc[date] = row - sector_medians
    
    return result

# For panel data (faster)
def sector_neutral_panel(panel_df, factor_col, sector_col):
    panel_df[factor_col + '_sn'] = (
        panel_df.groupby(['date', sector_col])[factor_col]
        .transform(lambda x: x - x.median())
    )
    return panel_df
```

---

## 7. Integration with H202-XL

H202-XL (XGBoost on 200-stock universe) should use:

1. **Feature set**: mom_12_1, mom_6_1, mom_3_1, vol_63, vol_252, vol_ratio, ma_ratio, mom_1m (reversal signal)
2. **Target**: 21-day forward return rank (quintile label for classification, or raw return for regression)
3. **Sector-neutral**: yes — apply `sector_neutral()` to each factor before feeding XGBoost
4. **Walk-forward**: 48-month IS window, 12-month step, 1-month OOS
5. **Benchmark**: H198 (6-1m momentum, no ML)

```python
from sklearn.preprocessing import QuantileTransformer
import xgboost as xgb

# Prepare features
feats = ['mom_12_1_sn', 'mom_6_1_sn', 'mom_3_1_sn', 'vol_63_sn', 'vol_ratio']
X = panel[feats]
y = panel['fwd_ret_rank']  # 0-4 quintile label

# Quantile transform — XGBoost is rank-invariant but this helps
qt = QuantileTransformer(output_distribution='uniform')
X_t = qt.fit_transform(X)

# Walk-forward split
for train_end in pd.date_range(start='2008', end='2022', freq='AS'):
    train_mask = (panel.date >= train_end - pd.DateOffset(years=4)) & (panel.date < train_end)
    test_mask  = (panel.date >= train_end) & (panel.date < train_end + pd.DateOffset(years=1))
    
    clf = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8, random_state=42)
    clf.fit(X_t[train_mask], y[train_mask])
    preds = clf.predict_proba(X_t[test_mask])[:, 4]  # top quintile prob
```

---

## 8. Useful Libraries Summary

| Library | Install | Purpose |
|---------|---------|---------|
| `pandas-datareader` | `pip install pandas-datareader` | Kenneth French data, FRED, etc. |
| `alphalens-reloaded` | `pip install alphalens-reloaded` | Factor tearsheets, IC, quantile returns |
| `linearmodels` | `pip install linearmodels` | Fama-MacBeth, panel OLS, PanelOLS |
| `statsmodels` | already installed | Factor regression, HAC errors |
| `xgboost` | `pip install xgboost` | Cross-sectional ML (H202-XL) |
| `openbb` | `pip install openbb` | Unified market/fundamental data API |
| `quantstats` | `pip install quantstats` | Factor tearsheets (simpler than alphalens) |

---

## 9. Key Papers

| Paper | Finding | Relevance |
|-------|---------|-----------|
| Fama & French (1993) JFE | SMB + HML explain size/value premia | 3-factor baseline |
| Fama & French (2015) JFE | RMW + CMA add quality factors | 5-factor baseline |
| Carhart (1997) JF | MOM extends FF3 | 4-factor model industry standard |
| Jegadeesh & Titman (1993) JF | 12-1m momentum: 1%/month | Momentum source paper |
| Asness, Moskowitz & Pedersen (2013) JF | Value + momentum negative correlation → diversification | Multi-factor portfolio theory |
| Hou, Xue & Zhang (2015) RFS | q-factor model: investment + ROE replace SMB/HML | Alternative to FF5 |
| Kozak, Nagel & Santosh (2020) JF | ML factor zoo: SDF spans many anomalies | Modern factor selection |

---

## Related Pages

- [Momentum Strategies](momentum-strategies.md) — H198 confirmed, H202-XL queued
- [Quality Factor (QMJ, Piotroski, GP/Assets)](quality-factor.md) — fundamental quality complement to BAB; H221/H222 designs; FMP API implementation
- [Low-Volatility Anomaly](low-volatility.md) — H192 BAB, H205 regime-conditional
- [Regime Detection](regime-detection.md) — factor conditioning on market regime
- [ML for Trading](../tools/ml-for-trading.md) — XGBoost, MASFIN, gradient boosting
- [Portfolio Optimization](../tools/portfolio-optimization.md) — HRP, risk parity, NCO


## AlphaCrafter — Multi-Agent Factor Ensemble (arXiv:2605.05580)

**Yuan et al., 2026 (NeurIPS 2026 submission)**  
A full-stack multi-agent framework for cross-sectional quantitative trading. Three specialized agents form a closed-loop pipeline:

1. **Miner** — expands the factor pool via LLM-guided search (generates new factor candidates)
2. **Screener** — assesses market regimes and builds a regime-conditioned factor ensemble (weights existing factors by current macro state)
3. **Trader** — converts the factor ensemble into a quantitative strategy with explicit risk constraints

### Key Results
- Consistently outperforms SOTA baselines on CSI 300 and S&P 500 in risk-adjusted returns
- Lowest cross-trial variance among tested systems — more robust across different market periods
- Regime-conditioned factor weighting (Screener) is the key differentiator vs static factor blends

### Relevance to Current Pipeline
Our confirmed factors (H192-D BAB, H198 momentum, H217 alpha101, H222 quality) could be combined using the AlphaCrafter Screener design:
- In bull markets (VIX<20, SPY>200MA): weight momentum + quality higher
- In bear markets: weight BAB + quality higher, reduce momentum
- The Miner agent approach maps to our alpha101 scan (H215/H217) extended to LLM-generated factor discovery

### H224 Candidate
Design: regime-conditional factor blend using confirmed signals (H192-D, H198, H222B GP/Assets, H215). Weight each signal by its trailing 6-month IC in the current regime (VIX/SMA-defined). Confirm: OOS Sharpe > 1.5 (must beat best individual signal H217's 1.559).

### Code Pattern
No open-source code released (submitted to NeurIPS 2026). Implement using:
- Regime detection: see `wiki/trading/algorithms/regime-detection.md` (VIX+SMA or HMM)
- Factor signals: H192-D BAB, H198 6-1m momentum, H222B GP/Assets, H215 alpha101
- IC weighting: trailing 6-month rank correlation between signal and next-month return

**Reference:** arXiv:2605.05580

## Factor Crowding Risk (arXiv:2512.11913, Dec 2025)

Paper: 'Not All Factors Crowd Equally: Modeling, Measuring, and Trading on Alpha Decay'

Key findings:
- Mechanical factors (momentum, short-term reversal) show measurable crowding post-2015 correlated with factor ETF AUM growth
- Crowding causes model-predicted alpha (0.30) to exceed realized alpha (0.15) — 2x over-prediction
- Judgment-based factors (value, quality) do NOT exhibit the same crowding pattern
- Crowding can be used as a trading signal itself: avoid momentum when ETF AUM in momentum products spikes

Implications for our pipeline:
- H217 (alpha101 momentum, OOS 1.559) and H228 (blend, OOS 1.572) are momentum-heavy — subject to crowding decay
- Prefer H228 blend over pure H217: the reversal and quality components are less crowded
- H221/H222 (quality/F-Score factors) may be more durable at lower raw Sharpe — diversification value is higher than Sharpe alone suggests
- Monitor MTUM (iShares MSCI Momentum Factor ETF) AUM as a crowding proxy; declining AUM periods have historically seen momentum mean-revert sharply

Source: arXiv:2512.11913

## Factor Timing & Regime-Switching Allocation

Factors have time-varying premiums — momentum thrives in trending regimes, low-vol excels in rate-stable regimes, value recovers during mean-reversion windows. Static equal-weight factor blends leave this timing alpha on the table.

### Key Reference
**arXiv:2410.14841** (Shu & Mulvey, October 2024) — *Dynamic Factor Allocation Leveraging Regime-Switching Signals*
- 6 style factors: value, size, momentum, quality, low-vol, growth
- Regime detection: Sparse Jump Model (SJM) + Black-Litterman optimization
- Result: Information ratio improves **from 0.05 to 0.4** vs. equal-weight factor blend (8x improvement)
- Tested on US equities 2000–2023

See also: `algorithms/regime-detection.md` for SJM implementation notes (Statistical Jump Model, arXiv:2402.05272, Shu et al. 2024).

### Why Factor Timing Matters for Our Pipeline

H245 (Low-Volatility Anomaly) failed OOS (Sharpe 0.626) because the 2022–2023 rate-hike cycle systematically destroyed bond-proxy low-vol stocks. A regime-aware allocation would have:
- Reduced low-vol exposure when VIX < 25 + 10Y yield rising sharply
- Increased momentum allocation in trending markets (where H228 thrives)

### Simple Regime-Factor Rules (Empirical)

| Regime | Signal | Favored Factors | Reduce Exposure |
|--------|--------|-----------------|-----------------|
| Rising rates | 10Y yield rising > 50bps/quarter | Momentum, Quality | Low-Vol, Value |
| High VIX (>25) | VIX > 25 for 5+ days | Low-Vol, Quality | Momentum |
| Bear market | SPY < 200-day MA | Quality, Defensive | Momentum |
| Bull trend | SPY > 200-day MA + VIX < 20 | Momentum, Growth | Low-Vol, Value |

### Production Portfolio Implications

Current blend (H041a 22% / H026 27% / H045 21% / IBS 30%) is static. A regime overlay could:
- In rate-hike regimes: increase IBS ETF weight (XLK/SMH/IGV — tech-growth, not bond-proxy)
- In bear markets: shift toward H045 (bonds top-2, safety focus)
- In bull trends: increase H041a/H026 (momentum ETF rotation)

Design candidate: **H249** — regime-conditional weight adjustment on production portfolio. Gate: Sharpe improvement vs static blend > 0.2 in OOS.
