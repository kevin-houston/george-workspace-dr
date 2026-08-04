---
title: QuantSightBench — Prediction-Interval Calibration for LLM Numeric Forecasting
tags: ai-industry, llm-benchmarks, calibration, uncertainty, numeric-forecasting, prediction-intervals
added: 2026-08-04
category: AI Industry
---

# QuantSightBench — Prediction-Interval Calibration for LLM Numeric Forecasting

**Source**: arXiv:2604.15859 (Qin & Andriushchenko, ELLIS Institute Tübingen / Max Planck Institute for Intelligent Systems / Tübingen AI Center, Apr 2026)

## The Problem Being Solved

[FinBench](finbench-calibration-2026.md) established that LLM **classification/categorical** confidence is poorly calibrated for financial decisions — a model 55% accurate but 80% confident produces negative Kelly growth. QuantSightBench asks the complementary question: when an LLM is asked to forecast a **continuous numeric quantity** with an explicit prediction interval (e.g. "what will metric X be, give a 90% confidence range"), is that interval actually calibrated?

This is a structurally different task from FinBERT-style sentiment scoring or a bull/bear classification vote. It's the shape of question a trading pipeline would ask for things like: an EPS-surprise magnitude estimate, a volatility forecast range, a price-target band, or an aggregate order-flow estimate — any place a strategy wants a *number with error bars* out of an LLM rather than a bounded score or a discrete label.

## Benchmark Design

- 1,000 forecasting questions across 8 domains: business/finance, economics, public health, demographics, sports, science, and others
- Three evaluation settings: zero-shot, background-context prompt, and **agentic** (model can retrieve news articles before forecasting)
- Three evaluation axes:
  1. **Calibration / Coverage** — does the model's stated X% interval actually contain the true value X% of the time?
  2. **Sharpness (Mean Log Interval Score, MLIS)** — narrower intervals score better, but only if coverage holds; a model can't game sharpness by giving deliberately wide intervals without being penalized elsewhere
  3. **Scale Awareness** — does calibration hold across magnitude ranges, from fractional quantities to 100K+?

## Models Evaluated

11 frontier and open-weight models: GPT-5.4, GPT-5.1, Claude Opus 4.5, Claude Sonnet 4.5, Gemini 3.1 Pro, Grok 4, DeepSeek v3.2, GLM-4.7, Kimi (plus others in the full set).

## Key Findings

### Systematic overconfidence, even at the frontier

No model achieved the target 90% coverage at the 90% confidence level. Best performer:

| Model | Coverage @ 90% target |
|---|---|
| Gemini 3.1 Pro | 79.1% |
| Grok 4 | 76.4% |
| GPT-5.4 | 75.3% |

All frontier models fell **10+ percentage points short** of nominal coverage — meaning stated 90% intervals actually contain the true value roughly 75-79% of the time. The gap is smaller than FinBench's categorical-confidence gap but still large enough to matter for sizing decisions built on interval width.

### Scale degradation is the sharpest finding

Coverage is not uniform across magnitude:

| Magnitude range | Typical coverage |
|---|---|
| 1–10 | >80% for most models |
| 100K+ | <65% for most models |

Intervals get systematically *too narrow* exactly where the true numbers get large — i.e. exactly the regime a trading application cares about (large notional price targets, large-cap market-cap estimates, aggregate volume/flow magnitudes). This is the opposite of a comforting result: the failure mode gets worse, not better, at the scale where a real position-sizing decision would be riding on the interval.

### Agentic retrieval helps open-weight models more than frontier models

Open-weight models (DeepSeek, GLM, Kimi) showed larger calibration improvement from retrieval access than frontier models did. This suggests their gap is more about *information access* (not having seen enough recent data) than a fundamental reasoning/calibration defect — while frontier models' overconfidence looks closer to intrinsic miscalibration that additional context doesn't fix as cleanly.

### Extended reasoning has diminishing returns

Extended reasoning effort improved calibration for weaker models but showed diminishing (near-zero) returns for already-strong performers — mirroring a pattern seen elsewhere in the LLM calibration literature (see [LLM Metacognition survey](../tools/llm-metacognition-2026.md): "individuated calibration fails — aggregate ECE ≠ per-query accuracy").

## Relationship to FinBench (Categorical Calibration)

| | FinBench (arXiv:2607.16229) | QuantSightBench (arXiv:2604.15859) |
|---|---|---|
| Output type | Categorical probability / classification confidence | Continuous quantity + prediction interval |
| Failure mode | Confidence-competence gap; overconfident-but-slightly-better-than-chance | Overconfident interval width; worsens at scale |
| Financial analog | FinBERT sentiment score, bull/bear vote | Price target, EPS-surprise magnitude, volatility forecast |
| Fix path (untested by either paper) | Isotonic/Platt/temperature recalibration | Conformal prediction wrapping (standard fix for interval undercoverage, not tested in the paper) |

Both papers are needed for a complete calibration picture: FinBench covers the "is this signal reliable enough to size a bet on" question for discrete scores; QuantSightBench covers the same question for numeric estimates with error bars. Neither paper has been applied to a George production signal yet — H174's FinBERT score is the closest existing case, and it falls under FinBench's categorical framing, not QuantSightBench's.

## Implications for George's Pipeline

No hypothesis in the H1–H489 log has yet asked an LLM to directly output a numeric estimate with an uncertainty band, as opposed to a bounded classification score. This benchmark is the first citation to check against if that changes — e.g. if a future proposal in the H279/H280/H281 queue (LLM momentum filter, MarketSenseAI 4-agent, macro-LLM ETF tilt) or a new idea asks an LLM to produce something like "expected EPS surprise magnitude, ±90% CI" rather than a [0,1] sentiment score.

**Practical takeaway if this pattern is ever used**: assume actual coverage on a stated 90% LLM-generated interval is closer to 65-80%, worse at large magnitude, and plan to either (a) wrap the raw LLM interval in a conformal-prediction correction layer calibrated on historical IS data (the standard fix for exactly this undercoverage failure mode — untested here but well-established in the broader ML literature), or (b) treat the LLM interval as a rough prior and widen it by a fixed multiplicative safety factor before it touches any Kelly-style position-sizing formula, following the same discipline FinBench recommends for categorical scores.

**Not staged as a new hypothesis.** This is a capability-limitation finding relevant to *future* LLM-numeric-forecast proposals, logged so any such proposal starts from an honest calibration prior rather than discovering the scale-degradation problem the hard way in a live backtest.

## Cross-References
- [FinBench — Calibration and Uncertainty Benchmarking for Agentic Financial Forecasting](finbench-calibration-2026.md) — categorical/classification calibration counterpart; Kelly-sizing implications
- [LLM Alpha Validation Checklist](../trading/algorithms/llm-alpha-validation.md) — 6-test gate; calibration checks belong under Test 4 (Predictive Calibration)
- [The Base-Rate Trap in LLM Trading Signals](base-rate-trap-llm-trading-2026.md) — related honest-benchmark discipline (5-baseline protocol, McNemar/DM tests) for LLM forecasting claims
- [LLM Metacognition (arXiv:2607.11881)](../tools/llm-metacognition-2026.md) — broader survey; individuated calibration failure, RL-with-metacognitive-feedback as training-time fix
- [PEAD — Post-Earnings Announcement Drift](../trading/algorithms/pead.md) — H174 production pipeline; nearest existing analog (categorical, not numeric-interval)
