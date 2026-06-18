"""
H306 — Low-Volatility Factor ETF Rotation
==========================================

Hypothesis:
  Rotating among factor ETFs (USMV/SPLV/QUAL/MTUM/VLUE/HDV/VYM) using momentum
  generates alpha over SPY. The low-volatility factor (USMV/SPLV) should
  dominate holdings in bear regimes, providing downside protection that pure
  momentum-on-sector ETFs lacks.

  Prior art:
  - H270 CONFIRMED: momentum+low-vol dual ranking on sector ETFs (Sharpe 1.18 OOS)
  - H285 CONFIRMED: QUAL/MTUM/VLUE/low-vol rotation (Sharpe 0.932, Corr SPY 0.969)
  - H286 CONFIRMED: COWZ macro-gated (Sharpe 1.031)
  - H026 OOS Sharpe 1.200 (sector ETF top-1)

  This test: factor-style ETF universe replaces sector ETFs.
  Variants:
    A: Top-1 momentum (12-1 signal), monthly rebalance
    B: Top-2 equal-weight
    C: Top-1 + SPY 200MA overlay (BIL when SPY < 200d MA)
    D: Top-1 + VIX gate (BIL when VIX ≥ 25)

  Universe: USMV, SPLV, QUAL, MTUM, VLUE, HDV, VYM (7 factor ETFs)
  Safety: BIL (T-bill)
  IS:  2014-01-01 to 2019-12-31
  OOS: 2020-01-01 to 2026-06-13
  Gate: OOS Sharpe > 1.0

Academic basis:
  Asness et al. (2013) "Quality minus Junk"; Frazzini & Pedersen (2014) "Betting
  Against Beta"; Fama & French (2015) five-factor model. Factor ETFs provide
  long-only, liquid, diversified exposure to well-documented anomalies.
  The low-vol anomaly persists in OOS (H270 confirmed); question is whether
  a factor ETF rotation (vs sector ETF) captures it more efficiently.
"""

import json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

RESULT_DIR = Path("/workspace/agent/backtesting/results")
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = ["USMV", "SPLV", "QUAL", "MTUM", "VLUE", "HDV", "VYM"]
BIL      = "BIL"
SPY      = "SPY"

FULL_START = "2012-01-01"
IS_START   = "2014-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
OOS_END    = "2026-06-13"
COST_BPS   = 10   # 0.10% one-way

PROD_W = {"H041a": 0.22, "H026": 0.27, "H045": 0.21,
          "XLK_IBS": 0.20, "SMH_IBS": 0.08, "IGV_IBS": 0.02}


def fetch_prices(tickers):
    all_t = sorted(set(tickers + [BIL, SPY]))
    raw = yf.download(all_t, start=FULL_START, end=OOS_END,
                      auto_adjust=True, progress=False)["Close"]
    return raw.ffill()


def monthly_returns(prices):
    return prices.resample("ME").last().pct_change()


def compute_signal(monthly_px):
    """12-1 month cross-sectional momentum score (same as H026 scoring logic)."""
    r12 = monthly_px.pct_change(12)
    r6  = monthly_px.pct_change(6)
    r3  = monthly_px.pct_change(3)
    vol = monthly_px.pct_change().rolling(12).std()

    score = pd.DataFrame(index=monthly_px.index)
    for t in UNIVERSE:
        s = (r12[t].rank() + r6[t].rank() + r3[t].rank()) / 3 * 100
        score[t] = s / (vol[t] + 1e-9) * 10  # vol-scale
    return score.shift(1)  # use prior month signal


def run_backtest(signal, monthly_ret, vix_monthly, spy_monthly_px,
                 top_n=1, use_200ma=False, use_vix_gate=False,
                 label=""):
    dates = signal.index
    # ensure we cover IS+OOS window
    dates = dates[(dates >= IS_START) & (dates <= OOS_END)]

    spy_200 = spy_monthly_px.rolling(200, min_periods=100).mean()
    equity = 1.0
    equity_curve = []
    prev_holding = None

    for dt in dates:
        if dt not in signal.index:
            equity_curve.append((dt, equity))
            continue

        row = signal.loc[dt].dropna()
        if len(row) == 0:
            equity_curve.append((dt, equity))
            continue

        ranked = row.sort_values(ascending=False)

        # Safety overlays
        bil_override = False
        if use_200ma:
            spy_close = spy_monthly_px.loc[:dt].iloc[-1]
            spy_ma    = spy_200.loc[:dt].iloc[-1]
            if spy_close < spy_ma:
                bil_override = True
        if use_vix_gate and dt in vix_monthly.index:
            if vix_monthly.loc[dt] >= 25:
                bil_override = True

        if bil_override:
            picks = [BIL]
        else:
            picks = ranked.index[:top_n].tolist()

        weights = {p: 1.0 / len(picks) for p in picks}

        # Turnover cost
        turnover = 0.0
        if prev_holding is not None:
            all_tickers = set(list(weights.keys()) + list(prev_holding.keys()))
            for t in all_tickers:
                w_new = weights.get(t, 0)
                w_old = prev_holding.get(t, 0)
                turnover += abs(w_new - w_old)
        cost = turnover * COST_BPS / 10000

        # Portfolio return
        port_ret = sum(weights.get(t, 0) * monthly_ret.loc[dt].get(t, 0)
                       for t in picks) - cost
        equity *= (1 + port_ret)
        equity_curve.append((dt, equity))
        prev_holding = weights

    ec = pd.Series(dict(equity_curve))
    rets = ec.pct_change().dropna()
    ann_ret = (ec.iloc[-1] ** (12 / len(ec)) - 1) if len(ec) > 1 else 0
    ann_vol = rets.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0
    roll_max = ec.cummax()
    maxdd = ((ec - roll_max) / roll_max).min()
    return ec, {"sharpe": round(sharpe, 3), "cagr": round(ann_ret, 4),
                "maxdd": round(maxdd, 4), "label": label}


