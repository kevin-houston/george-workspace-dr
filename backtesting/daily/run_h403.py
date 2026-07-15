"""
H403 — SPY 200MA Regime Gate on H398 Var A
===========================================
H398 Var A (OOS 4.068, MaxDD -4.7%) already performs well in bear markets
(zero negative years, strong 2022). But MaxDD -4.7% could theoretically be
reduced further with a regime gate that routes to BIL in deep bear markets.

Hypothesis: Adding SPY>200MA gate to H398 Var A improves MaxDD without
significant Sharpe cost. Analogue to H301 (200MA gate on H026: +27.4% Sharpe).

Gate: OOS Sharpe > 4.068 (must beat H398A standalone) OR MaxDD improvement > 1pp

Variants:
  A: SPY>200MA gate          → route to BIL when SPY<200MA (at month-end)
  B: VIX<20 gate             → route to BIL when VIX>20 at month-end
  C: SPY>200MA AND VIX<25    → both conditions must pass
  D: H398A standalone        → sanity check (= H398 Var A)

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
GATE_SHARPE = 4.068   # must beat H398 Var A
GATE_MDD_IMPROVEMENT = 0.01   # 1pp MaxDD improvement


def fetch_monthly(ticker):
    for prefix in ["h398","h402","h395","h393","h386","h385","h377","h198"]:
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
    pd.DataFrame(s).to_parquet(
        CACHE_DIR / f"h403_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet")
    return s


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def cagr_ann(r):
    return float(r.mean() * 12)

def neg_years(r):
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())

def eval_period(rets, start, end):
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


def compute_imom(monthly_px, window):
    monthly_ret = monthly_px.pct_change()
    compound    = monthly_px.pct_change(window)
    arith_sum   = monthly_ret.rolling(window).sum()
    return compound - arith_sum


def backtest_gated(monthly_px, signal, top_n, regime_mask):
    """Backtest with regime gate: hold BIL return (~0) when regime_mask=False."""
    monthly_ret = monthly_px.pct_change()
    port_rets   = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        # Check regime at this month end
        in_regime = True
        if month_end in regime_mask.index:
            in_regime = bool(regime_mask.loc[month_end])
        elif month_end > regime_mask.index[-1]:
            in_regime = bool(regime_mask.iloc[-1])

        if not in_regime:
            # In BIL/cash — approximate BIL return as 0 (or small positive)
            port_rets.append((month_end, 0.0))
            continue

        scores = signal.loc[month_end].dropna()
        if len(scores) < top_n:
            continue
        selected = scores.nlargest(top_n).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        r = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, float(r)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H403 — SPY 200MA Regime Gate on H398 Var A")
    print("=" * 48)

    print("\nLoading H198 universe prices…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    print("Computing H398 Var A signals…")
    ret      = monthly_px.pct_change()
    imom6    = monthly_px.pct_change(6)  - ret.rolling(6).sum()
    imom12   = monthly_px.pct_change(12) - ret.rolling(12).sum()
    mom60    = monthly_px.pct_change(6)
    rvol6    = ret.rolling(6).std() * np.sqrt(12)

    rank_i6  = imom6.rank(axis=1, pct=True)
    rank_i12 = imom12.rank(axis=1, pct=True)
    rank_m60 = mom60.rank(axis=1, pct=True)
    rank_lv  = rvol6.rank(axis=1, pct=True, ascending=False)

    composite = 0.25 * rank_i6 + 0.25 * rank_m60 + 0.25 * rank_lv + 0.25 * rank_i12

    print("Loading SPY for 200MA regime…")
    spy_close = None
    for prefix in ["h402","h398","h198","h112"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_SPY_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                spy_close = pd.read_parquet(cp).squeeze()
                break
        if spy_close is not None:
            break
    if spy_close is None:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_close = raw["Close"].resample("ME").last()

    spy_daily = yf.download("SPY", start="2003-01-01", end=DATA_END,
                            auto_adjust=True, progress=False)
    if isinstance(spy_daily.columns, pd.MultiIndex):
        spy_daily = spy_daily.xs("SPY", axis=1, level=1)
    spy_cl = spy_daily["Close"]
    spy_ma200 = spy_cl.rolling(200).mean()
    spy_above_ma = (spy_cl > spy_ma200).resample("ME").last()

    print("Loading VIX for VIX<20 gate…")
    try:
        vix_raw = yf.download("^VIX", start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        if isinstance(vix_raw.columns, pd.MultiIndex):
            vix_raw = vix_raw.xs("^VIX", axis=1, level=1)
        vix_monthly = vix_raw["Close"].resample("ME").last()
    except Exception as e:
        print(f"  WARN VIX: {e}")
        vix_monthly = pd.Series(dtype=float)

    vix_below_20 = (vix_monthly < 20).reindex(spy_above_ma.index, fill_value=False)
    vix_below_25 = (vix_monthly < 25).reindex(spy_above_ma.index, fill_value=False)

    # Regime masks aligned to monthly signal index
    months_idx = composite.index[composite.index >= IS_START]

    def align_regime(mask):
        return mask.reindex(months_idx, method="ffill").fillna(True)

    mask_200ma  = align_regime(spy_above_ma)
    mask_vix20  = align_regime(vix_below_20)
    mask_combo  = align_regime(spy_above_ma & vix_below_25)
    mask_always = pd.Series(True, index=months_idx)

    # Count months in cash per mask
    print(f"\n  SPY>200MA: {mask_200ma.sum()}/{len(mask_200ma)} months invested "
          f"({mask_200ma.mean():.0%})")
    if len(vix_below_20) > 0:
        print(f"  VIX<20:    {mask_vix20.sum()}/{len(mask_vix20)} months invested "
              f"({mask_vix20.mean():.0%})")
        print(f"  Combo:     {mask_combo.sum()}/{len(mask_combo)} months invested "
              f"({mask_combo.mean():.0%})")

    VARIANTS = {
        "A": ("SPY>200MA gate", mask_200ma),
        "B": ("VIX<20 gate",    mask_vix20),
        "C": ("SPY>200MA AND VIX<25", mask_combo),
        "D": ("H398A standalone (sanity)", mask_always),
    }

    results = {}
    h398a_ref_oos = {"sharpe": 4.068, "maxdd": -0.047}

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 90)

    for var_id, (desc, mask) in VARIANTS.items():
        rets = backtest_gated(monthly_px, composite, 2, mask)
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        beat_sharpe = vo["sharpe"] > GATE_SHARPE
        beat_mdd    = vo["maxdd"] > h398a_ref_oos["maxdd"] + GATE_MDD_IMPROVEMENT  # less negative
        flag = ""
        if beat_sharpe:
            flag += " ✓ SHARPE"
        if beat_mdd:
            flag += " ✓ MDD"
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {desc}{flag}")
        results[var_id] = {
            "is": vi, "oos": vo, "desc": desc,
            "beats_sharpe_gate": beat_sharpe,
            "beats_mdd_gate": beat_mdd,
            "cash_months_pct": round(float(1 - mask.mean()), 3),
        }

        # Annual breakdown OOS
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        yr_str = "  ".join(f"{y.year}:{v:+.0%}" for y, v in yr.items())
        print(f"  Annual: {yr_str}")

    print(f"\n=== Verdict (Gate: Sharpe > {GATE_SHARPE} OR MaxDD improvement > 1pp) ===")
    confirmed_sharpe = [v for v in ["A","B","C"] if results[v]["beats_sharpe_gate"]]
    confirmed_mdd    = [v for v in ["A","B","C"] if results[v]["beats_mdd_gate"]]
    all_confirmed    = list(set(confirmed_sharpe + confirmed_mdd))

    if all_confirmed:
        best_sharpe_v = max(["A","B","C"], key=lambda v: results[v]["oos"]["sharpe"])
        best_mdd_v    = max(["A","B","C"], key=lambda v: results[v]["oos"]["maxdd"])  # less negative = better
        print(f"  Sharpe-confirmed variants: {confirmed_sharpe or 'none'}")
        print(f"  MDD-confirmed variants:    {confirmed_mdd or 'none'}")
        print(f"  Best Sharpe: Var {best_sharpe_v} — {results[best_sharpe_v]['oos']['sharpe']:.3f}")
        print(f"  Best MaxDD:  Var {best_mdd_v}  — {results[best_mdd_v]['oos']['maxdd']:.1%}")
        verdict = "CONFIRMED"
    else:
        print(f"  NOT CONFIRMED — no variant beats gate on either dimension")
        best_all = max(["A","B","C"], key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  Best: Var {best_all} OOS {results[best_all]['oos']['sharpe']:.3f} / MDD {results[best_all]['oos']['maxdd']:.1%}")
        verdict = "NOT CONFIRMED"

    out = {
        "hypothesis": "H403",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE,
                 "or_mdd_improvement_pp": GATE_MDD_IMPROVEMENT,
                 "reference": "H398 Var A: OOS 4.068, MaxDD -4.7%"},
        "verdict": verdict,
        "results": results,
    }
    op = RESULT_DIR / "h403_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
