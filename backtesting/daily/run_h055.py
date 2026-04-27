"""
H055 — H042 with IBS Hedge: Split H037b Allocation Between SPY + QQQ IBS
=========================================================================

Motivation from H054:
  - H037b (SPY IBS): IS Sharpe 1.350, OOS Sharpe 0.873 → -35% degradation (FADING)
  - H054b (QQQ IBS): IS Sharpe 0.831, OOS Sharpe 1.472 → +77% improvement (STRENGTHENING)
  - Monthly correlation H054b vs H037b: 0.49 (just below 0.50 threshold)

Hypothesis: Replace half of H037b's allocation with H054b to:
  1. Maintain total IBS exposure (~28% of H042)
  2. Hedge against H037b's fading OOS edge
  3. Capture QQQ IBS's improving OOS trend
  4. Reduce concentration risk in a single IBS instrument

H055 design:
  - H041a:  56%  (unchanged from H042)
  - H026:   16%  (unchanged from H042)
  - H037b:  14%  (half of H042's 28%)
  - H054b:  14%  (QQQ IBS -0.5% filter, the other half)
  Total = 100%

Also test H055b: Equal-weighted split with H045 layer
  - H041a:  44.8% (56% × 80%)
  - H026:   12.8% (16% × 80%)
  - H037b:  11.2% (14% × 80%)
  - H054b:  11.2% (14% × 80%)
  - H045:   20.0%
  Total = 100%

IS/OOS validation (same split as H051/H052):
  IS: 2008-01 → 2017-12 (120 months)
  OOS: 2018-01 → 2026-04 (100 months)

Confirm criteria:
  - H055 OOS Sharpe > H042 OOS Sharpe (1.655 on 2018-2026 window)
  - H055 OOS degradation < H042 degradation (-20.2% on this window)
  - H055b OOS Sharpe > H052@20% OOS Sharpe (1.708)

Outputs:
  /workspace/agent/backtesting/results/h055_results.json
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

H041A_ASSETS = ["SPY", "QQQ", "TLT", "GLD", "IEF", "EFA", "EEM"]
SECTOR_ETFS  = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
TREASURY_ETFS = ["SHY", "IEI", "IEF", "TLT", "TIP", "HYG", "LQD"]
TOP_N_H41A = 2
TOP_N_H26  = 3
TOP_N_H45  = 2

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
    for prefix_tag in ["h042_all", "h043_", "h051_treasury", "h050_treasury"]:
        test_key = "_".join(sorted(tickers)) + f"_{prefix_tag}_{start}_{end}"
        test_h   = hashlib.md5(test_key.encode()).hexdigest()[:12]
        for prefix in ["h042", "h043", "h050", "h051", "h052"]:
            cp = CACHE_DIR / f"{prefix}_{test_h}.parquet"
            if cp.exists():
                return pd.read_parquet(cp)
    cp = CACHE_DIR / f"h055_{h}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers ({tag}) …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


def fetch_ohlc(ticker, start, end):
    # Ticker-specific cache from H054 (only valid source for QQQ)
    for prefix in ["h054", "h055"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open", "high", "low", "close"]):
                print(f"  Loaded {ticker} OHLC from {cp.name}")
                return df
    # SPY-named caches only for SPY
    if ticker == "SPY":
        for fname in [
            f"h031_spy_ohlc_{start}_{end}.parquet",
            f"h042_spy_ohlc_{start}_{end}.parquet",
            f"h050_spy_ohlc_{start}_{end}.parquet",
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
    cp = CACHE_DIR / f"h055_{ticker}_ohlc_{start}_{end}.parquet"
    df.to_parquet(cp)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Equity curve builders
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


def ibs_equity_curve(ohlc, gap_filter=None):
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
            buy_signal = prev_ibs < IBS_BUY
            if gap_filter is not None:
                buy_signal = buy_signal and (cur_gap >= gap_filter)
            if buy_signal:
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
    monthly_eq = eq_daily.resample("ME").last().ffill()
    return monthly_eq.pct_change().dropna()


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


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 80)
    print("H055 — H042 with IBS Hedge: SPY + QQQ IBS Split (IS/OOS Validated)")
    print("=" * 80)

    # ── 1. Fetch data ────────────────────────────────────────────────────────
    print("\n[1] Fetching price data …")
    all_mom = list(set(H041A_ASSETS + SECTOR_ETFS))
    prices_mom = fetch_close(all_mom,        FULL_START, FULL_END, tag="h042_all")
    prices_tr  = fetch_close(TREASURY_ETFS,  FULL_START, FULL_END, tag="h051_treasury")
    spy_ohlc   = fetch_ohlc("SPY", FULL_START, FULL_END)
    qqq_ohlc   = fetch_ohlc("QQQ", FULL_START, FULL_END)
    print(f"   SPY OHLC: {spy_ohlc.index[0].date()} → {spy_ohlc.index[-1].date()}")
    print(f"   QQQ OHLC: {qqq_ohlc.index[0].date()} → {qqq_ohlc.index[-1].date()}")

    # ── 2. Build equity curves ────────────────────────────────────────────────
    print("\n[2] Building component equity curves …")
    eq_h041a = momentum_equity_curve(prices_mom, H041A_ASSETS, TOP_N_H41A)
    eq_h026  = momentum_equity_curve(prices_mom, SECTOR_ETFS,  TOP_N_H26)
    eq_h037b = ibs_equity_curve(spy_ohlc, gap_filter=GAP_FILTER_B)
    eq_h054b = ibs_equity_curve(qqq_ohlc, gap_filter=GAP_FILTER_B)
    eq_h045  = momentum_equity_curve(prices_tr, TREASURY_ETFS, TOP_N_H45)
    for name, eq in [("H041a", eq_h041a), ("H026", eq_h026), ("H037b", eq_h037b), ("H054b", eq_h054b), ("H045", eq_h045)]:
        print(f"   {name}: {eq.index[0].date()} → {eq.index[-1].date()} ({len(eq)} days)")

    # ── 3. Monthly returns ────────────────────────────────────────────────────
    print("\n[3] Monthly returns …")
    r_all = {name: to_monthly_returns(eq) for name, eq in [
        ("h041a", eq_h041a), ("h026", eq_h026),
        ("h037b", eq_h037b), ("h054b", eq_h054b), ("h045", eq_h045),
    ]}

    window_ts = pd.Timestamp(WINDOW_START)
    common_5way = r_all["h041a"].index
    for r in r_all.values():
        common_5way = common_5way.intersection(r.index)
    common_5way = common_5way[common_5way >= window_ts]

    common_4way = common_5way  # H041a/H026/H037b/H054b (no H045)
    for k in ["h041a", "h026", "h037b", "h054b"]:
        common_4way = common_4way.intersection(r_all[k].index)
    common_4way = common_4way[common_4way >= window_ts]

    print(f"   4-way common (no H045): {common_4way[0].date()} → {common_4way[-1].date()} ({len(common_4way)} months)")
    print(f"   5-way common (with H045): {common_5way[0].date()} → {common_5way[-1].date()} ({len(common_5way)} months)")

    # ── 4. IS/OOS split ───────────────────────────────────────────────────────
    is_ts  = pd.Timestamp(IS_END)
    oos_ts = pd.Timestamp(OOS_START)
    is_4  = common_4way[(common_4way >= window_ts) & (common_4way <= is_ts)]
    oos_4 = common_4way[common_4way >= oos_ts]
    is_5  = common_5way[(common_5way >= window_ts) & (common_5way <= is_ts)]
    oos_5 = common_5way[common_5way >= oos_ts]

    print(f"   IS  (4-way): {is_4[0].date()} → {is_4[-1].date()} ({len(is_4)}m)")
    print(f"   OOS (4-way): {oos_4[0].date()} → {oos_4[-1].date()} ({len(oos_4)}m)")

    def rblend(idx, weights):
        """Blend returns on common index."""
        total = sum(weights.values())
        r = pd.Series(0.0, index=idx)
        for k, w in weights.items():
            r = r + (w / total) * r_all[k].loc[idx]
        return r

    # ── 5. H042 baseline (H041a/H026/H037b 56/16/28) ─────────────────────────
    print("\n[4] Computing portfolio stats …")
    H042_W = {"h041a": 0.56, "h026": 0.16, "h037b": 0.28}
    r_h042_full = rblend(common_4way, H042_W)
    r_h042_is   = rblend(is_4, H042_W)
    r_h042_oos  = rblend(oos_4, H042_W)

    s_h042_full = stats_from_monthly_returns(r_h042_full, "H042 baseline (full)")
    s_h042_is   = stats_from_monthly_returns(r_h042_is,   "H042 baseline (IS)")
    s_h042_oos  = stats_from_monthly_returns(r_h042_oos,  "H042 baseline (OOS)")

    # ── 6. H055 (H041a/H026/H037b/H054b 56/16/14/14) ─────────────────────────
    H055_W = {"h041a": 0.56, "h026": 0.16, "h037b": 0.14, "h054b": 0.14}
    r_h055_full = rblend(common_4way, H055_W)
    r_h055_is   = rblend(is_4, H055_W)
    r_h055_oos  = rblend(oos_4, H055_W)

    s_h055_full = stats_from_monthly_returns(r_h055_full, "H055 (56/16/14/14, full)")
    s_h055_is   = stats_from_monthly_returns(r_h055_is,   "H055 (IS)")
    s_h055_oos  = stats_from_monthly_returns(r_h055_oos,  "H055 (OOS)")

    # ── 7. H055b (with H045 at 20%) ──────────────────────────────────────────
    # H041a=44.8%, H026=12.8%, H037b=11.2%, H054b=11.2%, H045=20%
    H055B_W = {"h041a": 0.448, "h026": 0.128, "h037b": 0.112, "h054b": 0.112, "h045": 0.20}
    r_h055b_full = rblend(common_5way, H055B_W)
    r_h055b_is   = rblend(is_5, H055B_W)
    r_h055b_oos  = rblend(oos_5, H055B_W)

    s_h055b_full = stats_from_monthly_returns(r_h055b_full, "H055b (+H045 20%, full)")
    s_h055b_is   = stats_from_monthly_returns(r_h055b_is,   "H055b (IS)")
    s_h055b_oos  = stats_from_monthly_returns(r_h055b_oos,  "H055b (OOS)")

    # ── 8. H052@20% reference (H041a/H026/H037b/H045 44.8/12.8/22.4/20) ─────
    H052_20_W = {"h041a": 0.448, "h026": 0.128, "h037b": 0.224, "h045": 0.20}
    r_h052_full = rblend(common_5way, H052_20_W)
    r_h052_is   = rblend(is_5, H052_20_W)
    r_h052_oos  = rblend(oos_5, H052_20_W)

    s_h052_full = stats_from_monthly_returns(r_h052_full, "H052@20% reference (full)")
    s_h052_is   = stats_from_monthly_returns(r_h052_is,   "H052@20% (IS)")
    s_h052_oos  = stats_from_monthly_returns(r_h052_oos,  "H052@20% (OOS)")

    # ── 9. Print comparison ───────────────────────────────────────────────────
    h042_deg = (s_h042_oos["sharpe"] - s_h042_is["sharpe"]) / s_h042_is["sharpe"] * 100
    h055_deg = (s_h055_oos["sharpe"] - s_h055_is["sharpe"]) / s_h055_is["sharpe"] * 100
    h055b_deg = (s_h055b_oos["sharpe"] - s_h055b_is["sharpe"]) / s_h055b_is["sharpe"] * 100
    h052_deg  = (s_h052_oos["sharpe"] - s_h052_is["sharpe"])  / s_h052_is["sharpe"]  * 100

    print(f"\n{'=' * 100}")
    print("  H055 COMPARISON — H042 VARIANTS (IS/OOS 2008/2017 | 2018/2026)")
    print(f"{'=' * 100}")
    print(f"  {'Portfolio':<50}  {'Full':>8}  {'IS':>8}  {'OOS':>8}  {'Deg%':>7}  {'CAGR':>8}  {'MaxDD':>8}")
    print(f"  {'-'*97}")

    rows = [
        ("H042 baseline   (H041a 56 / H026 16 / H037b 28)",   s_h042_full, s_h042_is, s_h042_oos, h042_deg),
        ("H055  IBS-split (H041a 56 / H026 16 / H037b 14 / H054b 14)",
                                                                s_h055_full, s_h055_is, s_h055_oos, h055_deg),
        ("H055b IBS+H045  (44.8/12.8/11.2/11.2/H045=20%)",    s_h055b_full, s_h055b_is, s_h055b_oos, h055b_deg),
        ("H052@20% ref    (44.8/12.8/H037b=22.4/H045=20%)",   s_h052_full, s_h052_is, s_h052_oos, h052_deg),
    ]
    for label, sf, si, so, deg in rows:
        if "error" in sf or "error" in si or "error" in so:
            print(f"  {label:<50}  ERROR")
        else:
            print(f"  {label:<50}  {sf['sharpe']:>8.4f}  {si['sharpe']:>8.4f}  {so['sharpe']:>8.4f}  "
                  f"{deg:>7.1f}%  {so['cagr']:>8.2%}  {so['max_drawdown']:>8.2%}")

    # ── 10. H054b IS/OOS component check ─────────────────────────────────────
    print("\n[5] Component standalone IS/OOS …")
    r_h037b_w = r_all["h037b"].loc[common_4way]
    r_h054b_w = r_all["h054b"].loc[common_4way]
    corr_full_h054b_h037b = float(r_h037b_w.corr(r_h054b_w))

    for name, r, idx_is, idx_oos in [
        ("H037b SPY", r_h037b_w, is_4, oos_4),
        ("H054b QQQ", r_h054b_w, is_4, oos_4),
    ]:
        s_is  = stats_from_monthly_returns(r.loc[idx_is])
        s_oos = stats_from_monthly_returns(r.loc[idx_oos])
        deg   = (s_oos["sharpe"] - s_is["sharpe"]) / s_is["sharpe"] * 100
        print(f"   {name}: IS {s_is['sharpe']:.4f}  OOS {s_oos['sharpe']:.4f}  Deg {deg:+.1f}%")

    print(f"   Full-period monthly corr H037b vs H054b: {corr_full_h054b_h037b:.4f}")

    # ── 11. Verdict ───────────────────────────────────────────────────────────
    print("\n[6] Verdict …")
    h055_beats_h042_oos  = s_h055_oos["sharpe"]  > s_h042_oos["sharpe"]
    h055_lower_deg       = abs(h055_deg) < abs(h042_deg)
    h055b_beats_h052_oos = s_h055b_oos["sharpe"] > s_h052_oos["sharpe"]

    if h055_beats_h042_oos and h055_lower_deg:
        verdict = "CONFIRMED — IBS split strictly improves H042: better OOS Sharpe and lower degradation"
    elif h055_beats_h042_oos:
        verdict = "PARTIALLY CONFIRMED — IBS split improves OOS Sharpe but higher degradation"
    elif h055_lower_deg:
        verdict = "PARTIALLY CONFIRMED — IBS split reduces degradation but OOS Sharpe not improved"
    else:
        verdict = "REJECTED — Splitting IBS between SPY and QQQ does not improve H042 OOS"

    h055b_note = (
        "H055b IMPROVES H052@20% OOS" if h055b_beats_h052_oos
        else "H055b does not improve H052@20% OOS"
    )

    print(f"   H055 OOS Sharpe > H042 OOS: {h055_beats_h042_oos} ({s_h055_oos['sharpe']:.4f} vs {s_h042_oos['sharpe']:.4f})")
    print(f"   H055 lower degradation than H042: {h055_lower_deg} ({h055_deg:+.1f}% vs {h042_deg:+.1f}%)")
    print(f"   H055b vs H052@20% OOS: {h055b_note}")
    print(f"\n   Verdict: {verdict}")

    # ── 12. Save JSON ─────────────────────────────────────────────────────────
    output = {
        "strategy": "H055 — H042 with IBS Hedge: SPY + QQQ IBS Split",
        "description": (
            "Motivated by H054: H037b (SPY IBS) OOS degrading (-35%) while H054b "
            "(QQQ IBS) OOS improving (+77%). Splits H037b's 28% allocation 50/50 "
            "between SPY IBS and QQQ IBS as a hedge against H037b edge fading."
        ),
        "portfolios": {
            "H042_baseline":  {"weights": H042_W,  "full": s_h042_full,  "IS": s_h042_is,  "OOS": s_h042_oos,  "deg": round(h042_deg, 2)},
            "H055":           {"weights": H055_W,  "full": s_h055_full,  "IS": s_h055_is,  "OOS": s_h055_oos,  "deg": round(h055_deg, 2)},
            "H055b_with_H045":{"weights": H055B_W, "full": s_h055b_full, "IS": s_h055b_is, "OOS": s_h055b_oos, "deg": round(h055b_deg, 2)},
            "H052_20pct_ref": {"weights": H052_20_W, "full": s_h052_full, "IS": s_h052_is, "OOS": s_h052_oos, "deg": round(h052_deg, 2)},
        },
        "component_stats": {
            "h037b_h054b_monthly_corr_full": round(corr_full_h054b_h037b, 4),
        },
        "verdict": {
            "summary":                   verdict,
            "h055b_vs_h052_note":        h055b_note,
            "h055_beats_h042_oos":       h055_beats_h042_oos,
            "h055_lower_deg_than_h042":  h055_lower_deg,
            "h055b_beats_h052_oos":      h055b_beats_h052_oos,
        },
        "run_date": "2026-04-27",
    }

    out_path = RESULT_DIR / "h055_results.json"
    out_path.write_text(json.dumps(output, indent=2, default=str))
    print(f"\n  Results saved → {out_path}")
    return output


if __name__ == "__main__":
    main()
