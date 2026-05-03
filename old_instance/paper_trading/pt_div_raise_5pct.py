#!/usr/bin/env python3
"""
Dividend Strategy #1b: Dividend Raise Signal Paper Trader (5% threshold)
Signal: company raises dividend >= 5% → buy at ex-date close, hold 40 trading days.
Universe: Dividend Aristocrats + Fortune 100 dividend payers (~50 stocks)
Run daily at 4:35 PM CT after market close.
"""

import sys, json, math
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    import yfinance as yf
    import numpy as np
    import pandas as pd
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'yfinance', 'pandas', 'numpy', '--break-system-packages', '-q'],
                   capture_output=True)
    import yfinance as yf
    import numpy as np
    import pandas as pd

PORTFOLIO_FILE = Path(__file__).parent / 'div_raise_5pct_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 500.0    # $500 per trade
MAX_POSITIONS   = 10
HOLD_DAYS       = 40       # trading days
MIN_RAISE_PCT   = 0.05     # 5% minimum dividend raise
LOOKBACK_DAYS   = 10       # consider ex-dates within last N trading days as "new" signals

UNIVERSE = [
    'ABT','ADP','AFL','APD','AXP','BA','CAT','CL','CMCSA','COST',
    'CVX','DE','DIS','GD','GE','GS','HD','HON','IBM','ITW',
    'JNJ','JPM','KMB','KO','LIN','LMT','LOW','MCD','MDT','MMM',
    'MRK','MSFT','NKE','NOC','PEP','PG','RTX','SYY','T','TGT',
    'TROW','UNH','UNP','UPS','V','VZ','WMT','XOM','PFE','C',
]

def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'Dividend Raise Signal (>=5%, hold 40d)',
        'backtest_sharpe': 3.400,
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},  # ticker → {entry_price, shares, entry_date, exit_date, div_raise_pct}
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data: dict):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def trading_days_from(start: date, n: int) -> date:
    """Return date that is n trading days after start."""
    d, count = start, 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5: count += 1
    return d

def trading_days_ago(n: int) -> date:
    """Return date that was n trading days before today."""
    d = date.today()
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if d.weekday() < 5: count += 1
    return d

def detect_raise_events(ticker: str) -> list:
    """
    Download dividend history, detect raises >= 5%.
    Returns list of ex-dates where a qualifying raise occurred.
    """
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs is None or len(divs) < 3:
            return []
        # Strip timezone
        divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
        amounts = divs.values
        dates = [d.date() for d in divs.index]
        events = []
        for i in range(1, len(dates)):
            prev, cur = float(amounts[i-1]), float(amounts[i])
            if prev <= 0: continue
            chg = (cur - prev) / prev
            if chg >= MIN_RAISE_PCT:
                events.append({'ex_date': dates[i], 'raise_pct': chg, 'amount': cur})
        return events
    except:
        return []

