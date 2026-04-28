"""
H112 — H026 Expansion: IBB, XME, USO; H041a Expansion: EWZ
============================================================

Purpose:
  Part A — H026 further expansion (23-asset baseline):
  - IBB  (iShares Biotechnology, Feb 2001): pharma/biotech momentum cycle,
           distinct from XLV (broad healthcare). Biotech has high idiosyncratic
           momentum — can rank very high or very low on 12m momentum.
  - XME  (SPDR S&P Metals & Mining, Jun 2006): equity play on metals mining
           companies. Different from physical metals (GLD/SLV) and broad DBC —
           has equity beta plus commodity leverage.
  - USO  (United States Oil Fund, Apr 2006): pure crude oil vs UNG (natural gas).
           Despite DBC including energy, USO can be the top-scoring asset during
           oil bull runs, providing a purer oil signal.

  Part B — H041a expansion (19-asset baseline):
  - EWZ  (iShares MSCI Brazil, Jul 2000): just confirmed for H026, testing if
           it also improves H041a. H041a uses global equity momentum — EWZ would
           compete with SPY/QQQ/EFA/EEM/country ETFs. Previous tests combined
           EWZ with EWW (Mexico) and the combo failed; standalone never retested.

  H026 baseline (23-asset), H041a baseline (19-asset)
  Baseline: H111 (OOS 4.0940, AltOOS 4.0196, WF 3.024)
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

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

H026_CANDIDATES = [
    ("+IBB",          ["IBB"]),
    ("+XME",          ["XME"]),
    ("+USO",          ["USO"]),
    ("+IBB+XME",      ["IBB","XME"]),
    ("+IBB+USO",      ["IBB","USO"]),
    ("+XME+USO",      ["XME","USO"]),
    ("+IBB+XME+USO",  ["IBB","XME","USO"]),
]

H041A_CANDIDATES = [
    ("+EWZ",          ["EWZ"]),
    ("+EWC",          ["EWC"]),
    ("+EWZ+EWC",      ["EWZ","EWC"]),
]

_PREFIXES = [f"h{i:03d}" for i in range(62, 112)]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h112_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h112_{ticker}_close_{start}_{end}.parquet"
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


def sweep_component(base_universe, candidates, fixed_n_hold, other_r_dict_builder,
                    base_oos, base_ao, base_wf, section_name):
    """Generic sweep: test adding extras to base_universe, return winners."""
    results = []
    print(f"\n  {'Candidate':>16}  {'IS':>7}  {'OOS':>8}  {'AltOOS':>10}  "
          f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
    print("  "+"-"*100)

    for label, extras in candidates:
        universe = base_universe + extras
        comp_r = build_rotation_monthly(universe, FULL_START, FULL_END, fixed_n_hold)
        rd_c = other_r_dict_builder(comp_r)
        cidx_c = common_idx(*[v for v in rd_c.values() if isinstance(v, pd.Series)])
        port_oos = stats(make_port(rd_c, PROD_W, cidx_c[oos_mask(cidx_c)]))
        port_ao  = stats(make_port(rd_c, PROD_W, cidx_c[ao_mask(cidx_c)]))
        wf       = run_wf(cidx_c, rd_c, PROD_W)
        ww       = min(wf) if wf else 0.0
        comp_is  = stats(comp_r[is_mask(comp_r.index)])
        comp_oos = stats(comp_r[oos_mask(comp_r.index)])
        comp_ao  = stats(comp_r[ao_mask(comp_r.index)])

        both_up = bool(port_oos["sharpe"] > base_oos and
                       port_ao["sharpe"]  > base_ao  and ww >= WF_WORST_MIN)
        mark = "✓" if both_up else "✗"
        print(f"  {label:>16}  {comp_is['sharpe']:>7.4f}  {comp_oos['sharpe']:>8.4f}  "
              f"{comp_ao['sharpe']:>10.4f}  {port_oos['sharpe']:>9.4f}  "
              f"{port_ao['sharpe']:>11.4f}  {port_oos['max_drawdown']*100:>6.2f}%  "
              f"{ww:>7.3f}  {mark:>5}")
        results.append({"label": label, "extras": extras, "port_oos": port_oos["sharpe"],
                        "port_ao": port_ao["sharpe"], "maxdd": port_oos["max_drawdown"],
                        "wf": ww, "both_up": bool(both_up)})

    winners = [r for r in results if r["both_up"]]
    print(f"\n  {section_name} winners: {[r['label'] for r in winners] if winners else 'None'}")
    return results, winners


# ── main ─────────────────────────────────────────────────────────────────────

print("="*80)
print("H112 — H026 Expansion: IBB/XME/USO; H041a Expansion: EWZ/EWC")
print("="*80)

print("\n[0] Building fixed components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h41_base  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h026_base = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1)
h045      = build_rotation_monthly(H045_PROD,  FULL_START, FULL_END, 2)

cidx_base   = common_idx(h41_base, h026_base, h045, xlk_r, smh_r, igv_r)
rd_base     = {"h041a":h41_base,"h026":h026_base,"h045":h045,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
s_base_oos  = stats(make_port(rd_base, PROD_W, cidx_base[oos_mask(cidx_base)]))
s_base_ao   = stats(make_port(rd_base, PROD_W, cidx_base[ao_mask(cidx_base)]))
wf_base     = run_wf(cidx_base, rd_base, PROD_W)
print(f"  Baseline: OOS {s_base_oos['sharpe']:.4f}, AltOOS {s_base_ao['sharpe']:.4f}, WF {min(wf_base):.3f}")

# ── Part A: H026 expansion ───────────────────────────────────────────────────
print("\n[1] Part A — H026 expansion (IBB, XME, USO on 23-asset baseline) …")

def make_h026_rd(h026_r):
    return {"h041a":h41_base,"h026":h026_r,"h045":h045,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

h026_results, h026_winners = sweep_component(
    H026_BASE, H026_CANDIDATES, 1, make_h026_rd,
    s_base_oos["sharpe"], s_base_ao["sharpe"], min(wf_base), "H026"
)

# ── Part B: H041a expansion ──────────────────────────────────────────────────
print("\n[2] Part B — H041a expansion (EWZ, EWC on 19-asset baseline) …")

def make_h041a_rd(h41_r):
    return {"h041a":h41_r,"h026":h026_base,"h045":h045,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}

h41_results, h41_winners = sweep_component(
    H041A_FULL, H041A_CANDIDATES, 1, make_h041a_rd,
    s_base_oos["sharpe"], s_base_ao["sharpe"], min(wf_base), "H041a"
)

# ── Summary ──────────────────────────────────────────────────────────────────
all_winners = h026_winners + h41_winners
confirmed = len(all_winners) > 0

print(f"\n[3] Summary …")
print(f"  Baseline: OOS {s_base_oos['sharpe']:.4f}, AltOOS {s_base_ao['sharpe']:.4f}")

if h026_winners:
    bw = max(h026_winners, key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"  H026 best: {bw['label']} OOS {bw['port_oos']:.4f} (+{bw['port_oos']-s_base_oos['sharpe']:+.4f}), "
          f"AltOOS {bw['port_ao']:.4f} (+{bw['port_ao']-s_base_ao['sharpe']:+.4f})")
    print(f"\n  *** H112 CONFIRMED — H026 expanded with {bw['label']} ***")
elif h41_winners:
    bw = max(h41_winners, key=lambda x: x["port_oos"] + x["port_ao"])
    print(f"  H041a best: {bw['label']} OOS {bw['port_oos']:.4f}, AltOOS {bw['port_ao']:.4f}")
    print(f"\n  *** H112 CONFIRMED — H041a expanded with {bw['label']} ***")
else:
    print(f"  H112 not confirmed.")

output = {
    "h026_candidates": h026_results, "h41_candidates": h41_results,
    "confirmed": bool(confirmed),
    "base_oos": s_base_oos["sharpe"], "base_ao": s_base_ao["sharpe"],
}
out_path = RESULT_DIR / "h112_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
