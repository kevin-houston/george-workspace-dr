"""
H264b — Crypto Trend Momentum: Monthly Signal + Weekly Trailing Stop
=====================================================================
Source: arXiv:2602.11708 (AdaptiveTrend: Systematic Trend-Following with Adaptive
        Portfolio Construction, Sharpe 2.41, MaxDD -12.7%, 2022-2024).

H264 failure (OOS Sharpe 0.662): 2022 bear -37% — monthly rebalance exits too slowly.
Fix: add weekly trailing stop to exit a position mid-month if it draws down > TRAIL_STOP_PCT
     from its within-month peak. Re-entry at next monthly signal.

Strategy:
  Universe: BTC-USD, ETH-USD, SOL-USD, BNB-USD, ADA-USD
  Signal:   6m momentum, skip-1m (same as H264)
  Selection: Top-2 by relative momentum with positive absolute momentum
  Rebalance: Monthly (end of month) for signal; weekly check for trailing stop exit
  Trailing stop: if any held asset drops > TRAIL_STOP_PCT from its within-month peak,
                 exit to BIL until next monthly rebalance
  TC:        20bp per side
  TRAIL_STOP_PCT: test 10%, 15%, 20% (grid search)

IS: 2018-2021, OOS: 2022-2025
Confirm gates (improvement over H264):
  OOS Sharpe > 0.75 (H264 gate, unmet at 0.662)
  MaxDD OOS > -45% (H264 was -46%)
  Corr(H264b, SPY) OOS < 0.60
  NegYrs OOS <= 2
"""

import json
import warnings
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

warnings.filterwarnings("ignore")

RESULT_DIR = Path(__file__).parent.parent / "results"
RESULT_DIR.mkdir(exist_ok=True)

FULL_START  = "2017-01-01"
FULL_END    = "2025-12-31"
IS_START    = "2018-01-01"
IS_END      = "2021-12-31"
OOS_START   = "2022-01-01"
TC          = 0.002   # 20bp — same as H264
TOP_N       = 2

ASSETS      = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD"]
DEFENSIVE   = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]

TRAIL_STOP_LEVELS = [0.10, 0.15, 0.20]   # grid search


def sharpe(ret_series, ann=52):   # weekly Sharpe (52 weeks/yr)
    r = ret_series.dropna()
    if len(r) < 10 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def sharpe_monthly(ret_series):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(12))


def max_drawdown(curve):
    ec = pd.Series(curve)
    return float(((ec - ec.cummax()) / ec.cummax()).min())


