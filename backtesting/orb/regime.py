"""
Macro regime tagging via FRED USREC series.
Returns a dict mapping date -> regime ('expansion' | 'contraction').
"""

import os
from functools import lru_cache

import pandas as pd


@lru_cache(maxsize=1)
def load_recession_dates() -> pd.Series:
    """USREC: 1 = recession month, 0 = expansion. Monthly frequency."""
    from fredapi import Fred
    fred = Fred(api_key=os.environ["FRED_API_KEY"])
    usrec = fred.get_series("USREC", observation_start="2010-01-01")
    usrec.index = pd.to_datetime(usrec.index)
    return usrec


def tag_regime(trading_date: pd.Timestamp) -> str:
    usrec = load_recession_dates()
    # Find the most recent USREC observation at or before this date
    month_start = trading_date.replace(day=1)
    mask = usrec.index <= month_start
    if not mask.any():
        return "expansion"
    val = usrec[mask].iloc[-1]
    return "contraction" if val == 1 else "expansion"


def tag_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Add a 'regime' column to a per-trade or per-day DataFrame with a 'date' column."""
    df = df.copy()
    df["regime"] = df["date"].apply(lambda d: tag_regime(pd.Timestamp(d)))
    return df
