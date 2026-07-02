"""
H355 — OB Filter on H045 Bond ETF Universe
===========================================
H343/H344/H345/H346 confirmed that the Order Block filter dramatically improves
OOS Sharpe on both stock momentum (H198 universe, OOS 3.182) and sector ETF
rotation (H026 universe, OOS 3.238). The mechanism: bullish OBs persist when
institutional accumulation is ongoing; in bond markets, OBs should form before
duration-extending rallies or credit spread compression phases.

Hypothesis:
  Applying the OB confirmation filter to H045's bond ETF momentum rotation
  improves OOS Sharpe beyond the H045 baseline (1.351).

Universe: H045 bond ETF universe (7 assets)
  SHY  — 1-3yr Treasuries
  IEI  — 3-7yr Treasuries
  IEF  — 7-10yr Treasuries
  TLT  — 20+yr Treasuries (long duration)
  TIP  — TIPS (inflation-linked)
  HYG  — High-yield corporate
  LQD  — Investment-grade corporate

Signal: 12m momentum (H045 canonical, top-2 EW)
OB params: window=20, swing_len=3 (H344/H346 best for equity ETFs)
           + window=30, swing_len=5 (reference params) for comparison
IS:  2007-01-01 → 2016-12-31  (H045 canonical IS)
OOS: 2017-01-01 → 2026-06-30  (H045 canonical OOS)
Gate: OOS Sharpe > 1.451  (H045 baseline 1.351 + 0.10 improvement)

Variants per param set:
  A  Strict top-2: both picks must have OB; else SHY (short-term safe haven)
  B  Lenient top-2: try top-2 with OB; take OB pick + unfiltered to fill 2 slots
  C  Lenient top-3: if any of top-3 has OB, enter standard top-2; else SHY
  D  Baseline H045 (12m top-2 EW, no OB filter)
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

UNIVERSE   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD"]
CASH_PROXY = "SHY"   # short-term Treasuries as "safe haven" when no OB

DATA_START = "2005-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2007-01-01")
IS_END     = pd.Timestamp("2016-12-31")
OOS_START  = pd.Timestamp("2017-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE       = 1.451

PARAM_SETS = {
    "best": {"ob_window": 20, "swing_len": 3},
    "ref":  {"ob_window": 30, "swing_len": 5},
}


def load_close(ticker):
    for prefix in ["h345","h346","h355"]:
        for pat in [f"{prefix}_{ticker}_close.parquet",
                    f"{prefix}_{ticker}_daily.parquet"]:
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
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h355_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    for prefix in ["h345","h346","h343","h344"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                if "volume" not in df.columns:
                    df["volume"] = 0
                return df[["open","high","low","close","volume"]]
    print(f"  Downloading {ticker} OHLCV…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.to_parquet(CACHE_DIR / f"h355_{ticker}_daily.parquet")
    return df


def has_bullish_ob(daily_df, as_of, ob_window, swing_len):
    sub = daily_df[daily_df.index <= as_of].tail(ob_window + swing_len * 2)
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


def build_signal(daily_closes):
    daily_df    = pd.DataFrame(daily_closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, mom_12


def run_backtest(monthly_px, monthly_ret, mom_12, daily_data, variant, ob_window, swing_len):
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for i, me in enumerate(months):
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].dropna()
        valid   = [t for t in UNIVERSE if t in mom_row.index]
        if len(valid) < 1:
            port_rets.append((me, 0.0))
            continue

        ranked = list(mom_row[valid].nlargest(len(valid)).index)
        ret_row = monthly_ret.iloc[loc]

        def asset_ret(t):
            return float(ret_row.get(t, 0.0)) if not pd.isna(ret_row.get(t, np.nan)) else 0.0

        if variant == "D":
            # H045 baseline: top-2 EW, no filter
            picks = ranked[:2]
            r = np.mean([asset_ret(t) for t in picks])
        elif variant == "A":
            # Strict: both of top-2 must have OB; else SHY
            top2 = ranked[:2]
            ob_pass = [t for t in top2 if t in daily_data and
                       has_bullish_ob(daily_data[t], me, ob_window, swing_len)]
            if len(ob_pass) == 2:
                r = np.mean([asset_ret(t) for t in ob_pass])
            else:
                r = asset_ret(CASH_PROXY)
        elif variant == "B":
            # Lenient: take OB-passing picks from top-2; fill 2nd slot with top unfiltered
            top2 = ranked[:2]
            ob_pass = [t for t in top2 if t in daily_data and
                       has_bullish_ob(daily_data[t], me, ob_window, swing_len)]
            if len(ob_pass) >= 1:
                # At least 1 has OB — take it, fill second from top-3 non-OB
                picks = ob_pass[:1]
                for t in ranked[:3]:
                    if t not in picks and len(picks) < 2:
                        picks.append(t)
                r = np.mean([asset_ret(t) for t in picks])
            else:
                r = asset_ret(CASH_PROXY)
        elif variant == "C":
            # Any of top-3 has OB → use standard top-2; else SHY
            top3 = ranked[:3]
            any_ob = any(
                t in daily_data and has_bullish_ob(daily_data[t], me, ob_window, swing_len)
                for t in top3
            )
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
    return int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0))

def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cagr": 0.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 12), 3),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


def main():
    print("H355 — OB Filter on H045 Bond ETF Universe")
    print("=" * 55)

    print("\nLoading close data…")
    daily_closes = {}
    for t in UNIVERSE:
        try:
            daily_closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    daily_px    = pd.DataFrame(daily_closes).sort_index()
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
        "B": "OB lenient (≥1 of top-2 has OB; fill 2nd slot)",
        "C": "OB gate (any of top-3 has OB → top-2; else SHY)",
        "D": "H045 baseline (12m top-2 EW, no filter)",
    }

    all_results = {}
    print(f"\n{'Param':<6} {'Var':<4} {'Description':<45} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MDD':>8} {'Neg':>4}")
    print("-" * 90)

    for pname, params in PARAM_SETS.items():
        for vcode, vname in VARIANTS.items():
            key = f"{pname}_{vcode}"
            rets = run_backtest(monthly_px, monthly_ret, mom_12, daily_data,
                                vcode, params["ob_window"], params["swing_len"])
            is_  = eval_period(rets, IS_START, IS_END)
            oos_ = eval_period(rets, OOS_START, OOS_END)
            # Cash months in OOS
            oos_s = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
            shy_ret = monthly_ret[(monthly_ret.index >= OOS_START) & (monthly_ret.index <= OOS_END)].get("SHY")
            all_results[key] = {"name": vname, "params": pname, "is": is_, "oos": oos_}
            beats = oos_["sharpe"] > GATE
            print(f"{pname:<6} {vcode:<4} {vname:<45} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
                  f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  "
                  f"{'✓ BEATS GATE' if beats else ''}")
        print()

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    best_key = max(
        [k for k in all_results if not k.endswith("_D")],
        key=lambda k: all_results[k]["oos"]["sharpe"]
    )
    best = all_results[best_key]
    if best["oos"]["sharpe"] > GATE:
        print(f"  CONFIRMED — best: {best_key} OOS Sharpe {best['oos']['sharpe']:.3f}")
    else:
        print(f"  NOT CONFIRMED — best: {best_key} OOS Sharpe {best['oos']['sharpe']:.3f}")

    out = RESULT_DIR / "h355_results.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
