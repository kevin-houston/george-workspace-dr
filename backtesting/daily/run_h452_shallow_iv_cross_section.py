#!/usr/bin/env python3
"""
H449 — Shallow IV Representation Cross-Section Factor
Source: arXiv:2603.17151 (Lin, March 2026)

Hypothesis: Shallow neural representation of option-implied skewness
and kurtosis predicts the cross-section of equity returns.

Variants:
  A — 30d implied skewness standalone factor (IVSKEW)
  B — IVSKEW + IVKURT composite
  C — long/short dollar-neutral quintiles
  D — Var C + VIX < 25 regime gate

Gate: OOS Sharpe >= 1.0
IS:  2018-01-01 to 2021-12-31
OOS: 2022-01-01 to 2026-06-30
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ── Parameters ────────────────────────────────────────────────────────────────
IS_START   = '2018-01-01'
IS_END     = '2021-12-31'
OOS_START  = '2022-01-01'
OOS_END    = '2026-06-30'

# S&P 500 universe (liquid, options-active subset)
# Using a representative 50-stock options-heavy universe as tractable proxy
# Full implementation would use all ~400 stocks with liquid options chains
UNIVERSE = [
    'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'TSLA', 'JPM', 'V', 'MA',
    'UNH', 'XOM', 'WMT', 'PG', 'HD', 'LLY', 'MRK', 'ABBV', 'AVGO', 'JNJ',
    'CVX', 'PEP', 'COST', 'KO', 'MCD', 'CRM', 'CSCO', 'TMO', 'ACN', 'NFLX',
    'BAC', 'TXN', 'QCOM', 'INTC', 'AMD', 'MS', 'GS', 'BLK', 'SBUX', 'CAT',
    'DE', 'RTX', 'MMM', 'GE', 'BA', 'F', 'GM', 'T', 'VZ', 'DIS'
]

VIX_GATE = 25.0  # Var D regime filter


# ── Data loading ──────────────────────────────────────────────────────────────
def load_stock_prices(tickers: list, start: str, end: str) -> pd.DataFrame:
    """Load monthly-resampled adjusted close prices."""
    raw = yf.download(tickers, start=start, end=end, progress=False, auto_adjust=True)['Close']
    if isinstance(raw, pd.Series):
        raw = raw.to_frame(tickers[0])
    raw.index = pd.to_datetime(raw.index)
    # Resample to month-end
    monthly = raw.resample('ME').last()
    return monthly


def load_vix(start: str, end: str) -> pd.Series:
    vix = yf.download('^VIX', start=start, end=end, progress=False, auto_adjust=True)['Close']
    vix.index = pd.to_datetime(vix.index)
    return vix.resample('ME').last().squeeze()


# ── IV-based factor proxies ────────────────────────────────────────────────────
def compute_historical_skew_kurtosis(prices: pd.DataFrame,
                                      lookback: int = 63) -> tuple:
    """
    Proxy for implied skewness and kurtosis using realized higher moments.
    In full implementation, replace with options chain IV surface moments
    extracted via Polygon API using the shallow NN representation from arXiv:2603.17151.

    IVSKEW proxy: negative of 63-day realized skewness of log returns
      (stocks with negative return skew have higher demand for put protection
       → higher implied skewness premium → documented underperformance).

    IVKURT proxy: 63-day realized excess kurtosis
      (higher kurtosis → fatter tails → options buyers pay more → overpriced puts
       → short-put outperformance documented by Bakshi et al.).
    """
    log_ret = np.log(prices / prices.shift(1))

    # 63-day rolling skewness and kurtosis (monthly signal)
    skew_monthly  = log_ret.rolling(lookback).skew().resample('ME').last()
    kurt_monthly  = log_ret.rolling(lookback).kurt().resample('ME').last()  # excess

    # IVSKEW factor: stocks with most negative skew (left-tail risk) → expected to
    # underperform (short them in Var C). Rank so HIGH rank = more negative skew.
    ivskew_rank = skew_monthly.rank(axis=1, pct=True)  # high rank = most negative skew
    # Invert: we want high-rank = negative skew → these underperform
    # Short high-rank, long low-rank in Var C

    # IVKURT factor: high kurtosis → overpriced tail options → short-put alpha
    # High rank = high kurtosis = expected to outperform
    ivkurt_rank = kurt_monthly.rank(axis=1, pct=True)

    return skew_monthly, kurt_monthly, ivskew_rank, ivkurt_rank


def compute_composite_signal(ivskew_rank: pd.DataFrame,
                              ivkurt_rank: pd.DataFrame) -> pd.DataFrame:
    """
    Composite: weight IVSKEW inverted + IVKURT.
    IVSKEW inverted: low skew rank → high composite score (expected outperform).
    IVKURT: high kurtosis rank → high composite score.
    """
    # Invert skew rank (low skew rank = good = high composite)
    inv_skew = 1.0 - ivskew_rank
    composite = 0.5 * inv_skew + 0.5 * ivkurt_rank
    return composite


# ── Strategy simulation ────────────────────────────────────────────────────────
def simulate_cross_section(signal_df: pd.DataFrame,
                            prices: pd.DataFrame,
                            vix_monthly: pd.Series,
                            variant: str = 'A',
                            vix_gate: float = None) -> pd.Series:
    """
    Monthly rebalancing cross-sectional strategy.
    signal_df: monthly percentile ranks (high = expected outperform in Var B/D).
    """
    monthly_ret = prices.pct_change()  # already monthly
    aligned_ret = monthly_ret.shift(-1)  # next month return for each signal month
    aligned_ret, signal_df = aligned_ret.align(signal_df, join='inner')

    port_rets = []
    dates = []

    for dt in signal_df.index:
        if dt not in aligned_ret.index:
            continue

        scores = signal_df.loc[dt].dropna()
        next_ret = aligned_ret.loc[dt].reindex(scores.index).dropna()
        scores = scores.reindex(next_ret.index).dropna()

        if len(scores) < 10:
            port_rets.append(0.0)
            dates.append(dt)
            continue

        # Regime gate (Var D)
        if vix_gate is not None:
            if dt in vix_monthly.index and vix_monthly.loc[dt] >= vix_gate:
                port_rets.append(0.0)
                dates.append(dt)
                continue

        # Quintile cutoffs
        q80 = scores.quantile(0.80)
        q20 = scores.quantile(0.20)

        long_stocks  = scores[scores >= q80].index
        short_stocks = scores[scores <= q20].index

        if variant in ('A', 'B'):
            # Long-only top quintile
            if len(long_stocks) == 0:
                port_rets.append(0.0)
            else:
                port_rets.append(next_ret.loc[long_stocks].mean())
        elif variant in ('C', 'D'):
            # Dollar-neutral long/short
            long_ret  = next_ret.loc[long_stocks].mean()  if len(long_stocks)  > 0 else 0.0
            short_ret = next_ret.loc[short_stocks].mean() if len(short_stocks) > 0 else 0.0
            port_rets.append(0.5 * long_ret - 0.5 * short_ret)

        dates.append(dt)

    return pd.Series(port_rets, index=pd.DatetimeIndex(dates))


# ── Performance metrics ────────────────────────────────────────────────────────
def performance_metrics(returns: pd.Series, label: str) -> dict:
    daily = returns.dropna()
    if len(daily) == 0:
        return {}

    # Monthly returns — annualise assuming ~12 obs/year
    ann_ret = daily.mean() * 12
    ann_vol = daily.std() * np.sqrt(12)
    sharpe  = ann_ret / ann_vol if ann_vol > 0 else 0.0

    cum     = (1 + daily).cumprod()
    roll_max = cum.cummax()
    drawdown = (cum - roll_max) / roll_max
    max_dd  = drawdown.min()

    cagr = cum.iloc[-1] ** (12 / len(daily)) - 1 if len(daily) > 0 else 0.0

    annual = daily.groupby(daily.index.year).apply(lambda x: (1 + x).prod() - 1)
    neg_years = (annual < 0).sum()

    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"{'='*55}")
    print(f"  Sharpe:      {sharpe:.3f}")
    print(f"  CAGR:        {cagr*100:.1f}%")
    print(f"  MaxDD:       {max_dd*100:.1f}%")
    print(f"  Neg Years:   {neg_years}")
    print(f"  Annual returns:")
    for yr, r in annual.items():
        print(f"    {yr}: {r*100:+.1f}%")

    return {'sharpe': sharpe, 'cagr': cagr, 'max_dd': max_dd, 'neg_years': int(neg_years)}


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("H449 — Shallow IV Representation Cross-Section Factor")
    print(f"IS:  {IS_START} to {IS_END}")
    print(f"OOS: {OOS_START} to {OOS_END}")
    print(f"Universe: {len(UNIVERSE)} stocks")
    print("\nNOTE: Full implementation uses Polygon options IV surface moments")
    print("      via shallow NN representation (arXiv:2603.17151).")
    print("      Current stub uses realized skew/kurtosis as tractable proxy.")

    full_start = '2017-01-01'
    print("\nLoading prices...")
    prices = load_stock_prices(UNIVERSE, full_start, OOS_END)
    vix_monthly = load_vix(full_start, OOS_END)

    print("Computing IV proxy signals...")
    daily_prices = yf.download(UNIVERSE, start=full_start, end=OOS_END,
                                progress=False, auto_adjust=True)['Close']
    daily_prices.index = pd.to_datetime(daily_prices.index)

    skew_m, kurt_m, ivskew_rank, ivkurt_rank = compute_historical_skew_kurtosis(
        daily_prices, lookback=63
    )
    composite_rank = compute_composite_signal(ivskew_rank, ivkurt_rank)

    # Shift signals by 1 month to avoid look-ahead
    ivskew_shifted    = ivskew_rank.shift(1)
    composite_shifted = composite_rank.shift(1)

    # IS / OOS split
    is_prices   = prices.loc[IS_START:IS_END]
    oos_prices  = prices.loc[OOS_START:OOS_END]
    is_vix_m    = vix_monthly.loc[IS_START:IS_END]
    oos_vix_m   = vix_monthly.loc[OOS_START:OOS_END]

    # Inverted skew rank for Var A: low skew rank = expected outperform
    inv_skew_shifted = (1.0 - ivskew_rank).shift(1)

    results = {}

    for period_label, price_df, sig_df, vix_m in [
        ('IS',  is_prices,  inv_skew_shifted.loc[IS_START:IS_END],   is_vix_m),
        ('OOS', oos_prices, inv_skew_shifted.loc[OOS_START:OOS_END], oos_vix_m),
    ]:
        ret = simulate_cross_section(sig_df, price_df, vix_m, variant='A')
        results[f'VarA_{period_label}'] = performance_metrics(
            ret, f"Var A — IVSKEW Long-Only [{period_label}]"
        )

    for period_label, price_df, sig_df, vix_m in [
        ('IS',  is_prices,  composite_shifted.loc[IS_START:IS_END],   is_vix_m),
        ('OOS', oos_prices, composite_shifted.loc[OOS_START:OOS_END], oos_vix_m),
    ]:
        for var, vgate in [('B', None), ('C', None), ('D', VIX_GATE)]:
            if var == 'B' and period_label == 'IS':
                continue  # skip IS for brevity on B
            ret = simulate_cross_section(sig_df, price_df, vix_m,
                                          variant=var, vix_gate=vgate)
            results[f'Var{var}_{period_label}'] = performance_metrics(
                ret, f"Var {var} — Composite IV {'L/S' if var in ('C','D') else 'Long'} [{period_label}]"
            )

    print("\n" + "="*55)
    print("  GATE CHECK (OOS Sharpe >= 1.0)")
    print("="*55)
    for k, v in results.items():
        if 'OOS' in k and v:
            passed = v.get('sharpe', 0) >= 1.0
            print(f"  {k}: Sharpe={v.get('sharpe',0):.3f} → {'PASS' if passed else 'FAIL'}")


if __name__ == '__main__':
    main()
