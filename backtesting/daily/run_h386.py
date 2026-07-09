"""
H386: IMOM Window & Weighting Exploration on H198 30-Stock Large-Cap Universe
==============================================================================
H385 found that standalone IMOM fails the MaxDD gate (-31% to -53%) but the
composite IMOM + 6-0m MOM rank (Var D) passes cleanly: OOS Sharpe 3.055,
MaxDD -16.8%. Var D beat pure H377 6-0m MOM (OOS ~2.8) by adding IMOM.

This hypothesis explores:
1. Whether 12m IMOM is better than 6m (paper finds 12m alpha 0.88% vs 6m 1.39%)
2. Whether composite weighting (IMOM fraction) can be optimized
3. Whether top-2/top-3 composite reduces MaxDD while keeping Sharpe high
4. Comparing composite vs H377 best variant (Var C: 6-0m top-3, OOS 3.075)

Variants:
  A: 0.5×rank(IMOM_6m) + 0.5×rank(MOM_6_0), top-2  (diversify H385 Var D)
  B: 0.5×rank(IMOM_6m) + 0.5×rank(MOM_6_0), top-3  (more diversification)
  C: 0.33×rank(IMOM_6m) + 0.67×rank(MOM_6_0), top-1  (MOM-dominant composite)
  D: 0.67×rank(IMOM_6m) + 0.33×rank(MOM_6_0), top-1  (IMOM-dominant composite)
  E: 0.5×rank(IMOM_12m) + 0.5×rank(MOM_12_0), top-1  (12-month version)
  F: 0.5×rank(IMOM_6m) + 0.5×rank(MOM_3_0), top-1   (short MOM blend)

IS: 2013-2020  OOS: 2021-2026  Universe: H198 30-stock
Gate: OOS Sharpe > 1.174 AND MaxDD > -30%
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
    for prefix in ["h385", "h377", "h376", "h373", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
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
    cp = CACHE_DIR / f"h386_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_spy_daily() -> pd.Series:
    for prefix in ["h385", "h377", "h376", "h373", "h198", "h026"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_SPY_daily_{DATA_START}_{end}.parquet"
            if cp.exists():
                return pd.read_parquet(cp).squeeze()
    raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("SPY", axis=1, level=1)
    s = raw["Close"]
    s.name = "SPY"
    cp = CACHE_DIR / f"h386_SPY_daily_{DATA_START}_{DATA_END}.parquet"
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


def compute_imom(monthly_px: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """IMOM = compound return - arithmetic sum of monthly returns (no skip)."""
    monthly_ret = monthly_px.pct_change()
    mom = monthly_px.pct_change(window)        # geometric no-skip
    ret_sum = monthly_ret.rolling(window).sum() # arithmetic sum no-skip
    return mom - ret_sum


def backtest(
    monthly_px: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int,
    bil_mask: pd.Series = None,
) -> pd.Series:
    monthly_ret = monthly_px.pct_change()
    port_rets   = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
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
    print("H386 — IMOM+MOM Composite Weighting & Window Exploration on H198")
    print("=" * 68)

    # ── Load prices ───────────────────────────────────────────────────────────
    print("\nLoading monthly prices (reusing H385/H377 cache)…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # ── Compute base signals ──────────────────────────────────────────────────
    print("Computing IMOM and MOM signals…")
    imom_6m  = compute_imom(monthly_px, window=6)
    imom_12m = compute_imom(monthly_px, window=12)
    mom_6_0  = monthly_px.pct_change(6)
    mom_12_0 = monthly_px.pct_change(12)
    mom_3_0  = monthly_px.pct_change(3)

    rank_imom6   = imom_6m.rank(axis=1, pct=True)
    rank_imom12  = imom_12m.rank(axis=1, pct=True)
    rank_mom60   = mom_6_0.rank(axis=1, pct=True)
    rank_mom120  = mom_12_0.rank(axis=1, pct=True)
    rank_mom30   = mom_3_0.rank(axis=1, pct=True)

    # H198 baseline (6-1m top-1) for reference
    sig_6_1  = monthly_px.shift(1) / monthly_px.shift(7) - 1
    rank_6_1 = sig_6_1.rank(axis=1, pct=True)

    # H377 Var C baseline (6-0m top-3): OOS 3.075 — the bar to beat
    # H385 Var D (composite 6m top-1): OOS 3.055

    # ── SPY benchmark ─────────────────────────────────────────────────────────
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

    # ── Baselines ─────────────────────────────────────────────────────────────
    print("\n=== Baselines ===")
    base_rets = backtest(monthly_px, rank_6_1, top_n=1)
    bi = eval_period(base_rets, IS_START, IS_END)
    bo = eval_period(base_rets, OOS_START, OOS_END)
    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)
    # H377 Var C
    h377c_rets = backtest(monthly_px, rank_mom60, top_n=3)
    h377c_i = eval_period(h377c_rets, IS_START, IS_END)
    h377c_o = eval_period(h377c_rets, OOS_START, OOS_END)
    # H385 Var D
    comp_h385d = 0.5 * rank_imom6 + 0.5 * rank_mom60
    h385d_rets = backtest(monthly_px, comp_h385d, top_n=1)
    h385d_i = eval_period(h385d_rets, IS_START, IS_END)
    h385d_o = eval_period(h385d_rets, OOS_START, OOS_END)

    print(f"H198 6-1m top-1 (gate)      IS {bi['sharpe']:.3f} | OOS {bo['sharpe']:.3f}  MaxDD {bo['maxdd']:.1%}")
    print(f"H377 Var C 6-0m top-3       IS {h377c_i['sharpe']:.3f} | OOS {h377c_o['sharpe']:.3f}  MaxDD {h377c_o['maxdd']:.1%}")
    print(f"H385 Var D IMOM+MOM top-1   IS {h385d_i['sharpe']:.3f} | OOS {h385d_o['sharpe']:.3f}  MaxDD {h385d_o['maxdd']:.1%}")
    print(f"SPY buy-and-hold            IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    # ── Variants ──────────────────────────────────────────────────────────────
    comp_50_50_6   = 0.5 * rank_imom6  + 0.5 * rank_mom60
    comp_50_50_12  = 0.5 * rank_imom12 + 0.5 * rank_mom120
    comp_33_67_6   = 0.33 * rank_imom6 + 0.67 * rank_mom60
    comp_67_33_6   = 0.67 * rank_imom6 + 0.33 * rank_mom60
    comp_50_50_3   = 0.5 * rank_imom6  + 0.5 * rank_mom30

    variants = {
        "A": dict(signal=comp_50_50_6,  top_n=2, bil_mask=None, desc="0.5×IMOM6+0.5×MOM60 top-2"),
        "B": dict(signal=comp_50_50_6,  top_n=3, bil_mask=None, desc="0.5×IMOM6+0.5×MOM60 top-3"),
        "C": dict(signal=comp_33_67_6,  top_n=1, bil_mask=None, desc="0.33×IMOM6+0.67×MOM60 top-1"),
        "D": dict(signal=comp_67_33_6,  top_n=1, bil_mask=None, desc="0.67×IMOM6+0.33×MOM60 top-1"),
        "E": dict(signal=comp_50_50_12, top_n=1, bil_mask=None, desc="0.5×IMOM12+0.5×MOM120 top-1"),
        "F": dict(signal=comp_50_50_3,  top_n=1, bil_mask=None, desc="0.5×IMOM6+0.5×MOM30 top-1"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 95)
    print(f"{'H377C':4} {h377c_i['sharpe']:>7.3f} {h377c_o['sharpe']:>8.3f} {h377c_o['maxdd']:>9.1%} "
          f"{h377c_o['cagr']*100:>6.1f}% {h377c_o['neg_yrs']:>5d}  H377 Var C (6-0m top-3 reference)")
    print(f"{'H385D':4} {h385d_i['sharpe']:>7.3f} {h385d_o['sharpe']:>8.3f} {h385d_o['maxdd']:>9.1%} "
          f"{h385d_o['cagr']*100:>6.1f}% {h385d_o['neg_yrs']:>5d}  H385 Var D (composite top-1 reference)")
    print()

    results = {
        "baseline_6_1_top1":   {"is": bi, "oos": bo},
        "spy":                  {"is": si, "oos": so},
        "h377_var_c_ref":      {"is": h377c_i, "oos": h377c_o},
        "h385_var_d_ref":      {"is": h385d_i, "oos": h385d_o},
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

    # ── Annual breakdown for best variant ─────────────────────────────────────
    if confirmed_variants:
        best_v = max(confirmed_variants,
                     key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    else:
        best_v = max(variants.keys(),
                     key=lambda v: results.get(f"var_{v}", {}).get("oos", {}).get("sharpe", 0))
    print(f"\n=== Var {best_v} annual returns ===")
    rets_best = backtest(monthly_px, variants[best_v]["signal"], variants[best_v]["top_n"])
    ann_best  = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_best.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    # ── Verdict ───────────────────────────────────────────────────────────────
    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} AND MaxDD > {GATE_MAXDD:.0%}")
    confirmed = len(confirmed_variants) > 0
    if confirmed:
        best_v2 = max(confirmed_variants,
                      key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh = results[f"var_{best_v2}"]["oos"]["sharpe"]
        print(f"CONFIRMED — variants passing gate: {', '.join(confirmed_variants)}")
        print(f"Best variant: {best_v2}  OOS Sharpe {bsh:.3f}")
    else:
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best variant {best_v} OOS Sharpe {bsh:.3f}")

    out = {
        "hypothesis": "H386",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h386_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
