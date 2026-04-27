"""
H036 — Overnight Gap Mean-Reversion on SPY
===========================================

Concept:
  When SPY opens significantly lower than the prior close (gap-down),
  buy at the open and hold until close. Large gap-downs tend to partially
  fill intraday — a well-documented short-term mean-reversion pattern.

Strategy rules:
  - Each morning: gap = (Open[t] - Close[t-1]) / Close[t-1]
  - Threshold A (-0.5%): if gap < -0.005 → BUY at Open[t], SELL at Close[t]
  - Threshold B (-1.0%): if gap < -0.010 → BUY at Open[t], SELL at Close[t]
  - No position on gap-up or flat days
  - 100% capital allocation when signal fires
  - Single-day hold only (open→close)

P&L per trade = Close[t] / Open[t] - 1

Periods:
  Full:  2000-01-01 → 2026-04-27
  IS:    2000-01-01 → 2014-12-31
  OOS:   2015-01-01 → 2026-04-27

Outputs:
  /workspace/agent/backtesting/results/h036_results.json
  /workspace/agent/backtesting/daily/run_h036.py  (this file)
"""

import json
import math
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

TICKER      = "SPY"
FULL_START  = "2000-01-01"
FULL_END    = "2026-04-27"
IS_END      = "2014-12-31"
OOS_START   = "2015-01-01"

GAP_THRESH_A = -0.005   # -0.5%
GAP_THRESH_B = -0.010   # -1.0%

INITIAL_EQUITY = 100_000.0

CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

