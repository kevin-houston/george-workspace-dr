"""
H165a — VIX Threshold Benchmark for H026 Sector Rotation
==========================================================

PREREQUISITE for H165 (TradingAgents macro-regime gate):
Test whether a simple VIX-based regime filter improves H026 sector rotation
before committing API costs to a full LLM macro analyst.

Hypothesis: VIX > threshold signals a bad macro regime where we should go to
BIL (cash) instead of holding the top sector. This would act as a fast-exit
trigger ON TOP OF the existing 12m TSMOM filter.

Variants tested:
  A: No VIX filter (baseline H026 replication)
  B: Exit to BIL when end-of-month VIX > 20
  C: Exit to BIL when end-of-month VIX > 25
  D: Exit to BIL when end-of-month VIX > 30
  E: Exit to BIL when end-of-month VIX > 35
  F: Exit to BIL when end-of-month VIX > 40

H026 signal: rank(3m)+rank(6m)+rank(12m)+rank(inv_vol), top-1, TSMOM>5%
IS: 2007-01-01–2017-12-31  OOS: 2018-01-01–2026-04-30

Expected result: VIX filter may be neutral-to-harmful because:
  1. TSMOM already exits when sectors turn negative (correlated with VIX spikes)
  2. VIX spike recoveries are fast — exiting at high VIX misses V-shaped recoveries
  3. VIX is a coincident indicator, not forward-looking

Key months to watch:
  - 2008-2009: VIX>40 for 12+ months (GFC)
  - 2010-02: Flash Crash (brief VIX spike)
  - 2020-03: COVID crash (VIX→80), but V-shaped recovery
  - 2022: Ukraine invasion + Fed hiking cycle (VIX 25-35)
"""

import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

CACHE_DIR  = Path(__file__).parent.parent / "cache"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2006-01-01"   # extra year for warmup
FULL_END   = "2026-04-30"
IS_END     = pd.Timestamp("2017-12-31")
OOS_START  = pd.Timestamp("2018-01-01")
ALT_OOS_ST = pd.Timestamp("2013-01-01")

