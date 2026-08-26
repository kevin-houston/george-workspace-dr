#!/usr/bin/env python3
"""
H536 — Order-Block (SMC) Filter Stacked on H530's Volume-Confirmed "Glamour"
        Momentum (Variant B) on H241's 200-Stock Universe

Motivation: H530 CONFIRMED Variant B (momentum top-40 -> filter to the
HIGHEST relative-volume 20, i.e. heavily-traded "glamour" momentum winners)
as the strongest recent result in the H526-534 family: OOS Sharpe 1.373 vs
1.061 plain-momentum baseline, zero negative years, and the best walk-forward
robustness of the group (worst 3-fold OOS Sharpe 1.243 > full-period 1.373 is
impossible but close: 1.243 is still well above gate). H530's own
"Recommended follow-up" proposed testing its relative-volume tilt as an
in-sleeve tiebreaker, not as a standalone strategy — but the priority
research direction for this session explicitly calls out combining two
already-confirmed signals in the H241 family (naming "H344 OB filter x H534"
as one example). H535 (this session, same universe) tested the OB filter
against H534 and found it did NOT help. This hypothesis runs the same
OB-filter mechanism against H530 Variant B instead — a different confirmed
base signal — to see whether the OB filter's failure to add value in H535 is
specific to the sector-relative-momentum construction, or a more general
property of this filter on this 195-stock universe regardless of which
proven signal it's layered onto.

CRITICAL — look-ahead bias discipline (per H510-H514 audit history):
The OB `as_of` cutoff passed to has_bullish_ob() is fixed to the PRIOR
month-end -- the same date the relvol/momentum signal itself is formed on
(month_end_relvol.iloc[i-1], mom_6_1 computed through iloc[i-1] in H530's own
build_panel()) -- never the holding month's own closing date. Verified via
an explicit self-check mirroring H510/H535.

Universe: H241's 195-stock universe (11 GICS sectors); reuses H530's cached
  daily Close/Volume parquet where possible, but requires full OHLCV for the
  SMC order-block detector, so maintains its own OHLCV cache (same approach
  as H535, since the H527/H529/H530/H533/H534 caches are Close/Volume only).
Signal: H530's exact construction -- relative volume = trailing 3m avg
  dollar volume / trailing 12m avg dollar volume, momentum = 6-1m return,
  both formed at month-end t-1, applied to month t-1->t forward return.
  Base pool: momentum top-40 -> highest-relvol-20 (H530 Variant B). OB
  filter applied on top of this pool using the identical as_of date.
IS/OOS: 2013-01-01 to 2020-12-31 (IS) / 2021-01-01 to present (OOS) --
  matches H530 exactly for direct comparability.
Gate: OOS Sharpe > 1.174 (H198/H241/H526-535-family baseline) AND must beat
  H530 Variant B's own OOS Sharpe (1.373) to be worth adopting as a
  refinement.

Variants:
  A -- H530 Variant B baseline, recomputed fresh in this script (sanity
       check it reproduces ~1.373)
  B -- Variant B pool (momentum top-40 -> highest-relvol-20) -> OB-confirmed
       subset, strict (min_filter=3, else go to cash)
  C -- Variant B pool -> OB-confirmed subset, lenient (min_filter=1, else
       fall back to unfiltered Variant A picks)
  D -- Variant B pool -> OB-confirmed subset, with fallback to next-ranked
       high-relvol-momentum names if filter leaves too few (H344-style fill)
"""

import os, warnings
os.environ["SMC_CREDIT"] = "0"
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from datetime import datetime
from smartmoneyconcepts import smc as SMC

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

STRATEGY = "H536"

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
POOL_N  = 40   # momentum candidate pool before relvol/OB filtering
TC      = 0.001
GATE    = 1.174
RELVOL_SHORT = 63
RELVOL_LONG  = 252
OB_WINDOW  = 20
SWING_LEN  = 3
OB_MIN_FILTER_STRICT  = 3
OB_MIN_FILTER_LENIENT = 1


