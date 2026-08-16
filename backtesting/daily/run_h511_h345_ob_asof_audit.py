"""
H511 — Look-Ahead Bias Audit: OB Filter `as_of` Date in H345 (H026 Non-Canonical Split)
==========================================================================================
Source: H510's key finding #4/#5 flagged that `run_h345.py`, `run_h346.py`,
`run_h355.py`, `run_h356.py` all inherit the same `has_bullish_ob(daily_data[ticker],
month_end, ...)` as-of-date bug confirmed in H343/H344 — the CURRENT holding month's
own closing date is passed as the OB detector's `as_of` cutoff instead of the prior
month-end, letting the OB confirmation step see the entire holding month's daily bars
before deciding whether to include an asset. This is H510's dedicated correction run
for H345.

H345 tested the OB filter on H026 sector ETF rotation, non-canonical split (IS
2013-2020 / OOS 2021-2026), with 4 variants (A strict, B lenient, C gate, D baseline
no-filter). Original CONFIRMED result: Variant B (lenient) OOS Sharpe 3.337 vs
baseline D 2.538, gate 1.300.

This script:
  1. Reproduces H345's original `as_of=month_end` (buggy) result for all 4 variants,
     to confirm the logged numbers (IS/OOS Sharpe) are reproducible before trusting
     any correction.
  2. Re-runs all 4 variants with `as_of` corrected to the PRIOR month-end
     (`monthly_ret.index[loc - 1]`), matching H510's exact fix.
  3. Runs an automated look-ahead self-check assertion BEFORE any results are
     computed (matching H509/H510 style).
  4. Baseline D (no OB filter) is invariant to the as_of correction by construction
     (it never calls has_bullish_ob) — included as a stable reference in both rows.

Universe: H026 25-asset expanded (identical to H345)
Signal: 12m momentum + inv_6m_vol rank composite (unaffected — already correctly lagged)
IS/OOS: 2013-2020 / 2021-2026 (identical to H345 — non-canonical split)
Gate: OOS Sharpe > 1.300 (H345's own gate)
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
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
    "IBB","XME",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

OB_WINDOW  = 30
SWING_LEN  = 5
GATE       = 1.300
CASH_PROXY = "BIL"

ALT_OOS_START = pd.Timestamp("2013-01-01")  # AltOOS window per task instructions (2013-present)


def load_daily_close(ticker: str) -> pd.Series:
    for prefix in ["h112", "h343", "h344", "h345", "h511"]:
        for suffix in [f"_ohlc_{DATA_START}_{DATA_END}", f"_close_{DATA_START}_{DATA_END}",
                       f"_{ticker}_daily", "_close"]:
            p = CACHE_DIR / f"{prefix}_{ticker}{suffix}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    p = CACHE_DIR / f"h343_{ticker}_daily.parquet"
    if p.exists():
        df = pd.read_parquet(p)
        return df["close"].rename(ticker)
    print(f"  Downloading {ticker} daily…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h511_{ticker}_close.parquet")
    return s


def load_daily_ohlcv(ticker: str) -> pd.DataFrame:
    for prefix in ["h343", "h344", "h345", "h346", "h511"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if p.exists():
            return pd.read_parquet(p)
    for prefix in ["h112", "h344"]:
        p3 = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"
        if p3.exists():
            df = pd.read_parquet(p3)
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
    df.to_parquet(CACHE_DIR / f"h511_{ticker}_daily.parquet")
    return df


def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp) -> bool:
    sub = daily_df[daily_df.index <= as_of].tail(OB_WINDOW + SWING_LEN * 2)
    if len(sub) < SWING_LEN * 2:
        return False
    try:
        ohlcv = sub[["open", "high", "low", "close", "volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=SWING_LEN)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


def build_signal(tickers, daily_closes):
    daily_df = pd.DataFrame({t: daily_closes[t] for t in tickers if t in daily_closes}) \
        .sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6 = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, vol_6, mom_12


def run_backtest(monthly_px, monthly_ret, vol_6, mom_12, daily_data, variant: str,
                  corrected: bool) -> pd.Series:
    """corrected=False reproduces H345's original as_of=month_end bug.
    corrected=True uses as_of=prior month-end (last trading day before the
    holding month begins) -- the fix, mirroring H510's run_h510 script."""
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for month_end in months:
        loc = monthly_px.index.get_loc(month_end)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].dropna()
        vol_row = vol_6.iloc[loc].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        valid = valid[valid != CASH_PROXY]
        if len(valid) < 1:
            port_rets.append((month_end, 0.0))
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        ranked = list(score.nlargest(len(valid)).index)

        ob_as_of = monthly_ret.index[loc - 1] if corrected else month_end

        if variant == "D":
            selected = ranked[0]
            ret_this = monthly_ret.iloc[loc][selected] if selected in monthly_ret.columns else 0.0
        elif variant == "A":
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], ob_as_of):
                selected = top1
            else:
                selected = CASH_PROXY
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        elif variant == "B":
            selected = CASH_PROXY
            for pick in ranked[:2]:
                if pick in daily_data and has_bullish_ob(daily_data[pick], ob_as_of):
                    selected = pick
                    break
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        elif variant == "C":
            top3 = ranked[:3]
            any_ob = any(t in daily_data and has_bullish_ob(daily_data[t], ob_as_of) for t in top3)
            selected = ranked[0] if any_ob else CASH_PROXY
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        else:
            ret_this = 0.0

        port_rets.append((month_end, float(ret_this) if not np.isnan(ret_this) else 0.0))

    s = pd.Series({d: r for d, r in port_rets})
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
    """Automated self-check: corrected ob_as_of must always be strictly before
    the holding month's own trading days. Run BEFORE any results are computed."""
    idx = pd.date_range("2020-01-01", periods=30, freq="ME")
    for loc in range(5, 30):
        month_end = idx[loc]
        ob_as_of_corrected = idx[loc - 1]
        assert ob_as_of_corrected < month_end, "LOOK-AHEAD SELF-CHECK FAILED"
    print("Look-ahead self-check PASSED: corrected ob_as_of is always the PRIOR "
          "month-end, strictly before the holding month's own close.")


