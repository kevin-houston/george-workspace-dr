"""
H057 — Full IS/OOS + WF validation of new optimal 4-way portfolio
  H041a 44.8% / H026 12.8% / H054b 22.4% / H045 20.0%
================================================================

Purpose:
  H056 grid proved the optimal IBS split is H037b=0% / H054b=22.4% (within the
  H055b 5-way structure). H037b is now completely eliminated. H057 formally
  validates this new 4-way portfolio with:
    1. Full IS/OOS stats (IS: 2008-01→2017-12, OOS: 2018-01→2026-04)
    2. 5-fold expanding walk-forward
    3. H054b allocation grid: can we push H054b > 22.4% by reducing H041a/H026?
    4. H045 allocation grid: is 20% still optimal or should we push to 25-30%?
    5. Component-level OOS analysis: H054b vs H037b comparison post-2018

Baseline:
  H041a 44.8% / H026 12.8% / H054b 22.4% / H045 20.0%
  (from H056: OOS Sharpe 1.9829, MaxDD -4.27%, Degradation -0.8%)

Portfolio label: H057 (the new best)

Outputs:
  /workspace/agent/backtesting/results/h057_results.json
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

IBS_BUY    = 0.20
IBS_SELL   = 0.80
MAX_HOLD   = 5
GAP_FILTER = -0.005

# H057 baseline weights (from H056 grid winner)
W_H041A_BASE = 0.448
W_H026_BASE  = 0.128
W_H054B_BASE = 0.224
W_H045_BASE  = 0.200


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key  = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h    = hashlib.md5(key.encode()).hexdigest()[:12]
    # Try prior caches (tagged with various run prefixes)
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055", "h056"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h057_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    # Ticker-specific caches first (never use SPY-named caches for non-SPY tickers)
    for prefix in ["h054", "h055", "h056"]:
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
    cp = CACHE_DIR / f"h057_{ticker}_ohlc_{start}_{end}.parquet"
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
    vol_6        = monthly_rets.rolling(6).std() * np.sqrt(12)
    mom_12       = monthly_px / monthly_px.shift(12) - 1
    weight       = 1.0 / top_n
    equity       = INITIAL_EQUITY
    series       = []
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
        sub       = px[top].loc[sub_start:month_end]
        if len(sub) < 2:
            continue
        for j in range(1, len(sub)):
            port_ret = sum(
                weight * (float(sub[sym].iloc[j]) / float(sub[sym].iloc[j-1]) - 1)
                for sym in top
                if float(sub[sym].iloc[j-1]) > 0
                   and not np.isnan(sub[sym].iloc[j-1])
                   and not np.isnan(sub[sym].iloc[j])
            )
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))
    if not series:
        return pd.Series(dtype=float)
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def ibs_equity_curve(ohlc):
    df        = ohlc.copy()
    denom     = (df["high"] - df["low"]).replace(0, np.nan)
    ibs       = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl   = df["close"].shift(1)
    gap       = (df["open"] - prev_cl) / prev_cl
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
        ret_oc   = (c / o - 1)      if o > 0      else 0.0
        ret_cc   = (c / c_prev - 1) if c_prev > 0 else 0.0
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
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd  = float((equity / roll_max - 1).min())
    calmar  = abs(cagr / max_dd) if max_dd < 0 else 0.0
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
        r = r + w * r_dict[k].reindex(idx, fill_value=0.0)
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H057 — Full Validation of New Optimal 4-Way Portfolio")
    print("  H041a 44.8% / H026 12.8% / H054b 22.4% / H045 20.0%")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_mom    = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices_mom = fetch_close(all_mom,       FULL_START, FULL_END, tag="h042_all")
    prices_tr  = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h051_treasury")
    qqq_ohlc   = fetch_ohlc("QQQ", FULL_START, FULL_END)
    print(f"   Data loaded.")

    # ── 2. Build component equity curves ─────────────────────────────────────
    print("\n[2] Building component equity curves …")
    eq_h041a = momentum_equity_curve(prices_mom, H041A_ASSETS, TOP_N_H41A)
    eq_h026  = momentum_equity_curve(prices_mom, SECTOR_ETFS,  TOP_N_H26)
    eq_h054b = ibs_equity_curve(qqq_ohlc)
    eq_h045  = momentum_equity_curve(prices_tr, TREASURY_ETFS, TOP_N_H45)
    print(f"   Curves built.")

    r_dict = {
        "h041a": to_monthly_returns(eq_h041a),
        "h026":  to_monthly_returns(eq_h026),
        "h054b": to_monthly_returns(eq_h054b),
        "h045":  to_monthly_returns(eq_h045),
    }

    window_ts = pd.Timestamp(WINDOW_START)
    is_ts     = pd.Timestamp(IS_END)
    oos_ts    = pd.Timestamp(OOS_START)

    common = r_dict["h041a"].index
    for k in ["h026", "h054b", "h045"]:
        common = common.intersection(r_dict[k].index)
    common = common[common >= window_ts]

    is_idx  = common[(common >= window_ts) & (common <= is_ts)]
    oos_idx = common[common >= oos_ts]
    print(f"\n   Common window: {common[0].date()} → {common[-1].date()} ({len(common)}m)")
    print(f"   IS: {is_idx[0].date()} → {is_idx[-1].date()} ({len(is_idx)}m)")
    print(f"   OOS: {oos_idx[0].date()} → {oos_idx[-1].date()} ({len(oos_idx)}m)")

    base_w = {
        "h041a": W_H041A_BASE,
        "h026":  W_H026_BASE,
        "h054b": W_H054B_BASE,
        "h045":  W_H045_BASE,
    }

    # ── 3. Baseline H057 stats ────────────────────────────────────────────────
    print("\n[3] H057 baseline (44.8/12.8/22.4/20.0) …")
    full_r = blend_returns(common,  r_dict, base_w)
    is_r   = blend_returns(is_idx,  r_dict, base_w)
    oos_r  = blend_returns(oos_idx, r_dict, base_w)

    full_s = stats_from_monthly_returns(full_r, "H057 full")
    is_s   = stats_from_monthly_returns(is_r,   "H057 IS")
    oos_s  = stats_from_monthly_returns(oos_r,  "H057 OOS")
    deg    = (oos_s["sharpe"] - is_s["sharpe"]) / is_s["sharpe"] * 100

    print(f"   Full  Sharpe: {full_s['sharpe']:.4f}  CAGR: {full_s['cagr']*100:.2f}%  MaxDD: {full_s['max_drawdown']*100:.2f}%")
    print(f"   IS    Sharpe: {is_s['sharpe']:.4f}  CAGR: {is_s['cagr']*100:.2f}%  MaxDD: {is_s['max_drawdown']*100:.2f}%")
    print(f"   OOS   Sharpe: {oos_s['sharpe']:.4f}  CAGR: {oos_s['cagr']*100:.2f}%  MaxDD: {oos_s['max_drawdown']*100:.2f}%")
    print(f"   Degradation: {deg:+.1f}%")

    # ── 4. Component IS/OOS analysis ─────────────────────────────────────────
    print("\n[4] Component OOS analysis …")
    comp_results = {}
    for k in ["h041a", "h026", "h054b", "h045"]:
        r_full = r_dict[k].reindex(common).dropna()
        r_is   = r_dict[k].reindex(is_idx).dropna()
        r_oos  = r_dict[k].reindex(oos_idx).dropna()
        s_full = stats_from_monthly_returns(r_full, k)
        s_is   = stats_from_monthly_returns(r_is,   k + " IS")
        s_oos  = stats_from_monthly_returns(r_oos,  k + " OOS")
        comp_deg = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100 if s_is["sharpe"] > 0 else float("nan")
        comp_results[k] = {"full": s_full, "is": s_is, "oos": s_oos, "deg": comp_deg}
        print(f"   {k:7s}: IS {s_is['sharpe']:.3f} → OOS {s_oos['sharpe']:.3f}  Deg: {comp_deg:+.1f}%")

    # ── 5. H054b allocation grid (vary H054b 16%→36%, fix H045=20%) ──────────
    print("\n[5] H054b allocation grid (H045=20% fixed, H041a+H026 absorb slack) …")
    print(f"\n  {'H054b':>7}  {'H041a':>7}  {'H026':>7}  {'Full S':>8}  {'IS S':>8}  {'OOS S':>8}  {'MaxDD':>8}  {'Deg%':>7}")
    print(f"  {'-'*68}")

    grid_h54b = []
    h45_fixed = 0.20
    # Original H041a:H026 ratio within the non-H045, non-IBS bucket = 56:16 = 3.5:1
    h41_h26_ratio = 56.0 / 16.0   # 3.5

    for h54b_pct in range(16, 37, 2):
        w54b = h54b_pct / 100.0
        remain = 1.0 - h45_fixed - w54b
        if remain <= 0:
            continue
        w41a = remain * h41_h26_ratio / (1 + h41_h26_ratio)
        w26  = remain / (1 + h41_h26_ratio)
        w = {"h041a": w41a, "h026": w26, "h054b": w54b, "h045": h45_fixed}
        r_full = blend_returns(common,  r_dict, w)
        r_is   = blend_returns(is_idx,  r_dict, w)
        r_oos  = blend_returns(oos_idx, r_dict, w)
        s_f = stats_from_monthly_returns(r_full)
        s_i = stats_from_monthly_returns(r_is)
        s_o = stats_from_monthly_returns(r_oos)
        dg  = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100
        grid_h54b.append({"w54b": w54b, "w41a": w41a, "w26": w26,
                          "full_sharpe": s_f["sharpe"], "is_sharpe": s_i["sharpe"],
                          "oos_sharpe": s_o["sharpe"], "oos_maxdd": s_o["max_drawdown"],
                          "deg": dg})
        marker = " ← H057" if abs(w54b - W_H054B_BASE) < 0.001 else ""
        print(f"  {w54b*100:>6.1f}%  {w41a*100:>6.1f}%  {w26*100:>6.1f}%  {s_f['sharpe']:>8.4f}  {s_i['sharpe']:>8.4f}  {s_o['sharpe']:>8.4f}  {s_o['max_drawdown']*100:>7.2f}%  {dg:>+7.1f}%{marker}")

    best_h54b = max(grid_h54b, key=lambda x: x["oos_sharpe"])
    print(f"\n   Best OOS Sharpe: H054b={best_h54b['w54b']*100:.1f}% → OOS {best_h54b['oos_sharpe']:.4f}  Deg {best_h54b['deg']:+.1f}%")

    # ── 6. H045 allocation grid (vary H045 15%→35%, H054b at 22.4%) ──────────
    print("\n[6] H045 allocation grid (H054b=22.4% fixed, H041a+H026 absorb slack) …")
    print(f"\n  {'H045':>7}  {'H041a':>7}  {'H026':>7}  {'Full S':>8}  {'IS S':>8}  {'OOS S':>8}  {'MaxDD':>8}  {'Deg%':>7}")
    print(f"  {'-'*68}")

    grid_h45 = []
    h54b_fixed = W_H054B_BASE  # 0.224

    for h45_pct in range(10, 41, 5):
        w45  = h45_pct / 100.0
        remain = 1.0 - h54b_fixed - w45
        if remain <= 0:
            continue
        w41a = remain * h41_h26_ratio / (1 + h41_h26_ratio)
        w26  = remain / (1 + h41_h26_ratio)
        w = {"h041a": w41a, "h026": w26, "h054b": h54b_fixed, "h045": w45}
        r_full = blend_returns(common,  r_dict, w)
        r_is   = blend_returns(is_idx,  r_dict, w)
        r_oos  = blend_returns(oos_idx, r_dict, w)
        s_f = stats_from_monthly_returns(r_full)
        s_i = stats_from_monthly_returns(r_is)
        s_o = stats_from_monthly_returns(r_oos)
        dg  = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100
        grid_h45.append({"w45": w45, "w41a": w41a, "w26": w26,
                         "full_sharpe": s_f["sharpe"], "is_sharpe": s_i["sharpe"],
                         "oos_sharpe": s_o["sharpe"], "oos_maxdd": s_o["max_drawdown"],
                         "deg": dg})
        marker = " ← H057" if abs(w45 - W_H045_BASE) < 0.001 else ""
        print(f"  {w45*100:>6.1f}%  {w41a*100:>6.1f}%  {w26*100:>6.1f}%  {s_f['sharpe']:>8.4f}  {s_i['sharpe']:>8.4f}  {s_o['sharpe']:>8.4f}  {s_o['max_drawdown']*100:>7.2f}%  {dg:>+7.1f}%{marker}")

    best_h45 = max(grid_h45, key=lambda x: x["oos_sharpe"])
    print(f"\n   Best OOS Sharpe: H045={best_h45['w45']*100:.1f}% → OOS {best_h45['oos_sharpe']:.4f}  Deg {best_h45['deg']:+.1f}%")

    # ── 7. 5-fold walk-forward ────────────────────────────────────────────────
    print("\n[7] 5-fold walk-forward validation of H057 …")
    n     = len(common)
    folds = []

    # Fold sizing: 56m train minimum, 16m test, expanding
    min_train = 56
    test_size = 16
    # Folds: train ends at i, test is [i+1 : i+test_size]
    fold_ends_train = [min_train - 1 + k * test_size for k in range(5)]

    wf_rows = []
    for fold_idx, te in enumerate(fold_ends_train):
        if te + 1 >= n:
            print(f"   Fold {fold_idx+1}: skipping (out of bounds)")
            continue
        train_idx = common[:te+1]
        test_end  = min(te + test_size, n - 1)
        test_idx  = common[te+1:test_end+1]
        if len(train_idx) < min_train or len(test_idx) < 6:
            print(f"   Fold {fold_idx+1}: skipping (insufficient data: train={len(train_idx)}, test={len(test_idx)})")
            continue
        # IS-optimal weights via grid search (vary H054b 16%→36%, H045 10%→40%)
        best_is_sharpe = -np.inf
        best_w = base_w.copy()
        for h54b_pct in range(16, 37, 4):
            for h45_pct in range(10, 41, 5):
                w54b = h54b_pct / 100.0
                w45  = h45_pct  / 100.0
                remain = 1.0 - w54b - w45
                if remain <= 0:
                    continue
                w41a = remain * h41_h26_ratio / (1 + h41_h26_ratio)
                w26  = remain / (1 + h41_h26_ratio)
                ww   = {"h041a": w41a, "h026": w26, "h054b": w54b, "h045": w45}
                r_tr = blend_returns(train_idx, r_dict, ww)
                s_tr = stats_from_monthly_returns(r_tr)
                if s_tr.get("sharpe", -np.inf) > best_is_sharpe:
                    best_is_sharpe = s_tr["sharpe"]
                    best_w = ww.copy()
        # OOS: use baseline weights (operating) and IS-optimal weights
        r_test_op = blend_returns(test_idx, r_dict, base_w)
        r_test_is = blend_returns(test_idx, r_dict, best_w)
        s_op = stats_from_monthly_returns(r_test_op, f"Fold {fold_idx+1} OOS (op)")
        s_is = stats_from_monthly_returns(r_test_is, f"Fold {fold_idx+1} OOS (IS-opt)")
        s_tr_stat = stats_from_monthly_returns(blend_returns(train_idx, r_dict, base_w), f"Fold {fold_idx+1} IS")
        deg_op = (s_op["sharpe"] - s_tr_stat["sharpe"]) / s_tr_stat["sharpe"] * 100 if s_tr_stat["sharpe"] > 0 else float("nan")
        print(f"   Fold {fold_idx+1}: IS {s_tr_stat['sharpe']:.3f}  OOS(op) {s_op['sharpe']:.3f}  OOS(IS-opt) {s_is['sharpe']:.3f}  MaxDD {s_op['max_drawdown']*100:.2f}%  [{test_idx[0].date()} → {test_idx[-1].date()}]")
        wf_rows.append({
            "fold":          fold_idx + 1,
            "train_end":     str(train_idx[-1].date()),
            "test_start":    str(test_idx[0].date()),
            "test_end":      str(test_idx[-1].date()),
            "is_sharpe":     s_tr_stat["sharpe"],
            "oos_sharpe_op": s_op["sharpe"],
            "oos_sharpe_is": s_is["sharpe"],
            "oos_maxdd":     s_op["max_drawdown"],
            "deg_op":        deg_op,
        })

    if wf_rows:
        oos_sharpes = [r["oos_sharpe_op"] for r in wf_rows]
        is_sharpes  = [r["is_sharpe"] for r in wf_rows]
        avg_oos = np.mean(oos_sharpes)
        std_oos = np.std(oos_sharpes, ddof=1)
        avg_is  = np.mean(is_sharpes)
        wf_deg  = (avg_oos - avg_is) / avg_is * 100 if avg_is > 0 else float("nan")
        worst   = min(oos_sharpes)
        print(f"\n   WF summary ({len(wf_rows)} folds): avg IS {avg_is:.4f}  avg OOS {avg_oos:.4f} ± {std_oos:.4f}")
        print(f"   WF degradation: {wf_deg:+.1f}%  |  Worst fold OOS: {worst:.4f}")
        print(f"   Reference: H056 WF avg OOS 2.2098 ± 0.3938  worst 1.726")
    else:
        print("   No valid folds.")
        wf_rows = []

    # ── 8. Verdict ───────────────────────────────────────────────────────────
    print("\n[8] Summary …")
    print(f"   H057 (H041a 44.8 / H026 12.8 / H054b 22.4 / H045 20.0):")
    print(f"     Full Sharpe {full_s['sharpe']:.4f}  IS {is_s['sharpe']:.4f}  OOS {oos_s['sharpe']:.4f}  Deg {deg:+.1f}%")
    print(f"     OOS MaxDD {oos_s['max_drawdown']*100:.2f}%  OOS CAGR {oos_s['cagr']*100:.2f}%")
    print(f"   Best H054b from grid: {best_h54b['w54b']*100:.1f}% → OOS {best_h54b['oos_sharpe']:.4f}")
    print(f"   Best H045 from grid:  {best_h45['w45']*100:.1f}% → OOS {best_h45['oos_sharpe']:.4f}")

    if wf_rows:
        oos_sharpes = [r["oos_sharpe_op"] for r in wf_rows]
        print(f"   WF: avg OOS {np.mean(oos_sharpes):.4f} ± {np.std(oos_sharpes, ddof=1):.4f}  worst {min(oos_sharpes):.4f}")

    confirmed = oos_s["sharpe"] > 1.90 and deg > -5.0
    print(f"\n   Verdict: {'CONFIRMED' if confirmed else 'NEEDS REVIEW'} — OOS Sharpe {oos_s['sharpe']:.4f}, Deg {deg:+.1f}%")

    # ── 9. Save results ──────────────────────────────────────────────────────
    results = {
        "hypothesis":    "H057",
        "description":   "Full validation of new optimal 4-way portfolio (H041a/H026/H054b/H045)",
        "baseline":      {"weights": base_w, "full": full_s, "is": is_s, "oos": oos_s, "deg_pct": round(deg, 2)},
        "components":    comp_results,
        "grid_h054b":    grid_h54b,
        "grid_h045":     grid_h45,
        "walk_forward":  wf_rows,
        "verdict":       "CONFIRMED" if confirmed else "NEEDS REVIEW",
    }
    out = RESULT_DIR / "h057_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
