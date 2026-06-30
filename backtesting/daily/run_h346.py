"""
H346 — OB Filter on H026 Canonical IS/OOS Split
=================================================
H345 confirmed that OB filter on H026 ETF rotation improves OOS Sharpe from
2.538 → 3.337 (Variant B), but used a non-canonical IS 2013-2020 / OOS 2021-2026
split. H345's baseline (D) showed OOS 2.538 — much higher than production H026
(~1.200 on canonical split), so H345 results are NOT directly comparable to
the production benchmark.

H346 retests the SAME OB filter variants on the CANONICAL H026 split:
  IS: 2008–2017 (canonical H026 IS)
  OOS: 2018–2026 (canonical H026 OOS, benchmark 1.200)

Also tests H344's best OB params (window=20, min_filter=3, swing_len=3)
alongside the H345 reference params (window=30, min_filter=2, swing_len=5).

Gate: OOS Sharpe > 1.300 (H026 canonical OOS 1.200 + 0.1 improvement)
If confirmed, Variant B would directly replace H026 monthly selection logic.
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

DATA_START  = "2006-01-01"  # 2 extra years for 12m momentum warmup
DATA_END    = "2026-06-27"
IS_START    = pd.Timestamp("2008-01-01")
IS_END      = pd.Timestamp("2017-12-31")
OOS_START   = pd.Timestamp("2018-01-01")
OOS_END     = pd.Timestamp("2026-06-27")
CASH_PROXY  = "BIL"

# Two OB parameter sets to test
PARAM_SETS = {
    "ref":  {"ob_window": 30, "swing_len": 5},   # H345 reference (H343 defaults)
    "best": {"ob_window": 20, "swing_len": 3},    # H344 best params
}


# ── Data loading ─────────────────────────────────────────────────────────────

def load_close(ticker: str) -> pd.Series:
    for prefix in ["h112","h343","h344","h345","h346"]:
        for pat in [f"{prefix}_{ticker}_close.parquet",
                    f"{prefix}_{ticker}_daily.parquet",
                    f"{prefix}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                col = next((c for c in ["close","Close"] if c.lower() == "close"), None)
                if col and col.lower() in df.columns:
                    return df["close"].rename(ticker)
                if hasattr(df, 'squeeze') and df.shape[1] == 1:
                    return df.iloc[:, 0].rename(ticker)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h346_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker: str) -> pd.DataFrame:
    for prefix in ["h343","h344","h345","h346"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                if "volume" not in df.columns:
                    df["volume"] = 0
                return df[["open","high","low","close","volume"]]
        p2 = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"
        if p2.exists():
            df = pd.read_parquet(p2)
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
    df.to_parquet(CACHE_DIR / f"h346_{ticker}_daily.parquet")
    return df


# ── OB detection ─────────────────────────────────────────────────────────────

def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp,
                   ob_window: int, swing_len: int) -> bool:
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


# ── Signal ────────────────────────────────────────────────────────────────────

def build_signal(daily_closes):
    df = pd.DataFrame(daily_closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = df.resample("ME").last()
    monthly_ret = df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6       = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, vol_6, mom_12


# ── Backtest ──────────────────────────────────────────────────────────────────

def run_backtest(monthly_px, monthly_ret, vol_6, mom_12,
                 daily_data, variant: str, ob_window: int, swing_len: int) -> pd.Series:
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for i, month_end in enumerate(months):
        loc = monthly_px.index.get_loc(month_end)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].dropna()
        vol_row = vol_6.iloc[loc].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        valid   = valid[valid != CASH_PROXY]
        if len(valid) < 1:
            port_rets.append((month_end, 0.0))
            continue

        score  = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        ranked = list(score.nlargest(len(valid)).index)

        def ob_check(t):
            return (t in daily_data and
                    has_bullish_ob(daily_data[t], month_end, ob_window, swing_len))

        if variant == "D":
            selected = ranked[0]
        elif variant == "A":
            selected = ranked[0] if ob_check(ranked[0]) else CASH_PROXY
        elif variant == "B":
            selected = CASH_PROXY
            for pick in ranked[:2]:
                if ob_check(pick):
                    selected = pick
                    break
        elif variant == "C":
            selected = ranked[0] if any(ob_check(t) for t in ranked[:3]) else CASH_PROXY

        ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        port_rets.append((month_end, float(ret_this) if not np.isnan(ret_this) else 0.0))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Metrics ──────────────────────────────────────────────────────────────────

def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r):
    ann = r.resample("YE").apply(lambda x: (1+x).prod()-1)
    return int((ann < 0).sum())

def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0, "cagr": 0, "maxdd": 0, "neg_yrs": 0}
    return {
        "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H346 — OB Filter on H026 Canonical IS/OOS Split")
    print("=" * 60)
    print(f"  IS: {IS_START.date()} – {IS_END.date()}")
    print(f"  OOS: {OOS_START.date()} – {OOS_END.date()}")
    print(f"  H026 canonical OOS benchmark: ~1.200")
    print(f"  Gate: OOS Sharpe > 1.300")

    print("\nLoading close prices…")
    daily_closes = {}
    for t in UNIVERSE:
        try:
            daily_closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    monthly_px, monthly_ret, vol_6, mom_12 = build_signal(daily_closes)

    print("Loading OHLCV for OB detection…")
    daily_data = {}
    for t in UNIVERSE:
        if t == CASH_PROXY:
            continue
        try:
            daily_data[t] = load_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    GATE = 1.300
    VARIANTS = {
        "A": "OB strict (top-1 must have OB; else BIL)",
        "B": "OB lenient (try top-2; BIL if neither has OB)",
        "C": "OB gate (any top-3 has OB → enter top-1; else BIL)",
        "D": "Baseline H026 (no OB filter)",
    }

    all_results = {}

    for pset_name, pset in PARAM_SETS.items():
        ob_w = pset["ob_window"]
        sw_l = pset["swing_len"]
        print(f"\n── Param set '{pset_name}': window={ob_w}, swing_len={sw_l} ──")
        print(f"{'Var':<4} {'Description':<46} {'IS Sh':>7} {'OOS Sh':>7} "
              f"{'MaxDD':>7} {'Neg':>4} {'Cash%':>6}")
        print("-" * 80)

        pset_results = {}
        for vcode, vname in VARIANTS.items():
            print(f"  Running {vcode}…", end=" ", flush=True)
            rets = run_backtest(monthly_px, monthly_ret, vol_6, mom_12,
                                daily_data, vcode, ob_w, sw_l)
            is_  = eval_period(rets, IS_START, IS_END)
            oos_ = eval_period(rets, OOS_START, OOS_END)
            oos_slice   = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
            cash_months = int((oos_slice == 0).sum())
            cash_pct    = cash_months / max(len(oos_slice), 1)
            beats = oos_["sharpe"] > GATE
            pset_results[vcode] = {
                "name": vname, "is": is_, "oos": oos_,
                "oos_cash_months": cash_months,
                "oos_cash_pct": round(cash_pct, 3),
            }
            print(f"\r{vcode:<4} {vname:<46} {is_['sharpe']:>7.3f} "
                  f"{oos_['sharpe']:>7.3f} {oos_['maxdd']:>7.1%} "
                  f"{oos_['neg_yrs']:>4d} {cash_pct:>6.1%}  "
                  f"{'✓' if beats else ''}")

        all_results[pset_name] = {"params": pset, "variants": pset_results}

    print(f"\n{'='*60}")
    print(f"SUMMARY — Gate: OOS Sharpe > {GATE}")
    print(f"{'='*60}")
    for pset_name, pdata in all_results.items():
        print(f"\n  Param set '{pset_name}' (window={pdata['params']['ob_window']}, "
              f"swing_len={pdata['params']['swing_len']}):")
        for vcode in ["D","A","B","C"]:
            r = pdata["variants"][vcode]
            beats = r["oos"]["sharpe"] > GATE
            print(f"    {vcode}: OOS {r['oos']['sharpe']:.3f}  "
                  f"IS {r['is']['sharpe']:.3f}  "
                  f"MaxDD {r['oos']['maxdd']:.1%}  "
                  f"{'✓ BEATS GATE' if beats else '< gate'}")

    out = {
        "hypothesis": "H346",
        "description": "OB filter on H026 canonical IS 2008-2017 / OOS 2018-2026 split",
        "gate": GATE,
        "h026_canonical_oos_benchmark": 1.200,
        "param_sets": all_results,
    }
    outpath = RESULT_DIR / "h346_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
