"""
H234: Weekly Inside-Bar Breakout (Coiled Spring Momentum)
Source: Stats Edge Trading — "The 25-Year Backtest" (Michael Nauss CMT/CAIA/CDMS)

Signal logic (weekly bars):
  Week W-1 ("green bar"): weekly return > GREEN_THRESH AND volume > 1.5× 20-wk avg
                           AND close in upper 60% of the week's own range
  Week W ("inside bar"):   high < W-1 high AND low > W-1 low
                           AND close in upper 50% of W-1 bar's range
  Entry: open of week W+1 (proxied as Friday close of W, no gap adjustment)
  Exit:  close of week W+1 (1-week hold)
  Stop:  implicit — modeled as 1-week hold only (no intraweek stop on weekly bars)

Universe: S&P 500 large-cap subset (top ~150 by market cap, avoids delisting issues)
Data: yfinance weekly OHLCV
IS:  2013-01-01 to 2020-12-31
OOS: 2021-01-01 to 2026-05-23
TC:  0.10% round-trip per trade
"""

import pandas as pd
import numpy as np
import yfinance as yf
import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

# ── Parameters ────────────────────────────────────────────────────────────────
GREEN_THRESH   = 0.025   # min weekly return for the "green bar" (2.5%)
VOL_MULT       = 1.5     # volume must be > 1.5× 20-week rolling average
GREEN_CLOSE_FRAC = 0.60  # green bar close must be in top 40% of its range
INSIDE_UPPER_FRAC = 0.50 # inside bar close in upper 50% of green bar range
TC             = 0.001   # 0.10% round-trip transaction cost
MAX_POSITIONS  = 10      # max concurrent positions (equal-weight)

IS_START  = "2013-01-01"
IS_END    = "2020-12-31"
OOS_START = "2021-01-01"
OOS_END   = "2026-05-23"

CONFIRM_SHARPE = 1.40  # confirmation threshold

# ── Universe ──────────────────────────────────────────────────────────────────
TICKERS = [
    # Mega-cap tech
    "AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AVGO","ORCL","ADBE",
    # Financials
    "JPM","BAC","WFC","GS","MS","BLK","SCHW","AXP","V","MA",
    # Healthcare
    "UNH","JNJ","LLY","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN",
    # Industrials / Consumer
    "HD","MCD","COST","WMT","PG","KO","PEP","NKE","SBUX","DIS",
    # Energy / Materials
    "XOM","CVX","COP","SLB","EOG","LIN","APD","NEM","FCX","MOS",
    # Semis / Hardware
    "AMD","QCOM","TXN","AMAT","LRCX","KLAC","MU","INTC","ON","MRVL",
    # Software / Cloud
    "CRM","NOW","SNOW","PANW","ZS","CRWD","DDOG","NET","WDAY","MDB",
    # ETFs for broader market exposure
    "SPY","QQQ","IWM","XLF","XLE","XLK","XLV","XLI","XLP","XLU",
    # More large caps
    "BRK-B","LMT","RTX","CAT","DE","MMM","HON","GE","BA","UPS",
    "NFLX","PYPL","SQ","SHOP","UBER","ABNB","LYFT","DASH","COIN","MSTR",
    "T","VZ","TMUS","CMCSA","CHTR","DISH","LUMN","PARA","WBD","FOX",
]
TICKERS = list(dict.fromkeys(TICKERS))  # deduplicate

def download_weekly(tickers, start, end):
    """Download weekly OHLCV for all tickers, return dict of DataFrames."""
    print(f"Downloading weekly data for {len(tickers)} tickers...")
    raw = yf.download(
        tickers, start=start, end=end,
        interval="1wk", auto_adjust=True, progress=False
    )
    prices = {}
    for ticker in tickers:
        try:
            if len(tickers) == 1:
                df = raw[["Open","High","Low","Close","Volume"]].copy()
            else:
                df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close","Volume"]].copy()
            df = df.dropna(how="all")
            if len(df) > 100:
                prices[ticker] = df
        except Exception:
            pass
    print(f"  {len(prices)} tickers with sufficient data.")
    return prices

