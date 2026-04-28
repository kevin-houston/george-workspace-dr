"""
H069 — IBS Parameter Optimization for XLK and SMH
===================================================

Purpose:
  All IBS strategies (H037b through H068) have used fixed parameters:
    IBS_BUY = 0.20, IBS_SELL = 0.80, MAX_HOLD = 5, GAP_FILTER = -0.005

  These were optimized for SPY in H009/H037. XLK and SMH are tech ETFs
  with higher daily vol, larger intraday ranges, and stronger post-2018
  IBS signals. Their optimal parameters may differ from SPY.

  Grid: IBS_BUY ∈ {0.10, 0.15, 0.20, 0.25, 0.30}
        IBS_SELL ∈ {0.70, 0.75, 0.80, 0.85, 0.90}
        MAX_HOLD ∈ {3, 4, 5, 6, 7}
        GAP_FILTER ∈ {-1.0% (off), -0.5% (current), 0.0%, +0.25%}

  Method: Sweep each parameter pair on XLK and SMH standalone.
          Evaluate on IS (2008-2017) and OOS (2018-2026) Sharpe.
          Select top-5 configurations by OOS Sharpe for each ticker.
          Test winning configs in the full portfolio (H067 production).

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h069_results.json
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

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# Current production parameters (baseline)
DEFAULT_BUY  = 0.20
DEFAULT_SELL = 0.80
DEFAULT_HOLD = 5
DEFAULT_GAP  = -0.005

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h069_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h069_{ticker}_close_{start}_{end}.parquet"
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


def ibs_equity_curve(ohlc, buy_thresh, sell_thresh, max_hold, gap_filter):
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
            if prev_ibs < buy_thresh and cur_gap >= gap_filter:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > sell_thresh or days_held >= max_hold:
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

def sweep_ticker(ticker, ohlc, is_mask, oos_mask):
    """Grid sweep over IBS parameters for a single ticker."""
    buy_grid  = [0.10, 0.15, 0.20, 0.25, 0.30]
    sell_grid = [0.70, 0.75, 0.80, 0.85, 0.90]
    hold_grid = [3, 4, 5, 6, 7]
    gap_grid  = [-0.010, -0.005, 0.000, 0.0025]

    results = []
    for buy, sell, hold, gap in itertools.product(buy_grid, sell_grid, hold_grid, gap_grid):
        if buy >= sell:
            continue
        eq     = ibs_equity_curve(ohlc, buy, sell, hold, gap)
        r_mon  = to_monthly(eq)
        s_i    = stats(r_mon[r_mon.index.isin(is_mask)])
        s_o    = stats(r_mon[r_mon.index.isin(oos_mask)])
        results.append({
            "ticker": ticker,
            "buy": buy, "sell": sell, "hold": hold, "gap": gap,
            "is_sharpe": s_i["sharpe"],
            "oos_sharpe": s_o["sharpe"],
            "oos_maxdd": s_o["max_drawdown"],
            "deg": round((s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100, 2)
                   if s_i["sharpe"] > 0 else float("nan"),
        })
    return sorted(results, key=lambda x: x["oos_sharpe"], reverse=True)


def main():
    print("\n" + "=" * 80)
    print("H069 — IBS Parameter Optimization for XLK and SMH")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)

    print("\n[0] Loading data …")
    xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
    smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)

    # Build monthly date masks
    def daily_to_monthly_index(ohlc):
        return ohlc.resample("ME").last().index

    xlk_mon = daily_to_monthly_index(xlk_ohlc)
    is_mask  = xlk_mon[(xlk_mon >= is_st_ts) & (xlk_mon <= is_ts)]
    oos_mask = xlk_mon[xlk_mon >= oos_ts]

    # Baseline (current params)
    eq_xlk_base = ibs_equity_curve(xlk_ohlc, DEFAULT_BUY, DEFAULT_SELL, DEFAULT_HOLD, DEFAULT_GAP)
    eq_smh_base = ibs_equity_curve(smh_ohlc, DEFAULT_BUY, DEFAULT_SELL, DEFAULT_HOLD, DEFAULT_GAP)
    r_xlk_base  = to_monthly(eq_xlk_base)
    r_smh_base  = to_monthly(eq_smh_base)
    s_xlk_b_is  = stats(r_xlk_base[r_xlk_base.index.isin(is_mask)])
    s_xlk_b_oos = stats(r_xlk_base[r_xlk_base.index.isin(oos_mask)])
    s_smh_b_is  = stats(r_smh_base[r_smh_base.index.isin(is_mask)])
    s_smh_b_oos = stats(r_smh_base[r_smh_base.index.isin(oos_mask)])
    print(f"  XLK baseline (0.20/0.80/5/-0.5%): IS {s_xlk_b_is['sharpe']:.3f}, OOS {s_xlk_b_oos['sharpe']:.3f}")
    print(f"  SMH baseline (0.20/0.80/5/-0.5%): IS {s_smh_b_is['sharpe']:.3f}, OOS {s_smh_b_oos['sharpe']:.3f}")

    # ── XLK grid ────────────────────────────────────────────────────────────
    print("\n[1] XLK parameter grid …")
    xlk_results = sweep_ticker("XLK", xlk_ohlc, is_mask, oos_mask)

    print(f"\n  Top-10 XLK configs by OOS Sharpe (baseline: OOS {s_xlk_b_oos['sharpe']:.3f}):")
    print(f"  {'Buy':>5}  {'Sell':>5}  {'Hold':>5}  {'Gap':>7}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  {'MaxDD':>7}")
    print(f"  {'-'*70}")
    for r in xlk_results[:10]:
        print(f"  {r['buy']:>5.2f}  {r['sell']:>5.2f}  {r['hold']:>5d}  "
              f"{r['gap']*100:>6.2f}%  {r['is_sharpe']:>7.3f}  {r['oos_sharpe']:>7.3f}  "
              f"{r['deg']:>+8.1f}%  {r['oos_maxdd']*100:>6.2f}%")

    # ── SMH grid ────────────────────────────────────────────────────────────
    print("\n[2] SMH parameter grid …")
    smh_results = sweep_ticker("SMH", smh_ohlc, is_mask, oos_mask)

    print(f"\n  Top-10 SMH configs by OOS Sharpe (baseline: OOS {s_smh_b_oos['sharpe']:.3f}):")
    print(f"  {'Buy':>5}  {'Sell':>5}  {'Hold':>5}  {'Gap':>7}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  {'MaxDD':>7}")
    print(f"  {'-'*70}")
    for r in smh_results[:10]:
        print(f"  {r['buy']:>5.2f}  {r['sell']:>5.2f}  {r['hold']:>5d}  "
              f"{r['gap']*100:>6.2f}%  {r['is_sharpe']:>7.3f}  {r['oos_sharpe']:>7.3f}  "
              f"{r['deg']:>+8.1f}%  {r['oos_maxdd']*100:>6.2f}%")

    # ── Portfolio test with optimized params ────────────────────────────────
    print("\n[3] Portfolio test — production weights with optimized IBS params …")
    print("    Building rotation components …")

    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)

    # Production weights (H067)
    W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}

    # Baseline portfolio
    r_dict_base = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
                   "XLK": r_xlk_base, "SMH": r_smh_base}
    cidx = h041a_r.index
    for k in r_dict_base:
        cidx = cidx.intersection(r_dict_base[k].index)
    cidx  = cidx.sort_values()
    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]

    def port_stats(r_dict, w=W):
        p_is  = sum(ww * r_dict[k].reindex(c_is,  fill_value=0.0) for k, ww in w.items())
        p_oos = sum(ww * r_dict[k].reindex(c_oos, fill_value=0.0) for k, ww in w.items())
        wf    = run_wf_5fold(cidx, r_dict, w)
        return stats(p_is)["sharpe"], stats(p_oos)["sharpe"], wf["worst"]

    base_is, base_oos, base_wf = port_stats(r_dict_base)
    print(f"\n  Baseline (0.20/0.80/5/-0.5% both): IS {base_is:.4f}, OOS {base_oos:.4f}, WF worst {base_wf:.3f}")

    # Test top-5 XLK configs × top-5 SMH configs (25 combos)
    xlk_top = xlk_results[:5]
    smh_top = smh_results[:5]

    print(f"\n  {'XLK params':22}  {'SMH params':22}  {'IS S':>7}  {'OOS S':>7}  {'WF worst':>9}  WF OK")
    print(f"  {'-'*90}")

    port_results = []
    for xr, sr in itertools.product(xlk_top, smh_top):
        eq_xlk = ibs_equity_curve(xlk_ohlc, xr["buy"], xr["sell"], xr["hold"], xr["gap"])
        eq_smh = ibs_equity_curve(smh_ohlc, sr["buy"], sr["sell"], sr["hold"], sr["gap"])
        r_xlk  = to_monthly(eq_xlk)
        r_smh  = to_monthly(eq_smh)
        r_dict = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
                  "XLK": r_xlk, "SMH": r_smh}
        is_s, oos_s, wf_w = port_stats(r_dict)
        wf_ok = "✓" if wf_w >= WF_WORST_MIN else "✗"
        xlk_label = f"b{xr['buy']:.2f}/s{xr['sell']:.2f}/h{xr['hold']}/g{xr['gap']*100:.2f}"
        smh_label = f"b{sr['buy']:.2f}/s{sr['sell']:.2f}/h{sr['hold']}/g{sr['gap']*100:.2f}"
        print(f"  {xlk_label:22}  {smh_label:22}  {is_s:>7.4f}  {oos_s:>7.4f}  {wf_w:>9.3f} {wf_ok}")
        port_results.append({
            "xlk_params": {"buy": xr["buy"], "sell": xr["sell"], "hold": xr["hold"], "gap": xr["gap"]},
            "smh_params": {"buy": sr["buy"], "sell": sr["sell"], "hold": sr["hold"], "gap": sr["gap"]},
            "is_sharpe": round(is_s, 4), "oos_sharpe": round(oos_s, 4), "wf_worst": round(wf_w, 4),
        })

    # Winner
    wf_pass = [r for r in port_results if r["wf_worst"] >= WF_WORST_MIN]
    if wf_pass:
        best = max(wf_pass, key=lambda x: x["oos_sharpe"])
        print(f"\n  WINNER vs baseline ({base_oos:.4f}):")
        print(f"    XLK: {best['xlk_params']}  SMH: {best['smh_params']}")
        print(f"    OOS {best['oos_sharpe']:.4f} ({best['oos_sharpe']-base_oos:+.4f} vs baseline)")
        print(f"    WF worst {best['wf_worst']:.3f}")
        improvement = best["oos_sharpe"] - base_oos
        if improvement > 0.02:
            print(f"    *** MEANINGFUL IMPROVEMENT: +{improvement:.4f} OOS Sharpe ***")
        else:
            print(f"    (Marginal improvement — current params likely near-optimal)")

    # ── Save ─────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h069_results.json"
    with open(out, "w") as f:
        json.dump({
            "hypothesis": "H069",
            "baseline": {"is": base_is, "oos": base_oos, "wf_worst": base_wf},
            "xlk_top10": xlk_results[:10],
            "smh_top10": smh_results[:10],
            "portfolio_combos": port_results,
        }, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
