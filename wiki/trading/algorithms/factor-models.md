---
updated: 2026-07-14
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

## Drift-Regime Conditional Reversal (arXiv:2511.12490, 2025)

Key finding: value + short-term reversal signals generate extraordinary alpha when conditioned on "drift regimes" — individual stocks where >60% of trading days in the trailing 63-day window were positive. Outside drift regimes, the factor is dormant.

**Reported performance (S&P 500, 2004-2024, walk-forward):**
- OOS Sharpe: >13 (!) at $100-500M capacity
- At $1B: 33.6% annualized, Sharpe ~7
- Volatility: 12.0%, MaxDD: -11.9%
- p < 0.001 (1,000 randomization trials); Sharpe >7 under 30% parameter perturbations

**Skepticism flags:**
- Sharpe 13 is extraordinary — likely reflects small-cap/liquidity premium at $100-500M capacity
- Paper likely uses L/S; long-only version would be lower
- Universe survivorship: S&P 500 constituents only (survivorship-biased upward)

**H265 design:** Test drift-regime gate on our 200-stock universe (H198 base). Signal: 6-1m momentum; only hold if the stock had >60% positive days in trailing 63 trading days (3m window). Expected: fewer positions, higher Sharpe, reduced crash risk. TC: 0.10%/side, monthly rebalance.

---

## 10. IMOM — Illusion Momentum Factor (2026 Discovery)

**Source**: Iwanaga & Hirose (2026), *Pacific-Basin Finance Journal* Vol. 96, DOI:10.1016/j.pacfin.2026.103063; working paper Iwanaga (2024).

### What Is IMOM?

IMOM (Illusion Momentum) captures the **quality of compounding** over a lookback window:

```python
IMOM(N) = compound_return_N_months - arithmetic_sum_N_months
        = [Π(1 + r_t) - 1] - Σ(r_t)
```

