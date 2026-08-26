---
type: algorithm
title: Post-Earnings Announcement Drift (PEAD)
tags: pead, earnings, nlp, finbert, event-driven
added: 2026-07-18
updated: 2026-08-05
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

---

## Research Lead: Fine-Grained 8-K Event Taxonomy (arXiv:2607.08346, flagged 2026-08-01)

Dolphin et al. (Jul 2026) build a two-stage LLM pipeline classifying 8-K disclosures into a 119-event, 3-tier taxonomy, grounding every tag to a verbatim quote from the filing plus a quality-scored re-check pass. Applied to 292,984 filings (2022-2026) -> 601,088 tagged events. On a 5,125-filing stratified sample, precision on the extracted event tags rose from 12% (low quality-score bucket) to 96% (high quality-score bucket) as the quality filter tightened; unsupported tags fell to near-zero at the high end. Their event-study on abnormal returns shows the fine-grained taxonomy separates economically distinct events that the SEC's coarse Item-code buckets (e.g. our own Item 2.02) conflate.

**Why it matters here**: H163/H174's FinBERT score>=0.18 filter treats all Item 2.02 earnings-release text as one bucket. If distinct sub-event types within that bucket (e.g. guidance revision vs. one-time charge vs. restructuring commentary bundled into the same earnings release) have different drift magnitudes, an event-type-conditioned filter could sharpen H174 without changing its entry threshold. No ready-to-use package exists for their taxonomy -- this would require reimplementing a comparable classification+grounding pipeline before it becomes testable. Flagging as a design lead, not a confirmed improvement.

**Action needed before staging a hypothesis**: read the full paper's taxonomy definitions (which of the 119 event types map onto our Item 2.02 earnings-release corpus) and estimate the LLM-call cost of classifying our existing 8-K corpus before committing to a build.
---

## Research Lead: Structured Extraction Beyond Sentiment (arXiv:2607.28496, flagged 2026-08-01)

Zhu et al. (Jul 2026) extract 6 structured dimensions beyond sentiment (event type, impact scope, temporal horizon, semantic confidence, etc.) from financial news via LLaMA-3.1-70B, tested on 41,618 news-stock pairs (FNSPID dataset). Verified results: FinBERT-alone F1=0.576; FinBERT + structured features -> F1=0.600 (p<0.0001); structural dimensions alone contribute +0.019 F1 in ablation; **53.5% disagreement rate** between the sentiment signal and the structured signal, meaning the two are largely orthogonal rather than redundant.

**Why it matters here**: this is concrete, verified evidence (not just an abstract claim) that a FinBERT sentiment score used alone leaves real signal on the table. H174's current gate is score>=0.18 AND EPS surprise>=0.02 -- a sentiment dimension plus a fundamental-surprise dimension, but no *event-structure* dimension (impact scope, temporal horizon). Adding a structured-extraction second filter alongside the existing FinBERT score, in the spirit of this paper, is a candidate refinement distinct from the fine-grained-taxonomy lead (arXiv:2607.08346) filed the same night -- that one reclassifies event *type*, this one adds orthogonal structured *dimensions* on top of any event type.

**Caveat**: source domain is financial news, not 8-K filings -- our corpus and event-timing characteristics differ, so the F1 deltas here should be read as directional evidence for the general "sentiment alone is incomplete" claim, not as a number transferable to our own pipeline.
---

## Research Lead: Retail Investor Horizon as an Orthogonal PEAD Overlay (arXiv:2512.00280, flagged 2026-08-01)

Vamossy (Nov 2025, rev. Dec 2025) splits retail investors into long- vs. short-horizon cohorts using StockTwits self-reported holding periods (2010-2021). Long-horizon investors underreact to earnings news -> strong PEAD; short-horizon investors overreact then mean-revert. Verified alpha from the abstract: a long-short portfolio (stocks favored by long-horizon investors minus stocks favored by short-horizon investors) earns **0.43%/month (~5.16% annualized)**.

**Why it matters here**: this signal is investor-composition-based, not text- or fundamentals-based -- structurally orthogonal to H174's FinBERT-score + EPS-surprise gate. It could plausibly serve as a *third* independent filter dimension (alongside sentiment and surprise) rather than a competing PEAD mechanism, similar in spirit to how H418's drift gate is orthogonal to value in the momentum family.

