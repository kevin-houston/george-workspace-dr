"""
H345 — OB Filter on H026 Sector ETF Rotation
=============================================
H343 showed that an Order Block strict filter on H198 stock momentum produces
OOS Sharpe 3.182 by stepping to cash when fewer than 3 large-cap stocks have
unmitigated bullish OBs. This acts as an implicit bear-market detector.

H345 tests whether the SAME mechanism generalizes to ETF rotation:
  - H026 picks the top-1 sector ETF by momentum composite score (12m mom + inv_6m_vol)
  - H345 adds: at month-end, only enter the top-ranked ETF if it has an unmitigated
    bullish OB on daily bars in the last N days; otherwise hold BIL.

Variants:
  A  Strict: top pick must have OB; else BIL
  B  Lenient: try top-2 picks; hold BIL only if neither has OB
  C  Score-weighted: require OB to enter ANY of top-3; else BIL
  D  Baseline H026 (no OB filter) for comparison

Universe: H026 expanded 25-asset (as per H112 confirmed baseline)
Signal:   12m momentum + inv_6m_vol rank composite
OB check: 30-day window, swing_length=5 (H343 reference params)
IS: 2013-2020  OOS: 2021-2026  Gate: OOS Sharpe > 1.300 (H026 production baseline ~1.35)
"""

import os, warnings
os.environ["SMC_CREDIT"] = "0"
warnings.filterwarnings("ignore")

import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from smartmoneyconcepts import smc as SMC

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

# H026 25-asset universe (from H112 confirmed)
UNIVERSE = [
    "XLK","XLE","XLF","XLV","XLI","XLB","XLU","XLRE","XLY","XLP","XLC",
    "BIL","GLD","TLT","IEF","TIP","DBC","AGG","GDX","DBA","SLV","UNG","EWZ",
    "IBB","XME",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

OB_WINDOW  = 30
SWING_LEN  = 5

# BIL is the cash proxy — never apply OB filter to BIL itself
CASH_PROXY = "BIL"


# ── Data loading ─────────────────────────────────────────────────────────────

def load_daily_close(ticker: str) -> pd.Series:
    for prefix in ["h112","h343","h344","h345"]:
        for suffix in [f"_ohlc_{DATA_START}_{DATA_END}",
                       f"_close_{DATA_START}_{DATA_END}",
                       f"_{ticker}_daily"]:
            p = CACHE_DIR / f"{prefix}_{ticker}{suffix}.parquet"
            if p.exists():
                df = pd.read_parquet(p)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                df.columns = [c.lower() for c in df.columns]
                if "close" in df.columns:
                    return df["close"].rename(ticker)
    # Try loading from h343 daily cache pattern
    p = CACHE_DIR / f"h343_{ticker}_daily.parquet"
    if p.exists():
        df = pd.read_parquet(p)
        return df["close"].rename(ticker)
    print(f"  Downloading {ticker} daily…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].rename(ticker)
    pd.DataFrame(s).to_parquet(CACHE_DIR / f"h345_{ticker}_close.parquet")
    return s


def load_daily_ohlcv(ticker: str) -> pd.DataFrame:
    # Reuse H343 daily cache (stocks overlap — sector ETFs need fresh download)
    p = CACHE_DIR / f"h343_{ticker}_daily.parquet"
    if p.exists():
        return pd.read_parquet(p)
    p2 = CACHE_DIR / f"h345_{ticker}_daily.parquet"
    if p2.exists():
        return pd.read_parquet(p2)
    # h112 ohlc cache
    for prefix in ["h112","h344"]:
        p3 = CACHE_DIR / f"{prefix}_{ticker}_ohlc_{DATA_START}_{DATA_END}.parquet"
        if p3.exists():
            df = pd.read_parquet(p3)
            df.columns = [c.lower() for c in df.columns]
            if all(c in df.columns for c in ["open","high","low","close"]):
                if "volume" not in df.columns:
                    df["volume"] = 0
                return df[["open","high","low","close","volume"]]
    print(f"  Downloading {ticker} OHLCV…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open","High","Low","Close","Volume"]].copy()
    df.columns = ["open","high","low","close","volume"]
    df.to_parquet(p2)
    return df


# ── OB detection ─────────────────────────────────────────────────────────────

def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp) -> bool:
    sub = daily_df[daily_df.index <= as_of].tail(OB_WINDOW + SWING_LEN * 2)
    if len(sub) < SWING_LEN * 2:
        return False
    try:
        ohlcv = sub[["open","high","low","close","volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=SWING_LEN)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


# ── Rotation signal ───────────────────────────────────────────────────────────

def build_signal(tickers, daily_closes):
    daily_df   = pd.DataFrame({t: daily_closes[t] for t in tickers
                                if t in daily_closes}).sort_index().dropna(how="all", axis=1)
    monthly_px  = daily_df.resample("ME").last()
    monthly_ret = daily_df.pct_change().resample("ME").apply(lambda x: (1+x).prod()-1)
    vol_6       = monthly_ret.rolling(6).std() * np.sqrt(12)
    mom_12      = monthly_px / monthly_px.shift(12) - 1
    return monthly_px, monthly_ret, vol_6, mom_12


# ── Backtest engine ───────────────────────────────────────────────────────────

def run_backtest(monthly_px, monthly_ret, vol_6, mom_12,
                 daily_data, variant: str) -> pd.Series:
    port_rets = []
    months = monthly_px.index[monthly_px.index >= IS_START]

    for i, month_end in enumerate(months):
        loc = monthly_px.index.get_loc(month_end)
        if loc < 12:
            continue

        mom_row = mom_12.iloc[loc].dropna()
        vol_row = vol_6.iloc[loc].dropna()
        valid   = mom_row.index.intersection(vol_row.index)
        # Exclude BIL from momentum ranking (it's always at bottom)
        valid   = valid[valid != CASH_PROXY]
        if len(valid) < 1:
            port_rets.append((month_end, 0.0))
            continue

        score = mom_row[valid].rank() + vol_row[valid].rank(ascending=False)
        ranked = list(score.nlargest(len(valid)).index)  # all ranked, best first

        if variant == "D":
            # Pure baseline: top-1, no OB filter
            selected = ranked[0]
            ret_this = monthly_ret.iloc[loc][selected] if selected in monthly_ret.columns else 0.0
        elif variant == "A":
            # Strict: top-1 must have OB; else BIL
            top1 = ranked[0]
            if top1 in daily_data and has_bullish_ob(daily_data[top1], month_end):
                selected = top1
            else:
                selected = CASH_PROXY
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        elif variant == "B":
            # Lenient: try top-2; BIL only if neither has OB
            selected = CASH_PROXY
            for pick in ranked[:2]:
                if pick in daily_data and has_bullish_ob(daily_data[pick], month_end):
                    selected = pick
                    break
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)
        elif variant == "C":
            # Top-3 composite: require ≥1 of top-3 to have OB; use top-1 if passes
            top3 = ranked[:3]
            any_ob = any(
                t in daily_data and has_bullish_ob(daily_data[t], month_end)
                for t in top3
            )
            if any_ob:
                selected = ranked[0]
            else:
                selected = CASH_PROXY
            ret_this = monthly_ret.iloc[loc].get(selected, 0.0)

        port_rets.append((month_end, float(ret_this) if not np.isnan(ret_this) else 0.0))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


# ── Metrics ──────────────────────────────────────────────────────────────────

def sharpe(r):
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0

def cumul(r):
    return float((1 + r).prod())

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_yrs(r):
    return int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0))

