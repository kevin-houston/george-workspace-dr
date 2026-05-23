---
updated: 2026-05-23
type: reference
relevance: PEAD strategy (H163/H174), event-driven (H168), factor models (H202-XL)
---

# Earnings Calendar & Corporate Events Data Sources

Critical for PEAD (H163/H174) and any event-driven strategy. Our current pipeline uses SEC EDGAR 8-K Item 2.02 text + FinBERT — this page documents better and complementary approaches.

**Key question answered here**: Are there better ways to get earnings dates + EPS surprises than scraping 8-K filings? **Yes — see Recommended Stack below.**

---

## Free / Low-Cost APIs

### Financial Modeling Prep (FMP) — Best Free Tier for PEAD

```
GET https://financialmodelingprep.com/api/v3/earning_calendar
    ?from=YYYY-MM-DD&to=YYYY-MM-DD&apikey=KEY          # max 3-month range
GET https://financialmodelingprep.com/api/v3/historical/earning_calendar/{SYMBOL}
    ?limit=80&apikey=KEY
```

**Free tier**: 250 calls/day. **Paid**: from $19/month.

Returns: symbol, date, epsEstimated, eps (actual), epsSurprise (pre-calculated %), revenueEstimated, revenue, revenueSuprise. The pre-calculated surprise % is the key feature — no manual computation needed.

```python
import requests

def get_fmp_earnings(start: str, end: str, api_key: str) -> list[dict]:
    url = "https://financialmodelingprep.com/api/v3/earning_calendar"
    resp = requests.get(url, params={"from": start, "to": end, "apikey": api_key})
    return resp.json()

def get_fmp_earnings_history(symbol: str, api_key: str, limit: int = 20) -> list[dict]:
    url = f"https://financialmodelingprep.com/api/v3/historical/earning_calendar/{symbol}"
    resp = requests.get(url, params={"limit": limit, "apikey": api_key})
    return resp.json()
```

Key field to compute prior-quarter baseline: iterate historical EPS actuals over 4Q.

---

### Finnhub — Best for Real-Time Future Calendar

**Free tier**: 60 calls/minute. **Paid**: $49+/month.

```python
import finnhub

client = finnhub.Client(api_key=os.environ["FINNHUB_API_KEY"])

# Upcoming earnings for our 30-stock universe
calendar = client.earnings_calendar(
    _from="2026-05-20", to="2026-06-20", symbol=""
)
# Returns: symbol, date, epsActual, epsEstimate, epsSurprisePct, revenueActual, etc.

# Single ticker next earnings
next_date = client.earnings_calendar(_from="2026-05-20", to="2026-08-01", symbol="AAPL")
```

**Advantage over EDGAR**: Returns future earnings dates pre-announced, so pead_overnight.py can build a watchlist days ahead rather than waiting for the 8-K to appear.

---

### yfinance — Historical Earnings (Unreliable for Future Dates)

```python
import yfinance as yf
ticker = yf.Ticker("AAPL")

# Historical earnings dates with EPS estimates and actuals
earnings_df = ticker.get_earnings_dates(limit=8)
# Returns: Earnings Date, EPS Estimate, Reported EPS, Surprise(%)

# Earnings history (annual/quarterly)
earnings_hist = ticker.earnings_history  # dict with quarterly/annual frames
```

**Limitation**: Future earnings dates are unreliable as of 2025 (Yahoo Finance stopped providing forward estimates via the scraping layer). Use FMP or Finnhub for forward dates; yfinance for historical confirmation.

---

### API Ninjas — Best for Timing Data (Pre/After Market)

```
GET https://api.api-ninjas.com/v1/earningscalendar
    ?ticker=AAPL&date_start=2026-05-01&date_end=2026-06-01
Header: X-Api-Key: KEY
```

**Free tier**: 50 requests/day. Returns: `timing` field — `"before_market"`, `"during_market"`, or `"after_market"`. This is the only free API with explicit timing data and is critical for PEAD entry window selection.

