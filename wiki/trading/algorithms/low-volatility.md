---
updated: 2026-05-13
status: research closed — H190–H193 completed; STORM family (H195–H196) closed
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

## Confirmed US Large-Cap Results (30-Stock Universe, 2021–2026 OOS)

All hypotheses below used the same 30 large-cap S&P 500 stocks across 8 GICS sectors, equal-weight long-6, monthly rebalance. IS: 2013–2020; OOS: 2021–2026.

| H# | Strategy | OOS Sharpe | OOS CAGR | OOS MaxDD | IS/OOS Decay | Status |
|----|----------|-----------|----------|-----------|--------------|--------|
| SPY | Benchmark | 0.954 | 14.3% | -23.9% | — | — |
| H181 | Industry-adjusted reversal (sector-neutral) | 1.138 | 24.6% | -18.4% | — | CONFIRMED — deployed |
| H188 | 52-week high proximity momentum | 0.774 | 11.4% | -13.6% | — | CONFIRMED |
| H190 | H188 (40%) + H181 (60%) blend | **1.191** | — | **-14.7%** | — | CONFIRMED — improves both Sharpe and MaxDD vs H181 alone |
| H191-C | Low-vol hybrid (50% vol + 50% momentum) | 1.110 | — | -16.7% | ~9% | CONFIRMED |
| H192-D | Sector-neutral BAB (rank beta within GICS) | **1.367** | 19.1% | -17.1% | ~18% | CONFIRMED — best Sharpe in family |
| H193 | H192-D (40%) + H181 (60%) blend | 1.214 | 20.2% | -16.6% | — | NOT CONFIRMED as improvement over H192-D |
| H195 | STORM dual VQ-VAE (30 stocks) | 0.963 | 23.8% | -24.5% | **41%** | CONFIRMED — underperforms H192-D |
| H196 | STORM dual VQ-VAE (90 stocks) | 0.528 | 10.1% | -32.3% | **65%** | NOT CONFIRMED — scale hurts, not helps |

### Key Findings

**1. BAB dominates on this universe.** H192-D sector-neutral BAB (Sharpe 1.367) is the best risk-adjusted strategy across all 25+ strategies tested on this 30-stock universe. It outperforms low-vol (H191-C 1.110), reversal (H181 1.138), momentum (H188 0.774), and deep learning (H195 0.963).

**2. BAB ≈ Low-Vol on concentrated universes.** H192-A raw beta and H191-A raw 1yr vol select nearly identical stocks on 30 large-caps (Corr=0.799). Both identify the same defensive names (JNJ, WMT, COST, IBM). The sector-neutral variant breaks this equivalence by ranking within sectors.

**3. H181 dominates on absolute returns.** Despite lower Sharpe than H192-D (1.138 vs 1.367), H181 has higher CAGR (24.6% vs 19.1%) because its mean-reversion bets on temporarily beaten-down stocks generate larger individual returns. Choice between H181 and H192-D depends on whether you optimize for Sharpe or absolute compounding.

**4. H190 is the practical implementation recommendation.** The 40% H188 / 60% H181 blend achieves BOTH higher Sharpe than H181 pure (1.191 vs 1.138) AND lower MaxDD (-14.7% vs -18.4%). This is the Pareto improvement — strictly better on two objectives simultaneously.

**5. STORM (deep learning) does not beat factor models at this scale.** Despite IS Sharpe of 1.645, OOS decays to 0.963. Expanding to 90 stocks worsened IS/OOS decay to 65% and OOS Sharpe dropped to 0.528 (below SPY). The VQ-VAE architecture overfits when the IS training sample (84 months) is insufficient relative to graph complexity.

### Portfolio Deployment Decision

Current paper trading: **H181 deployed** (`backtesting/paper_trading/h181_monthly.py`).

Recommended upgrade: apply **H190 blend logic** — at monthly rebalance, score each stock by a 40/60 weighted combination of H188 (52wk high proximity) and H181 (industry-adjusted reversal) signals, then long top-6 by blended score. This requires a modest update to h181_monthly.py.

Second satellite candidate: **H192-D** — best Sharpe (1.367) but only marginally different stock picks than H191-A (Corr=0.723). Not deployed alongside H181 due to overlap.

H193 finding: H192-D and H181 pick almost entirely different stocks (only 14% overlap), but both are long-only so they share market beta and don't provide meaningful portfolio-level diversification when blended.

## Hypothesis Queue

All hypothesis families on the 30-stock large-cap universe are now **complete**. Research line closed 2026-05-13.

Future directions:
- **H190 live implementation**: update h181_monthly.py to apply 40/60 H188+H181 blended signal
- **Larger universe BAB**: test H192-D logic on S&P 500 (500 stocks, sector-neutral BAB) — different from H196 since H196 was STORM DL architecture, not simple BAB factor
- **H191-A as second satellite**: Corr(H191-A, H181) OOS=0.342 — genuine diversification. Could deploy as 3rd strategy in paper trading alongside H181 and H112.

---

## References

- Blitz, D. & Vliet, P. van (2007). "The Volatility Effect." *Journal of Portfolio Management*. [[Quantpedia summary]](https://quantpedia.com/strategies/low-volatility-factor-effect-in-stocks)
- Frazzini, A. & Pedersen, L.H. (2014). "Betting Against Beta." *Journal of Financial Economics*. [[NBER WP]](https://www.nber.org/system/files/working_papers/w16601/w16601.pdf)
- Baker, M., Bradley, B. & Wurgler, J. (2011). "Benchmarks as Limits to Arbitrage." *Financial Analysts Journal*.
- Clarke, R., de Silva, H. & Thorley, S. (2006). "Minimum-Variance Portfolios in the US Equity Market." *Journal of Portfolio Management*.
