"""
H503 — LightGBM Momentum-Crash Filter Applied to XLK/SMH/IGV IBS Legs (Production Blend)
===========================================================================================

Purpose:
  H502 (this session, NOT CONFIRMED) applied H320's LightGBM crash-filter mechanism to
  the H026/H041a ETF-rotation legs and found the classifier never fires: monthly
  returns < -5% occur in 0 of 201 OOS+IS months for H026 and only rarely for H041a
  (max P_crash 0.017 and 0.308, both under the 0.35 gate) — diversified rank-selected
  rotation legs are simply too smooth at the monthly frequency for a crash classifier
  to find enough positive training examples.

  The other 3 production sleeves (XLK/SMH/IGV, IBS mean-reversion strategies) are a
  structurally different case: they are short-hold (up to 5-7 days) daily strategies
  whose *monthly* aggregated returns exhibit real crash months. A direct check on
  cached IBS equity curves found XLK 10/279, SMH 21/279, and IGV 9/279 months with
  return < -5% over the full history — i.e., a nontrivial positive class exists for
  training, unlike H502. XLK is the largest of the three IBS legs (20% PROD_W, vs
  8% SMH and 2% IGV) and had 2 of its worst months in 2022 (broad tech selloff),
  which the underlying IBS pattern's short holding period doesn't inherently protect
  against if the whole month grinds lower. This tests whether the same crash-gating
  mechanism (H320-style, applied at monthly frequency to the *monthly-aggregated* IBS
  return series, since single-day IBS entries/exits are the wrong granularity for a
  macro-feature classifier) can improve the full production blend.

  As in H502, gated (cash) months are NOT redistributed to cash for the whole
  portfolio — the gated leg's own PROD_W weight month is simply zeroed for that leg,
  with all other 5 sleeves continuing to hold their normal static weight (same
  mechanism as H502, applied to a different leg family).

  Framework: IS 2008-2017, OOS 2018-2026, AltOOS 2013-2026, WF min=1.75.
  Reuses run_h502's production universe/build_rotation_monthly/IBS helpers unmodified.

Variants:
  A: production baseline (no filter)
  B: XLK IBS leg gated by LightGBM P_crash >= 0.35 -> cash for that month
  C: SMH IBS leg gated
  D: IGV IBS leg gated
  E: all three IBS legs gated independently (each has its own LightGBM model)

Gate: production-beat convention (matches H500/H502) — OOS Sharpe > 4.094 AND
      AltOOS Sharpe > 4.020 AND WF worst-fold >= 1.75
"""

import warnings
warnings.filterwarnings("ignore")
import json
import os
import numpy as np
import pandas as pd
import yfinance as yf
import lightgbm as lgb
import fredapi
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
ALT_IS_END = "2012-12-31"
ALT_OOS_ST = "2013-01-01"
WF_WORST_MIN = 1.75

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

CRASH_THRESH = -0.05
P_GATE       = 0.35
TRAIN_MONTHS = 60

_PREFIXES = [f"h{i:03d}" for i in range(62, 113)] + ["h500", "h502", "h503"]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h503_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


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
    cp = CACHE_DIR / f"h503_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def fetch_vix_daily():
    cp = CACHE_DIR / f"h502_VIX_daily_{FULL_START}_{FULL_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h503_VIX_daily_{FULL_START}_{FULL_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print("  Downloading VIX …")
    raw = yf.download("^VIX", start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("^VIX", axis=1, level=1)
    s = raw["Close"]
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_yield_curve():
    for pfx in ["h502", "h503"]:
        cp = CACHE_DIR / f"{pfx}_T10Y3M_monthly_{FULL_START}_{FULL_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h503_T10Y3M_monthly_{FULL_START}_{FULL_END}.parquet"
    print("  Downloading T10Y3M from FRED …")
    fred_key = os.environ.get("FRED_API_KEY", "")
    try:
        fred = fredapi.Fred(api_key=fred_key)
        s = fred.get_series("T10Y3M", observation_start=FULL_START, observation_end=FULL_END)
        s = s.resample("ME").last()
        s.name = "T10Y3M"
        pd.DataFrame(s).to_parquet(cp)
        return s
    except Exception as e:
        print(f"  WARN: FRED fetch failed ({e}), using constant 0.5 fallback")
        idx = pd.date_range(FULL_START, FULL_END, freq="ME")
        return pd.Series(0.5, index=idx, name="T10Y3M")


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
    for i in range(13, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


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


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r)}
    eq   = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol  = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r)}


def run_wf(idx, r_dict, w, min_train=56, test_size=16, n_folds=5):
    is_idx = pd.DatetimeIndex(sorted([d for d in idx if d >= pd.Timestamp(IS_START)]))
    n = len(is_idx)
    folds = []; start = min_train; fold = 0
    while start+test_size <= n and fold < n_folds:
        ti = is_idx[start:start+test_size]
        pr = sum(ww*r_dict[k].reindex(ti, fill_value=0.0) for k,ww in w.items())
        folds.append(stats(pr)["sharpe"])
        start += test_size; fold += 1
    return folds


