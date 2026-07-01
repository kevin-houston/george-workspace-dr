"""
H351 — Commodity Trend CTA: EWM Barbell Signal (span-60 + span-500)
=====================================================================
Sources:
  arXiv:2507.15876 (Tanneau & Simonian 2025) — Bayesian decomposition of
  CTA multi-horizon signals; 500d EWM is best single horizon (Sharpe 0.47),
  60d second-best (Sharpe 0.31), 125d third (Sharpe 0.33).
  arXiv:2510.23150 (Sandhu & Garg 2025) — medium-term (125d) IS REDUNDANT;
  optimal barbell = 60d short + 500d long, equal-weight blend.
  arXiv:2504.10914 (Valeyre Dec 2025) — cherry-picking warning: cross-corr
  test required when combining signals (primary is barbell Var A).

Hypothesis:
  H261b CONFIRMED (OOS 0.922) using 6m endpoint momentum (≈125d window).
  That window is exactly what arXiv:2510.23150 identifies as REDUNDANT.
  Replacing with EWM barbell (span=60 + span=500) should improve both IS
  performance (500d long captures commodity multi-year cycles) and OOS
  stability (60d short adds tactical responsiveness without medium-term noise).

Design:
  Universe: GLD, SLV, DBC, USO, DBA (same as H261b, no UNG)
  Daily prices → EWM computation → resample month-end → shift 1m (no lookahead)
    sig_short = Close / ema(span=60) - 1
    sig_long  = Close / ema(span=500) - 1
    combined  = 0.5 * sig_short + 0.5 * sig_long

  Selection: Top-2 by combined score among assets with combined > 0;
             Top-1 if only 1 positive; BIL if none positive.

  Variants:
    A = barbell (60+500 equal-weight) — PRIMARY HYPOTHESIS
    B = long-only signal (span=500 EWM)
    C = short-only signal (span=60 EWM)

IS: 2010-2017, OOS: 2018-2025
TC: 10bp per rebalance (same as H261b)
Top-N: 2

Gates (all must pass for Var A to CONFIRM):
  OOS Sharpe > 0.922  (beat H261b baseline)
  IS  Sharpe > 0.50   (fix H261b IS weakness of 0.256)
  Corr(Var-A, SPY) OOS < 0.50
  NegYrs OOS <= 2

Cherry-pick guard: Var A is pre-registered as the primary signal.
  Var B (long-only) and Var C (short-only) are diagnostic baselines.
  If only Var B or C confirms, result is NOT CONFIRMED for H351 thesis.
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

FULL_START  = "2007-01-01"   # extra history for span-500 warm-up
FULL_END    = "2025-12-31"
IS_START    = "2010-01-01"
IS_END      = "2017-12-31"
OOS_START   = "2018-01-01"
TC          = 0.001
TOP_N       = 2
SHORT_SPAN  = 60    # ~3 months in trading days
LONG_SPAN   = 500   # ~24 months in trading days

ASSETS      = ["GLD", "SLV", "DBC", "USO", "DBA"]
DEFENSIVE   = "BIL"
ALL_TICKERS = ASSETS + [DEFENSIVE]


def sharpe(ret_series, ann=12):
    r = ret_series.dropna()
    if len(r) < 6 or r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(ann))


def max_drawdown(equity_curve):
    ec = pd.Series(equity_curve)
    roll_max = ec.cummax()
    dd = (ec - roll_max) / roll_max
    return float(dd.min())


# ── Download daily prices ──────────────────────────────────────────────────
print("Downloading daily prices (longer history for EWM warm-up)...")
_dl = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)
daily = _dl["Close"] if "Close" in _dl.columns else _dl.xs("Close", axis=1, level=0)
if isinstance(daily.columns, pd.MultiIndex):
    daily.columns = daily.columns.get_level_values(-1)
daily = daily[ALL_TICKERS].ffill().dropna(how="all")

# ── Compute EWM signals on daily data ─────────────────────────────────────
def build_signal(span: int) -> pd.DataFrame:
    """Return month-end EWM-ratio signal, shifted 1 month (no lookahead)."""
    ema = daily[ASSETS].ewm(span=span, adjust=False).mean()
    raw = daily[ASSETS] / ema - 1
    monthly = raw.resample("ME").last()
    return monthly.shift(1)   # use prior month-end signal to trade current month

sig_short  = build_signal(SHORT_SPAN)
sig_long   = build_signal(LONG_SPAN)
sig_barbell = 0.5 * sig_short + 0.5 * sig_long

# Monthly returns (for backtest)
monthly_px  = daily.resample("ME").last()
monthly_ret = monthly_px.pct_change()

VARIANT_SIGNALS = {
    "A_barbell": sig_barbell,
    "B_long500": sig_long,
    "C_short60": sig_short,
}


def run_backtest(signal: pd.DataFrame, start: str, end: str, label: str = ""):
    sig  = signal.loc[start:end]
    ret  = monthly_ret[ALL_TICKERS].loc[start:end]
    common = sig.index.intersection(ret.index)

    equity    = 1.0
    curve     = []
    prev_hold = frozenset()
    annual    = {}

    for date in common:
        s = sig.loc[date].dropna()
        if len(s) == 0:
            curve.append(equity)
            continue

        positive = s[s > 0].sort_values(ascending=False)
        if len(positive) == 0:
            hold_assets = [DEFENSIVE]
        elif len(positive) == 1:
            hold_assets = list(positive.index[:1])
        else:
            hold_assets = list(positive.index[:TOP_N])

        hold_set = frozenset(hold_assets)
        changed  = hold_set != prev_hold

        period_total = 0.0
        for asset in hold_assets:
            w   = 1.0 / len(hold_assets)
            r   = monthly_ret.at[date, asset] if asset in monthly_ret.columns else 0.0
            r   = 0.0 if pd.isna(r) else float(r)
            tc  = TC if changed else 0.0
            period_total += w * (r - tc)

        equity *= (1 + period_total)
        curve.append(equity)
        prev_hold = hold_set
        yr = date.year
        annual.setdefault(yr, []).append(period_total)

    ret_series = pd.Series(curve, index=common).pct_change().dropna()
    neg_yrs    = sum(1 for v in annual.values() if sum(v) < 0)
    ann_ret    = {yr: round(sum(v) * 100, 1) for yr, v in annual.items()}

    result = {
        "sharpe":  round(sharpe(ret_series), 4),
        "cagr":    round(float(pd.Series(curve).iloc[-1] ** (12 / max(len(curve), 1)) - 1), 4),
        "max_dd":  round(max_drawdown(curve), 4),
        "neg_yrs": neg_yrs,
        "months":  len(curve),
    }
    print(f"\n  ── {label} ──")
    print(f"  Sharpe={result['sharpe']:.3f}  CAGR={result['cagr']*100:.1f}%"
          f"  MaxDD={result['max_dd']*100:.1f}%  NegYrs={result['neg_yrs']}")
    if "OOS" in label:
        for yr in sorted(ann_ret):
            print(f"    {yr}: {'+' if ann_ret[yr] >= 0 else ''}{ann_ret[yr]}%")
    return result, ann_ret, curve


def compute_corr_spy(signal: pd.DataFrame) -> float:
    """Corr of strategy monthly returns vs SPY OOS."""
    sig  = signal.loc[OOS_START:]
    ret  = monthly_ret[ALL_TICKERS].loc[OOS_START:]
    common = sig.index.intersection(ret.index)

    prev  = frozenset()
    rets  = []
    for date in common:
        s = sig.loc[date].dropna()
        if len(s) == 0:
            rets.append(0.0)
            continue
        positive = s[s > 0].sort_values(ascending=False)
        if len(positive) == 0:
            hold_assets = [DEFENSIVE]
        elif len(positive) == 1:
            hold_assets = list(positive.index[:1])
        else:
            hold_assets = list(positive.index[:TOP_N])
        hold_set = frozenset(hold_assets)
        changed  = hold_set != prev
        pt = 0.0
        for asset in hold_assets:
            w  = 1.0 / len(hold_assets)
            r  = monthly_ret.at[date, asset] if asset in monthly_ret.columns else 0.0
            r  = 0.0 if pd.isna(r) else float(r)
            pt += w * (r - (TC if changed else 0.0))
        rets.append(pt)
        prev = hold_set

    strat = pd.Series(rets, index=common)
    spy_dl = yf.download("SPY", start=OOS_START, end=FULL_END,
                          auto_adjust=True, progress=False)["Close"]
    if isinstance(spy_dl, pd.DataFrame):
        spy_dl = spy_dl.iloc[:, 0]
    spy_m = spy_dl.resample("ME").last().pct_change().dropna()
    aligned = spy_m.reindex(strat.index).dropna()
    return round(float(strat.reindex(aligned.index).corr(aligned)), 4)


# ── Run all variants ──────────────────────────────────────────────────────
all_results = {}
print("\n" + "=" * 60)
print("H351 — EWM Barbell CTA (span-60 + span-500)")
print("=" * 60)

for var_name, var_sig in VARIANT_SIGNALS.items():
    print(f"\n{'='*40}")
    print(f"Variant {var_name}")
    is_res,  _,       _         = run_backtest(var_sig, IS_START, IS_END,   f"IS 2010-2017  [{var_name}]")
    oos_res, oos_ann, oos_curve = run_backtest(var_sig, OOS_START, FULL_END, f"OOS 2018-2025 [{var_name}]")
    corr = compute_corr_spy(var_sig)

    all_results[var_name] = {
        "is": is_res, "oos": oos_res, "oos_annual": oos_ann, "corr_spy": corr
    }
    print(f"  Corr(SPY) OOS = {corr}")

# ── Verdict on primary variant A ──────────────────────────────────────────
va = all_results["A_barbell"]
sharpe_pass = va["oos"]["sharpe"] > 0.922
is_pass     = va["is"]["sharpe"]  > 0.50
corr_pass   = va["corr_spy"]      < 0.50
neg_pass    = va["oos"]["neg_yrs"] <= 2
confirmed   = sharpe_pass and is_pass and corr_pass and neg_pass

print("\n" + "=" * 60)
print("VERDICT (Variant A — barbell, pre-registered primary)")
print(f"  OOS Sharpe {va['oos']['sharpe']:.3f} vs gate >0.922  → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  IS  Sharpe {va['is']['sharpe']:.3f} vs gate >0.50   → {'PASS' if is_pass else 'FAIL'}")
print(f"  Corr(SPY)  {va['corr_spy']:.3f} vs gate <0.50   → {'PASS' if corr_pass else 'FAIL'}")
print(f"  NegYrs     {va['oos']['neg_yrs']}     vs gate <=2     → {'PASS' if neg_pass else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")
print("=" * 60)

# ── Save results ──────────────────────────────────────────────────────────
out = {
    "hypothesis": "H351",
    "title": "Commodity Trend CTA: EWM Barbell (span-60 + span-500)",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "primary_variant": "A_barbell",
    "results": all_results,
    "gates": {
        "oos_sharpe_gate": 0.922, "is_sharpe_gate": 0.50,
        "corr_gate": 0.50, "neg_gate": 2,
        "sharpe_pass": sharpe_pass, "is_pass": is_pass,
        "corr_pass": corr_pass, "neg_pass": neg_pass,
    },
    "sources": [
        "arXiv:2507.15876 (Tanneau & Simonian 2025)",
        "arXiv:2510.23150 (Sandhu & Garg 2025)",
        "arXiv:2504.10914 (Valeyre Dec 2025 — cherry-pick guard)",
    ],
}
out_path = RESULT_DIR / "h351_results.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nResults saved → {out_path}")
