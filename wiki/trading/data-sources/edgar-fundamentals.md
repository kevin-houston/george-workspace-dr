---
added: 2026-05-25
updated: 2026-05-25
category: data-sources
---

# SEC EDGAR XBRL Fundamentals

Free, permanent, no API key required. Covers all US public companies from **2009 onward** (when the SEC mandated XBRL tagging). This is the unblock path for H222 (quality factor), which was limited to 5-year yfinance history — EDGAR gives 15+ years of 10-K data.

## Why Use EDGAR for Fundamentals

| Source | History | Cost | Status |
|--------|---------|------|--------|
| SEC EDGAR XBRL | 2009–present | Free | ✅ Active |
| FMP API v3 (legacy) | 2000–present | Paid | ❌ Blocked Aug 2025 |
| yfinance | ~5 years | Free | ✅ Active (limited) |
| Polygon fundamentals | 2004–present | Paid ($29+/mo) | ✅ Active |
| Alpha Vantage | 20 years | Free (25 req/day) | ✅ Active (rate-limited) |

## API Endpoints

All endpoints are at `data.sec.gov`. **No API key needed** — only a `User-Agent` header.

| Endpoint | URL | Purpose |
|----------|-----|---------|
| CompanyFacts | `data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json` | All XBRL facts for a company |
| CompanyConcept | `data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/{taxonomy}/{tag}.json` | Single metric over time |
| Submissions | `data.sec.gov/submissions/CIK{cik10}.json` | Filing history + metadata |
| Company Tickers | `sec.gov/files/company_tickers.json` | Ticker → CIK lookup (all companies) |

- `cik10` = CIK zero-padded to 10 digits (e.g., Apple = `0000320193`)
- taxonomy = `us-gaap` for standard financials, `dei` for entity info

### Rate Limits

- **10 requests/second per IP** — add 0.12s sleep between calls
- No daily limit documented
- 403 if User-Agent header is missing or invalid
- Format: `"MyApp admin@example.com"` (company name + contact email)

## Key us-gaap Tags

Companies don't always use the same tag. The table below shows the primary tag and fallback alternatives in priority order. Always try the primary first, then iterate through alternatives.

### Income Statement

| Concept | Primary Tag | Alternatives |
|---------|-------------|-------------|
| Revenue | `RevenueFromContractWithCustomerExcludingAssessedTax` | `Revenues`, `SalesRevenueNet`, `SalesRevenueGoodsNet`, `RevenueFromContractWithCustomerIncludingAssessedTax` |
| Gross Profit | `GrossProfit` | (usually consistent) |
| COGS | `CostOfGoodsAndServicesSold` | `CostOfRevenue`, `CostOfGoodsSold` |
| Net Income | `NetIncomeLoss` | `ProfitLoss`, `NetIncome`, `NetIncomeLossAvailableToCommonStockholdersBasic` |
| Operating Income | `OperatingIncomeLoss` | (consistent) |
| EPS Basic | `EarningsPerShareBasic` | (consistent) |

### Balance Sheet

| Concept | Primary Tag | Alternatives |
|---------|-------------|-------------|
| Total Assets | `Assets` | (consistent) |
| Current Assets | `AssetsCurrent` | (consistent) |
| Current Liabilities | `LiabilitiesCurrent` | (consistent) |
| Long-term Debt | `LongTermDebt` | `LongTermDebtAndCapitalLeaseObligation` |
| Total Liabilities | `Liabilities` | (consistent) |
| Stockholders Equity | `StockholdersEquity` | `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |
| Shares Issued | `CommonStockSharesIssued` | `CommonStockSharesOutstanding` |

### Cash Flow Statement

| Concept | Primary Tag | Alternatives |
|---------|-------------|-------------|
| Operating CF | `NetCashProvidedByUsedInOperatingActivities` | (consistent) |
| CapEx | `PaymentsToAcquirePropertyPlantAndEquipment` | `CapitalExpendituresIncurredButNotYetPaid` |
| Free Cash Flow | not in XBRL (compute: Operating CF − CapEx) | — |

## Python Implementation

### CIK Lookup

```python
import requests, time

HEADERS = {"User-Agent": "ResearchBot admin@example.com"}

