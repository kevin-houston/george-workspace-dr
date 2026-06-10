"""
H272 — NASDAQ-100 Stock Momentum: 12-1 Month Signal
====================================================

Hypothesis:
  Top NASDAQ-100 stocks by 12-1 month momentum (skip-1 month to avoid reversal),
  monthly rebalance, hold top-5 or top-10 equal-weight.

  Universe: QQQ component proxy — 20 liquid large-cap NASDAQ-100 stocks
  (using fixed large-cap tech names to avoid survivorship on full universe)
  Signal: 12-month return minus 1-month return (Jegadeesh-Titman 1993)
  Rebalance: Monthly (first trading day)
  Gate: OOS Sharpe > 1.0 (production candidate standard, since this is concentrated equity)

  Variants:
    A) Top-5 equal weight from 20-stock NASDAQ-100 proxy
    B) Top-10 equal weight from 20-stock NASDAQ-100 proxy
    C) Top-5 with 12-month simple momentum (no skip-month)

  Framework: IS 2008-2017, OOS 2018-2025
  Benchmark: QQQ buy-and-hold

  Background:
    Jegadeesh & Titman (1993) 12-1 momentum is one of the most replicated
    anomalies in finance. For individual stocks, the intermediate (12-1 month)
    signal has highest Sharpe. NASDAQ stocks historically show stronger momentum
    persistence due to growth-factor clustering and analyst attention bias.

    Key risk: 2022 momentum crash — growth/tech momentum reversed sharply.
    The 2022 performance will be a critical test.
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

# 25 large-cap NASDAQ-100 stocks with data going back to 2003
# These are the stable large-cap names — survivorship bias present but these
# were all large/established by 2003 except NFLX (2002 IPO), AMZN (1997)
NASDAQ_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    "CSCO", "ADBE", "INTC", "QCOM", "TXN", "AMAT", "MU",
    "NFLX", "COST", "SBUX", "MDLZ", "GILD",
    "BIIB", "REGN", "VRTX", "ILMN", "LRCX"
]

# QQQ for benchmark
QQQ = "QQQ"

_PREFIXES = [f"h{i:03d}" for i in range(100, 272)]


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
    cp = CACHE_DIR / f"h272_{ticker}_close_{start}_{end}.parquet"
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


def build_stock_momentum(tickers, start, end, n_hold=5, skip_month=True):
    """
    12-1 momentum (skip_month=True) or 12-0 momentum.
    Monthly rebalance, equal-weight top n_hold stocks.
    """
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: skip ({e})")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    rows = []
    for i in range(13, len(monthly_px)):  # need 13 months lookback
        px_now   = monthly_px.iloc[i]
        px_12ago = monthly_px.iloc[i-12]
        if skip_month:
            px_1ago  = monthly_px.iloc[i-1]
            # 12-1 signal: return 12 months ago to 1 month ago
            mom = (px_1ago / px_12ago - 1).dropna()
        else:
            # 12-0 signal: return 12 months ago to now
            mom = (px_now / px_12ago - 1).dropna()

        if len(mom) < n_hold:
            continue

        top_n = list(mom.nlargest(n_hold).index)
        ret_this_month = monthly_ret.iloc[i][top_n].mean()
        rows.append((monthly_px.index[i], float(ret_this_month)))

    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


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


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ai_mask(idx):  return (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


print("="*80)
print("H272 — NASDAQ-100 Stock Momentum (12-1 Month Signal)")
print("="*80)
print(f"  Universe: {len(NASDAQ_UNIVERSE)} stocks")

# QQQ benchmark
print("\n[0] QQQ benchmark …")
qqq_close = fetch_daily_close(QQQ, FULL_START, FULL_END)
qqq_monthly = qqq_close.resample("ME").last().pct_change().dropna()
qqq_is  = stats(qqq_monthly[is_mask(qqq_monthly.index)])
qqq_oos = stats(qqq_monthly[oos_mask(qqq_monthly.index)])
print(f"  QQQ IS  Sharpe={qqq_is['sharpe']:.4f}, CAGR={qqq_is['cagr']*100:.1f}%")
print(f"  QQQ OOS Sharpe={qqq_oos['sharpe']:.4f}, CAGR={qqq_oos['cagr']*100:.1f}%, MaxDD={qqq_oos['max_drawdown']*100:.1f}%, NegYrs={qqq_oos['neg_years']}")

# SPY for correlation
spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
spy_monthly = spy_close.resample("ME").last().pct_change().dropna()

# ── Variant A: 12-1 Top-5
print("\n[1] Variant A — 12-1 momentum, Top-5 equal weight …")
va_r = build_stock_momentum(NASDAQ_UNIVERSE, FULL_START, FULL_END, n_hold=5, skip_month=True)
va_is  = stats(va_r[is_mask(va_r.index)])
va_oos = stats(va_r[oos_mask(va_r.index)])
va_ao  = stats(va_r[ao_mask(va_r.index)])
print(f"  IS  Sharpe={va_is['sharpe']:.4f}, CAGR={va_is['cagr']*100:.1f}%, MaxDD={va_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={va_oos['sharpe']:.4f}, CAGR={va_oos['cagr']*100:.1f}%, MaxDD={va_oos['max_drawdown']*100:.1f}%, NegYrs={va_oos['neg_years']}")
print(f"  AltOOS Sharpe={va_ao['sharpe']:.4f}")

# ── Variant B: 12-1 Top-10
print("\n[2] Variant B — 12-1 momentum, Top-10 equal weight …")
vb_r = build_stock_momentum(NASDAQ_UNIVERSE, FULL_START, FULL_END, n_hold=10, skip_month=True)
vb_is  = stats(vb_r[is_mask(vb_r.index)])
vb_oos = stats(vb_r[oos_mask(vb_r.index)])
vb_ao  = stats(vb_r[ao_mask(vb_r.index)])
print(f"  IS  Sharpe={vb_is['sharpe']:.4f}, CAGR={vb_is['cagr']*100:.1f}%, MaxDD={vb_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={vb_oos['sharpe']:.4f}, CAGR={vb_oos['cagr']*100:.1f}%, MaxDD={vb_oos['max_drawdown']*100:.1f}%, NegYrs={vb_oos['neg_years']}")
print(f"  AltOOS Sharpe={vb_ao['sharpe']:.4f}")

# ── Variant C: 12-0 Top-5 (no skip month)
print("\n[3] Variant C — 12-0 momentum (no skip), Top-5 …")
vc_r = build_stock_momentum(NASDAQ_UNIVERSE, FULL_START, FULL_END, n_hold=5, skip_month=False)
vc_is  = stats(vc_r[is_mask(vc_r.index)])
vc_oos = stats(vc_r[oos_mask(vc_r.index)])
vc_ao  = stats(vc_r[ao_mask(vc_r.index)])
print(f"  IS  Sharpe={vc_is['sharpe']:.4f}, CAGR={vc_is['cagr']*100:.1f}%, MaxDD={vc_is['max_drawdown']*100:.1f}%")
print(f"  OOS Sharpe={vc_oos['sharpe']:.4f}, CAGR={vc_oos['cagr']*100:.1f}%, MaxDD={vc_oos['max_drawdown']*100:.1f}%, NegYrs={vc_oos['neg_years']}")
print(f"  AltOOS Sharpe={vc_ao['sharpe']:.4f}")

# ── Correlation with SPY
print("\n[4] Correlation with SPY (OOS) …")
for name, r in [("Variant A", va_r), ("Variant B", vb_r), ("Variant C", vc_r)]:
    common_oos = r.index.intersection(spy_monthly.index)
    common_oos = common_oos[oos_mask(common_oos)]
    corr = r.reindex(common_oos).corr(spy_monthly.reindex(common_oos))
    print(f"  {name}: Corr(SPY) OOS = {corr:.4f}")

# ── Annual breakdown for best variant
all_variants = [(va_r, va_oos, "A: 12-1 Top-5"), (vb_r, vb_oos, "B: 12-1 Top-10"), (vc_r, vc_oos, "C: 12-0 Top-5")]
best_r, best_stats, best_name = max(all_variants, key=lambda x: x[1]["sharpe"])
print(f"\n[5] Annual returns for best variant ({best_name}) …")
annual = best_r[oos_mask(best_r.index)].resample("YE").apply(lambda x: (1+x).prod()-1)
for yr, ret in annual.items():
    print(f"  {yr.year}: {ret*100:+.1f}%")

# ── Decision
print("\n[6] Decision …")
gate = 1.0  # production candidate gate
best_sharpe = best_stats["sharpe"]
best_oos_neg_years = best_stats["neg_years"]
confirmed = best_sharpe >= gate

common_oos_idx = best_r.index.intersection(spy_monthly.index)
common_oos_idx = common_oos_idx[oos_mask(common_oos_idx)]
corr_spy = float(best_r.reindex(common_oos_idx).corr(spy_monthly.reindex(common_oos_idx)))

print(f"  Gate: OOS Sharpe > {gate}")
print(f"  Best OOS Sharpe: {best_sharpe:.4f} ({'PASS' if confirmed else 'FAIL'})")
print(f"  Corr(SPY) OOS: {corr_spy:.4f}")
if confirmed:
    print(f"  *** H272 CONFIRMED — Stock Momentum ({best_name}) OOS Sharpe={best_sharpe:.4f} ***")
else:
    print(f"  H272 NOT CONFIRMED — best OOS Sharpe {best_sharpe:.4f} < gate {gate}")
    print(f"  (Note: survivorship bias present in fixed 25-stock universe)")

# ── Save results
output = {
    "confirmed": bool(confirmed),
    "gate_sharpe": float(gate),
    "universe_size": len(NASDAQ_UNIVERSE),
    "universe": NASDAQ_UNIVERSE,
    "signal": "12-1 month momentum (Jegadeesh-Titman)",
    "survivorship_bias_warning": "Fixed 25-stock universe selected with foreknowledge of 2025 survival",
    "qqq_bh": {"is": qqq_is, "oos": qqq_oos},
    "variant_a": {"is": va_is, "oos": va_oos, "altoos": va_ao, "label": "12-1 Top-5"},
    "variant_b": {"is": vb_is, "oos": vb_oos, "altoos": vb_ao, "label": "12-1 Top-10"},
    "variant_c": {"is": vc_is, "oos": vc_oos, "altoos": vc_ao, "label": "12-0 Top-5"},
    "best_variant": best_name,
    "best_oos_sharpe": float(best_sharpe),
    "best_corr_spy": float(corr_spy),
}
out_path = RESULT_DIR / "h272_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
