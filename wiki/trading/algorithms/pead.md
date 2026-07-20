---
type: algorithm
title: Post-Earnings Announcement Drift (PEAD)
tags: pead, earnings, nlp, finbert, event-driven
added: 2026-07-18
updated: 2026-07-20
category: Algorithms
---

# Post-Earnings Announcement Drift (PEAD)

PEAD is the empirical finding that stocks drift in the direction of an earnings surprise for 20–60 days after the announcement. Discovered by Ball & Brown (1968); one of the most replicated and durable anomalies in finance. In its classic form, PEAD relies on quantitative EPS surprise. The modern NLP-driven version (H163/H174) uses FinBERT sentiment on 8-K filings as the primary gate, augmented by EPS surprise as a secondary filter.

**Related pages**: [Hypothesis Log](../backtesting/hypothesis-log.md) | [Event-Driven Strategies](event-driven.md) | [Short-Term Reversal](short-term-reversal.md) | [Alpha Illusion Checklist](llm-alpha-validation.md)

**Production status**: H174 CONFIRMED (FinBERT score ≥ 0.18 + EPS surprise ≥ 2%; OOS WR=81.8%, n=22, 20-day hold). Running live via `backtesting/paper_trading/pead_overnight.py` and `pead_gap_overnight.py` (PEAD-GAP variant).

---

## 1. Academic Foundation

### Seminal Papers

| Paper | Key Contribution |
|-------|-----------------|
| Ball & Brown (1968) | First documentation of post-announcement drift; market underreacts to earnings information |
| Foster, Olsen & Shevlin (1984) | Correlation between post-announcement abnormal returns and unexpected earnings persists years |
| Bernard & Thomas (1989/1990) | Mechanism identified: investors fail to recognize implications of current earnings for future earnings |
| Garfinkel, Hribar & Hsiao (2024) | 5.1% risk-adjusted return over three months (~20% annualized) in long/short portfolio |

### Mechanism: Why Does PEAD Persist?

**Investor underreaction** is the consensus explanation. Bernard & Thomas (1989) showed analysts and investors fail to fully update expectations — they anchor to prior-quarter results and underestimate earnings autocorrelation. This creates a predictable lag: after a positive surprise, forecasts converge upward gradually over 20–60 days, and price follows.

**Two-stage information release** (EarningsInOne, arXiv:2606.29734, Jun 2026) adds nuance:
- **Stage 1 (minutes)**: Quantitative EPS/revenue surprise arrives in press release; absorbed by algorithmic traders within minutes. The "number shock" is largely priced by market open.
- **Stage 2 (30–90 minutes later / day+1)**: Qualitative language in earnings conference call transcript (ECT) — management tone, guidance credibility, Q&A confidence — peaks on the *next* trading day. Human analysts read and revise forecasts overnight.

**Analyst behavioral bias** (Matera 2025, arXiv:2511.15214) explains why the ECT still generates drift:
- Analysts **over-react** to optimistic sentiment (revise forecasts up disproportionately)
- Analysts **under-react** to uncertainty/risk narratives (discount warnings and hedges)
- Six ECT narrative dimensions: Guidance, Jargon, Confidence, Macro-Perspective, Sentiment, Uncertainty

This creates a systematic forecast revision cascade that drives price adjustment over 20–60 days after earnings.

---

## 2. Standardized Unexpected Earnings (SUE) Signal

Classic PEAD uses the SUE metric:

```
SUE = (Actual EPS − Expected EPS) / σ(prior EPS surprises)
```

Stocks sorted into deciles by SUE; long top decile (positive surprise), short bottom decile. Returns:

| Hold Period | Cumulative Abnormal Return |
|-------------|--------------------------|
| Day 1–5 | ~1.5–2.0% of total drift |
| Day 1–20 | ~35–45% of total drift |
| Day 1–60 | Full drift (~5.1% for large-cap L/S) |
| Post day 60 | Drift reverses or flattens near next earnings |

**Why PEAD weakened in large caps (~2001–2010):** Decimalization and Reg NMS accelerated HFT absorption of quantitative surprise. Algo traders can fully price EPS beats within minutes. The *quantitative* component is largely gone for NASDAQ large-caps.

**Why NLP-based PEAD survives:** Text signals from 8-K filings and earnings call transcripts are harder for algorithms to process. Human under-reaction to qualitative language creates the remaining edge. H163/H174 confirmed this on our 30-stock universe.

---

## 3. Signal Taxonomy

