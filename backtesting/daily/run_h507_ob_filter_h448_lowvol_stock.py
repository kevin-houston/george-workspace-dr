#!/usr/bin/env python3
"""
H507 — OB Filter on H448 Stock-Level Low-Volatility Anomaly
=============================================================
H448 (2026-07-25, NOT CONFIRMED) tested the Ang/Hodrick/Xing/Zhang low-vol
anomaly directly on the H198 30-stock large-cap NASDAQ universe. Best variant
(B, pure 60-day realized vol, bottom-6) reached OOS Sharpe 1.045, just short
of the H198 momentum gate (1.174) — directionally correct (low-vol beat
high-vol, Var F 0.830) but not clearing the bar standalone.

The Order Block (SMC) confirmation filter has, across this project, reliably
turned marginal-but-directionally-correct signals into gate-clearing ones by
requiring institutional accumulation evidence before entry:
  - H343/H344 momentum:        1.174 -> 3.182 / 3.396
  - H355 bonds:                1.112 -> 1.522
  - H361 low-vol ETFs:         1.339 -> 1.903  (H354 Var C baseline)
  - H484-corrected BAB stocks: 1.200 -> 1.063 (post-correction; filter still
                                helps directionally even though H484's ORIGINAL
                                unshifted-signal numbers were retracted, see H506)

H448's low-vol stock signal has NEVER had the OB filter applied. This is the
specific gap: H484 already proved the OB-filter-on-a-stock-level-risk-factor
pattern generalizes (post-correction, OOS 0.930->1.063, still a real if
modest lift), but that was on BAB (beta rank). Low-vol (realized vol rank) is
a different risk-factor sort on the same universe and has never been tested
with the filter.

LOOK-AHEAD BIAS DISCIPLINE (per H506 audit — mandatory check before any new
H-series backtest touching a monthly-rebalance + "as of" OB filter):
  - The low-vol rank signal for month M's picks must be computable using only
    data through month M-1's close (H448's original script already does this
    correctly via `.shift(1)` on the monthly-resampled vol series — verified
    by inspection of compute_monthly_signals()).
  - The OB "as of" date passed to has_bullish_ob() must ALSO be month M-1's
    close, not month M's close — this is the exact bug H506 found in the
    original (uncorrected) run_h484_ob_filter_h192d_bab.py. This script uses
    the prior month-end explicitly (signal_asof = month_ends[i-1]), following
    the corrected pattern in run_h484_corrected.py, not the original buggy
    pattern in run_h484_ob_filter_h192d_bab.py.

Method: candidate pool = bottom-12 lowest-60d-realized-vol stocks (widened
from H448's bottom-6 to give the OB filter room to select), filtered to those
showing a bullish unmitigated SMC order block as of the PRIOR month-end,
final selection = bottom-6 of OB survivors by original vol rank (ascending —
lowest vol first). Holds cash (0% return, BIL proxy) if fewer than
`min_filter` OB-confirmed candidates survive.

Universe: H198/H448 30-stock large-cap NASDAQ-heavy universe
IS: 2013-2020  OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 canonical momentum baseline, same gate H448
      itself used, since this is a direct filter-enhancement of H448) AND
      MaxDD improvement >= 0.5pp vs H448 Var B baseline (-24.0% per H448 log)
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
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]

DATA_START = "2011-01-01"
DATA_END   = "2026-07-21"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-07-21")

GATE_SHARPE     = 1.174   # H198 canonical momentum gate, per H448's own gate
H448_B_OOS_MAXDD = -0.240  # H448 Var B (60d low-vol) OOS MaxDD, from log
VOL_WINDOW      = 60
CANDIDATE_N     = 12
TOP_N           = 6

OB_GRID = [
    (20, 2, 3), (20, 3, 3), (20, 3, 5),
    (30, 2, 3), (30, 3, 3), (30, 3, 5),
]


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h507_{ticker}_ohlcv.parquet"
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
    return int((r.resample("YE").apply(lambda x: (1 + x).prod() - 1) < 0).sum())

def eval_period(rets, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"n": 0, "sharpe": 0.0, "maxdd": 0.0, "cagr": 0.0, "neg_yrs": 0}
    return {"n": len(r), "sharpe": round(sharpe(r), 3),
            "maxdd": round(maxdd(r), 3), "cagr": round(float(r.mean() * 12), 3),
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


def load_prices():
    cp = CACHE_DIR / f"h507_universe_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
    df = df.dropna(how="all", axis=0)
    df.to_parquet(cp)
    return df


def compute_vol_rank(daily_px: pd.DataFrame) -> pd.DataFrame:
    """Monthly 60d realized-vol matrix, shifted 1 month so month M's rank
    uses only data through month M-1's close (matches H448's compute)."""
    daily_rets = daily_px.pct_change()
    vol60 = daily_rets.rolling(VOL_WINDOW).std() * np.sqrt(252)
    monthly_vol = vol60.resample("ME").last().shift(1)
    return monthly_vol


def backtest_baseline(monthly_px, vol_rank):
    """Replicate H448 Var B: bottom-6 by 60d vol, no OB filter."""
    monthly_ret = monthly_px.pct_change()
    rows = []
    for month_end in vol_rank.index:
        if month_end not in monthly_ret.index:
            continue
        scores = vol_rank.loc[month_end].dropna()
        if len(scores) < TOP_N:
            continue
        selected = scores.nsmallest(TOP_N).index.tolist()
        loc = monthly_ret.index.get_loc(month_end)
        rows.append((month_end, float(monthly_ret.iloc[loc][selected].mean())))
    s = pd.Series({d: r for d, r in rows})
    s.index = pd.DatetimeIndex(s.index)
    return s


def backtest_ob(monthly_px, vol_rank, daily_data, ob_window, min_filter, swing_len):
    monthly_ret = monthly_px.pct_change()
    month_ends = list(vol_rank.index)
    port_rets = []
    for i, month_end in enumerate(month_ends):
        if month_end not in monthly_ret.index:
            continue
        if i == 0:
            continue
        signal_asof = month_ends[i - 1]  # prior month-end — knowable before month_end (H506 discipline)
        scores = vol_rank.loc[month_end].dropna()
        if len(scores) < 1:
            port_rets.append((month_end, 0.0))
            continue
        candidates = scores.nsmallest(min(CANDIDATE_N, len(scores))).index.tolist()

        filtered = []
        for ticker in candidates:
            if ticker not in daily_data:
                continue
            if has_bullish_ob(daily_data[ticker], signal_asof, ob_window, swing_len):
                filtered.append(ticker)
            if len(filtered) >= TOP_N:
                break

        if len(filtered) < min_filter:
            port_rets.append((month_end, 0.0))
            continue

        selected = filtered[:TOP_N]
        loc = monthly_ret.index.get_loc(month_end)
        ret_this = float(monthly_ret.iloc[loc][selected].mean())
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def main():
    print("H507 — OB Filter on H448 Stock-Level Low-Volatility Anomaly")
    print("=" * 70)

    print("\nLoading prices...")
    daily_px = load_prices()
    print(f"  {daily_px.shape[1]} tickers, {len(daily_px)} daily obs")

    print("Loading OHLCV for OB detection...")
    daily_data = {}
    for t in UNIVERSE:
        try:
            daily_data[t] = fetch_daily_ohlcv(t)
        except Exception as e:
            print(f"  WARN {t}: {e}")

    print("Computing 60d realized-vol ranks (shifted 1 month)...")
    vol_rank = compute_vol_rank(daily_px)
    monthly_px = daily_px.resample("ME").last()

    print("\nReplicating H448 Var B baseline (bottom-6, 60d vol, no OB filter)...")
    base_series = backtest_baseline(monthly_px, vol_rank)
    base_is = eval_period(base_series, IS_START, IS_END)
    base_oos = eval_period(base_series, OOS_START, OOS_END)
    print(f"  Baseline replication: IS Sharpe={base_is['sharpe']:.3f}  "
          f"OOS Sharpe={base_oos['sharpe']:.3f}  OOS MaxDD={base_oos['maxdd']:.1%}  "
          f"(log reference: OOS~1.045 MaxDD~-24.0%)")

    print(f"\nGate: OOS Sharpe > {GATE_SHARPE} AND MaxDD improvement >= 0.5pp vs {H448_B_OOS_MAXDD:.1%}")
    print(f"\n{'Win':>4} {'Min':>4} {'Swg':>4} {'IS Sh':>8} {'OOS Sh':>8} "
          f"{'MaxDD':>8} {'MDDimp(pp)':>11} {'Cash%':>7} {'Beat?':>6}")
    print("-" * 75)

    results = []
    for ob_window, min_filter, swing_len in OB_GRID:
        rets = backtest_ob(monthly_px, vol_rank, daily_data, ob_window, min_filter, swing_len)
        is_ = eval_period(rets, IS_START, IS_END)
        oos_ = eval_period(rets, OOS_START, OOS_END)
        oos_rets = rets[(rets.index >= OOS_START) & (rets.index <= OOS_END)]
        cash_pct = (oos_rets == 0).sum() / max(len(oos_rets), 1) * 100
        mdd_improvement_pp = (oos_["maxdd"] - H448_B_OOS_MAXDD) * 100
        beats_sharpe = oos_["sharpe"] > GATE_SHARPE
        beats_mdd = mdd_improvement_pp >= 0.5
        beats_both = beats_sharpe and beats_mdd
        print(f"{ob_window:>4} {min_filter:>4} {swing_len:>4} "
              f"{is_['sharpe']:>8.3f} {oos_['sharpe']:>8.3f} "
              f"{oos_['maxdd']:>8.1%} {mdd_improvement_pp:>10.2f}pp {cash_pct:>6.1f}% "
              f"{'YES' if beats_both else 'no':>6}")
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
    print(f"Baseline (H448 Var B replication): OOS Sharpe {base_oos['sharpe']:.3f}, MaxDD {base_oos['maxdd']:.1%}")
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
        "hypothesis": "H507",
        "description": "OB filter on H448 Var B stock-level low-vol (bottom-12 candidate pool by 60d vol -> OB filter -> bottom-6)",
        "gate_sharpe": GATE_SHARPE,
        "gate_mdd_improvement_pp": 0.5,
        "h448_baseline_replication": {"is": base_is, "oos": base_oos},
        "n_variants": len(OB_GRID),
        "n_pass_both_gates": n_pass,
        "variants": results,
    }
    outpath = RESULT_DIR / "h507_results.json"
    outpath.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved -> {outpath}")
    return out


if __name__ == "__main__":
    main()
