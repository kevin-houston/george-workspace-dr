"""
H313 — Sector-Neutral Stock Momentum
=====================================

Source: Stosik & Zaremba (2025) SSRN 6630998 "Industry-Adjusted Momentum"
        Moskowitz & Grinblatt (1999) "Do Industries Explain Momentum?" (JF)
        Grundy & Martin (2001) "Understanding the Nature of the Risks and the
        Source of the Rewards to Momentum Investing" (RFS)

Hypothesis:
  Standard stock momentum (H312-B OOS Sharpe 1.202) is contaminated by industry
  momentum. The sector-neutral signal R_i − R̄_sector removes this industry
  component and isolates firm-specific momentum, which should have:
  - Lower correlation with SPY (sector noise removed)
  - More stable IS/OOS properties (fundamental rather than macro-driven)
  - Stosik & Zaremba: 0.53%/month globally, Sharpe ~0.74 long-only; long-short
    generates stronger signal but requires short capability

  Variants tested:
  A: Raw 12-1 momentum (baseline, same as H312-B for reference)
  B: Sector-neutral 12-1 (stock excess return vs GICS sector average)
  C: Sector-neutral 3m (shorter horizon)
  D: Composite: 70% sector-neutral 12-1 + 30% sector-neutral 3m (Stosik weight)
  E: Sector-neutral 12-1 with low-vol overlay (avoid high-vol names in top-20)

IS:  2010-01-01 to 2019-12-31
OOS: 2020-01-01 to 2026-06-19
Gate: OOS Sharpe > 1.10 AND Corr(SPY) < 0.80 (lower than H312 baseline)
"""

import sys
import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ── Universe with sector labels ───────────────────────────────────────────────
UNIVERSE_SECTORS = {
    # Technology
    "AAPL":"Tech","MSFT":"Tech","NVDA":"Tech","AVGO":"Tech","ORCL":"Tech",
    "CSCO":"Tech","INTC":"Tech","TXN":"Tech","QCOM":"Tech","AMD":"Tech",
    "IBM":"Tech","AMAT":"Tech","MU":"Tech","ADI":"Tech","KLAC":"Tech",
    # Communication
    "GOOGL":"Comm","META":"Comm","NFLX":"Comm","CMCSA":"Comm",
    "DIS":"Comm","VZ":"Comm","T":"Comm",
    # Consumer Discretionary
    "AMZN":"ConDisc","HD":"ConDisc","MCD":"ConDisc","NKE":"ConDisc",
    "SBUX":"ConDisc","TGT":"ConDisc","LOW":"ConDisc","COST":"ConDisc","BKNG":"ConDisc",
    # Consumer Staples
    "KO":"ConStap","PEP":"ConStap","PG":"ConStap","WMT":"ConStap",
    "CL":"ConStap","MO":"ConStap","PM":"ConStap",
    # Healthcare
    "JNJ":"Health","LLY":"Health","UNH":"Health","ABBV":"Health",
    "MRK":"Health","BMY":"Health","PFE":"Health","AMGN":"Health",
    "GILD":"Health","MDT":"Health","ABT":"Health",
    # Financials
    "JPM":"Fin","BAC":"Fin","WFC":"Fin","GS":"Fin","MS":"Fin",
    "BLK":"Fin","AXP":"Fin","V":"Fin","MA":"Fin","SCHW":"Fin",
    "C":"Fin","USB":"Fin","PNC":"Fin",
    # Industrials
    "CAT":"Ind","DE":"Ind","HON":"Ind","MMM":"Ind","GE":"Ind",
    "UPS":"Ind","FDX":"Ind","BA":"Ind","LMT":"Ind","RTX":"Ind",
    # Energy
    "XOM":"Energy","CVX":"Energy","COP":"Energy","SLB":"Energy",
    "EOG":"Energy","PSX":"Energy","VLO":"Energy",
    # Materials/Utilities/REITs
    "LIN":"Matl","SHW":"Matl","FCX":"Matl",
    "NEE":"Util","DUK":"Util",
    "PLD":"REIT","AMT":"REIT",
}
STOCKS = list(UNIVERSE_SECTORS.keys())
SECTORS = {s: [t for t, sec in UNIVERSE_SECTORS.items() if sec == s]
           for s in set(UNIVERSE_SECTORS.values())}
ALL_TICKERS = STOCKS + ["SPY"]

IS_START   = "2009-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-19"
TRADING_DAYS = 252
N_HOLD = 20

print("H313 — Sector-Neutral Stock Momentum")
print("=" * 60)

print("Downloading price data…")
raw = yf.download(ALL_TICKERS, start=IS_START, end=OOS_END,
                  progress=False, auto_adjust=True)
prices = raw["Close"]
prices.dropna(axis=1, how="all", inplace=True)
spx = prices["SPY"]
prices_s = prices[[t for t in STOCKS if t in prices.columns]]
avail_stocks = prices_s.columns.tolist()
print(f"  {len(avail_stocks)} stocks loaded")

