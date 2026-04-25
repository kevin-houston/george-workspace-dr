"""
Alpaca 1-min bar fetcher with local parquet cache.
Cache lives at backtesting/cache/<symbol>_1min_<start>_<end>.parquet
"""

import os
import pickle
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def fetch_bars(symbol: str, start: str, end: str) -> pd.DataFrame:
    """
    Return 1-minute OHLCV bars for symbol between start and end (inclusive).
    Dates as 'YYYY-MM-DD'. Uses Alpaca IEX feed (free tier).
    Returns DataFrame indexed by datetime (UTC), columns: open high low close volume.
    """
    cache_path = CACHE_DIR / f"{symbol}_1min_{start}_{end}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
    )

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Minute,
        start=start,
        end=end,
        feed="iex",
        adjustment="split",
    )

    bars = client.get_stock_bars(request).df

    if isinstance(bars.index, pd.MultiIndex):
        bars = bars.xs(symbol, level="symbol")

    bars.index = pd.to_datetime(bars.index, utc=True)
    bars = bars[["open", "high", "low", "close", "volume"]].sort_index()

    bars.to_parquet(cache_path)
    print(f"Fetched {len(bars):,} bars for {symbol} → cached to {cache_path.name}")
    return bars
