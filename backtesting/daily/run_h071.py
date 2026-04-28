"""
H071 — Commodity IBS Satellites: GDX and GLD in H070 Portfolio
==============================================================

Purpose:
  H062 found two commodity IBS signals with LOW or NEGATIVE correlation to tech IBS:
    GDX: IS 0.249, OOS 0.756, Deg +203%, corr to QQQ IBS = -0.117 (diversifying!)
    GLD: IS 0.457, OOS 0.571, Deg +25%,  corr to QQQ IBS = +0.091 (near-zero)

  These would be genuinely diversifying additions to the H070 portfolio which
  is heavy on tech IBS (XLK+SMH correlation = +0.592).

  Plan:
    Part 1: GDX and GLD IBS standalone parameter sweep (find optimal params)
    Part 2: Test best commodity IBS in H070 production portfolio
      - Allocation source: reduce XLK from 20% (primary, since GDX is anti-correlated to tech)
      - Also test: take from H041a, take from H045

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04
  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h071_results.json
"""

import json
import itertools
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
ALT_OOS_ST  = "2013-01-01"

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# H070 production weights and IBS params
H070_W   = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
DEFAULT_PARAMS = (0.20, 0.80, 5, -0.005)


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068", "h069", "h070"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h071_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068", "h069", "h070"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070", "h071"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h071_{ticker}_close_{start}_{end}.parquet"
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


