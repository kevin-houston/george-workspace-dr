---
updated: 2026-05-11
status: active — H190+ queued
---

# Low-Volatility Anomaly

Empirical finding that low-beta, low-volatility stocks earn higher *risk-adjusted* returns than high-beta stocks — directly contradicting CAPM. One of the most robust anomalies in finance; persists globally, across asset classes, and after factor adjustments.

**Related pages**: [Momentum Strategies](momentum-strategies.md) | [Short-Term Reversal](short-term-reversal.md) | [Position Sizing & Portfolio Construction](position-sizing.md) | [Hypothesis Log](../backtesting/hypothesis-log.md)

---

## Mechanism

CAPM predicts a positive risk-return tradeoff. Empirically, the Security Market Line (SML) is too flat — high-beta stocks underperform their predicted return and low-beta stocks outperform.

Two complementary explanations:

1. **Leverage constraints** (Baker, Bradley & Wurgler 2011): investors who want market-beating returns but can't use leverage buy high-beta stocks as a substitute, bidding them up and suppressing their forward returns. Low-beta stocks are neglected.

2. **Benchmark constraints** (same): fund managers benchmarked to an index are penalized for underperformance relative to it; they overweight high-beta/high-vol stocks chasing upside, systematically overpricing them.

The anomaly is therefore a structural feature of how capital is allocated, not a compensated risk premium.

---

## Three Main Signal Variants

### 1. Low-Volatility Decile (Blitz & Vliet 2007)

Rank stocks by **3-year rolling weekly return std**. Long the bottom decile (lowest vol), equal-weight, monthly rebalance.

| Metric | Value | Notes |
|--------|-------|-------|
| Annual Return | 11.3% | Long-only, US large-cap |
| Sharpe | 0.72 | 1986–2006 |
| MaxDD | -45.9% | Market beta ~0.7 |
| Universe | S&P 500 ~50 stocks | Global version similar |

**Key paper**: Blitz, D. & Vliet, P. van (2007). "The Volatility Effect." *Journal of Portfolio Management*.

```python
import pandas as pd
import numpy as np

def signal_3yr_weekly_vol(daily_prices: pd.DataFrame) -> pd.Series:
    """Blitz & Vliet signal: 3-year rolling weekly volatility (annualized)."""
    weekly = daily_prices.resample("W-FRI").last()
    weekly_ret = weekly.pct_change()
    vol = weekly_ret.rolling(156).std() * np.sqrt(52)  # 156 weeks = 3 years
    return vol  # lower = better (long bottom decile)
```

### 2. Betting Against Beta (BAB) — Frazzini & Pedersen 2014

Construct a market-neutral factor: **long low-beta stocks (leveraged to β=1) + short high-beta stocks (deleveraged to β=1)**.

Beta estimation uses a two-component formula designed to balance responsiveness and stability:
- **Volatility ratio**: 1-year daily rolling std (asset) / 1-year daily rolling std (market)
- **Correlation**: 5-year monthly rolling correlation (60 months)
- β = correlation × (σ_asset / σ_market)

US Stocks 1926–2012: **Sharpe 0.78** — ~2× value factor, ~40% more than momentum in same period.

```python
def compute_bab_beta(returns: pd.Series, market_returns: pd.Series) -> pd.Series:
    """Frazzini-Pedersen beta: vol ratio × long-run correlation."""
    vol_i = returns.rolling(252).std()
    vol_m = market_returns.rolling(252).std()

    monthly_i = returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    monthly_m = market_returns.resample("ME").apply(lambda x: (1 + x).prod() - 1)

    corr_60m = monthly_i.rolling(60).corr(monthly_m)
    beta = corr_60m * (vol_i / vol_m)
    return beta.clip(0.001, 10)  # shrink extremes; Frazzini-Pedersen shrink toward 1

def bab_factor_returns(
    returns: pd.DataFrame, betas: pd.DataFrame, n_long: int = 5, n_short: int = 5
) -> pd.Series:
    """Monthly BAB factor return (market-neutral, beta-scaled)."""
    ranked = betas.rank(axis=1, ascending=True)
    low = ranked <= n_long
    high = ranked > (len(ranked.columns) - n_short)

    # Leverage low-beta to beta=1, deleverage high-beta to beta=1
    w_long = low.div(betas.where(low)).div(low.div(betas.where(low)).sum(axis=1), axis=0)
    w_short = high.div(betas.where(high)).div(high.div(betas.where(high)).sum(axis=1), axis=0)

    r_long = (w_long * returns).sum(axis=1)
    r_short = (w_short * returns).sum(axis=1)
    return r_long - r_short  # market-neutral
```

### 3. 252-Day Daily Volatility (Simpler, Faster Turnover)

Uses 1-year daily returns std instead of 3-year weekly. Higher turnover (~2× vs Blitz & Vliet) but more responsive to volatility regime changes. Sharpe ≈ 0.84 in recent implementations (Emma Kirsten, Nov 2025).

```python
def signal_1yr_daily_vol(daily_prices: pd.DataFrame) -> pd.DataFrame:
    """1-year daily rolling vol — simpler, more responsive than 3yr weekly."""
    returns = daily_prices.pct_change()
    return returns.rolling(252).std() * np.sqrt(252)
```

