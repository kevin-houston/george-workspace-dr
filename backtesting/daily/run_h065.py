"""
H065 — XLK/SMH IBS Fine-Grid: Optimising the Tech IBS Blend
=============================================================

Purpose:
  H064 found: F (XLK 20% + SMH 8%) is the best WF-consistent variant with
  OOS Sharpe 2.3739, WF worst 2.395. XLK strictly dominates QQQ as an IBS
  signal (higher IS and OOS Sharpe, better WF consistency).

  This hypothesis fine-grids the XLK/SMH split within (and slightly above)
  the 28% IBS budget to find the optimal allocation.

  Grid:
    XLK: [0, 4, 8, 12, 14, 16, 18, 20, 22, 24, 26, 28%]
    SMH: [0, 4, 8, 12%]
    Subject to: XLK + SMH ∈ {24, 28, 32, 36%}

  Questions:
    1. What XLK/SMH split maximises WF-consistent OOS Sharpe at 28% total?
    2. Can we push above 28% total IBS with XLK+SMH and still pass WF?
    3. What is the new production portfolio?

  All keep H041a 25.7% / H026 7.3% / H045 39.0%.

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h065_results.json
"""

import json
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

IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5
GAP_FILTER = -0.005

H041A_W = 0.257
H026_W  = 0.073
H045_W  = 0.390

WF_WORST_MIN = 1.75

# ─────────────────────────────────────────────────────────────────────────────
# Data (identical to H064)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    if ticker == "QQQ":
        for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060", "h061"]:
            cp = CACHE_DIR / f"{prefix}_QQQ_ohlc_{start}_{end}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    cp = CACHE_DIR / f"h065_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    ohlc_prefixes = ["h064", "h063", "h062"]
    for pfx in ohlc_prefixes:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    if ticker == "QQQ":
        for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060", "h061"]:
            p = CACHE_DIR / f"{prefix}_QQQ_ohlc_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    cp = CACHE_DIR / f"h064_{ticker}_close_{start}_{end}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        return df.squeeze().rename(ticker)
    cp2 = CACHE_DIR / f"h065_{ticker}_close_{start}_{end}.parquet"
    if cp2.exists():
        df = pd.read_parquet(cp2)
        return df.squeeze().rename(ticker)
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp2)
    return close


