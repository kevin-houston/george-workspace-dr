---
updated: 2026-05-12
status: active
hypothesis: H181 (confirmed 2026-05-07), H190 (confirmed 2026-05-11)
source: SSRN:6630998
---

# Short-Term Reversal (Industry-Adjusted)

Short-term reversal is the tendency for last month's losers to outperform last month's winners the following month. Standard reversal has largely disappeared in international markets. **Industry-adjusted reversal is alive, global, and generates +0.53%/month with a six-factor alpha.**

---

## Literature Foundation

### Seminal Papers

| Paper | Signal | Return | Universe |
|-------|--------|--------|----------|
| Jegadeesh (1990) | 1-month loser minus winner | ~2.0%/month | NYSE/AMEX 1934–1987 |
| Lehmann (1990) | Weekly loser minus winner | ~1.7%/week | NYSE/AMEX 1962–1986 |
| Stosik & Zaremba (2026) | Industry-adjusted 1-month | 0.53%/month | 64 countries 1990–2023 |

Jegadeesh (1990) used an equally-weighted long-losers/short-winners portfolio. Lehmann (1990) operated at weekly frequency. Both documented that the effect was economically large before transaction costs.

### Why It Works: Two Competing Explanations

**1. Investor Overreaction (Behavioral)**
Lehmann (1990) hypothesized that short-term predictability reflects investor overreaction, "fads," or cognitive biases — prices overshoot, then correct.

**2. Liquidity Provision Premium (Market Microstructure)**
Campbell, Grossman & Wang (1993): uninformed order flow causes temporary price concessions that liquidity providers absorb. The reversal is compensation for bearing inventory risk. This is now the consensus explanation for the bulk of the effect.

Key evidence: **Nagel (2012) "Evaporating Liquidity"** (*Review of Financial Studies* 25(7): 2005–2039) showed that reversal strategy returns are **strongly predictable with the VIX**. During financial crises, conditional Sharpe Ratios spike dramatically — consistent with the liquidity-provision story (when liquidity providers withdraw, the required compensation rises). Even industry-portfolio reversal strategies produce high Sharpe during high-VIX regimes.

**Implication for implementation**: reversal strategies are *long volatility* — they systematically earn more during market stress and crash with the market when liquidity provision dries up.

---

## Source Paper (H181 Basis)

**"Short-Term Reversal Persists Globally—If Properly Measured"**
- **Authors**: Jan Stosik, Adam Zaremba
- **Date**: April 22, 2026
- **SSRN**: [6630998](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6630998)
- **Data**: CRSP (US) + Compustat (international), 64 countries, Jan 1990–Dec 2023, 5.79M monthly observations, avg 14,193 stocks/month
- **Method**: Monthly quintile sort on each signal within each country; equal- and value-weighted long-short portfolios; six-factor alpha (Fama-French + momentum + reversal factors)

---

## Core Finding

Standard short-term reversal (raw 1-month return) has essentially died in international markets:

| Signal | Return/month | Significance |
|--------|-------------|--------------|
| Standard reversal (`REV`) | 0.05%/month | Insignificant |
| **Industry-adjusted (`REV^IN`)** | **0.53%/month** | **Sharpe 0.74, α=0.60% (t=4.14)** |
| Regret signal (`REG`) | 0.40%/month | Subsumed by REV^IN |

---

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

---

## Return Decay Profile

Reversal profits are **highly time-concentrated**. Research consistently finds:

| Period after formation | Raw reversal return |
|------------------------|---------------------|
| Month 1 | ~1.57% |
| Month 2 | ~0.40% |
| Month 3+ | ~0.00% |

At the **intraday / daily level**, ~90% of idiosyncratic price shocks are permanent (real information), and only ~10% is temporary. The temporary component has a **half-life of ~2.5 days**. This means:
- Weekly rebalancing captures more of the reversal than monthly
- Monthly signal formation still works because the large cross-sectional spread more than compensates

**End-of-day reversal** (Baltussen, Da & Soebhag): a significant portion of monthly reversal accrues from the last-15-minutes price move reversing at the next open. Relevant for optimizing execution timing.

---

## Interaction: 52-Week High and Turnover

Recent research (2024 *Pacific-Basin Finance Journal*) shows reversal and momentum are **not uniform across stocks** — they depend on two moderating variables:

| Condition | Effect |
|-----------|--------|
| High turnover + near 52-week-high | **Momentum** (buy winners) |
| Low turnover + far below 52-week-high | **Reversal** (buy losers) |

