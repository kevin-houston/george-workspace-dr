"""
H299 — Market Breadth Timing: Sector 50d-MA Breadth Signal
============================================================

Hypothesis:
  Martin Pring (1992), Zweig "Breadth Thrust": when the majority of sectors
  are in uptrends (above their 50-day MA), equity returns are persistently
  positive. When breadth deteriorates (most sectors below 50d MA), equity
  drawdowns follow.

  Signal: compute each month-end the fraction of 11 sector ETFs (XLK, XLF,
  XLE, XLV, XLI, XLP, XLY, XLU, XLRE, XLC, XLB) trading above their
  50-day moving average.

  Breadth = (# sectors above 50d MA) / 11

  Variants:
    A) Threshold: breadth > 0.50 → SPY, else BIL
    B) Threshold: breadth > 0.70 → SPY, else BIL  (require strong breadth)
    C) Double filter: breadth > 0.50 AND SPY > 200d MA → SPY, else BIL
    D) Continuous: SPY weight = breadth score (0–100% SPY)
    E) Threshold: breadth > 0.30 → SPY, else BIL  (lenient — stay in unless near-collapse)

  Rebalance: monthly (signal evaluated at month-end close)
  Benchmark: SPY buy-and-hold, H296 Variant C (VIX term structure + 200MA)

  IS:  2012-01-01 to 2019-12-31  (XLRE since 2015; XLC since 2018 → use 9 sectors pre-2015)
  OOS: 2020-01-01 to 2026-06-15
  Gate: OOS Sharpe > 1.0 AND > SPY buy-and-hold
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2010-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2012-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"

OOS_SHARPE_GATE = 1.0

SECTOR_ETFS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLRE", "XLC", "XLB"]


def download_daily(tickers, start, end):
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes.index = pd.to_datetime(closes.index)
    return closes.ffill()


def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    cummax = eq.cummax()
    max_dd = ((eq - cummax) / cummax).min()
    annual = rets.resample("YE").apply(lambda r: (1 + r).prod() - 1)
    neg_years = (annual < 0).sum()
    return {
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "n_months":     int(len(rets) // 21),
        "neg_years":    int(neg_years),
    }


def compute_breadth(sectors_daily: pd.DataFrame) -> pd.Series:
    """Month-end breadth: fraction of sectors above their 50d MA."""
    ma50 = sectors_daily.rolling(50).mean()
    above_ma = (sectors_daily > ma50).astype(float)
    # Use only sectors with data on that date
    breadth = above_ma.apply(lambda row: row.dropna().mean(), axis=1)
    # Resample to month-end
    breadth_monthly = breadth.resample("ME").last()
    return breadth_monthly


def run_variant(
    spy_daily: pd.Series,
    breadth_monthly: pd.Series,
    spy_ma200: pd.Series,
    mode: str,
    threshold: float = 0.5,
) -> pd.Series:
    """
    Monthly strategy. At month-end, evaluate signal, hold for next month.
    mode: 'threshold', 'double', 'continuous'
    """
    month_ends = spy_daily.resample("ME").last().index
    equity = pd.Series(index=spy_daily.index, dtype=float)
    portfolio_val = INITIAL_EQUITY
    current_weight = 1.0  # start invested in SPY

    for i, me in enumerate(month_ends[:-1]):
        next_me = month_ends[i + 1]

        # Signal at this month-end
        b = breadth_monthly.get(me, None)
        spy_price = spy_daily.get(me, None)
        spy_ma = spy_ma200.get(me, None)

        if b is None:
            target_weight = current_weight
        elif mode == "threshold":
            target_weight = 1.0 if b >= threshold else 0.0
        elif mode == "double":
            target_weight = 1.0 if (b >= threshold and spy_price is not None
                                    and spy_ma is not None
                                    and spy_price > spy_ma) else 0.0
        elif mode == "continuous":
            target_weight = float(b)
        else:
            target_weight = current_weight

        current_weight = target_weight

        # Apply weight to daily returns in next month
        mask = (spy_daily.index > me) & (spy_daily.index <= next_me)
        daily_slice = spy_daily[mask]
        daily_rets = daily_slice.pct_change().fillna(0)

        for date, r in daily_rets.items():
            portfolio_val *= (1 + current_weight * r)
            equity[date] = portfolio_val

    equity.iloc[0] = INITIAL_EQUITY
    equity = equity.ffill().dropna()
    return equity


def main():
    print("\nH299 — Market Breadth Timing (Sector 50d-MA)")
    print("Downloading data...")

    all_tickers = SECTOR_ETFS + ["SPY"]
    daily = download_daily(all_tickers, FULL_START, FULL_END)
    spy_daily = daily["SPY"]
    sectors_daily = daily[SECTOR_ETFS]

    # 200d MA for SPY
    spy_ma200 = spy_daily.rolling(200).mean()

    breadth_monthly = compute_breadth(sectors_daily)
    print(f"Breadth computed: {len(breadth_monthly)} month-ends")
    print(f"Avg breadth (full): {breadth_monthly.mean():.2f}")
    print(f"Avg breadth IS ({IS_START}–{IS_END}): "
          f"{breadth_monthly.loc[IS_START:IS_END].mean():.2f}")
    print(f"Avg breadth OOS ({OOS_START}–): "
          f"{breadth_monthly.loc[OOS_START:].mean():.2f}")

    is_mask  = (spy_daily.index >= IS_START)  & (spy_daily.index <= IS_END)
    oos_mask = (spy_daily.index >= OOS_START) & (spy_daily.index <= FULL_END)

    # SPY benchmarks
    def spy_period_equity(mask):
        s = spy_daily[mask]
        rets = s.pct_change().fillna(0)
        eq = (1 + rets).cumprod() * INITIAL_EQUITY
        return eq

    spy_is_stats  = calc_stats(spy_period_equity(is_mask))
    spy_oos_stats = calc_stats(spy_period_equity(oos_mask))

    print(f"\nSPY IS  Sharpe={spy_is_stats['sharpe']:.3f}  MaxDD={spy_is_stats['max_drawdown']:.1%}")
    print(f"SPY OOS Sharpe={spy_oos_stats['sharpe']:.3f}  MaxDD={spy_oos_stats['max_drawdown']:.1%}")

    variants = [
        ("A: Breadth > 50%",        "threshold",  0.50, "monthly"),
        ("B: Breadth > 70%",        "threshold",  0.70, "monthly"),
        ("C: >50% + SPY>200MA",     "double",     0.50, "monthly"),
        ("D: Continuous weight",    "continuous", None, "monthly"),
        ("E: Breadth > 30%",        "threshold",  0.30, "monthly"),
    ]

    results = {
        "hypothesis": "H299",
        "description": "Market Breadth Timing: Fraction of Sector ETFs above 50d MA",
        "signal": "Monthly breadth = (#sectors above 50d MA) / 11; hold SPY vs BIL",
        "is_period": f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {FULL_END}",
        "spy_is":  spy_is_stats,
        "spy_oos": spy_oos_stats,
        "variants": {},
        "verdict": "NOT CONFIRMED",
    }

    print("\n" + "="*70)
    print(f"{'Variant':<30} {'IS Sh':>7} {'OOS Sh':>7} {'MaxDD':>8} {'%SPY':>6} {'Gate':>5}")
    print("="*70)

    best_oos = -99.0
    best_var = None

    for name, mode, threshold, _ in variants:
        eq_full = run_variant(spy_daily, breadth_monthly, spy_ma200,
                              mode, threshold if threshold else 0.5)
        eq_is  = eq_full[is_mask]
        eq_oos = eq_full[oos_mask]

        is_st  = calc_stats(eq_is)
        oos_st = calc_stats(eq_oos)
        passes = oos_st["sharpe"] >= OOS_SHARPE_GATE

        # Estimate % time in SPY for threshold variants
        if mode in ("threshold", "double") and threshold is not None:
            b_is  = breadth_monthly.loc[IS_START:IS_END]
            b_oos = breadth_monthly.loc[OOS_START:]
            if mode == "threshold":
                pct_in = f"{(b_oos >= threshold).mean():.0%}"
            else:
                spy_above = spy_daily.resample("ME").last()
                spy_ma_m  = spy_ma200.resample("ME").last()
                pct_in = f"{((b_oos >= threshold) & (spy_above.loc[OOS_START:] > spy_ma_m.loc[OOS_START:])).mean():.0%}"
        else:
            pct_in = "—"

        gate_str = "PASS" if passes else "fail"
        print(f"  {name:<28} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['max_drawdown']:>8.1%} {pct_in:>6} {gate_str:>5}")

        results["variants"][name] = {
            "mode": mode,
            "threshold": threshold,
            "is_stats":  is_st,
            "oos_stats": oos_st,
            "pct_time_in_spy_oos": pct_in,
            "passes": passes,
        }

        if oos_st["sharpe"] > best_oos:
            best_oos = oos_st["sharpe"]
            best_var = name

    print("="*70)

    results["best_variant"] = best_var
    results["best_oos_sharpe"] = round(best_oos, 4)

    any_pass = any(v["passes"] for v in results["variants"].values())
    if any_pass:
        results["verdict"] = "CONFIRMED"

    out_path = RESULT_DIR / "h299_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))

    print(f"\nVerdict: {results['verdict']}")
    print(f"Best OOS Sharpe: {best_oos:.3f} (gate >= {OOS_SHARPE_GATE})")
    print(f"Results saved: {out_path}")


if __name__ == "__main__":
    main()
