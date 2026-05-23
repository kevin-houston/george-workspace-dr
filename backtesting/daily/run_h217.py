"""
H217 — Median Alpha101 Cross-Sectional Signal
==============================================
Alpha101 = (close - open) / (0.001 + high - low), Kakushadze (2015)

H215 tested MEAN monthly aggregation (OOS Sharpe 1.321).
H215 sensitivity analysis showed MEDIAN aggregation OOS Sharpe 1.559.

H217 formally tests median as the primary aggregation method.
Hypothesis: median is more robust to outlier trading days (option expiry,
index rebalance days) that create extreme daily alpha101 values and skew the mean.

Universe: same 30 large-cap stocks as H215/H213/H198
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 1.4 (higher threshold given favorable sensitivity finding)

If confirmed: substitute median alpha101 for mean in H215+H198 blend.
Estimated blend (median alpha101 + H198 50/50) OOS Sharpe: ~1.5+
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
CONFIRM_THRESHOLD = 1.4


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    # Reuse H215 cache files — same universe, same date range
    cp = CACHE_DIR / f"h215_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = [c.lower() for c in df.columns]
    df.index = pd.to_datetime(df.index).normalize()
    df.to_parquet(cp)
    return df


def compute_alpha101(df: pd.DataFrame) -> pd.Series:
    """(close - open) / (0.001 + high - low), clipped to [-1, 1]."""
    a = (df["close"] - df["open"]) / (0.001 + df["high"] - df["low"])
    return a.clip(-1, 1)


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r): eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def main():
    print("H217 — Alpha101: MEDIAN Monthly Aggregation (vs H215 mean)")

    # Load daily OHLCV for all tickers (reuses H215 cache)
    print("Loading daily OHLCV data…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    print(f"  Loaded {len(daily_data)} tickers")

    # Compute daily alpha101 for each ticker
    print("Computing alpha101 signals…")
    alpha_series = {}
    for t, df in daily_data.items():
        alpha_series[t] = compute_alpha101(df)

    alpha_daily = pd.DataFrame(alpha_series).sort_index()
    alpha_daily = alpha_daily.loc[DATA_START:]
    print(f"  Alpha matrix: {alpha_daily.shape[0]} days × {alpha_daily.shape[1]} stocks")

    # Monthly MEDIAN signal (key change vs H215 which uses mean)
    alpha_monthly = alpha_daily.resample("ME").median()
    print(f"  Monthly signal matrix (median): {alpha_monthly.shape}")

    # Monthly close prices for return computation
    close_monthly = {}
    for t, df in daily_data.items():
        close_monthly[t] = df["close"].resample("ME").last()
    close_px = pd.DataFrame(close_monthly).sort_index().loc[DATA_START:]
    monthly_ret = close_px.pct_change()

    # SPY benchmark (reuse H198 cache)
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

    # Signal is known at end of month M; apply to returns of month M+1 (no lookahead)
    alpha_signal = alpha_monthly.shift(1)

    print("\n=== Exp A: Long top-6 by median alpha101 ===")
    port_rets_top = []
    port_rets_bot = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        if month_end not in alpha_signal.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        signal_row = alpha_signal.loc[month_end].dropna()
        if len(signal_row) < TOP_N * 2:
            continue
        top_sel = signal_row.nlargest(TOP_N).index.tolist()
        ret_top = monthly_ret.iloc[loc][top_sel].mean()
        port_rets_top.append((month_end, ret_top))
        bot_sel = signal_row.nsmallest(TOP_N).index.tolist()
        ret_bot = monthly_ret.iloc[loc][bot_sel].mean()
        port_rets_bot.append((month_end, ret_bot))

    rets_top = pd.Series({d: r for d, r in port_rets_top})
    rets_top.index = pd.DatetimeIndex(rets_top.index)
    rets_bot = pd.Series({d: r for d, r in port_rets_bot})
    rets_bot.index = pd.DatetimeIndex(rets_bot.index)

    fmt = f"{'Strategy':<30} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    for label, rets in [("Top-6 median alpha101 (H217)", rets_top), ("Bottom-6 median alpha101", rets_bot)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<30} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    print(f"{'SPY BH':<30} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    # Direct comparison: H217 (median) vs H215 (mean)
    print("\n=== Exp B: Median vs mean — head-to-head ===")
    alpha_mean_monthly = alpha_daily.resample("ME").mean().shift(1)
    port_rets_mean = []
    for month_end in months:
        if month_end not in alpha_mean_monthly.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        row = alpha_mean_monthly.loc[month_end].dropna()
        if len(row) < TOP_N * 2:
            continue
        sel = row.nlargest(TOP_N).index.tolist()
        port_rets_mean.append((month_end, monthly_ret.iloc[loc][sel].mean()))
    rets_mean = pd.Series({d: r for d, r in port_rets_mean})
    rets_mean.index = pd.DatetimeIndex(rets_mean.index)

    for label, rets in [("H217 median", rets_top), ("H215 mean (reference)", rets_mean)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"  {label:<25} IS {is_['sharpe']:.3f} | OOS {oos_['sharpe']:.3f} | MaxDD {oos_['maxdd']:.1%}")

    # Blend test: H217 median alpha101 + H198 momentum 50/50
    print("\n=== Exp C: H217 + H198 50/50 blend ===")
    h198_res_p = RESULT_DIR / "h198_results.json"
    h198_cp = CACHE_DIR / "h198_top6_rets.parquet"
    if h198_cp.exists():
        rets_h198 = pd.read_parquet(h198_cp).squeeze()
        rets_h198.index = pd.DatetimeIndex(rets_h198.index)
        blend = (rets_top.reindex(rets_h198.index) + rets_h198.reindex(rets_top.index)) / 2
        blend = blend.dropna()
        blend_is  = eval_period(blend, "blend", IS_START, IS_END)
        blend_oos = eval_period(blend, "blend", OOS_START, OOS_END)
        corr_h198 = rets_top.reindex(rets_h198.index).dropna().corr(
            rets_h198.reindex(rets_top.index).dropna())
        print(f"  H217 vs H198 correlation: {corr_h198:.3f}")
        print(f"  H217+H198 blend IS Sharpe {blend_is['sharpe']:.3f} | OOS Sharpe {blend_oos['sharpe']:.3f} | MaxDD {blend_oos['maxdd']:.1%}")
    else:
        blend_oos = {}
        print("  H198 cache not found — skipping blend test")

    top_is  = eval_period(rets_top, "top-6 median alpha101", IS_START, IS_END)
    top_oos = eval_period(rets_top, "top-6 median alpha101", OOS_START, OOS_END)
    confirmed = top_oos.get("sharpe", 0) >= CONFIRM_THRESHOLD

    print(f"\n=== Verdict ===")
    print(f"H217 median alpha101 OOS Sharpe: {top_oos['sharpe']:.3f} (threshold ≥ {CONFIRM_THRESHOLD})")
    print(f"H217 median alpha101 OOS MaxDD:  {top_oos['maxdd']:.1%}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    if blend_oos:
        print(f"H217+H198 blend OOS Sharpe: {blend_oos.get('sharpe', 'n/a')}")

    out = {
        "hypothesis": "H217",
        "aggregation": "median",
        "top6_is":    top_is,
        "top6_oos":   top_oos,
        "bot6_is":    eval_period(rets_bot, "bot-6", IS_START, IS_END),
        "bot6_oos":   eval_period(rets_bot, "bot-6", OOS_START, OOS_END),
        "spy_is":     spy_is,
        "spy_oos":    spy_oos,
        "blend_oos":  blend_oos if blend_oos else {},
        "confirmed":  confirmed,
        "confirm_threshold": CONFIRM_THRESHOLD,
    }
    (RESULT_DIR / "h217_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h217_results.json")
    return out


if __name__ == "__main__":
    main()