```python
import requests

def get_earnings_timing(symbol: str, start: str, end: str) -> list[dict]:
    url = "https://api.api-ninjas.com/v1/earningscalendar"
    headers = {"X-Api-Key": os.environ["API_NINJAS_KEY"]}
    params = {"ticker": symbol, "date_start": start, "date_end": end}
    return requests.get(url, headers=headers, params=params).json()
    # Returns: symbol, fiscalDateEnding, date, eps, epsEstimated, revenue,
    #          revenueEstimated, timing ("before_market" | "after_market" | etc)
```

**PEAD timing logic**:
- `after_market` → plan entry at next-day open (classic PEAD window, gap-up risk)
- `before_market` → gap already priced in; enter at open only if momentum confirms

---

### yahoo-earnings-calendar — Range Queries (Scraper)

```python
from yahoo_earnings_calendar import YahooEarningsCalendar
import datetime

yec = YahooEarningsCalendar()
events = yec.earnings_between(
    datetime.datetime(2026, 5, 20),
    datetime.datetime(2026, 6, 20)
)
# Also: yec.get_next_earnings_date("NVDA")
```

Scrapes Yahoo Finance. No rate limit specification but subject to blocking. Useful as fallback for date lookups.

---

## SEC EDGAR — Structured Approach (Current Method, Enhanced)

### Current Approach (8-K text + FinBERT)

Our `pead_overnight.py` polls SEC EDGAR for Item 2.02 filings, fetches the 8-K text, and runs ProsusAI/FinBERT for sentiment scoring. This is **slower than calendar APIs** for detecting dates but adds semantic richness (tone, guidance language, analyst reaction framing).

### Upgrade: XBRL-Structured EPS Extraction

Many 8-K filings include XBRL-tagged earnings data. Parsing XBRL gives exact EPS without NLP:

```python
from edgar import Company  # pip install edgartools

company = Company("AAPL")  # uses SEC EDGAR CIK lookup
filings = company.get_filings(form="8-K")

for filing in filings[:5]:
    if any("2.02" in item for item in (filing.items or [])):
        # Extract XBRL EPS
        xbrl = filing.xbrl
        if xbrl:
            eps_facts = xbrl.get_facts(concept="us-gaap:EarningsPerShareBasic")
            print(f"  XBRL EPS: {eps_facts}")
        else:
            print(f"  No XBRL; must parse text exhibit")
```

XBRL coverage is ~70–80% of S&P 500 8-Ks. For the remaining ~20%, fall back to FinBERT text parsing.

**EdgarTools** (GitHub: `dgunning/edgartools`, 2.2k stars, MIT):
- Parses 24+ SEC form types
- Auto-standardizes XBRL financial data
- LLM-optimized text extraction
- `pip install edgartools`

**Filing lag**:
- Companies file 8-K simultaneously with (or minutes before) earnings release
- SEC EDGAR real-time API provides sub-second latency
- Practical PEAD pipeline: calendar API → pre-stock the watchlist → 8-K XBRL confirms actual EPS same-minute

---

### SEC Official EDGAR API (Free, Real-Time)

```
GET https://data.sec.gov/submissions/CIK{cik}.json        # recent filings list
GET https://efts.sec.gov/LATEST/search-index?q="8-K"&dateRange=custom&startdt=...  # full-text search
```

Rate limit: 10 requests/second. No auth required. Sub-second latency for recent filings.

---

## Paid Options (Reference)

| Service | Price | Strength |
|---------|-------|---------|
| **Intrinio** | $150–$1,600/mo | Best calendar quality, 15yr history, standardized financials |
| **Wall Street Horizon** | ~$500+/mo | Specializes in *confirmed* event timing; lowest false-positive rate |
| **Benzinga Earnings API** | ~$100+/mo | Real-time, includes surprise metrics + call timing |
| **Nasdaq Data Link** | Varies | 20M+ datasets, many free |
| **Refinitiv LSEG** | $1,500–$3,000+/user/mo | Enterprise; includes analyst consensus |
| **WRDS I/B/E/S** | Institutional contract | Gold standard; every analyst estimate since 1976; requires WRDS subscription |

