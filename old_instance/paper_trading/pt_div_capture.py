#!/usr/bin/env python3
"""
Dividend Strategy #3: Dividend Capture Paper Trader
Signal: buy 3 trading days before ex-dividend date, sell 5 trading days after.
Captures the pre-ex-div institutional accumulation momentum (Sharpe +1.578 in backtest).
Universe: Dividend Aristocrats + Fortune 100 payers (~50 stocks)
Run daily at 4:35 PM CT after market close.
"""

import sys, json
from datetime import date, timedelta
from pathlib import Path

try:
    import yfinance as yf
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([sys.executable, '-m', 'pip', 'install',
                    'yfinance', 'pandas', 'numpy', '--break-system-packages', '-q'],
                   capture_output=True)
    import yfinance as yf
    import numpy as np

PORTFOLIO_FILE  = Path(__file__).parent / 'div_capture_portfolio.json'
VIRTUAL_CAPITAL = 5000.0
POSITION_SIZE   = 500.0    # per trade
MAX_POSITIONS   = 10
BUY_DAYS_BEFORE = 3        # trading days before ex-date to enter
HOLD_DAYS_AFTER = 5        # trading days after ex-date to exit
LOOKAHEAD_CAL   = 20       # calendar day window to scan for ex-dates

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
        'strategy': 'Dividend Capture (buy 3d before, sell 5d after ex-div)',
        'backtest_sharpe': 1.578,
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},   # ticker_exdate → position
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None
    }

def save(data: dict):
    with open(PORTFOLIO_FILE, 'w') as f: json.dump(data, f, indent=2, default=str)

def trading_days_until(target: date, from_date: date = None) -> int:
    d = from_date or date.today()
    count = 0
    while d < target:
        d += timedelta(days=1)
        if d.weekday() < 5: count += 1
    return count

def trading_days_from(start: date, n: int) -> date:
    d, count = start, 0
    while count < n:
        d += timedelta(days=1)
        if d.weekday() < 5: count += 1
    return d

def find_upcoming_ex_dates(ticker: str, lookahead_days: int = 20) -> list:
    try:
        t = yf.Ticker(ticker)
        divs = t.dividends
        if divs is None or len(divs) == 0: return []
        divs.index = divs.index.tz_localize(None) if divs.index.tz else divs.index
        today = date.today()
        future = today + timedelta(days=lookahead_days)
        return [
            {'ex_date': dt.date() if hasattr(dt, 'date') else dt, 'amount': float(amt)}
            for dt, amt in divs.items()
            if today <= (dt.date() if hasattr(dt, 'date') else dt) <= future
        ]
    except:
        return []

def get_price(ticker: str) -> float | None:
    try:
        hist = yf.download(ticker, period='2d', auto_adjust=True, progress=False)
        if len(hist) == 0: return None
        col = 'Close' if 'Close' in hist.columns else hist.columns[0]
        return float(hist[col].iloc[-1].squeeze())
    except:
        return None