def run():
    data = load()
    today = date.today()
    if today.weekday() >= 5:  # Skip weekends
        print(f"Weekend, skipping ({today})")
        return

    print(f"\n=== Dividend Raise Signal (>=5%) Paper Trader — {today} ===")

    # Window for "new" signals: ex-date fell within last LOOKBACK_DAYS trading days
    lookback_start = trading_days_ago(LOOKBACK_DAYS)
    already_entered = set(data['open_positions'].keys())
    already_traded  = {t['ticker'] for t in data['trades']
                       if t.get('entry_date', '') >= str(lookback_start)}

    # ── 1. Check exits ──
    exits = [t for t, pos in data['open_positions'].items()
             if pos.get('exit_date') and str(today) >= pos['exit_date']]
    for ticker in exits:
        pos = data['open_positions'].pop(ticker)
        try:
            hist = yf.download(ticker, period='2d', auto_adjust=True, progress=False)
            if len(hist) == 0: continue
            col = 'Close' if 'Close' in hist.columns else hist.columns[0]
            exit_price = float(hist[col].iloc[-1].squeeze())
        except:
            exit_price = pos['entry_price']  # fallback
        pnl = (exit_price - pos['entry_price']) / pos['entry_price'] * pos['shares'] * pos['entry_price']
        win = pnl > 0
        ret_pct = (exit_price - pos['entry_price']) / pos['entry_price']
        trade = {
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'exit_date': str(today),
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'shares': pos['shares'],
            'pnl_usd': round(pnl, 2),
            'return_pct': round(ret_pct, 4),
            'div_raise_pct': pos.get('div_raise_pct', 0),
            'win': win
        }
        data['trades'].append(trade)
        data['stats']['n_trades'] += 1
        data['stats']['wins'] += int(win)
        data['stats']['total_pnl'] += pnl
        print(f"  EXIT {ticker}: {ret_pct:+.1%} P&L ${pnl:+.2f} {'✓' if win else '✗'}")

    # ── 2. Scan for new raise signals ──
    n_open = len(data['open_positions'])
    if n_open < MAX_POSITIONS:
        print(f"  Scanning for raise signals (open={n_open}/{MAX_POSITIONS})...")
        for ticker in UNIVERSE:
            if n_open >= MAX_POSITIONS: break
            if ticker in already_entered or ticker in already_traded: continue
            events = detect_raise_events(ticker)
            recent = [e for e in events
                      if e['ex_date'] >= lookback_start and e['ex_date'] <= today]
            if not recent: continue
            best = max(recent, key=lambda x: x['raise_pct'])
            # Enter position
            try:
                hist = yf.download(ticker, period='2d', auto_adjust=True, progress=False)
                if len(hist) == 0: continue
                col = 'Close' if 'Close' in hist.columns else hist.columns[0]
                entry_price = float(hist[col].iloc[-1].squeeze())
            except:
                continue
            shares = POSITION_SIZE / entry_price
            exit_date = trading_days_from(today, HOLD_DAYS)
            data['open_positions'][ticker] = {
                'entry_price': entry_price,
                'shares': shares,
                'entry_date': str(today),
                'exit_date': str(exit_date),
                'div_raise_pct': round(best['raise_pct'], 4),
                'ex_date': str(best['ex_date']),
            }
            n_open += 1
            already_entered.add(ticker)
            print(f"  ENTER {ticker}: raise={best['raise_pct']:+.1%} "
                  f"price=${entry_price:.2f} exit={exit_date}")
    else:
        print(f"  Portfolio full ({n_open}/{MAX_POSITIONS}), no new entries")

    data['last_update'] = str(today)
    save(data)

    # ── 3. Summary ──
    stats = data['stats']
    open_pnl = 0.0
    print(f"\n  Open positions: {len(data['open_positions'])}")
    for tk, pos in data['open_positions'].items():
        try:
            hist = yf.download(tk, period='2d', auto_adjust=True, progress=False)
            if len(hist) > 0:
                col = 'Close' if 'Close' in hist.columns else hist.columns[0]
                cp = float(hist[col].iloc[-1].squeeze())
                unreal = (cp - pos['entry_price']) * pos['shares']
                open_pnl += unreal
                print(f"    {tk}: entry=${pos['entry_price']:.2f} cur=${cp:.2f} "
                      f"unreal=${unreal:+.2f} exit={pos['exit_date']}")
        except:
            pass

    total_pnl = stats['total_pnl'] + open_pnl
    wr = stats['wins'] / stats['n_trades'] * 100 if stats['n_trades'] > 0 else 0
    print(f"\n  Realized P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Unrealized:   ${open_pnl:+.2f}")
    print(f"  Total P&L:    ${total_pnl:+.2f}")
    print(f"  Win rate: {wr:.0f}% ({stats['wins']}/{stats['n_trades']} trades)")
    print(f"  Portfolio value: ${VIRTUAL_CAPITAL + total_pnl:,.2f}")

if __name__ == '__main__':
    run()
