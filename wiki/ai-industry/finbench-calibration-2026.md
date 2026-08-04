---
title: FinBench — Calibration and Uncertainty Benchmarking for Agentic Financial Forecasting
tags: ai-industry, llm-benchmarks, calibration, uncertainty, financial-forecasting, kelly, proper-scoring
added: 2026-07-27
updated: 2026-08-04
category: AI Industry
---

# FinBench — Calibration and Uncertainty Benchmarking for Agentic Financial Forecasting

**Source**: arXiv:2607.16229 (Ghosh & Devarakonda, Jul 2026)

## The Problem Being Solved

Most financial LLM benchmarks measure *direction accuracy* (did the model predict up/down correctly?) or *point RMSE* (how close was the price forecast?). Neither metric captures **calibration**: whether the model's expressed confidence accurately reflects its true accuracy.

FinBench fills this gap with a benchmark specifically designed to evaluate probabilistic calibration under:
- **Strict time-gating**: all evaluation windows use only information available before the prediction date
- **Market non-stationarity**: measures calibration separately across bull/bear/sideways regimes
- **Proper scoring rules**: Brier score (quadratic), log-loss (logarithmic) — metrics that strictly reward honest probability estimates

---

## The Confidence-Competence Gap

The paper's central warning for agentic financial systems:

> An LLM that is only slightly better than chance but consistently overconfident will, under typical bet-sizing rules, generate negative long-run growth.

**Why this matters under Kelly sizing**: If a model's true edge is 55% accuracy but it outputs 80% confidence on each trade, Kelly criterion instructs betting:

```
f* = (p - q) / odds
```

Where p=0.80 (model-stated) but true p=0.55. This causes systematic overbetting → capital ruin, even if the model's directional accuracy is positive.

**The compounding effect**: A model with 55% accuracy and perfect calibration will grow capital over 1000 trades. The same model with 80% stated confidence will be bankrupt in far fewer trades due to Kelly overcorrection.

---

## Calibration Concepts Applied to Trading

### Reliability Diagram
Plot predicted probability vs realized frequency across probability bins. A perfectly calibrated model lies on the 45-degree diagonal. Most neural networks are overconfident (curve above diagonal at high confidence).

### Expected Calibration Error (ECE)
```
ECE = Σ_B (|B|/n) × |accuracy(B) - confidence(B)|
```
Where B = probability buckets. Lower ECE = better calibrated. LLMs typically achieve ECE 0.10-0.25 on financial tasks (vs 0.02-0.05 for well-calibrated weather models).

### Calibration Methods
- **Temperature scaling**: T parameter divides logits before softmax — single-parameter post-hoc calibration
- **Isotonic regression**: non-parametric monotone mapping of raw scores to calibrated probabilities
- **Platt scaling**: sigmoid fit on validation set scores vs outcomes

---

## Implications for George's Production Pipeline

### H174 PEAD (FinBERT Score)
The FinBERT sentiment score (threshold 0.18 for H174) is a raw logit output, not a calibrated probability. Key questions FinBench raises:
1. **Is FinBERT overconfident on 8-K text?** — likely yes, as most FinNLP models are
2. **Does OOS WR degrade at marginal scores (0.18-0.25)?** — probable, as borderline scores are less reliable
3. **Calibration improvement path**: isotonic recalibration on H174's IS event history (WR by score decile)

**Proposed H174 enhancement**: Instead of binary threshold 0.18, use calibrated score → Kelly fraction for position sizing:
```
kelly_f = (calibrated_prob - 0.5) / (1 - calibrated_prob)  # simplified
position_size = max(0, min(kelly_f, 0.10)) × account_equity
```

### H185 Prediction Markets
Kalshi market prices are market-implied probabilities, already partially calibrated. But:
- LLM-derived probability adjustments (above or below market) need calibration before Kelly sizing
- PolyBench's finding (all LLMs negative return) may partly reflect calibration failure — models with directional edge but poor calibration that overbid on positions

### H426 FinDPO Scoring
FinDPO (DPO-aligned Llama-3-8B) produces softmax logprobs — better suited to calibration than FinBERT's classification head. FinBench's methodology should be applied to validate FinDPO scores before using them in Kelly sizing.

---

## MacroLens Connection

FinBench and MacroLens (arXiv:2606.24950) are complementary:
- **MacroLens**: tests which signal types (price/fundamental/macro/text) predict returns at all
- **FinBench**: tests whether models' confidence in those predictions is reliable enough for sizing

Both are needed for a complete evaluation framework. MacroLens tells you *if* there's a signal. FinBench tells you *how much* to size the trade.

---

## Practical Implementation

**Phase 1** (immediate): Apply isotonic calibration to H174 historical FinBERT scores vs realized WR:
1. Compute FinBERT score deciles across IS events
2. Fit isotonic regression: decile → realized WR in that decile
3. Use calibrated WR to set position size instead of equal-weight

