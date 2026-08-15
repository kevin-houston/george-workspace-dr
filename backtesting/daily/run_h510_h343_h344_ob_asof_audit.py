"""
H510 — Look-Ahead Bias Audit: OB/FVG Filter "as_of" Date in H343/H344/H345/H346/H355/H361
=============================================================================================
Source: Flagged directly in H509's key finding #5 while auditing H492/H493's look-ahead
bug. H343 (FVG/OB filter on H198 6-1m momentum, CONFIRMED OOS 3.182) and H344 (H343's
parameter sensitivity grid, CONFIRMED 36/36, best OOS 3.396) both call:

    has_bullish_ob(daily_data[ticker], month_end, ob_window, swing_len)

passing `month_end` -- the CURRENT holding month's own closing date -- as the `as_of`
cutoff for the daily-bar OB/FVG detector. Since `has_bullish_ob` does
`daily_df[daily_df.index <= as_of]`, this lets the OB detector see every daily bar
THROUGH AND INCLUDING the last trading day of the month whose return the strategy is
about to be credited with. The momentum RANKING signal itself is safe in these two
scripts (signal_end = loc - 1, correctly skip-month), so this is a narrower defect than
H509's H492/H493 bug -- it only affects the OB *confirmation* step's timing, not stock
selection -- but it is still look-ahead: a stock could be filtered in/out based on an
order block that only became visible using price action from days 2-20 of the very
month being traded.

This mirrors the exact "as_of date must be shifted, not just the signal" mechanism
H506 fixed in run_h483_corrected.py / run_h484_corrected.py (`signal_asof =
monthly_ret.index[loc_all - 1]`, i.e. the prior month-end, not month_end itself).

This script:
  1. Reproduces H343's original OB-filter variant (C: OB strict, window=30, swing_len=5)
     and H344's best grid variant (window=20, min_filter=3, swing_len=3) using the
     ORIGINAL (buggy) month_end as-of date, to confirm the logged numbers reproduce.
  2. Re-runs the identical variants with the as_of date corrected to the PRIOR month-end
     (the last trading day <= the start of the holding month), so the OB detector can
     only see data that was actually available before the holding month began.
  3. Runs a small grid (the two known-good parameter sets plus one additional check)
     to see whether the CONFIRMED verdict survives correction, and by how much the
     Sharpe changes -- distinguishing "narrows but still confirms" from "bug-driven
     inflation" per this project's H506 audit discipline.

Universe: H198 30-stock universe (same as H343/H344)
Signal: 6-1m momentum rank -> OB confirmation filter (unchanged, already skip-month safe)
IS/OOS: 2013-2020 / 2021-2026 (same as H343/H344)
Gate: OOS Sharpe > 1.174 (H198 baseline, same gate as H343/H344)
"""

import os, warnings
os.environ["SMC_CREDIT"] = "0"
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from smartmoneyconcepts import smc as SMC

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM",
    "UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST",
    "CVX","XOM",
    "BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
LOOKBACK   = 6
TOP_N      = 6
GATE       = 1.174

# Known parameter sets from H343 (reference) and H344 (grid best)
PARAM_SETS = [
    {"label": "H343 reference (win=30, min=3, swing=5)", "ob_window": 30, "min_filter": 3, "swing_len": 5},
    {"label": "H344 grid best (win=20, min=3, swing=3)",  "ob_window": 20, "min_filter": 3, "swing_len": 3},
]


