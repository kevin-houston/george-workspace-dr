"""
H091 — H045 Universe Expansion: MUB, BWX, IGIB
===============================================

Purpose:
  H045 (bond rotation) after H090: SHY/IEI/IEF/TLT/TIP/HYG/LQD/BKLN/EMB/BIL/MBB/FLOT
  (12-asset, top-2)

  Three potential additions with distinct return cycles:
  - MUB: iShares National Muni Bond ETF (tax-exempt, ~6yr duration; driven by
    state/local credit and AMT cycle — low correlation to corporate credit)
  - BWX: SPDR Bloomberg Barclays International Treasury Bond ETF (non-USD sovereign
    debt, ~8yr duration; exposes portfolio to EUR/JPY/GBP duration cycles that are
    out-of-phase with US rates)
  - IGIB: iShares Intermediate-Term Corporate Bond ETF (5-10yr IG corp; fills
    duration/credit gap between FLOT <1yr and LQD 15yr+)

  Sweep: each singly, pairs, all three.
  H090 baseline: OOS 3.5171, AltOOS 3.4382, MaxDD -2.26%, WF 2.444
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
# H045 after H090 confirmation
H045_BASE  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT"]

H045_CANDIDATES = {
    "base":           H045_BASE,
    "+MUB":           H045_BASE + ["MUB"],
    "+BWX":           H045_BASE + ["BWX"],
    "+IGIB":          H045_BASE + ["IGIB"],
    "+MUB+BWX":       H045_BASE + ["MUB","BWX"],
    "+MUB+IGIB":      H045_BASE + ["MUB","IGIB"],
    "+BWX+IGIB":      H045_BASE + ["BWX","IGIB"],
    "+MUB+BWX+IGIB":  H045_BASE + ["MUB","BWX","IGIB"],
}

PROD_W = {"h041a": 0.23, "h026": 0.07, "h045": 0.40,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062","h063","h064","h065","h066","h067","h068","h069","h070",
                   "h071","h072","h073","h074","h075","h076","h077","h078","h079",
                   "h080","h081","h082","h083","h084","h085","h086","h087","h088",
                   "h089","h090"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h091_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h080","h081","h082","h083","h084","h085","h086","h087","h088",
                "h089","h090"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h091_{ticker}_close_{start}_{end}.parquet"
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
print("H091 — H045 Universe Expansion: MUB, BWX, IGIB")
print("="*80)

print("\n[0] Building fixed components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
h41   = build_rotation_monthly(H041A_EPHE, FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_BIL,   FULL_START, FULL_END, 1)

# ── [1] H045 candidate sweep ──────────────────────────────────────────────────
print("\n[1] H045 universe candidate sweep …")
print(f"\n  {'Candidate':18}  {'H045 IS':>8}  {'H045 OOS':>9}  {'H045 AltOOS':>12}  "
      f"{'Port OOS':>9}  {'Port AltOOS':>11}  {'MaxDD':>7}  {'WF':>7}  {'Both↑':>5}")
print("  "+"-"*107)

results = {}
base_port_oos = base_port_ao = None

for name, tickers in H045_CANDIDATES.items():
    try:
        h045_v = build_rotation_monthly(tickers, FULL_START, FULL_END, 2)
        cidx   = common_idx(h045_v, h026, xlk_r, smh_r, igv_r, h41)
        rd     = {"h041a":h41,"h026":h026,"h045":h045_v,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
        s_is   = stats(h045_v[is_mask(h045_v.index)])
        s_oos  = stats(h045_v[oos_mask(h045_v.index)])
        s_ao   = stats(h045_v[ao_mask(h045_v.index)])
        p_oos  = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
        p_ao   = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
        wf     = run_wf(cidx, rd, PROD_W)
        ww     = min(wf) if wf else 0.0
        if name == "base":
            base_port_oos = p_oos["sharpe"]
            base_port_ao  = p_ao["sharpe"]
            both_up = False
        else:
            both_up = p_oos["sharpe"] > base_port_oos and p_ao["sharpe"] > base_port_ao
        print(f"  {name:18}  {s_is['sharpe']:>8.4f}  {s_oos['sharpe']:>9.4f}  "
              f"{s_ao['sharpe']:>12.4f}  {p_oos['sharpe']:>9.4f}  {p_ao['sharpe']:>11.4f}  "
              f"{p_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  "
              f"{'—' if name=='base' else ('✓' if both_up else '✗')}")
        results[name] = {
            "h045_is": s_is["sharpe"], "h045_oos": s_oos["sharpe"],
            "h045_ao": s_ao["sharpe"], "port_oos": p_oos["sharpe"],
            "port_ao": p_ao["sharpe"], "maxdd": p_oos["max_drawdown"],
            "wf_worst": ww, "both_up": bool(both_up),
            "h045_r": h045_v, "cidx": cidx, "rd": rd
        }
    except Exception as e:
        print(f"  {name:18}  ERROR: {e}")

# ── [2] Full cross-validation of best confirmed candidate ─────────────────────
winners = {k: v for k, v in results.items() if v.get("both_up", False)}
print(f"\n[2] Winners (both windows ✓): {list(winners.keys()) if winners else 'NONE'}")

if winners:
    best_name = max(winners, key=lambda k: winners[k]["port_oos"] + winners[k]["port_ao"])
    best = winners[best_name]
    print(f"\n  Best candidate: {best_name}")
    print(f"  Full cross-validation …")

    cidx = best["cidx"]
    rd   = best["rd"]

    s_is  = stats(make_port(rd, PROD_W, cidx[is_mask(cidx)]))
    s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
    s_ai  = stats(make_port(rd, PROD_W, cidx[ai_mask(cidx)]))
    s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, PROD_W)
    ww    = min(wf) if wf else 0.0

    print(f"\n  {'Portfolio':24}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
          f"{'AltOOS S':>9}  {'CAGR':>7}  {'MaxDD':>8}  {'WF':>7}")
    print("  "+"-"*87)

    # Baseline (H090)
    h045_base = build_rotation_monthly(H045_BASE, FULL_START, FULL_END, 2)
    cidx_b = common_idx(h045_base, h026, xlk_r, smh_r, igv_r, h41)
    rd_b   = {"h041a":h41,"h026":h026,"h045":h045_base,"XLK":xlk_r,"SMH":smh_r,"IGV":igv_r}
    sb_oos = stats(make_port(rd_b, PROD_W, cidx_b[oos_mask(cidx_b)]))
    sb_ao  = stats(make_port(rd_b, PROD_W, cidx_b[ao_mask(cidx_b)]))
    sb_is  = stats(make_port(rd_b, PROD_W, cidx_b[is_mask(cidx_b)]))
    sb_ai  = stats(make_port(rd_b, PROD_W, cidx_b[ai_mask(cidx_b)]))
    wf_b   = run_wf(cidx_b, rd_b, PROD_W)
    for lbl, s_i, s_o, s_a, s_ao_, wf_ in [
        ("H090 baseline", sb_is, sb_oos, sb_ai, sb_ao, wf_b),
        (f"H091 ({best_name})", s_is, s_oos, s_ai, s_ao, wf)
    ]:
        print(f"  {lbl:24}  {s_i['sharpe']:>7.4f}  {s_o['sharpe']:>7.4f}  "
              f"{s_a['sharpe']:>8.4f}  {s_ao_['sharpe']:>9.4f}  "
              f"{s_o['cagr']*100:>6.2f}%  {s_o['max_drawdown']*100:>7.2f}%  "
              f"{min(wf_):>7.3f} {'✓' if min(wf_)>=WF_WORST_MIN else '✗'}")

    # Calendar year
    print(f"\n  Calendar year comparison …")
    print(f"  {'Year':>5}  {'H090 base':>10}  {f'H091 ({best_name})':>16}  {'Delta':>7}")
    print("  "+"-"*50)
    cal = []
    neg_b = neg_n = 0
    for yr in range(2004, 2026):
        yib = cidx_b[cidx_b.year == yr]
        yin = cidx[cidx.year == yr]
        if len(yib) == 0 or len(yin) == 0: continue
        rb = float((1+make_port(rd_b, PROD_W, yib)).prod()-1)
        rn = float((1+make_port(rd, PROD_W, yin)).prod()-1)
        if rb < 0: neg_b += 1
        if rn < 0: neg_n += 1
        print(f"  {yr:>5}  {rb*100:>9.2f}%  {rn*100:>15.2f}%  {(rn-rb)*100:>+6.2f}pp")
        cal.append({"year":yr,"h090":round(rb,4),"h091":round(rn,4)})
    print(f"  H090: {'ZERO' if neg_b==0 else neg_b} neg yrs  |  H091: {'ZERO' if neg_n==0 else neg_n} neg yrs")

    print(f"\n  WF folds: {[round(f,3) for f in wf]} → min {ww:.3f}")

    confirmed = s_oos["sharpe"] > base_port_oos and s_ao["sharpe"] > base_port_ao and ww >= WF_WORST_MIN
    print(f"\n[3] Summary …")
    print(f"  OOS:    {base_port_oos:.4f} → {s_oos['sharpe']:.4f} (Δ={s_oos['sharpe']-base_port_oos:+.4f})")
    print(f"  AltOOS: {base_port_ao:.4f} → {s_ao['sharpe']:.4f} (Δ={s_ao['sharpe']-base_port_ao:+.4f})")
    print(f"  MaxDD:  {sb_oos['max_drawdown']*100:.2f}% → {s_oos['max_drawdown']*100:.2f}%")
    print(f"  WF:     {min(wf_b):.3f} → {ww:.3f}")
    if confirmed:
        print(f"\n  *** H091 CONFIRMED — H045 += {best_name} ***")
    else:
        print(f"\n  H091 not confirmed — H045 universe unchanged.")
else:
    cal = []
    confirmed = False
    best_name = "none"
    print("\n[3] Summary …")
    print("  No candidates passed dual-window criterion.")
    print("  H091 not confirmed — H045 universe unchanged.")

output = {
    "sweep": {k: {kk: vv for kk, vv in v.items() if kk not in ("h045_r","cidx","rd")}
              for k, v in results.items()},
    "winner": best_name,
    "calendar": cal,
    "confirmed": bool(confirmed),
}
out_path = RESULT_DIR / "h091_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
