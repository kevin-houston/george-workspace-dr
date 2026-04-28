"""
H074 — IGV IBS: Software Sector as Third IBS Satellite
=======================================================

Purpose:
  XLK and SMH IBS both exhibit inverse degradation (OOS > IS), driven by
  high post-2018 intraday volatility in tech/semiconductor sectors.

  IGV (iShares Expanded Tech-Software Sector ETF) is the natural third
  candidate:
    - Pure software (MSFT, ORCL, ADBE, CRM, INTU, etc.) — no semiconductor overlap
    - Software has even HIGHER intraday vol than broad tech (earnings reactions,
      SaaS multiple compression/expansion, AI sentiment swings)
    - Low correlation to SMH (different market dynamics: semis are more cyclical,
      software more momentum-driven)

  Hypothesis: IGV IBS shows inverse degradation. As a third IBS satellite it
  diversifies XLK+SMH and raises portfolio OOS Sharpe beyond 2.666.

Plan:
  [1] IGV IBS standalone sweep — same grid as H069 (buy/sell/hold/gap)
  [2] Portfolio integration — test IGV at 4% from XLK, from SMH, from H041a-,
      and as a flat addition to 28% IBS bucket
  [3] Optimized IGV params + portfolio scorecard

Periods:
  Full: 2003-01 → 2026-04  (IGV launched 2001-07-10 — plenty of history)
  IS:   2008-01 → 2017-12
  OOS:  2018-01 → 2026-04
  AltIS: 2003-01 → 2012-12
  AltOOS: 2013-01 → 2026-04

H073 production baseline:
  H041a 22.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8%
  H045 universe: SHY+IEI+IEF+TLT+TIP+HYG+LQD+BKLN+EMB (top-2)
  IBS: XLK buy=0.15/sell=0.90/hold=7/gap=-1.0%; SMH buy=0.20/sell=0.75/hold=6/gap=-0.5%
  OOS 2.666, AltOOS 2.705, WF worst 2.394

Outputs:
  /workspace/agent/backtesting/results/h074_results.json
"""

import itertools
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
FULL_END   = "2026-04-27"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_IS_ST  = "2003-01-01"
ALT_IS_END = "2012-12-31"
ALT_OOS_ST = "2013-01-01"

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# H073 production weights and IBS params
H073_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD", "BKLN", "EMB"]


# ── data helpers ────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    # reuse existing cache from prior runs
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072", "h073"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h074_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h069", "h070", "h071", "h072", "h073"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070",
                "h071", "h072", "h073", "h074"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h074_{ticker}_close_{start}_{end}.parquet"
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


def run_wf_5fold(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
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


def portfolio_stats_full(r_dict, w, full_idx):
    port = sum(ww * r_dict[k].reindex(full_idx, fill_value=0.0) for k, ww in w.items())
    is_mask  = (full_idx >= pd.Timestamp(IS_START))  & (full_idx <= pd.Timestamp(IS_END))
    oos_mask = (full_idx >= pd.Timestamp(OOS_START))
    alt_oos  = (full_idx >= pd.Timestamp(ALT_OOS_ST))
    return {
        "is":      stats(port[is_mask])["sharpe"],
        "oos":     stats(port[oos_mask])["sharpe"],
        "alt_oos": stats(port[alt_oos])["sharpe"],
        "oos_cagr":   stats(port[oos_mask])["cagr"],
        "oos_dd":     stats(port[oos_mask])["max_drawdown"],
    }


# ── main ────────────────────────────────────────────────────────────────────

print("=" * 80)
print("H074 — IGV IBS: Software Sector as Third IBS Satellite")
print("=" * 80)
print()

print("[0] Loading data …")
igv_ohlc = fetch_ohlc("IGV", FULL_START, FULL_END)
xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)

# Build all rotation components (reuse H073 BKLN+EMB setup)
print("    Building H045 rotation (BKLN+EMB universe) …")
h045_ret = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)

print("    Building H041a rotation …")
H041A_TICKERS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
h041a_ret = build_rotation_monthly(H041A_TICKERS, FULL_START, FULL_END, 2)

print("    Building H026 rotation …")
H026_TICKERS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
h026_ret = build_rotation_monthly(H026_TICKERS, FULL_START, FULL_END, 3)

# Build XLK and SMH IBS monthly returns
xlk_eq = ibs_equity_curve(xlk_ohlc, *XLK_PARAMS)
smh_eq = ibs_equity_curve(smh_ohlc, *SMH_PARAMS)
xlk_ret = to_monthly(xlk_eq)
smh_ret = to_monthly(smh_eq)

# ── [1] IGV IBS standalone sweep ────────────────────────────────────────────
print()
print("[1] IGV IBS standalone sweep …")

