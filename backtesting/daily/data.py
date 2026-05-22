"""
Daily bar data layer — ArcticDB-backed with yfinance/Alpaca fallback.

ArcticDB stores each symbol as its own time-series in a local LMDB database,
enabling incremental updates and fast date-range slicing without re-downloading
full history. Falls back to the old parquet cache if ArcticDB is unavailable.

Usage (unchanged API):
    from data import fetch_daily_bars
    bars = fetch_daily_bars(["AAPL", "MSFT"], "2020-01-01", "2025-12-31")
    # Returns MultiIndex (symbol, date) DataFrame with OHLCV columns
"""

import os
from pathlib import Path
from datetime import datetime, timedelta

import pandas as pd

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
ARCTIC_DIR = WORKSPACE / "backtesting" / "data" / "arctic_store"
CACHE_DIR.mkdir(exist_ok=True)
ARCTIC_DIR.parent.mkdir(parents=True, exist_ok=True)

# ── ArcticDB setup ────────────────────────────────────────────────────────────
def _get_arctic_lib():
    import arcticdb as adb
    ac = adb.Arctic(f"lmdb://{ARCTIC_DIR}")
    return ac.get_library("ohlcv", create_if_missing=True)


# ── Raw fetchers ──────────────────────────────────────────────────────────────
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
        df = raw.copy() if len(symbols) == 1 else raw.xs(sym, axis=1, level=1).copy()
        df.columns = [c.lower() for c in df.columns]
        df = df[["open", "high", "low", "close", "volume"]].dropna()
        df.index = pd.to_datetime(df.index).normalize()
        df.index.name = "date"
        df["symbol"] = sym
        frames.append(df.reset_index().set_index(["symbol", "date"]))
    return pd.concat(frames).sort_index()


def _fetch_raw(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    try:
        bars = _fetch_alpaca(symbols, start, end)
        print(f"  fetched {len(bars):,} rows via Alpaca")
        return bars
    except Exception as e:
        print(f"  Alpaca failed ({e}), using yfinance")
        bars = _fetch_yfinance(symbols, start, end)
        print(f"  fetched {len(bars):,} rows via yfinance")
        return bars


# ── ArcticDB read/write helpers ───────────────────────────────────────────────
def _arctic_read(lib, symbol: str, start: str, end: str) -> pd.DataFrame | None:
    """Read symbol from ArcticDB; return None if not present or range not covered."""
    try:
        if not lib.has_symbol(symbol):
            return None
        item = lib.read(symbol, date_range=(pd.Timestamp(start), pd.Timestamp(end)))
        df = item.data
        if df is None or df.empty:
            return None
        # Check coverage: stored data must reach at least to end - 3 trading days
        stored_end = df.index.max()
        required_end = pd.Timestamp(end)
        # Allow 3-day gap for weekends/holidays
        if (required_end - stored_end).days > 5:
            return None
        return df
    except Exception:
        return None


def _arctic_write(lib, symbol: str, df: pd.DataFrame):
    """Write or update a symbol's data in ArcticDB (appends new rows)."""
    try:
        if lib.has_symbol(symbol):
            existing = lib.read(symbol).data
            combined = pd.concat([existing, df[~df.index.isin(existing.index)]])
            combined = combined.sort_index()
            lib.write(symbol, combined)
        else:
            lib.write(symbol, df.sort_index())
    except Exception as e:
        print(f"  ArcticDB write failed for {symbol}: {e}")


# ── Public API ────────────────────────────────────────────────────────────────
def fetch_daily_bars(symbols: list[str], start: str, end: str) -> pd.DataFrame:
    """
    Return MultiIndex (symbol, date) OHLCV DataFrame for all symbols.

    Cache hierarchy:
      1. ArcticDB (symbol-keyed, incremental) — preferred
      2. Legacy parquet cache (query-hash-keyed) — fallback if Arctic unavailable
      3. Live fetch from Alpaca → yfinance
    """
    # Try ArcticDB path
    try:
        lib = _get_arctic_lib()
        cached, missing, missing_symbols = [], [], []

        for sym in symbols:
            df = _arctic_read(lib, sym, start, end)
            if df is not None:
                df = df.loc[start:end].copy()
                df["symbol"] = sym
                cached.append(df.reset_index().rename(columns={"index": "date"})
                               .set_index(["symbol", "date"])
                               if "symbol" not in df.index.names else df)
            else:
                missing_symbols.append(sym)

        if missing_symbols:
            print(f"  Arctic miss for {missing_symbols}, fetching...")
            fresh = _fetch_raw(missing_symbols, start, end)
            for sym in missing_symbols:
                sym_df = fresh.xs(sym, level="symbol") if sym in fresh.index.get_level_values("symbol") else None
                if sym_df is not None and not sym_df.empty:
                    _arctic_write(lib, sym, sym_df)
                    sym_df = sym_df.copy()
                    sym_df["symbol"] = sym
                    cached.append(sym_df.reset_index().set_index(["symbol", "date"])
                                  if "symbol" not in sym_df.index.names else sym_df)

        if cached:
            result = pd.concat(cached).sort_index()
            # Ensure only requested date range returned
            dates = result.index.get_level_values("date")
            mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
            return result[mask]

    except ImportError:
        pass  # ArcticDB not available, fall through to parquet

    # Legacy parquet fallback
    import hashlib
    h = hashlib.md5("_".join(sorted(symbols)).encode()).hexdigest()[:8]
    cache_path = CACHE_DIR / f"{h}_daily_{start}_{end}.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    bars = _fetch_raw(symbols, start, end)
    bars.to_parquet(cache_path)
    return bars


def warm_cache(symbols: list[str], start: str = "2010-01-01", end: str = None):
    """
    Pre-populate ArcticDB for a list of symbols from start to today.
    Run once to seed the store; subsequent fetch_daily_bars calls will be instant.
    """
    if end is None:
        end = datetime.today().strftime("%Y-%m-%d")
    print(f"Warming ArcticDB cache for {len(symbols)} symbols ({start} → {end})...")
    fetch_daily_bars(symbols, start, end)
    print("Cache warm complete.")
