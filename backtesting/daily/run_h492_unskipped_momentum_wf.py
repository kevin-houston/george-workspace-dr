"""
H492 — Unskipped (12-0) Momentum Walk-Forward Validation
============================================================
Source: side-effect finding from H491 (Dikhit conditional skip-month test).
H491's Variant B — unconditional 12-0 momentum (12-month lookback with NO
skip month, i.e. plain trailing-12m return, long top quintile) — beat both
the standard 12-1 skip-month baseline and the Dikhit conditional switch by
a wide margin on the H198 30-stock universe (OOS Sharpe 2.479 vs 1.096 and
0.886, IS 2.635, zero negative OOS years). That result was NOT the
hypothesis under test in H491 and needs independent validation before it's
treated as a standing finding, per this log's practice of flagging
opportunistic results for a dedicated follow-up rather than accepting them
inline.

This script runs three checks on the same H198 30-stock universe:
 (1) A rolling walk-forward analysis (5 non-overlapping expanding-then-
     testing folds) of 12-0 vs 12-1, to see if the OOS-beats-IS advantage
     of 12-0 replicates fold-by-fold or is a single-split artifact.
 (2) A split reversal check: swap IS/OOS (train 2021-2026, test 2013-2020)
     to see if the 12-0 > 12-1 advantage holds under the opposite split.
 (3) A transaction-cost sensitivity check, since 12-0 (no skip) has a
     structurally different turnover profile than 12-1: TC = 0, 10, 25, 50 bps
     one-way, since more of the reason a stock enters the top-6 in month t
     under 12-0 (vs 12-1) is transient 1-month performance which could imply
     higher turnover / more churn between winners.

Gate: for CONFIRMED status, require (a) 12-0 beats 12-1 in >= 4/5 walk-
forward folds by OOS Sharpe, (b) the reversed-split test also shows 12-0 >
12-1, and (c) 12-0 remains > gate 1.174 (H198 baseline) net of 25bps
one-way transaction costs.
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

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials", "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",     "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials","IBM":  "Information Technology",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N = 6
GATE  = 1.174


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 199)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h492_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
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


def backtest_fixed_window(prices: pd.DataFrame, lookback: int, skip: int,
                           top_n: int, tc_bps: float = 0.0) -> tuple:
    """Returns (net_returns_series, turnover_series)."""
    monthly_ret = prices.pct_change()
    port_rets = []
    turnovers = []
    prev_selected = set()
    months = monthly_ret.index[monthly_ret.index >= pd.Timestamp("2012-01-01")]
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
        selected = set(sig.nlargest(top_n).index.tolist())
        ret_this = monthly_ret.iloc[loc][list(selected)].mean()
        # turnover = fraction of names changed this month (0 to 1)
        if prev_selected:
            changed = len(selected - prev_selected)
            turnover = changed / top_n
        else:
            turnover = 1.0
        tc_cost = turnover * (tc_bps / 10000.0)
        net_ret = ret_this - tc_cost
        port_rets.append((month_end, net_ret))
        turnovers.append((month_end, turnover))
        prev_selected = selected
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    t = pd.Series({d: r for d, r in turnovers})
    t.index = pd.DatetimeIndex(t.index)
    return s, t


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


def main():
    print("H492 — Unskipped (12-0) Momentum Walk-Forward Validation")
    print("Loading price data…")
    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_price(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers loaded, {len(prices)} months")

    # ---- Check 1: 5-fold walk-forward, 2013-2026, non-overlapping 30-month test folds ----
    print("\n=== Check 1: Walk-forward folds (12-0 vs 12-1, no TC) ===")
    rets_12_0, _ = backtest_fixed_window(prices, lookback=12, skip=0, top_n=TOP_N)
    rets_12_1, _ = backtest_fixed_window(prices, lookback=12, skip=1, top_n=TOP_N)

    full_idx = rets_12_0.index[(rets_12_0.index >= IS_START) & (rets_12_0.index <= OOS_END)]
    n_folds = 5
    fold_bounds = np.array_split(full_idx, n_folds)
    fold_results = []
    wins_12_0 = 0
    for i, fold_idx in enumerate(fold_bounds):
        if len(fold_idx) == 0:
            continue
        start, end = fold_idx[0], fold_idx[-1]
        sh_12_0 = sharpe(rets_12_0[(rets_12_0.index >= start) & (rets_12_0.index <= end)])
        sh_12_1 = sharpe(rets_12_1[(rets_12_1.index >= start) & (rets_12_1.index <= end)])
        win = sh_12_0 > sh_12_1
        wins_12_0 += int(win)
        fold_results.append({
            "fold": i + 1, "start": str(start.date()), "end": str(end.date()),
            "sharpe_12_0": round(sh_12_0, 3), "sharpe_12_1": round(sh_12_1, 3),
            "12_0_wins": win,
        })
        print(f"  Fold {i+1} ({start.date()} to {end.date()}): 12-0={sh_12_0:.3f}  12-1={sh_12_1:.3f}  {'12-0 WINS' if win else '12-1 wins'}")
    print(f"  12-0 wins {wins_12_0}/{len(fold_results)} folds")

    # ---- Check 2: Reversed split (train on 2021-2026, test on 2013-2020) ----
    print("\n=== Check 2: Reversed split (test-period = 2013-2020) ===")
    rev_12_0 = eval_period(rets_12_0, "12-0 rev", IS_START, IS_END)  # "test" now = original IS window
    rev_12_1 = eval_period(rets_12_1, "12-1 rev", IS_START, IS_END)
    fwd_12_0 = eval_period(rets_12_0, "12-0 fwd", OOS_START, OOS_END)
    fwd_12_1 = eval_period(rets_12_1, "12-1 fwd", OOS_START, OOS_END)
    print(f"  Original-IS-as-test-period (2013-2020): 12-0 Sharpe={rev_12_0['sharpe']:.3f}  12-1 Sharpe={rev_12_1['sharpe']:.3f}")
    print(f"  Original-OOS-as-test-period (2021-2026): 12-0 Sharpe={fwd_12_0['sharpe']:.3f}  12-1 Sharpe={fwd_12_1['sharpe']:.3f}")
    reversed_holds = rev_12_0['sharpe'] > rev_12_1['sharpe']
    forward_holds  = fwd_12_0['sharpe'] > fwd_12_1['sharpe']
    print(f"  12-0 > 12-1 in both periods: {reversed_holds and forward_holds}")

    # ---- Check 3: Transaction cost sensitivity ----
    print("\n=== Check 3: Transaction cost sensitivity (OOS 2021-2026) ===")
    tc_results = {}
    for tc in [0, 10, 25, 50]:
        r0, to0 = backtest_fixed_window(prices, 12, 0, TOP_N, tc_bps=tc)
        r1, to1 = backtest_fixed_window(prices, 12, 1, TOP_N, tc_bps=tc)
        e0 = eval_period(r0, f"12-0_tc{tc}", OOS_START, OOS_END)
        e1 = eval_period(r1, f"12-1_tc{tc}", OOS_START, OOS_END)
        avg_to0 = float(to0[(to0.index >= OOS_START) & (to0.index <= OOS_END)].mean())
        avg_to1 = float(to1[(to1.index >= OOS_START) & (to1.index <= OOS_END)].mean())
        tc_results[tc] = {"12_0_sharpe": e0["sharpe"], "12_1_sharpe": e1["sharpe"],
                            "12_0_avg_turnover": round(avg_to0, 3), "12_1_avg_turnover": round(avg_to1, 3)}
        print(f"  TC={tc}bps: 12-0 Sharpe={e0['sharpe']:.3f} (turnover {avg_to0:.1%})  "
              f"12-1 Sharpe={e1['sharpe']:.3f} (turnover {avg_to1:.1%})")

    passes_tc = tc_results[25]["12_0_sharpe"] > GATE

    # ---- Overall verdict ----
    wf_pass = wins_12_0 >= 4
    reversed_pass = reversed_holds and forward_holds
    if wf_pass and reversed_pass and passes_tc:
        verdict = "CONFIRMED"
    elif (wf_pass or reversed_pass) and passes_tc:
        verdict = "PARTIAL CONFIRMED"
    else:
        verdict = "NOT CONFIRMED"

    print(f"\n=== Verdict ===")
    print(f"Walk-forward: 12-0 wins {wins_12_0}/{len(fold_results)} folds (need >=4): {'PASS' if wf_pass else 'FAIL'}")
    print(f"Reversed split: 12-0 > 12-1 in both directions: {'PASS' if reversed_pass else 'FAIL'}")
    print(f"TC-25bps gate (12-0 OOS Sharpe > {GATE}): {'PASS' if passes_tc else 'FAIL'} (value={tc_results[25]['12_0_sharpe']})")
    print(f"{verdict}")

    out = {
        "hypothesis": "H492",
        "universe": "H198 30-stock",
        "gate": GATE,
        "walk_forward_folds": fold_results,
        "wf_12_0_wins": wins_12_0,
        "wf_n_folds": len(fold_results),
        "reversed_split": {
            "test_2013_2020": {"12_0": rev_12_0, "12_1": rev_12_1},
            "test_2021_2026": {"12_0": fwd_12_0, "12_1": fwd_12_1},
        },
        "tc_sensitivity": tc_results,
        "verdict": verdict,
    }
    outpath = RESULT_DIR / "h492_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