month_ends = prices_s.resample("BME").last().index

def stock_mom(px, t0, months):
    """12-1 or 3m momentum up to t0."""
    p = px[px.index <= t0]
    if months == 12:
        if len(p) < 253: return np.nan
        return float(p.iloc[-1] / p.iloc[-252] - 1) - float(p.iloc[-1] / p.iloc[-22] - 1)
    elif months == 3:
        if len(p) < 64: return np.nan
        return float(p.iloc[-1] / p.iloc[-63] - 1)
    return np.nan

def stock_vol(px, t0):
    p = px[px.index <= t0]
    if len(p) < 23: return np.nan
    r = np.log(p.iloc[-22:] / p.iloc[-22:].shift(1)).dropna()
    return float(r.std(ddof=1) * np.sqrt(TRADING_DAYS))

# ── Build monthly signal table ────────────────────────────────────────────────
print("Computing sector-neutral factors…")

all_records = {v: [] for v in ["A","B","C","D","E"]}

for i in range(14, len(month_ends) - 1):
    t0 = month_ends[i]
    t1 = month_ends[i+1]

    raw_m12, raw_m3, vols = {}, {}, {}
    for sym in avail_stocks:
        px = prices_s[sym].dropna()
        raw_m12[sym] = stock_mom(px, t0, 12)
        raw_m3[sym]  = stock_mom(px, t0, 3)
        vols[sym]    = stock_vol(px, t0)

    # Sector averages (equal-weight)
    sec_avg_12, sec_avg_3 = {}, {}
    for sec, members in SECTORS.items():
        m12_vals = [raw_m12[s] for s in members if s in raw_m12 and not np.isnan(raw_m12.get(s, np.nan))]
        m3_vals  = [raw_m3[s]  for s in members if s in raw_m3  and not np.isnan(raw_m3.get(s, np.nan))]
        sec_avg_12[sec] = np.mean(m12_vals) if m12_vals else np.nan
        sec_avg_3[sec]  = np.mean(m3_vals)  if m3_vals  else np.nan

    # Signals
    sig = {}
    for sym in avail_stocks:
        sec = UNIVERSE_SECTORS.get(sym)
        m12 = raw_m12.get(sym, np.nan)
        m3  = raw_m3.get(sym, np.nan)
        v   = vols.get(sym, np.nan)
        sa12 = sec_avg_12.get(sec, np.nan)
        sa3  = sec_avg_3.get(sec, np.nan)
        sig[sym] = {
            "A": m12 if not np.isnan(m12) else np.nan,
            "B": (m12 - sa12) if not (np.isnan(m12) or np.isnan(sa12)) else np.nan,
            "C": (m3  - sa3)  if not (np.isnan(m3)  or np.isnan(sa3))  else np.nan,
            "D": (0.7*(m12-sa12) + 0.3*(m3-sa3)) if not any(np.isnan(x) for x in [m12,sa12,m3,sa3]) else np.nan,
            "E_signal": (m12-sa12) if not (np.isnan(m12) or np.isnan(sa12)) else np.nan,
            "E_vol": v,
        }

    # Portfolio returns for each variant
    spy_hold = spx[(spx.index > t0) & (spx.index <= t1)]
    spy_ret  = float(spy_hold.iloc[-1] / spy_hold.iloc[0] - 1) if len(spy_hold) >= 5 else np.nan

    for variant in ["A","B","C","D"]:
        scores = {s: sig[s][variant] for s in avail_stocks if not np.isnan(sig[s].get(variant, np.nan))}
        if len(scores) < N_HOLD + 5: continue
        top20 = sorted(scores, key=lambda s: -scores[s])[:N_HOLD]
        rets = []
        for sym in top20:
            px = prices_s[sym].dropna()
            ph = px[(px.index > t0) & (px.index <= t1)]
            if len(ph) >= 5: rets.append(float(ph.iloc[-1] / ph.iloc[0] - 1))
        if rets:
            all_records[variant].append({"date": t0, "ret": float(np.mean(rets)), "spy_ret": spy_ret})

    # Variant E: sector-neutral 12-1 with low-vol overlay (exclude top-half by vol)
    e_scores = {s: sig[s]["E_signal"] for s in avail_stocks
                if not np.isnan(sig[s].get("E_signal", np.nan)) and not np.isnan(sig[s].get("E_vol", np.nan))}
    if len(e_scores) >= N_HOLD + 5:
        vol_median = np.median([sig[s]["E_vol"] for s in e_scores])
        e_filtered = {s: v for s, v in e_scores.items() if sig[s]["E_vol"] <= vol_median}
        if len(e_filtered) >= N_HOLD:
            top20e = sorted(e_filtered, key=lambda s: -e_filtered[s])[:N_HOLD]
            rets_e = []
            for sym in top20e:
                px = prices_s[sym].dropna()
                ph = px[(px.index > t0) & (px.index <= t1)]
                if len(ph) >= 5: rets_e.append(float(ph.iloc[-1] / ph.iloc[0] - 1))
            if rets_e:
                all_records["E"].append({"date": t0, "ret": float(np.mean(rets_e)), "spy_ret": spy_ret})

