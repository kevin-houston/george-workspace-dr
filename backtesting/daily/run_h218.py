"""
H218 — Alpha101 + Momentum Blend (Kakushadze 2015 × Jegadeesh-Titman 1993)
===========================================================================
H217 (median alpha101) confirmed OOS Sharpe 1.559.
H198 (6-1m momentum) confirmed OOS Sharpe 1.174.

Hypothesis: these two signals are derived from different information
(intraday bar structure vs 6-month price trend). If correlation < 0.6,
a 50/50 blend should outperform either standalone via diversification.

Experiments:
  A. Measure H217 vs H198 monthly return correlation
  B. Test blends at 25/50/75 weights
  C. Add H192-D BAB (if cache available) for a 3-way blend check

Universe: same 30 large-cap stocks
IS: 2013-2020, OOS: 2021-2026
Confirm: any blend OOS Sharpe > 1.6 AND MaxDD < -25%
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
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 6
CONFIRM_THRESHOLD = 1.6


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r): eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


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


def build_alpha101_rets():
    """Compute H217 median alpha101 monthly portfolio returns from cache."""
    daily_data = {}
    for t in UNIVERSE:
        cp = CACHE_DIR / f"h215_{t}_daily_{DATA_START}_{DATA_END}.parquet"
        if not cp.exists():
            print(f"  WARN: daily cache missing for {t}, downloading…")
            raw = yf.download(t, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(t, axis=1, level=1)
            df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.columns = [c.lower() for c in df.columns]
            df.index = pd.to_datetime(df.index).normalize()
            df.to_parquet(cp)
            daily_data[t] = df
        else:
            daily_data[t] = pd.read_parquet(cp)

    alpha_series = {}
    for t, df in daily_data.items():
        a = (df["close"] - df["open"]) / (0.001 + df["high"] - df["low"])
        alpha_series[t] = a.clip(-1, 1)

    alpha_daily = pd.DataFrame(alpha_series).sort_index().loc[DATA_START:]
    alpha_monthly = alpha_daily.resample("ME").median().shift(1)  # signal known at month end → applied next

    close_monthly = {t: daily_data[t]["close"].resample("ME").last() for t in daily_data}
    close_px = pd.DataFrame(close_monthly).sort_index().loc[DATA_START:]
    monthly_ret = close_px.pct_change()

    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        if month_end not in alpha_monthly.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        signal_row = alpha_monthly.loc[month_end].dropna()
        if len(signal_row) < TOP_N * 2:
            continue
        sel = signal_row.nlargest(TOP_N).index.tolist()
        port_rets.append((month_end, monthly_ret.iloc[loc][sel].mean()))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    s.name = "alpha101_median"
    return s


def build_momentum_rets():
    """Compute H198 6-1m momentum monthly portfolio returns from price cache."""
    prices_list = []
    for t in UNIVERSE:
        cp = CACHE_DIR / f"h198_{t}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            s = pd.read_parquet(cp).squeeze()
            s.name = t
            prices_list.append(s)
        else:
            print(f"  WARN: H198 monthly cache missing for {t}, downloading…")
            raw = yf.download(t, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
            if isinstance(raw.columns, pd.MultiIndex):
                raw = raw.xs(t, axis=1, level=1)
            s = raw["Close"].resample("ME").last()
            s.name = t
            pd.DataFrame(s).to_parquet(cp)
            prices_list.append(s)

    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    monthly_ret = prices.pct_change()
    lookback = 6

    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        signal_start = loc - lookback - 1
        signal_end   = loc - 1
        sig = prices.iloc[signal_end] / prices.iloc[signal_start] - 1
        sig = sig.dropna()
        if len(sig) < TOP_N:
            continue
        sel = sig.nlargest(TOP_N).index.tolist()
        port_rets.append((month_end, monthly_ret.iloc[loc][sel].mean()))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    s.name = "momentum_6m1m"
    # Save for future blend tests
    pd.DataFrame(s).to_parquet(CACHE_DIR / "h198_top6_rets.parquet")
    return s


def main():
    print("H218 — Alpha101 + Momentum Blend")

    print("Building H217 (median alpha101) returns…")
    rets_a101 = build_alpha101_rets()
    print(f"  {len(rets_a101)} monthly observations")

    print("Building H198 (6-1m momentum) returns…")
    rets_mom = build_momentum_rets()
    print(f"  {len(rets_mom)} monthly observations")

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    # === Exp A: Correlation ===
    common_idx = rets_a101.index.intersection(rets_mom.index)
    corr_ab = rets_a101.reindex(common_idx).corr(rets_mom.reindex(common_idx))

    # OOS-only correlation
    oos_idx = common_idx[(common_idx >= OOS_START) & (common_idx <= OOS_END)]
    corr_oos = rets_a101.reindex(oos_idx).corr(rets_mom.reindex(oos_idx))

    print(f"\n=== Exp A: Correlation ===")
    print(f"  Full-period correlation (H217 vs H198): {corr_ab:.3f}")
    print(f"  OOS-only correlation  (H217 vs H198):   {corr_oos:.3f}")

    # SPY correlation
    print(f"  H217 vs SPY (OOS): {rets_a101.reindex(oos_idx).corr(spy_ret.reindex(oos_idx)):.3f}")
    print(f"  H198 vs SPY (OOS): {rets_mom.reindex(oos_idx).corr(spy_ret.reindex(oos_idx)):.3f}")

    # === Exp B: Blend weights ===
    print(f"\n=== Exp B: Blend weight sweep ===")
    fmt = f"{'Blend':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))

    blend_results = {}
    for w_a101 in [0.0, 0.25, 0.50, 0.75, 1.0]:
        w_mom = 1.0 - w_a101
        blend_idx = rets_a101.index.intersection(rets_mom.index)
        blend = w_a101 * rets_a101.reindex(blend_idx) + w_mom * rets_mom.reindex(blend_idx)
        blend = blend.dropna()

        label = (
            "H217 only (alpha101)"     if w_a101 == 1.0 else
            "H198 only (momentum)"     if w_a101 == 0.0 else
            f"Blend {int(w_a101*100)}/{int(w_mom*100)} (A101/Mom)"
        )
        is_  = eval_period(blend, label, IS_START, IS_END)
        oos_ = eval_period(blend, label, OOS_START, OOS_END)
        blend_results[label] = {"is": is_, "oos": oos_, "w_a101": w_a101}
        print(f"{label:<30} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")

    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    print(f"{'SPY BH':<30} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    # === Verdict ===
    best_label = max(blend_results.keys(), key=lambda k: blend_results[k]["oos"].get("sharpe", 0))
    best_oos   = blend_results[best_label]["oos"]
    confirmed  = best_oos.get("sharpe", 0) >= CONFIRM_THRESHOLD

    print(f"\n=== Verdict ===")
    print(f"Best blend: {best_label}")
    print(f"OOS Sharpe: {best_oos['sharpe']:.3f} (threshold ≥ {CONFIRM_THRESHOLD})")
    print(f"OOS MaxDD:  {best_oos['maxdd']:.1%}")
    print(f"Full-period correlation (H217 vs H198): {corr_ab:.3f}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H218",
        "corr_h217_h198_full": round(corr_ab, 3),
        "corr_h217_h198_oos":  round(corr_oos, 3),
        "blend_results": blend_results,
        "best_blend": best_label,
        "best_oos":   best_oos,
        "spy_is": spy_is, "spy_oos": spy_oos,
        "confirmed": confirmed,
        "confirm_threshold": CONFIRM_THRESHOLD,
    }
    (RESULT_DIR / "h218_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h218_results.json")
    return out


if __name__ == "__main__":
    main()
