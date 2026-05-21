"""
H208 — FOMC Pre-Meeting Premium
================================
Source: Lucca & Moench (2015, JF) — ~80% of annual US equity premium earned
in the 24h before FOMC rate decisions. ~8 meetings/year; effect is large
relative to frequency.

Design:
  Entry:  Buy SPY at close of day BEFORE FOMC decision day (D-1)
  Exit:   Sell SPY at close of FOMC decision day (D0)
  Hold:   BIL on all other days
  Window: 1 day (close D-1 → close D0)
  Cost:   5 bps each way (2 transitions per event)

Also tests a ±1 day window (close D-2 → close D+1) to capture wider pre-
and post-announcement drift (some studies show drift starts D-2).

IS:  2003–2017  OOS: 2018–2026
Confirm: OOS Sharpe > 0.6 (low bar — this is an infrequent strategy ~8x/year)
Baseline: SPY buy-and-hold, H201 TOM reference
"""

import warnings
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

DATA_START = "2001-01-01"
DATA_END   = "2026-05-20"
IS_START   = pd.Timestamp("2003-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")

COST_BPS = 5  # one-way slippage

# Historical FOMC decision dates (dates the decision was announced)
# Source: Federal Reserve website — all scheduled meeting dates
# Covers 2003-2026. Unscheduled emergency meetings excluded.
FOMC_DATES_RAW = [
    # 2003
    "2003-01-29","2003-03-18","2003-05-06","2003-06-25",
    "2003-08-12","2003-09-16","2003-10-28","2003-12-09",
    # 2004
    "2004-01-28","2004-03-16","2004-05-04","2004-06-30",
    "2004-08-10","2004-09-21","2004-11-10","2004-12-14",
    # 2005
    "2005-02-02","2005-03-22","2005-05-03","2005-06-30",
    "2005-08-09","2005-09-20","2005-11-01","2005-12-13",
    # 2006
    "2006-01-31","2006-03-28","2006-05-10","2006-06-29",
    "2006-08-08","2006-09-20","2006-10-25","2006-12-12",
    # 2007
    "2007-01-31","2007-03-21","2007-05-09","2007-06-28",
    "2007-08-07","2007-09-18","2007-10-31","2007-12-11",
    # 2008
    "2008-01-30","2008-03-18","2008-04-30","2008-06-25",
    "2008-08-05","2008-09-16","2008-10-29","2008-12-16",
    # 2009
    "2009-01-28","2009-03-18","2009-04-29","2009-06-24",
    "2009-08-12","2009-09-23","2009-11-04","2009-12-16",
    # 2010
    "2010-01-27","2010-03-16","2010-04-28","2010-06-23",
    "2010-08-10","2010-09-21","2010-11-03","2010-12-14",
    # 2011
    "2011-01-26","2011-03-15","2011-04-27","2011-06-22",
    "2011-08-09","2011-09-21","2011-11-02","2011-12-13",
    # 2012
    "2012-01-25","2012-03-13","2012-04-25","2012-06-20",
    "2012-08-01","2012-09-13","2012-10-24","2012-12-12",
    # 2013
    "2013-01-30","2013-03-20","2013-05-01","2013-06-19",
    "2013-07-31","2013-09-18","2013-10-30","2013-12-18",
    # 2014
    "2014-01-29","2014-03-19","2014-04-30","2014-06-18",
    "2014-07-30","2014-09-17","2014-10-29","2014-12-17",
    # 2015
    "2015-01-28","2015-03-18","2015-04-29","2015-06-17",
    "2015-07-29","2015-09-17","2015-10-28","2015-12-16",
    # 2016
    "2016-01-27","2016-03-16","2016-04-27","2016-06-15",
    "2016-07-27","2016-09-21","2016-11-02","2016-12-14",
    # 2017
    "2017-02-01","2017-03-15","2017-05-03","2017-06-14",
    "2017-07-26","2017-09-20","2017-11-01","2017-12-13",
    # 2018
    "2018-01-31","2018-03-21","2018-05-02","2018-06-13",
    "2018-08-01","2018-09-26","2018-11-08","2018-12-19",
    # 2019
    "2019-01-30","2019-03-20","2019-05-01","2019-06-19",
    "2019-07-31","2019-09-18","2019-10-30","2019-12-11",
    # 2020
    "2020-01-29","2020-03-15","2020-04-29","2020-06-10",
    "2020-07-29","2020-09-16","2020-11-05","2020-12-16",
    # 2021
    "2021-01-27","2021-03-17","2021-04-28","2021-06-16",
    "2021-07-28","2021-09-22","2021-11-03","2021-12-15",
    # 2022
    "2022-02-02","2022-03-16","2022-05-04","2022-06-15",
    "2022-07-27","2022-09-21","2022-11-02","2022-12-14",
    # 2023
    "2023-02-01","2023-03-22","2023-05-03","2023-06-14",
    "2023-07-26","2023-09-20","2023-11-01","2023-12-13",
    # 2024
    "2024-01-31","2024-03-20","2024-05-01","2024-06-12",
    "2024-07-31","2024-09-18","2024-11-07","2024-12-18",
    # 2025
    "2025-01-29","2025-03-19","2025-05-07","2025-06-18",
    "2025-07-30","2025-09-17","2025-11-07","2025-12-10",
    # 2026
    "2026-01-28","2026-03-18","2026-05-07",
]

