"""
H188 — 52-Week High Proximity Momentum
=======================================
Source: George & Hwang (2004) "The 52-Week High and Momentum Investing"
Journal of Finance 59(5): 2145-2176.

Hypothesis: Stocks trading closest to their 52-week high outperform over
the next month. Mechanism: anchoring bias — investors are reluctant to pay
above recent all-time highs even when fundamentals justify it, causing
temporary underpricing that resolves as the stock breaks out.

Signal: prox_i = P_t / max(P_{t-252d:t-1})
  - Ranges from 0 (far from 52wk high) to ~1.0 (at/near 52wk high)
  - Stocks nearest 52-week high expected to continue outperforming

Strategy:
  - Universe: same 30 large-cap S&P 500 stocks as H181
  - Portfolio: long top-6 (highest proximity to 52-week high), equal-weight
  - Rebalance: monthly
  - IS: 2013–2020, OOS: 2021–2026
  - Confirm: OOS Sharpe > 0.5, OOS cumul > 1.3×

Compare vs:
  - H181 (industry-adjusted reversal, same universe) — opposite signal
  - SPY buy-and-hold

Question: Do momentum (H188) and reversal (H181) signals generate different
alpha with low correlation? If so, a blend (H189) could outperform either alone.
"""

import warnings
warnings.filterwarnings("ignore")

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

UNIVERSE_SECTORS = {
    "AAPL": "Information Technology", "MSFT": "Information Technology",
    "AMZN": "Consumer Discretionary", "GOOGL": "Communication Services",
    "META": "Communication Services", "TSLA": "Consumer Discretionary",
    "NVDA": "Information Technology", "AVGO": "Information Technology",
    "QCOM": "Information Technology", "AMD":  "Information Technology",
    "V":    "Financials",             "MA":   "Financials",
    "BAC":  "Financials",             "WFC":  "Financials",  "JPM": "Financials",
    "UNH":  "Health Care",            "LLY":  "Health Care",
    "PFE":  "Health Care",            "JNJ":  "Health Care", "ABBV": "Health Care",
    "WMT":  "Consumer Staples",       "HD":   "Consumer Discretionary",
    "SBUX": "Consumer Discretionary", "LOW":  "Consumer Discretionary",
    "COST": "Consumer Staples",       "CVX":  "Energy",      "XOM":  "Energy",
    "BA":   "Industrials",            "CAT":  "Industrials", "IBM":  "Information Technology",
}

UNIVERSE = list(UNIVERSE_SECTORS.keys())

DATA_START = "2012-01-01"   # extra year for 52-week high lookback
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

QUINTILE_N = 6   # top-6 by 52-week high proximity


