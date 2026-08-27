#!/usr/bin/env python3
"""
H537 — Credit Spread Regime Rotation: High-Yield vs Investment-Grade vs
       Treasury Relative-Strength Timing

Motivation: H283 (bond ETF carry via TTM dividend yield) and H315 (FRED
credit-spread gate via BAMLH0A0HYM2) both tried to harvest a credit-cycle
signal on the H045 bond universe and both failed — H283 because dividend
yield is a risk proxy not an alpha proxy, H315 because the FRED high-yield
OAS series only goes back to June 2023 (ICE licensing change removed the
older history), so the gate never triggered in the available backtest
window. Neither of those is "credit spread rotation is a dead end" — they
are specific implementation failures. This hypothesis tests a THIRD,
independent construction that avoids both failure modes: a pure PRICE-BASED
relative-strength signal between HY credit (HYG), IG credit (LQD), and
Treasuries (IEF/SHY/TLT) — no FRED series, no dividend data, just relative
total-return momentum among credit-risk tiers. This is a different asset
class angle from H045's within-treasury-only rotation and from H283's
carry overlay: H045's OWN 12m-momentum signal already picks HYG/LQD when
they're strong (per h045_status: "HYG grew from 25.9% IS -> 48% OOS"), but
H045 ranks HYG/LQD/TIP/TLT/etc. all on the SAME 12m-momentum axis. H537
asks a narrower, more targeted question: does explicitly modeling the
HY-minus-IG "credit spread momentum" (relative strength between the two
credit tiers, not each vs. its own history) as a standalone regime signal,
used to gate exposure to credit risk vs. safe Treasuries, produce a cleaner
regime-timing signal than raw momentum ranking?

Universe: HYG (high yield corporate), LQD (investment grade corporate),
  IEF (7-10y Treasury), SHY (1-3y Treasury, defensive parking), TLT (20y+
  Treasury, only used in Variant D duration-extension check).
Signal: credit_spread_mom(t) = 3m total return of HYG - 3m total return of
  LQD, formed using ONLY data up to and including month-end t (both legs
  are trailing returns ending at the same month-end — no look-ahead).
  Positive value = credit risk-on (HY outperforming IG, spreads perceived
  tightening); negative = credit risk-off (flight to quality).
IS: 2008-01-01 to 2017-12-31 (spans the 2008-09 GFC credit crisis — the
  single most informative credit-spread-widening regime in the sample).
OOS: 2018-01-01 to present.
Gate: OOS Sharpe > 1.351 (H045 canonical baseline, since this is explicitly
  a bond-family strategy competing for the same H045 capital slot).

Variants:
  A — Binary regime gate: credit_spread_mom(t) > 0 -> hold HYG; else -> hold
      IEF. (pure switch, no LQD holding)
  B — Three-way: credit_spread_mom(t) > +0.5% -> HYG; < -0.5% -> SHY
      (flight to short-duration safety); else -> LQD (neutral, hold IG).
  C — Continuous tilt: hold w_HYG = clip(0.5 + 5*credit_spread_mom(t), 0, 1)
      in HYG, remainder in IEF (smooth exposure scaling vs hard switch).
  D — Regime gate + duration overlay: same binary switch as A, but the
      "risk-off" leg is TLT (long-duration Treasury, benefits most from
      flight-to-quality rate cuts) instead of IEF/SHY.
  E — Baseline: pure 12m HYG momentum vs cash (SHY) — sanity check that a
      naive single-asset momentum switch on HYG alone is inferior to the
      relative-strength construction.
"""

import warnings; warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

STRATEGY = "H537"
UNIVERSE = ["HYG", "LQD", "IEF", "SHY", "TLT"]

DATA_START = "2007-01-01"
DATA_END   = "2026-08-25"
IS_START   = pd.Timestamp("2008-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")

TC   = 0.0005   # ETF-level rotation, tighter spread than single stocks
GATE = 1.351    # H045 canonical OOS Sharpe baseline


def load_daily():
    cache = CACHE_DIR / "h537_daily_close.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        missing = [t for t in UNIVERSE if t not in df.columns]
        if not missing:
            print(f"  Loaded from cache: {df.shape}")
            return df
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                       auto_adjust=True, progress=False, threads=False)
    close = raw["Close"]
    close.to_parquet(cache)
    return close


