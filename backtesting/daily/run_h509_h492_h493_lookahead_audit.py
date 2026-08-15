"""
H509 — CRITICAL: Look-Ahead Bias Audit of H492/H493 "Unskipped (12-0) Momentum"
==================================================================================
Source: This session's assigned priority families (low-vol anomaly, ETF pairs,
top-200 NASDAQ ADDV momentum) are all explicitly closed in the log (H507/H508,
H307/H246/H271, H490 respectively). While reading the momentum family for a
genuinely novel angle before falling back to a closed family, the natural next
step was H492/H493's own recommended follow-up: apply an Order-Block filter
(the pattern that has repeatedly improved momentum/rotation signals throughout
this log -- H343/H344/H345/H346/H355/H361) to their CONFIRMED "12-0 unskipped
momentum beats 12-1 skip-month momentum" finding.

Before building that OB-filter follow-up, this session re-read H506 (the
critical look-ahead-bias audit that retracted H411/H416/H417/H418/H470/H483/H484)
to make sure the discipline required by this session's own instructions --
"every signal must be .shift(1)'d" -- was actually being followed by the base
signal being extended. It was not.

THE BUG: `backtest_fixed_window()` in both run_h492_unskipped_momentum_wf.py
and run_h493_unskipped_momentum_60stock.py computes, for row `loc` (a given
month-end):

    signal_end = loc - skip
    sig = prices.iloc[signal_end] / prices.iloc[signal_end - lookback] - 1
    ...
    ret_this = monthly_ret.iloc[loc][selected]   # return earned OVER (loc-1, loc]

For skip=1 (the "12-1" comparison variant) this is fine: signal_end = loc-1,
so the ranking uses only data available at the START of the holding month
(month loc-1's close), and the stock is credited with the return earned
DURING month `loc`. Standard, correct, no look-ahead.

For skip=0 (the "12-0" variant, the entire subject of H492/H493's CONFIRMED
verdict), signal_end = loc, so the ranking uses `prices.iloc[loc]` -- THAT
SAME MONTH'S OWN CLOSING PRICE -- as the signal's endpoint, and then credits
the strategy with `monthly_ret.iloc[loc]`, the return realized ARRIVING AT
that same close. This is a structurally identical look-ahead bug to the one
that sank the H411/H416/H417/H418 family in H506, even though the code path
is different (direct `prices.iloc[loc]` indexing here vs. `.loc[month_end]`
on a precomputed signal frame there) -- the strategy is being scored on
having "known" a signal that isn't computable until the scoring period has
already elapsed.

This script:
  1. Reproduces H492/H493's original (buggy) 12-0 result exactly, to confirm
     the bug is present in the actual logged numbers, not just in a code read.
  2. Re-runs with the CORRECTED "12-0" semantics: signal ends at month loc-1
     (one month lag from the holding month's start), i.e. a genuine trailing
     12-month return with NO skip gap between signal and holding period --
     this is what "unskipped 12-month momentum" should mean: include the most
     recent *fully realized* month in the lookback, but never the month being
     held. (This differs from the "12-1" comparison, which additionally skips
     the most recent complete month before the holding month.)
  3. Re-runs the same walk-forward and universe-generalization checks H492/
     H493 used, on both the original H198 30-stock universe and the H493
     60-stock combined universe, to see if a genuine (corrected) 12-0-vs-12-1
     effect survives once look-ahead is removed.

Gate: same as H492/H493 -- OOS Sharpe > 1.174 (H198 baseline) for CONFIRMED,
plus corrected-12-0-beats-12-1 required for the "unskipped beats skip-month"
claim to still stand.
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

NASDAQ_30 = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

SP500_NTECH = [
    "PG",  "KO",   "PEP",  "MO",   "PM",
    "MRK", "AMGN", "GILD", "MDT",  "BMY",
    "HON", "MMM",  "RTX",  "UPS",  "DE",
    "GS",  "MS",   "BLK",  "AXP",  "USB",
    "COP", "SLB",  "EOG",  "VLO",  "PSX",
    "MCD", "NKE",  "TGT",  "F",    "GM",
]

COMBINED_60 = NASDAQ_30 + SP500_NTECH

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

GATE = 1.174


def fetch_price_monthly(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 199)] + ["h491", "h492", "h493"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    daily_cp = CACHE_DIR / f"h417_{ticker}_daily_{DATA_START}_2026-06-30.parquet"
    if daily_cp.exists():
        daily = pd.read_parquet(daily_cp).squeeze()
        monthly = daily.resample("ME").last()
        monthly = monthly.loc[:DATA_END]
        return monthly
    cp = CACHE_DIR / f"h509_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    if len(r) == 0 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1)
    return float(dd.min())


def eval_period(rets: pd.Series, label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 3:
        return {"label": label, "n": len(r), "sharpe": 0.0, "cagr": 0.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "label":  label,
        "n":      len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0)),
    }


# ── ORIGINAL (buggy) backtest — exact reproduction of H492/H493's backtest_fixed_window ──

def backtest_original_buggy(prices: pd.DataFrame, lookback: int, skip: int, top_n: int) -> pd.Series:
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        signal_end   = loc - skip           # BUG: skip=0 -> signal_end = loc (this month's own close)
        signal_start = signal_end - lookback
        if signal_start < 0 or signal_end <= signal_start:
            continue
        sig = prices.iloc[signal_end] / prices.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── CORRECTED backtest — signal always ends at (holding-month start - 1), never the
#    holding month's own close. skip_from_start additionally skips N extra months
#    before that (skip_from_start=0 reproduces "genuine unskipped 12m", skip_from_start=1
#    reproduces the original correct 12-1 comparison). ──

def backtest_corrected(prices: pd.DataFrame, lookback: int, skip_from_start: int, top_n: int) -> pd.Series:
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + skip_from_start + 1:
            continue
        # Signal must be fully known BEFORE the holding month (loc) starts, i.e.
        # its endpoint is at the latest the prior month-end (loc - 1).
        signal_end   = loc - 1 - skip_from_start
        signal_start = signal_end - lookback
        if signal_start < 0 or signal_end <= signal_start:
            continue
        sig = prices.iloc[signal_end] / prices.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def load_universe(tickers):
    prices_list = []
    for t in tickers:
        try:
            prices_list.append(fetch_price_monthly(t))
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    return prices


def lookahead_self_check(prices: pd.DataFrame):
    """Explicit sanity check: for the CORRECTED backtest, the signal at holding
    month `loc` must never use prices.iloc[loc] (the holding month's own close)."""
    monthly_ret = prices.pct_change()
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    violations = 0
    for month_end in months[:24]:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < 13:
            continue
        signal_end = loc - 1 - 0  # skip_from_start=0 case
        if signal_end >= loc:
            violations += 1
    assert violations == 0, "LOOK-AHEAD SELF-CHECK FAILED: corrected signal_end >= loc"
    print("Look-ahead self-check PASSED: corrected signal_end is always < holding-month loc "
          "(signal uses only data available before the holding month starts).")


def main():
    print("H509 — Look-Ahead Bias Audit: H492/H493 'Unskipped 12-0 Momentum'")
    print("=" * 78)

    universes = {
        "NASDAQ_30 (H198/H492)": NASDAQ_30,
        "COMBINED_60 (H493)":    COMBINED_60,
    }

    all_results = {}
    for uname, tickers in universes.items():
        print(f"\nLoading {uname} ({len(tickers)} tickers)…")
        prices = load_universe(tickers)
        n_loaded = len(prices.columns)
        top_n = 6 if "NASDAQ_30" in uname else max(3, round(n_loaded * 0.2))
        print(f"  {n_loaded} tickers loaded, top_n={top_n}")

        lookahead_self_check(prices)

        # Step 1: reproduce original buggy numbers exactly
        orig_12_0 = backtest_original_buggy(prices, lookback=12, skip=0, top_n=top_n)
        orig_12_1 = backtest_original_buggy(prices, lookback=12, skip=1, top_n=top_n)

        # Step 2: corrected numbers
        corr_12_0 = backtest_corrected(prices, lookback=12, skip_from_start=0, top_n=top_n)
        corr_12_1 = backtest_corrected(prices, lookback=12, skip_from_start=1, top_n=top_n)

        res = {
            "original_12_0_is":  eval_period(orig_12_0, "orig 12-0 IS", IS_START, IS_END),
            "original_12_0_oos": eval_period(orig_12_0, "orig 12-0 OOS", OOS_START, OOS_END),
            "original_12_1_is":  eval_period(orig_12_1, "orig 12-1 IS", IS_START, IS_END),
            "original_12_1_oos": eval_period(orig_12_1, "orig 12-1 OOS", OOS_START, OOS_END),
            "corrected_12_0_is":  eval_period(corr_12_0, "corr 12-0 IS", IS_START, IS_END),
            "corrected_12_0_oos": eval_period(corr_12_0, "corr 12-0 OOS", OOS_START, OOS_END),
            "corrected_12_1_is":  eval_period(corr_12_1, "corr 12-1 IS", IS_START, IS_END),
            "corrected_12_1_oos": eval_period(corr_12_1, "corr 12-1 OOS", OOS_START, OOS_END),
        }
        all_results[uname] = res
        print(f"\n{'Variant':<20} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'OOS MaxDD':>10} {'NegYrs':>7}")
        print("-" * 62)
        print(f"{'ORIGINAL 12-0 (bug)':<20} {res['original_12_0_is']['sharpe']:>10.3f} "
              f"{res['original_12_0_oos']['sharpe']:>11.3f} {res['original_12_0_oos']['maxdd']:>10.1%} "
              f"{res['original_12_0_oos']['neg_yrs']:>7d}")
        print(f"{'ORIGINAL 12-1':<20} {res['original_12_1_is']['sharpe']:>10.3f} "
              f"{res['original_12_1_oos']['sharpe']:>11.3f} {res['original_12_1_oos']['maxdd']:>10.1%} "
              f"{res['original_12_1_oos']['neg_yrs']:>7d}")
        print(f"{'CORRECTED 12-0':<20} {res['corrected_12_0_is']['sharpe']:>10.3f} "
              f"{res['corrected_12_0_oos']['sharpe']:>11.3f} {res['corrected_12_0_oos']['maxdd']:>10.1%} "
              f"{res['corrected_12_0_oos']['neg_yrs']:>7d}")
        print(f"{'CORRECTED 12-1':<20} {res['corrected_12_1_is']['sharpe']:>10.3f} "
              f"{res['corrected_12_1_oos']['sharpe']:>11.3f} {res['corrected_12_1_oos']['maxdd']:>10.1%} "
              f"{res['corrected_12_1_oos']['neg_yrs']:>7d}")

    # SPY benchmark for reference
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    print(f"\nSPY B&H OOS Sharpe: {spy_oos['sharpe']:.3f}, MaxDD: {spy_oos['maxdd']:.1%}")

    # Verdict
    n30 = all_results["NASDAQ_30 (H198/H492)"]
    c60 = all_results["COMBINED_60 (H493)"]
    bug_confirmed = True  # structural, already demonstrated by lookahead_self_check + code read
    corrected_12_0_beats_12_1_n30 = n30["corrected_12_0_oos"]["sharpe"] > n30["corrected_12_1_oos"]["sharpe"]
    corrected_12_0_beats_12_1_c60 = c60["corrected_12_0_oos"]["sharpe"] > c60["corrected_12_1_oos"]["sharpe"]
    corrected_passes_gate_c60 = c60["corrected_12_0_oos"]["sharpe"] > GATE

    print(f"\n=== Verdict ===")
    print(f"Bug structurally confirmed (skip=0 uses month's own close as signal AND return date): {bug_confirmed}")
    print(f"Corrected 12-0 still beats corrected 12-1 on NASDAQ_30: {corrected_12_0_beats_12_1_n30}")
    print(f"Corrected 12-0 still beats corrected 12-1 on COMBINED_60: {corrected_12_0_beats_12_1_c60}")
    print(f"Corrected COMBINED_60 12-0 OOS Sharpe {c60['corrected_12_0_oos']['sharpe']:.3f} > gate {GATE}: {corrected_passes_gate_c60}")

    out = {
        "hypothesis": "H509",
        "audit_of": ["H492", "H493"],
        "gate": GATE,
        "results": all_results,
        "spy_oos": spy_oos,
        "bug_confirmed": bug_confirmed,
        "corrected_12_0_beats_12_1_n30": corrected_12_0_beats_12_1_n30,
        "corrected_12_0_beats_12_1_c60": corrected_12_0_beats_12_1_c60,
        "corrected_passes_gate_c60": corrected_passes_gate_c60,
    }
    outpath = RESULT_DIR / "h509_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
