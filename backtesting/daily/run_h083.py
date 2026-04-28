"""
H083 — Concentration Sweep & H041a Geographic Expansion
========================================================

Purpose:
  H082 confirmed OOS 3.2018 with H041a top-1 and H045+BIL. Three follow-ons:

  Part A — H026 top-1:
    H041a improved from top-2 → top-1 (+0.093 OOS). Does the same apply to H026?
    H026 has 12 assets (11-sector SPDR + BIL), currently top-2 holding.
    Test top-1 (single strongest sector or cash).

  Part B — H045 top-N sweep:
    H045 now has 10 assets. H041a benefited from top-1 (more concentrated).
    Test top-1 on the bond rotation. Also test whether top-3 adds value.

  Part C — H041a geographic expansion:
    With top-1 picking one asset each month, universe breadth matters.
    Current: SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL/EWJ (9-asset).
    Test: EWZ (Brazil), VWO (broad EM, vs EEM), EWH (HK/China), EWU (UK), EWG (Germany).
    These give the top-1 signal more geographic diversity to pick from.

H082 baseline: OOS 3.2018, AltOOS 3.0777, MaxDD -2.05%, WF 2.106
H082 weights: H041a 20.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 2%
H041a: SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL/EWJ (9-asset, top-1)
H026:  11-sector+BIL (12-asset, top-2)
H045:  SHY/IEI/IEF/TLT/TIP/HYG/LQD/BKLN/EMB/BIL (10-asset, top-2)
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

H041A_9   = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ"]
H026_BIL2 = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC","BIL"]
H045_BIL  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL"]

# H041a geographic candidates
GEO_CANDS = {
    "+EWZ": H041A_9 + ["EWZ"],   # Brazil
    "+VWO": H041A_9 + ["VWO"],   # EM broad (vs EEM)
    "+EWH": H041A_9 + ["EWH"],   # HK/China
    "+EWU": H041A_9 + ["EWU"],   # UK
    "+EWG": H041A_9 + ["EWG"],   # Germany
}

PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079",
                   "h080","h081","h082"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h083_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h080","h081","h082"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h083_{ticker}_close_{start}_{end}.parquet"
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
print("H083 — Concentration Sweep & H041a Geographic Expansion")
print("="*80)

print("\n[0] Building H082 baseline components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h026_bil2  = build_rotation_monthly(H026_BIL2, FULL_START, FULL_END, 2)
h045_bil   = build_rotation_monthly(H045_BIL, FULL_START, FULL_END, 2)
h41_top1   = build_rotation_monthly(H041A_9, FULL_START, FULL_END, 1)

# H082 baseline
cidx_h082 = common_idx(h045_bil, h026_bil2, xlk_r, smh_r, igv_r, h41_top1)
r_h082    = {"h041a":h41_top1,"h026":h026_bil2,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
s_h082_oos = stats(make_port(r_h082, PROD_W, cidx_h082[oos_mask(cidx_h082)]))
s_h082_ao  = stats(make_port(r_h082, PROD_W, cidx_h082[ao_mask(cidx_h082)]))
print(f"\n  H082 baseline: OOS {s_h082_oos['sharpe']:.4f}, AltOOS {s_h082_ao['sharpe']:.4f}")

# ── Part A: H026 top-N sweep ──────────────────────────────────────────────────
print("\n[A] H026 concentration: top-1 and top-3 on 12-asset universe …")
print(f"\n  {'top-N':>6}  {'H026 OOS':>9}  {'H026 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*90)

h026_oos_base = stats(h026_bil2[oos_mask(h026_bil2.index)])["sharpe"]
h026_ao_base  = stats(h026_bil2[ao_mask(h026_bil2.index)])["sharpe"]
wf_base = min(run_wf(cidx_h082, r_h082, PROD_W))
print(f"  {'top-2':>6}  {h026_oos_base:>9.4f}  {h026_ao_base:>11.4f}  "
      f"{s_h082_oos['sharpe']:>9.4f}  {s_h082_ao['sharpe']:>11.4f}  "
      f"{s_h082_oos['max_drawdown']*100:>6.2f}%  {wf_base:>7.3f}  —")

part_a = {}
for n_top in [1, 3]:
    try:
        h26_v = build_rotation_monthly(H026_BIL2, FULL_START, FULL_END, n_top)
        cidx  = common_idx(h045_bil, h26_v, xlk_r, smh_r, igv_r, h41_top1)
        rd    = {"h041a":h41_top1,"h026":h26_v,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h26_oos = stats(h26_v[oos_mask(h26_v.index)])["sharpe"]
        h26_ao  = stats(h26_v[ao_mask(h26_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h082_oos["sharpe"] and s_ao["sharpe"] > s_h082_ao["sharpe"]
        print(f"  {'top-'+str(n_top):>6}  {h26_oos:>9.4f}  {h26_ao:>11.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        part_a[n_top] = {"h26_oos":h26_oos,"h26_ao":h26_ao,"port_oos":s_oos["sharpe"],
                         "port_ao":s_ao["sharpe"],"maxdd":s_oos["max_drawdown"],
                         "wf_worst":ww,"both_up":bool(both_up),"series":h26_v}
    except Exception as e:
        print(f"  top-{n_top}: ERROR {e}")

# ── Part B: H045 top-N sweep ──────────────────────────────────────────────────
print("\n[B] H045 concentration: top-1 and top-3 on 10-asset universe …")
print(f"\n  {'top-N':>6}  {'H045 OOS':>9}  {'H045 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*90)

h045_oos_base = stats(h045_bil[oos_mask(h045_bil.index)])["sharpe"]
h045_ao_base  = stats(h045_bil[ao_mask(h045_bil.index)])["sharpe"]
print(f"  {'top-2':>6}  {h045_oos_base:>9.4f}  {h045_ao_base:>11.4f}  "
      f"{s_h082_oos['sharpe']:>9.4f}  {s_h082_ao['sharpe']:>11.4f}  "
      f"{s_h082_oos['max_drawdown']*100:>6.2f}%  {wf_base:>7.3f}  —")

part_b = {}
for n_top in [1, 3]:
    try:
        h45_v = build_rotation_monthly(H045_BIL, FULL_START, FULL_END, n_top)
        cidx  = common_idx(h45_v, h026_bil2, xlk_r, smh_r, igv_r, h41_top1)
        rd    = {"h041a":h41_top1,"h026":h026_bil2,"h045":h45_v,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h45_oos = stats(h45_v[oos_mask(h45_v.index)])["sharpe"]
        h45_ao  = stats(h45_v[ao_mask(h45_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h082_oos["sharpe"] and s_ao["sharpe"] > s_h082_ao["sharpe"]
        print(f"  {'top-'+str(n_top):>6}  {h45_oos:>9.4f}  {h45_ao:>11.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        part_b[n_top] = {"h45_oos":h45_oos,"h45_ao":h45_ao,"port_oos":s_oos["sharpe"],
                         "port_ao":s_ao["sharpe"],"maxdd":s_oos["max_drawdown"],
                         "wf_worst":ww,"both_up":bool(both_up),"series":h45_v}
    except Exception as e:
        print(f"  top-{n_top}: ERROR {e}")

# ── Part C: H041a geographic expansion ───────────────────────────────────────
print("\n[C] H041a geographic expansion (top-1 on 10-asset) …")
print(f"\n  {'Candidate':12}  {'H041a OOS':>9}  {'H041a AltOOS':>12}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*95)

h41_oos_base = stats(h41_top1[oos_mask(h41_top1.index)])["sharpe"]
h41_ao_base  = stats(h41_top1[ao_mask(h41_top1.index)])["sharpe"]
print(f"  {'base(9-asset)':12}  {h41_oos_base:>9.4f}  {h41_ao_base:>12.4f}  "
      f"{s_h082_oos['sharpe']:>9.4f}  {s_h082_ao['sharpe']:>11.4f}  "
      f"{s_h082_oos['max_drawdown']*100:>6.2f}%  {wf_base:>7.3f}  —")

part_c = {}
for name, tickers in GEO_CANDS.items():
    try:
        h41_v = build_rotation_monthly(tickers, FULL_START, FULL_END, 1)
        cidx  = common_idx(h045_bil, h026_bil2, xlk_r, smh_r, igv_r, h41_v)
        rd    = {"h041a":h41_v,"h026":h026_bil2,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h41_oos = stats(h41_v[oos_mask(h41_v.index)])["sharpe"]
        h41_ao  = stats(h41_v[ao_mask(h41_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h082_oos["sharpe"] and s_ao["sharpe"] > s_h082_ao["sharpe"]
        print(f"  {name:12}  {h41_oos:>9.4f}  {h41_ao:>12.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        part_c[name] = {"h41_oos":h41_oos,"h41_ao":h41_ao,"port_oos":s_oos["sharpe"],
                        "port_ao":s_ao["sharpe"],"maxdd":s_oos["max_drawdown"],
                        "wf_worst":ww,"both_up":bool(both_up),"series":h41_v,"cidx":cidx,"rd":rd}
    except Exception as e:
        print(f"  {name:12}  ERROR: {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[D] Summary …")
print(f"\n  H082 baseline: OOS {s_h082_oos['sharpe']:.4f}, AltOOS {s_h082_ao['sharpe']:.4f}")

print("\n  Part A (H026 top-N):")
for k,v in part_a.items():
    d_oos = v["port_oos"]-s_h082_oos["sharpe"]; d_ao = v["port_ao"]-s_h082_ao["sharpe"]
    print(f"    top-{k}: OOS {v['port_oos']:.4f} ({d_oos:+.4f}), AltOOS {v['port_ao']:.4f} ({d_ao:+.4f}), Both↑: {v['both_up']}")

print("\n  Part B (H045 top-N):")
for k,v in part_b.items():
    d_oos = v["port_oos"]-s_h082_oos["sharpe"]; d_ao = v["port_ao"]-s_h082_ao["sharpe"]
    print(f"    top-{k}: OOS {v['port_oos']:.4f} ({d_oos:+.4f}), AltOOS {v['port_ao']:.4f} ({d_ao:+.4f}), Both↑: {v['both_up']}")

print("\n  Part C (H041a geo expansion — sorted by OOS):")
sorted_c = sorted(part_c.items(), key=lambda x: x[1]["port_oos"], reverse=True)
for name,v in sorted_c:
    d_oos = v["port_oos"]-s_h082_oos["sharpe"]; d_ao = v["port_ao"]-s_h082_ao["sharpe"]
    print(f"    {name}: OOS {v['port_oos']:.4f} ({d_oos:+.4f}), AltOOS {v['port_ao']:.4f} ({d_ao:+.4f}), Both↑: {v['both_up']}")

# Save
output = {
    "h082_baseline": {"oos":s_h082_oos["sharpe"],"alt_oos":s_h082_ao["sharpe"]},
    "part_a": {str(k):{"h26_oos":v["h26_oos"],"h26_ao":v["h26_ao"],
                        "port_oos":v["port_oos"],"port_ao":v["port_ao"],
                        "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":v["both_up"]}
               for k,v in part_a.items()},
    "part_b": {str(k):{"h45_oos":v["h45_oos"],"h45_ao":v["h45_ao"],
                        "port_oos":v["port_oos"],"port_ao":v["port_ao"],
                        "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":v["both_up"]}
               for k,v in part_b.items()},
    "part_c": {k:{"h41_oos":v["h41_oos"],"h41_ao":v["h41_ao"],
                  "port_oos":v["port_oos"],"port_ao":v["port_ao"],
                  "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":v["both_up"]}
               for k,v in part_c.items()},
}
out_path = RESULT_DIR / "h083_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
