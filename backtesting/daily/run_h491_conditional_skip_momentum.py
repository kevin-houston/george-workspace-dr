"""
H491 — Conditional Skip-Month Momentum (Dikhit 2026 follow-up)
=================================================================
Source: Dikhit, "The Informational Role of the Most Recent Month in
Industry-Level Momentum Strategies" (Zenodo preprint, Jan 2026).

Hypothesis: unconditional skip-month (12-1) momentum discards signal that
is sometimes valuable. Dikhit's finding: the most recent month carries
momentum-continuation signal WHEN it was itself above the stock's own
trailing average — skip only when recent-month return was below the
trailing average, otherwise include it (use 12-0 instead of 12-1).

Design: for each month t and each stock, compute
    recent_month_return = r[t-1]
    trailing_avg = mean(r[t-13 : t-1])   (12-month trailing avg, excluding
                                           the most recent month)
If recent_month_return >= trailing_avg: use a 12-0 window (include the
most recent month in the momentum-ranking return).
Else: use the standard 12-1 window (skip the most recent month).

Universe: H198 30-stock NASDAQ/S&P mega-cap universe (reused cache).
IS: 2013-2020, OOS: 2021-2026 (matches H198 split exactly).
Gate: OOS Sharpe > 1.174 (H198 confirmed 6-1m baseline OOS Sharpe — the
      standing gate this family uses on this exact universe/split).

Also runs an unconditional 12-1 and unconditional 12-0 baseline on the
same universe/split for a clean 3-way A/B/C comparison, plus the H198
6-1m result already on file for reference.
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

# Same 30-stock universe as H198/H181/H192-D
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

DATA_START = "2011-01-01"   # need 14 months of history before IS start
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N = 6     # top quintile of 30 stocks, same as H198
GATE  = 1.174 # H198 6-1m confirmed OOS Sharpe on this exact universe/split


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 199)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h491_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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
    if r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1)
    return float(dd.min())


def backtest_fixed_window(prices: pd.DataFrame, lookback: int, skip: int, top_n: int) -> pd.Series:
    """
    Standard fixed skip-month momentum. lookback = months in signal window
    (e.g. 12), skip = months to skip at the end (1 for 12-1, 0 for 12-0).
    """
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


def backtest_conditional(prices: pd.DataFrame, top_n: int) -> tuple:
    """
    Dikhit conditional skip-month: per-stock, per-month choice between
    12-0 (include most recent month) and 12-1 (skip it), based on whether
    recent_month_return >= trailing_avg(t-13..t-1).

    Returns (returns_series, frac_12_0_series) — the latter tracks what
    fraction of the selected universe each month used the 12-0 window,
    for diagnostic purposes.
    """
    monthly_ret = prices.pct_change()
    port_rets = []
    frac_12_0 = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        # Need 13 months of prior returns: r[loc-13] .. r[loc-1]
        if loc < 14:
            continue
        # recent_month_return = r[t-1] = monthly_ret.iloc[loc-1]
        recent = monthly_ret.iloc[loc - 1]
        # trailing_avg = mean(r[t-13 : t-1]) i.e. monthly_ret.iloc[loc-13:loc-1]
        trailing_avg = monthly_ret.iloc[loc - 13: loc - 1].mean()

        use_12_0 = recent >= trailing_avg  # boolean per stock

        # 12-0 price return: prices[loc-1] / prices[loc-12] - 1  (12 months incl. most recent)
        sig_12_0 = prices.iloc[loc - 1] / prices.iloc[loc - 12] - 1
        # 12-1 price return: prices[loc-2] / prices[loc-13] - 1  (12 months, skip most recent)
        sig_12_1 = prices.iloc[loc - 2] / prices.iloc[loc - 13] - 1

        sig = sig_12_0.where(use_12_0, sig_12_1)
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        frac = float(use_12_0.reindex(selected).mean())
        port_rets.append((month_end, ret_this))
        frac_12_0.append((month_end, frac))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    f = pd.Series({d: r for d, r in frac_12_0})
    f.index = pd.DatetimeIndex(f.index)
    return s, f


def eval_period(rets: pd.Series, label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0}
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
    print("H491 — Conditional Skip-Month Momentum (Dikhit 2026)")
    print("Loading price data…")
    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_price(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T
    prices = prices.sort_index()
    prices = prices.loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers loaded, {len(prices)} months")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    results = {}

    print("\n=== Variant A: Unconditional 12-1 (standard skip-month baseline) ===")
    rets_a = backtest_fixed_window(prices, lookback=12, skip=1, top_n=TOP_N)
    results["A_12-1"] = {
        "is":  eval_period(rets_a, "A_12-1", IS_START, IS_END),
        "oos": eval_period(rets_a, "A_12-1", OOS_START, OOS_END),
        "rets": rets_a,
    }

    print("=== Variant B: Unconditional 12-0 (always include most recent month) ===")
    rets_b = backtest_fixed_window(prices, lookback=12, skip=0, top_n=TOP_N)
    results["B_12-0"] = {
        "is":  eval_period(rets_b, "B_12-0", IS_START, IS_END),
        "oos": eval_period(rets_b, "B_12-0", OOS_START, OOS_END),
        "rets": rets_b,
    }

    print("=== Variant C: Dikhit conditional (12-0 if recent>=trailing_avg else 12-1) ===")
    rets_c, frac_c = backtest_conditional(prices, top_n=TOP_N)
    results["C_conditional"] = {
        "is":  eval_period(rets_c, "C_conditional", IS_START, IS_END),
        "oos": eval_period(rets_c, "C_conditional", OOS_START, OOS_END),
        "rets": rets_c,
    }

    # H198 6-1m reference (already on file)
    h198_path = RESULT_DIR / "h198_results.json"
    h198_ref = None
    if h198_path.exists():
        h198_ref = json.loads(h198_path.read_text())["lookback_results"]["6-1m"]

    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)

    header = f"{'Variant':<18} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'OOS MaxDD':>10} {'NegYrs':>7}"
    print("\n" + header)
    print("-" * len(header))
    for label, key in [("A 12-1 (std)", "A_12-1"), ("B 12-0 (always)", "B_12-0"), ("C Dikhit cond.", "C_conditional")]:
        is_, oos_ = results[key]["is"], results[key]["oos"]
        print(f"{label:<18} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>10.1%} {oos_['neg_yrs']:>7d}")
    if h198_ref:
        print(f"{'H198 6-1m (ref)':<18} {h198_ref['is']['sharpe']:>10.3f} {h198_ref['is']['cumul']:>10.4f} "
              f"{h198_ref['oos']['sharpe']:>10.3f} {h198_ref['oos']['cumul']:>10.4f} "
              f"{h198_ref['oos']['maxdd']:>10.1%} {h198_ref['oos']['neg_yrs']:>7d}")
    print(f"{'SPY BH':<18} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>10.1%} {spy_oos['neg_yrs']:>7d}")

    # Diagnostics: how often does the conditional strategy pick 12-0 vs 12-1?
    frac_oos = frac_c[(frac_c.index >= OOS_START) & (frac_c.index <= OOS_END)]
    frac_is  = frac_c[(frac_c.index >= IS_START) & (frac_c.index <= IS_END)]
    print(f"\nConditional 12-0 usage: IS avg {frac_is.mean():.1%} of selected names/month, "
          f"OOS avg {frac_oos.mean():.1%} of selected names/month")

    # Correlation vs SPY
    print("\n=== Correlation with SPY (full IS+OOS sample) ===")
    corrs = {}
    for label, key in [("A_12-1", "A_12-1"), ("B_12-0", "B_12-0"), ("C_conditional", "C_conditional")]:
        rets = results[key]["rets"]
        all_rets = rets[(rets.index >= IS_START) & (rets.index <= OOS_END)]
        c = float(all_rets.corr(spy_ret.reindex(all_rets.index)))
        corrs[label] = round(c, 3)
        print(f"  {label}: n={len(all_rets)}, corr-SPY={c:.3f}")

    # Verdict: does C (conditional) beat gate AND beat A (unconditional 12-1)?
    oos_c = results["C_conditional"]["oos"]
    oos_a = results["A_12-1"]["oos"]
    oos_b = results["B_12-0"]["oos"]
    passes_gate = oos_c.get("sharpe", 0) > GATE
    beats_a = oos_c.get("sharpe", 0) > oos_a.get("sharpe", 0)
    beats_b = oos_c.get("sharpe", 0) > oos_b.get("sharpe", 0)

    if passes_gate and beats_a:
        verdict = "CONFIRMED"
    elif passes_gate or beats_a:
        verdict = "PARTIAL"
    else:
        verdict = "NOT CONFIRMED"

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE} (H198 6-1m baseline)")
    print(f"Variant C (Dikhit conditional): OOS Sharpe {oos_c.get('sharpe', 0):.3f}")
    print(f"Variant A (unconditional 12-1): OOS Sharpe {oos_a.get('sharpe', 0):.3f}")
    print(f"Variant B (unconditional 12-0): OOS Sharpe {oos_b.get('sharpe', 0):.3f}")
    print(f"Passes gate: {passes_gate} | Beats unconditional 12-1: {beats_a} | Beats unconditional 12-0: {beats_b}")
    print(f"{verdict}")

    out = {
        "hypothesis": "H491",
        "universe": "H198 30-stock",
        "gate": GATE,
        "variants": {
            k: {"is": v["is"], "oos": v["oos"]}
            for k, v in results.items()
        },
        "h198_6_1m_ref": h198_ref,
        "spy_is": spy_is,
        "spy_oos": spy_oos,
        "corr_spy": corrs,
        "frac_12_0_is_avg": round(float(frac_is.mean()), 4),
        "frac_12_0_oos_avg": round(float(frac_oos.mean()), 4),
        "verdict": verdict,
    }
    outpath = RESULT_DIR / "h491_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