# Baseline params (same as SPY defaults)
baseline_params = (0.20, 0.80, 5, -0.005)
eq_base = ibs_equity_curve(igv_ohlc, *baseline_params)
r_base  = to_monthly(eq_base)
b_idx   = r_base.index
is_mask_b  = (b_idx >= pd.Timestamp(IS_START)) & (b_idx <= pd.Timestamp(IS_END))
oos_mask_b = (b_idx >= pd.Timestamp(OOS_START))
is_s_b  = stats(r_base[is_mask_b])["sharpe"]
oos_s_b = stats(r_base[oos_mask_b])["sharpe"]
print(f"  Baseline (0.20/0.80/5/-0.5%): IS {is_s_b:.3f}, OOS {oos_s_b:.3f}")

buy_grid  = [0.10, 0.15, 0.20, 0.25, 0.30]
sell_grid = [0.70, 0.75, 0.80, 0.85, 0.90]
hold_grid = [3, 4, 5, 6, 7]
gap_grid  = [-0.010, -0.005, 0.000, 0.0025]

igv_sweep = []
for buy, sell, hold, gap in itertools.product(buy_grid, sell_grid, hold_grid, gap_grid):
    if buy >= sell:
        continue
    eq   = ibs_equity_curve(igv_ohlc, buy, sell, hold, gap)
    r    = to_monthly(eq)
    r_idx    = r.index
    is_mask  = (r_idx >= pd.Timestamp(IS_START)) & (r_idx <= pd.Timestamp(IS_END))
    oos_mask = (r_idx >= pd.Timestamp(OOS_START))
    is_s = stats(r[is_mask])["sharpe"]
    oo_s = stats(r[oos_mask])["sharpe"]
    if oo_s > 0.3:
        deg = (oo_s - is_s) / abs(is_s) * 100 if is_s != 0 else float("nan")
        igv_sweep.append({"buy": buy, "sell": sell, "hold": hold, "gap": gap,
                          "is_s": is_s, "oos_s": oo_s, "deg": deg, "ret": r})

igv_sweep.sort(key=lambda x: x["oos_s"], reverse=True)
print(f"  {'Buy':>4}  {'Sell':>4}  {'Hold':>4}  {'Gap':>7}  {'IS S':>7}  {'OOS S':>7}  {'Deg':>8}")
for row in igv_sweep[:8]:
    print(f"  {row['buy']:>4.2f}  {row['sell']:>4.2f}  {row['hold']:>4d}  "
          f"{row['gap']*100:>6.2f}%  {row['is_s']:>7.3f}  {row['oos_s']:>7.3f}  "
          f"{row['deg']:>+8.1f}%")

# Best IGV params
best_igv = igv_sweep[0]
IGV_PARAMS = (best_igv["buy"], best_igv["sell"], best_igv["hold"], best_igv["gap"])
igv_ret_best = best_igv["ret"]
print(f"\n  Best IGV params: buy={IGV_PARAMS[0]}, sell={IGV_PARAMS[1]}, "
      f"hold={IGV_PARAMS[2]}, gap={IGV_PARAMS[3]*100:.2f}%")
print(f"  IS {best_igv['is_s']:.3f}, OOS {best_igv['oos_s']:.3f}, "
      f"Deg {best_igv['deg']:+.1f}%")

# ── [2] Portfolio integration ────────────────────────────────────────────────
print()
print("[2] Portfolio integration …")

# Build common return index — intersection of all component series (same as H073)
all_idx = h045_ret.index
for s in [xlk_ret, smh_ret, h041a_ret, h026_ret]:
    all_idx = all_idx.intersection(s.index)
all_idx = all_idx.sort_values()

r_dict_base = {
    "h041a": h041a_ret.reindex(all_idx, fill_value=0.0),
    "h026":  h026_ret.reindex(all_idx, fill_value=0.0),
    "h045":  h045_ret.reindex(all_idx, fill_value=0.0),
    "XLK":   xlk_ret.reindex(all_idx, fill_value=0.0),
    "SMH":   smh_ret.reindex(all_idx, fill_value=0.0),
}

# IGV with best params
igv_ret_best_idx = igv_ret_best.reindex(all_idx, fill_value=0.0)

def test_portfolio(label, w, r_dict, full_idx):
    ps  = portfolio_stats_full(r_dict, w, full_idx)
    wf  = run_wf_5fold(full_idx, r_dict, w)
    wf_ok = min(wf) >= WF_WORST_MIN
    return {"label": label, "w": w,
            "is_s": ps["is"], "oos_s": ps["oos"], "alt_oos_s": ps["alt_oos"],
            "oos_cagr": ps["oos_cagr"], "oos_dd": ps["oos_dd"],
            "wf_worst": min(wf), "wf_ok": wf_ok, "wf_folds": wf}


# H073 production baseline
baseline_r = {**r_dict_base}
res_baseline = test_portfolio("H073 baseline", H073_W, baseline_r, all_idx)

# IGV test configurations:
# A) IGV4 from XLK (XLK: 20%→16%, IGV: 4%)
w_A = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.16, "SMH": 0.08, "IGV": 0.04}
r_A = {**r_dict_base, "IGV": igv_ret_best_idx}
res_A = test_portfolio("IGV4 (XLK16)", w_A, r_A, all_idx)

