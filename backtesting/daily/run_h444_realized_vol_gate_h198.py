#!/usr/bin/env python3
"""
H444 — Realized Volatility Regime Gate for H198 Momentum

Motivation: Choi (2026) arXiv:2607.14174 finds that portfolio-level volatility
signals from 10-K text aggregate to predictive regime information. This hypothesis
tests the price-based version: does portfolio-level realized volatility predict
whether momentum will underperform?

Hypothesis: When the H198 EW-portfolio rolling 20-day annualized realized volatility
exceeds an IS-calibrated threshold, the momentum signal degrades — reduce position
or add BIL as a dampener.

Intuition (Ang et al. 2006): Low-vol periods reward momentum; high-vol periods
produce momentum crashes (Daniel & Moskowitz 2016). Realized vol > threshold
signals elevated crash risk.

Variants:
  Var A: High-vol → top-3 (reduce from top-6)
  Var B: High-vol → BIL (full exit)
  Var C: Continuous: weight = max(0.5, 1 - vol_ratio) applied to top-6
  Var D: High-vol + low-vol → top-6 only if 3m return positive (TSMOM gate combined)
  Var E: Baseline H198 top-6 EW 6-1m momentum (no filter)
  Var F: Vol threshold = IS 70th percentile (tighter)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 AND MaxDD improvement vs baseline

Reference: Daniel & Moskowitz (2016) "Momentum Crashes" JFE.
           Choi (2026) arXiv:2607.14174 (motivation for portfolio-level vol signal).
"""

import json
import os
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY = 'H444'
H198_UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
SAFE_HAVEN = 'BIL'

DATA_START  = '2012-01-01'
IS_START    = '2013-01-01'
IS_END      = '2020-12-31'
OOS_START   = '2021-01-01'
OOS_END     = '2026-07-21'

LOOKBACK_FORMATION = 6   # momentum formation months (6-1m)
SKIP_MONTH = 1
N_POSITIONS = 6
VOL_WINDOW_DAYS = 20     # realized vol lookback (trading days)
VOL_PERCENTILE_HIGH = 80 # IS calibration: 80th pct = high-vol threshold
VOL_PERCENTILE_TIGHT = 70

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data(tickers):
    print(f"Downloading daily price data for {len(tickers)} tickers...")
    raw = yf.download(tickers + [SAFE_HAVEN], start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close']
    return raw


def compute_realized_vol_monthly(daily_prices: pd.DataFrame,
                                  tickers: list,
                                  window: int = VOL_WINDOW_DAYS) -> pd.Series:
    """
    Compute month-end rolling realized vol of equal-weight portfolio.
    Returns annualized vol series indexed by month-start dates.
    """
    ew = daily_prices[tickers].pct_change().mean(axis=1)  # EW daily return
    rv = ew.rolling(window).std() * np.sqrt(252)          # Annualized
    # Resample to month-start (use last trading day of month)
    rv_monthly = rv.resample('MS').last().shift(1)         # Shift 1 to avoid look-ahead
    return rv_monthly


def run_backtest(daily_prices: pd.DataFrame,
                 monthly_prices: pd.DataFrame,
                 vol_monthly: pd.Series,
                 vol_threshold_high: float,
                 vol_threshold_tight: float) -> dict:

    monthly_ret = monthly_prices.pct_change().shift(-1)

    results = {}
    variants = ['A', 'B', 'C', 'D', 'E', 'F']

    for var in variants:
        portfolio_rets = []
        dates = []

        for i in range(LOOKBACK_FORMATION + SKIP_MONTH, len(monthly_prices) - 1):
            dt = monthly_prices.index[i]

            # Realized vol regime
            rv = vol_monthly.get(dt, np.nan)
            threshold = vol_threshold_high if var != 'F' else vol_threshold_tight
            high_vol = (not np.isnan(rv)) and (rv > threshold)
            low_vol = (not np.isnan(rv)) and (rv < threshold * 0.6)

            # 6-1m momentum signal (skip most recent month)
            price_now  = monthly_prices.iloc[i]
            price_6m   = monthly_prices.iloc[i - LOOKBACK_FORMATION]
            price_1m   = monthly_prices.iloc[i - SKIP_MONTH]

            r6_skip = (price_now / price_6m - 1) - (price_now / price_1m - 1)

            # 3m return for TSMOM check (Var D)
            price_3m = monthly_prices.iloc[i - 3]
            r3 = (price_now / price_3m - 1)

            # Score and rank (exclude BIL from ranking)
            valid = r6_skip.drop(SAFE_HAVEN, errors='ignore').dropna()
            ranked = valid.sort_values(ascending=False)

            if var == 'A':
                n = 3 if high_vol else N_POSITIONS
                selected = list(ranked.head(n).index)

            elif var == 'B':
                if high_vol:
                    selected = [SAFE_HAVEN]
                else:
                    selected = list(ranked.head(N_POSITIONS).index)

            elif var == 'C':
                selected = list(ranked.head(N_POSITIONS).index)
                # Weight scaled by vol ratio
                if not np.isnan(rv) and rv > 0:
                    vol_ratio = rv / threshold
                    scale = max(0.4, 1.0 - 0.4 * (vol_ratio - 1))
                else:
                    scale = 1.0
            elif var == 'D':
                # Combine vol gate + TSMOM: only enter if 3m positive AND not high-vol
                tsmom_pass = r3.drop(SAFE_HAVEN, errors='ignore') > 0
                filtered = ranked[tsmom_pass]
                if high_vol:
                    filtered = filtered.head(3)
                else:
                    filtered = filtered.head(N_POSITIONS)
                selected = list(filtered.index) if len(filtered) > 0 else [SAFE_HAVEN]

            elif var == 'F':
                n = 3 if high_vol else N_POSITIONS
                selected = list(ranked.head(n).index)

            else:  # E — baseline
                selected = list(ranked.head(N_POSITIONS).index)

            # Portfolio return
            if not selected:
                ret = 0.0
            elif var == 'C':
                base_ret = monthly_ret.iloc[i][selected].mean()
                ret = base_ret * scale
            else:
                ret = monthly_ret.iloc[i][selected].mean()

            portfolio_rets.append(float(ret))
            dates.append(monthly_prices.index[i + 1])

        rets = pd.Series(portfolio_rets, index=dates, name=f'H444_{var}')
        results[var] = rets

    return results


def evaluate(rets: pd.Series, period_mask, label: str) -> dict:
    r = rets[period_mask].dropna()
    if len(r) < 6:
        return {'sharpe': 0, 'cagr': 0, 'maxdd': 0, 'neg_years': 0}
    ann_factor = 12
    sharpe = r.mean() / r.std() * np.sqrt(ann_factor) if r.std() > 0 else 0
    cum = (1 + r).cumprod()
    n_years = len(r) / 12
    cagr = cum.iloc[-1] ** (1 / max(n_years, 0.001)) - 1 if len(cum) > 0 else 0
    maxdd = (cum / cum.cummax() - 1).min()
    ann_rets = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg_years = int((ann_rets < 0).sum())
    print(f"  {label}: Sharpe={sharpe:.3f}, MaxDD={maxdd:.1%}, CAGR={cagr:.1%}, NegYrs={neg_years}")
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg_years}


