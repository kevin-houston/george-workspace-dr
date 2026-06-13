---
added: 2026-06-12
updated: 2026-06-12
category: data-source
relevance: H279 (LLM momentum filter), H280 (MarketSenseAI), H281 (macro-LLM ETF), PEAD/NLP pipeline, H185 (prediction markets nowcasting)
---

# Alternative Data Sources

Non-traditional signals beyond price/volume and financial statements. The alternative data market grew to ~$12B in 2025, with 78% penetration among hedge funds. This page catalogs free and low-cost sources accessible from the current stack, plus a curated landscape of institutional-grade providers.

**Related pages**: [NLP & Alternative Data Tools](../tools/nlp-alternative-data.md) — FinBERT/SEC filing libraries | [Free Data Sources](free-data.md) — price/macro free tiers | [EDGAR Fundamentals](edgar-fundamentals.md) — fundamentals from SEC

---

## Tier 0: Already Available (Keys in Env)

### NewsAPI (`$NEWSAPI_KEY`)

**URL**: https://newsapi.org  
**Free tier**: 500 req/day, 1-month history  
**Paid**: $35+/mo for commercial use and longer history

Aggregates 70,000+ news sources. Returns title, description, source, published_at per article. Best for keyword-based news flow on specific tickers or themes.

```python
import os
import requests
from datetime import datetime, timedelta

NEWSAPI_KEY = os.environ["NEWSAPI_KEY"]

def get_ticker_news(ticker: str, days_back: int = 3) -> list[dict]:
    """Fetch recent news articles mentioning a ticker symbol."""
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    r = requests.get("https://newsapi.org/v2/everything", params={
        "q": ticker,
        "from": from_date,
        "sortBy": "relevancy",
        "language": "en",
        "pageSize": 50,
        "apiKey": NEWSAPI_KEY,
    }, timeout=15)
    r.raise_for_status()
    return r.json().get("articles", [])

def get_market_news(query: str = "earnings surprise stock", days_back: int = 1) -> list[dict]:
    """Fetch market-wide news for a topic."""
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    r = requests.get("https://newsapi.org/v2/everything", params={
        "q": query,
        "from": from_date,
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 100,
        "apiKey": NEWSAPI_KEY,
    }, timeout=15)
    r.raise_for_status()
    return r.json().get("articles", [])

# Pipeline: NewsAPI → FinBERT scoring → aggregate sentiment index
# Use this for pre-earnings news flow check (last 3 days before earnings date)
```

**Limitation**: NewsAPI developer plan blocks sources for commercial use; upgrade to Business ($449/mo) for production. Free plan suitable for research and PEAD pipeline development.

**Signal design**: News volume spike (>2σ above 30d avg) + positive FinBERT score = reinforcing PEAD signal. News silence before earnings = uncertainty, higher reversal risk.

---

### Finnhub (social sentiment, congressional data, insider MSPR)

**URL**: https://finnhub.io  
**Free tier**: 60 calls/min, 1yr news history, social sentiment, congressional trades  
**Paid**: $50+/mo for extended history and premium endpoints  
**Install**: `pip install finnhub-python`

Finnhub is the best free-tier provider for alternative signals — social sentiment, insider MSPR (net buy/sell score), congressional trading, government contracts, and ESG all on the free plan.

```python
import finnhub
import os

fc = finnhub.Client(api_key="demo")  # replace with real key if you add one
# Note: Finnhub API key is separate from env vars above — use demo key for testing
# or register free at finnhub.io

# --- Company news with sentiment ---
def get_company_news(ticker: str, days_back: int = 7) -> list[dict]:
    from datetime import date, timedelta
    from_d = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    to_d = date.today().strftime("%Y-%m-%d")
    return fc.company_news(ticker, _from=from_d, to=to_d)
    # each item has: headline, summary, datetime, sentiment fields

# --- Social sentiment (Reddit, StockTwits, Twitter aggregate) ---
def get_social_sentiment(ticker: str) -> dict:
    """Returns reddit/twitter mention volume + sentiment score."""
    return fc.stock_social_sentiment(ticker)
    # {"reddit": [{"atTime": "...", "mention": N, "positiveScore": X, ...}],
    #  "twitter": [...]}

# --- Insider MSPR (net buy/sell ratio per month) ---
def get_insider_sentiment(ticker: str, from_date: str, to_date: str) -> dict:
    """
    MSPR = Monthly Share Purchase Ratio.
    Formula: net_buy / (net_buy + net_sell). Range: [-1, +1]
    +1 = all purchases, -1 = all sales.
    Studies show MSPR > 0.6 predicts next-month +1.2% alpha.
    """
    return fc.stock_insider_sentiment(ticker, from_date, to_date)

# --- Congressional trading (STOCK Act disclosures) ---
def get_congressional_trades(ticker: str) -> list[dict]:
    """Returns House + Senate STOCK Act disclosures."""
    return fc.stock_congressional_trading(ticker)
    # [{"symbol": "AAPL", "name": "Representative X", "transaction": "purchase",
    #   "transactionDate": "2025-11-12", "filingDate": "...", "amount": ">$1,000,000"}]

# --- Government contracts ---
def get_gov_contracts(ticker: str) -> list[dict]:
    return fc.stock_gov_spending(ticker)
```

