"""
H484 CORRECTED (H506 follow-up, 2026-08-13) — the OB-filtered strategy's beta
rank and OB "as of" date now use the PRIOR month-end instead of the current
month_end whose return is being awarded, fixing the look-ahead bias identified
in H506 (`rank_df.loc[month_end]` / `has_bullish_ob(..., month_end, ...)` both
used data through month_end's own close). The H192-D baseline-replication loop
is left unshifted intentionally -- see inline note in main().

H484 — OB Filter on H192-D Sector-Neutral BAB (Low-Volatility Anomaly family)
==============================================================================
H192-D: sector-neutral 1yr beta rank, long bottom-6 (lowest beta within each
GICS sector), monthly rebalance. OOS Sharpe=1.367, MaxDD=-17.1%, Cumul=2.518x
(hypothesis-log H192, confirmed 2026-05-12). This is the strongest confirmed
strategy in the low-volatility anomaly family and has never had the OB filter
applied to it, despite the OB filter's consistent record of improving momentum
and low-vol-ETF strategies (H343 1.174->3.182, H344 1.174->3.396, H346 2.610->
3.238, H355 bonds 1.112->1.522, H361 low-vol ETFs 1.735->1.903, H483 4.825->
4.874). H361 in particular already showed the OB filter pattern extends
cleanly from momentum to low-vol/defensive selection at the ETF level; this
tests whether it also extends to low-vol at the STOCK level.

Method: at each month-end, take the H192-D sector-neutral-beta candidate pool
(bottom-10 lowest beta stocks, instead of just bottom-6), then filter down to
stocks with a bullish unmitigated Smart-Money-Concepts order block as of that
month-end. Select bottom-6 of the OB-filtered survivors (by original beta
rank). If fewer than min_filter survive, hold cash (BIL proxy, 0% return).

Universe: 30-stock large-cap (same as H181/H188/H191/H192)
IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 1.367 (H192-D) AND MaxDD improvement >= 0.5pp vs -17.1%
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

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}
UNIVERSE = list(UNIVERSE_SECTORS.keys())
SPY      = "SPY"

DATA_START     = "2011-01-01"
DATA_END       = "2026-06-30"
IS_START       = pd.Timestamp("2013-01-01")
IS_END         = pd.Timestamp("2020-12-31")
OOS_START      = pd.Timestamp("2021-01-01")
OOS_END        = pd.Timestamp("2026-06-30")
GATE_SHARPE    = 1.367
H192D_OOS_MAXDD = -0.171
CANDIDATE_N    = 10
TOP_N          = 6

OB_GRID = [
    (20, 2, 3), (20, 3, 3), (20, 3, 5),
    (30, 2, 3), (30, 3, 3), (30, 3, 5),
]


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h484_{ticker}_ohlcv.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    df = raw[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.columns = ["open", "high", "low", "close", "volume"]
    df = df.dropna()
    df.to_parquet(cp)
    return df


def rolling_beta(stock_rets: pd.Series, spy_rets: pd.Series, window: int = 252) -> float:
    if len(stock_rets) < window // 2:
        return np.nan
    x = spy_rets.tail(window).values
    y = stock_rets.tail(window).values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < window // 3:
        return np.nan
    xm, ym = x[mask].mean(), y[mask].mean()
    cov = np.mean((x[mask] - xm) * (y[mask] - ym))
    var = np.mean((x[mask] - xm) ** 2)
    return cov / var if var > 1e-10 else np.nan


def sharpe(r):
    return 0.0 if r.std() == 0 else float(r.mean() / r.std() * np.sqrt(12))

def maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())

def neg_years(r):
    return int((r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3),
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean()*12), 3),
            "neg_yrs": neg_years(r)}


def has_bullish_ob(daily_df: pd.DataFrame, as_of: pd.Timestamp,
                    window: int, swing_len: int) -> bool:
    sub = daily_df[daily_df.index <= as_of].tail(window + swing_len * 2)
    if len(sub) < swing_len * 2:
        return False
    try:
        ohlcv = sub[["open", "high", "low", "close", "volume"]]
        swings = SMC.swing_highs_lows(ohlcv, swing_length=swing_len)
        ob = SMC.ob(ohlcv, swings)
    except Exception:
        return False
    bull = ob[(ob["OB"] == 1) & (ob["Bottom"].notna())]
    return len(bull) > 0


def compute_sector_neutral_beta_ranks(daily_px: pd.DataFrame, spy_px: pd.Series) -> pd.DataFrame:
    """Monthly sector-neutral beta rank matrix (lower rank = lower beta = more desirable)."""
    monthly_px = daily_px.resample("ME").last()
    daily_rets = daily_px.pct_change()
    spy_daily_rets = spy_px.pct_change()
    sectors = pd.Series(UNIVERSE_SECTORS)

    rows = {}
    for month_end in monthly_px.index:
        hist_rets = daily_rets[daily_rets.index <= month_end]
        spy_hist = spy_daily_rets[spy_daily_rets.index <= month_end]
        if len(hist_rets) < 130:
            continue
        spy_ser = spy_hist.tail(252)
        betas = {}
        for t in UNIVERSE:
            if t not in hist_rets.columns:
                continue
            b = rolling_beta(hist_rets[t], spy_ser, window=252)
            if pd.notna(b):
                betas[t] = b
        if len(betas) < TOP_N * 2:
            continue
        beta_series = pd.Series(betas)
        common = beta_series.index.intersection(sectors.index)
        df_tmp = pd.DataFrame({"beta": beta_series[common], "sector": sectors[common]})
        df_tmp["rank_in_sector"] = df_tmp.groupby("sector")["beta"].rank(ascending=True)
        rows[month_end] = df_tmp["rank_in_sector"]

    return pd.DataFrame(rows).T


def backtest_ob(monthly_px, rank_df, daily_data, ob_window, min_filter, swing_len,
                 candidate_n=CANDIDATE_N, top_n=TOP_N):
    # H506 fix: both the beta rank AND the OB detection must be computed as of
    # the PRIOR month-end, not the current month_end whose return is being
    # awarded — the original used month_end's own close in both the 252d
    # rolling beta window (hist_rets.index <= month_end) and the OB "as_of"
    # date, which is only knowable once month_end has already closed.
    monthly_ret = monthly_px.pct_change()
    rank_df_shifted = rank_df.shift(1)
    month_ends = list(rank_df.index)
    port_rets = []
    for i, month_end in enumerate(month_ends):
        if month_end not in monthly_ret.index:
            continue
        if i == 0:
            continue
        signal_asof = month_ends[i - 1]  # prior month-end: knowable before month_end
        scores = rank_df_shifted.loc[month_end].dropna()
        if len(scores) < 1:
            port_rets.append((month_end, 0.0))
            continue
        # lowest rank_in_sector value = lowest beta = most desirable -> nsmallest
        candidates = scores.nsmallest(min(candidate_n, len(scores))).index.tolist()

        filtered = []
        for ticker in candidates:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], signal_asof, ob_window, swing_len):
                filtered.append(ticker)
            if len(filtered) >= top_n:
                break

        if len(filtered) < min_filter:
            port_rets.append((month_end, 0.0))
            continue

        selected = filtered[:top_n]
        loc = monthly_ret.index.get_loc(month_end)
        ret_this = float(monthly_ret.iloc[loc][selected].mean())
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def load_prices():
    cache = CACHE_DIR / f"h188_daily_2012-01-01_2026-04-30.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
        need_refresh = df.index.max() < pd.Timestamp("2026-06-01")
    else:
        df = None
        need_refresh = True

    if need_refresh:
        print("  Downloading fresh daily prices (extending through 2026-06-30)...")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        cp2 = CACHE_DIR / f"h484_universe_daily_{DATA_START}_{DATA_END}.parquet"
        df.dropna(how="all", axis=0).to_parquet(cp2)
        df = pd.read_parquet(cp2)

    if SPY not in df.columns:
        spy_raw = yf.download(SPY, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        spy_px = spy_raw["Close"] if "Close" in spy_raw.columns else spy_raw.squeeze()
        spy_px = spy_px.reindex(df.index, method="ffill")
        df[SPY] = spy_px

    spy_px = df[SPY].copy()
    stock_px = df[UNIVERSE].copy()
    return stock_px, spy_px


def main():
    print("H484 — OB Filter on H192-D Sector-Neutral BAB")
    print("=" * 70)

    print("\nLoading prices...")
    daily_px, spy_px = load_prices()
    print(f"  {daily_px.shape[1]} tickers, {len(daily_px)} daily obs")

    print("Loading OHLCV for OB detection...")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    print("Computing H192-D sector-neutral beta ranks...")
    rank_df = compute_sector_neutral_beta_ranks(daily_px, spy_px)
    monthly_px = daily_px.resample("ME").last()

    print("\nReplicating H192-D baseline (bottom-6, no OB filter)...")
    # NOTE (H506 follow-up): this loop intentionally reproduces H192-D's ORIGINAL
    # (unshifted) signal indexing, since its purpose is to sanity-check against the
    # existing H192-D log entry's number. H192-D itself may have the same
    # rank_df.loc[month_end]-without-shift pattern -- that is a separate,
    # not-yet-audited hypothesis and out of scope for this H484-focused fix.
    monthly_ret = monthly_px.pct_change()
    base_rets = []
    for month_end in rank_df.index:
        if month_end not in monthly_ret.index:
            continue
        scores = rank_df.loc[month_end].dropna()
        selected = scores.nsmallest(min(TOP_N, len(scores))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        base_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    base_series = pd.Series({d: r for d, r in base_rets})
    base_series.index = pd.DatetimeIndex(base_series.index)
    base_is = eval_period(base_series, IS_START, IS_END)
    base_oos = eval_period(base_series, OOS_START, OOS_END)
    print(f"  Baseline replication: IS Sharpe={base_is['sharpe']:.3f}  "
          f"OOS Sharpe={base_oos['sharpe']:.3f}  OOS MaxDD={base_oos['maxdd']:.1%}  "
          f"(log reference: IS~1.203 OOS~1.367 MaxDD~-17.1%)")

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement >= 0.5pp vs {H192D_OOS_MAXDD:.1%}")
    print(f"\n{'Win':>4} {'Min':>4} {'Swg':>4} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'MDDimp(pp)':>11} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 75)

    results = []
    for ob_window, min_filter, swing_len in OB_GRID:
        rets = backtest_ob(monthly_px, rank_df, daily_data, ob_window, min_filter, swing_len)
        is_ = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
        mdd_improvement_pp = (oos_["maxdd"] - H192D_OOS_MAXDD) * 100
        beats_sharpe = oos_["sharpe"] > GATE_SHARPE
        beats_mdd = mdd_improvement_pp >= 0.5
        beats_both = beats_sharpe and beats_mdd
        print(f"{ob_window:>4} {min_filter:>4} {swing_len:>4} "
              f"{is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {mdd_improvement_pp:>10.2f}pp {cash_pct:>6.1f}% "
              f"{'✓' if beats_both else '✗':>6}")
        results.append({
            "ob_window": ob_window, "min_filter": min_filter, "swing_len": swing_len,
            "is": is_, "oos": oos_, "oos_cash_pct": round(cash_pct, 1),
            "mdd_improvement_pp": round(mdd_improvement_pp, 2),
            "beats_sharpe_gate": beats_sharpe, "beats_mdd_gate": beats_mdd,
            "beats_both_gates": beats_both,
        })

    n_pass = sum(r["beats_both_gates"] for r in results)
    best = max(results, key=lambda r: r["oos"]["sharpe"])
    print(f"\n=== Summary ===")
    print(f"Baseline (H192-D replication): OOS Sharpe {base_oos['sharpe']:.3f}, MaxDD {base_oos['maxdd']:.1%}")
    print(f"Variants passing BOTH gates: {n_pass}/{len(OB_GRID)}")
    print(f"Best OOS Sharpe: {best['oos']['sharpe']:.3f} "
          f"(window={best['ob_window']}, min_filter={best['min_filter']}, swing_len={best['swing_len']}), "
          f"MaxDD={best['oos']['maxdd']:.1%}, cash%={best['oos_cash_pct']:.1f}")

    if n_pass > 0:
        print(f"\nVERDICT: CONFIRMED — {n_pass} variant(s) beat both the Sharpe and MaxDD gates.")
    else:
        best_sharpe_only = max(results, key=lambda r: r["oos"]["sharpe"])
        if best_sharpe_only["beats_sharpe_gate"]:
            print(f"\nVERDICT: PARTIAL CONFIRMED — best variant beats Sharpe gate but MaxDD "
                  f"improvement insufficient ({best_sharpe_only['mdd_improvement_pp']:.2f}pp < 0.5pp).")
        else:
            print(f"\nVERDICT: NOT CONFIRMED — no variant beats OOS Sharpe {GATE_SHARPE} "
                  f"(best {best_sharpe_only['oos']['sharpe']:.3f}).")

    out = {
        "hypothesis": "H484",
        "description": "OB filter on H192-D sector-neutral BAB (bottom-10 candidate pool -> OB filter -> bottom-6)",
        "gate_sharpe": GATE_SHARPE,
        "gate_mdd_improvement_pp": 0.5,
        "h192d_baseline_replication": {"is": base_is, "oos": base_oos},
        "n_variants": len(OB_GRID),
        "n_pass_both_gates": n_pass,
        "variants": results,
    }
    outpath = RESULT_DIR / "h484_corrected_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
