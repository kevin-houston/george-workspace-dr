"""
H125 — Extended Momentum Lookbacks in Rank Ensemble
=====================================================

H122 production signal: rank(3m) + rank(6m) + rank(12m) + rank(inv_vol)

H119 confirmed that adding 6m and 3m to the original 12m signal drove +28% OOS.
The question is whether LONGER lookbacks (18m, 24m) also add signal.

Novy-Marx (2012) "Is Momentum Really Momentum?" shows 12-24m horizon is
empirically strongest for equities. For ETF rotation, untested.

H125 variants:
  A) H122 baseline: rank(3m)+rank(6m)+rank(12m)+rank(inv_vol)
  B) +rank(24m): 5-term ensemble with very-long-term momentum
  C) +rank(18m): 5-term ensemble with long-term extension
  D) +rank(18m)+rank(24m): 6-term full spectrum
  E) Replace 3m with 24m: rank(24m)+rank(6m)+rank(12m)+rank(inv_vol)
     (tests whether 24m strictly dominates short-term)
  F) rank(6m)+rank(12m)+rank(24m)+rank(inv_vol)
     (drop 3m, add 24m — symmetric 3-period coverage)
  G) rank(12m)+rank(24m)+rank(inv_vol) — minimal long-only
  H) rank(3m)+rank(6m)+rank(12m)+rank(18m)+rank(24m)+rank(inv_vol)
     (full 6-term ensemble)

H122 reference: OOS 27.8836, AltOOS 103.5302
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2001-01-01"   # extra history for 24m lookback
FULL_END   = "2026-04-27"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

H041A_FULL  = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]
H045_PROD   = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

IBS_CFGS = {
    "XLK": (0.15, 0.90, 7, -0.010),
    "SMH": (0.20, 0.75, 6, -0.005),
    "IGV": (0.30, 0.75, 5,  0.0025),
}
PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
          "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

VOL_TARGET_H026 = 0.15
VOL_WINDOW_H026 = 6
VOL_CLAMP_H026  = (0.5, 2.0)
ROTATION_WEIGHT = 0.22 + 0.27 + 0.21  # 0.70

_PREFIXES = [f"h{i:03d}" for i in range(62, 126)]


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    # Also check FULL_START variant of cache
    cp2 = CACHE_DIR / f"h124_{ticker}_ohlc_2003-01-01_{end}.parquet"
    if cp2.exists():
        df = pd.read_parquet(cp2)
        df.columns = [c.lower() for c in df.columns]
        if all(c in df.columns for c in ["open","high","low","close"]):
            return df.loc[start:]
    cp = CACHE_DIR / f"h125_{ticker}_ohlc_{start}_{end}.parquet"
    print(f"  Downloading {ticker} OHLC …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(cp)
    return df


def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                s = df[col].rename(ticker)
                if str(s.index[0].date()) <= start:
                    return s
                return s
    # Also check prior caches with different start dates
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            for alt_start in ["2003-01-01", "2001-01-01"]:
                p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{alt_start}_{end}.parquet"
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    col = "close" if "close" in df.columns else df.columns[0]
                    return df[col].rename(ticker)
    cp = CACHE_DIR / f"h125_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Rank ensemble with configurable lookbacks ─────────────────────────────────

def build_rotation(tickers, start, end, n_hold=1,
                   tsmom_filter: bool = False,
                   lookbacks: list[int] = None):
    """
    Rank ensemble with configurable momentum lookbacks.
    lookbacks: list of lookback months for momentum ranks.
               E.g. [3, 6, 12] = H122 baseline.
               E.g. [3, 6, 12, 24] = H125-B.
    Always includes rank(inv_vol_6m).
    tsmom_filter: if True, apply 12m TSMOM filter (H026 standard).
    """
    if lookbacks is None:
        lookbacks = [3, 6, 12]

    max_lb = max(lookbacks)
    warmup = max(max_lb + 1, 13)  # need max_lb + 1 months of data

    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    vol_6 = monthly_ret.rolling(6).std() * np.sqrt(12)

    # Precompute momentum for each lookback
    moms = {}
    for lb in set(lookbacks):
        moms[lb] = monthly_px / monthly_px.shift(lb) - 1

    rows = []
    for i in range(warmup, len(monthly_px)):
        vol_row  = vol_6.iloc[i].dropna()
        mom_rows = {lb: moms[lb].iloc[i].dropna() for lb in lookbacks}

        valid = vol_row.index
        for lb in lookbacks:
            valid = valid.intersection(mom_rows[lb].dropna().index)

        # 12m TSMOM filter
        if tsmom_filter:
            if 12 in moms:
                m12_row = moms[12].iloc[i].dropna()
            else:
                m12_row = (monthly_px / monthly_px.shift(12) - 1).iloc[i].dropna()
            valid = pd.Index([t for t in valid
                              if t in m12_row.index and m12_row[t] > 0])

        if len(valid) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue

        if len(valid) < n_hold:
            rows.append((monthly_px.index[i],
                         monthly_ret.iloc[i][list(valid)].mean()))
            continue

        score = vol_row[valid].rank(ascending=False)
        for lb in lookbacks:
            score = score + mom_rows[lb][valid].rank()

        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_ret.iloc[i][top_n].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom = (df["high"] - df["low"]).replace(0, np.nan)
    ibs = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"] - prev_cl) / prev_cl
    equity = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o - 1) if o > 0 else 0.0
        ret_cc = (c/cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1 + ret_oc)
        else:
            days_held += 1; equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0, "cumul": 1.0}
    eq   = (1 + r).cumprod()
    n_yr = len(r) / 12.0
    cagr = float(eq.iloc[-1]) ** (1/n_yr) - 1
    vol  = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r),
            "neg_years": neg_yrs, "cumul": round(float(eq.iloc[-1]), 4)}


def blend_vol_targeted(sub_rets):
    """H122 production blend with H026 vol-targeting. Matches H121 variant D."""
    df = pd.DataFrame(sub_rets).dropna(how="all")
    rot_keys = ["h041a", "h026", "h045"]
    combined = pd.Series(0.0, index=df.index)

    for i in range(len(df)):
        row_weights = dict(PROD_W)

        if "h026" in df.columns and i >= VOL_WINDOW_H026:
            window_rets = df["h026"].iloc[i - VOL_WINDOW_H026:i]
            if len(window_rets) >= 3:
                rv = float(window_rets.std(ddof=1)) * np.sqrt(12)
                if rv > 0:
                    scalar = float(np.clip(VOL_TARGET_H026 / rv, *VOL_CLAMP_H026))
                    row_weights["h026"] = PROD_W["h026"] * scalar
                    current_rot_sum = sum(row_weights.get(k, 0.0) for k in rot_keys
                                         if k in df.columns)
                    if current_rot_sum > 0:
                        for k in rot_keys:
                            if k in df.columns:
                                row_weights[k] = row_weights[k] * ROTATION_WEIGHT / current_rot_sum

        month_ret = sum(float(df[key].iloc[i]) * row_weights.get(key, 0.0)
                        for key in df.columns
                        if not np.isnan(float(df[key].iloc[i])))
        combined.iloc[i] = month_ret

    return combined.dropna()


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<58} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 82)
    print("H125 — Extended Momentum Lookbacks in Rank Ensemble")
    print("=" * 82)
    print("Testing 18m and 24m lookbacks vs H122 baseline (vol-targeted).")
    print("H122 baseline: OOS 27.8836, AltOOS 103.5302")

    print("\nPre-computing IBS components…")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    print("\nPre-computing H045 baseline (lookbacks=[3,6,12])…")
    h045_base = build_rotation(H045_PROD, FULL_START, FULL_END, n_hold=2,
                               tsmom_filter=False, lookbacks=[3, 6, 12])

    variants = [
        # label, h041a_lbs, h026_lbs, h045_lbs
        ("A) H122 baseline [3,6,12]",                    [3,6,12],       [3,6,12],       None),
        ("B) +24m all: [3,6,12,24]",                     [3,6,12,24],    [3,6,12,24],    [3,6,12,24]),
        ("C) +18m all: [3,6,12,18]",                     [3,6,12,18],    [3,6,12,18],    [3,6,12,18]),
        ("D) +18m+24m all: [3,6,12,18,24]",              [3,6,12,18,24], [3,6,12,18,24], [3,6,12,18,24]),
        ("E) Replace 3m→24m all: [6,12,24]",             [6,12,24],      [6,12,24],      [6,12,24]),
        ("F) Drop 3m, add 24m all: [6,12,24]",           [6,12,24],      [6,12,24],      [6,12,24]),
        ("G) [12,24] minimal long-term",                 [12,24],        [12,24],        [12,24]),
        ("H) Full 6-term [3,6,12,18,24,36]",             [3,6,12,18,24,36], [3,6,12,18,24,36], [3,6,12,18,24,36]),
    ]

    print("\n" + "=" * 82)
    print("Results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 82 + "\n")

    results = {}
    b_oos = b_alt = None

    for label, h041a_lbs, h026_lbs, h045_lbs in variants:
        print(f"  Computing {label}…", flush=True)
        h041a = build_rotation(H041A_FULL, FULL_START, FULL_END,
                               n_hold=1, tsmom_filter=False, lookbacks=h041a_lbs)
        h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END,
                               n_hold=1, tsmom_filter=True, lookbacks=h026_lbs)
        if h045_lbs is None:
            h045 = h045_base
        else:
            h045 = build_rotation(H045_PROD, FULL_START, FULL_END,
                                   n_hold=2, tsmom_filter=False, lookbacks=h045_lbs)

        sub_rets = {"h041a": h041a, "h026": h026, "h045": h045, **ibs_rets}
        port = blend_vol_targeted(sub_rets)
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("A)"):
            b_oos, b_alt = oos_s, alt_s

    print("\n" + "─" * 82)
    candidates = {k: v for k, v in results.items() if not k.startswith("A)")}
    best_label = max(candidates, key=lambda k: candidates[k][0]["cumul"] + candidates[k][1]["cumul"])
    best_oos, best_alt = candidates[best_label]
    delta_oos = best_oos["cumul"] - b_oos["cumul"]
    delta_alt = best_alt["cumul"] - b_alt["cumul"]

    print(f"\n  Best variant: {best_label}")
    print(f"    OOS Cumul:  {best_oos['cumul']:.4f}  (baseline {b_oos['cumul']:.4f},  Δ{delta_oos:+.4f})")
    print(f"    AltOOS:     {best_alt['cumul']:.4f}  (baseline {b_alt['cumul']:.4f},  Δ{delta_alt:+.4f})")
    print(f"    OOS Sharpe: {best_oos['sharpe']:.3f}  MaxDD: {best_oos['max_drawdown']*100:.1f}%  "
          f"NegYrs: {best_oos['neg_years']}")

    both_better = delta_oos > 0 and delta_alt > 0
    print(f"\n  Verdict: {'✅ CONFIRMED — both OOS windows improve' if both_better else '❌ NOT CONFIRMED — does not pass dual-window test'}")
    if not both_better:
        print(f"  Note: OOS Δ={delta_oos:+.4f}  AltOOS Δ={delta_alt:+.4f}  "
              f"(both must be positive to confirm)")


if __name__ == "__main__":
    main()
