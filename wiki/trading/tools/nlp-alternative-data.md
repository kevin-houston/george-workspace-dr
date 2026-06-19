---
updated: 2026-06-17
type: tool-guide
status: active — H163 CONFIRMED; H168 IN-PROGRESS; H171 QUEUED
---

# NLP & Alternative Data Libraries

Guide to Python libraries for financial text processing, earnings call sentiment analysis, and SEC filing retrieval. Directly relevant to the H163/H164 PEAD signal enhancement pipeline.

**Related pages**: [Event-Driven Strategies](../algorithms/event-driven.md) — H159/H163/H164 design | [Free Data Sources](../data-sources/free-data.md) — complementary free data catalog | [Hypothesis Log](../backtesting/hypothesis-log.md) — H163/H164 QUEUED

---

## Why financial NLP matters for this project

H159/H159b (PEAD) confirmed the gap-up drift effect is real (OOS t=5.64) but the portfolio has too many false positives — gap-up stocks that reverse. The goal is to **filter entries by earnings sentiment** to raise the win rate from 63.9% to ~68–72%.

Key academic finding (2025 study, 16,428 S&P 500 earnings calls 2015–2025):
- **FinBERT section-weighted sentiment** → OOS Spearman IC = 0.142, monthly long-short alpha = **+2.03%** unexplained by Fama-French 5-factor
- **Loughran-McDonald dictionary** → FinBERT entirely subsumes it (LM coeff t=0.86 vs FinBERT t=5.90 in combined regression)
- LM dictionary underestimates economic magnitude by 44% vs FinBERT

---

## Sentiment Models

### 1. ProsusAI/finbert — primary recommendation

**HuggingFace**: `ProsusAI/finbert` | **Downloads**: 6.4M/month | **License**: CC BY-SA 4.0  
**Paper**: arXiv:1908.10063 (Araci 2019)  
**Model size**: ~440MB (BERT-base architecture, 110M params)

Fine-tuned on **Financial PhraseBank** (4,840 analyst sentences, consensus-labeled positive/negative/neutral). Achieves:
- 97% accuracy on high-agreement subset (100% annotator agreement)
- 89% accuracy overall on financial sentiment classification vs 76% for general BERT

**Output**: softmax probabilities for `positive`, `negative`, `neutral`.

```python
from transformers import BertTokenizer, BertForSequenceClassification
import torch
import torch.nn.functional as F

tokenizer = BertTokenizer.from_pretrained("ProsusAI/finbert")
model = BertForSequenceClassification.from_pretrained("ProsusAI/finbert")
model.eval()

def finbert_score(text: str) -> float:
    """Returns positive_prob - negative_prob. Range: [-1, 1]"""
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = F.softmax(logits, dim=-1)[0]
    # label order: positive=0, negative=1, neutral=2 (check label2id)
    label2id = model.config.label2id
    pos_p = float(probs[label2id.get("positive", 0)])
    neg_p = float(probs[label2id.get("negative", 1)])
    return pos_p - neg_p  # positive → enter, negative → skip

# Example: batch scoring for H163 filter
def score_earnings_text(transcript: str) -> float:
    """Score a full earnings call transcript by averaging sentence scores."""
    sentences = [s.strip() for s in transcript.split('.') if len(s.strip()) > 20]
    scores = [finbert_score(s) for s in sentences[:200]]  # cap at 200 sentences
    return sum(scores) / len(scores) if scores else 0.0
```

**H163 threshold**: enter PEAD position only if `finbert_score > +0.10`.  
**Expected outcome**: base WR 63.9% → 68–72% on retained events (~20% fewer trades).

**Speed**: ~1 second/sentence on CPU; ~50ms/sentence on GPU. For our ~40 events/year: CPU is fine.

---

### 2. yiyanghkust/finbert-tone — alternative for analyst reports

**HuggingFace**: `yiyanghkust/finbert-tone` | **Paper**: arXiv:2006.08097 (Yang et al. 2020)  
**GitHub**: https://github.com/yya518/FinBERT

Pre-trained on a **much larger financial corpus** than ProsusAI/finbert:
- 2.5B tokens from annual/quarterly reports (10-K, 10-Q)
- 1.3B tokens from earnings call transcripts
- 1.1B tokens from analyst reports

Fine-tuned on 10,000 manually annotated sentences from analyst reports. Accuracy: **88.7%** on AnalystTone dataset (+5.5pp over standard BERT).

**When to use finbert-tone over ProsusAI/finbert**:
- Earnings call transcript tone analysis → **use finbert-tone** (trained on earnings call text)
- Financial news headlines → **use ProsusAI/finbert** (trained on news/phrases)
- SEC 10-K/10-Q management discussion → **use finbert-tone**

