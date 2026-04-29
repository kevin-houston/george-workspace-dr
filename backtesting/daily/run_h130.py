"""
H130 — 3m TSMOM Filter on H041a Global Equity Rotation
========================================================

H128 confirmed 3m TSMOM on H045 bond ETFs (+0.47 OOS cumul in blend).
H130 tests the same approach on H041a (19 global equity ETFs).

H123 showed 12m TSMOM on H041a HURTS (−0.30 OOS, −0.01 AltOOS).
H127 showed 3m TSMOM on H045 HELPS massively (bonds vs equities differ).

Question: does 3m TSMOM help H041a (equity) or does it whipsaw?

Economic reasoning for equity ETFs:
  - Equity downturns (2022 bear, 2020 COVID): all ETFs go negative 3m simultaneously
  - 3m filter would exit to cash early in a downturn
  - BUT equities recover faster than rates — 3m whipsaws are more likely
  - V-shaped recoveries (2020 COVID) would cause missed re-entry

Variants:
  A) H041a baseline (no filter) — H122/H128 production
  B) 3m > 0 filter on H041a    — most responsive
  C) 6m > 0 filter on H041a    — intermediate
  D) 12m + 3m > 0 dual         — strict quality gate

Reference: H128 production OOS 21.6336, AltOOS 71.5302
All variants test within full H122/H128 blend (H026 12m filter, H045 3m filter unchanged).
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
ROTATION_WEIGHT = 0.70

_PREFIXES = [f"h{i:03d}" for i in range(62, 131)]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h130_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h130_{ticker}_close_{start}_{end}.parquet"
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

def build_rotation_tsmom(tickers, start, end, n_hold=1,
                         tsmom_lookbacks: list[int] = None):
    """
    H120 rank ensemble (3m+6m+12m+inv_vol) with configurable TSMOM filter.
    Only hold ETFs where ALL lookbacks > 0. Empty list = no filter.
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
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_3  = monthly_px / monthly_px.shift(3)  - 1

    lookbacks = tsmom_lookbacks or []
    max_lb = max(lookbacks + [12])
    mom_by_lb = {lb: monthly_px / monthly_px.shift(lb) - 1 for lb in set(lookbacks)}

    rows = []
    for i in range(max_lb, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid = (m12_row.index.intersection(vol_row.index)
                 .intersection(m6_row.index).intersection(m3_row.index))

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
        if len(passing) < n_hold:
            rows.append((monthly_px.index[i], monthly_rt.iloc[i][passing].mean()))
            continue

        score = (m12_row.reindex(passing).rank() + m6_row.reindex(passing).rank() +
                 m3_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False))
        top   = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


def build_h045_3m_tsmom(tickers, start, end, n_hold=2):
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
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid   = m12_row.index.intersection(vol_row.index).intersection(m3_row.index)
        passing = [t for t in valid if float(m3_row.get(t, 0)) > 0]
        if len(passing) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue
        n = min(n_hold, len(passing))
        score = m12_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False)
        top   = list(score.nlargest(n).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))
    return pd.Series([v for _, v in rows], index=pd.DatetimeIndex([d for d, _ in rows]))


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
    return pd.Series([v for _, v in series], index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


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
    print(f"  {label:<52} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H130 — 3m TSMOM Filter on H041a Global Equity Rotation")
    print("=" * 80)
    print("H128 reference: OOS 21.6336, AltOOS 71.5302, Sharpe 4.553\n")

    print("Pre-computing IBS …")
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  {sym} done")

    print("\nPre-computing H026 (12m filter) and H045 (3m filter) …")
    h026 = build_rotation_tsmom(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_lookbacks=[12])
    h045 = build_h045_3m_tsmom(H045_PROD, FULL_START, FULL_END, n_hold=2)
    print("  done")

    VARIANTS = [
        ("A) Baseline: no H041a filter",      []),
        ("B) 3m > 0 filter on H041a",         [3]),
        ("C) 6m > 0 filter on H041a",         [6]),
        ("D) 12m + 3m > 0 dual on H041a",     [12, 3]),
    ]

    print("\nBuilding H041a variants …")
    h041a_series = {}
    for label, lookbacks in VARIANTS:
        tag = label[:2]
        print(f"  {label} …", end=" ", flush=True)
        h041a_series[tag] = build_rotation_tsmom(H041A_FULL, FULL_START, FULL_END,
                                                   n_hold=1, tsmom_lookbacks=lookbacks)
        n_cash = sum(1 for v in h041a_series[tag].values if v == 0.0)
        print(f"done  (cash months: {n_cash})")

    print("\n" + "=" * 80)
    print("Results")
    print("=" * 80)

    results = {}
    b_oos = b_alt = None

    for label, lookbacks in VARIANTS:
        tag = label[:2]
        sub_rets = {"h041a": h041a_series[tag], "h026": h026, "h045": h045, **ibs_rets}
        port = blend_vol_targeted(sub_rets)
        oos_s, alt_s = print_stats(port, label)
        results[label] = (oos_s, alt_s)
        if label.startswith("A)"):
            b_oos, b_alt = oos_s, alt_s

    print("\n" + "─" * 80)
    candidates = {k: v for k, v in results.items() if not k.startswith("A)")}
    best_label = max(candidates, key=lambda k: candidates[k][0]["cumul"] + candidates[k][1]["cumul"])
    best_oos, best_alt = candidates[best_label]
    d_oos = best_oos["cumul"] - b_oos["cumul"]
    d_alt = best_alt["cumul"] - b_alt["cumul"]

    print(f"\n  Best: {best_label}")
    print(f"    OOS:  {best_oos['cumul']:.4f} (baseline {b_oos['cumul']:.4f}, Δ{d_oos:+.4f})")
    print(f"    Alt:  {best_alt['cumul']:.4f} (baseline {b_alt['cumul']:.4f}, Δ{d_alt:+.4f})")
    print(f"    Sharpe: {best_oos['sharpe']:.3f}  MaxDD: {best_oos['max_drawdown']*100:.1f}%")

    any_better = any(
        results[k][0]["cumul"] > b_oos["cumul"] and results[k][1]["cumul"] > b_alt["cumul"]
        for k in candidates
    )
    print(f"\n  Verdict: {'CONFIRMED' if any_better else 'NOT CONFIRMED'}")
    if any_better:
        confirmed = [k for k in candidates
                     if results[k][0]["cumul"] > b_oos["cumul"]
                     and results[k][1]["cumul"] > b_alt["cumul"]]
        print(f"  Confirmed variants: {confirmed}")

    return results


if __name__ == "__main__":
    main()
