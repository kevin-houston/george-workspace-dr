"""
H486 — Dynamic Multi-Strategy Capital Allocation via Online Portfolio Selection
================================================================================

Source: universal-portfolios (Marigold, github.com/Marigold/universal-portfolios,
858 stars); dream cycle scan 2026-08-02.

Hypothesis: Replace the current STATIC target-weight blend across production
sleeves (H026 27% / H041a 22% / H045 21% / XLK IBS 20% / SMH IBS 8% / IGV IBS 2%)
with an Online Portfolio Selection (OPS) algorithm that dynamically reweights
sleeves based on their recent NAV trajectories — same family of algorithm as
OLMAR/CRP, applied to strategies-as-instruments instead of assets-as-instruments.

Design (3 phases):
  Phase 1 — Data prep: build nav_df (monthly return matrix) for all 6 production
    sleeves, reusing H500's exact production-blend reconstruction (H026 23-asset
    rotation, H041a 19-asset rotation, H045 13-asset bond rotation, XLK/SMH/IGV
    IBS legs) so the sleeve return series are faithful to the actual production
    system rather than a re-approximation. H174 PEAD is excluded — it is
    event-driven (not a continuously-held sleeve) and has no clean monthly NAV
    series comparable to the other 6 legs; PROD_W (the documented static blend)
    likewise does not include it.
  Phase 2 — Baseline replication: reproduce the current static PROD_W blend and
    confirm it lands close to the documented OOS Sharpe 4.158 / MaxDD -3.60%
    sanity-check numbers before trusting Phase 3's relative comparison.
  Phase 3 — OPS backtest: implement OLMAR (Online Moving Average Reversion,
    Li & Hoi 2012) and CRP (Constant Rebalanced Portfolio / uniform baseline)
    directly in numpy against nav_df (no new PyPI dependency — algorithms are
    ~30 lines each and avoids installing the unreviewed `universal-portfolios`
    package per the standing package-security policy). Compare resulting OOS
    Sharpe / MaxDD / turnover vs. the static baseline.

Gate: dynamically-reweighted blend OOS Sharpe > 4.158 AND MaxDD not worse than
-5.00% (baseline -3.60% + 1.4pp tolerance, matching the standard gate pattern).

Known risk: OPS algorithms assume free daily rebalancing into any "asset";
production sleeves have mismatched native cadences (H026/H041a/H045 monthly,
IBS sleeves near-daily, PEAD event-driven). This backtest necessarily operates
at monthly granularity (the common frequency across all sleeves) — a pass here
would still need a follow-up check that the achievable monthly rebalance
doesn't erode the improvement via turnover/transaction costs.
"""

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-04-27"
OOS_START  = "2018-01-01"

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

GATE_SHARPE = 4.158
GATE_MAXDD  = -0.05  # not worse than -5.00%

_PREFIXES = [f"h{i:03d}" for i in range(62, 113)] + ["h500", "h486"]


def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h486_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC ...")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        p = CACHE_DIR / f"{pfx}_{ticker}_ohlc_{start}_{end}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if "close" in df.columns:
                return df["close"].rename(ticker)
        cp2 = CACHE_DIR / f"{pfx}_{ticker}_close_{start}_{end}.parquet"
        if cp2.exists():
            return pd.read_parquet(cp2).squeeze().rename(ticker)
    cp = CACHE_DIR / f"h486_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} daily close ...")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


def build_rotation_monthly(tickers, start, end, n_hold=1):
    """Production 12-0 momentum rank-ensemble (rank(mom_12) + rank(inv_vol_6m))."""
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(13, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom   = (df["high"]-df["low"]).replace(0, np.nan)
    ibs     = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"]-prev_cl)/prev_cl
    equity  = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o-1) if o > 0 else 0.0
        ret_cc = (c/cp-1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1+ret_oc)
        else:
            days_held += 1; equity *= (1+ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _,v in series], index=pd.DatetimeIndex([d for d,_ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r)}
    eq   = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol  = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r)}


def common_idx(*series):
    idx = series[0].index
    for s in series[1:]:
        idx = idx.intersection(s.index)
    return idx.sort_values()


ts = pd.Timestamp
def oos_mask(idx): return idx >= ts(OOS_START)


# ── OPS algorithms (implemented directly — no `universal-portfolios` install) ──

