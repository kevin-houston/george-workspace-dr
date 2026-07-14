"""
H398: 12-Month IMOM as 4th Signal on H395 Var C Composite
==========================================================
H395 Var C (champion: OOS Sharpe 3.962) uses equal-weight:
  0.33×IMOM6 + 0.33×MOM60 + 0.33×LowVol

Theoretical basis (arXiv:2607.03858, Frøseth Jul 2026):
Spectral decomposition maps IMOM to the return-channel persistent-memory
component. If this channel has memory structure at BOTH 6m and 12m horizons,
adding IMOM12 as a 4th signal captures compounders that are consistently
good over a full year — orthogonal information to 6-month IMOM.

IMOM12 formula: compound_return_12m - arithmetic_sum_12m (= consistent compounders)

Gate: OOS Sharpe > 3.962 (must beat H395 Var C champion)

Variants:
  A: 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12  top-2  (equal 4-way)
  B: 0.30×IMOM6+0.30×MOM60+0.25×LowVol+0.15×IMOM12  top-2  (IMOM12 light)
  C: 0.20×IMOM6+0.20×MOM60+0.20×LowVol+0.40×IMOM12  top-2  (IMOM12 dominant)
  D: 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12  top-1  (concentrated)

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
GATE_SHARPE = 3.962   # must beat H395 Var C


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h395", "h393", "h386", "h385", "h377", "h376", "h373", "h198"]:
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
    cp = CACHE_DIR / f"h398_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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


def compute_imom(monthly_px: pd.DataFrame, window: int) -> pd.DataFrame:
    """IMOM = compound_return - arithmetic_sum over `window` months."""
    monthly_ret = monthly_px.pct_change()
    compound    = monthly_px.pct_change(window)
    arith_sum   = monthly_ret.rolling(window).sum()
    return compound - arith_sum


def compute_realized_vol(monthly_px: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    monthly_ret = monthly_px.pct_change()
    return monthly_ret.rolling(window).std() * np.sqrt(12)


def backtest(monthly_px: pd.DataFrame, signal: pd.DataFrame, top_n: int) -> pd.Series:
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
    print("H398 — 12-Month IMOM as 4th Signal on H395 Var C")
    print("=" * 60)

    print("\nLoading monthly prices…")
    monthly_list = []
    for t in UNIVERSE:
        try:
            monthly_list.append(fetch_monthly(t))
        except Exception as e:
            print(f"  WARN {t}: {e}")
    monthly_px = pd.DataFrame(monthly_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(monthly_px.columns)} tickers, {len(monthly_px)} months")

    print("Computing signals…")
    imom_6m  = compute_imom(monthly_px, window=6)
    imom_12m = compute_imom(monthly_px, window=12)
    mom_6_0  = monthly_px.pct_change(6)
    rvol_6m  = compute_realized_vol(monthly_px, window=6)

    rank_imom6  = imom_6m.rank(axis=1, pct=True)
    rank_imom12 = imom_12m.rank(axis=1, pct=True)
    rank_mom60  = mom_6_0.rank(axis=1, pct=True)
    rank_lowvol = rvol_6m.rank(axis=1, pct=True, ascending=False)

    # Report IMOM12 cross-sectional spread
    avg_imom12_spread = imom_12m.std(axis=1).mean()
    avg_imom6_spread  = imom_6m.std(axis=1).mean()
    print(f"  IMOM6  avg cross-sectional spread: {avg_imom6_spread:.4f}")
    print(f"  IMOM12 avg cross-sectional spread: {avg_imom12_spread:.4f}")
    corr_imom6_imom12 = imom_6m.corrwith(imom_12m, axis=1).mean()
    print(f"  Avg cross-sectional corr(IMOM6, IMOM12): {corr_imom6_imom12:.3f}")

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

    # H395 Var C reference
    comp_h395c = 0.33 * rank_imom6 + 0.33 * rank_mom60 + 0.33 * rank_lowvol
    h395c_rets  = backtest(monthly_px, comp_h395c, top_n=2)
    h395c_i     = eval_period(h395c_rets, IS_START, IS_END)
    h395c_o     = eval_period(h395c_rets, OOS_START, OOS_END)
    si          = eval_period(spy_ret, IS_START, IS_END)
    so          = eval_period(spy_ret, OOS_START, OOS_END)

    print(f"\n=== References ===")
    print(f"H395 Var C (champion) IS {h395c_i['sharpe']:.3f} | OOS {h395c_o['sharpe']:.3f}  MaxDD {h395c_o['maxdd']:.1%}")
    print(f"SPY buy-and-hold      IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    variants = {
        "A": dict(
            signal=0.25*rank_imom6 + 0.25*rank_mom60 + 0.25*rank_lowvol + 0.25*rank_imom12,
            top_n=2, desc="0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 top-2",
        ),
        "B": dict(
            signal=0.30*rank_imom6 + 0.30*rank_mom60 + 0.25*rank_lowvol + 0.15*rank_imom12,
            top_n=2, desc="0.30×IMOM6+0.30×MOM60+0.25×LowVol+0.15×IMOM12 top-2",
        ),
        "C": dict(
            signal=0.20*rank_imom6 + 0.20*rank_mom60 + 0.20*rank_lowvol + 0.40*rank_imom12,
            top_n=2, desc="0.20×IMOM6+0.20×MOM60+0.20×LowVol+0.40×IMOM12 top-2",
        ),
        "D": dict(
            signal=0.25*rank_imom6 + 0.25*rank_mom60 + 0.25*rank_lowvol + 0.25*rank_imom12,
            top_n=1, desc="0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 top-1",
        ),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 105)
    print(f"{'H395C':4} {h395c_i['sharpe']:>7.3f} {h395c_o['sharpe']:>8.3f} {h395c_o['maxdd']:>9.1%} "
          f"{h395c_o['cagr']*100:>6.1f}% {h395c_o['neg_yrs']:>5d}  H395 Var C reference")
    print()

    results = {
        "h395_var_c_ref": {"is": h395c_i, "oos": h395c_o},
        "spy":            {"is": si, "oos": so},
    }
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest(monthly_px, cfg["signal"], cfg["top_n"])
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS H395C" if beat else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {
            "is": vi, "oos": vo, "desc": cfg["desc"],
            "beats_h395c": beat,
        }
        if beat:
            confirmed_variants.append(var_id)

    # Annual breakdown for best OOS variant
    best_v = max(variants.keys(), key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    print(f"\n=== Var {best_v} annual returns (OOS: 2021+) ===")
    rets_best = backtest(monthly_px, variants[best_v]["signal"], variants[best_v]["top_n"])
    ann_best  = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_best.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (beat H395 Var C champion)")
    if confirmed_variants:
        best_v2 = max(confirmed_variants, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh = results[f"var_{best_v2}"]["oos"]["sharpe"]
        print(f"CONFIRMED — variants beating H395C: {', '.join(confirmed_variants)}")
        print(f"New champion candidate: Var {best_v2}  OOS Sharpe {bsh:.3f}")
        confirmed = True
    else:
        best_v2 = best_v
        bsh = results[f"var_{best_v2}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best_v2} OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        print(f"H395 Var C remains champion at OOS Sharpe {h395c_o['sharpe']:.3f}")
        confirmed = False

    out = {
        "hypothesis": "H398",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE, "description": "beat H395 Var C"},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "imom12_vs_imom6_corr": float(corr_imom6_imom12),
        "results": results,
    }
    op = RESULT_DIR / "h398_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
