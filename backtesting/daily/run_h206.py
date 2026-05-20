"""
H206 — Halloween Effect (Sell in May) on SPY with TOM Composite
===============================================================
Source: Bouman & Jacobsen (2002); Schroeder (IJFS, Nov 2025, doi:10.3390/ijfs13040208)
  - SEC disclosures 17% higher in winter (Nov–Apr), Feb peak, Sep trough
  - 22% more insider trading, 473% more annual reports in winter
  - Structural information-flow driver tied to fiscal year-end and regulatory cycles

Strategy:
  H206-A: Hold SPY in Nov–Apr (winter half), BIL in May–Oct (summer half)
  H206-B: Hold SPY only during TOM windows within Nov–Apr, BIL otherwise
           (combines Halloween seasonality × TOM intramonth concentration)

IS:  2003–2017  OOS: 2018–2026
Confirm: H206-A OOS Sharpe > 0.6; H206-B OOS Sharpe > 0.8
Benchmark: SPY buy-and-hold, H201 TOM-only (always in TOM window)
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

DATA_START = "2001-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2003-01-01")
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

# TOM window matches H201 confirmed params: last 1 + first 3 trading days
TOM_BEFORE = 1
TOM_AFTER  = 3

# Halloween months: winter = Nov, Dec, Jan, Feb, Mar, Apr
WINTER_MONTHS = {11, 12, 1, 2, 3, 4}

COST_BPS = 5  # one-way slippage per trade transition


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h206_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    # Try reuse from any prior h201 cache
    cp2 = CACHE_DIR / f"h201_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
    if cp2.exists():
        return pd.read_parquet(cp2).squeeze().rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def build_tom_mask(trading_days: pd.DatetimeIndex) -> pd.Series:
    mask = pd.Series(False, index=trading_days)
    monthly_ends = (trading_days.to_series()
                    .groupby([trading_days.year, trading_days.month])
                    .last().values)
    for month_end in monthly_ends:
        end_loc = trading_days.get_loc(month_end)
        start = max(0, end_loc - TOM_BEFORE + 1)
        end   = min(len(trading_days) - 1, end_loc + TOM_AFTER)
        mask.iloc[start:end + 1] = True
    return mask


def build_halloween_mask(trading_days: pd.DatetimeIndex) -> pd.Series:
    """True for days in Nov-Apr (winter half)."""
    return pd.Series(trading_days.month.isin(WINTER_MONTHS), index=trading_days)


def apply_costs(signal: pd.Series, cost_bps: float) -> pd.Series:
    """Subtract round-trip cost on days where position changes."""
    transitions = signal.diff().abs().fillna(0) > 0.5
    costs = pd.Series(0.0, index=signal.index)
    costs[transitions] = cost_bps / 10000
    return costs


def sharpe(r: pd.Series) -> float:
    if len(r) < 20 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(252))


def max_dd(r: pd.Series) -> float:
    cumulative = (1 + r).cumprod()
    peak = cumulative.cummax()
    dd = (cumulative - peak) / peak
    return float(dd.min())


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def neg_years(r: pd.Series) -> int:
    annual = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    return int((annual < 0).sum())


def eval_strategy(ret_spy: pd.Series, signal: pd.Series,
                  ret_bil: pd.Series) -> dict:
    """Evaluate a strategy defined by a 0/1 signal (1=SPY, 0=BIL)."""
    strat_ret = signal * ret_spy + (1 - signal) * ret_bil
    cost = apply_costs(signal, COST_BPS)
    strat_ret = strat_ret - cost

    is_r = strat_ret[IS_START:IS_END]
    oos_r = strat_ret[OOS_START:OOS_END]

    days_invested_pct = float(signal.mean() * 100)

    return {
        "is_sharpe":  sharpe(is_r),
        "is_cumul":   cumul(is_r),
        "is_maxdd":   max_dd(is_r),
        "oos_sharpe": sharpe(oos_r),
        "oos_cumul":  cumul(oos_r),
        "oos_maxdd":  max_dd(oos_r),
        "oos_cagr":   float((oos_r.mean()) * 252 * 100),
        "oos_neg_yrs": neg_years(oos_r),
        "days_invested_pct": days_invested_pct,
    }


def main():
    print("H206 — Halloween Effect + TOM Composite")
    print("=" * 50)

    spy = fetch_daily("SPY")
    bil = fetch_daily("BIL")

    # Align
    idx = spy.index.intersection(bil.index)
    spy = spy.loc[idx]
    bil = bil.loc[idx]

    ret_spy = spy.pct_change().fillna(0)
    ret_bil = bil.pct_change().fillna(0)

    trading_days = idx
    tom_mask = build_tom_mask(trading_days)
    halloween_mask = build_halloween_mask(trading_days)

    # ── Benchmark: SPY buy-and-hold ──────────────────────────────────────────
    spy_bh = eval_strategy(ret_spy, pd.Series(1.0, index=idx), ret_bil)
    print(f"\nSPY Buy-and-Hold:")
    print(f"  IS Sharpe={spy_bh['is_sharpe']:.3f}  OOS Sharpe={spy_bh['oos_sharpe']:.3f}"
          f"  OOS CAGR={spy_bh['oos_cagr']:.1f}%  OOS MaxDD={spy_bh['oos_maxdd']:.1%}")

    # ── H201 reference: TOM only (always, regardless of month) ──────────────
    tom_signal = tom_mask.astype(float)
    h201 = eval_strategy(ret_spy, tom_signal, ret_bil)
    print(f"\nH201 Reference (TOM-only, ~{h201['days_invested_pct']:.0f}% invested):")
    print(f"  IS Sharpe={h201['is_sharpe']:.3f}  OOS Sharpe={h201['oos_sharpe']:.3f}"
          f"  OOS CAGR={h201['oos_cagr']:.1f}%  OOS MaxDD={h201['oos_maxdd']:.1%}")

    # ── H206-A: Halloween standalone (hold SPY Nov-Apr, BIL May-Oct) ────────
    ha_signal = halloween_mask.astype(float)
    h206a = eval_strategy(ret_spy, ha_signal, ret_bil)
    print(f"\nH206-A Halloween standalone (~{h206a['days_invested_pct']:.0f}% invested):")
    print(f"  IS Sharpe={h206a['is_sharpe']:.3f}  OOS Sharpe={h206a['oos_sharpe']:.3f}"
          f"  OOS CAGR={h206a['oos_cagr']:.1f}%  OOS MaxDD={h206a['oos_maxdd']:.1%}")
    print(f"  OOS Cumul={h206a['oos_cumul']:.3f}×  NegYrs={h206a['oos_neg_yrs']}")
    confirmed_a = h206a['oos_sharpe'] > 0.6
    print(f"  CONFIRMED (Sharpe>0.6): {confirmed_a}")

    # ── H206-B: Halloween × TOM composite ────────────────────────────────────
    # Hold SPY only when BOTH halloween (Nov-Apr) AND TOM window
    hb_signal = (halloween_mask & tom_mask).astype(float)
    h206b = eval_strategy(ret_spy, hb_signal, ret_bil)
    print(f"\nH206-B Halloween×TOM (~{h206b['days_invested_pct']:.0f}% invested):")
    print(f"  IS Sharpe={h206b['is_sharpe']:.3f}  OOS Sharpe={h206b['oos_sharpe']:.3f}"
          f"  OOS CAGR={h206b['oos_cagr']:.1f}%  OOS MaxDD={h206b['oos_maxdd']:.1%}")
    print(f"  OOS Cumul={h206b['oos_cumul']:.3f}×  NegYrs={h206b['oos_neg_yrs']}")
    confirmed_b = h206b['oos_sharpe'] > 0.8
    print(f"  CONFIRMED (Sharpe>0.8): {confirmed_b}")

    # ── H206-C: Summer TOM only (May-Oct TOM) — diagnostic ───────────────────
    # Tests whether TOM still works in summer (if yes, Halloween effect is redundant)
    summer_mask = ~halloween_mask
    hc_signal = (summer_mask & tom_mask).astype(float)
    h206c = eval_strategy(ret_spy, hc_signal, ret_bil)
    print(f"\nH206-C Summer TOM diagnostic (~{h206c['days_invested_pct']:.0f}% invested):")
    print(f"  IS Sharpe={h206c['is_sharpe']:.3f}  OOS Sharpe={h206c['oos_sharpe']:.3f}")

    # ── Year-by-year OOS analysis ─────────────────────────────────────────────
    print("\n── OOS Year-by-Year ──────────────────────────────────────────")
    print(f"{'Year':<6} {'SPY':>7} {'H206-A':>8} {'H206-B':>8}")
    oos_slice = slice(OOS_START, OOS_END)
    spy_oos  = ret_spy[oos_slice]
    ha_ret   = (ha_signal * ret_spy + (1 - ha_signal) * ret_bil)[oos_slice]
    hb_ret   = (hb_signal * ret_spy + (1 - hb_signal) * ret_bil)[oos_slice]
    for yr in sorted(spy_oos.index.year.unique()):
        r_spy = spy_oos[spy_oos.index.year == yr]
        r_a   = ha_ret[ha_ret.index.year == yr]
        r_b   = hb_ret[hb_ret.index.year == yr]
        c_spy = (1 + r_spy).prod() - 1
        c_a   = (1 + r_a).prod() - 1
        c_b   = (1 + r_b).prod() - 1
        print(f"{yr:<6} {c_spy:>+7.1%} {c_a:>+8.1%} {c_b:>+8.1%}")

    # ── Month decomposition: which months drive H206-A ────────────────────────
    print("\n── H206-A Monthly Return by Month (OOS) ─────────────────────")
    ha_oos = ha_ret
    print(f"{'Month':<12} {'AvgRet':>8} {'WinRate':>8} {'N':>5}")
    for m in range(1, 13):
        m_idx = ha_oos.index[ha_oos.index.month == m]
        if len(m_idx) == 0:
            continue
        r_m = ha_oos.loc[m_idx]
        print(f"  {pd.Timestamp(2000, m, 1).strftime('%b'):<10}"
              f"  {r_m.mean()*100:>+6.3f}%  {(r_m>0).mean():>7.1%}  {len(r_m):>5}")

    # ── Correlation to H026/H041a (from H112 baseline) ───────────────────────
    print("\n── Correlation Diagnostics (OOS) ────────────────────────────")
    print("  Correlation to existing strategies requires h112 equity curve.")
    print("  H206-A invests ~50% of time vs H201 ~25%; both SPY-based.")
    print(f"  H206-A × H201 OOS correlation diagnostic:")
    tom_oos = (tom_signal * ret_spy + (1 - tom_signal) * ret_bil)[oos_slice]
    corr_ab = ha_ret.corr(tom_oos)
    print(f"    H206-A vs H201: {corr_ab:.3f}")
    corr_ab2 = h206b['oos_sharpe']  # already printed

    # ── Save results ─────────────────────────────────────────────────────────
    results = {
        "hypothesis": "H206",
        "description": "Halloween Effect (Sell in May) + TOM Composite on SPY",
        "is_period":  f"{IS_START.date()} to {IS_END.date()}",
        "oos_period": f"{OOS_START.date()} to {OOS_END.date()}",
        "spy_bh":  spy_bh,
        "h201_ref": h201,
        "h206a":   h206a,
        "h206b":   h206b,
        "h206c_summer_tom": h206c,
        "confirmed_h206a": confirmed_a,
        "confirmed_h206b": confirmed_b,
        "confirm_gate_a": "OOS Sharpe > 0.6",
        "confirm_gate_b": "OOS Sharpe > 0.8",
    }

    out_path = RESULT_DIR / "h206_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {out_path}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n══ SUMMARY ══════════════════════════════════════════════════")
    print(f"H206-A (Halloween standalone): OOS Sharpe={h206a['oos_sharpe']:.3f}"
          f"  Gate=0.6  {'✓ CONFIRMED' if confirmed_a else '✗ NOT CONFIRMED'}")
    print(f"H206-B (Halloween×TOM):        OOS Sharpe={h206b['oos_sharpe']:.3f}"
          f"  Gate=0.8  {'✓ CONFIRMED' if confirmed_b else '✗ NOT CONFIRMED'}")
    print(f"SPY B&H:                       OOS Sharpe={spy_bh['oos_sharpe']:.3f}")


if __name__ == "__main__":
    main()