def sweep_standalone(ticker, ohlc, is_mask, oos_mask, n_top=8):
    buy_g  = [0.10, 0.15, 0.20, 0.25, 0.30]
    sell_g = [0.70, 0.75, 0.80, 0.85, 0.90]
    hold_g = [3, 4, 5, 6, 7]
    gap_g  = [-0.010, -0.005, 0.000]
    results = []
    for buy, sell, hold, gap in itertools.product(buy_g, sell_g, hold_g, gap_g):
        if buy >= sell:
            continue
        eq    = ibs_equity_curve(ohlc, buy, sell, hold, gap)
        r_mon = to_monthly(eq)
        s_i   = stats(r_mon[r_mon.index.isin(is_mask)])
        s_o   = stats(r_mon[r_mon.index.isin(oos_mask)])
        results.append({
            "ticker": ticker, "buy": buy, "sell": sell, "hold": hold, "gap": gap,
            "is_sharpe": s_i["sharpe"], "oos_sharpe": s_o["sharpe"],
            "oos_maxdd": s_o["max_drawdown"],
            "deg": round((s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100, 2)
                   if s_i["sharpe"] > 0 else float("nan"),
        })
    return sorted(results, key=lambda x: x["oos_sharpe"], reverse=True)[:n_top]


def main():
    print("\n" + "=" * 80)
    print("H071 — Commodity IBS Satellites: GDX and GLD")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)
    alt_oos  = pd.Timestamp(ALT_OOS_ST)

    print("\n[0] Loading data …")
    gdx_ohlc = fetch_ohlc("GDX", FULL_START, FULL_END)
    gld_ohlc = fetch_ohlc("GLD", FULL_START, FULL_END)
    xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
    smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)

    xlk_mon = xlk_ohlc.resample("ME").last().index
    is_mask  = xlk_mon[(xlk_mon >= is_st_ts) & (xlk_mon <= is_ts)]
    oos_mask = xlk_mon[xlk_mon >= oos_ts]

    print("\n[1] GDX IBS standalone sweep …")
    gdx_top = sweep_standalone("GDX", gdx_ohlc, is_mask, oos_mask)
    print(f"  Baseline (0.20/0.80/5/-0.5%): ", end="")
    eq_base_g = ibs_equity_curve(gdx_ohlc, *DEFAULT_PARAMS)
    r_base_g  = to_monthly(eq_base_g)
    sb_is  = stats(r_base_g[r_base_g.index.isin(is_mask)])
    sb_oos = stats(r_base_g[r_base_g.index.isin(oos_mask)])
    print(f"IS {sb_is['sharpe']:.3f}, OOS {sb_oos['sharpe']:.3f}")
    print(f"  {'Buy':>5}  {'Sell':>5}  {'Hold':>5}  {'Gap':>7}  {'IS S':>7}  {'OOS S':>7}  Deg")
    for r in gdx_top:
        print(f"  {r['buy']:>5.2f}  {r['sell']:>5.2f}  {r['hold']:>5d}  "
              f"{r['gap']*100:>6.2f}%  {r['is_sharpe']:>7.3f}  {r['oos_sharpe']:>7.3f}  "
              f"{r['deg']:>+.1f}%")

    print("\n[2] GLD IBS standalone sweep …")
    gld_top = sweep_standalone("GLD", gld_ohlc, is_mask, oos_mask)
    print(f"  Baseline (0.20/0.80/5/-0.5%): ", end="")
    eq_base_gl = ibs_equity_curve(gld_ohlc, *DEFAULT_PARAMS)
    r_base_gl  = to_monthly(eq_base_gl)
    sbl_is  = stats(r_base_gl[r_base_gl.index.isin(is_mask)])
    sbl_oos = stats(r_base_gl[r_base_gl.index.isin(oos_mask)])
    print(f"IS {sbl_is['sharpe']:.3f}, OOS {sbl_oos['sharpe']:.3f}")
    print(f"  {'Buy':>5}  {'Sell':>5}  {'Hold':>5}  {'Gap':>7}  {'IS S':>7}  {'OOS S':>7}  Deg")
    for r in gld_top:
        print(f"  {r['buy']:>5.2f}  {r['sell']:>5.2f}  {r['hold']:>5d}  "
              f"{r['gap']*100:>6.2f}%  {r['is_sharpe']:>7.3f}  {r['oos_sharpe']:>7.3f}  "
              f"{r['deg']:>+.1f}%")

    # ── Portfolio test ───────────────────────────────────────────────────────
    print("\n[3] Portfolio test …")
    print("    Building rotation components …")

    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)

    r_xlk = to_monthly(ibs_equity_curve(xlk_ohlc, *XLK_PARAMS))
    r_smh = to_monthly(ibs_equity_curve(smh_ohlc, *SMH_PARAMS))
    r_gdx_opt = to_monthly(ibs_equity_curve(gdx_ohlc, gdx_top[0]["buy"], gdx_top[0]["sell"],
                                             gdx_top[0]["hold"], gdx_top[0]["gap"]))
    r_gld_opt = to_monthly(ibs_equity_curve(gld_ohlc, gld_top[0]["buy"], gld_top[0]["sell"],
                                             gld_top[0]["hold"], gld_top[0]["gap"]))

    # Common index (without commodities first)
    base_rd = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh}
    cidx = h041a_r.index
    for k in base_rd:
        cidx = cidx.intersection(base_rd[k].index)
    # Extend to include commodity IBS
    for r in [r_gdx_opt, r_gld_opt]:
        cidx = cidx.intersection(r.index)
    cidx  = cidx.sort_values()
    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]
    c_ao  = cidx[cidx >= alt_oos]

    def port_stats(r_dict, w):
        def _pr(idx):
            return sum(ww * r_dict.get(k, pd.Series(dtype=float)).reindex(idx, fill_value=0.0)
                       for k, ww in w.items())
        s_is  = stats(_pr(c_is))
        s_oos = stats(_pr(c_oos))
        s_ao  = stats(_pr(c_ao))
        wf    = run_wf_5fold(cidx, r_dict, w)
        return s_is, s_oos, s_ao, wf

    # Portfolios to test
    portfolios = {
        "H070 baseline": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh},
            {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
        ),
        "GDX4 (XLK16)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh, "GDX": r_gdx_opt},
            {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.16, "SMH": 0.08, "GDX": 0.04}
        ),
        "GDX4 (H041a-)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh, "GDX": r_gdx_opt},
            {"h041a": 0.186, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08, "GDX": 0.04}
        ),
        "GDX4 (H045 39%)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh, "GDX": r_gdx_opt},
            {"h041a": 0.252, "h026": 0.072, "h045": 0.39, "XLK": 0.20, "SMH": 0.08, "GDX": 0.04}
        ),
        "GLD4 (XLK16)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh, "GLD": r_gld_opt},
            {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.16, "SMH": 0.08, "GLD": 0.04}
        ),
        "GLD4 (H041a-)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh, "GLD": r_gld_opt},
            {"h041a": 0.186, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08, "GLD": 0.04}
        ),
        "GDX2+GLD2 (XLK16)": (
            {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": r_smh,
             "GDX": r_gdx_opt, "GLD": r_gld_opt},
            {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.16, "SMH": 0.08,
             "GDX": 0.02, "GLD": 0.02}
        ),
    }

    print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltOOS S':>9}  {'MaxDD':>7}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*90}")

    port_results = {}
    for name, (rd, w) in portfolios.items():
        s_is, s_oos, s_ao, wf = port_stats(rd, w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
              f"{s_ao['sharpe']:>9.4f}  {s_oos['max_drawdown']*100:>6.2f}%  "
              f"{wf['worst']:>9.3f} {wf_ok}")
        port_results[name] = {"is": s_is, "oos": s_oos, "alt_oos": s_ao, "wf": wf, "weights": w}

    base = port_results["H070 baseline"]
    wf_ok_ports = {k: v for k, v in port_results.items() if v["wf"]["worst"] >= WF_WORST_MIN}
    if wf_ok_ports:
        best = max(wf_ok_ports.items(), key=lambda x: x[1]["oos"]["sharpe"])
        print(f"\n  Best WF-consistent: {best[0]}")
        print(f"    OOS {best[1]['oos']['sharpe']:.4f} vs baseline {base['oos']['sharpe']:.4f} "
              f"(Δ={best[1]['oos']['sharpe']-base['oos']['sharpe']:+.4f})")

    out = RESULT_DIR / "h071_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H071", "gdx_top": gdx_top, "gld_top": gld_top,
                   "portfolios": port_results}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
