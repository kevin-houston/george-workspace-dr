"""
H078 — Full Cross-Validation of BIL Addition to H041a
======================================================

Purpose:
  H077 found adding BIL (SPDR 1-3 Month T-Bill ETF) to H041a's 7-asset rotation
  universe gives a massive dual-window improvement:
    Portfolio OOS: 2.6951 → 2.8094 (+0.114)
    Portfolio AltOOS: 2.7057 → 2.7844 (+0.079)
    MaxDD: -3.91% → -3.00%

  Full cross-validation to confirm this is genuine, not overfit.

  Tests:
    [1] Full scorecard — primary IS/OOS + alternate IS/OOS (4 windows)
    [2] Calendar year returns 2004-2025 (zero negative years must hold)
    [3] WF 5-fold detail
    [4] H041a standalone comparison (BIL+ vs base on both IS windows)
    [5] Monthly BIL selection frequency by year (understand when BIL fires)

H076 baseline: OOS 2.6951, AltOOS 2.7057, WF worst 2.379
H077 winner: H041a +BIL (8-asset, top-2)
Proposed new production:
  H041a 20.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 2%
  H041a universe: SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL (8-asset, top-2)

Periods:
  Full:   2003-01 → 2026-04
  IS:     2008-01 → 2017-12
  OOS:    2018-01 → 2026-04
  AltIS:  2003-01 → 2012-12
  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h078_results.json
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

WF_WORST_MIN = 1.75

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD", "BKLN", "EMB"]
H026_TICKERS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]

H041A_BASE = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H041A_BIL  = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL"]

H076_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}  # baseline (current production)
H078_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}  # same weights, H041a signal changes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072", "h073", "h074", "h075",
                   "h076", "h077"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h078_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h069", "h070", "h071", "h072", "h073", "h074", "h075",
                "h076", "h077"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070",
                "h071", "h072", "h073", "h074", "h075", "h076", "h077", "h078"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h078_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold, track_selection=False):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows   = []
    sel    = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
        if track_selection:
            sel.append((monthly_px.index[i], top_n))
    ret_ser = pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))
    if track_selection:
        return ret_ser, sel
    return ret_ser


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
    eq    = (1 + r).cumprod()
    n_yr  = len(r) / 12.0
    cagr  = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol   = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


def run_wf(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
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
    return folds


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


# ── main ────────────────────────────────────────────────────────────────────

print("=" * 80)
print("H078 — Full Cross-Validation of BIL Addition to H041a")
print("=" * 80)
print()

print("[0] Building components …")
h045_r = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
h026_r = build_rotation_monthly(H026_TICKERS, FULL_START, FULL_END, 3)
xlk_r  = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
smh_r  = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
igv_r  = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))
print("    H041a base (7-asset) …")
h41_base = build_rotation_monthly(H041A_BASE, FULL_START, FULL_END, 2)
print("    H041a BIL+ (8-asset) …")
h41_bil, bil_selection = build_rotation_monthly(H041A_BIL, FULL_START, FULL_END, 2, track_selection=True)

# Common index (intersection)
cidx_base = h045_r.index
for s in [h026_r, xlk_r, smh_r, igv_r, h41_base]:
    cidx_base = cidx_base.intersection(s.index)
cidx_base = cidx_base.sort_values()

cidx_bil = h045_r.index
for s in [h026_r, xlk_r, smh_r, igv_r, h41_bil]:
    cidx_bil = cidx_bil.intersection(s.index)
cidx_bil = cidx_bil.sort_values()

r_base = {"h041a": h41_base, "h026": h026_r, "h045": h045_r,
          "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
r_bil  = {"h041a": h41_bil,  "h026": h026_r, "h045": h045_r,
          "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}

ts = pd.Timestamp
is_m    = lambda idx: (idx >= ts(IS_START))  & (idx <= ts(IS_END))
oos_m   = lambda idx:  idx >= ts(OOS_START)
ai_m    = lambda idx: (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
ao_m    = lambda idx:  idx >= ts(ALT_OOS_ST)

# ── [1] Full scorecard ───────────────────────────────────────────────────────
print()
print("[1] Full cross-validation scorecard …")

portfolios = {
    "H076 baseline": (H076_W, r_base, cidx_base),
    "H078 (BIL+)":   (H078_W, r_bil,  cidx_bil),
}

print(f"\n  {'Portfolio':18}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  " + "-" * 100)

scorecard = {}
for name, (w, rd, idx) in portfolios.items():
    s_is  = stats(make_port(rd, w, idx[is_m(idx)]))
    s_oos = stats(make_port(rd, w, idx[oos_m(idx)]))
    s_ai  = stats(make_port(rd, w, idx[ai_m(idx)]))
    s_ao  = stats(make_port(rd, w, idx[ao_m(idx)]))
    wf    = run_wf(idx, rd, w)
    ww    = min(wf) if wf else 0.0
    wf_ok = ww >= WF_WORST_MIN
    print(f"  {name:18}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
          f"{s_ai['sharpe']:>8.4f}  {s_ao['sharpe']:>9.4f}  "
          f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
          f"{ww:>8.3f} {'✓' if wf_ok else '✗'}")
    scorecard[name] = {"is": s_is, "oos": s_oos, "ai": s_ai, "ao": s_ao,
                       "wf": wf, "wf_worst": ww, "wf_ok": bool(wf_ok)}

# ── [2] Calendar year returns ─────────────────────────────────────────────────
print()
print("[2] Calendar year returns 2004-2025 …")
print(f"\n  {'Year':>5}  {'Baseline':>10}  {'BIL+':>10}  {'Delta':>7}")
print("  " + "-" * 40)

neg_base = neg_bil = 0
cal = []
for yr in range(2004, 2026):
    def yr_ret(idx, rd, w):
        yi = idx[idx.year == yr]
        if len(yi) == 0: return None
        return float((1 + make_port(rd, w, yi)).prod() - 1)
    rb = yr_ret(cidx_base, r_base, H076_W)
    ri = yr_ret(cidx_bil,  r_bil,  H078_W)
    if rb is None or ri is None: continue
    if rb < 0: neg_base += 1
    if ri < 0: neg_bil += 1
    print(f"  {yr:>5}  {rb*100:>9.2f}%  {ri*100:>9.2f}%  {(ri-rb)*100:>+6.2f}pp")
    cal.append({"year": yr, "baseline": round(rb, 4), "bil_plus": round(ri, 4)})

print(f"  Baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  BIL+:     {'ZERO' if neg_bil==0 else neg_bil} negative years")

# ── [3] WF fold detail ───────────────────────────────────────────────────────
print()
print("[3] WF 5-fold detail …")
for name, (w, rd, idx) in portfolios.items():
    folds = run_wf(idx, rd, w)
    print(f"  {name}: {[round(f, 3) for f in folds]} → min {min(folds):.3f}")

# ── [4] H041a standalone (both IS windows) ─────────────────────────────────
print()
print("[4] H041a standalone — both IS windows …")

for label, h41 in [("Base (7-asset)", h41_base), ("BIL+ (8-asset)", h41_bil)]:
    idx = h41.index
    is_s  = stats(h41[is_m(idx)])["sharpe"]
    oos_s = stats(h41[oos_m(idx)])["sharpe"]
    ai_s  = stats(h41[ai_m(idx)])["sharpe"]
    ao_s  = stats(h41[ao_m(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [5] BIL selection frequency ──────────────────────────────────────────────
print()
print("[5] BIL selection frequency by year …")

bil_counts = {}
total_counts = {}
for date, selected in bil_selection:
    yr = date.year
    total_counts[yr] = total_counts.get(yr, 0) + 1
    if "BIL" in selected:
        bil_counts[yr] = bil_counts.get(yr, 0) + 1

print(f"\n  Year  BIL slots  Total  BIL%")
total_bil = total_bil_slots = 0
for yr in sorted(total_counts.keys()):
    bc = bil_counts.get(yr, 0)
    tc = total_counts[yr]
    total_bil += bc
    total_bil_slots += tc
    pct = bc / tc * 100 if tc > 0 else 0
    print(f"  {yr}    {bc:>5}    {tc:>5}  {pct:>5.1f}%")
print(f"  Total:  {total_bil:>5}    {total_bil_slots:>5}  "
      f"{total_bil/total_bil_slots*100:.1f}%")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("[6] Summary vs H076 baseline …")
b = scorecard["H076 baseline"]
i = scorecard["H078 (BIL+)"]
print(f"  OOS:    {b['oos']['sharpe']:.4f} → {i['oos']['sharpe']:.4f} "
      f"(Δ={i['oos']['sharpe']-b['oos']['sharpe']:+.4f})")
print(f"  AltOOS: {b['ao']['sharpe']:.4f} → {i['ao']['sharpe']:.4f} "
      f"(Δ={i['ao']['sharpe']-b['ao']['sharpe']:+.4f})")
print(f"  MaxDD:  {b['oos']['max_drawdown']*100:.2f}% → {i['oos']['max_drawdown']*100:.2f}%")
print(f"  WF:     {b['wf_worst']:.3f} → {i['wf_worst']:.3f}")

if (i["oos"]["sharpe"] > b["oos"]["sharpe"] and
    i["ao"]["sharpe"] > b["ao"]["sharpe"] and
    i["wf_ok"]):
    print(f"\n  *** BIL CONFIRMED on BOTH OOS WINDOWS → new production H041a universe ***")
    print(f"  *** New production: H041a 20.6% (SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL top-2) ***")
else:
    print(f"\n  BIL not confirmed on both windows")

# Save
output = {
    "scorecard": {n: {"is": d["is"]["sharpe"], "oos": d["oos"]["sharpe"],
                      "alt_is": d["ai"]["sharpe"], "alt_oos": d["ao"]["sharpe"],
                      "oos_cagr": d["oos"]["cagr"], "oos_dd": d["oos"]["max_drawdown"],
                      "wf_worst": d["wf_worst"], "wf_ok": d["wf_ok"], "wf_folds": d["wf"]}
                  for n, d in scorecard.items()},
    "calendar": cal,
    "bil_selection_by_year": [{"year": yr, "bil_slots": bil_counts.get(yr, 0),
                                "total_slots": total_counts[yr]}
                               for yr in sorted(total_counts.keys())],
}
out_path = RESULT_DIR / "h078_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print()
print("=" * 80)