def make_port(r_dict, w, idx):
    return sum(ww*r_dict[k].reindex(idx, fill_value=0.0) for k,ww in w.items())


def common_idx(*series):
    idx = series[0].index
    for s in series[1:]:
        idx = idx.intersection(s.index)
    return idx.sort_values()


ts = pd.Timestamp
def is_mask(idx):  return (idx >= ts(IS_START)) & (idx <= ts(IS_END))
def oos_mask(idx): return idx >= ts(OOS_START)
def ai_mask(idx):  return (idx >= ts(FULL_START)) & (idx <= ts(ALT_IS_END))
def ao_mask(idx):  return idx >= ts(ALT_OOS_ST)


def build_features(sleeve_rets, spy_daily, vix_daily, yc_monthly):
    vix_monthly_mean = vix_daily.resample("ME").mean()
    months = sleeve_rets.index
    rows = []
    for i, d in enumerate(months):
        if i < 6:
            continue
        spy_window = spy_daily.loc[:d].iloc[-200:]
        if len(spy_window) < 200:
            continue
        spy_ma200 = spy_window.mean()
        spy_cur = spy_window.iloc[-1]
        f1 = float(spy_cur / spy_ma200 - 1)

        f2 = float(vix_monthly_mean.get(d, np.nan))

        vix_recent = vix_daily.loc[:d].iloc[-20:]
        vix_prior  = vix_daily.loc[:d].iloc[-40:-20]
        f3 = float(vix_recent.mean()/vix_prior.mean()-1) if len(vix_recent) >= 10 and len(vix_prior) >= 10 else 0.0

        recent_rets = sleeve_rets.loc[:d].iloc[-6:]
        f4 = float(recent_rets.std()*np.sqrt(12)) if len(recent_rets) >= 3 else np.nan

        f5 = float((1+sleeve_rets.iloc[i-6:i]).prod()-1) if i >= 6 else np.nan

        yc_at_d = yc_monthly.get(d, np.nan)
        f6 = float(yc_at_d) if not pd.isna(yc_at_d) else 0.0

        rows.append({"date": d, "spy_ma200": f1, "vix_level": f2, "vix_chg20": f3,
                     "sleeve_vol": f4, "sleeve_ret6": f5, "yc_slope": f6})
    feats = pd.DataFrame(rows).set_index("date")
    return feats.dropna()


def rolling_lgbm_predict(features, sleeve_rets, train_months=TRAIN_MONTHS):
    feat_cols = ["spy_ma200","vix_level","vix_chg20","sleeve_vol","sleeve_ret6","yc_slope"]
    months = features.index
    preds = {}
    for i, t in enumerate(months):
        if i < train_months:
            continue
        train_idx = months[max(0, i-train_months):i]
        X_train = features.loc[train_idx, feat_cols].values
        y_train = (sleeve_rets.loc[train_idx] < CRASH_THRESH).astype(int).values
        if len(X_train) < 24 or y_train.sum() == 0:
            preds[t] = 0.0
            continue
        X_pred = features.loc[[t], feat_cols].values
        params = {"objective":"binary","metric":"binary_logloss","num_leaves":15,
                  "learning_rate":0.05,"n_estimators":100,"min_child_samples":3,
                  "subsample":0.8,"colsample_bytree":0.8,"verbose":-1,"random_state":42}
        clf = lgb.LGBMClassifier(**params)
        clf.fit(X_train, y_train)
        preds[t] = float(clf.predict_proba(X_pred)[0][1])
    return pd.Series(preds)


def gate_leg(sleeve_rets, crash_probs, gate=P_GATE):
    gated_rets = sleeve_rets.copy()
    gate_months = []
    for d in sleeve_rets.index:
        p = crash_probs.get(d, 0.0)
        if p >= gate:
            gated_rets.loc[d] = 0.0
            gate_months.append(d)
    return gated_rets, gate_months


print("="*80)
print("H503 — LightGBM Crash Filter on XLK/SMH/IGV IBS Legs (Production Blend)")
print("="*80)

print("\n[0] Building H026/H041a/H045 rotation legs (unaffected by this test) …")
h026 = build_rotation_monthly(H026_BASE,  FULL_START, FULL_END, 1)
h041 = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)
h045 = build_rotation_monthly(H045_PROD,  FULL_START, FULL_END, 2)

