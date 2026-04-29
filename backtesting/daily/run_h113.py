"""
H113 — Low-Volatility Anomaly (§3.4, 151 Strategies)
======================================================

Thesis: Low-volatility assets produce higher RISK-ADJUSTED returns than
high-volatility assets (contradicts CAPM). Implementation as monthly ETF
rotation using PURE vol signal (no momentum component) — tests whether
the vol half of the H041a/H026 composite score already captures this,
or whether a pure vol signal is complementary.

Sub-experiments:
  A) Pure-vol rotation on H041A_FULL (19-asset): rank by inv_6m_vol only
  B) Pure-vol rotation on H026_ASSETS (25-asset): same
  C) Low-vol factor ETFs (USMV/SPLV/EFAV/EEMV/XLU/BIL): AltOOS only
     (data available from ~2011)
  D) Blend test: if any sub-exp confirms edge, test adding as 10% component
     to production portfolio — check correlation and marginal OOS contribution

KEY QUESTION: Is pure-vol signal uncorrelated enough with H041a/H026/H045
to add to production, or does the existing composite already capture it?

Production baseline: OOS 4.1577, AltOOS 4.0612, MaxDD -3.60%, WF 3.024
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

# H112 production universes
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

# Low-vol factor ETFs (inception ~2011)
LOWVOL_FACTOR = ["USMV","SPLV","EFAV","EEMV","XLU","BIL"]
ALTOOS_START  = "2013-01-01"  # use AltOOS window for factor ETFs (full data)

# H112 IBS params
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
IBS_TOTAL = 0.30

# Production weights
PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

_PREFIXES = [f"h{i:03d}" for i in range(62, 113)]


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h113_{ticker}_ohlc_{start}_{end}.parquet"
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
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h113_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Strategy builders ────────────────────────────────────────────────────────

def build_rotation_monthly(tickers, start, end, n_hold=1, signal="composite"):
    """
    signal='composite': rank(12m_mom) + rank(inv_6m_vol)  [standard H-series]
    signal='lowvol':    rank(inv_6m_vol) only              [pure low-vol anomaly]
    signal='lowvol12':  rank(inv_12m_vol) only             [longer vol window]
    """
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_ret= daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    vol_12 = monthly_ret.rolling(12).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(12, len(monthly_px)):
        vol_row6  = vol_6.iloc[i].dropna()
        vol_row12 = vol_12.iloc[i].dropna()
        mom_row   = mom_12.iloc[i].dropna()
        if signal == "composite":
            valid = mom_row.index.intersection(vol_row6.index)
            if len(valid) < n_hold: continue
            score = mom_row[valid].rank() + vol_row6[valid].rank(ascending=False)
        elif signal == "lowvol":
            valid = vol_row6.index
            if len(valid) < n_hold: continue
            score = vol_row6[valid].rank(ascending=False)
        elif signal == "lowvol12":
            valid = vol_row12.index
            if len(valid) < n_hold: continue
            score = vol_row12[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom = (df["high"]-df["low"]).replace(0, np.nan)
    ibs = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"]-prev_cl)/prev_cl
    equity = INITIAL_EQUITY
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
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r)}


def build_production_blend(start, end):
    """Full production blend (H112 weights) for correlation analysis."""
    h041a = build_rotation_monthly(H041A_FULL, start, end, n_hold=1)
    h026  = build_rotation_monthly(H026_ASSETS, start, end, n_hold=1)
    h045  = build_rotation_monthly(H045_PROD, start, end, n_hold=2)
    xlk_eq = ibs_equity_curve(fetch_ohlc("XLK",start,end), *XLK_PARAMS)
    smh_eq = ibs_equity_curve(fetch_ohlc("SMH",start,end), *SMH_PARAMS)
    igv_eq = ibs_equity_curve(fetch_ohlc("IGV",start,end), *IGV_PARAMS)
    xlk_r = to_monthly(xlk_eq); smh_r = to_monthly(smh_eq); igv_r = to_monthly(igv_eq)
    w = PROD_W
    xlk_share = w["XLK"]/IBS_TOTAL; smh_share = w["SMH"]/IBS_TOTAL; igv_share = w["IGV"]/IBS_TOTAL
    ibs_r = xlk_r * xlk_share + smh_r.reindex(xlk_r.index).fillna(0) * smh_share + \
            igv_r.reindex(xlk_r.index).fillna(0) * igv_share
    idx = h041a.index.intersection(h026.index).intersection(h045.index).intersection(ibs_r.index)
    blend = (h041a[idx]*w["h041a"] + h026[idx]*w["h026"] + h045[idx]*w["h045"] +
             ibs_r[idx]*IBS_TOTAL)
    return blend


def run_wf(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    total = len(is_idx)
    folds = []
    for fold in range(n_folds):
        train_end = min_train + fold * test_size
        if train_end + test_size > total: break
        train_idx = is_idx[:train_end]
        test_idx  = is_idx[train_end:train_end+test_size]
        blend_test = sum(r_dict[k][test_idx].fillna(0) * w.get(k,0) for k in r_dict if k in r_dict)
        s = stats(blend_test)
        folds.append(s["sharpe"])
    return min(folds) if folds else 0.0


# ── Eval helper ──────────────────────────────────────────────────────────────

def eval_standalone(label, returns, context=""):
    r = returns.dropna()
    is_r  = r[(r.index >= IS_START) & (r.index <= IS_END)]
    oos_r = r[r.index >= OOS_START]
    alt_r = r[r.index >= ALT_OOS_ST]
    is_s  = stats(is_r)
    oos_s = stats(oos_r)
    alt_s = stats(alt_r)
    eq_oos = float((1+oos_r).cumprod().iloc[-1]) if len(oos_r) > 0 else 0.0
    eq_alt = float((1+alt_r).cumprod().iloc[-1]) if len(alt_r) > 0 else 0.0
    deg = (oos_s["sharpe"] - is_s["sharpe"]) / abs(is_s["sharpe"]) * 100 if is_s["sharpe"] != 0 else 0.0
    neg_yrs = sum(1 for y, g in r.groupby(r.index.year) if (1+g).prod()-1 < 0)
    print(f"\n  {label}{(' '+context) if context else ''}")
    print(f"    IS  {IS_START[:4]}-{IS_END[:4]}: Sharpe {is_s['sharpe']:+.3f}  CAGR {is_s['cagr']*100:+.1f}%  MaxDD {is_s['max_drawdown']*100:.1f}%")
    print(f"    OOS {OOS_START[:4]}-2026:       Sharpe {oos_s['sharpe']:+.3f}  CAGR {oos_s['cagr']*100:+.1f}%  Cumul {eq_oos:.4f}  NegYrs={neg_yrs}")
    print(f"    Alt {ALT_OOS_ST[:4]}-2026:      Sharpe {alt_s['sharpe']:+.3f}  CAGR {alt_s['cagr']*100:+.1f}%  Cumul {eq_alt:.4f}  Deg={deg:+.1f}%")
    return {"is": is_s, "oos": oos_s, "alt": alt_s, "eq_oos": round(eq_oos,4), "eq_alt": round(eq_alt,4), "deg": round(deg,1), "neg_yrs": neg_yrs}


def correlation_to_blend(candidate_returns, blend_returns, window_start, label):
    idx = candidate_returns.index.intersection(blend_returns.index)
    idx = idx[idx >= pd.Timestamp(window_start)]
    if len(idx) < 12:
        print(f"    {label}: insufficient overlap for correlation")
        return None
    corr = float(candidate_returns[idx].corr(blend_returns[idx]))
    print(f"    Correlation vs production blend ({window_start[:4]}–present): {corr:+.3f}")
    return corr


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("="*70)
    print("H113 — Low-Volatility Anomaly")
    print("="*70)

    # ── A: Pure vol signal on H041A universe ──────────────────────────────
    print("\n[A] Pure low-vol signal on H041A_FULL (19-asset) vs composite")
    print("    Hypothesis: pure vol rank diverges from momentum+vol composite,")
    print("    producing a different/uncorrelated equity curve.\n")

    r_h041a_comp = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, n_hold=1, signal="composite")
    r_h041a_lv6  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, n_hold=1, signal="lowvol")
    r_h041a_lv12 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, n_hold=1, signal="lowvol12")

    res_comp = eval_standalone("H041A composite (baseline)", r_h041a_comp)
    res_lv6  = eval_standalone("H041A pure-vol 6m",  r_h041a_lv6)
    res_lv12 = eval_standalone("H041A pure-vol 12m", r_h041a_lv12)

    # Correlation between signals
    idx_oos = r_h041a_comp.index[r_h041a_comp.index >= OOS_START]
    corr_cv = float(r_h041a_comp[idx_oos].corr(r_h041a_lv6[idx_oos]))
    print(f"\n    Correlation composite vs pure-vol-6m (OOS): {corr_cv:+.3f}")
    idx_alt = r_h041a_comp.index[r_h041a_comp.index >= ALT_OOS_ST]
    corr_ca = float(r_h041a_comp[idx_alt].corr(r_h041a_lv6[idx_alt]))
    print(f"    Correlation composite vs pure-vol-6m (AltOOS): {corr_ca:+.3f}")

    # ── B: Pure vol signal on H026 universe ──────────────────────────────
    print("\n[B] Pure low-vol signal on H026_ASSETS (25-asset)\n")

    r_h026_comp = build_rotation_monthly(H026_ASSETS, FULL_START, FULL_END, n_hold=1, signal="composite")
    r_h026_lv   = build_rotation_monthly(H026_ASSETS, FULL_START, FULL_END, n_hold=1, signal="lowvol")

    res_h026c = eval_standalone("H026 composite (baseline)", r_h026_comp)
    res_h026v = eval_standalone("H026 pure-vol 6m",  r_h026_lv)

    corr_h026 = float(r_h026_comp[idx_oos].corr(r_h026_lv[idx_oos]))
    print(f"\n    Correlation H026 composite vs pure-vol (OOS): {corr_h026:+.3f}")

    # ── C: Low-vol factor ETFs (AltOOS only) ─────────────────────────────
    print("\n[C] Low-vol factor ETFs: USMV/SPLV/EFAV/EEMV/XLU/BIL")
    print("    Data from 2012; testing AltOOS (2013-2026) window only.\n")

    r_factor_comp = build_rotation_monthly(LOWVOL_FACTOR, "2011-01-01", FULL_END, n_hold=1, signal="composite")
    r_factor_lv   = build_rotation_monthly(LOWVOL_FACTOR, "2011-01-01", FULL_END, n_hold=1, signal="lowvol")

    # AltOOS stats only
    for label, r in [("Factor composite (2013–2026)", r_factor_comp), ("Factor pure-vol (2013–2026)", r_factor_lv)]:
        alt_r = r[r.index >= ALT_OOS_ST]
        is_r  = r[(r.index >= "2012-01-01") & (r.index < "2013-01-01")]
        s_alt = stats(alt_r)
        eq_alt = float((1+alt_r).cumprod().iloc[-1]) if len(alt_r) else 0.0
        neg = sum(1 for y, g in alt_r.groupby(alt_r.index.year) if (1+g).prod()-1 < 0)
        print(f"  {label}: Sharpe {s_alt['sharpe']:+.3f}  CAGR {s_alt['cagr']*100:+.1f}%  Cumul {eq_alt:.4f}  NegYrs={neg}")

    # ── D: Correlation with production blend ─────────────────────────────
    print("\n[D] Correlation of low-vol signals vs production blend")
    print("    Building production blend (H112 weights) for comparison…\n")

    blend = build_production_blend(FULL_START, FULL_END)

    for label, sig, win in [
        ("H041A pure-vol 6m",  r_h041a_lv6,  OOS_START),
        ("H026 pure-vol 6m",   r_h026_lv,    OOS_START),
        ("Factor composite",   r_factor_comp, ALT_OOS_ST),
        ("Factor pure-vol",    r_factor_lv,   ALT_OOS_ST),
    ]:
        correlation_to_blend(sig, blend, win, label)

    # ── E: Blend test — add pure-vol H041A as 10% component ──────────────
    print("\n[E] Blend test: production (90%) + pure-vol H041A (10%)")
    print("    Does 10% pure-vol signal improve OOS vs production alone?\n")

    idx = blend.index.intersection(r_h041a_lv6.index)
    blend_plus = blend[idx] * 0.90 + r_h041a_lv6[idx] * 0.10

    prod_oos  = stats(blend[blend.index >= OOS_START])
    plus_oos  = stats(blend_plus[blend_plus.index >= OOS_START])
    prod_alt  = stats(blend[blend.index >= ALT_OOS_ST])
    plus_alt  = stats(blend_plus[blend_plus.index >= ALT_OOS_ST])
    prod_cumul_oos = float((1+blend[blend.index >= OOS_START]).cumprod().iloc[-1])
    plus_cumul_oos = float((1+blend_plus[blend_plus.index >= OOS_START]).cumprod().iloc[-1])
    prod_cumul_alt = float((1+blend[blend.index >= ALT_OOS_ST]).cumprod().iloc[-1])
    plus_cumul_alt = float((1+blend_plus[blend_plus.index >= ALT_OOS_ST]).cumprod().iloc[-1])

    print(f"  Production (OOS):  Sharpe {prod_oos['sharpe']:.3f}  Cumul {prod_cumul_oos:.4f}  MaxDD {prod_oos['max_drawdown']*100:.2f}%")
    print(f"  +PureVol10% (OOS): Sharpe {plus_oos['sharpe']:.3f}  Cumul {plus_cumul_oos:.4f}  MaxDD {plus_oos['max_drawdown']*100:.2f}%  Δ={plus_cumul_oos-prod_cumul_oos:+.4f}")
    print(f"  Production (Alt):  Sharpe {prod_alt['sharpe']:.3f}  Cumul {prod_cumul_alt:.4f}")
    print(f"  +PureVol10% (Alt): Sharpe {plus_alt['sharpe']:.3f}  Cumul {plus_cumul_alt:.4f}  Δ={plus_cumul_alt-prod_cumul_alt:+.4f}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)

    composite_oos  = res_comp["eq_oos"]
    lowvol_oos     = res_lv6["eq_oos"]
    lowvol_sharpe  = res_lv6["oos"]["sharpe"]
    delta_blend    = plus_cumul_oos - prod_cumul_oos

    if lowvol_sharpe > 0.5 and abs(corr_cv) < 0.7 and delta_blend > 0:
        verdict = "PROMISING — low-vol signal has edge + low correlation + blend improves OOS"
    elif lowvol_sharpe > 0 and delta_blend > 0:
        verdict = "MARGINAL — low-vol adds slight OOS improvement but modest standalone edge"
    elif abs(corr_cv) > 0.85:
        verdict = "REDUNDANT — pure-vol signal highly correlated with composite; already captured"
    else:
        verdict = "NOT ADDITIVE — blend does not improve OOS vs production"

    print(f"\n  H041A composite OOS cumul:   {composite_oos:.4f}")
    print(f"  H041A pure-vol OOS cumul:    {lowvol_oos:.4f}")
    print(f"  Pure-vol/composite corr:     {corr_cv:+.3f}")
    print(f"  Blend Δ OOS cumul:           {delta_blend:+.4f}")
    print(f"\n  → {verdict}")

    result = {
        "h113": {
            "h041a_composite_oos": composite_oos,
            "h041a_lowvol_oos":    lowvol_oos,
            "h041a_lowvol_sharpe_oos": lowvol_sharpe,
            "h026_composite_oos":  res_h026c["eq_oos"],
            "h026_lowvol_oos":     res_h026v["eq_oos"],
            "corr_composite_vs_lowvol_oos": round(corr_cv, 3),
            "corr_composite_vs_lowvol_alt": round(corr_ca, 3),
            "blend_plus_lowvol10_oos": round(plus_cumul_oos, 4),
            "blend_delta_oos": round(delta_blend, 4),
            "verdict": verdict,
        }
    }
    out = RESULT_DIR / "h113_results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  Results saved → {out}")


if __name__ == "__main__":
    main()
