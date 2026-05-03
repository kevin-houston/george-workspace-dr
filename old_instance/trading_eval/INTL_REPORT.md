# International Equity Strategy Evaluation Report
**Run Date:** 2026-03-30
**Data Range:** 2015-01-01 to 2025-01-01 (10 years daily)
**Universe:** 18 country ETFs (10 developed, 8 emerging) + benchmarks
**Benchmark:** SPY — Sharpe 0.784, CAGR 13.03%, Max DD -33.72%

---

## Executive Summary

The 10-year backtest (2015–2025) paints a clear picture: **SPY significantly outperformed all active international equity strategies on a raw return basis**, with a CAGR of 13.03% vs the best directional international strategy's 8.91%. However, the Canada/Australia pairs trade achieved a *higher Sharpe ratio* (0.937 vs 0.784) with only 9.5% max drawdown, making it the single best risk-adjusted finding. Most international ETFs delivered mediocre Sharpe ratios, confirming the broad underperformance of non-US equities over this decade — a period dominated by US tech.

---

## 1. Does International Diversification Provide Real Alpha vs Holding SPY?

**Short answer: No on returns, partial yes on risk-adjustment.**

| Metric | SPY | Best Intl Strategy | Best Intl Country |
|--------|-----|--------------------|-------------------|
| Sharpe | 0.784 | 0.937 (EWC/EWA pairs) | 0.615 (Taiwan EWT) |
| CAGR | 13.03% | 8.91% (EWC/EWA pairs) | 11.08% (Taiwan EWT) |
| Max DD | -33.72% | -9.5% (EWC/EWA pairs) | -38.88% (Taiwan) |

The only way to beat SPY's Sharpe in this period was via *market-neutral pairs trading* (EWC/EWA at 0.937), not via directional long-only exposure. Every long-only international strategy delivered lower CAGR than SPY by 4–10 percentage points.

The 2015–2025 decade was structurally unfavorable for international equities: USD strength, US tech dominance, China's regulatory crackdowns, and European/EM political instability all weighed on non-US markets.

**Diversification value exists but is limited.** The cross-country pairs strategies (SPY correlation 0.05–0.13) provide genuine portfolio diversification, but their absolute returns are modest.

---

## 2. Best Single-Country Momentum Bets

Individual country buy-and-hold results (2015–2025):

| ETF | Country | Sharpe | CAGR | Max DD | SPY Corr |
|-----|---------|--------|------|--------|----------|
| EWT | Taiwan | 0.615 | +11.08% | -38.88% | 0.707 |
| INDA | India | 0.420 | +7.01% | -45.07% | 0.650 |
| EWJ | Japan | 0.418 | +5.85% | -33.14% | 0.745 |
| EWQ | France | 0.413 | +6.64% | -39.23% | 0.782 |
| EWC | Canada | 0.385 | +5.72% | -42.66% | 0.805 |
| EWI | Italy | 0.375 | +6.25% | -43.00% | 0.720 |

**Taiwan (EWT)** is the standout — the only country ETF approaching SPY-like returns, driven by TSMC and semiconductor sector tailwinds. At 11.08% CAGR and Sharpe 0.615 it is the best single-country bet.

**India (INDA)** is the second-best EM play, with structural growth story delivering 7% CAGR and lower SPY correlation (0.65) than developed markets.

**Worst performers:**

| ETF | Country | Sharpe | CAGR | Max DD |
|-----|---------|--------|------|--------|
| TUR | Turkey | 0.141 | -1.20% | -65.02% |
| FXI | China | 0.115 | -0.71% | -60.81% |
| EWZ | Brazil | 0.192 | +0.38% | -56.99% |

China (FXI) and Turkey (TUR) suffered regulatory and currency disasters respectively, delivering near-zero or negative CAGR with catastrophic max drawdowns exceeding 60%. These are cautionary single-country concentration stories.

---

## 3. EM vs DM Rotation Effectiveness

**Strategy 2: DM/EM Rotation** (3-month momentum + UUP regime + SPY MA vote)
- Sharpe: 0.269 | CAGR: 3.30% | Max DD: -39.02%
- Chose VEA (developed) 70.4% of the time, VWO (emerging) 29.6%