```python
from transformers import pipeline

# Simpler pipeline API
pipe = pipeline("text-classification", model="yiyanghkust/finbert-tone")
result = pipe("Revenue beat expectations, guidance raised for full year")
# → [{'label': 'Positive', 'score': 0.94}]
```

---

### 3. Loughran-McDonald dictionary — fast baseline (subsumed by FinBERT)

**Library**: `pysentiment2` | **Install**: `pip install pysentiment2`  
**Dictionary**: Loughran & McDonald (2011), curated from SEC 10-K filings

Lexicon-based approach — no ML model, runs in microseconds. Word lists: Positive, Negative, Uncertainty, Litigious, Constraining, Superfluous.

```python
import pysentiment2 as ps

lm = ps.LM()
tokens = lm.tokenize("Revenue exceeded expectations though uncertainty remains elevated")
score = lm.get_score(tokens)
# → {'Positive': 1, 'Negative': 0, 'Uncertainty': 1, ...}

finbert_equivalent = (score['Positive'] - score['Negative']) / max(1, len(tokens))
```

**Verdict**: Use as a **fast pre-filter** before running the heavier FinBERT model, or as a fallback when GPU/compute is unavailable. For production H163, FinBERT is preferred — LM is statistically subsumed once FinBERT enters the regression.

---

## SEC Filing Retrieval

### 1. edgartools — preferred for structured 8-K parsing

**GitHub**: https://github.com/dgunning/edgartools | **Stars**: 2.1k  
**Version**: v5.30.2 (April 29, 2026) | **License**: MIT  
**Install**: `pip install edgartools`  
**No API key required.** Directly queries SEC EDGAR with rate limiting baked in.

Best tool for H163 pipeline: parses 8-K filings into structured `Item` objects, making it easy to extract Item 2.02 (Earnings Releases).

```python
from edgar import Company, get_filings, set_identity

# Required: identify yourself to SEC per EDGAR TOS
set_identity("yourname youremail@example.com")

# Get recent 8-K filings for a company
company = Company("AAPL")
filings = company.get_filings(form="8-K")

# Get the most recent 8-K
filing = filings[0]
eightk = filing.obj()

# Access item structure
print(eightk.items)  # list of items filed: ['2.02', '9.01']

# Get full text of Item 2.02 (Results of Operations)
item_202 = eightk["2.02"]
print(item_202.text[:500])  # earnings release text
```

**Rate limits**: Follows SEC's 10 req/sec limit automatically. 30-second caching on repeated requests.

**MCP server**: Also has a Claude MCP server (`edgartools-mcp`) — not needed for scripted use.

---

### 2. sec-edgar-downloader — bulk download to local files

**GitHub**: https://github.com/jadchaar/sec-edgar-downloader | **Stars**: 900+  
**Install**: `pip install sec-edgar-downloader`  
**License**: MIT | **No API key required**

Simpler than edgartools — downloads raw filing HTML/text files to disk. Better for batch downloading all 8-Ks for a large universe.

```python
from sec_edgar_downloader import Downloader

# Initialize with your company name and email (SEC requirement)
dl = Downloader("MyCompany", "user@example.com", "/path/to/downloads")

# Download all 8-K filings for Apple since 2020
dl.get("8-K", "AAPL", after="2020-01-01")

# Files saved to: /path/to/downloads/sec-edgar-filings/AAPL/8-K/
# Each filing folder contains: filing-details.xml, primary-document.html, exhibit files
```

**Limitation**: No structured item extraction — you get raw HTML. Use edgartools for structured access; use sec-edgar-downloader for bulk pre-fetching.

---

### 3. FMP Earnings Dates (for H163 event matching)

For matching ticker + earnings date to 8-K filing, use FMP (key already in vault):

```python
import requests, os

# Get earnings calendar for a ticker
def get_earnings_dates(ticker: str, api_key: str) -> list[dict]:
    url = f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/{ticker}"
    r = requests.get(url, params={"apikey": api_key, "limit": 40})
    return r.json()  # [{"date": "2024-10-31", "eps": 1.64, "epsEstimated": 1.57, ...}]

# Compute SUE (Standardized Unexpected Earnings)
def compute_sue(actual_eps: float, estimated_eps: float, std_eps: float = 0.1) -> float:
    return (actual_eps - estimated_eps) / std_eps
```

---

## H163 Full Pipeline

This combines all the above for the FinBERT PEAD signal filter:

```python
from edgar import Company, set_identity
from transformers import BertTokenizer, BertForSequenceClassification
import torch, torch.nn.functional as F
import pandas as pd

set_identity("George NanoClaw george@nanoclaw.io")

# Load FinBERT once
tokenizer = BertTokenizer.from_pretrained("ProsusAI/finbert")
model = BertForSequenceClassification.from_pretrained("ProsusAI/finbert")
model.eval()

def get_earnings_sentiment(ticker: str, event_date: str) -> float | None:
    """Return FinBERT score for 8-K Item 2.02 filed on or near event_date."""
    try:
        company = Company(ticker)
        filings = company.get_filings(form="8-K")
        
        # Find 8-K filed within ±3 days of event_date
        target = pd.Timestamp(event_date)
        for f in filings[:20]:
            filing_date = pd.Timestamp(str(f.filing_date))
            if abs((filing_date - target).days) <= 3:
                eightk = f.obj()
                if "2.02" in (eightk.items or []):
                    text = eightk["2.02"].text[:3000]  # first 3k chars
                    return score_earnings_text(text)
    except Exception:
        pass
    return None  # skip if no 8-K found

def filter_pead_events(events_df: pd.DataFrame,
                       score_threshold: float = 0.10) -> pd.DataFrame:
    """Add finbert_score column; filter to positive-sentiment events only."""
    scores = []
    for _, row in events_df.iterrows():
        score = get_earnings_sentiment(row["ticker"], str(row["date"]))
        scores.append(score)
    events_df = events_df.copy()
    events_df["finbert_score"] = scores
    # Keep events where we got a score AND it's positive
    filtered = events_df[
        events_df["finbert_score"].notna() &
        (events_df["finbert_score"] > score_threshold)
    ]
    print(f"Filtered: {len(filtered)}/{len(events_df)} events pass (threshold={score_threshold})")
    return filtered.reset_index(drop=True)
```

**Expected behavior**: ~20% of gap-up events have negative/neutral earnings sentiment and will be filtered. The remaining 80% should have higher drift probability.

---

## Benchmarks and Reality Checks

| Tool | Task | Accuracy | Speed | Free? |
|------|------|----------|-------|-------|
| ProsusAI/finbert | News/phrases sentiment | 89% | ~1s/sent CPU | ✓ (HuggingFace) |
| yiyanghkust/finbert-tone | Earnings call tone | 88.7% (AnalystTone) | ~1s/sent CPU | ✓ (HuggingFace) |
| Loughran-McDonald (pysentiment2) | SEC filing lexicon | ~70% (domain F1) | <1ms/doc | ✓ (PyPI) |
| edgartools | 8-K structured parse | N/A | ~0.5s/filing | ✓ (MIT) |
| sec-edgar-downloader | Bulk 8-K download | N/A | bulk async | ✓ (MIT) |
| sec-api.io | Commercial SEC API | N/A | fast hosted | ✗ ($250/mo) |

**Key academic results** (2025 study, 16k earnings calls):
- FinBERT section-weighted: OOS Spearman IC = 0.142, monthly long-short alpha = **+2.03%** vs FF5
- LM dictionary: entirely subsumed by FinBERT in combined specs (LM t=0.86, FinBERT t=5.90)
- LM underestimates economic magnitude by **44%** vs FinBERT

---

## Installation

```bash
pip install transformers torch edgartools pysentiment2 sec-edgar-downloader

# GPU support (optional but 20x faster):
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

**Model download on first use** (~440MB for ProsusAI/finbert):
```python
# Pre-download to cache before running backtest
from transformers import BertTokenizer, BertForSequenceClassification
BertTokenizer.from_pretrained("ProsusAI/finbert")          # ~300MB
BertForSequenceClassification.from_pretrained("ProsusAI/finbert")  # ~440MB
```

---

## Known Limitations

1. **8-K timing vs gap-up timing**: Earnings are pre-announced and gap-ups happen at open. The 8-K is filed with SEC hours after the gap-up. Use the *announcement text* (press release attached to 8-K), not subsequent analyst commentary.

2. **Text length**: FinBERT max input is 512 tokens (~380 words). Full earnings transcripts are 10–20k words. Chunk and average, or focus on the first 1,500 words (prepared remarks have highest signal density).

3. **In-sample only**: Item 2.02 often contains the exact EPS vs estimate comparison — this is *forward-looking text* from management's perspective. If management is guiding down, that's the signal. If they're celebrating a beat, that's also the signal. Both are legitimate.

4. **No real-time feed**: edgartools pulls from SEC EDGAR, which has filings within hours of announcement. For live trading H163, need to poll EDGAR for new 8-Ks every 15 minutes during earnings season.

5. **CPU inference time**: 40 events × 20 sentences × 1s/sentence = ~13 minutes on CPU. Fine for batch backtest; marginal for live trading. Consider GPU or batched inference.

---

## AlphaVantage Earnings Call Transcripts

**API**: `EARNINGS_CALL_TRANSCRIPT` endpoint  
**Key**: `$ALPHA_VANTAGE_API_KEY` (env var; free tier = 25 req/day)  
**Format**: speaker-segmented JSON with `{speaker, title, content, sentiment}`  
**Coverage**: Back to ~2015 for S&P 500 companies  
**Rate limit**: ~25 requests/day on free tier; pause between calls

```python
import requests, os

