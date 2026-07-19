"""
H416 — Drift Gate Robustness: Alternative Drift Definitions on H411 Value Signal
==================================================================================
H411 Var B confirmed OOS Sharpe 4.825 using pure 1/price rank gated by per-stock
20d positive-day fraction > 0.60. This is the new H-series record.

H416 diagnostic: does the 20d window / 0.60 threshold / per-stock calculation
matter specifically, or do other drift definitions work equally well?

Variants:
  A: 20d drift per-stock > 0.60 [H411 Var B replication — sanity check]
  B: 10d drift per-stock > 0.60 [shorter lookback]
  C: 30d drift per-stock > 0.60 [longer lookback]
  D: 40d drift per-stock > 0.60 [even longer]
  E: 20d drift per-stock > 0.55 [less strict threshold]
  F: 20d drift per-stock > 0.65 [more strict threshold]
  G: SPY 20d positive-day fraction > 0.60 [market-level gate instead of per-stock]
  H: 20d drift per-stock > 0.60 AND SPY > 200d MA [composite gate]
  I: 20d drift per-stock > 0.60, top-3 instead of top-2 [position count sensitivity]

Gate: OOS Sharpe > 4.825 (H411 Var B champion)
IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock NASDAQ large-cap
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

UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

DATA_START      = "2011-01-01"
DATA_END        = "2026-06-30"
IS_START        = pd.Timestamp("2013-01-01")
IS_END          = pd.Timestamp("2020-12-31")
OOS_START       = pd.Timestamp("2021-01-01")
OOS_END         = pd.Timestamp("2026-06-30")
GATE_SHARPE     = 4.825  # H411 Var B champion


def fetch_daily(ticker: str) -> pd.Series:
    # Reuse H409/H411 cache files
    for prefix in ["h409", "h411", "h398"]:
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
    cp = CACHE_DIR / f"h416_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h409", "h411", "h398", "h395", "h393", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    daily = fetch_daily(ticker)
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
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean()*12), 3),
            "neg_yrs": neg_years(r)}


def backtest(monthly_px, signal, top_n=2):
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna()
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


def compute_drift_mask(daily_ret: pd.DataFrame, monthly_index: pd.DatetimeIndex,
                       window: int, threshold: float) -> pd.DataFrame:
    """Per-stock drift gate: fraction of positive days in rolling window > threshold."""
    pos_count = (daily_ret > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


def compute_spy_drift(spy_daily: pd.Series, monthly_index: pd.DatetimeIndex,
                      window: int, threshold: float) -> pd.Series:
    """SPY-level drift gate: fraction of positive SPY days in rolling window."""
    pos_count = (spy_daily > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


def main():
    print("H416 — Drift Gate Robustness: Alternative Drift Definitions")
    print("=" * 70)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H411 Var B champion)")

    print("\nLoading prices (reusing H409/H411 daily cache)…")
    daily_px = pd.DataFrame(
        {t: s for t in UNIVERSE for s in [fetch_daily(t)] if s is not None}
    ).sort_index()
    monthly_px = pd.DataFrame(
        {t: s for t in UNIVERSE for s in [fetch_monthly(t)] if s is not None}
    ).sort_index().loc[DATA_START:]
    print(f"  {len(daily_px.columns)} tickers, {len(daily_px)} daily / {len(monthly_px)} monthly obs")

    # Load SPY for SPY-level gate
    spy_cp = CACHE_DIR / f"h413_daily_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_df = pd.read_parquet(spy_cp)
        spy_daily = spy_df["SPY"].pct_change() if "SPY" in spy_df.columns else None
        spy_px = spy_df["SPY"] if "SPY" in spy_df.columns else None
    else:
        spy_cp2 = CACHE_DIR / f"h416_SPY_daily_{DATA_START}_{DATA_END}.parquet"
        if spy_cp2.exists():
            spy_px = pd.read_parquet(spy_cp2).squeeze()
        else:
            raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
            spy_px = raw["Close"].squeeze()
            pd.DataFrame(spy_px).to_parquet(spy_cp2)
        spy_daily = spy_px.pct_change()

    spy_ma200 = spy_px.rolling(200).mean()
    spy_abv_200 = (spy_px > spy_ma200).resample("ME").last().astype(float)
    spy_abv_200 = spy_abv_200.reindex(monthly_px.index, method="ffill").fillna(0)

    daily_ret = daily_px.pct_change()
    monthly_index = monthly_px.index

    print("Computing value signal (1/price rank)…")
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)

    print("Computing drift gate variants…")
    gates = {}
    gates["A"] = compute_drift_mask(daily_ret, monthly_index, 20, 0.60)  # H411 baseline
    gates["B"] = compute_drift_mask(daily_ret, monthly_index, 10, 0.60)
    gates["C"] = compute_drift_mask(daily_ret, monthly_index, 30, 0.60)
    gates["D"] = compute_drift_mask(daily_ret, monthly_index, 40, 0.60)
    gates["E"] = compute_drift_mask(daily_ret, monthly_index, 20, 0.55)
    gates["F"] = compute_drift_mask(daily_ret, monthly_index, 20, 0.65)

    # SPY-level gate: all stocks get gate=1 or gate=0 based on SPY drift
    spy_drift_20 = compute_spy_drift(spy_daily, monthly_index, 20, 0.60)
    spy_gate_df = pd.DataFrame(
        {t: spy_drift_20 for t in monthly_px.columns}, index=monthly_index
    )
    gates["G"] = spy_gate_df

    # Composite: per-stock 20d + SPY > 200MA
    spy_abv_df = pd.DataFrame(
        {t: spy_abv_200 for t in monthly_px.columns}, index=monthly_index
    )
    gates["H"] = (gates["A"] > 0.5) & (spy_abv_df > 0.5)
    gates["H"] = gates["H"].astype(float)

    # Var I: same as A but top-3
    gates["I"] = gates["A"].copy()

    variant_specs = [
        ("A", "A", 2, "20d drift/stock > 0.60, top-2 [H411 Var B replication]"),
        ("B", "B", 2, "10d drift/stock > 0.60, top-2"),
        ("C", "C", 2, "30d drift/stock > 0.60, top-2"),
        ("D", "D", 2, "40d drift/stock > 0.60, top-2"),
        ("E", "E", 2, "20d drift/stock > 0.55, top-2 [less strict]"),
        ("F", "F", 2, "20d drift/stock > 0.65, top-2 [more strict]"),
        ("G", "G", 2, "SPY 20d drift > 0.60 (market-level gate), top-2"),
        ("H", "H", 2, "20d drift/stock > 0.60 AND SPY > 200d MA, top-2"),
        ("I", "I", 3, "20d drift/stock > 0.60, top-3"),
    ]

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 120)

    results = {}
    confirmed = []
    variant_rets = {}

    for v, gate_key, top_n, desc in variant_specs:
        sig = rank_value * gates[gate_key]
        rets = backtest(monthly_px, sig, top_n=top_n)
        variant_rets[v] = rets
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ NEW RECORD" if beat else ""
        print(f"Var {v}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {desc}{flag}")
        results[f"var_{v}"] = {"is": vi, "oos": vo, "desc": desc, "top_n": top_n,
                                "beats": beat}
        if beat:
            confirmed.append(v)

    best_v = max(results, key=lambda k: results[k]["oos"]["sharpe"])
    print(f"\n=== Var {best_v.split('_')[-1]} OOS annual returns ===")
    bv = best_v.split("_")[-1]
    ann = variant_rets[bv].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (H411 Var B)")
    if confirmed:
        best_c = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
        print(f"Champion: Var {best_c}  OOS {results[f'var_{best_c}']['oos']['sharpe']:.3f}")
    else:
        bsh = results[best_v]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best {best_v}  OOS {bsh:.3f} < gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H416",
        "gate": GATE_SHARPE,
        "h411_baseline": 4.825,
        "confirmed": bool(confirmed),
        "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h416_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
