"""
H064 — XLK IBS as QQQ Replacement: Corrected Portfolio Reconstruction
======================================================================

Purpose:
  H062 found: XLK IBS OOS 1.613 (Deg +83%) > QQQ IBS OOS 1.472 (Deg +84%).
  H063 found marginal improvements from blending XLK/SMH with QQQ.

  Key fix vs H063: H041a/H026/H045 use rank(12m_mom) + rank(inv_6m_vol)
  composite signal, NOT simple 1-month momentum. This fix is critical —
  using the wrong signal made H045 appear to have OOS Sharpe 0.216 instead
  of its true ~2.0+ contribution to the H060 portfolio.

  Tests:
    A: H060 baseline (QQQ 28%)
    B: QQQ → XLK entirely (XLK 28%)
    C: QQQ → SMH entirely (SMH 28%)
    D: 14% QQQ + 14% XLK
    E: 14% QQQ + 14% SMH
    F: XLK 20% + SMH 8% (best blend from H063)

  All keep H041a 25.7% / H026 7.3% / H045 39.0%.

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h064_results.json
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

# ─────────────────────────────────────────────────────────────────────────────
# Data
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
    if ticker == "SPY":
        cp = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("SPY", axis=1, level=1)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h064_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    """Daily close price Series, with cache."""
    # Try existing daily OHLC caches first
    ohlc_cp = CACHE_DIR / f"h064_{ticker}_ohlc_{start}_{end}.parquet"
    if not ohlc_cp.exists():
        for pfx in ["h062", "h063"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
            if p.exists():
                ohlc_cp = p
                break
    if ohlc_cp.exists():
        df = pd.read_parquet(ohlc_cp)
        df.columns = [c.lower() for c in df.columns]
        if "close" in df.columns:
            return df["close"].rename(ticker)

    # Try daily close cache
    cp = CACHE_DIR / f"h064_{ticker}_close_{start}_{end}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        return df.squeeze().rename(ticker)

    # QQQ OHLC from prior caches
    if ticker == "QQQ":
        for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060", "h061"]:
            p = CACHE_DIR / f"{prefix}_QQQ_ohlc_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)

    # SPY OHLC
    if ticker == "SPY":
        p = CACHE_DIR / f"h031_spy_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("SPY", axis=1, level=1)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)

    # Try h027 prices parquet (multi-ticker format used in early hypotheses)
    for pf in sorted(CACHE_DIR.glob(f"h0??_prices_*.parquet")):
        df = pd.read_parquet(pf)
        if isinstance(df.columns, pd.MultiIndex):
            if ticker in df.columns.get_level_values(1):
                close = df.xs(ticker, axis=1, level=1)["Close"]
                return close.rename(ticker)

    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold, label=""):
    """
    Correct signal: rank(12m_mom) + rank(inv_6m_vol), top-n, monthly rebalance.
    Matches original H041/H026/H045 implementations exactly.
    """
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    Warning: {t} failed: {e}")

    daily_df = pd.DataFrame(closes).sort_index()
    # Remove columns that are all NaN
    daily_df = daily_df.dropna(how="all", axis=1)

    monthly_px   = daily_df.resample("ME").last()
    monthly_rets = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    rows = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        avg_ret = monthly_rets.iloc[i][top_n].mean()
        rows.append((month_end, avg_ret))

    if not rows:
        return pd.Series(dtype=float, name=label)
    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]),
                     name=label)


# ─────────────────────────────────────────────────────────────────────────────
# IBS backtest
# ─────────────────────────────────────────────────────────────────────────────

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
        ret_oc   = (c / o - 1)      if o > 0      else 0.0
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
    eq = pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))
    return eq


def to_monthly(eq_daily):
    return eq_daily.resample("ME").last().ffill().pct_change().dropna()


def stats(monthly_rets):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(monthly_rets)}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd  = float((equity / roll_max - 1).min())
    return {
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "n_months":     len(monthly_rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward (IS-anchored, 5 folds matching H059 structure)
# ─────────────────────────────────────────────────────────────────────────────

def run_wf_5fold(idx, r_dict, weights, min_train=56, test_size=16, n_folds=5):
    """WF starting from IS_START (2008-01), 5 folds of 16 months."""
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    fold_sharpes = []
    start = min_train
    fold  = 0
    while start + test_size <= n and fold < n_folds:
        test_idx = is_idx[start:start + test_size]
        port_r = sum(w * r_dict[k].reindex(test_idx, fill_value=0.0) for k, w in weights.items())
        s = stats(port_r)
        fold_sharpes.append(s["sharpe"])
        start += test_size
        fold  += 1
    if not fold_sharpes:
        return {"avg": 0.0, "worst": 0.0, "folds": []}
    return {
        "avg":   round(float(np.mean(fold_sharpes)), 4),
        "worst": round(float(np.min(fold_sharpes)),  4),
        "folds": [round(x, 4) for x in fold_sharpes],
        "n_is":  n,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H064 — XLK IBS as QQQ Replacement (corrected portfolio reconstruction)")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)

    # ── 0. Build component return series (correct signal) ─────────────────────
    print("\n[0] Building component return series (rank(12m_mom)+rank(inv_6m_vol)) …")

    print("  Building H045 (treasury rotation, 7 ETFs, top-2) …")
    h045_r = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"],
        FULL_START, FULL_END, n_hold=2, label="h045"
    )
    s_h045_is  = stats(h045_r[(h045_r.index >= is_st_ts) & (h045_r.index <= is_ts)])
    s_h045_oos = stats(h045_r[h045_r.index >= oos_ts])
    print(f"    H045: {len(h045_r)} months  IS {s_h045_is['sharpe']:.3f}  OOS {s_h045_oos['sharpe']:.3f}")

    print("  Building H041a (multi-asset momentum, 7 assets, top-2) …")
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"],
        FULL_START, FULL_END, n_hold=2, label="h041a"
    )
    s_h041a_is  = stats(h041a_r[(h041a_r.index >= is_st_ts) & (h041a_r.index <= is_ts)])
    s_h041a_oos = stats(h041a_r[h041a_r.index >= oos_ts])
    print(f"    H041a: {len(h041a_r)} months  IS {s_h041a_is['sharpe']:.3f}  OOS {s_h041a_oos['sharpe']:.3f}")

    print("  Building H026 (sector rotation, 11 sectors, top-3) …")
    h026_r = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, n_hold=3, label="h026"
    )
    s_h026_is  = stats(h026_r[(h026_r.index >= is_st_ts) & (h026_r.index <= is_ts)])
    s_h026_oos = stats(h026_r[h026_r.index >= oos_ts])
    print(f"    H026: {len(h026_r)} months  IS {s_h026_is['sharpe']:.3f}  OOS {s_h026_oos['sharpe']:.3f}")

    print("  Building IBS return series …")
    ibs_m = {}
    for t in ["QQQ", "XLK", "SMH"]:
        ohlc     = fetch_ohlc(t, FULL_START, FULL_END)
        eq       = ibs_equity_curve(ohlc)
        ibs_m[t] = to_monthly(eq)
        s_is  = stats(ibs_m[t][(ibs_m[t].index >= is_st_ts) & (ibs_m[t].index <= is_ts)])
        s_oos = stats(ibs_m[t][ibs_m[t].index >= oos_ts])
        print(f"    IBS {t}: IS {s_is['sharpe']:.3f}  OOS {s_oos['sharpe']:.3f}")

    r_dict = {
        "h041a": h041a_r, "h026": h026_r, "h045": h045_r,
        "QQQ": ibs_m["QQQ"], "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"],
    }

    # Common index
    base_keys = ["h041a", "h026", "h045", "QQQ"]
    cidx = r_dict["h041a"].index
    for k in base_keys[1:]:
        cidx = cidx.intersection(r_dict[k].index)
    # Add XLK and SMH (they have full data)
    cidx = cidx.intersection(r_dict["XLK"].index).intersection(r_dict["SMH"].index)
    cidx = cidx.sort_values()

    c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
    c_oos = cidx[cidx >= oos_ts]
    print(f"\n  Common index: {len(cidx)} months ({cidx[0].date()} → {cidx[-1].date()})")
    print(f"  IS: n={len(c_is)}  OOS: n={len(c_oos)}")

    def port_rets(idx, weights):
        return sum(w * r_dict[k].reindex(idx, fill_value=0.0) for k, w in weights.items())

    def full_report(name, weights):
        r_is  = port_rets(c_is,  weights)
        r_oos = port_rets(c_oos, weights)
        s_i   = stats(r_is)
        s_o   = stats(r_oos)
        deg   = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")

        # OOS sub-periods
        sub = {}
        for lbl, st, en in [
            ("2018-2020", "2018-01-01", "2019-12-31"),
            ("2020-2022", "2020-01-01", "2021-12-31"),
            ("2022-2024", "2022-01-01", "2023-12-31"),
            ("2024-2026", "2024-01-01", "2026-04-27"),
        ]:
            si = cidx[(cidx >= pd.Timestamp(st)) & (cidx <= pd.Timestamp(en))]
            sub[lbl] = stats(port_rets(si, weights))["sharpe"]

        wf = run_wf_5fold(cidx, r_dict, weights)
        wf_ok = "✓" if wf["worst"] >= 1.75 else "✗"

        print(f"\n  [{name}]")
        print(f"    IS  Sharpe: {s_i['sharpe']:.4f}  CAGR {s_i['cagr']*100:.2f}%  MaxDD {s_i['max_drawdown']*100:.2f}%")
        print(f"    OOS Sharpe: {s_o['sharpe']:.4f}  CAGR {s_o['cagr']*100:.2f}%  MaxDD {s_o['max_drawdown']*100:.2f}%  Deg {deg:+.1f}%")
        print(f"    OOS sub:    " + "  ".join(f"{k} {v:.2f}" for k, v in sub.items()))
        print(f"    WF 5-fold:  avg {wf['avg']:.3f}  worst {wf['worst']:.3f} {wf_ok}  folds {wf['folds']}")
        return {
            "is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None,
            "oos_sub": sub, "wf": wf,
        }

    # ── 1. Run all variants ───────────────────────────────────────────────────
    print("\n[1] Portfolio variant analysis …")

    res = {}
    VARIANTS = [
        ("A_H060_baseline", "A: H060 baseline (QQQ 28%)",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.280}),
        ("B_XLK_28pct",     "B: QQQ→XLK (XLK 28%)",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "XLK": 0.280}),
        ("C_SMH_28pct",     "C: QQQ→SMH (SMH 28%)",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "SMH": 0.280}),
        ("D_QQQ14_XLK14",   "D: 14% QQQ + 14% XLK",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.14, "XLK": 0.14}),
        ("E_QQQ14_SMH14",   "E: 14% QQQ + 14% SMH",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.14, "SMH": 0.14}),
        ("F_XLK20_SMH8",    "F: XLK 20% + SMH 8%",
         {"h041a": H041A_W, "h026": H026_W, "h045": H045_W, "XLK": 0.20, "SMH": 0.08}),
    ]
    for key, name, w in VARIANTS:
        res[key] = full_report(name, w)

    # ── 2. Year-by-year OOS ───────────────────────────────────────────────────
    print("\n[2] Year-by-year OOS Sharpe comparison …")
    header = f"  {'Year':>5}  " + "  ".join(f"{v[0][:7]:>9}" for v in VARIANTS)
    print(header)
    print("  " + "-" * (7 + len(VARIANTS) * 12))
    for year in range(2018, 2026):
        yr_idx = cidx[(cidx >= pd.Timestamp(f"{year}-01-01")) & (cidx <= pd.Timestamp(f"{year}-12-31"))]
        if len(yr_idx) < 3:
            continue
        row = f"  {year:>5}  "
        for key, name, w in VARIANTS:
            s = stats(port_rets(yr_idx, w))["sharpe"]
            row += f"  {s:>9.3f}"
        print(row)

    # ── 3. Summary ────────────────────────────────────────────────────────────
    print("\n[3] Summary — all variants by OOS Sharpe …")
    for k, v in sorted(res.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
        wf_ok = "✓" if v["wf"]["worst"] >= 1.75 else "✗"
        print(f"   {k:<20}: OOS {v['oos']['sharpe']:.4f}  WF worst {v['wf']['worst']:.3f} {wf_ok}  "
              f"folds {v['wf']['folds']}")

    # ── 4. Save results ───────────────────────────────────────────────────────
    out = RESULT_DIR / "h064_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H064", "results": res}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
