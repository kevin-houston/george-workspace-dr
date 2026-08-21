"""
H524 -- VIX-Regime-Conditioned Momentum Lookback (Trend-Following)
====================================================================

Source: Alpha Architect, "VIX and Trend Following: Out of Sample" (2026
follow-up to Wesley Gray's 2017 original "VIX and Trend Following: The
Killer Combo"). Primary URL (alphaarchitect.com) is Cloudflare-protected
and could not be fetched directly or via agent-browser; methodology and
2017 baseline figures are drawn from a full-text Yahoo Finance syndication
of the original article, 2026 follow-up figures from WebSearch snippets
only (materially weaker sourcing -- flagged in the wiki note and to Kevin).

Idea: instead of a single fixed trend-following lookback window, condition
the lookback length on the current VIX regime.
  - Green  (calm):     VIX 20d SMA <= 18   -> use a LONG lookback (10m)
  - Yellow (elevated):  18 < VIX 20d SMA < 32 -> use a MEDIUM lookback (3m)
  - Red    (crisis):   VIX 20d SMA >= 32   -> use a SHORT lookback (1m)
The logic: in calm regimes, trends are slow and durable, so a long lookback
avoids whipsaw. In crisis regimes, trends move fast, so a short lookback
reacts quickly. VIX level itself is pulled from FRED (VIXCLS), not yfinance,
to satisfy the project's macro-regime-via-FRED-data convention.

Universe: SPY (US equity), VXF (US extended market / small-mid caps), EFA
(developed intl equity), AGG (US aggregate bond) -- matches the ETF-proxy
universe the 2026 follow-up piece used to modernize the original 10-asset-
class design onto liquid, cheap, long-history ETFs. BIL (T-bill) is the
cash/defensive fallback, used whenever the single best-ranked asset's own
momentum is negative (no forced allocation to a losing asset).

Two selection variants tested: Top-1 (single best asset) and Top-2 (equal
weight two best, both must be individually momentum-positive or replaced
by BIL for that leg).

Baseline (per the article's own comparator): STATIC 10-month lookback
Top-1 / Top-2, no VIX regime switching at all -- isolates the value-add of
the regime-conditional lookback, not of trend-following vs. buy-and-hold.

IS: 2008-01-01 - 2017-12-31 | OOS: 2018-01-01 - present
AltOOS (non-canonical split): 2013-01-01 - present
Gate for adoption: regime-conditional variant beats its own static-lookback
baseline OOS Sharpe by > 0.10 AND clears WF_WORST_MIN = 1.75 walk-forward,
OR meaningfully improves MaxDD (>2pp) without giving back >0.10 Sharpe.

After-tax note: monthly rebalancing => realized gains are overwhelmingly
short-term. Post-tax CAGR is reported as a conservative worst-case estimate
= pre-tax CAGR x (1 - 0.37), per the project's shared eval checklist
("model at 37% for worst-case planning"). This is a rough haircut, not a
lot-level tax simulation.
"""

import json
import os
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from pathlib import Path

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

FULL_START = "2005-01-01"
FULL_END   = "2026-08-19"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_IS_END = "2012-12-31"
ALT_OOS_ST = "2013-01-01"
WF_WORST_MIN = 1.75

UNIVERSE   = ["SPY", "VXF", "EFA", "AGG"]
CASH_PROXY = "BIL"
ALL_TICKERS = UNIVERSE + [CASH_PROXY]

GREEN_MAX  = 18.0
RED_MIN    = 32.0
LOOKBACK   = {"green": 10, "yellow": 3, "red": 1}  # months

TAX_RATE = 0.37  # short-term / worst-case per shared-eval-checklist.md