def get_transcript(ticker: str, fiscal_quarter: str) -> list | None:
    """
    fiscal_quarter: e.g. "2024Q1" = fiscal Q1 of 2024.
    AlphaVantage uses FISCAL year notation, not calendar year.
    For AAPL (Sep FY): 2024Q1 = Oct-Dec 2023, reported Jan 2024.
    For most others (Dec FY): 2024Q1 = Jan-Mar 2024, reported Apr 2024.
    """
    r = requests.get("https://www.alphavantage.co/query", params={
        "function": "EARNINGS_CALL_TRANSCRIPT",
        "symbol": ticker,
        "quarter": fiscal_quarter,
        "apikey": os.environ["ALPHA_VANTAGE_API_KEY"]
    }, timeout=30)
    data = r.json()
    if "transcript" in data:
        return data["transcript"]
    return None  # rate limit or no transcript

# Each entry in the list:
# {"speaker": "Tim Cook", "title": "CEO", "content": "...", "sentiment": "0.0"}
# Typical titles: "Analyst", "CEO", "CFO", "Operator", "Director of Investor Relations"
```

**Fiscal quarter mapping** (most common):
| Company type | Event month | AV quarter string |
|-------------|-------------|------------------|
| Calendar FY (most) | Jan-Mar | `YYYY-1Q4` (reporting prior Q4) |
| Calendar FY (most) | Apr-Jun | `YYYYQ1` |
| Calendar FY (most) | Jul-Sep | `YYYYQ2` |
| Calendar FY (most) | Oct-Dec | `YYYYQ3` |
| AAPL (Sep FY end) | Jan-Feb | `YYYYQ1` |
| AAPL (Sep FY end) | Apr-May | `YYYYQ2` |
| AAPL (Sep FY end) | Jul-Aug | `YYYYQ3` |
| MSFT (Jun FY end) | Jan-Mar | `YYYYQ3` |
| MSFT (Jun FY end) | Apr-Jun | `YYYYQ4` |
| MSFT (Jun FY end) | Jul-Sep | `YYYY+1Q1` |

**Use case**: H168 — speaker-weighted FinBERT. Weights from arXiv:2604.13260: Analyst 49%, CFO 30%, Executive 16%, Other 5%.

### Analyst belief asymmetry (arXiv:2511.15214)

Matera (Nov 2025): analysts **over-react** to positive sentiment/optimism and **under-react** to risk/uncertainty narratives in earnings calls. Exploitable implication: management hedging language contains delayed price information not captured by polarity alone.

**H168 v2 design refinement:** Add uncertainty-weighting layer on top of speaker weights:
1. Score each segment with FinBERT polarity (existing H168)
2. Compute uncertainty vocabulary density using Loughran-McDonald uncertainty word list
3. Downweight high-uncertainty CFO segments even if positive tone; upweight low-hedging analyst segments
4. Final score = speaker_weight × (finbert_polarity − λ × uncertainty_density)

Test λ in {0.0, 0.5, 1.0} as H168 v2 after baseline H168 results are known.

**GPT-4o-mini alternative (H171):** arXiv:2505.07871 shows instruction-prompted LLM achieves 82% financial sentiment accuracy comparable to FinBERT. Cost: ~$0.48 total for full H168 event universe. Speed: ~27 min vs ~3h CPU FinBERT inference. Simple prompts beat Chain-of-Thought for financial classification (arXiv:2506.04574). H171 queued after H168 baseline.

---

## Related Hypothesis Queue

| ID | Description | Depends on this page | Status |
|----|-------------|---------------------|--------|
| H163 | FinBERT NLP filter for PEAD entry (H159b + sentiment gate) | ProsusAI/finbert + edgartools | **CONFIRMED** (OOS WR ≥68%, MeanRet ≥5.5%) |
| H164 | Elastic-net 8-quarter SUE history → 60-day drift prediction | FMP earnings API | NOT CONFIRMED (data blocker) |
| H165 | TradingAgents macro regime gate on H026 rotation | External (TradingAgents library) | PARTIAL CONFIRMED |
| H168 | Speaker-weighted FinBERT on earnings call transcripts | AlphaVantage transcript API | IN-PROGRESS |
| H171 | GPT-4o-mini API earnings sentiment (H168 LLM branch) | OpenAI API | QUEUED (after H168 transcripts cached) |
| H172 | Fine-tuned FinBERT on H163 labeled 8-K texts | H163 8-K cache + outcome labels | PROPOSED (see below) |

---

## LLM Agent Design: Fine-Grained Tasks (arXiv:2602.23330, Feb 2026)

For H165 TradingAgents step 2: use **fine-grained task decomposition** instead of coarse agent roles.

- **Coarse (poor)**: "Analyze the macro environment and recommend position sizing"
- **Fine-grained (good)**: "(1) Compute 12m momentum for each sector ETF. (2) Check VIX level vs 25 threshold. (3) Check 2y10y spread. (4) Extract current-quarter earnings growth YoY. (5) Output: regime=expansion/neutral/contraction + confidence."

Finding: alignment between intermediate agent outputs and final investment decisions is the primary performance driver — more than number of agents or model size.

## sec-parser (alphanome-ai)

**GitHub:** https://github.com/alphanome-ai/sec-parser  
**License:** MIT | **Stars:** ~800 | **Maintained:** active 2025–2026

Parse SEC EDGAR filings (10-K, 10-Q, 8-K) into semantic tree structures. Enables section-level extraction without regex heuristics.

```bash
pip install sec-parser
```

```python
from sec_parser import SemanticTree, TreeBuilder
from edgar import Company  # edgartools to get raw HTML

