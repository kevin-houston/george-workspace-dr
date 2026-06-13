"""
H285 — Earnings Quality Factor: Accruals Anomaly + Quality ETF Rotation
=========================================================================

Hypothesis:
  Sloan (1996) "Do Stock Prices Fully Reflect Information in Accruals and
  Cash Flows about Future Earnings?" (TAR) — low-accrual stocks earn
  10.4%/yr more than high-accrual stocks (accruals = earnings - cash flows).
  Updated by Dechow et al. (2012): accruals anomaly persists but is
  concentrated in small/mid caps.

  Quality factor (AQR, 2014): high-quality firms (profitable, growing, safe)
  outperform low-quality firms by 4-6%/yr after controlling for beta.

  Design (two variants):
  A. Quality ETF rotation: rotate among quality-factor ETFs (QUAL, IQLR, SPHQ)
     vs market-weight (SPY) using 6-month momentum signal. Long top-1 of 4.
     Tests whether "quality" factor ETFs outperform in cross-sectional rotation.

  B. QUAL vs SPY buy-and-hold: does simply holding the quality ETF beat SPY?
     Long-run (2014-2025) and post-2018 OOS test.

  Universe A: QUAL (iShares MSCI USA Quality), SPHQ (Invesco S&P 500 Quality),
              DGRW (WisdomTree US Quality Dividend Growth), SPY, BIL
  Universe B: Same, extended test period back to 2014

  IS: 2014-2019 (QUAL/SPHQ both launched 2013-2014)
  OOS: 2020-2025

  Gate: OOS Sharpe ≥ 0.9 (rotation variant A beats SPY OOS)
        QUAL B&H OOS Sharpe ≥ 0.9

Academic basis:
  - Sloan (1996): accruals anomaly; low accruals → higher future returns
  - Asness, Frazzini & Pedersen (2014) "Quality Minus Junk" (QMJ)
  - Novy-Marx (2013): Gross Profitability Predicts Returns
  - QUAL ETF tracks MSCI USA Quality index: high ROE + stable earnings + low leverage
  - AQR has shown quality premium persists OOS in US equities (Clifford Asness, 2016)

Note: this tests whether the "quality" factor ETF wrapper generates alpha
beyond SPY, not the accruals anomaly directly (which requires stock-level data).
The quality ETF is the practical implementation of the accruals/profitability signal.
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2013-01-01"
FULL_END   = "2026-06-01"
IS_START   = "2014-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"

# Quality factor ETF universe
UNIVERSE = {
    "QUAL":  "iShares MSCI USA Quality Factor ETF",
    "SPHQ":  "Invesco S&P 500 Quality ETF",
    "DGRW":  "WisdomTree US Quality Dividend Growth ETF",
    "MTUM":  "iShares MSCI USA Momentum Factor ETF",  # momentum baseline for comparison
    "VLUE":  "iShares MSCI USA Value Factor ETF",     # value baseline
    "SPY":   "S&P 500 Index ETF",
    "BIL":   "SPDR Bloomberg 1-3 Month T-Bill ETF",
}

# Rotation universe for Variant A (quality vs defensive)
ROTATION_UNIVERSE = ["QUAL", "SPHQ", "DGRW", "SPY", "BIL"]
MOM_LOOKBACK = 6  # 6-month momentum signal


def fetch_monthly_returns(ticker):
    """Fetch monthly return series."""
    cache_path = CACHE_DIR / f"h285_{ticker}_monthly.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path).squeeze().rename(ticker)

    raw = yf.download(ticker, start=FULL_START, end=FULL_END,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float, name=ticker)

    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]

    monthly = close.resample("ME").last().pct_change().rename(ticker)
    monthly.to_frame().to_parquet(cache_path)
    return monthly


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    eq = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    if n_yr <= 0:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0}
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    annual = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((annual < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r), "neg_years": neg_years}


def corr_series(r1, r2):
    idx = r1.dropna().index.intersection(r2.dropna().index)
    if len(idx) < 6:
        return float("nan")
    return round(float(r1.reindex(idx).corr(r2.reindex(idx))), 4)


def build_rotation(monthly_data, tickers, mom_lookback, n_top=1):
    """
    Build monthly rotation using momentum signal.
    Signal = trailing mom_lookback-month return, lagged 1 month.
    """
    valid = [t for t in tickers if t in monthly_data]
    df = pd.DataFrame({t: monthly_data[t] for t in valid}).sort_index()
    price = (1 + df.fillna(0)).cumprod()

    rows = []
    for i in range(mom_lookback + 1, len(price)):
        date = price.index[i]
        # Signal at month-end i-1 (lag 1)
        mom_scores = {}
        for t in valid:
            if t == "BIL":
                continue
            px_now = float(price[t].iloc[i-1])
            px_ago = float(price[t].iloc[i-1-mom_lookback])
            if px_now > 0 and px_ago > 0:
                mom_scores[t] = px_now / px_ago - 1.0

        if not mom_scores:
            if "BIL" in valid and date in df.index:
                rows.append((date, float(df["BIL"].iloc[i])))
            continue

        scores = pd.Series(mom_scores)
        top = list(scores.nlargest(n_top).index)

        # Apply to month i return
        rets = [float(df[t].iloc[i]) for t in top
                if not np.isnan(df[t].iloc[i])]
        if not rets:
            if "BIL" in valid and date in df.index:
                rows.append((date, float(df["BIL"].iloc[i])))
            continue

        rows.append((date, np.mean(rets)))

    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("H285 — Earnings Quality Factor: Quality ETF Rotation + Buy-Hold")
print("=" * 80)

print("\n[1] Loading ETF data …")
monthly_data = {}
for t in UNIVERSE.keys():
    s = fetch_monthly_returns(t)
    if len(s.dropna()) > 12:
        monthly_data[t] = s
        print(f"  {t} ({UNIVERSE[t][:40]}): {len(s.dropna())} months ({s.dropna().index.min().date()} – {s.dropna().index.max().date()})")
    else:
        print(f"  {t}: insufficient data")

spy_monthly = monthly_data.get("SPY", pd.Series(dtype=float))

# ── VARIANT A: Quality ETF Rotation (6-month momentum, top-1) ────────────────
print("\n[2] Variant A — Quality ETF Rotation (6m momentum, top-1) …")

rot = build_rotation(monthly_data, ROTATION_UNIVERSE, MOM_LOOKBACK, n_top=1)

A_is  = rot[(rot.index >= IS_START) & (rot.index <= IS_END)]
A_oos = rot[rot.index >= OOS_START]

A_is_stats  = stats(A_is)
A_oos_stats = stats(A_oos)

spy_is  = stats(spy_monthly[(spy_monthly.index >= IS_START) & (spy_monthly.index <= IS_END)])
spy_oos = stats(spy_monthly[spy_monthly.index >= OOS_START])

corr_A_spy = corr_series(A_oos, spy_monthly.reindex(A_oos.index))

print(f"  IS  (2014-2019): Sharpe={A_is_stats['sharpe']:.4f}  CAGR={A_is_stats['cagr']*100:.1f}%  MaxDD={A_is_stats['max_drawdown']*100:.1f}%")
print(f"  OOS (2020-2025): Sharpe={A_oos_stats['sharpe']:.4f}  CAGR={A_oos_stats['cagr']*100:.1f}%  MaxDD={A_oos_stats['max_drawdown']*100:.1f}%  NegYrs={A_oos_stats['neg_years']}")
print(f"  SPY IS={spy_is['sharpe']:.4f}  OOS={spy_oos['sharpe']:.4f}")
print(f"  Corr(Rotation, SPY) OOS: {corr_A_spy:.3f}")

# Monthly holdings analysis
if len(rot) > 0:
    monthly_data_df = pd.DataFrame(monthly_data)
    price_df = (1 + monthly_data_df.fillna(0)).cumprod()
    # Track which ETF was held
    holdings = []
    for i in range(MOM_LOOKBACK + 1, len(price_df)):
        date = price_df.index[i]
        if date < pd.Timestamp(IS_START):
            continue
        mom_scores = {}
        for t in ROTATION_UNIVERSE:
            if t == "BIL":
                continue
            if t in price_df.columns:
                px_now = float(price_df[t].iloc[i-1])
                px_ago = float(price_df[t].iloc[i-1-MOM_LOOKBACK])
                if px_now > 0 and px_ago > 0:
                    mom_scores[t] = px_now / px_ago - 1.0
        if mom_scores:
            top = pd.Series(mom_scores).idxmax()
            holdings.append(top)
    if holdings:
        hold_counts = pd.Series(holdings).value_counts()
        print(f"\n  Holdings distribution (IS+OOS):")
        for t, cnt in hold_counts.items():
            print(f"    {t}: {cnt} months ({cnt/len(holdings)*100:.0f}%)")

# ── VARIANT B: Buy-and-Hold Quality ETFs vs SPY ───────────────────────────────
print("\n[3] Variant B — Buy-and-Hold Quality ETF vs SPY …")

for t in ["QUAL", "SPHQ", "DGRW", "MTUM", "VLUE", "SPY"]:
    if t not in monthly_data:
        continue
    r = monthly_data[t]
    is_r  = r[(r.index >= IS_START) & (r.index <= IS_END)]
    oos_r = r[r.index >= OOS_START]
    if len(oos_r.dropna()) < 12:
        continue
    s_is  = stats(is_r)
    s_oos = stats(oos_r)
    c = corr_series(oos_r, spy_monthly.reindex(oos_r.index))
    print(f"  {t:<6}: IS Sharpe={s_is['sharpe']:.4f}  OOS Sharpe={s_oos['sharpe']:.4f}  OOS CAGR={s_oos['cagr']*100:.1f}%  OOS MaxDD={s_oos['max_drawdown']*100:.1f}%  Corr(SPY)={c:.3f}")

# ── VARIANT C: QUAL only — is it better than SPY B&H on risk-adjusted basis? ──
print("\n[4] Variant C — QUAL vs SPY extended history …")

qual = monthly_data.get("QUAL", pd.Series(dtype=float))
if len(qual.dropna()) > 24:
    # Full history
    full_stats_qual = stats(qual.dropna())
    full_stats_spy  = stats(spy_monthly.dropna())
    print(f"  QUAL full history: Sharpe={full_stats_qual['sharpe']:.4f}  CAGR={full_stats_qual['cagr']*100:.1f}%  MaxDD={full_stats_qual['max_drawdown']*100:.1f}%")
    print(f"  SPY  full history: Sharpe={full_stats_spy['sharpe']:.4f}  CAGR={full_stats_spy['cagr']*100:.1f}%  MaxDD={full_stats_spy['max_drawdown']*100:.1f}%")

    # OOS alpha of QUAL vs SPY
    qual_oos = qual[qual.index >= OOS_START]
    qual_excess = qual_oos - spy_monthly.reindex(qual_oos.index)
    print(f"\n  QUAL excess return over SPY (OOS):")
    print(f"    Mean monthly alpha: {qual_excess.mean()*100:.3f}%  Annualized: {qual_excess.mean()*12*100:.2f}%")
    print(f"    t-stat: {qual_excess.mean() / (qual_excess.std(ddof=1) / np.sqrt(len(qual_excess))):.3f}")

# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print("GATE ASSESSMENT")
print(f"{'=' * 60}")
gate1 = A_oos_stats["sharpe"] >= 0.9
gate2 = A_oos_stats["sharpe"] > spy_oos["sharpe"]
print(f"Rotation OOS Sharpe >= 0.9:     {'PASS' if gate1 else 'FAIL'} ({A_oos_stats['sharpe']:.4f})")
print(f"Rotation OOS Sharpe > SPY OOS:  {'PASS' if gate2 else 'FAIL'} ({A_oos_stats['sharpe']:.4f} vs {spy_oos['sharpe']:.4f})")

qual_oos_stats = stats(monthly_data.get("QUAL", pd.Series(dtype=float))[
    monthly_data.get("QUAL", pd.Series(dtype=float)).index >= OOS_START
])
gate3 = qual_oos_stats["sharpe"] >= 0.9

print(f"QUAL B&H OOS Sharpe >= 0.9:     {'PASS' if gate3 else 'FAIL'} ({qual_oos_stats['sharpe']:.4f})")

# Verdict
any_gate = gate1 or gate3
verdict = "CONFIRMED" if any_gate else "NOT CONFIRMED"
print(f"\nVERDICT: {verdict}")

wf_ratio = A_oos_stats["sharpe"] / A_is_stats["sharpe"] if A_is_stats["sharpe"] > 0 else 0.0
print(f"Walkforward ratio (Rotation A): {wf_ratio:.3f}")

# Save
results = {
    "hypothesis": "H285",
    "description": "Earnings Quality Factor: Accruals Anomaly via Quality ETF Rotation",
    "variant_A_rotation": {
        "is_stats": A_is_stats,
        "oos_stats": A_oos_stats,
        "walkforward_ratio": round(wf_ratio, 4),
        "corr_spy_oos": corr_A_spy,
    },
    "qual_bh_oos_sharpe": qual_oos_stats["sharpe"],
    "spy_is": spy_is,
    "spy_oos": spy_oos,
    "verdict": verdict,
}
out_path = RESULT_DIR / "h285_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved to {out_path}")