def build_ticker_cik_map() -> dict[str, str]:
    """Returns {ticker: cik_padded} for all SEC-registered companies."""
    url = "https://www.sec.gov/files/company_tickers.json"
    data = requests.get(url, headers=HEADERS, timeout=30).json()
    return {
        v["ticker"].upper(): str(v["cik_str"]).zfill(10)
        for v in data.values()
    }

TICKER_TO_CIK = build_ticker_cik_map()  # cache this — ~50KB, stable
```

### Fetch All Facts for a Company

```python
def get_company_facts(cik10: str) -> dict:
    """Returns full XBRL facts JSON — all metrics, all years, all forms."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    time.sleep(0.12)  # stay under 10 req/s
    return r.json()
```

### Extract Annual 10-K Values with Fallbacks

```python
def extract_annual(facts: dict, *tags: str) -> dict[int, float]:
    """
    Try tags in order; return {fiscal_year: value} for annual 10-K filings.
    Deduplicates multiple amendments — keeps the most recently filed value.
    """
    for tag in tags:
        try:
            entries = facts["facts"]["us-gaap"][tag]["units"]["USD"]
        except KeyError:
            continue
        
        # Keep only annual (FY) 10-K filings
        annual = [e for e in entries
                  if e.get("form") == "10-K" and e.get("fp") == "FY"]
        if not annual:
            continue
        
        # Deduplicate: multiple 10-K/A amendments → keep latest filed
        by_year: dict[int, dict] = {}
        for e in annual:
            yr = e.get("fy")
            if yr and (yr not in by_year or e["filed"] > by_year[yr]["filed"]):
                by_year[yr] = e
        
        return {yr: e["val"] for yr, e in sorted(by_year.items())}
    
    return {}


# Usage:
# revenue = extract_annual(facts,
#     "RevenueFromContractWithCustomerExcludingAssessedTax",
#     "Revenues", "SalesRevenueNet")
```

### Shares Outstanding (non-USD unit)

```python
def extract_annual_shares(facts: dict) -> dict[int, float]:
    """Shares use 'shares' unit key, not 'USD'."""
    for tag in ("CommonStockSharesOutstanding", "CommonStockSharesIssued"):
        try:
            entries = facts["facts"]["us-gaap"][tag]["units"]["shares"]
        except KeyError:
            continue
        annual = [e for e in entries
                  if e.get("form") == "10-K" and e.get("fp") == "FY"]
        by_year = {}
        for e in annual:
            yr = e.get("fy")
            if yr and (yr not in by_year or e["filed"] > by_year[yr]["filed"]):
                by_year[yr] = e
        if by_year:
            return {yr: e["val"] for yr, e in sorted(by_year.items())}
    return {}
```

### Full Fundamentals Builder (Piotroski / Quality Factor)

```python
import json
from pathlib import Path
import numpy as np, pandas as pd

CACHE_DIR = Path("backtesting/cache")

PIOTROSKI_TAGS = {
    "revenue":    ("RevenueFromContractWithCustomerExcludingAssessedTax",
                   "Revenues", "SalesRevenueNet"),
    "gross_profit": ("GrossProfit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss"),
    "total_assets": ("Assets",),
    "cur_assets":   ("AssetsCurrent",),
    "cur_liab":     ("LiabilitiesCurrent",),
    "ltd":          ("LongTermDebt", "LongTermDebtAndCapitalLeaseObligation"),
    "cfo":          ("NetCashProvidedByUsedInOperatingActivities",),
}


def build_fundamentals(ticker: str, cik_map: dict) -> pd.DataFrame:
    cik = cik_map.get(ticker.upper())
    if not cik:
        return pd.DataFrame()
    
    cp = CACHE_DIR / f"edgar_{ticker}_facts.json"
    if cp.exists():
        with open(cp) as f:
            facts = json.load(f)
    else:
        facts = get_company_facts(cik)
        with open(cp, "w") as f:
            json.dump(facts, f)
    
    rows = {}
    for field, tags in PIOTROSKI_TAGS.items():
        for yr, val in extract_annual(facts, *tags).items():
            rows.setdefault(yr, {})[field] = val
    
    # Shares separately (non-USD)
    for yr, val in extract_annual_shares(facts).items():
        rows.setdefault(yr, {})["shares"] = val
    
    if not rows:
        return pd.DataFrame()
    
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    df.index.name = "fiscal_year"
    
    # Derived metrics
    ta = df["total_assets"].replace(0, np.nan)
    df["roa"]            = df["net_income"] / ta
    df["cfo_a"]          = df["cfo"] / ta
    df["leverage"]       = df["ltd"] / ta
    df["current_ratio"]  = df["cur_assets"] / df["cur_liab"].replace(0, np.nan)
    df["gross_margin"]   = df["gross_profit"] / df["revenue"].replace(0, np.nan)
    df["asset_turnover"] = df["revenue"] / ta
    df["gp_assets"]      = df["gross_profit"] / ta
    
    return df
```

### Batch Fetch (30 stocks ≈ 4 minutes at 0.12s/call)

```python
def build_fundamental_db(universe: list[str]) -> dict[str, pd.DataFrame]:
    cik_map = build_ticker_cik_map()
    db = {}
    for i, tk in enumerate(universe):
        try:
            df = build_fundamentals(tk, cik_map)
            if not df.empty:
                db[tk] = df
                yr_range = f"FY{df.index.min()}–{df.index.max()}"
                print(f"  ✓ {tk}: {len(df)} years ({yr_range})")
        except Exception as e:
            print(f"  ✗ {tk}: {e}")
    return db
```

## Data Quality Notes

- **History depth:** 2009–present for US-GAAP filers; some companies have pre-2009 data via voluntary early adoption
- **Fiscal year alignment:** `fy` field is the calendar year the fiscal year *ends in*. AAPL FY ending Sep 2024 has `fy=2024`
- **Multiple filings per year:** 10-K/A amendments are common. Always deduplicate using the `filed` date — use the most recently filed value
- **Tag inconsistency:** Revenue and COGS tags vary most across companies and industries. Banks/insurance use different taxonomies (ASC 606 adoption affected tags post-2018)
- **Non-GAAP companies:** Foreign private issuers (ADRs) use `ifrs-full` taxonomy instead of `us-gaap`
- **Bulk download:** For 500+ company pipelines, use `https://data.sec.gov/api/xbrl/companyfactsarchive.zip` (updated daily, ~4GB compressed) instead of individual API calls

## Using EdgarTools (Higher-Level Library)

```bash
pip install edgartools
```

```python
from edgar import Company

aapl = Company("AAPL")
facts = aapl.get_facts()

# Get revenue series as DataFrame
revenue_df = facts.to_pandas("us-gaap:Revenues")

# Or get a 10-K filing directly
filing = aapl.get_filings(form="10-K").latest()
xbrl = filing.xbrl()
income_stmt = xbrl.income_statement()
```

EdgarTools pros: higher-level API, handles tag variations automatically  
EdgarTools cons: slower, less control, may lag on newest filings

## Application to H222 (Quality Factor)

To run H222 with full 15-year IS/OOS history:

```python
# 1. Build fundamentals for all 30 universe stocks
UNIVERSE = ["AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
            "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
            "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM"]
db = build_fundamental_db(UNIVERSE)

# 2. Compute Piotroski F-Score for each year
# See run_h222.py — swap yfinance fetch_fundamentals_yf() 
# with edgar build_fundamentals() above

# Expected IS: 2010-2020 (10yr), OOS: 2021-2026 (5yr)
# Each stock should have FY2009+ data available
```

## Rate Limit Strategy for 30 Stocks

```python
# 30 stocks × 1 CompanyFacts call = 30 calls total
# At 0.12s/call = 3.6 seconds with cache miss
# After first run: all cached, 0 API calls

# For 500-stock universe: use companyfactsarchive.zip instead
import zipfile, io
r = requests.get("https://data.sec.gov/api/xbrl/companyfactsarchive.zip",
                 headers=HEADERS, stream=True)
# Streams ~4GB — extract only needed CIKs
```

## Related Pages

- [Free / Low-Cost Sources](free-data.md) — yfinance, Tiingo, FRED
- [Quality Factor (QMJ)](../algorithms/quality-factor.md) — H222 uses EDGAR fundamentals
- [Earnings Calendar & Corporate Events](earnings-events.md) — EDGAR 8-K and XBRL EPS
- [Point-in-Time Constituent & Vintage Data Sources](point-in-time-constituents.md) — this page's `filed`-date dedup logic is already vintage-aware fundamentals; see the provider table for point-in-time *index membership* to pair with it ← new 2026-08-06
