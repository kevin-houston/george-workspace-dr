---
title: Quant Convergence — Classical Value Investing and Modern Factor Models
tags: factor-models, value-investing, machine-learning, graham, quantitative, equity-selection
added: 2026-07-27
category: Trading / Concepts
---

# Quant Convergence — Classical Value Investing and Modern Factor Models

**Source**: arXiv:2606.24575 (Yamazaki & Garrido-Lestache, Jun 2026)

A study testing whether Benjamin Graham's classic value rules can act as a mathematical "low-pass filter" on complex ML models trained on 20 years of S&P 500 data. The 4-year test window (March 2022 – March 2026) covers both the 2022 crash and the subsequent AI-driven bull market — a particularly demanding OOS period.

---

## Core Hypothesis

Modern ML models (XGBoost, AutoGluon) memorize short-term market noise rather than identifying companies with durable value. Graham's rules — developed during the Great Depression to identify margin of safety — serve as a regularizer: they filter out the high-volatility growth stocks that ML would overweight.

This is a formalization of a practitioner insight: **momentum and value are natural complements**. Momentum selects what the market is bidding up; value filters ensure the bid-up names have fundamental backing.

---

## Experimental Design

- **Universe**: S&P 500 constituents (point-in-time construction over 20 years)
- **Feature sets tested**:
  - *Pure Graham*: P/E, P/B, Current Ratio, Debt/NCA, EPS growth — classical screeners
  - *Modern factors*: price momentum, volatility, sector, market cap
  - *Combined*: both sets together
- **Models**: Random Forest, XGBoost, AutoGluon (automated ML)
- **Strategy**: buy-and-hold over 4-year OOS period (March 2022 – March 2026)

---

## Key Results

| Model | Return | MaxDD | Calmar | Interpretation |
|-------|--------|-------|--------|----------------|
| AutoGluon (complex ML) | 222.68% | -39.78% | 5.59 | Chased volatile tech, large drawdown |
| **Pure Graham RF** | **232.13%** | **-18.9%** | **1.38** | Best risk-adjusted; avoided tech collapse |
| Combined RF (mom + Graham) | 202.91% | -34.53% | 5.88 | Diversified, lowest MaxDD tested |
| Pure momentum RF | ~180% | ~-42% | ~4.3 | Momentum alone — higher vol |

Note: Calmar Ratio here is return/MaxDD (not annualized), so higher = more return per unit of max drawdown endured.

**Key finding**: Graham's "margin of safety" constraints act as a regime-adaptive filter. During 2022 (rising rates, multiple compression), Graham-compliant stocks (low P/E, strong balance sheets) outperformed dramatically. During 2023-2026 AI bull market, the Graham filter cost some upside (excluded high-P/E tech) but the combined RF partially recovered this by blending momentum back in.

---

## Graham Filter Criteria

Benjamin Graham's quantitative criteria (from *The Intelligent Investor*, 1949; Security Analysis, 1934):

1. **P/E < 15**: Earnings yield ≥ 6.7% (margin of safety vs bonds)
2. **P/B < 1.5**: Price-to-book below 1.5 (asset value backing)
3. **Current Ratio > 2.0**: Adequate liquidity to cover near-term obligations
4. **Long-term Debt / Net Current Assets < 1.0**: Balance sheet conservatism
5. **EPS growth ≥ 0 in each of last 5 years**: No deteriorating earnings trend
6. **Dividend history**: (optional) Continuous dividends for 20+ years

**Critical observation**: These criteria would **exclude virtually all 30 stocks in the H198 NASDAQ universe** (AAPL, MSFT, NVDA, META all have P/E > 20-100). This is why H466 requires relaxed Graham proxies for testing on H198.

---

## Relevance to H198 Family

The Graham-ML study reinforces several findings from our hypothesis log:

| H198 Hypothesis | Connection to Graham Study |
|---|---|
| H337 NOT CONFIRMED (quality GP/A tiebreaker) | Same root cause: 30-stock large-cap universe has insufficient quality variation for screening |
| H448 NOT CONFIRMED (low-vol screener) | Low-vol stocks ~ Graham P/B<1.5 stocks in current market; 30-stock universe doesn't have this variety |
| H466 PROPOSED (Graham ML filter) | Direct port; expects strict Graham to eliminate most stocks; relaxed Graham may add mild value |
| H398 CONFIRMED (IMOM6+MOM60+LowVol+IMOM12) | The LowVol component is the H198-universe's closest analog to Graham quality screening |

**Key insight from convergence**: Graham value + momentum is complementary in an environment where the Graham universe (cheap, stable businesses) and the momentum universe (trending, high-growth tech) are largely non-overlapping. The "convergence" paper finds that the combination works because each catches different parts of the return distribution.

---

## Implications for Production Portfolio

1. **H026 (ETF rotation)**: The macro analog to Graham rules is the **bond ETF tilt during bear regimes** (H301/H165a, VIX>25 route to BIL). Both are margin-of-safety mechanisms — avoiding expensive assets during stress.

2. **H045 (bond rotation)**: Already embeds a Graham-like "quality" proxy — SHY (short-duration Treasuries) is selected 72% of OOS months, reflecting the conservative bias that Graham rules enforce.

3. **Value as diversifier**: If H466 confirms that Graham quality filter adds value on a *broader universe* (e.g., Russell 1000 vs H198's 30 stocks), it could serve as a low-correlation satellite to the momentum-dominated H026/H198 strategies.

---

## Future Research Directions

- **H466** (proposed): Port to H198 with relaxed Graham criteria; test as momentum pre-filter
- **H337b** (queued): Broader 200-stock universe for GP/A quality — Graham filters may have more cross-sectional spread there
- **Value-Momentum Interaction**: Asness, Moskowitz & Pedersen (2013) confirm value and momentum are negatively correlated; combining them in a 50/50 portfolio has historically improved Sharpe significantly

---

## Cross-References
- [Value Factors](../trading/algorithms/value-factors.md) — FCF yield, COWZ, H284/H286
- [Quality Factor (QMJ, Piotroski, GP/Assets)](../trading/algorithms/quality-factor.md) — AQR QMJ, H221/H222
- [Momentum Strategies](../trading/algorithms/momentum-strategies.md) — H198, H026 production
- [Factor Models & Cross-Sectional Alpha](../trading/algorithms/factor-models.md) — Fama-French context
- [Long-Short Equity](../trading/algorithms/long-short-equity.md) — Graham-quality L/S design context