def load_daily_prices() -> pd.DataFrame:
    """Load daily adj close for all 30 tickers."""
    cache_file = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache_file.exists():
        print("  Loading from cache…")
        df = pd.read_parquet(cache_file)
        return df

    print(f"  Downloading {len(UNIVERSE)} tickers from yfinance…")
    raw = yf.download(UNIVERSE, start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"]
    else:
        prices = raw
    prices = prices.dropna(how="all", axis=0)
    prices.to_parquet(cache_file)
    return prices


def compute_52wk_high_proximity(daily_prices: pd.DataFrame, rebal_date: pd.Timestamp) -> pd.Series:
    """
    For each stock, compute proximity to 52-week high as of rebal_date.
    proximity = last_close / max(close over prior 252 trading days)
    Returns pd.Series indexed by ticker.
    """
    # Get data up to and including rebal_date
    hist = daily_prices[daily_prices.index <= rebal_date]
    if len(hist) < 253:
        return pd.Series(dtype=float)

    last_close = hist.iloc[-1]
    high_252d  = hist.tail(252).max()   # 52-week high (252 trading days)

    proximity = last_close / high_252d
    return proximity.dropna()


def run_backtest(daily_prices: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly rebalance using 52-week high proximity signal.
    Each month:
      1. Compute proximity_i = P_t / max(P_{t-252d})
      2. Long top-6 (highest proximity)
      3. Record equal-weight portfolio return that month
    """
    monthly_px = daily_prices.resample("ME").last()
    month_ends = monthly_px.index

    records = []
    for i in range(1, len(month_ends)):
        rebal_date = month_ends[i - 1]  # signal computed at end of prior month
        hold_date  = month_ends[i]      # return realized at end of this month

        # Need prior 252 days of data for signal
        if rebal_date < pd.Timestamp(DATA_START) + pd.DateOffset(months=13):
            continue

        # Compute proximity signal as of rebal_date
        prox = compute_52wk_high_proximity(daily_prices, rebal_date)
        if len(prox) < QUINTILE_N * 2:
            continue

        # Long top-6 (highest proximity = nearest to 52-week high)
        long_tickers = prox.nlargest(QUINTILE_N).index.tolist()

        # Compute this month's returns for the held tickers
        current_rets = {}
        for t in long_tickers:
            if t in monthly_px.columns:
                p1 = monthly_px.loc[rebal_date, t] if rebal_date in monthly_px.index else np.nan
                p2 = monthly_px.loc[hold_date,  t] if hold_date  in monthly_px.index else np.nan
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    current_rets[t] = (p2 - p1) / p1

        if not current_rets:
            continue

        port_ret = np.mean(list(current_rets.values()))
        records.append({
            "date":         hold_date,
            "port_ret":     port_ret,
            "n_held":       len(current_rets),
            "long_tickers": ",".join(long_tickers),
            "avg_proximity": prox[long_tickers].mean(),
        })

    return pd.DataFrame(records).set_index("date")


def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    if len(returns) == 0:
        return {"label": label}
    cum    = (1 + returns).cumprod()
    n_yrs  = len(returns) / 12.0
    cagr   = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = (returns.mean() / returns.std() * np.sqrt(12)) if returns.std() > 0 else 0.0
    dd     = ((cum / cum.cummax()) - 1)
    return {
        "label":         label,
        "n_months":      len(returns),
        "cumul":         round(float(cum.iloc[-1]), 4),
        "cagr_pct":      round(cagr * 100, 2),
        "sharpe":        round(sharpe, 3),
        "max_dd_pct":    round(float(dd.min()) * 100, 2),
        "neg_years":     int(returns.resample("YE").apply(lambda x: (1+x).prod()-1).lt(0).sum()),
        "mean_monthly":  round(float(returns.mean()) * 100, 3),
    }


def main():
    print("=" * 64)
    print("  H188 — 52-Week High Proximity Momentum")
    print("  George & Hwang (2004), Journal of Finance")
    print("=" * 64)

    print(f"\n[1/5] Loading daily prices for {len(UNIVERSE)} tickers…")
    prices = load_daily_prices()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 300]
    print(f"  Available: {len(available)}/{len(UNIVERSE)} tickers, "
          f"{prices.index[0].date()} → {prices.index[-1].date()}")
    prices = prices[available]

    print("\n[2/5] Loading SPY benchmark…")
    spy_cache = CACHE_DIR / f"h181_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cache.exists():
        spy_close = pd.read_parquet(spy_cache)["close"]
    else:
        raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw = raw.xs("SPY", axis=1, level=1)
        close_col = "Close" if "Close" in raw.columns else raw.columns[0]
        spy_close = raw[close_col].resample("ME").last().dropna()
    spy_ret = spy_close.pct_change().dropna()

    print("\n[3/5] Running monthly backtest (52-week high proximity)…")
    port_df = run_backtest(prices)
    print(f"  Total monthly observations: {len(port_df)}")
    print(f"  Avg stocks held/month: {port_df['n_held'].mean():.1f}")
    print(f"  Avg proximity of selected stocks: {port_df['avg_proximity'].mean():.3f}")

    is_df  = port_df[(port_df.index >= IS_START)  & (port_df.index <= IS_END)]
    oos_df = port_df[(port_df.index >= OOS_START) & (port_df.index <= OOS_END)]
    print(f"  IS months: {len(is_df)}  |  OOS months: {len(oos_df)}")

    print("\n[4/5] Computing performance metrics…")
    is_m   = calc_metrics(is_df["port_ret"],  "IS  2013–2020")
    oos_m  = calc_metrics(oos_df["port_ret"], "OOS 2021–2026")
    spy_is = calc_metrics(spy_ret[(spy_ret.index >= IS_START) & (spy_ret.index <= IS_END)], "SPY IS")
    spy_oos= calc_metrics(spy_ret[(spy_ret.index >= OOS_START)& (spy_ret.index <= OOS_END)],"SPY OOS")

    # Correlation with SPY OOS
    oos_ret_s = oos_df["port_ret"]
    spy_oos_s = spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)]
    aligned = oos_ret_s.align(spy_oos_s, join="inner")
    corr_spy = aligned[0].corr(aligned[1]) if len(aligned[0]) > 5 else float("nan")

    # Correlation with H181 OOS (load from results)
    h181_result = RESULT_DIR / "h181_industry_reversal.txt"
    corr_h181 = float("nan")
    # Attempt to load H181 monthly returns from cache for cross-correlation
    h181_cache = CACHE_DIR / "h188_h181_oos_ret.parquet"
    if not h181_cache.exists():
        # Recompute H181 to get monthly returns series
        from pathlib import Path
        try:
            h181_module_path = Path(__file__).parent / "run_h181.py"
            if h181_module_path.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("run_h181", h181_module_path)
                h181_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(h181_mod)
                h181_prices = h181_mod.load_monthly_closes()
                h181_port   = h181_mod.run_backtest(h181_prices)
                h181_oos    = h181_port[(h181_port.index >= OOS_START) & (h181_port.index <= OOS_END)]
                pd.DataFrame({"ret": h181_oos["port_ret"]}).to_parquet(h181_cache)
                corr_h181 = oos_ret_s.align(h181_oos["port_ret"], join="inner")[0].corr(
                    oos_ret_s.align(h181_oos["port_ret"], join="inner")[1]
                )
        except Exception as e:
            print(f"  (H181 corr skipped: {e})")
    else:
        h181_oos_ret = pd.read_parquet(h181_cache)["ret"]
        aligned_h181 = oos_ret_s.align(h181_oos_ret, join="inner")
        corr_h181 = aligned_h181[0].corr(aligned_h181[1]) if len(aligned_h181[0]) > 5 else float("nan")

    print(f"\n  {'Metric':<16} {'IS':>10} {'OOS':>10} {'SPY_IS':>10} {'SPY_OOS':>10}")
    print("  " + "-" * 58)
    for k in ["cumul", "cagr_pct", "sharpe", "max_dd_pct", "neg_years"]:
        row = f"  {k:<16}"
        for m in [is_m, oos_m, spy_is, spy_oos]:
            v = m.get(k, "—")
            row += f" {v:>10}"
        print(row)

    print(f"\n  Corr(H188, SPY) OOS:  {corr_spy:.3f}")
    print(f"  Corr(H188, H181) OOS: {corr_h181:.3f}  (H181 = industry reversal — opposite signal?)")

    oos_sharpe = oos_m.get("sharpe", 0)
    oos_cumul  = oos_m.get("cumul", 0)
    confirmed  = (oos_sharpe > 0.5) and (oos_cumul > 1.3)

    print("\n[5/5] Confirmation check…")
    print(f"  OOS Sharpe: {oos_sharpe:.3f}  (threshold: > 0.5)  {'✓' if oos_sharpe > 0.5 else '✗'}")
    print(f"  OOS Cumul:  {oos_cumul:.3f}×  (threshold: > 1.3×) {'✓' if oos_cumul > 1.3 else '✗'}")
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    print("\n  Recent signal picks (last 6 months):")
    for _, row in port_df.tail(6).iterrows():
        print(f"    {row.name.date()}: {row['long_tickers']}  ret={row['port_ret']*100:+.2f}%  "
              f"avg_prox={row['avg_proximity']:.3f}")

    out_lines = [
        "H188 — 52-Week High Proximity Momentum",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Source: George & Hwang (2004) JF 59(5)",
        f"Universe: {len(available)}/30 large-cap S&P 500 stocks",
        f"Signal: proximity = P_t / max(P_{{t-252d:t-1}}); long top-{QUINTILE_N}",
        f"IS: 2013–2020  |  OOS: 2021–2026",
        "",
        f"IS  months: {is_m.get('n_months','?')}  Cumul={is_m.get('cumul','?')}×  "
        f"CAGR={is_m.get('cagr_pct','?')}%  Sharpe={is_m.get('sharpe','?')}  "
        f"MaxDD={is_m.get('max_dd_pct','?')}%  NegYrs={is_m.get('neg_years','?')}",
        f"OOS months: {oos_m.get('n_months','?')}  Cumul={oos_m.get('cumul','?')}×  "
        f"CAGR={oos_m.get('cagr_pct','?')}%  Sharpe={oos_m.get('sharpe','?')}  "
        f"MaxDD={oos_m.get('max_dd_pct','?')}%  NegYrs={oos_m.get('neg_years','?')}",
        "",
        f"SPY IS:  Cumul={spy_is.get('cumul','?')}×  Sharpe={spy_is.get('sharpe','?')}",
        f"SPY OOS: Cumul={spy_oos.get('cumul','?')}×  Sharpe={spy_oos.get('sharpe','?')}",
        "",
        f"Corr(H188, SPY) OOS:  {corr_spy:.3f}",
        f"Corr(H188, H181) OOS: {corr_h181:.3f}",
        "",
        f"Confirm: OOS Sharpe > 0.5  → {oos_sharpe:.3f} ({'PASS' if oos_sharpe > 0.5 else 'FAIL'})",
        f"Confirm: OOS Cumul > 1.3×  → {oos_cumul:.3f}× ({'PASS' if oos_cumul > 1.3 else 'FAIL'})",
        "",
        f"VERDICT: {verdict}",
    ]
    result_path = RESULT_DIR / "h188_52wk_high_proximity.txt"
    result_path.write_text("\n".join(out_lines))
    print(f"\n  Results saved: {result_path.name}")
    print("=" * 64)


if __name__ == "__main__":
    main()
