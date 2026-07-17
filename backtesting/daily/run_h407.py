"""
H407: Skip-Month Momentum on H026 ETF Rotation
===============================================
H026 uses full 12m momentum (monthly_px / monthly_px.shift(12) - 1).
Academic literature on cross-sectional stock momentum uses "12-1m" (skip-month)
to avoid the 1-month reversal effect (Jegadeesh 1990).
H277 (NASDAQ tech) found skip-month HURTS for tech — momentum is persistent
with no 1-month reversal. H026 has a heterogeneous universe (bonds + commodities
+ sector ETFs + alts). The reversal effect may differ here.

Hypothesis: 12-1m skip-month signal outperforms 12m full-window on H026's
diverse ETF universe because:
1. Commodity ETFs (GLD, DBC, XLE) exhibit short-term reversal
2. Bond ETFs (TLT, IEF) exhibit mean-reversion at 1-month horizon
3. Skip-month avoids the worst entry points after a "hot" month

Variants:
  A: 12-1m skip-month + low 6m vol, top-1        (exact H026 but skip-month)
  B: 12m + 1m reversal bonus composite, top-1     (12m rank + inverted 1m rank)
  C: 12-1m skip-month top-1, no vol ranking       (pure skip momentum)
  D: 12m standard + low 6m vol, top-1            (H026 sanity check)

IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 2.665 (H026 dual-rank 12m baseline)
"""

import warnings
warnings.filterwarnings("ignore")
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

DATA_START   = "2010-01-01"
DATA_END     = "2026-06-30"
IS_START     = pd.Timestamp("2013-01-01")
IS_END       = pd.Timestamp("2020-12-31")
OOS_START    = pd.Timestamp("2021-01-01")
OOS_END      = pd.Timestamp("2026-06-30")
GATE_SHARPE  = 2.665


def load_close(ticker: str) -> pd.Series:
    for prefix in ["h407","h405","h404","h401","h026","h112"]:
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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h407_{ticker}_close.parquet")
    return s


def load_bil() -> pd.Series:
    s = load_close("BIL")
    return s.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).rename("BIL")


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


def run_variant(variant: str, monthly_px: pd.DataFrame, monthly_ret: pd.DataFrame,
                bil_ret: pd.Series) -> pd.Series:
    """Run one variant. Returns monthly return series."""

    # Full 12m momentum (standard H026)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    # Skip-month momentum: 12m excluding most recent month
    mom_skip = monthly_px.shift(1) / monthly_px.shift(13) - 1
    # 1-month return (for reversal signal)
    mom_1 = monthly_px / monthly_px.shift(1) - 1
    # 6m rolling vol for low-vol ranking
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)

    rows = []
    for i in range(13, len(monthly_px)):
        dt = monthly_px.index[i]

        if variant == "A":
            # 12-1m skip + low vol (rank sum)
            m = mom_skip.iloc[i].dropna()
            v = vol_6.iloc[i].dropna()
            valid = m.index.intersection(v.index)
            if len(valid) < 1:
                continue
            score = m[valid].rank() + v[valid].rank(ascending=False)
            top = score.nlargest(1).index[0]
            ret = monthly_ret.iloc[i][top]

        elif variant == "B":
            # 12m standard + inverted 1m (reversal bonus) + low vol
            m12 = mom_12.iloc[i].dropna()
            m1  = mom_1.iloc[i].dropna()
            v   = vol_6.iloc[i].dropna()
            valid = m12.index.intersection(m1.index).intersection(v.index)
            if len(valid) < 1:
                continue
            # rank 12m (high=good) + rank(1-m1) = rank 1m reversal + rank 1/vol (high=good)
            score = m12[valid].rank() + m1[valid].rank(ascending=False) + v[valid].rank(ascending=False)
            top = score.nlargest(1).index[0]
            ret = monthly_ret.iloc[i][top]

        elif variant == "C":
            # Pure 12-1m skip momentum, no vol ranking
            m = mom_skip.iloc[i].dropna()
            if len(m) < 1:
                continue
            top = m.idxmax()
            ret = monthly_ret.iloc[i][top]

        elif variant == "D":
            # Standard H026 sanity check
            m = mom_12.iloc[i].dropna()
            v = vol_6.iloc[i].dropna()
            valid = m.index.intersection(v.index)
            if len(valid) < 1:
                continue
            score = m[valid].rank() + v[valid].rank(ascending=False)
            top = score.nlargest(1).index[0]
            ret = monthly_ret.iloc[i][top]

        else:
            continue

        rows.append((dt, float(ret)))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def evaluate(name: str, rets: pd.Series) -> dict:
    is_r  = rets[(rets.index >= IS_START)  & (rets.index <= IS_END)]
    oos_r = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
    return {
        "variant": name,
        "is_sharpe":  round(sharpe(is_r),  3),
        "oos_sharpe": round(sharpe(oos_r), 3),
        "oos_maxdd":  round(maxdd(oos_r),  4),
        "oos_neg_years": neg_years(oos_r),
        "oos_pass": bool(sharpe(oos_r) > GATE_SHARPE),
    }


def main():
    print("H407: Skip-Month Momentum on H026 ETF Rotation")
    print("=" * 60)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    print(f"IS: {IS_START.date()} – {IS_END.date()}")
    print(f"OOS: {OOS_START.date()} – {OOS_END.date()}\n")

    monthly_px, monthly_ret = build_universe()
    bil_ret = load_bil()

    results = []
    for var in ["A", "B", "C", "D"]:
        rets = run_variant(var, monthly_px, monthly_ret, bil_ret)
        res  = evaluate(var, rets)
        results.append(res)
        status = "✓ PASS" if res["oos_pass"] else "✗"
        print(f"  Var {var}: IS={res['is_sharpe']:6.3f}  OOS={res['oos_sharpe']:6.3f}"
              f"  MDD={res['oos_maxdd']*100:5.1f}%  NegY={res['oos_neg_years']}  {status}")

    # OOS annual breakdown for best variant
    best = max(results, key=lambda x: x["oos_sharpe"])
    print(f"\nBest variant: {best['variant']}  (OOS Sharpe {best['oos_sharpe']})")
    best_rets = run_variant(best["variant"], monthly_px, monthly_ret, bil_ret)
    oos_rets  = best_rets[(best_rets.index >= OOS_START) & (best_rets.index <= OOS_END)]
    print("OOS annual returns:")
    for yr, grp in oos_rets.resample("YE"):
        ann = (1 + grp).prod() - 1
        print(f"  {yr.year}: {ann*100:+.1f}%")

    import json
    (RESULT_DIR / "h407_results.json").write_text(json.dumps(results, indent=2))
    print("\nResults saved → backtesting/results/h407_results.json")


if __name__ == "__main__":
    main()
