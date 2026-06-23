"""
H318 — Meta-Agent ETF Rotation Selector (IC-Weighted Dynamic Blending)
=======================================================================
Source: Ang, Azimbayev & Kim arXiv:2604.02279 "The Self-Driving Portfolio"

Hypothesis:
  A meta-learner that dynamically adjusts H026/H041a/H045 portfolio weights
  monthly based on regime signals and rolling IC (information coefficient)
  should outperform the static 40/30/30 fixed blend.

  Three competing strategies run in parallel:
    - H026:  25-asset sector+alts top-1 momentum rotation
    - H041a: 7-asset multi-asset top-2 momentum rotation
    - H045:  7-asset bond top-2 momentum rotation

  Meta-learner variants:
    A) Static equal-weight blend (33/33/33) — baseline
    B) Static optimised blend (40/30/30 H026/H041a/H045) — prod ratio baseline
    C) IC-weighted: weights proportional to rolling 24m IC (floored at 0.01)
    D) Regime switch: bear=H045 heavy, bull=H026/H041a heavy (VIX+200MA signal)
    E) Logistic-regression: on 5 regime features → overweight predicted winner

IS:  2010-01-01 – 2017-12-31
OOS: 2018-01-01 – 2026-06-20
Gate: OOS Sharpe > static optimised blend AND MaxDD improvement ≥ 1pp

Note: Production portfolio Sharpe 4.158 includes IBS overlays (XLK/SMH/IGV)
which run daily. This test is restricted to the monthly rotation sleeve only.
"""

import json
import hashlib
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore")

INITIAL_EQUITY = 100_000.0
CACHE_DIR   = Path(__file__).parent.parent / "cache"
RESULT_DIR  = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2008-01-01"    # extra warmup for 12m momentum
FULL_END   = "2026-06-20"
IS_START   = "2010-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# ── Strategy universes ────────────────────────────────────────────────────────
H026_ASSETS = [
    "SPY", "QQQ", "IWM", "EFA", "EEM",
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLY", "XLU", "XLRE", "XLC",
    "GLD", "SLV", "USO", "UNG",
    "TLT", "IEF", "HYG", "LQD", "BIL", "VNQ",
]
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
H045_ASSETS  = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
H026_TOP_N   = 1
H041A_TOP_N  = 2
H045_TOP_N   = 2

ALL_TICKERS = sorted(set(H026_ASSETS + H041A_ASSETS + H045_ASSETS))


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def cache_path(tag: str, start: str, end: str) -> Path:
    h = hashlib.md5(f"{tag}{start}{end}".encode()).hexdigest()[:10]
    return CACHE_DIR / f"h318_{tag}_{h}.parquet"


def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = cache_path("prices", start, end)
    if cp.exists():
        print("  Loaded price cache")
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True,
                      progress=False, threads=True)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_vix(start: str, end: str) -> pd.Series:
    cp = cache_path("vix", start, end)
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    raw = yf.download("^VIX", start=start, end=end, auto_adjust=True, progress=False)
    s = raw["Close"].squeeze().rename("VIX")
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_t10y3m(start: str, end: str) -> pd.Series:
    """FRED T10Y3M (10Y minus 3M yield spread); negative = inverted curve."""
    cp = cache_path("t10y3m", start, end)
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    # Try cached parquet from other scripts first
    fred_cp = CACHE_DIR / "fred_t10y2y.parquet"
    if fred_cp.exists():
        s = pd.read_parquet(fred_cp).squeeze()
        pd.DataFrame(s).to_parquet(cp)
        return s
    # Fetch from FRED API if key available
    import os
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id=T10Y3M&observation_start={start}"
               f"&observation_end={end}&api_key={fred_key}&file_type=json")
        import urllib.request
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            obs = [(o["date"], float(o["value"])) for o in data["observations"]
                   if o["value"] != "."]
            s = pd.Series(dict(obs), name="T10Y3M")
            s.index = pd.to_datetime(s.index)
            pd.DataFrame(s).to_parquet(cp)
            return s
        except Exception as e:
            print(f"  FRED fetch failed: {e}, using SPY/TLT proxy")
    # Proxy: TLT relative strength vs SHY as duration demand signal
    return pd.Series(dtype=float, name="T10Y3M")