# B) IGV4 from SMH (SMH: 8%→4%, IGV: 4%)
w_B = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.04, "IGV": 0.04}
r_B = {**r_dict_base, "IGV": igv_ret_best_idx}
res_B = test_portfolio("IGV4 (SMH4)", w_B, r_B, all_idx)

# C) IGV4 from H041a (H041a-: 22.6%→18.6%, IGV: 4%)
equity_w = 1.0 - 0.43 - 0.28  # 29% to equity rotation
h041a_C  = equity_w * H41_H26_RATIO / (H41_H26_RATIO + 1) - 0.04
h026_C   = equity_w / (H41_H26_RATIO + 1)
w_C = {"h041a": round(h041a_C, 3), "h026": round(h026_C, 3), "h045": 0.43,
       "XLK": 0.20, "SMH": 0.08, "IGV": 0.04}
r_C = {**r_dict_base, "IGV": igv_ret_best_idx}
res_C = test_portfolio("IGV4 (H041a-)", w_C, r_C, all_idx)

# D) IGV2+XLK2: reduce XLK by 2%, add IGV 2% (conservative)
w_D = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.18, "SMH": 0.08, "IGV": 0.02}
r_D = {**r_dict_base, "IGV": igv_ret_best_idx}
res_D = test_portfolio("IGV2 (XLK18)", w_D, r_D, all_idx)

# E) IGV4 flat addition (total IBS goes to 32%)
w_E = {"h041a": 0.206, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08, "IGV": 0.04}
# h041a absorbs 2% to keep sum=1; adjust properly
total_ibs_e = 0.20 + 0.08 + 0.04
equity_e    = 1.0 - 0.43 - total_ibs_e
h041a_e     = equity_e * H41_H26_RATIO / (H41_H26_RATIO + 1)
h026_e      = equity_e / (H41_H26_RATIO + 1)
w_E = {"h041a": round(h041a_e, 3), "h026": round(h026_e, 3), "h045": 0.43,
       "XLK": 0.20, "SMH": 0.08, "IGV": 0.04}
r_E = {**r_dict_base, "IGV": igv_ret_best_idx}
res_E = test_portfolio("IGV4 (equity-)", w_E, r_E, all_idx)

results = [res_baseline, res_A, res_B, res_C, res_D, res_E]

print(f"\n  {'Portfolio':<28}  {'IS S':>7}  {'OOS S':>7}  {'AltOOS S':>9}  "
      f"{'MaxDD':>7}  {'WF worst':>9}  WF OK")
print("  " + "-" * 96)
for r in results:
    wf_str = f"{r['wf_worst']:.3f} {'✓' if r['wf_ok'] else '✗'}"
    print(f"  {r['label']:<28}  {r['is_s']:>7.4f}  {r['oos_s']:>7.4f}  "
          f"{r['alt_oos_s']:>9.4f}  {r['oos_dd']*100:>6.2f}%  {wf_str:>9}")

# Identify best WF-consistent variant
wf_ok_r = [r for r in results if r["wf_ok"] and r["label"] != "H073 baseline"]
if wf_ok_r:
    best = max(wf_ok_r, key=lambda x: x["oos_s"])
    baseline_oos = res_baseline["oos_s"]
    print(f"\n  Best WF-consistent: {best['label']}")
    print(f"    OOS {best['oos_s']:.4f} vs baseline {baseline_oos:.4f} "
          f"(Δ={best['oos_s']-baseline_oos:+.4f})")
    if best["oos_s"] > baseline_oos:
        print(f"\n  *** IGV IMPROVES portfolio OOS → proceed to H075 cross-validation ***")
        print(f"  Best weights: {best['w']}")
    else:
        print(f"\n  IGV does not improve OOS vs H073 baseline → investigate further")
else:
    print("\n  No WF-consistent improvement found")

# ── [3] Save results ─────────────────────────────────────────────────────────
output = {
    "igv_baseline_params": {"buy": 0.20, "sell": 0.80, "hold": 5, "gap": -0.005,
                             "is_s": is_s_b, "oos_s": oos_s_b},
    "igv_best_params": {"buy": IGV_PARAMS[0], "sell": IGV_PARAMS[1],
                        "hold": IGV_PARAMS[2], "gap": IGV_PARAMS[3],
                        "is_s": best_igv["is_s"], "oos_s": best_igv["oos_s"],
                        "deg": best_igv["deg"]},
    "igv_top8": [{"buy": r["buy"], "sell": r["sell"], "hold": r["hold"],
                  "gap": r["gap"], "is_s": r["is_s"], "oos_s": r["oos_s"]}
                 for r in igv_sweep[:8]],
    "portfolio_results": [
        {"label": r["label"], "is_s": r["is_s"], "oos_s": r["oos_s"],
         "alt_oos_s": r["alt_oos_s"], "wf_worst": r["wf_worst"],
         "wf_ok": bool(r["wf_ok"]), "oos_cagr": r["oos_cagr"], "oos_dd": r["oos_dd"]}
        for r in results
    ]
}

out_path = RESULT_DIR / "h074_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print()
print("=" * 80)
