"""
H295 — Factor MAX ETF Rotation (SSRN 6053114)
==============================================
Paper: Wang & Zeng (Dec 2025), "Factor MAX and Predictable Factor Returns"

Signal: The maximum single-day return of an ETF in the prior calendar month
predicts positive next-month return. Factors (ETFs) with the highest prior-month
MAX daily return outperform those with the lowest.

Paper result: 0.32%/month spread (t=5.89) on 172 academic factors, 1963-2023.
NOT subsumed by factor momentum. Mechanism: underreaction to extreme factor-level news.

Universe: 23-asset (H026-full minus USO/UNG — commodity futures with structral issues)
Signal:   max(daily_pct_change) in prior month for each ETF
Rebalance: monthly (first trading day of each month)

Variants:
  A) Standalone MAX, top-1, no filter
  B) Standalone MAX, top-1, TSMOM-12 > 0% filter (BIL safe harbor)
  C) Blend 50/50: rank(mom_12m) + rank(MAX), top-1, TSMOM > 0% filter
  D) Blend 70/30: 0.7*rank(mom_12m) + 0.3*rank(MAX), top-1, TSMOM > 0% filter
  E) H026 baseline: rank(mom_12m) only, top-1, TSMOM > 0% filter  [comparison]

IS:  2008-01-01 to 2017-12-31
OOS: 2018-01-01 to 2026-05-31
Gate: OOS Sharpe > 1.5  (realistic for ETF-level vs academic factor-level signal)
      Blend variants gate: OOS Sharpe > H026 baseline on same period
"""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

INITIAL_EQUITY = 100_000.0
CACHE_DIR  = Path(__file__).parent.parent / "cache" / "h295"
RESULT_DIR = Path(__file__).parent.parent / "results"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FULL_START = "2003-01-01"
FULL_END   = "2026-05-31"
IS_START   = "2008-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"

# 25-asset H026-full universe, minus USO (negative price 2020) and UNG (extreme contango)
UNIVERSE = [
    "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC",  # sectors
    "GLD", "SLV", "DBC", "DBA", "GDX",                                                  # commodities
    "TLT", "IEF", "TIP", "AGG",                                                         # bonds
    "EWZ", "IBB",                                                                        # equity alts
    "BIL",                                                                               # safe harbor
]
SAFE_HARBOR = "BIL"

# ─────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────

def _cache_key(tickers: list, start: str, end: str) -> str:
    key = "_".join(sorted(tickers)) + f"_{start}_{end}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def fetch_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"prices_{_cache_key(tickers, start, end)}.parquet"
    if cp.exists():
        print("  [cache hit]")
        return pd.read_parquet(cp)
    print(f"  Downloading {len(tickers)} tickers …")
    raw = yf.download(tickers, start=start, end=end, auto_adjust=True, progress=False)
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    closes = closes.dropna(how="all")
    closes.to_parquet(cp)
    return closes


# ─────────────────────────────────────────────
# Stats
# ─────────────────────────────────────────────

def calc_stats(eq: pd.Series, label: str = "") -> dict:
    if len(eq) < 10:
        return {"error": "insufficient data"}
    eq = eq.dropna()
    rets = eq.pct_change().dropna()
    n_years = (eq.index[-1] - eq.index[0]).days / 365.25
    if n_years <= 0:
        return {"error": "zero duration"}
    cagr    = (eq.iloc[-1] / eq.iloc[0]) ** (1 / n_years) - 1
    vol     = rets.std() * np.sqrt(252)
    sharpe  = cagr / vol if vol > 0 else 0
    dd      = (eq / eq.expanding().max() - 1).min()
    neg_yrs = sum(
        1 for yr, grp in rets.groupby(rets.index.year)
        if (1 + grp).prod() - 1 < 0
    )
    return {
        "cagr":     round(float(cagr),   4),
        "sharpe":   round(float(sharpe),  4),
        "max_dd":   round(float(dd),      4),
        "ann_vol":  round(float(vol),     4),
        "n_years":  round(float(n_years), 1),
        "neg_yrs":  neg_yrs,
    }


