"""
H221 — Drift Regime + Short-Term Reversal (arXiv:2511.12490)
==============================================================
Singha (2025): activate reversal signal ONLY for stocks in a 'drift regime'
= stocks with >60% positive days in trailing 63 trading days.

Our implementation: apply H181 (1-month short-term reversal) exclusively to
stocks in drift regime. Out-of-regime stocks get zero allocation.

Universe: same 30 large-cap stocks as H181/H217
IS: 2013-2020, OOS: 2021-2026
Drift threshold: >60% positive days in trailing 63 trading days
Signal: 1-month close return (same as H181)
Portfolio: long bottom-N by last month return among drift-regime stocks
Confirm: OOS Sharpe > 1.4 (must beat H181's 1.138 meaningfully)
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
CACHE_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

UNIVERSE = [
    "AAPL","MSFT","AMZN","GOOGL","META","TSLA","NVDA","AVGO","QCOM","AMD",
    "V","MA","BAC","WFC","JPM","UNH","LLY","PFE","JNJ","ABBV",
    "WMT","HD","SBUX","LOW","COST","CVX","XOM","BA","CAT","IBM",
]

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

DRIFT_THRESHOLD = 0.60   # fraction of positive days in 63-day window
DRIFT_WINDOW    = 63     # trading days (~3 months)
TOP_N           = 3      # bottom-3 reversal picks (fewer stocks since regime filter)
CONFIRM_THRESHOLD = 1.4


def fetch_daily_ohlcv(ticker: str) -> pd.DataFrame:
    cp = CACHE_DIR / f"h215_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp)
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    raw.index = pd.to_datetime(raw.index).tz_localize(None)
    cp2 = CACHE_DIR / f"h215_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    raw.to_parquet(cp2)
    return raw


def sharpe(rets: pd.Series, ann: int = 12) -> float:
    if rets.std() == 0:
        return 0.0
    return float(rets.mean() / rets.std() * np.sqrt(ann))


def maxdd(rets: pd.Series) -> float:
    cum = (1 + rets).cumprod()
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    return float(dd.min())


def neg_years(rets: pd.Series) -> int:
    ann = rets.resample("YE").apply(lambda r: (1 + r).prod() - 1)
    return int((ann < 0).sum())


# ── load daily data ──────────────────────────────────────────────────────────
print("Loading daily OHLCV for 30 stocks…")
close_daily = {}
for tk in UNIVERSE:
    df = fetch_daily_ohlcv(tk)
    close_daily[tk] = df["close"]

close_daily_df = pd.DataFrame(close_daily).sort_index()
close_daily_df.index = pd.to_datetime(close_daily_df.index).tz_localize(None)

# ── compute daily returns and drift regime ───────────────────────────────────
print("Computing drift regime signals…")
daily_ret = close_daily_df.pct_change()

# At each day, fraction of positive days in trailing 63-day window
# (rolling on daily data)
drift_regime_daily = (daily_ret > 0).rolling(DRIFT_WINDOW, min_periods=50).mean()

# ── resample to month-end ────────────────────────────────────────────────────
# Month-end close price → 1-month return (reversal signal)
monthly_close = close_daily_df.resample("ME").last()
monthly_ret   = monthly_close.pct_change()  # forward return (used for portfolio return)

# Drift regime at month-end: value as of last trading day of that month
drift_month = drift_regime_daily.resample("ME").last()

# Reversal signal: last month's return (use 1-month lag)
# signal at month t = return of month t-1 (buy losers = lowest signal)
reversal_signal = monthly_ret.shift(1)  # shift(1): use prior month return as signal

# ── build portfolio returns ──────────────────────────────────────────────────
print("Building regime-gated reversal portfolio…")

portfolio_rets = []
dates_list = monthly_ret.index

for date in dates_list:
    if date < IS_START:
        continue

    # Drift regime: use regime as of PRIOR month end (avoid lookahead)
    prior_date_idx = dates_list.get_loc(date) - 1
    if prior_date_idx < 0:
        continue
    prior_date = dates_list[prior_date_idx]

    regime_row = drift_month.loc[prior_date] if prior_date in drift_month.index else None
    signal_row = reversal_signal.loc[date]

    if regime_row is None:
        continue

    # Filter to stocks in drift regime (prior month)
    regime_stocks = regime_row[regime_row > DRIFT_THRESHOLD].index.tolist()
    regime_stocks = [s for s in regime_stocks if not pd.isna(signal_row.get(s, np.nan))]

    if len(regime_stocks) < 2:
        # Not enough regime stocks — go to cash (0 return)
        portfolio_rets.append({"date": date, "ret": 0.0, "n_regime": len(regime_stocks)})
        continue

    # Among regime stocks, pick bottom-N by prior month return (reversal)
    sig = signal_row[regime_stocks].dropna().sort_values()
    picks = sig.iloc[:TOP_N].index.tolist()

    # Equal-weight return this month
    fwd_rets = monthly_ret.loc[date, picks].dropna()
    if fwd_rets.empty:
        portfolio_rets.append({"date": date, "ret": 0.0, "n_regime": len(regime_stocks)})
    else:
        portfolio_rets.append({"date": date, "ret": float(fwd_rets.mean()),
                               "n_regime": len(regime_stocks)})

port_df = pd.DataFrame(portfolio_rets).set_index("date")
port_df.index = pd.to_datetime(port_df.index)

# ── IS / OOS split ───────────────────────────────────────────────────────────
is_rets  = port_df.loc[IS_START:IS_END, "ret"]
oos_rets = port_df.loc[OOS_START:OOS_END, "ret"]

# ── SPY benchmark ────────────────────────────────────────────────────────────
spy_d = fetch_daily_ohlcv("AAPL")  # use cache check; fetch SPY separately
spy_cp = CACHE_DIR / f"h221_SPY_monthly.parquet"
if spy_cp.exists():
    spy_monthly = pd.read_parquet(spy_cp)["ret"]
else:
    spy_raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
    if isinstance(spy_raw.columns, pd.MultiIndex):
        spy_raw = spy_raw.xs("SPY", axis=1, level=1)
    spy_monthly = spy_raw["Close"] if "Close" in spy_raw.columns else spy_raw["close"].resample("ME").last().pct_change()
    spy_monthly.index = pd.to_datetime(spy_monthly.index).tz_localize(None)
    pd.DataFrame({"ret": spy_monthly}).to_parquet(spy_cp)

spy_oos = spy_monthly.loc[OOS_START:OOS_END]

# ── H181 baseline (unconstrained reversal) ───────────────────────────────────
# Reconstruct H181: bottom-3 by last month return, all stocks
h181_rets = []
for date in dates_list:
    if date < IS_START:
        continue
    signal_row = reversal_signal.loc[date]
    fwd = monthly_ret.loc[date]
    valid_sig = signal_row.dropna().sort_values()
    if len(valid_sig) < 3:
        h181_rets.append({"date": date, "ret": 0.0})
        continue
    picks = valid_sig.iloc[:3].index.tolist()
    h181_rets.append({"date": date, "ret": float(fwd[picks].dropna().mean())})

h181_df = pd.DataFrame(h181_rets).set_index("date")
h181_df.index = pd.to_datetime(h181_df.index)
h181_oos = h181_df.loc[OOS_START:OOS_END, "ret"]

# ── Experiment B: sensitivity to threshold ───────────────────────────────────
print("\nExp B: sensitivity to drift threshold…")
thresholds = [0.50, 0.55, 0.60, 0.65, 0.70]
threshold_results = []
for thr in thresholds:
    t_rets = []
    for date in dates_list:
        if date < OOS_START or date > OOS_END:
            continue
        prior_date_idx = dates_list.get_loc(date) - 1
        if prior_date_idx < 0:
            continue
        prior_date = dates_list[prior_date_idx]
        if prior_date not in drift_month.index:
            continue
        regime_row = drift_month.loc[prior_date]
        signal_row = reversal_signal.loc[date]
        regime_stocks = regime_row[regime_row > thr].index.tolist()
        regime_stocks = [s for s in regime_stocks if not pd.isna(signal_row.get(s, np.nan))]
        if len(regime_stocks) < 2:
            t_rets.append(0.0)
            continue
        sig = signal_row[regime_stocks].dropna().sort_values()
        picks = sig.iloc[:TOP_N].index.tolist()
        fwd = monthly_ret.loc[date, picks].dropna()
        t_rets.append(float(fwd.mean()) if not fwd.empty else 0.0)
    s = sharpe(pd.Series(t_rets))
    threshold_results.append({"threshold": thr, "oos_sharpe": round(s, 3)})
    print(f"  Threshold {thr:.0%}: OOS Sharpe {s:.3f}")

# ── Experiment C: correlation with H181 ──────────────────────────────────────
oos_common = port_df.loc[OOS_START:OOS_END, "ret"].reindex(h181_oos.index).dropna()
h181_common = h181_oos.reindex(oos_common.index).dropna()
corr_h221_h181 = float(oos_common.corr(h181_common))
print(f"\nCorr(H221, H181) OOS: {corr_h221_h181:.3f}")

# ── Results ──────────────────────────────────────────────────────────────────
is_sh  = sharpe(is_rets)
oos_sh = sharpe(oos_rets)
oos_md = maxdd(oos_rets)
oos_ny = neg_years(oos_rets)
spy_sh = sharpe(spy_oos)
h181_sh = sharpe(h181_oos)

avg_regime = port_df.loc[OOS_START:OOS_END, "n_regime"].mean()

confirmed = oos_sh >= CONFIRM_THRESHOLD

print("\n" + "="*60)
print("H221 — DRIFT REGIME + REVERSAL RESULTS")
print("="*60)
print(f"\n  IS  Sharpe  : {is_sh:.3f}")
print(f"  OOS Sharpe  : {oos_sh:.3f}  (threshold: {CONFIRM_THRESHOLD})")
print(f"  OOS MaxDD   : {oos_md:.1%}")
print(f"  OOS NegYrs  : {oos_ny}")
print(f"  SPY OOS     : {spy_sh:.3f}")
print(f"  H181 OOS    : {h181_sh:.3f}  (unconstrained baseline)")
print(f"  Avg regime stocks/month: {avg_regime:.1f} of 30")
print(f"\n  Corr(H221, H181) OOS: {corr_h221_h181:.3f}")
print(f"\n  STATUS: {'✅ CONFIRMED' if confirmed else '❌ NOT CONFIRMED'}")

results = {
    "hypothesis": "H221",
    "description": "Drift Regime + Short-Term Reversal",
    "drift_threshold": DRIFT_THRESHOLD,
    "drift_window": DRIFT_WINDOW,
    "top_n": TOP_N,
    "is": {"sharpe": round(is_sh, 3)},
    "oos": {"sharpe": round(oos_sh, 3), "maxdd": round(oos_md, 4), "neg_yrs": oos_ny},
    "spy_oos_sharpe": round(spy_sh, 3),
    "h181_oos_sharpe": round(h181_sh, 3),
    "corr_h221_h181_oos": round(corr_h221_h181, 3),
    "avg_regime_stocks_oos": round(float(avg_regime), 1),
    "threshold_sensitivity": threshold_results,
    "confirmed": confirmed,
    "confirm_threshold": CONFIRM_THRESHOLD,
}

out = RESULT_DIR / "h221_results.json"
with open(out, "w") as f:
    json.dump(results, f, indent=2)
print(f"\nResults saved → {out}")
