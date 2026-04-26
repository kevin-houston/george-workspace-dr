"""Sector rotation signal generators (Kakushadze & Serur §4.1)."""

from typing import Optional
import pandas as pd


def _month_ends(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Return the last trading day of each month present in index."""
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.resample("ME").last().dropna().values)


def sector_momentum(
    prices_df: pd.DataFrame,
    top_n: int = 3,
    formation_months: int = 12,
    skip_months: int = 1,
) -> dict:
    """
    Monthly sector momentum rotation.
    Returns dict: date → {symbol: weight}, only on rebalance days.
    Lookback = formation_months - skip_months, skipping most recent skip_months.
    """
    rebalance_dates = _month_ends(prices_df.index)
    signals = {}

    for rebal_date in rebalance_dates:
        # Formation window: from (formation_months) ago to (skip_months) ago
        end_formation = rebal_date - pd.offsets.MonthBegin(skip_months)
        start_formation = rebal_date - pd.offsets.MonthBegin(formation_months)

        window = prices_df.loc[start_formation:end_formation]
        if len(window) < 20:
            continue

        returns = (window.iloc[-1] / window.iloc[0]) - 1
        returns = returns.dropna()
        if len(returns) < top_n:
            continue

        top_syms = returns.nlargest(top_n).index.tolist()
        weight = 1.0 / top_n
        signals[rebal_date] = {sym: weight for sym in top_syms}

    return signals


def dual_momentum(
    sector_prices: pd.DataFrame,
    spy_prices: pd.Series,
    tlt_prices: pd.Series,
    formation_months: int = 12,
    ma_period: int = 200,
    top_n: int = 3,
) -> dict:
    """
    Dual momentum: sector momentum but if SPY < SMA(ma_period), hold TLT instead.
    Returns dict: date → {symbol: weight}.
    """
    spy_sma = spy_prices.rolling(ma_period, min_periods=ma_period).mean()

    sector_signals = sector_momentum(
        sector_prices, top_n=top_n, formation_months=formation_months
    )

    signals = {}
    for rebal_date, weights in sector_signals.items():
        # Use SPY close on the rebalance date (or last available)
        available_spy = spy_prices.loc[:rebal_date].dropna()
        available_sma = spy_sma.loc[:rebal_date].dropna()
        if available_spy.empty or available_sma.empty:
            signals[rebal_date] = weights
            continue

        spy_close = available_spy.iloc[-1]
        sma_val = available_sma.iloc[-1]

        if spy_close < sma_val:
            # Risk-off: go to TLT
            signals[rebal_date] = {"TLT": 1.0}
        else:
            signals[rebal_date] = weights

    return signals


def signals_to_weights(
    signals: dict,
    all_dates: pd.DatetimeIndex,
    all_symbols: list,
) -> pd.DataFrame:
    """
    Expand a rebalance-date signals dict into a daily weight DataFrame.
    Forward-fills weights between rebalance dates.
    Returns DataFrame: DatetimeIndex × symbols, values = target weight.
    """
    weights = pd.DataFrame(0.0, index=all_dates, columns=all_symbols)

    rebal_dates = sorted(signals.keys())
    for i, rdate in enumerate(rebal_dates):
        # Find the first trading day on or after the rebalance date (signal executes next day)
        valid_dates = all_dates[all_dates > rdate]
        if valid_dates.empty:
            continue
        exec_date = valid_dates[0]
        weights.loc[exec_date:, :] = 0.0
        for sym, w in signals[rdate].items():
            if sym in weights.columns:
                weights.loc[exec_date:, sym] = w

        # Zero out after next rebal date's exec to avoid forward-fill bleed
        if i + 1 < len(rebal_dates):
            next_exec_dates = all_dates[all_dates > rebal_dates[i + 1]]
            if not next_exec_dates.empty:
                next_exec = next_exec_dates[0]
                weights.loc[next_exec:, :] = 0.0  # will be overwritten by next iteration

    return weights
