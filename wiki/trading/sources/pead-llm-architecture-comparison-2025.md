---
created: 2026-08-01
updated: 2026-08-01
type: source_summary
authors: Samuel Hadlock, Jesse Roberts, Joohun Lee (Tennessee Tech University)
published: 2025 (EMNLP-2025, FinNLP workshop)
source: Proceedings of the 10th Workshop on Financial Technology and Natural Language (FinNLP), EMNLP-2025, Suzhou, China
url: https://aclanthology.org/2025.finnlp-2.13.pdf
---

# Enhancing Post Earnings Announcement Drift Measurement with Large Language Models — Hadlock, Roberts & Lee 2025

**Authors:** Samuel Hadlock, Jesse Roberts, Joohun Lee (Tennessee Tech University)
**Venue:** FinNLP Workshop, EMNLP-2025, Suzhou, China

Compares three transformer architectures — BART, FinBERT, LLaMA-3.2-3B (LoRA + 8-bit) — for predicting PEAD from **MD&A sections of 10-Q filings** (not 8-Ks, unlike our own H163/H174 pipeline). Also tests prepending a plain-English 3-day return sentence to the text as an early-signal feature.

---

## What the Paper Studies

- **Universe:** 2,628 unique NYSE companies, 2010–2024
- **Text source:** MD&A section of the quarterly 10-Q filing (via SEC EDGAR) — **this is the key methodological difference from our pipeline**, which scores 8-K Item 2.02 press-release text
- **Split:** train 2010–2020 (10,000 examples), test 2021–2024 (4,000 examples); same companies can appear in both periods but no overlapping quarterly observations
- **Labeling:** firms bucketed into Earnings Beat / Earnings Miss vs analyst consensus, modeled separately. Label=1 (Drift) = abnormal return in the expected direction over the 60-day post-announcement window; Label=0 (No Drift) = absent/contradictory abnormal return
- **Models compared:**
  - **BART** — encoder-decoder denoising autoencoder (Lewis et al. 2019/2020)
  - **FinBERT** — domain-adapted encoder-only BERT (Yang et al. 2020) — same family as our production H163/H174 model
  - **LLaMA-3.2-3B** — LoRA fine-tuned, 8-bit quantized (Meta 2024)

---

## Key Results

### Classification Accuracy (Table 1)

| Model | Positive Group Acc. | Negative Group Acc. |
|---|---|---|
| BART | 55.2% | 54.8% |
| **FinBERT** | **57.6%** | **58.3%** |
| LLaMA 3 | 56.3% | 56.2% |

FinBERT wins on raw classification accuracy — consistent with why we chose it for H163/H174.

### Top-10% Portfolio 60-Day BHAR (Table 2)

| Model | Positive Group Ret ± SD | Negative Group Ret ± SD |
|---|---|---|
| **BART** | **3.29% ± 2.25** | **-3.18% ± 3.42** |
| FinBERT | 2.83% ± 1.25 | -2.39% ± 1.97 |
| LLaMA 3 | 1.56% ± 1.33 | -2.83% ± 1.10 |

BART wins on raw drift magnitude / trading returns, despite lower accuracy — it produces fewer but more extreme correct calls.

**Risk-adjusted (Coefficient of Variation = SD/mean):** FinBERT is best (CV=0.44 positive, 0.82 negative); BART moderate (0.68 / 0.93); LLaMA 3 worst on the positive side (0.85 / 0.39).

### Statistical Significance — the Critical Caveat

- **Stock-level** t-tests (N=203 positive, N=187 negative): BART's drift magnitude significantly exceeds FinBERT's (positive: t=2.31, p=0.022; negative: t=-2.18, p=0.031); FinBERT significantly exceeds LLaMA 3 (positive: t=3.42, p<0.001; negative: t=-2.87, p=0.005).
- **Portfolio/quarterly-level** (only **N=16 quarters**): paired Wilcoxon signed-rank tests found BART's outperformance over FinBERT (3.29% vs 2.83%) **NOT significant** (p=0.202, z=0.88 positive; p=0.26, z=1.13 negative). The authors explicitly flag: "portfolio-level implementation requires further research for statistical detectability."

