---
type: wiki-page
title: The Base-Rate Trap in LLM Trading Signals
description: Why naive directional accuracy metrics mislead in rising markets — honest benchmarking protocol for LLM-based trading signal evaluation (2026 synthesis)
tags: [llm, trading-signals, evaluation, base-rate, timesfm, foundation-models, benchmarking, directional-accuracy]
category: AI Industry
added: 2026-07-19
---

# The Base-Rate Trap in LLM Trading Signals

A recurring failure mode in AI trading research: a fine-tuned model shows 80% directional accuracy and researchers declare success — until someone checks that a naive "always predict up" rule achieves the same accuracy in bull market conditions. This page synthesizes July 2026 research exposing the base-rate trap and the honest benchmarking protocols needed to avoid it.

## The Core Illusion

Cheung (arXiv:2607.12248, Jul 2026) demonstrated the trap concretely using LoRA-adapted TimesFM on equity price forecasting:

- An early LoRA adapter showed ~80% directional accuracy
- This appeared to outperform the zero-shot TimesFM baseline convincingly
- The naive "always-up" rule achieved ~70–80% accuracy on the **same rising market test period**
- The fine-tuned model was **scoring below the base rate**, not above it

The base rate in equity markets is the underlying probability that prices move up over a given horizon. In 2020–2024 bull market conditions, this can be 65–75% for weekly/monthly horizons — making "predict up always" a surprisingly strong baseline that most fine-tuned models fail to beat once properly accounted for.

## The Honest Benchmark Protocol

Cheung's study establishes a rigorous evaluation framework that every LLM trading paper should follow:

### Required Baselines (All Must Be Run)
1. **Zero-shot foundation model** (no fine-tuning)
2. **Always-up rule** (the base-rate baseline — the critical new addition)
3. **Random walk** (Brownian motion null)
4. **Persistence** (yesterday's direction = today's prediction)
5. **AR(1)** (autoregressive baseline)

A model demonstrates genuine directional skill only when it statistically outperforms **all five baselines** — not just the zero-shot version.

### Validation Architecture
- **Frozen-data protocol** with expanding walk-forward windows (no look-ahead in baseline computation)
- **Stratified held-out ticker splits** (not random splits, which leak sector momentum)
- **Statistical tests**: McNemar test for directional accuracy; Diebold-Mariano test for point forecast errors
- **Multiple testing correction**: Benjamini-Hochberg FDR at 5% level across all horizon/universe combinations

### Key Findings from the Replication
Three replicated findings from Cheung:
1. The 80% accuracy reflected a base rate of ~0.70 that the fine-tuned model scored **below**
2. Pooled LoRA showed no directional skill over base rates across any horizon or universe tested
3. Per-sector LoRA significantly **underperformed** pooled adapters (p<0.001) — sector specialization makes it worse, not better

**Bottom line**: Fine-tuning improved point-forecast error (MSE) but did not confer tradeable directional edge. Raw model adaptation is insufficient without explicit base-rate adjustment.

## Volatility Foundation Models: Same Pattern

Brini (arXiv:2607.05291, Jul 2026) tested time-series foundation models (TSFMs) for realized volatility forecasting across 50 assets at multiple horizons, finding a parallel story:

- Only **Tiny Time Mixers (TTM)** consistently beat the Log-HAR econometric benchmark — and only "by a narrow margin"
- Most foundation models failed to improve on established econometric methods at any horizon
- **Best practical guidance**: equal-weight ensemble of TTM + Log-HAR "matches the best single model" without requiring asset-by-asset model selection overhead
- Architecture choice matters more than the foundation model vs. econometric model dichotomy

This mirrors the equity direction finding: foundation models in their current form provide marginal gains at best for financial prediction, and those gains disappear when proper baselines are applied.

## Why This Keeps Happening

The research ecosystem creates systematic pressure toward inflated accuracy claims:

1. **Benchmark gaming**: Models evaluated on recent bull-market periods with high intrinsic up-bias
2. **Look-ahead leakage**: Training data captures period-specific distributional features absent OOS (the KTD-Fin finding)
3. **Wrong null hypothesis**: "Better than zero-shot" is far too weak — must beat the naive always-up rule
4. **Publication selection**: Only positive results are published, creating the reproducibility crisis

The Agentic Trading Survey (arXiv:2605.19337, 2026) quantified this across 77 LLM trading agent papers:
- Only 19/77 satisfied closed-loop evaluation criteria
- 0/19 were fully reproducible
- 63% omitted transaction costs entirely
- None compared against a proper base-rate directional baseline

KTD-Fin (arXiv:2605.28359, 2026) confirmed via Barra factor attribution that LLM trading books exhibit high loadings on **intraday momentum** — meaning "AI alpha" is actually **long-horizon momentum beta** that would be captured by any standard momentum strategy. This is the signal-attribution version of the base-rate trap.

## Implications for George's Pipeline

### PEAD (H174) — Baseline Check

