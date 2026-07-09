"""
H385: Illusion Momentum (IMOM) on H198 30-Stock Large-Cap Universe
==================================================================
Iwanaga & Hirose (2024/2026) identify "illusion momentum" (IMOM):
  IMOM = MOM − SUM = [Π(1+r_t) − 1] − Σ(r_t)
where r_t are monthly returns over a 6-month no-skip formation window.

Cognitive bias: investors read arithmetic sum returns and underestimate
the true compound return. Stocks where MOM >> SUM (positive IMOM) are
systematically underpriced → predictable upward drift.

Distinction from H377 (no-skip 6-0m MOM):
- H377 ranks on total geometric return (MOM = Π(1+r) - 1)
- H385 ranks on how much MOM *exceeds* arithmetic SUM (IMOM = MOM - SUM)
- Orthogonal: IMOM captures smooth/consistent compounding, not raw magnitude

Paper findings (US 6M window):
- Long-Short raw alpha: 1.39%/month, FF-adj: 1.42%/month
- Alpha decay: 2.62% (1990s) → 0.55% (2010s+); tempering OOS expectations
- NO skip-month (footnote 7 confirmed)
- Confirmed in Japan + US; stronger in bear markets and large-cap

Variants:
  A: IMOM standalone top-1
  B: IMOM standalone top-2 EW
  C: IMOM standalone top-3 EW
  D: Composite rank = 0.5×rank(IMOM) + 0.5×rank(6-0m MOM), top-1  (blend w/ H377 Var A)
  E: IMOM top-1 + SPY 200MA overlay

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
    """Reuse H377/H376 cache; download if missing."""
    for prefix in ["h377", "h376", "h373", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    # Download fresh
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    cp = CACHE_DIR / f"h385_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_spy_daily() -> pd.Series:
    for prefix in ["h377", "h376", "h373", "h198", "h026"]:
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
    cp = CACHE_DIR / f"h385_SPY_daily_{DATA_START}_{DATA_END}.parquet"
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
    """
    Compute IMOM = MOM - SUM for each ticker.
    MOM = geometric return over 'window' months (no skip).
    SUM = arithmetic sum of monthly returns over 'window' months (no skip).
    IMOM = MOM - SUM = compounding gain above arithmetic approximation.
    """
    monthly_ret = monthly_px.pct_change()  # simple monthly returns

    # Rolling window compound return (no-skip): price_t / price_(t-window) - 1
    mom = monthly_px.pct_change(window)    # = (P_t / P_{t-window}) - 1

    # Rolling sum of the last 'window' monthly returns
    # Shift by 0 so current month IS included (no-skip, consistent with H377)
    # rolling(window) on monthly_ret looks back window months including current
    # But we want the sum of r_{t-window+1}...r_t (window monthly returns)
    # rolling.sum() on shifted series: sum of returns from r_{t-window+1} to r_t
    ret_sum = monthly_ret.rolling(window).sum()

    # IMOM = compound return - arithmetic sum
    imom = mom - ret_sum
    return imom


def backtest(
    monthly_px: pd.DataFrame,
    signal: pd.DataFrame,
    top_n: int,
    bil_mask: pd.Series = None,
) -> pd.Series:
    """Top-N equal-weight portfolio, monthly rebalance."""
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
    print("H385 — Illusion Momentum (IMOM) on H198 30-Stock Large-Cap Universe")
    print("=" * 70)

    # ── Load monthly prices ────────────────────────────────────────────────────
    print("\nLoading monthly prices (reusing H377/H376 cache)…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    # ── Compute signals ────────────────────────────────────────────────────────
    print("Computing IMOM and MOM signals…")

    # IMOM signal (6-month no-skip)
    imom_6  = compute_imom(monthly_px, window=6)

    # Raw 6-0m MOM (H377 Var A signal, for composite)
    mom_6_0 = monthly_px.pct_change(6)

    # Percentile ranks (higher = better)
    rank_imom  = imom_6.rank(axis=1, pct=True)
    rank_mom60 = mom_6_0.rank(axis=1, pct=True)

    # Composite rank: average of IMOM rank and 6-0m MOM rank
    rank_composite = 0.5 * rank_imom + 0.5 * rank_mom60

    # H198 baseline (6-1m top-1) for reference
    monthly_ret = monthly_px.pct_change()
    sig_6_1 = monthly_px.shift(1) / monthly_px.shift(7) - 1
    rank_6_1 = sig_6_1.rank(axis=1, pct=True)

    # ── SPY 200MA mask for Var E ──────────────────────────────────────────────
    print("Computing SPY 200MA mask for Var E…")
    spy_daily = fetch_spy_daily()
    spy_ma200 = spy_daily.rolling(200).mean()
    spy_monthly = spy_daily.resample("ME").last()
    spy_ma200_m = spy_ma200.resample("ME").last()
    spy_below_200 = (spy_monthly < spy_ma200_m).reindex(monthly_px.index).fillna(False)

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

    # H198 baseline (6-1m top-1)
    print("\n=== Baselines ===")
    base_rets = backtest(monthly_px, rank_6_1, top_n=1)
    bi = eval_period(base_rets, IS_START, IS_END)
    bo = eval_period(base_rets, OOS_START, OOS_END)
    si = eval_period(spy_ret, IS_START, IS_END)
    so = eval_period(spy_ret, OOS_START, OOS_END)
    print(f"H198 6-1m top-1 (H198 baseline)  IS {bi['sharpe']:.3f} | OOS {bo['sharpe']:.3f}  MaxDD {bo['maxdd']:.1%}")
    print(f"SPY buy-and-hold                  IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    # ── Variants ──────────────────────────────────────────────────────────────
    variants = {
        "A": dict(signal=rank_imom,      top_n=1, bil_mask=None,           desc="IMOM 6m top-1"),
        "B": dict(signal=rank_imom,      top_n=2, bil_mask=None,           desc="IMOM 6m top-2 EW"),
        "C": dict(signal=rank_imom,      top_n=3, bil_mask=None,           desc="IMOM 6m top-3 EW"),
        "D": dict(signal=rank_composite, top_n=1, bil_mask=None,           desc="IMOM+MOM composite rank top-1"),
        "E": dict(signal=rank_imom,      top_n=1, bil_mask=spy_below_200,  desc="IMOM 6m top-1 + SPY 200MA"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 92)
    # Reference lines
    print(f"{'base':4} {bi['sharpe']:>7.3f} {bo['sharpe']:>8.3f} {bo['maxdd']:>9.1%} "
          f"{bo['cagr']*100:>6.1f}% {bo['neg_yrs']:>5d}  H198 6-1m top-1 (H198 gate baseline)")
    print(f"{'SPY':4} {si['sharpe']:>7.3f} {so['sharpe']:>8.3f} {so['maxdd']:>9.1%} "
          f"{so['cagr']*100:>6.1f}% {so['neg_yrs']:>5d}  SPY buy-and-hold")
    print()

    results = {
        "baseline_6_1_top1": {"is": bi, "oos": bo},
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

    # ── Annual breakdown for best variant ─────────────────────────────────────
    best_standalone = max(["A", "B", "C"], key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    print(f"\n=== Var {best_standalone} annual returns (best standalone IMOM) ===")
    best_cfg = variants[best_standalone]
    rets_best = backtest(monthly_px, best_cfg["signal"], best_cfg["top_n"])
    ann_best  = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_best.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    # ── Diagnostic: IMOM vs MOM correlation ──────────────────────────────────
    print("\n=== Signal correlation: IMOM vs 6-0m MOM (OOS period) ===")
    # Flatten rank signals into long format and correlate over OOS months
    imom_flat = rank_imom.loc[OOS_START:OOS_END].values.flatten()
    mom60_flat = rank_mom60.loc[OOS_START:OOS_END].values.flatten()
    mask = ~(np.isnan(imom_flat) | np.isnan(mom60_flat))
    if mask.sum() > 0:
        corr = np.corrcoef(imom_flat[mask], mom60_flat[mask])[0, 1]
        print(f"  Pearson corr(rank_IMOM, rank_MOM_6_0) over OOS: {corr:.3f}")
    else:
        print("  (not enough data)")

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
        "hypothesis": "H385",
        "gate": {"oos_sharpe": GATE_SHARPE, "max_drawdown": GATE_MAXDD},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h385_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
