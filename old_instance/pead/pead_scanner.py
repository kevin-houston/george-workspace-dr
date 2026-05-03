#!/usr/bin/env python3
"""
PEAD Scanner — runs at 9:45 AM CT weekdays
Detects gap-up signals (3% and 5% thresholds) across 30-stock universe.
Logs new paper trades to pead_trades.json.
Also handles EOD exit checks when run with --exit flag.
"""

import sys
import json
import argparse
from datetime import datetime, timedelta, date
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')

try:
    import yfinance as yf
    import pandas as pd
    import numpy as np
except ImportError:
    import subprocess
    subprocess.run([
        sys.executable, '-m', 'pip', 'install',
        'yfinance', 'pandas', 'numpy',
        '--target=/tmp/eval_deps', '--quiet'
    ])
    import yfinance as yf
    import pandas as pd
    import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────

UNIVERSE = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'JPM',
    'JNJ', 'UNH', 'V', 'MA', 'HD', 'PG', 'COST', 'XOM', 'CVX', 'BAC',
    'WMT', 'MRK', 'NFLX', 'ADBE', 'QCOM', 'TXN', 'HON', 'GE', 'CAT',
    'MMM', 'LMT', 'RTX'
]

VIRTUAL_CAPITAL    = 5000.0
POSITION_SIZE      = 500.0       # $500 per trade (10% of $5k, max 10 concurrent)
MAX_POSITIONS      = 10
HOLD_DAYS          = 20          # trading days
THRESHOLD_3PCT     = 0.03
THRESHOLD_5PCT     = 0.05

TRADES_FILE = Path(__file__).parent / 'pead_trades.json'

# ── Helpers ───────────────────────────────────────────────────────────────────

def trading_days_between(start: date, end: date) -> int:
    """Count trading days between two dates (Mon-Fri, no holiday adjustment)."""
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count

def add_trading_days(start: date, n: int) -> date:
    """Return date that is n trading days after start."""
    cur = start
    added = 0
    while added < n:
        cur += timedelta(days=1)
        if cur.weekday() < 5:
            added += 1
    return cur

def load_trades() -> dict:
    if TRADES_FILE.exists():
        with open(TRADES_FILE) as f:
            return json.load(f)
    return {
        "virtual_capital": VIRTUAL_CAPITAL,
        "position_size": POSITION_SIZE,
        "max_positions": MAX_POSITIONS,
        "hold_days": HOLD_DAYS,
        "open_positions": [],
        "closed_positions": [],
        "stats": {
            "3pct": {"n_trades": 0, "wins": 0, "total_pnl": 0.0, "total_return_pct": 0.0},
            "5pct": {"n_trades": 0, "wins": 0, "total_pnl": 0.0, "total_return_pct": 0.0}
        },
        "last_scan": None,
        "last_exit_check": None
    }

def save_trades(data: dict):
    with open(TRADES_FILE, 'w') as f:
        json.dump(data, f, indent=2, default=str)

def open_symbols(data: dict) -> set:
    return {p['symbol'] for p in data['open_positions']}

def count_open(data: dict) -> int:
    return len(data['open_positions'])

# ── Scanner ───────────────────────────────────────────────────────────────────

def run_scan(data: dict) -> list:
    """Fetch today's open and yesterday's close for each symbol. Return gap signals."""
    today = date.today()
    signals = []

    # Download 3 days of data so we always have yesterday's close
    tickers = yf.download(
        UNIVERSE,
        period='5d',
        interval='1d',
        progress=False,
        auto_adjust=True
    )

    if tickers.empty:
        print("ERROR: No data returned from yfinance")
        return []

    closes = tickers['Close']
    opens  = tickers['Open']

    # Get last two rows
    if len(closes) < 2:
        print("ERROR: Insufficient price rows")
        return []

    prev_close = closes.iloc[-2]
    today_open = opens.iloc[-1]

    for sym in UNIVERSE:
        try:
            pc = float(prev_close[sym])
            to = float(today_open[sym])
            if pc <= 0 or to <= 0 or np.isnan(pc) or np.isnan(to):
                continue
            gap = (to / pc) - 1.0

            if gap >= THRESHOLD_5PCT:
                signals.append({
                    'symbol': sym,
                    'gap_pct': round(gap, 4),
                    'threshold': '5pct',
                    'prev_close': round(pc, 4),
                    'entry_price': round(to, 4)
                })
            elif gap >= THRESHOLD_3PCT:
                signals.append({
                    'symbol': sym,
                    'gap_pct': round(gap, 4),
                    'threshold': '3pct',
                    'prev_close': round(pc, 4),
                    'entry_price': round(to, 4)
                })
        except Exception as e:
            pass

    return signals

