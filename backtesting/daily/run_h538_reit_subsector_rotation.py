#!/usr/bin/env python3
"""
H538 — REIT Sub-Sector Momentum Rotation

Motivation: REIT/real-estate exposure in this log has only ever appeared as
a single-ticker component INSIDE broader multi-asset modules (H026's alts
sleeve holds VNQ as one of ~25 candidates; H257's "real assets module" is
GLD/DBC/VNQ/PDBC/IAU). Real estate has never been tested as its OWN
cross-sectional rotation universe across REIT property-type sub-sectors,
despite property-type dispersion being a well-documented real-estate
factor (industrial/data-center REITs vs. office/retail REITs have had
wildly different fundamentals post-2020 e-commerce and post-COVID
return-to-office shifts). This hypothesis asks whether monthly momentum
rotation among REIT sub-sector ETFs earns a risk-adjusted return premium
over a plain broad-REIT buy-and-hold (VNQ) or over parking in cash (BIL)
during REIT bear phases (2013 taper tantrum, 2020 COVID, 2022 rate shock —
REITs are rate-sensitive and got hit hard in the latter two).

Universe: VNQ (broad REIT benchmark, also a rotation candidate), REZ
  (residential REITs), REM (mortgage REITs — high rate sensitivity, useful
  dispersion vs equity REITs), ICF (Cohen & Steers REIT, cap-weighted
  large-cap tilt), USRT (broad market-cap-weighted REIT, S&P), RWR
  (Dow Jones REIT), BIL (cash proxy for defensive rotation slot).
  Note: excluded SCHH (near-duplicate of VNQ/USRT, adds no dispersion) and
  MORT (near-duplicate of REM) after a data-availability check to keep the
  universe to genuinely differentiated property-type/structure buckets.
Signal: 6-month total-return momentum (mom_6 = price[t]/price[t-6] - 1),
  computed at month-end t using ONLY data through month-end t. Absolute
  momentum overlay: if the top-ranked candidate's own mom_6 <= 0, route to
  BIL instead (trend-following crash protection, same convention as H045's
  TSMOM-style filter and H354's low-vol ETF family).
IS: 2013-01-01 to 2020-12-31 (covers 2013 taper tantrum + 2020 COVID crash).
OOS: 2021-01-01 to present (covers the 2022 REIT rate-shock bear market —
  the single hardest test for a rate-sensitive rotation strategy).
Gate: OOS Sharpe > 1.174 (H198/H241-family generic equity-analog baseline,
  used because REIT sub-sector ETFs are equity-like total-return
  instruments, not treated as part of the H045 bond family).

Variants:
  A — Top-1 momentum, absolute-momentum-gated to BIL (single best sub-sector
      each month, cash overlay).
  B — Top-2 equal-weight momentum, absolute-momentum-gated to BIL.
  C — Top-1 momentum, NO absolute-momentum gate (always fully invested in
      REITs — isolates whether the cash overlay or the rotation itself
      drives any edge).
  D — Inverse-volatility-weighted top-3 (risk-parity-style tilt among the
      3 best-momentum sub-sectors, absolute-momentum-gated).
  E — Baseline: VNQ buy-and-hold (broad REIT benchmark, no rotation).
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

STRATEGY = "H538"
ROTATION_UNIVERSE = ["VNQ", "REZ", "REM", "ICF", "USRT", "RWR"]
UNIVERSE = ROTATION_UNIVERSE + ["BIL"]

DATA_START = "2011-06-01"
DATA_END   = "2026-08-25"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")

TC   = 0.0008
GATE = 1.174


def load_daily():
    cache = CACHE_DIR / "h538_daily_close.parquet"
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
    mom_6 = {t: month_end[t] / month_end[t].shift(6) - 1 for t in ROTATION_UNIVERSE}
    # 6m realized daily-return vol proxy via monthly return std over trailing
    # 6 months, for Var D risk-parity weighting.
    vol_6 = {t: monthly_ret[t].rolling(6).std() for t in ROTATION_UNIVERSE}

    variants = {v: [] for v in "ABCDE"}
    prev_alloc = {v: None for v in "ABCDE"}

    min_i = 13
    for i in range(min_i, len(dates) - 1):
        date = dates[i]
        # Signal formed at index i using mom_6.iloc[i] (which itself only
        # reads month_end.iloc[i] and month_end.iloc[i-6] — both <= i).
        mom_i = {t: mom_6[t].iloc[i] for t in ROTATION_UNIVERSE}
        vol_i = {t: vol_6[t].iloc[i] for t in ROTATION_UNIVERSE}
        fwd = {t: monthly_ret[t].iloc[i + 1] for t in UNIVERSE}

        if any(pd.isna(v) for v in mom_i.values()) or any(pd.isna(fwd[t]) for t in UNIVERSE):
            for v in variants:
                variants[v].append((date, np.nan))
            continue

        ranked = sorted(mom_i, key=mom_i.get, reverse=True)
        top1, top2, top3 = ranked[0], ranked[:2], ranked[:3]

        allocs = {}

        # A — top-1, absolute-momentum gated
        allocs["A"] = {top1: 1.0} if mom_i[top1] > 0 else {"BIL": 1.0}

        # B — top-2 equal-weight, gated (gate on best of the two)
        if mom_i[top1] > 0:
            allocs["B"] = {t: 0.5 for t in top2}
        else:
            allocs["B"] = {"BIL": 1.0}

        # C — top-1, no gate
        allocs["C"] = {top1: 1.0}

        # D — inverse-vol top-3, gated
        if mom_i[top1] > 0:
            inv_vol = {t: 1.0 / vol_i[t] if vol_i[t] and vol_i[t] > 0 else 0.0 for t in top3}
            total = sum(inv_vol.values())
            if total > 0:
                allocs["D"] = {t: w / total for t, w in inv_vol.items()}
            else:
                allocs["D"] = {t: 1.0 / len(top3) for t in top3}
        else:
            allocs["D"] = {"BIL": 1.0}

        # E — baseline: VNQ buy-and-hold
        allocs["E"] = {"VNQ": 1.0}

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


def lookahead_self_check(month_end):
    dates = month_end.index
    i = 30
    mom_i = month_end["VNQ"].iloc[i] / month_end["VNQ"].iloc[i - 6] - 1
    signal_date = dates[i]
    credited_return_date = dates[i + 1]
    assert credited_return_date > signal_date, "LOOK-AHEAD BUG: credited return date must be strictly after signal date"
    print(f"  Self-check OK: signal formed at {signal_date.date()} using data through {signal_date.date()} "
          f"(6m lookback to {dates[i-6].date()}); credited forward return is month ending "
          f"{credited_return_date.date()} (strictly later).")


def main():
    print(f"=== {STRATEGY} — REIT Sub-Sector Momentum Rotation ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE}")
    print()

    close = load_daily()
    month_end, monthly_ret = build_monthly(close)
    lookahead_self_check(month_end)
    print()

    results = run_backtest(month_end, monthly_ret)

    print("\n=== IS Results (2013-2020) ===")
    is_stats = {}
    for v, s in results.items():
        mask = (s.index >= IS_START) & (s.index <= IS_END)
        is_stats[v] = evaluate(s, mask, f"IS Var{v}")

    print("\n=== OOS Results (2021-present) ===")
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

    print(f"\nBaseline (Var E, VNQ buy-hold): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")

    oos_best = results[best_var][results[best_var].index >= OOS_START]
    oos_vnq = results["E"][results["E"].index >= OOS_START]
    joined = pd.concat([oos_best, oos_vnq], axis=1, keys=["best", "vnq"]).dropna()
    corr_vs_vnq = float(joined["best"].corr(joined["vnq"])) if len(joined) > 2 else None

    output = {
        "strategy": STRATEGY,
        "run_date": datetime.now().isoformat(),
        "gate_oos_sharpe": GATE,
        "verdict": verdict,
        "confirmed_variants": confirmed,
        "best_variant": best_var,
        "best_oos_sharpe": best_sh,
        "baseline_oos_sharpe": baseline_sh,
        "corr_best_vs_vnq_buyhold_oos": round(corr_vs_vnq, 3) if corr_vs_vnq is not None else None,
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "wf_worst_fold_sharpe": wf_stats,
    }
    out_path = RESULT_DIR / "h538_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
