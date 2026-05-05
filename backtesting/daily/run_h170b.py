"""
H170b — 0DTE SPY Iron Condor (Near-Close Entry, 3:55 PM)
=========================================================
Strategy: At 3:55 PM on each 0DTE expiration day, sell a 16-delta iron condor
on SPY (short call spread + short put spread), $0.50-wide wings, expire at 4:00 PM.

Phase 1 (this script): Uses yfinance 5-minute bars — covers the last 60 calendar
days. Actual 3:55 PM SPY price and 4:00 PM close used.

Phase 2 (needs ThetaData): Real options bid/ask, actual delta quotes, longer history.

Simulation note: BS model prices the condor at entry. Wings are $0.50 wide on SPY.
16-delta strikes derived from VIX-implied σ at T=5min (5/98280 years).

P&L per condor ($0.50 wings, 1 contract = 100 shares):
  Win:  +credit × 100
  Lose: -(0.50 - credit) × 100  [if SPY close outside short strikes]

Confirm criteria: Sharpe > 0.5, MaxDD < -25%, CAGR > 5%, WinRate > 55%
"""

import sys
import math
import warnings
from datetime import datetime, timedelta, time as dt_time
import pandas as pd
import numpy as np
from scipy.stats import norm

warnings.filterwarnings("ignore")

# ── constants ──────────────────────────────────────────────────────────────────
WING_WIDTH = 2.50          # $2.50 wide wings on SPY (≈$25 on SPX, more realistic)
SHARES_PER_CONTRACT = 100
RISK_FREE = 0.045          # approximate, static
T_ENTRY_MIN = 5            # minutes before close
TRADING_MINS_PER_DAY = 390
TRADING_DAYS_PER_YEAR = 252
T_YEARS = T_ENTRY_MIN / (TRADING_MINS_PER_DAY * TRADING_DAYS_PER_YEAR)

# ── Black-Scholes helpers ──────────────────────────────────────────────────────

def bs_call(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)

def bs_put(S, K, T, r, sigma):
    return bs_call(S, K, T, r, sigma) - S + K * math.exp(-r * T)