# ─────────────────────────────────────────────────────────────────────────────
# Strategy engine
# ─────────────────────────────────────────────────────────────────────────────

def compute_strategy_returns(prices: pd.DataFrame, universe: list,
                              top_n: int, exclude_bill: bool = False) -> pd.Series:
    """
    Compute monthly returns for a momentum+inv-vol rotation strategy.
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top_n equally.
    Returns: monthly return series (start from first valid signal month).
    """
    avail = [t for t in universe if t in prices.columns]
    px = prices[avail].copy().ffill()
    # Build monthly resampled close and returns
    mpx = px.resample("ME").last()
    mret = (mpx / mpx.shift(1) - 1)
    # 12-month momentum (log-ratio to avoid negative price issues)
    mom12 = mpx / mpx.shift(12) - 1
    # 6-month realised vol (monthly std * sqrt(12))
    vol6  = mret.rolling(6).std() * np.sqrt(12)

    port_rets = []
    port_idx  = []

    for i in range(13, len(mpx)):
        row_date   = mpx.index[i]
        signal_row = mom12.iloc[i].dropna()
        vol_row    = vol6.iloc[i].dropna()
        valid = signal_row.index.intersection(vol_row.index)
        if exclude_bill and "BIL" in valid:
            valid = valid.drop("BIL")
        if len(valid) < top_n:
            port_rets.append(np.nan)
        else:
            score = signal_row[valid].rank() + vol_row[valid].rank(ascending=False)
            picks = list(score.nlargest(top_n).index)
            w     = 1.0 / len(picks)
            port_ret = (mret.iloc[i][picks] * w).sum()
            port_rets.append(float(port_ret))
        port_idx.append(row_date)

    return pd.Series(port_rets, index=port_idx, name="strategy_ret").dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Regime features
# ─────────────────────────────────────────────────────────────────────────────

def build_regime_features(prices: pd.DataFrame, vix: pd.Series,
                           t10y3m: pd.Series, monthly_idx: pd.DatetimeIndex
                           ) -> pd.DataFrame:
    """Build monthly regime feature matrix (aligned to month-end dates)."""
    spy = prices["SPY"].dropna() if "SPY" in prices.columns else pd.Series(dtype=float)
    spy_ma200 = spy.rolling(200).mean()
    spy_m = spy.resample("ME").last()
    ma200_m = spy_ma200.resample("ME").last()

    vix_m     = vix.resample("ME").last() if len(vix) > 0 else pd.Series(dtype=float)
    vix_ma12  = vix_m.rolling(12).mean()
    t10y3m_m  = t10y3m.resample("ME").last() if len(t10y3m) > 0 else pd.Series(dtype=float)

    rows = {}
    for dt in monthly_idx:
        spy_above = float(spy_m.asof(dt) > ma200_m.asof(dt)) if len(spy_m) > 0 else np.nan
        vix_val   = vix_m.asof(dt) if len(vix_m) > 0 else np.nan
        vix_rel   = (vix_val / vix_ma12.asof(dt)) if (len(vix_ma12) > 0 and not pd.isna(vix_ma12.asof(dt))) else np.nan
        slope     = t10y3m_m.asof(dt) if len(t10y3m_m) > 0 else np.nan
        rows[dt] = {
            "spy_above_200ma": spy_above,
            "vix_level":       vix_val,
            "vix_rel_ma":      vix_rel,
            "yield_slope":     slope,
        }

    return pd.DataFrame.from_dict(rows, orient="index")


# ─────────────────────────────────────────────────────────────────────────────
# Stats helper
# ─────────────────────────────────────────────────────────────────────────────

