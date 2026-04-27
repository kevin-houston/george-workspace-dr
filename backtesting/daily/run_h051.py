"""
H051 — IS/OOS Validation of H050 (H045 + H037b Two-Component Portfolio)
========================================================================

Purpose: Validate whether H050's 2-component portfolio (H045 Treasury rotation +
H037b IBS mean-reversion) generalises out-of-sample better than H047 (4-component)
which showed 23.8% OOS degradation in H049.

Hypothesis: Simpler structure → less overfit → H050 OOS degradation < H047's 23.8%.
Confirm criteria:
  - OOS degradation < 20% on full-period weights (82/18)
  - OOS Sharpe ≥ 1.50 (competitive with H042)
Reject criteria:
  - OOS degradation ≥ 25% (worse than H047)
  - OOS Sharpe < 1.30

IS  : 2008-01 → 2017-12  (120 months, same split as H049)
OOS : 2018-01 → 2026-04  ( 99 months)

Three tests:
  1. IS/OOS split — optimize weights on IS, apply to OOS
  2. Full-period weights (82/18) applied to OOS
  3. 5-fold walk-forward

Outputs:
  /workspace/agent/backtesting/results/h051_results.json
"""

import json
import hashlib
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START   = "2000-01-01"
FULL_END     = "2026-04-27"
WINDOW_START = "2008-01-01"

IS_START  = "2008-01-01"
IS_END    = "2017-12-31"
OOS_START = "2018-01-01"
OOS_END   = "2026-04-27"

# H050 full-period optimal weights (from H050 fine-grained sweep)
FULL_W_H045  = 0.82
FULL_W_H037B = 0.18

# H045 params
TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
TOP_N_H45 = 2

