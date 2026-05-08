---
updated: 2026-05-08
type: data-source
status: active
relevance: H181 (industry-adjusted reversal), H156 (stock momentum), H157 (sector ETF rotation)
---

# Sector & Industry Classification Data Sources

For strategies that require grouping stocks by sector or industry (industry-adjusted reversal, sector-neutral momentum, factor attribution), reliable classification data is critical. This page covers free and low-cost options, their limitations, and the best practical approach for backtesting.

**Related pages**: [Short-Term Reversal](../algorithms/short-term-reversal.md) — H181 uses these codes | [Free Data Sources](free-data.md) | [Polygon.io](polygon.md)

---

## Classification Systems

| System | Owner | Depth | Standard Use |
|--------|-------|-------|-------------|
| **GICS** (Global Industry Classification Standard) | MSCI + S&P | 4 levels: Sector → Industry Group → Industry → Sub-Industry | Index construction, institutional research |
| **SIC** (Standard Industrial Classification) | US Government (SEC) | 4-digit codes, ~1000 divisions | SEC filings, regulatory |
| **NAICS** (North American Industry Classification) | US/CA/MX gov | Replaced SIC for census, not widely used in finance | Government stats |
| **Custom** | Bloomberg, FMP, Refinitiv | Varies | Vendor-specific |

For backtesting, **GICS is preferred** because sector ETFs (XLK, XLV, etc.) map to GICS sectors. SIC is a free alternative — use SIC-to-GICS mapping table.

---

## Source 1: SEC EDGAR — Free, Bulk, Point-in-Time SIC Codes ★★★★★

**Best free option for historical backtesting.** The SEC maintains SIC codes for every registered company. No API key required.

```python
import requests
import json

EDGAR_HEADERS = {"User-Agent": "your-name your@email.com"}

def get_cik(ticker: str) -> str:
    """Get SEC CIK from ticker symbol."""
    url = "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&forms=10-K".format(ticker)
    # Simpler: use the company tickers JSON
    tickers_url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(tickers_url, headers=EDGAR_HEADERS)
    data = r.json()
    for entry in data.values():
        if entry["ticker"].upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    return None

def get_sic_code(ticker: str) -> str:
    """Get SIC code for ticker via SEC EDGAR."""
    cik = get_cik(ticker)
    if not cik:
        return None
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    r = requests.get(url, headers=EDGAR_HEADERS)
    data = r.json()
    return data.get("sic"), data.get("sicDescription")

# Bulk fetch for universe
def build_sic_map(tickers: list) -> dict:
    import time
    sic_map = {}
    for ticker in tickers:
        sic, desc = get_sic_code(ticker)
        sic_map[ticker] = {"sic": sic, "description": desc}
        time.sleep(0.1)  # be polite to SEC servers
    return sic_map
```

**SIC to GICS sector mapping** (major division → GICS Sector):

```python
SIC_TO_GICS = {
    # SIC major group → GICS Sector
    "01": "Consumer Staples",     # Agriculture
    "10": "Materials",             # Mining
    "13": "Energy",                # Oil & Gas
    "15": "Industrials",           # Construction
    "20": "Consumer Staples",      # Food
    "26": "Materials",             # Paper
    "28": "Health Care",           # Chemicals/Pharma (split needed)
    "2830": "Health Care",         # Drug manufacturing (more specific)
    "2836": "Health Care",         # Biological products
    "29": "Energy",                # Petroleum refining
    "35": "Information Technology",# Industrial machinery
    "36": "Information Technology",# Electronics
    "3674": "Information Technology", # Semiconductors (SIC 3674)
    "37": "Consumer Discretionary",# Motor vehicles
    "38": "Health Care",           # Instruments (split: IT or HC)
    "48": "Communication Services",# Communications
    "49": "Utilities",             # Electric/gas utilities
    "50": "Industrials",           # Wholesale durable
    "51": "Consumer Staples",      # Wholesale non-durable
    "52": "Consumer Discretionary",# Retail
    "58": "Consumer Discretionary",# Eating/drinking places
    "59": "Consumer Staples",      # Misc retail
    "60": "Financials",            # Banks
    "61": "Financials",            # Credit
    "62": "Financials",            # Security dealers
    "63": "Financials",            # Insurance
    "65": "Real Estate",           # Real estate
    "67": "Financials",            # Holding companies
    "70": "Consumer Discretionary",# Hotels
    "73": "Information Technology",# Computer services
    "75": "Industrials",           # Auto repair
    "80": "Health Care",           # Health services
    "87": "Industrials",           # Engineering services
}
```

**Caveats**: SIC≠GICS; some SIC codes straddle GICS sectors (SIC 28 is split between Materials and Health Care). For large-cap US stocks, the mapping is reliable. Cache results — SIC codes rarely change for established companies.

---

## Source 2: GitHub S&P 500 Constituents CSV — Free, Current Only ★★★☆☆

Good for current sector assignments. **Not point-in-time** — only reflects today's constituents.

