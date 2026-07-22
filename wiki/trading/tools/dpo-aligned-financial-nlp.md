---
title: DPO-Aligned LLMs for Financial Sentiment and PEAD Scoring
added: 2026-07-22
updated: 2026-07-22
category: tools
source: arXiv:2507.18417 (Iacovides, Zhou & Mandic, Jul 2025) — FinDPO
related_hypotheses: H426
---

# DPO-Aligned LLMs for Financial Sentiment and PEAD Scoring

## Overview

**Direct Preference Optimization (DPO)** is a post-training alignment technique that replaces RLHF with a stable offline optimization: instead of a separate reward model + PPO loop, DPO trains a causal LLM directly on *pairs* of preferred vs rejected responses using a binary cross-entropy objective.

**FinDPO** (arXiv:2507.18417, Iacovides, Zhou & Mandic, Imperial College London, Jul 2025) applies DPO to financial sentiment analysis, producing the first DPO-aligned causal LLM for algorithmic trading. This is a direct upgrade path for the H174 PEAD pipeline's FinBERT scorer.

---

## Why DPO Over SFT (Supervised Fine-Tuning)

The current H174 pipeline uses **FinBERT** (ProsusAI/finbert), a BERT-class model fine-tuned with supervised cross-entropy (SFT) on financial text. SFT limitations:

| Problem | Mechanism | Consequence for PEAD |
|---------|-----------|---------------------|
| Memorization | SFT can copy training distribution too closely | Scores novel earnings language from unseen sectors poorly |
| Discrete labels only | SFT predicts {positive, neutral, negative} class | Score threshold (≥ 0.18) requires probability calibration |
| No preference signal | SFT treats all errors equally | Can't express "positive/negative > neutral" ordering |
| BERT architecture limit | Sequence length ≤ 512 tokens | Truncates long 8-K press releases |

**DPO advantages:**
- Trains directly on *preferences* (output A is better than B), not absolute labels
- Better OOD generalization: preference pairs encode relative ordering, not memorized absolutes
- Causal LLM base (Llama-3-8B): handles longer contexts (8k+ tokens)
- Continuous probability score via softmax calibration of logprobs

---

## FinDPO Architecture

### Base Model
- **Llama-3-8B Instruct** (Meta, 8B params)
- Requires GPU for training; CPU inference possible via `llama.cpp` 4-bit quantization

### Training Data
- Financial news sentiment pairs from public datasets:
  - **FinSentiment** (ProsusAI): ~4,840 labeled financial sentences
  - **Financial PhraseBank** (Malo et al. 2014): 4,845 phrases, 3-class labels
- Preference pairs constructed: (positive_sentiment_text, negative_sentiment_text) → DPO training signal

### Scoring Pipeline
```
8-K text → Llama-3-8B (DPO-aligned) → discrete {positive, neutral, negative}
         → softmax calibration layer → continuous score [0, 1]
         → PEAD entry threshold (score ≥ 0.18 retained from H174)
```

### Reported Performance
- Long-short portfolio built from FinDPO continuous scores outperforms FinBERT-based long-short on:
  - Sharpe ratio improvement over FinBERT baseline
  - Better OOD generalization on unseen financial domains
  - Lower false-positive rate on neutral/ambiguous earnings releases

---

## Integration into H174 PEAD Pipeline

The H174 pipeline structure (`pead_overnight.py`) is modular:

```python
# Current FinBERT scorer call (in pead_overnight.py)
from transformers import pipeline
nlp = pipeline('sentiment-analysis', model='ProsusAI/finbert')
result = nlp(text[:512])[0]
score = result['score'] if result['label'] == 'positive' else 0

# FinDPO drop-in replacement (H426 design)
# Phase 1 (zero-shot GPT-4o-mini DPO-style proxy):
import openai
client = openai.OpenAI()
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[{'role': 'user', 'content': PEAD_SCORING_PROMPT.format(text=text[:4000])}],
    response_format={'type': 'json_object'}
)
score = json.loads(response.choices[0].message.content)['score']

# Phase 2 (local FinDPO model — requires GPU):
# from transformers import AutoModelForCausalLM, AutoTokenizer
# model = AutoModelForCausalLM.from_pretrained('iacovides/FinDPO-llama-3-8b')
```

**Three-phase upgrade path:**
1. **Phase 1 (now)**: GPT-4o-mini with DPO-style preference framing prompt — tests concept using available API, zero GPU cost (~$0.001/event)
2. **Phase 2 (medium-term)**: FinDPO checkpoint released publicly; deploy via llama.cpp quantized (no GPU needed for inference)
3. **Phase 3 (long-term)**: Fine-tune FinDPO on H174 confirmed event pairs (positive drift events as preferred, failed entries as rejected) — domain-specific DPO for PEAD