def build_rotation_monthly(tickers, start, end, n_hold):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    Warning: {t}: {e}")
    daily_df = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px   = daily_df.resample("ME").last()
    monthly_rets = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows   = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((month_end, monthly_rets.iloc[i][top_n].mean()))
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc):
    df        = ohlc.copy()
    denom     = (df["high"] - df["low"]).replace(0, np.nan)
    ibs       = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl   = df["close"].shift(1)
    gap       = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])
        ret_oc   = (c / o - 1) if o > 0 else 0.0
        ret_cc   = (c / c_prev - 1) if c_prev > 0 else 0.0
        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        series.append((date, equity))
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq      = (1 + r).cumprod()
    n_yr    = len(r) / 12.0
    cagr    = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol     = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    max_dd  = float((eq / eq.expanding().max() - 1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


def run_wf_5fold(idx, r_dict, weights, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    folds = []
    start = min_train
    fold  = 0
    while start + test_size <= n and fold < n_folds:
        ti = is_idx[start:start + test_size]
        pr = sum(w * r_dict[k].reindex(ti, fill_value=0.0) for k, w in weights.items())
        folds.append(stats(pr)["sharpe"])
        start += test_size
        fold  += 1
    if not folds:
        return {"avg": 0.0, "worst": 0.0, "folds": []}
    return {"avg": round(float(np.mean(folds)), 4),
            "worst": round(float(np.min(folds)), 4),
            "folds": [round(x, 4) for x in folds]}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H065 — XLK/SMH IBS Fine-Grid")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)

    # ── 0. Load component returns (reuse H064 caches) ─────────────────────────
    print("\n[0] Building component return series (reusing H064 caches) …")

    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)

    ibs_m = {}
    for t in ["XLK", "SMH"]:
        ohlc     = fetch_ohlc(t, FULL_START, FULL_END)
        ibs_m[t] = to_monthly(ibs_equity_curve(ohlc))

    r_dict = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
               "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"]}

    cidx = h041a_r.index
    for k in r_dict:
        cidx = cidx.intersection(r_dict[k].index)
    cidx  = cidx.sort_values()
    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]
    print(f"  Common index: {len(cidx)} months  IS={len(c_is)}  OOS={len(c_oos)}")

    def port_r(idx, w):
        return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())

    def run_candidate(xlk_w, smh_w):
        w = {"h041a": H041A_W, "h026": H026_W, "h045": H045_W,
             "XLK": xlk_w, "SMH": smh_w}
        s_i  = stats(port_r(c_is,  w))
        s_o  = stats(port_r(c_oos, w))
        deg  = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        wf   = run_wf_5fold(cidx, r_dict, w)
        return s_i, s_o, round(deg, 2) if not np.isnan(deg) else None, wf

    # ── 1. Grid: XLK×SMH with total = 28% ────────────────────────────────────
    print("\n[1] Grid at total IBS = 28% (XLK + SMH = 28%) …")
    print(f"\n  {'XLK':>5}  {'SMH':>5}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  "
          f"{'MaxDD':>7}  {'WF worst':>9}  {'WF folds'}")
    print(f"  {'-'*90}")

    results_28 = {}
    for xlk_w in [i/100 for i in range(0, 29, 4)]:
        smh_w = 0.28 - xlk_w
        if smh_w < 0:
            continue
        s_i, s_o, deg, wf = run_candidate(xlk_w, smh_w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        lbl = f"xlk{int(xlk_w*100):02d}_smh{int(smh_w*100):02d}"
        print(f"  {xlk_w*100:>4.0f}%  {smh_w*100:>4.0f}%  {s_i['sharpe']:>7.3f}  "
              f"{s_o['sharpe']:>7.3f}  {deg:>+8.1f}%  {s_o['max_drawdown']*100:>6.2f}%  "
              f"{wf['worst']:>9.3f} {wf_ok}  {wf['folds']}")
        results_28[lbl] = {"xlk": xlk_w, "smh": smh_w, "total": 0.28,
                            "is": s_i, "oos": s_o, "deg": deg, "wf": wf}

    # ── 2. Grid: can we push above 28%? ───────────────────────────────────────
    print("\n[2] Testing total IBS = 32% (XLK + SMH = 32%) …")
    print(f"\n  {'XLK':>5}  {'SMH':>5}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  "
          f"{'MaxDD':>7}  {'WF worst':>9}  {'WF folds'}")
    print(f"  {'-'*90}")

    results_32 = {}
    for xlk_w in [i/100 for i in range(0, 33, 4)]:
        smh_w = 0.32 - xlk_w
        if smh_w < 0:
            continue
        # Check feasibility: H041a + H026 + H045 + XLK + SMH = 1.0 means they sum correctly
        # H041A_W + H026_W + H045_W = 0.72; XLK + SMH = 0.32 → total = 1.04 > 1.0!
        # Need to reduce other components. Keep H045 fixed, reduce H041a + H026 proportionally.
        # Remaining = 1.0 - H045_W - 0.32 = 1.0 - 0.39 - 0.32 = 0.29
        remaining = 1.0 - H045_W - xlk_w - smh_w
        if remaining < 0.15:  # minimum equity component
            continue
        ratio = H041A_W / (H041A_W + H026_W)  # 0.78 for H041a, 0.22 for H026
        h041a_w = remaining * ratio
        h026_w  = remaining * (1 - ratio)
        w = {"h041a": h041a_w, "h026": h026_w, "h045": H045_W,
             "XLK": xlk_w, "SMH": smh_w}
        s_i, s_o, deg, wf = run_candidate(xlk_w, smh_w)
        # Use full weights
        s_i2  = stats(port_r(c_is,  w))
        s_o2  = stats(port_r(c_oos, w))
        deg2  = (s_o2["sharpe"] - s_i2["sharpe"]) / s_i2["sharpe"] * 100 if s_i2["sharpe"] > 0 else float("nan")
        wf2   = run_wf_5fold(cidx, r_dict, w)
        wf_ok = "✓" if wf2["worst"] >= WF_WORST_MIN else "✗"
        lbl = f"xlk{int(xlk_w*100):02d}_smh{int(smh_w*100):02d}_32"
        print(f"  {xlk_w*100:>4.0f}%  {smh_w*100:>4.0f}%  {s_i2['sharpe']:>7.3f}  "
              f"{s_o2['sharpe']:>7.3f}  {deg2:>+8.1f}%  {s_o2['max_drawdown']*100:>6.2f}%  "
              f"{wf2['worst']:>9.3f} {wf_ok}  {wf2['folds']}"
              f"  (H041a={h041a_w:.3f} H026={h026_w:.3f})")
        results_32[lbl] = {"xlk": xlk_w, "smh": smh_w, "total": 0.32,
                            "h041a": h041a_w, "h026": h026_w,
                            "is": s_i2, "oos": s_o2,
                            "deg": round(deg2, 2) if not np.isnan(deg2) else None,
                            "wf": wf2}

    # ── 3. Best candidates ─────────────────────────────────────────────────────
    print("\n[3] WF-consistent candidates (worst ≥ 1.75), ranked by OOS Sharpe …")
    all_results = {**results_28, **results_32}
    wf_pass = {k: v for k, v in all_results.items() if v["wf"]["worst"] >= WF_WORST_MIN}
    if wf_pass:
        for k, v in sorted(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
            xlk_pct = v["xlk"] * 100
            smh_pct = v["smh"] * 100
            total   = v["total"] * 100
            print(f"   XLK {xlk_pct:.0f}% + SMH {smh_pct:.0f}% (total {total:.0f}%)  "
                  f"OOS {v['oos']['sharpe']:.4f}  WF worst {v['wf']['worst']:.3f}  "
                  f"folds {v['wf']['folds']}")
        best_key   = max(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"])[0]
        best       = wf_pass[best_key]
        print(f"\n  WINNER: XLK {best['xlk']*100:.0f}% + SMH {best['smh']*100:.0f}%")
        print(f"    OOS Sharpe: {best['oos']['sharpe']:.4f}")
        print(f"    OOS MaxDD:  {best['oos']['max_drawdown']*100:.2f}%")
        print(f"    OOS CAGR:   {best['oos']['cagr']*100:.2f}%")
        print(f"    WF worst:   {best['wf']['worst']:.3f}")
        print(f"    Deg:        {best['deg']:+.1f}%")
    else:
        print("   No WF-consistent candidates found — all variants listed by OOS Sharpe:")
        for k, v in sorted(all_results.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True)[:5]:
            print(f"   {k}: OOS {v['oos']['sharpe']:.4f}  WF worst {v['wf']['worst']:.3f}")

    # ── 4. Definitive production portfolio weights ─────────────────────────────
    print("\n[4] Proposed H065 production portfolio …")
    # Use winner or fall back to H064-F
    if wf_pass:
        best_key = max(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"])[0]
        best = wf_pass[best_key]
        xlk_w = best["xlk"]
        smh_w = best["smh"]
        h041a_w = best.get("h041a", H041A_W)
        h026_w  = best.get("h026",  H026_W)
    else:
        xlk_w, smh_w, h041a_w, h026_w = 0.20, 0.08, H041A_W, H026_W
        print("  (Falling back to H064-F defaults)")

    w_prod = {"h041a": h041a_w, "h026": h026_w, "h045": H045_W, "XLK": xlk_w, "SMH": smh_w}
    s_full = stats(port_r(cidx, w_prod))
    s_is   = stats(port_r(c_is, w_prod))
    s_oos  = stats(port_r(c_oos, w_prod))
    wf     = run_wf_5fold(cidx, r_dict, w_prod)
    print(f"\n  H041a {h041a_w*100:.1f}% / H026 {h026_w*100:.1f}% / H045 {H045_W*100:.1f}% / "
          f"XLK IBS {xlk_w*100:.1f}% / SMH IBS {smh_w*100:.1f}%")
    print(f"  Full Sharpe {s_full['sharpe']:.4f}  CAGR {s_full['cagr']*100:.2f}%")
    print(f"  IS   Sharpe {s_is['sharpe']:.4f}  OOS Sharpe {s_oos['sharpe']:.4f}  "
          f"MaxDD {s_oos['max_drawdown']*100:.2f}%")
    print(f"  WF 5-fold: avg {wf['avg']:.3f}  worst {wf['worst']:.3f}  folds {wf['folds']}")

    # ── 5. Save ────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h065_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H065",
                   "results_28pct": results_28,
                   "results_32pct": results_32,
                   "production": w_prod}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
