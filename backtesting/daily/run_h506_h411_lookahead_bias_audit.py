"""
H506 — Look-Ahead Bias Audit of the H411/H416/H417/H418 "1/Price x Drift Gate"
             Family (drift-gated value signal)
=================================================================================
While attempting a follow-up to H492/H493 (apply unskipped 12-0 momentum to the
H417 combined-60 drift-gated signal, staged as H505), replicating H417's own
run_h417.py did NOT reproduce its logged OOS Sharpe 5.855 for Var C. Instead it
reproduced the number from run_h417_corrected.py (OOS Sharpe 0.383) — a
materially different, much weaker result. Diffing the two files showed the only
change is `signal.shift(1)` added before `backtest()` in the "_corrected"
variant. The hypothesis log's H417 entry cites the UNSHIFTED numbers (5.855,
5.328, 5.352) even though a "_corrected" script already exists in the repo
alongside it — the corrected version was apparently written but never used to
update the log entry, and the earlier H411/H416/H418 hypotheses that share the
same backtest() helper were never checked at all.

The bug: `backtest()` in this family does `signal.loc[month_end]` (a rank/gate
computed FROM monthly_px.loc[month_end], i.e. that month's own closing price)
to select which names receive `monthly_ret.iloc[loc]` — the return from the
PREVIOUS month-end to THIS month-end. The signal is available only at the
instant the return has already been fully realized. This is look-ahead bias:
in live trading you cannot know a stock is "cheap at month-end M" and buy it
to capture the return that already happened by month-end M.

This hypothesis systematically re-runs H411 (the "best OOS Sharpe in H-series
history" record, 4.825) with `.shift(1)` applied to every signal, exactly as
H416_corrected/H417_corrected already did for their own families, to quantify
the true magnitude of the bias and establish the corrected baseline number
that any future H411/H416/H417/H418-family follow-up (H505 and beyond) must
be gated against.

Universe: H198 30-stock NASDAQ (identical to original H411)
IS: 2013-2020   OOS: 2021-2026
Gate: N/A — this is a diagnostic/audit hypothesis, not a signal search.
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
        if month_end not in signal.index:
            port_rets.append((month_end, 0.0))
            continue
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
    print("H506 — Look-Ahead Bias Audit: H411 'value x drift gate' family, shift(1) corrected")
    print("=" * 90)

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
        "A": rev_10 * gate_mask,
        "B": rank_value * gate_mask,
        "C": (0.50 * rev_10 + 0.50 * rank_value) * gate_mask,
        "D": (0.30 * rev_10 + 0.70 * rank_value) * gate_mask,
        "E": rev_10,
        "F": rev_5 * gate_mask,
        "G": rev_21 * gate_mask,
    }
    descs = {
        "A": "Pure reversal 10d, 20d drift gate",
        "B": "Pure value (1/P), 20d drift gate  [H411 ORIGINAL CHAMPION]",
        "C": "50/50 rev+val, 20d drift gate",
        "D": "H409 Var D replication (0.70val+0.30rev), 20d gate",
        "E": "Pure reversal 10d, NO gate [diagnostic]",
        "F": "5d reversal, 20d drift gate",
        "G": "21d reversal, 20d drift gate",
    }

    print(f"\n{'Var':<4} {'--- ORIGINAL (unshifted) ---':<28} {'--- CORRECTED (shift(1)) ---':<28}  Desc")
    print(f"{'':4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9}   {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9}")
    print("-" * 115)

    results = {}
    for v, sig in signals.items():
        # Original (unshifted, replicates the logged H411 numbers)
        rets_orig = backtest(monthly_px, sig, top_n=2, gated=True)
        vi_o = eval_period(rets_orig, IS_START, IS_END)
        vo_o = eval_period(rets_orig, OOS_START, OOS_END)

        # Corrected (shift(1) — signal known only at start of the return month)
        rets_corr = backtest(monthly_px, sig.shift(1), top_n=2, gated=True)
        vi_c = eval_period(rets_corr, IS_START, IS_END)
        vo_c = eval_period(rets_corr, OOS_START, OOS_END)

        print(f"{v:<4} {vi_o['sharpe']:>7.3f} {vo_o['sharpe']:>8.3f} {vo_o['maxdd']:>9.1%}   "
              f"{vi_c['sharpe']:>7.3f} {vo_c['sharpe']:>8.3f} {vo_c['maxdd']:>9.1%}  {descs[v]}")

        results[v] = {
            "desc": descs[v],
            "original_unshifted": {"is": vi_o, "oos": vo_o},
            "corrected_shift1":   {"is": vi_c, "oos": vo_c},
        }

    best_corr = max(results, key=lambda k: results[k]["corrected_shift1"]["oos"]["sharpe"])
    print(f"\nBest CORRECTED variant: {best_corr} — OOS Sharpe {results[best_corr]['corrected_shift1']['oos']['sharpe']:.3f}")
    print(f"(Original logged H411 champion was Var B, OOS Sharpe 4.825 — this is the number to retract)")

    print("\n=== Verdict ===")
    print("CONFIRMED BUG: H411's backtest() (and the identical helper reused by H416,")
    print("H417, H418) selects names using signal.loc[month_end] where the signal")
    print("(1/price rank, drift gate fraction) is computed from monthly_px.loc[month_end]")
    print("— the SAME month-end close used to compute monthly_ret.loc[month_end], the")
    print("return already realized getting TO that close. This is look-ahead bias:")
    print("the strategy 'knows' a stock is cheap/trending at the close of the very month")
    print("whose return it is being awarded. Applying signal.shift(1) (already present in")
    print("run_h416_corrected.py and run_h417_corrected.py but never applied to H411/H418")
    print("and never used to update the hypothesis log) collapses Var B OOS Sharpe from")
    print(f"4.825 to {results['B']['corrected_shift1']['oos']['sharpe']:.3f} — the entire H411 record result was a look-ahead-bias artifact.")

    out = {
        "hypothesis": "H506",
        "type": "look_ahead_bias_audit",
        "affected_hypotheses": ["H411", "H416", "H417", "H418"],
        "root_cause": "backtest() indexes signal.loc[month_end] without shift(1); "
                       "signal computed from monthly_px.loc[month_end] which is the "
                       "same close used to compute the return being awarded that month.",
        "h411_var_b_original_oos_sharpe": results["B"]["original_unshifted"]["oos"]["sharpe"],
        "h411_var_b_corrected_oos_sharpe": results["B"]["corrected_shift1"]["oos"]["sharpe"],
        "results": results,
    }
    op = RESULT_DIR / "h506_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {op}")
    return out


if __name__ == "__main__":
    main()
