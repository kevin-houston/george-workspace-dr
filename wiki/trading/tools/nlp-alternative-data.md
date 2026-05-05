---
updated: 2026-05-05
type: tool-guide
status: active — H163 running; H168 using AlphaVantage transcripts
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
| H163 | FinBERT NLP filter for PEAD entry (H159b + sentiment gate) | ProsusAI/finbert + edgartools | BLOCKED (EDGAR OOS coverage) |
| H164 | Elastic-net 8-quarter SUE history → 60-day drift prediction | FMP earnings API | NOT CONFIRMED (data blocker) |
| H165 | TradingAgents macro regime gate on H026 rotation | External (TradingAgents library) | PARTIAL CONFIRMED |
| H168 | Speaker-weighted FinBERT on earnings call transcripts | AlphaVantage transcript API | IN-PROGRESS |
| H171 | GPT-4o-mini API earnings sentiment (H168 LLM branch) | OpenAI API | QUEUED (after H168 transcripts cached) |
