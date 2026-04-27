"""
H043 — IS/OOS Validation + Walk-Forward of H042
=================================================

Purpose: Verify that H042's Sharpe 1.949 (56% H041a / 16% H026 / 28% H037b)
is genuine alpha and not optimization overfitting.

Three tests:
  1. IS/OOS Split
     - IS  : 2003-08 → 2016-12  (13.4 years)
     - OOS : 2017-01 → 2026-04  ( 9.3 years — COVID, 2022 bear, 2023-24 bull)
     a) Optimize weights on IS only → IS-optimal weights
     b) Apply IS-optimal weights to OOS → true OOS performance
     c) Apply full-period weights (56/16/28) to OOS → extra check

  2. 5-Fold Walk-Forward
     - Fold each fold ~4.6 years IS, ~2.3 years OOS (rolling)
     - Report avg OOS Sharpe and std dev

Outputs:
  /workspace/agent/backtesting/results/h043_results.json
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
WINDOW_START = "2003-08-01"

# IS/OOS split
IS_START  = "2003-08-01"
IS_END    = "2016-12-31"
OOS_START = "2017-01-01"
OOS_END   = "2026-04-27"

# H042 full-period optimal weights
FULL_W1 = 0.56   # H041a
FULL_W2 = 0.16   # H026
FULL_W3 = 0.28   # H037b

# Asset universes
H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
TOP_N_H41A   = 2

SECTOR_ETFS = [
    "XLK", "XLE", "XLF", "XLV", "XLI",
    "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
]
TOP_N_H26 = 3

# H037b params
IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER_B = -0.005


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers (reuse H042 cache logic)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    cp  = CACHE_DIR / f"h043_{h}.parquet"
    # also try h042 cache (same tickers/dates)
    h42_key = "_".join(sorted(tickers)) + f"_h042_all_{start}_{end}"
    h42_h   = hashlib.md5(h42_key.encode()).hexdigest()[:12]
    h42_cp  = CACHE_DIR / f"h042_{h42_h}.parquet"
    if h42_cp.exists():
        return pd.read_parquet(h42_cp)
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({start}→{end}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_spy_ohlc(start, end):
    for fname in [
        f"h031_spy_ohlc_{start}_{end}.parquet",
        f"h031b_spy_ohlc_{start}_{end}.parquet",
        f"h042_spy_ohlc_{start}_{end}.parquet",
    ]:
        cp = CACHE_DIR / fname
        if cp.exists():
            df = pd.read_parquet(cp)
            if isinstance(df.columns, pd.MultiIndex):
                df = df.xs("SPY", axis=1, level=1)
            for col in df.columns:
                df = df.rename(columns={col: col.lower()})
            if not all(c in df.columns for c in ["open", "high", "low", "close"]):
                df.columns = [c.lower() for c in df.columns]
            return df
    cp = CACHE_DIR / f"h043_spy_ohlc_{start}_{end}.parquet"
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
# Equity curve builders (copied from H042 to be self-contained)
# ─────────────────────────────────────────────────────────────────────────────

def h041a_equity_curve(prices):
    available = [a for a in H041A_ASSETS if a in prices.columns]
    if len(available) < TOP_N_H41A:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H41A
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H41A:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(TOP_N_H41A).index)
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


def h026_equity_curve(prices):
    available = [t for t in SECTOR_ETFS if t in prices.columns]
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / TOP_N_H26
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < TOP_N_H26:
            continue
        score    = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_hold = list(score.nlargest(TOP_N_H26).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top_hold].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in top_hold:
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
        ret_oc = (c / o - 1)      if o > 0     else 0.0
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

def stats_from_monthly_returns(monthly_rets):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "n_months": len(monthly_rets)}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd   = float((equity / roll_max - 1).min())
    calmar   = abs(cagr / max_dd) if max_dd < 0 else 0.0
    return {
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


def blend_monthly_returns(r1, r2, r3, w1, w2, w3):
    """Return blend monthly-return series on the common index."""
    common = r1.index.intersection(r2.index).intersection(r3.index)
    return w1 * r1.loc[common] + w2 * r2.loc[common] + w3 * r3.loc[common]


# ─────────────────────────────────────────────────────────────────────────────
# Optimizer: find max-Sharpe weights over a monthly-return window
# ─────────────────────────────────────────────────────────────────────────────

def optimize_weights_maxsharpe(r1, r2, r3, n_steps=51):
    """Grid search for max-Sharpe blend on provided monthly return series."""
    common = r1.index.intersection(r2.index).intersection(r3.index)
    a1 = r1.loc[common].values
    a2 = r2.loc[common].values
    a3 = r3.loc[common].values
    n_years = len(a1) / 12.0
    if n_years < 1:
        return 0.56, 0.16, 0.28, 0.0  # fallback

    best_sharpe = -np.inf
    best = (0.56, 0.16, 0.28)
    axis = np.linspace(0, 1, n_steps)
    for w1 in axis:
        for w2 in axis:
            w3 = 1.0 - w1 - w2
            if w3 < 0:
                continue
            rb     = w1 * a1 + w2 * a2 + w3 * a3
            cagr   = float(np.prod(1 + rb) ** (1 / n_years) - 1)
            vol    = float(np.std(rb, ddof=1)) * np.sqrt(12)
            sharpe = cagr / vol if vol > 0 else 0.0
            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best = (w1, w2, w3)
    return best[0], best[1], best[2], best_sharpe


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H043 — IS/OOS Validation + Walk-Forward of H042")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_tickers = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices   = fetch_close(all_tickers, FULL_START, FULL_END, tag="h042_all")
    spy_ohlc = fetch_spy_ohlc(FULL_START, FULL_END)

    # ── 2. Build equity curves on full history ────────────────────────────────
    print("\n[2] Building full equity curves …")
    eq_h041a_full = h041a_equity_curve(prices)
    eq_h026_full  = h026_equity_curve(prices)
    eq_h037b_full = h037b_equity_curve(spy_ohlc)

    for name, eq in [("H041a", eq_h041a_full), ("H026", eq_h026_full), ("H037b", eq_h037b_full)]:
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} trading days)")

    # ── 3. Full monthly returns, clipped to common window ────────────────────
    r_h041a_all = to_monthly_returns(eq_h041a_full)
    r_h026_all  = to_monthly_returns(eq_h026_full)
    r_h037b_all = to_monthly_returns(eq_h037b_full)

    window_ts  = pd.Timestamp(WINDOW_START)
    common_idx = (
        r_h041a_all.index
        .intersection(r_h026_all.index)
        .intersection(r_h037b_all.index)
    )
    common_idx = common_idx[common_idx >= window_ts]

    r_h041a = r_h041a_all.loc[common_idx]
    r_h026  = r_h026_all.loc[common_idx]
    r_h037b = r_h037b_all.loc[common_idx]

    print(f"\n   Full common window: {common_idx[0].date()} → {common_idx[-1].date()} ({len(common_idx)} months)")

    # ── 4. IS / OOS split ────────────────────────────────────────────────────
    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)

    is_idx  = common_idx[(common_idx >= window_ts)  & (common_idx <= is_ts)]
    oos_idx = common_idx[common_idx >= oos_ts]

    r1_is  = r_h041a.loc[is_idx]
    r2_is  = r_h026.loc[is_idx]
    r3_is  = r_h037b.loc[is_idx]

    r1_oos = r_h041a.loc[oos_idx]
    r2_oos = r_h026.loc[oos_idx]
    r3_oos = r_h037b.loc[oos_idx]

    print(f"\n   IS  window: {is_idx[0].date()} → {is_idx[-1].date()}  ({len(is_idx)} months, {len(is_idx)/12:.1f} yrs)")
    print(f"   OOS window: {oos_idx[0].date()} → {oos_idx[-1].date()}  ({len(oos_idx)} months, {len(oos_idx)/12:.1f} yrs)")

    # ── 5. Optimize on IS only ────────────────────────────────────────────────
    print("\n[3] Optimizing weights on IS data only (51×51 grid) …")
    is_w1, is_w2, is_w3, is_sharpe_opt = optimize_weights_maxsharpe(r1_is, r2_is, r3_is, n_steps=51)
    print(f"   IS-optimal weights: H041a={is_w1:.2%}  H026={is_w2:.2%}  H037b={is_w3:.2%}")
    print(f"   IS-optimal Sharpe : {is_sharpe_opt:.4f}")

    # ── 6. IS performance at IS-optimal weights ───────────────────────────────
    print("\n[4] IS performance at IS-optimal weights …")
    r_is_opt   = blend_monthly_returns(r1_is, r2_is, r3_is, is_w1, is_w2, is_w3)
    s_is_opt   = stats_from_monthly_returns(r_is_opt)
    print(f"   IS: CAGR {s_is_opt['cagr']:.2%}  Sharpe {s_is_opt['sharpe']:.4f}  MaxDD {s_is_opt['max_drawdown']:.2%}")

    # ── 7. OOS performance at IS-optimal weights ──────────────────────────────
    print("\n[5] OOS performance at IS-optimal weights …")
    r_oos_is_opt = blend_monthly_returns(r1_oos, r2_oos, r3_oos, is_w1, is_w2, is_w3)
    s_oos_is_opt = stats_from_monthly_returns(r_oos_is_opt)
    print(f"   OOS (IS-weights): CAGR {s_oos_is_opt['cagr']:.2%}  Sharpe {s_oos_is_opt['sharpe']:.4f}  MaxDD {s_oos_is_opt['max_drawdown']:.2%}")

    # ── 8. OOS performance at full-period weights (56/16/28) ─────────────────
    print("\n[6] OOS performance at full-period weights (56/16/28) …")
    r_oos_full_w = blend_monthly_returns(r1_oos, r2_oos, r3_oos, FULL_W1, FULL_W2, FULL_W3)
    s_oos_full_w = stats_from_monthly_returns(r_oos_full_w)
    print(f"   OOS (full-weights 56/16/28): CAGR {s_oos_full_w['cagr']:.2%}  Sharpe {s_oos_full_w['sharpe']:.4f}  MaxDD {s_oos_full_w['max_drawdown']:.2%}")

    # ── 9. Full-period performance (reference H042) ───────────────────────────
    r_full = blend_monthly_returns(r_h041a, r_h026, r_h037b, FULL_W1, FULL_W2, FULL_W3)
    s_full = stats_from_monthly_returns(r_full)
    print(f"\n   Full period (56/16/28): CAGR {s_full['cagr']:.2%}  Sharpe {s_full['sharpe']:.4f}  MaxDD {s_full['max_drawdown']:.2%}")

    # ── 10. Degradation metrics ───────────────────────────────────────────────
    full_sharpe = 1.9492  # H042 reported Sharpe (from h042_results.json)

    deg_is_weights = (s_oos_is_opt["sharpe"] - s_is_opt["sharpe"]) / s_is_opt["sharpe"] * 100
    deg_full_weights = (s_oos_full_w["sharpe"] - full_sharpe) / full_sharpe * 100

    print(f"\n   Sharpe degradation (IS→OOS, IS-optimal weights): {deg_is_weights:+.1f}%")
    print(f"   Sharpe degradation (full-period weights, full→OOS): {deg_full_weights:+.1f}%")

    # ── 11. 5-Fold Walk-Forward ───────────────────────────────────────────────
    print("\n[7] Running 5-fold walk-forward validation …")

    n = len(common_idx)
    fold_size  = n // 5

    fold_results = []
    for fold in range(5):
        # Rolling: train on all folds BEFORE test fold (not just 4)
        # Test fold is fold k, train is everything before it
        # Standard walk-forward: train grows, test is next slice
        test_start_i = fold * fold_size
        test_end_i   = (fold + 1) * fold_size if fold < 4 else n

        # We need at least 24 months to train, so skip fold 0 if too small
        if test_start_i < 24:
            # Use fold 0 as initial train, fold 1 as first test
            # i.e., offset by 1 fold
            print(f"   Fold {fold+1}: skipping (insufficient training data before fold)")
            fold_results.append(None)
            continue

        train_idx  = common_idx[:test_start_i]
        test_idx   = common_idx[test_start_i:test_end_i]

        r1_tr = r_h041a.loc[train_idx]
        r2_tr = r_h026.loc[train_idx]
        r3_tr = r_h037b.loc[train_idx]

        r1_te = r_h041a.loc[test_idx]
        r2_te = r_h026.loc[test_idx]
        r3_te = r_h037b.loc[test_idx]

        fw1, fw2, fw3, fs = optimize_weights_maxsharpe(r1_tr, r2_tr, r3_tr, n_steps=31)

        r_test  = blend_monthly_returns(r1_te, r2_te, r3_te, fw1, fw2, fw3)
        s_test  = stats_from_monthly_returns(r_test)

        r_train = blend_monthly_returns(r1_tr, r2_tr, r3_tr, fw1, fw2, fw3)
        s_train = stats_from_monthly_returns(r_train)

        fold_results.append({
            "fold":          fold + 1,
            "train_start":   str(train_idx[0].date()),
            "train_end":     str(train_idx[-1].date()),
            "train_months":  len(train_idx),
            "test_start":    str(test_idx[0].date()),
            "test_end":      str(test_idx[-1].date()),
            "test_months":   len(test_idx),
            "is_opt_weights": {"w_h041a": round(fw1,4), "w_h026": round(fw2,4), "w_h037b": round(fw3,4)},
            "is_sharpe":     s_train["sharpe"],
            "is_cagr":       s_train["cagr"],
            "oos_sharpe":    s_test["sharpe"] if "error" not in s_test else None,
            "oos_cagr":      s_test["cagr"]   if "error" not in s_test else None,
            "oos_maxdd":     s_test["max_drawdown"] if "error" not in s_test else None,
        })

        if "error" not in s_test:
            print(f"   Fold {fold+1}: train {train_idx[0].date()}→{train_idx[-1].date()} ({len(train_idx)}m)  "
                  f"test {test_idx[0].date()}→{test_idx[-1].date()} ({len(test_idx)}m)  "
                  f"opt_w={fw1:.2f}/{fw2:.2f}/{fw3:.2f}  "
                  f"IS Sharpe={s_train['sharpe']:.3f}  OOS Sharpe={s_test['sharpe']:.3f}")
        else:
            print(f"   Fold {fold+1}: OOS error — {s_test}")

    valid_folds = [f for f in fold_results if f is not None and f["oos_sharpe"] is not None]
    oos_sharpes = [f["oos_sharpe"] for f in valid_folds]
    is_sharpes  = [f["is_sharpe"]  for f in valid_folds]
    avg_oos_sharpe = float(np.mean(oos_sharpes)) if oos_sharpes else None
    std_oos_sharpe = float(np.std(oos_sharpes))  if oos_sharpes else None
    avg_is_sharpe  = float(np.mean(is_sharpes))  if is_sharpes else None

    print(f"\n   Walk-forward summary ({len(valid_folds)} valid folds):")
    print(f"     Avg IS  Sharpe : {avg_is_sharpe:.4f}")
    print(f"     Avg OOS Sharpe : {avg_oos_sharpe:.4f}  ± {std_oos_sharpe:.4f}")
    if avg_is_sharpe and avg_oos_sharpe:
        wf_deg = (avg_oos_sharpe - avg_is_sharpe) / avg_is_sharpe * 100
        print(f"     WF degradation : {wf_deg:+.1f}%")
    else:
        wf_deg = None

    # ── 12. Standalone component performance in OOS ───────────────────────────
    print("\n[8] OOS standalone component performance …")
    s_h041a_oos = stats_from_monthly_returns(r1_oos)
    s_h026_oos  = stats_from_monthly_returns(r2_oos)
    s_h037b_oos = stats_from_monthly_returns(r3_oos)
    print(f"   H041a OOS: CAGR {s_h041a_oos['cagr']:.2%}  Sharpe {s_h041a_oos['sharpe']:.4f}  MaxDD {s_h041a_oos['max_drawdown']:.2%}")
    print(f"   H026  OOS: CAGR {s_h026_oos['cagr']:.2%}  Sharpe {s_h026_oos['sharpe']:.4f}  MaxDD {s_h026_oos['max_drawdown']:.2%}")
    print(f"   H037b OOS: CAGR {s_h037b_oos['cagr']:.2%}  Sharpe {s_h037b_oos['sharpe']:.4f}  MaxDD {s_h037b_oos['max_drawdown']:.2%}")

    # ── 13. IS standalone ─────────────────────────────────────────────────────
    s_h041a_is = stats_from_monthly_returns(r1_is)
    s_h026_is  = stats_from_monthly_returns(r2_is)
    s_h037b_is = stats_from_monthly_returns(r3_is)

    # ── 14. Verdict ───────────────────────────────────────────────────────────
    print("\n[9] Generating verdict …")

    oos_sharpe_is_w = s_oos_is_opt["sharpe"]
    oos_sharpe_full_w = s_oos_full_w["sharpe"]

    if oos_sharpe_is_w >= 1.4 and abs(deg_is_weights) <= 20:
        overfitting_verdict = "LOW overfit risk — OOS Sharpe is strong and degradation is within normal range"
    elif oos_sharpe_is_w >= 1.2 and abs(deg_is_weights) <= 35:
        overfitting_verdict = "MODERATE overfit risk — meaningful degradation but OOS Sharpe remains investable"
    else:
        overfitting_verdict = "HIGH overfit risk — OOS performance degrades severely; weights likely overfit to IS period"

    print(f"\n   OOS Sharpe (IS-optimal weights): {oos_sharpe_is_w:.4f}")
    print(f"   OOS Sharpe (full-period 56/16/28): {oos_sharpe_full_w:.4f}")
    print(f"   Verdict: {overfitting_verdict}")

    # ── 15. Print full summary table ──────────────────────────────────────────
    print(f"\n{'=' * 92}")
    print("  H043 IS/OOS VALIDATION SUMMARY")
    print(f"{'=' * 92}")
    print(f"  {'Scenario':<52}  {'CAGR':>8}  {'Sharpe':>8}  {'MaxDD':>8}  {'Months':>7}")
    print(f"  {'-'*90}")
    rows = [
        ("Full period (56/16/28) — H042 reference",         s_full,        len(common_idx)),
        ("IS  period  — IS-optimal weights",                 s_is_opt,      len(is_idx)),
        ("OOS period  — IS-optimal weights",                 s_oos_is_opt,  len(oos_idx)),
        ("OOS period  — full-period weights (56/16/28)",     s_oos_full_w,  len(oos_idx)),
    ]
    for label, s, nm in rows:
        if "error" in s:
            print(f"  {label:<52}  {'ERROR':>8}  {'ERROR':>8}  {'ERROR':>8}  {nm:>7}")
        else:
            print(f"  {label:<52}  {s['cagr']:>8.2%}  {s['sharpe']:>8.4f}  {s['max_drawdown']:>8.2%}  {nm:>7}")

    # ── 16. Save results ──────────────────────────────────────────────────────
    output = {
        "strategy":    "H043 — IS/OOS Validation + Walk-Forward of H042",
        "description": "Formal overfitting check: optimize weights on IS (2003-2016), apply to OOS (2017-2026)",
        "h042_reference": {
            "weights": {"w_h041a": FULL_W1, "w_h026": FULL_W2, "w_h037b": FULL_W3},
            "full_period_sharpe": full_sharpe,
            "full_period_maxdd":  -0.0902,
        },
        "periods": {
            "full": {
                "start":    str(common_idx[0].date()),
                "end":      str(common_idx[-1].date()),
                "n_months": len(common_idx),
            },
            "IS": {
                "start":    str(is_idx[0].date()),
                "end":      str(is_idx[-1].date()),
                "n_months": len(is_idx),
                "n_years":  round(len(is_idx) / 12, 1),
            },
            "OOS": {
                "start":    str(oos_idx[0].date()),
                "end":      str(oos_idx[-1].date()),
                "n_months": len(oos_idx),
                "n_years":  round(len(oos_idx) / 12, 1),
            },
        },
        "IS_optimization": {
            "method":      "101-step grid search, max-Sharpe",
            "is_opt_weights": {
                "w_h041a": round(is_w1, 4),
                "w_h026":  round(is_w2, 4),
                "w_h037b": round(is_w3, 4),
            },
            "is_performance": s_is_opt,
        },
        "OOS_results": {
            "is_optimal_weights":    s_oos_is_opt,
            "full_period_weights":   s_oos_full_w,
        },
        "full_period_at_full_weights": s_full,
        "component_performance": {
            "IS": {
                "h041a": s_h041a_is,
                "h026":  s_h026_is,
                "h037b": s_h037b_is,
            },
            "OOS": {
                "h041a": s_h041a_oos,
                "h026":  s_h026_oos,
                "h037b": s_h037b_oos,
            },
        },
        "degradation": {
            "is_to_oos_sharpe_pct_is_weights":   round(deg_is_weights,   2),
            "full_to_oos_sharpe_pct_full_weights": round(deg_full_weights, 2),
            "note": "Negative = OOS Sharpe lower than IS/full-period Sharpe (expected; positive = OOS beats IS)",
        },
        "walk_forward": {
            "n_folds":       5,
            "method":        "expanding window: train on all data before test fold",
            "fold_details":  [f for f in fold_results if f is not None],
            "avg_oos_sharpe": round(avg_oos_sharpe, 4) if avg_oos_sharpe is not None else None,
            "std_oos_sharpe": round(std_oos_sharpe, 4) if std_oos_sharpe is not None else None,
            "avg_is_sharpe":  round(avg_is_sharpe,  4) if avg_is_sharpe  is not None else None,
            "wf_degradation_pct": round(wf_deg, 2) if wf_deg is not None else None,
        },
        "verdict": {
            "overfitting_risk":  overfitting_verdict,
            "oos_sharpe_is_weights":   round(oos_sharpe_is_w,   4),
            "oos_sharpe_full_weights": round(oos_sharpe_full_w, 4),
            "is_sharpe":               s_is_opt["sharpe"],
            "sharpe_deg_is_weights_pct":   round(deg_is_weights,   2),
            "sharpe_deg_full_weights_pct": round(deg_full_weights, 2),
            "comparable_strategies": {
                "H020_degradation_pct": -6.7,
                "H031_implicit": "not measured",
            },
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h043_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    result = main()
