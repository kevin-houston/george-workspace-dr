"""
H327 — kNN Macro-Analog ETF Rotation Ranker
============================================
Source: arXiv:2606.22719 (2026-06-21) "Leakage-Aware Benchmarking of LLM
        Forecasting: Real-Time Nowcasts as Decision-Time Input for Macro
        Factor Ranking"

Hypothesis:
  kNN on lag-shifted macro feature vectors finds the k=10 historically most
  similar months and averages their H026/H041a/H045 returns to predict which
  strategy will outperform next month.  Non-parametric alternative to H318's
  logistic regression; more robust to regime shifts and no over-parameterisation.

  Feature vector (8 features, monthly, lagged 1 month):
    1. VIX level
    2. VIX 1-month change
    3. SPY 12-month return
    4. SPY distance from 200-day MA (%)
    5. T10Y3M yield curve slope (FRED)  — proxy via ^TNX - ^IRX if unavailable
    6. CPI 1-month change (FRED CPIAUCSL) — proxy via TIP/IEF ratio if unavailable
    7. Credit-spread proxy: HYG relative momentum vs IEI (12m)
    8. SPY 20-day realised volatility (monthly avg)

  kNN (cosine similarity, k=10):
    Library grows rolling: IS months + all prior OOS months.
    For each query month t, find 10 nearest neighbours.
    Average H026/H041a/H045 returns in those 10 months.
    Top-predicted strategy gets +15% overweight.

  Adjustment rule:
    base_w  = {H026: 0.40, H041a: 0.30, H045: 0.30}
    winner  = argmax(predicted returns)
    w_winner += 0.15; w_other1 -= 0.075; w_other2 -= 0.075
    floor each weight at 0.10

IS:  2010-01-01 – 2017-12-31 (seed kNN library)
OOS: 2018-01-01 – 2026-06-20 (rolling, library grows)
Gate: OOS Sharpe > 2.501 (H318 static B) AND MaxDD ≥ -4.3%
"""

import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2008-01-01"
FULL_END   = "2026-06-20"
IS_START   = "2010-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

H026_ASSETS  = [
    "SPY","QQQ","IWM","EFA","EEM",
    "XLK","XLF","XLE","XLV","XLI","XLP","XLY","XLU","XLRE","XLC",
    "GLD","SLV","USO","UNG","TLT","IEF","HYG","LQD","BIL","VNQ",
]
H041A_ASSETS = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM"]
H045_ASSETS  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD"]
H026_TOP_N   = 1
H041A_TOP_N  = 2
H045_TOP_N   = 2

BASE_W  = {"H026": 0.40, "H041a": 0.30, "H045": 0.30}
ADJUST  = 0.15   # overweight top-predicted
K_NEIGH = 10
W_FLOOR = 0.10

STATIC_B_SHARPE = 2.501
STATIC_B_MDD    = -0.043


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_prices(start: str, end: str) -> pd.DataFrame:
    all_tickers = sorted(set(H026_ASSETS + H041A_ASSETS + H045_ASSETS
                             + ["HYG", "IEI", "TIP"]))
    cp = CACHE_DIR / "h318_prices_main.parquet"
    if cp.exists():
        df = pd.read_parquet(cp)
        missing = [t for t in all_tickers if t not in df.columns]
        if not missing:
            print("  Loaded price cache (shared)")
            return df
    print(f"  Downloading {len(all_tickers)} tickers …")
    raw = yf.download(all_tickers, start=start, end=end,
                      auto_adjust=True, progress=False, threads=True)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_series_yf(ticker: str, start: str, end: str) -> pd.Series:
    cp = CACHE_DIR / f"h326_{ticker.replace('^','')}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    raw = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    s = raw["Close"].squeeze().rename(ticker)
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_fred(series_id: str, start: str, end: str) -> pd.Series:
    cp = CACHE_DIR / f"fred_{series_id.lower()}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        import urllib.request
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id={series_id}&observation_start={start}"
               f"&observation_end={end}&api_key={fred_key}&file_type=json")
        try:
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            obs = [(o["date"], float(o["value"])) for o in data["observations"]
                   if o["value"] not in (".", "")]
            s = pd.Series(dict(obs), name=series_id)
            s.index = pd.to_datetime(s.index)
            pd.DataFrame(s).to_parquet(cp)
            return s
        except Exception as e:
            print(f"  FRED {series_id} fetch failed: {e}")
    return pd.Series(dtype=float, name=series_id)


# ── Strategy engine ───────────────────────────────────────────────────────────

