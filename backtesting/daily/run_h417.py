"""
H417 — H416 Signal: Universe Sensitivity Test
==============================================
H416 Var I confirmed OOS Sharpe 5.342 on a 30-stock NASDAQ large-cap universe.
Critical question: is the 1/price × drift signal NASDAQ-specific, or does it
generalize to broader / sector-different universes?

Variants:
  A: H198 30-stock NASDAQ large-cap [H416-I replication, sanity check]
  B: 30-stock S&P 500 non-tech (consumer / healthcare / industrials / financials / energy)
  C: 60-stock combined (A ∪ B)

Gate: OOS Sharpe > 4.825 (H416 Var A / H411 Var B — generalization threshold,
      not the H416 record, to give non-NASDAQ variants a fair test)
IS: 2013-2020   OOS: 2021-2026
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

NASDAQ_30 = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

SP500_NTECH = [
    # Consumer Staples
    "PG",  "KO",   "PEP",  "MO",   "PM",
    # Healthcare (non-H198)
    "MRK", "AMGN", "GILD", "MDT",  "BMY",
    # Industrials
    "HON", "MMM",  "RTX",  "UPS",  "DE",
    # Financials
    "GS",  "MS",   "BLK",  "AXP",  "USB",
    # Energy
    "COP", "SLB",  "EOG",  "VLO",  "PSX",
    # Consumer Discretionary (non-Amazon)
    "MCD", "NKE",  "TGT",  "F",    "GM",
]

COMBINED_60 = NASDAQ_30 + SP500_NTECH

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 4.825  # H416 Var A / H411 Var B — generalization threshold

TOP_N       = 3      # H416 Var I champion used top-3


def fetch_daily(ticker: str) -> pd.Series:
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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h417_{ticker}_daily_{DATA_START}_{DATA_END}.parquet")
    return s


def fetch_monthly(ticker: str, daily: pd.Series) -> pd.Series:
    s = daily.resample("ME").last()
    s.name = ticker
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


def compute_drift_mask(daily_ret: pd.DataFrame, monthly_index, window=20, threshold=0.60):
    pos_count = (daily_ret > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


def backtest(monthly_px, signal, top_n=3):
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


def run_universe(label, universe, daily_cache):
    tickers = [t for t in universe if t in daily_cache]
    daily_px = pd.DataFrame({t: daily_cache[t] for t in tickers}).sort_index()
    monthly_px = pd.DataFrame({t: fetch_monthly(t, daily_cache[t]) for t in tickers}).sort_index().loc[DATA_START:]
    monthly_index = monthly_px.index

    daily_ret = daily_px.pct_change()
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    drift_mask = compute_drift_mask(daily_ret, monthly_index)
    signal = rank_value * drift_mask
    rets = backtest(monthly_px, signal, top_n=TOP_N)
    return rets, len(tickers)


def main():
    print("H417 — H416 Signal: Universe Sensitivity Test")
    print("=" * 65)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}  (H416 Var A / H411 Var B generalization threshold)")
    print(f"Signal: 1/price rank × 20d drift gate (>0.60), top-{TOP_N}\n")

    all_tickers = list(set(COMBINED_60))
    print(f"Loading daily prices for {len(all_tickers)} tickers…")
    daily_cache = {}
    for t in all_tickers:
        try:
            s = fetch_daily(t)
            if s is not None and len(s) > 100:
                daily_cache[t] = s
        except Exception as e:
            print(f"  WARNING: {t} failed — {e}")
    print(f"  Loaded {len(daily_cache)} tickers\n")

    variant_specs = [
        ("A", NASDAQ_30,   "H198 30-stock NASDAQ [H416-I replication]"),
        ("B", SP500_NTECH, "30-stock S&P 500 non-tech"),
        ("C", COMBINED_60, "60-stock combined (NASDAQ + non-tech)"),
    ]

    print(f"{'Var':<4} {'N':>4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Universe")
    print("-" * 110)

    results = {}
    confirmed = []
    variant_rets = {}

    for v, universe, desc in variant_specs:
        rets, n_tickers = run_universe(v, universe, daily_cache)
        variant_rets[v] = rets
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓" if beat else ""
        print(f"Var {v}  {n_tickers:>4d} {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {desc}{flag}")
        results[f"var_{v}"] = {"is": vi, "oos": vo, "desc": desc,
                                "n_tickers": n_tickers, "beats": beat}
        if beat:
            confirmed.append(v)

    # Annual breakdown for Var A (replication check)
    print(f"\n=== Var A OOS annual returns (replication check) ===")
    ann = variant_rets["A"].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    # Annual breakdown for Var B (non-tech)
    print(f"\n=== Var B OOS annual returns (non-tech S&P 500) ===")
    ann = variant_rets["B"].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
    else:
        best_v = max(results, key=lambda k: results[k]["oos"]["sharpe"])
        print(f"NOT CONFIRMED — best {best_v}  OOS {results[best_v]['oos']['sharpe']:.3f} < gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H417",
        "gate": GATE_SHARPE,
        "h416_record": 5.342,
        "signal": "1/price rank × 20d drift gate (>0.60), top-3",
        "confirmed": bool(confirmed),
        "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h417_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