def enter_trades(data: dict, signals: list) -> list:
    """Enter paper trades for valid signals (not already open, under position limit)."""
    today = date.today()
    entered = []
    already_open = open_symbols(data)

    for sig in signals:
        if count_open(data) >= MAX_POSITIONS:
            print(f"  MAX POSITIONS reached ({MAX_POSITIONS}), skipping {sig['symbol']}")
            break
        if sig['symbol'] in already_open:
            print(f"  Already open: {sig['symbol']}, skipping")
            continue

        shares = round(POSITION_SIZE / sig['entry_price'], 4)
        exit_date = add_trading_days(today, HOLD_DAYS)

        trade = {
            'symbol': sig['symbol'],
            'threshold': sig['threshold'],
            'entry_date': str(today),
            'entry_price': sig['entry_price'],
            'shares': shares,
            'position_size_usd': round(shares * sig['entry_price'], 2),
            'gap_pct': sig['gap_pct'],
            'prev_close': sig['prev_close'],
            'target_exit_date': str(exit_date),
            'status': 'open'
        }
        data['open_positions'].append(trade)
        entered.append(trade)
        print(f"  ENTERED: {sig['symbol']} @ ${sig['entry_price']} ({sig['threshold']}, gap {sig['gap_pct']*100:.1f}%, exit {exit_date})")

    return entered

# ── Exit checker ──────────────────────────────────────────────────────────────

def run_exit_check(data: dict) -> list:
    """Close positions that have hit 20 trading days. Fetch current prices."""
    today = date.today()
    to_close = []

    for pos in data['open_positions']:
        entry = date.fromisoformat(pos['entry_date'])
        days_held = trading_days_between(entry, today)
        if days_held >= HOLD_DAYS:
            to_close.append(pos)

    if not to_close:
        print("  No positions to close today.")
        return []

    # Fetch closing prices for positions being closed
    symbols = [p['symbol'] for p in to_close]
    prices = yf.download(symbols if len(symbols) > 1 else symbols[0],
                         period='2d', interval='1d', progress=False, auto_adjust=True)

    closed = []
    for pos in to_close:
        sym = pos['symbol']
        try:
            if isinstance(prices.columns, pd.MultiIndex):
                exit_price = float(prices['Close'][sym].iloc[-1])
            else:
                exit_price = float(prices['Close'].iloc[-1])

            if np.isnan(exit_price):
                raise ValueError("NaN price")
        except Exception:
            print(f"  WARNING: Could not fetch exit price for {sym}, skipping")
            continue

        ret_pct = (exit_price / pos['entry_price']) - 1.0
        pnl     = pos['shares'] * (exit_price - pos['entry_price'])
        win     = ret_pct > 0

        closed_trade = {**pos,
            'exit_date': str(today),
            'exit_price': round(exit_price, 4),
            'return_pct': round(ret_pct, 4),
            'pnl_usd': round(pnl, 2),
            'win': win,
            'status': 'closed'
        }

        data['closed_positions'].append(closed_trade)
        data['open_positions'] = [p for p in data['open_positions'] if p['symbol'] != sym]

        # Update stats
        bucket = pos['threshold']
        data['stats'][bucket]['n_trades'] += 1
        data['stats'][bucket]['total_pnl'] += pnl
        data['stats'][bucket]['total_return_pct'] += ret_pct
        if win:
            data['stats'][bucket]['wins'] += 1

        print(f"  CLOSED: {sym} @ ${exit_price:.2f} | ret={ret_pct*100:.1f}% | PnL=${pnl:.2f} | {'WIN' if win else 'LOSS'}")
        closed.append(closed_trade)

    data['last_exit_check'] = str(today)
    return closed