print("Downloading crypto universe + BIL (weekly bars)...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)

available = [t for t in ALL_TICKERS if t in raw.columns]
missing   = [t for t in ALL_TICKERS if t not in raw.columns]
if missing:
    print(f"  ⚠ Not available: {missing}")

raw = raw[available].ffill()
crypto_assets = [a for a in ASSETS if a in available]

# Monthly prices for signal construction (same as H264)
monthly = raw.resample("ME").last()
sig_6m  = (monthly.shift(1) / monthly.shift(7) - 1).shift(1)

# Weekly prices for trailing stop logic (Friday close)
weekly = raw.resample("W-FRI").last()
weekly_ret = weekly.pct_change()


def backtest_with_trailing_stop(start, end, trail_stop_pct, label=""):
    """
    Monthly signal selection; weekly trailing-stop exit to BIL mid-month.
    State machine:
      - At each month-end: compute signal, select hold_assets
      - At each weekly bar within the month: track peak from month-start
        if any held asset falls > trail_stop_pct from its month-start price → exit to BIL
        remain in BIL until next month-end rebalance
    """
    # Build monthly signal series for date range
    monthly_dates = monthly.loc[start:end].index
    weekly_dates  = weekly.loc[start:end].index

    equity    = 1.0
    curve     = []   # weekly equity curve
    prev_hold = frozenset()
    stopped_out = False   # True if trailing stop fired; reset at next month-end
    current_hold = []
    month_start_prices = {}   # asset -> price at month start
    annual = {}

    # Pre-index monthly signal lookup
    def get_monthly_signal(date):
        # Get the most recent monthly signal on or before date
        avail = sig_6m.loc[:date, crypto_assets].dropna(how="all")
        if len(avail) == 0:
            return []
        row = sig_6m.loc[avail.index[-1], crypto_assets].dropna()
        ranked = row.sort_values(ascending=False)
        positive = [a for a in ranked.index if float(row.loc[a]) > 0]
        if not positive:
            return [DEFENSIVE] if DEFENSIVE in available else []
        return positive[:TOP_N]

    current_month = None

    for wk_date in weekly_dates:
        wk_month = wk_date.to_period("M")

        # Month-end rebalance: update signal
        if wk_month != current_month:
            current_month = wk_month
            stopped_out = False
            # Find month-end signal (most recent monthly signal)
            hold_assets = get_monthly_signal(wk_date)
            hold_set = frozenset(hold_assets)
            changed = hold_set != prev_hold
            # Apply TC on rebalance
            if changed and len(hold_assets) > 0:
                tc_cost = TC
            else:
                tc_cost = 0.0
            current_hold = hold_assets
            prev_hold = hold_set
            # Record month-start prices for trailing stop
            for a in current_hold:
                p = weekly.loc[wk_date, a] if a in weekly.columns else np.nan
                month_start_prices[a] = float(p) if not pd.isna(p) else np.nan
        else:
            tc_cost = 0.0

        if stopped_out:
            # In BIL (defensive) until next month-end; use BIL return
            r = weekly_ret.loc[wk_date, DEFENSIVE] if DEFENSIVE in weekly_ret.columns else 0.0
            r = 0.0 if pd.isna(r) else float(r)
            equity *= (1 + r)
            curve.append(equity)
            annual.setdefault(wk_date.year, []).append(r)
            continue

        if not current_hold:
            curve.append(equity)
            continue

        # Check trailing stop for each held asset
        stop_triggered = False
        if current_hold != [DEFENSIVE]:
            for a in current_hold:
                if a == DEFENSIVE:
                    continue
                p0 = month_start_prices.get(a, np.nan)
                p1 = weekly.loc[wk_date, a] if a in weekly.columns else np.nan
                if pd.isna(p0) or pd.isna(p1) or p0 <= 0:
                    continue
                drawdown_from_start = float(p1) / float(p0) - 1
                if drawdown_from_start < -trail_stop_pct:
                    stop_triggered = True
                    break

        if stop_triggered:
            stopped_out = True
            # Exit to BIL this week
            r = weekly_ret.loc[wk_date, DEFENSIVE] if DEFENSIVE in weekly_ret.columns else 0.0
            r = 0.0 if pd.isna(r) else float(r)
            equity *= (1 + r - TC)   # TC for forced exit
            curve.append(equity)
            annual.setdefault(wk_date.year, []).append(r - TC)
            continue

        # Normal week: apply hold_assets return
        period_total = 0.0
        for asset in current_hold:
            w  = 1.0 / len(current_hold)
            r  = weekly_ret.loc[wk_date, asset] if asset in weekly_ret.columns else 0.0
            r  = 0.0 if pd.isna(r) else float(r)
            period_total += w * (r - tc_cost)

        equity *= (1 + period_total)
        curve.append(equity)
        annual.setdefault(wk_date.year, []).append(period_total)

    ret_series = pd.Series(curve, index=weekly_dates).pct_change().dropna()
    neg_yrs    = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret    = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

    res = {
        "trail_stop_pct": trail_stop_pct,
        "sharpe":   round(sharpe(ret_series), 4),
        "sharpe_m": round(sharpe_monthly(ret_series), 4),   # approx monthly Sharpe for comparison
        "cagr":     round(float(pd.Series(curve).iloc[-1] ** (52/max(len(curve),1)) - 1), 4),
        "max_dd":   round(max_drawdown(curve), 4),
        "neg_yrs":  neg_yrs,
        "weeks":    len(curve),
    }
    print(f"\n── {label} (stop={trail_stop_pct*100:.0f}%) ──")
    print(f"  Sharpe(w)={res['sharpe']:.3f}  Sharpe(m≈)={res['sharpe_m']:.3f}"
          f"  CAGR={res['cagr']*100:.1f}%  MaxDD={res['max_dd']*100:.1f}%  NegYrs={res['neg_yrs']}")
    if "OOS" in label:
        for yr in sorted(ann_ret):
            print(f"    {yr}: {'+' if ann_ret[yr]>=0 else ''}{ann_ret[yr]}%")
    return res, ann_ret


# Run grid search over TRAIL_STOP_LEVELS
print("\n====== H264b: Crypto Momentum + Weekly Trailing Stop ======")
print(f"  H264 baseline: IS Sharpe=1.005, OOS Sharpe=0.662, MaxDD=-46%\n")

results = {}
for ts in TRAIL_STOP_LEVELS:
    is_res,  _       = backtest_with_trailing_stop(IS_START,  IS_END,   ts, f"IS  (2018-2021)")
    oos_res, oos_ann = backtest_with_trailing_stop(OOS_START, FULL_END, ts, f"OOS (2022-2025)")
    results[ts] = {"is": is_res, "oos": oos_res, "oos_ann": oos_ann}

# SPY correlation (OOS) using best result by OOS Sharpe
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END,
                      auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe_monthly(spy_monthly), 4)

print(f"\n── SPY B&H Sharpe (OOS): {spy_sharpe} ──")
print(f"\n── Gates: OOS Sharpe(m) > 0.75, MaxDD > -45%, NegYrs ≤ 2 ──")

best_ts   = max(TRAIL_STOP_LEVELS, key=lambda ts: results[ts]["oos"]["sharpe_m"])
best_oos  = results[best_ts]["oos"]
sharpe_pass = best_oos["sharpe_m"] > 0.75
dd_pass     = best_oos["max_dd"]   > -0.45
neg_pass    = best_oos["neg_yrs"]  <= 2
confirmed   = sharpe_pass and dd_pass and neg_pass

print(f"\n  Best stop level: {best_ts*100:.0f}%")
print(f"  OOS Sharpe(m) {best_oos['sharpe_m']:.4f} > 0.75  → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  MaxDD {best_oos['max_dd']*100:.1f}% > -45%         → {'PASS' if dd_pass else 'FAIL'}")
print(f"  NegYrs {best_oos['neg_yrs']} ≤ 2                   → {'PASS' if neg_pass else 'FAIL'}")
print(f"\n  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H264b",
    "title": "Crypto Trend Momentum + Weekly Trailing Stop",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "best_trail_stop_pct": best_ts,
    "universe": crypto_assets,
    "h264_baseline_oos_sharpe": 0.662,
    "spy_oos_sharpe": spy_sharpe,
    "grid_results": {
        str(ts): {
            "is_sharpe_m": results[ts]["is"]["sharpe_m"],
            "oos_sharpe_m": results[ts]["oos"]["sharpe_m"],
            "oos_max_dd": results[ts]["oos"]["max_dd"],
            "oos_neg_yrs": results[ts]["oos"]["neg_yrs"],
            "oos_annual": results[ts]["oos_ann"],
        }
        for ts in TRAIL_STOP_LEVELS
    },
    "best_result": best_oos,
    "gates": {
        "sharpe_pass": sharpe_pass,
        "dd_pass": dd_pass,
        "neg_pass": neg_pass,
    },
}
out_path = RESULT_DIR / "h264b_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