def compute_strategy_returns(prices: pd.DataFrame, universe: list,
                              top_n: int) -> pd.Series:
    avail = [t for t in universe if t in prices.columns]
    px    = prices[avail].copy().ffill()
    mpx   = px.resample("ME").last()
    mret  = mpx / mpx.shift(1) - 1
    mom12 = mpx / mpx.shift(12) - 1
    vol6  = mret.rolling(6).std() * np.sqrt(12)

    port_rets, port_idx = [], []
    for i in range(13, len(mpx)):
        signal_row = mom12.iloc[i].dropna()
        vol_row    = vol6.iloc[i].dropna()
        valid = signal_row.index.intersection(vol_row.index)
        if len(valid) < top_n:
            port_rets.append(np.nan)
        else:
            score = signal_row[valid].rank() + vol_row[valid].rank(ascending=False)
            picks = list(score.nlargest(top_n).index)
            port_rets.append((mret.iloc[i][picks] / len(picks)).sum())
        port_idx.append(mpx.index[i])

    return pd.Series(port_rets, index=port_idx, name="strategy_ret").dropna()


# ── Feature engineering ───────────────────────────────────────────────────────

def build_features(prices: pd.DataFrame, vix: pd.Series,
                   tnx: pd.Series, irx: pd.Series,
                   cpi: pd.Series) -> pd.DataFrame:
    """
    Monthly macro feature matrix.  All lagged 1 month (shift(1)) at call site.
    """
    spy = prices["SPY"].dropna()
    hyg = prices["HYG"].dropna() if "HYG" in prices.columns else pd.Series(dtype=float)
    iei = prices["IEI"].dropna() if "IEI" in prices.columns else pd.Series(dtype=float)

    # Monthly resamples
    spy_m  = spy.resample("ME").last()
    vix_m  = vix.resample("ME").last()
    tnx_m  = tnx.resample("ME").last()
    irx_m  = irx.resample("ME").last()
    hyg_m  = hyg.resample("ME").last()
    iei_m  = iei.resample("ME").last()
    cpi_m  = cpi.resample("ME").last()

    # F1: VIX level
    f1 = vix_m.rename("vix_level")

    # F2: VIX 1-month change
    f2 = vix_m.diff(1).rename("vix_chg1m")

    # F3: SPY 12-month return
    f3 = (spy_m / spy_m.shift(12) - 1).rename("spy_12m")

    # F4: SPY distance from 200-day MA (using monthly as approx)
    spy_ma200 = spy.rolling(200).mean()
    spy_ma_m  = spy_ma200.resample("ME").last()
    f4 = (spy_m / spy_ma_m - 1).rename("spy_vs_200ma")

    # F5: T10Y3M yield curve slope (TNX - IRX as proxy)
    f5 = (tnx_m - irx_m).rename("yield_slope")

    # F6: CPI 1-month change (FRED) — fallback to TIP/IEI ratio momentum
    if len(cpi) > 0:
        f6 = cpi_m.pct_change(1).rename("cpi_chg1m")
    else:
        tip_m = prices["TIP"].resample("ME").last() if "TIP" in prices.columns else pd.Series(dtype=float)
        f6 = (tip_m / iei_m - 1).rename("cpi_chg1m")

    # F7: Credit spread proxy: HYG 12m relative momentum vs IEI
    if len(hyg_m) > 0 and len(iei_m) > 0:
        f7 = ((hyg_m / hyg_m.shift(12)) / (iei_m / iei_m.shift(12)) - 1).rename("credit_spread")
    else:
        f7 = pd.Series(dtype=float, name="credit_spread")

    # F8: SPY 20-day realised vol (monthly average of 20d rolling std of daily returns)
    spy_ret = spy.pct_change()
    spy_rv  = spy_ret.rolling(20).std() * np.sqrt(252)
    f8 = spy_rv.resample("ME").mean().rename("spy_rv20")

    feat = pd.concat([f1, f2, f3, f4, f5, f6, f7, f8], axis=1)
    feat = feat.dropna(how="all")
    return feat


