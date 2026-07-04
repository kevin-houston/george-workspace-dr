"""
Step 2: Daily price/yield data ingestion.

Outputs (all saved to cache/):
  - sp500_prices.parquet   — adjusted daily OHLCV for S&P 500 universe
  - dgs2.parquet           — FRED DGS2 daily 2Y Treasury yield
  - universe.parquet       — ticker, sector (GICS), current SP500 membership
  - earnings_dates.parquet — earnings release dates per ticker
"""

import os
import time
import json
import requests
import warnings
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

warnings.filterwarnings("ignore")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
FRED_KEY = os.environ.get("FRED_API_KEY", "")

# OneCLI proxy CA bundle — required for HTTPS in this environment
CA_BUNDLE = "/tmp/onecli-combined-ca.pem"
if not Path(CA_BUNDLE).exists():
    CA_BUNDLE = True  # fall back to system certs

# Monkey-patch requests to always use CA bundle
import functools
_orig_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    if "verify" not in kwargs:
        kwargs["verify"] = CA_BUNDLE
    return _orig_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

# ── S&P 500 universe ──────────────────────────────────────────────────────────

def get_sp500_tickers() -> pd.DataFrame:
    """
    Fetch current S&P 500 constituent list from Wikipedia.
    NOTE: This is CURRENT membership — survivorship bias caveat applies.
    Returns DataFrame with columns: ticker, company, sector, sub_industry.
    """
    import ssl
    import io

    cache_file = CACHE_DIR / "sp500_universe.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    print("  Fetching S&P 500 universe from Wikipedia...")
    try:
        # Try requests first (goes through OneCLI proxy with cert handling)
        resp = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text), attrs={"id": "constituents"})
    except Exception as e:
        print(f"  Wikipedia fetch failed ({e}), using hardcoded sector list...")
        return _hardcoded_sp500_sample()

    df = tables[0]
    df = df.rename(columns={
        "Symbol": "ticker",
        "Security": "company",
        "GICS Sector": "sector",
        "GICS Sub-Industry": "sub_industry",
    })
    df["ticker"] = df["ticker"].str.replace(".", "-", regex=False)
    df = df[["ticker", "company", "sector", "sub_industry"]].copy()
    df.to_parquet(cache_file, index=False)
    print(f"  {len(df)} tickers in universe")
    return df