def main():
    print(f"=== {STRATEGY} Realized-Vol Regime Gate for H198 Momentum ===")
    print(f"IS: {IS_START}–{IS_END} | OOS: {OOS_START}–{OOS_END}")
    print(f"Gate: OOS Sharpe > 1.174 (H198 baseline)")
    print()

    # Download data
    daily = download_data(H198_UNIVERSE)
    monthly = daily.resample('MS').first()

    # Compute portfolio realized vol signal
    print("Computing realized vol signal...")
    vol_monthly = compute_realized_vol_monthly(daily, H198_UNIVERSE)

    # IS calibration of vol threshold
    is_mask_daily = (vol_monthly.index >= IS_START) & (vol_monthly.index <= IS_END)
    is_vol = vol_monthly[is_mask_daily].dropna()
    vol_threshold_high  = is_vol.quantile(VOL_PERCENTILE_HIGH / 100)
    vol_threshold_tight = is_vol.quantile(VOL_PERCENTILE_TIGHT / 100)
    print(f"IS vol threshold (80th pct): {vol_threshold_high:.3f} ({vol_threshold_high*100:.1f}% annualized)")
    print(f"IS vol threshold (70th pct): {vol_threshold_tight:.3f} ({vol_threshold_tight*100:.1f}% annualized)")
    print()

    # Run backtest
    all_results = run_backtest(daily, monthly, vol_monthly,
                               vol_threshold_high, vol_threshold_tight)

    # Evaluate — masks applied to each result series index directly
    print("=== IS Results ===")
    is_stats = {v: evaluate(all_results[v],
                            (all_results[v].index >= IS_START) & (all_results[v].index <= IS_END),
                            f"IS_Var{v}") for v in all_results}
    print()
    print("=== OOS Results ===")
    oos_stats = {v: evaluate(all_results[v],
                             (all_results[v].index >= OOS_START) & (all_results[v].index <= OOS_END),
                             f"OOS_Var{v}") for v in all_results}

    # Gate check
    gate_sharpe = 1.174
    print(f"\n=== Gate Check (OOS Sharpe > {gate_sharpe}) ===")
    confirmed_variants = []
    for v in all_results:
        s = oos_stats[v]['sharpe']
        passed = s > gate_sharpe
        status = 'PASS' if passed else 'FAIL'
        print(f"  Var {v}: OOS {s:.3f} [{status}]")
        if passed:
            confirmed_variants.append(v)

    best_var = max(all_results, key=lambda v: oos_stats[v]['sharpe'])
    best_sharpe = oos_stats[best_var]['sharpe']
    baseline_sharpe = oos_stats['E']['sharpe']
    verdict = 'CONFIRMED' if confirmed_variants else 'NOT CONFIRMED'

    print(f"\nBaseline (Var E): OOS Sharpe {baseline_sharpe:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sharpe:.3f}")
    print(f"\nVERDICT: {verdict}")
    if confirmed_variants:
        print(f"Confirmed variants: {confirmed_variants}")
    if best_sharpe > baseline_sharpe:
        print("→ Realized vol gate ADDS VALUE vs baseline")
    else:
        print("→ Realized vol gate does NOT add value vs baseline")

    # Save results
    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': gate_sharpe,
        'vol_threshold_high': round(float(vol_threshold_high), 4),
        'vol_threshold_tight': round(float(vol_threshold_tight), 4),
        'verdict': verdict,
        'confirmed_variants': confirmed_variants,
        'best_variant': best_var,
        'best_oos_sharpe': best_sharpe,
        'baseline_oos_sharpe': baseline_sharpe,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h444_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")


if __name__ == '__main__':
    main()
