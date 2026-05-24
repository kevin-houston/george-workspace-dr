"""
H220 — ETF Time-Series Momentum (Moskowitz, Ooi & Pedersen 2012)
=================================================================
"Time Series Momentum" (JFE 2012): for each asset, go long if its trailing
12m return is positive, short/flat if negative. Distinct from cross-sectional
momentum (H198) because we're not ranking assets against each other — we're
asking whether each asset is in an uptrend or downtrend.

Applied to 14-ETF universe (same as H219, data already cached):
  SPY, QQQ, IWM, XLK, XLF, XLE, XLU, XLV, XLP, GLD, TLT, EEM, USMV, SPLV

Experiments:
  A. Long-only TSMOM: invest equally in ETFs with positive 12m return; BIL otherwise
  B. Long-flat TSMOM: equal-weight of all tickers, but 0 weight to trend-negative tickers
  C. Signal sensitivity: test 3m, 6m, 12m lookbacks
  D. Vol-scaled TSMOM: weight each position by 1/realized_vol (Barroso & Santa-Clara 2015)

IS: 2013-2019, OOS: 2020-2026 (same splits as H219)

Confirm: OOS Sharpe > 0.9 AND MaxDD < -25%
(TSMOM should beat buy-and-hold on risk-adjusted basis across asset classes)
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

UNIVERSE = ["SPY","QQQ","IWM","XLK","XLF","XLE","XLU","XLV","XLP","GLD","TLT","EEM","USMV","SPLV"]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2019-12-31")
OOS_START  = pd.Timestamp("2020-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
CONFIRM_THRESHOLD = 0.9


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r):  return float((1 + r).prod())
def maxdd(r):  eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0, "sharpe": 0.0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def fetch_monthly(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h219_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def main():
    print("H220 — ETF Time-Series Momentum")

    print("Loading monthly ETF prices (reusing H219 cache)…")
    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_monthly(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    monthly_ret = prices.pct_change()
    print(f"  {len(prices.columns)} ETFs loaded, {len(prices)} months")

    spy_ret = monthly_ret["SPY"].dropna()
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)

    def tsmom(lookback: int, vol_scale: bool = False, label: str = "") -> pd.Series:
        """
        Long-flat TSMOM: equal-weight among tickers with positive lookback-month return.
        If vol_scale=True, weight by 1/trailing 3m vol.
        """
        # Signal: lookback-month return (skip-1-month convention)
        # R(t-lookback-1, t-1)
        port_rets = []
        months = monthly_ret.index[monthly_ret.index >= IS_START]
        for month_end in months:
            loc = monthly_ret.index.get_loc(month_end)
            if loc < lookback + 1:
                continue
            sig_end   = loc - 1
            sig_start = loc - lookback - 1
            if sig_start < 0:
                continue
            sig = prices.iloc[sig_end] / prices.iloc[sig_start] - 1
            sig = sig.dropna()
            # Long only those with positive trend
            long_tickers = sig[sig > 0].index.tolist()
            if len(long_tickers) == 0:
                port_rets.append((month_end, 0.0))  # all in BIL (0 return proxy)
                continue
            if vol_scale:
                # Weight = 1/trailing 3m vol, normalized to sum to 1
                ret_hist = monthly_ret.iloc[max(0, loc-3):loc]
                vols = ret_hist[long_tickers].std().replace(0, np.nan)
                weights = (1 / vols).dropna()
                weights = weights / weights.sum()
                ret = (monthly_ret.iloc[loc][weights.index] * weights).sum()
            else:
                ret = monthly_ret.iloc[loc][long_tickers].mean()
            port_rets.append((month_end, ret))
        s = pd.Series({d: r for d, r in port_rets})
        s.index = pd.DatetimeIndex(s.index)
        s.name = label or f"TSMOM_{lookback}m"
        return s

    # === Exp A: Lookback sensitivity ===
    print("\n=== Exp A: Lookback sensitivity ===")
    fmt = f"{'Strategy':<28} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    results = {}
    for lb in [3, 6, 12]:
        label = f"TSMOM {lb}m"
        rets = tsmom(lb, vol_scale=False, label=label)
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        results[label] = {"is": is_, "oos": oos_}
        print(f"{label:<28} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    print(f"{'SPY BH':<28} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    # === Exp B: Vol-scaled TSMOM (12m) ===
    print("\n=== Exp B: Vol-scaled TSMOM (12m) ===")
    rets_vs = tsmom(12, vol_scale=True, label="TSMOM 12m vol-scaled")
    vs_is  = eval_period(rets_vs, "vol-scaled", IS_START, IS_END)
    vs_oos = eval_period(rets_vs, "vol-scaled", OOS_START, OOS_END)
    print(f"  Vol-scaled TSMOM 12m:  IS Sharpe {vs_is['sharpe']:.3f} | OOS Sharpe {vs_oos['sharpe']:.3f} | MaxDD {vs_oos.get('maxdd',0):.1%}")
    results["TSMOM 12m vol-scaled"] = {"is": vs_is, "oos": vs_oos}

    # === Exp C: Correlation with SPY and H219 ===
    print("\n=== Exp C: Correlation analysis ===")
    best_label = max([k for k in results if "vol" not in k], key=lambda k: results[k]["oos"].get("sharpe", 0))
    best_rets = tsmom(int(best_label.split()[1][:-1]), vol_scale=False, label=best_label)
    oos_idx = best_rets.index[(best_rets.index >= OOS_START) & (best_rets.index <= OOS_END)]
    corr_spy = best_rets.reindex(oos_idx).corr(spy_ret.reindex(oos_idx))
    print(f"  Best TSMOM ({best_label}) vs SPY (OOS): {corr_spy:.3f}")

    # === Verdict ===
    best_oos = results[best_label]["oos"]
    confirmed = best_oos.get("sharpe", 0) >= CONFIRM_THRESHOLD

    print(f"\n=== Verdict ===")
    print(f"Best variant: {best_label}")
    print(f"OOS Sharpe: {best_oos['sharpe']:.3f} (threshold ≥ {CONFIRM_THRESHOLD})")
    print(f"OOS MaxDD:  {best_oos.get('maxdd', 0):.1%}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H220",
        "universe": UNIVERSE,
        "results": results,
        "vol_scaled_is":  vs_is,
        "vol_scaled_oos": vs_oos,
        "spy_is": spy_is, "spy_oos": spy_oos,
        "best_label": best_label,
        "best_oos": best_oos,
        "confirmed": confirmed,
        "confirm_threshold": CONFIRM_THRESHOLD,
    }
    (RESULT_DIR / "h220_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h220_results.json")
    return out


if __name__ == "__main__":
    main()