print("\n[1] Building XLK/SMH/IGV IBS equity curves (monthly returns) …")
xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK",FULL_START,FULL_END),*XLK_PARAMS))
smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH",FULL_START,FULL_END),*SMH_PARAMS))
igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV",FULL_START,FULL_END),*IGV_PARAMS))
print(f"    XLK crash months (<-5%): {int((xlk_r < CRASH_THRESH).sum())}/{len(xlk_r)}")
print(f"    SMH crash months (<-5%): {int((smh_r < CRASH_THRESH).sum())}/{len(smh_r)}")
print(f"    IGV crash months (<-5%): {int((igv_r < CRASH_THRESH).sum())}/{len(igv_r)}")

print("\n[2] Loading VIX, SPY daily, yield curve for feature construction …")
spy_daily  = fetch_daily_close("SPY", FULL_START, FULL_END)
vix_daily  = fetch_vix_daily()
yc_monthly = fetch_yield_curve()

print("\n[3] Building crash-risk features + rolling LightGBM predictions …")
leg_data = {"XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
probs = {}
gate_months = {}
gated_rets = {}
for name, rets in leg_data.items():
    feat = build_features(rets, spy_daily, vix_daily, yc_monthly)
    p = rolling_lgbm_predict(feat, rets)
    probs[name] = p
    g_rets, g_months = gate_leg(rets, p)
    gated_rets[name] = g_rets
    gate_months[name] = g_months
    print(f"    {name}: {len(p)} predictions, mean P_crash={p.mean():.3f}, "
          f"max={p.max():.3f}, months>=gate={len(g_months)}")

VARIANTS = {
    "A_baseline (production)":  {"XLK": xlk_r,             "SMH": smh_r,             "IGV": igv_r},
    "B_XLK_LGBM_gated":          {"XLK": gated_rets["XLK"], "SMH": smh_r,             "IGV": igv_r},
    "C_SMH_LGBM_gated":          {"XLK": xlk_r,             "SMH": gated_rets["SMH"], "IGV": igv_r},
    "D_IGV_LGBM_gated":          {"XLK": xlk_r,             "SMH": smh_r,             "IGV": gated_rets["IGV"]},
    "E_all3_LGBM_gated":         {"XLK": gated_rets["XLK"], "SMH": gated_rets["SMH"], "IGV": gated_rets["IGV"]},
}

print("\n[4] Blending into full production portfolio (PROD_W) …")
results = {}
base_oos = base_ao = base_wf = None
print(f"\n  {'Variant':>28}  {'OOS':>8}  {'AltOOS':>10}  {'MaxDD':>7}  {'WF':>7}  {'Beats base':>10}")
print("  "+"-"*85)
for label, legs in VARIANTS.items():
    rd = {"h041a": h041, "h026": h026, "h045": h045,
          "XLK": legs["XLK"], "SMH": legs["SMH"], "IGV": legs["IGV"]}
    cidx = common_idx(*rd.values())
    s_oos = stats(make_port(rd, PROD_W, cidx[oos_mask(cidx)]))
    s_ao  = stats(make_port(rd, PROD_W, cidx[ao_mask(cidx)]))
    wf    = run_wf(cidx, rd, PROD_W)
    ww    = min(wf) if wf else 0.0
    if label.startswith("A_"):
        base_oos, base_ao, base_wf = s_oos["sharpe"], s_ao["sharpe"], ww
        beats = "—"
    else:
        beats_flag = (s_oos["sharpe"] > base_oos and s_ao["sharpe"] > base_ao and ww >= WF_WORST_MIN)
        beats = "✓" if beats_flag else "✗"
    print(f"  {label:>28}  {s_oos['sharpe']:>8.4f}  {s_ao['sharpe']:>10.4f}  "
          f"{s_oos['max_drawdown']*100:>6.2f}%  {ww:>7.3f}  {beats:>10}")
    results[label] = {"oos_sharpe": s_oos["sharpe"], "altoos_sharpe": s_ao["sharpe"],
                       "oos_maxdd": s_oos["max_drawdown"], "wf_min": ww}

winners = [k for k,v in results.items() if not k.startswith("A_") and
           v["oos_sharpe"] > base_oos and v["altoos_sharpe"] > base_ao and v["wf_min"] >= WF_WORST_MIN]
confirmed = len(winners) > 0

print(f"\n[5] Summary …")
print(f"  Baseline (production): OOS {base_oos:.4f}, AltOOS {base_ao:.4f}, WF {base_wf:.3f}")
if confirmed:
    print(f"  *** H503 CONFIRMED — LGBM-gated variant(s) beat production: {winners} ***")
else:
    print(f"  H503 NOT CONFIRMED — no LGBM-gated variant beats production baseline.")

output = {"variants": results, "base_oos": base_oos, "base_ao": base_ao,
          "base_wf": base_wf, "confirmed": bool(confirmed), "winners": winners,
          "gate_months": {k: [str(d.date()) for d in v] for k, v in gate_months.items()},
          "probs_stats": {k: {"mean": float(v.mean()), "max": float(v.max())} for k, v in probs.items()}}
out_path = RESULT_DIR / "h503_results.json"
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\n  Results saved → {out_path}")
print("="*80)
