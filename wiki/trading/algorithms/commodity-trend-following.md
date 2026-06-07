---
title: Commodity Trend Following
added: 2026-06-07
updated: 2026-06-07
category: algorithms
tags: [momentum, CTA, commodities, trend-following, ETF]
hypotheses: [H261, H261b, H262]
---

# Commodity Trend Following

## Overview

Commodity trend following (also called CTA-style momentum) is one of the oldest documented sources of risk premia in financial markets. Academic research confirms that commodity futures exhibit persistent momentum at 1–12 month horizons, and this momentum is largely uncorrelated with equity and bond returns. The key diversification insight: commodity trend following tends to profit in inflationary bear markets — precisely when equity and bond momentum strategies fail together (2022: SPY -18%, TLT -26%, while DBC +25%, USO +50%).

**Primary academic reference:** Asness, Moskowitz & Pedersen (2013) "Value and Momentum Everywhere" — confirmed momentum in commodity futures alongside equity, bond, FX, and country equity markets.

**Key property:** Low correlation with equity momentum. Our H261b backtest confirmed Corr(H261b, SPY) = 0.218 OOS 2018-2025 — the lowest SPY correlation of any confirmed hypothesis in our pipeline.

---

## ETF Universe

Commodity ETFs fall into two categories: those backed by commodity futures (subject to roll yield and contango) and physically-backed funds (gold, silver).

### Usable ETF Universe (all live by 2007)

| ETF | Asset | Type | Expense | Notes |
|-----|-------|------|---------|-------|
| GLD | Gold | Physical | 0.40% | Most liquid; no roll yield drag; no K-1 |
| SLV | Silver | Physical | 0.50% | More volatile than GLD |
| DBC | Broad commodities | Futures | 0.85% | ~14-asset basket; **issues K-1** |
| USO | Oil (WTI) | Futures | 0.45% | High volatility; **issues K-1** |
| DBA | Agriculture | Futures | 0.85% | Corn/wheat/soybeans/sugar; **issues K-1** |
| DBO | Oil | Futures | 0.83% | Optimized roll strategy vs USO |
| PDBC | Broad commodities | Futures | 0.59% | Tax-friendly (no K-1!) replaces DBC; live 2014 |
| CPER | Copper | Futures | 0.65% | **Issues K-1**; live 2011 |
| UNG | Natural gas | Futures | 1.06% | ⚠️ **Avoid** — mean-reverting, extreme drawdowns |
| CORN/WEAT/SOYB | Grain ETFs | Futures | ~0.25% | Narrow, very seasonal |

### K-1 Tax Caveat

DBC, USO, DBA, UNG, CPER issue **IRS Schedule K-1** (partnership income) rather than a 1099-DIV. This:
- Delays tax filing (K-1s often arrive late)
- Reports phantom income even when you haven't sold
- Complicates after-tax return modeling

**Workaround:** Prefer GLD (physical gold), SLV (physical silver), and PDBC (commodity index, no K-1) for tax-friendly commodity exposure. Or hold in a tax-advantaged account.

---

## Roll Yield & Contango

Commodity futures ETFs periodically roll expiring contracts to the next month. In **contango** (future price > spot), rolling is costly because you sell cheap near-term futures and buy expensive far-term futures. This creates a structural drag:

- **Normal backwardation** (futures < spot): rolling earns a positive yield — typical for oil during supply crunches
- **Contango** (futures > spot): rolling loses money — common for natural gas, often for oil in glut conditions

**Magnitude:** Contango drag can cost 15-30%/year for natural gas (UNG), 5-15%/year for oil (USO) in sustained contango. This is why UNG performs so poorly as a trend-following vehicle.

