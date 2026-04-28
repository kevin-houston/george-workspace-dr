"""
H082 — Full Cross-Validation: H045+BIL, H041a top-1, H026 weight optimization
===============================================================================

Purpose:
  H081 found three improvements over H080 baseline (OOS 2.9297):

  A) H041a top-1 (9-asset):    Port OOS +0.093, AltOOS +0.061, WF 2.106 ✓
  B) H045+BIL (10-asset):      Port OOS +0.185, AltOOS +0.131, WF 2.417 ✓
  C) H026 weight 10-15%:       OOS monotonically increasing, AltOOS too

  H045+BIL is the biggest single-component finding in the entire research programme.
  H045 standalone OOS jumps from 1.631 (base-9) to 2.227 (+37%).
  Mechanism: BIL is zero duration; in 2022 rate shocks and 2018 Fed cycle, even
  BKLN had some duration drag. BIL earns T-bill rate with zero vol or duration.

  Full cross-validation:
    [1] Scorecard — incremental (B alone, A alone, B+A, B+A+C_opt)
    [2] Calendar year 2004-2025
    [3] WF 5-fold detail (focus on top-1 WF stability)
    [4] H045 standalone: base vs BIL+
    [5] H041a standalone: top-2 vs top-1 (both IS windows)
    [6] Weight grid on new combination (H045+BIL + H041a top-1)

H080 baseline: OOS 2.9297, AltOOS 2.8928, MaxDD -2.79%, WF 2.417
H081 best combo (A+B): expected OOS ~3.2, AltOOS ~3.08 (from additive estimates)
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

H045_BASE  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB"]
H045_BIL   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL"]
H041A_9    = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ"]
H026_BIL2  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC","BIL"]

# H080 production weights
PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}
H041A_H045_RATIO = 0.206 / 0.43


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079","h080","h081"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h082_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h071","h072","h073","h074","h075","h076","h077","h078","h079","h080","h081"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h082_{ticker}_close_{start}_{end}.parquet"
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
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


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
print("H082 — Full Cross-Validation: H045+BIL, H041a top-1, H026 weight optimization")
print("="*80)

print("\n[0] Building components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))

print("    H026+BIL top-2 (H080 production) …")
h026_bil2 = build_rotation_monthly(H026_BIL2, FULL_START, FULL_END, 2)
print("    H041a 9-asset top-2 (H080 production) …")
h41_top2  = build_rotation_monthly(H041A_9, FULL_START, FULL_END, 2)
print("    H041a 9-asset top-1 …")
h41_top1  = build_rotation_monthly(H041A_9, FULL_START, FULL_END, 1)
print("    H045 base (9-asset, top-2) …")
h045_base = build_rotation_monthly(H045_BASE, FULL_START, FULL_END, 2)
print("    H045 BIL+ (10-asset, top-2) …")
h045_bil  = build_rotation_monthly(H045_BIL, FULL_START, FULL_END, 2)

# ── [1] Scorecard — incremental breakdown ─────────────────────────────────────
print("\n[1] Incremental scorecard …")

# H080 baseline
cidx_h080 = common_idx(h045_base, h026_bil2, xlk_r, smh_r, igv_r, h41_top2)
r_h080    = {"h041a":h41_top2,"h026":h026_bil2,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

# B alone: H045+BIL, top-2 H041a
cidx_b = common_idx(h045_bil, h026_bil2, xlk_r, smh_r, igv_r, h41_top2)
r_b    = {"h041a":h41_top2,"h026":h026_bil2,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

# A alone: top-1 H041a, base H045
cidx_a = common_idx(h045_base, h026_bil2, xlk_r, smh_r, igv_r, h41_top1)
r_a    = {"h041a":h41_top1,"h026":h026_bil2,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

# A+B: top-1 H041a + H045+BIL
cidx_ab = common_idx(h045_bil, h026_bil2, xlk_r, smh_r, igv_r, h41_top1)
r_ab    = {"h041a":h41_top1,"h026":h026_bil2,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

portfolios = {
    "H080 baseline":    (PROD_W, r_h080, cidx_h080),
    "B only (H045+BIL)":(PROD_W, r_b,    cidx_b),
    "A only (top-1)":   (PROD_W, r_a,    cidx_a),
    "H082 (A+B)":       (PROD_W, r_ab,   cidx_ab),
}

print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  "+"-"*105)

scorecard = {}
for name, (w, rd, cidx) in portfolios.items():
    s_is  = stats(make_port(rd, w, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(rd, w, cidx[oos_mask(cidx)]))
    s_ai  = stats(make_port(rd, w, cidx[ai_mask(cidx)]))
    s_ao  = stats(make_port(rd, w, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, w)
    ww    = min(wf) if wf else 0.0
    wf_ok = ww >= WF_WORST_MIN
    print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
          f"{s_ai['sharpe']:>8.4f}  {s_ao['sharpe']:>9.4f}  "
          f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
          f"{ww:>8.3f} {'✓' if wf_ok else '✗'}")
    scorecard[name] = {"is":s_is,"oos":s_oos,"ai":s_ai,"ao":s_ao,
                       "wf":wf,"wf_worst":ww,"wf_ok":bool(wf_ok),"cidx":cidx,"rd":rd,"w":w}

# ── [2] Calendar year ─────────────────────────────────────────────────────────
print("\n[2] Calendar year returns 2004-2025 …")
base_d = scorecard["H080 baseline"]
new_d  = scorecard["H082 (A+B)"]
print(f"\n  {'Year':>5}  {'H080 base':>10}  {'H082 (A+B)':>10}  {'Delta':>7}")
print("  "+"-"*44)
neg_base = neg_new = 0
cal = []
for yr in range(2004, 2026):
    def yr_ret(d):
        yi = d["cidx"][d["cidx"].year == yr]
        if len(yi) == 0: return None
        return float((1+make_port(d["rd"], d["w"], yi)).prod()-1)
    rb = yr_ret(base_d); rn = yr_ret(new_d)
    if rb is None or rn is None: continue
    if rb < 0: neg_base += 1
    if rn < 0: neg_new  += 1
    print(f"  {yr:>5}  {rb*100:>9.2f}%  {rn*100:>9.2f}%  {(rn-rb)*100:>+6.2f}pp")
    cal.append({"year":yr,"h080":round(rb,4),"h082":round(rn,4)})
print(f"  H080 baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  H082 (A+B):    {'ZERO' if neg_new==0 else neg_new} negative years")

# ── [3] WF fold detail ────────────────────────────────────────────────────────
print("\n[3] WF 5-fold detail …")
for name, d in scorecard.items():
    folds = d["wf"]
    print(f"  {name:22}: {[round(f,3) for f in folds]} → min {min(folds):.3f}")

# ── [4] H045 standalone ───────────────────────────────────────────────────────
print("\n[4] H045 standalone — both IS windows …")
for label, h45 in [("Base top-2 (9-asset)", h045_base), ("BIL+ top-2 (10-asset)", h045_bil)]:
    idx  = h45.index
    is_s = stats(h45[is_mask(idx)])["sharpe"]
    oos_s= stats(h45[oos_mask(idx)])["sharpe"]
    ai_s = stats(h45[ai_mask(idx)])["sharpe"]
    ao_s = stats(h45[ao_mask(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [5] H041a standalone ──────────────────────────────────────────────────────
print("\n[5] H041a standalone — both IS windows …")
for label, h41 in [("9-asset top-2", h41_top2), ("9-asset top-1", h41_top1)]:
    idx  = h41.index
    is_s = stats(h41[is_mask(idx)])["sharpe"]
    oos_s= stats(h41[oos_mask(idx)])["sharpe"]
    ai_s = stats(h41[ai_mask(idx)])["sharpe"]
    ao_s = stats(h41[ao_mask(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [6] Weight grid on new combination ────────────────────────────────────────
print("\n[6] Weight grid on H082 (top-1 + H045+BIL) …")
print(f"\n  {'H026 wt':>8}  {'H041a wt':>9}  {'H045 wt':>8}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}")
print("  "+"-"*80)

h026_weights = [0.040, 0.064, 0.080, 0.100, 0.120, 0.150, 0.180, 0.200]
weight_grid = {}
for w26 in h026_weights:
    remaining = 0.70 - w26
    w41 = round(remaining * H041A_H045_RATIO / (1 + H041A_H045_RATIO), 3)
    w45 = round(remaining - w41, 3)
    w   = {"h041a":w41,"h026":w26,"h045":w45,"XLK":0.20,"SMH":0.08,"IGV":0.02}
    s_oos = stats(make_port(r_ab, w, cidx_ab[oos_mask(cidx_ab)]))
    s_ao  = stats(make_port(r_ab, w, cidx_ab[ao_mask(cidx_ab)]))
    wf    = run_wf(cidx_ab, r_ab, w)
    ww    = min(wf) if wf else 0.0
    mark = "←" if abs(w26-0.064)<0.001 else ""
    print(f"  {w26:>7.1%}  {w41:>8.1%}  {w45:>7.1%}  "
          f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
          f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {mark}")
    weight_grid[w26] = {"h041a":w41,"h026":w26,"h045":w45,
                        "oos":round(s_oos["sharpe"],4),"alt_oos":round(s_ao["sharpe"],4),
                        "maxdd":round(s_oos["max_drawdown"],4),"wf_worst":round(ww,4)}

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[7] Summary …")
b = scorecard["H080 baseline"]
h = scorecard["H082 (A+B)"]
print(f"  OOS:    {b['oos']['sharpe']:.4f} → {h['oos']['sharpe']:.4f} "
      f"(Δ={h['oos']['sharpe']-b['oos']['sharpe']:+.4f})")
print(f"  AltOOS: {b['ao']['sharpe']:.4f} → {h['ao']['sharpe']:.4f} "
      f"(Δ={h['ao']['sharpe']-b['ao']['sharpe']:+.4f})")
print(f"  MaxDD:  {b['oos']['max_drawdown']*100:.2f}% → {h['oos']['max_drawdown']*100:.2f}%")
print(f"  WF:     {b['wf_worst']:.3f} → {h['wf_worst']:.3f}")

best_w = max(weight_grid, key=lambda k: weight_grid[k]["oos"])
bw = weight_grid[best_w]
print(f"\n  Weight grid best: H026={best_w:.1%}, H041a={bw['h041a']:.1%}, H045={bw['h045']:.1%}")
print(f"    OOS {bw['oos']:.4f}, AltOOS {bw['alt_oos']:.4f}, WF {bw['wf_worst']:.3f}")

if (h["oos"]["sharpe"] > b["oos"]["sharpe"] and
    h["ao"]["sharpe"] > b["ao"]["sharpe"] and
    h["wf_ok"]):
    print(f"\n  *** H082 CONFIRMED on BOTH OOS WINDOWS ***")
    print(f"  *** H045 universe: + BIL (10-asset, top-2) ***")
    print(f"  *** H041a: top-1 on 9-asset universe ***")
else:
    print(f"\n  H082 not confirmed — check WF and AltOOS")

output = {
    "scorecard": {n: {"is":d["is"]["sharpe"],"oos":d["oos"]["sharpe"],
                      "alt_is":d["ai"]["sharpe"],"alt_oos":d["ao"]["sharpe"],
                      "oos_cagr":d["oos"]["cagr"],"oos_dd":d["oos"]["max_drawdown"],
                      "wf_worst":d["wf_worst"],"wf_ok":d["wf_ok"],"wf_folds":d["wf"]}
                  for n,d in scorecard.items()},
    "calendar": cal,
    "weight_grid": {str(k):v for k,v in weight_grid.items()},
}
out_path = RESULT_DIR / "h082_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
