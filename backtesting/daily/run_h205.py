"""
H205 — TOM Calendar Overlay on H192-D BAB
==========================================
Tests whether restricting H192-D (sector-neutral BAB) positions to the
Turn-of-Month window (last 2 + first 2 trading days) improves risk-adjusted
returns by concentrating BAB exposure in the calendar window where equity
premia are historically concentrated.

Design:
  • Stock selection: sector-neutral BAB signal, same as H192-D (Sharpe 1.367 OOS)
  • Monthly rebalance: re-rank sector-neutral betas at each month-end → long 6
  • Timing: hold the BAB portfolio ONLY on TOM days; hold BIL (0%) otherwise
  • TOM window: last 2 + first 2 trading days of each month (H201 confirmed window)
  • ~19% of trading days invested; BIL the remaining ~81%

Hypothesis: BAB alpha is concentrated in the TOM window. Restricting exposure
to TOM days reduces drawdown while preserving most of the BAB return, lifting
the Sharpe ratio above H192-D's 1.367 OOS.

Baseline comparisons:
  H192-D (sector-neutral BAB, always-invested):  OOS Sharpe 1.367  MaxDD -15.4%
  H201   (TOM on SPY, 19% invested):             OOS Sharpe 0.740  MaxDD  -9.3%
  SPY buy-and-hold:                              OOS Sharpe 0.789  MaxDD -33.7%

Universe: 30 large-cap S&P 500 stocks (same as H181/H192)
IS: 2013–2020, OOS: 2021–2026
Confirm: OOS Sharpe > 1.5 (beat H192-D meaningfully); MaxDD < H192-D's -15.4%

Risk flags (from dream cycle):
  1. BAB in Asia is regime-conditional (works mainly in downturns). Add SPY-200MA
     regime split diagnostic to verify H205 is not regime-dependent on US data.
  2. FRL 2025 paper claims TOM disappears post-2001. H201 contradicts on SPY/ETF
     data. Run H205 with full 2013–2026 period to check.
"""

import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import json

import numpy as np
import pandas as pd
import yfinance as yf

WORKSPACE  = Path(__file__).resolve().parent.parent.parent
CACHE_DIR  = WORKSPACE / "backtesting" / "cache"
RESULT_DIR = WORKSPACE / "backtesting" / "results"
RESULT_DIR.mkdir(parents=True, exist_ok=True)

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
SPY      = "SPY"

DATA_START = "2012-01-01"
DATA_END   = "2026-04-30"
IS_START   = pd.Timestamp("2013-01-01")
IS_END     = pd.Timestamp("2020-12-31")
OOS_START  = pd.Timestamp("2021-01-01")
OOS_END    = pd.Timestamp("2026-04-30")
N_LONG     = 6   # long bottom-6 lowest-beta stocks per sector-neutral ranking
TOM_BEFORE = 2   # last N trading days of month
TOM_AFTER  = 2   # first N trading days of month


# ─── Data loading ─────────────────────────────────────────────────────────────

def load_prices() -> tuple[pd.DataFrame, pd.Series]:
    cache = CACHE_DIR / f"h188_daily_{DATA_START}_{DATA_END}.parquet"
    if cache.exists():
        print("  Loading daily prices from H188/H192 cache…")
        df = pd.read_parquet(cache)
    else:
        print(f"  Downloading {len(UNIVERSE)} tickers + SPY from yfinance…")
        raw = yf.download(UNIVERSE + [SPY], start=DATA_START, end=DATA_END,
                          auto_adjust=True, progress=False)
        df = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        df.dropna(how="all", axis=0).to_parquet(cache)
        df = pd.read_parquet(cache)

    if SPY not in df.columns:
        spy_raw = yf.download(SPY, start=DATA_START, end=DATA_END,
                              auto_adjust=True, progress=False)
        spy_px = spy_raw["Close"] if "Close" in spy_raw.columns else spy_raw.squeeze()
        df[SPY] = spy_px.reindex(df.index, method="ffill")

    return df[UNIVERSE].copy(), df[SPY].copy()


# ─── Beta computation ──────────────────────────────────────────────────────────

