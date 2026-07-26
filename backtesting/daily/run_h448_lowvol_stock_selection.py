#!/usr/bin/env python3
"""
H448 — Low-Volatility Stock Anomaly on H198 Universe

Motivation: Ang, Hodrick, Xing & Zhang (2006) JF show that stocks with LOW
idiosyncratic volatility earn HIGHER subsequent returns — the low-vol anomaly.
H113 tested at the ETF level (NOT CONFIRMED — degenerates to T-bills).
H198 uses momentum on 30 large-cap NASDAQ stocks. H448 tests the pure low-vol
signal (no momentum) on the same universe, and blends with H198 momentum.

Baker, Bradley & Wurgler (2011) FAJ: institutional constraints + benchmark
hugging causes investors to overpay for high-vol/high-beta stocks → low-vol
stocks are underpriced → low-vol premium.

In the H198 universe (tech mega-caps), vol dispersion may be higher than in
H291/H336 (where ALL stocks were near 52w highs). High-vol = speculative
names (TSLA, AMD when volatile); Low-vol = compounders (MSFT, AAPL, COST).

Variants:
  A: Pure low-vol top-6 (sort by ascending 20-day realized vol, take bottom-6)
  B: Pure low-vol top-6, using 60-day window
  C: Momentum × Low-Vol dual rank (0.5 mom + 0.5 inv_vol, normalized ranks)
  D: Momentum with low-vol filter (top-6 momentum → filter to lowest-3 vol)
  E: H198 baseline (6-1m momentum, top-6 EW)
  F: High-vol top-6 (sanity check — should lose)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 momentum baseline)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY = 'H448'
UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
DATA_START  = '2012-01-01'
IS_START    = '2013-01-01'
IS_END      = '2020-12-31'
OOS_START   = '2021-01-01'
OOS_END     = '2026-07-21'

N_POSITIONS     = 6
VOL_WINDOW_20   = 20    # short realized vol window (trading days)
VOL_WINDOW_60   = 60    # longer realized vol window
MOM_FORMATION   = 6     # momentum formation months
MOM_SKIP        = 1     # skip most recent month (standard)

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f"Downloading data for {len(UNIVERSE)} stocks...")
    daily = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                        auto_adjust=True, progress=False)['Close']
    daily = daily.dropna(how='all').ffill()
    return daily


def compute_monthly_signals(daily: pd.DataFrame) -> dict:
    """Compute all monthly signals — all shifted to avoid look-ahead."""
    monthly = daily.resample('MS').first()
    monthly_ret = monthly.pct_change().shift(-1)  # next-month return

    signals = {}

    # 6-1m momentum (skip-1)
    r6 = monthly.pct_change(MOM_FORMATION)
    r1 = monthly.pct_change(MOM_SKIP)
    signals['mom'] = (r6 - r1).shift(1)  # shift to avoid look-ahead

    # 20-day realized vol at each month-start (annualized)
    vol20 = daily.pct_change().rolling(VOL_WINDOW_20).std() * np.sqrt(252)
    vol20_monthly = vol20.resample('MS').last().shift(1)
    signals['vol20'] = vol20_monthly

    # 60-day realized vol
    vol60 = daily.pct_change().rolling(VOL_WINDOW_60).std() * np.sqrt(252)
    vol60_monthly = vol60.resample('MS').last().shift(1)
    signals['vol60'] = vol60_monthly

    return monthly, monthly_ret, signals


def run_backtest(monthly_ret: pd.DataFrame, signals: dict) -> dict:
    mom    = signals['mom']
    vol20  = signals['vol20']
    vol60  = signals['vol60']
    inv_vol20 = 1.0 / vol20.replace(0, np.nan)

    all_dates = monthly_ret.index
    results = {}

    for var in ['A', 'B', 'C', 'D', 'E', 'F']:
        rets = []
        dates = []

        for dt in all_dates:
            if dt not in mom.index:
                continue
            m_row   = mom.loc[dt].dropna()
            v20_row = vol20.loc[dt].dropna() if dt in vol20.index else pd.Series(dtype=float)
            v60_row = vol60.loc[dt].dropna() if dt in vol60.index else pd.Series(dtype=float)
            iv_row  = inv_vol20.loc[dt].dropna() if dt in inv_vol20.index else pd.Series(dtype=float)
            ret_row = monthly_ret.loc[dt].dropna()

            common = m_row.index.intersection(v20_row.index).intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            m_vals   = m_row[common]
            v20_vals = v20_row[common]
            v60_vals = v60_row.reindex(common)
            iv_vals  = iv_row.reindex(common)

            if var == 'A':
                # Pure low-vol 20d: sort ascending vol, take N_POSITIONS with lowest vol
                if v20_vals.isna().all():
                    continue
                selected = v20_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index

            elif var == 'B':
                # Pure low-vol 60d
                if v60_vals.isna().all():
                    continue
                selected = v60_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index

            elif var == 'C':
                # Dual rank: normalized momentum + normalized inv_vol
                m_rank  = m_vals.rank(pct=True)
                iv_rank = iv_vals.rank(pct=True)
                common2 = m_rank.index.intersection(iv_rank.dropna().index)
                if len(common2) < N_POSITIONS:
                    continue
                composite = 0.5 * m_rank[common2] + 0.5 * iv_rank[common2]
                selected = composite.sort_values(ascending=False).head(N_POSITIONS).index

            elif var == 'D':
                # Top-6 momentum → keep the 3 with lowest vol
                top_mom = m_vals.sort_values(ascending=False).head(N_POSITIONS)
                sub_vol = v20_vals.reindex(top_mom.index).dropna()
                if len(sub_vol) < 3:
                    selected = top_mom.index
                else:
                    selected = sub_vol.sort_values(ascending=True).head(3).index

            elif var == 'E':
                # H198 baseline: top-6 momentum
                selected = m_vals.sort_values(ascending=False).head(N_POSITIONS).index

            else:  # F — sanity check: highest vol (should lose)
                if v20_vals.isna().all():
                    continue
                selected = v20_vals.dropna().sort_values(ascending=False).head(N_POSITIONS).index

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
    ann = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg = int((ann < 0).sum())
    print(f"  {label:40s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}")
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f"=== {STRATEGY} Low-Volatility Stock Anomaly on H198 Universe ===")
    print(f"IS: {IS_START}–{IS_END} | OOS: {OOS_START}–{OOS_END}")
    print(f"Gate: OOS Sharpe > 1.174 (H198 baseline)")
    print()

    daily = download_data()
    monthly, monthly_ret, signals = compute_monthly_signals(daily)

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
        mask = (s.index >= OOS_START) & (s.index <= OOS_END)
        oos_stats[v] = evaluate(s, mask, f"OOS Var{v}")

    gate = 1.174
    print(f"\n=== Gate Check (OOS Sharpe > {gate}) ===")
    confirmed = []
    for v in results:
        sh = oos_stats[v]['sharpe']
        status = 'PASS' if sh > gate else 'FAIL'
        print(f"  Var {v}: {sh:.3f} [{status}]")
        if sh > gate:
            confirmed.append(v)

    baseline_sh = oos_stats['E']['sharpe']
    best_var    = max(oos_stats, key=lambda v: oos_stats[v]['sharpe'])
    best_sh     = oos_stats[best_var]['sharpe']
    verdict     = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'

    print(f"\nBaseline H198 (Var E): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")
    if confirmed:
        print(f"Confirmed variants: {confirmed}")
    if best_sh > baseline_sh:
        print("→ Low-vol signal ADDS VALUE vs H198 momentum baseline")
    else:
        print("→ Low-vol signal does NOT add value vs H198 momentum baseline")

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': gate,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'best_variant': best_var,
        'best_oos_sharpe': best_sh,
        'baseline_oos_sharpe': baseline_sh,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h448_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")


if __name__ == '__main__':
    main()
