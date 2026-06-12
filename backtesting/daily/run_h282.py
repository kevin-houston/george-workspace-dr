"""
H282 — Dividend Growth ETF Rotation
=====================================

Hypothesis:
  Rotating among high-dividend ETFs based on trailing dividend GROWTH RATE (not
  dividend YIELD) captures a distinct factor: dividend growers signal improving
  fundamental quality and attract incremental institutional demand, generating
  excess returns vs static high-yield holdings.

  Signal: YoY dividend growth rate = (sum of dividends in trailing 4 quarters) /
          (sum of dividends in 4 quarters ending 1 year ago) - 1.

  Universe (high-dividend focused):
    Core  (data since 2003-2006): DVY, VYM, SDY, VIG, BIL
    Extended (data since 2011+):  + SCHD, DGRO, NOBL

  Two sub-tests:
    A) Core 5-asset universe (DVY/VYM/SDY/VIG/BIL): IS 2008-2019, OOS 2020-present
    B) Extended 8-asset universe (adds SCHD/DGRO/NOBL): IS 2016-2019, OOS 2020-present

  Variants (each sub-test):
    1) Top-1 by div growth rate
    2) Top-2 by div growth rate
    3) Blend: 50% div_growth rank + 50% 6m momentum rank (hybrid signal)

  Baseline comparisons:
    - Equal-weight all (no rotation) — the "buy all and hold" benchmark
    - DVY buy-and-hold (largest, oldest dividend ETF)
    - SPY buy-and-hold

  Gate:
    CONFIRMED: OOS Sharpe > 1.0 AND > equal-weight baseline
    Production-additive: Corr(H282, production) < 0.7

IS: 2008-2019 (core), 2016-2019 (extended)
OOS: 2020-present

Background:
  Dividend growth investing (DGI) differs from dividend yield investing:
  - High-yield: select ETFs with highest current yield (may attract distressed assets)
  - Dividend growth: select ETFs whose underlying holdings show accelerating div growth
    (typically quality bias: profitability, stable cash flows, moat companies)

  Academic support:
    - Litzenberger & Ramaswamy (1979): dividend yield cross-sectionally predicts returns
    - Arnott & Asness (2003): payout ratios (hence div growth) predict market returns
    - Hartzmark & Solomon (2019): investors irrationally chase dividends, creating price
      pressure before ex-date in high-growth-yield ETFs
    - Practical: SCHD/DGRO (growth-screened) have outperformed DVY (yield-screened) OOS
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
IS_START_CORE = "2008-01-01"
IS_END_CORE   = "2019-12-31"
IS_START_EXT  = "2016-01-01"
IS_END_EXT    = "2019-12-31"
OOS_START     = "2020-01-01"

CORE_UNIVERSE = ["DVY", "VYM", "SDY", "VIG", "BIL"]
EXT_UNIVERSE  = ["DVY", "VYM", "SDY", "VIG", "SCHD", "DGRO", "NOBL", "BIL"]
RISKY_CORE    = ["DVY", "VYM", "SDY", "VIG"]
RISKY_EXT     = ["DVY", "VYM", "SDY", "VIG", "SCHD", "DGRO", "NOBL"]

# Production components for correlation
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
              "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
              "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]
IBS_XLK_PARAMS = (0.15, 0.90, 7, -0.010)
IBS_SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IBS_IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

_PREFIXES = [f"h{i:03d}" for i in range(100, 282)]


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
    cp = CACHE_DIR / f"h282_{ticker}_close_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h282_{ticker}_dividends_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze().rename(ticker)
    tk = yf.Ticker(ticker)
    divs = tk.dividends
    if len(divs) == 0:
        return pd.Series(dtype=float, name=ticker)
    # Timezone-strip
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
    cp = CACHE_DIR / f"h282_{ticker}_ohlc_{start}_{end}.parquet"
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


def compute_quarterly_dividends(ticker, divs_raw, close_monthly):
    """
    Aggregate dividends to monthly-resample frequency, then compute
    trailing 4-quarter sum (TTM dividends) for each month-end.

    Returns pd.Series indexed by month-end dates with TTM dividend sum.
    """
    if len(divs_raw) == 0:
        return pd.Series(dtype=float, name=ticker)

    # Resample dividends to monthly sum
    divs_monthly = divs_raw.resample("ME").sum()

    # Align to close_monthly index (fill missing months with 0)
    divs_monthly = divs_monthly.reindex(close_monthly.index, fill_value=0.0)

    # Rolling 4-quarter (12-month) sum = TTM dividends
    ttm = divs_monthly.rolling(12, min_periods=4).sum()
    return ttm.rename(ticker)


def build_div_growth_portfolio(risky_tickers, all_tickers, universe_data,
                                div_data, signal_type="growth", n_top=1):
    """
    Build portfolio rotating by dividend growth rate signal.

    signal_type:
      "growth"  — rank by YoY dividend growth rate (TTM_t / TTM_{t-12} - 1)
      "hybrid"  — 50% growth rank + 50% 6m price momentum rank

    n_top: number of ETFs to hold each month (equal-weight)

    Returns: monthly return series
    """
    valid = [t for t in risky_tickers if t in universe_data and t in div_data]
    daily_df   = pd.DataFrame({t: universe_data[t] for t in valid}).sort_index()
    monthly_px = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    bil_ret = None
    if "BIL" in universe_data:
        bil_close = universe_data["BIL"]
        bil_ret = bil_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    # Build TTM dividend series for each ticker
    ttm_divs = {}
    for t in valid:
        ttm_divs[t] = compute_quarterly_dividends(
            t, div_data[t], monthly_px[t].dropna()
        )

    rows = []
    for i in range(24, len(monthly_px)):  # Need 24 months for YoY comparison
        this_date = monthly_px.index[i]
        scores = {}

        for t in valid:
            ttm = ttm_divs.get(t)
            if ttm is None or len(ttm) < 13:
                continue
            # Current TTM
            try:
                ttm_now = ttm.iloc[i]
                ttm_yr_ago = ttm.iloc[i-12]  # YoY comparison
            except IndexError:
                continue

            if np.isnan(ttm_now) or np.isnan(ttm_yr_ago) or ttm_yr_ago <= 0:
                continue

            growth_rate = ttm_now / ttm_yr_ago - 1.0
            scores[t] = growth_rate

        if len(scores) < max(1, n_top):
            # Fall back to BIL if no valid scores
            if bil_ret is not None and this_date in bil_ret.index:
                rows.append((this_date, float(bil_ret.loc[this_date])))
            continue

        scores_s = pd.Series(scores)

        if signal_type == "hybrid":
            # Add 6m momentum rank
            mom_6m = {}
            for t in scores.keys():
                if i >= 7 and t in monthly_px.columns:
                    px_now  = monthly_px[t].iloc[i-1]
                    px_6ago = monthly_px[t].iloc[i-7]
                    if not np.isnan(px_now) and not np.isnan(px_6ago) and px_6ago > 0:
                        mom_6m[t] = px_now / px_6ago - 1.0
            if len(mom_6m) == 0:
                signal = scores_s.rank()
            else:
                mom_s = pd.Series(mom_6m)
                growth_rank = scores_s.rank()
                mom_rank    = mom_s.rank()
                combined    = growth_rank.reindex(scores.keys()) * 0.5 + \
                              mom_rank.reindex(scores.keys()).fillna(0) * 0.5
                signal = combined
        else:
            signal = scores_s.rank()

        top_n_tickers = list(signal.nlargest(n_top).index)
        next_rets = [float(monthly_ret.loc[this_date, t])
                     for t in top_n_tickers
                     if this_date in monthly_ret.index and t in monthly_ret.columns]
        if not next_rets:
            if bil_ret is not None and this_date in bil_ret.index:
                rows.append((this_date, float(bil_ret.loc[this_date])))
            continue
        rows.append((this_date, np.mean(next_rets)))

    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def build_equal_weight_ret(tickers, universe_data, start, end):
    """Equal-weight all non-BIL tickers, monthly rebalance."""
    risky = [t for t in tickers if t != "BIL" and t in universe_data]
    daily_df   = pd.DataFrame({t: universe_data[t] for t in risky}).sort_index()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    return monthly_ret.mean(axis=1).dropna()


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
def is_mask_core(idx):  return (idx >= ts(IS_START_CORE)) & (idx <= ts(IS_END_CORE))
def is_mask_ext(idx):   return (idx >= ts(IS_START_EXT))  & (idx <= ts(IS_END_EXT))
def oos_mask(idx):      return idx >= ts(OOS_START)


# ── main ──────────────────────────────────────────────────────────────────────
print("="*80)
print("H282 — Dividend Growth ETF Rotation")
print("="*80)

print("\n[0] Loading universe data …")
all_tickers = list(set(EXT_UNIVERSE))
universe_data = {}
for t in all_tickers:
    try:
        universe_data[t] = fetch_daily_close(t, FULL_START, FULL_END)
        print(f"  {t}: OK")
    except Exception as e:
        print(f"  {t}: {e}")

print("\n[0b] Loading dividend data …")
div_data = {}
for t in all_tickers:
    if t == "BIL":
        div_data[t] = pd.Series(dtype=float, name=t)  # BIL pays tiny money-market yield
        continue
    try:
        div_data[t] = fetch_dividends(t, FULL_START, FULL_END)
        n_divs = len(div_data[t])
        print(f"  {t}: {n_divs} dividend payments")
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

# ── Section A: Core universe (DVY/VYM/SDY/VIG/BIL) ────────────────────────────
print("\n" + "="*60)
print("SECTION A: Core Universe (DVY/VYM/SDY/VIG + BIL)")
print("="*60)

# Equal-weight baseline
ew_core = build_equal_weight_ret(CORE_UNIVERSE, universe_data, FULL_START, FULL_END)
spy_close = universe_data.get("SPY") or fetch_daily_close("SPY", FULL_START, FULL_END)

# Load SPY for comparison
spy_data_tmp = {}
try:
    spy_data_tmp["SPY"] = fetch_daily_close("SPY", FULL_START, FULL_END)
except:
    pass
spy_m = spy_data_tmp["SPY"].pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna() if "SPY" in spy_data_tmp else pd.Series(dtype=float)
spy_oos_s = stats(spy_m[oos_mask(spy_m.index)])
print(f"\n  SPY B&H OOS Sharpe={spy_oos_s['sharpe']:.4f}")

ew_core_oos_s = stats(ew_core[oos_mask(ew_core.index)])
print(f"  Equal-weight core OOS Sharpe={ew_core_oos_s['sharpe']:.4f}")

# DVY buy-and-hold
dvy_m = universe_data["DVY"].pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
dvy_oos_s = stats(dvy_m[oos_mask(dvy_m.index)])
print(f"  DVY B&H OOS Sharpe={dvy_oos_s['sharpe']:.4f}")

# Variants A1, A2, A3
print("\n  Building core rotation variants …")
print("  A1: Top-1 by dividend growth rate …")
a1 = build_div_growth_portfolio(RISKY_CORE, CORE_UNIVERSE, universe_data, div_data,
                                 signal_type="growth", n_top=1)
print("  A2: Top-2 by dividend growth rate …")
a2 = build_div_growth_portfolio(RISKY_CORE, CORE_UNIVERSE, universe_data, div_data,
                                 signal_type="growth", n_top=2)
print("  A3: Hybrid (50% growth rank + 50% 6m momentum rank), Top-1 …")
a3 = build_div_growth_portfolio(RISKY_CORE, CORE_UNIVERSE, universe_data, div_data,
                                 signal_type="hybrid", n_top=1)
print("  A4: Hybrid Top-2 …")
a4 = build_div_growth_portfolio(RISKY_CORE, CORE_UNIVERSE, universe_data, div_data,
                                 signal_type="hybrid", n_top=2)

core_variants = [("A1: Top-1 growth",  a1), ("A2: Top-2 growth", a2),
                 ("A3: Hybrid Top-1",   a3), ("A4: Hybrid Top-2",  a4)]
core_results  = {}
for name, r in core_variants:
    oos_r = r[oos_mask(r.index)]
    is_r  = r[is_mask_core(r.index)]
    s_oos = stats(oos_r)
    s_is  = stats(is_r)
    c_prod = corr_with_series(oos_r, prod_oos)
    c_spy  = corr_with_series(oos_r, spy_m[oos_mask(spy_m.index)])
    passes = s_oos["sharpe"] > 1.0 and s_oos["sharpe"] > ew_core_oos_s["sharpe"]
    print(f"\n  {name}:")
    print(f"    IS:  Sharpe={s_is['sharpe']:.4f} CAGR={s_is['cagr']*100:.1f}% MaxDD={s_is['max_drawdown']*100:.1f}% n={s_is['n_months']}")
    print(f"    OOS: Sharpe={s_oos['sharpe']:.4f} CAGR={s_oos['cagr']*100:.1f}% MaxDD={s_oos['max_drawdown']*100:.1f}% NegYrs={s_oos['neg_years']} n={s_oos['n_months']}")
    print(f"    Corr(prod)={c_prod:.3f}  Corr(SPY)={c_spy:.3f}  PASS={passes}")
    core_results[name] = {"is_sharpe": s_is["sharpe"], "oos_sharpe": s_oos["sharpe"],
                           "oos_cagr": s_oos["cagr"], "oos_max_drawdown": s_oos["max_drawdown"],
                           "oos_neg_years": s_oos["neg_years"], "corr_production": round(c_prod, 4),
                           "corr_spy": round(c_spy, 4), "passes": passes}

# ── Section B: Extended universe ──────────────────────────────────────────────
print("\n" + "="*60)
print("SECTION B: Extended Universe (+SCHD/DGRO/NOBL)")
print("="*60)

# Check which extended tickers have enough dividend data
valid_ext = [t for t in RISKY_EXT
             if t in div_data and len(div_data.get(t, [])) >= 20]
print(f"  Valid tickers with ≥20 dividend payments: {valid_ext}")

ew_ext = build_equal_weight_ret([t for t in EXT_UNIVERSE if t in universe_data],
                                  universe_data, FULL_START, FULL_END)
ew_ext_oos_s = stats(ew_ext[oos_mask(ew_ext.index)])
print(f"  Equal-weight extended OOS Sharpe={ew_ext_oos_s['sharpe']:.4f}")

print("\n  Building extended rotation variants …")
print("  B1: Top-1 by dividend growth rate …")
b1 = build_div_growth_portfolio(valid_ext, EXT_UNIVERSE, universe_data, div_data,
                                 signal_type="growth", n_top=1)
print("  B2: Top-2 by dividend growth rate …")
b2 = build_div_growth_portfolio(valid_ext, EXT_UNIVERSE, universe_data, div_data,
                                 signal_type="growth", n_top=2)
print("  B3: Hybrid Top-1 …")
b3 = build_div_growth_portfolio(valid_ext, EXT_UNIVERSE, universe_data, div_data,
                                 signal_type="hybrid", n_top=1)

ext_variants = [("B1: Top-1 growth",  b1), ("B2: Top-2 growth", b2),
                ("B3: Hybrid Top-1",   b3)]
ext_results  = {}
for name, r in ext_variants:
    oos_r = r[oos_mask(r.index)]
    is_r  = r[is_mask_ext(r.index)]
    s_oos = stats(oos_r)
    s_is  = stats(is_r)
    c_prod = corr_with_series(oos_r, prod_oos)
    c_spy  = corr_with_series(oos_r, spy_m[oos_mask(spy_m.index)])
    passes = s_oos["sharpe"] > 1.0 and s_oos["sharpe"] > ew_ext_oos_s["sharpe"]
    print(f"\n  {name}:")
    print(f"    IS:  Sharpe={s_is['sharpe']:.4f} CAGR={s_is['cagr']*100:.1f}% MaxDD={s_is['max_drawdown']*100:.1f}% n={s_is['n_months']}")
    print(f"    OOS: Sharpe={s_oos['sharpe']:.4f} CAGR={s_oos['cagr']*100:.1f}% MaxDD={s_oos['max_drawdown']*100:.1f}% NegYrs={s_oos['neg_years']} n={s_oos['n_months']}")
    print(f"    Corr(prod)={c_prod:.3f}  Corr(SPY)={c_spy:.3f}  PASS={passes}")
    ext_results[name] = {"is_sharpe": s_is["sharpe"], "oos_sharpe": s_oos["sharpe"],
                          "oos_cagr": s_oos["cagr"], "oos_max_drawdown": s_oos["max_drawdown"],
                          "oos_neg_years": s_oos["neg_years"], "corr_production": round(c_prod, 4),
                          "corr_spy": round(c_spy, 4), "passes": passes}

# ── Confirmation gate ──────────────────────────────────────────────────────────
print("\n" + "="*60)
print("CONFIRMATION GATE")
print("="*60)

all_variants_flat = list(core_results.items()) + list(ext_results.items())
best = max(all_variants_flat, key=lambda kv: kv[1]["oos_sharpe"])
best_name, best_stats = best
confirmed = best_stats["passes"]
print(f"\n  Best variant: {best_name}")
print(f"  OOS Sharpe: {best_stats['oos_sharpe']:.4f}")
print(f"  OOS CAGR: {best_stats['oos_cagr']*100:.1f}%")
print(f"  OOS MaxDD: {best_stats['oos_max_drawdown']*100:.1f}%")
print(f"  Corr(prod): {best_stats['corr_production']:.3f}")
print(f"\n  Equal-weight baseline OOS Sharpe: {ew_core_oos_s['sharpe']:.4f}")
print(f"  SPY OOS Sharpe: {spy_oos_s['sharpe']:.4f}")
print(f"  DVY B&H OOS Sharpe: {dvy_oos_s['sharpe']:.4f}")
print(f"\n  H282 {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

# ── Save results ───────────────────────────────────────────────────────────────
output = {
    "hypothesis": "H282",
    "description": "Dividend Growth ETF Rotation",
    "confirmed": confirmed,
    "gates": {"oos_sharpe_threshold": 1.0, "require_beats_equal_weight": True},
    "benchmarks": {
        "spy_oos_sharpe": spy_oos_s["sharpe"],
        "dvy_bh_oos_sharpe": dvy_oos_s["sharpe"],
        "equal_weight_core_oos_sharpe": ew_core_oos_s["sharpe"],
        "equal_weight_ext_oos_sharpe": ew_ext_oos_s["sharpe"],
    },
    "core_variants": core_results,
    "extended_variants": ext_results,
    "best_variant": best_name,
    "best_oos_sharpe": best_stats["oos_sharpe"],
}

class SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        if isinstance(obj, (bool, int, float)):
            return obj
        return super().default(obj)

out_path = RESULT_DIR / "h282_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2, cls=SafeEncoder)
print(f"\n  Results saved → {out_path}")
print("="*80)