---

## Sector-Neutral Variant

The raw low-vol strategy loads heavily on Utilities and Consumer Staples (low-beta sectors). A **sector-neutral** version ranks within GICS sectors before forming the portfolio:

```python
def signal_sector_neutral_vol(daily_prices, sector_map, window=252):
    """Rank volatility within each GICS sector."""
    returns = daily_prices.pct_change()
    vol = returns.rolling(window).std() * np.sqrt(252)

    # Last row of vol = current cross-section
    current_vol = vol.iloc[-1].rename("vol")
    df = current_vol.to_frame()
    df["sector"] = df.index.map(sector_map)
    df["rank_within_sector"] = df.groupby("sector")["vol"].rank(ascending=True)
    return df["rank_within_sector"]  # lower rank = lower vol within sector
```

This removes the sector-timing component, isolates pure vol signal, and reduces exposure to sector crowding in SPLV/USMV.

---

## Minimum Variance Portfolio

Full portfolio optimization rather than decile selection. Constrained minimum-variance finds the portfolio with lowest possible variance for a given universe.

```python
# pip install skfolio
from skfolio import Portfolio
from skfolio.optimization import MinimumVariance
from skfolio.preprocessing import prices_to_returns

returns = prices_to_returns(daily_prices)
model = MinimumVariance()
model.fit(returns)
portfolio = model.predict(returns)
# portfolio.weights gives the minimum variance allocation
```

Clarke, de Silva & Thorley show min-var achieves ~25% lower realized volatility than cap-weighted index with comparable long-run returns (Sharpe uplift via vol reduction alone).

---

## Known ETF Implementations (Benchmark / Competition)

| ETF | Issuer | Strategy | AUM (~2026) |
|-----|--------|----------|------------|
| SPLV | Invesco | S&P 500 Low Volatility — bottom 100 by 252d vol | ~$8B |
| USMV | iShares | MSCI Min Vol USA — full optimization + constraints | ~$30B |
| FDLO | Fidelity | Low Volatility Factor — multi-factor tilt | ~$1.5B |

**Crowding risk**: SPLV/USMV launch (~2011) partially arbitraged the anomaly. The simple 252d-vol decile alpha has compressed post-2011; sector-neutral and BAB variants show more resilience.

---

## Performance Benchmark Table

| Variant | Period | Sharpe | CAGR | MaxDD | Source |
|---------|--------|--------|------|-------|--------|
| Low-Vol Decile (3yr weekly) | 1986–2006 | 0.72 | 11.3% | -45.9% | Blitz & Vliet 2007 |
| BAB Factor (US, long-short) | 1926–2012 | 0.78 | — | — | Frazzini & Pedersen 2014 |
| 252d Daily Vol (recent) | ~2020–2025 | 0.84 | — | — | Emma Kirsten Nov 2025 |
| Min Variance | various | ~0.80 | — | 25% less vol | Clarke et al. |

Decay note: all figures pre-date massive ETF crowding. Current raw anomaly alpha is likely 30–50% of historical values; sector-neutral and BAB variants decay more slowly.

---

## Correlation with Other Strategies

| Strategy | Expected Correlation | Notes |
|----------|---------------------|-------|
| H026 ETF Rotation (TSMOM) | Low–negative | Low-vol is defensive; TSMOM often risk-on |
| H181 Industry-Adjusted Reversal | Low–moderate | Both target lower-vol end of universe |
| H188 52-Week High Proximity | Moderate | Both long-only on same stock universe |

Low-vol + momentum historically have near-zero or negative correlation — natural diversifier.

---

## Hypothesis Queue

| H# | Description | Signal | Status |
|----|-------------|--------|--------|
| H190 | H188 + H181 Blend | 52wk-high prox + industry-adjusted reversal on 30-stock universe | QUEUED |
| H191 | Low-Vol Decile (252d daily vol) | Long bottom-6 of 30-stock universe by annual vol | QUEUED |
| H192 | BAB-style Beta Rank | Long bottom-6 by Frazzini-Pedersen beta | QUEUED |
| H193 | Sector-Neutral Low-Vol | Rank within GICS sector, long bottom-6 | QUEUED |
| H194 | Low-Vol + H026 Blend | Portfolio diversification test | QUEUED |

All use the existing 30-stock GICS-mapped universe (`UNIVERSE_SECTORS` in `h181_monthly.py`) and the monthly rebalance pattern from H181/H188.

---

## References

- Blitz, D. & Vliet, P. van (2007). "The Volatility Effect." *Journal of Portfolio Management*. [[Quantpedia summary]](https://quantpedia.com/strategies/low-volatility-factor-effect-in-stocks)
- Frazzini, A. & Pedersen, L.H. (2014). "Betting Against Beta." *Journal of Financial Economics*. [[NBER WP]](https://www.nber.org/system/files/working_papers/w16601/w16601.pdf)
- Baker, M., Bradley, B. & Wurgler, J. (2011). "Benchmarks as Limits to Arbitrage." *Financial Analysts Journal*.
- Clarke, R., de Silva, H. & Thorley, S. (2006). "Minimum-Variance Portfolios in the US Equity Market." *Journal of Portfolio Management*.
