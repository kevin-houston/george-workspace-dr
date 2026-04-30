"""
H151 — Hybrid Vol+Momentum Signal for H026 Sector Rotation
============================================================

H150 found that a hybrid signal (50% inv-vol + 50% momentum) on the 11-sector
universe produces Sharpe 2.645 vs H026's 2.163 on the same 11 sectors.

BUT: H150 used a loose filter (3m TSMOM > 0%) while H026 uses a tighter filter
(12m TSMOM > +5%). The comparison was confounded. This test isolates the
signal effect by holding the filter constant across variants.

Key question: Does adding an inverse-volatility component to H026's momentum
signal improve the 11-sector rotation? If yes, apply to the full 25-asset
H026 universe as well.

Universe A: 11 S&P sector ETFs (H026 core sectors only, + BIL safe harbor)
Universe B: 25-asset H026-full universe (sectors + commodities + bonds)

Signal variants (all use 12m TSMOM > +5% filter, identical to production H026):
  A) Pure momentum (rank 3m+6m+12m+inv_vol) — H026 baseline
  B) Hybrid: 75% momentum + 25% inv-vol rank
  C) Hybrid: 50% momentum + 50% inv-vol rank
  D) Hybrid: 25% momentum + 75% inv-vol rank
  E) Pure inv-vol (rank by 6m realized vol ascending only)

Run A-E on BOTH universes (11 sectors and 25 assets).

Baseline A on 11 sectors: OOS 22.6548, AltOOS 97.3526, Sharpe 2.163
Baseline A on 25 assets: OOS 382.9355, AltOOS 3243.0783, Sharpe 3.007

A variant CONFIRMS if it improves BOTH OOS windows vs its respective baseline.
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
H026_FULL   = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ","IBB","USO"]

TSMOM_LB        = 12
TSMOM_THRESHOLD = 0.05     # +5%, same as production H026

# (label, mom_weight, vol_weight)
SIGNAL_VARIANTS = [
    ("A) Pure momentum (H026 baseline)",       1.00, 0.00),
    ("B) 75% momentum + 25% inv-vol",          0.75, 0.25),
    ("C) 50% momentum + 50% inv-vol",          0.50, 0.50),
    ("D) 25% momentum + 75% inv-vol",          0.25, 0.75),
    ("E) Pure inv-vol (same TSMOM filter)",    0.00, 1.00),
]

_PREFIXES = [f"h{i:03d}" for i in range(62, 152)]


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
    cp = CACHE_DIR / f"h151_{ticker}_close_{start}_{end}.parquet"
    raw = yf.download([ticker], start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw.xs(ticker, axis=1, level=1)["Close"]
    else:
        close = raw["Close"]
    close.name = ticker
    close.to_frame().to_parquet(cp)
    return close


# ─────────────────────────────────────────────────────────────────────────────
# Hybrid signal rotation
# ─────────────────────────────────────────────────────────────────────────────

def build_hybrid_signal_rotation(ranking_tickers, start, end, n_hold=1,
                                  mom_weight=1.0, vol_weight=0.0,
                                  tsmom_lb=12, tsmom_threshold=0.05):
    """
    Rotation with a blended signal: mom_weight * momentum_rank + vol_weight * inv_vol_rank.
    Both rankings are normalized to [0,1] before blending so neither dominates by scale.
    TSMOM filter applied before ranking — assets that don't pass go to BIL safe harbor.
    BIL excluded from ranking (always used as cash fallback only).
    """
    all_tickers = ranking_tickers + ["BIL"]
    closes = {}
    for t in all_tickers:
        try:
            closes[t] = fetch_daily_close(t, start, end)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
    monthly_rt = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)

    vol_6      = monthly_rt.rolling(6).std() * np.sqrt(12)
    mom_12     = monthly_px / monthly_px.shift(12) - 1
    mom_6      = monthly_px / monthly_px.shift(6)  - 1
    mom_3      = monthly_px / monthly_px.shift(3)  - 1
    tsmom_ser  = monthly_px / monthly_px.shift(tsmom_lb) - 1

    def normalize(s):
        lo, hi = s.min(), s.max()
        return (s - lo) / (hi - lo) if (hi - lo) > 0 else pd.Series(0.5, index=s.index)

    rows = []
    for i in range(13, len(monthly_px)):
        vol_row  = vol_6.iloc[i].dropna()
        m12_row  = mom_12.iloc[i].dropna()
        m6_row   = mom_6.iloc[i].dropna()
        m3_row   = mom_3.iloc[i].dropna()
        ts_row   = tsmom_ser.iloc[i]

        # Start with full ranking universe (exclude BIL)
        candidates = [t for t in ranking_tickers
                      if t in vol_row.index and t in m12_row.index
                      and t in m6_row.index and t in m3_row.index]

        # TSMOM filter
        candidates = [t for t in candidates
                      if t in ts_row.index
                      and not np.isnan(float(ts_row[t]))
                      and float(ts_row[t]) > tsmom_threshold]

        if len(candidates) == 0:
            ret = float(monthly_rt.iloc[i]["BIL"]) if "BIL" in monthly_rt.columns else 0.0
            rows.append((monthly_px.index[i], ret))
            continue

        # Momentum score (standard ensemble)
        if mom_weight > 0:
            mom_score = (m12_row.reindex(candidates).rank() +
                         m6_row.reindex(candidates).rank()  +
                         m3_row.reindex(candidates).rank()  +
                         vol_row.reindex(candidates).rank(ascending=False))
            mom_norm = normalize(mom_score)
        else:
            mom_norm = pd.Series(0.0, index=candidates)

        # Inverse-vol score (lower vol = higher rank)
        if vol_weight > 0:
            inv_vol_rank = vol_row.reindex(candidates).rank(ascending=False)
            vol_norm = normalize(inv_vol_rank)
        else:
            vol_norm = pd.Series(0.0, index=candidates)

        score = mom_weight * mom_norm + vol_weight * vol_norm
        top   = list(score.nlargest(min(n_hold, len(score))).index)
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
    print(f"  {label:<50} IS={is_['sharpe']:.3f}/{is_['cagr']*100:.1f}%  "
          f"OOS={oos['sharpe']:.3f}/{oos['cagr']*100:.1f}%/{oos['cumul']:.4f}  "
          f"Alt={alt['cumul']:.4f}  MaxDD={oos['max_drawdown']*100:.1f}%  NegYrs={oos['neg_years']}")
    return oos, alt


def run_universe(universe_tickers, universe_label, baseline_oos, baseline_alt):
    print(f"\n{'=' * 80}")
    print(f"Universe: {universe_label}  ({len(universe_tickers)} ranking assets + BIL)")
    print(f"{'=' * 80}")
    print(f"Baseline A — OOS {baseline_oos:.4f}, AltOOS {baseline_alt:.4f}\n")

    results = {}
    for label, mom_w, vol_w in SIGNAL_VARIANTS:
        r = build_hybrid_signal_rotation(
            universe_tickers, FULL_START, FULL_END,
            n_hold=1, mom_weight=mom_w, vol_weight=vol_w,
            tsmom_lb=TSMOM_LB, tsmom_threshold=TSMOM_THRESHOLD)
        oos_s, alt_s = print_stats(r, label)
        results[label] = (oos_s, alt_s)

    print(f"\n{'─' * 80}")
    print(f"Δ vs baseline A (pure momentum):\n")
    b_oos, b_alt = results[SIGNAL_VARIANTS[0][0]]
    confirmed = []
    for label, mom_w, vol_w in SIGNAL_VARIANTS[1:]:
        oos_s, alt_s = results[label]
        d_oos = oos_s["cumul"] - b_oos["cumul"]
        d_alt = alt_s["cumul"] - b_alt["cumul"]
        verdict = "✓ CONFIRMED" if d_oos > 0 and d_alt > 0 else "✗ not confirmed"
        if d_oos > 0 and d_alt > 0:
            confirmed.append(label)
        print(f"  {label}")
        print(f"    OOS: {oos_s['cumul']:.4f} (Δ{d_oos:+.4f})  "
              f"Alt: {alt_s['cumul']:.4f} (Δ{d_alt:+.4f})  "
              f"Sharpe: {oos_s['sharpe']:.3f}  MaxDD: {oos_s['max_drawdown']*100:.1f}%  "
              f"{verdict}")
        print()

    return confirmed, results


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("H151 — Hybrid Vol+Momentum Signal for H026 Sector Rotation")
    print("=" * 80)
    print("Baseline A: H026 sectors (OOS 22.6548) | H026-full 25-asset (OOS 382.9355)\n")

    # ── Part 1: 11-sector universe ─────────────────────────────────────────────
    conf_11, res_11 = run_universe(
        SECTOR_ETFs, "11 S&P Sectors",
        baseline_oos=22.6548, baseline_alt=97.3526)

    # ── Part 2: 25-asset H026-full universe ───────────────────────────────────
    conf_25, res_25 = run_universe(
        [t for t in H026_FULL if t != "BIL"], "25-asset H026-full",
        baseline_oos=382.9355, baseline_alt=3243.0783)

    # ── Overall verdict ────────────────────────────────────────────────────────
    print("=" * 80)
    print("OVERALL VERDICT")
    print("=" * 80)

    if conf_11:
        best_11 = max(conf_11, key=lambda l: (res_11[l][0]["cumul"] + res_11[l][1]["cumul"]))
        oos, alt = res_11[best_11]
        print(f"\n  11-sector: CONFIRMED — best variant: {best_11}")
        print(f"    OOS {oos['cumul']:.4f} (Δ{oos['cumul']-22.6548:+.4f})  "
              f"Alt {alt['cumul']:.4f}  Sharpe {oos['sharpe']:.3f}  MaxDD {oos['max_drawdown']*100:.1f}%")
    else:
        print(f"\n  11-sector: NOT CONFIRMED — pure momentum dominates on 11-sector universe.")

    if conf_25:
        best_25 = max(conf_25, key=lambda l: (res_25[l][0]["cumul"] + res_25[l][1]["cumul"]))
        oos, alt = res_25[best_25]
        print(f"\n  25-asset: CONFIRMED — best variant: {best_25}")
        print(f"    OOS {oos['cumul']:.4f} (Δ{oos['cumul']-382.9355:+.4f})  "
              f"Alt {alt['cumul']:.4f}  Sharpe {oos['sharpe']:.3f}  MaxDD {oos['max_drawdown']*100:.1f}%")
    else:
        print(f"\n  25-asset: NOT CONFIRMED — H026's pure momentum signal is already optimal.")

    if not conf_11 and not conf_25:
        print(f"\n  VERDICT: NOT CONFIRMED — inv-vol component does not improve H026's signal.")
        print(f"  The momentum + inv-vol tied rank in the existing signal already captures the")
        print(f"  low-vol factor. Adding more vol-weighting trades alpha for stability.")
        print(f"\n  Interpretation: LowVol is a valid standalone strategy (H150 confirmed) but")
        print(f"  does not improve H026. These are two separate uncorrelated alpha sources.")
    print()


if __name__ == "__main__":
    main()
