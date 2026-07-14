---
title: "Inside the Unfair Judge: A Mechanistic Interpretability Account of LLM-as-Judge Bias"
added: 2026-07-13
updated: 2026-07-13
category: AI / evaluation / interpretability
arxiv: "2607.11871"
url: https://arxiv.org/abs/2607.11871
authors: Zixiang Xu, Sixian Li, Huaxing Liu, Xiang Wang, Shuai Li, Zirui Song, Xiuying Chen (2026)
---

# Inside the Unfair Judge — LLM-as-Judge Bias (Mechanistic Account)

**What it is:** A mechanistic interpretability study of scoring bias in LLM-as-judge systems. Rather than measuring bias as input-output noise, this paper locates it in the judge's activation geometry — enabling both causal control and operational prediction. Published July 13, 2026.

## The Problem with Existing Bias Studies

Prior work on LLM-as-judge bias operates at the **input-output level**: perturb the prompt (add formatting, change candidate order, alter verbosity), measure the score delta, propose a prompt mitigation. This works but is post-hoc and reactive.

This paper reframes bias as a **representation-level phenomenon** in the judge's hidden states.

## Three Key Findings

**1. Geometry — Bias Lives in a Low-Dimensional Subspace**
- Clean (unbiased) judging inputs occupy a tight activation manifold in the judge's hidden space
- Biased inputs are displaced from this manifold along a **low-dimensional, type-specific subspace** — different bias types occupy different directions
- The displacement sharpens with model depth (later layers are more discriminative)
- Three families of estimators (linear probe, PCA, ICA) all recover the same subspace consistently

**2. Causal Control — Steering Activations Steers Scores**
- Steering hidden states *along* the bias subspace drives scoring in both directions:
  - Forward shift: reproduces biased scoring on clean inputs
  - Reverse shift: restores baseline scoring on biased inputs
- Random directions of matched norm produce shifts ~10× smaller → the bias subspace is causal, not merely correlated
- Validated across 7 judge models, 7 bias types, 9 benchmarks

**3. Operational — Predicts Judge Failures Before Scoring**
- A linear projection onto the bias-direction features can **anticipate judge failures** on entirely unseen benchmarks
- Substantially outperforms text-based alternatives for failure prediction
- Practical: lets you flag likely-biased evaluations before accepting scores

## Bias Types Studied

Seven bias types tested: position bias (preferred option order), verbosity bias, formatting bias (markdown), sycophancy (flattery), self-enhancement bias, authority bias, and bandwagon bias.

Each has a distinct direction in activation space — suggesting bias is not a single global contaminant but a structured set of named directions.

## Why This Matters for George's Workflow

**Dream cycle evaluation:** When using LLM to evaluate proposed hypotheses, the judge model is subject to these biases. Position of a hypothesis in the context window, length of description, and formatting all affect scores in ways unrelated to quality.

**H381/H382 multi-agent trading:** Bull/bear "debate" architectures that use a judge model to resolve disputes are subject to position bias (first vs. second argument) and verbosity bias (longer argument wins).

**Practical mitigations enabled by this work:**
- Run a bias probe on the judge's activations before accepting evaluations
- Double-evaluate with swapped positions (catches position bias geometrically, not just empirically)
- Use the activation-level predictor to flag uncertain evaluations for human review

## Project Resources

- Project page: https://xzx34.github.io/unfair-judge/
- 7 judges × 7 bias types × 9 benchmarks = reproducible evaluation suite

## Cross-References

- [LLM Metacognition (arXiv:2607.11881)](llm-metacognition-2026.md) — related: calibration and bias are complementary failure modes
- [LLM Evaluation & Benchmarking for Finance](../ai-industry/llm-finance-benchmarks-2026.md) — benchmark design implications
- [Multi-Agent LLM Trading](../trading/algorithms/multi-agent-llm-trading.md) — H274/H381 bull/bear debate architectures are subject to these biases
- [LLM Alpha Validation Checklist](../trading/algorithms/llm-alpha-validation.md) — add bias probe to LLM-judge validation step
