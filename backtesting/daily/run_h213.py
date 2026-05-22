"""
H213 — Idiosyncratic Volatility Anomaly (Ang et al. 2006)
==========================================================
Ang, Hodrick, Xing, Zhang (JF 2006) "The Cross-Section of Volatility and Expected Returns":
stocks with HIGH idiosyncratic volatility earn LOWER future returns (the IVOL puzzle).

This anomaly persists in large-caps and conflicts with standard theory (high risk = high return).
Proposed mechanism: lottery-demand from retail investors overprices high-IVOL stocks;
institutional limits-to-arbitrage prevent correction.

Cross-sectional implementation:
  IVOL_i(t) = std of residuals from regressing stock returns on SPY over trailing 3m daily returns
  Signal: -IVOL_i (short high-IVOL, or equivalently, long low-IVOL = lowest-IVOL stocks outperform)

Portfolio: Long bottom-6 by IVOL (= lowest IVOL), equal-weight, monthly rebalance
Note: at monthly data frequency we approximate IVOL via residual from beta-adjusted SPY
IS: 2013-2020, OOS: 2021-2026
Confirm: OOS Sharpe > 0.8 (distinct from SPY B&H at ~0.95); MaxDD < -25%

Cross-reference: H192-D (BAB) is correlated — both target low-beta/low-vol stocks.
Key diagnostic: correlation with H192-D and H198.
"""

import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
from scipy import stats

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
IVOL_WINDOW = 3    # months trailing for IVOL estimate


def fetch_price_monthly(ticker: str) -> pd.Series:
    for prefix in [f"h{i:03d}" for i in range(181, 214)]:
        cp = CACHE_DIR / f"{prefix}_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
        if cp.exists():
            return pd.read_parquet(cp).squeeze()
    cp = CACHE_DIR / f"h213_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
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


def sharpe(r): return float(r.mean() / r.std() * np.sqrt(12)) if r.std() > 0 else 0.0
def cumul(r): return float((1 + r).prod())
def maxdd(r): eq = (1 + r).cumprod(); return float((eq / eq.cummax() - 1).min())


def compute_ivol_monthly(monthly_ret: pd.DataFrame, spy_ret: pd.Series,
                          window: int = 3) -> pd.DataFrame:
    """
    Compute IVOL for each stock at each month-end:
    IVOL = std(residuals) from OLS of stock_ret ~ spy_ret over trailing window months.
    Monthly approximation: sufficient for cross-sectional ranking signal.
    """
    ivol_records = []
    for loc in range(window, len(monthly_ret)):
        month_end = monthly_ret.index[loc]
        slice_stk = monthly_ret.iloc[loc - window : loc]
        slice_spy = spy_ret.reindex(slice_stk.index)
        valid_spy = slice_spy.dropna()
        if len(valid_spy) < window:
            continue
        ivol_row = {}
        for ticker in monthly_ret.columns:
            stk = slice_stk[ticker].reindex(valid_spy.index).dropna()
            spy = valid_spy.reindex(stk.index)
            if len(stk) < window:
                ivol_row[ticker] = np.nan
                continue
            # OLS: stk = alpha + beta * spy + epsilon
            slope, intercept, _, _, _ = stats.linregress(spy.values, stk.values)
            residuals = stk.values - (intercept + slope * spy.values)
            ivol_row[ticker] = residuals.std() * np.sqrt(12)  # annualized
        ivol_records.append((month_end, ivol_row))

    ivol_df = pd.DataFrame([row for _, row in ivol_records],
                            index=pd.DatetimeIndex([dt for dt, _ in ivol_records]))
    return ivol_df


