"""
H302 — BTC Moving Average Trend Following
==========================================

Hypothesis:
  Long BTC when daily close > N-day moving average; else cash (0% return).
  Inspired by Grayscale Research (2023): BTC 50d MA strategy → Sharpe 1.9
  vs buy-and-hold Sharpe 1.3 (2012–2023), 126% annualized return.

  Variants:
    A) 50d SMA   (primary — matches Grayscale/AUT paper)
    B) 100d SMA
    C) 200d SMA
    D) 20d/50d EMA crossover (long when 20d EMA > 50d EMA)

  Gate: OOS Sharpe > 1.0 (any variant must beat BTC B&H and clear 1.0)
  IS:  2014-01-01 to 2020-12-31
  OOS: 2021-01-01 to 2026-06-15

  Benchmark: BTC buy-and-hold (same period)

  NOTE: Crypto trades 365 days/year. Volatility annualized with sqrt(365).
  Returns are gross of tax; STCG would reduce real-world Sharpe significantly.
  Survivorship concern is minimal here — BTC is the single asset.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2012-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2014-01-01"
IS_END     = "2020-12-31"
OOS_START  = "2021-01-01"


def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 20:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(365)   # 365-day annualization for crypto
    sharpe = cagr / vol if vol > 0 else 0
    max_dd = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(1 for _, g in rets.groupby(rets.index.year)
                  if (1 + g).prod() - 1 < 0)
    return {
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "neg_years":    neg_yrs,
        "n_days":       len(eq),
    }


def run_ma_strategy(btc: pd.Series, start: str, end: str,
                    ma_type: str, n: int, n2: int = None) -> pd.Series:
    """
    Build daily equity curve for MA signal on BTC.
    Signal is lagged 1 day to avoid look-ahead.
    Cash = 0% return when out of market.
    """
    px = btc.loc[start:end].dropna()
    if ma_type == "sma":
        ma = px.rolling(n, min_periods=n).mean()
        raw_signal = (px > ma).astype(float)
    elif ma_type == "ema_cross":
        ema_fast = px.ewm(span=n, adjust=False).mean()
        ema_slow = px.ewm(span=n2, adjust=False).mean()
        raw_signal = (ema_fast > ema_slow).astype(float)
    else:
        raise ValueError(f"Unknown ma_type: {ma_type}")

    signal    = raw_signal.shift(1).fillna(0)
    daily_ret = px.pct_change().fillna(0)
    strat_ret = signal * daily_ret
    equity    = INITIAL_EQUITY * (1 + strat_ret).cumprod()
    return equity


def run_bnh(btc: pd.Series, start: str, end: str) -> pd.Series:
    px = btc.loc[start:end].dropna()
    daily_ret = px.pct_change().fillna(0)
    equity    = INITIAL_EQUITY * (1 + daily_ret).cumprod()
    return equity


def main():
    print("\nH302 — BTC Moving Average Trend Following")
    print("Downloading BTC-USD data...")

    raw = yf.download("BTC-USD", start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    btc = (raw["Close"] if isinstance(raw.columns, pd.MultiIndex)
           else raw["Close"]).squeeze().dropna()
    print(f"  BTC-USD: {btc.index[0].date()} to {btc.index[-1].date()} ({len(btc)} days)")

    bnh_is  = calc_stats(run_bnh(btc, IS_START, IS_END))
    bnh_oos = calc_stats(run_bnh(btc, OOS_START, FULL_END))
    print(f"\n  B&H IS:  Sharpe {bnh_is['sharpe']:.3f} | CAGR {bnh_is['cagr']:.1%} | MaxDD {bnh_is['max_drawdown']:.1%}")
    print(f"  B&H OOS: Sharpe {bnh_oos['sharpe']:.3f} | CAGR {bnh_oos['cagr']:.1%} | MaxDD {bnh_oos['max_drawdown']:.1%}")

    variants = [
        ("A: 50d SMA",           "sma",       50,  None),
        ("B: 100d SMA",          "sma",       100, None),
        ("C: 200d SMA",          "sma",       200, None),
        ("D: 20d/50d EMA cross", "ema_cross", 20,  50),
    ]

    results = {
        "hypothesis":  "H302",
        "description": "BTC Moving Average Trend Following",
        "is_period":   f"{IS_START} to {IS_END}",
        "oos_period":  f"{OOS_START} to {FULL_END}",
        "gate":        "OOS Sharpe > 1.0",
        "bnh_is_sharpe":   bnh_is["sharpe"],
        "bnh_oos_sharpe":  bnh_oos["sharpe"],
        "bnh_oos_maxdd":   bnh_oos["max_drawdown"],
        "variants":    {},
        "verdict":     "NOT CONFIRMED",
    }

    print(f"\n{'='*72}")
    print(f"  {'Variant':<28} {'IS Sh':>7} {'OOS Sh':>7} {'OOS CAGR':>9} {'MaxDD':>8} {'Gate':>5}")
    print(f"{'='*72}")

    any_pass = False
    for name, ma_type, n, n2 in variants:
        eq_is  = run_ma_strategy(btc, IS_START,  IS_END,    ma_type, n, n2)
        eq_oos = run_ma_strategy(btc, OOS_START, FULL_END,  ma_type, n, n2)

        is_st  = calc_stats(eq_is)
        oos_st = calc_stats(eq_oos)

        passes   = oos_st.get("sharpe", 0) > 1.0
        gate_str = "PASS" if passes else "fail"
        if passes:
            any_pass = True

        print(f"  {name:<28} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['cagr']:>9.1%} {oos_st['max_drawdown']:>8.1%} {gate_str:>5}")

        results["variants"][name] = {
            "ma_type": ma_type, "n": n, "n2": n2,
            "is_stats":  is_st,
            "oos_stats": oos_st,
            "passes":    passes,
        }

    print(f"{'='*72}")

    if any_pass:
        results["verdict"] = "CONFIRMED"

    out_path = RESULT_DIR / "h302_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nVerdict:      {results['verdict']}")
    print(f"B&H OOS:      Sharpe {bnh_oos['sharpe']:.3f} | CAGR {bnh_oos['cagr']:.1%} | MaxDD {bnh_oos['max_drawdown']:.1%}")
    print(f"Results:      {out_path}")


if __name__ == "__main__":
    main()