# H026 production universe (as of H149)
H026_ASSETS = [
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",
    "BIL", "GLD", "TLT", "IEF", "TIP", "DBC", "AGG", "GDX", "DBA", "SLV",
    "UNG", "EWZ", "IBB", "USO",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def fetch_monthly(ticker, prefix="h165a"):
    cp = CACHE_DIR / f"{prefix}_{ticker}_monthly.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    try:
        raw = yf.download([ticker], start=FULL_START, end=FULL_END,
                          auto_adjust=True, progress=False)
        if raw.empty:
            return pd.Series(dtype=float, name=ticker)
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw.xs(ticker, axis=1, level=1)["Close"]
        else:
            close = raw["Close"]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        monthly = close.resample("ME").last()
        monthly = monthly.pct_change().rename(ticker)
        monthly.to_frame().to_parquet(cp)
        return monthly
    except Exception as e:
        print(f"    WARNING: {ticker} load failed: {e}")
        return pd.Series(dtype=float, name=ticker)


def fetch_vix_monthly():
    cp = CACHE_DIR / "h165a_VIX_monthly_level.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    try:
        raw = yf.download(["^VIX"], start=FULL_START, end=FULL_END,
                          auto_adjust=False, progress=False)
        if raw.empty:
            return pd.Series(dtype=float, name="VIX")
        if isinstance(raw.columns, pd.MultiIndex):
            close = raw.xs("^VIX", axis=1, level=1)["Close"]
        else:
            close = raw["Close"]
        close.index = pd.to_datetime(close.index).tz_localize(None)
        # Use end-of-month VIX level (the level when the rebalance decision is made)
        monthly = close.resample("ME").last().rename("VIX")
        monthly.to_frame().to_parquet(cp)
        return monthly
    except Exception as e:
        print(f"    WARNING: VIX load failed: {e}")
        return pd.Series(dtype=float, name="VIX")


# ---------------------------------------------------------------------------
# Signal computation (H026 production replica)
# ---------------------------------------------------------------------------

def compute_h026_signal(monthly_df, date, tsmom_thresh=0.05):
    """
    H026 signal: rank(3m)+rank(6m)+rank(12m)+rank(inv_6m_vol), top-1, TSMOM>5%.
    Returns the ticker to hold (or 'BIL' if nothing qualifies).
    """
    avail = monthly_df.loc[:date]
    if len(avail) < 13:
        return "BIL"

    def mom_return(lb, skip=1):
        end   = date - pd.DateOffset(months=skip)
        start = end   - pd.DateOffset(months=lb - 1)
        win = monthly_df.loc[start:end]
        if len(win) < max(lb - 2, 1):
            return pd.Series(dtype=float)
        return (1 + win).prod() - 1

    r12 = mom_return(12, skip=1)
    r6  = mom_return(6,  skip=0)
    r3  = mom_return(3,  skip=0)

    # Require ≥24 months of history
    n_obs    = avail.count()
    eligible = n_obs[n_obs >= 24].index
    r12 = r12.reindex(eligible).dropna()
    r6  = r6.reindex(eligible).dropna()
    r3  = r3.reindex(eligible).dropna()

    if r12.empty:
        return "BIL"

    # TSMOM filter: require 12m return > tsmom_thresh
    r12_filtered = r12[r12 > tsmom_thresh]
    if r12_filtered.empty:
        return "BIL"

    common = r12_filtered.index.intersection(r6.index).intersection(r3.index)
    if common.empty:
        return "BIL"

    r12f = r12_filtered.loc[common]
    r6f  = r6.loc[common]
    r3f  = r3.loc[common]

    # Inverse 6m vol
    vol6m_start = date - pd.DateOffset(months=6)
    vol_window  = monthly_df.loc[vol6m_start:date, common]
    inv_vol = (1.0 / vol_window.std(ddof=1)).replace([np.inf, -np.inf], np.nan).dropna()

    final_common = r12f.index.intersection(r6f.index).intersection(r3f.index).intersection(inv_vol.index)
    if final_common.empty:
        return "BIL"

    scores = (r12f.loc[final_common].rank(ascending=True)
              + r6f.loc[final_common].rank(ascending=True)
              + r3f.loc[final_common].rank(ascending=True)
              + inv_vol.loc[final_common].rank(ascending=True))

    return str(scores.idxmax())


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def backtest(monthly_df, vix_monthly, vix_threshold=None):
    """
    Run H026 monthly rotation backtest with optional VIX threshold override.

    vix_threshold: if set, go to BIL whenever end-of-month VIX > threshold.
    Returns monthly return series.
    """
    dates = monthly_df.index
    dates = dates[dates >= pd.Timestamp(FULL_START)]

    portfolio_ret = []
    portfolio_dates = []

    for i, date in enumerate(dates[13:], start=13):  # need 13m warmup
        # Compute H026 signal
        holding = compute_h026_signal(monthly_df, date)

        # VIX override: if VIX is too high, go to BIL
        if vix_threshold is not None and date in vix_monthly.index:
            vix_val = float(vix_monthly.loc[date])
            if not np.isnan(vix_val) and vix_val > vix_threshold:
                holding = "BIL"

        # Return for next month (not lookahead: this month's close → next month's return)
        if i + 1 >= len(dates):
            break
        next_date = dates[i + 1]

        if holding in monthly_df.columns and next_date in monthly_df.index:
            ret = float(monthly_df.loc[next_date, holding])
            if np.isnan(ret):
                ret = 0.0
        elif holding == "BIL" and "BIL" in monthly_df.columns:
            ret = float(monthly_df.loc[next_date, "BIL"]) if next_date in monthly_df.index else 0.0
        else:
            ret = 0.0

        portfolio_ret.append(ret)
        portfolio_dates.append(next_date)

    return pd.Series(portfolio_ret, index=portfolio_dates, name="portfolio")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def stats(r, label=""):
    r = r.dropna()
    if len(r) < 6:
        return {"cumul": 1.0, "cagr": 0.0, "sharpe": 0.0, "max_dd": 0.0, "neg_yrs": 0, "label": label}
    eq  = (1 + r).cumprod()
    ann = 12
    cumul  = float(eq.iloc[-1])
    cagr   = cumul ** (ann / len(r)) - 1
    vol    = r.std(ddof=1) * np.sqrt(ann)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cumul": cumul, "cagr": cagr, "sharpe": sharpe,
            "max_dd": max_dd, "neg_yrs": neg_yrs, "label": label}


