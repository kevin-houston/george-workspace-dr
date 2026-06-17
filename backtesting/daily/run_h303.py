"""
H303 — Crypto Cross-Sectional Momentum
=======================================

Hypothesis:
  Monthly cross-sectional momentum on a fixed crypto universe.
  At each month-end, rank all coins by 1-month return; hold top-N equal-weight
  for the following month. Inspired by Liu et al. (2022) "Common Risk Factors
  in Cryptocurrency" and momentum literature on crypto assets.

  SURVIVORSHIP BIAS CAVEAT: Universe is fixed as of 2026-06-16. Coins that
  failed/delisted between 2018 and 2022 are excluded. OOS Sharpe is optimistic.

  Variants:
    A) Top-3 equal-weight
    B) Top-5 equal-weight  (primary)
    C) Top-3 inv-vol weight
    D) Top-5 inv-vol weight
    E) Top-1 (pure winner rotation)

  Gate: OOS Sharpe > 1.2
  IS:  2018-01-01 to 2021-12-31
  OOS: 2022-01-01 to 2026-06-15

  Benchmark: BTC buy-and-hold (same period)

  NOTE: Monthly returns annualized with sqrt(12). Trades 365 days/year
  but signal fires monthly, so monthly vol annualization is appropriate.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2017-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2018-01-01"
IS_END     = "2021-12-31"
OOS_START  = "2022-01-01"

# Fixed universe — coins available on yfinance with reasonable 2018+ history
UNIVERSE = [
    "BTC-USD", "ETH-USD", "XRP-USD", "LTC-USD", "BCH-USD",
    "ETC-USD", "XLM-USD", "ADA-USD", "TRX-USD", "LINK-USD",
    "BNB-USD", "DOGE-USD", "XMR-USD", "ZEC-USD", "DASH-USD",
    "EOS-USD", "NEO-USD", "XTZ-USD", "VET-USD", "BAT-USD",
]


def calc_stats_monthly(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 6:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(12)   # monthly annualization
    sharpe = cagr / vol if vol > 0 else 0
    max_dd = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(1 for _, g in rets.groupby(rets.index.year)
                  if (1 + g).prod() - 1 < 0)
    return {
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "neg_years":    neg_yrs,
        "n_months":     len(rets),
    }


def run_momentum(monthly_px: pd.DataFrame, start: str, end: str,
                 top_n: int, inv_vol: bool) -> pd.Series:
    """
    Monthly cross-sectional momentum equity curve.
    Signal: rank by 1-month return at each month-end → hold top_n next month.
    Lagged 1 period to avoid look-ahead.
    """
    px = monthly_px.loc[start:end]
    rets = px.pct_change()

    equity = pd.Series(index=px.index, dtype=float)
    equity.iloc[0] = INITIAL_EQUITY

    for i in range(1, len(px)):
        # Signal based on return ending at i-1 (lag 1 — avoid look-ahead)
        if i < 2:
            equity.iloc[i] = equity.iloc[i - 1]
            continue

        signal_rets = rets.iloc[i - 1]  # 1-month return ending at prior month-end
        valid = signal_rets.dropna()
        if len(valid) < top_n:
            equity.iloc[i] = equity.iloc[i - 1]
            continue

        top_coins = valid.nlargest(top_n).index

        if inv_vol:
            # Inv-vol weighting using last 3 months of daily vol (approx from monthly)
            vols = rets.iloc[max(0, i - 3):i][top_coins].std()
            vols = vols.replace(0, np.nan).dropna()
            if len(vols) == 0:
                weights = pd.Series(1.0 / top_n, index=top_coins)
            else:
                inv = 1.0 / vols
                weights = inv / inv.sum()
        else:
            weights = pd.Series(1.0 / top_n, index=top_coins)

        # Period return = weighted sum of coin returns this month
        period_rets = rets.iloc[i][top_coins]
        period_ret = (weights * period_rets).sum()

        equity.iloc[i] = equity.iloc[i - 1] * (1 + period_ret)

    return equity


def run_bnh_monthly(monthly_px: pd.DataFrame, ticker: str,
                    start: str, end: str) -> pd.Series:
    px = monthly_px[ticker].loc[start:end].dropna()
    rets = px.pct_change().fillna(0)
    equity = INITIAL_EQUITY * (1 + rets).cumprod()
    return equity


def main():
    print("\nH303 — Crypto Cross-Sectional Momentum")
    print("Downloading universe data...")

    raw = yf.download(UNIVERSE, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)

    if isinstance(raw.columns, pd.MultiIndex):
        prices_daily = raw["Close"]
    else:
        prices_daily = raw[["Close"]]

    prices_daily = prices_daily.squeeze()

    # Drop coins with < 1000 daily observations (insufficient history)
    sufficient = prices_daily.count() >= 1000
    prices_daily = prices_daily.loc[:, sufficient]
    print(f"  Universe after data filter: {list(prices_daily.columns)}")
    print(f"  Date range: {prices_daily.index[0].date()} to {prices_daily.index[-1].date()}")

    # Resample to month-end
    monthly_px = prices_daily.resample("ME").last()
    print(f"  Monthly observations: {len(monthly_px)}")

    bnh_is  = calc_stats_monthly(run_bnh_monthly(monthly_px, "BTC-USD", IS_START, IS_END))
    bnh_oos = calc_stats_monthly(run_bnh_monthly(monthly_px, "BTC-USD", OOS_START, FULL_END))
    print(f"\n  BTC B&H IS:  Sharpe {bnh_is['sharpe']:.3f} | CAGR {bnh_is['cagr']:.1%} | MaxDD {bnh_is['max_drawdown']:.1%}")
    print(f"  BTC B&H OOS: Sharpe {bnh_oos['sharpe']:.3f} | CAGR {bnh_oos['cagr']:.1%} | MaxDD {bnh_oos['max_drawdown']:.1%}")

    variants = [
        ("A: Top-3 equal",    3, False),
        ("B: Top-5 equal",    5, False),
        ("C: Top-3 inv-vol",  3, True),
        ("D: Top-5 inv-vol",  5, True),
        ("E: Top-1 (winner)", 1, False),
    ]

    results = {
        "hypothesis":  "H303",
        "description": "Crypto Cross-Sectional Momentum",
        "is_period":   f"{IS_START} to {IS_END}",
        "oos_period":  f"{OOS_START} to {FULL_END}",
        "gate":        "OOS Sharpe > 1.2",
        "universe":    list(prices_daily.columns),
        "bnh_is_sharpe":   bnh_is["sharpe"],
        "bnh_oos_sharpe":  bnh_oos["sharpe"],
        "bnh_oos_maxdd":   bnh_oos["max_drawdown"],
        "variants":    {},
        "verdict":     "NOT CONFIRMED",
        "caveat":      "Survivorship bias: fixed 2026-06-16 universe excludes failed coins",
    }

    print(f"\n{'='*72}")
    print(f"  {'Variant':<26} {'IS Sh':>7} {'OOS Sh':>7} {'OOS CAGR':>9} {'MaxDD':>8} {'Gate':>5}")
    print(f"{'='*72}")

    any_pass = False
    for name, top_n, inv_vol in variants:
        eq_is  = run_momentum(monthly_px, IS_START,  IS_END,    top_n, inv_vol)
        eq_oos = run_momentum(monthly_px, OOS_START, FULL_END,  top_n, inv_vol)

        is_st  = calc_stats_monthly(eq_is)
        oos_st = calc_stats_monthly(eq_oos)

        passes   = oos_st.get("sharpe", 0) > 1.2
        gate_str = "PASS" if passes else "fail"
        if passes:
            any_pass = True

        print(f"  {name:<26} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['cagr']:>9.1%} {oos_st['max_drawdown']:>8.1%} {gate_str:>5}")

        results["variants"][name] = {
            "top_n": top_n, "inv_vol": inv_vol,
            "is_stats":  is_st,
            "oos_stats": oos_st,
            "passes":    passes,
        }

    print(f"{'='*72}")

    if any_pass:
        results["verdict"] = "CONFIRMED (survivorship bias caveat)"

    out_path = RESULT_DIR / "h303_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nVerdict:      {results['verdict']}")
    print(f"BTC B&H OOS:  Sharpe {bnh_oos['sharpe']:.3f} | CAGR {bnh_oos['cagr']:.1%} | MaxDD {bnh_oos['max_drawdown']:.1%}")
    print(f"Results:      {out_path}")


if __name__ == "__main__":
    main()