H174 FinBERT gate (score ≥ 0.18 + EPS surprise ≥ 0.02) was validated on n=22 OOS events with WR=81.8%. The base-rate check:
- What fraction of EPS beats produce positive post-announcement drift regardless of sentiment? ~60–65%
- H174's 81.8% WR is clearly above this base rate by 15–20pp
- **Status: passes base-rate test** — genuine signal beyond the base rate

However, this check must be re-run annually as market conditions shift. A 2022-dominated test period would show a lower base-rate (~45% upward drift in down market), which could artificially inflate apparent WR vs. a simple "buy all EPS beats" strategy.

### LLM Alpha Proposals (H381/H382) — Required Tests

Any new LLM-generated alpha factor must be validated against:
- `always_buy_top_momentum` baseline (catches momentum beta disguised as LLM alpha)
- Rolling base-rate for directional accuracy in the specific test period
- Diebold-Mariano test vs. H198 6-1m momentum OOS Sharpe 1.174 baseline
- McNemar test vs. always-up and always-down rules for directional predictions

### The Right Test for LLM Directional Signals

| Test | What It Catches | Implementation |
|------|----------------|----------------|
| Always-up baseline | Base-rate inflation | `np.full(n, 1)` as prediction vector |
| Momentum baseline | Factor loading as LLM alpha | H198 6-1m signal as competing model |
| McNemar test | Statistical difference in directions | `scipy.stats.mcnemar(contingency_table)` |
| Diebold-Mariano | Statistical difference in point forecasts | `arch.tests.diebold_mariano()` |
| BH FDR correction | Multiple testing across horizons | `statsmodels.stats.multitest.multipletests(method='fdr_bh')` |
| Barra attribution | Factor disguise detection | Regress returns on FF5 + momentum factor |

## Historical Parallel: The Anomaly Decay Pattern

This mirrors the broader finding from Chen & Welch (arXiv:2607.06502, 2026): of ~200 published price-based anomalies, median alpha collapsed from 48bp/month pre-2005 to 7bp post-2005 for non-micro-cap stocks. The mechanism is identical — strategies are discovered in favorable sub-periods, published, and arbitraged away. LLM trading papers are now following the same lifecycle at accelerated speed, compressed into months rather than decades due to rapid model sharing.

The base-rate trap is the LLM era's version of data-snooping bias: models pick up the distributional properties of the training period (bull market up-bias) rather than genuine predictive relationships. The speed of iteration in LLM research makes it worse — a new model is "validated" on a rising market quarter before the paper is even submitted.

## Actionable Checklist

Before claiming an LLM model generates trading alpha:

- [ ] Compute base-rate directional accuracy for the test period (what % of periods is price up?)
- [ ] Confirm model directional accuracy > base rate + 2 standard errors (one-sided)
- [ ] Run McNemar test against always-up and always-down rules
- [ ] Run Diebold-Mariano test against AR(1) and persistence models
- [ ] Attribute excess returns via Barra/factor model (ruling out momentum beta, size, etc.)
- [ ] Rerun on held-out period where bull/bear market mix differs from training
- [ ] Apply BH FDR correction across all variants, horizons, and universes tested
- [ ] Verify no look-ahead in base-rate computation (use expanding window, not full-sample)

## Key Papers

- **arXiv:2607.12248** — Cheung (Jul 2026): "When Directional Accuracy Lies: Base-Rate-Honest Benchmark for LoRA-Adapted TimesFM" — primary source, honest benchmark protocol
- **arXiv:2607.05291** — Brini (Jul 2026): "Forecasting Realized Volatility with Time Series Foundation Models" — vol forecasting parallel; TTM marginally best but barely
- **arXiv:2605.28359** — KTD-Fin (2026): Barra attribution reveals LLM alpha = momentum beta; see [LLM Trading Agent Benchmarks 2026](llm-trading-agent-benchmarks-2026.md)
- **arXiv:2605.19337** — Agentic Trading Survey (2026): 0/19 fully reproducible; see [Agentic Trading Survey 2026](agentic-trading-survey-2026.md)
- **arXiv:2607.06502** — Chen & Welch (2026): 7bp post-2005 median alpha; see [What Useful Alphas?](anomaly-decay-chen-welch-2026.md)

## Related Pages

- [LLM Alpha Validation Checklist](../trading/algorithms/llm-alpha-validation.md) — 6-test production gate (predates but complements this page)
- [Agentic Trading Survey 2026](agentic-trading-survey-2026.md) — reproducibility crisis documentation
- [LLM Trading Agent Benchmarks 2026](llm-trading-agent-benchmarks-2026.md) — KTD-Fin Barra attribution
- [What Useful Alphas? — Chen & Welch 2026](anomaly-decay-chen-welch-2026.md) — anomaly decay baseline
- [Time-Series Foundation Models](../trading/algorithms/ts-foundation-models.md) — Chronos/TimesFM/Moirai broader evaluation
- [LLM Alpha Mining Systems 2026](llm-alpha-mining-systems-2026.md) — H381/H382 proposals this page governs