def generate_signals(prices):
    """For each ticker, generate weekly signals. Returns list of (date, ticker) tuples."""
    signals = []
    for ticker, df in prices.items():
        df = df.copy()
        df["ret"] = df["Close"].pct_change()
        df["vol_avg"] = df["Volume"].rolling(20).mean()
        df["range"] = df["High"] - df["Low"]
        df["close_frac"] = (df["Close"] - df["Low"]) / (df["range"] + 1e-8)

        for i in range(2, len(df) - 1):
            # Green bar conditions (week W-1)
            g = df.iloc[i - 1]
            g_range = g["High"] - g["Low"]
            if g_range <= 0:
                continue
            if g["ret"] < GREEN_THRESH:
                continue
            if g["Volume"] < VOL_MULT * g["vol_avg"]:
                continue
            if g["close_frac"] < GREEN_CLOSE_FRAC:
                continue

            # Inside bar conditions (week W = current bar i)
            b = df.iloc[i]
            if b["High"] >= g["High"]:
                continue
            if b["Low"] <= g["Low"]:
                continue
            # Close in upper half of green bar's range
            inside_frac = (b["Close"] - g["Low"]) / (g["High"] - g["Low"] + 1e-8)
            if inside_frac < INSIDE_UPPER_FRAC:
                continue

            # Signal: enter at open of next week (index i+1)
            entry_date = df.index[i + 1]
            signals.append((entry_date, ticker))

    return signals

def backtest(prices, signals, start, end):
    """
    Simple equal-weight backtest. Entry at week open, exit at week close.
    Max MAX_POSITIONS concurrent. No overlapping positions in same ticker.
    """
    # Build weekly date index
    all_dates = sorted(set(
        date for df in prices.values() for date in df.index
        if pd.Timestamp(start) <= date <= pd.Timestamp(end)
    ))
    if not all_dates:
        return pd.Series(dtype=float)

    # Filter signals to period
    sig_df = pd.DataFrame(signals, columns=["entry_date", "ticker"])
    sig_df = sig_df[
        (sig_df["entry_date"] >= pd.Timestamp(start)) &
        (sig_df["entry_date"] <= pd.Timestamp(end))
    ].sort_values("entry_date")

    trades = []
    open_positions = {}  # ticker -> exit_date

    for _, row in sig_df.iterrows():
        ticker = row["ticker"]
        entry_date = row["entry_date"]

        # Release any positions whose exit_date has passed
        open_positions = {t: ex for t, ex in open_positions.items() if ex > entry_date}

        if ticker in open_positions:
            continue
        if len(open_positions) >= MAX_POSITIONS:
            continue

        df = prices.get(ticker)
        if df is None:
            continue

        # Find entry and exit rows
        future = df[df.index >= entry_date]
        if len(future) < 2:
            continue

        entry_price = future.iloc[0]["Open"]
        exit_price  = future.iloc[1]["Close"] if len(future) > 1 else future.iloc[0]["Close"]
        exit_date   = future.index[1] if len(future) > 1 else future.index[0]

        if entry_price <= 0 or exit_price <= 0:
            continue

        ret = (exit_price / entry_price - 1) - TC

        trades.append({
            "entry_date": entry_date,
            "exit_date":  exit_date,
            "ticker":     ticker,
            "entry_price": entry_price,
            "exit_price":  exit_price,
            "return":      ret,
        })
        open_positions[ticker] = exit_date

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return pd.Series(dtype=float), trades_df

    # Build weekly portfolio returns
    # Weight each trade by 1/MAX_POSITIONS (equal weight, but only when active)
    # Aggregate by exit week
    trades_df["week_return"] = trades_df["return"]
    weekly = trades_df.groupby("exit_date")["week_return"].mean()  # avg return across trades that week
    # Annualize using weekly series
    return weekly, trades_df

def compute_metrics(weekly_returns):
    """Compute Sharpe, MaxDD, CAGR from weekly return series."""
    if weekly_returns.empty or len(weekly_returns) < 10:
        return {"sharpe": 0, "cagr": 0.0, "max_dd": 0.0, "n_weeks": 0, "neg_weeks": 0, "win_rate": 0.0, "n_trades": None}

    weekly = weekly_returns.dropna()
    ann_factor = np.sqrt(52)
    sharpe = (weekly.mean() / (weekly.std() + 1e-8)) * ann_factor

    cum = (1 + weekly).cumprod()
    years = len(weekly) / 52
    cagr = cum.iloc[-1] ** (1 / max(years, 0.1)) - 1

    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    neg_weeks = (weekly < 0).sum()
    n = len(weekly)

    return {
        "sharpe":    round(sharpe, 3),
        "cagr":      round(cagr, 3),
        "max_dd":    round(max_dd, 3),
        "n_weeks":   n,
        "neg_weeks": int(neg_weeks),
        "win_rate":  round((n - neg_weeks) / n, 3),
        "n_trades":  None,
    }

