"""Moving-average crossover signal generators."""

import pandas as pd


def single_ma(prices: pd.Series, ma_period: int = 200) -> pd.Series:
    """Long when price > SMA(ma_period), flat otherwise. Returns {1, 0}."""
    sma = prices.rolling(ma_period, min_periods=ma_period).mean()
    return (prices > sma).astype(int)


def dual_ma(prices: pd.Series, fast: int = 10, slow: int = 30, allow_short: bool = False) -> pd.Series:
    """Long when SMA(fast) > SMA(slow). If allow_short, -1 when inverted."""
    fast_ma = prices.rolling(fast, min_periods=fast).mean()
    slow_ma = prices.rolling(slow, min_periods=slow).mean()
    signal = pd.Series(0, index=prices.index, dtype=int)
    signal[fast_ma > slow_ma] = 1
    if allow_short:
        signal[fast_ma < slow_ma] = -1
    return signal


def triple_ma(prices: pd.Series, t1: int = 3, t2: int = 10, t3: int = 21) -> pd.Series:
    """Long when MA(t1) > MA(t2) > MA(t3); short when MA(t1) < MA(t2) < MA(t3)."""
    ma1 = prices.rolling(t1, min_periods=t1).mean()
    ma2 = prices.rolling(t2, min_periods=t2).mean()
    ma3 = prices.rolling(t3, min_periods=t3).mean()
    signal = pd.Series(0, index=prices.index, dtype=int)
    signal[(ma1 > ma2) & (ma2 > ma3)] = 1
    signal[(ma1 < ma2) & (ma2 < ma3)] = -1
    return signal