**Key signals from Finnhub**:
| Signal | Endpoint | Alpha evidence |
|--------|----------|---------------|
| Social sentiment | `stock_social_sentiment` | WSB mention spike: event-driven momentum |
| MSPR | `stock_insider_sentiment` | Insider net buy → +1.2%/mo alpha (Seyhun 1998 updated) |
| Congressional trades | `stock_congressional_trading` | Leadership committee members: ~47% annualized (pre-STOCK Act era); post-2012 edge reduced but cluster buys still signal |
| Gov contracts | `stock_gov_spending` | Contract wins predict revenue surprise for defense/tech |

---

## Tier 1: Free Public APIs (No Key Required)

### ApeWisdom — Reddit/4chan Mention Tracking

**URL**: https://apewisdom.io  
**API**: https://apewisdom.io/api/v1.0/  
**Auth**: None required  
**Cost**: Free  
**Update frequency**: Every ~2 hours

Tracks mention volume and upvotes across r/wallstreetbets, r/stocks, r/options, r/investing, r/SPACs, and 4chan /biz/. No API key — just GET requests.

```python
import requests

BASE = "https://apewisdom.io/api/v1.0"

def get_trending_stocks(filter_type: str = "wallstreetbets", page: int = 1) -> list[dict]:
    """
    filter_type options: 'wallstreetbets', 'stocks', 'options', 'investing',
                         'all-stocks', 'all-crypto', 'all'
    Returns top 100 tickers by mentions in last 24h.
    """
    r = requests.get(f"{BASE}/filter/{filter_type}/page/{page}", timeout=10)
    r.raise_for_status()
    data = r.json()
    return data["results"]

def get_ticker_rank(ticker: str, filter_type: str = "all-stocks") -> dict | None:
    """Check if a ticker is in top 100 trending and return its rank/mentions."""
    results = get_trending_stocks(filter_type)
    for item in results:
        if item["ticker"].upper() == ticker.upper():
            return item
    return None

# Response format per ticker:
# {
#   "rank": 3,
#   "ticker": "NVDA",
#   "name": "NVIDIA Corporation",
#   "mentions": 847,
#   "upvotes": 12043,
#   "rank_24h_ago": 5,        # rank yesterday
#   "mentions_24h_ago": 312   # mentions yesterday
# }

def mention_spike(ticker: str) -> float:
    """Returns ratio of today_mentions / yesterday_mentions. >2.0 = spike."""
    item = get_ticker_rank(ticker)
    if item and item.get("mentions_24h_ago", 0) > 0:
        return item["mentions"] / item["mentions_24h_ago"]
    return 1.0
```

**Signal design**: Mention spike ratio >2× + top-20 rank = retail momentum catalyst. Use as supplementary filter on PEAD entries or H279 LLM momentum positions.

**Limitation**: No historical data beyond 24-hour comparison. No sentiment scores (mentions only). For historical Reddit data, use Quiver Quantitative (paid).

---

### Congressional Stock Trades — Free S3 Feed

**URL**: https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json  
**Auth**: None  
**Cost**: Free  
**Update**: Daily  
**History**: ~2019–present