def count_bils(monthly_df, vix_monthly, vix_threshold=None):
    """Count months in BIL due to TSMOM vs VIX filter."""
    dates = monthly_df.index
    n_tsmom_bil = 0
    n_vix_bil   = 0
    for date in dates[13:]:
        h026_signal = compute_h026_signal(monthly_df, date)
        if h026_signal == "BIL":
            n_tsmom_bil += 1
        elif vix_threshold is not None and date in vix_monthly.index:
            vix_val = float(vix_monthly.loc[date])
            if not np.isnan(vix_val) and vix_val > vix_threshold:
                n_vix_bil += 1
    return n_tsmom_bil, n_vix_bil


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    lines = []
    def out(s=""):
        print(s)
        lines.append(s)

    out()
    out("=" * 65)
    out("  H165a — VIX Threshold Benchmark for H026")
    out("=" * 65)
    out("  Testing: does VIX-based regime gate improve H026 sector rotation?")
    out("  Prerequisite for H165 (TradingAgents macro LLM gate)")
    out()

    # [1] Load data
    out("[1] Loading H026 asset prices and VIX…")
    series_list = []
    for ticker in H026_ASSETS:
        s = fetch_monthly(ticker)
        if not s.empty and len(s) >= 50:
            series_list.append(s)
        else:
            out(f"    Skipping {ticker}: insufficient data")

    monthly_df = pd.concat(series_list, axis=1)
    monthly_df.index = pd.to_datetime(monthly_df.index).tz_localize(None)

    vix_monthly = fetch_vix_monthly()
    spy_m = fetch_monthly("SPY", prefix="h165a_spy")

    out(f"    Assets loaded: {monthly_df.shape[1]}/{len(H026_ASSETS)}")
    out(f"    Grid: {monthly_df.shape}  ({monthly_df.index[0].date()} → {monthly_df.index[-1].date()})")
    out(f"    VIX monthly: {len(vix_monthly)} months  "
        f"({vix_monthly.index[0].date()} → {vix_monthly.index[-1].date()})")
    out(f"    VIX range: min={vix_monthly.min():.1f}  max={vix_monthly.max():.1f}  "
        f"median={vix_monthly.median():.1f}")

    # [2] Run baseline
    out("\n[2] Running variants…")

    spy_oos  = stats(spy_m[spy_m.index >= OOS_START], "SPY OOS")
    spy_alt  = stats(spy_m[spy_m.index >= ALT_OOS_ST], "SPY AltOOS")
    out(f"    SPY OOS baseline: cumul={spy_oos['cumul']:.4f}  Sharpe={spy_oos['sharpe']:.3f}")
    out()

    VARIANTS = [
        ("A",  None,  "No VIX filter (baseline H026 replica)"),
        ("B",  20.0,  "VIX < 20 required"),
        ("C",  25.0,  "VIX < 25 required"),
        ("D",  30.0,  "VIX < 30 required"),
        ("E",  35.0,  "VIX < 35 required"),
        ("F",  40.0,  "VIX < 40 required"),
    ]

    results = []
    for (label, thresh, desc) in VARIANTS:
        r = backtest(monthly_df, vix_monthly, vix_threshold=thresh)
        r_is  = r[(r.index > pd.Timestamp("2008-01-01")) & (r.index <= IS_END)]
        r_oos = r[r.index >= OOS_START]
        r_alt = r[r.index >= ALT_OOS_ST]

        s_is  = stats(r_is, f"{label} IS")
        s_oos = stats(r_oos, f"{label} OOS")
        s_alt = stats(r_alt, f"{label} AltOOS")

        n_tsmom_bil, n_vix_bil = count_bils(monthly_df, vix_monthly, thresh)

        results.append({
            "label": label, "thresh": thresh, "desc": desc,
            "is": s_is, "oos": s_oos, "alt": s_alt,
            "n_tsmom_bil": n_tsmom_bil, "n_vix_bil": n_vix_bil,
        })

        out(f"  Variant {label}: {desc}")
        out(f"    IS(2008-17):  cumul={s_is['cumul']:.4f}  Sharpe={s_is['sharpe']:.3f}"
            f"  MaxDD={s_is['max_dd']:.2%}")
        out(f"    OOS(2018+):  cumul={s_oos['cumul']:.4f}  Sharpe={s_oos['sharpe']:.3f}"
            f"  MaxDD={s_oos['max_dd']:.2%}  NegYrs={s_oos['neg_yrs']}")
        out(f"    AltOOS:      cumul={s_alt['cumul']:.4f}  Sharpe={s_alt['sharpe']:.3f}")
        if thresh:
            out(f"    Cash months: TSMOM={n_tsmom_bil}  VIX-added={n_vix_bil}"
                f"  (VIX>{thresh:.0f} adds {n_vix_bil} forced-BIL months)")
        else:
            out(f"    Cash months: TSMOM={n_tsmom_bil} (baseline)")
        out()

    # [3] Delta analysis vs baseline
    out("[3] Delta vs baseline (Variant A)…")
    baseline_oos = results[0]["oos"]
    baseline_alt = results[0]["alt"]
    out(f"  {'Variant':>8}  {'Thresh':>7}  {'ΔOOS_cumul':>11}  {'ΔAlt_cumul':>11}"
        f"  {'ΔOOS_Sharpe':>12}  {'VIX_BIL_mo':>10}")
    for rec in results:
        d_oos = rec["oos"]["cumul"] - baseline_oos["cumul"]
        d_alt = rec["alt"]["cumul"] - baseline_alt["cumul"]
        d_sh  = rec["oos"]["sharpe"] - baseline_oos["sharpe"]
        thresh_str = f">{rec['thresh']:.0f}" if rec["thresh"] else "none"
        out(f"  {rec['label']:>8}  {thresh_str:>7}  {d_oos:>+11.4f}  {d_alt:>+11.4f}"
            f"  {d_sh:>+12.3f}  {rec['n_vix_bil']:>10}")

    # [4] Key regime analysis
    out("\n[4] VIX regimes and TSMOM overlap…")
    vix_oos = vix_monthly[vix_monthly.index >= OOS_START]
    if not vix_oos.empty:
        out(f"    OOS VIX (2018-2026):")
        out(f"      Months VIX>20: {(vix_oos>20).sum()} / {len(vix_oos)}")
        out(f"      Months VIX>25: {(vix_oos>25).sum()} / {len(vix_oos)}")
        out(f"      Months VIX>30: {(vix_oos>30).sum()} / {len(vix_oos)}")
        out(f"      Months VIX>35: {(vix_oos>35).sum()} / {len(vix_oos)}")
        out(f"      Months VIX>40: {(vix_oos>40).sum()} / {len(vix_oos)}")

    # [5] Verdict
    out("\n[5] Verdict…")
    confirmed = [r for r in results[1:] if
                 r["oos"]["cumul"] > baseline_oos["cumul"] and
                 r["alt"]["cumul"] > baseline_alt["cumul"]]

    if confirmed:
        out(f"    VIX threshold HELPS in {len(confirmed)}/5 variants:")
        for r in confirmed:
            out(f"      {r['label']}: VIX>{r['thresh']:.0f}  "
                f"ΔOOS={r['oos']['cumul']-baseline_oos['cumul']:+.4f}")
        verdict = "VIX FILTER USEFUL — proceed to test TradingAgents (H165)"
    else:
        out("    No VIX threshold variant improves BOTH OOS windows vs baseline.")
        out("    TSMOM filter alone is already capturing market-regime information.")
        verdict = ("VIX FILTER DOES NOT HELP — TradingAgents (H165) unlikely to add "
                   "value via regime-gating. Consider direct fundamental overlay instead.")

    out()
    out(f"    CONCLUSION: {verdict}")

    # Save results
    result_path = RESULT_DIR / "h165a_vix_threshold_benchmark.txt"
    with open(result_path, "w") as f:
        f.write("\n".join(lines))
    out(f"\n    Results saved → {result_path}")


if __name__ == "__main__":
    main()
