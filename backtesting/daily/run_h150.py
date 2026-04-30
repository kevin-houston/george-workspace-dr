"""
H150 — Low-Volatility Anomaly: Sector Universe
================================================

NEW STRATEGY FAMILY.  Tests whether rotating into the *lowest-volatility*
S&P sector ETF each month generates standalone alpha, and whether it is
sufficiently uncorrelated with H026 (momentum rotation) to justify a
portfolio blend.

Academic basis: the Low-Volatility Anomaly (Blitz & van Vliet 2007, Baker et
al. 2011) — low-vol equities outperform high-vol equities on a risk-adjusted
basis, and often in absolute terms (in direct contradiction to CAPM).

Implementation for ETFs:
  Universe : 11 S&P sector ETFs (XLK XLE XLF XLV XLI XLB XLU XLRE XLY XLP XLC)
             BIL is excluded from ranking (trivially lowest vol) but used as
             safe-harbor when the TSMOM filter eliminates all sectors.
  Signal   : Rank sectors by 6-month realized volatility (ascending).
             Hold the 1 or 2 lowest-vol sectors.
  Filter   : Optional 3m TSMOM filter (>0 or >threshold) — avoids buying a
             "low-vol but crashing" sector.

Variants:
  A) Inv-vol top-1, no TSMOM filter        — pure anomaly, no safety net
  B) Inv-vol top-1, 3m TSMOM > 0%         — crash protection
  C) Inv-vol top-2, 3m TSMOM > 0%         — slight diversification
  D) Hybrid: 50% inv-vol + 50% mom rank, top-1, 3m TSMOM > 0%
  E) Defensive-only subset (XLU XLP XLV XLRE), inv-vol top-1, no filter
  F) Inv-vol top-1, 3m TSMOM > 2%         — tighter filter

Baselines: SPY buy-and-hold, H026 momentum rotation.

Success criteria (new strategy family):
  - OOS Sharpe > 1.0
  - OOS cumulative return > SPY
  - Passes both OOS windows (OOS 2018+ and AltOOS 2013+)
  - Monthly return correlation with H026 < 0.7 (diversification potential)

If standalone criteria met → run H151 to test H026 + LowVol blend.

H149 context: production is now 100% H026. Any new strategy must justify
displacing part of H026's budget, so the correlation check is critical.
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

SECTOR_ETFs = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC"]
DEFENSIVE   = ["XLU","XLP","XLV","XLRE"]

H026_ASSETS = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]

_PREFIXES = [f"h{i:03d}" for i in range(62, 151)]


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def fetch_daily_close(ticker, start, end):
    for pfx in _PREFIXES:
        for suffix in ["ohlc", "close"]:
            p = CACHE_DIR / f"{pfx}_{ticker}_{suffix}_{start}_{end}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                col = "close" if "close" in df.columns else df.columns[0]
                return df[col].rename(ticker)
    cp = CACHE_DIR / f"h150_{ticker}_close_{start}_{end}.parquet"
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

def _load_price_frame(tickers, start, end):
    closes = {}
    for t in tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    return monthly_px, monthly_rt


def build_lowvol_rotation(tickers, start, end, n_hold=1,
                           tsmom_lb=None, tsmom_threshold=0.0):
    """
    Low-volatility sector rotation.
    Signal: hold the n_hold sectors with lowest 6m realized vol this month.
    BIL used as cash fallback if TSMOM filter eliminates all sectors.
    """
    all_tickers = tickers + (["BIL"] if "BIL" not in tickers else [])
    monthly_px, monthly_rt = _load_price_frame(all_tickers, start, end)

    vol_6     = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_tsmom = (monthly_px / monthly_px.shift(tsmom_lb) - 1) if tsmom_lb else None

    max_lb = max(6, tsmom_lb or 0) + 1
    rows = []
    for i in range(max_lb, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        candidates = [t for t in tickers if t in vol_row.index]

        if mom_tsmom is not None:
            tsmom_row = mom_tsmom.iloc[i]
            candidates = [t for t in candidates
                          if t in tsmom_row.index
                          and not np.isnan(float(tsmom_row[t]))
                          and float(tsmom_row[t]) > tsmom_threshold]

        if len(candidates) == 0:
            # All sectors failed filter → BIL safe harbor
            ret = float(monthly_rt.iloc[i]["BIL"]) if "BIL" in monthly_rt.columns else 0.0
            rows.append((monthly_px.index[i], ret))
            continue

        vol_sub = vol_row.reindex(candidates).dropna()
        if len(vol_sub) == 0:
            rows.append((monthly_px.index[i], 0.0))
            continue

        top = list(vol_sub.nsmallest(min(n_hold, len(vol_sub))).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def build_hybrid_rotation(tickers, start, end, n_hold=1,
                           vol_weight=0.5, mom_weight=0.5,
                           tsmom_lb=3, tsmom_threshold=0.0):
    """
    Hybrid: score = vol_weight * rank(inv_vol) + mom_weight * rank(momentum).
    Momentum rank uses the standard 3m+6m+12m ensemble.
    """
    all_tickers = tickers + (["BIL"] if "BIL" not in tickers else [])
    monthly_px, monthly_rt = _load_price_frame(all_tickers, start, end)

    vol_6  = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    tsmom_series = monthly_px / monthly_px.shift(tsmom_lb) - 1

    rows = []
    for i in range(13, len(monthly_px)):
        vol_row   = vol_6.iloc[i].dropna()
        m3_row    = mom_3.iloc[i].dropna()
        m6_row    = mom_6.iloc[i].dropna()
        m12_row   = mom_12.iloc[i].dropna()
        ts_row    = tsmom_series.iloc[i]

        candidates = [t for t in tickers
                      if t in vol_row.index and t in m3_row.index
                      and t in m6_row.index and t in m12_row.index]
        # TSMOM filter
        candidates = [t for t in candidates
                      if t in ts_row.index
                      and not np.isnan(float(ts_row[t]))
                      and float(ts_row[t]) > tsmom_threshold]

        if len(candidates) == 0:
            ret = float(monthly_rt.iloc[i]["BIL"]) if "BIL" in monthly_rt.columns else 0.0
            rows.append((monthly_px.index[i], ret))
            continue

        vol_sub = vol_row.reindex(candidates)
        # rank(inv_vol): highest rank = lowest vol
        inv_vol_rank = vol_sub.rank(ascending=False)
        mom_score    = (m3_row.reindex(candidates).rank() +
                        m6_row.reindex(candidates).rank() +
                        m12_row.reindex(candidates).rank())
        # Normalize each to 0-1 before blending
        def normalize(s):
            r = s.max() - s.min()
            return (s - s.min()) / r if r > 0 else s * 0
        score = vol_weight * normalize(inv_vol_rank) + mom_weight * normalize(mom_score)
        top = list(score.nlargest(min(n_hold, len(score))).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def build_momentum_rotation(tickers, start, end, n_hold=1,
                             tsmom_lookbacks=None, tsmom_threshold=0.0):
    """Standard momentum rotation — used for H026 and SPY benchmark."""
    all_tickers = tickers + (["BIL"] if "BIL" not in tickers else [])
    monthly_px, monthly_rt = _load_price_frame(all_tickers, start, end)

    vol_6  = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_12 = monthly_px / monthly_px.shift(12) - 1
    mom_6  = monthly_px / monthly_px.shift(6)  - 1
    mom_3  = monthly_px / monthly_px.shift(3)  - 1
    lookbacks = tsmom_lookbacks or []
    mom_by_lb = {lb: monthly_px / monthly_px.shift(lb) - 1 for lb in set(lookbacks)}

    rows = []
    for i in range(max(12, max(lookbacks or [0])) + 1, len(monthly_px)):
        vol_row = vol_6.iloc[i].dropna()
        m12_row = mom_12.iloc[i].dropna()
        m6_row  = mom_6.iloc[i].dropna()
        m3_row  = mom_3.iloc[i].dropna()
        valid = list(m12_row.index.intersection(vol_row.index)
                     .intersection(m6_row.index).intersection(m3_row.index))
        valid = [t for t in valid if t in tickers]  # exclude BIL from ranking
        passing = list(valid)
        for lb in lookbacks:
            lb_row = mom_by_lb[lb].iloc[i]
            passing = [t for t in passing
                       if t in lb_row.index
                       and not np.isnan(float(lb_row[t]))
                       and float(lb_row[t]) > tsmom_threshold]
        if len(passing) == 0:
            ret = float(monthly_rt.iloc[i]["BIL"]) if "BIL" in monthly_rt.columns else 0.0
            rows.append((monthly_px.index[i], ret))
            continue
        n = min(n_hold, len(passing))
        score = (m12_row.reindex(passing).rank() + m6_row.reindex(passing).rank() +
                 m3_row.reindex(passing).rank() + vol_row.reindex(passing).rank(ascending=False))
        top = list(score.nlargest(n).index)
        rows.append((monthly_px.index[i], float(monthly_rt.iloc[i][top].mean())))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


# ─────────────────────────────────────────────────────────────────────────────
# Analytics
# ─────────────────────────────────────────────────────────────────────────────

def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {"sharpe": 0.0, "cagr": 0.0, "max_drawdown": 0.0,
                "n_months": len(r), "neg_years": 0, "cumul": 1.0}
    eq    = (1 + r).cumprod()
    n_yr  = len(r) / 12.0
    cagr  = float(eq.iloc[-1]) ** (1/n_yr) - 1
    vol   = float(r.std(ddof=1)) * np.sqrt(12)
    sharpe = cagr / vol if vol > 0 else 0.0
    max_dd = float((eq / eq.expanding().max() - 1).min())
    neg_yrs = int(r.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum())
    return {"cagr": round(cagr, 4), "sharpe": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4), "n_months": len(r),
            "neg_years": neg_yrs, "cumul": round(float(eq.iloc[-1]), 4)}


def print_stats(r, label):
    oos = stats(r[OOS_START:])
    alt = stats(r[ALT_OOS_ST:])
    is_ = stats(r[IS_START:IS_END])
    print(f"  {label:<55} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


def correlation_vs(r_a, r_b, window_start):
    """Monthly return correlation in a date window."""
    aligned = pd.DataFrame({"a": r_a, "b": r_b}).dropna()
    aligned = aligned[window_start:]
    if len(aligned) < 12:
        return float("nan")
    return round(float(aligned["a"].corr(aligned["b"])), 3)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H150 — Low-Volatility Anomaly: Sector Universe")
    print("=" * 80)
    print("New strategy family. Baseline comparisons: SPY B&H and H026 momentum.\n")

    # ── Baselines ──────────────────────────────────────────────────────────────
    print("Computing baselines…")
    spy_close = fetch_daily_close("SPY", FULL_START, FULL_END)
    spy_monthly_px = spy_close.resample("ME").last()
    spy_rets = spy_monthly_px.pct_change().dropna()

    h026_rets = build_momentum_rotation(
        SECTOR_ETFs, FULL_START, FULL_END,
        n_hold=1, tsmom_lookbacks=[12], tsmom_threshold=0.05)
    print("  H026 (sector, 12m mom, +5% threshold) done")

    h026_full_rets = build_momentum_rotation(
        H026_ASSETS, FULL_START, FULL_END,
        n_hold=1, tsmom_lookbacks=[12], tsmom_threshold=0.05)
    print("  H026-full (25-asset, production config) done")

    # ── Variants ───────────────────────────────────────────────────────────────
    print("\nComputing low-vol variants…")

    variants = {}

    # A: Pure inv-vol, no filter
    variants["A) Inv-vol top-1, no TSMOM filter"] = build_lowvol_rotation(
        SECTOR_ETFs, FULL_START, FULL_END, n_hold=1)
    print("  A done")

    # B: Inv-vol top-1 + 3m TSMOM > 0
    variants["B) Inv-vol top-1, 3m TSMOM > 0%"] = build_lowvol_rotation(
        SECTOR_ETFs, FULL_START, FULL_END, n_hold=1, tsmom_lb=3, tsmom_threshold=0.0)
    print("  B done")

    # C: Inv-vol top-2 + 3m TSMOM > 0
    variants["C) Inv-vol top-2, 3m TSMOM > 0%"] = build_lowvol_rotation(
        SECTOR_ETFs, FULL_START, FULL_END, n_hold=2, tsmom_lb=3, tsmom_threshold=0.0)
    print("  C done")

    # D: Hybrid 50/50 vol+mom, top-1, 3m TSMOM > 0
    variants["D) Hybrid 50% inv-vol + 50% mom, top-1"] = build_hybrid_rotation(
        SECTOR_ETFs, FULL_START, FULL_END, n_hold=1,
        vol_weight=0.5, mom_weight=0.5, tsmom_lb=3, tsmom_threshold=0.0)
    print("  D done")

    # E: Defensive-only subset, inv-vol top-1, no filter
    variants["E) Defensive subset (XLU/XLP/XLV/XLRE), inv-vol top-1"] = \
        build_lowvol_rotation(DEFENSIVE, FULL_START, FULL_END, n_hold=1)
    print("  E done")

    # F: Inv-vol top-1, tighter 3m TSMOM > 2%
    variants["F) Inv-vol top-1, 3m TSMOM > 2%"] = build_lowvol_rotation(
        SECTOR_ETFs, FULL_START, FULL_END, n_hold=1, tsmom_lb=3, tsmom_threshold=0.02)
    print("  F done")

    # ── Print results ──────────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("Results (standalone performance)")
    print("=" * 80)
    print(f"  {'Strategy':<55} IS=Sharpe/CAGR  OOS=Sharpe/CAGR/Cumul  Alt=Cumul  MaxDD  NegYrs\n")

    spy_oos, spy_alt = print_stats(spy_rets, "SPY buy-and-hold")
    h026_oos, h026_alt = print_stats(h026_rets, "H026 (11 sectors, 12m mom, +5%)")
    h026f_oos, h026f_alt = print_stats(h026_full_rets, "H026-full (25 assets, production)")

    print()
    variant_results = {}
    for label, r in variants.items():
        oos_s, alt_s = print_stats(r, label)
        variant_results[label] = (oos_s, alt_s, r)

    # ── Correlation analysis ───────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("Correlation vs H026-full (production config) — OOS 2018+")
    print("=" * 80)
    for label, (oos_s, alt_s, r) in variant_results.items():
        corr_oos = correlation_vs(r, h026_full_rets, OOS_START)
        corr_alt = correlation_vs(r, h026_full_rets, ALT_OOS_ST)
        diversify = "✓ diversifying" if corr_oos < 0.70 else "~ moderate corr" if corr_oos < 0.85 else "✗ high corr"
        print(f"  {label:<55}  OOS corr={corr_oos:+.3f}  Alt corr={corr_alt:+.3f}  {diversify}")

    # ── Standalone verdict ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("Standalone verdict (beats SPY in both OOS windows?)")
    print("=" * 80)
    confirmed_standalone = []
    for label, (oos_s, alt_s, r) in variant_results.items():
        beats_spy_oos = oos_s["cumul"] > spy_oos["cumul"]
        beats_spy_alt = alt_s["cumul"] > spy_alt["cumul"]
        sharpe_ok     = oos_s["sharpe"] > 1.0
        both_positive = oos_s["cumul"] > 1.0 and alt_s["cumul"] > 1.0
        passes = beats_spy_oos and beats_spy_alt and sharpe_ok and both_positive
        verdict = "✓ STANDALONE CONFIRMED" if passes else "✗ below SPY or Sharpe<1"
        print(f"  {label}")
        print(f"    OOS: {oos_s['cumul']:.4f} (SPY {spy_oos['cumul']:.4f})  "
              f"Alt: {alt_s['cumul']:.4f} (SPY {spy_alt['cumul']:.4f})  "
              f"Sharpe={oos_s['sharpe']:.3f}  {verdict}")
        if passes:
            confirmed_standalone.append(label)
        print()

    # ── Overall verdict ────────────────────────────────────────────────────────
    print("=" * 80)
    if confirmed_standalone:
        print(f"\n  VERDICT: CONFIRMED — {len(confirmed_standalone)} variant(s) beat SPY standalone.")
        print(f"  Best by OOS Sharpe:")
        best = max(confirmed_standalone,
                   key=lambda l: variant_results[l][0]["sharpe"])
        oos_s, alt_s, _ = variant_results[best]
        corr = correlation_vs(variant_results[best][2], h026_full_rets, OOS_START)
        print(f"    {best}")
        print(f"    OOS Sharpe={oos_s['sharpe']:.3f}  OOS cumul={oos_s['cumul']:.4f}  "
              f"MaxDD={oos_s['max_drawdown']*100:.1f}%  corr(H026)={corr:+.3f}")
        print(f"\n  Next step: H151 — blend H026 + LowVol at various weights if corr < 0.70")
    else:
        print(f"\n  VERDICT: NOT CONFIRMED — no variant beats SPY consistently in both OOS windows.")
        print(f"  Low-vol sector rotation does not generate standalone alpha on 11-sector universe.")
        print(f"  Consider: (1) add fixed-income/commodity to the universe, or")
        print(f"             (2) test broader ETF universe with USMV/SPLV (2011+ only), or")
        print(f"             (3) move to next strategy family (ETF Pairs Trading).")
    print()


if __name__ == "__main__":
    main()
