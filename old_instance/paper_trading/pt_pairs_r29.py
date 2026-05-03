#!/usr/bin/env python3
"""
Pairs Portfolio Paper Trader — R29 Factor Residualization
Key improvement over R23: factor residualize returns (SPY + sector ETF) before
computing z-score spread. This reveals cointegration hidden by common factors.

Best pairs from R29 backtest (2020-2025):
  MSFT/TXN (Sharpe 0.79), TXN/META (0.74), AMZN/TSLA (0.73),
  NVDA/META (0.68), NVDA/TXN, GOOGL/META, XOM/CVX, JPM/GS, MSFT/GOOGL

R29 v1 portfolio Sharpe: 1.3802 (vs R23 baseline 0.964)
Entry ±2.0σ, Exit ±0.5σ, Stop ±4.0σ  (fixed thresholds beat OU-calibrated per R29)
Run daily at 4:35 PM CT.
"""

import sys, json, argparse
from datetime import date
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')
try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'yfinance', 'pandas', 'numpy',
                    '--target=/tmp/eval_deps', '--quiet'])
    import yfinance as yf
    import pandas as pd
    import numpy as np

PORTFOLIO_FILE  = Path(__file__).parent / 'pairs_r29_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 500.0   # $500 per leg (each pair = $1,000 total notional)
Z_ENTRY         = 2.0     # R29 uses ±2.0 (wider than R23's ±1.5)
Z_EXIT          = 0.5
Z_STOP          = 4.0
LOOKBACK        = 60      # days for rolling z-score

# (stock_a, stock_b, sector_etf_a, sector_etf_b)
# Sector ETFs: XLK=tech, XLC=comms, XLY=consumer_disc, XLF=financials, XLE=energy
PAIRS = [
    ('MSFT',  'TXN',   'XLK', 'XLK'),   # tech/tech
    ('TXN',   'META',  'XLK', 'XLC'),   # tech/comms
    ('AMZN',  'TSLA',  'XLY', 'XLY'),   # consumer_d/consumer_d
    ('NVDA',  'META',  'XLK', 'XLC'),   # tech/comms
    ('NVDA',  'TXN',   'XLK', 'XLK'),   # tech/tech
    ('GOOGL', 'META',  'XLC', 'XLC'),   # comms/comms
    ('XOM',   'CVX',   'XLE', 'XLE'),   # energy/energy
    ('JPM',   'GS',    'XLF', 'XLF'),   # financials/financials
    ('MSFT',  'GOOGL', 'XLK', 'XLC'),   # tech/comms
    ('AMZN',  'GOOGL', 'XLY', 'XLC'),   # consumer_d/comms
]

ALL_TICKERS = list({sym for p in PAIRS for sym in (p[0], p[1], p[2], p[3])})


def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f:
            return json.load(f)
    return {
        'strategy': 'Pairs Portfolio R29 (Factor Residualized)',
        'backtest_sharpe': 1.3802,
        'methodology': 'R29 v1: OLS residualization on SPY + sector ETF, fixed ±2σ z-score',
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},   # pair_key → position dict
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None,
    }


