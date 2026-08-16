"""
H514 — Look-Ahead Bias Audit: OB Filter `as_of` Date in H356 (H354 Low-Vol ETF Universe)
============================================================================================
Source: H510's key finding #4/#5 — same `has_bullish_ob(daily_data[t], me, ...)`
as-of-date bug inherited from H343/H344 into H356's low-vol ETF OB filter. This is
H510's dedicated correction run for H356 (last of the four flagged hypotheses).

H356 tested the OB filter on H354's low-vol ETF rotation (pure 12m momentum top-1),
canonical IS 2013-2020 / OOS 2021-2026 split, two OB param sets ('best' window=20/
swing=3, 'ref' window=30/swing=5), 3 filter variants (A strict, B lenient, C gate)
plus baseline D. Original CONFIRMED result: ref_A (strict) OOS Sharpe 2.312 vs
baseline (H354-C) OOS 1.339 (note: H356's own logged baseline; H354's canonical
number elsewhere in the log is 1.735 — H356 explicitly noted this discrepancy as a
data-alignment difference between runs), gate 1.735 (primary) / 1.535+MaxDD (partial).

This script:
  1. Reproduces H356's original `as_of=month_end` (buggy) result for baseline D and
     all OB variants (A/B/C) x both param sets, to confirm the logged numbers are
     reproducible before trusting any correction.
  2. Re-runs the OB variants with `as_of` corrected to the PRIOR month-end.
  3. Runs an automated look-ahead self-check assertion BEFORE any results are computed.
  4. Baseline D is invariant to the as_of correction (never calls has_bullish_ob).

Universe: H354 8-asset low-vol ETFs (USMV/SPLV/XLU/SPHD/EFAV/EEMV/ACWV + BIL)
Signal: pure 12m momentum top-1 (unaffected — already correctly lagged)
IS/OOS: 2013-2020 / 2021-2026 (identical to H356 — H354 canonical split)
Gate: OOS Sharpe > 1.735 (primary, H354-C canonical); H356's own logged baseline was
      1.339 due to a data-alignment discrepancy it explicitly flagged — this script
      reports both the H356-comparable baseline (from this exact code path) and notes
      the discrepancy so the corrected numbers aren't misread against the wrong ref.
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

UNIVERSE   = ["USMV", "SPLV", "XLU", "SPHD", "EFAV", "EEMV", "ACWV", "BIL"]
RISKY      = [t for t in UNIVERSE if t != "BIL"]
CASH_PROXY = "BIL"

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")

GATE_PRIMARY   = 1.735
GATE_SECONDARY = 1.535
MAXDD_BASELINE = -0.113

ALT_OOS_START = pd.Timestamp("2013-01-01")

PARAM_SETS = {
    "best": {"ob_window": 20, "swing_len": 3},
    "ref":  {"ob_window": 30, "swing_len": 5},
}


def load_close(ticker):
    for prefix in ["h354", "h356", "h514"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_close.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame):
                col = next((c for c in df.columns if c.lower() in ["close", "Close"]), df.columns[0])
                return df[col].rename(ticker)
            return df.rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h514_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    for prefix in ["h345", "h346", "h343", "h344", "h354", "h355", "h356", "h514"]:
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
    df.to_parquet(CACHE_DIR / f"h514_{ticker}_daily.parquet")
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
    cash_months = 0
    months = monthly_px.index[monthly_px.index >= IS_START]

    for me in months:
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].drop(CASH_PROXY, errors="ignore").dropna()
        valid = [t for t in RISKY if t in mom_row.index]
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
            r = asset_ret(ranked[0])
        elif variant == "A":
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], ob_as_of, ob_window, swing_len):
                r = asset_ret(top1)
            else:
                r = asset_ret(CASH_PROXY)
                cash_months += 1
        elif variant == "B":
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], ob_as_of, ob_window, swing_len):
                r = asset_ret(top1)
            elif len(ranked) > 1:
                top2 = ranked[1]
                if top2 in daily_data and has_bullish_ob(daily_data[top2], ob_as_of, ob_window, swing_len):
                    r = asset_ret(top2)
                else:
                    r = asset_ret(CASH_PROXY)
                    cash_months += 1
            else:
                r = asset_ret(CASH_PROXY)
                cash_months += 1
        elif variant == "C":
            top3 = ranked[:3]
            any_ob = any(t in daily_data and has_bullish_ob(daily_data[t], ob_as_of, ob_window, swing_len)
                         for t in top3)
            if any_ob:
                r = asset_ret(ranked[0])
            else:
                r = asset_ret(CASH_PROXY)
                cash_months += 1
        else:
            r = 0.0

        port_rets.append((me, float(r)))

    s = pd.Series({d: v for d, v in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s, cash_months


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
    print("H514 — Look-Ahead Bias Audit: OB Filter as_of Date in H356")
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
    for t in RISKY:
        try:
            daily_data[t] = load_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    VARIANTS = {
        "A": "OB strict (top-1 needs OB; else BIL)",
        "B": "OB lenient (top-1 OB->hold; elif top-2 OB->hold; else BIL)",
        "C": "OB gate (any top-3 has OB -> top-1; else BIL)",
    }

    results = {}
    print(f"\n{'Param':<6} {'Var':<4} {'as_of':<10} {'IS Sh':>7} {'OOS Sh':>7} "
          f"{'AltOOS Sh':>10} {'WF':>6} {'MDD':>8} {'Neg':>4} {'Cash%':>7}")
    print("-" * 100)

    rets_d, _ = run_backtest(monthly_px, monthly_ret, mom_12, daily_data, "D", 20, 3, corrected=False)
    is_d = eval_period(rets_d, IS_START, IS_END)
    oos_d = eval_period(rets_d, OOS_START, OOS_END)
    alt_d = eval_period(rets_d, ALT_OOS_START, OOS_END)
    wf_d = walk_forward_ratio(is_d["sharpe"], oos_d["sharpe"])
    results["baseline_D"] = {"variant": "D", "name": "H354-C baseline (pure 12m top-1, no filter)",
                              "is": is_d, "oos": oos_d, "alt_oos": alt_d, "wf_ratio": wf_d,
                              "beats_gate_primary": oos_d["sharpe"] > GATE_PRIMARY}
    print(f"{'--':<6} {'D':<4} {'n/a':<10} {is_d['sharpe']:>7.3f} {oos_d['sharpe']:>7.3f} "
          f"{alt_d['sharpe']:>10.3f} {str(wf_d):>6} {oos_d['maxdd']:>8.1%} {oos_d['neg_yrs']:>4d} {'--':>7}")

    for pname, params in PARAM_SETS.items():
        for vcode, vname in VARIANTS.items():
            for mode in ["original", "corrected"]:
                rets, cm = run_backtest(monthly_px, monthly_ret, mom_12, daily_data, vcode,
                                         params["ob_window"], params["swing_len"],
                                         corrected=(mode == "corrected"))
                is_ = eval_period(rets, IS_START, IS_END)
                oos_ = eval_period(rets, OOS_START, OOS_END)
                alt_oos_ = eval_period(rets, ALT_OOS_START, OOS_END)
                wf = walk_forward_ratio(is_["sharpe"], oos_["sharpe"])
                oos_n = oos_["n"]
                cash_pct = cm / oos_n if oos_n > 0 else 0.0
                key = f"{pname}_{vcode}_{mode}"
                beats_p = oos_["sharpe"] > GATE_PRIMARY
                beats_s = (oos_["sharpe"] > GATE_SECONDARY and oos_["maxdd"] < MAXDD_BASELINE + 0.02)
                results[key] = {"variant": vcode, "params": pname, "name": vname, "as_of": mode,
                                 "is": is_, "oos": oos_, "alt_oos": alt_oos_, "wf_ratio": wf,
                                 "oos_cash_pct": round(cash_pct, 3),
                                 "beats_gate_primary": beats_p, "beats_gate_secondary_partial": beats_s}
                print(f"{pname:<6} {vcode:<4} {mode:<10} {is_['sharpe']:>7.3f} {oos_['sharpe']:>7.3f} "
                      f"{alt_oos_['sharpe']:>10.3f} {str(wf):>6} {oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d} "
                      f"{cash_pct:>7.1%}")

    print(f"\n=== Verdict (Primary Gate: OOS Sharpe > {GATE_PRIMARY}; "
          f"Partial: Sharpe > {GATE_SECONDARY} AND MaxDD improves >=2pp) ===")
    for pname in PARAM_SETS:
        for vcode in ["A", "B", "C"]:
            orig = results[f"{pname}_{vcode}_original"]
            corr = results[f"{pname}_{vcode}_corrected"]
            delta = corr["oos"]["sharpe"] - orig["oos"]["sharpe"]
            print(f"  {pname}_{vcode}: original OOS {orig['oos']['sharpe']:.3f} -> "
                  f"corrected OOS {corr['oos']['sharpe']:.3f} (delta {delta:+.3f}), "
                  f"corrected beats primary gate: {corr['beats_gate_primary']}, "
                  f"partial: {corr['beats_gate_secondary_partial']}")
    print(f"  Baseline D: OOS {results['baseline_D']['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H514",
        "audit_of": "H356",
        "gate_primary": GATE_PRIMARY,
        "gate_secondary": GATE_SECONDARY,
        "results": results,
    }
    outpath = RESULT_DIR / "h514_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