# Get 8-K HTML from edgartools
filing = Company("AAPL").get_filings(form="8-K").latest()
html = filing.html()

# Parse into semantic tree
builder = TreeBuilder()
tree = builder.build(html)

# Extract Item 2.02 (Results of Operations)
item_202_nodes = [n for n in tree.nodes if '2.02' in str(getattr(n, 'title', ''))]
item_202_text = ' '.join(n.text for n in item_202_nodes if hasattr(n, 'text'))
```

**Use case for H163/H175:** Score only Item 2.02 text rather than full 8-K. arXiv 2509.24254 shows press release *structure* matters — specific sections are more predictive than full text noise.

**vs edgartools:** edgartools provides filing access and `.obj()` for structured 8-K; sec-parser provides section-level HTML parsing. Use both: edgartools to fetch, sec-parser to extract specific items.

---

## Time Series Foundation Models Need In-Domain Pre-Training (arXiv:2511.18578, Nov 2025)

Off-the-shelf pre-trained TSFMs (time series foundation models like TimesFM, Chronos) **fail in zero-shot and fine-tuning settings for financial data**. Models trained from scratch on financial data achieve substantial improvements.

**H172 opportunity**: Fine-tune FinBERT on H163's labeled 8-K event texts:
1. H163 cache has ~200 8-K press release texts for IS events
2. Each event has a ground-truth label: 20-day return > 0 = WIN, ≤ 0 = LOSS
3. Fine-tune FinBERT on these labeled texts as a binary classifier
4. Expected: better-calibrated positive probability for PEAD filtering than zero-shot polarity score
5. Cost: ~4h CPU training, no GPU needed; H163 already confirmed zero-shot works at WR ≥68%

---

## ModernFinBERT (July 2025) — Successor to ProsusAI/finbert

**ModernFinBERT** is a financial sentiment model based on the ModernBERT architecture, released July 2025. Positioned as the successor to `ProsusAI/finbert` with improved accuracy on earnings calls and analyst reports.

**Usage** (identical to FinBERT via HuggingFace `transformers`):
```python
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Drop-in swap: change model name only
model_name = "your-org/ModernFinBERT"  # check HuggingFace for exact ID
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(model_name)
model.eval()

# Inference unchanged from H163/H174 pipeline
inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
with torch.no_grad():
    logits = model(**inputs).logits
