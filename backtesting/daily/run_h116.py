"""
H116 — TSMOM Filter Production Upgrade
=======================================

H115 confirmed TSMOM filter on H026 adds +0.84 OOS and +2.12 AltOOS to H112.
H041a filter improved OOS Cumul (8.0794→8.3509) but lowered Sharpe (2.868→2.611).

This script exhaustively tests all filter combinations to find the best
production upgrade:
  A) H026 filter only          (H115 confirmed)
  B) H041a filter only         (H115 missed — Sharpe drop)
  C) H026 + H041a both         (new)
  D) H045 filter               (new — fixed income rotation)
  E) All three sub-strats      (new)

Best combination → new production baseline H116.

H112 baseline: OOS 5.7265, AltOOS 12.8207
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
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
ALT_OOS_ST = "2013-01-01"

H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
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

_PREFIXES = [f"h{i:03d}" for i in range(62, 117)]


# ── Data helpers ─────────────────────────────────────────────────────────────

def fetch_ohlc(ticker, start, end):
    for prefix in _PREFIXES:
        cp = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{start}_{end}.parquet"
        if cp.exists():
            df = pd.read_parquet(cp)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    cp = CACHE_DIR / f"h116_{ticker}_ohlc_{start}_{end}.parquet"
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
    cp = CACHE_DIR / f"h116_{ticker}_close_{start}_{end}.parquet"
    print(f"  Downloading {ticker} …")
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ── Strategy builders ─────────────────────────────────────────────────────────

def build_rotation(tickers, start, end, n_hold=1, tsmom_filter=False):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_ret= daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6  = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1

    rows = []
    for i in range(12, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        mom_row = mom_12.iloc[i].dropna()
        valid = mom_row.index.intersection(vol_row.index)
        if tsmom_filter:
            valid = pd.Index([t for t in valid if mom_row[t] > 0])
            if len(valid) == 0:
                rows.append((monthly_px.index[i], 0.0))
                continue
        if len(valid) < n_hold:
            rows.append((monthly_px.index[i], monthly_ret.iloc[i][list(valid)].mean() if len(valid) > 0 else 0.0))
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], float(monthly_ret.iloc[i][top_n].mean())))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom = (df["high"]-df["low"]).replace(0, np.nan)
    ibs = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g = (df["open"]-prev_cl)/prev_cl
    equity = INITIAL_EQUITY
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
        return {"sharpe":0.0,"cagr":0.0,"max_drawdown":0.0,"n_months":len(r),"neg_years":0,"cumul":1.0}
    eq = (1+r).cumprod()
    n_yr = len(r)/12.0
    cagr = float(eq.iloc[-1])**(1/n_yr)-1
    vol = float(r.std(ddof=1))*np.sqrt(12)
    sharpe = cagr/vol if vol > 0 else 0.0
    max_dd = float((eq/eq.expanding().max()-1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr":round(cagr,4),"sharpe":round(sharpe,4),
            "max_drawdown":round(max_dd,4),"n_months":len(r),
            "neg_years":neg_yrs,"cumul":round(float(eq.iloc[-1]),4)}


def build_blend(sub_rets_dict):
    df = pd.DataFrame(sub_rets_dict)
    combined = pd.Series(0.0, index=df.dropna(how="all").index)
    for key, w in PROD_W.items():
        if key in df.columns:
            combined = combined.add(df[key].reindex(combined.index).fillna(0) * w, fill_value=0)
    return combined.dropna()


def print_blend_stats(r, label):
    oos  = stats(r[OOS_START:])
    alt  = stats(r[ALT_OOS_ST:])
    is_  = stats(r[IS_START:IS_END])
    print(f"  {label:<35} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("H116 — TSMOM Filter Combination Search")
    print("=" * 70)

    print("\nPre-computing sub-strategy return series…")

    # IBS components (shared across all combinations)
    ibs_rets = {}
    for sym, (buy, sell, hold, gap_min) in IBS_CFGS.items():
        ohlc = fetch_ohlc(sym, FULL_START, FULL_END)
        ibs_rets[sym] = to_monthly(ibs_equity_curve(ohlc, buy, sell, hold, gap_min))
        print(f"  IBS {sym} done")

    # Monthly rotation variants
    print("\n  Computing H041a (baseline + filtered)…")
    h041a_base = build_rotation(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h041a_filt = build_rotation(H041A_FULL, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)

    print("  Computing H026 (baseline + filtered)…")
    h026_base  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=False)
    h026_filt  = build_rotation(H026_ASSETS, FULL_START, FULL_END, n_hold=1, tsmom_filter=True)

    print("  Computing H045 (baseline + filtered)…")
    h045_base  = build_rotation(H045_PROD, FULL_START, FULL_END, n_hold=2, tsmom_filter=False)
    h045_filt  = build_rotation(H045_PROD, FULL_START, FULL_END, n_hold=2, tsmom_filter=True)

    print("\n" + "=" * 70)
    print("Combination results (IS Sharpe/CAGR | OOS Sharpe/CAGR/Cumul | AltOOS Cumul | MaxDD | NegYrs)")
    print("=" * 70 + "\n")

    combinations = {
        "Baseline (H112)":           {"h041a": h041a_base, "h026": h026_base, "h045": h045_base},
        "H026 filter":               {"h041a": h041a_base, "h026": h026_filt, "h045": h045_base},
        "H041a filter":              {"h041a": h041a_filt, "h026": h026_base, "h045": h045_base},
        "H045 filter":               {"h041a": h041a_base, "h026": h026_base, "h045": h045_filt},
        "H026+H041a filter":         {"h041a": h041a_filt, "h026": h026_filt, "h045": h045_base},
        "H026+H045 filter":          {"h041a": h041a_base, "h026": h026_filt, "h045": h045_filt},
        "H041a+H045 filter":         {"h041a": h041a_filt, "h026": h026_base, "h045": h045_filt},
        "All three filtered":        {"h041a": h041a_filt, "h026": h026_filt, "h045": h045_filt},
    }

    results_table = {}
    baseline_oos_c = None

    for label, sub_strats in combinations.items():
        base = {**sub_strats, **ibs_rets}
        blend = build_blend(base)
        oos_s, alt_s = print_blend_stats(blend, label)
        results_table[label] = {
            "oos_cumul":   oos_s["cumul"],
            "alt_cumul":   alt_s["cumul"],
            "oos_sharpe":  oos_s["sharpe"],
            "oos_cagr":    oos_s["cagr"],
            "max_drawdown":oos_s["max_drawdown"],
            "neg_years":   oos_s["neg_years"],
        }
        if label == "Baseline (H112)":
            baseline_oos_c = oos_s["cumul"]
            baseline_alt_c = alt_s["cumul"]

    # Best combination
    print("\n" + "─" * 70)
    best_label = max(
        (k for k in results_table if k != "Baseline (H112)"),
        key=lambda k: results_table[k]["oos_cumul"] + results_table[k]["alt_cumul"]
    )
    best = results_table[best_label]
    baseline = results_table["Baseline (H112)"]

    print(f"\n  Best combination: {best_label}")
    print(f"    OOS Cumul:  {best['oos_cumul']:.4f}  (baseline {baseline['oos_cumul']:.4f},  Δ{best['oos_cumul']-baseline['oos_cumul']:+.4f})")
    print(f"    AltOOS:     {best['alt_cumul']:.4f}  (baseline {baseline['alt_cumul']:.4f},  Δ{best['alt_cumul']-baseline['alt_cumul']:+.4f})")
    print(f"    OOS Sharpe: {best['oos_sharpe']:.3f}  MaxDD: {best['max_drawdown']*100:.1f}%  NegYrs: {best['neg_years']}")

    # Determine verdict
    both_better = (best['oos_cumul'] > baseline['oos_cumul'] and
                   best['alt_cumul'] > baseline['alt_cumul'])

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    if both_better:
        delta_oos = best['oos_cumul'] - baseline['oos_cumul']
        delta_alt = best['alt_cumul'] - baseline['alt_cumul']
        print(f"\n  → CONFIRMED: '{best_label}' improves both windows")
        print(f"     OOS Δ{delta_oos:+.4f}  AltOOS Δ{delta_alt:+.4f}")
        print(f"\n  H116 production upgrade: apply '{best_label}' to existing H112")
        print(f"  New baseline: OOS {best['oos_cumul']:.4f}  AltOOS {best['alt_cumul']:.4f}")
    else:
        print(f"\n  → NOT CONFIRMED — no combination improves both OOS windows simultaneously")

    verdict = "CONFIRMED" if both_better else "NOT_CONFIRMED"
    out_data = {
        "combinations": results_table,
        "baseline": results_table["Baseline (H112)"],
        "best_label": best_label,
        "best": best,
        "verdict": verdict,
        "confirmed": both_better,
    }
    out = RESULT_DIR / "h116_results.json"
    out.write_text(json.dumps(out_data, indent=2, default=str))
    print(f"\n  Results saved → {out}")


if __name__ == "__main__":
    main()
