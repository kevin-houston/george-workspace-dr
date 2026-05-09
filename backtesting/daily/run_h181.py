"""
H181 — Industry-Adjusted Short-Term Reversal
=============================================
SSRN:6630998 (Stosik & Zaremba): 0.53%/month globally, Sharpe 0.74
Signal: REV^IN_i = R_i(t) - R̄_industry(t)
  where R̄_industry = equal-weight avg return of same-GICS-sector stocks

Strategy:
  - Universe: 30 large-cap S&P 500 stocks (same as H163/H174 PEAD universe)
  - Signal: prior month return minus equal-weight industry average
  - Portfolio: long bottom quintile (most negative adj-reversal = reversal candidates)
  - Rebalance: monthly
  - IS: 2013–2020, OOS: 2021–2026
  - Confirm: OOS Sharpe > 0.5, OOS cumul > 1.3×
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"

# 30-ticker GICS sector map (from wiki/trading/data-sources/sector-classification.md)
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

DATA_START = "2012-01-01"   # extra year to compute first-month return
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")

QUINTILE_N = 6   # ~bottom quintile of 30 stocks
SPY_START  = "2012-01-01"


# ── data loading ────────────────────────────────────────────────────────────

def load_monthly_closes() -> pd.DataFrame:
    """Return DataFrame: index=month-end date, columns=tickers, values=adj close."""
    all_closes = {}

    to_download = []
    for ticker in UNIVERSE:
        # Try h161 daily cache first (covers 2007–2026)
        p161 = CACHE_DIR / f"h161_{ticker}_close_{DATA_START[:4][:4]}_{DATA_END[:4]}.parquet"
        p161_full = CACHE_DIR / f"h161_{ticker}_close_2007-01-01_2026-04-30.parquet"

        h181_cache = CACHE_DIR / f"h181_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"

        if h181_cache.exists():
            df = pd.read_parquet(h181_cache)
            all_closes[ticker] = df["close"]
            continue

        if p161_full.exists():
            df = pd.read_parquet(p161_full)
            df.index = pd.to_datetime(df.index)
            close_col = [c for c in df.columns if c.lower() in ("close", "adj close", "adjclose")]
            if close_col:
                s = df[close_col[0]].dropna()
            else:
                s = df.iloc[:, 0].dropna()
            # Resample to month-end
            monthly = s.resample("ME").last()
            monthly = monthly[monthly.index >= DATA_START]
            out = pd.DataFrame({"close": monthly})
            out.to_parquet(h181_cache)
            all_closes[ticker] = monthly
            continue

        to_download.append(ticker)

    if to_download:
        print(f"  Downloading {len(to_download)} tickers from yfinance: {to_download}")
        raw = yf.download(to_download, start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        close = raw["Close"] if "Close" in raw.columns else raw.xs("Close", axis=1, level=0)
        if isinstance(close, pd.Series):
            # single ticker
            ticker = to_download[0]
            monthly = close.resample("ME").last().dropna()
            h181_cache = CACHE_DIR / f"h181_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
            pd.DataFrame({"close": monthly}).to_parquet(h181_cache)
            all_closes[ticker] = monthly
        else:
            for ticker in to_download:
                if ticker in close.columns:
                    s = close[ticker].dropna()
                    monthly = s.resample("ME").last()
                    h181_cache = CACHE_DIR / f"h181_{ticker}_monthly_{DATA_START}_{DATA_END}.parquet"
                    pd.DataFrame({"close": monthly}).to_parquet(h181_cache)
                    all_closes[ticker] = monthly

    df = pd.DataFrame(all_closes)
    df.index = pd.to_datetime(df.index)
    return df.sort_index()


def load_spy_monthly() -> pd.Series:
    """Load SPY monthly returns as benchmark."""
    spy_cache = CACHE_DIR / f"h181_SPY_monthly_{DATA_START}_{DATA_END}.parquet"
    if spy_cache.exists():
        return pd.read_parquet(spy_cache)["close"]
    raw = yf.download("SPY", start=DATA_START, end=DATA_END,
                      auto_adjust=True, progress=False)
    # Handle MultiIndex columns from newer yfinance
    if isinstance(raw.columns, pd.MultiIndex):
        raw = raw.xs("SPY", axis=1, level=1)
    close_col = "Close" if "Close" in raw.columns else raw.columns[0]
    close = raw[close_col].resample("ME").last().dropna()
    close.name = "close"
    pd.DataFrame({"close": close}).to_parquet(spy_cache)
    return close


# ── signal construction ──────────────────────────────────────────────────────

def industry_adjusted_reversal(monthly_returns: pd.Series, sector_map: dict) -> pd.Series:
    """
    monthly_returns: pd.Series, index=ticker, values=last month's return
    Returns: industry-adjusted return (stock return - equal-weight sector mean)
    Sort ascending → long bottom = most negative = strongest reversal candidates
    """
    sectors = pd.Series(sector_map)
    common = monthly_returns.index.intersection(sectors.index)
    r = monthly_returns[common]
    s = sectors[common]
    industry_means = r.groupby(s).transform("mean")
    return r - industry_means


# ── portfolio simulation ──────────────────────────────────────────────────────

def run_backtest(prices: pd.DataFrame) -> pd.DataFrame:
    """
    Monthly rebalance. Each month:
      1. Compute prior-month return for each stock
      2. Compute industry-adjusted reversal
      3. Long bottom quintile (QUINTILE_N most negative adj-reversal)
      4. Record equal-weight portfolio return that month
    Returns: DataFrame with columns [date, port_ret, n_held, signal_stocks]
    """
    months = prices.index
    records = []

    for i in range(1, len(months)):
        rebal_date = months[i - 1]   # end of prior month (signal computed)
        hold_date  = months[i]       # end of this month (return realized)

        # Prior-month returns (signal period = month i-1)
        if i < 2:
            # Need at least 2 months of data for first return
            continue
        prior_close = prices.loc[months[i - 2]]
        signal_close = prices.loc[months[i - 1]]
        hold_close   = prices.loc[months[i]]

        # Compute prior-month return for each stock
        prior_returns = {}
        current_returns = {}
        for ticker in UNIVERSE:
            if ticker in prior_close.index and ticker in signal_close.index:
                p0 = prior_close[ticker]
                p1 = signal_close[ticker]
                p2 = hold_close.get(ticker, np.nan)
                if pd.notna(p0) and pd.notna(p1) and p0 > 0:
                    prior_returns[ticker] = (p1 - p0) / p0
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    current_returns[ticker] = (p2 - p1) / p1

        if len(prior_returns) < QUINTILE_N * 2:
            continue

        # Compute industry-adjusted reversal signal
        prior_ret_series = pd.Series(prior_returns)
        adj_rev = industry_adjusted_reversal(prior_ret_series, UNIVERSE_SECTORS)

        # Long bottom quintile (most negative adj-reversal)
        adj_rev_sorted = adj_rev.sort_values()
        long_tickers = adj_rev_sorted.head(QUINTILE_N).index.tolist()

        # Equal-weight portfolio return
        port_returns = [current_returns[t] for t in long_tickers if t in current_returns]
        if not port_returns:
            continue

        port_ret = np.mean(port_returns)

        records.append({
            "date": hold_date,
            "port_ret": port_ret,
            "n_held": len(port_returns),
            "signal_stocks": ",".join(long_tickers),
            "avg_adj_rev_signal": adj_rev_sorted.head(QUINTILE_N).mean(),
        })

    return pd.DataFrame(records).set_index("date")


# ── performance metrics ───────────────────────────────────────────────────────

def calc_metrics(returns: pd.Series, label: str = "") -> dict:
    """Calculate annual Sharpe, cumulative return, MaxDD, CAGR, win rate."""
    if len(returns) == 0:
        return {}

    cum = (1 + returns).cumprod()
    total_ret = cum.iloc[-1]
    n_years = len(returns) / 12.0

    cagr = total_ret ** (1 / n_years) - 1 if n_years > 0 else 0.0
    sharpe = (returns.mean() / returns.std() * np.sqrt(12)) if returns.std() > 0 else 0.0

    # Max drawdown
    roll_max = cum.cummax()
    dd = (cum - roll_max) / roll_max
    max_dd = dd.min()

    neg_years = sum(
        1 for yr, g in returns.groupby(returns.index.year)
        if g.sum() < 0
    )

    return {
        "label": label,
        "n_months": len(returns),
        "cumul": round(total_ret, 4),
        "cagr_pct": round(cagr * 100, 2),
        "sharpe": round(sharpe, 3),
        "max_dd_pct": round(max_dd * 100, 2),
        "neg_years": neg_years,
        "mean_monthly_pct": round(returns.mean() * 100, 3),
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 64)
    print("  H181 — Industry-Adjusted Short-Term Reversal")
    print("  SSRN:6630998 (Stosik & Zaremba)")
    print("=" * 64)

    print(f"\n[1/5] Loading monthly close prices for {len(UNIVERSE)} tickers…")
    prices = load_monthly_closes()
    available = [t for t in UNIVERSE if t in prices.columns and prices[t].notna().sum() > 24]
    print(f"  Price data: {len(available)}/{len(UNIVERSE)} tickers, "
          f"{prices.index[0].date()} → {prices.index[-1].date()}")
    missing = [t for t in UNIVERSE if t not in available]
    if missing:
        print(f"  Missing/sparse: {missing}")

    # Sector distribution of available tickers
    sector_counts = {}
    for t in available:
        s = UNIVERSE_SECTORS.get(t, "Unknown")
        sector_counts[s] = sector_counts.get(s, 0) + 1
    print(f"  Sectors: {sector_counts}")

    print("\n[2/5] Loading SPY benchmark…")
    spy_close = load_spy_monthly()
    spy_ret = spy_close.pct_change().dropna()

    print("\n[3/5] Running monthly backtest (2013–2026)…")
    # Only use available tickers
    prices_avail = prices[available]
    port_df = run_backtest(prices_avail)
    print(f"  Total monthly observations: {len(port_df)}")
    print(f"  Avg stocks held/month: {port_df['n_held'].mean():.1f}")

    # Split IS / OOS
    is_df  = port_df[(port_df.index >= IS_START)  & (port_df.index <= IS_END)]
    oos_df = port_df[(port_df.index >= OOS_START) & (port_df.index <= OOS_END)]

    print(f"  IS months: {len(is_df)}  |  OOS months: {len(oos_df)}")

    print("\n[4/5] Computing performance metrics…")
    is_ret  = is_df["port_ret"]
    oos_ret = oos_df["port_ret"]

    is_metrics  = calc_metrics(is_ret,  "IS  2013-2020")
    oos_metrics = calc_metrics(oos_ret, "OOS 2021-2026")

    # Benchmark SPY in same windows
    spy_is  = spy_ret[(spy_ret.index >= IS_START)  & (spy_ret.index <= IS_END)]
    spy_oos = spy_ret[(spy_ret.index >= OOS_START) & (spy_ret.index <= OOS_END)]
    spy_is_m  = calc_metrics(spy_is,  "SPY IS")
    spy_oos_m = calc_metrics(spy_oos, "SPY OOS")

    # Correlation with SPY (OOS)
    oos_aligned = oos_ret.align(spy_oos, join="inner")
    corr_spy = oos_aligned[0].corr(oos_aligned[1]) if len(oos_aligned[0]) > 5 else float("nan")

    print(f"\n  {'Metric':<18} {'IS':>12} {'OOS':>12} {'SPY_IS':>12} {'SPY_OOS':>12}")
    print("  " + "-" * 68)
    for k in ["cumul", "cagr_pct", "sharpe", "max_dd_pct", "neg_years"]:
        row = f"  {k:<18}"
        for m in [is_metrics, oos_metrics, spy_is_m, spy_oos_m]:
            v = m.get(k, "—")
            row += f" {v:>12}"
        print(row)
    print(f"\n  Corr(Portfolio, SPY) OOS: {corr_spy:.3f}")

    # Confirm criteria check
    oos_sharpe = oos_metrics.get("sharpe", 0)
    oos_cumul  = oos_metrics.get("cumul", 0)
    confirmed  = (oos_sharpe > 0.5) and (oos_cumul > 1.3)

    print("\n[5/5] Confirmation check…")
    print(f"  OOS Sharpe: {oos_sharpe:.3f}  (threshold: > 0.5)  {'✓' if oos_sharpe > 0.5 else '✗'}")
    print(f"  OOS Cumul:  {oos_cumul:.3f}×  (threshold: > 1.3×) {'✓' if oos_cumul > 1.3 else '✗'}")
    verdict = "CONFIRMED" if confirmed else "NOT CONFIRMED"
    print(f"\n  VERDICT: {verdict}")

    # Top monthly signal stocks
    print("\n  Sample of recent signal picks (last 6 months):")
    for _, row in port_df.tail(6).iterrows():
        print(f"    {row.name.date()}: {row['signal_stocks']}  "
              f"ret={row['port_ret']*100:+.2f}%")

    # ── save results ──────────────────────────────────────────────────────────
    out_lines = [
        "H181 — Industry-Adjusted Short-Term Reversal",
        f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Universe: {len(available)}/30 tickers  |  Sectors: {len(sector_counts)} GICS",
        f"Signal: REV^IN_i = R_i(t) - R_bar_industry(t)  |  Monthly rebalance",
        f"Portfolio: Long bottom-quintile (n={QUINTILE_N} most negative adj-reversal)",
        f"IS: 2013–2020  |  OOS: 2021–2026",
        f"Source: SSRN:6630998 (Stosik & Zaremba)",
        "",
        f"IS  months: {is_metrics['n_months']}  |  "
        f"Cumul={is_metrics['cumul']}×  CAGR={is_metrics['cagr_pct']}%  "
        f"Sharpe={is_metrics['sharpe']}  MaxDD={is_metrics['max_dd_pct']}%  "
        f"NegYrs={is_metrics['neg_years']}",
        f"OOS months: {oos_metrics['n_months']}  |  "
        f"Cumul={oos_metrics['cumul']}×  CAGR={oos_metrics['cagr_pct']}%  "
        f"Sharpe={oos_metrics['sharpe']}  MaxDD={oos_metrics['max_dd_pct']}%  "
        f"NegYrs={oos_metrics['neg_years']}",
        "",
        f"SPY IS:  Cumul={spy_is_m['cumul']}×  Sharpe={spy_is_m['sharpe']}",
        f"SPY OOS: Cumul={spy_oos_m['cumul']}×  Sharpe={spy_oos_m['sharpe']}",
        "",
        f"Corr(Portfolio, SPY) OOS: {corr_spy:.3f}",
        "",
        f"Confirm criteria: OOS Sharpe > 0.5 -> {oos_sharpe:.3f} "
        f"({'PASS' if oos_sharpe > 0.5 else 'FAIL'})",
        f"Confirm criteria: OOS Cumul > 1.3x -> {oos_cumul:.3f}x "
        f"({'PASS' if oos_cumul > 1.3 else 'FAIL'})",
        "",
        f"VERDICT: {verdict}",
    ]

    result_path = RESULT_DIR / "h181_industry_reversal.txt"
    result_path.write_text("\n".join(out_lines))
    print(f"\n  Results saved: {result_path.name}")
    print("=" * 64)


if __name__ == "__main__":
    main()