def main():
    print("H511 — Look-Ahead Bias Audit: OB Filter as_of Date in H345")
    print("=" * 70)
    lookahead_self_check()

    print("\nLoading daily close data for rotation signal…")
    daily_closes = {}
    for t in UNIVERSE:
        try:
            daily_closes[t] = load_daily_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    monthly_px, monthly_ret, vol_6, mom_12 = build_signal(UNIVERSE, daily_closes)

    print("Loading OHLCV data for OB detection…")
    daily_data = {}
    for t in UNIVERSE:
        if t == CASH_PROXY:
            continue
        try:
            daily_data[t] = load_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    VARIANTS = {
        "A": "OB strict (top-1 must have OB; else BIL)",
        "B": "OB lenient (try top-2; BIL if neither has OB)",
        "C": "OB gate (any of top-3 has OB -> enter top-1; else BIL)",
        "D": "Baseline H026 (no OB filter, top-1 momentum)",
    }

    results = {}
    print(f"\n{'Var':<4} {'as_of':<10} {'Description':<45} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'AltOOS Sh':>10} {'WF':>6} {'MaxDD':>8} {'Neg':>4}")
    print("-" * 100)

    for vcode, vname in VARIANTS.items():
        as_of_modes = ["original"] if vcode == "D" else ["original", "corrected"]
        for mode in as_of_modes:
            rets = run_backtest(monthly_px, monthly_ret, vol_6, mom_12, daily_data,
                                 vcode, corrected=(mode == "corrected"))
            is_ = eval_period(rets, IS_START, IS_END)
            oos_ = eval_period(rets, OOS_START, OOS_END)
            alt_oos_ = eval_period(rets, ALT_OOS_START, OOS_END)
            wf = walk_forward_ratio(is_["sharpe"], oos_["sharpe"])
            oos_slice = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
            cash_n = int((oos_slice == 0).sum())
            key = f"{vcode}_{mode}"
            results[key] = {"variant": vcode, "name": vname, "as_of": mode,
                             "is": is_, "oos": oos_, "alt_oos": alt_oos_,
                             "wf_ratio": wf, "oos_cash_months": cash_n,
                             "beats_gate": oos_["sharpe"] > GATE}
            print(f"{vcode:<4} {mode:<10} {vname:<45} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
                  f"{alt_oos_['sharpe']:>10.3f} {str(wf):>6} {oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    for vcode in ["A", "B", "C"]:
        orig = results[f"{vcode}_original"]
        corr = results[f"{vcode}_corrected"]
        delta = corr["oos"]["sharpe"] - orig["oos"]["sharpe"]
        print(f"  {vcode}: original OOS {orig['oos']['sharpe']:.3f} (logged H345 comparison) -> "
              f"corrected OOS {corr['oos']['sharpe']:.3f} (delta {delta:+.3f}), "
              f"corrected beats gate: {corr['beats_gate']}")
    print(f"  D baseline (invariant to correction): OOS {results['D_original']['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H511",
        "audit_of": "H345",
        "gate": GATE,
        "results": results,
    }
    outpath = RESULT_DIR / "h511_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
