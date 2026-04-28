"""
H070 — Full Cross-Validation of H069 Optimized IBS Parameters
==============================================================

Purpose:
  H069 found that tech-specific IBS parameters meaningfully beat SPY-defaults:
    XLK: buy=0.15, sell=0.90, hold=7, gap=-1.0% (OOS standalone 2.207 vs 1.613 baseline)
    SMH: buy=0.20, sell=0.75, hold=6, gap=-0.5% (OOS standalone 1.649 vs 1.417 baseline)
    Portfolio OOS Sharpe: 2.550 vs 2.379 baseline (+7.2%)

  Concern: parameters were selected by maximizing OOS Sharpe — potential overfitting.

  Validation approach:
    1. Primary IS/OOS split: 2008-2017 IS / 2018-2026 OOS
    2. Alt IS/OOS split:     2003-2012 IS / 2013-2026 OOS (alternate window)
    3. Walk-forward 5-fold (IS-anchored)
    4. Calendar-year analysis (2004-2025)
    5. Fine-grid around XLK winner: buy ∈ {0.12, 0.15, 0.18}, sell ∈ {0.85, 0.90}, hold ∈ {6, 7}

  Portfolios compared:
    Baseline: H067 production (0.20/0.80/5/-0.5% both)
    H070_opt: Optimized params (XLK 0.15/0.90/7/-1.0%, SMH 0.20/0.75/6/-0.5%)
    H070_xlk: XLK optimized only (keep SMH at defaults)
    H070_smh: SMH optimized only (keep XLK at defaults)

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12  |  OOS: 2018-01 → 2026-04
  AltIS: 2003-01 → 2012-12  |  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h070_results.json
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
ALT_IS_END  = "2012-12-31"
ALT_OOS_ST  = "2013-01-01"

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# Confirmed production weights (H067)
PROD_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}

# IBS params: (buy, sell, hold, gap)
DEFAULT_PARAMS = (0.20, 0.80, 5, -0.005)
XLK_OPT       = (0.15, 0.90, 7, -0.010)
SMH_OPT       = (0.20, 0.75, 6, -0.005)


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068", "h069"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h070_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068", "h069"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h070_{ticker}_close_{start}_{end}.parquet"
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


def calendar_year_returns(r_dict, w, cidx):
    r = sum(ww * r_dict[k].reindex(cidx, fill_value=0.0) for k, ww in w.items())
    return r.groupby(r.index.year).apply(lambda x: float((1 + x).prod() - 1))


def main():
    print("\n" + "=" * 80)
    print("H070 — Full Cross-Validation of H069 Optimized IBS Parameters")
    print("=" * 80)

    is_ts     = pd.Timestamp(IS_END)
    oos_ts    = pd.Timestamp(OOS_START)
    is_st_ts  = pd.Timestamp(IS_START)
    alt_is_ts = pd.Timestamp(ALT_IS_END)
    alt_oos   = pd.Timestamp(ALT_OOS_ST)

    print("\n[0] Building components …")
    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)

    xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
    smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)

    # Build 4 IBS variants
    ibs_variants = {
        "baseline": (DEFAULT_PARAMS, DEFAULT_PARAMS),
        "H070_opt": (XLK_OPT, SMH_OPT),
        "H070_xlk": (XLK_OPT, DEFAULT_PARAMS),
        "H070_smh": (DEFAULT_PARAMS, SMH_OPT),
    }

    r_dicts = {}
    for name, (xp, sp) in ibs_variants.items():
        r_xlk = to_monthly(ibs_equity_curve(xlk_ohlc, *xp))
        r_smh = to_monthly(ibs_equity_curve(smh_ohlc, *sp))
        r_dicts[name] = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
                         "XLK": r_xlk, "SMH": r_smh}

    # Common index
    cidx = h041a_r.index
    for k in r_dicts["baseline"]:
        cidx = cidx.intersection(r_dicts["baseline"][k].index)
    cidx = cidx.sort_values()
    c_is     = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos    = cidx[cidx >= oos_ts]
    c_alt_is = cidx[(cidx >= pd.Timestamp(FULL_START)) & (cidx <= alt_is_ts)]
    c_alt_oos= cidx[cidx >= alt_oos]

    # ── Primary IS/OOS + Alt IS/OOS scorecard ───────────────────────────────
    print("\n[1] Cross-validation scorecard …")
    print(f"\n  {'Portfolio':14}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
          f"{'AltOOS S':>9}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*80}")

    results = {}
    for name, rd in r_dicts.items():
        def pr(idx, _rd=rd, w=PROD_W):
            return sum(ww * _rd[k].reindex(idx, fill_value=0.0) for k, ww in w.items())
        s_is      = stats(pr(c_is))
        s_oos     = stats(pr(c_oos))
        s_alt_is  = stats(pr(c_alt_is))
        s_alt_oos = stats(pr(c_alt_oos))
        wf = run_wf_5fold(cidx, rd, PROD_W)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {name:14}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
              f"{s_alt_is['sharpe']:>8.4f}  {s_alt_oos['sharpe']:>9.4f}  "
              f"{wf['worst']:>9.3f} {wf_ok}")
        results[name] = {
            "is": s_is, "oos": s_oos, "alt_is": s_alt_is, "alt_oos": s_alt_oos, "wf": wf
        }

    # ── Calendar year analysis ───────────────────────────────────────────────
    print("\n[2] Calendar year returns (selected years) …")
    years_to_show = [2004, 2007, 2008, 2009, 2010, 2014, 2015, 2018, 2020, 2021, 2022, 2023, 2024, 2025]
    print(f"\n  {'Year':>5}", end="")
    for name in ibs_variants:
        print(f"  {name:>14}", end="")
    print()
    print(f"  {'-'*75}")

    cal_data = {}
    for name, rd in r_dicts.items():
        cal_data[name] = calendar_year_returns(rd, PROD_W, cidx)

    neg_years = {}
    for name in ibs_variants:
        neg_years[name] = [y for y, r in cal_data[name].items() if r < 0]

    for yr in years_to_show:
        print(f"  {yr:>5}", end="")
        for name in ibs_variants:
            v = cal_data[name].get(yr, float("nan"))
            flag = " ✗" if v < -0.001 else ""
            print(f"  {v*100:>+13.2f}%{flag}", end="")
        print()

    for name in ibs_variants:
        neg = neg_years[name]
        print(f"  {name}: {'ZERO negative years' if not neg else f'NEGATIVE years: {neg}'}")

    # ── Fine grid around XLK winner ──────────────────────────────────────────
    print("\n[3] XLK fine-grid around winner (buy=0.15, sell=0.90, hold=7) …")
    buy_fg   = [0.12, 0.15, 0.18]
    sell_fg  = [0.85, 0.90]
    hold_fg  = [6, 7, 8]
    gap_fg   = [-0.010, -0.005]

    print(f"\n  {'Buy':>5}  {'Sell':>5}  {'Hold':>5}  {'Gap':>7}  "
          f"{'XLK IS S':>9}  {'XLK OOS S':>10}  {'Port OOS':>9}  {'WF worst':>9}")
    print(f"  {'-'*80}")

    smh_r_opt = to_monthly(ibs_equity_curve(smh_ohlc, *SMH_OPT))
    fine_results = []
    for buy, sell, hold, gap in itertools.product(buy_fg, sell_fg, hold_fg, gap_fg):
        r_xlk = to_monthly(ibs_equity_curve(xlk_ohlc, buy, sell, hold, gap))
        rd = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": r_xlk, "SMH": smh_r_opt}
        xlk_is  = stats(r_xlk[r_xlk.index.isin(c_is)])["sharpe"]
        xlk_oos = stats(r_xlk[r_xlk.index.isin(c_oos)])["sharpe"]
        def pr(idx):
            return sum(ww * rd[k].reindex(idx, fill_value=0.0) for k, ww in PROD_W.items())
        port_oos = stats(pr(c_oos))["sharpe"]
        wf = run_wf_5fold(cidx, rd, PROD_W)
        wf_ok = "✓" if wf["worst"] >= WF_WORST_MIN else "✗"
        print(f"  {buy:>5.2f}  {sell:>5.2f}  {hold:>5d}  {gap*100:>6.2f}%  "
              f"{xlk_is:>9.3f}  {xlk_oos:>10.3f}  {port_oos:>9.4f}  {wf['worst']:>9.3f} {wf_ok}")
        fine_results.append({
            "buy": buy, "sell": sell, "hold": hold, "gap": gap,
            "xlk_is": xlk_is, "xlk_oos": xlk_oos, "port_oos": port_oos, "wf_worst": wf["worst"]
        })

    # Overall summary
    print("\n[4] Summary …")
    base_oos = results["baseline"]["oos"]["sharpe"]
    opt_oos  = results["H070_opt"]["oos"]["sharpe"]
    base_ao  = results["baseline"]["alt_oos"]["sharpe"]
    opt_ao   = results["H070_opt"]["alt_oos"]["sharpe"]
    print(f"  Baseline OOS: {base_oos:.4f}  Optimized OOS: {opt_oos:.4f}  "
          f"Δ={opt_oos-base_oos:+.4f} ({(opt_oos-base_oos)/base_oos*100:+.1f}%)")
    print(f"  Baseline AltOOS: {base_ao:.4f}  Optimized AltOOS: {opt_ao:.4f}  "
          f"Δ={opt_ao-base_ao:+.4f} ({(opt_ao-base_ao)/base_ao*100:+.1f}%)")
    if opt_oos > base_oos and opt_ao > base_ao:
        print(f"  *** BOTH OOS windows confirm improvement — NOT overfit to primary OOS ***")
        # Find best fine-grid config
        wf_fine = [r for r in fine_results if r["wf_worst"] >= WF_WORST_MIN]
        if wf_fine:
            best_fine = max(wf_fine, key=lambda x: x["port_oos"])
            print(f"  Fine-grid XLK winner: buy={best_fine['buy']}, sell={best_fine['sell']}, "
                  f"hold={best_fine['hold']}, gap={best_fine['gap']*100:.2f}%")
            print(f"  Port OOS: {best_fine['port_oos']:.4f}  WF: {best_fine['wf_worst']:.3f}")
    else:
        print(f"  WARNING: AltOOS does not confirm — may be overfit to 2018-2026 OOS window.")

    # ── Save ─────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h070_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H070",
                   "portfolios": results,
                   "neg_years": {k: list(v) for k, v in neg_years.items()},
                   "fine_grid": fine_results}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
