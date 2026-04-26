"""
H005: Sector Momentum Rotation vs. SPY Buy-and-Hold
Strategies: sector_momentum, dual_momentum (§4.1), MA crossover on SPY (§3.12)
Universe: 9 SPDR sector ETFs
In-sample:  2005-01-01 to 2019-12-31
Out-of-sample: 2020-01-01 to 2026-04-01 (LOCKED — OOS)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pandas as pd
import numpy as np

from backtesting.daily.data import fetch_daily_bars
from backtesting.daily.engine import DailyBacktester
from backtesting.daily.metrics import compute_metrics, print_metrics
from backtesting.daily.signals.sector_rotation import (
    sector_momentum,
    dual_momentum,
    signals_to_weights,
)
from backtesting.daily.signals.ma_crossover import dual_ma

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB"]
BENCHMARK = ["SPY"]
TLT = ["TLT"]
ALL_SYMS = sorted(set(SECTORS + BENCHMARK + TLT))

IS_START = "2005-01-01"
IS_END = "2019-12-31"
OOS_START = "2020-01-01"
OOS_END = "2026-04-01"
STARTING_EQUITY = 100_000.0


def _close_prices(bars: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
    """Extract close prices as DatetimeIndex × symbols DataFrame."""
    frames = {}
    for sym in symbols:
        try:
            s = bars.xs(sym, level="symbol")["close"]
            s.index = pd.to_datetime(s.index)
            frames[sym] = s
        except KeyError:
            print(f"WARNING: {sym} not found in data")
    return pd.DataFrame(frames).sort_index()


def _tag_regime(spy_close: pd.Series, ma_period: int = 200) -> pd.Series:
    """'bull' when SPY > SMA(200), 'bear' otherwise."""
    sma = spy_close.rolling(ma_period, min_periods=ma_period).mean()
    return pd.Series(
        np.where(spy_close > sma, "bull", "bear"),
        index=spy_close.index,
    )


def _regime_breakdown(equity_curve: pd.Series, regime: pd.Series) -> dict:
    """Mean daily return by regime."""
    rets = equity_curve.pct_change().dropna()
    combined = pd.concat([rets, regime.reindex(rets.index)], axis=1)
    combined.columns = ["ret", "regime"]
    return combined.groupby("regime")["ret"].mean().mul(252).round(4).to_dict()


def _build_weights_from_signals(
    rebal_signals: dict,
    all_dates: pd.DatetimeIndex,
    all_symbols: list[str],
) -> pd.DataFrame:
    return signals_to_weights(rebal_signals, all_dates, all_symbols)


def run_period(label: str, prices_all: pd.DataFrame, start: str, end: str) -> None:
    """Run all strategies for a given period and print results."""
    close = _close_prices(prices_all, ALL_SYMS)
    close = close.loc[start:end]

    spy = close["SPY"]
    tlt = close["TLT"] if "TLT" in close.columns else None
    sector_close = close[SECTORS]

    all_dates = close.index
    regime = _tag_regime(spy)

    print(f"\n{'#'*60}")
    print(f"  {label}  ({start} → {end})")
    print(f"{'#'*60}")

    results = {}

    # --- 1. Buy-and-hold SPY ---
    spy_weights = pd.DataFrame({"SPY": 1.0}, index=all_dates)
    bt = DailyBacktester(close[["SPY"]], spy_weights[["SPY"]], starting_equity=STARTING_EQUITY)
    eq, tr = bt.run()
    m = compute_metrics(eq, tr)
    m["regime"] = _regime_breakdown(eq, regime)
    results["BH_SPY"] = m
    print_metrics("Buy-and-Hold SPY", m)
    print(f"  Regime returns:   {m['regime']}")

    # --- 2. Sector Momentum (top 3, 12-1 momentum) ---
    sec_signals = sector_momentum(sector_close, top_n=3, formation_months=12, skip_months=1)
    sec_weights = _build_weights_from_signals(sec_signals, all_dates, SECTORS)
    bt = DailyBacktester(close[SECTORS], sec_weights, starting_equity=STARTING_EQUITY)
    eq, tr = bt.run()
    m = compute_metrics(eq, tr)
    m["regime"] = _regime_breakdown(eq, regime)
    results["SectorMom"] = m
    print_metrics("Sector Momentum (12-1, top-3)", m)
    print(f"  Regime returns:   {m['regime']}")

    # --- 3. Dual Momentum (sector + SPY filter → TLT safe haven) ---
    if tlt is not None:
        dm_signals = dual_momentum(
            sector_close, spy, tlt,
            formation_months=12, ma_period=200, top_n=3,
        )
        dm_all_syms = SECTORS + ["TLT"]
        dm_weights = _build_weights_from_signals(dm_signals, all_dates, dm_all_syms)
        bt = DailyBacktester(close[dm_all_syms], dm_weights, starting_equity=STARTING_EQUITY)
        eq, tr = bt.run()
        m = compute_metrics(eq, tr)
        m["regime"] = _regime_breakdown(eq, regime)
        results["DualMom"] = m
        print_metrics("Dual Momentum (+ SPY/TLT filter)", m)
        print(f"  Regime returns:   {m['regime']}")
    else:
        print("  Skipping dual momentum: TLT data not available")

    # --- 4. MA Crossover on SPY (SMA 10/30) ---
    ma_signal = dual_ma(spy, fast=10, slow=30)
    # Convert signal series to DataFrame of weights aligned to all_dates
    ma_weights = pd.DataFrame({"SPY": ma_signal.reindex(all_dates, fill_value=0).astype(float)})
    bt = DailyBacktester(close[["SPY"]], ma_weights, starting_equity=STARTING_EQUITY)
    eq, tr = bt.run()
    m = compute_metrics(eq, tr)
    m["regime"] = _regime_breakdown(eq, regime)
    results["MA_10_30_SPY"] = m
    print_metrics("MA Crossover SPY (SMA 10/30)", m)
    print(f"  Regime returns:   {m['regime']}")

    # --- Summary table ---
    print(f"\n{'─'*72}")
    print(f"  SUMMARY — {label}")
    print(f"  {'Strategy':<30} {'Ann.Ret':>8} {'AfterTax':>9} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7}")
    print(f"{'─'*72}")
    for name, m in results.items():
        if "error" in m:
            continue
        print(
            f"  {name:<30} {m['annualized_return']:>8.2%} {m['after_tax_return']:>9.2%} "
            f"{m['sharpe']:>7.3f} {m['max_drawdown']:>8.2%} {m['calmar']:>7.3f}"
        )
    print(f"{'─'*72}")


def main():
    print("Fetching data...")
    bars = fetch_daily_bars(ALL_SYMS, IS_START, OOS_END)

    run_period("IN-SAMPLE", bars, IS_START, IS_END)

    print("\n" + "!"*60)
    print("  NOTE: Out-of-sample results below are LOCKED (no further")
    print("  parameter tuning allowed after viewing these results).")
    print("!"*60)
    run_period("OUT-OF-SAMPLE [LOCKED]", bars, OOS_START, OOS_END)


if __name__ == "__main__":
    main()
