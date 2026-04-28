"""
H066 — H065 Production Portfolio: Full Cross-Validation
========================================================

Purpose:
  H065 found the new production portfolio:
    H041a 22.6% / H026 6.4% / H045 39.0% / XLK IBS 24% / SMH IBS 8%
  OOS Sharpe 2.387, WF worst 2.222 ✓

  This hypothesis performs full cross-validation:
    1. Alternate IS/OOS split (IS: 2003-2012, OOS: 2013-2026 — 13yr OOS)
    2. Calendar-year returns 2004-2025
    3. Negative month analysis
    4. Comparison table: H060 vs H065

  Also confirms the top-2 H065 finalists:
    F1: XLK 24% + SMH 8% (32% total) — highest OOS, WF 2.222
    F2: XLK 20% + SMH 8% (28% total) — highest WF (2.395), OOS 2.374

Periods:
  Full: 2003-01 → 2026-04
  Primary IS:  2008-01 → 2017-12
  Primary OOS: 2018-01 → 2026-04
  Alt IS:      2003-01 → 2012-12
  Alt OOS:     2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h066_results.json
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
ALT_IS_END  = "2012-12-31"
ALT_OOS_ST  = "2013-01-01"

IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5
GAP_FILTER = -0.005

# H060 weights
H060_W = {"h041a": 0.257, "h026": 0.073, "h045": 0.390, "QQQ": 0.280}
# H065 finalists
H065_F1_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.390, "XLK": 0.240, "SMH": 0.080}  # 32% IBS
H065_F2_W = {"h041a": 0.257, "h026": 0.073, "h045": 0.390, "XLK": 0.200, "SMH": 0.080}  # 28% IBS

# ─────────────────────────────────────────────────────────────────────────────
# Data (reuse H064 caches)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065"]:
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
    cp = CACHE_DIR / f"h066_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065"]:
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
    for pfx in ["h064", "h065"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h066_{ticker}_close_{start}_{end}.parquet"
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
    n_neg   = int((r < 0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r),
            "n_negative": n_neg,
            "pct_negative": round(n_neg / len(r) * 100, 1)}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H066 — H065 Production Portfolio: Full Cross-Validation")
    print("=" * 80)

    ts = {k: pd.Timestamp(v) for k, v in {
        "is_st": IS_START, "is_en": IS_END,
        "oos_st": OOS_START,
        "alt_is_en": ALT_IS_END, "alt_oos_st": ALT_OOS_ST,
    }.items()}

    # ── 0. Build component return series ─────────────────────────────────────
    print("\n[0] Building component return series …")

    h045_r  = build_rotation_monthly(
        ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"], FULL_START, FULL_END, 2)
    h041a_r = build_rotation_monthly(
        ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
    h026_r  = build_rotation_monthly(
        ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
        FULL_START, FULL_END, 3)

    ibs_m = {}
    for t in ["QQQ", "XLK", "SMH"]:
        ohlc     = fetch_ohlc(t, FULL_START, FULL_END)
        ibs_m[t] = to_monthly(ibs_equity_curve(ohlc))
        s_is  = stats(ibs_m[t][(ibs_m[t].index >= ts["is_st"]) & (ibs_m[t].index <= ts["is_en"])])
        s_oos = stats(ibs_m[t][ibs_m[t].index >= ts["oos_st"]])
        print(f"    IBS {t}: IS {s_is['sharpe']:.3f}  OOS {s_oos['sharpe']:.3f}")

    r_dict = {
        "h041a": h041a_r, "h026": h026_r, "h045": h045_r,
        "QQQ": ibs_m["QQQ"], "XLK": ibs_m["XLK"], "SMH": ibs_m["SMH"],
    }

    # Common index
    cidx = r_dict["h041a"].index
    for k in r_dict:
        cidx = cidx.intersection(r_dict[k].index)
    cidx = cidx.sort_values()
    c_is     = cidx[(cidx >= ts["is_st"])   & (cidx <= ts["is_en"])]
    c_oos    = cidx[cidx >= ts["oos_st"]]
    c_alt_is = cidx[cidx <= ts["alt_is_en"]]
    c_alt_oos= cidx[cidx >= ts["alt_oos_st"]]
    print(f"\n  cidx: full={len(cidx)}  primary IS={len(c_is)}  primary OOS={len(c_oos)}")
    print(f"         alt IS={len(c_alt_is)}  alt OOS={len(c_alt_oos)}")

    PORTFOLIOS = {
        "H060_baseline": H060_W,
        "H065_F1 (XLK24+SMH8, 32%)": H065_F1_W,
        "H065_F2 (XLK20+SMH8, 28%)": H065_F2_W,
    }

    def port_r(idx, w):
        return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())

    # ── 1. IS/OOS stats comparison ────────────────────────────────────────────
    print("\n[1] Primary IS/OOS comparison …")
    print(f"\n  {'Portfolio':<36}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}  "
          f"{'OOS CAGR':>9}  {'OOS MaxDD':>9}  {'Neg Mths':>9}")
    print(f"  {'-'*95}")
    primary_stats = {}
    for name, w in PORTFOLIOS.items():
        s_i = stats(port_r(c_is,  w))
        s_o = stats(port_r(c_oos, w))
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100 if s_i["sharpe"] > 0 else float("nan")
        primary_stats[name] = {"is": s_i, "oos": s_o, "deg": round(deg, 2) if not np.isnan(deg) else None}
        print(f"  {name:<36}  {s_i['sharpe']:>7.3f}  {s_o['sharpe']:>7.3f}  {deg:>+8.1f}%  "
              f"{s_o['cagr']*100:>8.2f}%  {s_o['max_drawdown']*100:>8.2f}%  "
              f"{s_o['n_negative']:>5}/{s_o['n_months']:}")

    # ── 2. Alternate IS/OOS stats ─────────────────────────────────────────────
    print("\n[2] Alternate IS/OOS (IS: 2003-2012, OOS: 2013-2026) …")
    print(f"\n  {'Portfolio':<36}  {'Alt IS S':>9}  {'Alt OOS S':>10}  {'Alt Deg':>8}  "
          f"{'OOS CAGR':>9}  {'OOS MaxDD':>9}")
    print(f"  {'-'*95}")
    alt_stats = {}
    for name, w in PORTFOLIOS.items():
        s_ai = stats(port_r(c_alt_is,  w))
        s_ao = stats(port_r(c_alt_oos, w))
        deg  = (s_ao["sharpe"] - s_ai["sharpe"]) / s_ai["sharpe"] * 100 if s_ai["sharpe"] > 0 else float("nan")
        alt_stats[name] = {"alt_is": s_ai, "alt_oos": s_ao, "alt_deg": round(deg, 2) if not np.isnan(deg) else None}
        print(f"  {name:<36}  {s_ai['sharpe']:>9.3f}  {s_ao['sharpe']:>10.3f}  {deg:>+8.1f}%  "
              f"{s_ao['cagr']*100:>8.2f}%  {s_ao['max_drawdown']*100:>8.2f}%")

    # ── 3. Calendar-year returns ──────────────────────────────────────────────
    print("\n[3] Annual returns (2004–2025) …")
    port_names = list(PORTFOLIOS.keys())
    header = f"  {'Year':>5}  " + "  ".join(f"{n[:16]:>16}" for n in port_names)
    print(header)
    print("  " + "-" * (7 + len(port_names) * 19))
    annual = {}
    neg_years = {n: [] for n in port_names}
    for year in range(2004, 2026):
        yr_idx = cidx[(cidx >= pd.Timestamp(f"{year}-01-01")) &
                       (cidx <= pd.Timestamp(f"{year}-12-31"))]
        if len(yr_idx) < 3:
            continue
        row = f"  {year:>5}  "
        annual[year] = {}
        for name, w in PORTFOLIOS.items():
            r   = port_r(yr_idx, w)
            s   = stats(r)
            cag = s["cagr"] * 100
            annual[year][name] = cag
            marker = " ✗" if cag < 0 else "  "
            row += f"  {cag:>14.2f}%{marker}"
            if cag < 0:
                neg_years[name].append(year)
        print(row)

    print(f"\n  Negative calendar years:")
    for name, yrs in neg_years.items():
        print(f"    {name}: {yrs if yrs else 'NONE'}")

    # ── 4. Summary scorecard ──────────────────────────────────────────────────
    print("\n[4] Comprehensive scorecard …")
    print(f"\n  {'Metric':<32}  {'H060':>10}  {'H065_F1':>10}  {'H065_F2':>10}")
    print(f"  {'-'*65}")

    def row(label, vals):
        print(f"  {label:<32}  " + "  ".join(f"{v:>10}" for v in vals))

    pn = list(PORTFOLIOS.keys())
    row("Primary IS Sharpe",   [f"{primary_stats[n]['is']['sharpe']:.4f}"    for n in pn])
    row("Primary OOS Sharpe",  [f"{primary_stats[n]['oos']['sharpe']:.4f}"   for n in pn])
    row("Primary OOS Deg%",    [f"{primary_stats[n]['deg']:+.1f}%"           for n in pn])
    row("Primary OOS CAGR",    [f"{primary_stats[n]['oos']['cagr']*100:.2f}%" for n in pn])
    row("Primary OOS MaxDD",   [f"{primary_stats[n]['oos']['max_drawdown']*100:.2f}%" for n in pn])
    row("Alt OOS Sharpe",      [f"{alt_stats[n]['alt_oos']['sharpe']:.4f}"   for n in pn])
    row("Alt OOS Deg%",        [f"{alt_stats[n]['alt_deg']:+.1f}%"           for n in pn])
    row("Neg calendar years",  [str(neg_years[n]) if neg_years[n] else "NONE" for n in pn])

    # ── 5. Save ────────────────────────────────────────────────────────────────
    out = RESULT_DIR / "h066_results.json"
    with open(out, "w") as f:
        json.dump({"hypothesis": "H066",
                   "primary_stats": primary_stats,
                   "alt_stats": alt_stats,
                   "annual_returns": annual,
                   "neg_years": neg_years}, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
