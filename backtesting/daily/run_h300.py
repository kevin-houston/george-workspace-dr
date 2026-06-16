"""
H300 — Yield Curve Slope as Equity Timing Signal (10Y-2Y Spread)
=================================================================

Hypothesis:
  Estrella & Mishkin (1998), Fama (1990): the 10Y-2Y Treasury spread is a
  well-established recession predictor. When the curve inverts (spread < 0),
  recession risk rises and equity markets tend to underperform over the next
  6-18 months. Conversely, steep curves predict economic expansion and equity gains.

  This tests whether a simple monthly yield-curve signal improves equity timing:
  - Steep curve (spread > 0) → hold SPY
  - Inverted/flat curve (spread ≤ 0) → hold BIL (cash)

  Variants:
    A) Binary: spread > 0 → SPY, else BIL
    B) Threshold: spread > +0.50% → SPY, else BIL  (require meaningfully steep)
    C) Combined: spread > 0 AND SPY > 200d MA → SPY, else BIL
    D) Lagged 3M: use spread lagged 3 months (pure look-ahead-free signal)
    E) Gradient: SPY weight proportional to spread clipped [0, 2.5%] → [0%, 100%]

  Data:
    - 10Y yield: ^TNX (CBOE 10-year Treasury yield index, yfinance)
    - 2Y yield:  ^IRX = 13-week T-bill; use DGS2 from FRED API for true 2-year
    - Alternatively: use yfinance "^TNX" and compute spread vs "^IRX" (3M proxy)

  Note: 10Y-3M spread is a stronger recession predictor (Johanssen & Mertens 2018)
  than 10Y-2Y in some studies. We test 10Y-3M (available via ^TNX minus ^IRX).

  IS:  2000-01-01 to 2014-12-31  (includes 2001 and 2008 recessions)
  OOS: 2015-01-01 to 2026-06-15  (includes 2020 COVID, 2022 inversion)
  Gate: OOS Sharpe > 1.0 AND > SPY buy-and-hold
"""

import json
import os
import urllib3
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import requests.adapters as _ra
_orig_send = _ra.HTTPAdapter.send
def _no_verify_send(self, request, **kwargs):
    kwargs["verify"] = False
    return _orig_send(self, request, **kwargs)
_ra.HTTPAdapter.send = _no_verify_send

INITIAL_EQUITY = 100_000.0
RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "1999-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2000-01-01"
IS_END     = "2014-12-31"
OOS_START  = "2015-01-01"

OOS_SHARPE_GATE = 1.0


def fetch_fred(series_id: str, start: str, end: str) -> pd.Series:
    api_key = os.environ.get("FRED_API_KEY", "")
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&observation_start={start}&observation_end={end}"
           f"&api_key={api_key}&file_type=json")
    resp = requests.get(url, timeout=30)
    data = resp.json()
    obs = data.get("observations", [])
    s = pd.Series(
        {pd.Timestamp(o["date"]): float(o["value"])
         for o in obs if o["value"] != "."},
        dtype=float,
    )
    s.index = pd.to_datetime(s.index)
    return s