**Phase 2**: Add FinBench-style time-gated Brier score tracking to H174 live paper trading log:
- Monthly: compute rolling Brier score on most recent 10 resolved events
- Alert if Brier score > 0.30 (indicating calibration degradation)

---

## Cross-References
- [LLM Alpha Validation Checklist](../trading/algorithms/llm-alpha-validation.md) — 6-test gate; FinBench calibration adds to Test 4 (Predictive Calibration)
- [PEAD — Post-Earnings Announcement Drift](../trading/algorithms/pead.md) — H174 production pipeline
- [DPO-Aligned LLMs for Financial Sentiment](../trading/tools/dpo-aligned-financial-nlp.md) — H426 FinDPO scorer
- [AI Model Benchmarks on Prediction Markets](../trading/prediction-markets/ai-model-benchmarks.md) — Kalshi/Polymarket calibration context
- [LLM Evaluation & Benchmarking for Finance 2026](llm-finance-benchmarks-2026.md) — broader benchmark landscape
- [Superforecasting Methods](../trading/prediction-markets/superforecasting-methods.md) — isotonic recalibration methods
- [QuantSightBench — Prediction-Interval Calibration for LLM Numeric Forecasting](quantsightbench-interval-calibration-2026.md) — complementary finding for continuous-quantity forecasts (prediction intervals) rather than categorical/classification confidence ← new 2026-08-04

---

## Research Lead: QuantSightBench — Prediction-Interval Calibration for Numeric Forecasts (Qin & Andriushchenko, arXiv:2604.15859, flagged 2026-08-04)

The FinBench finding above (confidence-competence gap, negative Kelly growth from overconfident-but-slightly-better-than-chance LLM outputs) is about **categorical/classification** confidence. QuantSightBench (Jeremy Qin & Maksym Andriushchenko, ELLIS Institute Tübingen / Max Planck Institute / Tübingen AI Center, submitted 2026-04, arXiv:2604.15859) tests the complementary case: can LLMs produce well-calibrated **prediction intervals for continuous numeric quantities**? 1,000 forecasting questions across 8 domains (business/finance, economics, public health, demographics, sports, science), evaluated under three settings — zero-shot, background-context prompt, and agentic (retrieval-augmented).

**Three evaluation axes**: (1) Calibration/Coverage — does the stated X% interval actually contain the true value X% of the time; (2) Sharpness (Mean Log Interval Score) — narrower is better *if* coverage holds; (3) Scale Awareness — does performance hold across magnitude ranges (fractional to 100K+).

**Headline result — systematic overconfidence, even in frontier models**: 11 models tested (GPT-5.4, GPT-5.1, Claude Opus 4.5, Claude Sonnet 4.5, Gemini 3.1 Pro, Grok 4, DeepSeek v3.2, GLM-4.7, Kimi). None hit the target 90% coverage at the 90% confidence level. Best performer Gemini 3.1 Pro reached only 79.1% coverage; Grok 4 76.4%; GPT-5.4 75.3% — all 10+ points short of nominal.

**Scale degradation is the sharpest finding**: in the 1–10 magnitude range, most models cleared 80% coverage; by the 100K+ range, most models fell **below 65% coverage**. Intervals get systematically too narrow exactly where the numbers get big — i.e. exactly where a trading application (large notional price targets, large-cap market-cap estimates, aggregate volume/flow forecasts) would be using them.

**Agentic/retrieval nuance**: open-weight models (DeepSeek, GLM, Kimi) showed larger calibration improvement from retrieval access than frontier models did — suggesting their gap is more about information access than reasoning quality, while frontier models' overconfidence is closer to an intrinsic calibration defect that more context doesn't fix as cleanly.

**Why this matters for George**: no hypothesis in the H-series has yet asked an LLM to directly output a numeric estimate with an uncertainty band (as opposed to a classification score like FinBERT's sentiment, or a binary/discrete signal). If any future proposal in the H279/H280/H281 queue (or a new one) leans on an LLM to produce, say, an expected-EPS-surprise magnitude or a volatility-forecast interval rather than a bounded [0,1] score, this paper is the first citation to check against — and its scale-degradation finding specifically warns against trusting LLM-generated intervals on large-magnitude numeric targets without independent calibration correction (e.g. conformal prediction wrapping, which neither this paper nor finbench-calibration-2026.md tests but which is the standard fix for exactly this failure mode).

**Not staged as a new hypothesis** — this is a capability-limitation finding relevant to future LLM-numeric-forecast proposals, not a signal to backtest today. Logged so any future numeric-interval LLM proposal starts from 'assume ~65-80% actual coverage on stated 90% intervals, worse at large magnitude' rather than discovering it the hard way.

## See Also

- [FinBench — Calibration and Uncertainty Benchmarking for Financial LLMs](#) (this page, above) — categorical/classification calibration counterpart
- [LLM Alpha Validation Checklist](../trading/algorithms/llm-alpha-validation.md)
- [The Base-Rate Trap in LLM Trading Signals](base-rate-trap-llm-trading-2026.md) — related honest-benchmark discipline for LLM forecasting claims
