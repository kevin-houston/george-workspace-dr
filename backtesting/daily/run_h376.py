"""
H376: MAX Factor Composite on H198 Top-6 Selection (Cross-Sectional)
=====================================================================
H373 tested MAX tilt on top-1 and did not confirm. This hypothesis tests
whether MAX composite improves the TOP-6 (equal-weight) selection in H198,
comparing directly against H198's best result: 6-1m top-6 OOS Sharpe 1.174.

Rationale: Tandfonline 2025 shows high-MAX × high-momentum = +2.5%/month.
This effect may be better captured at the portfolio level (top-6 composite)
than in concentrated top-1, because the composite selects the intersection
of momentum AND lottery-premium stocks rather than gambling on a single winner.

Gate: OOS Sharpe > 1.174 AND MaxDD > -30%

Variants (top-6 equal-weight, monthly rebalance):
  A: composite rank = 0.7·mom_rank + 0.3·max_rank  (mild tilt)
  B: composite rank = 0.5·mom_rank + 0.5·max_rank  (equal blend)
  C: top-6 by momentum, drop any candidate with max_rank < 0.4 (quality gate),
     replace dropped with next momentum-ranked stock
  D: Var A with 6-0m momentum (no skip month, following H277 finding that
     skip-month hurts on tech-heavy universes)

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
TOP_N       = 6
GATE_SHARPE = 1.174
GATE_MAXDD  = -0.30


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 374)]:
        for end in ["2026-04-30", DATA_END]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    cp = CACHE_DIR / f"h373_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    cp2 = CACHE_DIR / f"h376_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp2.exists():
        return pd.read_parquet(cp2).squeeze()
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp2)
    return s


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h373_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    cp2 = CACHE_DIR / f"h376_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp2.exists():
        return pd.read_parquet(cp2).squeeze()
    print(f"  Downloading daily {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"]
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp2)
    return s


def sharpe(r: pd.Series) -> float:
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

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


def backtest_top6(
    monthly_px: pd.DataFrame,
    composite: pd.DataFrame,
    top_n: int = TOP_N,
    max_rank: pd.DataFrame = None,
    min_max_rank: float = None,   # Var C: drop stocks with max_rank < threshold
    mom_lookback: int = 6,
    mom_skip: int = 1,
) -> pd.Series:
    """Long top_n monthly by composite score, equal-weight."""
    monthly_ret = monthly_px.pct_change()
    port_rets   = []

    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        loc = monthly_ret.index.get_loc(month_end)
        if loc < mom_lookback + mom_skip + 1:
            continue

        scores = composite.loc[month_end].dropna()
        if len(scores) < top_n:
            continue

        if min_max_rank is not None and max_rank is not None:
            # Var C: take top momentum candidates, filter out low-MAX
            mr_row  = max_rank.loc[month_end]
            ranked  = scores.nlargest(top_n * 2)          # candidate pool
            kept    = [t for t in ranked.index if mr_row.get(t, 0) >= min_max_rank]
            selected = kept[:top_n] if len(kept) >= top_n else ranked.index[:top_n].tolist()
        else:
            selected = scores.nlargest(top_n).index.tolist()

        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, float(ret_this)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H376 — MAX Factor Composite on H198 Top-6 Selection")
    print("=" * 60)

    # Monthly prices (reuse H373 cache)
    print("\nLoading monthly prices (reusing H373 cache)…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # Daily prices (reuse H373 cache)
    print("Loading daily prices (reusing H373 cache)…")
    daily_list = []
    for t in UNIVERSE:
        try:
            daily_list.append(fetch_daily(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    daily_px  = pd.DataFrame(daily_list).T.sort_index().loc[DATA_START:]
    daily_ret = daily_px.pct_change()

    monthly_max_raw = daily_ret.resample("ME").max()
    monthly_max     = monthly_max_raw.shift(1).reindex(monthly_px.index)

    # 6-1m momentum signal
    sig_6m_1skip = (monthly_px.shift(1) / monthly_px.shift(7) - 1)
    # 6-0m momentum signal (no skip, per H277 finding)
    sig_6m_0skip = monthly_px.pct_change(6)

    mom_rank_1  = sig_6m_1skip.rank(axis=1, pct=True)
    mom_rank_0  = sig_6m_0skip.rank(axis=1, pct=True)
    max_rank    = monthly_max.rank(axis=1, pct=True)

    # SPY benchmark
    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_2026-04-30.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
    spy_ret = spy_px.pct_change().dropna()

    # ── Baseline: H198 pure 6-1m top-6 ──────────────────────────────────────
    print("\n=== Baseline: H198 6-1m top-6 (pure momentum, standard skip-month) ===")
    base = backtest_top6(monthly_px, mom_rank_1, top_n=TOP_N)
    bi   = eval_period(base, IS_START, IS_END)
    bo   = eval_period(base, OOS_START, OOS_END)
    print(f"IS  n={bi['n']}  Sharpe {bi['sharpe']:.3f}  MaxDD {bi['maxdd']:.1%}  NegYrs {bi['neg_yrs']}")
    print(f"OOS n={bo['n']}  Sharpe {bo['sharpe']:.3f}  MaxDD {bo['maxdd']:.1%}  NegYrs {bo['neg_yrs']}")

    # ── Variants ──────────────────────────────────────────────────────────────
    composites = {
        "A":  (0.7 * mom_rank_1 + 0.3 * max_rank, None,  None,  "6-1m: composite 0.7·mom + 0.3·max, top-6"),
        "B":  (0.5 * mom_rank_1 + 0.5 * max_rank, None,  None,  "6-1m: composite 0.5·mom + 0.5·max, top-6"),
        "C":  (mom_rank_1,                         max_rank, 0.4, "6-1m: top-6 momentum, drop max_rank < 0.40"),
        "D":  (0.7 * mom_rank_0 + 0.3 * max_rank, None,  None,  "6-0m (no skip): composite 0.7·mom + 0.3·max"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR':>7} {'NegY':>5}  Desc")
    print("-" * 82)

    results = {"baseline": {"is": bi, "oos": bo}}
    confirmed_any = False

    for var, (comp, mr, min_mr, desc) in composites.items():
        rets = backtest_top6(monthly_px, comp, TOP_N,
                             max_rank=mr, min_max_rank=min_mr)
        vi = eval_period(rets, IS_START, IS_END)
        vo = eval_period(rets, OOS_START, OOS_END)
        pass_gate = vo["sharpe"] > GATE_SHARPE and vo["maxdd"] > GATE_MAXDD
        flag = " ✓ PASS" if pass_gate else ""
        print(f"Var {var}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} "
              f"{vo['maxdd']:>9.1%} {vo['cagr']:>7.1%} {vo['neg_yrs']:>5d}  {desc}{flag}")
        results[f"var_{var}"] = {
            "is": vi, "oos": vo, "desc": desc, "pass_gate": pass_gate,
        }
        if pass_gate:
            confirmed_any = True

    # 6-0m baseline for reference (no skip, no MAX)
    base_noskip = backtest_top6(monthly_px, mom_rank_0, top_n=TOP_N)
    bns_i = eval_period(base_noskip, IS_START, IS_END)
    bns_o = eval_period(base_noskip, OOS_START, OOS_END)
    results["baseline_6m_noskip"] = {"is": bns_i, "oos": bns_o}
    print(f"6-0m base (no skip, no MAX): IS {bns_i['sharpe']:.3f} | OOS {bns_o['sharpe']:.3f}  MaxDD {bns_o['maxdd']:.1%}")

    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"SPY   {si['sharpe']:>7.3f} {so['sharpe']:>8.3f} {so['maxdd']:>9.1%} {so['cagr']:>7.1%} {so['neg_yrs']:>5d}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND OOS MaxDD > {GATE_MAXDD:.0%}")
    print(f"H198 baseline OOS Sharpe: {bo['sharpe']:.3f}")
    if confirmed_any:
        passing = [v for v in ["A","B","C","D"]
                   if results.get(f"var_{v}", {}).get("pass_gate")]
        print(f"CONFIRMED — variants passing gate: {', '.join(passing)}")
    else:
        best_v = max(["A","B","C","D"],
                     key=lambda v: results.get(f"var_{v}", {}).get("oos", {}).get("sharpe", 0))
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best variant {best_v} OOS Sharpe {bsh:.3f} vs gate {GATE_SHARPE}")

    out = {
        "hypothesis": "H376",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "results": results,
        "confirmed": confirmed_any,
        "spy": {"is": si, "oos": so},
    }
    op = RESULT_DIR / "h376_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {op}")
    return out


if __name__ == "__main__":
    main()
