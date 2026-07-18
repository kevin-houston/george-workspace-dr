"""
H411: Pure Reversal vs Pure Value vs Optimal Blend — all gated by 20d Drift Regime
====================================================================================
H409 Var D confirmed OOS Sharpe 4.550 using 0.70*pct_rank(1/price) + 0.30*pct_rank(-zscore(ret_10d))
gated by 20d drift regime (>60% positive days).

H411 diagnostic: decompose which component drives H409's alpha.
  A: Pure reversal only: pct_rank(-zscore(ret_10d)) * drift_20d
  B: Pure value only: pct_rank(1/price) * drift_20d
  C: 50/50 blend: (0.5*rev + 0.5*val) * drift_20d
  D: H409 Var D replication (0.70 val + 0.30 rev) * drift_20d  [sanity check]
  E: Pure reversal NO gate [diagnostic: is gating still essential for reversal alone?]
  F: 5d reversal instead of 10d, gated 20d [shorter lookback]
  G: 21d reversal gated 20d [monthly reversal instead of 2-week]

Gate: OOS Sharpe > 4.068 (H398A champion)
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
GATE_SHARPE     = 4.068
DRIFT_THRESHOLD = 0.60


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h409_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
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
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h409", "h398", "h395", "h393", "h198"]:
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


def backtest(monthly_px, signal, top_n=2, gated=False):
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna()
        pool = scores[scores > 1e-6] if gated else scores
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(top_n, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def reversal_signal(daily_px, monthly_px, window):
    r_raw = daily_px.pct_change(window).resample("ME").last()
    r_raw = r_raw.reindex(monthly_px.index, method="ffill")
    std = r_raw.std(axis=1).replace(0, np.nan)
    zsc = r_raw.sub(r_raw.mean(axis=1), axis=0).div(std, axis=0)
    return (-zsc).rank(axis=1, pct=True)


def main():
    print("H411 — Pure Reversal vs Pure Value vs Blends — 20d Drift Gate")
    print("=" * 70)
    print(f"Source: Diagnostic extension of H409 | Gate: OOS Sharpe > {GATE_SHARPE}")

    print("\nLoading prices (reusing H409 daily cache)…")
    daily_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_daily(t)] if s is not None]
    ).T.sort_index()
    monthly_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_monthly(t)] if s is not None]
    ).T.sort_index().loc[DATA_START:]
    print(f"  {len(daily_px.columns)} tickers, {len(daily_px)} daily / {len(monthly_px)} monthly obs")

    print("Computing drift regime (20d)…")
    daily_ret = daily_px.pct_change()
    pos_20 = (daily_ret > 0).rolling(20).sum()
    d20 = (pos_20 / 20) > DRIFT_THRESHOLD
    d20_mly = d20.resample("ME").last().astype(float)
    d20_mly = d20_mly.reindex(monthly_px.index, method="ffill")
    gate_mask = d20_mly.gt(0.5).astype(float)

    print("Computing factor signals…")
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    rev_10 = reversal_signal(daily_px, monthly_px, 10)
    rev_5  = reversal_signal(daily_px, monthly_px, 5)
    rev_21 = reversal_signal(daily_px, monthly_px, 21)

    signals = {
        "A": rev_10 * gate_mask,                             # pure reversal 10d gated
        "B": rank_value * gate_mask,                         # pure value gated
        "C": (0.50 * rev_10 + 0.50 * rank_value) * gate_mask,  # 50/50 gated
        "D": (0.30 * rev_10 + 0.70 * rank_value) * gate_mask,  # H409 replication
        "E": rev_10,                                          # pure reversal, no gate
        "F": rev_5 * gate_mask,                              # 5d reversal gated
        "G": rev_21 * gate_mask,                             # 21d reversal gated
    }
    descs = {
        "A": "Pure reversal 10d, 20d drift gate",
        "B": "Pure value (1/P), 20d drift gate",
        "C": "50/50 rev+val, 20d drift gate",
        "D": "H409 Var D replication (0.70val+0.30rev), 20d gate",
        "E": "Pure reversal 10d, NO gate [diagnostic]",
        "F": "5d reversal, 20d drift gate",
        "G": "21d reversal, 20d drift gate",
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 115)

    results = {}
    confirmed = []
    variant_rets = {}

    for v, sig in signals.items():
        rets = backtest(monthly_px, sig, top_n=2, gated=True)
        variant_rets[v] = rets
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS GATE" if beat else ""
        print(f"Var {v}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {descs[v]}{flag}")
        results[f"var_{v}"] = {"is": vi, "oos": vo, "desc": descs[v], "beats": beat}
        if beat:
            confirmed.append(v)

    best_v = max(signals, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    print(f"\n=== Var {best_v} annual returns ===")
    ann = variant_rets[best_v].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        best_c = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
        print(f"Champion: Var {best_c}  OOS Sharpe {results[f'var_{best_c}']['oos']['sharpe']:.3f}")
    else:
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best_v}  OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H411",
        "gate": GATE_SHARPE,
        "confirmed": bool(confirmed),
        "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h411_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
