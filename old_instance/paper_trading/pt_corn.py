#!/usr/bin/env python3
"""
Strategy 3: Corn Seasonal Paper Trader
Signal: Long CORN ETF Nov 1 → Mar 1 (calendar-based).
Also tracks Natural Gas (UNG) Nov→Mar as secondary.
Run daily at 4:35 PM CT.
"""

import sys, json
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')
try:
    import yfinance as yf
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'yfinance', 'pandas', 'numpy',
                    '--target=/tmp/eval_deps', '--quiet'])
    import yfinance as yf

PORTFOLIO_FILE  = Path(__file__).parent / 'corn_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
# Corn: long Nov 1 – Mar 1 each year
# NatGas (UNG): long Nov 1 – Mar 1 (winter demand)
SEASONALS = {
    'CORN': {'ticker': 'CORN', 'entry_month': 11, 'entry_day': 1,
             'exit_month': 3,  'exit_day': 1,  'position_size': 2500.0},
    'UNG':  {'ticker': 'UNG',  'entry_month': 11, 'entry_day': 1,
             'exit_month': 3,  'exit_day': 1,  'position_size': 2500.0},
}

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'Commodity Seasonal',
        'virtual_capital': VIRTUAL_CAPITAL,
        'positions': {},
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def is_in_season(today: date, cfg: dict) -> bool:
    em, ed = cfg['entry_month'], cfg['entry_day']
    xm, xd = cfg['exit_month'],  cfg['exit_day']
    entry_this = date(today.year, em, ed)
    if xm < em:  # wraps year (Nov→Mar)
        exit_this = date(today.year + 1, xm, xd)
        entry_prev = date(today.year - 1, em, ed)
        exit_prev  = date(today.year, xm, xd)
        return (entry_this <= today < exit_this) or (entry_prev <= today < exit_prev)
    return date(today.year, em, ed) <= today < date(today.year, xm, xd)

def next_entry(today: date, cfg: dict) -> date:
    em, ed = cfg['entry_month'], cfg['entry_day']
    d = date(today.year, em, ed)
    if d <= today: d = date(today.year + 1, em, ed)
    return d

def run():
    data = load()
    today = date.today()

    for name, cfg in SEASONALS.items():
        in_season = is_in_season(today, cfg)
        in_pos    = name in data['positions']

        # Get price
        hist = yf.download(cfg['ticker'], period='5d', interval='1d', progress=False, auto_adjust=True)
        if hist.empty:
            print(f"  {name}: no data"); continue
        price = float(hist['Close'].squeeze().iloc[-1])

        print(f"  {name}: ${price:.2f}  in_season={in_season}  in_pos={in_pos}")

        if in_season and not in_pos:
            shares = cfg['position_size'] / price
            data['positions'][name] = {'entry_price': price, 'shares': shares,
                                        'entry_date': str(today), 'ticker': cfg['ticker']}
            print(f"    → ENTER {name} @ ${price:.2f}")

        elif not in_season and in_pos:
            pos = data['positions'][name]
            pnl = pos['shares'] * (price - pos['entry_price'])
            ret = (price / pos['entry_price'] - 1) * 100
            win = pnl > 0
            data['trades'].append({'instrument': name, 'entry_date': pos['entry_date'],
                                    'exit_date': str(today), 'entry_price': pos['entry_price'],
                                    'exit_price': price, 'return_pct': round(ret/100, 4),
                                    'pnl_usd': round(pnl, 2), 'win': win})
            data['stats']['n_trades'] += 1
            data['stats']['total_pnl'] += pnl
            if win: data['stats']['wins'] += 1
            del data['positions'][name]
            print(f"    → EXIT {name} @ ${price:.2f}  P&L=${pnl:+.2f}  ({ret:+.1f}%)")

        elif in_season and in_pos:
            pos = data['positions'][name]
            unrealized = pos['shares'] * (price - pos['entry_price'])
            print(f"    → HOLDING  unrealized=${unrealized:+.2f}")

        else:
            ne = next_entry(today, cfg)
            print(f"    → OFF-SEASON  next entry: {ne}")

    # Store current prices for reporting
    data['last_update'] = str(today)
    save(data)
    return data

if __name__ == '__main__':
    print(f"=== Corn Seasonal — {date.today()} ===")
    run()
    print("Done.")
