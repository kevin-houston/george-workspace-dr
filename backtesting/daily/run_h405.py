"""
H405: Short-Horizon Momentum Windows on H026 ETF Universe
==========================================================
H026 confirmed at 12-month momentum (OOS Sharpe ~1.2 on canonical 2018-2026 split,
2.665 on 2021-2026 sub-period). H335 (bond ETF window optimization) failed at
shorter horizons. Question: for the H026 EQUITY ETF universe, do shorter momentum
windows (3m, 6m) capture more timely sector rotation signals?

EarningsInOne (arXiv:2606.29734, tonight's dream cycle) documents that news
decomposes into fast (EPS, 0-30 min) and slow (ECT, 30-90 min → next day) channels.
Analogously, ETF momentum may have fast (3m) and slow (12m) channels. Does a
composite multi-window signal outperform single-window?

Variants:
  A: 3-month momentum, top-1 (short-term)
  B: 6-month momentum, top-1 (medium-term)
  C: 3m+6m equal-weight composite, top-1
  D: 3m+6m+12m equal-weight composite, top-1 (multi-scale)
  E: 12-month momentum, top-1 (reference — should match H026 baseline)

IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 2.665 (H026 12m baseline on this split)
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

DATA_START  = "2003-01-01"
DATA_END    = "2026-06-30"
IS_START    = pd.Timestamp("2013-01-01")
IS_END      = pd.Timestamp("2020-12-31")
OOS_START   = pd.Timestamp("2021-01-01")
OOS_END     = pd.Timestamp("2026-06-30")
GATE_SHARPE = 2.665   # beat H026 12m baseline on this 2021-2026 OOS split

H026_UNIVERSE = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
]


def load_close(ticker: str) -> pd.Series:
    for prefix in ["h112","h113","h354","h361","h362","h363","h402","h404","h405"]:
        for pat in [f"{prefix}_{ticker}_close.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df, pd.DataFrame):
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns:
                        return df["close"].rename(ticker)
                return df.squeeze().rename(ticker)
        for i in range(62, 130):
            p = CACHE_DIR / f"h{i:03d}_{ticker}_close_{DATA_START}_{DATA_END}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h405_{ticker}_close.parquet")
    return s


def sharpe(r): return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))
def maxdd(r):
    eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())
def cagr_ann(r): return float(r.mean() * 12)
def neg_years(r):
    ann = r.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    return int((ann < 0).sum())
def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3), "maxdd": round(maxdd(r), 3),
            "cagr": round(cagr_ann(r), 3), "neg_yrs": neg_years(r)}


def backtest_rotation(monthly_px: pd.DataFrame, monthly_ret: pd.DataFrame,
                      signal: pd.DataFrame, n_hold: int = 1) -> pd.Series:
    """
    Top-n rotation by signal rank.
    Signal is formed at end of month i-1 and applied to return of month i.
    Uses signal.iloc[i-1] to avoid look-ahead bias at short windows.
    """
    rows = []
    for i in range(13, len(monthly_px)):   # warmup: 12 months + 1 lag
        sig_row = signal.iloc[i-1].dropna()   # signal from LAST month (no look-ahead)
        if len(sig_row) < n_hold:
            continue
        top_n    = list(sig_row.nlargest(n_hold).index)
        ret_this = float(monthly_ret.iloc[i][top_n].mean())
        rows.append((monthly_px.index[i], ret_this))
    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def main():
    print("H405 — Short-Horizon Momentum Windows on H026 ETF Universe")
    print("=" * 65)

    print("\nLoading H026 ETF data…")
    closes = {}
    for t in H026_UNIVERSE:
        try:
            closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    print(f"  {len(monthly_px.columns)} ETFs, {len(monthly_px)} months")

    # Compute momentum signals at various windows
    mom_3m  = monthly_px / monthly_px.shift(3) - 1
    mom_6m  = monthly_px / monthly_px.shift(6) - 1
    mom_12m = monthly_px / monthly_px.shift(12) - 1

    # Rank each
    r3  = mom_3m.rank(axis=1, pct=True)
    r6  = mom_6m.rank(axis=1, pct=True)
    r12 = mom_12m.rank(axis=1, pct=True)

    # SPY benchmark
    spy_cp = CACHE_DIR / "h198_SPY_monthly_2011-01-01_2026-04-30.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
        spy_ret_m = spy_px.pct_change().dropna()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex): raw = raw.xs("SPY", axis=1, level=1)
        spy_ret_m = raw["Close"].pct_change().dropna()
    si = eval_period(spy_ret_m, IS_START, IS_END)
    so = eval_period(spy_ret_m, OOS_START, OOS_END)

    # Note: H026 baseline (dual-rank momentum+lowvol) gave OOS 2.665
    # For these variants we use pure momentum rank only (simpler, fair comparison)
    variants = {
        "A": dict(signal=r3,                    desc="3m momentum, top-1"),
        "B": dict(signal=r6,                    desc="6m momentum, top-1"),
        "C": dict(signal=(r3+r6)/2,             desc="3m+6m equal composite, top-1"),
        "D": dict(signal=(r3+r6+r12)/3,         desc="3m+6m+12m equal composite, top-1"),
        "E": dict(signal=r12,                   desc="12m momentum, top-1 (reference)"),
    }

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5}  Desc")
    print("-" * 100)
    print(f"{'SPY':4} {si['sharpe']:>7.3f} {so['sharpe']:>8.3f} {so['maxdd']:>9.1%} "
          f"{so['cagr']*100:>6.1f}% {so['neg_yrs']:>5d}  SPY buy-and-hold")

    results = {"spy": {"is": si, "oos": so}}
    confirmed_variants = []

    for var_id, cfg in variants.items():
        rets = backtest_rotation(monthly_px, monthly_ret, cfg["signal"])
        vi   = eval_period(rets, IS_START, IS_END)
        vo   = eval_period(rets, OOS_START, OOS_END)
        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS H026 12m" if beat else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {"is": vi, "oos": vo, "desc": cfg["desc"], "beats_gate": beat}
        if beat:
            confirmed_variants.append(var_id)

    # Best OOS annual breakdown
    best_v = max(variants.keys(), key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    rets_best = backtest_rotation(monthly_px, monthly_ret, variants[best_v]["signal"])
    print(f"\n=== Var {best_v} annual returns (OOS: 2021+) ===")
    ann = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (beat H026 12m baseline on 2021-2026 split)")
    if confirmed_variants:
        best  = max(confirmed_variants, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh   = results[f"var_{best}"]["oos"]["sharpe"]
        print(f"CONFIRMED — beating gate: {confirmed_variants}")
        print(f"Best: Var {best}  OOS Sharpe {bsh:.3f}")
        confirmed = True
    else:
        best  = best_v
        bsh   = results[f"var_{best}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best} OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        print(f"H026 12-month momentum remains optimal for ETF universe.")
        confirmed = False

    out = {
        "hypothesis": "H405",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE, "description": "beat H026 12m baseline"},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h405_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
