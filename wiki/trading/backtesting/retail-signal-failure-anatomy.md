---
title: Retail Signal Failure — Anatomy of Popular Rule Failure Under Rigorous Gates
added: 2026-07-23
category: trading/backtesting
source: arXiv:2607.20093 (Darmanin, Jul 2026)
---

# Retail Signal Failure: An Anatomy of Popular Rule Families

## Overview

Darmanin (2026) tests five widely promoted retail signal families — trend, oscillator, candlestick, volume, and calendar rules — against a **three-gate practical viability criterion** that is more stringent than typical academic backtests. The result: zero signal families pass all three gates. This is directly relevant to our hypothesis evaluation framework and validates the multi-gate approach used throughout the H-series log.

## The Three Practical Viability Gates

Darmanin's three gates define "practical viability" as the **conjunction** of:

### Gate 1: Statistical Edge After Multiplicity Correction
- Hierarchical Benjamini-Yekutieli (BY) FDR control across all rule variants
- Stationary-bootstrap confidence intervals (not asymptotic)
- One-sided claim-exclusion tests (NOT "we can't reject H0" — must positively confirm edge)
- **Analogy to our framework**: our single-gate minimum Sharpe thresholds (e.g., OOS Sharpe > 1.174 for H198) are similar but do not apply BY correction. This is a known weakness — the H-series is at risk of multiple testing artifacts.

### Gate 2: Economic Viability After Trading Costs
- Representative bid-ask spread for retail execution (not institutional)
- Round-trip costs modeled per trade, not per bar
- Break-even cost analysis: how much edge remains after costs?
- **Our pipeline comparison**: our cost model (see [Transaction Cost Modeling](transaction-costs.md)) uses similar logic. Key difference: Darmanin uses retail spread models, we use institutional estimates (appropriate for our strategy sizes).

### Gate 3: Finite-Bankroll Survival Under Leverage
- Kelly criterion / ruin probability under practical leverage constraints
- Exposure-matched benchmarks (not raw returns)
- Equivalence tests: distinguish "no evidence of edge" from "evidence of no edge"
- **Our pipeline gap**: we rarely compute ruin probabilities. For strategies with high MaxDD (e.g., H376 6-0m no-skip MaxDD -8.4%), ruin analysis at 2× leverage would be informative.

## Signal Family Results

| Signal Family | Statistical Edge | After Costs | Survival | Notes |
|---|---|---|---|---|
| Trend rules (MA crossovers) | Some variants pass | Most fail | Often fail | By-FDR destroys most |
| Oscillators (RSI, MACD) | None pass | N/A | N/A | Pure noise after correction |
| Candlestick patterns | None pass | N/A | N/A | p-value artifact |
| Volume rules | Marginal pass (1 variant) | Fails | Fails | Volume predictive but not tradeable |
| Calendar rules | Pass (robust) | Pass | Borderline | Monday/TOM effects survive |

**Key finding**: Calendar rules are the only family where statistical edge survives multiplicity correction *and* remains economically meaningful after costs. This is consistent with our H201 TOM CONFIRMED result (OOS Sharpe 0.740).

## Methodological Lessons for H-Series

### 1. The Multiplicity Problem

Darmanin shows that testing 20+ variants of the same signal without BY correction will produce ~1 apparent "significant" result at 5% significance by chance alone. Our H-series has tested hundreds of variants. The BY correction is our [Multiple Testing](multiple-testing.md) page's recommendation that we apply infrequently.

**Mitigation already in place**: We require OOS Sharpe **materially above** baseline (not just p < 0.05). E.g., H198 gate 1.174 vs SPY 0.954. The economic significance requirement partially controls for this.

### 2. Exposure-Matched Benchmarks

Darmanin's most important methodological innovation: comparing a signal's returns to an **exposure-matched random benchmark** (buy-and-hold for the same fraction of time the signal is invested). Strategies that are mostly long a rising market will appear to have "edge" vs cash but are simply long the equity premium.