def _hardcoded_sp500_sample() -> pd.DataFrame:
    """
    Fallback: a representative 100-ticker sample across all 11 GICS sectors.
    Used when Wikipedia is unavailable. Survivorship bias caveat applies to full run too.
    For production, replace with a point-in-time membership file.
    """
    tickers = [
        # Information Technology
        ("AAPL","Apple","Information Technology","Technology Hardware"),
        ("MSFT","Microsoft","Information Technology","Systems Software"),
        ("NVDA","NVIDIA","Information Technology","Semiconductors"),
        ("AVGO","Broadcom","Information Technology","Semiconductors"),
        ("AMD","AMD","Information Technology","Semiconductors"),
        ("AMAT","Applied Materials","Information Technology","Semiconductor Equipment"),
        ("ORCL","Oracle","Information Technology","Application Software"),
        ("CRM","Salesforce","Information Technology","Application Software"),
        ("NOW","ServiceNow","Information Technology","Application Software"),
        ("ADBE","Adobe","Information Technology","Application Software"),
        ("INTC","Intel","Information Technology","Semiconductors"),
        ("QCOM","Qualcomm","Information Technology","Semiconductors"),
        ("TXN","Texas Instruments","Information Technology","Semiconductors"),
        ("IBM","IBM","Information Technology","IT Consulting"),
        ("ACN","Accenture","Information Technology","IT Consulting"),
        # Health Care
        ("UNH","UnitedHealth","Health Care","Managed Health Care"),
        ("LLY","Eli Lilly","Health Care","Pharmaceuticals"),
        ("JNJ","Johnson & Johnson","Health Care","Pharmaceuticals"),
        ("ABBV","AbbVie","Health Care","Biotechnology"),
        ("MRK","Merck","Health Care","Pharmaceuticals"),
        ("TMO","Thermo Fisher","Health Care","Life Sciences Tools"),
        ("ABT","Abbott","Health Care","Health Care Equipment"),
        ("DHR","Danaher","Health Care","Life Sciences Tools"),
        ("BMY","Bristol-Myers","Health Care","Pharmaceuticals"),
        ("AMGN","Amgen","Health Care","Biotechnology"),
        ("GILD","Gilead","Health Care","Biotechnology"),
        ("ISRG","Intuitive Surgical","Health Care","Health Care Equipment"),
        ("VRTX","Vertex","Health Care","Biotechnology"),
        # Financials
        ("BRK-B","Berkshire","Financials","Multi-line Insurance"),
        ("JPM","JPMorgan","Financials","Diversified Banks"),
        ("BAC","Bank of America","Financials","Diversified Banks"),
        ("WFC","Wells Fargo","Financials","Diversified Banks"),
        ("GS","Goldman Sachs","Financials","Investment Banking"),
        ("MS","Morgan Stanley","Financials","Investment Banking"),
        ("BLK","BlackRock","Financials","Asset Management"),
        ("SCHW","Schwab","Financials","Investment Services"),
        ("C","Citigroup","Financials","Diversified Banks"),
        ("AXP","AmEx","Financials","Consumer Finance"),
        ("V","Visa","Financials","Data Processing"),
        ("MA","Mastercard","Financials","Data Processing"),
        # Consumer Discretionary
        ("AMZN","Amazon","Consumer Discretionary","Internet Retail"),
        ("TSLA","Tesla","Consumer Discretionary","Automobile Manufacturers"),
        ("HD","Home Depot","Consumer Discretionary","Home Improvement Retail"),
        ("MCD","McDonald's","Consumer Discretionary","Restaurants"),
        ("NKE","Nike","Consumer Discretionary","Apparel"),
        ("LOW","Lowe's","Consumer Discretionary","Home Improvement Retail"),
        ("SBUX","Starbucks","Consumer Discretionary","Restaurants"),
        ("TJX","TJX Companies","Consumer Discretionary","Apparel Retail"),
        ("BKNG","Booking","Consumer Discretionary","Hotels & Resorts"),
        ("GM","General Motors","Consumer Discretionary","Automobile Manufacturers"),
        # Communication Services
        ("META","Meta","Communication Services","Interactive Media"),
        ("GOOGL","Alphabet A","Communication Services","Interactive Media"),
        ("GOOG","Alphabet C","Communication Services","Interactive Media"),
        ("NFLX","Netflix","Communication Services","Movies & Entertainment"),
        ("DIS","Disney","Communication Services","Movies & Entertainment"),
        ("CMCSA","Comcast","Communication Services","Cable & Satellite"),
        ("T","AT&T","Communication Services","Integrated Telecom"),
        ("VZ","Verizon","Communication Services","Integrated Telecom"),
        # Industrials
        ("GE","GE Aerospace","Industrials","Aerospace & Defense"),
        ("CAT","Caterpillar","Industrials","Construction Machinery"),
        ("RTX","RTX","Industrials","Aerospace & Defense"),
        ("HON","Honeywell","Industrials","Industrial Conglomerates"),
        ("UPS","UPS","Industrials","Air Freight"),
        ("DE","Deere","Industrials","Agricultural Machinery"),
        ("LMT","Lockheed","Industrials","Aerospace & Defense"),
        ("BA","Boeing","Industrials","Aerospace & Defense"),
        ("GD","General Dynamics","Industrials","Aerospace & Defense"),
        ("MMM","3M","Industrials","Industrial Conglomerates"),
        # Consumer Staples
        ("WMT","Walmart","Consumer Staples","Hypermarkets"),
        ("PG","P&G","Consumer Staples","Household Products"),
        ("KO","Coca-Cola","Consumer Staples","Soft Drinks"),
        ("PEP","PepsiCo","Consumer Staples","Soft Drinks"),
        ("COST","Costco","Consumer Staples","Hypermarkets"),
        ("PM","Philip Morris","Consumer Staples","Tobacco"),
        ("MO","Altria","Consumer Staples","Tobacco"),
        ("CL","Colgate","Consumer Staples","Household Products"),
        ("MDLZ","Mondelez","Consumer Staples","Packaged Foods"),
        # Energy
        ("XOM","ExxonMobil","Energy","Integrated Oil & Gas"),
        ("CVX","Chevron","Energy","Integrated Oil & Gas"),
        ("COP","ConocoPhillips","Energy","E&P"),
        ("SLB","SLB","Energy","Oil & Gas Services"),
        ("EOG","EOG Resources","Energy","E&P"),
        ("MPC","Marathon Petroleum","Energy","Oil & Gas Refining"),
        # Utilities
        ("NEE","NextEra","Utilities","Electric Utilities"),
        ("SO","Southern Company","Utilities","Electric Utilities"),
        ("DUK","Duke Energy","Utilities","Electric Utilities"),
        ("D","Dominion","Utilities","Electric Utilities"),
        ("AEP","AEP","Utilities","Electric Utilities"),
        # Real Estate
        ("AMT","American Tower","Real Estate","Telecom Tower REITs"),
        ("PLD","Prologis","Real Estate","Industrial REITs"),
        ("EQIX","Equinix","Real Estate","Data Center REITs"),
        ("CCI","Crown Castle","Real Estate","Telecom Tower REITs"),
        ("SPG","Simon Property","Real Estate","Retail REITs"),
        # Materials
        ("LIN","Linde","Materials","Industrial Gases"),
        ("APD","Air Products","Materials","Industrial Gases"),
        ("SHW","Sherwin-Williams","Materials","Specialty Chemicals"),
        ("ECL","Ecolab","Materials","Specialty Chemicals"),
        ("NEM","Newmont","Materials","Gold"),
        ("FCX","Freeport","Materials","Copper"),
    ]
    df = pd.DataFrame(tickers, columns=["ticker", "company", "sector", "sub_industry"])
    cache_file = CACHE_DIR / "sp500_universe.parquet"
    df.to_parquet(cache_file, index=False)
    print(f"  Using hardcoded sample: {len(df)} tickers across {df.sector.nunique()} sectors")
    return df


