---
updated: 2026-05-07
status: active
hypothesis: H181 (queued)
source: SSRN:6630998
---

# Short-Term Reversal (Industry-Adjusted)

Short-term reversal is the tendency for last month's losers to outperform last month's winners the following month. Standard reversal has largely disappeared in international markets. **Industry-adjusted reversal is alive, global, and generates +0.53%/month with a six-factor alpha.**

## Source Paper

**"Short-Term Reversal Persists Globally—If Properly Measured"**
- **Authors**: Jan Stosik, Adam Zaremba
- **Date**: April 22, 2026
- **SSRN**: [6630998](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6630998)
- **Data**: CRSP (US) + Compustat (international), 64 countries, Jan 1990–Dec 2023, 5.79M monthly observations, avg 14,193 stocks/month
- **Method**: Monthly quintile sort on each signal within each country; equal- and value-weighted long-short portfolios; six-factor alpha (Fama-French + momentum + reversal factors)

## Core Finding

Standard short-term reversal (raw 1-month return) has essentially died in international markets:

| Signal | Return/month | Significance |
|--------|-------------|--------------|
| Standard reversal (`REV`) | 0.05%/month | Insignificant |
| **Industry-adjusted (`REV^IN`)** | **0.53%/month** | **Sharpe 0.74, α=0.60% (t=4.14)** |
| Regret signal (`REG`) | 0.40%/month | Subsumed by REV^IN |

## Signal Definition

```
REV^IN_{i,t-1} = R_{i,t-1} − R̄_{j,t-1}
```

Where:
- `R_{i,t-1}` = stock i's return in month t-1
- `R̄_{j,t-1}` = equal-weighted mean return of all stocks in industry j in month t-1
- Go **long** bottom quintile (biggest industry-relative losers)
- Go **short** top quintile (biggest industry-relative winners)

The regret signal (`REG = R_{i,t-1} − max(R_k, k∈j)`) is correlated but subsumed by REV^IN in spanning regressions (alpha 0.25%, t=1.34, R²=0.05).

## Country-Level Performance (selected markets)

| Country | REV^IN monthly alpha | Significant? |
|---------|---------------------|--------------|
| United States | 0.34% | Yes |
| United Kingdom | 0.87% | Yes |
| Japan | 0.82% | Yes |
| France | 0.68% | Yes |
| Overall (22/64 countries) | 0.53% | Yes |

Returns persist in developed and emerging markets. Stronger in markets with higher analyst coverage dispersion.

## Why Does Industry-Adjustment Work?

Standard reversal captures both idiosyncratic and industry-level noise. Industry-level reversals are weaker (or absent) because:
- Industry trends are persistent (momentum, not mean-reversion)
- Market-makers don't buffer industry shocks the way they buffer idiosyncratic noise
- After filtering industry effect, what remains is pure idiosyncratic overreaction / liquidity provision premium

The adjustment isolates the **idiosyncratic component** of last month's move — which is what actually mean-reverts.

## Relationship to H026 and Sector Rotation

This is the **opposite end of the frequency spectrum** from H026:

| | H026 (sector rotation) | Short-term reversal |
|--|------------------------|---------------------|
| Frequency | Monthly rebalance | Monthly rebalance |
| Signal lookback | 12 months | 1 month |
| Signal direction | Momentum (buy winners) | Reversal (buy losers) |
| Universe | 25 sector ETFs | Individual stocks |
| Premium source | Trend persistence | Idiosyncratic overreaction |

These two effects are largely uncorrelated — sector momentum and stock-level reversal co-exist. A combined long-short (H026 + industry-adjusted reversal long-short book) could provide diversification.

## Why H179 Failed: Connection to This Paper

H179 attempted international equity rotation — and the root cause of failure maps directly onto this paper's finding. At the ETF level, there's no way to industry-adjust: EFA, EWJ, EWC are market-cap weighted across all industries. The cross-sectional dispersion that H026 exploits (tech vs energy vs healthcare) collapses to a single noisy country-level return. This paper confirms the mechanism: raw return ranking without industry adjustment produces ~0.05%/month, consistent with H179's weak OOS edge.

## Implementation Notes (H181)

**Proposed**: H181 — industry-adjusted short-term reversal, US stocks

### Data requirements
- Minimum: monthly stock-level returns + SIC/GICS industry codes
- Source options:
  - Polygon.io (free tier: limited to recent years; need `$POLYGON_API_KEY`)
  - EDGAR + Compustat-like data via FMP (`$FMP_API_KEY`)
  - yfinance for historical prices; industry codes from FMP fundamentals
- Lookahead bias risk: industry code changes mid-sample (use lagged codes)

### Signal construction
```python
import pandas as pd

def industry_adjusted_reversal(returns_t_minus_1, industry_codes):
    """
    returns_t_minus_1: pd.Series, index = ticker
    industry_codes: pd.Series, index = ticker, value = industry group
    """
    industry_means = returns_t_minus_1.groupby(industry_codes).transform('mean')
    rev_in = returns_t_minus_1 - industry_means
    return rev_in  # sort ascending for long-short: long bottom quintile
```

### Portfolio construction
- Monthly rebalance (align with H026 rebalance timing)
- Equal-weight within quintile
- Long bottom quintile, short top quintile
- Apply to liquid universe (e.g., top 1000 stocks by market cap to avoid small-cap liquidity issues)

### Confirm criteria
- OOS Sharpe > 0.5 (below H026's ~3.0 because this is long-short, not long-only)
- Six-factor alpha significant at p < 0.05
- Performance in minimum 20% of sub-periods (quarterly blocks)

### Priority
- Lower than H168/H171/H175/H176 (those have active prerequisites)
- Queue alongside H180 (after H171)
- Estimate: 2–3h implementation

## Practical Considerations

**Liquidity**: The premium is strongest in small/mid caps — but liquidity is worst there. Apply a minimum ADV filter ($1M+/day) to make the strategy executable.

**Transaction costs**: At 1-month turnover with full quintile rotation, expect ~100% annual turnover on the long side. At 5–10bps per-leg, costs are meaningful but the 0.53%/month gross alpha likely survives.

**Short selling**: Requires a prime broker or margin account. Paper trading version: long-only (bottom quintile) is weaker but operationally simpler.
