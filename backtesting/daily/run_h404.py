"""
H404: FRED Composite Macro Regime Gate on H026 ETF Rotation
=============================================================
H300 (yield curve alone, NOT CONFIRMED) and H299 (breadth alone, NOT CONFIRMED)
both failed as single macro signals. Hypothesis: a COMPOSITE of 4 orthogonal
FRED economic indicators produces a more robust macro regime signal than
any single series.

Theory: Economic expansions favor equity ETFs (high momentum signal pays off).
Recessions/contractions favor cash (BIL). A multi-series composite captures
NBER-like recession probability from leading + coincident indicators.

FRED Signals (all lagged 1 month for publication delay):
  UNRATE  — unemployment rate 3m change: RISING = bad (weight: -1)
  T10Y2Y  — 10Y-2Y yield curve slope: INVERTED = bad (weight: +1)
  PAYEMS  — nonfarm payrolls YoY%: FALLING = bad (weight: +1)
  INDPRO  — industrial production 3m ann. growth: FALLING = bad (weight: +1)

Each series z-scored over trailing 36 months. Equal-weight composite.
If composite > threshold → hold H026 top-1; else → BIL.

H026 momentum baseline: dual-rank (12m momentum + low 6m vol), top-1, 23 ETFs
(matches run_h402 build_rotation_monthly logic exactly).

Variants:
  A: Composite > 0 gate (expansion filter, ~40% cash expected)
  B: Composite > 0.5 gate (strict expansion, ~60% cash)
  C: Composite > -0.5 gate (mild recession filter, ~20% cash)
  D: No macro gate (H026 sanity check — must match known ~1.2 OOS Sharpe)

IS: 2013-2020  OOS: 2021-2026  Gate: OOS Sharpe > 1.529 (H301 200MA-gated H026)
"""

import warnings
warnings.filterwarnings("ignore")

import json
import os
import time
import urllib3
import numpy as np
import pandas as pd
import yfinance as yf
import requests
import requests.adapters as _ra
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_orig_send = _ra.HTTPAdapter.send
def _no_verify_send(self, request, **kwargs):
    kwargs['verify'] = False
    return _orig_send(self, request, **kwargs)
_ra.HTTPAdapter.send = _no_verify_send

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
DATA_START   = "2003-01-01"
DATA_END     = "2026-06-30"
IS_START     = pd.Timestamp("2013-01-01")
IS_END       = pd.Timestamp("2020-12-31")
OOS_START    = pd.Timestamp("2021-01-01")
OOS_END      = pd.Timestamp("2026-06-30")
GATE_SHARPE  = 1.529   # beat H301 (200MA-gated H026)

H026_UNIVERSE = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
]


def load_close(ticker: str) -> pd.Series:
    """Load daily close prices, from cache if available."""
    for prefix in ["h112","h113","h354","h361","h362","h363","h402","h404"]:
        for pat in [f"{prefix}_{ticker}_close.parquet",
                    f"{prefix}_{ticker}_close_{DATA_START}_{DATA_END}.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df, pd.DataFrame):
                    df.columns = [c.lower() for c in df.columns]
                    col = next((c for c in ["close"] if c in df.columns), None)
                    if col:
                        return df[col].rename(ticker)
                return df.squeeze().rename(ticker)
        for i in range(62, 130):
            for pat2 in [f"h{i:03d}_{ticker}_close_{DATA_START}_{DATA_END}.parquet"]:
                p = CACHE_DIR / pat2
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
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h404_{ticker}_close.parquet")
    return s


def build_h026_monthly(tickers: list, n_hold: int = 1) -> tuple[pd.Series, pd.DataFrame]:
    """
    Exact replica of run_h402's build_rotation_monthly:
    dual-rank (12m momentum + low 6m vol) top-n monthly rotation.
    Returns (portfolio_monthly_returns, monthly_px).
    """
    closes = {}
    for t in tickers:
        try:
            closes[t] = load_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    vol_6       = monthly_ret.rolling(6).std() * np.sqrt(12)

    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)
        rows.append((monthly_px.index[i], monthly_ret.iloc[i][top_n].mean()))

    port = pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))
    return port, monthly_px, monthly_ret, mom_12, vol_6


