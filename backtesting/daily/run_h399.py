"""
H399: 5-Factor Extensions and 12m-MOM Substitution on H398 Var A
=================================================================
H398 Var A (new champion: OOS Sharpe 4.068, MaxDD -4.7%) uses:
  0.25×IMOM6 + 0.25×MOM60 + 0.25×LowVol + 0.25×IMOM12

IMOM12 corr(IMOM6) = 0.484 — partially independent. Hypothesis:
adding 12-month directional momentum (MOM12, no-skip) as a 5th
factor, OR replacing 6-month MOM with 12-month MOM, might capture
even more of the persistent-memory spectral component.

Gate: OOS Sharpe > 4.068 (must beat H398 Var A)

Variants:
  A: 0.20×IMOM6+0.20×MOM60+0.20×LowVol+0.20×IMOM12+0.20×MOM120  top-2  (5-factor equal)
  B: 0.33×IMOM6+0.33×LowVol+0.33×IMOM12                           top-2  (3-factor: drop both MOMs)
  C: 0.25×IMOM6+0.25×LowVol+0.25×IMOM12+0.25×MOM120              top-2  (replace MOM60 with MOM120)
  D: 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12               top-3  (H398 Var A but top-3)
  E: 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12               top-2  (H398 Var A repeat — sanity)

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


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h398", "h395", "h393", "h386", "h385", "h377", "h376", "h373", "h198"]:
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
    cp = CACHE_DIR / f"h399_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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
    monthly_ret = monthly_px.pct_change()
    compound    = monthly_px.pct_change(window)
    arith_sum   = monthly_ret.rolling(window).sum()
    return compound - arith_sum


def compute_realized_vol(monthly_px: pd.DataFrame, window: int = 6) -> pd.DataFrame:
    return monthly_px.pct_change().rolling(window).std() * np.sqrt(12)


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
    print("H399 — 5-Factor Extensions and 12m-MOM Substitution")
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
    mom_6_0  = monthly_px.pct_change(6)    # 6-month no-skip
    mom_12_0 = monthly_px.pct_change(12)   # 12-month no-skip
    rvol_6m  = compute_realized_vol(monthly_px, window=6)

    rank_imom6  = imom_6m.rank(axis=1, pct=True)
    rank_imom12 = imom_12m.rank(axis=1, pct=True)
    rank_mom60  = mom_6_0.rank(axis=1, pct=True)
    rank_mom120 = mom_12_0.rank(axis=1, pct=True)
    rank_lowvol = rvol_6m.rank(axis=1, pct=True, ascending=False)

    # Pairwise correlations of new signal
    corr_mom60_mom120  = mom_6_0.corrwith(mom_12_0, axis=1).mean()
    corr_imom12_mom120 = imom_12m.corrwith(mom_12_0, axis=1).mean()
    print(f"  corr(MOM60, MOM120):    {corr_mom60_mom120:.3f}")
    print(f"  corr(IMOM12, MOM120):   {corr_imom12_mom120:.3f}")

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

    # H395C and H398A references
    comp_h395c = 0.33*rank_imom6 + 0.33*rank_mom60 + 0.33*rank_lowvol
    h395c_rets = backtest(monthly_px, comp_h395c, top_n=2)
    h395c_o    = eval_period(h395c_rets, OOS_START, OOS_END)

    comp_h398a = 0.25*rank_imom6 + 0.25*rank_mom60 + 0.25*rank_lowvol + 0.25*rank_imom12
    h398a_rets = backtest(monthly_px, comp_h398a, top_n=2)
    h398a_i    = eval_period(h398a_rets, IS_START, IS_END)
    h398a_o    = eval_period(h398a_rets, OOS_START, OOS_END)

    so = eval_period(spy_ret, OOS_START, OOS_END)

    print(f"\n=== References ===")
    print(f"H395 Var C             OOS {h395c_o['sharpe']:.3f}  MaxDD {h395c_o['maxdd']:.1%}")
    print(f"H398 Var A (champion)  OOS {h398a_o['sharpe']:.3f}  MaxDD {h398a_o['maxdd']:.1%}")
    print(f"SPY                    OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    variants = {
        "A": dict(
            signal=0.20*rank_imom6+0.20*rank_mom60+0.20*rank_lowvol+0.20*rank_imom12+0.20*rank_mom120,
            top_n=2, desc="0.20×IMOM6+0.20×MOM60+0.20×LowVol+0.20×IMOM12+0.20×MOM120 top-2",
        ),
        "B": dict(
            signal=0.33*rank_imom6+0.33*rank_lowvol+0.33*rank_imom12,
            top_n=2, desc="0.33×IMOM6+0.33×LowVol+0.33×IMOM12 top-2  (drop both MOMs)",
        ),
        "C": dict(
            signal=0.25*rank_imom6+0.25*rank_lowvol+0.25*rank_imom12+0.25*rank_mom120,
            top_n=2, desc="0.25×IMOM6+0.25×LowVol+0.25×IMOM12+0.25×MOM120 top-2  (replace MOM60)",
        ),
        "D": dict(
            signal=0.25*rank_imom6+0.25*rank_mom60+0.25*rank_lowvol+0.25*rank_imom12,
            top_n=3, desc="0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 top-3  (H398A, top-3)",
        ),
        "E": dict(
            signal=0.25*rank_imom6+0.25*rank_mom60+0.25*rank_lowvol+0.25*rank_imom12,
            top_n=2, desc="0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 top-2  (H398A sanity)",
        ),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 115)
    print(f"{'H398A':4} {h398a_i['sharpe']:>7.3f} {h398a_o['sharpe']:>8.3f} {h398a_o['maxdd']:>9.1%} "
          f"{h398a_o['cagr']*100:>6.1f}% {h398a_o['neg_yrs']:>5d}  H398 Var A reference")
    print()

    results = {
        "h395_var_c_ref": {"oos": h395c_o},
        "h398_var_a_ref": {"is": h398a_i, "oos": h398a_o},
        "spy":            {"oos": so},
    }
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest(monthly_px, cfg["signal"], cfg["top_n"])
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS H398A" if beat else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {"is": vi, "oos": vo, "desc": cfg["desc"], "beats_h398a": beat}
        if beat:
            confirmed_variants.append(var_id)

    # Best variant annual detail
    best_v = max(variants.keys(), key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    print(f"\n=== Var {best_v} annual returns (OOS: 2021+) ===")
    rets_best = backtest(monthly_px, variants[best_v]["signal"], variants[best_v]["top_n"])
    ann_best  = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann_best.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (beat H398 Var A champion)")
    if confirmed_variants:
        best_v2 = max(confirmed_variants, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh = results[f"var_{best_v2}"]["oos"]["sharpe"]
        print(f"CONFIRMED — variants beating H398A: {', '.join(confirmed_variants)}")
        print(f"New champion: Var {best_v2}  OOS Sharpe {bsh:.3f}")
        confirmed = True
    else:
        bsh = results[f"var_{best_v}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best_v} OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        print(f"H398 Var A remains champion at OOS Sharpe {h398a_o['sharpe']:.3f}")
        confirmed = False

    out = {
        "hypothesis": "H399",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE, "description": "beat H398 Var A"},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "signal_corrs": {
            "mom60_vs_mom120":  float(corr_mom60_mom120),
            "imom12_vs_mom120": float(corr_imom12_mom120),
        },
        "results": results,
    }
    op = RESULT_DIR / "h399_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
