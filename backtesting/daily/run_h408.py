"""
H408: Absolute Momentum Floor on H026 ETF Top-1 Selection
==========================================================
H026 uses relative momentum (dual-rank 12m+LowVol) to pick the best ETF
from 23. The top pick could still have negative absolute return (e.g., in a
severe bear market where everything falls, XLE might be "least bad" but still
negative). Antonacci's Dual Momentum (H256, NOT CONFIRMED) added an absolute
momentum gate globally — but H256 failed because 2022 crashed both equity AND
bonds simultaneously, eliminating the defensive escape.

Key difference from H256: H026 already routes to BIL organically when BIL
ranks highest in the dual-rank composite. The absolute floor is a VETO on
top picks that are losing money — even if they rank best relatively.

Hypothesis: Adding an absolute momentum floor reduces H026 drawdowns in
concentrated downtrends without sacrificing bull-market returns, because
the floor only triggers when the best available ETF is also losing money.

Variants:
  A: Top-1 only if 12m abs return > 0.0  (strict floor)
  B: Top-1 only if 12m abs return > -5%  (lenient, allows mild losers)
  C: Top-1 only if 12m abs return > -10% (very lenient sanity test)
  D: Top-1 only if 6m abs return > 0.0   (shorter lookback floor)
  E: H026 standard (sanity, must match ~2.665 OOS Sharpe)

IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 2.665 (H026 dual-rank 12m baseline on this sub-period)
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

H026_UNIVERSE = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"
]

DATA_START  = "2010-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 2.665


def load_close(ticker: str) -> pd.Series:
    for prefix in ["h408","h407","h405","h404","h026","h112"]:
        for pat in [
            CACHE_DIR / f"{prefix}_{ticker}_close_{DATA_START}_{DATA_END}.parquet",
            CACHE_DIR / f"{prefix}_{ticker}_close.parquet",
        ]:
            if pat.exists():
                df = pd.read_parquet(pat)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h408_{ticker}_close.parquet")
    return s


def build_universe() -> tuple:
    closes = {}
    for t in H026_UNIVERSE:
        try:
            closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    return monthly_px, monthly_ret


def load_bil_monthly(monthly_px: pd.DataFrame, monthly_ret: pd.DataFrame) -> pd.Series:
    if "BIL" in monthly_ret.columns:
        return monthly_ret["BIL"]
    return pd.Series(0.0, index=monthly_ret.index)


def sharpe(rets: pd.Series, ann: int = 12) -> float:
    r = rets.dropna()
    if len(r) < 6 or r.std() == 0:
        return float("nan")
    return (r.mean() / r.std()) * np.sqrt(ann)


def maxdd(rets: pd.Series) -> float:
    cum = (1 + rets.fillna(0)).cumprod()
    roll_max = cum.cummax()
    return float((cum / roll_max - 1).min())


def neg_years(rets: pd.Series) -> int:
    ann = rets.resample("YE").apply(lambda x: (1+x).prod()-1)
    return int((ann < 0).sum())


def cash_pct(rets: pd.Series, full_rets: pd.Series) -> float:
    """Fraction of months routed to BIL."""
    # We'll track this via a flag in run_variant instead
    return 0.0


def run_variant(variant: str, monthly_px: pd.DataFrame,
                monthly_ret: pd.DataFrame, abs_floor: float,
                abs_window: int = 12) -> tuple[pd.Series, float]:
    """
    Returns (monthly_returns, cash_fraction).
    abs_floor: minimum absolute return threshold; NaN means no floor (sanity).
    abs_window: lookback in months for absolute momentum check.
    """
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    mom_6  = monthly_px / monthly_px.shift(6) - 1
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    bil    = load_bil_monthly(monthly_px, monthly_ret)

    rows = []
    cash_months = 0
    total_months = 0

    lookback = abs_window

    for i in range(max(12, lookback), len(monthly_px)):
        dt = monthly_px.index[i]

        m_rel = mom_12.iloc[i].dropna()
        v     = vol_6.iloc[i].dropna()
        valid = m_rel.index.intersection(v.index)
        if len(valid) < 1:
            continue

        # Relative score: rank by momentum + rank by low vol
        score = m_rel[valid].rank() + v[valid].rank(ascending=False)
        top_etf = score.nlargest(1).index[0]
        total_months += 1

        if not pd.isna(abs_floor):
            # Absolute momentum check
            if abs_window == 12:
                abs_ret = mom_12.iloc[i].get(top_etf, float("nan"))
            else:
                abs_ret = mom_6.iloc[i].get(top_etf, float("nan"))

            if pd.isna(abs_ret) or abs_ret < abs_floor:
                # Veto: route to BIL
                ret = bil.get(dt, 0.0)
                cash_months += 1
            else:
                ret = float(monthly_ret.iloc[i][top_etf])
        else:
            # Standard H026 — no floor
            ret = float(monthly_ret.iloc[i][top_etf])

        rows.append((dt, ret))

    port = pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))
    cash_frac = cash_months / total_months if total_months > 0 else 0.0
    return port, cash_frac


def evaluate(name: str, rets: pd.Series, cash_frac: float) -> dict:
    is_r  = rets[(rets.index >= IS_START)  & (rets.index <= IS_END)]
    oos_r = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
    return {
        "variant": name,
        "is_sharpe":  round(sharpe(is_r),  3),
        "oos_sharpe": round(sharpe(oos_r), 3),
        "oos_maxdd":  round(maxdd(oos_r),  4),
        "oos_neg_years": neg_years(oos_r),
        "cash_pct_oos": round(cash_frac * 100, 1),
        "oos_pass": bool(sharpe(oos_r) > GATE_SHARPE),
    }


def main():
    print("H408: Absolute Momentum Floor on H026 ETF Top-1")
    print("=" * 60)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    print(f"IS: {IS_START.date()} – {IS_END.date()}")
    print(f"OOS: {OOS_START.date()} – {OOS_END.date()}\n")

    monthly_px, monthly_ret = build_universe()

    variant_configs = [
        ("A", 0.00,  12),   # strict 12m floor
        ("B", -0.05, 12),   # lenient 12m floor (-5%)
        ("C", -0.10, 12),   # very lenient 12m floor (-10%)
        ("D", 0.00,  6),    # strict 6m absolute floor
        ("E", float("nan"), 12),  # standard H026 sanity
    ]

    results = []
    best_rets_store = {}

    for var, floor, window in variant_configs:
        rets, cash_frac = run_variant(var, monthly_px, monthly_ret, floor, window)
        res = evaluate(var, rets, cash_frac)
        results.append(res)
        best_rets_store[var] = rets

        status = "✓ PASS" if res["oos_pass"] else "✗"
        floor_str = f"{floor*100:+.0f}%" if not pd.isna(floor) else "none"
        print(f"  Var {var} (floor={floor_str}, {window}m): "
              f"IS={res['is_sharpe']:6.3f}  OOS={res['oos_sharpe']:6.3f}"
              f"  MDD={res['oos_maxdd']*100:5.1f}%  Cash={res['cash_pct_oos']:4.1f}%  {status}")

    # Annual breakdown for best variant
    best = max(results, key=lambda x: x["oos_sharpe"])
    print(f"\nBest variant: {best['variant']}  (OOS Sharpe {best['oos_sharpe']}, "
          f"Cash {best['cash_pct_oos']}%)")
    best_rets = best_rets_store[best["variant"]]
    oos_rets  = best_rets[(best_rets.index >= OOS_START) & (best_rets.index <= OOS_END)]
    print("OOS annual returns:")
    for yr, grp in oos_rets.resample("YE"):
        ann = (1 + grp).prod() - 1
        print(f"  {yr.year}: {ann*100:+.1f}%")

    (RESULT_DIR / "h408_results.json").write_text(json.dumps(results, indent=2))
    print("\nResults saved → backtesting/results/h408_results.json")


if __name__ == "__main__":
    main()