# ── Backtest ──────────────────────────────────────────────────────────────────
def backtest(label, df_sub, spy_sub=None):
    rets = df_sub["ret"]
    if len(rets) < 6:
        print(f"  {label}: n={len(rets)} (insufficient)")
        return None
    s = float(rets.mean() / rets.std(ddof=1) * np.sqrt(12))
    cagr = float((1 + rets).prod() ** (12 / len(rets)) - 1)
    cum = (1 + rets).cumprod()
    dd = float(((cum - cum.cummax()) / cum.cummax()).min())
    wr = float((rets > 0).mean())
    extra = ""
    if spy_sub is not None:
        corr = float(rets.corr(spy_sub["spy_ret"]))
        ir_num = (rets - spy_sub["spy_ret"]).mean()
        ir_den = (rets - spy_sub["spy_ret"]).std(ddof=1)
        ir = float(ir_num / ir_den * np.sqrt(12)) if ir_den > 0 else 0
        extra = f"  Corr(SPY)={corr:.3f}  IR={ir:.3f}"
    print(f"  {label}: Sharpe={s:.3f}  CAGR={cagr:.1%}  MaxDD={dd:.1%}  WR={wr:.0%}  n={len(rets)}{extra}")
    return {"sharpe": s, "cagr": cagr, "max_dd": dd, "win_rate": wr, "n": len(rets)}

results = {}
variant_names = {
    "A": "Raw 12-1 mom (baseline)",
    "B": "Sector-neutral 12-1",
    "C": "Sector-neutral 3m",
    "D": "Composite 70%B+30%C",
    "E": "Sector-neutral 12-1 + low-vol filter",
}
for variant, name in variant_names.items():
    df_v = pd.DataFrame(all_records[variant]).set_index("date")
    df_v.index = pd.to_datetime(df_v.index)
    is_mask  = df_v.index <  pd.Timestamp(OOS_START)
    oos_mask = df_v.index >= pd.Timestamp(OOS_START)
    print(f"\n── {name} ──")
    r_is  = backtest("IS ", df_v[is_mask],  df_v[is_mask])
    r_oos = backtest("OOS", df_v[oos_mask], df_v[oos_mask])
    wf = round(r_oos["sharpe"] / r_is["sharpe"], 3) if r_is and r_oos and r_is["sharpe"] > 0 else None
    if wf: print(f"    WF={wf:.3f}")
    results[variant] = {"is": r_is, "oos": r_oos, "wf": wf}

# ── OOS year-by-year for best variant ────────────────────────────────────────
print("\n─── OOS Year-by-Year (Variant B — Sector-Neutral 12-1) ───")
df_b = pd.DataFrame(all_records["B"]).set_index("date")
df_b.index = pd.to_datetime(df_b.index)
oos_b = df_b[df_b.index >= pd.Timestamp(OOS_START)]
for yr in sorted(oos_b.index.year.unique()):
    yr_df = oos_b[oos_b.index.year == yr]
    if len(yr_df) < 2: continue
    h = float((1 + yr_df["ret"]).prod() - 1)
    s = float((1 + yr_df["spy_ret"]).prod() - 1)
    print(f"  {yr}: H313-B={h:>+6.1%}  SPY={s:>+6.1%}  excess={h-s:>+5.1%}")

# ── Gate check ────────────────────────────────────────────────────────────────
print("\n─── Gate Check (OOS Sharpe > 1.10 AND Corr(SPY) < 0.80) ───")
for v, name in variant_names.items():
    r = results[v]
    if not r["oos"]: continue
    # Recompute Corr for display
    df_v = pd.DataFrame(all_records[v]).set_index("date")
    df_v.index = pd.to_datetime(df_v.index)
    oos_v = df_v[df_v.index >= pd.Timestamp(OOS_START)]
    corr = float(oos_v["ret"].corr(oos_v["spy_ret"]))
    sh = r["oos"]["sharpe"]
    gate = "PASS" if sh > 1.10 and corr < 0.80 else "FAIL"
    print(f"  {v}: OOS Sharpe={sh:.3f}  Corr(SPY)={corr:.3f}  → {gate}  [{name}]")

out = "backtesting/results/h313_results.json"
with open(out, "w") as f:
    json.dump({v: {"is": r["is"], "oos": r["oos"], "wf": r["wf"]}
               for v, r in results.items()}, f, indent=2, default=str)
print(f"\nResults → {out}")
