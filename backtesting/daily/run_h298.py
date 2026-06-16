"""
H298 — Short-Term (1-Week) Reversal on ETF Universe
======================================================

Hypothesis:
  Lehmann (1990), Lo & MacKinlay (1990), Jegadeesh (1990): stocks that lost the most
  in the past week tend to recover the following week. Lo & MacKinlay demonstrated
  this on individual stocks; Gutierrez & Kelley (2008) confirm it persists after
  transaction-cost adjustment.

  This test applies the 1-week reversal signal to the H026 sector/alt ETF universe
  (25 assets). ETFs should show cleaner reversal than individual stocks due to
  lower idiosyncratic noise and higher liquidity.

  Signal: rank ETFs by trailing 5-day return. Long top-n (worst recent performers).
  Rebalance: weekly (every Friday close → Monday open, here proxied as weekly bars).

  Variants:
    A) Top-1 reversal (pure concentrated reversal)
    B) Top-3 reversal (broad reversal basket)
    C) Top-5 reversal (widest basket, most diversified)
    D) Reversal with TSMOM gate: only hold reversal candidates with positive 3M return
       (recent loser BUT not in multi-month downtrend — captures bounce, not falling knife)

  Universe: H026's 25-ETF universe (sector + alts)
  IS:  2008-01-01 to 2017-12-31  (10 years)
  OOS: 2018-01-01 to 2026-06-15  (8 years)
  Gate: OOS Sharpe > 0.8

  Benchmarks:
    - SPY buy-and-hold
    - Equal-weight H026 universe buy-and-hold
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2007-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

OOS_SHARPE_GATE = 0.8

H026_UNIVERSE = [
    "SPY", "QQQ", "IWM", "EFA", "EEM",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLRE", "XLC",
    "GLD", "SLV", "USO", "UNG",
    "TLT", "IEF", "HYG", "LQD",
    "BIL", "VNQ",
]


def download_weekly(tickers, start, end):
    raw = yf.download(tickers, start=start, end=end,
                      interval="1wk", auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes.index = pd.to_datetime(closes.index)
    closes = closes.ffill()
    return closes


def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(52) if rets.std() > 0 else 0
    cummax = eq.cummax()
    drawdowns = (eq - cummax) / cummax
    max_dd = drawdowns.min()
    annual = rets.resample("YE").apply(lambda r: (1 + r).prod() - 1)
    neg_years = (annual < 0).sum()
    return {
        "cagr": round(float(cagr), 4),
        "sharpe": round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "n_weeks": int(len(rets)),
        "neg_years": int(neg_years),
    }


def run_variant(closes: pd.DataFrame, n_long: int, tsmom_gate: bool) -> pd.Series:
    """
    Weekly reversal strategy.
    closes: weekly close prices, columns = tickers
    n_long: number of worst-returning ETFs to hold each week
    tsmom_gate: if True, only hold ETFs with positive 13-week (3M) return
    """
    weekly_ret = closes.pct_change()       # 1-week return
    mom_13w = closes.pct_change(13)        # 13-week return for TSMOM gate

    equity = pd.Series(index=closes.index, dtype=float)
    portfolio_val = INITIAL_EQUITY

    for i in range(13, len(closes) - 1):
        week_ret = weekly_ret.iloc[i]
        available = week_ret.dropna()

        if tsmom_gate:
            mom_now = mom_13w.iloc[i]
            available = available[mom_now[available.index] > 0]

        if len(available) < n_long:
            # hold equal-weight of whatever is available, or BIL
            holdings = available.index.tolist() if len(available) > 0 else ["BIL"]
        else:
            # buy worst n_long (reversal)
            holdings = available.nsmallest(n_long).index.tolist()

        # Compute return of this week's holdings (next week's price change)
        next_ret = weekly_ret.iloc[i + 1]
        port_ret = next_ret[holdings].mean()

        portfolio_val *= (1 + port_ret)
        equity.iloc[i + 1] = portfolio_val

    equity.iloc[0] = INITIAL_EQUITY
    equity = equity.ffill()
    return equity


def run_equal_weight(closes: pd.DataFrame) -> pd.Series:
    weekly_ret = closes.pct_change()
    eq = (1 + weekly_ret).cumprod() * INITIAL_EQUITY
    eq_portfolio = eq.mean(axis=1)
    eq_portfolio.iloc[0] = INITIAL_EQUITY
    return eq_portfolio


def main():
    print("\nH298 — Weekly ETF Reversal")
    print(f"Universe: {len(H026_UNIVERSE)} ETFs (H026)")
    print("Downloading weekly price data...")

    closes = download_weekly(H026_UNIVERSE, FULL_START, FULL_END)
    closes = closes.dropna(how="all")

    # Drop tickers with insufficient history
    min_date = pd.Timestamp(IS_START)
    available_tickers = [t for t in H026_UNIVERSE
                         if t in closes.columns and closes[t].first_valid_index() <= min_date]
    closes = closes[available_tickers]
    print(f"Tickers with full IS history: {len(available_tickers)}")
    print(f"  {available_tickers}")

    is_mask  = (closes.index >= IS_START)  & (closes.index <= IS_END)
    oos_mask = (closes.index >= OOS_START) & (closes.index <= FULL_END)

    # SPY benchmark
    spy_weekly = closes["SPY"]
    spy_ret = spy_weekly.pct_change()

    def spy_equity(mask):
        eq = pd.Series(INITIAL_EQUITY, index=closes.index[mask])
        for i, d in enumerate(closes.index[mask][1:], 1):
            r = spy_ret.loc[d] if d in spy_ret.index else 0
            eq.iloc[i] = eq.iloc[i-1] * (1 + r)
        return eq

    spy_is  = spy_equity(is_mask)
    spy_oos = spy_equity(oos_mask)
    spy_is_stats  = calc_stats(spy_is)
    spy_oos_stats = calc_stats(spy_oos)

    print(f"\nSPY IS  Sharpe={spy_is_stats['sharpe']:.3f}  MaxDD={spy_is_stats['max_drawdown']:.1%}")
    print(f"SPY OOS Sharpe={spy_oos_stats['sharpe']:.3f}  MaxDD={spy_oos_stats['max_drawdown']:.1%}")

    variants = [
        ("A: Top-1 reversal",      1, False),
        ("B: Top-3 reversal",      3, False),
        ("C: Top-5 reversal",      5, False),
        ("D: Top-3 + TSMOM gate",  3, True),
    ]

    results = {
        "hypothesis": "H298",
        "description": "Short-Term (1-Week) Reversal on H026 ETF Universe (Lehmann 1990)",
        "signal": "Long n ETFs with worst 5-day return last week; weekly rebalance",
        "universe": available_tickers,
        "is_period": f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {FULL_END}",
        "spy_is":  spy_is_stats,
        "spy_oos": spy_oos_stats,
        "variants": {},
        "verdict": "NOT CONFIRMED",
        "survivorship_bias": False,
    }

    print("\n" + "="*65)
    print(f"{'Variant':<30} {'IS Sh':>7} {'OOS Sh':>7} {'MaxDD':>8} {'Gate':>5}")
    print("="*65)

    best_oos = -99.0
    best_var = None

    for name, n, tsmom in variants:
        eq_full = run_variant(closes, n, tsmom)
        eq_is   = eq_full[is_mask]
        eq_oos  = eq_full[oos_mask]

        is_st  = calc_stats(eq_is)
        oos_st = calc_stats(eq_oos)

        passes = oos_st["sharpe"] >= OOS_SHARPE_GATE
        gate_str = "PASS" if passes else "fail"

        print(f"  {name:<28} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['max_drawdown']:>8.1%} {gate_str:>5}")

        results["variants"][name] = {
            "n_long": n,
            "tsmom_gate": tsmom,
            "is_stats":  is_st,
            "oos_stats": oos_st,
            "passes": passes,
        }

        if oos_st["sharpe"] > best_oos:
            best_oos = oos_st["sharpe"]
            best_var = name

    print("="*65)

    # Equal-weight benchmark
    ew_full = run_equal_weight(closes)
    ew_is_st  = calc_stats(ew_full[is_mask])
    ew_oos_st = calc_stats(ew_full[oos_mask])
    results["equal_weight_is"]  = ew_is_st
    results["equal_weight_oos"] = ew_oos_st
    print(f"  {'EW buy-hold':<28} {ew_is_st['sharpe']:>7.3f} {ew_oos_st['sharpe']:>7.3f} "
          f"{ew_oos_st['max_drawdown']:>8.1%}")

    results["best_variant"] = best_var
    results["best_oos_sharpe"] = round(best_oos, 4)

    any_pass = any(v["passes"] for v in results["variants"].values())
    if any_pass:
        results["verdict"] = "CONFIRMED"

    out_path = RESULT_DIR / "h298_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nVerdict: {results['verdict']}")
    print(f"Best OOS Sharpe: {best_oos:.3f} (gate >= {OOS_SHARPE_GATE})")
    print(f"Results saved: {out_path}")


if __name__ == "__main__":
    main()
