"""
H075 — Full Cross-Validation of IGV IBS Addition
=================================================

Purpose:
  H074 confirmed IGV IBS (software sector) exhibits strong inverse degradation
  (OOS 1.442, Deg +130%) and improves the portfolio:
    IGV4 (H041a-): OOS 2.6657 → 2.7186 (+0.053), WF worst 2.358 ✓

  Full cross-validation to confirm this is not overfit to primary OOS window.

IGV optimal params (from H074):
  buy=0.30, sell=0.75, hold=5, gap=+0.25%
  IS 0.627, OOS 1.442, Deg +130%

Best portfolio config:
  H041a 18.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 4%
  H045 universe: SHY+IEI+IEF+TLT+TIP+HYG+LQD+BKLN+EMB (top-2)

Tests:
  [1] Full scorecard — primary IS/OOS + alternate IS/OOS (4 windows)
  [2] Calendar year returns 2004-2025 (zero negative years must hold)
  [3] WF 5-fold detail
  [4] IGV standalone — both IS windows (confirm not 2018+ bull artifact)

H073 production baseline (for comparison):
  H041a 22.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8%
  OOS 2.6657, AltOOS 2.7054, WF worst 2.394

Periods:
  Full:   2003-01 → 2026-04
  IS:     2008-01 → 2017-12
  OOS:    2018-01 → 2026-04
  AltIS:  2003-01 → 2012-12
  AltOOS: 2013-01 → 2026-04

Outputs:
  /workspace/agent/backtesting/results/h075_results.json
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

H41_H26_RATIO = 3.5
WF_WORST_MIN  = 1.75

# H073 production weights/params (baseline)
H073_W = {"h041a": 0.226, "h026": 0.064, "h045": 0.43, "XLK": 0.20, "SMH": 0.08}
XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)   # best from H074
BASE_BONDS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD", "BKLN", "EMB"]

# H074 winner: 4% from H041a
H075_W = {"h041a": 0.186, "h026": 0.064, "h045": 0.43,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.04}


# ── data helpers ────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in ["h062", "h063", "h064", "h065", "h066", "h067", "h068",
                   "h069", "h070", "h071", "h072", "h073", "h074"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    cp = CACHE_DIR / f"h075_{ticker}_ohlc_{start}_{end}.parquet"
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
                "h069", "h070", "h071", "h072", "h073", "h074"]:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
    for pfx in ["h064", "h065", "h066", "h067", "h068", "h069", "h070",
                "h071", "h072", "h073", "h074", "h075"]:
        cp = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h075_{ticker}_close_{start}_{end}.parquet"
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


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


# ── main ────────────────────────────────────────────────────────────────────

print("=" * 80)
print("H075 — Full Cross-Validation of IGV IBS Addition")
print("=" * 80)
print()

print("[0] Building components …")
print("    H045 (BKLN+EMB) …")
h045_r   = build_rotation_monthly(BASE_BONDS, FULL_START, FULL_END, 2)
print("    H041a …")
h041a_r  = build_rotation_monthly(
    ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"], FULL_START, FULL_END, 2)
print("    H026 …")
h026_r   = build_rotation_monthly(
    ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"],
    FULL_START, FULL_END, 3)
xlk_ohlc = fetch_ohlc("XLK", FULL_START, FULL_END)
smh_ohlc = fetch_ohlc("SMH", FULL_START, FULL_END)
igv_ohlc = fetch_ohlc("IGV", FULL_START, FULL_END)
xlk_r    = to_monthly(ibs_equity_curve(xlk_ohlc, *XLK_PARAMS))
smh_r    = to_monthly(ibs_equity_curve(smh_ohlc, *SMH_PARAMS))
igv_r    = to_monthly(ibs_equity_curve(igv_ohlc, *IGV_PARAMS))

# Common index — intersection (same as H073)
cidx = h045_r.index
for s in [h041a_r, h026_r, xlk_r, smh_r]:
    cidx = cidx.intersection(s.index)
cidx = cidx.sort_values()

# Extended index for IGV variant — intersection of all 6 components
cidx_igv = cidx.intersection(igv_r.index).sort_values()

# Masks
ts = lambda s: pd.Timestamp(s)
is_mask     = lambda idx: (idx >= ts(IS_START)) & (idx <= ts(IS_END))
oos_mask    = lambda idx: (idx >= ts(OOS_START))
alt_is_mask = lambda idx: (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
alt_oo_mask = lambda idx: (idx >= ts(ALT_OOS_ST))

# Return dicts
r_base = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
          "XLK": xlk_r, "SMH": smh_r}
r_igv  = {**r_base, "IGV": igv_r}

# ── [1] Full cross-validation scorecard ────────────────────────────────────
print()
print("[1] Full cross-validation scorecard …")

portfolios = {
    "Baseline (H073)": (H073_W, r_base, cidx),
    "H075 (IGV4)":     (H075_W, r_igv,  cidx_igv),
}

print(f"\n  {'Portfolio':22}  {'IS S':>7}  {'OOS S':>7}  {'AltIS S':>8}  "
      f"{'AltOOS S':>9}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'WF worst':>9}")
print("  " + "-" * 100)

scorecard = {}
for name, (w, rd, idx) in portfolios.items():
    port_is     = make_port(rd, w, idx[is_mask(idx)])
    port_oos    = make_port(rd, w, idx[oos_mask(idx)])
    port_alt_is = make_port(rd, w, idx[alt_is_mask(idx)])
    port_alt_oo = make_port(rd, w, idx[alt_oo_mask(idx)])
    s_is     = stats(port_is)
    s_oos    = stats(port_oos)
    s_ai     = stats(port_alt_is)
    s_ao     = stats(port_alt_oo)
    wf       = run_wf_5fold(idx, rd, w)
    wf_worst = min(wf) if wf else 0.0
    wf_ok    = wf_worst >= WF_WORST_MIN
    print(f"  {name:22}  {s_is['sharpe']:>7.4f}  {s_oos['sharpe']:>7.4f}  "
          f"{s_ai['sharpe']:>8.4f}  {s_ao['sharpe']:>9.4f}  "
          f"{s_oos['cagr']*100:>8.2f}%  {s_oos['max_drawdown']*100:>9.2f}%  "
          f"{wf_worst:>8.3f} {'✓' if wf_ok else '✗'}")
    scorecard[name] = {"is": s_is, "oos": s_oos, "alt_is": s_ai, "alt_oos": s_ao,
                       "wf_worst": wf_worst, "wf_ok": bool(wf_ok), "wf_folds": wf}

# ── [2] Calendar year returns ────────────────────────────────────────────────
print()
print("[2] Calendar year returns 2004-2025 …")
print(f"\n  {'Year':>5}  {'Baseline (H073)':>18}  {'H075 (IGV4)':>14}  {'Delta':>7}")
print("  " + "-" * 55)

neg_base = neg_igv = 0
cal_rows = []
for yr in range(2004, 2026):
    ym = lambda idx: idx[(idx.year == yr)]
    def yr_ret(idx, rd, w):
        yi = ym(idx)
        if len(yi) == 0:
            return None
        p = make_port(rd, w, yi)
        return float((1 + p).prod() - 1)
    rb = yr_ret(cidx, r_base, H073_W)
    ri = yr_ret(cidx_igv, r_igv, H075_W)
    if rb is None or ri is None:
        continue
    if rb < 0:
        neg_base += 1
    if ri < 0:
        neg_igv += 1
    delta = ri - rb
    print(f"  {yr:>5}  {rb*100:>17.2f}%  {ri*100:>13.2f}%  {delta*100:>+6.2f}pp")
    cal_rows.append({"year": yr, "baseline": round(rb, 4), "igv4": round(ri, 4)})

print(f"  Baseline (H073): {'ZERO' if neg_base == 0 else neg_base} negative years")
print(f"  H075 (IGV4):     {'ZERO' if neg_igv  == 0 else neg_igv}  negative years")

# ── [3] WF fold detail ───────────────────────────────────────────────────────
print()
print("[3] WF 5-fold detail …")

for name, (w, rd, idx) in portfolios.items():
    folds = run_wf_5fold(idx, rd, w)
    print(f"  {name}: {[round(f, 3) for f in folds]} → min {min(folds):.3f}")

# ── [4] IGV standalone validation ───────────────────────────────────────────
print()
print("[4] IGV IBS standalone — both IS windows …")

igv_idx  = igv_r.index
igv_is   = igv_r[is_mask(igv_idx)]
igv_oos  = igv_r[oos_mask(igv_idx)]
igv_ai   = igv_r[alt_is_mask(igv_idx)]
igv_ao   = igv_r[alt_oo_mask(igv_idx)]

print(f"  Primary IS   (2008-2017): Sharpe {stats(igv_is)['sharpe']:.3f}")
print(f"  Primary OOS  (2018-2026): Sharpe {stats(igv_oos)['sharpe']:.3f}")
print(f"  Alt IS       (2003-2012): Sharpe {stats(igv_ai)['sharpe']:.3f}")
print(f"  Alt OOS      (2013-2026): Sharpe {stats(igv_ao)['sharpe']:.3f}")

# Deg check
is_s  = stats(igv_is)["sharpe"]
oos_s = stats(igv_oos)["sharpe"]
ai_s  = stats(igv_ai)["sharpe"]
ao_s  = stats(igv_ao)["sharpe"]
print(f"\n  Primary deg: {(oos_s-is_s)/abs(is_s)*100:+.1f}%  "
      f"(OOS {oos_s:.3f} vs IS {is_s:.3f})")
print(f"  Alt deg:     {(ao_s-ai_s)/abs(ai_s)*100:+.1f}%  "
      f"(AltOOS {ao_s:.3f} vs AltIS {ai_s:.3f})")

# ── Summary ──────────────────────────────────────────────────────────────────
print()
print("[5] Summary …")

b_oos = scorecard["Baseline (H073)"]["oos"]["sharpe"]
i_oos = scorecard["H075 (IGV4)"]["oos"]["sharpe"]
b_ao  = scorecard["Baseline (H073)"]["alt_oos"]["sharpe"]
i_ao  = scorecard["H075 (IGV4)"]["alt_oos"]["sharpe"]

print(f"  OOS:    {b_oos:.4f} → {i_oos:.4f} (Δ={i_oos-b_oos:+.4f})")
print(f"  AltOOS: {b_ao:.4f} → {i_ao:.4f} (Δ={i_ao-b_ao:+.4f})")

if i_oos > b_oos and i_ao > b_ao and scorecard["H075 (IGV4)"]["wf_ok"]:
    print(f"\n  *** IGV4 CONFIRMED on BOTH OOS windows → new production portfolio ***")
    print(f"  *** H041a 18.6% / H026 6.4% / H045 43% / XLK 20% / SMH 8% / IGV 4% ***")
elif i_oos > b_oos and scorecard["H075 (IGV4)"]["wf_ok"]:
    print(f"\n  IGV4: primary OOS improves but AltOOS diverges — partially confirmed")
else:
    print(f"\n  IGV4 not confirmed — investigate further")

# ── Save ─────────────────────────────────────────────────────────────────────
output = {
    "igv_params": {"buy": IGV_PARAMS[0], "sell": IGV_PARAMS[1],
                   "hold": IGV_PARAMS[2], "gap": IGV_PARAMS[3]},
    "scorecard": {n: {"is": d["is"]["sharpe"], "oos": d["oos"]["sharpe"],
                      "alt_is": d["alt_is"]["sharpe"], "alt_oos": d["alt_oos"]["sharpe"],
                      "oos_cagr": d["oos"]["cagr"], "oos_dd": d["oos"]["max_drawdown"],
                      "wf_worst": d["wf_worst"], "wf_ok": d["wf_ok"],
                      "wf_folds": d["wf_folds"]}
                  for n, d in scorecard.items()},
    "calendar": cal_rows,
    "igv_standalone": {"is": is_s, "oos": oos_s, "alt_is": ai_s, "alt_oos": ao_s},
    "production_weights": H075_W,
}

out_path = RESULT_DIR / "h075_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print()
print("=" * 80)
