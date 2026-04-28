"""
H088 — Full Cross-Validation: H041a+EPHE (Philippines)
=======================================================

Purpose:
  H087's extended sweep found EPHE (iShares MSCI Philippines) adds dual-window
  improvement on top of H087 baseline (OOS 3.4138, AltOOS 3.3470):

    +EPHE: Port OOS 3.4339 (+0.0201), AltOOS 3.3481 (+0.0011), WF 2.325

  Note: AltOOS improvement is marginal (+0.001) and WF drops 2.580 → 2.325.
  Full cross-validation required to confirm the signal is genuine vs noise,
  and to assess whether WF degradation is an issue or sweep artifact.

  EPHE exposure: SM Prime, PLDT, Ayala Corp — Philippines consumer/services/BPO cycle.
  Distinct from manufacturing-heavy Korea/Taiwan: services-led EM growth cycle.

  Full cross-validation:
    [1] Scorecard — incremental breakdown (H087 base → H088)
    [2] Calendar year 2004-2025
    [3] WF 5-fold detail (key — watch for WF degradation)
    [4] H041a standalone: 13-asset+EWS vs 14-asset+EPHE
    [5] H026 standalone (unchanged, top-1 confirmation)
    [6] Further ASEAN/other sweep + H041a weight sensitivity

H087 baseline: OOS 3.4138, AltOOS 3.3470, MaxDD -2.02%, WF 2.580
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

H041A_EWS  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ","EWH","EWT","EWY","EWS"]
H041A_EPHE = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ","EWH","EWT","EWY","EWS","EPHE"]
H026_BIL   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC","BIL"]
H045_BIL   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL"]

# Further sweep on 14-asset universe
EXTEND_EXTRA = {
    "+THD":  H041A_EPHE + ["THD"],   # Thailand (ASEAN manufacturing)
    "+EWN":  H041A_EPHE + ["EWN"],   # Netherlands (ASML semi exposure)
}

# H041a weight sensitivity at H087 level (13-asset) and H088 level (14-asset)
WEIGHT_GRID = [0.15, 0.175, 0.20, 0.206, 0.22, 0.25, 0.28]

PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079",
                   "h080","h081","h082","h083","h084","h085","h086","h087"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h088_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h071","h072","h073","h074","h075","h076","h077","h078","h079",
                "h080","h081","h082","h083","h084","h085","h086","h087"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h088_{ticker}_close_{start}_{end}.parquet"
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
print("H088 — Full Cross-Validation: H041a+EPHE (Philippines)")
print("="*80)

print("\n[0] Building components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))

h045_bil   = build_rotation_monthly(H045_BIL,   FULL_START, FULL_END, 2)
h41_ews    = build_rotation_monthly(H041A_EWS,  FULL_START, FULL_END, 1)
h41_ephe   = build_rotation_monthly(H041A_EPHE, FULL_START, FULL_END, 1)
h026_top1  = build_rotation_monthly(H026_BIL,   FULL_START, FULL_END, 1)

# ── [1] Incremental scorecard ─────────────────────────────────────────────────
print("\n[1] Incremental scorecard …")

portfolios = {
    "H087 baseline":  (h41_ews,  "13-asset top-1"),
    "H088 (+EPHE)":   (h41_ephe, "14-asset top-1"),
}

print(f"\n  {'Portfolio':20}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  "+"-"*100)

scorecard = {}
for name, (h41, desc) in portfolios.items():
    cidx = common_idx(h045_bil, h026_top1, xlk_r, smh_r, igv_r, h41)
    rd   = {"h041a":h41,"h026":h026_top1,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    s_is  = stats(make_port(rd, PROD_W, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
    s_ai  = stats(make_port(rd, PROD_W, cidx[ai_mask(cidx)]))
    s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, PROD_W)
    ww    = min(wf) if wf else 0.0
    wf_ok = ww >= WF_WORST_MIN
    print(f"  {name:20}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
          f"{s_ai['sharpe']:>8.4f}  {s_ao['sharpe']:>9.4f}  "
          f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
          f"{ww:>8.3f} {'✓' if wf_ok else '✗'}")
    scorecard[name] = {"is":s_is,"oos":s_oos,"ai":s_ai,"ao":s_ao,
                       "wf":wf,"wf_worst":ww,"wf_ok":bool(wf_ok),"cidx":cidx,"rd":rd}

# ── [2] Calendar year ─────────────────────────────────────────────────────────
print("\n[2] Calendar year returns 2004-2025 …")
base_d = scorecard["H087 baseline"]
new_d  = scorecard["H088 (+EPHE)"]
print(f"\n  {'Year':>5}  {'H087 base':>10}  {'H088 (+EPHE)':>12}  {'Delta':>7}")
print("  "+"-"*45)
neg_base = neg_new = 0
cal = []
for yr in range(2004, 2026):
    def yr_ret(d):
        yi = d["cidx"][d["cidx"].year == yr]
        if len(yi) == 0: return None
        return float((1+make_port(d["rd"], PROD_W, yi)).prod()-1)
    rb = yr_ret(base_d); rn = yr_ret(new_d)
    if rb is None or rn is None: continue
    if rb < 0: neg_base += 1
    if rn < 0: neg_new  += 1
    print(f"  {yr:>5}  {rb*100:>9.2f}%  {rn*100:>11.2f}%  {(rn-rb)*100:>+6.2f}pp")
    cal.append({"year":yr,"h087":round(rb,4),"h088":round(rn,4)})
print(f"  H087 baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  H088 (+EPHE):  {'ZERO' if neg_new==0 else neg_new} negative years")

# ── [3] WF fold detail ────────────────────────────────────────────────────────
print("\n[3] WF 5-fold detail (watch for degradation) …")
for name, d in scorecard.items():
    folds = d["wf"]
    print(f"  {name:20}: {[round(f,3) for f in folds]} → min {min(folds):.3f}")

# ── [4] H041a standalone ──────────────────────────────────────────────────────
print("\n[4] H041a standalone — both IS windows …")
for label, h41 in [("13-asset+EWS top-1", h41_ews), ("14-asset+EPHE top-1", h41_ephe)]:
    idx  = h41.index
    is_s = stats(h41[is_mask(idx)])["sharpe"]
    oos_s= stats(h41[oos_mask(idx)])["sharpe"]
    ai_s = stats(h41[ai_mask(idx)])["sharpe"]
    ao_s = stats(h41[ao_mask(idx)])["sharpe"]
    print(f"  {label}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")
    if is_s > 0:
        print(f"           Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
              f"Alt deg: {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%")

# ── [5] H026 standalone (unchanged) ──────────────────────────────────────────
print("\n[5] H026 standalone (unchanged, top-1) …")
idx  = h026_top1.index
is_s = stats(h026_top1[is_mask(idx)])["sharpe"]
oos_s= stats(h026_top1[oos_mask(idx)])["sharpe"]
ai_s = stats(h026_top1[ai_mask(idx)])["sharpe"]
ao_s = stats(h026_top1[ao_mask(idx)])["sharpe"]
print(f"  12-asset top-1: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")

# ── [6] Further sweep + H041a weight sensitivity ─────────────────────────────
print("\n[6a] Further geographic sweep on 14-asset+EPHE (top-1) …")
print(f"\n  {'Candidate':14}  {'H041a OOS':>9}  {'H041a AltOOS':>12}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*97)

h41_ephe_oos = stats(h41_ephe[oos_mask(h41_ephe.index)])["sharpe"]
h41_ephe_ao  = stats(h41_ephe[ao_mask(h41_ephe.index)])["sharpe"]
new_base    = scorecard["H088 (+EPHE)"]
s_new_oos   = new_base["oos"]["sharpe"]
s_new_ao    = new_base["ao"]["sharpe"]
print(f"  {'EPHE base':14}  {h41_ephe_oos:>9.4f}  {h41_ephe_ao:>12.4f}  "
      f"{s_new_oos:>9.4f}  {s_new_ao:>11.4f}  "
      f"{new_base['oos']['max_drawdown']*100:>6.2f}%  {new_base['wf_worst']:>7.3f}  —")

sec6_results = {}
for name, tickers in EXTEND_EXTRA.items():
    try:
        h41_v = build_rotation_monthly(tickers, FULL_START, FULL_END, 1)
        cidx  = common_idx(h045_bil, h026_top1, xlk_r, smh_r, igv_r, h41_v)
        rd    = {"h041a":h41_v,"h026":h026_top1,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h41_oos = stats(h41_v[oos_mask(h41_v.index)])["sharpe"]
        h41_ao  = stats(h41_v[ao_mask(h41_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_new_oos and s_ao["sharpe"] > s_new_ao
        print(f"  {name:14}  {h41_oos:>9.4f}  {h41_ao:>12.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        sec6_results[name] = {"port_oos":s_oos["sharpe"],"port_ao":s_ao["sharpe"],
                              "maxdd":s_oos["max_drawdown"],"wf_worst":ww,"both_up":bool(both_up)}
    except Exception as e:
        print(f"  {name:14}  ERROR: {e}")

# Weight sensitivity using best available H041a (whichever confirmed)
print("\n[6b] H041a weight sensitivity (13-asset+EWS baseline) …")
print(f"\n  {'H041a wt':>10}  {'Port OOS':>9}  {'Port AltOOS':>11}  {'WF worst':>9}")
print("  "+"-"*45)
cidx_h087 = scorecard["H087 baseline"]["cidx"]
rd_h087   = scorecard["H087 baseline"]["rd"]
wt_results = {}
for wt in WEIGHT_GRID:
    # Rescale: keep relative proportions of other components, replace h041a weight
    remaining = 1.0 - wt
    base_other = sum(v for k,v in PROD_W.items() if k != "h041a")
    w_adj = {k: (v/base_other)*remaining if k != "h041a" else wt for k,v in PROD_W.items()}
    s_oos = stats(make_port(rd_h087, w_adj, cidx_h087[oos_mask(cidx_h087)]))
    s_ao  = stats(make_port(rd_h087, w_adj, cidx_h087[ao_mask(cidx_h087)]))
    wf    = run_wf(cidx_h087, rd_h087, w_adj)
    ww    = min(wf) if wf else 0.0
    marker = " ← current" if abs(wt - 0.206) < 0.001 else ""
    print(f"  {wt*100:>9.1f}%  {s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  {ww:>9.3f}{marker}")
    wt_results[str(round(wt,3))] = {"oos":s_oos["sharpe"],"ao":s_ao["sharpe"],"wf_worst":ww}

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[7] Summary …")
b = scorecard["H087 baseline"]
h = scorecard["H088 (+EPHE)"]
print(f"  OOS:    {b['oos']['sharpe']:.4f} → {h['oos']['sharpe']:.4f} "
      f"(Δ={h['oos']['sharpe']-b['oos']['sharpe']:+.4f})")
print(f"  AltOOS: {b['ao']['sharpe']:.4f} → {h['ao']['sharpe']:.4f} "
      f"(Δ={h['ao']['sharpe']-b['ao']['sharpe']:+.4f})")
print(f"  MaxDD:  {b['oos']['max_drawdown']*100:.2f}% → {h['oos']['max_drawdown']*100:.2f}%")
print(f"  WF:     {b['wf_worst']:.3f} → {h['wf_worst']:.3f}")

confirmed = (h["oos"]["sharpe"] > b["oos"]["sharpe"] and
             h["ao"]["sharpe"] > b["ao"]["sharpe"] and
             h["wf_ok"])
if confirmed:
    print(f"\n  *** H088 CONFIRMED on BOTH OOS WINDOWS ***")
    print(f"  *** H041a: 14-asset+EPHE top-1 ***")
else:
    print(f"\n  H088 not confirmed")
    if h["oos"]["sharpe"] <= b["oos"]["sharpe"]:
        print(f"  Primary OOS did not improve")
    if h["ao"]["sharpe"] <= b["ao"]["sharpe"]:
        print(f"  AltOOS did not improve")
    if not h["wf_ok"]:
        print(f"  WF worst {h['wf_worst']:.3f} below threshold {WF_WORST_MIN}")

output = {
    "scorecard": {n: {"is":d["is"]["sharpe"],"oos":d["oos"]["sharpe"],
                      "alt_is":d["ai"]["sharpe"],"alt_oos":d["ao"]["sharpe"],
                      "oos_cagr":d["oos"]["cagr"],"oos_dd":d["oos"]["max_drawdown"],
                      "wf_worst":d["wf_worst"],"wf_ok":d["wf_ok"],"wf_folds":d["wf"]}
                  for n,d in scorecard.items()},
    "calendar": cal,
    "sec6a_geographic_sweep": sec6_results,
    "sec6b_weight_sensitivity": wt_results,
    "confirmed": bool(confirmed),
}
out_path = RESULT_DIR / "h088_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
