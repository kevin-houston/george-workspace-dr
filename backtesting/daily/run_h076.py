"""
H076 — IGV IBS at 2% Allocation: Smaller Satellite Test
========================================================

Purpose:
  H075 showed IGV at 4% (from H041a) improves primary OOS (+0.053) but slightly
  hurts AltOOS (−0.007). The regression is concentrated in 2013-2017 calendar years
  (-0.7 to -1.2pp/yr) when software intraday volatility wasn't yet as extreme.

  Question: Does a smaller 2% IGV allocation retain the post-2018 benefit while
  avoiding the 2013-2017 drag? A smaller position = less damage in unfavourable
  periods while still capturing the post-2018 regime.

  Also test the best allocation source for 2% IGV:
    A) 2% from XLK (XLK: 20%→18%, IGV: 2%)
    B) 2% from SMH (SMH: 8%→6%, IGV: 2%)
    C) 2% from H041a (H041a: 22.6%→20.6%, IGV: 2%)

  Confirm/reject criteria:
    CONFIRM: Both OOS Sharpes improve vs H073 baseline, WF worst ≥ 1.75
    PARTIAL: Primary OOS improves, AltOOS flat or better, WF ✓
    REJECT: Either window regresses, or WF fails

H073 baseline: OOS 2.6657, AltOOS 2.7054, WF worst 2.394

Periods: Same as H073/H075

Outputs:
  /workspace/agent/backtesting/results/h076_results.json
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

H073_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}


def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072", "h073", "h074", "h075"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h076_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h069", "h070", "h071", "h072", "h073", "h074", "h075"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070",
                "h071", "h072", "h073", "h074", "h075", "h076"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h076_{ticker}_close_{start}_{end}.parquet"
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


def scorecard(name, w, rd, idx):
    ts = pd.Timestamp
    def p(mask):
        i = idx[mask(idx)]
        return sum(ww * rd[k].reindex(i, fill_value=0.0) for k, ww in w.items())
    s_is  = stats(p(lambda x: (x >= ts(IS_START))  & (x <= ts(IS_END))))
    s_oos = stats(p(lambda x:  x >= ts(OOS_START)))
    s_ai  = stats(p(lambda x: (x >= ts(FULL_START)) & (x <= ts(ALT_IS_END))))
    s_ao  = stats(p(lambda x:  x >= ts(ALT_OOS_ST)))
    wf    = run_wf(idx, rd, w)
    return {"name": name, "is": s_is["sharpe"], "oos": s_oos["sharpe"],
            "ai": s_ai["sharpe"], "ao": s_ao["sharpe"],
            "oos_cagr": s_oos["cagr"], "oos_dd": s_oos["max_drawdown"],
            "wf_worst": min(wf) if wf else 0.0, "wf_ok": bool(min(wf) >= WF_WORST_MIN if wf else False),
            "wf_folds": wf}


# ── main ────────────────────────────────────────────────────────────────────

print("=" * 80)
print("H076 — IGV IBS at 2% Allocation")
print("=" * 80)
print()

print("[0] Building components …")
h045_r  = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
h041a_r = build_rotation_monthly(
    ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
h026_r  = build_rotation_monthly(
    ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
    FULL_START, FULL_END, 3)
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))

# Common index — intersection (no IGV)
cidx = h045_r.index
for s in [h041a_r, h026_r, xlk_r, smh_r]:
    cidx = cidx.intersection(s.index)
cidx = cidx.sort_values()

# Extended index with IGV
cidx_igv = cidx.intersection(igv_r.index).sort_values()

r_base = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r, "XLK": xlk_r, "SMH": smh_r}
r_igv  = {**r_base, "IGV": igv_r}

print()
print("[1] Portfolio scorecard …")

# Weight configs
configs = [
    ("H073 baseline",   H073_W,                                              r_base, cidx),
    ("IGV2 (XLK18)",    {"h041a": 0.226, "h026": 0.064, "h045": 0.43,
                          "XLK": 0.18,   "SMH": 0.08,   "IGV": 0.02},       r_igv,  cidx_igv),
    ("IGV2 (SMH6)",     {"h041a": 0.226, "h026": 0.064, "h045": 0.43,
                          "XLK": 0.20,   "SMH": 0.06,   "IGV": 0.02},       r_igv,  cidx_igv),
    ("IGV2 (H041a-)",   {"h041a": 0.206, "h026": 0.064, "h045": 0.43,
                          "XLK": 0.20,   "SMH": 0.08,   "IGV": 0.02},       r_igv,  cidx_igv),
    ("IGV4 (H041a-)",   {"h041a": 0.186, "h026": 0.064, "h045": 0.43,
                          "XLK": 0.20,   "SMH": 0.08,   "IGV": 0.04},       r_igv,  cidx_igv),
]

print(f"\n  {'Portfolio':<22}  {'IS S':>7}  {'OOS S':>7}  {'AltOOS S':>9}  "
      f"{'MaxDD':>7}  {'WF worst':>9}  WF OK")
print("  " + "-" * 85)

results = []
for name, w, rd, idx in configs:
    sc = scorecard(name, w, rd, idx)
    wf_s = f"{sc['wf_worst']:.3f} {'✓' if sc['wf_ok'] else '✗'}"
    print(f"  {name:<22}  {sc['is']:>7.4f}  {sc['oos']:>7.4f}  "
          f"{sc['ao']:>9.4f}  {sc['oos_dd']*100:>6.2f}%  {wf_s:>9}")
    results.append(sc)

print()
print("[2] Calendar year returns (IGV2 vs baseline) …")

base_sc = results[0]
best_igv2 = max(results[1:4], key=lambda x: x["oos"])  # best 2% config
print(f"\n  Testing: {best_igv2['name']}")

w_best, rd_best, idx_best = [(w, rd, idx) for n, w, rd, idx in configs if n == best_igv2["name"]][0]

print(f"\n  {'Year':>5}  {'Baseline':>10}  {'IGV2':>10}  {'Delta':>7}")
print("  " + "-" * 40)

neg_base = neg_igv2 = 0
cal = []
for yr in range(2004, 2026):
    def yr_r(idx, rd, w):
        yi = idx[idx.year == yr]
        if len(yi) == 0: return None
        p = sum(ww * rd[k].reindex(yi, fill_value=0.0) for k, ww in w.items())
        return float((1 + p).prod() - 1)
    rb = yr_r(cidx, r_base, H073_W)
    ri = yr_r(idx_best, rd_best, w_best)
    if rb is None or ri is None: continue
    if rb < 0: neg_base += 1
    if ri < 0: neg_igv2 += 1
    print(f"  {yr:>5}  {rb*100:>9.2f}%  {ri*100:>9.2f}%  {(ri-rb)*100:>+6.2f}pp")
    cal.append({"year": yr, "baseline": round(rb, 4), "igv2": round(ri, 4)})

print(f"  Baseline: {'ZERO' if neg_base==0 else neg_base} negative years")
print(f"  IGV2:     {'ZERO' if neg_igv2==0 else neg_igv2} negative years")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("[3] Summary …")

b = results[0]
for r in results[1:]:
    d_oos = r["oos"] - b["oos"]
    d_ao  = r["ao"]  - b["ao"]
    both_up = d_oos > 0 and d_ao > 0
    status = "BOTH ↑" if both_up else ("OOS ↑ AltOOS ↓" if d_oos > 0 else "OOS ↓")
    print(f"  {r['name']:<22}: OOS {d_oos:+.4f}, AltOOS {d_ao:+.4f}, "
          f"WF {r['wf_worst']:.3f}  [{status}]")

best_both = [r for r in results[1:] if r["oos"] > b["oos"] and r["ao"] > b["ao"] and r["wf_ok"]]
if best_both:
    winner = max(best_both, key=lambda x: x["oos"])
    print(f"\n  *** DUAL-WINDOW CONFIRMED: {winner['name']} ***")
    print(f"  OOS {b['oos']:.4f} → {winner['oos']:.4f} (Δ={winner['oos']-b['oos']:+.4f})")
    print(f"  AltOOS {b['ao']:.4f} → {winner['ao']:.4f} (Δ={winner['ao']-b['ao']:+.4f})")
else:
    print(f"\n  No dual-window improvement found — H073 remains production baseline")

output = {
    "results": [{"name": r["name"], "is": r["is"], "oos": r["oos"],
                 "alt_oos": r["ao"], "wf_worst": r["wf_worst"], "wf_ok": r["wf_ok"],
                 "oos_cagr": r["oos_cagr"], "oos_dd": r["oos_dd"]}
                for r in results],
    "calendar": cal,
}
out_path = RESULT_DIR / "h076_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print()
print("=" * 80)
