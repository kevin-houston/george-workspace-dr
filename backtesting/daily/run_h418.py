"""
H418 — H416 Signal Decomposition: What Actually Drives the Alpha?
==================================================================
H416 Var I uses (1/price rank) × (20d drift gate). Both components could drive alpha:
  Component 1 — 1/price rank: "cheap" stocks (low absolute price) outperform peers
  Component 2 — 20d drift gate: only stocks with >60% positive days in last 20 qualify

This test isolates each component on the canonical H198 30-stock NASDAQ universe.
The answer matters enormously for understanding robustness and the economic mechanism.

Variants:
  A: 1/price rank × drift gate, top-3 [H416-I baseline replication]
  B: 1/price rank ONLY (no gate), top-3   — pure cheap-stock value signal
  C: Drift fraction rank only, top-3      — pure short-term momentum (no price filter)
  D: 12-1m momentum × drift gate, top-3  — replace price rank with momentum
  E: avg(1/price rank, drift rank), top-3 — composite, no binary gate

Gate: OOS Sharpe > 4.825 (H416 Var A / H411 Var B)
IS: 2013-2020   OOS: 2021-2026   Universe: H198 30-stock NASDAQ large-cap
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

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 4.825
TOP_N       = 3


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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h418_{ticker}_daily_{DATA_START}_{DATA_END}.parquet")
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


def main():
    print("H418 — H416 Signal Decomposition: 1/Price vs Drift vs Momentum")
    print("=" * 68)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}   Universe: H198 30-stock NASDAQ   Top-N: {TOP_N}\n")

    print("Loading daily prices (reusing H416/H411 cache)…")
    daily_px_dict = {}
    for t in UNIVERSE:
        s = fetch_daily(t)
        if s is not None:
            daily_px_dict[t] = s

    daily_px = pd.DataFrame(daily_px_dict).sort_index()
    monthly_px = daily_px.resample("ME").last().loc[DATA_START:]
    monthly_index = monthly_px.index
    print(f"  {len(daily_px.columns)} tickers, {len(daily_px)} daily / {len(monthly_px)} monthly obs\n")

    daily_ret  = daily_px.pct_change()

    # --- Signal components ---
    # 1/price rank (high rank = cheapest stock)
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)

    # 20d drift fraction per stock
    drift_frac_20 = (daily_ret > 0).rolling(20).sum() / 20
    drift_frac_mly = drift_frac_20.resample("ME").last()
    drift_frac_mly = drift_frac_mly.reindex(monthly_index, method="ffill").fillna(0)

    # Binary drift gate: >0.60
    drift_gate = (drift_frac_mly > 0.60).astype(float)

    # Drift fraction rank (high rank = most positive days)
    drift_rank = drift_frac_mly.rank(axis=1, pct=True)

    # 12-1m momentum (skip-1 momentum)
    ret_12 = monthly_px.pct_change(12)
    ret_1  = monthly_px.pct_change(1)
    mom_12_1 = (ret_12 - ret_1).rank(axis=1, pct=True)

    # --- Variant signals ---
    signals = {
        "A": rank_value * drift_gate,                                  # H416-I baseline
        "B": rank_value,                                               # 1/price only, no gate
        "C": drift_rank,                                               # drift rank only, no gate
        "D": mom_12_1 * drift_gate,                                    # momentum × drift gate
        "E": ((rank_value + drift_rank) / 2),                         # composite, no gate
    }

    descs = {
        "A": "1/price rank × drift gate [H416-I baseline]",
        "B": "1/price rank ONLY (no gate)",
        "C": "Drift fraction rank ONLY (no price filter)",
        "D": "12-1m momentum rank × drift gate",
        "E": "avg(1/price rank, drift rank), no gate",
    }

    print(f"{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Description")
    print("-" * 110)

    results = {}
    confirmed = []
    variant_rets = {}

    for v in ["A", "B", "C", "D", "E"]:
        sig = signals[v]
        sig_aligned = sig.reindex(monthly_index).fillna(0)
        rets = backtest(monthly_px, sig_aligned, top_n=TOP_N)
        variant_rets[v] = rets
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓" if beat else ""
        print(f"Var {v}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {descs[v]}{flag}")
        results[f"var_{v}"] = {"is": vi, "oos": vo, "desc": descs[v], "beats": beat}
        if beat:
            confirmed.append(v)

    # OOS annual breakdown for A vs B vs C
    for v in ["A", "B", "C"]:
        print(f"\n=== Var {v} OOS annual returns ===")
        ann = variant_rets[v].resample("YE").apply(lambda x: (1+x).prod()-1)
        for yr, ret in ann.items():
            print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        best_c = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
        print(f"Champion: Var {best_c}  OOS {results[f'var_{best_c}']['oos']['sharpe']:.3f}")
        # Interpretation
        if "B" in confirmed and "A" not in confirmed:
            print("  → 1/price rank is the alpha source; drift gate adds noise")
        elif "C" in confirmed and "B" not in confirmed:
            print("  → Drift momentum is the alpha source; 1/price rank is the noise")
        elif "A" in confirmed and "B" not in confirmed and "C" not in confirmed:
            print("  → Interaction of price rank AND drift gate is essential; neither alone works")
        elif "A" in confirmed and "B" in confirmed and "C" not in confirmed:
            print("  → 1/price rank drives alpha; drift gate adds modest improvement")
        elif "A" in confirmed and "C" in confirmed and "B" not in confirmed:
            print("  → Drift momentum drives alpha; 1/price rank adds modest improvement")
    else:
        best_v = max(results, key=lambda k: results[k]["oos"]["sharpe"])
        print(f"NOT CONFIRMED — best {best_v}  OOS {results[best_v]['oos']['sharpe']:.3f} < gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H418",
        "gate": GATE_SHARPE,
        "h416_i_record": 5.342,
        "confirmed": bool(confirmed),
        "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h418_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
