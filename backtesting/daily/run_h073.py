"""
H073 — Full Cross-Validation of H072 BKLN+EMB Improvement
==========================================================

Purpose:
  H072 found adding BKLN+EMB to H045's 7-bond universe dramatically improves:
    OOS: 2.550 → 2.666 (+4.6%)
    AltOOS: 2.576 → 2.705 (+5.0%)

  This hypothesis validates the improvement with:
    1. Full scorecard across primary and alternate IS/OOS splits
    2. Calendar year returns 2004-2025 (verify zero negative years holds)
    3. WF 5-fold detail (individual fold Sharpes)
    4. OOS CAGR and MaxDD comparison

  Also tests BKLN-alone (vs BKLN+EMB) to isolate EMB's marginal contribution.

Portfolios:
  Baseline:    H070 production (base-7 H045, top-2)
  H072_BKLN:  Base-7 + BKLN H045, top-2
  H072_best:  Base-7 + BKLN + EMB H045, top-2

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04
  AltIS: 2003-01 → 2012-12
  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h073_results.json
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

FULL_START  = "2003-01-01"
FULL_END    = "2026-04-27"
IS_START    = "2008-01-01"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
ALT_IS_END  = "2012-12-31"
ALT_OOS_ST  = "2013-01-01"

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# H070 production weights and IBS params
H070_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)

BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h073_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068",
                "h069", "h070", "h071", "h072"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070", "h071", "h072", "h073"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h073_{ticker}_close_{start}_{end}.parquet"
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


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df        = ohlc.copy()
    denom     = (df["high"] - df["low"]).replace(0, np.nan)
    ibs       = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl   = df["close"].shift(1)
    g         = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i - 1])
        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
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


def main():
    print("\n" + "=" * 80)
    print("H073 — Full Cross-Validation of BKLN+EMB H045 Expansion")
    print("=" * 80)

    is_ts     = pd.Timestamp(IS_END)
    oos_ts    = pd.Timestamp(OOS_START)
    is_st_ts  = pd.Timestamp(IS_START)
    alt_is_ts = pd.Timestamp(ALT_IS_END)
    alt_oos   = pd.Timestamp(ALT_OOS_ST)

    print("\n[0] Building components …")
    h045_base = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
    h045_bkln = build_rotation_monthly(BASE_BONDS + ["BKLN"], FULL_START, FULL_END, 2)
    h045_best = build_rotation_monthly(BASE_BONDS + ["BKLN", "EMB"], FULL_START, FULL_END, 2)

    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)
    xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
    smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)
    r_xlk = to_monthly(ibs_equity_curve(xlk_ohlc, *XLK_PARAMS))
    r_smh = to_monthly(ibs_equity_curve(smh_ohlc, *SMH_PARAMS))

    base_parts = {"h041a": h041a_r, "h026": h026_r, "XLK": r_xlk, "SMH": r_smh}

    portfolios = {
        "Baseline (H070)": {**base_parts, "h045": h045_base},
        "H072_BKLN":       {**base_parts, "h045": h045_bkln},
        "H072_BKLN+EMB":   {**base_parts, "h045": h045_best},
    }

    # Common index
    cidx = h041a_r.index
    for rd in portfolios.values():
        for s in rd.values():
            cidx = cidx.intersection(s.index)
    cidx  = cidx.sort_values()
    c_is      = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos     = cidx[cidx >= oos_ts]
    c_alt_is  = cidx[(cidx >= pd.Timestamp(FULL_START)) & (cidx <= alt_is_ts)]
    c_alt_oos = cidx[cidx >= alt_oos]

    # ── Main scorecard ───────────────────────────────────────────────────────
    print("\n[1] Full cross-validation scorecard …")
    print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
          f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}  Folds")
    print(f"  {'-'*115}")

    results = {}
    for name, rd in portfolios.items():
        def _pr(idx, _rd=rd, w=H070_W):
            return sum(ww * _rd[k].reindex(idx, fill_value=0.0) for k, ww in w.items())
        s_is     = stats(_pr(c_is))
        s_oos    = stats(_pr(c_oos))
        s_alt_is = stats(_pr(c_alt_is))
        s_alt_oo = stats(_pr(c_alt_oos))
        wf = run_wf_5fold(cidx, rd, H070_W)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
              f"{s_alt_is['sharpe']:>8.4f}  {s_alt_oo['sharpe']:>9.4f}  "
              f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
              f"{wf['worst']:>9.3f} {wf_ok}  {wf['folds']}")
        results[name] = {"is": s_is, "oos": s_oos, "alt_is": s_alt_is,
                         "alt_oos": s_alt_oo, "wf": wf}

    # ── Calendar year returns ─────────────────────────────────────────────
    print("\n[2] Calendar year returns 2004-2025 …")
    print(f"\n  {'Year':>5}", end="")
    for name in portfolios:
        print(f"  {name:>22}", end="")
    print()
    print(f"  {'-'*80}")

    neg_years = {k: [] for k in portfolios}
    for yr in range(2004, 2026):
        print(f"  {yr:>5}", end="")
        for name, rd in portfolios.items():
            r = sum(ww * rd[k].reindex(cidx, fill_value=0.0) for k, ww in H070_W.items())
            yr_r = float((1 + r[r.index.year == yr]).prod() - 1)
            if yr_r < -0.001:
                neg_years[name].append(yr)
            flag = " ✗" if yr_r < -0.001 else ""
            print(f"  {yr_r*100:>+21.2f}%{flag}", end="")
        print()

    for name in portfolios:
        neg = neg_years[name]
        print(f"  {name}: {'ZERO negative years' if not neg else f'NEGATIVE years: {neg}'}")

    # ── Summary ──────────────────────────────────────────────────────────
    print("\n[3] Summary vs H070 baseline …")
    base = results["Baseline (H070)"]
    best = results["H072_BKLN+EMB"]
    bkln = results["H072_BKLN"]

    print(f"  BKLN only:   OOS {bkln['oos']['sharpe']:.4f} "
          f"({bkln['oos']['sharpe']-base['oos']['sharpe']:+.4f}), "
          f"AltOOS {bkln['alt_oos']['sharpe']:.4f} "
          f"({bkln['alt_oos']['sharpe']-base['alt_oos']['sharpe']:+.4f})")
    print(f"  BKLN+EMB:    OOS {best['oos']['sharpe']:.4f} "
          f"({best['oos']['sharpe']-base['oos']['sharpe']:+.4f}), "
          f"AltOOS {best['alt_oos']['sharpe']:.4f} "
          f"({best['alt_oos']['sharpe']-base['alt_oos']['sharpe']:+.4f})")

    if (best["oos"]["sharpe"] > base["oos"]["sharpe"] and
            best["alt_oos"]["sharpe"] > base["alt_oos"]["sharpe"] and
            best["wf"]["worst"] >= WF_WORST_MIN):
        print(f"\n  *** BKLN+EMB CONFIRMED on both OOS windows, WF worst {best['wf']['worst']:.3f} ***")
        print(f"  *** New production H045 universe: SHY+IEI+IEF+TLT+TIP+HYG+LQD+BKLN+EMB ***")

    # ── Save ─────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h073_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H073", "portfolios": results,
                   "neg_years": neg_years}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