probs = torch.softmax(logits, dim=-1)[0].numpy()
score = float(probs[0] - probs[1])  # positive - negative
```

**Candidate for H176**: Drop-in upgrade to H163/H174 scoring pipeline. Validate on H163 IS/OOS event set before deploying to live paper trading. If ModernFinBERT scores show meaningful correlation improvement vs ProsusAI/finbert on labeled events, update `pead_overnight.py` scorer.

**Check**: https://huggingface.co/models?search=modernfinbert for current release artifacts. Benchmark: compare pos−neg score distribution on H163's 85 OOS events with known outcomes.

---

## LLM vs FinBERT for Financial Sentiment (2026 Benchmark)

**Source**: arXiv:2505.16090 (May 2026). "Can AI Read Between the Lines? Benchmarking LLMs on Financial Nuance."

**Key finding**: FinBERT remains most effective for finance-specific sentiment classification. General-purpose LLMs (GPT-4o, Claude 3.5) underperform FinBERT on domain-specific tasks despite superior general reasoning.

**Decision tree for H-series NLP tasks:**

| Task | Recommended Model | Reason |
|------|------------------|--------|
| 8-K press release sentiment (H163/H174) | FinBERT (ProsusAI) | Domain-specific, fast, proven |
| Earnings transcript sentiment scoring | FinBERT or ModernFinBERT | Financial domain pretraining essential |
| Nuanced qualitative reasoning ("read between lines") | GPT-4o-mini | General LLMs win on nuance |
| High-volume batch processing (<1ms latency) | FinBERT | 10× faster than GPT-4o-mini |
| Low-volume, high-stakes signals | GPT-4o-mini | Justify API cost with edge |

**Implication for H171 (GPT-4o-mini alternative)**: H171 should target nuanced qualitative signals (management tone shifts, guidance hedging language) rather than raw sentiment — that's where GPT-4o-mini has an actual advantage over FinBERT.

---

## Dynamic Factor Reweighting via Earnings Sentiment (QuantMuse pattern)

**Source**: [QuantMuse](https://github.com/0xemmkty/QuantMuse) — MIT-licensed quant trading system, first major release April 2026.

**Pattern**: At each monthly rebalance, compute an aggregate earnings sentiment score for the portfolio universe (FinBERT or GPT over recent 8-Ks and transcripts). Use this score to shift factor weights:

```python
def sentiment_adjusted_weights(base_weights: dict, sentiment_score: float) -> dict:
    """
    sentiment_score: [-1, 1] from FinBERT or GPT over recent earnings releases
    base_weights: {'momentum': 0.3, 'value': 0.2, 'quality': 0.3, 'vol': 0.2}
    """
    # Positive sentiment: lean momentum and quality
    # Negative sentiment: lean value and low-vol (defensive)
    momentum_tilt = 0.1 * sentiment_score
    quality_tilt = 0.05 * sentiment_score
    value_tilt = -0.08 * sentiment_score
    vol_tilt = -0.07 * sentiment_score
    
    adjusted = {
        'momentum': base_weights['momentum'] + momentum_tilt,
        'quality': base_weights['quality'] + quality_tilt,
        'value': base_weights['value'] + value_tilt,
        'vol': base_weights['vol'] + vol_tilt,
    }
    # Normalize to sum to 1.0
    total = sum(adjusted.values())
    return {k: v / total for k, v in adjusted.items()}
