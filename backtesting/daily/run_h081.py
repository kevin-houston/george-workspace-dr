"""
H081 — Top-N Sweep, H045+BIL, & H026 Weight Sensitivity
=========================================================

Purpose:
  Three focused follow-ons after H080 confirmed production at OOS 2.9297:

  Part A — H041a top-N on 9-asset universe:
    H078 used top-2 on 8-asset. Now with 9 assets (added EWJ in H080),
    test top-1, top-2, top-3. Does a 3rd asset add value or dilute?

  Part B — H045 + BIL:
    The BIL insight worked for H041a (+0.114) and H026 (+0.081). H045's
    bond universe (SHY/IEI/IEF/TLT/TIP/HYG/LQD/BKLN/EMB) already has
    BKLN (near-zero duration) and SHY (1-3yr). BIL (T-bills, 0-3 months)
    would be the shortest possible duration option — may help in worst
    rate-shock months when even BKLN lags.

  Part C — H026 weight sensitivity:
    H026 standalone Sharpe jumped 2.109 after BIL+top-2 (was 1.518).
    Current portfolio weight is only 6.4%. Test 6.4% / 8% / 10% / 12%
    by taking from H041a (and/or H045) proportionally.

H080 baseline: OOS 2.9297, AltOOS 2.8928, MaxDD -2.79%, WF 2.417
H080 weights: H041a 20.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 2%
H041a universe: SPY/QQQ/TLT/GLD/IEF/EFA/EEM/BIL/EWJ (9-asset, top-2)
H026 universe:  11-sector+BIL (12-asset, top-2)
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

# H080 confirmed universes
H045_TICKERS    = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB"]
H045_BIL        = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL"]
H041A_9         = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL","EWJ"]
H026_BIL2       = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC","BIL"]

# Production weights (H080)
PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}
IBS_TOTAL = 0.30  # XLK+SMH+IGV fixed


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079","h080"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h081_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h071","h072","h073","h074","h075","h076","h077","h078","h079","h080"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h081_{ticker}_close_{start}_{end}.parquet"
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
print("H081 — Top-N Sweep, H045+BIL, & H026 Weight Sensitivity")
print("="*80)

print("\n[0] Building core components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))

print("    H026 BIL top-2 (H080 production) …")
h026_bil2 = build_rotation_monthly(H026_BIL2, FULL_START, FULL_END, 2)
print("    H041a 9-asset top-2 (H080 production) …")
h41_top2  = build_rotation_monthly(H041A_9, FULL_START, FULL_END, 2)
print("    H045 base (9-asset, top-2) …")
h045_base = build_rotation_monthly(H045_TICKERS, FULL_START, FULL_END, 2)
print("    H045 BIL+ (10-asset, top-2) …")
h045_bil  = build_rotation_monthly(H045_BIL, FULL_START, FULL_END, 2)

# H080 production baseline
cidx_h080 = common_idx(h045_base, h026_bil2, xlk_r, smh_r, igv_r, h41_top2)
r_h080    = {"h041a":h41_top2,"h026":h026_bil2,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
s_h080_oos = stats(make_port(r_h080, PROD_W, cidx_h080[oos_mask(cidx_h080)]))
s_h080_ao  = stats(make_port(r_h080, PROD_W, cidx_h080[ao_mask(cidx_h080)]))
print(f"\n  H080 baseline: OOS {s_h080_oos['sharpe']:.4f}, AltOOS {s_h080_ao['sharpe']:.4f}")

# ── Part A: H041a top-N sweep ─────────────────────────────────────────────────
print("\n[A] H041a top-N sweep (9-asset) …")
print(f"\n  {'top-N':>6}  {'H041a OOS':>9}  {'H041a AltOOS':>12}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*85)

h41_oos_base = stats(h41_top2[oos_mask(h41_top2.index)])["sharpe"]
h41_ao_base  = stats(h41_top2[ao_mask(h41_top2.index)])["sharpe"]
wf_base      = min(run_wf(cidx_h080, r_h080, PROD_W))
print(f"  {'top-2':>6}  {h41_oos_base:>9.4f}  {h41_ao_base:>12.4f}  "
      f"{s_h080_oos['sharpe']:>9.4f}  {s_h080_ao['sharpe']:>11.4f}  "
      f"{s_h080_oos['max_drawdown']*100:>6.2f}%  {wf_base:>7.3f}  —")

part_a_results = {}
for n_top in [1, 3, 4]:
    try:
        h41_v = build_rotation_monthly(H041A_9, FULL_START, FULL_END, n_top)
        cidx  = common_idx(h045_base, h026_bil2, xlk_r, smh_r, igv_r, h41_v)
        rd    = {"h041a":h41_v,"h026":h026_bil2,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h41_oos = stats(h41_v[oos_mask(h41_v.index)])["sharpe"]
        h41_ao  = stats(h41_v[ao_mask(h41_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h080_oos["sharpe"] and s_ao["sharpe"] > s_h080_ao["sharpe"]
        print(f"  {'top-'+str(n_top):>6}  {h41_oos:>9.4f}  {h41_ao:>12.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        part_a_results[n_top] = {"port_oos":s_oos["sharpe"],"port_ao":s_ao["sharpe"],
                                 "maxdd":s_oos["max_drawdown"],"wf_worst":ww,
                                 "both_up":bool(both_up),"series":h41_v,"cidx":cidx,"rd":rd}
    except Exception as e:
        print(f"  top-{n_top}: ERROR {e}")

# ── Part B: H045 + BIL ───────────────────────────────────────────────────────
print("\n[B] H045 + BIL (10-asset) …")
print(f"\n  {'Variant':16}  {'H045 OOS':>9}  {'H045 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*95)

h45_oos_base = stats(h045_base[oos_mask(h045_base.index)])["sharpe"]
h45_ao_base  = stats(h045_base[ao_mask(h045_base.index)])["sharpe"]
print(f"  {'H045 base(9)':16}  {h45_oos_base:>9.4f}  {h45_ao_base:>11.4f}  "
      f"{s_h080_oos['sharpe']:>9.4f}  {s_h080_ao['sharpe']:>11.4f}  "
      f"{s_h080_oos['max_drawdown']*100:>6.2f}%  {wf_base:>7.3f}  —")

for n_top in [2, 3]:
    try:
        cidx  = common_idx(h045_bil, h026_bil2, xlk_r, smh_r, igv_r, h41_top2)
        rd    = {"h041a":h41_top2,"h026":h026_bil2,"h045":h045_bil,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h45_oos = stats(h045_bil[oos_mask(h045_bil.index)])["sharpe"]
        h45_ao  = stats(h045_bil[ao_mask(h045_bil.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h080_oos["sharpe"] and s_ao["sharpe"] > s_h080_ao["sharpe"]
        label = f"H045+BIL top-{n_top}"
        print(f"  {label:16}  {h45_oos:>9.4f}  {h45_ao:>11.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        # only need to run once; store top-2 result
        if n_top == 2:
            part_b_result = {"h45_oos":h45_oos,"h45_ao":h45_ao,
                             "port_oos":s_oos["sharpe"],"port_ao":s_ao["sharpe"],
                             "maxdd":s_oos["max_drawdown"],"wf_worst":ww,
                             "both_up":bool(both_up),"series":h045_bil,"cidx":cidx,"rd":rd}
        break  # use top-2 only (same as H045 base)
    except Exception as e:
        print(f"  H045+BIL top-{n_top}: ERROR {e}")
        part_b_result = None

# ── Part C: H026 weight sensitivity ──────────────────────────────────────────
print("\n[C] H026 weight sensitivity (taking from H041a and H045 proportionally) …")
print(f"\n  {'H026 wt':>8}  {'H041a wt':>9}  {'H045 wt':>8}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}")
print("  "+"-"*80)

# Base: H041a=0.206, H026=0.064, H045=0.43, IBS=0.30
# Scale H026; reduce H041a and H045 proportionally (maintain their ratio)
h041a_base_w = 0.206
h026_base_w  = 0.064
h045_base_w  = 0.43
h041a_h045_ratio = h041a_base_w / h045_base_w  # ~0.479

weight_variants = {}
h026_weights = [0.040, 0.064, 0.080, 0.100, 0.120, 0.150]
for w26 in h026_weights:
    remaining = 0.70 - w26  # IBS fixed at 0.30, total=1.0
    # Distribute remaining between H041a and H045 maintaining original ratio
    w41 = round(remaining * h041a_h045_ratio / (1 + h041a_h045_ratio), 3)
    w45 = round(remaining - w41, 3)
    w   = {"h041a":w41,"h026":w26,"h045":w45,"XLK":0.20,"SMH":0.08,"IGV":0.02}
    try:
        s_oos = stats(make_port(r_h080, w, cidx_h080[oos_mask(cidx_h080)]))
        s_ao  = stats(make_port(r_h080, w, cidx_h080[ao_mask(cidx_h080)]))
        wf    = run_wf(cidx_h080, r_h080, w)
        ww    = min(wf) if wf else 0.0
        mark = "←" if abs(w26-0.064)<0.001 else ""
        print(f"  {w26:>7.1%}  {w41:>8.1%}  {w45:>7.1%}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {mark}")
        weight_variants[w26] = {"h041a":w41,"h026":w26,"h045":w45,
                                "oos":s_oos["sharpe"],"alt_oos":s_ao["sharpe"],
                                "maxdd":s_oos["max_drawdown"],"wf_worst":ww}
    except Exception as e:
        print(f"  {w26:.1%}: ERROR {e}")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n[D] Summary …")
print(f"\n  H080 baseline: OOS {s_h080_oos['sharpe']:.4f}, AltOOS {s_h080_ao['sharpe']:.4f}")

print("\n  Part A best (H041a top-N):")
best_a = max(part_a_results, key=lambda k: part_a_results[k]["port_oos"]) if part_a_results else None
if best_a:
    bav = part_a_results[best_a]
    print(f"    top-{best_a}: OOS {bav['port_oos']:.4f} (Δ{bav['port_oos']-s_h080_oos['sharpe']:+.4f}), "
          f"AltOOS {bav['port_ao']:.4f} (Δ{bav['port_ao']-s_h080_ao['sharpe']:+.4f}), "
          f"Both↑: {bav['both_up']}")

if 'part_b_result' in dir() and part_b_result:
    bv = part_b_result
    print(f"\n  Part B (H045+BIL): OOS {bv['port_oos']:.4f} (Δ{bv['port_oos']-s_h080_oos['sharpe']:+.4f}), "
          f"AltOOS {bv['port_ao']:.4f} (Δ{bv['port_ao']-s_h080_ao['sharpe']:+.4f}), "
          f"Both↑: {bv['both_up']}")

print("\n  Part C H026 weight (best by OOS):")
if weight_variants:
    best_wv = max(weight_variants, key=lambda k: weight_variants[k]["oos"])
    bwv = weight_variants[best_wv]
    print(f"    H026={best_wv:.1%}, H041a={bwv['h041a']:.1%}, H045={bwv['h045']:.1%}: "
          f"OOS {bwv['oos']:.4f} (Δ{bwv['oos']-s_h080_oos['sharpe']:+.4f}), "
          f"AltOOS {bwv['alt_oos']:.4f} (Δ{bwv['alt_oos']-s_h080_ao['sharpe']:+.4f})")

# Save
output = {
    "h080_baseline": {"oos":s_h080_oos["sharpe"],"alt_oos":s_h080_ao["sharpe"]},
    "part_a": {str(k):{"port_oos":v["port_oos"],"port_ao":v["port_ao"],
                        "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":v["both_up"]}
               for k,v in part_a_results.items()},
    "part_b": ({"h45_oos":part_b_result["h45_oos"],"h45_ao":part_b_result["h45_ao"],
                "port_oos":part_b_result["port_oos"],"port_ao":part_b_result["port_ao"],
                "both_up":part_b_result["both_up"]}
               if 'part_b_result' in dir() and part_b_result else None),
    "part_c": {str(k):v for k,v in weight_variants.items()},
}
out_path = RESULT_DIR / "h081_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