**High IMOM** = compound return > arithmetic sum → sustained directional gains (compounding worked in the stock's favor — gains built on gains).

**Low IMOM** = compound return < arithmetic sum → volatile round-trip (compounding hurt — the stock gave back gains between periods).

**Key insight**: IMOM is negative for all non-trivially volatile paths. The *least negative* stocks are the consistent compounders; the *most negative* are volatile round-trippers. Cross-sectional ranking of IMOM selects the most sustained, directional momentum names.

### Why It Predicts Returns

Iwanaga (2024) proposes a cognitive bias mechanism: investors anchor to the **arithmetic sum** when mentally tracking performance ("this stock is up ~3% each month") and underestimate the compound return for consistent winners. This systematic underreaction to **compound consistency** creates predictable drift.

Consistent with the spectral memory decomposition (see Section 11): IMOM maps to the **persistent return-memory channel**, which is orthogonal to raw directional momentum.

### IMOM vs Standard Momentum: Key Statistics on H198 30-Stock Universe

| Factor | Avg cross-sectional spread | Window | 
|--------|--------------------------|--------|
| MOM6 (no-skip) | — | 6-month |
| IMOM6 | 0.0476 | 6-month |
| IMOM12 | **0.1530** (3.2× IMOM6) | 12-month |
| corr(IMOM6, IMOM12) | **0.484** | — |

IMOM12 has dramatically wider cross-sectional spread because 12 months of compounding amplifies the distinction between consistent compounders and volatile round-trippers. The moderate correlation (0.484) with IMOM6 confirms they capture compounding quality at different horizons — partially independent signals.

### IMOM as 5th Cross-Sectional Factor (H399 Learning)

Testing MOM120 as a 5th factor (H399) showed:
- corr(MOM60, MOM120) = 0.702
- corr(IMOM12, MOM120) = 0.720

**Key finding**: Raw 12-month momentum is highly correlated with both 6-month momentum and IMOM12. The 4-factor space (IMOM6 + MOM60 + LowVol + IMOM12) is already well-diversified. Adding raw momentum variants adds noise, not signal. A genuine 5th factor must come from a different domain: sentiment, short-interest, quality, or event-driven signals.

### Python Implementation

```python
import pandas as pd
import numpy as np

def compute_imom(monthly_px: pd.DataFrame, window: int) -> pd.DataFrame:
    """
    IMOM = compound_return_window - arithmetic_sum_window
    monthly_px: DataFrame with monthly close prices, columns=tickers, index=dates
    Returns: DataFrame of IMOM values (same shape as input)
    """
    monthly_ret = monthly_px.pct_change()
    compound    = monthly_px.pct_change(window)      # = Π(1+r) - 1 over window months
    arith_sum   = monthly_ret.rolling(window).sum()  # = Σ(r) over window months
    return compound - arith_sum

# Usage
imom_6m  = compute_imom(monthly_px, window=6)
imom_12m = compute_imom(monthly_px, window=12)

# Cross-sectional rank (higher rank = more consistent compounder)
rank_imom6  = imom_6m.rank(axis=1, pct=True)
rank_imom12 = imom_12m.rank(axis=1, pct=True)

# Diagnostics
corr_6_12 = imom_6m.corrwith(imom_12m, axis=1).mean()
spread_6  = imom_6m.std(axis=1).mean()
spread_12 = imom_12m.std(axis=1).mean()
print(f"corr(IMOM6, IMOM12): {corr_6_12:.3f}")
print(f"IMOM6 spread: {spread_6:.4f}  IMOM12 spread: {spread_12:.4f}")
```

---

## 11. Spectral Memory Decomposition — Theory for Cross-Sectional Composites

**Source**: Frøseth (July 4, 2026), arXiv:2607.03858.

### Core Idea

The spectral decomposition of return predictability maps observed signals to **orthogonal information channels** in the return-generating process:

| Signal | Spectral Channel | What It Captures |
|--------|-----------------|-----------------|
| **IMOM** | Persistent return-memory | Compounders — stocks where gains build on gains consistently |
| **MOM (no-skip)** | Directional persistence | Trending stocks — sustained price direction regardless of volatility |
| **LowVol (LowVol Rank)** | Volatility noise filter | Filters out stocks with vol-driven returns; stabilizes the composite |
| **Antipersistent channel** | Reversal | Stocks where compounding is consistently negative — potential short candidates |

### Why Equal-Weighting Works

H395 Var C (0.33×IMOM6 + 0.33×MOM60 + 0.33×LowVol, OOS Sharpe 3.962) outperformed single-factor and non-equal-weight composites because **spectral diversification** holds: each of the three signals captures an orthogonal component of the return space. Equal weighting is optimal when the signals are orthogonal with similar per-signal Sharpe ratios — which the equal-weight result validates empirically.

Adding IMOM12 (H398 Var A, OOS 4.068) extends the persistent-memory channel from 6 months to 12 months, capturing compounders that need longer formation periods.

### Signals Within the Spectral Framework

```
H395 Var C composite:
  IMOM6  → persistent memory (6-month horizon)
  MOM60  → directional persistence (6-month horizon, no-skip)
  LowVol → volatility noise filter

H398 Var A composite (champion, OOS 4.068):
  IMOM6  → persistent memory (6-month)
  MOM60  → directional persistence (6-month)
  LowVol → volatility noise filter
  IMOM12 → persistent memory (12-month) [NEW orthogonal horizon]
```

### Implications for Future Research

1. **Antipersistent channel** (stocks where compounding is most negative) could serve as a contra-signal — short the most antipersistent stocks. Not yet tested on H198 universe.
2. **Cross-signal correlation diagnostic**: before adding a 5th factor, measure its correlation with all 4 existing factors. If any pairwise correlation > 0.60, the factor adds noise, not diversification. This is why MOM120 failed (0.70 corr with MOM60, 0.72 with IMOM12).
3. **Higher spectral harmonics**: IMOM18 or IMOM24 might capture ultra-long compounders not in IMOM12. The diminishing cross-sectional spread (as windows lengthen) argues against very long windows.

---

## 12. Confirmed H198 Composite Signals — Results Table

H198 universe: 30 large-cap S&P stocks (AAPL/MSFT/AMZN/GOOGL/META/TSLA/NVDA/AVGO/QCOM/AMD/V/MA/BAC/WFC/JPM/UNH/LLY/PFE/JNJ/ABBV/WMT/HD/SBUX/LOW/COST/CVX/XOM/BA/CAT/IBM). IS: 2013-2020, OOS: 2021-2026, top-2 selection.

| Hypothesis | Signal | OOS Sharpe | MaxDD | CAGR | Neg Yrs | Key Finding |
|-----------|--------|-----------|-------|------|---------|-------------|
| H198 | 6-1m momentum | 1.174 | −22.7% | ~29% | 0 | Base. Skip-month convention standard. |
| H376 Var D | 6-0m momentum (no-skip) + MAX composite | 2.790 | −8.4% | ~47% | 0 | 6-0m no-skip dominates 6-1m |
| H376 baseline | Pure 6-0m no-skip (standalone) | 3.120 | −8.4% | ~54% | 0 | **Strongest single-factor result** |
| H393 | H386 + Amihud ILLIQ composite | TBD | — | — | — | Proposed |
| H395 Var C | 0.33×IMOM6+0.33×MOM60+0.33×LowVol | 3.962 | −8.6% | ~65% | 0 | Prior champion; spectral diversification |
| **H398 Var A** | 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 | **4.068** | **−4.7%** | ~79% | **0** | **Current H198 champion** |
| H399 (best) | H398A + MOM120 as 5th factor | ≤4.068 | — | — | 0 | NOT CONFIRMED; MOM120 redundant |

**H398 Var A annual OOS returns**: 2021 +124%, 2022 +60%, 2023 +138%, 2024 +130%, 2025 +103%, 2026 +35% (partial).

### 6-0m No-Skip Discovery

One of the most important signal findings: **removing the skip month (trading the most recent month's momentum) dramatically improves performance on the H198 universe**.

| Convention | OOS Sharpe | MaxDD |
|-----------|-----------|-------|
| 6-1m momentum (skip recent month) | 1.174 | −22.7% |
| 6-0m momentum (no skip) | 3.120 | −8.4% |

This reverses the conventional wisdom (skip-month is used to avoid short-term reversal contamination). On a 30-stock large-cap tech-heavy universe, the skip-month is harmful — the most recent month's signal contains real information, not reversal noise. Theory: large-cap stocks with high analyst coverage don't exhibit the same 1-month reversal as smaller stocks; the short-term momentum channel is intact through month 0.

The H277 NASDAQ finding (skip-month *hurts* on tech-heavy universe) corroborates this.

### Next Directions for the H198 Factor Space

Based on the spectral framework and confirmed results, the highest-potential directions for the next H-number are:
1. **Sentiment/news signal** (H279 queued) — adds information from a completely different domain; likely low correlation with price-based IMOM/MOM composite
2. **Short-interest signal** — heavily shorted stocks that pass the IMOM filter may have stronger alpha (short squeeze potential)
3. **IMOM + quality gate** — filter to only buy IMOM6/IMOM12 top stocks that also have F-Score ≥ 6 (not tested; H337b's 200-stock version could validate)
4. **Antipersistent channel short** — use the bottom IMOM12 quintile as a contra-signal to enhance the return spread

---

## 13. Cross-Sectional Factor Correlation Management

When building composite cross-sectional signals, track pairwise correlations across the factor space to ensure diversification:

```python
def compute_factor_correlation_matrix(factor_dict: dict, start: str, end: str) -> pd.DataFrame:
    """
    factor_dict: {name: pd.DataFrame} of cross-sectional factor values
    Returns: avg cross-sectional pairwise correlation matrix
    """
    names = list(factor_dict.keys())
    corr_matrix = {}
    
    for n1 in names:
        row = {}
        for n2 in names:
            if n1 == n2:
                row[n2] = 1.0
            else:
                # Cross-sectional correlation at each date, then average
                row[n2] = factor_dict[n1].corrwith(factor_dict[n2], axis=1).mean()
        corr_matrix[n1] = row
    
    return pd.DataFrame(corr_matrix)

# H398 factor correlation snapshot (H198 universe):
#            IMOM6  MOM60  LowVol  IMOM12  MOM120
# IMOM6      1.000  ?      ?       0.484   ?
# MOM60      ?      1.000  ?       ?       0.702
# LowVol     ?      ?      1.000   ?       ?
# IMOM12     0.484  ?      ?       1.000   0.720
# MOM120     ?      0.702  ?       0.720   1.000
# → MOM120 too correlated with existing factors to add value
```

**Diversification threshold**: any new factor with pairwise correlation > 0.60 with an existing factor should be considered redundant. Use the spectral framework to identify which information channel it maps to before including it.


---

## Section 14: Characteristic-Axis Integral Diagnostic (arXiv:2607.05091, Jul 2026)

This framework tests whether a factor model *genuinely explains* return variation or *artificially overcorrects* — a key distinction when validating new factors like IMOM against established benchmarks.

**The problem with existing factor tests**: Standard alpha-t tests only check if abnormal returns persist after controlling for the factor. They cannot distinguish:
- **Genuine explanation**: factor aligns with the economic source of return predictability
- **Overcorrection**: factor model mechanically suppresses a return pattern without economic grounding (e.g., HML artificially penalizes high-momentum stocks that happen to have high B/M)

**The diagnostic**: Measure the integral of the return-characteristic sorted axis (think: the area under the curve when you sort stocks by a characteristic and plot average returns). A factor that *explains* a characteristic will flatten this axis to near-zero. A factor that *overcorrects* will flip the axis negative.

**FF5+MOM findings (from paper):**

| Factor | Effect on characteristic axis | Interpretation |
|--------|-------------------------------|----------------|
| HML | Overcorrects (flips negative) | B/M premium mechanical, not economic |
| CMA | Overcorrects (flips negative) | Investment premium over-absorbed |
| RMW | Flattens to ~0 | Profitability correctly explained |
| UMD (MOM) | Flattens to ~0 | Momentum correctly explained |

**Implication for IMOM (H398):**

IMOM is not in the Fama-French factor library. The characteristic-axis diagnostic would tell us:
1. Does IMOM *explain* variation that MOM (UMD) misses? → If yes: IMOM is a genuine new factor, H398 is theoretically grounded
2. Does IMOM *merely replace* MOM with a better-measured version of the same thing? → If yes: IMOM is a measurement refinement, not a new factor — still valid but no diversification benefit from both
3. Does IMOM overcorrect? → Unlikely given H398 OOS results, but the diagnostic would confirm

**How to run**:
```python
import numpy as np
import pandas as pd

def characteristic_axis_integral(returns: pd.Series, characteristic: pd.Series, n_deciles: int = 10) -> float:
    """Compute integral of return-characteristic axis. Near-zero = genuine explanation; negative = overcorrection."""
    bins = pd.qcut(characteristic, q=n_deciles, labels=False)
    decile_returns = returns.groupby(bins).mean()
    # Integral as trapezoid under sorted decile return curve
    return np.trapz(decile_returns.values, dx=1.0 / n_deciles)

# Usage: run before and after controlling for IMOM, compare integrals
# before_integral = characteristic_axis_integral(raw_returns, momentum_signal)
# after_integral = characteristic_axis_integral(imom_residuals, momentum_signal)
# if abs(after_integral) < abs(before_integral): IMOM explains momentum variation
```

**Relevance to H398 production deployment**: Before going live with H398, run this diagnostic on IMOM6 and IMOM12 vs FF5+UMD. A near-zero after-integral confirms IMOM is theoretically grounded. An overcorrection flag would suggest IMOM is mechanically fitted to the IS period (2013-2020) and may not generalize.

**See also**: Section 13 (Cross-Sectional Factor Correlation Management), Section 11 (Spectral Memory Decomposition Theory), H398 (4-factor equal-weight composite, OOS Sharpe 4.068).

---

## Why Monthly Cross-Sectional Momentum Is Immune to Trend Demise (arXiv:2607.01550)

Kurth, Eisler, Rej, Bouchaud (Jul 2026, presented at Quantitative Finance Conference 2026) studied ~100 liquid futures 1995-2025. Core finding: **short-term trend-following has ceased delivering reliable returns since ~2009 on small-tick contracts across all signal horizons**. Large-tick contracts remain largely intact.

**Mechanism:** Post-2008 HFT market makers withdraw liquidity in front of predictable directional flow on small-tick contracts. This breaks the feedback loop that made short-term trend signals self-reinforcing.

**Why H198/H026/H398A are NOT affected:**
1. **Cross-sectional, not time-series:** H198/H026 rank stocks relative to each other — not directional bets on absolute price continuation. Cross-sectional momentum is a different alpha source than time-series trend.
2. **Monthly horizon:** 1-month rebalancing is far above HFT-affected intraday/daily timeframes. The demise affects signal horizons within days, not months.
3. **Equities, not futures:** H198/H026 universe is large-cap US equities — microstructure differs from liquid futures markets. No tick-size bifurcation applies.

**Implication for H198:** IMOM factors (consistent compounders) are even further immunized — they measure path quality over 6-12 months, not price continuation speed.

**Caution for new hypotheses:** Any new hypothesis using short-term (daily/weekly) time-series momentum signals on liquid instruments should account for post-2009 crowding decay. This is consistent with H298 NOT CONFIRMED (weekly ETF reversal) and H339 NOT CONFIRMED (price momentum filter gates).

**See also**: H198 (cross-sectional momentum, OOS 1.174), H398A (IMOM composite, OOS 4.068), H026 (ETF rotation, production), H298 (NOT CONFIRMED, weekly reversal), H339 (NOT CONFIRMED, price momentum gate).
