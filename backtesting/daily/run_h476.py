"""
H476 — OB Filter on H417 60-Stock Combined Universe
=====================================================
H417 Var C achieved OOS Sharpe 5.855 (H-series record) on the 60-stock combined
universe using 1/price rank × 20d drift gate, top-3 selection.

Key question: can the SMC Order Block filter (from H344, which improved H198
from 1.174 → 3.396) push Sharpe higher or reduce MaxDD below -1.2% on the
already-strong H417 signal?

Approach: same signal as H417 Var C, but stocks must show a bullish unmitigated
order block before being selected each month. OB is applied to the top-6
signal candidates; if <min_filter have OB confirmation, go to cash.

Gate: OOS Sharpe > 5.855 (H417 Var C) AND MaxDD improvement >= 0.2pp
IS: 2013-2020   OOS: 2021-2026
"""

import warnings
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

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 5.855   # H417 Var C champion
BASELINE_MDD = -0.012  # H417 Var C MaxDD

TOP_N        = 3
CANDIDATE_N  = 6      # screen top-6 by signal before OB check

# focused grid (best single-param from H344: window=20, swing=3)
OB_WINDOWS  = [20, 30]
MIN_FILTERS = [2, 3]
SWING_LENS  = [3, 5]


# ── Data loaders ─────────────────────────────────────────────────────────────

