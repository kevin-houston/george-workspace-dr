"""Alpaca daily bar fetcher with parquet cache; falls back to yfinance."""

import hashlib
import os
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _symbols_hash(symbols: list[str]) -> str:
    key = "_".join(sorted(symbols))
    return hashlib.md5(key.encode()).hexdigest()[:8]


def _fetch_alpaca(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET"],
    )
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        feed="iex",
        adjustment="split",
    )
    bars = client.get_stock_bars(request).df
    bars.index.names = ["symbol", "date"]
    bars.index = bars.index.set_levels(
        pd.to_datetime(bars.index.get_level_values("date")).normalize(), level="date"
    )
    return bars[["open", "high", "low", "close", "volume"]]


def _fetch_yfinance(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)

    frames = []
    for sym in symbols:
        if len(symbols) == 1:
            df = raw.copy()
        else:
            df = raw.xs(sym, axis=1, level=1).copy()
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "date"
        df["symbol"] = sym
        frames.append(df.reset_index().set_index(["symbol", "date"]))

    return pd.concat(frames).sort_index()


def fetch_daily_bars(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """Return MultiIndex (symbol, date) OHLCV DataFrame for all symbols."""
    h = _symbols_hash(symbols)
    cache_path = CACHE_DIR / f"{h}_daily_{start}_{end}.parquet"

    if cache_path.exists():
        return pd.read_parquet(cache_path)

    try:
        bars = _fetch_alpaca(symbols, start, end)
        source = "Alpaca"
    except Exception as e:
        print(f"Alpaca fetch failed ({e}), falling back to yfinance")
        bars = _fetch_yfinance(symbols, start, end)
        source = "yfinance"

    bars.to_parquet(cache_path)
    print(f"Fetched {len(bars):,} rows for {len(symbols)} symbols via {source} → {cache_path.name}")
    return bars