def build_h026_with_macro_gate(monthly_px, monthly_ret, mom_12, vol_6,
                                bil_ret: pd.Series, macro_score: pd.Series,
                                threshold: float, n_hold: int = 1) -> pd.Series:
    """H026 rotation with FRED macro gate: if macro <= threshold → BIL."""
    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i].dropna()
        vol_row = vol_6.iloc[i].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        if len(valid) < n_hold:
            continue
        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        top_n = list(score.nlargest(n_hold).index)

        dt      = monthly_px.index[i]
        macro_v = macro_score.get(dt, float("nan"))

        if not pd.isna(macro_v) and macro_v <= threshold:
            ret_this = bil_ret.get(dt, 0.0)
        else:
            ret_this = float(monthly_ret.iloc[i][top_n].mean())

        rows.append((dt, ret_this))

    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def fetch_fred(series_id: str) -> pd.Series:
    cp = CACHE_DIR / f"fred_{series_id}.parquet"
    if cp.exists():
        age = time.time() - cp.stat().st_mtime
        if age < 86400 * 7:
            return pd.read_parquet(cp).squeeze().rename(series_id)
    url = (
        f"https://api.stlouisfed.org/fred/series/observations"
        f"?series_id={series_id}&api_key={FRED_API_KEY}&file_type=json"
        f"&observation_start={DATA_START}&observation_end={DATA_END}"
    )
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    obs  = resp.json()["observations"]
    s    = pd.Series(
        {pd.Timestamp(o["date"]): float(o["value"]) for o in obs if o["value"] != "."}
    ).rename(series_id)
    pd.DataFrame(s).to_parquet(cp)
    return s


