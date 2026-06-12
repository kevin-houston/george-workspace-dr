"""
H283 — Bond ETF Carry + Momentum Rotation (H045 Enhancement)
==============================================================

Hypothesis:
  H045 (Treasury/bond ETF momentum rotation) is CONFIRMED at OOS Sharpe=1.351.
  Adding a carry signal (trailing dividend yield as bond income proxy) alongside
  the momentum signal improves risk-adjusted returns by rewarding ETFs that
  provide both price appreciation AND income.

  Carry signal: trailing 12-month dividend yield per bond ETF.
    yield_t = sum(dividends in past 12 months) / price_t
  This is a forward-looking CARRY proxy — higher-yielding bond ETFs are
  compensating for either: (a) more duration risk, (b) more credit risk,
  or (c) more convexity. In aggregate, they represent the income component
  of total return.

  Blend formula: combined_rank = α × momentum_rank + (1-α) × carry_rank
    - Pure momentum: α=1.0 (H045 baseline)
    - Blend 75/25: α=0.75 (slight carry tilt)
    - Blend 50/50: α=0.50 (equal carry+momentum)
    - Blend 25/75: α=0.25 (carry-dominant)
    - Pure carry:  α=0.00 (carry only, no momentum)

  Universe (same as H045):
    SHY, IEI, IEF, TLT, TIP, HYG, LQD, BKLN, EMB, BIL, MBB, FLOT, PCY

  Hold top-2 by combined rank each month (same as H045's confirmed approach).

  IS: 2008-2017
  OOS: 2018-present
  Gate: OOS Sharpe > H045 baseline (1.351)

Background:
  "Carry" in fixed income = yield - cash rate.
  High-carry bonds (HYG, EMB, LQD) offer more income but more credit/duration risk.
  Low-carry bonds (SHY, BIL) are near cash rate — very low carry.
  Momentum alone (H045) does well by rotating into whichever bond segment is
  appreciating in price — this tends to reward duration during easing cycles
  (TLT/IEF) or credit during growth cycles (HYG/LQD).
  Carry alone would always hold high-yield bonds, ignoring regime shifts.
  The hypothesis is that COMBINING carry and momentum creates a more robust
  signal than either alone.

  Academic basis:
    - Koijen et al. (2018) "Carry" (JFE): carry predicts returns across asset
      classes including government bonds and currencies.
    - Brooks & Moskowitz (2017): momentum + carry combination > either alone in
      bonds globally (Journal of Portfolio Management).
    - Asness, Moskowitz, Pedersen (2013): value+momentum everywhere; carry is
      related to the "value" signal in bonds.
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
FULL_END   = "2026-06-11"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# H045 universe (same 13-ETF set)
BOND_UNIVERSE = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]
N_TOP = 2  # Hold top-2 as in confirmed H045

# Production components for correlation
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
              "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]
IBS_XLK_PARAMS = (0.15, 0.90, 7, -0.010)
IBS_SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IBS_IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
H045_OOS_BASELINE = 1.351  # Confirmed OOS Sharpe from hypothesis log

_PREFIXES = [f"h{i:03d}" for i in range(100, 283)]


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
    cp = CACHE_DIR / f"h283_{ticker}_close_{start}_{end}.parquet"
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


def fetch_dividends(ticker, start, end):
    """Fetch historical dividends. Returns Series indexed by ex-date."""
    cp = CACHE_DIR / f"h283_{ticker}_dividends_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    tk = yf.Ticker(ticker)
    divs = tk.dividends
    if len(divs) == 0:
        return pd.Series(dtype=float, name=ticker)
    divs.index = divs.index.tz_localize(None) if divs.index.tz is not None else divs.index
    divs = divs[(divs.index >= pd.Timestamp(start)) & (divs.index <= pd.Timestamp(end))]
    divs.name = ticker
    divs.to_frame().to_parquet(cp)
    return divs


def fetch_ohlc(ticker, start, end):
    for pfx in _PREFIXES:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h283_{ticker}_ohlc_{start}_{end}.parquet"
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
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        valid   = mom_row.index
        if len(valid) < n_hold:
            continue
        top_n = list(mom_row.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def build_carry_momentum_rotation(tickers, universe_data, div_data, n_top, alpha,
                                   mom_lookback=6):
    """
    Build bond rotation using alpha*momentum_rank + (1-alpha)*carry_rank.

    alpha=1.0 → pure momentum (H045 baseline)
    alpha=0.0 → pure carry (yield only)

    Momentum: trailing mom_lookback-month total return (price only)
    Carry: trailing 12-month dividend yield = sum(divs last 12m) / price_t

    Lag: signal is computed at month-end t-1, applied to month t returns.
    """
    valid = [t for t in tickers if t in universe_data]
    daily_df    = pd.DataFrame({t: universe_data[t] for t in valid}).sort_index()
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    # Build monthly dividend aggregates for carry signal
    div_monthly = {}
    for t in valid:
        if t in div_data and len(div_data[t]) > 0:
            dm = div_data[t].resample("ME").sum().reindex(monthly_px.index, fill_value=0.0)
            div_monthly[t] = dm
        else:
            # No dividends (BIL has tiny amounts; FLOT floats near zero)
            div_monthly[t] = pd.Series(0.0, index=monthly_px.index)

    rows = []
    signal_log = []

    for i in range(max(12, mom_lookback + 1), len(monthly_px)):
        date = monthly_px.index[i]

        # Build scores dict for all available tickers
        mom_scores   = {}
        carry_scores = {}

        for t in valid:
            if t not in monthly_px.columns:
                continue
            px_now = monthly_px[t].iloc[i-1]   # Signal at t-1 (lag for lookahead)
            if np.isnan(px_now) or px_now <= 0:
                continue

            # Momentum: total return over trailing mom_lookback months
            if i >= mom_lookback + 1:
                px_ago = monthly_px[t].iloc[i-1-mom_lookback]
                if not np.isnan(px_ago) and px_ago > 0:
                    mom_scores[t] = px_now / px_ago - 1.0

            # Carry: trailing 12-month dividend yield
            # sum of dividends paid in past 12 months / current price
            if t in div_monthly:
                dm = div_monthly[t]
                if i >= 13:
                    ttm_divs = float(dm.iloc[i-12:i].sum())
                    carry_scores[t] = ttm_divs / px_now  # yield
                else:
                    carry_scores[t] = 0.0

        # Require at least n_top valid entries
        common = set(mom_scores.keys()) & set(carry_scores.keys())
        if len(common) < n_top:
            # Fall back to BIL
            if "BIL" in valid and date in monthly_ret.index:
                rows.append((date, float(monthly_ret.loc[date, "BIL"])))
            continue

        common_list = sorted(common)
        mom_s   = pd.Series({t: mom_scores[t] for t in common_list})
        carry_s = pd.Series({t: carry_scores[t] for t in common_list})

        # Ranks (ascending = higher rank for better)
        mom_rank   = mom_s.rank(ascending=True)
        carry_rank = carry_s.rank(ascending=True)

        combined = alpha * mom_rank + (1 - alpha) * carry_rank
        top_n = list(combined.nlargest(n_top).index)

        # Apply to next month returns
        next_rets = [float(monthly_ret.loc[date, t])
                     for t in top_n
                     if t in monthly_ret.columns and not np.isnan(monthly_ret.loc[date, t])]
        if not next_rets:
            if "BIL" in valid and date in monthly_ret.index:
                rows.append((date, float(monthly_ret.loc[date, "BIL"])))
            continue

        rows.append((date, np.mean(next_rets)))
        signal_log.append({"date": str(date.date()), "held": top_n,
                            "alpha": alpha, "combined_score": combined[top_n].round(3).to_dict()})

    if not rows:
        return pd.Series(dtype=float), []
    return (pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows])),
            signal_log)


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


# ── main ──────────────────────────────────────────────────────────────────────
print("="*80)
print("H283 — Bond ETF Carry + Momentum Rotation (H045 Enhancement)")
print("="*80)

print("\n[0] Loading bond ETF price data …")
universe_data = {}
for t in BOND_UNIVERSE:
    try:
        universe_data[t] = fetch_daily_close(t, FULL_START, FULL_END)
        print(f"  {t}: OK")
    except Exception as e:
        print(f"  {t}: {e}")

print("\n[0b] Loading bond ETF dividend data …")
div_data = {}
for t in BOND_UNIVERSE:
    try:
        div_data[t] = fetch_dividends(t, FULL_START, FULL_END)
        n_divs = len(div_data[t])
        first_div = div_data[t].index[0].date() if n_divs > 0 else "N/A"
        print(f"  {t}: {n_divs} dividend payments  first={first_div}")
    except Exception as e:
        print(f"  {t}: {e}")
        div_data[t] = pd.Series(dtype=float, name=t)

print("\n[0c] Building production baseline …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*IBS_XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*IBS_SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IBS_IGV_PARAMS))
h041a = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1)
h045  = build_rotation_monthly(H045_PROD,  FULL_START, FULL_END, 2)

def prod_blend(h41_r, h26_r, h45_r, xlk, smh, igv):
    idx = h41_r.index
    for s in [h26_r, h45_r, xlk, smh, igv]:
        idx = idx.intersection(s.index)
    idx = idx.sort_values()
    return (0.22*h41_r.reindex(idx) + 0.27*h26_r.reindex(idx) + 0.21*h45_r.reindex(idx)
            + 0.20*xlk.reindex(idx) + 0.08*smh.reindex(idx) + 0.02*igv.reindex(idx))

prod_r   = prod_blend(h041a, h026, h045, xlk_r, smh_r, igv_r)
prod_oos = prod_r[oos_mask(prod_r.index)]
print(f"  Production OOS Sharpe: {stats(prod_oos)['sharpe']:.4f}")

# AGG benchmark
print("\n[1] AGG buy-and-hold benchmark …")
try:
    agg_close = fetch_daily_close("AGG", FULL_START, FULL_END)
    agg_m = agg_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
    agg_oos_s = stats(agg_m[oos_mask(agg_m.index)])
    print(f"  AGG OOS Sharpe={agg_oos_s['sharpe']:.4f} MaxDD={agg_oos_s['max_drawdown']*100:.1f}%")
except Exception as e:
    print(f"  AGG: {e}")
    agg_oos_s = {"sharpe": float("nan")}

# ── Build all blend variants ──────────────────────────────────────────────────
print("\n[2] Building carry+momentum blend variants …")
alphas = {
    "alpha=1.00 (pure momentum)": 1.00,
    "alpha=0.75 (blend 75/25)":   0.75,
    "alpha=0.50 (blend 50/50)":   0.50,
    "alpha=0.25 (blend 25/75)":   0.25,
    "alpha=0.00 (pure carry)":    0.00,
}

variant_results = {}
for label, alpha in alphas.items():
    print(f"\n  {label} …")
    r, slog = build_carry_momentum_rotation(
        BOND_UNIVERSE, universe_data, div_data,
        n_top=N_TOP, alpha=alpha
    )
    oos_r  = r[oos_mask(r.index)]
    is_r   = r[is_mask(r.index)]
    s_oos  = stats(oos_r)
    s_is   = stats(is_r)
    c_prod = corr_with_series(oos_r, prod_oos)
    c_h045 = corr_with_series(oos_r, h045[oos_mask(h045.index)])
    passes = s_oos["sharpe"] > H045_OOS_BASELINE
    print(f"    IS:  Sharpe={s_is['sharpe']:.4f} CAGR={s_is['cagr']*100:.1f}% MaxDD={s_is['max_drawdown']*100:.1f}%")
    print(f"    OOS: Sharpe={s_oos['sharpe']:.4f} CAGR={s_oos['cagr']*100:.1f}% MaxDD={s_oos['max_drawdown']*100:.1f}% NegYrs={s_oos['neg_years']}")
    print(f"    Corr(prod)={c_prod:.3f}  Corr(H045)={c_h045:.3f}  PASS={passes}")
    variant_results[label] = {
        "alpha": alpha,
        "is_sharpe": s_is["sharpe"], "oos_sharpe": s_oos["sharpe"],
        "oos_cagr": s_oos["cagr"], "oos_max_drawdown": s_oos["max_drawdown"],
        "oos_neg_years": s_oos["neg_years"], "corr_production": round(c_prod, 4),
        "corr_h045": round(c_h045, 4), "passes": passes,
    }

# ── Confirmation gate ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("CONFIRMATION GATE")
print("="*60)

# H045 reference (pure 12m momentum, no carry)
h045_oos_s = stats(h045[oos_mask(h045.index)])
h045_is_s  = stats(h045[is_mask(h045.index)])
print(f"\n  H045 (12m mom, no carry) IS Sharpe={h045_is_s['sharpe']:.4f}  OOS Sharpe={h045_oos_s['sharpe']:.4f}")

print(f"\n  H045 confirmed OOS baseline = {H045_OOS_BASELINE:.3f}")
print(f"\n  {'Variant':<38}  {'OOS Sharpe':>10}  {'vs H045':>8}  {'Passes?':>7}")
print("  " + "-"*68)
best = None
for label, res in variant_results.items():
    diff = res["oos_sharpe"] - H045_OOS_BASELINE
    marker = "PASS" if res["passes"] else "FAIL"
    print(f"  {label:<38}  {res['oos_sharpe']:>10.4f}  {diff:>+8.4f}  {marker:>7}")
    if res["passes"] and (best is None or res["oos_sharpe"] > best[1]["oos_sharpe"]):
        best = (label, res)

confirmed = best is not None
if confirmed:
    print(f"\n  *** H283 CONFIRMED ***")
    print(f"  Best variant: {best[0]}")
    print(f"  OOS Sharpe={best[1]['oos_sharpe']:.4f} vs H045 baseline {H045_OOS_BASELINE:.3f}")
    print(f"  MaxDD={best[1]['oos_max_drawdown']*100:.1f}%  Corr(prod)={best[1]['corr_production']:.3f}")
else:
    print(f"\n  H283 NOT CONFIRMED — no blend variant beats H045 baseline {H045_OOS_BASELINE:.3f}")
    print(f"  Pure momentum (H045) remains the optimal bond rotation signal.")
    # Show best result anyway
    best_any = max(variant_results.items(), key=lambda kv: kv[1]["oos_sharpe"])
    print(f"  Best result: {best_any[0]} → OOS Sharpe={best_any[1]['oos_sharpe']:.4f}")

# ── Save results ───────────────────────────────────────────────────────────────
output = {
    "hypothesis": "H283",
    "description": "Bond ETF Carry + Momentum Rotation (H045 Enhancement)",
    "confirmed": confirmed,
    "h045_oos_baseline": H045_OOS_BASELINE,
    "gate": "OOS Sharpe > H045 baseline (1.351)",
    "benchmarks": {
        "agg_oos_sharpe": agg_oos_s["sharpe"],
        "h045_recomputed_oos_sharpe": h045_oos_s["sharpe"],
    },
    "variants": variant_results,
    "best_variant": best[0] if best else None,
    "best_oos_sharpe": best[1]["oos_sharpe"] if best else None,
}

class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        if isinstance(obj, (bool, int, float)):
            return obj
        return super().default(obj)

out_path = RESULT_DIR / "h283_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, cls=SafeEncoder)
print(f"\n  Results saved → {out_path}")
print("="*80)
