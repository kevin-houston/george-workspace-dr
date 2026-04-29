"""
H119 — Momentum Ensemble (Multi-Lookback Signal)
=================================================

H116 uses 12-month price momentum as the ranking signal.
H119 hypothesis: blending multiple lookback windows (3m, 6m, 12m) produces
a more robust signal — less prone to momentum crashes and more adaptive
to trend changes.

Reference: Novy-Marx (2012) "Is momentum really momentum?" shows 6-12m
intermediate momentum dominates short-term (1m) and long-term (>12m).
AQR research confirms ensemble lookbacks reduce crash risk.

Variants tested (all applied to H026 with TSMOM filter, H041a, H045):
  A) 12m only (H116 baseline)
  B) 6m only
  C) (6m + 12m) / 2 blend
  D) (3m + 6m + 12m) / 3 blend
  E) Rank ensemble: avg of rank(6m) + rank(12m) (rank before blending)
  F) Rank ensemble: avg of rank(3m) + rank(6m) + rank(12m)

H116 baseline: OOS 6.5635, AltOOS 14.9411, MaxDD -3.6%, NegYrs 0
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

_PREFIXES = [f"h{i:03d}" for i in range(62, 120)]


# ── Data helpers ──────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h119_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h119_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Rotation builder with configurable momentum signal ───────────────────────

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter=False, mom_mode="12m"):
    """
    mom_mode: one of "12m", "6m", "3m", "6m+12m", "3m+6m+12m",
              "rank_6m+12m", "rank_3m+6m+12m"
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

    # Minimum lookback required before we can score
    min_lb = 12  # always require 12m for TSMOM filter even if signal is shorter

    rows = []
    for i in range(min_lb, len(monthly_px)):
        vol_row  = vol_6.iloc[i].dropna()
        m12_row  = mom_12.iloc[i].dropna()
        m6_row   = mom_6.iloc[i].dropna()
        m3_row   = mom_3.iloc[i].dropna()
        valid    = m12_row.index.intersection(vol_row.index)

        if tsmom_filter:
            valid = pd.Index([t for t in valid if m12_row[t] > 0])
            if len(valid) == 0:
                rows.append((monthly_px.index[i], 0.0))
                continue

        if len(valid) < n_hold:
            rows.append((monthly_px.index[i],
                         monthly_ret.iloc[i][list(valid)].mean() if len(valid) > 0 else 0.0))
            continue

        # Build momentum score based on mode
        if mom_mode == "12m":
            mom_score = m12_row[valid]
        elif mom_mode == "6m":
            v2 = valid.intersection(m6_row.dropna().index)
            valid = v2 if len(v2) >= n_hold else valid
            mom_score = m6_row[valid] if mom_mode == "6m" else m12_row[valid]
        elif mom_mode == "3m":
            v2 = valid.intersection(m3_row.dropna().index)
            valid = v2 if len(v2) >= n_hold else valid
            mom_score = m3_row[valid]
        elif mom_mode == "6m+12m":
            v2 = valid.intersection(m6_row.dropna().index)
            if len(v2) >= n_hold:
                valid = v2
                mom_score = 0.5 * m6_row[valid] + 0.5 * m12_row[valid]
            else:
                mom_score = m12_row[valid]
        elif mom_mode == "3m+6m+12m":
            v2 = valid.intersection(m6_row.dropna().index).intersection(m3_row.dropna().index)
            if len(v2) >= n_hold:
                valid = v2
                mom_score = (m3_row[valid] + m6_row[valid] + m12_row[valid]) / 3.0
            else:
                mom_score = m12_row[valid]
        elif mom_mode == "rank_6m+12m":
            v2 = valid.intersection(m6_row.dropna().index)
            if len(v2) >= n_hold:
                valid = v2
                mom_score = m12_row[valid].rank() + m6_row[valid].rank()
            else:
                mom_score = m12_row[valid].rank()
        elif mom_mode == "rank_3m+6m+12m":
            v2 = valid.intersection(m6_row.dropna().index).intersection(m3_row.dropna().index)
            if len(v2) >= n_hold:
                valid = v2
                mom_score = m12_row[valid].rank() + m6_row[valid].rank() + m3_row[valid].rank()
            else:
                mom_score = m12_row[valid].rank()
        else:
            mom_score = m12_row[valid]

        # Composite: mom_score rank + inverse vol rank
        score = mom_score.rank() + vol_row[valid].rank(ascending=False)
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


def blend(sub_rets):
    df = pd.DataFrame(sub_rets).dropna(how="all")
    combined = pd.Series(0.0, index=df.index)
    for key, w in PROD_W.items():
        if key in df.columns:
            combined += df[key].reindex(combined.index).fillna(0) * w
    return combined.dropna()


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<45} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 75)
    print("H119 — Momentum Ensemble (Multi-Lookback Signal Blend)")
    print("=" * 75)

    print("\nPre-computing IBS components…")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    modes = [
        ("12m (H116 baseline)", "12m", False),
        ("6m only",             "6m",  False),
        ("(6m+12m)/2 blend",    "6m+12m", False),
        ("(3m+6m+12m)/3 blend", "3m+6m+12m", False),
        ("rank(6m)+rank(12m)",  "rank_6m+12m", False),
        ("rank(3m)+rank(6m)+rank(12m)", "rank_3m+6m+12m", False),
    ]

    print("\n" + "=" * 75)
    print("Results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 75 + "\n")

    results = {}
    baseline_oos = baseline_alt = None

    for label, mode, _ in modes:
        print(f"  Computing {label}…", flush=True)
        # Apply same mode to H041a and H026 (with TSMOM filter on H026)
        h041a = build_rotation(H041A_FULL,  FULL_START, FULL_END, n_hold=1,
                               tsmom_filter=False, mom_mode=mode)
        h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1,
                               tsmom_filter=True,  mom_mode=mode)
        h045  = build_rotation(H045_PROD,   FULL_START, FULL_END, n_hold=2,
                               tsmom_filter=False, mom_mode=mode)
        port  = blend({"h041a": h041a, "h026": h026, "h045": h045, **ibs_rets})
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("12m"):
            baseline_oos, baseline_alt = oos_s, alt_s

    print("\n" + "─" * 75)
    best_label = max(
        (k for k in results if not k.startswith("12m")),
        key=lambda k: results[k][0]["cumul"] + results[k][1]["cumul"]
    )
    best_oos, best_alt = results[best_label]
    delta_oos = best_oos["cumul"] - baseline_oos["cumul"]
    delta_alt = best_alt["cumul"] - baseline_alt["cumul"]

    print(f"\n  Best variant: {best_label}")
    print(f"    OOS Cumul:  {best_oos['cumul']:.4f}  (baseline {baseline_oos['cumul']:.4f},  Δ{delta_oos:+.4f})")
    print(f"    AltOOS:     {best_alt['cumul']:.4f}  (baseline {baseline_alt['cumul']:.4f},  Δ{delta_alt:+.4f})")
    print(f"    OOS Sharpe: {best_oos['sharpe']:.3f}  MaxDD: {best_oos['max_drawdown']*100:.1f}%  "
          f"NegYrs: {best_oos['neg_years']}")

    both_better = delta_oos > 0 and delta_alt > 0
    print(f"\n  Verdict: {'✅ CONFIRMED — both OOS windows improve' if both_better else '❌ NOT CONFIRMED — does not pass dual-window test'}")


if __name__ == "__main__":
    main()
