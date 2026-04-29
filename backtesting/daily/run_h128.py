"""
H128 — TSMOM Filter on H045 Within Full H122 Blend
====================================================

H127 confirmed TSMOM filter on standalone H045 (7-ETF universe):
  Best D (3m>0): OOS +44.92% → +78.60% (+33.68pp), Sharpe 1.351 → 2.370

H128 tests the same filter within the full H122 production blend:
  H041a (22%) + H026 (27%, 12m TSMOM) + H045 (21%) + IBS XLK/SMH/IGV (30%)

Production H045 universe is 13 ETFs:
  SHY, IEI, IEF, TLT, TIP, HYG, LQD, BKLN, EMB, BIL, MBB, FLOT, PCY

TSMOM filter: only hold H045 ETFs where N-month return > 0.
  If <1 passes → cash (0 return for H045 that month).
  If only 1 passes → hold 1 at 100%.
  Hold top-2 from passing candidates.

Variants (H045 filter only; H026 keeps its 12m filter throughout):
  A) Baseline: no H045 filter (H122 production)
  B) 3m > 0 filter   ← best in H127 standalone
  C) 6m > 0 filter
  D) 12m + 6m > 0    ← best Sharpe in H127 standalone
  E) 12m > 0 filter

Reference H122: OOS cumul 27.8836, AltOOS 103.5302
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

_PREFIXES = [f"h{i:03d}" for i in range(62, 129)]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers (reused from H124 pattern)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h128_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h128_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ─────────────────────────────────────────────────────────────────────────────
# Strategy builders
# ─────────────────────────────────────────────────────────────────────────────

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter: bool = False):
    """Standard H120 rank ensemble: rank(12m)+rank(6m)+rank(3m)+rank(inv_vol)."""
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_3  = monthly_px / monthly_px.shift(3)  - 1

    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid = (m12_row.index.intersection(vol_row.index)
                 .intersection(m6_row.index).intersection(m3_row.index))
        if tsmom_filter:
            valid = pd.Index([t for t in valid if m12_row.get(t, 0) > 0])
        if len(valid) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue
        if len(valid) < n_hold:
            rows.append((monthly_px.index[i], monthly_rt.iloc[i][list(valid)].mean()))
            continue
        score = (m12_row[valid].rank() + m6_row[valid].rank() +
                 m3_row[valid].rank() + vol_row[valid].rank(ascending=False))
        top   = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def build_h045_tsmom(tickers, start, end, n_hold=2, tsmom_lookbacks: list[int] = None):
    """
    H045 rotation with TSMOM filter.
    Signal: rank(12m_mom) + rank(inv_6m_vol), hold top-N from passing assets.
    tsmom_lookbacks: list of lookback months; ALL must be positive.
      Empty list = no filter (baseline).
    """
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    lookbacks = tsmom_lookbacks or []
    max_lb = max(lookbacks + [12])
    mom_by_lb = {lb: monthly_px / monthly_px.shift(lb) - 1 for lb in set(lookbacks)}

    rows = []
    for i in range(max_lb, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        valid   = m12_row.index.intersection(vol_row.index)

        # TSMOM filter
        passing = list(valid)
        for lb in lookbacks:
            lb_row = mom_by_lb[lb].iloc[i]
            passing = [t for t in passing
                       if t in lb_row.index
                       and not np.isnan(float(lb_row[t]))
                       and float(lb_row[t]) > 0]

        if len(passing) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue

        n = min(n_hold, len(passing))
        score = m12_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False)
        top   = list(score.nlargest(n).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom  = (df["high"] - df["low"]).replace(0, np.nan)
    ibs    = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"] - prev_cl) / prev_cl
    equity = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i]);  c  = float(df["close"].iloc[i])
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


# ─────────────────────────────────────────────────────────────────────────────
# Blend (H122 production: vol-targeted H026, 3-rotation renorm)
# ─────────────────────────────────────────────────────────────────────────────

def blend_vol_targeted(sub_rets):
    df = pd.DataFrame(sub_rets).dropna(how="all")
    rot_keys = ["h041a", "h026", "h045"]
    combined = pd.Series(0.0, index=df.index)
    for i in range(len(df)):
        row_weights = dict(PROD_W)
        if "h026" in df.columns and i >= VOL_WINDOW_H026:
            window = df["h026"].iloc[i - VOL_WINDOW_H026:i]
            if len(window) >= 3:
                rv = float(window.std(ddof=1)) * np.sqrt(12)
                if rv > 0:
                    scalar = float(np.clip(VOL_TARGET_H026 / rv, *VOL_CLAMP_H026))
                    row_weights["h026"] = PROD_W["h026"] * scalar
                    cur_rot = sum(row_weights.get(k, 0.0) for k in rot_keys if k in df.columns)
                    if cur_rot > 0:
                        for k in rot_keys:
                            if k in df.columns:
                                row_weights[k] = row_weights[k] * ROTATION_WEIGHT / cur_rot
        combined.iloc[i] = sum(
            float(df[key].iloc[i]) * row_weights.get(key, 0.0)
            for key in df.columns
            if not np.isnan(float(df[key].iloc[i]))
        )
    return combined.dropna()


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
    return {"cagr": round(cagr,4), "sharpe": round(sharpe,4),
            "max_drawdown": round(max_dd,4), "n_months": len(r),
            "neg_years": neg_yrs, "cumul": round(float(eq.iloc[-1]),4)}


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<50} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H128 — TSMOM Filter on H045 in Full H122 Blend")
    print("=" * 80)
    print("H122 baseline reference: OOS 27.8836, AltOOS 103.5302")
    print("H127 standalone H045 best (D, 3m): OOS +33.68pp, Sharpe 1.351→2.370\n")

    # ── IBS (shared across all variants) ────────────────────────────────────
    print("Pre-computing IBS components …")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    # ── H041a, H026 (shared) ─────────────────────────────────────────────────
    print("\nPre-computing H041a and H026 …")
    h041a = build_rotation(H041A_FULL,  FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h026  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)
    print("  H041a, H026 done")

    # ── H045 variants ────────────────────────────────────────────────────────
    VARIANTS = [
        ("A) Baseline: no filter (H122)",    []),
        ("B) 3m > 0 filter",                 [3]),
        ("C) 6m > 0 filter",                 [6]),
        ("D) 12m + 6m > 0 dual filter",      [12, 6]),
        ("E) 12m > 0 filter",                [12]),
    ]

    print("\nBuilding H045 variants …")
    h045_rets = {}
    for label, lookbacks in VARIANTS:
        tag = label[:3]
        print(f"  {label} …", end=" ", flush=True)
        h045_rets[tag] = build_h045_tsmom(H045_PROD, FULL_START, FULL_END,
                                           n_hold=2, tsmom_lookbacks=lookbacks)
        print("done")

    # ── Full blend + results ─────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("Results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 80)

    results = {}
    b_oos = b_alt = None

    for label, lookbacks in VARIANTS:
        tag = label[:3]
        sub_rets = {"h041a": h041a, "h026": h026, "h045": h045_rets[tag], **ibs_rets}
        port = blend_vol_targeted(sub_rets)
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("A)"):
            b_oos, b_alt = oos_s, alt_s

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "─" * 80)
    candidates = {k: v for k, v in results.items() if not k.startswith("A)")}
    best_label = max(candidates, key=lambda k: candidates[k][0]["cumul"] + candidates[k][1]["cumul"])
    best_oos, best_alt = candidates[best_label]
    d_oos = best_oos["cumul"] - b_oos["cumul"]
    d_alt = best_alt["cumul"] - b_alt["cumul"]

    print(f"\n  Best variant: {best_label}")
    print(f"    OOS Cumul:  {best_oos['cumul']:.4f}  (baseline {b_oos['cumul']:.4f},  Δ{d_oos:+.4f})")
    print(f"    AltOOS:     {best_alt['cumul']:.4f}  (baseline {b_alt['cumul']:.4f},  Δ{d_alt:+.4f})")
    print(f"    OOS Sharpe: {best_oos['sharpe']:.3f}  MaxDD: {best_oos['max_drawdown']*100:.1f}%  "
          f"NegYrs: {best_oos['neg_years']}")

    both_better = all(
        results[k][0]["cumul"] > b_oos["cumul"] and results[k][1]["cumul"] > b_alt["cumul"]
        for k in candidates
    )
    any_better = any(
        results[k][0]["cumul"] > b_oos["cumul"] and results[k][1]["cumul"] > b_alt["cumul"]
        for k in candidates
    )

    verdict = ("CONFIRMED" if any_better else "NOT CONFIRMED")
    print(f"\n  Verdict: {verdict}")
    if any_better:
        confirmed = [k for k in candidates
                     if results[k][0]["cumul"] > b_oos["cumul"]
                     and results[k][1]["cumul"] > b_alt["cumul"]]
        print(f"  Confirmed variants: {confirmed}")

    return results


if __name__ == "__main__":
    main()
