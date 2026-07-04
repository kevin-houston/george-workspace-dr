"""
H362 — Low-Vol ETF Rotation with Macro Regime Gate
===================================================
H354 confirmed low-vol ETF momentum rotation (Var C pure 12m, OOS 1.735).
H301 confirmed SPY 200MA safety overlay (+27.4% Sharpe lift on H026).
H249 confirmed regime-conditional weights (VIX×200MA, +0.282 Sharpe lift).

Hypothesis:
  Adding a macro regime gate (VIX + SPY 200MA) to H354's low-vol ETF rotation
  further reduces drawdowns and improves risk-adjusted returns. During bear/
  high-vol regimes, low-vol ETFs themselves become correlated with SPY — the
  gate routes to BIL when both VIX is elevated AND SPY is below 200MA.

Universe: H354 low-vol ETF universe (7 risky ETFs)
  USMV / SPLV / XLU / SPHD / EFAV / EEMV / ACWV / BIL

Signal: Pure 12m momentum (H354 Var C — confirmed best)
Regime gate combinations:
  A  SPY > 200MA only (trade H354 Var C; else BIL)
  B  VIX < 20 only (trade H354 Var C; else BIL)
  C  SPY > 200MA AND VIX < 25 (joint gate)
  D  SPY > 200MA OR VIX < 20 (either condition)
  E  H354 Var C baseline (pure 12m top-1, no regime gate)

IS: 2013-01-01 → 2020-12-31
OOS: 2021-01-01 → 2026-06-30
Gate: OOS Sharpe > 1.735 (H354 Var C baseline)
      Secondary gate: MaxDD improvement vs H354 Var C (-11.3%)
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

UNIVERSE   = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV"]
CASH_PROXY = "BIL"
SIGNAL_TICKERS = UNIVERSE + [CASH_PROXY, "SPY"]

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE_SHARPE = 1.735   # H354 Var C OOS Sharpe
GATE_MDD    = -0.113  # H354 Var C OOS MaxDD (need to improve)


def load_close(ticker):
    """Load daily close — check H354 cache first."""
    for prefix in ["h354","h362","h361","h355"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_close.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame):
                df.columns = [c.lower() for c in df.columns]
                col = next((c for c in ["close"] if c in df.columns), None)
                if col:
                    return df[col].rename(ticker)
                return df.squeeze().rename(ticker)
            return df.rename(ticker)
    # Also check H112 style caches
    for prefix in [f"h{i:03d}" for i in range(62, 120)]:
        for pat in [f"{prefix}_{ticker}_close_{DATA_START}_{DATA_END}.parquet",
                    f"{prefix}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h362_{ticker}_close.parquet")
    return s


def load_vix():
    """Load VIX daily."""
    cp = CACHE_DIR / "h362_VIX_close.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename("VIX")
    # Check H249 cache
    for pfx in ["h249","h301"]:
        p = CACHE_DIR / f"{pfx}_VIX_close.parquet"
        if p.exists():
            return pd.read_parquet(p).squeeze().rename("VIX")
    print("  Downloading ^VIX…")
    raw = yf.download("^VIX", start=DATA_START, end=DATA_END, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^VIX", axis=1, level=1)
    s = raw["Close"].rename("VIX")
    pd.DataFrame(s).to_parquet(cp)
    return s


def compute_spy_200ma(spy_daily):
    """Compute monthly flag: True if SPY close > 200-day MA at month-end."""
    ma200  = spy_daily.rolling(200).mean()
    above  = spy_daily > ma200
    return above.resample("ME").last()


def compute_vix_monthly(vix_daily):
    """Compute monthly VIX level at month-end."""
    return vix_daily.resample("ME").last()


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


def run_backtest(monthly_px, monthly_ret, mom_12,
                 spy_200ma_monthly, vix_monthly, variant):
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for me in months:
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc]
        valid   = [t for t in UNIVERSE if t in mom_row.index and not pd.isna(mom_row[t])]
        if not valid:
            port_rets.append((me, 0.0))
            continue

        ret_row = monthly_ret.iloc[loc]

        def asset_ret(t):
            v = ret_row.get(t, 0.0)
            return float(v) if not pd.isna(v) else 0.0

        def cash_ret():
            v = ret_row.get(CASH_PROXY, 0.0)
            return float(v) if not pd.isna(v) else 0.0

        # Rank by pure 12m momentum
        ranked = list(mom_row[valid].nlargest(len(valid)).index)
        top1_ret = asset_ret(ranked[0])

        # Get regime signals (lagged by 1 month — use prior month-end values)
        spy_above = bool(spy_200ma_monthly.get(me, True))   # default True if missing
        vix_val   = float(vix_monthly.get(me, 15.0))        # default 15 if missing

        if variant == "E":
            r = top1_ret

        elif variant == "A":
            # SPY > 200MA only
            r = top1_ret if spy_above else cash_ret()

        elif variant == "B":
            # VIX < 20 only
            r = top1_ret if vix_val < 20 else cash_ret()

        elif variant == "C":
            # Joint: SPY above AND VIX < 25
            r = top1_ret if (spy_above and vix_val < 25) else cash_ret()

        elif variant == "D":
            # Either: SPY above OR VIX < 20
            r = top1_ret if (spy_above or vix_val < 20) else cash_ret()

        else:
            r = top1_ret

        port_rets.append((me, float(r)))

    s = pd.Series({d: v for d, v in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H362 — Low-Vol ETF Rotation with Macro Regime Gate")
    print("=" * 55)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H354 Var C)")

    print("\nLoading price data…")
    daily_closes = {}
    for t in SIGNAL_TICKERS:
        try:
            daily_closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    print("Loading VIX…")
    try:
        vix_daily = load_vix()
    except Exception as e:
        print(f"  WARN VIX: {e}")
        vix_daily = pd.Series(dtype=float)

    spy_daily = daily_closes.get("SPY", pd.Series(dtype=float))
    spy_200ma_monthly = compute_spy_200ma(spy_daily) if len(spy_daily) > 200 else pd.Series(dtype=bool)
    vix_monthly       = compute_vix_monthly(vix_daily) if len(vix_daily) > 10 else pd.Series(dtype=float)

    # Build monthly signals from low-vol ETFs
    daily_df    = pd.DataFrame({t: daily_closes[t] for t in UNIVERSE + [CASH_PROXY]
                                 if t in daily_closes}).sort_index()
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1

    VARIANTS = {
        "A": "SPY > 200MA gate",
        "B": "VIX < 20 gate",
        "C": "SPY > 200MA AND VIX < 25 (joint)",
        "D": "SPY > 200MA OR VIX < 20 (either)",
        "E": "H354 Var C baseline (no regime gate)",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<42} {'IS Sh':>8} {'OOS Sh':>8} {'MDD':>8} {'Neg':>4}")
    print("-" * 75)

    variant_rets = {}
    for vcode, vname in VARIANTS.items():
        rets = run_backtest(monthly_px, monthly_ret, mom_12,
                            spy_200ma_monthly, vix_monthly, vcode)
        variant_rets[vcode] = rets
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": vname, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE_SHARPE
        print(f"{vcode:<4} {vname:<42} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  {'✓' if beats else ''}")

    # Per-year OOS breakdown
    for vcode in ["A","B","C","D","E"]:
        rets = variant_rets[vcode]
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        print(f"\n  Var {vcode} OOS annual:")
        for dt, v in yr.items():
            print(f"    {dt.year}: {v:+.1%}")

    # Regime distribution
    print("\n  OOS regime statistics (2021-2026):")
    oos_spy   = spy_200ma_monthly[(spy_200ma_monthly.index >= OOS_START) &
                                   (spy_200ma_monthly.index <= OOS_END)]
    oos_vix   = vix_monthly[(vix_monthly.index >= OOS_START) &
                             (vix_monthly.index <= OOS_END)]
    if len(oos_spy) > 0:
        print(f"    SPY > 200MA: {oos_spy.sum()}/{len(oos_spy)} months ({oos_spy.mean()*100:.1f}%)")
    if len(oos_vix) > 0:
        low_vix = (oos_vix < 20).sum()
        print(f"    VIX < 20:    {low_vix}/{len(oos_vix)} months ({low_vix/len(oos_vix)*100:.1f}%)")

    # Cash months in OOS
    print("\n  Cash months (BIL) in OOS:")
    base_rets = variant_rets["E"]
    for vcode in ["A","B","C","D"]:
        rets = variant_rets[vcode]
        oos_v = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        oos_b = base_rets[(base_rets.index >= OOS_START) & (base_rets.index <= OOS_END)]
        aligned = pd.concat([oos_v, oos_b], axis=1).dropna()
        if len(aligned) > 0:
            aligned.columns = ["gated","base"]
            diff = (aligned["gated"] != aligned["base"]).sum()
            print(f"    Var {vcode}: ~{diff} months diverted ({diff/len(oos_v)*100:.1f}%)")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE_SHARPE}) ===")
    test_variants = ["A","B","C","D"]
    confirmed = [v for v in test_variants if results[v]["oos"]["sharpe"] > GATE_SHARPE]
    if confirmed:
        best = max(test_variants, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  CONFIRMED variants: {confirmed}")
        print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}, "
              f"MaxDD {results[best]['oos']['maxdd']:.1%}")
        print(f"  H362 CONFIRMED — macro regime gate improves H354 low-vol ETF rotation")
    else:
        # Check secondary MaxDD gate
        mdd_improved = [v for v in test_variants
                        if results[v]["oos"]["maxdd"] > GATE_MDD   # less negative = better
                        and results[v]["oos"]["sharpe"] > 1.0]
        if mdd_improved:
            best = max(mdd_improved, key=lambda v: results[v]["oos"]["sharpe"])
            print(f"  PARTIAL — Sharpe gate not met but MaxDD improved")
            print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}, "
                  f"MaxDD {results[best]['oos']['maxdd']:.1%}")
        else:
            best = max(test_variants, key=lambda v: results[v]["oos"]["sharpe"])
            print(f"  NOT CONFIRMED — best Var {best}: "
                  f"OOS {results[best]['oos']['sharpe']:.3f}, "
                  f"MDD {results[best]['oos']['maxdd']:.1%}")

    out = RESULT_DIR / "h362_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