def period_stats(ec, start, end):
    ec_p = ec[(ec.index >= start) & (ec.index <= end)]
    if len(ec_p) < 6:
        return {"sharpe": np.nan, "cagr": np.nan, "maxdd": np.nan}
    rets = ec_p.pct_change().dropna()
    ann_ret = (ec_p.iloc[-1] / ec_p.iloc[0]) ** (12 / len(ec_p)) - 1
    ann_vol = rets.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0
    roll_max = ec_p.cummax()
    maxdd = ((ec_p - roll_max) / roll_max).min()
    return {"sharpe": round(sharpe, 3), "cagr": round(ann_ret, 4), "maxdd": round(maxdd, 4)}


# ── Main ──────────────────────────────────────────────────────────────────────

print("=" * 60)
print("H306 — Low-Volatility Factor ETF Rotation")
print("=" * 60)

print("\n[1] Fetching prices…")
prices = fetch_prices(UNIVERSE)
prices_m = prices.resample("ME").last()

print("[2] Computing monthly returns…")
all_monthly = yf.download(UNIVERSE + [BIL, SPY], start=FULL_START, end=OOS_END,
                          auto_adjust=True, progress=False)["Close"].ffill()
all_monthly_m = all_monthly.resample("ME").last()
monthly_ret = all_monthly_m.pct_change()

print("[3] Computing signals…")
signal = compute_signal(prices_m[UNIVERSE])

# VIX proxy via ^VIX
vix_daily = yf.download("^VIX", start=FULL_START, end=OOS_END, progress=False)["Close"]
vix_monthly = vix_daily.resample("ME").mean().squeeze()

spy_monthly_px = all_monthly_m[SPY]

print("[4] Running variants…")
variants = [
    dict(top_n=1, use_200ma=False, use_vix_gate=False, label="A: Top-1"),
    dict(top_n=2, use_200ma=False, use_vix_gate=False, label="B: Top-2 EW"),
    dict(top_n=1, use_200ma=True,  use_vix_gate=False, label="C: Top-1+200MA"),
    dict(top_n=1, use_200ma=False, use_vix_gate=True,  label="D: Top-1+VIX gate"),
]

results = {}
print(f"\n{'Variant':<22} {'IS Sharpe':>10} {'OOS Sharpe':>11} {'OOS CAGR':>10} {'OOS MaxDD':>10}")
print("-" * 68)

for v in variants:
    ec, _ = run_backtest(signal, monthly_ret, vix_monthly, spy_monthly_px, **v)
    is_s  = period_stats(ec, IS_START, IS_END)
    oos_s = period_stats(ec, OOS_START, OOS_END)
    gate  = "PASS" if oos_s["sharpe"] >= 1.0 else "fail"
    print(f"{v['label']:<22} {is_s['sharpe']:>10.3f} {oos_s['sharpe']:>11.3f} "
          f"{oos_s['cagr']:>9.1%} {oos_s['maxdd']:>9.1%}  {gate}")
    results[v["label"]] = {"is": is_s, "oos": oos_s}

# SPY baseline
spy_ec = all_monthly_m[SPY] / all_monthly_m[SPY].iloc[0]
spy_oos = period_stats(spy_ec, OOS_START, OOS_END)
print(f"{'SPY buy-hold':<22} {'—':>10} {spy_oos['sharpe']:>11.3f} "
      f"{spy_oos['cagr']:>9.1%} {spy_oos['maxdd']:>9.1%}")

best_oos = max((results[k]["oos"]["sharpe"] for k in results), default=0)
confirmed = best_oos >= 1.0

print("\n" + "=" * 60)
print(f"H306 RESULT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
print(f"  Best OOS Sharpe: {best_oos:.3f}  (gate: 1.0)")
print(f"  SPY OOS Sharpe:  {spy_oos['sharpe']:.3f}")
print("=" * 60)

# Save results
out = {
    "hypothesis": "H306",
    "title": "Low-Volatility Factor ETF Rotation",
    "universe": UNIVERSE,
    "is_period": f"{IS_START} to {IS_END}",
    "oos_period": f"{OOS_START} to {OOS_END}",
    "gate": "OOS Sharpe > 1.0",
    "confirmed": bool(confirmed),
    "variants": results,
    "spy_oos": spy_oos,
}
path = RESULT_DIR / "h306_results.json"
path.write_text(json.dumps(out, indent=2))
print(f"\nResults → {path}")
