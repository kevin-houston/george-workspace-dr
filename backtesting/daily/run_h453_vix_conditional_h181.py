#!/usr/bin/env python3
"""
H453 — VIX-Conditional Gate for H181 Industry-Adjusted Short-Term Reversal

Source: Nagel (2012) 'Evaporating Liquidity' RFS 25(7), 2005-2039
        Blitz, van der Grient & Honarvar (2023) SSRN:4575689

Hypothesis: H181 (industry-adjusted reversal) earns most of its alpha when
VIX is elevated, because the strategy is fundamentally a liquidity provision
service whose fee spikes during market stress. Gating H181 exposure on VIX
concentrates on the high-premium regime and avoids capital allocation during
thin-premium (low-VIX) periods.

Variants:
  A: H181 only when VIX > 20 (above long-run median), else BIL
  B: Continuous VIX scaling: W = min(VIX/20, 2.0) x baseline
  C: Triple regime: VIX>30 -> 1.5x; VIX 15-30 -> 1x; VIX<15 -> 0x (BIL)
  D: H181 baseline (no gate) — replication
  E: SPY 200MA gate on H181 (comparison: confirmed H301 pattern)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.250 (vs H181 baseline 1.138)
Universe: Same 30-stock H198 large-cap NASDAQ universe
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY  = 'H453'
UNIVERSE  = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START = '2012-01-01'
IS_START   = '2013-01-01'
IS_END     = '2020-12-31'
OOS_START  = '2021-01-01'
OOS_END    = '2026-07-21'
N_POSITIONS = 6

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Industry groupings for H198 30-stock universe (8 GICS-like groups)
INDUSTRY_MAP = {
    'AAPL': 'consumer_tech', 'MSFT': 'enterprise_sw', 'NVDA': 'semiconductors',
    'AMZN': 'consumer_tech', 'GOOGL': 'internet', 'META': 'internet',
    'TSLA': 'ev_auto', 'AVGO': 'semiconductors', 'COST': 'retail',
    'NFLX': 'media', 'AMD': 'semiconductors', 'QCOM': 'semiconductors',
    'ADBE': 'enterprise_sw', 'INTU': 'enterprise_sw', 'CSCO': 'networking',
    'TXN': 'semiconductors', 'AMAT': 'semiconductor_equipment',
    'MU': 'semiconductors', 'LRCX': 'semiconductor_equipment',
    'KLAC': 'semiconductor_equipment', 'PANW': 'cybersecurity',
    'CDNS': 'enterprise_sw', 'SNPS': 'enterprise_sw', 'MRVL': 'semiconductors',
    'FTNT': 'cybersecurity', 'CRWD': 'cybersecurity', 'WDAY': 'enterprise_sw',
    'DXCM': 'healthcare_tech', 'TEAM': 'enterprise_sw', 'ZS': 'cybersecurity'
}


def download_data():
    print(f'Downloading {len(UNIVERSE)} stocks + VIX + SPY...')
    prices = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                         auto_adjust=True, progress=False)['Close']
    prices = prices.dropna(how='all').ffill()
    vix = yf.download('^VIX', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    spy = yf.download('SPY', start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close'].squeeze()
    return prices, vix, spy


def compute_h181_signal(daily: pd.DataFrame) -> pd.DataFrame:
    """Industry-adjusted 1-month reversal signal (H181 design)."""
    monthly = daily.resample('MS').first()
    ret_1m = monthly.pct_change().shift(1)  # avoid look-ahead
    industry = pd.Series(INDUSTRY_MAP)
    # Industry-mean for each stock
    ind_mean = ret_1m.apply(
        lambda row: row.groupby(industry.reindex(row.index)).transform('mean'), axis=1
    )
    rev_in = ret_1m - ind_mean  # REV^IN: stock return minus industry average
    return ret_1m, rev_in


def compute_gates(vix_daily: pd.Series, spy_daily: pd.Series) -> pd.DataFrame:
    """Compute monthly VIX and SPY 200MA gates (shift to avoid look-ahead)."""
    vix_monthly = vix_daily.resample('MS').last().shift(1)  # end-of-prior-month VIX
    spy_200ma = spy_daily.rolling(200).mean()
    spy_above_ma = (spy_daily > spy_200ma).resample('MS').last().shift(1)
    return pd.DataFrame({
        'vix': vix_monthly,
        'spy_above_200ma': spy_above_ma
    })


def run_backtest(daily: pd.DataFrame, vix_daily: pd.Series, spy_daily: pd.Series) -> dict:
    monthly = daily.resample('MS').first()
    monthly_ret_fwd = monthly.pct_change().shift(-1)  # next-month forward return
    ret_1m, rev_in = compute_h181_signal(daily)
    gates = compute_gates(vix_daily, spy_daily)

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        rets, dates = [], []
        for dt in monthly_ret_fwd.index:
            if dt not in rev_in.index:
                continue
            sig_row = rev_in.loc[dt].dropna()
            ret_row = monthly_ret_fwd.loc[dt].dropna()
            common = sig_row.index.intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            # H181 selection: bottom N by REV^IN (biggest industry-relative losers)
            selected = sig_row[common].sort_values(ascending=True).head(N_POSITIONS).index

            # VIX / SPY gate
            vix_now = gates['vix'].get(dt, np.nan)
            spy_ma  = gates['spy_above_200ma'].get(dt, True)
            base_w  = 1.0

            if var == 'A':
                if np.isnan(vix_now) or vix_now <= 20:
                    dates.append(dt)
                    rets.append(0.0)  # hold BIL (0 return proxy)
                    continue
            elif var == 'B':
                if not np.isnan(vix_now):
                    base_w = min(vix_now / 20.0, 2.0)
            elif var == 'C':
                if not np.isnan(vix_now):
                    if vix_now > 30:
                        base_w = 1.5
                    elif vix_now < 15:
                        dates.append(dt)
                        rets.append(0.0)  # BIL
                        continue
            elif var == 'E':
                if not spy_ma:  # SPY below 200MA -> hold BIL
                    dates.append(dt)
                    rets.append(0.0)
                    continue
            # var D: no gate (baseline H181)

            ret = ret_row.reindex(selected).mean() * base_w
            if not np.isnan(ret):
                rets.append(float(ret))
                dates.append(dt)

        results[var] = pd.Series(rets, index=dates, name=f'{STRATEGY}_{var}')
    return results


def evaluate(s: pd.Series, mask, label: str) -> dict:
    r = s[mask].dropna()
    if len(r) < 6:
        return {'sharpe': 0.0, 'cagr': 0.0, 'maxdd': 0.0, 'neg_years': 0}
    sharpe = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else 0.0
    cum = (1 + r).cumprod()
    n_yrs = len(r) / 12
    cagr = cum.iloc[-1] ** (1 / max(n_yrs, 1e-6)) - 1
    maxdd = (cum / cum.cummax() - 1).min()
    ann = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg = int((ann < 0).sum())
    print(f'  {label:42s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}')
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f'=== {STRATEGY} VIX-Conditional H181 Gate ===')
    print(f'IS: {IS_START}-{IS_END} | OOS: {OOS_START}-{OOS_END}')
    print(f'Gate: OOS Sharpe > 1.250 (vs H181 baseline 1.138)')
    print()

    daily, vix, spy = download_data()
    results = run_backtest(daily, vix, spy)

    for period, label, start, end in [
        ('IS', IS_START, IS_END, None), ('OOS', OOS_START, OOS_END, None)
    ][::-1]:
        pass

    print('=== IS Results ===')
    is_stats = {}
    for v, s in results.items():
        mask = (s.index >= IS_START) & (s.index <= IS_END)
        is_stats[v] = evaluate(s, mask, f'IS Var{v}')

    print()
    print('=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s, mask, f'OOS Var{v}')

    gate = 1.250
    print(f'\n=== Gate Check (OOS Sharpe > {gate}) ===')
    confirmed = []
    for v in results:
        sh = oos_stats[v]['sharpe']
        status = 'PASS' if sh > gate else 'FAIL'
        print(f'  Var {v}: {sh:.3f} [{status}]')
        if sh > gate:
            confirmed.append(v)

    base_sh = oos_stats['D']['sharpe']  # D = H181 baseline
    verdict = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'
    print(f'\nH181 Baseline (Var D): OOS Sharpe {base_sh:.3f}')
    print(f'\nVERDICT: {verdict}')
    if confirmed:
        print(f'Confirmed variants: {confirmed}')

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': gate,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'h181_baseline_oos_sharpe': base_sh,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h453_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f'\nResults: {out_path}')


if __name__ == '__main__':
    main()
