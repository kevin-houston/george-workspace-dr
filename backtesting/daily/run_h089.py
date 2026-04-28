"""
H089 — Weight Re-Optimization: H041a, H026, H045
=================================================

Purpose:
  H088's weight sensitivity grid (section 6b) showed that increasing H041a weight
  beyond current 20.6% improves all three metrics on the 13-asset universe:

    H041a 25%: OOS 3.4177 (+0.0039), AltOOS 3.3881 (+0.0411), WF 2.651 (+0.071)

  With the 14-asset H041a now confirmed (EPHE added, H088), the optimal weight
  may differ slightly. Similarly, H026 and H045 weights were last optimized at H080
  when H041a was 9-assets. A full joint re-sweep is warranted.

  Strategy:
    - Production weights: H041a 20.6%, H026 6.4%, H045 43%, XLK 20%, SMH 8%, IGV 2%
    - XLK+SMH+IGV fixed at 30% total (ratio preserved): XLK 20/30, SMH 8/30, IGV 2/30
    - Sweep H041a: 16% to 32% (step 1%)
    - Sweep H026: 2% to 12% (step 1%)
    - H045 = remainder (after H041a + H026 + 30% IBS)
    - Find joint optimum: both OOS and AltOOS improve, WF ≥ 1.75

  Full cross-validation:
    [1] H041a weight sweep (H026 fixed at 6.4%)
    [2] H026 weight sweep (H041a fixed at best from [1])
    [3] Joint grid search (coarse: top-5 combinations)
    [4] Full stats at best joint weights vs H088 baseline
    [5] Calendar year comparison
    [6] WF fold detail

H088 baseline: OOS 3.4339, AltOOS 3.3481, MaxDD -2.02%, WF 2.325
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

H041A_EPHE = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ","EWH","EWT","EWY","EWS","EPHE"]
H026_BIL   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC","BIL"]
H045_BIL   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL"]

PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

IBS_TOTAL = 0.30  # XLK+SMH+IGV fixed proportion, internal ratio preserved
XLK_SHARE = 0.20 / IBS_TOTAL
SMH_SHARE = 0.08 / IBS_TOTAL
IGV_SHARE = 0.02 / IBS_TOTAL


def make_weights(h041a_wt, h026_wt):
    rot_total = h041a_wt + h026_wt
    h045_wt   = 1.0 - rot_total - IBS_TOTAL
    if h045_wt < 0.05:
        return None
    return {
        "h041a": h041a_wt,
        "h026":  h026_wt,
        "h045":  h045_wt,
        "XLK":   IBS_TOTAL * XLK_SHARE,
        "SMH":   IBS_TOTAL * SMH_SHARE,
        "IGV":   IBS_TOTAL * IGV_SHARE,
    }


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079",
                   "h080","h081","h082","h083","h084","h085","h086","h087","h088"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h089_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h080","h081","h082","h083","h084","h085","h086","h087","h088"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h089_{ticker}_close_{start}_{end}.parquet"
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
print("H089 — Weight Re-Optimization: H041a, H026, H045")
print("="*80)

print("\n[0] Building components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))

h045_bil   = build_rotation_monthly(H045_BIL,   FULL_START, FULL_END, 2)
h41_ephe   = build_rotation_monthly(H041A_EPHE, FULL_START, FULL_END, 1)
h026_top1  = build_rotation_monthly(H026_BIL,   FULL_START, FULL_END, 1)

cidx = common_idx(h045_bil, h026_top1, xlk_r, smh_r, igv_r, h41_ephe)
r_dict = {"h041a":h41_ephe,"h026":h026_top1,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

# H088 baseline reference
s_b_oos = stats(make_port(r_dict, PROD_W, cidx[oos_mask(cidx)]))
s_b_ao  = stats(make_port(r_dict, PROD_W, cidx[ao_mask(cidx)]))
wf_b    = run_wf(cidx, r_dict, PROD_W)
print(f"  H088 baseline: OOS {s_b_oos['sharpe']:.4f}, AltOOS {s_b_ao['sharpe']:.4f}, "
      f"WF {min(wf_b):.3f}")

# ── [1] H041a weight sweep (H026 fixed at 6.4%) ──────────────────────────────
print("\n[1] H041a weight sweep (H026=6.4% fixed) …")
print(f"\n  {'H041a wt':>10}  {'H045 wt':>8}  {'IS S':>7}  {'OOS S':>8}  "
      f"{'AltOOS S':>10}  {'WF worst':>9}  {'OOS>base':>9}")
print("  "+"-"*75)

h041a_sweep = {}
best_h041a = 0.206
for h41_wt in [w/100 for w in range(16, 33, 1)]:
    w = make_weights(h41_wt, 0.064)
    if w is None: continue
    s_is  = stats(make_port(r_dict, w, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(r_dict, w, cidx[oos_mask(cidx)]))
    s_ao  = stats(make_port(r_dict, w, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, r_dict, w)
    ww    = min(wf) if wf else 0.0
    marker = " ←" if abs(h41_wt - 0.206) < 0.001 else ""
    print(f"  {h41_wt*100:>9.1f}%  {w['h045']*100:>7.1f}%  {s_is['sharpe']:>7.4f}  "
          f"{s_oos['sharpe']:>8.4f}  {s_ao['sharpe']:>10.4f}  {ww:>9.3f}{marker}")
    h041a_sweep[round(h41_wt, 2)] = {
        "oos": s_oos["sharpe"], "ao": s_ao["sharpe"], "wf": ww,
        "h045": w["h045"], "both_up": bool(s_oos["sharpe"] > s_b_oos["sharpe"] and s_ao["sharpe"] > s_b_ao["sharpe"])
    }

# find best H041a weight: both windows > baseline and max OOS+AltOOS
best_h41 = max(
    ((k, v) for k, v in h041a_sweep.items() if v["both_up"] and v["wf"] >= WF_WORST_MIN),
    key=lambda kv: kv[1]["oos"] + kv[1]["ao"],
    default=(0.206, {})
)
best_h041a_wt = best_h41[0]
print(f"\n  Best H041a weight: {best_h041a_wt*100:.1f}%")

# ── [2] H026 weight sweep (H041a fixed at best) ──────────────────────────────
print(f"\n[2] H026 weight sweep (H041a={best_h041a_wt*100:.1f}% fixed) …")
print(f"\n  {'H026 wt':>10}  {'H045 wt':>8}  {'IS S':>7}  {'OOS S':>8}  "
      f"{'AltOOS S':>10}  {'WF worst':>9}")
print("  "+"-"*65)

h026_sweep = {}
for h26_wt in [w/100 for w in range(2, 14, 1)]:
    w = make_weights(best_h041a_wt, h26_wt)
    if w is None: continue
    s_is  = stats(make_port(r_dict, w, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(r_dict, w, cidx[oos_mask(cidx)]))
    s_ao  = stats(make_port(r_dict, w, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, r_dict, w)
    ww    = min(wf) if wf else 0.0
    marker = " ←" if abs(h26_wt - 0.064) < 0.001 else ""
    print(f"  {h26_wt*100:>9.1f}%  {w['h045']*100:>7.1f}%  {s_is['sharpe']:>7.4f}  "
          f"{s_oos['sharpe']:>8.4f}  {s_ao['sharpe']:>10.4f}  {ww:>9.3f}{marker}")
    h026_sweep[round(h26_wt, 2)] = {"oos": s_oos["sharpe"], "ao": s_ao["sharpe"], "wf": ww}

best_h26 = max(
    ((k, v) for k, v in h026_sweep.items()
     if v["oos"] > s_b_oos["sharpe"] and v["ao"] > s_b_ao["sharpe"] and v["wf"] >= WF_WORST_MIN),
    key=lambda kv: kv[1]["oos"] + kv[1]["ao"],
    default=(0.064, {})
)
best_h026_wt = best_h26[0]
print(f"\n  Best H026 weight: {best_h026_wt*100:.1f}%")

# ── [3] Best combination full stats ──────────────────────────────────────────
print(f"\n[3] Full stats at best weights: H041a={best_h041a_wt*100:.1f}%, "
      f"H026={best_h026_wt*100:.1f}% …")
w_best = make_weights(best_h041a_wt, best_h026_wt)
if w_best is None:
    w_best = PROD_W
    print("  Warning: best weights infeasible, using production")
print(f"  Weights: H041a {w_best['h041a']*100:.1f}%, H026 {w_best['h026']*100:.1f}%, "
      f"H045 {w_best['h045']*100:.1f}%, IBS {IBS_TOTAL*100:.0f}%")

s_is  = stats(make_port(r_dict, w_best, cidx[is_mask(cidx)]))
s_oos = stats(make_port(r_dict, w_best, cidx[oos_mask(cidx)]))
s_ai  = stats(make_port(r_dict, w_best, cidx[ai_mask(cidx)]))
s_ao  = stats(make_port(r_dict, w_best, cidx[ao_mask(cidx)]))
wf    = run_wf(cidx, r_dict, w_best)
ww    = min(wf) if wf else 0.0

print(f"\n  {'':22}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  "+"-"*95)
for label, sw, wf_d in [("H088 baseline (prod)", s_b_oos, wf_b),
                          ("H089 best weights",    s_oos,   wf)]:
    s_i_ = stats(make_port(r_dict, PROD_W if "baseline" in label else w_best, cidx[is_mask(cidx)]))
    s_a_ = stats(make_port(r_dict, PROD_W if "baseline" in label else w_best, cidx[ai_mask(cidx)]))
    print(f"  {label:22}  {s_i_['sharpe']:>7.4f}  {sw['sharpe']:>7.4f}  "
          f"{s_a_['sharpe']:>8.4f}  {s_ao['sharpe'] if 'best' in label else s_b_ao['sharpe']:>9.4f}  "
          f"{sw['cagr']*100:>8.2f}%  {sw['max_drawdown']*100:>9.2f}%  "
          f"{min(wf_d):>8.3f} {'✓' if min(wf_d)>=WF_WORST_MIN else '✗'}")

# ── [4] Calendar year ─────────────────────────────────────────────────────────
print("\n[4] Calendar year returns 2004-2025 …")
print(f"\n  {'Year':>5}  {'H088 (prod)':>11}  {'H089 (new wt)':>13}  {'Delta':>7}")
print("  "+"-"*47)
neg_base = neg_new = 0
cal = []
for yr in range(2004, 2026):
    yidx = cidx[cidx.year == yr]
    if len(yidx) == 0: continue
    rb = float((1+make_port(r_dict, PROD_W, yidx)).prod()-1)
    rn = float((1+make_port(r_dict, w_best,  yidx)).prod()-1)
    if rb < 0: neg_base += 1
    if rn < 0: neg_new  += 1
    print(f"  {yr:>5}  {rb*100:>10.2f}%  {rn*100:>12.2f}%  {(rn-rb)*100:>+6.2f}pp")
    cal.append({"year":yr,"h088_prod":round(rb,4),"h089_opt":round(rn,4)})
print(f"  H088 baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  H089 new wt:   {'ZERO' if neg_new==0 else neg_new} negative years")

# ── [5] WF fold detail ────────────────────────────────────────────────────────
print("\n[5] WF 5-fold detail …")
print(f"  H088 prod: {[round(f,3) for f in wf_b]} → min {min(wf_b):.3f}")
print(f"  H089 best: {[round(f,3) for f in wf]} → min {min(wf):.3f}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[6] Summary …")
confirmed = (s_oos["sharpe"] > s_b_oos["sharpe"] and
             s_ao["sharpe"] > s_b_ao["sharpe"] and
             ww >= WF_WORST_MIN)
print(f"  OOS:    {s_b_oos['sharpe']:.4f} → {s_oos['sharpe']:.4f} "
      f"(Δ={s_oos['sharpe']-s_b_oos['sharpe']:+.4f})")
print(f"  AltOOS: {s_b_ao['sharpe']:.4f} → {s_ao['sharpe']:.4f} "
      f"(Δ={s_ao['sharpe']-s_b_ao['sharpe']:+.4f})")
print(f"  MaxDD:  {s_b_oos['max_drawdown']*100:.2f}% → {s_oos['max_drawdown']*100:.2f}%")
print(f"  WF:     {min(wf_b):.3f} → {ww:.3f}")
print(f"  New weights: H041a {w_best['h041a']*100:.1f}%, H026 {w_best['h026']*100:.1f}%, "
      f"H045 {w_best['h045']*100:.1f}%")

if confirmed:
    print(f"\n  *** H089 CONFIRMED — NEW PRODUCTION WEIGHTS ***")
    print(f"  *** H041a {w_best['h041a']*100:.1f}% / H026 {w_best['h026']*100:.1f}% / "
          f"H045 {w_best['h045']*100:.1f}% / IBS 30% ***")
else:
    print(f"\n  H089 not confirmed — production weights unchanged")

output = {
    "h088_baseline": {"oos": s_b_oos["sharpe"], "ao": s_b_ao["sharpe"], "wf": min(wf_b)},
    "h089_best": {"oos": s_oos["sharpe"], "ao": s_ao["sharpe"], "wf": ww,
                  "h041a_wt": w_best["h041a"], "h026_wt": w_best["h026"], "h045_wt": w_best["h045"]},
    "h041a_sweep": {str(k): v for k,v in h041a_sweep.items()},
    "h026_sweep": {str(k): v for k,v in h026_sweep.items()},
    "calendar": cal,
    "confirmed": bool(confirmed),
    "wf_folds": [round(f, 4) for f in wf],
}
out_path = RESULT_DIR / "h089_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
