"""
H264 — Crypto Trend Momentum (Top-2)
=====================================
Source: Momentum anomaly in crypto well-documented in literature:
  - Grobys & Sapkota (2019) JFinReg: crypto momentum persists 1-4 weeks
  - Liu, Tsyvinski & Wu (2022 JF): crypto-specific factor structure, momentum prominent
  - Cong, Harvey, Kahraman, Saad (2023 RFS): risk/return in crypto assets
  Hypothesis: 6m relative + absolute momentum on liquid crypto ETFs/tokens generates
  positive Sharpe with low correlation to equity production portfolio (H041a/H026).

Strategy:
  Universe: BTC-USD, ETH-USD, SOL-USD, BNB-USD, ADA-USD (5 major tokens via yfinance)
  Signal:   6m momentum, skip-1m, lagged-1m (same construction as H261b/H026)
  Selection: Top-2 by relative momentum; both must have positive absolute momentum
             → 1 if only 1 positive; BIL if all negative (capital preservation)
  Rebalance: Monthly (end of month)
  TC:        20bp per side (higher than equities — crypto spread/slippage)
  Defensive: BIL (T-bills) when all signals negative

IS: 2018-2021 (covers 2018 bear, 2019-2021 bull; SOL available late 2020)
OOS: 2022-2025 (2022 crypto bear -65% BTC, 2023 recovery, 2024 halving rally, 2025)

Confirm gates:
  OOS Sharpe > 0.75 (crypto-adjusted; lower than equity targets due to vol)
  Corr(H264, SPY) OOS < 0.60 (diversification check)
  Corr(H264, H041a proxy: SPY) OOS < 0.60
  NegYrs OOS ≤ 2
  MaxDD OOS < -60% (crypto-adjusted; eliminates catastrophic concentration risk)
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
TC          = 0.002   # 20bp — higher than equities for crypto spread
TOP_N       = 2

ASSETS      = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "ADA-USD"]
DEFENSIVE   = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]


def sharpe(ret_series, ann=12):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def max_drawdown(curve):
    ec = pd.Series(curve)
    return float(((ec - ec.cummax()) / ec.cummax()).min())


print("Downloading crypto universe + BIL...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
raw = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(-1)

# Keep only tickers that actually downloaded
available = [t for t in ALL_TICKERS if t in raw.columns]
missing   = [t for t in ALL_TICKERS if t not in raw.columns]
if missing:
    print(f"  ⚠ Not available: {missing}")

raw  = raw[available].ffill()
# BIL might be absent from FULL_START for crypto start — forward fill is fine
# Crypto assets: use individual available tickers
crypto_assets = [a for a in ASSETS if a in available]
print(f"  Crypto universe: {crypto_assets}")
print(f"  Defensive: {'BIL' if DEFENSIVE in available else 'cash (BIL unavailable)'}")

monthly     = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# Show universe availability
for asset in crypto_assets:
    first = monthly[asset].dropna().index[0]
    print(f"  {asset}: first data = {first.date()}")

# 6m momentum signal (same as H261b)
sig_6m = (monthly.shift(1) / monthly.shift(7) - 1).shift(1)


def backtest(start, end, label=""):
    ret    = monthly_ret[available].loc[start:end]
    dates  = ret.index
    equity = 1.0
    curve  = []
    prev_hold = frozenset()
    annual = {}

    for date in dates:
        s = sig_6m.loc[date, crypto_assets].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        ranked   = s.sort_values(ascending=False)
        positive = [a for a in ranked.index if float(s.loc[a]) > 0]

        if not positive:
            hold_assets = [DEFENSIVE] if DEFENSIVE in available else []
            if not hold_assets:
                curve.append(equity)
                continue
        elif len(positive) == 1:
            hold_assets = positive[:1]
        else:
            hold_assets = positive[:TOP_N]

        hold_set = frozenset(hold_assets)
        changed  = hold_set != prev_hold

        period_total = 0.0
        for asset in hold_assets:
            w  = 1.0 / len(hold_assets)
            r  = monthly_ret.loc[date, asset] if asset in monthly_ret.columns else 0.0
            r  = 0.0 if pd.isna(r) else float(r)
            tc = TC if changed else 0.0
            period_total += w * (r - tc)

        equity *= (1 + period_total)
        curve.append(equity)
        prev_hold = hold_set
        annual.setdefault(date.year, []).append(period_total)

    ret_series = pd.Series(curve, index=dates).pct_change().dropna()
    neg_yrs    = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret    = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

    res = {
        "sharpe":  round(sharpe(ret_series), 4),
        "cagr":    round(float(pd.Series(curve).iloc[-1] ** (12/max(len(curve),1)) - 1), 4),
        "max_dd":  round(max_drawdown(curve), 4),
        "neg_yrs": neg_yrs,
        "months":  len(curve),
    }
    print(f"\n── {label} ──")
    print(f"  Sharpe={res['sharpe']:.3f}  CAGR={res['cagr']*100:.1f}%"
          f"  MaxDD={res['max_dd']*100:.1f}%  NegYrs={res['neg_yrs']}")
    for yr in sorted(ann_ret):
        print(f"    {yr}: {'+' if ann_ret[yr]>=0 else ''}{ann_ret[yr]}%")
    return res, ann_ret


is_result,  is_ann  = backtest(IS_START,  IS_END,     "IS  (2018-2021)")
oos_result, oos_ann = backtest(OOS_START, FULL_END,   "OOS (2022-2025)")

# SPY correlation
spy_raw = yf.download("SPY", start=OOS_START, end=FULL_END,
                      auto_adjust=True, progress=False)["Close"]
if isinstance(spy_raw, pd.DataFrame):
    spy_raw = spy_raw.iloc[:, 0]
spy_monthly = spy_raw.resample("ME").last().pct_change().dropna()
spy_sharpe  = round(sharpe(spy_monthly), 4)

# H264 OOS monthly rets for correlation
oos_dates = monthly_ret.loc[OOS_START:].index
prev2 = frozenset()
h264_rets = []
for date in oos_dates:
    s    = sig_6m.loc[date, crypto_assets].dropna()
    if len(s) == 0:
        h264_rets.append(0.0); continue
    ranked   = s.sort_values(ascending=False)
    positive = [a for a in ranked.index if float(s.loc[a]) > 0]
    hold     = ([DEFENSIVE] if not positive
                else positive[:1] if len(positive) == 1
                else positive[:TOP_N])
    if DEFENSIVE not in available and not positive:
        h264_rets.append(0.0); continue
    h_set    = frozenset(hold)
    changed  = h_set != prev2
    pt = sum(
        (1.0/len(hold)) * (
            (0.0 if pd.isna(monthly_ret.loc[date, a]) else float(monthly_ret.loc[date, a]))
            - (TC if changed else 0.0)
        )
        for a in hold
    )
    h264_rets.append(pt)
    prev2 = h_set

h264_oos    = pd.Series(h264_rets, index=oos_dates)
spy_aligned = spy_monthly.reindex(h264_oos.index).dropna()
h264_aln    = h264_oos.reindex(spy_aligned.index).dropna()
corr_spy    = round(float(h264_aln.corr(spy_aligned)), 4)

# Gate evaluation
sharpe_pass = oos_result["sharpe"] > 0.75
corr_pass   = corr_spy < 0.60
neg_pass    = oos_result["neg_yrs"] <= 2
dd_pass     = oos_result["max_dd"] > -0.60   # MaxDD > -60% (less severe)
confirmed   = sharpe_pass and corr_pass and neg_pass and dd_pass

print(f"\n── SPY B&H Sharpe (OOS): {spy_sharpe} ──")
print(f"\n── Gates ──")
print(f"  OOS Sharpe {oos_result['sharpe']:.4f} > 0.75          → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  Corr(H264, SPY) OOS {corr_spy} < 0.60   → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs {oos_result['neg_yrs']} ≤ 2                      → {'PASS' if neg_pass else 'FAIL'}")
print(f"  MaxDD {oos_result['max_dd']*100:.1f}% > -60%             → {'PASS' if dd_pass else 'FAIL'}")
print(f"\n  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

out = {
    "hypothesis": "H264",
    "title": "Crypto Trend Momentum Top-2",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "universe": crypto_assets,
    "is_result": is_result, "is_annual": is_ann,
    "oos_result": oos_result, "oos_annual": oos_ann,
    "spy_oos_sharpe": spy_sharpe,
    "corr_h264_spy_oos": corr_spy,
    "gates": {
        "oos_sharpe_gate": 0.75, "corr_gate": 0.60, "neg_gate": 2, "maxdd_gate": -0.60,
        "sharpe_pass": sharpe_pass, "corr_pass": corr_pass,
        "neg_pass": neg_pass, "dd_pass": dd_pass,
    },
}
out_path = RESULT_DIR / "h264_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
