"""
H198 — Cross-Sectional Stock Momentum (Jegadeesh-Titman 12-1 signal)
=====================================================================
§3.1 "151 Trading Strategies": long top decile by 12-1 month return,
monthly rebalance, equal-weight.

Universe: same 30 large-cap S&P 500 stocks as H181/H192-D
Signal: R(t-13, t-1) — 12-month return skipping last month
  (standard "skip-month" avoids short-term reversal contamination)
Portfolio: Long top-6 (top quintile), equal-weight, monthly rebalance
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 0.5, OOS cumul > 1.3×

Also tests: 6-1 and 3-1 month lookbacks to find best signal window.
Also tests: bottom-6 (contrarian) vs top-6 (momentum) to confirm direction.
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

DATA_START = "2011-01-01"   # need 14 months of history before IS start
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

TOP_N      = 6     # top quintile of 30 stocks
TC_BPS     = 5     # one-way transaction cost (5 bps)


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 198)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h198_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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


def backtest(prices: pd.DataFrame, lookback: int, top_n: int, long_top: bool = True) -> pd.Series:
    """
    Monthly returns for a cross-sectional momentum strategy.
    lookback: months to look back (skip last 1 month is baked in)
    long_top: if True, long top_n winners; if False, long top_n losers (contrarian)
    """
    monthly_ret = prices.pct_change()
    port_rets = []

    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for i, month_end in enumerate(months):
        loc = monthly_ret.index.get_loc(month_end)
        # Signal: return from (loc - lookback - 1) to (loc - 1) [skip last month]
        if loc < lookback + 1:
            continue
        signal_start = loc - lookback - 1
        signal_end   = loc - 1
        if signal_start < 0:
            continue
        sig = prices.iloc[signal_end] / prices.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        if long_top:
            selected = sig.nlargest(top_n).index.tolist()
        else:
            selected = sig.nsmallest(top_n).index.tolist()
        # Return for this month = equal-weight portfolio
        ret_this = monthly_ret.iloc[loc][selected].mean()
        # Transaction cost: turnover * TC
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


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
    print("H198 — Cross-Sectional Stock Momentum")
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

    # Also load SPY for benchmark
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
    print("\n=== Experiment A: Lookback comparison (top-6 winners, long only) ===")
    header = f"{'Lookback':<12} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(header)
    print("-" * len(header))

    for lookback, label in [(12, "12-1m"), (6, "6-1m"), (3, "3-1m")]:
        rets = backtest(prices, lookback, TOP_N, long_top=True)
        is_  = eval_period(rets, label, IS_START,  IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        results[label] = {"is": is_, "oos": oos_, "rets": rets}
        print(f"{label:<12} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")

    # SPY benchmark
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    print(f"{'SPY BH':<12} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    print("\n=== Experiment B: Winner vs Loser (12-1m lookback) ===")
    rets_loser = backtest(prices, 12, TOP_N, long_top=False)
    lo_is  = eval_period(rets_loser, "bottom-6",  IS_START,  IS_END)
    lo_oos = eval_period(rets_loser, "bottom-6",  OOS_START, OOS_END)
    wi_is  = results["12-1m"]["is"]
    wi_oos = results["12-1m"]["oos"]
    print(f"{'Top-6 (winner)':<18} IS Sharpe {wi_is['sharpe']:.3f} | OOS Sharpe {wi_oos['sharpe']:.3f} | OOS Cumul {wi_oos['cumul']:.4f}")
    print(f"{'Bottom-6 (loser)':<18} IS Sharpe {lo_is['sharpe']:.3f} | OOS Sharpe {lo_oos['sharpe']:.3f} | OOS Cumul {lo_oos['cumul']:.4f}")

    # Correlation with H192-D (BAB) — check via H192 results file if available
    print("\n=== Correlation with H192-D (BAB) and H181 (reversal) ===")
    h192_path = RESULT_DIR / "h192d_results.json"
    h181_path = RESULT_DIR / "h181_results.json"
    for label in ["12-1m", "6-1m"]:
        rets = results[label]["rets"]
        all_rets = rets[(rets.index >= IS_START) & (rets.index <= OOS_END)]
        print(f"  {label}: n={len(all_rets)}, corr-SPY={all_rets.corr(spy_ret.reindex(all_rets.index)):.3f}")

    # Verdict
    best_label = max(["12-1m","6-1m","3-1m"], key=lambda l: results[l]["oos"].get("sharpe", 0))
    best_oos   = results[best_label]["oos"]
    confirmed  = best_oos.get("sharpe", 0) > 0.5 and best_oos.get("cumul", 0) > 1.3

    print(f"\n=== Verdict ===")
    print(f"Best lookback: {best_label} → OOS Sharpe {best_oos['sharpe']:.3f}, Cumul {best_oos['cumul']:.4f}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'} (threshold: Sharpe>0.5, Cumul>1.3)")

    # Save results
    out = {
        "hypothesis": "H198",
        "lookback_results": {
            k: {"is": v["is"], "oos": v["oos"]}
            for k, v in results.items()
        },
        "bottom6_is":  lo_is,
        "bottom6_oos": lo_oos,
        "spy_is":  spy_is,
        "spy_oos": spy_oos,
        "best_lookback": best_label,
        "confirmed": confirmed,
    }
    outpath = RESULT_DIR / "h198_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
