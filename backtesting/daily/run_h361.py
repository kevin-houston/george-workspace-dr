"""
H361 — OB Filter on H354 Low-Vol ETF Universe
===============================================
H343/H344/H345/H346 confirmed Order Block filter on stock momentum (H198) and
sector ETF rotation (H026). H355 confirmed OB filter on bond ETF rotation (H045).
H354 confirmed low-vol ETF momentum rotation (OOS Sharpe 1.735, Var C pure 12m).

Hypothesis:
  Applying the Order Block confirmation filter to H354's low-vol ETF universe
  improves OOS Sharpe beyond the H354 Var C baseline (1.735).

Universe: H354 low-vol ETF universe (7 risky ETFs + cash)
  USMV  — iShares MSCI Min Vol USA (Oct 2011)
  SPLV  — Invesco S&P 500 Low Vol (May 2011)
  XLU   — Utilities SPDR (traditional low-vol proxy, since 1998)
  SPHD  — Invesco S&P 500 High Div Low Vol (Oct 2012)
  EFAV  — iShares MSCI Min Vol EAFE (Oct 2011)
  EEMV  — iShares MSCI Min Vol EM (Oct 2011)
  ACWV  — iShares MSCI Min Vol Global (Oct 2011)
  BIL   — cash proxy

Signal: Pure 12m momentum (H354 Var C — best performer)
OB filter: window=20, swing_len=3 (best from H344/H346)
IS: 2013-01-01 → 2020-12-31
OOS: 2021-01-01 → 2026-06-30
Gate: OOS Sharpe > 1.735 (H354 Var C baseline)

Variants:
  A  OB strict — top-1 only if has bullish OB in last 30d; else BIL
  B  OB lenient — top-1 if has OB; else top-2 unfiltered if both available
  C  OB gate — any of top-3 has OB → take top-1; else BIL
  D  H354 Var C baseline (pure 12m top-1, no OB filter)
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
ALL_TICKERS = UNIVERSE + [CASH_PROXY]

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE       = 1.735   # H354 Var C OOS Sharpe

OB_WINDOW  = 20
SWING_LEN  = 3
OB_LOOKBACK_DAYS = 30   # days before month-end to check for OB


def load_close(ticker):
    """Load daily close — check H354 cache first."""
    for prefix in ["h354","h355","h346","h345","h361"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_close.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df, pd.DataFrame):
                df.columns = [c.lower() for c in df.columns]
                col = next((c for c in ["close","Close"] if c in df.columns), None)
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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h361_{ticker}_close.parquet")
    return s


def load_ohlcv(ticker):
    """Load daily OHLCV for OB detection."""
    for prefix in ["h355","h346","h345","h344","h343","h361"]:
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
    df.to_parquet(CACHE_DIR / f"h361_{ticker}_daily.parquet")
    return df


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
    daily_df    = pd.DataFrame(daily_closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, mom_12


def run_backtest(monthly_px, monthly_ret, mom_12, daily_ohlcv, variant):
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    # Get BIL return series for cash
    bil_ret = monthly_ret.get("BIL") if "BIL" in monthly_ret.columns else None

    for me in months:
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row  = mom_12.iloc[loc]
        valid    = [t for t in UNIVERSE if t in mom_row.index and not pd.isna(mom_row[t])]
        if not valid:
            port_rets.append((me, 0.0))
            continue

        ret_row  = monthly_ret.iloc[loc]

        def asset_ret(t):
            v = ret_row.get(t, 0.0)
            return float(v) if not pd.isna(v) else 0.0

        def cash_ret():
            v = ret_row.get(CASH_PROXY, 0.0)
            return float(v) if not pd.isna(v) else 0.0

        # Rank by pure 12m momentum (H354 Var C signal)
        ranked = list(mom_row[valid].nlargest(len(valid)).index)

        if variant == "D":
            # H354 Var C baseline: top-1 pure 12m, no filter
            r = asset_ret(ranked[0])

        elif variant == "A":
            # Strict: top-1 must have OB; else BIL
            top1 = ranked[0]
            ob_ok = top1 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top1], me)
            r = asset_ret(top1) if ob_ok else cash_ret()

        elif variant == "B":
            # Lenient: top-1 if has OB; else try top-2 if available; else BIL
            top1 = ranked[0]
            ob_top1 = top1 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top1], me)
            if ob_top1:
                r = asset_ret(top1)
            elif len(ranked) >= 2:
                top2 = ranked[1]
                ob_top2 = top2 in daily_ohlcv and has_bullish_ob(daily_ohlcv[top2], me)
                if ob_top2:
                    r = asset_ret(top2)
                else:
                    r = cash_ret()
            else:
                r = cash_ret()

        elif variant == "C":
            # Gate: if any of top-3 has OB → take top-1; else BIL
            top3 = ranked[:min(3, len(ranked))]
            any_ob = any(
                t in daily_ohlcv and has_bullish_ob(daily_ohlcv[t], me)
                for t in top3
            )
            r = asset_ret(ranked[0]) if any_ob else cash_ret()

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
    print("H361 — OB Filter on H354 Low-Vol ETF Universe")
    print("=" * 55)
    print(f"Gate: OOS Sharpe > {GATE} (H354 Var C baseline)")

    print("\nLoading close data…")
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

    VARIANTS = {
        "A": "OB strict (top-1 must have OB; else BIL)",
        "B": "OB lenient (top-1 if OB; top-2 if OB; else BIL)",
        "C": "OB gate (any of top-3 has OB → top-1; else BIL)",
        "D": "H354 Var C baseline (pure 12m top-1)",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<48} {'IS Sh':>8} {'OOS Sh':>8} {'MDD':>8} {'Neg':>4}")
    print("-" * 80)

    variant_rets = {}
    for vcode, vname in VARIANTS.items():
        rets = run_backtest(monthly_px, monthly_ret, mom_12, daily_ohlcv, vcode)
        variant_rets[vcode] = rets
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": vname, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE
        print(f"{vcode:<4} {vname:<48} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  {'✓ BEATS GATE' if beats else ''}")

    # Per-year OOS breakdown for OB variants
    for vcode in ["A","B","C","D"]:
        rets = variant_rets[vcode]
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        print(f"\n  Var {vcode} OOS annual:")
        for dt, v in yr.items():
            print(f"    {dt.year}: {v:+.1%}")

    # Count cash months for OB variants (OOS)
    print("\n  Cash months (BIL) in OOS:")
    for vcode in ["A","B","C"]:
        rets = variant_rets[vcode]
        base = variant_rets["D"]
        oos_v = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        oos_b = base[(base.index >= OOS_START) & (base.index <= OOS_END)]
        # Cash = month where filtered version differs from unfiltered
        aligned = pd.concat([oos_v, oos_b], axis=1).dropna()
        aligned.columns = ["filtered","baseline"]
        # BIL months: filtered return ≈ BIL (very small positive return)
        cash_months = (aligned["filtered"] < 0.003).sum()
        print(f"    Var {vcode}: ~{cash_months} months in cash ({cash_months/len(oos_v)*100:.1f}%)")

    # Correlation with SPY (OOS)
    print("\n  Correlation with SPY (OOS):")
    spy_cp = CACHE_DIR / "h354_SPY_close.parquet"
    if spy_cp.exists():
        spy_daily = pd.read_parquet(spy_cp).squeeze().rename("SPY")
        spy_monthly = spy_daily.resample("ME").last().pct_change()
        for vcode in ["A","B","C","D"]:
            rets = variant_rets[vcode]
            oos_slice = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
            spy_oos = spy_monthly[(spy_monthly.index >= OOS_START) & (spy_monthly.index <= OOS_END)]
            aligned = pd.concat([oos_slice, spy_oos], axis=1).dropna()
            if len(aligned) > 5:
                corr = aligned.iloc[:,0].corr(aligned.iloc[:,1])
                print(f"    Var {vcode}: {corr:.3f}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    test_variants = ["A","B","C"]
    confirmed = [v for v in test_variants if results[v]["oos"]["sharpe"] > GATE]
    if confirmed:
        best = max(test_variants, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  CONFIRMED variants: {confirmed}")
        print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}")
        print(f"  H361 CONFIRMED — OB filter improves H354 low-vol ETF rotation")
    else:
        best = max(test_variants, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  NOT CONFIRMED — best Var {best} OOS Sharpe {results[best]['oos']['sharpe']:.3f} < {GATE}")

    out = RESULT_DIR / "h361_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
