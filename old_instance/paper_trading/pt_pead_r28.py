#!/usr/bin/env python3
"""
PEAD Paper Trader — R28 Quality Filter
Signal: earnings gap >= 5% with quality score >= 40/70 (R28 EarningsQualityAgent proxy).
Quality score: gap_score (0-40) + vol_score (0-30). RegimeGuard: skip if VIX > 30.
Run at 9:45 AM CT to enter; run with --exit at 4:35 PM CT to check exits.
Backtest Sharpe (R28 Full): 9.028
"""

import sys, json, argparse
from datetime import date, timedelta
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

PORTFOLIO_FILE   = Path(__file__).parent / 'pead_r28_portfolio.json'
VIRTUAL_CAPITAL  = 5000.0
POSITION_SIZE    = 333.0   # $333 per position → ~15 concurrent positions
MAX_POSITIONS    = 15
GAP_THRESHOLD    = 0.05    # 5% minimum
QUALITY_THRESHOLD = 40     # out of 70 max (at entry time, 3rd component not observable)
VIX_LIMIT        = 30.0
HOLD_DAYS        = 20      # trading days

UNIVERSE = [
    'AAPL','MSFT','GOOGL','AMZN','META','NVDA','TSLA','JPM',
    'JNJ','UNH','V','MA','HD','PG','COST','XOM','CVX','BAC',
    'WMT','MRK','NFLX','ADBE','QCOM','TXN','HON','GE','CAT',
    'MMM','LMT','RTX'
]


def load() -> dict:
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE) as f: return json.load(f)
    return {
        'strategy': 'PEAD R28 Quality Filter',
        'backtest_sharpe': 9.028,
        'virtual_capital': VIRTUAL_CAPITAL,
        'open_positions': {},  # ticker → {entry_price, shares, entry_date, exit_date, gap_pct, quality_score}
        'trades': [],
        'stats': {'n_trades': 0, 'wins': 0, 'total_pnl': 0.0},
        'last_update': None,
        'skipped_vix': 0,      # count of signals skipped due to VIX > 30
        'skipped_quality': 0,  # count of signals skipped due to quality < threshold
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


def add_trading_days(start: date, n: int) -> date:
    """Alias for trading_days_from."""
    return trading_days_from(start, n)


def compute_quality_score(gap_pct: float, vol_ratio: float) -> float:
    """
    R28 quality proxy — two components observable at entry:
      gap_score: min(40, gap_pct/0.10 * 40)   # 40 pts at 10%+ gap
      vol_score: min(30, vol_ratio/3.0 * 30)   # 30 pts at 3x+ volume
    Max = 70 (3rd component — price persistence — is forward-looking, skipped here)
    """
    gap_score = min(40.0, (gap_pct / 0.10) * 40.0)
    vol_score = min(30.0, (vol_ratio / 3.0) * 30.0)
    return gap_score + vol_score


def get_vix() -> float:
    """Fetch latest VIX close."""
    hist = yf.download('^VIX', period='5d', progress=False)
    col = 'Close' if 'Close' in hist.columns else hist.columns[0]
    return float(hist[col].iloc[-1].squeeze())


def process_exits(data: dict, today: date):
    """Check open positions for exits due today or earlier."""
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
            'gap_pct': pos.get('gap_pct', 0),
            'quality_score': pos.get('quality_score', 0),
            'win': win
        }
        data['trades'].append(trade)
        data['stats']['n_trades'] += 1
        data['stats']['wins'] += int(win)
        data['stats']['total_pnl'] += pnl
        print(f"  EXIT {ticker}: {ret_pct:+.1%} P&L ${pnl:+.2f} {'✓' if win else '✗'}")