# ── Daily prices ──────────────────────────────────────────────────────────────

def fetch_prices(tickers: list[str], start: str = "2007-01-01",
                 end: str | None = None, batch_size: int = 50) -> pd.DataFrame:
    """
    Download adjusted close prices for all tickers via yfinance.
    Returns wide DataFrame (date × ticker).
    """
    import yfinance as yf

    if end is None:
        end = date.today().strftime("%Y-%m-%d")

    cache_file = CACHE_DIR / "sp500_prices.parquet"
    if cache_file.exists():
        existing = pd.read_parquet(cache_file)
        last_date = existing.index.max()
        if pd.Timestamp(end) <= last_date + pd.Timedelta(days=2):
            print(f"  Price cache up to date ({last_date.date()})")
            return existing
        # Incremental update
        new_start = (last_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        print(f"  Updating prices from {new_start}...")
    else:
        existing = None
        new_start = start

    all_frames = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        print(f"  Downloading batch {i//batch_size + 1}/{(len(tickers)-1)//batch_size + 1}...")
        try:
            raw = yf.download(
                batch, start=new_start, end=end,
                auto_adjust=True, progress=False, threads=True
            )
            if isinstance(raw.columns, pd.MultiIndex):
                closes = raw["Close"]
            else:
                closes = raw[["Close"]] if "Close" in raw.columns else raw
            all_frames.append(closes)
        except Exception as e:
            print(f"  Batch error: {e}")
        time.sleep(0.5)

    if not all_frames:
        return existing or pd.DataFrame()

    new_prices = pd.concat(all_frames, axis=1)
    new_prices = new_prices.loc[:, ~new_prices.columns.duplicated()]

    if existing is not None:
        result = pd.concat([existing, new_prices]).sort_index()
        result = result[~result.index.duplicated(keep="last")]
    else:
        result = new_prices

    result.to_parquet(cache_file)
    print(f"  Price data: {result.shape[0]} days × {result.shape[1]} tickers")
    return result


def fetch_market_returns(start: str = "2007-01-01", end: str | None = None) -> pd.Series:
    """SPY daily returns as market factor."""
    import yfinance as yf

    cache_file = CACHE_DIR / "spy_returns.parquet"
    if end is None:
        end = date.today().strftime("%Y-%m-%d")

    if cache_file.exists():
        sr = pd.read_parquet(cache_file).squeeze()
        if pd.Timestamp(end) <= sr.index.max() + pd.Timedelta(days=2):
            return sr

    spy = yf.download("SPY", start=start, end=end, auto_adjust=True, progress=False)
    returns = spy["Close"].pct_change().dropna()
    returns.name = "spy_ret"
    pd.DataFrame(returns).to_parquet(cache_file)
    return returns


# ── FRED DGS2 ──────────────────────────────────────────────────────────────────

def fetch_dgs2(start: str = "2007-01-01") -> pd.Series:
    """
    Download FRED DGS2 (2-Year Treasury Yield, daily).
    Returns Series indexed by date.
    """
    cache_file = CACHE_DIR / "dgs2.parquet"
    if cache_file.exists():
        existing = pd.read_parquet(cache_file).squeeze()
        last = existing.index.max()
        if (pd.Timestamp("today") - last).days < 3:
            return existing

    if not FRED_KEY:
        print("  WARNING: FRED_API_KEY not set, attempting without key...")
        key_param = ""
    else:
        key_param = f"&api_key={FRED_KEY}"

    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id=DGS2&observation_start={start}"
        f"&file_type=json{key_param}"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        obs = data["observations"]
        df = pd.DataFrame(obs)[["date", "value"]]
        df["date"] = pd.to_datetime(df["date"])
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna().set_index("date")["value"]
        df.name = "dgs2"
        pd.DataFrame(df).to_parquet(cache_file)
        print(f"  DGS2: {len(df)} observations, through {df.index.max().date()}")
        return df
    except Exception as e:
        print(f"  ERROR fetching DGS2: {e}")
        if cache_file.exists():
            return pd.read_parquet(cache_file).squeeze()
        return pd.Series(dtype=float, name="dgs2")


# ── Earnings dates ─────────────────────────────────────────────────────────────

def fetch_earnings_dates(tickers: list[str]) -> pd.DataFrame:
    """
    Get earnings dates per ticker for contamination filtering.
    Returns DataFrame: ticker, earnings_date.
    """
    import yfinance as yf

    cache_file = CACHE_DIR / "earnings_dates.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)

    print("  Fetching earnings dates (this takes a while)...")
    records = []
    for i, ticker in enumerate(tickers):
        if i % 50 == 0:
            print(f"    {i}/{len(tickers)}...")
        try:
            t = yf.Ticker(ticker)
            cal = t.earnings_dates
            if cal is not None and not cal.empty:
                for dt in cal.index:
                    records.append({"ticker": ticker, "earnings_date": dt.date()})
        except Exception:
            pass
        time.sleep(0.05)

    df = pd.DataFrame(records)
    if not df.empty:
        df["earnings_date"] = pd.to_datetime(df["earnings_date"])
    df.to_parquet(cache_file, index=False)
    print(f"  Earnings dates: {len(df)} records for {df['ticker'].nunique()} tickers")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def build_price_data(start: str = "2007-01-01") -> dict:
    """
    Run all data downloads. Returns dict of DataFrames.
    """
    print("=== Step 2: Price/yield data ingestion ===")
    universe = get_sp500_tickers()
    tickers = universe["ticker"].tolist()

    dgs2 = fetch_dgs2(start=start)
    prices = fetch_prices(tickers, start=start)
    spy_rets = fetch_market_returns(start=start)
    earnings = fetch_earnings_dates(tickers)

    return {
        "universe": universe,
        "prices": prices,
        "dgs2": dgs2,
        "spy_rets": spy_rets,
        "earnings": earnings,
    }


if __name__ == "__main__":
    data = build_price_data()
    print(f"\nUniverse: {len(data['universe'])} tickers")
    print(f"Price history: {data['prices'].shape}")
    print(f"DGS2: {len(data['dgs2'])} observations")
    print(f"SPY returns: {len(data['spy_rets'])} observations")
    print(f"Earnings dates: {len(data['earnings'])} records")
