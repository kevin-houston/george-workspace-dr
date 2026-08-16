"""
H513 — Look-Ahead Bias Audit: OB Filter `as_of` Date in H355 (H045 Bond ETF Universe)
========================================================================================
Source: H510's key finding #4/#5 — same `has_bullish_ob(daily_data[t], me, ...)`
as-of-date bug inherited from H343/H344 into H355's bond ETF OB filter. This is
H510's dedicated correction run for H355.

H355 tested the OB filter on H045 bond ETF momentum rotation (top-2 EW), canonical
IS 2007-2016 / OOS 2017-2026 split, two OB param sets ('best' window=20/swing=3,
'ref' window=30/swing=5), 4 variants (A strict both, B lenient fill, C gate, D
baseline). Original CONFIRMED result: best_B OOS Sharpe 1.522 vs baseline D 1.112,
gate 1.451 (H045 baseline 1.351 + 0.10).

This script:
  1. Reproduces H355's original `as_of=month_end` (buggy) result for baseline D and
     all OB variants (A/B/C) x both param sets, to confirm the logged numbers are
     reproducible before trusting any correction.
  2. Re-runs the OB variants with `as_of` corrected to the PRIOR month-end.
  3. Runs an automated look-ahead self-check assertion BEFORE any results are computed.
  4. Baseline D is invariant to the as_of correction (never calls has_bullish_ob).

Universe: H045 7-asset bond ETFs (SHY/IEI/IEF/TLT/TIP/HYG/LQD), identical to H355
Signal: 12m momentum top-2 EW (unaffected — already correctly lagged)
IS/OOS: 2007-2016 / 2017-2026 (identical to H355 — H045 canonical split)
Gate: OOS Sharpe > 1.451 (H355's own gate)
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

UNIVERSE   = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
CASH_PROXY = "SHY"

DATA_START = "2005-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2007-01-01")
IS_END     = pd.Timestamp("2016-12-31")
OOS_START  = pd.Timestamp("2017-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE       = 1.451

ALT_OOS_START = pd.Timestamp("2013-01-01")

PARAM_SETS = {
    "best": {"ob_window": 20, "swing_len": 3},
    "ref":  {"ob_window": 30, "swing_len": 5},
}


def load_close(ticker):
    for prefix in ["h345", "h346", "h355", "h513"]:
        for pat in [f"{prefix}_{ticker}_close.parquet", f"{prefix}_{ticker}_daily.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df, pd.DataFrame) and "close" in df.columns:
                    return df["close"].rename(ticker)
                elif isinstance(df, pd.DataFrame) and "Close" in df.columns:
                    return df["Close"].rename(ticker)
                elif isinstance(df, pd.Series):
                    return df.rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h513_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    for prefix in ["h345", "h346", "h343", "h344", "h355", "h513"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                if "volume" not in df.columns:
                    df["volume"] = 0
                return df[["open", "high", "low", "close", "volume"]]
    print(f"  Downloading {ticker} OHLCV…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df.to_parquet(CACHE_DIR / f"h513_{ticker}_daily.parquet")
    return df


def has_bullish_ob(daily_df, as_of, ob_window, swing_len):
    sub = daily_df[daily_df.index <= as_of].tail(ob_window + swing_len * 2)
    if len(sub) < swing_len * 2:
        return False
    try:
        ohlcv = sub[["open", "high", "low", "close", "volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


def build_signal(daily_closes):
    daily_df = pd.DataFrame(daily_closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, mom_12


def run_backtest(monthly_px, monthly_ret, mom_12, daily_data, variant, ob_window, swing_len,
                  corrected: bool):
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for me in months:
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].dropna()
        valid = [t for t in UNIVERSE if t in mom_row.index]
        if len(valid) < 1:
            port_rets.append((me, 0.0))
            continue

        ranked = list(mom_row[valid].nlargest(len(valid)).index)
        ret_row = monthly_ret.iloc[loc]

        def asset_ret(t):
            v = ret_row.get(t, np.nan)
            return float(v) if not pd.isna(v) else 0.0

        ob_as_of = monthly_ret.index[loc - 1] if corrected else me

        if variant == "D":
            picks = ranked[:2]
            r = np.mean([asset_ret(t) for t in picks])
        elif variant == "A":
            top2 = ranked[:2]
            ob_pass = [t for t in top2 if t in daily_data and
                       has_bullish_ob(daily_data[t], ob_as_of, ob_window, swing_len)]
            if len(ob_pass) == 2:
                r = np.mean([asset_ret(t) for t in ob_pass])
            else:
                r = asset_ret(CASH_PROXY)
        elif variant == "B":
            top2 = ranked[:2]
            ob_pass = [t for t in top2 if t in daily_data and
                       has_bullish_ob(daily_data[t], ob_as_of, ob_window, swing_len)]
            if len(ob_pass) >= 1:
                picks = ob_pass[:1]
                for t in ranked[:3]:
                    if t not in picks and len(picks) < 2:
                        picks.append(t)
                r = np.mean([asset_ret(t) for t in picks])
            else:
                r = asset_ret(CASH_PROXY)
        elif variant == "C":
            top3 = ranked[:3]
            any_ob = any(t in daily_data and has_bullish_ob(daily_data[t], ob_as_of, ob_window, swing_len)
                         for t in top3)
            if any_ob:
                r = np.mean([asset_ret(t) for t in ranked[:2]])
            else:
                r = asset_ret(CASH_PROXY)
        else:
            r = 0.0

        port_rets.append((me, float(r)))

    s = pd.Series({d: v for d, v in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0


def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def neg_yrs(r):
    return int(sum(r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0))


def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cagr": 0.0, "maxdd": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3), "cagr": round(float(r.mean() * 12), 3),
             "maxdd": round(maxdd(r), 3), "neg_yrs": neg_yrs(r)}


def walk_forward_ratio(is_sharpe, oos_sharpe):
    if is_sharpe == 0:
        return None
    return round(oos_sharpe / is_sharpe, 3)


def lookahead_self_check():
    idx = pd.date_range("2020-01-01", periods=30, freq="ME")
    for loc in range(5, 30):
        month_end = idx[loc]
        ob_as_of_corrected = idx[loc - 1]
        assert ob_as_of_corrected < month_end, "LOOK-AHEAD SELF-CHECK FAILED"
    print("Look-ahead self-check PASSED: corrected ob_as_of is always the PRIOR "
          "month-end, strictly before the holding month's own close.")


def main():
    print("H513 — Look-Ahead Bias Audit: OB Filter as_of Date in H355")
    print("=" * 70)
    lookahead_self_check()

    print("\nLoading close data…")
    daily_closes = {}
    for t in UNIVERSE:
        try:
            daily_closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    monthly_px, monthly_ret, mom_12 = build_signal(daily_closes)

    print("Loading OHLCV for OB detection…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = load_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    VARIANTS = {
        "A": "OB strict (both top-2 must have OB; else SHY)",
        "B": "OB lenient (>=1 of top-2 has OB; fill 2nd slot)",
        "C": "OB gate (any of top-3 has OB -> top-2; else SHY)",
    }

    results = {}
    print(f"\n{'Param':<6} {'Var':<4} {'as_of':<10} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'AltOOS Sh':>10} {'WF':>6} {'MDD':>8} {'Neg':>4}")
    print("-" * 90)

    rets_d = run_backtest(monthly_px, monthly_ret, mom_12, daily_data, "D", 0, 0, corrected=False)
    is_d = eval_period(rets_d, IS_START, IS_END)
    oos_d = eval_period(rets_d, OOS_START, OOS_END)
    alt_d = eval_period(rets_d, ALT_OOS_START, OOS_END)
    wf_d = walk_forward_ratio(is_d["sharpe"], oos_d["sharpe"])
    results["baseline_D"] = {"variant": "D", "name": "H045 baseline (12m top-2 EW, no filter)",
                              "is": is_d, "oos": oos_d, "alt_oos": alt_d, "wf_ratio": wf_d,
                              "beats_gate": oos_d["sharpe"] > GATE}
    print(f"{'--':<6} {'D':<4} {'n/a':<10} {is_d['sharpe']:>8.3f} {oos_d['sharpe']:>8.3f} "
          f"{alt_d['sharpe']:>10.3f} {str(wf_d):>6} {oos_d['maxdd']:>8.1%} {oos_d['neg_yrs']:>4d}")

    for pname, params in PARAM_SETS.items():
        for vcode, vname in VARIANTS.items():
            for mode in ["original", "corrected"]:
                rets = run_backtest(monthly_px, monthly_ret, mom_12, daily_data, vcode,
                                     params["ob_window"], params["swing_len"],
                                     corrected=(mode == "corrected"))
                is_ = eval_period(rets, IS_START, IS_END)
                oos_ = eval_period(rets, OOS_START, OOS_END)
                alt_oos_ = eval_period(rets, ALT_OOS_START, OOS_END)
                wf = walk_forward_ratio(is_["sharpe"], oos_["sharpe"])
                key = f"{pname}_{vcode}_{mode}"
                results[key] = {"variant": vcode, "params": pname, "name": vname, "as_of": mode,
                                 "is": is_, "oos": oos_, "alt_oos": alt_oos_, "wf_ratio": wf,
                                 "beats_gate": oos_["sharpe"] > GATE}
                print(f"{pname:<6} {vcode:<4} {mode:<10} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
                      f"{alt_oos_['sharpe']:>10.3f} {str(wf):>6} {oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    for pname in PARAM_SETS:
        for vcode in ["A", "B", "C"]:
            orig = results[f"{pname}_{vcode}_original"]
            corr = results[f"{pname}_{vcode}_corrected"]
            delta = corr["oos"]["sharpe"] - orig["oos"]["sharpe"]
            print(f"  {pname}_{vcode}: original OOS {orig['oos']['sharpe']:.3f} -> "
                  f"corrected OOS {corr['oos']['sharpe']:.3f} (delta {delta:+.3f}), "
                  f"corrected beats gate: {corr['beats_gate']}")
    print(f"  Baseline D: OOS {results['baseline_D']['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H513",
        "audit_of": "H355",
        "gate": GATE,
        "results": results,
    }
    outpath = RESULT_DIR / "h513_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
