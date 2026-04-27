"""
H037 — H009 IBS Mean-Reversion with Gap-Down Exclusion Filter
==============================================================

H009 recap:
  Buy SPY at open when yesterday's IBS < 0.20.
  Sell when today's IBS > 0.80 OR held >= 5 days.
  Full-period Sharpe 0.846, OOS Sharpe 0.655.

H037 modification:
  Keep all H009 rules identical, but add one extra entry filter:
  Do NOT enter if today's gap-down is < -1.0%
  (i.e., today opened more than 1% below yesterday's close).

  Hypothesis: large gap-down opens on low-IBS days signal capitulation
  continuation, not mean-reversion. Filtering them out should improve
  win rate and reduce drawdown.

H037b variant:
  Same as H037 but with -0.5% gap exclusion threshold.

Variants tested:
  H009    — baseline (no gap filter)
  H037    — exclude if gap < -1.0%
  H037b   — exclude if gap < -0.5%

Gap = (Open[t] - Close[t-1]) / Close[t-1]

Periods:
  Full:  2003-01-01 → 2026-04-27   (matches H009 standard period)
  OOS:   2017-01-01 → 2026-04-27

Outputs:
  /workspace/agent/backtesting/results/h037_results.json
  /workspace/agent/backtesting/daily/run_h037.py  (this file)
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
DATA_START  = "2000-01-01"   # download from 2000 for warmup
FULL_START  = "2003-01-01"   # analysis start
FULL_END    = "2026-04-27"
OOS_START   = "2017-01-01"

IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5

INITIAL_EQUITY = 100_000.0

CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULTS_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_spy_ohlc(start: str, end: str) -> pd.DataFrame:
    """Fetch SPY OHLC from yfinance, with parquet cache."""
    # Reuse existing h031 cache if it covers the range
    cached = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
    if cached.exists():
        df = pd.read_parquet(cached)
        print(f"  Loaded SPY OHLC from existing cache ({len(df)} rows)")
        return df

    key = f"h037_spy_ohlc_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h037_{h}.parquet"

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


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add derived columns. No look-ahead.
      ibs[t]   = (Close[t] - Low[t]) / (High[t] - Low[t])
      gap[t]   = (Open[t] - Close[t-1]) / Close[t-1]
    """
    df = df.copy()
    denom         = (df["high"] - df["low"]).replace(0, np.nan)
    df["ibs"]     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0)
    df["prev_close"] = df["close"].shift(1)
    df["gap"]     = (df["open"] - df["prev_close"]) / df["prev_close"]
    return df.dropna(subset=["prev_close", "ibs", "gap"])


# ─────────────────────────────────────────────────────────────────────────────
# Backtest engine
# ─────────────────────────────────────────────────────────────────────────────

def run_h009_variant(
    df: pd.DataFrame,
    gap_filter: float | None = None,
    label: str = "H009",
) -> tuple:
    """
    Simulate H009 (or a gap-filtered variant).

    Entry: at open[t] if ibs[t-1] < IBS_BUY
           AND (gap_filter is None OR gap[t] >= gap_filter)
    Exit:  at close[t] when ibs[t] > IBS_SELL OR days_held >= MAX_HOLD

    P&L approximation:
      Entry day:    open-to-close return = close[t]/open[t] - 1
      Hold days:    close-to-close return = close[t]/close[t-1] - 1
      Exit day:     same as hold day (exit at close)

    We also track:
      - filtered_trades: trades that were skipped due to the gap filter
        (these would have been entered under H009 rules)

    Returns:
      equity_series   : daily equity curve (pd.Series, indexed by date)
      trades          : list of completed-trade dicts
      filtered_trades : list of skipped-trade entry dicts (gap was too bad)
    """
    dates      = list(df.index)
    opens      = df["open"].values
    closes     = df["close"].values
    ibs_vals   = df["ibs"].values
    gap_vals   = df["gap"].values
    n          = len(df)

    equity     = INITIAL_EQUITY
    position   = 0       # 0=flat, 1=long
    days_held  = 0
    entry_open = 0.0
    entry_idx  = 0

    equity_list     = []
    trades          = []
    filtered_trades = []

    # Accumulators for the current open trade
    trade_daily_rets = []

    for i in range(1, n):
        date     = dates[i]
        prev_ibs = ibs_vals[i - 1]
        cur_ibs  = ibs_vals[i]
        gap      = gap_vals[i]
        o        = opens[i]
        c        = closes[i]
        c_prev   = closes[i - 1]

        # Intraday return (open→close)
        ret_oc = c / o - 1 if o > 0 else 0.0
        # Close-to-close return
        ret_cc = c / c_prev - 1 if c_prev > 0 else 0.0

        if position == 0:
            # Check entry signal
            if prev_ibs < IBS_BUY:
                # Would H009 enter here?
                would_enter = True
                if gap_filter is not None and gap < gap_filter:
                    # Gap is too deep — filter this trade
                    filtered_trades.append({
                        "date":        str(date.date()),
                        "gap_pct":     round(float(gap) * 100, 4),
                        "prev_ibs":    round(float(prev_ibs), 4),
                    })
                    would_enter = False

                if would_enter:
                    position   = 1
                    days_held  = 1
                    entry_open = o
                    entry_idx  = i
                    trade_daily_rets = [ret_oc]
                    equity    *= (1 + ret_oc)

        else:
            # Already in a position — apply hold return (close-to-close)
            days_held += 1
            trade_daily_rets.append(ret_cc)
            equity    *= (1 + ret_cc)

            # Check exit
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                # Compute trade stats
                total_ret = float(closes[i]) / float(opens[entry_idx]) - 1
                win       = int(total_ret > 0)
                trades.append({
                    "date_entry":    str(dates[entry_idx].date()),
                    "date_exit":     str(date.date()),
                    "days_held":     days_held,
                    "gap_pct":       round(float(gap_vals[entry_idx]) * 100, 4),
                    "prev_ibs":      round(float(ibs_vals[entry_idx - 1]), 4),
                    "entry_open":    round(float(opens[entry_idx]), 4),
                    "exit_close":    round(float(c), 4),
                    "trade_ret_pct": round(total_ret * 100, 4),
                    "win":           win,
                    "exit_reason":   "ibs" if cur_ibs > IBS_SELL else "maxhold",
                })
                position  = 0
                days_held = 0
                trade_daily_rets = []

        equity_list.append((date, equity))

    eq_series = pd.Series(
        [v for _, v in equity_list],
        index=pd.DatetimeIndex([d for d, _ in equity_list]),
        name="equity",
    )
    return eq_series, trades, filtered_trades


