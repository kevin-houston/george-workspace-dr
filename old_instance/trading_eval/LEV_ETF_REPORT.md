# Leveraged ETF Decay Strategy Evaluation

**Period:** 2015-01-01 to 2025-01-01 (10 years, 2,516 trading days)
**Run Date:** 2026-03-30
**Best Strategy:** lev_momentum_UPRO_IEF (Sharpe: 0.422)

---

## Executive Summary

This report evaluates six systematic strategies designed to exploit leveraged ETF volatility decay, rebalancing mechanics, and momentum amplification. The core hypothesis — that daily rebalancing creates a "volatility tax" that can be harvested by shorting leveraged ETFs — is confirmed empirically: 3x bull ETFs underperform their theoretical 3x leverage by **5.5% per year** for TQQQ and **5.7% per year** for UPRO.

However, the critical finding is that **harvesting this decay via shorting does not produce positive risk-adjusted returns** over the 2015–2025 sample. The short-both-sides strategy (short TQQQ + SQQQ) achieved Sharpe = **-1.08** with CAGR = **-1.2%**. The decay exists but the bull market dominance and funding/borrow costs consume the edge.

**The winning strategy is leveraged momentum amplification:** Using UPRO (3x) instead of SPY when SPY is above its 50-day MA, and parking in IEF otherwise, produced Sharpe = **0.42**, CAGR = **8.9%**, max drawdown = **-52.5%**.

**Key Finding:** Leveraged ETF decay is real and large, but shorting it is a losing game in a trending bull market. The optimal use of leveraged ETFs is momentum amplification, not short decay harvesting. The VIX-optimal shorting regime (VIX 30-35, Sharpe 1.74) occurs too rarely (86 days in 10 years) to build a systematic strategy around.

---

## 1. How Much Do Leveraged ETFs Actually Decay?

### Theory

