#!/usr/bin/env python3
"""
H529 — MAX Effect (Lottery-Demand Anomaly) Retested on H241's 200-Stock Universe

Motivation: H373 tested the Bali, Cakici & Whitelaw (2011) MAX effect / Tandfonline
2025 MAX x momentum interaction on H198's 30-stock concentrated mega-cap universe
and found it purely dilutive (NOT CONFIRMED) — its own write-up attributed the
failure to insufficient cross-sectional MAX heterogeneity within a homogeneous
30-name tech-heavy universe (MAX rank and momentum rank were highly correlated,
both selecting the same volatile growth names). This closes the same "retest at
200-stock scale" gap that H487 (idiosyncratic vol) and H527 (illiquidity) already
closed for their respective families — H241's 195-stock, 11-GICS-sector universe
spans defensive/low-vol names (KO, PG, DUK) alongside genuine lottery-ticket
candidates (small biotech-adjacent, energy E&P, semis), giving MAX real
cross-sectional spread that a 30-stock mega-cap sample lacks.

Universe: H241's 195-stock universe (11 GICS sectors) — reuses H527's cached
  daily Close/Volume parquet (same UNIVERSE, same date range).
Signal: MAX = max single-day return over the trailing 21 trading days (Bali et
  al. 2011's definition), computed strictly through month-end t-1, applied to
  month t+1 forward return (one full month of separation between signal date
  and the return being credited — see build_panel()).
IS: 2013-01-01 to 2020-12-31 / OOS: 2021-01-01 to present.
Gate: OOS Sharpe > 1.174 (H198/H241-family baseline, consistent with H526/H527/H528).

Variants:
  A — pure MAX top-20 (lottery-demand overpricing predicts UNDERperformance —
      sanity direction; academic finding is that high-MAX stocks underperform)
  B — pure low-MAX top-20 (long the LEAST lottery-like names — the anomaly's
      actual "long" leg per Bali et al. 2011's negative MAX-return relation)
  C — MAX x momentum dual rank (0.5 rank(mom_6_1) + 0.5 rank(-MAX)), i.e.
      momentum tilted toward low-MAX names within the momentum set
  D — momentum top-40 -> filter to lowest-MAX 20 (lottery-avoidance overlay
      on momentum, mirrors H527 Var D's liquidity-tilt construction)
  E — baseline: plain 6-1m momentum top-20 (H241-A style, no MAX filter)
  F — pure MAX top-20 momentum-direction sanity check: high-MAX, same as A
      (kept distinct from A only for symmetry with H527's lettering; A and F
      are identical by construction and used to confirm no signal-inversion bug)
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

STRATEGY = "H529"

UNIVERSE = [
    "AAPL","MSFT","NVDA","AVGO","AMD","QCOM","ORCL","CRM","ADBE","INTC",
    "TXN","ACN","IBM","AMAT","LRCX","MU","NOW","INTU","ADI","NXPI",
    "MCHP","KLAC","CDNS","SNPS","FTNT","GLW","HPE","KEYS","ZBRA","JNPR",
    "AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","F","GM",
    "CMG","BKNG","ROST","DRI","DHI","LEN","PHM","NVR","TOL","EXPE",
    "JPM","BAC","WFC","GS","MS","C","BLK","AXP","CB","PGR",
    "MET","PRU","TRV","ICE","CME","SCHW","USB","PNC","TFC","SPGI",
    "MCO","COF","DFS","AIG","MMC",
    "UNH","LLY","JNJ","ABBV","MRK","PFE","TMO","ABT","AMGN","GILD",
    "MDT","BMY","ISRG","CVS","CI","HUM","ELV","REGN","VRTX","ZBH",
    "BDX","BSX","EW","DXCM","HOLX",
    "WMT","COST","PG","KO","PEP","PM","MO","MDLZ","CL","GIS",
    "K","CPB","HRL","SJM","CAG",
    "XOM","CVX","COP","EOG","PSX","VLO","MPC","SLB","HAL",
    "OXY","HES","APA","DVN","FANG","KMI",
    "HON","UPS","RTX","LMT","CAT","GE","NOC","BA","DE","EMR",
    "ETN","ITW","CTAS","WM","RSG","CSX","NSC","UNP","FDX","MMM",
    "LIN","APD","SHW","ECL","NEM","FCX","NUE","ALB","CF","MOS",
    "PLD","AMT","EQIX","CCI","SPG","O","DLR","EXR","AVB","EQR",
    "NEE","DUK","SO","D","AEP","EXC","PCG","SRE","XEL","PPL",
    "GOOGL","META","NFLX","DIS","CMCSA","VZ","T","TMUS","CHTR","FOXA",
    "EA","TTWO","OMC","IPG","LDOS",
]
seen = set()
UNIVERSE = [t for t in UNIVERSE if not (t in seen or seen.add(t))]

DATA_START = "2011-06-01"
DATA_END   = "2026-08-20"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")

TOP_N   = 20
TC      = 0.001
GATE    = 1.174
MAX_WIN = 21  # trailing trading days for MAX statistic (Bali et al. 2011)


def load_daily():
    # Reuse H527's cache: same UNIVERSE, same date range, Close+Volume columns.
    shared_cache = CACHE_DIR / "h527_daily_close_volume.parquet"
    cache = CACHE_DIR / "h529_daily_close_volume.parquet"
    if shared_cache.exists() and not cache.exists():
        print(f"  Reusing H527 cache: {shared_cache}")
        df = pd.read_parquet(shared_cache)
        close_nonnull = df["Close"].notna().sum()
        empty_cols = [t for t in UNIVERSE if t in close_nonnull.index and close_nonnull[t] == 0]
        missing = [t for t in UNIVERSE if t not in df.columns.get_level_values(1)]
        if not missing and not empty_cols:
            return df
        print(f"  Shared cache stale/incomplete ({len(missing)} missing, {len(empty_cols)} empty) — falling through to fresh download")
    if cache.exists():
        df = pd.read_parquet(cache)
        close_nonnull = df["Close"].notna().sum()
        empty_cols = [t for t in UNIVERSE if t in close_nonnull.index and close_nonnull[t] == 0]
        missing = [t for t in UNIVERSE if t not in df.columns.get_level_values(1)]
        if not missing and not empty_cols:
            print(f"  Loaded from cache: {df.shape}")
            return df
        print(f"  Cache stale/incomplete ({len(missing)} missing, {len(empty_cols)} empty) — re-downloading")

    all_tickers = list(UNIVERSE)
    frames = []
    remaining = set(all_tickers)
    for attempt in range(4):
        if not remaining:
            break
        batch = sorted(remaining)
        print(f"  Downloading {len(batch)} tickers daily OHLCV (attempt {attempt+1})…")
        raw = yf.download(batch, start=DATA_START, end=DATA_END,
                           auto_adjust=True, progress=False, threads=False)
        if isinstance(raw.columns, pd.MultiIndex):
            got = raw["Close"].notna().sum()
            ok = set(got[got > 0].index)
        else:
            ok = set(batch) if raw["Close"].notna().sum() > 0 else set()
        frames.append(raw[["Close", "Volume"]])
        remaining -= ok
        if remaining:
            print(f"    still missing after attempt {attempt+1}: {sorted(remaining)}")

    df = frames[0]
    for f in frames[1:]:
        df = df.combine_first(f)
        for col in f.columns:
            if col in df.columns:
                df[col] = f[col].combine_first(df[col])

    still_empty = [t for t in UNIVERSE if t not in df["Close"].columns or df["Close"][t].notna().sum() == 0]
    if still_empty:
        print(f"  WARNING: {len(still_empty)} tickers have no data after retries: {sorted(still_empty)}")

    df.to_parquet(cache)
    return df


def build_monthly_signals(daily: pd.DataFrame):
    close = daily["Close"]
    ret = close.pct_change()

    max_21d = ret.rolling(MAX_WIN).max()

    month_end_close = close.resample("ME").last()
    month_end_max = max_21d.resample("ME").last()
    monthly_ret = month_end_close.pct_change()

    return month_end_close, month_end_max, monthly_ret


def build_panel(month_end_close, month_end_max, monthly_ret):
    dates = month_end_close.index
    rows = []
    for i in range(13, len(dates) - 1):
        date = dates[i]
        max_signal = month_end_max.iloc[i - 1]
        mom_6_1 = month_end_close.iloc[i - 1] / month_end_close.iloc[i - 7] - 1
        fwd_ret = monthly_ret.iloc[i + 1]

        tickers = month_end_close.columns[
            month_end_close.iloc[i - 1].notna()
            & month_end_max.iloc[i - 1].notna()
            & fwd_ret.notna()
        ]
        for t in tickers:
            rows.append({
                "date": date, "ticker": t,
                "max_stat": max_signal[t],
                "mom_6_1": mom_6_1[t],
                "fwd_ret": fwd_ret[t],
            })
    df = pd.DataFrame(rows).dropna(subset=["max_stat", "mom_6_1", "fwd_ret"])
    return df.set_index(["date", "ticker"])


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


def run_backtest(panel: pd.DataFrame):
    dates = panel.index.get_level_values("date").unique().sort_values()
    variants = {v: [] for v in "ABCDEF"}
    prev_sets = {v: set() for v in "ABCDEF"}

    for date in dates:
        df_t = panel.loc[date].copy()
        if len(df_t) < TOP_N:
            for v in variants:
                variants[v].append((date, 0.0))
            continue

        max_rank = df_t["max_stat"].rank(pct=True)   # high rank = high MAX (lottery-like)
        mom_rank = df_t["mom_6_1"].rank(pct=True)

        picks = {
            "A": df_t.loc[max_rank.nlargest(TOP_N).index],        # high MAX (lottery)
            "B": df_t.loc[max_rank.nsmallest(TOP_N).index],       # low MAX (anti-lottery long leg)
            "E": df_t.loc[mom_rank.nlargest(TOP_N).index],        # baseline momentum
            "F": df_t.loc[max_rank.nlargest(TOP_N).index],        # identical to A, inversion sanity check
        }

        composite = 0.5 * mom_rank + 0.5 * (1 - max_rank)
        picks["C"] = df_t.loc[composite.nlargest(TOP_N).index]

        top_mom40 = mom_rank.nlargest(min(40, len(df_t))).index
        sub_lowmax = max_rank.loc[top_mom40].nsmallest(TOP_N).index
        picks["D"] = df_t.loc[sub_lowmax]

        for v, sub in picks.items():
            top_set = set(sub.index)
            turnover = len(top_set.symmetric_difference(prev_sets[v])) / (2 * TOP_N)
            tc_drag = turnover * TC
            prev_sets[v] = top_set
            r = sub["fwd_ret"].mean() - tc_drag
            variants[v].append((date, r))

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
    }
    print(f"  {label:40s}  Sharpe={stats['sharpe']:.3f}  CAGR={stats['cagr']:.1%}  "
          f"MaxDD={stats['maxdd']:.1%}  NegYrs={stats['neg_years']}")
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


def main():
    print(f"=== {STRATEGY} — MAX Effect (Lottery-Demand Anomaly) on H241 Universe ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE} (H198/H241/H527-family baseline)")
    print()

    daily = load_daily()
    month_end_close, month_end_max, monthly_ret = build_monthly_signals(daily)
    panel = build_panel(month_end_close, month_end_max, monthly_ret)
    print(f"  Panel rows: {len(panel)}  tickers: {panel.index.get_level_values('ticker').nunique()}")

    results = run_backtest(panel)

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

    print(f"\nBaseline (Var E, momentum): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")

    output = {
        "strategy": STRATEGY,
        "run_date": datetime.now().isoformat(),
        "gate_oos_sharpe": GATE,
        "verdict": verdict,
        "confirmed_variants": confirmed,
        "best_variant": best_var,
        "best_oos_sharpe": best_sh,
        "baseline_oos_sharpe": baseline_sh,
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "wf_worst_fold_sharpe": wf_stats,
    }
    out_path = RESULT_DIR / "h529_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
