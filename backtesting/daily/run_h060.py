"""
H060 — Extended Validation: 2003-2026 window + H045 upper bound
================================================================

Purpose:
  H059 found H054b=28%/H045=35% as the WF-consistent winner. H060:
  1. Tests whether H045 can go beyond 35% at H054b=28%
     (H045=37%, 38%, 39%, 40% — fine-grained near the boundary)
  2. Validates H059 winner on the full 2003-2026 window (H026 starts 2001,
     H041a starts 2001, H054b starts ~2000, H045 starts 2003 — so 2003+ works)
  3. Shows year-by-year annual returns for the new portfolio vs SPY
  4. Runs IS/OOS on the 2003-2016 IS window (older IS split) for cross-check

Key question: Can H045 go to 37-38% while keeping WF worst ≥ 1.75?
If yes, a small incremental OOS gain is available.

Outputs:
  /workspace/agent/backtesting/results/h060_results.json
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
WINDOW_START = "2003-01-01"   # extended window start
WINDOW_IS_START = "2008-01-01"  # consistent IS start
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

# H059 winner
H059_W54B = 0.280
H059_W45  = 0.350

# Fine-grained upper-bound candidates
UPPER_CANDIDATES = [0.35, 0.36, 0.37, 0.38, 0.39, 0.40]

WF_WORST_MIN = 1.75


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key  = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h    = hashlib.md5(key.encode()).hexdigest()[:12]
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055", "h056", "h057", "h058", "h059"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h060_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h054", "h055", "h056", "h057", "h058", "h059"]:
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
    cp = CACHE_DIR / f"h060_{ticker}_ohlc_{start}_{end}.parquet"
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
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "calmar": 0.0, "n_months": 0}
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
    print("H060 — Extended Validation: 2003-2026 Window + H045 Upper Bound")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_mom    = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices_mom = fetch_close(all_mom,       FULL_START, FULL_END, tag="h042_all")
    prices_tr  = fetch_close(TREASURY_ETFS, FULL_START, FULL_END, tag="h051_treasury")
    qqq_ohlc   = fetch_ohlc("QQQ", FULL_START, FULL_END)
    spy_ohlc   = fetch_ohlc("SPY", FULL_START, FULL_END)
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
    print(f"   Curves built.")

    # SPY B&H monthly returns for comparison
    spy_monthly = to_monthly_returns(spy_ohlc["close"].resample("ME").last() * (INITIAL_EQUITY / spy_ohlc["close"].iloc[0]))

    # Common indices
    window_ts = pd.Timestamp(WINDOW_START)     # 2003-01-01
    is_start_ts = pd.Timestamp(WINDOW_IS_START)  # 2008-01-01
    is_ts     = pd.Timestamp(IS_END)
    oos_ts    = pd.Timestamp(OOS_START)

    common_ext = r_dict["h041a"].index
    for k in ["h026", "h054b", "h045"]:
        common_ext = common_ext.intersection(r_dict[k].index)
    common_ext = common_ext[common_ext >= window_ts]

    common_is = common_ext[common_ext >= is_start_ts]  # 2008+ window
    is_idx    = common_is[(common_is >= is_start_ts) & (common_is <= is_ts)]
    oos_idx   = common_is[common_is >= oos_ts]

    print(f"\n   Extended window: {common_ext[0].date()} → {common_ext[-1].date()} ({len(common_ext)}m)")
    print(f"   IS window (2008+): {is_idx[0].date()} → {is_idx[-1].date()} ({len(is_idx)}m)")
    print(f"   OOS window: {oos_idx[0].date()} → {oos_idx[-1].date()} ({len(oos_idx)}m)")

    # H059 winner weights
    h059_w = make_weights(H059_W54B, H059_W45)

    # ── 3. H059 on extended 2003-2026 window ─────────────────────────────────
    print("\n[3] H059 winner on extended 2003-2026 window …")
    r_ext = blend_returns(common_ext, r_dict, h059_w)
    s_ext = stats_from_monthly_returns(r_ext, "H059 2003-2026")
    print(f"   H059 (2003-2026): Sharpe {s_ext['sharpe']:.4f}  CAGR {s_ext['cagr']*100:.2f}%  MaxDD {s_ext['max_drawdown']*100:.2f}%  ({len(common_ext)}m)")

    # Compare to H057
    h057_w = make_weights(0.224, 0.20)
    r_h57_ext = blend_returns(common_ext, r_dict, h057_w)
    s_h57_ext = stats_from_monthly_returns(r_h57_ext, "H057 2003-2026")
    print(f"   H057 (2003-2026): Sharpe {s_h57_ext['sharpe']:.4f}  CAGR {s_h57_ext['cagr']*100:.2f}%  MaxDD {s_h57_ext['max_drawdown']*100:.2f}%")

    # ── 4. Year-by-year annual returns ───────────────────────────────────────
    print("\n[4] Year-by-year annual returns (H059 vs H057 vs SPY) …")
    print(f"\n  {'Year':>6}  {'H059 CAGR':>10}  {'H057 CAGR':>10}  {'SPY B&H':>10}")
    print(f"  {'-'*40}")

    annual_rows = []
    spy_full_rets = spy_monthly.reindex(common_ext, fill_value=0.0)
    for year in range(common_ext[0].year, common_ext[-1].year + 1):
        yr_idx = common_ext[common_ext.year == year]
        if len(yr_idx) < 3:
            continue
        r59  = blend_returns(yr_idx, r_dict, h059_w)
        r57  = blend_returns(yr_idx, r_dict, h057_w)
        r_spy = spy_full_rets.loc[yr_idx]
        def annual_ret(r):
            return (1 + r).prod() - 1
        ret59  = annual_ret(r59)
        ret57  = annual_ret(r57)
        ret_spy = annual_ret(r_spy)
        print(f"  {year:>6}  {ret59*100:>+9.1f}%  {ret57*100:>+9.1f}%  {ret_spy*100:>+9.1f}%")
        annual_rows.append({"year": year, "h059": round(ret59, 4), "h057": round(ret57, 4), "spy": round(ret_spy, 4)})

    # ── 5. H045 upper-bound fine-grid (H054b=28% fixed) ─────────────────────
    print("\n[5] H045 upper-bound fine-grid (H054b=28% fixed, WF on 2008+ window) …")
    print(f"\n  {'H045':>7}  {'IS S':>6}  {'OOS S':>6}  {'OOS CAGR':>9}  {'Deg%':>6}  {'WF avg':>7}  {'WF worst':>9}  {'Pass?':>6}")
    print(f"  {'-'*72}")

    upper_results = []
    for w45 in UPPER_CANDIDATES:
        w    = make_weights(H059_W54B, w45)
        r_is  = blend_returns(is_idx,  r_dict, w)
        r_oos = blend_returns(oos_idx, r_dict, w)
        s_is  = stats_from_monthly_returns(r_is)
        s_oos = stats_from_monthly_returns(r_oos)
        deg   = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100

        wf_rows = run_wf(common_is, r_dict, w)
        wf_sharpes = [r["oos_sharpe"] for r in wf_rows]
        wf_avg  = np.mean(wf_sharpes)
        wf_worst = min(wf_sharpes)
        passes  = wf_worst >= WF_WORST_MIN

        ok = "YES" if passes else "no"
        print(f"  {int(w45*100):>6}%  {s_is['sharpe']:>6.3f}  {s_oos['sharpe']:>6.3f}  {s_oos['cagr']*100:>8.1f}%  {deg:>+6.1f}%  {wf_avg:>7.3f}  {wf_worst:>9.3f}  {ok:>6}")
        upper_results.append({
            "w45": w45, "weights": w,
            "is_sharpe": s_is["sharpe"], "oos_sharpe": s_oos["sharpe"],
            "oos_cagr": s_oos["cagr"], "oos_maxdd": s_oos["max_drawdown"],
            "deg": round(deg, 2), "wf_avg": round(wf_avg, 4),
            "wf_worst": round(wf_worst, 4), "passes_wf": passes,
        })

    best_upper = max([r for r in upper_results if r["passes_wf"]], key=lambda x: x["oos_sharpe"], default=None)
    print(f"\n   Best passing upper bound: H045={int(best_upper['w45']*100)}% → OOS {best_upper['oos_sharpe']:.4f}  WF worst {best_upper['wf_worst']:.3f}" if best_upper else "   No passing upper bound found.")

    # ── 6. Definitive production portfolio ───────────────────────────────────
    print("\n[6] Definitive production portfolio …")
    prod_w45 = best_upper["w45"] if (best_upper and best_upper["oos_sharpe"] > 1.9829) else H059_W45
    prod_w = make_weights(H059_W54B, prod_w45)
    r_prod_oos = blend_returns(oos_idx, r_dict, prod_w)
    s_prod_oos = stats_from_monthly_returns(r_prod_oos, "Production OOS")
    r_prod_ext = blend_returns(common_ext, r_dict, prod_w)
    s_prod_ext = stats_from_monthly_returns(r_prod_ext, "Production 2003-2026")

    w_str = " / ".join(f"{k.upper()} {v*100:.1f}%" for k, v in prod_w.items())
    print(f"\n   Production portfolio: {w_str}")
    print(f"   Full (2003-2026):  Sharpe {s_prod_ext['sharpe']:.4f}  CAGR {s_prod_ext['cagr']*100:.2f}%  MaxDD {s_prod_ext['max_drawdown']*100:.2f}%")
    print(f"   OOS (2018-2026):   Sharpe {s_prod_oos['sharpe']:.4f}  CAGR {s_prod_oos['cagr']*100:.2f}%  MaxDD {s_prod_oos['max_drawdown']*100:.2f}%")

    # ── 7. Save results ──────────────────────────────────────────────────────
    results = {
        "hypothesis":       "H060",
        "description":      "Extended validation + H045 upper bound at H054b=28%",
        "h059_extended":    s_ext,
        "h057_extended":    s_h57_ext,
        "annual_returns":   annual_rows,
        "upper_bound_grid": upper_results,
        "best_upper":       best_upper,
        "production_weights": prod_w,
        "production_oos":   s_prod_oos,
        "production_ext":   s_prod_ext,
        "verdict": "CONFIRMED" if best_upper and best_upper["oos_sharpe"] > 1.9829 else "H059 UNCHANGED",
    }
    out = RESULT_DIR / "h060_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