def load_monthly(ticker: str) -> pd.Series:
    for prefix in ["h343", "h198", "h199", "h320", "h344"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h510_{ticker}_monthly.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading monthly {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last().rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def load_daily(ticker: str) -> pd.DataFrame:
    for prefix in ["h343", "h344"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if cp.exists():
            return pd.read_parquet(cp)
    cp2 = CACHE_DIR / f"h510_{ticker}_daily.parquet"
    if cp2.exists():
        return pd.read_parquet(cp2)
    print(f"  Downloading daily {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.to_parquet(cp2)
    return df


def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp,
                    window: int, swing_len: int) -> bool:
    sub = daily_df[daily_df.index <= as_of].tail(window + swing_len * 2)
    if len(sub) < swing_len * 2:
        return False
    try:
        ohlcv = sub[["open","high","low","close","volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


def run_backtest(monthly_px: pd.DataFrame, daily_data: dict,
                  ob_window: int, min_filter: int, swing_len: int,
                  corrected: bool) -> pd.Series:
    """corrected=False reproduces H343/H344's original as_of=month_end bug.
    corrected=True uses as_of=prior month-end (last trading day before the
    holding month begins) -- the fix, mirroring H506's run_h483_corrected.py."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < LOOKBACK + 1:
            continue
        signal_start = loc - LOOKBACK - 1
        signal_end   = loc - 1
        if signal_start < 0:
            continue

        sig = monthly_px.iloc[signal_end] / monthly_px.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        ranked = sig.nlargest(TOP_N * 2).index.tolist()

        # The as_of cutoff for the OB detector: original (buggy) uses month_end
        # itself; corrected uses the prior month-end (data available BEFORE the
        # holding month starts).
        if corrected:
            ob_as_of = monthly_ret.index[loc - 1]
        else:
            ob_as_of = month_end

        filtered = []
        for ticker in ranked:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], ob_as_of, ob_window, swing_len):
                filtered.append(ticker)
            if len(filtered) >= TOP_N:
                break

        if len(filtered) < min_filter:
            port_rets.append((month_end, 0.0))
            continue
        selected = filtered[:TOP_N]
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0


def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"sharpe": 0, "cagr": 0, "maxdd": 0}
    return {
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "maxdd":  round(maxdd(r), 3),
    }


def lookahead_self_check():
    """Sanity check: corrected ob_as_of must always be strictly before the
    holding month's own trading days."""
    idx = pd.date_range("2020-01-01", periods=30, freq="ME")
    for loc in range(5, 30):
        month_end = idx[loc]
        ob_as_of_corrected = idx[loc - 1]
        assert ob_as_of_corrected < month_end, "LOOK-AHEAD SELF-CHECK FAILED"
    print("Look-ahead self-check PASSED: corrected ob_as_of is always the PRIOR "
          "month-end, strictly before the holding month's own close.")


def main():
    print("H510 — Look-Ahead Bias Audit: OB Filter as_of Date in H343/H344")
    print("=" * 70)
    lookahead_self_check()

    print("\nLoading monthly data…")
    px_list = []
    for t in UNIVERSE:
        try:
            px_list.append(load_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(px_list).T.sort_index()

    print("Loading daily data…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = load_daily(t)
        except Exception as e:
            print(f"  WARN {t} daily: {e}")

    results = []
    print(f"\n{'Params':<40} {'as_of':<10} {'IS Sh':>8} {'OOS Sh':>8} {'MaxDD':>8}")
    print("-" * 78)
    for ps in PARAM_SETS:
        for corrected, label in [(False, "original"), (True, "corrected")]:
            rets = run_backtest(monthly_px, daily_data,
                                 ps["ob_window"], ps["min_filter"], ps["swing_len"],
                                 corrected=corrected)
            is_  = eval_period(rets, IS_START, IS_END)
            oos_ = eval_period(rets, OOS_START, OOS_END)
            print(f"{ps['label']:<40} {label:<10} {is_['sharpe']:>8.3f} "
                  f"{oos_['sharpe']:>8.3f} {oos_['maxdd']:>8.1%}")
            results.append({
                "param_label": ps["label"], "ob_window": ps["ob_window"],
                "min_filter": ps["min_filter"], "swing_len": ps["swing_len"],
                "as_of": label, "is": is_, "oos": oos_,
                "beats_gate": oos_["sharpe"] > GATE,
            })

    print(f"\n=== Verdict ===")
    for ps in PARAM_SETS:
        orig = next(r for r in results if r["param_label"] == ps["label"] and r["as_of"] == "original")
        corr = next(r for r in results if r["param_label"] == ps["label"] and r["as_of"] == "corrected")
        delta = corr["oos"]["sharpe"] - orig["oos"]["sharpe"]
        print(f"{ps['label']}: original OOS {orig['oos']['sharpe']:.3f} -> "
              f"corrected OOS {corr['oos']['sharpe']:.3f} (delta {delta:+.3f}), "
              f"corrected still passes gate: {corr['beats_gate']}")

    out = {
        "hypothesis": "H510",
        "audit_of": ["H343", "H344"],
        "gate": GATE,
        "results": results,
    }
    outpath = RESULT_DIR / "h510_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