| Signal Type | Source | Timing | Difficulty | H-Number |
|------------|--------|--------|-----------|----------|
| Raw EPS surprise | Press release | T+0 minutes | Easy | H173 (NOT CONFIRMED standalone) |
| FinBERT full 8-K | EDGAR 8-K filing | T+0 to T+2 hours | Medium | H163 CONFIRMED; H174 CONFIRMED |
| FinBERT section-weighted | Parsed 8-K sections | T+0 to T+2 hours | Medium | H414 (proposed) |
| ECT management tone | Earnings call transcript | T+30–90 min | Medium | H410 (staged) |
| Multi-modal (text+audio+slides) | Conference call materials | T+30–90 min | High | H415 (proposed) |
| SAE-FiRE sparse features | Financial documents | T+0 to T+2 hours | High | H400 (candidate) |
| Multi-task learning (MTL) | 8-K + analyst revisions | T+0 to T+5 days | High | H423 (staged) |

---

## 4. Confirmed Pipeline: H174

Signal: FinBERT sentiment score on full 8-K filing ≥ 0.18 AND EPS surprise ≥ 2%.
Universe: EDGAR 8-K filings for our 30-stock H198 universe (NASDAQ large-cap).
Hold: 20 trading days from announcement.
Entry: market open next day (gap ≥ 0% on day).

| Metric | Value |
|--------|-------|
| OOS Win Rate | 81.8% |
| OOS Mean Return | 6.89% |
| n (OOS events) | 22 |
| IS Win Rate | ~77% |
| Hold period | 20 trading days |
| Min event gate | n ≥ 20 for statistical validity |

**Why 20 trading days**: Captures ~40% of full 60-day drift on NASDAQ large-caps. Beyond 20 days, idiosyncratic variance grows while drift decays — Sharpe degrades. Also avoids holding through the next earnings announcement.

**Why 8-K over earnings transcript**: H168 tested conference call transcripts — OOS coverage only 26.5%, OOS WR=34.6% worse than baseline. Root cause: transcript availability bias skews OOS sample. Full 8-K filings are available for all events, ensuring consistent coverage.

**Why FinBERT over CLS embedding**: H172 (FinBERT CLS embedding) NOT CONFIRMED. The fine-tuned classification head (positive/negative/neutral probabilities) provides a cleaner signal than raw token embeddings.

---

## 5. Lessons from Failed Variants (H163–H179)

| Hypothesis | What Was Tested | Result | Lesson |
|-----------|----------------|--------|--------|
| H163 | FinBERT on full 8-K | CONFIRMED (baseline) | Full document FinBERT works; threshold ≥ 0.18 |
| H172 | FinBERT CLS embedding | NOT CONFIRMED | Probability head beats embedding |
| H173 | EPS surprise standalone | NOT CONFIRMED | Text signal dominates; surprise alone not enough |
| H174 | score ≥ 0.18 + surprise ≥ 2% | CONFIRMED (champion) | Combined filter best; OOS WR 81.8% |
| H175 | Item 2.02 text (not full 8-K) | NOT CONFIRMED | Full 8-K more discriminative than section alone |
| H168 | Speaker-weighted FinBERT on transcripts | NOT CONFIRMED | Transcript coverage bias (26.5% OOS); full 8-K wins |
| H317 | FinBERT + EPS + pre-momentum | NOT CONFIRMED | 77% of H174 events already have EPS beats; filter redundant |
| H179 | Global equity rotation (PEAD-adjacent) | NOT CONFIRMED | Country-level ETFs collapse cross-section |

**Core lessons:**
1. Full 8-K document beats section-level parsing (counterintuitive — context matters)
2. Text signal beats EPS surprise standalone for large-caps
3. Coverage consistency is critical — any filter that reduces n below 20 fails the gate
4. Don't compound filters: H317 showed each additional filter has diminishing returns

---

## 6. PEAD-GAP Variant (Live)

A parallel paper trading pipeline runs on the gap-up variant:

**Strategy**: On earnings dates (from overnight watchlist scan), identify stocks that gap up > 3% at the open. Enter at 9:32 AM market order. Hold 20 trading days. No FinBERT scoring required — the gap itself is the confirmation signal.

**Logic**: The open gap is a revealed preference signal. If informed traders are buying at open (pushing price 3%+ above prior close), it suggests the quantitative surprise component is strong enough to overcome pre-open trading. This is complementary to H174's text-based filter: H174 enters on quality NLP signal; PEAD-GAP enters on strong market reaction.

Files:
- Overnight scan: `backtesting/paper_trading/pead_gap_overnight.py` → `pead_gap_watchlist.json`
- Open execution: `backtesting/paper_trading/pead_gap_open.py`
- Exit logic: `backtesting/paper_trading/pead_gap_exits.py`

---

## 7. Upgrade Candidates

### H400 — SAE-FiRE Sparse Feature Selection (arXiv:2505.14420)

