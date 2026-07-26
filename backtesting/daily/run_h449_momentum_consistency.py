#!/usr/bin/env python3
"""
H449 — Momentum Consistency (Risk-Adjusted Momentum) on H198 Universe

Motivation: Standard 6-1m momentum treats all positive-momentum stocks equally
regardless of HOW they got there. A stock that rose steadily every month is very
different from one that had one giant month and was flat otherwise.

"Consistent momentum" = high return relative to return variance → Sharpe ratio
over the formation window. This is related to IMOM (H376/H385 confirmed) but
captures a complementary dimension: not just compounding vs arithmetic gap, but
the consistency of the upward path itself.

Empirical basis:
- Bandarchuk & Hilscher (2013): momentum profits concentrated in low-dispersion
  stocks (stocks with consistent return over formation period)
- Rachwalski & Wen (2016): momentum scaled by idiosyncratic volatility (IVOL)
  identifies more persistent winners

The H198 universe (30 large-cap NASDAQ stocks) has high cross-sectional
variation in return consistency: MSFT/AAPL trend slowly, TSLA/AMD have huge
swings. A consistency-adjusted momentum signal may identify more durable winners.

Variants:
  A: Pure Sharpe-momentum: 6m cum return / rolling_std(monthly returns, 6m), top-6
  B: Dual rank: 0.5 × mom_rank + 0.5 × sharpe_rank, top-6
  C: Momentum + consistency filter: top-12 by 6m momentum → sort by Sharpe, take top-6
  D: Max drawdown-adjusted momentum: 6m cum return / (1 + max_drawdown_6m), top-6
  E: H198 baseline: 6-1m momentum top-6 equal-weight
  F: Low-consistency momentum (highest vol winners): sanity check, top-6 by mom,
     re-sorted to keep HIGHEST 6m vol among top-12 (should lose in OOS)

IS: 2013-2020, OOS: 2021-2026
Gate: OOS Sharpe > 1.174 (H198 momentum baseline, H198 confirmed)
"""

import json
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings('ignore')