def save(data: dict):
    with open(PORTFOLIO_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def pair_key(a: str, b: str) -> str:
    return f"{a}/{b}"


def residualize(returns: pd.Series, spy_ret: pd.Series, sector_ret: pd.Series) -> pd.Series:
    """
    OLS: r_stock = alpha + beta_mkt * r_spy + beta_sector * r_sector + epsilon
    Returns the residual epsilon (factor-neutral return).
    """
    common = returns.index.intersection(spy_ret.index).intersection(sector_ret.index)
    if len(common) < 30:
        return returns  # not enough data — fall back to raw returns

    r   = returns[common].values
    s   = spy_ret[common].values
    sec = sector_ret[common].values

    X = np.column_stack([np.ones(len(r)), s, sec])
    try:
        beta, _, _, _ = np.linalg.lstsq(X, r, rcond=None)
        resid = r - X @ beta
    except Exception:
        resid = r  # fallback

    return pd.Series(resid, index=common)


def compute_zscore(resid_a: pd.Series, resid_b: pd.Series) -> tuple:
    """
    Compute z-score of the cumulative-residual spread.
    Returns (z, spread_value, mean, std).
    """
    # Cumulative residuals approximate the cointegrated log-price spread
    cum_a = resid_a.cumsum()
    cum_b = resid_b.cumsum()
    spread = cum_a - cum_b

    if len(spread) < LOOKBACK:
        return 0.0, 0.0, 0.0, 0.0

    rolling_mean = spread.rolling(LOOKBACK).mean().iloc[-1]
    rolling_std  = spread.rolling(LOOKBACK).std().iloc[-1]

    if rolling_std == 0 or np.isnan(rolling_std):
        return 0.0, float(spread.iloc[-1]), float(rolling_mean), 0.0

    z = (spread.iloc[-1] - rolling_mean) / rolling_std
    return float(z), float(spread.iloc[-1]), float(rolling_mean), float(rolling_std)


def run():
    data  = load()
    today = str(date.today())

    if date.today().weekday() >= 5:
        print(f"Weekend, skipping ({today})")
        return data

    print(f"\n=== Pairs Portfolio R29 — {today} ===")

    # ── Fetch all price data at once ──────────────────────────────────────────
    period = f'{LOOKBACK + 20}d'
    try:
        raw = yf.download(ALL_TICKERS, period=period, interval='1d',
                          progress=False, auto_adjust=True)
        if raw.empty:
            print("  No data returned"); return data
        closes = raw['Close'] if 'Close' in raw else raw.xs('Close', axis=1, level=0)
    except Exception as e:
        print(f"  Download failed: {e}"); return data

    # SPY returns for factor model
    try:
        spy_raw   = yf.download('SPY', period=period, progress=False, auto_adjust=True)
        spy_close = spy_raw['Close'].squeeze()
        spy_ret   = spy_close.pct_change().dropna()
    except Exception:
        spy_ret = pd.Series(dtype=float)

    # ── Process each pair ─────────────────────────────────────────────────────
    for sym_a, sym_b, etf_a, etf_b in PAIRS:
        key = pair_key(sym_a, sym_b)

        try:
            close_a = closes[sym_a].dropna()
            close_b = closes[sym_b].dropna()
            common  = close_a.index.intersection(close_b.index)
            if len(common) < LOOKBACK + 5:
                print(f"  {key}: insufficient data ({len(common)} days)"); continue

            close_a = close_a[common]
            close_b = close_b[common]
            ret_a   = close_a.pct_change().dropna()
            ret_b   = close_b.pct_change().dropna()

            # Sector ETF returns for residualization
            sec_a_ret = closes[etf_a].pct_change().dropna() if etf_a in closes.columns else pd.Series(dtype=float)
            sec_b_ret = closes[etf_b].pct_change().dropna() if etf_b in closes.columns else pd.Series(dtype=float)

            # Residualize each stock's returns
            resid_a = residualize(ret_a, spy_ret, sec_a_ret)
            resid_b = residualize(ret_b, spy_ret, sec_b_ret)

            z, spread, mean_s, std_s = compute_zscore(resid_a, resid_b)

            p_a = float(close_a.iloc[-1])
            p_b = float(close_b.iloc[-1])

        except Exception as e:
            print(f"  {key}: error — {e}"); continue

        in_pos    = key in data['open_positions']
        pos       = data['open_positions'].get(key, {})
        direction = pos.get('direction')

        # ── Entry ─────────────────────────────────────────────────────────────
        if not in_pos:
            if z > Z_ENTRY:
                # Spread high → short spread (short A, long B)
                data['open_positions'][key] = {
                    'sym_a': sym_a, 'sym_b': sym_b,
                    'direction': 'short_spread',
                    'entry_z': round(z, 3), 'entry_date': today,
                    'entry_p_a': p_a, 'entry_p_b': p_b,
                    'shares_a': POSITION_SIZE / p_a,
                    'shares_b': POSITION_SIZE / p_b,
                    'etf_a': etf_a, 'etf_b': etf_b,
                }
                print(f"  ENTER {key}: z={z:.2f} → SHORT spread (short {sym_a}, long {sym_b})")
            elif z < -Z_ENTRY:
                # Spread low → long spread (long A, short B)
                data['open_positions'][key] = {
                    'sym_a': sym_a, 'sym_b': sym_b,
                    'direction': 'long_spread',
                    'entry_z': round(z, 3), 'entry_date': today,
                    'entry_p_a': p_a, 'entry_p_b': p_b,
                    'shares_a': POSITION_SIZE / p_a,
                    'shares_b': POSITION_SIZE / p_b,
                    'etf_a': etf_a, 'etf_b': etf_b,
                }
                print(f"  ENTER {key}: z={z:.2f} → LONG spread (long {sym_a}, short {sym_b})")
            else:
                print(f"  {key}: z={z:.2f}  neutral")

        # ── Exit ──────────────────────────────────────────────────────────────
        else:
            exit_signal = False
            stop_hit    = abs(z) > Z_STOP

            if direction == 'short_spread' and z < Z_EXIT:   exit_signal = True
            if direction == 'long_spread'  and z > -Z_EXIT:  exit_signal = True

            if exit_signal or stop_hit:
                if direction == 'short_spread':
                    pnl = (pos['entry_p_a'] - p_a) * pos['shares_a'] + \
                          (p_b - pos['entry_p_b']) * pos['shares_b']
                else:
                    pnl = (p_a - pos['entry_p_a']) * pos['shares_a'] + \
                          (pos['entry_p_b'] - p_b) * pos['shares_b']

                win    = pnl > 0
                reason = 'stop' if stop_hit else 'target'
                data['trades'].append({
                    'pair': key, 'direction': direction,
                    'entry_date': pos['entry_date'], 'exit_date': today,
                    'entry_z': pos['entry_z'], 'exit_z': round(z, 3),
                    'pnl_usd': round(pnl, 2), 'win': win, 'exit_reason': reason,
                })
                data['stats']['n_trades'] += 1
                data['stats']['total_pnl'] += pnl
                if win: data['stats']['wins'] += 1
                del data['open_positions'][key]
                tag = '🛑 STOP' if stop_hit else '✅ EXIT'
                print(f"  {key}: z={z:.2f} → {tag}  P&L=${pnl:+.2f}  {'WIN' if win else 'LOSS'}")
            else:
                # Mark-to-market unrealized
                if direction == 'short_spread':
                    unreal = (pos['entry_p_a'] - p_a) * pos['shares_a'] + \
                             (p_b - pos['entry_p_b']) * pos['shares_b']
                else:
                    unreal = (p_a - pos['entry_p_a']) * pos['shares_a'] + \
                             (pos['entry_p_b'] - p_b) * pos['shares_b']
                print(f"  {key}: z={z:.2f}  {direction}  unreal=${unreal:+.2f}")

    data['last_update'] = today
    save(data)

    # ── Summary ───────────────────────────────────────────────────────────────
    stats = data['stats']
    wr    = stats['wins'] / stats['n_trades'] * 100 if stats['n_trades'] > 0 else 0
    open_unreal = 0.0  # already printed per-pair above
    print(f"\n  Open positions: {len(data['open_positions'])}/{len(PAIRS)}")
    print(f"  Realized P&L:  ${stats['total_pnl']:+.2f}")
    print(f"  Win rate: {wr:.0f}% ({stats['wins']}/{stats['n_trades']} trades)")
    print(f"  Portfolio value: ${VIRTUAL_CAPITAL + stats['total_pnl']:,.2f}")

    return data


if __name__ == '__main__':
    run()