def monthly_equity(px_daily: pd.DataFrame, signals: pd.DataFrame,
                   start: str, end: str, top_n: int = 1) -> pd.Series:
    """
    Build equity curve given a monthly signal DataFrame.
    signals: index = month-end dates, columns = tickers, values = rank score (higher = better)
    top_n:   number of ETFs to hold (equal weight)
    """
    px = px_daily.loc[start:end]
    monthly_dates = signals.loc[start:end].index

    equity = INITIAL_EQUITY
    series = []

    for i in range(1, len(monthly_dates)):
        prev_month_end = monthly_dates[i - 1]
        this_month_end = monthly_dates[i]

        row = signals.loc[prev_month_end].dropna()
        if len(row) == 0:
            continue

        hold = list(row.nlargest(top_n).index)
        weight = 1.0 / len(hold)

        sub = px[hold].loc[
            prev_month_end + pd.Timedelta(days=1):this_month_end
        ]
        if len(sub) < 2:
            continue

        for j in range(1, len(sub)):
            port_ret = 0.0
            for sym in hold:
                p0 = float(sub[sym].iloc[j - 1])
                p1 = float(sub[sym].iloc[j])
                if p0 > 0 and not (np.isnan(p0) or np.isnan(p1)):
                    port_ret += weight * (p1 / p0 - 1)
            equity *= (1 + port_ret)
            series.append((sub.index[j], equity))

    if not series:
        return pd.Series(dtype=float)

    return pd.Series(
        [v for _, v in series],
        index=pd.DatetimeIndex([d for d, _ in series])
    )


# ─────────────────────────────────────────────
# Signal construction
# ─────────────────────────────────────────────

def build_signals(px: pd.DataFrame) -> dict:
    """
    Returns a dict of signal DataFrames:
      'max_signal':  MAX daily return in prior month (raw)
      'mom_12m':     12-month momentum
      'mom_rank':    cross-sectional rank of mom_12m (0–1 scale)
      'max_rank':    cross-sectional rank of max_signal (0–1 scale)
    """
    # Monthly last-close prices
    monthly_px = px.resample("ME").last()

    # 12-month momentum (skip 0)
    mom_12m = monthly_px / monthly_px.shift(12) - 1

    # Factor MAX: max daily pct-change in each prior calendar month
    daily_rets = px.pct_change()
    max_daily = daily_rets.resample("ME").max()

    # Cross-sectional ranks (pct=True → 0 to 1)
    mom_rank = mom_12m.rank(axis=1, pct=True)
    max_rank = max_daily.rank(axis=1, pct=True)

    return {
        "monthly_px": monthly_px,
        "mom_12m":    mom_12m,
        "max_daily":  max_daily,
        "mom_rank":   mom_rank,
        "max_rank":   max_rank,
    }


def apply_tsmom_filter(score_row: pd.Series, mom_row: pd.Series,
                       threshold: float = 0.0) -> pd.Series:
    """Zero out score for ETFs below TSMOM threshold. Keeps BIL always available."""
    mask = (mom_row >= threshold) | (score_row.index == SAFE_HARBOR)
    return score_row.where(mask, other=np.nan)


# ─────────────────────────────────────────────
# Variant builders
# ─────────────────────────────────────────────