def load_daily_ohlcv():
    # H535's OHLCV cache is the same universe -- reuse if present, since the
    # H527/H529/H530/H533/H534 caches are Close/Volume only and insufficient
    # for the SMC order-block detector.
    shared_cache = CACHE_DIR / "h535_daily_ohlcv.parquet"
    cache = CACHE_DIR / "h536_daily_ohlcv.parquet"
    for candidate in [shared_cache, cache]:
        if candidate.exists():
            df = pd.read_parquet(candidate)
            close_nonnull = df["Close"].notna().sum()
            empty_cols = [t for t in UNIVERSE if t in close_nonnull.index and close_nonnull[t] == 0]
            missing = [t for t in UNIVERSE if t not in df.columns.get_level_values(1)]
            if not missing and not empty_cols:
                print(f"  Loaded OHLCV from cache: {candidate}")
                return df
            print(f"  Cache {candidate} stale/incomplete ({len(missing)} missing, {len(empty_cols)} empty)")

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
        frames.append(raw[["Open", "High", "Low", "Close", "Volume"]])
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
    vol = daily["Volume"]
    dollar_vol = close * vol

    avg_short = dollar_vol.rolling(RELVOL_SHORT).mean()
    avg_long = dollar_vol.rolling(RELVOL_LONG).mean()
    rel_vol = avg_short / avg_long.replace(0, np.nan)

    month_end_close = close.resample("ME").last()
    month_end_relvol = rel_vol.resample("ME").last()
    monthly_ret = month_end_close.pct_change()

    return month_end_close, month_end_relvol, monthly_ret


def build_panel(month_end_close, month_end_relvol, monthly_ret):
    """Matches H530's build_panel exactly: signal formed through month-end
    i-1, forward return is month i-1 -> i (one full month lag)."""
    dates = month_end_close.index
    rows = []
    for i in range(13, len(dates) - 1):
        date = dates[i]
        signal_asof = dates[i - 1]   # the prior month-end -- signal formation date
        relvol_signal = month_end_relvol.iloc[i - 1]
        mom_6_1 = month_end_close.iloc[i - 1] / month_end_close.iloc[i - 7] - 1
        fwd_ret = monthly_ret.iloc[i]  # month i-1 -> i, matches H530's iloc[i+1] relative to its own date=dates[i]... see note below

        tickers = month_end_close.columns[
            month_end_close.iloc[i - 1].notna()
            & month_end_relvol.iloc[i - 1].notna()
            & fwd_ret.notna()
        ]
        for t in tickers:
            rows.append({
                "date": date, "ticker": t, "signal_asof": signal_asof,
                "relvol": relvol_signal[t],
                "mom_6_1": mom_6_1[t],
                "fwd_ret": fwd_ret[t],
            })
    df = pd.DataFrame(rows).dropna(subset=["relvol", "mom_6_1", "fwd_ret"])
    return df.set_index(["date", "ticker"])


