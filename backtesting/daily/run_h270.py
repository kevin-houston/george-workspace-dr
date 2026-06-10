"""
H270 — Low-Volatility Anomaly: USMV/SPLV/XLU/SPHD as Satellite
================================================================

Hypothesis:
  Low-volatility ETFs (USMV, SPLV, XLU, SPHD) outperform on a risk-adjusted basis
  as standalone satellite strategies. Monthly rebalance. Rank by trailing 12m
  annualized volatility — lowest-vol ETF wins (inverse momentum = low-vol selection).

  Two variants:
    A) Pure lowest-vol selection from {USMV, SPLV, XLU, SPHD, BIL}
    B) Momentum + Low-Vol dual filter: must be top-3 12m momentum AND lowest 12m vol
       among qualified, else hold BIL (defensive)

  Framework: IS 2008-2017, OOS 2018-2025
  Gate: OOS Sharpe > 0.9 (satellite)
  Benchmark: SPY buy-and-hold for reference

Background:
  The low-volatility anomaly (Blitz & van Vliet 2007, Baker et al. 2011) shows
  low-beta/low-vol stocks outperform high-vol on risk-adjusted basis, violating
  CAPM. ETF vehicles like USMV (iShares Min Vol, Oct 2011) and SPLV (PowerShares
  Low Vol, May 2011) provide direct exposure.

  Key test: does a low-vol ETF rotation improve Sharpe vs pure momentum rotation?
  USMV/SPLV have limited history (2011+), so we also include XLU (1998) and SPHD.
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
FULL_END   = "2026-06-06"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_IS_END = "2012-12-31"
ALT_OOS_ST = "2013-01-01"
WF_WORST_MIN = 1.75

# Low-vol universe
LOW_VOL_UNIVERSE = ["USMV", "SPLV", "XLU", "SPHD", "BIL"]
# Extended universe for momentum pre-filter
EXTENDED_UNIVERSE = ["USMV", "SPLV", "XLU", "SPHD", "XLK", "XLF", "XLE", "XLV", "BIL"]

# Production portfolio weights (for correlation estimation)
PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

_PREFIXES = [f"h{i:03d}" for i in range(100, 270)]


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
    cp = CACHE_DIR / f"h270_{ticker}_close_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    print(f"  Downloading {ticker} daily close …")
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
    cp = CACHE_DIR / f"h270_{ticker}_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    XLK_PARAMS = (0.15, 0.90, 7, -0.010)
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
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r),"neg_years":0}
    eq   = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol  = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    # Negative years
    annual = r.resample("YE").apply(lambda x: (1+x).prod()-1)
    neg_years = int((annual < 0).sum())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r),"neg_years":neg_years}


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
    vol_12 = monthly_ret.rolling(12).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_12.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def build_lowvol_rotation(tickers, start, end, lookback=12):
    """Pure low-vol rotation: always hold lowest-vol non-BIL asset (unless all vol > BIL)."""
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_lb = monthly_ret.rolling(lookback).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(lookback) - 1
    rows = []
    for i in range(lookback, len(monthly_px)):
        vol_row = vol_lb.iloc[i].dropna()
        mom_row = mom_12.iloc[i].dropna()
        risky = [t for t in vol_row.index if t != "BIL"]
        if not risky:
            rows.append((monthly_px.index[i], monthly_ret.iloc[i].get("BIL", 0.0)))
            continue
        # Variant A: pure lowest-vol from risky assets (positive momentum required)
        pos_mom = [t for t in risky if mom_row.get(t, -1) > 0]
        if pos_mom:
            best = min(pos_mom, key=lambda t: vol_row.get(t, 99))
        else:
            best = "BIL"
        rows.append((monthly_px.index[i], monthly_ret.iloc[i].get(best, 0.0)))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def build_lowvol_rotation_strict(tickers, start, end, lookback=12):
    """Variant B: pick absolute lowest-vol regardless of momentum sign."""
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_lb = monthly_ret.rolling(lookback).std() * np.sqrt(12)
    rows = []
    for i in range(lookback, len(monthly_px)):
        vol_row = vol_lb.iloc[i].dropna()
        risky = [t for t in vol_row.index if t != "BIL"]
        if not risky:
            rows.append((monthly_px.index[i], monthly_ret.iloc[i].get("BIL", 0.0)))
            continue
        best = min(risky, key=lambda t: vol_row.get(t, 99))
        rows.append((monthly_px.index[i], monthly_ret.iloc[i].get(best, 0.0)))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


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


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


print("="*80)
print("H270 — Low-Volatility Anomaly: USMV/SPLV/XLU/SPHD Rotation")
print("="*80)

# ── Build production portfolio baseline (for correlation)
print("\n[0] Building baseline production portfolio components …")
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))
h41_base  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h026_base = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1)
h045      = build_rotation_monthly(H045_PROD,  FULL_START, FULL_END, 2)

# SPY buy-and-hold as benchmark
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_monthly = spy_close.resample("ME").last().pct_change().dropna()

rd_prod = {"h041a": h41_base, "h026": h026_base, "h045": h045,
           "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
cidx_prod = common_idx(*list(rd_prod.values()))
prod_oos_r = make_port(rd_prod, PROD_W, cidx_prod[oos_mask(cidx_prod)])
prod_stats = stats(prod_oos_r)
print(f"  Production OOS: Sharpe={prod_stats['sharpe']:.4f}, CAGR={prod_stats['cagr']*100:.1f}%")

# SPY stats
spy_oos = spy_monthly[oos_mask(spy_monthly.index)]
spy_stats = stats(spy_oos)
print(f"  SPY OOS:        Sharpe={spy_stats['sharpe']:.4f}, CAGR={spy_stats['cagr']*100:.1f}%")

# ── Variant A: Low-vol rotation (momentum-gated)
print("\n[1] Variant A — Low-vol rotation with positive momentum gate (USMV/SPLV/XLU/SPHD/BIL) …")
lva_r = build_lowvol_rotation(LOW_VOL_UNIVERSE, FULL_START, FULL_END, lookback=12)
lva_is  = stats(lva_r[is_mask(lva_r.index)])
lva_oos = stats(lva_r[oos_mask(lva_r.index)])
lva_ao  = stats(lva_r[ao_mask(lva_r.index)])
print(f"  IS  Sharpe={lva_is['sharpe']:.4f}, CAGR={lva_is['cagr']*100:.1f}%, MaxDD={lva_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={lva_oos['sharpe']:.4f}, CAGR={lva_oos['cagr']*100:.1f}%, MaxDD={lva_oos['max_drawdown']*100:.1f}%, NegYrs={lva_oos['neg_years']}")
print(f"  AltOOS Sharpe={lva_ao['sharpe']:.4f}")

# Corr with SPY OOS
common_lva_spy = lva_r.index.intersection(spy_monthly.index)
corr_lva_spy = lva_r.reindex(common_lva_spy).corr(spy_monthly.reindex(common_lva_spy))
print(f"  Corr(SPY) OOS region: {corr_lva_spy:.4f}")

# ── Variant B: Pure lowest-vol selection (no momentum gate)
print("\n[2] Variant B — Pure lowest-vol rotation (no momentum gate) …")
lvb_r = build_lowvol_rotation_strict(LOW_VOL_UNIVERSE, FULL_START, FULL_END, lookback=12)
lvb_is  = stats(lvb_r[is_mask(lvb_r.index)])
lvb_oos = stats(lvb_r[oos_mask(lvb_r.index)])
lvb_ao  = stats(lvb_r[ao_mask(lvb_r.index)])
print(f"  IS  Sharpe={lvb_is['sharpe']:.4f}, CAGR={lvb_is['cagr']*100:.1f}%, MaxDD={lvb_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={lvb_oos['sharpe']:.4f}, CAGR={lvb_oos['cagr']*100:.1f}%, MaxDD={lvb_oos['max_drawdown']*100:.1f}%, NegYrs={lvb_oos['neg_years']}")
print(f"  AltOOS Sharpe={lvb_ao['sharpe']:.4f}")

# ── Variant C: Momentum+Vol dual signal (rank by mom - vol_zscore)
print("\n[3] Variant C — Momentum-minus-vol dual ranking (USMV/SPLV/XLU/SPHD/XLK/XLF/XLE/XLV/BIL) …")
lvc_r = build_rotation_monthly(EXTENDED_UNIVERSE, FULL_START, FULL_END, n_hold=1)
lvc_is  = stats(lvc_r[is_mask(lvc_r.index)])
lvc_oos = stats(lvc_r[oos_mask(lvc_r.index)])
lvc_ao  = stats(lvc_r[ao_mask(lvc_r.index)])
print(f"  IS  Sharpe={lvc_is['sharpe']:.4f}, CAGR={lvc_is['cagr']*100:.1f}%, MaxDD={lvc_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={lvc_oos['sharpe']:.4f}, CAGR={lvc_oos['cagr']*100:.1f}%, MaxDD={lvc_oos['max_drawdown']*100:.1f}%, NegYrs={lvc_oos['neg_years']}")
print(f"  AltOOS Sharpe={lvc_ao['sharpe']:.4f}")

# ── Pure XLU standalone (longest history low-vol proxy)
print("\n[4] XLU standalone buy-and-hold (low-vol proxy, 1999+) …")
xlu_close = fetch_daily_close("XLU", FULL_START, FULL_END)
xlu_monthly = xlu_close.resample("ME").last().pct_change().dropna()
xlu_is  = stats(xlu_monthly[is_mask(xlu_monthly.index)])
xlu_oos = stats(xlu_monthly[oos_mask(xlu_monthly.index)])
print(f"  IS  Sharpe={xlu_is['sharpe']:.4f}, CAGR={xlu_is['cagr']*100:.1f}%, MaxDD={xlu_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={xlu_oos['sharpe']:.4f}, CAGR={xlu_oos['cagr']*100:.1f}%, MaxDD={xlu_oos['max_drawdown']*100:.1f}%, NegYrs={xlu_oos['neg_years']}")

# ── USMV standalone (purest low-vol ETF, 2011+)
print("\n[5] USMV standalone buy-and-hold (purest min-vol ETF) …")
usmv_close = fetch_daily_close("USMV", FULL_START, FULL_END)
usmv_monthly = usmv_close.resample("ME").last().pct_change().dropna()
usmv_is  = stats(usmv_monthly[is_mask(usmv_monthly.index)])
usmv_oos = stats(usmv_monthly[oos_mask(usmv_monthly.index)])
print(f"  IS  Sharpe={usmv_is['sharpe']:.4f}, CAGR={usmv_is['cagr']*100:.1f}%, MaxDD={usmv_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={usmv_oos['sharpe']:.4f}, CAGR={usmv_oos['cagr']*100:.1f}%, MaxDD={usmv_oos['max_drawdown']*100:.1f}%, NegYrs={usmv_oos['neg_years']}")

# ── Correlation with production portfolio
print("\n[6] Correlation analysis (OOS) …")
best_var = max([(lva_r, lva_oos, "Variant A"), (lvb_r, lvb_oos, "Variant B"), (lvc_r, lvc_oos, "Variant C")],
               key=lambda x: x[1]["sharpe"])
best_r, best_stats, best_name = best_var

prod_oos_full = make_port(rd_prod, PROD_W, cidx_prod)
oos_idx = cidx_prod[oos_mask(cidx_prod)]
common_oos = best_r.index.intersection(oos_idx)
corr_prod = best_r.reindex(common_oos).corr(prod_oos_r.reindex(common_oos))
corr_spy  = best_r.reindex(common_oos).corr(spy_monthly.reindex(common_oos))
print(f"  Best variant: {best_name}, OOS Sharpe={best_stats['sharpe']:.4f}")
print(f"  Corr(Production) OOS: {corr_prod:.4f}")
print(f"  Corr(SPY) OOS:        {corr_spy:.4f}")

# ── Decision
print("\n[7] Decision …")
gate = 0.9
best_sharpe = best_stats["sharpe"]
confirmed = best_sharpe >= gate
print(f"  Gate: OOS Sharpe > {gate}")
print(f"  Best OOS Sharpe: {best_sharpe:.4f} ({'PASS' if confirmed else 'FAIL'})")
if confirmed:
    print(f"  *** H270 CONFIRMED — Low-vol rotation ({best_name}) OOS Sharpe={best_sharpe:.4f} ***")
else:
    print(f"  H270 NOT CONFIRMED — best OOS Sharpe {best_sharpe:.4f} < gate {gate}")

# ── Save results
output = {
    "confirmed": bool(confirmed),
    "gate_sharpe": float(gate),
    "variant_a": {"is": lva_is, "oos": lva_oos, "altoos": lva_ao},
    "variant_b": {"is": lvb_is, "oos": lvb_oos, "altoos": lvb_ao},
    "variant_c": {"is": lvc_is, "oos": lvc_oos, "altoos": lvc_ao},
    "xlu_bh":  {"is": xlu_is,  "oos": xlu_oos},
    "usmv_bh": {"is": usmv_is, "oos": usmv_oos},
    "spy_oos":  spy_stats,
    "best_variant": best_name,
    "best_oos_sharpe": float(best_sharpe),
    "corr_production": float(corr_prod),
    "corr_spy": float(corr_spy),
}
out_path = RESULT_DIR / "h270_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