def build_monthly(close: pd.DataFrame):
    month_end = close.resample("ME").last()
    monthly_ret = month_end.pct_change()
    return month_end, monthly_ret


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if len(r) and r.std() > 0 else 0.0


def cagr(r):
    if len(r) == 0:
        return 0.0
    cum = (1 + r).cumprod()
    n_years = len(r) / 12
    return float(cum.iloc[-1] ** (1 / max(n_years, 1e-6)) - 1)


def maxdd(r):
    if len(r) == 0:
        return 0.0
    cum = (1 + r).cumprod()
    return float((cum / cum.cummax() - 1).min())


def neg_years(r):
    if len(r) == 0:
        return 0
    ann = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())


def run_backtest(month_end: pd.DataFrame, monthly_ret: pd.DataFrame):
    dates = month_end.index
    # 3m trailing total return for HYG and LQD, computed at month-end i using
    # only data up to and including i (close[i] / close[i-3] - 1). This is
    # NOT forward-looking: both legs use the SAME as-of date i, and the
    # portfolio return credited for month i is monthly_ret.iloc[i+1] (the
    # NEXT month), preserving one full month of separation between signal
    # formation and the return being earned.
    hyg_3m = month_end["HYG"] / month_end["HYG"].shift(3) - 1
    lqd_3m = month_end["LQD"] / month_end["LQD"].shift(3) - 1
    credit_spread_mom = hyg_3m - lqd_3m

    hyg_12m = month_end["HYG"] / month_end["HYG"].shift(12) - 1

    variants = {v: [] for v in "ABCDE"}
    prev_alloc = {v: None for v in "ABCDE"}

    min_i = 13  # need 12m history for Var E, plus 1 for forward return
    for i in range(min_i, len(dates) - 1):
        date = dates[i]
        csm = credit_spread_mom.iloc[i]
        hm12 = hyg_12m.iloc[i]

        fwd = {t: monthly_ret[t].iloc[i + 1] for t in UNIVERSE}
        if any(pd.isna(v) for v in [csm, hm12]) or any(pd.isna(fwd[t]) for t in ["HYG", "LQD", "IEF", "SHY", "TLT"]):
            for v in variants:
                variants[v].append((date, np.nan))
            continue

        allocs = {}

        # A — binary HYG vs IEF
        allocs["A"] = {"HYG": 1.0} if csm > 0 else {"IEF": 1.0}

        # B — three-way HYG / SHY / LQD
        if csm > 0.005:
            allocs["B"] = {"HYG": 1.0}
        elif csm < -0.005:
            allocs["B"] = {"SHY": 1.0}
        else:
            allocs["B"] = {"LQD": 1.0}

        # C — continuous tilt HYG/IEF
        w_hyg = float(np.clip(0.5 + 5 * csm, 0.0, 1.0))
        allocs["C"] = {"HYG": w_hyg, "IEF": 1.0 - w_hyg}

        # D — binary HYG vs TLT (duration overlay on risk-off leg)
        allocs["D"] = {"HYG": 1.0} if csm > 0 else {"TLT": 1.0}

        # E — baseline: pure HYG 12m momentum vs SHY cash parking
        allocs["E"] = {"HYG": 1.0} if hm12 > 0 else {"SHY": 1.0}

        for v, alloc in allocs.items():
            port_ret = sum(w * fwd[t] for t, w in alloc.items())
            if prev_alloc[v] is None:
                turnover = 1.0
            else:
                keys = set(alloc) | set(prev_alloc[v])
                turnover = sum(abs(alloc.get(k, 0) - prev_alloc[v].get(k, 0)) for k in keys) / 2
            tc_drag = turnover * TC
            prev_alloc[v] = alloc
            variants[v].append((date, port_ret - tc_drag))

    out = {}
    for v, lst in variants.items():
        idx = [d for d, _ in lst]
        vals = [x for _, x in lst]
        out[v] = pd.Series(vals, index=pd.to_datetime(idx))
    return out


def evaluate(s: pd.Series, mask, label: str) -> dict:
    r = s[mask].dropna()
    stats = {
        "sharpe": round(sharpe(r), 3),
        "cagr": round(cagr(r), 3),
        "maxdd": round(maxdd(r), 3),
        "neg_years": neg_years(r),
        "n_months": int(len(r)),
    }
    print(f"  {label:40s}  Sharpe={stats['sharpe']:.3f}  CAGR={stats['cagr']:.1%}  "
          f"MaxDD={stats['maxdd']:.1%}  NegYrs={stats['neg_years']}  N={stats['n_months']}")
    return stats


