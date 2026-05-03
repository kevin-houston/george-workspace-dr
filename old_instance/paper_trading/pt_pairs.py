#!/usr/bin/env python3
"""
Strategy 4: Pairs Portfolio Paper Trader
10-pair equal-weight stat-arb book. 60d rolling z-score.
Entry: |z| > 1.5, Exit: |z| < 0.5, Stop: |z| > 4.0
Run daily at 4:35 PM CT.
"""

import sys, json
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

PORTFOLIO_FILE  = Path(__file__).parent / 'pairs_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 500.0   # $500 per pair leg (each pair = $1,000 total notional)
Z_ENTRY         = 1.5
Z_EXIT          = 0.5
Z_STOP          = 4.0
LOOKBACK        = 60

PAIRS = [
    ('JNJ', 'UNH'),
    ('LMT', 'NOC'),
    ('DE',  'CAT'),
    ('BAC', 'GS'),
    ('BAC', 'WFC'),
    ('JNJ', 'PFE'),
    ('CVX', 'COP'),
    ('COST','PG'),
    ('EWC', 'EWA'),   # Canada/Australia international pair
    ('PFE', 'MRK'),
]

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'Pairs Portfolio',
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def pair_key(a, b): return f"{a}/{b}"

def calc_zscore(s1: pd.Series, s2: pd.Series) -> tuple:
    """Compute spread z-score using log prices. Returns (z, spread, mean, std)."""
    spread = np.log(s1) - np.log(s2)
    mean   = spread.rolling(LOOKBACK).mean().iloc[-1]
    std    = spread.rolling(LOOKBACK).std().iloc[-1]
    z      = (spread.iloc[-1] - mean) / std if std > 0 else 0.0
    return float(z), float(spread.iloc[-1]), float(mean), float(std)

def run():
    data = load()
    today = str(date.today())

    # Fetch all symbols at once
    all_syms = list({s for pair in PAIRS for s in pair})
    raw = yf.download(all_syms, period=f'{LOOKBACK + 10}d', interval='1d',
                      progress=False, auto_adjust=True)
    if raw.empty:
        print("  No data returned"); return data

    closes = raw['Close']

    for sym_a, sym_b in PAIRS:
        key = pair_key(sym_a, sym_b)
        try:
            s1 = closes[sym_a].dropna()
            s2 = closes[sym_b].dropna()
            common = s1.index.intersection(s2.index)
            if len(common) < LOOKBACK:
                print(f"  {key}: insufficient history"); continue
            s1, s2 = s1[common], s2[common]
            z, spread, mean_s, std_s = calc_zscore(s1, s2)
            p1, p2 = float(s1.iloc[-1]), float(s2.iloc[-1])
        except Exception as e:
            print(f"  {key}: error — {e}"); continue

        in_pos    = key in data['open_positions']
        pos       = data['open_positions'].get(key, {})
        direction = pos.get('direction', None)  # 'long_spread' or 'short_spread'

        # Entry logic
        if not in_pos:
            if z > Z_ENTRY:
                # Spread high → short spread (short A, long B)
                shares_a = POSITION_SIZE / p1
                shares_b = POSITION_SIZE / p2
                data['open_positions'][key] = {
                    'sym_a': sym_a, 'sym_b': sym_b,
                    'direction': 'short_spread',
                    'entry_z': round(z, 3), 'entry_date': today,
                    'entry_p_a': p1, 'entry_p_b': p2,
                    'shares_a': shares_a, 'shares_b': shares_b
                }
                print(f"  {key}: z={z:.2f} → SHORT spread (short {sym_a}, long {sym_b})")

            elif z < -Z_ENTRY:
                # Spread low → long spread (long A, short B)
                shares_a = POSITION_SIZE / p1
                shares_b = POSITION_SIZE / p2
                data['open_positions'][key] = {
                    'sym_a': sym_a, 'sym_b': sym_b,
                    'direction': 'long_spread',
                    'entry_z': round(z, 3), 'entry_date': today,
                    'entry_p_a': p1, 'entry_p_b': p2,
                    'shares_a': shares_a, 'shares_b': shares_b
                }
                print(f"  {key}: z={z:.2f} → LONG spread (long {sym_a}, short {sym_b})")
            else:
                print(f"  {key}: z={z:.2f}  neutral")

        # Exit logic
        elif in_pos:
            exit_signal = False
            stop_hit    = abs(z) > Z_STOP

            if direction == 'short_spread' and z < Z_EXIT:  exit_signal = True
            if direction == 'long_spread'  and z > -Z_EXIT: exit_signal = True

            if exit_signal or stop_hit:
                # P&L for short spread: short A (gain if A falls), long B (gain if B rises)
                if direction == 'short_spread':
                    pnl = (pos['entry_p_a'] - p1) * pos['shares_a'] + \
                          (p2 - pos['entry_p_b']) * pos['shares_b']
                else:
                    pnl = (p1 - pos['entry_p_a']) * pos['shares_a'] + \
                          (pos['entry_p_b'] - p2) * pos['shares_b']

                win = pnl > 0
                reason = 'stop' if stop_hit else 'target'
                data['trades'].append({
                    'pair': key, 'direction': direction,
                    'entry_date': pos['entry_date'], 'exit_date': today,
                    'entry_z': pos['entry_z'], 'exit_z': round(z, 3),
                    'pnl_usd': round(pnl, 2), 'win': win, 'exit_reason': reason
                })
                data['stats']['n_trades'] += 1
                data['stats']['total_pnl'] += pnl
                if win: data['stats']['wins'] += 1
                del data['open_positions'][key]
                tag = '🛑 STOP' if stop_hit else '✅ EXIT'
                print(f"  {key}: z={z:.2f} → {tag}  P&L=${pnl:+.2f}  {'WIN' if win else 'LOSS'}")
            else:
                unrealized_pnl = 0.0
                if direction == 'short_spread':
                    unrealized_pnl = (pos['entry_p_a'] - p1) * pos['shares_a'] + \
                                     (p2 - pos['entry_p_b']) * pos['shares_b']
                else:
                    unrealized_pnl = (p1 - pos['entry_p_a']) * pos['shares_a'] + \
                                     (pos['entry_p_b'] - p2) * pos['shares_b']
                print(f"  {key}: z={z:.2f}  {direction}  unrealized=${unrealized_pnl:+.2f}")

    data['last_update'] = today
    save(data)
    return data

if __name__ == '__main__':
    print(f"=== Pairs Portfolio — {date.today()} ===")
    run()
    print("Done.")