```python
import json
import urllib.request
from datetime import datetime, timedelta

HOUSE_URL = "https://house-stock-watcher-data.s3-us-west-2.amazonaws.com/data/all_transactions.json"

def fetch_congress_trades(days_back: int = 45, min_tier: str = "$15,001 - $50,000") -> list[dict]:
    """
    Fetch House STOCK Act disclosures.
    min_tier filters by minimum dollar range bracket.
    """
    TIERS = [
        "$1,001 - $15,000",
        "$15,001 - $50,000",
        "$50,001 - $100,000",
        "$100,001 - $250,000",
        "$250,001 - $500,000",
        "$500,001 - $1,000,000",
        "$1,000,001 - $5,000,000",
        "$5,000,001 - $25,000,000",
    ]
    min_idx = TIERS.index(min_tier)
    valid = set(TIERS[min_idx:])
    cutoff = datetime.now() - timedelta(days=days_back)
    
    with urllib.request.urlopen(HOUSE_URL, timeout=30) as resp:
        trades = json.loads(resp.read())
    
    return [
        t for t in trades
        if t.get("amount") in valid
        and t.get("transaction_date", "") >= cutoff.strftime("%Y-%m-%d")
    ]

def find_cluster_buys(trades: list[dict], window_days: int = 14) -> dict[str, list]:
    """
    Find tickers with ≥3 purchase disclosures within window_days.
    Cluster buys historically outperform individual trades.
    """
    from collections import defaultdict
    purchases: dict[str, list] = defaultdict(list)
    for t in trades:
        if t.get("type") == "purchase" and t.get("ticker"):
            purchases[t["ticker"].upper()].append(t)
    return {t: ps for t, ps in purchases.items() if len(ps) >= 3}
```

**Alpha evidence**: Pre-STOCK Act (pre-2012) studies found ~12% annual abnormal returns. Post-2012, edge greatly reduced — but "cluster buys" (≥3 members, same ticker, <14 days) and committee-relevant trades retain ~4–8% annual alpha in recent studies. Leadership position holders still show ~47% annualized in older datasets. Best used as a conviction filter, not a standalone signal.

---

### Google Trends — `pytrends`

**URL**: https://trends.google.com  
**Python**: `pip install pytrends`  
**Auth**: None (unofficial API)  
**Cost**: Free  
**Caveat**: Rate-limited, can be temporarily blocked under sustained use

Google Trends data predicts investor attention and information diffusion. Academic finding (arXiv:1403.1715): trend-based strategies produce ~17 bps/week alpha — modest but real. Best use is as an attention proxy for momentum and PEAD filtering.

```python
from pytrends.request import TrendReq
import pandas as pd
import time

def get_search_trend(ticker: str, company_name: str,
                     timeframe: str = "today 3-m",
                     geo: str = "US") -> pd.Series:
    """
    Returns weekly search interest index (0-100 relative) for past 3 months.
    Use company_name not ticker for better coverage ("Apple Inc" not "AAPL").
    """
    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([company_name], timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()
    if df.empty:
        return pd.Series(dtype=float)
    return df[company_name]

def search_momentum_signal(ticker: str, company_name: str) -> float:
    """
    Returns 4-week change in search interest normalized by 52-week avg.
    Positive = rising attention = momentum amplifier.
    """
    series = get_search_trend(company_name, company_name, timeframe="today 12-m")
    if len(series) < 8:
        return 0.0
    recent_4wk = series.iloc[-4:].mean()
    baseline = series.iloc[:-4].mean()
    return (recent_4wk - baseline) / (baseline + 1e-9)  # normalized change

# Practical usage note: pytrends returns relative values (0-100), not absolute.
# A score of 80 means 80% of peak search interest. Combine with yfinance price
# momentum for confirming signals.

# Rate limit workaround: add delays between calls
def safe_trends(tickers_companies: list[tuple[str, str]]) -> dict[str, float]:
    results = {}
    for ticker, name in tickers_companies:
        results[ticker] = search_momentum_signal(ticker, name)
        time.sleep(2)   # avoid rate limits
    return results
```

**Academic findings on Google Trends alpha**:
- Da et al. (2011, RFS): ASVI (abnormal search volume index) predicts next 2-week return +1.2% for high-ASVI stocks
- Preis et al. (2013, Scientific Reports): search volume on "debt" predicts S&P 500 declines
- Statistical preprocessing (arXiv:2504.07032, 2025): raw pytrends data degrades model performance; detrending + smoothing required for reliable signals
- Best use case: confirming momentum stocks with rising search interest vs. just price momentum

