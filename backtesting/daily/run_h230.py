"""
H230 — Alpha Decay Optimization for H217 Rebalancing Frequency
==============================================================
arXiv:2512.11913 (Dec 2025): Hyperbolic alpha decay modeling across
Fama-French factors. Momentum decays fastest (~40% in 3 months).
alpha101 is an intraday microstructure signal — may decay faster than
monthly momentum, potentially favoring bi-monthly rebalancing.

Test rebalancing frequencies: monthly, bi-monthly (every 2 weeks),
weekly — applying H217 signal (median alpha101 top-6) at each frequency.

Transaction cost model: 0.1% round-trip per full portfolio rebalance.
  Monthly:    ~12 rebalances/yr  → ~1.2% annual cost
  Bi-monthly: ~24 rebalances/yr  → ~2.4% annual cost
  Weekly:     ~52 rebalances/yr  → ~5.2% annual cost

Universe: 30 large-cap (same as H217)
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe after transaction costs > H217 monthly (1.559)
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

# Transaction cost: 0.1% round-trip per full portfolio rebalance
TC_PER_REBALANCE = 0.001

# H217 monthly baseline (after costs)
H217_OOS_SHARPE = 1.559
CONFIRM_THRESHOLD = H217_OOS_SHARPE


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    """Load from H215 daily cache (all 30 tickers pre-cached)."""
    cp = CACHE_DIR / f"h215_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}...")
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


def get_rebalance_dates(freq: str, daily_idx: pd.DatetimeIndex) -> list:
    """
    Return sorted list of rebalance dates (trading days in daily_idx).

    freq: 'monthly' | 'bimonthly' | 'weekly'
      - monthly:   last trading day of each calendar month
      - bimonthly: 1st and 3rd Friday of each month (if not trading day, use next)
      - weekly:    every Friday (if not trading day, use Thursday)
    """
    trading_days = set(daily_idx)
    dates = []

    if freq == "monthly":
        # Last trading day of each month
        monthly_end = pd.date_range(
            start=daily_idx.min(), end=daily_idx.max(), freq="ME"
        )
        for d in monthly_end:
            # Find the last trading day on or before d
            candidates = daily_idx[daily_idx <= d]
            if len(candidates) > 0:
                dates.append(candidates[-1])

    elif freq == "bimonthly":
        # 1st and 3rd Friday of each month
        # Generate all Fridays
        all_fridays = pd.date_range(
            start=daily_idx.min(), end=daily_idx.max(), freq="W-FRI"
        )
        # Group by (year, month) and pick indices 0 and 2 (1st and 3rd Friday)
        fri_df = pd.DataFrame({"date": all_fridays})
        fri_df["year"]  = fri_df["date"].dt.year
        fri_df["month"] = fri_df["date"].dt.month
        for (yr, mo), grp in fri_df.groupby(["year", "month"]):
            for idx in [0, 2]:  # 1st and 3rd Friday
                if idx < len(grp):
                    target = grp.iloc[idx]["date"]
                    # If target is a trading day, use it; else search forward
                    if target in trading_days:
                        dates.append(target)
                    else:
                        # Find next trading day within the same week
                        for delta in range(1, 5):
                            nxt = target + pd.Timedelta(days=delta)
                            if nxt in trading_days:
                                dates.append(nxt)
                                break

    elif freq == "weekly":
        # Every Friday (or Thursday if Friday is holiday)
        all_fridays = pd.date_range(
            start=daily_idx.min(), end=daily_idx.max(), freq="W-FRI"
        )
        for d in all_fridays:
            if d in trading_days:
                dates.append(d)
            else:
                # Try Thursday
                thu = d - pd.Timedelta(days=1)
                if thu in trading_days:
                    dates.append(thu)

    return sorted(set(dates))


def sharpe_annualized(r, periods_per_year):
    """Annualized Sharpe from period returns."""
    if r.std() == 0 or len(r) < 4:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(periods_per_year))


def maxdd(rets):
    eq = (1 + rets).cumprod()
    return float((eq / eq.cummax() - 1).min())


def neg_years(rets):
    annual = rets.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((annual < 0).sum())


def run_frequency(freq: str, alpha_daily: pd.DataFrame, close_daily: pd.DataFrame) -> dict:
    """
    Backtest H217 signal at a given rebalancing frequency.

    Returns dict with IS/OOS stats (after transaction costs).

    Method:
    - At each rebalance date, compute trailing 22-day MEDIAN alpha101
    - Select top-6 tickers by signal
    - Hold equally weighted until next rebalance
    - Subtract TC_PER_REBALANCE from the return on the rebalance day
    """
    rebal_dates = get_rebalance_dates(freq, alpha_daily.index)
    rebal_dates = [d for d in rebal_dates if d >= IS_START and d <= OOS_END]

    if len(rebal_dates) < 10:
        return {"error": f"Too few rebalance dates: {len(rebal_dates)}"}

    # Build period-by-period returns
    # For each consecutive pair of rebalance dates [t_k, t_{k+1}),
    # portfolio is held from day after t_k through t_{k+1} (inclusive).
    daily_rets = close_daily.pct_change()

    period_records = []

    for i in range(len(rebal_dates) - 1):
        signal_date = rebal_dates[i]
        hold_start  = signal_date
        hold_end    = rebal_dates[i + 1]

        # Signal: trailing 22-day median alpha101 ending at signal_date (no lookahead)
        window_start = signal_date - pd.Timedelta(days=35)  # ~25 trading days buffer
        window_data  = alpha_daily.loc[
            (alpha_daily.index >= window_start) & (alpha_daily.index <= signal_date)
        ].tail(22)

        if len(window_data) < 15:
            continue

        signal_row = window_data.median()
        signal_row = signal_row.dropna()
        if len(signal_row) < TOP_N * 2:
            continue

        selected = signal_row.nlargest(TOP_N).index.tolist()

        # Portfolio return over holding period: day after signal through end of hold period
        # (signal_date is observation day; we hold starting the next open)
        hold_mask = (daily_rets.index > hold_start) & (daily_rets.index <= hold_end)
        hold_rets  = daily_rets.loc[hold_mask, selected]
        if hold_rets.empty:
            continue

        # Equal-weight daily returns across selected stocks
        period_daily = hold_rets.mean(axis=1)  # daily returns for this holding period

        # Compute period return then subtract transaction cost on first day
        # (cost applies when we rebalance: 0.1% round-trip regardless of turnover)
        period_total = float((1 + period_daily).prod() - 1)
        period_total_after_tc = period_total - TC_PER_REBALANCE

        period_records.append({
            "start":      hold_start,
            "end":        hold_end,
            "ret_gross":  period_total,
            "ret_net":    period_total_after_tc,
            "selected":   selected,
        })

    if not period_records:
        return {"error": "No valid periods"}

    records_df = pd.DataFrame(period_records).set_index("end")
    rets_net   = records_df["ret_net"]
    rets_gross = records_df["ret_gross"]

    # Annualization factor: periods per year
    # Estimate from data: average days between rebalances
    avg_hold_days = np.mean([
        (rebal_dates[i+1] - rebal_dates[i]).days
        for i in range(len(rebal_dates)-1)
    ])
    periods_per_year = 365.25 / avg_hold_days

    def eval_period_subset(rets, label, start, end):
        r = rets[(rets.index >= start) & (rets.index <= end)]
        if len(r) < 4:
            return {"label": label, "n": 0, "sharpe": 0.0, "maxdd": 0.0, "neg_yrs": 0, "cagr": 0.0}
        sh = sharpe_annualized(r, periods_per_year)
        ann_ret = float((1 + r).prod() ** (periods_per_year / len(r)) - 1)
        md = maxdd(r)
        ny = neg_years(r)
        return {
            "label": label, "n": len(r),
            "sharpe": round(sh, 3),
            "cagr":   round(ann_ret, 3),
            "maxdd":  round(md, 3),
            "neg_yrs": ny,
        }

    n_rebal_per_year = periods_per_year
    annual_tc_drag   = TC_PER_REBALANCE * n_rebal_per_year

    return {
        "freq":            freq,
        "n_rebalances":    len(period_records),
        "avg_hold_days":   round(avg_hold_days, 1),
        "periods_per_year": round(periods_per_year, 1),
        "annual_tc_drag":  round(annual_tc_drag, 4),
        "is_net":          eval_period_subset(rets_net,   f"{freq} IS",  IS_START,  IS_END),
        "oos_net":         eval_period_subset(rets_net,   f"{freq} OOS", OOS_START, OOS_END),
        "is_gross":        eval_period_subset(rets_gross, f"{freq} IS gross",  IS_START,  IS_END),
        "oos_gross":       eval_period_subset(rets_gross, f"{freq} OOS gross", OOS_START, OOS_END),
    }


def main():
    print("H230 — Alpha Decay Rebalancing Frequency Optimization")
    print("=" * 60)
    print(f"Universe: {len(UNIVERSE)} tickers | Signal: Median Alpha101 (trailing 22-day)")
    print(f"IS: {IS_START.date()} – {IS_END.date()} | OOS: {OOS_START.date()} – {OOS_END.date()}")
    print(f"TC model: {TC_PER_REBALANCE*100:.2f}% round-trip per rebalance")
    print(f"H217 baseline (monthly, after costs): OOS Sharpe = {H217_OOS_SHARPE}")
    print()

    # Load daily OHLCV for all tickers
    print("Loading daily OHLCV data (H215 cache)...")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    print(f"  Loaded {len(daily_data)} tickers")

    # Compute daily alpha101 for each ticker
    print("Computing daily alpha101 signals...")
    alpha_series = {}
    close_series = {}
    for t, df in daily_data.items():
        alpha_series[t] = compute_alpha101(df)
        close_series[t] = df["close"]

    alpha_daily = pd.DataFrame(alpha_series).sort_index()
    close_daily = pd.DataFrame(close_series).sort_index()

    # Trim to relevant range (leave some buffer before IS_START for 22-day lookback)
    alpha_daily = alpha_daily.loc["2012-01-01":]
    close_daily = close_daily.loc["2012-01-01":]
    print(f"  Alpha matrix: {alpha_daily.shape[0]} trading days × {alpha_daily.shape[1]} stocks")

    # Run all three frequencies
    frequencies = ["monthly", "bimonthly", "weekly"]
    results = {}

    for freq in frequencies:
        print(f"\nRunning {freq} backtest...")
        r = run_frequency(freq, alpha_daily, close_daily)
        results[freq] = r
        if "error" in r:
            print(f"  ERROR: {r['error']}")
        else:
            print(f"  Rebalances: {r['n_rebalances']} | Avg hold: {r['avg_hold_days']} days | "
                  f"~{r['periods_per_year']:.1f}/yr | Annual TC drag: {r['annual_tc_drag']*100:.2f}%")
            is_  = r["is_net"]
            oos_ = r["oos_net"]
            print(f"  IS  (net): Sharpe={is_['sharpe']:.3f}, CAGR={is_['cagr']:.1%}, MaxDD={is_['maxdd']:.1%}, NegYrs={is_['neg_yrs']}")
            print(f"  OOS (net): Sharpe={oos_['sharpe']:.3f}, CAGR={oos_['cagr']:.1%}, MaxDD={oos_['maxdd']:.1%}, NegYrs={oos_['neg_yrs']}")

    # Summary table
    print("\n" + "=" * 80)
    print(f"SUMMARY — H230 Rebalancing Frequency Comparison")
    print("=" * 80)
    hdr = f"{'Freq':<14} {'IS Sharpe':>10} {'IS CAGR':>8} {'OOS Sharpe':>11} {'OOS CAGR':>9} {'OOS MaxDD':>10} {'NegYrs':>7} {'TC Drag':>8}"
    print(hdr)
    print("-" * len(hdr))

    best_freq   = None
    best_sharpe = -999
    for freq in frequencies:
        r = results[freq]
        if "error" in r:
            print(f"  {freq:<12}  ERROR: {r['error']}")
            continue
        is_  = r["is_net"]
        oos_ = r["oos_net"]
        tc   = r["annual_tc_drag"]
        marker = " ← H217 baseline" if freq == "monthly" else ""
        print(f"  {freq:<12} {is_['sharpe']:>10.3f} {is_['cagr']:>8.1%} {oos_['sharpe']:>11.3f} "
              f"{oos_['cagr']:>9.1%} {oos_['maxdd']:>10.1%} {oos_['neg_yrs']:>7d} {tc*100:>7.2f}%{marker}")
        if oos_["sharpe"] > best_sharpe:
            best_sharpe = oos_["sharpe"]
            best_freq   = freq

    print()
    best_result = results.get(best_freq, {})
    best_oos    = best_result.get("oos_net", {})
    confirmed   = best_oos.get("sharpe", 0) > CONFIRM_THRESHOLD and best_freq != "monthly"

    print(f"Best frequency (OOS Sharpe after costs): {best_freq} — Sharpe={best_sharpe:.3f}")
    print(f"H217 monthly baseline: Sharpe={H217_OOS_SHARPE:.3f}")
    print(f"Improvement over monthly: {best_sharpe - H217_OOS_SHARPE:+.3f}")
    print()
    if confirmed:
        print(f"CONFIRMED — {best_freq} rebalancing outperforms monthly after costs")
        print(f"OOS Sharpe {best_sharpe:.3f} > {CONFIRM_THRESHOLD:.3f} (H217 baseline)")
    else:
        print(f"NOT CONFIRMED — monthly rebalancing remains optimal after transaction costs")
        print(f"Higher-frequency strategies are eroded by TC drag")

    # Build full output dict
    monthly_oos_sharpe = results.get("monthly", {}).get("oos_net", {}).get("sharpe", 0.0)
    out = {
        "hypothesis":        "H230",
        "description":       "Alpha decay rebalancing frequency optimization for H217",
        "universe_size":     len(UNIVERSE),
        "signal":            "median alpha101 trailing 22-day",
        "top_n":             TOP_N,
        "tc_per_rebalance":  TC_PER_REBALANCE,
        "h217_baseline":     H217_OOS_SHARPE,
        "confirm_threshold": CONFIRM_THRESHOLD,
        "frequencies":       results,
        "best_freq":         best_freq,
        "best_oos_sharpe":   round(best_sharpe, 3),
        "confirmed":         confirmed,
        "verdict": (
            f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}: "
            f"best freq={best_freq}, OOS Sharpe={best_sharpe:.3f} vs H217={H217_OOS_SHARPE}"
        ),
    }

    out_path = RESULT_DIR / "h230_results.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {out_path}")
    return out


if __name__ == "__main__":
    main()