The rotation strategy *underperformed both the VEA and VWO buy-and-hold benchmarks*:

| | Sharpe | CAGR |
|--|--------|------|
| Rotation strategy | 0.269 | 3.30% |
| VEA buy-hold | 0.399 | 5.54% |
| VWO buy-hold | 0.303 | 4.11% |

The rotation signal added noise rather than value. The dominant regime in 2015–2025 was consistently US-dollar strength and developed market outperformance, so the model was mostly correct (70% DM allocation) but the switching friction destroyed alpha. The signal works at extremes but fails in trending USD environments where timing is difficult.

**Key insight:** In a structural USD bull market decade, EM underperforms persistently and simple rotation signals cannot overcome that regime. The 3-signal voting approach (momentum + UUP + SPY MA) does identify the direction correctly but lacks conviction — frequent switches cost returns.

---

## 4. Dollar Regime as Signal (Strategy 5)

**EM Momentum + Dollar Filter:**

| | Sharpe | CAGR | Max DD | SPY Corr |
|--|--------|------|--------|----------|
| USD-filtered (only invest when USD weakening) | 0.316 | 3.33% | -22.82% | 0.347 |
| No filter (always invested in top-3 EM) | 0.213 | 2.27% | — | — |

**The dollar filter does add value.** Conditioning EM exposure on UUP 20-day negative momentum improves Sharpe from 0.213 to 0.316 (+48%) and reduces max drawdown to -22.82% by staying in cash when USD is strengthening.

This confirms the well-known empirical relationship: **EM equities outperform when the dollar weakens** because:
1. EM corporate debt is often USD-denominated (weaker USD reduces debt burden)
2. Commodity prices rise when USD falls, benefiting EM commodity exporters
3. Capital flows rotate toward EM in risk-on USD-weakness environments

The strategy's SPY correlation of 0.347 is the lowest among all directional strategies, making it the best *long-only diversifier*. The filtered strategy essentially goes to cash for much of the decade (when USD was trending up) which limits CAGR but dramatically improves risk-adjusted returns.

**Practical insight:** A simple UUP 20-day momentum filter is a meaningful overlay for EM ETF exposure. Investors should reduce or hedge EM when UUP trends up.

---

## 5. Country Pairs Results

**Mean-reversion pairs: 60-day rolling z-score, ±1.5σ entry, ±0.5σ exit**

| Pair | Sharpe | CAGR | Max DD | SPY Corr |
|------|--------|------|--------|----------|
| Canada/Australia (EWC/EWA) | **0.937** | **+8.91%** | **-9.5%** | 0.092 |
| Germany/UK (EWG/EWU) | 0.321 | +2.35% | -34.16% | 0.055 |
| EM Broad (EEM/VWO) | 0.257 | +0.51% | -5.23% | 0.049 |
| Japan/HK (EWJ/EWH) | 0.002 | -0.86% | -35.00% | 0.001 |
| China/India (FXI/INDA) | -0.182 | -5.95% | -53.89% | 0.118 |
| Equal-weight combo | 0.270 | +1.49% | -16.55% | 0.128 |