def fetch_close(tickers, start, end):
    key = "_".join(sorted(tickers))
    cp = CACHE_DIR / f"h524_{key}_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw.to_frame(tickers[0])
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_fred(series_id, start=FULL_START):
    cache_path = CACHE_DIR / f"h524_fred_{series_id}.parquet"
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        return df["value"]
    print(f"  Fetching FRED {series_id}...")
    url = (
        "https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
        f"&observation_start={start}&limit=100000"
    )
    r = requests.get(url, timeout=30)
    data = r.json()
    obs = data.get("observations", [])
    records = [(o["date"], o["value"]) for o in obs if o["value"] != "."]
    df = pd.DataFrame(records, columns=["date", "value"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    df.to_parquet(cache_path)
    return df["value"]


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"cagr": 0.0, "sharpe": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    post_tax_cagr = cagr * (1 - TAX_RATE) if cagr > 0 else cagr
    return {
        "cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
        "max_drawdown": round(max_dd, 4), "n_months": len(r),
        "post_tax_cagr_est": round(post_tax_cagr, 4),
    }


def run_wf(r, min_train=56, test_size=16, n_folds=5):
    is_idx = r.index[r.index >= pd.Timestamp(IS_START)]
    n = len(is_idx)
    folds, start, fold = [], min_train, 0
    while start + test_size <= n and fold < n_folds:
        ti = is_idx[start:start + test_size]
        folds.append(stats(r.reindex(ti, fill_value=0.0))["sharpe"])
        start += test_size
        fold += 1
    return folds


def is_mask(idx):  return (idx >= pd.Timestamp(IS_START)) & (idx <= pd.Timestamp(IS_END))
def oos_mask(idx): return idx >= pd.Timestamp(OOS_START)
def ai_mask(idx):  return idx <= pd.Timestamp(ALT_IS_END)
def ao_mask(idx):  return idx >= pd.Timestamp(ALT_OOS_ST)


def build_vix_regime(vix_daily):
    """VIX 20-day SMA -> Green/Yellow/Red regime, shifted 1 day (no lookahead)."""
    sma20 = vix_daily.rolling(20).mean().shift(1)
    regime = pd.Series(index=sma20.index, dtype=object)
    regime[sma20 <= GREEN_MAX] = "green"
    regime[(sma20 > GREEN_MAX) & (sma20 < RED_MIN)] = "yellow"
    regime[sma20 >= RED_MIN] = "red"
    return regime.dropna()


def monthly_strategy(prices, regime, top_n, regime_conditional):
    """
    Monthly rebalance: rank UNIVERSE by trailing momentum (lookback depends
    on regime if regime_conditional, else fixed 10m), pick top_n positive-
    momentum assets equal-weighted; any unfilled slot (negative momentum or
    regime-conditional degenerate case) goes to CASH_PROXY.
    """
    monthly_px = prices.resample("ME").last()
    idx = monthly_px.index
    rets = []
    dates = []

    # i = decision month (all info known as of idx[i]'s close). The resulting
    # trade is HELD over the next period, idx[i]+1day .. idx[i+1] — never the
    # same period whose own closing price fed the signal (that would be
    # look-ahead, the exact bug class documented for H343/H509/H510 etc.).
    for i in range(11, len(idx) - 1):
        decision_date = idx[i]
        hold_end = idx[i + 1]
        prior_regime = regime.loc[:decision_date]
        cur_regime = prior_regime.iloc[-1] if len(prior_regime) else "yellow"
        lb = LOOKBACK[cur_regime] if regime_conditional else 10
        if i - lb < 0:
            continue

        mom = (monthly_px[UNIVERSE].iloc[i] / monthly_px[UNIVERSE].iloc[i - lb] - 1).dropna()
        if mom.empty:
            continue
        ranked = mom.sort_values(ascending=False)
        picks = list(ranked.index[:top_n])
        weight = 1.0 / top_n

        sub_start = decision_date + pd.Timedelta(days=1)
        sub = prices.loc[sub_start:hold_end]
        if len(sub) < 2:
            continue
        sub_ret = sub.pct_change().dropna(how="all")

        port_ret = pd.Series(0.0, index=sub_ret.index)
        for p in picks:
            leg = p if mom.get(p, -1) >= 0 else CASH_PROXY
            if leg in sub_ret.columns:
                port_ret = port_ret.add(weight * sub_ret[leg].fillna(0.0), fill_value=0.0)

        m_ret = float((1 + port_ret).prod() - 1)
        rets.append(m_ret)
        dates.append(hold_end)

    return pd.Series(rets, index=pd.DatetimeIndex(dates))


def report(label, r):
    is_r  = stats(r[is_mask(r.index)])
    oos_r = stats(r[oos_mask(r.index)])
    ai_r  = stats(r[ai_mask(r.index)])
    ao_r  = stats(r[ao_mask(r.index)])
    wf    = run_wf(r)
    ww    = min(wf) if wf else 0.0
    print(f"\n  {label}")
    print(f"    IS  {IS_START}..{IS_END}:      Sharpe {is_r['sharpe']:.3f}  CAGR {is_r['cagr']*100:.2f}%  MaxDD {is_r['max_drawdown']*100:.2f}%")
    print(f"    OOS {OOS_START}..present:     Sharpe {oos_r['sharpe']:.3f}  CAGR {oos_r['cagr']*100:.2f}%  MaxDD {oos_r['max_drawdown']*100:.2f}%  PostTaxCAGR {oos_r['post_tax_cagr_est']*100:.2f}%")
    print(f"    AltOOS {ALT_OOS_ST}..present:  Sharpe {ao_r['sharpe']:.3f}  CAGR {ao_r['cagr']*100:.2f}%  MaxDD {ao_r['max_drawdown']*100:.2f}%")
    print(f"    Walk-forward worst fold Sharpe: {ww:.3f}  (gate {WF_WORST_MIN})")
    return {"label": label, "is": is_r, "oos": oos_r, "alt_is": stats(r[ai_mask(r.index)]),
            "alt_oos": ao_r, "wf_folds": wf, "wf_worst": round(ww, 3)}


print("=" * 80)
print("H524 -- VIX-Regime-Conditioned Momentum Lookback (Trend-Following)")
print("=" * 80)

print("\n[1] Fetching data...")
prices = fetch_close(ALL_TICKERS, FULL_START, FULL_END)
vix = fetch_fred("VIXCLS", start=FULL_START)
vix = vix.reindex(pd.date_range(vix.index.min(), vix.index.max(), freq="D")).ffill()
regime = build_vix_regime(vix)

print(f"  Prices: {prices.shape}, {prices.index.min().date()}..{prices.index.max().date()}")
print(f"  VIX regime coverage: {regime.value_counts().to_dict()}")

results = {}
print("\n[2] Running variants...")
for top_n, tag in [(1, "Top1"), (2, "Top2")]:
    r_regime  = monthly_strategy(prices, regime, top_n, regime_conditional=True)
    r_static  = monthly_strategy(prices, regime, top_n, regime_conditional=False)
    results[f"regime_{tag}"] = report(f"REGIME-CONDITIONAL {tag} (10m/3m/1m by VIX regime)", r_regime)
    results[f"static_{tag}"] = report(f"STATIC {tag} (fixed 10m lookback, no regime switch)", r_static)

print("\n[3] Regime observation counts (IS / OOS)...")
r_is  = regime[is_mask(regime.index)]
r_oos = regime[oos_mask(regime.index)]
print(f"  IS  regime days:  {r_is.value_counts().to_dict()}")
print(f"  OOS regime days:  {r_oos.value_counts().to_dict()}")

print("\n[4] Gate check...")
for tag in ["Top1", "Top2"]:
    reg = results[f"regime_{tag}"]
    stc = results[f"static_{tag}"]
    d_sharpe = reg["oos"]["sharpe"] - stc["oos"]["sharpe"]
    d_dd = (stc["oos"]["max_drawdown"] - reg["oos"]["max_drawdown"]) * 100
    passes_sharpe = d_sharpe > 0.10 and reg["wf_worst"] >= WF_WORST_MIN
    passes_dd = d_dd > 2.0 and d_sharpe > -0.10
    verdict = "PASS" if (passes_sharpe or passes_dd) else "FAIL"
    print(f"  {tag}: regime-vs-static OOS Sharpe delta {d_sharpe:+.3f}, MaxDD delta {d_dd:+.2f}pp, WF {reg['wf_worst']:.3f} -> {verdict}")
    results[f"gate_{tag}"] = {"delta_sharpe": round(d_sharpe, 4), "delta_maxdd_pp": round(d_dd, 2), "verdict": verdict}

out_path = RESULT_DIR / "h524_results.json"
with open(out_path, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\nResults written to {out_path}")