**Paper**: Zhang et al. (2025). "SAE-FiRE: Enhancing Earnings Surprise Predictions Through Sparse Autoencoder Feature Selection."

**Approach**: Sparse autoencoders decompose dense LLM representations into interpretable sparse components. ANOVA F-tests + tree-based importance scoring identify top-k discriminative dimensions. Filters noise in financial documents (5,000+ word 8-Ks) while preserving earnings-relevant features.

**Path**: Replace raw FinBERT probability with SAE-decomposed features → logistic classifier → score. Interpretable: can see *which* linguistic dimensions drive predictions (guidance confidence, uncertainty hedging, etc.).

**Gate**: OOS WR > 81.8% (H174 champion) with n ≥ 20.

---

### H410 — ECT Transcript Layer (arXiv:2606.29734, STAGED)

**Design**: After H174 open entry (~9:32 AM), run FinBERT on the earnings call transcript (ECT) as it posts at ~10-11 AM. If ECT management tone is negative despite a positive 8-K score, exit or reduce position.

**Expected improvement**: Filter 15-20% of H174 false positives. WR from 81.8% → ~85%+. The EarningsInOne paper shows ECT tone peaks at day+1, providing an exit/hold signal with additional information not in the 8-K.

**Status**: Staged proposal in `dream_cycle/staged/2026-07-17/`.

---

### H414 — Section-Weighted FinBERT (arXiv:2509.24254)

**Design**: Parse 8-K HTML to isolate management discussion, guidance, and results sections. Apply FinBERT separately to each section. Weight section scores by historical predictive power.

```python
SECTION_PATTERNS = {
    'guidance': ['outlook', 'guidance', 'expect', 'fiscal year'],
    'commentary': ['management', 'CEO', 'CFO', 'we believe', 'we expect'],
    'results': ['revenue', 'earnings per share', 'net income', 'EPS'],
}
```

**Expected improvement**: Section targeting reduces noise from boilerplate legalese that dominates full-document scoring.

**Gate**: OOS WR > 81.8%, n ≥ 20.

---

### H415 — Multi-Modal Announcement-Day Pre-Filter (arXiv:2605.25894)

**Design**: Use multi-modal model (fundamentals + FinBERT text + EPS surprise) to predict announcement-day direction. Only enter H174 drift trade if multi-modal model also predicts up. Expected: reduces n but increases WR above 81.8%.

**Risk**: n constraint. Each additional filter risks dropping below n=20 gate. Must test coverage before committing.

---

### H421 — 10-K Item 1A Pre-Filter (STAGED 2026-07-19)

**Design**: Before entering a PEAD trade, check the company's most recent 10-K Item 1A (Risk Factors) for warning language. High-risk language → skip the event. Hypothesis: companies with elevated Item 1A uncertainty language have worse PEAD follow-through.

**Source**: arXiv paper finding that 10-K Item 1A language predicts future earnings quality. Staged in `dream_cycle/staged/2026-07-20/`.

---

### H422 — FinBERT2 Model Upgrade

**Design**: Replace `ProsusAI/FinBERT` in `pead_overnight.py` with FinBERT2 (KDD 2025, ValueSimplex, 32B finance-specific tokens). FinBERT2 dominates across 681 financial NLP papers (2022-2025 meta-analysis); superior sentiment classification on earnings-domain text.

**Implementation**:
```python
# Current
from transformers import BertTokenizer, BertForSequenceClassification
model = BertForSequenceClassification.from_pretrained("ProsusAI/finbert")

# FinBERT2 upgrade (when available via HuggingFace)
# model = AutoModelForSequenceClassification.from_pretrained("valuesimplex/finbert2")
```

**Risk**: HIGH — modifies live trading script. Requires side-by-side IS comparison before replacing. Stage as medium-risk with .bak copy.

---

### H423 — Multi-Task Learning PEAD (SSRN:5284651)

**Design**: MTL framework treating PEAD prediction as primary task; analyst forecast revisions (obtained from FMP API) and institutional trading (13-F data) as auxiliary tasks. Shared encoder, multiple task heads. Learning signal from analyst update patterns teaches the model to anticipate the forecast revision cascade.

**Gate**: OOS WR > 81.8%, n ≥ 20.

---

## 8. Production Architecture