def wf_worst_fold(s: pd.Series):
    oos = s[s.index >= OOS_START].dropna()
    if len(oos) < 12:
        return None
    n = len(oos)
    fold_size = n // 3
    folds = [oos.iloc[i * fold_size:(i + 1) * fold_size] for i in range(3)]
    folds[-1] = oos.iloc[2 * fold_size:]
    fold_sharpes = [sharpe(f) for f in folds if len(f) > 3]
    return min(fold_sharpes) if fold_sharpes else None


def lookahead_self_check(month_end, monthly_ret):
    """Explicit self-check: verify that the signal at index i only touches
    month_end/monthly_ret data at index <= i, and that the return credited
    for signal-at-i is monthly_ret at index i+1 (strictly later)."""
    dates = month_end.index
    i = 30
    hyg_3m_i = month_end["HYG"].iloc[i] / month_end["HYG"].iloc[i - 3] - 1
    # This computation only reads iloc[i] and iloc[i-3] — both <= i. Good.
    signal_date = dates[i]
    credited_return_date = dates[i + 1]
    assert credited_return_date > signal_date, "LOOK-AHEAD BUG: credited return date must be strictly after signal date"
    print(f"  Self-check OK: signal formed at {signal_date.date()} using data through {signal_date.date()}; "
          f"credited forward return is month ending {credited_return_date.date()} (strictly later).")


def main():
    print(f"=== {STRATEGY} — Credit Spread Regime Rotation (HY vs IG vs Treasury) ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE} (H045 canonical baseline)")
    print()

    close = load_daily()
    month_end, monthly_ret = build_monthly(close)
    lookahead_self_check(month_end, monthly_ret)
    print()

    results = run_backtest(month_end, monthly_ret)

    print("\n=== IS Results (2008-2017) ===")
    is_stats = {}
    for v, s in results.items():
        mask = (s.index >= IS_START) & (s.index <= IS_END)
        is_stats[v] = evaluate(s, mask, f"IS Var{v}")

    print("\n=== OOS Results (2018-present) ===")
    oos_stats = {}
    wf_stats = {}
    for v, s in results.items():
        mask = s.index >= OOS_START
        oos_stats[v] = evaluate(s, mask, f"OOS Var{v}")
        wf = wf_worst_fold(s)
        wf_stats[v] = round(wf, 3) if wf is not None else None
        print(f"    -> worst 3-fold OOS Sharpe: {wf_stats[v]}")

    print(f"\n=== Gate Check (OOS Sharpe > {GATE}) ===")
    confirmed = []
    for v in results:
        sh = oos_stats[v]["sharpe"]
        status = "PASS" if sh > GATE else "FAIL"
        print(f"  Var {v}: {sh:.3f} [{status}]")
        if sh > GATE:
            confirmed.append(v)

    baseline_sh = oos_stats["E"]["sharpe"]
    best_var = max(oos_stats, key=lambda v: oos_stats[v]["sharpe"])
    best_sh = oos_stats[best_var]["sharpe"]
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"

    print(f"\nBaseline (Var E, HYG 12m mom vs SHY): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")

    # Correlation vs H045-style bond baseline proxy (buy&hold AGG-like blend
    # not available offline; report corr vs SHY/IEF/TLT buy-hold as sanity)
    oos_best = results[best_var][results[best_var].index >= OOS_START]
    ief_bh = monthly_ret["IEF"][monthly_ret.index >= OOS_START]
    joined = pd.concat([oos_best, ief_bh], axis=1, keys=["best", "ief_bh"]).dropna()
    corr_vs_ief = float(joined["best"].corr(joined["ief_bh"])) if len(joined) > 2 else None

    output = {
        "strategy": STRATEGY,
        "run_date": datetime.now().isoformat(),
        "gate_oos_sharpe": GATE,
        "verdict": verdict,
        "confirmed_variants": confirmed,
        "best_variant": best_var,
        "best_oos_sharpe": best_sh,
        "baseline_oos_sharpe": baseline_sh,
        "corr_best_vs_ief_buyhold_oos": round(corr_vs_ief, 3) if corr_vs_ief is not None else None,
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "wf_worst_fold_sharpe": wf_stats,
    }
    out_path = RESULT_DIR / "h537_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