def build_macro_score_monthly(unrate, t10y2y, payems, indpro,
                               monthly_index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Build monthly macro composite. All signals lagged 1 month (publication delay).
    Returns DataFrame with 'composite' and component z-scores.
    """
    def to_monthly(s: pd.Series) -> pd.Series:
        return s.resample("ME").last().reindex(monthly_index, method="ffill")

    ur  = to_monthly(unrate)
    yc  = to_monthly(t10y2y)
    pay = to_monthly(payems)
    ip  = to_monthly(indpro)

    ur_chg  = ur.diff(3)
    yc_lvl  = yc
    pay_yoy = pay.pct_change(12) * 100
    ip_chg  = ip.pct_change(3) * 400

    def zscore36(s):
        mu = s.rolling(36).mean()
        sd = s.rolling(36).std()
        return (s - mu) / sd.replace(0, float("nan"))

    z_ur  = -zscore36(ur_chg)
    z_yc  = +zscore36(yc_lvl)
    z_pay = +zscore36(pay_yoy)
    z_ip  = +zscore36(ip_chg)

    composite = (z_ur + z_yc + z_pay + z_ip) / 4

    df = pd.DataFrame({
        "composite": composite,
        "z_ur":  z_ur,
        "z_yc":  z_yc,
        "z_pay": z_pay,
        "z_ip":  z_ip,
    }, index=monthly_index)

    return df.shift(1)   # 1-month publication lag


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


def main():
    print("H404 — FRED Composite Macro Regime Gate on H026")
    print("=" * 60)

    if not FRED_API_KEY:
        print("ERROR: FRED_API_KEY not set"); return

    # Build H026 rotation (baseline)
    print("\nBuilding H026 rotation (dual-rank, top-1)…")
    h026_rets, monthly_px, monthly_ret, mom_12, vol_6 = build_h026_monthly(H026_UNIVERSE)
    bil_ret = monthly_ret.get("BIL", pd.Series(0.0, index=monthly_ret.index))

    # Verify baseline
    h026_i = eval_period(h026_rets, IS_START, IS_END)
    h026_o = eval_period(h026_rets, OOS_START, OOS_END)
    print(f"  H026 baseline IS {h026_i['sharpe']:.3f} | OOS {h026_o['sharpe']:.3f}  "
          f"MaxDD {h026_o['maxdd']:.1%}  (expected OOS ~1.20)")

    # Load FRED data
    print("\nLoading FRED series…")
    try:
        unrate = fetch_fred("UNRATE")
        t10y2y = fetch_fred("T10Y2Y")
        payems = fetch_fred("PAYEMS")
        indpro = fetch_fred("INDPRO")
        print(f"  UNRATE {len(unrate)} / T10Y2Y {len(t10y2y)} / PAYEMS {len(payems)} / INDPRO {len(indpro)}")
    except Exception as e:
        print(f"  FRED error: {e}"); return

    macro = build_macro_score_monthly(unrate, t10y2y, payems, indpro, monthly_px.index)
    print(f"  Macro composite built: {len(macro)} months, "
          f"non-NaN: {macro['composite'].notna().sum()}")
    print(f"  Composite > 0: {(macro['composite']>0).sum()} months "
          f"({(macro['composite']>0).mean():.0%})")

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

    print(f"\n=== References ===")
    print(f"H026 baseline (no gate)  IS {h026_i['sharpe']:.3f} | OOS {h026_o['sharpe']:.3f}  MaxDD {h026_o['maxdd']:.1%}")
    print(f"H301 (SPY>200MA gate)    IS  n/a | OOS  1.529  MaxDD  n/a")
    print(f"SPY buy-and-hold         IS {si['sharpe']:.3f} | OOS {so['sharpe']:.3f}  MaxDD {so['maxdd']:.1%}")

    variants = {
        "A": dict(threshold=0.0,  desc="Composite >  0 gate (~40% cash)"),
        "B": dict(threshold=0.5,  desc="Composite >0.5 gate (~60% cash)"),
        "C": dict(threshold=-0.5, desc="Composite >-0.5 gate (~20% cash, mild)"),
        "D": dict(threshold=float("-inf"), desc="No gate (H026 sanity check)"),
    }

    macro_score = macro["composite"]

    print(f"\n{'Var':<4} {'IS Sh':>7} {'OOS Sh':>8} {'OOS MDD':>9} {'CAGR%':>7} {'NegY':>5} {'Cash%':>7}  Desc")
    print("-" * 115)
    print(f"{'REF':4} {h026_i['sharpe']:>7.3f} {h026_o['sharpe']:>8.3f} {h026_o['maxdd']:>9.1%} "
          f"{h026_o['cagr']*100:>6.1f}% {h026_o['neg_yrs']:>5d} {'  ---':>7}  H026 no-gate baseline")

    results = {"h026_baseline": {"is": h026_i, "oos": h026_o}, "spy": {"is": si, "oos": so}}
    confirmed_variants = []

    for var_id, cfg in variants.items():
        th = cfg["threshold"]
        if th == float("-inf"):
            rets = h026_rets
        else:
            rets = build_h026_with_macro_gate(
                monthly_px, monthly_ret, mom_12, vol_6, bil_ret, macro_score, th
            )
        vi  = eval_period(rets, IS_START, IS_END)
        vo  = eval_period(rets, OOS_START, OOS_END)

        # Cash fraction
        if th == float("-inf"):
            cf = 0.0
        else:
            macro_oos = macro_score.reindex(monthly_px.index)
            valid = macro_oos[macro_oos.index >= IS_START].dropna()
            cf = (valid <= th).sum() / len(valid) if len(valid) else 0.0

        beat = vo["sharpe"] > GATE_SHARPE
        flag = " ✓ BEATS H301" if beat else ""
        print(f"Var {var_id}  {vi['sharpe']:>7.3f} {vo['sharpe']:>8.3f} {vo['maxdd']:>9.1%} "
              f"{vo['cagr']*100:>6.1f}% {vo['neg_yrs']:>5d} {cf:>7.0%}  {cfg['desc']}{flag}")
        results[f"var_{var_id}"] = {
            "is": vi, "oos": vo, "desc": cfg["desc"],
            "cash_fraction": round(cf, 3), "beats_h301": beat,
        }
        if beat:
            confirmed_variants.append(var_id)

    # Annual breakdown of best OOS variant
    best_v = max(variants.keys(), key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
    cfg = variants[best_v]
    rets_best = (h026_rets if cfg["threshold"] == float("-inf") else
                 build_h026_with_macro_gate(monthly_px, monthly_ret, mom_12, vol_6,
                                             bil_ret, macro_score, cfg["threshold"]))
    print(f"\n=== Var {best_v} annual returns ===")
    ann = rets_best.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    for yr, ret in ann.items():
        tag = " ← OOS" if yr.year >= 2021 else ""
        print(f"  {yr.year}: {ret:+.1%}{tag}")

    print(f"\n=== Macro signal quality (OOS 2021-2026) ===")
    oos_macro = macro_score[(macro_score.index >= OOS_START) & (macro_score.index <= OOS_END)]
    print(f"  Mean: {oos_macro.mean():.2f}  Std: {oos_macro.std():.2f}")
    print(f"  Months >0: {(oos_macro>0).sum()}/{len(oos_macro)} ({(oos_macro>0).mean():.0%})")

    print(f"\n=== Verdict ===")
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (beat H301 200MA-gated H026)")
    if confirmed_variants:
        best  = max(confirmed_variants, key=lambda v: results[f"var_{v}"]["oos"]["sharpe"])
        bsh   = results[f"var_{best}"]["oos"]["sharpe"]
        print(f"CONFIRMED — variants: {confirmed_variants}")
        print(f"Best: Var {best}  OOS Sharpe {bsh:.3f}")
        confirmed = True
    else:
        best  = best_v
        bsh   = results[f"var_{best}"]["oos"]["sharpe"]
        print(f"NOT CONFIRMED — best Var {best} OOS Sharpe {bsh:.3f} < gate {GATE_SHARPE}")
        confirmed = False

    out = {
        "hypothesis": "H404",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE, "description": "beat H301 200MA-gated H026"},
        "confirmed": confirmed,
        "confirmed_variants": confirmed_variants,
        "results": results,
    }
    op = RESULT_DIR / "h404_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
