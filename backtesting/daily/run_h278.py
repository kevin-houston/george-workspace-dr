"""
H278 — Low-Vol Anomaly: Volatility-Parity ETF Portfolio
=========================================================

Hypothesis:
  Volatility-parity (inverse-vol) weighting of a 9-ETF universe outperforms
  H270's dual-ranking (momentum+low-vol) approach.

  H270 CONFIRMED with OOS Sharpe=1.290 using dual-ranking (Variant C, 9-asset universe).
  H278 tests whether replacing the selection-and-hold-1 step with inverse-vol weights
  across all assets (always invested, no BIL defensive) is a superior approach.

  Three variants:
    A) Inverse-vol weights on 8 risky ETFs (no BIL) — always invested
    B) Inverse-vol weights with BIL as 9th asset — allows defensive tilt
    C) Inverse-vol weights with momentum filter: exclude ETFs with negative 6m momentum
       (weight zeroed, redistributed proportionally to remaining ETFs or BIL)
    D) Risk-parity-style: normalize weights to target 10% annual portfolio vol
       (vol targeting layer on top of Var A)

  Universe (same as H270 Variant C):
    USMV, SPLV, XLU, SPHD, XLK, XLF, XLE, XLV, BIL

  Framework: IS 2008-2017, OOS 2018-present
  Gates:
    Confirmation: OOS Sharpe > 1.0 AND OOS Sharpe > H270 Var C baseline (1.290)
    Production-additive: Corr(H278, production) < 0.6

Background:
  Volatility parity / risk parity (Bridgewater All Weather) allocates weight proportional
  to 1/vol(i) — each asset contributes equal risk, not equal capital. This naturally
  overweights low-vol ETFs (USMV/SPLV/XLU) vs high-vol (XLE/XLF).

  Comparison with H270:
    H270 Var C: select top-1 by (momentum_rank + inv_vol_rank), hold 1 month, BIL if none qualify
    H278: hold ALL assets with inverse-vol weights, rebalance monthly

  H278 removes concentration risk (always 1 winner) in favor of diversified low-vol tilt.
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

# Same universe as H270 Var C (confirmed)
UNIVERSE = ["USMV", "SPLV", "XLU", "SPHD", "XLK", "XLF", "XLE", "XLV", "BIL"]
RISKY    = ["USMV", "SPLV", "XLU", "SPHD", "XLK", "XLF", "XLE", "XLV"]

# Production components for correlation
H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_XLK_PARAMS = (0.15, 0.90, 7, -0.010)
IBS_SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IBS_IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

_PREFIXES = [f"h{i:03d}" for i in range(100, 278)]


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df, pd.DataFrame):
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns:
                        return df["close"].rename(ticker)
                else:
                    return df.squeeze().rename(ticker)
    cp = CACHE_DIR / f"h278_{ticker}_close_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if raw.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def fetch_ohlc(ticker, start, end):
    for pfx in _PREFIXES:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h278_{ticker}_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
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
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp_val = float(df["close"].iloc[i-1])
        ret_oc = (c/o-1) if o > 0 else 0.0
        ret_cc = (c/cp_val-1) if cp_val > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1+ret_oc)
        else:
            days_held += 1; equity *= (1+ret_cc)
            cur_ibs = float(ibs.iloc[i])
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _,v in series], index=pd.DatetimeIndex([d for d,_ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


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


def build_inv_vol_portfolio(tickers, all_tickers_data, lookback_months=6,
                            use_bil_defensive=False, momentum_filter=False,
                            vol_target=None):
    """
    Build inverse-volatility-weighted portfolio.

    lookback_months: rolling window for vol estimation
    use_bil_defensive: if True, BIL is included as a defensive asset
    momentum_filter: if True, zero out assets with negative 6m momentum
    vol_target: if float, scale leverage to target this annualized vol

    Returns monthly return series.
    """
    # Get daily and monthly data
    valid_tickers = [t for t in tickers if t in all_tickers_data]
    daily_df = pd.DataFrame({t: all_tickers_data[t] for t in valid_tickers}).sort_index()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    monthly_px  = daily_df.resample("ME").last()

    rows = []
    weights_log = []

    for i in range(lookback_months + 1, len(monthly_ret)):
        # Rolling vol (annualized) using past lookback_months
        vol_window = monthly_ret.iloc[i-lookback_months:i]
        vols = vol_window.std(ddof=1) * np.sqrt(12)

        # Compute inverse vol weights
        inv_vols = 1.0 / vols.replace(0, np.nan)
        inv_vols = inv_vols.dropna()

        if use_bil_defensive:
            # BIL gets very low vol (near 0) → huge inverse vol weight
            # Cap BIL weight at 30% to prevent degenerate allocation
            risky_tickers = [t for t in inv_vols.index if t != "BIL"]
            bil_weight = min(0.30, inv_vols.get("BIL", 0) / inv_vols.sum())
            if "BIL" in inv_vols.index:
                risky_inv_vols = inv_vols[risky_tickers]
                if risky_inv_vols.sum() > 0:
                    risky_weights = risky_inv_vols / risky_inv_vols.sum() * (1 - bil_weight)
                    weights = risky_weights.copy()
                    weights["BIL"] = bil_weight
                else:
                    weights = pd.Series({"BIL": 1.0})
            else:
                weights = inv_vols / inv_vols.sum()
        else:
            # All risky assets, normalize
            risky = [t for t in inv_vols.index if t != "BIL"]
            inv_vols_risky = inv_vols[risky]
            if inv_vols_risky.sum() == 0:
                continue
            weights = inv_vols_risky / inv_vols_risky.sum()

        # Momentum filter: zero out negative 6m momentum assets
        if momentum_filter and i >= 7:
            px_now   = monthly_px.iloc[i-1]
            px_6ago  = monthly_px.iloc[i-7]
            mom_6 = (px_now / px_6ago - 1)
            for t in weights.index:
                if t != "BIL" and t in mom_6.index and mom_6[t] < 0:
                    weights[t] = 0.0
            if "BIL" in monthly_ret.columns:
                # Redistribute zeroed weight to BIL
                zeroed = (weights == 0).sum()
                if zeroed > 0:
                    total_w = weights.sum()
                    if total_w > 0:
                        weights = weights / total_w
            else:
                total_w = weights.sum()
                if total_w > 0:
                    weights = weights / total_w
                else:
                    # All momentum negative → equal-weight remaining
                    weights = pd.Series({t: 1.0/len(weights) for t in weights.index})

        # Normalize to sum to 1
        if weights.sum() > 0:
            weights = weights / weights.sum()

        # Vol targeting: scale to target_vol
        if vol_target is not None:
            port_vol = float((vol_window * weights.reindex(vol_window.columns, fill_value=0)).sum(axis=1).std(ddof=1) * np.sqrt(12))
            if port_vol > 0:
                lev = min(vol_target / port_vol, 2.0)  # cap leverage at 2x
                weights = weights * lev
                # Excess cash earns 0 (we don't model explicitly)

        # Apply weights to next month's returns
        next_ret = monthly_ret.iloc[i]
        avail = weights.index.intersection(next_ret.index)
        if len(avail) == 0:
            continue
        port_ret = float((weights.reindex(avail) * next_ret.reindex(avail)).sum())
        rows.append((monthly_ret.index[i], port_ret))
        weights_log.append({"date": str(monthly_ret.index[i].date()), "weights": weights.round(3).to_dict()})

    if not rows:
        return pd.Series(dtype=float), []
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows])), weights_log


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


def corr_with_series(r1, r2):
    idx = r1.index.intersection(r2.index)
    if len(idx) < 12:
        return float("nan")
    return float(r1.reindex(idx).corr(r2.reindex(idx)))


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


# ── main ─────────────────────────────────────────────────────────────────────

print("="*80)
print("H278 — Low-Vol Anomaly: Volatility-Parity ETF Portfolio")
print("="*80)

print("\n[0] Loading universe data …")
universe_data = {}
for t in UNIVERSE:
    try:
        universe_data[t] = fetch_daily_close(t, FULL_START, FULL_END)
        print(f"  {t}: OK")
    except Exception as e:
        print(f"  {t}: {e}")

print("\n[0b] Building production baseline …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*IBS_XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*IBS_SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IBS_IGV_PARAMS))
h041a = build_rotation_monthly(H041A_FULL,  FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_BASE,   FULL_START, FULL_END, 1)
h045  = build_rotation_monthly(H045_PROD,   FULL_START, FULL_END, 2)

def prod_blend(h41_r, h26_r, h45_r, xlk, smh, igv):
    idx = h41_r.index
    for s in [h26_r, h45_r, xlk, smh, igv]:
        idx = idx.intersection(s.index)
    idx = idx.sort_values()
    return (0.22*h41_r.reindex(idx) + 0.27*h26_r.reindex(idx) + 0.21*h45_r.reindex(idx)
            + 0.20*xlk.reindex(idx) + 0.08*smh.reindex(idx) + 0.02*igv.reindex(idx))

prod_r = prod_blend(h041a, h026, h045, xlk_r, smh_r, igv_r)
prod_oos = prod_r[oos_mask(prod_r.index)]
print(f"  Production OOS Sharpe: {stats(prod_oos)['sharpe']:.4f}")

# H270 Var C baseline (confirmed: OOS Sharpe 1.290)
H270_BASELINE = 1.290

# ── Variant A: Inverse vol, risky assets only (no BIL) ──────────────────────
print("\n[1] Variant A — inverse-vol weights, risky ETFs only (no defensive) …")
var_a, wlog_a = build_inv_vol_portfolio(
    RISKY, universe_data, lookback_months=6,
    use_bil_defensive=False, momentum_filter=False)
s_a_is  = stats(var_a[is_mask(var_a.index)])
s_a_oos = stats(var_a[oos_mask(var_a.index)])
corr_a_prod = corr_with_series(var_a[oos_mask(var_a.index)], prod_oos)
corr_a_spy  = corr_with_series(var_a[oos_mask(var_a.index)],
    pd.Series([(v/p - 1) for v,p in zip(
        pd.DataFrame(universe_data).resample("ME").last()["XLK"].values[1:],
        pd.DataFrame(universe_data).resample("ME").last()["XLK"].values[:-1])]))
print(f"  IS:  Sharpe={s_a_is['sharpe']:.4f}  CAGR={s_a_is['cagr']*100:.1f}%  MaxDD={s_a_is['max_drawdown']*100:.1f}%")
print(f"  OOS: Sharpe={s_a_oos['sharpe']:.4f}  CAGR={s_a_oos['cagr']*100:.1f}%  MaxDD={s_a_oos['max_drawdown']*100:.1f}%  NegYrs={s_a_oos['neg_years']}")
print(f"  Corr(prod)={corr_a_prod:.3f}")

# ── Variant B: Inverse vol with BIL as 9th asset (capped at 30%) ────────────
print("\n[2] Variant B — inverse-vol weights, BIL included (capped 30%) …")
var_b, wlog_b = build_inv_vol_portfolio(
    UNIVERSE, universe_data, lookback_months=6,
    use_bil_defensive=True, momentum_filter=False)
s_b_is  = stats(var_b[is_mask(var_b.index)])
s_b_oos = stats(var_b[oos_mask(var_b.index)])
corr_b_prod = corr_with_series(var_b[oos_mask(var_b.index)], prod_oos)
print(f"  IS:  Sharpe={s_b_is['sharpe']:.4f}  CAGR={s_b_is['cagr']*100:.1f}%  MaxDD={s_b_is['max_drawdown']*100:.1f}%")
print(f"  OOS: Sharpe={s_b_oos['sharpe']:.4f}  CAGR={s_b_oos['cagr']*100:.1f}%  MaxDD={s_b_oos['max_drawdown']*100:.1f}%  NegYrs={s_b_oos['neg_years']}")
print(f"  Corr(prod)={corr_b_prod:.3f}")

# ── Variant C: Inverse vol + momentum filter ─────────────────────────────────
print("\n[3] Variant C — inverse-vol weights + 6m momentum filter (exclude neg-mom assets) …")
var_c, wlog_c = build_inv_vol_portfolio(
    RISKY, universe_data, lookback_months=6,
    use_bil_defensive=False, momentum_filter=True)
# Add BIL when momentum filter is active
var_c_bil, _ = build_inv_vol_portfolio(
    UNIVERSE, universe_data, lookback_months=6,
    use_bil_defensive=True, momentum_filter=True)
s_c_is   = stats(var_c[is_mask(var_c.index)])
s_c_oos  = stats(var_c[oos_mask(var_c.index)])
s_cb_is  = stats(var_c_bil[is_mask(var_c_bil.index)])
s_cb_oos = stats(var_c_bil[oos_mask(var_c_bil.index)])
corr_c_prod     = corr_with_series(var_c[oos_mask(var_c.index)], prod_oos)
corr_c_bil_prod = corr_with_series(var_c_bil[oos_mask(var_c_bil.index)], prod_oos)
print(f"  C (no BIL):  IS Sharpe={s_c_is['sharpe']:.4f}  OOS Sharpe={s_c_oos['sharpe']:.4f}  "
      f"MaxDD={s_c_oos['max_drawdown']*100:.1f}%  NegYrs={s_c_oos['neg_years']}  Corr(prod)={corr_c_prod:.3f}")
print(f"  C (BIL):     IS Sharpe={s_cb_is['sharpe']:.4f}  OOS Sharpe={s_cb_oos['sharpe']:.4f}  "
      f"MaxDD={s_cb_oos['max_drawdown']*100:.1f}%  NegYrs={s_cb_oos['neg_years']}  Corr(prod)={corr_c_bil_prod:.3f}")

# ── Variant D: Vol targeting overlay on Var A ─────────────────────────────────
print("\n[4] Variant D — vol-targeted inverse-vol (target 10% annual vol) …")
var_d, _ = build_inv_vol_portfolio(
    RISKY, universe_data, lookback_months=6,
    use_bil_defensive=False, momentum_filter=False, vol_target=0.10)
s_d_is  = stats(var_d[is_mask(var_d.index)])
s_d_oos = stats(var_d[oos_mask(var_d.index)])
corr_d_prod = corr_with_series(var_d[oos_mask(var_d.index)], prod_oos)
print(f"  IS:  Sharpe={s_d_is['sharpe']:.4f}  CAGR={s_d_is['cagr']*100:.1f}%  MaxDD={s_d_is['max_drawdown']*100:.1f}%")
print(f"  OOS: Sharpe={s_d_oos['sharpe']:.4f}  CAGR={s_d_oos['cagr']*100:.1f}%  MaxDD={s_d_oos['max_drawdown']*100:.1f}%  NegYrs={s_d_oos['neg_years']}")
print(f"  Corr(prod)={corr_d_prod:.3f}")

# ── SPY benchmark ─────────────────────────────────────────────────────────────
print("\n[5] SPY benchmark …")
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_m = spy_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
spy_oos_s = stats(spy_m[oos_mask(spy_m.index)])
print(f"  SPY OOS Sharpe={spy_oos_s['sharpe']:.4f}  MaxDD={spy_oos_s['max_drawdown']*100:.1f}%")

# ── Confirmation ──────────────────────────────────────────────────────────────
print("\n[6] Confirmation gate check …")
all_variants = [
    ("A: inv-vol, no BIL",     s_a_oos,   corr_a_prod),
    ("B: inv-vol + BIL",       s_b_oos,   corr_b_prod),
    ("C: inv-vol + mom filter",s_c_oos,   corr_c_prod),
    ("C+BIL: inv-vol+mom+BIL", s_cb_oos,  corr_c_bil_prod),
    ("D: vol-targeted 10%",    s_d_oos,   corr_d_prod),
]
print(f"\n  {'Variant':<30}  {'OOS Sharpe':>10}  {'vs H270':>8}  {'Corr(prod)':>10}  {'Passes?':>7}")
print("  " + "-"*72)
best_variant = None
for name, s, corr_p in all_variants:
    passes = s["sharpe"] > 1.0 and s["sharpe"] > H270_BASELINE
    marker = "PASS" if passes else "FAIL"
    diff = s["sharpe"] - H270_BASELINE
    print(f"  {name:<30}  {s['sharpe']:>10.4f}  {diff:>+8.4f}  {corr_p:>10.3f}  {marker:>7}")
    if passes and (best_variant is None or s["sharpe"] > best_variant[1]["sharpe"]):
        best_variant = (name, s, corr_p)

confirmed = best_variant is not None
if confirmed:
    print(f"\n  *** H278 CONFIRMED — Best variant: {best_variant[0]} ***")
    print(f"      OOS Sharpe={best_variant[1]['sharpe']:.4f} vs H270 baseline {H270_BASELINE:.3f}")
    prod_additive = best_variant[2] < 0.6 and best_variant[1]["sharpe"] > 1.0
    print(f"      Production-additive (Corr < 0.6): {'YES' if prod_additive else 'NO'}")
else:
    print(f"\n  H278 NOT CONFIRMED — no variant beats H270 baseline {H270_BASELINE:.3f}")
    print(f"  H270's dual-ranking approach is superior to volatility-parity weighting.")

# ── Save results ──────────────────────────────────────────────────────────────
output = {
    "hypothesis": "H278",
    "description": "Low-Vol Anomaly: Volatility-Parity ETF Portfolio",
    "confirmed": confirmed,
    "h270_baseline_oos_sharpe": H270_BASELINE,
    "variant_a": {
        "name": "Inverse-vol, risky ETFs only",
        "is_sharpe": s_a_is["sharpe"], "oos_sharpe": s_a_oos["sharpe"],
        "oos_cagr": s_a_oos["cagr"], "oos_max_drawdown": s_a_oos["max_drawdown"],
        "oos_neg_years": s_a_oos["neg_years"], "corr_production": round(corr_a_prod, 4),
    },
    "variant_b": {
        "name": "Inverse-vol + BIL (capped 30%)",
        "is_sharpe": s_b_is["sharpe"], "oos_sharpe": s_b_oos["sharpe"],
        "oos_cagr": s_b_oos["cagr"], "oos_max_drawdown": s_b_oos["max_drawdown"],
        "oos_neg_years": s_b_oos["neg_years"], "corr_production": round(corr_b_prod, 4),
    },
    "variant_c": {
        "name": "Inverse-vol + 6m momentum filter",
        "is_sharpe": s_c_is["sharpe"], "oos_sharpe": s_c_oos["sharpe"],
        "oos_cagr": s_c_oos["cagr"], "oos_max_drawdown": s_c_oos["max_drawdown"],
        "oos_neg_years": s_c_oos["neg_years"], "corr_production": round(corr_c_prod, 4),
    },
    "variant_c_bil": {
        "name": "Inverse-vol + momentum filter + BIL",
        "is_sharpe": s_cb_is["sharpe"], "oos_sharpe": s_cb_oos["sharpe"],
        "oos_cagr": s_cb_oos["cagr"], "oos_max_drawdown": s_cb_oos["max_drawdown"],
        "oos_neg_years": s_cb_oos["neg_years"], "corr_production": round(corr_c_bil_prod, 4),
    },
    "variant_d": {
        "name": "Vol-targeted inverse-vol (10% target)",
        "is_sharpe": s_d_is["sharpe"], "oos_sharpe": s_d_oos["sharpe"],
        "oos_cagr": s_d_oos["cagr"], "oos_max_drawdown": s_d_oos["max_drawdown"],
        "oos_neg_years": s_d_oos["neg_years"], "corr_production": round(corr_d_prod, 4),
    },
    "spy_oos_sharpe": spy_oos_s["sharpe"],
    "best_variant": best_variant[0] if best_variant else None,
}

out_path = RESULT_DIR / "h278_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
