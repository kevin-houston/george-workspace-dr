"""
H061 — H026 Marginal Value + Alternate IS/OOS Cross-Validation
==============================================================

Purpose:
  Two questions:
  1. Is H026 (sector ETF rotation, 7.3%) worth keeping in H060 production portfolio?
     H041a and H026 are both equity momentum — H026's 7.3% weight might just add
     correlated noise. Test: 3-component (H041a/H054b/H045 without H026) vs
     4-component H060.
     If H026 removal improves or doesn't hurt: simplify to 3-component.

  2. Alternate IS/OOS split cross-validation of H060.
     All prior tests used IS 2008-2017 / OOS 2018-2026.
     Test on IS 2003-2012 / OOS 2013-2026 (13-year OOS!) — completely different
     market regimes for both IS and OOS.
     If H060 production weights hold up on this alternate split: very high confidence.

  3. Correlation matrix of H060 components (H041a, H026, H054b, H045) to check
     for hidden concentration risks in the production portfolio.

H060 production weights: H041a 25.7% / H026 7.3% / H054b 28.0% / H045 39.0%

Outputs:
  /workspace/agent/backtesting/results/h061_results.json
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

# Primary IS/OOS split (all prior work)
IS_START_PRI = "2008-01-01"
IS_END_PRI   = "2017-12-31"
OOS_START_PRI = "2018-01-01"

# Alternate IS/OOS split
IS_START_ALT = "2003-01-01"
IS_END_ALT   = "2012-12-31"
OOS_START_ALT = "2013-01-01"

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

# H060 production weights
H060_W = {
    "h041a": 0.257,
    "h026":  0.073,
    "h054b": 0.280,
    "h045":  0.390,
}

# 3-component (no H026, H041a absorbs H026 allocation keeping H054b/H045 fixed)
H3C_W = {
    "h041a": 0.257 + 0.073,  # = 0.330
    "h026":  0.000,
    "h054b": 0.280,
    "h045":  0.390,
}

# 3-component proportional (H041a scaled, same H054b/H045)
# Normalise so total = 1: H041a=0.33/(0.33+0.28+0.39) = 0.33
# Already sum to 1: 0.33+0.28+0.39 = 1.00 ✓


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_close(tickers, start, end, tag=""):
    key  = "_".join(sorted(tickers)) + f"_{tag}_{start}_{end}"
    h    = hashlib.md5(key.encode()).hexdigest()[:12]
    for prefix_tag in ["h042_all", "h051_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h050", "h051", "h052", "h055", "h056", "h057", "h058", "h059", "h060"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h061_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw    = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    for prefix in ["h054", "h055", "h056", "h057", "h058", "h059", "h060"]:
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
    cp = CACHE_DIR / f"h061_{ticker}_ohlc_{start}_{end}.parquet"
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
        if w == 0.0:
            continue
        r = r + w * r_dict[k].reindex(idx, fill_value=0.0)
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H061 — H026 Marginal Value + Alternate IS/OOS Cross-Validation")
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
    print(f"   Curves built.")

    # ── 3. Correlation matrix ────────────────────────────────────────────────
    print("\n[3] Component correlation matrix (2008-2026 full window) …")
    ts = pd.Timestamp("2008-01-01")
    common = r_dict["h041a"].index
    for k in r_dict:
        common = common.intersection(r_dict[k].index)
    common = common[common >= ts]
    corr_df = pd.DataFrame({k: r_dict[k].reindex(common) for k in r_dict})
    corr = corr_df.corr()
    print(f"\n   Monthly return correlations (2008-2026, {len(common)}m):")
    for i, k1 in enumerate(["h041a", "h026", "h054b", "h045"]):
        row = "   " + f"{k1:7s}"
        for k2 in ["h041a", "h026", "h054b", "h045"]:
            row += f"  {corr.loc[k1, k2]:+.3f}"
        print(row)
    corr_results = corr.round(4).to_dict()

    # ── 4. H026 marginal value test ─────────────────────────────────────────
    print("\n[4] H026 marginal value (primary IS/OOS split 2008-2017 / 2018-2026) …")
    is_ts  = pd.Timestamp(IS_END_PRI)
    oos_ts = pd.Timestamp(OOS_START_PRI)
    is_idx  = common[(common <= is_ts)]
    oos_idx = common[common >= oos_ts]

    portfolios = {
        "H060 (4-way, H026 kept)":   H060_W,
        "3-component (H026 removed)": H3C_W,
    }

    print(f"\n  {'Portfolio':>35}  {'Full S':>7}  {'IS S':>7}  {'OOS S':>7}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'Deg%':>7}")
    print(f"  {'-'*90}")

    p_results = {}
    for label, w in portfolios.items():
        r_full = blend_returns(common,  r_dict, w)
        r_is   = blend_returns(is_idx,  r_dict, w)
        r_oos  = blend_returns(oos_idx, r_dict, w)
        s_f = stats_from_monthly_returns(r_full, label)
        s_i = stats_from_monthly_returns(r_is,   label + " IS")
        s_o = stats_from_monthly_returns(r_oos,  label + " OOS")
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100
        print(f"  {label:>35}  {s_f['sharpe']:>7.4f}  {s_i['sharpe']:>7.4f}  {s_o['sharpe']:>7.4f}  {s_o['cagr']*100:>8.1f}%  {s_o['max_drawdown']*100:>9.2f}%  {deg:>+7.1f}%")
        p_results[label] = {"full": s_f, "is": s_i, "oos": s_o, "deg": round(deg, 2)}

    h026_delta = p_results["3-component (H026 removed)"]["oos"]["sharpe"] - p_results["H060 (4-way, H026 kept)"]["oos"]["sharpe"]
    print(f"\n   H026 marginal contribution to OOS Sharpe: {-h026_delta:+.4f}")
    print(f"   {'H026 adds value — keep it' if h026_delta < 0 else 'H026 costs OOS Sharpe — consider removing'}")

    # ── 5. Alternate IS/OOS cross-validation ─────────────────────────────────
    print("\n[5] Alternate IS/OOS split: IS 2003-2012 / OOS 2013-2026 …")
    ts_alt_start = pd.Timestamp(IS_START_ALT)
    ts_alt_is_end = pd.Timestamp(IS_END_ALT)
    ts_alt_oos = pd.Timestamp(OOS_START_ALT)

    common_alt = r_dict["h041a"].index
    for k in r_dict:
        common_alt = common_alt.intersection(r_dict[k].index)
    common_alt = common_alt[common_alt >= ts_alt_start]
    is_alt  = common_alt[(common_alt >= ts_alt_start) & (common_alt <= ts_alt_is_end)]
    oos_alt = common_alt[common_alt >= ts_alt_oos]

    print(f"\n   Alt window: {common_alt[0].date()} → {common_alt[-1].date()} ({len(common_alt)}m)")
    print(f"   Alt IS: {is_alt[0].date()} → {is_alt[-1].date()} ({len(is_alt)}m)")
    print(f"   Alt OOS: {oos_alt[0].date()} → {oos_alt[-1].date()} ({len(oos_alt)}m)")

    print(f"\n  {'Portfolio':>35}  {'Full S':>7}  {'IS S':>7}  {'OOS S':>7}  {'OOS CAGR':>9}  {'OOS MaxDD':>10}  {'Deg%':>7}")
    print(f"  {'-'*90}")

    alt_results = {}
    for label, w in portfolios.items():
        r_full = blend_returns(common_alt, r_dict, w)
        r_is   = blend_returns(is_alt,     r_dict, w)
        r_oos  = blend_returns(oos_alt,    r_dict, w)
        s_f = stats_from_monthly_returns(r_full, label)
        s_i = stats_from_monthly_returns(r_is,   label + " IS alt")
        s_o = stats_from_monthly_returns(r_oos,  label + " OOS alt")
        deg = (s_o["sharpe"] - s_i["sharpe"]) / s_i["sharpe"] * 100
        print(f"  {label:>35}  {s_f['sharpe']:>7.4f}  {s_i['sharpe']:>7.4f}  {s_o['sharpe']:>7.4f}  {s_o['cagr']*100:>8.1f}%  {s_o['max_drawdown']*100:>9.2f}%  {deg:>+7.1f}%")
        alt_results[label] = {"full": s_f, "is": s_i, "oos": s_o, "deg": round(deg, 2)}

    print(f"\n   Note: Alt OOS (2013-2026) is a 13-year window vs primary OOS 8-year window.")

    # ── 6. Year-by-year for alternate OOS ─────────────────────────────────────
    print("\n[6] H060 year-by-year on alternate OOS (2013-2026) …")
    print(f"\n  {'Year':>6}  {'H060':>9}  {'3-comp':>9}")
    for year in range(2013, 2027):
        yr_idx = oos_alt[oos_alt.year == year]
        if len(yr_idx) < 3:
            continue
        def annual_ret(w):
            r = blend_returns(yr_idx, r_dict, w)
            return (1 + r).prod() - 1
        r60 = annual_ret(H060_W)
        r3c = annual_ret(H3C_W)
        print(f"  {year:>6}  {r60*100:>+8.1f}%  {r3c*100:>+8.1f}%")

    # ── 7. Verdict ────────────────────────────────────────────────────────────
    print("\n[7] Verdict …")
    h060_alt_oos = alt_results["H060 (4-way, H026 kept)"]["oos"]["sharpe"]
    h3c_alt_oos  = alt_results["3-component (H026 removed)"]["oos"]["sharpe"]
    h026_val = p_results["H060 (4-way, H026 kept)"]["oos"]["sharpe"] - p_results["3-component (H026 removed)"]["oos"]["sharpe"]
    print(f"   H026 marginal OOS value (primary split): {h026_val:+.4f} Sharpe")
    print(f"   H060 alternate OOS (2013-2026): Sharpe {h060_alt_oos:.4f}  vs 3-component {h3c_alt_oos:.4f}")
    print(f"   H060 primary OOS (2018-2026): Sharpe 2.1314 (from H060 run)")
    print(f"   Alt OOS degradation (H060): {alt_results['H060 (4-way, H026 kept)']['deg']:+.1f}%")

    h026_keep = h026_val > 0
    alt_robust = h060_alt_oos > 1.80
    print(f"\n   H026: {'KEEP' if h026_keep else 'CONSIDER REMOVING'} (OOS delta {h026_val:+.4f})")
    print(f"   Alternate OOS: {'ROBUST' if alt_robust else 'DEGRADED'} (Sharpe {h060_alt_oos:.4f})")

    # ── 8. Save results ──────────────────────────────────────────────────────
    results = {
        "hypothesis":         "H061",
        "description":        "H026 marginal value + alternate IS/OOS cross-validation",
        "correlations":       corr_results,
        "primary_split":      p_results,
        "alternate_split":    alt_results,
        "h026_marginal_oos":  round(h026_val, 4),
        "alt_oos_sharpe_h060": h060_alt_oos,
        "verdict": {
            "h026_keep":    h026_keep,
            "alt_robust":   alt_robust,
        },
    }
    out = RESULT_DIR / "h061_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved → {out}")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
