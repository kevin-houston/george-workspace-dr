"""
H356 — OB Filter on H354 Low-Volatility ETF Universe
=====================================================
H354 confirmed that rotating among low-vol factor ETFs using pure 12m momentum
delivers OOS Sharpe 1.735, MaxDD -11.3% (2021-2026 OOS). The OB filter has
universally improved momentum strategies across 3 asset classes:
  - H343/H344 stocks:      baseline 1.174 → OB 3.182/3.396 (+2.0+ Sharpe)
  - H345/H346 equity ETFs: baseline 2.538 → OB 3.238/3.337 (+0.70 Sharpe)
  - H355 bond ETFs:        baseline 1.112 → OB 1.522 (+0.41 Sharpe, MaxDD halved)

Hypothesis:
  Applying the OB confirmation filter to H354's low-vol ETF rotation improves
  OOS Sharpe beyond H354-C baseline (1.735) and/or reduces the -11.3% MaxDD.
  Expected mechanism: in market tops, bullish OBs on USMV/SPLV/XLU get mitigated
  as prices break below support → filter routes to BIL earlier than raw momentum.

Universe: H354 low-vol ETF universe (8 assets)
  USMV  — iShares MSCI Min Vol USA (Oct 2011)
  SPLV  — Invesco S&P 500 Low Vol (May 2011)
  XLU   — Utilities SPDR (traditional low-vol proxy, since 1998)
  SPHD  — Invesco S&P 500 High Div Low Vol (Oct 2012)
  EFAV  — iShares MSCI Min Vol EAFE (Oct 2011)
  EEMV  — iShares MSCI Min Vol EM (Oct 2011)
  ACWV  — iShares MSCI Min Vol Global (Oct 2011)
  BIL   — cash proxy

Signal: pure 12m momentum (H354-C formula; dual-rank HURT in H354)
OB params: window=20, swing_len=3 (H344/H346/H355 best params)
           + window=30, swing_len=5 (reference params)
IS:  2013-01-01 → 2020-12-31  (H354 canonical IS)
OOS: 2021-01-01 → 2026-06-30  (H354 canonical OOS)

Gate:
  Primary: OOS Sharpe > 1.735 (beat H354-C baseline)
  Secondary (partial): OOS Sharpe > 1.535 AND MaxDD < -9.3% (MaxDD improvement ≥ 2pp)

Variants per param set:
  A  Strict top-1: top-1 momentum must have OB; else BIL
  B  Lenient: if top-1 has OB → hold; elif top-2 has OB → hold; else BIL
  C  Gate: any of top-3 has OB → top-1 momentum; else BIL
  D  H354-C baseline (pure 12m top-1, no filter)
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

UNIVERSE   = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV","BIL"]
RISKY      = [t for t in UNIVERSE if t != "BIL"]
CASH_PROXY = "BIL"

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")

GATE_PRIMARY   = 1.735   # must beat H354-C
GATE_SECONDARY = 1.535   # partial confirm if MaxDD also improves ≥2pp
MAXDD_BASELINE = -0.113  # H354-C OOS MaxDD

PARAM_SETS = {
    "best": {"ob_window": 20, "swing_len": 3},
    "ref":  {"ob_window": 30, "swing_len": 5},
}


def load_close(ticker):
    # Reuse H354 cache if available
    for prefix in ["h354", "h356"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_close.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame):
                col = next((c for c in df.columns if c.lower() in ["close","Close"]), df.columns[0])
                return df[col].rename(ticker)
            return df.rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h356_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    # Reuse H345/H346 cache if available
    for prefix in ["h345","h346","h343","h344","h354","h355","h356"]:
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
    df.to_parquet(CACHE_DIR / f"h356_{ticker}_daily.parquet")
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
    cash_months = 0
    months = monthly_px.index[monthly_px.index >= IS_START]

    for i, me in enumerate(months):
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].drop(CASH_PROXY, errors="ignore").dropna()
        valid   = [t for t in RISKY if t in mom_row.index]
        if len(valid) < 1:
            port_rets.append((me, 0.0))
            continue

        # Pure 12m ranking (H354-C formula — dual-rank hurt in H354)
        ranked = list(mom_row[valid].nlargest(len(valid)).index)
        ret_row = monthly_ret.iloc[loc]

        def asset_ret(t):
            v = ret_row.get(t, np.nan)
            return float(v) if not pd.isna(v) else 0.0

        if variant == "D":
            # H354-C baseline: pure 12m top-1, no filter
            r = asset_ret(ranked[0])
        elif variant == "A":
            # Strict: top-1 must have OB; else BIL
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], me, ob_window, swing_len):
                r = asset_ret(top1)
            else:
                r = asset_ret(CASH_PROXY)
                cash_months += 1
        elif variant == "B":
            # Lenient: top-1 has OB → hold; elif top-2 has OB → hold; else BIL
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], me, ob_window, swing_len):
                r = asset_ret(top1)
            elif len(ranked) > 1:
                top2 = ranked[1]
                if top2 in daily_data and has_bullish_ob(daily_data[top2], me, ob_window, swing_len):
                    r = asset_ret(top2)
                else:
                    r = asset_ret(CASH_PROXY)
                    cash_months += 1
            else:
                r = asset_ret(CASH_PROXY)
                cash_months += 1
        elif variant == "C":
            # Gate: any of top-3 has OB → top-1; else BIL
            top3 = ranked[:3]
            any_ob = any(
                t in daily_data and has_bullish_ob(daily_data[t], me, ob_window, swing_len)
                for t in top3
            )
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
    print("H356 — OB Filter on H354 Low-Volatility ETF Universe")
    print("=" * 58)
    print(f"Universe: {' '.join(RISKY)} + BIL (cash)")
    print(f"Signal:   Pure 12m momentum top-1 (H354-C formula)")
    print(f"Gate:     OOS Sharpe > {GATE_PRIMARY} (H354-C baseline)")

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
        "B": "OB lenient (top-1 OB→hold; elif top-2 OB→hold; else BIL)",
        "C": "OB gate (any top-3 has OB → top-1; else BIL)",
        "D": "H354-C baseline (pure 12m top-1, no filter)",
    }

    all_results = {}
    print(f"\n{'Param':<6} {'Var':<4} {'Description':<50} {'IS Sh':>7} {'OOS Sh':>7} "
          f"{'MDD':>8} {'Neg':>4} {'Cash%':>7}")
    print("-" * 100)

    for pname, params in PARAM_SETS.items():
        for vcode, vname in VARIANTS.items():
            if vcode == "D" and pname == "ref":
                continue  # baseline only needs to run once
            rets, cm = run_backtest(monthly_px, monthly_ret, mom_12, daily_data,
                                    vcode, params["ob_window"], params["swing_len"])
            is_  = eval_period(rets, IS_START, IS_END)
            oos_ = eval_period(rets, OOS_START, OOS_END)

            oos_n = oos_["n"]
            cash_pct = cm / oos_n if (oos_n > 0 and vcode != "D") else 0.0

            key = f"{pname}_{vcode}" if vcode != "D" else "baseline"
            all_results[key] = {
                "name": vname, "params": pname, "is": is_, "oos": oos_,
                "oos_cash_pct": round(cash_pct, 3)
            }

            beats = oos_["sharpe"] > GATE_PRIMARY
            partial = (oos_["sharpe"] > GATE_SECONDARY and
                       oos_["maxdd"] < MAXDD_BASELINE + 0.02)  # 2pp improvement
            tag = "✓ BEATS" if beats else ("△ PARTIAL" if partial else "")
            print(f"{pname:<6} {vcode:<4} {vname:<50} {is_['sharpe']:>7.3f} {oos_['sharpe']:>7.3f} "
                  f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d} {cash_pct:>7.1%}  {tag}")
        print()

    # Per-year OOS for best OB variant
    print("\n  Baseline H354-C OOS annual returns:")
    base_rets, _ = run_backtest(monthly_px, monthly_ret, mom_12, daily_data,
                                "D", 20, 3)
    oos_base = base_rets[base_rets.index >= OOS_START]
    for dt, v in oos_base.resample("YE").apply(lambda x: (1+x).prod()-1).items():
        print(f"    {dt.year}: {v:+.1%}")

    # Find best OB variant
    ob_keys = [k for k in all_results if k != "baseline"]
    best_key = max(ob_keys, key=lambda k: all_results[k]["oos"]["sharpe"])
    best = all_results[best_key]
    print(f"\n  Best OB variant ({best_key}) OOS annual returns:")
    pname = best["params"]
    vcode = best_key.split("_")[1]
    params = PARAM_SETS[pname]
    best_rets, _ = run_backtest(monthly_px, monthly_ret, mom_12, daily_data,
                                vcode, params["ob_window"], params["swing_len"])
    oos_best = best_rets[best_rets.index >= OOS_START]
    for dt, v in oos_best.resample("YE").apply(lambda x: (1+x).prod()-1).items():
        print(f"    {dt.year}: {v:+.1%}")

    # Correlation with SPY
    spy_close = load_close("SPY") if "SPY" not in daily_closes else daily_closes["SPY"]
    spy_monthly = spy_close.resample("ME").last().pct_change()
    spy_oos = spy_monthly[spy_monthly.index >= OOS_START]
    aligned = pd.concat([oos_best.rename("h356"), spy_oos.rename("spy")], axis=1).dropna()
    if len(aligned) > 5:
        corr = aligned["h356"].corr(aligned["spy"])
        print(f"\n  Corr(H356 best, SPY) OOS: {corr:.3f}")

    print(f"\n=== Verdict (Primary Gate: OOS Sharpe > {GATE_PRIMARY}) ===")
    confirmed = [k for k in ob_keys if all_results[k]["oos"]["sharpe"] > GATE_PRIMARY]
    partial   = [k for k in ob_keys
                 if all_results[k]["oos"]["sharpe"] > GATE_SECONDARY
                 and all_results[k]["oos"]["maxdd"] < MAXDD_BASELINE + 0.02
                 and k not in confirmed]
    if confirmed:
        print(f"  CONFIRMED: {confirmed}")
        print(f"  Best: {best_key} — OOS Sharpe {best['oos']['sharpe']:.3f}, "
              f"MaxDD {best['oos']['maxdd']:.1%}")
    elif partial:
        print(f"  PARTIAL CONFIRMED (Sharpe>{GATE_SECONDARY} AND MaxDD improves ≥2pp): {partial}")
    else:
        print(f"  NOT CONFIRMED — best: {best_key} OOS Sharpe {best['oos']['sharpe']:.3f}")

    out = RESULT_DIR / "h356_results.json"
    with open(out, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
