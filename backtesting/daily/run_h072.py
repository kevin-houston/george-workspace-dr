"""
H072 — H045 Universe Expansion: BKLN and EMB
=============================================

Purpose:
  H045 (treasury rotation) is the dominant portfolio component at 43%.
  Current universe: SHY, IEI, IEF, TLT, TIP, HYG, LQD (7 bonds, top-2 monthly).

  Key gap: NO floating-rate exposure. In 2022-2023 (rate hike cycle):
    - TLT: -31.5% in 2022 (long duration crushed)
    - IEF: -16% in 2022
    - BKLN (senior floating rate loans): +0.45% in 2022 (zero duration!)
    - SHY (0-2yr Treasuries): -4.7% in 2022

  BKLN (Invesco Senior Loan ETF, launched 2011-03-03) has ~zero duration.
  Its momentum signal should have picked it in 2022 as TLT/IEF fell.

  Also test EMB (iShares EM Bond) for yield diversification.

  Grid:
    Universe A (8-asset): current 7 + BKLN
    Universe B (8-asset): current 7 + EMB
    Universe C (9-asset): current 7 + BKLN + EMB
    Also test top-3 selection (vs current top-2) for each universe

  If H045 improves, rebuild the full H070 production portfolio.

Periods:
  Full: 2003-01 → 2026-04 (BKLN starts 2011-03 → signal from 2012-03)
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04
  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h072_results.json
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
ALT_OOS_ST = "2013-01-01"

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# H070 production weights and IBS params
H070_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068", "h069", "h070", "h071"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h072_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068", "h069", "h070", "h071"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070", "h071", "h072"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h072_{ticker}_close_{start}_{end}.parquet"
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
    print("H072 — H045 Universe Expansion: BKLN and EMB")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)
    alt_oos  = pd.Timestamp(ALT_OOS_ST)

    BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]

    # ── Part 1: H045 standalone comparison ──────────────────────────────────
    print("\n[1] H045 standalone — universe variants (top-2 and top-3) …")

    bond_universes = {
        "Base-7 top-2":    (BASE_BONDS, 2),
        "Base+BKLN top-2": (BASE_BONDS + ["BKLN"], 2),
        "Base+EMB top-2":  (BASE_BONDS + ["EMB"], 2),
        "Base+BKLN+EMB top-2": (BASE_BONDS + ["BKLN", "EMB"], 2),
        "Base-7 top-3":    (BASE_BONDS, 3),
        "Base+BKLN top-3": (BASE_BONDS + ["BKLN"], 3),
    }

    h045_variants = {}
    is_mask_m  = None
    oos_mask_m = None
    ao_mask_m  = None

    print(f"\n  {'Universe':24}  {'Full S':>7}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  {'AltOOS S':>9}")
    print(f"  {'-'*80}")

    for name, (bonds, n_hold) in bond_universes.items():
        r = build_rotation_monthly(bonds, FULL_START, FULL_END, n_hold)
        if is_mask_m is None:
            is_mask_m  = r.index[(r.index >= is_st_ts) & (r.index <= is_ts)]
            oos_mask_m = r.index[r.index >= oos_ts]
            ao_mask_m  = r.index[r.index >= alt_oos]
        s_f  = stats(r)
        s_is = stats(r[r.index.isin(is_mask_m)])
        s_oo = stats(r[r.index.isin(oos_mask_m)])
        s_ao = stats(r[r.index.isin(ao_mask_m)])
        deg  = (s_oo["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100 if s_is["sharpe"] > 0 else float("nan")
        print(f"  {name:24}  {s_f['sharpe']:>7.4f}  {s_is['sharpe']:>7.4f}  "
              f"{s_oo['sharpe']:>7.4f}  {deg:>+8.1f}%  {s_ao['sharpe']:>9.4f}")
        h045_variants[name] = {"r": r, "is": s_is, "oos": s_oo, "alt_oos": s_ao, "deg": deg}

    # ── Part 2: Full portfolio with best H045 variant ─────────────────────
    print("\n[2] Full portfolio reconstruction with H045 variants (top-2 only) …")
    print("    Building other components …")

    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)
    xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
    smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)
    r_xlk = to_monthly(ibs_equity_curve(xlk_ohlc, *XLK_PARAMS))
    r_smh = to_monthly(ibs_equity_curve(smh_ohlc, *SMH_PARAMS))

    # Build portfolios with different H045 variants
    port_tests = {
        "H070 (base-7 top-2)": h045_variants["Base-7 top-2"]["r"],
        "BKLN added (8 top-2)": h045_variants["Base+BKLN top-2"]["r"],
        "EMB added  (8 top-2)": h045_variants["Base+EMB top-2"]["r"],
        "BKLN+EMB   (9 top-2)": h045_variants["Base+BKLN+EMB top-2"]["r"],
        "Base top-3":            h045_variants["Base-7 top-3"]["r"],
        "BKLN top-3":            h045_variants["Base+BKLN top-3"]["r"],
    }

    # Base r_dict components (without H045)
    base_parts = {"h041a": h041a_r, "h026": h026_r, "XLK": r_xlk, "SMH": r_smh}

    # Common index
    cidx = h041a_r.index
    for k, v in base_parts.items():
        cidx = cidx.intersection(v.index)
    for r in port_tests.values():
        cidx = cidx.intersection(r.index)
    cidx  = cidx.sort_values()
    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]
    c_ao  = cidx[cidx >= alt_oos]

    print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltOOS S':>9}  {'MaxDD':>7}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*95}")

    port_results = {}
    for name, h045_r in port_tests.items():
        rd = {**base_parts, "h045": h045_r}
        w  = H070_W

        def _pr(idx, _rd=rd, _w=w):
            return sum(ww * _rd[k].reindex(idx, fill_value=0.0) for k, ww in _w.items())

        s_is  = stats(_pr(c_is))
        s_oos = stats(_pr(c_oos))
        s_ao  = stats(_pr(c_ao))
        wf    = run_wf_5fold(cidx, rd, w)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
              f"{s_ao['sharpe']:>9.4f}  {s_oos['max_drawdown']*100:>6.2f}%  "
              f"{wf['worst']:>9.3f} {wf_ok}")
        port_results[name] = {"is": s_is, "oos": s_oos, "alt_oos": s_ao, "wf": wf}

    # ── Winner ────────────────────────────────────────────────────────────
    wf_pass = {k: v for k, v in port_results.items() if v["wf"]["worst"] >= WF_WORST_MIN}
    if wf_pass:
        best = max(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"])
        base_oos = port_results["H070 (base-7 top-2)"]["oos"]["sharpe"]
        base_ao  = port_results["H070 (base-7 top-2)"]["alt_oos"]["sharpe"]
        print(f"\n  WINNER: {best[0]}")
        print(f"    OOS {best[1]['oos']['sharpe']:.4f} vs baseline {base_oos:.4f} "
              f"(Δ={best[1]['oos']['sharpe']-base_oos:+.4f})")
        print(f"    AltOOS {best[1]['alt_oos']['sharpe']:.4f} vs baseline {base_ao:.4f} "
              f"(Δ={best[1]['alt_oos']['sharpe']-base_ao:+.4f})")
        if best[1]["oos"]["sharpe"] > base_oos and best[1]["alt_oos"]["sharpe"] > base_ao:
            print(f"    *** BOTH OOS windows confirm improvement ***")

    # ── Calendar year 2022 comparison ──────────────────────────────────────
    print("\n[3] 2022 calendar year return (rate hike stress test) …")
    for name, h045_r in port_tests.items():
        rd = {**base_parts, "h045": h045_r}
        r_full = sum(ww * rd[k].reindex(cidx, fill_value=0.0) for k, ww in H070_W.items())
        ret_2022 = float((1 + r_full[r_full.index.year == 2022]).prod() - 1)
        print(f"  {name:22}  2022: {ret_2022*100:+.2f}%")

    # ── Save ─────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h072_results.json"
    with open(out, "w") as f:
        h045_ser = {k: {"is": v["is"], "oos": v["oos"], "alt_oos": v["alt_oos"]}
                    for k, v in h045_variants.items()}
        json.dump({"hypothesis": "H072", "h045_standalone": h045_ser,
                   "portfolios": port_results}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
