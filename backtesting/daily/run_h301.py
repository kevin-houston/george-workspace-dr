"""
H301 — H026 ETF Rotation + VIX Term Structure Safety Overlay
=============================================================

Hypothesis:
  H026 (ETF sector rotation) confirmed with OOS Sharpe ~2.2-3.0 (monthly).
  H296 (VIX term structure Variant C) confirmed with OOS Sharpe 1.116 (daily).

  H296's production note: "Best immediate use: as an overlay to BIL safe-harbor
  decision in existing monthly rotation. If month-end VIX > VIX3M AND SPY < 200MA
  → BIL regardless of rotation signal."

  This directly tests that proposal. At each month-end:
    - Compute H026 top-1 pick (12m momentum + inv-6m-vol ranking)
    - Check VIX term structure condition at month-end
    - If condition signals STRESS: hold BIL instead of H026's pick

  Variants:
    A) H026 standalone (baseline — 12m momentum, no overlay)
    B) H026 + VIX<VIX3M gate (retreat to BIL when term structure inverts)
    C) H026 + VIX<VIX3M + SPY>200MA (H296 Variant C — the confirmed overlay)
    D) H026 + SPY>200MA only (isolate 200MA contribution without VIX term)

  Gate: OOS Sharpe improvement of ≥ 5% over H026 standalone AND MaxDD improvement
  Note: H026 OOS (2020–2026) Sharpe varies ~2.0–2.5; any meaningful improvement counts.

  IS:  2013-01-01 to 2019-12-31
  OOS: 2020-01-01 to 2026-06-15
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
RESULT_DIR     = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2010-01-01"
FULL_END   = "2026-06-15"
IS_START   = "2013-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"

TOP_N    = 1           # H026-style top-1
WEIGHT   = 1.0 / TOP_N

H026_ASSETS = [
    "SPY", "QQQ", "IWM", "EFA", "EEM",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLRE", "XLC",
    "GLD", "SLV", "USO", "UNG",
    "TLT", "IEF", "HYG", "LQD",
    "BIL", "VNQ",
]


def calc_stats(eq: pd.Series) -> dict:
    eq = eq.dropna()
    if len(eq) < 10:
        return {"error": "insufficient data"}
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr   = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol    = rets.std() * np.sqrt(252)
    sharpe = cagr / vol if vol > 0 else 0
    max_dd = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(1 for _, g in rets.groupby(rets.index.year)
                  if (1 + g).prod() - 1 < 0)
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "neg_years":    neg_yrs,
    }


def run_h301(prices: pd.DataFrame, vix: pd.Series, vix3m: pd.Series,
             spy: pd.Series, start: str, end: str, overlay: str) -> pd.Series:
    """
    overlay: 'none' | 'vix' | 'vix+ma' | 'ma'
    Builds daily equity curve using H026 top-1 monthly momentum signal,
    optionally overriding with BIL when market stress detected.
    """
    available = [t for t in H026_ASSETS if t in prices.columns]
    px = prices[available].loc[start:end].ffill().dropna(how="all")
    bil = px["BIL"]

    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)

    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    spy_ma200 = spy.rolling(200).mean()

    equity = INITIAL_EQUITY
    series = []

    for i in range(12, len(monthly_px)):
        month_end  = monthly_px.index[i]
        prev_month = monthly_px.index[i - 1]

        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        valid   = [t for t in valid if t != "BIL"]

        if len(valid) == 0:
            top_hold = ["BIL"]
        else:
            score     = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
            top_hold  = list(score.nlargest(TOP_N).index)

        # Overlay: check VIX term structure + SPY MA at month-end
        if overlay != "none":
            vix_val   = vix.asof(month_end)
            vix3m_val = vix3m.asof(month_end)
            spy_price = spy.asof(month_end)
            spy_ma    = spy_ma200.asof(month_end)

            in_stress = False
            if overlay == "vix" and not pd.isna(vix_val) and not pd.isna(vix3m_val):
                in_stress = vix_val >= vix3m_val
            elif overlay == "vix+ma":
                vix_bad = (not pd.isna(vix_val)) and (not pd.isna(vix3m_val)) and (vix_val >= vix3m_val)
                ma_bad  = (not pd.isna(spy_price)) and (not pd.isna(spy_ma)) and (spy_price < spy_ma)
                in_stress = vix_bad or ma_bad   # either condition triggers safety
            elif overlay == "ma":
                in_stress = (not pd.isna(spy_price)) and (not pd.isna(spy_ma)) and (spy_price < spy_ma)

            if in_stress:
                top_hold = ["BIL"]

        # Simulate daily P&L in next month
        sub_start = prev_month + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += WEIGHT * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)
    return pd.Series({d: v for d, v in series})


def main():
    print("\nH301 — H026 + VIX Term Structure Overlay")
    print("Downloading data...")

    prices_raw = yf.download(H026_ASSETS, start=FULL_START, end=FULL_END,
                             auto_adjust=True, progress=False)
    prices = prices_raw["Close"] if isinstance(prices_raw.columns, pd.MultiIndex) else prices_raw
    prices = prices.ffill()

    vix_raw = yf.download(["^VIX", "^VIX3M", "SPY"], start=FULL_START, end=FULL_END,
                           auto_adjust=True, progress=False)
    vix_px = vix_raw["Close"] if isinstance(vix_raw.columns, pd.MultiIndex) else vix_raw
    vix   = vix_px["^VIX"].ffill()
    vix3m = vix_px["^VIX3M"].ffill()
    spy   = vix_px["SPY"].ffill()

    print(f"  Prices: {len(prices.columns)} assets, {len(prices)} days")
    print(f"  VIX: {vix.first_valid_index().date()} to {vix.index[-1].date()}")
    print(f"  VIX3M: {vix3m.first_valid_index().date()} to {vix3m.index[-1].date()}")

    # Overlay statistics in OOS
    vix_me   = vix.resample("ME").last()
    vix3m_me = vix3m.resample("ME").last()
    spy_me   = spy.resample("ME").last()
    spy_ma_me = spy.rolling(200).mean().resample("ME").last()
    vix_stress  = (vix_me >= vix3m_me).loc[OOS_START:]
    ma_stress   = (spy_me < spy_ma_me).loc[OOS_START:]
    both_stress = (vix_stress | ma_stress)
    print(f"\n  OOS stress stats:")
    print(f"    VIX backwardation: {vix_stress.mean():.1%} of months")
    print(f"    SPY below 200MA:   {ma_stress.mean():.1%} of months")
    print(f"    Either condition:  {both_stress.mean():.1%} of months")

    variants = [
        ("A: H026 standalone",   "none"),
        ("B: H026 + VIX gate",   "vix"),
        ("C: H026 + VIX+200MA",  "vix+ma"),
        ("D: H026 + 200MA only", "ma"),
    ]

    results = {
        "hypothesis": "H301",
        "description": "H026 ETF Rotation + VIX Term Structure Safety Overlay",
        "signal": "H026 top-1 momentum; BIL override when VIX>VIX3M [OR SPY<200MA]",
        "is_period":  f"{IS_START} to {IS_END}",
        "oos_period": f"{OOS_START} to {FULL_END}",
        "variants": {},
        "verdict": "NOT CONFIRMED",
    }

    print("\n" + "="*72)
    print(f"{'Variant':<30} {'IS Sh':>7} {'OOS Sh':>7} {'MaxDD':>8} {'NegYr':>6} {'Gate':>5}")
    print("="*72)

    base_oos_sharpe = None
    base_oos_maxdd  = None
    best_oos = -99.0
    best_var = None

    for name, overlay in variants:
        eq_full = run_h301(prices, vix, vix3m, spy, FULL_START, FULL_END, overlay)
        if eq_full.empty:
            print(f"  {name:<28}  (no data)")
            continue

        is_mask  = (eq_full.index >= IS_START) & (eq_full.index <= IS_END)
        oos_mask = (eq_full.index >= OOS_START)

        is_st  = calc_stats(eq_full[is_mask])
        oos_st = calc_stats(eq_full[oos_mask])

        if name.startswith("A"):
            base_oos_sharpe = oos_st["sharpe"]
            base_oos_maxdd  = oos_st["max_drawdown"]
            gate_str = "BASE"
            passes = False
        else:
            # Gate: OOS Sharpe ≥ 5% improvement over base
            sharpe_ok = (base_oos_sharpe and oos_st["sharpe"] >= base_oos_sharpe * 1.05)
            maxdd_ok  = (base_oos_maxdd  and oos_st["max_drawdown"] >= base_oos_maxdd * 0.90)
            passes = sharpe_ok  # primary gate: Sharpe improvement
            gate_str = "PASS" if passes else "fail"

        print(f"  {name:<28} {is_st['sharpe']:>7.3f} {oos_st['sharpe']:>7.3f} "
              f"{oos_st['max_drawdown']:>8.1%} {oos_st.get('neg_years',0):>6} {gate_str:>5}")

        results["variants"][name] = {
            "overlay": overlay,
            "is_stats":  is_st,
            "oos_stats": oos_st,
            "passes": passes,
        }

        if oos_st["sharpe"] > best_oos:
            best_oos = oos_st["sharpe"]
            best_var = name

    print("="*72)

    results["h026_base_oos_sharpe"] = base_oos_sharpe
    results["best_variant"] = best_var
    results["best_oos_sharpe"] = round(best_oos, 4)

    if any(v.get("passes", False) for v in results["variants"].values()):
        results["verdict"] = "CONFIRMED"

    out_path = RESULT_DIR / "h301_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nVerdict: {results['verdict']}")
    print(f"H026 base OOS Sharpe: {base_oos_sharpe:.3f}")
    print(f"Best: {best_var} ({best_oos:.3f})")
    print(f"Results: {out_path}")


if __name__ == "__main__":
    main()
