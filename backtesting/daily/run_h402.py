"""
H402 — H398 Var A as Production Satellite Allocation
=====================================================
H398 Var A (new H198 champion: OOS Sharpe 4.068, MaxDD -4.7%) uses:
  0.25×IMOM6 + 0.25×MOM60 + 0.25×LowVol + 0.25×IMOM12, top-2

Hypothesis: H398 Var A (30-stock large-cap momentum with quality filters)
is sufficiently uncorrelated with the production blend (H041a/H026/H045/IBS)
to earn a production sleeve. If Corr < 0.70 OOS and Sharpe improves,
allocate 10–20%.

Production baseline:
  H041a 22%, H026 27%, H045 21%, XLK IBS 20%, SMH IBS 8%, IGV IBS 2%
  OOS Sharpe ~4.158, MaxDD ~-3.60%

Variants tested:
  A:  5% H398A replacing 5% H041a       (H041a: 17%)
  B:  5% H398A replacing 5% H026        (H026: 22%)
  C: 10% H398A (-5% H041a, -5% H026)   (H041a: 17%, H026: 22%)
  D: 15% H398A (-8% H041a, -7% H026)   (H041a: 14%, H026: 20%)
  E: 20% H398A (-10% H041a, -10% H026) (H041a: 12%, H026: 17%)
  F: Production baseline (no H398A)

IS: 2013-01-01 → 2020-12-31
OOS: 2021-01-01 → 2026-06-30
Gate: OOS Sharpe > 4.158 (production baseline) as primary; MaxDD improvement secondary
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

# H198 30-stock large-cap universe
H198_UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

# Production tickers
H041A_FULL = ["SPY","QQQ","TLT","GLD","IEF","EFA","EEM","BIL",
               "EWJ","EWH","EWT","EWY","EWS","EPHE","EWG","EWQ","EWU","EWD","EWN"]
H026_BASE  = ["XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
               "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ"]
H045_PROD  = ["SHY","IEI","IEF","TLT","TIP","HYG","LQD","BKLN","EMB","BIL","MBB","FLOT","PCY"]

XLK_PARAMS = (0.15, 0.90, 7, -0.010)
SMH_PARAMS = (0.20, 0.75, 6, -0.005)
IGV_PARAMS = (0.30, 0.75, 5, 0.0025)

INITIAL_EQUITY = 100_000.0
PROD_DATA_START  = "2003-01-01"
H198_DATA_START  = "2011-01-01"
DATA_END         = "2026-06-30"

IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-06-30")

GATE_SHARPE = 4.158
GATE_MDD    = -0.036


# ── Utility ────────────────────────────────────────────────────────────────────

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


# ── H398 Var A builder ─────────────────────────────────────────────────────────

def fetch_monthly_h198(ticker):
    for prefix in ["h398","h395","h393","h386","h385","h377","h376","h373","h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{H198_DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    raw = yf.download(ticker, start=H198_DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(
        CACHE_DIR / f"h402_{ticker}_monthly_{H198_DATA_START}_{DATA_END}.parquet")
    return s


def build_h398_var_a():
    """H398 Var A: 0.25×IMOM6+0.25×MOM60+0.25×LowVol+0.25×IMOM12 top-2."""
    monthly_list = []
    for t in H198_UNIVERSE:
        try:
            monthly_list.append(fetch_monthly_h198(t))
        except Exception as e:
            print(f"    WARN {t}: {e}")
    px = pd.DataFrame(monthly_list).T.sort_index().loc[H198_DATA_START:]

    ret = px.pct_change()

    # Signals
    imom6  = px.pct_change(6)  - ret.rolling(6).sum()
    imom12 = px.pct_change(12) - ret.rolling(12).sum()
    mom60  = px.pct_change(6)
    rvol6  = ret.rolling(6).std() * np.sqrt(12)

    rank_i6  = imom6.rank(axis=1, pct=True)
    rank_i12 = imom12.rank(axis=1, pct=True)
    rank_m60 = mom60.rank(axis=1, pct=True)
    rank_lv  = rvol6.rank(axis=1, pct=True, ascending=False)

    composite = 0.25 * rank_i6 + 0.25 * rank_m60 + 0.25 * rank_lv + 0.25 * rank_i12

    port_rets = []
    months = ret.index[ret.index >= IS_START]
    for month_end in months:
        scores = composite.loc[month_end].dropna()
        if len(scores) < 2:
            continue
        selected = scores.nlargest(2).index.tolist()
        loc = ret.index.get_loc(month_end)
        r = ret.iloc[loc][selected].mean()
        port_rets.append((month_end, float(r)))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    s.name = "h398a"
    return s


# ── Production components ──────────────────────────────────────────────────────

def load_close_prod(ticker):
    for prefix in ["h112","h113","h354","h361","h362","h363","h402"]:
        for pat in [f"{prefix}_{ticker}_close.parquet",
                    f"{prefix}_{ticker}_close_{PROD_DATA_START}_{DATA_END}.parquet"]:
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
        for i in range(62, 130):
            for pat2 in [f"h{i:03d}_{ticker}_close_{PROD_DATA_START}_{DATA_END}.parquet",
                         f"h{i:03d}_{ticker}_ohlc_{PROD_DATA_START}_{DATA_END}.parquet"]:
                p = CACHE_DIR / pat2
                if p.exists():
                    df = pd.read_parquet(p)
                    df.columns = [c.lower() for c in df.columns]
                    if "close" in df.columns:
                        return df["close"].rename(ticker)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=PROD_DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h402_{ticker}_close.parquet")
    return s


def load_ohlc_prod(ticker):
    for i in range(62, 130):
        p = CACHE_DIR / f"h{i:03d}_{ticker}_ohlc_{PROD_DATA_START}_{DATA_END}.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    for prefix in ["h363","h402"]:
        p = CACHE_DIR / f"{prefix}_{ticker}_ohlc.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                return df
    print(f"  Downloading {ticker} OHLC…")
    raw = yf.download([ticker], start=PROD_DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        df = raw.xs(ticker, axis=1, level=1)[["Open","High","Low","Close"]].rename(columns=str.lower)
    else:
        df = raw[["Open","High","Low","Close"]].rename(columns=str.lower)
    df.to_parquet(CACHE_DIR / f"h402_{ticker}_ohlc.parquet")
    return df


def ibs_equity_curve(ohlc, buy, sell, hold, gap):
    df = ohlc.copy()
    denom    = (df["high"] - df["low"]).replace(0, np.nan)
    ibs      = ((df["close"] - df["low"]) / denom).clip(0.0, 1.0).fillna(0.5)
    prev_cl  = df["close"].shift(1)
    g        = (df["open"] - prev_cl) / prev_cl
    equity   = INITIAL_EQUITY
    position = days_held = 0
    series   = []
    for i in range(1, len(df)):
        prev_ibs = float(ibs.iloc[i-1])
        cur_ibs  = float(ibs.iloc[i])
        cur_gap  = float(g.iloc[i]) if not np.isnan(g.iloc[i]) else 0.0
        o  = float(df["open"].iloc[i])
        c  = float(df["close"].iloc[i])
        cp = float(df["close"].iloc[i-1])
        ret_oc = (c / o - 1) if o > 0 else 0.0
        ret_cc = (c / cp - 1) if cp > 0 else 0.0
        if position == 0:
            if prev_ibs < buy and cur_gap >= gap:
                position = 1; days_held = 1; equity *= (1 + ret_oc)
        else:
            days_held += 1; equity *= (1 + ret_cc)
            if cur_ibs > sell or days_held >= hold:
                position = 0; days_held = 0
        series.append((df.index[i], equity))
    return pd.Series([v for _, v in series],
                     index=pd.DatetimeIndex([d for d, _ in series]))


def to_monthly(eq):
    return eq.resample("ME").last().ffill().pct_change().dropna()


def build_rotation_monthly(tickers, n_hold=1):
    closes = {}
    for t in tickers:
        try:
            closes[t] = load_close_prod(t)
        except Exception as e:
            print(f"    {t}: {e}")
    daily_df   = pd.DataFrame(closes).sort_index().dropna(how="all", axis=1)
    monthly_px = daily_df.resample("ME").last()
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
    return pd.Series([v for _, v in rows],
                     index=pd.DatetimeIndex([d for d, _ in rows]))


def common_idx(*series):
    idx = series[0].index
    for s in series[1:]:
        idx = idx.intersection(s.index)
    return idx.sort_values()


def make_port(r_dict, w, idx):
    return sum(ww * r_dict[k].reindex(idx, fill_value=0.0) for k, ww in w.items())


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("H402 — H398 Var A as Production Satellite Allocation")
    print("=" * 56)
    print(f"Gate: OOS Sharpe > {GATE_SHARPE} (production baseline)")

    # Build H398 Var A
    print("\n[1] Building H398 Var A (IMOM6+MOM60+LowVol+IMOM12 top-2)…")
    h398a = build_h398_var_a()
    print(f"  H398A: {len(h398a)} months, {h398a.index[0].date()} – {h398a.index[-1].date()}")

    # Build production components
    print("\n[2] Building production components…")
    print("  H041a…")
    h041a = build_rotation_monthly(H041A_FULL, 1)
    print("  H026…")
    h026  = build_rotation_monthly(H026_BASE,  1)
    print("  H045…")
    h045  = build_rotation_monthly(H045_PROD,  2)
    print("  IBS strategies…")
    xlk_r = to_monthly(ibs_equity_curve(load_ohlc_prod("XLK"), *XLK_PARAMS))
    smh_r = to_monthly(ibs_equity_curve(load_ohlc_prod("SMH"), *SMH_PARAMS))
    igv_r = to_monthly(ibs_equity_curve(load_ohlc_prod("IGV"), *IGV_PARAMS))

    full_r = {
        "h041a": h041a, "h026": h026, "h045": h045,
        "XLK": xlk_r, "SMH": smh_r, "IGV": igv_r,
        "h398a": h398a,
    }

    # Correlation: H398A vs production baseline (OOS)
    prod_w_base = {"h041a": 0.22, "h026": 0.27, "h045": 0.21,
                   "XLK": 0.20, "SMH": 0.08, "IGV": 0.02}
    cidx_base = common_idx(*[full_r[k] for k in prod_w_base])
    base_rets  = make_port(full_r, prod_w_base, cidx_base)

    h398a_oos  = h398a[(h398a.index >= OOS_START) & (h398a.index <= OOS_END)]
    base_oos   = base_rets[(base_rets.index >= OOS_START) & (base_rets.index <= OOS_END)]
    aligned    = pd.concat([h398a_oos, base_oos], axis=1).dropna()
    corr_oos   = float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1])) if len(aligned) > 5 else float("nan")

    h398a_is   = h398a[(h398a.index >= IS_START) & (h398a.index <= IS_END)]
    base_is    = base_rets[(base_rets.index >= IS_START) & (base_rets.index <= IS_END)]
    aligned_is = pd.concat([h398a_is, base_is], axis=1).dropna()
    corr_is    = float(aligned_is.iloc[:, 0].corr(aligned_is.iloc[:, 1])) if len(aligned_is) > 5 else float("nan")

    # SPY correlation
    try:
        spy_px = fetch_monthly_h198("SPY")
        spy_ret = spy_px.pct_change().dropna()
    except Exception:
        spy_ret = pd.Series(dtype=float)

    h398a_spy = h398a.align(spy_ret, join="inner")[0]
    spy_al    = h398a.align(spy_ret, join="inner")[1]
    corr_spy  = float(h398a_spy.corr(spy_al)) if len(h398a_spy) > 5 else float("nan")

    print(f"\n  Corr(H398A, production) IS:  {corr_is:.3f}")
    print(f"  Corr(H398A, production) OOS: {corr_oos:.3f}")
    print(f"  Corr(H398A, SPY)        OOS: {corr_spy:.3f}")
    diversification_note = (
        "DIVERSIFIER (Corr < 0.70)" if corr_oos < 0.70 else
        "PARTIAL DIVERSIFIER (0.70–0.85)" if corr_oos < 0.85 else
        "HIGH CORRELATION (>0.85) — limited diversification value"
    )
    print(f"  → {diversification_note}")

    # Blend variants
    VARIANTS = {
        "A": {"h041a": 0.17, "h026": 0.27, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h398a": 0.05},
        "B": {"h041a": 0.22, "h026": 0.22, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h398a": 0.05},
        "C": {"h041a": 0.17, "h026": 0.22, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h398a": 0.10},
        "D": {"h041a": 0.14, "h026": 0.20, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h398a": 0.15},
        "E": {"h041a": 0.12, "h026": 0.17, "h045": 0.21,
               "XLK": 0.20, "SMH": 0.08, "IGV": 0.02, "h398a": 0.20},
        "F": prod_w_base,
    }
    VARIANT_NAMES = {
        "A":  "5% H398A replacing 5% H041a",
        "B":  "5% H398A replacing 5% H026",
        "C": "10% H398A (-5% H041a, -5% H026)",
        "D": "15% H398A (-8% H041a, -7% H026)",
        "E": "20% H398A (-10% H041a, -10% H026)",
        "F": "Production baseline (no H398A)",
    }

    print(f"\n[3] Blend variants")
    print(f"\n{'Var':<4} {'Description':<45} {'IS Sh':>7} {'OOS Sh':>8} {'MDD':>8} {'Neg':>4}")
    print("-" * 82)

    results = {}
    variant_rets = {}
    for vcode, w in VARIANTS.items():
        cidx = common_idx(*[full_r[k] for k in w.keys()])
        rets = make_port(full_r, w, cidx)
        variant_rets[vcode] = rets
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        results[vcode] = {"name": VARIANT_NAMES[vcode], "weights": w, "is": is_, "oos": oos_}
        beats = oos_["sharpe"] > GATE_SHARPE
        print(f"{vcode:<4} {VARIANT_NAMES[vcode]:<45} {is_['sharpe']:>7.3f} "
              f"{oos_['sharpe']:>8.3f} {oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  "
              f"{'✓' if beats else ''}")

    # Per-year OOS breakdown
    print("\n[4] OOS annual breakdown:")
    for vcode in VARIANTS:
        rets = variant_rets[vcode]
        oos_slice = rets[rets.index >= OOS_START]
        yr = oos_slice.resample("YE").apply(lambda x: (1+x).prod()-1)
        row = "  " + vcode + ": " + "  ".join(f"{yr.year}:{v:+.0%}" for yr, v in yr.items())
        print(row)

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE_SHARPE}) ===")
    test_vs = ["A","B","C","D","E"]
    confirmed = [v for v in test_vs if results[v]["oos"]["sharpe"] > GATE_SHARPE]
    best = max(test_vs, key=lambda v: results[v]["oos"]["sharpe"])
    if confirmed:
        print(f"  CONFIRMED variants: {confirmed}")
        best_sh = results[best]["oos"]["sharpe"]
        best_mdd = results[best]["oos"]["maxdd"]
        print(f"  Best: Var {best} — OOS Sharpe {best_sh:.3f}, MaxDD {best_mdd:.1%}")
        verdict = "CONFIRMED"
    else:
        print(f"  NOT CONFIRMED — best Var {best}: OOS {results[best]['oos']['sharpe']:.3f} < {GATE_SHARPE}")
        mdd_baseline = results["F"]["oos"]["maxdd"]
        mdd_best = results[best]["oos"]["maxdd"]
        if mdd_best > mdd_baseline:
            print(f"  MaxDD improvement: {mdd_baseline:.1%} → {mdd_best:.1%} ({mdd_best - mdd_baseline:.1%} improvement)")
            print(f"  PARTIAL — MaxDD improvement without Sharpe gain")
            verdict = "PARTIAL"
        else:
            print(f"  NOT CONFIRMED — no improvement in Sharpe or MaxDD")
            verdict = "NOT CONFIRMED"

    out = {
        "hypothesis": "H402",
        "gate": {"oos_sharpe_must_beat": GATE_SHARPE, "description": "beat production baseline"},
        "verdict": verdict,
        "confirmed_variants": confirmed,
        "correlations": {
            "h398a_vs_production_IS":  round(corr_is,  3),
            "h398a_vs_production_OOS": round(corr_oos, 3),
            "h398a_vs_spy_OOS":        round(corr_spy, 3),
            "diversification_note":    diversification_note,
        },
        "results": {k: v for k, v in results.items()},
    }
    op = RESULT_DIR / "h402_results.json"
    op.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {op}")
    return out


if __name__ == "__main__":
    main()