def run():
    data = load()
    today = date.today()
    if today.weekday() >= 5:
        print(f"Weekend, skipping ({today})")
        return

    print(f"\n=== Dividend Capture Paper Trader — {today} ===")

    # ── 1. Check exits: sell 5 trading days after ex-date ──
    to_exit = [k for k, pos in data['open_positions'].items()
               if str(today) >= pos.get('exit_date', '9999-99-99')]
    for key in to_exit:
        pos = data['open_positions'].pop(key)
        ticker = pos['ticker']
        exit_price = get_price(ticker) or pos['entry_price']
        ret = (exit_price - pos['entry_price']) / pos['entry_price']
        pnl = ret * pos['shares'] * pos['entry_price']
        win = pnl > 0
        trade = {
            'ticker': ticker,
            'entry_date': pos['entry_date'],
            'exit_date': str(today),
            'ex_date': pos['ex_date'],
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'shares': pos['shares'],
            'pnl_usd': round(pnl, 2),
            'return_pct': round(ret, 4),
            'win': win
        }
        data['trades'].append(trade)
        data['stats']['n_trades'] += 1
        data['stats']['wins'] += int(win)
        data['stats']['total_pnl'] += pnl
        print(f"  EXIT {ticker}: ret={ret:+.1%} pnl=${pnl:+.2f} {'✓' if win else '✗'}")

    # ── 2. Scan for entries: ex-date exactly BUY_DAYS_BEFORE trading days away ──
    n_open = len(data['open_positions'])
    already_active = set(data['open_positions'].keys())

    # Also avoid re-entering the same ticker/ex_date from closed trades recently
    recent_cutoff = str(today - timedelta(days=30))
    recently_traded = {
        t['ticker'] + '_' + t['ex_date']
        for t in data['trades']
        if t.get('entry_date', '') >= recent_cutoff
    }

    if n_open < MAX_POSITIONS:
        print(f"  Scanning for ex-dates in {BUY_DAYS_BEFORE} trading days "
              f"(open={n_open}/{MAX_POSITIONS})...")
        for ticker in UNIVERSE:
            if n_open >= MAX_POSITIONS: break
            upcoming = find_upcoming_ex_dates(ticker, lookahead_days=LOOKAHEAD_CAL)
            for event in upcoming:
                if n_open >= MAX_POSITIONS: break
                ex_date = event['ex_date']
                key = f"{ticker}_{ex_date}"
                if key in already_active or key in recently_traded: continue
                td = trading_days_until(ex_date, today)
                if td != BUY_DAYS_BEFORE: continue

                # Enter today
                price = get_price(ticker)
                if price is None: continue
                shares = POSITION_SIZE / price
                exit_date = trading_days_from(ex_date, HOLD_DAYS_AFTER)
                data['open_positions'][key] = {
                    'ticker': ticker,
                    'entry_price': price,
                    'shares': shares,
                    'entry_date': str(today),
                    'ex_date': str(ex_date),
                    'exit_date': str(exit_date),
                    'div_amount': event['amount'],
                }
                n_open += 1
                already_active.add(key)
                print(f"  ENTER {ticker}: price=${price:.2f} "
                      f"ex={ex_date} exit={exit_date} div=${event['amount']:.4f}")
    else:
        print(f"  Portfolio full ({n_open}/{MAX_POSITIONS}), no new entries")

    data['last_update'] = str(today)
    save(data)

    # ── 3. Mark to market open positions ──
    stats = data['stats']
    open_pnl = 0.0
    print(f"\n  Open positions: {len(data['open_positions'])}")
    for key, pos in data['open_positions'].items():
        price = get_price(pos['ticker'])
        if price:
            unreal = (price - pos['entry_price']) * pos['shares']
            open_pnl += unreal
            td_ex = trading_days_until(date.fromisoformat(pos['ex_date']), today)
            td_exit = trading_days_until(date.fromisoformat(pos['exit_date']), today)
            status = f"pre-ex ({td_ex}d)" if td_ex > 0 else f"post-ex, exit in {td_exit}d"
            print(f"    {pos['ticker']}: entry=${pos['entry_price']:.2f} "
                  f"cur=${price:.2f} unreal=${unreal:+.2f} [{status}]")

    total_pnl = stats['total_pnl'] + open_pnl
    wr = stats['wins'] / stats['n_trades'] * 100 if stats['n_trades'] > 0 else 0
    print(f"\n  Realized P&L: ${stats['total_pnl']:+.2f}")
    print(f"  Unrealized:   ${open_pnl:+.2f}")
    print(f"  Total P&L:    ${total_pnl:+.2f}")
    print(f"  Win rate: {wr:.0f}% ({stats['wins']}/{stats['n_trades']} trades)")
    print(f"  Portfolio value: ${VIRTUAL_CAPITAL + total_pnl:,.2f}")

if __name__ == '__main__':
    run()