**Blocker before this becomes testable**: we do not currently ingest StockTwits holding-period/investor-composition data. Would need to confirm API access and historical coverage before designing a hypothesis (working title: H-TBD retail-horizon PEAD overlay).

---

## Research Lead: Multi-Modal Earnings-Day Direction Prediction (arXiv:2605.25894, flagged 2026-08-02)

"Predicting Stock Price Direction on Earnings Announcement Days using Multi-modal Deep Learning" (arXiv:2605.25894) builds a feature space combining 15 fundamental metrics, 3 price-based technical indicators, and FinBERT-derived news-sentiment scores, then compares an LSTM, a Transformer, and a logistic-regression baseline for classifying next-day price direction on earnings announcement days. Ablation studies show a consistent benefit from adding the sentiment feature on top of fundamentals+technicals alone -- directionally consistent with our own H163/H174 confirmation that FinBERT-derived signal on earnings text carries real predictive value, though this paper targets earnings-day direction classification rather than the multi-week PEAD drift H163/H174 trades on. Architecture note: LSTM achieves higher precision via a more conservative decision boundary; the Transformer achieves a higher macro F1-score by catching more of the volatile/large moves.

**Caveat**: the publicly available abstract discloses no concrete accuracy, Sharpe, or return figures, nor the backtest universe/time period -- this is meaningfully thinner evidence than our own confirmed H163/H174 numbers (OOS WR=81.8%, MeanRet=6.89%, n=22) and should be read as corroborating direction, not a new actionable technique. It does not resolve the H317 finding that adding EPS-surprise/pre-momentum filters on top of FinBERT cuts event count below the n>=20 gate -- multi-modal feature fusion at the *architecture* level (this paper) is a different lever than filter-threshold stacking (H317's approach).

**Action needed before staging a hypothesis**: none currently planned -- flagging for awareness only until the full paper (not just abstract) is read and concrete backtest numbers can be extracted, similar to how pead-llm-architecture-comparison-2025.md required a full-PDF fetch (WebFetch failed on raw PDF; curl+Read succeeded) to get past abstract-level vagueness.
---

## Research Lead: Earnings-Call Q&A Evasion Signal (Journal of Investment Management 2026, flagged 2026-08-03)

"The Language of Evasion: How Semantic Similarity Between Questions and Answers Predicts Stock Returns" (Journal of Investment Management, 2026, DOI 10.1080/15427560.2026.2657322) proposes a PEAD-adjacent signal built from earnings-call Q&A structure rather than document sentiment. Method: embed each analyst question and the corresponding executive answer, score their semantic cosine similarity -- low similarity flags an evasive/non-responsive answer. Validated against 1,642 human-labeled Q&A pairs (evasive answers score low similarity 67% of the time vs. 22% for direct answers). Headline result: executives who answer directly (high Q&A similarity) generate **3.9% annual alpha** relative to evasive peers.

**Why this is structurally different from what we've already tried and rejected**: H168 (speaker-weighted FinBERT on transcripts) and H317 (multi-modal FinBERT+EPS+momentum) both extended or stacked onto the same underlying signal type -- document/utterance-level sentiment tone. This paper scores dialogue *structure* (does the answer address the question at all), which is orthogonal to whether the language used is positive or negative. A CEO can give a confidently-worded, FinBERT-positive answer that is still evasive by this metric, and vice versa. That orthogonality is the reason this is being logged as a distinct research lead rather than filed as "another FinBERT paper."

**Shared blocker with H168**: this needs full earnings-call Q&A transcript text, not just the 8-K filing H174 currently uses. H168's post-mortem found transcript availability itself introduces coverage bias into the OOS sample (only 26.5% of H163/H174-qualifying events had a matching transcript, and that 26.5% scored *worse* than baseline, WR=34.6%, suggesting the transcripts that exist are systematically different from the ones that don't). Any hypothesis built on this signal must budget for confirming transcript coverage rate on the current H174 event universe *before* backtesting, and should explicitly test whether the coverage-bias problem recurs -- if it does, this signal has the same practical ceiling as H168 regardless of its cleaner theoretical differentiation.