**Better commodity baskets:** DBC and PDBC use "optimized roll" strategies that avoid the worst contango by rolling to longer-dated contracts when the front-to-back spread is unfavorable. This reduces (but doesn't eliminate) contango drag.

---

## Signal Design

Standard academic signal for commodity trend following:

```python
# 6-month momentum, skip 1 month, lagged 1 month (no look-ahead)
# price(t-2) / price(t-8) - 1, evaluated at month t
r6_raw = monthly.shift(1) / monthly.shift(7) - 1
signal  = r6_raw.shift(1)   # signal at t uses data through t-1
```

The skip-1m lag avoids the short-term reversal effect (assets that went up in the most recent month tend to reverse slightly). The additional 1m lag ensures no look-ahead bias.

### Dual Momentum Gate

A **dual momentum** gate (Antonacci 2014) requires both:
1. **Relative momentum**: which asset is ranked highest among peers
2. **Absolute momentum**: the chosen asset must also be above BIL (i.e., positive 6m return)

If the top-ranked asset has negative absolute momentum → hold BIL.

```python
ranked = signal.sort_values(ascending=False)
positive_assets = [a for a in ranked.index if signal[a] > 0]
if not positive_assets:
    hold = "BIL"           # all negative: cash
elif len(positive_assets) >= 2:
    hold = positive_assets[:2]   # Top-2 (H261b style)
else:
    hold = positive_assets[:1]   # Only 1 positive
```

---

## Backtest Results

### H261 — Top-1, 6-ETF Universe (includes UNG) | NOT CONFIRMED

| Period | Sharpe | CAGR | MaxDD | NegYrs |
|--------|--------|------|-------|--------|
| IS 2010-2017 | -0.105 | -7.5% | -78.0% | 5 |
| OOS 2018-2025 | 0.239 | 2.2% | -60.7% | 2 |

**Failure:** UNG single-asset concentration → MaxDD -78% IS. Single-asset top-1 is catastrophic with natural gas. Corr(SPY) OOS = 0.186 (diversification thesis valid, implementation invalid).

### H261b — Top-2, 5-ETF Universe (UNG excluded) | CONFIRMED

| Period | Sharpe | CAGR | MaxDD | NegYrs |
|--------|--------|------|-------|--------|
| IS 2010-2017 | 0.256 | 2.8% | -40.4% | 3 |
| OOS 2018-2025 | **0.922** | **19.7%** | -26.9% | 2 |

**Annual OOS breakdown:**

| Year | H261b | SPY |
|------|-------|-----|
| 2018 | -6.7% | -4.6% |
| 2019 | +5.4% | +31.5% |
| 2020 | +23.9% | +18.4% |
| 2021 | +33.3% | +28.7% |
| 2022 | **+26.7%** | **-18.2%** |
| 2023 | -5.6% | +26.3% |
| 2024 | +17.3% | +25.0% |
| 2025 | +68.8% | est. +15% |

SPY OOS Sharpe = 0.865. Corr(H261b, SPY) OOS = **0.218** — genuinely low.

### IS/OOS Disconnect

IS Sharpe 0.256 vs OOS Sharpe 0.922 is a significant gap. Root cause: the IS period (2010-2017) was the commodity bear market driven by the oil glut (USO -65% from 2014-2016) and Chinese demand slowdown. The OOS period coincided with two commodity bull runs:
1. 2020: COVID commodity rebound (DBC, GLD surge)
2. 2021-2022: Energy/inflation supercycle (USO, DBC, GLD all strong)

**Conclusion:** This is a **regime-dependent** strategy. It produces excellent crisis alpha in inflationary environments but struggles in commodity bears. Not unconditional alpha.

---

## Production Portfolio Fit

| Criterion | Assessment |
|-----------|-----------|
| Standalone Sharpe (OOS) | 0.922 — solid but below production blend (4.158) |
| SPY correlation | 0.218 — **excellent** diversification |
| 2022 performance | +26.7% vs SPY -18.2% — **genuine crisis alpha** |
| IS weakness | MaxDD -40.4%, Sharpe 0.256 in commodity bear |
| K-1 complexity | DBC, USO issue K-1 — manageable in tax-advantaged account |
| Recommended allocation | 5-10% of production portfolio after 6-month paper forward test |

**Current status:** On paper forward test. NOT added to production until behavior in an IS-like commodity bear regime is observed.

---

## Extensions (Queued)

### H262 — Bayesian Short+Long CTA Decomposition

**Source:** arXiv:2507.15876 (2025) "Re-evaluating Short- and Long-Term Trend Factors in CTA Replication: A Bayesian Graphical Approach"

CTAs historically blend short-term momentum (~3 month) and long-term trend (~12 month) signals. A Bayesian graphical model decomposition shows these factors contribute independently to CTA returns. Extension of H261b:
- **Short signal:** 3-month momentum (skip 1m, lag 1m)
- **Long signal:** 12-month momentum (skip 1m, lag 1m)
- **Blend:** Bayesian posterior weighting vs 50/50 equal weight
- Gate: improve OOS Sharpe vs H261b baseline 0.922

### Alternative Implementation: PDBC-Based

Replace DBC with PDBC (no K-1, tax-friendly) and add GLD, SLV, DBO (optimized oil roll). Universe: GLD, SLV, PDBC, DBO, DBA. Shorter IS possible (PDBC live 2014) but avoids K-1 entirely.

---

## Implementation Notes

```python
# H261b universe (no UNG, no DBC for K-1 avoidance → use PDBC variant)
ASSETS    = ["GLD", "SLV", "DBC", "USO", "DBA"]
DEFENSIVE = "BIL"
TOP_N     = 2

# Download + signal
monthly = yf.download(ASSETS + [DEFENSIVE], start="2008-01-01",
                      auto_adjust=True, progress=False
                     )["Close"].resample("ME").last()
r6_raw  = monthly.shift(1) / monthly.shift(7) - 1
signal  = r6_raw.shift(1)

# Monthly allocation
def get_allocation(date):
    s = signal.loc[date, ASSETS].dropna()
    positive = s[s > 0].sort_values(ascending=False)
    if len(positive) == 0:
        return {DEFENSIVE: 1.0}
    hold = list(positive.index[:TOP_N])
    return {a: 1.0 / len(hold) for a in hold}
```

Script: `backtesting/daily/run_h261b.py` (confirmed, runnable).
Results: `backtesting/results/h261b_results.json`.
