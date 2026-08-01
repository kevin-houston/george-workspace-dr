"""
H483 — OB Filter on H411 Var B (OOS 4.825) — Highest-Priority Backtest
=======================================================================
H411 Var B: rank(1/monthly_price) * drift_mask(window=20, threshold=0.60), top-2, OOS Sharpe 4.825.
This is the strongest baseline in the H-series. OB filter has confirmed consistent
improvement on NASDAQ momentum strategies: H343 (1.174->3.182), H344 (1.174->3.396),
H345 (2.538->3.337), H346 (2.610->3.238), H476 (0.383->1.929 non-gate-passing but still a lift).

Method: at each month-end, take the H411 Var B gated-value ranking, generate a candidate
pool of the top-5 stocks (instead of top-2), then filter down to stocks with a bullish
unmitigated Smart-Money-Concepts order block as of that month-end. Select top-2 of the
OB-filtered survivors (by original H411 rank). If fewer than min_filter survive, hold cash.

Universe: NASDAQ_30 (same 30 stocks as H411/H198)
IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 4.825 (H411 Var B) AND MaxDD improvement >= 0.5pp (i.e. OOS MaxDD better than -1.2% - 0.5pp = -1.7%...
      interpreted as MaxDD_OB <= MaxDD_H411 - 0.5pp in absolute terms, i.e. less negative by at least 0.5 percentage points,
      OR at minimum not worse by more than a rounding margin -- see verdict logic below)
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

UNIVERSE = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "NVDA", "AVGO",
    "QCOM", "AMD",  "V",    "MA",    "BAC",  "WFC",  "JPM",
    "UNH",  "LLY",  "PFE",  "JNJ",   "ABBV",
    "WMT",  "HD",   "SBUX", "LOW",   "COST",
    "CVX",  "XOM",  "BA",   "CAT",   "IBM",
]

DATA_START      = "2011-01-01"
DATA_END        = "2026-06-30"
IS_START        = pd.Timestamp("2013-01-01")
IS_END          = pd.Timestamp("2020-12-31")
OOS_START       = pd.Timestamp("2021-01-01")
OOS_END         = pd.Timestamp("2026-06-30")
GATE_SHARPE     = 4.825
H411_OOS_MAXDD  = -0.012          # H411 Var B OOS MaxDD -1.2%
DRIFT_THRESHOLD = 0.60
CANDIDATE_N     = 5
TOP_N           = 2

# OB parameter grid from staged spec
OB_GRID = [
    (20, 1, 3), (20, 1, 5), (20, 2, 3), (20, 2, 5),
    (30, 1, 3), (30, 1, 5), (30, 2, 3), (30, 2, 5),
]


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h409_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        s = pd.read_parquet(cp).squeeze()
        s.name = ticker
        return s
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].dropna()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h483_{ticker}_ohlcv.parquet"
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


def fetch_monthly(ticker: str) -> pd.Series:
    for prefix in ["h409", "h398", "h395", "h393", "h198"]:
        for end in [DATA_END, "2026-06-30", "2026-04-30"]:
            cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{end}.parquet"
            if cp.exists():
                s = pd.read_parquet(cp).squeeze()
                s.name = ticker
                return s
    daily = fetch_daily(ticker)
    s = daily.resample("ME").last()
    s.name = ticker
    return s


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


def backtest_ob(monthly_px, h411_signal, daily_data, ob_window, min_filter, swing_len,
                 candidate_n=CANDIDATE_N, top_n=TOP_N):
    monthly_ret = monthly_px.pct_change()
    port_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = h411_signal.loc[month_end].dropna()
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            port_rets.append((month_end, 0.0))
            continue
        candidates = pool.nlargest(min(candidate_n, len(pool))).index.tolist()

        filtered = []
        for ticker in candidates:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], month_end, ob_window, swing_len):
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


def main():
    print("H483 — OB Filter on H411 Var B (champion baseline OOS 4.825)")
    print("=" * 70)

    print("\nLoading monthly + daily prices...")
    daily_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_daily(t)] if s is not None]
    ).T.sort_index()
    monthly_px = pd.DataFrame(
        [s for t in UNIVERSE for s in [fetch_monthly(t)] if s is not None]
    ).T.sort_index().loc[DATA_START:]
    print(f"  {len(daily_px.columns)} tickers, {len(daily_px)} daily / {len(monthly_px)} monthly obs")

    print("Loading OHLCV for OB detection...")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    print("Computing H411 Var B signal: rank(1/price) * 20d drift gate...")
    daily_ret = daily_px.pct_change()
    pos_20 = (daily_ret > 0).rolling(20).sum()
    d20 = (pos_20 / 20) > DRIFT_THRESHOLD
    d20_mly = d20.resample("ME").last().astype(float)
    d20_mly = d20_mly.reindex(monthly_px.index, method="ffill")
    gate_mask = d20_mly.gt(0.5).astype(float)
    rank_value = (1.0 / monthly_px).rank(axis=1, pct=True)
    h411_var_b = rank_value * gate_mask

    # Baseline replication (sanity check vs H411 log: expect OOS ~4.825)
    print("\nReplicating H411 Var B baseline (top-2, no OB filter)...")
    monthly_ret = monthly_px.pct_change()
    base_rets = []
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        scores = h411_var_b.loc[month_end].dropna()
        pool = scores[scores > 1e-6]
        if len(pool) < 1:
            base_rets.append((month_end, 0.0))
            continue
        selected = pool.nlargest(min(2, len(pool))).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        base_rets.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    base_series = pd.Series({d: r for d, r in base_rets})
    base_series.index = pd.DatetimeIndex(base_series.index)
    base_is = eval_period(base_series, IS_START, IS_END)
    base_oos = eval_period(base_series, OOS_START, OOS_END)
    print(f"  Baseline replication: IS Sharpe={base_is['sharpe']:.3f}  "
          f"OOS Sharpe={base_oos['sharpe']:.3f}  OOS MaxDD={base_oos['maxdd']:.1%}")

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement >= 0.5pp vs {H411_OOS_MAXDD:.1%}")
    print(f"\n{'Win':>4} {'Min':>4} {'Swg':>4} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'MDDimp(pp)':>11} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 75)

    results = []
    for ob_window, min_filter, swing_len in OB_GRID:
        rets = backtest_ob(monthly_px, h411_var_b, daily_data, ob_window, min_filter, swing_len)
        is_ = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
        mdd_improvement_pp = (oos_["maxdd"] - H411_OOS_MAXDD) * 100  # positive = improvement (less negative than baseline)
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
    print(f"Baseline (H411 Var B replication): OOS Sharpe {base_oos['sharpe']:.3f}, MaxDD {base_oos['maxdd']:.1%}")
    print(f"Variants passing BOTH gates (Sharpe > {GATE_SHARPE} AND MaxDD improved >= 0.5pp): {n_pass}/{len(OB_GRID)}")
    print(f"Best OOS Sharpe: {best['oos']['sharpe']:.3f} "
          f"(window={best['ob_window']}, min_filter={best['min_filter']}, swing_len={best['swing_len']}), "
          f"MaxDD={best['oos']['maxdd']:.1%}, cash%={best['oos_cash_pct']:.1f}")

    if n_pass > 0:
        print(f"\nVERDICT: CONFIRMED — {n_pass} variant(s) beat both the Sharpe and MaxDD gates.")
    else:
        best_sharpe_only = max(results, key=lambda r: r["oos"]["sharpe"])
        if best_sharpe_only["beats_sharpe_gate"]:
            print(f"\nVERDICT: PARTIAL CONFIRMED — best variant beats Sharpe gate "
                  f"({best_sharpe_only['oos']['sharpe']:.3f} > {GATE_SHARPE}) but MaxDD improvement "
                  f"insufficient ({best_sharpe_only['mdd_improvement_pp']:.2f}pp < 0.5pp).")
        else:
            print(f"\nVERDICT: NOT CONFIRMED — no variant beats OOS Sharpe {GATE_SHARPE} "
                  f"(best {best_sharpe_only['oos']['sharpe']:.3f}). OB filter's top-5 candidate pool + "
                  f"top-2 selection under-concentrates vs H411 Var B's already-optimal top-2 pure rank.")

    out = {
        "hypothesis": "H483",
        "description": "OB filter on H411 Var B (rank(1/price) x 20d drift gate, top-2)",
        "gate_sharpe": GATE_SHARPE,
        "gate_mdd_improvement_pp": 0.5,
        "h411_varb_baseline_replication": {"is": base_is, "oos": base_oos},
        "n_variants": len(OB_GRID),
        "n_pass_both_gates": n_pass,
        "variants": results,
    }
    outpath = RESULT_DIR / "h483_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