**Action needed before staging a hypothesis**: confirm transcript source/coverage (the HuggingFace dataset used for H168 ingestion is a candidate reuse target -- see H168 entry in hypothesis-log.md) and build a lightweight embedding-similarity scorer (any small sentence-embedding model, e.g. an already-available OpenAI embeddings call via `$OPENAI_API_KEY`, is sufficient -- no need for a dedicated FinBERT-scale model) before committing to a full IS/OOS hypothesis run.

---

## Research Lead: FinSMART — RL-Trained Sentiment Scoring (2026-08-05)

**Source**: Iacovides, Zhou & Mandic, "FinSMART: Financial Sentiment Analysis via Market-Aligned RL," arXiv:2607.28127, Jul 30 2026.

Trains a sentiment scorer via reinforcement learning directly against realized market returns (idiosyncratic + market components), using an asymmetric reward that requires two market conditions to align before reinforcing a signal -- a structurally different training target from FinBERT's static human-labeled sentiment classification that H163/H174 currently use. Reports +220% cumulative return over the strongest baseline in the paper's own benchmark; no Sharpe or win-rate disclosed at abstract level, and OOS methodology detail is unverified pending full-text read.

**Why it matters here**: H174 (score>=0.18 + surprise>=0.02 dual filter, OOS WR=81.8% n=22) has proven hard to beat by adding filters on top (H175 EPS magnitude, H317 multi-modal, H469 HiFi-KPI magnitude layer -- all NOT CONFIRMED or marginal). FinSMART targets a different lever: replacing the sentiment *scorer itself* rather than adding filters downstream of it. This is a parallel track to H481 (FinDPO), which also proposes swapping FinBERT's training objective.

**Status**: Research lead only, not yet a hypothesis. Needs full-text read to confirm OOS methodology and whether numbers are reproducible on our EDGAR 8-K corpus before scoping a backtest.

---

## Research Lead: Pure-Alpha / Pure-Beta Event Split (arXiv:2608.12283, flagged 2026-08-18)

**Source**: Kargarzadeh, Khaledian, Parvini & Khaledian, "Large Language Model-Driven Small-Capitalization Trading," arXiv:2608.12283, Aug 12 2026. Full writeup: [Sources — LLM Sentiment & Risk Decomposition, Small-Cap](../sources/llm-sentiment-risk-decomposition-smallcap-2026.md).

This Russell 2000 sentiment-trading paper splits stock-selection triggers into **pure-alpha** (the stock itself moved on a return z-score threshold, with no coincident macro-indicator trigger) vs. **pure-beta** (a macro indicator moved and the stock's rolling beta to it is elevated, but the stock hasn't reacted yet) vs. an intersection regime — and finds the intersection **consistently underperforms** requiring only one or the other to fire. Best OOS cell (pure-beta, GPT-4o mini sentiment, 40-day hold, risk-parity allocator) reaches Sharpe 2.33 at 100bp costs, though this is single-year (2025) OOS only and should not be taken as an established number.

**Why this is relevant to H174**: our current pipeline pools every qualifying 8-K/earnings event (score>=0.18, surprise>=0.02) identically regardless of whether the surprise coincided with a broader sector/macro move that day. This paper's finding suggests splitting the 22 confirmed H174 OOS events into "pure-alpha" (surprise with no same-day sector co-mover) vs. "pure-beta" (surprise riding a broader move) subgroups and checking whether win rate/mean return differs materially between them — a cheap re-slice of existing H174 event data, not a new data pipeline.

