"""
H068 — H045 True Upper Bound + EFA IBS Addition
================================================

Purpose:
  H067 found ALL H045 values 34%-46% pass WF comfortably (worst 2.370-2.401).
  The QQQ-era upper bound (40%) no longer applies with XLK+SMH IBS.

  Part 1: Extend H045 grid to 47%-62% to find the true WF failure point.
          XLK=20%, SMH=8% fixed. H041a/H026 shrink at 3.5:1 ratio.

  Part 2: EFA IBS as third component (H062: IS 0.653, OOS 1.021, Deg +56%).
          At H045=43%, test EFA replacing or augmenting XLK/SMH:
            Blend A: XLK 16% + SMH 8% + EFA 4%  = 28% total (replaces 4% XLK)
            Blend B: XLK 20% + SMH 4% + EFA 4%  = 28% total (replaces 4% SMH)
            Blend C: XLK 20% + SMH 8% + EFA 4%  = 32% total (additive)
            Blend D: XLK 12% + SMH 8% + EFA 8%  = 28% total (EFA = XLK)
          Baseline: XLK 20% + SMH 8% + EFA 0%  = 28% (H067 winner at 43%)

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h068_results.json
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

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75


def make_weights_2ibs(h045_w, xlk_w, smh_w):
    ibs_w    = xlk_w + smh_w
    equity_w = 1.0 - ibs_w - h045_w
    h041a_w  = equity_w * H41_H26_RATIO / (H41_H26_RATIO + 1.0)
    h026_w   = equity_w / (H41_H26_RATIO + 1.0)
    return {"h041a": h041a_w, "h026": h026_w, "h045": h045_w,
            "XLK": xlk_w, "SMH": smh_w}


def make_weights_3ibs(h045_w, xlk_w, smh_w, efa_w):
    ibs_w    = xlk_w + smh_w + efa_w
    equity_w = 1.0 - ibs_w - h045_w
    h041a_w  = equity_w * H41_H26_RATIO / (H41_H26_RATIO + 1.0)
    h026_w   = equity_w / (H41_H26_RATIO + 1.0)
    return {"h041a": h041a_w, "h026": h026_w, "h045": h045_w,
            "XLK": xlk_w, "SMH": smh_w, "EFA": efa_w}


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h068_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h068_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df     = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px   = daily_df.resample("ME").last()
    monthly_rets = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows   = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_rets.iloc[i][top_n].mean()))
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
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i - 1])
        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0
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
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq     = (1 + r).cumprod()
    n_yr   = len(r) / 12.0
    cagr   = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol    = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


def run_wf_5fold(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    folds = []
    start = min_train
    fold  = 0
    while start + test_size <= n and fold < n_folds:
        ti = is_idx[start:start + test_size]
        pr = sum(ww * r_dict[k].reindex(ti, fill_value=0.0) for k, ww in w.items())
        folds.append(stats(pr)["sharpe"])
        start += test_size
        fold  += 1
    if not folds:
        return {"avg": 0.0, "worst": 0.0, "folds": []}
    return {"avg": round(np.mean(folds), 4),
            "worst": round(np.min(folds), 4),
            "folds": [round(x, 4) for x in folds]}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H068 — H045 True Upper Bound + EFA IBS Addition")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)

    print("\n[0] Building component return series …")
    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)
    ibs_m = {}
    for t in ["XLK", "SMH", "EFA"]:
        ohlc     = fetch_ohlc(t, FULL_START, FULL_END)
        ibs_m[t] = to_monthly(ibs_equity_curve(ohlc))

    # ── Part 1: Extended H045 grid 47%-62%, XLK=20%+SMH=8% ─────────────────
    print("\n[1] Extended H045 upper bound grid (XLK=20%, SMH=8% fixed, H045=47%-62%) …")
    print(f"\n  {'H045':>6}  {'H041a':>6}  {'H026':>6}  {'IS S':>7}  {'OOS S':>7}  "
          f"{'Deg':>8}  {'OOS MaxDD':>9}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*90}")

    r_dict_2 = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
                "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"]}

    cidx_2 = h041a_r.index
    for k in r_dict_2:
        cidx_2 = cidx_2.intersection(r_dict_2[k].index)
    cidx_2  = cidx_2.sort_values()
    c_is_2  = cidx_2[(cidx_2 >= is_st_ts) & (cidx_2 <= is_ts)]
    c_oos_2 = cidx_2[cidx_2 >= oos_ts]

    def port_r_2(idx, w):
        return sum(ww * r_dict_2[k].reindex(idx, fill_value=0.0) for k, ww in w.items())

    results_p1 = {}
    h045_ext = [i / 100 for i in range(47, 63)]
    for h045_w in h045_ext:
        w = make_weights_2ibs(h045_w, 0.20, 0.08)
        equity_total = w["h041a"] + w["h026"]
        if equity_total < 0.05:
            print(f"  {h045_w*100:>5.0f}%  (equity too small)")
            continue
        s_i = stats(port_r_2(c_is_2, w))
        s_o = stats(port_r_2(c_oos_2, w))
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        wf  = run_wf_5fold(cidx_2, r_dict_2, w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {h045_w*100:>5.0f}%  {w['h041a']*100:>5.1f}%  {w['h026']*100:>5.1f}%  "
              f"{s_i['sharpe']:>7.3f}  {s_o['sharpe']:>7.3f}  {deg:>+8.1f}%  "
              f"{s_o['max_drawdown']*100:>8.2f}%  {wf['worst']:>9.3f} {wf_ok}")
        results_p1[f"h045_{int(h045_w*100):02d}"] = {
            "h045": h045_w, "h041a": w["h041a"], "h026": w["h026"],
            "is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None,
            "wf": wf,
        }

    # Find failure point
    failures = [k for k, v in results_p1.items() if v["wf"]["worst"] < WF_WORST_MIN]
    if failures:
        first_fail = sorted(failures)[0]
        fv = results_p1[first_fail]
        print(f"\n  *** WF FAILURE at H045={fv['h045']*100:.0f}%  (WF worst={fv['wf']['worst']:.3f}) ***")
    else:
        print(f"\n  All H045 47%-62% still PASS WF — bound extends further.")

    # ── Part 2: EFA as third IBS component at H045=43% ──────────────────────
    print("\n[2] EFA IBS addition test (H045=43% fixed) …")

    r_dict_3 = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
                "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"], "EFA": ibs_m["EFA"]}

    cidx_3 = h041a_r.index
    for k in r_dict_3:
        cidx_3 = cidx_3.intersection(r_dict_3[k].index)
    cidx_3  = cidx_3.sort_values()
    c_is_3  = cidx_3[(cidx_3 >= is_st_ts) & (cidx_3 <= is_ts)]
    c_oos_3 = cidx_3[cidx_3 >= oos_ts]

    def port_r_3(idx, w):
        return sum(ww * r_dict_3.get(k, pd.Series(dtype=float)).reindex(idx, fill_value=0.0)
                   for k, ww in w.items())

    H045_FIXED = 0.43
    blends = {
        "Baseline (XLK20+SMH8, no EFA)":    make_weights_2ibs(H045_FIXED, 0.20, 0.08),
        "Blend A (XLK16+SMH8+EFA4=28%)":    make_weights_3ibs(H045_FIXED, 0.16, 0.08, 0.04),
        "Blend B (XLK20+SMH4+EFA4=28%)":    make_weights_3ibs(H045_FIXED, 0.20, 0.04, 0.04),
        "Blend C (XLK20+SMH8+EFA4=32%)":    make_weights_3ibs(H045_FIXED, 0.20, 0.08, 0.04),
        "Blend D (XLK12+SMH8+EFA8=28%)":    make_weights_3ibs(H045_FIXED, 0.12, 0.08, 0.08),
        "Blend E (XLK20+SMH8+EFA8=36%)":    make_weights_3ibs(H045_FIXED, 0.20, 0.08, 0.08),
    }

    print(f"\n  {'Blend':42}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  {'MaxDD':>7}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*100}")

    results_p2 = {}
    for name, w in blends.items():
        # For 2-component IBS, use r_dict_2 (no EFA key); for 3-component use r_dict_3
        r_dict_use = r_dict_3 if "EFA" in w else r_dict_2
        cidx_use   = cidx_3 if "EFA" in w else cidx_2
        c_is_use   = c_is_3 if "EFA" in w else c_is_2
        c_oos_use  = c_oos_3 if "EFA" in w else c_oos_2

        def _pr(idx, _w=w, _rd=r_dict_use):
            return sum(ww * _rd.get(k, pd.Series(dtype=float)).reindex(idx, fill_value=0.0)
                       for k, ww in _w.items())

        s_i = stats(_pr(c_is_use))
        s_o = stats(_pr(c_oos_use))
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        wf  = run_wf_5fold(cidx_use, r_dict_use, w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {name:42}  {s_i['sharpe']:>7.3f}  {s_o['sharpe']:>7.3f}  "
              f"{deg:>+8.1f}%  {s_o['max_drawdown']*100:>6.2f}%  {wf['worst']:>9.3f} {wf_ok}")
        results_p2[name] = {
            "weights": {k: round(v, 4) for k, v in w.items()},
            "is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None,
            "wf": wf,
        }

    # Winner of Part 2
    wf_p2 = {k: v for k, v in results_p2.items() if v["wf"]["worst"] >= WF_WORST_MIN}
    if wf_p2:
        best_p2 = max(wf_p2.items(), key=lambda x: x[1]["oos"]["sharpe"])
        print(f"\n  BEST EFA blend: {best_p2[0]}")
        print(f"    OOS Sharpe: {best_p2[1]['oos']['sharpe']:.4f}  WF worst: {best_p2[1]['wf']['worst']:.3f}")
        print(f"    Weights: {best_p2[1]['weights']}")

    # ── Save ─────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h068_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H068",
                   "part1_extended_h045": results_p1,
                   "part2_efa_blends": results_p2}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