def eval_period(r, start, end):
    r = r[(r.index >= start) & (r.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0, "cagr": 0, "maxdd": 0, "neg_yrs": 0}
    return {
        "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr": round(float(r.mean() * 12), 3),
        "maxdd": round(maxdd(r), 3),
        "neg_yrs": neg_yrs(r),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("H345 — OB Filter on H026 Sector ETF Rotation")
    print("=" * 55)

    print("\nLoading daily close data for rotation signal…")
    daily_closes = {}
    for t in UNIVERSE:
        try:
            daily_closes[t] = load_daily_close(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    monthly_px, monthly_ret, vol_6, mom_12 = build_signal(UNIVERSE, daily_closes)

    print("Loading OHLCV data for OB detection…")
    daily_data = {}
    for t in UNIVERSE:
        if t == CASH_PROXY:
            continue
        try:
            daily_data[t] = load_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t} OHLCV: {e}")

    GATE = 1.300  # H026 ~1.35 confirmed; set gate slightly below for this test
    VARIANTS = {
        "A": "OB strict (top-1 must have OB; else BIL)",
        "B": "OB lenient (try top-2; BIL if neither has OB)",
        "C": "OB gate (any of top-3 has OB → enter top-1; else BIL)",
        "D": "Baseline H026 (no OB filter, top-1 momentum)",
    }

    results = {}
    print(f"\n{'Var':<4} {'Description':<45} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'Neg':>4}")
    print("-" * 80)

    for vcode, vname in VARIANTS.items():
        print(f"  Running {vcode}…", end=" ", flush=True)
        rets = run_backtest(monthly_px, monthly_ret, vol_6, mom_12,
                            daily_data, vcode)
        is_  = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        # Cash frequency in OOS
        oos_slice = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_n = (oos_slice == 0).sum()
        results[vcode] = {"name": vname, "is": is_, "oos": oos_,
                          "oos_cash_months": int(cash_n)}
        beats = oos_["sharpe"] > GATE
        print(f"\r{vcode:<4} {vname:<45} {is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>4d}  "
              f"{'✓ BEATS GATE' if beats else ''}")

    print(f"\n=== Verdict (Gate: OOS Sharpe > {GATE}) ===")
    for vcode in ["A","B","C"]:
        r = results[vcode]
        beats = r["oos"]["sharpe"] > GATE
        print(f"  {vcode} ({r['name']}): OOS {r['oos']['sharpe']:.3f} "
              f"{'✓ BEATS GATE' if beats else '< gate'} "
              f"| Cash months: {r['oos_cash_months']}")
    print(f"  D Baseline H026: OOS {results['D']['oos']['sharpe']:.3f}")

    out = {
        "hypothesis": "H345",
        "description": "OB filter on H026 sector ETF rotation",
        "gate": GATE,
        "ob_window": OB_WINDOW,
        "swing_len": SWING_LEN,
        "variants": results,
    }
    outpath = RESULT_DIR / "h345_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {outpath}")
    return out


if __name__ == "__main__":
    main()