**Action needed before staging a hypothesis**: define the same-day "macro co-mover" threshold precisely (this paper uses a 58-indicator panel with |Z|>=2; H174's universe is much smaller so a simpler sector-ETF or SPY co-move threshold would need to be chosen), then re-slice the existing 22-event H174 OOS sample — note n will likely drop well below the usual n>=20 gate once split into two groups, so this may only be viable as a qualitative check rather than a formal gated hypothesis until more H174 events accumulate.

## Research Lead: 3-day early price signal as a PEAD.txt feature (2026-08-22)

Hadlock, Roberts & Lee, "Enhancing Post Earnings Announcement Drift Measurement with Large Language Models," FinNLP 2025 (ACL Anthology 2025.finnlp-2.13) compare encoder-decoder (BART) vs. encoder-only (FinBERT) architectures for PEAD text-signal prediction, and test whether adding a 3-day early market price signal improves textual PEAD measurement.

**Findings (abstract/search-snippet level only -- full PDF could not be parsed, needs a full read before acting on details):**
- FinBERT has the highest classification accuracy among architectures tested (57.6% positive-group, 58.3% negative-group) -- this validates our existing H163/H174 model choice rather than suggesting a change.
- BART (encoder-decoder) shows superior individual-stock drift-*magnitude* detection, but the authors flag portfolio-level implementation as unresolved.
- A 3-day early price signal folded in alongside the text signal is the paper's genuinely new element versus prior PEAD.txt work.

**Candidate follow-up hypothesis (next open slot, H529+):** add a trailing 3-day pre-8K-filing price-drift feature to the existing FinBERT-score + EPS-surprise dual-filter gate (score>=0.18 AND surprise>=0.02, per H174) and re-test on the H174 event set -- does it tighten win rate or n, or is it redundant with the already-required EPS surprise (H317 found 77% of H174 events already have EPS beats, so a naive early-price feature may be similarly redundant)? Low-cost test: no new data source needed, EDGAR 8-K timestamps + existing Alpaca/yfinance daily bars suffice.

**Caveat:** this entry is based on abstract/search-snippet claims only. WebFetch of the full PDF failed (binary parse error). Before implementing, do a full read of the PDF via curl+Read per the wiki skill's source-acquisition rule.

## Research Lead: Press-Release Structural Sentiment Aggregation ("SoftMean") — H174 Refinement Candidate (2026-08-26)

**Source**: Wu, Akin, Martineau, Grégoire & Veneris, "Extracting the Structure of Press Releases for Predicting Earnings Announcement Returns," ICAIF 2025, arXiv:2509.24254.

**Dataset**: 138,797 EDGAR 8-K earnings press releases, 2005-2023, 6,543 firms — same filing type and same FinBERT-family text model H174 already uses in production.

**Key finding**: Among bag-of-words vs. BERT-embedding sentiment methods compared, FinBERT gives the highest predictive power. The paper's headline result comes from an aggregated "SoftMean" signal — sentiment averaged across the *structural sections* of the press release (e.g. headline/lead, financial-results narrative, management commentary) rather than a single scalar score computed over the whole document at once. Top-sentiment-decile vs. bottom-sentiment-decile portfolios show a same-day return spread of **+4.58% vs -5.06%** (~9.6pp spread). The paper's broader claim: press-release *soft* information carries return-predictive content comparable in magnitude to the *numeric* EPS surprise itself — the two are complementary, not redundant, information channels.

**Why this matters for H174**: George's confirmed production PEAD strategy (H174: FinBERT score >= 0.18 AND EPS surprise >= 0.02, OOS win rate 81.8%, n=22) currently scores the *entire* 8-K document as a single pass, producing one scalar sentiment number. This paper suggests a structurally-aggregated multi-section score could extract materially more signal than a whole-document scalar — a concrete, testable refinement rather than a speculative new architecture.

**Candidate future hypothesis** (not yet numbered, not yet run — flagged for a future dream-cycle backtest session): segment each qualifying 8-K into 2-4 structural sections (e.g. via simple heading/paragraph-boundary heuristics, no new ML needed), score each with the existing FinBERT pipeline, and compare a SoftMean-aggregated composite against the current single-score baseline on the same H174 event set. Success criterion: does the SoftMean composite either (a) raise win rate/mean return at the same n=22 event count, or (b) allow a lower score threshold that expands n above 22 without degrading win rate below 81.8%? Either would be a genuine H174 upgrade. Must audit for the same look-ahead/as-of-date bug class documented in H509-H514 before trusting any backtested result — section boundaries must be determined only from text available at filing time, not from any downstream label.

**Related**: [PEAD LLM Architecture Comparison](../sources/pead-llm-architecture-comparison-2025.md) (BART vs FinBERT vs LLaMA-3.2-3B, same EMNLP-2025 FinNLP venue family — FinBERT wins accuracy, 3-day-return text-injection flagged as a separate candidate H174 enhancement). This SoftMean idea is complementary: architecture-comparison paper suggests *what model* to use (FinBERT, already confirmed); this paper suggests *how to structure the scoring pass* over the same model.