# H009 parameters (for correlation comparison)
IBS_BUY  = 0.20
IBS_SELL = 0.80
MAX_HOLD = 5


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    """Fetch SPY OHLC from yfinance, with parquet cache."""
    key = f"h036_spy_ohlc_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h036_{h}.parquet"

    if cp.exists():
        df = pd.read_parquet(cp)
        print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
        return df

    print(f"  Downloading SPY OHLC {start} → {end} …")
    raw = yf.download([TICKER], start=start, end=end,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(TICKER, axis=1, level=1)[["Open", "High", "Low", "Close"]]
    else:
        df = raw[["Open", "High", "Low", "Close"]]
    df = df.rename(columns=str.lower).dropna()
    df.index = pd.to_datetime(df.index)
    df.to_parquet(cp)
    print(f"  Downloaded and cached ({len(df)} rows)")
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add gap and IBS columns (no look-ahead).
    gap[t]  = (Open[t] - Close[t-1]) / Close[t-1]
    ibs[t]  = (Close[t] - Low[t]) / (High[t] - Low[t])
    trade_ret[t] = Close[t] / Open[t] - 1  (same-day return if bought at open)
    """
    df = df.copy()
    df["prev_close"]  = df["close"].shift(1)
    df["gap"]         = (df["open"] - df["prev_close"]) / df["prev_close"]
    df["trade_ret"]   = df["close"] / df["open"] - 1
    denom             = (df["high"] - df["low"]).replace(0, np.nan)
    df["ibs"]         = (df["close"] - df["low"]) / denom
    df["ibs"]         = df["ibs"].clip(0.0, 1.0)
    df = df.dropna(subset=["prev_close", "gap"])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# H036 backtest engine
# ─────────────────────────────────────────────────────────────────────────────

def run_h036(df: pd.DataFrame, threshold: float) -> tuple:
    """
    Simulate H036 gap mean-reversion strategy.

    Args:
        df:        DataFrame with gap, trade_ret, ibs columns (from build_features)
        threshold: gap threshold (negative float, e.g. -0.005)

    Returns:
        (equity_series, trades_list, daily_returns_series)

    daily_returns_series: indexed by date, = trade_ret on signal days, 0 elsewhere.
    equity_series:        compounded equity curve starting at INITIAL_EQUITY.
    """
    equity  = INITIAL_EQUITY
    equity_list  = []
    trades       = []
    daily_rets   = []

    for idx, row in df.iterrows():
        gap  = row["gap"]
        ret  = row["trade_ret"]
        date = idx

        if gap < threshold:
            # Signal fires: buy at open, sell at close
            trade_ret = float(ret)
            equity   *= (1.0 + trade_ret)
            trades.append({
                "date":       str(date.date()),
                "gap_pct":    round(float(gap) * 100, 4),
                "trade_ret_pct": round(trade_ret * 100, 4),
                "win":        int(trade_ret > 0),
                "open":       round(float(row["open"]), 4),
                "close":      round(float(row["close"]), 4),
            })
            daily_rets.append((date, trade_ret))
        else:
            daily_rets.append((date, 0.0))

        equity_list.append((date, equity))

    eq_series   = pd.Series(
        [v for _, v in equity_list],
        index=pd.DatetimeIndex([d for d, _ in equity_list]),
        name="equity",
    )
    dr_series   = pd.Series(
        [r for _, r in daily_rets],
        index=pd.DatetimeIndex([d for d, _ in daily_rets]),
        name="daily_ret",
    )
    return eq_series, trades, dr_series


# ─────────────────────────────────────────────────────────────────────────────
# H009 daily return series (for correlation comparison)
# ─────────────────────────────────────────────────────────────────────────────

def build_h009_daily_rets(df: pd.DataFrame) -> pd.Series:
    """
    Reproduce H009 IBS strategy and return a daily return series:
      - 0 when not in position
      - close-to-close return when in position (covers entry day too as open→close)

    Signal (no look-ahead):
      - BUY  at Open[t] if IBS[t-1] < IBS_BUY  (previous day IBS)
      - SELL at Open[t] if IBS[t-1] > IBS_SELL OR days_held >= MAX_HOLD

    For the daily-return series used in correlation:
      - On each in-position day, return = Close[t]/Close[t-1] - 1
      - On out-of-position days, return = 0
    """
    dates     = list(df.index)
    closes    = df["close"].values
    ibs_vals  = df["ibs"].values
    n         = len(df)

    position  = 0        # 0=flat, 1=long
    days_held = 0
    rets_list = []

    for i in range(1, n):
        prev_ibs = ibs_vals[i - 1]
        c_prev   = closes[i - 1]
        c_curr   = closes[i]
        daily_r  = c_curr / c_prev - 1 if c_prev > 0 else 0.0
        date     = dates[i]

        if position == 1:
            days_held += 1
            if prev_ibs > IBS_SELL or days_held >= MAX_HOLD:
                # Exit at open[i]; for the correlation series use close[i-1]→close[i]
                # (simplification: the position ends but we still earned the day's cc return)
                rets_list.append((date, daily_r))
                position  = 0
                days_held = 0
            else:
                rets_list.append((date, daily_r))
        else:
            if prev_ibs < IBS_BUY:
                # Enter at open[i]
                position  = 1
                days_held = 1
                rets_list.append((date, daily_r))
            else:
                rets_list.append((date, 0.0))

    return pd.Series(
        [r for _, r in rets_list],
        index=pd.DatetimeIndex([d for d, _ in rets_list]),
        name="h009_daily_ret",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(eq: pd.Series, trades: list, label: str, n_years_override: float = None) -> dict:
    """Compute CAGR, Sharpe, MaxDD, win rate, trade stats from equity curve."""
    # CAGR
    if n_years_override is not None:
        n_years = n_years_override
    else:
        n_years = len(eq) / 252.0
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1.0 / n_years) - 1 if n_years > 0 else 0.0

    # Sharpe from daily returns (only trade days contribute non-zero returns)
    # Use all daily returns (0 on non-trade days) for Sharpe denominator
    daily_rets = eq.pct_change().dropna()
    # Replace tiny floating-point noise with true zeros
    if len(daily_rets) > 0:
        vol_daily = float(daily_rets.std())
        mean_daily = float(daily_rets.mean())
        sharpe = (mean_daily / vol_daily * math.sqrt(252)) if vol_daily > 0 else 0.0
    else:
        sharpe = 0.0

    # MaxDD
    roll_max = eq.expanding().max()
    max_dd   = float((eq / roll_max - 1).min())

    # Trade stats
    n_trades = len(trades)
    if n_trades > 0:
        wins      = sum(t["win"] for t in trades)
        win_rate  = wins / n_trades
        avg_ret   = sum(t["trade_ret_pct"] for t in trades) / n_trades
        avg_gap   = sum(t["gap_pct"] for t in trades) / n_trades
    else:
        win_rate = avg_ret = avg_gap = 0.0

    trades_per_year = n_trades / n_years if n_years > 0 else 0.0

    return {
        "period":          label,
        "n_years":         round(n_years, 1),
        "cagr_pct":        round(float(cagr) * 100, 3),
        "sharpe":          round(sharpe, 4),
        "max_dd_pct":      round(max_dd * 100, 3),
        "n_trades":        n_trades,
        "trades_per_year": round(trades_per_year, 1),
        "win_rate_pct":    round(win_rate * 100, 2),
        "avg_trade_ret_pct": round(avg_ret, 4),
        "avg_gap_pct":     round(avg_gap, 4),
        "final_equity":    round(float(eq.iloc[-1]), 2),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H036 — Overnight Gap Mean-Reversion on SPY")
    print("=" * 72)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print("\n[1] Fetching SPY OHLC …")
    df_raw = fetch_spy_ohlc(FULL_START, FULL_END)
    df     = build_features(df_raw)
    print(f"    Data range: {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} trading days)")

    # ── 2. Slice periods ──────────────────────────────────────────────────────
    df_full = df.loc[FULL_START:FULL_END]
    df_is   = df.loc[FULL_START:IS_END]
    df_oos  = df.loc[OOS_START:FULL_END]

    n_years_full = len(df_full) / 252.0
    n_years_is   = len(df_is)   / 252.0
    n_years_oos  = len(df_oos)  / 252.0

    print(f"    Full: {len(df_full)} days ({n_years_full:.1f} yrs)  "
          f"IS: {len(df_is)} days ({n_years_is:.1f} yrs)  "
          f"OOS: {len(df_oos)} days ({n_years_oos:.1f} yrs)")

    # ── 3. Run backtests ──────────────────────────────────────────────────────
    results = {}

    for label_thresh, threshold in [
        ("threshold_0.5pct", GAP_THRESH_A),
        ("threshold_1.0pct", GAP_THRESH_B),
    ]:
        pct_str = f"{abs(threshold)*100:.1f}%"
        print(f"\n[{'2' if threshold == GAP_THRESH_A else '3'}] Running threshold = -{pct_str} …")

        eq_full, tr_full, dr_full = run_h036(df_full, threshold)
        eq_is,   tr_is,   dr_is   = run_h036(df_is,   threshold)
        eq_oos,  tr_oos,  dr_oos  = run_h036(df_oos,  threshold)

        s_full = compute_stats(eq_full, tr_full, f"Full 2000–2026",   n_years_full)
        s_is   = compute_stats(eq_is,   tr_is,   f"IS   2000–2014",   n_years_is)
        s_oos  = compute_stats(eq_oos,  tr_oos,  f"OOS  2015–2026",   n_years_oos)

        # Print summary table
        cols = ["period", "cagr_pct", "sharpe", "max_dd_pct",
                "n_trades", "trades_per_year", "win_rate_pct", "avg_trade_ret_pct"]
        header = (f"  {'Period':<20} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8}"
                  f" {'#Trades':>8} {'Trades/yr':>10} {'Win%':>7} {'AvgPnL%':>9}")
        sep = "  " + "-" * (len(header) - 2)
        print(f"\n  GAP THRESHOLD: -{pct_str}")
        print(header)
        print(sep)
        for s in [s_full, s_is, s_oos]:
            print(
                f"  {s['period']:<20} {s['cagr_pct']:>8.3f} {s['sharpe']:>8.4f}"
                f" {s['max_dd_pct']:>8.3f} {s['n_trades']:>8}"
                f" {s['trades_per_year']:>10.1f} {s['win_rate_pct']:>7.2f}"
                f" {s['avg_trade_ret_pct']:>9.4f}"
            )

        results[label_thresh] = {
            "threshold_pct":   abs(threshold) * 100,
            "full_period":     s_full,
            "in_sample":       s_is,
            "out_of_sample":   s_oos,
            "full_trades":     tr_full,
            "is_trades":       tr_is,
            "oos_trades":      tr_oos,
            "_eq_full":        eq_full,   # kept for correlation (stripped before JSON)
            "_dr_full":        dr_full,
            "_dr_is":          dr_is,
            "_dr_oos":         dr_oos,
        }

    # ── 4. H009 signal overlap / correlation ─────────────────────────────────
    print("\n[4] Computing H009 daily return series for correlation …")
    h009_dr = build_h009_daily_rets(df_full)

    corr_data = {}
    for label_thresh, threshold in [
        ("threshold_0.5pct", GAP_THRESH_A),
        ("threshold_1.0pct", GAP_THRESH_B),
    ]:
        h036_dr = results[label_thresh]["_dr_full"]
        common  = h036_dr.index.intersection(h009_dr.index)
        h36     = h036_dr.loc[common]
        h09     = h009_dr.loc[common]

        # Overall daily return correlation (including many 0/0 days)
        corr_all = float(h36.corr(h09)) if h36.std() > 0 and h09.std() > 0 else 0.0

        # Correlation on days where at LEAST one strategy is active
        active_mask = (h36 != 0) | (h09 != 0)
        h36_a = h36[active_mask]
        h09_a = h09[active_mask]
        corr_active = float(h36_a.corr(h09_a)) if (
            len(h36_a) > 5 and h36_a.std() > 0 and h09_a.std() > 0
        ) else 0.0

        # Overlap: H036 signal days where H009 is also active
        h036_signal_days = set(h36[h36 != 0].index)
        h009_active_days = set(h09[h09 != 0].index)
        overlap_days     = h036_signal_days & h009_active_days
        overlap_pct      = len(overlap_days) / len(h036_signal_days) * 100 if h036_signal_days else 0.0

        pct_str = f"{abs(threshold)*100:.1f}%"
        print(f"\n  H036 (-{pct_str}) vs H009 correlation:")
        print(f"    Overall daily corr (all days):      {corr_all:.4f}")
        print(f"    Corr on active days (either fires): {corr_active:.4f}")
        print(f"    H036 signal days:                   {len(h036_signal_days)}")
        print(f"    H009 active days:                   {len(h009_active_days)}")
        print(f"    Overlap (both active same day):     {len(overlap_days)} ({overlap_pct:.1f}%)")

        corr_data[label_thresh] = {
            "corr_all_daily":          round(corr_all,    4),
            "corr_active_days":        round(corr_active, 4),
            "n_h036_signal_days":      len(h036_signal_days),
            "n_h009_active_days":      len(h009_active_days),
            "n_overlap_days":          len(overlap_days),
            "overlap_pct":             round(overlap_pct, 2),
            "interpretation": (
                "Low correlation means H036 and H009 fire on different days — "
                "good diversification if blending."
            ),
        }

    # ── 5. Print comparison table ─────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  H036 FULL-PERIOD SUMMARY vs H009 IBS")
    print("=" * 80)
    print(f"  {'Strategy':<30} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8}"
          f" {'Trades/yr':>10} {'Win%':>7}")
    print("  " + "-" * 78)

    # H009 on same full period
    eq_h009_full = pd.Series(INITIAL_EQUITY, index=[df_full.index[0]])
    equity_h009  = INITIAL_EQUITY
    h009_eq_list = [(df_full.index[0], equity_h009)]
    h009_ibs     = df_full["ibs"].values
    h009_closes  = df_full["close"].values
    h009_opens   = df_full["open"].values
    h009_dates   = list(df_full.index)
    position_h9  = 0
    dh           = 0
    h009_trades  = []

    for i in range(1, len(df_full)):
        prev_ibs = h009_ibs[i - 1]
        if position_h9 == 1:
            dh += 1
            ret_cc = h009_closes[i] / h009_closes[i - 1] - 1
            equity_h009 *= (1 + ret_cc)
            if prev_ibs > IBS_SELL or dh >= MAX_HOLD:
                h009_trades.append({"win": int(ret_cc > 0), "trade_ret_pct": round(ret_cc * 100, 4), "gap_pct": 0.0})
                position_h9 = 0
                dh = 0
        else:
            if prev_ibs < IBS_BUY:
                position_h9 = 1
                dh = 1
                ret_cc = h009_closes[i] / h009_closes[i - 1] - 1
                equity_h009 *= (1 + ret_cc)
        h009_eq_list.append((h009_dates[i], equity_h009))

    eq_h009s = pd.Series(
        [v for _, v in h009_eq_list],
        index=pd.DatetimeIndex([d for d, _ in h009_eq_list]),
    )
    s_h009 = compute_stats(eq_h009s, h009_trades, "H009 IBS (full)", n_years_full)

    rows_table = [
        ("H036 gap < -0.5% (full)",  results["threshold_0.5pct"]["full_period"]),
        ("H036 gap < -1.0% (full)",  results["threshold_1.0pct"]["full_period"]),
        ("H009 IBS < 0.20  (full)",  s_h009),
    ]
    for name, s in rows_table:
        print(
            f"  {name:<30} {s['cagr_pct']:>8.3f} {s['sharpe']:>8.4f}"
            f" {s['max_dd_pct']:>8.3f} {s['trades_per_year']:>10.1f}"
            f" {s['win_rate_pct']:>7.2f}"
        )

    # ── 6. Build and save JSON ────────────────────────────────────────────────
    # Strip internal equity curve objects before serialising
    for k in results:
        results[k].pop("_eq_full", None)
        results[k].pop("_dr_full", None)
        results[k].pop("_dr_is",   None)
        results[k].pop("_dr_oos",  None)

    output = {
        "strategy":    "H036 — Overnight Gap Mean-Reversion (SPY)",
        "concept":     ("Buy SPY at open when it gaps down ≥ threshold vs prior close. "
                        "Hold until close. Profit from intraday gap-fill tendency."),
        "rules": {
            "entry":         "Buy at Open[t]",
            "exit":          "Sell at Close[t] (same day)",
            "position_size": "100% of capital",
            "signal_A":      "gap = (Open[t] - Close[t-1]) / Close[t-1] < -0.5%",
            "signal_B":      "gap = (Open[t] - Close[t-1]) / Close[t-1] < -1.0%",
        },
        "periods": {
            "full":    f"{FULL_START} → {FULL_END}",
            "IS":      f"{FULL_START} → {IS_END}",
            "OOS":     f"{OOS_START} → {FULL_END}",
        },
        "results": {
            "threshold_0.5pct": results["threshold_0.5pct"],
            "threshold_1.0pct": results["threshold_1.0pct"],
        },
        "h009_comparison": s_h009,
        "h036_h009_correlation": corr_data,
        "run_date": FULL_END,
    }

    # Convert any numpy types for JSON serialisation
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return str(obj)

    out_path = RESULTS_DIR / "h036_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=_json_safe))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