Practical implication: a pure long-short reversal strategy mixes momentum and reversal signals by accident. Filtering to *low-turnover stocks far below 52-week-high* for the long leg and *high-turnover stocks near 52-week-high* for the short leg creates a cleaner reversal book.

This connects directly to H181 (industry-adjusted) and H188 (52-week high proximity momentum): they naturally segment stocks into these regimes, which is why their overlap in H190 is so low (0.4/6 stocks on average).

---

## Country-Level Performance (selected markets)

| Country | REV^IN monthly alpha | Significant? |
|---------|---------------------|--------------|
| United States | 0.34% | Yes |
| United Kingdom | 0.87% | Yes |
| Japan | 0.82% | Yes |
| France | 0.68% | Yes |
| Overall (22/64 countries) | 0.53% | Yes |

Returns persist in developed and emerging markets. Stronger in markets with higher analyst coverage dispersion.

---

## Why Does Industry-Adjustment Work?

Standard reversal captures both idiosyncratic and industry-level noise. Industry-level reversals are weaker (or absent) because:
- Industry trends are persistent (momentum, not mean-reversion)
- Market-makers don't buffer industry shocks the way they buffer idiosyncratic noise
- After filtering industry effect, what remains is pure idiosyncratic overreaction / liquidity provision premium

The adjustment isolates the **idiosyncratic component** of last month's move — which is what actually mean-reverts.

---

## Transaction Costs: The Real Challenge

**Bid-ask bounce** (Jegadeesh 1987, Roll 1984): much of the raw reversal signal in early studies was an artifact of prices bouncing between bid and ask. Using midpoint returns removes this mechanical component. The effect survives but is smaller.

**Cost tiering by market cap**:

| Universe | Net return | Notes |
|----------|-----------|-------|
| Small-cap stocks | Negative (net) | Excessive spread + impact costs |
| Large-cap (100 largest) | +30–50 bps/week | Quantpedia, weekly rebalance |

The Quantpedia strategy (100 largest stocks, weekly rebalance, 1990–2009):
- **Sharpe Ratio**: 1.09
- **CAGR**: 16.25%
- **Volatility**: 14.94%
- **Max Drawdown**: -52.94%

The high Sharpe is achievable because weekly rebalancing in large-cap stocks has very low transaction costs relative to the alpha. Note the large max drawdown — consistent with the liquidity-provision (long-volatility) nature of the strategy.

**Turnover vs. alpha tradeoff**: Monthly rebalancing has ~100% annual long-side turnover. At 5–10 bps per leg, costs are meaningful but the 0.53%/month gross alpha survives in large caps. For small-cap universes, this math inverts.

---

## Python Implementation

### Signal Construction (industry-adjusted)

```python
import pandas as pd

def industry_adjusted_reversal(returns_t_minus_1: pd.Series, industry_codes: pd.Series) -> pd.Series:
    """
    returns_t_minus_1: pd.Series, index = ticker
    industry_codes: pd.Series, index = ticker, value = SIC/GICS group
    Returns: REV^IN — sort ascending for long (bottom quintile) / short (top quintile)
    """
    industry_means = returns_t_minus_1.groupby(industry_codes).transform("mean")
    return returns_t_minus_1 - industry_means
```

### 52-Week High Filter (separate momentum/reversal regimes)

```python
def classify_regime(row, turnover_col="turnover_rank", proximity_col="price_to_52w_high"):
    """
    Separates stocks likely to momentum-continue vs. mean-revert.
    High turnover + near 52w high → momentum regime (exclude from reversal long)
    Low turnover + far from 52w high → reversal regime (include in reversal long)
    """
    high_turn = row[turnover_col] > 0.5  # top half by turnover
    near_high = row[proximity_col] > 0.9  # within 10% of 52-week high
    if not high_turn and not near_high:
        return "reversal"
    elif high_turn and near_high:
        return "momentum"
    return "neutral"
```

### Portfolio Construction

```python
def build_reversal_portfolio(signals: pd.Series, n_stocks: int = 10) -> dict:
    """
    signals: REV^IN values, index = ticker
    Returns: dict with 'long' and 'short' ticker lists
    """
    sorted_signals = signals.sort_values()
    return {
        "long": sorted_signals.head(n_stocks).index.tolist(),   # bottom = biggest losers
        "short": sorted_signals.tail(n_stocks).index.tolist(),  # top = biggest winners
    }
```

### VIX-Conditional Sizing (Nagel 2012)

