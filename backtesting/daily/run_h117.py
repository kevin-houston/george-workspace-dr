"""
H117 — Seasonality Overlay: "Sell in May" (§4.5, 151 Strategies)
=================================================================

Thesis: Equity markets earn most of their returns in the Nov-Apr window;
May-Oct is historically flat or negative. The "Halloween effect" / "Sell in
May" pattern is one of the most replicated calendar anomalies (Bouman &
Jacobsen 2002). Test as an overlay on H116 production.

Sub-experiments:
  A) Standalone seasonality: hold SPY Nov-Apr, hold BIL May-Oct.
  B) Seasonality filter on H116's equity sub-strategies (H041a + H026):
     In May-Oct, force selection to BIL (or best fixed-income proxy).
  C) Soft version: in May-Oct, reduce H041a/H026 weight by 50% and shift to H045.
  D) Best version → test production impact vs H116 baseline.

H116 baseline: OOS 6.5635, AltOOS 14.9411, MaxDD -3.60%, NegYrs=0
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
ALT_OOS_ST = "2013-01-01"

H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}
PROD_W_H116 = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

SUMMER_MONTHS = {5, 6, 7, 8, 9, 10}   # May–Oct = "sell" season

_PREFIXES = [f"h{i:03d}" for i in range(62, 118)]


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h117_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h117_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Strategy builders ─────────────────────────────────────────────────────────

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter=False,
                   seasonal_filter=False):
    """
    seasonal_filter: in May-Oct, override selection to return 0% (cash/BIL).
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
        month = monthly_px.index[i].month

        # Seasonal override: in May-Oct, go to cash (0%)
        if seasonal_filter and month in SUMMER_MONTHS:
            rows.append((monthly_px.index[i], 0.0))
            continue

        vol_row = vol_6.iloc[i].dropna()
        mom_row = mom_12.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)

        if tsmom_filter:
            valid = pd.Index([t for t in valid if mom_row[t] > 0])
            if len(valid) == 0:
                rows.append((monthly_px.index[i], 0.0))
                continue

        if len(valid) < n_hold:
            rows.append((monthly_px.index[i], monthly_ret.iloc[i][list(valid)].mean() if len(valid) > 0 else 0.0))
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
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


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r),"neg_years":0,"cumul":1.0}
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r),
            "neg_years":neg_yrs,"cumul":round(float(eq.iloc[-1]),4)}


def build_blend(sub_rets_dict, weights=None):
    w = weights or PROD_W_H116
    df = pd.DataFrame(sub_rets_dict)
    combined = pd.Series(0.0, index=df.dropna(how="all").index)
    for key, wt in w.items():
        if key in df.columns:
            combined = combined.add(df[key].reindex(combined.index).fillna(0) * wt, fill_value=0)
    return combined.dropna()


