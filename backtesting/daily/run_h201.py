"""
H201 — Turn-of-Month (TOM) Effect
===================================
Source: Ariel (1987), Lakonishok & Smidt (1988); §3.6 "151 Trading Strategies"

Hypothesis: US equities generate abnormally high returns in the 5 trading days
surrounding month-end (days -1 to +3, where day 0 = first trading day of month).
The effect is attributed to institutional rebalancing flows and pension contributions.

Strategy:
  - Hold SPY (or H026 sector-rotation universe) only during TOM window
  - Hold BIL (T-bill) or cash outside the TOM window
  - TOM window: last 1 trading day of month + first 3 trading days of next month

Universe: SPY (scalar test), then H026 ETF universe (production relevance test)
IS:  2003-2017, OOS: 2018-2026 (longer IS for calendar effect — needs many years)
Confirm: OOS Sharpe > 0.5, OOS Cumul > 1.3×, Corr(TOM, H026) < 0.5
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
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2003-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOM_BEFORE = 1   # last N trading days of month included in TOM window
TOM_AFTER  = 3   # first N trading days of new month included in TOM window
COST_BPS   = 5   # one-way cost in bps (for each transition in/out)

H026_ASSETS = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO",
]


def fetch_daily(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in list(range(113, 153)) + list(range(181, 201))]:
        for suffix in ["close", "ohlc"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_{suffix}_{DATA_START}_{DATA_END}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h201_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def is_tom_day(date: pd.Timestamp, trading_days: pd.DatetimeIndex) -> bool:
    """Return True if date is within the TOM window."""
    loc = trading_days.get_loc(date)
    # Find last trading day of date's month
    same_month = trading_days[(trading_days.year == date.year) &
                               (trading_days.month == date.month)]
    if len(same_month) == 0:
        return False
    last_of_month = same_month[-1]
    last_loc = trading_days.get_loc(last_of_month)

    # TOM window: last TOM_BEFORE days of month + first TOM_AFTER days of next month
    tom_start = last_loc - TOM_BEFORE + 1
    tom_end   = last_loc + TOM_AFTER

    return tom_start <= loc <= tom_end


def build_tom_mask_params(trading_days: pd.DatetimeIndex,
                          before: int, after: int) -> pd.Series:
    """Boolean series: True on TOM days."""
    mask = pd.Series(False, index=trading_days)
    monthly_ends = trading_days.to_series().groupby(
        [trading_days.year, trading_days.month]).last().values

    for month_end in monthly_ends:
        end_loc = trading_days.get_loc(month_end)
        tom_start = max(0, end_loc - before + 1)
        tom_end   = min(len(trading_days) - 1, end_loc + after)
        mask.iloc[tom_start:tom_end + 1] = True

    return mask


def build_tom_mask(trading_days: pd.DatetimeIndex) -> pd.Series:
    return build_tom_mask_params(trading_days, TOM_BEFORE, TOM_AFTER)


def sharpe(r: pd.Series) -> float:
    if len(r) < 20 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(252))


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def eval_period(rets: pd.Series, label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)].dropna()
    if len(r) < 20:
        return {"label": label, "n": 0}
    ann_r = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return {
        "label":   label,
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 252), 3),
        "cumul":   round(cumul(r), 4),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": int((ann_r < 0).sum()),
    }


def backtest_tom(asset_ret: pd.Series, cash_ret: pd.Series,
                 tom_mask: pd.Series) -> pd.Series:
    """
    Hold asset on TOM days, cash otherwise.
    Apply transaction cost on each transition.
    """
    aligned = asset_ret.index.intersection(cash_ret.index).intersection(tom_mask.index)
    ar = asset_ret.loc[aligned]
    cr = cash_ret.loc[aligned]
    tm = tom_mask.loc[aligned]

    ret = pd.Series(index=aligned, dtype=float)
    prev_tom = False
    for date in aligned:
        in_tom = tm.loc[date]
        ret.loc[date] = ar.loc[date] if in_tom else cr.loc[date]
        if in_tom != prev_tom:
            ret.loc[date] -= COST_BPS / 10000
        prev_tom = in_tom

    return ret


def main():
    print("H201 — Turn-of-Month Effect")
    print("Loading SPY and BIL…")

    spy_ret = fetch_daily("SPY").pct_change().rename("SPY")
    bil_ret = fetch_daily("BIL").pct_change().rename("BIL")

    trading_days = spy_ret.dropna().index
    tom_mask = build_tom_mask(trading_days)

    print(f"  TOM window: {tom_mask.sum()} / {len(tom_mask)} trading days "
          f"({tom_mask.mean()*100:.1f}%)\n")

    # --- Experiment A: SPY-only TOM vs Buy-and-Hold ---
    print("=== Experiment A: SPY TOM timing (hold SPY on TOM, BIL otherwise) ===")
    spy_full = spy_ret.loc[IS_START:OOS_END].dropna()
    bil_full = bil_ret.loc[IS_START:OOS_END].dropna()
    tom_aligned = tom_mask.loc[IS_START:OOS_END]

    tom_strat = backtest_tom(spy_full, bil_full, tom_aligned)

    is_tom  = eval_period(tom_strat, "IS  2003-2017", IS_START, IS_END)
    oos_tom = eval_period(tom_strat, "OOS 2018-2026", OOS_START, OOS_END)
    is_spy  = eval_period(spy_full,  "SPY IS",        IS_START, IS_END)
    oos_spy = eval_period(spy_full,  "SPY OOS",       OOS_START, OOS_END)

    header = f"{'Period':<18} {'Sharpe':>8} {'CAGR%':>8} {'Cumul':>8} {'MaxDD':>8} {'NegYrs':>7}"
    print(header)
    print("─" * 62)
    for res in [is_tom, oos_tom, is_spy, oos_spy]:
        if res["n"] == 0:
            print(f"  {res['label']:<16} — insufficient data")
            continue
        print(f"  {res['label']:<16} {res['sharpe']:>8.3f} {res['cagr']*100:>7.1f}% "
              f"{res['cumul']:>8.4f} {res['maxdd']*100:>7.1f}% {res['neg_yrs']:>7}")

    # TOM vs non-TOM raw return comparison
    spy_day = spy_full.loc[IS_START:OOS_END]
    tom_days_ret   = spy_day[tom_aligned.reindex(spy_day.index).fillna(False)]
    nontom_days_ret = spy_day[~tom_aligned.reindex(spy_day.index).fillna(False)]
    print(f"\n  TOM days mean daily return:     {tom_days_ret.mean()*100:+.3f}%")
    print(f"  Non-TOM days mean daily return: {nontom_days_ret.mean()*100:+.3f}%")
    print(f"  TOM premium: {(tom_days_ret.mean() - nontom_days_ret.mean())*100:+.3f}% per day")

    # --- Experiment B: TOM window sensitivity (±1 day) ---
    print("\n=== Experiment B: TOM window sensitivity (OOS Sharpe) ===")
    print(f"  {'Window':<20} {'OOS Sharpe':>10} {'OOS CAGR':>10}")
    best_window = (TOM_BEFORE, TOM_AFTER)
    best_sharpe = oos_tom.get("sharpe", -99)
    for before in [1, 2]:
        for after in [2, 3, 4]:
            m = build_tom_mask_params(trading_days, before, after)
            s = backtest_tom(spy_full, bil_full, m.loc[IS_START:OOS_END])
            res = eval_period(s, "", OOS_START, OOS_END)
            sh = res.get("sharpe", -99)
            cagr = res.get("cagr", 0)
            marker = " ←" if sh > best_sharpe else ""
            if sh > best_sharpe:
                best_sharpe = sh
                best_window = (before, after)
            print(f"  before={before} after={after}: {sh:>10.3f} {cagr*100:>9.1f}%{marker}")
    best_before, best_after = best_window
    print(f"\n  Best window: last {best_before} + first {best_after} days")

    # Rebuild with best window
    tom_mask = build_tom_mask_params(trading_days, best_before, best_after)
    tom_strat = backtest_tom(spy_full, bil_full, tom_mask.loc[IS_START:OOS_END])
    oos_tom_best = eval_period(tom_strat, "OOS (best window)", OOS_START, OOS_END)

    # Correlation with H026
    print("\n=== Correlation with H026 (production ETF rotation) ===")
    h026_cp = CACHE_DIR / "h026_monthly_returns.parquet"
    corr_h026 = None
    if h026_cp.exists():
        h026_m = pd.read_parquet(h026_cp).squeeze()
        tom_m = tom_strat.resample("ME").apply(lambda x: (1 + x).prod() - 1)
        common = tom_m.index.intersection(h026_m.index)
        oos_idx = (common >= OOS_START) & (common <= OOS_END)
        if oos_idx.sum() > 12:
            corr_h026 = float(tom_m.loc[common[oos_idx]].corr(h026_m.loc[common[oos_idx]]))
            print(f"  Corr(TOM, H026) OOS = {corr_h026:.3f}")
    if corr_h026 is None:
        print("  H026 returns cache not found — skipping correlation check")

    # SPY correlation
    tom_m = tom_strat.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    spy_m = spy_full.resample("ME").apply(lambda x: (1 + x).prod() - 1)
    common = tom_m.index.intersection(spy_m.index)
    oos_idx = (common >= OOS_START) & (common <= OOS_END)
    corr_spy = float(tom_m.loc[common[oos_idx]].corr(spy_m.loc[common[oos_idx]]))

    oos_sharpe = oos_tom_best.get("sharpe", 0)
    oos_cumul  = oos_tom_best.get("cumul", 0)
    confirmed  = oos_sharpe > 0.5 and oos_cumul > 1.3

    print(f"\n=== Final Verdict ===")
    print(f"  OOS Sharpe = {oos_sharpe:.3f}  (need > 0.5)")
    print(f"  OOS Cumul  = {oos_cumul:.4f}× (need > 1.3×)")
    print(f"  Corr SPY   = {corr_spy:.3f}")
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    results = {
        "hypothesis": "H201",
        "description": "Turn-of-Month Effect (SPY TOM timing)",
        "source": "Ariel (1987), 151 Strategies §3.6",
        "best_window": {"before": best_before, "after": best_after},
        "is":  is_tom,
        "oos": oos_tom_best,
        "spy_oos": oos_spy,
        "corr_spy_oos": round(corr_spy, 4),
        "corr_h026_oos": round(corr_h026, 4) if corr_h026 else None,
        "confirmed": confirmed,
    }
    out = RESULT_DIR / "h201_turn_of_month.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved → {out}")
    return results


if __name__ == "__main__":
    main()