def main():
    # Download full history
    all_prices = download_weekly(TICKERS, start="2012-01-01", end=OOS_END)

    # Generate all signals
    print("Generating signals...")
    all_signals = generate_signals(all_prices)
    print(f"  {len(all_signals)} raw signals generated")

    # IS backtest
    print("\n── In-Sample (2013–2020) ──")
    is_weekly, is_trades = backtest(all_prices, all_signals, IS_START, IS_END)
    is_metrics = compute_metrics(is_weekly)
    is_metrics["n_trades"] = len(is_trades)
    print(f"  Trades:   {is_metrics['n_trades']}")
    print(f"  Sharpe:   {is_metrics['sharpe']}")
    print(f"  CAGR:     {is_metrics['cagr']:.1%}")
    print(f"  MaxDD:    {is_metrics['max_dd']:.1%}")
    print(f"  Win rate: {is_metrics['win_rate']:.1%}")

    # OOS backtest
    print("\n── Out-of-Sample (2021–2026) ──")
    oos_weekly, oos_trades = backtest(all_prices, all_signals, OOS_START, OOS_END)
    oos_metrics = compute_metrics(oos_weekly)
    oos_metrics["n_trades"] = len(oos_trades)
    print(f"  Trades:   {oos_metrics['n_trades']}")
    print(f"  Sharpe:   {oos_metrics['sharpe']}")
    print(f"  CAGR:     {oos_metrics['cagr']:.1%}")
    print(f"  MaxDD:    {oos_metrics['max_dd']:.1%}")
    print(f"  Win rate: {oos_metrics['win_rate']:.1%}")

    confirmed = oos_metrics["sharpe"] >= CONFIRM_SHARPE
    print(f"\n  Confirm threshold (OOS Sharpe >= {CONFIRM_SHARPE}): {'✅ CONFIRMED' if confirmed else '❌ NOT CONFIRMED'}")

    # Parameter sweep: vary GREEN_THRESH
    print("\n── Parameter sweep (green bar threshold) ──")
    sweep_results = []
    for thresh in [0.015, 0.020, 0.025, 0.030, 0.040]:
        _sigs = []
        for ticker, df in all_prices.items():
            df2 = df.copy()
            df2["ret"] = df2["Close"].pct_change()
            df2["vol_avg"] = df2["Volume"].rolling(20).mean()
            df2["range"] = df2["High"] - df2["Low"]
            df2["close_frac"] = (df2["Close"] - df2["Low"]) / (df2["range"] + 1e-8)
            for i in range(2, len(df2) - 1):
                g = df2.iloc[i - 1]
                g_range = g["High"] - g["Low"]
                if g_range <= 0: continue
                if g["ret"] < thresh: continue
                if g["Volume"] < VOL_MULT * g["vol_avg"]: continue
                if g["close_frac"] < GREEN_CLOSE_FRAC: continue
                b = df2.iloc[i]
                if b["High"] >= g["High"]: continue
                if b["Low"] <= g["Low"]: continue
                inside_frac = (b["Close"] - g["Low"]) / (g["High"] - g["Low"] + 1e-8)
                if inside_frac < INSIDE_UPPER_FRAC: continue
                _sigs.append((df2.index[i + 1], ticker))

        _oos_w, _oos_t = backtest(all_prices, _sigs, OOS_START, OOS_END)
        _m = compute_metrics(_oos_w)
        _m["green_thresh"] = thresh
        _m["n_trades"] = len(_oos_t)
        sweep_results.append(_m)
        print(f"  thresh={thresh:.1%}  OOS Sharpe={_m['sharpe']}  n={_m['n_trades']}  CAGR={_m['cagr']:.1%}")

    # Save results
    results = {
        "hypothesis": "H234",
        "description": "Weekly Inside-Bar Breakout (Coiled Spring)",
        "source": "Stats Edge Trading — The 25-Year Backtest",
        "parameters": {
            "green_thresh": GREEN_THRESH,
            "vol_mult": VOL_MULT,
            "green_close_frac": GREEN_CLOSE_FRAC,
            "inside_upper_frac": INSIDE_UPPER_FRAC,
            "tc": TC,
            "max_positions": MAX_POSITIONS,
        },
        "is": is_metrics,
        "oos": oos_metrics,
        "confirmed": confirmed,
        "sweep": sweep_results,
    }
    out_path = Path("/workspace/agent/backtesting/results/h234_results.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\nResults saved to {out_path}")
    return results

if __name__ == "__main__":
    main()
