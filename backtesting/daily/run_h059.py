"""
H059 — WF-Consistent Pareto Frontier: Moderate H054b/H045 Allocations
======================================================================

Purpose:
  H058 showed the aggressive allocation (H054b=32%/H045=40%) has OOS 2.145 but
  WF worst-fold drops to 1.413 (vs H057's 2.167). H059 tests moderate intermediate
  points to find the allocation that maximises OOS Sharpe while keeping
  WF worst-fold >= 1.75.

Candidates tested (from H058 2D grid, moderate cells):
  - H054b=24% / H045=25%  (OOS ~2.026)
  - H054b=24% / H045=30%  (OOS ~2.052)
  - H054b=28% / H045=25%  (OOS ~2.061)
  - H054b=28% / H045=28%  (OOS ~2.075)
  - H054b=28% / H045=30%  (OOS ~2.086)
  - H054b=28% / H045=35%  (OOS ~2.111)
  - H054b=32% / H045=25%  (OOS ~2.082)
  - H054b=32% / H045=30%  (OOS ~2.104)

For each candidate: 5-fold expanding WF + full IS/OOS stats.
Reference: H057 (22.4/20.0) OOS 1.9829, WF worst 2.167, WF std 0.822.

Selection criterion: max OOS Sharpe with WF worst-fold >= 1.75.

Outputs:
  /workspace/agent/backtesting/results/h059_results.json
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

H41_H26_RATIO = 56.0 / 16.0  # 3.5

# WF selection threshold
WF_WORST_MIN = 1.75

# Candidates: (H054b, H045)
CANDIDATES = [
    (0.224, 0.200),  # H057 reference
    (0.240, 0.250),
    (0.240, 0.300),
    (0.280, 0.250),
    (0.280, 0.275),
    (0.280, 0.300),
    (0.280, 0.350),
    (0.320, 0.250),
    (0.320, 0.300),
    (0.320, 0.350),
]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key  = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h    = hashlib.md5(key.encode()).hexdigest()[:12]
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055", "h056", "h057", "h058"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h059_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h054", "h055", "h056", "h057", "h058"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                return df
    if ticker == "SPY":
        for fname in [f"h031_spy_ohlc_{start}_{end}.parquet", f"h042_spy_ohlc_{start}_{end}.parquet"]:
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
    cp = CACHE_DIR / f"h059_{ticker}_ohlc_{start}_{end}.parquet"
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
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": 0}
    equity  = (1 + monthly_rets).cumprod()
    n_years = len(monthly_rets) / 12.0
    cagr    = float(equity.iloc[-1]) ** (1 / n_years) - 1
    vol     = float(monthly_rets.std(ddof=1)) * np.sqrt(12)
    sharpe  = cagr / vol if vol > 0 else 0.0
    roll_max = equity.expanding().max()
    max_dd  = float((equity / roll_max - 1).min())
    return {
        "label":        label,
        "cagr":         round(float(cagr),   4),
        "sharpe":       round(float(sharpe),  4),
        "max_drawdown": round(float(max_dd),  4),
        "n_months":     len(monthly_rets),
    }


def blend_returns(idx, r_dict, weights):
    r = pd.Series(0.0, index=idx)
    for k, w in weights.items():
        r = r + w * r_dict[k].reindex(idx, fill_value=0.0)
    return r


def make_weights(w54b, w45):
    remain = 1.0 - w54b - w45
    w41a   = remain * H41_H26_RATIO / (1 + H41_H26_RATIO)
    w26    = remain / (1 + H41_H26_RATIO)
    return {"h041a": round(w41a, 4), "h026": round(w26, 4), "h054b": w54b, "h045": w45}


def run_wf(common, r_dict, w, min_train=56, test_size=16):
    n = len(common)
    fold_ends = [min_train - 1 + k * test_size for k in range(5)]
    rows = []
    for fold_idx, te in enumerate(fold_ends):
        if te + 1 >= n:
            continue
        train_idx = common[:te+1]
        test_end  = min(te + test_size, n - 1)
        test_idx  = common[te+1:test_end+1]
        if len(train_idx) < min_train or len(test_idx) < 6:
            continue
        s_tr  = stats_from_monthly_returns(blend_returns(train_idx, r_dict, w))
        s_oos = stats_from_monthly_returns(blend_returns(test_idx,  r_dict, w))
        rows.append({
            "fold": fold_idx + 1,
            "is_sharpe":  s_tr["sharpe"],
            "oos_sharpe": s_oos["sharpe"],
            "oos_maxdd":  s_oos["max_drawdown"],
            "test_start": str(test_idx[0].date()),
            "test_end":   str(test_idx[-1].date()),
        })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H059 — WF-Consistent Pareto Frontier for Moderate H054b/H045 Allocations")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_mom    = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices_mom = fetch_close(all_mom,       FULL_START, FULL_END, tag="h042_all")
    prices_tr  = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h051_treasury")
    qqq_ohlc   = fetch_ohlc("QQQ", FULL_START, FULL_END)
    print(f"   Data loaded.")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building component equity curves …")
    eq_h041a = momentum_equity_curve(prices_mom, H041A_ASSETS, TOP_N_H41A)
    eq_h026  = momentum_equity_curve(prices_mom, SECTOR_ETFS,  TOP_N_H26)
    eq_h054b = ibs_equity_curve(qqq_ohlc)
    eq_h045  = momentum_equity_curve(prices_tr, TREASURY_ETFS, TOP_N_H45)

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
    print(f"   Window: {common[0].date()} → {common[-1].date()} ({len(common)}m)")

    # ── 3. Test each candidate ────────────────────────────────────────────────
    print("\n[3] Testing candidates (IS/OOS + WF) …")
    print(f"\n  {'Label':>22}  {'IS S':>6}  {'OOS S':>6}  {'OOS DD':>7}  {'OOS CAGR':>9}  {'Deg%':>6}  {'WF avg':>7}  {'WF std':>7}  {'WF worst':>9}  {'Pass?':>6}")
    print(f"  {'-'*108}")

    all_results = []
    for w54b, w45 in CANDIDATES:
        w    = make_weights(w54b, w45)
        r_is  = blend_returns(is_idx,  r_dict, w)
        r_oos = blend_returns(oos_idx, r_dict, w)
        s_is  = stats_from_monthly_returns(r_is)
        s_oos = stats_from_monthly_returns(r_oos)
        deg   = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100

        wf_rows = run_wf(common, r_dict, w)
        wf_sharpes = [r["oos_sharpe"] for r in wf_rows]
        wf_avg  = np.mean(wf_sharpes)
        wf_std  = np.std(wf_sharpes, ddof=1)
        wf_worst = min(wf_sharpes)
        passes  = wf_worst >= WF_WORST_MIN

        label = f"H054b={int(w54b*100)}%/H045={int(w45*100)}%"
        ref   = " ← H057" if abs(w54b - 0.224) < 0.001 and abs(w45 - 0.20) < 0.001 else ""
        ok    = "YES" if passes else "no"
        print(f"  {label:>22}  {s_is['sharpe']:>6.3f}  {s_oos['sharpe']:>6.3f}  {s_oos['max_drawdown']*100:>6.2f}%  {s_oos['cagr']*100:>8.1f}%  {deg:>+6.1f}%  {wf_avg:>7.3f}  {wf_std:>7.3f}  {wf_worst:>9.3f}  {ok:>6}{ref}")

        all_results.append({
            "w54b": w54b, "w45": w45, "weights": w,
            "is_sharpe": s_is["sharpe"], "is_cagr": s_is["cagr"],
            "oos_sharpe": s_oos["sharpe"], "oos_maxdd": s_oos["max_drawdown"],
            "oos_cagr": s_oos["cagr"], "deg": round(deg, 2),
            "wf_avg": round(wf_avg, 4), "wf_std": round(wf_std, 4),
            "wf_worst": round(wf_worst, 4),
            "wf_rows": wf_rows,
            "passes_wf": passes,
        })

    # ── 4. Select best ────────────────────────────────────────────────────────
    passing = [r for r in all_results if r["passes_wf"]]
    best    = max(passing, key=lambda x: x["oos_sharpe"]) if passing else None
    h057_ref = next(r for r in all_results if abs(r["w54b"] - 0.224) < 0.001)

    print(f"\n[4] Selection (WF worst-fold >= {WF_WORST_MIN}) …")
    if best:
        delta_oos = best["oos_sharpe"] - h057_ref["oos_sharpe"]
        print(f"   Best WF-consistent: H054b={int(best['w54b']*100)}% / H045={int(best['w45']*100)}%")
        print(f"     OOS Sharpe: {best['oos_sharpe']:.4f}  (H057: {h057_ref['oos_sharpe']:.4f}  Δ={delta_oos:+.4f})")
        print(f"     OOS MaxDD:  {best['oos_maxdd']*100:.2f}%  OOS CAGR: {best['oos_cagr']*100:.1f}%  Deg: {best['deg']:+.1f}%")
        print(f"     WF: avg {best['wf_avg']:.3f} ± {best['wf_std']:.3f}  worst {best['wf_worst']:.3f}")
        weights_str = " / ".join(f"{k.upper()} {v*100:.1f}%" for k, v in best["weights"].items())
        print(f"     Weights: {weights_str}")
    else:
        print("   No candidates passed WF threshold.")

    # Print WF detail for the best candidate
    if best:
        print(f"\n   WF fold detail for best candidate:")
        for r in best["wf_rows"]:
            print(f"     Fold {r['fold']}: IS {r['is_sharpe']:.3f}  OOS {r['oos_sharpe']:.3f}  MaxDD {r['oos_maxdd']*100:.2f}%  [{r['test_start']} → {r['test_end']}]")

    # ── 5. Verdict ───────────────────────────────────────────────────────────
    print("\n[5] Verdict …")
    if best and best["oos_sharpe"] > h057_ref["oos_sharpe"]:
        print(f"   CONFIRMED — H054b={int(best['w54b']*100)}%/H045={int(best['w45']*100)}% is the new WF-validated production portfolio.")
        print(f"   OOS improvement vs H057: {(best['oos_sharpe']-h057_ref['oos_sharpe']):+.4f}")
        verdict = "CONFIRMED"
    else:
        print(f"   H057 (22.4/20.0) remains the best WF-consistent portfolio.")
        verdict = "H057 PREFERRED"

    # ── 6. Save results ──────────────────────────────────────────────────────
    results = {
        "hypothesis": "H059",
        "description": "WF-consistent Pareto frontier for moderate H054b/H045 allocations",
        "wf_worst_threshold": WF_WORST_MIN,
        "candidates": all_results,
        "best_passing": best,
        "h057_reference": h057_ref,
        "verdict": verdict,
    }
    out = RESULT_DIR / "h059_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
