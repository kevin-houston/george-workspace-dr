"""
H364 — Stacked OB Filter + VIX<20 Regime Gate on H354 Low-Vol ETF Universe
===========================================================================
H361 CONFIRMED: OB lenient filter (Var B) → OOS Sharpe 1.903, Corr(SPY)=0.621
H362 CONFIRMED: VIX<20 regime gate (Var B) → OOS Sharpe 1.819, MaxDD -8.0%

Hypothesis:
  Stack both filters: apply the OB lenient gate (H361 Var B) AND the VIX<20
  regime gate (H362 Var B) jointly on H354's low-vol ETF universe. If both
  improvements are additive, OOS Sharpe should exceed 1.903 (H361 best) with
  MaxDD better than -8.0% (H362 best). If stacking hurts, test each standalone
  to find the dominant filter.

Universe: H354 low-vol ETF universe (7 risky ETFs + BIL)
  USMV / SPLV / XLU / SPHD / EFAV / EEMV / ACWV / BIL

Signal: Pure 12m momentum (H354 Var C — confirmed best across all three prior hypotheses)

Variants:
  A  OB-only (H361 Var B reproduction — standalone reference)
  B  VIX<20-only (H362 Var B reproduction — standalone reference)
  C  Stacked: OB lenient AND VIX<20 (primary hypothesis)
  D  Stacked with fallback: OB lenient AND VIX<20; if VIX<20 but no OB → try top-2
  E  H354 Var C baseline (pure 12m top-1, no filters)

IS:  2013-01-01 → 2020-12-31
OOS: 2021-01-01 → 2026-06-30
Gate: OOS Sharpe > 1.903 (H361 Var B baseline)
      Secondary: Corr(SPY) < 0.621 (H361 Var B baseline)
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

UNIVERSE   = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV"]
CASH_PROXY = "BIL"
ALL_TICKERS = UNIVERSE + [CASH_PROXY, "SPY"]

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")

GATE_SHARPE  = 1.903   # H361 Var B OOS Sharpe
GATE_CORR    = 0.621   # H361 Var B Corr(SPY) — need to stay below

OB_WINDOW  = 20        # best from H344/H346/H361
SWING_LEN  = 3
VIX_THRESH = 20.0      # H362 Var B confirmed threshold


def load_close(ticker):
    """Load daily close — check H354/H361/H362 cache first."""
    for prefix in ["h354","h361","h362","h355","h346","h345"]:
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
    print(f"  Downloading {ticker} close…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h364_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    """Load daily OHLCV for OB detection — check H361/H355/H346 caches first."""
    for prefix in ["h361","h355","h346","h345","h344","h343"]:
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
    df.to_parquet(CACHE_DIR / f"h364_{ticker}_daily.parquet")
    return df


def load_vix():
    """Load VIX daily — check H362/H249/H301 caches first."""
    for pfx in ["h362","h249","h301","h364"]:
        p = CACHE_DIR / f"{pfx}_VIX_close.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame):
                return df.squeeze().rename("VIX")
            return df.rename("VIX")
    print("  Downloading ^VIX…")
    raw = yf.download("^VIX", start=DATA_START, end=DATA_END, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^VIX", axis=1, level=1)
    s = raw["Close"].rename("VIX")
    pd.DataFrame(s).to_parquet(CACHE_DIR / "h364_VIX_close.parquet")
    return s


def has_bullish_ob(daily_df, as_of, ob_window=OB_WINDOW, swing_len=SWING_LEN):
    """Return True if ticker has an unmitigated bullish OB as of date."""
    sub = daily_df[daily_df.index <= as_of].tail(ob_window + swing_len * 2)
    if len(sub) < swing_len * 2 + 2:
        return False
    try:
        ohlcv = sub[["open","high","low","close","volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
        bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
        return len(bull) > 0
    except Exception:
        return False


def build_signal(daily_closes):
    etf_tickers = [t for t in UNIVERSE + [CASH_PROXY] if t in daily_closes]
    daily_df    = pd.DataFrame({t: daily_closes[t] for t in etf_tickers}).sort_index()
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, mom_12


def run_backtest(monthly_px, monthly_ret, mom_12, daily_ohlcv,
                 vix_monthly, variant):
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

        # Rank by pure 12m momentum (H354 Var C signal)
        ranked = list(mom_row[valid].nlargest(len(valid)).index)
        top1_ret = asset_ret(ranked[0])

        # VIX regime check (H362 Var B: VIX < 20)
        vix_val = float(vix_monthly.get(me, 15.0))
        vix_ok  = vix_val < VIX_THRESH

        if variant == "E":
            # Baseline: pure 12m top-1
            r = top1_ret

        elif variant == "A":
            # OB-only (H361 Var B reproduction)
            top1 = ranked[0]
            ob_top1 = top1 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top1], me)
            if ob_top1:
                r = asset_ret(top1)
            elif len(ranked) >= 2:
                top2 = ranked[1]
                ob_top2 = top2 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top2], me)
                r = asset_ret(top2) if ob_top2 else cash_ret()
            else:
                r = cash_ret()

        elif variant == "B":
            # VIX<20-only (H362 Var B reproduction)
            r = top1_ret if vix_ok else cash_ret()

        elif variant == "C":
            # Stacked: BOTH OB lenient AND VIX<20 required
            # If VIX >= 20 → BIL regardless of OB
            # If VIX < 20 → apply OB lenient logic
            if not vix_ok:
                r = cash_ret()
            else:
                top1 = ranked[0]
                ob_top1 = top1 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top1], me)
                if ob_top1:
                    r = asset_ret(top1)
                elif len(ranked) >= 2:
                    top2 = ranked[1]
                    ob_top2 = top2 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top2], me)
                    r = asset_ret(top2) if ob_top2 else cash_ret()
                else:
                    r = cash_ret()

        elif variant == "D":
            # Stacked with softer fallback:
            # VIX<20 required; if OB top-1 available → take it;
            # if no OB but VIX<20 → still take top-1 (OB as enhancement not gate);
            # if VIX>=20 → BIL
            # This tests whether VIX gate is the dominant improvement
            if not vix_ok:
                r = cash_ret()
            else:
                # VIX<20: take top-1 unconditionally (OB not required)
                # This is pure VIX gate — should match Var B
                r = top1_ret

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
    print("H364 — Stacked OB Filter + VIX<20 Regime Gate on H354 Low-Vol ETF Universe")
    print("=" * 75)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H361 Var B baseline)")
    print(f"      Corr(SPY) < {GATE_CORR} (H361 Var B baseline)\n")

    print("Loading close data…")
    daily_closes = {}
    for t in ALL_TICKERS:
        try:
            daily_closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    monthly_px, monthly_ret, mom_12 = build_signal(daily_closes)

    print("Loading OHLCV for OB detection…")
    daily_ohlcv = {}
    for t in UNIVERSE:
        try:
            daily_ohlcv[t] = load_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    print("Loading VIX…")
    try:
        vix_daily   = load_vix()
        vix_monthly = vix_daily.resample("ME").last()
    except Exception as e:
        print(f"  WARN VIX: {e}")
        vix_monthly = pd.Series(dtype=float)

    VARIANTS = {
        "A": "OB-only (H361 Var B reproduction)",
        "B": "VIX<20-only (H362 Var B reproduction)",
        "C": "Stacked: OB lenient AND VIX<20 (primary)",
        "D": "VIX<20 gate only — verify matches Var B",
        "E": "H354 Var C baseline (pure 12m top-1)",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<48} {'IS Sh':>8} {'OOS Sh':>8} {'MDD':>8} {'Neg':>4}")
    print("-" * 82)

    variant_rets = {}
    for vcode, vname in VARIANTS.items():
        rets = run_backtest(monthly_px, monthly_ret, mom_12,
                            daily_ohlcv, vix_monthly, vcode)
        variant_rets[vcode] = rets
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": vname, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE_SHARPE
        print(f"{vcode:<4} {vname:<48} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  {'✓ BEATS GATE' if beats else ''}")

    # Per-year OOS breakdown
    print()
    for vcode in ["A","B","C","D","E"]:
        rets = variant_rets[vcode]
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        print(f"  Var {vcode} OOS annual: ", end="")
        print("  ".join(f"{dt.year}:{v:+.1%}" for dt, v in yr.items()))

    # Cash months in OOS
    print("\n  Cash months (BIL) in OOS:")
    base_rets = variant_rets["E"]
    for vcode in ["A","B","C","D"]:
        rets = variant_rets[vcode]
        oos_v = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        oos_b = base_rets[(base_rets.index >= OOS_START) & (base_rets.index <= OOS_END)]
        aligned = pd.concat([oos_v, oos_b], axis=1).dropna()
        if len(aligned) > 0:
            aligned.columns = ["filtered","baseline"]
            cash_months = (aligned["filtered"] < 0.003).sum()
            print(f"    Var {vcode}: ~{cash_months} months in cash ({cash_months/len(oos_v)*100:.1f}%)")

    # Correlation with SPY (OOS)
    print("\n  Correlation with SPY (OOS):")
    spy_cp = CACHE_DIR / "h354_SPY_close.parquet"
    spy_found = False
    for pfx in ["h354","h362","h361","h364"]:
        cp = CACHE_DIR / f"{pfx}_SPY_close.parquet"
        if cp.exists():
            spy_found = True
            spy_close_raw = pd.read_parquet(cp)
            if isinstance(spy_close_raw, pd.DataFrame):
                spy_close_raw = spy_close_raw.squeeze()
            spy_daily_s  = spy_close_raw.rename("SPY")
            spy_monthly_r = spy_daily_s.resample("ME").last().pct_change()
            for vcode in ["A","B","C","D","E"]:
                rets = variant_rets[vcode]
                oos_slice = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
                spy_oos = spy_monthly_r[(spy_monthly_r.index >= OOS_START) &
                                        (spy_monthly_r.index <= OOS_END)]
                aligned = pd.concat([oos_slice, spy_oos], axis=1).dropna()
                if len(aligned) > 5:
                    corr = aligned.iloc[:,0].corr(aligned.iloc[:,1])
                    print(f"    Var {vcode}: {corr:.3f}  {'✓ BELOW GATE' if corr < GATE_CORR else ''}")
            break
    if not spy_found:
        print("    (SPY cache not found — skipping correlation)")

    # VIX distribution in OOS
    if len(vix_monthly) > 0:
        oos_vix = vix_monthly[(vix_monthly.index >= OOS_START) &
                               (vix_monthly.index <= OOS_END)]
        if len(oos_vix) > 0:
            low_v = (oos_vix < VIX_THRESH).sum()
            print(f"\n  VIX < {VIX_THRESH}: {low_v}/{len(oos_vix)} months ({low_v/len(oos_vix)*100:.1f}%)")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE_SHARPE}) ===")
    test_variants = ["A","B","C","D"]
    confirmed = [v for v in test_variants if results[v]["oos"]["sharpe"] > GATE_SHARPE]
    if confirmed:
        best = max(confirmed, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  CONFIRMED variants: {confirmed}")
        print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}, "
              f"MaxDD {results[best]['oos']['maxdd']:.1%}")
        # Check if stacking (Var C) is additive over either standalone
        c_sh = results["C"]["oos"]["sharpe"]
        a_sh = results["A"]["oos"]["sharpe"]
        b_sh = results["B"]["oos"]["sharpe"]
        if c_sh > max(a_sh, b_sh):
            print(f"  Stacking IS additive: C({c_sh:.3f}) > A({a_sh:.3f}), B({b_sh:.3f})")
        else:
            dominant = "A (OB)" if a_sh > b_sh else "B (VIX<20)"
            print(f"  Stacking NOT additive — dominant filter is {dominant}")
            print(f"  C({c_sh:.3f}) vs A({a_sh:.3f}) vs B({b_sh:.3f})")
        print(f"  H364 CONFIRMED")
    else:
        best_all = max(test_variants, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  NOT CONFIRMED — best Var {best_all}: "
              f"OOS {results[best_all]['oos']['sharpe']:.3f} < {GATE_SHARPE}")
        a_sh = results["A"]["oos"]["sharpe"]
        b_sh = results["B"]["oos"]["sharpe"]
        c_sh = results["C"]["oos"]["sharpe"]
        print(f"  Standalone A (OB): {a_sh:.3f} | Standalone B (VIX<20): {b_sh:.3f} | "
              f"Stacked C: {c_sh:.3f}")

    out = RESULT_DIR / "h364_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