def crp_backtest(ret_df: pd.DataFrame, w0: dict) -> pd.Series:
    """Constant Rebalanced Portfolio: fixed target weights, rebalanced every period.
    Equivalent to the static PROD_W blend when w0 == PROD_W — serves as the
    Phase 2 baseline replication / sanity check."""
    cols = list(ret_df.columns)
    w = np.array([w0[c] for c in cols])
    port_ret = (ret_df.values * w).sum(axis=1)
    return pd.Series(port_ret, index=ret_df.index)


def olmar_backtest(ret_df: pd.DataFrame, window: int = 5, eps: float = 10.0) -> tuple:
    """Online Moving Average Reversion (Li & Hoi 2012).
    At each step, predict next-period relative price via a moving-average
    reversion estimate, then solve for the weight vector meeting a target
    portfolio return of `eps` via projection onto the simplex (closed-form
    per the OLMAR-1 update rule). Returns (portfolio_returns, weights_df)."""
    cols = list(ret_df.columns)
    n_assets = len(cols)
    prices = (1 + ret_df).cumprod()
    prices = prices / prices.iloc[0]

    b = np.ones(n_assets) / n_assets  # start uniform
    port_rets = []
    weights_hist = []

    price_vals = prices.values
    for t in range(len(ret_df)):
        weights_hist.append(b.copy())
        x_t = ret_df.values[t] + 1.0  # relative price this period
        port_ret = float(np.dot(b, x_t - 1.0))
        port_rets.append(port_ret)

        # Update b for next period using MA-reversion predictor
        if t + 1 >= window:
            ma = price_vals[t + 1 - window: t + 1].mean(axis=0)
            cur_p = price_vals[t]
            x_pred = np.divide(ma, cur_p, out=np.ones_like(ma), where=cur_p != 0)
        else:
            x_pred = np.ones(n_assets)

        x_bar = x_pred.mean()
        denom = np.dot(x_pred - x_bar, x_pred - x_bar)
        if denom < 1e-8:
            b_new = b.copy()
        else:
            lam = max(0.0, (eps - np.dot(b, x_pred)) / denom)
            b_new = b + lam * (x_pred - x_bar)
            # Project onto simplex (non-negative, sum to 1)
            b_new = np.clip(b_new, 0, None)
            s = b_new.sum()
            b_new = b_new / s if s > 0 else np.ones(n_assets) / n_assets
        b = b_new

    port_series = pd.Series(port_rets, index=ret_df.index)
    weights_df = pd.DataFrame(weights_hist, index=ret_df.index, columns=cols)
    return port_series, weights_df


def turnover(weights_df: pd.DataFrame) -> float:
    """Average monthly L1 turnover (sum of |weight changes| / 2)."""
    diffs = weights_df.diff().abs().sum(axis=1) / 2.0
    return float(diffs.mean())