FOMC_DATES = pd.to_datetime(FOMC_DATES_RAW)


def sharpe(rets: pd.Series) -> float:
    if rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(252))


def cumul(rets: pd.Series) -> float:
    return float((1 + rets).prod())


def maxdd(rets: pd.Series) -> float:
    eq = (1 + rets).cumprod()
    return float((eq / eq.cummax() - 1).min())


def neg_years(rets: pd.Series) -> int:
    yr = rets.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((yr < 0).sum())


def fetch_close(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h208_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        raw = pd.read_parquet(cp).squeeze().rename(ticker)
        raw.index = pd.to_datetime(raw.index).tz_localize(None)
        return raw
    # Try h201 cache first
    cp2 = CACHE_DIR / f"h201_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp2.exists():
        raw = pd.read_parquet(cp2).squeeze().rename(ticker)
        raw.index = pd.to_datetime(raw.index).tz_localize(None)
        return raw
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    s = raw["Close"].rename(ticker)
    s.index = pd.to_datetime(s.index).tz_localize(None)
    s.to_frame().to_parquet(cp)
    return s


def build_fomc_signal(spy_idx: pd.DatetimeIndex, window_before: int = 1,
                      window_after: int = 0) -> pd.Series:
    """Return 1 on days within the FOMC window, 0 otherwise."""
    fomc_set = set(FOMC_DATES.normalize())
    trading_days = sorted(spy_idx)
    td_arr = pd.DatetimeIndex(trading_days)

    signal = pd.Series(0, index=td_arr)

    for fomc_dt in fomc_set:
        # Find the FOMC decision day in the trading calendar (or nearest)
        pos = td_arr.searchsorted(fomc_dt)
        if pos >= len(td_arr):
            continue
        # Decision day index
        d0 = pos
        start = max(0, d0 - window_before)
        end   = min(len(td_arr) - 1, d0 + window_after)
        signal.iloc[start:end + 1] = 1

    return signal


def run_strategy(spy_ret: pd.Series, bil_ret: pd.Series,
                 signal: pd.Series, cost_bps: float) -> pd.Series:
    """
    signal=1 → hold SPY, signal=0 → hold BIL.
    Apply slippage on transitions.
    """
    aligned_sig = signal.reindex(spy_ret.index).fillna(0)
    transitions = aligned_sig.diff().abs().fillna(0)

    raw = aligned_sig * spy_ret + (1 - aligned_sig) * bil_ret
    cost = transitions * (cost_bps / 10_000)
    return raw - cost


def metrics_dict(rets: pd.Series) -> dict:
    return {
        "sharpe":   round(sharpe(rets), 4),
        "cumul":    round(cumul(rets), 4),
        "maxdd":    round(maxdd(rets), 4),
        "cagr_pct": round(((cumul(rets)) ** (252 / max(len(rets), 1)) - 1) * 100, 2),
        "neg_years": neg_years(rets),
    }


def main():
    print("=" * 60)
    print("H208 — FOMC Pre-Meeting Premium")
    print("=" * 60)

    spy = fetch_close("SPY")
    bil = fetch_close("BIL")

    spy_ret = spy.pct_change().dropna()
    bil_ret = bil.pct_change().dropna()
    common = spy_ret.index.intersection(bil_ret.index)
    spy_ret = spy_ret.loc[common]
    bil_ret = bil_ret.loc[common]

    # Signals: narrow (D-1 → D0) and wide (D-2 → D+1)
    sig_narrow = build_fomc_signal(spy_ret.index, window_before=1, window_after=0)
    sig_wide   = build_fomc_signal(spy_ret.index, window_before=2, window_after=1)

    # Days-invested stats
    pct_narrow = sig_narrow.reindex(spy_ret.index).fillna(0).mean()
    pct_wide   = sig_wide.reindex(spy_ret.index).fillna(0).mean()

    # Strategy returns
    r_narrow = run_strategy(spy_ret, bil_ret, sig_narrow, COST_BPS)
    r_wide   = run_strategy(spy_ret, bil_ret, sig_wide,   COST_BPS)

    # Slice periods
    def s(rets, start, end):
        mask = (rets.index >= start) & (rets.index <= end)
        return rets.loc[mask]

    IS_END   = pd.Timestamp("2017-12-31")

    spy_bh_is  = s(spy_ret, IS_START, IS_END)
    spy_bh_oos = s(spy_ret, OOS_START, pd.Timestamp("2026-05-20"))

    nar_is  = s(r_narrow, IS_START, IS_END)
    nar_oos = s(r_narrow, OOS_START, pd.Timestamp("2026-05-20"))
    wid_is  = s(r_wide,   IS_START, IS_END)
    wid_oos = s(r_wide,   OOS_START, pd.Timestamp("2026-05-20"))

    print(f"\nFOMC events in dataset: {len([d for d in FOMC_DATES if d >= pd.Timestamp(DATA_START)])}")
    print(f"Narrow window (D-1→D0) days invested: {pct_narrow:.1%}")
    print(f"Wide   window (D-2→D+1) days invested: {pct_wide:.1%}")

    rows = {
        "SPY buy-and-hold": {"is": metrics_dict(spy_bh_is),
                             "oos": metrics_dict(spy_bh_oos)},
        "H208-A narrow (D-1→D0)": {"is": metrics_dict(nar_is),
                                    "oos": metrics_dict(nar_oos),
                                    "days_pct": round(pct_narrow * 100, 1)},
        "H208-B wide (D-2→D+1)":  {"is": metrics_dict(wid_is),
                                    "oos": metrics_dict(wid_oos),
                                    "days_pct": round(pct_wide * 100, 1)},
    }

    print(f"\n{'Strategy':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>11} {'OOS Cumul':>10} {'MaxDD':>8}")
    print("-" * 85)
    for name, d in rows.items():
        print(f"{name:<30} {d['is']['sharpe']:>10.3f} {d['is']['cumul']:>10.4f} "
              f"{d['oos']['sharpe']:>11.3f} {d['oos']['cumul']:>10.4f} "
              f"{d['oos']['maxdd']:>8.1%}")

    # Confirm?
    confirmed_a = rows["H208-A narrow (D-1→D0)"]["oos"]["sharpe"] > 0.6
    confirmed_b = rows["H208-B wide (D-2→D+1)"]["oos"]["sharpe"] > 0.6

    print(f"\nH208-A confirmed (OOS Sharpe > 0.6): {confirmed_a}")
    print(f"H208-B confirmed (OOS Sharpe > 0.6): {confirmed_b}")

    result = {
        "hypothesis": "H208",
        "description": "FOMC Pre-Meeting Premium on SPY",
        "confirm_gate": "OOS Sharpe > 0.6",
        "verdict_a": "CONFIRMED" if confirmed_a else "NOT CONFIRMED",
        "verdict_b": "CONFIRMED" if confirmed_b else "NOT CONFIRMED",
        **{k: v for k, v in rows.items()},
    }

    out = RESULT_DIR / "h208_results.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved → {out}")


if __name__ == "__main__":
    main()
