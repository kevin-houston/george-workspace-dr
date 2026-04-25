"""
ORB signal generation.

Opening range = first 5 minutes of regular session (9:30–9:34 ET inclusive).
Signal fires at the open of bar 6 (9:35 ET).

Long  if bar-6 open > opening_high
Short if bar-6 open < opening_low
No trade otherwise (inside bar)
"""

import pandas as pd
import pytz

ET = pytz.timezone("America/New_York")


def _session_bars(day_df: pd.DataFrame) -> pd.DataFrame:
    """Filter to regular session bars (9:30–15:59 ET) for a single day."""
    et_times = day_df.index.tz_convert(ET)
    mask = (
        (et_times.time >= pd.Timestamp("09:30").time())
        & (et_times.time <= pd.Timestamp("15:59").time())
    )
    return day_df[mask]


def generate_signals(bars: pd.DataFrame) -> pd.DataFrame:
    """
    bars: 1-min OHLCV DataFrame with UTC DatetimeIndex.
    Returns per-day signal DataFrame with columns:
        date, signal (1=long/-1=short/0=no trade),
        entry_price, range_high, range_low, range_size,
        atr14 (populated later by engine for ATR mode)
    """
    bars_et = bars.copy()
    bars_et.index = bars_et.index.tz_convert(ET)

    records = []
    for day, day_df in bars_et.groupby(bars_et.index.date):
        session = _session_bars(day_df)
        if len(session) < 6:
            continue

        opening_range = session.iloc[:5]
        bar6 = session.iloc[5]

        range_high = opening_range["high"].max()
        range_low = opening_range["low"].min()
        range_size = range_high - range_low

        if range_size <= 0:
            continue

        entry_price = bar6["open"]

        if entry_price > range_high:
            signal = 1
        elif entry_price < range_low:
            signal = -1
        else:
            signal = 0

        records.append({
            "date": day,
            "signal": signal,
            "entry_price": entry_price,
            "range_high": range_high,
            "range_low": range_low,
            "range_size": range_size,
            "bar6_time": bar6.name,
            "session_bars": session,  # kept for exit simulation
        })

    return pd.DataFrame([{k: v for k, v in r.items() if k != "session_bars"} for r in records]), records