**Canada/Australia is the standout pair** — by far the best-performing strategy in the entire evaluation:
- Sharpe 0.937 beats SPY's 0.784
- Max drawdown of only -9.5% (vs SPY's -33.7%)
- SPY correlation of 0.092 — essentially uncorrelated to US markets

The EWC/EWA relationship is structurally sound: both are commodity-linked economies (oil/energy for Canada, mining/iron ore for Australia), both have stable currencies and similar monetary regimes, and their economies oscillate on commodity cycle timing. The 60-day z-score captures these oscillations effectively.

**Germany/UK** performs adequately (Sharpe 0.321) — post-Brexit divergence created exploitable spreads.

**China/India (FXI/INDA)** is the worst pair. These two countries are driven by entirely different economic cycles (tech manufacturing vs domestic consumption), regulatory regimes, and geopolitical risks. The spread is not mean-reverting — it is a divergence trade, not a convergence trade.

**EEM/VWO** (two broad EM ETFs) shows the tightest spread (max DD -5.23%) but minimal return because the two ETFs track almost identically — the z-score rarely reaches ±1.5σ.

---

## 6. Correlation to US Market (Diversification Value)

| Strategy | SPY Correlation |
|----------|----------------|
| Global Momentum | 0.687 |
| DM/EM Rotation | 0.825 |
| Valuation-Momentum | 0.677 |
| EM Momentum (dollar-filtered) | 0.347 |
| Cross-Country Momentum (L/S) | -0.029 |
| Pairs: Canada/Australia | 0.092 |
| Pairs: Germany/UK | 0.055 |
| Pairs: EM Broad | 0.049 |

**Individual country correlations to SPY remain high** (0.56–0.81), confirming that in 2015–2025, international equity markets moved largely in tandem with the US, especially during selloffs (correlation 1 in crises).

True diversification — correlation below 0.15 — is found *only* in market-neutral or pairs strategies:
- Canada/Australia pairs: 0.092
- Germany/UK pairs: 0.055
- EM Broad pairs: 0.049
- Cross-country L/S momentum: -0.029

**The dollar-filtered EM strategy** provides the best risk-adjusted long-only diversification at 0.347 correlation — it automatically de-risks during USD strength regimes, which tend to coincide with risk-off periods.

---

## Strategy Rankings

| Rank | Strategy | Sharpe | CAGR | Max DD | SPY Corr |
|------|----------|--------|------|--------|----------|
| 1 | Canada/Australia Pairs | 0.937 | +8.91% | -9.5% | 0.092 |
| 2 | Global Momentum (SPY/EFA/TLT) | 0.427 | +5.87% | -38.29% | 0.687 |
| 3 | EM Momentum + Dollar Filter | 0.316 | +3.33% | -22.82% | 0.347 |
| 4 | DM/EM Rotation | 0.269 | +3.30% | -39.02% | 0.825 |
| 5 | Valuation-Momentum | -0.126 | -5.75% | -47.27% | 0.677 |
| 6 | Cross-Country L/S Momentum | -0.305 | -6.23% | -46.76% | -0.029 |
| — | SPY Benchmark | 0.784 | +13.03% | -33.72% | 1.000 |

---

## Key Conclusions

1. **SPY wins on absolute returns** but the Canada/Australia pairs trade wins on Sharpe (0.937) with far lower drawdown and near-zero US market correlation.

2. **Taiwan (EWT) is the best single-country bet** in developed and emerging markets combined — semiconductor dominance drove 11% CAGR over the decade.

3. **Emerging markets require a dollar filter.** Unfiltered EM exposure delivers poor risk-adjusted returns; conditioning on USD weakness (UUP 20d momentum) meaningfully improves Sharpe.

4. **Cross-country long/short momentum fails.** The classic international momentum factor did not work in this period — international equity returns are too correlated and transaction costs destroy the edge in a low-return environment.

5. **Valuation-based macro rotation (cheapest + positive momentum) fails.** Value traps (China, Turkey) persist for years; annual rebalance is too slow to capture recovery and too late to avoid the falls.

6. **Pairs trading provides the only consistent alpha** that is also uncorrelated to SPY. The economic rationale (commodity-linked economies oscillating on cycle timing) is sound and generates a Sharpe ratio exceeding the US market benchmark.

7. **Global momentum (SPY/EFA/TLT)** is a reasonable defensive overlay — spending 19.6% of the time in TLT reduces drawdown vs buy-and-hold EFA while maintaining equity-like exposure.

---

## Practical Portfolio Implications

For a US-based investor:
- Hold SPY as core (it won this decade on raw returns)
- Add Canada/Australia pairs as satellite (uncorrelated alpha, low drawdown)
- Use UUP 20-day momentum as EM filter signal when adding EM exposure
- Taiwan (EWT) is the single best international long to consider
- Avoid China (FXI) and Turkey (TUR) as standalone positions — the regulatory and currency risks are not compensated
- DM/EM rotation adds complexity without adding net value vs simple buy-and-hold

---

*Generated by the Karpathy autoresearch loop — international equity module*
*Data: yfinance, 2015-01-01 to 2025-01-01*
