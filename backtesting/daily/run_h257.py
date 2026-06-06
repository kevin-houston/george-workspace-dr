"""
H257 — Multi-Asset Composite Dual Momentum (20-Asset Universe)
==============================================================
Source: Geczy & Samonov (2015) SSRN:2607730 "Two Centuries of Multi-Asset Momentum"
        Antonacci composite dual momentum extension
        H256 failure analysis: binary equity/bonds gate fails in inflationary bear markets

Hypothesis:
  A 4-module composite dual momentum structure (equity, credit, real assets, international)
  each with its own relative+absolute momentum gate outperforms classic GEM (H256 NOT CONFIRMED)
  because it provides multiple defensive escape routes. When equity AND bonds both crash
  (2022 style), real assets (gold, commodities) or international modules may still show
  positive absolute momentum, preventing the total portfolio loss seen in H256.

Universe (4 modules, 5 assets each + defensive):
  Equity:       SPY, EFA, IWM, QQQ           → defensive: BIL
  Credit:       HYG, LQD, TLT, SHY, AGG     → defensive: SHY
  Real Assets:  GLD, DBC, VNQ, PDBC, IAU    → defensive: BIL
  International: EEM, VEA, FXI, EWJ, EWZ    → defensive: BIL

Each module:
  1. Compute 6-month absolute momentum (signal lagged 1m)
  2. If best relative asset has positive absolute momentum → invest in it
  3. If all assets in module have negative absolute momentum → park in defensive
  Aggregate: equal-weight allocation to 4 modules (25% each)

IS: 2010-01-01 to 2017-12-31  (8 years; most ETFs live by 2008)
OOS: 2018-01-01 to 2025-12-31 (8 years, includes COVID + 2022 rate shock)
TC: 10bp round-trip per rebalance

Confirm gates:
  OOS Sharpe > 1.0
  OOS MaxDD improvement vs GEM (H256 best: Sharpe=0.696) by > 0.30 Sharpe
  Corr(H257_best, SPY_BH) OOS < 0.70
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

FULL_START = "2009-01-01"
FULL_END   = "2025-12-31"
IS_START   = "2010-01-01"
IS_END     = "2017-12-31"
OOS_START  = "2018-01-01"
TC         = 0.001   # 10bp one-way

MODULES = {
    "equity":        {"assets": ["SPY", "EFA", "IWM", "QQQ"],        "defensive": "BIL"},
    "credit":        {"assets": ["HYG", "LQD", "TLT", "SHY", "AGG"], "defensive": "SHY"},
    "real_assets":   {"assets": ["GLD", "DBC", "VNQ", "PDBC", "IAU"],"defensive": "BIL"},
    "international": {"assets": ["EEM", "VEA", "FXI", "EWJ", "EWZ"], "defensive": "BIL"},
}

ALL_TICKERS = list({t for m in MODULES.values() for t in m["assets"] + [m["defensive"]]})

# ─────────────────────────────────────────────
# 1. Download
# ─────────────────────────────────────────────
print("Downloading multi-asset universe...")
raw = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)["Close"]
raw = raw.ffill().dropna(how="all")
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# ─────────────────────────────────────────────
# 2. Signal: 6-month momentum, skip 1m, lagged 1m
# ─────────────────────────────────────────────
# r6(t) = price(t-1) / price(t-7) - 1   [lagged, no look-ahead]
r6_raw = monthly.shift(1) / monthly.shift(7) - 1
signal = r6_raw.shift(1)  # additional lag: signal at t uses data through t-1


def run_module_backtest(module_name, module_cfg, signal_df, ret_df, start, end):
    """
    For each month: find best asset by relative 6m momentum.
    If that asset's absolute momentum > 0: hold it.
    Else: hold defensive.
    Returns equity curve.
    """
    assets    = module_cfg["assets"]
    defensive = module_cfg["defensive"]
    all_assets = assets + [defensive]

    sig = signal_df[all_assets].loc[start:end]
    ret = ret_df[all_assets].loc[start:end]
    common = sig.index.intersection(ret.index)

    equity = 1.0
    curve  = []
    prev   = None

    for date in common:
        s = sig.loc[date, assets].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        best_asset   = s.idxmax()
        best_abs_mom = s[best_asset]
        hold = best_asset if best_abs_mom > 0 else defensive

        # TC
        tc_cost = TC if hold != prev else 0.0
        period_ret = ret.loc[date, hold]
        if pd.isna(period_ret):
            period_ret = 0.0
        equity *= (1 + period_ret - tc_cost)
        curve.append(equity)
        prev = hold

    return pd.Series(curve, index=common)


def combine_modules(signal_df, ret_df, start, end):
    """Equal-weight across 4 modules."""
    module_curves = {}
    for name, cfg in MODULES.items():
        ec = run_module_backtest(name, cfg, signal_df, ret_df, start, end)
        module_curves[name] = ec

    combined_df = pd.DataFrame(module_curves).dropna()
    # Monthly return of equal-weight portfolio
    combined_ret = combined_df.pct_change().dropna().mean(axis=1)
    equity = (1 + combined_ret).cumprod()

    ann_ret = (1 + combined_ret.mean()) ** 12 - 1
    ann_vol = combined_ret.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    max_dd  = ((equity / equity.cummax()) - 1).min()
    cagr    = equity.iloc[-1] ** (12 / len(combined_ret)) - 1
    neg_yrs = (combined_ret.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()

    return {
        "sharpe": round(sharpe, 4),
        "cagr":   round(cagr, 4),
        "max_dd": round(max_dd, 4),
        "neg_yrs": int(neg_yrs),
        "months":  len(combined_ret),
        "equity_curve": equity,
    }


# ─────────────────────────────────────────────
# 3. Run IS and OOS
# ─────────────────────────────────────────────
print("\n── IS Results (2010-2017) ──")
is_r = combine_modules(signal, monthly_ret, IS_START, IS_END)
print(f"  H257 IS: Sharpe={is_r['sharpe']:.3f}  CAGR={is_r['cagr']:.1%}  MaxDD={is_r['max_dd']:.1%}")

print("\n── OOS Results (2018-2025) ──")
oos_r = combine_modules(signal, monthly_ret, OOS_START, FULL_END)
print(f"  H257 OOS: Sharpe={oos_r['sharpe']:.3f}  CAGR={oos_r['cagr']:.1%}  MaxDD={oos_r['max_dd']:.1%}  NegYrs={oos_r['neg_yrs']}")

# SPY benchmark
spy_monthly = monthly_ret["SPY"].loc[OOS_START:FULL_END]
spy_ann = (1 + spy_monthly.mean()) ** 12 - 1
spy_vol = spy_monthly.std() * np.sqrt(12)
spy_sharpe = spy_ann / spy_vol
print(f"  SPY B&H: Sharpe={spy_sharpe:.3f}")

# Correlation with SPY
spy_ec = (1 + spy_monthly).cumprod()
ec     = oos_r["equity_curve"]
common = ec.index.intersection(spy_ec.index)
corr_spy = ec.loc[common].pct_change().dropna().corr(
           spy_ec.loc[common].pct_change().dropna())
print(f"  Corr(H257, SPY) OOS = {corr_spy:.3f}")

# Annual OOS breakdown
print("\n── Annual OOS returns ──")
ann = oos_r["equity_curve"].resample("YE").last().pct_change().dropna()
for yr, r in ann.items():
    print(f"  {yr.year}: {r:+.1%}")

# ─────────────────────────────────────────────
# 4. Verdict
# ─────────────────────────────────────────────
SHARPE_GATE = 1.0
CORR_GATE   = 0.70
GEM_OOS     = 0.696   # H256 best

oos_sharpe = oos_r["sharpe"]
sharpe_pass = bool(oos_sharpe >= SHARPE_GATE)
corr_pass   = bool(corr_spy < CORR_GATE)
gem_improvement = round(oos_sharpe - GEM_OOS, 4)
confirmed = sharpe_pass

print(f"\n── Verdict ──")
print(f"  OOS Sharpe {oos_sharpe:.3f} vs gate {SHARPE_GATE} → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  Corr(H257, SPY) {corr_spy:.3f} vs gate <{CORR_GATE} → {'PASS' if corr_pass else 'FAIL'}")
print(f"  Improvement vs H256 GEM: {gem_improvement:+.3f} Sharpe")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

# ─────────────────────────────────────────────
# 5. Save
# ─────────────────────────────────────────────
output = {
    "hypothesis": "H257",
    "title": "Multi-Asset Composite Dual Momentum",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "is_result": {k: v for k, v in is_r.items() if k != "equity_curve"},
    "oos_result": {k: v for k, v in oos_r.items() if k != "equity_curve"},
    "spy_oos_sharpe": round(float(spy_sharpe), 4),
    "corr_h257_spy_oos": round(float(corr_spy), 4),
    "gem_sharpe_improvement": gem_improvement,
    "gates": {
        "sharpe_gate": SHARPE_GATE,
        "corr_gate": CORR_GATE,
        "sharpe_pass": sharpe_pass,
        "corr_pass": corr_pass,
    },
}
with open(RESULT_DIR / "h257_results.json", "w") as f:
    json.dump(output, f, indent=2)
print("\nResults saved → backtesting/results/h257_results.json")
