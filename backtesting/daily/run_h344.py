"""
H344 — H343 OB Filter Sensitivity Analysis
===========================================
H343 (OB strict filter on H198 momentum) returned OOS Sharpe 3.182 — extraordinary.
This script stress-tests whether that result is robust to parameter choices:

  Parameters varied:
    OB_WINDOW   : trading days to look back for unmitigated bullish OB [15, 20, 30, 45]
    MIN_FILTER  : min stocks passing OB filter to enter (else cash)    [2, 3, 4]
    SWING_LEN   : swing_highs_lows period                              [3, 5, 7]

  Reference: H343 used OB_WINDOW=30, MIN_FILTER=3, SWING_LEN≈5

  If OOS Sharpe remains >> 1.174 across most of the grid, the signal is robust.
  If performance is knife-edged around H343's exact parameters, the result is fragile.

Universe: H198 30 large-cap stocks
Signal:   6-1m momentum rank → OB confirmation filter (strict mode)
IS: 2013-2020  OOS: 2021-2026  Gate: OOS Sharpe > 1.174
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

# Parameter grid
OB_WINDOWS   = [15, 20, 30, 45]
MIN_FILTERS  = [2, 3, 4]
SWING_LENS   = [3, 5, 7]


# ── Data loading ─────────────────────────────────────────────────────────────

def load_monthly(ticker: str) -> pd.Series:
    for prefix in ["h343", "h198", "h199", "h320"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h344_{ticker}_monthly.parquet"
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
    cp = CACHE_DIR / f"h343_{ticker}_daily.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    cp2 = CACHE_DIR / f"h344_{ticker}_daily.parquet"
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


# ── OB detection ─────────────────────────────────────────────────────────────

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


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_backtest(monthly_px: pd.DataFrame, daily_data: dict,
                 ob_window: int, min_filter: int, swing_len: int) -> pd.Series:
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

        filtered = []
        for ticker in ranked:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], month_end, ob_window, swing_len):
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


# ── Metrics ──────────────────────────────────────────────────────────────────

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


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H344 — OB Filter Sensitivity Analysis (H343 robustness check)")
    print("=" * 65)

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

    GATE = 1.174
    results = []
    total = len(OB_WINDOWS) * len(MIN_FILTERS) * len(SWING_LENS)
    done  = 0

    print(f"\n{'Win':>4} {'Min':>4} {'Swg':>4} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 60)

    for ob_window in OB_WINDOWS:
        for min_filter in MIN_FILTERS:
            for swing_len in SWING_LENS:
                rets = run_backtest(monthly_px, daily_data,
                                    ob_window, min_filter, swing_len)
                is_  = eval_period(rets, IS_START, IS_END)
                oos_ = eval_period(rets, OOS_START, OOS_END)
                # cash months in OOS
                oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
                cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
                beats = oos_["sharpe"] > GATE
                done += 1
                print(f"{ob_window:>4} {min_filter:>4} {swing_len:>4} "
                      f"{is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
                      f"{oos_['maxdd']:>8.1%} {cash_pct:>6.1f}% "
                      f"{'✓' if beats else '✗':>6}")
                results.append({
                    "ob_window": ob_window,
                    "min_filter": min_filter,
                    "swing_len": swing_len,
                    "is": is_,
                    "oos": oos_,
                    "oos_cash_pct": round(cash_pct, 1),
                    "beats_gate": beats,
                })

    n_pass = sum(r["beats_gate"] for r in results)
    print(f"\n=== Summary ===")
    print(f"Variants passing gate (OOS Sharpe > {GATE}): {n_pass}/{total}")
    print(f"H343 reference: OB_WINDOW=30, MIN_FILTER=3, SWING_LEN≈5  → OOS 3.182")
    best = max(results, key=lambda r: r["oos"]["sharpe"])
    print(f"Best OOS Sharpe: {best['oos']['sharpe']:.3f} "
          f"(window={best['ob_window']}, min_filter={best['min_filter']}, "
          f"swing_len={best['swing_len']})")
    worst_pass = min((r for r in results if r["beats_gate"]),
                     key=lambda r: r["oos"]["sharpe"], default=None)
    if worst_pass:
        print(f"Worst passing OOS Sharpe: {worst_pass['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H344",
        "description": "OB filter sensitivity analysis on H343",
        "gate": GATE,
        "reference_params": {"ob_window": 30, "min_filter": 3, "swing_len": 5,
                              "h343_oos_sharpe": 3.182},
        "n_variants": total,
        "n_pass": n_pass,
        "variants": results,
    }
    outpath = RESULT_DIR / "h344_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