def find_delta_strike(S, T, r, sigma, target_delta, option_type='call'):
    """Binary search for strike with given |delta|."""
    lo, hi = S * 0.5, S * 1.5
    for _ in range(60):
        mid = (lo + hi) / 2
        d1 = (math.log(S / mid) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        delta = norm.cdf(d1) if option_type == 'call' else norm.cdf(d1) - 1
        if option_type == 'call':
            if delta > target_delta:
                lo = mid
            else:
                hi = mid
        else:
            if delta < target_delta:
                hi = mid
            else:
                lo = mid
    return (lo + hi) / 2

def condor_credit(S, T, r, sigma, wing):
    """BS credit for 16-delta iron condor with given wing width."""
    K_call = find_delta_strike(S, T, r, sigma, 0.16, 'call')
    K_put  = find_delta_strike(S, T, r, sigma, -0.16, 'put')
    call_spread = bs_call(S, K_call, T, r, sigma) - bs_call(S, K_call + wing, T, r, sigma)
    put_spread  = bs_put(S, K_put, T, r, sigma)  - bs_put(S, K_put - wing, T, r, sigma)
    return call_spread + put_spread, K_call, K_put

def pnl(credit, K_call, K_put, S_close, wing):
    """P&L per spread unit at expiry given SPY close."""
    if K_put <= S_close <= K_call:
        return credit
    elif S_close > K_call:
        loss = min(S_close - K_call, wing)
        return credit - loss
    else:
        loss = min(K_put - S_close, wing)
        return credit - loss

# ── data download ──────────────────────────────────────────────────────────────

def fetch_data():
    import yfinance as yf

    print("Downloading SPY 5-minute bars (last 60 days)...")
    spy5 = yf.download("SPY", period="60d", interval="5m", auto_adjust=True, progress=False)
    # Flatten multi-level columns (yfinance returns ('Close','SPY') etc.)
    if isinstance(spy5.columns, pd.MultiIndex):
        spy5.columns = spy5.columns.get_level_values(0)
    spy5.index = spy5.index.tz_convert("America/New_York")

    print("Downloading ^VIX daily (2022-present)...")
    vix_raw = yf.download("^VIX", start="2022-01-01", progress=False, auto_adjust=True)["Close"]
    # Flatten multi-level if present
    if isinstance(vix_raw, pd.DataFrame):
        vix_raw = vix_raw.iloc[:, 0]
    vix = vix_raw.squeeze()
    vix.index = pd.to_datetime(vix.index)
    if hasattr(vix.index, "tz") and vix.index.tz is not None:
        vix.index = vix.index.tz_localize(None)

    print(f"SPY 5m: {len(spy5)} bars | VIX: {len(vix)} days")
    return spy5, vix

# ── expiration calendar ────────────────────────────────────────────────────────

def is_0dte_expiry(date):
    """
    SPX/SPY 0DTE expirations:
    - Before 2022-02-22: Fridays only (weekly options)
    - 2022-02-22 onwards: Mon/Wed/Fri
    """
    wd = date.weekday()  # 0=Mon, 4=Fri
    if date >= datetime(2022, 2, 22).date():
        return wd in (0, 2, 4)
    else:
        return wd == 4

# ── main simulation ────────────────────────────────────────────────────────────

def simulate(spy5, vix):
    trades = []

    # Get all unique expiry dates in the 5-minute dataset
    dates = spy5.index.normalize().unique()

    for dt in dates:
        date = dt.date()
        if not is_0dte_expiry(date):
            continue

        # Bars for this day
        day_bars = spy5[spy5.index.date == date]
        if len(day_bars) < 2:
            continue

        # 3:55 PM bar (the bar starting at 15:55 ET)
        entry_bars = day_bars[
            (day_bars.index.hour == 15) & (day_bars.index.minute == 55)
        ]
        if entry_bars.empty:
            continue

        # 4:00 PM close — use the last bar's close
        S_close = float(day_bars["Close"].iloc[-1])

        # Entry price = open of the 3:55 bar
        S_entry = float(entry_bars["Open"].iloc[0])

        # VIX on this date (use most recent available)
        date_ts = pd.Timestamp(date)
        vix_slice = vix[vix.index <= date_ts]
        if vix_slice.empty:
            continue
        iv = float(vix_slice.iloc[-1]) / 100.0

        # Price the condor
        credit, K_call, K_put = condor_credit(S_entry, T_YEARS, RISK_FREE, iv, WING_WIDTH)

        # P&L per unit at expiry
        trade_pnl = pnl(credit, K_call, K_put, S_close, WING_WIDTH)
        trade_dollar = trade_pnl * SHARES_PER_CONTRACT

        trades.append({
            "date": date,
            "S_entry": round(S_entry, 2),
            "S_close": round(S_close, 2),
            "vix": round(iv * 100, 1),
            "K_call": round(K_call, 2),
            "K_put": round(K_put, 2),
            "credit": round(credit, 4),
            "win": trade_pnl > 0,
            "pnl_unit": round(trade_pnl, 4),
            "pnl_dollar": round(trade_dollar, 2),
        })

    return pd.DataFrame(trades)

# ── metrics ────────────────────────────────────────────────────────────────────

def report(df):
    if df.empty:
        print("No trades found.")
        return

    print(f"\n{'='*60}")
    print(f"  H170b — 0DTE SPY Iron Condor (Near-Close B)")
    print(f"  Period: {df['date'].min()} → {df['date'].max()}")
    print(f"{'='*60}")

    n = len(df)
    wins = df["win"].sum()
    win_rate = wins / n * 100
    total_pnl = df["pnl_dollar"].sum()
    avg_win  = df.loc[df["win"],  "pnl_dollar"].mean() if wins > 0 else 0
    avg_loss = df.loc[~df["win"], "pnl_dollar"].mean() if (n - wins) > 0 else 0
    avg_credit = df["credit"].mean()
    avg_wing_pct = (df["credit"] / WING_WIDTH * 100).mean()

    # Daily cumulative P&L
    df_sorted = df.sort_values("date")
    cumulative = df_sorted["pnl_dollar"].cumsum()
    peak = cumulative.cummax()
    drawdown = cumulative - peak
    max_dd = drawdown.min()

    # Approximate annualized Sharpe
    annual_factor = 252  # using days, not trades — rough
    daily_pnl = df_sorted.groupby("date")["pnl_dollar"].sum()
    sharpe = (daily_pnl.mean() / daily_pnl.std() * math.sqrt(annual_factor)) if daily_pnl.std() > 0 else 0

    print(f"\n  Trades:       {n}")
    print(f"  Win rate:     {win_rate:.1f}%")
    print(f"  Total P&L:    ${total_pnl:,.2f}")
    print(f"  Avg win:      ${avg_win:,.2f}")
    print(f"  Avg loss:     ${avg_loss:,.2f}")
    print(f"  Avg credit:   ${avg_credit:.4f} ({avg_wing_pct:.1f}% of wing)")
    print(f"  Max drawdown: ${max_dd:,.2f}")
    print(f"  Sharpe (approx): {sharpe:.3f}")

    print(f"\n  Per-trade sample (last 10):")
    print(f"  {'Date':<12} {'SPY@3:55':>9} {'Close':>8} {'VIX':>5} {'KP':>7} {'KC':>7} {'Cred':>7} {'P&L':>8}")
    for _, row in df_sorted.tail(10).iterrows():
        flag = "✓" if row["win"] else "✗"
        print(f"  {flag} {row['date']}  {row['S_entry']:>8.2f} {row['S_close']:>7.2f} "
              f"{row['vix']:>4.0f}  {row['K_put']:>6.2f} {row['K_call']:>6.2f} "
              f"${row['credit']:>5.4f}  ${row['pnl_dollar']:>6.2f}")

    print(f"\n{'='*60}")
    print(f"  NOTE: BS simulation only — no real bid/ask data.")
    print(f"  Real slippage on 4-leg 0DTE ~$0.10-0.30/contract.")
    print(f"  Phase 2 needs ThetaData ($35/mo) for multi-year test.")
    print(f"{'='*60}\n")

    return df_sorted

# ── save results ───────────────────────────────────────────────────────────────

def save(df):
    out = "/workspace/agent/backtesting/results/h170b_0dte_spy_iron_condor.txt"
    lines = []
    lines.append("H170b — 0DTE SPY Iron Condor Near-Close (Variant B)")
    lines.append(f"Run: {datetime.now():%Y-%m-%d %H:%M}")
    lines.append(f"Period: {df['date'].min()} to {df['date'].max()}")
    lines.append(f"Wing: ${WING_WIDTH} | Entry delta: 16 | T: 5 min")
    lines.append("-" * 60)

    n = len(df)
    wins = df["win"].sum()
    total_pnl = df["pnl_dollar"].sum()
    cumulative = df["pnl_dollar"].cumsum()
    max_dd = (cumulative - cumulative.cummax()).min()
    daily_pnl = df.groupby("date")["pnl_dollar"].sum()
    sharpe = (daily_pnl.mean() / daily_pnl.std() * math.sqrt(252)) if daily_pnl.std() > 0 else 0

    lines.append(f"Trades:       {n}")
    lines.append(f"Win rate:     {wins/n*100:.1f}%")
    lines.append(f"Total P&L:    ${total_pnl:,.2f}")
    lines.append(f"Max drawdown: ${max_dd:,.2f}")
    lines.append(f"Sharpe:       {sharpe:.3f}")
    lines.append(f"Avg credit:   ${df['credit'].mean():.4f} ({df['credit'].mean()/WING_WIDTH*100:.1f}% of wing)")
    lines.append("")
    lines.append(f"{'Date':<12} {'SPY@3:55':>9} {'Close':>8} {'VIX':>5} {'KP':>7} {'KC':>7} {'Cred':>7} {'Win':>4} {'P&L':>8}")
    for _, row in df.iterrows():
        flag = "Y" if row["win"] else "N"
        lines.append(
            f"{row['date']}  {row['S_entry']:>8.2f} {row['S_close']:>7.2f} "
            f"{row['vix']:>4.0f}  {row['K_put']:>6.2f} {row['K_call']:>6.2f} "
            f"${row['credit']:>5.4f}   {flag}  ${row['pnl_dollar']:>6.2f}"
        )

    with open(out, "w") as f:
        f.write("\n".join(lines))
    print(f"Results saved: {out}")

# ── entry ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    spy5, vix = fetch_data()
    df = simulate(spy5, vix)
    if not df.empty:
        df_sorted = report(df)
        save(df_sorted)
    else:
        print("No qualifying trades in data window.")
        sys.exit(1)
