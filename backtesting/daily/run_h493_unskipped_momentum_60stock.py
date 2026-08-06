"""
H493 — Unskipped (12-0) Momentum Generalization: 60-Stock Combined Universe
=============================================================================
Source: follow-up to H492 (CONFIRMED — 12-0 unskipped momentum robustly beats
standard 12-1 skip-month momentum on the H198 30-stock mega-cap tech-tilted
universe, across walk-forward folds, split reversal, and transaction costs).
H492's own key finding #4 flagged that the result "should not be assumed to
generalize... to broader or smaller-cap universes" given the concentrated,
tech-tilted nature of the H198 universe. This hypothesis tests that directly.

Design: Reuse H417's 60-stock combined universe (NASDAQ_30 = H198's 30-stock
set, plus SP500_NTECH = 30 non-tech S&P 500 large caps spanning consumer
staples, healthcare, industrials, financials, energy, and consumer
discretionary). If 12-0 still beats 12-1 pure cross-sectional momentum here
-- a universe deliberately constructed to be sector-diverse and NOT
tech/growth-concentrated -- that's real evidence the H492 finding is a
general large-cap momentum property, not a H198-universe artifact.

Also tests the same 3 sub-universes H417 used (NASDAQ 30 / non-tech 30 /
combined 60) for a within-hypothesis sensitivity check.

Gate: OOS Sharpe > 1.174 (H198 baseline -- the standard cross-family gate
used throughout the momentum family on this data era) for the CONFIRM
threshold on pure momentum performance; secondarily, 12-0 must beat 12-1
on the combined-60 universe to confirm generalization.
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
    "PG",  "KO",   "PEP",  "MO",   "PM",
    "MRK", "AMGN", "GILD", "MDT",  "BMY",
    "HON", "MMM",  "RTX",  "UPS",  "DE",
    "GS",  "MS",   "BLK",  "AXP",  "USB",
    "COP", "SLB",  "EOG",  "VLO",  "PSX",
    "MCD", "NKE",  "TGT",  "F",    "GM",
]

COMBINED_60 = NASDAQ_30 + SP500_NTECH

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

GATE = 1.174


def fetch_price_monthly(ticker: str) -> pd.Series:
    # Check existing monthly caches from the H181-H198 and H491/H492 families first
    for prefix in [f"h{i:03d}" for i in range(181, 199)] + ["h491", "h492"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    # Check H417's daily cache and resample
    daily_cp = CACHE_DIR / f"h417_{ticker}_daily_{DATA_START}_2026-06-30.parquet"
    if daily_cp.exists():
        daily = pd.read_parquet(daily_cp).squeeze()
        monthly = daily.resample("ME").last()
        monthly = monthly.loc[:DATA_END]
        return monthly
    cp = CACHE_DIR / f"h493_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    if len(r) == 0 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1)
    return float(dd.min())


def backtest_fixed_window(prices: pd.DataFrame, lookback: int, skip: int, top_n: int) -> pd.Series:
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        signal_end   = loc - skip
        signal_start = signal_end - lookback
        if signal_start < 0 or signal_end <= signal_start:
            continue
        sig = prices.iloc[signal_end] / prices.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def eval_period(rets: pd.Series, label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 3:
        return {"label": label, "n": len(r), "sharpe": 0.0, "cagr": 0.0, "cumul": 1.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "label":  label,
        "n":      len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def load_universe(tickers):
    prices_list = []
    for t in tickers:
        try:
            s = fetch_price_monthly(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    return prices


def main():
    print("H493 — Unskipped (12-0) Momentum Generalization: 60-Stock Combined Universe")

    universes = {
        "NASDAQ_30 (H198)": NASDAQ_30,
        "SP500_NTECH_30":   SP500_NTECH,
        "COMBINED_60":      COMBINED_60,
    }

    all_results = {}
    header = f"{'Universe':<20} {'TopN':>5} {'Window':>8} {'IS Sharpe':>10} {'OOS Sharpe':>10} {'OOS MaxDD':>10} {'NegYrs':>7}"
    print("\n" + header)
    print("-" * len(header))

    for uname, tickers in universes.items():
        print(f"\nLoading {uname} ({len(tickers)} tickers)…")
        prices = load_universe(tickers)
        n_loaded = len(prices.columns)
        top_n = max(3, round(n_loaded * 0.2))  # top quintile, same convention as H198/H417
        print(f"  {n_loaded} tickers loaded, top_n={top_n}")

        uni_res = {}
        for skip, wlabel in [(1, "12-1"), (0, "12-0")]:
            rets = backtest_fixed_window(prices, lookback=12, skip=skip, top_n=top_n)
            is_  = eval_period(rets, wlabel, IS_START, IS_END)
            oos_ = eval_period(rets, wlabel, OOS_START, OOS_END)
            uni_res[wlabel] = {"is": is_, "oos": oos_, "rets": rets}
            print(f"{uname:<20} {top_n:>5} {wlabel:>8} {is_['sharpe']:>10.3f} "
                  f"{oos_['sharpe']:>10.3f} {oos_['maxdd']:>10.1%} {oos_['neg_yrs']:>7d}")
        all_results[uname] = uni_res

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    print(f"\n{'SPY BH':<20} {'':>5} {'':>8} {'':>10} {spy_oos['sharpe']:>10.3f} {spy_oos['maxdd']:>10.1%} {spy_oos['neg_yrs']:>7d}")

    # Correlation vs SPY for combined-60 12-0
    combined_12_0 = all_results["COMBINED_60"]["12-0"]["rets"]
    common = combined_12_0.index.intersection(spy_ret.index)
    corr_spy = float(combined_12_0.reindex(common).corr(spy_ret.reindex(common)))
    print(f"\nCorr(COMBINED_60 12-0, SPY) full sample: {corr_spy:.3f}")

    # Verdict: does 12-0 beat 12-1 on ALL THREE universes (generalization), and beat gate on combined-60?
    wins = {}
    for uname in universes:
        oos_12_0 = all_results[uname]["12-0"]["oos"]["sharpe"]
        oos_12_1 = all_results[uname]["12-1"]["oos"]["sharpe"]
        wins[uname] = oos_12_0 > oos_12_1
        print(f"{uname}: 12-0 ({oos_12_0:.3f}) {'beats' if wins[uname] else 'LOSES TO'} 12-1 ({oos_12_1:.3f})")

    all_universes_win = all(wins.values())
    combined_oos_12_0 = all_results["COMBINED_60"]["12-0"]["oos"]["sharpe"]
    passes_gate = combined_oos_12_0 > GATE

    if all_universes_win and passes_gate:
        verdict = "CONFIRMED"
    elif wins["COMBINED_60"] and passes_gate:
        verdict = "PARTIAL CONFIRMED"
    else:
        verdict = "NOT CONFIRMED"

    print(f"\n=== Verdict ===")
    print(f"12-0 beats 12-1 on all 3 universes: {all_universes_win}")
    print(f"Combined-60 12-0 OOS Sharpe {combined_oos_12_0:.3f} > gate {GATE}: {passes_gate}")
    print(f"{verdict}")

    out = {
        "hypothesis": "H493",
        "gate": GATE,
        "results": {
            uname: {w: {"is": v["is"], "oos": v["oos"]} for w, v in uni_res.items()}
            for uname, uni_res in all_results.items()
        },
        "spy_oos": spy_oos,
        "corr_combined60_12_0_spy": round(corr_spy, 3),
        "wins_12_0_over_12_1": wins,
        "verdict": verdict,
    }
    outpath = RESULT_DIR / "h493_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