# ─────────────────────────────────────────────────────────────────────────────
# Statistics
# ─────────────────────────────────────────────────────────────────────────────

def compute_stats(
    eq: pd.Series,
    trades: list,
    label: str,
    n_years_override: float | None = None,
) -> dict:
    """Compute CAGR, Sharpe, MaxDD, win rate, avg trade P&L, trade count."""
    if eq.empty or len(eq) < 2:
        return {"period": label, "error": "insufficient data"}

    n_years = n_years_override if n_years_override is not None else len(eq) / 252.0

    # CAGR
    cagr = (eq.iloc[-1] / INITIAL_EQUITY) ** (1.0 / n_years) - 1 if n_years > 0 else 0.0

    # Sharpe — use daily equity pct-change (0 on non-trade days)
    daily_rets = eq.pct_change().dropna()
    if len(daily_rets) > 1 and daily_rets.std() > 0:
        sharpe = float(daily_rets.mean() / daily_rets.std() * math.sqrt(252))
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
    else:
        win_rate = 0.0
        avg_ret  = 0.0

    trades_per_year = n_trades / n_years if n_years > 0 else 0.0

    return {
        "period":             label,
        "n_years":            round(n_years, 1),
        "cagr_pct":           round(float(cagr) * 100, 3),
        "sharpe":             round(sharpe, 4),
        "max_dd_pct":         round(max_dd * 100, 3),
        "n_trades":           n_trades,
        "trades_per_year":    round(trades_per_year, 1),
        "win_rate_pct":       round(win_rate * 100, 2),
        "avg_trade_ret_pct":  round(avg_ret, 4),
        "final_equity":       round(float(eq.iloc[-1]), 2),
    }


