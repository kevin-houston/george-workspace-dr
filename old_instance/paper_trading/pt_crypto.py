#!/usr/bin/env python3
"""
Strategy 2: SOL 20-day Momentum Paper Trader
Signal: SOL-USD close > 20d SMA → long, else flat.
Also tracks BTC as second position (runner-up in backtest).
Run daily at 4:35 PM CT after market close.
"""

import sys, json
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')
try:
    import yfinance as yf
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'yfinance', 'pandas', 'numpy',
                    '--target=/tmp/eval_deps', '--quiet'])
    import yfinance as yf
    import numpy as np

PORTFOLIO_FILE = Path(__file__).parent / 'crypto_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 2500.0   # $2,500 per coin (SOL + BTC each)
COINS           = {'SOL-USD': 'SOL', 'BTC-USD': 'BTC'}
SMA_WINDOW      = 20

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'Crypto 20d Momentum',
        'virtual_capital': VIRTUAL_CAPITAL,
        'positions': {},   # coin → {entry_price, shares, entry_date}
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def run():
    data = load()
    today = str(date.today())
    results = []

    for ticker, name in COINS.items():
        hist = yf.download(ticker, period='60d', interval='1d', progress=False, auto_adjust=True)
        if hist.empty or len(hist) < SMA_WINDOW + 1:
            print(f"  {name}: insufficient data"); continue

        closes = hist['Close'].squeeze()
        price  = float(closes.iloc[-1])
        sma20  = float(closes.iloc[-SMA_WINDOW:].mean())
        signal = price > sma20
        in_pos = name in data['positions']
        pct_above = (price / sma20 - 1) * 100

        print(f"  {name}: ${price:,.2f}  SMA20=${sma20:,.2f}  ({pct_above:+.1f}%)  signal={'LONG' if signal else 'FLAT'}  pos={'IN' if in_pos else 'OUT'}")

        if signal and not in_pos:
            # Enter
            shares = POSITION_SIZE / price
            data['positions'][name] = {'entry_price': price, 'shares': shares,
                                        'entry_date': today, 'ticker': ticker}
            print(f"    → ENTER {name} @ ${price:,.2f}")

        elif not signal and in_pos:
            # Exit
            pos = data['positions'][name]
            pnl = pos['shares'] * (price - pos['entry_price'])
            ret = (price / pos['entry_price'] - 1) * 100
            win = pnl > 0
            data['trades'].append({'coin': name, 'entry_date': pos['entry_date'],
                                    'exit_date': today, 'entry_price': pos['entry_price'],
                                    'exit_price': price, 'return_pct': round(ret/100, 4),
                                    'pnl_usd': round(pnl, 2), 'win': win})
            data['stats']['n_trades'] += 1
            data['stats']['total_pnl'] += pnl
            if win: data['stats']['wins'] += 1
            del data['positions'][name]
            print(f"    → EXIT {name} @ ${price:,.2f}  P&L=${pnl:+.2f}  ({ret:+.1f}%)")

        results.append({'coin': name, 'price': price, 'sma20': sma20,
                        'signal': signal, 'in_position': name in data['positions']})

    data['last_update'] = today
    data['current_prices'] = {r['coin']: r for r in results}
    save(data)
    return data

if __name__ == '__main__':
    print(f"=== Crypto Momentum — {date.today()} ===")
    run()
    print("Done.")