# H037b params
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h051_{h}.parquet"
    # reuse H050 cache
    h50_key = "_".join(sorted(tickers)) + f"_h050_treasury_{start}_{end}"
    h50_h   = hashlib.md5(h50_key.encode()).hexdigest()[:12]
    h50_cp  = CACHE_DIR / f"h050_{h50_h}.parquet"
    if h50_cp.exists():
        return pd.read_parquet(h50_cp)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start, end):
    for tag in ["h042", "h047", "h050", "h031", "h031b"]:
        for variant in [
            f"h031_spy_ohlc_{start}_{end}.parquet",
            f"h050_spy_ohlc_{start}_{end}.parquet",
            f"h042_spy_ohlc_{start}_{end}.parquet",
        ]:
            cp = CACHE_DIR / variant
            if cp.exists():
                df = pd.read_parquet(cp)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    print(f"  Loaded SPY OHLC from cache ({len(df)} rows)")
                    return df
    cp = CACHE_DIR / f"h051_spy_ohlc_{start}_{end}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print("  Downloading SPY OHLC …")
    raw = yf.download(["SPY"], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs("SPY", axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Equity curve builders
# ─────────────────────────────────────────────────────────────────────────────

def h045_equity_curve(prices):
    available = [t for t in TREASURY_ETFS if t in prices.columns]
    if len(available) < TOP_N_H45:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H45
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H45:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H45).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not np.isnan(p0) and not np.isnan(p1):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def h037b_equity_curve(ohlc):
    df = ohlc.copy()
    denom   = (df["high"] - df["low"]).replace(0, np.nan)
    ibs     = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    gap     = (df["open"] - prev_cl) / prev_cl
    equity    = INITIAL_EQUITY
    position  = 0
    days_held = 0
    series    = []
    for i in range(1, len(df)):
        date     = df.index[i]
        prev_ibs = float(ibs.iloc[i - 1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(gap.iloc[i]) if not np.isnan(gap.iloc[i]) else 0.0
        o        = float(df["open"].iloc[i])
        c        = float(df["close"].iloc[i])
        c_prev   = float(df["close"].iloc[i - 1])
        ret_oc = (c / o - 1)      if o > 0      else 0.0
        ret_cc = (c / c_prev - 1) if c_prev > 0 else 0.0
        if position == 0:
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER_B:
                position  = 1
                days_held = 1
                equity   *= (1 + ret_oc)
        else:
            days_held += 1
            equity    *= (1 + ret_cc)
            if cur_ibs > IBS_SELL or days_held >= MAX_HOLD:
                position  = 0
                days_held = 0
        series.append((date, equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


# ─────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ─────────────────────────────────────────────────────────────────────────────

def stats_from_monthly_returns(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "n_months": len(monthly_rets), "label": label}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "calmar":       round(float(calmar),  4),
        "ann_vol":      round(float(vol),     4),
        "n_months":     len(monthly_rets),
    }


def to_monthly_returns(eq_daily):
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


def blend_2way(r45, r37b, w45, w37b):
    common = r45.index.intersection(r37b.index)
    return w45 * r45.loc[common] + w37b * r37b.loc[common]


def optimize_2way_maxsharpe(r45, r37b, n_steps=101):
    common = r45.index.intersection(r37b.index)
    a45  = r45.loc[common].values
    a37b = r37b.loc[common].values
    n_years = len(a45) / 12.0
    if n_years < 1:
        return FULL_W_H045, FULL_W_H037B, 0.0
    best_sharpe = -np.inf
    best_w45 = FULL_W_H045
    for w45 in np.linspace(0, 1, n_steps):
        w37b = 1.0 - w45
        rb     = w45 * a45 + w37b * a37b
        cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
        vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
        sharpe = cagr / vol if vol > 0 else 0.0
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_w45 = w45
    return float(best_w45), float(1 - best_w45), float(best_sharpe)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H051 — IS/OOS Validation of H050 (H045 + H037b Two-Component Portfolio)")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    prices_tr = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h051_treasury")
    spy_ohlc  = fetch_spy_ohlc(FULL_START, FULL_END)
    print(f"   Treasury ETFs available: {sorted(prices_tr.columns.tolist())}")
    print(f"   SPY OHLC: {spy_ohlc.index[0].date()} → {spy_ohlc.index[-1].date()}")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building equity curves …")
    eq_h045  = h045_equity_curve(prices_tr)
    eq_h037b = h037b_equity_curve(spy_ohlc)
    print(f"   H045  : {eq_h045.index[0].date()} → {eq_h045.index[-1].date()}  ({len(eq_h045)} days)")
    print(f"   H037b : {eq_h037b.index[0].date()} → {eq_h037b.index[-1].date()}  ({len(eq_h037b)} days)")

    # ── 3. Monthly returns, common window ────────────────────────────────────
    print("\n[3] Monthly returns …")
    r_h045_all  = to_monthly_returns(eq_h045)
    r_h037b_all = to_monthly_returns(eq_h037b)

    window_ts = pd.Timestamp(WINDOW_START)
    common_idx = (
        r_h045_all.index
        .intersection(r_h037b_all.index)
    )
    common_idx = common_idx[common_idx >= window_ts]

    r_h045  = r_h045_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]

    print(f"   Full common window: {common_idx[0].date()} → {common_idx[-1].date()} ({len(common_idx)} months)")

    # ── 4. IS / OOS split ────────────────────────────────────────────────────
    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)

    is_idx  = common_idx[(common_idx >= window_ts) & (common_idx <= is_ts)]
    oos_idx = common_idx[common_idx >= oos_ts]

    r_h045_is   = r_h045.loc[is_idx]
    r_h037b_is  = r_h037b.loc[is_idx]
    r_h045_oos  = r_h045.loc[oos_idx]
    r_h037b_oos = r_h037b.loc[oos_idx]

    print(f"   IS  window: {is_idx[0].date()} → {is_idx[-1].date()}  ({len(is_idx)} months)")
    print(f"   OOS window: {oos_idx[0].date()} → {oos_idx[-1].date()}  ({len(oos_idx)} months)")

    # IS correlations
    corr_full = float(r_h045.corr(r_h037b))
    corr_is   = float(r_h045_is.corr(r_h037b_is))
    corr_oos  = float(r_h045_oos.corr(r_h037b_oos))
    print(f"\n   Correlations — Full: {corr_full:.4f}  IS: {corr_is:.4f}  OOS: {corr_oos:.4f}")

    # ── 5. Optimize weights on IS ─────────────────────────────────────────────
    print("\n[4] Optimizing weights on IS data (101-step grid) …")
    is_w45, is_w37b, is_sharpe_opt = optimize_2way_maxsharpe(r_h045_is, r_h037b_is, n_steps=101)
    print(f"   IS-optimal weights: H045={is_w45:.2%}  H037b={is_w37b:.2%}")
    print(f"   IS-optimal Sharpe : {is_sharpe_opt:.4f}")

    # ── 6. Performance on IS at IS-optimal weights ────────────────────────────
    r_is_opt = blend_2way(r_h045_is, r_h037b_is, is_w45, is_w37b)
    s_is_opt = stats_from_monthly_returns(r_is_opt, "IS (IS-optimal weights)")
    print(f"\n   IS  (IS-optimal): CAGR {s_is_opt['cagr']:.2%}  Sharpe {s_is_opt['sharpe']:.4f}  MaxDD {s_is_opt['max_drawdown']:.2%}")

    # ── 7. OOS at IS-optimal weights ──────────────────────────────────────────
    r_oos_is_w = blend_2way(r_h045_oos, r_h037b_oos, is_w45, is_w37b)
    s_oos_is_w = stats_from_monthly_returns(r_oos_is_w, "OOS (IS-optimal weights)")
    print(f"   OOS (IS-optimal): CAGR {s_oos_is_w['cagr']:.2%}  Sharpe {s_oos_is_w['sharpe']:.4f}  MaxDD {s_oos_is_w['max_drawdown']:.2%}")

    # ── 8. OOS at full-period weights (82/18) ─────────────────────────────────
    r_oos_full = blend_2way(r_h045_oos, r_h037b_oos, FULL_W_H045, FULL_W_H037B)
    s_oos_full = stats_from_monthly_returns(r_oos_full, "OOS (full-period 82/18)")
    print(f"   OOS (full 82/18): CAGR {s_oos_full['cagr']:.2%}  Sharpe {s_oos_full['sharpe']:.4f}  MaxDD {s_oos_full['max_drawdown']:.2%}")

    # ── 9. Full-period at full-period weights (reference H050) ────────────────
    r_full_full = blend_2way(r_h045, r_h037b, FULL_W_H045, FULL_W_H037B)
    s_full_full = stats_from_monthly_returns(r_full_full, "Full (full-period 82/18)")
    print(f"   Full (82/18)    : CAGR {s_full_full['cagr']:.2%}  Sharpe {s_full_full['sharpe']:.4f}  MaxDD {s_full_full['max_drawdown']:.2%}")

    # ── 10. Degradation metrics ───────────────────────────────────────────────
    h050_full_sharpe = 1.9109  # from H050 results (fine-grained max-Sharpe)
    deg_is_weights   = (s_oos_is_w["sharpe"] - s_is_opt["sharpe"]) / s_is_opt["sharpe"] * 100
    deg_full_weights = (s_oos_full["sharpe"] - h050_full_sharpe) / h050_full_sharpe * 100
    print(f"\n   Degradation (IS→OOS, IS-optimal): {deg_is_weights:+.1f}%")
    print(f"   Degradation (full→OOS, 82/18 wts): {deg_full_weights:+.1f}%")
    print(f"   H047 reference (IS-optimal):        -23.8%  |  H042 reference: -9.3%")

    # ── 11. IS period standalone stats ───────────────────────────────────────
    s_h045_is   = stats_from_monthly_returns(r_h045_is,  "H045 IS")
    s_h037b_is  = stats_from_monthly_returns(r_h037b_is, "H037b IS")
    s_h045_oos  = stats_from_monthly_returns(r_h045_oos,  "H045 OOS")
    s_h037b_oos = stats_from_monthly_returns(r_h037b_oos, "H037b OOS")

    print(f"\n   H045  IS : Sharpe {s_h045_is['sharpe']:.4f}  OOS : Sharpe {s_h045_oos['sharpe']:.4f}")
    print(f"   H037b IS : Sharpe {s_h037b_is['sharpe']:.4f}  OOS : Sharpe {s_h037b_oos['sharpe']:.4f}")

    # Component degradations
    deg_h045_component  = (s_h045_oos["sharpe"]  - s_h045_is["sharpe"])  / s_h045_is["sharpe"]  * 100
    deg_h037b_component = (s_h037b_oos["sharpe"] - s_h037b_is["sharpe"]) / s_h037b_is["sharpe"] * 100
    print(f"   H045  degradation: {deg_h045_component:+.1f}%  |  H037b degradation: {deg_h037b_component:+.1f}%")

    # ── 12. 5-Fold Walk-Forward ───────────────────────────────────────────────
    print("\n[5] 5-fold walk-forward validation …")
    n = len(common_idx)
    fold_size = n // 5
    fold_results = []

    for fold in range(5):
        test_start_i = fold * fold_size
        test_end_i   = (fold + 1) * fold_size if fold < 4 else n
        if test_start_i < 24:
            print(f"   Fold {fold+1}: skipping (insufficient training data)")
            fold_results.append(None)
            continue

        train_idx = common_idx[:test_start_i]
        test_idx  = common_idx[test_start_i:test_end_i]

        r45_tr  = r_h045.loc[train_idx]
        r37b_tr = r_h037b.loc[train_idx]
        r45_te  = r_h045.loc[test_idx]
        r37b_te = r_h037b.loc[test_idx]

        fw45, fw37b, fs = optimize_2way_maxsharpe(r45_tr, r37b_tr, n_steps=51)

        r_test  = blend_2way(r45_te, r37b_te, fw45, fw37b)
        s_test  = stats_from_monthly_returns(r_test)
        r_train = blend_2way(r45_tr, r37b_tr, fw45, fw37b)
        s_train = stats_from_monthly_returns(r_train)

        fold_results.append({
            "fold":           fold + 1,
            "train_start":    str(train_idx[0].date()),
            "train_end":      str(train_idx[-1].date()),
            "train_months":   len(train_idx),
            "test_start":     str(test_idx[0].date()),
            "test_end":       str(test_idx[-1].date()),
            "test_months":    len(test_idx),
            "opt_weights":    {"w_h045": round(fw45, 4), "w_h037b": round(fw37b, 4)},
            "is_sharpe":      s_train.get("sharpe"),
            "oos_sharpe":     s_test.get("sharpe"),
            "oos_cagr":       s_test.get("cagr"),
            "oos_maxdd":      s_test.get("max_drawdown"),
        })
        if "error" not in s_test:
            print(f"   Fold {fold+1}: train {train_idx[0].date()}→{train_idx[-1].date()} ({len(train_idx)}m)  "
                  f"test {test_idx[0].date()}→{test_idx[-1].date()} ({len(test_idx)}m)  "
                  f"w={fw45:.2f}/{fw37b:.2f}  IS Sharpe={s_train.get('sharpe',0):.3f}  OOS Sharpe={s_test.get('sharpe',0):.3f}")
        else:
            print(f"   Fold {fold+1}: OOS error — {s_test}")

    valid_folds = [f for f in fold_results if f is not None and f["oos_sharpe"] is not None]
    oos_sharpes = [f["oos_sharpe"] for f in valid_folds]
    is_sharpes  = [f["is_sharpe"]  for f in valid_folds]
    avg_oos = float(np.mean(oos_sharpes)) if oos_sharpes else None
    std_oos = float(np.std(oos_sharpes))  if oos_sharpes else None
    avg_is  = float(np.mean(is_sharpes))  if is_sharpes  else None
    wf_deg  = (avg_oos - avg_is) / avg_is * 100 if (avg_oos and avg_is) else None

    print(f"\n   WF summary ({len(valid_folds)} folds): avg IS Sharpe {avg_is:.4f}  avg OOS Sharpe {avg_oos:.4f} ± {std_oos:.4f}")
    if wf_deg is not None:
        print(f"   WF degradation: {wf_deg:+.1f}%  (H049/H047 reference: -11.5%  H043/H042 reference: -20.2%)")

    # ── 13. Verdict ──────────────────────────────────────────────────────────
    print("\n[6] Verdict …")
    oos_s_is   = s_oos_is_w["sharpe"]
    oos_s_full = s_oos_full["sharpe"]
    deg_main   = deg_is_weights

    if abs(deg_main) <= 20 and oos_s_is >= 1.50:
        verdict = "CONFIRMED — Low overfit risk; OOS Sharpe competitive with H042"
    elif abs(deg_main) <= 30 and oos_s_is >= 1.30:
        verdict = "PARTIALLY CONFIRMED — Moderate degradation but OOS Sharpe investable"
    elif abs(deg_main) < 24 and oos_s_is >= 1.20:
        verdict = "BORDERLINE — Better than H047 but marginal versus H042"
    else:
        verdict = "REJECTED — Higher overfit than expected; 2-component simplicity did not help"

    # Compare vs H047 (23.8% degradation)
    if abs(deg_main) < 23.8:
        h047_compare = f"BETTER OOS robustness than H047 ({abs(deg_main):.1f}% vs 23.8%)"
    else:
        h047_compare = f"WORSE OOS robustness than H047 ({abs(deg_main):.1f}% vs 23.8%)"

    print(f"\n   OOS Sharpe (IS-optimal): {oos_s_is:.4f}")
    print(f"   OOS Sharpe (full 82/18): {oos_s_full:.4f}")
    print(f"   Degradation:             {deg_main:+.1f}%")
    print(f"   H047 comparison:         {h047_compare}")
    print(f"\n   Verdict: {verdict}")

    # ── 14. Summary table ─────────────────────────────────────────────────────
    print(f"\n{'=' * 92}")
    print("  H051 IS/OOS VALIDATION SUMMARY")
    print(f"{'=' * 92}")
    print(f"  {'Scenario':<52}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'Months':>7}")
    print(f"  {'-'*90}")
    for label, s, nm in [
        ("Full period (82/18) — H050 reference",      s_full_full,  len(common_idx)),
        ("IS  period  — IS-optimal weights",           s_is_opt,     len(is_idx)),
        ("OOS period  — IS-optimal weights",           s_oos_is_w,   len(oos_idx)),
        ("OOS period  — full-period weights (82/18)",  s_oos_full,   len(oos_idx)),
    ]:
        if "error" in s:
            print(f"  {label:<52}  {'ERROR':>8}")
        else:
            print(f"  {label:<52}  {s['cagr']:>8.2%}  {s['sharpe']:>8.4f}  {s['max_drawdown']:>8.2%}  {nm:>7}")

    # ── 15. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H051 — IS/OOS Validation of H050 (H045 + H037b)",
        "description": (
            "Tests whether H050's 2-component simplicity produces better OOS robustness "
            "than H047 (4-component, 23.8% IS/OOS degradation). "
            "IS: 2008-01→2017-12 / OOS: 2018-01→2026-04 (same split as H049)."
        ),
        "h050_reference": {
            "full_period_weights": {"w_h045": FULL_W_H045, "w_h037b": FULL_W_H037B},
            "full_period_sharpe": h050_full_sharpe,
        },
        "comparison_benchmarks": {
            "H042_IS_OOS_degradation_pct":  -9.3,
            "H047_IS_OOS_degradation_pct": -23.8,
        },
        "periods": {
            "full":  {"start": str(common_idx[0].date()), "end": str(common_idx[-1].date()), "n_months": len(common_idx)},
            "IS":    {"start": str(is_idx[0].date()),     "end": str(is_idx[-1].date()),     "n_months": len(is_idx)},
            "OOS":   {"start": str(oos_idx[0].date()),    "end": str(oos_idx[-1].date()),    "n_months": len(oos_idx)},
        },
        "correlations": {
            "full_period": round(corr_full, 4),
            "IS_period":   round(corr_is,   4),
            "OOS_period":  round(corr_oos,  4),
        },
        "IS_optimization": {
            "is_opt_weights": {"w_h045": round(is_w45, 4), "w_h037b": round(is_w37b, 4)},
            "is_opt_sharpe":  round(is_sharpe_opt, 4),
            "is_performance": s_is_opt,
        },
        "OOS_results": {
            "IS_optimal_weights":   s_oos_is_w,
            "full_period_weights":  s_oos_full,
        },
        "full_period_at_full_weights": s_full_full,
        "degradation": {
            "is_to_oos_pct_IS_weights":   round(deg_is_weights,   2),
            "full_to_oos_pct_full_weights": round(deg_full_weights, 2),
        },
        "component_performance": {
            "IS":  {"h045": s_h045_is,  "h037b": s_h037b_is},
            "OOS": {"h045": s_h045_oos, "h037b": s_h037b_oos},
            "component_degradations": {
                "h045_pct":  round(deg_h045_component,  2),
                "h037b_pct": round(deg_h037b_component, 2),
            },
        },
        "walk_forward": {
            "n_folds":           5,
            "method":            "expanding window",
            "fold_details":      [f for f in fold_results if f is not None],
            "avg_oos_sharpe":    round(avg_oos, 4) if avg_oos is not None else None,
            "std_oos_sharpe":    round(std_oos, 4) if std_oos is not None else None,
            "avg_is_sharpe":     round(avg_is,  4) if avg_is  is not None else None,
            "wf_degradation_pct": round(wf_deg, 2) if wf_deg is not None else None,
        },
        "verdict": {
            "summary":          verdict,
            "h047_comparison":  h047_compare,
            "oos_sharpe_IS_weights":   round(oos_s_is,   4),
            "oos_sharpe_full_weights": round(oos_s_full, 4),
            "degradation_IS_weights_pct": round(deg_is_weights, 2),
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h051_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
