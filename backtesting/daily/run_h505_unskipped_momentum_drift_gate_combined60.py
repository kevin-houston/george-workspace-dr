"""
H505 — Unskipped (12-0) Momentum as a Component in the H417/H411 Drift-Gated
             Value Signal, Combined-60 Universe
=============================================================================
H492/H493 (CONFIRMED, 2026-08-05) found that unskipped 12-0 trailing momentum
robustly beats the standard 12-1 skip-month convention as a STANDALONE
cross-sectional momentum signal on both the H198 30-stock and H417 combined-60
universes (combined-60 12-0 OOS Sharpe 3.178 vs 12-1's 1.157). Both hypotheses
explicitly recommended, as the natural next step, applying the 12-0 window
to the higher-Sharpe PRODUCTION-ADJACENT signal families (H411/H417) rather
than committing to production from the standalone 30-stock reference alone.
That follow-up has not been run until now.

H417's own champion (Var C, combined-60, OOS Sharpe 5.855) is NOT standalone
momentum — it's H411's "1/price rank x 20d drift gate" signal (buy the
cheapest stocks currently in a 20d uptrend). This hypothesis asks: does
swapping in 12-0 momentum (as an additional rank component, or as an
alternative/combined gate) improve on that 5.855 champion, or is the existing
20d drift gate already capturing everything the momentum signal would add
(same redundancy H418 found for 12-1m momentum x drift gate = 4.513, barely
above drift-alone's 4.497)?

Variants (all on COMBINED_60, IS 2013-2020 / OOS 2021-2026):
  A: H417 Var C replication (1/price rank x 20d drift gate, top-3) [baseline]
  B: 1/price rank x 12-0 momentum gate (positive 12-0 return, instead of 20d drift)
  C: 1/price rank x (20d drift gate AND 12-0 momentum > 0)  [stacked gate]
  D: 0.5*(1/price rank) + 0.5*(12-0 momentum rank), x 20d drift gate [blended rank]
  E: 12-0 momentum rank ONLY, x 20d drift gate [replaces value component entirely]

Gate: OOS Sharpe > 5.855 (H417 Var C combined-60 champion) to beat; report
      against production gate (4.094, H500) as a secondary bar.
IS: 2013-2020   OOS: 2021-2026
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

NASDAQ_30 = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

SP500_NTECH = [
    "PG",  "KO",   "PEP",  "MO",   "PM",
    "MRK", "AMGN", "GILD", "MDT",  "BMY",
    "HON", "MMM",  "RTX",  "UPS",  "DE",
    "GS",  "MS",   "BLK",  "AXP",  "USB",
    "COP", "SLB",  "EOG",  "VLO",  "PSX",
    "MCD", "NKE",  "TGT",  "F",    "GM",
]

COMBINED_60 = NASDAQ_30 + SP500_NTECH

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 5.855   # H417 Var C combined-60 champion (primary bar)
PROD_GATE   = 4.094   # H500 production Sharpe (secondary/context bar)

TOP_N       = 3        # H417/H411 champion top_n
MOM_WINDOW  = 12       # 12-0 unskipped trailing window, per H492/H493


def fetch_daily(ticker: str) -> pd.Series:
    for prefix in ["h409", "h411", "h416", "h417", "h492", "h493", "h505"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            s = pd.read_parquet(cp).squeeze()
            s.name = ticker
            return s
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].dropna()
    s.name = ticker
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h505_{ticker}_daily_{DATA_START}_{DATA_END}.parquet")
    return s


def fetch_monthly(ticker: str, daily: pd.Series) -> pd.Series:
    s = daily.resample("ME").last()
    s.name = ticker
    return s


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3),
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean() * 12), 3),
            "neg_yrs": neg_years(r)}


def compute_drift_mask(daily_ret: pd.DataFrame, monthly_index, window=20, threshold=0.60):
    """20d drift gate — fraction of positive days > 60%, per H411/H417 convention."""
    pos_count = (daily_ret > 0).rolling(window).sum()
    drift_bool = (pos_count / window) > threshold
    drift_mly = drift_bool.resample("ME").last().astype(float)
    return drift_mly.reindex(monthly_index, method="ffill").fillna(0)


def compute_mom12_0(monthly_px: pd.DataFrame, window=MOM_WINDOW):
    """Unskipped 12-0 trailing momentum: (P_t / P_{t-12}) - 1, per H492/H493."""
    return monthly_px.pct_change(window)


def backtest(monthly_ret_index, monthly_ret, signal, top_n=3):
    port_rets = []
    for month_end in monthly_ret_index[monthly_ret_index >= IS_START]:
        scores = signal.loc[month_end].dropna() if month_end in signal.index else pd.Series(dtype=float)
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(top_n, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H505 — Unskipped (12-0) Momentum in H417/H411 Drift-Gated Value Signal, Combined-60")
    print("=" * 90)
    print(f"Primary gate: OOS Sharpe > {GATE_SHARPE} (H417 Var C champion)")
    print(f"Secondary/context bar: OOS Sharpe > {PROD_GATE} (H500 production)\n")

    print(f"Loading daily prices for {len(COMBINED_60)} tickers…")
    daily_cache = {}
    for t in COMBINED_60:
        try:
            s = fetch_daily(t)
            if s is not None and len(s) > 100:
                daily_cache[t] = s
        except Exception as e:
            print(f"  WARNING: {t} failed — {e}")
    tickers = [t for t in COMBINED_60 if t in daily_cache]
    print(f"  Loaded {len(tickers)} tickers\n")

    daily_px = pd.DataFrame({t: daily_cache[t] for t in tickers}).sort_index()
    monthly_px = pd.DataFrame({t: fetch_monthly(t, daily_cache[t]) for t in tickers}).sort_index().loc[DATA_START:]
    monthly_index = monthly_px.index
    monthly_ret = monthly_px.pct_change()
    daily_ret = daily_px.pct_change()

    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    drift_mask_20d = compute_drift_mask(daily_ret, monthly_index, window=20, threshold=0.60)

    mom12_0 = compute_mom12_0(monthly_px, window=MOM_WINDOW)
    mom_gate = (mom12_0 > 0).astype(float)
    mom_rank = mom12_0.rank(axis=1, pct=True)

    variants = {}

    # A: H417 Var C replication (1/price rank x 20d drift gate)
    variants["A_H417_replication"] = rank_value * drift_mask_20d

    # B: 1/price rank x 12-0 momentum gate (positive momentum instead of drift-fraction gate)
    variants["B_value_x_mom12_0_gate"] = rank_value * mom_gate

    # C: 1/price rank x (20d drift gate AND 12-0 momentum > 0)  [stacked gate]
    stacked_gate = drift_mask_20d * mom_gate
    variants["C_value_x_stacked_gate"] = rank_value * stacked_gate

    # D: blended rank (0.5 value + 0.5 momentum) x 20d drift gate
    blended_rank = 0.5 * rank_value + 0.5 * mom_rank
    variants["D_blended_rank_x_drift"] = blended_rank * drift_mask_20d

    # E: momentum rank ONLY x 20d drift gate (replaces value component)
    variants["E_mom_rank_x_drift"] = mom_rank * drift_mask_20d

    print(f"{'Var':<28} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Beats H417  Beats Prod")
    print("-" * 100)

    results = {}
    confirmed = []
    variant_rets = {}

    for label, signal in variants.items():
        rets = backtest(monthly_index, monthly_ret, signal.shift(1), top_n=TOP_N)
        variant_rets[label] = rets
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat_h417 = vo["sharpe"] > GATE_SHARPE
        beat_prod = vo["sharpe"] > PROD_GATE
        flag417 = " ✓" if beat_h417 else " ✗"
        flagprod = "     ✓" if beat_prod else "     ✗"
        print(f"{label:<28} {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {flag417}       {flagprod}")
        results[label] = {"is": vi, "oos": vo, "beats_h417": beat_h417, "beats_prod": beat_prod}
        if beat_h417:
            confirmed.append(label)

    # Correlation of best variant's OOS returns vs SPY, for production-blend context
    print("\nFetching SPY for correlation check…")
    try:
        spy_daily = fetch_daily("SPY")
        spy_monthly = fetch_monthly("SPY", spy_daily)
        spy_ret = spy_monthly.pct_change().reindex(monthly_index)
        best_label = max(results, key=lambda k: results[k]["oos"]["sharpe"])
        best_rets = variant_rets[best_label]
        common = best_rets.index.intersection(spy_ret.dropna().index)
        common = common[(common >= OOS_START) & (common <= OOS_END)]
        corr_spy = float(best_rets.loc[common].corr(spy_ret.loc[common])) if len(common) > 5 else None
    except Exception as e:
        print(f"  WARNING: SPY fetch/corr failed — {e}")
        best_label = max(results, key=lambda k: results[k]["oos"]["sharpe"])
        corr_spy = None

    print(f"\nBest variant: {best_label}  OOS Sharpe {results[best_label]['oos']['sharpe']:.3f}")
    print(f"Corr(SPY) OOS: {corr_spy}")

    # Annual breakdown for best variant
    print(f"\n=== {best_label} OOS annual returns ===")
    ann = variant_rets[best_label].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        tag = " <- OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    print(f"\n=== Verdict ===")
    print(f"Primary gate: OOS Sharpe > {GATE_SHARPE} (H417 champion)")
    if confirmed:
        print(f"CONFIRMED — variants beating H417 champion: {', '.join(confirmed)}")
    else:
        print(f"NOT CONFIRMED vs H417 champion — best {best_label} OOS {results[best_label]['oos']['sharpe']:.3f} < {GATE_SHARPE}")
        if results[best_label]["oos"]["sharpe"] > PROD_GATE:
            print(f"  (but beats production gate {PROD_GATE} — see secondary bar)")

    out = {
        "hypothesis": "H505",
        "primary_gate_h417_champion": GATE_SHARPE,
        "secondary_gate_production": PROD_GATE,
        "signal_family": "1/price value rank x drift/momentum gate, combined-60 universe",
        "confirmed_vs_h417": bool(confirmed),
        "confirmed_variants": confirmed,
        "best_variant": best_label,
        "best_oos_sharpe": results[best_label]["oos"]["sharpe"],
        "corr_spy_oos_best": corr_spy,
        "results": results,
    }
    op = RESULT_DIR / "h505_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {op}")
    return out


if __name__ == "__main__":
    main()
