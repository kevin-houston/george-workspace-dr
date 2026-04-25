"""
Macro regime tagging.

Two methods:
  1. USREC (FRED): official NBER recession months — sparse, misses bear markets
  2. SPY 200-day SMA: market-based risk-on/risk-off — more granular, better for H002
"""

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / "cache"


@lru_cache(maxsize=1)
def load_recession_dates() -> pd.Series:
    """USREC: 1 = recession month, 0 = expansion. Monthly frequency."""
    from fredapi import Fred
    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    usrec = fred.get_series("USREC", observation_start="2010-01-01")
    usrec.index = pd.to_datetime(usrec.index)
    return usrec


def tag_usrec(trading_date: pd.Timestamp) -> str:
    usrec = load_recession_dates()
    month_start = trading_date.replace(day=1)
    mask = usrec.index <= month_start
    if not mask.any():
        return "expansion"
    val = usrec[mask].iloc[-1]
    return "contraction" if val == 1 else "expansion"


@lru_cache(maxsize=1)
def load_spy_200sma(start: str = "2014-01-01", end: str = "2023-01-01") -> pd.Series:
    """
    Daily SPY close from Alpaca, compute 200-day SMA.
    Returns Series indexed by date, values: 'risk-on' or 'risk-off'.
    200-day SMA needs ~1 year of lead data before in-sample start.
    """
    cache_path = CACHE_DIR / f"SPY_daily_{start}_{end}_regime.parquet"
    if cache_path.exists():
        s = pd.read_parquet(cache_path)["regime"]
        s.index = pd.to_datetime(s.index).date
        return s

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
    )
    req = StockBarsRequest(
        symbol_or_symbols="SPY",
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed="iex",
        adjustment="split",
    )
    bars = client.get_stock_bars(req).df
    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs("SPY", level="symbol")
    bars.index = pd.to_datetime(bars.index, utc=True).tz_convert("America/New_York").normalize()

    close = bars["close"]
    sma200 = close.rolling(200).mean()
    regime = pd.Series(
        ["risk-on" if c > s else "risk-off" for c, s in zip(close, sma200)],
        index=close.index,
        name="regime",
    )
    regime.to_frame().to_parquet(cache_path)
    return pd.Series(regime.values, index=close.index.date, name="regime")


def tag_spy_regime(trading_date, spy_regime: pd.Series) -> str:
    """Look up regime for a given date from the precomputed series."""
    if hasattr(trading_date, "date"):
        d = trading_date.date() if hasattr(trading_date, "date") and callable(trading_date.date) else trading_date
    else:
        d = trading_date
    try:
        return spy_regime.loc[d]
    except KeyError:
        return "risk-on"


def tag_dataframe(df: pd.DataFrame, method: str = "usrec") -> pd.DataFrame:
    """
    Add a 'regime' column. method: 'usrec' or 'spy200'.
    For spy200, fetches SPY daily bars covering the df date range.
    """
    df = df.copy()
    if method == "usrec":
        df["regime"] = df["date"].apply(lambda d: tag_usrec(pd.Timestamp(d)))
    else:
        dates = pd.to_datetime(df["date"])
        start = (dates.min() - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
        end = (dates.max() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        spy_regime = load_spy_200sma(start=start, end=end)
        df["regime"] = df["date"].apply(lambda d: tag_spy_regime(d, spy_regime))
    return df