```
PEAD SYSTEM (Nightly → Open → Hold → Exit)

11 PM CT: pead_overnight.py
  ├── Fetch earnings calendar (FMP API) for tomorrow's events
  ├── For each ticker in H198 universe with earnings:
  │   ├── Pull latest 8-K from EDGAR
  │   ├── Score with ProsusAI/FinBERT
  │   ├── Check EPS surprise ≥ 2% (yfinance)
  │   └── Add to pead_watchlist.json if score ≥ 0.18 AND surprise ≥ 2%
  └── pead_overnight.py writes pead_watchlist.json

9:32 AM CT: pead_open.py
  ├── Read pead_watchlist.json
  ├── For each watchlist ticker: check gap ≥ 0% at open
  └── Submit BUY orders (Alpaca paper, market order, portfolio-sized)

2:46 PM CT: pead_exits.py
  ├── Read pead_positions.json (all open PEAD positions)
  ├── For each position: check hold_days ≥ 20 trading days
  └── Submit MOC SELL orders for aged positions

PARALLEL: PEAD-GAP variant
  11 PM CT: pead_gap_overnight.py → pead_gap_watchlist.json (no FinBERT)
  9:32 AM CT: pead_gap_open.py (gap ≥ 3% gate at open)
  2:46 PM CT: pead_gap_exits.py
```

**Shared dependencies**:
- `ProsusAI/FinBERT` (~400MB): cached after first run; ~90s load from disk
- `$EDGAR_USER_AGENT` env var (must be set): `your.email@example.com George-Agent`
- `$ALPACA_API_KEY` + `$ALPACA_SECRET`: via OneCLI proxy, `NO_PROXY=paper-api.alpaca.markets`
- `$FMP_API_KEY`: earnings calendar and EPS surprise data

---

## 9. Decay Timeline by Hold Period

| Hold Period | % of 60-Day Drift Captured | Sharpe Profile | Recommended For |
|------------|---------------------------|---------------|-----------------|
| 5 days | ~10–15% | Very volatile | High-frequency only |
| 20 days | ~35–45% | Best risk-adj (current H174) | Monthly-rebalance style |
| 30 days | ~55–65% | Good | Institutional-grade L/S |
| 60 days | ~100% | Longer runway, more variance | Full drift capture |
| > 60 days | Reverses or flattens | Negative | Avoid |

H174 uses 20-day hold — empirically optimal for our universe given the 20-event n-gate. The academic literature suggests 30–60 days captures more drift, but 20-day is cleaner for position rotation and avoids next-earnings-cycle reversal risk.

---

## 10. PEAD × Momentum Interaction

A key finding from the drift-regime research (arXiv:2511.12490): momentum strategies improve dramatically when restricted to stocks in positive drift cycles (>60% positive days in trailing window). This is the same gate as H411/H416's 20d drift filter.

**Implication**: PEAD and momentum are not independent:
- Strong momentum stocks (H198) during positive drift periods (H411 gate) are likely post-earnings uptrend stocks
- PEAD entries on these same stocks at earnings events may capture a *double signal* — momentum continuation + post-announcement drift
- H416's 5.342 OOS Sharpe on cheap stocks in uptrend may partially reflect the earnings catalyst mechanism

This suggests a confluence strategy: enter H174 PEAD on stocks that also satisfy H411's 20d drift gate (per-stock positive-day fraction > 0.60). Reduces n but may substantially improve WR.

---

## 11. Key References

| Paper | arXiv/SSRN | Key Finding |
|-------|-----------|------------|
| Ball & Brown (1968) | — | First PEAD documentation |
| Bernard & Thomas (1989/1990) | — | Analyst underreaction mechanism |
| Garfinkel, Hribar & Hsiao (2024) | — | 5.1% risk-adjusted return, 3-month L/S |
| Wu et al. (2025) | arXiv:2509.24254 | Section-weighted FinBERT on press releases |
| Matera (2025) | arXiv:2511.15214 | Analyst bias: over-react sentiment, under-react uncertainty |
| Zhang et al. (2025) | arXiv:2505.14420 | SAE-FiRE sparse feature selection for earnings NLP |
| EarningsInOne (2026) | arXiv:2606.29734 | Two-stage release: EPS minutes, ECT peaks day+1 |
| FinCall-Surprise (2025) | arXiv:2510.03965 | Multi-modal earnings dataset (2,688 calls, audio+slides) |
| PEAD MTL (2025) | SSRN:5284651 | Multi-task learning with analyst revision auxiliary task |
| Drift-Regime Gate (2025) | arXiv:2511.12490 | 13-Sharpe via drift-regime × value+reversal; validates H411 |

---

## 12. Data Sources

| Data | Source | Cost |
|------|--------|------|
| 8-K filings | EDGAR ATOM feed + EDGAR full-text search | Free |
| EPS surprise | FMP API (`$FMP_API_KEY`) | Freemium |
| Earnings calendar | FMP API | Freemium |
| Earnings call transcripts | FMP Transcripts (Professional plan, $299/mo) or EDGAR if in exhibit | Paid |
| FinBERT model | HuggingFace `ProsusAI/finbert` | Free |
| Historical PEAD events | `backtesting/paper_trading/pead_watchlist.json` (current session) | Internal |
