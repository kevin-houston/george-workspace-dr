"""
H115 — Time-Series Momentum (TSMOM, §3.3, 151 Strategies)
==========================================================

Thesis: Each asset's own past return predicts its future return (Moskowitz,
Ooi & Pedersen 2012). Unlike cross-sectional momentum (ranking assets against
each other), TSMOM compares each asset to its own history — hold if 12m return
> 0, else go to cash. Often called "trend following" at asset class level.

Sub-experiments:
  A) Pure TSMOM on multi-asset ETF universe (SPY, QQQ, EEM, EFA, TLT, GLD,
     IEF, BIL, XLE, XLB, DBC, USO): hold all positive-momentum assets equal-
     weight; when none qualify, hold BIL.
  B) TSMOM as a PRE-FILTER on H112 selection — asset must pass 12m > 0 to
     be eligible for the composite score ranking. Test on H041a + H026.
  C) Blend test: if any sub-exp confirms standalone edge, test adding as 10%
     component to production (check correlation + marginal OOS contribution).

Production baseline: H112 OOS 4.1577, AltOOS 4.0612, MaxDD -3.60%, WF 3.024
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

# Multi-asset TSMOM universe: broad coverage across equity, bond, commodity
TSMOM_UNIVERSE = [
    "SPY","QQQ","EEM","EFA","TLT","GLD","IEF","BIL",
    "XLE","XLK","XLF","XLV","DBC","USO","GDX","EWJ","EWH",
]

# H112 sub-strategy universes
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

# H112 IBS parameters
IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}
IBS_TOTAL = 0.30
PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

_PREFIXES = [f"h{i:03d}" for i in range(62, 116)]


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        for suffix in ["ohlc"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_{suffix}_{start}_{end}.parquet"
            if cp.exists():
                df = pd.read_parquet(cp)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open","high","low","close"]):
                    return df
    cp = CACHE_DIR / f"h115_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h115_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Strategy builders ────────────────────────────────────────────────────────

def build_tsmom_monthly(tickers, start, end):
    """
    Pure TSMOM: each month, hold equal weight in all assets with 12m return > 0.
    If nothing qualifies, hold BIL (via its ~0 return).
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
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        positive = mom_row[mom_row > 0].index.tolist()
        if not positive:
            # All assets negative — go to BIL equivalent (0% return)
            rows.append((monthly_px.index[i], 0.0))
        else:
            month_ret = monthly_ret.iloc[i][positive].mean()
            rows.append((monthly_px.index[i], float(month_ret)))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def build_rotation_monthly_filtered(tickers, start, end, n_hold=1,
                                    tsmom_filter=False):
    """
    Standard composite score (12m mom rank + inv 6m vol rank), top-N.
    If tsmom_filter=True: only assets with positive 12m return are eligible.
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
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        mom_row = mom_12.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if tsmom_filter:
            # Only allow positive-momentum assets to compete
            valid = [t for t in valid if mom_row[t] > 0]
            if not valid:
                # Nothing passes filter → go to BIL (0%)
                rows.append((monthly_px.index[i], 0.0))
                continue
            valid_idx = pd.Index(valid)
        else:
            valid_idx = valid
        if len(valid_idx) < n_hold:
            if tsmom_filter:
                rows.append((monthly_px.index[i], monthly_ret.iloc[i][list(valid_idx)].mean()))
            continue
        score = mom_row[valid_idx].rank() + vol_row[valid_idx].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_ret.iloc[i][top_n].mean())))
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


def stats(r, label=""):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r)}
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    cumul = float(eq.iloc[-1])
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r),
            "neg_years":neg_yrs,"cumul":round(cumul,4)}


def build_production_blend(start, end):
    """Reconstruct H112 production blend monthly returns."""
    from collections import defaultdict
    sub_rets = {}

    # H041a
    sub_rets["h041a"] = build_rotation_monthly_filtered(H041A_FULL, start, end, n_hold=1, tsmom_filter=False)
    # H026
    sub_rets["h026"]  = build_rotation_monthly_filtered(H026_ASSETS, start, end, n_hold=1, tsmom_filter=False)
    # H045
    sub_rets["h045"]  = build_rotation_monthly_filtered(H045_PROD, start, end, n_hold=2, tsmom_filter=False)

    # IBS components (daily → monthly)
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, start, end)
        eq = ibs_equity_curve(ohlc, buy, sell, hold, gap_min)
        sub_rets[sym] = to_monthly(eq)

    # Combine at H112 weights
    df = pd.DataFrame(sub_rets)
    combined = pd.Series(0.0, index=df.dropna(how="all").index)
    for key, w in PROD_W.items():
        if key in df.columns:
            combined = combined.add(df[key].reindex(combined.index).fillna(0) * w, fill_value=0)
    return combined.dropna()


# ── Evaluation helpers ────────────────────────────────────────────────────────

def period_stats(r, start, end, label):
    sub = r[start:end].dropna()
    s = stats(sub)
    print(f"   {label}:  Sharpe {s['sharpe']:.3f}  CAGR {s['cagr']*100:.1f}%  "
          f"MaxDD {s['max_drawdown']*100:.1f}%  Cumul {s['cumul']:.4f}  NegYrs={s['neg_years']}")
    return s


def blend_with_production(prod_r, new_r, weight=0.10, label=""):
    """Replace weight% of production with new strategy."""
    aligned = pd.DataFrame({"prod": prod_r, "new": new_r}).dropna()
    blended = aligned["prod"] * (1 - weight) + aligned["new"] * weight
    oos  = blended[OOS_START:]
    alt  = blended[ALT_OOS_ST:]
    orig_oos = aligned["prod"][OOS_START:]
    orig_alt = aligned["prod"][ALT_OOS_ST:]
    oos_delta  = (1+oos).cumprod().iloc[-1]  - (1+orig_oos).cumprod().iloc[-1]
    alt_delta  = (1+alt).cumprod().iloc[-1]  - (1+orig_alt).cumprod().iloc[-1]
    print(f"   Blend +{weight*100:.0f}% {label}: "
          f"OOS Δcumul={oos_delta:+.4f}  AltOOS Δcumul={alt_delta:+.4f}")
    return oos_delta, alt_delta


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    results = {}

    print("=" * 70)
    print("H115 — Time-Series Momentum (TSMOM)")
    print("=" * 70)

    # ── Experiment A: Pure TSMOM on multi-asset universe ─────────────────────
    print("\n── A) Pure TSMOM — multi-asset universe")
    print(f"   Universe ({len(TSMOM_UNIVERSE)} assets): {', '.join(TSMOM_UNIVERSE)}")
    tsmom_r = build_tsmom_monthly(TSMOM_UNIVERSE, FULL_START, FULL_END)
    is_a  = period_stats(tsmom_r, IS_START, IS_END, "IS  2008-2017")
    oos_a = period_stats(tsmom_r, OOS_START, FULL_END, "OOS 2018-2026")
    alt_a = period_stats(tsmom_r, ALT_OOS_ST, FULL_END, "Alt 2013-2026")

    # Fraction of months with ≥1 asset positive
    closes_ts = {}
    for t in TSMOM_UNIVERSE:
        try:
            closes_ts[t] = fetch_daily_close(t, FULL_START, FULL_END)
        except Exception:
            pass
    daily_ts = pd.DataFrame(closes_ts).sort_index()
    monthly_ts = daily_ts.resample("ME").last()
    mom12_ts = monthly_ts / monthly_ts.shift(12) - 1
    pct_positive = (mom12_ts > 0).sum(axis=1) / mom12_ts.notna().sum(axis=1)
    avg_holding = float(pct_positive[IS_START:].mean())
    print(f"   Avg fraction positive (IS+): {avg_holding:.1%}")

    results["exp_a"] = {"is": is_a, "oos": oos_a, "alt": alt_a,
                        "avg_pct_positive": round(avg_holding, 4)}

    # ── Experiment B1: TSMOM filter on H041a ─────────────────────────────────
    print("\n── B1) TSMOM pre-filter on H041a (22%)")
    print("   [baseline: composite, no filter]")
    h041a_baseline = build_rotation_monthly_filtered(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    b_is  = period_stats(h041a_baseline, IS_START, IS_END, "IS  baseline")
    b_oos = period_stats(h041a_baseline, OOS_START, FULL_END, "OOS baseline")

    print("   [TSMOM filter: only positive-momentum assets eligible]")
    h041a_filtered = build_rotation_monthly_filtered(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)
    f_is  = period_stats(h041a_filtered, IS_START, IS_END, "IS  filtered")
    f_oos = period_stats(h041a_filtered, OOS_START, FULL_END, "OOS filtered")
    f_alt = period_stats(h041a_filtered, ALT_OOS_ST, FULL_END, "Alt filtered")
    results["exp_b1"] = {"baseline_oos": b_oos, "filtered_oos": f_oos, "filtered_alt": f_alt}

    # ── Experiment B2: TSMOM filter on H026 ──────────────────────────────────
    print("\n── B2) TSMOM pre-filter on H026 (27%)")
    print("   [baseline: composite, no filter]")
    h026_baseline = build_rotation_monthly_filtered(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    b2_is  = period_stats(h026_baseline, IS_START, IS_END, "IS  baseline")
    b2_oos = period_stats(h026_baseline, OOS_START, FULL_END, "OOS baseline")

    print("   [TSMOM filter: only positive-momentum assets eligible]")
    h026_filtered = build_rotation_monthly_filtered(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)
    f2_is  = period_stats(h026_filtered, IS_START, IS_END, "IS  filtered")
    f2_oos = period_stats(h026_filtered, OOS_START, FULL_END, "OOS filtered")
    f2_alt = period_stats(h026_filtered, ALT_OOS_ST, FULL_END, "Alt filtered")
    results["exp_b2"] = {"baseline_oos": b2_oos, "filtered_oos": f2_oos, "filtered_alt": f2_alt}

    # ── Experiment C: Blend test ──────────────────────────────────────────────
    print("\n── C) Blend test vs production H112")
    print("   Building production blend…")
    prod_r = build_production_blend(FULL_START, FULL_END)
    prod_oos = prod_r[OOS_START:]
    prod_alt = prod_r[ALT_OOS_ST:]
    prod_oos_cumul = float((1+prod_oos).cumprod().iloc[-1])
    prod_alt_cumul = float((1+prod_alt).cumprod().iloc[-1])
    print(f"   Production: OOS {prod_oos_cumul:.4f}  AltOOS {prod_alt_cumul:.4f}")

    # Correlation
    aligned_a = pd.DataFrame({"prod": prod_r, "tsmom": tsmom_r}).dropna()
    corr_a = round(float(aligned_a.corr().iloc[0, 1]), 4)
    print(f"\n   Pure TSMOM: corr_with_prod={corr_a:+.3f}  OOS Sharpe={oos_a['sharpe']:.3f}  OOS Cumul={oos_a['cumul']:.4f}")

    blend_results = {}
    # Only blend if standalone performance is meaningful
    if oos_a["sharpe"] > 0 and oos_a["cumul"] > 1.0:
        d_oos, d_alt = blend_with_production(prod_r, tsmom_r, weight=0.10, label="pure TSMOM")
        blend_results["pure_tsmom"] = {"oos_delta": round(float(d_oos), 4), "alt_delta": round(float(d_alt), 4)}

    # Test filtered H041a blend contribution
    if f_oos["sharpe"] > b_oos["sharpe"] and f_oos["cumul"] > b_oos["cumul"]:
        print("\n   TSMOM filter IMPROVES H041a — testing production impact…")
        # Rebuild production with filtered H041a
        sub_rets_filt = {}
        sub_rets_filt["h041a"] = h041a_filtered
        sub_rets_filt["h026"]  = h026_baseline
        sub_rets_filt["h045"]  = build_rotation_monthly_filtered(H045_PROD, FULL_START, FULL_END, n_hold=2, tsmom_filter=False)
        for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
            ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
            eq = ibs_equity_curve(ohlc, buy, sell, hold, gap_min)
            sub_rets_filt[sym] = to_monthly(eq)
        df_filt = pd.DataFrame(sub_rets_filt)
        combined_filt = pd.Series(0.0, index=df_filt.dropna(how="all").index)
        for key, w in PROD_W.items():
            if key in df_filt.columns:
                combined_filt = combined_filt.add(df_filt[key].reindex(combined_filt.index).fillna(0) * w, fill_value=0)
        combined_filt = combined_filt.dropna()
        filt_oos = combined_filt[OOS_START:]
        filt_alt = combined_filt[ALT_OOS_ST:]
        filt_oos_c = float((1+filt_oos).cumprod().iloc[-1])
        filt_alt_c = float((1+filt_alt).cumprod().iloc[-1])
        print(f"   H112 with H041a TSMOM filter: OOS {filt_oos_c:.4f}  AltOOS {filt_alt_c:.4f}")
        print(f"   Delta vs baseline:             OOS {filt_oos_c-prod_oos_cumul:+.4f}  AltOOS {filt_alt_c-prod_alt_cumul:+.4f}")
        blend_results["h041a_tsmom_filter"] = {
            "oos_cumul": round(filt_oos_c, 4), "alt_cumul": round(filt_alt_c, 4),
            "oos_delta": round(filt_oos_c - prod_oos_cumul, 4),
            "alt_delta": round(filt_alt_c - prod_alt_cumul, 4),
        }

    if f2_oos["sharpe"] > b2_oos["sharpe"] and f2_oos["cumul"] > b2_oos["cumul"]:
        print("\n   TSMOM filter IMPROVES H026 — testing production impact…")
        sub_rets_filt2 = {}
        sub_rets_filt2["h041a"] = h041a_baseline
        sub_rets_filt2["h026"]  = h026_filtered
        sub_rets_filt2["h045"]  = build_rotation_monthly_filtered(H045_PROD, FULL_START, FULL_END, n_hold=2, tsmom_filter=False)
        for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
            ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
            eq = ibs_equity_curve(ohlc, buy, sell, hold, gap_min)
            sub_rets_filt2[sym] = to_monthly(eq)
        df_filt2 = pd.DataFrame(sub_rets_filt2)
        combined_filt2 = pd.Series(0.0, index=df_filt2.dropna(how="all").index)
        for key, w in PROD_W.items():
            if key in df_filt2.columns:
                combined_filt2 = combined_filt2.add(df_filt2[key].reindex(combined_filt2.index).fillna(0) * w, fill_value=0)
        combined_filt2 = combined_filt2.dropna()
        filt2_oos = combined_filt2[OOS_START:]
        filt2_alt = combined_filt2[ALT_OOS_ST:]
        filt2_oos_c = float((1+filt2_oos).cumprod().iloc[-1])
        filt2_alt_c = float((1+filt2_alt).cumprod().iloc[-1])
        print(f"   H112 with H026 TSMOM filter: OOS {filt2_oos_c:.4f}  AltOOS {filt2_alt_c:.4f}")
        print(f"   Delta vs baseline:            OOS {filt2_oos_c-prod_oos_cumul:+.4f}  AltOOS {filt2_alt_c-prod_alt_cumul:+.4f}")
        blend_results["h026_tsmom_filter"] = {
            "oos_cumul": round(filt2_oos_c, 4), "alt_cumul": round(filt2_alt_c, 4),
            "oos_delta": round(filt2_oos_c - prod_oos_cumul, 4),
            "alt_delta": round(filt2_alt_c - prod_alt_cumul, 4),
        }

    results["exp_c"] = {
        "prod_oos_cumul": round(prod_oos_cumul, 4),
        "prod_alt_cumul": round(prod_alt_cumul, 4),
        "tsmom_corr_with_prod": corr_a,
        "blend": blend_results,
    }

    # ── Verdict ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    confirmed = False
    # Pure TSMOM standalone confirmed if Sharpe > 0.5 and Cumul > 1.2
    if oos_a["sharpe"] > 0.5 and oos_a["cumul"] > 1.2:
        print(f"\n  → CONFIRMED (standalone): Pure TSMOM  "
              f"Sharpe {oos_a['sharpe']:.3f}  Cumul {oos_a['cumul']:.4f}  corr={corr_a:+.3f}")
        confirmed = True
    else:
        print(f"\n  Pure TSMOM standalone: Sharpe {oos_a['sharpe']:.3f}  Cumul {oos_a['cumul']:.4f}")

    # Filter improvements
    if "h041a_tsmom_filter" in blend_results:
        d = blend_results["h041a_tsmom_filter"]
        if d["oos_delta"] > 0 and d["alt_delta"] > 0:
            print(f"  → CONFIRMED (filter): H041a TSMOM filter improves both windows "
                  f"OOS Δ{d['oos_delta']:+.4f}  AltOOS Δ{d['alt_delta']:+.4f}")
            confirmed = True
    if "h026_tsmom_filter" in blend_results:
        d = blend_results["h026_tsmom_filter"]
        if d["oos_delta"] > 0 and d["alt_delta"] > 0:
            print(f"  → CONFIRMED (filter): H026 TSMOM filter improves both windows "
                  f"OOS Δ{d['oos_delta']:+.4f}  AltOOS Δ{d['alt_delta']:+.4f}")
            confirmed = True

    if not confirmed:
        print("  → NOT CONFIRMED — neither standalone TSMOM nor TSMOM filter improves production")

    verdict = "CONFIRMED" if confirmed else "NOT_CONFIRMED"
    results["verdict"] = verdict
    results["confirmed"] = confirmed

    out = RESULT_DIR / "h115_results.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved → {out}")


if __name__ == "__main__":
    main()
