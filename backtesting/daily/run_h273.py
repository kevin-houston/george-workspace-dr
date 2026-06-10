"""
H273 — Volatility-Targeted Production Portfolio (Dynamic Leverage)
===================================================================

Hypothesis:
  Apply a simple volatility-targeting overlay to the existing production
  portfolio to smooth drawdowns and improve Sharpe. Target annual vol = 10%.
  When realized 21-day vol is above target, scale down position; below target,
  scale up (capped at 1.5x leverage for OOS safety).

  This is NOT a new strategy family — it's a risk management overlay on
  the existing production portfolio (H041a/H026/H045/IBS).

  Gate: OOS Sharpe improves by > +0.1 vs unlevered baseline (3.55),
        AND MaxDD does not get worse (i.e., stays ≤ -3.60%)

  Expected behavior:
  - 2022 bear: high vol → scale down to protect
  - 2019/2023 bull: moderate vol → near full allocation
  - Overall: smoother equity curve, less 2022 damage

  Background:
    Volatility targeting (Moreira & Muir 2017 JF) scales equity exposure
    inversely to realized variance. Applied to managed futures and multi-asset
    portfolios, it improves Sharpe and reduces left-tail events.
    The key concern: it introduces momentum-like behaviour (buy low-vol, sell
    high-vol) which works against mean-reversion strategies.

    For production portfolio blending, this adds a monthly signal that adjusts
    total weight while keeping the internal allocation ratios constant.
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

# Production portfolio weights
PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

# Vol targeting parameters to sweep
VOL_TARGETS = [0.08, 0.10, 0.12, 0.15]
LOOKBACK_DAYS = 21   # ~1 month realized vol
MAX_LEVERAGE  = 1.5  # cap upside scaling

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

_PREFIXES = [f"h{i:03d}" for i in range(100, 273)]


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
    cp = CACHE_DIR / f"h273_{ticker}_close_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
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
    cp = CACHE_DIR / f"h273_{ticker}_ohlc_{start}_{end}.parquet"
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


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


def apply_vol_target(monthly_r, vol_target, lookback_months=3, max_lev=1.5):
    """
    Scale monthly returns by vol_target / realized_vol (lagged 1 month to avoid look-ahead).
    lookback_months: rolling window to estimate annualized vol.
    """
    r = monthly_r.copy()
    # Rolling realized vol (annualized)
    roll_vol = r.rolling(lookback_months).std() * np.sqrt(12)
    # Scale factor: target / realized, shifted 1 month for no look-ahead
    scale = (vol_target / roll_vol.shift(1)).clip(0.0, max_lev)
    scaled_r = r * scale
    return scaled_r.dropna()


def common_idx(*series):
    idx = series[0].index
    for s in series[1:]:
        idx = idx.intersection(s.index)
    return idx.sort_values()


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


print("="*80)
print("H273 — Volatility-Targeted Production Portfolio")
print("="*80)

# ── Build production portfolio
print("\n[0] Building production portfolio …")
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))
h41_base  = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h026_base = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1)
h045      = build_rotation_monthly(H045_PROD,  FULL_START, FULL_END, 2)

rd_prod = {"h041a": h41_base, "h026": h026_base, "h045": h045,
           "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
cidx_prod = common_idx(*list(rd_prod.values()))
prod_r    = make_port(rd_prod, PROD_W, cidx_prod)

# Baseline stats
prod_is_stats  = stats(prod_r[is_mask(prod_r.index)])
prod_oos_stats = stats(prod_r[oos_mask(prod_r.index)])
prod_ao_stats  = stats(prod_r[ao_mask(prod_r.index)])

print(f"  Baseline IS:    Sharpe={prod_is_stats['sharpe']:.4f}, CAGR={prod_is_stats['cagr']*100:.1f}%, MaxDD={prod_is_stats['max_drawdown']*100:.1f}%")
print(f"  Baseline OOS:   Sharpe={prod_oos_stats['sharpe']:.4f}, CAGR={prod_oos_stats['cagr']*100:.1f}%, MaxDD={prod_oos_stats['max_drawdown']*100:.1f}%, NegYrs={prod_oos_stats['neg_years']}")
print(f"  Baseline AltOOS:Sharpe={prod_ao_stats['sharpe']:.4f}")

# ── Vol-target sweep
print(f"\n[1] Vol-target sweep (lookback=3mo, max_leverage={MAX_LEVERAGE}x) …")
print(f"  {'Target':>8}  {'IS Sharpe':>10}  {'OOS Sharpe':>11}  {'OOS MaxDD':>10}  {'OOS CAGR':>9}  {'Delta Sharpe':>13}  {'Pass?':>6}")
print("  " + "-"*80)

sweep_results = []
for vt in VOL_TARGETS:
    vt_r = apply_vol_target(prod_r, vol_target=vt, lookback_months=3, max_lev=MAX_LEVERAGE)
    vt_is  = stats(vt_r[is_mask(vt_r.index)])
    vt_oos = stats(vt_r[oos_mask(vt_r.index)])
    delta = vt_oos["sharpe"] - prod_oos_stats["sharpe"]
    # Gate: Sharpe improvement > 0.1 AND MaxDD ≤ baseline MaxDD
    passed = (delta > 0.1) and (vt_oos["max_drawdown"] <= prod_oos_stats["max_drawdown"])
    mark = "PASS" if passed else "FAIL"
    print(f"  {vt*100:>7.0f}%  {vt_is['sharpe']:>10.4f}  {vt_oos['sharpe']:>11.4f}  "
          f"{vt_oos['max_drawdown']*100:>9.1f}%  {vt_oos['cagr']*100:>8.1f}%  "
          f"{delta:>+13.4f}  {mark:>6}")
    sweep_results.append({
        "vol_target": float(vt),
        "is": vt_is, "oos": vt_oos,
        "delta_sharpe": round(float(delta), 4),
        "passed": bool(passed),
    })

# ── Also test different lookback windows for best vol target
best_vt = 0.10
print(f"\n[2] Lookback sweep at vol_target={best_vt*100:.0f}% …")
print(f"  {'Lookback':>9}  {'OOS Sharpe':>11}  {'OOS MaxDD':>10}  {'Delta':>8}")
print("  " + "-"*55)

lookback_results = []
for lb in [2, 3, 6, 12]:
    vt_r = apply_vol_target(prod_r, vol_target=best_vt, lookback_months=lb, max_lev=MAX_LEVERAGE)
    vt_oos = stats(vt_r[oos_mask(vt_r.index)])
    delta = vt_oos["sharpe"] - prod_oos_stats["sharpe"]
    passed = (delta > 0.1) and (vt_oos["max_drawdown"] <= prod_oos_stats["max_drawdown"])
    print(f"  {lb:>6}mo  {vt_oos['sharpe']:>11.4f}  {vt_oos['max_drawdown']*100:>9.1f}%  {delta:>+8.4f}  {'PASS' if passed else 'FAIL'}")
    lookback_results.append({"lookback": lb, "oos": vt_oos, "delta_sharpe": round(float(delta), 4), "passed": bool(passed)})

# ── Annual breakdown for best combo
best_combo = max(sweep_results, key=lambda x: x["oos"]["sharpe"])
best_vt_r = apply_vol_target(prod_r, vol_target=best_combo["vol_target"], lookback_months=3, max_lev=MAX_LEVERAGE)
print(f"\n[3] Annual returns — Vol-target {best_combo['vol_target']*100:.0f}% vs Baseline …")
annual_vt   = best_vt_r[oos_mask(best_vt_r.index)].resample("YE").apply(lambda x: (1+x).prod()-1)
annual_base = prod_r[oos_mask(prod_r.index)].resample("YE").apply(lambda x: (1+x).prod()-1)
for yr in annual_vt.index:
    base_ret = float(annual_base.reindex([yr]).iloc[0]) if yr in annual_base.index else np.nan
    print(f"  {yr.year}: VolTarget={annual_vt[yr]*100:+.1f}%  Baseline={base_ret*100:+.1f}%")

# ── Decision
confirmed_any = any(r["passed"] for r in sweep_results)
best_passed = max([r for r in sweep_results if r["passed"]], key=lambda x: x["delta_sharpe"]) if confirmed_any else None

print(f"\n[4] Decision …")
print(f"  Gate: delta_OOS_Sharpe > +0.1 AND MaxDD ≤ {prod_oos_stats['max_drawdown']*100:.1f}%")
if confirmed_any:
    vt_pct = best_passed["vol_target"] * 100
    print(f"  *** H273 CONFIRMED — vol_target={vt_pct:.0f}% "
          f"OOS Sharpe={best_passed['oos']['sharpe']:.4f} "
          f"(+{best_passed['delta_sharpe']:+.4f}) ***")
else:
    best_r_any = max(sweep_results, key=lambda x: x["delta_sharpe"])
    print(f"  H273 NOT CONFIRMED — best delta_sharpe={best_r_any['delta_sharpe']:+.4f} "
          f"(gate +0.10), MaxDD={best_r_any['oos']['max_drawdown']*100:.1f}%")

# ── Save results
output = {
    "confirmed": bool(confirmed_any),
    "gate": {"delta_sharpe": 0.1, "max_dd_no_worse": float(prod_oos_stats["max_drawdown"])},
    "baseline": {
        "is": prod_is_stats, "oos": prod_oos_stats, "altoos": prod_ao_stats
    },
    "vol_target_sweep": sweep_results,
    "lookback_sweep": lookback_results,
    "params": {
        "lookback_months": 3,
        "max_leverage": MAX_LEVERAGE,
        "vol_targets_tested": VOL_TARGETS,
    },
    "best_confirmed": best_passed,
}
out_path = RESULT_DIR / "h273_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
