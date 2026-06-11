"""
H277 — NASDAQ Stock Momentum: 12-1 Skip-Month Signal
=====================================================

Hypothesis:
  Top-200 NASDAQ stocks by average daily dollar volume (ADDV proxy).
  12-1 month momentum signal (skip most recent month to avoid reversal contamination).
  Monthly rebalance, long top-5 equal weight.

  This is a follow-on to H272 (12-0 momentum, OOS Sharpe 2.509, SEVERE SURVIVORSHIP BIAS).
  H277 tests two things:
    1. Whether the 12-1 skip-month signal improves over H272's 12-0 signal
    2. Two different universe constructions to understand the bias magnitude:
       A) Fixed 30-stock universe (same survivorship caveat as H272, but 12-1 signal)
       B) Fixed 60-stock broader universe (more diversified but same survivorship caveat)

  Key improvement over H272: skip most recent month to avoid reversal noise.
  Framework: IS 2008-2017, OOS 2018-present
  Gate: OOS Sharpe > 1.0

  SURVIVORSHIP BIAS WARNING: Both universe constructions use stocks that survived to
  2026. Results are materially inflated. Treat as signal-quality test only, NOT
  production-ready results. True OOS would require historical NASDAQ constituent data.

Background:
  Jegadeesh & Titman (1993) — standard momentum uses 12m-1m signal.
  The skip-1-month convention: signal = return from t-12 to t-1 (not t-12 to t).
  Rationale: the most recent month carries short-term reversal noise that contaminates
  the momentum signal. This is the industry standard for cross-sectional momentum.

  H272 used 12-0 (no skip) and got OOS 2.509 with survivorship bias.
  H277 tests whether the academically correct 12-1 formulation performs differently.
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

# Universe A: 30 large-cap NASDAQ/tech stocks (same size as H272 anchor)
# Deliberately includes survivors that dominated 2018-2025
UNIVERSE_A = [
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","ASML","NFLX",
    "ADBE","QCOM","INTC","TXN","AMD","AMAT","LRCX","KLAC","MU","MRVL",
    "ORCL","CRM","NOW","INTU","SNPS","CDNS","ANSS","MCHP","SWKS","FSLR",
]

# Universe B: 60-stock broader NASDAQ/S&P tech universe
UNIVERSE_B = [
    # Core tech
    "AAPL","MSFT","NVDA","AMZN","META","GOOGL","TSLA","AVGO","ASML","NFLX",
    "ADBE","QCOM","INTC","TXN","AMD","AMAT","LRCX","KLAC","MU","MRVL",
    "ORCL","CRM","NOW","INTU","SNPS","CDNS","ANSS","MCHP","SWKS","FSLR",
    # Mid-cap tech + additional NASDAQ names
    "PANW","CRWD","ZS","FTNT","OKTA","DDOG","NET","SNOW","PLTR","ABNB",
    "PYPL","SQ","COIN","HOOD","DOCU","ZM","TEAM","ATLASSIAN","WDAY","VEEV",
    # Healthcare tech + other NASDAQ
    "ISRG","IDXX","ALGN","HOLX","DXCM",
    "COST","SBUX","MNST","FAST","ODFL",
    "REGN","VRTX","ILMN","BIIB","GILD",
]

# Filter B to only stocks that list on yfinance and have data from 2008
# (some like SNOW/PLTR/COIN/HOOD listed after 2018 — they'll be excluded by data availability)

# Production portfolio for correlation calc
H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_XLK_PARAMS = (0.15, 0.90, 7, -0.010)
IBS_SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IBS_IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

_PREFIXES = [f"h{i:03d}" for i in range(100, 277)]


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
    cp = CACHE_DIR / f"h277_{ticker}_close_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h277_{ticker}_ohlc_{start}_{end}.parquet"
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


def build_stock_momentum(tickers, start, end, n_hold=5, skip_month=True):
    """
    Build stock cross-sectional momentum portfolio.
    skip_month=True: use 12-1 signal (standard, avoids reversal)
    skip_month=False: use 12-0 signal (like H272)
    Returns monthly return series.
    """
    closes = {}
    for t in tickers:
        try:
            s = fetch_daily_close(t, start, end)
            if len(s) > 252:
                closes[t] = s
        except Exception as e:
            print(f"    {t}: {e}")

    if not closes:
        return pd.Series(dtype=float)

    daily_df   = pd.DataFrame(closes).sort_index()
    monthly_px = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    rows = []
    for i in range(13, len(monthly_px)):  # need 13 months for 12-1 signal
        if skip_month:
            # 12-1: signal = return from t-12 to t-1 (skip most recent month)
            px_now   = monthly_px.iloc[i-1]   # t-1 (one month ago)
            px_12ago = monthly_px.iloc[i-13]  # t-13 (13 months ago)
        else:
            # 12-0: signal = return from t-12 to t (include most recent month)
            px_now   = monthly_px.iloc[i]     # t
            px_12ago = monthly_px.iloc[i-12]  # t-12

        signal = (px_now / px_12ago - 1).dropna()

        # Require data available throughout (at least 12m of data)
        valid_tickers = [t for t in signal.index
                        if not pd.isna(monthly_px.iloc[i][t])
                        and not pd.isna(monthly_px.iloc[i-12][t])]

        if len(valid_tickers) < n_hold:
            continue

        sig_valid = signal[valid_tickers]
        top_n = list(sig_valid.nlargest(n_hold).index)
        # Return is next month's return (buy at end of signal month, hold 1 month)
        ret_row = monthly_ret.iloc[i][top_n].dropna()
        if len(ret_row) == 0:
            continue
        rows.append((monthly_px.index[i], ret_row.mean()))

    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


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
    # Count negative calendar years
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
def ai_mask(idx):  return (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


# ── main ─────────────────────────────────────────────────────────────────────

print("="*80)
print("H277 — NASDAQ Stock Momentum: 12-1 Skip-Month Signal")
print("="*80)

print("\n[0] Building production baseline components …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*IBS_XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*IBS_SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IBS_IGV_PARAMS))
h041a = build_rotation_monthly(H041A_FULL,  FULL_START, FULL_END, 1)
h026  = build_rotation_monthly(H026_BASE,   FULL_START, FULL_END, 1)
h045  = build_rotation_monthly(H045_PROD,   FULL_START, FULL_END, 2)

# Production blend monthly returns
def prod_blend(*series_list):
    # weights: h041a=22%, h026=27%, h045=21%, XLK=20%, SMH=8%, IGV=2%
    h41_r, h26_r, h45_r, xlk, smh, igv = series_list
    idx = h41_r.index
    for s in series_list[1:]:
        idx = idx.intersection(s.index)
    idx = idx.sort_values()
    return (0.22*h41_r.reindex(idx) + 0.27*h26_r.reindex(idx) + 0.21*h45_r.reindex(idx)
            + 0.20*xlk.reindex(idx) + 0.08*smh.reindex(idx) + 0.02*igv.reindex(idx))

prod_r = prod_blend(h041a, h026, h045, xlk_r, smh_r, igv_r)
prod_oos = prod_r[oos_mask(prod_r.index)]

print(f"  Production OOS Sharpe: {stats(prod_oos)['sharpe']:.4f}")

# ── Variant A: 30-stock universe, top-5, 12-1 signal ─────────────────────────
print("\n[1] Variant A — 30-stock NASDAQ universe, top-5, 12-1 skip-month …")
mom_a_12_1 = build_stock_momentum(UNIVERSE_A, FULL_START, FULL_END, n_hold=5, skip_month=True)
mom_a_12_0 = build_stock_momentum(UNIVERSE_A, FULL_START, FULL_END, n_hold=5, skip_month=False)

s_a_12_1_is  = stats(mom_a_12_1[is_mask(mom_a_12_1.index)])
s_a_12_1_oos = stats(mom_a_12_1[oos_mask(mom_a_12_1.index)])
s_a_12_0_is  = stats(mom_a_12_0[is_mask(mom_a_12_0.index)])
s_a_12_0_oos = stats(mom_a_12_0[oos_mask(mom_a_12_0.index)])

corr_a_12_1_prod = corr_with_series(mom_a_12_1[oos_mask(mom_a_12_1.index)], prod_oos)
corr_a_12_0_prod = corr_with_series(mom_a_12_0[oos_mask(mom_a_12_0.index)], prod_oos)

print(f"  12-1: IS Sharpe={s_a_12_1_is['sharpe']:.4f}  OOS Sharpe={s_a_12_1_oos['sharpe']:.4f}  "
      f"MaxDD={s_a_12_1_oos['max_drawdown']*100:.1f}%  NegYrs={s_a_12_1_oos['neg_years']}  "
      f"Corr(prod)={corr_a_12_1_prod:.3f}")
print(f"  12-0: IS Sharpe={s_a_12_0_is['sharpe']:.4f}  OOS Sharpe={s_a_12_0_oos['sharpe']:.4f}  "
      f"MaxDD={s_a_12_0_oos['max_drawdown']*100:.1f}%  NegYrs={s_a_12_0_oos['neg_years']}  "
      f"Corr(prod)={corr_a_12_0_prod:.3f}")
print(f"  Skip-month effect (12-1 vs 12-0): OOS delta={s_a_12_1_oos['sharpe']-s_a_12_0_oos['sharpe']:+.4f}")

# ── Variant B: 60-stock universe, top-5, 12-1 signal ─────────────────────────
print("\n[2] Variant B — 60-stock broader universe, top-5, 12-1 skip-month …")
# Filter to valid tickers (those that have data from 2008)
print("  Downloading/caching prices …")
valid_b = []
for t in UNIVERSE_B:
    try:
        s = fetch_daily_close(t, FULL_START, FULL_END)
        # Check data starts before 2010
        first_date = s.dropna().index[0] if len(s.dropna()) > 0 else None
        if first_date is not None and first_date < pd.Timestamp("2010-01-01"):
            valid_b.append(t)
        else:
            print(f"    Skipping {t}: data starts {first_date}")
    except Exception as e:
        print(f"    Skipping {t}: {e}")

print(f"  Valid universe B size: {len(valid_b)} stocks")
if len(valid_b) >= 10:
    mom_b_12_1 = build_stock_momentum(valid_b, FULL_START, FULL_END, n_hold=5, skip_month=True)
    s_b_12_1_is  = stats(mom_b_12_1[is_mask(mom_b_12_1.index)])
    s_b_12_1_oos = stats(mom_b_12_1[oos_mask(mom_b_12_1.index)])
    corr_b_prod = corr_with_series(mom_b_12_1[oos_mask(mom_b_12_1.index)], prod_oos)
    print(f"  12-1: IS Sharpe={s_b_12_1_is['sharpe']:.4f}  OOS Sharpe={s_b_12_1_oos['sharpe']:.4f}  "
          f"MaxDD={s_b_12_1_oos['max_drawdown']*100:.1f}%  NegYrs={s_b_12_1_oos['neg_years']}  "
          f"Corr(prod)={corr_b_prod:.3f}")
else:
    print(f"  Insufficient valid stocks — skipping Variant B")
    mom_b_12_1 = pd.Series(dtype=float)
    s_b_12_1_is = s_b_12_1_oos = {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":0,"neg_years":0}
    corr_b_prod = float("nan")
    valid_b = []

# ── Variant C: top-5 with n_hold sensitivity sweep ──────────────────────────
print("\n[3] Variant C — n_hold sensitivity (2, 5, 10) on Var A 12-1 …")
sweep_results = []
for n in [2, 3, 5, 10]:
    r = build_stock_momentum(UNIVERSE_A, FULL_START, FULL_END, n_hold=n, skip_month=True)
    s_oos = stats(r[oos_mask(r.index)])
    s_is  = stats(r[is_mask(r.index)])
    corr_p = corr_with_series(r[oos_mask(r.index)], prod_oos)
    print(f"  n_hold={n:>2}: IS {s_is['sharpe']:.4f}  OOS {s_oos['sharpe']:.4f}  "
          f"MaxDD {s_oos['max_drawdown']*100:.1f}%  NegYrs {s_oos['neg_years']}  Corr {corr_p:.3f}")
    sweep_results.append({"n_hold": n, "is_sharpe": s_is["sharpe"],
                          "oos_sharpe": s_oos["sharpe"], "max_drawdown": s_oos["max_drawdown"],
                          "neg_years": s_oos["neg_years"], "corr_prod": corr_p})

# ── SPY benchmark ─────────────────────────────────────────────────────────────
print("\n[4] SPY benchmark …")
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_m = spy_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
spy_oos = stats(spy_m[oos_mask(spy_m.index)])
print(f"  SPY OOS: Sharpe={spy_oos['sharpe']:.4f}  MaxDD={spy_oos['max_drawdown']*100:.1f}%")

# ── Confirmation gate ─────────────────────────────────────────────────────────
print("\n[5] Confirmation gate check …")
# Use Variant A 12-1 top-5 as the primary result
primary_oos = s_a_12_1_oos
print(f"  Primary (Var A, top-5, 12-1) OOS Sharpe: {primary_oos['sharpe']:.4f}")
print(f"  Gate: OOS Sharpe > 1.0 → {'PASS' if primary_oos['sharpe'] > 1.0 else 'FAIL'}")
print(f"  Skip-month improves on 12-0: {'+' if s_a_12_1_oos['sharpe'] > s_a_12_0_oos['sharpe'] else '-'}")
print(f"  Corr vs production (Var A 12-1): {corr_a_12_1_prod:.3f}")
print(f"  Production-additive (Corr < 0.6 AND OOS > 1.0): "
      f"{'YES' if corr_a_12_1_prod < 0.6 and primary_oos['sharpe'] > 1.0 else 'NO'}")
print(f"\n  ⚠️  SURVIVORSHIP BIAS WARNING: Fixed universe selected with foreknowledge of 2026 survival.")
print(f"  Results are materially inflated. NOT production-ready.")
print(f"  True OOS requires historical NASDAQ constituent data (unavailable without Compustat/Bloomberg).")

confirmed = bool(primary_oos['sharpe'] > 1.0)
print(f"\n  H277 {'CONFIRMED' if confirmed else 'NOT CONFIRMED'} "
      f"(with survivorship bias caveat)" if confirmed else "")

# ── Save results ──────────────────────────────────────────────────────────────
output = {
    "hypothesis": "H277",
    "description": "NASDAQ Stock Momentum 12-1 Skip-Month Signal",
    "confirmed": confirmed,
    "survivorship_bias_warning": True,
    "variant_a": {
        "universe_size": len(UNIVERSE_A),
        "signal": "12-1 skip-month",
        "n_hold": 5,
        "is_sharpe": s_a_12_1_is["sharpe"],
        "oos_sharpe": s_a_12_1_oos["sharpe"],
        "oos_cagr": s_a_12_1_oos["cagr"],
        "oos_max_drawdown": s_a_12_1_oos["max_drawdown"],
        "oos_neg_years": s_a_12_1_oos["neg_years"],
        "corr_production": round(corr_a_12_1_prod, 4),
    },
    "variant_a_12_0_comparison": {
        "signal": "12-0 no-skip (H272 style)",
        "is_sharpe": s_a_12_0_is["sharpe"],
        "oos_sharpe": s_a_12_0_oos["sharpe"],
        "corr_production": round(corr_a_12_0_prod, 4),
        "skip_month_delta": round(s_a_12_1_oos["sharpe"] - s_a_12_0_oos["sharpe"], 4),
    },
    "variant_b": {
        "universe_size": len(valid_b),
        "signal": "12-1 skip-month",
        "n_hold": 5,
        "is_sharpe": s_b_12_1_is["sharpe"],
        "oos_sharpe": s_b_12_1_oos["sharpe"],
        "oos_max_drawdown": s_b_12_1_oos["max_drawdown"],
        "oos_neg_years": s_b_12_1_oos["neg_years"],
        "corr_production": round(corr_b_prod, 4),
    },
    "n_hold_sweep": sweep_results,
    "spy_oos_sharpe": spy_oos["sharpe"],
    "production_oos_sharpe": stats(prod_oos)["sharpe"],
}

out_path = RESULT_DIR / "h277_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