def fetch_close(ticker: str) -> pd.Series:
    for prefix in ["h409", "h411", "h416", "h398", "h417"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h476_{ticker}_close_{DATA_START}_{DATA_END}.parquet")
    return s


def fetch_ohlcv(ticker: str) -> pd.DataFrame:
    for prefix in ["h343", "h344", "h476"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily.parquet"
        if cp.exists():
            return pd.read_parquet(cp)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.to_parquet(CACHE_DIR / f"h476_{ticker}_daily.parquet")
    return df


# ── Signal (H417 Var C) ───────────────────────────────────────────────────────

def compute_drift_mask(daily_ret: pd.DataFrame, monthly_index, window=20, threshold=0.60):
    pos_count = (daily_ret > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


# ── OB filter ────────────────────────────────────────────────────────────────

def has_bullish_ob(ohlcv_df: pd.DataFrame, as_of: pd.Timestamp,
                   window: int, swing_len: int) -> bool:
    sub = ohlcv_df[ohlcv_df.index <= as_of].tail(window + swing_len * 2)
    if len(sub) < swing_len * 2:
        return False
    try:
        ohlcv = sub[["open","high","low","close","volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
        bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
        return len(bull) > 0
    except Exception:
        return False


# ── Backtest engines ──────────────────────────────────────────────────────────

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


def run_baseline(monthly_px, signal):
    """H417 Var C baseline — no OB filter."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna() if month_end in signal.index else pd.Series(dtype=float)
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(TOP_N, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def run_ob_backtest(monthly_px, signal, ohlcv_cache,
                    ob_window, min_filter, swing_len):
    """H417 signal + OB confirmation on top candidates."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []

    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna() if month_end in signal.index else pd.Series(dtype=float)
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue

        # Screen top-CANDIDATE_N by signal score
        candidates = pool.nlargest(min(CANDIDATE_N, len(pool))).index.tolist()

        # OB confirmation pass
        ob_confirmed = []
        for ticker in candidates:
            if ticker not in ohlcv_cache:
                continue
            if has_bullish_ob(ohlcv_cache[ticker], month_end, ob_window, swing_len):
                ob_confirmed.append(ticker)
            if len(ob_confirmed) >= TOP_N:
                break

        if len(ob_confirmed) < min_filter:
            port_rets.append((month_end, 0.0))  # go to cash
            continue

        selected = ob_confirmed[:TOP_N]
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H476 — OB Filter on H417 60-Stock Combined Universe")
    print("=" * 65)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H417 Var C) AND MaxDD improvement")
    print(f"Signal: 1/price rank × 20d drift gate (>0.60), top-{TOP_N}\n")

    tickers = list(set(COMBINED_60))
    print(f"Loading close prices for {len(tickers)} tickers…")
    close_cache = {}
    for t in tickers:
        try:
            s = fetch_close(t)
            if s is not None and len(s) > 100:
                close_cache[t] = s
        except Exception as e:
            print(f"  WARNING: {t} close failed — {e}")
    print(f"  Loaded close for {len(close_cache)} tickers")

    print(f"Loading daily OHLCV for {len(tickers)} tickers…")
    ohlcv_cache = {}
    for t in tickers:
        try:
            df = fetch_ohlcv(t)
            if df is not None and len(df) > 100:
                ohlcv_cache[t] = df
        except Exception as e:
            print(f"  WARNING: {t} ohlcv failed — {e}")
    print(f"  Loaded OHLCV for {len(ohlcv_cache)} tickers\n")

    # Build monthly price frame and H417 signal
    avail = [t for t in COMBINED_60 if t in close_cache]
    daily_px  = pd.DataFrame({t: close_cache[t] for t in avail}).sort_index()
    monthly_px = daily_px.resample("ME").last().loc[DATA_START:]
    monthly_index = monthly_px.index

    daily_ret  = daily_px.pct_change()
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    drift_mask = compute_drift_mask(daily_ret, monthly_index)
    signal     = rank_value * drift_mask

    # Baseline (H417 Var C replication)
    print("Running baseline (H417 Var C)…")
    base_rets = run_baseline(monthly_px, signal.shift(1))
    b_is  = eval_period(base_rets, IS_START, IS_END)
    b_oos = eval_period(base_rets, OOS_START, OOS_END)
    print(f"  Baseline  IS={b_is['sharpe']:.3f}  OOS={b_oos['sharpe']:.3f}  MDD={b_oos['maxdd']:.1%}\n")

    # OB grid search
    print(f"{'Win':>5} {'MF':>4} {'SL':>4} | {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'NegY':>5}  {'Cash%':>7}")
    print("-" * 70)

    grid_results = {}
    best_oos = 0.0
    best_params = None

    for ob_window in OB_WINDOWS:
        for min_filter in MIN_FILTERS:
            for swing_len in SWING_LENS:
                rets = run_ob_backtest(monthly_px, signal.shift(1), ohlcv_cache,
                                       ob_window, min_filter, swing_len)
                vi  = eval_period(rets, IS_START, IS_END)
                vo  = eval_period(rets, OOS_START, OOS_END)
                cash_months = (rets == 0.0).sum()
                cash_pct    = cash_months / len(rets) * 100 if len(rets) > 0 else 0.0
                beat = vo["sharpe"] > GATE_SHARPE
                flag = " ✓" if beat else ""
                print(f"{ob_window:>5} {min_filter:>4} {swing_len:>4} | "
                      f"{vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
                      f"{vo['neg_yrs']:>5d}  {cash_pct:>6.1f}%{flag}")
                key = f"w{ob_window}_mf{min_filter}_sl{swing_len}"
                grid_results[key] = {"is": vi, "oos": vo, "cash_pct": round(cash_pct,1), "beats": beat}
                if vo["sharpe"] > best_oos:
                    best_oos = vo["sharpe"]
                    best_params = key

    # OOS annual breakdown for best param combo
    if best_params:
        w, mf, sl = [int(x.split("w")[-1].split("_")[0] if "w" in x else 0)
                     for x in [best_params.split("_")[0],
                                best_params.split("_")[1],
                                best_params.split("_")[2]]]
        # parse properly
        parts = best_params.split("_")
        w  = int(parts[0][1:])
        mf = int(parts[1][2:])
        sl = int(parts[2][2:])
        best_rets = run_ob_backtest(monthly_px, signal.shift(1), ohlcv_cache, w, mf, sl)
        print(f"\n=== Best params ({best_params}) OOS annual returns ===")
        ann = best_rets.resample("YE").apply(lambda x: (1+x).prod()-1)
        for yr, ret in ann.items():
            print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    confirmed = [k for k, v in grid_results.items() if v["beats"]]
    print(f"\n=== Verdict ===")
    print(f"Baseline OOS Sharpe: {b_oos['sharpe']:.3f}  MDD: {b_oos['maxdd']:.1%}")
    print(f"Best OB OOS Sharpe:  {best_oos:.3f}  (params: {best_params})")
    if confirmed:
        print(f"CONFIRMED — {len(confirmed)} param combos beat gate {GATE_SHARPE}")
    else:
        print(f"NOT CONFIRMED — best OOS {best_oos:.3f} < gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H476",
        "gate": GATE_SHARPE,
        "baseline_oos": b_oos,
        "best_ob_oos": best_oos,
        "best_params": best_params,
        "confirmed": bool(confirmed),
        "confirmed_combos": confirmed,
        "grid": grid_results,
    }
    op = RESULT_DIR / "h476_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
