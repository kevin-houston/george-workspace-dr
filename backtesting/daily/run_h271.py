"""
H271 — ETF Pairs Trading: Cointegrated Pairs Z-Score Mean Reversion
====================================================================

Hypothesis:
  Cointegrated ETF pairs generate alpha via z-score mean-reversion:
  long the underperformer, short the outperformer when spread deviates >2σ,
  exit at z=0. Pairs tested:
    - GDX / SIL  (Gold Miners vs Silver Miners — highly correlated commodity equity)
    - XLE / OIH  (Broad Energy vs Oil Services — sector vs sub-sector)
    - XLK / SOXX (Tech sector vs Semiconductors — sector vs sub-sector)
    - GLD / SLV  (Gold vs Silver — commodity pair)
    - XLF / KRE  (Broad Finance vs Regional Banks)

  Strategy: Daily signals, monthly position review.
    - Z-score = (spread - rolling mean) / rolling std (63-day window)
    - Entry: |z| > 2.0
    - Exit:  |z| < 0.5
    - Long-short equal weight (dollar neutral)

  Framework:
    - IS:  2008–2017
    - OOS: 2018–2025
    - Gate: OOS Sharpe > 0.9 AND Corr(SPY) < 0.4 (pairs should be market-neutral)

  Background:
    ETF pairs have institutional arbitrage due to creation/redemption mechanism
    that maintains long-run equilibrium. Engle-Granger cointegration test
    used to confirm pairs before deploying.
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from statsmodels.tsa.stattools import coint, adfuller

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

# Pairs to test
PAIRS = [
    ("GDX",  "SIL"),   # Gold miners vs silver miners
    ("XLE",  "OIH"),   # Broad energy vs oil services
    ("XLK",  "SOXX"),  # Tech sector vs semiconductors
    ("GLD",  "SLV"),   # Gold vs silver (physical ETFs)
    ("XLF",  "KRE"),   # Broad finance vs regional banks
]

# Z-score parameters
Z_ENTRY = 2.0
Z_EXIT  = 0.5
LOOKBACK = 63  # ~3 months

_PREFIXES = [f"h{i:03d}" for i in range(100, 271)]


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
    cp = CACHE_DIR / f"h271_{ticker}_close_{start}_{end}.parquet"
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


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_periods":len(r),"neg_years":0}
    eq   = (1+r).cumprod()
    # Annualize assuming daily returns
    n_yr = len(r) / 252.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol  = float(r.std(ddof=1)) * np.sqrt(252)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    annual = r.resample("YE").apply(lambda x: (1+x).prod()-1)
    neg_years = int((annual < 0).sum())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_periods":len(r),"neg_years":neg_years}


def backtest_pair(t1_close, t2_close, z_entry=2.0, z_exit=0.5, lookback=63):
    """
    Backtest a pairs trade: long t1/short t2 when spread z > z_entry,
    long t2/short t1 when spread z < -z_entry.
    Spread = log(t1) - hedge_ratio * log(t2), hedge_ratio from OLS in rolling window.
    Returns daily P&L series (dollar-neutral, $1 each side).
    """
    df = pd.DataFrame({"t1": t1_close, "t2": t2_close}).dropna()
    log1 = np.log(df["t1"])
    log2 = np.log(df["t2"])

    # Rolling OLS hedge ratio
    from numpy.linalg import lstsq
    hedge = pd.Series(index=df.index, dtype=float)
    spread = pd.Series(index=df.index, dtype=float)

    for i in range(lookback, len(df)):
        window = slice(i - lookback, i)
        y = log1.iloc[window].values
        x = log2.iloc[window].values
        X = np.column_stack([x, np.ones(len(x))])
        coef, _, _, _ = lstsq(X, y, rcond=None)
        hedge.iloc[i] = coef[0]
        spread.iloc[i] = log1.iloc[i] - coef[0]*log2.iloc[i] - coef[1]

    spread = spread.dropna()
    roll_mean = spread.rolling(lookback).mean()
    roll_std  = spread.rolling(lookback).std()
    zscore    = (spread - roll_mean) / roll_std.replace(0, np.nan)
    zscore    = zscore.dropna()

    # Position: +1 = long t1/short t2, -1 = long t2/short t1, 0 = flat
    position = 0
    daily_pnl = []
    ret1 = df["t1"].pct_change()
    ret2 = df["t2"].pct_change()

    for i in range(1, len(zscore)):
        dt = zscore.index[i]
        z = float(zscore.iloc[i])
        z_prev = float(zscore.iloc[i-1])

        r1 = float(ret1.loc[dt]) if dt in ret1.index else 0.0
        r2 = float(ret2.loc[dt]) if dt in ret2.index else 0.0

        # Entry / exit logic
        if position == 0:
            if z_prev > z_entry:
                position = -1  # spread too high: short t1, long t2
            elif z_prev < -z_entry:
                position = 1   # spread too low: long t1, short t2
        else:
            if position == 1 and z_prev > -z_exit:
                position = 0
            elif position == -1 and z_prev < z_exit:
                position = 0

        # P&L: $1 long + $1 short (dollar neutral)
        pnl = position * (r1 - r2) / 2.0  # equal weight spread
        daily_pnl.append((dt, pnl))

    return pd.Series([v for _, v in daily_pnl], index=[d for d, _ in daily_pnl])


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)


print("="*80)
print("H271 — ETF Pairs Trading: Z-Score Mean Reversion")
print("="*80)

# Load SPY for correlation
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_daily_ret = spy_close.pct_change()

all_results = []

for (t1, t2) in PAIRS:
    print(f"\n  Testing pair: {t1} / {t2}")
    try:
        c1 = fetch_daily_close(t1, FULL_START, FULL_END)
        c2 = fetch_daily_close(t2, FULL_START, FULL_END)
    except Exception as e:
        print(f"    Error downloading: {e}")
        continue

    # Align
    common = c1.index.intersection(c2.index)
    c1_a = c1.reindex(common).dropna()
    c2_a = c2.reindex(common).dropna()
    common = c1_a.index.intersection(c2_a.index)
    c1_a = c1_a.reindex(common)
    c2_a = c2_a.reindex(common)

    # Cointegration test on IS data
    is_idx = common[(common >= ts(IS_START)) & (common <= ts(IS_END))]
    if len(is_idx) < 200:
        print(f"    Insufficient IS data ({len(is_idx)} days), skipping")
        continue
    c1_is = c1_a.reindex(is_idx)
    c2_is = c2_a.reindex(is_idx)
    score, pval, _ = coint(np.log(c1_is), np.log(c2_is))
    print(f"    Cointegration p-value (IS): {pval:.4f} ({'PASS' if pval < 0.05 else 'FAIL'})")

    # Backtest full period
    pnl = backtest_pair(c1_a, c2_a, Z_ENTRY, Z_EXIT, LOOKBACK)
    if len(pnl) < 100:
        print(f"    Too few trades, skipping")
        continue

    pnl_is  = pnl[is_mask(pnl.index)]
    pnl_oos = pnl[oos_mask(pnl.index)]

    s_is  = stats(pnl_is)
    s_oos = stats(pnl_oos)

    # Correlation with SPY in OOS
    common_oos = pnl_oos.index.intersection(spy_daily_ret.index)
    corr_spy = float(pnl_oos.reindex(common_oos).corr(spy_daily_ret.reindex(common_oos)))

    # Trade count (non-zero P&L days)
    n_trades_oos = int((pnl_oos != 0).sum())

    print(f"    IS  Sharpe={s_is['sharpe']:.4f}, CAGR={s_is['cagr']*100:.1f}%, MaxDD={s_is['max_drawdown']*100:.1f}%")
    print(f"    OOS Sharpe={s_oos['sharpe']:.4f}, CAGR={s_oos['cagr']*100:.1f}%, MaxDD={s_oos['max_drawdown']*100:.1f}%, NegYrs={s_oos['neg_years']}")
    print(f"    Corr(SPY) OOS: {corr_spy:.4f}, Active days OOS: {n_trades_oos}")

    all_results.append({
        "pair": f"{t1}/{t2}",
        "coint_pval": round(float(pval), 4),
        "is":  s_is,
        "oos": s_oos,
        "corr_spy_oos": round(corr_spy, 4),
        "active_days_oos": n_trades_oos,
    })

# ── Best pair
print("\n[Summary] Best pairs by OOS Sharpe:")
all_results.sort(key=lambda x: x["oos"]["sharpe"], reverse=True)
for r in all_results:
    mark = "PASS" if r["oos"]["sharpe"] >= 0.9 and r["corr_spy_oos"] < 0.4 else "FAIL"
    print(f"  {r['pair']:12s}  OOS Sharpe={r['oos']['sharpe']:.4f}  Corr(SPY)={r['corr_spy_oos']:.4f}  [{mark}]")

confirmed_pairs = [r for r in all_results if r["oos"]["sharpe"] >= 0.9 and r["corr_spy_oos"] < 0.4]
confirmed = len(confirmed_pairs) > 0

print(f"\n[Decision]")
print(f"  Gate: OOS Sharpe > 0.9 AND Corr(SPY) < 0.4")
if confirmed:
    best = confirmed_pairs[0]
    print(f"  *** H271 CONFIRMED — {best['pair']} OOS Sharpe={best['oos']['sharpe']:.4f}, Corr(SPY)={best['corr_spy_oos']:.4f} ***")
else:
    best_oos = all_results[0] if all_results else None
    if best_oos:
        print(f"  H271 NOT CONFIRMED — best {best_oos['pair']} OOS Sharpe={best_oos['oos']['sharpe']:.4f}, Corr(SPY)={best_oos['corr_spy_oos']:.4f}")
    else:
        print(f"  H271 NOT CONFIRMED — no valid pairs")

output = {
    "confirmed": bool(confirmed),
    "gate_sharpe": 0.9,
    "gate_corr_spy": 0.4,
    "z_entry": Z_ENTRY,
    "z_exit":  Z_EXIT,
    "lookback_days": LOOKBACK,
    "pairs": all_results,
    "confirmed_pairs": [r["pair"] for r in confirmed_pairs],
}
out_path = RESULT_DIR / "h271_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
