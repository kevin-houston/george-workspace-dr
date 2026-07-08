"""
H377: 6-0m No-Skip Momentum on H198 30-Stock Large-Cap Universe
================================================================
H376 confirmed that removing the skip month triples OOS Sharpe on the H198
universe (6-0m baseline OOS 3.120 vs 6-1m OOS 1.174). This hypothesis
fully tests the 6-0m signal across concentration levels and lookbacks.

Hypothesis: On tech-heavy large-cap universes, the 1-month reversal that
motivated the skip-month convention is absent or reversed — most-recent-month
return is signal, not noise.

Gate: OOS Sharpe > 1.174 AND MaxDD > -30%

Variants:
  A: 6-0m top-1       (concentrated, replicates H376 sub-finding)
  B: 6-0m top-2 EW    (slightly diversified)
  C: 6-0m top-3 EW    (moderate diversification)
  D: 12-0m top-1      (longer lookback, no skip)
  E: 3-0m  top-1      (short lookback, no skip)
  F: 6-0m top-1 + SPY 200MA overlay (H301-style safety net)

IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock
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

DATA_START  = "2011-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 1.174
GATE_MAXDD  = -0.30


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h376", "h373", "h198"]:
        for end in [DATA_END, "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    cp = CACHE_DIR / f"h377_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_spy_daily() -> pd.Series:
    for prefix in ["h376", "h373", "h198", "h026"]:
        for end in [DATA_END, "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_SPY_daily_{DATA_START}_{end}.parquet"
            if cp.exists():
                return pd.read_parquet(cp).squeeze()
    raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("SPY", axis=1, level=1)
    s = raw["Close"]
    s.name = "SPY"
    cp = CACHE_DIR / f"h377_SPY_daily_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def cagr_ann(r: pd.Series) -> float:
    return float(r.mean() * 12)

def neg_years(r: pd.Series) -> int:
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def eval_period(rets: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "maxdd":   round(maxdd(r), 3),
        "cagr":    round(cagr_ann(r), 3),
        "neg_yrs": neg_years(r),
    }


def backtest(
    monthly_px: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int,
    bil_mask: pd.Series = None,  # True → go to BIL (0% return) that month
) -> pd.Series:
    """Top-N equal-weight momentum portfolio, monthly rebalance."""
    monthly_ret = monthly_px.pct_change()
    port_rets   = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
        # If SPY 200MA overlay says cash, skip
        if bil_mask is not None and bil_mask.get(month_end, False):
            port_rets.append((month_end, 0.0))
            continue

        scores = signal.loc[month_end].dropna()
        if len(scores) < top_n:
            continue
        selected = scores.nlargest(top_n).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, float(ret_this)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H377 — 6-0m No-Skip Momentum on H198 30-Stock Large-Cap Universe")
    print("=" * 68)

    # Load monthly prices (reuse H376/H373 cache)
    print("\nLoading monthly prices (reusing H376 cache)…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # Momentum signals — various lookbacks, no skip
    # No-skip: pct_change(N) = month_t / month_(t-N) - 1  (includes current month)
    # Standard skip: shift(1)/shift(N+1) - 1              (excludes current month)
    sig_6_0  = monthly_px.pct_change(6)           # 6-0m no skip
    sig_12_0 = monthly_px.pct_change(12)          # 12-0m no skip
    sig_3_0  = monthly_px.pct_change(3)           # 3-0m no skip
    sig_6_1  = monthly_px.shift(1) / monthly_px.shift(7) - 1   # 6-1m (standard)

    rank_6_0  = sig_6_0.rank(axis=1, pct=True)
    rank_12_0 = sig_12_0.rank(axis=1, pct=True)
    rank_3_0  = sig_3_0.rank(axis=1, pct=True)
    rank_6_1  = sig_6_1.rank(axis=1, pct=True)

    # SPY 200MA mask for Var F
    print("Computing SPY 200MA mask for Var F…")
    spy_daily = fetch_spy_daily()
    spy_ma200 = spy_daily.rolling(200).mean()
    spy_monthly = spy_daily.resample("ME").last()
    spy_ma200_m = spy_ma200.resample("ME").last()
    spy_below_200 = (spy_monthly < spy_ma200_m).reindex(monthly_px.index).fillna(False)

    # SPY benchmark
    spy_cp = CACHE_DIR / "h198_SPY_monthly_2011-01-01_2026-04-30.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()

    # H198 baseline (6-1m top-1) for reference
    print("\n=== Baselines ===")
    base_6_1_top1 = backtest(monthly_px, rank_6_1, top_n=1)
    bi1 = eval_period(base_6_1_top1, IS_START, IS_END)
    bo1 = eval_period(base_6_1_top1, OOS_START, OOS_END)
    print(f"H198 baseline 6-1m top-1  IS {bi1['sharpe']:.3f} | OOS {bo1['sharpe']:.3f}  MaxDD {bo1['maxdd']:.1%}  NegYrs {bo1['neg_yrs']}")

    # ── Variants ─────────────────────────────────────────────────────────────
    variants = {
        "A": dict(signal=rank_6_0,  top_n=1, bil_mask=None,           desc="6-0m top-1 (no skip)"),
        "B": dict(signal=rank_6_0,  top_n=2, bil_mask=None,           desc="6-0m top-2 EW (no skip)"),
        "C": dict(signal=rank_6_0,  top_n=3, bil_mask=None,           desc="6-0m top-3 EW (no skip)"),
        "D": dict(signal=rank_12_0, top_n=1, bil_mask=None,           desc="12-0m top-1 (no skip)"),
        "E": dict(signal=rank_3_0,  top_n=1, bil_mask=None,           desc="3-0m top-1 (no skip)"),
        "F": dict(signal=rank_6_0,  top_n=1, bil_mask=spy_below_200,  desc="6-0m top-1 + SPY 200MA overlay"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 88)
    # Print baselines first
    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"{'base':4} {bi1['sharpe']:>7.3f} {bo1['sharpe']:>8.3f} {bo1['maxdd']:>9.1%} "
          f"{bo1['cagr']*100:>6.1f}% {bo1['neg_yrs']:>5d}  H198 6-1m top-1 (reference)")
    print(f"{'SPY':4} {si['sharpe']:>7.3f} {so['sharpe']:>8.3f} {so['maxdd']:>9.1%} "
          f"{so['cagr']*100:>6.1f}% {so['neg_yrs']:>5d}  SPY buy-and-hold")
    print()

    results = {
        "baseline_6_1_top1": {"is": bi1, "oos": bo1},
        "spy": {"is": si, "oos": so},
    }
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest(monthly_px, cfg["signal"], cfg["top_n"], cfg["bil_mask"])
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        pass_gate = vo["sharpe"] > GATE_SHARPE and vo["maxdd"] > GATE_MAXDD
        flag = " ✓ PASS" if pass_gate else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {
            "is": vi, "oos": vo, "desc": cfg["desc"], "pass_gate": pass_gate,
        }
        if pass_gate:
            confirmed_variants.append(var_id)

    # Yearly breakdown for Var A (the key result)
    print("\n=== Var A (6-0m top-1) annual returns ===")
    rets_a = backtest(monthly_px, rank_6_0, top_n=1)
    ann_a  = rets_a.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_a.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND MaxDD > {GATE_MAXDD:.0%}")
    confirmed = len(confirmed_variants) > 0
    if confirmed:
        print(f"CONFIRMED — variants passing gate: {', '.join(confirmed_variants)}")
        best_v = max(confirmed_variants,
                     key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"Best variant: {best_v}  OOS Sharpe {bsh:.3f}")
    else:
        best_v = max(variants.keys(),
                     key=lambda v: results.get(f"var_{v}", {}).get("oos", {}).get("sharpe", 0))
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best variant {best_v} OOS Sharpe {bsh:.3f}")

    out = {
        "hypothesis": "H377",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h377_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
