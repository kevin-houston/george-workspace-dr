"""
H103 — Weight Re-optimization Post-H102
========================================

Purpose:
  H102 expanded H026 to 16-asset (added IEF+TIP), gaining +0.036/+0.045 OOS/AltOOS.
  With two more defensive assets in H026, the signal quality improved.
  The H026 weight (18%) was set with 14-asset H026; may now benefit from re-calibration.

  H100 showed the weight landscape is very flat near 23%/18%/29%, but H026 is
  meaningfully stronger now — may shift the AltOOS-heavy Pareto frontier.

  Sweep:
    Phase 1 — H026 sweep (H041a=23% fixed): 10% to 28% in 1pp steps
    Phase 2 — H041a sweep (H026=best from P1): 16% to 35% in 1pp steps

  H026_IEF_TIP (16-asset): 11-sector+BIL+GLD+TLT+IEF+TIP
  Baseline: H102 (OOS 3.7943, AltOOS 3.7699, WF 2.929)
  Current weights: H041a 23% / H026 18% / H045 29%
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

IBS_TOTAL = 0.30
XLK_SHARE = 0.20 / IBS_TOTAL
SMH_SHARE = 0.08 / IBS_TOTAL
IGV_SHARE = 0.02 / IBS_TOTAL

H041A_FULL   = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
                "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_IEF_TIP = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
                "BIL","GLD","TLT","IEF","TIP"]
H045_PROD    = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT"]

_PREFIXES = [f"h{i:03d}" for i in range(62, 103)]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h103_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp2 = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp2.exists():
            return pd.read_parquet(cp2).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h103_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold=1):
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


def make_weights(h041a_wt, h026_wt):
    h045_wt = 1.0 - h041a_wt - h026_wt - IBS_TOTAL
    if h045_wt < 0.05:
        return None
    return {
        "h041a": h041a_wt, "h026": h026_wt, "h045": h045_wt,
        "XLK": IBS_TOTAL * XLK_SHARE, "SMH": IBS_TOTAL * SMH_SHARE,
        "IGV": IBS_TOTAL * IGV_SHARE,
    }


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
print("H103 — Weight Re-optimization Post-H102")
print("="*80)

print("\n[0] Building all components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h41   = build_rotation_monthly(H041A_FULL,   FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_IEF_TIP, FULL_START, FULL_END, 1)
h045  = build_rotation_monthly(H045_PROD,    FULL_START, FULL_END, 2)

cidx  = common_idx(h41, h026, h045, xlk_r, smh_r, igv_r)
rd    = {"h041a":h41,"h026":h026,"h045":h045,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

CURR_W = make_weights(0.23, 0.18)
s_curr_oos = stats(make_port(rd, CURR_W, cidx[oos_mask(cidx)]))
s_curr_ao  = stats(make_port(rd, CURR_W, cidx[ao_mask(cidx)]))
wf_curr    = run_wf(cidx, rd, CURR_W)
print(f"  Baseline (23%/18%/29%): OOS {s_curr_oos['sharpe']:.4f}, AltOOS {s_curr_ao['sharpe']:.4f}")

# ── Phase 1: H026 sweep (H041a=23%) ─────────────────────────────────────────
print("\n[1] Phase 1 — H026 sweep (H041a=23% fixed) …")
print(f"  {'H026':>7}  {'H045':>6}  {'Port OOS':>9}  {'Port AltOOS':>11}  {'Sum':>8}  {'MaxDD':>7}")
print("  "+"-"*62)

p1_results = []
for pct in range(10, 29):
    w = make_weights(0.23, pct/100)
    if w is None:
        continue
    p_oos = stats(make_port(rd, w, cidx[oos_mask(cidx)]))
    p_ao  = stats(make_port(rd, w, cidx[ao_mask(cidx)]))
    s_sum = p_oos["sharpe"] + p_ao["sharpe"]
    mark = " ←" if pct == 18 else ""
    print(f"  {pct:>6}%  {w['h045']*100:>5.0f}%  {p_oos['sharpe']:>9.4f}  "
          f"{p_ao['sharpe']:>11.4f}  {s_sum:>8.4f}  {p_oos['max_drawdown']*100:>6.2f}%{mark}")
    p1_results.append({
        "h041a": 0.23, "h026": pct/100, "h045": w["h045"],
        "oos": p_oos["sharpe"], "ao": p_ao["sharpe"], "sum": s_sum,
        "maxdd": p_oos["max_drawdown"], "cagr": p_oos["cagr"],
    })

p1_best = max(p1_results, key=lambda x: x["sum"])
print(f"\n  Phase 1 best: H026={p1_best['h026']*100:.0f}% "
      f"(OOS {p1_best['oos']:.4f}, AltOOS {p1_best['ao']:.4f})")

# ── Phase 2: H041a sweep (H026=best from P1) ────────────────────────────────
print(f"\n[2] Phase 2 — H041a sweep (H026={p1_best['h026']*100:.0f}% fixed) …")
print(f"  {'H041a':>7}  {'H045':>6}  {'Port OOS':>9}  {'Port AltOOS':>11}  {'Sum':>8}  {'MaxDD':>7}")
print("  "+"-"*62)

p2_results = []
for pct in range(16, 36):
    w = make_weights(pct/100, p1_best["h026"])
    if w is None:
        continue
    p_oos = stats(make_port(rd, w, cidx[oos_mask(cidx)]))
    p_ao  = stats(make_port(rd, w, cidx[ao_mask(cidx)]))
    s_sum = p_oos["sharpe"] + p_ao["sharpe"]
    mark = " ←" if pct == 23 else ""
    print(f"  {pct:>6}%  {w['h045']*100:>5.0f}%  {p_oos['sharpe']:>9.4f}  "
          f"{p_ao['sharpe']:>11.4f}  {s_sum:>8.4f}  {p_oos['max_drawdown']*100:>6.2f}%{mark}")
    p2_results.append({
        "h041a": pct/100, "h026": p1_best["h026"], "h045": w["h045"],
        "oos": p_oos["sharpe"], "ao": p_ao["sharpe"], "sum": s_sum,
        "maxdd": p_oos["max_drawdown"], "cagr": p_oos["cagr"],
    })

p2_best = max(p2_results, key=lambda x: x["sum"])
print(f"\n  Phase 2 best: H041a={p2_best['h041a']*100:.0f}% "
      f"(OOS {p2_best['oos']:.4f}, AltOOS {p2_best['ao']:.4f})")

# ── Phase 3: Joint verification ──────────────────────────────────────────────
print("\n[3] Phase 3 — Joint verification …")
new_w = make_weights(p2_best["h041a"], p2_best["h026"])
new_h041a_pct = round(p2_best["h041a"]*100)
new_h026_pct  = round(p2_best["h026"]*100)
new_h045_pct  = round(p2_best["h045"]*100)

s_is  = stats(make_port(rd, new_w, cidx[is_mask(cidx)]))
s_oos = stats(make_port(rd, new_w, cidx[oos_mask(cidx)]))
s_ai  = stats(make_port(rd, new_w, cidx[ai_mask(cidx)]))
s_ao  = stats(make_port(rd, new_w, cidx[ao_mask(cidx)]))
wf    = run_wf(cidx, rd, new_w)
ww    = min(wf) if wf else 0.0

c_is  = stats(make_port(rd, CURR_W, cidx[is_mask(cidx)]))
c_ai  = stats(make_port(rd, CURR_W, cidx[ai_mask(cidx)]))

print(f"\n  {'Portfolio':32}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'CAGR':>7}  {'MaxDD':>8}  {'WF':>7}")
print("  "+"-"*99)
for lbl, s_i, s_o, s_a, s_ao_, wf_ in [
    ("H102 (23%/18%/29%)", c_is, s_curr_oos, c_ai, s_curr_ao, wf_curr),
    (f"H103 ({new_h041a_pct}%/{new_h026_pct}%/{new_h045_pct}%)", s_is, s_oos, s_ai, s_ao, wf),
]:
    print(f"  {lbl:32}  {s_i['sharpe']:>7.4f}  {s_o['sharpe']:>7.4f}  "
          f"{s_a['sharpe']:>8.4f}  {s_ao_['sharpe']:>9.4f}  "
          f"{s_o['cagr']*100:>6.2f}%  {s_o['max_drawdown']*100:>7.2f}%  "
          f"{min(wf_):>7.3f} {'✓' if min(wf_)>=WF_WORST_MIN else '✗'}")

print(f"\n  Calendar year comparison …")
print(f"  {'Year':>5}  {'H102 (23%/18%/29%)':>19}  {'H103 best':>10}  {'Delta':>7}")
print("  "+"-"*58)
cal = []
neg_b = neg_n = 0
for yr in range(2004, 2026):
    yi = cidx[cidx.year == yr]
    if len(yi) == 0: continue
    rb = float((1+make_port(rd, CURR_W, yi)).prod()-1)
    rn = float((1+make_port(rd, new_w,  yi)).prod()-1)
    if rb < 0: neg_b += 1
    if rn < 0: neg_n += 1
    print(f"  {yr:>5}  {rb*100:>18.2f}%  {rn*100:>9.2f}%  {(rn-rb)*100:>+6.2f}pp")
    cal.append({"year":yr,"h102_weights":round(rb,4),"h103_weights":round(rn,4)})
print(f"  H102: {'ZERO' if neg_b==0 else neg_b} neg | H103: {'ZERO' if neg_n==0 else neg_n} neg")
print(f"\n  WF folds: {[round(f,3) for f in wf]} → min {ww:.3f}")

confirmed = (s_oos["sharpe"] > s_curr_oos["sharpe"] and
             s_ao["sharpe"]  > s_curr_ao["sharpe"]  and
             ww >= WF_WORST_MIN)

print(f"\n[4] Summary …")
print(f"  OOS:    {s_curr_oos['sharpe']:.4f} → {s_oos['sharpe']:.4f} (Δ={s_oos['sharpe']-s_curr_oos['sharpe']:+.4f})")
print(f"  AltOOS: {s_curr_ao['sharpe']:.4f} → {s_ao['sharpe']:.4f} (Δ={s_ao['sharpe']-s_curr_ao['sharpe']:+.4f})")
print(f"  MaxDD:  {s_curr_oos['max_drawdown']*100:.2f}% → {s_oos['max_drawdown']*100:.2f}%")
print(f"  WF:     {min(wf_curr):.3f} → {ww:.3f}")
print(f"  New weights: H041a {new_h041a_pct}% / H026 {new_h026_pct}% / H045 {new_h045_pct}%")
if confirmed:
    print(f"\n  *** H103 CONFIRMED — new weights {new_h041a_pct}%/{new_h026_pct}%/{new_h045_pct}% ***")
else:
    print(f"\n  H103 not confirmed — weights 23%/18%/29% unchanged.")

output = {
    "phase1": p1_results, "phase2": p2_results,
    "best_h026": p1_best["h026"], "best_h041a": p2_best["h041a"],
    "new_h041a": new_h041a_pct, "new_h026": new_h026_pct, "new_h045": new_h045_pct,
    "oos_new": s_oos["sharpe"], "ao_new": s_ao["sharpe"],
    "oos_base": s_curr_oos["sharpe"], "ao_base": s_curr_ao["sharpe"],
    "maxdd": s_oos["max_drawdown"], "cagr": s_oos["cagr"],
    "wf_folds": [round(f,3) for f in wf], "wf_worst": ww,
    "confirmed": bool(confirmed), "calendar": cal,
}
out_path = RESULT_DIR / "h103_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