# ── Report builder ────────────────────────────────────────────────────────────

def build_report(data: dict) -> str:
    today = date.today()
    lines = []
    lines.append(f"PEAD Paper Tracker — {today.strftime('%B %d, %Y')}")
    lines.append("=" * 50)

    # Portfolio summary
    total_closed_pnl = sum(p['pnl_usd'] for p in data['closed_positions'])
    total_trades     = sum(data['stats'][b]['n_trades'] for b in ['3pct', '5pct'])
    total_wins       = sum(data['stats'][b]['wins'] for b in ['3pct', '5pct'])
    win_rate         = (total_wins / total_trades * 100) if total_trades else 0
    portfolio_value  = VIRTUAL_CAPITAL + total_closed_pnl

    lines.append(f"\nVirtual Portfolio: ${portfolio_value:.2f}  (started $5,000.00)")
    lines.append(f"Realized P&L: ${total_closed_pnl:+.2f}")
    lines.append(f"Total closed trades: {total_trades}  |  Win rate: {win_rate:.0f}%")

    for bucket in ['5pct', '3pct']:
        s = data['stats'][bucket]
        if s['n_trades'] > 0:
            wr = s['wins'] / s['n_trades'] * 100
            avg_ret = s['total_return_pct'] / s['n_trades'] * 100
            lines.append(f"  {bucket} threshold: {s['n_trades']} trades, {wr:.0f}% win, avg ret {avg_ret:.1f}%, P&L ${s['total_pnl']:+.2f}")

    # Open positions
    lines.append(f"\nOpen Positions ({count_open(data)}/{MAX_POSITIONS}):")
    if data['open_positions']:
        for p in sorted(data['open_positions'], key=lambda x: x['entry_date']):
            entry = date.fromisoformat(p['entry_date'])
            days_held = trading_days_between(entry, today)
            days_left = HOLD_DAYS - days_held
            lines.append(f"  {p['symbol']:6s} [{p['threshold']}]  in @ ${p['entry_price']:.2f}  "
                         f"day {days_held}/{HOLD_DAYS}  exit ~{p['target_exit_date']}")
    else:
        lines.append("  (none)")

    # Recent closes
    recent = sorted(data['closed_positions'], key=lambda x: x['exit_date'], reverse=True)[:5]
    if recent:
        lines.append("\nRecent Closes (last 5):")
        for p in recent:
            lines.append(f"  {p['symbol']:6s}  {p['exit_date']}  "
                         f"{p['return_pct']*100:+.1f}%  ${p['pnl_usd']:+.2f}  {'✓' if p['win'] else '✗'}")

    return '\n'.join(lines)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exit', action='store_true', help='Run exit check instead of scan')
    parser.add_argument('--report', action='store_true', help='Print report only')
    args = parser.parse_args()

    data = load_trades()

    if args.report:
        print(build_report(data))
        return

    if args.exit:
        print(f"=== PEAD Exit Check — {date.today()} ===")
        closed = run_exit_check(data)
        save_trades(data)
        print(f"Closed {len(closed)} position(s).")
        return

    # Default: morning scan
    print(f"=== PEAD Gap Scanner — {date.today()} ===")
    print(f"Open positions: {count_open(data)}/{MAX_POSITIONS}")

    signals = run_scan(data)
    print(f"Signals found: {len(signals)}")
    for s in signals:
        print(f"  {s['symbol']:6s}  gap={s['gap_pct']*100:.1f}%  ({s['threshold']})  open=${s['entry_price']:.2f}")

    if signals:
        entered = enter_trades(data, signals)
        print(f"Entered {len(entered)} new trade(s).")
    else:
        print("No signals today.")

    data['last_scan'] = str(date.today())
    save_trades(data)
    print("Done.")

if __name__ == '__main__':
    main()