```

**QuantMuse claims**: ~70% of post-earnings drift is captured by tilting toward momentum + quality factors when aggregate sentiment is positive.

**Applicability to our pipeline**: Could upgrade H188 monthly rebalance to use FinBERT aggregate sentiment (from PEAD watchlist passes) to tilt factor weights. Low-risk experiment — worst case reverts to equal weights.

**Caveat**: 70% claim is unverified and likely reflects paper trading / simulation results, not live OOS performance. Treat as an implementation pattern to test, not a validated result.


---

## FinBERT on Earnings Call Transcripts — Benchmark Findings

**Source**: arXiv:2503.01886 (Mar 2025). "Deep Learning Benchmarks for Earnings Call Transcript Analysis."

**Key finding**: Domain-adapted FinBERT trained specifically on earnings call language outperforms general FinBERT (news-trained) by 8–12% accuracy on transcript sentiment tasks. General-purpose BERT falls a further 15% below FinBERT. The distinction matters because earnings transcript language has distinct patterns:
- Management hedging language ("headwinds", "uncertainty", "remain cautious")
- Analyst Q&A adversarial probing vs. prepared statement tone
- Sequential structure: prepared remarks → Q&A → closing statements

**Recommended model hierarchy for H163/H174**:
1. `yiyanghkust/finbert-tone` — best for sentiment direction (positive/negative/neutral) on short spans
2. `ProsusAI/finbert` — general financial text, good baseline
3. Transcript-specific fine-tune (see paper Table 3) — best for earnings call Q&A sections
4. General BERT — **avoid** for this task

**Implementation note for H163**: The current pipeline calls `prosus-ai/finbert` on the full 8-K text. Accuracy uplift of ~10% is available by:
1. Splitting the 8-K into MD&A section vs. financial tables
2. Running tone-adapted FinBERT only on the MD&A narrative
3. Ignoring quantitative table sections (adds noise, not signal)

**Signal quality impact**: The paper estimates that using appropriate transcript-tuned model vs. naive FinBERT adds ~0.15 information coefficient (IC) per quarter across earnings events. On H163's current universe (30 large-caps), this translates to roughly 0.2–0.3 Sharpe improvement if the signal quality gain propagates through.

**Practical upgrade path**: Before H174 goes live, test `yiyanghkust/finbert-tone` as a drop-in replacement for the current FinBERT call in `backtesting/paper_trading/pead_overnight.py`. Compare classification output on a sample of historical 8-Ks.

## PEAD + LLM (2025 update)

**Source**: Enhancing Post Earnings Announcement Drift Measurement with Large Language Models (FinNLP 2025)

- FinBERT still outperforms LLMs (BART, GPT) on PEAD direction classification: 57.6% accuracy vs lower for generative models
- Encoder-only FinBERT captures financial domain nuance more reliably than decoder models for this task
- **Key finding**: Adding 3-day early market signal alongside FinBERT text score significantly improves PEAD prediction
- Practical implication for H163/H174: add a confirming filter — only enter OPG order if early pre-market move aligns with FinBERT sentiment direction

---

### FinBERT2 — Next-Generation Financial NLP (H174 Upgrade Candidate)

**Reference**: arXiv:2506.06335 (May 2025), presented KDD 2025  
**Model**: `prosus-ai/finbert2` or equivalent HuggingFace release

**Performance vs. FinBERT1 (ProsusAI/finbert)**:
- +0.4%–3.3% accuracy improvement across 5 financial classification benchmarks
- +9.7%–12.3% vs. GPT-4/Claude on discriminative tasks (classification, topic modeling)
- Trained on 32B tokens financial corpus (vs. FinBERT1's smaller corpus)
- Better on structured retrieval and feature tasks, not just sentiment

**H174 integration notes**:
- Direct drop-in for current `ProsusAI/finbert` in `pead_overnight.py`
- Change: `model_name = 'prosus-ai/finbert2'` (verify HuggingFace availability)
- Same positive/negative/neutral output format
- Expected improvement: 1-3 bps additional signal quality on 8-K press release scoring
- A/B test: run both models on same 8-K corpus; compare score distributions vs. actual PEAD returns

**Caution**: 0.4–3.3% accuracy gain is small in absolute terms. Only pursue if FinBERT2 is available on HuggingFace and inference latency is comparable. The dual-threshold gate (FinBERT score + EPS surprise) may mask single-model improvements — the EPS surprise filter does more heavy lifting than the NLP score alone.


## FinCall-Surprise (arXiv:2510.03965, Oct 2025)

**Dataset:** 2,688 corporate conference calls 2019-2021. Three modalities: transcript text, audio recordings, presentation slides.
**Benchmark:** 26 language models (unimodal + multi-modal) tested on earnings surprise prediction.

**Key findings:**
- Audio and visual data provide small performance improvements, but current models cannot effectively extract value from these signals
- Specialized financial models unexpectedly struggle with instruction-following (important caveat for GPT-4o/Claude-based PEAD pipelines)
- High accuracy metrics often mask class imbalance — evaluate with balanced metrics
- **Text-only remains the best practical approach** for earnings-driven signals

**Implication for H174/H258:** Our FinBERT text-only approach (H174 OOS WR=81.8%) remains state-of-the-art accessible. Multi-modal (audio from earnings calls) is not yet reliable enough to warrant the complexity. H258 (LLM metric-shift on 10-Q text) is the right extension — text-based, not audio.

---

## Kevin's Curated NLP References (2026-06-09)

### BloombergGPT — Domain-Specific LLM for Finance (arXiv:2303.17564)

**Reference:** arXiv:2303.17564 (Wu et al., Bloomberg, Mar 2023)
**Kevin's note:** "Why general models like Claude underperform on finance tasks vs domain-specific ones."

**Architecture:** 50B parameter LLM trained on a 363B token corpus — half Bloomberg's proprietary financial data (FinPile: news, filings, press releases, earnings calls), half general text. Mixed training was found to be critical: pure financial corpus overfits, pure general corpus lacks domain knowledge.

**Benchmark results (vs GPT-3.5 and general LLMs):**
- Financial NLP tasks (sentiment, NER, headline classification, QA): BloombergGPT wins decisively
- General NLP benchmarks: comparable to GPT-3.5 on most tasks
- Task: financial sentiment on FPB dataset — BloombergGPT 51.1% F1 vs FinBERT 23.8% F1 (general sentiment framing differs from financial polarity)

**Why general models underperform on finance:**
1. **Vocabulary gap:** Finance has dense jargon ("amortization," "convexity," "covenant-lite") that general corpora underrepresent
2. **Polarity reversal:** "Impressive losses" is negative; general models can misread financial irony
3. **Entity disambiguation:** Company names, ticker symbols, and financial instruments require domain-grounded understanding
4. **Numerical reasoning:** Balance sheet arithmetic requires precision general LLMs struggle with

**Implication for our stack:** This is why H174 uses FinBERT (encoder-only, fine-tuned on financial text) rather than a general Claude API call for 8-K scoring. The domain gap is real and measurable. For tasks beyond binary sentiment — structured extraction, nuanced risk language — the gap may be even larger. H258 (LLM metric-shift) should use a finance-tuned model, not base Claude/GPT.

---

### LLMs as Financial Data Annotators (arXiv:2403.18152)

**Reference:** arXiv:2403.18152 (Mar 2024)
**Kevin's note:** "Where LLMs actually belong in your quant stack: labeling and signal extraction."

**Core finding:** LLMs (GPT-4, Claude, etc.) are effective as **zero-shot annotators** for financial data — classifying sentiment, extracting structured facts from filings, labeling events — but perform inconsistently as direct trading signal generators.

**Where LLMs work well as annotators:**
- Binary/ternary sentiment labels on news headlines and earnings excerpts (accuracy 80-90% vs human gold labels)
- Named entity extraction from 10-K/10-Q risk factor sections (company names, event types, financial metrics)
- Event classification (M&A, restructuring, guidance change, regulatory action) from press releases
- Consistency: LLMs outperform crowdworkers on annotation agreement when given structured rubrics

**Where LLMs fail as direct signal generators:**
- Calibrated probability estimates for price direction (overconfident)
- Aggregating multi-document context coherently under long context windows
- Numerical reasoning on financial ratios directly from text

**The right architecture:**
```
Raw text → LLM annotator (structured labels) → traditional quant model (ML/rules) → signal
```
Not: `Raw text → LLM → trade signal`

**Implication for our stack:** This validates exactly how H174 works: FinBERT is the annotator (labels 8-K sentiment), and the signal is the composite score + EPS surprise gate, not raw LLM output. For H260 (12-quarter ML features), LLM annotation of earnings call tone/topic shifts is the right sub-role — not direct price prediction.

---

## LLM Stock Forecasting Reviews (2025–2026)

### arXiv:2605.05211 — LLMs for Stock Price Forecasting: Hedge-Fund Perspective (Apr 2026)
**Accepted:** IEEE Conference on Artificial Intelligence, Spain, May 2026

**Key findings:**
- LLM sentiment pipelines produce **regime-dependent** text-to-return mappings — what works in bull markets fails in bear markets (and vice versa)
- **Source selection bias**: papers cherry-pick news sources; out-of-sample coverage degrades when source mix changes
- Survivorship and publication effects inflate IS statistics systematically
- **Bottom line**: LLM as *signal contributor* (FinBERT score → threshold rule) is more robust than LLM as *portfolio manager*

**Implication for H163/H174**: Our FinBERT-on-8-K approach (fixed threshold, score ≥ 0.18) is the safer architecture. BUT the regime-dependence finding suggests adding a regime gate (e.g., only fire PEAD entries when SPY > 200MA) could improve OOS consistency — addressed by H305/H308.

### arXiv:2510.03195 — From Text to Alpha: LLMs Track Evolving Corporate Disclosures (Mar 2026)

**Key findings:**
- SEC 8-K and 10-K language evolves meaningfully over 5–10 year horizons (boilerplate shifts, new risk factor language, ESG language)
- LLMs fine-tuned on 2010–2015 language show signal decay by 2022
- **Rolling recalibration** (1–2 year fine-tune window) restores alpha in simulations

**Implication for H174**: FinBERT (ProsusAI/finbert) was trained on FinancialPhraseBank + Reuters financial news (pre-2020 corpus). As 8-K language evolves post-2020, model calibration may drift. Practical mitigation: monitor H174 win rate quarterly; if 4Q rolling WR drops below 70%, flag for model refresh.

**Monitoring hook** (add to pead_overnight.py — future enhancement): log rolling 90-day win rate to a JSON metrics file; alert George if WR < 0.70 over trailing 10 trades.

## FinBERT2 — Potential H163/H174 Upgrade (arXiv:2506.06335, KDD 2026)

**Source:** arXiv:2506.06335, Proceedings of the 31st ACM SIGKDD Conference on Knowledge Discovery and Data Mining V.2 (2026)

**What it is:** A new specialized bidirectional encoder pretrained on 32B financial-domain tokens — the largest known Chinese financial pretraining corpus for models of this parameter size. Architecture follows BERT-base but with domain-specific vocabulary.

**Performance vs FinBERT (ProsusAI/finbert):**
- Discriminative tasks (Fin-Labelers): +0.4–3.3% over BERT variants including FinBERT; +9.7–12.3% over GPT-4-class LLMs on 5 financial classification benchmarks
- Retrieval tasks (Fin-Retrievers): +6.8% over BGE-base-zh, +4.2% over OpenAI text-embedding-3-large
- Topic modeling: Fin-TopicModel outperforms standard LDA on Chinese financial titles

**Important caveat:** Pretrained on *Chinese* financial corpus. English-domain financial text performance not documented in abstract. Need to test on EDGAR 8-K corpus before swapping into pead_overnight.py pipeline.

**H312 hypothesis seed:** Run H163/H174 PEAD backtest replacing ProsusAI/finbert with FinBERT2 (if English model weights available). Gate: OOS win rate ≥ 83% (current H174 = 81.8%). If Chinese-only: treat as negative result and document.

**Model weights:** Check Hugging Face for `FinBERT2` or `finbert2` — not confirmed available as of 2026-06-19. Monitor KDD 2026 proceedings for code release.