def rolling_beta(stock_rets: pd.Series, spy_rets: pd.Series, window: int = 252) -> float:
    x = spy_rets.tail(window).values
    y = stock_rets.tail(window).values
    mask = np.isfinite(x) & np.isfinite(y)
    if mask.sum() < window // 3:
        return np.nan
    xm, ym = x[mask].mean(), y[mask].mean()
    cov = np.mean((x[mask] - xm) * (y[mask] - ym))
    var = np.mean((x[mask] - xm) ** 2)
    return cov / var if var > 1e-10 else np.nan


def sector_neutral_beta_rank(daily_rets: pd.DataFrame, spy_rets: pd.Series,
                              rebal_date: pd.Timestamp) -> list[str]:
    """
    Compute sector-neutral beta ranks as of rebal_date.
    Returns list of N_LONG ticker symbols (lowest sector-adjusted beta rank).
    """
    hist_rets     = daily_rets[daily_rets.index <= rebal_date]
    spy_hist_rets = spy_rets[spy_rets.index <= rebal_date]
    if len(hist_rets) < 130:
        return []

    spy_ser = spy_hist_rets.tail(252)
    betas = {}
    for t in UNIVERSE:
        if t not in hist_rets.columns:
            continue
        b = rolling_beta(hist_rets[t], spy_ser, window=252)
        if pd.notna(b):
            betas[t] = b

    if len(betas) < N_LONG * 2:
        return []

    beta_series = pd.Series(betas)
    sectors     = pd.Series(UNIVERSE_SECTORS)
    common      = beta_series.index.intersection(sectors.index)
    df_tmp = pd.DataFrame({
        "beta":   beta_series[common],
        "sector": sectors[common],
    })
    df_tmp["rank_in_sector"] = df_tmp.groupby("sector")["beta"].rank(ascending=True)
    # Long bottom N_LONG sector-neutral ranks
    return df_tmp["rank_in_sector"].nsmallest(N_LONG).index.tolist()


# ─── TOM mask ─────────────────────────────────────────────────────────────────

def build_tom_mask(trading_days: pd.DatetimeIndex,
                   before: int = TOM_BEFORE,
                   after:  int = TOM_AFTER) -> pd.Series:
    """True on TOM window days (last `before` + first `after` trading days of month)."""
    mask = pd.Series(False, index=trading_days)
    monthly_ends = (pd.Series(trading_days)
                    .groupby([trading_days.year, trading_days.month])
                    .last().values)
    for month_end in monthly_ends:
        end_loc = trading_days.get_loc(month_end)
        start   = max(0, end_loc - before + 1)
        stop    = min(len(trading_days) - 1, end_loc + after)
        mask.iloc[start : stop + 1] = True
    return mask


# ─── H205 strategy ────────────────────────────────────────────────────────────

def run_h205(daily_prices: pd.DataFrame, spy_prices: pd.Series,
             label: str = "H205") -> pd.Series:
    """
    TOM-gated sector-neutral BAB strategy.
    Returns daily return series (0 on non-TOM days, BAB portfolio return on TOM days).
    """
    trading_days = daily_prices.index
    daily_rets   = daily_prices.pct_change()
    spy_rets     = spy_prices.pct_change()
    tom_mask     = build_tom_mask(trading_days)

    # Pre-compute month-end rebalance dates
    month_ends = daily_prices.resample("ME").last().index

    # Map each month-end → BAB portfolio (list of tickers)
    print("  Pre-computing sector-neutral BAB portfolios at each month-end…")
    portfolio_map: dict[pd.Timestamp, list[str]] = {}
    for me in month_ends:
        tickers = sector_neutral_beta_rank(daily_rets, spy_rets, me)
        if tickers:
            portfolio_map[me] = tickers

    if not portfolio_map:
        return pd.Series(dtype=float)

    sorted_ends = sorted(portfolio_map.keys())

    # For each trading day: find the most recent rebalance date, get portfolio
    def get_current_portfolio(day: pd.Timestamp) -> list[str]:
        # Most recent month-end on or before `day`
        valid = [me for me in sorted_ends if me <= day]
        if not valid:
            return []
        return portfolio_map[valid[-1]]

    # Build daily return series
    result_rets, result_dates = [], []
    for day in trading_days:
        if day < IS_START:
            continue
        portfolio = get_current_portfolio(day)
        if not portfolio:
            continue

        is_tom = bool(tom_mask.get(day, False))
        if not is_tom:
            # BIL — approximately 0 daily return (or use T-bill rate)
            result_rets.append(0.0)
            result_dates.append(day)
        else:
            # BAB portfolio return for this day
            day_rets = []
            for t in portfolio:
                if t in daily_rets.columns:
                    r = daily_rets.loc[day, t]
                    if pd.notna(r):
                        day_rets.append(r)
            if day_rets:
                result_rets.append(np.mean(day_rets))
                result_dates.append(day)

    return pd.Series(result_rets, index=result_dates, name=label)