---

### Wikipedia Page Views — Wikimedia API

**URL**: https://wikimedia.org/api/rest_v1/  
**Auth**: None  
**Cost**: Free  
**History**: 2015–present (daily granularity)

Wikipedia views capture institutional-grade investor attention — academic studies show weekly-rebalanced long/short strategies based on page-view changes generate significant alpha (the "Wikipedia Effect").

```python
import requests
import pandas as pd
from datetime import datetime, timedelta

def get_wiki_views(article: str, days_back: int = 90,
                   project: str = "en.wikipedia") -> pd.DataFrame:
    """
    Get daily Wikipedia page view counts.
    article: Wikipedia page title (e.g. "Apple_Inc." not "AAPL")
    """
    end = datetime.now()
    start = end - timedelta(days=days_back)
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{project}/all-access/user/{article}/daily/"
        f"{start.strftime('%Y%m%d')}/{end.strftime('%Y%m%d')}"
    )
    r = requests.get(url, timeout=15,
                     headers={"User-Agent": "trading-research/1.0 research@example.com"})
    if r.status_code != 200:
        return pd.DataFrame()
    items = r.json().get("items", [])
    df = pd.DataFrame(items)[["timestamp", "views"]]
    df["date"] = pd.to_datetime(df["timestamp"], format="%Y%m%d00")
    return df.set_index("date")[["views"]]

def wiki_attention_signal(article: str) -> float:
    """
    Returns 7-day rolling avg view change vs 30-day baseline.
    >1.5 = rising attention (positive momentum signal).
    """
    df = get_wiki_views(article, days_back=40)
    if len(df) < 14:
        return 1.0
    recent = df["views"].iloc[-7:].mean()
    baseline = df["views"].iloc[-37:-7].mean()
    return recent / (baseline + 1)

# Ticker-to-article mapping (requires curation — Wikipedia titles vary):
TICKER_TO_WIKI = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "TSLA": "Tesla,_Inc.",
    "GOOGL": "Alphabet_Inc.",
    "META": "Meta_Platforms",
    "AMZN": "Amazon_(company)",
    "JPM": "JPMorgan_Chase",
}
```

**Academic support**: "The Wikipedia Effect" study (Quiver data, 2016–2023): H-M-L portfolio on weekly view-change ranks generates statistically significant alpha unexplained by Fama-French factors. Industries with highest attention: telecom, consumer durables, high-tech. Weekly rebalancing is key — daily frequency degrades signal.

---

## Tier 2: Low-Cost APIs ($25–$50/month)

### Quiver Quantitative — Alternative Data Aggregator

**URL**: https://api.quiverquant.com  
**Cost**: $30/mo basic, ~$300/yr  
**Install**: `pip install quiverquant`  
**Coverage**: ~6,000 US stocks  
**Update**: Nightly

Best single source for unconventional signals: congressional trades (with historical depth), Reddit WSB mentions back to 2018, Wikipedia views, off-exchange short volume, lobbying, and patents — all in one normalized API.

```python
import quiverquant
import os

# API token from quiverquant.com dashboard
quiver = quiverquant.quiver("<YOUR_TOKEN>")

# Congressional trading (full history, House + Senate)
congress = quiver.congress_trading("NVDA")
# [{"Date": "2025-11-12", "Politician": "Rep. X", "Transaction": "Purchase",
#   "Amount": "$250,001 - $500,000", "Party": "D", "Chamber": "House"}]

# Reddit WSB mentions + sentiment (back to Aug 2018)
wsb = quiver.wallstreetbets("GME")
# [{"Date": "2021-01-27", "Mentions": 3451, "Rank": 1, "Sentiment": 0.73}]

# Wikipedia views
wiki = quiver.wikipedia("TSLA")
# [{"Date": "2025-12-01", "Views": 48231, "PageName": "Tesla, Inc."}]

# Off-exchange short volume (dark pools + OTC)
short_vol = quiver.offexchange("SPY")
# Short volume as % of total — spikes can signal institutional positioning

# Government contracts
contracts = quiver.gov_contracts("LMT")
# [{"Date": "2025-10-15", "Agency": "DOD", "Amount": 180000000, ...}]

# Corporate lobbying spend
lobbying = quiver.lobbying("META")
# [{"QuarterEnding": "2025-09-30", "Amount": 4200000, "Issue": "Privacy"}]

# Insider transactions (Form 4)
insiders = quiver.insiders("AAPL")

# 13F changes (institutional buys/sells from quarterly filings)
inst = quiver.sec13FChanges(ticker="AMZN")
```

