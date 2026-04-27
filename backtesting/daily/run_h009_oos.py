"""
H009 IBS Mean-Reversion Strategy — In-Sample / Out-of-Sample Backtest
=======================================================================
Strategy:
  - IBS = (Close - Low) / (High - Low)
  - Buy next open if yesterday IBS < 0.20
  - Sell next open if yesterday IBS > 0.80 OR held >= 5 days
  - 100% capital when in position (full allocation)
  - No transaction costs

Signal note: both buy and sell use PREVIOUS day's IBS (end-of-day signal,
execute at next open) — no look-ahead bias.

Hold-day counting: hold_days = 0 at entry open, incremented at start of each
subsequent day. Force-exit fires when hold_days >= MAX_HOLD (i.e., at open of
entry + MAX_HOLD days), giving 5 full trading days of exposure.

Periods:
  - In-Sample  (IS):  2003-01-01 to 2016-12-31
  - Out-of-Sample (OOS): 2017-01-01 to 2026-04-25

Run:
  python3 run_h009_oos.py
"""

import json
import math
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────────
TICKER    = "SPY"
IS_START  = "2003-01-01"
IS_END    = "2016-12-31"
OOS_START = "2017-01-01"
OOS_END   = "2026-04-25"
IBS_BUY   = 0.20
IBS_SELL  = 0.80
MAX_HOLD  = 5

OUTPUT_JSON = Path("/workspace/agent/backtesting/results/h009_oos_results.json")

# ── Download data ───────────────────────────────────────────────────────────────
print("Downloading SPY data...")
raw = yf.download(TICKER, start="2002-12-01", end="2026-04-26", auto_adjust=True, progress=False)
raw.columns = raw.columns.get_level_values(0) if isinstance(raw.columns, pd.MultiIndex) else raw.columns
raw.index = pd.to_datetime(raw.index)
raw = raw[["Open", "High", "Low", "Close"]].dropna()
raw["IBS"] = (raw["Close"] - raw["Low"]) / (raw["High"] - raw["Low"])

print(f"Data loaded: {raw.index[0].date()} to {raw.index[-1].date()} ({len(raw)} rows)")

# Flatten to DataFrame with Date column
df_all_raw = raw.reset_index()
df_all_raw.rename(columns={df_all_raw.columns[0]: "Date"}, inplace=True)


# ── Core backtest ───────────────────────────────────────────────────────────────
def run_backtest(df: pd.DataFrame):
    """
    Backtest H009 on a DataFrame with columns [Date, Open, High, Low, Close, IBS].

    Signal logic (no look-ahead):
      - BUY:  if prev_ibs < IBS_BUY  → buy at today's open
      - SELL: if prev_ibs > IBS_SELL OR hold_days >= MAX_HOLD → sell at today's open

    Returns (stats dict, trades list, equity Series).
    """
    df = df.reset_index(drop=True)
    n = len(df)

    capital = 1.0
    shares = 0.0
    in_position = False
    hold_days = 0
    entry_price = 0.0
    entry_date = None
    trades = []
    equity = np.zeros(n)
    equity[0] = capital  # start in cash

    for i in range(1, n):
        today_open  = df.loc[i, "Open"]
        today_close = df.loc[i, "Close"]
        today_date  = df.loc[i, "Date"]
        prev_ibs    = df.loc[i - 1, "IBS"]  # yesterday's IBS — no look-ahead

        if in_position:
            hold_days += 1  # day 1 = first full day after entry open
            # Sell: yesterday's IBS > threshold OR max hold reached
            if prev_ibs > IBS_SELL or hold_days >= MAX_HOLD:
                pnl = (today_open - entry_price) / entry_price
                capital = shares * today_open
                shares = 0.0
                in_position = False
                trades.append({
                    "entry_date":  str(entry_date)[:10],
                    "exit_date":   str(today_date)[:10],
                    "entry_price": float(entry_price),
                    "exit_price":  float(today_open),
                    "hold_days":   hold_days,
                    "pnl_pct":     round(float(pnl * 100), 4),
                    "win":         int(pnl > 0),
                })
                hold_days = 0
                equity[i] = capital
            else:
                equity[i] = shares * today_close
        else:
            # Buy: yesterday's IBS < threshold
            if prev_ibs < IBS_BUY:
                shares = capital / today_open
                entry_price = today_open
                entry_date = today_date
                capital = 0.0
                in_position = True
                hold_days = 0  # start counting from next day
                equity[i] = shares * today_close
            else:
                equity[i] = capital

    # Mark-to-market any open position at the last bar
    if in_position:
        last_close = df.loc[n - 1, "Close"]
        last_date  = df.loc[n - 1, "Date"]
        pnl = (last_close - entry_price) / entry_price
        capital = shares * last_close
        trades.append({
            "entry_date":  str(entry_date)[:10],
            "exit_date":   str(last_date)[:10],
            "entry_price": float(entry_price),
            "exit_price":  float(last_close),
            "hold_days":   hold_days,
            "pnl_pct":     round(float(pnl * 100), 4),
            "win":         int(pnl > 0),
            "open_at_end": True,
        })
        equity[n - 1] = capital

    eq = pd.Series(equity, index=df["Date"])
    return eq, trades


