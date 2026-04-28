"""
H063 — Multi-Asset IBS Blend: Splitting the 28% QQQ Budget
===========================================================

Purpose:
  H062 confirmed 5 improving IBS signals. Top candidates for blending with
  H054b (QQQ IBS):
    - XLK IBS: OOS 1.613, Deg +83%, corr to QQQ = 0.784 (high — similar behaviour)
    - SMH IBS: OOS 1.417, Deg +171%, corr to QQQ = 0.592 (moderate)
    - GLD IBS: OOS 0.839, corr to QQQ = 0.091 (low — true diversifier)

  Question: Does splitting the 28% IBS budget between QQQ and a partner
  improve OOS Sharpe and/or WF worst-fold vs H060 (QQQ-only at 28%)?

  Fix vs H063 attempt 1: H026 sector ETF computation now handles sparse data
  (XLC launched 2018, XLRE 2015) by computing top-3 from available tickers
  at each time step rather than dropping all rows with any NaN.

Periods:
  Full: 2003-01 → 2026-04
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h063_results.json
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

# H060 fixed weights
H041A_W = 0.257
H026_W  = 0.073
H045_W  = 0.390

# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    cp = CACHE_DIR / f"h062_{ticker}_ohlc_{start}_{end}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            return df
    if ticker == "QQQ":
        for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060", "h061"]:
            cp2 = CACHE_DIR / f"{prefix}_QQQ_ohlc_{start}_{end}.parquet"
            if cp2.exists():
                df = pd.read_parquet(cp2)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    if ticker == "SPY":
        for fname in [f"h031_spy_ohlc_{start}_{end}.parquet"]:
            cp2 = CACHE_DIR / fname
            if cp2.exists():
                df = pd.read_parquet(cp2)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    cp = CACHE_DIR / f"h063_{ticker}_ohlc_{start}_{end}.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        df.columns = [c.lower() for c in df.columns]
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            return df
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def get_monthly_close(ticker, start, end):
    for prefix in ["h063", "h062", "h060", "h059", "h058", "h057", "h056", "h055",
                   "h054", "h053", "h052", "h051", "h050", "h045", "h041a", "h040",
                   "h039", "h038", "h037", "h036", "h035", "h034", "h033", "h032",
                   "h031", "h030", "h029", "h028", "h027", "h026", "h025"]:
        for suffix in [f"_{ticker}_monthly_{start}_{end}.parquet",
                       f"_{ticker.lower()}_monthly_{start}_{end}.parquet"]:
            cp = CACHE_DIR / f"{prefix}{suffix}"
            if cp.exists():
                df = pd.read_parquet(cp)
                s = df.squeeze() if isinstance(df, pd.DataFrame) else df
                if len(s) > 50:
                    return s
    cp = CACHE_DIR / f"h063_{ticker}_monthly_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    mp = close.resample("ME").last().ffill()
    mp.name = ticker
    mp.to_frame().to_parquet(cp)
    return mp


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


def stats(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 12:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(monthly_rets)}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd  = float((equity / roll_max - 1).min())
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "n_months":     len(monthly_rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Component return series builders
# ─────────────────────────────────────────────────────────────────────────────

def build_h045(start, end):
    """Top-2 treasury momentum (monthly, look-back 1 month)."""
    tickers = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
    prices  = {t: get_monthly_close(t, start, end) for t in tickers}
    df      = pd.DataFrame(prices)
    ret     = df.pct_change()
    rows    = []
    for i in range(1, len(ret)):
        date = ret.index[i]
        mom  = ret.iloc[i - 1]
        avail = mom.dropna()
        if len(avail) < 2:
            continue
        top2 = avail.nlargest(2).index.tolist()
        rows.append((date, ret.iloc[i][top2].mean()))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def build_h041a(start, end):
    """Top-2 multi-asset momentum (12-month)."""
    tickers = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
    prices  = {t: get_monthly_close(t, start, end) for t in tickers}
    df      = pd.DataFrame(prices)
    ret     = df.pct_change()
    rows    = []
    for i in range(12, len(ret)):
        date  = ret.index[i]
        mom12 = (df.iloc[i] / df.iloc[i - 12] - 1)
        avail = mom12.dropna()
        if len(avail) < 2:
            continue
        top2 = avail.nlargest(2).index.tolist()
        rows.append((date, ret.iloc[i][top2].mean()))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def build_h026(start, end):
    """Top-3 sector ETF rotation (1-month mom). Sparse-safe: uses tickers available each period.
    Excludes XLC (launched 2018) and XLRE (launched 2015) from pre-launch periods."""
    tickers = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
    prices  = {}
    for t in tickers:
        try:
            prices[t] = get_monthly_close(t, start, end)
        except Exception:
            pass
    df  = pd.DataFrame(prices)
    ret = df.pct_change()
    rows = []
    for i in range(1, len(ret)):
        date = ret.index[i]
        mom  = ret.iloc[i - 1]
        avail = mom.dropna()
        if len(avail) < 3:
            continue
        top3 = avail.nlargest(3).index.tolist()
        rows.append((date, ret.iloc[i][top3].mean()))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward validation
# ─────────────────────────────────────────────────────────────────────────────

def run_wf(idx, r_dict, weights, min_train=56, test_size=16):
    idx = pd.DatetimeIndex(sorted(idx))
    n   = len(idx)
    fold_sharpes = []
    start = min_train
    while start + test_size <= n:
        test_idx = idx[start:start + test_size]
        port_r = sum(w * r_dict[k].reindex(test_idx, fill_value=0.0) for k, w in weights.items())
        s = stats(port_r)
        fold_sharpes.append(s["sharpe"])
        start += test_size
    if not fold_sharpes:
        return {"avg": 0.0, "worst": 0.0, "folds": []}
    return {
        "avg":   round(float(np.mean(fold_sharpes)), 4),
        "worst": round(float(np.min(fold_sharpes)),  4),
        "folds": [round(x, 4) for x in fold_sharpes],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H063 — Multi-Asset IBS Blend: Splitting the 28% QQQ Budget")
    print("=" * 80)

    is_ts    = pd.Timestamp(IS_END)
    oos_ts   = pd.Timestamp(OOS_START)
    is_st_ts = pd.Timestamp(IS_START)

    # ── 0. Build component return series ─────────────────────────────────────
    print("\n[0] Building component return series …")

    ibs_tickers = ["QQQ", "XLK", "SMH", "GLD"]
    ibs_monthly = {}
    for t in ibs_tickers:
        ohlc = fetch_ohlc(t, FULL_START, FULL_END)
        eq   = ibs_equity_curve(ohlc)
        ibs_monthly[t] = to_monthly(eq)
        s_oos = stats(ibs_monthly[t][ibs_monthly[t].index >= oos_ts])
        s_is  = stats(ibs_monthly[t][(ibs_monthly[t].index >= is_st_ts) & (ibs_monthly[t].index <= is_ts)])
        print(f"    IBS {t}: IS {s_is['sharpe']:.3f}  OOS {s_oos['sharpe']:.3f}  "
              f"({len(ibs_monthly[t])} months total)")

    print("  Building H045 (treasury rotation) …")
    h045_r = build_h045(FULL_START, FULL_END)
    print(f"    H045: {len(h045_r)} months, "
          f"IS {stats(h045_r[(h045_r.index>=is_st_ts)&(h045_r.index<=is_ts)])['sharpe']:.3f}  "
          f"OOS {stats(h045_r[h045_r.index>=oos_ts])['sharpe']:.3f}")

    print("  Building H041a (multi-asset momentum) …")
    h041a_r = build_h041a(FULL_START, FULL_END)
    print(f"    H041a: {len(h041a_r)} months, "
          f"IS {stats(h041a_r[(h041a_r.index>=is_st_ts)&(h041a_r.index<=is_ts)])['sharpe']:.3f}  "
          f"OOS {stats(h041a_r[h041a_r.index>=oos_ts])['sharpe']:.3f}")

    print("  Building H026 (sector rotation, sparse-safe) …")
    h026_r = build_h026(FULL_START, FULL_END)
    print(f"    H026: {len(h026_r)} months, "
          f"IS {stats(h026_r[(h026_r.index>=is_st_ts)&(h026_r.index<=is_ts)])['sharpe']:.3f}  "
          f"OOS {stats(h026_r[h026_r.index>=oos_ts])['sharpe']:.3f}")

    # ── 1. Common index ───────────────────────────────────────────────────────
    r_dict_full = {
        "h041a": h041a_r,
        "h026":  h026_r,
        "h045":  h045_r,
        "QQQ":   ibs_monthly["QQQ"],
        "XLK":   ibs_monthly["XLK"],
        "SMH":   ibs_monthly["SMH"],
        "GLD":   ibs_monthly["GLD"],
    }
    # Build common index using only base components (H041a/H026/H045/QQQ)
    base_keys = ["h041a", "h026", "h045", "QQQ"]
    common_full = r_dict_full["h041a"].index
    for k in base_keys[1:]:
        common_full = common_full.intersection(r_dict_full[k].index)
    common_full = common_full.sort_values()
    common_is   = common_full[(common_full >= is_st_ts) & (common_full <= is_ts)]
    common_oos  = common_full[common_full >= oos_ts]
    print(f"\n  Common index (base components): full={len(common_full)}, "
          f"IS={len(common_is)}, OOS={len(common_oos)}")

    # Extended index including IBS blend partners
    all_keys = list(r_dict_full.keys())
    common_ext = common_full
    for k in all_keys:
        common_ext = common_ext.intersection(r_dict_full[k].index)
    common_ext = common_ext.sort_values()
    common_ext_is  = common_ext[(common_ext >= is_st_ts) & (common_ext <= is_ts)]
    common_ext_oos = common_ext[common_ext >= oos_ts]
    print(f"  Common index (all components):  full={len(common_ext)}, "
          f"IS={len(common_ext_is)}, OOS={len(common_ext_oos)}")

    def port_r(idx, weights):
        return sum(w * r_dict_full[k].reindex(idx, fill_value=0.0) for k, w in weights.items())

    def report(label, weights, run_wf_flag=True):
        # Use the common index for the tickers in this blend
        keys = list(weights.keys())
        cidx = common_full
        for k in keys:
            cidx = cidx.intersection(r_dict_full[k].index)
        cidx = cidx.sort_values()
        c_is  = cidx[(cidx >= is_st_ts) & (cidx <= is_ts)]
        c_oos = cidx[cidx >= oos_ts]

        r_is_   = port_r(c_is,   weights)
        r_oos_  = port_r(c_oos,  weights)
        s_i = stats(r_is_)
        s_o = stats(r_oos_)
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        wf  = run_wf(cidx, r_dict_full, weights) if run_wf_flag else {"avg": 0.0, "worst": 0.0, "folds": []}
        wf_ok = "✓" if wf["worst"] >= 1.75 else "✗"
        is_n  = f"n={len(c_is)}"
        oos_n = f"n={len(c_oos)}"
        print(f"  {label:<42}  IS {s_i['sharpe']:>6.3f}({is_n})  OOS {s_o['sharpe']:>6.3f}({oos_n})  "
              f"Deg {deg:>+7.1f}%  DD {s_o['max_drawdown']*100:>6.2f}%  "
              f"WF worst {wf['worst']:>5.3f} {wf_ok}  folds={wf['folds']}")
        return {"is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None,
                "wf": wf, "weights": weights, "n_is": len(c_is), "n_oos": len(c_oos)}

    # ── 2. Run all candidates ─────────────────────────────────────────────────
    print("\n[1] IS/OOS/WF results for all blend candidates …\n")

    res = {}

    # H060 baseline (QQQ only)
    res["H060_baseline"] = report("H060 baseline (QQQ 28%)", {
        "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.280
    })
    print()

    # 2-way IBS splits within 28% budget
    for partner, pw in [("XLK", 0.14), ("SMH", 0.14), ("GLD", 0.14)]:
        label = f"14% QQQ + 14% {partner}"
        res[label] = report(label, {
            "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.14, partner: pw
        })

    print()
    for qqq_w, gld_w, label in [
        (0.18, 0.10, "18% QQQ + 10% GLD"),
        (0.16, 0.12, "16% QQQ + 12% GLD"),
        (0.21, 0.07, "21% QQQ +  7% GLD"),
    ]:
        res[label] = report(label, {
            "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": qqq_w, "GLD": gld_w
        })

    print()
    # Can we exceed 28% total with diversification?
    res["20% QQQ + 12% GLD (32% total)"] = report("20% QQQ + 12% GLD (32% total)", {
        "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.20, "GLD": 0.12
    })

    print()
    # 3-way IBS
    res["14% QQQ + 8% SMH + 6% GLD"] = report("14% QQQ + 8% SMH + 6% GLD", {
        "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": 0.14, "SMH": 0.08, "GLD": 0.06
    })

    print()
    # QQQ-only references
    print("  -- QQQ-only references --")
    for qqq_w in [0.14, 0.21, 0.28, 0.32]:
        label = f"QQQ-only {int(qqq_w*100)}%"
        res[label] = report(label, {
            "h041a": H041A_W, "h026": H026_W, "h045": H045_W, "QQQ": qqq_w
        })

    # ── 3. Winner analysis ────────────────────────────────────────────────────
    print("\n[2] WF-consistent candidates (worst fold ≥ 1.75), ranked by OOS Sharpe …")
    wf_pass = {k: v for k, v in res.items() if v["wf"]["worst"] >= 1.75}
    for k, v in sorted(wf_pass.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True):
        print(f"   {k:<42}  OOS {v['oos']['sharpe']:.4f}  WF worst {v['wf']['worst']:.3f}  "
              f"WF folds {v['wf']['folds']}")

    # ── 4. Save results ───────────────────────────────────────────────────────
    out = RESULT_DIR / "h063_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H063", "results": {
            k: {kk: vv for kk, vv in v.items() if kk != "weights"}
            for k, v in res.items()
        }}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
