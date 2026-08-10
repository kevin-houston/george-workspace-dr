"""
H501 — True Long-Short Low-Vol-Minus-High-Vol Spread (§3.4, Kakushadze & Serur)
================================================================================

Purpose:
  The task's Priority #1 explicitly frames §3.4 as "Long low-vol, short/avoid
  high-vol ETFs." H113 (2026-04-28, NOT CONFIRMED) tested this on H041A/H026,
  but only as a LONG-ONLY pure inverse-vol rank ("avoid" branch) — the signal
  degenerated to always picking BIL (lowest-vol asset in any broad universe),
  earning ~T-bill returns. H113 never actually built a SHORT leg, so the
  literal "long low-vol, SHORT high-vol" spread trade from the source material
  has never been tested.

  This hypothesis builds a genuine dollar-neutral long-short spread: each
  month, rank the universe by trailing 6m annualized realized vol, go long
  the N lowest-vol assets (equal weight) and short the N highest-vol assets
  (equal weight), monthly rebalance. Tested on:
    Var A: H026 universe (23 sector/alt ETFs) — within-universe spread
    Var B: H041a universe (19 global assets) — within-universe spread
    Var C: Factor low-vol ETFs (USMV/SPLV/XLU/SPHD/EFAV/EEMV/ACWV, per H354)
           long leg vs H026 high-vol short leg — literal factor-ETF framing
           from the H113 hypothesis text ("Also test factor ETF universe").

  Gate (standalone diversifier convention, per H298/H311/H354 precedent):
  OOS Sharpe > SPY buy-and-hold OOS Sharpe. Also reports correlation vs the
  current production blend (H041a/H026/H045/XLK-IBS/SMH-IBS/IGV-IBS) to
  answer the task's explicit "is it additive" question for any variant that
  passes.

  Framework: IS 2008-2017, OOS 2018-2026, AltOOS 2013-2026, WF min=1.75.
  Reuses run_h112.py's caching/stats helpers (verified via run_h500).
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

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

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
FACTOR_LOWVOL = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV"]

_PREFIXES = [f"h{i:03d}" for i in range(62, 113)] + ["h500", "h501"]


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
    cp = CACHE_DIR / f"h501_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def to_monthly_ret(daily_df):
    return daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)


def build_longshort(long_tickers, short_tickers, start, end, n_side=3):
    """Dollar-neutral: long N lowest-vol of long_tickers, short N highest-vol
    of short_tickers, 6m trailing realized vol, monthly rebalance."""
    all_t = sorted(set(long_tickers) | set(short_tickers))
    closes = {}
    for t in all_t:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_ret = to_monthly_ret(daily_df)
    vol_6 = monthly_ret.rolling(6).std() * np.sqrt(12)

    rows = []
    for i in range(6, len(monthly_ret)):
        vol_row = vol_6.iloc[i].dropna()
        long_pool  = vol_row.index.intersection(long_tickers)
        short_pool = vol_row.index.intersection(short_tickers)
        if len(long_pool) < n_side or len(short_pool) < n_side:
            continue
        long_legs  = vol_row[long_pool].nsmallest(n_side).index
        short_legs = vol_row[short_pool].nlargest(n_side).index
        long_ret  = monthly_ret.iloc[i][long_legs].mean()
        short_ret = monthly_ret.iloc[i][short_legs].mean()
        spread = long_ret - short_ret
        rows.append((monthly_ret.index[i], spread))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ai_mask(idx):  return (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


print("="*80)
print("H501 — True Long-Short Low-Vol-Minus-High-Vol Spread")
print("="*80)

print("\n[0] SPY buy-and-hold benchmark …")
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_mret = spy_close.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1).dropna()
spy_oos = stats(spy_mret[oos_mask(spy_mret.index)])["sharpe"]
spy_ao  = stats(spy_mret[ao_mask(spy_mret.index)])["sharpe"]
print(f"    SPY OOS Sharpe = {spy_oos:.4f}, AltOOS Sharpe = {spy_ao:.4f}")

print("\n[1] Var A: H026 universe, long-3 lowest-vol / short-3 highest-vol …")
varA = build_longshort(H026_BASE, H026_BASE, FULL_START, FULL_END, n_side=3)

print("\n[2] Var B: H041a universe, long-3 lowest-vol / short-3 highest-vol …")
varB = build_longshort(H041A_FULL, H041A_FULL, FULL_START, FULL_END, n_side=3)

print("\n[3] Var C: Factor low-vol ETFs (long) vs H026 high-vol (short) …")
varC = build_longshort(FACTOR_LOWVOL, H026_BASE, FULL_START, FULL_END, n_side=3)

VARIANTS = {"A_H026_within_universe": varA, "B_H041a_within_universe": varB,
            "C_FactorETF_long_vs_H026_short": varC}

print(f"\n{'Variant':40s} {'OOS':>8s} {'AltOOS':>8s} {'MaxDD':>8s} {'Beats SPY':>10s}")
print("-"*80)
results = {"spy_oos": spy_oos, "spy_ao": spy_ao, "variants": {}, "confirmed": False, "winners": []}
for name, r in VARIANTS.items():
    s_oos = stats(r[oos_mask(r.index)])
    s_ao  = stats(r[ao_mask(r.index)])
    beats = s_oos["sharpe"] > spy_oos and s_ao["sharpe"] > spy_ao
    flag = "✓" if beats else "✗"
    print(f"{name:40s} {s_oos['sharpe']:8.4f} {s_ao['sharpe']:8.4f} {s_oos['max_drawdown']*100:7.2f}% {flag:>10s}")
    results["variants"][name] = {"oos": s_oos, "altoos": s_ao}
    if beats:
        results["confirmed"] = True
        results["winners"].append(name)

print()
if results["confirmed"]:
    print(f"H501 CONFIRMED for: {results['winners']} — beats SPY OOS/AltOOS Sharpe.")
else:
    print("H501 NOT CONFIRMED — no long-short low-vol/high-vol spread variant")
    print("beats SPY buy-and-hold on both OOS and AltOOS windows.")
    print("Closes the literal §3.4 'long low-vol, short high-vol' framing left")
    print("open by H113 (which only tested a long-only avoid-high-vol rank).")

out_path = RESULT_DIR / "h501_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults saved → {out_path}")
