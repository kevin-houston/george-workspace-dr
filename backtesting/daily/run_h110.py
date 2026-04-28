"""
H110 — H041a Top-N Sweep (19-asset Universe)
=============================================

Purpose:
  H041a uses top-1 from its 19-asset universe. H096 tested H026 top-N (failed).
  H106 tested H026 top-N on 18-asset (failed). H041a top-N has never been
  explicitly tested in the recent research phases.

  H041a 19-asset universe spans global equities, bonds, gold, cash, and
  international markets (Asia, Europe). Top-1 concentration might leave signal
  on the table — top-2 could capture both momentum in equities AND defensive
  rotation simultaneously.

  Also test H045 top-3 (now 13-asset with PCY) — was confirmed at top-2 but
  three bonds may improve the blend.

  Production weights (H109): H041a 22% / H026 27% / H045 21%
  Baseline: H109 (OOS 4.0724, AltOOS 3.9905, WF 3.024)
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

H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_FULL  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
              "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV"]
H045_PCY   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

_PREFIXES = [f"h{i:03d}" for i in range(62, 110)]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h110_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h110_{ticker}_close_{start}_{end}.parquet"
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
print("H110 — H041a Top-N Sweep + H045 Top-N (19-asset / 13-asset)")
print("="*80)

print("\n[0] Building fixed components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h026  = build_rotation_monthly(H026_FULL, FULL_START, FULL_END, 1)

print("\n[1] H041a top-N sweep …")
h41_top1 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h41_top2 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 2)
h41_top3 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 3)
h045     = build_rotation_monthly(H045_PCY,   FULL_START, FULL_END, 2)

h41_base_oos = h41_base_ao = h41_base_wf = None
h41_results = []

print(f"\n  {'Variant':12}  {'H41 IS':>7}  {'H41 OOS':>8}  {'H41 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*100)

for label, h41_r in [("top-1 (base)", h41_top1), ("top-2", h41_top2), ("top-3", h41_top3)]:
    rd = {"h041a":h41_r,"h026":h026,"h045":h045,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    cidx_v = common_idx(h41_r, h026, h045, xlk_r, smh_r, igv_r)
    w = PROD_W

    h41_is  = stats(h41_r[is_mask(h41_r.index)])
    h41_oos = stats(h41_r[oos_mask(h41_r.index)])
    h41_ao  = stats(h41_r[ao_mask(h41_r.index)])
    port_oos = stats(make_port(rd, w, cidx_v[oos_mask(cidx_v)]))
    port_ao  = stats(make_port(rd, w, cidx_v[ao_mask(cidx_v)]))
    wf       = run_wf(cidx_v, rd, w)
    ww       = min(wf) if wf else 0.0

    if h41_base_oos is None:
        h41_base_oos = port_oos["sharpe"]; h41_base_ao = port_ao["sharpe"]; h41_base_wf = ww
        both_up = True
    else:
        both_up = bool(port_oos["sharpe"] > h41_base_oos and
                      port_ao["sharpe"]  > h41_base_ao  and ww >= WF_WORST_MIN)

    mark = "✓" if both_up else "✗"
    print(f"  {label:12}  {h41_is['sharpe']:>7.4f}  {h41_oos['sharpe']:>8.4f}  "
          f"{h41_ao['sharpe']:>11.4f}  {port_oos['sharpe']:>9.4f}  "
          f"{port_ao['sharpe']:>11.4f}  {port_oos['max_drawdown']*100:>6.2f}%  "
          f"{ww:>7.3f}  {mark:>5}")

    h41_results.append({"label": label, "port_oos": port_oos["sharpe"],
                        "port_ao": port_ao["sharpe"], "maxdd": port_oos["max_drawdown"],
                        "wf": ww, "both_up": bool(both_up)})

h41_confirmed = any(r["both_up"] for r in h41_results[1:])
print(f"\n  H041a top-N: {'CONFIRMED — top-N improves over top-1' if h41_confirmed else 'top-1 is optimal'}")

print("\n[2] H045 top-3 sweep …")
h45_base_r  = build_rotation_monthly(H045_PCY, FULL_START, FULL_END, 2)
h45_top3_r  = build_rotation_monthly(H045_PCY, FULL_START, FULL_END, 3)

h45_results = []
h45_base_oos = h45_base_ao = h45_base_wf = None

print(f"\n  {'Variant':12}  {'H45 IS':>7}  {'H45 OOS':>8}  {'H45 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*100)

for label, h45_r in [("top-2 (base)", h45_base_r), ("top-3", h45_top3_r)]:
    h41 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
    rd = {"h041a":h41,"h026":h026,"h045":h45_r,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    cidx_v = common_idx(h41, h026, h45_r, xlk_r, smh_r, igv_r)
    w = PROD_W

    h45_is  = stats(h45_r[is_mask(h45_r.index)])
    h45_oos = stats(h45_r[oos_mask(h45_r.index)])
    h45_ao  = stats(h45_r[ao_mask(h45_r.index)])
    port_oos = stats(make_port(rd, w, cidx_v[oos_mask(cidx_v)]))
    port_ao  = stats(make_port(rd, w, cidx_v[ao_mask(cidx_v)]))
    wf       = run_wf(cidx_v, rd, w)
    ww       = min(wf) if wf else 0.0

    if h45_base_oos is None:
        h45_base_oos = port_oos["sharpe"]; h45_base_ao = port_ao["sharpe"]; h45_base_wf = ww
        both_up = True
    else:
        both_up = bool(port_oos["sharpe"] > h45_base_oos and
                      port_ao["sharpe"]  > h45_base_ao  and ww >= WF_WORST_MIN)

    mark = "✓" if both_up else "✗"
    print(f"  {label:12}  {h45_is['sharpe']:>7.4f}  {h45_oos['sharpe']:>8.4f}  "
          f"{h45_ao['sharpe']:>11.4f}  {port_oos['sharpe']:>9.4f}  "
          f"{port_ao['sharpe']:>11.4f}  {port_oos['max_drawdown']*100:>6.2f}%  "
          f"{ww:>7.3f}  {mark:>5}")

    h45_results.append({"label": label, "port_oos": port_oos["sharpe"],
                        "port_ao": port_ao["sharpe"], "maxdd": port_oos["max_drawdown"],
                        "wf": ww, "both_up": bool(both_up)})

h45_confirmed = any(r["both_up"] for r in h45_results[1:])
print(f"\n  H045 top-3: {'CONFIRMED — top-3 improves over top-2' if h45_confirmed else 'top-2 is optimal'}")

print("\n[3] Summary …")
confirmed = h41_confirmed or h45_confirmed
if h41_confirmed:
    bw = max([r for r in h41_results[1:] if r["both_up"]], key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"  H041a best: {bw['label']} OOS {bw['port_oos']:.4f}, AltOOS {bw['port_ao']:.4f}")
if h45_confirmed:
    bw = max([r for r in h45_results[1:] if r["both_up"]], key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"  H045 best:  {bw['label']} OOS {bw['port_oos']:.4f}, AltOOS {bw['port_ao']:.4f}")
if not confirmed:
    print(f"  H110 not confirmed — top-1/top-2 remain optimal.")

if h41_confirmed:
    print(f"\n  *** H110 CONFIRMED — H041a top-N improved ***")
elif h45_confirmed:
    print(f"\n  *** H110 CONFIRMED — H045 top-3 improved ***")
else:
    print(f"\n  H110 not confirmed.")

output = {
    "h041a_results": h41_results, "h045_results": h45_results,
    "h041a_confirmed": bool(h41_confirmed), "h045_confirmed": bool(h45_confirmed),
    "confirmed": bool(confirmed),
}
out_path = RESULT_DIR / "h110_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
