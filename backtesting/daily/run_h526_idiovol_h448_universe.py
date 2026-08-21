#!/usr/bin/env python3
"""
H526 — Idiosyncratic-Volatility Low-Vol Anomaly on H448's Universe

Motivation: Ang, Hodrick, Xing & Zhang (2006) JF define the low-vol anomaly
signal as IDIOSYNCRATIC volatility — the standard deviation of residuals from
a market-model (CAPM) regression — not total realized volatility. H448 tested
total realized vol (raw rolling std of returns) and came close to the gate but
failed (best OOS Sharpe 1.045 vs gate 1.174). Total vol conflates market beta
with idiosyncratic risk; on a mega-cap tech universe, high-beta stocks (NVDA,
TSLA) also happen to have real idiosyncratic risk, so a total-vol filter may
be accidentally screening on beta as much as on the anomaly's actual driver.

H526 reconstructs the original Ang et al. signal: for each stock, regress
trailing 12m of monthly returns on SPY (CAPM one-factor), take the residual
std (idiosyncratic vol). Low-vol anomaly predicts low RESIDUAL vol stocks
outperform, independent of their beta.

Universe: identical to H448 (30-stock tech-heavy mega-cap set) for direct
comparability of idio-vol vs H448's total-vol result.

Variants:
  A: Pure idio-vol top-6 (12m trailing residual std, bottom-6)
  B: Pure idio-vol top-6, 24m trailing window (more stable beta estimate)
  C: Idio-vol x momentum dual rank (0.5 mom + 0.5 inv_idiovol)
  D: Top-6 momentum -> filter to lowest-3 idio-vol
  E: H448/H198 baseline (6-1m momentum, top-6 EW)
  F: Sanity check: high idio-vol top-6 (should lose)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (same gate H448 used)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY = 'H526'
UNIVERSE = [
    'AAPL', 'MSFT', 'NVDA', 'AMZN', 'GOOGL', 'META', 'TSLA', 'AVGO',
    'COST', 'NFLX', 'AMD', 'QCOM', 'ADBE', 'INTU', 'CSCO', 'TXN',
    'AMAT', 'MU', 'LRCX', 'KLAC', 'PANW', 'CDNS', 'SNPS', 'MRVL',
    'FTNT', 'CRWD', 'WDAY', 'DXCM', 'TEAM', 'ZS'
]
BENCHMARK = 'SPY'
DATA_START  = '2011-01-01'   # need 24m history before IS start for Var B
IS_START    = pd.Timestamp('2013-01-01')
IS_END      = pd.Timestamp('2020-12-31')
OOS_START   = pd.Timestamp('2021-01-01')
OOS_END     = '2026-07-21'

N_POSITIONS   = 6
MOM_FORMATION = 6
MOM_SKIP      = 1
IDIO_WIN_12   = 12
IDIO_WIN_24   = 24
GATE = 1.174

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    tickers = UNIVERSE + [BENCHMARK]
    print(f"Downloading data for {len(tickers)} tickers...")
    daily = yf.download(tickers, start=DATA_START, end=OOS_END,
                        auto_adjust=True, progress=False)['Close']
    daily = daily.dropna(how='all').ffill()
    return daily


def rolling_idio_vol(stock_ret: pd.Series, mkt_ret: pd.Series, window: int) -> pd.Series:
    """Rolling CAPM residual std: for each window, OLS beta of stock on market,
    residual std of that window. Vectorized via rolling covariance/variance."""
    cov = stock_ret.rolling(window).cov(mkt_ret)
    var = mkt_ret.rolling(window).var()
    beta = cov / var.replace(0, np.nan)
    # residual variance = var(stock) - beta^2 * var(mkt)  (single-factor decomposition)
    var_stock = stock_ret.rolling(window).var()
    resid_var = (var_stock - (beta ** 2) * var).clip(lower=0)
    idio_vol = np.sqrt(resid_var) * np.sqrt(12)  # annualize (monthly returns)
    return idio_vol


def compute_monthly_signals(daily: pd.DataFrame):
    monthly = daily.resample('MS').first()
    monthly_ret_all = monthly.pct_change()
    monthly_ret = monthly_ret_all[UNIVERSE].shift(-1)  # next-month forward return

    mkt_ret = monthly_ret_all[BENCHMARK]

    r6 = monthly[UNIVERSE].pct_change(MOM_FORMATION)
    r1 = monthly[UNIVERSE].pct_change(MOM_SKIP)
    mom = (r6 - r1).shift(1)

    idio12 = pd.DataFrame({t: rolling_idio_vol(monthly_ret_all[t], mkt_ret, IDIO_WIN_12)
                            for t in UNIVERSE}).shift(1)
    idio24 = pd.DataFrame({t: rolling_idio_vol(monthly_ret_all[t], mkt_ret, IDIO_WIN_24)
                            for t in UNIVERSE}).shift(1)
    inv_idio12 = 1.0 / idio12.replace(0, np.nan)

    return monthly_ret, {'mom': mom, 'idio12': idio12, 'idio24': idio24, 'inv_idio12': inv_idio12}


def run_backtest(monthly_ret, signals):
    mom = signals['mom']
    idio12 = signals['idio12']
    idio24 = signals['idio24']
    inv_idio12 = signals['inv_idio12']

    results = {}
    for var in ['A', 'B', 'C', 'D', 'E', 'F']:
        rets, dates = [], []
        for dt in monthly_ret.index:
            if dt not in mom.index:
                continue
            m_row = mom.loc[dt].dropna()
            i12_row = idio12.loc[dt].dropna() if dt in idio12.index else pd.Series(dtype=float)
            i24_row = idio24.loc[dt].dropna() if dt in idio24.index else pd.Series(dtype=float)
            iv_row = inv_idio12.loc[dt].dropna() if dt in inv_idio12.index else pd.Series(dtype=float)
            ret_row = monthly_ret.loc[dt].dropna()

            common = m_row.index.intersection(i12_row.index).intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            m_vals = m_row[common]
            i12_vals = i12_row[common]
            i24_vals = i24_row.reindex(common)
            iv_vals = iv_row.reindex(common)

            if var == 'A':
                if i12_vals.isna().all():
                    continue
                selected = i12_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index
            elif var == 'B':
                if i24_vals.isna().all():
                    continue
                selected = i24_vals.dropna().sort_values(ascending=True).head(N_POSITIONS).index
            elif var == 'C':
                m_rank = m_vals.rank(pct=True)
                iv_rank = iv_vals.rank(pct=True)
                common2 = m_rank.index.intersection(iv_rank.dropna().index)
                if len(common2) < N_POSITIONS:
                    continue
                composite = 0.5 * m_rank[common2] + 0.5 * iv_rank[common2]
                selected = composite.sort_values(ascending=False).head(N_POSITIONS).index
            elif var == 'D':
                top_mom = m_vals.sort_values(ascending=False).head(N_POSITIONS)
                sub_vol = i12_vals.reindex(top_mom.index).dropna()
                if len(sub_vol) < 3:
                    selected = top_mom.index
                else:
                    selected = sub_vol.sort_values(ascending=True).head(3).index
            elif var == 'E':
                selected = m_vals.sort_values(ascending=False).head(N_POSITIONS).index
            else:  # F
                if i12_vals.isna().all():
                    continue
                selected = i12_vals.dropna().sort_values(ascending=False).head(N_POSITIONS).index

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
    print(f"=== {STRATEGY} Idiosyncratic-Vol Low-Vol Anomaly on H448 Universe ===")
    print(f"IS: {IS_START.date()}-{IS_END.date()} | OOS: {OOS_START.date()}-present")
    print(f"Gate: OOS Sharpe > {GATE} (H448/H198 baseline)")
    print()

    daily = download_data()
    monthly_ret, signals = compute_monthly_signals(daily)
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

    print(f"\n=== Gate Check (OOS Sharpe > {GATE}) ===")
    confirmed = []
    for v in results:
        sh = oos_stats[v]['sharpe']
        status = 'PASS' if sh > GATE else 'FAIL'
        print(f"  Var {v}: {sh:.3f} [{status}]")
        if sh > GATE:
            confirmed.append(v)

    baseline_sh = oos_stats['E']['sharpe']
    best_var = max(oos_stats, key=lambda v: oos_stats[v]['sharpe'])
    best_sh = oos_stats[best_var]['sharpe']
    verdict = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'

    print(f"\nBaseline (Var E, momentum): OOS Sharpe {baseline_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"vs H448 total-vol best (Var B, 60d): OOS Sharpe 1.045")
    print(f"\nVERDICT: {verdict}")

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': GATE,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'best_variant': best_var,
        'best_oos_sharpe': best_sh,
        'baseline_oos_sharpe': baseline_sh,
        'h448_total_vol_best_oos_sharpe': 1.045,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h526_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")


if __name__ == '__main__':
    main()