# ── Stats ───────────────────────────────────────────────────────────────────────
def compute_stats(eq: pd.Series, trades: list, label: str) -> dict:
    dr = eq.pct_change().dropna()
    years = len(eq) / 252
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1 if years > 0 else 0.0
    sharpe = float((dr.mean() / dr.std()) * math.sqrt(252)) if dr.std() > 0 else 0.0
    mdd = float(((eq - eq.cummax()) / eq.cummax()).min())
    nt = len(trades)
    wr = sum(t["win"] for t in trades) / nt * 100 if nt else 0.0
    ah = sum(t["hold_days"] for t in trades) / nt if nt else 0.0
    ap = sum(t["pnl_pct"] for t in trades) / nt if nt else 0.0
    return {
        "period":        label,
        "start":         str(eq.index[0].date()),
        "end":           str(eq.index[-1].date()),
        "cagr_pct":      round(float(cagr * 100), 3),
        "sharpe":        round(sharpe, 4),
        "max_dd_pct":    round(mdd * 100, 3),
        "n_trades":      nt,
        "win_rate_pct":  round(wr, 2),
        "avg_hold_days": round(ah, 2),
        "avg_pnl_pct":   round(float(ap), 3),
        "final_equity":  round(float(eq.iloc[-1]), 6),
    }


# ── Slice periods and run ───────────────────────────────────────────────────────
df_is  = df_all_raw[(df_all_raw["Date"] >= IS_START)  & (df_all_raw["Date"] <= IS_END)]
df_oos = df_all_raw[(df_all_raw["Date"] >= OOS_START) & (df_all_raw["Date"] <= OOS_END)]
df_all = df_all_raw[(df_all_raw["Date"] >= IS_START)  & (df_all_raw["Date"] <= OOS_END)]

print(f"Periods — IS: {len(df_is)} rows | OOS: {len(df_oos)} rows | Full: {len(df_all)} rows")

eq_is,   tr_is   = run_backtest(df_is)
eq_oos,  tr_oos  = run_backtest(df_oos)
eq_full, tr_full = run_backtest(df_all)

s_is   = compute_stats(eq_is,   tr_is,   "IS  (2003-2016)")
s_oos  = compute_stats(eq_oos,  tr_oos,  "OOS (2017-2026)")
s_full = compute_stats(eq_full, tr_full, "FULL(2003-2026)")

oos_deg = (
    round((s_is["sharpe"] - s_oos["sharpe"]) / s_is["sharpe"] * 100, 2)
    if s_is["sharpe"] != 0 else None
)


# ── Print summary table ─────────────────────────────────────────────────────────
H   = f"{'Period':<22} {'CAGR%':>8} {'Sharpe':>8} {'MaxDD%':>8} {'#Trades':>8} {'Win%':>7} {'AvgHold':>8} {'AvgPnL%':>9}"
SEP = "-" * len(H)
print()
print("=" * len(H))
print("  H009 IBS MEAN-REVERSION — IS / OOS BACKTEST  (SPY)")
print("=" * len(H))
print(H)
print(SEP)
for s in [s_is, s_oos, s_full]:
    print(
        f"{s['period']:<22} {s['cagr_pct']:>8.2f} {s['sharpe']:>8.4f} {s['max_dd_pct']:>8.2f}"
        f" {s['n_trades']:>8} {s['win_rate_pct']:>7.2f} {s['avg_hold_days']:>8.2f} {s['avg_pnl_pct']:>9.3f}"
    )
print(SEP)
if oos_deg is not None:
    print(
        f"\n  OOS Sharpe degradation: {oos_deg:.2f}%"
        f"  (IS {s_is['sharpe']:.4f} → OOS {s_oos['sharpe']:.4f})"
    )
print()


# ── Save JSON ───────────────────────────────────────────────────────────────────
result = {
    "strategy": "H009_IBS",
    "ticker": TICKER,
    "rules": {
        "ibs_buy_threshold": IBS_BUY,
        "ibs_sell_threshold": IBS_SELL,
        "max_hold_days": MAX_HOLD,
        "allocation_pct": 100,
        "transaction_costs": False,
        "signal_note": (
            "Both buy and sell use PREVIOUS day IBS (no look-ahead). "
            "hold_days = 0 at entry open; force-exit at open when hold_days >= MAX_HOLD "
            "(i.e., 5 full sessions)."
        ),
    },
    "in_sample":          s_is,
    "out_of_sample":      s_oos,
    "full_period":        s_full,
    "oos_degradation_pct": oos_deg,
    "is_trades":          tr_is,
    "oos_trades":         tr_oos,
}

OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
with open(OUTPUT_JSON, "w") as f:
    json.dump(result, f, indent=2, default=str)

print(f"Results saved → {OUTPUT_JSON}")