```python
import pandas as pd

# S&P 500 with GICS sectors (current)
SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"

def get_sp500_gics() -> pd.DataFrame:
    """Returns DataFrame: Symbol, Security, GICS Sector, GICS Sub-Industry, CIK"""
    df = pd.read_csv(SP500_URL)
    return df[["Symbol", "Security", "GICS Sector", "GICS Sub-Industry"]]

# Build sector map
sp500 = get_sp500_gics()
sector_map = dict(zip(sp500["Symbol"], sp500["GICS Sector"]))
# e.g., {'AAPL': 'Information Technology', 'JPM': 'Financials', ...}
```

**When this is acceptable**: For our 30-stock fixed universe (AAPL, MSFT, etc.), none of these names has changed GICS sectors in 2019-2026. Look-ahead bias is negligible for large-cap stable names. For a dynamic 500-stock universe, use point-in-time sources.

**Wikipedia revision API** for historical S&P 500 membership:
```python
# Get S&P 500 list as of a specific date (monthly snapshots via Wikipedia API)
import requests
from datetime import datetime

def get_sp500_at_date(date: str) -> pd.DataFrame:
    """date: 'YYYY-MM-DD'. Fetches Wikipedia S&P 500 list revision near that date."""
    # Wikipedia API: revisions for "List of S&P 500 companies"
    title = "List_of_S%26P_500_companies"
    rvstart = date + "T00:00:00Z"
    url = f"https://en.wikipedia.org/w/api.php?action=query&titles={title}&prop=revisions&rvstart={rvstart}&rvlimit=1&rvprop=ids|timestamp|content&format=json"
    # Parse wikitext revision to extract constituents table...
    # (complex but doable; consider caching monthly snapshots to parquet)
    pass
```

---

## Source 3: yfinance Sector/Industry — Free, Simple, NOT for Historical Backtests ★★☆☆☆

```python
import yfinance as yf

# Single stock
tk = yf.Ticker("AAPL")
sector = tk.info.get("sector")      # "Technology"
industry = tk.info.get("industry")  # "Consumer Electronics"
sector_key = tk.info.get("sectorKey")  # "technology"

# Sector-level navigation (yfinance ≥ 0.2.40)
tech_sector = yf.Sector("technology")
print(tech_sector.top_companies)  # top stocks in sector
```

**Critical caveats:**
- Returns **current** sector classification only — no historical
- Frequent NaN/missing values (version-dependent: 0.2.14+ most reliable)
- No bulk endpoint — must fetch `.info` one ticker at a time (rate-limited)
- **Not suitable for 2019-2026 backtest** — introduces look-ahead bias for any stock that ever changed sector

**When to use**: Live paper trading forward-looking sector membership. Acceptable for fixed universe of large-cap stocks where sectors are known to be stable (our 30-ticker PEAD universe).

---

## Source 4: FMP API — Moderate Quality, 250 calls/day free ★★★☆☆

```python
import requests
import os

FMP_KEY = os.environ["FMP_API_KEY"]

def get_fmp_sector(ticker: str) -> str:
    url = f"https://financialmodelingprep.com/api/v3/profile/{ticker}"
    r = requests.get(url, params={"apikey": FMP_KEY})
    data = r.json()
    if data:
        return data[0].get("sector"), data[0].get("industry")
    return None, None

# Bulk: get all S&P 500 profiles at once (counts as many calls)
def get_all_sectors(tickers: list) -> dict:
    result = {}
    for t in tickers:
        sector, industry = get_fmp_sector(t)
        result[t] = {"sector": sector, "industry": industry}
    return result
```

**Notes**: FMP uses custom classification, not standard GICS or SIC. 250 req/day on free tier limits bulk use. Upgrade to Starter ($19.99/mo) for 2,000/day. Historical point-in-time sector data requires Premium tier.

---

## Source 5: SPDR Sector ETF Proxy — Incomplete but Consistent ★★☆☆☆

Map stocks to GICS sectors via their membership in SPDR Select Sector ETFs. Only covers S&P 500.

| ETF | GICS Sector | Key Holdings |
|-----|-------------|-------------|
| XLK | Information Technology | AAPL, MSFT, NVDA, AVGO, QCOM, AMD |
| XLV | Health Care | UNH, LLY, ABBV, PFE, JNJ, MRK |
| XLF | Financials | JPM, BAC, WFC, V, MA |
| XLE | Energy | XOM, CVX |
| XLC | Communication Services | GOOGL, META |
| XLY | Consumer Discretionary | AMZN, TSLA, HD, LOW, SBUX |
| XLP | Consumer Staples | WMT, COST |
| XLI | Industrials | (CAT adjacent) |
| XLB | Materials | — |
| XLRE | Real Estate | — |
| XLU | Utilities | — |

```python
# Manual static mapping for our 30-ticker universe (2019-2026 stable)
UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD": "Information Technology",
    "V": "Financials", "MA": "Financials",
    "BAC": "Financials", "WFC": "Financials", "JPM": "Financials",
    "UNH": "Health Care", "LLY": "Health Care",
    "PFE": "Health Care", "JNJ": "Health Care", "ABBV": "Health Care",
    "WMT": "Consumer Staples", "HD": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW": "Consumer Discretionary",
    "COST": "Consumer Staples", "CVX": "Energy", "XOM": "Energy",
    "BA": "Industrials", "CAT": "Industrials", "IBM": "Information Technology",
}
```

