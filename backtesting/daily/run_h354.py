"""
H354 — Low-Volatility Factor ETF Momentum Rotation
====================================================
Source: Ang, Hodrick, Xing & Zhang (2006) "The Cross-Section of Volatility and
Expected Returns" (JF); Baker, Bradley & Wurgler (2011) "Benchmarks as Limits to
Arbitrage" (FAJ). Low-vol ETFs launched 2011-2012 (USMV, SPLV, ACWV, EFAV, EEMV).

Hypothesis:
  Rotating among low-volatility factor ETFs using momentum outperforms
  buy-and-hold any single low-vol ETF and delivers equity-like returns
  with below-market drawdowns. Tests the "low-vol within low-vol" rotation.

Universe: 8 ETFs
  USMV  — iShares MSCI Min Vol USA (Oct 2011)
  SPLV  — Invesco S&P 500 Low Vol (May 2011)
  XLU   — Utilities SPDR (traditional low-vol proxy, since 1998)
  SPHD  — Invesco S&P 500 High Div Low Vol (Oct 2012)
  EFAV  — iShares MSCI Min Vol EAFE (Oct 2011)
  EEMV  — iShares MSCI Min Vol EM (Oct 2011)
  ACWV  — iShares MSCI Min Vol Global (Oct 2011)
  BIL   — cash proxy

Signal: 12m momentum + inv_6m_vol dual rank composite (same as H026)
IS: 2013-01-01 → 2020-12-31
OOS: 2021-01-01 → 2026-06-30
Gate: OOS Sharpe > 1.000  (vs SPY long-run OOS ~0.95)

Variants:
  A  Top-1 momentum (same signal as H026)
  B  Top-2 equal-weight
  C  Pure 12m momentum only (no vol-adjust rank)
  D  SPY buy-and-hold benchmark
  E  Equal-weight all non-cash ETFs
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

UNIVERSE = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV","BIL"]
RISKY    = [t for t in UNIVERSE if t != "BIL"]
CASH_PROXY = "BIL"

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE       = 1.000


def load_monthly(tickers):
    frames = []
    for t in tickers:
        cp = CACHE_DIR / f"h354_{t}_close.parquet"
        if cp.exists():
            s = pd.read_parquet(cp).squeeze()
        else:
            print(f"  Downloading {t}…")
            raw = yf.download(t, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(t, axis=1, level=1)
            s = raw["Close"].rename(t)
            pd.DataFrame(s).to_parquet(cp)
        frames.append(s.rename(t))
    return pd.DataFrame(frames).T


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


def run_backtest(daily_px, variant):
    monthly_px  = daily_px.resample("ME").last()
    daily_ret   = daily_px.pct_change()
    monthly_ret = daily_ret.resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    vol_6       = monthly_ret.rolling(6).std() * np.sqrt(12)

    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for i, me in enumerate(months):
        loc = monthly_px.index.get_loc(me)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].drop(CASH_PROXY, errors="ignore").dropna()
        vol_row = vol_6.iloc[loc].drop(CASH_PROXY, errors="ignore").dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < 1:
            port_rets.append((me, 0.0))
            continue

        ret_row = monthly_ret.iloc[loc]

        if variant == "D":
            # SPY buy-and-hold (need SPY in dataset)
            r = ret_row.get("SPY", 0.0)
        elif variant == "E":
            # Equal-weight all risky ETFs available this month
            avail = [t for t in RISKY if t in ret_row.index and not pd.isna(ret_row[t])]
            r = ret_row[avail].mean() if avail else 0.0
        else:
            score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
            ranked = list(score.nlargest(len(valid)).index)

            if variant == "A":
                selected = [ranked[0]]
            elif variant == "B":
                selected = ranked[:2]
            elif variant == "C":
                pure_rank = list(mom_row[valid].nlargest(len(valid)).index)
                selected = [pure_rank[0]]
            else:
                selected = [ranked[0]]

            avail = [t for t in selected if t in ret_row.index and not pd.isna(ret_row[t])]
            r = ret_row[avail].mean() if avail else 0.0

        port_rets.append((me, float(r) if not pd.isna(r) else 0.0))

    s = pd.Series({d: v for d, v in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H354 — Low-Volatility Factor ETF Momentum Rotation")
    print("=" * 55)

    # Download SPY too for benchmark
    all_tickers = UNIVERSE + ["SPY"]
    print("\nLoading price data…")
    daily_px = load_monthly(all_tickers)
    print(f"  Loaded {len(daily_px.columns)} tickers, {len(daily_px)} days")

    VARIANTS = {
        "A": "Top-1 mom+invvol rank",
        "B": "Top-2 equal-weight mom+invvol",
        "C": "Top-1 pure 12m momentum",
        "D": "SPY buy-and-hold",
        "E": "Equal-weight all low-vol ETFs",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<35} {'IS Sh':>8} {'OOS Sh':>8} {'OOS MDD':>8} {'Neg':>4}")
    print("-" * 70)

    for vcode, vname in VARIANTS.items():
        rets = run_backtest(daily_px, vcode)
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": vname, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE
        mark = "✓ BEATS GATE" if beats else ""
        print(f"{vcode:<4} {vname:<35} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  {mark}")

    # Per-year breakdown for top-2 variants
    for vcode in ["A","B","C"]:
        rets = run_backtest(daily_px, vcode)
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        print(f"\n  Var {vcode} OOS annual returns:")
        for dt, v in yr.items():
            print(f"    {dt.year}: {v:+.1%}")

    # Correlation with production portfolio
    print("\n  Correlation of variants with SPY (OOS):")
    spy_rets = run_backtest(daily_px, "D")
    spy_oos  = spy_rets[spy_rets.index >= OOS_START]
    for vcode in ["A","B","C","E"]:
        rets = run_backtest(daily_px, vcode)
        oos_slice = rets[rets.index >= OOS_START]
        aligned = pd.concat([oos_slice, spy_oos], axis=1).dropna()
        if len(aligned) > 5:
            corr = aligned.iloc[:,0].corr(aligned.iloc[:,1])
            print(f"    {vcode}: {corr:.3f}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    confirmed = [v for v in ["A","B","C"] if results[v]["oos"]["sharpe"] > GATE]
    if confirmed:
        best = max(["A","B","C"], key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  CONFIRMED variants: {confirmed}")
        print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}")
    else:
        print("  NOT CONFIRMED — no variant beats gate")

    out = RESULT_DIR / "h354_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
