"""
H500 — Skip-Month vs Unskipped Momentum on Actual Production H026/H041a Signals
================================================================================

Purpose:
  H492 (CONFIRMED) and H493 (CONFIRMED) found that unskipped 12-month (12-0)
  momentum robustly beats the traditional Jegadeesh-Titman skip-month (12-1)
  convention on the H198 30-stock and H417 60-stock toy universes, and both
  entries explicitly recommended checking "whether H041a's actual 19-asset
  universe and current lookback windows show the same 12-0 advantage" before
  touching production.

  Code inspection of run_h112.py (the current production rotation-scoring
  template) shows the momentum term is already:
      mom_12 = monthly_px / monthly_px.shift(12) - 1
  i.e. month-end price vs. price 12 months prior, with NO skip of the most
  recent month. Production H026/H041a already use 12-0, not 12-1.

  This hypothesis makes that empirical rather than a code-reading inference:
  it builds the actual H026 (23-asset) and H041a (19-asset) production
  universes/rank-ensemble scoring (rank(mom_12) + rank(inv_vol_6m), same as
  build_rotation_monthly in run_h112.py) and tests explicitly swapping in a
  12-1 skip-month variant on each leg, individually and combined, inside the
  full 6-component production blend (H041a/H026/H045/XLK-IBS/SMH-IBS/IGV-IBS,
  PROD_W weights). If skip-month improves the blended OOS/AltOOS Sharpe and
  clears the WF gate, that's a real, actionable production change. If not,
  it closes the H492/H493 recommendation with a definitive "no gap to close"
  answer instead of leaving it open indefinitely.

  Framework: IS 2008-2017, OOS 2018-2026, AltOOS 2013-2026, WF min=1.75.
  Reuses run_h112.py's caching, IBS, and stats helpers unmodified.
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

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

_PREFIXES = [f"h{i:03d}" for i in range(62, 113)] + ["h500"]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h500_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h500_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold=1, skip_month=False):
    """skip_month=False → production 12-0 (mom = P_t/P_{t-12}-1).
       skip_month=True  → traditional 12-1 (mom = P_{t-1}/P_{t-13}-1, skip most recent month)."""
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
    if skip_month:
        mom_12 = monthly_px.shift(1) / monthly_px.shift(13) - 1
    else:
        mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(13, len(monthly_px)):
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


print("="*80)
print("H500 — Skip-Month vs Unskipped Momentum on Actual Production H026/H041a")
print("="*80)

print("\n[0] Building fixed components (H045, IBS legs — unaffected by this test) …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h045  = build_rotation_monthly(H045_PROD, FULL_START, FULL_END, 2, skip_month=False)

print("\n[1] Building H026/H041a rotation legs, both windows …")
h026_120 = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1, skip_month=False)  # production
h026_121 = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1, skip_month=True)   # skip-month
h41_120  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1, skip_month=False)  # production
h41_121  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1, skip_month=True)   # skip-month

VARIANTS = {
    "A_baseline_both_12-0 (production)":      {"h026": h026_120, "h041a": h41_120},
    "B_H026_12-1_only":                        {"h026": h026_121, "h041a": h41_120},
    "C_H041a_12-1_only":                       {"h026": h026_120, "h041a": h41_121},
    "D_both_12-1":                             {"h026": h026_121, "h041a": h41_121},
}

print("\n[2] Blending into full production portfolio (PROD_W) …")
results = {}
base_oos = base_ao = base_wf = None
print(f"\n  {'Variant':>38}  {'OOS':>8}  {'AltOOS':>10}  {'MaxDD':>7}  {'WF':>7}  {'Beats base':>10}")
print("  "+"-"*95)
for label, legs in VARIANTS.items():
    rd = {"h041a": legs["h041a"], "h026": legs["h026"], "h045": h045,
          "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
    cidx = common_idx(*rd.values())
    s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
    s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, PROD_W)
    ww    = min(wf) if wf else 0.0
    if label.startswith("A_"):
        base_oos, base_ao, base_wf = s_oos["sharpe"], s_ao["sharpe"], ww
        beats = "—"
    else:
        beats_flag = (s_oos["sharpe"] > base_oos and s_ao["sharpe"] > base_ao and ww >= WF_WORST_MIN)
        beats = "✓" if beats_flag else "✗"
    print(f"  {label:>38}  {s_oos['sharpe']:>8.4f}  {s_ao['sharpe']:>10.4f}  "
          f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {beats:>10}")
    results[label] = {"oos_sharpe": s_oos["sharpe"], "altoos_sharpe": s_ao["sharpe"],
                       "oos_maxdd": s_oos["max_drawdown"], "wf_min": ww}

winners = [k for k,v in results.items() if not k.startswith("A_") and
           v["oos_sharpe"] > base_oos and v["altoos_sharpe"] > base_ao and v["wf_min"] >= WF_WORST_MIN]
confirmed = len(winners) > 0

print(f"\n[3] Summary …")
print(f"  Baseline (production, both legs 12-0): OOS {base_oos:.4f}, AltOOS {base_ao:.4f}, WF {base_wf:.3f}")
if confirmed:
    print(f"  *** H500 CONFIRMED — skip-month variant(s) beat production: {winners} ***")
else:
    print(f"  H500 NOT CONFIRMED — no skip-month variant beats current production (both-legs-12-0) baseline.")
    print(f"  Production H026/H041a already use unskipped (12-0) momentum via")
    print(f"  'mom_12 = monthly_px / monthly_px.shift(12) - 1' — the H492/H493")
    print(f"  recommendation is closed: there is no skip-month gap to fix.")

output = {"variants": results, "base_oos": base_oos, "base_ao": base_ao,
          "base_wf": base_wf, "confirmed": bool(confirmed), "winners": winners}
out_path = RESULT_DIR / "h500_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