def resample_to_monthly(daily: pd.Series) -> pd.Series:
    """Convert daily returns to monthly compound returns."""
    return daily.resample("ME").apply(lambda x: (1 + x).prod() - 1)


# ─── Metrics ──────────────────────────────────────────────────────────────────

def calc_metrics(returns: pd.Series, label: str = "", freq: str = "monthly") -> dict:
    if len(returns) == 0:
        return {"label": label, "cumul": 0, "sharpe": 0, "max_dd_pct": 0, "neg_years": 0}
    cum   = (1 + returns).cumprod()
    n_yrs = len(returns) / (252.0 if freq == "daily" else 12.0)
    scale = np.sqrt(252 if freq == "daily" else 12)
    cagr  = cum.iloc[-1] ** (1 / n_yrs) - 1 if n_yrs > 0 else 0.0
    sharpe = returns.mean() / returns.std() * scale if returns.std() > 0 else 0.0
    dd     = (cum / cum.cummax()) - 1

    if freq == "daily":
        annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)
    else:
        annual = returns.resample("YE").apply(lambda x: (1 + x).prod() - 1)

    return {
        "label":      label,
        "n_periods":  len(returns),
        "cumul":      round(float(cum.iloc[-1]), 4),
        "cagr_pct":   round(cagr * 100, 2),
        "sharpe":     round(sharpe, 3),
        "max_dd_pct": round(float(dd.min()) * 100, 2),
        "neg_years":  int(annual.lt(0).sum()),
    }


