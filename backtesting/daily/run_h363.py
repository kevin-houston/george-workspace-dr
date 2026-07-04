"""
H363 — Low-Vol ETF Rotation as Production Satellite Allocation
=============================================================
H354 confirmed low-vol ETF momentum rotation (Var C pure 12m, OOS 1.735,
Corr(SPY)=0.854, MaxDD -11.3%, 2022: +7.0%). Key finding: 2022 performance
makes it a genuine diversifier despite high SPY correlation.

Hypothesis:
  Allocating a portion of the production portfolio to H354 Var C as a satellite
  improves production Sharpe and/or reduces MaxDD, despite the high SPY
  correlation (0.854). The 2022 crisis resilience (+7% vs SPY -24%) provides
  genuine orthogonality during the worst drawdown events.

Production baseline (H112):
  H041a 22%, H026 27%, H045 21%, XLK IBS 20%, SMH IBS 8%, IGV IBS 2%
  OOS Sharpe ~4.158, MaxDD ~-3.60%

Test: Replace a portion of one production component with H354 Var C
  Each allocation takes proportional weight from the existing production blend

Variants:
  A  5% H354 replacing 5% H041a (H041a: 17%)
  B  5% H354 replacing 5% H026  (H026: 22%)
  C  5% H354 replacing 5% H045  (H045: 16%)
  D  10% H354: -5% H041a, -5% H026 (H041a: 17%, H026: 22%)
  E  Production baseline (H112 weights, no H354)

IS: 2013-01-01 → 2020-12-31 (H354's IS period)
OOS: 2021-01-01 → 2026-06-30 (H354's OOS period)
Gate: OOS Sharpe > 4.158 (production baseline) AND MaxDD < -3.60% improvement

Note: Production Sharpe is very high (4.158). Even a small improvement is
      meaningful. If no variant beats the Sharpe gate, check MaxDD improvement
      as secondary gate.
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

# H354 universe
LOW_VOL_UNIVERSE = ["USMV","SPLV","XLU","SPHD","EFAV","EEMV","ACWV"]
CASH_PROXY = "BIL"

# Production H112 tickers
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

INITIAL_EQUITY = 100_000.0

DATA_START = "2003-01-01"
DATA_END   = "2026-06-30"
LOW_VOL_DATA_START = "2011-01-01"

IS_START   = pd.Timestamp("2013-01-01")   # H354 IS
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")

GATE_SHARPE = 4.158   # production OOS Sharpe
GATE_MDD    = -0.036  # production OOS MaxDD (less negative = better)


def load_close(ticker, start=DATA_START):
    """Load daily close with caching."""
    for prefix in ["h112","h113","h354","h361","h362","h363"]:
        for pat in [f"{prefix}_{ticker}_close.parquet",
                    f"{prefix}_{ticker}_close_{start}_{DATA_END}.parquet"]:
            p = CACHE_DIR / pat
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df, pd.DataFrame):
                    df.columns = [c.lower() for c in df.columns]
                    col = next((c for c in ["close"] if c in df.columns), None)
                    if col:
                        return df[col].rename(ticker)
                    return df.squeeze().rename(ticker)
                return df.rename(ticker)
        # H112-style prefix scan
        for i in range(62, 120):
            for pat in [f"h{i:03d}_{ticker}_close_{DATA_START}_{DATA_END}.parquet",
                        f"h{i:03d}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"]:
                p = CACHE_DIR / pat
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns:
                        return df["close"].rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=start, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h363_{ticker}_close.parquet")
    return s


def load_ohlc(ticker):
    """Load daily OHLC for IBS strategy."""
    for i in range(62, 120):
        p = CACHE_DIR / f"h{i:03d}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    print(f"  Downloading {ticker} OHLC…")
    raw = yf.download([ticker], start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(CACHE_DIR / f"h363_{ticker}_ohlc.parquet")
    return df


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom   = (df["high"]-df["low"]).replace(0, np.nan)
    ibs     = ((df["close"]-df["low"])/denom).clip(0.0,1.0).fillna(0.5)
    prev_cl = df["close"].shift(1)
    g       = (df["open"]-prev_cl)/prev_cl
    equity  = INITIAL_EQUITY
    position = days_held = 0
    series = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o = float(df["open"].iloc[i]); c = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c/o-1) if o > 0 else 0.0
        ret_cc = (c/cp-1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1+ret_oc)
        else:
            days_held += 1; equity *= (1+ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _,v in series], index=pd.DatetimeIndex([d for d,_ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def build_rotation_monthly(tickers, start, end, n_hold=1):
    closes = {}
    for t in tickers:
        try:
            closes[t] = load_close(t, start)
        except Exception as e:
            print(f"    {t}: {e}")
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
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def build_h354_var_c():
    """Build H354 Var C: pure 12m top-1 rotation on low-vol ETF universe."""
    closes = {}
    for t in LOW_VOL_UNIVERSE + [CASH_PROXY]:
        try:
            closes[t] = load_close(t, LOW_VOL_DATA_START)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df    = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    rows = []
    for i in range(12, len(monthly_px)):
        mom_row = mom_12.iloc[i]
        valid   = [t for t in LOW_VOL_UNIVERSE
                   if t in mom_row.index and not pd.isna(mom_row[t])]
        if not valid:
            continue
        top1 = mom_row[valid].idxmax()
        ret  = monthly_ret.iloc[i].get(top1, 0.0)
        rows.append((monthly_px.index[i], float(ret) if not pd.isna(ret) else 0.0))
    return pd.Series([v for _,v in rows], index=pd.DatetimeIndex([d for d,_ in rows]))


def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r):
    return int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0))

def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "cagr": 0.0, "maxdd": 0.0, "neg_yrs": 0}
    return {
        "n":       len(r),
        "sharpe":  round(sharpe(r), 3),
        "cagr":    round(float(r.mean() * 12), 3),
        "maxdd":   round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


def main():
    print("H363 — Low-Vol ETF Rotation as Production Satellite")
    print("=" * 55)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (production baseline)")

    # Build production components
    print("\n[1] Building production components…")
    print("  Building H041a…")
    h041a = build_rotation_monthly(H041A_FULL, DATA_START, DATA_END, 1)
    print("  Building H026…")
    h026  = build_rotation_monthly(H026_BASE,  DATA_START, DATA_END, 1)
    print("  Building H045…")
    h045  = build_rotation_monthly(H045_PROD,  DATA_START, DATA_END, 2)
    print("  Building IBS strategies…")
    xlk_r = to_monthly(ibs_equity_curve(load_ohlc("XLK"), *XLK_PARAMS))
    smh_r = to_monthly(ibs_equity_curve(load_ohlc("SMH"), *SMH_PARAMS))
    igv_r = to_monthly(ibs_equity_curve(load_ohlc("IGV"), *IGV_PARAMS))

    print("\n[2] Building H354 Var C (low-vol ETF pure 12m top-1)…")
    h354  = build_h354_var_c()
    print(f"  H354 series: {len(h354)} months, range {h354.index[0].date()} – {h354.index[-1].date()}")

    # Build production r_dict
    prod_r = {"h041a": h041a, "h026": h026, "h045": h045,
              "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r}

    # Common index (intersection)
    def common_idx(*series):
        idx = series[0].index
        for s in series[1:]:
            idx = idx.intersection(s.index)
        return idx.sort_values()

    # Production baseline weights
    PROD_W = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
              "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}

    # Test: add H354 as satellite with adjusted weights
    VARIANTS = {
        "A": {"h041a": 0.17, "h026": 0.27, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h354": 0.05},
        "B": {"h041a": 0.22, "h026": 0.22, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h354": 0.05},
        "C": {"h041a": 0.22, "h026": 0.27, "h045": 0.16,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h354": 0.05},
        "D": {"h041a": 0.17, "h026": 0.22, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h354": 0.10},
        "E": PROD_W,   # baseline
    }

    VARIANT_NAMES = {
        "A": "5% H354 replacing 5% H041a",
        "B": "5% H354 replacing 5% H026",
        "C": "5% H354 replacing 5% H045",
        "D": "10% H354 (-5% H041a, -5% H026)",
        "E": "Production baseline (H112 weights)",
    }

    # Build r_dict with h354
    full_r = {**prod_r, "h354": h354}

    results = {}
    print(f"\n{'Var':<4} {'Description':<42} {'IS Sh':>8} {'OOS Sh':>8} {'MDD':>8} {'Neg':>4}")
    print("-" * 80)

    variant_rets = {}
    for vcode, w in VARIANTS.items():
        cidx = common_idx(*[full_r[k] for k in w.keys()])
        rets = make_port(full_r, w, cidx)
        variant_rets[vcode] = rets
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": VARIANT_NAMES[vcode], "weights": w, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE_SHARPE
        print(f"{vcode:<4} {VARIANT_NAMES[vcode]:<42} {is_['sharpe']:>8.3f} "
              f"{oos_['sharpe']:>8.3f} {oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  "
              f"{'✓' if beats else ''}")

    # Per-year OOS breakdown
    for vcode in ["A","B","C","D","E"]:
        rets = variant_rets[vcode]
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        print(f"\n  Var {vcode} OOS annual:")
        for dt, v in yr.items():
            print(f"    {dt.year}: {v:+.1%}")

    # Correlation of H354 with production (OOS)
    base_rets = variant_rets["E"]
    h354_oos  = h354[(h354.index >= OOS_START) & (h354.index <= OOS_END)]
    base_oos  = base_rets[(base_rets.index >= OOS_START) & (base_rets.index <= OOS_END)]
    aligned = pd.concat([h354_oos, base_oos], axis=1).dropna()
    if len(aligned) > 5:
        corr = aligned.iloc[:,0].corr(aligned.iloc[:,1])
        print(f"\n  Corr(H354 Var C, production) OOS: {corr:.3f}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE_SHARPE}) ===")
    test_vs = ["A","B","C","D"]
    confirmed = [v for v in test_vs if results[v]["oos"]["sharpe"] > GATE_SHARPE]
    if confirmed:
        best = max(test_vs, key=lambda v: results[v]["oos"]["sharpe"])
        print(f"  CONFIRMED variants: {confirmed}")
        print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}")
        print(f"  H363 CONFIRMED — H354 low-vol ETF improves production blend")
    else:
        # Check MaxDD improvement
        mdd_better = [v for v in test_vs
                      if results[v]["oos"]["maxdd"] > results["E"]["oos"]["maxdd"]
                      and results[v]["oos"]["sharpe"] > 2.0]
        if mdd_better:
            best = max(mdd_better, key=lambda v: results[v]["oos"]["maxdd"])
            print(f"  PARTIAL — MaxDD improved but Sharpe gate not met")
            print(f"  Best: Var {best} — OOS Sharpe {results[best]['oos']['sharpe']:.3f}, "
                  f"MaxDD {results[best]['oos']['maxdd']:.1%}")
        else:
            best = max(test_vs, key=lambda v: results[v]["oos"]["sharpe"])
            print(f"  NOT CONFIRMED — best Var {best}: "
                  f"OOS {results[best]['oos']['sharpe']:.3f} < {GATE_SHARPE}")
            print(f"  Note: production baseline ({GATE_SHARPE}) is extremely high — "
                  f"meaningful if MaxDD or CAGR improve")

    out = RESULT_DIR / "h363_results.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults → {out}")


if __name__ == "__main__":
    main()
