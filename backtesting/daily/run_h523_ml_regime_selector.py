"""
H523 — Lightweight-ML Regime Selector for H041a/H026/H045/IBS Weighting (resolves H318)
==========================================================================================
Closes the long-queued "H318 meta-agent ETF rotation selector" direction
(Ang et al. arXiv:2604.02279 AlphaCrafter Miner/Screener/Trader blueprint,
staged as a "PROPOSED (not staged as script yet)" architectural note in the
hypothesis log but never implemented). Per this session's explicit brief,
implemented WITHOUT any LLM agent — H520/H521 both established that
gpt-4o-mini at temperature 0.0, fed structured numeric macro inputs,
collapses to near-constant/degenerate output. H523 instead uses a
lightweight, IS-frozen ML classifier (LightGBM-style gradient boosting via
scikit-learn's HistGradientBoostingClassifier, since xgboost is also
available but sklearn avoids an extra dependency) to pick the regime bucket,
mirroring the established H241-C / H320 / H502 / H508 "train once on IS,
freeze, evaluate on OOS" pattern.

Baseline / precedent: H249 (CONFIRMED) — a HAND-CODED discrete regime table
keyed by (SPY vs 200MA, VIX<20) plus a rate-hike modifier, OOS Sharpe
improvement of +0.282 over the static 22/27/21/30 blend, gate was
improvement > 0.20.

H523 asks: can a supervised classifier, trained to predict which of H249's
four regime buckets would have maximized realized next-month portfolio
Sharpe/return, beat H249's hand-coded rule table -- using the SAME
sub-strategies and SAME regime-weight buckets, so this is a clean ML-vs-rules
comparison, not a new strategy design.

CRITICAL LOOK-AHEAD FIX vs. run_h249.py: H249's regime-conditional loop
computes `prior_dt = dt - pd.offsets.MonthEnd(1)` but then never uses it —
`regime_df.loc[dt, ...]` and `rate_hike.loc[dt]` both look up the CURRENT
month `dt` directly, using that month's own regime label (computed from
that month's own month-end SPY/VIX close) to pick that same month's weights.
This is the exact as-of-date bug class this session was told to avoid
(same mechanism as the OB filter's H343/H344/.../H492/H493 bug family,
applied here to a regime signal instead of an order-block filter). H523
does NOT copy this: the regime label and all ML features used to pick
month t's weights are built from data available at month (t-1)'s close
only (regime_df / feature frame explicitly shifted by 1 before use).

IS: 2008-2017   OOS: 2018-2026 (matches H249's canonical split)
Gate: OOS Sharpe improvement over H249's static blend > 0.20 (H249's own
gate) AND the ML selector must beat H249's own regime-conditional (hand-
coded rule) OOS Sharpe, otherwise "ML adds value beyond hand-coded rules"
is not actually being tested.
"""

import warnings; warnings.filterwarnings("ignore")
import sys, json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.ensemble import HistGradientBoostingClassifier

WORKSPACE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(WORKSPACE / "backtesting" / "daily"))

from run_h249 import (
    fetch_close, fetch_ohlcv, fetch_fred,
    compute_momentum_strategy, compute_ibs_strategy, compute_monthly_regime,
    calc_stats,
    H041A_ASSETS, H026_SECTORS, H045_BONDS, IBS_TICKERS, IBS_WEIGHTS,
    STATIC_WEIGHTS, REGIME_WEIGHTS,
    FULL_START, FULL_END, IS_END, OOS_START,
)

RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(exist_ok=True)

GATE_IMPROVEMENT = 0.20
SEED = 42


def build_feature_frame(regime_df, rate_hike, vix_m, dgs10_m, spy_m, ma_m, common_idx):
    """
    Build ML feature frame for regime classification. Every column here is
    computed from data available AT month t's close (using .resample("ME")
    on daily series is fine — that is data known by that month-end), but
    when USED to pick month t's portfolio weights it will be shifted by one
    row (features.shift(1)) so month t's weights are chosen using only
    information through month t-1's close. This mirrors the momentum
    strategy's own established sig_date = dates[i-1] convention.
    """
    feat = pd.DataFrame(index=common_idx)
    feat["spy_vs_ma"] = (spy_m.reindex(common_idx) / ma_m.reindex(common_idx) - 1.0)
    feat["vix_level"] = vix_m.reindex(common_idx)
    feat["vix_chg_3m"] = vix_m.reindex(common_idx).diff(3)
    feat["dgs10_chg_3m"] = dgs10_m.reindex(common_idx).diff(3)
    feat["dgs10_level"] = dgs10_m.reindex(common_idx)
    feat["market_bull"] = (regime_df["market"].reindex(common_idx) == "bull").astype(float)
    feat["vol_calm"] = (regime_df["vol"].reindex(common_idx) == "calm").astype(float)
    feat["rate_hike"] = rate_hike.reindex(common_idx).astype(float)
    feat = feat.ffill().fillna(0.0)
    return feat