def print_metrics(m: dict, window: str = "") -> None:
    tag = f"[{window}]" if window else ""
    print(f"    {tag} {m['label']:<45}  Sharpe={m['sharpe']:.3f}  "
          f"Cumul={m['cumul']:.3f}×  CAGR={m['cagr_pct']:.1f}%  "
          f"MaxDD={m['max_dd_pct']:.1f}%  NegYrs={m['neg_years']}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 76)
    print("  H205 — TOM Calendar Overlay on H192-D BAB")
    print("=" * 76)

    print("\n[1] Loading prices…")
    prices, spy_px = load_prices()
    print(f"    {prices.shape[1]} tickers, {len(prices)} trading days")

    daily_rets_spy = spy_px.pct_change().dropna()
    spy_monthly    = spy_px.resample("ME").last().pct_change().dropna()

    # ── SPY benchmarks ──────────────────────────────────────────────────────
    spy_is  = spy_monthly[(spy_monthly.index >= IS_START)  & (spy_monthly.index <= IS_END)]
    spy_oos = spy_monthly[(spy_monthly.index >= OOS_START) & (spy_monthly.index <= OOS_END)]

    print("\n[2] SPY benchmarks:")
    print_metrics(calc_metrics(spy_is,  "SPY buy-and-hold", "monthly"), "IS ")
    print_metrics(calc_metrics(spy_oos, "SPY buy-and-hold", "monthly"), "OOS")

    # ── H205: TOM-gated sector-neutral BAB ─────────────────────────────────
    print("\n[3] Running H205 (TOM overlay on sector-neutral BAB)…")
    print("    [This computes betas at every month-end — may take 2-3 minutes]")
    h205_daily = run_h205(prices, spy_px, label="H205 TOM-BAB")
    if h205_daily.empty:
        print("    ERROR: No results generated. Check data.")
        return

    h205_monthly = resample_to_monthly(h205_daily)

    h205_is  = h205_monthly[(h205_monthly.index >= IS_START)  & (h205_monthly.index <= IS_END)]
    h205_oos = h205_monthly[(h205_monthly.index >= OOS_START) & (h205_monthly.index <= OOS_END)]

    print("\n[4] H205 Results:")
    m_is  = calc_metrics(h205_is,  "H205 IS  2013–2020")
    m_oos = calc_metrics(h205_oos, "H205 OOS 2021–2026")
    print_metrics(m_is,  "IS ")
    print_metrics(m_oos, "OOS")

    # ── Baseline: H192-D (always-invested sector-neutral BAB, monthly) ──────
    print("\n[5] H192-D baseline (sector-neutral BAB, always-invested, monthly rebal)…")
    # Re-run H192-D monthly for clean comparison on same data
    h192d_rets, h192d_dates = [], []
    daily_rets   = prices.pct_change()
    spy_daily    = spy_px.pct_change()
    monthly_px   = prices.resample("ME").last()
    month_ends_m = monthly_px.index
    sectors_s    = pd.Series(UNIVERSE_SECTORS)

    for i, hold_date in enumerate(month_ends_m[1:], 1):
        rebal_date    = month_ends_m[i - 1]
        hist_rets     = daily_rets[daily_rets.index <= rebal_date]
        spy_hist_rets = spy_daily[spy_daily.index <= rebal_date]
        if len(hist_rets) < 130:
            continue
        spy_ser = spy_hist_rets.tail(252)
        betas = {}
        for t in UNIVERSE:
            if t not in hist_rets.columns:
                continue
            b = rolling_beta(hist_rets[t], spy_ser, window=252)
            if pd.notna(b):
                betas[t] = b
        if len(betas) < N_LONG * 2:
            continue
        beta_series = pd.Series(betas)
        common = beta_series.index.intersection(sectors_s.index)
        df_tmp = pd.DataFrame({"beta": beta_series[common], "sector": sectors_s[common]})
        df_tmp["rank_in_sector"] = df_tmp.groupby("sector")["beta"].rank(ascending=True)
        long_tickers = df_tmp["rank_in_sector"].nsmallest(N_LONG).index.tolist()
        port_rets = []
        for t in long_tickers:
            if t in monthly_px.columns:
                p1 = monthly_px.iloc[i - 1].get(t, np.nan)
                p2 = monthly_px.iloc[i].get(t, np.nan)
                if pd.notna(p1) and pd.notna(p2) and p1 > 0:
                    port_rets.append((p2 - p1) / p1)
        if port_rets:
            h192d_rets.append(np.mean(port_rets))
            h192d_dates.append(hold_date)

    h192d = pd.Series(h192d_rets, index=h192d_dates, name="H192-D")
    h192d_is  = h192d[(h192d.index >= IS_START)  & (h192d.index <= IS_END)]
    h192d_oos = h192d[(h192d.index >= OOS_START) & (h192d.index <= OOS_END)]

    print_metrics(calc_metrics(h192d_is,  "H192-D IS  2013–2020"), "IS ")
    print_metrics(calc_metrics(h192d_oos, "H192-D OOS 2021–2026"), "OOS")

    # ── Comparison summary ──────────────────────────────────────────────────
    print("\n[6] Comparison (OOS 2021–2026):")
    print(f"    {'Strategy':<40} {'Sharpe':>8} {'CAGR':>8} {'MaxDD':>8} {'NegYrs':>8}")
    print(f"    {'-'*40} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    for label, rets in [
        ("H205 TOM-BAB (19% invested)", h205_oos),
        ("H192-D sector-neutral BAB (100%)", h192d_oos),
        ("SPY buy-and-hold", spy_oos),
    ]:
        m = calc_metrics(rets, label)
        print(f"    {m['label']:<40} {m['sharpe']:>8.3f} {m['cagr_pct']:>7.1f}% "
              f"{m['max_dd_pct']:>7.1f}% {m['neg_years']:>8}")

    # ── Regime analysis (SPY above/below 200-day MA) ────────────────────────
    print("\n[7] Regime diagnostic (H205 OOS performance in bull vs bear)…")
    sma200  = spy_px.rolling(200).mean()
    bull_days = spy_px.index[spy_px > sma200]
    bear_days = spy_px.index[spy_px <= sma200]

    h205_bull = h205_daily[h205_daily.index.isin(bull_days)]
    h205_bear = h205_daily[h205_daily.index.isin(bear_days)]
    h205_bull_oos = h205_bull[(h205_bull.index >= OOS_START) & (h205_bull.index <= OOS_END)]
    h205_bear_oos = h205_bear[(h205_bear.index >= OOS_START) & (h205_bear.index <= OOS_END)]

    if len(h205_bull_oos) > 20:
        bull_days_count = len(h205_bull_oos)
        bull_ann_ret = (1 + h205_bull_oos.mean()) ** 252 - 1
        print(f"    Bull regime (SPY>200MA): {bull_days_count} TOM days, "
              f"ann ret={bull_ann_ret*100:.1f}%")
    if len(h205_bear_oos) > 5:
        bear_days_count = len(h205_bear_oos)
        bear_ann_ret = (1 + h205_bear_oos.mean()) ** 252 - 1
        print(f"    Bear regime (SPY≤200MA): {bear_days_count} TOM days, "
              f"ann ret={bear_ann_ret*100:.1f}%")
    else:
        print(f"    Bear regime: only {len(h205_bear_oos)} TOM days in OOS — too few to characterize")

    # ── Correlation with H192-D ─────────────────────────────────────────────
    print("\n[8] Correlation analysis (OOS monthly)…")
    common_idx = h205_oos.index.intersection(h192d_oos.index)
    if len(common_idx) > 12:
        corr_h192d = h205_oos.loc[common_idx].corr(h192d_oos.loc[common_idx])
        print(f"    Corr(H205, H192-D) OOS = {corr_h192d:.3f}")
        spy_common = spy_oos.loc[spy_oos.index.isin(common_idx)]
        if len(spy_common) > 12:
            corr_spy = h205_oos.loc[common_idx].corr(spy_oos.loc[spy_common.index])
            print(f"    Corr(H205, SPY)    OOS = {corr_spy:.3f}")

    # ── Confirmation verdict ────────────────────────────────────────────────
    print("\n" + "=" * 76)
    oos_sharpe = m_oos["sharpe"]
    oos_maxdd  = m_oos["max_dd_pct"]
    h192d_sharpe_oos = calc_metrics(h192d_oos, "H192-D OOS")["sharpe"]

    confirm_threshold = 1.5
    if oos_sharpe >= confirm_threshold:
        verdict = "CONFIRMED"
        note    = f"OOS Sharpe {oos_sharpe:.3f} ≥ threshold {confirm_threshold}"
    elif oos_sharpe >= h192d_sharpe_oos:
        verdict = "PARTIAL — beats H192-D but below 1.5 threshold"
        note    = f"OOS Sharpe {oos_sharpe:.3f} > H192-D {h192d_sharpe_oos:.3f}"
    else:
        verdict = "NOT CONFIRMED"
        note    = f"OOS Sharpe {oos_sharpe:.3f} < H192-D {h192d_sharpe_oos:.3f}"

    print(f"  Verdict: {verdict}")
    print(f"  {note}")
    print(f"  H205 MaxDD={oos_maxdd:.1f}% vs H192-D MaxDD={calc_metrics(h192d_oos)['max_dd_pct']:.1f}%")

    # ── Save results ────────────────────────────────────────────────────────
    result = {
        "hypothesis": "H205",
        "description": "TOM Calendar Overlay on H192-D BAB",
        "verdict":     verdict,
        "is": {
            "period": "2013-2020",
            **{k: m_is[k] for k in ["sharpe", "cagr_pct", "max_dd_pct", "neg_years", "cumul"]},
        },
        "oos": {
            "period": "2021-2026",
            **{k: m_oos[k] for k in ["sharpe", "cagr_pct", "max_dd_pct", "neg_years", "cumul"]},
        },
        "baseline_h192d_oos_sharpe": h192d_sharpe_oos,
        "confirm_threshold_sharpe": confirm_threshold,
        "tom_pct_invested": round(float(tom_mask_fraction(prices.index)), 3),
    }
    out = RESULT_DIR / "h205_results.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"\n  Results saved → {out}")
    print("=" * 76)


def tom_mask_fraction(idx: pd.DatetimeIndex) -> float:
    """What fraction of trading days are TOM days?"""
    mask = build_tom_mask(idx)
    return mask.sum() / len(mask)


if __name__ == "__main__":
    main()
