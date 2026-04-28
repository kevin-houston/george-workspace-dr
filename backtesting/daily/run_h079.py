"""
H079 — H041a Further Expansion & H026 Defensive Option
=======================================================

Purpose:
  H078 confirmed BIL (T-bill cash proxy) in H041a gives a massive dual-window
  improvement (OOS 2.6951→2.8094, AltOOS 2.7057→2.7844). Two natural follow-ons:

  Part A — H041a 9-asset sweep:
    H077 showed IWM added +0.026/+0.040 on the base-7 universe. Does IWM still
    help on top of BIL+? Also sweep DBC (commodities), EWJ (Japan), SHY (short-bond).

  Part B — H026 defensive option:
    H026 (11-sector SPDR, top-3) has no cash option. Adding BIL or SHY to the
    H026 universe may give sector rotation a genuine capital-preservation month
    in broad sell-offs — same mechanism that helped both H041a (BIL) and H045 (BKLN).
    Also test top-2 vs top-3 for H026 with BIL.

  Part C — Portfolio integration of winners (dual-window filter).

H078 production: H041a 20.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 2%
H078 baseline:   OOS 2.8094, AltOOS 2.7844, MaxDD -3.00%, WF worst 2.257

Periods:
  Full:   2003-01 → 2026-04
  IS:     2008-01 → 2017-12
  OOS:    2018-01 → 2026-04
  AltIS:  2003-01 → 2012-12
  AltOOS: 2013-01 → 2026-04
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

# H041a universe: base-8 (BIL+, confirmed in H078)
H041A_BIL  = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL"]
# Candidates to add on top of BIL+
H041A_CANDS = {
    "BIL+IWM":  ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL", "IWM"],
    "BIL+DBC":  ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL", "DBC"],
    "BIL+EWJ":  ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL", "EWJ"],
    "BIL+SHY":  ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM", "BIL", "SHY"],
}

# H026 universe variants
H026_BASE = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
H026_BIL  = H026_BASE + ["BIL"]
H026_SHY  = H026_BASE + ["SHY"]

# Production weights (H078)
PROD_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h079_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h071","h072","h073","h074","h075","h076","h077","h078"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h079_{ticker}_close_{start}_{end}.parquet"
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
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
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
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
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
print("H079 — H041a Further Expansion & H026 Defensive Option")
print("="*80)

print("\n[0] Building core components …")
h045_r = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
h026_r = build_rotation_monthly(H026_BASE, FULL_START, FULL_END, 3)
xlk_r  = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r  = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r  = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
print("    H041a BIL+ (8-asset, H078 baseline) …")
h41_bil = build_rotation_monthly(H041A_BIL, FULL_START, FULL_END, 2)

# H078 production baseline
cidx_h078 = common_idx(h045_r, h026_r, xlk_r, smh_r, igv_r, h41_bil)
r_h078 = {"h041a":h41_bil,"h026":h026_r,"h045":h045_r,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
s_h078_oos = stats(make_port(r_h078, PROD_W, cidx_h078[oos_mask(cidx_h078)]))
s_h078_ao  = stats(make_port(r_h078, PROD_W, cidx_h078[ao_mask(cidx_h078)]))

print(f"\n  H078 baseline: OOS {s_h078_oos['sharpe']:.4f}, AltOOS {s_h078_ao['sharpe']:.4f}")

# ────────────────────────────────────────────────────────────────────────────
print("\n[A] H041a 9-asset expansion candidates (on top of BIL+) …")
print(f"\n  {'Variant':12}  {'H041a OOS':>9}  {'H041a AltOOS':>12}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*90)

print(f"  {'BIL+ base':12}  {stats(h41_bil[oos_mask(h41_bil.index)])['sharpe']:>9.4f}  "
      f"{stats(h41_bil[ao_mask(h41_bil.index)])['sharpe']:>12.4f}  "
      f"{s_h078_oos['sharpe']:>9.4f}  {s_h078_ao['sharpe']:>11.4f}  "
      f"{s_h078_oos['max_drawdown']*100:>6.2f}%  "
      f"{min(run_wf(cidx_h078,r_h078,PROD_W)):>7.3f}  —")

part_a_results = {}
for name, tickers in H041A_CANDS.items():
    try:
        h41_cand = build_rotation_monthly(tickers, FULL_START, FULL_END, 2)
        cidx = common_idx(h045_r, h026_r, xlk_r, smh_r, igv_r, h41_cand)
        rd   = {"h041a":h41_cand,"h026":h026_r,"h045":h045_r,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf    = run_wf(cidx, rd, PROD_W)
        ww    = min(wf) if wf else 0.0
        h41_oos = stats(h41_cand[oos_mask(h41_cand.index)])["sharpe"]
        h41_ao  = stats(h41_cand[ao_mask(h41_cand.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h078_oos["sharpe"] and s_ao["sharpe"] > s_h078_ao["sharpe"]
        print(f"  {name:12}  {h41_oos:>9.4f}  {h41_ao:>12.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        part_a_results[name] = {"h41_oos":h41_oos,"h41_ao":h41_ao,
                                "port_oos":s_oos["sharpe"],"port_ao":s_ao["sharpe"],
                                "maxdd":s_oos["max_drawdown"],"wf_worst":ww,
                                "both_up":both_up,"series":h41_cand,"cidx":cidx,"rd":rd}
    except Exception as e:
        print(f"  {name:12}  ERROR: {e}")

# ────────────────────────────────────────────────────────────────────────────
print("\n[B] H026 variants — defensive option & top-N test …")
print(f"\n  {'Variant':18}  {'H026 OOS':>9}  {'H026 AltOOS':>11}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*100)

h026_base_oos = stats(h026_r[oos_mask(h026_r.index)])["sharpe"]
h026_base_ao  = stats(h026_r[ao_mask(h026_r.index)])["sharpe"]
print(f"  {'H026 base(top-3)':18}  {h026_base_oos:>9.4f}  {h026_base_ao:>11.4f}  "
      f"{s_h078_oos['sharpe']:>9.4f}  {s_h078_ao['sharpe']:>11.4f}  "
      f"{s_h078_oos['max_drawdown']*100:>6.2f}%  "
      f"{min(run_wf(cidx_h078,r_h078,PROD_W)):>7.3f}  —")

h026_variants = {}
for label, tickers, n_top in [
    ("H026+BIL top-3", H026_BIL,  3),
    ("H026+BIL top-2", H026_BIL,  2),
    ("H026+SHY top-3", H026_SHY,  3),
    ("H026 top-2",     H026_BASE, 2),
    ("H026 top-4",     H026_BASE, 4),
]:
    try:
        h026_v = build_rotation_monthly(tickers, FULL_START, FULL_END, n_top)
        cidx   = common_idx(h045_r, h026_v, xlk_r, smh_r, igv_r, h41_bil)
        rd     = {"h041a":h41_bil,"h026":h026_v,"h045":h045_r,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_oos  = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        s_ao   = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf     = run_wf(cidx, rd, PROD_W)
        ww     = min(wf) if wf else 0.0
        h26_oos = stats(h026_v[oos_mask(h026_v.index)])["sharpe"]
        h26_ao  = stats(h026_v[ao_mask(h026_v.index)])["sharpe"]
        both_up = s_oos["sharpe"] > s_h078_oos["sharpe"] and s_ao["sharpe"] > s_h078_ao["sharpe"]
        print(f"  {label:18}  {h26_oos:>9.4f}  {h26_ao:>11.4f}  "
              f"{s_oos['sharpe']:>9.4f}  {s_ao['sharpe']:>11.4f}  "
              f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {'✓' if both_up else '✗'}")
        h026_variants[label] = {"h26_oos":h26_oos,"h26_ao":h26_ao,
                                "port_oos":s_oos["sharpe"],"port_ao":s_ao["sharpe"],
                                "maxdd":s_oos["max_drawdown"],"wf_worst":ww,
                                "both_up":both_up,"series":h026_v,"cidx":cidx,"rd":rd}
    except Exception as e:
        print(f"  {label:18}  ERROR: {e}")

# ────────────────────────────────────────────────────────────────────────────
print("\n[C] Best combinations — dual-window confirmed variants …")

# Collect confirmed Part A winners
a_winners = {k:v for k,v in part_a_results.items() if v["both_up"] and v["wf_worst"] >= WF_WORST_MIN}
b_winners = {k:v for k,v in h026_variants.items() if v["both_up"] and v["wf_worst"] >= WF_WORST_MIN}

if a_winners:
    print(f"\n  Part A dual-window winners: {list(a_winners.keys())}")
    # Best Part A winner × best Part B winner (if any)
    best_a = max(a_winners, key=lambda k: a_winners[k]["port_oos"])
    av = a_winners[best_a]
    print(f"  Best A: {best_a} → Port OOS {av['port_oos']:.4f}, AltOOS {av['port_ao']:.4f}")
else:
    print("  No Part A candidates improved both windows.")

if b_winners:
    print(f"\n  Part B dual-window winners: {list(b_winners.keys())}")
    best_b = max(b_winners, key=lambda k: b_winners[k]["port_oos"])
    bv = b_winners[best_b]
    print(f"  Best B: {best_b} → Port OOS {bv['port_oos']:.4f}, AltOOS {bv['port_ao']:.4f}")
else:
    print("  No Part B candidates improved both windows.")

# If both parts have winners, test combining best-A H041a × best-B H026
if a_winners and b_winners:
    print(f"\n  Testing combination: {best_a} H041a × {best_b} H026 …")
    best_a_series = av["series"]
    best_b_series = bv["series"]
    cidx_combo = common_idx(h045_r, best_a_series, xlk_r, smh_r, igv_r, best_b_series)
    rd_combo   = {"h041a":best_a_series,"h026":best_b_series,"h045":h045_r,
                  "XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    s_oos_c  = stats(make_port(rd_combo, PROD_W, cidx_combo[oos_mask(cidx_combo)]))
    s_ao_c   = stats(make_port(rd_combo, PROD_W, cidx_combo[ao_mask(cidx_combo)]))
    wf_c     = run_wf(cidx_combo, rd_combo, PROD_W)
    ww_c     = min(wf_c) if wf_c else 0.0
    print(f"  Combo OOS {s_oos_c['sharpe']:.4f} (Δ{s_oos_c['sharpe']-s_h078_oos['sharpe']:+.4f}), "
          f"AltOOS {s_ao_c['sharpe']:.4f} (Δ{s_ao_c['sharpe']-s_h078_ao['sharpe']:+.4f}), "
          f"MaxDD {s_oos_c['max_drawdown']*100:.2f}%, WF {ww_c:.3f} {'✓' if ww_c>=WF_WORST_MIN else '✗'}")

# ────────────────────────────────────────────────────────────────────────────
print("\n[D] Summary …")
print(f"\n  H078 baseline: OOS {s_h078_oos['sharpe']:.4f}, AltOOS {s_h078_ao['sharpe']:.4f}")

print("\n  All variants vs baseline (sorted by OOS):")
all_variants = {}
all_variants["H078 base"] = {"port_oos":s_h078_oos["sharpe"],"port_ao":s_h078_ao["sharpe"],"both_up":False}
for k,v in part_a_results.items():
    all_variants[k] = v
for k,v in h026_variants.items():
    all_variants[k] = v

print(f"  {'Variant':22}  {'OOS':>8}  {'AltOOS':>8}  {'Δ OOS':>7}  {'Δ AltOOS':>9}  {'Both↑':>5}")
print("  "+"-"*75)
for k,v in sorted(all_variants.items(), key=lambda x: x[1]["port_oos"], reverse=True):
    d_oos = v["port_oos"] - s_h078_oos["sharpe"]
    d_ao  = v["port_ao"] - s_h078_ao["sharpe"]
    print(f"  {k:22}  {v['port_oos']:>8.4f}  {v['port_ao']:>8.4f}  "
          f"{d_oos:>+7.4f}  {d_ao:>+9.4f}  {'✓' if v.get('both_up') else ''}")

# Save results
output = {
    "h078_baseline": {"oos":s_h078_oos["sharpe"],"alt_oos":s_h078_ao["sharpe"]},
    "part_a": {k:{"h41_oos":v["h41_oos"],"h41_ao":v["h41_ao"],
                  "port_oos":v["port_oos"],"port_ao":v["port_ao"],
                  "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":bool(v["both_up"])}
               for k,v in part_a_results.items()},
    "part_b": {k:{"h26_oos":v["h26_oos"],"h26_ao":v["h26_ao"],
                  "port_oos":v["port_oos"],"port_ao":v["port_ao"],
                  "maxdd":v["maxdd"],"wf_worst":v["wf_worst"],"both_up":bool(v["both_up"])}
               for k,v in h026_variants.items()},
}
out_path = RESULT_DIR / "h079_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