This is the same pattern this wiki has flagged before with outsized headline results (e.g. arXiv:2511.12490's implausible Sharpe 13+) — stock-level significance does not automatically survive at the small-N portfolio level. Treat the BART-vs-FinBERT architecture ranking as suggestive, not confirmed.

---

## Hypothesis 2: 3-Day Early-Signal Text Injection

The paper's most robust finding. Each MD&A text sample is prepended with a single standardized sentence:

```
"The three-day stock return for this period was X.XX%."
```

— the cumulative return from market open Day 1 through close Day 3 post-announcement, deliberately **non-overlapping** with the days-4-to-60 PEAD measurement window (no look-ahead into the label). Models are retrained on the identical 2010–2020 / 2021–2024 split with only this text-injection change.

**Results — all statistically significant (p<0.05), both accuracy (paired t-test) and returns (Wilcoxon signed-rank):**

| Model | Δ Accuracy (pos/neg) | Δ BHAR (pos/neg) |
|---|---|---|
| BART | +0.9% / +0.8% | 3.29%→3.91% (+0.62) / -3.18%→-3.70% (-0.52, more negative = stronger drift) |
| FinBERT | +0.3% / +0.1% | 2.83%→3.12% (+0.29) / -2.39%→-2.64% (-0.25) |
| LLaMA 3 | +0.7% / +0.6% | 1.56%→1.69% (+0.13) / -2.83%→-3.05% (-0.22) |

Unlike the architecture comparison, this improvement holds up statistically at both levels. The authors describe the gains as "incremental" but robust.

### Illustrative Python — text injection into a FinBERT-style scoring pipeline

```python
def build_signal_text(mdna_text: str, three_day_return_pct: float) -> str:
    """Prepend a plain-English 3-day return sentence ahead of the narrative text,
    per Hadlock/Roberts/Lee 2025 Hypothesis 2. Keep this window (Day 1 open -> Day 3
    close) strictly separate from the drift measurement window (Day 4-60) to avoid
    leaking the label into the feature.
    """
    sentence = f"The three-day stock return for this period was {three_day_return_pct:.2f}%."
    return f"{sentence} {mdna_text}"

# score = finbert_pipeline(build_signal_text(mdna_text, three_day_ret))["score"]
```

---

## Critical Limitation: MD&A/10-Q Filing Lag vs Earnings Announcement

The paper's Appendix B discloses an empirical filing-lag distribution the model treats as simultaneous with the earnings release despite it not being so:

| Lag from earnings release to 10-Q filing | % of firms |
|---|---|
| 0–2 days | 50.5% |
| 3–7 days | 15.0% |
| 8–15 days | 15.8% |
| 16–30 days | 11.4% |
| >31 days | 7.3% |

**49.5% of firms file their 10-Q more than 2 days after the earnings announcement.** The paper's own model assumes same-day availability for training purposes — a self-acknowledged methodological weakness. This is a look-ahead-adjacent risk specific to any MD&A/10-Q-based signal: in live trading, the text simply isn't available yet for half the universe when the earnings surprise is known. The authors recommend restricting to same-day filers or explicitly modeling the lag as a feature.

Other disclosed limitations: no transaction costs/spreads/market impact modeled; only MD&A text is used (not earnings calls, press releases, or social media); accuracy gains are "incremental."

---

## Relevance to Our Pipeline

Nothing currently in the wiki compares BART vs FinBERT vs LLaMA-3 architecture choice, or evaluates MD&A/10-Q as an alternative text source to 8-K Item 2.02 (our current H163/H174/H175 approach). Three actionable angles:

1. **Architecture choice is a live, unresolved question** for text-driven PEAD scoring — FinBERT (our current choice) wins on accuracy and risk-adjusted return; BART wins on raw magnitude but the edge is not significant at portfolio level (N=16 quarters). Not compelling enough on its own to justify replacing FinBERT in H174.
2. **3-day-return text injection is a simple, directly implementable technique** that differs meaningfully from H317's failed approach. H317 (NOT CONFIRMED) added EPS surprise + pre-momentum as **hard filter thresholds**, which cut N below the 20-event gate. This paper's technique instead **injects the return as continuous text context** ahead of FinBERT scoring rather than filtering on it — it doesn't reduce N, just enriches the input. This is a genuinely different implementation path worth a dedicated hypothesis test on our own 8-K corpus.
3. **10-Q/MD&A filing-lag distribution (49.5% >2-day lag)** is a caveat to remember if a future hypothesis ever explores 10-Q text as a signal source instead of/alongside 8-Ks — don't assume same-day availability.

**Proposed hypothesis (staged in dream cycle, see research-log):** test 3-day-return text injection on our existing FinBERT + 8-K Item 2.02 pipeline (H174's dual filter: score≥0.18 AND surprise≥0.02), retaining the current filter thresholds unchanged and only modifying the FinBERT input text — measure whether score distribution/WR/n changes vs the H174 baseline (WR=81.8%, n=22).

---

## Cross-References

- [PEAD Strategies](../algorithms/pead.md) — H163/H174/H175 FinBERT-on-8-K production pipeline
- [Event-Driven Strategies](../algorithms/event-driven.md)
- [SEC EDGAR XBRL Fundamentals](../data-sources/edgar-fundamentals.md) — 10-Q/8-K filing data source
- Hypothesis log: H163 CONFIRMED, H174 CONFIRMED, H175 NOT CONFIRMED, H317 NOT CONFIRMED (multi-modal PEAD — hard filters reduced n below gate), H481 (staged two-stage PEAD, evaluated 2026-07-31)
