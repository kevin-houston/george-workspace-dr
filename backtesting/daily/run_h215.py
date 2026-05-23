"""
H215 — Alpha101 Close-Within-Range Cross-Sectional Signal
==========================================================
Kakushadze (2015) "101 Formulaic Alphas", alpha #101:

    alpha101 = (close - open) / (0.001 + high - low)

Measures where each stock closes within its daily high-low range,
normalized and ranked cross-sectionally. High score = stock closed near
top of range that day (intraday momentum). Low score = closed near bottom
(potential reversal candidate).

Implementation:
- Compute daily alpha101 for all 30 stocks
- Average over the calendar month to get a stable monthly signal
- Long top-6 by monthly avg alpha101, equal-weight, monthly rebalance
- OHLCV-only: no VWAP required, buildable from free-tier Alpaca/yfinance

IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 0.7 (weaker prior than momentum; alpha101 is a
         complementary signal, expected to add value in blend, not standalone)

Cross-reference: expected low correlation with H212 (momentum uses 6m returns;
alpha101 uses daily bar structure). If corr < 0.4, worth adding to blend.
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


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
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
    print("H215 — Alpha101: Close-Within-Range Cross-Sectional Signal")

    # Load daily OHLCV for all tickers
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

    # Monthly average signal (mean of daily alpha101 over each calendar month)
    alpha_monthly = alpha_daily.resample("ME").mean()
    print(f"  Monthly signal matrix: {alpha_monthly.shape}")

    # Monthly close prices for return computation
    close_monthly = {}
    for t, df in daily_data.items():
        close_monthly[t] = df["close"].resample("ME").last()
    close_px = pd.DataFrame(close_monthly).sort_index().loc[DATA_START:]
    monthly_ret = close_px.pct_change()

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

    # Signal is known at end of month M; apply to returns of month M+1 (no lookahead)
    alpha_signal = alpha_monthly.shift(1)  # shift 1 month forward

    print("\n=== Exp A: Long top-6 by alpha101 (closed near top of range) ===")
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
        # Long top-6 (closed near high of range last month)
        top_sel = signal_row.nlargest(TOP_N).index.tolist()
        ret_top = monthly_ret.iloc[loc][top_sel].mean()
        port_rets_top.append((month_end, ret_top))
        # Long bottom-6 (closed near low of range last month = contrarian)
        bot_sel = signal_row.nsmallest(TOP_N).index.tolist()
        ret_bot = monthly_ret.iloc[loc][bot_sel].mean()
        port_rets_bot.append((month_end, ret_bot))

    rets_top = pd.Series({d: r for d, r in port_rets_top})
    rets_top.index = pd.DatetimeIndex(rets_top.index)
    rets_bot = pd.Series({d: r for d, r in port_rets_bot})
    rets_bot.index = pd.DatetimeIndex(rets_bot.index)

    fmt = f"{'Strategy':<26} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    for label, rets in [("Top-6 alpha101 (H215)", rets_top), ("Bottom-6 alpha101", rets_bot)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<26} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    print(f"{'SPY BH':<26} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    # Top-6 signal aggregation sensitivity: monthly mean vs month-end vs monthly median
    print("\n=== Exp B: Signal aggregation sensitivity ===")
    for agg_name, agg_fn in [("mean", "mean"), ("median", "median"), ("month-end", "last")]:
        if agg_fn == "last":
            sig_m = alpha_daily.resample("ME").last().shift(1)
        else:
            sig_m = alpha_daily.resample("ME").agg(agg_fn).shift(1)
        pr = []
        for month_end in months:
            if month_end not in sig_m.index:
                continue
            loc = monthly_ret.index.get_loc(month_end)
            row = sig_m.loc[month_end].dropna()
            if len(row) < TOP_N * 2:
                continue
            sel = row.nlargest(TOP_N).index.tolist()
            pr.append((month_end, monthly_ret.iloc[loc][sel].mean()))
        rs = pd.Series({d: r for d, r in pr})
        rs.index = pd.DatetimeIndex(rs.index)
        is_r  = eval_period(rs, agg_name, IS_START, IS_END)
        oos_r = eval_period(rs, agg_name, OOS_START, OOS_END)
        print(f"  {agg_name:<12} IS Sharpe {is_r['sharpe']:.3f} | OOS Sharpe {oos_r['sharpe']:.3f}")

    # Correlation with H212 momentum
    print("\n=== Correlation with H212/H198 ===")
    h212_cp = CACHE_DIR / "h215_spy_monthly.parquet"
    # Load H212 results to get correlation if available
    h212_res_p = RESULT_DIR / "h212_results.json"
    if h212_res_p.exists():
        print("  H212 results available — estimating correlation via SPY proxy")
    all_top = rets_top.reindex(spy_ret.index).dropna()
    spy_aligned = spy_ret.reindex(all_top.index).dropna()
    corr_spy = all_top.corr(spy_aligned)
    print(f"  Top-6 alpha101 vs SPY: {corr_spy:.3f}")

    top_is  = eval_period(rets_top, "top-6 alpha101", IS_START, IS_END)
    top_oos = eval_period(rets_top, "top-6 alpha101", OOS_START, OOS_END)
    confirmed = top_oos.get("sharpe", 0) >= 0.7

    print(f"\n=== Verdict ===")
    print(f"Top-6 alpha101 OOS Sharpe: {top_oos['sharpe']:.3f} (threshold ≥ 0.7)")
    print(f"Top-6 alpha101 OOS MaxDD:  {top_oos['maxdd']:.1%}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H215",
        "top6_is":    top_is,
        "top6_oos":   top_oos,
        "bot6_is":    eval_period(rets_bot, "bot-6", IS_START, IS_END),
        "bot6_oos":   eval_period(rets_bot, "bot-6", OOS_START, OOS_END),
        "spy_is":     spy_is,
        "spy_oos":    spy_oos,
        "corr_spy":   round(corr_spy, 3),
        "confirmed":  confirmed,
    }
    (RESULT_DIR / "h215_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h215_results.json")
    return out


if __name__ == "__main__":
    main()
