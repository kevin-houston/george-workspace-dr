"""
H219 — ETF Low-Volatility Anomaly (§3.4, 151 Trading Strategies)
=================================================================
The low-vol anomaly: lower-volatility assets earn HIGHER risk-adjusted returns.
Attributed to: leverage constraints (Black 1972), institutional benchmarking
(Baker, Bradley & Wurgler 2011), lottery preferences (Ang et al. 2006).

ETF-level test: universe of 14 broad ETFs spanning sectors, factors, and
asset classes. Monthly signal = trailing 3m realized volatility.
Portfolio: long bottom-3 (lowest vol), equal-weight, monthly rebalance.

Also tests:
  A. Low-vol portfolio (long bottom-3 by vol)
  B. High-vol portfolio (long top-3 by vol) — should UNDERPERFORM per anomaly
  C. VIX-regime switching: low-vol ETF when VIX > 20, high-vol when VIX ≤ 20
  D. Does USMV/SPLV systematically appear in the low-vol bucket?

ETF universe (14 tickers, all with data since ~2005):
  SPY   — US large-cap equity
  QQQ   — Nasdaq 100 (tech-heavy, high beta)
  IWM   — Russell 2000 small-cap
  XLK   — Technology sector
  XLF   — Financials sector
  XLE   — Energy sector
  XLU   — Utilities (classic defensive/low-vol)
  XLV   — Health Care sector
  XLP   — Consumer Staples (defensive)
  GLD   — Gold
  TLT   — 20+ Year Treasury (rates)
  EEM   — Emerging markets
  USMV  — iShares MSCI USA Min Vol Factor (inception: Oct 2011)
  SPLV  — Invesco S&P 500 Low Vol (inception: May 2011)

IS: 2013-2019 (7 years, starts after USMV/SPLV have 1yr history)
OOS: 2020-2026 (includes COVID crash, 2022 bear, 2023-24 bull)

Confirm: OOS Sharpe > 0.8 (ETF strategies vs stocks have lower expected Sharpe;
         low-vol ETF rotation should beat SPY on risk-adjusted basis)
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

UNIVERSE = ["SPY","QQQ","IWM","XLK","XLF","XLE","XLU","XLV","XLP","GLD","TLT","EEM","USMV","SPLV"]
VIX_TICKER = "^VIX"

DATA_START = "2011-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2019-12-31")
OOS_START  = pd.Timestamp("2020-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
TOP_N      = 3
VOL_WINDOW = 3   # months trailing realized vol
VIX_THRESH = 20  # regime gate
CONFIRM_THRESHOLD = 0.8


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r):  return float((1 + r).prod())
def maxdd(r):  eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0, "sharpe": 0.0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def fetch_monthly(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h219_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def fetch_daily(ticker: str) -> pd.Series:
    cp = CACHE_DIR / f"h219_{ticker}_daily_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker} (daily)…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"]
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def main():
    print("H219 — ETF Low-Volatility Anomaly")

    # Load monthly price data
    print("Loading monthly ETF prices…")
    prices_list = []
    for t in UNIVERSE:
        try:
            s = fetch_monthly(t)
            prices_list.append(s)
        except Exception as e:
            print(f"  WARN: {t} failed — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    monthly_ret = prices.pct_change()
    print(f"  Loaded {len(prices.columns)} ETFs, {len(prices)} months")

    # Load VIX (daily, downsample to monthly)
    print("Loading VIX…")
    try:
        vix_daily = fetch_daily(VIX_TICKER)
        vix_monthly = vix_daily.resample("ME").last()
        vix_monthly.name = "VIX"
    except Exception as e:
        print(f"  WARN: VIX load failed — {e}; regime test skipped")
        vix_monthly = None

    # SPY benchmark
    spy_ret = monthly_ret["SPY"].dropna() if "SPY" in monthly_ret.columns else None

    # Compute trailing 3m annualized realized volatility (monthly)
    # vol_i(t) = std of monthly returns over past VOL_WINDOW months × sqrt(12)
    vol_df = monthly_ret.rolling(VOL_WINDOW).std() * np.sqrt(12)
    vol_signal = vol_df.shift(1)  # known at end of month t → applied to month t+1

    def run_vol_strategy(long_lowest: bool, label: str) -> pd.Series:
        """Long top-N by lowest (or highest) realized vol, monthly rebalance."""
        port_rets = []
        for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
            loc = monthly_ret.index.get_loc(month_end)
            if month_end not in vol_signal.index:
                continue
            row = vol_signal.loc[month_end].dropna()
            if len(row) < TOP_N * 2:
                continue
            if long_lowest:
                sel = row.nsmallest(TOP_N).index.tolist()
            else:
                sel = row.nlargest(TOP_N).index.tolist()
            ret = monthly_ret.iloc[loc][sel].mean()
            port_rets.append((month_end, ret))
        s = pd.Series({d: r for d, r in port_rets})
        s.index = pd.DatetimeIndex(s.index)
        s.name = label
        return s

    # === Exp A: Low-vol portfolio ===
    print("\n=== Exp A: Low-vol vs High-vol ===")
    rets_low  = run_vol_strategy(long_lowest=True,  label="low-vol top-3")
    rets_high = run_vol_strategy(long_lowest=False, label="high-vol top-3")

    fmt = f"{'Strategy':<28} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    for label, rets in [("Low-vol top-3 (H219)", rets_low), ("High-vol top-3 (contrast)", rets_high)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<28} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    if spy_ret is not None:
        spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
        spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
        print(f"{'SPY BH':<28} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
              f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
              f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")
    else:
        spy_is = spy_oos = {}

    # === Exp B: How often does USMV/SPLV appear in low-vol bucket? ===
    print("\n=== Exp B: USMV/SPLV selection frequency ===")
    selection_counts = {t: 0 for t in UNIVERSE}
    total_months = 0
    for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
        if month_end not in vol_signal.index:
            continue
        row = vol_signal.loc[month_end].dropna()
        if len(row) < TOP_N * 2:
            continue
        total_months += 1
        sel = row.nsmallest(TOP_N).index.tolist()
        for t in sel:
            selection_counts[t] = selection_counts.get(t, 0) + 1
    print(f"  {total_months} months evaluated")
    sorted_counts = sorted(selection_counts.items(), key=lambda x: -x[1])
    for ticker, cnt in sorted_counts[:8]:
        print(f"    {ticker:6s}: selected {cnt:3d}/{total_months} months ({100*cnt/max(total_months,1):.0f}%)")

    # === Exp C: VIX-regime switching ===
    print("\n=== Exp C: VIX-regime switching ===")
    if vix_monthly is not None:
        regime_rets = []
        for month_end in monthly_ret.index[monthly_ret.index >= IS_START]:
            if month_end not in vol_signal.index:
                continue
            loc = monthly_ret.index.get_loc(month_end)
            row = vol_signal.loc[month_end].dropna()
            if len(row) < TOP_N * 2:
                continue

            # Get VIX value at signal month (shift 1 already applied)
            # Signal month = previous month; look up VIX from that month
            if month_end not in vix_monthly.index:
                # find nearest prior
                prior = vix_monthly.index[vix_monthly.index < month_end]
                if len(prior) == 0:
                    continue
                vix_val = float(vix_monthly.loc[prior[-1]])
            else:
                vix_val = float(vix_monthly.loc[month_end])

            if vix_val > VIX_THRESH:
                # High-vol regime: long lowest-vol ETFs (defensive)
                sel = row.nsmallest(TOP_N).index.tolist()
            else:
                # Low-vol regime: long highest-vol ETFs (growth/risk-on)
                sel = row.nlargest(TOP_N).index.tolist()

            ret = monthly_ret.iloc[loc][sel].mean()
            regime_rets.append((month_end, ret))

        rets_regime = pd.Series({d: r for d, r in regime_rets})
        rets_regime.index = pd.DatetimeIndex(rets_regime.index)
        reg_is  = eval_period(rets_regime, "VIX-regime switch", IS_START, IS_END)
        reg_oos = eval_period(rets_regime, "VIX-regime switch", OOS_START, OOS_END)
        print(f"  VIX-regime switch IS Sharpe {reg_is['sharpe']:.3f} | OOS Sharpe {reg_oos['sharpe']:.3f} | MaxDD {reg_oos.get('maxdd', 0):.1%}")
    else:
        reg_is = reg_oos = {}
        print("  VIX data unavailable — skipped")

    # === Vol window sensitivity ===
    print("\n=== Vol window sensitivity (low-vol portfolio) ===")
    sensitivity = {}
    for window in [1, 2, 3, 6, 12]:
        v = monthly_ret.rolling(window).std() * np.sqrt(12)
        v_sig = v.shift(1)
        pr = []
        for me in monthly_ret.index[monthly_ret.index >= IS_START]:
            if me not in v_sig.index:
                continue
            loc2 = monthly_ret.index.get_loc(me)
            row2 = v_sig.loc[me].dropna()
            if len(row2) < TOP_N * 2:
                continue
            sel2 = row2.nsmallest(TOP_N).index.tolist()
            pr.append((me, monthly_ret.iloc[loc2][sel2].mean()))
        s2 = pd.Series({d: r for d, r in pr})
        s2.index = pd.DatetimeIndex(s2.index)
        oos2 = eval_period(s2, f"{window}m vol", OOS_START, OOS_END)
        sensitivity[window] = oos2
        print(f"  Window {window:2d}m → OOS Sharpe {oos2['sharpe']:.3f} | MaxDD {oos2.get('maxdd',0):.1%}")

    # === Verdict ===
    low_is  = eval_period(rets_low, "low-vol top-3", IS_START, IS_END)
    low_oos = eval_period(rets_low, "low-vol top-3", OOS_START, OOS_END)
    confirmed = low_oos.get("sharpe", 0) >= CONFIRM_THRESHOLD

    print(f"\n=== Verdict ===")
    print(f"Low-vol ETF top-3 OOS Sharpe: {low_oos['sharpe']:.3f} (threshold ≥ {CONFIRM_THRESHOLD})")
    print(f"Low-vol ETF top-3 OOS MaxDD:  {low_oos.get('maxdd', 0):.1%}")
    print(f"VIX-regime OOS Sharpe:        {reg_oos.get('sharpe', 'n/a')}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H219",
        "universe": UNIVERSE,
        "vol_window": VOL_WINDOW,
        "vix_threshold": VIX_THRESH,
        "low_vol_is":  low_is,
        "low_vol_oos": low_oos,
        "high_vol_is": eval_period(rets_high, "high-vol", IS_START, IS_END),
        "high_vol_oos": eval_period(rets_high, "high-vol", OOS_START, OOS_END),
        "regime_is":   reg_is,
        "regime_oos":  reg_oos,
        "selection_counts": selection_counts,
        "vol_sensitivity": {str(k): v for k, v in sensitivity.items()},
        "spy_is": spy_is, "spy_oos": spy_oos,
        "confirmed": confirmed,
        "confirm_threshold": CONFIRM_THRESHOLD,
    }
    (RESULT_DIR / "h219_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"Saved → {RESULT_DIR}/h219_results.json")
    return out


if __name__ == "__main__":
    main()
