"""
H212 — Volatility-Scaled Cross-Sectional Momentum (Barroso & Santa-Clara 2015)
==============================================================================
Key insight from Barroso & Santa-Clara (JFE 2015) "Momentum has its moments":
volatility-scaling the momentum signal by trailing realized vol reduces momentum
crashes by ~50% and substantially improves Sharpe.

Cross-sectional application:
  vol_scaled_signal_i = R(t-7, t-1) / realized_vol_i(t)

where realized_vol_i = std of last 6 monthly returns (annualized).

Universe: same 30 large-cap S&P 500 stocks as H181/H192-D/H198
Signal: 6-1m return divided by trailing 6m realized vol
Portfolio: Long top-6 by vol-scaled signal, equal-weight, monthly rebalance
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 1.3 (beat H198's 1.174); MaxDD < H198's -22.7%

Key question: does vol-scaling improve Sharpe AND reduce crash? If so, replaces H198.
If similar Sharpe but lower corr, it adds diversification.
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
TOP_N      = 6
VOL_WINDOW = 6    # months for trailing vol estimate
TC_BPS     = 5


def fetch_price(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 213)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h212_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
    if cp.exists():
        return pd.read_parquet(cp).squeeze()
    print(f"  Downloading {ticker}…")
    raw = yf.download(ticker, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs(ticker, axis=1, level=1)
    s = raw["Close"].resample("ME").last()
    s.name = ticker
    pd.DataFrame(s).to_parquet(cp)
    return s


def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0


def cumul(r: pd.Series) -> float:
    return float((1 + r).prod())


def maxdd(r: pd.Series) -> float:
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def backtest_volscaled(prices: pd.DataFrame, lookback: int = 6,
                       vol_window: int = 6, top_n: int = 6) -> pd.Series:
    """
    Vol-scaled cross-sectional momentum.
    Signal = R(t-lookback-1, t-1) / sigma_i(t)
    sigma_i = std of last vol_window monthly returns * sqrt(12)
    """
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]

    for i, month_end in enumerate(months):
        loc = monthly_ret.index.get_loc(month_end)
        # Need lookback+1 bars for signal + vol_window bars for vol estimate
        min_bars = max(lookback + 1, vol_window)
        if loc < min_bars:
            continue

        # Raw 6-1m momentum signal (skip last month)
        sig_start = loc - lookback - 1
        sig_end   = loc - 1
        if sig_start < 0:
            continue
        raw_sig = prices.iloc[sig_end] / prices.iloc[sig_start] - 1

        # Trailing vol: std of last vol_window monthly returns (annualized)
        vol_slice = monthly_ret.iloc[loc - vol_window : loc]
        trailing_vol = vol_slice.std() * np.sqrt(12)
        trailing_vol = trailing_vol.replace(0, np.nan)

        # Vol-scaled signal: raw return / trailing vol
        scaled_sig = raw_sig / trailing_vol
        scaled_sig = scaled_sig.dropna()

        if len(scaled_sig) < top_n:
            continue

        selected = scaled_sig.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))

    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def backtest_raw(prices: pd.DataFrame, lookback: int = 6, top_n: int = 6) -> pd.Series:
    """Raw momentum for direct comparison."""
    monthly_ret = prices.pct_change()
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for i, month_end in enumerate(months):
        loc = monthly_ret.index.get_loc(month_end)
        if loc < lookback + 1:
            continue
        sig = prices.iloc[loc - 1] / prices.iloc[loc - lookback - 1] - 1
        sig = sig.dropna()
        if len(sig) < top_n:
            continue
        selected = sig.nlargest(top_n).index.tolist()
        port_rets.append((month_end, monthly_ret.iloc[loc][selected].mean()))
    s = pd.Series({d: r for d, r in port_rets})
    s.index = pd.DatetimeIndex(s.index)
    return s


def eval_period(rets, label, start, end):
    r = rets[(rets.index >= start) & (rets.index <= end)]
    if len(r) < 6:
        return {"label": label, "n": 0}
    return {
        "label": label, "n": len(r),
        "sharpe": round(sharpe(r), 3),
        "cagr":   round(float(r.mean() * 12), 3),
        "cumul":  round(cumul(r), 4),
        "maxdd":  round(maxdd(r), 3),
        "neg_yrs": int(sum(r.resample("YE").apply(lambda x: (1+x).prod()-1) < 0)),
    }


def main():
    print("H212 — Volatility-Scaled Cross-Sectional Momentum")
    print("Loading price data…")
    prices_list = []
    for t in UNIVERSE:
        try:
            prices_list.append(fetch_price(t))
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]
    print(f"  {len(prices.columns)} tickers, {len(prices)} months")

    spy_cp = CACHE_DIR / f"h198_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cp.exists():
        spy_px = pd.read_parquet(spy_cp).squeeze()
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END, auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        spy_px = raw["Close"].resample("ME").last()
        spy_px.name = "SPY"
        pd.DataFrame(spy_px).to_parquet(spy_cp)
    spy_ret = spy_px.pct_change().dropna()

    print("\n=== Exp A: Vol-scaled 6-1m vs raw 6-1m (top-6) ===")
    rets_vs  = backtest_volscaled(prices, lookback=6, vol_window=6, top_n=6)
    rets_raw = backtest_raw(prices, lookback=6, top_n=6)

    fmt = f"{'Strategy':<22} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    for label, rets in [("Vol-scaled 6-1m", rets_vs), ("Raw 6-1m (H198)", rets_raw)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<22} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    print(f"{'SPY BH':<22} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    print("\n=== Exp B: Vol window sensitivity (3m, 6m, 12m) ===")
    results_b = {}
    for vw in [3, 6, 12]:
        r = backtest_volscaled(prices, lookback=6, vol_window=vw, top_n=6)
        is_  = eval_period(r, f"vw={vw}", IS_START, IS_END)
        oos_ = eval_period(r, f"vw={vw}", OOS_START, OOS_END)
        results_b[vw] = {"is": is_, "oos": oos_}
        print(f"Vol window={vw:2d}m:  IS Sharpe {is_['sharpe']:.3f} | OOS Sharpe {oos_['sharpe']:.3f} | MaxDD {oos_['maxdd']:.1%}")

    print("\n=== Correlations ===")
    all_vs  = rets_vs[(rets_vs.index >= IS_START) & (rets_vs.index <= OOS_END)]
    all_raw = rets_raw[(rets_raw.index >= IS_START) & (rets_raw.index <= OOS_END)]
    spy_all = spy_ret.reindex(all_vs.index)
    print(f"  Vol-scaled vs SPY:   {all_vs.corr(spy_all):.3f}")
    print(f"  Raw 6-1m vs SPY:     {all_raw.corr(spy_all):.3f}")
    print(f"  Vol-scaled vs Raw:   {all_vs.corr(all_raw.reindex(all_vs.index)):.3f}")

    # Crash analysis: worst 3 months for raw momentum
    print("\n=== Crash comparison (worst 5 months for raw 6-1m) ===")
    oos_raw = rets_raw[(rets_raw.index >= OOS_START) & (rets_raw.index <= OOS_END)]
    oos_vs  = rets_vs[(rets_vs.index >= OOS_START) & (rets_vs.index <= OOS_END)]
    worst5  = oos_raw.nsmallest(5)
    for dt, raw_r in worst5.items():
        vs_r = oos_vs.get(dt, np.nan)
        print(f"  {dt.strftime('%Y-%m')}: Raw {raw_r:+.1%}  Vol-scaled {vs_r:+.1%}")

    vs_is  = eval_period(rets_vs, "vol-scaled", IS_START, IS_END)
    vs_oos = eval_period(rets_vs, "vol-scaled", OOS_START, OOS_END)
    confirmed = vs_oos.get("sharpe", 0) > 1.3 and vs_oos.get("maxdd", -99) > -0.227

    print(f"\n=== Verdict ===")
    print(f"Vol-scaled OOS Sharpe: {vs_oos['sharpe']:.3f} (threshold >1.3)")
    print(f"Vol-scaled OOS MaxDD:  {vs_oos['maxdd']:.1%} (H198 baseline: -22.7%)")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H212",
        "vol_scaled_is": vs_is, "vol_scaled_oos": vs_oos,
        "raw_is": eval_period(rets_raw, "raw", IS_START, IS_END),
        "raw_oos": eval_period(rets_raw, "raw", OOS_START, OOS_END),
        "vol_window_sensitivity": results_b,
        "spy_is": spy_is, "spy_oos": spy_oos,
        "confirmed": confirmed,
    }
    (RESULT_DIR / "h212_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {RESULT_DIR}/h212_results.json")
    return out


if __name__ == "__main__":
    main()