**Signal quality notes**:
- WSB dataset is the most reliable retail sentiment source with long history
- Congressional cluster buy signal: ≥3 same-ticker purchases within 14 days
- Short volume spikes (>60% of total volume) often precede price drops
- Government contract awards are clean, ticker-matched signal for defense/tech

---

### Alpha Vantage NEWS_SENTIMENT (`$ALPHA_VANTAGE_API_KEY`)

**Already have key in env.** The `NEWS_SENTIMENT` endpoint (premium) provides per-article sentiment scores and topic tagging for US equities.

```python
import requests, os

def get_news_sentiment(ticker: str, limit: int = 50) -> list[dict]:
    """
    Returns recent news with per-article sentiment scores.
    Premium endpoint — requires upgraded plan beyond free 25 req/day.
    Each article includes: overall_sentiment_score, overall_sentiment_label,
    ticker_sentiment (per-ticker relevance score + sentiment).
    """
    r = requests.get("https://www.alphavantage.co/query", params={
        "function": "NEWS_SENTIMENT",
        "tickers": ticker,
        "limit": limit,
        "apikey": os.environ["ALPHA_VANTAGE_API_KEY"],
    }, timeout=15)
    data = r.json()
    return data.get("feed", [])

# Response article structure:
# {
#   "title": "...",
#   "url": "...",
#   "time_published": "20251215T143000",
#   "overall_sentiment_score": 0.234,    # -1 to +1
#   "overall_sentiment_label": "Somewhat-Bullish",
#   "ticker_sentiment": [
#     {"ticker": "AAPL", "relevance_score": "0.891", "ticker_sentiment_score": "0.312"}
#   ]
# }
```

**Note**: The free plan's 25 req/day is sufficient for PEAD pipeline (check sentiment on ~5 tickers/night). If NEWS_SENTIMENT endpoint is blocked on current plan tier, fall back to NewsAPI + FinBERT scoring pipeline.

---

## Tier 3: Institutional-Grade (Reference Only)

These providers are standard for hedge funds but priced well above the current project's budget. Listed for completeness and future reference.

| Provider | Data Type | Est. Price | Alpha Evidence |
|----------|-----------|-----------|----------------|
| **RavenPack** | News analytics, event extraction | Enterprise ($50k+/yr) | 38k companies, 143 countries; validated Sharpe uplift in quant literature |
| **Earnest Analytics** | Credit/debit card transaction data | Enterprise | "~16%/yr" long-short on earnings surprises, 90% accuracy claim |
| **Second Measure** (Bloomberg) | Consumer spend by company | Bloomberg Terminal | Revenue nowcast 2-3 weeks before earnings; Bloomberg integration |
| **Orbital Insight** | Satellite imagery (parking lots, oil tanks) | Enterprise | Physical activity tracking; oil tank studies confirm commodity edge |
| **Thinknum** | Job postings, LinkedIn counts, app ratings | $5k–$15k/yr | 4,600+ companies, 35+ web-scraped feeds |
| **Social Market Analytics** | Twitter/X sentiment (60-second latency) | Quote-only | History to 2011; fastest social update of any provider |
| **Adanos** | Reddit + X + news + Polymarket combined | $29/$299/mo | 35,000+ tickers; multi-source in one schema; cheapest multi-source |
| **Planet Labs / Maxar** | Satellite imagery | Enterprise | Raw imagery; requires CV pipeline on top |
| **Spire Global / MarineTraffic** | Ship AIS tracking | $500+/mo | Commodity supply chain; oil tanker fill levels |
| **YipitData** | Multi-source alt data research | Enterprise | Credit card + web + app usage synthesized |

**Budget path**: Adanos at $29/mo is the cheapest entry into multi-source social sentiment with commercial licensing. Quiver at $30/mo provides the best depth for retail-accessible congressional/insider/social data.

---

## Signal Taxonomy & Strategy Mapping

