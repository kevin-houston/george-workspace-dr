#!/usr/bin/env python3
"""
H535 — Order-Block (SMC) Filter Layered on H534's Sector-Relative Momentum
        (Variant B: "industry leaders keep leading") on H241's 200-Stock Universe

Motivation: H534 CONFIRMED (Variant B only) that on the H241 195-stock
universe, longing the industry-relative LEADERS (REV^IN = R_i - R_sector_mean,
long the top-20 by this measure) beats the originally-hypothesized reversal
direction and modestly beats plain 6-1m momentum (OOS Sharpe 1.266 vs 1.061
baseline). H534's own "Recommended follow-up" (c) flagged this signal as
still highly correlated with plain momentum (dual-rank Variant C failed at
OOS 0.979) and worth checking whether an orthogonal confirmation filter adds
value. This hypothesis applies the OB/FVG (order block / fair value gap)
filter mechanism — CONFIRMED across H343 (stock momentum), H344 (grid
sensitivity), H361 (low-vol ETFs) — to H534's Variant B stock pool, following
exactly the same "proven filter x newly confirmed signal" combination pattern
used by H507/H508 (which tested OB filter + regime gate on H448 low-vol) and
directly requested by the priority-direction brief ("H344 OB filter x H534
sector-relative momentum").

CRITICAL — look-ahead bias discipline (per H510-H514 audit history):
The OB `as_of` cutoff passed to has_bullish_ob() MUST be the PRIOR month-end
(the last trading day before the holding month begins), never the holding
month's own closing date. H343/H344's original bug (retroactively found in
H510) was passing `month_end` (the current holding month's own close) as
as_of. This script uses `ob_as_of = prior month-end signal formation date`
throughout — the same date already used to form the REV^IN signal itself,
verified via an explicit self-check (lookahead_self_check) mirroring H510's.

Universe: H241's 195-stock universe (11 GICS sectors), reusing the cached
  daily Close/Volume parquet from H527/H529/H530/H533/H534.
Signal: REV^IN_i(t) = R_i(t) - R_sector_mean(t) at month-end t (H534's exact
  construction), long top-20 (Variant B direction: most outperforming vs
  sector). OB filter: require a bullish order block detected in the daily
  bars up to and including the PRIOR month-end (the same date REV^IN itself
  is formed on — no additional future information used by the filter beyond
  what the signal already uses).
IS/OOS: 2013-01-01 to 2020-12-31 (IS) / 2021-01-01 to present (OOS) — matches
  H534 exactly for direct comparability.
Gate: OOS Sharpe > 1.174 (H198/H241/H526-534-family baseline) AND must beat
  H534 Variant B's own OOS Sharpe (1.266) to be worth adopting as a
  refinement (mirrors H532's "must beat Variant A's own baseline" logic).

Variants:
  A — H534 Variant B baseline, recomputed fresh in this script (sanity check
      it reproduces ~1.266)
  B — Variant B pool (top-40 by REV^IN) -> OB-confirmed subset, strict
      (min_filter=3, else go to cash)
  C — Variant B pool -> OB-confirmed subset, lenient (min_filter=1, else
      fall back to unfiltered top-20)
  D — Variant B pool -> OB-confirmed subset, with fallback to 2nd-tier picks
      (H344-style: fill remaining slots from next-ranked names if filter
      leaves too few)
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

STRATEGY = "H535"

SECTOR_BLOCKS = {
    "Information Technology": [
        "AAPL","MSFT","NVDA","AVGO","AMD","QCOM","ORCL","CRM","ADBE","INTC",
        "TXN","ACN","IBM","AMAT","LRCX","MU","NOW","INTU","ADI","NXPI",
        "MCHP","KLAC","CDNS","SNPS","FTNT","GLW","HPE","KEYS","ZBRA","JNPR",
    ],
    "Consumer Discretionary": [
        "AMZN","TSLA","HD","MCD","NKE","SBUX","LOW","TJX","F","GM",
        "CMG","BKNG","ROST","DRI","DHI","LEN","PHM","NVR","TOL","EXPE",
    ],
    "Financials": [
        "JPM","BAC","WFC","GS","MS","C","BLK","AXP","CB","PGR",
        "MET","PRU","TRV","ICE","CME","SCHW","USB","PNC","TFC","SPGI",
        "MCO","COF","DFS","AIG","MMC",
    ],
    "Health Care": [
        "UNH","LLY","JNJ","ABBV","MRK","PFE","TMO","ABT","AMGN","GILD",
        "MDT","BMY","ISRG","CVS","CI","HUM","ELV","REGN","VRTX","ZBH",
        "BDX","BSX","EW","DXCM","HOLX",
    ],
    "Consumer Staples": [
        "WMT","COST","PG","KO","PEP","PM","MO","MDLZ","CL","GIS",
        "K","CPB","HRL","SJM","CAG",
    ],
    "Energy": [
        "XOM","CVX","COP","EOG","PSX","VLO","MPC","SLB","HAL",
        "OXY","HES","APA","DVN","FANG","KMI",
    ],
    "Industrials": [
        "HON","UPS","RTX","LMT","CAT","GE","NOC","BA","DE","EMR",
        "ETN","ITW","CTAS","WM","RSG","CSX","NSC","UNP","FDX","MMM",
    ],
    "Materials": [
        "LIN","APD","SHW","ECL","NEM","FCX","NUE","ALB","CF","MOS",
    ],
    "Real Estate": [
        "PLD","AMT","EQIX","CCI","SPG","O","DLR","EXR","AVB","EQR",
    ],
    "Utilities": [
        "NEE","DUK","SO","D","AEP","EXC","PCG","SRE","XEL","PPL",
    ],
    "Communication Services": [
        "GOOGL","META","NFLX","DIS","CMCSA","VZ","T","TMUS","CHTR","FOXA",
        "EA","TTWO","OMC","IPG","LDOS",
    ],
}

UNIVERSE_SECTORS = {}
for sector, tickers in SECTOR_BLOCKS.items():
    for t in tickers:
        UNIVERSE_SECTORS[t] = sector
UNIVERSE = list(UNIVERSE_SECTORS.keys())
seen = set()
UNIVERSE = [t for t in UNIVERSE if not (t in seen or seen.add(t))]

DATA_START = "2011-06-01"
DATA_END   = "2026-08-20"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")

TOP_N   = 20
POOL_N  = 40   # candidate pool before OB filtering
TC      = 0.001
GATE    = 1.174
OB_WINDOW  = 20
SWING_LEN  = 3
OB_MIN_FILTER_STRICT  = 3
OB_MIN_FILTER_LENIENT = 1


def load_daily():
    # NOTE: the H527/H529/H530/H533/H534 shared caches only store Close/Volume
    # (no Open/High/Low), which is insufficient for the SMC order-block
    # detector used here (needs full OHLCV). This script maintains its own
    # full-OHLCV cache rather than reusing those Close/Volume-only caches.
    cache = CACHE_DIR / "h535_daily_ohlcv.parquet"
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
    month_end_close = close.resample("ME").last()
    monthly_ret = month_end_close.pct_change()
    return month_end_close, monthly_ret


def build_panel(month_end_close, monthly_ret):
    """Reproduces H534's exact REV^IN construction: signal uses month t's own
    completed return, forward return is month t+1 (one full month lag)."""
    dates = month_end_close.index
    rows = []
    for i in range(13, len(dates) - 1):
        date = dates[i]  # this is the signal formation date == prior month-end
        ret_t = monthly_ret.iloc[i]
        fwd_ret = monthly_ret.iloc[i + 1]

        valid = ret_t.notna()
        sector_means = {}
        for sector, tickers in SECTOR_BLOCKS.items():
            members = [t for t in tickers if t in ret_t.index and valid.get(t, False)]
            if members:
                sector_means[sector] = ret_t[members].mean()

        tickers = month_end_close.columns[ret_t.notna() & fwd_ret.notna()]
        for t in tickers:
            sector = UNIVERSE_SECTORS.get(t)
            smean = sector_means.get(sector)
            if smean is None:
                continue
            rows.append({
                "date": date, "ticker": t,
                "revin": ret_t[t] - smean,
                "fwd_ret": fwd_ret[t],
            })
    df = pd.DataFrame(rows).dropna(subset=["revin", "fwd_ret"])
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
    for loc in range(5, 29):
        signal_date = idx[loc]   # matches build_panel: date = dates[i], the prior month-end
        fwd_date = idx[loc + 1]  # the month whose return is being credited
        assert signal_date < fwd_date, "LOOK-AHEAD SELF-CHECK FAILED"
        # OB as_of must equal the signal formation date, never the fwd/holding month's own close
        ob_as_of = signal_date
        assert ob_as_of < fwd_date, "OB as_of must precede the holding month it gates"
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

        revin_rank = df_t["revin"].rank(pct=True)  # high rank = beat sector peers
        pool = revin_rank.nlargest(min(POOL_N, len(df_t))).index.tolist()  # ranked best-first
        top20 = revin_rank.nlargest(TOP_N).index  # Variant A: H534 Var B baseline, no OB filter

        # OB confirmation over the pool, in rank order, ob_as_of = this signal
        # formation date (the same "date" the REV^IN signal itself uses --
        # no additional future information beyond what the signal already has)
        ob_confirmed = []
        for ticker in pool:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], date, OB_WINDOW, SWING_LEN):
                ob_confirmed.append(ticker)

        picks = {"A": df_t.loc[top20]}

        # B: strict — need >= min_filter confirmed names, else go to cash (return 0)
        if len(ob_confirmed) >= OB_MIN_FILTER_STRICT:
            sel_b = ob_confirmed[:TOP_N]
            picks["B"] = df_t.loc[sel_b]
        else:
            picks["B"] = None  # cash

        # C: lenient — if >=1 confirmed name use them (up to TOP_N), else fall back to unfiltered top20
        if len(ob_confirmed) >= OB_MIN_FILTER_LENIENT:
            sel_c = ob_confirmed[:TOP_N]
            picks["C"] = df_t.loc[sel_c]
        else:
            picks["C"] = df_t.loc[top20]

        # D: fill remaining slots from next-ranked pool names if OB filter leaves <TOP_N
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
    print(f"=== {STRATEGY} — OB Filter on H534 Sector-Relative Momentum (Var B) ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE}, must also beat H534 Var B's own OOS 1.266")
    print()

    lookahead_self_check()

    daily = load_daily()
    month_end_close, monthly_ret = build_monthly_signals(daily)
    panel = build_panel(month_end_close, monthly_ret)
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

    print(f"\nBaseline (Var A, H534 Var B reproduction): OOS Sharpe {baseline_sh:.3f}")
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
    out_path = RESULT_DIR / "h535_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved: {out_path}")


if __name__ == "__main__":
    main()