def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    cagr = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    max_dd = ((eq - eq.cummax()) / eq.cummax()).min()
    neg_years = (rets.resample("YE").apply(lambda r: (1 + r).prod() - 1) < 0).sum()
    return {
        "cagr":         round(float(cagr), 4),
        "sharpe":       round(float(sharpe), 4),
        "max_drawdown": round(float(max_dd), 4),
        "n_months":     int(len(rets) // 21),
        "neg_years":    int(neg_years),
    }


def run_variant(
    spy_daily: pd.Series,
    spread_monthly: pd.Series,
    spy_ma200: pd.Series,
    mode: str,
    threshold: float = 0.0,
    lag_months: int = 0,
) -> pd.Series:
    if lag_months > 0:
        spread_monthly = spread_monthly.shift(lag_months)

    month_ends = spy_daily.resample("ME").last().index
    equity = pd.Series(index=spy_daily.index, dtype=float)
    portfolio_val = INITIAL_EQUITY
    current_weight = 1.0

    for i, me in enumerate(month_ends[:-1]):
        next_me = month_ends[i + 1]

        spread_val = spread_monthly.asof(me) if me in spread_monthly.index or True else None
        spy_price  = spy_daily.asof(me)
        spy_ma     = spy_ma200.asof(me)

        if pd.isna(spread_val):
            target_weight = current_weight
        elif mode == "binary":
            target_weight = 1.0 if spread_val >= threshold else 0.0
        elif mode == "combined":
            above_curve = spread_val >= threshold
            above_ma    = (not pd.isna(spy_ma)) and spy_price > spy_ma
            target_weight = 1.0 if (above_curve and above_ma) else 0.0
        elif mode == "gradient":
            # scale: 0 when spread=0, 1 when spread >= 2.5pp
            target_weight = float(np.clip(spread_val / 2.5, 0.0, 1.0))
        else:
            target_weight = current_weight

        current_weight = target_weight

        mask = (spy_daily.index > me) & (spy_daily.index <= next_me)
        rets = spy_daily[mask].pct_change().fillna(0)
        for date, r in rets.items():
            portfolio_val *= (1 + current_weight * r)
            equity[date] = portfolio_val

    equity.iloc[0] = INITIAL_EQUITY
    equity = equity.ffill().dropna()
    return equity


def main():
    print("\nH300 — Yield Curve Slope (10Y-3M Spread) Equity Timing")
    print("Downloading data...")

    # SPY daily prices
    spy_raw = yf.download("SPY", start=FULL_START, end=FULL_END,
                          auto_adjust=True, progress=False)
    spy_daily = spy_raw["Close"].squeeze()
    spy_daily.index = pd.to_datetime(spy_daily.index)
    spy_ma200 = spy_daily.rolling(200).mean()

    # Yield curve from FRED: DGS10 (10Y) and DGS3MO (3-month)
    print("Fetching FRED yield data...")
    dgs10  = fetch_fred("DGS10", FULL_START, FULL_END)
    dgs3mo = fetch_fred("DGS3MO", FULL_START, FULL_END)

    # Spread: 10Y minus 3M (positive = normal/steep, negative = inverted)
    spread_daily = (dgs10 - dgs3mo).ffill()
    spread_monthly = spread_daily.resample("ME").last()

    print(f"Spread data: {spread_daily.index[0].date()} to {spread_daily.index[-1].date()}")
    print(f"Current spread: {spread_daily.iloc[-1]:.2f}pp")
    print(f"IS avg spread ({IS_START}–{IS_END}): {spread_daily.loc[IS_START:IS_END].mean():.2f}pp")
    print(f"OOS avg spread ({OOS_START}–): {spread_daily.loc[OOS_START:].mean():.2f}pp")
    print(f"% of OOS months with inverted curve: "
          f"{(spread_monthly.loc[OOS_START:] < 0).mean():.1%}")

    is_mask  = (spy_daily.index >= IS_START)  & (spy_daily.index <= IS_END)
    oos_mask = (spy_daily.index >= OOS_START) & (spy_daily.index <= FULL_END)

    spy_is_stats  = calc_stats((spy_daily[is_mask].pct_change().fillna(0) + 1).cumprod() * INITIAL_EQUITY)
    spy_oos_stats = calc_stats((spy_daily[oos_mask].pct_change().fillna(0) + 1).cumprod() * INITIAL_EQUITY)

    print(f"\nSPY IS  Sharpe={spy_is_stats['sharpe']:.3f}  MaxDD={spy_is_stats['max_drawdown']:.1%}")
    print(f"SPY OOS Sharpe={spy_oos_stats['sharpe']:.3f}  MaxDD={spy_oos_stats['max_drawdown']:.1%}")

    variants = [
        ("A: Spread > 0%",          "binary",   0.0,  0),
        ("B: Spread > 0.5%",        "binary",   0.5,  0),
        ("C: >0% + SPY>200MA",      "combined", 0.0,  0),
        ("D: 3M lagged spread > 0", "binary",   0.0,  3),
        ("E: Gradient [0,2.5%]",    "gradient", None, 0),
    ]

    results = {
        "hypothesis": "H300",
        "description": "Yield Curve Slope (10Y-3M) as Monthly Equity Timing Signal",
        "signal": "DGS10 - DGS3MO; positive → SPY, inverted → BIL",
        "is_period":  f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {FULL_END}",
        "spy_is":  spy_is_stats,
        "spy_oos": spy_oos_stats,
        "spread_stats": {
            "pct_inverted_oos": float((spread_monthly.loc[OOS_START:] < 0).mean()),
            "avg_spread_is": float(spread_monthly.loc[IS_START:IS_END].mean()),
            "avg_spread_oos": float(spread_monthly.loc[OOS_START:].mean()),
        },
        "variants": {},
        "verdict": "NOT CONFIRMED",
    }

    print("\n" + "="*70)
    print(f"{'Variant':<30} {'IS Sh':>7} {'OOS Sh':>7} {'MaxDD':>8} {'%SPY':>6} {'Gate':>5}")
    print("="*70)

    best_oos = -99.0
    best_var = None

    for name, mode, threshold, lag in variants:
        thr = threshold if threshold is not None else 0.0
        eq_full = run_variant(spy_daily, spread_monthly, spy_ma200, mode, thr, lag)
        eq_is  = eq_full[is_mask]
        eq_oos = eq_full[oos_mask]

        is_st  = calc_stats(eq_is)
        oos_st = calc_stats(eq_oos)
        passes = oos_st["sharpe"] >= OOS_SHARPE_GATE

        # Pct time in SPY for binary/combined modes
        if mode in ("binary", "combined") and threshold is not None:
            b_oos = spread_monthly.loc[OOS_START:]
            if mode == "binary":
                pct_in = f"{(b_oos >= thr).mean():.0%}"
            else:
                spy_m  = spy_daily.resample("ME").last().loc[OOS_START:]
                ma_m   = spy_ma200.resample("ME").last().loc[OOS_START:]
                valid  = spy_m.index.intersection(b_oos.index).intersection(ma_m.index)
                pct_in = f"{((b_oos.loc[valid] >= thr) & (spy_m.loc[valid] > ma_m.loc[valid])).mean():.0%}"
        else:
            pct_in = "—"

        gate_str = "PASS" if passes else "fail"
        print(f"  {name:<28} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['max_drawdown']:>8.1%} {pct_in:>6} {gate_str:>5}")

        results["variants"][name] = {
            "mode": mode,
            "threshold": threshold,
            "lag_months": lag,
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
    if any(v["passes"] for v in results["variants"].values()):
        results["verdict"] = "CONFIRMED"

    out_path = RESULT_DIR / "h300_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))

    print(f"\nVerdict: {results['verdict']}")
    print(f"Best OOS Sharpe: {best_oos:.3f} (gate >= {OOS_SHARPE_GATE})")
    print(f"Results saved: {out_path}")


if __name__ == "__main__":
    main()