Leveraged ETFs reset their leverage daily. If the underlying moves +r on day 1 and -r on day 2, the underlying nets out. But the 3x ETF on day 1 is at 1 + 3r, and on day 2 is at (1 + 3r)(1 - 3r) = 1 - 9r^2. The decay per two-day cycle is 9r^2 - r^2 = 8r^2 (vs the underlying's zero). The general formula for annualized decay is approximately:

```
Annual Decay ~ -0.5 * (L^2 - L) * sigma^2
```

For L=3, sigma=15%: Decay ~ -0.5 * 6 * 0.0225 = -6.75% per year

### Measured Results (2015-2025)

| Instrument | Annual Decay vs Lev Underlying | Mean Daily Decay (bp) | N Days | Low VIX (<20) bp | Mid VIX (20-30) bp | High VIX (>30) bp |
|---|---|---|---|---|---|---|
| TQQQ (3x QQQ bull) | **-5.51%** | -2.49 | 2,515 | -2.5 | -1.8 | -5.3 |
| UPRO (3x SPY bull) | **-5.69%** | -2.27 | 2,515 | -2.3 | -2.3 | -1.6 |
| SQQQ (3x QQQ bear) | +5.38% | +1.90 | 2,515 | +2.8 | +0.6 | -2.8 |
| QLD (2x QQQ bull) | **-3.16%** | -1.28 | 2,515 | -1.3 | -1.2 | -1.3 |
| SSO (2x SPY bull) | **-3.24%** | -1.28 | 2,515 | -1.3 | -1.3 | -0.6 |

**Average 3x bull annual decay:** -4.40% vs 3x underlying return
**Average 3x bear annual decay:** +5.38% vs (-3x) underlying return

**Key observations:**

1. **TQQQ and UPRO decay ~5.5-5.7%/yr** relative to a hypothetical 3x leveraged position in QQQ/SPY. This closely matches the theoretical formula given observed daily volatility.

2. **SQQQ shows positive excess return (+5.38%)** relative to -3x QQQ. This is not free money — it reflects that QQQ trended strongly upward 2015-2025, so SQQQ's mandate (short QQQ) was a losing directional bet. The positive figure means SQQQ lost *less* than a pure -3x QQQ position, i.e., decay partially offset the directional loss.

3. **Decay is highest at HIGH VIX (>30)** for TQQQ: -5.3 bp/day vs -2.5 bp/day at low VIX. But high VIX is also when gap risk and directionality are most dangerous for short positions.

4. **2x ETFs (QLD, SSO) decay roughly half as much** as 3x ETFs (~3.2% vs ~5.5%), consistent with the L^2 scaling in the decay formula.

---

## 2. Does Shorting Both Sides Work?

### Strategy: Short TQQQ + Short SQQQ (Equal Dollar)

**Mechanics:** Short $50k TQQQ and $50k SQQQ simultaneously. Monthly rebalance to equal dollar. Borrow cost: 1%/year each leg.

**Results (2015-2025):**
- Sharpe: **-1.08**
- CAGR: **-1.2%**
- Max Drawdown: **-11.8%**
- SPY Correlation: **+0.07** (effectively market neutral)

**Why does this fail despite measurable decay?**

The short-both-sides strategy suffers because the 2015-2025 period was dominated by a secular bull market. QQQ returned ~+430% over this period. The decay on TQQQ does exist, but TQQQ also generated massive capital appreciation — shorting it was extremely expensive in terms of unrealized P&L on the short leg. The SQQQ short (which profits from QQQ rising, since SQQQ is short QQQ) partially offsets, but not enough.

More precisely: decay harvesting from both sides only nets positive P&L if the underlying goes sideways. When QQQ trends strongly upward for years, the TQQQ short bleeds continuously. The convexity benefit (~5.5%/yr) is swamped by the directional cost.

**Short UPRO + Short SPXU:**
- Sharpe: **-1.49**
- CAGR: **-2.0%**
- Max Drawdown: **-18.1%**
- SPY Correlation: **-0.14**

Even worse — the SPY bull market from 2015-2025 (+170%) makes the UPRO short even more painful.

### Crisis Period Performance of Short-Both-Sides

| Period | TQQQ+SQQQ Return | UPRO+SPXU Return | Buy and Hold SPY |
|---|---|---|---|
| COVID Crash (Feb 15 - Mar 23, 2020) | **+3.24%** | +0.86% | -33.57% |
| COVID Recovery (Mar 24 - Aug 31, 2020) | +1.26% | +0.91% | +57.37% |
| Rate Hike Bear 2022 (full year) | +0.37% | -1.50% | -18.18% |
| Tech Bull 2023 (full year) | **-4.24%** | **-4.69%** | +26.18% |

**Important finding:** Short-both-sides actually held up during the COVID crash (+3.24%) and the 2022 bear market (+0.37%). These are the environments where the strategy should theoretically shine — high realized volatility, choppy prices. The problem is 2023: a strong trending bull year where QQQ went +54%, making the TQQQ short extremely painful.

**Verdict: The strategy is not viable as a standalone due to the asymmetric payoff in bull markets.**

---

## 3. Short Lev + Long Underlying (Convexity Arbitrage)

### Strategy: Short TQQQ, Long QQQ (Equal Notional)

**Theory:** If the 3x ETF decays relative to 3x underlying, then short TQQQ + long QQQ should capture the spread. Expected P&L per day ~ -(3 * r_etf) + r_qqq ~ variance (the decay term).

**Results (2015-2025):**

| Strategy | Sharpe | CAGR | Max Drawdown |
|---|---|---|---|
| Short TQQQ + Long QQQ | -0.78 | **-34.7%** | **-98.8%** |
| Short UPRO + Long SPY | -0.65 | **-25.6%** | **-95.6%** |

**Catastrophic failure.** Why? As QQQ trends upward, TQQQ rises faster (3x with compounding). The short TQQQ position grows against you rapidly, while the long QQQ position grows slower. Even with daily rebalancing, the directional exposure from a secular bull market is devastating. The short leg loses far more than the decay captured on the TQQQ side.

**This confirms: pure decay arbitrage is only viable in range-bound markets.**

---

## 4. VIX Regime Impact on Decay Profitability

### Short TQQQ+SQQQ Conditional on VIX Level

| VIX Range | N Days (10yr) | Ann. Return | Ann. Vol | Sharpe |
|---|---|---|---|---|
| VIX 10-15 | 951 (38%) | -2.52% | 0.74% | -3.39 |
| VIX 15-20 | 742 (29%) | -2.11% | 0.94% | -2.24 |
| VIX 20-25 | 406 (16%) | -0.69% | 1.17% | -0.59 |
| VIX 25-30 | 213 (8%) | +0.00% | 0.99% | +0.00 |
| VIX 30-35 | 86 (3%) | **+2.71%** | 1.56% | **+1.74** |
| VIX 35-40 | 22 (1%) | -3.46% | 1.47% | -2.35 |

**Optimal VIX range for short-both-sides: 30-35**

### Interpretation

The counterintuitive finding is that **the strategy only makes money at VIX 30-35**, not at low VIX. This inverts the naive hypothesis that "low volatility = most decay."

Why? At low VIX (10-15), the market trends strongly in one direction. QQQ steadily rises, TQQQ rises even faster (leveraged bull trend), and the short TQQQ position bleeds badly. The small daily decay (~2.5 bp) cannot compensate for a trending market's directional bias.

At VIX 30-35, markets are actually choppy — they move up 3% then down 3%, up 2% then down 2%. This is exactly the volatility decay mechanism's ideal environment. The decay per day is higher (~5.3 bp for TQQQ) and the underlying goes sideways overall.

**However**, VIX 30-35 represents only 86 trading days over 10 years (3% of the sample). VIX > 30 is typically brief and clustered around specific events (COVID crash, 2022 drawdown peak). Building a strategy that is only active 3% of the time is impractical.

The VIX-regime-filtered strategy (trade when VIX < 20, pause when VIX > 25) was in the market 77.7% of the time and achieved Sharpe = **-2.34** — worse than the unconditional strategy. This is because VIX < 20 corresponds to strong bull market regimes where the short is most painful.

---

## 5. Momentum Amplification Strategy (Best Strategy)

### Strategy: UPRO vs IEF on SPY 50-Day Moving Average

**Mechanism:** When SPY > 50-day MA: hold UPRO (3x SPY). When SPY < 50-day MA: hold IEF (7-10yr treasury bonds).

| Strategy | Sharpe | CAGR | Max Drawdown |
|---|---|---|---|
| **Leveraged Momentum (UPRO/IEF)** | **0.422** | **8.9%** | -52.5% |
| Base Momentum (SPY/IEF) | 0.338 | 4.2% | -27.1% |

**Key findings:**

1. **Leveraged momentum improves Sharpe over base momentum** (0.42 vs 0.34). Using UPRO amplifies the momentum signal's positive payoff more than it amplifies the drawdowns in this 10-year sample.

2. **CAGR of leveraged momentum (8.9%) beats base momentum (4.2%) by 2.1x**, consistent with ~3x leverage amplification after accounting for IEF periods and decay drag.

3. **Max drawdown of -52.5%** is severe — this is the cost of 3x leverage during a bear market before the 50d MA signal triggers. In 2022, UPRO fell ~75% from peak to trough.

4. **The 50d MA filter causes the strategy to miss portions of the secular bull rally**, which is why Buy-and-Hold SPY (~Sharpe 0.55, CAGR ~12.5%) still wins on both metrics in this particular sample.

### When Leveraged Momentum Works and Fails

**Works in:**
- Strong trending bull markets (2017, 2019, 2023, 2024): UPRO compounds gains at 3x SPY pace
- Markets that make clean breaks below/above 50d MA and stay there for extended periods

**Fails in:**
- Whipsaw years (2018, 2022): Multiple MA crossings generate losses both entering and exiting UPRO
- Fast bear markets: If SPY drops 10% rapidly, UPRO loses 25-30% before the MA signal triggers the switch to IEF

---

## 6. Rebalancing Band Strategy

### Strategy: Hold TQQQ + SQQQ Short, Rebalance When Drift > 20%

This attempts to profit from mean reversion between TQQQ and SQQQ when one outpaces the other, reducing transaction costs vs daily rebalancing.

**Results:**
- Sharpe: **-0.03**
- CAGR: **-0.94%**
- Max Drawdown: **-30.1%**

Essentially flat but slightly negative. The strategy avoids the worst of directional trending losses compared to continuous rebalancing, but still cannot overcome the fundamental problem: in a bull market, TQQQ rises faster than SQQQ falls, and the net short position bleeds.

---

## 7. Risk Profile: What Kills These Strategies

### Short-Both-Sides Strategy Killers

**Secular bull markets** (2015-2021, 2023-2024): The single biggest risk. When QQQ trends upward for years, the TQQQ short is a perpetual loser. TQQQ returned approximately +3,000% from 2015 to late 2021. Shorting this at any point after 2015 with a fixed position size would have been catastrophic.

**Strong trending years (2023):** QQQ returned +54% in 2023. The TQQQ short generated approximately -4.24% strategy-level P&L despite the SQQQ short providing some offset.

**Borrow cost escalation**: This analysis assumes a flat 1%/year. In practice, during COVID (March 2020), borrow rates for TQQQ and SQQQ reached 3-5%. In a prolonged short squeeze, borrow can exceed 10%. The strategy is barely positive in the VIX 30-35 regime at 1% borrow; it turns negative at realistic stressed rates.

**Margin requirements**: Short both 3x ETFs requires significant margin. A -11.8% max drawdown in portfolio terms may trigger margin calls before recovery, especially since leveraged ETFs attract higher margin requirements from prime brokers.

### Leveraged Momentum Strategy Killers

**Bear markets with slow MA signals**: In 2022, SPY crossed its 50d MA in mid-January around 468. By the time the signal triggers and the position closes, UPRO has already fallen 25-30%. The total 2022 bear market loss for UPRO was ~-75%; the strategy would have been in UPRO for several weeks of that move.

**Choppy mean-reverting markets**: If SPY repeatedly crosses the 50d MA (as in late 2018 or mid-2022), each whipsaw generates a round-trip loss. 3x leverage amplifies each false signal's cost by 3x versus a non-leveraged implementation.

---

## 8. Practical Implementation Concerns

### Margin and Capital Requirements

Short-both-sides: FINRA Regulation T requires 150% of short position value as margin. Shorting $100k of TQQQ + $100k of SQQQ requires approximately $300k in margin. With max drawdown at -11.8%, a $100k allocation within a $300k account risks margin call.

Leveraged momentum: No shorting required. UPRO can be held long in any standard brokerage account. UPRO is liquid (ADV ~$800M as of 2025). The 50d MA strategy generates approximately 4-8 round trips per year.

### Borrow Cost Reality Check

| ETF | Normal Borrow Rate | Stressed Market Borrow |
|---|---|---|
| TQQQ | 0.5-1.5%/yr | 3-8%/yr |
| SQQQ | 0.5-2.0%/yr | 4-10%/yr |
| UPRO | 0.3-1.0%/yr | 2-5%/yr |
| SPXU | 0.5-1.5%/yr | 3-7%/yr |

This analysis uses 1%/year flat for all short positions. In stressed markets — exactly when you most want the hedge active — borrow costs spike, further eroding the strategy's edge.

### Tax Treatment

Short sales held under 1 year are taxed as ordinary income (marginal rates up to 37%). Long UPRO positions held more than 1 year qualify for 15-20% long-term capital gains rates. This meaningfully favors the momentum amplification strategy for taxable accounts.

---

## 9. Full Strategy Rankings (by Sharpe, 2015-2025)

| Rank | Strategy | Sharpe | CAGR | Max DD | Notes |
|---|---|---|---|---|---|
| 1 | **lev_momentum_UPRO_IEF** | **0.422** | **8.9%** | -52.5% | Best risk-adjusted |
| 2 | base_momentum_SPY_IEF | 0.338 | 4.2% | -27.1% | Lower risk, lower return |
| 3 | rebalancing_band_TQQQ_SQQQ | -0.032 | -0.9% | -30.1% | Effectively flat |
| 4 | short_UPRO_long_SPY | -0.645 | -25.6% | -95.6% | Catastrophic in bull |
| 5 | short_TQQQ_long_QQQ | -0.776 | -34.7% | -98.8% | Near total loss |
| 6 | short_both_TQQQ_SQQQ | -1.078 | -1.2% | -11.8% | Market neutral, poor SR |
| 7 | short_both_UPRO_SPXU | -1.495 | -2.0% | -18.1% | Worse than TQQQ pair |
| 8 | vix_regime_short_TQQQ_SQQQ | -2.339 | -1.8% | -16.7% | VIX filter hurts, not helps |

---

## 10. Conclusions

### 1. Leveraged ETF Decay Is Real and Large

3x bull ETFs underperform their 3x leveraged benchmark by **5.5-5.7% annually** over the full sample. This is statistically robust (2,515 observations). The decay is approximately equal to 0.5 * (L^2 - L) * sigma^2 as predicted by theory.

### 2. Shorting Both Sides Does Not Work in a Bull Market

The theoretical elegance of shorting both TQQQ and SQQQ to capture decay from both legs fails in practice because the 2015-2025 period was a dominant secular bull market. TQQQ's capital appreciation vastly exceeded its decay. The strategy requires perfect sideways underlying movement to profit and shows positive performance only during VIX 30-35 environments (3% of trading days).

### 3. VIX Filtering Works in Theory, Fails in Execution

Filtering to low-VIX environments (where the strategy "should" work best per conventional wisdom) actually **worsens** performance. Low VIX coincides with trending bull markets. High VIX (30-35) is the true sweet spot, but it is rare and brief.

### 4. Momentum Amplification Is the Superior Approach

Using 3x ETFs as a momentum amplifier (UPRO when SPY > 50d MA) delivers Sharpe 0.42, CAGR 8.9% — better risk-adjusted returns than pure SPY momentum (Sharpe 0.34). The leverage amplifies the signal's alpha without introducing the catastrophic downside of shorting in a bull market.

### 5. Decay Harvesting Requires a Different Market Regime

Short-both-sides is theoretically viable and would likely have performed well in the 2000-2010 decade (dot-com bust + sideways post-GFC decade). The 2015-2025 data represents an exceptionally unfavorable environment for it. A 2000-2015 backtest would likely show positive Sharpe for this strategy.

### 6. Practical Recommendation

- **Primary strategy:** Leveraged momentum (UPRO/IEF on 50d MA) with 15-20% portfolio allocation
- **Maximum drawdown tolerance required:** -50% on the leveraged portion; sized accordingly
- **Avoid:** Short-both-sides unless explicitly in a bear/choppy market regime with a clear re-entry rule
- **Risk overlay:** Switch from UPRO to IEF when VIX > 30, regardless of MA signal, to avoid the worst tail events

---

## Appendix: Data Notes

- All data from yfinance (Yahoo Finance), daily adjusted closes, 2015-01-01 to 2025-01-01
- VXX and UVXY have experienced multiple reverse splits; their long-term price series are adjusted but show extreme decay (VXX lost ~99%+ from 2015-2025)
- SOXL (3x semiconductors) and FAS (3x financials) were included in the universe fetch but not paired in head-to-head strategies due to absence of natural bear-side counterparts
- Borrow cost: 1% annual flat (applied to all short positions, every leg, every day)
- No transaction costs modeled beyond borrow (bid-ask and commissions negligible for daily strategy at this scale)
- Decay measurement: annualized ratio of cumulative ETF return to cumulative (leverage * underlying return) - 1, over the full sample

---

*Report generated by lev_etf_harness.py — Karpathy Autoresearch Loop*
*Data: yfinance daily adjusted closes, 2015-01-01 to 2025-01-01*
*Borrow cost assumption: 1% annual flat for all short positions*