| Signal Type | Best Free Source | Best Paid Source | Strategy Fit |
|------------|-----------------|-----------------|-------------|
| News flow/sentiment | NewsAPI + FinBERT | RavenPack | PEAD filter, event-driven |
| Social mentions | ApeWisdom (Reddit free) | Quiver ($30/mo) | Momentum catalyst detection |
| Insider MSPR | Finnhub (free tier) | Quiver | Entry confirmation |
| Congressional trades | Free S3 JSON | Quiver (full history) | Event-driven alpha, cluster signal |
| Government contracts | Finnhub (free tier) | Quiver | Defense/tech sector catalyst |
| Investor attention | Wikipedia API (free) | Quiver (normalized) | Momentum amplifier |
| Search trends | pytrends (free) | Google Trends API ($) | Attention proxy |
| Card transaction data | N/A (institutional only) | Earnest / 1010data | Earnings surprise nowcast |
| Satellite/geospatial | N/A (institutional only) | Orbital Insight | Retail traffic, commodities |

---

## Integration Patterns for H-Series Hypotheses

### H279 (LLM momentum filter): Adding attention layer

```python
# Combine price momentum with search attention + social mentions
def h279_attention_augmented_score(ticker: str, company: str,
                                   momentum_score: float) -> float:
    """
    Augment 12-1 month momentum with attention signals.
    Higher attention amplifies momentum signal.
    """
    # Wikipedia attention
    wiki_ratio = wiki_attention_signal(TICKER_TO_WIKI.get(ticker, ticker))
    
    # Reddit mention spike
    wsb_spike = mention_spike(ticker)
    
    # Composite attention multiplier
    attention = (0.5 * min(wiki_ratio, 3.0) + 0.5 * min(wsb_spike, 3.0))
    
    # Blend: keep momentum dominant, use attention as tiebreaker
    return momentum_score * (0.8 + 0.2 * (attention - 1.0))
```

### PEAD pipeline: News sentiment pre-filter

```python
# Before running FinBERT on 8-K, check news flow
def pead_news_context(ticker: str, event_date: str) -> dict:
    """
    Check news volume and sentiment in 3 days before earnings.
    Use to weight confidence in FinBERT score.
    """
    articles = get_ticker_news(ticker, days_back=3)
    if not articles:
        return {"volume": 0, "sentiment": 0.0}
    
    # Quick headline sentiment using positive/negative word counts
    positive_words = {"beat", "exceed", "surpass", "strong", "record", "growth"}
    negative_words = {"miss", "disappoint", "weak", "decline", "cut", "loss"}
    
    scores = []
    for a in articles:
        headline = (a.get("title", "") + " " + a.get("description", "")).lower()
        pos = sum(1 for w in positive_words if w in headline)
        neg = sum(1 for w in negative_words if w in headline)
        if pos + neg > 0:
            scores.append((pos - neg) / (pos + neg))
    
    return {
        "volume": len(articles),
        "sentiment": sum(scores) / len(scores) if scores else 0.0,
    }
```

---

## Data Quality Caveats

1. **Congressional disclosure lag**: STOCK Act requires filing within 45 days. Median lag ~25 days in practice. Trade by the filing date, not the transaction date — the transaction date is stale by definition.

2. **Reddit survivorship bias**: ApeWisdom and Quiver WSB data only track currently-tracked tickers. Historical meme stock frenzies may look stronger in hindsight because losing tickers drop from tracking.

3. **Google Trends relative scaling**: pytrends returns normalized indices (0–100) relative to peak within the time window. Cross-ticker comparison requires careful normalization. Raw trends *degrade* model performance without preprocessing — detrend and smooth before use.

4. **Wikipedia article mapping**: Ticker → Wikipedia title mapping is not standardized. "GOOG" and "GOOGL" both map to "Alphabet Inc." — build a curated mapping table. Avoid auto-mapping via API lookup (error-prone for subsidiaries, holding companies).

5. **NewsAPI commercial restriction**: Free and Developer plans prohibit commercial use. Research use only until upgrading to Business tier.

6. **Alternative data correlation with price**: Many alt data signals are partially captured by price already. Always test incremental alpha vs. a price-only baseline. The strongest alternative data (credit card transactions, satellite) have <0.3 correlation with price momentum — the cheapest sources (news, social) have 0.5–0.7 correlation.