```python
def vix_adjusted_weight(base_weight: float, current_vix: float, vix_ma: float) -> float:
    """
    Scale position size with VIX relative to its 12-month moving average.
    During crises (VIX >> MA), reversal alpha is higher but drawdowns deeper.
    """
    vix_ratio = current_vix / vix_ma
    return base_weight * min(vix_ratio, 2.0)  # cap at 2x leverage
```

---

## Relationship to Active Hypotheses

### H181 (Confirmed 2026-05-07)
Industry-adjusted short-term reversal on 30-stock universe. OOS Sharpe = 1.138, MaxDD = -18.4%. Long-only variant (bottom quintile) avoids short-selling complexity. Result: signal is cleanest when industry groups have ≥ 5 stocks.

### H188 (Confirmed)
52-week high proximity momentum on same 30-stock universe. Near-antithesis signal to H181 — but same positive market beta means correlation = 0.389, not negative.

### H190 (Confirmed 2026-05-11)
40% H188 + 60% H181 blend. Sharpe = 1.191, MaxDD = -14.7%. Average stock overlap = 0.4/6, confirming the regime-segmentation logic above: these signals are applied to different subsets of the universe at almost every rebalance. This validates the 52-week-high/turnover segmentation insight.

### H192 (Queued)
BAB (Betting Against Beta) market-neutral variant. Conceptually complementary to reversal: BAB targets cross-sectional beta spread while reversal targets cross-sectional return spread.

---

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

---

## Why H179 Failed: Connection to This Page

H179 attempted international equity rotation — and the root cause of failure maps directly onto this paper's finding. At the ETF level, there's no way to industry-adjust: EFA, EWJ, EWC are market-cap weighted across all industries. The cross-sectional dispersion that H026 exploits (tech vs energy vs healthcare) collapses to a single noisy country-level return. This paper confirms the mechanism: raw return ranking without industry adjustment produces ~0.05%/month, consistent with H179's weak OOS edge.

---

## Implementation Notes (H181)

### Data Requirements
- Minimum: monthly stock-level returns + SIC/GICS industry codes
- Source options:
  - Polygon.io (free tier: limited to recent years; need `$POLYGON_API_KEY`)
  - EDGAR + Compustat-like data via FMP (`$FMP_API_KEY`)
  - yfinance for historical prices; industry codes from FMP fundamentals
- Lookahead bias risk: industry code changes mid-sample (use lagged codes)

### Portfolio Construction
- Monthly rebalance (align with H026 rebalance timing)
- Equal-weight within quintile
- Long bottom quintile, short top quintile
- Apply to liquid universe (e.g., top 1000 stocks by market cap to avoid small-cap liquidity issues)

### Confirm Criteria
- OOS Sharpe > 0.5 (below H026's ~3.0 because this is long-short, not long-only)
- Six-factor alpha significant at p < 0.05
- Performance in minimum 20% of sub-periods (quarterly blocks)

---

## Practical Considerations

**Liquidity**: The premium is strongest in small/mid caps — but liquidity is worst there. Apply a minimum ADV filter ($1M+/day) to make the strategy executable.

**Transaction costs**: At 1-month turnover with full quintile rotation, expect ~100% annual turnover on the long side. At 5–10 bps per-leg, costs are meaningful but the 0.53%/month gross alpha likely survives.

**Short selling**: Requires a prime broker or margin account. Paper trading version: long-only (bottom quintile) is weaker but operationally simpler.

**Crisis behavior**: Reversal is long-volatility / short-liquidity. During crises, Sharpe spikes but drawdowns also spike. The -52.94% max drawdown in the Quantpedia backtest illustrates this. Position sizing should be volatility-targeted, not fixed-weight.

**Execution timing**: Given the ~2.5-day half-life of idiosyncratic shocks and the end-of-day reversal effect, for monthly strategies: execute at the open on the first trading day of the month (not at the close of the last day) to avoid giving back end-of-month drift.

---

## Key References

- Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance* 45(3), 881–898.
- Lehmann, B.N. (1990). Fads, martingales, and market efficiency. *Quarterly Journal of Economics* 105(1), 1–28.
- Campbell, J., Grossman, S., & Wang, J. (1993). Trading volume and serial correlation in stock returns. *Quarterly Journal of Economics* 108(4), 905–939.
- Nagel, S. (2012). Evaporating liquidity. *Review of Financial Studies* 25(7), 2005–2039. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1988706)
- Stosik, J. & Zaremba, A. (2026). Short-term reversal persists globally — if properly measured. [SSRN:6630998](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6630998)
- Quantpedia: [Short Term Reversal Effect in Stocks](https://quantpedia.com/strategies/short-term-reversal-in-stocks)
