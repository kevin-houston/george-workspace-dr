#!/usr/bin/env python3
"""
H470 CORRECTED (H506 follow-up, 2026-08-13) — S3 (H411-B value×drift) signal now
shift(1)'d before use, fixing the look-ahead bias identified in H506. All other
logic identical to run_h470_design_choice_momentum_h198.py.

H470 — ML Design Choice Momentum: Monthly Best-Variant Selection on H198 Family

Source: SSRN:5031755 (Chen, Hanauer, Kalsbach, Feb 2026)
        "Design choices, machine learning, and the cross-section of stock returns"

Hypothesis: Chen et al. document that ML model design choices exhibit momentum — going
long configurations that performed best over trailing 3-12 months delivers statistically
significant returns. Applied to the H198 family: we have confirmed variants with different
OOS Sharpes (H376=3.120, H411-B confirmed, H217=1.559, H198=1.174). A meta-selector picks
the best-performing variant over trailing 3/6/12 months and uses that variant's signal for
the coming month. This tests whether design-choice momentum extends to monthly-rebalanced
stock-selection strategies.

Pool (4 constituent strategies on the same 30-stock NASDAQ universe):
  S1: H198 representative — 6-1m momentum, top-1 equal-weight
  S2: H376 best — 6-0m no-skip momentum, top-6 equal-weight
  S3: H411-B — pure value (1/price ranked) × 20d drift gate, top-2
  S4: H217 representative — alpha101 median, top-6 equal-weight

Meta-selector variants:
  A: 3-month trailing Sharpe meta-selector (pick best of S1-S4)
  B: 6-month trailing Sharpe meta-selector
  C: 12-month trailing Sharpe meta-selector
  D: Ensemble — equal-weight top-2 by 6m trailing Sharpe
  E: S2 (H376 static baseline, 6-0m top-6) — sanity check

IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe >= 3.120 (H376 static) AND MaxDD improvement vs -8.4%

Known risk: 3-month window = only 3 monthly observations (vs 60+ daily in SSRN paper).
Short Sharpe estimates will be very noisy. Null result is plausible and meaningful.
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

UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

DATA_START      = "2011-01-01"
DATA_END        = "2026-06-30"
IS_START        = pd.Timestamp("2013-01-01")
IS_END          = pd.Timestamp("2020-12-31")
OOS_START       = pd.Timestamp("2021-01-01")
OOS_END         = pd.Timestamp("2026-06-30")
GATE_SHARPE     = 3.120   # H376 static baseline
GATE_MAXDD_REF  = -0.084  # H376 static baseline MaxDD; improvement = less negative
DRIFT_THRESHOLD = 0.60


# ── Price loading (reuse H411/H376 cache) ─────────────────────────────────────

def fetch_daily(ticker: str) -> pd.Series:
    for prefix in ["h409", "h411", "h376", "h198"]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            s = pd.read_parquet(cp).squeeze()
            s.name = ticker
            return s
    cp = CACHE_DIR / f"h470_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"]
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h376", "h373", "h411", "h198"]:
        for end in [DATA_END, "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    # Fallback: resample daily
    s_d = fetch_daily(ticker)
    s = s_d.resample("ME").last()
    s.name = ticker
    cp = CACHE_DIR / f"h470_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


# ── Metrics ───────────────────────────────────────────────────────────────────

def sharpe(r: pd.Series) -> float:
    if len(r) < 2 or r.std() == 0:
        return 0.0
    return float(r.mean() / r.std() * np.sqrt(12))


def maxdd(r: pd.Series) -> float:
    wealth = (1 + r).cumprod()
    peak   = wealth.cummax()
    dd     = (wealth - peak) / peak
    return float(dd.min())


def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    neg = int(sum(r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0))
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "maxdd":   round(maxdd(r), 3),
        "cagr":    round(float(r.mean() * 12), 3),
        "neg_yrs": neg,
    }


# ── Constituent strategy return series ────────────────────────────────────────

def strategy_s1_momentum_6_1_top1(monthly_px: pd.DataFrame) -> pd.Series:
    """H198 representative: 6-1m momentum, top-1."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < 8:
            continue
        # 6-1m: price t-7 to t-1 (skip most recent month)
        p_start = monthly_px.iloc[loc - 7]
        p_end   = monthly_px.iloc[loc - 1]
        mom     = (p_end / p_start - 1).dropna()
        if mom.empty:
            continue
        selected = [mom.idxmax()]
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def strategy_s2_momentum_6_0_top6(monthly_px: pd.DataFrame) -> pd.Series:
    """H376 best: 6-0m no-skip momentum, top-6 equal-weight."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < 7:
            continue
        # 6-0m: price t-6 to t (use month-end price itself, no skip)
        p_start = monthly_px.iloc[loc - 6]
        p_end   = monthly_px.iloc[loc]
        mom     = (p_end / p_start - 1).dropna()
        if len(mom) < 6:
            continue
        selected = mom.nlargest(6).index.tolist()
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def strategy_s3_value_drift_top2(
    monthly_px: pd.DataFrame, daily_px: pd.DataFrame
) -> pd.Series:
    """H411-B: pure value (1/price ranked) × 20d drift gate, top-2."""
    monthly_ret = monthly_px.pct_change()
    # Drift gate: fraction of positive days over trailing 20
    daily_ret = daily_px.pct_change()
    pos_20    = (daily_ret > 0).rolling(20).sum() / 20
    gate_mly  = pos_20.resample("ME").last()
    gate_mly  = gate_mly.reindex(monthly_px.index, method="ffill")
    gate_mask = gate_mly.gt(DRIFT_THRESHOLD).astype(float)

    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    signal     = (rank_value * gate_mask).shift(1)  # H506 fix: signal must be knowable BEFORE month_end

    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        loc    = monthly_ret.index.get_loc(month_end)
        scores = signal.loc[month_end].dropna()
        pool   = scores[scores > 1e-6]   # 0 in gate-off months → no trade
        if pool.empty:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(2, len(pool))).index.tolist()
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def strategy_s4_alpha101_top6(monthly_px: pd.DataFrame, daily_px: pd.DataFrame) -> pd.Series:
    """H217 representative: alpha101 median aggregation, top-6 EW."""
    # alpha101 = (close - open) / (0.001 + high - low)
    # We only have close prices → approximate with daily return as proxy for
    # intraday price action: use daily_ret as stand-in for (close - open) / range
    # This is a best-effort approximation since OHLCV cache isn't always available.
    monthly_ret = monthly_px.pct_change()

    # Alpha101 via daily return as proxy (Kakushadze 2015)
    # Better approximation: use abs(daily_ret) as denominator proxy
    daily_ret    = daily_px.pct_change()
    abs_ret      = daily_ret.abs().replace(0, 0.001)
    alpha_daily  = daily_ret / abs_ret           # sign: +1 (up), -1 (down)
    alpha_monthly = alpha_daily.resample("ME").median()
    alpha_monthly = alpha_monthly.reindex(monthly_px.index, method="ffill")

    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        loc    = monthly_ret.index.get_loc(month_end)
        scores = alpha_monthly.loc[month_end].dropna().rank(pct=True)
        if len(scores) < 6:
            continue
        selected = scores.nlargest(6).index.tolist()
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Meta-selector ─────────────────────────────────────────────────────────────

def meta_selector(
    strategy_rets: dict,          # {"S1": pd.Series, ...}
    lookback: int,                # trailing months for Sharpe estimation
    top_k: int = 1,              # 1 = pick best; 2 = EW top-2
) -> pd.Series:
    """
    Each month t: compute trailing Sharpe over [t-lookback, t-1] for each strategy.
    Select top_k strategies by trailing Sharpe; portfolio return = EW average of
    selected strategies' return at month t.
    """
    all_months = sorted(set.union(*[set(s.index) for s in strategy_rets.values()]))
    all_months = pd.DatetimeIndex(all_months)
    all_months = all_months[all_months >= IS_START]

    combined = pd.DataFrame(strategy_rets).reindex(all_months).fillna(0.0)

    port_rets = []
    for i, month_end in enumerate(all_months):
        if i < lookback:
            continue
        trailing = combined.iloc[i - lookback: i]   # lookback months ending BEFORE t
        if len(trailing) < max(3, lookback // 2):
            continue
        t_sharpe = {
            name: sharpe(trailing[name])
            for name in combined.columns
        }
        ranked = sorted(t_sharpe, key=t_sharpe.__getitem__, reverse=True)
        selected = ranked[:top_k]
        ret_t = combined.iloc[i][selected].mean()
        port_rets.append((month_end, float(ret_t)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H470 — ML Design Choice Momentum: Monthly Best-Variant Selection")
    print("=" * 70)
    print(f"Source: SSRN:5031755 | Gate: OOS Sharpe >= {GATE_SHARPE} (H376 static)")

    print("\nLoading prices…")
    daily_list, monthly_list = [], []
    for t in UNIVERSE:
        try:
            sd = fetch_daily(t)
            sm = fetch_monthly(t)
            if sd is not None and sm is not None:
                daily_list.append(sd)
                monthly_list.append(sm)
        except Exception as e:
            print(f"  Warning: {t} load failed: {e}")

    daily_px   = pd.DataFrame(daily_list).T.sort_index()
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]

    # Align columns
    cols = sorted(set(daily_px.columns) & set(monthly_px.columns))
    daily_px   = daily_px[cols]
    monthly_px = monthly_px[cols]
    print(f"  {len(cols)} tickers, {len(daily_px)} daily rows, {len(monthly_px)} monthly rows")

    # Truncate to DATA_END
    daily_px   = daily_px[daily_px.index <= DATA_END]
    monthly_px = monthly_px[monthly_px.index <= DATA_END]

    print("\nComputing constituent strategy return series…")
    print("  S1: H198 rep — 6-1m momentum top-1")
    s1 = strategy_s1_momentum_6_1_top1(monthly_px)
    print(f"      {len(s1)} monthly obs  Sharpe_all={sharpe(s1):.3f}")

    print("  S2: H376 best — 6-0m no-skip top-6")
    s2 = strategy_s2_momentum_6_0_top6(monthly_px)
    print(f"      {len(s2)} monthly obs  Sharpe_all={sharpe(s2):.3f}")

    print("  S3: H411-B — value×drift gate top-2")
    s3 = strategy_s3_value_drift_top2(monthly_px, daily_px)
    print(f"      {len(s3)} monthly obs  Sharpe_all={sharpe(s3):.3f}")

    print("  S4: H217 rep — alpha101 proxy top-6")
    s4 = strategy_s4_alpha101_top6(monthly_px, daily_px)
    print(f"      {len(s4)} monthly obs  Sharpe_all={sharpe(s4):.3f}")

    strategy_rets = {"S1": s1, "S2": s2, "S3": s3, "S4": s4}

    # Cross-strategy correlations (OOS only)
    print("\nCross-strategy OOS correlations:")
    oos_df = pd.DataFrame(strategy_rets)
    oos_df = oos_df[(oos_df.index >= OOS_START) & (oos_df.index <= OOS_END)]
    print(oos_df.corr().round(3).to_string())

    print("\nRunning meta-selector variants…")
    variants_def = {
        "A": dict(lookback=3,  top_k=1, desc="3m trailing Sharpe, pick best"),
        "B": dict(lookback=6,  top_k=1, desc="6m trailing Sharpe, pick best"),
        "C": dict(lookback=12, top_k=1, desc="12m trailing Sharpe, pick best"),
        "D": dict(lookback=6,  top_k=2, desc="6m trailing Sharpe, EW top-2"),
        "E": dict(lookback=None,         desc="S2 static baseline (H376 6-0m top-6)"),
    }

    results = {}
    for vname, vdef in variants_def.items():
        if vdef.get("lookback") is None:
            rets = s2   # static H376 baseline
        else:
            rets = meta_selector(
                strategy_rets,
                lookback=vdef["lookback"],
                top_k=vdef["top_k"],
            )
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = (vo["sharpe"] >= GATE_SHARPE) and (vo["maxdd"] > GATE_MAXDD_REF)
        flag = " ✓ BEATS GATE" if beat else ""
        print(f"\n  Var {vname}: {vdef['desc']}")
        print(f"    IS  n={vi['n']}  Sharpe={vi['sharpe']:.3f}  MaxDD={vi['maxdd']:.3f}  "
              f"CAGR={vi['cagr']:.3f}  NegYrs={vi['neg_yrs']}")
        print(f"    OOS n={vo['n']}  Sharpe={vo['sharpe']:.3f}  MaxDD={vo['maxdd']:.3f}  "
              f"CAGR={vo['cagr']:.3f}  NegYrs={vo['neg_yrs']}{flag}")
        results[f"var_{vname}"] = {"is": vi, "oos": vo, "desc": vdef["desc"], "beats": beat}

    # Summary
    print("\n" + "=" * 70)
    confirmed_vars = [v for v, r in results.items() if r["beats"]]
    if confirmed_vars:
        best = max(results, key=lambda v: results[v]["oos"]["sharpe"])
        bsh  = results[best]["oos"]["sharpe"]
        bmdd = results[best]["oos"]["maxdd"]
        print(f"CONFIRMED — best {best}  OOS Sharpe {bsh:.3f}  MaxDD {bmdd:.3f}")
        print(f"Design-choice momentum extends to monthly rebalanced H198-family strategies.")
        confirmed = True
    else:
        best = max(results, key=lambda v: results[v]["oos"]["sharpe"])
        bsh  = results[best]["oos"]["sharpe"]
        bmdd = results[best]["oos"]["maxdd"]
        print(f"NOT CONFIRMED — best Var {best[-1]}  OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        if bsh < results["var_E"]["oos"]["sharpe"]:
            print("Meta-selectors UNDERPERFORM static H376 baseline — switching costs hurt.")
        elif bsh >= results["var_E"]["oos"]["sharpe"]:
            print("Meta-selectors match but don't surpass static baseline.")
        print("\nLikely causes:")
        print("  1. 3-12 monthly obs = noisy trailing Sharpe (SSRN paper uses ~60 daily obs)")
        print("  2. High constituent correlation → switching is noise, not alpha")
        print("  3. S3 (H411-B) dominates pool → static H411-B would beat meta-selector")
        confirmed = False
        confirmed_vars = []

    print(f"\nGate: OOS Sharpe >= {GATE_SHARPE}  MaxDD > {GATE_MAXDD_REF:.1%}")
    print(f"Baseline (Var E / H376 static): OOS Sharpe={results['var_E']['oos']['sharpe']:.3f}  "
          f"MaxDD={results['var_E']['oos']['maxdd']:.3f}")

    out = {
        "hypothesis": "H470",
        "gate":       {"sharpe": GATE_SHARPE, "maxdd_ref": GATE_MAXDD_REF},
        "confirmed":  confirmed,
        "confirmed_variants": [v.replace("var_", "") for v in confirmed_vars],
        "results":    results,
    }
    outpath = RESULT_DIR / "h470_corrected_results.json"
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nResults saved → {outpath}")


if __name__ == "__main__":
    main()
