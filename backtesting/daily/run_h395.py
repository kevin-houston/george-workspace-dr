"""
H395: Realized-Vol Tiebreaker on H386 IMOM+MOM Composite
==========================================================
H393 showed ILLIQ adds no alpha on large-cap universe (all 30 stocks
highly liquid, minimal cross-sectional variation). Realized vol (σ) does
vary meaningfully cross-sectionally: NVDA/TSLA σ >> SBUX/WMT σ. If H386's
top-2 momentum picks happen to include high-vol names, penalizing them
toward the lower-vol version of the same rank could reduce MaxDD.

Low volatility = high rank in tiebreaker (prefer smoother compounders).
Composite = w_mom×rank(IMOM6) + w_mom×rank(MOM60) + w_vol×rank(1/σ_6m)

Variants:
  A: 0.40×IMOM6 + 0.40×MOM60 + 0.20×VOL, top-2  (baseline weight)
  B: 0.45×IMOM6 + 0.45×MOM60 + 0.10×VOL, top-2  (light vol filter)
  C: 0.33×IMOM6 + 0.33×MOM60 + 0.33×VOL, top-2  (equal weight)
  D: 0.40×IMOM6 + 0.40×MOM60 + 0.20×VOL, top-1  (concentrated)

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
    for prefix in ["h393", "h386", "h385", "h377", "h376", "h373", "h198"]:
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
    cp = CACHE_DIR / f"h395_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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
    monthly_ret = monthly_px.pct_change()
    mom = monthly_px.pct_change(window)
    ret_sum = monthly_ret.rolling(window).sum()
    return mom - ret_sum


def compute_realized_vol(monthly_px: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    """6-month trailing realized vol from monthly returns (annualized)."""
    monthly_ret = monthly_px.pct_change()
    return monthly_ret.rolling(window).std() * np.sqrt(12)


def backtest(
    monthly_px: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int,
) -> pd.Series:
    monthly_ret = monthly_px.pct_change()
    port_rets   = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for month_end in months:
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
    print("H395 — Realized-Vol Tiebreaker on H386 IMOM+MOM Composite")
    print("=" * 62)

    # ── Load monthly prices ───────────────────────────────────────────────────
    print("\nLoading monthly prices…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # ── Compute signals ───────────────────────────────────────────────────────
    print("Computing IMOM, MOM, and realized vol signals…")
    imom_6m = compute_imom(monthly_px, window=6)
    mom_6_0 = monthly_px.pct_change(6)
    rvol_6m = compute_realized_vol(monthly_px, window=6)

    rank_imom6 = imom_6m.rank(axis=1, pct=True)
    rank_mom60 = mom_6_0.rank(axis=1, pct=True)
    # Low vol = high rank (prefer low-vol names): rank INVERTED
    rank_lowvol = rvol_6m.rank(axis=1, pct=True, ascending=False)

    # Print cross-sectional vol spread to confirm signal quality
    avg_vol_spread = rvol_6m.std(axis=1).mean()
    print(f"  Avg cross-sectional σ spread (annualized): {avg_vol_spread:.1%} — "
          f"{'meaningful' if avg_vol_spread > 0.10 else 'minimal'}")

    # H198 baseline
    sig_6_1  = monthly_px.shift(1) / monthly_px.shift(7) - 1
    rank_6_1 = sig_6_1.rank(axis=1, pct=True)

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

    # H386 Var A reference
    comp_h386a = 0.5 * rank_imom6 + 0.5 * rank_mom60
    h386a_rets = backtest(monthly_px, comp_h386a, top_n=2)
    h386a_i = eval_period(h386a_rets, IS_START, IS_END)
    h386a_o = eval_period(h386a_rets, OOS_START, OOS_END)

    print(f"H198 6-1m top-1 (gate)     IS {bi['sharpe']:.3f} | OOS {bo['sharpe']:.3f}  MaxDD {bo['maxdd']:.1%}")
    print(f"H386 Var A IMOM+MOM top-2  IS {h386a_i['sharpe']:.3f} | OOS {h386a_o['sharpe']:.3f}  MaxDD {h386a_o['maxdd']:.1%}")
    print(f"SPY buy-and-hold           IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    # ── Variants ──────────────────────────────────────────────────────────────
    comp_40_40_20_t2 = 0.40 * rank_imom6 + 0.40 * rank_mom60 + 0.20 * rank_lowvol
    comp_45_45_10_t2 = 0.45 * rank_imom6 + 0.45 * rank_mom60 + 0.10 * rank_lowvol
    comp_33_33_33_t2 = 0.33 * rank_imom6 + 0.33 * rank_mom60 + 0.33 * rank_lowvol

    variants = {
        "A": dict(signal=comp_40_40_20_t2, top_n=2, desc="0.40×IMOM6+0.40×MOM60+0.20×LowVol top-2"),
        "B": dict(signal=comp_45_45_10_t2, top_n=2, desc="0.45×IMOM6+0.45×MOM60+0.10×LowVol top-2"),
        "C": dict(signal=comp_33_33_33_t2, top_n=2, desc="0.33×IMOM6+0.33×MOM60+0.33×LowVol top-2"),
        "D": dict(signal=comp_40_40_20_t2, top_n=1, desc="0.40×IMOM6+0.40×MOM60+0.20×LowVol top-1"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 92)
    print(f"{'H386A':4} {h386a_i['sharpe']:>7.3f} {h386a_o['sharpe']:>8.3f} {h386a_o['maxdd']:>9.1%} "
          f"{h386a_o['cagr']*100:>6.1f}% {h386a_o['neg_yrs']:>5d}  H386 Var A reference (no vol filter)")
    print()

    results = {
        "baseline_6_1_top1": {"is": bi, "oos": bo},
        "spy":                {"is": si, "oos": so},
        "h386_var_a_ref":    {"is": h386a_i, "oos": h386a_o},
    }
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest(monthly_px, cfg["signal"], cfg["top_n"])
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
        "hypothesis": "H395",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h395_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
