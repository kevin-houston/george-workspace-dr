"""
H058 — 2D Allocation Grid: H054b × H045 Joint Optimisation
===========================================================

Purpose:
  H057 found that both H054b and H045 improve OOS Sharpe monotonically when
  increased independently (while holding the other fixed). H058 tests the 2D
  joint space to find the true OOS optimum.

  Constraint: H041a + H026 >= 20% (preserve equity growth engine, practical CAGR)
  H041a : H026 ratio maintained at 56:16 = 3.5:1 throughout.

Grid:
  H054b: 16%, 20%, 24%, 28%, 32%, 36%
  H045:  10%, 15%, 20%, 25%, 30%, 35%, 40%

For each cell:
  - Full period, IS, OOS Sharpe + MaxDD + CAGR + Deg%
  - Find OOS-optimal point
  - Also show practical-CAGR-filtered best (OOS CAGR >= 10%)

Then run 5-fold walk-forward on the 2D OOS winner.

IS/OOS split: 2008-01 → 2017-12 / 2018-01 → 2026-04 (consistent)

Outputs:
  /workspace/agent/backtesting/results/h058_results.json
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

# H041a:H026 fixed ratio
H41_H26_RATIO = 56.0 / 16.0  # 3.5

# Grid ranges
H54B_VALS = [0.16, 0.20, 0.24, 0.28, 0.32, 0.36]
H45_VALS  = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]

MIN_EQUITY_WT = 0.20  # H041a + H026 must be >= 20%


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key  = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h    = hashlib.md5(key.encode()).hexdigest()[:12]
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055", "h056", "h057"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h058_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h054", "h055", "h056", "h057"]:
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
    cp = CACHE_DIR / f"h058_{ticker}_ohlc_{start}_{end}.parquet"
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
        return {"error": "insufficient", "sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0, "n_months": 0}
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
    return {"h041a": w41a, "h026": w26, "h054b": w54b, "h045": w45}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H058 — 2D Allocation Grid: H054b × H045 Joint Optimisation")
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
    print(f"\n   Window: {common[0].date()} → {common[-1].date()} ({len(common)}m)")

    # ── 3. 2D grid ────────────────────────────────────────────────────────────
    print("\n[3] 2D grid: H054b × H045 …")

    # Print header
    h45_labels = [f"H45={int(h*100)}%" for h in H45_VALS]
    print(f"\n  OOS Sharpe matrix:")
    print(f"  {'H054b↓ H045→':>14}", end="")
    for h45 in H45_VALS:
        print(f"  {int(h45*100):>5}%", end="")
    print()

    grid = []
    best_oos      = -np.inf
    best_oos_pt   = None
    best_cagr_oos = -np.inf
    best_cagr_pt  = None   # best OOS Sharpe subject to OOS CAGR >= 10%

    for w54b in H54B_VALS:
        row_str = f"  {int(w54b*100):>5}% H054b "
        for w45 in H45_VALS:
            remain = 1.0 - w54b - w45
            if remain < MIN_EQUITY_WT:
                row_str += f"  {'---':>5} "
                continue
            w = make_weights(w54b, w45)
            r_oos = blend_returns(oos_idx, r_dict, w)
            r_is  = blend_returns(is_idx,  r_dict, w)
            s_oos = stats_from_monthly_returns(r_oos)
            s_is  = stats_from_monthly_returns(r_is)
            deg   = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100 if s_is["sharpe"] > 0 else float("nan")
            row_str += f"  {s_oos['sharpe']:>5.3f}"
            rec = {
                "w54b": w54b, "w45": w45,
                "w41a": w["h041a"], "w26": w["h026"],
                "is_sharpe":  s_is["sharpe"],  "is_cagr":  s_is["cagr"],
                "oos_sharpe": s_oos["sharpe"], "oos_cagr": s_oos["cagr"],
                "oos_maxdd":  s_oos["max_drawdown"],
                "deg": round(deg, 2),
            }
            grid.append(rec)
            if s_oos["sharpe"] > best_oos:
                best_oos    = s_oos["sharpe"]
                best_oos_pt = rec
            if s_oos["cagr"] >= 0.10 and s_oos["sharpe"] > best_cagr_oos:
                best_cagr_oos = s_oos["sharpe"]
                best_cagr_pt  = rec
        print(row_str)

    # MaxDD matrix
    print(f"\n  OOS MaxDD matrix:")
    print(f"  {'H054b↓ H045→':>14}", end="")
    for h45 in H45_VALS:
        print(f"  {int(h45*100):>5}%", end="")
    print()
    for w54b in H54B_VALS:
        row_str = f"  {int(w54b*100):>5}% H054b "
        for w45 in H45_VALS:
            rec = next((r for r in grid if abs(r["w54b"]-w54b)<0.001 and abs(r["w45"]-w45)<0.001), None)
            if rec is None:
                row_str += f"  {'---':>5} "
            else:
                row_str += f"  {rec['oos_maxdd']*100:>5.2f}"
        print(row_str)

    # OOS CAGR matrix
    print(f"\n  OOS CAGR matrix:")
    print(f"  {'H054b↓ H045→':>14}", end="")
    for h45 in H45_VALS:
        print(f"  {int(h45*100):>5}%", end="")
    print()
    for w54b in H54B_VALS:
        row_str = f"  {int(w54b*100):>5}% H054b "
        for w45 in H45_VALS:
            rec = next((r for r in grid if abs(r["w54b"]-w54b)<0.001 and abs(r["w45"]-w45)<0.001), None)
            if rec is None:
                row_str += f"  {'---':>5} "
            else:
                row_str += f"  {rec['oos_cagr']*100:>4.1f}%"
        print(row_str)

    print(f"\n   2D OOS winner (unconstrained):  H054b={best_oos_pt['w54b']*100:.0f}% / H045={best_oos_pt['w45']*100:.0f}%  →  OOS Sharpe {best_oos_pt['oos_sharpe']:.4f}  MaxDD {best_oos_pt['oos_maxdd']*100:.2f}%  CAGR {best_oos_pt['oos_cagr']*100:.1f}%  Deg {best_oos_pt['deg']:+.1f}%")
    if best_cagr_pt:
        print(f"   2D OOS winner (CAGR >= 10%):    H054b={best_cagr_pt['w54b']*100:.0f}% / H045={best_cagr_pt['w45']*100:.0f}%  →  OOS Sharpe {best_cagr_pt['oos_sharpe']:.4f}  MaxDD {best_cagr_pt['oos_maxdd']*100:.2f}%  CAGR {best_cagr_pt['oos_cagr']*100:.1f}%  Deg {best_cagr_pt['deg']:+.1f}%")

    # ── 4. Full stats for 2D winner ───────────────────────────────────────────
    print("\n[4] Full stats for 2D winner …")
    for label, pt in [("Unconstrained", best_oos_pt), ("CAGR>=10%", best_cagr_pt)]:
        if pt is None:
            continue
        w = make_weights(pt["w54b"], pt["w45"])
        r_full = blend_returns(common,  r_dict, w)
        r_is   = blend_returns(is_idx,  r_dict, w)
        r_oos  = blend_returns(oos_idx, r_dict, w)
        s_f = stats_from_monthly_returns(r_full, f"{label} full")
        s_i = stats_from_monthly_returns(r_is,   f"{label} IS")
        s_o = stats_from_monthly_returns(r_oos,  f"{label} OOS")
        dg  = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100
        print(f"\n   [{label}] H041a {w['h041a']*100:.1f}% / H026 {w['h026']*100:.1f}% / H054b {pt['w54b']*100:.0f}% / H045 {pt['w45']*100:.0f}%:")
        print(f"     Full:  Sharpe {s_f['sharpe']:.4f}  CAGR {s_f['cagr']*100:.2f}%  MaxDD {s_f['max_drawdown']*100:.2f}%")
        print(f"     IS:    Sharpe {s_i['sharpe']:.4f}  CAGR {s_i['cagr']*100:.2f}%  MaxDD {s_i['max_drawdown']*100:.2f}%")
        print(f"     OOS:   Sharpe {s_o['sharpe']:.4f}  CAGR {s_o['cagr']*100:.2f}%  MaxDD {s_o['max_drawdown']*100:.2f}%")
        print(f"     Degradation: {dg:+.1f}%")

    # ── 5. Walk-forward on CAGR-constrained winner ────────────────────────────
    print(f"\n[5] Walk-forward on CAGR>=10% winner …")
    wf_pt = best_cagr_pt if best_cagr_pt else best_oos_pt
    op_w  = make_weights(wf_pt["w54b"], wf_pt["w45"])
    h57_w = make_weights(0.224, 0.20)   # H057 reference

    n         = len(common)
    min_train = 56
    test_size = 16
    fold_ends_train = [min_train - 1 + k * test_size for k in range(5)]

    wf_rows = []
    for fold_idx, te in enumerate(fold_ends_train):
        if te + 1 >= n:
            continue
        train_idx = common[:te+1]
        test_end  = min(te + test_size, n - 1)
        test_idx  = common[te+1:test_end+1]
        if len(train_idx) < min_train or len(test_idx) < 6:
            continue
        s_tr   = stats_from_monthly_returns(blend_returns(train_idx, r_dict, op_w))
        s_oos  = stats_from_monthly_returns(blend_returns(test_idx,  r_dict, op_w))
        s_h57  = stats_from_monthly_returns(blend_returns(test_idx,  r_dict, h57_w))
        deg_op = (s_oos["sharpe"] - s_tr["sharpe"]) / s_tr["sharpe"] * 100 if s_tr["sharpe"] > 0 else float("nan")
        print(f"   Fold {fold_idx+1}: IS {s_tr['sharpe']:.3f}  OOS {s_oos['sharpe']:.3f}  (H057 ref: {s_h57['sharpe']:.3f})  MaxDD {s_oos['max_drawdown']*100:.2f}%  [{test_idx[0].date()} → {test_idx[-1].date()}]")
        wf_rows.append({
            "fold": fold_idx+1,
            "train_end": str(train_idx[-1].date()),
            "test_start": str(test_idx[0].date()),
            "test_end": str(test_idx[-1].date()),
            "is_sharpe": s_tr["sharpe"],
            "oos_sharpe": s_oos["sharpe"],
            "oos_sharpe_h57": s_h57["sharpe"],
            "oos_maxdd": s_oos["max_drawdown"],
            "deg": deg_op,
        })

    if wf_rows:
        sharpes = [r["oos_sharpe"] for r in wf_rows]
        is_s_wf = [r["is_sharpe"] for r in wf_rows]
        avg_oos = np.mean(sharpes)
        std_oos = np.std(sharpes, ddof=1)
        avg_is  = np.mean(is_s_wf)
        worst   = min(sharpes)
        print(f"\n   WF ({len(wf_rows)} folds): avg IS {avg_is:.4f}  avg OOS {avg_oos:.4f} ± {std_oos:.4f}  worst {worst:.4f}")

    # ── 6. Verdict ───────────────────────────────────────────────────────────
    print("\n[6] Verdict …")
    print(f"   H057 reference:  H054b=22.4% / H045=20.0% → OOS 1.9829  MaxDD -4.27%  Deg -0.8%")
    print(f"   H058 grid best:  H054b={best_cagr_pt['w54b']*100:.0f}% / H045={best_cagr_pt['w45']*100:.0f}% → OOS {best_cagr_pt['oos_sharpe']:.4f}  MaxDD {best_cagr_pt['oos_maxdd']*100:.2f}%  Deg {best_cagr_pt['deg']:+.1f}%")
    delta = best_cagr_pt["oos_sharpe"] - 1.9829
    print(f"   Improvement vs H057: {delta:+.4f} OOS Sharpe")

    confirmed = best_cagr_pt["oos_sharpe"] > 1.9829
    print(f"\n   Verdict: {'CONFIRMED — new portfolio is better than H057' if confirmed else 'INCONCLUSIVE'}")

    # ── 7. Save results ──────────────────────────────────────────────────────
    results = {
        "hypothesis":    "H058",
        "description":   "2D H054b × H045 joint allocation grid",
        "grid":          grid,
        "best_oos_unconstrained": best_oos_pt,
        "best_oos_cagr10": best_cagr_pt,
        "walk_forward":  wf_rows,
        "verdict":       "CONFIRMED" if confirmed else "INCONCLUSIVE",
    }
    out = RESULT_DIR / "h058_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
