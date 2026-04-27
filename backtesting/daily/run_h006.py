"""
H006: Dual Momentum with SGOV safe haven vs. TLT safe haven

Hypothesis: Replacing TLT (long-duration bonds) with SGOV (0-3 month T-bills)
as the risk-off refuge asset fixes the 2022 failure mode of H005, where TLT
fell ~25% simultaneously with equities during the Fed rate hike cycle.

SGOV (iShares 0-3 Month Treasury Bond ETF) launched Sep 2020.
Proxy: we use BIL (iShares 1-3 Month T-Bill ETF, launched 2007) for
in-sample period, then SGOV where available.

Prediction: Dual-momentum + SGOV will outperform Dual-momentum + TLT
in the 2020-2026 OOS period, especially in 2022.
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
    dual_momentum,
    signals_to_weights,
)

SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLY", "XLP", "XLI", "XLU", "XLB"]
BENCHMARK = ["SPY"]
# BIL = 1-3 month T-bills (2007+); proxy for SGOV pre-2020
ALL_SYMS = sorted(set(SECTORS + BENCHMARK + ["TLT", "BIL"]))

IS_START = "2007-11-01"   # BIL launched late 2007
IS_END = "2019-12-31"
OOS_START = "2020-01-01"
OOS_END = "2026-04-01"
STARTING_EQUITY = 100_000.0


def _close_prices(bars: pd.DataFrame, symbols: list) -> pd.DataFrame:
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
    sma = spy_close.rolling(ma_period, min_periods=ma_period).mean()
    return pd.Series(
        np.where(spy_close > sma, "bull", "bear"),
        index=spy_close.index,
    )


def _regime_breakdown(equity_curve: pd.Series, regime: pd.Series) -> dict:
    rets = equity_curve.pct_change().dropna()
    combined = pd.concat([rets, regime.reindex(rets.index)], axis=1)
    combined.columns = ["ret", "regime"]
    return combined.groupby("regime")["ret"].mean().mul(252).round(4).to_dict()


def run_period(label: str, prices_all: pd.DataFrame, start: str, end: str) -> dict:
    close = _close_prices(prices_all, ALL_SYMS)
    close = close.loc[start:end]

    spy = close["SPY"]
    tlt = close.get("TLT")
    bil = close.get("BIL")
    sector_close = close[SECTORS]
    all_dates = close.index
    regime = _tag_regime(spy)

    print(f"\n{'#'*60}")
    print(f"  {label}  ({start} → {end})")
    print(f"{'#'*60}")

    results = {}

    # --- 1. Buy-and-hold SPY ---
    spy_weights = pd.DataFrame({"SPY": 1.0}, index=all_dates)
    bt = DailyBacktester(close[["SPY"]], spy_weights, starting_equity=STARTING_EQUITY)
    eq, tr = bt.run()
    m = compute_metrics(eq, tr)
    m["regime"] = _regime_breakdown(eq, regime)
    results["BH_SPY"] = m
    print_metrics("Buy-and-Hold SPY", m)
    print(f"  Regime returns:   {m['regime']}")

    # --- 2. Dual Momentum + TLT (H005 baseline) ---
    if tlt is not None:
        dm_signals = dual_momentum(sector_close, spy, tlt, top_n=3)
        dm_syms = SECTORS + ["TLT"]
        dm_weights = signals_to_weights(dm_signals, all_dates, dm_syms)
        bt = DailyBacktester(close[dm_syms], dm_weights, starting_equity=STARTING_EQUITY)
        eq, tr = bt.run()
        m = compute_metrics(eq, tr)
        m["regime"] = _regime_breakdown(eq, regime)
        results["DualMom_TLT"] = m
        print_metrics("Dual Momentum + TLT (H005 baseline)", m)
        print(f"  Regime returns:   {m['regime']}")

    # --- 3. Dual Momentum + BIL (SGOV proxy — H006) ---
    if bil is not None:
        dm_signals_bil = dual_momentum(sector_close, spy, bil, top_n=3)
        dm_syms_bil = SECTORS + ["BIL"]
        dm_weights_bil = signals_to_weights(dm_signals_bil, all_dates, dm_syms_bil)
        bt = DailyBacktester(close[dm_syms_bil], dm_weights_bil, starting_equity=STARTING_EQUITY)
        eq, tr = bt.run()
        m = compute_metrics(eq, tr)
        m["regime"] = _regime_breakdown(eq, regime)
        results["DualMom_BIL"] = m
        print_metrics("Dual Momentum + BIL (H006 — SGOV proxy)", m)
        print(f"  Regime returns:   {m['regime']}")

    # --- Summary table ---
    print(f"\n{'─'*72}")
    print(f"  SUMMARY — {label}")
    print(f"  {'Strategy':<35} {'Ann.Ret':>8} {'AfterTax':>9} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7}")
    print(f"{'─'*72}")
    for name, m in results.items():
        if "error" in m:
            continue
        print(
            f"  {name:<35} {m['annualized_return']:>8.2%} {m['after_tax_return']:>9.2%} "
            f"{m['sharpe']:>7.3f} {m['max_drawdown']:>8.2%} {m['calmar']:>7.3f}"
        )
    print(f"{'─'*72}")
    return results


def main():
    print("Fetching data (BIL + TLT + sectors 2007-2026)...")
    bars = fetch_daily_bars(ALL_SYMS, IS_START, OOS_END)

    is_results  = run_period("IN-SAMPLE",              bars, IS_START, IS_END)
    oos_results = run_period("OUT-OF-SAMPLE [LOCKED]", bars, OOS_START, OOS_END)

    # Year-by-year 2020-2026 comparison: TLT vs. BIL
    print(f"\n{'='*72}")
    print("  YEAR-BY-YEAR 2020-2026: DualMom+TLT vs. DualMom+BIL")
    print(f"{'='*72}")

    close_full = _close_prices(
        fetch_daily_bars(ALL_SYMS, OOS_START, OOS_END), ALL_SYMS
    )
    close_full = close_full.loc[OOS_START:OOS_END]

    for year in range(2020, 2027):
        y_start = f"{year}-01-01"
        y_end   = f"{year}-12-31"
        y_close = close_full.loc[y_start:y_end]
        if y_close.empty:
            continue

        spy   = y_close["SPY"]
        tlt   = y_close.get("TLT")
        bil   = y_close.get("BIL")
        secs  = y_close[SECTORS]
        dates = y_close.index

        row = f"  {year}: SPY={spy.pct_change().add(1).prod()-1:+.1%}"

        for safe, label in [(tlt, "TLT"), (bil, "BIL")]:
            if safe is None:
                continue
            sigs = dual_momentum(secs, spy, safe, top_n=3)
            syms = SECTORS + [label]
            wts  = signals_to_weights(sigs, dates, syms)
            bt   = DailyBacktester(y_close[syms], wts, starting_equity=STARTING_EQUITY)
            eq, _ = bt.run()
            ret = eq.iloc[-1] / eq.iloc[0] - 1
            row += f"  DM+{label}={ret:+.1%}"

        # also show what TLT and BIL themselves returned that year
        if tlt is not None:
            row += f"  TLT={tlt.pct_change().add(1).prod()-1:+.1%}"
        if bil is not None:
            row += f"  BIL={bil.pct_change().add(1).prod()-1:+.1%}"

        print(row)

    print(f"{'='*72}")


if __name__ == "__main__":
    main()