def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp,
                    window: int, swing_len: int) -> bool:
    sub = daily_df[daily_df.index <= as_of].tail(window + swing_len * 2)
    if len(sub) < swing_len * 2:
        return False
    try:
        ohlcv = sub[["open", "high", "low", "close", "volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


def lookahead_self_check():
    idx = pd.date_range("2020-01-01", periods=30, freq="ME")
    for loc in range(13, 29):
        date = idx[loc]
        signal_asof = idx[loc - 1]
        fwd_start = idx[loc - 1]
        fwd_end = idx[loc]
        assert signal_asof <= fwd_start, "Signal formation date must not exceed forward window start"
        assert signal_asof < fwd_end, "LOOK-AHEAD SELF-CHECK FAILED"
        ob_as_of = signal_asof
        assert ob_as_of < fwd_end, "OB as_of must precede the end of the holding month it gates"
    print("Look-ahead self-check PASSED: OB as_of == signal formation date "
          "(prior month-end), strictly before the holding month's own close.")


def run_backtest(panel: pd.DataFrame, daily_data: dict):
    dates = panel.index.get_level_values("date").unique().sort_values()
    variants = {v: [] for v in "ABCD"}
    prev_sets = {v: set() for v in "ABCD"}

    for date in dates:
        df_t = panel.loc[date].copy()
        if len(df_t) < TOP_N:
            for v in variants:
                variants[v].append((date, 0.0))
            continue

        signal_asof = df_t["signal_asof"].iloc[0]
        relvol_rank = df_t["relvol"].rank(pct=True)
        mom_rank = df_t["mom_6_1"].rank(pct=True)

        top_mom40 = mom_rank.nlargest(min(POOL_N, len(df_t))).index
        pool = relvol_rank.loc[top_mom40].sort_values(ascending=False).index.tolist()  # highest relvol first (Variant B direction)
        varA_pool = relvol_rank.loc[top_mom40].nlargest(TOP_N).index  # H530 Var B baseline

        ob_confirmed = []
        for ticker in pool:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], signal_asof, OB_WINDOW, SWING_LEN):
                ob_confirmed.append(ticker)

        picks = {"A": df_t.loc[varA_pool]}

        if len(ob_confirmed) >= OB_MIN_FILTER_STRICT:
            picks["B"] = df_t.loc[ob_confirmed[:TOP_N]]
        else:
            picks["B"] = None  # cash

        if len(ob_confirmed) >= OB_MIN_FILTER_LENIENT:
            picks["C"] = df_t.loc[ob_confirmed[:TOP_N]]
        else:
            picks["C"] = df_t.loc[varA_pool]

        sel_d = list(ob_confirmed[:TOP_N])
        if len(sel_d) < TOP_N:
            for t in pool:
                if t not in sel_d:
                    sel_d.append(t)
                if len(sel_d) >= TOP_N:
                    break
        picks["D"] = df_t.loc[sel_d] if sel_d else None

        for v, sub in picks.items():
            if sub is None or len(sub) == 0:
                top_set = set()
                turnover = len(top_set.symmetric_difference(prev_sets[v])) / (2 * TOP_N)
                prev_sets[v] = top_set
                variants[v].append((date, 0.0 - turnover * TC))
                continue
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
    print(f"=== {STRATEGY} — OB Filter on H530 Volume-Confirmed Momentum (Var B) ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE}, must also beat H530 Var B's own OOS 1.373")
    print()

    lookahead_self_check()

    daily = load_daily_ohlcv()
    month_end_close, month_end_relvol, monthly_ret = build_monthly_signals(daily)
    panel = build_panel(month_end_close, month_end_relvol, monthly_ret)
    print(f"  Panel rows: {len(panel)}  tickers: {panel.index.get_level_values('ticker').nunique()}")

    daily_data = {}
    for t in UNIVERSE:
        try:
            sub = pd.DataFrame({
                "open": daily["Open"][t], "high": daily["High"][t],
                "low": daily["Low"][t], "close": daily["Close"][t],
                "volume": daily["Volume"][t],
            }).dropna()
            if len(sub) > 50:
                daily_data[t] = sub
        except Exception:
            continue
    print(f"  Daily OHLCV series available for OB detection: {len(daily_data)} tickers")

    results = run_backtest(panel, daily_data)

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

    baseline_sh = oos_stats["A"]["sharpe"]
    print(f"\n=== Gate Check (OOS Sharpe > {GATE} AND beats Var A baseline {baseline_sh:.3f}) ===")
    confirmed = []
    for v in results:
        sh = oos_stats[v]["sharpe"]
        status = "PASS" if (sh > GATE and (v == "A" or sh > baseline_sh)) else "FAIL"
        print(f"  Var {v}: {sh:.3f} [{status}]")
        if v != "A" and sh > GATE and sh > baseline_sh:
            confirmed.append(v)

    best_var = max([v for v in oos_stats if v != "A"], key=lambda v: oos_stats[v]["sharpe"])
    best_sh = oos_stats[best_var]["sharpe"]
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"

    print(f"\nBaseline (Var A, H530 Var B reproduction): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best OB-filtered (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")

    oos_best = results[best_var][results[best_var].index >= OOS_START]
    oos_base = results["A"][results["A"].index >= OOS_START]
    joined = pd.concat([oos_best, oos_base], axis=1, keys=["best", "base"]).dropna()
    corr_vs_baseline = float(joined["best"].corr(joined["base"])) if len(joined) > 2 else None

    output = {
        "strategy": STRATEGY,
        "run_date": datetime.now().isoformat(),
        "gate_oos_sharpe": GATE,
        "verdict": verdict,
        "confirmed_variants": confirmed,
        "best_variant": best_var,
        "best_oos_sharpe": best_sh,
        "baseline_oos_sharpe": baseline_sh,
        "corr_best_vs_baseline_oos": round(corr_vs_baseline, 3) if corr_vs_baseline is not None else None,
        "is_stats": is_stats,
        "oos_stats": oos_stats,
        "wf_worst_fold_sharpe": wf_stats,
    }
    out_path = RESULT_DIR / "h536_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