def label_best_bucket(ret_components: pd.DataFrame, common_idx, buckets: dict):
    """
    For each month t, the "label" is which regime bucket (from H249's own
    REGIME_WEIGHTS table, same 4 buckets) WOULD HAVE produced the highest
    realized return in month t, given the actual sub-strategy returns that
    month. This is the ML classifier's training target.

    IMPORTANT: this label is only ever used to train the classifier on the
    IS period. It is never used directly to trade (that would be trivial
    look-ahead) -- OOS evaluation always uses the classifier's *predicted*
    bucket for month t from features known at t-1, never the realized-label.
    """
    labels = []
    bucket_names = list(buckets.keys())
    for dt in common_idx:
        row = ret_components.loc[dt]
        best_name, best_ret = None, -np.inf
        for name in bucket_names:
            wts = buckets[name]
            r = sum(wts[k] * row[k] for k in wts if k in row)
            if r > best_ret:
                best_ret = r
                best_name = name
        # sklearn's classification target checks reject tuple labels
        # (interpreted as a legacy multi-label sequence-of-sequences); use a
        # joined string key instead, mapped back to a tuple at prediction time.
        labels.append("|".join(best_name))
    return pd.Series(labels, index=common_idx)


def main():
    print("=" * 80)
    print("H523 — Lightweight-ML Regime Selector for H041a/H026/H045/IBS")
    print("=" * 80)

    print("\n[1] Fetching sub-strategy universes (reusing run_h249 helpers)...")
    h041a_px = fetch_close(H041A_ASSETS, tag="h041a")
    h026_px = fetch_close(H026_SECTORS + ["BIL"], tag="h026")
    h045_px = fetch_close(H045_BONDS, tag="h045")
    ibs_ohlcv = fetch_ohlcv(IBS_TICKERS, tag="ibs")
    spy_daily = fetch_close(["SPY"], tag="spy_daily")["SPY"]

    vix = fetch_fred("VIXCLS")
    dgs10 = fetch_fred("DGS10")

    print("\n[2] Building sub-strategy monthly return series...")
    h041a_m = h041a_px.resample("ME").last()
    h026_m = h026_px.resample("ME").last()
    h045_m = h045_px.resample("ME").last()

    r_h041a = compute_momentum_strategy(h041a_m, top_n=1)
    r_h026 = compute_momentum_strategy(h026_m, top_n=1)
    r_h045 = compute_momentum_strategy(h045_m, top_n=2)

    ibs_daily = compute_ibs_strategy(ibs_ohlcv, ["XLK", "SMH", "IGV"], IBS_WEIGHTS)
    r_ibs_m = (1 + ibs_daily).resample("ME").apply(lambda x: x.prod() - 1) if len(ibs_daily) else pd.Series(dtype=float)

    print("\n[3] Building regime signal + ML feature frame...")
    vix_m_reg = vix.resample("ME").mean() if vix is not None else None
    regime_df = compute_monthly_regime(spy_daily, vix_m_reg)

    if dgs10 is not None:
        dgs10_m = dgs10.resample("ME").last()
        dgs10_3m_chg = dgs10_m.diff(3)
        rate_hike = (dgs10_3m_chg > 0.5)
    else:
        dgs10_m = pd.Series(dtype=float)
        rate_hike = pd.Series(False, index=regime_df.index)

    spy_m = spy_daily.resample("ME").last()
    ma_m = spy_daily.rolling(200).mean().resample("ME").last()
    vix_m = vix.resample("ME").mean() if vix is not None else pd.Series(dtype=float)

    start = pd.Timestamp("2008-01-01")
    end = pd.Timestamp("2026-05-31")

    def align(s):
        return s[(s.index >= start) & (s.index <= end)]

    r_h041a, r_h026, r_h045, r_ibs_m = align(r_h041a), align(r_h026), align(r_h045), align(r_ibs_m)
    regime_df = align(regime_df)
    rate_hike = align(rate_hike)

    common_idx = r_h041a.index.intersection(r_h026.index).intersection(
        r_h045.index).intersection(r_ibs_m.index)
    common_idx = common_idx[(common_idx >= start) & (common_idx <= end)].sort_values()
    print(f"    Common months: {len(common_idx)}")

    ret_components = pd.DataFrame({
        "H041a": r_h041a.reindex(common_idx),
        "H026": r_h026.reindex(common_idx),
        "H045": r_h045.reindex(common_idx),
        "IBS": r_ibs_m.reindex(common_idx),
    }).fillna(0.0)

    regime_df = regime_df.reindex(common_idx, method="ffill")
    rate_hike = rate_hike.reindex(common_idx, method="ffill").fillna(False)

    feat = build_feature_frame(regime_df, rate_hike, vix_m, dgs10_m, spy_m, ma_m, common_idx)

    # ── Label: which of H249's 4 regime buckets would have been best THAT month ──
    labels = label_best_bucket(ret_components, common_idx, REGIME_WEIGHTS)

    # ── CRITICAL: shift features by 1 month so month t's weight decision uses
    # only information known through month t-1's close. This is the fix for
    # the un-applied `prior_dt` in run_h249.py's own loop. ──────────────────
    feat_lagged = feat.shift(1)
    labels_for_training = labels  # target: month t's realized best bucket

    is_mask = common_idx <= pd.Timestamp(IS_END)
    oos_mask = common_idx >= pd.Timestamp(OOS_START)

    # Drop first row (NaN from shift) from training
    train_idx = common_idx[is_mask]
    train_idx = train_idx[feat_lagged.loc[train_idx].notna().all(axis=1)]

    X_train = feat_lagged.loc[train_idx]
    y_train = labels_for_training.loc[train_idx]

    print(f"\n[4] Training HistGradientBoostingClassifier on IS ({len(train_idx)} months)...")
    print(f"    Label distribution (IS): {y_train.value_counts().to_dict()}")

    clf = HistGradientBoostingClassifier(
        max_iter=150, max_depth=3, learning_rate=0.05,
        random_state=SEED, l2_regularization=1.0,
    )
    clf.fit(X_train.values, y_train.values)

    is_train_acc = float((clf.predict(X_train.values) == y_train.values).mean())
    print(f"    IS training accuracy: {is_train_acc:.3f} (4-class, random baseline=0.25)")

    # ── Predict bucket for every month (IS-frozen model, no retraining) ─────
    all_idx = common_idx[feat_lagged.notna().all(axis=1)]
    X_all = feat_lagged.loc[all_idx]
    pred_bucket = pd.Series(clf.predict(X_all.values), index=all_idx)

    oos_idx_check = all_idx[all_idx >= pd.Timestamp(OOS_START)]
    oos_acc = float((pred_bucket.loc[oos_idx_check] == labels.loc[oos_idx_check]).mean())
    print(f"    OOS prediction accuracy vs. realized-best-bucket label: {oos_acc:.3f}")
    print(f"    OOS predicted-bucket distribution: {pred_bucket.loc[oos_idx_check].value_counts().to_dict()}")

    # ── Build ML-selector portfolio return series ────────────────────────────
    ml_ret = []
    for dt in all_idx:
        bucket_key = tuple(pred_bucket.loc[dt].split("|"))
        wts = dict(REGIME_WEIGHTS[bucket_key])
        # Rate hike modifier (same as H249, using dt's OWN rate_hike flag is
        # fine here since rate_hike is itself derived from a 3-month lagged
        # diff of month-end data and is only used as a feature INPUT to the
        # classifier's t-1 decision, not applied again post-hoc -- to avoid
        # double-counting we do NOT re-apply an extra rate-hike shift here,
        # unlike H249, since the classifier already sees rate_hike as a
        # lagged feature and can learn to route toward IBS on its own.)
        total = sum(wts.values())
        wts = {k: v / total for k, v in wts.items()}
        row = ret_components.loc[dt]
        r = sum(wts[k] * row[k] for k in wts if k in row)
        ml_ret.append(r)
    r_ml = pd.Series(ml_ret, index=all_idx)

    # ── Static and H249-style hand-coded regime baselines for comparison ────
    static_w = pd.Series(STATIC_WEIGHTS)
    r_static = (ret_components * static_w).sum(axis=1)

    regime_ret = []
    for dt in common_idx:
        # CORRECTLY LAGGED version of H249's rule table: use month t-1's
        # regime label to pick month t's weights (fixes the un-applied
        # prior_dt bug identified in run_h249.py).
        prior_positions = common_idx[common_idx < dt]
        if len(prior_positions) == 0:
            wts = dict(STATIC_WEIGHTS)
        else:
            prior_dt = prior_positions[-1]
            mkt = regime_df.loc[prior_dt, "market"] if prior_dt in regime_df.index else "bull"
            vol = regime_df.loc[prior_dt, "vol"] if prior_dt in regime_df.index else "calm"
            hike = rate_hike.loc[prior_dt] if prior_dt in rate_hike.index else False
            wts = dict(REGIME_WEIGHTS.get((mkt, vol), STATIC_WEIGHTS))
            if hike:
                shift = 0.08
                wts["H045"] = max(0.0, wts["H045"] - shift)
                wts["IBS"] = min(1.0, wts["IBS"] + shift)
        total = sum(wts.values())
        wts = {k: v / total for k, v in wts.items()}
        row = ret_components.loc[dt]
        r = sum(wts[k] * row[k] for k in wts if k in row)
        regime_ret.append(r)
    r_regime_lagged = pd.Series(regime_ret, index=common_idx)

    # ── Stats ─────────────────────────────────────────────────────────────
    print("\n[5] Computing stats (IS 2008-2017 / OOS 2018-2026)...")

    def is_oos(series):
        s = series.dropna()
        is_s = s[s.index <= pd.Timestamp(IS_END)]
        oos_s = s[s.index >= pd.Timestamp(OOS_START)]
        return calc_stats(is_s, "IS"), calc_stats(oos_s, "OOS")

    static_is, static_oos = is_oos(r_static)
    regime_is, regime_oos = is_oos(r_regime_lagged)
    ml_is, ml_oos = is_oos(r_ml)

    print(f"\n  Static blend:            IS Sharpe={static_is.get('sharpe',0):.3f}  OOS Sharpe={static_oos.get('sharpe',0):.3f}  OOS MaxDD={static_oos.get('max_dd',0)*100:.1f}%")
    print(f"  Regime rules (lag-fixed): IS Sharpe={regime_is.get('sharpe',0):.3f}  OOS Sharpe={regime_oos.get('sharpe',0):.3f}  OOS MaxDD={regime_oos.get('max_dd',0)*100:.1f}%")
    print(f"  ML selector (IS-frozen):  IS Sharpe={ml_is.get('sharpe',0):.3f}  OOS Sharpe={ml_oos.get('sharpe',0):.3f}  OOS MaxDD={ml_oos.get('max_dd',0)*100:.1f}%")

    delta_vs_static = ml_oos.get("sharpe", 0) - static_oos.get("sharpe", 0)
    delta_vs_rules = ml_oos.get("sharpe", 0) - regime_oos.get("sharpe", 0)

    print(f"\n[6] Gate check: ML OOS Sharpe improvement vs static > {GATE_IMPROVEMENT}, "
          f"AND ML beats hand-coded rules")
    print(f"    Delta vs static: {delta_vs_static:+.4f}")
    print(f"    Delta vs regime rules: {delta_vs_rules:+.4f}")

    confirmed = (delta_vs_static > GATE_IMPROVEMENT) and (delta_vs_rules > 0)
    print(f"    Verdict: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    # ── Correlation of ML selector OOS returns vs static (production) blend ──
    common_oos = r_ml.index.intersection(r_static.index)
    common_oos = common_oos[common_oos >= pd.Timestamp(OOS_START)]
    corr_vs_prod = float(r_ml.loc[common_oos].corr(r_static.loc[common_oos])) if len(common_oos) > 3 else None
    print(f"\n[7] OOS correlation of ML selector vs static production blend: {corr_vs_prod}")

    out = {
        "hypothesis": "H523",
        "gate_improvement_threshold": GATE_IMPROVEMENT,
        "confirmed": bool(confirmed),
        "static": {"is": static_is, "oos": static_oos},
        "regime_rules_lag_fixed": {"is": regime_is, "oos": regime_oos},
        "ml_selector": {"is": ml_is, "oos": ml_oos},
        "delta_ml_vs_static_oos_sharpe": round(delta_vs_static, 4),
        "delta_ml_vs_rules_oos_sharpe": round(delta_vs_rules, 4),
        "is_train_accuracy": round(is_train_acc, 4),
        "oos_prediction_accuracy": round(oos_acc, 4),
        "corr_ml_vs_static_prod_oos": corr_vs_prod,
    }
    out_path = RESULT_DIR / "h523_results.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nResults saved -> {out_path}")
    print("=" * 80)


if __name__ == "__main__":
    main()
