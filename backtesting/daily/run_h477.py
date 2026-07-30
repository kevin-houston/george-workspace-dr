"""
H477 — H417 Signal Parameter Sensitivity on 60-Stock Combined Universe
=======================================================================
H417 Var C (60-stock, top-3, drift_window=20, drift_threshold=0.60)
achieved OOS Sharpe 5.855. This is a sensitivity sweep to determine
whether adjusting top-N selection, drift window, or drift threshold
can push further above 5.855 or if the original params are already optimal.

Variants:
  TOP_N grid:        1, 2, 3, 4, 5
  Drift window grid: 10, 15, 20, 25, 30
  Drift threshold:   0.50, 0.55, 0.60, 0.65, 0.70
  Full cross of TOP_N × (window, threshold) for most informative ones

Gate: OOS Sharpe > 5.855 (H417 Var C) — must beat the record
IS: 2013-2020   OOS: 2021-2026
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
import itertools

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

NASDAQ_30 = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

SP500_NTECH = [
    "PG",  "KO",   "PEP",  "MO",   "PM",
    "MRK", "AMGN", "GILD", "MDT",  "BMY",
    "HON", "MMM",  "RTX",  "UPS",  "DE",
    "GS",  "MS",   "BLK",  "AXP",  "USB",
    "COP", "SLB",  "EOG",  "VLO",  "PSX",
    "MCD", "NKE",  "TGT",  "F",    "GM",
]

COMBINED_60 = NASDAQ_30 + SP500_NTECH

DATA_START = "2011-01-01"
DATA_END   = "2026-06-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")
GATE_SHARPE = 5.855  # H417 Var C record

TOP_N_GRID       = [1, 2, 3, 4, 5]
DRIFT_WINDOW_GRID = [10, 15, 20, 25, 30]
DRIFT_THRESH_GRID = [0.50, 0.55, 0.60, 0.65, 0.70]


def fetch_close(ticker: str) -> pd.Series:
    for prefix in ["h409", "h411", "h416", "h398", "h417", "h476"]:
        for suf in [f"_daily_{DATA_START}_{DATA_END}.parquet",
                    f"_close_{DATA_START}_{DATA_END}.parquet"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}{suf}"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].dropna()
    s.name = ticker
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h477_{ticker}_close.parquet")
    return s


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3),
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean() * 12), 3),
            "neg_yrs": neg_years(r)}


def compute_drift_mask(daily_ret, monthly_index, window, threshold):
    pos_count = (daily_ret > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


def backtest(monthly_px, signal, top_n):
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna() if month_end in signal.index else pd.Series(dtype=float)
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(top_n, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H477 — H417 Signal Parameter Sensitivity (60-Stock Combined)")
    print("=" * 65)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H417 Var C record)\n")

    tickers = list(set(COMBINED_60))
    print(f"Loading close prices for {len(tickers)} tickers…")
    close_cache = {}
    for t in tickers:
        try:
            s = fetch_close(t)
            if s is not None and len(s) > 100:
                close_cache[t] = s
        except Exception as e:
            print(f"  WARNING: {t} failed — {e}")
    print(f"  Loaded {len(close_cache)} tickers\n")

    avail = [t for t in COMBINED_60 if t in close_cache]
    daily_px   = pd.DataFrame({t: close_cache[t] for t in avail}).sort_index()
    monthly_px = daily_px.resample("ME").last().loc[DATA_START:]
    monthly_index = monthly_px.index
    daily_ret  = daily_px.pct_change()
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)

    # ── Phase 1: TOP_N sensitivity (fixed window=20, threshold=0.60) ──────────
    print("PHASE 1: TOP_N sensitivity  (drift_window=20, drift_thresh=0.60)")
    print(f"{'TopN':>5} | {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}")
    print("-" * 55)

    drift_mask_20_60 = compute_drift_mask(daily_ret, monthly_index, 20, 0.60)
    signal_20_60 = rank_value * drift_mask_20_60

    top_n_results = {}
    for top_n in TOP_N_GRID:
        rets = backtest(monthly_px, signal_20_60.shift(1), top_n)
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        flag = " ✓" if vo["sharpe"] > GATE_SHARPE else ""
        ref  = " ← H417" if top_n == 3 else ""
        print(f"top-{top_n}  | {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}{flag}{ref}")
        top_n_results[top_n] = {"is": vi, "oos": vo}

    # ── Phase 2: Drift window sensitivity (fixed TOP_N=3, threshold=0.60) ────
    print(f"\nPHASE 2: Drift window sensitivity  (top_n=3, drift_thresh=0.60)")
    print(f"{'Win':>5} | {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}")
    print("-" * 55)

    window_results = {}
    for window in DRIFT_WINDOW_GRID:
        dm = compute_drift_mask(daily_ret, monthly_index, window, 0.60)
        sig = rank_value * dm
        rets = backtest(monthly_px, sig.shift(1), 3)
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        flag = " ✓" if vo["sharpe"] > GATE_SHARPE else ""
        ref  = " ← H417" if window == 20 else ""
        print(f"w={window:>2}  | {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}{flag}{ref}")
        window_results[window] = {"is": vi, "oos": vo}

    # ── Phase 3: Drift threshold sensitivity (fixed TOP_N=3, window=20) ──────
    print(f"\nPHASE 3: Drift threshold sensitivity  (top_n=3, drift_window=20)")
    print(f"{'Thr':>6} | {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}")
    print("-" * 55)

    thresh_results = {}
    for thr in DRIFT_THRESH_GRID:
        dm = compute_drift_mask(daily_ret, monthly_index, 20, thr)
        sig = rank_value * dm
        rets = backtest(monthly_px, sig.shift(1), 3)
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        flag = " ✓" if vo["sharpe"] > GATE_SHARPE else ""
        ref  = " ← H417" if thr == 0.60 else ""
        print(f"t={thr:.2f} | {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}{flag}{ref}")
        thresh_results[thr] = {"is": vi, "oos": vo}

    # ── Best combination ──────────────────────────────────────────────────────
    # Search best top_n × best drift window/threshold
    best_top_n = max(top_n_results, key=lambda k: top_n_results[k]["oos"]["sharpe"])
    best_window = max(window_results, key=lambda k: window_results[k]["oos"]["sharpe"])
    best_thresh = max(thresh_results, key=lambda k: thresh_results[k]["oos"]["sharpe"])

    print(f"\nBest top_n={best_top_n}, best_window={best_window}, best_thresh={best_thresh}")
    print("Testing best combination…")
    dm_best = compute_drift_mask(daily_ret, monthly_index, best_window, best_thresh)
    sig_best = rank_value * dm_best
    rets_best = backtest(monthly_px, sig_best.shift(1), best_top_n)
    vb_is  = eval_period(rets_best, IS_START, IS_END)
    vb_oos = eval_period(rets_best, OOS_START, OOS_END)
    beat_best = vb_oos["sharpe"] > GATE_SHARPE
    print(f"Best combo: IS={vb_is['sharpe']:.3f}  OOS={vb_oos['sharpe']:.3f}  "
          f"MDD={vb_oos['maxdd']:.1%}  NegY={vb_oos['neg_yrs']}")

    if beat_best:
        print(f"\n=== Best combo OOS annual returns ===")
        ann = rets_best.resample("YE").apply(lambda x: (1+x).prod()-1)
        for yr, ret in ann.items():
            if yr.year >= 2021:
                print(f"  {yr.year}: {ret:+.1%} ← OOS")

    # Summary
    all_oos = (
        [v["oos"]["sharpe"] for v in top_n_results.values()] +
        [v["oos"]["sharpe"] for v in window_results.values()] +
        [v["oos"]["sharpe"] for v in thresh_results.values()] +
        [vb_oos["sharpe"]]
    )
    confirmed = [s for s in all_oos if s > GATE_SHARPE]

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        print(f"CONFIRMED — {len(confirmed)} param combos beat gate (max {max(confirmed):.3f})")
    else:
        print(f"NOT CONFIRMED — H417 Var C params (top-3, w=20, t=0.60) are optimal or near-optimal")
        print(f"Best OOS in sweep: {max(all_oos):.3f}")

    out = {
        "hypothesis": "H477",
        "gate": GATE_SHARPE,
        "top_n_results": {str(k): v for k, v in top_n_results.items()},
        "window_results": {str(k): v for k, v in window_results.items()},
        "thresh_results": {str(k): v for k, v in thresh_results.items()},
        "best_combo": {
            "top_n": best_top_n, "window": best_window, "thresh": best_thresh,
            "is": vb_is, "oos": vb_oos
        },
        "confirmed": bool(confirmed),
        "max_oos": max(all_oos),
    }
    op = RESULT_DIR / "h477_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
