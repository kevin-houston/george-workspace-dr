---
type: algorithm
title: Post-Earnings Announcement Drift (PEAD)
tags: pead, earnings, nlp, finbert, event-driven
added: 2026-07-18
category: Algorithms
---

# Post-Earnings Announcement Drift (PEAD)

PEAD is the empirical finding that stocks drift in the direction of an earnings surprise for 20–60 days after the announcement. Discovered by Ball & Brown (1968); survives after risk-adjustment and remains one of the most robust anomalies.

**Related pages**: [Hypothesis Log](../backtesting/hypothesis-log.md) | [Backtesting Index](../backtesting/) | [Short-Term Reversal](short-term-reversal.md)

**Production status**: H174 CONFIRMED (FinBERT score ≥ 0.18 + EPS surprise ≥ 2%; OOS WR=81.8%, n=22, 20-day hold). Running live via `backtesting/paper_trading/pead_overnight.py`.

---

## Confirmed Pipeline (H174)

Signal: FinBERT sentiment score on full 8-K filing ≥ 0.18 AND EPS surprise ≥ 2%.
Universe: EDGAR 8-K filings for our 30-stock H198 universe.
Hold: 20 trading days from announcement.
Entry: market open next day (gap ≥ 0% on day; H175-GAP variant requires gap ≥ 3%).

| Metric | Value |
|--------|-------|
| OOS Win Rate | 81.8% |
| OOS Mean Return | 6.89% |
| n (OOS events) | 22 |
| IS Win Rate | ~77% |
| Hold period | 20 trading days |

---

## Structured Press Release Parsing (Wu et al. 2025)

**Paper**: Wu, Y., Akin, M., Martineau, C., Grégoire, V. & Veneris, A. (2025). 'Extracting the Structure of Press Releases for Predicting Earnings Announcement Returns.' ACM AI in Finance. arXiv:2509.24254. [[arXiv]](https://arxiv.org/abs/2509.24254)

**Key finding**: Analyzing 138,000+ press releases (2005–2023): FinBERT applied to *specific sections* of earnings press releases (revenue table, management commentary, guidance paragraph) outperforms full-document embedding. Soft text information is as predictive as hard EPS surprise data.

**H174 upgrade path**: Our confirmed pipeline (H174 OOS WR=81.8%) uses full 8-K FinBERT score ≥ 0.18. Potential improvement:
1. Parse 8-K HTML to isolate management discussion and guidance sections
2. Apply FinBERT separately to each section
3. Weight section scores by historical predictive power
4. Use composite score as gating threshold instead of raw full-doc score

```python
# Structural section parser for 8-K press releases
SECTION_PATTERNS = {
    'guidance': ['outlook', 'guidance', 'expect', 'fiscal year'],
    'commentary': ['management', 'CEO', 'CFO', 'we believe', 'we expect'],
    'results': ['revenue', 'earnings per share', 'net income', 'EPS'],
}

def extract_sections(text: str) -> dict:
    """Extract key sections from earnings press release text."""
    paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 50]
    sections = {k: [] for k in SECTION_PATTERNS}
    for para in paragraphs:
        para_lower = para.lower()
        for section, keywords in SECTION_PATTERNS.items():
            if any(kw in para_lower for kw in keywords):
                sections[section].append(para)
    return {k: ' '.join(v) for k, v in sections.items()}
```

**Proposed next step**: H414 — apply section-weighted FinBERT to H174 8-K corpus, confirm OOS WR > 81.8% gate with same n≥20 requirement.

---

## Multi-Modal Earnings Day Prediction (arXiv:2605.25894, May 2026)

**Paper**: 'Predicting Stock Price Direction on Earnings Announcement Days using Multi-modal Deep Learning.' arXiv:2605.25894. [[arXiv]](https://arxiv.org/abs/2605.25894)

**Approach**: Fuses price-volume features, EPS surprise, and FinBERT text scores in a single deep learning model to predict binary up/down direction on the announcement day itself (not post-announcement drift).

| Modality | Accuracy |
|----------|----------|
| Price-volume only | ~53% |
| EPS surprise only | ~58% |
| FinBERT text only | ~61% |
| Multi-modal fusion | ~65% |

**H415 candidate**: Use multi-modal announcement-day prediction as a pre-filter for H174 PEAD entries. Only enter drift trade if multi-modal model also predicts up-direction on announcement day. Expected: reduces n but improves WR above 81.8% current H174 gate. Design constraint: must maintain n≥20 OOS to be statistically valid.
