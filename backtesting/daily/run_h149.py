"""
H149 — Total Rotation/IBS Budget Re-split
==========================================

H148 confirmed H026 should own 100% of the rotation budget (70%), with
H041a and H045 at 0%. The portfolio is now H026 (70%) + IBS (30%).

H026 is the dominant alpha. The question: should the rotation budget itself
be larger than 70%? The original 70/30 split was set in H122 when H026 was
one of three rotation legs. Now that H026 is the sole rotation strategy,
the IBS strategies (XLK/SMH/IGV) must be evaluated against H026 directly.

IBS strategies (XLK=20%, SMH=8%, IGV=2%) are daily mean-reversion tactics
on tech ETFs. They provide smoother returns but potentially lower CAGR than
H026's monthly trend rotation. If H026's risk-adjusted return per unit of
capital is higher than IBS, we should shift more capital to H026.

Tests:
  A) Rotation=70%, IBS=30%  — H148 baseline (XLK=20%, SMH=8%, IGV=2%)
  B) Rotation=75%, IBS=25%  — (XLK=17%, SMH=6%, IGV=2%)
  C) Rotation=80%, IBS=20%  — (XLK=14%, SMH=5%, IGV=1%)
  D) Rotation=85%, IBS=15%  — (XLK=11%, SMH=3%, IGV=1%)
  E) Rotation=90%, IBS=10%  — (XLK=7%, SMH=2%, IGV=1%)
  F) Rotation=95%, IBS=5%   — (XLK=4%, SMH=1%, IGV=0%)
  G) Rotation=100%, IBS=0%  — Pure H026 only

IBS weights scaled proportionally (3.5:1:0.1 ratio: XLK:SMH:IGV).
H026 always gets all of the rotation budget.

Baseline: H148 — OOS 127.9462, AltOOS 675.3286, Sharpe 3.153
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

H026_ASSETS  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
                "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]

IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}

VOL_TARGET_H026 = 0.20
VOL_WINDOW      = 6
VOL_CLAMP       = (0.5, 2.0)

H026_TSMOM_THRESHOLD = 0.05

_PREFIXES = [f"h{i:03d}" for i in range(62, 150)]

# (label, rotation_frac, ibs_xlk, ibs_smh, ibs_igv)
VARIANTS = [
    ("A) Rotation=70%, IBS=30% (H148)",  0.70, 0.200, 0.080, 0.020),
    ("B) Rotation=75%, IBS=25%",         0.75, 0.167, 0.067, 0.017),
    ("C) Rotation=80%, IBS=20%",         0.80, 0.134, 0.054, 0.014),
    ("D) Rotation=85%, IBS=15%",         0.85, 0.100, 0.040, 0.010),
    ("E) Rotation=90%, IBS=10%",         0.90, 0.067, 0.027, 0.007),
    ("F) Rotation=95%, IBS=5%",          0.95, 0.034, 0.013, 0.003),
    ("G) Rotation=100%, IBS=0%",         1.00, 0.000, 0.000, 0.000),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h149_{ticker}_ohlc_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h149_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ─────────────────────────────────────────────────────────────────────────────
# Strategy builders
# ─────────────────────────────────────────────────────────────────────────────

def build_rotation_tsmom(tickers, start, end, n_hold=1,
                          tsmom_lookbacks=None, tsmom_threshold=0.0):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    lookbacks  = tsmom_lookbacks or []
    max_lb     = max(lookbacks + [12])
    mom_by_lb  = {lb: monthly_px / monthly_px.shift(lb) - 1 for lb in set(lookbacks)}
    rows = []
    for i in range(max_lb, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid = (m12_row.index.intersection(vol_row.index)
                 .intersection(m6_row.index).intersection(m3_row.index))
        passing = list(valid)
        for lb in lookbacks:
            lb_row = mom_by_lb[lb].iloc[i]
            passing = [t for t in passing
                       if t in lb_row.index
                       and not np.isnan(float(lb_row[t]))
                       and float(lb_row[t]) > tsmom_threshold]
        if len(passing) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue
        n = min(n_hold, len(passing))
        score = (m12_row.reindex(passing).rank() + m6_row.reindex(passing).rank() +
                 m3_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False))
        top   = list(score.nlargest(n).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"] - prev_cl) / prev_cl
    equity  = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i]);  c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o - 1) if o > 0 else 0.0
        ret_cc = (c/cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1 + ret_oc)
        else:
            days_held += 1; equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def blend(h026_rets, ibs_rets, rotation_frac, ibs_w):
    """Simple fixed-weight blend: H026 gets rotation_frac, IBS gets proportional shares."""
    all_rets = {"h026": h026_rets, **ibs_rets}
    df = pd.DataFrame(all_rets).dropna(how="all")
    weights = {"h026": rotation_frac, **ibs_w}
    total_w = sum(weights.values())
    combined = pd.Series(0.0, index=df.index)
    for i in range(len(df)):
        combined.iloc[i] = sum(
            float(df[key].iloc[i]) * weights.get(key, 0.0)
            for key in df.columns
            if not np.isnan(float(df[key].iloc[i]))
        )
    return combined.dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0, "cumul": 1.0}
    eq   = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1/n_yr) - 1
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr": round(cagr,4), "sharpe": round(sharpe,4),
            "max_drawdown": round(max_dd,4), "n_months": len(r),
            "neg_years": neg_yrs, "cumul": round(float(eq.iloc[-1]),4)}


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<50} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H149 — Total Rotation/IBS Budget Re-split")
    print("=" * 80)
    print("H148 baseline: OOS 127.9462, AltOOS 675.3286, Sharpe 3.153\n")

    print("Pre-computing IBS …")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap))
        print(f"  {sym} done")

    print("\nPre-computing H026 (+5% threshold) …")
    h026 = build_rotation_tsmom(H026_ASSETS, FULL_START, FULL_END,
                                 n_hold=1, tsmom_lookbacks=[12],
                                 tsmom_threshold=H026_TSMOM_THRESHOLD)
    print("  done")

    print("\n" + "=" * 80)
    print("Results")
    print("=" * 80)

    results = {}
    b_oos = b_alt = None

    for label, rot_frac, xlk_w, smh_w, igv_w in VARIANTS:
        ibs_w = {}
        if xlk_w > 0: ibs_w["XLK"] = xlk_w
        if smh_w > 0: ibs_w["SMH"] = smh_w
        if igv_w > 0: ibs_w["IGV"] = igv_w
        port = blend(h026, ibs_rets, rot_frac, ibs_w)
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("A)"):
            b_oos, b_alt = oos_s, alt_s

    print("\n" + "─" * 80)
    print("Comparison vs H148 baseline (A = 70/30 split):\n")
    confirmed_any = False
    for label, rot_frac, xlk_w, smh_w, igv_w in VARIANTS:
        if label.startswith("A)"):
            continue
        oos_s, alt_s = results[label]
        d_oos = oos_s["cumul"] - b_oos["cumul"]
        d_alt = alt_s["cumul"] - b_alt["cumul"]
        verdict = "✓ CONFIRMED" if d_oos > 0 and d_alt > 0 else "✗ not confirmed"
        if d_oos > 0 and d_alt > 0:
            confirmed_any = True
        print(f"  {label}")
        print(f"    OOS: {oos_s['cumul']:.4f} (Δ{d_oos:+.4f})  "
              f"Alt: {alt_s['cumul']:.4f} (Δ{d_alt:+.4f})  "
              f"Sharpe: {oos_s['sharpe']:.3f}  MaxDD: {oos_s['max_drawdown']*100:.1f}%  "
              f"{verdict}")
        print()

    print("─" * 80)
    if confirmed_any:
        candidates = {k: v for k, v in results.items() if not k.startswith("A)")}
        best_label = max(candidates, key=lambda k: candidates[k][0]["cumul"] + candidates[k][1]["cumul"])
        best_oos, best_alt = candidates[best_label]
        best_var = next(v for v in VARIANTS if v[0] == best_label)
        d_oos = best_oos["cumul"] - b_oos["cumul"]
        d_alt = best_alt["cumul"] - b_alt["cumul"]
        print(f"\n  VERDICT: CONFIRMED — {best_label}")
        print(f"  OOS Δ{d_oos:+.4f}  AltOOS Δ{d_alt:+.4f}  "
              f"Sharpe {b_oos['sharpe']:.3f}→{best_oos['sharpe']:.3f}  "
              f"MaxDD {b_oos['max_drawdown']*100:.1f}%→{best_oos['max_drawdown']*100:.1f}%")
        print(f"  Rotation={best_var[1]*100:.0f}% H026, IBS={100-best_var[1]*100:.0f}% (XLK={best_var[2]*100:.1f}%,SMH={best_var[3]*100:.1f}%,IGV={best_var[4]*100:.1f}%)")
    else:
        print(f"\n  VERDICT: NOT CONFIRMED — 70% rotation / 30% IBS is already optimal")
    print()


if __name__ == "__main__":
    main()