def scan_gaps(data: dict, today: date):
    """Scan UNIVERSE for earnings gap signals that pass the R28 quality filter."""
    n_open = len(data['open_positions'])
    if n_open >= MAX_POSITIONS:
        print(f"  Portfolio full ({n_open}/{MAX_POSITIONS}), no new entries")
        return

    already_entered = set(data['open_positions'].keys())
    lookback_start = trading_days_ago(5)
    already_traded = {t['ticker'] for t in data['trades']
                      if t.get('entry_date', '') >= str(lookback_start)}

    print(f"  Scanning for gap signals (open={n_open}/{MAX_POSITIONS})...")
    for ticker in UNIVERSE:
        if n_open >= MAX_POSITIONS: break
        if ticker in already_entered or ticker in already_traded: continue

        try:
            # Download recent OHLCV for gap calculation
            hist = yf.download(ticker, period='5d', auto_adjust=True, progress=False)
            if hist is None or len(hist) < 2: continue

            col_close = 'Close' if 'Close' in hist.columns else hist.columns[0]
            col_open  = 'Open'  if 'Open'  in hist.columns else None
            col_vol   = 'Volume' if 'Volume' in hist.columns else None

            if col_open is None or col_vol is None: continue

            prev_close   = float(hist[col_close].iloc[-2].squeeze())
            today_open   = float(hist[col_open].iloc[-1].squeeze())
            today_close  = float(hist[col_close].iloc[-1].squeeze())
            today_volume = float(hist[col_vol].iloc[-1].squeeze())

            if prev_close <= 0: continue
            gap = today_open / prev_close - 1.0

            if gap < GAP_THRESHOLD:
                continue

            # Compute 20-day average volume (exclude today)
            hist_30 = yf.download(ticker, period='30d', auto_adjust=True, progress=False)
            if hist_30 is None or len(hist_30) < 5: continue
            vol_col = 'Volume' if 'Volume' in hist_30.columns else None
            if vol_col is None: continue
            avg_vol = float(hist_30[vol_col].iloc[:-1].mean())
            if avg_vol <= 0: continue

            vol_ratio = today_volume / avg_vol
            quality   = compute_quality_score(gap, vol_ratio)

            if quality >= QUALITY_THRESHOLD:
                # Enter at today's close
                entry_price = today_close
                shares      = POSITION_SIZE / entry_price
                exit_date   = add_trading_days(today, HOLD_DAYS)
                data['open_positions'][ticker] = {
                    'entry_price':   entry_price,
                    'shares':        shares,
                    'entry_date':    str(today),
                    'exit_date':     str(exit_date),
                    'gap_pct':       round(gap, 4),
                    'quality_score': round(quality, 2),
                }
                n_open += 1
                already_entered.add(ticker)
                print(f"  ENTER {ticker}: gap={gap:+.1%} quality={quality:.1f}/70 "
                      f"vol_ratio={vol_ratio:.1f}x price=${entry_price:.2f} exit={exit_date}")
            else:
                data['skipped_quality'] += 1
                print(f"  SKIP  {ticker}: gap={gap:+.1%} quality={quality:.1f} "
                      f"< {QUALITY_THRESHOLD} threshold")

        except Exception as e:
            continue


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument('--exit', action='store_true',
                        help='Only process exits, skip entry scanning')
    args = parser.parse_args()

    data  = load()
    today = date.today()

    if today.weekday() >= 5:
        print(f"Weekend, skipping ({today})")
        return

    print(f"\n=== PEAD R28 Quality Filter Paper Trader — {today} ===")

    # ── VIX check ──
    vix_ok = True
    try:
        vix = get_vix()
        print(f"  VIX: {vix:.2f}", end='')
        if vix > VIX_LIMIT:
            print(f" ⚠  VIX > {VIX_LIMIT} — skipping new entries (exits still processed)")
            vix_ok = False
        else:
            print(f"  (below {VIX_LIMIT} limit)")
    except Exception as e:
        print(f"  VIX fetch failed ({e}), proceeding with caution")

    # ── 1. Check exits ──
    process_exits(data, today)

    # ── 2. Scan for gap entries (unless --exit mode or VIX too high) ──
    if not args.exit:
        if vix_ok:
            scan_gaps(data, today)
        else:
            data['skipped_vix'] += 1
            print(f"  Skipped entry scan (VIX regime filter). "
                  f"Total VIX skips: {data['skipped_vix']}")
    else:
        print("  --exit mode: skipping entry scan")

    data['last_update'] = str(today)
    save(data)

    # ── 3. Summary ──
    stats    = data['stats']
    open_pnl = 0.0
    print(f"\n  Open positions: {len(data['open_positions'])}")
    for tk, pos in data['open_positions'].items():
        try:
            hist = yf.download(tk, period='2d', auto_adjust=True, progress=False)
            if len(hist) > 0:
                col = 'Close' if 'Close' in hist.columns else hist.columns[0]
                cp    = float(hist[col].iloc[-1].squeeze())
                unreal = (cp - pos['entry_price']) * pos['shares']
                open_pnl += unreal
                print(f"    {tk}: entry=${pos['entry_price']:.2f} cur=${cp:.2f} "
                      f"unreal=${unreal:+.2f} exit={pos['exit_date']} "
                      f"gap={pos.get('gap_pct', 0):+.1%} q={pos.get('quality_score', 0):.1f}")
        except:
            pass

    total_pnl = stats['total_pnl'] + open_pnl
    wr = stats['wins'] / stats['n_trades'] * 100 if stats['n_trades'] > 0 else 0
    print(f"\n  Realized P&L:    ${stats['total_pnl']:+.2f}")
    print(f"  Unrealized:      ${open_pnl:+.2f}")
    print(f"  Total P&L:       ${total_pnl:+.2f}")
    print(f"  Win rate:        {wr:.0f}% ({stats['wins']}/{stats['n_trades']} trades)")
    print(f"  Portfolio value: ${VIRTUAL_CAPITAL + total_pnl:,.2f}")
    print(f"  Skipped (VIX):   {data['skipped_vix']}")
    print(f"  Skipped (quality): {data['skipped_quality']}")


if __name__ == '__main__':
    run()
