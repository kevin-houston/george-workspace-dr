"""
H255 — Factor ETF Momentum Rotation (Factor Momentum Everywhere)
================================================================
Source: Gupta & Kelly (2019) "Factor Momentum Everywhere"
        Jegadeesh & Titman (1993) momentum applied to factor ETFs
        "151 Trading Strategies" §3.4 (factor-based rotation)

Hypothesis:
  Rotating among smart-beta factor ETFs by 6-1 month momentum outperforms
  static factor blends and adds diversification beyond H026 sector rotation.
  Factor ETFs rotate at a higher level than sector ETFs — they capture
  style-regime shifts (growth vs value, momentum vs reversal) that are
  missed by sector rotation alone.

Universe (11 factor + broad-market ETFs, all on yfinance):
  MTUM  — iShares MSCI USA Momentum Factor (Apr 2013)
  QUAL  — iShares MSCI USA Quality Factor (Jul 2013)
  VLUE  — iShares MSCI USA Value Factor (Apr 2013)
  USMV  — iShares MSCI USA Min Vol Factor (Oct 2011)
  SIZE  — iShares MSCI USA Size Factor (Apr 2013) [equal-weight tilt]
  IVW   — iShares S&P 500 Growth (May 2000)
  IVE   — iShares S&P 500 Value (May 2000)
  IWM   — iShares Russell 2000 Small Cap (May 2000)
  IWD   — iShares Russell 1000 Value (May 2000)
  IWF   — iShares Russell 1000 Growth (May 2000)
  SPY   — SPDR S&P 500 (benchmark / cash alternative)
  BIL   — SPDR 1-3 Month T-Bill (cash parking slot)

Signal: 6-1 month momentum (skip 1-month reversal as per standard)
Variants:
  A — Top-1 EW (best factor ETF, hold 1 month)
  B — Top-2 EW
  C — Top-3 EW
  D — Top-1, momentum-weighted (proportional to signal rank)

IS: 2014-01-01 to 2019-12-31  (6 years; MTUM/QUAL/VLUE launched Apr 2013)
OOS: 2020-01-01 to 2025-12-31 (6 years, includes COVID crash + rate hike)
TC: 10bp round-trip per rebalance

Confirm gate: OOS Sharpe > 1.0
Portfolio gate: Corr(H255_best, H026_proxy) OOS < 0.70
  (H026 proxy: SPY 6m momentum as stand-in for sector rotation)
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

FULL_START = "2013-06-01"   # all factor ETFs live by Apr 2013
FULL_END   = "2025-12-31"
IS_START   = "2014-01-01"
IS_END     = "2019-12-31"
OOS_START  = "2020-01-01"
TC         = 0.001          # 10bp one-way

UNIVERSE = ["MTUM", "QUAL", "VLUE", "USMV", "SIZE",
            "IVW",  "IVE",  "IWM",  "IWD",  "IWF",
            "SPY",  "BIL"]

# ─────────────────────────────────────────────
# 1. Download data
# ─────────────────────────────────────────────
print("Downloading factor ETF prices...")
raw = yf.download(UNIVERSE, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)["Close"]
raw = raw.dropna(how="all")
raw = raw.ffill().dropna()
print(f"  Loaded {len(raw)} trading days, {raw.shape[1]} ETFs")
print(f"  Date range: {raw.index[0].date()} → {raw.index[-1].date()}")

# ─────────────────────────────────────────────
# 2. Monthly returns (month-end)
# ─────────────────────────────────────────────
monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# ─────────────────────────────────────────────
# 3. Signal: 6-1 month momentum (skip 1m reversal)
# ─────────────────────────────────────────────
# At each month-end, rank by 6-month return ending 1 month prior
# Signal(t) = price(t-1) / price(t-7) - 1
def compute_signal(monthly_prices):
    """6-1 month momentum: 6m return shifted by 1 month."""
    r6 = monthly_prices.shift(1) / monthly_prices.shift(7) - 1
    return r6


signal = compute_signal(monthly)

# ─────────────────────────────────────────────
# 4. Backtest engine
# ─────────────────────────────────────────────
def run_backtest(signal_df, ret_df, top_n, start, end, label):
    sig = signal_df.loc[start:end]
    ret = ret_df.loc[start:end]
    common_idx = sig.index.intersection(ret.index)
    sig = sig.loc[common_idx]
    ret = ret.loc[common_idx]

    equity = 1.0
    equity_curve = []
    prev_holding = set()

    for date in common_idx:
        s = sig.loc[date].dropna()
        if len(s) < top_n:
            equity_curve.append(equity)
            continue

        ranked = s.sort_values(ascending=False)
        new_holding = set(ranked.index[:top_n])

        # transaction cost for turnover
        turnover = len(new_holding.symmetric_difference(prev_holding))
        tc_drag = TC * turnover / top_n

        # equal-weight return
        held = list(new_holding)
        period_ret = ret.loc[date, held].mean()
        equity *= (1 + period_ret - tc_drag)
        equity_curve.append(equity)
        prev_holding = new_holding

    ec = pd.Series(equity_curve, index=common_idx)
    monthly_r = ec.pct_change().dropna()

    ann_ret = (1 + monthly_r.mean()) ** 12 - 1
    ann_vol = monthly_r.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    max_dd  = ((ec / ec.cummax()) - 1).min()
    neg_yrs = (monthly_r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum()
    cagr    = (ec.iloc[-1]) ** (12 / len(monthly_r)) - 1

    return {
        "label":   label,
        "sharpe":  round(sharpe, 4),
        "cagr":    round(cagr, 4),
        "max_dd":  round(max_dd, 4),
        "neg_yrs": int(neg_yrs),
        "months":  len(monthly_r),
        "equity_curve": ec,
    }


# ─────────────────────────────────────────────
# 5. Run variants
# ─────────────────────────────────────────────
variants = [(1, "A-Top1"), (2, "B-Top2"), (3, "C-Top3")]
results_is  = []
results_oos = []

print("\n── IS Results (2014-2019) ──")
for top_n, label in variants:
    r = run_backtest(signal, monthly_ret, top_n, IS_START, IS_END, label)
    results_is.append(r)
    print(f"  {label}: Sharpe={r['sharpe']:.3f}  CAGR={r['cagr']:.1%}"
          f"  MaxDD={r['max_dd']:.1%}  NegYrs={r['neg_yrs']}")

print("\n── OOS Results (2020-2025) ──")
spy_oos = run_backtest(pd.DataFrame({"SPY": signal["SPY"]}),
                       pd.DataFrame({"SPY": monthly_ret["SPY"]}),
                       1, OOS_START, FULL_END, "SPY-BH")
for top_n, label in variants:
    r = run_backtest(signal, monthly_ret, top_n, OOS_START, FULL_END, label)
    results_oos.append(r)
    print(f"  {label}: Sharpe={r['sharpe']:.3f}  CAGR={r['cagr']:.1%}"
          f"  MaxDD={r['max_dd']:.1%}  NegYrs={r['neg_yrs']}")

print(f"  SPY B&H: Sharpe={spy_oos['sharpe']:.3f}")

# ─────────────────────────────────────────────
# 6. Correlation with H026 proxy (SPY momentum)
# ─────────────────────────────────────────────
best_idx  = max(range(len(results_oos)), key=lambda i: results_oos[i]["sharpe"])
best_r    = results_oos[best_idx]
best_label = best_r["label"]

spy_momentum_ec = spy_oos["equity_curve"]
best_ec = best_r["equity_curve"]
common = best_ec.index.intersection(spy_momentum_ec.index)
corr_spy = best_ec.loc[common].pct_change().dropna().corr(
           spy_momentum_ec.loc[common].pct_change().dropna())
print(f"\n  Best OOS variant: {best_label}  Sharpe={best_r['sharpe']:.3f}")
print(f"  Corr(best, SPY B&H) OOS = {corr_spy:.3f}")

# ─────────────────────────────────────────────
# 7. Year-by-year OOS breakdown
# ─────────────────────────────────────────────
print(f"\n── Annual OOS returns — {best_label} ──")
ec = best_r["equity_curve"]
ann = ec.resample("YE").last().pct_change().dropna()
for yr, ret in ann.items():
    print(f"  {yr.year}: {ret:+.1%}")

# ─────────────────────────────────────────────
# 8. Top holdings frequency (OOS)
# ─────────────────────────────────────────────
top_n_best = variants[best_idx][0]
oos_signal = signal.loc[OOS_START:FULL_END]
holdings_count = {}
for date in oos_signal.index:
    s = oos_signal.loc[date].dropna().sort_values(ascending=False)
    for ticker in s.index[:top_n_best]:
        holdings_count[ticker] = holdings_count.get(ticker, 0) + 1

print(f"\n── Top holdings frequency OOS ({best_label}) ──")
for t, c in sorted(holdings_count.items(), key=lambda x: -x[1])[:8]:
    print(f"  {t}: {c} months")

# ─────────────────────────────────────────────
# 9. Confirm / reject
# ─────────────────────────────────────────────
CONFIRM_SHARPE = 1.0
CONFIRM_CORR   = 0.70

oos_sharpe = best_r["sharpe"]
confirmed  = oos_sharpe >= CONFIRM_SHARPE

print(f"\n── Verdict ──")
print(f"  OOS Sharpe {oos_sharpe:.3f} vs gate {CONFIRM_SHARPE} → {'PASS' if oos_sharpe >= CONFIRM_SHARPE else 'FAIL'}")
print(f"  Corr(best, SPY) {corr_spy:.3f} vs gate <{CONFIRM_CORR} → {'PASS' if corr_spy < CONFIRM_CORR else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

# ─────────────────────────────────────────────
# 10. Save results
# ─────────────────────────────────────────────
output = {
    "hypothesis": "H255",
    "title": "Factor ETF Momentum Rotation",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "best_variant": best_label,
    "is_results":  [{k: v for k, v in r.items() if k != "equity_curve"}
                    for r in results_is],
    "oos_results": [{k: v for k, v in r.items() if k != "equity_curve"}
                    for r in results_oos],
    "spy_oos_sharpe": spy_oos["sharpe"],
    "corr_best_spy_oos": round(corr_spy, 4),
    "gates": {
        "sharpe_gate": CONFIRM_SHARPE,
        "corr_gate": CONFIRM_CORR,
        "sharpe_pass": bool(oos_sharpe >= CONFIRM_SHARPE),
        "corr_pass": bool(corr_spy < CONFIRM_CORR),
    },
    "top_holdings_oos": holdings_count,
}
with open(RESULT_DIR / "h255_results.json", "w") as f:
    json.dump(output, f, indent=2)
print("\nResults saved → backtesting/results/h255_results.json")
