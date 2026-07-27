#!/usr/bin/env python3
"""
H460 — Bias-Corrected Multi-Factor Pipeline for H198: Mask-First Design

Source: arXiv:2507.07107 (Du, May 2026)
        "Machine Learning Enhanced Multi-Factor Quantitative Trading:
         A Cross-Sectional Portfolio Optimization Approach with Bias Correction"

Hypothesis: Du identifies 'upstream contamination' in rolling factor pipelines — thin-volume
or halt days propagate silently through moving averages and ranks, inflating apparent IC
while reducing realized Sharpe. Fix: a boolean tradability mask is constructed at load time
and threaded through every operator, so no window ever reads a non-tradable day. H460 applies
the mask-first design to H198 6-1m momentum and IMOM6 signals. We define non-tradable days
as those where a stock's daily volume falls below its own rolling 20th-percentile baseline.
Additionally tests a bias-corrected Alpha101 factor (#001: 1-day reversal with volume mask).

Variants:
  A: Mask-corrected 6-1m momentum (volume mask at 20th pct threshold), top-6
  B: Mask-corrected 6-1m momentum (volume mask at 10th pct threshold, stricter), top-6
  C: Mask-corrected IMOM6 signal (illusion momentum with non-tradable days removed), top-6
  D: Alpha101 factor #001 (1-day reversal) with volume mask, top-6 short-reversal
  E: H198 unmasked 6-1m momentum top-6 (sanity baseline)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe >= 1.174 (H198 baseline) — any improvement informs bias-correction value
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY    = 'H460'
UNIVERSE    = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START  = '2012-01-01'
IS_START    = '2013-01-01'
IS_END      = '2020-12-31'
OOS_START   = '2021-01-01'
OOS_END     = '2026-07-25'
N_POSITIONS = 6

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f'Downloading {len(UNIVERSE)} stocks (price + volume)...')
    raw = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)
    prices  = raw['Close'].dropna(how='all').ffill()
    volumes = raw['Volume'].dropna(how='all').fillna(0)
    return prices, volumes


def build_volume_mask(volumes: pd.DataFrame, pct_threshold: float = 20.0) -> pd.DataFrame:
    """
    Tradability mask: True = tradable (volume above threshold percentile).
    Rolling 252-day window to compute the IS-calibrated baseline.
    pct_threshold: percentile below which days are masked (non-tradable).
    """
    rolling_pct = volumes.rolling(252, min_periods=60).apply(
        lambda x: np.nanpercentile(x, pct_threshold), raw=True
    )
    mask = volumes >= rolling_pct  # True = tradable
    return mask


def masked_rolling_return(prices: pd.DataFrame, mask: pd.DataFrame,
                           window: int) -> pd.DataFrame:
    """
    Compute rolling return over `window` trading days using only tradable days.
    If fewer than window/2 tradable days exist, returns NaN.
    """
    log_ret = np.log(prices / prices.shift(1))
    masked_log = log_ret.where(mask)  # NaN out non-tradable days

    # Sum of log returns over window (equivalent to compound return minus skip-month artifacts)
    roll_sum = masked_log.rolling(window, min_periods=window // 2).sum()
    return np.exp(roll_sum) - 1


def masked_imom(prices: pd.DataFrame, mask: pd.DataFrame, window: int = 126) -> pd.DataFrame:
    """
    IMOM = compound_return - arithmetic_sum, with mask applied.
    Only tradable days contribute to the sum.
    """
    daily_ret = prices.pct_change()
    masked_ret = daily_ret.where(mask)

    comp  = masked_ret.rolling(window, min_periods=window // 2).apply(
        lambda x: (1 + x).prod() - 1, raw=True
    )
    arith = masked_ret.rolling(window, min_periods=window // 2).sum()
    return comp - arith


def alpha101_001(prices: pd.DataFrame, volumes: pd.DataFrame,
                 mask: pd.DataFrame) -> pd.DataFrame:
    """
    Alpha101 Factor #001: (-1 * correlation(rank(delta(log(volume), 1)), rank(delta(price, 1)), 6))
    Simplified tractable version: 1-day reversal weighted by volume surprise.
    With mask: only tradable days enter the correlation computation.
    """
    log_vol    = np.log(volumes.replace(0, np.nan))
    d_logvol   = log_vol.diff(1).where(mask)
    d_price    = prices.pct_change(1).where(mask)

    def rolling_corr(a: pd.Series, b: pd.Series, w: int = 6) -> pd.Series:
        return a.rolling(w, min_periods=3).corr(b)

    result = {}
    for col in prices.columns:
        rvol  = d_logvol[col].rank(pct=True, na_option='keep')
        rprice = d_price[col].rank(pct=True, na_option='keep')
        result[col] = -1 * rolling_corr(rvol, rprice)
    return pd.DataFrame(result, index=prices.index)


def build_signals(prices: pd.DataFrame, volumes: pd.DataFrame) -> dict:
    """Build monthly signals from masked and unmasked data."""
    mask20 = build_volume_mask(volumes, pct_threshold=20.0)
    mask10 = build_volume_mask(volumes, pct_threshold=10.0)

    # Var A: mask-corrected 6-1m momentum (20th pct mask)
    # 6-month masked return, skip most-recent 1 month
    ret6_mask20 = masked_rolling_return(prices, mask20, window=126)
    ret1_raw    = prices.pct_change(21)  # ~1 month skip
    mom_6_1_mask20 = (ret6_mask20 - ret1_raw).resample('MS').last().shift(1)

    # Var B: stricter 10th pct mask
    ret6_mask10    = masked_rolling_return(prices, mask10, window=126)
    mom_6_1_mask10 = (ret6_mask10 - ret1_raw).resample('MS').last().shift(1)

    # Var C: IMOM with 20th pct mask
    imom6_masked = masked_imom(prices, mask20, window=126).resample('MS').last().shift(1)

    # Var D: Alpha101 #001 (reversal) with mask
    alpha001 = alpha101_001(prices, volumes, mask20).resample('MS').last().shift(1)

    # Var E: unmasked 6-1m baseline
    ret6_raw    = prices.pct_change(126)
    mom_6_1_raw = (ret6_raw - ret1_raw).resample('MS').last().shift(1)

    return {
        'A': mom_6_1_mask20,
        'B': mom_6_1_mask10,
        'C': imom6_masked,
        'D': alpha001,
        'E': mom_6_1_raw,
    }


def run_backtest(prices: pd.DataFrame, volumes: pd.DataFrame) -> dict:
    sigs    = build_signals(prices, volumes)
    monthly = prices.resample('MS').first()
    fwd_ret = monthly.pct_change().shift(-1)

    oos_dates = [d for d in fwd_ret.index if OOS_START <= str(d.date()) <= OOS_END]

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        sig     = sigs[var]
        rets, dates = [], []

        for dt in oos_dates:
            if dt not in fwd_ret.index or dt not in sig.index:
                continue
            ret_row = fwd_ret.loc[dt].dropna()
            sig_row = sig.loc[dt].dropna()
            common  = sig_row.index.intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            # Var D (reversal): select highest alpha001 (largest negative autocorr = biggest bounce)
            sel = sig_row[common].sort_values(ascending=(var != 'D')).head(N_POSITIONS).index
            r   = ret_row.reindex(sel).mean()
            if not np.isnan(r):
                rets.append(float(r))
                dates.append(dt)

        results[var] = pd.Series(rets, index=dates, name=f'{STRATEGY}_{var}')
    return results


def evaluate(s: pd.Series, label: str) -> dict:
    r = s.dropna()
    if len(r) < 6:
        return {'sharpe': 0.0, 'cagr': 0.0, 'maxdd': 0.0, 'neg_years': 0}
    sharpe = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else 0.0
    cum    = (1 + r).cumprod()
    n_yrs  = len(r) / 12
    cagr   = cum.iloc[-1] ** (1 / max(n_yrs, 1e-6)) - 1
    maxdd  = (cum / cum.cummax() - 1).min()
    ann    = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg    = int((ann < 0).sum())
    print(f'  {label:42s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}')
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f'=== {STRATEGY} Bias-Corrected Multi-Factor Pipeline ===')
    print(f'IS: {IS_START}—{IS_END} | OOS: {OOS_START}—{OOS_END}')
    print(f'Gate: OOS Sharpe >= 1.174 (H198 baseline)')
    print()

    prices, volumes = download_data()
    results = run_backtest(prices, volumes)

    print('=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s[mask], f'OOS Var{v}')

    GATE = 1.174
    print(f'\n=== Gate Check (OOS Sharpe >= {GATE}) ===')
    confirmed = []
    for v, st in oos_stats.items():
        status = 'PASS' if st['sharpe'] >= GATE else 'FAIL'
        delta  = st['sharpe'] - oos_stats.get('E', {}).get('sharpe', 0.0)
        print(f'  Var {v}: OOS Sharpe={st["sharpe"]:.3f} (delta vs baseline: {delta:+.3f}) → {status}')
        if st['sharpe'] >= GATE:
            confirmed.append(v)

    if confirmed:
        print(f'\nCONFIRMED variants: {confirmed}')
    else:
        print('\nNOT CONFIRMED — all variants below gate')
        print('NOTE: Even a neutral result is informative — it shows bias correction')
        print('      neither helps nor hurts on US large-cap (no price-limit days).')

    out = RESULTS_DIR / 'h460_results.json'
    payload = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat()[:10],
        'oos_stats': oos_stats,
        'confirmed_variants': confirmed,
    }
    out.write_text(json.dumps(payload, indent=2))
    print(f'\nResults saved to {out}')


if __name__ == '__main__':
    main()
