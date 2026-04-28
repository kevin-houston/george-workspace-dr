"""
H109 — H045 Universe Expansion: VCSH, BIV, PCY, ANGL, VCLT, SRLN
==================================================================

Purpose:
  H045 (12-asset bond rotation, top-2) has been at 21% weight since H045 was
  confirmed. The universe covers: short/intermediate/long Treasuries (SHY/IEI/
  IEF/TLT), inflation (TIP), high yield (HYG), investment grade (LQD), bank
  loans (BKLN), EM bonds (EMB), cash (BIL), MBS (MBB), floating rate (FLOT).

  Missing segments:
  - VCSH  (Vanguard Short-Term Corporate Bond, Dec 2009): short IG corporates
  - BIV   (Vanguard Intermediate-Term Bond, Jan 2009): blended intermediate
  - PCY   (Invesco EM Sovereign Debt, Oct 2007): EM sovereign vs corporate
  - ANGL  (VanEck Fallen Angel HY, Apr 2012): fallen angels outperform HY index
  - VCLT  (Vanguard Long-Term Corporate, Dec 2009): long IG corporates vs TLT
  - SRLN  (SPDR Blackstone Senior Loan, Apr 2013): secured senior loans

  Strategy: test singletons, then pairs of winners.

  H045_PROD (12-asset): SHY/IEI/IEF/TLT/TIP/HYG/LQD/BKLN/EMB/BIL/MBB/FLOT
  Production weights (H107): H041a 22% / H026 27% / H045 21%
  Baseline: H108/H107 (OOS 4.0717, AltOOS 3.9901, WF 3.020)
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
H045_BASE  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

CANDIDATES = [
    ("+VCSH",          ["VCSH"]),
    ("+BIV",           ["BIV"]),
    ("+PCY",           ["PCY"]),
    ("+ANGL",          ["ANGL"]),
    ("+VCLT",          ["VCLT"]),
    ("+SRLN",          ["SRLN"]),
    ("+VCSH+BIV",      ["VCSH","BIV"]),
    ("+VCSH+PCY",      ["VCSH","PCY"]),
    ("+VCSH+VCLT",     ["VCSH","VCLT"]),
    ("+BIV+PCY",       ["BIV","PCY"]),
    ("+BIV+VCLT",      ["BIV","VCLT"]),
    ("+PCY+ANGL",      ["PCY","ANGL"]),
    ("+VCSH+BIV+PCY",  ["VCSH","BIV","PCY"]),
    ("+VCSH+BIV+VCLT", ["VCSH","BIV","VCLT"]),
]

_PREFIXES = [f"h{i:03d}" for i in range(62, 109)]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h109_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h109_{ticker}_close_{start}_{end}.parquet"
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
print("H109 — H045 Universe Expansion: VCSH, BIV, PCY, ANGL, VCLT, SRLN")
print("="*80)

print("\n[0] Building fixed components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h41   = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_FULL,  FULL_START, FULL_END, 1)

print("\n[1] Building H045 baseline (12-asset, top-2) …")
h045_base = build_rotation_monthly(H045_BASE, FULL_START, FULL_END, 2)
cidx_base = common_idx(h41, h026, h045_base, xlk_r, smh_r, igv_r)
rd_base   = {"h041a":h41,"h026":h026,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
s_base_oos = stats(make_port(rd_base, PROD_W, cidx_base[oos_mask(cidx_base)]))
s_base_ao  = stats(make_port(rd_base, PROD_W, cidx_base[ao_mask(cidx_base)]))
wf_base    = run_wf(cidx_base, rd_base, PROD_W)
print(f"  Baseline: OOS {s_base_oos['sharpe']:.4f}, AltOOS {s_base_ao['sharpe']:.4f}, "
      f"WF {min(wf_base):.3f}")

print("\n[2] H045 candidate sweep …")
header = (f"  {'Candidate':>18}  {'H045 IS':>8}  {'H045 OOS':>9}  {'H045 AltOOS':>12}  "
          f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print(header)
print("  "+"-"*110)

sweep_results = []
for label, extras in CANDIDATES:
    universe = H045_BASE + extras
    h045_c = build_rotation_monthly(universe, FULL_START, FULL_END, 2)
    cidx_c = common_idx(h41, h026, h045_c, xlk_r, smh_r, igv_r)
    rd_c   = {"h041a":h41,"h026":h026,"h045":h045_c,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

    h045_is  = stats(h045_c[is_mask(h045_c.index)])
    h045_oos = stats(h045_c[oos_mask(h045_c.index)])
    h045_ao  = stats(h045_c[ao_mask(h045_c.index)])
    port_oos = stats(make_port(rd_c, PROD_W, cidx_c[oos_mask(cidx_c)]))
    port_ao  = stats(make_port(rd_c, PROD_W, cidx_c[ao_mask(cidx_c)]))
    wf       = run_wf(cidx_c, rd_c, PROD_W)
    ww       = min(wf) if wf else 0.0

    both_up = bool(port_oos["sharpe"] > s_base_oos["sharpe"] and
                   port_ao["sharpe"]  > s_base_ao["sharpe"]  and
                   ww >= WF_WORST_MIN)
    mark = "✓" if both_up else "✗"

    print(f"  {label:>18}  {h045_is['sharpe']:>8.4f}  {h045_oos['sharpe']:>9.4f}  "
          f"{h045_ao['sharpe']:>12.4f}  {port_oos['sharpe']:>9.4f}  "
          f"{port_ao['sharpe']:>11.4f}  {port_oos['max_drawdown']*100:>6.2f}%  "
          f"{ww:>7.3f}  {mark:>5}")

    sweep_results.append({
        "label": label, "extras": extras,
        "h045_is": h045_is["sharpe"], "h045_oos": h045_oos["sharpe"],
        "h045_ao": h045_ao["sharpe"],
        "port_oos": port_oos["sharpe"], "port_ao": port_ao["sharpe"],
        "maxdd": port_oos["max_drawdown"], "wf": ww,
        "both_up": bool(both_up),
    })

winners = [r for r in sweep_results if r["both_up"]]
print(f"\n[3] Winners: {[r['label'] for r in winners] if winners else 'None'}")

confirmed = len(winners) > 0
if confirmed:
    best = max(winners, key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"\n  Best winner: {best['label']} "
          f"(OOS {best['port_oos']:.4f}, AltOOS {best['port_ao']:.4f}, sum {best['port_oos']+best['port_ao']:.4f})")

    print(f"\n  Full verification …")
    universe_best = H045_BASE + best["extras"]
    h045_best = build_rotation_monthly(universe_best, FULL_START, FULL_END, 2)
    cidx_best = common_idx(h41, h026, h045_best, xlk_r, smh_r, igv_r)
    rd_best   = {"h041a":h41,"h026":h026,"h045":h045_best,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

    s_is  = stats(make_port(rd_best, PROD_W, cidx_best[is_mask(cidx_best)]))
    s_oos = stats(make_port(rd_best, PROD_W, cidx_best[oos_mask(cidx_best)]))
    s_ai  = stats(make_port(rd_best, PROD_W, cidx_best[ai_mask(cidx_best)]))
    s_ao  = stats(make_port(rd_best, PROD_W, cidx_best[ao_mask(cidx_best)]))
    wf_b  = run_wf(cidx_best, rd_best, PROD_W)
    ww_b  = min(wf_b) if wf_b else 0.0
    c_is  = stats(make_port(rd_base, PROD_W, cidx_base[is_mask(cidx_base)]))
    c_ai  = stats(make_port(rd_base, PROD_W, cidx_base[ai_mask(cidx_base)]))

    print(f"\n  {'Portfolio':36}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
          f"{'AltOOS S':>9}  {'CAGR':>7}  {'MaxDD':>8}  {'WF':>7}")
    print("  "+"-"*103)
    for lbl, s_i, s_o, s_a, s_ao_, wf_ in [
        ("H107/H108 baseline (12-asset)", c_is, s_base_oos, c_ai, s_base_ao, wf_base),
        (f"H109 {best['label']}", s_is, s_oos, s_ai, s_ao, wf_b),
    ]:
        print(f"  {lbl:36}  {s_i['sharpe']:>7.4f}  {s_o['sharpe']:>7.4f}  "
              f"{s_a['sharpe']:>8.4f}  {s_ao_['sharpe']:>9.4f}  "
              f"{s_o['cagr']*100:>6.2f}%  {s_o['max_drawdown']*100:>7.2f}%  "
              f"{min(wf_):>7.3f} {'✓' if min(wf_)>=WF_WORST_MIN else '✗'}")
    print(f"\n  WF folds: {[round(f,3) for f in wf_b]} → min {ww_b:.3f}")
    print(f"\n  *** H109 CONFIRMED — H045 expanded with {best['label']} ***")

print(f"\n[4] Summary …")
print(f"  OOS baseline:    {s_base_oos['sharpe']:.4f}")
print(f"  AltOOS baseline: {s_base_ao['sharpe']:.4f}")
if confirmed:
    bw = max(winners, key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"  OOS best:    {bw['port_oos']:.4f} (Δ={bw['port_oos']-s_base_oos['sharpe']:+.4f})")
    print(f"  AltOOS best: {bw['port_ao']:.4f} (Δ={bw['port_ao']-s_base_ao['sharpe']:+.4f})")

output = {
    "candidates": sweep_results,
    "confirmed": bool(confirmed),
    "base_oos": s_base_oos["sharpe"], "base_ao": s_base_ao["sharpe"],
}
out_path = RESULT_DIR / "h109_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