def pstats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<40} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  Neg={oos['neg_years']}")
    return oos, alt


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H117 — Seasonality Overlay (Sell in May, §4.5)")
    print(f"Summer months: {sorted(SUMMER_MONTHS)} (May–Oct)")
    print("=" * 70)

    results = {}

    # ── Exp A: Standalone SPY seasonal ───────────────────────────────────────
    print("\n── A) Standalone SPY seasonality (hold SPY Nov-Apr, BIL May-Oct)")
    spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
    spy_monthly_px = spy_close.resample("ME").last()
    spy_monthly_ret= spy_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    # Nov-Apr only, 0% otherwise
    rows = []
    for i in range(len(spy_monthly_px)):
        m = spy_monthly_px.index[i].month
        ret = float(spy_monthly_ret.iloc[i]) if m not in SUMMER_MONTHS else 0.0
        rows.append((spy_monthly_px.index[i], ret))
    seasonal_spy = pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))

    # SPY buy-and-hold for comparison
    spy_bah = spy_monthly_ret.dropna()

    oos_spy_s, alt_spy_s = pstats(seasonal_spy, "SPY seasonal (Nov-Apr)")
    oos_bah, alt_bah = pstats(spy_bah, "SPY buy-and-hold")

    # Monthly return by month for intuition
    monthly_avg = spy_bah.groupby(spy_bah.index.month).mean()
    print("\n   Avg SPY monthly return by month (2003–2026):")
    for m, v in monthly_avg.items():
        tag = " ← summer" if m in SUMMER_MONTHS else ""
        print(f"     {m:2d}: {v*100:+.2f}%{tag}")

    results["exp_a"] = {"seasonal_oos": oos_spy_s, "bah_oos": oos_bah}

    # ── Exp B: H116 with seasonal filter on H041a ─────────────────────────────
    print("\n── B) H116 with seasonal filter on H041a (summer → 0%)")

    # Build all components once (H116 base = H026 tsmom_filter=True)
    print("  Computing H041a variants…")
    h041a_base = build_rotation(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h041a_seas = build_rotation(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=False, seasonal_filter=True)
    print("  Computing H026 variants (with TSMOM filter)…")
    h026_filt      = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)
    h026_filt_seas = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True, seasonal_filter=True)
    print("  Computing H045…")
    h045_base = build_rotation(H045_PROD, FULL_START, FULL_END, n_hold=2, tsmom_filter=False)

    print("  Computing IBS…")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))

    # H116 baseline
    h116_base = build_blend({
        "h041a": h041a_base, "h026": h026_filt, "h045": h045_base, **ibs_rets
    })
    oos_b116, alt_b116 = pstats(h116_base, "H116 baseline")

    print("\n── B) Seasonal filter combinations on H116")
    combos = {
        "H116 base (reference)":         {"h041a": h041a_base, "h026": h026_filt},
        "H041a seasonal":                {"h041a": h041a_seas, "h026": h026_filt},
        "H026 seasonal":                 {"h041a": h041a_base, "h026": h026_filt_seas},
        "H041a+H026 seasonal":           {"h041a": h041a_seas, "h026": h026_filt_seas},
    }

    combo_results = {}
    for label, sub in combos.items():
        blend = build_blend({**sub, "h045": h045_base, **ibs_rets})
        oos, alt = pstats(blend, label)
        combo_results[label] = {
            "oos_cumul": oos["cumul"], "alt_cumul": alt["cumul"],
            "oos_sharpe": oos["sharpe"], "oos_cagr": oos["cagr"],
            "max_drawdown": oos["max_drawdown"], "neg_years": oos["neg_years"],
        }

    results["exp_b"] = combo_results

    # ── Verdict ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)

    baseline_oos = combo_results["H116 base (reference)"]["oos_cumul"]
    baseline_alt = combo_results["H116 base (reference)"]["alt_cumul"]

    confirmed_combos = []
    for label, r in combo_results.items():
        if label == "H116 base (reference)":
            continue
        if r["oos_cumul"] > baseline_oos and r["alt_cumul"] > baseline_alt:
            confirmed_combos.append((label, r))

    if confirmed_combos:
        best_label, best = max(confirmed_combos, key=lambda x: x[1]["oos_cumul"] + x[1]["alt_cumul"])
        print(f"\n  → CONFIRMED: '{best_label}'")
        print(f"    OOS  {best['oos_cumul']:.4f}  Δ{best['oos_cumul']-baseline_oos:+.4f}")
        print(f"    Alt  {best['alt_cumul']:.4f}  Δ{best['alt_cumul']-baseline_alt:+.4f}")
        results["verdict"] = "CONFIRMED"
        results["confirmed"] = True
        results["best_label"] = best_label
        results["best"] = best
    else:
        print("\n  → NOT CONFIRMED — no seasonal filter improves both OOS windows")
        results["verdict"] = "NOT_CONFIRMED"
        results["confirmed"] = False

    # SPY standalone seasonal info
    if oos_spy_s["sharpe"] > 0.5 and oos_spy_s["cumul"] > 1.2:
        print(f"\n  Note: Pure SPY seasonal IS valuable standalone: "
              f"Sharpe {oos_spy_s['sharpe']:.3f}  Cumul {oos_spy_s['cumul']:.4f}")

    out = RESULT_DIR / "h117_results.json"
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved → {out}")


if __name__ == "__main__":
    main()
