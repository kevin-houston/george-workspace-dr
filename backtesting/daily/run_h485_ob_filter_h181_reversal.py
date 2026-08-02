"""
H485 — OB Filter on H181 Industry-Adjusted Short-Term Reversal (Stock Momentum family)
=========================================================================================
H181: signal = R_i(t) - R_industry_mean(t) (monthly return minus equal-weight sector
mean); long bottom-6 (most negative industry-adjusted return = strongest reversal
candidates), monthly rebalance. OOS Sharpe=1.138, MaxDD=-18.4%, Cumul=3.233x
(hypothesis-log H181, confirmed 2026-05-08). Low correlation with H026
(Corr=0.293 OOS) makes H181 a genuine production diversification candidate, but it
has never had the OB filter applied despite the filter's consistent record across
the momentum family (H343, H344, H345, H346, H476, H483) and now the low-vol family
(H484, same session).

Economic rationale for applying OB here: H181 buys stocks that just underperformed
their sector (potential reversal candidates). Not every beaten-down stock reverts —
some are breaking down structurally. Requiring a bullish Smart-Money-Concepts order
block (institutional accumulation zone) as of month-end should filter OUT stocks
that are still in pure distribution and keep only reversal candidates where smart
money is already stepping in — the same "quality confirmation" role OB plays in the
momentum variants.

Method: at each month-end, take the H181 candidate pool (bottom-10 most negative
industry-adjusted return, instead of just bottom-6), filter down to stocks with a
bullish unmitigated order block as of that month-end, and select the bottom-6 (by
original signal rank) of the OB-filtered survivors. If fewer than min_filter survive,
hold cash.

Universe: 30-stock large-cap (same as H181/H188/H191/H192)
IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 1.138 (H181) AND MaxDD improvement >= 0.5pp vs -18.4%
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
GATE_SHARPE    = 1.138
H181_OOS_MAXDD = -0.184
CANDIDATE_N    = 10
TOP_N          = 6

OB_GRID = [
    (20, 2, 3), (20, 3, 3), (20, 3, 5),
    (30, 2, 3), (30, 3, 3), (30, 3, 5),
]


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h484_{ticker}_ohlcv.parquet"   # reuse H484's OHLCV cache (same universe)
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


def industry_adjusted_reversal(monthly_returns: pd.Series, sector_map: dict) -> pd.Series:
    sectors = pd.Series(sector_map)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


def load_prices():
    cache = CACHE_DIR / f"h484_universe_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df.dropna(how="all", axis=0).to_parquet(cache)
    stock_px = df[UNIVERSE].copy()
    return stock_px


def compute_signal_and_backtest(monthly_px, daily_data, ob_window, min_filter, swing_len,
                                 candidate_n=CANDIDATE_N, top_n=TOP_N, use_ob=True):
    months = monthly_px.index
    port_rets = []
    for i in range(2, len(months)):
        rebal_date  = months[i - 1]
        hold_date   = months[i]
        prior_close  = monthly_px.loc[months[i - 2]]
        signal_close = monthly_px.loc[months[i - 1]]
        hold_close   = monthly_px.loc[months[i]]

        prior_returns, current_returns = {}, {}
        for ticker in UNIVERSE:
            p0 = prior_close.get(ticker, np.nan)
            p1 = signal_close.get(ticker, np.nan)
            p2 = hold_close.get(ticker, np.nan)
            if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                prior_returns[ticker] = (p1 - p0) / p0
            if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                current_returns[ticker] = (p2 - p1) / p1

        if len(prior_returns) < top_n * 2:
            port_rets.append((hold_date, 0.0))
            continue

        prior_ret_series = pd.Series(prior_returns)
        adj_rev = industry_adjusted_reversal(prior_ret_series, UNIVERSE_SECTORS)
        adj_rev_sorted = adj_rev.sort_values()  # ascending: most negative first

        candidates = adj_rev_sorted.head(candidate_n).index.tolist()

        if use_ob:
            filtered = []
            for ticker in candidates:
                if ticker not in daily_data:
                    continue
                if has_bullish_ob(daily_data[ticker], rebal_date, ob_window, swing_len):
                    filtered.append(ticker)
                if len(filtered) >= top_n:
                    break
            if len(filtered) < min_filter:
                port_rets.append((hold_date, 0.0))
                continue
            selected = filtered[:top_n]
        else:
            selected = candidates[:top_n]

        rets = [current_returns[t] for t in selected if t in current_returns]
        if not rets:
            port_rets.append((hold_date, 0.0))
            continue
        port_rets.append((hold_date, float(np.mean(rets))))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H485 — OB Filter on H181 Industry-Adjusted Reversal")
    print("=" * 70)

    print("\nLoading prices...")
    daily_px = load_prices()
    monthly_px = daily_px.resample("ME").last()
    print(f"  {monthly_px.shape[1]} tickers, {len(monthly_px)} monthly obs")

    print("Loading OHLCV for OB detection...")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    print("\nReplicating H181 baseline (bottom-6, no OB filter)...")
    base_series = compute_signal_and_backtest(monthly_px, daily_data, None, None, None, use_ob=False)
    base_is = eval_period(base_series, IS_START, IS_END)
    base_oos = eval_period(base_series, OOS_START, OOS_END)
    print(f"  Baseline replication: IS Sharpe={base_is['sharpe']:.3f}  "
          f"OOS Sharpe={base_oos['sharpe']:.3f}  OOS MaxDD={base_oos['maxdd']:.1%}  "
          f"(log reference: IS~1.381 OOS~1.138 MaxDD~-18.4%)")

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement >= 0.5pp vs {H181_OOS_MAXDD:.1%}")
    print(f"\n{'Win':>4} {'Min':>4} {'Swg':>4} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'MDDimp(pp)':>11} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 75)

    results = []
    for ob_window, min_filter, swing_len in OB_GRID:
        rets = compute_signal_and_backtest(monthly_px, daily_data, ob_window, min_filter, swing_len, use_ob=True)
        is_ = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
        mdd_improvement_pp = (oos_["maxdd"] - H181_OOS_MAXDD) * 100
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
    print(f"Baseline (H181 replication): OOS Sharpe {base_oos['sharpe']:.3f}, MaxDD {base_oos['maxdd']:.1%}")
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
        "hypothesis": "H485",
        "description": "OB filter on H181 industry-adjusted reversal (bottom-10 candidate pool -> OB filter -> bottom-6)",
        "gate_sharpe": GATE_SHARPE,
        "gate_mdd_improvement_pp": 0.5,
        "h181_baseline_replication": {"is": base_is, "oos": base_oos},
        "n_variants": len(OB_GRID),
        "n_pass_both_gates": n_pass,
        "variants": results,
    }
    outpath = RESULT_DIR / "h485_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
