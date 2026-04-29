"""
H124 — 1-Month Reversal in Rank Ensemble Signal
=================================================

H122 production signal: rank(3m) + rank(6m) + rank(12m) + rank(inv_vol)

Academic literature (Jegadeesh 1990, Fama/French) documents that 1-month
returns exhibit REVERSAL (negative autocorrelation), while 2-12 month returns
show momentum. The 3m lookback partially captures this — but 1m is different.

H124 tests: adding a 1-month reversal penalty to the score.
  score = rank(12m) + rank(6m) + rank(3m) + rank(inv_vol) - W * rank(1m)

Where W = the weight on the reversal term. W=0 is baseline (H122).

Variants:
  A) H122 baseline (W=0)
  B) W=0.25 — light reversal
  C) W=0.50 — moderate reversal (symmetric with one momentum term)
  D) W=1.00 — full reversal (equal weight to any momentum term)
  E) W=2.00 — strong reversal
  F) Skip 3m entirely: rank(12m) + rank(6m) + rank(inv_vol) - W=1 * rank(1m)
     (tests whether 3m is actually already capturing reversal)

H122 reference: OOS 27.8836, AltOOS 103.5302 (vol-targeted H026)
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

FULL_START = "2003-01-01"
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

_PREFIXES = [f"h{i:03d}" for i in range(62, 125)]


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h124_{ticker}_ohlc_{start}_{end}.parquet"
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
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h124_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Rank ensemble rotation with configurable reversal weight ─────────────────

def build_rotation(tickers, start, end, n_hold=1,
                   tsmom_filter: bool = False,
                   reversal_weight: float = 0.0,
                   skip_3m: bool = False):
    """
    Rank ensemble signal with optional 1-month reversal penalty.

    score = rank(12m) + rank(6m) + rank(3m) + rank(inv_vol)
            - reversal_weight * rank(1m)

    If skip_3m=True: rank(12m) + rank(6m) + rank(inv_vol) - reversal_weight * rank(1m)

    tsmom_filter: if True, apply 12m TSMOM filter (H122 standard).
    """
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
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    mom_1  = monthly_px / monthly_px.shift(1)  - 1

    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        m1_row  = mom_1.iloc[i].dropna()

        valid = (m12_row.index
                 .intersection(vol_row.index)
                 .intersection(m6_row.dropna().index)
                 .intersection(m1_row.dropna().index))
        if not skip_3m:
            valid = valid.intersection(m3_row.dropna().index)

        # 12m TSMOM filter (H026 standard — only when tsmom_filter=True)
        if tsmom_filter:
            valid = pd.Index([t for t in valid if m12_row.get(t, 0) > 0])

        if len(valid) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue

        if len(valid) < n_hold:
            rows.append((monthly_px.index[i],
                         monthly_ret.iloc[i][list(valid)].mean()))
            continue

        # Build score
        score = (m12_row[valid].rank() + m6_row[valid].rank() +
                 vol_row[valid].rank(ascending=False))
        if not skip_3m:
            score = score + m3_row[valid].rank()

        # Reversal penalty: subtract rank(1m) * weight
        if reversal_weight > 0:
            score = score - reversal_weight * m1_row[valid].rank()

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
    """
    Blend sub-strategy returns with H026 vol-targeting (H122 production config).
    Matches H121 variant D implementation exactly.
    Rotation keys (h041a + h026 + h045) renorm to ROTATION_WEIGHT each month.
    """
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
                    # Renorm rotation to ROTATION_WEIGHT
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
    print(f"  {label:<55} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H124 — 1-Month Reversal in Rank Ensemble Signal")
    print("=" * 80)
    print("Testing reversal penalty W on 1m return vs H122 baseline (vol-targeted).")
    print("H122 baseline: OOS 27.8836, AltOOS 103.5302")

    print("\nPre-computing IBS components…")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    print("\nPre-computing H045 (no TSMOM, no reversal)…")
    h045 = build_rotation(H045_PROD, FULL_START, FULL_END, n_hold=2,
                          tsmom_filter=False, reversal_weight=0.0)

    variants = [
        # label, h041a_reversal_w, h026_reversal_w, skip_3m
        ("A) H122 baseline (W=0)",                 0.0,  0.0,  False),
        ("B) W=0.25 reversal on both",             0.25, 0.25, False),
        ("C) W=0.50 reversal on both",             0.50, 0.50, False),
        ("D) W=1.00 reversal on both",             1.00, 1.00, False),
        ("E) W=2.00 reversal on both",             2.00, 2.00, False),
        ("F) Skip 3m + W=1.00 reversal on both",   1.00, 1.00, True),
        ("G) W=0.50 on H026 only (H041a baseline)", 0.0, 0.50, False),
        ("H) W=1.00 on H026 only",                 0.0,  1.00, False),
    ]

    print("\n" + "=" * 80)
    print("Results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 80 + "\n")

    results = {}
    b_oos = b_alt = None

    for label, h041a_w, h026_w, skip_3m in variants:
        print(f"  Computing {label}…", flush=True)

        h041a = build_rotation(H041A_FULL, FULL_START, FULL_END,
                               n_hold=1, tsmom_filter=False,
                               reversal_weight=h041a_w, skip_3m=skip_3m)
        h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END,
                               n_hold=1, tsmom_filter=True,   # 12m TSMOM always on H026
                               reversal_weight=h026_w, skip_3m=skip_3m)

        sub_rets = {"h041a": h041a, "h026": h026, "h045": h045, **ibs_rets}
        port = blend_vol_targeted(sub_rets)
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("A)"):
            b_oos, b_alt = oos_s, alt_s

    print("\n" + "─" * 80)
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
