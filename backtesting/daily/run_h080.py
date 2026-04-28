"""
H080 — Full Cross-Validation: H026+BIL top-2 & H041a+EWJ
==========================================================

Purpose:
  H079 found two independent dual-window improvements over H078 baseline (OOS 2.8094):

  A) H041a+EWJ (Japan equity):  Port OOS +0.038, AltOOS +0.039, WF 2.358 ✓
  B) H026+BIL top-2:            Port OOS +0.081, AltOOS +0.067, WF 2.305 ✓
  Combo (A×B):                  Port OOS 2.9297 (+0.120), AltOOS 2.8928 (+0.108),
                                 MaxDD -2.79%, WF 2.417 ✓

  Mechanism for A: EWJ (iShares MSCI Japan) adds geographic diversification; Japan
  had strong returns in early 2000s recovery and 2023-2024 weak-yen bull market.
  With BIL already handling risk-off months, EWJ fills a distinct return niche.

  Mechanism for B: H026 with BIL+top-2 holds only the 2 strongest SPDR sectors plus
  a cash option. Concentrating in only the top-2 sectors removes weaker conviction
  holdings; BIL gives a genuine exit in sector-wide drawdowns (2022, 2018).

  Full cross-validation:
    [1] Scorecard — 4 windows, incremental breakdown (B alone, A alone, A×B)
    [2] Calendar year 2004-2025 (zero negative years must hold)
    [3] WF 5-fold detail
    [4] H041a standalone: BIL+base vs BIL+EWJ (both IS windows)
    [5] H026 standalone:  base-top3 vs BIL-top3 vs BIL-top2 (both IS windows)
    [6] BIL selection frequency in H026 by year (top-2 variant)

H078 baseline: OOS 2.8094, AltOOS 2.7844, MaxDD -3.00%, WF worst 2.257
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
ALT_IS_END = "2012-12-31"
ALT_OOS_ST = "2013-01-01"
WF_WORST_MIN = 1.75

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD", "BKLN", "EMB"]

H041A_BIL     = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL"]
H041A_BIL_EWJ = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL", "EWJ"]

H026_BASE = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC"]
H026_BIL3 = H026_BASE + ["BIL"]
H026_BIL2 = H026_BASE + ["BIL"]  # same tickers, different top-N

PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h080_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                "h071","h072","h073","h074","h075","h076","h077","h078","h079"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h080_{ticker}_close_{start}_{end}.parquet"
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
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    sel  = []
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
    ret_ser = pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))
    if track_selection:
        return ret_ser, sel
    return ret_ser


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom   = (df["high"]-df["low"]).replace(0, np.nan)
    ibs     = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"]-prev_cl)/prev_cl
    equity  = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o-1) if o > 0 else 0.0
        ret_cc = (c/cp-1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1+ret_oc)
        else:
            days_held += 1; equity *= (1+ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _,v in series], index=pd.DatetimeIndex([d for d,_ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r)}
    eq   = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol  = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r)}


def run_wf(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    folds = []; start = min_train; fold = 0
    while start+test_size <= n and fold < n_folds:
        ti = is_idx[start:start+test_size]
        pr = sum(ww*r_dict[k].reindex(ti, fill_value=0.0) for k,ww in w.items())
        folds.append(stats(pr)["sharpe"])
        start += test_size; fold += 1
    return folds


def make_port(r_dict, w, idx):
    return sum(ww*r_dict[k].reindex(idx, fill_value=0.0) for k,ww in w.items())


def common_idx(*series):
    idx = series[0].index
    for s in series[1:]:
        idx = idx.intersection(s.index)
    return idx.sort_values()


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ai_mask(idx):  return (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


# ── main ─────────────────────────────────────────────────────────────────────

print("="*80)
print("H080 — Full Cross-Validation: H026+BIL top-2 & H041a+EWJ")
print("="*80)

print("\n[0] Building components …")
h045_r = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
xlk_r  = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r  = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r  = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))

print("    H041a: BIL base (8-asset) …")
h41_bil     = build_rotation_monthly(H041A_BIL, FULL_START, FULL_END, 2)
print("    H041a: BIL+EWJ (9-asset) …")
h41_bil_ewj = build_rotation_monthly(H041A_BIL_EWJ, FULL_START, FULL_END, 2)

print("    H026: base top-3 …")
h026_base = build_rotation_monthly(H026_BASE, FULL_START, FULL_END, 3)
print("    H026: BIL top-3 …")
h026_bil3 = build_rotation_monthly(H026_BIL3, FULL_START, FULL_END, 3)
print("    H026: BIL top-2 …")
h026_bil2, bil26_sel = build_rotation_monthly(H026_BIL2, FULL_START, FULL_END, 2, track_selection=True)

# ── [1] Full scorecard ────────────────────────────────────────────────────────
print("\n[1] Full cross-validation scorecard …")

portfolios = {
    "H078 baseline":     (h41_bil,     h026_base, "BIL-8 / top-3"),
    "B only (H026 BIL2)":(h41_bil,     h026_bil2, "BIL-8 / BILtop-2"),
    "A only (EWJ)":      (h41_bil_ewj, h026_base, "EWJ-9 / top-3"),
    "H080 (A+B)":        (h41_bil_ewj, h026_bil2, "EWJ-9 / BILtop-2"),
}

print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  "+"-"*105)

scorecard = {}
for name, (h41, h26, desc) in portfolios.items():
    cidx = common_idx(h045_r, h26, xlk_r, smh_r, igv_r, h41)
    rd   = {"h041a":h41,"h026":h26,"h045":h045_r,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    s_is  = stats(make_port(rd, PROD_W, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
    s_ai  = stats(make_port(rd, PROD_W, cidx[ai_mask(cidx)]))
    s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, PROD_W)
    ww    = min(wf) if wf else 0.0
    wf_ok = ww >= WF_WORST_MIN
    print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
          f"{s_ai['sharpe']:>8.4f}  {s_ao['sharpe']:>9.4f}  "
          f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
          f"{ww:>8.3f} {'✓' if wf_ok else '✗'}")
    scorecard[name] = {"is":s_is,"oos":s_oos,"ai":s_ai,"ao":s_ao,
                       "wf":wf,"wf_worst":ww,"wf_ok":bool(wf_ok),"cidx":cidx,"rd":rd}

# ── [2] Calendar years ────────────────────────────────────────────────────────
print("\n[2] Calendar year returns 2004-2025 …")
base_d  = scorecard["H078 baseline"]
h080_d  = scorecard["H080 (A+B)"]
print(f"\n  {'Year':>5}  {'H078 base':>10}  {'H080 (A+B)':>10}  {'Delta':>7}")
print("  "+"-"*42)
neg_base = neg_new = 0
cal = []
for yr in range(2004, 2026):
    def yr_ret(d):
        yi = d["cidx"][d["cidx"].year == yr]
        if len(yi) == 0: return None
        return float((1+make_port(d["rd"], PROD_W, yi)).prod()-1)
    rb = yr_ret(base_d); rn = yr_ret(h080_d)
    if rb is None or rn is None: continue
    if rb < 0: neg_base += 1
    if rn < 0: neg_new  += 1
    print(f"  {yr:>5}  {rb*100:>9.2f}%  {rn*100:>9.2f}%  {(rn-rb)*100:>+6.2f}pp")
    cal.append({"year":yr,"h078":round(rb,4),"h080":round(rn,4)})
print(f"  H078 baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  H080 (A+B):    {'ZERO' if neg_new==0 else neg_new} negative years")

# ── [3] WF fold detail ────────────────────────────────────────────────────────
print("\n[3] WF 5-fold detail …")
for name, d in scorecard.items():
    folds = d["wf"]
    print(f"  {name:22}: {[round(f,3) for f in folds]} → min {min(folds):.3f}")

# ── [4] H041a standalone ──────────────────────────────────────────────────────
print("\n[4] H041a standalone — both IS windows …")
for label, h41 in [("BIL base (8-asset)", h41_bil), ("BIL+EWJ (9-asset)", h41_bil_ewj)]:
    idx  = h41.index
    is_s = stats(h41[is_mask(idx)])["sharpe"]
    oos_s= stats(h41[oos_mask(idx)])["sharpe"]
    ai_s = stats(h41[ai_mask(idx)])["sharpe"]
    ao_s = stats(h41[ao_mask(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [5] H026 standalone ───────────────────────────────────────────────────────
print("\n[5] H026 standalone — both IS windows …")
for label, h26 in [("Base top-3", h026_base), ("BIL top-3", h026_bil3), ("BIL top-2", h026_bil2)]:
    idx  = h26.index
    is_s = stats(h26[is_mask(idx)])["sharpe"]
    oos_s= stats(h26[oos_mask(idx)])["sharpe"]
    ai_s = stats(h26[ai_mask(idx)])["sharpe"]
    ao_s = stats(h26[ao_mask(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [6] BIL selection in H026 ─────────────────────────────────────────────────
print("\n[6] BIL selection frequency in H026 (top-2) by year …")
bil_counts = {}; total_counts = {}
for date, selected in bil26_sel:
    yr = date.year
    total_counts[yr] = total_counts.get(yr,0)+1
    if "BIL" in selected:
        bil_counts[yr] = bil_counts.get(yr,0)+1
print(f"\n  Year  BIL slots  Total  BIL%")
tb = tbs = 0
for yr in sorted(total_counts):
    bc = bil_counts.get(yr,0); tc = total_counts[yr]
    tb += bc; tbs += tc
    print(f"  {yr}    {bc:>5}    {tc:>5}  {bc/tc*100:>5.1f}%")
print(f"  Total:  {tb:>5}    {tbs:>5}  {tb/tbs*100:.1f}%")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[7] Summary vs H078 baseline …")
b = scorecard["H078 baseline"]
h = scorecard["H080 (A+B)"]
print(f"  OOS:    {b['oos']['sharpe']:.4f} → {h['oos']['sharpe']:.4f} "
      f"(Δ={h['oos']['sharpe']-b['oos']['sharpe']:+.4f})")
print(f"  AltOOS: {b['ao']['sharpe']:.4f} → {h['ao']['sharpe']:.4f} "
      f"(Δ={h['ao']['sharpe']-b['ao']['sharpe']:+.4f})")
print(f"  MaxDD:  {b['oos']['max_drawdown']*100:.2f}% → {h['oos']['max_drawdown']*100:.2f}%")
print(f"  WF:     {b['wf_worst']:.3f} → {h['wf_worst']:.3f}")

if (h["oos"]["sharpe"] > b["oos"]["sharpe"] and
    h["ao"]["sharpe"] > b["ao"]["sharpe"] and
    h["wf_ok"]):
    print(f"\n  *** H080 CONFIRMED on BOTH OOS WINDOWS ***")
    print(f"  *** New H041a: SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL/EWJ (9-asset, top-2) ***")
    print(f"  *** New H026: 11-sector+BIL (12-asset, top-2) ***")
else:
    print(f"\n  H080 NOT confirmed on both windows")

# Save
output = {
    "scorecard": {n: {"is":d["is"]["sharpe"],"oos":d["oos"]["sharpe"],
                      "alt_is":d["ai"]["sharpe"],"alt_oos":d["ao"]["sharpe"],
                      "oos_cagr":d["oos"]["cagr"],"oos_dd":d["oos"]["max_drawdown"],
                      "wf_worst":d["wf_worst"],"wf_ok":d["wf_ok"],"wf_folds":d["wf"]}
                  for n,d in scorecard.items()},
    "calendar": cal,
    "h026_bil2_selection_by_year": [{"year":yr,"bil_slots":bil_counts.get(yr,0),
                                     "total_slots":total_counts[yr]}
                                    for yr in sorted(total_counts)],
}
out_path = RESULT_DIR / "h080_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
