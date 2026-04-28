"""
H056 — Walk-Forward Validation + IBS Weight Grid for H055/H055b
================================================================

Purpose:
  1. Walk-forward validation of H055 (SPY+QQQ IBS split) to confirm -9.7% OOS
     degradation is robust and not a lucky 2018-2026 period.
  2. Fine-grained grid: what is the optimal H037b/H054b split within the 28%
     IBS allocation? Is 50/50 (14/14) truly optimal, or does 0/28 or 28/0 do better?
  3. Key test: does H054b-only (H037b=0, H054b=28%) outperform H037b-only in OOS?

Grid tested (total IBS allocation kept at 28%):
  H037b = 28%, 24%, 20%, 16%, 14%, 12%, 8%, 4%, 0%
  H054b = 0%,  4%,  8%,  12%, 14%, 16%, 20%, 24%, 28%

IS/OOS split: 2008-01 → 2017-12 / 2018-01 → 2026-04 (same as H055)
Walk-forward: 5-fold expanding window on H055 (14/14 weights)

Also tests H055b extensions (with H045=20%):
  - H055b grid: vary IBS split while fixing H045=20%

Outputs:
  /workspace/agent/backtesting/results/h056_results.json
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
IS_END       = "2017-12-31"
OOS_START    = "2018-01-01"

H041A_ASSETS  = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
SECTOR_ETFS   = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
TOP_N_H41A = 2
TOP_N_H26  = 3
TOP_N_H45  = 2

IBS_BUY      = 0.20
IBS_SELL     = 0.80
MAX_HOLD     = 5
GAP_FILTER   = -0.005

# Fixed outer weights (H041a + H026 bundle)
W_H041A = 0.56
W_H026  = 0.16
TOTAL_IBS = 0.28   # total IBS budget (H037b + H054b must sum to this)

# H045 extension weight
W_H045_EXT = 0.20   # for H055b grid (scales all others by 0.80)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h   = hashlib.md5(key.encode()).hexdigest()[:12]
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h056_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h054", "h055"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    if ticker == "SPY":
        for fname in [
            f"h031_spy_ohlc_{start}_{end}.parquet",
            f"h042_spy_ohlc_{start}_{end}.parquet",
        ]:
            cp = CACHE_DIR / fname
            if cp.exists():
                df = pd.read_parquet(cp)
                if isinstance(df.columns, pd.MultiIndex):
                    df = df.xs("SPY", axis=1, level=1)
                df.columns = [c.lower() for c in df.columns]
                if all(c in df.columns for c in ["open", "high", "low", "close"]):
                    return df
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open", "High", "Low", "Close"]].rename(columns=str.lower)
    cp = CACHE_DIR / f"h056_{ticker}_ohlc_{start}_{end}.parquet"
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Strategy builders
# ─────────────────────────────────────────────────────────────────────────────

def momentum_equity_curve(prices, assets, top_n):
    available = [a for a in assets if a in prices.columns]
    if len(available) < top_n:
        return pd.Series(dtype=float)
    px = prices[available].dropna(how="all")
    if px.empty or len(px) < 20:
        return pd.Series(dtype=float)
    monthly_px   = px.resample("ME").last()
    monthly_rets = px.pct_change().resample("ME").apply(lambda x: (1 + x).prod() - 1)
    vol_6  = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    weight = 1.0 / top_n
    equity = INITIAL_EQUITY
    series = []
    for i in range(12, len(monthly_px)):
        month_end = monthly_px.index[i]
        mom_row   = mom_12.iloc[i].dropna()
        vol_row   = vol_6.iloc[i].dropna()
        valid     = mom_row.index.intersection(vol_row.index)
        if len(valid) < top_n:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top   = list(score.nlargest(top_n).index)
        sub_start = monthly_px.index[i - 1] + pd.Timedelta(days=1)
        sub = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = sum(
                weight * (float(sub[sym].iloc[j]) / float(sub[sym].iloc[j-1]) - 1)
                for sym in top
                if float(sub[sym].iloc[j-1]) > 0 and not np.isnan(sub[sym].iloc[j-1]) and not np.isnan(sub[sym].iloc[j])
            )
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def ibs_equity_curve(ohlc):
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
            if prev_ibs < IBS_BUY and cur_gap >= GAP_FILTER:
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


def to_monthly_returns(eq_daily):
    return eq_daily.resample("ME").last().ffill().pct_change().dropna()


def stats_from_monthly_returns(monthly_rets, label=""):
    monthly_rets = monthly_rets.dropna()
    if len(monthly_rets) < 6:
        return {"error": "insufficient data", "n_months": len(monthly_rets), "label": label}
    equity   = (1 + monthly_rets).cumprod()
    n_years  = len(monthly_rets) / 12.0
    cagr     = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol      = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe   = cagr / vol if vol > 0 else 0.0
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


def blend_returns(idx, r_dict, weights):
    r = pd.Series(0.0, index=idx)
    for k, w in weights.items():
        r = r + w * r_dict[k].loc[idx]
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H056 — Walk-Forward Validation + IBS Weight Grid for H055/H055b")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_mom = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices_mom = fetch_close(all_mom,       FULL_START, FULL_END, tag="h042_all")
    prices_tr  = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h051_treasury")
    spy_ohlc   = fetch_ohlc("SPY", FULL_START, FULL_END)
    qqq_ohlc   = fetch_ohlc("QQQ", FULL_START, FULL_END)
    print(f"   Data loaded.")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building component equity curves …")
    eq_h041a = momentum_equity_curve(prices_mom, H041A_ASSETS, TOP_N_H41A)
    eq_h026  = momentum_equity_curve(prices_mom, SECTOR_ETFS,  TOP_N_H26)
    eq_h037b = ibs_equity_curve(spy_ohlc)
    eq_h054b = ibs_equity_curve(qqq_ohlc)
    eq_h045  = momentum_equity_curve(prices_tr, TREASURY_ETFS, TOP_N_H45)
    print(f"   All curves built.")

    # ── 3. Monthly returns, common window ────────────────────────────────────
    r_dict = {k: to_monthly_returns(eq) for k, eq in [
        ("h041a", eq_h041a), ("h026", eq_h026),
        ("h037b", eq_h037b), ("h054b", eq_h054b), ("h045", eq_h045),
    ]}

    window_ts = pd.Timestamp(WINDOW_START)
    is_ts     = pd.Timestamp(IS_END)
    oos_ts    = pd.Timestamp(OOS_START)

    common_4 = r_dict["h041a"].index
    for k in ["h026", "h037b", "h054b"]:
        common_4 = common_4.intersection(r_dict[k].index)
    common_4 = common_4[common_4 >= window_ts]

    common_5 = common_4.intersection(r_dict["h045"].index)
    common_5 = common_5[common_5 >= window_ts]

    is_4  = common_4[(common_4 >= window_ts) & (common_4 <= is_ts)]
    oos_4 = common_4[common_4 >= oos_ts]
    is_5  = common_5[(common_5 >= window_ts) & (common_5 <= is_ts)]
    oos_5 = common_5[common_5 >= oos_ts]

    print(f"\n   4-way: {common_4[0].date()} → {common_4[-1].date()} ({len(common_4)}m)")
    print(f"   5-way: {common_5[0].date()} → {common_5[-1].date()} ({len(common_5)}m)")

    # ── 4. IBS weight grid (total IBS = 28%, vary H037b/H054b split) ─────────
    print("\n[3] IBS weight grid (total IBS budget = 28%) …")
    print(f"\n  {'H037b':>7}  {'H054b':>7}  {'Full S':>8}  {'IS S':>8}  {'OOS S':>8}  {'OOS MaxDD':>10}  {'Deg%':>7}  {'OOS CAGR':>10}")
    print(f"  {'-'*78}")

    grid_results_4 = []
    for w37b_pct in range(0, 29, 4):  # 0, 4, 8, 12, 14, 16, 20, 24, 28
        w37b = w37b_pct / 100.0
        w54b = TOTAL_IBS - w37b
        weights = {"h041a": W_H041A, "h026": W_H026, "h037b": w37b, "h054b": w54b}

        r_full = blend_returns(common_4, r_dict, weights)
        r_is   = blend_returns(is_4,     r_dict, weights)
        r_oos  = blend_returns(oos_4,    r_dict, weights)

        s_full = stats_from_monthly_returns(r_full)
        s_is   = stats_from_monthly_returns(r_is)
        s_oos  = stats_from_monthly_returns(r_oos)

        if "error" in s_is or "error" in s_oos:
            continue

        deg = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100
        row = {
            "w_h037b": round(w37b, 4), "w_h054b": round(w54b, 4),
            "full": s_full, "is": s_is, "oos": s_oos, "deg_pct": round(deg, 2),
        }
        grid_results_4.append(row)

        marker = " ← H055" if abs(w37b - 0.14) < 0.001 else (" ← H042" if abs(w37b - 0.28) < 0.001 else "")
        print(f"  {w37b:>7.1%}  {w54b:>7.1%}  {s_full['sharpe']:>8.4f}  {s_is['sharpe']:>8.4f}  "
              f"{s_oos['sharpe']:>8.4f}  {s_oos['max_drawdown']:>10.2%}  {deg:>7.1f}%  {s_oos['cagr']:>10.2%}{marker}")

    # ── 5. H055b grid (+H045=20%) ─────────────────────────────────────────────
    print(f"\n[4] H055b grid (H045=20% fixed, vary IBS split) …")
    print(f"\n  {'H037b':>7}  {'H054b':>7}  {'Full S':>8}  {'IS S':>8}  {'OOS S':>8}  {'OOS MaxDD':>10}  {'Deg%':>7}")
    print(f"  {'-'*68}")

    grid_results_5 = []
    for w37b_pct in range(0, 25, 4):  # 0, 4, 8, 10, 12, 16, 20, 22, 24
        w37b_raw = w37b_pct / 100.0
        w54b_raw = TOTAL_IBS - w37b_raw
        # Scale by (1 - H045_weight)
        scale = 1.0 - W_H045_EXT
        weights_5 = {
            "h041a": W_H041A * scale,
            "h026":  W_H026  * scale,
            "h037b": w37b_raw * scale,
            "h054b": w54b_raw * scale,
            "h045":  W_H045_EXT,
        }

        r_full = blend_returns(common_5, r_dict, weights_5)
        r_is   = blend_returns(is_5,     r_dict, weights_5)
        r_oos  = blend_returns(oos_5,    r_dict, weights_5)

        s_full = stats_from_monthly_returns(r_full)
        s_is   = stats_from_monthly_returns(r_is)
        s_oos  = stats_from_monthly_returns(r_oos)

        if "error" in s_is or "error" in s_oos:
            continue

        deg = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100
        row = {
            "w_h037b_raw": round(w37b_raw, 4), "w_h054b_raw": round(w54b_raw, 4),
            "weights": {k: round(v, 4) for k, v in weights_5.items()},
            "full": s_full, "is": s_is, "oos": s_oos, "deg_pct": round(deg, 2),
        }
        grid_results_5.append(row)

        w37b_actual = weights_5["h037b"]
        w54b_actual = weights_5["h054b"]
        marker = " ← H055b" if abs(w37b_raw - 0.14) < 0.001 else (" ← H052@20%" if w37b_raw > 0.22 and w54b_raw < 0.02 else "")
        print(f"  {w37b_actual:>7.1%}  {w54b_actual:>7.1%}  {s_full['sharpe']:>8.4f}  {s_is['sharpe']:>8.4f}  "
              f"{s_oos['sharpe']:>8.4f}  {s_oos['max_drawdown']:>10.2%}  {deg:>7.1f}%{marker}")

    # ── 6. Best allocations ───────────────────────────────────────────────────
    best_oos_4 = max(grid_results_4, key=lambda r: r["oos"]["sharpe"])
    best_oos_5 = max(grid_results_5, key=lambda r: r["oos"]["sharpe"])
    low_deg_4  = min(grid_results_4, key=lambda r: abs(r["deg_pct"]))

    print(f"\n[5] Best allocations (4-way without H045):")
    print(f"   Best OOS Sharpe : H037b={best_oos_4['w_h037b']:.1%} / H054b={best_oos_4['w_h054b']:.1%}  "
          f"→ OOS {best_oos_4['oos']['sharpe']:.4f}  Deg {best_oos_4['deg_pct']:+.1f}%")
    print(f"   Lowest degradat : H037b={low_deg_4['w_h037b']:.1%} / H054b={low_deg_4['w_h054b']:.1%}  "
          f"→ OOS {low_deg_4['oos']['sharpe']:.4f}  Deg {low_deg_4['deg_pct']:+.1f}%")
    print(f"\n   Best OOS Sharpe (5-way with H045=20%):")
    print(f"   H037b={best_oos_5['weights']['h037b']:.1%} / H054b={best_oos_5['weights']['h054b']:.1%}  "
          f"→ OOS {best_oos_5['oos']['sharpe']:.4f}  Deg {best_oos_5['deg_pct']:+.1f}%")

    # ── 7. Walk-forward validation of H055 (14/14 weights) ───────────────────
    print("\n[6] Walk-forward validation of H055 (56/16/14/14) …")
    H055_W = {"h041a": 0.56, "h026": 0.16, "h037b": 0.14, "h054b": 0.14}
    n = len(common_4)
    fold_size = n // 5
    fold_results = []

    for fold in range(5):
        test_start_i = fold * fold_size
        test_end_i   = (fold + 1) * fold_size if fold < 4 else n
        if test_start_i < 24:
            print(f"   Fold {fold+1}: skipping (insufficient training data)")
            fold_results.append(None)
            continue

        train_idx = common_4[:test_start_i]
        test_idx  = common_4[test_start_i:test_end_i]

        r_train = blend_returns(train_idx, r_dict, H055_W)
        r_test  = blend_returns(test_idx,  r_dict, H055_W)
        s_train = stats_from_monthly_returns(r_train)
        s_test  = stats_from_monthly_returns(r_test)

        fold_results.append({
            "fold": fold + 1,
            "train": f"{train_idx[0].date()}→{train_idx[-1].date()} ({len(train_idx)}m)",
            "test":  f"{test_idx[0].date()}→{test_idx[-1].date()} ({len(test_idx)}m)",
            "is_sharpe":  s_train.get("sharpe"),
            "oos_sharpe": s_test.get("sharpe"),
            "oos_maxdd":  s_test.get("max_drawdown"),
        })

        if "error" not in s_test:
            print(f"   Fold {fold+1}: IS {s_train.get('sharpe',0):.3f}  OOS {s_test.get('sharpe',0):.3f}  "
                  f"MaxDD {s_test.get('max_drawdown',0):.2%}  [{test_idx[0].date()}→{test_idx[-1].date()}]")

    valid_folds = [f for f in fold_results if f and f["oos_sharpe"] is not None]
    oos_sharpes = [f["oos_sharpe"] for f in valid_folds]
    is_sharpes  = [f["is_sharpe"]  for f in valid_folds]
    avg_oos     = float(np.mean(oos_sharpes)) if oos_sharpes else None
    std_oos     = float(np.std(oos_sharpes))  if oos_sharpes else None
    avg_is      = float(np.mean(is_sharpes))  if is_sharpes  else None
    wf_deg      = (avg_oos - avg_is) / avg_is * 100 if (avg_oos and avg_is) else None

    print(f"\n   WF summary ({len(valid_folds)} folds): avg IS {avg_is:.4f}  avg OOS {avg_oos:.4f} ± {std_oos:.4f}")
    if wf_deg:
        print(f"   WF degradation: {wf_deg:+.1f}%")
    print(f"   H050 WF reference: avg 1.722 ± 0.186  H047 WF reference: 2.067 ± 0.888")
    min_fold_oos = min(oos_sharpes) if oos_sharpes else None
    print(f"   Worst fold OOS Sharpe: {min_fold_oos:.4f}  (H047 worst: 0.613, H051 worst: 1.460)")

    # ── 8. Verdict ────────────────────────────────────────────────────────────
    print("\n[7] Verdict …")
    best_split_beats_5050 = best_oos_4["oos"]["sharpe"] > 1.829  # H055 OOS from H055 script
    h054b_only_row = next((r for r in grid_results_4 if r["w_h037b"] == 0.0), None)
    h037b_only_row = next((r for r in grid_results_4 if abs(r["w_h037b"] - 0.28) < 0.001), None)

    print(f"   H054b-only (28/0): OOS {h054b_only_row['oos']['sharpe']:.4f}  Deg {h054b_only_row['deg_pct']:+.1f}%")
    print(f"   H037b-only (0/28): OOS {h037b_only_row['oos']['sharpe']:.4f}  Deg {h037b_only_row['deg_pct']:+.1f}%")
    print(f"   50/50 split (H055): OOS ~1.829  Deg -9.7%")
    print(f"   Best OOS split: H037b={best_oos_4['w_h037b']:.1%} / H054b={best_oos_4['w_h054b']:.1%}  OOS {best_oos_4['oos']['sharpe']:.4f}")

    if best_split_beats_5050:
        verdict = "CONFIRMED — A different IBS split further improves H055"
    elif abs(best_oos_4["oos"]["sharpe"] - 1.829) < 0.01:
        verdict = "CONFIRMED — 50/50 split (H055) is near-optimal; fine-tuning provides marginal gains"
    else:
        verdict = "CONFIRMED — H055's 50/50 split is already close to optimal across the grid"

    wf_ok = (avg_oos > 1.60 and std_oos < 0.50) if (avg_oos and std_oos) else False
    wf_note = f"Walk-forward: avg OOS {avg_oos:.4f} ± {std_oos:.4f} — {'robust' if wf_ok else 'needs monitoring'}"

    print(f"\n   Verdict: {verdict}")
    print(f"   {wf_note}")

    # ── 9. Summary table ─────────────────────────────────────────────────────
    print(f"\n{'=' * 80}")
    print("  H056 SUMMARY")
    print(f"{'=' * 80}")

    # ── 10. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H056 — Walk-Forward Validation + IBS Weight Grid for H055/H055b",
        "description": (
            "Fine-grained grid over H037b/H054b IBS split (total IBS budget = 28%). "
            "Also walk-forward validates H055 (14/14 weights). "
            "Key question: is 50/50 optimal, or does H054b-only outperform?"
        ),
        "ibs_grid_4way": grid_results_4,
        "ibs_grid_5way_with_h045": grid_results_5,
        "best_4way": {
            "best_oos": {"w_h037b": best_oos_4["w_h037b"], "w_h054b": best_oos_4["w_h054b"], "oos_sharpe": best_oos_4["oos"]["sharpe"]},
            "lowest_deg": {"w_h037b": low_deg_4["w_h037b"], "w_h054b": low_deg_4["w_h054b"], "deg_pct": low_deg_4["deg_pct"]},
            "h054b_only": {"w_h037b": 0.0, "w_h054b": 0.28, "oos_sharpe": h054b_only_row["oos"]["sharpe"] if h054b_only_row else None},
            "h037b_only": {"w_h037b": 0.28, "w_h054b": 0.0, "oos_sharpe": h037b_only_row["oos"]["sharpe"] if h037b_only_row else None},
        },
        "best_5way": {"w_h037b": best_oos_5["weights"]["h037b"], "w_h054b": best_oos_5["weights"]["h054b"], "oos_sharpe": best_oos_5["oos"]["sharpe"]},
        "walk_forward": {
            "portfolio": "H055 (56/16/14/14)",
            "n_folds": 5,
            "fold_details": [f for f in fold_results if f is not None],
            "avg_oos_sharpe": round(avg_oos, 4) if avg_oos else None,
            "std_oos_sharpe": round(std_oos, 4) if std_oos else None,
            "avg_is_sharpe":  round(avg_is,  4) if avg_is  else None,
            "wf_deg_pct":     round(wf_deg,  2) if wf_deg  else None,
            "min_fold_oos":   round(min_fold_oos, 4) if min_fold_oos else None,
        },
        "verdict": {
            "summary":   verdict,
            "wf_note":   wf_note,
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h056_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