STRATEGY = 'H449'
UNIVERSE = [
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

N_POSITIONS   = 6
N_POOL        = 12    # wider pool for filter variants
FORM_MONTHS   = 6
SKIP_MONTHS   = 1
ROLL_MONTHS   = 6     # rolling window for Sharpe/std computation

RESULTS_DIR = Path('/workspace/agent/backtesting/results')
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def download_data():
    print(f"Downloading {len(UNIVERSE)} stocks...")
    raw = yf.download(UNIVERSE, start=DATA_START, end=OOS_END,
                      auto_adjust=True, progress=False)['Close']
    return raw.dropna(how='all').ffill()


def compute_signals(daily: pd.DataFrame) -> tuple:
    """Compute monthly signals with look-ahead prevention."""
    monthly = daily.resample('MS').first()
    monthly_ret_raw = monthly.pct_change()           # raw single-period returns
    monthly_ret_fwd = monthly_ret_raw.shift(-1)       # forward returns (target)

    # 6-1m momentum (shift 1 to prevent look-ahead)
    r6 = monthly.pct_change(FORM_MONTHS)
    r1 = monthly.pct_change(SKIP_MONTHS)
    mom6m = (r6 - r1).shift(1)

    # Rolling 6m monthly return std (consistency inverse signal)
    # std of the last 6 monthly returns, shifted to avoid look-ahead
    roll_std = monthly_ret_raw.rolling(ROLL_MONTHS).std().shift(1)

    # Rolling 6m Sharpe: cumulative 6m return / std of monthly returns
    roll_sharpe = mom6m / roll_std.replace(0, np.nan)

    # Rolling 6m max drawdown within monthly prices
    def rolling_maxdd(ser, n=ROLL_MONTHS):
        result = pd.Series(index=ser.index, dtype=float)
        for i in range(n, len(ser)):
            window = ser.iloc[i-n:i]
            cum = window.cumprod()
            dd = (cum / cum.cummax() - 1).min()
            result.iloc[i] = dd
        return result

    # Compute max drawdown adjusted (drawdown of 1+monthly returns over 6m)
    cum_ret_6m = (1 + monthly_ret_raw).rolling(ROLL_MONTHS).apply(lambda x: x.prod(), raw=True) - 1
    # Max drawdown of monthly cum path over 6m rolling
    # Approximate: 6m total return / (1 + abs(worst month in window))
    worst_month = monthly_ret_raw.rolling(ROLL_MONTHS).min().shift(1)
    dd_adj_mom  = mom6m / (1 + worst_month.abs().replace(0, np.nan))

    # Rolling vol (20d) for daily realized vol at month-start
    daily_vol = daily.pct_change().rolling(20).std() * np.sqrt(252)
    daily_vol_monthly = daily_vol.resample('MS').last().shift(1)

    return {
        'monthly_ret_fwd': monthly_ret_fwd,
        'mom6m':           mom6m,
        'roll_std':        roll_std,
        'roll_sharpe':     roll_sharpe,
        'dd_adj_mom':      dd_adj_mom,
        'daily_vol_20':    daily_vol_monthly,
    }


def run_backtest(signals: dict) -> dict:
    fwd_ret     = signals['monthly_ret_fwd']
    mom6m       = signals['mom6m']
    roll_sharpe = signals['roll_sharpe']
    roll_std    = signals['roll_std']
    dd_adj_mom  = signals['dd_adj_mom']
    daily_vol   = signals['daily_vol_20']

    results = {}

    for var in ['A', 'B', 'C', 'D', 'E', 'F']:
        rets, dates = [], []

        for dt in fwd_ret.index:
            # Require all signals to have data
            if dt not in mom6m.index:
                continue

            m_row  = mom6m.loc[dt].dropna()
            sh_row = roll_sharpe.loc[dt].dropna() if dt in roll_sharpe.index else pd.Series(dtype=float)
            std_row = roll_std.loc[dt].dropna()   if dt in roll_std.index   else pd.Series(dtype=float)
            dd_row  = dd_adj_mom.loc[dt].dropna() if dt in dd_adj_mom.index  else pd.Series(dtype=float)
            ret_row = fwd_ret.loc[dt].dropna()
            vol_row = daily_vol.loc[dt].dropna()  if dt in daily_vol.index   else pd.Series(dtype=float)

            common = m_row.index.intersection(ret_row.index)
            if len(common) < N_POSITIONS:
                continue

            m_vals   = m_row[common]
            sh_vals  = sh_row.reindex(common)
            std_vals = std_row.reindex(common)
            dd_vals  = dd_row.reindex(common)
            vol_vals = vol_row.reindex(common)

            if var == 'A':
                # Pure Sharpe-momentum
                valid = sh_vals.dropna()
                if len(valid) < N_POSITIONS:
                    continue
                selected = valid.sort_values(ascending=False).head(N_POSITIONS).index

            elif var == 'B':
                # Dual rank: 0.5 × mom + 0.5 × sharpe
                m_rank  = m_vals.rank(pct=True)
                sh_rank = sh_vals.dropna().rank(pct=True)
                c2 = m_rank.index.intersection(sh_rank.index)
                if len(c2) < N_POSITIONS:
                    continue
                composite = 0.5 * m_rank[c2] + 0.5 * sh_rank[c2]
                selected = composite.sort_values(ascending=False).head(N_POSITIONS).index

            elif var == 'C':
                # Top-12 by momentum → filter to top-6 by Sharpe
                top12_idx = m_vals.sort_values(ascending=False).head(N_POOL).index
                sub_sh = sh_vals.reindex(top12_idx).dropna()
                if len(sub_sh) < N_POSITIONS:
                    selected = top12_idx[:N_POSITIONS]
                else:
                    selected = sub_sh.sort_values(ascending=False).head(N_POSITIONS).index

            elif var == 'D':
                # Max-drawdown-adjusted momentum
                valid = dd_vals.dropna()
                if len(valid) < N_POSITIONS:
                    continue
                selected = valid.sort_values(ascending=False).head(N_POSITIONS).index

            elif var == 'E':
                # H198 baseline: top-6 by 6-1m momentum
                selected = m_vals.sort_values(ascending=False).head(N_POSITIONS).index

            else:  # F — sanity check: top-12 mom → highest volatility 6 (should lose)
                top12_idx = m_vals.sort_values(ascending=False).head(N_POOL).index
                sub_vol = vol_vals.reindex(top12_idx).dropna()
                if len(sub_vol) < N_POSITIONS:
                    selected = top12_idx[:N_POSITIONS]
                else:
                    selected = sub_vol.sort_values(ascending=False).head(N_POSITIONS).index

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
    cum    = (1 + r).cumprod()
    n_yrs  = len(r) / 12
    cagr   = cum.iloc[-1] ** (1 / max(n_yrs, 1e-6)) - 1
    maxdd  = (cum / cum.cummax() - 1).min()
    ann    = r.resample('YE').apply(lambda x: (1 + x).prod() - 1)
    neg    = int((ann < 0).sum())
    print(f"  {label:40s}  Sharpe={sharpe:.3f}  CAGR={cagr:.1%}  MaxDD={maxdd:.1%}  NegYrs={neg}")
    return {'sharpe': round(sharpe, 3), 'cagr': round(cagr, 3),
            'maxdd': round(maxdd, 3), 'neg_years': neg}


def main():
    print(f"=== {STRATEGY} Momentum Consistency (Risk-Adjusted Momentum) on H198 ===")
    print(f"IS: {IS_START}–{IS_END} | OOS: {OOS_START}–{OOS_END}")
    print(f"Gate: OOS Sharpe > 1.174 (H198 baseline)")
    print()

    daily = download_data()
    signals = compute_signals(daily)
    results = run_backtest(signals)

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

    base_sh  = oos_stats['E']['sharpe']
    best_var = max(oos_stats, key=lambda v: oos_stats[v]['sharpe'])
    best_sh  = oos_stats[best_var]['sharpe']
    verdict  = 'CONFIRMED' if confirmed else 'NOT CONFIRMED'

    print(f"\nBaseline H198 (Var E): OOS Sharpe {base_sh:.3f}")
    print(f"Best (Var {best_var}): OOS Sharpe {best_sh:.3f}")
    print(f"\nVERDICT: {verdict}")
    if confirmed:
        print(f"Confirmed variants: {confirmed}")
    if best_sh > base_sh:
        print("→ Momentum consistency ADDS VALUE vs H198 baseline")
    else:
        print("→ Momentum consistency does NOT add value vs H198 baseline")

    output = {
        'strategy': STRATEGY,
        'run_date': datetime.now().isoformat(),
        'gate_oos_sharpe': gate,
        'verdict': verdict,
        'confirmed_variants': confirmed,
        'best_variant': best_var,
        'best_oos_sharpe': best_sh,
        'baseline_oos_sharpe': base_sh,
        'is_stats': is_stats,
        'oos_stats': oos_stats,
    }
    out_path = RESULTS_DIR / 'h449_results.json'
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults: {out_path}")


if __name__ == '__main__':
    main()