---

## Comparison: FinBERT vs FinDPO vs GPT-4o-mini

| Property | FinBERT | FinDPO (Llama-3-8B) | GPT-4o-mini proxy |
|----------|---------|---------------------|-------------------|
| Model size | 110M params | 8B params | ~8B (API) |
| Context length | 512 tokens | 8,192 tokens | 128k tokens |
| Training method | SFT | DPO preference alignment | RLHF (proprietary) |
| Score output | Softmax probability | Calibrated continuous [0,1] | JSON structured |
| Cost per event | $0 (local) | $0 (local, GPU) | ~$0.001 (API) |
| OOD performance | Good (financial domain) | Better (DPO generalization) | Strong (SOTA LLM) |
| Look-ahead risk | None | None | None |
| H174 integration | CURRENT | H426 target | H426 Phase 1 |

---

## 8-K Taxonomy Filter (arXiv:2607.08346) — Complementary Approach

Dolphin et al. (arXiv:2607.08346, Jul 2026) take a different angle: instead of improving the sentiment scorer, they classify 8-K events into a 3-tier 119-event-type taxonomy and achieve 96% precision at high quality scores. 

These two approaches are complementary:
- **FinDPO** improves the *scoring* quality (continuous calibrated drift probability)
- **8-K Taxonomy** improves *event selection* (filter to PEAD-relevant event types)

**H427** tests the taxonomy filter independently. A combined pipeline would:
1. Classify 8-K into event taxonomy (H427) → exclude noise events
2. Score remaining events with FinDPO (H426) → continuous drift probability
3. Apply thresholds: taxonomy filter AND score ≥ threshold AND EPS surprise ≥ 0.02

---

## Related Approaches Tested in the H-Series

| Hypothesis | Method | Status |
|-----------|--------|--------|
| H163 | FinBERT SFT on 8-K (baseline) | CONFIRMED (WR 80.8%) |
| H174 | FinBERT + EPS surprise dual filter | CONFIRMED (WR 81.8%, n=22) — DEPLOYED |
| H317 | FinBERT + EPS surprise + pre-momentum | NOT CONFIRMED (n too low) |
| H348 | GPT-4o-mini ensemble + FinBERT | PROPOSED |
| H350 | LM uncertainty anti-filter | SOFT CONFIRM (p67 n=19) |
| H372 | Structure-aware section-weighted FinBERT | STUB |
| H375 | Fine-tuned Mistral 7B PEAD predictor | STUB |
| H422 | FinBERT2 upgrade (ModernFinBERT) | STUB |
| H426 | FinDPO DPO-aligned Llama-3-8B | STAGED (2026-07-22) |
| H427 | 8-K Event Taxonomy filter | STAGED (2026-07-22) |

**Key design constraint for all NLP upgrades**: gate is OOS WR > 81.8% AND n ≥ 15. Any filtering approach that reduces n below 15 fails, even with improved WR. This was the H317 failure mode.

---

## DPO for PEAD: Practical Prompt Design

The GPT-4o-mini proxy implements DPO preference framing without training:

```python
PEAD_SCORING_PROMPT = \"\"\"
You are evaluating the post-earnings announcement drift (PEAD) potential of this
earnings press release. Rate the probability that this stock will drift upward
over the next 20 trading days on a scale of 0.0 to 1.0.

Consider POSITIVELY:
- EPS beat vs analyst consensus (quantified)
- Revenue growth acceleration
- Raised full-year guidance
- Margin expansion commentary
- Strong demand signals in management tone

Consider NEGATIVELY (lower score):
- EPS miss or in-line surprise
- Revenue shortfall
- Guidance cut or withdrawn
- Margin compression concerns
- Weak demand language

Return JSON: {{\"score\": <float 0-1>, \"key_signal\": <one phrase>, \"rationale\": <one sentence>}}

PRESS RELEASE:
{text}
\"\"\"
```

The structured JSON output allows direct comparison with FinBERT scores on historical H174 events (H426 backtest).

---

## Related Pages

- [NLP & Alternative Data](nlp-alternative-data.md) — FinBERT, EDGAR pipeline, H163/H174 tooling
- [PEAD — Post-Earnings Announcement Drift](../algorithms/pead.md) — full pipeline reference
- [Event-Driven Strategies](../algorithms/event-driven.md) — H163/H174 context
- [Machine Learning for Trading](ml-for-trading.md) — ModernFinBERT, LightGBM, score calibration
- [LLM Alpha Validation Checklist](../algorithms/llm-alpha-validation.md) — validation protocol for H426