def filtered_trade_stats(filtered: list, label: str) -> dict:
    """Summarise the trades that were excluded by the gap filter."""
    n = len(filtered)
    if n == 0:
        return {"label": label, "n_filtered": 0}
    avg_gap = sum(t["gap_pct"] for t in filtered) / n
    return {
        "label":        label,
        "n_filtered":   n,
        "avg_gap_pct":  round(avg_gap, 4),
        "sample":       filtered[:5],   # first 5 examples
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 72)
    print("H037 — H009 IBS with Gap-Down Exclusion Filter")
    print("=" * 72)

    # ── 1. Load data ──────────────────────────────────────────────────────────
    print("\n[1] Fetching SPY OHLC …")
    df_raw = fetch_spy_ohlc(DATA_START, FULL_END)
    df     = build_features(df_raw)
    print(f"    Data range: {df.index[0].date()} → {df.index[-1].date()}  ({len(df)} trading days)")

    # ── 2. Slice analysis windows ─────────────────────────────────────────────
    df_full = df.loc[FULL_START:FULL_END]
    df_oos  = df.loc[OOS_START:FULL_END]

    n_years_full = len(df_full) / 252.0
    n_years_oos  = len(df_oos)  / 252.0

    print(f"    Full: {FULL_START} → {FULL_END}  ({len(df_full)} days, {n_years_full:.1f} yrs)")
    print(f"    OOS:  {OOS_START}  → {FULL_END}  ({len(df_oos)} days, {n_years_oos:.1f} yrs)")

    # ── 3. Run variants ───────────────────────────────────────────────────────
    variants = [
        ("H009",  None,   "Baseline — no gap filter"),
        ("H037",  -0.010, "Exclude gap < -1.0%"),
        ("H037b", -0.005, "Exclude gap < -0.5%"),
    ]

    all_results = {}

    for tag, gap_filter, description in variants:
        print(f"\n[{'2' if tag == 'H009' else '3' if tag == 'H037' else '4'}] {tag}: {description}")

        # Full period
        eq_full, tr_full, filt_full = run_h009_variant(df_full, gap_filter, tag)
        s_full = compute_stats(eq_full, tr_full, f"Full {FULL_START}–{FULL_END}", n_years_full)

        # OOS period — restart equity at INITIAL_EQUITY for comparable Sharpe
        eq_oos, tr_oos, filt_oos = run_h009_variant(df_oos, gap_filter, tag)
        s_oos  = compute_stats(eq_oos,  tr_oos,  f"OOS  {OOS_START}–{FULL_END}",  n_years_oos)

        # Filtered-trade summary (full period only)
        filt_summary = filtered_trade_stats(filt_full, f"{tag} full-period filtered")

        print(f"    Full: CAGR {s_full['cagr_pct']:.2f}%  Sharpe {s_full['sharpe']:.4f}"
              f"  MaxDD {s_full['max_dd_pct']:.2f}%  Trades {s_full['n_trades']}"
              f"  WinRate {s_full['win_rate_pct']:.1f}%  AvgPnL {s_full['avg_trade_ret_pct']:.4f}%")
        print(f"    OOS:  CAGR {s_oos['cagr_pct']:.2f}%  Sharpe {s_oos['sharpe']:.4f}"
              f"  MaxDD {s_oos['max_dd_pct']:.2f}%  Trades {s_oos['n_trades']}"
              f"  WinRate {s_oos['win_rate_pct']:.1f}%  AvgPnL {s_oos['avg_trade_ret_pct']:.4f}%")
        if filt_summary["n_filtered"] > 0:
            print(f"    Filtered (excluded) trades: {filt_summary['n_filtered']}"
                  f"  avg gap {filt_summary['avg_gap_pct']:.3f}%")

        all_results[tag] = {
            "description":         description,
            "gap_filter_pct":      None if gap_filter is None else round(gap_filter * 100, 1),
            "full_period":         s_full,
            "oos_period":          s_oos,
            "filtered_trade_summary": filt_summary,
        }

    # ── 4. Now compute the actual avg return of filtered trades ──────────────
    # Re-run: for each filtered gap-down entry, what would the trade have returned?
    # We simulate H009 on just the filtered days to get actual P&L.
    print("\n[5] Computing actual P&L of filtered-out trades …")

    for tag, gap_filter, _ in variants:
        if gap_filter is None:
            all_results[tag]["filtered_actual_pnl"] = "N/A — no filter applied"
            continue

        # Find all entries that H009 would make AND the gap crosses the threshold
        filtered_returns = []
        dates    = list(df_full.index)
        opens    = df_full["open"].values
        closes   = df_full["close"].values
        ibs_vals = df_full["ibs"].values
        gap_vals = df_full["gap"].values
        n        = len(df_full)

        # Track H009 position to know when entries would happen
        position  = 0
        days_held = 0

        for i in range(1, n):
            prev_ibs = ibs_vals[i - 1]
            cur_ibs  = ibs_vals[i]
            gap      = gap_vals[i]

            if position == 0:
                if prev_ibs < IBS_BUY:
                    if gap < gap_filter:
                        # This is a filtered entry — compute what H009 would have earned
                        # We simulate the full H009 trade from this entry point
                        equity_sim  = 1.0
                        sim_entry_open = opens[i]
                        sim_days    = 1
                        # Entry day: open→close
                        equity_sim *= closes[i] / opens[i]

                        # Continue holding
                        j = i + 1
                        while j < n and sim_days < MAX_HOLD:
                            sim_days += 1
                            equity_sim *= closes[j] / closes[j - 1]
                            if ibs_vals[j] > IBS_SELL or sim_days >= MAX_HOLD:
                                break
                            j += 1

                        trade_ret = equity_sim - 1.0
                        filtered_returns.append({
                            "date_entry":    str(dates[i].date()),
                            "gap_pct":       round(float(gap) * 100, 4),
                            "prev_ibs":      round(float(prev_ibs), 4),
                            "trade_ret_pct": round(trade_ret * 100, 4),
                            "win":           int(trade_ret > 0),
                            "days_held":     sim_days,
                        })
                        # Don't enter (this is the filtered variant) — stay flat
                    else:
                        # Normal entry
                        position  = 1
                        days_held = 1
            else:
                days_held += 1
                if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                    position  = 0
                    days_held = 0

        n_filt    = len(filtered_returns)
        if n_filt > 0:
            avg_ret   = sum(t["trade_ret_pct"] for t in filtered_returns) / n_filt
            wins      = sum(t["win"] for t in filtered_returns)
            win_rate  = wins / n_filt * 100
            avg_gap   = sum(t["gap_pct"] for t in filtered_returns) / n_filt
        else:
            avg_ret = win_rate = avg_gap = 0.0

        print(f"    {tag} filtered trades: n={n_filt}  avg_ret={avg_ret:.4f}%"
              f"  win_rate={win_rate:.1f}%  avg_gap={avg_gap:.3f}%")

        all_results[tag]["filtered_actual_pnl"] = {
            "n_filtered_trades":     n_filt,
            "avg_trade_ret_pct":     round(avg_ret, 4),
            "win_rate_pct":          round(win_rate, 2),
            "avg_gap_pct":           round(avg_gap, 4),
            "all_filtered_trades":   filtered_returns,
        }

    # ── 5. Summary comparison table ───────────────────────────────────────────
    print("\n" + "=" * 90)
    print("  H037 SUMMARY: H009 Baseline vs Gap Exclusion Variants")
    print("=" * 90)

    for period_key, period_label in [("full_period", "FULL PERIOD (2003–2026)"), ("oos_period", "OOS (2017–2026)")]:
        print(f"\n  {period_label}")
        print(f"  {'Strategy':<20}  {'CAGR%':>7}  {'Sharpe':>7}  {'MaxDD%':>7}  {'Trades':>7}  {'WinRate%':>9}  {'AvgPnL%':>9}  {'Filtered':>9}")
        print("  " + "-" * 86)
        for tag, gap_filter, desc in variants:
            s  = all_results[tag][period_key]
            gf = all_results[tag]["gap_filter_pct"]
            fa = all_results[tag].get("filtered_actual_pnl", {})
            n_filt_full = all_results[tag]["filtered_trade_summary"]["n_filtered"]
            print(
                f"  {tag:<20}  {s['cagr_pct']:>7.2f}  {s['sharpe']:>7.4f}  "
                f"{s['max_dd_pct']:>7.2f}  {s['n_trades']:>7}  "
                f"{s['win_rate_pct']:>9.2f}  {s['avg_trade_ret_pct']:>9.4f}  "
                f"{n_filt_full:>9}"
            )

    print("\n  FILTERED TRADE QUALITY (Full Period, trades excluded by filter):")
    print(f"  {'Strategy':<20}  {'N filtered':>10}  {'AvgRet%':>9}  {'WinRate%':>9}  {'AvgGap%':>9}")
    print("  " + "-" * 62)
    for tag, gap_filter, _ in variants:
        if gap_filter is None:
            print(f"  {tag:<20}  {'N/A (no filter)':>40}")
            continue
        fa = all_results[tag].get("filtered_actual_pnl", {})
        if isinstance(fa, str):
            continue
        print(
            f"  {tag:<20}  {fa['n_filtered_trades']:>10}  "
            f"{fa['avg_trade_ret_pct']:>9.4f}  "
            f"{fa['win_rate_pct']:>9.2f}  "
            f"{fa['avg_gap_pct']:>9.4f}"
        )

    # ── 6. Save results ───────────────────────────────────────────────────────
    def _json_safe(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        return str(obj)

    output = {
        "strategy":   "H037 — H009 IBS Mean-Reversion with Gap-Down Exclusion Filter",
        "hypothesis": (
            "Large gap-down opens on low-IBS days signal capitulation continuation, "
            "not mean-reversion. Filtering them out should improve win rate and reduce drawdown."
        ),
        "rules": {
            "base":       "H009: IBS[t-1] < 0.20 → buy at open; exit when IBS > 0.80 or held 5 days",
            "H037":       "H009 + skip entry if gap < -1.0%",
            "H037b":      "H009 + skip entry if gap < -0.5%",
            "gap_def":    "gap[t] = (Open[t] - Close[t-1]) / Close[t-1]",
        },
        "periods": {
            "full":  f"{FULL_START} → {FULL_END}",
            "oos":   f"{OOS_START} → {FULL_END}",
        },
        "results":   all_results,
        "run_date":  FULL_END,
    }

    out_path = RESULTS_DIR / "h037_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=_json_safe))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
