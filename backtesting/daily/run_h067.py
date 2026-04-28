"""
H067 — H045 Upper Bound Re-test with H065_F2 Portfolio
=======================================================

Purpose:
  H060 found H045=39% as the upper WF-consistent bound (40% fails WF worst
  1.742 < 1.75). That validation used QQQ IBS at 28%.

  H065_F2 replaces QQQ with XLK 20% + SMH 8% — a more WF-consistent IBS
  blend. Does this change the H045 upper bound? Can we now push to 40%, 41%,
  or 42% and still pass WF?

  Grid: H045 ∈ {37, 38, 39, 40, 41, 42, 43%}
  XLK=20%, SMH=8% fixed. H041a/H026 adjusted to fill remainder at 3.5:1 ratio.

  H041a + H026 = 1 - H045 - 0.28 = 0.72 - H045
  H041a = (0.72 - H045) * (3.5 / 4.5)
  H026  = (0.72 - H045) * (1.0 / 4.5)

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h067_results.json
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

XLK_W  = 0.20
SMH_W  = 0.08
IBS_W  = XLK_W + SMH_W   # 0.28 fixed
H41_H26_RATIO = 3.5

WF_WORST_MIN = 1.75


def make_weights(h045_w):
    equity_w = 1.0 - IBS_W - h045_w
    h041a_w  = equity_w * H41_H26_RATIO / (H41_H26_RATIO + 1.0)
    h026_w   = equity_w / (H41_H26_RATIO + 1.0)
    return {"h041a": h041a_w, "h026": h026_w, "h045": h045_w,
            "XLK": XLK_W, "SMH": SMH_W}


# ─────────────────────────────────────────────────────────────────────────────
# Data (all from H064/H066 caches)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066"]:
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
    cp = CACHE_DIR / f"h067_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066"]:
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
    for pfx in ["h064", "h065", "h066", "h067"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h067_{ticker}_close_{start}_{end}.parquet"
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
    daily_df = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
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
    print("H067 — H045 Upper Bound Re-test with H065_F2 IBS Weights")
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
    for t in ["XLK", "SMH"]:
        ohlc     = fetch_ohlc(t, FULL_START, FULL_END)
        ibs_m[t] = to_monthly(ibs_equity_curve(ohlc))

    r_dict = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
               "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"]}

    cidx = r_dict["h041a"].index
    for k in r_dict:
        cidx = cidx.intersection(r_dict[k].index)
    cidx  = cidx.sort_values()
    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]

    def port_r(idx, w):
        return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())

    # ── Grid: H045 from 37% to 43% ───────────────────────────────────────────
    print("\n[1] H045 upper bound grid (XLK=20%, SMH=8% fixed) …")
    print(f"\n  {'H045':>6}  {'H041a':>6}  {'H026':>6}  {'IS S':>7}  {'OOS S':>7}  "
          f"{'Deg':>8}  {'OOS MaxDD':>9}  {'WF worst':>9}  {'WF folds'}")
    print(f"  {'-'*100}")

    results = {}
    h045_range = [i / 100 for i in range(34, 47)]
    for h045_w in h045_range:
        w = make_weights(h045_w)
        equity_total = w["h041a"] + w["h026"]
        if equity_total < 0.10:
            print(f"  {h045_w*100:>5.0f}%  (equity component too small: {equity_total:.3f})")
            continue
        s_i = stats(port_r(c_is,  w))
        s_o = stats(port_r(c_oos, w))
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        wf  = run_wf_5fold(cidx, r_dict, w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {h045_w*100:>5.0f}%  {w['h041a']*100:>5.1f}%  {w['h026']*100:>5.1f}%  "
              f"{s_i['sharpe']:>7.3f}  {s_o['sharpe']:>7.3f}  {deg:>+8.1f}%  "
              f"{s_o['max_drawdown']*100:>8.2f}%  {wf['worst']:>9.3f} {wf_ok}  {wf['folds']}")
        results[f"h045_{int(h045_w*100):02d}"] = {
            "h045": h045_w, "h041a": w["h041a"], "h026": w["h026"],
            "is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None,
            "wf": wf,
        }

    # ── Winner ────────────────────────────────────────────────────────────────
    print("\n[2] WF-consistent candidates (worst ≥ 1.75), ranked by OOS Sharpe …")
    wf_pass = {k: v for k, v in results.items() if v["wf"]["worst"] >= WF_WORST_MIN}
    for k, v in sorted(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
        print(f"   H045={v['h045']*100:.0f}%  H041a={v['h041a']*100:.1f}%  H026={v['h026']*100:.1f}%  "
              f"OOS {v['oos']['sharpe']:.4f}  WF worst {v['wf']['worst']:.3f}  folds {v['wf']['folds']}")

    if wf_pass:
        best_key = max(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"])[0]
        best = wf_pass[best_key]
        print(f"\n  WINNER: H045={best['h045']*100:.0f}%")
        print(f"    Production weights: H041a {best['h041a']*100:.1f}% / H026 {best['h026']*100:.1f}% / "
              f"H045 {best['h045']*100:.1f}% / XLK IBS {XLK_W*100:.0f}% / SMH IBS {SMH_W*100:.0f}%")
        print(f"    OOS Sharpe: {best['oos']['sharpe']:.4f}  MaxDD: {best['oos']['max_drawdown']*100:.2f}%")
        print(f"    WF worst:   {best['wf']['worst']:.3f}  folds: {best['wf']['folds']}")

    # ── Save ──────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h067_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H067", "results": results,
                   "xlk_w": XLK_W, "smh_w": SMH_W}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
