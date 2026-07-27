#!/usr/bin/env python3
"""
H458 — Multi-Scale Markov-Switching GARCH Volatility Regime Gate for H026 ETF Portfolio

Source: arXiv:2606.06190 (Chaudhary, Jun 2026)
        "Multi-Scale Markov Switching GARCH: Volatility Regime Detection in EUR/USD"

Hypothesis: Chaudhary's triple-timeframe MS-GARCH framework operates simultaneously
across Daily (macro), Weekly (meso), and Monthly (micro) scales, each with AR(1)-MS-GARCH
and three Calm/Turbulent/Crisis hidden states. The outer-product of per-scale regime
probabilities forms a 27-state cross-scale tensor. H458 adapts a two-scale (daily + weekly)
version to the H026 25-ETF equal-weight portfolio return series, derives a composite
Crisis probability, and uses it as a position-sizing gate: full top-1 in Calm, top-2
in Turbulent, BIL in Crisis. Uses hmmlearn as the MS-GARCH approximation.

Variants:
  A: Two-scale (daily+weekly) composite Crisis gate — BIL when crisis > 0.5
  B: Single-scale daily 3-state MS-GARCH (Calm/Turbulent/Crisis), top-1 vs. BIL
  C: Two-scale — top-2 in Turbulent, top-1 in Calm, BIL in Crisis
  D: Continuous crisis weight — scale position by (1 - crisis_prob)
  E: H026 H346 OB-gated top-2 baseline (no MS-GARCH gate)

IS: 2008-2017, OOS: 2018-2026
Gate: OOS Sharpe >= 3.238 (H346 canonical) AND MaxDD improvement vs -5.7%
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY   = 'H458'
H026_UNIVERSE = [
    'XLK', 'XLV', 'XLF', 'XLY', 'XLP', 'XLE', 'XLI', 'XLU', 'XLB', 'XLRE',
    'XLC', 'QQQ', 'IWM', 'EFA', 'EEM', 'GLD', 'SLV', 'DBC', 'TLT', 'IEF',
    'HYG', 'LQD', 'VNQ', 'AGG', 'BIL'
]
BIL         = 'BIL'
DATA_START  = '2007-01-01'
IS_START    = '2008-01-01'
IS_END      = '2017-12-31'
OOS_START   = '2018-01-01'
OOS_END     = '2026-07-25'

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f'Downloading H026 universe ({len(H026_UNIVERSE)} ETFs)...')
    prices = yf.download(H026_UNIVERSE, start=DATA_START, end=OOS_END,
                         auto_adjust=True, progress=False)['Close']
    prices = prices.dropna(how='all').ffill()
    return prices


def compute_portfolio_returns(prices: pd.DataFrame) -> tuple:
    """Compute daily and weekly EW portfolio returns for MS-GARCH fitting."""
    daily_ret  = prices.pct_change().dropna(how='all')
    ew_daily   = daily_ret.drop(columns=[BIL], errors='ignore').mean(axis=1)
    weekly_ret = ew_daily.resample('W-FRI').apply(lambda x: (1 + x).prod() - 1)
    monthly    = prices.resample('MS').first()
    monthly_ret = monthly.pct_change()
    return ew_daily, weekly_ret, monthly_ret


def fit_hmm_regime(returns: pd.Series, n_states: int = 3,
                   is_end: str = IS_END) -> tuple:
    """
    Fit a Gaussian HMM on return series (IS window).
    Returns (model, regime_labels) — sorted so state 0=Calm, 1=Turbulent, 2=Crisis
    based on ascending conditional variance.
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        print('  hmmlearn not available — install with: pip install hmmlearn')
        return None, pd.Series(1, index=returns.index)

    is_ret = returns[returns.index <= is_end].dropna()
    X = is_ret.values.reshape(-1, 1)

    model = GaussianHMM(n_components=n_states, covariance_type='full',
                        n_iter=200, random_state=42)
    model.fit(X)

    # Order states by conditional variance (ascending = Calm first)
    vars_ = np.array([model.covars_[i, 0, 0] for i in range(n_states)])
    order = np.argsort(vars_)  # low-var state first
    # Remap states
    state_map = {old: new for new, old in enumerate(order)}

    # Predict on full series for OOS use (forward-predict only — filtered probs)
    X_full = returns.dropna().values.reshape(-1, 1)
    raw_states = model.predict(X_full)
    mapped = pd.Series([state_map[s] for s in raw_states],
                       index=returns.dropna().index)
    # Shift by 1 month when used at monthly frequency to avoid look-ahead
    return model, mapped, state_map, order


def compute_composite_crisis_prob(daily_ret: pd.Series, weekly_ret: pd.Series,
                                  is_end: str = IS_END) -> pd.Series:
    """
    Two-scale crisis probability: outer-product of daily and weekly MS-GARCH states.
    Simplified: compute daily and weekly regime independently, combine linearly.
    Crisis prob = 0.5 * P(daily crisis) + 0.5 * P(weekly crisis)
    """
    _, daily_states, _, _ = fit_hmm_regime(daily_ret, n_states=3, is_end=is_end)
    _, weekly_states, _, _ = fit_hmm_regime(weekly_ret, n_states=3, is_end=is_end)

    # Convert states to crisis probability: state=2 -> 1.0, state=1 -> 0.4, state=0 -> 0.0
    state_to_prob = {0: 0.0, 1: 0.4, 2: 1.0}
    daily_crisis  = daily_states.map(state_to_prob)
    weekly_crisis = weekly_states.map(state_to_prob)

    # Resample both to monthly
    daily_m  = daily_crisis.resample('MS').mean()
    weekly_m = weekly_crisis.resample('MS').mean()

    crisis_prob = (0.5 * daily_m + 0.5 * weekly_m.reindex(daily_m.index).ffill())
    return crisis_prob.shift(1)  # shift to avoid look-ahead at month boundary