def main():
    print("=" * 80)
    print("H486 — Dynamic Multi-Strategy Capital Allocation via Online Portfolio Selection")
    print("=" * 80)

    print("\n[Phase 1] Building production sleeve NAV series (reusing H500 reconstruction) ...")
    xlk_r = to_monthly(ibs_equity_curve(fetch_ohlc("XLK", FULL_START, FULL_END), *XLK_PARAMS))
    smh_r = to_monthly(ibs_equity_curve(fetch_ohlc("SMH", FULL_START, FULL_END), *SMH_PARAMS))
    igv_r = to_monthly(ibs_equity_curve(fetch_ohlc("IGV", FULL_START, FULL_END), *IGV_PARAMS))
    h045_r = build_rotation_monthly(H045_PROD, FULL_START, FULL_END, 2)
    h026_r = build_rotation_monthly(H026_BASE, FULL_START, FULL_END, 1)
    h041a_r = build_rotation_monthly(H041A_FULL, FULL_START, FULL_END, 1)

    rd = {"h041a": h041a_r, "h026": h026_r, "h045": h045_r,
          "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}
    cidx = common_idx(*rd.values())
    nav_df = pd.DataFrame({k: v.reindex(cidx, fill_value=0.0) for k, v in rd.items()})
    print(f"  Sleeve NAV panel: {len(nav_df)} months, columns {list(nav_df.columns)}")
    print("  Note: H174 PEAD excluded — event-driven, no continuous monthly NAV series,")
    print("  and not part of the documented static PROD_W blend either.")

    oos_idx = cidx[oos_mask(cidx)]
    nav_oos = nav_df.loc[oos_idx]

    print("\n[Phase 2] Baseline replication: static PROD_W blend (CRP with fixed target weights) ...")
    static_rets = crp_backtest(nav_df, PROD_W)
    static_oos = static_rets.loc[oos_idx]
    base_stats = stats(static_oos)
    print(f"  Static PROD_W blend OOS: Sharpe={base_stats['sharpe']:.3f}, "
          f"MaxDD={base_stats['max_drawdown']:.2%}, CAGR={base_stats['cagr']:.2%}")
    print(f"  (Documented production reference: OOS Sharpe 4.158, MaxDD -3.60%, ~23.5% CAGR)")

    print("\n[Phase 3] OPS backtests: OLMAR + uniform CRP ...")
    results = {}

    olmar_variants = [
        ("OLMAR_w5_eps10", 5, 10.0),
        ("OLMAR_w10_eps10", 10, 10.0),
        ("OLMAR_w5_eps3", 5, 3.0),
    ]
    best_olmar_series = None
    best_olmar_label = None
    best_olmar_sharpe = -999
    for label, window, eps in olmar_variants:
        port_rets, weights_df = olmar_backtest(nav_df, window=window, eps=eps)
        port_oos = port_rets.loc[oos_idx]
        s = stats(port_oos)
        to_ = turnover(weights_df.loc[oos_idx])
        print(f"  {label}: OOS Sharpe={s['sharpe']:.3f}, MaxDD={s['max_drawdown']:.2%}, "
              f"CAGR={s['cagr']:.2%}, avg monthly turnover={to_:.1%}")
        results[label] = {**s, "turnover": round(to_, 4)}
        if s["sharpe"] > best_olmar_sharpe:
            best_olmar_sharpe = s["sharpe"]
            best_olmar_series = port_oos
            best_olmar_label = label

    uniform_w = {k: 1.0 / len(rd) for k in rd}
    uniform_rets = crp_backtest(nav_df, uniform_w)
    uniform_oos = uniform_rets.loc[oos_idx]
    us = stats(uniform_oos)
    print(f"  Uniform_CRP (1/N): OOS Sharpe={us['sharpe']:.3f}, MaxDD={us['max_drawdown']:.2%}, "
          f"CAGR={us['cagr']:.2%}")
    results["Uniform_CRP"] = us

    results["Static_PROD_W_baseline"] = base_stats

    print(f"\n[Gate Check] OOS Sharpe > {GATE_SHARPE} AND MaxDD > {GATE_MAXDD:.0%}")
    winners = []
    for label in [l for l, _, _ in olmar_variants] + ["Uniform_CRP"]:
        s = results[label]
        passed = s["sharpe"] > GATE_SHARPE and s["max_drawdown"] > GATE_MAXDD
        flag = "PASS" if passed else "FAIL"
        print(f"  {label}: Sharpe={s['sharpe']:.3f} MaxDD={s['max_drawdown']:.2%} => {flag}")
        if passed:
            winners.append(label)

    confirmed = len(winners) > 0
    print(f"\n{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
    print(f"  Best OPS variant: {best_olmar_label} Sharpe={best_olmar_sharpe:.3f} vs static baseline "
          f"{base_stats['sharpe']:.3f} and gate {GATE_SHARPE}")

    # Correlation of best OLMAR variant vs static baseline (production blend proxy)
    corr = float(pd.concat([best_olmar_series.rename("olmar"), static_oos.rename("static")],
                            axis=1).corr().iloc[0, 1])
    print(f"  Corr(best OLMAR variant, static PROD_W baseline) OOS: {corr:.3f}")

    output = {
        "hypothesis": "H486",
        "phase2_baseline_replication": base_stats,
        "phase2_documented_reference": {"sharpe": 4.158, "max_drawdown": -0.036},
        "results": results,
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": bool(confirmed),
        "winners": winners,
        "best_olmar_variant": best_olmar_label,
        "corr_best_olmar_vs_static": round(corr, 3),
    }
    out_path = RESULT_DIR / "h486_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved -> {out_path}")

    static_oos.to_csv(RESULT_DIR / "h486_static_baseline_returns.csv", header=["ret"])
    if best_olmar_series is not None:
        best_olmar_series.to_csv(RESULT_DIR / "h486_best_olmar_returns.csv", header=["ret"])
    print("=" * 80)


if __name__ == "__main__":
    main()
