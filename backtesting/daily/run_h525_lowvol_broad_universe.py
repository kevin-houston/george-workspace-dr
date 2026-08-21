#!/usr/bin/env python3
"""
H525 — Low-Volatility Anomaly on Broader 200-Stock Universe

Motivation: H448 tested Ang/Baker low-vol anomaly on the H198 30-stock
mega-cap tech universe and came close but failed the gate (best OOS Sharpe
1.045 vs gate 1.174), noting: "H448 might confirm on broader universe with
actual cross-sectional vol spread" — the 30-stock universe is concentrated
mega-cap tech, where vol dispersion is compressed relative to a true
market-wide cross-section. H525 tests the same signal construction on
H241's ~200-stock, 11-GICS-sector universe, which has genuine cross-sectional
vol spread (utilities/staples vs. energy/tech).

Reuses H241's cached monthly price panel (backtesting/cache/h241_monthly_prices.parquet)
to avoid a fresh 200-ticker download.

Variants:
  A: Pure low-vol top-20 (bottom 10% by trailing 12m monthly-return vol)
  B: Pure low-vol top-20, trailing 3m vol (short window)
  C: Momentum x Low-Vol dual rank (0.5 mom_6_1 + 0.5 inv_vol12m, normalized ranks)
  D: Top-40 momentum -> filter to lowest-20 vol
  E: Baseline: top-20 by 6-1m momentum (H241-style, no ML)
  F: Sanity check: high-vol top-20 (should lose)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 momentum baseline, same gate H448 used, for
direct comparability across universe size)
Secondary gate: OOS Sharpe > 1.5 (H241 baseline gate, for comparability within
this universe)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

STRATEGY = 'H525'
WORKSPACE = Path('/workspace/agent')
CACHE = WORKSPACE / 'backtesting' / 'cache' / 'h241_monthly_prices.parquet'
RESULTS_DIR = WORKSPACE / 'backtesting' / 'results'
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

IS_START  = pd.Timestamp('2013-01-01')
IS_END    = pd.Timestamp('2020-12-31')
OOS_START = pd.Timestamp('2021-01-01')

N_POSITIONS = 20   # ~10% of 200-stock universe, comparable concentration to H448's 6/30
MOM_FORMATION = 6
MOM_SKIP = 1
GATE_H198 = 1.174
GATE_H241 = 1.500


def load_prices() -> pd.DataFrame:
    if not CACHE.exists():
        raise SystemExit(f"H241 cache not found at {CACHE} — run run_h241.py first")
    df = pd.read_parquet(CACHE)
    df = df.dropna(axis=1, thresh=int(len(df) * 0.8))  # drop tickers with too much missing history
    print(f"Loaded {df.shape[1]} tickers from H241 cache, {df.shape[0]} months")
    return df


def compute_signals(monthly: pd.DataFrame):
    ret = monthly.pct_change()
    monthly_ret = ret.shift(-1)  # next-month forward return (target)

    r6 = monthly.pct_change(MOM_FORMATION)
    r1 = monthly.pct_change(MOM_SKIP)
    mom = (r6 - r1).shift(1)  # signal known at month t, using data through t-1

    vol12 = ret.rolling(12).std().shift(1) * np.sqrt(12)
    vol3  = ret.rolling(3).std().shift(1) * np.sqrt(12)
    inv_vol12 = 1.0 / vol12.replace(0, np.nan)

    return monthly_ret, {'mom': mom, 'vol12': vol12, 'vol3': vol3, 'inv_vol12': inv_vol12}


def run_backtest(monthly_ret, signals):
    mom = signals['mom']
    vol12 = signals['vol12']
    vol3 = signals['vol3']
    inv_vol12 = signals['inv_vol12']

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E', 'F']:
        rets, dates = [], []
        for dt in monthly_ret.index:
            if dt not in mom.index:
                continue
            m_row = mom.loc[dt].dropna()
            v12_row = vol12.loc[dt].dropna() if dt in vol12.index else pd.Series(dtype=float)
            v3_row = vol3.loc[dt].dropna() if dt in vol3.index else pd.Series(dtype=float)
            iv_row = inv_vol12.loc[dt].dropna() if dt in inv_vol12.index else pd.Series(dtype=float)
            ret_row = monthly_ret.loc[dt].dropna()

            common = m_row.index.intersection(v12_row.index).intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            m_vals = m_row[common]
            v12_vals = v12_row[common]
            v3_vals = v3_row.reindex(common)
            iv_vals = iv_row.reindex(common)

            if var == 'A':
                if v12_vals.isna().all():
                    continue
                selected = v12_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index
            elif var == 'B':
                if v3_vals.isna().all():
                    continue
                selected = v3_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index
            elif var == 'C':
                m_rank = m_vals.rank(pct=True)
                iv_rank = iv_vals.rank(pct=True)
                common2 = m_rank.index.intersection(iv_rank.dropna().index)
                if len(common2) < N_POSITIONS:
                    continue
                composite = 0.5 * m_rank[common2] + 0.5 * iv_rank[common2]
                selected = composite.sort_values(ascending=False).head(N_POSITIONS).index
            elif var == 'D':
                top_mom = m_vals.sort_values(ascending=False).head(N_POSITIONS * 2)
                sub_vol = v12_vals.reindex(top_mom.index).dropna()
                if len(sub_vol) < N_POSITIONS:
                    selected = top_mom.index[:N_POSITIONS]
                else:
                    selected = sub_vol.sort_values(ascending=True).head(N_POSITIONS).index
            elif var == 'E':
                selected = m_vals.sort_values(ascending=False).head(N_POSITIONS).index
            else:  # F
                if v12_vals.isna().all():
                    continue
                selected = v12_vals.dropna().sort_values(ascending=False).head(N_POSITIONS).index

            ret = ret_row.reindex(selected).mean()
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
    n_years = len(r) / 12
    cagr = cum.iloc[-1] ** (1 / max(n_years, 1e-6)) - 1
    maxdd = (cum / cum.cummax() - 1).min()
    ann = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
    neg = int((ann < 0).sum())
    print(f"  {label:40s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}")
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f"=== {STRATEGY} Low-Volatility Anomaly on Broader 200-Stock Universe ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE_H198} (H198 baseline) / secondary > {GATE_H241} (H241 baseline)")
    print()

    monthly = load_prices()
    monthly_ret, signals = compute_signals(monthly)
    results = run_backtest(monthly_ret, signals)

    print("=== IS Results ===")
    is_stats = {}
    for v, s in results.items():
        mask = (s.index >= IS_START) & (s.index <= IS_END)
        is_stats[v] = evaluate(s, mask, f"IS Var{v}")

    print()
    print("=== OOS Results ===")
    oos_stats = {}
    for v, s in results.items():
        mask = (s.index >= OOS_START)
        oos_stats[v] = evaluate(s, mask, f"OOS Var{v}")

    print(f"\n=== Gate Check (OOS Sharpe > {GATE_H198}) ===")
    confirmed = []
    for v in results:
        sh = oos_stats[v]['sharpe']
        status = 'PASS' if sh > GATE_H198 else 'FAIL'
        print(f"  Var {v}: {sh:.3f} [{status}]")
        if sh > GATE_H198:
            confirmed.append(v)

    baseline_sh = oos_stats['E']['sharpe']
    best_var = max(oos_stats, key=lambda v: oos_stats[v]['sharpe'])
    best_sh = oos_stats[best_var]['sharpe']
    verdict = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'

    print(f"\nBaseline (Var E, top-20 momentum): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe_h198': GATE_H198,
        'gate_oos_sharpe_h241': GATE_H241,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'best_variant': best_var,
        'best_oos_sharpe': best_sh,
        'baseline_oos_sharpe': baseline_sh,
        'n_tickers': monthly.shape[1],
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h525_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")


if __name__ == '__main__':
    main()
