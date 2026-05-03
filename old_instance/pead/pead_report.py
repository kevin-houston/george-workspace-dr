#!/usr/bin/env python3
"""
PEAD Daily Report — generates WhatsApp-formatted summary for George to send Kevin.
Run at 4:35 PM CT weekdays after exit check completes.
"""

import sys
import json
import math
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, '/tmp/eval_deps')

try:
    import yfinance as yf
    import numpy as np
except ImportError:
    pass

TRADES_FILE = Path(__file__).parent / 'pead_trades.json'

def trading_days_between(start, end):
    count = 0
    cur = start + timedelta(days=1)
    while cur <= end:
        if cur.weekday() < 5:
            count += 1
        cur += timedelta(days=1)
    return count

def compute_sharpe(trades: list, bucket: str = None) -> float:
    """Compute annualized Sharpe from closed trade returns."""
    returns = []
    for t in trades:
        if bucket and t.get('threshold') != bucket:
            continue
        returns.append(t.get('return_pct', 0.0))
    if len(returns) < 3:
        return float('nan')
    arr = [r for r in returns]
    mean = sum(arr) / len(arr)
    variance = sum((r - mean) ** 2 for r in arr) / len(arr)
    std = math.sqrt(variance)
    if std == 0:
        return float('nan')
    # Annualize assuming 20-day hold per trade, ~12.6 trades/yr
    return round((mean / std) * math.sqrt(252 / 20), 3)

def fetch_unrealized(open_positions: list) -> dict:
    """Fetch current prices for open positions and compute unrealized P&L."""
    if not open_positions:
        return {}
    symbols = [p['symbol'] for p in open_positions]
    try:
        data = yf.download(
            symbols if len(symbols) > 1 else symbols[0],
            period='2d', interval='1d', progress=False, auto_adjust=True
        )
        prices = {}
        for sym in symbols:
            try:
                if hasattr(data.columns, 'levels'):
                    px = float(data['Close'][sym].iloc[-1])
                else:
                    px = float(data['Close'].iloc[-1])
                prices[sym] = px
            except Exception:
                pass
        return prices
    except Exception:
        return {}

def format_report(data: dict) -> str:
    today = date.today()
    closed = data.get('closed_positions', [])
    opens  = data.get('open_positions', [])
    stats  = data.get('stats', {})

    total_closed_pnl = sum(p.get('pnl_usd', 0) for p in closed)
    total_trades     = sum(stats.get(b, {}).get('n_trades', 0) for b in ['3pct', '5pct'])
    total_wins       = sum(stats.get(b, {}).get('wins', 0) for b in ['3pct', '5pct'])
    win_rate         = (total_wins / total_trades * 100) if total_trades else 0
    portfolio_value  = 5000.0 + total_closed_pnl
    pnl_sign         = '+' if total_closed_pnl >= 0 else ''

    # Unrealized P&L
    current_prices = fetch_unrealized(opens)
    unrealized_pnl = 0.0
    for p in opens:
        cp = current_prices.get(p['symbol'])
        if cp:
            unrealized_pnl += p['shares'] * (cp - p['entry_price'])

    sharpe_5 = compute_sharpe(closed, '5pct')
    sharpe_3 = compute_sharpe(closed, '3pct')

    lines = []
    lines.append(f"*📊 PEAD Paper Tracker — {today.strftime('%b %d, %Y')}*")
    lines.append("")

    # Portfolio summary
    total_value = portfolio_value + unrealized_pnl
    lines.append(f"*Portfolio:* ${total_value:.2f}  _(started $5,000)_")
    lines.append(f"Realized P&L: *{pnl_sign}${total_closed_pnl:.2f}*  |  Unrealized: *{'+' if unrealized_pnl>=0 else ''}${unrealized_pnl:.2f}*")
    if total_trades > 0:
        lines.append(f"Closed trades: {total_trades}  |  Win rate: *{win_rate:.0f}%*")

    # Per-threshold stats
    lines.append("")
    lines.append("*By threshold:*")
    for bucket, label in [('5pct', '5% gap'), ('3pct', '3% gap')]:
        s = stats.get(bucket, {})
        n = s.get('n_trades', 0)
        if n > 0:
            wr = s['wins'] / n * 100
            avg_r = s['total_return_pct'] / n * 100
            sh = compute_sharpe(closed, bucket)
            sh_str = f"  Sharpe {sh:.2f}" if not math.isnan(sh) else ""
            lines.append(f"• {label}: {n} trades, {wr:.0f}% win, avg {avg_r:+.1f}%{sh_str}  P&L *{'+' if s['total_pnl']>=0 else ''}${s['total_pnl']:.2f}*")
        else:
            lines.append(f"• {label}: no closed trades yet")

    # Open positions
    lines.append("")
    lines.append(f"*Open ({len(opens)}/10):*")
    if opens:
        for p in sorted(opens, key=lambda x: x['entry_date']):
            entry = date.fromisoformat(p['entry_date'])
            days_held = trading_days_between(entry, today)
            days_left = 20 - days_held
            cp = current_prices.get(p['symbol'])
            if cp:
                ret = (cp / p['entry_price'] - 1) * 100
                price_str = f"${cp:.2f} ({ret:+.1f}%)"
            else:
                price_str = f"in @ ${p['entry_price']:.2f}"
            lines.append(f"• {p['symbol']} [{p['threshold']}]  {price_str}  day {days_held}/20  ({days_left}d left)")
    else:
        lines.append("• (none open)")

    # Recent closed trades
    recent = sorted(closed, key=lambda x: x.get('exit_date',''), reverse=True)[:5]
    if recent:
        lines.append("")
        lines.append("*Recent closes:*")
        for p in recent:
            icon = '✅' if p.get('win') else '❌'
            lines.append(f"• {icon} {p['symbol']}  {p.get('exit_date','')}  {p.get('return_pct',0)*100:+.1f}%  ${p.get('pnl_usd',0):+.2f}")

    return '\n'.join(lines)

if __name__ == '__main__':
    if not TRADES_FILE.exists():
        print("No trades file found.")
    else:
        with open(TRADES_FILE) as f:
            data = json.load(f)
        print(format_report(data))
