# R35 — Minimum Regime Performance (MRP) Diagnostic

**Run date:** 2026-04-15  
**Strategies analysed:** 1311  
**Summary:** 0 of 1296 classified strategies are regime-resilient; 162 are bull-only; 991 are inconsistent; 143 are weak; 15 have insufficient regime data.

## Methodology

Per-regime Sharpe ratios are estimated using a price-proxy approach:
for each strategy, representative ticker daily returns are scaled by the
ratio of the strategy's overall Sharpe to the ticker's B&H Sharpe,
then split into FRED-labeled macro regimes.

**Regime definitions** (from `macro_harness.classify_regimes()`):
- `calm` — no active macro stressors
- `stress` — VIX > 25 or HY spread > 500bp
- `tightening` — inverted yield curve or rising Fed Funds
- `easing` — Fed Funds falling
- `oil_shock` — WTI > 90d mean + 1.5σ
- `inflationary` — CPI YoY > 3.5% (or BIE > 2.8%)
- `oil_high` — WTI > 90d rolling mean
- `gold_bull` — Gold 6m momentum > +5%

## Regime Durations

| Regime | Days | % Time |
|--------|-----:|-------:|
| calm | 1,725 | — |
| stress | 493 | — |
| tightening | 1,113 | — |
| easing | 548 | — |
| oil_shock | 683 | — |
| inflationary | 580 | — |
| oil_high | 1,971 | — |
| gold_bull | 1,619 | — |

## Strategy Rankings by MRP Score

> MRP Score = minimum Sharpe ratio across all regimes with sufficient data.
> Higher is better. `regime_resilient` = min Sharpe > 0.5 across ≥ 3 regimes.

### Regime-Resilient Strategies

| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes | Calm | Stress | Tighten | Easing |
|-----:|----------|---------------:|----------:|----------:|-----:|-------:|--------:|-------:|

### Bull-Market-Only Strategies

| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes | Calm | Stress |
|-----:|----------|---------------:|----------:|----------:|-----:|-------:|
| 1 | PM_12_1 (R01) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 2 | PM_12_1 (R02) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 3 | PM_12_1 (R03) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 4 | PM_12_1 (R04) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 5 | PM_12_1 (R05) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 6 | PM_12_1 (R06) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 7 | PM_12_1 (R07) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 8 | PM_12_1 (R08) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 9 | PM_12_1 (R09) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 10 | PM_12_1 (R10) | 0.421 | -0.836 | 8 | 0.76 | -0.84 |
| 11 | PMO_50_30 (R06) | 0.383 | -0.851 | 8 | 0.77 | -0.85 |
| 12 | PMO_50_30 (R07) | 0.383 | -0.851 | 8 | 0.77 | -0.85 |
| 13 | PMO_50_30 (R08) | 0.383 | -0.851 | 8 | 0.77 | -0.85 |
| 14 | PMO_50_30 (R09) | 0.383 | -0.851 | 8 | 0.77 | -0.85 |
| 15 | PMO_50_30 (R10) | 0.383 | -0.851 | 8 | 0.77 | -0.85 |
| 16 | LV55_mom_gate (R04) | 0.425 | -0.861 | 8 | 0.79 | -0.86 |
| 17 | LV55_mom_gate (R05) | 0.425 | -0.861 | 8 | 0.79 | -0.86 |
| 18 | LV55_mom_gate (R06) | 0.425 | -0.861 | 8 | 0.79 | -0.86 |
| 19 | LV55_mom_gate (R07) | 0.425 | -0.861 | 8 | 0.79 | -0.86 |
| 20 | LV55_mom_gate (R08) | 0.425 | -0.861 | 8 | 0.79 | -0.86 |

### Inconsistent Strategies (pass some regimes, fail others)

| Rank | Strategy | Overall Sharpe | MRP Score | # Regimes |
|-----:|----------|---------------:|----------:|----------:|
| 1 | MR_20_15 (R01) | 0.236 | -0.384 | 8 |
| 2 | MR_20_15 (R02) | 0.236 | -0.384 | 8 |
| 3 | MR_20_15 (R03) | 0.236 | -0.384 | 8 |
| 4 | MR_20_15 (R04) | 0.236 | -0.384 | 8 |
| 5 | MR_20_15 (R05) | 0.236 | -0.384 | 8 |
| 6 | MR_20_15 (R06) | 0.236 | -0.384 | 8 |
| 7 | MR_20_15 (R07) | 0.236 | -0.384 | 8 |
| 8 | MR_20_15 (R08) | 0.236 | -0.384 | 8 |
| 9 | MR_20_15 (R09) | 0.236 | -0.384 | 8 |
| 10 | MR_20_15 (R10) | 0.236 | -0.384 | 8 |
| 11 | LV55_gate_MA10 (R04) | 0.251 | -0.424 | 8 |
| 12 | LV55_gate_MA10 (R05) | 0.251 | -0.424 | 8 |
| 13 | LV55_gate_MA10 (R06) | 0.251 | -0.424 | 8 |
| 14 | LV55_gate_MA10 (R07) | 0.251 | -0.424 | 8 |
| 15 | LV55_gate_MA10 (R08) | 0.251 | -0.424 | 8 |
| 16 | LV55_gate_MA10 (R09) | 0.251 | -0.424 | 8 |
| 17 | LV55_gate_MA10 (R10) | 0.251 | -0.424 | 8 |
| 18 | MR_20_2 (R01) | 0.269 | -0.533 | 8 |
| 19 | BB_20 (R01) | 0.269 | -0.533 | 8 |
| 20 | MR_20_2 (R02) | 0.269 | -0.533 | 8 |

### Weak Strategies (poor overall)

| Strategy | Overall Sharpe | MRP Score |
|----------|---------------:|----------:|
| MR_60_2 (R01) | 0.181 | -0.246 |
| MR_60_2 (R02) | 0.181 | -0.246 |
| MR_60_2 (R03) | 0.181 | -0.246 |
| MR_60_2 (R04) | 0.181 | -0.246 |
| MR_60_2 (R05) | 0.181 | -0.246 |
| MR_60_2 (R06) | 0.181 | -0.246 |
| MR_60_2 (R07) | 0.181 | -0.246 |
| MR_60_2 (R08) | 0.181 | -0.246 |
| MR_60_2 (R09) | 0.181 | -0.246 |
| MR_60_2 (R10) | 0.181 | -0.246 |
| DC_55 (R01) | 0.084 | -0.270 |
| DC_55 (R02) | 0.084 | -0.270 |
| DC_55 (R03) | 0.084 | -0.270 |
| DC_55 (R04) | 0.084 | -0.270 |
| DC_55 (R05) | 0.084 | -0.270 |

## Classification Summary

| Classification | Count | % of Classified |
|----------------|------:|----------------:|
| regime_resilient | 0 | 0.0% |
| bull_only | 162 | 12.5% |
| inconsistent | 991 | 76.5% |
| weak | 143 | 11.0% |
| insufficient_data | 15 | — |

## Notes on Estimation Method

- Regime Sharpe ratios are **estimated** (proxy method), not exact replays.
- For round_001-010 strategies: per-ticker B&H returns are scaled by
  the strategy/B&H Sharpe ratio, then split by regime.
- For macro rounds (R11-R18): same approach using UNIVERSE tickers.
- The proxy preserves directional regime sensitivity but smooths
  cross-sectional variation. Use for ranking, not precise measurement.
- Minimum 60 trading days required per regime to include it.

*Generated by r35_mrp_diagnostic.py on 2026-04-15*