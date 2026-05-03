# FinNLP 2025: Enhancing PEAD Measurement with LLMs — FinBERT + Early Price Signal

**Source:** ACL Anthology 2025.finnlp-2.13 — "Enhancing Post Earnings Announcement Drift Measurement with Large Language Models"
**Authors:** Samuel Hadlock, Jesse Roberts, Joohun Lee
**Published:** FinNLP Workshop, ACL 2025, Suzhou, China (November 2025), pages 197–209
**DOI:** 10.18653/v1/2025.finnlp-2.13
**Relevance:** R31 — text-based PEAD with FinBERT

---

## Key Findings

### Model Comparison: FinBERT vs BART

The paper benchmarks two LLM architectures for PEAD direction classification (positive drift vs negative drift):

| Model | Positive Group Accuracy | Negative Group Accuracy |
|-------|------------------------|------------------------|
| **FinBERT** (encoder-only) | **57.6%** | **58.3%** |
| BART (encoder-decoder) | lower | lower |

**Winner: FinBERT.** Financial domain pretraining makes FinBERT better at capturing PEAD-relevant narrative signals in earnings texts than a general-purpose encoder-decoder.

### The 3-Day Early Price Signal Enhancement

Key finding: incorporating the 3-day post-announcement cumulative return as an auxiliary input to the text model improves classification performance.

**Intuition:** The first 3 trading days after an earnings announcement partially reveals institutional interpretation of the call. If text score says "positive" AND the market has already moved up 2% in 3 days, the remaining drift is confirmed. If text says "positive" but market is down 1% in 3 days, the text signal may be reversed or institutional investors saw something the model missed.

**Practical implementation for R31:**
```python
# After computing FinBERT text surprise score:
confirmation_return = cumulative_return(stock, day_0, day_3)  # post-announcement

if finbert_score > threshold:  # positive text signal
    if confirmation_return > 0:
        signal_strength = "strong"  # text and market agree
        position_size = 1.0
    elif confirmation_return < -0.01:
        signal_strength = "weak"    # market disagrees with text
        position_size = 0.5         # reduce or skip
    else:
        signal_strength = "neutral"
        position_size = 0.75
```

---

## Validation of R31 FinBERT Approach

This paper directly validates the core R31 hypothesis:

1. FinBERT is the correct model for PEAD text scoring (beats BART/general LLMs)
2. Text-based PEAD generates actionable directional signals (57-58% accuracy)
3. The 3-day confirmation window adds additional predictive power

Combined with PEAD.txt findings (JFQA 2022): text signal generates 3.9 bps/day vs numeric SUE 2.6 bps/day — the FinNLP paper confirms this advantage persists with modern benchmarking.

---

## R31 Implementation Blueprint (Updated)

```
For each earnings event:
  1. Pull earnings call transcript (Q&A section + prepared remarks)
  2. Score with FinBERT (ProsusAI/finbert) → sentiment per segment
  3. Compute text_surprise = this_quarter_score - trailing_12Q_avg_score
  4. Wait 3 trading days post-announcement
  5. Compute confirmation_return = 3-day cumulative return
  6. Combine: adjusted_signal = text_surprise × confirmation_factor(confirmation_return)
  7. Enter position on day 3 close (not day 0!) — after confirmation window
  8. Hold 20-40 days per classic PEAD drift horizon
  9. Exit sentinel: FinBERT < -0.70 on subsequent news → exit immediately
```

**Note on day 3 entry:** Entering on day 3 (after confirmation) sacrifices the first 3 days of potential drift but substantially improves signal quality. The paper's finding suggests this tradeoff is favorable.
