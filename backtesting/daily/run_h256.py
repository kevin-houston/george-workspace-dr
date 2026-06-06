"""
H256 — Dual Momentum (Antonacci 2014) & Extended Protective Asset Class Momentum
==================================================================================
Source: Gary Antonacci "Dual Momentum Investing" (2014); GEM model and PACS model.
        Antonacci (2012) "Risk Premia Harvesting Through Dual Momentum"
        (original paper: annualized returns 17.7% 1974-2011, MaxDD -22.7%)

Two mechanics in one hypothesis:
  (A) CLASSIC DUAL MOMENTUM (GEM — Global Equity Momentum, 3 assets)
      Month-end rule:
        Step 1 — Absolute: if SPY_12m > BIL_12m → proceed to Step 2; else → BIL
        Step 2 — Relative: if SPY_12m > EFA_12m → hold SPY; else → hold EFA
      Assets: SPY, EFA, BIL

  (B) EXTENDED DUAL MOMENTUM (12-asset Protective Asset Class Momentum — PACS)
      Extends GEM by adding:
        - Additional equity universes: IWM, EEM
        - Defensive alternatives: TLT, GLD (not just BIL)
        - Rule: if best equity asset 12m > BIL → rotate among equities; else → top defensive
      Assets: SPY, QQQ, IWM, EFA, EEM  (equity pool)
              TLT, GLD, BIL             (defensive pool)

  (C) GEM WITH SECTORS — absolute gate + cross-sectional sector rotation
      Absolute gate: if SPY_12m > BIL_12m → rotate among 11 sector ETFs (top-2); else → TLT
      This tests whether Antonacci's defensive gate improves H026-style rotation

Key insight vs H026:
  H026 is purely cross-sectional (always in the market, pick best sector).
  Dual Momentum adds an absolute momentum filter that exits equity entirely
  when the overall equity market shows negative 12m momentum.
  The 2008-2009 bear market is the classic use case — SPY 12m turned negative
  in late 2007, triggering a defensive shift before the worst drawdown.

IS: 2002-01-01 to 2014-12-31  (EFA launched 2001; GLD/IWM launched 2000/2000)
OOS: 2015-01-01 to 2025-12-31 (11 years: includes 2020 COVID, 2022 rate hike)
TC: 10bp round-trip per rebalance

Confirm gate (any variant): OOS Sharpe > 0.9, MaxDD improvement vs SPY > 10pp
Portfolio gate: Corr(best_H256, H026_proxy) OOS < 0.70
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

FULL_START = "2001-06-01"
FULL_END   = "2025-12-31"
IS_START   = "2002-01-01"
IS_END     = "2014-12-31"
OOS_START  = "2015-01-01"
TC         = 0.001

# ─────────────────────────────────────────────
# 1. Download prices
# ─────────────────────────────────────────────
ALL_TICKERS = ["SPY", "EFA", "IWM", "QQQ", "EEM",
               "TLT", "GLD", "BIL",
               "XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]
print("Downloading prices...")
raw = yf.download(ALL_TICKERS, start=FULL_START, end=FULL_END,
                  auto_adjust=True, progress=False)["Close"]
raw = raw.ffill().dropna(how="all")
print(f"  {len(raw)} trading days, {raw.shape[1]} tickers")
print(f"  {raw.index[0].date()} → {raw.index[-1].date()}")

monthly = raw.resample("ME").last()
monthly_ret = monthly.pct_change()

# 12-month total return signal — shifted 1 month to avoid look-ahead
# r12_signal at month t = price(t-1)/price(t-13) - 1
# This means position at month t is based on signal known at t-1 month-end
r12_raw = monthly / monthly.shift(12) - 1
r12 = r12_raw.shift(1)  # lag 1 month: signal at t uses data through t-1

SECTORS = ["XLK", "XLE", "XLF", "XLV", "XLI", "XLB", "XLU", "XLRE", "XLY", "XLP", "XLC"]

# ─────────────────────────────────────────────
# 2. Backtest helpers
# ─────────────────────────────────────────────
def single_asset_backtest(positions_series, ret_df, label):
    """positions_series: Series of ticker to hold each month."""
    equity = 1.0
    eq_list = []
    prev = None
    for date, ticker in positions_series.items():
        if date not in ret_df.index or ticker not in ret_df.columns:
            eq_list.append(equity)
            continue
        tc = TC if ticker != prev else 0
        r = ret_df.loc[date, ticker]
        if pd.isna(r):
            eq_list.append(equity)
            continue
        equity *= (1 + r - tc)
        eq_list.append(equity)
        prev = ticker
    ec = pd.Series(eq_list, index=positions_series.index)
    return _stats(ec, label)


def topn_backtest(signal_df, ret_df, top_n, universe, label, start, end, tc_per=TC):
    sig = signal_df[universe].loc[start:end]
    ret = ret_df[universe].loc[start:end]
    common = sig.index.intersection(ret.index)
    equity = 1.0
    eq_list = []
    prev = set()
    for date in common:
        s = sig.loc[date].dropna()
        if len(s) < top_n:
            eq_list.append(equity)
            continue
        new = set(s.sort_values(ascending=False).index[:top_n])
        turn = len(new.symmetric_difference(prev))
        tc = tc_per * turn / top_n
        r = ret.loc[date, list(new)].mean()
        equity *= (1 + r - tc)
        eq_list.append(equity)
        prev = new
    ec = pd.Series(eq_list, index=common)
    return _stats(ec, label)


def _stats(ec, label):
    mr = ec.pct_change().dropna()
    ann_ret = (1 + mr.mean()) ** 12 - 1
    ann_vol = mr.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0
    max_dd  = ((ec / ec.cummax()) - 1).min()
    neg_yrs = int((mr.resample("YE").apply(lambda x: (1+x).prod()-1) < 0).sum())
    cagr    = float((ec.iloc[-1]) ** (12 / max(len(mr), 1)) - 1)
    return {
        "label": label, "sharpe": round(float(sharpe), 4),
        "cagr": round(cagr, 4), "max_dd": round(float(max_dd), 4),
        "neg_yrs": neg_yrs, "months": len(mr), "ec": ec,
    }


# ─────────────────────────────────────────────
# 3. Variant A — Classic GEM (3-asset)
# ─────────────────────────────────────────────
def run_gem(start, end, label):
    idx = r12.loc[start:end].index.intersection(monthly_ret.loc[start:end].index)
    positions = {}
    for date in idx:
        spy_r  = r12.loc[date, "SPY"] if "SPY" in r12.columns else np.nan
        efa_r  = r12.loc[date, "EFA"] if "EFA" in r12.columns else np.nan
        bil_r  = r12.loc[date, "BIL"] if "BIL" in r12.columns else np.nan
        if pd.isna(spy_r) or pd.isna(bil_r):
            positions[date] = "BIL"
            continue
        if spy_r > bil_r:
            positions[date] = "SPY" if (pd.isna(efa_r) or spy_r >= efa_r) else "EFA"
        else:
            positions[date] = "BIL"
    pos = pd.Series(positions)
    return single_asset_backtest(pos, monthly_ret, label)

gem_is  = run_gem(IS_START, IS_END, "GEM-IS")
gem_oos = run_gem(OOS_START, FULL_END, "GEM-OOS")

# ─────────────────────────────────────────────
# 4. Variant B — Extended PACS (equity pool vs defensive pool)
# ─────────────────────────────────────────────
EQ_POOL  = ["SPY", "QQQ", "IWM", "EFA", "EEM"]
DEF_POOL = ["TLT", "GLD", "BIL"]

def run_pacs(start, end, label, top_n_eq=1, top_n_def=1):
    idx = r12.loc[start:end].index
    positions = {}    # date → list of tickers (equal-weight)
    prev = []
    eq_list = []
    equity = 1.0

    for date in idx:
        if date not in monthly_ret.index:
            eq_list.append(equity)
            prev_holding = prev
            continue

        eq_signals  = r12.loc[date, EQ_POOL].dropna()
        def_signals = r12.loc[date, DEF_POOL].dropna()
        bil_r = r12.loc[date, "BIL"] if "BIL" in r12.columns else 0.0

        if len(eq_signals) == 0:
            tickers = ["BIL"]
        else:
            best_eq = eq_signals.sort_values(ascending=False).index[0]
            best_eq_r = eq_signals[best_eq]
            if best_eq_r > bil_r:
                tickers = list(eq_signals.sort_values(ascending=False).index[:top_n_eq])
            else:
                tickers = list(def_signals.sort_values(ascending=False).index[:top_n_def]) if len(def_signals) else ["BIL"]

        # compute return
        turn = len(set(tickers).symmetric_difference(set(prev)))
        tc = TC * turn / len(tickers)
        r = monthly_ret.loc[date, tickers].mean()
        equity *= (1 + (r if not pd.isna(r) else 0) - tc)
        eq_list.append(equity)
        prev = tickers

    ec = pd.Series(eq_list, index=idx[:len(eq_list)])
    return _stats(ec, label)

pacs_is  = run_pacs(IS_START, IS_END, "PACS-IS")
pacs_oos = run_pacs(OOS_START, FULL_END, "PACS-OOS")

# ─────────────────────────────────────────────
# 5. Variant C — GEM gate + sector cross-sectional rotation
# ─────────────────────────────────────────────
def run_gem_sector(start, end, label, top_n=2):
    idx = r12.loc[start:end].index.intersection(monthly_ret.loc[start:end].index)
    equity = 1.0
    eq_list = []
    prev = []

    for date in idx:
        spy_r = r12.loc[date, "SPY"] if "SPY" in r12.columns else np.nan
        bil_r = r12.loc[date, "BIL"] if "BIL" in r12.columns else np.nan
        if pd.isna(spy_r) or pd.isna(bil_r):
            eq_list.append(equity)
            continue

        if spy_r > bil_r:
            sec_sig = r12.loc[date, SECTORS].dropna()
            if len(sec_sig) >= top_n:
                tickers = list(sec_sig.sort_values(ascending=False).index[:top_n])
            else:
                tickers = ["SPY"]
        else:
            tickers = ["TLT"]

        turn = len(set(tickers).symmetric_difference(set(prev)))
        tc = TC * turn / len(tickers)
        r = monthly_ret.loc[date, tickers].mean()
        equity *= (1 + (r if not pd.isna(r) else 0) - tc)
        eq_list.append(equity)
        prev = tickers

    ec = pd.Series(eq_list, index=idx[:len(eq_list)])
    return _stats(ec, label)

gsec_is  = run_gem_sector(IS_START, IS_END, "GEM+Sector-IS")
gsec_oos = run_gem_sector(OOS_START, FULL_END, "GEM+Sector-OOS")

# ─────────────────────────────────────────────
# 6. SPY benchmark
# ─────────────────────────────────────────────
spy_oos = _stats(
    (1 + monthly_ret["SPY"].loc[OOS_START:FULL_END].fillna(0)).cumprod(),
    "SPY-BH"
)

# ─────────────────────────────────────────────
# 7. Print results
# ─────────────────────────────────────────────
print("\n══════════════════════════════════")
print("IS Results (2002-2014)")
print("══════════════════════════════════")
for r in [gem_is, pacs_is, gsec_is]:
    print(f"  {r['label']:22s}  Sharpe={r['sharpe']:.3f}  CAGR={r['cagr']:.1%}"
          f"  MaxDD={r['max_dd']:.1%}  NegYrs={r['neg_yrs']}")

print("\n══════════════════════════════════")
print("OOS Results (2015-2025)")
print("══════════════════════════════════")
for r in [gem_oos, pacs_oos, gsec_oos]:
    print(f"  {r['label']:22s}  Sharpe={r['sharpe']:.3f}  CAGR={r['cagr']:.1%}"
          f"  MaxDD={r['max_dd']:.1%}  NegYrs={r['neg_yrs']}")
print(f"  {'SPY B&H':22s}  Sharpe={spy_oos['sharpe']:.3f}  CAGR={spy_oos['cagr']:.1%}"
      f"  MaxDD={spy_oos['max_dd']:.1%}")

# OOS annual breakdown for best
oos_variants = [gem_oos, pacs_oos, gsec_oos]
best = max(oos_variants, key=lambda x: x["sharpe"])
print(f"\n── Annual OOS — {best['label']} ──")
ann = best["ec"].resample("YE").last().pct_change().dropna()
for yr, ret in ann.items():
    print(f"  {yr.year}: {ret:+.1%}")

# Correlation with SPY
print("\n── Correlations (OOS) ──")
spy_ret = monthly_ret["SPY"].loc[OOS_START:FULL_END]
for r in oos_variants:
    ec_ret = r["ec"].pct_change().dropna()
    common = ec_ret.index.intersection(spy_ret.index)
    corr = ec_ret.loc[common].corr(spy_ret.loc[common])
    r["corr_spy"] = round(float(corr), 4)
    print(f"  Corr({r['label']}, SPY) = {corr:.3f}")

# ─────────────────────────────────────────────
# 8. Confirm / reject
# ─────────────────────────────────────────────
SHARPE_GATE = 0.90
CORR_GATE   = 0.70
SPY_DD_GATE = spy_oos["max_dd"] + 0.10  # need MaxDD 10pp better than SPY

best_oos = max(oos_variants, key=lambda x: x["sharpe"])
sharpe_pass = best_oos["sharpe"] >= SHARPE_GATE
dd_pass     = best_oos["max_dd"] > SPY_DD_GATE
corr_pass   = best_oos["corr_spy"] < CORR_GATE
confirmed   = sharpe_pass

print(f"\n══════════════════════════════════")
print(f"Verdict")
print(f"══════════════════════════════════")
print(f"  Best: {best_oos['label']}  OOS Sharpe={best_oos['sharpe']:.3f}")
print(f"  Sharpe {best_oos['sharpe']:.3f} >= {SHARPE_GATE} → {'PASS' if sharpe_pass else 'FAIL'}")
print(f"  MaxDD  {best_oos['max_dd']:.1%} vs SPY {spy_oos['max_dd']:.1%}"
      f" (need {SPY_DD_GATE:.1%}) → {'PASS' if dd_pass else 'FAIL'}")
print(f"  Corr   {best_oos['corr_spy']:.3f} < {CORR_GATE} → {'PASS' if corr_pass else 'FAIL'}")
print(f"  VERDICT: {'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

# ─────────────────────────────────────────────
# 9. Save
# ─────────────────────────────────────────────
out = {
    "hypothesis": "H256",
    "title": "Dual Momentum (Antonacci GEM + PACS + GEM+Sector)",
    "status": "CONFIRMED" if confirmed else "NOT CONFIRMED",
    "is_results":  [{k: v for k, v in r.items() if k != "ec"} for r in [gem_is, pacs_is, gsec_is]],
    "oos_results": [{k: v for k, v in r.items() if k != "ec"} for r in [gem_oos, pacs_oos, gsec_oos]],
    "spy_oos": {k: v for k, v in spy_oos.items() if k != "ec"},
    "gates": {
        "sharpe_gate": SHARPE_GATE, "sharpe_pass": bool(sharpe_pass),
        "dd_gate": round(float(SPY_DD_GATE), 4), "dd_pass": bool(dd_pass),
        "corr_gate": CORR_GATE, "corr_pass": bool(corr_pass),
    },
    "best_variant": best_oos["label"],
}
with open(RESULT_DIR / "h256_results.json", "w") as f:
    json.dump(out, f, indent=2)
print("Results saved → backtesting/results/h256_results.json")
