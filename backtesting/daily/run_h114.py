"""
H114 — ETF Pairs Trading (§3.8, 151 Strategies)
================================================

Thesis: Cointegrated ETF pairs mean-revert around a stable equilibrium.
A z-score of the log price ratio provides a timing signal. The strategy
is MARKET-NEUTRAL (long/short), so it should be uncorrelated with the
existing directional portfolio.

Implementation:
  - Monthly rebalance on z-score of log(P1/P2)
  - Lookback: 12-month rolling mean and std
  - Entry: |z| > 1.5 standard deviations
  - Exit: |z| < 0.5 standard deviations
  - Dollar-neutral (50% long, 50% short)
  - Return = return(long leg) - return(short leg)

Candidate pairs:
  1. GDX/SIL   — gold miners vs silver miners (highest cointegration expected)
  2. XLE/OIH   — energy sector vs oil services ETF
  3. TLT/IEF   — 20yr vs 7-10yr Treasuries (pure rate-level spread)
  4. EWJ/EWH   — Japan vs Hong Kong (Asian equity relative value)
  5. XLK/QQQ   — S&P Tech sector vs NASDAQ 100 (very tight)

Evaluation:
  - Standalone IS/OOS/AltOOS Sharpe and CAGR for each pair
  - Correlation with production blend (market-neutral ≠ correlated?)
  - Best-pair blend test (add top-pair at 10-15% weight)

Production baseline: OOS 4.1577, AltOOS 4.0612, MaxDD -3.60%
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy import stats as scipy_stats

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

# Pairs to test: (asset1, asset2, label, rationale)
PAIRS = [
    ("GDX", "SIL",  "GDX/SIL",  "Gold miners vs silver miners"),
    ("XLE", "OIH",  "XLE/OIH",  "Energy sector vs oil services"),
    ("TLT", "IEF",  "TLT/IEF",  "20yr vs 7-10yr Treasuries"),
    ("EWJ", "EWH",  "EWJ/EWH",  "Japan vs Hong Kong equities"),
    ("XLK", "QQQ",  "XLK/QQQ",  "S&P Tech sector vs NASDAQ 100"),
]

PAIRS_PARAMS = {
    "entry_z": 1.5,   # enter when |z| > entry_z
    "exit_z":  0.5,   # exit when |z| < exit_z
    "lookback": 12,   # months for rolling z-score
}

# H112 production weights (for blend/correlation test)
H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
IBS_TOTAL  = 0.30
PROD_W     = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
              "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

_PREFIXES = [f"h{i:03d}" for i in range(62, 114)]


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suf in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suf}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h114_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h114_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


# ── Pairs trading engine ──────────────────────────────────────────────────────

def build_pairs_monthly(t1, t2, start, end, entry_z=1.5, exit_z=0.5, lookback=12):
    """
    Monthly pairs mean-reversion.
    Returns monthly return series of the long-short strategy.
    """
    p1 = fetch_daily_close(t1, start, end)
    p2 = fetch_daily_close(t2, start, end)

    # Align and compute monthly closes
    daily = pd.DataFrame({t1: p1, t2: p2}).dropna()
    monthly = daily.resample("ME").last()
    monthly_ret = daily.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    # Log price ratio (spread)
    log_ratio = np.log(monthly[t1] / monthly[t2])

    # Rolling z-score
    roll_mean = log_ratio.rolling(lookback).mean()
    roll_std  = log_ratio.rolling(lookback).std()
    z = (log_ratio - roll_mean) / roll_std

    # Signal: +1 = long t1/short t2 (spread wide below mean → t1 cheap)
    #          -1 = short t1/long t2 (spread wide above mean → t1 expensive)
    #           0 = flat
    position = 0
    rows = []
    for i in range(lookback, len(z)):
        z_val = float(z.iloc[i])
        if np.isnan(z_val):
            rows.append((monthly.index[i], 0.0))
            continue

        # Exit if we're in position and z has reverted
        if position != 0 and abs(z_val) < exit_z:
            position = 0

        # Entry
        if position == 0:
            if z_val > entry_z:    # spread too high → short t1, long t2
                position = -1
            elif z_val < -entry_z: # spread too low → long t1, short t2
                position = 1

        # Compute return: position * (ret_t1 - ret_t2)
        r1 = float(monthly_ret[t1].iloc[i])
        r2 = float(monthly_ret[t2].iloc[i])
        if np.isnan(r1) or np.isnan(r2):
            rows.append((monthly.index[i], 0.0))
            continue

        pair_ret = position * (r1 - r2)  # dollar-neutral spread return
        rows.append((monthly.index[i], pair_ret))

    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def cointegration_test(t1, t2, start, end):
    """
    Engle-Granger cointegration test on log price ratio.
    Returns ADF statistic, p-value, and critical values.
    """
    p1 = fetch_daily_close(t1, start, end)
    p2 = fetch_daily_close(t2, start, end)
    daily = pd.DataFrame({t1: p1, t2: p2}).dropna()
    monthly = daily.resample("ME").last()
    log_ratio = np.log(monthly[t1] / monthly[t2])
    # ADF test on the spread (test for stationarity)
    adf_stat, p_val, _, _, cv, _ = scipy_stats.spearmanr(  # use own ADF
        log_ratio.diff().dropna(), log_ratio.shift(1).dropna()
    )
    # Simple manual ADF: regression of Δy on y_{t-1}
    y = log_ratio.dropna().values
    dy = np.diff(y)
    y_lag = y[:-1]
    # OLS: dy = alpha + beta * y_lag
    X = np.vstack([np.ones(len(y_lag)), y_lag]).T
    beta = np.linalg.lstsq(X, dy, rcond=None)[0]
    resid = dy - X @ beta
    se = np.sqrt(np.sum(resid**2) / (len(resid) - 2)) * np.sqrt(np.linalg.inv(X.T @ X)[1,1])
    adf_t = beta[1] / se
    return adf_t, len(log_ratio)


# ── Stats and eval helpers ────────────────────────────────────────────────────

def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0}
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),"max_drawdown":round(max_dd,4)}


def build_rotation_monthly(tickers, start, end, n_hold=1):
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
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold: continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom = (df["high"]-df["low"]).replace(0, np.nan)
    ibs = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"]-prev_cl)/prev_cl
    equity = INITIAL_EQUITY; position = days_held = 0; series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1]); cur_ibs = float(ibs.iloc[i])
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


def build_production_blend(start, end):
    h041a = build_rotation_monthly(H041A_FULL, start, end, n_hold=1)
    h026  = build_rotation_monthly(H026_ASSETS, start, end, n_hold=1)
    h045  = build_rotation_monthly(H045_PROD, start, end, n_hold=2)
    xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",start,end), *XLK_PARAMS))
    smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",start,end), *SMH_PARAMS))
    igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",start,end), *IGV_PARAMS))
    xlk_s = PROD_W["XLK"]/IBS_TOTAL; smh_s = PROD_W["SMH"]/IBS_TOTAL; igv_s = PROD_W["IGV"]/IBS_TOTAL
    ibs_r = xlk_r*xlk_s + smh_r.reindex(xlk_r.index).fillna(0)*smh_s + igv_r.reindex(xlk_r.index).fillna(0)*igv_s
    idx = h041a.index.intersection(h026.index).intersection(h045.index).intersection(ibs_r.index)
    return (h041a[idx]*PROD_W["h041a"] + h026[idx]*PROD_W["h026"] +
            h045[idx]*PROD_W["h045"] + ibs_r[idx]*IBS_TOTAL)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    p = PAIRS_PARAMS
    print("="*70)
    print("H114 — ETF Pairs Trading Mean-Reversion")
    print(f"Entry |z|>{p['entry_z']}  Exit |z|<{p['exit_z']}  Lookback={p['lookback']}mo")
    print("="*70)

    # Run all pairs
    pair_results = {}
    pair_returns  = {}

    for t1, t2, label, rationale in PAIRS:
        print(f"\n── {label}: {rationale}")

        # Cointegration check
        try:
            adf_t, n_obs = cointegration_test(t1, t2, FULL_START, FULL_END)
            coint_flag = "✓ stationary" if adf_t < -2.5 else "~ borderline" if adf_t < -1.5 else "✗ non-stationary"
            print(f"   ADF t-stat: {adf_t:.3f} ({n_obs} obs) → {coint_flag}")
        except Exception as e:
            print(f"   Cointegration test failed: {e}")
            adf_t = 0.0

        # Pairs returns
        r = build_pairs_monthly(t1, t2, FULL_START, FULL_END,
                                 p["entry_z"], p["exit_z"], p["lookback"])

        is_r  = r[(r.index >= IS_START) & (r.index <= IS_END)]
        oos_r = r[r.index >= OOS_START]
        alt_r = r[r.index >= ALT_OOS_ST]
        is_s  = stats(is_r);  oos_s = stats(oos_r); alt_s = stats(alt_r)

        eq_oos = float((1+oos_r).cumprod().iloc[-1]) if len(oos_r) > 0 else 1.0
        eq_alt = float((1+alt_r).cumprod().iloc[-1]) if len(alt_r) > 0 else 1.0
        neg_oos = sum(1 for y, g in oos_r.groupby(oos_r.index.year) if (1+g).prod()-1 < 0)

        # Active fraction (not in cash)
        active_frac = float((r != 0).mean())
        long_frac  = float((r > 0.001).mean())
        short_frac = float((r < -0.001).mean())

        print(f"   IS  {IS_START[:4]}-{IS_END[:4]}: Sharpe {is_s['sharpe']:+.3f}  CAGR {is_s['cagr']*100:+.1f}%  MaxDD {is_s['max_drawdown']*100:.1f}%")
        print(f"   OOS {OOS_START[:4]}-2026:       Sharpe {oos_s['sharpe']:+.3f}  CAGR {oos_s['cagr']*100:+.1f}%  Cumul {eq_oos:.4f}  NegYrs={neg_oos}")
        print(f"   Alt {ALT_OOS_ST[:4]}-2026:      Sharpe {alt_s['sharpe']:+.3f}  CAGR {alt_s['cagr']*100:+.1f}%  Cumul {eq_alt:.4f}")
        print(f"   Active: {active_frac:.1%}  (Long: {long_frac:.1%}, Short: {short_frac:.1%})")

        pair_results[label] = {
            "is": is_s, "oos": oos_s, "alt": alt_s,
            "eq_oos": round(eq_oos, 4), "eq_alt": round(eq_alt, 4),
            "adf_t": round(adf_t, 3), "neg_oos": neg_oos,
            "active_frac": round(active_frac, 3),
        }
        pair_returns[label] = r

    # ── Correlation with production blend ────────────────────────────────
    print("\n── Correlation with production blend")
    print("   Building production blend (H112 weights)…\n")

    blend = build_production_blend(FULL_START, FULL_END)

    best_pair = None; best_corr = 1.0; best_oos = 0.0

    for label, r in pair_returns.items():
        oos_r = r[r.index >= OOS_START]
        blend_oos = blend[blend.index >= OOS_START]
        idx = oos_r.index.intersection(blend_oos.index)
        if len(idx) < 12:
            print(f"   {label}: insufficient overlap")
            continue
        corr = float(oos_r[idx].corr(blend_oos[idx]))
        oos_sharpe = pair_results[label]["oos"]["sharpe"]
        print(f"   {label}: corr={corr:+.3f}  OOS Sharpe={oos_sharpe:+.3f}  OOS Cumul={pair_results[label]['eq_oos']:.4f}")
        pair_results[label]["corr_vs_blend_oos"] = round(corr, 3)

        # Track best candidate: high Sharpe + low correlation + decent cumul
        score = oos_sharpe - abs(corr) * 2
        if score > best_oos and pair_results[label]["eq_oos"] > 1.0:
            best_pair = label; best_oos = score; best_corr = corr

    # ── Best pair blend test ─────────────────────────────────────────────
    if best_pair:
        print(f"\n── Blend test: production (90%) + {best_pair} (10%)")
        r_best = pair_returns[best_pair]
        idx = blend.index.intersection(r_best.index)
        blend_plus = blend[idx] * 0.90 + r_best[idx] * 0.10

        for window, label, start in [
            (OOS_START, "OOS", "2018"), (ALT_OOS_ST, "Alt", "2013")
        ]:
            b_r  = blend[blend.index >= window]
            bp_r = blend_plus[blend_plus.index >= window]
            b_c  = float((1+b_r).cumprod().iloc[-1])
            bp_c = float((1+bp_r).cumprod().iloc[-1])
            b_s  = stats(b_r)["sharpe"]; bp_s = stats(bp_r)["sharpe"]
            print(f"   {label}: base cumul={b_c:.4f} Sharpe={b_s:.3f}  +{best_pair} 10%: cumul={bp_c:.4f} Sharpe={bp_s:.3f}  Δ={bp_c-b_c:+.4f}")
    else:
        print("\n   No pair qualified for blend test (all cumul < 1.0 or negative Sharpe)")
        blend_plus = None

    # ── Verdict ─────────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("VERDICT")
    print("="*70)

    # Rank pairs by OOS Sharpe
    ranked = sorted(pair_results.items(), key=lambda x: x[1]["oos"]["sharpe"], reverse=True)
    print("\n  Pairs ranked by OOS Sharpe:")
    for label, res in ranked:
        corr = res.get("corr_vs_blend_oos", float("nan"))
        print(f"    {label:<10} Sharpe {res['oos']['sharpe']:+.3f}  Cumul {res['eq_oos']:.4f}  "
              f"Corr {corr:+.3f}  NegYrs {res['neg_oos']}")

    # Best confirmed candidate
    top_label, top_res = ranked[0]
    verdict = ""
    if top_res["oos"]["sharpe"] > 0.5 and top_res["eq_oos"] > 1.2:
        corr = top_res.get("corr_vs_blend_oos", 1.0)
        if abs(corr) < 0.4:
            verdict = f"CONFIRMED — {top_label} has positive OOS edge + low correlation; candidate for production blend"
        elif abs(corr) < 0.7:
            verdict = f"MARGINAL — {top_label} has edge but moderate correlation ({corr:.2f}); limited portfolio benefit"
        else:
            verdict = f"NOT ADDITIVE — {top_label} is correlated with production ({corr:.2f})"
    else:
        verdict = "NOT CONFIRMED — no pair shows sufficient standalone OOS edge (Sharpe>0.5, Cumul>1.2)"

    print(f"\n  → {verdict}")

    result = {
        "h114": {
            "pairs": {k: {kk: vv for kk, vv in v.items() if kk not in ["is","oos","alt"]}
                      for k, v in pair_results.items()},
            "best_pair": best_pair,
            "verdict": verdict,
        }
    }
    out = RESULT_DIR / "h114_results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  Results saved → {out}")


if __name__ == "__main__":
    main()