def calc_stats(rets: pd.Series, label: str = "") -> dict:
    rets = rets.dropna()
    if len(rets) < 6:
        return {"error": "too few months"}
    eq = (1 + rets).cumprod()
    n_years = len(rets) / 12
    cagr    = (eq.iloc[-1]) ** (1 / n_years) - 1
    vol     = rets.std() * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0
    mdd     = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(1 for _, g in rets.groupby(rets.index.year)
                  if (1 + g).prod() - 1 < 0)
    wf = 0.0
    return {
        "label":      label,
        "cagr":       round(float(cagr),   4),
        "sharpe":     round(float(sharpe),  4),
        "max_dd":     round(float(mdd),     4),
        "ann_vol":    round(float(vol),     4),
        "neg_years":  neg_yrs,
        "n_months":   len(rets),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Meta-learner variants
# ─────────────────────────────────────────────────────────────────────────────

def blend_static(strats: dict, weights: dict, start: str, end: str) -> pd.Series:
    """Equal or fixed-weight blend of strategy return series."""
    idx = strats[list(strats.keys())[0]].index
    idx = idx[(idx >= start) & (idx <= end)]
    port = pd.Series(0.0, index=idx)
    for name, ret in strats.items():
        w = weights.get(name, 0)
        port += ret.reindex(idx).fillna(0) * w
    return port


def blend_ic_weighted(strats: dict, start: str, end: str,
                      ic_window: int = 24) -> pd.Series:
    """
    IC-weighted blend: weights are proportional to rolling IC (autocorrelation
    of each strategy's returns — strategies with persistent performance get
    higher weight). IC floored at 0.01 to avoid zero/negative weights.
    Window: rolling ic_window months.
    """
    names = list(strats.keys())
    df = pd.DataFrame({n: strats[n] for n in names}).dropna()
    df = df[(df.index >= start) & (df.index <= end)]
    port = pd.Series(np.nan, index=df.index)

    for i in range(ic_window, len(df)):
        window_rets = df.iloc[i - ic_window:i]
        # IC = 1-month autocorrelation (rolling Sharpe as IC proxy)
        ics = {}
        for n in names:
            r = window_rets[n]
            # Sharpe-based IC: strategies with better recent risk-adj perf get more weight
            sr = r.mean() / r.std() if r.std() > 0 else 0
            ics[n] = max(float(sr), 0.01)
        total_ic = sum(ics.values())
        w = {n: ics[n] / total_ic for n in names}
        port.iloc[i] = sum(df[n].iloc[i] * w[n] for n in names)

    return port.dropna()


def blend_regime_switch(strats: dict, features: pd.DataFrame,
                         start: str, end: str) -> pd.Series:
    """
    Regime-conditional blend:
      Bull (SPY>200MA, VIX<20): H026 50%, H041a 30%, H045 20%
      Bear (SPY<200MA OR VIX>25): H026 20%, H041a 10%, H045 70%
      Neutral: H026 33%, H041a 33%, H045 33%
    """
    idx = strats["H026"].index
    idx = idx[(idx >= start) & (idx <= end)]
    port = pd.Series(np.nan, index=idx)

    for dt in idx:
        feat = features.asof(dt) if dt in features.index or features.index.max() >= dt else pd.Series(dtype=float)
        spy_bull = feat.get("spy_above_200ma", np.nan) if len(feat) > 0 else np.nan
        vix_v    = feat.get("vix_level",       np.nan) if len(feat) > 0 else np.nan

        if pd.isna(spy_bull) or pd.isna(vix_v):
            w = {"H026": 0.333, "H041a": 0.333, "H045": 0.333}
        elif spy_bull == 1.0 and vix_v < 20:
            w = {"H026": 0.50,  "H041a": 0.30,  "H045": 0.20}
        elif spy_bull == 0.0 or vix_v > 25:
            w = {"H026": 0.20,  "H041a": 0.10,  "H045": 0.70}
        else:
            w = {"H026": 0.40,  "H041a": 0.30,  "H045": 0.30}

        port[dt] = sum(strats[n].get(dt, np.nan) * w[n] for n in strats
                       if not pd.isna(strats[n].get(dt, np.nan)))

    return port.dropna()


def blend_logistic(strats: dict, features: pd.DataFrame,
                    is_end: str, oos_start: str, end: str,
                    base_w: dict, lookahead_months: int = 36) -> pd.Series:
    """
    Logistic regression: for each month, use last lookahead_months of features
    to train a classifier predicting which strategy had highest return.
    Apply softmax-style weight adjustment based on predicted probabilities.
    IS window: rolling — grows from first 24 months through is_end,
    then extends as OOS proceeds.
    """
    names = list(strats.keys())
    df_ret = pd.DataFrame({n: strats[n] for n in names}).dropna()
    feat_aligned = features.reindex(df_ret.index, method="nearest",
                                    tolerance=pd.Timedelta("31D")).dropna(how="all")

    # Align both
    common = df_ret.index.intersection(feat_aligned.index)
    df_ret = df_ret.loc[common]
    feats  = feat_aligned.loc[common].copy()

    port = pd.Series(np.nan, index=df_ret.index)
    scaler = StandardScaler()
    clf    = LogisticRegression(max_iter=500, random_state=42, C=1.0)

    for i in range(lookahead_months, len(df_ret)):
        train_idx = df_ret.index[:i]
        train_X   = feats.loc[train_idx].ffill().fillna(0)
        train_y   = df_ret.loc[train_idx].idxmax(axis=1)  # winner each month

        if len(train_y.unique()) < 2 or len(train_X) < 12:
            w = base_w
        else:
            try:
                Xs = scaler.fit_transform(train_X)
                clf.fit(Xs, train_y)
                test_X  = feats.iloc[[i]].ffill().fillna(0)
                Xs_test = scaler.transform(test_X)
                probs   = dict(zip(clf.classes_, clf.predict_proba(Xs_test)[0]))
                # Blend base weight 70% + predicted probability 30%
                total_w = {}
                for n in names:
                    total_w[n] = 0.7 * base_w.get(n, 0.333) + 0.3 * probs.get(n, 0.0)
                s = sum(total_w.values())
                w = {n: total_w[n] / s for n in names}
            except Exception:
                w = base_w

        row = df_ret.iloc[i]
        port.iloc[i] = sum(row[n] * w[n] for n in names if n in row.index)

    return port.dropna()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\nH318 — Meta-Agent ETF Rotation Selector")
    print("=" * 60)

    # 1. Download price data
    print("\n[1] Fetching price data …")
    prices = fetch_prices(ALL_TICKERS, FULL_START, FULL_END)
    print(f"  Loaded {prices.shape[1]} tickers, {prices.shape[0]} daily rows")

    # 2. Download regime data
    print("\n[2] Fetching regime data …")
    vix    = fetch_vix(FULL_START, FULL_END)
    t10y3m = fetch_t10y3m(FULL_START, FULL_END)
    print(f"  VIX: {len(vix)} days | T10Y3M: {len(t10y3m)} points")

    # 3. Compute individual strategy monthly returns
    print("\n[3] Computing strategy monthly returns …")
    r_h026  = compute_strategy_returns(prices, H026_ASSETS, H026_TOP_N)
    r_h041a = compute_strategy_returns(prices, H041A_ASSETS, H041A_TOP_N)
    r_h045  = compute_strategy_returns(prices, H045_ASSETS, H045_TOP_N)
    print(f"  H026:  {len(r_h026)} months  {r_h026.index[0].date()} – {r_h026.index[-1].date()}")
    print(f"  H041a: {len(r_h041a)} months  {r_h041a.index[0].date()} – {r_h041a.index[-1].date()}")
    print(f"  H045:  {len(r_h045)} months  {r_h045.index[0].date()} – {r_h045.index[-1].date()}")

    strats = {"H026": r_h026, "H041a": r_h041a, "H045": r_h045}

    # 4. Build regime features
    print("\n[4] Building regime features …")
    common_idx = r_h026.index.intersection(r_h041a.index).intersection(r_h045.index)
    features   = build_regime_features(prices, vix, t10y3m, common_idx)
    print(f"  Features: {list(features.columns)}, {len(features)} months")

    # 5. Individual strategy OOS stats
    print("\n[5] Individual strategy stats (OOS) …")
    for name, ret in strats.items():
        s = calc_stats(ret[OOS_START:], label=name)
        print(f"  {name}: Sharpe={s['sharpe']:.3f}  CAGR={s['cagr']:.1%}  "
              f"MaxDD={s['max_dd']:.1%}  NegYrs={s['neg_years']}")

    # 6. Static blends
    base_w_opt = {"H026": 0.40, "H041a": 0.30, "H045": 0.30}
    base_w_eq  = {"H026": 0.333, "H041a": 0.333, "H045": 0.333}
    base_w_prod = {"H026": 0.386, "H041a": 0.314, "H045": 0.300}  # normalized prod weights

    blend_a = blend_static(strats, base_w_eq,  OOS_START, FULL_END)
    blend_b = blend_static(strats, base_w_opt, OOS_START, FULL_END)

    # IS reference for WF ratio
    blend_a_is = blend_static(strats, base_w_eq,  IS_START, IS_END)
    blend_b_is = blend_static(strats, base_w_opt, IS_START, IS_END)

    # 7. IC-weighted blend
    blend_c = blend_ic_weighted(strats, OOS_START, FULL_END, ic_window=24)
    blend_c_is = blend_ic_weighted(strats, IS_START, IS_END, ic_window=24)

    # 8. Regime-switch blend
    blend_d = blend_regime_switch(strats, features, OOS_START, FULL_END)
    blend_d_is = blend_regime_switch(strats, features, IS_START, IS_END)

    # 9. Logistic regression blend
    blend_e = blend_logistic(strats, features, IS_END, OOS_START, FULL_END,
                              base_w=base_w_eq, lookahead_months=36)
    blend_e_is = blend_logistic(strats, features, IS_END, OOS_START, IS_END,
                                 base_w=base_w_eq, lookahead_months=24)

    # 10. Compute stats
    print("\n[6] IS and OOS results …")
    variants = {
        "A_equal_33":     (blend_a_is, blend_a),
        "B_opt_40_30_30": (blend_b_is, blend_b),
        "C_ic_weighted":  (blend_c_is, blend_c),
        "D_regime_switch":(blend_d_is, blend_d),
        "E_logistic":     (blend_e_is, blend_e),
    }

    results = {}
    for name, (is_r, oos_r) in variants.items():
        s_is  = calc_stats(is_r,  label=f"{name}_IS")
        s_oos = calc_stats(oos_r, label=f"{name}_OOS")
        wf = s_oos["sharpe"] / s_is["sharpe"] if s_is.get("sharpe", 0) > 0 else 0
        results[name] = {"IS": s_is, "OOS": s_oos, "wf_ratio": round(wf, 3)}
        print(f"  {name:20s}  IS Sharpe={s_is.get('sharpe', 0):.3f}  "
              f"OOS Sharpe={s_oos.get('sharpe', 0):.3f}  "
              f"OOS MaxDD={s_oos.get('max_dd', 0):.1%}  "
              f"WF={wf:.2f}  NegYrs={s_oos.get('neg_years',0)}")

    # 11. Year-by-year OOS comparison
    print("\n[7] Year-by-year OOS (equal-weight vs best dynamic) …")
    print(f"  {'Year':6s} {'A (EW)':>10s} {'C (IC-wt)':>10s} {'D (regime)':>11s} {'E (logit)':>10s}")
    for year in range(2018, 2027):
        y = str(year)
        a_yr = blend_a[y] if y in blend_a.index.year.astype(str) else pd.Series()
        c_yr = blend_c[y] if y in blend_c.index.year.astype(str) else pd.Series()
        d_yr = blend_d[y] if y in blend_d.index.year.astype(str) else pd.Series()
        e_yr = blend_e[y] if y in blend_e.index.year.astype(str) else pd.Series()

        def yr_ret(s):
            s = s[s.index.year == int(year)]
            return (1 + s).prod() - 1 if len(s) > 0 else np.nan

        a_r, c_r, d_r, e_r = yr_ret(blend_a), yr_ret(blend_c), yr_ret(blend_d), yr_ret(blend_e)
        print(f"  {year:6d} {a_r:>10.1%} {c_r:>10.1%} {d_r:>11.1%} {e_r:>10.1%}")

    # 12. OOS correlations with SPY
    print("\n[8] OOS correlations with SPY monthly returns …")
    spy_m = prices["SPY"].resample("ME").last().pct_change().dropna()
    spy_oos = spy_m[OOS_START:]
    for name, (_, oos_r) in variants.items():
        aligned = oos_r.reindex(spy_oos.index).dropna()
        corr = aligned.corr(spy_oos.reindex(aligned.index))
        print(f"  {name:20s}  Corr(SPY)={corr:.3f}")

    # 13. Save results
    out = {
        "hypothesis":  "H318",
        "description": "Meta-Agent ETF Rotation Selector — IC-weighted dynamic blend",
        "is_period":   {"start": IS_START, "end": IS_END},
        "oos_period":  {"start": OOS_START, "end": FULL_END},
        "individual_strategies": {
            n: calc_stats(r[OOS_START:], n) for n, r in strats.items()
        },
        "variants": results,
    }
    out_path = RESULT_DIR / "h318_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n  Results saved to {out_path}")

    return out


if __name__ == "__main__":
    result = main()