---

## Best Practical Approach for H181

**Scenario**: Industry-adjusted short-term reversal, US stocks, 2019–2026 backtest

### For our fixed 30-ticker universe (simple case)
Use the static `UNIVERSE_SECTORS` mapping above. These 30 large-caps have not changed GICS sectors in 2019-2026. Acceptable look-ahead bias exposure: zero.

### For a 300-500 stock universe (H181 full implementation)
```python
import pandas as pd
import requests
import time

def build_sector_cache(tickers: list, cache_path="backtesting/cache/sector_codes.parquet") -> pd.DataFrame:
    """
    Build sector cache. Strategy:
    1. Try GitHub S&P 500 CSV first (free, instant, GICS)
    2. Fill gaps with SEC EDGAR SIC → GICS mapping
    3. Cache to parquet; don't re-fetch unless missing
    """
    from pathlib import Path
    
    # Load cached if exists
    if Path(cache_path).exists():
        df = pd.read_parquet(cache_path)
        cached_tickers = set(df["ticker"])
        missing = [t for t in tickers if t not in cached_tickers]
        if not missing:
            return df
        tickers = missing
    
    records = []
    
    # Source 1: GitHub S&P 500 CSV (fast, GICS)
    sp500 = pd.read_csv("https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv")
    sp500_map = dict(zip(sp500["Symbol"], sp500["GICS Sector"]))
    sp500_sub = dict(zip(sp500["Symbol"], sp500["GICS Sub-Industry"]))
    
    remaining = []
    for t in tickers:
        if t in sp500_map:
            records.append({
                "ticker": t, "gics_sector": sp500_map[t],
                "gics_sub_industry": sp500_sub.get(t), "source": "sp500_csv"
            })
        else:
            remaining.append(t)
    
    # Source 2: SEC EDGAR SIC codes for remainder
    EDGAR_HEADERS = {"User-Agent": "george-nanoclaw george@nanoclaw.com"}
    tickers_url = "https://www.sec.gov/files/company_tickers.json"
    r = requests.get(tickers_url, headers=EDGAR_HEADERS)
    ticker_to_cik = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in r.json().values()}
    
    for t in remaining:
        cik = ticker_to_cik.get(t.upper())
        if cik:
            url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            data = requests.get(url, headers=EDGAR_HEADERS).json()
            sic = data.get("sic", "")
            records.append({
                "ticker": t, "sic": sic,
                "gics_sector": SIC_TO_GICS.get(sic[:4], SIC_TO_GICS.get(sic[:2], "Unknown")),
                "source": "sec_edgar_sic"
            })
            time.sleep(0.1)
    
    df_new = pd.DataFrame(records)
    
    # Merge with existing cache
    if Path(cache_path).exists():
        df_existing = pd.read_parquet(cache_path)
        df_new = pd.concat([df_existing, df_new]).drop_duplicates("ticker")
    
    df_new.to_parquet(cache_path)
    return df_new
```

### Applying to monthly reversal signal
```python
def industry_adjusted_reversal(monthly_returns: pd.Series, sector_map: dict) -> pd.Series:
    """
    monthly_returns: pd.Series, index = ticker, values = last month return
    sector_map: dict, ticker → GICS sector string
    Returns: industry-adjusted return (= stock return - industry mean return)
    """
    sectors = pd.Series(sector_map)
    # Only compute for tickers where we have sector
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means  # sort ascending → long bottom quintile
```

---

## Comparison Table

| Source | Classification | Free? | Bulk? | Historical | Point-in-Time | Best For |
|--------|---------------|-------|-------|-----------|---------------|----------|
| **SEC EDGAR SIC** | SIC | ✓ | ✓ | ✓ | ✓ (filing date) | Historical backtests, large universes |
| **GitHub S&P 500 CSV** | GICS | ✓ | ✓ | ✗ (current) | ✗ | Current 500-stock universe |
| **yfinance `.info`** | GICS-like | ✓ | ✗ (slow) | ✗ | ✗ | Fixed universe live trading |
| **FMP `/profile`** | Custom | 250/day | ✓ | ✗ | ✗ | Supplemental lookup |
| **Polygon.io** | SIC | ✗ (5/min) | ✗ | ✗ | ✗ | Not practical for bulk |
| **Static ETF mapping** | GICS | ✓ | ✓ | ✓ (manual) | ✓ (if versioned) | Small fixed universe |

---

## H181 Implementation Decision

For H181 US stock reversal backtest on ~100 large-caps (2019-2026):

1. **Universe**: Top 100 S&P 500 stocks by market cap in each period
2. **Sector source**: GitHub S&P 500 CSV (GICS, free) + static ETF map for pre-S&P 500 period
3. **Bias check**: For large-caps, current GICS sector is stable over our 7-year window
4. **Code**: Use `build_sector_cache()` above → `industry_adjusted_reversal()` monthly

This avoids the Compustat/CRSP requirement of the original paper while maintaining acceptable accuracy for US large-caps.