def backtest_ivol(monthly_ret: pd.DataFrame, ivol_df: pd.DataFrame,
                  top_n: int = 6, long_low: bool = True) -> pd.Series:
    """
    long_low=True: long lowest IVOL (Ang et al.: low IVOL = higher returns)
    long_low=False: long highest IVOL (contrarian, expected to lose)
    """
    port_rets = []
    months = monthly_ret.index[monthly_ret.index >= IS_START]
    for month_end in months:
        if month_end not in ivol_df.index:
            continue
        loc = monthly_ret.index.get_loc(month_end)
        ivol_row = ivol_df.loc[month_end].dropna()
        if len(ivol_row) < top_n:
            continue
        if long_low:
            selected = ivol_row.nsmallest(top_n).index.tolist()
        else:
            selected = ivol_row.nlargest(top_n).index.tolist()
        ret_this = monthly_ret.iloc[loc][selected].mean()
        port_rets.append((month_end, ret_this))
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
    print("H213 — Idiosyncratic Volatility Anomaly (Ang et al. 2006)")
    print("Loading price data…")
    prices_list = []
    for t in UNIVERSE:
        try:
            prices_list.append(fetch_price_monthly(t))
        except Exception as e:
            print(f"  WARN: {t} — {e}")
    prices = pd.DataFrame(prices_list).T.sort_index().loc[DATA_START:]

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

    print(f"  {len(prices.columns)} tickers, {len(prices)} months")
    monthly_ret = prices.pct_change()

    print("\nComputing IVOL matrix (trailing 3m OLS residuals)…")
    ivol_df = compute_ivol_monthly(monthly_ret, spy_ret, window=IVOL_WINDOW)
    print(f"  IVOL matrix: {ivol_df.shape[0]} rows × {ivol_df.shape[1]} cols")
    avg_ivol = ivol_df.mean(axis=0)
    print(f"  Mean IVOL by ticker (annualized std of residuals):")
    print(f"  Lowest 5: {avg_ivol.nsmallest(5).round(3).to_dict()}")
    print(f"  Highest 5: {avg_ivol.nlargest(5).round(3).to_dict()}")

    print("\n=== Exp A: Long low-IVOL vs Long high-IVOL (top-6) ===")
    rets_low  = backtest_ivol(monthly_ret, ivol_df, top_n=6, long_low=True)
    rets_high = backtest_ivol(monthly_ret, ivol_df, top_n=6, long_low=False)

    fmt = f"{'Strategy':<22} {'IS Sharpe':>10} {'IS Cumul':>10} {'OOS Sharpe':>10} {'OOS Cumul':>10} {'MaxDD':>8} {'NegYrs':>7}"
    print(fmt)
    print("-" * len(fmt))
    spy_is  = eval_period(spy_ret, "SPY", IS_START, IS_END)
    spy_oos = eval_period(spy_ret, "SPY", OOS_START, OOS_END)
    for label, rets in [("Low IVOL (H213)", rets_low), ("High IVOL", rets_high)]:
        is_  = eval_period(rets, label, IS_START, IS_END)
        oos_ = eval_period(rets, label, OOS_START, OOS_END)
        print(f"{label:<22} {is_['sharpe']:>10.3f} {is_['cumul']:>10.4f} "
              f"{oos_['sharpe']:>10.3f} {oos_['cumul']:>10.4f} "
              f"{oos_['maxdd']:>8.1%} {oos_['neg_yrs']:>7d}")
    print(f"{'SPY BH':<22} {spy_is['sharpe']:>10.3f} {spy_is['cumul']:>10.4f} "
          f"{spy_oos['sharpe']:>10.3f} {spy_oos['cumul']:>10.4f} "
          f"{spy_oos['maxdd']:>8.1%} {spy_oos['neg_yrs']:>7d}")

    print("\n=== Exp B: IVOL window sensitivity ===")
    results_b = {}
    for window in [2, 3, 6]:
        ivol_w = compute_ivol_monthly(monthly_ret, spy_ret, window=window)
        rets_w = backtest_ivol(monthly_ret, ivol_w, top_n=6, long_low=True)
        is_  = eval_period(rets_w, f"w={window}", IS_START, IS_END)
        oos_ = eval_period(rets_w, f"w={window}", OOS_START, OOS_END)
        results_b[window] = {"is": is_, "oos": oos_}
        print(f"  Window={window}m:  IS Sharpe {is_['sharpe']:.3f} | OOS Sharpe {oos_['sharpe']:.3f}")

    print("\n=== Correlations ===")
    all_low = rets_low[(rets_low.index >= IS_START) & (rets_low.index <= OOS_END)]
    spy_all = spy_ret.reindex(all_low.index)
    print(f"  Low-IVOL vs SPY: {all_low.corr(spy_all):.3f}")

    lo_is  = eval_period(rets_low, "low-IVOL", IS_START, IS_END)
    lo_oos = eval_period(rets_low, "low-IVOL", OOS_START, OOS_END)
    confirmed = lo_oos.get("sharpe", 0) > 0.8

    print(f"\n=== Verdict ===")
    print(f"Low-IVOL OOS Sharpe: {lo_oos['sharpe']:.3f} (threshold >0.8)")
    print(f"Low-IVOL OOS MaxDD:  {lo_oos['maxdd']:.1%}")
    print(f"{'CONFIRMED' if confirmed else 'NOT CONFIRMED'}")

    out = {
        "hypothesis": "H213",
        "low_ivol_is": lo_is, "low_ivol_oos": lo_oos,
        "high_ivol_is": eval_period(rets_high, "high", IS_START, IS_END),
        "high_ivol_oos": eval_period(rets_high, "high", OOS_START, OOS_END),
        "window_sensitivity": results_b,
        "spy_is": spy_is, "spy_oos": spy_oos,
        "confirmed": confirmed,
    }
    (RESULT_DIR / "h213_results.json").write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {RESULT_DIR}/h213_results.json")
    return out


if __name__ == "__main__":
    main()