For our current free-tier constraint: FMP (250 calls/day) + Finnhub (60/min) covers everything needed.

---

## EPS Surprise Calculation

### Formulas

```python
# Basic surprise
surprise_pct = (actual_eps - consensus_eps) / abs(consensus_eps) * 100

# Standardized Unexpected Earnings (SUE) — more robust
# Requires trailing std dev of forecast errors (needs 4+ quarters)
prior_errors = [actual_q[t-i] - estimate_q[t-i] for i in range(1, 5)]
sue = (actual_eps - consensus_eps) / np.std(prior_errors)
# SUE > 1.0 = strong beat; SUE < -1.0 = strong miss
```

Our current `pead_overnight.py` computes a sentiment surprise score from FinBERT vs prior-quarter FinBERT baseline. **FMP already returns epsSurprisePct directly** — consider using that as the primary surprise signal and FinBERT as a sentiment overlay for tone/guidance language.

---

## Recommended PEAD Stack (Hybrid Upgrade Path)

**Current bottlenecks in pead_overnight.py**:
1. Must wait for 8-K to appear (minutes delay vs. pre-announced calendar)
2. FinBERT processes unstructured text (slow; XBRL EPS available instantly for 80% of filings)
3. No explicit timing data → entry timing is imprecise

**Proposed hybrid stack**:

```
Phase 1 (weekly): Finnhub earnings_calendar → 4-week forward watchlist (dates, consensus EPS)
Phase 2 (nightly): FMP historical → actual EPS when available → compute epsSurprisePct
Phase 3 (8-K arrives): EdgarTools XBRL → confirm EPS, extract tone from text → FinBERT
Phase 4 (morning): API Ninjas timing flag → select OPG vs. MOC entry
```

**Cost**: $0/month on free tiers for Phase 1-3. Phase 4 adds API Ninjas ($0 on free tier).

**vs. current approach**: 
- Reduces detection lag from minutes (EDGAR poll) to near-zero (calendar pre-built)
- Adds timing awareness (pre/after-market flag)
- Keeps FinBERT for sentiment overlay (tone/guidance)

**Implementation note**: `$FMP_API_KEY` and `$FINNHUB_API_KEY` (= `$FINNHUB_TOKEN` in env) already present in API access table. API Ninjas requires new key. EdgarTools is MIT-licensed, `pip install edgartools`.

---

## Earnings Transcript Data (For H174 Enhancement)

Beyond press releases — full call transcripts unlock analyst Q&A signals:

| Source | Cost | Notes |
|--------|------|-------|
| **EarningsCall.biz** | Free trial; ~$50+/mo | Full transcripts, API access |
| **Seeking Alpha Transcripts** | Free (manual) | No API; scraping-only |
| **MotleyFool / Fool Transcripts** | Free (manual) | Crowd-sourced, variable quality |
| **Refinitiv** | Enterprise | Best quality, full call |
| **API Ninjas EarningCallTranscript** | Free tier 50/day | Per-ticker JSON transcript |

The PEAD.txt paper (dream cycle 2026-05-22) uses transcript text to build composite 60/40 press-release + transcript score — directly implementable with EarningsCall.biz or API Ninjas transcript endpoint.

---

## Cross-References

- [PEAD-NLP Alpaca Deployment](../paper-trading/pead-nlp-alpaca.md) — live pipeline using current EDGAR approach
- [Event-Driven Strategies](../algorithms/event-driven.md) — H163/H174 hypothesis results; H174 earnings transcript upgrade candidate
- [NLP & Alternative Data](../tools/nlp-alternative-data.md) — FinBERT2 upgrade notes
- [Free / Low-Cost Sources](free-data.md) — broader data source catalog