def variant_score(signals: dict, variant: str) -> pd.DataFrame:
    mom_rank = signals["mom_rank"]
    max_rank = signals["max_rank"]
    mom_12m  = signals["mom_12m"]
    tickers  = [t for t in UNIVERSE if t in mom_rank.columns]

    if variant == "A":
        # Standalone MAX, no filter
        score = max_rank[tickers].copy()

    elif variant == "B":
        # Standalone MAX, TSMOM > 0% filter
        score = max_rank[tickers].copy()
        for dt in score.index:
            if dt in mom_12m.index:
                score.loc[dt] = apply_tsmom_filter(
                    score.loc[dt], mom_12m.loc[dt, tickers], threshold=0.0
                )

    elif variant == "C":
        # Blend 50/50, TSMOM > 0% filter
        score = 0.5 * mom_rank[tickers] + 0.5 * max_rank[tickers]
        for dt in score.index:
            if dt in mom_12m.index:
                score.loc[dt] = apply_tsmom_filter(
                    score.loc[dt], mom_12m.loc[dt, tickers], threshold=0.0
                )

    elif variant == "D":
        # Blend 70/30 (momentum-dominant), TSMOM > 0% filter
        score = 0.7 * mom_rank[tickers] + 0.3 * max_rank[tickers]
        for dt in score.index:
            if dt in mom_12m.index:
                score.loc[dt] = apply_tsmom_filter(
                    score.loc[dt], mom_12m.loc[dt, tickers], threshold=0.0
                )

    elif variant == "E":
        # Baseline: momentum only, TSMOM > 0% filter
        score = mom_rank[tickers].copy()
        for dt in score.index:
            if dt in mom_12m.index:
                score.loc[dt] = apply_tsmom_filter(
                    score.loc[dt], mom_12m.loc[dt, tickers], threshold=0.0
                )

    else:
        raise ValueError(f"Unknown variant: {variant}")

    return score


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    print("\n══ H295 — Factor MAX ETF Rotation ══")
    print(f"Universe: {len(UNIVERSE)} assets")
    print(f"IS: {IS_START} → {IS_END}  |  OOS: {OOS_START} → {FULL_END}\n")

    # Fetch data
    px = fetch_prices(UNIVERSE, FULL_START, FULL_END)
    print(f"  Prices loaded: {px.shape[0]} days × {px.shape[1]} tickers")

    available = [t for t in UNIVERSE if t in px.columns]
    px = px[available]

    # Build signals
    signals = build_signals(px)
    print(f"  Monthly signal dates: {len(signals['monthly_px'])}")

    # SPY buy-and-hold benchmark (download separately)
    spy_raw = yf.download("SPY", start=FULL_START, end=FULL_END, auto_adjust=True, progress=False)
    spy_px  = spy_raw["Close"].squeeze() if "Close" in spy_raw.columns else spy_raw.iloc[:, 0]
    spy_is  = calc_stats(spy_px.loc[IS_START:IS_END])
    spy_oos = calc_stats(spy_px.loc[OOS_START:])

    variants = {
        "A: MAX standalone (no filter)":       ("A", 1),
        "B: MAX standalone (TSMOM>0% filter)": ("B", 1),
        "C: Blend 50/50 (TSMOM>0% filter)":   ("C", 1),
        "D: Blend 70/30 (TSMOM>0% filter)":   ("D", 1),
        "E: Momentum baseline (TSMOM>0%)":     ("E", 1),
    }

    results = {}
    print("\n── Results ──────────────────────────────────────────────────────────\n")

    for label, (vcode, top_n) in variants.items():
        score = variant_score(signals, vcode)

        eq_is  = monthly_equity(px, score, IS_START,  IS_END,    top_n)
        eq_oos = monthly_equity(px, score, OOS_START, FULL_END,  top_n)

        is_r  = calc_stats(eq_is,  label + " IS")
        oos_r = calc_stats(eq_oos, label + " OOS")

        results[label] = {"is": is_r, "oos": oos_r}

        print(f"  {label}")
        print(f"    IS  Sharpe={is_r.get('sharpe','?'):.3f}  CAGR={is_r.get('cagr',0):.1%}  MaxDD={is_r.get('max_dd',0):.1%}")
        print(f"    OOS Sharpe={oos_r.get('sharpe','?'):.3f}  CAGR={oos_r.get('cagr',0):.1%}  MaxDD={oos_r.get('max_dd',0):.1%}  NegYrs={oos_r.get('neg_yrs','?')}")
        print()

    # SPY benchmark
    print(f"  SPY buy-and-hold")
    print(f"    IS  Sharpe={spy_is.get('sharpe','?'):.3f}  CAGR={spy_is.get('cagr',0):.1%}  MaxDD={spy_is.get('max_dd',0):.1%}")
    print(f"    OOS Sharpe={spy_oos.get('sharpe','?'):.3f}  CAGR={spy_oos.get('cagr',0):.1%}  MaxDD={spy_oos.get('max_dd',0):.1%}")

    # Gate evaluation
    STANDALONE_GATE = 1.5
    baseline_oos_sharpe = results["E: Momentum baseline (TSMOM>0%)"]["oos"].get("sharpe", 0)

    print("\n── Gate Evaluation ──────────────────────────────────────────────────")
    print(f"  Standalone gate: OOS Sharpe > {STANDALONE_GATE}")
    print(f"  Blend gate:      OOS Sharpe > baseline ({baseline_oos_sharpe:.3f})\n")

    for label, data in results.items():
        oos_sharpe = data["oos"].get("sharpe", 0)
        if "MAX standalone" in label:
            gate = STANDALONE_GATE
            passed = oos_sharpe > gate
        elif "baseline" in label:
            continue
        else:
            gate = baseline_oos_sharpe
            passed = oos_sharpe > gate
        status = "PASS ✓" if passed else "FAIL ✗"
        print(f"  {label}: OOS Sharpe {oos_sharpe:.3f} vs gate {gate:.3f} → {status}")

    # Save results
    output = {
        "hypothesis": "H295",
        "title": "Factor MAX ETF Rotation",
        "source": "Wang & Zeng (Dec 2025), SSRN 6053114",
        "universe": available,
        "is_period": f"{IS_START} – {IS_END}",
        "oos_period": f"{OOS_START} – {FULL_END}",
        "standalone_gate": STANDALONE_GATE,
        "blend_gate": f"OOS Sharpe > momentum baseline ({baseline_oos_sharpe:.3f})",
        "variants": results,
        "spy": {"is": spy_is, "oos": spy_oos},
    }

    out_path = RESULT_DIR / "h295_results.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved → {out_path}")


if __name__ == "__main__":
    main()
