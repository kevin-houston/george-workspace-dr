"""
H409: Drift-Regime-Gated Value+Reversal on H198 30-Stock Universe
==================================================================
Source: arXiv:2511.12490 (Nov 2025) -- 'Discovery of a 13-Sharpe OOS Factor:
Drift Regimes Unlock Hidden Cross-Sectional Predictability'

Key idea: Value and short-term reversal signals only fire when a stock is in
a 'drift regime' -- defined as >60% positive return days in trailing 63-day
(3-month) window. The regime gate selectively activates the signal,
producing OOS Sharpe 13.19 long-short on S&P 500.

H409 adapts this to our long-only production pipeline:
  1. drift_regime[i,t] = (positive_days_63d / 63) > 0.60
  2. BASE[i,t] = 0.7 * pct_rank(1/price) + 0.3 * pct_rank(-zscore(ret_10d))
  3. GATED[i,t] = BASE[i,t] * drift_regime[i,t]  (zero if not in regime)
  4. Variants blend GATED with H398A momentum signal or use as standalone

Gate: OOS Sharpe > 4.068 (H398A champion on H198 universe)
IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock NASDAQ large-cap

Variants:
  A: Pure GATED 63d signal, top-2
  B: 50/50 GATED + H398A momentum blend, top-2
  C: H398A momentum + drift_regime FILTER (fallback to unfiltered)
  D: Pure GATED 20d window, top-2
  E: Base value+reversal, NO regime gate [diagnostic]
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
GATE_SHARPE     = 4.068
DRIFT_WINDOW    = 63
DRIFT_THRESHOLD = 0.60
REVERSAL_WINDOW = 10
VALUE_WEIGHT    = 0.70
REVERSAL_WEIGHT = 0.30


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h409_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
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
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h398", "h395", "h393", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    daily = fetch_daily(ticker)
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
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean()*12), 3),
            "neg_yrs": neg_years(r)}


def backtest(monthly_px, signal, top_n=2, gated=False):
    """top-N monthly backtest; if gated=True only stocks with score>0 qualify."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = signal.loc[month_end].dropna()
        pool = scores[scores > 1e-6] if gated else scores
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(top_n, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def backtest_filter(monthly_px, momentum_signal, drift_mly, top_n=2):
    """Variant C: momentum pick, filter by regime, fallback to unfiltered."""
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = momentum_signal.loc[month_end].dropna()
        if len(scores) < top_n:
            port_rets.append((month_end, 0.0))
            continue
        candidates = scores.nlargest(top_n * 3).index.tolist()
        if month_end in drift_mly.index:
            row = drift_mly.loc[month_end]
            filtered = [t for t in candidates if row.get(t, 0) > 0.5]
        else:
            filtered = []
        selected = filtered[:top_n] if filtered else candidates[:top_n]
        loc = monthly_ret.index.get_loc(month_end)
        port_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def compute_h398a_signal(monthly_px):
    """IMOM6 + MOM60 + LowVol + IMOM12, equal-weight (H398A champion)."""
    r = monthly_px.pct_change()
    imom = lambda w: monthly_px.pct_change(w) - r.rolling(w).sum()
    ri6  = imom(6).rank(axis=1, pct=True)
    ri12 = imom(12).rank(axis=1, pct=True)
    rm60 = monthly_px.pct_change(6).rank(axis=1, pct=True)
    rlv  = (r.rolling(6).std() * np.sqrt(12)).rank(axis=1, pct=True, ascending=False)
    return 0.25*ri6 + 0.25*rm60 + 0.25*rlv + 0.25*ri12


def main():
    print("H409 — Drift-Regime-Gated Value+Reversal on H198 30-Stock Universe")
    print("=" * 72)
    print(f"Source: arXiv:2511.12490 | Gate: OOS Sharpe > {GATE_SHARPE}")

    print("\nLoading daily prices…")
    daily_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_daily(t)] if s is not None]
    ).T.sort_index()
    print(f"  {len(daily_px.columns)} tickers, {len(daily_px)} daily obs")

    print("Loading monthly prices…")
    monthly_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_monthly(t)] if s is not None]
    ).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # Drift regime
    print(f"Computing drift regime ({DRIFT_WINDOW}d and 20d windows)…")
    daily_ret = daily_px.pct_change()

    def drift_monthly(window):
        pos = (daily_ret > 0).rolling(window).sum()
        d   = (pos / window) > DRIFT_THRESHOLD
        m   = d.resample("ME").last().astype(float)
        return m.reindex(monthly_px.index, method="ffill")

    d63_mly = drift_monthly(DRIFT_WINDOW)
    d20_mly = drift_monthly(20)

    # Coverage stats
    oos_63  = d63_mly[d63_mly.index >= OOS_START]
    avg_pct = float(oos_63.mean().mean())
    avg_n   = float(oos_63.sum(axis=1).mean())
    print(f"  OOS 63d: {avg_pct:.1%} stock-months in regime | avg {avg_n:.1f}/{len(UNIVERSE)} per month")

    # Value signal: pct_rank(1/price)
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)

    # Reversal signal: pct_rank(-zscore(10d return))
    r10_mly   = daily_px.pct_change(REVERSAL_WINDOW).resample("ME").last()
    r10_mly   = r10_mly.reindex(monthly_px.index, method="ffill")
    r10_std   = r10_mly.std(axis=1).replace(0, np.nan)
    zscore_10 = r10_mly.sub(r10_mly.mean(axis=1), axis=0).div(r10_std, axis=0)
    rank_rev  = (-zscore_10).rank(axis=1, pct=True)

    # Base and gated signals
    base_sig  = VALUE_WEIGHT * rank_value + REVERSAL_WEIGHT * rank_rev
    gated_63  = base_sig.multiply(d63_mly.gt(0.5).astype(float))
    gated_20  = base_sig.multiply(d20_mly.gt(0.5).astype(float))

    # H398A and blend
    print("Computing H398A reference signal…")
    h398a_sig = compute_h398a_signal(monthly_px)
    blend_sig = 0.50 * gated_63 + 0.50 * h398a_sig

    # SPY
    spy_ret = fetch_monthly("SPY").pct_change().dropna()

    # References
    ref_rets = backtest(monthly_px, h398a_sig, top_n=2)
    ri = eval_period(ref_rets, IS_START, IS_END)
    ro = eval_period(ref_rets, OOS_START, OOS_END)
    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"\n=== References ===")
    print(f"H398A  IS {ri['sharpe']:.3f} | OOS {ro['sharpe']:.3f}  MaxDD {ro['maxdd']:.1%}  CAGR {ro['cagr']*100:.1f}%")
    print(f"SPY    IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    # Variants
    variant_rets = {
        "A": backtest(monthly_px, gated_63,   top_n=2, gated=True),
        "B": backtest(monthly_px, blend_sig,  top_n=2, gated=False),
        "C": backtest_filter(monthly_px, h398a_sig, d63_mly, top_n=2),
        "D": backtest(monthly_px, gated_20,   top_n=2, gated=True),
        "E": backtest(monthly_px, base_sig,   top_n=2, gated=False),
    }
    variant_desc = {
        "A": "Pure GATED 63d, top-2 (cash if no regime stocks)",
        "B": "50/50 GATED 63d + H398A momentum, top-2",
        "C": "H398A momentum + 63d regime FILTER (fallback=unfiltered)",
        "D": "Pure GATED 20d window, top-2",
        "E": "Base value+reversal, no regime gate [diagnostic]",
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 115)
    print(f"{'H398A':4} {ri['sharpe']:>7.3f} {ro['sharpe']:>8.3f} {ro['maxdd']:>9.1%} "
          f"{ro['cagr']*100:>6.1f}% {ro['neg_yrs']:>5d}  H398A reference")
    print()

    results = {"h398a_ref": {"is": ri, "oos": ro}, "spy": {"is": si, "oos": so}}
    confirmed = []

    for v, rets in variant_rets.items():
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS H398A" if beat else ""
        print(f"Var {v}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {variant_desc[v]}{flag}")
        results[f"var_{v}"] = {"is": vi, "oos": vo, "desc": variant_desc[v], "beats": beat}
        if beat:
            confirmed.append(v)

    best_v = max(variant_rets, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    print(f"\n=== Var {best_v} annual returns ===")
    ann = variant_rets[best_v].resample("YE").apply(lambda x: (1+x).prod()-1)
    for yr, ret in ann.items():
        print(f"  {yr.year}: {ret:+.1%}{' ← OOS' if yr.year >= 2021 else ''}")

    def cash_oos(rets):
        r = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        return f"{(r == 0.0).mean():.1%}"

    print(f"\nCash months OOS: Var A={cash_oos(variant_rets['A'])}  Var D={cash_oos(variant_rets['D'])}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE}")
    if confirmed:
        best_c = max(confirmed, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        print(f"CONFIRMED — variants: {', '.join(confirmed)}")
        print(f"Champion: Var {best_c}  OOS Sharpe {results[f'var_{best_c}']['oos']['sharpe']:.3f}")
    else:
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best_v}  OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        print("Long-only + 30 large-cap stocks: value (1/P) lacks discrimination; reversal")
        print("conflicts with momentum; regime gate doesn't recover enough alpha from L/S loss.")

    out = {
        "hypothesis": "H409", "gate": GATE_SHARPE,
        "regime_stats": {"avg_pct": avg_pct, "avg_n": avg_n},
        "confirmed": bool(confirmed), "confirmed_variants": confirmed,
        "results": results,
    }
    op = RESULT_DIR / "h409_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
