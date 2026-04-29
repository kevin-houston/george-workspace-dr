"""
H129 — Weight Re-Optimization Post-H128
========================================

Current production weights (H122 → H128): h041a=22%, h026=27%, h045=21%.
H045 now has a 3m TSMOM filter — lower volatility, better Sharpe.

Hypothesis: H045's improved signal warrants a higher weight allocation.
  Also test increasing H026 (confirmed to help AltOOS historically).

Sweep:
  Phase 1 — H045 sweep (h041a fixed at 22%, h026 fixed at 27%):
    H045: 14%, 17%, 21% (baseline), 25%, 28%
    Rotation total = 22% + 27% + H045_W; IBS fills rest.

  Phase 2 — Joint sweep (top candidates from Phase 1):
    Vary h041a and h045 around the Phase 1 best.

Reference (H128 baseline): OOS 21.6336, AltOOS 71.5302, Sharpe 4.553

NOTE: All rotation allocations renorm to 70% (same as H122).
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

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}

# H128 production weights (baseline for this sweep)
PROD_W_BASE = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

VOL_TARGET_H026 = 0.15
VOL_WINDOW_H026 = 6
VOL_CLAMP_H026  = (0.5, 2.0)
ROTATION_WEIGHT = 0.70

_PREFIXES = [f"h{i:03d}" for i in range(62, 130)]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers (reused from H128)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h129_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
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
    cp = CACHE_DIR / f"h129_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
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

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter: bool = False):
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
    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid = (m12_row.index.intersection(vol_row.index)
                 .intersection(m6_row.index).intersection(m3_row.index))
        if tsmom_filter:
            valid = pd.Index([t for t in valid if m12_row.get(t, 0) > 0])
        if len(valid) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue
        if len(valid) < n_hold:
            rows.append((monthly_px.index[i], monthly_rt.iloc[i][list(valid)].mean()))
            continue
        score = (m12_row[valid].rank() + m6_row[valid].rank() +
                 m3_row[valid].rank() + vol_row[valid].rank(ascending=False))
        top   = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def build_h045_3m_tsmom(tickers, start, end, n_hold=2):
    """H045 with 3m TSMOM filter (H128 production)."""
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
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid   = m12_row.index.intersection(vol_row.index).intersection(m3_row.index)
        passing = [t for t in valid if float(m3_row.get(t, 0)) > 0]
        if len(passing) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue
        n = min(n_hold, len(passing))
        score = m12_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False)
        top   = list(score.nlargest(n).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom  = (df["high"] - df["low"]).replace(0, np.nan)
    ibs    = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"] - prev_cl) / prev_cl
    equity = INITIAL_EQUITY
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


# ─────────────────────────────────────────────────────────────────────────────
# Blend with custom weights (vol-targeted H026)
# ─────────────────────────────────────────────────────────────────────────────

def blend_vol_targeted(sub_rets, prod_w: dict):
    df = pd.DataFrame(sub_rets).dropna(how="all")
    rot_keys = ["h041a", "h026", "h045"]
    combined = pd.Series(0.0, index=df.index)
    for i in range(len(df)):
        row_weights = dict(prod_w)
        if "h026" in df.columns and i >= VOL_WINDOW_H026:
            window = df["h026"].iloc[i - VOL_WINDOW_H026:i]
            if len(window) >= 3:
                rv = float(window.std(ddof=1)) * np.sqrt(12)
                if rv > 0:
                    scalar = float(np.clip(VOL_TARGET_H026 / rv, *VOL_CLAMP_H026))
                    row_weights["h026"] = prod_w["h026"] * scalar
                    cur_rot = sum(row_weights.get(k, 0.0) for k in rot_keys if k in df.columns)
                    if cur_rot > 0:
                        for k in rot_keys:
                            if k in df.columns:
                                row_weights[k] = row_weights[k] * ROTATION_WEIGHT / cur_rot
        combined.iloc[i] = sum(
            float(df[key].iloc[i]) * row_weights.get(key, 0.0)
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


def run_blend(sub_rets_base, h041a_w, h026_w, h045_w):
    """
    Run blend with given rotation weights.
    Rotation sum (h041a+h026+h045) must be <= 0.70; remainder stays as cash.
    IBS always at fixed 30% (0.20 XLK, 0.08 SMH, 0.02 IGV).
    Total allocation = rotation + IBS (may be < 100% if rotation sum < 70%).
    """
    prod_w = {
        "h041a": h041a_w, "h026": h026_w, "h045": h045_w,
        "XLK": 0.20, "SMH": 0.08, "IGV": 0.02,
    }
    port = blend_vol_targeted(sub_rets_base, prod_w)
    oos = stats(port[OOS_START:])
    alt = stats(port[ALT_OOS_ST:])
    return oos, alt


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H129 — Weight Re-Optimization Post-H128")
    print("=" * 80)
    print("H128 baseline: OOS 21.6336, AltOOS 71.5302, Sharpe 4.553\n")

    # ── Pre-compute all sub-strategy returns (shared) ────────────────────────
    print("Pre-computing IBS …")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  {sym} done")

    print("\nPre-computing H041a, H026, H045 (with 3m filter) …")
    h041a = build_rotation(H041A_FULL,  FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)
    h045  = build_h045_3m_tsmom(H045_PROD, FULL_START, FULL_END, n_hold=2)
    print("  done")

    sub_rets_base = {"h041a": h041a, "h026": h026, "h045": h045, **ibs_rets}

    # ── Phase 1: H045 sweep (rotation sum always 70%, h041a+h026 share the rest)
    # Convention: h041a + h026 + h045 = 0.70; IBS = 0.30 fixed.
    # When H045 decreases, we proportionally increase h041a and h026.
    print("\n" + "=" * 80)
    print("Phase 1 — H045 weight sweep (rotation=70% fixed, h041a:h026 ratio 22:27)")
    print("=" * 80)
    print(f"  {'H041a':>6}  {'H026':>6}  {'H045':>6}  {'IBS':>6}  {'OOS Cumul':>10}  {'AltOOS':>10}  {'OOS Sharpe':>11}  {'MaxDD':>8}")
    print(f"  {'-'*75}")

    ROTATION = 0.70
    IBS_W    = 0.30
    BASE_RATIO = 0.22 / (0.22 + 0.27)  # h041a share of (h041a+h026)

    phase1_results = []
    for h045_w in [0.14, 0.17, 0.21, 0.25, 0.28]:
        remainder = ROTATION - h045_w
        h041a_w = round(remainder * BASE_RATIO, 4)
        h026_w  = round(remainder * (1 - BASE_RATIO), 4)
        oos, alt = run_blend(sub_rets_base, h041a_w, h026_w, h045_w)
        phase1_results.append((h041a_w, h026_w, h045_w, oos, alt))
        baseline_mark = " ←" if abs(h045_w - 0.21) < 0.001 else ""
        print(f"  {h041a_w:>6.4f}  {h026_w:>6.4f}  {h045_w:>6.2f}  {IBS_W:>6.2f}  "
              f"{oos['cumul']:>10.4f}  {alt['cumul']:>10.4f}  "
              f"{oos['sharpe']:>11.3f}  {oos['max_drawdown']:>8.2%}{baseline_mark}")

    best_p1 = max(phase1_results, key=lambda r: r[3]["cumul"] + r[4]["cumul"])
    best_h045_w = best_p1[2]
    print(f"\n  Phase 1 best H045 weight: {best_h045_w:.2f}")

    # ── Phase 2: H026 sweep (h041a+h026 total fixed, h045=best from Phase 1) ─
    print("\n" + "=" * 80)
    print(f"Phase 2 — h041a vs h026 ratio sweep (rotation=70%, h045={best_h045_w:.2f})")
    print("=" * 80)
    print(f"  {'H041a':>6}  {'H026':>6}  {'H045':>6}  {'IBS':>6}  {'OOS Cumul':>10}  {'AltOOS':>10}  {'OOS Sharpe':>11}  {'MaxDD':>8}")
    print(f"  {'-'*75}")

    remainder = ROTATION - best_h045_w
    phase2_results = []
    for h041a_share in [0.30, 0.38, 0.449, 0.52, 0.60]:  # 0.449 ≈ current 22/(22+27)
        h041a_w = round(remainder * h041a_share, 4)
        h026_w  = round(remainder * (1 - h041a_share), 4)
        oos, alt = run_blend(sub_rets_base, h041a_w, h026_w, best_h045_w)
        phase2_results.append((h041a_w, h026_w, best_h045_w, oos, alt))
        baseline_mark = " ←" if abs(h041a_share - 0.449) < 0.01 else ""
        print(f"  {h041a_w:>6.4f}  {h026_w:>6.4f}  {best_h045_w:>6.2f}  {IBS_W:>6.2f}  "
              f"{oos['cumul']:>10.4f}  {alt['cumul']:>10.4f}  "
              f"{oos['sharpe']:>11.3f}  {oos['max_drawdown']:>8.2%}{baseline_mark}")

    # ── Summary ──────────────────────────────────────────────────────────────
    all_results = phase1_results + phase2_results
    baseline_oos, baseline_alt = 21.6336, 71.5302  # H128 baseline

    best = max(all_results, key=lambda r: r[3]["cumul"] + r[4]["cumul"])
    d_oos = best[3]["cumul"] - baseline_oos
    d_alt = best[4]["cumul"] - baseline_alt

    print("\n" + "=" * 80)
    print(f"  Best weights: h041a={best[0]:.2f}  h026={best[1]:.2f}  h045={best[2]:.2f}  "
          f"IBS={(1-best[0]-best[1]-best[2]):.2f}")
    print(f"  OOS:  {best[3]['cumul']:.4f}  (baseline {baseline_oos:.4f},  Δ{d_oos:+.4f})")
    print(f"  AltOOS: {best[4]['cumul']:.4f}  (baseline {baseline_alt:.4f},  Δ{d_alt:+.4f})")
    print(f"  OOS Sharpe: {best[3]['sharpe']:.3f}  MaxDD: {best[3]['max_drawdown']*100:.1f}%")

    both_better = d_oos > 0 and d_alt > 0
    print(f"\n  Verdict: {'CONFIRMED — new weights improve both windows' if both_better else 'NOT CONFIRMED — current weights optimal'}")

    return all_results


if __name__ == "__main__":
    main()