def cosine_sim(a: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Cosine similarity of vector a to each row of B."""
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(B, axis=1)
    if a_norm == 0:
        return np.zeros(len(B))
    denom = b_norm * a_norm
    denom[denom == 0] = 1e-10
    return (B @ a) / denom


def knn_predict(query: np.ndarray, library_feats: np.ndarray,
                library_rets: np.ndarray, k: int = K_NEIGH) -> np.ndarray:
    """
    Find k nearest neighbours to query in library by cosine similarity.
    Returns average of their strategy returns (shape: 3, for H026/H041a/H045).
    """
    sims = cosine_sim(query, library_feats)
    if len(sims) < k:
        k = max(1, len(sims))
    top_k = np.argpartition(sims, -k)[-k:]
    return library_rets[top_k].mean(axis=0)


def knn_weights(predicted: np.ndarray, strat_order: list) -> dict:
    """
    Adjust base weights based on kNN prediction.
    Top-predicted strategy: +ADJUST. Others: -ADJUST/2 each.
    Floor all at W_FLOOR.
    """
    w = dict(BASE_W)
    winner = strat_order[np.argmax(predicted)]
    others = [s for s in strat_order if s != winner]
    w[winner] += ADJUST
    for s in others:
        w[s] -= ADJUST / 2
    # Floor
    for s in strat_order:
        w[s] = max(w[s], W_FLOOR)
    # Re-normalise
    total = sum(w.values())
    for s in strat_order:
        w[s] /= total
    return w


# ── Stats helper ──────────────────────────────────────────────────────────────

def calc_stats(rets: pd.Series, label: str = "") -> dict:
    rets = rets.dropna()
    if len(rets) < 6:
        return {"error": "too few months"}
    eq = (1 + rets).cumprod()
    n  = len(rets) / 12
    cagr   = eq.iloc[-1] ** (1 / n) - 1
    vol    = rets.std() * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0
    mdd    = (eq / eq.expanding().max() - 1).min()
    neg_yr = sum(1 for _, g in rets.groupby(rets.index.year)
                 if (1 + g).prod() - 1 < 0)
    return {
        "label": label, "cagr": round(float(cagr), 4),
        "sharpe": round(float(sharpe), 4), "max_dd": round(float(mdd), 4),
        "ann_vol": round(float(vol), 4), "neg_years": neg_yr,
        "n_months": len(rets),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("H327 — kNN Macro-Analog ETF Rotation Ranker")
    print("=" * 62)

    # ── Download data ─────────────────────────────────────────────
    prices = fetch_prices(FULL_START, FULL_END)
    vix    = fetch_series_yf("^VIX", FULL_START, FULL_END)
    tnx    = fetch_series_yf("^TNX", FULL_START, FULL_END)
    irx    = fetch_series_yf("^IRX", FULL_START, FULL_END)   # 3-month T-bill
    cpi    = fetch_fred("CPIAUCSL", FULL_START, FULL_END)

    # ── Sub-strategy returns ──────────────────────────────────────
    print("\nComputing sub-strategy returns …")
    r026  = compute_strategy_returns(prices, H026_ASSETS,  H026_TOP_N)
    r041a = compute_strategy_returns(prices, H041A_ASSETS, H041A_TOP_N)
    r045  = compute_strategy_returns(prices, H045_ASSETS,  H045_TOP_N)
    strats_order = ["H026", "H041a", "H045"]
    strats = {"H026": r026, "H041a": r041a, "H045": r045}

    # ── Feature matrix ────────────────────────────────────────────
    print("Building feature matrix …")
    features = build_features(prices, vix, tnx, irx, cpi)

    # Standardise features (z-score per feature over IS period only)
    is_feat  = features.loc[IS_START:IS_END].dropna()
    feat_mu  = is_feat.mean()
    feat_std = is_feat.std().replace(0, 1)
    feat_z   = (features - feat_mu) / feat_std

    # Align strategy returns to feature index (use next-month returns)
    ret_df = pd.DataFrame({s: strats[s] for s in strats_order})
    # Feature at t-1 predicts returns at t: shift features forward 1m
    feat_z_shifted = feat_z.shift(1)   # lag features so f(t-1) aligns to ret(t)

    # Common index
    common = feat_z_shifted.dropna(how="all").index.intersection(ret_df.dropna().index)
    feat_aligned = feat_z_shifted.loc[common].dropna()
    ret_aligned  = ret_df.loc[feat_aligned.index].dropna()
    feat_aligned = feat_aligned.loc[ret_aligned.index]

    # ── kNN backtest (rolling walk-forward) ──────────────────────
    print("Running kNN rolling backtest …")

    is_end_dt  = pd.Timestamp(IS_END)
    oos_start_dt = pd.Timestamp(OOS_START)
    oos_months = [dt for dt in feat_aligned.index if dt >= oos_start_dt]
    is_months  = [dt for dt in feat_aligned.index if dt <  oos_start_dt]

    lib_dates = list(is_months)   # starts as IS library, grows with each OOS month

    oos_rets  = []
    oos_idx   = []
    winner_log = []

    for dt in oos_months:
        if dt not in feat_aligned.index or dt not in ret_aligned.index:
            continue

        lib_feats = feat_aligned.loc[lib_dates].values
        lib_rets  = ret_aligned.loc[lib_dates].values  # shape (n, 3)

        query = feat_aligned.loc[dt].values

        if np.any(np.isnan(query)) or len(lib_dates) < K_NEIGH:
            # Fallback to static B
            w = BASE_W
        else:
            pred = knn_predict(query, lib_feats, lib_rets)
            w    = knn_weights(pred, strats_order)
            winner_log.append(strats_order[np.argmax(pred)])

        # Weighted return at this month
        r = sum(w[s] * ret_aligned.loc[dt, s] for s in strats_order)
        oos_rets.append(r)
        oos_idx.append(dt)

        # Grow library
        lib_dates.append(dt)

    oos_knn    = pd.Series(oos_rets, index=oos_idx, name="H327_knn").dropna()
    oos_static = ret_aligned.loc[oos_knn.index].apply(
        lambda row: sum(BASE_W[s] * row[s] for s in strats_order), axis=1
    )
    oos_static.name = "static_B"

    # Winner distribution
    from collections import Counter
    winner_dist = Counter(winner_log)

    # ── Stats ─────────────────────────────────────────────────────
    oos_stat = calc_stats(oos_knn,    "OOS kNN")
    oos_bs   = calc_stats(oos_static, "OOS static B")

    is_rets  = ret_aligned.loc[:is_end_dt].apply(
        lambda row: sum(BASE_W[s] * row[s] for s in strats_order), axis=1)
    is_stat  = calc_stats(is_rets, "IS static B (reference)")

    wf = round(oos_stat["sharpe"] / is_stat["sharpe"], 3) if is_stat.get("sharpe", 0) > 0 else 0
    oos_stat["wf_ratio"] = wf

    # Year-by-year
    yoy = {str(yr): round(float((1 + g).prod() - 1), 4)
           for yr, g in oos_knn.groupby(oos_knn.index.year)}

    # ── Print ──────────────────────────────────────────────────────
    print(f"\n{'Metric':<20} {'OOS kNN':>12} {'OOS static B':>14}")
    print("-" * 48)
    for key in ("sharpe", "cagr", "max_dd", "ann_vol", "neg_years"):
        v_k = oos_stat.get(key, "—")
        v_s = oos_bs.get(key, "—")
        fmt = lambda v: f"{v:>14.4f}" if isinstance(v, float) else f"{v:>14}"
        print(f"{key:<20}{fmt(v_k)}{fmt(v_s)}")
    print(f"{'wf_ratio':<20}{wf:>12.3f}")
    print()
    print("OOS year-by-year (kNN):")
    for yr, r in yoy.items():
        print(f"  {yr}: {r*100:+.1f}%")
    print()
    print("Winner distribution (OOS):")
    for s in strats_order:
        cnt = winner_dist.get(s, 0)
        print(f"  {s}: {cnt} months ({cnt/len(oos_months)*100:.0f}%)")

    # ── Gate ──────────────────────────────────────────────────────
    oos_sharpe = oos_stat.get("sharpe", 0)
    oos_mdd    = oos_stat.get("max_dd", -999)
    gate_sharpe = oos_sharpe > STATIC_B_SHARPE
    gate_mdd    = oos_mdd   >= STATIC_B_MDD
    confirmed   = gate_sharpe and gate_mdd
    print(f"\nGate check:")
    print(f"  Sharpe > {STATIC_B_SHARPE} → {oos_sharpe:.4f}  {'✓ PASS' if gate_sharpe else '✗ FAIL'}")
    print(f"  MaxDD  ≥ {STATIC_B_MDD}  → {oos_mdd:.4f}  {'✓ PASS' if gate_mdd else '✗ FAIL'}")
    print(f"\n  → H327 {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── Save ──────────────────────────────────────────────────────
    results = {
        "hypothesis": "H327",
        "title": "kNN Macro-Analog ETF Rotation Ranker",
        "source": "arXiv:2606.22719",
        "oos": oos_stat, "oos_static_b": oos_bs, "is_ref": is_stat,
        "oos_yoy": yoy,
        "winner_distribution": {s: winner_dist.get(s, 0) for s in strats_order},
        "gate": {"sharpe_pass": gate_sharpe, "mdd_pass": gate_mdd,
                 "confirmed": confirmed},
    }
    out = RESULT_DIR / "h327_results.json"
    out.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved → {out}")


if __name__ == "__main__":
    main()