**Our pipeline gap**: Several H-series strategies (H296 VIX term structure Var D: Sharpe 2.379 but only 3.7% CAGR) are flagged as "deceptive Sharpe" in our log — this matches Darmanin's exposure mismatch problem. We correctly flagged these and excluded them from production.

### 3. The Equivalence Test for Non-Results

Standard significance testing conflates "cannot reject null" with "signal has no edge." Darmanin uses equivalence tests (TOST: two one-sided tests) to actively confirm when a signal has negligible effect. This is relevant for our NOT CONFIRMED results: e.g., H336 (52-week high, OOS 0.342) is confirmed "no edge" not just "insufficient evidence of edge."

### 4. Stationary Bootstrap Confidence Intervals

Politis & Romano (1994) stationary bootstrap preserves serial dependence in the return series, unlike standard bootstrap or t-tests. Our current pipeline uses standard Sharpe ratio with OOS period as point estimate. Adding bootstrap CIs would narrow confidence in borderline results.

**Recommendation**: For any future strategy with OOS Sharpe in the 1.0-1.3 range (borderline cases), add `arch` library bootstrap CI: if the lower CI bound is below 1.0, treat as inconclusive.

## Connection to Retail Trader Failure Patterns

The paper's broader thesis: retail traders fail not because markets are efficient against all signals, but because:

1. **Multiple testing without correction**: testing 50 MA combinations finds one "that works"
2. **Paper trading ≠ live execution**: spread costs and slippage erase thin edges
3. **Finite bankroll ruin**: even strategies with positive expectation fail at leverage (Kelly fraction << 1 for typical retail drawdowns)

These map precisely to our three-gate system: the H-series log's "survivorship bias" section, transaction cost modeling, and MaxDD gates together approximate all three of Darmanin's gates without formal BY correction.

## Implications for H429, H430, H431

- **H429** (text-enhanced regime bond rotation): gate is OOS Sharpe > 1.522 with MaxDD improvement — passes Darmanin's economic viability gate if spread costs are modeled
- **H430** (10-K sentiment): 10-K annual frequency → low turnover → cost drag is minimal; main risk is statistical edge after correction (single variant family)
- **H431** (MRC Shapley): gate is OOS Sharpe > 3.238 — extremely high bar that naturally accounts for multiplicity

## The Calendar Effect Exception

Darmanin's most striking result: **calendar anomalies survive all three gates**. TOM (Turn-of-Month), holiday effects, and some day-of-week effects remain profitable after BY correction, costs, and ruin analysis. This validates:
- H201 TOM CONFIRMED (OOS Sharpe 0.740)
- H292 return seasonality (CONFIRMED with survivorship caveat)
- The behavioral finance explanation: calendar effects are driven by predictable cash flows (pension rebalancing, month-end window dressing) — structural, not statistical artifacts

## References

- Darmanin, A. (2026). "Retail Trader's Ruin: An Anatomy of Popular Signal Failure." arXiv:2607.20093
- Politis, D. & Romano, J. (1994). "The stationary bootstrap." JASA 89(428):1303-1313
- Benjamini, Y. & Yekutieli, D. (2001). "The control of the false discovery rate in multiple testing." Ann. Stat.

## Cross-References

- [Multiple Testing & Statistical Significance](multiple-testing.md) — BY correction, deflated Sharpe
- [Transaction Cost Modeling](transaction-costs.md) — retail vs institutional spread models
- [Walk-Forward & CPCV](walk-forward-cpcv.md) — OOS methodology defense
- [Calendar Anomalies](../algorithms/calendar-anomalies.md) — H201 TOM / H292 seasonality
- [Shared Strategy Evaluation Checklist](../shared-eval-checklist.md) — 7-point pre-production gate
- [Signal Half-Life](signal-halflife.md) — alpha decay context