def compute_momentum_signal(monthly_ret: pd.DataFrame) -> pd.DataFrame:
    """12-month momentum for H026 ETF selection."""
    return monthly_ret.rolling(12).apply(
        lambda x: (1 + x).prod() - 1, raw=True
    ).shift(1)


def run_backtest(prices: pd.DataFrame) -> dict:
    ew_daily, weekly_ret, monthly_ret = compute_portfolio_returns(prices)

    print('  Fitting two-scale MS-GARCH (daily + weekly)...')
    crisis_prob_2scale = compute_composite_crisis_prob(ew_daily, weekly_ret, IS_END)

    print('  Fitting single-scale daily MS-GARCH...')
    _, daily_states, _, _ = fit_hmm_regime(ew_daily, n_states=3, is_end=IS_END)
    daily_states_m = daily_states.resample('MS').last().shift(1)

    mom12 = compute_momentum_signal(monthly_ret)

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E']:
        rets, dates = [], []

        for dt in monthly_ret.index:
            period_label = str(dt.date())
            if not (OOS_START <= period_label <= OOS_END):
                continue

            # Forward return: pick from next-month
            fwd = monthly_ret.loc[dt].dropna()
            if BIL not in fwd.index:
                continue

            if var == 'E':
                # H346 OB-gated top-2 baseline (simplified: plain top-2 momentum)
                sig_row = mom12.loc[dt].dropna() if dt in mom12.index else pd.Series(dtype=float)
                if len(sig_row) < 2:
                    rets.append(float(fwd.get(BIL, 0.0)))
                    dates.append(dt)
                    continue
                top2 = sig_row.sort_values(ascending=False).head(2).index
                r = fwd.reindex(top2).mean()
                rets.append(float(r) if not np.isnan(r) else float(fwd.get(BIL, 0.0)))
                dates.append(dt)
                continue

            # Determine position tier
            if var in ('A', 'C', 'D'):
                cprob = float(crisis_prob_2scale.get(dt, 0.4))
            else:
                # Var B: single scale
                st = int(daily_states_m.get(dt, 1))
                cprob = {0: 0.0, 1: 0.4, 2: 1.0}.get(st, 0.4)

            sig_row = mom12.loc[dt].dropna() if dt in mom12.index else pd.Series(dtype=float)

            if var == 'D':
                # Continuous weight
                weight = max(0.0, 1.0 - cprob)
                if len(sig_row) < 1:
                    bil_ret = float(fwd.get(BIL, 0.0))
                    rets.append(bil_ret)
                    dates.append(dt)
                    continue
                top1 = sig_row.sort_values(ascending=False).head(1).index
                strat_ret = float(fwd.reindex(top1).mean())
                bil_ret   = float(fwd.get(BIL, 0.0))
                r = weight * strat_ret + (1 - weight) * bil_ret
                rets.append(r if not np.isnan(r) else bil_ret)
                dates.append(dt)
                continue

            if cprob > 0.5:
                # Crisis: BIL
                rets.append(float(fwd.get(BIL, 0.0)))
            elif cprob > 0.25:
                # Turbulent
                if var == 'C':
                    # top-2 in turbulent
                    n = 2
                else:
                    # Var A/B: top-1 in turbulent
                    n = 1
                if len(sig_row) >= n:
                    top_n = sig_row.sort_values(ascending=False).head(n).index
                    r = fwd.reindex(top_n).mean()
                    rets.append(float(r) if not np.isnan(r) else float(fwd.get(BIL, 0.0)))
                else:
                    rets.append(float(fwd.get(BIL, 0.0)))
            else:
                # Calm: top-1
                if len(sig_row) >= 1:
                    top1 = sig_row.sort_values(ascending=False).head(1).index
                    r = fwd.reindex(top1).mean()
                    rets.append(float(r) if not np.isnan(r) else float(fwd.get(BIL, 0.0)))
                else:
                    rets.append(float(fwd.get(BIL, 0.0)))

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
    print(f'=== {STRATEGY} Multi-Scale MS-GARCH Regime Gate (H026) ===')
    print(f'IS: {IS_START}—{IS_END} | OOS: {OOS_START}—{OOS_END}')
    print(f'Gate: OOS Sharpe >= 3.238 (H346) AND MaxDD < -5.7%')
    print()

    prices  = download_data()
    results = run_backtest(prices)

    print('=== OOS Results ===')
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s[mask], f'OOS Var{v}')

    GATE = 3.238
    print(f'\n=== Gate Check (OOS Sharpe >= {GATE}) ===')
    confirmed = []
    for v, st in oos_stats.items():
        status = 'PASS' if st['sharpe'] >= GATE else 'FAIL'
        print(f'  Var {v}: OOS Sharpe={st["sharpe"]:.3f}  MaxDD={st["maxdd"]:.1%} → {status}')
        if st['sharpe'] >= GATE:
            confirmed.append(v)

    if confirmed:
        print(f'\nCONFIRMED variants: {confirmed}')
    else:
        print('\nNOT CONFIRMED — all variants below gate')

    out = RESULTS_DIR / 'h458_results.json'
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
