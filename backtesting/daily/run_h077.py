"""
H077 — H041a Universe Optimization: Top-N and Asset Expansion
=============================================================

Purpose:
  H041a rotation (20.6% of portfolio) uses SPY/QQQ/TLT/GLD/IEF/EFA/EEM top-2.
  This hypothesis explores:
    [1] Top-N sweep: top-1 vs top-2 vs top-3 for the existing 7-asset universe
    [2] Asset expansion: add IWM (US small-cap) or XLRE (real estate) — quick test
    [3] Full portfolio impact of the best H041a variant vs H076 production baseline

  H041a is the largest equity rotation component (20.6% of portfolio, IS 1.619/OOS 1.821).
  Small improvements in H041a signal propagate directly to portfolio performance.

H076 baseline: OOS 2.6951, AltOOS 2.7057, WF worst 2.379
H041a current: SPY/QQQ/TLT/GLD/IEF/EFA/EEM top-2

Periods: Same as H073/H076.

Outputs:
  /workspace/agent/backtesting/results/h077_results.json
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

FULL_START  = "2003-01-01"
FULL_END    = "2026-04-27"
IS_START    = "2008-01-01"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
ALT_IS_END  = "2012-12-31"
ALT_OOS_ST  = "2013-01-01"

WF_WORST_MIN = 1.75

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)
BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD", "BKLN", "EMB"]

H041A_BASE = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H026_TICKERS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]

# H076 production weights
H076_W = {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072", "h073", "h074", "h075", "h076"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h077_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in ["h064", "h063", "h062", "h065", "h066", "h067", "h068",
                "h069", "h070", "h071", "h072", "h073", "h074", "h075", "h076"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070",
                "h071", "h072", "h073", "h074", "h075", "h076", "h077"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h077_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
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
    if not rows:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df        = ohlc.copy()
    denom     = (df["high"] - df["low"]).replace(0, np.nan)
    ibs       = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl   = df["close"].shift(1)
    g         = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i - 1])
        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position  = 0
                days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": len(r)}
    eq    = (1 + r).cumprod()
    n_yr  = len(r) / 12.0
    cagr  = float(eq.iloc[-1]) ** (1 / n_yr) - 1
    vol   = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r)}


def run_wf(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    folds = []
    start = min_train
    fold  = 0
    while start + test_size <= n and fold < n_folds:
        ti = is_idx[start:start + test_size]
        pr = sum(ww * r_dict[k].reindex(ti, fill_value=0.0) for k, ww in w.items())
        folds.append(stats(pr)["sharpe"])
        start += test_size
        fold  += 1
    return folds


def score_portfolio(name, w, rd, cidx):
    ts = pd.Timestamp
    def p(mask):
        i = cidx[mask(cidx)]
        return sum(ww * rd[k].reindex(i, fill_value=0.0) for k, ww in w.items())
    s_is  = stats(p(lambda x: (x >= ts(IS_START)) & (x <= ts(IS_END))))
    s_oos = stats(p(lambda x: x >= ts(OOS_START)))
    s_ai  = stats(p(lambda x: (x >= ts(FULL_START)) & (x <= ts(ALT_IS_END))))
    s_ao  = stats(p(lambda x: x >= ts(ALT_OOS_ST)))
    wf    = run_wf(cidx, rd, w)
    ww    = min(wf) if wf else 0.0
    return {"name": name, "is": s_is["sharpe"], "oos": s_oos["sharpe"],
            "ai": s_ai["sharpe"], "ao": s_ao["sharpe"],
            "oos_cagr": s_oos["cagr"], "oos_dd": s_oos["max_drawdown"],
            "wf_worst": ww, "wf_ok": bool(ww >= WF_WORST_MIN), "wf_folds": wf}


# ── main ────────────────────────────────────────────────────────────────────

print("=" * 80)
print("H077 — H041a Universe Optimization: Top-N and Asset Expansion")
print("=" * 80)
print()

print("[0] Loading shared components …")
h045_r = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
h026_r = build_rotation_monthly(H026_TICKERS, FULL_START, FULL_END, 3)
xlk_r  = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
smh_r  = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
igv_r  = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))

# ── [1] H041a standalone: top-N sweep ───────────────────────────────────────
print()
print("[1] H041a standalone top-N sweep …")

h41_variants = {}
for n_hold in [1, 2, 3]:
    r = build_rotation_monthly(H041A_BASE, FULL_START, FULL_END, n_hold)
    h41_variants[f"top-{n_hold}"] = r
    idx = r.index
    is_s  = stats(r[(idx >= pd.Timestamp(IS_START)) & (idx <= pd.Timestamp(IS_END))])["sharpe"]
    oos_s = stats(r[idx >= pd.Timestamp(OOS_START)])["sharpe"]
    ai_s  = stats(r[(idx >= pd.Timestamp(FULL_START)) & (idx <= pd.Timestamp(ALT_IS_END))])["sharpe"]
    ao_s  = stats(r[idx >= pd.Timestamp(ALT_OOS_ST)])["sharpe"]
    print(f"  H041a top-{n_hold}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")

# ── [2] H041a asset expansion ────────────────────────────────────────────────
print()
print("[2] H041a asset expansion …")

expansions = {
    "base (7-asset)": H041A_BASE,
    "+IWM (8-asset)": H041A_BASE + ["IWM"],
    "+XLRE (8-asset)": H041A_BASE + ["XLRE"],
    "+IWM+XLRE (9-asset)": H041A_BASE + ["IWM", "XLRE"],
    "+BIL (8-asset)": H041A_BASE + ["BIL"],   # cash-like for risk-off months
}

exp_returns = {}
for label, tickers in expansions.items():
    r = build_rotation_monthly(tickers, FULL_START, FULL_END, 2)
    exp_returns[label] = r
    idx = r.index
    is_s  = stats(r[(idx >= pd.Timestamp(IS_START)) & (idx <= pd.Timestamp(IS_END))])["sharpe"]
    oos_s = stats(r[idx >= pd.Timestamp(OOS_START)])["sharpe"]
    ai_s  = stats(r[(idx >= pd.Timestamp(FULL_START)) & (idx <= pd.Timestamp(ALT_IS_END))])["sharpe"]
    ao_s  = stats(r[idx >= pd.Timestamp(ALT_OOS_ST)])["sharpe"]
    print(f"  {label:<22}: IS {is_s:.3f}, OOS {oos_s:.3f}, AltIS {ai_s:.3f}, AltOOS {ao_s:.3f}")

# ── [3] Portfolio integration — best H041a variants ──────────────────────────
print()
print("[3] Portfolio integration …")

# Determine best H041a standalone by OOS
all_h41 = {}
for k, r in h41_variants.items():
    idx = r.index
    oos_s = stats(r[idx >= pd.Timestamp(OOS_START)])["sharpe"]
    all_h41[k + " (base)"] = (r, oos_s)
for k, r in exp_returns.items():
    idx = r.index
    oos_s = stats(r[idx >= pd.Timestamp(OOS_START)])["sharpe"]
    all_h41[f"top-2 {k}"] = (r, oos_s)

# Build shared IBS components
r_ibs = {"h026": h026_r, "h045": h045_r, "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}

# Common IBS intersection (no H041a yet)
ibs_idx = h045_r.index
for s in [h026_r, xlk_r, smh_r, igv_r]:
    ibs_idx = ibs_idx.intersection(s.index)
ibs_idx = ibs_idx.sort_values()

configs = []
# H076 baseline
h41a_base2 = h41_variants["top-2"]
base_idx = ibs_idx.intersection(h41a_base2.index).sort_values()
base_rd = {"h041a": h41a_base2, **r_ibs}
configs.append(("H076 baseline", H076_W, base_rd, base_idx))

# Test top-N variants (7-asset, different top-N)
for n_hold in [1, 3]:
    h41 = h41_variants[f"top-{n_hold}"]
    cidx = ibs_idx.intersection(h41.index).sort_values()
    rd   = {"h041a": h41, **r_ibs}
    configs.append((f"H041a top-{n_hold}", H076_W, rd, cidx))

# Test best expansion assets (top-2 for expanded universes)
for label in ["+IWM (8-asset)", "+XLRE (8-asset)", "+BIL (8-asset)", "+IWM+XLRE (9-asset)"]:
    h41 = exp_returns[label]
    cidx = ibs_idx.intersection(h41.index).sort_values()
    rd   = {"h041a": h41, **r_ibs}
    configs.append((f"H041a {label}", H076_W, rd, cidx))

print(f"\n  {'Portfolio':<28}  {'IS S':>7}  {'OOS S':>7}  {'AltOOS S':>9}  "
      f"{'MaxDD':>7}  {'WF worst':>9}  WF OK")
print("  " + "-" * 90)

results = []
for name, w, rd, idx in configs:
    sc = score_portfolio(name, w, rd, idx)
    wf_s = f"{sc['wf_worst']:.3f} {'✓' if sc['wf_ok'] else '✗'}"
    print(f"  {name:<28}  {sc['is']:>7.4f}  {sc['oos']:>7.4f}  "
          f"{sc['ao']:>9.4f}  {sc['oos_dd']*100:>6.2f}%  {wf_s:>9}")
    results.append(sc)

b   = results[0]
wf_ok_variants = [r for r in results[1:] if r["wf_ok"]]
if wf_ok_variants:
    best = max(wf_ok_variants, key=lambda x: x["oos"])
    print(f"\n  Best WF-consistent variant: {best['name']}")
    print(f"    OOS {b['oos']:.4f} → {best['oos']:.4f} (Δ={best['oos']-b['oos']:+.4f})")
    print(f"    AltOOS {b['ao']:.4f} → {best['ao']:.4f} (Δ={best['ao']-b['ao']:+.4f})")

    if best["oos"] > b["oos"] and best["ao"] > b["ao"]:
        print(f"\n  *** BOTH OOS WINDOWS IMPROVE → {best['name']} recommended ***")
    elif best["oos"] > b["oos"]:
        print(f"\n  Primary OOS improves but AltOOS does not — partial confirmation only")
    else:
        print(f"\n  No meaningful improvement found")

# Save
def _sharpe_slice(s, start, end=None):
    idx = s.index
    if end:
        m = (idx >= pd.Timestamp(start)) & (idx <= pd.Timestamp(end))
    else:
        m = idx >= pd.Timestamp(start)
    return stats(s[m])["sharpe"]

output = {
    "h041a_standalone": {
        f"top-{n}": {
            "is":  _sharpe_slice(h41_variants[f"top-{n}"], IS_START, IS_END),
            "oos": _sharpe_slice(h41_variants[f"top-{n}"], OOS_START)
        }
        for n in [1, 2, 3]
    },
    "portfolio_results": [
        {"name": r["name"], "is": r["is"], "oos": r["oos"],
         "alt_oos": r["ao"], "wf_worst": r["wf_worst"], "wf_ok": r["wf_ok"],
         "oos_cagr": r["oos_cagr"], "oos_dd": r["oos_dd"]}
        for r in results
    ]
}
out_path = RESULT_DIR / "h077_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print()
print("=" * 80)
