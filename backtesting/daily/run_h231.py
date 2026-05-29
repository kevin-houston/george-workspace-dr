"""
H231 — Alpha101 with AI-Driven Alpha Decay Half-Life Weighting
==============================================================
Source: arXiv:2605.23905 (May 2026) — momentum half-lives compressed 84→12 months
post-AI adoption. Traditional uniform/median aggregation treats all days equally,
but if alpha decays exponentially, recent days should dominate.

Signal modification:
  Instead of uniform trailing-22-day median, weight each day by exp(-age/halflife)
  where age = days since that observation (0 = most recent), halflife = halflife_months * 21.

  signal[t] = sum(alpha101[t-k] * exp(-k/halflife), k=0..21) / sum(weights)
  (exponentially weighted mean — practical proxy for rank-equivalent to EW-median)

Test halflife_months in [6, 12, 18, 24] → halflives in [126, 252, 378, 504] trading days.
Also test halflife = ∞ (uniform mean) as reference.

Comparison baseline: H217 uniform median (OOS Sharpe 1.559)
Universe: same 30 large-cap as H217
IS: 2013-2020, OOS: 2021-2026
Success gate: OOS Sharpe > 1.7
Transaction cost: 0.1% round-trip monthly rebalance (same as H217)
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
CONFIRM_THRESHOLD = 1.7
TC_PER_TRADE = 0.001  # 0.1% per leg → 0.1% round-trip for long-only monthly turnover


# Halflife configurations: months → trading days
HALFLIFE_CONFIGS = {
    "hl_6mo":  6  * 21,   # 126 trading days
    "hl_12mo": 12 * 21,   # 252 trading days
    "hl_18mo": 18 * 21,   # 378 trading days
    "hl_24mo": 24 * 21,   # 504 trading days
    "uniform": None,      # equivalent to infinite halflife (reference)
}


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    """Reuse H215 cache files — same universe, same date range."""
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
        return {"label": label, "n": 0, "sharpe": 0.0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def compute_ewm_monthly_signal(alpha_daily: pd.DataFrame, halflife: float | None) -> pd.DataFrame:
    """
    Compute exponentially weighted mean alpha101 signal, aggregated to month-end.

    For each month-end date M, look back WINDOW=22 trading days and compute:
        signal[ticker] = sum(alpha101[day] * exp(-age/halflife)) / sum(weights)
    where age=0 for the most recent day (day M), age=21 for the oldest.

    If halflife is None → uniform weights (mean, reference case).

    Returns a month-end DataFrame of signals (same structure as alpha_daily.resample("ME").mean()).
    """
    WINDOW = 22

    if halflife is None:
        # Uniform mean (reference) — just resample
        return alpha_daily.resample("ME").mean()

    # Build weight vector: index 0=oldest, WINDOW-1=most recent
    # age of day at position i (0-indexed from oldest): age = (WINDOW-1) - i
    ages = np.arange(WINDOW - 1, -1, -1, dtype=float)  # [21, 20, ..., 0]
    weights = np.exp(-ages / halflife)                   # higher weight for age=0 (recent)
    weights /= weights.sum()

    # Get all month-end dates in data
    month_ends = alpha_daily.resample("ME").last().index

    result = {}
    for me in month_ends:
        # Get the WINDOW trading days ending on or before me
        avail = alpha_daily.index[alpha_daily.index <= me]
        if len(avail) < WINDOW:
            continue
        window_days = avail[-WINDOW:]  # oldest first
        window_data = alpha_daily.loc[window_days]  # shape: (WINDOW, n_tickers)

        if len(window_data) < WINDOW:
            continue

        # weights shape (WINDOW,), window_data shape (WINDOW, n_tickers)
        # weighted mean = weights @ values / sum(weights) [weights already normalized]
        w = weights[-len(window_data):]  # in case window shorter than WINDOW at start
        w = w / w.sum()
        row = (window_data.values * w[:, np.newaxis]).sum(axis=0)
        result[me] = pd.Series(row, index=window_data.columns)

    if not result:
        return pd.DataFrame()

    return pd.DataFrame(result).T


def apply_tc(port_rets: pd.Series, prev_holdings: list, curr_holdings: list) -> float:
    """Simple TC: count turnover (stocks entering/exiting top-N) × TC_PER_TRADE."""
    if not prev_holdings:
        return 0.0
    prev_set = set(prev_holdings)
    curr_set = set(curr_holdings)
    # Exits + entries
    exits   = len(prev_set - curr_set)
    entries = len(curr_set - prev_set)
    # Each exit + entry is a round-trip sell+buy: charge TC_PER_TRADE per leg
    tc = (exits + entries) * TC_PER_TRADE / TOP_N  # spread cost per position
    return tc


def run_backtest(alpha_daily: pd.DataFrame, close_px: pd.DataFrame,
                 halflife: float | None, label: str) -> pd.Series:
    """Run the monthly long-top-6 strategy with EWM signal and TC."""
    print(f"  Running {label}…")
    signal_monthly = compute_ewm_monthly_signal(alpha_daily, halflife)
    # Shift by 1: signal at month M is known at end of M, applied at return of M+1
    signal_lagged = signal_monthly.shift(1)

    monthly_ret = close_px.pct_change()
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    port_rets = []
    prev_holdings = []
    for month_end in months:
        if month_end not in signal_lagged.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        signal_row = signal_lagged.loc[month_end].dropna()
        if len(signal_row) < TOP_N * 2:
            continue
        top_sel = signal_row.nlargest(TOP_N).index.tolist()
        gross_ret = monthly_ret.iloc[loc][top_sel].mean()
        tc = apply_tc(None, prev_holdings, top_sel)
        net_ret = gross_ret - tc
        port_rets.append((month_end, net_ret))
        prev_holdings = top_sel

    rets = pd.Series({d: r for d, r in port_rets})
    rets.index = pd.DatetimeIndex(rets.index)
    return rets


def main():
    print("H231 — Alpha101 Exponential Decay Half-Life Weighting")
    print("=" * 55)

    # Load daily OHLCV (reuse H215 cache)
    print("\nLoading daily OHLCV data…")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    print(f"  Loaded {len(daily_data)} tickers")

    # Compute daily alpha101
    print("Computing alpha101 signals…")
    alpha_series = {}
    for t, df in daily_data.items():
        alpha_series[t] = compute_alpha101(df)

    alpha_daily = pd.DataFrame(alpha_series).sort_index()
    alpha_daily = alpha_daily.loc[DATA_START:]
    print(f"  Alpha matrix: {alpha_daily.shape[0]} days × {alpha_daily.shape[1]} stocks")

    # Monthly close prices
    close_monthly = {}
    for t, df in daily_data.items():
        close_monthly[t] = df["close"].resample("ME").last()
    close_px = pd.DataFrame(close_monthly).sort_index().loc[DATA_START:]

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

    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)

    # Run all halflife configurations
    print("\nRunning halflife experiments…")
    results_by_config = {}
    for cfg_name, hl in HALFLIFE_CONFIGS.items():
        rets = run_backtest(alpha_daily, close_px, hl, cfg_name)
        results_by_config[cfg_name] = rets

    # Report
    print("\n=== Results Table ===")
    hdr = f"{'Config':<14} {'HalfLife':>10}  {'IS Sharpe':>10} {'IS MaxDD':>9}  {'OOS Sharpe':>11} {'OOS MaxDD':>10} {'OOS NegYrs':>11}"
    print(hdr)
    print("-" * len(hdr))

    summary = {}
    best_oos_sharpe = -99.0
    best_config = None
    for cfg_name, hl in HALFLIFE_CONFIGS.items():
        rets = results_by_config[cfg_name]
        hl_label = f"{hl//21}mo" if hl else "uniform"
        is_  = eval_period(rets, cfg_name, IS_START, IS_END)
        oos_ = eval_period(rets, cfg_name, OOS_START, OOS_END)
        print(f"  {cfg_name:<12} {hl_label:>10}  {is_['sharpe']:>10.3f} {is_['maxdd']:>8.1%}  "
              f"{oos_['sharpe']:>11.3f} {oos_['maxdd']:>9.1%} {oos_.get('neg_yrs', 0):>11d}")
        summary[cfg_name] = {"halflife_days": hl, "halflife_label": hl_label, "is": is_, "oos": oos_}
        if oos_['sharpe'] > best_oos_sharpe:
            best_oos_sharpe = oos_['sharpe']
            best_config = cfg_name

    print(f"\n{'SPY BH':<14} {'—':>10}  {spy_is['sharpe']:>10.3f} {spy_is['maxdd']:>8.1%}  "
          f"{spy_oos['sharpe']:>11.3f} {spy_oos['maxdd']:>9.1%} {spy_oos.get('neg_yrs', 0):>11d}")

    print(f"\n=== Verdict ===")
    print(f"Best config: {best_config}  |  OOS Sharpe: {best_oos_sharpe:.3f}  (H217 baseline: 1.559)")
    print(f"Confirm threshold: OOS Sharpe > {CONFIRM_THRESHOLD}")
    confirmed = best_oos_sharpe >= CONFIRM_THRESHOLD
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    best_oos = summary[best_config]["oos"]
    best_is  = summary[best_config]["is"]

    out = {
        "hypothesis": "H231",
        "description": "Alpha101 exponential decay half-life weighting",
        "source": "arXiv:2605.23905",
        "halflife_configs_tested": list(HALFLIFE_CONFIGS.keys()),
        "best_config": best_config,
        "best_halflife_days": HALFLIFE_CONFIGS[best_config],
        "best_is":   best_is,
        "best_oos":  best_oos,
        "h217_baseline_oos_sharpe": 1.559,
        "all_configs": summary,
        "spy_is":  spy_is,
        "spy_oos": spy_oos,
        "confirmed": confirmed,
        "confirm_threshold": CONFIRM_THRESHOLD,
    }
    out_path = RESULT_DIR / "h231_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {out_path}")
    return out


if __name__ == "__main__":
    main()
